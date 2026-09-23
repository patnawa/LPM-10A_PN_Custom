# RX PN1.27: the knob sets the rhythm's reference over its whole travel

Date: 2026-09-23. Parent: owner-tested RX PN1.24. Transmitter: TX PN2.27A, unchanged.
Status: **owner-tested release [rx-v1.27](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/rx-v1.27).** The owner reports "1.27 test pass"
on the probe (2026-09-23). The confirmation covers the owner's device test, not measured pickup
distance or selectivity.
Earlier steps: [PN1.25](RX-ISOLATE-PN1.25-2026-09-23.md) (audit, louder beep),
[PN1.26](RX-RELATIVE-PN1.26-2026-09-23.md) (full sensitivity, peak-relative isolation).

## Report

PN1.26 on the owner's probe:

> เริ่มได้ยิน 5-10% digital 10-20% analog

> เสียง Rx แรงตลอด ตั้งแต่ 10% หมุนเพิ่ม ลด ไม่ต่าง Toneprobe

("Heard from 5–10 % Digital, 10–20 % Analog" and "the RX is always strong from
10 %; turning the knob up or down makes no difference.")

## Diagnosis

**Feedback loop.** `python -m unittest test_rx_knob_response -v` (0.3 s,
deterministic). It runs the real analyser, curve, peak and publisher on one fresh
window per case. The case is one steady signal (the receiver's only and
strongest), at knob 10/25/40/50/75/100 %. The test requires the signal to stay
audible, the rhythm never to slow as the knob rises, and knob 10 % to sound
slower than 100 % for a moderate or near signal. PN1.26 goes red with the
reported symptom. Quiet interval in ms:

```
PN1.26  weak      [20, 20, 20, 92, 92, 92]
        moderate  [20, 20, 20, 66, 66, 66]
        near      [20, 20, 20, 20, 20, 20]
        touching  [20, 20, 20, 20, 20, 20]
```

**Hypotheses, ranked before testing:**

1. In PN1.26's lower half a lone signal is its own peak, and the ranking against
   the peak always gives the fastest rhythm.
2. The upper half is knob-independent by design (full gain, gain-normalised
   rhythm).
3. Near readings sit at or above the curve's fastest point, so without a knob
   reference they are fastest everywhere.
4. The beep volume is constant and the knob never controlled volume; "strong" may
   partly mean loud. This cannot be tested in the emulator.

**Probe (one variable: the remembered peak).** The same near window on PN1.26:
with a lone cable, 20 ms at every knob position; with a +12 dB stronger pair
remembered, mute / 82 / 68 / 20 / 20 / 20 ms. The lower half follows the knob
only relative to a stronger pair. **Confirmed cause: hypotheses 1–3 together.
For a lone cable nothing in PN1.26 depends on the knob.**

## Fix

The normalised strength is multiplied by a knob reference K before PN1.24's
curve, at every knob position. K is 1 on the top sixteenth (reading ≥ 3840),
where PN1.24 is reproduced exactly. It falls about 2 dB per sixteenth, linearly
interpolated, to −30 dB at the bottom: table `8, 10, 13, 16, 20, 25, 32, 40,
51, 64, 81, 102, 128, 161, 203, 256, 256` /256. K mutes nothing, so a lone
cable stays audible down to the stock gates, which keeps PN1.26's sensitivity
result.

PN1.26's other parts are kept: full gain at every knob position, the
peak-relative mute below the middle (a lone cable is never muted), the Compare
gain ceiling, the NCV gain and the louder beep. PN1.26's ranking against the
peak is dropped. Clipped windows play fastest on the top sixteenth, as PN1.24;
elsewhere they count as score 40 000 at the driven gain and go through K.
`rx-sdk/knob_reference.py` appends 660 bytes at `0x0800D348`, touches the same
sites as PN1.26 and tags the image `PN1.27`.

After the fix, the same loop in ms:

```
PN1.27  weak      [109, 109, 107, 106, 98, 92]
        moderate  [102, 96, 92, 88, 77, 66]
        near      [90, 83, 76, 69, 51, 20]
        touching  [76, 67, 55, 44, 20, 20]
```

## Validation

| Check | Result |
|---|---|
| `test_rx_knob_response` | PN1.27 green; PN1.26 kept as the red negative control |
| Top sixteenth against PN1.24, any stored peak | 5 805 Digital and 2 064 Analog windows identical |
| Every knob position against an independent model (normalise, peak and decay, mute, K, curve, smoothing) | 24 336 Digital (6 060 muted) and 9 504 Analog (2 216 muted) windows |
| Clipped windows | top sixteenth as PN1.24; elsewhere 40 000 at the driven gain through K |
| Gain | hook equals PN1.26's assembled source; 42 TIM1 ceiling cases; full-knob AGC identical to PN1.24; tracing drives the full gain for a lone cable at every knob; NCV gain law; knob off silences |
| Speaker | tone 1 100 / 500, silence 800 |
| Lone-cable stream (moderate level) | tone fraction rises with the knob: Digital 0.22 → 0.33, Analog 0.24 → 0.32 |
| Cabinet stream (target and a −14 dB neighbour) | knob 7 % / 15 %: neighbour muted, target sounds; knob 51 %: target fastest (0.56–0.63), neighbour clearly slower (0.38–0.43); full knob: both fast, as PN1.24 |

`python -m unittest test_rx_knob_response test_rx_knob_reference -v`: 22 tests.
These are software-model results. They do not measure pickup, loudness or
selectivity.

## Files

| File | SHA-256 |
|---|---|
| `APP_LPM-10RX_PN1.27-knob.bin` (raw, 28 124 bytes) | `febd648daa98b51cf06c35e855afa4a088bb789c8ae643acf42b0f828c081c83` |
| `APP_LPM-10RX_PN1.27-knob-update.bin` (container, 32 768 bytes) | `b3aa9618e4eeaabc14120bcae6a381771d8b8b0c65a85f38b0d1808cdbf36de1` |

Both are in `LPM-10A/Firmware File/experimental/` with `RX-PN1.27-README.txt`.
The update file and `RX-PN1.27-README.txt` are also at the root of
`LPM-10A/Firmware File/`; `python build.py --write` from `rx-sdk` rebuilds both
images exactly in `experimental/`. Install the `-update.bin` with the usual RX procedure. Roll back with PN1.24
(`archive/` or release rx-v1.24) or PN1.26.
