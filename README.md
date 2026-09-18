<div align="center">

# LPM-10A PN Custom Firmware

**PN 1.1: an unofficial, industrial-grade firmware for the FNIRSI LPM-10A network cable tester,
built by patching the official V2.0.7 image, proving every change by CPU emulation, and
validated on a real unit (PN 1.0; the PN 1.1 additions await their own flash).**

![version](https://img.shields.io/badge/version-PN%201.1-orange)
![base](https://img.shields.io/badge/base-FNIRSI%20V2.0.7-lightgrey)
![patches](https://img.shields.io/badge/patches-12-blue)
![verified](https://img.shields.io/badge/verify.py-142%20checks%20pass-brightgreen)
![hardware](https://img.shields.io/badge/hardware%20test-PN%201.0%20passed-brightgreen)
![license](https://img.shields.io/badge/tooling%20license-MIT-lightgrey)

<img src="docs/img/length_screen.png" alt="Length screen: stock vs PN Custom, NVP and Zero calibration, English and Chinese" width="1000">

</div>

---

> **Status: PN 1.0 passed every item of the first-power-on checklist on a real unit
> (2026-09-18).** PN 1.1 adds the Zero calibration that the hardware test showed was
> needed; that addition is verified by emulation (142 checks) and awaits its own flash.
> Flash at your own risk, and read [How to go back to stock](#going-back-to-stock) first.

## Why

The LPM-10A is a capable tester (Motorcomm YT8531 PHY, TDR length, PoE, wiremap) let down
by its firmware: length shown in whole metres, no cable calibration, a low-battery
shutdown armed by a single noisy ADC sample, an Auto-Off that cut cable-tracing sessions
short, a heap leak on every settings save, and the thin serif "dev-board" font.
There is no vendor source, so this project works on the shipped binary: it disassembles
it, adds code in an unused flash tail, re-assembles, and verifies the result in place.

## What changes

| Area | Stock V2.0.7 | PN Custom |
|---|---|---|
| Length display | whole metres ("55"), inches, cm forced on every screen entry | **m / cm / ft with one decimal** ("55.4"), unit remembered across power cycles |
| Cable calibration | none; the PHY's fixed constant | **Zero 0.0–2.0 m and NVP 50–99 %** on the Length screen, live redraw, saved; 0.0 m / 69 % = factory |
| Length result | a new reading inside the tolerance band was replaced by the previous cable's value | the measured value is always shown |
| Low battery | one sample < 3150 mV starts an uncancellable 30 s shutdown | needs 3 consecutive samples; cancels when the pack recovers ≥ 3250 mV |
| Battery gauge | 4 steps | 10-step Li-ion curve, red at ≤ 20 % |
| Auto Off | keeps counting while the SCAN tone or FLASH blink is running, so a trace ends with the unit switching itself off | held (and restarted) while a tone or blink session is active; unchanged elsewhere |
| Settings save | 204 bytes leaked per save | freed on both exit paths |
| Fonts | thin serif 8×16 ASCII, Song-style Chinese | **Ubuntu Sans Mono** (8×16, 6×12) and **Droid Sans Fallback** (16×16), both open-licensed |
| Language | Chinese/English picker on first boot | boots to English; both languages kept, machine-translated strings corrected |
| Identity | About screen reports `Software:V2.0.7` and `http://www.fnirsi.cn` | reports `Software:PN 1.1` and this repository's URL; the bootloader-facing image name is untouched |

Everything is also verified **correct and left alone** where stock was right: battery mV,
PoE mV, link speed/duplex decoding, the 2.54 inch constant, the auto-off table. The full
per-formula audit with verdicts is in
[`LPM-10A/Firmware File/FORMULA-AUDIT.md`](LPM-10A/Firmware%20File/FORMULA-AUDIT.md).

## Fonts

The firmware has exactly three glyph tables. They were located, decoded (column-major
bitmaps; the Chinese strings are glyph indices, not GB2312), transcribed, and regenerated
in the same cells so no screen layout changes.

<div align="center">
<img src="docs/img/font_ascii.png" alt="ASCII font, stock vs new" width="700">
</div>

<details>
<summary>All 171 Chinese glyphs, stock (white) beside PN Custom (green)</summary>
<div align="center">
<img src="docs/img/font_cjk.png" alt="Chinese glyph table, stock vs new" width="700">
</div>
</details>

## Install

1. Verify the download:
   ```
   certutil -hashfile LPM-10A-TX_PN1.1.bin SHA256
   315f3214b605d812979cbafa7e9cc59c542467ac398d4baaa1d308915cc32604
   ```
2. Power the tester off. Hold **M + Power** until the firmware update screen appears.
3. Connect USB-C; a removable drive appears.
4. Copy [`LPM-10A-TX_PN1.1.bin`](LPM-10A/Firmware%20File/LPM-10A-TX_PN1.1.bin)
   onto that drive. Do not unplug during the update.
5. Long-press Power to shut down, then power on normally.

If the device refuses the file, rename it to exactly `LPM-10A-TX_V2.0.7_260610.bin` and copy
it again; some bootloaders match on the filename (the name stored inside the image is the
stock one for exactly this reason). This update does not touch the receiver (probe); the
receiver build below is a separate file with its own, still unconfirmed, procedure. Requires
V2.x.x hardware, like stock V2.0.7.

### First power-on checklist

The PN 1.0 items passed on a real unit on 2026-09-18 (the bootloader accepted the file
under its own name). The Zero and About-URL items are new in PN 1.1 and still need their
first check:

- Settings > About reads `Software:PN 1.1` and shows `github.com/patnawa/LPM-10A_PN_Custom`.
- Text everywhere is the new bold sans font, in Chinese mode too.
- Length screen shows `ZERO 0.0m` left of the Unit box and `NVP 69%` right of it; UP/DOWN
  change the white one, a long press of OK swaps which is white, and after a test the four
  readings follow.
- Leave the Length screen and return, then power-cycle: unit, NVP and Zero are kept.
- Measure two cables of different length back to back; the second must not repeat the first.
- SCAN with the tone on for longer than Auto Off: the unit stays on and the probe still
  finds the tone.
- The battery icon shows intermediate levels while discharging.

### Going back to stock

Same procedure with the original `LPM-10A-TX_V2.0.7_260610.bin` from FNIRSI's official
V2.0.7 package ([fnirsi.com](https://www.fnirsi.com), support / downloads). FNIRSI's files
are not distributed here. The bootloader lives in a separate flash region that is never
touched, so the update screen stays reachable. The three settings bytes the mod uses (NVP,
unit, Zero) are bytes the stock firmware ignores.

## Length calibration: Zero and NVP

The PHY's TDR reading contains two errors, and the hardware test measured both on one
unit: a fixed **offset** from the chip's own signal path and a **scale** from the cable's
velocity of propagation. At NVP 69 % a 2.9 m cable read 3.1–3.5 m in one session and,
converted back from a later session at 66 %, 3.45–3.66 m; a 14 m cable read 14.4–15.0 m.
That is an offset of roughly +0.4 to +0.6 m with a scale within a few percent, on top of
the PHY's ±0.2 m reading-to-reading spread. A factor (NVP) alone cannot remove an offset,
which is why PN 1.1 adds Zero:

```
length = (raw − Zero) × NVP / 69       Zero 0.0–2.0 m in 0.1 m steps, NVP 50–99 %
```

On the **Length** screen `ZERO 0.0m` is shown left of the Unit box and `NVP 69%` right of
it. UP / DOWN (hold for auto-repeat) change the value drawn in white; **hold OK for about a
second** to swap which one is white (a short press still starts a test). Every change
redraws the four readings at once, no re-measure needed. Both values are saved with the other settings at power-off; Factory Reset returns
to 0.0 m / 69 %.

To calibrate, use two cables of known length, one short (about 3 m) and one long (15 m or
more):

1. Measure the short cable. Long-press OK to select Zero, then UP / DOWN until it reads
   right.
2. Measure the long cable. Long-press OK to select NVP, then UP / DOWN until it reads right.
3. Re-check the short cable; adjust Zero once more if needed.

On the unit measured, expect Zero around 0.5 m and NVP around 68 %; every unit and cable
batch will differ, which is the point of having the controls. Below about 2 m the PHY's
value is unreliable: a 1 m cable came back as 2.4 m or as *Out of range*. The stock blind
zone (raw readings of 2 m or less are discarded, before the Zero is subtracted) is kept, so
short readings are not to be trusted.

Integers only, rounded; 69 % and 0.0 m are the PHY's own calibration, so at the factory
values the reading is exactly stock's centimetre value.

## How it is built and verified

<div align="center">
<img src="docs/img/pipeline.png" alt="Build and verification pipeline" width="900">
</div>

The build input is FNIRSI's own image, which is **not in this repository**: download the
official V2.0.7 package, unzip it, and put `LPM-10A-TX_V2.0.7_260610.bin` either in
`LPM-10A/Firmware File/`, in a folder named `LPM-10A_FNIRSI_originals` next to the
repository, or anywhere with `LPM10A_STOCK` pointing at it. Every tool checks its SHA-256
(`29081ccbbd929a884c7c81fb309aa2894ce2ab84e061918538b3ead8e632940b`) and refuses anything else.

```bash
cd "LPM-10A/Firmware File/sdk"
pip install capstone unicorn        # pillow + pymupdf only to rebuild the fonts
python test_thumb.py                # assembler self-test against Capstone
python build.py --list              # the patch set
python build.py                     # dry run: every byte it would change, disassembled
python build.py --write             # emit LPM-10A-TX_PN1.1.bin
python verify.py                    # 142 checks
```

`build.py --only a,b` builds a subset; every patch is independent. `build.py` refuses to
run on anything but the pinned stock image.

What `verify.py` proves, section by section:

| § | check | how |
|---|---|---|
| 1–3 | container, byte footprint, full disassembly inventory | any byte changed without being declared by a patch fails |
| 4–5 | auto-off hold, factory defaults | a key event through the stock dispatcher (proves stock already resets on keys); the 1 s housekeeping in SCAN/FLASH with the session flags on and off |
| 6–7 | unit conversion, on-screen text | 36 vectors; the text comes out of the firmware's own `sprintf` |
| 8 | sticky result | 50 m previous, 52 m readings: stock keeps 50, mod stores 52 |
| 9–10 | battery debounce and gauge | sample sequences, ADC + GPIO for the cancel path, 18-point curve |
| 11 | heap leak | both exit paths trapped at `vPortFree` |
| 12–16 | Zero + NVP | 477 arithmetic vectors including the measured unit's numbers, key hook (clicks, repeat, clamps, OK long press, other screens), message routing, both rendered texts with their colours, screen-entry draw, Factory Reset defaults compared with stock byte for byte |
| 17 | fonts | the firmware's own glyph drawers render all 361 glyphs; pixels must equal the designed bitmaps |
| 18 | identity | the version strings through the firmware's `sprintf`; the container name is byte-identical to stock; the About URL line's geometry, font and text at the `gui_blit` call |

Each behavioural check runs the stock image too, so the report shows the defect and the fix
side by side. The SDK internals (symbol database, assembler, cave allocator, font tool) are
documented in [`LPM-10A/Firmware File/sdk/README.md`](LPM-10A/Firmware%20File/sdk/README.md).

## Repository layout

```
LPM-10A/
  Firmware File/
    LPM-10A-TX_PN1.1.bin              PN Custom image (the build output)
    LPM-10A-TX_V2.0.7_260610.bin      stock image: NOT included, put FNIRSI's copy here to build
    MOD-README.txt                    change list, hashes, flashing, checklist
    FORMULA-AUDIT.md                  every measurement formula, with verdicts
    sdk/                              the transmitter toolkit: patches, assembler, verifier, fonts
    APP_LPM-10RX_PN1.0.bin            receiver image (battery fix); flashing procedure unconfirmed
    RX-README.txt                     receiver change list, hash, warnings
    rx-sdk/                           the receiver toolkit: patches, verifier, disassembler
docs/img/                             the images on this page
```

## Receiver (probe)

The probe has its own firmware, audit and toolkit:
[`docs/RX-AUDIT.md`](docs/RX-AUDIT.md) and
[`LPM-10A/Firmware File/rx-sdk`](LPM-10A/Firmware%20File/rx-sdk/README.md). The first receiver
build, [`APP_LPM-10RX_PN1.0.bin`](LPM-10A/Firmware%20File/APP_LPM-10RX_PN1.0.bin), fixes one
thing: a critical-battery shutdown that could not be cancelled once a single reading dipped
below 3280 mV. It is emulation-verified (25 checks) and **must not be flashed yet**: FNIRSI
does not document how the receiver enters its update mode, and the way back to stock has to
be confirmed first. Details in
[`LPM-10A/Firmware File/RX-README.txt`](LPM-10A/Firmware%20File/RX-README.txt).

## What next

The prioritised list of what to test on hardware and what to build after that is in
[`docs/ROADMAP.md`](docs/ROADMAP.md).

## Known limitations

Things that need vendor source or hardware, so they are documented rather than patched:

- Cables under 2 m read "Out of range" (PHY blind zone).
- FreeRTOS queue calls are made from interrupt handlers in stock; the likely cause of
  rare lockups. The independent watchdog (≈3.3 s) is what recovers from a hard fault.
- The PoE "unstable supply" check compares byte data against 40 000 and can never trigger.
- NVP and Zero are on the Length screen, not in Settings: the five Settings rows already fill the
  320-px screen.
- The update container has no CRC or signature; that is what `verify.py` is for.

## Licences and credits

- Tooling, patches and documentation: MIT (see [LICENSE](LICENSE)).
- FNIRSI's firmware files are not redistributed here; the build takes the official V2.0.7
  image as its input and the flashing instructions send you to FNIRSI for it.
- Fonts: Ubuntu Sans Mono under the Ubuntu Font Licence 1.0; Droid Sans Fallback under the
  Apache License 2.0. Both permit redistribution of the rasterized glyphs.
- Disassembly with [Capstone](https://www.capstone-engine.org/), emulation with
  [Unicorn](https://www.unicorn-engine.org/).

*Not affiliated with or endorsed by FNIRSI.*
