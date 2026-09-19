# RX PN 1.7 - Precision cable tracing

**Experimental prerelease for the LPM-10RX probe; owner-reported device test pass.**
PN 1.7 adds finer digital strength feedback and faster release when moving
between cables. On **2026-09-19**, the owner reported **"Tested pass"** for this
build. Use **TX Digital with RX digital mode**; the existing mode button works
as before, with no new key combination or transmitter waveform.

## Downloads

- `APP_LPM-10RX_PN1.7-precision.bin` — **RX probe only**, 26,152 bytes.
- `RX-PN1.7-README.txt` — changes, validation scope and update instructions.
- `RX-PN1.7-SHA256SUMS.txt` — binary checksum.

SHA-256:

```text
5ccd7990043507911aeb357d83b0bc6fd054208ff6d253b7feea718e963d38e6
```

Image size is unchanged. The vendor-facing version remains `3.0.0`; identify
this build by filename and hash. The pinned vendor input remains
`APP_LPM-10RX_V3.0.0_260416.bin`.

## Changes since the published PN 1.5 release

- Five strength levels span a wider ADC contrast range. Removing one extreme
  high and low sample from strength scoring reduces outlier influence; 10%
  hysteresis steadies the grade near a boundary. Stronger signals repeat faster.
- Fixed 30 ms digital pulses retain their timing when fresh detections arrive.
  A rejected completed window stops further repeats; without a new result,
  repeats expire after 300 ms. Active tones finish, including key confirmation.
  The 800 ms recent-signal hold still protects tracing from idle auto-off.
- Inherit PN 1.6's sample ownership fixes: mode changes reset acquisition at
  a main-loop boundary, gate reopening requires fresh samples, and invalidated
  analysis cannot publish stale feedback.
- Retain the earlier DFT, mains sampling, ADC, battery recovery and watchdog
  corrections. PN 1.7 preserves PN 1.6's detection eligibility, sampling rates,
  analog/mains analysis, buttons and device-binding behavior.

Digital acquisition still takes approximately 240 ms. Faster release provides
less smoothing of missed windows, so weak or drifting reception may sound less
continuous than PN 1.6. Adjacent cables carrying the same coupled code can still
be detected; the strength levels are not calibrated distance measurements.

## Validation and limits

- **80 CPU test groups passed:** 58 image/profile and earlier RX regression
  groups, plus 22 PN 1.7 groups, in two separate runs.
- Actual firmware instructions preserve eligibility across 3,624 synthetic
  windows and exercise all five cadences, outlier resistance, hysteresis,
  release timing, key feedback and interrupt-safe publication.
- The saved binary matches its deterministic rebuild and checksum. The owner
  separately reported a functional device pass; no detailed test matrix or
  quantitative range/cable-selection measurements accompanied that report.

See the [implementation and validation report](https://github.com/patnawa/LPM-10A_PN_Custom/blob/rx-v1.7/docs/RX-PRECISION-PN1.7-2026-09-19.md).
Companion tester: [TX PN 2.12](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/v2.12).

## Build and update

From `LPM-10A/Firmware File/rx-sdk`:

```text
python build.py --precision --write
python -m unittest test_image test_roadmap test_firmware_audit test_rx_followup test_rx_precision -v
```

1. Verify the binary against the SHA-256 above.
2. With the probe off, hold **Power** until its LED illuminates.
3. Connect USB-C and copy the RX binary to the update drive; wait for completion.
4. Power-cycle and check digital, analog and mains modes.

Retain the prior working RX image. TX and RX firmware are not interchangeable.
