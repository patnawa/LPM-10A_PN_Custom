# Digital release: supplied video and firmware identity check

**คลิปยืนยันว่าเสียง Digital ดังตามหลังการสลับ TX เป็น Analog ประมาณ
0.8–1.0 วินาที โดยเป็นบี๊บสั้นซ้ำ ๆ ไม่ใช่เสียงหนึ่งพัลส์ยาวหนึ่งวินาที**
จังหวะเสียงประมาณ 50 ms เปิด / 49 ms เงียบ ใกล้กับ scheduler ของ RX
รุ่นเก่า แต่ยังใช้ยืนยันรุ่นที่ติดตั้งจริงไม่ได้ PN 1.13 ยังไม่ถือว่าแก้อาการแล้ว

The owner supplied the local MP4
`C:\Users\Alpha\Desktop\5da1ebc8-1c14-45a7-ae03-b1cc9fb00ba2.mp4`.
SHA-256: `c2f0006778004c8cc0f07197dbe5af3b6631460a7d2012dd2c2a41c246824925`.
Its duration is 15.877 s, with approximately 33 ms video frame spacing.
Audio measurements include the AAC stream's +0.026 s start offset.

## What the recording establishes

The yellow selection on the TX display changes from Digital to Analog in
three inspected frame brackets. The last large acoustic falling edge follows
that visible change as follows:

| TX Digital → Analog display change | Last large tone falling edge | UI-to-sound interval |
|---|---:|---:|
| 1.400–1.466 s | 2.270 s | 0.804–0.870 s |
| 8.165–8.199 s | 9.186 s | 0.987–1.021 s |
| 14.364–14.398 s | 15.385 s | 0.987–1.021 s |

These are display-to-acoustic intervals, not measurements of the TX output
jack or RX electrical signal. The last sound includes a smaller acoustic decay
after the major falling edge. The recording does not visibly establish a TX
Pause operation or pressing the RX mode key; those earlier owner reports remain
separate, approximate observations.

The main sound is approximately 2516 Hz. In the final tail, eight acoustic
rise/fall pairs have separations 48.46–49.46 ms, median 49.10 ms, and onsets
repeat about every 98 ms. A second envelope-derivative method finds a 49–50 ms
opposite transition in each of the three tails. Separate approximately 2971 Hz
chirps last about 104–106 ms; their device origin is not established here.
Microphone processing and reverberation prevent equating these values with
exact electrical pulse widths.

See the [audio methods and results](experiments/results/clip-5da1ebc8/audio_audit_report.md),
[audio measurements](experiments/results/clip-5da1ebc8/audio_audit_results.json),
and selected-mode frames retained locally under
`docs/experiments/results/clip-5da1ebc8/`. The owner's recording and extracted
frames are not included in the public repository; numerical analysis is retained.

## Consequence for the diagnosis

The previous PN 1.13 experiment addressed a *single stretched pulse* caused by
deliberately withholding TIM1 in simulation. That fault was never established
on the device. The recorded endings instead show repeated short pulses.
The measured sound frequency also does not support a tenfold slower speaker
oscillator. This video therefore redirects investigation toward continued
scheduling/detection and firmware identity; it does not justify another blind
audio-clock adjustment.

PN 1.7 onward normally schedules 30-tick Digital pulses; PN 1.9 onward also
has a 100-tick uncertainty indication. PN 1.13 retains those pulse classes.
Earlier images permit 50/50 ms normal Digital scheduling with a longer hold.
This is a concrete match to the observed *pattern*, not proof that an older
image is installed. An unexpected runtime state remains possible.
See the [15-image / 42-case scheduler audit](RX-AUDIO-IDENTITY-AUDIT-2026-09-20.md).

All existing RX candidates retain the internal `3.0.0` version string. Their
PN filename alone is not readback evidence. The repo does not contain the RX
bootloader, so its filename acceptance and update-success behavior are unknown.
Do not transfer the TX bootloader's known behavior to the RX as a fact.

## Filename check and live UDISK follow-up

The owner confirms copying the file with its original custom name:
`APP_LPM-10RX_PN1.13-audio-clock.bin`.

A separate desktop folder `LPM-10RX-PN1.13-update-check` contains a byte-identical
copy named `APP_LPM-10RX_V3.0.0_260416.bin`, the stock basename documented in
[RX-AUDIT.md](RX-AUDIT.md). **This copy is still PN 1.13, not stock firmware.**
Its expected length is 26,152 bytes and SHA-256 remains
`2cafd8a234a9b372a4d09c4969b28c8c35a45f05b72c57d2248d39f22cf7373b`.

This is a filename-acceptance check, not a new firmware revision or a proven
fix. Use the RX probe's own UDISK mode (probe off, hold SCAN, connect USB),
copy this one image, allow the update to finish, then restart the probe.
The owner tried this copy and replied **“เหมือนเดิม”** (unchanged). Renaming did
not resolve the observed symptom; it does not by itself prove or disprove image
acceptance. A changed sound pattern would support uptake
of a different application; exact identity still needs readback or a separately
tested explicit identity marker. No device write occurred during that clip
analysis or the filename-copy preparation.

The owner then reported an undeletable file, clarified as `3.0.1.txt` on the
RX's UDISK, and connected the RX for read-only inspection. Windows exposed
drive `D:` with volume label `BOOTLOADER`, model `NATIONS SD Flash Disk USB
Device`, USB identifier ending in `N32L40X`. Its root contains `3.0.1.TXT`,
**zero bytes**, with filesystem timestamp 2008-04-18. The other root entry is
`System Volume Information`. Despite being enumerated, `Test-Path` returns false
and `Get-Item` cannot open the `3.0.1.TXT` path.

A bounded, read-only raw FAT16 inspection found 2,048-byte sectors, two reserved
sectors, two FATs of 13 sectors each, and the root at byte 57,344. The actual
root begins with the zero-length short-name entry `UNKOWN  TXT`, followed by
the volume label `BOOTLOADER`. It contains no long-name entry for `3.0.1.TXT`.
The owner unplugged and reconnected the RX; both the Windows listing and the
different raw root result repeated. The mismatch therefore persists after a
reconnect. Its exact bootloader/caching cause is unknown; this is **not proof
of a malformed `3.0.1` short-name entry**, since no such raw entry was observed.
See the [second read-only snapshot](experiments/results/rx-udisk-reconnect-2026-09-20.json).

The filename alone cannot distinguish an application-version marker from a
bootloader-version marker or another virtual-disk label. No installed firmware
image is exposed as an ordinary root file. The read-only inspection performed
no deletion, formatting or firmware write. See the
[retained observation](experiments/results/rx-udisk-readonly-2026-09-20.json).
The next prepared diagnostic is an explicit startup lamp marker. The owner
subsequently approved its copy to RX; the host write completed at 21:15:47
+07:00, with physical uptake still pending. It is not a release-delay fix. See the
[marker artifact and verification](RX-IDENTITY-MARKER-PN1.13-2026-09-20.md).

The current [FNIRSI package](https://cdn.shopify.com/s/files/1/0694/8310/2426/files/LPM-10A_Firmware_V2.0.7.zip?v=1782962470)
contains RX `APP_LPM-10RX_V3.0.0_260416.bin`, byte-identical to the stock parent
used here (SHA-256 `083f3825e8f8a38627417e26732e88fd13ee0dbe3c13ca1cd1cd9c4875c7c8c5`).
Its instructions do not identify `3.0.1.TXT` or specify RX filename acceptance.
The stock input matching the vendor download does not prove compatibility or
successful installation on this specific probe.

## Reproduction

From the repository root:

```powershell
python docs/experiments/clip_video_audit.py
python docs/experiments/results/clip-5da1ebc8/audio_audit.py
```

The retained frame timestamps support manual display-state classification.
No firmware bytes or detection thresholds were changed during this clip analysis.
