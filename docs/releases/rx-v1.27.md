# RX PN1.27 — the knob sets the rhythm, full sensitivity, cabinet isolation

The owner tested PN1.27 on the receiver and reported on 2026-09-23:

> 1.27 test pass

This release answers two reports from a field test in a telephone PBX cabinet
with TX PN2.27A and RX PN1.24. First, the tone sounded the same on every pair,
so the toned line could not be picked out. Second, the knob had to be turned
about half way before Digital, Analog or NCV sounded. TX PN2.27A is unchanged
and remains the paired transmitter.

- **Full sensitivity at every knob position.** Digital and Analog use the full
  front-end gain wherever the knob is. The automatic gain still steps down near
  the cable. On PN1.26, which has the same gain law, the owner heard the tone
  from 5–10 % of the knob (Digital) and 10–20 % (Analog).
- **The knob sets the rhythm's reference over its whole travel.** The top
  sixteenth plays exactly as PN1.24. Each sixteenth lower is about 2 dB slower,
  down to −30 dB at the bottom: lower knob, slower rhythm. The knob mutes
  nothing.
- **Cabinet isolation below the middle of the knob.** The probe remembers the
  strongest pair heard recently. That peak falls 2 dB per second and is
  forgotten after 10 s. Pairs weaker than it by more than the knob's window are
  muted: −36 dB just below the middle, −6 dB at the bottom. A lone cable always
  sounds.
- **NCV** uses the knob's gain, full from a quarter of the knob up, including
  right after a tracing mode.
- **Louder beeps:** the speaker swing is three times stock's, about +9.5 dB.

Two candidates before it were tested on the probe the same day. PN1.25 made the
beeps louder, but the knob still had to pass the middle. PN1.26 was heard from
5–10 %, but the knob had no effect. `test_rx_knob_response` reproduces the
PN1.26 report on the actual code and passes on PN1.27. Near the cable, the quiet
interval at knob 10 / 25 / 40 / 50 / 75 / 100 % is 90 / 83 / 76 / 69 / 51 / 20 ms
(PN1.26: 20 ms at every position).

Validation: the top sixteenth matches PN1.24 on 5,805 Digital and 2,064 Analog
windows. Every knob position matches an independent model on 24,336 Digital and
9,504 Analog windows. In a cabinet stream (the toned pair and a neighbour 14 dB
weaker), the neighbour is muted at a low knob. At 51 % it is clearly slower than
the toned pair. The full RX run completed 606 tests (one optional external
fixture skipped). The default build reproduces the exact tested firmware bytes.

These figures are emulator results. The device confirmation is the owner's
report. Pickup distance, loudness and selectivity were not measured.

Known limitation, reported by the owner after the release test: with the knob
all the way up, PN1.27 keeps PN1.24's rhythm. Every pair strong enough to
saturate the full gain plays the fastest rhythm, so near a bundle several pairs
can sound the same. Lower on the knob the pairs rank, and below the middle the
weaker ones are muted.

**Install the RX `APP_LPM-10RX_PN1.27-knob-update.bin` asset.**
Turn the probe off, hold **SCAN**, plug in USB, and copy the update file to the
`BOOTLOADER` drive using Explorer. Verify `PN1.27.TXT` when entering the update
drive again. The raw `.bin` asset is for rebuilding/emulation, not installation.
Roll back with PN1.24 from release rx-v1.24.

Update SHA-256:
`b3aa9618e4eeaabc14120bcae6a381771d8b8b0c65a85f38b0d1808cdbf36de1`

[Diagnosis and validation](https://github.com/patnawa/LPM-10A_PN_Custom/blob/rx-v1.27/docs/RX-KNOB-PN1.27-2026-09-23.md) ·
[RX update/rollback guide](https://github.com/patnawa/LPM-10A_PN_Custom/blob/rx-v1.27/docs/RX-UPDATE-GUIDE.md).
