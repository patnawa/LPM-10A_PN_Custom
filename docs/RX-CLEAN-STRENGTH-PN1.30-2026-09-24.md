# RX PN1.30: a steady Digital strength, gain at every window, no walk-down at a touch

Date: 2026-09-24. Parent: the owner-tested RX PN1.29 (rx-v1.29). Transmitter TX PN2.33, unchanged.
Status: **released as [rx-v1.30](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/rx-v1.30)** after the owner's device test on 2026-09-24
("1.30 test pass flicker fixed"); PN1.29 (rx-v1.29) is superseded and its files are in
`LPM-10A/Firmware File/archive/`. Install file: `LPM-10A/Firmware File/APP_LPM-10RX_PN1.30-clean-strength-update.bin`
(notes and checklist: `RX-PN1.30-README.txt` beside it). Everything measured below is the real
firmware executing on a CPU model with a modeled ADC, link and interrupt arrival; none of it is a
measurement of real pickup, noise or loudness.

## สรุป (ภาษาไทย)

- **สถานะ**: ปล่อยเป็นรีลีส rx-v1.30 หลังเจ้าของทดสอบบนเครื่องผ่าน 2026-09-24 ("1.30 test pass flicker fixed")
  แทน PN1.29 (ไฟล์ PN1.29 ย้ายไป archive/)
- **โจทย์**: หาบั๊กและปรับปรุงตรรกะเกนสัญญาณกับความแม่นยำของ RX PN1.29 ด้วยการรันเฟิร์มแวร์จริงในอีมูเลเตอร์
  ใช้ลูปสองตัว: `cabinet_scorecard.py` (ตู้สาย: แยกคู่ถูกไหม) ที่มีอยู่แล้ว และ `steady_probe.py` ตัวใหม่
  (สัญญาณนิ่งหนึ่งเส้น: ค่าความแรงทุกหน้าต่างและขั้นที่แสดง)
- **บั๊ก 1 - ความแรง Digital ตกเป็นช่วง ๆ**: ตัวรับอ่าน ADC ช่วง 2 ms ท้ายของช่องเวลา 5 ms แต่ชิปของตัวส่งยาว
  5.05 ms ขอบสัญญาณจึงเลื่อนเข้าช่วงอ่านทุก ~0.55 วินาที ตัวอย่างที่ตามหลังขอบเป็นค่าผสม ตัวประมาณเดิม
  อ่านได้ 5/6, 2/3 หรือ 1/2 ของค่าจริง (-1.6/-3.5/-6 dB) ราว 200 ms; 23 % ของหน้าต่างต่ำกว่าจริง ผลที่หู:
  สัญญาณนิ่งที่แรงกว่าขั้นถัดไป 0.6-1.0 dB จังหวะกระโดดสองขั้นราววินาทีละครั้ง (RX-AUDIT ปี 2026-09-19
  ข้อ F2 เคยชี้ไว้ว่าจะ "กระตุกเป็นจังหวะช้า ๆ ทั้งที่โพรบนิ่ง")
- **บั๊ก 2 - เกนลงตัวช้าเมื่อแตะสายแรง**: เกนลดได้แค่ที่จังหวะ 500 ms (1.5 วินาทีถึงเกนต่ำสุด) ค่าที่อ่านระหว่างนั้น
  เป็นค่าอิ่มตัว (ขั้นต่ำ) และ **บั๊ก 3** ตัวกรองเดินตามค่าอิ่มตัวลงไป จังหวะจึงถอยก่อนแล้วค่อยขึ้น (8 -> 5 -> 7 -> 8)
- **PN1.30** (จาก PN1.29 ทุกไบต์ + 684 ไบต์ต่อท้าย): ตัวประมาณแบบชุดสามที่ไม่กินขอบ (2 x max - min - ต่ำ),
  เกนตัดสินใจทุกหน้าต่างที่แสดงแล้ว (Digital ~280 ms, Analog ~21 ms), หน้าต่างอิ่มตัวนับต่ำลง 1.2 dB และไม่ลดค่าที่แสดง,
  ค่าลดจริงเกิน 2.5 dB เดินครึ่งทาง ผลอีมูเลเตอร์: จังหวะเปลี่ยน 0 ครั้ง (เดิม 0.8-1.2/วินาที), เกนลงตัว 0.73 วินาที
  (เดิม 1.5; Analog 66 ms), ลด 6 dB เห็นใน 0.57 วินาที (เดิม 0.64 ด้วยความช่วยของ dip เอง; ตัวกรอง 1/8 บนค่านิ่ง 1.0),
  scorecard Digital 14/24 เท่า PN1.29 ทุกแถว, Analog 18/24 (เดิม 19; แถวเดียวที่ต่างคือคู่ข้างเคียงบนรอยต่อขั้น 0.02 dB)
  แต่ความต่างของคู่เดิมระหว่างการแตะ (สิ่งที่ลูปนี้วัดเป็นความแม่นได้) ลดจาก 0.043 เป็น 0.007 (Digital) และ 0.015 เป็น 0.001 (Analog)
- **ยังทำไม่ได้/ต้องการข้อมูล**: การล็อกเฟสของช่องเวลาให้ตรงชิป (แก้ที่ต้นเหตุของบั๊ก 1 ทั้งหมด) เป็นงานเขียน
  ตัวเก็บตัวอย่างใหม่; อัตราส่วนเกน 4-7 กับ 2 วัดขณะอิ่มตัว; สเกลคะแนน Digital กับ Analog ต่างกัน 2-2.5 dB
  ในโมเดล และเกต Analog ที่ 14 % ของปุ่มเป็นของโรงงาน

## The feedback loops

| Loop | What it runs | Signal it gives | Verdict on PN1.29 |
|---|---|---|---|
| `rx-sdk/cabinet_scorecard.py` (existing) | the firmware on a toned pair and neighbours -3/-6/-10 dB, 7 visits of 2 s, 3 contact strengths, 8 knobs | identified (of 24) per mode, per-pair spread across visits | Digital 14, Analog 19 |
| `rx-sdk/steady_probe.py` (new, 2026-09-24) | the firmware on one constant signal for 6 s; hooks the display's entry for every window's raw score | score min / median, windows below -0.5 dB, displayed-level changes per second, gain-step times | red: see finding 1 |
| `test_rx_clean_strength` (new) | the loops above as assertions, plus the estimator against its model and PN1.29 as negative control | 24 tests | |

Both loops are deterministic and run unattended (`steady_probe.py` in about 10 s per build and
amplitude; the scorecard in about 5 min per build).

## Findings

### 1. Digital strength dips as the chip edge drifts through the readings (confirmed)

The mode-0 sampler (`sampler_modes_0_1`, `0x080075F8`) reads channel 1 at sub-steps 6-10 of a
5 ms slot (3.0-5.0 ms) and keeps the trimmed mean of the five; the transmitter's chip is 5.05 ms
(TIM2 101 µs x 50), so the chip edge moves 47 µs later per slot and spends about 200 ms of every
~550 ms inside the readings. A sample that follows a 0->1 or 1->0 transition is then a mix of both
levels, quantised by the trimmed mean to 1/3 or 2/3 of the contrast, and the PN1.9-1.29 estimator
(median of the expected-high samples minus median of the expected-low samples over the 16 newest
samples) reads the contrast at 5/6, 2/3 or 1/2 of its value.

`steady_probe.py`, PN1.29, Digital, knob 100 %, 125 windows after the first second:

| amplitude | windows at 1/2 | at 2/3 | at 5/6 | at 1 | dip runs (windows of 40 ms) |
|---|---|---|---|---|---|
| 300 | 4 | 15 | 10 | 96 | 1 1 5 1 1 3 5 3 3 1 1 4 |
| 2000 | 3 | 11 | 13 | 96 | 1 1 3 1 1 4 4 3 4 1 1 3 |

PN1.29's display moves an eighth of the way toward a weaker window and changes level 0.5 dB past a
threshold, so a run of five dips at 2/3 pulls the stored strength down about 1.9 dB. The result
(`Flicker` test, red on PN1.29):

| strength above the level threshold | PN1.29 level changes per second | PN1.30 |
|---|---|---|
| +0.24 dB (amp 680) | 0, but at the level **below** the right one | 0, right level |
| +0.7 dB (amp 720) | 0.8 (5 <-> 6) | 0 |
| +1.0 dB (amp 745) | 0.8 (5 <-> 6) | 0 |
| +0.6 dB (amp 1000) | 1.2 (6 <-> 7) | 0 |

Analog is unaffected (its DFT window is not aligned to chips: score spread 0.06 dB).
`docs/RX-AUDIT.md` F2 predicted this in general terms on 2026-09-19 ("beeping that stutters in a
slow rhythm even with the probe held still") and proposed a sampler rewrite; PN1.11-1.29 fixed the
detection side (tolerant code match) but not the strength.

### 2. The gain settles once per 500 ms tick (confirmed in the trace)

The automatic gain (`gain_select_3bit` -> PN1.24 helper) is called only from
`agc_update_500ms` in `TIM1_UP_IRQHandler` (every 500 ms; the docs said "main context", it is
the TIM1 interrupt). PN1.29 removed the hold after a step down, so a strong pair steps
7 -> 2 -> 1 -> 0 at 0.5 / 1.0 / 1.5 s. The front end saturates at ~2 400 counts before the ADC
rail, so every window read at a too-high gain is a lower bound (trace: 51 444 raw at gains 7, 2
and 1 for a pair whose true value at gain 0 is 28 560 x 20).

### 3. The display walks down through the lower bounds (confirmed in the trace)

Knob 19 %, contact 30 000, PN1.29: stored strength 29 580 (level 8) at gain 1, then at gain 7 the
saturated window reads 3 215 and the 1/8 filter follows it: 25 207, 22 458, ... 13 087 (levels 7,
6, 5), at gain 2 down to 10 217, then 29 580 (level 7) at gain 1 and 35 700 (level 8) at gain 0.
Level 8 -> 5 -> 7 -> 8 over 2 s on one steady pair.

### 4. Documented, not changed

- The Digital score is 21.43 x contrast; on the owner's unit the saturated contrast was ~1 590
  at 2 400 p-p (`RX-SENSITIVITY-2026-09-21.md`), while the model's clean square wave gives
  contrast = p-p. The model therefore reads Digital about 3.5 dB high against the same p-p, and
  Digital about 2.1-2.5 dB above Analog for the same modeled p-p (Analog ~16.9 per count of p-p).
  The level thresholds were set from the measured Digital saturation (40 000). Which physical
  p-p lands on which level in each mode can only be settled with captures.
- The gain-step multipliers for codes 4-7 (1.07-1.11) were measured while saturated; the ratio
  used at the 7 -> 2 step (2.6) was measured against a saturated code 7 and may be as large as
  2 400 / 780 = 3.1 (a 1.5 dB discontinuity at most). A weak-signal capture of all eight codes is
  the data need (`RX-SENSITIVITY-2026-09-21.md`).
- Analog is gated off below knob reading 580 (14 % of travel; stock) while Digital works from
  reading 2. The scorecard's Analog 13 % / 6 % rows are silent and count as passes.
- The root-cause fix for finding 1 (a sampler whose slot follows the transmitter's chip, F2 in
  `RX-AUDIT.md`) would also remove the mixed samples from the detector; it is a rewrite of the
  TIM5 sampler path and is left for a later candidate.

## Hypotheses, ranked before the fixes

1. The dips come from the edge drifting through the last-2-ms readings: predicted that an
   estimator built from samples whose readings hold no edge reads the true contrast at every
   edge fraction, and that the flicker disappears. Confirmed (Estimator and Flicker tests).
2. The settle is paced by the 500 ms tick, not by acquisition: predicted that letting the same
   guarded gain routine decide at every completed window brings 7 -> 2 -> 1 -> 0 to about
   3 x 240 ms in Digital and 3 x 21 ms in Analog with no dropout. Confirmed (Attack, Settle).
3. The walk-down comes from following saturated windows: predicted that treating a window taken
   at p-p >= 1 900 above the lowest gain as a lower bound makes the display monotonic at a
   touch and leaves everything else unchanged. Confirmed (Settle), with one refinement: taken at
   face value a saturated reading can exceed the unsaturated truth at the next gain when the
   gain-step table is off, so it is counted 1.2 dB lower.
4. The first estimator (three medians over the whole window) would be enough. Refuted twice: when
   the edge fraction is above 1/2 the detector aligns each sample to the previous chip and the
   "highs after a high" are the mixed ones (the formula went negative and published 'uncertain',
   which PN1.29 shows as the top level); and on a window spanning two pairs the two high groups
   sample different pairs and the sum overshoots, which the hysteresis then keeps (a one-level
   difference between two visits of the same pair in the cabinet loop). The triplet estimator
   below answers both.

## PN1.30

Built by `rx-sdk/clean_strength.py` from the exact PN1.29 image (SHA-256 pinned; every replaced
site checked byte for byte); 684 bytes appended at `0x0800D4DC`, 8 bytes of zero-initialised RAM
at `0x20000218`; the version slot reads `PN1.30`.

- **Edge-free estimator** (replaces the detector's `bl recent_estimate` at `0x08009EFA`). In
  the code 10110110 every high that precedes a low (chips 4 and 7) follows a high. For each such
  high b with its predecessor a and the low c after it, whichever way the detector aligned the
  window one of a / b holds no edge in its readings while the other and c are mixed by the same
  edge fraction f (a mixed high reads L + (1-f)C, a mixed low L + fC), so
  2 max(a, b) - min(a, b) - c = C for every f. A 16-sample window holds three or four such
  triplets; their median rejects the one a change of pair inside the window can corrupt. The
  rail check (the clean highs at 4 095) and the score scale (x 29, / 46, x 12: 21.43 per
  count) are PN1.9's; clean windows score exactly as PN1.29 (210 corpus windows identical).
- **Gain at every displayed window.** The TIM1 1 ms tick's `RECENT` countdown block
  (`0x0800AA1E`, 32 bytes, stock) becomes a call to a helper that counts `RECENT` down as before
  and, in the tracing modes with no hold pending, calls `gain_select_3bit` once for each completed
  window (`COMPLETED_AT`) that the display has already shown (the display records the window it
  showed). The PN1.24 routine's own guards (fresh complete window at the current gain, age,
  1 900 / 450 thresholds, invalidation) are unchanged; the 500 ms tick still calls it too and
  still counts a step-up hold down.
- **Lower bound.** The display (a copy of PN1.29's curve with three insertions) scans the newest 40
  samples and, when they span >= 1 900 counts at a driven gain above 0, counts the window 1.2 dB
  lower (x 7/8) and, when it is weaker than the stored strength, keeps the stored strength. The
  margin covers the gain-step table (20 / 9.2 / 2.6, measured once, on one unit): without it a
  saturated reading at gain 1 could land 1.4 dB above the same signal's unsaturated reading at
  gain 0 and hold the display one level too high for about 0.4 s (seen in the cabinet loop with
  the model's own gain ratios, which differ from the table by up to 1 dB). Stronger windows show
  at once as before.
- **Faster real drop.** An unsaturated weaker window 25 % or more below the stored strength moves
  it half way instead of an eighth; the residual edge dips (<= 1.6 dB) never reach that.

## Validation (emulator)

| Check | Result |
|---|---|
| Estimator vs model | 67 captured (16 samples, pattern) windows equal the model; 96 mixed-edge windows (8 rotations x 3 contrasts x f = 1/3, 2/3 x both alignments) within 3 % of the true contrast; PN1.29 reads as low as 0.33 on them; drifting-f windows within 1 dB |
| Clean windows | 210 corpus windows (clean, clipped, noise, DC; knob 19 % / 100 %; gains 0, 2, 7): scores identical to PN1.29; the display identical except that 48 saturated windows above the lowest gain are counted 1.2 dB lower |
| Steady signal | PN1.29 dip 0.50, 4-6 level changes in 5 s; PN1.30 dip 0.83, 0 changes (amplitudes 720 and 1 000, knob 100 %) |
| Settle, knob 19 %, contact 30 000 | Digital gain steps 242 ms apart, settled 726 ms after the first decision (PN1.29 1 500), one displayed window at each of gains 7, 2, 1, display never falls, same final level; Analog settled in 66 ms, same final level |
| Real drop 30 000 -> 15 000 | level 7 at +90 ms, level 6 at +571 ms (PN1.29 +642 ms, helped by its own dips; the 1/8 filter alone on a steady estimate: +1 007 ms) |
| AGC fixture (PN1.24 stream, knob 4 060) | 20 000 p-p: 7 -> 2 -> 1 -> 0 at 241 / 482 / 723 ms Digital, 21 / 42 / 63 ms Analog, no unowned refresh, no quiet gap over 150 ms; 2 400 -> 800: down then up with the hold kept; 1 850 / 1 170 / 800 no step, 1 950 one step (no hunting) |
| Cabinet at 19 % | all three contact strengths identified in both modes; the toned pair's tone fraction identical on both visits (spread 0.00) |
| `cabinet_scorecard.py` | Digital 14 / 24 with the same verdict on every row as PN1.29; Analog 18 / 24 (PN1.29 19): the one row that differs is a neighbour 0.02 dB above a level threshold that now shows its own level, which is also the toned pair's (0.007 dB under the next threshold), where PN1.29's hysteresis had happened to hold it one lower. The failures in both builds are the Locate range (every pair at the top level by design), pairs sharing a level on a boundary, and the model's first visit while the gain starts from the knob code. What the loop measures of precision, the spread of one pair's tone fraction across its visits, falls from 0.043 to 0.007 (Digital) and 0.015 to 0.001 (Analog) on average |
| Lone cable (`test_rx_knob_response`) | quiet intervals identical to PN1.29 at every knob and signal |
| Unchanged | speaker 1 100 / 500, mains analysis, knob off silences, NCV gain law, full gain in tracing at every knob, a lost signal still releases through the TIM1 countdown |
| Build | parent pinned; only the six declared sites change; no branch lands inside replaced instructions; container round-trips; written files match |

`python -m unittest test_rx_clean_strength test_rx_knob_response -v` (24 + 2 tests, about 4 min);
`python cabinet_scorecard.py pn1.29 pn1.30`; `python steady_probe.py`.

## What this does not do

- It does not move the chip edges out of the readings; the residual 5/6 windows (12 of 125,
  -1.6 dB, runs of up to three) are the windows in which the edge fraction changes between the
  two code periods. The 1/8 filter turns them into -0.2 dB, under the 0.5 dB hysteresis; a
  signal within about 0.1 dB above a threshold can still alternate. A phase-following sampler
  (F2) is the complete fix.
- The owner's report ("1.30 test pass flicker fixed", 2026-09-24) is the device confirmation; it did not
  measure pickup, loudness or selectivity. The release changes the strength arithmetic, the gain timing and
  the display's fall; the checklist in `RX-PN1.30-README.txt` covers a still probe,
  a strong touch, repeated visits, a strong-to-weak move, fast movement (the PN1.23F dropout
  case) and NCV. Roll back with PN1.29.
