# LPM-10A firmware SDK

A reverse-engineering and patching toolkit for the FNIRSI LPM-10A cable tester
(TX / main unit), built against the official **V2.0.7** release.

There is no vendor source. Everything here works on the shipped binary:
it is disassembled, patched, re-assembled and verified in place.

```
sdk/
  lpm10a/
    symbols.py    recovered symbol database (functions, RAM map, tables)
    thumb.py      Thumb/Thumb-2 assembler, Capstone-verified
    image.py      container parser, patch primitives, code-cave allocator
  patches.py      the patch set
  build.py        build a modified firmware
  verify.py       post-build verification (disassembly + CPU emulation)
  assets.py       export / replace the UI graphics
  fonts.py        export / rebuild the three on-screen fonts
  cjk_chars.py    the 171 Chinese characters, in glyph-table order
  fonts_out/      the replacement font tables the build uses (+ previews)
  test_thumb.py   assembler round-trip tests
```

Requires `capstone` and `unicorn` (`pip install capstone unicorn`).
Rebuilding the fonts (not needed for a build) also needs `pillow` and `pymupdf`.

---

## Quick start

```bash
python test_thumb.py            # assembler self-test
python build.py --list          # what patches exist
python build.py                 # dry run: prints every byte it would change
python build.py --write         # emit LPM-10A-TX_PN1.3.bin
python verify.py                # prove the result is what was intended
```

The stock image `../LPM-10A-TX_V2.0.7_260610.bin` is **not part of the
repository**: download FNIRSI's official V2.0.7 package and copy the file
there, or keep it in a folder named `LPM-10A_FNIRSI_originals` next to the
repository, or set `LPM10A_STOCK` to its path (the tools try all three). `build.py` refuses to run unless it hashes to the expected SHA-256, so
it can never be silently applied to a different release. `assets_out/` (the UI
artwork exported from that image) and the `fonts_out/stock_*.png` glyph sheets
are likewise not committed; `python assets.py export` and `python fonts.py
export` regenerate them from the stock image.

---

## The target

| | |
|---|---|
| MCU | Nations N32G45x, Cortex-M4F @144 MHz |
| App load address | `0x0800A000` (a ~40 KB bootloader sits below, not in the package) |
| RTOS | FreeRTOS, heap_4, 48 KB heap, 1 ms tick, 11 tasks |
| Cable PHY | Motorcomm YT8531, bit-banged MDIO; length in cm read from CSD ext regs 0x87–0x8A, speed/duplex from reg 0x11 |
| ADC scaling | battery `raw×2×3300/4096` mV (1:2 divider); PoE `spread×3300×40/4096` mV (1:40 divider) |
| Settings | flash page `0x0807F800`, magic `0x9718`, 0xC8-byte struct flashed at power-off; stock never saves the length unit (mod: bytes 0xA6/0xA7 = NVP, unit; 0xC5 = Zero, stock struct padding) |
| Watchdog | IWDG, prescaler /32, reload 0xFFF ≈ 3.3 s, fed from TIM2 |
| Debug log | USART1 on PA9, **1 Mbaud**, TX only, very verbose |

### Update container

```
0x0000  char name[32]     internal image name (bootloader reads this)
0x0020  u32  payload_off  0x1000
0x0024  u32  payload_len
0x0028  u32  payload_end  == payload_off + payload_len - 1
0x1000  payload           loaded at 0x0800A000
```

**There is no CRC and no signature anywhere in the container.** A corrupted
file will be flashed as-is. That is why `verify.py` exists.

### Memory available for new code

* **Code cave** — 872 bytes at `0x08067C98`, the zero tail between the end of
  the payload and the end of its 2 KB flash sector. Because it is inside a
  sector the bootloader must already erase, extending `payload_len` into it
  does not touch any sector that would otherwise be left alone.
* **RAM arena** — `0x2000F000`, above the stack top (`0x2000E888`); nothing in
  the stock firmware references RAM above that. It is **outside the ZI region,
  so it is not zero-initialised** — which makes it the right place for a crash
  log that must survive a reset, and the wrong place for anything that assumes
  a clean start.

---

## Writing a patch

```python
@patch("my-fix", "One-line description", risk="low", group="bugfix")
def p_my_fix(img):
    from lpm10a.thumb import assemble
    code = assemble(0x08011234, """
            movs r0, #0
            strh r0, [r1, #0x28]
            b    0x08011240
    """)
    img.poke(0x08011234, "00bf f6e7 0000", code, "why this is correct")
```

Primitives on `img`:

| call | does |
|---|---|
| `poke(addr, expect_hex, new_bytes, why)` | overwrite, asserting the original bytes first; refuses to change length |
| `poke_blob(addr, stock_sha256, new_bytes, why)` | same for a data table identified by hash (fonts); the report prints a summary |
| `set_string(addr, text)` | replace a NUL-terminated string; refuses if it will not fit its slot |
| `emit_code(source)` | assemble into the code cave, returns its address |
| `alloc_ram(n)` | carve a variable out of the RAM arena |

Every primitive records what it touched. `verify.py` replays the patch set and
then holds the on-disk image to that record: **any byte that changed without
being declared by a patch is a failure.**

The assembler rejects anything it does not recognise rather than guessing, and
`test_thumb.py` round-trips every encoder through Capstone.

---

## Current patch set

| id | risk | group | what |
|---|---|---|---|
| `autooff-hold` | low | bugfix | Auto Off is held (and restarted) while a SCAN tone or FLASH blink session is running; stock already resets it on every key event |
| `boot-english` | low | english | Boot straight to English; no Chinese/English picker |
| `english-strings` | safe | english | Corrects the machine-translated UI text |
| `length-decimal` | low | measure | Length in **m / cm / ft with one decimal**, Zero- and NVP-corrected; the unit is remembered (stock: whole metres, inches, and cm forced on every screen entry) |
| `nvp-calibration` | low | measure | **NVP 50–99 % and Zero 0.0–2.0 m**: UP/DOWN adjust the white value on the Length screen, holding OK for a second swaps them, shown as `ZERO 0.0m` / `NVP 69%`, results redraw live, both persisted, Factory Reset clears both |
| `length-average` | low | measure | Each Test Start runs the PHY's cable diagnostic **4 times** (`AVG_RUNS`) and shows per-pair means; halves the ±0.3 m run-to-run scatter, test takes 4× longer. Code lives in the dead body of the stock `length_convert` |
| `length-no-sticky` | low | bugfix | The measured length is always displayed; stock kept the previous cable's reading if the new one was inside the tolerance band |
| `batt-debounce` | low | bugfix | Low-battery shutdown needs 3 consecutive samples < 3150 mV and is cancelled when the pack recovers to ≥ 3250 mV |
| `batt-gauge` | low | ux | 10-step Li-ion battery gauge instead of 4 steps |
| `settings-leak` | low | bugfix | Frees the 204-byte buffer leaked by every settings save |
| `font-pro` | low | ux | Replaces all three fonts: 8x16 and 6x12 ASCII (Ubuntu Sans Mono) and the 171 Chinese glyphs (Droid Sans Fallback) |
| `version-string` | safe | identity | About screen and boot log report `PN 1.3` (edit `VERSION` in patches.py, 7 characters max) |
| `scan-labels` | safe | identity | SCAN screen modes labelled `Digital` (0xB6B6 coded pattern) and `825 Hz` (keyed tone) instead of `Noiseless` / `Normal` |
| `about-url` | safe | identity | About screen shows `github.com/patnawa/LPM-10A_PN_Custom` (string in the cave, 6x12 font, 216 px) where the vendor site was; edit `REPO_URL` in patches.py, 36 characters max |
| `english-only` | untested | english | Removes Chinese from the language menu (off by default) |
| `batt-grace` | low | tuning | Low-battery shutdown grace 30 s → 60 s (off by default) |

`risk=untested` patches are excluded unless you pass `--all`; they are things
that look right on paper but need a real device to confirm. Everything else
is verified by emulation; the PN 1.0 set has also passed the first-power-on
checklist on a real unit (2026-09-18). PN 1.1's Zero + NVP calibration was confirmed there too. **The PN 1.2 run
averaging and the PN 1.3 labels have not been flashed yet.**

The reasoning behind each measurement change, and the formulas that were
checked and found correct, are in [`../FORMULA-AUDIT.md`](../FORMULA-AUDIT.md).

### What `verify.py` proves

Sections 1–3 are structural (container, byte footprint, disassembly
inventory compared **by address**, so a patch may change the instruction
count inside its own declared range), plus a byte-for-byte comparison with a
fresh in-memory build. Sections 4–18 execute the code:

| § | check | how |
|---|---|---|
| 4 | auto-off | a key event through `Action_key_Process` resets the counter on stock too (the corrected claim); the 1 s housekeeping holds in SCAN/FLASH only while the session flags are set |
| 5 | factory defaults | run the defaults writer, read the settings page image |
| 6 | unit conversion | run `length_convert` for 12 values × 3 units against a Python reference |
| 7 | on-screen text | run the cave formatter **through the firmware's own `sprintf`** and read the string |
| 8 | sticky result | run the store loop with a 50 m previous result and 52 m readings |
| 8b | run averaging | simulated CSD runs through the real re-run block: per-pair means, out-of-range runs left out, stale accumulator ignored, the timeout tick re-stamped per run, r4–r7 and sp intact, every arena write inside the patch's own allocation, all arena allocations disjoint; stock's single retry for comparison |
| 9 | battery debounce | feed sample sequences to the arming check; feed ADC + GPIO to the cancel check |
| 10 | battery gauge | sweep mV through the curve; run the drawing switch and read segment count / colour |
| 11 | heap leak | run both exit paths and trap the `vPortFree` call |
| 12 | Zero + NVP | `length_convert` for 9 NVP bytes × 3 units × 4 lengths, then 5 Zero bytes × 81 vectors, against the reference; the measured unit's numbers as a worked example |
| 13 | unit memory | screen-entry hook for stored 0/1/2/3/7/255 (and it resets the UP/DOWN target); the change hook stores and keeps the message args |
| 14 | keys | the key hook with UP/DOWN × click/repeat/long on both targets, all clamps, the OK hold toggle and every other OK event, POWER/LEFT/RIGHT, other screens; `GUI_MSG_SEND(0x3D, 0, 0)` and r4–r6 preserved |
| 14b | end to end | `Action_key_Process` itself in LENGTH, mod and stock: stock actions 0x11/0x12/0x13 still dispatch, UP/DOWN and the OK hold act, holds and releases are ignored |
| 15 | message | dispatcher routing for 0x10 / 0x3D / 0xFF; both texts through the real `sprintf`, `gui_blit` geometry, white/grey on black with the colour globals pre-loaded with a sentinel |
| 16 | screen entry | the picker epilogue draws both texts and returns with the stack and r4–r7 intact |
| 16b | Factory Reset | the defaults writer on mod and stock, the whole 0xC8-byte struct compared: only the first-boot flag and the Zero byte differ |
| 17 | fonts | the firmware's own glyph drawers render every glyph of all three tables; pixels must equal the designed bitmaps |
| 18 | identity | both version strings through the firmware's `sprintf`; container name byte-identical to stock |
| 18b | About URL | the About line's `gui_blit` call: geometry (12, 184, 216, 12), 12-px font, the URL text, stock colours; the stock draw for comparison |

Each behavioural check runs the stock image as well, so the report shows the
defect and the fix side by side.

### Zero and NVP calibration, how it works

The PHY reports each pair's length in centimetres assuming one fixed
propagation velocity, and the value includes the chip's own signal path.
The patch subtracts the Zero first (`cm0 = cm − 10 × Zero`, clamped at 0, so
a reading at or below the Zero shows as out of range for that pair), then
keeps the PHY's velocity as the 69 % reference and scales by `NVP / 69`,
both before the unit conversion (integer maths, rounded).  On the Length
screen UP/DOWN change whichever value is drawn white (NVP by 1 %, Zero by
0.1 m; auto-repeat when held); holding OK for about a second swaps them
(the RAM-arena byte `adj_target`, reset to NVP on every screen entry), and
the four results are redrawn immediately.  The field procedure needs two
cables: set Zero on a short one (about 3 m), NVP on a long one (15 m or
more), then re-check the short one.  NVP lives in settings byte 0xA6 and the
unit in 0xA7, free bytes the stock defaults writer zeroes; Zero lives in
0xC5, struct padding that stock never touches, which the hooked defaults
writer clears.  All three are flashed at power-off with the rest of the
struct, and Factory Reset returns them to 69 % / metres / 0.0 m.

A Settings-menu entry was considered and rejected: the five rows already fill
the 320-px screen (tiles at y = 68, 124, 175, 220, 263), so a sixth would mean
rewriting every hard-coded coordinate in three drawing functions.

---

## UI graphics

The 22 UI images are RGB565 blobs reached through a getter at `0x0800E3B0`,
with pointers in RAM at `0x200000E4..0x20000138`:

```
u16 magic 0x1000 | u16 width | u16 height | u16 flags 0x1B01 | u16 px[w*h]
```

```bash
python assets.py export                     # -> sdk/assets_out/*.png
python assets.py import 21 new.png          # replace one, writes a new .bin
```

Replacements must keep the **exact same width and height** — the blobs are
packed back-to-back and every pointer is absolute, so resizing one would shift
all the others. Export → import round-trips losslessly.

---

## Writing cave code

`emit_code` assembles into the cave with the symbol table from `symbols.py`
available, so hooks can `bl sprintf`, `bl vPortFree`, `ldr r4, =leng_unit_idx`
and so on by name. The assembler is deliberately small; what it accepts is
listed at the top of `lpm10a/thumb.py` (Thumb-1 plus `movw/movt`, `bl/b.w`,
`udiv/sdiv/mul/mls`, sp-relative `ldr/str`, `add/sub sp`). A label may share a
line with its instruction. Function symbols carry the Thumb bit; branch
encoders strip it.

Two things the patches rely on:

* A hook may read a register that is not an argument register, if the site
  guarantees it (e.g. `batt_low_check` takes the millivolts in **r5** because
  that is where `battery_ui_update` keeps them). Say so in the patch docstring.
* Variables in the RAM arena are **not** zero-initialised. Design them so a
  garbage value is harmless (the low-battery counter is reset by the first
  healthy sample and can at worst reproduce stock behaviour once).

## Known, not yet fixed

Architectural problems that cannot be retrofitted safely by patching a binary;
they need a rebuild from vendor source:

* Task-level `xQueueSend`/`xQueueReceive` called from the SysTick and TIM2
  interrupt handlers. No `*FromISR` variant exists anywhere in the image. This
  is the most likely cause of rare lockups.
* TIM2 runs at NVIC priority 0, above `configMAX_SYSCALL_INTERRUPT_PRIORITY`,
  and its handler calls logging code.
* All fault handlers are bare `while(1)` with no crash capture. The independent
  watchdog (prescaler /32, reload 0xFFF ≈ 3.3 s) is what recovers from a hard
  fault; a hung *task* is never caught because the watchdog is fed from TIM2.
* Cables of 2 m or less read "Out of range" (results ≤ 200 cm are zeroed).
* `poe_ring_is_stable` (0x08014C42) compares a byte spread with 40000 and can
  never report "unstable"; the intended threshold is not recoverable.

Fixed since the first mod: single-sample low-battery shutdown, the settings
save heap leak, the sticky length result, whole-metre display, Auto Off
during tone / blink sessions, and the missing cable calibration (NVP, then
Zero once the hardware test showed the offset). Mod 1's `autooff-keyreset` was removed: stock
already resets the idle counter at the end of `Action_key_Process`.

## Fonts

There are exactly three fonts, found by following `gui_draw_text_box`
(`0x0800EF6C`) → GUI message 0x38 → `gui_blit` → the glyph drawer at
`0x080171D4`, and the Chinese path `0x080176AC` → `0x08017550`:

| table | flash | glyphs | cell | format |
|---|---|---|---|---|
| ascii12 | `0x08065904` | 95 | 6×12 | column-major, 2 bytes/column, MSB = top, 4 pad bits |
| ascii16 | `0x08065D78` | 95 | 8×16 | column-major, 2 bytes/column, MSB = top |
| cjk16 | `0x08066368` | 171 | 16×16 | 16 little-endian u16 columns, bit N = row N |

The text-size selector is not a pixel size: `0x0C`/`0x10` pick the two ASCII
tables, `0x20` is 8×16 **centred**, `0x40`/`0x50` select the Chinese renderers.
Chinese strings are not GB2312; each byte is an index into the 171-glyph
table, terminated by a byte ≥ 0xAB. The characters, in table order, are in
`cjk_chars.py` (transcribed from the stock glyphs and checked side by side).

```bash
python fonts.py export     # stock tables -> fonts_out/stock_*.png
python fonts.py build      # rasterize replacements -> fonts_out/*.bin + *.png
python fonts.py preview    # render the .bin tables without Pillow
```

`build` renders with FreeType's monochrome hinting into the fixed cells:
Ubuntu Sans Mono (weight 600, 13 px and 10 px) for ASCII and Droid Sans
Fallback (16 px, extracted from the pymupdf wheel) for the Chinese glyphs.
Both fonts allow redistribution of the result; do not ship tables built from
the Microsoft fonts on a Windows machine. The `font-pro` patch writes the
three `.bin` files over the stock tables, and verify.py §17 runs the real
glyph drawers over them.
