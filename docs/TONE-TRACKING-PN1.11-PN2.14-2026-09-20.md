# RX PN 1.11 / TX PN 2.14 — Digital and Analog tracking

**Follow-up:** [RX PN 1.12](TONE-OVERLOAD-PN1.12-PN2.14-2026-09-20.md) adds
upper-rail uncertainty for an old-code fallback. This report and its PN 1.11
artifact remain preserved as the predecessor's evidence.

**สถานะ: สร้างเฟิร์มแวร์และทดสอบ CPU แล้ว ยังรอผลจากเครื่องจริง**
รุ่นนี้ปรับ RX จากข้อจำกัดที่พบในการตรวจเชิงลึก และใช้ TX PN 2.14 ที่มีเพียง
Digital 454 kHz / Analog 825 Hz พร้อมแก้ข้อผิดพลาดปุ่มขวา
ผู้ใช้ยืนยันว่าไม่มี Fluke สำหรับเปรียบเทียบ จึงยังไม่อ้างว่าเหนือกว่า Fluke
หรือดีที่สุดในโลก

## ผลที่เปลี่ยนไป

| จุดปรับ | รุ่นก่อนหน้า | RX PN 1.11 |
|---|---|---|
| Digital / อัปเดตข้อมูล | รับใหม่ครบ 48 samples ทุกประมาณ 240 ms | หลังชุดแรก เก็บ 32 samples เดิมและรับใหม่ 16 samples อัปเดตประมาณทุก 80 ms |
| Digital / noise กระชาก | threshold ทั้งหน้าต่างถูกดันจนตรวจรหัสไม่ผ่าน | เพิ่ม threshold แบบช่วงสั้น และยังตรวจความสอดคล้องของรหัสครบ 48 samples |
| Digital / วัดความแรง | median จากข้อมูลถึง 48 samples | ใช้ 16 samples ล่าสุดที่ผ่านการตรวจรหัส; fallback ใช้ช่วงรหัสสมบูรณ์ล่าสุดซึ่งอาจเก่ากว่า |
| Digital / ตามความแรงที่เปลี่ยน | แบบจำลองเดิมพบประมาณ 390–470 ms ในกรณีที่ตรวจ | แบบจำลองหลังจับรหัสแล้วพบ 45–125 ms ในชุดการเปลี่ยนความแรงที่ระบุด้านล่าง |
| Analog / ความละเอียดเสียง | 3 ระดับ บี๊บยาว 50/100/200 ms | บี๊บปกติ 30 ms กับช่วงเงียบที่ไล่ระดับ 20–160 ms |
| Analog / ตามสัญญาณแรงขึ้น | กรณีจำลองต้องรอ 378 ms หลังผลใหม่ | กรณีเดียวกันลดเหลือ 39 ms หลังผลใหม่ |
| Analog / คำนวณ | ตัวอย่างใช้ 230,116–237,131 คำสั่ง | 59,879–60,734 คำสั่ง ลดประมาณ 74%; ผล DFT เท่าเดิมทุกบิต |
| Analog / สัญญาณอิ่มตัว | ยังให้เสียงแรงปกติ | หากผ่านเกณฑ์รับและมีค่า ADC ถึงขอบบนอย่างน้อย 8/64 ค่า ให้เสียงไม่เหมาะสำหรับเทียบความแรง |

**ตัวเลขเหล่านี้มาจาก ADC และเวลา interrupt จำลองที่รันโค้ด ARM จริง**
ไม่ใช่ผลวัดระยะ ความแม่นยำในการเลือกสาย หรือเวลาเสียงบนเครื่องจริง
Digital ตอนเริ่มต้นหรือหลังสลับโหมด/ปิดแล้วเปิด gate ยังต้องรับใหม่ครบประมาณ
240 ms ไม่ได้เริ่มจับรหัสใน 80 ms ทุกกรณี

## Files and exact identity

| Device | File | Bytes | SHA-256 |
|---|---|---:|---|
| RX probe | [APP_LPM-10RX_PN1.11-tracking.bin](../LPM-10A/Firmware%20File/experimental/APP_LPM-10RX_PN1.11-tracking.bin) | 26,152 | `3e39ae56832cf92881ffdc46564e293278d6c3f1b55a9832b7a9a8350f031828` |
| TX tester | [LPM-10A-TX_PN2.14-tone-recovery.bin](../LPM-10A/Firmware%20File/experimental/LPM-10A-TX_PN2.14-tone-recovery.bin) | 393,216 | `a7402de6f18e39df55bbe53f5641efd5135f0de4d81f9407515cf9d8710c5527` |

[Device notes](../LPM-10A/Firmware%20File/experimental/TONE-TRACKING-PN1.11-PN2.14-README.txt)
and [checksums](../LPM-10A/Firmware%20File/experimental/TONE-TRACKING-SHA256SUMS.txt).
The TX file is the same verified PN 2.14 from the preceding turn; no additional
TX waveform or electrical-drive change accompanies this RX update.

RX uses the exact PN 1.9 parent, preserving the previous battery, ADC, watchdog,
mode/gate ownership and Digital feedback fixes. It omits the failed Sync32
experiment. The existing Digital/Analog waveform remains compatible with
TX PN 2.12/2.13; PN 2.14 additionally removes the unused menu modes and repairs
the RIGHT-key carrier-cache defect. Prior artifacts remain available unchanged.

The RX image retains its original size and vector table. No bootloader, UID
license record, version-page operation, sample timer, gain GPIO or drive-level
setting changes. New routines reuse audited code space and stack; no new
persistent RAM is allocated.

## Digital evidence and tradeoffs

The hybrid detector first tries robust thresholds in six eight-sample blocks,
with contrast of at least 9 ADC counts in five blocks. A candidate must still
fit the complete 48-sample B6 observation within four total bit errors and two
errors per 16-sample region. When this does not fit, the original global
threshold and exact-code fallback remain available. Raw sample tags are cleared
before fallback. See the [algorithm and reproducible model report](DIGITAL-TRACKING-CANDIDATE-2026-09-20.md).

- Prior audit corpus: accepted windows increase from **1,517/2,490 to 2,482/2,490**,
  with no previous acceptance lost in that corpus.
- Exhaustive pairs of positive-rail corruptions at every position and code
  phase: **8,880/9,024** recover with the correct amplitude, versus zero before.
  The remaining 144 difficult cases are still rejected.
- All 2,304 clean fresh/steady phase-and-clock cases remain accepted.
- In 49,152 synthetic noise windows, both versions accept the same one false
  case inherited from the exact-span fallback. This is not a field false-alarm
  rate. Overlapping windows increase decisions per unit time and correlate them.
- Steady-state transitions 100→300, 300→100, 60→3000 and 3000→60 ADC counts,
  at all eight phases and 16 update offsets, settle in **45.028–125.078 ms**
  on the reduced-sample model grid. Signal removal rejects in **95.059–205.128 ms**.
  These exclude the acquisition aperture, processing and audible scheduling.

The recent median uses six LOW and ten HIGH samples, trading some averaging
for faster comparison. It is not immune to larger structured interference.
The exact fallback can retain an older qualified span; its indication is not
an unconditional measurement of the newest 80 ms. Same-code coupling into a
neighboring cable remains indistinguishable from a stronger target observation.

## Analog implementation and measured software behavior

Both the original 31-bin DFT decision and the noise divisor **12** are retained.
No new analog signal is accepted merely to make the device appear sensitive.
The signed Q12 coefficient products remain exact; software-double magnitude
is replaced by exact 64-bit squares and a bounded integer square root. The
integer equivalence and input bounds are documented in
[analog_integer.py](../LPM-10A/Firmware%20File/rx-sdk/analog_integer.py).
This also preserves the DFT values used by mains detection.

An accepted margin maps to `40 * (target - noise_metric - 10)` through the
existing interpolated cadence curve. The established 3 ms cadence deadband
remains. Normal tones last 30 ms. A stronger accepted result can shorten a
pending quiet interval; it cannot truncate an active tone or key confirmation.
Rejected windows clear the repeat grade. With no fresh accepted result, Analog
stops starting repeats after 100 nominal ms; an existing tone completes.

Eight or more upper-rail ADC readings in an otherwise accepted 64-sample
window select 100 ms pulses with 160 ms quiet intervals. This means the reading
is unsuitable for fine strength comparison, not "no cable." A normal zero
LOW level is not classified as overload by itself. Internal front-end clipping
below the ADC rail is still unobserved.

The complete, pinned PN 1.11 artifact produces:

| Input | PN 1.9 instructions / stack | PN 1.11 instructions / stack |
|---|---:|---:|
| DC | 230,116 / 408 bytes | 59,879 / 80 bytes |
| Nominal 825 Hz sine, amplitude 300 | 237,131 / 408 bytes | 60,647 / 80 bytes |
| Clipped nominal 825 Hz sine, amplitude 8,000 | 236,513 / 408 bytes | 60,734 / 80 bytes |

These are retired-instruction counts and maximum observed stack depth, not
hardware CPU cycles. ADC values are clamped to 0–4095.

For square-envelope contrasts 25, 50, …, 300, all 12 previous results select
the same 200 ms tone. PN 1.11 instead gives 12 distinct quiet intervals from
156 down to 86 ms, with 30 ms tones. In the weak-sine-to-strong-sine fixture,
new strong results begin at tick 21; the first corresponding tone begins at
tick 399 previously and tick 60 now: **378 versus 39 nominal ms**. Analysis
arrivals are deliberately modeled every 21 ms; this does not measure a moving
physical probe or actual main-loop throughput.

## Verification and reproduction

The full RX discovery run passed **256 groups in 318.978 seconds**. Two added
fragment/bounds groups subsequently passed in 8.606 seconds, bringing the
initial checked suite to **258 groups**. They exercise 6,768 additional
fragmented-code windows and explicitly retain the older-exact-span tradeoff.
The delivered binary matches an independent profile rebuild byte-for-byte.

The integrated profile passed 41 test groups including actual Digital windows,
real TIM5 acquisition, Analog DFT/feedback, mode changes, ADC completion,
watchdog/keys and interrupt interleavings. Separate component validation includes
14,714 Digital ARM/model comparisons, 70 ADC vectors × 31 DFT bins, 13,034 signed
component boundary pairs, and 34,751 square-root boundary values. The exact
Analog integers agree with the corrected PN 1.9 implementation.

The Analog race suite covers 967 interrupt placements and 384 mains-state
comparisons. Full-grid acquisition executes every TIM5 interrupt: 9,620 ticks
for the fresh first window, then 3,200 ticks per overlapping update. Copying
the retained 32 samples finishes before publishing index 32 and ACTIVE last.
Mode/gate invalidation resets the index and requires a fresh complete window.

In `LPM-10A/Firmware File/rx-sdk`:

```text
python build.py --tracking --write
python -m unittest discover -p "test_*.py" -q
```

From the repository root:

```text
python docs/experiments/digital_acquisition_candidate.py
python docs/experiments/tracking_profile_audit.py
```

The second audit pins the delivered artifact by SHA-256 and reproduces the
complete-profile Analog table and cadence fixture above. Existing TX PN 2.14
verification remains in its [report](TONE-RECOVERY-PN2.14-2026-09-20.md).

### Follow-up on confirmation and evidence scope

The [Digital confidence study](DIGITAL-CONFIDENCE-FOLLOWUP-2026-09-20.md)
checks 2,364 windows against the pinned ARM detector, including 2,304 existing
clean fixtures and 60 selected counterexamples. It rejects tighter
periodicity gates because they lose continuing signals during amplitude
changes. A separate held-out clean corpus exposes two existing very-weak
amplitude-13 misses. Exact-flat-tail rejection is a model-only future
prototype; it does not remove the known synthetic noise acceptance and is
not implemented in PN 1.11.

The [Analog confirmation study](ANALOG-CONFIDENCE-TRADEOFF-2026-09-20.md)
finds that requiring two consecutive detections reduces synthetic noise
acceptance, but misses all 16 tested phases of a weak one-frame visit. Two
additional tests run the complete, pinned PN 1.11 code and verify bounded
release for short real-tone fixtures and an isolated false indication.
That proposed policy is not included in this firmware.

The [continuous Digital audit](TONE-TRACKING-CONTINUOUS-AUDIT-2026-09-20.md)
adds four tests: 160 continuous windows, 689 instruction-boundary interruption
schedules, 18 DSP-stage preemptions and 10 mode/gate invalidations. No ownership
failure was found in those schedules. The combined follow-up run passed
**eight groups in 40.300 seconds**: six new groups plus the two existing
fragment groups. Its [output](experiments/results/pn111-followup-2026-09-20.log)
and [environment/source hashes](experiments/results/pn111-followup-2026-09-20.json)
are retained. All follow-ups preserve the same firmware binary and hash.

The [evidence review](TONE-GOAL-EVIDENCE-2026-09-20.md) records which claims
are supported and which remain unmeasured. The 256-group discovery run includes
the 41 integrated-profile groups and historical/component profiles; these
counts must not be added together or described as 256 tests solely of the
delivered binary.

## What still requires device evidence

The original [deep audit](TONE-PERFORMANCE-AUDIT-2026-09-20.md) remains the record
of the pre-improvement limits. This candidate addresses several of those limits;
it does not prove physical range, selectivity, gain calibration, complete
overload detection, audible preference, or comparative superiority.

The next local check needs no oscilloscope: use known disconnected cables,
test both modes, move from close contact to a neighboring cable and then away,
exercise mode changes/pause/resume/RIGHT, and record sustained operation and
any silence or reset. The [comparison protocol](TONE-PROBE-COMPARISON-PROTOCOL.md)
provides a blinded local pilot and the separate head-to-head test. Real LPM
validation and a physical comparator are still missing; the overall superiority
objective remains unverified.
