# RX PN 1.8: finer cable pinpointing feedback

PN 1.8 is an experimental prerelease for comparing cables in a bundle.
It replaces PN 1.7's five broad digital strength grades with an interpolated
beep interval and extends the feedback range for strong signals. The published,
owner-tested PN 1.7 binary remains unchanged.

**Hardware follow-up, 2026-09-19:** the owner reports **"Tested pass"** for
PN 1.8. This is recorded as a functional device test pass; no detailed test
matrix or quantitative range/cable-selection measurements were supplied.
Published as [RX PN 1.8](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/rx-v1.8)
with the same tested binary and checksum below.

[Firmware](../LPM-10A/Firmware%20File/experimental/APP_LPM-10RX_PN1.8-pinpoint.bin)
| [Device notes](../LPM-10A/Firmware%20File/experimental/RX-PN1.8-PINPOINT-README.txt)
| [Checksum](../LPM-10A/Firmware%20File/experimental/RX-PINPOINT-SHA256SUMS.txt)

Size: **26,152 bytes**, unchanged. SHA-256:
`a588af8e0883fca119b9ed00e30761502ec0c4e0d2b6fee16a67c8b7cacc615d`.
The vendor-facing version remains `3.0.0`; identify the build by filename and
hash. Exactly 128 bytes differ from PN 1.7, in three guarded blocks.

## Measurable improvement over PN 1.7

The actual PN 1.7 instructions produce identical feedback for substantially
different synthetic strengths within a grade. PN 1.8 distinguishes these
inputs, including strong signals that previously all received the fastest
repeat. Each example below uses a clean coded window with low level 1000 and
the listed high-to-low differences, starting with no prior strength history.

| Pair of ADC differences | PN 1.7 quiet gaps | PN 1.8 quiet gaps |
|---|---|---|
| 60 and 100 counts | 110 / 110 ms | 123 / 109 ms |
| 120 and 300 counts | 75 / 75 ms | 104 / 80 ms |
| 1000 and 2000 counts | 20 / 20 ms | 50 / 38 ms |

These are CPU measurements of feedback resolution, not measurements of cable
selectivity, audible discrimination, or physical distance. PN 1.8 does not
make every signal beep faster; a broader range receives distinct rates.

## Feedback curve and stability

Signal eligibility and the trimmed strength score remain exactly as in PN 1.7.
The score excludes one minimum and maximum sample before summing deviations
around the trimmed mean. Only the mapping from that score to sound changes.

The raw quiet interval is linearly interpolated between these knots:

| Strength score | Raw target quiet interval |
|---:|---:|
| 0 | 160 ms |
| 800 | 130 ms |
| 2400 | 105 ms |
| 7200 | 75 ms |
| 24000 | 45 ms |
| 88000 or more | 20 ms |

Within a segment, the gap is the starting gap minus the integer part of the
proportional decrease. All arithmetic uses integers; strength remains 32-bit.
Segment widths, including the final 64,000-count span, fit in 16-bit storage.
Values at or above the last knot clamp before multiplication.

For current feedback, a proposed change of only one or two milliseconds keeps
the last published gap. A difference of three milliseconds or more updates it.
Comparison is against the last published gap, so a slow strength ramp still
makes progress. Rejected or expired feedback starts with a fresh target.
The same deadband applies at the endpoints: retained feedback can remain up to
two milliseconds from the raw target. This is a provisional stability setting,
not a measured auditory optimization.

Pulses remain 30 ms long. A new result leaves the active pulse and current quiet
interval intact; its rate applies to the next pulse. The existing timer order
gives a repeat period of `30 + gap - 1` ticks. Acquisition remains approximately
240 ms per digital window. Repeats stop after a rejected completed window or
300 ms without a new accepted window, while the separate 800 ms power keepalive
and key confirmation remain as in PN 1.7.

## Implementation and reproduction

`rx-sdk/pinpoint_fixes.py` requires the exact PN 1.7 image hash and replaces only
the mapper at `0x0800A048`, the curve table at `0x080084FC`, and the tone-start
helper at `0x080086EC`. The existing grade byte now holds a quiet interval
between 20 and 160 ms, or zero to prevent repeats. No persistent RAM is added.
The detector, snapshot handling, guarded publisher, scheduler entry, ADC,
timer handlers, analog/mains paths and device binding retain their existing
instructions outside those three blocks.

Use TX Digital with the existing RX digital mode; no new key combination is
needed. Build and verify from `LPM-10A/Firmware File/rx-sdk`:

```text
python build.py --pinpoint --write
python -m unittest test_image test_roadmap test_firmware_audit test_rx_followup test_rx_precision test_rx_pinpoint -v
python boot_emu.py ../experimental/APP_LPM-10RX_PN1.8-pinpoint.bin
```

**104 test groups passed:** 81 existing image/profile and RX regression groups
in 118.5 seconds, followed by 23 PN 1.8 groups in 43.2 seconds. These were two
separate runs of the modules listed above. Some unchanged behavior is checked
against multiple profiles; the count is not a number of separate fixes.

The new suite executes candidate ARM instructions against an independent
rational-arithmetic interpolation model. Coverage includes:

- Every segment boundary, all 141 integer target gaps, monotonicity, scores
  above 65,535, the full ADC score range and unsigned 32-bit extremes.
- All previous valid gaps around the three-millisecond update boundary,
  stale/empty history, slow ramps and endpoint retention.
- The existing 3,624-window phase/error/noise/tone corpus, with identical
  eligibility and the expected new gap for each accepted window.
- A broad ADC-amplitude sweep, same-band comparisons with PN 1.7 and 768
  isolated high/low outlier windows.
- Seven sustained input strengths at three arrival phases, without restarting
  active tones or quiet intervals; rejected-window release, the 300 ms repeat
  cutoff and preservation of 100 ms key tones.
- Mode/gate transitions and interrupt arrival at instruction boundaries on
  scheduler, publisher and interpolated/held/clamped mapper paths. Publication
  remains guarded and atomic; interrupt masks are restored.
- Shared-buffer overwrite after snapshot, register preservation, a bounded
  152-byte tested stack footprint, wrong-parent/tamper/double-apply rejection,
  patch-log replay and exact preservation of the PN 1.7 binary.

Independent review found no conflicting branch or literal references and
confirmed arithmetic bounds and publication invariants. The boot model reaches
ADC initialization with the existing 64 MHz clock and unchanged timer setup;
it skips binding/version work and is not a complete device boot. The saved
image matches a deterministic rebuild and its recorded checksum.

These checks do not measure real interrupt deadlines, front-end response or
audible discrimination. The separate owner-reported PN 1.8 device pass is
recorded above; the published binary retains the verified candidate bytes.

## Quantitative device comparison follow-up

Compare PN 1.7 and PN 1.8 with the same transmitter, cable bundle and probe
position. Check whether previously similar signals sound distinct, whether
the new intervals are easy to judge, and whether holding the probe still
produces distracting changes. Include both moderate and strong coupling,
moving between adjacent cables, signal removal/reacquisition and key feedback.

Coupled signals on neighboring cables can carry the same code. The strength
score remains uncalibrated and may depend on front-end behavior that has not
been characterized. Finer software feedback is established by the synthetic
tests; no quantitative cable-selection measurements accompanied the device
pass report.
