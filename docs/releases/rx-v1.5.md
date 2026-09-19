# RX PN 1.5 — Strong-signal and mains sampling fixes

**Experimental prerelease for the LPM-10RX probe; hardware validation pending.**
Strong valid ADC signals could overflow the shared DFT calculation and be
reported as zero in analog and mains modes. PN 1.5 corrects that arithmetic
and a mains buffer handoff race that could erase a fresh interrupt sample.

## Downloads

- `APP_LPM-10RX_PN1.5-audit.bin` — **RX probe only**, 26152 bytes.
- `RX-PN1.5-README.txt` — changes, validation scope and update instructions.
- `RX-PN1.5-SHA256SUMS.txt` — binary checksum.

SHA-256:

```text
6874d65549e3c67b3ad1020495effc93645e325e104eaa7697737a44c11fb0cd
```

Vendor-facing version remains `3.0.0`; identify this build by filename and hash.
The pinned vendor input is `APP_LPM-10RX_V3.0.0_260416.bin`.

## Changes since PN 1.4

- Keep DFT squared values and their sum in double precision through magnitude
  scaling; convert only the final result to integer. Strong analog/mains inputs
  now retain their magnitude in the reproduced cases.
- Clear the mains sample buffer before publishing readiness for TIM5 to refill
  it. An interrupt immediately after publication no longer has its sample erased.
- Retain PN 1.4's ADC timeout margin, digital detector and graded feedback,
  activity-aware auto-off, battery recovery and main-loop watchdog.

No image growth or additional persistent RAM. Vectors, device-binding logic,
sampling rates and digital detector bytes are unchanged from PN 1.4.

## Validation and limits

- **28 RX image/profile/roadmap/audit tests pass**, including 13 PN 1.5 groups.
- Actual DFT instructions agree with an independent complex-sum reference
  within two ADC counts across 162 sinusoidal cases and 40 random window/bin
  pairs. Full analog/mains analyzers recover the strong-signal beep.
- The actual TIM5/main-loop interleaving reproduces the lost sample on PN 1.4
  and preserves it on PN 1.5. Candidate bytes match a deterministic rebuild.

These are modeled hardware tests. No PN 1.5 device pass has been reported;
range, noise rejection, mains calibration, worst-case interrupt timing and
compatibility with other revisions remain unverified. The TX PN 2.12 Port
FLASH confirmation does not validate this RX image.

See the [full audit](https://github.com/patnawa/LPM-10A_PN_Custom/blob/rx-v1.5/docs/FULL-FIRMWARE-AUDIT-2026-09-19.md).
Companion tester: [TX PN 2.12](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/v2.12).

## Build and update

From `LPM-10A/Firmware File/rx-sdk`:

```text
python build.py --audit --write
python -m unittest test_image test_roadmap test_firmware_audit -v
```

1. Verify the binary against the SHA-256 above.
2. With the probe off, hold **Power** until its LED illuminates.
3. Connect USB-C and copy the RX binary to the update drive; wait for completion.
4. Power-cycle and check digital, analog and mains modes.

Retain the prior working RX image. TX and RX firmware are not interchangeable.
