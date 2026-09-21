<div align="center">

# LPM-10A PN Custom Firmware

Unofficial firmware for the **FNIRSI LPM-10A** network cable tester (TX) and its tone probe (RX).
Built by patching the shipped binaries — no vendor source — and verified by emulation and on a real unit.

![tester](https://img.shields.io/badge/TX-PN%202.14-blue) ![receiver](https://img.shields.io/badge/RX-PN%201.23-blue) ![licence](https://img.shields.io/badge/licence-MIT-green)

<img src="docs/img/length_screen.png" alt="Length screen: stock (whole metres) vs PN Custom (one decimal, Zero and NVP calibration)" width="1000">

</div>

## Current firmware

| Device | Version | Download | File to copy |
|---|---|---|---|
| **TX** tester | **PN 2.14** | [Release v2.14](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/v2.14) | `LPM-10A-TX_PN2.14-tone-recovery.bin` |
| **RX** probe | **PN 1.23** | [Release rx-v1.23](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/rx-v1.23) | `APP_LPM-10RX_PN1.23-mains-tone-update.bin` |

Both are the builds running on the owner's unit (2026-09-21; RX PN 1.23 tested in all three modes). Each release carries its notes and a
SHA-256 file. **TX and RX firmware are not interchangeable.** FNIRSI's own files are not
redistributed here.

> **สรุปภาษาไทย:** TX ใช้ PN 2.14, RX ใช้ PN 1.23 · TX อัปเดต: ปิดเครื่อง → กด **M + Power** ค้าง → เสียบ USB → ก๊อปปี้ไฟล์ ·
> RX อัปเดต: ปิดเครื่อง → กด **SCAN** ค้าง → เสียบ USB → ไดรฟ์ `BOOTLOADER` → ก๊อปปี้ไฟล์ **`-update.bin`** ด้วย Explorer →
> ไดรฟ์หายใน 1 วิ = เสร็จ · รายละเอียดและวิธีย้อนกลับ: [คู่มืออัปเดต RX](docs/RX-UPDATE-GUIDE.md)

## Install

### TX (tester)

1. Check the download: `certutil -hashfile LPM-10A-TX_PN2.14-tone-recovery.bin SHA256` →
   `a7402de6f18e39df55bbe53f5641efd5135f0de4d81f9407515cf9d8710c5527`
2. Tester off. Hold **M + Power** until the firmware-update screen appears.
3. Plug in USB-C; a removable drive appears.
4. Copy the `.bin` onto the drive. Do not unplug while it writes.
5. Long-press Power to shut down, then power on. Settings › About shows `Software:PN 2.14`.

If the drive refuses the file, rename it exactly `LPM-10A-TX_V2.0.7_260610.bin` and copy again
(some bootloaders match on the file name; the name inside the image is already the stock one).
**Back to stock:** same procedure with FNIRSI's `LPM-10A-TX_V2.0.7_260610.bin`
([fnirsi.com](https://www.fnirsi.com) → downloads). The bootloader and its update screen are never touched.

### RX (probe) — read this, the FNIRSI file will not work as shipped

1. Probe off. **Hold SCAN**, plug USB into the PC. A drive named **`BOOTLOADER`** appears.
2. Copy **`APP_LPM-10RX_PN1.23-mains-tone-update.bin`** onto it with Explorer (an ordinary copy).
3. Within about **one second the drive disappears**: the probe has programmed the file and restarted.
   Unplug USB; press the power key if it is silent. PN 1.14+ chirps high→low at power-on; entering the
   drive again (no copy) shows `PN1.23.TXT`, the installed build.

Only the **`-update.bin` container** is accepted. The raw image FNIRSI ships for the RX — and every
`.bin` without `-update` — is silently ignored (the drive's status file shows `UNKOWN.TXT`). Slow or
sector-by-sector copy tools make the bootloader give up (`APPRUN.TXT`). **Back to stock:** wrap FNIRSI's
`APP_LPM-10RX_V3.0.0_260416.bin` with `python -m lpm10rx.container wrap …` and copy it the same way.
Everything about the RX update — why it never worked, the container format, what was changed, status
files, rollback, troubleshooting — is in **[docs/RX-UPDATE-GUIDE.md](docs/RX-UPDATE-GUIDE.md)** (Thai + English).

<img src="docs/img/rx-update-container.png" alt="RX update: a raw image is ignored; the -update.bin container (32-byte name, 0x1000 header, image) is programmed" width="1000">

## What PN changes

There is no vendor source. PN patches FNIRSI's shipped binaries: it disassembles them, adds code in
unused flash (TX: the tail of the last used sector, RX: appended after the image), re-assembles and
verifies the result — every patch is checked instruction by instruction, the TX screens are rendered
from the firmware's own draw code, and the RX helpers are executed on a CPU model. Below, each change is
explained: what stock does, what PN does, how it works and how it was checked.

### TX (tester) — summary

| Area | Stock | PN Custom |
|---|---|---|
| Length display | whole metres, cm forced on every entry | **m / cm / ft with one decimal**, unit remembered |
| Cable calibration | none | **Zero 0.0–2.0 m and NVP 50–99 %** on the Length screen, saved (factory = 0.0 m / 69 %) |
| Length stability | one TDR run (±0.3 m scatter at 14 m) | **four runs averaged per pair**; `~` marks pairs with fewer runs |
| Blind pairs | `0.0 m` | **`< 2 m`** (`< 200 cm`, `< 7 ft`): the PHY cannot time echoes inside ~2 m |
| Low battery | one sample < 3150 mV starts an uncancellable 30 s shutdown | three consecutive samples; cancels on recovery or charging |
| Battery gauge | 4 steps | 10-step Li-ion curve, red at ≤ 20 % |
| Auto Off | keeps counting during a SCAN tone or FLASH blink | held while a tone or blink session runs |
| Port FLASH | fixed phase counter | blink timed from the PHY link; 1.5 s on / 1 s off minimum; back-off 4 → 8 → 16 s |
| PoE screen | voltage drawn once; blank without a supply | **voltage refreshed every 0.5 s**; "Detecting…" then "No PoE"; "Standard : Yes / No" |
| Tone (SCAN) menu | Noiseless / Normal | **Digital 454 kHz** and **Analog 825 Hz** — the two the probe decodes |
| Cable Test | Back leaves the screen; error text hidden under a button | Back returns to the Switch / Far-end choice; error line visible |
| Language | Chinese / English | **ไทย / English** on every screen; picker on first boot |
| Font | thin serif | Ubuntu Sans Mono + Sarabun (Thai), rendered from the firmware's own layout tables |
| Reliability | heap leak on settings save, timer-path logging, FP crash frame | fixed; watchdog on the service task; fault records kept across warm reset |
| Identity | `Software:V2.0.7`, fnirsi.cn | `Software:PN 2.14`, this repository's URL; bootloader-facing image name unchanged |

### TX (tester) — in detail

<details>
<summary><b>Length: one decimal, m / cm / ft, unit remembered</b></summary>

*Stock* shows whole metres (`cm/100`, rounded), offers inches (`cm / 2.54`, truncated) rather than feet,
and forces the unit back to cm every time the screen is opened.

*PN* keeps the PHY's centimetre value all the way to the display and prints it with one decimal:
`m: (cm + 5) / 10` tenths, `cm: cm`, `ft: (cm × 1000 + 1524) / 3048` tenths — integer arithmetic,
rounded, using the firmware's own `sprintf`. The unit lives in settings byte `0xA7` (a byte stock ignores)
and survives power cycles. A value that would not fit the field prints `OVR` instead of overflowing.
</details>

<details>
<summary><b>Cable calibration: Zero and NVP</b></summary>

The tester does not time pulses itself; it runs the *Cable Status Diagnostic* of the Motorcomm YT8531
PHY, which reports one centimetre value per pair. That value is `v_assumed × t / 2`, where `t`
includes the chip's own signal path, so the reading is really `k × length + offset` with two unknowns:

- **NVP** (nominal velocity of propagation, 0.64–0.70 for twisted pair, different for every cable
  batch) fixes `k`. Every percent of NVP error is a percent of length error; stock used one fixed
  constant inside the PHY (equivalent to 69 %).
- **Zero** fixes `offset`: on the tested unit every length read about **+0.4 m** too long — the delay
  through the PHY front end and connector, which no factor can remove.

PN computes `length = (raw − Zero) × NVP / 69`, exactly:
`cm0 = cm − 10 × Zero` (≤ 0 → 0), then `cm' = (cm0 × NVP + 34) / 69`. Zero is 0.0–2.0 m in 0.1 m steps
(settings byte `0xC5`), NVP 50–99 % (byte `0xA6`); 0.0 m / 69 % reproduces stock's number exactly, so
the factory state is unchanged. Both are shown on the Length screen (`ZERO 0.4m` left of the Unit box,
`NVP 68%` right): UP / DOWN change the white one (hold for auto-repeat), **hold OK about a second** to
swap which is white; every change redraws the four readings at once, no re-measure needed. Saved when
leaving the screen and at power-off; Factory Reset returns to 0.0 m / 69 %.

Calibrating with two cables of known length L₁ (short, ~3 m) and L₂ (long, ≥ 15 m), raw readings R₁, R₂
at 0.0 m / 69 %: `NVP = 69 × (L₂ − L₁) / (R₂ − R₁)`, `Zero = R₁ − L₁ × 69 / NVP`. On the tested unit a
2.9 m cable read 3.34 m and a 14 m cable 14.7 m → NVP ≈ 67 %, Zero ≈ 0.4 m; dialled in on the screen it
settled at **Zero 0.4 m, NVP 68 %**. Worked example at those settings: run mean 1470 cm → 1470 − 40 = 1430
→ (1430 × 68 + 34) / 69 = 1409 → (1409 + 5) / 10 → **14.1 m**.
</details>

<details>
<summary><b>Four-run average and the <code>~</code> mark</b></summary>

The PHY resolves the echo to about ±1.5 ns per run, which at NVP 0.68 is ±0.3 m — the run-to-run scatter
seen on the bench (±0.2 m at 3 m, ±0.3 m at 14 m). Stock showed one run as is (with a single retry when
the four pairs disagreed). PN runs the diagnostic **four times** and averages each pair over the runs in
which it returned a non-zero value (`mean_i = floor(Σ runs_i / n_i)`); the 20 s timeout restarts per
run, so a test takes four times longer. A pair that yielded only 1–3 runs is marked `~`. This halves the
scatter and is why the calibration above settled from 0.5 m to 0.4 m.
</details>

<details>
<summary><b>Blind pairs: <code>&lt; 2 m</code> instead of <code>0.0 m</code></b></summary>

Below about 2 m the echo returns while the pulse is still being launched and the PHY reports nothing
usable; stock discards raw readings ≤ 200 cm (before Zero is subtracted) and printed such a pair as
`0.0 m`, which reads like a measurement. PN prints **`< 2 m`** (`< 200 cm`, `< 7 ft`) for a pair whose
converted value is 0, and still says *Out of range* when all four are zero. On a long cable such a pair is
open within its first two metres; the Cable Test (wiremap) screen tells which one. This is the PHY's
limit, kept as is: a 1 m cable is not measurable (an experimental build lowers the cut-off to 0.5 m only
to collect raw readings).
</details>

<details>
<summary><b>Low-battery shutdown and the battery gauge</b></summary>

Pack voltage is `mV = raw × 2 × 3300 / 4096` (12-bit ADC, 3.3 V reference, 1:2 divider; 1 LSB ≈ 1.6 mV),
sampled once a second, skipped while a test runs, armed only with no charger connected.

*Stock* started an **uncancellable 30 s shutdown from a single sample below 3150 mV** — one noisy sample
(a beep burst is exactly the load that dips a tired cell) could switch the tester off mid-job; only a
charger cancelled it. *PN* arms it after **three consecutive samples** below 3150 mV (≥ 3 s), cancels it
when the pack reads ≥ 3250 mV again or the charger is connected (100 mV hysteresis), and clears the
debounce on cancellation and at start-up. Charger state is GPIO (PC10 low = charging, PA15 low = full),
unchanged.

The gauge had four values (`> 4000 → 100`, `> 3800 → 80`, `> 3600 → 50`, else `20`) and the icon only drew
those four. PN uses a single-cell Li-ion open-circuit curve in ten steps (`≥ 4150 → 100, ≥ 4050 → 90,
≥ 3950 → 80, ≥ 3870 → 70, ≥ 3800 → 60, ≥ 3750 → 50, ≥ 3700 → 40, ≥ 3650 → 30, ≥ 3600 → 20, ≥ 3450 → 10,
else 0`), the icon draws `pct / 10` segments and turns red at ≤ 20 %. Stock's debounce (a new
percentage after two agreeing samples; it only falls while discharging) is kept.
</details>

<details>
<summary><b>Auto Off held during a tone or blink session</b></summary>

Auto Off is `{OFF, 5, 10, 15}` min, reset on every key and after every Length / Speed result. Stock kept
counting while the SCAN tone or the Port FLASH blink was running, so a tracing session ended with the
tester switching itself off. PN holds (and restarts) the counter while a tone or blink session is active
and leaves everything else as stock. (PN 1.0–2.2 held it during SCAN only — the FLASH branch compared
the wrong state number; fixed in PN 2.3.)
</details>

<details>
<summary><b>Port FLASH timed from the PHY link</b></summary>

Port FLASH makes a switch port's LED blink so you can find the port. The tester advertises 10BASE-T only
(the fastest-linking speed), and stock ran a fixed 5 s phase counter (4 s PHY up, 1 s down) that ignored
whether the link had actually come up — the switch's own re-link (Clause 28 break-link timer plus
auto-negotiation, 2–3 s) ate most of the "up" window, and a GPIO input pattern could restart the hold
timer indefinitely (LED stuck on).

PN polls every 500 ms and drives the cycle from the PHY's link state: wait for link (re-asserting
power-up every tick, power-cycling again after 4 s without a link) → hold **1.5 s** from the tick that saw
the link → PHY off for **1 s** minimum → power-up → wait for link. Failed negotiations back off 4 → 8 →
16 s and the working window is kept for the session; the tester's own LED and screen indicator follow
the same published link state. Since PN 2.12 the link comes from the PHY's current status register
(historical latch-low status cleared, all-ones MDIO reads rejected) and battery monitoring stays active
during FLASH. Confirmed on a D-Link gigabit switch. Links needing more than 16 s can still fail.
</details>

<details>
<summary><b>PoE screen: live voltage, "Detecting…", "No PoE"</b></summary>

PoE voltage is `mV = (max − min of 4 ADC channels) × 3300 × 40 / 4096` (1:40 divider); the class comes
from two comparator inputs (PA6/PA7 → 802.3af / at / bt / bt, printed as Class 3 / 4 / 6 / 8).

*Stock* drew the voltage **once**, from the sample a tick or two after the first one above 40 V, and never
refreshed it while the screen was shown (the two wires of a pair could even disagree); with no supply
the screen stayed **blank**, because its 3.5 s "no supply" timeout fired once per power-on — usually
before the screen was ever opened — and was never re-armed. *PN* refreshes the voltage column **every
0.5 s** while a supply is present (every wire from one latched sample), clears it the moment the supply
goes, shows **"Detecting…"** on entry and **"No PoE"** 3.5 s later without a supply, every time, and
prints "Standard : Yes / No" instead of "Standar / UnStandar". The stock "unstable supply" check compares
byte data against 40 000 and can never trigger; it is documented and left alone. The supply paths were
verified by emulation; the no-supply path on hardware (no PoE switch or injector was available).
</details>

<details>
<summary><b>Tone menu: Digital 454 kHz and Analog 825 Hz</b></summary>

The SCAN screen drives the cable with a ~454 kHz carrier from TIM2 (10 kHz tick, 5 ms slots). **Digital**
keys the carrier with the 16-slot code `0xB6B6` (period 8 chips, ~198 chips/s) that the probe's Digital
mode decodes; **Analog** keys it at ~825 Hz for the probe's Analog mode (any analogue tone probe hears it
too). Stock labelled them "Noiseless" and "Normal"; PN names them by what they are (454 kHz is the
carrier, 825 Hz the modulation — neither is the probe's beep frequency), fixes one lost tick at the
digital wrap, the debug logging in the timer path, the stale carrier state after Pause and a RIGHT-key
carrier-cache defect, and removes two experimental modes (Sync32, Pulse test) that the probe does not
use. Pair TX Digital with RX Digital and TX Analog with RX Analog.
</details>

<details>
<summary><b>Cable Test: Back returns to the Switch / Far-end choice; the error line is visible</b></summary>

Stock's Back key left the Cable Test screen from every step, and the red "Result error!!" line was
painted underneath the Test Retry button. PN's Back returns to the Switch / Far end choice from the
armed and result screens (a `tbb` byte and two spare `nop`s at the key handler), and the button moved
9 px down so the error line sits above it.
</details>

<details>
<summary><b>Thai interface and fonts</b></summary>

The firmware has three glyph tables (column-major bitmaps; the Chinese strings are glyph indices, not
GB2312). PN regenerated them in the same cells so no layout changes: **Ubuntu Sans Mono** (8×16 and
6×12) replaces the thin serif for English, and in PN 2.0 the 171-glyph Chinese table carries **118
Sarabun 13 px Thai cells** instead, one per consonant cluster, drawn proportionally by a replacement
text drawer that keeps the stock drawers' signatures. Every Chinese string slot became a 3-byte redirect
to the Thai text in the freed glyph slots; messages stock only had in English got Thai versions through
a hook on `gui_blit` that is inert in English (English is byte-for-byte PN 1.3). The language picker
appears on first boot and after a factory reset. The screens shown on this page are what the firmware
draws — `verify.py` compares all 61 screen states pixel for pixel against the model. All fonts are
open-licensed (Ubuntu Font Licence, SIL OFL).
</details>

<details>
<summary><b>Reliability: settings save, service task, watchdog, fault records</b></summary>

Stock leaked 204 bytes of heap on every settings save and saved calibration only at power-off; PN uses a
checked static writer for explicit saves, default setup, power-off and changed Length calibration, with
no heap allocation (writes stay single-page and are not power-fail atomic). Stock called application
queues from SysTick and fed the watchdog from a timer; PN defers the ten SysTick application callbacks
into a service task, the watchdog (IWDG, ~3.3 s) requires service-task progress, a Cortex-M4F FP crash
frame bug and the SHCSR fault handlers are fixed, and fault details survive a warm reset and are shown
on the About screen. 109 TX regression tests cover these paths on the real instructions with modelled
hardware/RTOS boundaries.
</details>

<details>
<summary><b>Identity and the update file</b></summary>

About reports `Software:PN 2.14` and this repository's URL instead of `V2.0.7` / fnirsi.cn. The
container's internal image name stays FNIRSI's, because the bootloader may match on it. Since PN 2.3
the file is one 4 KB flash page longer than stock (393 216 bytes) because the code cave ran out; the
container header carries the payload length and the bootloader accepted the longer file on the tested
unit. Formulas, addresses and verdicts for every calculation: [`FORMULA-AUDIT.md`](LPM-10A/Firmware%20File/FORMULA-AUDIT.md).
</details>

<p>
<img src="docs/img/scan-pn214-en.png" alt="Tone menu: Digital 454 kHz and Analog 825 Hz" width="180">
<img src="docs/img/scan-pn214-th.png" alt="Tone menu in Thai" width="180">
<img src="docs/img/about_screen.png" alt="About screen: stock vs PN Custom" width="620">
</p>

<img src="docs/img/battery_gauge.png" alt="Battery percentage vs pack voltage: stock 4 steps vs PN 10-step Li-ion curve" width="800">

<img src="docs/img/thai/thai_overview.png" alt="Every screen of the Thai interface, rendered from the firmware's own draw code" width="1000">

### RX (probe) — summary

| | Stock (V3.0.0 / 3.0.1) | PN 1.23 |
|---|---|---|
| Sound per mode | one 2.5 kHz beep in every mode | **Digital 2.5 kHz, Analog 1.25 kHz, mains 5 kHz**; key beeps chirp toward the mode (Digital low→high, Analog high→low) |
| Strength feedback | 50 ms beep / 50 ms gap whenever a signal is detected | 30 ms pulses whose **rate reports distance to the cable**: quiet interval 110 ms (weakest) → 20 ms (touching) |
| Sensitivity knob | sets gain; the middle of its travel fell to the lowest gain (firmware bug) | monotonic gain steps; the knob only sets how weak a signal is still accepted — turning it does not change the rhythm; **the gain steps down by itself when the front end saturates** (2 s hold) so two strong cables stay distinguishable at any knob position |
| Signal loss | audio kept going ~1 s after the TX stopped | stops within ~¼ s; a single missed reading no longer cuts the rhythm |
| Very strong signal | — | touching the cable is the fastest rhythm at every knob position (front-end saturation measured at ~2400 counts p-p), then the automatic gain step-down restores distance resolution |
| Update rate | Digital every 80 ms | **Digital every 40 ms** (Analog every 21 ms as before) |
| Detection | exact 16-bit code match | PN 1.12 detector: full-window code search with bounded bit errors, upper-rail handling, guarded sample ownership |
| Installed build | — | the `BOOTLOADER` drive's status file names it: `PN1.23.TXT` |
| Low battery | uncancellable shutdown at one sample | recoverable |

### RX (probe) — in detail

The probe is a Nations N32L406 (Cortex-M4F, 64 MHz, no RTOS). TIM1 ticks every 1 ms (keys, battery,
countdowns, 5-minute auto-off); TIM5 runs at 40 kHz (ADC sampling and the speaker PWM). The front end's
gain is selected by three GPIO lines from the sensitivity knob, read every 500 ms.

<details>
<summary><b>How each mode listens</b></summary>

- **Digital**: one ADC sample per 5 ms slot (the trimmed mean of five readings in the slot's last 2.5 ms),
  48 samples = 240 ms. Stock thresholded the 48 samples at their trimmed mean and slid the bits past
  `0xB6B6`, needing two exact 16-bit matches. PN 1.12's detector searches all rotations of the repeated
  code over the whole frame, tolerates a bounded number of bit errors, keeps stock's exact-match path as a
  fallback, estimates strength from the 16 newest code-verified samples, and treats a fully upper-railed
  window as "uncertain". Since PN 1.21 the frame keeps its newest 40 samples and collects 8 more before
  re-evaluating, so detection and strength refresh every **40 ms** (the first lock after a mode change
  still needs a full frame).
- **Analog**: 64 samples every 0.325 ms (21 ms), a 32-bin DFT, bin 17 = 817 Hz compared with the floor of
  the other bins (margins 600 / 200 / 10). PN keeps the acceptance rule bit-exact but computes the DFT
  with an exact integer inner loop (−74 % CPU) and turns the margin into the same strength score the
  Digital mode uses.
- **Mains (NCV)**: 64 samples every 1.55 ms (99 ms) from a separate input (PD15), DFT bins 5 and 6 = 50.4
  and 60.5 Hz; stock's three-tier beep length (50 / 100 / 200 ms) is kept because this input is not behind
  the gain stage.

Sample ownership between the main loop and the timer interrupt is guarded (PN 1.6): a pending mode
change or a gate transition invalidates the window instead of racing the ADC.
</details>

<details>
<summary><b>One pitch per mode, and the chirp (PN 1.14, 1.23)</b></summary>

The speaker is TIM5 channel 4 PWM at 40 kHz; a beep is made by flipping the duty between 900 and 700
every N interrupts. Stock flipped every 8th (2.5 kHz) in every mode. PN's TIM5 dispatch picks N by mode:
Digital 8 (2.5 kHz), **Analog 16 (1.25 kHz, one octave lower)**, **mains 4 (5 kHz)**. A key press starts a
100 ms confirmation beep; during its first 50 ms the helper uses the *other* mode's pitch, so entering
Digital sounds low→high and entering Analog high→low (the power-on beep is high→low). Tracing pulses are
30 ms (Digital) and 12 ms (Analog) and never reach the chirp half.
</details>

<details>
<summary><b>The rhythm reports distance (PN 1.7–1.9, 1.15, 1.19)</b></summary>

Instead of stock's fixed 50 ms on / 50 ms off, PN plays **30 ms pulses** separated by a quiet interval
taken from a strength curve: score 0 → 110 ms, 800 → 95, 2 400 → 85, 7 200 → 70, 24 000 → 45,
**40 000 → 20 ms** (linear between knots, a 3 ms deadband against jitter). The score is ADC contrast, which
scales with the front-end gain, so on the first hardware run turning the knob up simply sped the rhythm.
Live captures gave the gain step per knob code (peak-to-peak at one position: 95 / 230 / 780 / 90 /
1920 / 1940 / 2040 / 2400 for codes 0–7), and PN 1.15 multiplies the score by the measured step
(×20 / 9.2 / 2.6 / 2.6 / 1.1 / 1.1 / 1.1 / 1.0) before the curve, so **the rhythm reports the signal at
the probe tip and the knob is only a threshold**, as on stock. The curve's fastest point sits at the
front end's measured saturation (~40 000): touching the cable is the fastest rhythm at every knob
position, and a clipped ("uncertain") reading counts as strongest rather than sparse (PN 1.18).
</details>

<details>
<summary><b>Knob gain dead zone, automatic gain range (PN 1.17, 1.22)</b></summary>

`gain_select_3bit` writes the knob level's bits to PB12..PB14 and special-cases level 0 to the pattern
`011` — which is also what level 3 produces, so the middle of the knob (43–56 %) dropped to the lowest
gain in stock. PN 1.17 maps level 3 to level 2's pattern, making the knob monotonic (low / 230 / 780 /
780 / high).

On the high steps the front end saturates at ~2000–2600 counts p-p well before the ADC rail, so on the
cable every nearby conductor sounded the same and Analog could lose its DFT margin. PN 1.22 measures the
sample buffer's peak-to-peak at every 500 ms AGC tick: **≥ 1900 steps the driven gain down** one
effective step (high → 780 → 230 → 90), **< 450 steps back up** toward the knob, a change is held 2 s, and
moving the knob resets to the knob. The strength normaliser reads the gain actually driven, so the rhythm
stays meaningful after a step; the mode gates (Digital raw ≥ 2, Analog code ≥ 1) still follow the knob.
State: four bytes at `0x20000200`.
</details>

<details>
<summary><b>Release, hold and smoothing (PN 1.7, 1.16, 1.17)</b></summary>

Stock kept beeping for 800 ms after the last match — the "one-second tail" after pausing the TX. PN 1.7
released on the first rejected window, which the owner heard as choppiness at marginal signals. PN 1.16
keeps the last interval on a rejected window and instead clamps the freshness countdown (audio needs
> 500): to 660 in Digital (one missed 80 ms update bridged; three at 40 ms) and 560 in Analog, so a signal
that is really gone still stops within ~¼ s. PN 1.17 moves the published interval **half way** toward each
new target (fresh starts and "uncertain" readings jump directly), so a single noisy window shifts the
rhythm half as much and it settles in two to three updates. The sensitivity knob's gate, RECENT
countdown and the 800 ms power keep-alive are stock.
</details>

<details>
<summary><b>Identity, battery and what the drive shows (PN 1.0, 1.20)</b></summary>

Stock armed an uncancellable low-battery shutdown from a single sample; PN 1.0 makes the critical state
recoverable when the pack reads ≥ 3400 mV again. PN 1.20 sets the application's version string to
`PN1.xx`; the application writes it to the version page at boot and the bootloader names the drive's
empty status file after it, so entering the `BOOTLOADER` drive (without copying anything) shows which
build is installed. The device-binding record (the RSA-30 check over the chip UID on the bootloader page)
is outside the image and untouched.
</details>

<p>
<img src="docs/img/rx-measurements.png" alt="RX: measured front-end gain per knob code (stock dropped code 3 to the lowest gain) and the pulse-rhythm curve" width="960">
<img src="docs/img/rx-board.jpg" alt="The probe's board: Nations N32L406 MCU, 4-pin SWD header on the left, sensitivity potentiometer" width="200">
</p>

Everything above was measured live over SWD on the probe while sweeping the knob and moving the probe
(the SWD header is the 4-pin row beside the MCU in the photo):
[docs/RX-SENSITIVITY-2026-09-21.md](docs/RX-SENSITIVITY-2026-09-21.md). The probe firmware, function by
function: [docs/RX-AUDIT.md](docs/RX-AUDIT.md). Pair TX **Digital** with RX Digital and TX **Analog
825 Hz** with RX Analog. Only one hardware unit has been tested; range and cable selectivity are not
quantified against another probe.

## Known limitations

- **Cables of about 2 m and under cannot be measured** (the PHY's TDR blind zone); the Cable Test (wiremap)
  screen still finds the broken pair. Blind pairs read `< 2 m`.
- The TX update file is one 4 KB page longer than stock (code cave grew); the bootloader accepts it.
- Links that need more than 16 s to negotiate can still fail Port FLASH; the PoE "unstable supply" check
  can never trigger (vendor bug, left as is).
- RX Digital evaluates every 40 ms and needs a full 240 ms frame to lock after a mode change; Analog reacts
  faster still. Digital is the mode for noisy places. A matched-filter Digital detector was modelled on
  7,992 live windows and rejected: the 8-chip code and 50 Hz hum make it no more sensitive
  ([assessment](docs/RX-NEXT-STEPS-2026-09-21.md)).
- The RX front-end gain multipliers were measured on one unit; other units may need
  `MULT_X10` in `rx-sdk/gain_norm.py` re-measured.

## Repository layout

```
LPM-10A/Firmware File/
  experimental/LPM-10A-TX_PN2.14-tone-recovery.bin        current TX build
  experimental/TONE-RECOVERY-PN2.14-README.txt            its notes / TONE-RECOVERY-SHA256SUMS.txt
  experimental/APP_LPM-10RX_PN1.23-mains-tone-update.bin  current RX build — copy THIS to the BOOTLOADER drive
  experimental/APP_LPM-10RX_PN1.23-mains-tone.bin         its raw image (hashes, emulation only)
  experimental/RX-PN1.20-1.23-SHA256SUMS.txt              RX checksums
  RX-PN1.23-README.txt                                    RX notes: update, what you hear, rollback
  FORMULA-AUDIT.md                                        every TX measurement formula, with verdicts
  sdk/                                                    TX toolkit: patches, assembler, verifier, Thai UI
  rx-sdk/                                                 RX toolkit: patches (PN 1.0 → 1.23, profiles.py), container, emulator, tests
  (older PN builds and notes are kept alongside for reference)
docs/
  RX-UPDATE-GUIDE.md                    how to update / roll back the RX and what was changed to make it work
  RX-UPDATE-PROCEDURE-2026-09-21.md     the SWD investigation that found the container requirement
  RX-SENSITIVITY-2026-09-21.md          knob / gain / rhythm measurements behind PN 1.15–1.19
  RX-AUDIT.md                           the probe firmware, function by function
  ROADMAP.md                            what to test and build next
  RX-NEXT-STEPS-2026-09-21.md           assessment of the next RX improvements and what was done about each
  RX-FIELD-CHECKLIST-PN1.23.md          30-minute field measurements to compare builds
  README-DETAILED-2026-09-21.md         the full write-up: history, TDR science, maths, audits
  experiments/                          read-only SWD tools (rx_ro.py, rx_sens_capture.py, …)
  img/                                  the pictures on this page (screens are rendered from the firmware's own layout tables and glyphs)
```

Build: `python sdk/build.py --write` (TX) and `python rx-sdk/build.py --write` (RX, latest profile; `--profile pn1.xx` for another) with FNIRSI's
images placed outside the repository (see each `build.py`). Every RX build writes both the raw image and the
`-update.bin` container; `python -m lpm10rx.container check <file>` tells which one you have.

## Licences and credits

- Tooling, patches and documentation: MIT (see [LICENSE](LICENSE)).
- FNIRSI's original firmware files are not redistributed; obtain them from FNIRSI for building and rollback.
- Fonts: Ubuntu Sans Mono (Ubuntu Font Licence), Sarabun and Droid Sans Fallback (open licences).
