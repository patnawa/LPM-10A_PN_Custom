# RX PN1.29 - IntelliTone-style strength levels, Locate/Isolate, stable pair identification

The owner tested PN1.29 on the receiver and reported on 2026-09-23:

> 1.29 test pass work perfect

This release answers the reports from a telephone PBX cabinet. PN1.24 sounded
loud on every pair, so the toned line could not be picked out, and PN1.27 with
the knob all the way up played every pair the same. PN1.28, tested the same
day, was worse than PN1.27: "สัญญาณ Detect ไม่ตรง" ("detects, but not
accurately"). The owner asked for the precision of a Fluke IntelliTone. Fluke's
IntelliTone Pro 200 probe has no sensitivity knob: a Locate/Isolate switch and
eight LEDs show the strength as fixed levels, typically 7–8 on the toned cable
with neighbours a couple of levels lower in Isolate. Fluke also notes that the
digital signal bleeds over significantly between pairs, especially in Cat 3
cabling, and recommends analog mode for pairs. PN1.29 is built from the exact
PN1.24 image. TX PN2.27A is unchanged and remains the paired transmitter.
PN1.27 and PN1.28 are superseded.

- **Ten absolute levels, 3 dB apart.** The strength, scaled by the knob's
  reference (PN1.27's law: 0 dB on the top sixteenth, about −2 dB per sixteenth,
  −30 dB at the bottom), plays one of ten fixed levels. The quiet interval, the
  same in Digital and Analog, is 20, 27, 36, 46, 57, 71, 86, 103, 123 or 146 ms.
  Pulses are 30 ms in Digital and 12 ms in Analog; each Digital pulse period is
  15 % longer than the next level's. The same strength plays the same level,
  apart from the 0.5 dB hysteresis at a level boundary.
- **No memory.** PN1.25–1.28's peak, mute and comparison with earlier pairs are
  gone. Once the level has settled, a pair sounds the same whichever pair was
  touched before. Right after a stronger pair, the shown strength is still
  falling to the new pair's (next point).
- **Steady levels.** A stronger window shows at once. While audio continues, a
  weaker one moves the shown strength an eighth of the way per window (a real
  3 dB drop in about 0.3 s in Digital). A level changes only 0.5 dB past its
  boundary.
- **Full gain at every knob position** for Digital and Analog, so the tone is
  heard low on the knob (Analog from about 14 %). A clipped window counts as the
  saturation score at the driven gain, at every knob position.
- **Faster gain step down.** After an automatic gain step down, the next 500 ms
  callback may decide again. Saturation steps 7 → 2 → 1 → 0 at 0.5 / 1.0 / 1.5 s
  (PN1.24: 0.5 / 1.5 / 2.5 s) with no audio gap over 150 ms in the emulator
  stream test. A step up keeps PN1.24's hold.
- **Kept:** NCV uses the knob's gain, full from a quarter of the knob up; the
  louder beep (about +9.5 dB over stock); mode pitches Digital 2.5 kHz, Analog
  1.25 kHz, mains 5 kHz; key chirps; PN1.24's detection and thresholds.

How to use: the knob fully up is **Locate**. Use it to find the bundle or
cabinet: weak signals are graded, and at the cabinet strong pairs all play the
top level, by design, like IntelliTone's 7–8 LEDs on the toned cable. About a
fifth of the travel (roughly 19–25 %) is **Isolate**. Touch each pair for about
2 s: the toned pair plays the fastest rhythm of the pairs you touch, and its
neighbours at least one level slower. If every pair plays the slowest level,
turn the knob up a little; if the suspect pair and its neighbours all play the
top (fastest, 20 ms) level, turn it down a little. At the first touch of a
bundle, wait 1–2 s for the gain to settle. Analog is recommended for pairs: in
the emulator it separates pairs more steadily than Digital (single Digital
windows read 3–6 dB low; Analog is stable to 0.06 dB).

Validation: `cabinet_scorecard.py` runs the real firmware while a modeled probe
visits a bundle: the toned pair and neighbours 3, 6 and 10 dB weaker, 2 s per
visit with no gap between visits, each scored on the rhythm published over its
last 1.2 s, at three contact strengths and eight knob positions (100 % down to
6 %). The toned pair is identified when every neighbour visit's pulse period is
at least 12 % longer than every toned-pair visit's, or the neighbour is silent.

| Build | Digital identified (of 24) | Analog identified (of 24) |
|---|---|---|
| PN1.24 | 0 | 6 |
| PN1.27 | 4 | 9 |
| PN1.28 | 4 | 8 |
| **PN1.29** | **14** | **19** |

In Analog every build is silent on every pair, the toned pair too, at 13 % and
6 % of the knob (below PN1.24's Analog gate, about 14 %), and the scorecard
counts those 6 cases as identified. Of the 18 audible Analog cases, PN1.24
identifies 0, PN1.27 3, PN1.28 2 and PN1.29 13.

At 19 % of the knob, PN1.29 identifies the toned pair at all three contact
strengths in both modes; in Analog anywhere from 19 % to 38 %. In Digital, a
lone cable is audible at every tested knob position from 10 % to 100 % and never
slower as the knob rises; Analog is silent below about 14 % of the knob, and the
knob fully down silences both modes. Near the cable, the Digital quiet interval
at knob 10 / 25 / 40 / 50 / 75 / 100 % is 146 / 123 / 86 / 71 / 36 / 20 ms.
`test_rx_level_display` (19 tests) matches an independent model on 6,864
Digital and 3,456 Analog windows and checks clipped windows, gain, NCV, attack,
the speaker and the cabinet at 19 %, with PN1.27 as a negative control.
`test_rx_knob_response` and `test_rx_release_profile` cover the lone cable and
the release profile. The full RX run completed 647 tests (one optional external fixture skipped).

All figures in these notes are emulator results. The device confirmation is the
owner's report. Pickup distance, loudness and selectivity were not measured.

Known limits: Locate (the knob fully up) does not separate strong pairs, by
design. A neighbour within about 2 dB of the toned pair cannot be separated by
strength, because the 454 kHz carrier couples between pairs and through PBX line
circuits. A neighbour about 3 dB weaker can play the same level as the toned
pair when the two sit near a level boundary; turn the knob a little and compare
again. The first 1–2 s at a bundle can be wrong while the gain settles. Signals
more than about 24 dB below the strength that reaches the top level at that knob
position all play the slowest level (146 ms). PN1.29's remaining scorecard
failures are the knob outside the Isolate range for that contact strength (all
pairs at the top level, or all at the slowest), the first touch at the bundle
while the gain settles, and a neighbour 3 dB weaker on a level boundary. A
SmartTone-style far-end short detector would need the TX tone path traced on
the board.

**Install the RX `APP_LPM-10RX_PN1.29-levels-update.bin` asset.**
Turn the probe off, hold **SCAN**, plug in USB, and copy the update file to the
`BOOTLOADER` drive using Explorer. Verify `PN1.29.TXT` when entering the update
drive again. The raw `.bin` asset is for rebuilding/emulation, not installation.
Roll back with PN1.27 from release rx-v1.27.

Update SHA-256:
`5ab28e753a54e2425cf4e3214b196b291b2f49be4555bdeee516633dbe476ed2`

[Analysis and validation](https://github.com/patnawa/LPM-10A_PN_Custom/blob/rx-v1.29/docs/RX-INTELLITONE-ANALYSIS-2026-09-23.md) ·
[RX update/rollback guide](https://github.com/patnawa/LPM-10A_PN_Custom/blob/rx-v1.29/docs/RX-UPDATE-GUIDE.md).
