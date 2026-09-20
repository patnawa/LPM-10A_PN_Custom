# RX PN 1.13 / TX PN 2.14 — audio countdown test candidate

**สถานะเครื่องจริง: เจ้าของลอง PN 1.13 แล้วรายงานว่า “เหมือนเดิม” — ยังไม่แก้อาการเสียงค้าง**

**ผลจากคลิปล่าสุด:** หลังสลับ TX Digital → Analog มีบี๊บสั้นซ้ำต่อประมาณ
0.8–1.0 วินาที จังหวะประมาณ 50 ms ต่างจากพัลส์ปกติ 30 ms ของ PN 1.13
คลิปนี้ยังไม่ยืนยันกรณี Pause หรือเสียงปุ่ม RX จึงแยกจากคำรายงานเดิม
ดู [การวิเคราะห์คลิปและตรวจการรับไฟล์อัปเดต](TONE-CLIP-DIAGNOSIS-2026-09-20.md)

ผลนี้ได้รับระหว่างการตรวจซอฟต์แวร์ รุ่นทดสอบจึงไม่ถือเป็นคำตอบของอาการบน
เครื่องจริง แม้ผ่านการจำลองกรณี TIM1 ล่าช้า การยืนยันรุ่นเป็นคำรายงานจาก
เจ้าของ ยังไม่มีการอ่าน flash กลับมา เจ้าของตอบติดตามโดยระบุปุ่มบนตัว RX
เองหลัง PN 1.13 ว่ายังยาว **“1วิ”** ด้วย จึงยังอธิบายอาการด้วย TIM1 เพียง
อย่างเดียวไม่ได้ ต่อมาได้รับคลิปซึ่งแสดงพัลส์สั้นซ้ำตามรายละเอียดด้านบน

เจ้าของใช้ RX PN 1.12 กับ TX PN 2.14 และรายงานว่า Digital มีเสียงต่อเนื่อง
ประมาณหนึ่งวินาทีหลังย้ายโพรบออกหรือหลังจอ TX แสดง Pause ขณะที่ Analog
ไม่มีอาการนี้ เมื่อถามเสียงยืนยันปุ่มสลับโหมด RX ซึ่งโค้ดกำหนดไว้ 100 ticks
เจ้าของก็ประมาณว่ายาวหนึ่งวินาทีเช่นกัน ส่วนการสลับ TX จาก Analog เป็น
Digital ทำให้เสียงตัดทันที เก็บคำรายงานตามลำดับใน
[บันทึกเครื่องจริง](TONE-DEVICE-FEEDBACK-2026-09-20.md)

PN 1.13 ทดสอบการย้ายตัวนับความยาวเสียงและช่วงเงียบไปใช้ TIM5 ซึ่งเป็น
ตัวจับเวลาที่สร้างเสียงอยู่แล้ว เพื่อให้พัลส์เสียงจบได้แม้ TIM1 ส่ง interrupt
มาช้า การตรวจจับรหัส ความไว การวัดความแรง และข้อมูลสำหรับแยกสายคงเดิม
การเปลี่ยนนี้ใช้กับเสียง Digital, Analog และเสียงยืนยันปุ่ม เพราะใช้ตัวนับ
เสียงร่วมกัน TX ยังคงใช้ PN 2.14 ไฟล์เดิม

การจำลอง PN 1.12 พบว่าการจงใจหยุด TIM1 หนึ่งวินาทีทำให้เสียงหนึ่งพัลส์ยืด
ออกได้ แม้ตัวตรวจจับปฏิเสธสัญญาณใหม่แล้ว แต่ยังไม่มีหลักฐานว่า TIM1 บน
เครื่องจริงหยุดหรือเดินช้าด้วยสาเหตุใด ผลทดสอบจากเจ้าของยืนยันว่า
**อาการยังเหมือนเดิมหลังลอง PN 1.13** จึงต้องตรวจสาเหตุต่อ และไม่เปลี่ยน
ค่าตรวจจับจากการคาดเดาว่าสัญญาณยังอยู่

## Mechanism and scope

The exact PN 1.12 parent is retained. `BEEP` and `GAP` countdown work moves
from TIM1 to the existing TIM5 interrupt counter, once per forty delivered
TIM5 interrupts. At the nominal configured 64 MHz timer clock and ARR 1600,
one audio countdown tick is **1.000625 ms**. A normal 30-tick pulse is about
30 ms; a 100-tick uncertainty or key-confirmation pulse is about 100 ms.

The former TIM1 decrement is removed, so two timers cannot decrement the
same pulse. A brief saved-PRIMASK critical section protects the decrement
from a key interrupt installing a new confirmation pulse midway through
its read/modify/write operation. Existing TIM5 state supplies the timing;
no new persistent RAM or sample-buffer metadata is allocated.

RECENT, battery monitoring, key scanning and auto-off retain their existing
TIM1 timing. This candidate does not fix an aged completed ADC buffer or
claim to diagnose a physical oscillator, interrupt-priority or timer fault.
If TIM5 itself stops making progress, it cannot supply a time bound either.

The existing 32-bit TIM5 counter wraps approximately every 29.84 hours at
the nominal interrupt rate. Because forty does not divide 2^32, that wrap
has one shorter countdown interval; no interval is lengthened into a stuck
tone. Exact boundary behavior is covered by the patch tests.

## Reproduction

From `LPM-10A/Firmware File/rx-sdk`:

```powershell
python build.py --audio-clock --write
python -m unittest test_audio_clock_profile test_audio_clock_patch test_audio_clock_integration -v
```

The fixed profile inherits PN 1.12 and writes a distinct PN 1.13 file.
Earlier profiles and binaries remain available. Eleven full builds (the default,
PN 1.4 through PN 1.13) reproduce their saved artifacts byte-for-byte; see
[build results](experiments/results/pn113-profile-rebuilds-2026-09-20.json).
Twenty-five CLI profile test groups passed across the new audio-clock profile
and the preceding overload, tracking, sync and robust profiles.

The [audio integration suite](../LPM-10A/Firmware%20File/rx-sdk/test_audio_clock_integration.py)
passed **8 groups in one run, 13.429 seconds**, against bytes equal to the
delivered artifact. [Retained results](experiments/results/pn113-audio-clock-integration-2026-09-20.json)
include 48 tone cases, 36 actual key-confirmation cases, 504 key interrupt
schedules, and 7,024 paired detector input cases identical to PN 1.12.
Normal, slowed, faster and withheld TIM1 schedules leave the candidate's
100-tick confirmation approximately 100 ms on the nominal TIM5 grid.
Actual mains-analyzer pulse classes and loss/reacquisition also passed.

Four focused patch groups also passed: exact artifact/scope, wrong-parent
rejection, 10,140 helper cases covering every byte counter value with both
interrupt masks, and actual TIM5 dispatch through the 32-bit counter wrap in
all three modes. Only 105 bytes differ from PN 1.12, inside three declared slots.
Commands, scoped group counts and final source hashes are retained in the
[verification manifest](experiments/results/pn113-verification-2026-09-20.json).

These checks establish the implementation of the proposed clock change.
**They do not override the owner's unchanged physical symptom**, and they
do not establish oscillator frequency, actual IRQ delivery or flash uptake
on the device.

Built RX artifact:
[APP_LPM-10RX_PN1.13-audio-clock.bin](../LPM-10A/Firmware%20File/experimental/APP_LPM-10RX_PN1.13-audio-clock.bin),
26,152 bytes, SHA-256
`2cafd8a234a9b372a4d09c4969b28c8c35a45f05b72c57d2248d39f22cf7373b`.
The [paired checksum file](../LPM-10A/Firmware%20File/experimental/TONE-AUDIO-CLOCK-SHA256SUMS.txt)
also identifies the unchanged TX PN 2.14 artifact.

## Owner check

Use the new RX file with the same TX PN 2.14. Check these audible results:

1. Digital: receive steadily, then press TX Pause. Record whether the long
   continuous tail remains. Repeat by moving the probe away.
2. With TX paused, press the RX mode key and check whether the confirmation
   is now a short beep.
3. Check Analog reception/release and ordinary cable sweeping again, since
   all modes share the audio countdown.

These checks need no oscilloscope. Approximate listening results should be
reported as observations; a recording can establish elapsed time more precisely.
