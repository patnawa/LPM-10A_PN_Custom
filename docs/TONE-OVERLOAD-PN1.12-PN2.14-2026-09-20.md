# RX PN 1.12 / TX PN 2.14 — Digital upper-rail feedback

Follow-up: [PN 1.13 audio-clock test candidate](TONE-AUDIO-CLOCK-PN1.13-PN2.14-2026-09-20.md)
investigates the delayed sound. PN 1.12 observations and results below remain
specific to that preserved version; a physical fix has not been confirmed.

**สถานะ: ผ่านการทดสอบโค้ด ARM; เครื่องจริงรับได้ทั้งสองโหมด แต่มีปัญหา Digital หยุดเสียงช้าประมาณ 1 วินาที**

เจ้าของรายงานว่า **Digital/Analog รับได้ทั้งคู่และกวาดหาสายแม่นขึ้น** โดยยืนยัน TX PN 2.14
และชื่อไฟล์ `APP_LPM-10RX_PN1.12-overload.bin` แล้ว ดู
[บันทึกผลจากเจ้าของ](TONE-DEVICE-FEEDBACK-2026-09-20.md)
ผลนี้เป็นความเห็นจากการใช้งาน ไม่ใช่อัตราความแม่นยำที่วัดหรือผลเทียบ Fluke
เจ้าของรายงานต่อมาว่าฟังก์ชันอื่นที่ทดลองก็ผ่าน โดยไม่ได้ระบุรายการแยก
ผลติดตามล่าสุดระบุว่า **Digital ยังดังต่อประมาณ 1 วินาทีหลังย้ายโพรบออก
หรือกด Pause ที่ TX ส่วน Analog ไม่มีอาการนี้** ปัญหาเวลาหยุดเสียงยังไม่ปิด
ผลติดตามนี้แทนที่ข้อสรุปเบื้องต้นเรื่องไม่มีเสียงค้าง โดยคงคำรายงานเดิมไว้ในบันทึก

แก้กรณีที่ RX ยังพบรหัส Digital ในข้อมูลเก่า แต่ข้อมูลล่าสุด 16 จุดค้างที่
ขอบบน ADC ทั้งหมด เดิมอาจส่งเสียงบอกความแรงจากรหัสเก่า ทำให้เข้าใจว่าความแรง
ปัจจุบันยังเปรียบเทียบได้ PN 1.12 ใช้เสียงเดิมสำหรับผลที่ไม่น่าเชื่อถือ:
บี๊บ 100 ms เว้น 160 ms แทนการจัดอันดับความแรงในกรณีนี้

เสียงนี้หมายถึง **ยังใช้ค่านี้เปรียบเทียบความแรงไม่ได้** ไม่ใช่การยืนยันว่า
เลือกสายถูกแล้ว ลองถอยโพรบออกเล็กน้อยแล้วเปรียบเทียบอีกครั้ง การตรวจขอบบน
เพียงกรณีนี้ไม่ครอบคลุมการอิ่มตัวของวงจรรับทั้งหมด

รุ่นนี้รวมการติดตาม Digital และ Analog ของ
[PN 1.11](TONE-TRACKING-PN1.11-PN2.14-2026-09-20.md) ใช้ TX PN 2.14 ไฟล์เดิม
มีเพียง Digital 454 kHz / Analog 825 Hz ไม่มี Sync32 หรือ Pulse test
ยังไม่มีผลเทียบ Fluke หรือหลักฐานว่าเหนือกว่าเครื่องระดับโลก

## Files

| Device | File | Bytes | SHA-256 |
|---|---|---:|---|
| RX probe | [APP_LPM-10RX_PN1.12-overload.bin](../LPM-10A/Firmware%20File/experimental/APP_LPM-10RX_PN1.12-overload.bin) | 26,152 | `4ea18c52bde25353a9a38dbf46775425860f7859bc2c10e3c908a7bff4044403` |
| TX tester | [LPM-10A-TX_PN2.14-tone-recovery.bin](../LPM-10A/Firmware%20File/experimental/LPM-10A-TX_PN2.14-tone-recovery.bin) | 393,216 | `a7402de6f18e39df55bbe53f5641efd5135f0de4d81f9407515cf9d8710c5527` |

[Device notes](../LPM-10A/Firmware%20File/experimental/TONE-OVERLOAD-PN1.12-PN2.14-README.txt)
and [checksums](../LPM-10A/Firmware%20File/experimental/TONE-OVERLOAD-SHA256SUMS.txt).
RX and TX files are for different devices. No release has been published or
device flashed by this work.

## Exact change and why broader rejection was discarded

The extra check runs only after full-window fitting fails and the existing
global detector has found at least two exact code spans. If all newest sixteen
raw 12-bit ADC values equal 4095, it publishes the existing uncertainty grade.
Otherwise it rejoins the original selected-span estimator. Temporary sample
tags do not affect the check. Full-window fits, lower-zero tails, other flat
tails, existing uncertainty, acquisition and normal release retain PN 1.11
behavior.

The reproducer consists of 32 B6 samples with LOW=1000 and HIGH=4000, followed
by sixteen 4095 readings. PN 1.11 reports the old amplitude 3000 and a 30 ms
quiet interval. PN 1.12 reports uncertainty. Actual TIM5 raw-input replay,
foreground analysis and the speaker scheduler reproduce this change.

This deliberately does not silence every flat tail. The
[independent challenge](DIGITAL-FLAT-TAIL-CHALLENGE-2026-09-20.md) found that
general flat-tail rejection erased 233 of 516 previously detected brief-contact
streams. A zero tail can also be a normal signal-off baseline. The selected
upper-only policy preserves every publication in those brief-contact streams.
The rejected broad-silence prototype remains an unregistered experiment; it
is not part of this image.

## Implementation and verification

The patch changes three slots totaling 42 bytes in the exact PN 1.11 parent:
the fallback branch and two previously unreachable NOP tails. Their original
return instructions remain intact. A complete parent SHA guard and exact
callsite/padding checks run before any mutation. Assembly is size-checked
before applying the edits. No extra persistent RAM, stack, interrupt masking,
gain setting, drive level, ADC clock, bootloader or license-record change.

- **55 groups passed in 63.251 seconds:** 43 complete-profile integration
  groups, six upper-rail groups and six profile-selection groups. Integration
  runs Digital, Analog, mains, keys, ADC, watchdog, overlap and interruption
  contracts against PN 1.12 bytes.
- The helper interruption test was then extended to both the all-rail and
  non-rail branches. That test and the actual raw-input/audio test passed again
  in **3.644 seconds**. These two are included in the 55, not additional unique
  groups. The test delivers 3,217 actual TIM5 IRQ calls at each selected first
  and last instruction visit, allowing the next window to complete.
- The focused low-level suite checks 7,200 fragment/tail vectors, 896 controls,
  every tag nibble, all sixteen non-rail exception positions, existing
  uncertainty and lower-zero behavior. Observed maximum stack stays 184 bytes;
  Analog DFT checks confirm the reused padding is not executed by that path.
- Profile-selection tests reject incompatible/custom unnamed builds before
  loading firmware. The integration audit rebuilt default and PN 1.4–1.11
  profiles and found them byte-identical to their preserved artifacts.
- **Five independent oracle groups passed in 23.527 seconds**, executing
  18,149 windows against the saved, SHA-pinned PN 1.12 binary and confirming
  an identical full source rebuild. Of those windows, 177 upper-rail cases
  change to uncertainty, 145 already-uncertain results remain uncertain, and
  all 8,064 brief-contact publications retain their previous behavior. No
  accepted window becomes silent. Known noise acceptance and two very-weak
  clean misses remain explicitly tested.

There are **60 unique groups** across the 55-group and five-group runs. The
two repeated integration groups are not added again. The
[verification record](experiments/results/pn112-verification-2026-09-20.json)
retains commands, results, environment and source hashes, with the timing of
the helper-test expansion stated explicitly. The independent
[oracle output](experiments/results/pn112-overload-oracle-2026-09-20.log) is also
retained. The 18,149-window corpus overlaps earlier studies; it is not presented
as entirely new input data.

The separate mathematical challenge covers 101,522 windows, including 10,000
structured clipping contexts. It changes 306 normal-strength results to
uncertainty and loses no accepted window in that corpus. Those are model
decisions, not 101,522 physical measurements or unique ARM tests. Its 693 ARM
comparisons validate the old PN 1.11 baseline used by that model.

Reproduce from `LPM-10A/Firmware File/rx-sdk`:

```text
python build.py --overload --write
python -m unittest test_overload_integration test_rx_digital_upper_rail test_overload_profile -q
python test_rx_overload_oracle.py
```

The new firmware's [implementation](../LPM-10A/Firmware%20File/rx-sdk/digital_upper_rail.py)
and [integration tests](../LPM-10A/Firmware%20File/rx-sdk/test_overload_integration.py)
make the scope reviewable. `--tracking` still builds the exact PN 1.11 file;
`--overload` is a separate fixed profile. The TX file is unchanged.

## Remaining evidence and device check

This is a correction to one misleading-strength case, not proof of maximum
range or bundle selectivity. Partial clipping, clipping below the ADC rail,
same-code coupling, inherited synthetic noise acceptance and very weak-signal
misses remain. ADC saturation cannot be forced or measured on the user's
hardware from this workspace.

On known disconnected cables, test both modes, sweep past a target briefly,
compare a neighboring cable, move away, and exercise mode/pause/resume/RIGHT.
Record unexpected silence, prolonged indications or resets. Use the
[comparison protocol](TONE-PROBE-COMPARISON-PROTOCOL.md) for a blinded local
selection test. The owner has no Fluke comparator; the comparative-performance
goal remains unverified.
