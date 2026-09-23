# RX PN1.26: full sensitivity at every knob position, isolation relative to the strongest pair

Date: 2026-09-23. Parent: owner-tested RX PN1.24 (raw SHA-256
`780951565cca…d8b1ce`). Transmitter: TX PN2.27A, unchanged.
Status: **candidate, partly device-tested.** On the owner's probe (2026-09-23) the tone is first heard at 5–10 % of the knob in Digital and 10–20 % in Analog ("เริ่มได้ยิน 5-10% digital 10-20% analog"); PN1.25 needed more than half. Analog's start matches the stock Analog gate at 580 of 4095 (14 %). The owner then reported "always strong from 10 %, turning the knob makes no difference": a lone cable is its own peak, so the ranking played it fastest everywhere. Superseded by [PN1.27](RX-KNOB-PN1.27-2026-09-23.md).
Predecessor candidate and audit: [RX-ISOLATE-PN1.25-2026-09-23.md](RX-ISOLATE-PN1.25-2026-09-23.md).

## PN1.25 on the device

> 1.25 test แล้วเหมือนเสียงแรงขึ้นแต่ยังต้องหมุนจนผ่านกึ่งกลางถึงค่อยได้ยินเสียง

("Tested 1.25: the sound seems louder, but I still have to turn past the middle
before I hear anything.")

The louder beep worked. The knob result is PN1.25's design showing through:
its lower half raised an **absolute** floor (only strong signals sound) and
kept the knob's lower hardware gain. The owner's bench signal is only picked
up at full gain, so it cut in exactly at the middle. For the owner the knob
must not cost sensitivity; isolation has to come from somewhere else.

## Design

**Sensitivity.** Digital and Analog let the automatic gain use the full gain at
every knob position. Whatever the detectors accept can sound anywhere above the
stock gates (Digital reading ≥ 2, Analog ≥ 580 of 4095).

**Peak.** The receiver remembers the strongest normalised strength heard
recently. A stronger reading raises it at once. It decays 2 dB per second of
TIM5 time (×250/256 every 100 ms) and is forgotten after 10 s without a
detection. The decay is computed from elapsed time whenever it is read, so it
also relaxes while nothing is detected. It is stored in 8 bytes at
`0x20000210`: inside the startup zero-init region `0x20000018–0x20001617`,
above every PN1.24 global and below the deepest audited stack (`0x200013F0`).
No literal or movw/movt pair of PN1.24 reaches it.

**Upper half of the knob (reading ≥ 2048): Search.** PN1.24's rhythm; nothing is
muted.

**Lower half: Compare.** A reading below *peak × window* is published as
rejected; the existing release hold ends its rhythm. The window narrows as the
knob turns down (table `128, 121, 102, 72, 45, 23, 10, 4, 0` /256 at each
sixteenth, interpolated):

| Knob | Pairs muted if weaker than the strongest by |
|---:|---:|
| 45 % | 36 dB |
| 40 % | 30 dB |
| 30 % | 19 dB |
| 20 % | 12 dB |
| 10 % | 7 dB |
| bottom | 6 dB |

Readings inside the window are ranked against the peak: the peak plays the
fastest rhythm (20 ms), the window edge the slowest (110 ms). A lone cable is
its own peak, so it always sounds, and fastest exactly where it is strongest.

**Compare gain ceiling.** A saturated reading is only a lower bound. If the
gain rose while a strong peak was remembered, the strongest pair would read as
the saturation of that gain and be muted, for 1–2 s until the AGC stepped back
down. The first build did exactly that in the stream model, which is why the
ceiling exists. In Compare the ceiling is the highest level whose saturation
still reaches the mute threshold. Those saturation points are 40 000 × the
measured gain step: level 7 → 40 000, 2 → 104 000, 1 → 368 000, 0 → 800 000.
A pair that should sound therefore never reads below the threshold. A lone
weak cable has a small peak, so its ceiling is the full gain. The gain hook only
reads the peak; the analyser owns it.

**Clipped windows** count as 40 000 at the driven gain in Compare (fastest in
Search, as PN1.24).

**NCV** keeps its stock analysis. Its gain is the knob's hardware step, full
from a quarter of the knob up. It is re-applied at every tick, so NCV also has
the knob's gain right after a tracing mode (PN1.24 kept the tracing AGC's
lowered gain).

**Sound:** PN1.25's louder tone (duty 800 ± 300, stock ± 100) is kept.

Unchanged: detection and its thresholds, sampling, overlap, release hold,
half-step smoothing, sample-age guards, gain continuity, the mains analysis and
the mode pitches.

### Code

`rx-sdk/relative_isolate.py` pins the exact PN1.24 parent, checks every site
and the peak RAM before changing a byte, and appends 620 bytes at `0x0800D348`:
`peak_now` (decay to now, read only), the curve, the Digital/Analog clipped-
window helpers from PN1.25 and the gain hook. Sites: `0x0800A048` (curve entry),
`0x08009F08` (Digital clipped), `0x08009FB0` (Analog score/clipped, 24 bytes),
`0x0800A500` (gain hook), `0x08007528` / `0x0800753E` (tone duty), `0x0800CDE4`
(`PN1.26`).

## Validation

Executed on the built image in Unicorn; ADC values, the analogue link (measured
gain ratios, front end limited at 2 400 counts p-p) and interrupt arrival are
modeled. `python -m unittest test_rx_relative_isolate -v`: 22 tests.

| Check | Result |
|---|---|
| Upper half (2048 / 3000 / 4095) against PN1.24, any stored peak | **5 805 Digital** and **2 064 Analog** windows identical |
| Lower half against an independent model of peak, decay, window and ranking, including the stored peak and decay remainder | **16 848 Digital** (6 060 muted) and **6 048 Analog** (2 216 muted) windows |
| Clipped windows | upper half as PN1.24; lower half 40 000 at the driven gain |
| Gain hook through the real TIM1 path | 42 seeded peak/knob cases equal the ceiling model; the hook never writes the peak |
| Owner's bench case: probe still at a weak cable | PN1.24 silent at knob 7–37 %; PN1.26 sounds at every one of those positions (tone fraction 0.53–0.59) |
| Cabinet case: target and a −14 dB neighbour alternating every 1.2 s | PN1.24 and PN1.26's upper half sound on both (0.6); PN1.26 at 7 % Digital / 15 % Analog: target 0.46–0.6, neighbour **0.0** |
| Dwelling on the neighbour | it starts to sound 1.9 s after leaving the target (the peak fades) |
| AGC | full-knob sequences identical to PN1.24; tracing drives the full gain at knob 7 / 24 / 49 / 100 % (PN1.24: levels 0 / 1 / 2 / 7) |
| NCV | gain 7 at 100 % and 27 %, level 1 at 20 %, 0 at 7 %; returns to the knob's gain after Digital |
| Knob off, speaker | knob 0 silences; tone 1 100 / 500, silence 800 |
| Image | only the declared sites plus the appended block differ; no branch lands inside replaced instructions; container round-trips; written files equal a fresh build |

## Limits and what to watch on the device

- The peak remembers about 2 s of advantage per 4 dB of window. Probing pairs
  more slowly than that lets a weaker pair sound; touching the strongest pair
  again restores the comparison.
- Physical selectivity is unchanged: if the tone couples into a neighbour as
  strongly as into the toned pair, they stay within each other's window.
- The model's gain ratios come from one capture near saturation; a
  weak-signal ST-Link capture would calibrate them (see the PN1.25 document's
  next steps).

## Files

| File | SHA-256 |
|---|---|
| `APP_LPM-10RX_PN1.26-relative.bin` (raw, 28 084 bytes) | `d3f19545c3d9f382534e60e0cc91e64af038b80f03da77ff0c61c4d4006edab8` |
| `APP_LPM-10RX_PN1.26-relative-update.bin` (container, 32 768 bytes) | `600262f38fad838db06950554806135014fad578ec0eb5ed9e3a3f536be79c02` |

In `LPM-10A/Firmware File/experimental/` with `RX-PN1.26-README.txt` (Thai/English
notes and checklist) and `RX-PN1.26-SHA256SUMS.txt`. Install the `-update.bin`
with the usual RX procedure; roll back with the PN1.24 update file. PN1.24 stays
the default build and the published release until a device test.
