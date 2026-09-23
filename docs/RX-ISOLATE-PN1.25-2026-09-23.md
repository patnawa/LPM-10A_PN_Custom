# RX PN1.25: a knob that separates pairs, full sensitivity from half way, louder beeps

Date: 2026-09-23. Parent: owner-tested RX PN1.24 (raw SHA-256
`780951565cca…d8b1ce`). Transmitter: TX PN2.27A, unchanged.
Status: **device-tested 2026-09-23 and superseded by [PN1.26](RX-RELATIVE-PN1.26-2026-09-23.md).** The owner confirmed the louder beeps, but the knob still had to pass the middle before anything sounded: this design's lower half raises an absolute floor. PN1.26 keeps the louder beeps and the NCV gain fix and isolates relative to the strongest pair instead.

## Owner reports

Both with TX PN2.27A and RX PN1.24, 2026-09-23:

1. In a telephone PBX cabinet with many pairs:

   > หาไม่เจอ สัญญาณ ดังไปหมด ระบุไม่ได้เลยว่าสายไหน

   ("Could not find it; the signal was loud everywhere; I could not tell which line.")

2. Afterwards:

   > ต้องหมุน Knob เกือบครึ่งทางถึงได้ยินเสียงทั้งสองโหมด Digital/Analog, NCV Function too
   > lets audit Sensitivity precision and signal sound gain improve?

   ("The knob has to be turned almost half way before anything sounds, in
   Digital, Analog and NCV. Audit sensitivity, precision and sound gain.")

## Audit findings

| # | Area | Finding | Evidence | PN1.25 |
|---|---|---|---|---|
| 1 | Precision | Every reading from the full gain's saturation (score 40 000) to about 26 dB above it plays the same fastest rhythm, and the knob cannot shift that range | PN1.15 normalises by the driven gain, PN1.19 puts the fastest point at 40 000, PN1.22's AGC reaches the lowest gain (×20 range); the curve at `0x0800CF28` clamps at 40 000 | Knob reference and floor in the lower half |
| 2 | Sensitivity | Below 57 % of travel the knob selects 1/2.6, 1/9 or 1/20 of the full gain; for ordinary signals the lower half is silent, and at 29–57 % the probe is 8 dB less sensitive than at the top | `gain_select_3bit` levels; measured step ratios 90 / 230 / 780 / ~2 000 (RX-SENSITIVITY-2026-09-21) | Upper half always has the full gain ceiling |
| 3 | NCV | Mains mode skips the AGC but keeps the level it last drove, so after tracing a strong tone NCV runs at the AGC-lowered gain until the knob moves | PN1.24 AGC helper `0x0800D244`: knob unchanged + mode 2 → no change; reproduced in the stream model | Mains always drives the knob's gain |
| 4 | Sound | The tone is a ±100 duty swing around 800 of 1 600 at 40 kHz, 12.5 % modulation | `speaker_tick` `0x08007508`: 900 / 700, silence 800 | ±300 (1 100 / 500): ~3× amplitude, about +9.5 dB |
| 5 | Detection floor | Digital accepts 9 counts p-p (PN1.11's local block acquisition already bypasses the stock 1 000-count level gate); Analog about 20–24 counts. The previous capture study found analogue gain and 50 Hz hum, not the decision rule, limit weak signals | PN1.24 regression "cutoff 9" at DC 0/1000/4000; RX-NEXT-STEPS matched-filter verdict | No threshold change without new captures |
| 6 | Gain calibration | Codes 4–7 were measured only near saturation (~2 000 p-p), so their true ratios, and PN1.15's ×1.0–1.1 factors for them, are unverified. The pin pattern 000 is never driven (stock maps level 0 to 011) and its gain is unknown | RX-SENSITIVITY capture table | Not changed; see next steps |

## Precision failure reproduced on the actual code

`test_rx_isolate.Field` executes the real TIM1/TIM5 handlers, sampler, AGC,
analysers, publisher and speaker PWM for six seconds while the probe alternates
every 1.5 s between a toned pair (modeled amplitude 30 000) and a neighbour at
−12 dB (7 500). The link applies the measured gain ratios and a front-end limit
at 2 400 counts peak-to-peak. Fraction of time the speaker sounds in the last
0.8 s of each segment:

| Image, mode, knob | Target | Neighbour | Target | Neighbour |
|---|---:|---:|---:|---:|
| PN1.24 Digital, 20 % | 0.62 | **0.62** | 0.60 | **0.62** |
| PN1.24 Digital, 100 % | 0.57 | **0.57** | 0.56 | **0.56** |
| PN1.24 Analog, 20 % | 0.60 | **0.60** | 0.60 | **0.60** |
| PN1.24 Analog, 100 % | 0.60 | **0.61** | 0.60 | **0.60** |
| PN1.25 Digital, 61 % / 100 % (upper half) | 0.62 / 0.57 | **0.62 / 0.57** | 0.60 / 0.56 | **0.62 / 0.56** |
| PN1.25 Digital, 16 % | 0.28 | **0.00** | 0.30 | **0.00** |
| PN1.25 Digital, 20 % | 0.34 | **0.00** | 0.34 | **0.00** |
| PN1.25 Digital, 22 % | 0.37 | 0.24 | 0.38 | 0.24 |
| PN1.25 Analog, 16 % | 0.26 | **0.00** | 0.26 | **0.00** |
| PN1.25 Analog, 20 % | 0.34 | **0.00** | 0.34 | **0.00** |
| PN1.25 Analog, 22 % | 0.36 | **0.00** | 0.36 | **0.00** |

0.6 is the fastest rhythm (30 ms tone, 20 ms gap). PN1.24 plays the −12 dB
neighbour like the target at any knob position: the field report. PN1.25's
upper half does the same by design (search); its lower half separates them.
At 22 % the Digital neighbour is just above the floor and sounds, clearly
slower than the target. After moving between them: Analog first tone
~29 ms, silence ≤ ~96 ms; Digital ~42 ms and ~190 ms.

## PN1.25 design

**Upper half (knob reading ≥ 2048): Search.** The AGC ceiling is always the full
gain (it still steps down on saturation and back up), so sensitivity no longer
depends on where in the upper half the knob sits. The rhythm is PN1.24's:
everything the detectors accept sounds, 20 ms quiet interval at 40 000 and
above, and a clipped window plays fastest.

**Lower half: Isolate.** The knob sets a reference level.

- Normalised strength × K. K is 1 at the middle and halves every sixteenth of
  travel (6 dB) down to 1/64 at the bottom eighth, interpolated linearly by the
  low byte of the reading: table `4, 4, 4, 8, 16, 32, 64, 128, 256` (/256).
- A floor in the referenced score, `7200, 7200, 7200, 7200, 7200, 7200, 2400,
  450, 0` at the same points: below it the window is published as *rejected*
  and the existing release hold ends the rhythm. For Analog the accepted-window
  refresh is skipped for a muted window.
- Between the floor and 40 000 the score is stretched over the whole PN1.24
  curve: `(s − floor) × 40000 / (40000 − floor)`. The weakest audible pair gets
  110 ms quiet intervals and anything at or above 40 000 gets 20 ms.
- A clipped window counts as 40 000 at the driven gain, the saturation of the
  gain in use.
- The AGC ceiling is the knob's hardware step, as in PN1.24, but turning the
  knob down never raises an automatically lowered gain. PN1.24 reset the gain
  to the knob on every change, so a strong pair measured at the lowest gain
  jumped back up, saturated, and sounded weaker for up to two seconds.

Resulting audible range (strength at the probe tip, relative to 40 000, the
full gain's saturation):

| Knob | Quietest audible | Fastest from | Typical situation still heard |
|---:|---:|---:|---|
| 50–100 % | detector limit | 0 dB | everything (search) |
| 45 % | −36 dB | +4.5 dB | weak signals |
| 40 % | −19 dB | +9 dB | a few cm from the cable |
| 34 % | −3 dB | +15 dB | touching the cable |
| 25 % | +9 dB | +24 dB | stronger than the full gain can measure |
| ≤ 12.5 % | +21 dB | +36 dB | only the very strongest |

Each 6 dB between two pairs gives about one sixteenth of travel in the lower
half in which only the stronger one sounds.

**Mains (NCV):** the driven gain equals the knob's at every 500 ms tick: full in
the upper half, the knob's hardware step below. A difference from the driven
level takes PN1.24's knob-change path, which invalidates the current window.
The mains analysis, thresholds and beeps are unchanged.

**Sound:** `speaker_tick` writes 1 100 / 500 instead of 900 / 700; silence stays
800. Every mode, key beep and chirp is about 9.5 dB louder; pitches and beep
lengths are unchanged.

Unchanged: detection and its thresholds, sampling, overlap, release hold,
half-step smoothing, sample-age guards, gain continuity, the mains analysis and
the mode pitches. No RAM is added.

### Code

`rx-sdk/isolate.py` pins the exact PN1.24 parent and checks every site before
changing a byte. It appends 452 bytes at `0x0800D348`.

| Site | PN1.24 | PN1.25 |
|---|---|---|
| `0x0800A048` | `b.w 0x0800CF28` (curve) | `b.w` knob-law curve |
| `0x08009F08` | `movs r1,#1; b publish` (Digital clipped) | `b.w` helper: Search → same; Isolate → curve(40 000) |
| `0x08009FB0` (24 bytes) | Analog score / clipped publication | `b.w` helper + NOPs; a muted window jumps to the rejection tail `0x08009FFE` |
| `0x0800A500` | `b.w 0x0800D244` (PN1.24 AGC) | `b.w` gain hook (upper-half ceiling, knob-down, mains), then the PN1.24 AGC |
| `0x08007528` / `0x0800753E` | `mov.w r0,#900` / `#700` | `movw r0,#1100` / `#500` |
| `0x0800CDE4` | `PN1.24` | `PN1.25` (the BOOTLOADER drive shows `PN1.25.TXT`) |

## Validation

Executed on the built image in Unicorn; ADC values, the analogue link and
interrupt arrival are modeled. `python -m unittest test_rx_isolate -v`: 24 tests.

| Check | Result |
|---|---|
| Upper half (2048 / 3000 / 4095), Digital: B6 at 8 amplitudes × 3 phases, clipped, noise, DC; levels 0/1/2/5/7; four rhythm states | **3 000 windows identical to PN1.24** (all published state bytes) |
| Upper half (2048 / 4095), Analog: the established corpus plus sines; levels 0/2/7; three rhythm states | **1 548 windows identical to PN1.24** |
| Lower half (14 positions, 0 … 2047), Digital, levels 0–7, three rhythm states | **8 736** windows equal to an independent model of the arithmetic (4 788 muted, 3 948 sounding); raw score unchanged |
| Lower half, Analog | **2 112** windows equal the model (846 muted, including the skipped refresh) |
| Clipped windows | upper half: fastest as PN1.24; lower half: 40 000 at the driven gain (Digital 504 cases, Analog all levels) |
| Mains analysis at four knob positions | identical to PN1.24 |
| Speaker | tone writes 1 100 / 500 (PN1.24 900 / 700); silence 800 in both |
| AGC | upper half drives the full gain at 2048 / 2400 / 3300 (PN1.24: levels 2 / 4 / 5); knob-down keeps a lowered gain (PN1.24 re-raised it); knob-up follows; full-knob sequences give the same gain steps and publications as PN1.24; knob to 0 silences; turning down onto a strong pair leaves no gap ≥ 120 ms |
| NCV after Digital | driven gain returns to the knob's (7 at 100 %, 2 at 32 %); PN1.24 stayed at 0 |
| Image | only the declared sites plus the appended block differ; no branch lands inside replaced instructions; container round-trips; written files equal a fresh build (pinned SHA-256) |

The full RX suite ran 556 tests with one pre-existing failure,
`test_audio_clock_profile…test_preserved_profiles_exclude_audio_clock`: its mock
image cannot pass PN1.24's exact-parent guard now that PN1.24 is the default
profile. It fails identically on a clean checkout of HEAD.

## What firmware cannot change

The probe measures field strength. If the tone couples into a neighbouring
pair almost as strongly as it drives the toned pair, no setting separates
them. The transmitter drives a 454 kHz carrier from PA8/PB13 (TIM1 CH1/CH1N)
through a fixed path; SCAN never touches the wiremap multiplexer, and which
RJ45 conductors carry it has not been traced on the board. Pairs connected to a
running PBX also return the carrier through the exchange's line circuits and
ground, which spreads it across the frame.

Field procedure (also in the notes file): check the pair carries tone next to
the transmitter; locate the block with the knob in the upper half; switch TX
and RX to Analog and touch the terminals; turn the knob down below half until
one pair remains; if everything is still fast near the bottom, back the tip
off 2–5 mm; if everything goes silent together, the pairs really are equally
strong. Disconnecting the pair from the PBX helps when possible. The
transmitter is not designed for telephone line voltages; avoid leaving it on a
live extension while it rings.

## Next steps that need measurements

- **Gain calibration and pattern 000.** One ST-Link capture at a weak probe
  position (code 7 well below saturation) through all eight PB12–14 patterns
  would give the true ratios of codes 4–7 (the normaliser's ×1.0–1.1 factors)
  and show whether the never-used pattern 000 is a higher gain.
- **NCV sensitivity.** Capture the mains DFT level (`0x20000058`) near a live
  wire at a few distances and knob positions. The 151 / 251 / 350 thresholds
  and the stock "stronger = shorter beep" pattern can then be set from data.
- **Digital in hum.** The earlier capture study suggested a 50/60 Hz notch
  (a 4-sample moving-average difference) before the bit decisions.

## Files

| File | SHA-256 |
|---|---|
| `APP_LPM-10RX_PN1.25-isolate.bin` (raw, 27 916 bytes) | `c8617ea67228d86bad30a80af1f5e0d4f8fd3ae55983c81761e541efd362be95` |
| `APP_LPM-10RX_PN1.25-isolate-update.bin` (bootloader container, 32 768 bytes) | `95697bf98e215a0f9db043514caf29a4bce8bc6f041b44bcc34b2c3f174f88aa` |

Both are in `LPM-10A/Firmware File/experimental/` with `RX-PN1.25-README.txt`
(Thai/English notes and device checklist) and `RX-PN1.25-SHA256SUMS.txt`.
Install the `-update.bin` with the usual RX procedure
([RX-UPDATE-GUIDE.md](RX-UPDATE-GUIDE.md)); roll back with the PN1.24 update
file. PN1.25 is not yet a registered release profile; the default build and the
published release remain PN1.24 until the device test.
