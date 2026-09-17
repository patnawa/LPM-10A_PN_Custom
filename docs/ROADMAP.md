# Roadmap: what to check next

Everything in PN 1.0 is verified by emulation only. The order below is deliberate:
nothing further is worth building until step 1 has happened, because one flash
answers questions that no amount of disassembly can.

## 1. Hardware validation of PN 1.0 (do first)

Flash it and work through the checklist in `MOD-README.txt`. Report what you see
for each item, including "looks fine", because the negative results matter too:

| what | why it matters |
|---|---|
| Bootloader accepts the file | the payload is 528 bytes longer than stock; a refusal means the bootloader checks length |
| About screen: `Software:PN 1.0` | proves the string patch and the new 8×16 font in one look |
| Length screen: `NVP 69%` sits right of the Unit box, nothing overlaps | the position came from the layout table, not from a photo |
| UP/DOWN change NVP and the four readings follow | proves the key hook, the GUI message and the live redraw |
| Leave Length, come back, power-cycle: unit and NVP kept | proves the settings bytes survive the power-off flash write |
| SCAN with tone on for longer than Auto Off; same for FLASH | proves the hold; **also confirm the receiver still finds the tone** |
| Chinese mode: every screen readable, no clipped glyphs | dense glyphs (置 量 模) are the ones to look at |
| Battery icon shows intermediate steps while discharging | proves the 10-step gauge in the real drawing path |
| Ten quick settings changes in a row, unit stays responsive | proves the heap fix under the real allocator |

If anything is wrong, `python build.py --only <ids> --write` builds subsets so the
responsible patch can be isolated in two or three flashes.

## 2. Calibrate length against known cables (needs the unit)

Measure 5 m, 20 m, 50 m and 100 m cables of known length, all four pairs, and
record raw readings at NVP 69 %. That answers three open questions at once:

- what NVP the PHY really assumes (so the default can be set correctly instead of the
  placeholder 69 %),
- whether the error is a pure scale (NVP fixes it) or has an offset (a per-unit
  zero would be needed),
- whether the PHY reports anything usable below 2 m, where the firmware currently
  zeroes the result. If it does, the blind zone can be reduced.

## 3. Improvements that are ready to build once 1 and 2 are done

Ranked by value against risk. All are byte patches in the same style as PN 1.0.

1. **Per-pair fault on the Length screen.** The PHY's CSD status register 0x84 reports
   more than "done"; if it carries open/short per pair (as Marvell-style VCT does), the
   screen can show "1-2 open 12.3 m" instead of a bare distance. Needs the register
   bits confirmed on hardware with a deliberately cut cable.
2. **PoE voltage as a number.** The firmware already measures PoE in millivolts
   (`poe_measure_mv`) but only draws a class bar. Drawing "48.2 V" next to it is a
   small, verifiable change. Also fix the dead "unstable supply" check, whose
   threshold is impossible (40 000 against byte data).
3. **Average two CSD runs** when the four pairs disagree, instead of the single retry.
   Costs about a second per measurement, removes most of the flicker between
   consecutive readings.
4. **Battery voltage and NVP on the About screen.** Both values exist in RAM; two
   more text lines.
5. **Save settings when leaving the Length screen**, not only at power-off, so a dead
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

The probe firmware has its own audit in [`RX-AUDIT.md`](RX-AUDIT.md): an
uncancellable low-battery shutdown, an exact-match tone decoder that stutters with
clock drift, and no strength grading in digital mode. It is the next body of work
after the transmitter is validated.

## 6. Not planned

- Changing the tone carrier or cadence on the transmitter: the receiver decodes the
  current patterns and the improvements worth making are on the receiver side.
- A sixth Settings row: the five rows fill the screen; NVP lives on the Length
  screen for that reason.
- Anything requiring the vendor source (task priorities, stack sizes, RTOS config).
