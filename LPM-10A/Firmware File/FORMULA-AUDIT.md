# LPM-10A firmware — measurement formula audit (TX §1–6, receiver PN formulas §7)

*Updated 2026-09-21 for TX PN 2.14 and RX PN 1.23; section 7 updated 2026-09-23 for RX PN 1.27.*

Every value the tester computes and shows was traced in the stock binary
(`LPM-10A-TX_V2.0.7_260610.bin`, sha256 `29081ccb…`) by disassembly, and the
arithmetic was re-executed under CPU emulation where the result depends on it.
There is no vendor source; addresses below are flash addresses as the CPU sees
them (`sdk/lpm10a/symbols.py` has the names).

Verdict key: **OK** = correct as implemented · **FIXED** = wrong or below
instrument standard, corrected in the mod build · **NOTE** = correct but worth
knowing · **OPEN** = defect that cannot be fixed safely by patching.

---

## 1. Cable length (TDR via the YT8531 PHY)

### 1.1 Where the number comes from — `APP_LENG_Test_Sequence` 0x080119EC

The firmware does **not** compute length from time-of-flight itself. It runs
the PHY's built-in Cable Status Diagnostic (the vendor log calls the register
sequence "Competitor Compatible Mode"):

| step | action |
|---|---|
| 1–4 | ext reg 0x80 = 0x9240, 0x97 = 0x5600, 0xA000 = 0, 0x98 = 0xB0A6 |
| 5 | ext reg 0x27: clear bit 15 |
| 6 | BMCR (reg 0) = 0x8000 soft reset |
| 7 | ext reg 0x80 \|= 1 → start CSD |
| 8 | poll ext reg 0x84 until bit 15 clears, 20 000 ms timeout (`0x4E20`) |
| 9 | read ext regs 0x87, 0x88, 0x89, 0x8A → pair 1-2, 3-6, 4-5, 7-8, **already in cm** |

**FIXED** — the cm value is whatever the PHY reports; there is no nominal
velocity of propagation (NVP) or cable-type calibration anywhere in the
stock firmware, so accuracy depends entirely on Motorcomm's internal
constant. Industrial testers let the user set NVP. Mod 3 adds it: see §1.6.

### 1.2 Post-processing — the four-pair vote (0x08012494 … 0x08012ADE)

```
for each pair:  if len <= 200 cm → len = 0            (blind zone: < 2 m reads "Out of range")
zeros = count(len == 0)
sort descending (sort_u16_array 0x08014BE4 is a DESCENDING bubble sort)
ref   = sorted[1]  (second-largest: rejects one high outlier)
        if sorted[0] == sorted[1] → ref = sorted[2]
tol   = length_tolerance_cm(ref)
mask  = pairs with |len - ref| <= tol ;  avg = mean(mask)
n = 4 → all pairs = avg
n = 3 → pairs in mask = avg, outlier keeps its own value
n = 2 → mask pairs = avg; if sorted[2], sorted[3] are within tol of each
        other they become their own mean (2 + 2 cluster case)
n = 1 → the lower two pairs are merged if within tolerance
retry once if the four pairs still differ (0x08012AE0), then accept
```

PN 1.2 (`length-average`): the block at 0x08012AE0 now runs the whole
sequence `AVG_RUNS` = 4 times and replaces each pair's value with the mean of
the runs in which it produced a reading (a 0 from the blind-zone cut is left
out; a pair that never reads stays 0). The four-pair vote above still runs
once per run, and the 20 s timeout is restarted per run. Measured scatter of a
single run at 14 m was ±0.3 m; the mean of four halves it. Verified in verify.py §8b with simulated runs through the
real re-run block, on stock and mod.

`length_tolerance_cm` 0x08015D18: `< 1000 cm → 100 · < 10000 → 300 · < 20000 → 500 · else 600`.

Verdict **OK** — this is a consensus filter, not a formula, and the branches
are consistent with a descending sort. (The `0x0C8`/2 m blind zone and the
bands are the vendor's tuning; left alone.)

### 1.3 The sticky-result comparison (0x08012B8C … 0x08012BF2) — **FIXED**

Before the vote result is stored, each pair is compared with the *previous*
stored result:

```
if |new - previous| < tolerance(new) - 1 :  new = previous      ← discards the measurement
```

With a 50 m cable the band is ±2.98 m, so a 52 m cable measured next still
displays 50 m; a 6 m cable after a 5 m one displays 5 m. Emulated
(verify.py §8): stock stores `[50.0, 50.0, 50.0, 53.0]` for a 52 m cable,
which is also internally inconsistent because the +3.00 m pair escapes the
band. Patch `length-no-sticky` makes the branch unconditional so the measured
value is always stored.

### 1.4 Unit conversion — `length_convert` 0x08019774

Stock, verified by disassembly and emulation (verify.py §6):

| unit index | label | formula | shown as |
|---|---|---|---|
| 0 | Inch | `(int)((double)cm / 2.54)` — truncated, software double | `%d` |
| 1 | Cent | `cm` | `%d` |
| 2 | Meter | `cm/100 + (cm%100 >= 50)` — rounded | `%d` → **whole metres** |

* The 2.54 constant is exact (`0x400451EB851EB852`). **OK**
* Inch truncates while metre rounds. Inconsistent, and inches are not a
  cable-length unit (100 m = 3937 in). **FIXED**
* Metres are displayed with 1 m resolution: 55.4 m shows "55". **FIXED**
* The unit index (`0x200002C0`) is set to **1 = cm** every time the Length
  screen is entered (`leng_enter_state`, 0x08012F1C), so a unit choice never
  survives leaving the screen. (Mod 2's audit said "boots into Inch"; that was
  only the power-on value before the first entry. Corrected here.) **FIXED**

Mod (`length-decimal`), integer arithmetic only, applied after the Zero offset
and NVP scale of §1.6:

| unit index | label | formula | shown as | verified |
|---|---|---|---|---|
| 0 | m | `(cm' + 5) / 10` → tenths of a metre | `%d.%d` | 5540 → "55.4", 1005 → "10.1" |
| 1 | cm | `cm'` | `%d` | 5540 → "5540" |
| 2 | ft | `(cm'·1000 + 1524) / 3048` → tenths of a foot | `%d.%d` | 5540 → "181.8", 30480 → "1000.0" |

Slot 0 is metres. On entry the index is loaded from settings byte 0xA7 (0 or
out of range → metres) and every change is written back, so the choice is
remembered across screens and power cycles. The text is produced by the
firmware's own `sprintf` under emulation (verify.py §7), so the on-screen
string is what was checked, not just the number.

### 1.5 Display — `length_result_draw` 0x080199B0

`sprintf(buf, "%s = %d", pair_name, value)`; the unit label is drawn at
`x + 8·strlen`. "Out of range" is shown only when all four converted values
are 0. **OK** (the `> 60000` test after it is dead code: it is only reached
when the value is 0).

### 1.6 Zero and NVP calibration — mod 3 (`nvp-calibration`), Zero added in PN 1.1

```
cm0 = cm − 10 × ZERO             ZERO = settings byte 0xC5, valid 0..20 (0.1 m steps)
cm0 = 0 when the difference is ≤ 0 (that pair reads out of range)
cm0 = cm                         byte > 20 (unset / garbage)
cm' = (cm0 × NVP + 34) / 69      NVP = settings byte 0xA6, valid 50..99
cm' = cm0                        byte 0 (factory) or out of range
```

The Zero exists because the hardware test found an offset that a factor cannot
remove: on the unit measured, at NVP 69 %, a 2.9 m cable read 3.1–3.5 m (mean
3.34) in one session and 3.45–3.66 m (converted back from readings at 66 %) in
another, and a 14 m cable read 14.4–15.0 m (mean 14.7). Fitting the means gives
reading ≈ 1.00–1.02 × length + 0.4–0.6 m; the ±0.2 m spread is the PHY's own
resolution. As a worked example, raw 3.34 m / 14.7 m with Zero 0.4 m and NVP
67 % read 2.9 m / 13.9 m (68 %: 14.1 m), which verify.py §12 checks; the unit
indeed settled at Zero 0.4 m / NVP 68 % once PN 1.2's four-run average was in.
A pair the PHY zeroed (its echo inside the blind zone) prints `< 2` / `< 200` /
`< 7` for m / cm / ft since PN 2.2 (`length-blind-text`, verify.py §7); with a
1 m cable the unit showed three such pairs and a raw 2.2 m on the fourth. A 1 m cable returned 2.4 m or nothing, so the ≤ 2 m blind zone
(§1.2) is genuine and is kept.

69 % is the reference: the PHY's own calibration, whatever velocity it
actually assumes internally, so the factory state is bit-identical to stock.
Length is linear in NVP, so calibrating against a cable of known length
(adjust until the display reads the true length) is exact regardless of the
PHY's internal constant; only the *label* on the value is then relative.

UI: on the Length screen, UP / DOWN change the active value (NVP by 1 % within
50–99, Zero by 0.1 m within 0.0–2.0; auto-repeat when held); holding OK for
about a second swaps between them, the active one drawn white and the other
grey; `ZERO n.nm` sits at x = 4 and `NVP nn%` at x = 166 on the y = 90 header
line, and the four pair results are redrawn immediately via a new GUI message
(0x3D). Both persist with the other settings at power-off; Factory Reset
returns to 69 % / 0.0 m (the defaults writer is hooked at 0x080195BC to clear
byte 0xC5, which stock never touches). Verified in verify.py §12 (arithmetic,
513 vectors), §14 (keys including the OK hold and both clamps), §14b (the
whole key path end to end, mod and stock), §15 (dispatch, both texts and their
colours), §16 (screen entry) and §16b (Factory Reset compared with stock).

Worked example: a 55.40 m reading with NVP set to 75 % shows 60.2 m
(5540 × 75 / 69 = 6022 cm).

### 1.7 Known-length calibration — `length-reference` (PN 2.18), `length-ref-anytime` / `length-ref-reset` (PN 2.22 / 2.23)

The inverse of 1.6, solved on the tester instead of by the user: with a result
on screen, a third OK-hold target `REF` starts at the displayed length
`disp = (mean − 10·Zero) × NVP / 69` (mean = the raw centimetres of the pairs
the PHY timed, zero pairs left out) and every UP / DOWN step (0.1 m, 10 cm or
0.1 ft, REF kept in 100..30000 cm) stores

    NVP = round(69 × REF / (mean − 10·Zero))        clamped to 50..99

so the readings settle on REF to within NVP's 1 % step (±0.1 m at 20 m).
Zero is not solved for — one cable fixes one unknown — and stays the short-
cable step. Integer maths (`69 × REF ≤ 2 070 000`, 32-bit), no change to the
measurement or to 1.4 / 1.6. Exercised end to end through `Action_key_Process`
in `sdk/test_length_reference.py` (both languages, every unit, both clamps).

PN 2.18 offers REF only while a result is on screen (the flag byte 0x200002B4
== 2 and at least one timed pair), else the hold goes ZERO → NVP — met by the
owner on 2026-09-21 as "ZERO does not change to REF". PN 2.22 always offers it:
without a result REF starts at 10.0 m (PN 2.23: written on every screen entry —
PN 2.22 showed the RAM cell's power-up content, `REF 189.1`, because it kept any
value within 1 … 300 m as "last dialled") or the value dialled on this visit,
dialling marks it pending, and the accept path of `APP_LENG_Test_Sequence`
(0x08012C02, right after the flag is set to 2) solves the same formula from the
new mean once and clears the mark; leaving REF or entering the screen clears it
too. Same integer maths; `sdk/test_length_ref_anytime.py` runs the whole sequence
with a simulated PHY and checks the fit (REF 20.0 m on a 2031 cm mean → 68 %), that
the next measurement is not re-fitted, and that the PN 2.18 order still solves at
once; `test_length_ref_reset.py` repeats it on PN 2.23 with 18910 in the cell.

---

**PN2.24 follow-up:** retains the arithmetic above, but keeps a pending REF
through an unusable result, binds Length work/messages to their visit/test,
and redraws only the counter between averaging runs. See
[the Length/QC report](../../docs/TX-LENGTH-QC-PN2.24-2026-09-22.md).

## 2. Link speed / duplex — `LENG_link_test` 0x0800D47C, `LENG_speed_result` 0x0801A9A8

PHY register 0x11 (PHY-specific status) is read after auto-negotiation:

| bits | value | shown |
|---|---|---|
| 15:14 | 00 / 01 / 10 / 11 | 10 Mbps / 100 Mbps / 1000 Mbps / "Error!!" |
| 13 | 1 / 0 | Full-duplex / Half-duplex |

Matches the YT8531 register map (Marvell-compatible layout). Link wait
timeout 20 s. **OK**

PN 2.17 (`speed-partner`, candidate) adds what the port offered, from the two
IEEE 802.3 registers every PHY has and stock never reads: register 5
(auto-negotiation link partner ability; bits 5/6 = 10BASE-T HD/FD, 7/8 =
100BASE-TX HD/FD, 9 = 100BASE-T4) and register 10 (1000BASE-T status; bits
10/11 = partner 1000BASE-T HD/FD), read right after the link came up, before
stock's register 0x11. Shown as `10/100/1000`, `10/100`, `100/1000`, … or
`No autoneg` (register 5 = 0: parallel detection, a fixed-speed port). Display
only; the resolved speed / duplex above are untouched.

---

## 3. PoE

### 3.1 Voltage — `poe_measure_mv` 0x08019CDC

```
v[0..3] = four ADC channels (poe_read_4ch 0x08019D20)
spread  = max(v) - min(v)                     (u16_max_min_spread 0x0801573A)
mV      = spread × 3300 × 5 × 8 / 4096  =  spread × 3300/4096 × 40
```

i.e. a 12-bit ADC on a 3.3 V reference behind a 1:40 divider. **OK** for the
hardware as designed. **NOTE**: the result is truncated to 16 bits, so a
reading above 65.5 V would wrap; PoE never exceeds 57 V, so it is harmless in
practice. Thresholds used: 2.0 V (idle), 4.0 V, 40 V (`0x9C40`, "PoE present").

### 3.2 Span / polarity — `CheckPoESpan` 0x08014CA0

Empirical classifier: if `spread > 372` counts the pair differences are compared
with `0.7 × spread`, otherwise with `0.9 × spread`, in software double
arithmetic. Result 1/2 = end-span (two polarities), 3/4 = mid-span, 5 = both.
Not a physical formula; the constants are the vendor's tuning. **NOTE**

### 3.3 Class / protocol — `poe_class_detect` 0x08019D40 → 0x0801A26C

Two comparator inputs (PA6, PA7 on GPIOA 0x40010800: both high → 3, PA6 only
→ 4, PA7 only → 6, both low → 8) give class code 3 / 4 / 6 / 8, mapped to
IEEE 802.3af / at / bt / bt. The "Power Level" row prints the code as
"Class 3 / 4 / 6 / 8" (the top class of each type); there is no wattage
arithmetic and, contrary to an earlier note here, no bar. **OK** for what it is.

### 3.4 Stability check — `poe_ring_is_stable` 0x08014C42 — **NOTE / OPEN**

Scans 200 entries of the 2048-byte sample ring (one byte per 10 ms tick, `mV >> 8`)
for max−min and returns "unstable" if the spread exceeds **40 000**. A byte spread
can never exceed 255, so the function always returns "stable" and the `Flag=5`
branch after it (`DEVICE_TYPE_UNSTANDAR_1`) is dead code. The window is not even
the last 200 samples: the caller (0x0801A11C) first walks back from the newest
sample while entries are above 20 (5.1 V), so the window runs from 150 samples
before the supply rose past 5 V to 50 after it. With the units made consistent
(40 000 mV = 156 in ring units) every supply that rises from 0 to 48 V would be
"unstable", so the vendor's intent cannot be recovered from the binary, and the
check is documented, not patched. Non-standard supplies are still recognised by
the other path (§3.5, `UNSTANDAR_2`).

### 3.5 State machine and display — `poe_state_machine` 0x08019F00, GUI 0x13 / 0x14 handlers 0x08013270 / 0x08013620

Read for PN 2.3. The PoE task receives message 1 every 10 ms (tick hook
0x0801BD10, in every state but OFF / BOOT) and runs:

```
mv = poe_measure_mv()                ring[idx++ & 0x7FF] = mv >> 8
mv < 2 V and std != 0                → "Votage low, reset buff": ring cleared, std = 0, timeout counter = 0
span == 0                            → timeout counter++ ; at 350 (3.5 s): counter = 0xFFFF, GUI 0x14, LED blue
4 V < mv < 40 V, nearflag == 0       → nearflag = mv >> 8, near timer = 0
mv > 40 V and std != 2               → walk back to the last sample ≤ 5.1 V, poe_ring_is_stable() (always 1),
                                       std = 2 (STANDAR), class = poe_class_detect(), proto 1 / 2 / 3
nearflag != 0 and ++near timer > 100 → spread of the last 80 samples × 256 < mv / 4  → std = 1 (UNSTANDAR_2)
                                       (the supply sat still between 4 and 40 V for a second: a passive injector)
```

`app_poe_set_standar(1|2)` posts task message 2 → `CheckPoESpan` (§3.2) → GUI
0x14 and a green LED. The 0x14 handler (0x08013620) clears the voltage column,
prints `mv / 10` as "XX.YV" on the two wires of the powered pair and "0.0V" on
its return pair (span 5, both pair sets: each pair's own channel relative to
the lowest, `(adc − min) × 3300 × 40 / 4096` mV, the §3.1 scale), clears the four result rows and
prints Standard / Span / Protocol / Class; with standard 0 (the timeout) it
returns before the rows.

Two findings, both fixed in PN 2.3 (`poe-screen`): the voltage is drawn only
when 0x14 is posted, i.e. from the sample a tick or two after the first one
above 40 V, on the rising edge, and not refreshed while the screen is shown
(the handler even loads poe_mv once per wire, so the two wires of a pair can
disagree by a step); and the "no supply" timeout counter, parked at 0xFFFF once
it has fired, is not re-armed when the screen is entered (0x08013270 draws the
frame and, if a span is known, re-posts 0x14, nothing else), so after the first
3.5 s of a power-on the screen simply stays blank without a supply. **NOTE**,
fixed: a live refresh every 0.5 s (voltage column only, every wire from one
latched sample block), the column cleared the moment the supply goes,
"Detecting..." on entry, "No PoE" 3.5 s later, counter re-armed on every entry.

---

### 3.6 FLASH (port blink) — `leng_enter_state` 0x08012EE4, `LENG_link_test` 0x0800D47C, net-task message 8 at 0x0801494C — **FIXED**

Entering FLASH resets the PHY, advertises 10BASE-T only (`yt8531_set_1000M(0)`,
`set_100M(0)`: the fastest-linking speed, a sound choice), shows "Testing" for
half a second while the PHY is configured, then starts the blink session (the
20 s wait for the link at 0x0800D5E0 is the SPEED screen's path). Stock then
blinks by a counter: net-task message 8 every 1000 ms (0x0801BCEE), phases
0..3 `yt8531_set_pwr_down(0)`, phase 4 `set_pwr_down(1)`, phase 5 wraps (and
powers up twice); it never reads the link. Every power-down costs the switch its
re-link: IEEE 802.3 Clause 28 keeps it in TRANSMIT DISABLE for break_link_timer
(1.2–1.5 s) from the drop, then auto-negotiation, 2–3 s in all, taken out of the
4 s "up" window, so the port LED is lit for what is left and, on a switch slower
than the window, not at all. Mod (`flash-blink`): message 8 every 500 ms; the
handler waits for the link (PB5, the PHY's link output that the screen
indicator already uses), holds it `FLASH_ON_MS` = 1500 from the tick that saw
it, drops it `FLASH_OFF_MS` = 1000, waits again, re-asserting the power-up on
every waiting tick and power-cycling the PHY again after `FLASH_RELINK_MS` =
4000 without a link (PN 2.4: PN 2.3 wrote the power-up once and waited without
limit, and stalled after three or four cycles on the tested unit); elapsed time
from `xTaskGetTickCount`, a phase ending at the first tick at or past its
length less half a tick. On the switch: LED on 1.5–2 s (fixed by the tester),
off for its own re-link (about 2–3 s, independent of `FLASH_OFF_MS`), a regular
cycle of 4–5 s. Figures from the code and the standard, unmeasured.
Emulated in verify.py §22.

PN 2.7 (`flash-negotiation`): a wait that produced no link within its window
backs the window off 4 → 8 → 16 s and the first window that produced a link is
kept for the session (ports needing longer than 16 s, or rejecting the 10 Mb/s
advertisement, can still fail). PN 2.12 (`portflash-status`, **device-confirmed
on a D-Link gigabit switch, 2026-09-19**): the link is no longer read from GPIO
PB5 during acquisition and hold — a sampled high/high/low input pattern could
restart the 1500 ms hold indefinitely with the switch LED steadily on — but
from the PHY's **MII BMSR register 1, read twice, bit 2 of the second read**
(link status is latched low, so the first read clears a historical drop and
the second samples the current state; `0xFFFF` on either read is rejected as
an MDIO error). The tester's own indicator task reads the net task's published
phase instead of doing its own GPIO/MDIO reads, so only one task touches the
bit-banged bus; a real observed link loss still starts a fresh hold on
recovery; battery monitoring and low-voltage detection stay active during
FLASH; the auto-negotiation register used by FLASH and SPEED setup was
corrected. Hold/off durations and back-off are unchanged. Sub-poll (< 500 ms)
link interruptions can still be missed.

### 3.7 Auto Off during FLASH — `autooff-hold` — **FIXED in PN 2.3, was wrong in PN 1.0–2.2**

The hold routine compared the state with 8 (QC Test) instead of 6 (FLASH): the
symbol table had the two swapped, and verify §4b tested state 8. So PN 1.0–2.2
held Auto Off during a SCAN tone but not during a port blink. Corrected with
the value from the symbol table; §4b tests 6 and checks 8 is not held.

## 4. QC (crimp) test — `CNT_run_test` 0x0800BF40 — **record corrected 2026-09-21**

Earlier revisions of this section called this routine the wire map; it is the
**QC Test** (压接测试, sysState 8: `cnt_is_calibrated` returns 1 only there).
For each of the 8 wires: select it (4-bit mux on PE1/PE2/PE3/PC3), zero TIM8's
counter (0x40013400, external clock on PC7), wait 10 ms, read the count.
Compared with the baseline captured by the Init action (eight counts, stored
in the settings block at offset 0x90 and reloaded at boot):

```
|count - baseline| < 7   → "not connected"
count > baseline         → "error, please init again"
otherwise                → connected
```

**OK** — a threshold test, no unit conversion involved.

**PN2.23Q experiment (2026-09-22):** replaces the GUI scan call with a
20-second sequence of bounded single-pin acquisitions, retained fault history,
and staged five-sample calibration. The stock scheduler already requested QC
once a second; it did not retain transient faults. See the
[implementation and validation](../../docs/TX-QC-FLEX-PN2.23Q-2026-09-22.md).
The stock formulas above still describe the released PN2.23 behavior.

**PN2.23R follow-up:** owner feedback rejected Q's table and repeated blanking.
R restores the original QC graphic with changed-pin-only rendering and
continuous automatic acquisition; it keeps Q's calibration/session guards.
See [the classic QC report](../../docs/TX-QC-CLASSIC-PN2.23R-2026-09-22.md).

**PN2.24 follow-up:** a single synthetic 7-count dip below an unplugged
baseline could light a passing pin on R. Three consecutive passing samples
are now required for green; OPEN/CHECK revokes green immediately. The
electrical threshold and calibration are unchanged. See
[noise reproduction and hardware limits](../../docs/TX-LENGTH-QC-PN2.24-2026-09-22.md).

**PN2.25 timing correction:** the native QC sampler returned raw TIM8 counts
after a ten-tick task delay, making both calibration and live readings depend
on the actual wake time. The new sampler normalizes to a nominal 10 ms using
the measured SysTick interval and rejects counter overflow or invalid timing.
Legacy baselines require an unplugged Init once after upgrade. The original
decision threshold, classic screen and automatic testing remain. See
[timing reproduction, arithmetic and validation](../../docs/TX-QC-TIMING-PN2.25-2026-09-22.md).

**PN2.26 display correction:** the owner found a garbled QC entry on PN2.25.
Queued connector artwork could paint over the Init prompt after baseline
validation. PN2.26 orders those draws and rejects stale connector messages,
retaining the timing correction and classic automatic screen. See
[the reproduced framebuffer defect and correction](../../docs/TX-QC-DISPLAY-PN2.26-2026-09-22.md).
The owner confirmed every PN2.26 function passed on the device on 2026-09-22;
the exact tested image is now the default TX release.

### 4.1 Wire map (Cable Test) — far end 0x0800C4E0, switch 0x0800CB68 — **FIXED in the PN 2.19 candidate**

The Cable Test is a resistive matrix in the CNT task.  For each of nine tester
pins (1..8 and the shield) it drives that pin through the source mux
(0x080180A0, mode 0) and reads the other eight through the sense mux (mode 1)
into ADC channel 4 (`0x080107A4`, the latest DMA sample), one reading each,
2 ms after switching:

```
switch mode:  open if all 8 readings > 4000, else connected      (no pattern check)
far-end mode: short if any reading <= 1240 (0x4D8, map bit set)
              open  if all 8 readings > 4000
              else: readings in (1240, 4000) averaged, nearest of the remote
                    ladder table [1655 1975 2319 2607 2935 3183 3391 3679 3900]
                    (windows +-5 %): same index -> straight, other -> crossed,
                    none -> "unknown" (the only case that prints "Result error!!")
```

The open threshold, 4000 of 4095, sits 77 mV under the rail; a floating wire
(nothing at the far end) picks up mains hum and single samples cross it at
random, which is the random open / crossed result the owner reported on an
unconnected cable (2026-09-21).  **PN 2.19** (`cable-robust`) reads eleven
samples 1 ms apart per sensed pin and uses their median where stock used the
sample; far-end mode's open test judges the highest of the eleven (a floating
wire touches the rail within a half-cycle, a wire on the ladder does not);
switch mode's "connected" becomes a real short (<= 1240, stock's own far-end
short threshold) instead of anything under 4000; all eight signal pins open
prints "Not connected".  The thresholds and the ladder table are stock's; the
`cable-diag` build prints the deciding numbers per row so the owner's unit
can confirm them (protocol in `experimental/TX-PN2.19-CABLE-README.txt`).

---

## 5. Battery

### 5.1 Voltage — `battery_millivolts` 0x080108F8

`mV = raw × 2 × 3300 / 4096` (signed divide by 4096, truncating). 12-bit ADC,
3.3 V reference, 1:2 divider. **OK** (1 LSB ≈ 1.6 mV).

### 5.2 Percent — `battery_level_percent` 0x080107C0 — **FIXED**

Stock: `> 4000 mV → 100 %, > 3800 → 80 %, > 3600 → 50 %, else 20 %`, and the
gauge only draws for exactly those four values. Mod (`batt-gauge`): 10-point
Li-ion table (4150/4050/3950/3870/3800/3750/3700/3650/3600/3450 mV → 100…10 %),
gauge draws `pct/10` segments for any value, red at ≤ 20 %. The stock
two-sample debounce and "only falls while discharging" rule are kept.

### 5.3 Low-battery shutdown — `battery_ui_update` 0x0800E6B0, `battery_tick` 0x0800DD34 — **FIXED**

Stock arms a 30 s countdown on **one** sample below 3150 mV (sampled once a
second by GUI message 4 from the 1 ms SysTick hook, skipped while a test runs,
and only while no charger is connected); only a charger connection cancels it.
Mod (`batt-debounce`): three consecutive low samples (≥ 3 s) are needed, and
the 1 Hz tick cancels the
countdown when the pack reads ≥ 3250 mV again (100 mV hysteresis) or the
charger is connected. Emulated in verify.py §9. Since PN 2.12 the battery
sample is not skipped during a FLASH blink session.

### 5.4 Charger state — `charger_state` 0x08010918

PC10 low = charging, PA15 low = standby (charge complete). GPIO reads. **OK**

---

## 6. Housekeeping constants

| item | value | verdict |
|---|---|---|
| Auto-off table 0x08064D72 | `{0, 300, 600, 900}` s = OFF / 5 / 10 / 15 min; stock resets the counter on every key event (`Action_key_Process` tail) | **FIXED**: the counter also ran during SCAN tone / FLASH blink sessions; `autooff-hold` pauses it there |
| Battery table 0x08064D7A | `{4000, 3800, 3600}` mV | superseded by `batt-gauge` |
| Backlight dim | `setting × 200 ms` of inactivity (`backlight_dim_update`) | **OK** |
| Watchdog `iwdg_init` 0x0801B17E | writes **prescaler** = /32 (the function the SDK had named `iwdg_set_reload` writes IWDG+0x04 = PR, not RLR); RLR stays 0xFFF → ≈ 3.3 s at 40 kHz LSI | **NOTE**: a hard fault resets the unit in ~3.3 s |
| Settings save `APP_Home_Cust_Info_Storage` 0x0800FF74 | 204-byte `pvPortMalloc` never freed | **FIXED** (`settings-leak`) |

---

## Summary of changes made because of this audit

| patch | what was wrong | what it does now |
|---|---|---|
| `length-decimal` | whole-metre display, inch unit, cm forced on every screen entry | m / cm / ft with one decimal, unit remembered, Zero and NVP applied |
| `nvp-calibration` | no cable calibration at all | Zero 0.0–2.0 m and NVP 50–99 % on the Length screen, live redraw, both saved |
| `font-pro` | thin serif 8×16 "dev-board" ASCII font, Song-style Chinese | Ubuntu Sans Mono 600 (8×16, 6×12) and Droid Sans Fallback (16×16), rendered by the firmware's own glyph drawers in verify.py §17 |
| `length-no-sticky` | new reading replaced by old one inside the tolerance band | measured value always displayed |
| `batt-debounce` | one noisy ADC sample could start an uncancellable shutdown | 3 consecutive samples, cancels on recovery |
| `batt-gauge` | 4-step gauge | 10-step Li-ion gauge |
| `settings-leak` | 204 bytes leaked per save | freed on both exit paths (PN 1.x); since PN 2.11/2.12 a checked static writer with no heap allocation serves explicit save, default setup, power-off and changed Length calibration |
| `length-average` (PN 1.2) | one run shown as is, ±0.3 m scatter at 14 m | four runs averaged per pair, `~` when fewer than four yielded a reading (§1.2) |
| `length-blind-text` (PN 2.2) | a pair the PHY zeroed printed `0.0 m` | `< 2` / `< 200` / `< 7` (§1.6) |
| `autooff-hold` (PN 1.0, FLASH half fixed in PN 2.3) | Auto Off counted during SCAN / FLASH sessions | held; compared the wrong state (8) for FLASH until PN 2.3 (§3.7) |
| `poe-screen` (PN 2.3) | voltage drawn once, blank screen without a supply | refreshed every 0.5 s, "Detecting..." / "No PoE" re-armed every entry (§3.5) |
| `flash-blink` (PN 2.3/2.4), `flash-negotiation` (PN 2.7), `portflash-status` (PN 2.12) | 5 s phase counter ignoring the link; GPIO sampling could stall the hold | link-timed 1.5 s / 1 s cycle from the PHY status register, 4 → 8 → 16 s back-off, device-confirmed (§3.6) |
| SCAN timing (PN 2.6), RIGHT-key carrier cache (PN 2.14) | one high tick lost at the digital wrap, logging in the timer path, stale carrier after Pause, carrier cache not invalidated by RIGHT | exact 50-tick slots, logging bypassed, carrier driven correctly on resume and after RIGHT (docs/TONE-PERFORMANCE-AUDIT-2026-09-20.md) |
| service task / watchdog / fault frame (PN 2.8, 2.9) | application queue calls in SysTick, timer-fed watchdog, FP crash frame | callbacks deferred to a service task, watchdog requires service-task progress, SHCSR handlers and the Cortex-M4F frame fixed, fault details kept across warm reset |
| Thai UI (PN 2.0) | Chinese second language | Thai on every screen; English byte-identical to PN 1.3 (docs/THAI-UI.md) |

The TX formulas were verified by disassembly and CPU emulation, then on one
real unit: PN 1.0–1.3 on 2026-09-18 (the length data in §1.6, Zero + NVP,
four-run averaging), PN 2.2 / 2.4 the same day (Thai UI, FLASH blink), PN 2.8
and 2.12 on 2026-09-19 (Port FLASH on a D-Link gigabit switch), and PN 2.14 is
the build in daily use. The PoE supply paths, the divider ratio and the class
comparators still await a reference PSE (no PoE switch or injector has been
available); the no-supply path was checked on the unit.

---

## 7. Receiver (probe) — the PN formulas

The stock receiver firmware is audited function by function in
[`../../docs/RX-AUDIT.md`](../../docs/RX-AUDIT.md) (modes, decoder, DFT, speaker,
battery, keys, device binding). What PN adds is arithmetic of its own, all of
it measured on the owner's unit on 2026-09-21
([`RX-SENSITIVITY-2026-09-21.md`](../../docs/RX-SENSITIVITY-2026-09-21.md)) and
executed on a CPU model in `rx-sdk/test_rx_*.py`.

### 7.1 Digital detection — PN 1.12 (`digital-correlation` … `rx-overload`)

```
frame       48 samples, one per 5 ms slot (trimmed mean of 5 readings in the slot's last 2.5 ms)
threshold   trimmed mean of the frame (stock), plus PN 1.11's short-span local slicing
code test   all 8 rotations of the repeated 0xB6B6 pattern over the 48 bits:
            accept when <= 4 bit errors in total and <= 2 in each 16-bit block,
            or stock's two exact sliding 16-bit matches (kept as a fallback)
floor       sum |sample - threshold| >= 192 counts (4 per sample) and stock's high-sample sum
strength    trimmed estimate over the 16 newest code-verified samples (one code period);
            a window whose 16 newest raw samples are all 4095 -> 'uncertain' (interval 1)
overlap     since PN 1.21 keep the newest 40 samples, collect 8 -> re-evaluate every 40 ms
            (32 / 16 = 80 ms in PN 1.11-1.20); the first lock after a mode or gate change needs a full frame
```

A matched-filter alternative was modelled on 7 992 live windows and rejected
(§ "ทำไมไม่ทำ matched filter" in `RX-NEXT-STEPS-2026-09-21.md`): the 8-chip code
and 50 Hz hum (period 4 samples) give noise correlations up to 0.77.

### 7.2 Analog detection — stock rule, PN arithmetic (PN 1.11)

```
window      64 samples every 0.325 ms (20.8 ms), 32-bin DFT, target bin 17 = 817 Hz
noise       (sum of bins 1..31 - bin 1 - bin 17) / 12          (uxth, as stock)
margin      bin17 - noise;  accept when margin > 10
upper rail  >= 8 of 64 samples at 4095 in an accepted window -> 'uncertain' (interval 1)
score       (margin - 10) x 40                                  (feeds the same curve as Digital)
DFT         exact integer inner loop, bit-identical results, -74 % instructions
```

### 7.3 Strength score → quiet interval (PN 1.8, 1.15, 1.17, 1.19, 1.27)

```
score'      = score x MULT[level] / 10,  MULT = {200, 92, 26, 26, 11, 11, 11, 10} for driven gain level 0..7
              (measured p-p per knob code at one position: 95, 230, 780, 90->780, 1920, 1940, 2040, 2400;
               level = the gain actually driven, see 7.4); clamped to 0x00FFFFFF (PN 1.27)
mute        PN 1.26/1.27, below the middle of the knob: score' < peak x window -> rejected, see 7.9
score''     = score' x K(knob) / 256  (PN 1.27, see 7.9; K = 256 on the top sixteenth: PN 1.24 exactly)
interval    piecewise linear through (score'', ms):
              (0, 110) (800, 95) (2400, 85) (7200, 70) (24000, 45) (40000, 20); >= 40000 -> 20
              (40 000 = the front end's measured saturation: touching the cable is 20 ms on the top
               sixteenth of the knob; lower down K slows it)
publish     if audio is fresh (RECENT > 500) and an interval is already published (not 0 / 'uncertain'):
              new = old + (target - old) / 2, applied only when |half step| >= 3 ms  (PN 1.17)
            otherwise the target directly
pulse       30 ms on (Digital), 12 ms (Analog); 'uncertain' (1) is published as 20 ms since PN 1.18
            (PN 1.27: on the top sixteenth only; below it a clipped window is score 40 000 at the driven gain)
```

### 7.4 Knob, gain steps and automatic range (PN 1.17, 1.22, 1.24, 1.26)

```
knob        PA2 trimmed mean every 500 ms; code = raw / 580 (0..7); gates: Digital raw >= 2, Analog code >= 1
pins        PB12..14 = bits of the level; stock forces level 0 to 011 == level 3 -> PN maps level 3 to level 2
AGC tick    (500 ms, main context; Digital and Analog)
              ceiling changed or first tick -> driven = ceiling, hold = 0
                (PN 1.26: a lowered ceiling still above the driven gain is only recorded)
              else p-p of the 48-sample buffer:
                >= 1900 -> driven steps down one effective step (7..4 -> 2 -> 1 -> 0), hold
                <  450  -> driven steps up (0 -> 1 -> 2 -> ceiling), never above the ceiling, hold
                else keep;  a hold tick decrements and forbids changes
              hold = 4 ticks (PN 1.22), 1 tick (PN 1.24: a step at most every 1 s); PN 1.24 decides only on a
              complete recent acquisition from the current gain
ceiling     PN 1.22-1.25: the knob level; PN 1.26: 7 at every knob position, below the middle of the
            knob the peak-derived ceiling of 7.9
mains       PN 1.25/1.26: driven = knob level (7 from raw >= 1024), set again at every tick, see 7.7
state       0x20000200: [0] driven level, [1] 0, [2] hold, [3] last ceiling   (normaliser reads [0..1] as u16)
ratios      1900 / 450 = 4.2 > 2.6 x 1.3: no oscillation between adjacent steps
```

### 7.5 Release and freshness (PN 1.7, 1.16)

```
accepted window   RECENT = 800 (Digital), then trimmed to 600 by the Analog analyzer
rejected window   interval kept; RECENT = min(RECENT, 660 Digital / 560 Analog)
audio             pulses scheduled only while RECENT > 500 and interval != 0
release           Digital <= 40 ms (first rejected update) + 160 ms; Analog <= 21 + 60 ms
keep-alive        800 ms power keep-alive is stock and separate
```

### 7.6 Speaker cadence (PN 1.14, 1.23, 1.25)

```
TIM5 40 kHz; duty 1100/500 (PN 1.25; stock 900/700, silence 800: 3x the swing, +9.5 dB) flipped every N interrupts: Digital N = 8 (2.5 kHz), Analog 16 (1.25 kHz), mains 4 (5 kHz)
key beep 100 ms: first 50 ms at the other mode's N -> Digital chirps low->high, Analog high->low
```

### 7.7 Mains (NCV) — stock analysis, PN gain (PN 1.25, 1.26)

```
64 samples every 1.55 ms from ADC channel 7 (PA6; the PD15 key selects the mode); DFT bins 5 and 6 = 50.4 / 60.5 Hz
level = max(bin5, bin6): > 350 -> 50 ms beep, 251..350 -> 100 ms, 151..250 -> 200 ms, else none (per 99 ms window)
gain  driven = knob level, 7 from knob raw >= 1024 (PN 1.26), set again at every 500 ms tick (PN 1.25);
      PN 1.22-1.24 kept the gain a tracing mode had lowered until the knob moved
```

The owner reported that NCV sensitivity follows the knob (2026-09-23), so the
mains input is treated as affected by the selected gain; the thresholds are
stock's until the DFT level is captured against distance.

### 7.8 Battery and identity (PN 1.0, 1.20)

```
critical state recoverable when the pack reads >= 3400 mV again (stock: uncancellable below 3280 mV)
version string "PN1.xx" at 0x0800CDE4 -> written to page 0x0801F000 at boot -> BOOTLOADER drive shows PN1.xx.TXT
```

### 7.9 Knob reference, peak and mute window (PN 1.26, 1.27)

```
knob        raw 0..4095 (7.4); i = raw >> 8 (sixteenth), f = raw & 0xFF;
            tables are interpolated as T[i] + (T[i+1] - T[i]) x f / 256 (integer steps)
peak        u32 at 0x20000210, u32 TIM5 tick (40 kHz) of its last decay step at 0x20000214 (zero-initialised)
              decayed to now: x 250/256 per 4 000 ticks (100 ms, about -2 dB/s);
              more than 400 000 ticks (10 s) since the last step -> 0
              every analysed score' (7.3): peak = max(peak decayed to now, score')
mute        lower half (i < 8): window W = (128, 121, 102, 72, 45, 23, 10, 4, 0) at i = 0..8 (x/256)
              (-6 dB at the bottom ... -36 dB just below the middle); score' < peak x W / 256 -> published as
              rejected, so the release hold of 7.5 ends the rhythm; upper half: nothing is muted
reference   K = (8, 10, 13, 16, 20, 25, 32, 40, 51, 64, 81, 102, 128, 161, 203, 256, 256) at i = 0..16 (x/256)
              = 8 x 32^(i/15): about 2 dB per sixteenth, -30 dB at the bottom, 256 (x1) from raw 3840 up
              score'' = score' x K / 256 -> the 7.3 curve; K never mutes
clipped     i = 15: fastest (interval 1, published as 20 ms); i < 15: score 40 000 at the driven gain
              -> score' -> mute -> K -> curve
ceiling     tracing modes: 7 in the upper half; lower half: threshold = peak (decayed to now) x W / 256,
              ceiling = the first of (7, 40 000) (2, 104 000) (1, 368 000) whose saturation score' >= threshold,
              else 0 (saturation score' = 40 000 x MULT[level] / 10: a pair above the threshold never reads clipped)
```

Checked on the actual code: `test_rx_knob_reference` compares every knob position
with an independent model of these formulas (24 336 Digital and 9 504 Analog
windows) and the top sixteenth with PN 1.24; `test_rx_relative_isolate` covers the
peak, the ceiling and the mains gain; `test_rx_knob_response` is the owner's
report as a test ([docs/RX-KNOB-PN1.27-2026-09-23.md](../../docs/RX-KNOB-PN1.27-2026-09-23.md)).
