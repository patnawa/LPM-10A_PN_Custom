<div align="center">

# LPM-10A PN Custom Firmware

**PN 1.0: an unofficial, industrial-grade firmware for the FNIRSI LPM-10A network cable tester,
built by patching the official V2.0.7 image and proving every change by CPU emulation.**

![version](https://img.shields.io/badge/version-PN%201.0-orange)
![base](https://img.shields.io/badge/base-FNIRSI%20V2.0.7-lightgrey)
![patches](https://img.shields.io/badge/patches-11-blue)
![verified](https://img.shields.io/badge/verify.py-96%20checks%20pass-brightgreen)
![hardware](https://img.shields.io/badge/hardware%20test-pending-red)
![license](https://img.shields.io/badge/tooling%20license-MIT-lightgrey)

<img src="docs/img/length_screen.png" alt="Length screen: stock vs PN Custom, English and Chinese" width="900">

</div>

---

> **Status: verified by emulation, not yet flashed to a real unit.**
> Every change was checked by disassembly and by running the firmware's own code under a
> Cortex-M emulator (96 checks). That proves the code does what each patch says; it does
> not prove the LCD looks right. Flash at your own risk, and read
> [How to go back to stock](#going-back-to-stock) first.

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
| Cable calibration | none; the PHY's fixed constant | **NVP 50–99 %** on the Length screen, live redraw, saved; 69 % = factory |
| Length result | a new reading inside the tolerance band was replaced by the previous cable's value | the measured value is always shown |
| Low battery | one sample < 3150 mV starts an uncancellable 30 s shutdown | needs 3 consecutive samples; cancels when the pack recovers ≥ 3250 mV |
| Battery gauge | 4 steps | 10-step Li-ion curve, red at ≤ 20 % |
| Auto Off | keeps counting while the SCAN tone or FLASH blink is running, so a trace ends with the unit switching itself off | held (and restarted) while a tone or blink session is active; unchanged elsewhere |
| Settings save | 204 bytes leaked per save | freed on both exit paths |
| Fonts | thin serif 8×16 ASCII, Song-style Chinese | **Ubuntu Sans Mono** (8×16, 6×12) and **Droid Sans Fallback** (16×16), both open-licensed |
| Language | Chinese/English picker on first boot | boots to English; both languages kept, machine-translated strings corrected |
| Identity | About screen reports `Software:V2.0.7` | reports `Software:PN 1.0`; the bootloader-facing image name is untouched |

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
   certutil -hashfile LPM-10A-TX_PN1.0.bin SHA256
   6c1c8fa726857942e476f834b24cf94782db31fc6542dfa72e1f0baa7b67b1e0
   ```
2. Power the tester off. Hold **M + Power** until the firmware update screen appears.
3. Connect USB-C; a removable drive appears.
4. Copy [`LPM-10A-TX_PN1.0.bin`](LPM-10A/Firmware%20File/LPM-10A-TX_PN1.0.bin)
   onto that drive. Do not unplug during the update.
5. Long-press Power to shut down, then power on normally.

If the device refuses the file, rename it to exactly `LPM-10A-TX_V2.0.7_260610.bin` and copy
it again; some bootloaders match on the filename (the name stored inside the image is the
stock one for exactly this reason). The receiver firmware is not touched: keep
the `APP_LPM-10RX_V3.0.0_260416.bin` from FNIRSI's package. Requires V2.x.x hardware, like
stock V2.0.7.

### First power-on checklist

- Settings > About reads `Software:PN 1.0`.
- Text everywhere is the new bold sans font, in Chinese mode too.
- Length screen shows `NVP 69%` right of the Unit box; UP/DOWN change it and, after a
  test, the four readings follow.
- Leave the Length screen and return, then power-cycle: unit and NVP are kept.
- Measure two cables of different length back to back; the second must not repeat the first.
- The battery icon shows intermediate levels while discharging.

### Going back to stock

Same procedure with the original `LPM-10A-TX_V2.0.7_260610.bin` from FNIRSI's official
V2.0.7 package ([fnirsi.com](https://www.fnirsi.com), support / downloads). FNIRSI's files
are not distributed here. The bootloader lives in a separate flash region that is never
touched, so the update screen stays reachable. The two settings bytes the mod uses (NVP,
unit) are bytes the stock firmware ignores.

## NVP calibration

Professional testers let you set the cable's Nominal Velocity of Propagation. Length is
linear in NVP, so calibrating against a known cable is exact whatever the PHY assumes
internally:

1. Open **Length**, connect a cable of known length, press OK to measure.
2. Press **UP** / **DOWN** (hold for auto-repeat) until the four readings show the true
   length. The value `NVP nn%` is shown in the header and applied instantly, no re-measure
   needed.
3. Done. It is saved with the other settings at power-off. Factory Reset returns to 69 %.

Formula: `cm' = cm × NVP / 69`, integer maths, rounded. 69 % is the PHY's own calibration,
so the factory state is bit-identical to stock.

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
python build.py --write             # emit LPM-10A-TX_PN1.0.bin
python verify.py                    # 96 checks
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
| 12–16 | NVP | 72 arithmetic vectors, key hook (clicks, repeat, clamps, other screens), message routing, rendered text, screen-entry draw |
| 17 | fonts | the firmware's own glyph drawers render all 361 glyphs; pixels must equal the designed bitmaps |
| 18 | identity | the version strings through the firmware's `sprintf`; the container name is byte-identical to stock |

Each behavioural check runs the stock image too, so the report shows the defect and the fix
side by side. The SDK internals (symbol database, assembler, cave allocator, font tool) are
documented in [`LPM-10A/Firmware File/sdk/README.md`](LPM-10A/Firmware%20File/sdk/README.md).

## Repository layout

```
LPM-10A/
  Firmware File/
    LPM-10A-TX_PN1.0.bin              PN Custom image (the build output)
    LPM-10A-TX_V2.0.7_260610.bin      stock image: NOT included, put FNIRSI's copy here to build
    MOD-README.txt                    change list, hashes, flashing, checklist
    FORMULA-AUDIT.md                  every measurement formula, with verdicts
    sdk/                              the toolkit: patches, assembler, verifier, fonts
docs/img/                             the images on this page
```

## What next

The prioritised list of what to test on hardware and what to build after that is in
[`docs/ROADMAP.md`](docs/ROADMAP.md). The receiver (probe) firmware has been audited too:
[`docs/RX-AUDIT.md`](docs/RX-AUDIT.md).

## Known limitations

Things that need vendor source or hardware, so they are documented rather than patched:

- Cables under 2 m read "Out of range" (PHY blind zone).
- FreeRTOS queue calls are made from interrupt handlers in stock; the likely cause of
  rare lockups. The independent watchdog (≈3.3 s) is what recovers from a hard fault.
- The PoE "unstable supply" check compares byte data against 40 000 and can never trigger.
- NVP is on the Length screen, not in Settings: the five Settings rows already fill the
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
