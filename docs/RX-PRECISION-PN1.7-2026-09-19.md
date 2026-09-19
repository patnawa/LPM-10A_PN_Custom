# RX PN 1.7: precision cable tracing

PN 1.7 is an experimental receiver prerelease for comparing cables in
a bundle. It includes the PN 1.6 reliability fixes and changes the feedback in
the existing **digital mode**. Use TX Digital with RX digital; the mode button
works as before. There is no new button combination or transmitter waveform.

**Hardware follow-up, 2026-09-19:** the owner reports **"Tested pass"** for
PN 1.7. This is recorded as an owner-reported functional device test pass.
A detailed test matrix and quantitative range/cable-selection measurements
were not supplied.

Published as [RX PN 1.7](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/rx-v1.7)
with the same tested binary and checksum below.

[Firmware](../LPM-10A/Firmware%20File/experimental/APP_LPM-10RX_PN1.7-precision.bin)
| [Device notes](../LPM-10A/Firmware%20File/experimental/RX-PN1.7-PRECISION-README.txt)
| [Checksum](../LPM-10A/Firmware%20File/experimental/RX-PRECISION-SHA256SUMS.txt)

Size: **26,152 bytes**, unchanged. SHA-256:
`5ccd7990043507911aeb357d83b0bc6fd054208ff6d253b7feea718e963d38e6`.
The vendor-facing version remains `3.0.0`. PN 1.7 changes 436 bytes relative
to PN 1.6; the PN 1.6 image is preserved.

## Why change the feedback

Actual PN 1.6 instructions gave the same strongest beep for clean coded windows
with high-to-low ADC differences of 45 and 1000 counts. A weak coded window
with one extreme high sample also received the strongest grade. These are
synthetic sample-window results, not measurements of physical cable coupling.
The previous 800 ms repeat hold could also continue through three completed
windows with no accepted signal, obscuring changes while moving the probe.

## Strength and release

Detection eligibility keeps the PN 1.6 contrast floor, level gate, exact-match
fallback and bounded bit-error matcher. Strength grading runs only after a
window qualifies. The strength score discards the largest positive and negative
deviations from the trimmed mean; a single extreme high or low sample therefore
does not dominate the grade. This does not remove arbitrary interference or
multiple outliers, and the score is not a calibrated distance measurement.

Five feedback levels span a wider range than PN 1.6's three levels. Hysteresis
around grade boundaries prevents small fluctuations from repeatedly switching
the beep rate. Stronger accepted signals produce faster repeats.

For samples `x` and the integer trimmed mean `m`, the score is
`sum(abs(x - m)) - (max(x) - min(x))`. Equivalently, remove one minimum and
maximum sample, then sum the remaining 46 absolute deviations around `m`.
Cold acquisition uses boundaries 800, 2400, 7200 and 18000. A rising grade
crosses 110% of its boundary; a falling grade drops below 90%. Expired or
rejected feedback starts fresh instead of retaining an old grade.

| Grade | Score on fresh acquisition | Pulse | Requested quiet gap |
|---|---:|---:|---:|
| 1, weakest | below 800 | 30 ms | 160 ms |
| 2 | 800-2399 | 30 ms | 110 ms |
| 3 | 2400-7199 | 30 ms | 75 ms |
| 4 | 7200-17999 | 30 ms | 45 ms |
| 5, strongest | 18000 or more | 30 ms | 20 ms |

The existing countdown order makes repeat periods one timer tick shorter than
the sum of the requested pulse and gap: 189, 139, 104, 74 and 49 ticks.
Active pulses and quiet intervals are not restarted by arriving detections.

A completed rejected window clears permission for further digital repeats.
If no result arrives, repeats expire 300 ms after the last accepted window.
An active tone finishes normally, including a key's 100 ms confirmation tone.
The independent 800 ms recent-signal countdown still protects active tracing
from idle auto-off. Acquisition still takes approximately 240 ms per digital
window: these changes improve feedback release, not the sampling rate.

The faster release deliberately gives less protection against occasional
missed windows. Weak or drifting reception can sound less continuous than on
PN 1.6. Compare both profiles on the actual bundle before selecting one for
routine use.

## Implementation boundaries

`rx-sdk/precision_fixes.py` applies only to the exact PN 1.6 image hash. It
replaces the digital detector, its publisher and speaker scheduler, and uses
verified NOP padding for the grade table and tone-start helper. No image growth
or additional persistent RAM is required. The existing grade byte now holds
0 for no repeats or 1-5 for strength; the scheduler also requires the recent
countdown to exceed 500. Accepted windows set that countdown to 800 as before.

The sampler's shared buffer is copied before rearming. Mode/gate validity is
rechecked during atomic result publication. Rejection clears the grade but
preserves the power keepalive, active tone and quiet interval. Earlier ADC,
battery, watchdog, sample ownership and DFT fixes remain in force. Analog/mains
analysis, timer handlers/configuration, keys and device binding are unchanged.

The detector's measured stack-write footprint is bounded by 152 bytes in these
tests, eight more than PN 1.6; its frame remains eight-byte aligned. This bound
excludes caller and interrupt frames. The replacement helpers occupy audited
slots at `0x08009F20` (publication), `0x0800A048` (grading), `0x080084FC`
(threshold/gap table), and `0x080086EC` (tone start). An independent scan found
no conflicting incoming branches or literal references.

## Build and validation

From `LPM-10A/Firmware File/rx-sdk`:

```text
python build.py --precision --write
python -m unittest test_image test_roadmap test_firmware_audit test_rx_followup test_rx_precision -v
python boot_emu.py ../experimental/APP_LPM-10RX_PN1.7-precision.bin
```

**80 test groups passed:** 58 image/profile and earlier RX regressions in
71.5 seconds, plus 22 PN 1.7 groups in 44.6 seconds. These were two separate
runs of the test modules listed above; some unchanged contracts are exercised
against more than one profile. The saved image matches its deterministic
rebuild and the recorded checksum.

The PN 1.7 suite executes actual candidate ARM instructions, with explicit
GPIO/ADC and interrupt-arrival models. It covers:

- The existing 3,624-window phase, bit-error, tone and seeded-noise corpus,
  preserving detector eligibility against the independent reference model.
- 768 single high/low outlier windows across every phase and sample position;
  none promotes the weak coded input out of its weakest grade.
- 864 histories at exact nominal and hysteresis boundaries, plus 56 cases
  across the ADC range, including strength scores above 65,535.
- All five cadences with four detection-arrival phases; incoming windows
  preserve the active tone and quiet interval.
- Rejected-window release, the 300 ms repeat timeout, retained power hold and
  100 ms key confirmation. No repeat starts at or after 300 ms without a new
  accepted window; an existing digital pulse finishes before 330 ms in the
  nominal timer model.
- Mode changes, gate reopening, buffer overwrite after snapshot, register and
  stack preservation, guarded publication and interrupt-mask restoration.
- A pending key interrupt at every instruction boundary on selected scheduler,
  accepted/rejected publisher and grading paths, deferred while interrupts are
  masked. This preserves key feedback and blocks results invalidated by a
  preceding mode request.
- Wrong-parent/tampered-image rejection, repeated-patch rejection, patch-log
  replay, unchanged image size and the preserved PN 1.6 binary.

The boot emulator reaches ADC initialization with a 64 MHz core and the same
TIM1/TIM5 configuration. It skips binding/version work and stops before ADC
initialization; it is not a full device boot or a measurement of interrupt
deadlines. `git diff --check` also passes. The owner-reported device pass is
recorded above; the published image retains the verified candidate bytes.

## Quantitative bundle comparison follow-up

Connect the transmitter to a known cable and compare the target with adjacent
cables at the same probe position and orientation. Move between them, hold
still near a grade boundary, remove the signal, and repeat with weaker coupling.
Record whether the new levels distinguish the target and whether release is
fast enough without excessive interruptions. Also check mode changes, the
lamp, key confirmation, battery behavior, analog mode and power-off.

Adjacent cables can carry the same valid code through coupling. Firmware
cannot infer which cable was directly connected from the code alone. PA2 and
PB12-PB14 still need board characterization before any gain-normalized strength
or physical sensitivity calibration is claimed. No quantitative range or
cable-selection measurements accompanied the owner's device pass report.
