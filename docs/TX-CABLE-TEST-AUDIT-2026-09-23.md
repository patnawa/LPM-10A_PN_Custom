# TX Cable Test (wire map) audit, 2026-09-23 — led to TX release v2.33

Status: **audit done; fixes released as TX PN2.33** (GitHub tag v2.33, owner "2.33 test pass",
2026-09-24; RX stays PN1.29). The owner asked to "audit the cable tester function, find bugs, then
fix and improve it", paused on 2026-09-23, and the fixes went through device rounds on 2026-09-24:
PN2.28 → 2.29 → 2.30 → (2.31, 2.32 interim, not archived) → 2.33. Outcome per finding group:

- **Shipped in v2.33:** B2, B5, B6 (RX unit mode decisions), B7, B10, B13 and critic NEW-1 (keys
  and screen guard), I5 (busy indication), plus the LAN cable colours the owner asked for after
  PN2.28.
- **Attempted in PN2.28–2.30 and withdrawn:** B1, B3, B4 (the Switch-mode partner / shield check).
  On the owner's switch the port's centre-tap paths between pairs read within a few counts of the
  pair winding, so every wire of a good cable went yellow. That is inferred from the device result,
  not measured; the diagnostic build PN2.30D (`sdk/cable_diag2.py`) prints the two lowest readings
  per wire and is the way to measure it. Switch mode in v2.33 decides and draws as PN2.27A did.
- **Unchanged by decision:** B8 (RX open test; both proposed changes regressed confirmed behaviour).
- **Open:** the cosmetic items B9, B11, B12, B14, B15 and the improvements other than I5 (I6 and
  I10 partly done, see the table).

Release note: [docs/releases/v2.33.md](releases/v2.33.md). Code, under `LPM-10A/Firmware File/sdk/`:
[`cable_check.py`](../LPM-10A/Firmware%20File/sdk/cable_check.py) (PN2.28),
[`cable_colours.py`](../LPM-10A/Firmware%20File/sdk/cable_colours.py) (PN2.29),
[`cable_fix.py`](../LPM-10A/Firmware%20File/sdk/cable_fix.py) (PN2.30),
[`cable_safe.py`](../LPM-10A/Firmware%20File/sdk/cable_safe.py) (PN2.33),
[`cable_diag2.py`](../LPM-10A/Firmware%20File/sdk/cable_diag2.py) (PN2.30D diagnostic, not a release);
tests [`test_cable_check.py`](../LPM-10A/Firmware%20File/sdk/test_cable_check.py),
[`test_cable_colours.py`](../LPM-10A/Firmware%20File/sdk/test_cable_colours.py),
[`test_cable_fix.py`](../LPM-10A/Firmware%20File/sdk/test_cable_fix.py).

สรุปภาษาไทย: ตรวจฟังก์ชัน Cable Test (wire map) ของ TX ทั้งโหมด Switch และโหมดเครื่องรับ (RX unit) บน PN2.27A
ด้วยอีมูเลเตอร์ที่รันเฟิร์มแวร์จริง พบปัญหา 15 ข้อ (B1–B15) และข้อเสนอปรับปรุง 14 ข้อ (I1–I14) ผลลัพธ์: ออกเฟิร์มแวร์
TX PN2.33 (v2.33, เจ้าของทดสอบบนเครื่อง "2.33 test pass" 24 ก.ย. 2026) ผ่านรอบทดสอบ PN2.28 → 2.29 → 2.30 → 2.33
แก้แล้ว B2 B5 B6 B7 B10 B13 NEW-1 I5 และสายแสดงสีตามสาย LAN (T568B) ส่วนการตรวจคู่สายในโหมด Switch (B1 B3 B4)
ลองใน PN2.28–2.30 แล้วถอนออก เพราะสายดีในสวิตช์ของเจ้าของขึ้นเหลืองทุกเส้น (คาดว่าเส้นทาง centre-tap ของพอร์ตอ่านค่า
ใกล้คู่สายมาก ยังไม่ได้วัดจริง วัดได้ด้วยบิลด์ PN2.30D) B8 คงเดิมโดยตั้งใจ ข้อคอสเมติกและข้อเสนอปรับปรุงที่เหลือยังเปิดอยู่

## Scope and method

- Target: TX PN2.27A (profile `pn2.27a`, sha256 c12b127a…), the Cable Test screen: mode selector,
  Switch mode (stock routine 0x0800CB68), RX unit mode (stock 0x0800C4E0), and the PN layers on it:
  PN2.19 `cable-robust` (11-sample median, max-sample open test, switch threshold 1240, "Not connected"),
  PN2.20 `cable-text-clear`, PN2.21 `cable-values`.
- Workflow `wf_e0e0bb2b-d12` (multi-agent): two agents mapped the routines (appendix files below);
  six independent audit angles (RX-unit logic, switch logic, patch code, task flow/concurrency,
  electrical thresholds, professional-tester gap); a triage merge; then **two independent verifiers per
  finding** — bugs: *reproduce* (emulator script on the real firmware, must go red) and *refute*
  (re-derive the disassembly and physics, default to refuted); improvements: *value* and *feasibility*.
- Everything below is firmware fact or emulator result unless marked as a hardware assumption [H].
  No schematic exists; far-end electrical models (switch magnetics, Bob-Smith paths, the RX unit's
  ladder, mains hum) are assumptions stated in each finding.
- The workflow's completeness critic completed after the pause and is appended at the end of this
  file. Its "plan" agent never completed: no synthesized PN2.28 plan section exists. What was built
  instead is in "What was built (2026-09-24)" below.

## Headline results

| Group | Findings | Verifier outcome |
|---|---|---|
| Wrong or misleading results in **Switch mode** (default mode) | B1 miswire / cross-pair short passes green; B3 shield row inverted; B4 short or leak on an unplugged cable drawn green, "Not connected" suppressed | both verifiers confirmed; both rate P2 (stock had the same behaviour, not a PN regression) |
| **Key handling during a test** | B7 extra OK queues more tests; OK then Back replays and silently switches RX unit mode to Switch → "Not connected" on a good cable | both confirmed (P2) |
| **RX unit mode robustness** | B2 neighbouring crossings (6↔7, 7↔8, 8↔G…) can pass as straight (own-window rule accepts 1 of 8 slots); B5 floating slot averaged in; B6 no one-to-one / plausibility check; B8 connected shield can read open under hum; B9 number on an open wire is hum-lowered | firmware logic reproduced in every case; refuters confirmed B5/B6 as P3 and **refuted B2/B8/B9 as device bugs** — they need hum levels nobody has measured (owner measurements first, see below) |
| Cosmetic / UX | B10 stray Test Retry after Back mid-test; B11 values on crossed rows sit at another wire's end; B12 low-battery recovery redraw; B13 mode byte read twice; B14 dark box behind English text; B15 stray pixel at x 207 | all confirmed, P3–P4 |
| Improvements confirmed valuable + feasible | I1 show the mode / hint the wrong mode; I3 a verdict line naming the fault (crossover, miswire, short, open); I5 busy indication during the ~0.86 s test; I6 test harness with correlated hum and ladder gain error (gate for any RX-mode change); I8 RX-mode numbers as far-end pin names; I10 docs wrong in places | value + feasibility confirmed |
| Improvements needing data or not worth it now | I2 PoE/external voltage warning (uncertain value); I4 unterminated 10/100 hint; I7 centre-tap paths; I13 distance to fault (PHY CSD) — uncertain. I9 English wording, I11 split pairs (physically undetectable at DC), I12 unused LO table, I14 one-press start — value refuted | — |

## What was built (2026-09-24)

1. **Switch-mode classifier** (B1, B3, B4) — built in PN2.28, reworked in PN2.30, **withdrawn in
   PN2.33**. PN2.28 (`cable_check.py`, `switch_tail`) ran after the stock switch routine, from the
   median table PN2.19 already keeps, at the hook site the verifiers chose: the switch-only
   `bl values_hook` at 0x0800CE76 (site (a); the alternative at 0x0800CC16 cannot draw status 0/3
   and would leave the LED green). It took the pins within a margin (m1 + 4 + m1/16, never above
   1240) of each row's lowest reading as the pins the wire is joined to: partner only = ok, one
   other pin = miswire (red), more = short (yellow), shield joined = short, otherwise grey "not
   tested"; a fault set the red LED and double beep. Owner: PN2.28 "2.28 tested", PN2.29 "still
   yellow color no color show", PN2.30 "every line cable test 1-8 show yellow" (good cable in a
   switch port). Cause, reproduced in the emulator and found independently by a code review of
   PN2.28: the check assumed the port's centre-tap (Bob-Smith) paths between pairs read well above
   the pair winding; on the owner's switch they read within a few counts of it, so every wire
   looked joined to several pins and was called a short. PN2.30 (`cable_fix.py`) passed a row when
   its own partner was among the joined pins and stopped claiming cross-pair shorts; still yellow on
   the device. PN2.31 / 2.32 (interim): the grey shield line read as "ground show connect even my
   cable no ground". PN2.33 (`cable_safe.py`) points 0x0800CE76 at a stub in PN2.28's dead
   `classify_row` cave that keeps the stock decisions and only draws the values in the LAN colours,
   so Switch mode decides and draws exactly as PN2.27A (PN2.19 rules: connected when any sensed pin
   reads <= 1240, "Not connected" when all eight are open, G open = red X, the LED ignores G).
2. **Busy guard + screen guard** (B7, B10, B13, I5, critic NEW-1) — **shipped** (PN2.28, kept
   through v2.33). OK while a test runs is dropped, gated by the stock "routine running" byte
   0x20000011; the Cable Test GUI handler at 0x0800C344 runs messages 0x0F..0x12 only while
   sysState == 4 (a guard in front of the dispatcher's call at 0x0800F596), so a test queued before
   leaving can no longer paint the Cable Test layout over Home or SPEED; "Test Retry" is posted only
   if the screen is still armed and the retry label is reset after Back, so the next screen says
   "Test Start"; each routine passes its own mode to the readings drawer (the mode byte is not
   re-read after the test); the button reads "Testing..." / "กำลังทดสอบ" while measuring, and
   PN2.30 restores the text background to the panel colour after it. NEW-1 (emulator, critic): OK
   pressed 3 times during a 0.86 s test then Back, Back → a queued test ran on the Home or SPEED
   screen, painted the Cable Test layout over it, red LED and double beep, while that screen's
   keys stayed live. Stock has the same hole but its 0.144 s test makes it hard to hit.
3. **Verdict line + mode shown** (I3, I1) — **not built**, open.
4. **RX unit mode** (B2, B5, B6; B8 unchanged) — **shipped**, decided from the emulator model, not
   from owner measurements (the UTP/STP retries below were never collected). The decision-side fix
   went in as proposed, sampling unchanged: a row's value is the median of its non-floating slots
   (highest sample <= 4000 and median > 1240) — PN2.28 used a trimmed mean, PN2.30 the median after
   the code review's P1 (two leaky loose wires shifted a good row); the wire goes to the nearest
   ladder value with a common gain estimate over the rows (clamped 0.93..1.07), no own-window
   short-cut; a plausibility pass turns two wires on one remote pin, a wire on an open shield, or
   one level on every wire into unknown (blank row, "Result error!!", red LED). Harness (I6,
   partly): `test_cable_check.py` / `test_cable_fix.py` run the real 0x11 path with correlated
   50 Hz hum and ladder gain sweeps (−5..+5 %, +6 %); every defect test also runs the parent build
   and asserts its wrong answer. B8 stays PN2.19's open test by decision.
5. **LAN cable colours** (owner request after PN2.28) — **shipped** in PN2.29 (`cable_colours.py`):
   T568B in the u16 colour table at 0x0801E2CC (read only by the Cable Test): 1 white-orange,
   2 orange, 3 white-green, 4 blue, 5 white-blue, 6 green, 7 white-brown, 8 brown, G silver; the
   striped wires carry white dashes (5 px every 12 px, x 29..170), along crossed diagonals in RX
   unit mode; the reading at the wire end is in the wire's colour; fault colours win and get no
   dashes.
6. **Cosmetic B11, B14, B15, RX-mode pin names I8** — not built, open. **Docs I10** — partly: the
   module docstrings and FORMULA-AUDIT §4.1 (updated for v2.33) state the corrected facts:
   the wire map runs in the GUI task (GUI message 0x11 from the COUNT task), not the CNT task; bit
   0x10 of 0x20000010 means "layout armed", not "test started"; PN2.21's number is the lowest
   median, which is not always the value that decided the row.

Build notes: the stages are one profile chain in `sdk/profiles.py` (pn2.27a → pn2.28 → pn2.29 →
pn2.30 → pn2.33), each module pinning its exact parent SHA; `python build.py --write` builds pn2.33,
`--profile pn2.28` (etc.) reproduces a stage, `test_profiles.py` pins every digest byte-exact. The
critic's extra 4 KB extend was not needed for what shipped: the image is still 401 408 bytes
(PN2.27A's size). Tests: `test_cable_check` (19), `test_cable_colours` (6, one optional
preview-image test skipped), `test_cable_fix` (9) plus the existing 22 = 56 Cable Test tests.

**Open: measurements still wanted**
- Switch mode: the PN2.30D diagnostic (`python cable_diag2.py --write`, flash, photograph, flash
  back) on a good cable in the owner's switch, in Switch mode. It prints each wire's two lowest
  readings and their pins (e.g. "2  60 5  63"), the margin any partner check needs. B1 / B3 / B4
  stay withdrawn until then.
- RX unit mode, on v2.33: a straight UTP and a straight STP cable, 5 × Test Retry each, photo of
  every result; one deliberately 6↔7-swapped (or reversed 7-8) patch cord. These settle B8 / B9 and
  confirm the new rules on the device.
- Code review of PN2.28, remaining P2 / P3 items, open only if the partner check returns: the label
  of a broken wire's partner behind a centre-tap port (I7), and the label of a hard short between
  pairs (PN2.30 stopped claiming it: it cannot be told from the centre taps).

## Where things are

- Evidence folder (outside the repo, survives Temp clean-up): `C:\Users\Alpha\Documents\LPM-10A-cable-audit-2026-09-23`
  - `map-far-end.md`, `map-switch.md` — annotated disassembly/semantics of both routines on PN2.27A;
  - `findings.json` — every merged finding and every verifier's full output;
  - `scratch/` — all emulator scripts and outputs (`verify-Bn`, `refute-Bn`, `value-In`, `feas-In`, lens folders);
  - `workflow-journal.jsonl` — the raw workflow journal.
- Repo, under `LPM-10A/Firmware File/`: profile chain `sdk/profiles.py`; modules `sdk/cable_check.py`
  (PN2.28), `sdk/cable_colours.py` (PN2.29), `sdk/cable_fix.py` (PN2.30), `sdk/cable_safe.py`
  (PN2.33), `sdk/cable_diag2.py` (PN2.30D); tests `sdk/test_cable_check.py`,
  `sdk/test_cable_colours.py`, `sdk/test_cable_fix.py` beside `sdk/test_cable_test.py`,
  `sdk/test_cable_values.py`, `sdk/test_cable_clear.py`; images `LPM-10A-TX_PN2.33-cable-safe.bin`
  with `TX-PN2.33-README.txt` at the folder root, the PN2.28 / 2.29 / 2.30 / 2.30D / 2.33 builds
  with README and SHA256SUMS in `experimental/`, PN2.27A in `archive/`.
- Release note: `docs/releases/v2.33.md`.
- Emulator harness: `sdk/test_cable_test.py` (Harness, far_end kinds), `sdk/test_cable_check.py`
  (Rig: the real 0x11 path with far end, hum and mid-test key events), `sdk/thai/engine.py` (Scene),
  `sdk/thai/mockup.py` (sc_cable_result).
- The workflow's "plan" agent never completed: this file has no synthesized plan section. The
  completeness critic did complete and is appended at the end.

## Summary table

| ID | Sev (claimed) | Finding | Verifiers | v2.33 |
|---|---|---|---|---|
| B1 | P1 | Switch mode passes a wire crossed into another pair, or a short between pairs, as good: eight green wires, green LED, no beep, no text | reproduce confirmed (run) / refute confirmed (run) | withdrawn |
| B2 | P1 | RX unit mode passes crossings between neighbouring ladder values as straight (6<->7, 7<->8, 8<->G, 5<->6; 1-2 and 4-5 at higher hum): the own-window rule accepts any 1 of 8 slots, and the 11-sample median does not reject mains hum | reproduce confirmed (run) / refute refuted (run) | shipped |
| B3 | P1 | Shield (G) row is inverted in Switch mode: G shorted to a conductor turns green and passes, while an open G, which is normal in Switch mode and on UTP in RX mode, is drawn as a red broken wire next to a green LED | reproduce confirmed (run) / refute confirmed (run) | withdrawn |
| B4 | P1 | Switch mode with nothing (or no switch) at the far end: a short, or a leak of up to a few kilohms, draws those two wires green as the only good ones and suppresses 'Not connected' | reproduce confirmed (run) / refute confirmed (run) | withdrawn |
| B5 | P2 | RX unit mode: a floating slot (a broken wire, or the unconnected G contact) is averaged into the crossing decision, because the range test uses the median while PN2.19's open test uses the highest sample | reproduce confirmed (run) / refute confirmed (run) | shipped |
| B6 | P2 | RX unit mode: no plausibility or one-to-one check. A leaky unplugged cable reads as eight wires crossed to G (or to 8) instead of 'Not connected', and two wires can be shown landing on one remote pin | reproduce confirmed (run) / refute confirmed (run) | shipped |
| B7 | P2 | No busy check on OK during a test: every press queues another full test, and an OK followed by Back is replayed after Back, which undoes Back and silently switches RX unit mode to Switch, so the next retry shows 'Not connected' on a good cable | reproduce confirmed (run) / refute confirmed (run) | shipped |
| B8 | P2 | RX unit mode: a connected shield is drawn OPEN. PN2.19 compares each slot's highest sample with 4000, only 100 counts above the shield's ladder value of 3900 | reproduce confirmed (run) / refute refuted | unchanged |
| B9 | P2 | RX unit mode: the number on an open wire is the hum-lowered lowest median (often 3700-3950, next to the shield's 3900), not the value the open rule judged, and the docs say ~3800 means leakage or moisture | reproduce confirmed (run) / refute refuted | open |
| B10 | P3 | Back during a running test leaves a stray 'Test Retry' button and a stale retry label; a quick double Back draws garbage as the title (menu_name_table[-2] = the count_queue handle) | reproduce confirmed (run) / refute confirmed (run) | shipped |
| B11 | P3 | RX unit mode, crossed rows: each value is drawn where a different wire lands, in the wrong colour, and hides that wire's end | reproduce confirmed (run) / refute confirmed (run) | open |
| B12 | P3 | Low-battery recovery redraws the armed result layout even while the selector is showing; the selector then draws over the wire panel | reproduce confirmed (run) / refute confirmed (run) | open |
| B13 | P3 | values_hook reads the mode byte twice, after 0.86 s of measurement; a key press in between can change it | reproduce confirmed (run) / refute confirmed (run) | shipped |
| B14 | P3 | English 'Not connected' and 'Result error!!' sit in a dark 0x2105 box on the 0x31A7 band; Thai has no box | reproduce confirmed (run) / refute confirmed (run) | open |
| B15 | P3 | The wire's last pixel (x 207) shows as a dot after every value | reproduce confirmed (run) / refute confirmed (run) | open |
| I1 | P2 | The wrong far-end mode gives a wrong result with no hint, and the mode resets to Switch on every entry and Back and is never shown on the result screen | value confirmed (run) / feasibility confirmed (run) | open |
| I2 | P2 | No PoE or external-voltage check before the wire map drives the RJ45 pins, although poe_mv is measured every 10 ms on this screen | value uncertain (run) / feasibility confirmed (run) | open |
| I3 | P2 | No verdict line: fault types are never named. A crossover or reversed pair is an unnamed failure, two separate shorts can look like one, and the text line is empty on pass and on most fails | value confirmed (run) / feasibility confirmed (run) | open |
| I4 | P2 | A 10/100 port that leaves pins 4, 5, 7 and 8 unterminated gives a hard FAIL on a good cable | value uncertain (run) / feasibility confirmed (run) | open |
| I5 | P3 | A test shows no busy indication for about 0.8 s: the panel is blank, the button still says 'Test Retry', and the LED keeps the old result, which invites the key presses behind B7 and B10 | value confirmed (run) / feasibility confirmed (run) | shipped |
| I6 | P3 | The test harness cannot reproduce correlated mains hum or ladder gain error, so the existing 22 tests cannot catch B2, B5, B6 or B8 | value confirmed (run) / feasibility confirmed (run) | partly |
| I7 | P3 | On ports with centre-tap/Bob-Smith DC paths, one broken wire leaves its partner green with a letter for an unrelated pin; the docs and tests assume both wires go red | value uncertain (run) / feasibility confirmed (run) | open |
| I8 | P3 | In RX unit mode the per-wire number is a raw ADC count that names no pin, and the two modes use different formats | value confirmed (run) / feasibility confirmed (run) | open |
| I9 | P3 | English 'Not connected' is ambiguous, and it is also shown when the RX unit is connected | value refuted (run) / feasibility confirmed (run) | open |
| I10 | P3 | The cable docstrings and FORMULA-AUDIT section 4.1 are wrong in several places: task, mode bit, frame-draw arguments, 'the number that decided it', and the floating-wire median | value confirmed (run) / feasibility confirmed (run) | partly |
| I11 | P3 | True split pairs cannot be detected in either mode (DC matrix only), so a split-pair cable passes; the wording should not claim more | value refuted (run) / feasibility confirmed (run) | open |
| I12 | P3 | The PN2.19 LO (minimum sample) table is written 72 times per test and never read | value refuted (run) / feasibility confirmed (run) | open |
| I13 | P3 | No distance to fault on the wire map; the PHY's per-pair CSD status bits are unused | value uncertain (run) / feasibility confirmed (run) | open |
| I14 | P3 | Starting a test takes two OK presses: the first only draws an empty frame | value refuted (run) / feasibility confirmed (run) | open |

## Findings

Each finding: the merged claim from the audit lenses and each verifier's verdict with the first line of its severity assessment. The verifiers' full assessments, evidence (commands, outputs, disassembly) and fix corrections are in `C:\Users\Alpha\Documents\LPM-10A-cable-audit-2026-09-23\TX-CABLE-TEST-AUDIT-full.md` and `findings.json`.

### B1 [bug, claimed P1] Switch mode passes a wire crossed into another pair, or a short between pairs, as good: eight green wires, green LED, no beep, no text

- Sources: switch-logic: Switch mode passes cables with wires crossed between pairs, switch-logic: Switch mode passes a short between wires of different pairs; the PN2.21 letter is not a reliable hint, patch-code: Switch mode shows a split pair or a short between pairs as all-green, professional-gap: Switch mode passes cables with a short between pairs or a wire swapped across pairs
- Location: pn2.27a switch wire map 0x0800CB68.
- The only status write is at 0x0800CBDE..0x0800CC0C: `cmp.w r0,#0x4D8 ; ble` at 0x0800CBEA counts the medians above 1240; `cmp r7,#8` at 0x0800CBFC gives 1 (open) when all 8 are above, else 2 (ok).
- Status 2 draws a line in the wire colour at 0x0800CC3E.
- The fault flag r8 is set only at 0x0800CCC4 (status 1, not G) and 0x0800CE1C (status 4).
- PN2.21 values_hook 0x08068F98 (called from 0x0800CE76) picks the letter from the first lowest median (0x08068FB4..0x08068FC6, `cmp r3,r7 ; bhs`).

**Mechanism.** A row's status depends only on how many of its 8 medians are above 1240. The sensed-pin index fp is used only for select(fp,1), and map[] is zeroed and never written in this mode. So the routine never checks WHICH pins a wire reaches, or HOW MANY.

A switch far end joins far 1-2, 3-6, 4-5 and 7-8 at DC (hardware: the magnetics). On a correct cable, straight or crossover, each near pin reaches exactly its T568 partner, so the letters read 2 1 6 5 4 3 8 7.
- Wire swapped into another pair (e.g. near 2 to far 3): every row still has exactly one partner at or below 1240, just the wrong one, so status 2.
- Short between two pairs (e.g. 1-3): rows 1, 2, 3 and 6 each reach several pins; still status 2.

The LED rule sees no fault. The only sign is PN2.21's small letter, which shows the single lowest median (ties go to the lowest slot). For a short, the direct path and the short path differ by less than 1 count, so ADC noise picks the letter; on some retries it looks exactly like a good cable.

pn2.18 behaves the same, so this is not a PN regression.

What a switch far end cannot show at DC (physics, not a firmware defect): a short inside one pair, a crossover, a reversed pair, a 4-5<->7-8 pair swap, and a true split pair (pins straight, wrong twisting).

Terminology: patch-code's 'split pair (tester 2<->3 swapped)' is this cross-pair miswire, which DC can see. It is not a true split pair (see I11).

**What the owner sees.** In Switch mode, which is the default on entry, two kinds of faulty patch cable show eight green wires, a green LED and no text:
- two wires crimped into the wrong pair positions;
- a crushed or badly crimped conductor shorting pair 1-2 to pair 3-6.

The only sign is the small letters (3 6 1 . . 2 instead of 2 1 6 . . 3). For a short they change between retries and sometimes look exactly normal.

The owner passes a cable that will not link at 1 Gb/s, drops to 100M or shows errors, and the switch port gets blamed.

**Proposed fix (audit).** Add one switch-only classifier that reads the MED table already in the arena (0x2000F144).

Where to hook it:
- (a) Change 0x0800CE76 `bl values_hook` to `bl switch_values_hook`; the far-end site 0x0800CB18 keeps its own entry. This also fixes the mode per call site (B13).
- (b) Less code: a 4-byte `bl` at 0x0800CC16, replacing `ldr r0,=status ; ldrb r0,[r0,#8]` and returning r0 = status[8], rewrites fault rows before the stock draw loop. The switch draw loop draws nothing for status 0 or 3 (0x0800CCC2), so those need their own drawing, and release_hook's 'Not connected' test must skip reclassified rows.

Rule:
- ref = this test's direct level (median of the per-row minima that are <= 1240).
- near(r) = {p : med <= 1240 and within a margin of ref}.
- Expected partner E: 1<->2, 3<->6, 4<->5, 7<->8.
- near == {E}: OK.
- near == {q}, q not E: miswire ('Miswire 1-3 2-6' / 'สลับสาย').
- More than one pin in near: SHORT; merge the groups and print 'Short 1-2 / 3-6' / 'ลัดวงจร' (pair level is all a switch far end can resolve). Draw every near pin's letter, or '*'.
- Fault rows get a fault colour (0x08016ADC redraw, yellow 0xFFE0, or a red letter), plus rgb_led(1) and 0x080116E0(2), the stock fail calls at 0x0800CE62..0x0800CE6A.
- Allow extra partners inside {4,5,7,8} for 10/100 ports whose Bob-Smith network joins 4-5 to 7-8 at DC (hardware inference).

The margin cannot be set without hardware:
- Prototype values: max(24, ref/4) in switch-logic; min(1240, 2*lowest+100) in professional-gap.
- A plain <= 1240 rule would flag every row if a cross-pair termination path read about 700 counts.
- Modelled levels: direct about 63 vs cross-pair about 121 (model P); about 378 vs about 588 (model A).

Staging:
1. Text only, plus a diag build that dumps all 72 medians on a gigabit, a 10/100 and a PoE switch. The current cable-diag prints only the lowest median per row.
2. Enable the red LED and beep once those captures show the partner is clearly lower than any cross-pair path.

Validate on the device with a deliberately miswired cable.

- *reproduce*: **confirmed** (run) — Confirmed. P1 is defensible for a cable tester in its default mode, but this is a missing check that stock firmware already lacked, not a regression; pn2.18 behaves the same.
- *refute*: **confirmed** (run) — The behaviour is real. In Switch mode, which is the default, a pair swap or a short between pairs gives a false pass: 8 green wires, green LED, no beep, no text. It holds for any switch-side network whenever a good cable reads green.

### B2 [bug, claimed P1] RX unit mode passes crossings between neighbouring ladder values as straight (6<->7, 7<->8, 8<->G, 5<->6; 1-2 and 4-5 at higher hum): the own-window rule accepts any 1 of 8 slots, and the 11-sample median does not reject mains hum

- Sources: far-end-logic: RX-unit mode: the own-window rule (any 1 of 8 slots within +-5 %) hides crossings at the top of the ladder, electrical-thresholds: The 11-sample median over 10 ms does not reject mains hum; RX-unit crossings between neighbouring ladder values are missed
- Location: pn2.27a far-end routine 0x0800C4E0:
- rule 3 (own +-5 % window) at 0x0800C5CC..0x0800C642; the 0.95f/1.05f literals are at 0x0800C900/0x0800C904, applied around T[r4]; ladder table at 0x0801E2BA
- rules 5/6 (average, then nearest) at 0x0800C644..0x0800C704
- no one-to-one check before the draw loop at 0x0800C71E
- PN2.19 sample 0x08068E70 (11 x adc_read(4), vTaskDelay(1) between), called at 0x0800C544 (far end) and 0x0800CBCA (switch)

**Mechanism.** Once SHORT and OPEN fail, rule 3 marks the row OK if ANY one of its 8 slot medians lies strictly inside T[driven]*(0.95..1.05). This runs before the average/nearest step.

From pin 5 up the windows overlap: 5/6 by 57 counts, 6/7 by 120, 7/8 by 64, 8/G by 156. The own window therefore also accepts readings that are nearer the neighbour. Own-window margins of common crossings are small: 7-8 reversed 105/119 counts, 4-5 182/198, 1-2 222/238, 8<->G 27/39.

Two things push one slot across:
- Mains hum. The 11 samples, 1 ms apart, span 10 ms: half a 50 Hz period, 0.6 of a 60 Hz one. A slot's median is offset by up to 0.707*A at 50 Hz and 0.588*A at 60 Hz (bias.py). far-end-logic quoted 0.59*A, but its own floating-wire minima, e.g. A=200 -> 3953, match 0.707*A. Slots are 12 ms apart, so they sit at different phases and one usually lands in the window. PN2.19's premise that a real connection is steady holds for a switch winding, but not for the kilohm-level RX ladder [H].
- A systematic ladder error of about 1 %, with no hum at all.

The average (rules 5/6) would give the right pin, but rule 3 stops the row first. Nothing checks that the map is one-to-one (see B6).

Verified by electrical-thresholds:
- The tick is 1 ms: SysTick LOAD 0x2327F and CTRL 7 at 0x0801C744; PLL = HSE x18 = 144 MHz at 0x08018120.
- adc_read(4) returns a fresh conversion: ADC1 0x40020800 scans 5 ranks continuously with circular DMA to 0x20000C68, refreshed at least every 340 us.
- Settling is not the cause: samples fall 1.7..11.7 ms after the select.

INFERENCE (no schematic):
- Every sensed pin reads the ladder value of the remote pin that the driven wire reaches. This is the firmware's own assumption.
- Hum on a ladder wire: far-end-logic models it as A*T/4095, electrical-thresholds as the full A. Both models show the failure.
- A of about 100 counts is plausible: the owner's 2026-09-21 stock-firmware report implies floating-wire hum above the 95-count margin.
- Cable series resistance is not a realistic cause: a 100 m loop moves pin 1 by about 3 counts in a 10 k pull-up model.

**What the owner sees.** In RX unit mode, a cable with 6 and 7 swapped, a common termination slip, can show every wire straight with a green LED. It can also show one diagonal whose partner is drawn straight, so two wires appear to land on one RX pin. Test Retry flips between the right answer, the half answer and 'good'.

With more hum, a reversed 7-8 pair, a 5-6 swap and 'green pair not split' behave the same. At higher hum, so do reversed 1-2 and 4-5 pairs.

On shielded cables an 8<->G swap is misreported with almost any hum.

The printed number contradicts the drawing: for example 3133 on wire 7.

**Proposed fix (audit).** There are two complementary fixes.

(A) Decision-side (far-end-logic). It handles both hum and static gain error, and keeps the same test time:
1. `sample` also stores the mean of its 11 samples in a new arena table MEAN[72] (img.alloc_ram).
2. At 0x0800C5CC put `bl classify_row`, and at 0x0800C5D0 put `b.n 0x0800C714`. classify_row (r4 = driven pin, AAPCS):
   - ladder slots are those with HI < 4095 and MED > 1240;
   - x = trimmed mean of their MEANs (drop the lowest and highest when there are 4 or more);
   - r = nearest T, with no own-window pass;
   - write status 2 or 3, map[r4] = r, X[r4] = x.
3. At 0x0800C71E replace `ldr r0,[pc,#0x1d0]; ldrb r0,[r0,#8]` with `bl post_pass`, which returns r0 = status[8]:
   - (a) Gain self-calibration: when rows 0..7 all have an X, k = median of the sorted X / T[0..7]; reclassify with X/k. Without this, a plain nearest rule narrows straight-cable tolerance to 0.97..1.03.
   - (b) Two rows landing on one remote pin both become status 4 (B6).
4. values_hook prints X[r4] for status 2 and 3 rows.

(B) Sampler-side (electrical-thresholds). The far-end site 0x0800C544 gets its own sampler; the switch site 0x0800CBCA keeps PN2.19's, since its margin is above 2800 counts. The new sampler:
- takes 20 reads 1 ms apart;
- forms pair means p_k = (x_k + x_{k+10})/2 for k = 0..9, keeping pairs where both samples are < 4090;
- value = median of the kept pairs, or 4095 if none;
- floating = at least 8 clipped pairs, or value > 4000;
- stores MED = HI = (floating ? 4095 : value) and LO = min, and preserves r4..r7.
This cancels the 50 Hz fundamental exactly; the 60 Hz residual is 0.18A. It costs about 0.65 s: 0.86 s -> 1.51 s.

(B) alone keeps rule 3, so the static ~1 % gain cases from e2_scale.py remain. (A) also fixes B5 and B6. (B) also fixes B5 and B8.

Hardware gate: photograph PN2.21's per-row readings for a straight UTP and a straight STP cable in RX unit mode; validate with the cable-diag build near a mains run. Regression tests: I6.

- *reproduce*: **confirmed** (run) — The firmware defect is confirmed deterministically. With no noise model at all, one slot out of eight inside the driven pin's own ±5 % window marks a crossed wire OK. Rule 3 then pre-empts the average/nearest step, which would have given the right pin.
- *refute*: **refuted** (run) — This is not a P1 bug as stated. The code-level weakness is real and comes from stock: at the top of the ladder a crossing is only 27-50 counts from being called straight, against 100-240 counts elsewhere, and "any 1 of 8 slots" takes the worst of 8 noisy readings.

### B3 [bug, claimed P1] Shield (G) row is inverted in Switch mode: G shorted to a conductor turns green and passes, while an open G, which is normal in Switch mode and on UTP in RX mode, is drawn as a red broken wire next to a green LED

- Sources: switch-logic: Shield (G) row is inverted in Switch mode, professional-gap: Shield row: G is drawn as a red broken wire with an X on every switch-mode test and on every unshielded cable, while the LED says pass
- Location: - Switch routine: row 8 uses the same any-reading-<=1240 rule, 0x0800CBFC..0x0800CC0C.
- Draw loop 0x0800CCC4..0x0800CCD0 (`mov.w r0,#0xf800; str fg; cmp r4,#8; beq skip; mov.w r8,#1`): a red line with an X, and the fault flag is skipped for G.
- Status 2 draws a green line at 0x0800CC3E.
- Far-end G open is drawn at 0x0800C7D0/0x0800C7D8.
- release_hook 0x08068F00 ignores row 8.
- values_hook draws status 1 in red.

**Mechanism.** A switch port never DC-connects its shield or chassis to a signal pin; the Bob-Smith node reaches chassis only through a capacitor [hardware inference]. So in Switch mode, a G row that reaches any pin at or below 1240 is always a fault, and an open G is normal.

The firmware does the opposite:
- An open G is drawn red with an X on every good cable. The LED deliberately ignores row 8.
- G shorted to a conductor gets status 2: a green G line, a green LED, no beep. The shorted conductor's letter shows 'G' only on some retries.

In RX unit mode a UTP cable has no shield, so G is also drawn red with '4095' under a green LED.

A red 'broken' wire next to a green pass LED is contradictory.

**What the owner sees.** With a shielded cable whose foil or drain touches a conductor, Switch mode shows everything green, including G, which reads like 'shield continuous'.

Meanwhile every good cable in Switch mode, and every UTP cable in RX unit mode, shows G as a red broken wire with an X under a green LED. That trains users to ignore red rows, and the owner has already questioned it.

**Proposed fix (audit).** Switch mode (hook at 0x0800CC16 before the draw loop, or in B1's switch-only values hook):
- G open: set status[8] = 5, 'not tested'.
  - The switch draw loop draws nothing for codes other than 1, 2 and 4 (0x0800CC38 `cmp r0,#4 ; bne 0x0800CCC2`).
  - r6 is discarded by 0x0800C344, and release_hook ignores index 8.
  - values_hook prints a grey '  --' (0x4A69) instead of a red '- 4095'.
- G reaching any pin at or below 1240 is SHORT-G:
  - a yellow row or letter and a 'Shield short' text;
  - rgb_led(1) and a double beep;
  - the same for any signal row whose near set contains G.

RX unit mode:
- An open G is drawn as a grey line without the X, and the verdict adds ' (no G)' (see I3).
- A good G stays white.
- A G short still fails.

- *reproduce*: **confirmed** (run) — I rate this P2 (medium), one step below the claimed P1. It is real, but inherited: stock V2.0.7 and pn2.18 behave identically, so it is not a PN regression.
- *refute*: **confirmed** (run) — P1 is overstated. I rate it P2 for the missed shield short and P3 for the red-G presentation.

### B4 [bug, claimed P1] Switch mode with nothing (or no switch) at the far end: a short, or a leak of up to a few kilohms, draws those two wires green as the only good ones and suppresses 'Not connected'

- Sources: switch-logic: Nothing at the far end plus a short or leak: the shorted wires are drawn green as the only good wires, and 'Not connected' disappears
- Location: - 0x0800CBDE..0x0800CC0C: a row is OK if any reading is <= 1240, whatever the far end is.
- release_hook 0x08068F00: 'Not connected' only when status[0..7] are all 1.
- 0x0800C30E: Switch mode is forced on every entry.

**Mechanism.** Switch mode treats every path at or below 1240 as 'the switch joined this wire'.

With nothing at the far end (the owner's original 2026-09-21 situation), a short or low-resistance leak between two wires is the only path. Those two rows get status 2 and are drawn green, the six healthy but unterminated wires are drawn red, and 'Not connected' disappears.

The 1240 threshold is 0.42 x R_pu:
- reading = 4095(R_on+R)/(R_pu+R_on+R);
- the 60-count short fixes R_on = R_pu x 60/4035;
- so the threshold is about 4.2 kohm if the pull-up is 10 k [the pull-up value is inference].
Contamination or moisture leaks of up to a few kohm therefore also draw green.

pn2.18 has the same logic.

**What the owner sees.** Testing an unterminated run in Switch mode: two wires show green, six red, the LED is red, and there is no text.

The owner concludes that six wires are broken and two are good. In fact the six are fine and the two green wires are shorted together. A 3-6 short looks exactly like 'only the 3-6 pair reaches the switch'.

**Proposed fix (audit).** In the B1 classifier, first decide whether the far end is a switch: at least two T568 pairs must each be joined only to their own partner (near(a) == {b} and near(b) == {a}).
- If it is not a switch, every joined set is a SHORT: draw it yellow and print 'Short 1-3 (far end not a switch)' in place of 'Not connected'.
- A single joined pair is ambiguous: print it as 'joined', never as a green pass.
- Keep 'Not connected' for the all-open case.

- *reproduce*: **confirmed** (run) — The firmware part is confirmed exactly as claimed. In Switch mode, with nothing at the far end and a short or low-reading path between two wires:
- *refute*: **confirmed** (run) — The finding is correct, but I rate it **P2**, not P1, for four reasons:

### B5 [bug, claimed P2] RX unit mode: a floating slot (a broken wire, or the unconnected G contact) is averaged into the crossing decision, because the range test uses the median while PN2.19's open test uses the highest sample

- Sources: far-end-logic: The average of in-range slots takes in a broken wire whose hum-pulled median dips under 4000, electrical-thresholds: RX unit mode: a floating wire's slot is averaged into the crossing decision
- Location: - Far-end average loop 0x0800C644..0x0800C680. A slot counts when its median is in 1242..3999: 0x0800C65E `ldr r0,=0x2000025A ; ldrh.w r0,[r0,r5,lsl#1]`, then 0x0800C664 `cmp r0, ip(=4000) ; bge skip`.
- The open test is at 0x0800C5A8: `bl hi_slot` (0x08068ED8).
- PN2.19 sampler: 0x08068E70.

**Mechanism.** PN2.19 moved the per-slot open test to the highest of 11 samples but left the averaging loop on the median.

A floating conductor always clips at the rail, but its median over half a 50 Hz cycle sits up to 0.707*A below 4095 (0.588*A at 60 Hz). For A of about 135-165 counts or more, the median drops under 4000 at some phases. PN2.19's docstring premise, that a floating wire's median is at the rail, is false for sine hum.

That slot then joins the average of ladder readings and moves it by (about 3990 - T)/7 or /8, i.e. +75 to +292 counts. That is past the nearest-value boundaries 1816/2148/2464/2772/3060, so a crossing is assigned to the next ladder value. That can be the driven pin itself, so the wire is drawn straight. On straight rows rule 3 hides it. Stock had the same weakness.

The scope depends on the hum model:
- far-end-logic (ladder hum scaled by T/4095) needs a double fault: a crossing plus a broken wire.
- electrical-thresholds (full A on every wire, including the unconnected G contact on UTP) also shows it for a single reversed pair (1-2, 3-6) on UTP.
[H] How much hum the unconnected G contact picks up is unknown. A broken wire is a real long floating conductor.

**What the owner sees.** In RX unit mode, a crossing together with a broken wire (e.g. a crossover cable with a cut conductor) shows the wrong crossing. If the unconnected G contact picks up hum, a plain reversed pair on UTP does too.

Examples: 1 crossed to 3 instead of 2, with wire 2 drawn straight; or 6 crossed to 4 instead of 3. The picture changes between retries.

**Proposed fix (audit).** Minimal fix (electrical-thresholds): replace the 6 bytes at 0x0800C65E (a6 48 30 f8 15 00) with `bl hi_slot ; nop`, the same change PN2.19 made at 0x0800C5A8.
- hi_slot is at 0x08068ED8 in pn2.27a (img.cable['hi_slot']).
- The value summed is still the median, reloaded at 0x0800C66C.
- hi_slot clobbers only r0 and r1. r1 is dead here; r3, ip, r5, r6 and r7 are untouched.
- It works with B8's hi_slot variant.

Fuller fix: B2(A)'s classify_row excludes slots with HI == 4095 and uses a trimmed mean. The B2(B) sampler also covers it.

Also correct the cable_test.py docstring (I10) and add a sine-hum regression test (I6).

- *reproduce*: **confirmed** (run) — **P2 holds.** The firmware defect is real and deterministic: PN2.19 judges "open" on the highest sample but "in range for averaging" on the median. A floating slot therefore passes the open test's escape (its highest sample, 4095) and still has its median averaged in whenever the median dips below 4000.
- *refute*: **confirmed** (run) — The firmware defect is real. I would lower it from P2 to P3, because the device-level trigger is not verified.

### B6 [bug, claimed P2] RX unit mode: no plausibility or one-to-one check. A leaky unplugged cable reads as eight wires crossed to G (or to 8) instead of 'Not connected', and two wires can be shown landing on one remote pin

- Sources: far-end-logic: No plausibility or consistency check: a leaky unplugged cable in RX unit mode reads as eight wires crossed to G
- Location: - pn2.27a far-end nearest search 0x0800C684..0x0800C704, with no distance limit.
- No post-pass between the end of the measure loop (0x0800C71A) and the draw loop (0x0800C71E).
- release_hook 0x08068F00 shows 'Not connected' only when status[0..7] are all 1.

**Mechanism.** Any average from 1242 to 3999 gets a remote pin, however far it is from the ladder value, and the 9 results are never checked to form a permutation.

A floating wire that sits DC-low at 3600..3999 (leakage or moisture) has a highest sample at or below 4000, so it is not OPEN. Every row's average then falls into G's catchment (>= 3790) or pin 8's.

The result is a fabricated but plausible map with a red LED and a double beep, and 'Not connected' is suppressed.

The same missing check lets a result show two wires on one remote pin ('6->7 7:ok', '8->G G:ok' in B2).

**What the owner sees.** A damp or leaky cable that is not plugged into the RX unit shows all eight wires as diagonals to the shield (or to pin 8), a red LED and a double beep, instead of 'Not connected'. The owner could chase a wiring fault that does not exist.

A crossing can also be drawn with two wires ending on the same RX pin.

**Proposed fix (audit).** 1. Add a post-pass before drawing (B2(A)'s `bl post_pass` at 0x0800C71E): when two or more rows land on the same remote pin, set them to status 4.
2. Optionally add a distance limit: |x - T[r]| <= 0.45 x the gap to the nearer neighbour, otherwise status 4.
3. When status-4 rows exist, release_hook prints a clearer line than 'Result error!!', e.g. 'Check cable'. When every signal row is status 4 and all read within about 150 counts of one value, print 'Not connected (leakage)'.

- *reproduce*: **confirmed** (run) — P2 holds for the firmware logic.
- *refute*: **confirmed** (run) — **Downgrade from P2 to P3** (robustness / plausibility).

### B7 [bug, claimed P2] No busy check on OK during a test: every press queues another full test, and an OK followed by Back is replayed after Back, which undoes Back and silently switches RX unit mode to Switch, so the next retry shows 'Not connected' on a good cable

- Sources: flow-concurrency: A second Test Retry press during a test is replayed after Back, flow-concurrency: OK presses during a test queue full re-tests (no busy check), patch-code: About 0.86 s blank frame during the test; OK presses queue more full tests (OK-queue part)
- Location: - COUNT handler 0x0800C3FC: every OK becomes GUI 0x11 (0x0800C412..0x0800C418), with no busy check.
- GUI 0x11 handler 0x0800C366..0x0800C398: when armed it runs a full test; when mode&0xF0 == 0 it takes the arm path and sets mode 0x10 (Switch).
- cable_back 0x0806784C -> cable_test_enter 0x0800C300 sets mode = 0 at 0x0800C30E and retry = 0 at 0x0800C30C.
- Running byte 0x20000011: stored at 0x0800C4F2, 0x0800CB20, 0x0800CB78 and 0x0800CE7E, never loaded.
- gui_queue: 20 x 8 entries, drop-oldest (0x0800E548..0x0800E574).
- Routine tails: 0x0800CB1C and 0x0800CE7A.

**Mechanism.** The wire map runs inside APP_GUI_task (priority 1) and blocks it for about 0.79-0.86 s: 864 ticks, against 72-144 ms in stock, so the window is about 6x wider. Event_key_task and APP_COUNT_task (priority 2) keep running.

Every OK becomes GUI 0x11, and each 0x11 while armed runs a full test. Nothing reads 0x20000011. The consequences:
- N extra presses give N more full tests, about 0.86 s each and up to 20 queued. Each test wipes the panel first, so the result blanks and reappears.
- OK then Back: Back runs cable_test_enter at once (mode = 0, retry = 0, sysState 4, posts 0x36 and 0x0F). When the test returns, the queued 0x11 runs first. Mode&0xF0 is now 0, so it takes the arm path, sets mode = 0x10 (Switch) and posts 0x10. The result layout comes back, and the RX unit choice is silently lost.
- OK, Back, Back: the replayed 0x11 arms the layout while sysState = 2, so the keys act as Home.
- OK, OK, Back, Back: a second full test runs (792 ADC reads) while the user is on Home.

**What the owner sees.** The owner is in RX unit mode, presses Test Retry, then presses again because the panel stays blank, then presses Back. The selector flashes and the result screen comes back.

The next Test Retry shows nine red wires, 'Not connected', a red LED and a double beep on a good cable: the tester is silently in Switch mode.

With a double Back, the Cable Test screen stays up while the buttons act as Home. Several presses make the result blank and reappear for several seconds.

**Proposed fix (audit).** Add one busy gate in the stock byte 0x20000011 (write-only in the image, 0 at boot):
- bit0 = running
- bit1 = Back pending
- bit2 = test posted but not started

Changes:
1. At 0x0800C418 replace `bl GUI_MSG_SEND` with `bl ok_gate`. With interrupts off (cpsid i): if the byte is non-zero, drop the OK; if (mode&0xF0) is set, write 4. Then cpsie and post 0x11.
2. In cable_back: if bit0 is set, set bit1 and return to 0x0800D3AA. Otherwise clear the byte and run the existing logic. Put this inside the cable-back patch body (verify.py checks 0x0800D386).
3. Replace the tails at 0x0800CB1C and 0x0800CE7A with `bl tail` + 9 nops. tail reads and clears the byte atomically. If bit1 is set it calls cable_test_enter from the GUI task; otherwise it sets retry = 1 and posts 0x12. It preserves r8 and r6. This also fixes B10.

A stuck bit2 is cleared by Back through cable_back's idle path; B12's recover hook should clear it too. One gap remains: a Back that lands between COUNT posting 0x11 and the GUI starting the test (a few milliseconds).

Pair this with I5.

- *reproduce*: **confirmed** (run) — P2 is justified.
- *refute*: **confirmed** (run) — The bug is real and its consequence is misleading.

### B8 [bug, claimed P2] RX unit mode: a connected shield is drawn OPEN. PN2.19 compares each slot's highest sample with 4000, only 100 counts above the shield's ladder value of 3900

- Sources: far-end-logic: The shield's ladder value 3900 is only 100 counts under the open threshold, patch-code: Far-end open test (PN2.19 hi_slot) can call a connected shield OPEN, electrical-thresholds: Far-end open test has only 100 counts of headroom above the shield's ladder value
- Location: - Far-end OPEN rule 0x0800C5A2..0x0800C5CA: `bl hi_slot` (0x08068ED8) at 0x0800C5A8, then `cmp.w r0,#0xFA0 ; ble` at 0x0800C5AE.
- Shield ladder value T[8] = 3900 at 0x0801E2CA.

**Mechanism.** A row is OPEN when all 8 slots have HI (the max of 11 samples) above 4000. With G driven, every sensed wire reads 3900.

Two things make that look open:
- A hum peak of more than 100 counts in each slot. Each 10 ms window contains a peak, and the slots cycle through only 5 distinct 50 Hz phases.
- A ladder reading about 2.6 % high.

Pin 8 (3679) has 321 counts of headroom.

Stock compared a single sample with 4000. That gave the same margin for static error, but PN2.19's max-of-11 turns hum peaks into a false open. The 4000 threshold itself is sound; the estimator is what fails.

Row 8 is not counted by the LED or by 'Not connected'.

The hum on a connected shield is INFERENCE.

**What the owner sees.** A good shielded (STP) cable in RX unit mode sometimes shows G as red with an X while the LED is green. On a unit whose readings run a few percent high, it happens every time. The number on the 'broken' wire is a normal shield reading such as 3780 or 4007.

UTP cables are unaffected.

**Proposed fix (audit).** Keep 4000 as the level threshold, but decide 'open' by whether the wire touched the rail. Options:
- (a) patch-code rail_open: hi_slot returns HI only when HI >= 4090, and the median otherwise. That is 9 extra instructions, checked in the emulator. A floating wire always clips, because samples 0 and 10 are 180 degrees apart at 50 Hz.
- (b) far-end-logic: open = every slot HI > 4000 AND at least 6 of 8 slots HI >= 4090.
- (c) the B2(B) sampler.

Caveat for all three: a floating wire that sits DC-high between 4001 and 4089 with no hum would no longer count as open. Check that with cable-diag on a long unplugged cable.

Retest on the device with UTP (G must stay open) and STP (G must pass).

- *reproduce*: **confirmed** (run) — P2 is justified.
- *refute*: **refuted** — Not a demonstrated P2 bug. At most a P3 latent margin note.

### B9 [bug, claimed P2] RX unit mode: the number on an open wire is the hum-lowered lowest median (often 3700-3950, next to the shield's 3900), not the value the open rule judged, and the docs say ~3800 means leakage or moisture

- Sources: patch-code: PN2.21 value on an OPEN row in RX-unit mode is not the number the open rule judged, electrical-thresholds: The reading shown on an open wire is set by mains hum, yet the docs present ~3800 as leakage or moisture
- Location: - PN2.21 values_hook 0x08068F98: lowest-median scan 0x08068FAA..0x08068FCA; the RX format '%4d' is chosen at 0x08068FF8.
- The open rule uses HI through hi_slot 0x08068ED8.
- Docs: the sdk/cable_values.py docstring; sdk/README.md; docs/releases/v2.21.md; the PN2.21 and TX-PN2.23 archive READMEs.

**Mechanism.** values_hook always prints the lowest of the row's 8 medians, but OPEN is decided from each slot's highest sample.

With hum A, a floating wire's slot medians sit up to 0.707*A below 4095. The lowest of the 8 lands near 4095 - 0.59..0.67*A on every retry. About 0.4 V peak of hum on a dry unplugged cable therefore shows about 3800-3900, inside the shield's window (3706..4093).

This breaks cable_values.py's own promises ('the number that decided it', '4095 open').

Under the divider model [H], a real leak reading 3800 would need R_leak of about 12.9 x the pull-up.

The open/'Not connected' decisions themselves are correct up to A=1500.

**What the owner sees.** The owner sees 3700-3950 on the red wires of a dry, unplugged cable. Read against the PN2.21 legend (3900 = shield) and the v2.21 note (under 4095 = leakage), that suggests the wire reaches the shield or the cable is wet. The number also changes on every retry.

**Proposed fix (audit).** Firmware: for status-1 rows print the lowest HI of the 8 slots, which is what the open rule judged; this is checked in variant.values_v2. Alternatively print a fixed 'open'. The B2(B) sampler stores 4095 for floating slots automatically. For OK and crossed rows, print the deciding estimate (B2(A) step 4).

Docs: replace the leakage sentence with 'values a few hundred below 4095 on open wires are mains hum; only a steady value well below the rail on every retry suggests leakage', and drop the 3800 example.

- *reproduce*: **confirmed** (run) — P2 is right. This is a display and interpretation problem only. Every run gives the correct status ([1]*9), the correct 'Not connected' message, the correct red wires and the correct LED.
- *refute*: **refuted** — This is not a P2 firmware bug. At most it is P3: a wording problem in the docs and docstring.

### B10 [bug, claimed P3] Back during a running test leaves a stray 'Test Retry' button and a stale retry label; a quick double Back draws garbage as the title (menu_name_table[-2] = the count_queue handle)

- Sources: flow-concurrency: Back during a running test: a stray 'Test Retry' button, a stale retry label, and with Back-Back a garbage title
- Location: - cable_back 0x0806784C / cable_test_enter 0x0800C300.
- Routine tails 0x0800CB22..0x0800CB2E and 0x0800CE80..0x0800CE8C: set retry = 1 and post GUI 0x12 with no context check.
- Button draw: 0x0800C424.
- Title draw 0x0800EE6C: English reads menu_name_table[sysState-4] at 0x0800EEAA..0x0800EEC0; lang 2 calls 0x0800F748.

**Mechanism.** The test keeps running after Back, then sets retry = 1 and posts 0x12 behind the key task's 0x36/0x0F. The button handler has no state check, so 'Test Retry' is painted over the selector, or over Home. retry stays 1, so the next layout says 'Test Retry' instead of 'Test Start'.

With a double Back, GUI 0x36 is dispatched when sysState is 2. It indexes menu_name_table[-2], the word at 0x2000000C, which holds the count_queue handle. gui_blit then draws the queue object's bytes as the title. The memory is readable, so this is momentary garbage, not a crash [H].

**What the owner sees.** After pressing Back during a test, the selector (or Home) shows a leftover 'Test Retry' button, and the next test screen says 'Test Retry' before any test has run. After a quick double Back, garbage characters flash in the title.

**Proposed fix (audit).** Use B7's deferred Back: the tail calls cable_test_enter itself. In the fc_verify.py prototype, D1 and E3 leave the queue as ['0x36','0xf'], with retry 0 and no stray button.

Hardening that also helps other screens: in 0x0800EE6C, skip the title when sysState is outside 4..11.

- *reproduce*: **confirmed** (run) — P3 is right.
- *refute*: **confirmed** (run) — P3 is right. The problem is visual only: no crash, no measurement or status corruption, and nothing is written to persistent storage.

### B11 [bug, claimed P3] RX unit mode, crossed rows: each value is drawn where a different wire lands, in the wrong colour, and hides that wire's end

- Sources: patch-code: RX-unit crossed rows: the value is drawn where a different wire lands, in the wrong colour, and hides that wire's end
- Location: values_hook: y = 62 + 24*r4 at 0x0806904A..0x08069050; colour COLOURS[r4] at 0x08069034..0x0806903A.

**Mechanism.** A crossed wire runs from row r4 on the left to row map[r4] on the right. values_hook still writes row r4's number, in row r4's colour, as an opaque box at x 183..206 of row r4. That is where another wire arrives, so the box covers the last 19-24 px of that wire.

**What the owner sees.** On a crossed pair, right-hand pin 1 shows 2319 (pin 3's value) in pin 1's colour, next to a diagonal whose end is hidden behind the number.

**Proposed fix (audit).** When status[r4] == 3, take y from 62 + 24*map[r4] and keep COLOURS[r4]. This is checked in variant.values_v2.

If two wires land on one row, their numbers overlap; that case is caught by B6.

- *reproduce*: **confirmed** (run) — P3 (display and UX only) is the right grade.
- *refute*: **confirmed** (run) — The mechanism is real, but it is a cosmetic display issue (P3 at most, arguably P4).

### B12 [bug, claimed P3] Low-battery recovery redraws the armed result layout even while the selector is showing; the selector then draws over the wire panel

- Sources: flow-concurrency: Low-battery recovery redraws the armed result layout even when the selector is showing
- Location: - battery_tick 0x0800DD34, recovery branch 0x0800DD5C..0x0800DDA2: in state 4 it posts GUI_MSG_SEND(0x10) whatever 0x20000010 holds.
- The cable GUI handler 0x0800C344 handles 0x10 with no flag check.

**Mechanism.** When a shutdown countdown is cancelled (charger attached, or battery >= 3250 mV), the code always posts 0x10, the armed layout, and ignores the layout bit 0x10.

If the selector was showing, the screen now shows the result layout while the key logic is still on the selector. LEFT or RIGHT then draws the selector boxes over the panel, and the first OK only re-arms.

**What the owner sees.** After a low-battery warning goes away, the selector turns into an empty result screen. LEFT or RIGHT then draws the mode boxes over the wire list, and the first OK does nothing visible.

**Proposed fix (audit).** At 0x0800DDA2 replace `bl GUI_MSG_SEND` with `bl recover`: if (0x20000010 >> 4) == 0, set r0 = 0x0F; then b.w GUI_MSG_SEND. This is prototyped in fc_fix.py.

With B7 in place, recover should also clear a stale bit2 of 0x20000011 when bit0 is clear.

- *reproduce*: **confirmed** (run) — P3 is right. This is a UI state mismatch only: no measurement is wrong, and the next OK or Back puts the screen back in order.
- *refute*: **confirmed** (run) — P3 is correct: this is a real UX bug that can happen, but it is rare and fixes itself.

### B13 [bug, claimed P3] values_hook reads the mode byte twice, after 0.86 s of measurement; a key press in between can change it

- Sources: patch-code: values_hook reads the mode byte twice, after 0.86 s of measurement
- Location: values_hook reads 0x20000010 at 0x08068FE8 and at 0x08069006; call sites are 0x0800CE76 (switch) and 0x0800CB18 (far end).

**Mechanism.** The mode is read from RAM after the whole measurement, but Event_key_task can write it during the test: Back runs 0x0800C300, which stores 0.
- A change before the first read prints RX readings in the switch format.
- A change between the two reads builds '%4d', then overwrites the first digit with a letter.

Each routine already knows its own mode.

flow-concurrency notes that the wrong-format numbers are normally overwritten at once when the selector repaints.

**What the owner sees.** After Back during a test, the result is briefly drawn in the wrong format. A corrupted digit is rare.

**Proposed fix (audit).** Give values_hook two entry points (values_sw: movs r4,#0 / values_rx: movs r4,#1), poke them at 0x0800CE76 and 0x0800CB18, and keep the mode in a stack slot. This is checked in variant.values_v2.

B1's switch-only hook gives the same per-site entry. Pass the mode to release_hook for I1.

- *reproduce*: **confirmed** (run) — The mechanism is confirmed as described. My rating is P3 at most, and P4 (cosmetic) would also be defensible. The user impact is smaller than the claim suggests.
- *refute*: **confirmed** (run) — The mechanism is real, but P3 is too high; I rate it P4 (cosmetic and short-lived, a latent robustness issue).

### B14 [bug, claimed P3] English 'Not connected' and 'Result error!!' sit in a dark 0x2105 box on the 0x31A7 band; Thai has no box

- Sources: patch-code: English 'Not connected' and 'Result error!!' sit in a dark 0x2105 box
- Location: - release_hook gui_blit at 0x08068F2C..0x08068F3E.
- Stock 'Result error!!' at 0x0800CAD6 and 0x0800CE30.
- BG 0x200001AE was last set to 0x2105 by the frame draw at 0x0800D17A..0x0800D188.

**Mechanism.** The English glyph drawer paints background pixels with BG, which still holds 0x2105 from the frame draw. The Thai wrapper draws transparently.

**What the owner sees.** In English only, a dark rectangle appears behind the red message.

**Proposed fix (audit).** In frame_hook, after the band fill, store 0x31A7 to 0x200001AE. Nothing else between frame_hook and values_hook uses BG.

- *reproduce*: **confirmed** (run) — P3, cosmetic only, confirmed.
- *refute*: **confirmed** (run) — P3 cosmetic (or lower). This is not a functional defect.

### B15 [bug, claimed P3] The wire's last pixel (x 207) shows as a dot after every value

- Sources: patch-code: The wire's last pixel (x 207) shows as a dot after every value
- Location: values_hook 0x08069056: movs r0,#0xCF ; subs r0,r0,r2 (x = 207 - width).

**Mechanism.** Wires end at x 207 inclusive, but the value box covers 207-6*len .. 206, so one pixel of the wire shows.

**What the owner sees.** A small coloured dot sits between every number and its pin label.

**Proposed fix (audit).** Use x = 208 - width, which leaves a 4 px gap to the label at x 212. Checked in variant.values_v2.

- *reproduce*: **confirmed** (run) — P3, cosmetic only.
- *refute*: **confirmed** (run) — The bug is real but only cosmetic. P3 is fine, and P4 would also be fair. It is an off-by-one in PN2.21's text placement: one pixel in the wire's colour stays visible after the value on rows where a wire ends at x 207. Measurements, status, the LED, the beep and the messages are all unaffected. The owner has used PN2.21 through PN2.27A on the device without noticing it.

### I1 [improvement, claimed P2] The wrong far-end mode gives a wrong result with no hint, and the mode resets to Switch on every entry and Back and is never shown on the result screen

- Sources: switch-logic: RX unit plugged in with Switch selected shows 'Not connected', patch-code: Wrong mode gives a false 'Not connected' or four false shorts, with no hint, professional-gap: Wrong far-end type gives a wrong result with no hint; the mode resets to Switch on every entry, flow-concurrency: The mode is reset to Switch on every entry/Back and never shown on the result screen
- Location: - release_hook 0x08068F00..0x08068F54.
- cable_test_enter 0x0800C300 (0x0800C30E `strb r0,[r1]` with r0 = 0), also reached from cable_back 0x08067854.
- Armed layout 0x0800C328: no mode text.
- Selector 0x0800CF00: highlights only when the byte is exactly 0 or 1.

**Mechanism.** Both routines measure identically. The mode only picks how the readings are classified, and the user has to choose it.
- RX unit plugged in, Switch mode selected: the ladder values (1655..3900) are all above 1240, so every row is open and the unit shows 'Not connected' with a red LED and a double beep.
- Switch plugged in, RX unit mode selected: every signal row reads its pair partner, so the unit shows four yellow shorts with a red LED and a double beep.

Every entry and Back writes 0 (Switch), and the result layout never shows the mode.

**What the owner sees.** The owner plugs into the RX unit, enters Cable Test (Switch is preselected), and sees nine red wires with 'Not connected'. RIGHT has to be pressed after every Back. A switch tested in RX unit mode shows four shorts on a good cable.

**Proposed fix (audit).** Stage 1: text hints only, with the mode passed in from the call site (B13).
- Switch mode, all 8 signal rows open, and the readings match the ladder signature: print 'RX unit found - use RX unit mode' / 'พบเครื่องรับ'. Three signatures were proposed:
  - switch-logic: each row's medians within +-5 % of one another and of a ladder value;
  - patch-code: at least 6 rows inside their own +-5 % window;
  - professional-gap: every HI <= 4000 and every median in 1242..3999. Floating wires still give 'No far end found'.
- RX unit mode, all 8 signal rows SHORT with map[i] == 1<<partner(i): print 'Switch port found - use Switch mode' / 'พบสวิตช์'.

Stage 2 (needs the owner's approval):
- On entry and Back, use mode &= 0x0F instead of writing 0; the selector highlight still works.
- Draw the mode name on the result layout.
- Optionally pick the mode automatically.

- *value*: **confirmed** (run) — P2 is right. The RX-unit half is worth doing now; the switch half and Stage 2 are not urgent.
- *feasibility*: **confirmed** (run) — P2 is right. The unit gives a confidently wrong verdict on a good cable: nine red wires, "Not connected", red LED and double beep for an RX unit in Switch mode, or four yellow shorts for a switch in RX mode. Nothing on screen says the mode is wrong, and the mode is not shown anywhere. Entry and Back reset the mode to Switch every time, so an owner who uses the RX unit hits this after every Back. Measurement and data are not at risk. The fix is display-only and can be tested in the emulator.

### I2 [improvement, claimed P2] No PoE or external-voltage check before the wire map drives the RJ45 pins, although poe_mv is measured every 10 ms on this screen

- Sources: switch-logic: No PoE or foreign-voltage check before the wire map drives the RJ45 pins, flow-concurrency: No PoE check before the wire map drives the mux (hardware inference), electrical-thresholds: No check for PoE or other external voltage on the pairs, professional-gap: No PoE / voltage check before the wire map
- Location: - GUI Cable handler 0x0800C366: `bl 0x0800C4E0` at 0x0800C37A, `bl 0x0800CB68` at 0x0800C380.
- frame_hook 0x08068F74.
- poe_state_machine 0x08019F00 -> poe_measure_mv 0x08019CDC -> poe_mv at 0x200000C0.
- Stock threshold: 0x08019F38 `cmp.w r0,#0x7D0` (2000 mV).

**Mechanism.** poe_measure_mv reads ADC channels 0..3 (the pair voltages) and stores the spread in mV. It is posted every 10 ms in every state except OFF/BOOT (0x0801BD1C..0x0801BD32 and 0x080684BC..0x080684CA), so poe_mv is always fresh on this screen. No cable-test code reads it.

The wire map therefore drives the mux into a line carrying passive PoE or a PSE detection pulse, with no warning. Stock even recognises non-standard PoE (strings at 0x0801A58F / 0x0801A5E8).

INFERENCE (no schematic): whether the PoE divider sees the same pins, and what 24-57 V does to the front end.

**What the owner sees.** On a PoE switch port or a passive-PoE injector, the tester shows a meaningless wire map with no hint that the line is powered. The front end may be stressed [inference].

**Proposed fix (audit).** Point the two bl sites at a pre_test hook, or check in frame_hook before any mux select:
1. Read poe_mv, or compute a fresh spread of adc_read(0..3).
2. At or above the threshold: select no mux, print red 'PoE / voltage on cable - unplug' / 'ไฟ PoE ถอดสาย' with the voltage, call rgb_led(1), clear 0x20000011, set 0x20000012 = 1, and post 0x12.
3. Otherwise call the selected routine.

The proposed thresholds differ: 2000 mV (switch-logic and electrical-thresholds, the stock value), 10000 mV (professional-gap), about 20000 mV (flow-concurrency). Set it on the device after measuring poe_mv idle on a plain port and on a PoE port.

The same hook can latch the mode (B13) and set the busy flag (B7).

- *value*: **uncertain** (run) — The premise is true, but P2 overstates it: this is a P3 usability improvement, not a bug.
- *feasibility*: **confirmed** (run) — P2 is right. This is an improvement, not a defect in the firmware.

### I3 [improvement, claimed P2] No verdict line: fault types are never named. A crossover or reversed pair is an unnamed failure, two separate shorts can look like one, and the text line is empty on pass and on most fails

- Sources: professional-gap: No verdict line: faults are never named, far-end-logic: A crossover cable is correctly mapped but reported as an unnamed failure, professional-gap: RX-unit mode reports a standard crossover cable as four (or eight) crossed faults
- Location: - Text band x 40..200, y 271..286, wiped by frame_hook 0x08068F74.
- Only 'Result error!!' (0x0800CAD6 / 0x0800CE30) and 'Not connected' (release_hook) ever write it.
- LED/beep: 0x0800CB00..0x0800CB16 (far end) and 0x0800CE5C..0x0800CE72 (switch).
- Far-end nearest rule: 0x0800C684..0x0800C704.

**Mechanism.** The only verdict is the LED. 'Result error!!' is practically unreachable. Everything else has to be read from the line drawing, and several drawings are ambiguous:
- RX unit mode maps a T568A<->B crossover exactly (plus 4->7, 5->8 for gigabit) and a reversed 1<->2 pair, but each row is judged alone: diagonals, a red LED, no name.
- In RX unit mode, the 1-3 short bus crosses wire 2, so shorts 1-3 + 4-5 look like a 1-2-3 short.
- In Switch mode a crossover is drawn as straight green lines.
- In Switch mode with one broken wire, the pair-only model shows both wires red. Ports with a Bob-Smith network keep the partner green instead (see I7).

Everything a verdict needs is already in RAM when values_hook runs.

**What the owner sees.** A good crossover cable gets a red LED, a double beep and four crossing lines with no name. Two separate shorts look like one. In Switch mode, green straight lines suggest that the wire order was checked.

**Proposed fix (audit).** Add a verdict writer to values_hook (per-site entries, B13). It draws after the stock result and changes no status, drawing or LED. Priority: PoE > short > open > miswire/crossover > pass.

Far end:
- 'Crossover 10/100' / 'สายครอส 10/100'
- 'Crossover Gigabit'
- 'Reversed pair 1-2' / 'สลับสาย 1-2'
- 'Miswire 2>3 3>2'
- 'Short 1-3 4-5' / 'ลัดวงจร 1-3'
- 'Open 4 7' / 'สายขาด 4'
- 'Straight OK' (+ ' (no G)') / 'สายตรง ปกติ'
- 'No far end found' / 'ไม่พบปลายสาย'

Switch:
- 'Pairs OK' (never 'Straight')
- 'Open pair 45'
- plus B1's miswire and short texts

Thai text: draw an existing-cluster word, then ASCII pin numbers with gui_blit.

Keep the red LED for a crossover; whether it turns amber is the owner's choice. Estimated size: 0.5-1 KB.

- *value*: **confirmed** (run) — Worth doing, but P3 rather than P2. It is a usability improvement, not a wrong result. Every decision is already drawn: red X for open, yellow bus for short, diagonals for crossed. PN2.21 also prints each wire's value, which the owner liked.
- *feasibility*: **confirmed** (run) — P2 improvement, feasible at low risk.

### I4 [improvement, claimed P2] A 10/100 port that leaves pins 4, 5, 7 and 8 unterminated gives a hard FAIL on a good cable

- Sources: switch-logic: A 10/100 port that leaves pins 4,5,7,8 unterminated gives a hard FAIL on a good cable
- Location: - 0x0800CBFC: a row is open when nothing reads <= 1240.
- 0x0800CCC4: open rows are drawn red with an X and set the fault flag.
- 0x0800CE5C..0x0800CE6A: LED and beep.

**Mechanism.** Open rows set the fault flag. Some 10/100 devices do not terminate the unused pairs [H; how common is unknown], so a perfect cable shows four red wires and a double beep. Both wires of a pair being open while the other pairs are correctly joined is a recognisable pattern.

**What the owner sees.** A good cable tested against a 10/100 port fails with rows 4, 5, 7 and 8 red and a double beep. The owner may throw away a good cable.

**Proposed fix (audit).** When whole pairs are open while at least two pairs are joined correctly: keep them red, but print 'Pairs 4-5 7-8: no path (10/100 port or open pair)'. Consider a single beep or an amber state. The message can point to the SPEED screen's partner row (PN2.17).

- *value*: **uncertain** (run) — Downgrade from P2 to P3 (UX hint only).
- *feasibility*: **confirmed** (run) — P2 improvement is right. Keep it a hint, not a pass.

### I5 [improvement, claimed P3] A test shows no busy indication for about 0.8 s: the panel is blank, the button still says 'Test Retry', and the LED keeps the old result, which invites the key presses behind B7 and B10

- Sources: flow-concurrency: A test shows no busy indication for 0.79-0.86 s and the LED keeps the previous result, patch-code: About 0.86 s blank frame during the test, no progress shown
- Location: - PN2.19 sample 0x08068E70 (`cmp r7,#0xb` at 0x08068E9A).
- vTaskDelay(2) at 0x0800C53E and 0x0800CBC4.
- frame_hook 0x08068F74.
- rgb_led 0x08010F94, called only at the end of the test.
- 0x20000011 is never read.

**Mechanism.** 72 samples x (vTaskDelay(2) + 10 x vTaskDelay(1)) = 864 ticks at 1 ms. The tick setting is SysTick LOAD 0x2327F at 0x0801C744, on a 144 MHz core.

That is about 0.79-0.86 s, against 72-144 ms in stock. frame_hook wipes the wires first, and nothing shows that a test is running.

**What the owner sees.** After Test Retry the wire list is blank for almost a second, and the old button and LED stay. It looks as if the press was ignored, so the owner presses again, or presses Back.

**Proposed fix (audit).** In frame_hook, after the band wipe:
- draw 'Testing...' in the band, or redraw the button face (record 0x0801E320) with the existing 'Testing' string (0x0800D898);
- call rgb_led(3), the idle blue set at 0x0800F51E.

The tail's 0x12 restores the button. Wipe the band again before the result message.

Do not shorten the sampling. The drop-OK-while-busy part of the fix is in B7.

- *value*: **confirmed** (run) — P3 is correct: a UX improvement, not a defect.
- *feasibility*: **confirmed** (run) — P3 UX improvement: the fix is feasible, cheap and low risk. The problem is real in firmware. A PN2.19+ test blocks the GUI task for 864 ticks, about 0.86 s at the 1 ms tick. During that time the only visible change is the blank frame; the old "Test Start"/"Test Retry" label and the previous red/green LED stay. That invites the repeat OK / Back presses behind B7 and B10.

### I6 [improvement, claimed P3] The test harness cannot reproduce correlated mains hum or ladder gain error, so the existing 22 tests cannot catch B2, B5, B6 or B8

- Sources: far-end-logic: The test harness cannot reproduce hum or ladder-error effects, electrical-thresholds: RX unit mode: a floating wire's slot is averaged into the crossing decision (test recommendation)
- Location: sdk/test_cable_test.py, Harness and far_end() (lines 38-86): hum only on readings >= 4000, independent uniform noise per sample, no clock, noise-free ladder readings.

**Mechanism.** The Harness's delay hook discards time, and its hum is independent noise on floating wires only. Real hum is a sine that is correlated across the 1 ms samples and rides on ladder wires too. Gain error cannot be simulated.

**What the owner sees.** None directly. Classification regressions under realistic conditions would reach the device untested.

**Proposed fix (audit).** Extend the Harness:
- the delay hook advances a clock;
- reading(d, s, k, t) adds a 50/60 Hz sine with a phase, scaled by T/4095 on ladder wires and clipped on floating ones;
- add a gain `scale`, and the kinds swap67, stp, leaky(L), broken+crossover, partial-short and reversed-pair-with-humming-G.

Assert:
- 6<->7 at A=100 reads '6->7 7->6';
- STP at +2.75 % and at A=200 reads G ok;
- leaky L=3900 produces no map;
- a crossover with a broken wire keeps the correct crossings;
- the 22 existing tests stay green.

- *value*: **confirmed** (run) — P3 is right. This only changes the tests: no firmware byte changes, so behaviour the owner confirmed on the device cannot change. The owner sees no symptom from the gap itself.
- *feasibility*: **confirmed** (run) — P3 is right, since this changes only test infrastructure. It changes no firmware byte and needs no flash cave, RAM arena, screen space or Thai glyphs. Its value is high, though: it is the only way to gate the B2, B5, B6 and B8 fixes in CI.

### I7 [improvement, claimed P3] On ports with centre-tap/Bob-Smith DC paths, one broken wire leaves its partner green with a letter for an unrelated pin; the docs and tests assume both wires go red

- Sources: switch-logic: On ports with centre-tap/Bob-Smith DC paths, one broken wire leaves its partner green
- Location: - values_hook 0x08068FD2..0x08068FE4: the letter is the lowest median at or below 1240, with no level check.
- sdk/test_cable_test.py far_end('switch-open3').
- experimental/TX-PN2.19-CABLE-README.txt.

**Mechanism.** Gigabit magnetics, and some 10/100 ports, join the pairs' centre taps through 75 ohm, so pins in different pairs see about 150 ohm [H]. When wire 3 is broken, row 6 stays green and shows the letter of the first minimum, e.g. '1 121'. Only the pair-only SDK model expects row 6 to go red.

**What the owner sees.** Wire 3 is red, but wire 6 is green and labelled '1 121', which suggests a miswire to pin 1.

**Proposed fix (audit).** Print '-' when the lowest median is well above this test's direct level, and mark the row 'no pair partner'. State the assumption in the README and the tests. Confirm with a full-matrix capture on a gigabit switch.

- *value*: **uncertain** (run) — P3 (low), and possibly lower. The gap only appears with a damaged cable in a switch port whose pairs are joined through a DC path. What the owner acts on stays right: wire 3 is red with the X, the LED is red and the tester double-beeps. Wire 6 staying green is physically correct, because wire 6 is intact; the pair-only model's "both red" is the less accurate answer. The only defect is row 6's text, e.g. '1 121', which can read like a miswire. Its letter also changes between Test Retries (1, 8, 4, 2, 7 in 10 noisy runs), a small echo of the randomness complaint that led to PN 2.19, but only on a cable that is already failing. It never changes a good-cable result. The docs and tests state as fact something that has not been measured, so correcting them is worth doing now at no risk. The firmware change is not worth doing before a hardware measurement, and the rule as proposed would break the owner-liked PN 2.21 poor-contact reading.
- *feasibility*: **confirmed** (run) — P3 is right.

### I8 [improvement, claimed P3] In RX unit mode the per-wire number is a raw ADC count that names no pin, and the two modes use different formats

- Sources: professional-gap: Per-wire numbers use different formats in the two modes, and the RX-mode number is a raw ADC count
- Location: values_hook 0x08068F98 (fmt_switch '? %4d', fmt_rx '%4d').

**Mechanism.** Switch mode prints the partner pin and the count. RX unit mode prints only the lowest median, which the user has to map to a pin through the ladder table, and that value is not always the one that decided the row (B2, B9).

**What the owner sees.** In RX unit mode the numbers mean nothing without the ladder table, and the two modes read differently.

**Proposed fix (audit).** Use '? %4d' in RX unit mode too, with the letter taken from the decision: own pin for status 2, map[d] for status 3, '*' for status 0, '-' for status 1. Keep the count, printing the deciding value per B2(A) step 4 and B9. It fits the same 36 px box.

- *value*: **confirmed** (run) — P3: display only. Worth doing, but only inside the release that already rewrites values_hook for B2/B9. It is not worth a release on its own.
- *feasibility*: **confirmed** (run) — The finding is accurate: P3, a UX improvement with low risk.

### I9 [improvement, claimed P3] English 'Not connected' is ambiguous, and it is also shown when the RX unit is connected

- Sources: professional-gap: English 'Not connected' is ambiguous
- Location: release_hook 0x08068F00 (cable_test.py NOT_CONNECTED_EN, gui_blit(68,271,104,16)).

**Mechanism.** The English text does not say what is not connected. The Thai 'ไม่พบปลายสาย' means 'far end not found', which is the actual condition.

**What the owner sees.** 'Not connected' with a cable plugged in at both ends reads like a tester fault.

**Proposed fix (audit).** Change the English to 'No far end found' (16 characters, gui_blit(56,271,128,16)). Keep the Thai. Combine with I1's hint.

- *value*: **refuted** (run) — This is P4 cosmetic, not P3. It is an English-only wording change, and the owner reads the Thai UI. The Thai text already says what the proposed English would say ("far end not found"). The user symptom quoted in the finding, "Not connected" with both ends plugged, is the wrong-mode case. The rename leaves that case unchanged in both languages; only I1's ladder-window hint addresses it. The change carries no risk to behaviour the owner has confirmed, because the Thai drawing is pixel-identical and the measurement and status are untouched. It also gives the owner no value.
- *feasibility*: **confirmed** (run) — P3, a user-experience wording change. The measurement, status codes, LED and beep are unchanged. The text appears only when all 8 signal rows are OPEN. The finding's claim holds in the emulator: pn2.27a prints the ambiguous "Not connected" when nothing is attached, and also when the RX unit is plugged in with Switch mode selected. The proposed wording alone ("No far end found") makes that second case read as a false statement, so the fix should name the mode (Variant B) or ship together with I1. Risk is low: it touches only same-length pokes inside PN code (release_hook), adds cave code, uses no RAM, and changes no timing measurably (3 extra 8x16 glyphs).

### I10 [improvement, claimed P3] The cable docstrings and FORMULA-AUDIT section 4.1 are wrong in several places: task, mode bit, frame-draw arguments, 'the number that decided it', and the floating-wire median

- Sources: patch-code: Docstrings in the cable patch modules are wrong in several places, flow-concurrency: Docs name the wrong task for the wire map, far-end-logic: (docstring sentence on the floating-wire median, from the broken-wire average finding)
- Location: - sdk/cable_test.py lines 3-4.
- sdk/cable_values.py (line 42 and docstring).
- sdk/cable_clear.py line 27.
- FORMULA-AUDIT.md around line 417.

**Mechanism.** - The wire map runs in APP_GUI_task (GUI 0x11 -> 0x0800C344), not in the CNT task.
- 0x10 means 'layout armed', not 'test started'.
- FRAME_DRAW 0x0800D170 takes no arguments.
- 'The number that decided it' does not hold (B9, B2).
- The claim that a floating wire's median is at the rail is false (B5).

Checked and found correct (flow-concurrency, patch-code):
- no concurrent LCD access;
- the mux is always released;
- auto-off (300 s minimum) cannot hit a test;
- LEFT/RIGHT are ignored during a test;
- r4/r5 are correct at every call site;
- a 3000-vector sort fuzz shows 0 mismatches;
- SP is 8-byte aligned;
- arena allocations do not overlap.

**What the owner sees.** None on the device. The wrong docs misled this audit and would mislead the next change.

**Proposed fix (audit).** Correct the docstrings and FORMULA-AUDIT section 4.1:
- the GUI task, message 0x11;
- 0x10 = layout armed;
- the frame draw takes no arguments;
- the test takes 864 ticks at 1 ms;
- 0x20000011 is the running flag;
- the median of a floating wire under hum.

Once the value fixes land, restate what the number means. The leakage wording is covered in B9.

- *value*: **confirmed** (run) — P3, documentation only.
- *feasibility*: **confirmed** (run) — P3, documentation only, but worth doing. There is no device symptom: the image is byte-identical before and after the change (sha c12b127a in both). The wrong statements are all real, and two of them matter more than cosmetics:

### I11 [improvement, claimed P3] True split pairs cannot be detected in either mode (DC matrix only), so a split-pair cable passes; the wording should not claim more

- Sources: professional-gap: Split pairs are undetectable in both modes, switch-logic: (split-pair limitation note in the crossed-wire finding)
- Location: Both wire-map routines (DC readings on ADC channel 4).

**Mechanism.** In a true split pair the wires run pin to pin with the wrong twisting, so the DC matrix is identical to a straight cable. Detection needs crosstalk measurement.

The 'split pair' cases in B1 are cross-pair miswires, which DC can detect.

**What the owner sees.** A split-pair cable, which gives errors or no gigabit link, shows as perfect.

**Proposed fix (audit).** Be honest in the wording: Switch mode says 'Pairs OK', never 'Straight'. Note the limit in the release notes, and point to the SPEED screen, which shows a gigabit port linking at 100M.

- *value*: **refuted** (run) — P3 at most, and only for documentation. As a firmware change it is not worth doing now.
- *feasibility*: **confirmed** (run) — P3 improvement, confirmed feasible. The physics claim is right: a DC wire map cannot see a true split pair. Emulation shows a split pair gives the same screen as a straight cable in both modes, byte for byte, with a green LED.

### I12 [improvement, claimed P3] The PN2.19 LO (minimum sample) table is written 72 times per test and never read

- Sources: patch-code: The PN2.19 LO table is written 72 times per test and never read
- Location: - sample 0x08068EB4..0x08068EBA (LO store).
- Arena 0x2000F1D4..0x2000F263 (144 B).

**Mechanism.** No code reads LO. values_hook and cable-diag read MED and HI; hi_slot reads HI.

**What the owner sees.** None. It wastes RAM and cycles.

**Proposed fix (audit).** Either drop it, or use the HI-LO spread as a flag for unstable contacts (the threshold needs device data). B2(A) proposes a new MEAN table rather than reusing LO.

- *value*: **refuted** (run) — P3 at most, and not worth a release. The owner sees no symptom, and the premise is only "wasted RAM and cycles".
- *feasibility*: **confirmed** (run) — The claim is confirmed: the LO table is written 72 times per test and nothing reads it, in firmware or in the SDK's image code. It should stay at P3 or lower, because it has no user symptom and almost no cost:

### I13 [improvement, claimed P3] No distance to fault on the wire map; the PHY's per-pair CSD status bits are unused

- Sources: professional-gap: Distance to fault is not available on the wire map
- Location: - APP_LENG_Test_Sequence 0x080119EC (only caller 0x0801491A).
- CSD status ext reg 0x84.
- Mux 0x080180A0 / release 0x08018C3C.

**Mechanism.** Opens are reported without a distance. The YT8531 CSD reports per-pair distance, but the firmware reads ext reg 0x84 only for bit 15. Combining CSD with the wire map would mean cross-task work and powering the PHY. Whether the two share a jack is unknown [H].

**What the owner sees.** An open wire gives no distance; the owner has to switch to the Length screen.

**Proposed fix (audit).** First do TX-NEXT-STEPS item 3: dump ext 0x84..0x8A. Then add open/short labels on the Length screen, and on the wire map only a pointer: 'Open: see Length'.

- *value*: **uncertain** (run) — This is P3 or lower and is not a cable-tester bug. The wire map reports what it can with a DC resistance test, and no confirmed behaviour is wrong.
- *feasibility*: **confirmed** (run) — P3 improvement, correctly rated. It is not a defect. The distance to an open is already measurable: a cut pair keeps its own value through the four-pair vote and the average, and the Length screen shows it ("3-6 = 4.5 m", emulated). What is missing on the wire map is only a hint to go there.

### I14 [improvement, claimed P3] Starting a test takes two OK presses: the first only draws an empty frame

- Sources: professional-gap: Starting a test takes two OK presses
- Location: GUI Cable handler 0x0800C344, msg 0x11 path 0x0800C386..0x0800C398.

**Mechanism.** On the selector, OK only sets the 0x10 bit and posts 0x10, which draws an empty frame. The test needs a second OK.

**What the owner sees.** After choosing a mode, the owner sees an empty frame and has to press OK again.

**Proposed fix (audit).** Optional: after posting 0x10, also post 0x11. This changes a flow the owner is used to, so offer it as a candidate only, and combine it with B7's busy flag.

- *value*: **refuted** (run) — Not a defect. It is a UX preference inherited unchanged from stock V2.0.7, and P3 at most. Its only benefit is one key press per cable session; each retry is already a single press.
- *feasibility*: **confirmed** (run) — P3 improvement, and feasible. It saves one key press, and the owner no longer sees an idle empty frame. The measurement code and the result screens do not change: final screens are pixel-identical in English and Thai.

## Dropped during triage


## Completeness critic

**Completeness critic: gaps in the Cable Test audit (pn2.27a)**

I built every image in memory. Scripts and outputs are in `C:\Users\Alpha\AppData\Local\Temp\claude\C--Users-Alpha-Documents-GitHub-LPM-10A-Firmware\8df87b21-94fd-403b-a806-022f84e36051\scratchpad\cable-audit\completeness\`. The repo was not changed and `git status --short` is empty. My first run saved its PNGs into `verify-B7\`, because `b7_repro` also defines `HERE`. I moved them into my folder and fixed the script.

### Checked in the emulator or disassembly

**NEW-1 (bug, P2, the most important gap).** A queued OK can run a full wire-map test after the user has left Cable Test. That test then covers the new screen with the Cable Test layout while the new screen's keys stay active.
- B7 and B10 only showed OK replaying inside state 4 and the drawing after a double Back. Nobody checked for a measurement running in another state.
- Command: `python -B n2_realistic.py` (exit 1, output in `n2_realistic.out`). It reuses verify-B7's `Dev`, which runs the real key dispatcher, the COUNT handler and the GUI dispatcher.
- Key timing is realistic:
  - three OK presses during test 1, which takes 0.86 s;
  - then BACK and BACK during the first queued test.
- What happens on pn2.27a:
  - Queue after test 2: `['0x11','0x11','0x12','0x36','0xf','0x2','0x12']`.
  - The first 0x11 arms again.
  - The second 0x11 runs `('switch', sysState 2, '0x10')`: 81 mux selects, 792 ADC reads, 864 ticks, with the Home screen active.
  - It gives "Not connected" (Switch mode on an RX cable), rgb_led 1 (red) and a double beep.
  - The final screen is the armed Cable Test layout with no title and "Test Retry". The device is in `sysState 2`, so Home's keys are live (`n2_pn2.27a_home.png`).
- Same run, adding RIGHT and OK on Home: the device enters SPEED (`sysState 9`) and the queued test runs there, `('switch', 9, '0x10')`. The SPEED screen ends up hidden under a Cable Test layout titled "SPEED" (`n2_pn2.27a_speed.png`).
- Stock does the same: two queued far-end tests run in state 2 with 162 selects. On stock the window is 0.144 s, so three presses do not fit into it in practice. On PN it is 0.86 s per test, so they do.
- Fix implication:
  - B7's busy check on COUNT msg 2 is not enough on its own. The screen can still be abandoned while more tests are queued, and B12's 0x10 is still posted.
  - The handler at 0x0800C344 needs a `sysState == 4` guard for 0x10, 0x11 and 0x12. This is the map's D6, which should be raised from "low".
  - Whether the mux driving the jack disturbs SPEED, Length or PoE is an inference about hardware.

**NEW-2 (checked; the premise holds).** The ADC runs continuous scan into a circular DMA buffer, so the 11 samples really are separate conversions.
- The init at 0x0801B6C8 is called from `APP_HOME_task` at 0x0800F8D0:
  - DMA ch1 (0x40020008): source 0x4002084C, destination 0x20000C68, 5 halfwords, circular (0x20), high priority.
  - `ADC_Init` sets scan = 1 and continuous = 1 (CR2 bit 1, at 0x0800B9EA), with software trigger 0xE0000.
  - Ranks are ch7, ch1, ch2, ch11, ch4, with sample-time code 5.
  - It starts with 0x0800B974 (`CR2 |= 0x500000`).
- The ADC base is 0x40020800, not the STM32F1 ADC1 address, so this is an F1-compatible clone.
- The hum analyses assumed each `adc_read` returns a fresh reading; that is correct.
- Not examined (inference about hardware): charge carried on the ADC's sampling capacitor from ch11, the rank scanned just before ch4, when the source impedance is high.

**NEW-3 (checked; nothing wrong).**
- The MED/LO/HI tables at 0x2000F144..F2F3 overlap none of the 18 pn2.27a arena allocations; the arena ends at 0x2000F364.
- The initial MSP is 0x2000E888, below the arena.
- PendSV at 0x0800A2E8 saves and restores s16–s31 (`vstmdbeq`/`vldmiaeq`). Rule 3's `vcvt` float code in the GUI task is therefore safe from preemption.

### Not examined or not verified (no new evidence)

- **G1. The mode selector screen (0x0800CF00).** Only its highlight rule was mapped. Nobody checked in either language:
  - whether the labels and icons fit their boxes;
  - that the selector is drawn with no box highlighted whenever the mode byte is 0x10 or 0x11. This does happen in the B7 and NEW-1 drains.
- **G2. The fixes were each prototyped alone, but they touch the same code.**
  - I1, I3, I4, I7 and I8 each patch `values_hook` or the release sites 0x0800CB18 / 0x0800CE76. I5 changes `frame_hook`.
  - Their cave use adds up to about 3.2 KB (I3 1572 + I1 596 + I8 436 + I4 330 + I7 224), against 2664 B free. This needs another 4 KB extend, and about 80 KB of headroom exists.
  - A merged build was never tested.
- **G3. No readings from the real device.** The existing `cable-diag` experiment (`cable_test.py` DIAG_ID) prints, for each row, the lowest median, its pin and that pin's highest sample. It could settle the refuted or uncertain items: B2 and B8 (hum and ladder gain), B9, I4 (unterminated 10/100 pairs) and I7 (cross-pair DC paths). All of these rest on modelled hum, gain or port values.
- **G4. PoE switch ports in Switch mode.** Nobody examined what the PSE's detection pulses (about 2.8–10 V) on the pairs do during the 0.86 s test. I2 only covers a line that is already powered.
- **G5. Other screens and the port hardware.** The tone carrier is ruled out: the TIM2 IRQ only drives it when enabled and sysState == 5, which `test_tone_pn226_lifecycle.py` covers. Nothing was checked about the mux being active while the PHY is in use, which NEW-1 shows can happen. Whether the mux and the PHY share conductors is unknown without a schematic.
- **G6. Languages.** The settings byte is `language 1=Chinese(→Thai slot) 2=English` (symbols.py 0xA5). The audit labelled emulator runs "lang 1 = English" in some scripts and "lang 2" in others. Whether the verifiers consistently exercised the real Thai path of `release_hook` and `values_hook` (the `LANG_IS(2)` branch) was not cross-checked.
- **G7. Tests.** The repo suite still has no test for the key and task interplay (B7, B10, NEW-1), and no test that runs the plain pn2.27a release through the cable routine (I6).
- **G8. Hardware inference that remains.** Mux settling (1–2 ms before the first sample) and the tester's own magnetics and isolation path are inferred, not shown. No schematic is available.
