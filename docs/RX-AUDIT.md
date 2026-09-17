# LPM-10A receiver (probe) firmware audit

Image: `APP_LPM-10RX_V3.0.0_260416.bin` (FNIRSI, 26 152 bytes, not in this repository).
Method: disassembly only; the receiver has not been emulated or run on hardware.
Addresses are flash addresses as the CPU sees them.

## What the receiver is

| | |
|---|---|
| Image | raw Cortex-M image, no container header; loads at **0x08006800** with a 26 KB bootloader below it |
| CPU | Cortex-M4F (FPU enabled in `SystemInit`), Nations-style peripheral map, ADC on the AHB bus |
| Clock | **32 MHz from the internal RC oscillator** (HSI/2 × PLL 8); APB1 = 8 MHz, APB2 = 16 MHz |
| Toolchain | GCC, unoptimised (`-O0`), no RTOS: two timer interrupts and a main-loop state machine |
| RAM used | ≈ 5.6 KB; settings page in flash at `0x0801F000` |
| Outputs | LEDs on GPIO, a lamp on PA10, a speaker driven by **TIM5 channel 4 PWM**; no display |
| Inputs | three keys (PC15 mode, PD15 third mode, PD14 lamp), ADC channel 1 (tone detector), channel 2 (battery), channel 7 (second detector) |

Only three interrupts exist:

| vector | rate | job |
|---|---|---|
| TIM1 update, `0x0800A97C` | **2 ms** tick (period 64 000 at 32 MHz) | keys every 10 ms, battery once a second, beep/keep-alive countdowns, auto-off |
| TIM5 update, `0x0800AC1C` | **10 kHz** (period 1 600 at 16 MHz) | ADC sampling for the active mode; speaker PWM every 0.8 ms |
| SysTick | | stub |

## Modes (state byte at 0x20000048)

| mode | key | sampling | analysis | indication |
|---|---|---|---|---|
| 0 "Normal" | PC15 toggles 0/1 | ADC1 ch 1: four readings 0.5 ms apart, averaged into **one sample per 5 ms**; 48 samples = 240 ms | `0x08009E08`: threshold at the trimmed mean of the window, then the 48 bits are matched against **0xB6B6**, the exact 16-slot cadence the transmitter keys; needs 2 matches in the window | 100 ms beep every 200 ms while a match was seen in the last 1.6 s |
| 1 | PC15 | ADC1 ch 1 every 1.3 ms, 64 samples | `0x08009F58`: energy of the window in three bands | beep length 100 / 200 / 400 ms by level |
| 2 | PD15 | ADC1 ch 7 every 6.2 ms, 64 samples (397 ms) | `0x080085F4`: single-bin DFT at bins 5 and 6 (≈ 12.6 and 15.1 Hz, i.e. the envelope of the 80 ms cadence); magnitude against 151 / 251 / 350 | beep length by level |

The transmitter's "Normal" cadence, corrected here: TIM2 on the TX runs at 10 kHz
(prescaler 71, period 100 on a 72 MHz timer clock), so one slot is **5 ms** and the
16-slot pattern repeats every **80 ms**. Its second cadence keys the carrier at
about 833 Hz in 100 ms phases. (Earlier notes in this project said 50 ms and 6 ms;
those were off by the TIM2 rate.)

## Speaker

`0x0800B364` writes TIM5 CCR4. While a beep is active the duty alternates between
900 and 700 (of 1 600) every 0.8 ms, a 625 Hz tone on a 10 kHz carrier; silence is a
steady 800. Beep length is the keep-alive byte at 0x2000010C, counted down every 2 ms.

## Power

- **Auto-off**: 300 000 ticks = **10 minutes** without keep-alive. Keys and every
  detected signal set the keep-alive, so a receiver that is hearing tone stays on.
  Correct as designed; no change needed.
- **Power-off** `0x08007570`: PA10 high, PA8 low, PB15 low, PB8 high (latch released).
- **Battery** `0x08007770`, once a second: trimmed mean of five ADC samples,
  `mV = raw × 6600 / 4096` (same divider and reference as the TX).
  Low-battery LED (PA15) below 3579 mV, cleared above 3621 mV: proper hysteresis.
  Below **3280 mV** the state becomes "critical" and the unit powers off **5 s later**.

## Findings

### F1. Critical-battery shutdown cannot be cancelled (bug, same family as the TX)

One second's reading below 3280 mV moves the state to critical; the counter then
runs to five and calls power-off. Nothing moves the state back if the voltage
recovers. A 400 ms beep is exactly the load that dips a tired cell for one reading.
Fix: require three consecutive critical readings and return to the low state when
the voltage is back above 3400 mV. A byte patch of the same shape as the TX
`batt-debounce`.

### F2. Digital detection is an exact 16-bit match with no phase tolerance (accuracy)

Mode 0 requires all 16 slots of a period to be read correctly, twice, within 240 ms.
Each 5 ms sample is averaged over only the last 2 ms of the slot, and the receiver's
sampling clock is a free-running RC oscillator (±1 %) against the transmitter's
crystal. The sampling point therefore drifts through the slot continuously, and for
roughly 40 % of each drift cycle (about half a second per cycle) the averaging
window straddles slot transitions and the pattern breaks. The expected symptom on
hardware is beeping that stutters in a slow rhythm even with the probe held still,
and a shorter usable range than the analogue level would allow.

Fix, receiver firmware only: sample four times per slot (every 1.25 ms), keep the
last 64 samples, and correlate the known pattern at all four phases with a tolerance
of two wrong bits per period, choosing the best phase. That removes the dropouts
and extends range at low signal levels. The correlation score is also a
signal-strength estimate, which the current digital mode does not have (see F4).

### F3. Mode-0 sample averaging uses a stale element (quirk, harmless)

The four ADC readings go into buffer slots 4..1; slot 0 is never written and stays 0,
so the "trimmed mean of five" is really the mean of the three lowest of four. The
threshold is derived from the same data, so the bias cancels; worth fixing only
alongside F2.

### F4. No strength indication in the digital mode (usability)

Mode 0 answers yes/no. Picking the right cable out of a bundle needs a graded
indication, which only modes 1 and 2 give, in three coarse steps. With F2 in
place, the correlation amplitude can drive beep rate (or pitch) in five or more
steps.

### F5. Keys (checked, fine)

Every key is debounced over six consecutive 10 ms scans. The mode key toggles
between modes 0 and 1 and sets the two mode LEDs; PD15 selects mode 2; PD14 toggles
the lamp. Each press gives a 200 ms confirmation beep.

## What would bring it closer to a Fluke IntelliTone probe

IntelliTone's edge is three things: a digitally coded signal the probe decodes with
error rejection, a graded strength display to isolate one cable in a bundle, and a
front end designed for it. Firmware can deliver the first two:

| IntelliTone behaviour | LPM-10A today | reachable in firmware |
|---|---|---|
| decodes a digital signature, ignores noise | exact 16-bit match, fragile (F2) | yes: correlator with tolerance and phase search, both units unchanged on the wire |
| strength bar to find the exact cable | yes/no in digital mode (F4) | yes: correlation amplitude → 5-step beep rate/pitch; optional sensitivity setting |
| stable indication, no stutter | drops out with clock drift (F2) | yes |
| rejects bleed onto adjacent pairs | depends on coupling | partly: strength grading helps; the coupling itself is hardware |
| cable map on the probe | none | no (needs the remote and a different front end) |

The signal path (single-ended 454 kHz carrier from the TX, envelope detector into a
10 kHz ADC on the RX) is fixed by the hardware; the ceiling is set there, not in code.
Everything above needs bench time with a real bundle, because signal levels cannot
be emulated the way the TX logic was.

## Suggested order

1. Flash PN 1.0 on the transmitter first; nothing here changes the wire signal.
2. F1 on the receiver (small, verifiable by emulation like the TX patches).
3. F2 + F4 together as one receiver release, tested on a bundle of at least five
   cables at 1 m, 10 m and 50 m.
