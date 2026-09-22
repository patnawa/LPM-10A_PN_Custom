# RX PN1.24: gain recovery, sample age and Analog analysis

PN1.24 builds on the exact PN1.23G image whose Digital motion/knob audio fix
was confirmed by the owner. It improves automatic gain recovery and rejects
outdated measurements, while reducing Analog processing work without changing
its spectral decision. These changes address reproducible firmware limits;
they do not establish a new physical pickup distance or calibrated accuracy.

PN1.24 is the current RX release. On 2026-09-22 the owner reported:

> 1.24 Tested pass no signal drop on digital and analog. Git push release doc update

This is a qualitative pass on the owner's receiver, separate from the emulator
measurements below. The [RX PN1.24 release](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/rx-v1.24)
and default build retain the exact tested bytes. Previous RX PN1.23 remains
available; TX PN2.26 remains current and needs no update for these RX improvements.

## Findings and scope

The original request was to maximize Digital/Analog gain and precision. The
existing hardware selector already reaches gain code 7. Available captures
cover one receiver at one probe position, so they do not justify new gain
calibration factors or lower detection thresholds. Instead, this change
addresses three measured limits in the firmware:

1. The 500 ms gain callback skips four callbacks after a change. Automatic
   corrections therefore occur up to 2.5 seconds apart. In both modes, a
   strong-to-weak input transition at 1000 ms leaves gain at 2 until 3000 ms.
2. A completed Digital sample window can remain pending indefinitely if the
   foreground loop stalls. In the reproduction, the window completes at
   640.900 ms, input disappears at 650 ms, and analysis at 1850.029 ms renews
   feedback from that old window. Audio restarts about 1.2 seconds after loss.
3. Analog computes all 31 DFT bins even for flat DC. The resulting decision
   is rejection, but this costs 59,886 emulated instructions.

The probes execute the actual Thumb sampler, analyzer, gain selector and
speaker paths. ADC values, the analog transfer function and interrupt arrival
times are modeled. Emulated instruction counts are not MCU cycle counts.

The ranked predictions were: a shorter hold should improve gain recovery with
the same hysteresis; timestamps should prevent delayed feedback from old
windows; and computing the Analog target bin first should reduce work while
preserving the decision. Each has an old-image control and a regression at its
actual call path.

## Changes

### Gain recovery

The callback still runs every 500 ms. It now skips one callback after an
automatic change, allowing another correction after 1 second. The existing
1900-count decrease and 450-count increase thresholds, knob ceiling, physical
gain mapping and normalization factors are retained. Mains mode bypasses cable
auto-ranging as before.

A current-acquisition completion marker prevents an automatic decision from
using an incomplete buffer left after a gain or mode transition. Manual knob
changes keep their existing behavior. Hold checks occur before the 48-sample
peak-to-peak scan so a held gain does not spend time scanning unnecessarily.
An isolated instruction probe measures 455 to 60 instructions for that callback,
with 48 to zero sample-buffer reads (86.8% fewer instructions on the hold path).
Both modes now step from gain 7 to 2 at 500 ms and back to 7 at 1500 ms in the
strong-to-weak test; PN1.23G does not recover until 3000 ms. Sustained overload
steps 7 to 2 to 1 to 0 at 500/1500/2500 ms. Boundary-amplitude tests retain a
stable gain instead of oscillating.

### Sample freshness

Completed windows carry a TIM5 timestamp. Readiness and result publication
both check age, so a stall before analysis or during analysis cannot renew
feedback from an expired measurement. Unsigned elapsed-time arithmetic handles
timer wrap. Expiry returns acquisition to a full fresh window; Digital overlap
cannot keep recycling old samples after a long stall.

The limits are 300 ms for Digital and 100 ms for Analog, matching their existing
new-feedback eligibility intervals. The timestamp uses the sampling/audio
timer, so delaying TIM1 alone does not make old samples appear current.

Gain changes retain PN1.23G's bounded continuation of already-confirmed Digital
feedback. They cannot renew its deadline. Mode changes, gate closure and
expired acquisitions invalidate measurements before further publication.

The age limits govern whether a result may publish; they are not a measured
TX-pause-to-silence specification. An accepted recent window still uses the
existing bounded feedback policy. Permanent tests cover expiry before
analysis, expiry during analysis despite a newer completion stamp, Analog's
separate late refresh, exact age boundaries, wraparound, full reacquisition,
and entry with interrupts already masked. The original long-stall scenario no
longer produces an eligible stale publication or late audio restart.

### Digital precision controls

The final combined image matches PN1.23G on 2,078 fresh ADC vectors. A
1,176-vector sweep retains the same 9-count peak-to-peak cutoff across eight
B6 phases and three DC offsets. Of all 256 repeating eight-bit words, only the
eight rotations of B6 are accepted; none of 128 seeded noise vectors is
accepted. Rail, flat-DC, spike and distributed-error controls also match.
Another 400 vectors cover all eight driven gain codes and existing rhythm
states. Detection, strength input, published rhythm, retained overlap samples,
callee-saved registers, D8, SP and PRIMASK remain equivalent for fresh input.

This establishes preserved software sensitivity and classification on the
tested corpus. It is not an electrical noise-floor or false-alarm-rate claim.

### Analog work reduction

The target is DFT bin 17. If its magnitude is at most 10, subtracting a
nonnegative noise estimate cannot reach the original acceptance threshold.
PN1.24 rejects immediately in that case. Otherwise it evaluates bins 2 through
31 except 17. Bin 1 was previously computed and then subtracted, so omitting it
does not change the result. The final unsigned 16-bit noise truncation and
integer division remain intact.

The replacement occupies the same 40 bytes at `0x08009F62..0x08009F8A`, with
no additional Analog RAM or stack. Raw strength, gain scaling, rail handling,
decision thresholds and guarded publication are preserved.

| Analog input | PN1.23G instructions | Selective change alone | Complete PN1.24 |
|---|---:|---:|---:|
| Flat DC | 59,886 | 1,972 | 2,036 |
| 50 Hz interference | 59,922 | 1,968 | 2,032 |
| Weak target tone | 60,387 | 58,397 | 58,488 |
| Normal target tone | 60,669 | 58,663 | 58,754 |

The separate and complete-build measurements show the cost of the sample-age
guards. Quiet-input work drops approximately 96.6% in the complete build;
accepted target windows save approximately 3.2%. A 344-vector differential
sweep covers phase, amplitude, DC offset, noise, wrong frequency, clipping and
full 16-bit sample values. Both the isolated optimization and complete PN1.24
match PN1.23G's decisions and raw strength results. The maximum Analog stack
depth in these instruction probes remains 80 bytes.

## Binary and RAM audit

The builder requires exact parent SHA-256
`a0822e2f454e08d0a213e63a1bbf0cac9948776dd8b067560d4786605b0307bb`.
It checks each overwritten instruction sequence before mutation. The existing
vector table, clock setup, ADC transaction, detector thresholds and gain
normalizer are preserved. Helpers stay below the application extension limit
`0x0801E000`; the bootloader and version-page placement are unchanged.

Three timestamp/validity words occupy `0x20000204..0x2000020F`, immediately
after the existing four-byte gain state. Independent analysis of the exact
parent resolves direct RAM references and bounded indirect arrays: ordinary
globals end at `0x20000113`, while the existing gain state occupies
`0x20000200..0x20000203`. Startup clears the proposed area. The reachable
application has no allocator path; merely finding zeroed RAM was not used as
proof that it was available.

A static stack walk across 136 reachable functions found no recursive calls,
dynamic stack allocation or unbalanced return. The largest main/TIM1/TIM5
software paths were 200/80/56 bytes. Conservatively adding both ISR paths and
two 108-byte extended/aligned exception frames gives a parent MSP floor of
`0x200013F0`, 4576 bytes above the new state end. This is a static bound for the
audited paths, not a physical stack high-water measurement; the new freshness
helpers add at most 16 bytes of local stack usage.

An independent reviewer also executed 192 boundary combinations (three modes,
four pending requests, four gate states, open/closed gate, and both PRIMASK
states). All legacy RAM through `0x20000203` matched PN1.23G exactly; the new
completion-valid word cleared on actual acquisition resets. Sixteen separate
freshness/publication probes preserved callee-saved registers, D8, stack and
interrupt state, including Digital's gain bridge.

## Build and validation

From `LPM-10A/Firmware File/rx-sdk`:

```powershell
python build.py --write
python verify_release.py
python -m unittest test_rx_precision_build test_rx_precision_streams test_rx_precision_analog test_rx_precision_digital test_rx_gain_response test_rx_sample_age_guard test_rx_analog_selective -v
python -m unittest discover -p 'test_*.py' -q
```

The default `pn1.24` profile builds the published release. The dedicated
`python rx_precision.py --write` command also reproduces the identical files
in `experimental/`, preserving the original tested artifacts.

Validation completed on 2026-09-22:

| Check | Result |
|---|---|
| Full RX regression run on the frozen PN1.24 implementation | 524 tests in 658.862 s; OK, one optional device-accepted container fixture skipped because it is absent |
| Final profile/publication, historical builder, freshness, Digital equivalence and artifact checks after release promotion | 59 tests in 13.441 s; OK |
| Saved update and raw readback | Exact rebuild, canonical container and checksum match |

The second run includes the final additional freshness/Digital tests and the
release-default changes added while the long suite was running. These run
counts overlap; they are not a count of distinct tests. Historical raw hashes
remain unchanged, including PN1.23F and PN1.23G. New profile stages are imported
lazily, and four separate import-order probes confirm no builder import cycle.

Use [APP_LPM-10RX_PN1.24-gain-precision-update.bin](../LPM-10A/Firmware%20File/APP_LPM-10RX_PN1.24-gain-precision-update.bin)
with the RX bootloader. The raw `.bin` is for analysis and building, not bootloader copying.
The installed identity should be `PN1.24.TXT`. See the
[RX update guide](RX-UPDATE-GUIDE.md) for the established procedure.

| Artifact | Size | SHA-256 |
|---|---:|---|
| `APP_LPM-10RX_PN1.24-gain-precision.bin` (raw) | 27,464 bytes | `780951565cca543e50d38537cd179ee1793562c6a4642b688c8143b0e4d8b1ce` |
| `APP_LPM-10RX_PN1.24-gain-precision-update.bin` | 32,768 bytes | `d08285d835562ed7154bdd75bb4d2a12b2875e694adfffe3d2970fbe4625609f` |

The build adds 520 flash bytes to G. The saved raw and update files match a
fresh rebuild byte for byte, and the update unwraps and rewraps canonically.
The generated `RX-PN1.24-SHA256SUMS.txt` matches both saved files. Boot emulation
reaches the ADC initialization boundary with the same 64 MHz clocks,
TIM1 prescaler/period 0/64000 and TIM5 prescaler/period 0/1600. The boot harness
stops at ADC initialization and does not establish a complete hardware boot.

The owner's device report confirms a test pass with no signal drop in Digital
or Analog. It does not provide quantitative pickup distance, cable-ranking
accuracy, noise-floor, gain-settling or receiver-to-receiver measurements.
The numerical gains and timing results in this report remain software-model
results; the hardware report does not convert them into measured device specifications.
