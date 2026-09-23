# RX PN1.28: the toned pair plays fastest with the knob all the way up

Date: 2026-09-23. Parent: owner-tested release RX PN1.27
([rx-v1.27](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/rx-v1.27)).
Transmitter: TX PN2.27A, unchanged.
Status: **device-tested 2026-09-23 and superseded by PN1.29.** The owner reports PN1.28 "detects, but
not accurately", worse than PN1.27. The cabinet scorecard in
[RX-INTELLITONE-ANALYSIS-2026-09-23.md](RX-INTELLITONE-ANALYSIS-2026-09-23.md) reproduces why: the
curve slides to a remembered peak, so the same pair sounds different depending on what was touched
before and for how long.

## Report

PN1.27 on the owner's probe, after the release test:

> พอเร่งสุดเหมือนหาสายไม่แม่น ดังทั่วไปหมด ไม่แม่นยำในการ identify สาย

("With the knob all the way up it does not find the line precisely: it sounds
everywhere, and identifying the line is imprecise.")

## Diagnosis

**Feedback loop.** `python -m unittest test_rx_pair_identify -v` (0.1 s,
deterministic). It runs the real analyser, curve, peak and publisher on one
fresh window per case. The toned pair is touched first: +10 dB over the full
gain's saturation, with the automatic gain stepped down to level 2. Then come
neighbours 3, 6, 10 and 14 dB weaker. On PN1.27 the loop goes red with the
reported symptom. Quiet interval in ms, toned pair | neighbours:

```
PN1.27  knob  25 %  67 | 71  78  83  88
        knob  50 %  44 | 55  62  69  77
        knob  75 %  20 | 20  33  51  62
        knob 100 %  20 | 20  20  20  44
```

Minimal repro: knob 100 %, the toned pair and one neighbour 6 dB weaker. Both
play 20 ms. The stored peak is not load-bearing; the result is the same without
it.

**Hypotheses, ranked before testing:**

1. The rhythm curve's fastest point is score 40 000, the full gain's
   saturation. On the top of the knob the knob's reference K is 1, so every pair
   read above 40 000 is clamped to 20 ms.
2. A clipped window on the top sixteenth plays fastest (PN1.18), so while the
   front end clips every touched pair is fastest.
3. Nothing is muted in the upper half of the knob.
4. The peak's decay lets a neighbour become the reference.
5. Every beep has the same loudness. This cannot be tested in the emulator.

**Probe (one variable: the strength against the curve).** With both pairs
moved below the full gain's saturation, PN1.27 ranks them: 39 against 60 ms.
At 75 % and 50 % of the knob, K brings the same readings back into the curve and
they rank (table above). **Confirmed cause: hypothesis 1.**

**A second mechanism, found with the cabinet stream.** In this stream the probe
alternates every 1.2 s between the toned pair and a neighbour, with the knob at
full. With the curve fix alone, the second touch of a neighbour ranks but the
first does not. A trace of the gain level and the stored peak shows why. The
front end saturates at about 2 400 counts p-p, before the ADC rail. A window
read at too high a gain is therefore not flagged as clipped: it reads the
saturation of that gain (133 754 at level 2), which is only a lower bound. The
PN1.24 automatic gain steps one level per second, because one 500 ms callback
is held after every change (7 → 2 at 0.5 s, 2 → 1 at 1.5 s). The toned pair,
touched for 1.2 s, was never measured unsaturated. The first neighbour,
measured at level 1 (335 634), became the peak and played fastest.

Probe (one variable: the hold after a step). With no hold, the steps come at
0.5 s and 1.0 s and the first touch ranks. Matrix of toned-pair strength,
neighbour deficit and mode, tone fraction of the first neighbour touch against
the toned pair:

| Toned pair (link units) | Neighbour | Curve fix alone | With fast attack |
|---|---|---|---|
| 3 000 (settles at level 2) | −6 / −14 dB | 0.39 / 0.31 vs 0.54 (ranked) | same |
| 10 000 (level 1) | −6 dB | 0.55–0.56 vs 0.54–0.60 (not ranked) | 0.39–0.43 (ranked) |
| 10 000 | −14 dB | 0.31–0.35 (ranked) | 0.30–0.34 |
| 30 000 (level 0) | −14 dB | 0.56–0.60 (not ranked) | 0.34–0.35 (ranked) |
| 30 000 | −6 dB | 0.56–0.60 (not ranked) | 0.50–0.52 (partly) |

## Fix

`rx-sdk/pair_rank.py` builds PN1.28 from the exact PN1.27 image:

1. **Curve.** The reference is the smaller of K and ceil(40 000 × 256 / peak)
   once the peak is above 40 000. The strongest recent pair lands exactly on the
   fastest point, and weaker pairs play slower by their dB deficit. When the
   peak fits the curve at the knob's reference nothing changes. A lone cable is
   its own peak, so its rhythm at every knob position is PN1.27's.
2. **Fast attack.** After a gain step down, the next 500 ms callback may decide
   again. Its freshness guard still requires a complete window acquired at the
   new gain. A step up keeps PN1.24's one-callback hold.

52 bytes of helpers at `0x0800D5DC`, a `bl` at `0x0800D400` (the curve's
reference multiply) and at `0x0800D30A` (the AGC's hold), tag `PN1.28`.

After the fix, the same loop in ms:

```
PN1.28  knob  25 %  67 | 71  78  83  88
        knob  50 %  44 | 55  62  69  77
        knob  75 %  20 | 33  47  60  68
        knob 100 %  20 | 33  47  60  68
```

## Validation

| Check | Result |
|---|---|
| `test_rx_pair_identify` (the report as a test) | PN1.28 green; PN1.27 kept as the red negative control |
| Every knob position against an independent model (normalise, peak and decay, mute, reference = min(K, 40 000 / peak), curve, smoothing) | 29 952 Digital and 12 096 Analog windows; the curve slides to the peak in 16 050 and 6 916 of them |
| Against PN1.27 | identical wherever the peak fits the curve (2 712 Digital windows); the peak and its decay identical in every case |
| Lone cable (`test_rx_knob_response`, lone moderate stream) | identical to PN1.27 at every knob position |
| Clipped windows | top sixteenth as PN1.27 (fastest); lower down 40 000 at the driven gain through the model |
| Gain | steps down every 0.5 s on saturation (7 → 2 → 1 → 0 at 0.5 / 1.0 / 1.5 s; PN1.27 0.5 / 1.5 / 2.5 s) with no audio gap over 150 ms; a step up keeps the 1 s hold; near-threshold inputs do not hunt; incomplete, closed, pending or expired windows cannot drive a step; a partial window after a step cannot trigger a second one |
| Cabinet streams, knob 100 %, pairs alternating every 1.2 s | first and second touch of each neighbour slower than the toned pair: tone fraction 0.30–0.43 against 0.53–0.60 (toned pair 3 000 / 10 000 / 30 000 link units, neighbours −6 and −14 dB, Digital and Analog); PN1.27 plays every pair the same |
| Low knob | the neighbour is still muted next to the toned pair |

`python -m unittest test_rx_pair_identify test_rx_pair_rank test_rx_knob_response -v`: 24 tests.

These are software-model results. They do not measure pickup, coupling
between real pairs or loudness.

## Files

| File | SHA-256 |
|---|---|
| `APP_LPM-10RX_PN1.28-pair-rank.bin` (raw, 28 176 bytes) | `0e4b34b2347b1054035194500e1885fffeb1a90ed57753739ed4a2fbb8f5a619` |
| `APP_LPM-10RX_PN1.28-pair-rank-update.bin` (container, 32 768 bytes) | `ef0dcf7c1a1ae1313f550263d8766d5771f8c4f3b6d321b6fc831063b563798f` |

Both are in `LPM-10A/Firmware File/experimental/` with `RX-PN1.28-README.txt`.
Install the `-update.bin` with the usual RX procedure. Roll back with PN1.27
(release rx-v1.27; `LPM-10A/Firmware File/archive/APP_LPM-10RX_PN1.27-knob-update.bin`).
PN1.28 and PN1.27 are superseded by PN1.29 ([rx-v1.29](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/rx-v1.29)), the current download.
