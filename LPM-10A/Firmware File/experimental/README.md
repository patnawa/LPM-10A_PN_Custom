# Experimental builds

**RX PN1.30 clean-strength release (2026-09-24):** the owner reports "1.30 test pass flicker fixed" on
the probe. Built from the exact PN1.29 image: the Digital strength estimator ignores the samples that
hold a chip edge (the transmitter's 5.05 ms chip drifts through the receiver's 5 ms slot's last-2-ms
readings every ~0.55 s; PN1.29 read 23 % of its windows 1.6–6 dB low and flickered between two levels
when a still probe sat 0.6–1.0 dB above a level threshold), the gain decides once per displayed window
(Digital ~0.28 s, Analog 21 ms) instead of every 500 ms, a saturated window above the lowest gain counts
1.2 dB lower and never lowers the display, and an unsaturated drop of 2.5 dB or more moves half way per
window. Emulator: 0 level changes on a steady signal (PN1.29 0.8–1.2/s), a strong pair settles in 0.73 s
(1.5 s), Analog in 66 ms, a 6 dB drop shows in 0.57 s; scorecard verdicts as PN1.29 on every Digital row
and all but one boundary row in Analog, visit-to-visit spread down from 0.043 to 0.007 (Digital) and
0.015 to 0.001 (Analog). The default build (`python build.py --write`, profile pn1.30) and
[published release](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/rx-v1.30) retain the exact tested bytes archived here.
[Default RX update file](../APP_LPM-10RX_PN1.30-clean-strength-update.bin),
[archived copy](APP_LPM-10RX_PN1.30-clean-strength-update.bin), [raw image](APP_LPM-10RX_PN1.30-clean-strength.bin),
[notes and checklist](RX-PN1.30-README.txt), [checksums](RX-PN1.30-SHA256SUMS.txt),
[analysis](../../../docs/RX-CLEAN-STRENGTH-PN1.30-2026-09-24.md).
Roll back with the [PN1.29 update file](../archive/APP_LPM-10RX_PN1.29-levels-update.bin).

**RX PN1.29 levels release (2026-09-23; superseded by PN1.30):** the owner reports "1.29 test pass work perfect" on the
probe. IntelliTone-style display: strength against the knob's reference is shown as ten absolute
rhythm levels 3 dB apart (in Digital each level's pulse period is 15 % longer than the next), with
no peak memory (while audio continues a weaker window eases the shown strength down; a 3 dB drop
shows in about 0.3 s in Digital), no mute and no Compare ceiling; the gain may step down again at
the next 0.5 s callback; Digital/Analog tracing may use the full gain at every knob position. Knob
fully up = Locate, about a fifth of the travel = Isolate. In the emulator's cabinet scorecard it
identifies the toned pair in 14/24 Digital and 19/24 Analog cases (PN1.27: 4/24 and 9/24). The
[published release](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/rx-v1.29)
retains the exact tested bytes archived here (`python build.py --profile pn1.29 --write` rebuilds them).
[Release copy](../archive/APP_LPM-10RX_PN1.29-levels-update.bin),
[archived copy](APP_LPM-10RX_PN1.29-levels-update.bin), [raw image](APP_LPM-10RX_PN1.29-levels.bin),
[notes and procedure](RX-PN1.29-README.txt), [checksums](RX-PN1.29-SHA256SUMS.txt),
[analysis](../../../docs/RX-INTELLITONE-ANALYSIS-2026-09-23.md).
Roll back with the [PN1.27 update file](../archive/APP_LPM-10RX_PN1.27-knob-update.bin).

**RX PN1.28 candidate (2026-09-23; on the probe: "detects, but not accurately", worse than PN1.27 → superseded by PN1.29):** with the knob all the way up the toned
pair plays the fastest rhythm and its neighbours slower by their dB deficit (PN1.27 played every
pair that saturates the full gain at 20 ms); the gain steps down every 0.5 s instead of 1 s.
Everything else is PN1.27's. [Update file](APP_LPM-10RX_PN1.28-pair-rank-update.bin) (copy this one),
[raw image](APP_LPM-10RX_PN1.28-pair-rank.bin), [notes and checklist](RX-PN1.28-README.txt),
[checksums](RX-PN1.28-SHA256SUMS.txt), [diagnosis and tests](../../../docs/RX-PAIR-RANK-PN1.28-2026-09-23.md).
Roll back with PN1.27.

**RX PN1.27 knob-reference release (2026-09-23; superseded by PN1.29):** the owner reports
"1.27 test pass" on the probe. The knob sets the rhythm's reference over its whole travel (lower
knob, slower rhythm), still audible from low on the knob; PN1.26's peak-relative mute, full gain,
NCV gain and louder beep kept. `python build.py --profile pn1.27` reproduces, and the
[published release](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/rx-v1.27)
retains, the exact tested bytes archived here.
[Release copy](../archive/APP_LPM-10RX_PN1.27-knob-update.bin),
[archived copy](APP_LPM-10RX_PN1.27-knob-update.bin), [raw image](APP_LPM-10RX_PN1.27-knob.bin),
[notes and checklist](RX-PN1.27-README.txt), [checksums](RX-PN1.27-SHA256SUMS.txt),
[diagnosis and tests](../../../docs/RX-KNOB-PN1.27-2026-09-23.md).

**RX PN1.26 candidate (2026-09-23; on the probe: heard from 5-10 %, knob had no effect → superseded by PN1.27):** full sensitivity at every
knob position; the lower half mutes pairs clearly weaker than the strongest one heard in
the last seconds (a lone cable always sounds), the strongest fastest. Keeps PN1.25's louder
beeps and NCV gain. [Update file](APP_LPM-10RX_PN1.26-relative-update.bin) (copy this one),
[raw image](APP_LPM-10RX_PN1.26-relative.bin), [notes and checklist](RX-PN1.26-README.txt),
[checksums](RX-PN1.26-SHA256SUMS.txt),
[analysis and tests](../../../docs/RX-RELATIVE-PN1.26-2026-09-23.md). Roll back with PN1.24.

**RX PN1.25 candidate (2026-09-23; on the probe: louder confirmed, knob still past half → superseded by PN1.26):** answers the field
report from a telephone PBX cabinet ("loud everywhere, cannot tell which line")
and "the knob must be turned half way before anything sounds". Upper half of the
knob = full-gain search with the PN1.24 rhythm; lower half = the knob sets a
reference level, weaker pairs slow down and go silent, the strongest keeps a
rhythm. NCV always gets the knob's gain; beeps are about 9.5 dB louder.
[Update file](APP_LPM-10RX_PN1.25-isolate-update.bin) (copy this one),
[raw image](APP_LPM-10RX_PN1.25-isolate.bin), [notes and checklist](RX-PN1.25-README.txt),
[checksums](RX-PN1.25-SHA256SUMS.txt),
[analysis and tests](../../../docs/RX-ISOLATE-PN1.25-2026-09-23.md).
Roll back with the PN1.24 update file.

**TX PN2.33 release (2026-09-24):** the owner reports "2.33 test pass" on the tester, paired with
RX PN1.29 (no RX change). Four Cable Test changes on top of PN2.27A, everything else PN2.27A's: the
nine wires are drawn in their LAN cable colours (T568B, white dashes on 1, 3, 5 and 7, the PN2.21
reading in the wire's colour; red open and yellow short still win); keys during the ~0.86 s test are
guarded (a second OK queues nothing, a test queued before leaving cannot paint over Home or SPEED,
Back leaves no stray "Test Retry", the button reads "Testing..." / "กำลังทดสอบ"); RX unit mode decides
a row from the median of its non-floating slots against the nearest ladder value with a common gain
(0.93 … 1.07) and turns maps no RX unit can produce (two wires on one remote pin, a wire on an open
shield, one level on every wire) into "Result error!!", replacing stock's overlapping ±5 % windows;
Switch mode decides and draws exactly as PN2.27A (PN2.19 rules) in the new colours. In the emulator
a 6↔7 or 8↔G crossing at +1 % gain no longer passes as straight and straight / crossover cables map
from −5 % to +6 % gain (56 Cable Test tests in `sdk/`); the device confirmation is the owner's report.
The default build (`python build.py --write`, profile pn2.33) and the
[published release](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/v2.33)
retain the exact tested bytes archived here.
[Default TX firmware](../LPM-10A-TX_PN2.33-cable-safe.bin),
[archived copy](LPM-10A-TX_PN2.33-cable-safe.bin), [notes](TX-PN2.33-README.txt),
[checksums](TX-PN2.33-SHA256SUMS.txt),
[Cable Test audit](../../../docs/TX-CABLE-TEST-AUDIT-2026-09-23.md),
[release notes](../../../docs/releases/v2.33.md).
Roll back with the [PN2.27A firmware](../archive/LPM-10A-TX_PN2.27A-analog-alignment.bin).

**TX PN2.28-2.30 candidates (2026-09-24; superseded by PN2.33):** three stages on top of PN2.27A,
each flashed by the owner the same day. **PN2.28** (`cable-check`) added a Switch-mode pair-partner
check (a wire reaching one pin outside its T568 pair = red miswire, several pins = yellow short,
shield grey "not tested", any fault = red LED and two beeps), the RX-unit nearest-ladder decision
with plausibility, the key/busy guard and the "Testing..." button; the owner: "2.28 tested", then
asked for "color per line base on lan cable". **PN2.29** (`cable-colours`) drew the wires in the T568B
colours with white stripes, decisions PN2.28's; the owner: "still yellow color no color show".
**PN2.30** (`cable-fix`) let a wire pass when its own partner sits among the lowest readings, replaced
the RX-unit trimmed mean by the median (two leaky loose wires shifted a good row, a code-review P1),
one beep, panel background; the owner: "every line cable test 1-8 show yellow" with a good cable in
a switch port. Cause (reproduced in the emulator and found independently by a code review of PN2.28):
the partner check assumed a switch port's centre-tap (Bob-Smith) paths between pairs read well above
the pair winding; on the owner's switch they read within a few counts of it, so every wire looked
joined to several pins and was called a short. PN2.33 withdraws the check and keeps the rest; bringing
it back needs the owner's PN2.30D readings. PN2.31 and PN2.32 were interim builds ("every color right
but ground show connect even my cable no ground", "ground status seems not fix": their grey shield line
read as a connected wire); they are not archived and not reproducible.
PN2.28 [firmware](LPM-10A-TX_PN2.28-cable-check.bin), [notes](TX-PN2.28-README.txt),
[checksums](TX-PN2.28-SHA256SUMS.txt); PN2.29 [firmware](LPM-10A-TX_PN2.29-cable-colours.bin),
[notes](TX-PN2.29-README.txt), [checksums](TX-PN2.29-SHA256SUMS.txt); PN2.30
[firmware](LPM-10A-TX_PN2.30-cable-fix.bin), [notes](TX-PN2.30-README.txt),
[checksums](TX-PN2.30-SHA256SUMS.txt). `python build.py --profile pn2.28` (`pn2.29`, `pn2.30`)
reproduces each byte for byte; `sdk/test_profiles.py` pins the digests. The **PN2.30D diagnostic**
[LPM-10A-TX_PN2.30D-diag.bin](LPM-10A-TX_PN2.30D-diag.bin) ([checksum](TX-PN2.30D-SHA256SUMS.txt),
`python cable_diag2.py --write`) is PN2.30 with the Switch-mode readings at the wire ends replaced by
each wire's two lowest readings and the pins they reach, e.g. `2  60 5  63`. Not a release: flash it,
photograph a good cable in the owner's switch, flash back; that photo is what a partner check that
tolerates the owner's switch needs.

**TX PN2.27A release (2026-09-22; superseded by PN2.33):** the owner reports a test pass with the named
TX image paired with RX PN1.24. It specializes carrier GPIO updates and aligns Analog
to nominal 816.832 Hz (817 Hz on screen), retaining the shared timer and Digital timing;
PN2.33 keeps all of it. `python build.py --profile pn2.27a` reproduces it, and
[release v2.27A](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/v2.27A)
retains the exact tested bytes.
[Roll-back copy](../archive/LPM-10A-TX_PN2.27A-analog-alignment.bin),
[archived copy](LPM-10A-TX_PN2.27A-analog-alignment.bin),
[notes](TX-PN2.27A-README.txt), [SHA256](TX-PN2.27A-SHA256SUMS.txt),
[analysis and tests](../../../docs/TX-TONE-PRECISION-PN2.27-2026-09-22.md).
The intermediate [PN2.27](LPM-10A-TX_PN2.27-tone-precision.bin) retains the
original Analog frequency and remains a historical comparison; its standalone
device status is unconfirmed.

**RX PN1.24 gain/precision release (2026-09-22; superseded by PN1.27):** the owner reports a device
test pass with no signal drop in Digital or Analog. Based on owner-tested
PN1.23G, it adds faster automatic gain recovery, full-window validation before
automatic gain decisions, sample-age checks, and less Analog analysis work
with unchanged spectral thresholds. Performance figures remain emulator
measurements. `python build.py --profile pn1.24` reproduces, and the
[published release](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/rx-v1.24)
retains, the exact tested bytes archived here.
[Release copy](../archive/APP_LPM-10RX_PN1.24-gain-precision-update.bin),
[archived copy](APP_LPM-10RX_PN1.24-gain-precision-update.bin),
[notes](RX-PN1.24-README.txt), [checksums](RX-PN1.24-SHA256SUMS.txt),
[analysis and test results](../../../docs/RX-GAIN-PRECISION-PN1.24-2026-09-22.md).
Use the `-update.bin` file with the RX bootloader.

**TX PN2.26 historical release (2026-09-22; superseded by PN2.27A):** the owner reports all functions passed on
the tester. [Firmware](LPM-10A-TX_PN2.26-qc-display.bin),
[release notes](TX-PN2.26-README.txt), [SHA256](TX-PN2.26-SHA256SUMS.txt).
It retains the classic automatic QC screen, normalizes measurement timing,
fixes the Init prompt overlap, and includes Length lifecycle/REF/progress
corrections. If QC requests Init, disconnect all cables and hold Right.
The explicit `--profile pn2.26` build reproduces this exact release; Q, R, PN2.24 and PN2.25
remain here as historical steps. See the
[device report and visual regression](../../../docs/TX-QC-DISPLAY-PN2.26-2026-09-22.md).

**TX PN 2.22 / 2.23 (2026-09-21; superseded by PN2.26):** on PN 2.21 the
owner held OK on the Length screen and saw ZERO go back to NVP instead of REF — PN 2.18 offered REF only
while a result was on screen and skipped it silently otherwise. PN 2.22 makes the hold always cycle
NVP → ZERO → REF: with a result, REF starts at the measured length and every step solves NVP as before;
without one, REF starts at 10.0 m, UP / DOWN dial it, and the next measurement is fitted to it once — the
measurement after that is an ordinary one, so a REF target left behind never re-fits NVP by itself.
On the unit PN 2.22's first REF read `REF 189.1`: it kept whatever the REF RAM cell held at power-up
whenever that was within 1 … 300 m. **PN 2.23** writes 10.0 m into the cell on every entry to the Length
screen; passed on the unit the same evening. [TX PN 2.23](LPM-10A-TX_PN2.23-ref-reset.bin)
(archived release v2.23; [checksum](TX-PN2.23-SHA256SUMS.txt)),
[TX PN 2.22](LPM-10A-TX_PN2.22-ref-anytime.bin) ([checksum](TX-PN2.22-SHA256SUMS.txt)),
[notes and the on-unit checklist](TX-PN2.22-2.23-REF-README.txt), `sdk/test_length_ref_anytime.py` (7 tests:
the whole measurement with a simulated PHY, the keys through the real dispatcher, the drawing through the
real GUI task) and `test_length_ref_reset.py` (8: the same on PN 2.23, plus the 189.1 reproduced and gone).

**TX PN 2.21 (2026-09-21, on the unit; superseded by 2.23):** the owner liked the
diag build's numbers — they tell the state of the cable, not just pass / fail — so PN 2.21 puts
the reading that decided each wire at its right end, in the wire's colour: Switch mode
`2   60` (the partner pin through the switch and the reading; `- 4037` = nothing reached), RX unit
mode `1655` (the ladder value = the remote pin: 1655 pin 1 … 3679 pin 8, 3900 shield). A swapped
single wire shows the wrong partner letter where stock only draws green; a crossover cable reads
like a straight one in Switch mode (whole pairs are swapped, as in stock) and shows its crossing
lines and values in RX unit mode. No change to any decision. Passed on the owner's unit the same day.
[TX PN 2.21](LPM-10A-TX_PN2.21-cable-values.bin) (release v2.21), [checksum](TX-PN2.21-SHA256SUMS.txt),
`sdk/test_cable_values.py` (6 tests on the real routines with simulated far ends and hum).

**TX PN 2.20 (2026-09-21, on the unit; superseded by 2.21):** PN 2.19 passed every function on the owner's unit; its
one report — the "Not connected" of an earlier unplugged test staying on screen after a Test Retry
with the cable in a switch or the RX unit — was reproduced on the CPU model (a retry never redrew
the text line) and fixed by [TX PN 2.20](LPM-10A-TX_PN2.20-cable-text-clear.bin)
([checksum](TX-PN2.20-SHA256SUMS.txt), `sdk/test_cable_clear.py`), release v2.20.

**TX PN 2.19 cable-robust (2026-09-21, on the unit):** the owner reported
random open / crossed wires in Cable Test on a cable not plugged into anything. Cause found
in the firmware: one ADC sample per sensed pin against a threshold 77 mV under the rail, no
"nothing connected" state. PN 2.19 reads eleven samples per pin and uses the median (the
highest for the far-end open test), switch mode needs a real short, all pins open prints
**Not connected** / ไม่พบปลายสาย, and the second mode is named **RX unit** / เครื่องรับ.
[TX PN 2.19](LPM-10A-TX_PN2.19-cable-robust.bin) (superseded by 2.20 above); the
[diag build](LPM-10A-TX_PN2.19-exp-cablediag.bin) prints the deciding numbers on the
result screen if the thresholds ever need checking on another unit —
[notes, checklist and the four-measurement protocol](TX-PN2.19-CABLE-README.txt),
[checksums](TX-PN2.19-SHA256SUMS.txt). Simulated far ends with hum on the real routines:
`sdk/test_cable_test.py`.

**TX PN 2.15 … 2.18 (2026-09-21, on the unit as part of PN 2.19):** four small functions
on top of PN 2.14, one per version so a problem bisects: PN 2.15 a run counter
(`1/4 … 4/4`) on the Length screen's Testing line during the four-run average;
PN 2.16 a `BATT / NVP / ZERO` line on the About screen; PN 2.17 a **Switch** row on
the SPEED screen with the speeds the link partner advertises (IEEE registers 5 and
10 — a 100 Mbps link on a `10/100/1000` port points at the cable); PN 2.18 a **REF**
target on the Length screen (hold OK: NVP → ZERO → REF) that dials a known cable
length and solves NVP from it. No measurement changes. PN 2.19 / 2.20 above include them all; on
their own, [TX PN 2.18](LPM-10A-TX_PN2.18-length-reference.bin); see the
[device notes and checklist](TX-PN2.16-2.18-README.txt),
[checksums](TX-PN2.16-2.18-SHA256SUMS.txt) (PN 2.15:
[notes](LENGTH-PROGRESS-PN2.15-README.txt), [checksum](LENGTH-PROGRESS-SHA256SUMS.txt))
and the [TX assessment](../../../docs/TX-NEXT-STEPS-2026-09-21.md). Each is verified
on the real screen, key and draw code under Unicorn (`sdk/test_length_progress.py`,
`test_about_values.py`, `test_speed_partner.py`, `test_length_reference.py`); the chain
passed on the owner's unit as PN 2.19 on 2026-09-21. Since this date every TX
version is a profile in `sdk/profiles.py` and `sdk/test_profiles.py` rebuilds each
file here byte for byte.

**2026-09-20 archival prerelease:** these candidates and their research are
preserved in the [development snapshot](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/tone-snapshot-2026-09-20).
The owner is retaining the working device setup. RX update acceptance remains
unresolved; live SRAM is incompatible with normal execution of the stored
PN 1.13 image. Earlier RX version names below describe selected files and owner
reports, not authenticated installed firmware. PN 1.13 and the lamp marker are
research artifacts, not a confirmed Digital-tail fix or a recommended update.
See [current status](../../../docs/releases/TONE-SNAPSHOT-2026-09-20.md).

**Latest RX PN 1.13 audio-clock test candidate:** moves the shared pulse and
quiet-gap countdown to the speaker timer. Detection and strength logic remain
PN 1.12. The owner tried PN 1.13 and reports the symptom is unchanged; the
physical issue remains unresolved. Retained test artifact:
[RX PN 1.13](APP_LPM-10RX_PN1.13-audio-clock.bin) and keep the same
[TX PN 2.14](LPM-10A-TX_PN2.14-tone-recovery.bin). See
[device notes](TONE-AUDIO-CLOCK-PN1.13-PN2.14-README.txt),
[checksums](TONE-AUDIO-CLOCK-SHA256SUMS.txt), and
[verification](../../../docs/TONE-AUDIO-CLOCK-PN1.13-PN2.14-2026-09-20.md).

The subsequent clip shows repeated roughly 50 ms pulses after TX Digital →
Analog, rather than a continuous one-second pulse. See the
[video diagnosis and unchanged filename-check result](../../../docs/TONE-CLIP-DIAGNOSIS-2026-09-20.md).
A separate [startup lamp identity diagnostic](../../../docs/RX-IDENTITY-MARKER-PN1.13-2026-09-20.md)
changes one byte of PN 1.13 to identify update uptake. It is not a tail fix or
a replacement normal release.

**Preserved RX PN 1.12 local candidate:** includes PN 1.11 tracking and replaces
old normal strength with uncertainty when the newest Digital tail is fully at
the ADC upper rail. Lower-zero and brief-contact behavior remain unchanged.
Download [RX PN 1.12](APP_LPM-10RX_PN1.12-overload.bin), paired with the same
[TX PN 2.14](LPM-10A-TX_PN2.14-tone-recovery.bin); see
[device notes](TONE-OVERLOAD-PN1.12-PN2.14-README.txt),
[checksums](TONE-OVERLOAD-SHA256SUMS.txt) and
[verification](../../../docs/TONE-OVERLOAD-PN1.12-PN2.14-2026-09-20.md).
Software tested. With owner-reported RX PN 1.12 / TX PN 2.14 files, both modes receive
and sweeping is more accurate. Later feedback reports an open Digital release
issue: sound continues about one second after moving away or pressing TX Pause.
Analog has no such delay.
See [owner feedback](../../../docs/TONE-DEVICE-FEEDBACK-2026-09-20.md).
No comparator result is available.

**RX PN 1.11 local tracking candidate:** robust Digital acquisition with the
established fallback, overlapping updates and recent strength; finer short
Analog feedback and exact integer DFT. Use with the two established TX modes.
Download [RX PN 1.11](APP_LPM-10RX_PN1.11-tracking.bin); see
[paired device notes](TONE-TRACKING-PN1.11-PN2.14-README.txt),
[checksums](TONE-TRACKING-SHA256SUMS.txt), and
[verification and remaining limits](../../../docs/TONE-TRACKING-PN1.11-PN2.14-2026-09-20.md).
This RX candidate awaits device testing. No Fluke comparison is available.

**TX PN 2.14 local two-mode candidate:** removes Sync32 and Pulse test from the
menu at the owner's request after Sync32 was silent with RX PN 1.10 digital
mode. Keeps `Digital 454 kHz` / `Analog 825 Hz`, using the unchanged PN 2.12
waveforms, and repairs the RIGHT-key carrier-cache invalidation. Download
[TX PN 2.14](LPM-10A-TX_PN2.14-tone-recovery.bin); see
[device notes](TONE-RECOVERY-PN2.14-README.txt),
[checksum](TONE-RECOVERY-SHA256SUMS.txt), and
[verification report](../../../docs/TONE-RECOVERY-PN2.14-2026-09-20.md).
The [detailed performance audit](../../../docs/TONE-PERFORMANCE-AUDIT-2026-09-20.md)
documents the prior RX limits. The separate RX PN 1.11 candidate above addresses
several of them; a TX-only update does not change the receiver algorithm.
The owner's current RX remains usable with these two modes. This TX image
has owner feedback linked above; the installed RX version is unconfirmed.
The filename does not denote a bootloader recovery image.

**Historical TX PN 2.13 / RX PN 1.10 Sync32 trial — reported failure:** the owner
reports Sync32 silent while Digital/Analog work, despite RX PN 1.10 digital mode.
Pulse test is for an oscilloscope and is expected to be rejected by the probe.
PN 2.14 removes both menu options. The following files preserve the trial;
they are not a recommended Sync32 upgrade. The trial added optional Sync32 tracing
and a TX Pulse test mode while retaining existing Digital and analog waveforms.
The tone labels are `Digital 454 kHz`, `Analog 825 Hz`, `Sync32 454 kHz` and
`Pulse test`. Digital/Sync32 show carrier frequency; Analog shows tone rate.
Download [TX PN 2.13](LPM-10A-TX_PN2.13-sync.bin) and
[RX PN 1.10](APP_LPM-10RX_PN1.10-sync.bin); see
[device notes](SCAN-SYNC-PN2.13-PN1.10-README.txt),
[checksums](SCAN-SYNC-SHA256SUMS.txt), and the
[paired report](../../../docs/SCAN-SYNC-PN2.13-PN1.10-2026-09-20.md).
Sync32 is more sensitive to clock mismatch in the model. The owner has now
tested this pair on hardware and reports the failure above; it is not published.

**RX PN 1.9 robust local experimental candidate:** uses medians grouped by the
expected digital code to improve cable-strength ranking in synthetic impulse
tests. Existing digital detection and sampling remain unchanged. A valid code
with an upper-rail-dominated or inseparable strength estimate gives distinct
100 ms pulses with 160 ms quiet gaps; normal feedback retains 30 ms pulses.
Build `python build.py --robust --write` and run
`python -m unittest test_rx_robust test_robust_profile -v` in `rx-sdk`.
The local candidate is [APP_LPM-10RX_PN1.9-robust.bin](APP_LPM-10RX_PN1.9-robust.bin);
see [device notes](RX-PN1.9-ROBUST-README.txt),
[checksum](RX-ROBUST-SHA256SUMS.txt), and
[implementation report](../../../docs/RX-ROBUST-PN1.9-2026-09-20.md).
It has not been published or flashed; hardware validation is pending.
PN 1.8 remains the current owner-tested experimental prerelease.

**Current owner-tested RX PN 1.8 pinpoint prerelease:** replaces PN 1.7's five broad digital
grades with an interpolated beep interval across a wider strength range.
Build `python build.py --pinpoint --write` and run
`python -m unittest test_rx_pinpoint -v` in `rx-sdk`.
Download [APP_LPM-10RX_PN1.8-pinpoint.bin](APP_LPM-10RX_PN1.8-pinpoint.bin);
see [device notes](RX-PN1.8-PINPOINT-README.txt),
[checksum](RX-PINPOINT-SHA256SUMS.txt), and
[implementation report](../../../docs/RX-PINPOINT-PN1.8-2026-09-19.md).
The owner reports a device test pass on 2026-09-19. The exact binary is published
in the [RX PN 1.8 experimental prerelease](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/rx-v1.8).
Quantitative cable-selection measurements were not supplied; PN 1.7 is preserved.

**Previous RX PN 1.7 precision prerelease:** digital cable tracing with five strength
levels, outlier-resistant grading, stable level transitions and faster release.
Build `python build.py --precision --write` and run
`python -m unittest test_rx_precision -v` in `rx-sdk`.
Download [APP_LPM-10RX_PN1.7-precision.bin](APP_LPM-10RX_PN1.7-precision.bin);
see [device notes](RX-PN1.7-PRECISION-README.txt),
[checksum](RX-PRECISION-SHA256SUMS.txt), and
[implementation report](../../../docs/RX-PRECISION-PN1.7-2026-09-19.md).
It includes PN 1.6; the owner reports a device test pass on 2026-09-19.
Quantitative range and cable-selection measurements were not supplied.
The exact binary is published in the
[RX PN 1.7 experimental prerelease](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/rx-v1.7).

**RX PN 1.6 local candidate:** corrects mode/gate sample ownership and digital
beep timing. Build `python build.py --followup --write` and run
`python -m unittest test_rx_followup -v` in `rx-sdk`.
Download [APP_LPM-10RX_PN1.6-followup.bin](APP_LPM-10RX_PN1.6-followup.bin);
see [device notes](RX-PN1.6-FOLLOWUP-README.txt),
[checksum](RX-FOLLOWUP-SHA256SUMS.txt), and
[implementation report](../../../docs/RX-FIXES-PN1.6-2026-09-19.md).
This intermediate image has no separate device pass; its fixes are included
in the PN 1.7 prerelease above.

This directory also retains the exact binaries published as
[TX PN 2.12](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/v2.12) and
[RX PN 1.5 experimental prerelease](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/rx-v1.5).
Their filenames and bytes are preserved from the tested candidates.

**Latest TX follow-up: PN 2.12 Port FLASH status.** For intermittent long-on
pauses reported on PN 2.11 / D-Link gigabit: the controller and indicator now
use PHY link status. Includes all PN 2.11 fixes; CPU-tested. The owner confirmed
the Port FLASH fix on the D-Link gigabit switch on 2026-09-19. Other functions
await separate device validation.
Build `python build.py --portflash-status --write` and run
`python -m unittest test_portflash_status -v` in `sdk`.
Download [LPM-10A-TX_PN2.12-portflash-status.bin](LPM-10A-TX_PN2.12-portflash-status.bin);
see [device notes](PN2.12-PORTFLASH-STATUS-README.txt),
[checksum](PORTFLASH-STATUS-SHA256SUMS.txt) and
[investigation](../../../docs/PORT-FLASH-STATUS-2026-09-19.md).

**Full audit candidates: TX PN 2.11 / RX PN 1.5.** Seven reproduced firmware
defects are corrected, including all PN 2.10 fixes below. CPU-tested; device
validation pending. Build with `python build.py --audit --write` in each
device's SDK and run `python -m unittest test_firmware_audit -v` there.
See the [full audit](../../../docs/FULL-FIRMWARE-AUDIT-2026-09-19.md) and
[checksums](AUDIT-SHA256SUMS.txt).

| Device | Firmware | Notes |
|---|---|---|
| TX tester | [LPM-10A-TX_PN2.11-audit.bin](LPM-10A-TX_PN2.11-audit.bin) | [FLASH, battery and settings fixes](PN2.11-AUDIT-README.txt) |
| RX probe | [APP_LPM-10RX_PN1.5-audit.bin](APP_LPM-10RX_PN1.5-audit.bin) | [Sample handoff and DFT overflow fixes](RX-PN1.5-AUDIT-README.txt) |

Use the firmware for the matching device; TX and RX images are not interchangeable.

**PN 2.10 Port FLASH candidate:** addresses the reported blink-then-stop issue
with a corrected PHY auto-negotiation register, recovery after observed link
loss, and timing measured after power operations complete. CPU-tested; awaiting
device validation. Build with `python build.py --portflash --write` and test with
`python -m unittest test_portflash -v` in `sdk`.
See the [audit](../../../docs/PORT-FLASH-AUDIT-2026-09-19.md),
[device notes](PN2.10-PORTFLASH-README.txt) and [checksum](PORTFLASH-SHA256SUMS.txt).
The binary is [LPM-10A-TX_PN2.10-portflash.bin](LPM-10A-TX_PN2.10-portflash.bin).

This directory retains experimental profiles and the exact roadmap binaries
published after the owner's device test pass.

The **PN 2.9 TX / PN 1.4 RX roadmap** builds implement the requested fixes
and Ideas 1–7. In the corresponding SDK directory, run `python build.py --roadmap --write`
and `python -m unittest test_roadmap -v`. Their dedicated tests must pass without
expected failures. Checksums are in `ROADMAP-SHA256SUMS.txt`; see the
[implementation report](../../../docs/ROADMAP-IMPLEMENTATION-2026-09-19.md).
These exact files are now the [TX PN 2.9 release](../../../docs/releases/v2.9.md) and
[RX PN 1.4 experimental prerelease](../../../docs/releases/rx-v1.4.md).

The older **PN 2.4 blind-zone experiment** below is the default PN build plus one
experiment, for measuring something on hardware. Its original verifier reports two
expected failures on them (the byte-for-byte match with the default build and
the undeclared instruction at the experiment's site); everything else must pass.

| file | experiment | how to build |
|---|---|---|
| `LPM-10A-TX_PN2.4-exp-blindzone50.bin` | length blind zone 2.0 m → 0.5 m: cables of 0.5–2 m show whatever the PHY reports instead of *Out of range* | `python build.py --with blind-zone-50cm --out ../experimental/LPM-10A-TX_PN2.4-exp-blindzone50.bin --write` |

## What the blind-zone experiment is for

On the tested unit a 1 m cable came back as raw 2.0–2.4 m or as nothing: the
PHY's short-range result exists but is unreliable, and stock discards it
below 2 m. To find out whether short cables can be measured at all:

1. Flash the experimental image. Keep Zero and NVP as calibrated (0.4 m / 68 %).
2. Measure cables of known length 0.5, 1.0, 1.5, 2.0 and 3.0 m, five times each,
   far end unplugged, and record all four pairs each time.
3. Send the table. If the readings are monotonic and repeatable (even if
   wrong), a short-range correction table can be added and the blind zone
   lowered for real. If they scatter or collapse to a constant, the PHY cannot
   resolve that range and the 2 m limit stays.

sha256 of the current experimental image: `b55872030783c2535575e73f352cb4a872a3300e14c7fe2bf025924392cde5d0` (PN 2.4 base, so it also carries the PoE
screen and FLASH changes and the 4 KB longer update file)
