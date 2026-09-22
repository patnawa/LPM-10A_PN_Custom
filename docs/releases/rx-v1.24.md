# RX PN1.24 — faster gain recovery and stable Digital/Analog feedback

The owner tested PN1.24 on the receiver and confirmed on 2026-09-22:

> 1.24 Tested pass no signal drop on digital and analog.

This release retains PN1.23G's Digital audio continuity during probe motion and
knob changes, improves gain recovery, and prevents expired measurements from
restarting feedback after a foreground stall. TX PN2.26 remains compatible.

- Automatic gain corrections can occur every **1 second instead of 2.5 seconds**.
  Decisions require a complete, recent acquisition at the current gain.
- Digital and Analog check sample age before analysis and before publishing a
  result; Digital overlap cannot refresh an expired analysis.
- Quiet-input Analog analysis uses **about 97% fewer modeled instructions**.
  Detector thresholds, strength scaling and maximum knob gain are preserved.
- The final image matches PN1.23G across **2,078 Digital and 344 Analog vectors**.
  Build, ABI, interruption, mode/gate and audio-continuity regressions pass.

Validation: the full RX run completed 524 tests (one optional external fixture
skipped); 59 focused checks after release promotion also passed. Default and
historical builds reproduce their exact recorded firmware bytes.

Timing and instruction figures are emulator results. The device confirmation
establishes the owner's reported signal continuity; pickup distance and
calibrated electrical precision were not measured by that confirmation.

**Install the RX `APP_LPM-10RX_PN1.24-gain-precision-update.bin` asset.**
Turn the probe off, hold **SCAN**, plug in USB, and copy the update file to the
`BOOTLOADER` drive using Explorer. Verify `PN1.24.TXT` when entering the update
drive again. The raw `.bin` asset is for rebuilding/emulation, not installation.

Update SHA-256:
`d08285d835562ed7154bdd75bb4d2a12b2875e694adfffe3d2970fbe4625609f`

[Full analysis and verification](https://github.com/patnawa/LPM-10A_PN_Custom/blob/rx-v1.24/docs/RX-GAIN-PRECISION-PN1.24-2026-09-22.md) ·
[RX update/rollback guide](https://github.com/patnawa/LPM-10A_PN_Custom/blob/rx-v1.24/docs/RX-UPDATE-GUIDE.md).
