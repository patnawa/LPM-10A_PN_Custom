# Roadmap: what to check next

**TX after PN 2.14 (2026-09-21):** what is left, ranked, with what was done about each item
(build profiles; PN 2.15 … 2.20 — run counter, About values, SPEED partner row, known-length NVP calibration,
a Cable Test that says "Not connected" instead of guessing — PN 2.19 passed on the unit 2026-09-21, PN 2.20 is
the release) —
[TX-NEXT-STEPS-2026-09-21.md](TX-NEXT-STEPS-2026-09-21.md). The RX equivalent is
[RX-NEXT-STEPS-2026-09-21.md](RX-NEXT-STEPS-2026-09-21.md).

## Owner checkpoint (2026-09-20)

The owner requested Git push and an archival prerelease, and is retaining the
currently working devices. Preserve TX PN 2.14, RX experimental profiles, tests
and the SWD/update investigation in the
[development snapshot](releases/TONE-SNAPSHOT-2026-09-20.md).
RX PN 1.13 installation remains unconfirmed and the Digital tail is unresolved.
Resume device-update work when a compatible RX image and a verifiable update
path are available. No further hardware changes are part of this checkpoint.

## Current release update (2026-09-19)

TX PN 2.7 and experimental RX PN 1.2 Reliability pass CPU verification; the
owner reports both new builds passed hardware testing. TX adds adaptive FLASH
retries, minimum phase timing, partial/overflow length markers, guarded redraws
and battery startup initialisation. RX adds activity-aware auto-off while
retaining the digital detector. See [audit and test scope](RELIABILITY-AUDIT-2026-09-19.md).

Next priorities are remaining length pair-filter/raw-status issues, interrupt
queue and ADC concurrency, quantified RX range/noise and adjacent-cable tests, and explicit PoE-supply and
long-duration checks. The general hardware report is not a detailed checklist.
Earlier plans below are historical where superseded by this update; the RX
oversampling and strength-indication proposals have not been implemented.

## Done: hardware validation of PN 1.0 … PN 1.3 (2026-09-18)

PN 1.3 (four-run averaging, Zero + NVP, the Digital / 825 Hz labels) was flashed and
every function tested on a real unit: all good. The one open measurement problem is the
PHY's blind zone below about 2 m (a 1 m cable still reads nothing useful); the
experimental `blind-zone-50cm` build exists to collect raw readings for it, see
`LPM-10A/Firmware File/experimental/README.md`. The Thai UI ([THAI-UI.md](THAI-UI.md))
shipped as PN 2.0 and passed on the unit the same day, as did PN 2.1's two Cable Test
fixes (Back to the mode selector, the error line above the button) and PN 2.2's `< 2 m`
text for blind pairs. PN 2.3 (the PoE screen: live voltage, "Detecting..." / "No PoE",
the timeout re-armed on every visit; FLASH: the port blink timed from the link, 1.5 s
on time fixed by the tester instead of a 5 s counter that ignored the link; and the Auto Off
hold during FLASH, which PN 1.0–2.2 keyed on the wrong state number, actually working) was
flashed the same day: the bootloader took the 4 KB longer file, but the port blink stopped
after three or four cycles. PN 2.4 (the blink re-asserts the power-up while waiting and
power-cycles the PHY again after 4 s without a link) was flashed the same day and its FLASH
passed: the blink keeps going, the tester's LED orange during the session. The PoE screen
could not be tested with a supply (no PoE switch or injector available); its no-supply path
("Detecting..." → "No PoE") needs no equipment and is the one still worth a look. The on /
off times seen on the switch during FLASH would be welcome too.

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
| Bootloader accepts the file | since PN 2.3 the update file is one 4 KB page longer than stock (393 216 bytes; payload past 0x08068000) because the code cave grew; accepted on the tested unit on 2026-09-18 |
| About screen: `Software:PN 1.2` and the GitHub URL line | proves the string patches and both fonts in one look |
| Length screen: `ZERO 0.0m` left of the Unit box, `NVP 69%` right of it, nothing overlaps | the positions came from the layout table, not from a photo |
| UP/DOWN change the white value, OK long press swaps it, the four readings follow | proves the key hook, the GUI message and the live redraw |
| Leave Length, come back, power-cycle: unit, NVP and Zero kept | proves the settings bytes survive the power-off flash write |
| SCAN with tone on for longer than Auto Off; same for FLASH | proves the hold; **also confirm the receiver still finds the tone**. The FLASH half only works from PN 2.3 on (earlier builds compared state 8, QC Test, instead of 6), so it was never really tested |
| Chinese mode: every screen readable, no clipped glyphs | dense glyphs (置 量 模) are the ones to look at |
| Battery icon shows intermediate steps while discharging | proves the 10-step gauge in the real drawing path |
| Ten quick settings changes in a row, unit stays responsive | proves the heap fix under the real allocator |

If anything is wrong, `python build.py --only <ids> --write` builds subsets so the
responsible patch can be isolated in two or three flashes.

## 2. Length calibration (done on one unit; more units welcome)

Measured at NVP 69 %: a 2.9 m cable read 3.1–3.5 m in one session and 3.45–3.66 m
(converted back from readings at 66 %) in another, a 14 m cable read 14.4–15.0 m,
a 1 m cable read 2.4 m or *Out of range* (on PN 2.1 with Zero 0.4 / NVP 68: pairs 1-2,
3-6, 7-8 blind, pair 4-5 = 1.7 m, i.e. a raw 2.2 m; the screen shows the blind pairs as
0.0 m, which is misleading and is the next thing to fix). Conclusions:

- the error is mostly a fixed **offset of roughly +0.4 to +0.6 m** (the PHY's own
  signal path) plus a scale within a few percent; NVP alone cannot fix both.
  PN 1.1 adds a **Zero** setting (`length = (raw − Zero) × NVP / 69`); this unit
  calibrates at Zero 0.4 m, NVP 68 % (0.5 m before the four-run average),
- below about 2 m the PHY's value is unusable, so the ≤ 2 m blind zone stays,
- the ±0.2–0.3 m spread between readings is the PHY's resolution; PN 1.2 averages
  four runs to halve it (confirmed need: after calibration the 14 m cable still
  scattered).

Still useful: the same two-cable measurement on a second unit, to learn whether
the 0.4 m offset is per-unit or per-design (if per-design it becomes the factory
default), and a 50 m or 100 m cable to check the scale at range. The long-cable step
is one dial since the PN 2.18 candidate (hold OK: NVP → ZERO → **REF**, dial the true
length, NVP is solved; [TX-NEXT-STEPS](TX-NEXT-STEPS-2026-09-21.md) item 2).

## 3. Improvements that are ready to build once 1 and 2 are done

Ranked by value against risk. All are byte patches in the same style as PN 1.x.

1. **Flash PN 1.1 and confirm the Zero control** (long-press OK swaps the white value;
   readings follow; both values survive a power cycle).
2. **Per-pair fault on the Length screen.** The PHY's CSD status register 0x84 reports
   more than "done"; if it carries open/short per pair (as Marvell-style VCT does), the
   screen can show "1-2 open 12.3 m" instead of a bare distance. Needs the register
   bits confirmed on hardware with a deliberately cut cable.
3. ~~PoE voltage as a number~~ Done in PN 2.3, after a correction of the record: this
   item claimed stock "only draws a class bar", which was wrong. Stock already prints
   the voltage as "48.2V" on the two wires of the powered pair (0.1 V, from
   `poe_mv`) and "Class 3 / 4 / 6 / 8" in the Power Level row; there is no bar. What
   stock actually lacked, found by reading the 0x14 handler and the PoE state machine
   (`FORMULA-AUDIT.md` §3.5): the voltage is drawn once, from the first 10 ms sample
   above 40 V (the rising edge), and not refreshed while the screen is shown; with no supply the screen stays
   blank forever, because the 3.5 s "no PoE" timeout is parked after it fires once
   (3.5 s after boot, usually) and is never re-armed on entering the screen. PN 2.3
   refreshes the voltage every 0.5 s while a supply is present, writes "Detecting..."
   on entry and "No PoE" after 3.5 s without one, every time. Needs the hardware
   pass: a PoE switch (802.3af/at/bt) and, if available, a passive injector.
   The dead "unstable supply" check stays as documented: the vendor's intent cannot be
   recovered from the binary (the window it examines is 150 samples before the rise
   and 50 after, which would flag every supply once the units were made consistent),
   and making it live could only change classifications that work today.
4. ~~Average CSD runs~~ Done in PN 1.2: four runs averaged per pair, every test.
   Confirm on hardware that repeated tests of one cable now agree to about ±0.15 m
   at 14 m and that the longer test time is acceptable; `AVG_RUNS` in `patches.py`
   is the knob.
5. ~~Battery voltage, NVP and Zero on the About screen~~ Done in the PN 2.16 candidate:
   one line under Factory Reset, `BATT 3874mV  NVP 68%  ZERO 0.4m`.
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
grading in digital mode are the next body of work after the transmitter is validated.
**Next steps after PN 1.19, assessed in detail:** [RX-NEXT-STEPS-2026-09-21.md](RX-NEXT-STEPS-2026-09-21.md)
(status file naming the PN build, AGC auto-range, 40 ms Digital updates, Digital matched filter,
field protocol, build-profile refactor).

**Resolved 2026-09-21:** the RX bootloader programs only a TX-style container
(name + `0x1000` header + image), copied with an ordinary Explorer copy; raw
images are ignored. `rx-sdk/build.py` now emits the `-update.bin` container, and
RX PN 1.12 is installed and running on the owner's probe, with the one-second
Digital tail gone. Every earlier RX "device pass" was a test of the factory
firmware. See [the procedure and evidence](RX-UPDATE-PROCEDURE-2026-09-21.md).
Historical notes follow. Update-mode entry was owner-confirmed on 2026-09-18
(probe off, hold SCAN, plug USB → a drive appears). Early notes asserted V3.0.1,
but installed version was subsequently clarified as uncertain. The empty `3.0.1.TXT` seen on UDISK
does not establish application version or downgrade behavior. On 2026-09-20,
two authorized transfers of a PN 1.13 startup-lamp diagnostic did not produce
its visible marker, although the lamp key works. Next steps require verified
RX update instructions or application-flash readback; see the
[identity investigation](RX-IDENTITY-MARKER-PN1.13-2026-09-20.md).

Live SWD inspection now identifies N32L406 and L1 protection. Battery-first,
three-wire operation permits SRAM/timer measurements, but not flash backup.
A 2,348-sample Digital capture has a different layout from all stored RX images
and an approximately 800-tick repeated-audio hold. Exact PN1.13 normal execution
is incompatible with the observed state. Resolve the actual application/update
path before attributing device results to further PN patches; see
[live findings](RX-SWD-FINDINGS-2026-09-20.md).

## 6. Not planned

- Changing the tone carrier or cadence on the transmitter: the receiver decodes the
  current patterns and the improvements worth making are on the receiver side.
- A sixth Settings row: the five rows fill the screen; NVP and Zero live on the
  Length screen for that reason.
- Anything requiring the vendor source (task priorities, stack sizes, RTOS config).
