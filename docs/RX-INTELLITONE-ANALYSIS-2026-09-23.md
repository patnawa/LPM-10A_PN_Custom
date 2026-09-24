# RX probe against Fluke IntelliTone: why the fixes got worse, and what can be done

Date: 2026-09-23. Receiver builds PN1.24 (earlier release), PN1.27, PN1.28 and PN1.29. Transmitter
TX PN2.27A, unchanged. Written while PN1.29 was a candidate. Status: PN1.29 was the owner-tested
release [rx-v1.29](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/rx-v1.29) (owner's
device confirmation, 2026-09-23: "1.29 test pass work perfect") and is superseded by PN1.30
([rx-v1.30](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/rx-v1.30), built from the exact PN1.29 image:
[RX-CLEAN-STRENGTH-PN1.30-2026-09-24.md](RX-CLEAN-STRENGTH-PN1.30-2026-09-24.md)); PN1.27 (rx-v1.27) and
PN1.28 are superseded too. The owner's report did not measure pickup distance, loudness or selectivity; the
scorecard and trace figures below are emulator results. PN1.29's files are in
`LPM-10A/Firmware File/archive/` with PN1.27's.

## สรุป (ภาษาไทย)

- **IntelliTone ทำอะไรจริง** (จากคู่มือ Fluke): หัวโพรบไม่มีปุ่มปรับความไว มีแค่สวิตช์ Locate/Isolate และ
  ไฟ LED 8 ดวงแสดงความแรงแบบค่าตายตัว (absolute) ในโหมด Isolate จะไวน้อยลงแต่แยกละเอียดขึ้นช่วงสัญญาณแรง
  ปกติต่างกับคู่ข้างเคียงแค่ "สองสามขีด" และไม่มีอะไรขึ้นกับว่าแตะคู่ไหนมาก่อน
- **Fluke เองบอกว่า** สัญญาณดิจิทัลของ IntelliTone "รั่วข้ามคู่ในสายเดียวกันมาก โดยเฉพาะสายโทรศัพท์ Cat 3"
  และ "สาย PBX บางสายมีสัญญาณย่านเดียวกัน" สำหรับแยกคู่สายโทรศัพท์ Fluke ให้ใช้ SmartTone แบบอนาล็อก
  แล้ว **ช็อตคู่สายที่ปลายทาง ตัวส่งจะเปลี่ยนจังหวะเสียง** — ความแม่นยำนี้มาจากตัวส่ง ไม่ใช่หัวโพรบ
- **เทสต์ใหม่ `cabinet_scorecard.py`** จำลองการแตะคู่สายในตู้ด้วยเฟิร์มแวร์จริง: คู่ที่ต่อ TX กับคู่ข้างเคียงที่อ่อนกว่า
  3/6/10 dB แตะสลับกัน 7 ครั้ง ที่ความแรงแตะ 3 ระดับ และ 8 ตำแหน่งปุ่ม ผล (แยกถูกจาก 24 กรณี Digital/Analog):
  PN1.24 = 0/6, PN1.27 = 4/9, PN1.28 = 4/8, **PN1.29 = 14/19** — ตัวเลข Analog รวม 6 กรณีต่อรุ่นที่ปุ่ม
  13% และ 6% ซึ่ง Analog ถูกปิดต่ำกว่าราว 14% ของปุ่ม ทุกคู่ (รวมคู่ที่ต่อ TX) เงียบ สกอร์จึงนับเป็นผ่าน
  กรณี Analog ที่ได้ยินและแยกถูก: PN1.24 0, PN1.27 3, PN1.28 2, PN1.29 13 จาก 18
- **สาเหตุที่ยิ่งแก้ยิ่งแย่ 3 ข้อ**: (1) จังหวะเสียงเดิม (PN1.24-1.28) แยกความต่างได้แค่ ~15 dB ช่วงบน
  แต่แรงแตะเปลี่ยนได้ ~20 dB ตำแหน่งปุ่มที่ใช้ได้จึงเลื่อนไปทุกครั้งที่แตะ (2) ภาคขยายอิ่มตัวก่อน ADC
  ค่าที่อ่านตอนแตะครั้งแรกจึงต่ำกว่าจริง จนกว่า AGC จะลดเกนทัน (เดิม PN1.24 ขั้นละ 1 วินาที; PN1.29 ลดได้ทุก
  0.5 วินาที) ทำให้คู่เดียวกันดังไม่เท่ากันแม้ใน PN1.27 (3) PN1.26-1.28 จำค่า peak
  เสียงจึงขึ้นกับว่าแตะคู่ไหนมาก่อน — ทุกครั้งที่แก้ เราเช็กแค่อาการล่าสุด ไม่ได้เช็กทุกอาการพร้อมกัน
- **PN1.29 = รีลีส rx-v1.29** เจ้าของทดสอบบนเครื่องจริงผ่านแล้ว 2026-09-23 ("1.29 test pass work perfect")
  แทนที่ PN1.27 (rx-v1.27) และ PN1.28 ทำตามหลัก IntelliTone: ความแรงเป็น 10 ขั้นคงที่ ห่างกันขั้นละ 3 dB
  (จังหวะ Digital ต่างกัน 15% ต่อขั้น), ไม่จำ peak, กรองค่าให้ขั้นนิ่ง, AGC ลดเกนเร็วขึ้น, เกนเต็มทุกตำแหน่งปุ่ม
  (ได้ยินตั้งแต่ปุ่มต่ำ), NCV และเสียงดังคงเดิม — ผลจากเครื่องจริงเป็นรายงานของเจ้าของ ไม่ได้วัดระยะ ความดัง
  หรือการแยกคู่เป็นตัวเลข ตัวเลขในเอกสารนี้มาจากอีมูเลเตอร์
- **วิธีใช้แบบ IntelliTone**: ปุ่มสุด = Locate (หามัด/ตู้ ใกล้แล้วเร็วขึ้นเป็นขั้น ถึงตู้แล้วทุกคู่เร็วสุด = ปกติ)
  หมุนลงเหลือราว 1/5 ของรอบ = Isolate (แตะคู่ละ ~2 วินาที คู่ที่ต่อ TX เร็วที่สุด คู่อื่นช้ากว่าอย่างน้อยหนึ่งขั้น)
  ใน scorecard ของ PN1.29 (อีมูเลเตอร์) Analog แยกถูก 13 จาก 18 กรณีที่ได้ยิน Digital 10 ที่ตำแหน่งปุ่มเดียวกัน
  และค่าความแรง Analog นิ่งถึง 0.06 dB — ตรงกับที่ Fluke แนะนำโหมดอนาล็อกสำหรับแยกคู่
- **ข้อจำกัดที่เฟิร์มแวร์แก้ไม่ได้**: ถ้าคู่ข้างเคียงได้สัญญาณแรงเกือบเท่าคู่ที่ต่อ (พาหะ 454 kHz รั่วผ่านสาย
  และผ่านวงจร PBX) ไม่มีวิธีแยกด้วยความแรง — แบบเดียวกับที่ Fluke ต้องใช้วิธีช็อตคู่สาย

## What Fluke documents

Sources: IntelliTone Pro 200 LAN Toner and Probe Users Manual (Rev. 2, 2017) and the Fluke Networks
application note "Cable Toning Techniques Using IntelliTone Pro Toners and Probes" (2006).

| Item | Fluke |
|---|---|
| Probe controls | rotary switch: Locate, Isolate, SmartTone, Cable Map; a volume control; **no sensitivity knob** |
| Display | 8 LEDs, "light up from 1 to 8 as the signal strength increases" in both Locate and Isolate |
| Typical readings | "4-6 in locate mode with the probe tip inserted into the jack"; "7-8 on the toned cable"; neighbours lower |
| Isolate | "help eliminate bleed and provide more granularity on the stronger LEDs ... a couple of LED levels of difference in strength" |
| Pairs in a cable | "The IntelliTone digital signal is subject to significant bleed-over between pairs in a cable. This is especially true for Cat 3 cabling. Because of this, IntelliTone's analog mode is recommended for isolating individual pairs." |
| SmartTone | the toner changes cadence "when a pair is shorted at the far end": positive pair identification, for dry pairs only |
| PBX | "Some PBX lines generate signals in the operating frequency of IntelliTone ... it is recommended to use IntelliTone's analog mode" |

The precision the owner remembers comes from an absolute, discrete display that never depends on
what was probed before, from a less sensitive Isolate setting, and, for telephone pairs, from a
transmitter feature (short-to-change-cadence), not from a smarter probe algorithm.

## The owner's reports, one loop

| Build | Report (2026-09-23) | Mechanism |
|---|---|---|
| PN1.24 | PBX cabinet: every pair loud, cannot tell which | curve clamps above full-gain saturation |
| PN1.24/1.25 | knob past half before anything sounds | low knob = low hardware gain |
| PN1.26 | always strong from 10 %, knob no effect | lone cable ranked against its own peak |
| PN1.27 | full knob: every pair sounds the same | curve clamp at K = 1 |
| PN1.28 | detects, but not accurately (worse than PN1.27) | peak memory: order-dependent rhythm |

`rx-sdk/cabinet_scorecard.py` runs the real firmware (TIM1/TIM5 handlers, sampler, automatic gain,
analysers, publisher, speaker) while a modeled probe visits a bundle: the toned pair T and
neighbours 3, 6 and 10 dB weaker, in the order N3 N6 T N10 N3 T N6, 2 s each, no gap, at three
contact strengths (link 3 000 / 10 000 / 30 000, which read +4 / +15 / +23 dB over the full
gain's saturation in the model) and eight knob positions. A visit is scored on the rhythm the
firmware publishes over its last 1.2 s; the toned pair is identified when every neighbour visit's
pulse period is at least 12 % longer than every toned-pair visit's (or the neighbour is silent).

| Build | Digital identified (of 24) | Analog identified (of 24) |
|---|---|---|
| PN1.24 | 0 | 6 |
| PN1.27 | 4 | 9 |
| PN1.28 | 4 | 8 |
| **PN1.29** | **14** | **19** |

The Analog counts include 6 cases per build at 13 % and 6 % of the knob. Analog is gated off below
about 14 % of the knob (PN1.24's gate, knob reading >= 580 of 4 095), so every pair, the toned pair
too, is silent there, and the scorecard counts those as passes. Audible Analog cases identified:
PN1.24 0, PN1.27 3, PN1.28 2, PN1.29 13 of 18.

In Digital, PN1.27 and PN1.28 identify only at one narrow knob position that moves with contact
strength (3 000: 75 %, 10 000: 38-50 %, 30 000: 25 %); in Analog they identify only 10 000 at 50 %
and 30 000 at 19-25 % (PN1.28: 19 %), and no audible case at 3 000. PN1.29 identifies all three
contact strengths in both modes at 19 % of the knob, and in Analog anywhere from 19 % to 38 %. Its
remaining failures are the knob outside the Isolate range for that strength (all pairs at the top
level, or all at the slowest), the first touch at the bundle while the gain settles, and a
neighbour exactly 3 dB weaker sitting on a level boundary.

## Why each fix made it worse

1. **Display range against contact strength.** The PN1.24-PN1.28 rhythm curve (continuous,
   110 -> 20 ms) resolved about 15 dB at its fast end (PN1.29: ten levels 3 dB apart, about
   24 dB). Contact strength varies over about 20 dB with pressure. A knob law (PN1.25, PN1.27)
   can place that window, but the right place moves with every touch; outside it the toned pair
   and its neighbours are all at the fastest rhythm or all slow.
2. **Saturation before the rail.** The front end limits at about 2 400 counts p-p, before the ADC
   rail, so a too-high gain reads the saturation of that gain, a lower bound that is not flagged as
   clipped (trace: 133 754 at level 2 for a pair whose true value is 473 284). The PN1.24 automatic
   gain steps once per second, so a 1-2 s touch is often never measured correctly. This makes even
   PN1.27 history-dependent: the same neighbour read 0.34 on its first visit and 0.56 on its second.
3. **Memory.** PN1.26-PN1.28 keep a peak (the strongest strength heard recently, -2 dB/s). The mute
   below the middle (PN1.26/1.27) and the sliding curve (PN1.28) compare each pair with that peak,
   so the answer depends on what was touched before and for how long. In the PN1.28 trace a
   neighbour 3 dB weaker played as fast as the toned pair because the peak had decayed 3 dB while
   the probe rested on another pair.

Each change was checked against the newest report only. The scorecard checks every report's
scenario at once and is part of the PN1.29 tests.

## PN1.29

Built by `rx-sdk/level_display.py` from the exact PN1.24 image, so the PN1.25-1.28 mechanisms are
gone: PN1.25's mute floor, PN1.26-1.28's peak memory, peak-relative mute and Compare gain ceiling,
and PN1.28's sliding curve. PN1.27's knob law and the louder beep are applied again on top of
PN1.24:

- **Ten absolute levels, 3 dB apart**, of strength x K(knob) (PN1.27's knob law). Each Digital
  pulse period is 15 % longer than the next level's (Analog, with 12 ms pulses, 17-23 %); Digital
  quiet interval 20, 27, 36, 46, 57, 71, 86, 103, 123, 146 ms. The same strength always gives the
  same level; nothing is muted.
- **Stable levels.** The Digital strength estimate is exactly linear (score = 21.44 x amplitude on
  clean windows) but single windows read 3-6 dB low; the Analog estimate is stable to 0.06 dB. A
  stronger window shows at once, a weaker one moves the shown strength an eighth of the way (a real
  3 dB drop in about 0.3 s), and a level changes only 0.5 dB past its boundary.
- **Full gain at every knob position** (heard low on the knob, as PN1.26/1.27), and a **faster
  attack**: after a gain step down the next 500 ms callback may decide again (PN1.24 held one); a
  step up keeps the one-callback hold. Saturation 7 -> 2 -> 1 -> 0 at 0.5 / 1.0 / 1.5 s instead of
  0.5 / 1.5 / 2.5 s, with no audio gap over 150 ms.
- Kept: NCV knob gain (full from a quarter up), louder beep, mode pitches and chirps, detection.

Knob: fully up is **Locate** (weak signals graded, strong ones all at the top level, like
IntelliTone's 7-8 LEDs on the cable); about a fifth of the travel is **Isolate** for comparing
pairs by touch. In PN1.29's scorecard, Analog identified 13 of the 18 audible cases and Digital 10
at the same knob positions, and the Analog estimate is stable to 0.06 dB (emulator). This matches
Fluke's advice to use analog for pairs.

## What firmware cannot do

- Separate two pairs that pick up nearly the same signal. The 454 kHz carrier couples between
  pairs and through PBX line circuits; if a neighbour is within about 2 dB of the toned pair, no
  display can rank them reliably (Fluke uses a far-end short for this).
- A SmartTone-style short detector needs the transmitter to sense the pair it is toning. Which RJ45
  conductors carry the tone, and whether the wire-map circuit can measure them during SCAN, has not
  been traced on the board; on live PBX lines the exchange's battery would also prevent it.
- The contact strengths, coupling and noise here are modeled. The scorecard shows which design
  can work and why the old ones cannot; only a device test shows the real separation. The owner's
  PN1.29 pass (2026-09-23, "1.29 test pass work perfect") is a report, not a measurement: it did
  not measure separation, pickup distance or loudness.

## Next steps

The owner test of PN1.29 is done (passed 2026-09-23, released as rx-v1.29). Remaining:

1. If pairs remain too close: trace the TX tone path (which pins, balanced or not) to decide whether
   a SmartTone-style short detector or a lower-radiation drive is possible.
2. Optional: pitch steps in addition to rhythm (finer audible steps over a wider range).
