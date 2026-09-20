# RX PN 1.9: robust strength for cable comparison

PN 1.9 is a **local experimental RX candidate**, not a published release or a
hardware-tested upgrade. It implements the first firmware stage of the
[bundle-tracing design](TONE-BUNDLE-OPTIMIZATION-2026-09-20.md): estimate strength
from the recognized code and make an unsuitable comparison audibly distinct.
TX Digital and the existing RX digital mode remain the operating combination.

[Firmware](../LPM-10A/Firmware%20File/experimental/APP_LPM-10RX_PN1.9-robust.bin)
| [Device notes](../LPM-10A/Firmware%20File/experimental/RX-PN1.9-ROBUST-README.txt)
| [Checksum](../LPM-10A/Firmware%20File/experimental/RX-ROBUST-SHA256SUMS.txt)

The image remains **26,152 bytes**. Vendor-facing version remains `3.0.0`;
identify the candidate by filename and SHA-256. PN 1.8 remains the published,
owner-tested comparison build. No TX firmware or previous RX binary changes.

SHA-256: `6128e0a4a0261f3da51bea232c8e431474033f0a09fd24283faa0a743b67fe3e`.
Exactly **485 bytes differ from PN 1.8**, confined to four audited regions.

## What improves

PN 1.8 uses total trimmed variation to determine the beep rate. Multiple
impulses can raise that variation even when the underlying coded signal is
weaker. PN 1.9 uses the difference between robust high/low levels associated
with the recognized code instead.

Actual ARM instructions produce these quiet gaps on synthetic ADC windows:

| Input | PN 1.8 | PN 1.9 |
|---|---:|---:|
| Clean 100-count code amplitude | 109 ms | 109 ms |
| Clean 150-count code amplitude | 100 ms | 100 ms |
| 100-count code with four added impulses | 95 ms | 109 ms |

Lower gaps mean faster repeats. The four-impulse case no longer outranks the
stronger clean signal. The exact inputs and original reproduction are in the
design document; the PN 1.9 tests repeat this comparison on both binaries.
This is a demonstrated numerical improvement, not a measured cable-selection
or range improvement.

## Recognition and strength are separate

Find eligibility retains PN 1.8's contrast floor, level gate, exact-match
fallback, and bounded-error matcher. Accepted signals have two strength paths:

1. If one of the eight code phases fits all 48 samples with at most four total
   bit errors and at most two in each 16-sample block, group all samples by
   that expected code. This provides 30 highs and 18 lows.
2. Otherwise, an accepted exact-match window uses only samples covered by its
   exact 16-bit `B6B6` matches. Overlaps count once. This union has at least
   24 samples, including at least 15 highs and 9 lows. Each selected sample's
   threshold label is justified by an exact code match. Unmatched material
   does not contribute to the strength estimate.

The second path preserves useful strength feedback when sampling drift
prevents a single phase from fitting the whole window. It does not recover
the clock or create independent evidence from overlapping code matches.

The implementation computes the usual median of each group, averaging its
two central samples when the group size is even and rounding down. Let
`A = median_high - median_low`. The legacy-scale strength is:

```text
S = 29*A - 12*floor(29*A/46)
```

This is exactly PN 1.8's trimmed score for an ideal 48-sample `B6` waveform
with that integer amplitude. It lets the existing interpolation curve and
3 ms deadband remain unchanged. It does not calibrate ADC counts to distance
or compensate for analog gain changes.

Sparse impulses and a few bit errors cannot dominate the group medians as
they can dominate total variation. Sustained interference, compression,
changing gain, or corruption of enough samples can still mislead this
estimate. A valid code on a neighboring cable remains a valid coupled code.

## What the operator hears

| Result | Pulse | Quiet gap | Meaning |
|---|---:|---:|---|
| Usable strength | 30 ms | Existing 20-160 ms curve | Faster repeats indicate larger fitted code amplitude |
| Unsuitable comparison | 100 ms | 160 ms | Code was found, but this window cannot provide a usable strength measurement |
| Rejected completed window | No new pulse | — | Repeat permission is cleared; any active pulse finishes |

The longer repeated pulse occurs when the high median is at the ADC's upper
rail (4095), or the estimated high level does not exceed the low level. A
zero low level alone is permitted: the input is an envelope measurement, so
zero during carrier-off slots does not by itself establish overload.

For a longer repeated pulse, try reducing the probe's physical sensitivity
or increasing tip distance, then compare again. This detects a rail-dominated
reading; it cannot detect all analog compression below the ADC rail. The
audibility and usefulness of this new pattern require a device listening test.

Normal and key-feedback pulse ownership remain intact. New detections do not
restart the active pulse or quiet interval. No new repeat starts at or after
300 ms without another accepted window. A normal pulse finishes before
330 ms, and an uncertainty pulse before 400 ms in the modeled timer behavior.
The separate 800 ms activity hold remains intact.

## Implementation boundaries

`rx-sdk/robust_fixes.py` applies only to the exact PN 1.8 image hash and is
selected by the new fixed `--robust` profile. Raw amplitudes and temporary
code/coverage tags stay in the detector's private stack snapshot. The shared
ADC buffer is copied before rearming as before. Sorting never changes it.

Space comes from a compact, behavior-equivalent rewrite of the shared
trimmed-mean routine and audited padding after the DFT return. All callers
still enter the same trimmed-mean address. Its unsigned byte count, unsigned
16-bit samples/result, zero-count behavior, and input immutability are
preserved. The rewrite was compared against the old ARM instructions for
every count from 0 through 255, including arbitrary 16-bit values and high
bits in the count argument.

The digital publisher, scheduler guards, sample timing, ADC completion,
mode/gate invalidation, battery rules, watchdog, and device binding retain
their earlier behavior. Normal cadence uses the same mapper. The tone-start
helper recognizes one extra internal value for the uncertainty pulse. No
new persistent RAM or image growth is needed.

The detector occupies 280 bytes at `0x08009E08`, the estimator 156 bytes at
`0x0800B670`, and its median helper 28 bytes at `0x0800B584`. The shared mean
occupies 62 bytes within a 64-byte reservation at `0x0800B630`. The other changed
region is the 34-byte tone-start slot at `0x080086EC`; the estimator is within
the old shared-mean region, so these are four changed regions in total.
The tested detector/helper stack footprint remains 152 bytes, excluding caller
and interrupt frames. No conflicting incoming references were found in the
reclaimed tails.

Sampling still takes approximately 240 ms per window. This candidate does
not implement rolling acquisition, automatic gain calibration, new key modes,
transmitter IDs, cable-confirmation hardware, or a new TX waveform. Those
stages depend on hardware characterization and separate timing work.

## Validation

**142 test groups passed**, in two runs: 108 image/profile and earlier RX
regression groups, followed by 34 PN 1.9 groups. The shared-mean audit separately
passed **3,072 old/new ARM comparisons**. An independent review also exercised
1,481 direct estimator cases across selected-group sizes and empty groups.

The existing **3,624-window** corpus retained all prior acceptance decisions:
1,055 windows produced ranked strength, 8 produced the upper-rail uncertainty
indication, and 2,561 were rejected. Its 640 phase/drift/noise windows retained
591 ranked finds and 49 rejections, with no uncertainty fallback. These are
synthetic corpus counts, not field error rates.

The largest observed execution count was **11,882 ARM instructions** across
3,665 corpus and adversarial-order windows. This is a tested maximum, not a
worst-case hardware cycle bound. The saved image matches its deterministic
rebuild and patch-log replay; prior images and all bytes outside the four
allowed regions are preserved. The boot model reaches ADC initialization with
the same 64 MHz clock and timer setup. `git diff --check` passes.

Tests execute actual ARM detector, median, mapper, publication, and audio
instructions against independently grouped Python medians. They cover phase,
DC/amplitude sweeps, bit errors, sparse impulses, overlapping/disjoint exact
matches, changing phase, clipping, stale/gated windows, key feedback, buffer
overwrite after snapshot, register/stack ownership, and patch guards.

The boot model skips binding/version operations and stops before ADC
initialization. CPU tests do not establish real interrupt timing, electrical
compatibility, analog gain behavior, audible discrimination, or bundle
selectivity. Hardware validation remains pending.

Build and verify from `LPM-10A/Firmware File/rx-sdk`:

```text
python build.py --robust --write
python -m unittest test_image test_robust_profile test_roadmap test_firmware_audit test_rx_followup test_rx_precision test_rx_pinpoint test_rx_robust -v
python compact_mean.py
python boot_emu.py ../experimental/APP_LPM-10RX_PN1.9-robust.bin
```

## Device comparison

Use the established RX update procedure for the same compatible probe, keep
PN 1.8 available, and use TX Digital. Compare PN 1.8 and PN 1.9 on the same
known target and neighboring cables with fixed sensitivity, distance, and
orientation. Include stationary and moving measurements, weak and strong
pickup, signal removal, and recovery from the longer uncertainty pulse.

Also check mode changes, key confirmation, lamp, analog/mains modes, battery
indication, and power-off. Record correct/incorrect/inconclusive selections
and the time needed to identify the cable. A general functional pass should
be recorded separately from quantified bundle performance.
