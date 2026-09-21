# TX — what is left to improve after PN 2.14 (assessed 2026-09-21)

Starting point: TX PN 2.14 in daily use on the owner's unit; length, calibration, battery, FLASH,
PoE, Thai UI and the reliability plumbing all hardware-confirmed (README, `FORMULA-AUDIT.md`).
The sister document for the probe is [RX-NEXT-STEPS-2026-09-21.md](RX-NEXT-STEPS-2026-09-21.md).
Ranking is value ÷ effort, on what the code and the hardware record actually show. Space is not
a constraint: 1.7 KB left in the current cave page and about 92 KB before the boot-flag page.

| # | Item | Value | Effort / risk | Gate |
|---|---|---|---|---|
| 1 | Build tooling: one profile table, the current release as the default build | every future TX change goes through it | small / none | — |
| 2 | Known-length calibration on the Length screen | industrial testers have it; today NVP is trimmed ±1 % per press with a four-run test between tries | medium / low | — |
| 3 | Per-pair fault type ("open 12.3 m" / "short 3.1 m") from the YT8531 CSD status | the last thing separating the Length screen from a real TDR tester | small for the register dump, medium for the feature / display-only | hardware: dump ext regs 0x84–0x8A with a good open-ended cable, a shorted pair and a cut pair |
| 4 | Length test time: a run counter (or early stop when runs agree) | the four-run test takes ~4× stock; the wait was unexplained | small / low | — |
| 5 | About screen: battery mV, NVP, Zero | three text lines, diagnostic value (ROADMAP §3.5) | tiny / none | — |
| 6 | Settings A/B page | saves are single-page and not power-fail atomic; autosave writes more often since PN 2.9; a torn write costs the calibration, not the unit | medium / moderate | low priority |
| 7 | SPEED: what the switch port offers, next to what the link got | stock prints the resolved speed / duplex only; the partner's advertised speeds (IEEE registers 5 and 10) tell a cable fault (100 Mbps on a gigabit port) from a port limit — the row every professional link tester has | small / low, display only | — |
| 8 | Cable Test on an unconnected cable (owner report 2026-09-21: random open / crossed wires in both modes) | one ADC sample per sensed pin against a threshold 77 mV under the rail, no "nothing connected" state; the wire map is the one function whose result the owner cannot trust on a bad day | small / low: sampling and one threshold, the routines' logic kept | the owner's four measurements with the diag build confirm the numbers |

## Status (2026-09-21)

| # | Result |
|---|---|
| 1 | **Done.** `sdk/profiles.py` lists every PN version as its parent plus one module, with its output file and hardware record; `python build.py --write` emits the latest profile, `--profile pn2.12` (or the old alias flags) reproduces an earlier one, `--default` builds the frozen baseline that `verify.py` models. `test_profiles.py` rebuilds every image in memory and compares it with the published digest (baseline `f9d8cbfe…`, PN 2.9 `2a82c86d…` … PN 2.14 `a7402de6…`, PN 2.15 … 2.18), all byte-exact. The nine patches that have run on the unit since PN 2.12/2.14 are labelled `low` instead of `untested`; the profile record says what the owner confirmed. `verify.py` finds the archived baseline again (the folder reorganisation had moved it). 234 sdk tests pass. |
| 2 | **Done as PN 2.18** (`length-reference`, `experimental/LPM-10A-TX_PN2.18-length-reference.bin`, sha256 `b5538e72…`): holding OK now cycles NVP → ZERO → **REF** (offered only with a result on screen); REF shows the measured length, UP / DOWN dial it to the cable's true length and every step solves `NVP = 69 × REF / (raw − 10 × Zero)` from the mean of the timed pairs (rounded, 50..99 %), stores it and redraws the readings. Zero stays a separate step (short cable first). Driven end to end through the real `Action_key_Process`, GUI message 0x3D and the draw code under Unicorn (`test_length_reference.py`, 8 tests, both languages). **Not yet flashed.** |
| 3 | Open, hardware-gated. First step is an experimental build that prints the raw CSD registers on the Length screen; the bit meanings are unconfirmed (no datasheet). |
| 4 | **Done as PN 2.15** (`length-progress`, `experimental/LPM-10A-TX_PN2.15-length-progress.bin`, sha256 `e50d53a4…`): the Testing line counts the runs at its right end, `1/4 … 4/4`, in both languages; measurement unchanged. Verified on the real draw code under Unicorn (`test_length_progress.py`, 6 tests: every run's number, Thai label kept, result screen pixel-identical afterwards, footprint = one `bl` + version strings + the appended hook). **Not yet flashed** — checklist in `experimental/LENGTH-PROGRESS-PN2.15-README.txt`. Early stop was not done: two agreeing runs average to ±0.21 m where four give ±0.15 m; the counter explains the wait without giving that back. |
| 5 | **Done as PN 2.16** (`about-values`, sha256 `1b6cbfab…`): one 6×12 line under Factory Reset, `BATT 3874mV  NVP 68%  ZERO 0.4m`, both languages; the About epilogue that crash-record already routes through the cave calls one more routine. Verified on the real About draw code (`test_about_values.py`, 6 tests, with and without a fault record). **Not yet flashed.** |
| 6 | Open, deferred. |
| 8 | **Done as PN 2.19** (`cable-robust`, `experimental/LPM-10A-TX_PN2.19-cable-robust.bin`, sha256 `8353e0b0…`): eleven samples 1 ms apart per sensed pin, median where stock used one sample, the highest for the far-end open test; Switch mode "connected" = a real short (≤ 1240, stock's own far-end short threshold) instead of ≤ 4000; all eight signal pins open → **Not connected** / ไม่พบปลายสาย; the second mode named **RX unit** / เครื่องรับ. Run end to end on the real routines with simulated far ends and hum (`test_cable_test.py`, 10 tests): PN 2.18 gives random results on the same readings, PN 2.19 does not; switch pairs, a broken pair, the RX ladder straight / crossed / shorted all still classify. The `cable-diag` build (`LPM-10A-TX_PN2.19-exp-cablediag.bin`) prints the deciding numbers per row for the owner's four measurements. FORMULA-AUDIT §4 corrected on the way: `CNT_run_test` is the QC test, the wire map is §4.1. **Not yet flashed.** |
| 7 | **Done as PN 2.17** (`speed-partner`, sha256 `78b50e5d…`): a third row **Switch** / สวิตช์ on the SPEED screen with `10/100/1000`, `10/100`, …, or `No autoneg`, from registers 5 and 10 read right after link-up in the net task; the row's box and label are drawn with the screen, its value after the stock result (`LENG_speed_result` wrapped, both of its callers), left empty on a retry or `Error!!`. Verified on the real builder and result code (`test_speed_partner.py`, 10 tests: every speed combination, Thai label, error and retry paths, redraw with a result on screen). **Not yet flashed.** |

**Hardware, 2026-09-21:** the owner flashed PN 2.19 and reports every function passes — items 2, 4, 5, 7 and 8
are confirmed on the unit. The one report, a "Not connected" line staying on screen after a Test Retry with the
cable in a switch / the RX unit (the retry never redrew that line), was reproduced on the CPU model and fixed in
**PN 2.20** (`cable-text-clear`, sha256 `9eaa0fde…`, `test_cable_clear.py`), confirmed on the unit the same day —
the release (`docs/releases/v2.20.md`). The chain PN 2.15 → … → 2.20 stays one patch per file in `experimental/` for
bisecting; device notes in `experimental/TX-PN2.16-2.18-README.txt`, `TX-PN2.19-CABLE-README.txt` and the
release's `TX-PN2.20-README.txt`.

## Where there is no room (checked, so nobody chases them)

- **Cables ≤ 2 m** — the PHY's TDR blind zone; the raw values are genuinely unusable (1 m cable: three pairs zero, one at 2.2 m; `ROADMAP.md` §2).
- **Battery life through PHY idle power** — stock already calls `yt8531_set_pwr_down(1)` at net-task start (0x080147F8) and when leaving every network screen (0x0801493A); verified in the disassembly 2026-09-21. Nothing to gain.
- **Tone side** — the `0xB6B6` code is 8 chips, 5:3 unbalanced, and its 40 ms period aliases with 50 Hz hum in the probe; a longer balanced code would help a matched filter, but it is a lock-step TX+RX change and the RX analysis (RX-NEXT-STEPS §4) showed front-end gain and hum are the limit, with a 50/60 Hz notch on the RX the cheaper lever. Not now.

## Hardware, not code

- A cheap 802.3af injector: the PoE supply paths, the divider ratio and the class comparators are still emulation-only.
- A 50 or 100 m cable for the NVP scale at range.
- A second unit, to learn whether the +0.4 m Zero is per-unit or per-design.
- A cut and a shorted cable for item 3.
