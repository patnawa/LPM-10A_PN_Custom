<div align="center">

# LPM-10A PN Custom Firmware

**RX update solved and RX PN 1.12 running on hardware (2026-09-21).** The receiver
bootloader only programs a **container** (32-byte name, `payload_off 0x1000`, length,
end, image at 0x1000 — the same layout as FNIRSI's TX file); the raw RX image FNIRSI ships
is silently ignored (`UNKOWN.TXT`). Copy the `*-update.bin` that `rx-sdk/build.py` now
emits with Explorer; the probe programs it in about a second and reboots. Proven by watching
the bootloader's SRAM over SWD, then by stack return addresses that exist only in PN 1.12.
The owner reports the one-second Digital tail is gone and the feedback is finer than stock.
PN 1.14 then gave Analog its own pitch (1.25 kHz vs 2.5 kHz) with a chirp on every key beep,
and PN 1.15 made the beep rate report the cable rather than the sensitivity knob after a
live measurement showed the front end has three effective gain steps and the knob was
scaling the strength score ~20x ([RX sensitivity measurements](docs/RX-SENSITIVITY-2026-09-21.md)).
**Earlier RX "device pass" reports (PN 1.3–1.8) were tests of the factory firmware**, since
no PN image had ever been installed. See [the procedure, evidence and rollback](docs/RX-UPDATE-PROCEDURE-2026-09-21.md).

**Development snapshot, 2026-09-20:** [TX PN 2.14 / RX experiments and investigation](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/tone-snapshot-2026-09-20)
is an archival prerelease. The owner is keeping the currently working devices;
no new RX installation is recommended by this snapshot. **RX PN 1.13 uptake
is unconfirmed and the Digital audio tail remains unresolved.** Live RX state
differs from all stored RX images, so earlier filename-based device-pass reports
do not authenticate an installed PN version. See the
[snapshot notes and exact artifact checksums](docs/releases/TONE-SNAPSHOT-2026-09-20.md).
The previously published releases below remain available; TX PN 2.12 retains
the GitHub Latest designation.

**TX release: PN 2.12 (2026-09-19).** Port FLASH now uses PHY link status;
the owner confirms the blink fix on a D-Link gigabit switch. Includes the
PHY setup, FLASH timing, battery monitoring and settings-save corrections.
See the [release notes](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/v2.12) and
[Port FLASH investigation](docs/PORT-FLASH-STATUS-2026-09-19.md).

**Archived TX PN 2.14 candidate: Digital / Analog only.** Removes Sync32 and Pulse
test from the tone menu after the owner's Sync32 failure report, retaining
`Digital 454 kHz` / `Analog 825 Hz` labels and the established waveforms.
Also fixes a RIGHT-key carrier-cache defect found in the
[detailed performance audit](docs/TONE-PERFORMANCE-AUDIT-2026-09-20.md).
RX PN 1.10 supports these modes; no RX update is
required for this TX menu change. See the
[two-mode candidate and verification](docs/TONE-RECOVERY-PN2.14-2026-09-20.md).
คำอธิบายภาษาไทย: [ความหมายของ Digital 454 kHz / Analog 825 Hz](#tone-probe-frequencies).
See the latest [owner device feedback](docs/TONE-DEVICE-FEEDBACK-2026-09-20.md).
The owner reports using RX PN 1.12 / TX PN 2.14 files and basic tone-function operation;
the installed RX image has not been authenticated.
PN 2.12 remains the published TX release.

**Archived RX PN 1.13 test candidate: independent audio countdown.** Moves
the shared pulse/quiet-gap countdown to the existing speaker timer, so delayed
TIM1 delivery cannot stretch a pulse while TIM5 continues. Detection and
strength processing remain PN 1.12. This investigates the owner's long Digital
tail and long key-confirmation sound. The owner tried PN 1.13 and reports the
symptom is unchanged; this candidate has not resolved the device issue.
Use the same TX PN 2.14. See the
[PN 1.13 file, verification and device checks](docs/TONE-AUDIO-CLOCK-PN1.13-PN2.14-2026-09-20.md).

**Video follow-up:** the supplied clip shows repeated short beeps for about
0.8–1.0 seconds after TX Digital → Analog. Its roughly 50 ms pulse pattern
differs from PN 1.13's expected normal 30 ms pulses; installed-image identity
remains unverified. Retrying the stock filename left the symptom unchanged;
the RX UDISK's empty `3.0.1.TXT` does not authenticate the running image.
See the [clip analysis and live-drive findings](docs/TONE-CLIP-DIAGNOSIS-2026-09-20.md)
and the [startup lamp identity diagnostic](docs/RX-IDENTITY-MARKER-PN1.13-2026-09-20.md).
After both authorized diagnostic transfers (streamed write and native Windows
file copy), the owner reports no automatic startup lamp, although the lamp key
works normally. The identity check has not passed; host file-copy success must
not be treated as confirmed application uptake. RX update requirements remain
unresolved; a [vendor support draft](docs/RX-UPDATE-SUPPORT-REQUEST-2026-09-20.md)
collects the questions needed to proceed.

**Live SWD investigation:** ST-Link V2 now reads the receiver's chip identity,
RAM and timers. `DBG_ID` identifies N32L406 with 128 KiB flash and 24 KiB SRAM;
L1 read protection prevents application-flash backup. Battery-first operation
with three-wire SWD works. A 2,348-sample Digital/Pause recording shows a
different application layout from every stored V3.0.0-based PN image and
eight new pulses after the last detection refresh. Sound scheduling ends
about 0.82–0.87 s after that refresh while both timers keep advancing;
this is not evidence of a tenfold timer slowdown. The captured state is
incompatible with normal execution of exact PN 1.13. Its installed version
remains unknown. No firmware or option bytes were written during this inspection.
See the [live findings](docs/RX-SWD-FINDINGS-2026-09-20.md) and
[measured Digital release](docs/RX-LIVE-DIGITAL-RELEASE-2026-09-20.md).

**Preserved local RX PN 1.12 candidate: upper-rail Digital uncertainty.** Includes
PN 1.11 tracking and prevents an older exact-code span from supplying normal
strength when all newest 16 ADC values are at the upper rail. Reuses the existing
100 ms uncertainty indication; lower-zero and brief-contact behavior remain.
Use with the same TX PN 2.14. See the
[PN 1.12 files, tests and limits](docs/TONE-OVERLOAD-PN1.12-PN2.14-2026-09-20.md).
The owner reports both modes receive and cable sweeping is more accurate on
the owner-reported RX PN 1.12 / TX PN 2.14 files. Later feedback identifies an open Digital
issue: sound continues about one second after moving away or pressing TX Pause;
Analog does not show this delay. Other tested functions were reported passing.
Fluke comparison remains unperformed. See the
[scoped owner feedback](docs/TONE-DEVICE-FEEDBACK-2026-09-20.md).

**Preserved RX PN 1.11 candidate: faster Digital tracking and finer Analog feedback.**
Adds robust local B6 acquisition with legacy fallback, overlapping updates after
16 new samples, recent code-based strength, and short interpolated Analog beeps.
Exact integer DFT reduces profiled Analog work by about 74%. The new RX binary
awaits device testing; comparison with Fluke has not been performed. See
[RX PN 1.11 / TX PN 2.14 and verification](docs/TONE-TRACKING-PN1.11-PN2.14-2026-09-20.md).
The [evidence review](docs/TONE-GOAL-EVIDENCE-2026-09-20.md) distinguishes software
results from the device and comparison results still needed.

**RX PN 1.9 local candidate: robust code-based strength.** Uses code-associated
group medians to reduce misleading strength from impulses, with a distinct
longer pulse for readings unsuitable for comparison. See the
[implementation and device-test plan](docs/RX-ROBUST-PN1.9-2026-09-20.md).
Hardware validation is pending; PN 1.8 remains the published owner-tested RX build.

**RX prerelease: PN 1.8 pinpoint feedback.** Finer beep intervals span a wider
digital strength range, with a small deadband to reduce jitter. Includes the
earlier RX reliability and feedback fixes. **104 CPU test groups passed;
the owner reports a device test pass on 2026-09-19.** Download the
[RX prerelease](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/rx-v1.8) and see the
[comparison and validation report](docs/RX-PINPOINT-PN1.8-2026-09-19.md).
The previous PN 1.7 release is preserved.

Unofficial firmware for the FNIRSI LPM-10A network cable tester and probe,
with changes verified under CPU emulation.
The owner confirms PN 2.12 Port FLASH and reports an RX PN 1.8 device pass; broader TX/RX validation
is tracked separately in the release notes.
This is not certification of every hardware revision or measurement condition.

![version](https://img.shields.io/badge/TX-PN%202.12-orange)
![receiver](https://img.shields.io/badge/RX-PN%201.8%20experimental-yellow)
![patches](https://img.shields.io/badge/TX%20patches-28-blue)
![languages](https://img.shields.io/badge/UI-English%20%2F%20%E0%B9%84%E0%B8%97%E0%B8%A2-blue)
![verified](https://img.shields.io/badge/CPU%20verification-passed-brightgreen)
![hardware](https://img.shields.io/badge/TX%20Port%20FLASH-owner%20confirms%20fix-brightgreen)
![license](https://img.shields.io/badge/tooling%20license-MIT-lightgrey)
[![release](https://img.shields.io/github/v/release/patnawa/LPM-10A_PN_Custom?label=download)](https://github.com/patnawa/LPM-10A_PN_Custom/releases/latest)

<img src="docs/img/length_screen.png" alt="Length screen: stock vs PN Custom, NVP and Zero calibration" width="1000">

</div>

---

## Downloads and current status

**TX PN 2.12: Port FLASH fix confirmed by the owner on a D-Link gigabit switch.**
PN 2.11 had intermittent long pauses with the switch port LED staying on.
The [new investigation](docs/PORT-FLASH-STATUS-2026-09-19.md) reproduces a GPIO
input pattern that indefinitely restarts the hold timer. The
[PN 2.12 release](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/v2.12)
uses direct PHY link status and includes all PN 2.11 fixes. CPU-tested, with
Port FLASH device confirmation on 2026-09-19. Other TX changes await device
validation.

**RX PN 1.8: finer pinpointing feedback, owner-reported device pass.** The
[RX prerelease](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/rx-v1.8)
replaces PN 1.7's five broad grades with interpolated beep intervals and a wider
feedback range for strong signals. Changes below 3 ms are held to reduce jitter.
It retains the earlier detection, release, ADC, battery and DFT behavior. Quantitative range and
cable-selection measurements were not supplied with the device pass.

**Full TX/RX audit.** The expanded
[firmware audit](docs/FULL-FIRMWARE-AUDIT-2026-09-19.md) reproduced and fixed seven
defects: Port FLASH/PHY recovery, TX battery monitoring and settings saving,
and RX sample handoff and strong-signal overflow. See the
[TX release notes](LPM-10A/Firmware%20File/PN2.12-README.txt),
[RX PN 1.5 audit notes](LPM-10A/Firmware%20File/RX-PN1.5-README.txt) and
[firmware profiles](LPM-10A/Firmware%20File/experimental/README.md).
The images are CPU-tested. PN 2.11's intermittent FLASH pauses led to
the owner-confirmed PN 2.12 correction above.
The RX PN 1.8 device pass is recorded in its separate pinpointing report.
Published PN 2.9 / PN 1.4 files are preserved.

The owner reported "test pass on device" on 2026-09-19 for
**TX PN 2.8 / RX PN 1.3**, and **TX PN 2.9 / RX PN 1.4** incorporates subsequent
fault-handling and ADC timeout margin bug fixes. See the
[implementation and validation report](docs/ROADMAP-IMPLEMENTATION-2026-09-19.md).

| Device | Release | Firmware | Status |
|---|---|---|---|
| TX tester | [PN 2.12](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/v2.12) | `LPM-10A-TX_PN2.12-portflash-status.bin` | CPU-verified; owner confirms Port FLASH fixed |
| RX probe | PN 1.17 (local, [procedure](docs/RX-UPDATE-PROCEDURE-2026-09-21.md)) | `experimental/APP_LPM-10RX_PN1.17-smooth-gain-update.bin` | **Running on the owner's probe 2026-09-21**: PN 1.12 detection + Analog one octave below Digital with mode chirps (1.14) + beep rate normalised by the measured knob gain step (1.15) + rejected windows bridged 160/60 ms (1.16) + knob level 3 gain dead zone closed and half-step rhythm smoothing (1.17); all measured live over SWD ([measurements](docs/RX-SENSITIVITY-2026-09-21.md)); copy the `-update.bin` container, not the raw image |

**Use the file for the correct device; TX and RX firmware are not interchangeable.**
Each release includes device-specific notes and a SHA-256 checksum file.
The RX build requires the verified V3.0.0 input file. Rollback to the factory
V3.0.0 image works with the same container procedure (verified 2026-09-21); the
probe's earlier 3.0.1 build has no file and cannot be restored.

The earlier PN 2.8 / RX PN 1.3 hardware report is a general functional pass, not a detailed
range/noise or PoE-supply test matrix. The [implementation report](docs/ROADMAP-IMPLEMENTATION-2026-09-19.md)
documents the fixes and the remaining limitations. Earlier binaries remain available.

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
| Length stability | one CSD run shown as is (±0.3 m scatter at 14 m) | **four runs averaged per pair**; `~` warns when only 1–3 runs yielded a reading; a test takes four times longer |
| Length result | sticky previous readings, whole numbers and possible display overflow | fresh calibrated values; zero-result pairs show **`< 2 m`** (`< 200 cm`, `< 7 ft`), not proof of a fault location; `OVR` replaces an unrepresentable display value |
| Low battery | one sample < 3150 mV starts an uncancellable 30 s shutdown | needs 3 consecutive samples; cancels on recovery/charging; debounce cleared on cancellation and explicitly at startup |
| Battery gauge | 4 steps | 10-step Li-ion curve, red at ≤ 20 % |
| Auto Off | keeps counting while the SCAN tone or FLASH blink is running, so a trace ends with the unit switching itself off | held (and restarted) while a tone or blink session is active; unchanged elsewhere. Correction: PN 1.0–2.2 held it during SCAN only — the FLASH branch compared the wrong state number (8, QC Test, instead of 6); fixed in PN 2.3 |
| Settings save | 204 bytes leaked per save; calibration saved only at power-off | checked static writer for explicit save, default setup, power-off and changed Length calibration; no heap allocation |
| Runtime reliability | application queue calls in SysTick; timer-fed watchdog | application callbacks deferred to a service task; watchdog requires service-task progress; fault details retained across warm reset and shown in About |
| Fonts | thin serif 8×16 ASCII, Song-style Chinese | **Ubuntu Sans Mono** (8×16, 6×12) for English; **Sarabun** 13 px cells for Thai; all open-licensed |
| Language | Chinese / English, picker on first boot | **ไทย / English** on every screen (PN 2.0); picker on first boot and after a factory reset; machine-translated English corrected |
| SCAN modes | labelled "Noiseless" and "Normal" | labelled **Digital** (the 0xB6B6 coded pattern the probe decodes) and **825 Hz** (a plain keyed tone for any analogue probe) |
| SCAN timing | one high tick lost at digital wrap, debug logging in the timer path, stale carrier state after pause | exact 50-tick slots, SCAN timer-path logging bypassed, carrier correctly driven on resume (PN 2.6) |
| Cable Test | Back leaves the screen from every step; "Result error!!" is painted under the Test Retry button | **Back returns to the Switch / Far end choice** from the armed and result screens (PN 2.1); the error line sits above the button, which moved 9 px down |
| FLASH (port blink) | fixed phase counter, no link-aware hold | full minimum 1500 ms hold / 1000 ms PHY-off; failed negotiation backs off 4 → 8 → 16 s and retains the working window for the session. Links needing >16 s can still fail; see the [audit](docs/RELIABILITY-AUDIT-2026-09-19.md) |
| PoE screen | the voltage is drawn once per detection, from the sample a tick or two after the first one above 40 V (the rising edge), and not refreshed while the screen is shown (the two wires of a pair can even disagree); with no supply the screen stays blank, because the 3.5 s "no supply" timeout fires once per power-on (usually before the screen is ever opened) and is never re-armed | **the voltage column is refreshed every 0.5 s** while a supply is present, every wire from one latched sample, and cleared the moment the supply goes; **"Detecting..."** on entry, **"No PoE"** 3.5 s later without a supply, every time (PN 2.3); "Standard : Yes / No" instead of "Standar / UnStandar" |
| Identity | About screen reports `Software:V2.0.7` and `http://www.fnirsi.cn` | reports `Software:PN 2.12` and this repository's URL; the bootloader-facing image name is untouched |

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

These instructions are for the **TX tester only**. Download PN 2.12 from the
[TX release](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/v2.12), together with
`PN2.12-README.txt` and `PN2.12-SHA256SUMS.txt`. The tested binary retains its
`-portflash-status.bin` filename and is stored under `LPM-10A/Firmware File/experimental/`.
The SDK's default `LPM-10A-TX_PN2.9.bin` is an unreleased base comparison build;
use the PN 2.12 file for all current release features.

1. Verify the download:
   ```
   certutil -hashfile LPM-10A-TX_PN2.12-portflash-status.bin SHA256
   3d2db80f8288744191fe1ddb2855a83b900166dd365e1583c6270dfb460a0076
   ```
2. Power the tester off. Hold **M + Power** until the firmware update screen appears.
3. Connect USB-C; a removable drive appears.
4. Copy [`LPM-10A-TX_PN2.12-portflash-status.bin`](LPM-10A/Firmware%20File/experimental/LPM-10A-TX_PN2.12-portflash-status.bin)
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

The PN 2.8 TX / PN 1.3 RX general hardware pass was reported on 2026-09-19;
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
- Settings > About reads `Software:PN 2.12` and shows `github.com/patnawa/LPM-10A_PN_Custom`.
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
redraws the four readings at once, no re-measure needed. NVP, Zero and unit are
saved when leaving Length in the PN 2.8 release, as well as with the other
settings at power-off. Factory Reset returns
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
python build.py --write             # emit the unreleased base comparison build
python build.py --portflash-status --write  # reproduce the PN 2.12 release
python verify.py                    # full base-profile verifier
python -m unittest test_portflash_status -v # release-profile regressions
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
    LPM-10A-TX_PN2.6.bin              earlier owner-tested TX release
    LPM-10A-TX_PN2.7.bin              previous TX release (preserved)
    LPM-10A-TX_PN2.8.bin              earlier base candidate
    LPM-10A-TX_PN2.9.bin              unreleased base candidate
    PN2.12-README.txt                 current TX changes and update notes
    PN2.12-SHA256SUMS.txt             current TX binary checksum
    experimental/LPM-10A-TX_PN2.12-portflash-status.bin  current TX release
    experimental/APP_LPM-10RX_PN1.8-pinpoint.bin        current RX prerelease
    experimental/ROADMAP-MANIFEST.json            tested image hashes and profiles
    LPM-10A-TX_V2.0.7_260610.bin      stock image: NOT included, put FNIRSI's copy here to build
    MOD-README.txt                    historical PN 2.4 notes and checklist
    FORMULA-AUDIT.md                  every measurement formula, with verdicts
    sdk/                              the transmitter toolkit: patches, assembler, verifier, fonts
    sdk/thai/                         the Thai UI: cell font, drawers, wording, screen emulator, mock-ups
    APP_LPM-10RX_PN1.0.bin            earlier receiver image (battery fix)
    APP_LPM-10RX_PN1.1-digital-experimental.bin   earlier RX digital prerelease
    APP_LPM-10RX_PN1.2-reliability-experimental.bin   previous RX prerelease
    RX-PN1.8-README.txt               current RX notes, scope and validation
    RX-PN1.8-SHA256SUMS.txt            current RX binary checksum
    RX-README.txt                     historical PN 1.0 notes
    rx-sdk/                           the receiver toolkit: patches, verifier, disassembler
docs/img/                             the images on this page (screens are rendered from the firmware's own layout tables and glyphs)
```

## Receiver (probe)

The probe has its own firmware, audit and toolkit:
[`docs/RX-AUDIT.md`](docs/RX-AUDIT.md) and
[`LPM-10A/Firmware File/rx-sdk`](LPM-10A/Firmware%20File/rx-sdk/README.md).
[RX PN 1.8](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/rx-v1.8)
provides interpolated digital feedback with 30 ms pulses and quiet gaps from
160 to 20 ms as strength rises. A small output deadband steadies the sound,
and a wider feedback range distinguishes more strong inputs. It retains
PN 1.7's trimmed strength estimate and stops repeats
after a rejected window or 300 ms without an accepted result. An active tone
finishes normally; the 800 ms power keepalive remains separate.

It includes PN 1.6's mode/gate sample ownership and stable beep scheduling,
plus the earlier ADC, battery, watchdog and strong-signal DFT fixes. **104 CPU
test groups passed**, and the owner reports a **device test pass on 2026-09-19**.
The faster release can make weak or intermittent signals sound less continuous.
It remains an experimental prerelease; quantitative cable selectivity, range
and compatibility with other hardware revisions are not established.

Match TX **Digital** to RX digital mode, or TX **825 Hz** to RX analog mode.
Sampling rates and PN 1.6's digital eligibility rules are retained. The internal
RX vendor version remains `3.0.0`; identify the custom
image by its filename and checksum.

Update-mode entry was reported on 2026-09-18: with the probe off, hold SCAN and
connect USB to expose the "UDISK" drive. The owner subsequently reported testing
the new RX firmware successfully. Earlier notes asserted the probe ran V3.0.1;
the owner later clarified that its previous installed version was uncertain.
The build requires the verified V3.0.0 receiver input image.
Confirm applicability and a stock recovery path for your unit before flashing;
do not apply the TX procedure or TX binary to the probe. See
[RX release notes](LPM-10A/Firmware%20File/RX-PN1.8-README.txt).

## Tone probe frequencies

**Digital 454 kHz และ Analog 825 Hz บอกความถี่คนละส่วนของสัญญาณ**
TX PN 2.14 รุ่นทดลองมีเพียงสองโหมดนี้ โดยคงรูปคลื่นและวงจรส่งเดิม
ผู้ใช้ยืนยันว่า Digital/Analog ของ PN 2.13 ใช้งานได้ ส่วน Sync32 ไม่ตอบสนอง
จึงนำ Sync32 และ Pulse test ออกจากเมนูตามคำขอ โดย RX PN 1.10 เดิมยังใช้ต่อได้

| ชื่อบนหน้าจอ TX | ความหมาย | โหมด RX ที่ใช้คู่กัน |
|---|---|---|
| **Digital 454 kHz** | ใช้คลื่นพาหะประมาณ 454,000 รอบ/วินาที แล้วเปิด–ปิดตามรหัสดิจิทัล B6 เพื่อให้โพรบตรวจหารหัสที่ตรงกัน | Digital; ใช้กับ RX รุ่นก่อนหน้าได้ |
| **Analog 825 Hz** | ใช้คลื่นพาหะประมาณ 454 kHz เช่นกัน แต่เปิด–ปิดเป็นจังหวะประมาณ 825 รอบ/วินาที ให้โพรบตรวจหาจังหวะนี้ | Analog |

**454 kHz คือความถี่พาหะ (carrier frequency)** ส่วน **825 Hz คือความถี่ของ
จังหวะเปิด–ปิดพาหะ (modulation frequency)** จึงไม่ควรนำตัวเลขสองค่านี้มา
เปรียบเทียบว่าค่าสูงกว่าจะค้นหาสายได้ดีกว่า ทั้งสองค่าไม่ใช่ความถี่เสียงบี๊บ
แจ้งความแรงที่โพรบสร้างขึ้น และเป็นค่าประมาณจากการตั้งค่าในเฟิร์มแวร์
ไม่ใช่ค่าที่วัดจากเครื่องของผู้ใช้

Digital มีอัตราชิปประมาณ 198 ชิป/วินาที หมายถึงจำนวนช่วงรหัสต่อวินาที
ซึ่งแยกจากความถี่พาหะ 454 kHz เสียงบี๊บของ RX ใช้บอกความแรงที่ตรวจจับได้
ให้ใช้โหมด RX ตรงกับ TX ตามตารางด้านบน

บันทึกการทดลองเดิม: Sync32 ไม่ผ่านการใช้งานจริงที่ผู้ใช้รายงาน แม้จำลอง CPU
แล้วผ่าน ส่วน Pulse test เป็นพัลส์สำหรับออสซิลโลสโคปและไม่มีรหัสหรือจังหวะ
825 Hz ให้โพรบตรวจจับ จึงไม่เหมาะเป็นโหมดค้นหาสายปกติ ทั้งสองโหมดไม่มีใน
เมนู PN 2.14 แล้ว ดู [บันทึกการตรวจสอบ](docs/TONE-RECOVERY-PN2.14-2026-09-20.md)

**ผลตรวจเชิงลึก: ยังไม่ใช่ประสิทธิภาพสูงสุด** พบข้อผิดพลาดปุ่มขวาของ TX
ที่เปลี่ยนสถานะขาส่งแต่ไม่ล้างค่าจำสถานะพาหะ แก้ใน PN 2.14 แล้ว โดยคง
รูปคลื่นและแรงขับเดิม ผ่านการทดสอบ TX 60 กลุ่ม ผลเครื่องจริงล่าสุดอยู่ใน
[บันทึกจากเจ้าของ](docs/TONE-DEVICE-FEEDBACK-2026-09-20.md) โดยยืนยันคู่ RX PN 1.12 / TX PN 2.14 แล้ว

ผลตรวจ RX เดิมพบว่า Digital อาจหลุดเมื่อ noise กระชากหรือความแรงเปลี่ยนเร็ว
ส่วน Analog มีเพียงสามระดับเสียงและปรับเสียงค่อนข้างช้า จึงพัฒนา
**RX PN 1.11** เพิ่มการตรวจรหัสแบบช่วงสั้นร่วมกับวิธีเดิม อัปเดตหลังรับใหม่
16 samples ประมาณทุก 80 ms หลังการรับชุดแรก และวัดความแรงจากช่วงรหัสล่าสุด
Analog ใช้บี๊บ 30 ms กับช่วงเงียบที่ไล่ระดับ พร้อมลดภาระคำนวณ DFT โดยผลเท่าเดิม

**RX PN 1.12 รุ่นทดลองล่าสุด** เพิ่มการแก้กรณีพบรหัสในข้อมูลเก่า แต่ข้อมูล
Digital ล่าสุด 16 จุดค้างขอบบน ADC ทั้งหมด โดยใช้เสียงแจ้งว่าความแรงไม่น่าเชื่อถือ
บี๊บ 100 ms เว้น 160 ms แทนการบอกความแรงเก่า การกวาดผ่านช่วงสั้นและข้อมูล
ที่เป็นศูนย์ยังใช้พฤติกรรมเดิม ดู [ไฟล์และผลทดสอบ PN 1.12](docs/TONE-OVERLOAD-PN1.12-PN2.14-2026-09-20.md)

ตัวเลขการทดสอบซอฟต์แวร์มาจาก ADC จำลองที่ป้อนเข้าโค้ด ARM จริง ไม่ใช่ผลวัดระยะ
เจ้าของรายงานว่า Digital/Analog รับได้ทั้งคู่ กวาดสายแม่นขึ้น และฟังก์ชันอื่นที่ทดลองก็ผ่าน
แต่ผลติดตามพบว่า Digital ยังดังต่อประมาณ 1 วินาทีหลังย้ายโพรบออกหรือกด Pause ที่ TX
ส่วน Analog ไม่มีอาการหน่วงนี้ ปัญหาเวลาหยุดเสียง Digital ยังอยู่ระหว่างตรวจสอบ
เป็นผลตอบรับเชิงคุณภาพ
โดยยังไม่มี Fluke สำหรับเทียบ
ดู [ผลตรวจเดิม](docs/TONE-PERFORMANCE-AUDIT-2026-09-20.md),
[การปรับปรุงและไฟล์ RX PN 1.11](docs/TONE-TRACKING-PN1.11-PN2.14-2026-09-20.md)
และ [วิธีทดสอบเปรียบเทียบ](docs/TONE-PROBE-COMPARISON-PROTOCOL.md)

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

- The [reliability audit](docs/RELIABILITY-AUDIT-2026-09-19.md) records remaining
  limits after PN 2.7: links needing >16 s can still fail; partial averages are
  marked but retained; vendor pair voting can conceal pair differences; raw PHY
  status/range validation remains open. Overflow wrapping and stale calibration
  redraws are fixed. A general hardware pass does not prove every edge case.
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
- PN 2.8 defers all ten SysTick application callbacks into a service task and
  retains the SCAN logging bypasses. Pending events can coalesce during a stall.
  The TX watchdog checks service-task progress, not every application task.
- Calibration autosave runs on Length exit. Power loss while editing or during
  flash writing can still lose changes; this is not a power-fail journal.
  Fault records survive application warm reset, not battery removal.
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
