# RX PN 1.3 Digital Strength — graded beeps, ADC completion and main-loop watchdog

**Experimental prerelease for the LPM-10RX probe.** On 2026-09-19 the owner
reported "test pass on device" for the TX PN 2.8 / RX PN 1.3 candidates and
requested publication. This release contains the exact tested RX roadmap binary.

## Downloads

- `APP_LPM-10RX_PN1.3-roadmap.bin` — RX only, 26152 bytes.
- `RX-PN1.3-README.txt` — changes, update instructions and validation limits.
- `RX-PN1.3-SHA256SUMS.txt` — binary checksum.

```text
fa51768b92d08fafe280312a61b2059e3050cfa69c6b43fb4d443640708d43f2
```

The vendor-facing RX version remains `3.0.0`; identify this build by filename
and checksum. The required vendor build input is `APP_LPM-10RX_V3.0.0_260416.bin`.

## Changes from PN 1.2

- Add IntelliTone-style contrast-based feedback for accepted digital detections:
  strong = **30 ms on / 30 off**, medium = **50/50**, weak = **50/100**.
  Exact and tolerant correlation acceptance rules are preserved.
- Reset idle time while `signal_recent` or the beep/key countdown is active.
  Normal beep gaps already reset frequently enough; this adds protection for
  recorded detection without a current beep countdown.
- Serialize ADC channel selection through conversion completion and wait for
  ENDC before reading DAT. Restore the incoming interrupt mask. A bounded
  timeout requests reset instead of returning stale or fabricated samples.
- Feed the watchdog from the main loop, removing TIM1's unconditional refresh.
- Retain critical-battery recovery, key behavior, physical power-off and the
  stock analog/mains analysis, clock rates, image size and device binding.

Use **TX Digital → RX digital**, or **TX 825 Hz → RX analog**.
Companion tester: [TX PN 2.8](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/v2.8).

## Validation and limits

Owner-reported device pass; nine roadmap CPU test groups and five image-tool
tests pass, including existing digital/key/power suites, delayed ADC completion
and timeout, watchdog behavior and all three beep cadences. The boot model
preserves the 64 MHz clock and timer setup. PN 1.2's 97 checks still pass.

The device report is a general functional pass, not quantified range, adjacent
cable rejection, gain-normalized strength or worst-case ISR timing validation.
The grading is inspired by IntelliTone feedback; it does not implement Fluke's
protocol or establish equivalent performance. ADC masking changes interrupt
latency. This build remains opt-in and experimental; the earlier RX profiles
remain reproducible.

## Build, update and recovery

From `LPM-10A/Firmware File/rx-sdk`:

```text
python build.py --roadmap --write
python -m unittest test_roadmap test_image -v
```

Verify with `certutil -hashfile APP_LPM-10RX_PN1.3-roadmap.bin SHA256`.
Owner-confirmed update entry: probe off, hold **SCAN**, connect USB; **UDISK**
appears. Copy the RX image and wait for completion without interrupting it.
Keep the working PN 1.2 file and a matching recovery image. Do not use the TX
image or TX update procedure. Compatibility with every revision and every
rollback scenario has not been established.

[Implementation, audit corrections and detailed coverage](https://github.com/patnawa/LPM-10A_PN_Custom/blob/rx-v1.3/docs/ROADMAP-IMPLEMENTATION-2026-09-19.md)
