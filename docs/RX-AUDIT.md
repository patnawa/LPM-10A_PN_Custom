# LPM-10A receiver (probe) firmware audit

Image: `APP_LPM-10RX_V3.0.0_260416.bin` (FNIRSI, 26 152 bytes, not in this repository).
Method: disassembly, a full function survey (156 routines named, see
`rx-sdk/lpm10rx/symbols.py`), and CPU emulation: the image is booted from its reset
vector through the clock and timer set-up (`rx-sdk/boot_emu.py`), and the battery
routine is exercised call by call (`rx-sdk/verify.py`). Nothing has been run on
hardware. Addresses are flash addresses as the CPU sees them.

## What the receiver is

| | |
|---|---|
| Image | raw Cortex-M image, no container header; loads at **0x08006800**. The flash page below it (`0x08006000`) belongs to the bootloader and carries a 24-byte record at `0x08006700` plus the tag `_V3.` at `0x0800676C` (see "Device binding") |
| CPU | Nations **N32L40x** class: Cortex-M4F (FPU enabled in `SystemInit`), 16 MHz HSI, MSI, ADC on the AHB bus at `0x40020800` |
| Clock | **64 MHz** from the internal 16 MHz oscillator × PLL 4 (`rcc_init` at run time; `SystemInit` had already reached 64 MHz as HSI/2 × 8). APB1 = APB2 = 32 MHz, so both timers run from **64 MHz** (the timer clock doubles when the APB prescaler is not 1, as the Nations SDK's own timer examples state). The register programming is verified by booting the image under emulation (`boot_emu.py`: SystemCoreClock 64 MHz, the firmware's own `RCC_GetClocksFreqValue` reporting 64 / 64 / 32 / 32 MHz, TIM1 PSC 0 / period 64 000, TIM5 PSC 0 / period 1 600); the 16 MHz HSI and the ×2 timer rule are SDK facts, corroborated three times over by the cadences below (5 ms sample vs the TX's 5.05 ms slot, mode 2 at 50/60 Hz, mode 1 at 817 Hz vs the TX's 825 Hz). One scope check of the 40 kHz speaker carrier or the 2.5 kHz beep tone settles it on hardware |
| Toolchain | ARM Compiler (Keil MDK), unoptimised, ARM C library; no RTOS: two timer interrupts and a main-loop state machine |
| RAM used | ≈ 5.6 KB. The flash page `0x0801F000` holds only the version string `3.0.0`; `main` rewrites it when it differs, and no setting is stored anywhere (the mode resets to 0 at every boot) |
| Outputs | LEDs on GPIO (PA8 blinks at 0.5 Hz in mode 0, PA15 low-battery, PB4 blinks in the low state), a lamp on PA10, a speaker driven by **TIM5 channel 4 PWM**, a 3-bit code on PB12..PB14 (see "Gain control"), PA5 driven low at boot (unknown), PB8 low holds the power latch; no display |
| Inputs | power key on PC13 (boot waits for its release; held 1.2 s → power-off), three keys (PC15 mode, PD15 mains mode, PD14 lamp), PB1/PB2 sampled at boot (a charger-present branch that waits forever with interrupts masked; schematic needed), ADC channel 1 = PA0 (tone detector), channel 2 = PA1 (battery), channel 3 = PA2 (level for the gain control), channel 7 = PA6 (mains detector) |

Only three interrupts exist:

| vector | rate | job |
|---|---|---|
| TIM1 update, `0x0800A97C` | **1 ms** tick (prescaler 0, period 64 000 at 64 MHz) | keys every 5 ms, battery every 500 ms, beep/keep-alive countdowns, auto-off |
| TIM5 update, `0x0800AC1C` | **40 kHz** (prescaler 0, period 1 600 at 64 MHz) | ADC sampling for the active mode; speaker PWM update every 8 ticks |
| SysTick | | stub (delays are busy loops) |

`tim5_init` computes a prescaler from `SystemCoreClock` and never writes it; the
timer runs with prescaler 0. That is the detail a code-only reading gets wrong,
and it is why the emulator was needed.

## Modes (state byte at 0x20000048)

| mode | key | sampling | analysis | indication |
|---|---|---|---|---|
| 0 "Normal" | PC15 toggles 0/1 | ADC1 ch 1, read every 0.5 ms during the last 2.5 ms of each 5 ms slot, a trimmed mean of the five readings = **one sample per 5 ms**; 48 samples = 240 ms | `0x08009E08`: threshold at the trimmed mean of the window, then the 48 bits are slid past **0xB6B6**, the transmitter's 16-slot cadence; needs 2 exact matches in the window and a minimum level | 50 ms beeps with 50 ms gaps while a match was seen in the last 0.8 s |
| 1 "second tone" | PC15 | ADC1 ch 1 every 0.325 ms, 64 samples = 20.8 ms | `0x08009F58`: 32-bin DFT; **bin 17 = 817 Hz** (48 Hz wide), the transmitter's ~825 Hz second cadence, against the floor of the other bins with margins 600 / 200 / 10 | beep 50 / 100 / 200 ms: **shorter = faster repeat = stronger** |
| 2 "mains" | PD15 | ADC1 ch 7 every 1.55 ms, 64 samples = 99.2 ms | `0x080085F4`: DFT bins 5 and 6 = **50.4 Hz and 60.5 Hz**; the larger magnitude against 151 / 251 / 350 | beep length by level |

Mode 1 is therefore the receiver for the transmitter's second cadence, and mode 2
is a **50/60 Hz mains detector** on a separate analogue input, not a tone mode at
all. Earlier notes in this project described mode 2 with bins at 12.6 / 15.1 Hz;
that followed from a wrong timer rate.

The transmitter keys its "Normal" cadence from TIM2 at 72 MHz / 72 / 101 =
9 901 Hz, one slot every 50 ticks: **5.05 ms per slot**, 0xB6B6 repeating every
8 slots (40.4 ms). The receiver's 5 ms sample (200 ticks of 25.016 µs =
5.003 ms) is therefore **0.94 % short of the transmitter's slot** before any
oscillator tolerance is counted. The transmitter's second cadence keys the
carrier at about 825 Hz in 101 ms phases.

## Speaker

`0x0800B364` writes TIM5 CCR4. While a beep is active the duty alternates between
900 and 700 (of 1 600) every 8 ticks = 0.2 ms, a **2.5 kHz** tone on the 40 kHz
carrier; silence is a steady 800. Beep length is the keep-alive byte at
0x2000010C, in milliseconds, counted down by TIM1.

## Gain control (channel 3)

Every 500 ms, together with the battery, `0x080084D8` takes a trimmed mean of
ADC channel 3 (PA2), keeps it as a gate for the analysers (mode 0 runs only when
it is ≥ 2, mode 1 only when level/580 ≥ 1) and writes level/580 (0..7) as a
3-bit code to PB12..PB14 (`0x0800A4FC`; active low, and level 0 is written as
the same pin pattern as level 3). That looks like an automatic gain or
attenuator select for the analogue front end with a default step, or a level
display; the schematic decides which. It matters twice: the digital mode is
silently disabled when that input reads zero, and if the front end really
auto-ranges every 500 ms then no amplitude measured in firmware (F4) is
comparable across steps until PA2 and PB12..PB14 are identified on the board.

## Power

- **Auto-off**: 300 000 ticks = **5 minutes** without keep-alive. Keys and every
  detected signal set the keep-alive, so a receiver that is hearing tone stays on.
  Correct as designed; no change needed.
- **Power-off** `0x08007570`: PA10 high, PA8 low, PB15 low, PB8 high (latch released).
- **Battery** `0x08007770`, every **500 ms**: trimmed mean of five ADC samples,
  `mV = raw × 6600 / 4096` (same divider and reference as the TX; the grid is 1.6 mV).
  Low-battery LED (PA15) at or below 3579 mV, cleared at or above 3621 mV: proper hysteresis;
  PB4 blinks at 1 Hz in the low state.
  Below **3280 mV** the state becomes "critical" and the unit powers off after
  five readings, **2.5 s later**.

## Device binding (informational)

`main` calls `0x0800BAE8` once at power-on. It reads the 96-bit chip UID, loads a
key pair from the record at `0x08006700`, and on first boot (record word 0 not
yet 0xFFFFFFFF) encrypts the UID with a small modular-exponentiation cipher
(30-bit modulus 0x249EC503), rewrites the record (erasing page `0x08006000`)
and writes the tag `_V3.` at `0x0800676C`. On every boot it decrypts the stored
16 bytes and compares them with the UID; `main` then also requires the `_V3.`
tag to be present. Both checks hang the unit forever on failure.

For this project the point is simple: **the record lives outside the
application image**, so replacing the application does not touch it, and a
unit that has booted stock once will boot a patched image without going through
provisioning. Nothing in `rx-sdk` reads or writes that page.

## Findings

### F1. Critical-battery shutdown cannot be cancelled (bug, same family as the TX) — FIXED in `APP_LPM-10RX_PN1.0.bin`

One reading below 3280 mV moves the state to critical; the counter then runs to
five and calls power-off 2.5 s later. Nothing moves the state back if the
voltage recovers. A beep burst is exactly the load that dips a tired cell for
one reading.
Fix (`rx-sdk`, patch `batt-critical-recover`, 28 bytes in place): each reading
at or above 3400 mV returns to the low state and clears the counter, so only
five consecutive readings (2.5 s) below 3400 mV power the probe off. The
counter still wraps as a byte, exactly like stock. Verified by running the real
routine under emulation on stock and mod with a fake ADC: nine voltage
sequences with their expected state traces, the shutdown timing, the recovery
boundary (raw 2110 = 3399 mV does not recover, raw 2111 = 3401 mV does), and
the register facts the in-place code relies on (`rx-sdk/verify.py`, 25 checks).
A mis-edited image with a different threshold or branch target fails the byte
and trace checks.

### F2. Digital detection is an exact 16-bit match with no phase tolerance (accuracy)

Mode 0 requires all 16 slots of a period to be read correctly, twice, within
240 ms. Each 5 ms sample is averaged over only the last 2.5 ms of the slot, the
receiver's sample is 0.94 % shorter than the transmitter's slot by construction
(9 901 Hz against 39 975 Hz / 4, both with their period registers off by one),
and both clocks carry their own tolerance (the receiver's is a factory-trimmed
RC oscillator). The sampling point therefore walks through the slot
continuously, about once every 0.5 s, and for roughly 40 % of each walk the
averaging window straddles slot transitions and the pattern breaks. The
expected symptom on hardware is beeping that stutters in a slow rhythm even
with the probe held still, and a shorter usable range than the analogue level
would allow.

Fix, receiver firmware only: sample four times per slot (every 1.25 ms), keep
the last 64 samples, and correlate the known pattern at all four phases with a
tolerance of two wrong bits per period, choosing the best phase. That removes
the dropouts and extends range at low signal levels. The correlation score is
also a signal-strength estimate, which the current digital mode does not have
(see F4).

### F3. ADC readings are one conversion behind, and TIM1 pre-empts the sampler (design note for F2)

`adc_read_channel` (`0x080072A4`) selects the channel, starts a conversion and
reads the data register without waiting for end-of-conversion, and the ADC is
single-shot, so every reading returned is the **previous** call's conversion.
TIM1 (priority 1) pre-empts TIM5 (priority 2), and every 500 ms it runs ten
conversions on channels 2 and 3 in the middle of mode-0 sampling: the next
mode-0 sub-sample is a channel-3 value and the first battery sample a channel-1
value. Stock tolerates this only because every consumer takes a trimmed mean of
five. A rewritten sampler (F2) that keeps single readings must wait for
end-of-conversion or discard the first reading after a channel change.
(An earlier version of this note claimed the mode-0 buffer had a stale slot; it
does not: readings land in slots 4..0 at sub-steps 6..10.)

### F4. No strength indication in the digital mode (usability)

Mode 0 answers yes/no. Picking the right cable out of a bundle needs a graded
indication, which only mode 1 gives, in three coarse steps. With F2 in place,
the correlation amplitude can drive beep rate (or pitch) in five or more steps,
provided the gain-control question above is settled first.

### F5. Keys (checked, fine)

Every key is debounced over six consecutive 5 ms scans. The mode key toggles
between modes 0 and 1 and sets the two mode LEDs; PD15 selects the mains mode;
PD14 toggles the lamp. Each press gives a 100 ms confirmation beep.

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
40 kHz ADC on the RX) is fixed by the hardware; the ceiling is set there, not in code.
Everything above needs bench time with a real bundle, because signal levels cannot
be emulated the way the logic was.

## Not read yet

The receiver's **bootloader** (`0x08000000..0x080067FF`) is not part of the
image and has not been read. It decides how update mode is entered, what image
length it accepts, and whether it checks the `_V3.` tag or the version page.
Until it is dumped (SWD, or from a future FNIRSI package) the flashing
procedure stays unconfirmed and every patch stays in place, same length. The
image itself ends exactly at its file size (`0x0800CE28`), 472 bytes short of
its last 2 KB page, so there is no free tail inside the file either.

## Suggested order

1. Flash PN 1.0 on the transmitter first; nothing here changes the wire signal.
2. Read the receiver's bootloader, find out how the receiver enters its update
   mode (FNIRSI's readme does not say) and confirm the stock image can be
   written back. Only then F1 (`APP_LPM-10RX_PN1.0.bin`, built and
   emulation-verified).
3. One bench measurement of the 40 kHz speaker carrier / 2.5 kHz beep tone, and
   identification of PA2 and PB12..PB14 on the board.
4. F2 + F4 together as one receiver release, tested on a bundle of at least five
   cables at 1 m, 10 m and 50 m.
