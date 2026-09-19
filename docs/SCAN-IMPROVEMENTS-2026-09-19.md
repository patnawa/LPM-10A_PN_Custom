# SCAN improvements — TX PN 2.6 and experimental RX digital detection

Both candidates are built and CPU-tested. **Owner-reported hardware pass,
2026-09-19:** after testing the new TX and RX firmware, the owner reports
"everything work perfect". This is a functional report on the owner's units;
no detailed test matrix, measured range/noise results or scope traces were
provided. The binaries and RX opt-in policy are unchanged.
Earlier binaries remain available. This work does not close the separate
[FLASH/length findings](FLASH-LENGTH-AUDIT-2026-09-19.md).

## Transmitter

Three reproduced bugs are fixed in `sdk/patches.py`, patch `scan-timing`:

| Site | Defect | Change |
|---|---|---|
| `0x08014310`, `0x08014314` | At counter 800, the counter resets but the bit index stays 16; the first high bit is only 49 ticks | Reset both counter and index before selecting the bit |
| `0x0801436C`, `0x0801469E` | Analog phase rollover and default-mode initialization execute debug formatting, critical sections and a task-context queue send inside TIM2 | Branch past logging, retaining the surrounding state updates |
| `0x0801449C` | Back forces the carrier off but leaves the gate cache high; resume can skip re-enabling it | A 16-byte helper invalidates the gate cache **before** publishing the enabled byte |

The digital `0xB6B6` pattern, 50-tick slots, timer settings and carrier configuration
are retained. Analog mode keeps its six-tick half-cycles. The full TIM2 body and
carrier hardware routines are byte-identical to stock. No new persistent RAM.

`sdk/verify_scan.py` runs the dispatcher, modulation, gate and key handlers,
including real TIM2 control flow with peripheral/RTOS calls trapped. Its 39 checks
cover ten digital frames plus wrap, extreme counter values, 6001 analog ticks,
mode changes, pause/resume from high and low states, return Home, inactive modes,
and 5000 TIM2 calls per mode with watchdog and backlight cadence assertions.
Twelve checks failed against PN 2.5 before implementation; all pass on PN 2.6.

The complete TX verifier also passes, including 61 screen states in both
languages. All 12 earlier audit regressions and the assembler self-test pass.
This proves intended logic/bytes, not physical waveform quality or ISR latency.

## Probe: conservative, opt-in detector improvement

The verified source is `APP_LPM-10RX_V3.0.0_260416.bin`, shipped inside the
official TX V2.0.7 package. The owner is unsure of the installed RX version.
This candidate is specifically **V3.0.0-based**, not a validated V3.0.1 patch.

`rx-sdk/rx_patches.py`, patch `digital-correlation`, replaces only the existing
336-byte digital analysis routine. It is `risk="untested"`, **off by default**.
The experimental image also includes the existing PN 1.0 battery-recovery fix.

The new detector:

1. Copies the completed 48-sample window, then re-arms the existing sampler.
2. Uses the vendor trimmed mean to threshold the samples.
3. Rejects insufficient contrast: sum of absolute deviations from that mean
   must be at least 192 ADC counts (an average of four counts per sample).
   This is a provisional bench-tunable threshold, not a calibrated signal level.
   Stock's high-sample sum and PA2 gates remain in force.
4. Accepts two exact sliding 16-bit `B6B6` matches, as stock did, **or** accepts
   the full 48-bit pattern at any of eight bit rotations with at most four
   errors total and at most two errors in each 16-sample block.
5. Uses the existing 50-ms beep/gap and 800-ms signal-hold outputs.

An initial correlation-only prototype regressed a synthetic clock/phase sweep
(310/640 detections versus stock's 589/640). It was **not retained**. Restoring
the stock exact-match route produced 591/640 and preserved every stock detection
in that sweep. This is why the design is a hybrid rather than a wholesale
replacement with a stricter full-window matcher.

This adds **bit-error tolerance**, not four-times oversampling or clock recovery.
The ADC's previous-conversion behavior and interrupt preemption remain as audited;
keeping the existing trimmed sampler avoids introducing a new single-sample
dependency. Gain control and strength grading remain unchanged because their
electrical meaning still needs confirmation. Very weak signals may be rejected
by the new contrast threshold even when stock could accept them.

## Probe verification

`python verify.py --digital` in `rx-sdk` passes **41 checks**, including image
footprint, vector table, every changed byte, disassembly and all prior battery
traces. `verify_digital.py` executes the firmware and its real trimmed-mean code:

| Synthetic experiment | Result |
|---|---|
| Clean patterns: eight phases, four amplitude/DC ranges | All 32 detected by stock and candidate |
| Three distributed bad bits | Stock 0/8; candidate 8/8 phases detected |
| Every single-bit corruption at every phase | All 384 recovered |
| Error budgets, contrast boundaries and 256 repeating 8-bit words | CPU matches independent Python model; only eight rotations of B6 accepted among periodic words |
| DC, ramps, isolated spikes and one isolated 16-bit burst | Rejected |
| 2048 seeded random/bi-level noise windows | No detections |
| 112 sinusoidal windows, including 50/60 Hz and 825 Hz | No detections |
| 640 approximate trimmed-sampler windows over phase, clock ratios 0.98–1.02 and noise | Stock 589/640; candidate 591/640, with no lost stock detections |
| Sampler still active / PA2 gate low | No processing / detection |
| Shared buffer overwritten immediately after sampling is re-armed | Completed stack snapshot remains valid |
| Rejected signal window | Sampling resumes; existing signal-hold countdown is not extended or erased |

Tested paths preserve callee-saved registers, restore the stack, and write only
owned stack bytes and existing flags. Maximum observed execution is 4100
instructions with at most 144 bytes of stack in this routine and its called
trimmed mean; interrupts and caller frames are additional. No physical cycle
timing or interrupt-stack bound is claimed. ADC/sampler/TIM5 code is unchanged.
Default PN 1.0 still passes its original 25 checks and builds without this patch.

Finite noise tests are **not** a real-world false-positive-rate estimate. The
small gain in the drift sweep is not evidence of greater cable range.

## Artifacts and reproduction

| Candidate | Bytes | SHA-256 |
|---|---:|---|
| `LPM-10A-TX_PN2.6.bin` | 393216 | `92304aa3ad6452bd60d81b96018c5db563014805d013668ff577b306c37a0f57` |
| `APP_LPM-10RX_PN1.1-digital-experimental.bin` | 26152 | `70c72436c30d91df52b6bc2935cde1f2077989b7b16c7223ddff829eb774d56f` |

TX, from `LPM-10A/Firmware File/sdk`:

```text
python build.py --write
python verify_scan.py
python -m unittest test_audit -v
python test_thumb.py
python verify.py
```

RX, from `LPM-10A/Firmware File/rx-sdk`:

```text
python build.py --only batt-critical-recover,digital-correlation --write
python verify.py --digital
python verify.py
```

The RX version string remains the vendor's `3.0.0`: no change to bootloader
binding or version-page handling. Identify the experimental build by its hash.

## Further hardware characterization

Before flashing RX, confirm hardware applicability and a stock recovery path.
Knowing USB update entry alone does not demonstrate rollback or version compatibility.
Test TX digital and analog SCAN, repeated pause/resume and mode changes; observe
the digital frame boundary and analog rollover with a scope if available.
Compare stock and candidate RX on the same target and adjacent cables, multiple
lengths, stationary/moving probe, weak/strong coupling and battery levels.
Confirm no-tone behavior, buttons, lamp, analog/mains modes, battery indication
and power-off. Do not treat this firmware as validation of the mains detector's
electrical safety. The owner's successful hardware report above supersedes
the original pre-test status; broader compatibility and quantitative
performance testing remain outstanding.
