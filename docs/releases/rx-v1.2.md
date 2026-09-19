# RX PN 1.2 Reliability — activity-aware auto-off

**Experimental prerelease for the LPM-10RX probe only.** On 2026-09-19 the owner
reported "Test pass on new firmware tx rx" for TX PN 2.7 and RX PN 1.2.
The release binary is unchanged from the tested candidate. This is a general
functional pass, not quantified range/noise, rollback or cross-revision validation.

## Downloads

- `APP_LPM-10RX_PN1.2-reliability-experimental.bin` — RX only, 26152 bytes.
- `RX-PN1.2-README.txt` — changes, compatibility and update/recovery caveats.
- `RX-PN1.2-SHA256SUMS.txt` — binary checksum.

SHA-256:

```text
8176a40988eea3319c5c46dd65b0c97dce16c420b2e7fcbb3ddb05b28feef879
```

Required build input: `APP_LPM-10RX_V3.0.0_260416.bin`. The owner's earlier
installed probe version is unconfirmed. Internal version remains `3.0.0`;
identify this image by its filename and checksum, not the vendor version string.

Companion tester: [TX PN 2.7](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/v2.7).
**Do not copy a TX image to the probe or use the TX update procedure.**

## Changes from PN 1.1

- Fix idle auto-off ignoring existing signal/key activity on its deadline tick.
  The handler now checks that recorded activity before deciding to shut down.
- Only the existing 36-byte auto-off block changes; no image growth or extra RAM.
- Retain critical-battery recovery and error-tolerant digital detection.
- ADC/sampler, analog/mains detectors, timer rates, battery protection, physical
  power key, binding and vendor-version-page routines are unchanged from PN 1.1.
- Harden SDK image-range/string checks and refuse resized-image writes.

Match **TX Digital → RX digital**, or **TX 825 Hz → RX analog**. The separate
mains mode is unchanged. This release does not add oversampling or strength grading.

## Verification and limits

All **97 CPU checks pass**: 41 existing image/battery/digital checks plus 56
key/control/power checks. Includes auto-off boundaries, mode/lamp debounce,
physical power hold, timer housekeeping, stack/register preservation, synthetic
noise/phase/drift tests and byte ownership. Five SDK boundary tests pass.

Range, noise rejection and the digital contrast floor still need quantitative
bench validation. ADC conversion/preemption and interrupt-fed watchdog limitations
remain. Activity must already be recorded when the timer checks it; this is not
a guarantee for every simultaneous physical-key/signal arrival.

The patch remains opt-in. Default RX builds remain PN 1.0; `--digital` verifies
PN 1.1 and `--reliability` verifies PN 1.2. Earlier binaries are retained.

## Update and recovery

Owner-confirmed update entry: probe off, hold **SCAN**, connect USB; **UDISK**
appears. Confirm applicability and retain a matching recovery image plus the
working PN 1.1 file before updating. Verify the checksum before copying and
do not interrupt the update. The general test report does not document every
rollback step or prove compatibility with every revision. Vendor original not
attached. Flash at your own risk.

[Implementation, audit coverage and detailed follow-up](https://github.com/patnawa/LPM-10A_PN_Custom/blob/rx-v1.2/docs/RELIABILITY-AUDIT-2026-09-19.md)
