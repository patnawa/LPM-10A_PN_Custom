# RX PN 1.13 — temporary startup lamp identity diagnostic

**Purpose: identify whether the RX executes the newly supplied application.**
The unchanged tail after both custom and stock filenames, the recorded 50 ms
pulses, and the empty UDISK version label do not authenticate the running image.
This file is a diagnostic, not a Digital release fix or a new normal release.

Expected visible result: **the probe's flashlight comes on by itself at normal
power-on**, before pressing its flashlight key. Pressing that key turns it off.
Detection and audio remain those of PN 1.13. Physical lamp behavior and device
uptake require device observation; an absent marker by itself is not proof of
which other firmware is running. **Device result:** after the authorized copy,
the owner reports no automatic flashlight at startup, while pressing the
flashlight key turns it on normally. The identity check has not passed.

## Artifact

- [APP_LPM-10RX_PN1.13-id-lamp.bin](../LPM-10A/Firmware%20File/experimental/APP_LPM-10RX_PN1.13-id-lamp.bin)
- Length: 26,152 bytes.
- SHA-256: `e68cbb7d2d3cea417fec0bd76bdcf11c7ddef84fc8f13711edc31171be6709ce`.
- Exact parent: PN 1.13 audio-clock,
  `2cafd8a234a9b372a4d09c4969b28c8c35a45f05b72c57d2248d39f22cf7373b`.
- Desktop package: `LPM-10RX-PN1.13-identity-check`, containing the same marked
  image under `APP_LPM-10RX_V3.0.0_260416.bin`. Despite its stock basename this
  is the **PN 1.13 lamp diagnostic**, not stock firmware.

After reviewing the prepared diagnostic, the owner explicitly approved copying
it to the connected RX. At 21:15:47 +07:00 the guarded file copy wrote 26,152
bytes to `D:\APP_LPM-10RX_V3.0.0_260416.bin` and requested a disk flush without
an OS error. The target was revalidated as the observed NATIONS/N32L40X RX.
This is a successful host file-write operation, **not flash readback or proof
that the application now runs**. The subsequent owner observation was negative:
“เปิดแล้วไฟฉายไม่ติด”; manual lamp-key operation was reported normal.
[Copy evidence](experiments/results/pn113-identity-marker-device-copy-2026-09-20.json).
No files were deleted and no raw sectors were written.
The following root-listing attempt found that drive `D:` was no longer present.
That observation alone does not establish an automatic reboot or update success.

A follow-up static call-site audit found no normal post-startup PA10 writer
except the lamp-key toggle and power-off. A bounded actual-instruction check
in all three modes (2,000 TIM1 calls, 2,000 TIM5 calls and 2,001 boundary calls
per mode, ADC/pending status modeled) preserved the marked PA10 state. A lamp
input held for six scans then released can clear it; an ordinary power-button
input does not trigger that handler. This strengthens the uptake concern but
is not device flash readback. No new firmware was made in this follow-up.

The previous host write used a FileStream with WriteThrough and Flush(true).
One controlled retry using Windows' native file-copy operation, with the same
already approved binary, was completed after the owner reconnected RX at
21:22:00 +07:00. `System.IO.File.Copy` returned without an OS error, with
overwrite disabled and the same source SHA-256. The owner subsequently reported
**“ไฟฉายไม่ติด”** for the second startup too. Both transfer methods therefore
failed to produce the visible marker; the running image remains unverified. See the
[native-copy record](experiments/results/pn113-identity-marker-native-copy-2026-09-20.json).
The Windows listing subsequently showed the complete 26,152-byte filename.
A bounded raw-volume read still returned the template root (`UNKOWN.TXT`),
an empty allocation table and zeros in the first 32 KiB of the data area.
This demonstrates why the visible file listing is not flash readback; neither
observation proves acceptance. A volume Flush(true) completed without an OS
error before asking the owner to disconnect and power on.
No vendor evidence currently establishes that the previous method caused a
failure. The official Nations mass-storage sample is ordinary block storage,
not the missing FNIRSI bootloader implementation.

## Follow-up after both negative marker observations

No new image or further device write was made in this follow-up. The supplied
stock binary was checked for an obvious bootloader-facing checksum field:
reserved vector words are zero, and the final 24 bytes are initialized RAM
data consumed by the scatter loader, not an unexplained footer. No whole-image
checksum computation was identified in the application startup validators.
These findings do not exclude validation in the missing bootloader. The SDK
image-module documentation was corrected to remove its unsupported assertion
that the bootloader necessarily writes the raw file without a checksum check.

The [official download catalog](https://www.fnirsi.com/pages/manuals-firmwares)
and [manual](https://cdn.shopify.com/s/files/1/0694/8310/2426/files/LPM-10_User_Manual_New_EN.pdf?v=1788328015)
do not resolve RX-specific entry/commit steps, accepted filename/version rules,
or the meaning of `3.0.1.TXT`. The documented M+Power/display procedure cannot
be assumed to apply to the screenless receiver. A vendor clarification or
actual application-flash readback is needed before further firmware changes
can be meaningfully tied to this device's audio behavior.

A [support request draft](RX-UPDATE-SUPPORT-REQUEST-2026-09-20.md) records the
concrete questions and evidence. It has not been sent. The visible marker's
absence supports an uptake concern, but does not prove the old application
version, a downgrade restriction, a checksum rejection or a particular
bootloader failure.

Do not use deleting `3.0.1.TXT` as an update prerequisite; its presence does not
authenticate the application. See the [live-drive findings](TONE-CLIP-DIAGNOSIS-2026-09-20.md).

Subsequent [live SWD inspection](RX-SWD-FINDINGS-2026-09-20.md) adds stronger
identity evidence: the active Digital application uses a shifted RAM layout,
and its captured state contradicts the exact PN1.13 scheduler's prerequisites.
Thus the negative lamp observations now have independent runtime corroboration.
L1 protection still prevents a flash hash or exact installed-version identification;
the reason for update non-acceptance remains unknown. No further marker copy was
performed during this SWD investigation.

## Exact scope and verification

Only byte `0x08007D56` changes, `0x0C → 0x16`. The existing board GPIO-init
call at `0x08007D54` changes its target from `0x08008170` to `0x08008184` with
arguments GPIOA and mask `0x400`. It sets PA10 at boot instead of clearing it.
No delay, timer, RAM, detector, audio scheduler, version, binding or bootloader
bytes change. Original lamp-key and shutdown instructions remain intact.

Register semantics matter: older reverse-engineered GPIO helper labels in this
repo are reversed. Actual instructions at `0x08008170` write PBC at `+0x28`
(clear); `0x08008184` writes PBSC at `+0x18` (set). POD is at `+0x14`.
These definitions are in the
[Nations N32L40x manual, pages 114–117](https://www.nsing.com.sg/uploads/MCUProducts/N32L40x/Chip_Documentation/User_Manual/EN_UM_N32L40x_Series_User_Manual.pdf).
The marker tests model those register effects rather than relying on the old
function labels. Physical PA10-to-flashlight correspondence follows the
existing reverse engineering, not a board schematic.

Six focused groups passed. They check full-parent and call-site guards,
one-byte confinement, dry-run/write behavior, actual startup to the main loop,
and actual lamp-key/shutdown execution. Only PA10 differs on reaching main;
application globals and other GPIO outputs match the parent. The key toggles
PA10 and retains its 100-tick confirmation; shutdown clears PA10 in both images.
Clock/peripheral-ready flags and GPIO register effects are modeled; delays,
ADC initialization and licensing/version checks are stubbed. This establishes
software behavior, not hardware update success. Retained
[verification results](experiments/results/pn113-identity-marker-verification-2026-09-20.json).

Reproduce from `LPM-10A/Firmware File/rx-sdk`:

```powershell
python identity_marker.py
python identity_marker.py --write
python -m unittest test_identity_marker -v
```

The default command is a dry run. The write option can create only the fixed
local experimental artifact and refuses an unexpected existing output. It does
not copy to a removable drive. Ordinary firmware profiles remain unchanged.
