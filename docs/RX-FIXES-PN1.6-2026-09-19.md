# RX PN 1.6 sampling and feedback fixes — 2026-09-19

The three defects reproduced in the [PN 1.5 review](RX-REVIEW-2026-09-19.md)
are corrected in a separate **PN 1.6 local candidate**. Mode changes and gate
reopening require fresh samples, and repeated digital detections no longer
restart the current beep/gap. Device validation is pending. No device was
flashed and no release was published during this work.

## Candidate

- [RX binary](../LPM-10A/Firmware%20File/experimental/APP_LPM-10RX_PN1.6-followup.bin)
- [Device notes](../LPM-10A/Firmware%20File/experimental/RX-PN1.6-FOLLOWUP-README.txt)
- [SHA-256 checksum](../LPM-10A/Firmware%20File/experimental/RX-FOLLOWUP-SHA256SUMS.txt)

The file is **26,152 bytes**, the same size as PN 1.5. SHA-256:

```text
159bd15f50e3329fd866bdd7e1ebdac2900569dbd2686e2956d82585280457dc
```

It retains the vendor-facing `3.0.0` identity. Earlier binaries and build profiles
remain reproducible; PN 1.5 remains the published prerelease. PN 1.6 differs from
PN 1.5 in 1,229 bytes, all within declared, guarded patch ranges.

## Implementation

| Defect | Correction | Result |
|---|---|---|
| Mode changes mix previous and current samples | Keys queue a requested mode. The main loop applies it between analyzers with a short interrupt-masked reset of indices, sub-step and obsolete detection state. | Each new mode must fill its complete 48- or 64-sample window. Results from interrupted old-mode analysis cannot publish. |
| Gate reopening consumes a frozen old window | Gate threshold crossings latch invalidity. Closed gates stop acquisition; reopening resets acquisition. Analysis entry and result publication check validity. | Even a close/open pulse during an analysis pass remains invalid until the main loop discards that acquisition. |
| Fresh detections disturb digital cadence | The detector publishes only contrast grade and signal expiry. One repeat scheduler owns the beep and gap countdowns. | Constant strength retains its cadence; a changed grade takes effect at the next beep. Active key feedback is preserved. |

The gate updater never resets sampler indices: it can interrupt TIM5 partway
through a sample, so resetting there would let the resumed ISR publish into a
new window. Only the main loop changes the active mode or resets acquisition,
when neither interrupt handler is suspended underneath it. Gate and mode
invalidations are checked again under the interrupt mask when publishing results.

An already active beep finishes after a mode/gate change. Pending old results
and subsequent repeats are blocked. This preserves the shared key/lamp
confirmation countdown without introducing a second audio state machine.
On loss and reacquisition, an unfinished beep/gap also finishes normally.

The existing nominal cadence classes remain 30/30, 50/50 and 50/100 ms.
The inherited TIM1 ordering counts the first quiet tick when the active beep
reaches zero, so discrete repeat periods remain 59, 99 and 149 ticks. This
correction removes larger detection-induced disturbances; it does not claim
new oscillator or audio timing calibration.

Two previously unused, zero-initialized padding bytes hold metadata:
`0x20000049` is a pending mode request and `0x200000EF` holds gate validity.
Key handling and analog/mains output tails were compacted in place to provide
space for the helpers. Every reused block is guarded by expected bytes or a
PN 1.5 block hash, and the combined patch requires the exact full PN 1.5 image.

Main-loop watchdog feeding, physical power-off, idle handling, battery recovery,
ADC completion/timeout, DFT overflow correction and mains clear-before-rearm
behavior are retained. Vector, binding, version-page and timer configuration
bytes are unchanged. Long analysis operations run with interrupts enabled;
only ownership and publication transactions are masked.

## Validation

The final combined run passed **57 tests**: **28 PN 1.6 candidate groups** and
29 existing image/profile/roadmap/PN 1.5 groups. The binary matches a deterministic
rebuild and its recorded checksum. These counts include behavior exercised
against multiple profiles, not 57 independent defect fixes.

The automated suite executes actual candidate instructions under Unicorn and
uses explicit models at GPIO, ADC and interrupt-scheduling boundaries. Coverage
includes:

- All six directed mode changes with both partial and completed old windows,
  full new acquisition and signal reacquisition in all three modes.
- Closed/open digital and analog gates, latched close/open pulses, and a mode
  key interrupting actual digital or DFT analysis.
- The existing digital reference, bit-error, phase, tone and seeded-noise corpus.
- Sustained detections at seven arrival phases for each strength grade, grade
  changes, expiry/reacquisition, key tones and interrupt-mask preservation.
- ADC completion and timeout, idle deadlines, physical power-off and watchdog
  placement; the prior battery, ADC, DFT and TIM1 code remains byte-exact.
- Actual startup with pending interrupts, 126 gate-publication cases and 63
  key/LED/battery-state comparisons against PN 1.5.
- Analog/mains response comparison at 42 mode/bin/amplitude combinations,
  plus an actual TIM5 sample preempting mains immediately after rearm.
- Deterministic rebuild, unchanged image length and binding/vector regions,
  and replay of every declared patch write.

Independent review additionally checked original incoming branches and pointer
literals before reclaiming code slots, metadata overlap, and publication
interleavings with a pending key interrupt. No blocking issues were found.

The boot emulator still reaches ADC initialization with a 64 MHz core and the
existing TIM1/TIM5 register settings. It skips binding/version work and does
not establish a complete physical boot, oscillator accuracy, ADC conversion
latency, or electrical range/noise performance.

## Reproduce

From `LPM-10A/Firmware File/rx-sdk`:

```text
python build.py --followup --write
python -m unittest test_image test_roadmap test_firmware_audit test_rx_followup -v
python boot_emu.py ../experimental/APP_LPM-10RX_PN1.6-followup.bin
```

`diagnose_pn15.py` intentionally remains pinned to PN 1.5 and reproduces the
original defects. It is evidence for the old release, not a PN 1.6 verifier.

Before promoting this candidate, check it on the RX probe: repeated mode
switches during detection, weak/strong digital feedback, signal removal and
reacquisition, analog/mains operation, keys/lamp, power-off and a sustained
session. ADC/interrupt deadlines, front-end gain behavior and adjacent-cable
noise rejection still need measurement. These changes do not claim additional
range or calibrated mains sensitivity.
