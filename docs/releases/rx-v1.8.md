# RX PN 1.8 - Finer cable pinpointing feedback

**Experimental prerelease for the LPM-10RX probe; owner-reported device test pass.**
PN 1.8 gives different beep rates to strengths that shared one of PN 1.7's five
levels, including stronger signals that previously all received the fastest
rate. On **2026-09-19**, the owner reported **"Tested pass"** for this build.
Use **TX Digital with RX digital mode**; buttons work as before.

## Downloads

- `APP_LPM-10RX_PN1.8-pinpoint.bin` — **RX probe only**, 26,152 bytes.
- `RX-PN1.8-README.txt` — changes, validation scope and update instructions.
- `RX-PN1.8-SHA256SUMS.txt` — binary checksum.

SHA-256:

```text
a588af8e0883fca119b9ed00e30761502ec0c4e0d2b6fee16a67c8b7cacc615d
```

Image size is unchanged. The vendor-facing version remains `3.0.0`; identify
this build by filename and hash. The pinned vendor input remains
`APP_LPM-10RX_V3.0.0_260416.bin`.

## Changes since PN 1.7

- Replace five discrete feedback levels with an interpolated quiet interval
  from 160 toward 20 ms. Stronger accepted signals repeat faster, with a wider
  feedback range before reaching the fastest rate.
- Retain the last published interval when a proposed change is below 3 ms.
  Slow strength changes still accumulate until they cross that threshold.
- Keep 30 ms pulses, approximately 240 ms acquisition, release after the first
  rejected completed window, and the 300 ms repeat timeout. Active tones and
  quiet intervals finish normally; key confirmation and the separate 800 ms
  recent-signal power hold are preserved.
- Retain PN 1.7's trimmed strength estimate, detection eligibility and all
  earlier reliability fixes, including fresh samples across mode/gate changes,
  guarded feedback publication, ADC completion, DFT arithmetic and watchdog
  handling. Analog/mains operation and device binding remain unchanged.

Only **128 bytes change in three existing blocks**. No persistent RAM is added,
and the published PN 1.7 binary is preserved.

## Validation and limits

- **104 CPU test groups passed:** 81 existing image/profile and RX regression
  groups, followed by 23 PN 1.8 groups, in two separate runs.
- Actual firmware instructions preserve eligibility across 3,624 synthetic
  windows. Tests cover interpolation, integer bounds, stability on slow ramps,
  cadence, release, key tones and publication during interrupts.
- The saved binary matches its deterministic rebuild and checksum. The owner
  separately reported a functional device pass; no detailed test matrix or
  quantitative range/cable-selection measurements accompanied that report.

The tests establish finer feedback, not improved physical cable-selection
accuracy. The strength score is uncalibrated, and neighboring cables carrying
the same coupled code can still be detected. The existing fast release may
make weak or drifting reception sound less continuous.

See the [implementation and validation report](https://github.com/patnawa/LPM-10A_PN_Custom/blob/rx-v1.8/docs/RX-PINPOINT-PN1.8-2026-09-19.md).
Companion tester: [TX PN 2.12](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/v2.12).

## Build and update

From `LPM-10A/Firmware File/rx-sdk`:

```text
python build.py --pinpoint --write
python -m unittest test_image test_roadmap test_firmware_audit test_rx_followup test_rx_precision test_rx_pinpoint -v
```

1. Verify the binary against the SHA-256 above.
2. With the probe off, hold **Power** until its LED illuminates.
3. Connect USB-C and copy the RX binary to the update drive; wait for completion.
4. Power-cycle and check digital, analog and mains modes.

Retain the prior working RX image. TX and RX firmware are not interchangeable.
