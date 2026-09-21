<div align="center">

# LPM-10A PN Custom Firmware

Unofficial firmware for the **FNIRSI LPM-10A** network cable tester (TX) and its tone probe (RX).
Built by patching the shipped binaries — no vendor source — and verified by emulation and on a real unit.

![tester](https://img.shields.io/badge/TX-PN%202.14-blue) ![receiver](https://img.shields.io/badge/RX-PN%201.19-blue) ![licence](https://img.shields.io/badge/licence-MIT-green)

</div>

## Current firmware

| Device | Version | Download | File to copy |
|---|---|---|---|
| **TX** tester | **PN 2.14** | [Release v2.14](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/v2.14) | `LPM-10A-TX_PN2.14-tone-recovery.bin` |
| **RX** probe | **PN 1.19** | [Release rx-v1.19](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/rx-v1.19) | `APP_LPM-10RX_PN1.19-strong-cap-update.bin` |

Both are the builds running on the owner's unit (2026-09-21). Each release carries its notes and a
SHA-256 file. **TX and RX firmware are not interchangeable.** FNIRSI's own files are not
redistributed here.

> **สรุปภาษาไทย:** TX ใช้ PN 2.14, RX ใช้ PN 1.19 · TX อัปเดต: ปิดเครื่อง → กด **M + Power** ค้าง → เสียบ USB → ก๊อปปี้ไฟล์ ·
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
2. Copy **`APP_LPM-10RX_PN1.19-strong-cap-update.bin`** onto it with Explorer (an ordinary copy).
3. Within about **one second the drive disappears**: the probe has programmed the file and restarted.
   Unplug USB; press the power key if it is silent. PN 1.14+ chirps high→low at power-on.

Only the **`-update.bin` container** is accepted. The raw image FNIRSI ships for the RX — and every
`.bin` without `-update` — is silently ignored (the drive's status file shows `UNKOWN.TXT`). Slow or
sector-by-sector copy tools make the bootloader give up (`APPRUN.TXT`). **Back to stock:** wrap FNIRSI's
`APP_LPM-10RX_V3.0.0_260416.bin` with `python -m lpm10rx.container wrap …` and copy it the same way.
Everything about the RX update — why it never worked, the container format, what was changed, status
files, rollback, troubleshooting — is in **[docs/RX-UPDATE-GUIDE.md](docs/RX-UPDATE-GUIDE.md)** (Thai + English).

## What PN changes

### TX (tester)

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

Formulas and their verification: [`LPM-10A/Firmware File/FORMULA-AUDIT.md`](LPM-10A/Firmware%20File/FORMULA-AUDIT.md).
Why TDR needs NVP and how Zero was calibrated (0.4 m / 68 % on the owner's unit): [docs/README-DETAILED-2026-09-21.md](docs/README-DETAILED-2026-09-21.md#the-science-why-tdr-needs-nvp).

### RX (probe)

| | Stock (V3.0.0 / 3.0.1) | PN 1.19 |
|---|---|---|
| Sound per mode | one 2.5 kHz beep in every mode | **Digital 2.5 kHz, Analog 1.25 kHz** (one octave lower); key beeps chirp toward the mode (Digital low→high, Analog high→low) |
| Strength feedback | 50 ms beep / 50 ms gap whenever a signal is detected | 30 ms pulses whose **rate reports distance to the cable**: quiet interval 110 ms (weakest) → 20 ms (touching) |
| Sensitivity knob | sets gain; the middle of its travel fell to the lowest gain (firmware bug) | monotonic gain steps; the knob only sets how weak a signal is still accepted — turning it does not change the rhythm |
| Signal loss | audio kept going ~1 s after the TX stopped | stops within ~¼ s; a single missed reading no longer cuts the rhythm |
| Very strong signal | — | touching the cable is the fastest rhythm at every knob position (front-end saturation measured at ~2400 counts p-p) |
| Detection | exact 16-bit code match | PN 1.12 detector: full-window code search with bounded bit errors, upper-rail handling, guarded sample ownership |
| Low battery | uncancellable shutdown at one sample | recoverable |

Everything above was measured live over SWD on the probe while sweeping the knob and moving the probe:
[docs/RX-SENSITIVITY-2026-09-21.md](docs/RX-SENSITIVITY-2026-09-21.md). Pair TX **Digital** with RX Digital and
TX **Analog 825 Hz** with RX Analog. Only one hardware unit has been tested; range and cable selectivity are not
quantified against another probe.

## Known limitations

- **Cables of about 2 m and under cannot be measured** (the PHY's TDR blind zone); the Cable Test (wiremap)
  screen still finds the broken pair. Blind pairs read `< 2 m`.
- The TX update file is one 4 KB page longer than stock (code cave grew); the bootloader accepts it.
- Links that need more than 16 s to negotiate can still fail Port FLASH; the PoE "unstable supply" check
  can never trigger (vendor bug, left as is).
- RX Digital updates every 80 ms (the code repeats every 80 ms), so Analog reacts faster; Digital is the
  mode for noisy places. Very strong Analog signals at maximum knob clip the front end — turn the knob down.
- The RX front-end gain multipliers were measured on one unit; other units may need
  `MULT_X10` in `rx-sdk/gain_norm.py` re-measured.

## Repository layout

```
LPM-10A/Firmware File/
  experimental/LPM-10A-TX_PN2.14-tone-recovery.bin        current TX build
  experimental/TONE-RECOVERY-PN2.14-README.txt            its notes / TONE-RECOVERY-SHA256SUMS.txt
  experimental/APP_LPM-10RX_PN1.19-strong-cap-update.bin  current RX build — copy THIS to the BOOTLOADER drive
  experimental/APP_LPM-10RX_PN1.19-strong-cap.bin         its raw image (hashes, emulation only)
  experimental/RX-PN1.16-1.19-SHA256SUMS.txt              RX checksums
  RX-PN1.19-README.txt                                    RX notes: update, what you hear, rollback
  FORMULA-AUDIT.md                                        every TX measurement formula, with verdicts
  sdk/                                                    TX toolkit: patches, assembler, verifier, Thai UI
  rx-sdk/                                                 RX toolkit: patches (PN 1.0 → 1.19), container, emulator, tests
  (older PN builds and notes are kept alongside for reference)
docs/
  RX-UPDATE-GUIDE.md                    how to update / roll back the RX and what was changed to make it work
  RX-UPDATE-PROCEDURE-2026-09-21.md     the SWD investigation that found the container requirement
  RX-SENSITIVITY-2026-09-21.md          knob / gain / rhythm measurements behind PN 1.15–1.19
  RX-AUDIT.md                           the probe firmware, function by function
  ROADMAP.md                            what to test and build next
  RX-NEXT-STEPS-2026-09-21.md           detailed assessment of the next RX improvements
  README-DETAILED-2026-09-21.md         the full write-up: history, TDR science, maths, audits
  experiments/                          read-only SWD tools (rx_ro.py, rx_sens_capture.py, …)
```

Build: `python sdk/build.py --write` (TX) and `python rx-sdk/build.py --strong-cap --write` (RX) with FNIRSI's
images placed outside the repository (see each `build.py`). Every RX build writes both the raw image and the
`-update.bin` container; `python -m lpm10rx.container check <file>` tells which one you have.

## Licences and credits

- Tooling, patches and documentation: MIT (see [LICENSE](LICENSE)).
- FNIRSI's original firmware files are not redistributed; obtain them from FNIRSI for building and rollback.
- Fonts: Ubuntu Sans Mono (Ubuntu Font Licence), Sarabun and Droid Sans Fallback (open licences).
