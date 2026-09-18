# Roadmap: what to check next

## Done: hardware validation of PN 1.0 … PN 1.3 (2026-09-18)

PN 1.3 (four-run averaging, Zero + NVP, the Digital / 825 Hz labels) was flashed and
every function tested on a real unit: all good. The one open measurement problem is the
PHY's blind zone below about 2 m (a 1 m cable still reads nothing useful); the
experimental `blind-zone-50cm` build exists to collect raw readings for it, see
`LPM-10A/Firmware File/experimental/README.md`. The Thai UI ([THAI-UI.md](THAI-UI.md))
shipped as PN 2.0 and passed on the unit the same day; PN 2.1's two Cable Test fixes
(Back to the mode selector, the error line above the button) await their flash.

### Earlier: PN 1.0 first power-on

PN 1.0 was flashed to a real unit and every item of the checklist below passed:
the bootloader accepted the file under its own name, the fonts, the NVP control,
the remembered unit and NVP across power cycles, the Auto-Off hold with the
probe still hearing the tone, the non-sticky result, the responsive settings
menu and the 10-step gauge. The length calibration (step 2) was done in the same
session and produced PN 1.1 (Zero calibration, confirmed on the unit) and PN 1.2
(run averaging); see below.

## 1. Hardware validation checklist (re-run after each release)

Flash and work through the checklist in `MOD-README.txt`. Report what you see
for each item, including "looks fine", because the negative results matter too:

| what | why it matters |
|---|---|
| Bootloader accepts the file | the payload is 864 bytes longer than stock (it accepted PN 1.0's 528); a refusal means the bootloader checks length |
| About screen: `Software:PN 1.2` and the GitHub URL line | proves the string patches and both fonts in one look |
| Length screen: `ZERO 0.0m` left of the Unit box, `NVP 69%` right of it, nothing overlaps | the positions came from the layout table, not from a photo |
| UP/DOWN change the white value, OK long press swaps it, the four readings follow | proves the key hook, the GUI message and the live redraw |
| Leave Length, come back, power-cycle: unit, NVP and Zero kept | proves the settings bytes survive the power-off flash write |
| SCAN with tone on for longer than Auto Off; same for FLASH | proves the hold; **also confirm the receiver still finds the tone** |
| Chinese mode: every screen readable, no clipped glyphs | dense glyphs (置 量 模) are the ones to look at |
| Battery icon shows intermediate steps while discharging | proves the 10-step gauge in the real drawing path |
| Ten quick settings changes in a row, unit stays responsive | proves the heap fix under the real allocator |

If anything is wrong, `python build.py --only <ids> --write` builds subsets so the
responsible patch can be isolated in two or three flashes.

## 2. Length calibration (done on one unit; more units welcome)

Measured at NVP 69 %: a 2.9 m cable read 3.1–3.5 m in one session and 3.45–3.66 m
(converted back from readings at 66 %) in another, a 14 m cable read 14.4–15.0 m,
a 1 m cable read 2.4 m or *Out of range*. Conclusions:

- the error is mostly a fixed **offset of roughly +0.4 to +0.6 m** (the PHY's own
  signal path) plus a scale within a few percent; NVP alone cannot fix both.
  PN 1.1 adds a **Zero** setting (`length = (raw − Zero) × NVP / 69`); this unit
  should calibrate around Zero 0.5 m, NVP 68 %,
- below about 2 m the PHY's value is unusable, so the ≤ 2 m blind zone stays,
- the ±0.2–0.3 m spread between readings is the PHY's resolution; PN 1.2 averages
  four runs to halve it (confirmed need: after calibration the 14 m cable still
  scattered).

Still useful: the same two-cable measurement on a second unit, to learn whether
the 0.4 m offset is per-unit or per-design (if per-design it becomes the factory
default), and a 50 m or 100 m cable to check the scale at range.

## 3. Improvements that are ready to build once 1 and 2 are done

Ranked by value against risk. All are byte patches in the same style as PN 1.x.

1. **Flash PN 1.1 and confirm the Zero control** (long-press OK swaps the white value;
   readings follow; both values survive a power cycle).
2. **Per-pair fault on the Length screen.** The PHY's CSD status register 0x84 reports
   more than "done"; if it carries open/short per pair (as Marvell-style VCT does), the
   screen can show "1-2 open 12.3 m" instead of a bare distance. Needs the register
   bits confirmed on hardware with a deliberately cut cable.
3. **PoE voltage as a number.** The firmware already measures PoE in millivolts
   (`poe_measure_mv`) but only draws a class bar. Drawing "48.2 V" next to it is a
   small, verifiable change. Also fix the dead "unstable supply" check, whose
   threshold is impossible (40 000 against byte data).
4. ~~Average CSD runs~~ Done in PN 1.2: four runs averaged per pair, every test.
   Confirm on hardware that repeated tests of one cable now agree to about ±0.15 m
   at 14 m and that the longer test time is acceptable; `AVG_RUNS` in `patches.py`
   is the knob.
5. **Battery voltage, NVP and Zero on the About screen.** All three values exist in RAM;
   three more text lines.
6. **Save settings when leaving the Length screen**, not only at power-off, so a dead
   battery cannot lose a calibration. One flash-page write per change is acceptable
   for the page's endurance.

## 4. Reliability work (bigger, needs care and hardware time)

- **Queue calls from interrupt context.** `tick_hook_1ms` runs inside SysTick and
  posts to FreeRTOS queues with the task-level API; there is no `FromISR` variant in
  the image. FNIRSI's own V2.0.7 notes mention unexpected shutdowns during length
  measurement, which fits. The fix is to make the tick hook only set flags and let a
  task do the posting. It is doable as a patch but touches the timing backbone, so
  it needs a soak test on hardware, not just emulation.
- **Crash record.** Fault handlers are bare loops; the watchdog reboots the unit
  about 3 s later and the cause is lost. Writing the faulting PC into the
  non-initialised RAM arena and showing it on the About screen would turn a
  mystery reboot into a fixable bug.

## 5. Receiver

The probe firmware has its own audit in [`RX-AUDIT.md`](RX-AUDIT.md) and its own
toolkit (`LPM-10A/Firmware File/rx-sdk`). The uncancellable low-battery shutdown is
fixed in `APP_LPM-10RX_PN1.0.bin`; the exact-match tone decoder (whose 5 ms sample is
0.94 % shorter than the transmitter's slot by construction) and the missing strength
grading in digital mode are the next body of work after the transmitter is validated. Before any receiver flash: find out how the
probe enters its update mode and confirm the way back to stock.

## 6. Not planned

- Changing the tone carrier or cadence on the transmitter: the receiver decodes the
  current patterns and the improvements worth making are on the receiver side.
- A sixth Settings row: the five rows fill the screen; NVP and Zero live on the
  Length screen for that reason.
- Anything requiring the vendor source (task priorities, stack sizes, RTOS config).
