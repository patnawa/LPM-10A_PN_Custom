# LPM-10A TX firmware V2.0.7 — measurement formula audit

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
67 % read 2.9 m / 13.9 m (68 %: 14.1 m), which verify.py §12 checks. A 1 m cable returned 2.4 m or nothing, so the ≤ 2 m blind zone
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

---

## 2. Link speed / duplex — `LENG_link_test` 0x0800D47C, `LENG_speed_result` 0x0801A9A8

PHY register 0x11 (PHY-specific status) is read after auto-negotiation:

| bits | value | shown |
|---|---|---|
| 15:14 | 00 / 01 / 10 / 11 | 10 Mbps / 100 Mbps / 1000 Mbps / "Error!!" |
| 13 | 1 / 0 | Full-duplex / Half-duplex |

Matches the YT8531 register map (Marvell-compatible layout). Link wait
timeout 20 s. **OK**

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

Two comparator inputs (PB6, PB7) give class code 3 / 4 / 6 / 8, mapped to
IEEE 802.3af / at / bt / bt. The "Power Level" bar draws one segment per
class step; there is no wattage arithmetic. **OK** for what it is.

### 3.4 Stability check — `poe_ring_is_stable` 0x08014C42 — **NOTE / OPEN**

Scans 200 entries of a byte ring (each entry is `mV >> 8`) for max−min and
returns "unstable" if the spread exceeds **40 000**. A byte spread can never
exceed 255, so the function always returns "stable" and the `Flag=5` branch
after it is dead code. The intended threshold is unknowable from the binary
(40 000 would only make sense for mV data), so it is documented, not patched.

---

## 4. Wiremap / continuity — `CNT_run_test` 0x0800BF40

For each of the 8 wires: select it (4-bit mux), reset TIM1, wait 10 ms, read
the count. Compared with the open-circuit baseline taken at initialisation:

```
|count - baseline| < 7   → "not connected"
count > baseline         → "error, please init again"
otherwise                → connected
```

**OK** — a threshold test, no unit conversion involved.

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

Stock arms a 30 s countdown on **one** sample below 3150 mV (checked every 2 s),
and only a charger connection cancels it. Mod (`batt-debounce`): three
consecutive low samples (≥ 6 s) are needed, and the 1 Hz tick cancels the
countdown when the pack reads ≥ 3250 mV again (100 mV hysteresis) or the
charger is connected. Emulated in verify.py §9.

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
| `settings-leak` | 204 bytes leaked per save | freed on both exit paths |

The formulas were verified by disassembly and CPU emulation; PN 1.0 has since
run on one real unit (2026-09-18), which produced the length data in §1.6. The
PN 1.1 Zero control has not been flashed yet. The PoE divider ratio and the
class comparators are hardware facts that still await a reference PSE. The
Zero and NVP settings exist precisely so that the length constant can be
corrected on the bench.
