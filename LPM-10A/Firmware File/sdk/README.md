# LPM-10A firmware SDK

**Build profiles (2026-09-21):** `python build.py --write` emits the latest profile;
`profiles.py` lists every PN version as its parent plus one module, with its output file
and hardware record, and `python -m unittest test_profiles` rebuilds each one in memory
and compares it with the published digest. `--profile pn2.14` (or the old alias flags
below) reproduces the release or any earlier version; `--default` builds the frozen
baseline that `verify.py` models. Custom builds (`--only`, `--with`, `--all`) need `--out`.

**PN 2.15 … 2.23 (PN 2.23 the release, every step on the owner's unit 2026-09-21):** one module each on top of PN 2.14 —
`length_progress.py` (run counter `1/4 … 4/4` on the Length Testing line),
`about_values.py` (`BATT / NVP / ZERO` line on About), `speed_partner.py` (a Switch row on
SPEED: the link partner's advertised speeds from IEEE registers 5 and 10) and
`length_reference.py` (a REF target on Length: dial a known cable length, NVP is solved
from it), `cable_test.py` (PN 2.19: the wire map reads eleven samples per pin and uses the
median, a real-short rule in Switch mode, "Not connected", the RX unit label; plus the
`cable-diag` experiment that prints the deciding numbers, `--with cable-diag --out …`),
`cable_clear.py` (PN 2.20: the message line is wiped before every test), `cable_values.py`
(PN 2.21: the reading that decided each wire at its right end; the partner pin in Switch mode),
`length_ref_anytime.py` (PN 2.22: REF reachable before a measurement; a REF dialled first is applied
to the next result once), `length_ref_reset.py` (PN 2.23: REF starts at 10.0 m on every screen entry —
PN 2.22 showed the RAM cell's power-up content, `REF 189.1`, on the unit).
Each has a test file on the real screen / key / draw code under Unicorn, in English and
Thai: `python -m unittest test_length_progress test_about_values test_speed_partner
test_length_reference test_cable_test test_cable_clear test_cable_values test_length_ref_anytime test_length_ref_reset -v`. See `../experimental/TX-PN2.16-2.18-README.txt`,
`../experimental/TX-PN2.19-CABLE-README.txt` and
[what is left on the TX](../../../docs/TX-NEXT-STEPS-2026-09-21.md).

**PN 2.14 local two-mode candidate:** `python build.py --scan-recovery --write`
uses the exact PN 2.12 parent with `Digital 454 kHz` / `Analog 825 Hz` labels in
both languages. It retains only the two established tone modes, their original
key cycle and waveforms, with no new tone state. It also repairs the RIGHT-key
carrier-cache invalidation while retaining the original GPIO operation.
The earlier RX PN 1.10 report established that those modes work while Sync32
was silent. Following the latest pair test request, the owner reports both
modes receive and sweeping is more accurate on confirmed RX PN 1.12 / TX PN 2.14.
Later feedback reports an open Digital issue: sound continues about one second
after moving away or pressing TX Pause; Analog has no such delay. See
[owner feedback](../../../docs/TONE-DEVICE-FEEDBACK-2026-09-20.md), the
[two-mode report](../../../docs/TONE-RECOVERY-PN2.14-2026-09-20.md) and
[detailed performance audit](../../../docs/TONE-PERFORMANCE-AUDIT-2026-09-20.md).

**PN 2.13 historical failed Sync32 trial:** the owner reports Sync32 silent even
with RX PN 1.10 in digital mode. Pulse test is a scope waveform, not a probe
tracing mode. These options were removed from the PN 2.14 menu at the owner's
request. The old binary/build profile is retained for reproducing the audit.
`python build.py --scan-sync --write`
adds optional Sync32 and Pulse test modes. The tone screen shows `Digital 454 kHz`,
`Analog 825 Hz`, `Sync32 454 kHz`, and `Pulse test` in both UI languages.
Digital/Sync32 display carrier frequency; Analog displays modulation frequency.
The existing generators and output hardware are preserved. Sync32 needs the
PN 1.10 RX digital mode. Run
`python -m unittest test_scan_sync.ScanSync test_sync_profile test_portflash_status -q`.
See the [paired implementation and limitations](../../../docs/SCAN-SYNC-PN2.13-PN1.10-2026-09-20.md).
Its CPU tests did not establish operation through the real analog path.
Existing named/default profiles remain available.

**PN 2.12 Port FLASH release:** `python build.py --portflash-status --write`
includes PN 2.11 plus direct PHY link reads and an indicator using the same
controller state. This follows the owner's intermittent long-on report with
PN 2.11 / D-Link gigabit. Run `python -m unittest test_portflash_status -v`.
See the [follow-up](../../../docs/PORT-FLASH-STATUS-2026-09-19.md).
Download the [TX release](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/v2.12).
CPU-tested; owner confirms the Port FLASH fix on the D-Link gigabit switch
(2026-09-19). Other functions await separate device validation.

**PN 2.11 audit candidate:** `python build.py --audit --write` includes all
Port FLASH fixes below, keeps battery monitoring active during FLASH and uses
the checked static settings writer for every save path. Run
`python -m unittest test_firmware_audit -v`. See the
[full TX/RX audit](../../../docs/FULL-FIRMWARE-AUDIT-2026-09-19.md).
CPU-tested; device validation pending. Default/released profiles are preserved.

**PN 2.10 Port FLASH candidate:** `python build.py --portflash --write` builds
all PN 2.9 roadmap features plus three PHY/FLASH recovery corrections. Run
`python -m unittest test_portflash -v`. This opt-in candidate awaits hardware
validation; the default and `--roadmap` profiles still reproduce PN 2.9.
See the [Port FLASH audit](../../../docs/PORT-FLASH-AUDIT-2026-09-19.md).

**Earlier TX PN 2.9 roadmap release.** The base build fixes partial
zero formatting and protects the PoE latch copy. `python build.py --roadmap --write`
adds deferred ISR events, service-task watchdog gating, calibration autosave and
retained crash diagnostics in `../experimental/LPM-10A-TX_PN2.9-roadmap.bin`.
Run `python -m unittest test_roadmap -v` for that profile. The owner reported a
PN 2.8 device test pass on 2026-09-19; PN 2.9 adds fault-handler corrections. The
default base profile remains a separate unreleased comparison build. See the
[implementation report](../../../docs/ROADMAP-IMPLEMENTATION-2026-09-19.md).

A reverse-engineering and patching toolkit for the FNIRSI LPM-10A cable tester
(TX / main unit), with hash-verified build inputs.

There is no vendor source. Everything here works on the shipped binary:
it is disassembled, patched, re-assembled and verified in place.

```
sdk/
  lpm10a/
    symbols.py    recovered symbol database (functions, RAM map, tables)
    thumb.py      Thumb/Thumb-2 assembler, Capstone-verified
    image.py      container parser, patch primitives, code-cave allocator
  patches.py      the patch set (the baseline, plus the modules registered at its end)
  profiles.py     the PN versions: parent, module, output file, hardware record
  build.py        build a modified firmware (the latest profile unless told otherwise)
  verify.py       post-build verification of the baseline (disassembly + CPU emulation)
  test_profiles.py  every profile rebuilds its published image byte for byte
  verify_scan.py  SCAN waveforms, interrupt paths, pause/resume and mode changes
  assets.py       export / replace the UI graphics
  fonts.py        export / rebuild the three on-screen fonts
  cjk_chars.py    the 171 Chinese characters, in glyph-table order
  fonts_out/      the replacement font tables the build uses (+ previews)
  test_thumb.py   assembler round-trip tests
  thai/           the Thai UI (PN 2.0): wording.py (every string), thaifont.py
                  (Sarabun -> 16x16 cells), cells.py (the shipped table, encoders),
                  sites.py (where every Chinese string lives), drawers.py (the
                  Thumb sources of the two drawers and the gui_blit hook),
                  engine.py (screen emulator: the firmware's draw code under
                  Unicorn), mockup.py / sheets.py (every screen, docs images),
                  compare.py + test_drawers.py (used by verify.py section 19)
```

Requires `capstone` and `unicorn` (`pip install capstone unicorn`).
Rebuilding the fonts (not needed for a build) also needs `pillow` and `pymupdf`;
the Thai mock-ups (`python -m thai.mockup`, `python -m thai.sheets`) need `pillow`;
regenerating the Thai cells (`python -m thai.cells`, not needed for a build) also
needs `uharfbuzz`.

---

## Quick start

```bash
python test_thumb.py            # assembler self-test
python build.py --list          # what patches and profiles exist
python build.py                 # dry run of the latest profile: prints every byte it would change
python build.py --write         # emit the latest profile (experimental/LPM-10A-TX_PN2.23-ref-reset.bin, the release)
python build.py --profile pn2.14 --write   # an earlier version (PN 2.14 was the release before PN 2.20)
python build.py --default --write   # the frozen baseline, LPM-10A-TX_PN2.9.bin (unreleased, what verify.py models)
python verify.py                # prove the baseline is what was intended
python -m unittest test_profiles -v  # every PN version rebuilds byte for byte
python verify_scan.py           # fast SCAN-only regressions (also in verify.py)
python -m unittest test_audit -v # allocator, dependency and battery-cancellation regressions
```

PN 2.7 adds bounded adaptive FLASH retries and full minimum hold/off durations,
partial length markers (`~`), overflow text (`OVR`), a stale-calibration redraw
guard and explicit battery-debounce startup initialisation. The owner reported
successful TX PN 2.7 / RX PN 1.2 testing on 2026-09-19. See
[audit, coverage and bench checklist](../../../docs/RELIABILITY-AUDIT-2026-09-19.md).
Run `python verify_reliability.py` for the focused regressions; they also run in
section 24 of the full verifier. [TX PN 2.7](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/v2.7)
is the previous release; RX PN 1.2 is the previous opt-in experimental prerelease
in `../rx-sdk`. Both binaries are unchanged from the owner-tested candidates.

PN 2.6 fixes the digital SCAN wrap, bypasses logging in its timer path, and
invalidates the cached carrier state before enabling so resume drives the right
level immediately. Carrier configuration and the 825 Hz waveform are unchanged.
See [SCAN improvements](../../../docs/SCAN-IMPROVEMENTS-2026-09-19.md).
The owner reports successful TX and RX hardware testing on 2026-09-19.
The [PN 2.6 release](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/v2.6)
includes the binary, device-specific notes and its SHA-256 checksum.

PN 2.5 clears the low-battery debounce counter when recovery or a charger cancels
an active shutdown, so the next low-voltage episode requires three fresh samples.
See [the audit](../../../docs/AUDIT-2026-09-19.md) for reproductions and remaining risks.

Subset builds must include their prerequisites, listed by `--list`:
`nvp-calibration`, `length-average` and `length-blind-text` require `length-decimal`;
`thai-ui` requires both `font-pro` and `length-decimal`. Missing dependencies fail
before edits, including when patches are called directly from Python. For example,
`python build.py --only length-decimal,length-average` is a valid dry run.

The stock image `../LPM-10A-TX_V2.0.7_260610.bin` is **not part of the
repository**: obtain the matching firmware package from FNIRSI and copy the file
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
  does not touch any sector that would otherwise be left alone. **When it is
  exhausted it grows** (`Image.extend()`, called by `alloc_code`): the
  container gets another 4 KB page of zeros appended (the unit the vendor's
  own file is padded to) and `payload_len` covers whatever of it is used.
  The header has nothing but the two length fields, so this is the same
  mechanism every PN build has used, now past `0x08068000`; the build summary
  says `[file extended by 4 KB]` and `verify.py` §1 reports the size. PN 2.3
  was the first build that needed it (393 216 bytes) and the bootloader
  accepted it on the tested unit on 2026-09-18; the PN 2.19 cable-diag build
  needed a second page (397 312 bytes) and the owner's unit took that too
  (2026-09-21), so two extra pages are known good.
* **Thai region** — the 53 glyph slots the Thai cell table does not use
  (`0x08067248..0x080678C8`, 1696 bytes), owned by `thai-ui`; its strings,
  tables and the three routines live there (4 bytes left).
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
| `autooff-hold` | low | bugfix | Auto Off is held (and restarted) while a SCAN tone or FLASH blink session is running; stock already resets it on every key event. PN 1.0–2.2 compared the FLASH state with 8 (QC Test) instead of 6, so only the SCAN half worked; fixed in PN 2.3, the value now comes from `symbols.STATES` |
| `boot-english` | low | english | Factory defaults come up in English with no language picker (off by default since PN 2.0: the Thai build keeps the English / ไทย picker) |
| `english-strings` | safe | english | Corrects the machine-translated UI text |
| `length-decimal` | low | measure | Length in **m / cm / ft with one decimal**, Zero- and NVP-corrected; the unit is remembered (stock: whole metres, inches, and cm forced on every screen entry) |
| `nvp-calibration` | low | measure | **NVP 50–99 % and Zero 0.0–2.0 m**: UP/DOWN adjust the white value on the Length screen, holding OK for a second swaps them, shown as `ZERO 0.0m` / `NVP 69%`, results redraw live, both persisted, Factory Reset clears both |
| `length-average` | low | measure | Each Test Start runs the PHY's cable diagnostic **4 times** (`AVG_RUNS`) and shows per-pair means; halves the ±0.3 m run-to-run scatter, test takes 4× longer. Code lives in the dead body of the stock `length_convert` |
| `length-no-sticky` | low | bugfix | The measured length is always displayed; stock kept the previous cable's reading if the new one was inside the tolerance band |
| `batt-debounce` | low | bugfix | Low-battery shutdown needs 3 consecutive samples < 3150 mV and is cancelled when the pack recovers to ≥ 3250 mV; counter explicitly cleared at main entry and cancellation |
| `batt-gauge` | low | ux | 10-step Li-ion battery gauge instead of 4 steps |
| `settings-leak` | low | bugfix | Frees the 204-byte buffer leaked by every settings save |
| `font-pro` | low | ux | Replaces all three fonts: 8x16 and 6x12 ASCII (Ubuntu Sans Mono) and the 171 Chinese glyphs (Droid Sans Fallback; superseded by the Thai cells when `thai-ui` is on) |
| `version-string` | safe | identity | About screen and boot log report `PN 2.8` (edit `VERSION` in patches.py, 7 characters max) |
| `length-blind-text` | low | measure | Zero-result pairs print `< 2` / `< 200` / `< 7` (m / cm / ft). With `length-average`, partial acquisition uses `~` instead of `=`. Reserved overflow displays `OVR`. These markers are not a diagnosis of physical fault distance. |
| `cable-back` | low | ux | Cable Test: Back returns to the Switch / Far end selector from the armed and result screens (stock left the screen); code lives in the Thai region |
| `cable-error-visible` | low | ux | Cable Test: the red "Result error!!" line moves above the Test Retry button (stock drew the button over it); the button moves 9 px down |
| `scan-labels` | safe | identity | SCAN screen modes labelled `Digital` (0xB6B6 coded pattern) and `825 Hz` (keyed tone) instead of `Noiseless` / `Normal` |
| `scan-timing` | low | scan | Exact 50-tick digital slots at wrap, no SCAN interrupt-context logging, immediate carrier restore on resume; no carrier or timer changes |
| `about-url` | safe | identity | About screen shows `github.com/patnawa/LPM-10A_PN_Custom` (string in the cave, 6x12 font, 216 px) where the vendor site was; edit `REPO_URL` in patches.py, 36 characters max |
| `thai-ui` | low | thai | **The second language is Thai**: 118 Sarabun cells in the glyph table, proportional drawers with the stock signatures, every Chinese string slot a redirect stub to its Thai text, a `gui_blit` hook for the six English-only messages (`wording.py` ASCII_TH), the About labels 14 px left, YES / NO as whole-word cells. English untouched. See `thai/` and `docs/THAI-UI.md` |
| `flash-blink` | low | flash | Link-aware blink with full minimum 1500 ms hold and 1000 ms PHY-off periods. Failed negotiation backs off 4 → 8 → 16 seconds, retains the working window during the session and resets on re-entry. Power-up is reasserted while waiting; indicator clears after 300 ms. Dispatch and negotiation add delay; links needing >16 s can still fail. |
| `poe-screen` | low | poe | PoE screen: the voltage column is **refreshed every 0.5 s** while a supply is present (stock drew it once per detection, from the sample just after the first one above 40 V, and not again while the screen was shown), every wire from one latched sample, cleared the moment the supply goes; **"Detecting..."** on entry and **"No PoE"** 3.5 s later without a supply (stock: blank, and its timeout only ever fired once per power-on because the counter was never re-armed). Five hooks and three literal-pool words, code in the cave, which grew the file by 4 KB |
| `batt-grace` | low | tuning | Low-battery shutdown grace 30 s → 60 s (off by default) |

The table above is the frozen baseline (`default=True`, what `verify.py` models). Everything since
PN 2.9 is a module selected by a profile (`profiles.py`, `python build.py --list`): `roadmap.py`
(service task, watchdog, calibration autosave, crash record), `portflash.py`, `audit_fixes.py`,
`portflash_status.py`, `scan_sync.py` (retired), `scan_recovery.py`, and the PN 2.15 … 2.23 chain
`length_progress.py`, `about_values.py`, `speed_partner.py`, `length_reference.py`,
`cable_test.py`, `cable_clear.py`, `cable_values.py`, `length_ref_anytime.py`, `length_ref_reset.py`. Each module
pins its parent image's SHA-256, writes its own version string and has its own test file.

`risk=untested` patches are excluded unless you pass `--all`; they are things
that look right on paper but need a real device to confirm. Everything else
is verified by emulation; the PN 1.0 set has also passed the first-power-on
checklist on a real unit (2026-09-18), PN 1.3 passed every function there and so did
PN 2.0 with the Thai interface, PN 2.1 with the two Cable Test fixes and PN 2.2 with
the blind-pair text; PN 2.3 flashed and ran (the bootloader took the 4 KB longer file) but
its FLASH blink stalled after a few cycles, fixed in PN 2.4, whose FLASH passed on the unit
the same day; the PoE screen still awaits its report. `english-only` was dropped: the
string it blanked was a log message, not the menu entry.

The reasoning behind each measurement change, and the formulas that were
checked and found correct, are in [`../FORMULA-AUDIT.md`](../FORMULA-AUDIT.md).

### What `verify.py` proves

Sections 1–3 are structural (container, byte footprint, disassembly
inventory compared **by address**, so a patch may change the instruction
count inside its own declared range), plus a byte-for-byte comparison with a
fresh in-memory build. Sections 4–18 execute the code:

| § | check | how |
|---|---|---|
| 4 | auto-off | a key event through `Action_key_Process` resets the counter on stock too (the corrected claim); the 1 s housekeeping holds in SCAN (5) / FLASH (6) only while the session flags are set, and not in QC Test (8) with stale flags |
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
| 16b | Factory Reset | the defaults writer on mod and stock, the whole 0xC8-byte struct compared: only the Zero byte differs |
| 17 | fonts | the firmware's own glyph drawers render every glyph of all three tables; pixels must equal the designed bitmaps |
| 18 | identity | both version strings through the firmware's `sprintf`; container name byte-identical to stock |
| 18b | About URL | the About line's `gui_blit` call: geometry (12, 184, 216, 12), 12-px font, the URL text, stock colours; the stock draw for comparison |
| 19 | Thai UI | the cell table and every cell through the stock glyph drawer; all 64 stubs resolved through RELOC to the wording table; the hook table against `wording.py`; the three routines byte-identical to `thai/drawers.py` assembled; the three jumps; the drawer unit test; then all 61 screen states in Thai pixel-identical to the model, all 61 in English pixel-identical to the same build without `thai-ui` (whose cave grows the same way), every Thai string drawn at least once |
| 20 | Cable Test Back | action 7 through the key dispatcher in every function state, mod and stock |
| 22 | FLASH blink | Hook, tick divisor, indicator delay and source-byte checks; full minimum hold/off intervals including just-before-boundary calls, bunched messages, retry, session gates and stock comparison. Section 24 adds adaptive 4/8/16-second windows, slow-link acquisitions, restart and rollover tests. |
| 21 | PoE screen | the five hook sites branch to the emitted blocks, the three literals point at the latch, and the blocks are the assembled sources, in the cave; `poe_tick` under emulation on the POE screen with a supply: 49 ticks post nothing, the 50th posts one 0x14 with the partial flag set, 200 ticks post four, no span / other screens post nothing, the supply going away posts one full redraw at once; screen entry: timeout counter 0xFFFF → 0, live cell cleared, "Detecting..." at (117, 220), the stock 0x14 still posted when a span is known, stock leaves the counter parked; the timeout's 0x14 draws "No PoE" (stock: nothing); a live refresh 48.2 → 53.1 V changes only the voltage column, to exactly what a full redraw draws, and the rows are drawn once; a sample changed mid-redraw does not reach the screen (stock: the second wire shows it) |

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
more), then re-check the short one.  Since PN 2.18 (`length_reference.py`) the
OK hold also offers **REF** while a result is on screen: the header shows the
measured length, UP/DOWN dial it to the cable's true length and every step
solves `NVP = 69 × REF / (raw − 10 × Zero)` from the mean of the timed pairs
(rounded, 50–99 %), so the long-cable step is one dial instead of a 1 %
hunt; Zero is still set first.  Without a result PN 2.18 skips REF (the hold
goes ZERO → NVP); PN 2.22 / 2.23 (`length_ref_anytime.py`, `length_ref_reset.py`)
always offer it, starting at 10.0 m on every screen entry, and apply a
REF dialled beforehand to the next result, once.  The RAM arena is not initialised
at power-up: a cell whose content is shown must be written on a known path first
(PN 2.22's lesson, `REF 189.1`).  NVP lives in settings byte 0xA6 and the
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
* Variables in the RAM arena are **not** zero-initialised. Initialise before
  use: PN 2.7 clears the debounce word at main entry; FLASH writes both phase
  timestamp and retry-window words before publishing its waiting phase.

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
  never report "unstable"; the intended threshold is not recoverable (the
  window it looks at would flag every supply once the units were consistent).

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
