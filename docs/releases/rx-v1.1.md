# RX PN 1.1 Digital — experimental error-tolerant detection

**Experimental prerelease for the LPM-10RX probe only.** The owner reported
testing the new TX and RX firmware on 2026-09-19 and that "everything work
perfect". This confirms reported operation on their units, not measured range,
false-alarm performance, rollback or compatibility with every hardware revision.

## Download and base version

- `APP_LPM-10RX_PN1.1-digital-experimental.bin` — **RX only**, 26152 bytes.
- `RX-PN1.1-DIGITAL-README.txt` — changes, compatibility and recovery caveats.
- `RX-PN1.1-SHA256SUMS.txt` — firmware checksum.

SHA-256:

```text
70c72436c30d91df52b6bc2935cde1f2077989b7b16c7223ddff829eb774d56f
```

Base: `APP_LPM-10RX_V3.0.0_260416.bin` from the official **TX V2.0.7 package**.
The owner's previous installed RX version is unconfirmed; earlier references
to V3.0.1 were clarified as uncertain. This is not a validated V3.0.1 patch.
The internal vendor version string remains `3.0.0`; identify this build by hash.

The companion tester release is [TX PN 2.6](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/v2.6).
TX and RX images and update procedures are not interchangeable.

## What changes

- Retain stock detection of two exact sliding B6B6 matches.
- Add correlation over eight bit rotations of the 48-sample window, allowing
  up to four errors overall and two per 16-sample block.
- Add a provisional DC-independent contrast floor; keep stock PA2 and
  high-sample-sum gates. Very weak signals may fail the new contrast floor.
- Include the existing PN 1.0 critical-battery recovery fix.

Only the digital detector changes for tracing. Match **TX Digital → RX
digital**, or **TX 825 Hz → RX analog**. RX analog and separate mains modes,
ADC sampler, timer configuration, beep cadence and signal hold are unchanged.
No image growth, new persistent RAM, binding-code or vendor-version-page edits.
This is bit-error tolerance, not oversampling, clock recovery or strength grading.

## Verification

All **41 RX checks pass**, including original battery regressions, image and
disassembly integrity, model agreement, memory ownership and register checks.

- All 384 single-bit corruptions recovered.
- Three distributed bad bits: stock 0/8 phases detected, candidate 8/8.
- Synthetic phase/clock/noise sweep: stock 589/640, candidate 591/640, with
  every stock detection in that sweep preserved.
- No detections in 2048 seeded noise-only windows or 112 single-tone windows.

These finite synthetic tests do **not** establish real range or false-alarm
rates. The release binary is unchanged from the owner-tested candidate.
The patch stays opt-in; default RX builds remain PN 1.0.

## Update and recovery caution

Update-mode entry was owner-confirmed: probe off, hold **SCAN**, connect USB;
the "UDISK" drive appears. The later functional report does not document every
update/rollback step or another revision's compatibility. Confirm applicability
and a stock recovery path for your unit before flashing; verify the checksum
before copying. Do not use the TX update procedure on the probe. The original
vendor image is not attached. Flash at your own risk.

[Implementation, tests and remaining work](https://github.com/patnawa/LPM-10A_PN_Custom/blob/rx-v1.1/docs/SCAN-IMPROVEMENTS-2026-09-19.md)
