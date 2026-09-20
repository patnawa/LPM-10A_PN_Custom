# RX live runtime reverse-engineering plan

The live SWD link can read SRAM and peripheral state while application flash
is protected. This permits diagnosis and identification of behavior families;
it does not authenticate an installed PN image. This plan issues no hardware
commands and changes no firmware.

**Subsequent live Digital capture established a different runtime layout.**
The measured receiver uses GAP at `0x2000005C`, Digital index at `0x2000005D`,
and RECENT at `0x2000006E`; these are two bytes above the supplied V3.0.0
locations. The interrupt counters and BEEP address remain unchanged. See the
[live release report](RX-LIVE-DIGITAL-RELEASE-2026-09-20.md) for validated
mapping and the observed 0.82–0.86-second tail after final detection. The
V3.0.0 map below is a reference model, not the installed device's current ABI.

## Current active runtime: battery first, three-wire SWD

The owner reports that RX would not start with the earlier STLink connection,
but started normally after disconnection. RX was then powered from its battery
first, followed by GND/SWCLK/SWDIO only, with no STLink 3.3 V or 5 V supply.
The owner confirmed RX remained on. This supersedes the earlier inactive
capture as the basis for runtime diagnosis.

[The new live recording](experiments/results/rx-swd-battery-on-2026-09-20.json)
shows enabled TIM1 and TIM5 update interrupts, PSC=0 on both, TIM1 AR=64000,
TIM5 AR=1600, and advancing interrupt counters. Over 1.043210100 seconds,
TIM1 increases by 1,051 and TIM5 by 42,011:

| Calculation | TIM1 | TIM5 |
|---|---:|---:|
| First-to-last counter difference / host elapsed time | 1,007.467 Hz | 40,270.891 Hz |
| Linear least-squares slope across all 10 samples | 1,007.431 Hz | 40,270.053 Hz |
| Nominal stored configuration at 64 MHz | 999.984 Hz | 39,975.016 Hz |

The measured counter ratio is 39.97241 versus nominal 39.97564. Both rates are
about 0.75% above nominal; this is consistent with a common clock difference
and host sampling uncertainty, rather than a tenfold TIM1 slowdown. Reads are
sequential and host timestamps bracket acquisition imperfectly. This quiet
baseline does not exclude a load-dependent interruption during reception.

The associated 24 KiB live dump is
`C:/Users/Alpha/Desktop/LPM-10RX-SWD-2026-09-20/rx-sram-battery-on.bin`, SHA-256
`cb1f687cb85924c1496c989368f41bc49394cc69b65db994c73690df8fc185b8`.
It contains the expected clock-result values 64/64/32/32/64/64 MHz at
`0x20000030`. Initial decoding with the stored V3.0.0 map gave `MODE=0`,
`ACTIVE=0`, `GATE=0`, `GRADE=0`, `RECENT=0`, `BEEP=0` and a zero sample buffer;
the later active capture showed that several of these labels used the wrong
addresses. The extra initialized-data byte
at `0x20000009` is now zero. Hardware clock configuration remains
`RCC_CFG=0x0008240F`. Clock/counter compatibility does not authenticate the
application or prove its other state locations.

The initial `0x200000EF=0` observation appeared inconsistent with modern PN
sample ownership under an unchanged-layout assumption. That assumption is now
superseded: `0x200000EF` falls within the inferred shifted sample buffer, and
`0x2000005D` demonstrably contains the Digital index rather than PN strength.
Neither byte can support the earlier ownership/grade interpretation.

`DWT_PCSR` repeatedly returns `0x40000000`, also the observed DWT control
value. It supplies no usable application PC here; do not infer execution at
that address. Continue with live SRAM and peripheral observations.

## Earlier inactive capture, retained for comparison

The first 24 KiB SRAM capture is
`C:/Users/Alpha/Desktop/LPM-10RX-SWD-2026-09-20/rx-sram-live-2206.bin`, SHA-256
`673e3bacad0e1d01321ad0eed70a64a1ab2b3eceea8a1a2299a1d84108a59a8b`.
It was read without halting, so its contents are not an atomic snapshot.

- `0x20000004` contains 64,000,000. The first 24 bytes match the stored
  application's initialized data except `0x20000009`, which is 1 instead of
  its stored initial 0. That extra byte has no established meaning.
- Every byte from `0x20000030` through `0x20000113` is zero: clock-result
  globals, sample buffer, both interrupt counters and all known detector state.
- Later [eight live samples](experiments/results/rx-swd-runtime-samples-2026-09-20.json)
  still show zero counters and zero mode/feedback state. `DHCSR=0x01010000`
  reports no halt, sleep or lockup, with instruction retirement observed.
- [Peripheral reads](experiments/results/rx-swd-peripherals-2026-09-20.json)
  show both timers uninitialized: control, interrupt-enable, counter and
  prescaler zero, period `0xFFFF`. RCC configuration is `0x0008240F`, while
  current PB1/PB2/PC13 inputs are high. Configured clocks alone do not establish
  entry into the sampling loop.
- `VTOR=0x08006800` is consistent with the application location shared by the
  stored images. It identifies neither their content nor their version.
- Bootloader-range pointer-like words at SRAM `0x20001724/174C` may be residue.
  Stack-looking words and uncleared high SRAM cannot establish the current PC.

Under the known application's layout, that earlier capture was **not an active sampling loop**.
A startup wait, a different runtime layout, or another runtime state remains
possible. It must not be interpreted as a captured Digital release failure.

## Read-only measurement addresses

Read only the listed registers, retaining host start/end timestamps. All
addresses below are 32-bit aligned. Avoid broad peripheral dumps, ADC result
reads, timer event registers and write-only registers. No halt, reset, unlock,
option-byte changes, SRAM writes, injected code or flash operation is needed.

| Purpose | Exact addresses |
|---|---|
| RCC clock/source/enables | `40021000`, `40021004`, `40021018`, `4002101C`, `40021024`, `4002102C`, `40021040` |
| TIM1 control/interrupt/status | `40012C00`, `40012C0C`, `40012C10` |
| TIM1 counter/prescaler/period/repetition | `40012C24`, `40012C28`, `40012C2C`, `40012C30` |
| TIM5 control/interrupt/status | `40000C00`, `40000C0C`, `40000C10` |
| TIM5 counter/prescaler/period/speaker compare | `40000C24`, `40000C28`, `40000C2C`, `40000C40` |
| Startup inputs/output latch | GPIOB input `40010C10`, output `40010C14`; GPIOC input `40011010` |
| Mode/lamp inputs and outputs, if needed | GPIOD input `40011410`; GPIOA output `40010814` |

These addresses are independently present in the stored application. Register
definitions were checked against the [Nations N32L40x user manual](https://www.nsing.com.sg/uploads/MCUProducts/N32L40x/Chip_Documentation/User_Manual/EN_UM_N32L40x_Series_User_Manual.pdf):
printed pages 4–6, 59–60, 83, 114–115, 197–198 and 255–256 (PDF pages are 25
higher). `RCC_CFG2[29]` selects the TIM1/8 clock source; TIM1 repetition is at
offset `0x30`, which is reserved on TIM5. GPIO input/output are `+0x10/+0x14`.
Use actual registers rather than the older reversed GPIO helper names.

In the known image, TIM1 should eventually have PSC=0, AR=64000, REPCNT=0;
TIM5 should have PSC=0, AR=1600. Timer enable and update-interrupt enable are
bit 0 of their control and interrupt-enable registers. A running hardware
counter with a stationary SRAM interrupt counter points toward interrupt
delivery or a changed SRAM layout; stopped timers point earlier in startup.

Known startup branches precede the clock-result stores and timer setup:

- PB2 low in at least three of five startup reads enters `0800B7D8..B842`,
  subsequently examining PB1/PB2. Its physical charger purpose is inferred.
- PC13 low holds execution in `0800B84A..B85E` until power-key release.
- License/version-tag checks can wait at `0800B86A` or `0800B880`.

GPIO levels alone cannot prove a historical startup branch. Normal receiver
operation and advancing counters have now been established in the later
battery-powered session above.
In particular, the PB2 startup branch can latch into the permanent loop at
`0800B81E` after PB1 and PB2 become high; their present high levels do not
exclude that earlier path.

An optional read-only localization attempt is `DWT_PCSR=E000101C`, with
`DWT_CTRL=E0001000` for implementation information. The
[ARM Cortex-M4 technical reference manual](https://documentation-service.arm.com/static/5fce431be167456a35b36ade)
lists PCSR as a read-only PC sample register and says absent DWT registers
read zero. Try only passive reads in the current state; do not enable trace or
halt the CPU. A zero or unavailable sample cannot establish a PC of zero.

## Known SRAM layout once sampling is active

All multibyte values are little-endian. These meanings are established for the
stored V3.0.0-derived images, not yet for the protected installed application.

| Address | Width | Meaning |
|---|---:|---|
| `20000008` | 1 | Sampling state: 1 acquiring, 0 complete; later profiles use 2 for closed/idle state |
| `20000048`, `49` | 1 each | Mode: 0 Digital, 1 Analog, 2 NCV; later pending mode request = desired mode + 1 |
| `20000055` | 1 | Speaker duty phase |
| `2000005A..5D` | 4 bytes | Gap, Digital index, Analog index, later strength/uncertainty grade |
| `20000068`, `6A`, `6C` | 2 each | Raw sensitivity gate, gate/580, recent-detection countdown |
| `2000006E..ED` | 128 | 64 ADC samples; Digital uses first 48 |
| `200000EE`, `EF` | 1 each | Digital subsample position; later ownership/gate state (0 invalid, 1 closed, 2 open) |
| `200000FC`, `20000100` | 4 each | TIM1 and TIM5 delivered-interrupt counters |
| `20000104` | 4 | Idle up-counter used for automatic power-off |
| `20000108`, `0A`, `0C` | 1, 2, 1 | NCV index, power-key hold ticks, BEEP countdown |
| `2000010E`, `110`, `112` | 2 each | SCAN, NCV and lamp debounce counters |

For a short release recording, the useful small reads are `20000048` length
`0x28` and `200000EC` length `0x28`. Together they capture feedback, ownership,
indices, interrupt counters and BEEP in 80 bytes. Read the sample buffer less
frequently and bracket it with index/counter reads: it can change mid-transfer.
Never interpret a live buffer as one coherent completed window without an
ownership check.

## Measurements that distinguish the delay

First record a quiet baseline, then sustained Digital reception, then TX Pause
while retaining simultaneous audio/video. Sample the small RAM windows as fast
as the existing read-only link allows, ideally every 10–20 ms; report actual
timestamp gaps rather than the requested polling period. One 160 ms interval
cannot resolve a 30/50 ms pulse. Record the TX action's time independently.

At the stored nominal clock, delivered rates are approximately TIM1=999.984/s,
TIM5=39,975.016/s; their ratio is 39.97564. Compute differences modulo 2^32.
Changing CPU frequency, missed interrupts and a changed layout require separate
interpretation; the RAM clock value alone does not prove physical frequency.

| Observation after TX Pause | Supported interpretation |
|---|---|
| BEEP repeatedly rises after falling to zero | Repeated software scheduling, not one stretched pulse |
| BEEP remains nonzero while TIM1 stalls and TIM5 advances | Consistent with the older TIM1-owned countdown failure hypothesis |
| GRADE becomes zero and stays zero, but BEEP keeps reloading | Inconsistent with the stored modern scheduler under this layout |
| RECENT is refreshed and valid grades continue with new sample windows | Continued detector acceptance; examine residual input/windows |
| RECENT counts down through 500 yet normal new pulses start | Consistent with older hold logic, incompatible with PN1.7+ scheduling under this layout |
| Both SRAM counters remain zero | Runtime/layout is still unestablished; stop release interpretation |

Normal PN1.7+ Digital pulses start at 30 ticks. PN1.9+ uncertainty uses 100.
PN1.11+ Analog also uses 30/100; NCV retains 50/100/200. A key adds a separate
100-tick confirmation, so exclude key presses from detector cadence inference.
The modern Digital gate requires `RECENT>500`; new Digital acceptance publishes
800 and modern Analog publishes 600.

## Identity limits

A persistent gate-state byte of 2 and a nonzero grade support later state
ownership logic. Digital index cycling through 32..47 after first acquisition
supports PN1.11+'s retained-32/new-16 overlap; earlier full-window acquisition
starts again at zero. These signatures need a time series in confirmed Digital
mode, and can be shared by other firmware.

PN1.12 and PN1.13 share detector layout and nearly identical normal timing.
When both interrupt clocks run normally, passive SRAM observations cannot
uniquely distinguish them: PN1.13 only moves BEEP/GAP decrement ownership to
every fortieth TIM5 tick. Do not force an interrupt failure to fingerprint it.
Existing filenames, a `3.0.0` data string, USB `3.0.1.TXT`, VTOR and static SRAM
initializers are not installed-image hashes. A previously tested visible marker
or an authorized, available exact readback remains stronger identity evidence.
