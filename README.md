<div align="center">

# LPM-10A PN Custom Firmware

**TX release: PN 2.6 (2026-09-19).** Adds exact SCAN digital-pattern
wrap, removes SCAN timer-interrupt logging, and fixes the carrier on resume.
Includes PN 2.5's battery and SDK fixes. The owner reports successful TX and RX
hardware testing on 2026-09-19 ("everything work perfect"); the PN 2.4 release
and its hardware results below are retained. See the
[audit and remaining risks](docs/AUDIT-2026-09-19.md) and
[release notes](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/v2.6).

**RX prerelease: PN 1.1 Digital.** An opt-in V3.0.0-based build adds error-tolerant
digital detection, retaining the stock sampler. CPU tests pass, and the owner
reports successful operation on the probe. Quantified range/noise tests remain
outstanding. See the [SCAN report](docs/SCAN-IMPROVEMENTS-2026-09-19.md)
and [RX prerelease](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/rx-v1.1).

Unofficial firmware for the FNIRSI LPM-10A network cable tester and probe,
with changes verified under CPU emulation.
The owner reports that the new TX and RX firmware work perfectly on their units.
This is not certification of every hardware revision or measurement condition.

![version](https://img.shields.io/badge/TX-PN%202.6-orange)
![receiver](https://img.shields.io/badge/RX-PN%201.1%20experimental-yellow)
![patches](https://img.shields.io/badge/TX%20patches-20-blue)
![languages](https://img.shields.io/badge/UI-English%20%2F%20%E0%B9%84%E0%B8%97%E0%B8%A2-blue)
![verified](https://img.shields.io/badge/CPU%20verification-passed-brightgreen)
![hardware](https://img.shields.io/badge/TX%20%2B%20RX-owner%20reports%20pass-brightgreen)
![license](https://img.shields.io/badge/tooling%20license-MIT-lightgrey)
[![release](https://img.shields.io/github/v/release/patnawa/LPM-10A_PN_Custom?label=download)](https://github.com/patnawa/LPM-10A_PN_Custom/releases/latest)

<img src="docs/img/length_screen.png" alt="Length screen: stock vs PN Custom, NVP and Zero calibration" width="1000">

</div>

---

## Downloads and current status

| Device | Release | Firmware | Status |
|---|---|---|---|
| TX tester | [PN 2.6](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/v2.6) | `LPM-10A-TX_PN2.6.bin` | CPU-verified; owner-reported hardware pass |
| RX probe | [PN 1.1 Digital](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/rx-v1.1) | `APP_LPM-10RX_PN1.1-digital-experimental.bin` | Experimental prerelease; CPU-verified; owner-reported hardware pass |

**Use the file for the correct device; TX and RX firmware are not interchangeable.**
Each release includes device-specific notes and a SHA-256 checksum file.
The RX build requires the verified V3.0.0 input file; the owner's
previous RX version is unconfirmed. Success on that probe does not establish
compatibility with all revisions or a stock rollback procedure.

The 2026-09-19 hardware report is a general functional pass, not a detailed
range/noise or PoE-supply test matrix. The [FLASH/length audit](docs/FLASH-LENGTH-AUDIT-2026-09-19.md)
also documents open edge cases not changed by these releases.

### Earlier hardware history

> **PN 2.2 passed every function on a real unit on 2026-09-18**: the Thai interface
> on every screen, the two Cable Test fixes (Back returns to the Switch / Far end choice; the
> red "Result error!!" is no longer hidden under the Test Retry button), the `< 2 m` text
> for a pair the PHY could not time, and everything from PN 1.x (Zero 0.4 m / NVP 68 % read
> a 2.9 m cable right). **PN 2.3** (the PoE screen: the voltage refreshed every 0.5 s,
> "Detecting..." / "No PoE" instead of a blank screen; FLASH: a port blink timed from the
> link) was flashed the same day: the bootloader took the 4 KB longer file and the unit runs,
> but the port blink stopped after three or four cycles. **PN 2.4** is the fix (the blink
> re-asserts the PHY's power-up while it waits and power-cycles it again after 4 s without a
> link, so nothing can stall it), verified by emulation (235 checks, 61 screen states
> compared pixel for pixel) and **its FLASH passed on the unit the same day**: the port keeps
> blinking, the tester's LED shows orange while it does; the PoE screen's supply paths could
> not be tested (no PoE switch or injector at hand), so they stay emulation-verified only. What
> was observed then includes the PHY's own limit: cables of about 2 m and under
> cannot be measured, see [Known limitations](#known-limitations). Flash at your own risk,
> and read [How to go back to stock](#going-back-to-stock) first.

## Why

The LPM-10A is a capable tester (Motorcomm YT8531 PHY, TDR length, PoE, wiremap) let down
by its firmware: length shown in whole metres, no cable calibration, a low-battery
shutdown armed by a single noisy ADC sample, an Auto-Off that cut cable-tracing sessions
short, a heap leak on every settings save, and the thin serif "dev-board" font.
There is no vendor source, so this project works on the shipped binary: it disassembles
it, adds code in an unused flash tail, re-assembles, and verifies the result in place.

## What changes

| Area | Stock firmware | PN Custom |
|---|---|---|
| Length display | whole metres ("55"), inches, cm forced on every screen entry | **m / cm / ft with one decimal** ("55.4"), unit remembered across power cycles |
| Cable calibration | none; the PHY's fixed constant | **Zero 0.0–2.0 m and NVP 50–99 %** on the Length screen, live redraw, saved; 0.0 m / 69 % = factory |
| Length stability | one CSD run shown as is (±0.3 m scatter at 14 m) | **four runs averaged per pair**; a test takes four times longer |
| Length result | a new reading inside the tolerance band was replaced by the previous cable's value; a pair the PHY could not time printed `0.0` | the measured value is always shown; a blind pair reads **`< 2 m`** (`< 200 cm`, `< 7 ft`), so a pair open within the first two metres of a long cable is named as such (PN 2.2) |
| Low battery | one sample < 3150 mV starts an uncancellable 30 s shutdown | needs 3 consecutive samples; cancels on voltage recovery or charging, clearing debounce so re-arming needs fresh samples |
| Battery gauge | 4 steps | 10-step Li-ion curve, red at ≤ 20 % |
| Auto Off | keeps counting while the SCAN tone or FLASH blink is running, so a trace ends with the unit switching itself off | held (and restarted) while a tone or blink session is active; unchanged elsewhere. Correction: PN 1.0–2.2 held it during SCAN only — the FLASH branch compared the wrong state number (8, QC Test, instead of 6); fixed in PN 2.3 |
| Settings save | 204 bytes leaked per save | freed on both exit paths |
| Fonts | thin serif 8×16 ASCII, Song-style Chinese | **Ubuntu Sans Mono** (8×16, 6×12) for English; **Sarabun** 13 px cells for Thai; all open-licensed |
| Language | Chinese / English, picker on first boot | **ไทย / English** on every screen (PN 2.0); picker on first boot and after a factory reset; machine-translated English corrected |
| SCAN modes | labelled "Noiseless" and "Normal" | labelled **Digital** (the 0xB6B6 coded pattern the probe decodes) and **825 Hz** (a plain keyed tone for any analogue probe) |
| SCAN timing | one high tick lost at digital wrap, debug logging in the timer path, stale carrier state after pause | exact 50-tick slots, SCAN timer-path logging bypassed, carrier correctly driven on resume (PN 2.6) |
| Cable Test | Back leaves the screen from every step; "Result error!!" is painted under the Test Retry button | **Back returns to the Switch / Far end choice** from the armed and result screens (PN 2.1); the error line sits above the button, which moved 9 px down |
| FLASH (port blink) | fixed phase counter, no link-aware hold | link-aware hold/drop/retry, with nominal 1500 ms hold, 1000 ms dark and 4000 ms recovery; power-up re-asserted while waiting. Phases are checked every 500 ms against thresholds 250 ms early. Slow links can still be starved by recovery; see the [audit](docs/FLASH-LENGTH-AUDIT-2026-09-19.md). Unchanged in PN 2.6 |
| PoE screen | the voltage is drawn once per detection, from the sample a tick or two after the first one above 40 V (the rising edge), and not refreshed while the screen is shown (the two wires of a pair can even disagree); with no supply the screen stays blank, because the 3.5 s "no supply" timeout fires once per power-on (usually before the screen is ever opened) and is never re-armed | **the voltage column is refreshed every 0.5 s** while a supply is present, every wire from one latched sample, and cleared the moment the supply goes; **"Detecting..."** on entry, **"No PoE"** 3.5 s later without a supply, every time (PN 2.3); "Standard : Yes / No" instead of "Standar / UnStandar" |
| Identity | About screen reports `Software:V2.0.7` and `http://www.fnirsi.cn` | reports `Software:PN 2.6` and this repository's URL; the bootloader-facing image name is untouched |

<img src="docs/img/about_screen.png" alt="About screen: stock and PN Custom" width="760">

Selected stock calculations were checked and left unchanged: battery mV,
PoE mV, link speed/duplex decoding, the 2.54 inch constant and the auto-off table.
This does not imply that all firmware edge cases are resolved. Every
formula is written out below in [The maths, formula by formula](#the-maths-formula-by-formula);
the long form with addresses and verdicts is
[`LPM-10A/Firmware File/FORMULA-AUDIT.md`](LPM-10A/Firmware%20File/FORMULA-AUDIT.md).

## Fonts

The firmware has exactly three glyph tables. They were located, decoded (column-major
bitmaps; the Chinese strings are glyph indices, not GB2312), transcribed, and regenerated
in the same cells so no screen layout changes. In PN 2.0 the 171-glyph Chinese table
carries the Thai cells instead (see [Thai user interface](#thai-user-interface-pn-20));
the Droid Sans Fallback Chinese table below is what PN 1.x shipped and is still built by
`fonts.py`.

<div align="center">
<img src="docs/img/font_ascii.png" alt="ASCII font, stock vs new" width="700">
</div>

<details>
<summary>All 171 Chinese glyphs, stock (white) beside PN Custom (green)</summary>
<div align="center">
<img src="docs/img/font_cjk.png" alt="Chinese glyph table, stock vs new" width="700">
</div>
</details>

## Install

These instructions are for the **TX tester only**. Download PN 2.6 from the
[TX release](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/v2.6), together with
`PN2.6-README.txt` and `PN2.6-SHA256SUMS.txt`. The files also live under
`LPM-10A/Firmware File/`. `MOD-README.txt` is retained as historical PN 2.4 documentation.

1. Verify the download:
   ```
   certutil -hashfile LPM-10A-TX_PN2.6.bin SHA256
   92304aa3ad6452bd60d81b96018c5db563014805d013668ff577b306c37a0f57
   ```
2. Power the tester off. Hold **M + Power** until the firmware update screen appears.
3. Connect USB-C; a removable drive appears.
4. Copy [`LPM-10A-TX_PN2.6.bin`](LPM-10A/Firmware%20File/LPM-10A-TX_PN2.6.bin)
   onto that drive. Do not unplug during the update.
5. Long-press Power to shut down, then power on normally.

If the device refuses the file, rename it to exactly `LPM-10A-TX_V2.0.7_260610.bin` and copy
it again; some bootloaders match on the filename (the name stored inside the image is the
stock one for exactly this reason). **Since PN 2.3 the file is 4 KB longer than stock**
(393 216 bytes, one flash page more, because the code cave ran out): the container header
has no size field beyond the payload length, and the bootloader accepted the longer file on
the tested unit on 2026-09-18 (PN 2.3 flashed and ran). The way back is the same M + Power
procedure with any earlier PN file or FNIRSI's.
This update does not touch the receiver (probe); the
receiver build below is a separate file with its own update mode and recovery caveats. Requires
compatible V2.x.x hardware.

### First power-on checklist

The PN 2.6 TX / PN 1.1 RX general hardware pass was reported on 2026-09-19;
it did not enumerate each checklist item. Earlier testing was on PN 2.2,
2026-09-18; PN 2.4's FLASH passed the
same day (PN 2.3's had stopped after three or four cycles); the PoE items with a supply
could not be tested (no PoE switch or injector available), the no-supply item is the one
that needs no equipment:

- PoE screen without a cable: "Detecting..." / "กำลังตรวจหา..." in the Standard row, then
  "No PoE" / "ไม่พบ PoE" and a blue LED after about 3.5 s; leave and re-enter: the same
  again (stock stayed blank).
- PoE screen on a PoE switch port: the result within a second or two (Standard : Yes, END or
  MID, IEEE 802.3AF/AT/BT, Class 3/4/6/8), the two powered wires reading e.g. `48.2V` and
  updating every half second (a switch under load drifts a few tenths), the return pair
  `0.0V`, the result rows not blinking, both wires of the pair always the same. Unplug: "No PoE" at once.
- A passive injector (12 / 24 V), if available: Standard : No, `--` for protocol and class.
- FLASH on a switch port: after "Testing", the note "Watch the port / LED on the switch: / it
  blinks when linked"; the port's link LED on about 1.5–2 s, then off about 2–3 s while the
  switch re-links, the same on time every cycle (stock: the on time varied with the switch);
  on a managed switch the LED may show amber (spanning tree) rather than green. Note the
  on / off times you see, on a gigabit and a 100 Mb switch if both are at hand; the green dot
  on the tester's screen follows the port within a second. (PN 2.4: passed, the blink keeps
  going; the tester's LED shows orange during the session.)
- FLASH left blinking for longer than the Auto Off setting: the unit stays on (PN 1.0–2.2
  did not hold Auto Off here, only in SCAN).

- A 1 m cable reads `< 2 m` on the pairs the PHY could not time (or *Out of range* when it
  timed none), never `0.0 m`.

- Cable Test: choose Switch or Far end, OK to the wiremap layout, then Back: the choice
  comes back (not Home). Back once more: Home. The same from a result.
- A cable with a broken wire: the red "Result error!!" / "ผลลัพธ์ผิดพลาด!!" line is
  readable between the wiremap and the Test Retry button.

- Settings > Language (ภาษา): switch between `English` and `ไทย`; every screen follows.
- In Thai: walk through Home (both pages), Cable Test, SCAN, FLASH, Length (a result and an
  "Out of range"), QC Test, SPEED (a result), PoE, Settings, About and Factory Reset (answer
  ไม่). Nothing overlaps, every word is readable, tone marks and vowels sit where they
  should ([the expected pictures](docs/THAI-UI.md)).
- Length in Thai: "กำลังทดสอบ" with the dots to its right, then the four readings with
  เมตร / ซม. / ฟุต; unplug the cable for "เกินช่วงการวัด".
- Switch back to English: every screen is exactly as PN 1.3.
- Settings > About reads `Software:PN 2.6` and shows `github.com/patnawa/LPM-10A_PN_Custom`.
- Length screen shows `ZERO 0.0m` left of the Unit box and `NVP 69%` right of it; UP/DOWN
  change the white one, a long press of OK swaps which is white, and after a test the four
  readings follow.
- Leave the Length screen and return, then power-cycle: unit, NVP and Zero are kept.
- Measure two cables of different length back to back; the second must not repeat the first.
- A length test now takes about four times as long as before and repeated tests of the same
  cable agree to within about ±0.15 m at 14 m (they scattered ±0.3 m before).
- SCAN with the tone on for longer than Auto Off: the unit stays on and the probe still
  finds the tone.
- The battery icon shows intermediate levels while discharging.

### Going back to stock

Same procedure with the original `LPM-10A-TX_V2.0.7_260610.bin` obtained from
FNIRSI ([fnirsi.com](https://www.fnirsi.com), support / downloads). FNIRSI's files
are not distributed here. The bootloader lives in a separate flash region that is never
touched, so the update screen stays reachable. The three settings bytes the mod uses (NVP,
unit, Zero) are bytes the stock firmware ignores.

## The science: why TDR needs NVP

<div align="center">
<img src="docs/img/tdr_nvp.png" alt="Time-domain reflectometry: pulse, echo, NVP scale and Zero offset" width="1000">
</div>

The tester measures length the way every cable tester does, by **time-domain
reflectometry**: the PHY (the Ethernet chip, a Motorcomm YT8531) launches a short pulse
down a pair and times the echo that comes back from the far end. An open end reflects the
pulse with the same polarity, a short with the opposite one, a properly terminated pair
(a switch port) reflects nothing at all, which is why the Length screen wants the far end
unplugged. The distance follows from the round-trip time:

```
L = v · t / 2              t   round-trip time of the echo
v = NVP · c                c   speed of light, 299 792 458 m/s
L = NVP · c · t / 2        NVP nominal velocity of propagation, a property of the cable
```

Nothing in the cable travels at *c*. The signal moves through the insulation around the
copper, and its dielectric slows it to a fraction of *c* called the **nominal velocity of
propagation**: about 0.64 to 0.70 for twisted pair, printed on the reel by good cable
makers and different for every jacket, gauge and manufacturer. Because NVP multiplies the
whole result, **every percent of NVP error is a percent of length error**: a 14 m cable
measured with the NVP one point too high reads 14.2 m. Professional testers therefore let
you set NVP or calibrate it on a cable of known length; stock's firmware used one fixed
constant inside the PHY (equivalent to 69 %) and offered no way to change it.

The PHY resolves the echo time to roughly ±1.5 ns per run, which at NVP 0.68 is ±0.3 m
(0.68 × *c* × 1.5 ns / 2). That is the run-to-run scatter measured on the bench, and the
reason PN runs the diagnostic four times and averages.

Two things in the tested unit's readings were not NVP:

- a constant **+0.4 m at every length**, the delay through the PHY's own front end and the
  connector before the pulse reaches the cable. A factor cannot remove a constant, so PN 1.1
  added **Zero**, an offset subtracted before the NVP scaling;
- the **blind zone**: below about 2 m the echo returns while the outgoing pulse is still
  being launched, and the timer cannot separate the two. That limit is physical; stock
  reports "Out of range" there and PN keeps it (an experimental build lowers the cut-off to
  0.5 m only to collect raw readings).

So the PN formula is `length = (raw − Zero) × NVP / 69` with both constants yours to set,
and the two-cable calibration below solves for them exactly. The same formula, with the
addresses and every intermediate value, is written out in
[The maths, formula by formula](#the-maths-formula-by-formula).

## Length calibration: Zero and NVP

The PHY's TDR reading contains two errors, and the hardware test measured both on one
unit: a fixed **offset** from the chip's own signal path and a **scale** from the cable's
velocity of propagation. At NVP 69 % a 2.9 m cable read 3.1–3.5 m in one session and,
converted back from a later session at 66 %, 3.45–3.66 m; a 14 m cable read 14.4–15.0 m.
That is an offset of roughly +0.4 to +0.6 m with a scale within a few percent, on top of
the PHY's ±0.2 m reading-to-reading spread. A factor (NVP) alone cannot remove an offset,
which is why PN 1.1 adds Zero:

```
length = (raw − Zero) × NVP / 69       Zero 0.0–2.0 m in 0.1 m steps, NVP 50–99 %
```

On the **Length** screen `ZERO 0.0m` is shown left of the Unit box and `NVP 69%` right of
it. UP / DOWN (hold for auto-repeat) change the value drawn in white; **hold OK for about a
second** to swap which one is white (a short press still starts a test). Every change
redraws the four readings at once, no re-measure needed. Both values are saved with the other settings at power-off; Factory Reset returns
to 0.0 m / 69 %.

To calibrate, use two cables of known length, one short (about 3 m) and one long (15 m or
more):

1. Measure the short cable. Long-press OK to select Zero, then UP / DOWN until it reads
   right.
2. Measure the long cable. Long-press OK to select NVP, then UP / DOWN until it reads right.
3. Re-check the short cable; adjust Zero once more if needed.

On the unit measured, Zero 0.4 m and NVP 68 % read the 2.9 m cable right (with the four-run
average of PN 1.2 the earlier 0.5 m settled to 0.4 m, exactly what the two-cable formula
below predicts); every unit and
cable batch will differ, which is the point of having the controls. The remaining
reading-to-reading scatter (±0.3 m at 14 m) is the PHY's, not the calibration's; PN 1.2
averages four runs per pair to halve it. Below about 2 m the PHY's
value is unreliable: a 1 m cable came back as 2.4 m or as *Out of range*. The stock blind
zone (raw readings of 2 m or less are discarded, before the Zero is subtracted) is kept, so
short readings are not to be trusted.

Integers only, rounded; 69 % and 0.0 m are the PHY's own calibration, so at the factory
values the reading is exactly stock's centimetre value.

## The maths, formula by formula

Everything the tester computes, with the exact integer arithmetic the firmware runs.
Stock formulas were recovered by disassembly and checked by running the firmware's own
code under emulation; the patched ones are the code in `sdk/patches.py`. The long form
with addresses and verdicts is
[`LPM-10A/Firmware File/FORMULA-AUDIT.md`](LPM-10A/Firmware%20File/FORMULA-AUDIT.md).

### Cable length

<img src="docs/img/length_pipeline.png" alt="How a length reading is made, step by step, worked through with the tested unit's numbers" width="900">

The tester does not time pulses itself. It runs the Cable Status Diagnostic built into
the Motorcomm YT8531 PHY and reads four results in centimetres, one per pair
(1-2, 3-6, 4-5, 7-8). From there:

| step | who | formula | notes |
|---|---|---|---|
| 1. Diagnostic run | stock | ext regs 0x80 = 0x9240, 0x97 = 0x5600, 0xA000 = 0, 0x98 = 0xB0A6; clear bit 15 of 0x27; BMCR soft reset; 0x80 bit 0 = start; poll 0x84 bit 15; read 0x87–0x8A | one run, PHY-timed |
| 2. Blind zone | stock | `raw ≤ 200 cm → 0` | 0 means "out of range" for that pair |
| 3. Four-pair vote | stock | tolerance `tol = 100 cm` below 10 m, `300` below 100 m, `500` below 200 m, else `600`; reference = the second-largest value (the third if the top two are equal); pairs within `tol` of it are replaced by their mean, the rest keep their own value, and two outliers within `tol` of each other are averaged as a second cluster | a consensus filter, not a formula; runs once per diagnostic run |
| 4. Run average | **PN 1.2** | `mean_i = floor(Σ runs_i / n_i)` over the 4 runs, counting only runs where pair *i* read non-zero; `n_i = 0 → 0` | halves the per-run scatter (±0.2 m at 3 m, ±0.3 m at 14 m on the tested unit); the 20 s timeout restarts per run; replaces stock's single retry |
| 5. Zero | **PN 1.1** | `cm0 = cm − 10 × Zero`; `cm0 ≤ 0 → 0` | Zero in 0.1 m steps, 0.0–2.0 m, settings byte 0xC5; a byte above 20 (unset) = no offset |
| 6. NVP | **PN 1.0** | `cm' = (cm0 × NVP + 34) / 69` | 50–99 %, settings byte 0xA6; any byte outside that range (0 = factory) is the identity, and so is 69 % inside it |
| 7. Unit | **PN 1.0** | m: `(cm' + 5) / 10` tenths · cm: `cm'` · ft: `(cm' × 1000 + 1524) / 3048` tenths | integer division, rounded; a pair only 1–4 cm above the Zero rounds to 0 and counts as blind |
| 8. Blind pair | **PN 2.2** | a converted value of 0 prints `< 2` / `< 200` / `< 7` (m / cm / ft) instead of `0.0`; all four zero still gives *Out of range* | the PHY zeroes any pair whose echo came back inside its ~2 m blind zone; on a long cable such a pair is open within the first two metres |
| 8. Display | **PN 1.0** | `sprintf("%s = %d.%d")` for m and ft, `"%s = %d"` for cm; "Out of range" only when all four are 0 | the firmware's own `sprintf` |

Why the two calibration controls: the PHY's number is `v_assumed × t / 2`, where the time
includes the chip's internal path. So the reading is `k × length + offset`. NVP fixes `k`
(the cable's velocity relative to what the PHY assumes), Zero fixes `offset` (the internal
path). With two cables of known length L₁ (short) and L₂ (long) and their raw readings R₁,
R₂ taken at Zero 0.0 / NVP 69 %:

```
NVP  = 69 × (L₂ − L₁) / (R₂ − R₁)
Zero = R₁ − L₁ × 69 / NVP
```

Tested unit: L₁ = 2.9 m read 3.34 m, L₂ = 14 m read 14.7 m → NVP ≈ 67 %, Zero ≈ 0.4 m;
dialled in on the screen it settled at **Zero 0.4 m, NVP 68 %** (0.5 m before the four-run
average, both within the PHY's per-run scatter of ±0.2 m at 3 m and ±0.3 m at 14 m). Worked
example with those settings and the diagram's run mean: 1470 cm → 1470 − 40 = 1430 →
(1430 × 68 + 34) / 69 = 1409 → (1409 + 5) / 10 = 141 → **14.1 m**.

Stock had none of steps 4–6: its only re-run was a single retry when the four post-vote
pairs were not all identical, showing that second run as is. It showed whole metres
(`cm/100 + (cm % 100 ≥ 50)`), offered inches (`cm / 2.54`, truncated) instead of feet,
forced centimetres on every screen entry, and kept the previous cable's result whenever
`|new − previous| < tol(new) − 1` (up to 2.98 m at 50 m, 0.98 m below 10 m: the "sticky"
bug, removed by `length-no-sticky`).

### Battery

<img src="docs/img/battery_gauge.png" alt="Battery percentage vs pack voltage, stock and PN Custom" width="800">

| quantity | formula | notes |
|---|---|---|
| Pack voltage | `mV = raw × 2 × 3300 / 4096` | 12-bit ADC, 3.3 V reference, 1:2 divider; 1 LSB ≈ 1.6 mV; unchanged |
| Percent, stock | `> 4000 → 100`, `> 3800 → 80`, `> 3600 → 50`, else `20` | four values, and the icon only drew those four |
| Percent, PN Custom | `≥ 4150 → 100, ≥ 4050 → 90, ≥ 3950 → 80, ≥ 3870 → 70, ≥ 3800 → 60, ≥ 3750 → 50, ≥ 3700 → 40, ≥ 3650 → 30, ≥ 3600 → 20, ≥ 3450 → 10, else 0` | single-cell Li-ion open-circuit curve; icon draws `pct / 10` segments, red at ≤ 20 % |
| Gauge debounce | a new percentage is shown after two consecutive samples agree, and it only falls while discharging (it rises only on the charger) | stock rule, kept |
| Low-battery shutdown, stock | one sample `< 3150 mV` (sampled once a second, skipped while a test runs, armed only with no charger connected) starts a 30 s countdown; only a charger cancels it | one noisy sample could switch the unit off |
| Low-battery shutdown, PN Custom | three consecutive samples `< 3150 mV` (≥ 3 s) arm it; cancelled, checked once a second, when the pack reads `≥ 3250 mV` again or the charger is connected | 100 mV hysteresis |
| Charger state | PC10 low = charging, PA15 low = charge complete | GPIO, unchanged |

### PoE

| quantity | formula | notes |
|---|---|---|
| Voltage | `mV = (max − min of 4 ADC channels) × 3300 × 40 / 4096` | 1:40 divider; thresholds 2 V idle, 4 V, 40 V "PoE present"; truncated to 16 bits (harmless below 65 V) |
| Span / polarity | pair differences compared with `0.7 × spread` (spread > 372 counts) or `0.9 × spread` | vendor tuning → end-span / mid-span / both |
| Class | two comparator inputs, PA6 and PA7: both high → 3, PA6 only → 4, PA7 only → 6, both low → 8 → 802.3af / at / bt / bt | printed as "Class 3 / 4 / 6 / 8" (the top class of each type); no wattage arithmetic |
| Non-standard supply | the voltage sat between 4 and 40 V for 1 s with a spread over the last 0.8 s below a quarter of its value | a passive injector; "Standard : No", protocol and class `--` |
| Stability | 200 ring entries of `mV >> 8` (150 before the rise past 5 V, 50 after), "unstable" if max − min > 40 000 | can never trigger (a byte spread is ≤ 255); dead code, documented, not patched: with consistent units it would flag every supply |
| Display (PN 2.3) | `poe_mv / 10` printed as `XX.YV` on the powered pair every 0.5 s; "Detecting..." on entry, "No PoE" 3.5 s later | stock drew the first sample above 40 V once and never re-armed its timeout |

### FLASH (port blink)

| quantity | formula | notes |
|---|---|---|
| Link | 10BASE-T only is advertised (`yt8531_set_1000M(0)`, `set_100M(0)`), auto-negotiation; "Testing" for half a second, then the blink session starts (the 20 s link wait is SPEED's) | stock; the fastest-linking speed, kept |
| Blink, stock | net-task message 8 once a second; phases 0–3 `yt8531_set_pwr_down(0)`, phase 4 `set_pwr_down(1)`, phase 5 wraps | a 5 s cycle that ignores the link; the switch's re-link (2–3 s) comes out of the 4 s "up" window |
| Blink, PN 2.4 | message 8 every 500 ms; wait for link (PB5, the PHY's link output), re-asserting `set_pwr_down(0)` every tick and power-cycling again after `FLASH_RELINK_MS` = 4000 without a link → hold `FLASH_ON_MS` = 1500 from the tick that saw it → `set_pwr_down(1)` for `FLASH_OFF_MS` = 1000 → `set_pwr_down(0)` → wait for link; timed with `xTaskGetTickCount`, phases end at the first tick past their length less half a tick | LED on 1.5–2 s (fixed by the tester), off for the switch's re-link (break_link_timer + auto-negotiation, about 2–3 s; `FLASH_OFF_MS` only sets the minimum); PN 2.3 wrote the power-up once and waited without limit, and stopped after a few cycles on the unit |
| Screen indicator | PB5 mirrored on the screen and the RGB LED: on after 150 ms, off after 300 ms (stock 800) | `APP_Flash_task` |

### Link, wiremap, housekeeping

| quantity | formula | notes |
|---|---|---|
| Link speed | PHY reg 0x11 bits 15:14 = 00 / 01 / 10 → 10 / 100 / 1000 Mbps (11 = error) | 20 s auto-negotiation wait |
| Duplex | reg 0x11 bit 13 = 1 → full, 0 → half | |
| Wiremap | per wire: select via a 4-bit mux (PE1/PE2/PE3/PC3), zero TIM8's counter (external clock on PC7), wait 10 ms, read the count; `|count − baseline| < 7 → open`, `count > baseline → "init again"`, else connected | baseline = the eight counts stored by the wiremap Init action, kept in the settings block (offset 0x90) and reloaded at boot |
| Auto Off | `{0, 300, 600, 900}` s = OFF / 5 / 10 / 15 min, counter reset on every key event and after every Length / Speed result | **PN Custom** also holds it while a SCAN tone or FLASH blink session runs (the FLASH half only since PN 2.3: earlier builds compared the wrong state) |
| Backlight dim | `setting × 200 ms` of inactivity | unchanged |
| Watchdog | IWDG prescaler /32, reload 0xFFF ≈ 3.3 s at 40 kHz | a hard fault reboots the unit in ~3.3 s |

### Receiver (probe), for reference

The probe's own firmware is analysed in [`docs/RX-AUDIT.md`](docs/RX-AUDIT.md). The numbers
that matter for the tone function: the transmitter keys its carrier in 5.05 ms slots
(TIM2 at 72 MHz / 72 / 101) in the 16-slot pattern 0xB6B6; the probe samples once per
5.00 ms (TIM5 at 40 kHz, 200 ticks) and needs two exact 16-bit matches within 240 ms.
Its battery is `mV = raw × 6600 / 4096`, LED at ≤ 3579 mV, cleared at ≥ 3621 mV, critical
below 3280 mV; the receiver build makes that critical state recoverable at ≥ 3400 mV.

## How it is built and verified

<div align="center">
<img src="docs/img/pipeline.png" alt="Build and verification pipeline" width="900">
</div>

The build input is FNIRSI's own image, which is **not in this repository**: download the
matching firmware package, unzip it, and put `LPM-10A-TX_V2.0.7_260610.bin` either in
`LPM-10A/Firmware File/`, in a folder named `LPM-10A_FNIRSI_originals` next to the
repository, or anywhere with `LPM10A_STOCK` pointing at it. Every tool checks its SHA-256
(`29081ccbbd929a884c7c81fb309aa2894ce2ab84e061918538b3ead8e632940b`) and refuses anything else.

```bash
cd "LPM-10A/Firmware File/sdk"
pip install capstone unicorn        # pillow + pymupdf only to rebuild the fonts
python test_thumb.py                # assembler self-test against Capstone
python build.py --list              # the patch set
python build.py                     # dry run: every byte it would change, disassembled
python build.py --write             # emit LPM-10A-TX_PN2.6.bin
python verify.py                    # 235 checks
python -m unittest test_audit -v     # audit regressions, including battery recovery
```

`build.py --only a,b` builds a subset; include its required patches, shown by
`--list` (for example `--only length-decimal,length-average`). Incomplete selections
are rejected. `build.py` refuses to run on anything but the pinned stock image.

What `verify.py` proves, section by section:

| § | check | how |
|---|---|---|
| 1–3 | container, byte footprint, full disassembly inventory | any byte changed without being declared by a patch fails |
| 4–5 | auto-off hold, factory defaults | a key event through the stock dispatcher (proves stock already resets on keys); the 1 s housekeeping in SCAN/FLASH with the session flags on and off |
| 6–7 | unit conversion, on-screen text | 36 vectors plus the three blind-pair texts; the text comes out of the firmware's own `sprintf` |
| 8 | sticky result, run averaging | 50 m previous, 52 m readings: stock keeps 50, mod stores 52; four simulated CSD runs through the real re-run block: per-pair means, out-of-range runs left out, stale accumulator ignored, registers and stack intact; stock's single retry for comparison |
| 9–10 | battery debounce and gauge | sample sequences, ADC + GPIO for the cancel path, 18-point curve |
| 11 | heap leak | both exit paths trapped at `vPortFree` |
| 12–16 | Zero + NVP | 513 arithmetic vectors including the measured unit's numbers, key hook (clicks, repeat, clamps, OK long press, other screens), message routing, both rendered texts with their colours, screen-entry draw, Factory Reset defaults compared with stock byte for byte |
| 17 | fonts | the firmware's own glyph drawers render all 361 glyphs; pixels must equal the designed bitmaps |
| 18 | identity | the version strings through the firmware's `sprintf`; the container name is byte-identical to stock; the SCAN labels and the About URL line drawn through the stock code with `gui_blit` trapped |
| 19 | Thai UI | the cell table, every one of the 64 string stubs resolved through the redirect table, the hook table, the three routines byte-identical to their assembled source, the drawer unit test; then **all 57 screen states drawn by the built firmware in Thai compared pixel for pixel with the design model, all 57 in English compared with the same build without the Thai patch**, and every Thai string drawn at least once |
| 20 | Cable Test Back | the key dispatcher with action 7 in every function state, mod and stock: only CABLE_TEST with the layout shown re-enters the screen; everything else keeps stock's target |
| 23 | SCAN | digital wrap and exact slots, analog cadence, no SCAN timer-path logging, pause/resume and mode changes, watchdog/backlight cadence |

Each behavioural check runs the stock image too, so the report shows the defect and the fix
side by side. The SDK internals (symbol database, assembler, cave allocator, font tool) are
documented in [`LPM-10A/Firmware File/sdk/README.md`](LPM-10A/Firmware%20File/sdk/README.md).

## Repository layout

```
LPM-10A/
  Firmware File/
    LPM-10A-TX_PN2.6.bin              current TX release (the build output)
    PN2.6-README.txt                  current TX notes and hardware-test status
    PN2.6-SHA256SUMS.txt              current TX binary checksum
    LPM-10A-TX_V2.0.7_260610.bin      stock image: NOT included, put FNIRSI's copy here to build
    MOD-README.txt                    historical PN 2.4 notes and checklist
    FORMULA-AUDIT.md                  every measurement formula, with verdicts
    sdk/                              the transmitter toolkit: patches, assembler, verifier, fonts
    sdk/thai/                         the Thai UI: cell font, drawers, wording, screen emulator, mock-ups
    APP_LPM-10RX_PN1.0.bin            earlier receiver image (battery fix)
    APP_LPM-10RX_PN1.1-digital-experimental.bin   RX digital prerelease
    RX-PN1.1-DIGITAL-README.txt        current RX notes, scope and warnings
    RX-PN1.1-SHA256SUMS.txt            current RX binary checksum
    RX-README.txt                     historical PN 1.0 notes
    rx-sdk/                           the receiver toolkit: patches, verifier, disassembler
docs/img/                             the images on this page (screens are rendered from the firmware's own layout tables and glyphs)
```

## Receiver (probe)

The probe has its own firmware, audit and toolkit:
[`docs/RX-AUDIT.md`](docs/RX-AUDIT.md) and
[`LPM-10A/Firmware File/rx-sdk`](LPM-10A/Firmware%20File/rx-sdk/README.md).
[RX PN 1.1 Digital](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/rx-v1.1)
includes PN 1.0's battery-recovery fix and adds error-tolerant digital detection.
It passes 41 CPU checks and the owner reports successful operation on hardware.
It remains an opt-in experimental prerelease: range, noise performance and
compatibility with other hardware revisions are not established.

Match TX **Digital** to RX digital mode, or TX **825 Hz** to RX analog mode.
Only the RX digital detector changes; the analog and separate mains modes are
unchanged. The internal RX vendor version remains `3.0.0`; identify the custom
image by its filename and checksum.

Update-mode entry was reported on 2026-09-18: with the probe off, hold SCAN and
connect USB to expose the "UDISK" drive. The owner subsequently reported testing
the new RX firmware successfully. Earlier notes asserted the probe ran V3.0.1;
the owner later clarified that its previous installed version was uncertain.
The build requires the verified V3.0.0 receiver input image.
Confirm applicability and a stock recovery path for your unit before flashing;
do not apply the TX procedure or TX binary to the probe. See
[RX release notes](LPM-10A/Firmware%20File/RX-PN1.1-DIGITAL-README.txt).

## Thai user interface (PN 2.0)

The second language of the tester is Thai instead of Chinese, on every screen. Sarabun
(SIL OFL) is rendered into 16 × 16 one-bit cells, one per consonant cluster (118 cells,
Latin letters and digits in the same face), and drawn proportionally by a replacement text
drawer that keeps the stock drawers' signatures, so no coordinate in the firmware changes.
Every Chinese string slot became a 3-byte redirect to the Thai text in the freed glyph
slots; the messages stock only had in English got Thai versions through a hook on
`gui_blit` that is inert in English. English is byte-for-byte PN 1.3.

The wording of every string, how it was built and how it is verified are in
[docs/THAI-UI.md](docs/THAI-UI.md); the tooling is `sdk/thai/`. The pictures below are
not mock-ups: they are what the firmware draws (`verify.py` §19 proves the built image
produces exactly these pixels), and the whole interface passed on a real unit on 2026-09-18
(PN 2.0 and PN 2.1).

<img src="docs/img/thai/thai_overview.png" alt="Every screen of the Thai interface" width="1000">

## What next

The prioritised list of what to test on hardware and what to build after that is in
[`docs/ROADMAP.md`](docs/ROADMAP.md).

## Known limitations

Remaining firmware edge cases and hardware limits:

- The [deep FLASH/length audit](docs/FLASH-LENGTH-AUDIT-2026-09-19.md) remains open:
  a slow-link acquisition can be repeatedly interrupted by FLASH recovery;
  nonzero-only averaging can report a length from a single valid run; vendor
  pair voting can conceal pair differences; stale calibration redraws and
  overflow with malformed high readings are reproduced in CPU experiments.
  PN 2.6 does not change those paths, and the general hardware pass does not
  specifically test these edge cases.
- RX digital contrast thresholds need bench calibration. Synthetic noise tests
  do not establish false-alarm rate, cable range or adjacent-cable rejection.

- Cables of about 2 m and under read "Out of range" (the PHY's TDR blind zone: the echo
  returns before the pulse has finished, so the YT8531 reports nothing usable; confirmed on
  hardware with a 1 m cable on PN 1.3 and again on PN 2.1, where three pairs returned
  nothing and pair 4-5 returned a raw 2.2 m, shown as 1.7 m after Zero and NVP: an
  artefact of the overlapping pulse and echo, not a length; on other runs all four pairs
  returned nothing and the screen said *Out of range*, which for a 1 m cable is the honest
  answer). Since PN 2.2 a blind pair reads `< 2 m` rather than `0.0 m`. This is why the Length screen cannot tell which pair
  of a short patch cable is broken; the Cable Test (wiremap) screen can. An experimental
  build that lowers stock's 2.0 m cut-off to 0.5 m exists to collect raw readings, see
  [`experimental/README.md`](LPM-10A/Firmware%20File/experimental/README.md).
- Stock contains task-context FreeRTOS queue calls in interrupt handlers.
  PN 2.6 removes the two SCAN logging paths; other interrupt paths remain
  outside this fix. Their contribution to rare lockups is not hardware-proven.
- The PoE "unstable supply" check compares byte data against 40 000 and can never trigger;
  the window it examines would flag every supply once the units were made consistent, so
  the vendor's intent is not recoverable and the check is left as it is.
- Since PN 2.3 the update file is one 4 KB flash page longer than stock; the bootloader
  accepted it on the tested unit (2026-09-18).
- NVP and Zero are on the Length screen, not in Settings: the five Settings rows already fill the
  320-px screen.
- The update container has no CRC or signature; that is what `verify.py` is for.

## Licences and credits

- Tooling, patches and documentation: MIT (see [LICENSE](LICENSE)).
- FNIRSI's original firmware files are not redistributed here; obtain the
  required build and recovery images directly from FNIRSI.
- Fonts: Ubuntu Sans Mono under the Ubuntu Font Licence 1.0; Sarabun (the Thai interface)
  under the SIL Open Font License 1.1; Droid Sans Fallback (the PN 1.x Chinese table) under
  the Apache License 2.0. All three permit redistribution of the rasterized glyphs.
- Disassembly with [Capstone](https://www.capstone-engine.org/), emulation with
  [Unicorn](https://www.unicorn-engine.org/).

*Not affiliated with or endorsed by FNIRSI.*
