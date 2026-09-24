# RX PN1.30 - a steady strength, a fast gain settle, no walk-down at a touch

The owner tested PN1.30 on the receiver and reported on 2026-09-24:

> 1.30 test pass flicker fixed

PN1.30 is built from the exact PN1.29 image (rx-v1.29, "1.29 test pass work
perfect"). It keeps PN1.29's display, ten absolute levels 3 dB apart with the
knob as Locate / Isolate and no memory of earlier pairs, and fixes three
defects found by running PN1.29 in the emulator on a still probe. TX PN2.33 is
unchanged and remains the paired transmitter. PN1.29 is superseded; its files
are in `LPM-10A/Firmware File/archive/`.

- **Digital strength no longer dips.** The receiver reads the ADC in the last
  2 ms of each 5 ms slot while the transmitter's chip is 5.05 ms, so the chip
  edges drift through the readings every ~0.55 s; the samples that follow an
  edge are mixes of both levels, and PN1.29's estimator (median of the
  expected-high samples minus median of the expected-low samples) read 5/6,
  2/3 or 1/2 of the contrast for up to 200 ms (29 of 125 windows on a steady
  signal). A probe held still 0.6–1.0 dB above a level threshold flickered
  between two levels about once a second, and one 0.2 dB above showed the
  level below. PN1.30 estimates the contrast from local triplets: in the
  code 10110110 every high that precedes a low follows a high, and with that
  high a, the high b before the low and the low c after it (15 ms apart),
  2·max(a, b) − min(a, b) − c is the contrast however the edge falls in the
  readings; the median over the window's three or four triplets rejects the
  one a change of pair can corrupt. Clean windows score exactly as PN1.29. On a
  steady signal the display now holds one level (0 changes; PN1.29 0.8–1.2 per
  second), and the residual dips are single windows at −1.6 dB.
- **The gain settles at every displayed window.** PN1.29's automatic gain
  decided only at the 500 ms tick, so a strong pair took 1.5 s to step
  7 → 2 → 1 → 0 and read the saturation of a too-high gain meanwhile. PN1.30
  lets the TIM1 1 ms tick call the same guarded PN1.24 routine once per
  completed window after the display has shown it: a strong touch is heard at
  once at the first gain's saturation and rises one gain at a time to its
  level in about 0.8 s in Digital (steps 0.24 s apart) and 0.07 s in Analog,
  with no gap. A step up still holds one 500 ms tick.
- **A saturated reading never walks the display down.** PN1.29's display
  followed the saturated lower bounds down and up again (trace: level 8 → 5 →
  7 → 8 over 2 s on one pair). In PN1.30 a window whose newest 40 samples span
  1900 counts or more at a gain above the lowest counts 1.2 dB lower (a margin
  for the gain-step table, measured once on one unit) and never lowers the
  shown strength. An unsaturated drop of 2.5 dB or more moves the shown
  strength half way per window (PN1.29: an eighth), so a 6 dB drop shows its
  new level in about 0.6 s.
- **Kept:** the ten levels and intervals, the knob law, Locate / Isolate, NCV
  gain, the louder beep, mode pitches, detection thresholds, the sampler and
  the Analog analysis. 684 bytes appended after the PN1.29 image; 8 bytes of
  zero-initialised RAM at `0x20000218`.

How to use: as PN1.29. Knob fully up is **Locate**; about a fifth of the travel
is **Isolate**: touch each pair for about 2 s, the toned pair plays the fastest
rhythm and its neighbours at least one level slower. The rhythm now rises to
its level within about a second of a strong touch and holds steady while the
probe is still.

Validation (emulator, real firmware, modeled ADC / link / interrupts):
`steady_probe.py` (new) records every window's raw score on one constant
signal; `cabinet_scorecard.py` is unchanged. On a steady signal PN1.29 reads
29 of 125 windows low, down to −6 dB, and changes level 4–6 times in 5 s
near a boundary; PN1.30 reads 12 windows at −1.6 dB and changes level 0 times.
A strong pair at the Isolate position settles its gain 0.73 s after the first
decision (PN1.29 1.5 s) with one heard window at each gain and the display
never falling; Analog settles in 66 ms. The cabinet scorecard gives the same
verdict as PN1.29 on every Digital row and on all but one boundary row in
Analog (14 / 18 of 24; the differing row is a neighbour 0.02 dB above a level
threshold shown at its own level, which is also the toned pair's, 0.007 dB
under the next), and the spread of one pair's tone fraction across its visits
falls from 0.043 to 0.007 in Digital and 0.015 to 0.001 in Analog. The lone
cable's knob response is identical to PN1.29 at every knob and signal.
`test_rx_clean_strength` (24 tests) checks the estimator against its model on
67 captured windows and 96 mixed-edge windows (PN1.29 as negative control
reads as low as 0.33 of the truth), the flicker, the settle, the AGC fixture
with no gap over 150 ms and no hunting, the cabinet at 19 % and the unchanged
speaker, mains, gates and release. The full RX run completed 669 tests (one
optional external fixture skipped).

All figures in these notes are emulator results. The device confirmation is
the owner's report. Pickup distance, loudness and selectivity were not
measured.

Known limits: PN1.29's limits stand (Locate does not separate strong pairs by
design; a neighbour within about 2 dB of the toned pair cannot be separated by
strength; a neighbour about 3 dB weaker can share a level at a boundary). The
chip edges still drift through the readings; the residual single-window dips
of −1.6 dB are filtered to −0.2 dB, so a signal within about 0.1 dB above a
threshold can still alternate. A sampler whose slot follows the transmitter's
chip is the complete fix and is left for a later build. The gain-step table
(20 / 9.2 / 2.6) was measured once, on one unit; the Digital and Analog score
scales differ by 2–2.5 dB in the model; the Analog knob gate at 14 % is stock.

**Install the RX `APP_LPM-10RX_PN1.30-clean-strength-update.bin` asset.**
Turn the probe off, hold **SCAN**, plug in USB, and copy the update file to the
`BOOTLOADER` drive using Explorer. Verify `PN1.30.TXT` when entering the update
drive again. The raw `.bin` asset is for rebuilding/emulation, not installation.
Roll back with PN1.29 from release rx-v1.29.

Update SHA-256:
`bf723bdd7b51ef850388cc485c02b471a8eb6a48e414701a24924ca336900180`

[Analysis and validation](https://github.com/patnawa/LPM-10A_PN_Custom/blob/rx-v1.30/docs/RX-CLEAN-STRENGTH-PN1.30-2026-09-24.md) ·
[RX update/rollback guide](https://github.com/patnawa/LPM-10A_PN_Custom/blob/rx-v1.30/docs/RX-UPDATE-GUIDE.md).
