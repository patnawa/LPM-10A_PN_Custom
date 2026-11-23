<div align="center">

# LPM-10A PN Custom Firmware

Unofficial firmware for the **FNIRSI LPM-10A** network cable tester (TX) and its tone probe (RX).
Built by patching the shipped binaries — no vendor source — and verified by emulation and on a real unit.

![tester](https://img.shields.io/badge/TX-PN%202.33-blue) ![receiver](https://img.shields.io/badge/RX-PN%201.30-blue) ![licence](https://img.shields.io/badge/licence-MIT-green)

<img src="docs/img/hero.png" alt="LPM-10A PN Custom Firmware: TX PN 2.14, RX PN 1.23 — Length, PoE and tone screens rendered from the firmware's own draw code" width="1000">

</div>

## New validation releases — RX PN1.31 / TX PN2.34

The September 26 bug hunt produced two RX fixes (impulse-resistant Digital strength and an atomic
sound/gain handoff) and a TX fix (queued Cable Test requests canceled by Back). These builds have
CPU-emulation regression coverage; **device testing is pending**. The owner-tested releases below
remain available for rollback. No new physical range, loudness, or selectivity claim is made.

| Device | Prerelease | Install file |
|---|---|---|
| RX probe | [rx-v1.31](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/rx-v1.31) | `APP_LPM-10RX_PN1.31-resilient-update.bin` |
| TX tester | [v2.34](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/v2.34) | `LPM-10A-TX_PN2.34-cable-session.bin` |

[Validation and device checklist](docs/RX-TX-RESILIENT-2026-09-26.md) ·
[RX notes](docs/releases/rx-v1.31.md) · [TX notes](docs/releases/v2.34.md).
The SDK default profiles are now PN1.31 and PN2.34; numbered earlier profiles stay reproducible.

## Current device-tested firmware

| Device | Version | Download | File to copy |
|---|---|---|---|
| **TX** tester | **PN 2.33** | [Release v2.33](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/v2.33) | `LPM-10A-TX_PN2.33-cable-safe.bin` |
| **RX** probe | **PN 1.30** | [Release rx-v1.30](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/rx-v1.30) | `APP_LPM-10RX_PN1.30-clean-strength-update.bin` |

The owner reports **TX PN2.33 passed device testing (2026-09-24)**: "2.33 test pass".
PN2.33 changes the Cable Test only: the wires are drawn in their **LAN cable colours** (T568B), keys
are ignored while a test runs (the button reads **Testing...**), RX unit mode decides each wire from the
median of its readings against the ladder and rejects impossible maps with "Result error!!", and Switch
mode decides exactly as PN2.27A did. Length, SPEED, FLASH, PoE, tone, QC and About are PN2.27A's.
See the [Cable Test audit](docs/TX-CABLE-TEST-AUDIT-2026-09-23.md) and the
[v2.33 release notes](docs/releases/v2.33.md). No RX change is needed.
The owner reports **RX PN1.30 passed device testing (2026-09-24)**: "1.30 test pass flicker fixed".
PN1.30 keeps PN1.29's display, **ten fixed levels 3 dB apart** like the LEDs of a Fluke IntelliTone
(no peak memory, no mute; knob fully up = **Locate**, about a fifth of its travel = **Isolate**), and
fixes three things found by running PN1.29 in the emulator: the Digital strength no longer dips when
the transmitter's 5.05 ms chip edges drift through the probe's sample readings (a probe held still
no longer flickers between two levels), a strong touch settles its gain in about 0.8 s instead of
1.5 s with the rhythm rising step by step and no gap, and a saturated reading never walks the display
down. See the [PN1.30 analysis and validation](docs/RX-CLEAN-STRENGTH-PN1.30-2026-09-24.md), the
[rx-v1.30 release notes](docs/releases/rx-v1.30.md) and, for the level display's design, the
[IntelliTone analysis](docs/RX-INTELLITONE-ANALYSIS-2026-09-23.md). TX PN2.33 is unchanged.
Each release carries its notes and a SHA-256 file. **TX and RX firmware are not interchangeable.**
FNIRSI's own files are not redistributed here.

`--profile pn2.33` reproduces the exact owner-tested TX file. PN2.27A is the previous release
(device-tested 2026-09-22; its files are in `LPM-10A/Firmware File/archive/`): flash it to roll back.
`--profile pn1.30` reproduces the exact owner-tested RX file; PN1.29 is the previous RX release
(device-tested 2026-09-23; its files are in `archive/` too).

> **สรุปภาษาไทย:** TX ใช้ PN 2.33, RX ใช้ PN 1.30 (ปุ่มสุด = Locate หามัด/ตู้, ราว 1/5 = Isolate แยกคู่; จังหวะนิ่งไม่กระตุก แตะสายแรงลงตัวใน ~0.8 วิ) ·
> TX อัปเดต: ปิดเครื่อง → กด **M + Power** ค้าง → เสียบ USB → ก๊อปปี้ไฟล์ ·
> RX อัปเดต: ปิดเครื่อง → กด **SCAN** ค้าง → เสียบ USB → ไดรฟ์ `BOOTLOADER` → ก๊อปปี้ไฟล์ **`-update.bin`** ด้วย Explorer →
> ไดรฟ์หายใน 1 วิ = เสร็จ · รายละเอียดและวิธีย้อนกลับ: [คู่มืออัปเดต RX](docs/RX-UPDATE-GUIDE.md)

## Install

### TX (tester)

1. Check the download: `certutil -hashfile LPM-10A-TX_PN2.33-cable-safe.bin SHA256` →
   `84f9fb991a5bf43f0e29d978277ebe76baa58ff21714b430c1b6cef040751e91`
2. Tester off. Hold **M + Power** until the firmware-update screen appears.
3. Plug in USB-C; a removable drive appears.
4. Copy the `.bin` onto the drive. Do not unplug while it writes.
5. Long-press Power to shut down, then power on. Settings › About shows `Software:PN2.33`.
6. If QC Test requests Init, **disconnect all cables and hold Right until Init succeeds**.
   This is required once for calibration made before PN2.25; a successful PN2.25 Init is retained.

If the drive refuses the file, rename it exactly `LPM-10A-TX_V2.0.7_260610.bin` and copy again
(some bootloaders match on the file name; the name inside the image is already the stock one).
**Back to stock:** same procedure with FNIRSI's `LPM-10A-TX_V2.0.7_260610.bin`
([fnirsi.com](https://www.fnirsi.com) → downloads). The bootloader and its update screen are never touched.

### RX (probe) — read this, the FNIRSI file will not work as shipped

1. Probe off. **Hold SCAN**, plug USB into the PC. A drive named **`BOOTLOADER`** appears.
2. Copy **`APP_LPM-10RX_PN1.30-clean-strength-update.bin`** onto it with Explorer (an ordinary copy).
3. Within about **one second the drive disappears**: the probe has programmed the file and restarted.
   Unplug USB; press the power key if it is silent. PN 1.14+ chirps high→low at power-on; entering the
   drive again (no copy) shows `PN1.30.TXT`, the installed build.

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
| Cable calibration | none | **Zero 0.0–2.0 m and NVP 50–99 %** on the Length screen, saved (factory = 0.0 m / 69 %); **REF**: dial the known length of a cable and NVP is solved from it — after the measurement or before it |
| Length stability | one TDR run (±0.3 m scatter at 14 m) | **four runs averaged per pair**; `~` marks pairs with fewer runs; the Testing line counts the runs `1/4 … 4/4` |
| Blind pairs | `0.0 m` | **`< 2 m`** (`< 200 cm`, `< 7 ft`): the PHY cannot time echoes inside ~2 m |
| Low battery | one sample < 3150 mV starts an uncancellable 30 s shutdown | three consecutive samples; cancels on recovery or charging |
| Battery gauge | 4 steps | 10-step Li-ion curve, red at ≤ 20 % |
| Auto Off | keeps counting during a SCAN tone or FLASH blink | held while a tone or blink session runs |
| Port FLASH | fixed phase counter | blink timed from the PHY link; 1.5 s on / 1 s off minimum; back-off 4 → 8 → 16 s |
| PoE screen | voltage drawn once; blank without a supply | **voltage refreshed every 0.5 s**; "Detecting…" then "No PoE"; "Standard : Yes / No" |
| Tone (SCAN) menu | Noiseless / Normal | **Digital 454 kHz** and **Analog 817 Hz**; specialized carrier switching and Analog alignment with the RX filter |
| SPEED | resolved speed and duplex only | + a **Switch** row: the speeds the port advertises (`10/100/1000`, `10/100`, … `No autoneg`) — a 100 Mbps link on a gigabit port points at the cable, on a 10/100 port at the port |
| Cable Test | one ADC sample per pin, "open" only 77 mV under the rail → random open / crossed wires on a cable plugged into nothing; any one reading inside a pin's ±5 % window names the remote pin (windows overlap from pin 5 up); pass / fail only; keys queue extra tests; Back leaves the screen; error text hidden under a button | **eleven samples per pin, the median decides**; Switch mode needs a real short; **Not connected** when nothing is at the far end; **every wire ends with its reading** (partner pin + reading in Switch mode, the RX unit's ladder value otherwise); **wires in their LAN cable colours** (T568B, white dashes on 1 / 3 / 5 / 7); RX unit mode takes the **median of a wire's readings to the nearest ladder value** and rejects impossible maps (two wires on one pin, a wire on an open shield, one level on every wire) with **"Result error!!"**; **keys ignored during the test**, the button reads **Testing...**; modes named Switch / **RX unit**; the message line is wiped before every test; Back returns to the mode choice; error line visible |
| Language | Chinese / English | **ไทย / English** on every screen; picker on first boot |
| Font | thin serif | Ubuntu Sans Mono + Sarabun (Thai), rendered from the firmware's own layout tables |
| Reliability | heap leak on settings save, timer-path logging, FP crash frame | fixed; watchdog on the service task; fault records kept across warm reset |
| QC Test | raw pulse counts depend on the actual task delay | **Classic screen and continuous automatic testing**; counts normalized to the actual measurement duration; three passing observations before green, immediate fault classification; clean Init prompt |
| Identity | `Software:V2.0.7`, fnirsi.cn | `Software:PN2.33`, this repository's URL, and `BATT / NVP / ZERO` on the About screen; bootloader-facing image name unchanged |

### TX (tester) — in detail

<details>
<summary><b>Length: one decimal, m / cm / ft, unit remembered</b></summary>

<img src="docs/img/length_screen.png" alt="Length screen: stock (whole metres) vs PN Custom (one decimal, Zero and NVP calibration)" width="1000">

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

**REF** (PN 2.18, PN 2.22 / 2.23) does the long-cable step for you: holding OK cycles NVP → ZERO → **REF**.
With a result on screen REF starts at the measured length, UP / DOWN dial it to the cable's true length
(0.1 m, 10 cm or 0.1 ft per step) and every step solves `NVP = 69 × REF / (raw − 10·Zero)` from the mean of
the timed pairs (rounded, 50–99 %), shows it in grey on the right and redraws the four readings. Without a
result REF starts at 10.0 m: dial it to the cable's true length, press OK to measure (far end open) and the
result is fitted to it once — the measurement after that is an ordinary one, a REF target left behind never
re-fits NVP by itself. Zero stays the short-cable step; NVP is saved on leaving the screen as before.
</details>

<details>
<summary><b>Four-run average and the <code>~</code> mark</b></summary>

The PHY resolves the echo to about ±1.5 ns per run, which at NVP 0.68 is ±0.3 m — the run-to-run scatter
seen on the bench (±0.2 m at 3 m, ±0.3 m at 14 m). Stock showed one run as is (with a single retry when
the four pairs disagreed). PN runs the diagnostic **four times** and averages each pair over the runs in
which it returned a non-zero value (`mean_i = floor(Σ runs_i / n_i)`); the 20 s timeout restarts per
run, so a test takes four times longer. A pair that yielded only 1–3 runs is marked `~`. This halves the
scatter and is why the calibration above settled from 0.5 m to 0.4 m. Since PN 2.15 the Testing line counts
the runs at its right end, `1/4 … 4/4`, so the wait is understood.
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
<summary><b>Tone menu: Digital 454 kHz and Analog 817 Hz</b></summary>

The SCAN screen drives the cable with a ~454 kHz carrier from TIM1. TIM2 services modulation every
101 microseconds. **Digital** keys the carrier with the 16-slot code `0xB6B6` (period 8 chips,
5.05 ms per chip) that the probe's Digital mode decodes. **Analog** uses a local phase accumulator
at nominal 816.832 Hz, close to the RX Analog filter's target bin, without changing the shared timer.
Stock labelled them "Noiseless" and "Normal"; PN labels the carrier and modulation frequencies.
PN2.27A specializes carrier GPIO switching and inherits the fixes for one lost tick at the
digital wrap, the debug logging in the timer path, the stale carrier state after Pause and a RIGHT-key
carrier-cache defect, and removes two experimental modes (Sync32, Pulse test) that the probe does not
use. Pair TX Digital with RX Digital and TX Analog with RX Analog.
</details>

<details>
<summary><b>Cable Test: "Not connected" instead of a guess; the reading on every wire; Switch / RX unit</b></summary>

The wire map drives one tester pin and reads the other eight through the ADC. *Stock* took **one sample**
per pin, 2 ms after switching the mux, and called a pin open only when all eight readings were above
4000 of 4095 — 77 mV under the rail. A cable plugged into nothing floats on the tester's pull-up and picks
up mains hum, so single samples crossed that line at random: Switch mode then called the pin connected
(its rule was "any other pin at or below 4000"), far-end mode went on to guess which remote pin it had
reached — a different pattern of open / crossed wires on every Test Retry, and no "nothing connected"
state at all.

*PN* (2.19) reads every sensed pin **eleven times, 1 ms apart** — a half-cycle of mains — and uses the
median where stock used the sample (the highest of the eleven for far-end mode's open test: a floating
wire touches the rail within a half-cycle, a wire on the RX unit's resistor ladder does not). Switch mode
counts a pin connected only through a real short (≤ 1240, the far-end routine's own short value), since a
switch port joins the two wires of a pair through its transformer winding. When all eight signal pins
are open the screen says **Not connected** / ไม่พบปลายสาย; G (the shield) shows open on an unshielded cable
or a switch and is not counted. The second mode is named for what you plug in, **RX unit** / เครื่องรับ. A
test takes about 0.9 s instead of 0.15 s; the thresholds and the remote ladder table are stock's.
(PN 2.20: the message line under the wires is wiped before every test — a Test Retry from the result
screen never redrew it, so a message could outlive its result.)

PN 2.21 puts the reading that decided each wire at its right end, in the wire's colour (red for an open
wire, yellow for a short). In Switch mode it is the partner pin and the reading — `2   60` — so a good
cable reads `2 1 6 5 4 3 8 7` down the rows and a single swapped wire shows the wrong letter where stock
only draws green; `- 4037` means nothing reached. In RX unit mode it is the ladder value alone, which *is*
the remote pin (1655 pin 1 … 3679 pin 8, 3900 shield), so a crossover cable shows its crossing lines and the
swapped values. A floating wire well under 4095 (say 3800) is leakage or moisture; a switch partner well
above 60 (say 300) a poor contact. Nothing about the decision changes.

Stock's Back key also left the Cable Test screen from every step, and the red "Result error!!" line was
painted underneath the Test Retry button. PN's Back returns to the Switch / RX unit choice from the armed
and result screens (a `tbb` byte and two spare `nop`s at the key handler), and the button moved 9 px down
so the message line sits above it.

PN 2.33 draws the wires in their **LAN cable colours** (T568B: 1 white-orange, 2 orange, 3 white-green,
4 blue, 5 white-blue, 6 green, 7 white-brown, 8 brown, G silver). The white-striped wires 1, 3, 5 and 7
carry white dashes along the straight wires and, in RX unit mode, along the crossed diagonals; the
reading at the right end is in the wire's colour. Fault colours win and get no dashes: red for an open
wire (with the X), yellow for a short in RX unit mode, and an unknown row is left blank with "Result
error!!". The colours live in the u16 colour table at `0x0801E2CC`, which only the Cable Test reads.

Keys are ignored while a test runs (about 0.86 s: eleven samples × 72 pin pairs). Stock queued every OK
pressed during a test as another test, and a test queued before leaving the screen could paint the Cable
Test layout over Home or SPEED. PN 2.33 gates the OK post on stock's own "routine running" byte, runs
the Cable Test's GUI messages only while the Cable Test is the active screen, leaves no stray "Test
Retry" button when Back is pressed mid-test (the next screen says "Test Start"), hands each routine's
own mode to the readings drawer, and shows **Testing...** / กำลังทดสอบ on the button while measuring.

RX unit mode decides differently. Stock accepted a remote pin when *any one* of the eight readings fell
inside that pin's ±5 % window; the windows overlap from pin 5 up, so a 6↔7 or 8↔G crossing at +1 % gain
could pass as straight. PN 2.33 takes the **median of the wire's non-floating readings** (highest sample
≤ 4000 and median > 1240), sends the wire to the **nearest ladder value** (1655 1975 2319 2607 2935 3183
3391 3679 3900) with one gain estimate shared by all rows (median of value / nearest ladder value,
clamped 0.93–1.07), then checks that the map is possible: two wires landing on one remote pin, a wire
landing on an open shield, or one level on every wire (the leakage of an unplugged cable) make the row
unknown — blank, "Result error!!", red LED. The short rule (≤ 1240) and PN 2.19's open rule are
unchanged. In the emulator straight and crossover cables map correctly from −5 % to +6 % gain and a
reversed 1-2 pair with a floating shield under 50 Hz hum maps correctly at every phase (PN2.27A misread
some); the device confirmation is the owner's "2.33 test pass".

Switch mode decides and draws exactly as PN2.27A, in the new colours. PN 2.28–2.30 tried a pair-partner
check there (a wire whose partner is not its pair-mate red, a short between pairs yellow, the shield
grey). It assumed the switch port's centre-tap paths between pairs read well above the pair winding; on
the owner's switch they read within a few counts of it, so every wire looked joined to several pins
("every line cable test 1-8 show yellow"). The check is withdrawn, so **Switch mode still cannot see a
crossover, a reversed pair, a wire crimped into the wrong pair or a short between pairs** — the switch
joins each pair's far ends. `experimental/LPM-10A-TX_PN2.30D-diag.bin` is a diagnostic build, not a
release: in Switch mode it prints each wire's two lowest readings and the pins they reach (`2  60 5  63`);
a photo of a good cable in the owner's switch on that build is what bringing the check back needs.
</details>

<details>
<summary><b>SPEED: what the port offers, next to what the link got</b></summary>

Stock negotiates a link and prints the resolved speed and duplex from the PHY's status register — what
you got, not what the port could do. PN (2.17) adds a **Switch** row from the two IEEE 802.3 registers
every PHY has and stock never read: register 5 (the partner's advertised 10 / 100 abilities) and
register 10 (1000BASE-T status). `10/100/1000`, `10/100`, `100/1000`, … or `No autoneg` for a fixed-speed
port. A 100 Mbps link under a `10/100/1000` row means the cable lost pairs 4-5 / 7-8; under `10/100` it is
the port. The row is empty after "Error!!". Display only; nothing is written to the PHY.
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

About reports `Software:PN2.33` and this repository's URL instead of `V2.0.7` / fnirsi.cn, and since PN 2.16 one
line under Factory Reset — `BATT 3874mV  NVP 68%  ZERO 0.4m` — the pack voltage and the Length calibration as
stored. The
container's internal image name stays FNIRSI's, because the bootloader may match on it. Since PN 2.3
the file is one 4 KB flash page longer than stock (393 216 bytes) because the code cave ran out; the
container header carries the payload length and the bootloader accepted the longer file (and, in the
`cable-diag` experiment, a two-page-longer one) on the tested
unit. The current PN2.33 update is **401,408 bytes**, accepted on the owner's tester.
Formulas, addresses and verdicts for every calculation, TX and RX: [`FORMULA-AUDIT.md`](LPM-10A/Firmware%20File/FORMULA-AUDIT.md).
</details>

<p>
<img src="docs/img/scan-pn214-en.png" alt="Historical PN2.14 tone menu: Digital 454 kHz and Analog 825 Hz" width="180">
<img src="docs/img/scan-pn214-th.png" alt="Historical PN2.14 tone menu in Thai" width="180">
<img src="docs/img/about_screen.png" alt="About screen: stock vs PN Custom" width="620">
</p>

<img src="docs/img/battery_gauge.png" alt="Battery percentage vs pack voltage: stock 4 steps vs PN 10-step Li-ion curve" width="800">

<img src="docs/img/thai/thai_overview.png" alt="Every screen of the Thai interface, rendered from the firmware's own draw code" width="1000">

### RX (probe) — summary

| | Stock (V3.0.0 / 3.0.1) | PN 1.30 |
|---|---|---|
| Sound per mode | one 2.5 kHz beep in every mode | **Digital 2.5 kHz, Analog 1.25 kHz, mains 5 kHz**, about **9.5 dB louder**; key beeps chirp toward the mode (Digital low→high, Analog high→low) |
| Strength feedback | 50 ms beep / 50 ms gap whenever a signal is detected | 30 ms pulses (Analog 12 ms) whose rate shows the strength against the knob's reference as **ten absolute levels 3 dB apart**: quiet interval 146 ms (level 0) → 20 ms (level 9); the same strength gives the same level (0.5 dB hysteresis at each level boundary); since PN 1.30 the Digital estimate ignores the samples that hold a chip edge, so a probe held still keeps one level (PN 1.29 read 23 % of its windows 1.6–6 dB low and flickered near a level boundary) |
| Sensitivity knob | sets the gain; the middle of its travel fell to the lowest gain (firmware bug); below the middle only strong signals were heard | **full gain at every position**; the knob sets the reference (0 dB on the top sixteenth, about 2 dB per sixteenth lower, −30 dB at the bottom): **fully up = Locate**, **about a fifth of the travel = Isolate** — lower knob, slower rhythm; the reference never mutes (Analog, as in stock, is off below about 14 % of the knob) |
| Crowded bundle or cabinet | every coupled pair sounds | at **Isolate** the toned pair plays the fastest level and its neighbours at least one level slower (touch each pair about 2 s); at Locate strong pairs all play the top level, by design; no peak memory and no mute: after about 2 s a pair's level follows its own strength, except within 0.5 dB of a level boundary |
| Moving/adjusting gain | — | automatic range changes use a fresh completed acquisition; the gain steps **down at every displayed window** (about 0.28 s in Digital, 21 ms in Analog; PN 1.29: every 0.5 s) and up every 1 s; confirmed Digital feedback bridges fresh acquisition (the owner confirmed no signal drops in Digital or Analog on PN 1.24; no audio gap over 150 ms in the emulator's PN 1.29 stream test) |
| Delayed measurements | no completion-age guard | expired Digital/Analog results cannot renew feedback; quiet-input Analog analysis uses about **97% fewer modeled instructions** than PN1.23G |
| Signal loss | audio kept going ~1 s after the TX stopped | stops within ~¼ s; a single missed reading no longer cuts the rhythm |
| Very strong signal | — | the automatic gain steps down when the front end saturates (~2400 counts p-p) to restore distance resolution, 7 → 2 → 1 → 0 within about 0.8 s (PN 1.29: 1.5 s), each gain's saturated reading heard once as a lower bound that never walks the display down; a clipped window counts as the saturation score at the driven gain at every knob position; touching a lone cable plays the fastest level from about three quarters of the knob up |
| Mains (NCV) | the knob's gain step | the knob's gain step, **full from a quarter of the knob up**, set again every 500 ms (also right after a tracing mode) |
| Update rate | Digital every 80 ms | **Digital every 40 ms** (Analog every 21 ms as before) |
| Detection | exact 16-bit code match | PN 1.12 detector: full-window code search with bounded bit errors, upper-rail handling, guarded sample ownership |
| Installed build | — | the `BOOTLOADER` drive's status file names it: `PN1.30.TXT` |
| Low battery | uncancellable shutdown at one sample | recoverable |

### RX (probe) — in detail

The probe is a Nations N32L406 (Cortex-M4F, 64 MHz, no RTOS). TIM1 ticks every 1 ms (keys, battery,
countdowns, 5-minute auto-off); TIM5 runs at 40 kHz (ADC sampling and the speaker PWM). The front end's
gain is selected by three GPIO lines, set every 500 ms: stock takes it from the sensitivity knob; PN's
automatic gain and knob law are described below.

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
  Digital mode uses. PN1.24 checks bin 17 first and rejects immediately when it
  cannot pass; it also omits the canceled bin 1. Fresh-input decisions and
  strength scores match PN1.23G in the comparison sweep.
- **Mains (NCV)**: 64 samples every 1.55 ms (99 ms) from ADC channel 7 (the PD15 key selects the mode),
  DFT bins 5 and 6 = 50.4 and 60.5 Hz; stock's analysis and three-tier beep length (50 / 100 / 200 ms)
  are kept. The owner found NCV sensitivity follows the knob, so mains mode drives the knob's gain step,
  full from a quarter of the knob up, and sets it again every 500 ms, also right after a tracing mode
  had lowered it (PN 1.25, 1.26).

Sample ownership between the main loop and the timer interrupt is guarded (PN 1.6): a pending mode
change or a gate transition invalidates the window instead of racing the ADC.
PN1.24 also guards gain transitions and completed-window age before analysis
and publication, with full reacquisition after expiry.
</details>

<details>
<summary><b>One pitch per mode, the chirp, louder beeps (PN 1.14, 1.23, 1.25)</b></summary>

The speaker is TIM5 channel 4 PWM at 40 kHz; a beep is made by flipping the duty between 1 100 and 500
every N interrupts (stock 900 and 700: a third of the swing, about 9.5 dB quieter; silence is 800).
Stock flipped every 8th (2.5 kHz) in every mode. PN's TIM5 dispatch picks N by mode:
Digital 8 (2.5 kHz), **Analog 16 (1.25 kHz, one octave lower)**, **mains 4 (5 kHz)**. A key press starts a
100 ms confirmation beep; during its first 50 ms the helper uses the *other* mode's pitch, so entering
Digital sounds low→high and entering Analog high→low (the power-on beep is high→low). Tracing pulses are
30 ms (Digital) and 12 ms (Analog) and never reach the chirp half.
</details>

<details>
<summary><b>The level display and the knob's reference (PN 1.15, 1.22, 1.27, 1.29)</b></summary>

Instead of stock's fixed 50 ms on / 50 ms off, PN plays **30 ms pulses** (12 ms in Analog) separated by
a quiet interval that reports the strength. The strength score is ADC contrast, which scales with the
front-end gain, so on the first hardware run turning the knob up simply sped the rhythm. Live captures
gave the gain step per knob code (peak-to-peak at one position: 95 / 230 / 780 / 90 / 1920 / 1940 /
2040 / 2400 for codes 0–7), and PN 1.15 multiplies the score by the measured step (×20 / 9.2 / 2.6 /
2.6 / 1.1 / 1.1 / 1.1 / 1.0), so the score is the signal at the probe tip whatever gain is driven (since
PN 1.22 the gain actually driven). The front end's measured saturation is about 40 000 on that scale.

**PN 1.29** multiplies that score by the knob's reference K (PN 1.27's law: 1 on the top sixteenth of the
knob, about −2 dB per sixteenth below it, −30 dB at the bottom, `8 × 32^(i/15) / 256` interpolated; the
firmware stores K × 256, 8 … 256, and computes `(strength × 256K) >> 8`) and shows the result as one
of **ten absolute levels 3 dB apart**: level k (1–9) when strength × K ≥ 2 524, 3 565, 5 036, 7 113,
10 048, 14 193, 20 047, 28 318, 40 000, level 0 below 2 524. Quiet interval per level 0–9: 146, 123,
103, 86, 71, 57, 46, 36, 27, **20 ms**; each Digital pulse period is 15 % longer than the next level's.
A clipped window (ADC rail) counts as the saturation score 40 000 at the driven gain, through the same
display, at every knob position.

On a fresh start (RECENT countdown ≤ 500, no audio playing) the level is taken directly. While audio
continues, a stronger window shows at once and a weaker one moves the shown strength an eighth of the
way per window (a real 3 dB drop in about 0.3 s in Digital, whose estimate has single windows 3–6 dB
low; a 10 dB drop in about 1.1 s), and the level changes only 0.5 dB past its boundary (value ±
value/16). The PN1.25–1.28 peak memory, mute and gain ceiling are gone: from a fresh start the same
strength always gives the same level; while audio continues, a strength within 0.5 dB of a boundary
keeps the level shown before. Emulator, Digital, lone cable, quiet interval at knob 10 / 25 / 40 / 50 /
75 / 100 %: weak 146 at every position; moderate 146 / 146 / 146 / 146 / 86 / 57; near 146 / 123 / 86 /
71 / 36 / 20; touching 86 / 71 / 46 / 36 / 20 / 20 ms — audible at every knob position (Analog, as in
stock, listens only from about 14 % of the knob up) and never slower as the knob rises.
</details>

<details>
<summary><b>Knob gain dead zone, automatic gain range (PN 1.17, 1.22, 1.24, 1.26, 1.29)</b></summary>

`gain_select_3bit` writes the knob level's bits to PB12..PB14 and special-cases level 0 to the pattern
`011` — which is also what level 3 produces, so the middle of the knob (43–56 %) dropped to the lowest
gain in stock. PN 1.17 maps level 3 to level 2's pattern, making the knob monotonic (low / 230 / 780 /
780 / high).

On the high steps the front end saturates at ~2000–2600 counts p-p well before the ADC rail, so on the
cable every nearby conductor sounded the same and Analog could lose its DFT margin. PN 1.22 measures the
sample buffer's peak-to-peak at every 500 ms AGC tick: **≥ 1900 steps the driven gain down** one
effective step (high → 780 → 230 → 90), **< 450 steps back up** toward its ceiling, and a raised
ceiling is taken at once. In PN 1.29 the ceiling in Digital and Analog is the **full gain at every knob
position** (for tracing, the knob sets the display's reference and the stock mode gates); NCV drives
the knob's gain step, full from a quarter of the knob up (raw ≥ 1024), set every 500 ms (PN 1.26).
PN1.24 checks that a complete recent
window belongs to the current gain and skips one callback after an automatic change. PN 1.29 removes
that hold after a step **down**: the next 500 ms callback may decide again, and its freshness guard
still requires a complete window acquired at the new gain; a step up keeps the one-callback hold. A
saturated front end therefore steps 7 → 2 → 1 → 0 at 0.5 / 1.0 / 1.5 s (PN1.24: 0.5 / 1.5 / 2.5 s), with
no audio gap over 150 ms in the emulator's stream test. A held callback skips the sample scan. PN 1.30
lets the TIM1 1 ms tick call the same guarded routine once per completed window, after the display has
shown that window, so the steps come about 0.24 s apart in Digital and 21 ms apart in Analog (a strong
touch settles in about 0.8 s / 0.07 s); a step up still holds one 500 ms tick, and the 500 ms call stays. The
strength normaliser reads the gain actually driven, so the level stays meaningful after a step; the mode
gates (Digital raw ≥ 2, Analog code ≥ 1) still follow the knob. Gain state: four bytes at `0x20000200`;
completion/analysis timestamps and validity: twelve bytes at `0x20000204`; the level display's shown
strength (u32) and level (u8): `0x20000210` and `0x20000214`, zero-initialised and unused by PN1.24; PN 1.30's
last-judged and last-displayed window stamps: `0x20000218` and `0x2000021C`.
</details>

<details>
<summary><b>Crowded bundles and cabinets: Locate and Isolate (PN 1.29)</b></summary>

In a telephone PBX cabinet the 454 kHz tone couples into every neighbouring pair, so the probe can only
rank pairs by strength. PN 1.29 uses the knob like the Locate / Isolate switch of a Fluke IntelliTone
probe:

- **Locate — knob fully up.** Find the bundle or cabinet: weak signals are graded and the rhythm speeds
  up level by level as the probe gets closer. At the cabinet every strong pair plays the top level; that
  is by design, like IntelliTone's 7–8 LEDs on the toned cable.
- **Isolate — about a fifth of the travel (roughly 19–25 %).** Touch each pair for about 2 s: the toned
  pair plays the fastest level and its neighbours at least one level slower. If every pair plays the
  slowest level, turn the knob up a little; if the suspect pair and its neighbours all play the fastest,
  turn it down a little. At the first touch of a bundle wait 1–2 s for the gain to settle.

There is no peak memory and no mute. While audio continues, the shown strength falls an eighth of the
way per window (in Digital a 3 dB drop takes about 0.3 s, a 10 dB drop about 1.1 s), the automatic
gain carries over from the pair before, and a strength within 0.5 dB of a level boundary can show
either level depending on the one before. So give each pair about 2 s; after that its level follows
its own strength, except at a level boundary. Analog separates pairs more steadily than Digital in
the emulator (Analog's strength is stable to 0.06 dB, Digital has single windows 3–6 dB low), so TX
Analog with RX Analog is the better choice for pairs.

Fluke's IntelliTone Pro 200 probe has no sensitivity knob: a rotary switch selects Locate or Isolate and
8 LEDs show absolute strength, typically 7–8 on the toned cable, with Isolate giving "a couple of LED
levels of difference" to its neighbours. Fluke also writes that its digital signal is "subject to
significant bleed-over between pairs in a cable", especially on Cat 3, and recommends analog mode for
pairs. In the emulator's cabinet scorecard (`rx-sdk/cabinet_scorecard.py`, real firmware: the toned pair
and neighbours 3, 6 and 10 dB weaker, three contact strengths, eight knob positions; identified when
every neighbour visit's pulse period is at least 12 % longer than every toned-pair visit's) PN 1.29
identifies the toned pair in 14 of 24 cases in Digital and in 13 of the 18 Analog cases where the
probe sounds (Digital of 24 / audible Analog of 18: PN 1.24 0 / 0, PN 1.27 4 / 3, PN 1.28 4 / 2).
Analog is silent at the 13 % and 6 % positions, below its stock gate at about 14 % of the knob; the
script counts those six silent cases as passes, which gives its raw Analog totals of 6, 9, 8 and 19 of
24 for PN 1.24, 1.27, 1.28 and 1.29. At 19 % of the knob PN 1.29 identifies all three contact
strengths in both modes, in Analog anywhere from 19 % to 38 %. PN 1.30 gives the same verdict on every
Digital row and on all but one boundary row in Analog (14 / 18 of 24), and the spread of one pair's tone
fraction across its visits falls from 0.043 to 0.007 in Digital and 0.015 to 0.001 in Analog. The
manual's comparison, the owner's reports and the scorecard:
[docs/RX-INTELLITONE-ANALYSIS-2026-09-23.md](docs/RX-INTELLITONE-ANALYSIS-2026-09-23.md); PN 1.30's
findings and validation: [docs/RX-CLEAN-STRENGTH-PN1.30-2026-09-24.md](docs/RX-CLEAN-STRENGTH-PN1.30-2026-09-24.md).
</details>

<details>
<summary><b>Release, hold and smoothing (PN 1.7, 1.16, 1.17, 1.29)</b></summary>

Stock kept beeping for 800 ms after the last match — the "one-second tail" after pausing the TX. PN 1.7
released on the first rejected window, which the owner heard as choppiness at marginal signals. PN 1.16
keeps the last interval on a rejected window and instead clamps the freshness countdown (audio needs
> 500): to 660 in Digital (one missed 80 ms update bridged; three at 40 ms) and 560 in Analog, so a signal
that is really gone still stops within ~¼ s. PN 1.17 moved the published interval **half way** toward
each new target; PN 1.29 replaces that step with the level display's filter and 0.5 dB hysteresis
(above). PN 1.30 keeps them and moves half way per window when an unsaturated window is 2.5 dB or more
below the shown strength, so a 6 dB drop shows in about 0.6 s. The sensitivity knob's gate, RECENT countdown and the 800 ms power keep-alive are stock.
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
<img src="docs/img/rx-measurements.png" alt="RX: measured front-end gain per knob code (stock dropped code 3 to the lowest gain) and the PN 1.15–1.24 rhythm curve (110 → 20 ms, replaced by PN 1.29's ten levels)" width="960">
<img src="docs/img/rx-board.jpg" alt="The probe's board: Nations N32L406 MCU, 4-pin SWD header on the left, sensitivity potentiometer" width="200">
</p>

The earlier gain and rhythm measurements were captured live over SWD while
sweeping the knob and moving the probe (the SWD header is beside the MCU):
[docs/RX-SENSITIVITY-2026-09-21.md](docs/RX-SENSITIVITY-2026-09-21.md). The rhythm curve in the picture
is PN 1.15–1.24's (110 → 20 ms, knob-independent); PN 1.29 plays ten fixed levels, 146 → 20 ms, against
the knob's reference (above). The probe firmware, function by function:
[docs/RX-AUDIT.md](docs/RX-AUDIT.md). PN1.29's and PN1.30's numerical figures (knob
response, level display, steady-signal probe, cabinet scorecard) are emulator results on the actual ARM
code with modelled ADC, coupling and interrupts; the device confirmations are the owner's reports ("1.29
test pass work perfect", 2026-09-23; "1.30 test pass flicker fixed", 2026-09-24), which did not measure
pickup distance, loudness or selectivity. Pair TX
**Digital** with RX Digital and TX **Analog 817 Hz** with RX Analog. Only one hardware unit has been
tested; range and cable selectivity are not quantified against another probe.

## Known limitations

- **Cables of about 2 m and under cannot be measured** (the PHY's TDR blind zone); the Cable Test (wiremap)
  screen still finds the broken pair. Blind pairs read `< 2 m`.
- The current TX update file is 401,408 bytes; the owner confirmed this exact image works on the tester.
- A Cable Test takes about a second (eleven samples per pin); keys are ignored while it runs. G (the shield)
  reads open on an unshielded cable in both modes, and on a switch — normal, not counted as a fault.
- **Switch mode cannot tell a crossover, a reversed pair or a wire crimped into the wrong pair** (the switch
  joins each pair's far ends), nor a short between pairs behind a switch port with centre taps; plug the RX
  unit in for those. A true split pair is invisible in both modes (a DC test). The PN2.28–2.30 attempt to
  read pair partners through the switch was withdrawn (see *Cable Test* above).
- The wire-map thresholds are stock's, confirmed on one unit; the `cable-diag` build in `experimental/` prints
  the deciding numbers and the PN2.30D build prints each wire's two lowest Switch-mode readings if another
  unit or switch disagrees.
- Links that need more than 16 s to negotiate can still fail Port FLASH; the PoE "unstable supply" check
  can never trigger (vendor bug, left as is).
- RX Digital evaluates every 40 ms and needs a full 240 ms frame to lock after a mode change; Analog reacts
  faster still. Digital is the mode for noisy places; to compare pairs at Isolate, Analog is steadier in
  the emulator (see *Crowded bundles and cabinets: Locate and Isolate*). A matched-filter Digital
  detector was modelled on 7,992 live windows and rejected: the 8-chip code and 50 Hz hum make it no
  more sensitive
  ([assessment](docs/RX-NEXT-STEPS-2026-09-21.md)).
- The RX front-end gain multipliers were measured on one unit; other units may need
  `MULT_X10` in `rx-sdk/gain_norm.py` re-measured.
- RX Locate (knob fully up) does not separate strong pairs, by design: at a bundle or cabinet every pair
  strong enough plays the top level. Turn the knob down to about a fifth (Isolate) to compare pairs.
  Signals more than about 24 dB below the fastest level's threshold all play the slowest level (146 ms)
  at that knob position.
- A neighbour within about 2 dB of the toned pair cannot be separated by strength at any knob position:
  the 454 kHz carrier couples between pairs and through PBX line circuits; a neighbour exactly one level
  (3 dB) weaker can play the same level when it sits on a level boundary (0.5 dB hysteresis). A
  SmartTone-style short detector (IntelliTone changes cadence when the pair is shorted at the far end)
  would need the TX tone path traced on the board.
- At the first touch of a bundle the RX needs 1–2 s for the automatic gain to settle before pairs are
  compared.

## Repository layout

```
LPM-10A/Firmware File/
  LPM-10A-TX_PN2.33-cable-safe.bin           current TX build — copy to the tester's update drive
  APP_LPM-10RX_PN1.30-clean-strength-update.bin  current RX build — copy to the probe's BOOTLOADER drive
  TX-PN2.33-README.txt, RX-PN1.30-README.txt  notes for each: what it does, how to update, how to roll back
  SHA256SUMS.txt                             checksums of the two files above
  README.md                                  what is in this folder
  FORMULA-AUDIT.md                           every measurement formula with verdicts: TX §1-6, receiver PN formulas §7
  sdk/                                       TX toolkit: patch chain PN 2.9 → 2.33 (profiles.py), assembler, verifier, Thai UI, tests
  rx-sdk/                                    RX toolkit: patch chain PN 1.0 → 1.30 (profiles.py), container, emulator, tests
  experimental/                              build outputs of every PN version (the test suites compare against them),
                                             the PN2.28–2.30 Cable Test stages and the PN2.30D diagnostic build
  archive/                                   earlier release copies and their notes (TX PN2.27A, RX PN1.29 and before; history only)
docs/
  RX-UPDATE-GUIDE.md                    how to update / roll back the RX and what was changed to make it work
  RX-UPDATE-PROCEDURE-2026-09-21.md     the SWD investigation that found the container requirement
  RX-SENSITIVITY-2026-09-21.md          knob / gain / rhythm measurements behind PN 1.15–1.23
  RX-NEXT-STEPS-2026-09-21.md           assessment of the next RX improvements and what was done about each
  TX-NEXT-STEPS-2026-09-21.md           the same for the TX: what is left, what was done, where there is no room
  RX-FIELD-CHECKLIST-PN1.23.md          30-minute field measurements to compare builds
  RX-KNOB-PN1.27-2026-09-23.md          the PBX-cabinet report and PN1.27's knob reference (PN1.25 and PN1.26 steps linked; superseded)
  RX-INTELLITONE-ANALYSIS-2026-09-23.md the RX against Fluke IntelliTone, the cabinet scorecard and PN1.29 (the level display's design)
  RX-CLEAN-STRENGTH-PN1.30-2026-09-24.md the PN1.29 defects found by emulation (chip-edge dips, gain settle, walk-down) and PN1.30 (current RX)
  TX-CABLE-TEST-AUDIT-2026-09-23.md     the Cable Test wire-map audit (29 findings) behind PN2.28–2.33 (current TX)
  releases/v2.33.md, releases/rx-v1.30.md  TX PN2.33 and RX PN1.30 release notes (the other releases' notes sit beside them)
  RX-AUDIT.md                           the probe firmware, function by function
  ROADMAP.md                            what to test and build next
  README-DETAILED-2026-09-21.md         the full write-up: history, TDR science, maths, audits
  experiments/                          read-only SWD tools (rx_ro.py, rx_sens_capture.py, …)
  img/                                  the pictures on this page (screens are rendered from the firmware's own layout tables and glyphs)
```

Build: `python sdk/build.py --write` (TX) and `python rx-sdk/build.py --write` (RX) emit the latest profile of each
(`--profile pn2.xx` / `--profile pn1.xx` for another; `python -m unittest test_profiles` in either toolkit rebuilds every
version and compares it with its published digest); outputs land in `experimental/`, and `publish_current.py` copies the
release pair to the folder root with FNIRSI's images placed outside the repository (see each `build.py`). Every RX build writes both the raw image and the
`-update.bin` container; `python -m lpm10rx.container check <file>` tells which one you have.

The [2026-09-22 deep audit](docs/DEEP-AUDIT-2026-09-22.md) documents new RX gain/sample
and TX capability-display findings, opt-in corrections, and build/publication fixes.
From `rx-sdk`, `python verify_release.py` checks the complete current RX update against
an exact profile rebuild. PN1.29 builds on PN1.24's gain ownership and Digital continuity, and PN1.30 on the exact PN1.29 image
corrections, faster gain recovery, sample-age guards and Analog optimization.

The [PN1.23G follow-up](docs/RX-DIGITAL-GAIN-PN1.23G-2026-09-22.md) addresses
Digital audio dropouts reported on PN1.23F during probe motion or knob changes.
The owner confirmed the Digital dropout is fixed on PN1.23G (2026-09-22).
Its update file, device feedback and measured emulator results are in the report.
The [PN1.24 release](docs/RX-GAIN-PRECISION-PN1.24-2026-09-22.md) retains that fix;
the owner confirms both Digital and Analog pass without signal dropouts.
The [PN1.27 release](docs/RX-KNOB-PN1.27-2026-09-23.md) keeps both and answers the
PBX-cabinet field report of 2026-09-23 (two device-tested candidates, PN1.25 and
PN1.26, led to it); the owner reported the device test passed the same day.
[PN1.28](docs/RX-PAIR-RANK-PN1.28-2026-09-23.md) (pair ranking against a remembered peak) was
device-tested worse ("detects, but not accurately") and superseded. The
[PN1.29 release](docs/RX-INTELLITONE-ANALYSIS-2026-09-23.md) (2026-09-23, built from PN1.24) and the [PN1.30 release](docs/RX-CLEAN-STRENGTH-PN1.30-2026-09-24.md) (2026-09-24, built from PN1.29)
replaces the peak and mute window with ten absolute levels and Locate / Isolate knob use; the owner
reported "1.29 test pass work perfect" the same day. PN1.27 and PN1.28 are superseded; PN1.27's
release files are in `LPM-10A/Firmware File/archive/`, PN1.28's in `experimental/`.

The [PN2.23Q QC experiment](docs/TX-QC-FLEX-PN2.23Q-2026-09-22.md) adds a
20-second TX crimp-test session, retained per-pin fault history and stable
five-sample calibration. Build with `python qc_continuity.py --write` from
`sdk`; the update is in `experimental/`. CPU/GUI-tested; device validation is
pending. This opt-in candidate does not change the published release pair.

Owner feedback on Q led to [PN2.23R](docs/TX-QC-CLASSIC-PN2.23R-2026-09-22.md):
the original QC graphic, continuous automatic testing, and changed-pin-only
drawing to remove repeated screen blanking. Build with `python qc_classic.py --write`
from `sdk`. The owner reported R passed, then reported random QC lights with
the connector unplugged.

[PN2.24](docs/TX-LENGTH-QC-PN2.24-2026-09-22.md) follows up with three-observation
QC pass confirmation and immediate fault indication. It also fixes Length
work surviving rapid reentry, stale queued screen text and loss of pending
REF after an unusable result, and reduces repeated Testing-box redraws.
Build with `python length_integrity.py --write` from `sdk`; the combined TX
update is `experimental/LPM-10A-TX_PN2.24-length-qc.bin`. The owner subsequently
reported changing QC indicators with a complete stationary cable on PN2.24.

[PN2.25](docs/TX-QC-TIMING-PN2.25-2026-09-22.md) corrects the shared QC sampler:
counts are normalized using actual elapsed time, since a ten-tick RTOS wait
was not a fixed measurement interval. It retains the classic automatic screen
and Length fixes. Its archived builder is `qc_timing.py`. The owner then
reported a garbled screen immediately on QC entry: queued artwork was painting
over the Init prompt. PN2.25 is superseded by PN2.26 below.

[PN2.26](docs/TX-QC-DISPLAY-PN2.26-2026-09-22.md) fixes that reproduced display
ordering defect while retaining the timing and Length fixes. The owner
confirmed every function passed on the device on 2026-09-22. Reproduce this
historical release with `python build.py --profile pn2.26 --write` from `sdk`;
its unchanged file remains in `experimental/` and
[release v2.26](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/v2.26).
If QC requests Init, disconnect all cables and hold Right.

[PN2.27A](docs/TX-TONE-PRECISION-PN2.27-2026-09-22.md) adds faster carrier GPIO
switching and Analog alignment while retaining Digital timing. The owner
reported a test pass with RX PN1.24. Its pre-release TX suite passed 516 tests,
with 60,006 timer IRQ executions and 2,096 modeled receiver acquisitions in the
paired experiment. PN2.27A is superseded by PN2.33; `python build.py --profile
pn2.27a --write` reproduces its exact tested bytes, archived in
`LPM-10A/Firmware File/archive/`.

[PN2.33](docs/releases/v2.33.md) (2026-09-24) is the current TX release, built on
PN2.27A through the [Cable Test audit](docs/TX-CABLE-TEST-AUDIT-2026-09-23.md):
LAN cable colours, keys ignored during a test, the RX-unit median / nearest-ladder
decision with a plausibility check, Switch mode as PN2.27A. Three device-tested
stages led to it — PN2.28 ("2.28 tested"), PN2.29 and PN2.30 (Switch mode yellow on
every wire: the pair-partner check, withdrawn) — plus two interim builds, PN2.31 and
PN2.32, that drew the shield as a grey "not tested" line ("ground show connect") and
are neither archived nor reproducible. `python build.py --write` reproduces the exact
tested bytes; `--profile pn2.28` / `pn2.29` / `pn2.30` rebuild the stages in
`experimental/`. The 56 Cable Test tests in `sdk/` are emulator results (every defect
test also runs the parent build and asserts its wrong answer); the device
confirmation is the owner's "2.33 test pass".

## Licences and credits

- Tooling, patches and documentation: MIT (see [LICENSE](LICENSE)).
- FNIRSI's original firmware files are not redistributed; obtain them from FNIRSI for building and rollback.
- Fonts: Ubuntu Sans Mono (Ubuntu Font Licence), Sarabun and Droid Sans Fallback (open licences).
