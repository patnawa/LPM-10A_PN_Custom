# หลักฐานต่อเป้าหมาย Tone Probe — RX PN 1.11 / TX PN 2.14

**รุ่นถัดมา:** [RX PN 1.12 / TX PN 2.14](TONE-OVERLOAD-PN1.12-PN2.14-2026-09-20.md)
แก้การรายงานความแรงจากรหัสเก่าเมื่อข้อมูลล่าสุดค้างขอบบน ADC รายงานด้านล่าง
ยังเป็น snapshot ของ PN 1.11; ใช้ผลทดสอบ PN 1.12 จากรายงานใหม่แยกกัน
เจ้าของรายงานว่า **Digital/Analog รับได้ทั้งคู่และกวาดหาสายแม่นขึ้น**
ดู [บันทึกเครื่องจริงเบื้องต้น](TONE-DEVICE-FEEDBACK-2026-09-20.md): ยืนยันคู่
RX PN 1.12 / TX PN 2.14 แล้ว ผลติดตามล่าสุดพบว่า **Digital ยังดังต่อประมาณ
1 วินาทีหลังย้ายโพรบออกหรือกด Pause ที่ TX ส่วน Analog ไม่มีอาการนี้**
ปัญหาเวลาหยุดเสียง Digital ยังไม่ปิด
เจ้าของรายงานเพิ่มว่าฟังก์ชันอื่นที่ทดลองก็ผ่าน โดยไม่ได้แจกแจงรายการ
ยังไม่มีผลเทียบ Fluke
ผลใหม่ไม่ได้เปลี่ยน snapshot ของ PN 1.11 ด้านล่างเป็นผลผ่านของรุ่นนั้น

วันที่ตรวจ: 2026-09-20. **ผลประเมิน: ยังยืนยันว่าเหนือกว่า Fluke หรือเครื่องระดับโลกไม่ได้**

เฟิร์มแวร์มีการแก้บั๊กและมีหลักฐานว่าคำนวณเร็วขึ้น ติดตามความแรงเร็วขึ้นใน
ชุดข้อมูลจำลองที่ระบุ แต่ยังไม่มีผลทดสอบเครื่องจริงของคู่รุ่นใหม่นี้ และไม่มี
ผลเปรียบเทียบกับ Fluke ผู้ใช้ยืนยันว่าไม่มี Fluke และไม่มีออสซิลโลสโคป
การไม่มีเครื่องมือเหล่านี้ไม่ทำให้ผลจำลองกลายเป็นผลวัดจริง และไม่ขัดขวาง
การทดสอบซอฟต์แวร์หรือการทดลองบนสายที่ถอดจากระบบด้วย LPM ที่มีอยู่

รายงานนี้เป็น **snapshot ของไฟล์ตาม hash ด้านล่าง** ไม่ใช่ใบรับรองไฟล์ที่
อาจถูกเปลี่ยนหลังจากนี้ ไม่ได้รันทดสอบทุกชุดใหม่หรือแก้เฟิร์มแวร์ระหว่างตรวจ
ได้อ่านโค้ดทดสอบ รายงาน log ที่ยังอยู่ในเครื่อง และสร้างทั้งสองไฟล์ซ้ำในหน่วยความจำ
เพื่อเปรียบเทียบกับไฟล์ส่งมอบทุกไบต์
หลังการตรวจเอกสาร มีการรันทดสอบเพิ่มเติม 8 กลุ่มตามบันทึกถาวรด้านล่าง
โดยไม่เปลี่ยนเฟิร์มแวร์

## ตัวตนของไฟล์ที่ตรวจยืนยันแล้ว

| ไฟล์ | ขนาด | SHA-256 | หลักฐานตรวจครั้งนี้ |
|---|---:|---|---|
| [RX PN 1.11](../LPM-10A/Firmware%20File/experimental/APP_LPM-10RX_PN1.11-tracking.bin) | 26,152 bytes | `3e39ae56832cf92881ffdc46564e293278d6c3f1b55a9832b7a9a8350f031828` | Hash ตรง manifest และรายงาน; `test_tracking_integration.candidate()` สร้างได้ตรงทุกไบต์ |
| [TX PN 2.14](../LPM-10A/Firmware%20File/experimental/LPM-10A-TX_PN2.14-tone-recovery.bin) | 393,216 bytes | `a7402de6f18e39df55bbe53f5641efd5135f0de4d81f9407515cf9d8710c5527` | Hash ตรง manifest ทั้งสองชุดและรายงาน; `test_scan_recovery.build_candidate()` สร้างได้ตรงทุกไบต์ |

Manifest ที่ตรวจ: [คู่ RX/TX](../LPM-10A/Firmware%20File/experimental/TONE-TRACKING-SHA256SUMS.txt)
และ [TX แยก](../LPM-10A/Firmware%20File/experimental/TONE-RECOVERY-SHA256SUMS.txt)
ไม่มี hash ขัดกันในไฟล์เหล่านี้

## ข้อกำหนดกับหลักฐาน

คำว่า **พิสูจน์ในขอบเขต** หมายถึงเฉพาะไฟล์และกรณีที่ทดสอบ ไม่หมายถึง
ปราศจากบั๊กทุกกรณี คำว่า **ยังไม่ครบ** หมายถึงมีบางส่วนแล้วแต่ยังสรุปทั้งข้อไม่ได้

| ข้อกำหนดจากงาน | สถานะ | หลักฐานที่มี / สิ่งที่ยังขาด |
|---|---|---|
| มี RX และ TX ที่สร้างซ้ำได้และระบุไฟล์แน่นอน | พิสูจน์ในขอบเขต | ตรวจ hash และ rebuild ตรงทุกไบต์ตามตารางบน; [build RX](../LPM-10A/Firmware%20File/rx-sdk/build.py), [build TX](../LPM-10A/Firmware%20File/sdk/build.py) |
| เหลือ Digital/Analog พร้อมชื่อความถี่ตามที่ผู้ใช้เลือก | พิสูจน์ในขอบเขต | [TX recovery tests](../LPM-10A/Firmware%20File/sdk/test_scan_recovery.py) ตรวจการวนโหมด จอทั้งสองภาษา และ state การเลือก/พัก; [ภาพและคำอธิบาย](TONE-RECOVERY-PN2.14-2026-09-20.md) |
| แก้บั๊ก TX ปุ่มขวาโดยรักษารูปคลื่นเดิม | พิสูจน์ในขอบเขต | ทดสอบ parent fault และ repair, 812 ตำแหน่งของรูปคลื่น รวม mask/interruption/พักแล้วเริ่มใหม่; ยังไม่ใช่ผลวัด PA8/PB13 หรือการยืนยันบนเครื่อง |
| Digital ทน noise และติดตามความแรงดีขึ้น | พิสูจน์บางชุดข้อมูล; ยังไม่ครบการใช้งาน | [แบบจำลองและ corpus](DIGITAL-TRACKING-CANDIDATE-2026-09-20.md), [ARM tests](../LPM-10A/Firmware%20File/rx-sdk/test_rx_digital_tracking.py), [integration](../LPM-10A/Firmware%20File/rx-sdk/test_tracking_integration.py); ไม่มี ADC ที่บันทึกจากมัดสายจริงหรือผล false indication ต่อเวลาจริง |
| Digital อัปเดตเร็วขึ้นโดยไม่ใช้ข้อมูลผิดโหมด/ผิด gate | พิสูจน์ในขอบเขต | [overlap tests](../LPM-10A/Firmware%20File/rx-sdk/test_rx_digital_overlap.py) รัน TIM5 จริงครบ tick และแทรก interrupt; ชุดแรกยังต้อง 48 samples และเวลาเสียงจริงยังไม่วัด |
| การวัดความแรงสะท้อนตำแหน่งโพรบปัจจุบันเสมอ | ยังไม่ครบ | [fragment tests](../LPM-10A/Firmware%20File/rx-sdk/test_rx_tracking_fragments.py) ยืนยันโดยตรงว่า exact fallback อาจรายงานช่วงรหัสเก่าขณะที่ 16 samples ล่าสุดไม่มี tone; รายงาน PN 1.11 เปิดเผยข้อแลกเปลี่ยนนี้แล้ว |
| Analog ให้ feedback ละเอียดและคำนวณเร็วขึ้น | พิสูจน์ในกรณีที่ระบุ | [pinned artifact audit](experiments/tracking_profile_audit.py) ตรวจจำนวนคำสั่ง/stack/จังหวะเสียง; [integer tests](../LPM-10A/Firmware%20File/rx-sdk/test_rx_analog_integer.py) ตรวจค่า DFT; ไม่ใช่ hardware cycles, ระยะรับ หรือความง่ายในการเลือกสายของคน |
| ไม่ถดถอยด้านโหมด ปุ่ม เสียง ADC watchdog และ mains | มี regression; ยังไม่ครบทุกสภาวะ | [integrated tests](../LPM-10A/Firmware%20File/rx-sdk/test_tracking_integration.py), [race tests](../LPM-10A/Firmware%20File/rx-sdk/test_rx_analog_feedback_races.py); coverage เป็นชุดสถานะและจุด preemption ที่กำหนด ไม่ใช่ทุกลำดับเหตุการณ์/ระยะเวลา |
| Digital/Analog รุ่นใหม่ทำงานบนเครื่องของผู้ใช้ | ขาดหลักฐานใหม่ | ผู้ใช้รายงานรุ่นก่อน TX PN 2.13 / RX PN 1.10 ใช้สองโหมดเดิมได้; ผลนั้นไม่ยืนยัน PN 2.14 / PN 1.11 โดยอัตโนมัติ |
| เลือกสายเป้าหมายในมัดได้ถูกและรวดเร็วกว่าเดิม | ขาดผลเครื่องจริง | มี [protocol](TONE-PROBE-COMPARISON-PROTOCOL.md) แต่ยังไม่มีผล blind local pilot ของไฟล์ตาม hash นี้ |
| เหนือกว่า Fluke IntelliTone หรือคู่เทียบระดับโลก | ขาดหลักฐานตัดสิน | ไม่มีเครื่องคู่เทียบ ไม่มีทะเบียนเครื่อง ไม่มีผลทดลองเทียบ ไม่มีช่วงความไม่แน่นอน และไม่มีผลผ่าน acceptance gates; emulator เปรียบเทียบกับ PN เดิม ไม่ได้เปรียบเทียบกับ Fluke |
| สูงสุดหรือดีที่สุดในโลก | ไม่ได้พิสูจน์ | แม้ชนะคู่เทียบหนึ่งรุ่นในอนาคตก็พิสูจน์ได้เฉพาะรุ่น เงื่อนไข และตัวชี้วัดที่ทดสอบ ไม่ครอบคลุมเครื่องทุกชนิด/ทุกสภาพสาย |

## ตรวจความหมายของจำนวนทดสอบ

ตรวจ log ใน `%TEMP%` ที่ยังมีอยู่ ณ เวลาตรวจ:

| Log | ผลที่อ่านได้ | ขอบเขตที่อ้างได้ |
|---|---|---|
| `rx-pn111-all-tests.txt` | `Ran 256 tests in 318.978s` / `OK` | Discovery ของ RX SDK รวมรุ่นเก่าและ component tests; ไม่ใช่ 256 การทดสอบเฉพาะ binary PN 1.11 |
| `rx-pn111-integration.txt` | `Ran 41 tests in 29.190s` / `OK` | Adapters สร้าง profile PN 1.11 ครบชุดแล้วรัน Digital, Analog, overlap, races และ control contracts |
| `lpm10tx-pn214-tests.txt` | `Ran 60 tests in 20.712s` / `OK` | Recovery/profile และ regression ที่ระบุในรายงาน TX รวม tests ของ preserved PN 2.13; ไม่ใช่การวัดวงจรจริง |
| `rx-pn111-build.txt` | SHA ตรงตารางไฟล์ | Build ที่บันทึกไว้ให้ไฟล์เดียวกับ artifact; ตรวจ rebuild ในหน่วยความจำใหม่แล้วตรงกัน |
| `rx-pn111-profile-audit.json` | SHA ตรงตารางและผล Analog ตรงรายงาน | 3 instruction/stack fixtures, 12 cadence steps และ weak-to-strong fixture ของไฟล์ที่ pin hash |
| [follow-up log](experiments/results/pn111-followup-2026-09-20.log) / [metadata](experiments/results/pn111-followup-2026-09-20.json) | `Ran 8 tests in 40.300s` / `OK` | 2 Analog transient + 4 continuous Digital + 2 fragment groups; exact PN 1.11 และข้อมูล ADC จำลอง ไม่มีผลเครื่องจริง |

ตัวเลข **258 RX groups** ใน [รายงานรุ่น](TONE-TRACKING-PN1.11-PN2.14-2026-09-20.md)
คือ 256 กลุ่มใน log ข้างต้น บวก 2 กลุ่ม fragment/bounds ที่รันเพิ่มเติม
หลังตรวจเอกสารได้รัน fragment สองกลุ่มซ้ำรวมกับการทดสอบใหม่ 6 กลุ่ม และเก็บ
log 8 กลุ่มไว้ใน repository แล้ว จึงมีหลักฐานถาวรของ fragment แต่ไม่ได้อ้างว่า
รันทั้ง suite พร้อมกันอีกครั้ง กลุ่ม fragment ซ้ำกับยอด 258 เดิม และ 41 กลุ่ม
integration เป็นส่วนหนึ่งของ discovery ไม่ให้นำจำนวนที่ซ้ำมาบวกอีก

Log เดิมใน `%TEMP%` อยู่ในพื้นที่ชั่วคราวของเครื่อง ส่วน follow-up log
และ metadata อยู่ใน repository แล้ว โดยบันทึก environment, binary hash,
source hash และข้อจำกัดของการเก็บ metadata ภายหลังการรันไว้ด้วย
ผลตรวจ [Digital confidence](DIGITAL-CONFIDENCE-FOLLOWUP-2026-09-20.md)
รัน 2,364 ARM/model windows (2,304 clean fixtures เดิมและ 60 กรณีตัวอย่าง)
พร้อม [ผล JSON](experiments/results/pn111-digital-confidence-2026-09-20.json)
ยังพบข้อจำกัดสัญญาณอ่อนมากและ noise จำลองที่รับผิด วิธีกรองที่ทำให้พลาด
สัญญาณขณะความแรงเปลี่ยนจึงไม่ได้ใส่ลงเฟิร์มแวร์
ก่อนอ้างผลภายนอกควรเก็บคำสั่ง สภาพแวดล้อม source revision/diff hash และ output
ร่วมกับ hash ของ binary ทุกครั้ง โดยเฉพาะเมื่อมีการแก้โค้ดระหว่างรอบทดสอบ
การที่ไฟล์สร้างซ้ำตรงกันยืนยันตัว firmware แต่ไม่ทำให้ log เก่าผูกกับ source
ที่เปลี่ยนภายหลังโดยอัตโนมัติ

## หลักฐานเปรียบเทียบที่ยังไม่มี

ตรวจ [selection CSV](experiments/tone_probe_comparison_trials.csv) พบ 43 columns
และ **0 data rows**; ตรวจ [diagnostic CSV](experiments/tone_probe_comparison_diagnostics.csv)
พบ 41 columns และ **0 data rows** ทั้งคู่เป็น template ตามที่เอกสารแจ้งไว้
ไม่มีผลวัดศูนย์ที่ถูกตีความเป็นผ่าน และไม่มีแถวตัวอย่างถูกนำมาอ้างเป็นผลจริง

ก่อนตัดสินเป้าหมายต้องมีอย่างน้อยผลเครื่อง LPM ตาม hash นี้ บันทึกข้อผิดพลาด
และการเลือกผิดทั้งหมด การเทียบกับคู่เครื่องที่ระบุรุ่นโดยซ่อนสายเป้าหมาย
ผลบนเงื่อนไขสายที่อ้าง พร้อม raw records และผลประเมินทุกเกณฑ์ตาม
[comparison protocol](TONE-PROBE-COMPARISON-PROTOCOL.md#11-evidence-needed-before-claiming-success)
ข้อค้นพบเพิ่มเติมจากการทดสอบซอฟต์แวร์หลัง snapshot นี้ต้องแก้/ทดสอบและบันทึก
แยกตาม hash ของรุ่นที่แก้ ไม่ใช้ผลรุ่นนี้รับรองรุ่นถัดไป

**สถานะเป้าหมายรวมยังไม่สำเร็จ**: หลักฐานปัจจุบันรองรับการปรับปรุงซอฟต์แวร์
บางด้านและการเตรียมไฟล์ทดลอง ไม่รองรับการรับรองว่าแยกสายในมัดจริงเหนือกว่า
Fluke หรือเหนือกว่าเครื่องระดับโลก
