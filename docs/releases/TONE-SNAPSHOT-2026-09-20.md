# TX PN 2.14 / RX experiments — development snapshot, 2026-09-20

Archived at the owner's request while the currently working devices remain in
use. This is a **prerelease checkpoint**, not a recommendation to update RX.
TX PN 2.12 keeps the GitHub Latest designation; previous releases are preserved.

## Current device status

- The owner reports Digital and Analog reception, improved cable sweeping,
  working TX pause/resume and other tested functions with TX PN 2.14. The other
  functions were not itemized, and no Fluke comparison was performed.
- Digital audio still follows signal loss or TX Pause by roughly one second;
  Analog does not show the same delay. RX PN 1.13 has **not** resolved that issue.
- A live recording of 2,348 SRAM samples shows a different RX layout from all
  stored V3.0.0-based PN images. It is incompatible with normal execution of the
  exact PN 1.13 image. Earlier owner-reported RX filenames and device passes do
  not authenticate the firmware actually installed.
- After the last detection refresh, RX starts eight more pulses and stops
  scheduling audio about 0.82–0.87 seconds later while both timers advance
  normally. This interval is measured inside RX, not from a synchronized TX
  button timestamp.
- ST-Link identifies N32L406 with L1 read protection. No firmware or option-byte
  writes, unlock, erase, explicit halt or reset were performed in that inspection.
  The owner confirmed normal RX operation after disconnecting USB and SWD.
- RX firmware compatibility and UDISK acceptance remain unresolved. Keep the
  existing working receiver; the archived RX images are not verified rollback
  images or a supported ST-Link recovery package.

## What is preserved

TX PN 2.14 retains only `Digital 454 kHz` and `Analog 825 Hz`, removes the
unsuccessful Sync32/Pulse-test menu options, and repairs RIGHT-key carrier-cache
invalidation. Digital displays the nominal carrier frequency; Analog displays
the nominal modulation rate of the same carrier.

RX PN 1.9–1.13 source, binaries and CPU tests preserve the robust-strength,
Sync32, tracking, overload and audio-clock experiments. The separate PN 1.13
startup-lamp diagnostic is an identity experiment, not a normal-use release.
TX PN 2.13 / RX PN 1.10 Sync32 is retained as a historical trial with a reported
hardware failure, not a working feature.

The source archive also includes the reverse-engineering reports, numerical
results, read-only capture tools and release plot. The owner's recording,
extracted frames and raw device captures remain local. Vendor stock binaries
remain excluded from Git; build tools require the matching official inputs.

## Downloads

- `LPM-10A-TX_PN2.14-tone-recovery.bin`: exact preserved TX candidate.
- `LPM-10A-tone-experiments-2026-09-20.zip`: eight candidate/diagnostic images,
  their notes, and an internal `SHA256SUMS.txt`. Read its `README.md` first.
- `TONE-SNAPSHOT-2026-09-20.md`: these status notes.
- `SHA256SUMS.txt`: checksums of the three assets above.

No firmware bytes were changed for this checkpoint.

| Image | Bytes | SHA-256 |
|---|---:|---|
| TX PN 2.14 | 393216 | `a7402de6f18e39df55bbe53f5641efd5135f0de4d81f9407515cf9d8710c5527` |
| RX PN 1.12 | 26152 | `4ea18c52bde25353a9a38dbf46775425860f7859bc2c10e3c908a7bff4044403` |
| RX PN 1.13 | 26152 | `2cafd8a234a9b372a4d09c4969b28c8c35a45f05b72c57d2248d39f22cf7373b` |
| RX PN 1.13 lamp diagnostic | 26152 | `e68cbb7d2d3cea417fec0bd76bdcf11c7ddef84fc8f13711edc31171be6709ce` |

## Verification for publication

- TX: 60 existing test groups passed in 20.608 seconds using
  `python -m unittest test_scan_recovery test_recovery_profile test_sync_profile test_portflash_status test_scan_hardware -q`.
- RX: 23 existing test groups passed in 13.805 seconds using
  `python -m unittest test_audio_clock_profile test_audio_clock_patch.AudioClockPatch test_audio_clock_integration.AudioClockIntegration test_identity_marker -q`.
- These tests check software profiles, exact image bytes and modeled execution.
  They do not establish physical update acceptance or resolution of the Digital
  tail. TX tests emitted existing unclosed-file ResourceWarnings but passed.

## Investigation and resuming work

Resume RX update work after obtaining a compatible image and a verifiable update
path. The vendor support request is prepared but has not been sent.

- [Live SWD findings](https://github.com/patnawa/LPM-10A_PN_Custom/blob/main/docs/RX-SWD-FINDINGS-2026-09-20.md)
- [Measured Digital release](https://github.com/patnawa/LPM-10A_PN_Custom/blob/main/docs/RX-LIVE-DIGITAL-RELEASE-2026-09-20.md)
- [Official image and SDK search](https://github.com/patnawa/LPM-10A_PN_Custom/blob/main/docs/RX-OFFICIAL-IMAGE-SEARCH-2026-09-20.md)
- [Vendor support draft](https://github.com/patnawa/LPM-10A_PN_Custom/blob/main/docs/RX-UPDATE-SUPPORT-REQUEST-2026-09-20.md)

สรุป: เก็บงานและไฟล์ทดลองไว้ก่อนตามคำขอ เจ้าของใช้เครื่องเดิมต่อได้
ยังไม่แนะนำให้อัปเดต RX 1.13 ซ้ำ และยังไม่ถือว่าแก้อาการ Digital ดับช้าสำเร็จ
