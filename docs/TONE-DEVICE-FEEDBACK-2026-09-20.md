# Tone Probe — owner device feedback, 2026-09-20

**ผลล่าสุด: Digital/Analog รับได้ทั้งคู่และกวาดหาสายแม่นขึ้น แต่ Digital มีเสียงต่อประมาณ 1 วินาทีหลังย้ายโพรบออกหรือกด Pause ที่ TX; Analog ไม่มีอาการหน่วงนี้**

เจ้าของรายงานเพิ่มเติมว่า **ฟังก์ชันอื่นที่ทดลองก็ผ่าน** สำหรับคู่รุ่นที่ยืนยันด้านล่าง

คำรายงานจากเจ้าของในงานนี้:

> Digital และ Analog รับได้ทั้งคู่   กวามสายแล้วแม่นขึ้น

ผลติดตามจากเจ้าของ:

> ย้ายโพรบออกจากสาย  ไม่มีเสียงค้าง

> pause/resume ทำงายปรกติ

เจ้าของระบุรุ่น:

> 1.2/2.14

และยืนยันชื่อไฟล์ RX เพิ่มเติม:

> APP_LPM-10RX_PN1.12-overload.bin

ผลเพิ่มเติม:

> ฟั่งชั่นอื่นก็เทสผ่าน

ผลติดตามเรื่องเวลาหยุดเสียง (ได้รับภายหลังผลเบื้องต้นข้างต้น):

> mode digital เวลาเอาโพรบออกเหมือนเสียงจะดับช้าไปหน่อย

เจ้าของเลือกคำอธิบายอาการ:

> ดังต่อหลายครั้งหรือเกินประมาณ 1 วินาที

หลังจากเดิมยังไม่ได้ลองกรณี Pause เจ้าของทดลองเพิ่มเติมและรายงาน:

> กด pause แล้วเหมือนกันดังต่อ 1 วิ

> digital mode only analog ไม่ค้าง 1 วิ

เมื่อถามแยกเสียงหลังจอ TX แสดง Pause เจ้าของชี้แจงล่าสุดว่า:

> เสียงต่อเนื่องหนึ่งครั้งยาวประมาณ 1 วินาที

เมื่อถามเสียงยืนยันการกดสลับโหมดที่ RX ขณะ TX ยัง Pause อยู่
(ในโค้ดกำหนดไว้ 100 ticks หรือประมาณ 0.1 วินาทีตามฐานเวลาที่จำลอง):

> ยาวประมาณ 1 วินาทีเหมือนกัน

เจ้าของรายงานอีกกรณีแยกกัน:

> สลับ tx analog to digital ไม่ค้าง เสียงตัดทันที

The key-confirmation duration is also approximate. It is evidence for checking
the shared audio countdown, not a measurement establishing a tenfold clock
error. The TX Analog-to-Digital transition is a separate observation of prompt
cutoff; it does not establish Digital-to-Pause release timing.

หลังสร้าง RX PN 1.13 รุ่นทดสอบย้ายฐานเวลาตัดเสียง เจ้าของรายงานว่า:

> ลอง 1.13 แล้ว เหมือนเดิม

This is a separate owner-reported PN 1.13 trial. The reported symptom remains;
the candidate has **not resolved the device issue**. Version uptake remains
owner-reported, without flash readback. Do not relabel the earlier PN 1.12
results as PN 1.13 results or use a passing timer-fault simulation to override
this device feedback. The owner was then asked specifically about the button
on the RX probe itself while TX was paused, after PN 1.13, and replied:

> 1วิ

Thus both the Digital tail and the RX key-confirmation duration remain
approximately one second by the owner's report after PN 1.13. At that stage
no recording, hardware register dump or flash readback was available.

The owner subsequently supplied the desktop clip
`5da1ebc8-1c14-45a7-ae03-b1cc9fb00ba2.mp4`. It shows TX Digital → Analog
selection changes followed by **repeated short pulses** for about 0.8–1.0 s.
It does not visibly establish the earlier TX Pause or RX-key test. Measured
acoustic transitions are approximately 49–50 ms; normal PN 1.13 pulses are
30 ticks. This warrants an installed-image check without asserting an older
image is installed. The owner confirms using the unchanged custom filename
`APP_LPM-10RX_PN1.13-audio-clock.bin` on UDISK. A byte-identical copy with the
stock basename was prepared for a filename-acceptance check. The owner tried it
and reported **“เหมือนเดิม”**. The owner subsequently identified `3.0.1.txt`
on the RX UDISK and reported it would not stay deleted. Read-only inspection
after the owner connected it found volume `BOOTLOADER` and an empty (zero-byte)
`3.0.1.TXT`. This does not authenticate the running application. No device
write or deletion was performed by the inspection. See the
[clip diagnosis and live-drive evidence](TONE-CLIP-DIAGNOSIS-2026-09-20.md).

The owner then explicitly approved copying the prepared PN 1.13 lamp identity
diagnostic onto the connected RX. The 26,152-byte host write and disk-flush
request completed without an OS error at 21:15:47 +07:00. No files were deleted.
This is not flash readback. The owner subsequently reports **“เปิดแล้วไฟฉายไม่ติด”**;
when explicitly asked, pressing the lamp key turns the lamp on normally. Thus
the expected startup identity marker has **not** been observed. This raises an
update-uptake concern; it does not identify the running image. Earlier reception
reports remain observations with owner-reported file identity, not proof of
specific PN code executing. See the [identity diagnostic](RX-IDENTITY-MARKER-PN1.13-2026-09-20.md).

After reconnecting RX as requested, the owner allowed a controlled retry of
the same approved diagnostic with Windows' native file-copy operation. It
completed at 21:22:00 +07:00 without an OS error. The owner again reported
**“ไฟฉายไม่ติด”** at startup. Both transfers failed to produce the expected
marker; no further firmware changes or device writes were made in the follow-up.

The owner subsequently connected ST-Link V2 and authorized SWD inspection and
reverse engineering. DBG_ID identifies N32L406 with 128 KiB flash / 24 KiB SRAM;
L1 blocks flash readback. Initial operation with the programmer attached would
not start normally; disconnecting it restored normal battery operation. Powering
RX on its battery before attaching only GND/SWCLK/SWDIO enabled live measurements.
The owner provided board photographs and cooperated with a Digital/Pause capture.
Its 2,348 samples establish a shifted runtime layout incompatible with the stored
PN1.13 application's normal execution, and repeated audio scheduling for roughly
0.82–0.87 seconds after the final detection refresh. Exact installed version and
TX-button-to-sound delay remain unauthenticated/unmeasured respectively. These
findings supersede any assumption that the earlier named PN file was executing.
See [SWD findings](RX-SWD-FINDINGS-2026-09-20.md) and
[live release analysis](RX-LIVE-DIGITAL-RELEASE-2026-09-20.md).

This later, mode-specific report supersedes the initial broad move-away release
pass. The earlier approximate one-second duration is an owner estimate; the
later clip supplies timed evidence for a separate TX mode-change operation.
Digital release latency is an **open device issue**; the owner also reports it
after TX Pause. The pre-video clarification describes **one continuous sound**, not
several beeps separated by silence; the earlier answer combined those options
and did not distinguish them. Analog does not show this one-second tail. Pause/resume control
operation and delayed Digital audio cessation are separate observations.

This is a qualitative owner observation from a real-device trial, received
after the RX PN 1.12 / TX PN 2.14 test request. It adds new observations after
the owner previously said the requested pair had not yet been tested. TX is
owner-confirmed PN 2.14. The owner clarified the initially abbreviated RX
version by naming `APP_LPM-10RX_PN1.12-overload.bin`, confirming PN 1.12.
This feedback therefore applies to the owner-reported PN 1.12 / PN 2.14 pair.
The installed version/file identity is owner-reported, not a device flash readback.

| Observation | Evidence currently supplied |
|---|---|
| Digital reception | Owner reports it works |
| Analog reception | Owner reports it works |
| Sweeping to find a cable | Owner reports improved accuracy; no trial counts or specified comparison baseline |
| Digital move-away release | Later report: sound takes approximately one second to stop; open issue |
| Digital release after TX Pause | Latest clarification: one continuous sound for approximately one second after TX shows Pause; open issue |
| Analog release | Owner explicitly reports no one-second tail |
| RX mode-key confirmation while TX paused | Owner estimates approximately one second too; expected code duration is 100 countdown ticks |
| TX Analog-to-Digital transition | Owner reports sound cuts immediately |
| Pause/resume controls | Initially reported normal; later Digital audio-stop delay applies even after Pause |
| Other tested functions | Owner reports they also passed; individual functions and test conditions were not itemized |
| Installed TX version | Owner reports PN 2.14 |
| Installed RX version | Owner confirms `APP_LPM-10RX_PN1.12-overload.bin` (PN 1.12) |
| Fluke comparison | Not performed; owner previously reported no comparator available |

No error rate, bundle size, cable geometry, saturation stimulus or repeated
blinded-trial data was supplied. Timing from the subsequent clip applies only
to its visible TX mode changes. Do not turn this feedback into
numerical results or a pass for the specific all-4095 overload condition.
The comparison CSV templates remain without trial rows; this note preserves
the observation without inventing individual trial records.

This is an owner-reported basic reception pass for both modes, with a positive
qualitative cable-sweeping observation and an additional owner pass report for
other tested functions. The later Digital release complaint remains unresolved.
It does not establish every operating condition or comparative superiority.
See the [candidate report](TONE-OVERLOAD-PN1.12-PN2.14-2026-09-20.md) and
[comparison protocol](TONE-PROBE-COMPARISON-PROTOCOL.md).
