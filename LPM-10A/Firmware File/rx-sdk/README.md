# LPM-10A receiver (probe) firmware SDK

**PN 1.7 precision experimental prerelease:** `python build.py --precision --write` builds
`../experimental/APP_LPM-10RX_PN1.7-precision.bin`. Its existing digital mode
adds robust strength grading, five beep levels, hysteresis and faster release
for comparing cables in a bundle. Includes PN 1.6; earlier profiles remain
available. Run `python -m unittest test_rx_precision -v`. See the
[implementation and validation report](../../../docs/RX-PRECISION-PN1.7-2026-09-19.md).
The owner reports a device test pass on 2026-09-19. Threshold calibration and
quantitative cable-selection measurements remain undocumented.
Download the [RX PN 1.7 prerelease](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/rx-v1.7).

**PN 1.6 local candidate:** `python build.py --followup --write` builds
`../experimental/APP_LPM-10RX_PN1.6-followup.bin`. It includes PN 1.5 plus fresh
sample ownership across mode/gate changes and stable digital beep scheduling.
Run `python -m unittest test_rx_followup -v`. Earlier profiles remain byte-exact.
See the [implementation report](../../../docs/RX-FIXES-PN1.6-2026-09-19.md).
Device validation is pending; this candidate has not been published or flashed.

**Previous PN 1.5 experimental prerelease:** `python build.py --audit --write` builds
`../experimental/APP_LPM-10RX_PN1.5-audit.bin`. It includes PN 1.4 plus a mains
sampler handoff correction and a DFT arithmetic fix that prevents strong
analog/mains signals from overflowing to zero. Run
`python -m unittest test_firmware_audit -v`. See the
[full TX/RX audit](../../../docs/FULL-FIRMWARE-AUDIT-2026-09-19.md).
CPU-tested; device validation pending. Vendor-facing version remains `3.0.0`.
Download the [RX prerelease](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/rx-v1.5).

**PN 1.4 ADC Timeout Fix experimental prerelease:** `python build.py --roadmap --write`
builds `../experimental/APP_LPM-10RX_PN1.4-roadmap.bin`. It adds recent-signal
auto-off protection, serialized ADC completion, main-loop watchdog feeding and
three digital beep cadences and the expanded ADC timeout margin.
Run `python -m unittest test_roadmap -v`.
The owner reported a PN 1.3 device test pass on 2026-09-19; PN 1.4 adds the ADC
timeout correction. The existing PN 1.0/1.1/1.2 profiles remain reproducible.
See the [implementation report](../../../docs/ROADMAP-IMPLEMENTATION-2026-09-19.md).

**Previous PN 1.2 Reliability experimental prerelease; owner-reported hardware pass.**
The owner reported successful new TX/RX testing on 2026-09-19. Retains the PN 1.1
digital detector and checks existing activity before idle auto-off. A narrow
deadline-ordering bug was reproduced in the original timer handler and fixed in
its existing 36-byte block. No ADC, analog/mains detector, battery, timer-rate,
speaker or device-binding changes from PN 1.1. See
[release notes](../RX-PN1.2-README.txt) and
[audit coverage](../../../docs/RELIABILITY-AUDIT-2026-09-19.md).

**2026-09-19: experimental digital detector available, off by default.**
The V3.0.0-based PN 1.1 digital candidate adds bounded bit-error tolerance
alongside the stock exact matcher, plus a provisional contrast floor. The
sampler, ADC and image size are unchanged. On 2026-09-19 the owner reported
successful testing of both new TX and RX firmware. Range/noise measurements
and compatibility with other revisions remain unverified. See
[candidate notes](../RX-PN1.1-DIGITAL-README.txt) and the
[implementation and test report](../../../docs/SCAN-IMPROVEMENTS-2026-09-19.md).

A patching toolkit for the tone-probe half of the FNIRSI LPM-10A, built against
the official receiver image **APP_LPM-10RX_V3.0.0_260416.bin**. Same philosophy
as the transmitter SDK in [`../sdk`](../sdk/README.md): no vendor source, every
byte accounted for, every behavioural change run under CPU emulation before it
is written to a file.

```
rx-sdk/
  lpm10rx/
    symbols.py    recovered symbol database: 156 functions, RAM map, constants
    image.py      raw-image loader, patch primitives, stock-image lookup
  rx_patches.py   the patch set
  build.py        build APP_LPM-10RX_PN1.0.bin
  verify.py       post-build verification (bytes + disassembly + emulation)
  verify_digital.py  opt-in detector: independent model, faults, noise and phase sweeps
  boot_emu.py     boots the image under emulation and prints the clock tree
                  and timer registers the firmware really programs
  disasm.py       movw/movt-aware disassembler, function survey, xref
```

Requires `capstone` and `unicorn`. The Thumb assembler is shared with the
transmitter SDK (`../sdk/lpm10a/thumb.py`).

## Quick start

```bash
python build.py --list          # what patches exist
python build.py                 # dry run: instruction-level diff
python build.py --write         # emit ../APP_LPM-10RX_PN1.0.bin
python verify.py                # 25 checks
python boot_emu.py              # clock tree and timer rates, from the running code
python disasm.py funcs          # survey every function
python disasm.py fn 08007770    # one function (add an image.bin anywhere to pick a file)
```

To build and verify the **experimental** digital candidate separately:

```bash
python build.py --only batt-critical-recover,digital-correlation --write
python verify.py --digital     # 41 checks, including original battery regressions
```

For the previous **PN 1.2 Reliability experimental prerelease**:

```bash
python build.py --only batt-critical-recover,digital-correlation,activity-before-autooff --write
python verify.py --reliability # 97 checks, including keys, housekeeping and auto-off
python -m unittest test_image -v
```

This writes `../APP_LPM-10RX_PN1.2-reliability-experimental.bin` without replacing
PN 1.0 or PN 1.1. `--all` now includes this new opt-in patch too. A custom subset
containing `activity-before-autooff` needs an explicit `--out` filename. Bounds
checks reject truncated reads, unterminated strings and resized-image writes.

The earlier two-patch digital command writes
`../APP_LPM-10RX_PN1.1-digital-experimental.bin`, not PN 1.0 or PN 1.2.
The default build/verification still use PN 1.0. The internal vendor version
string is deliberately unchanged (`3.0.0`); use the candidate hash to identify it.
Stock's five-read trimmed sampler is retained: this is not oversampling or
sub-slot clock recovery. The added contrast threshold needs bench calibration.

The stock receiver image is FNIRSI's and is **not in the repository**. Put it in
`LPM-10A/Firmware File/`, or in a folder named `LPM-10A_FNIRSI_originals` next
to the repository, or point `LPM10RX_STOCK` at it. `build.py` refuses any image
whose SHA-256 is not the V3.0.0 one.

## The target

| | |
|---|---|
| Image | raw Cortex-M image, **no container**, loaded at `0x08006800`; the bootloader page below holds the UID-binding record (`0x08006700`) and the `_V3.` tag |
| CPU | Nations N32L40x class: Cortex-M4F (FPU enabled), 16 MHz HSI, MSI, ADC1 at `0x40020800` |
| Clock | 64 MHz (HSI × PLL 4); APB1 = APB2 = 32 MHz; timer clocks 64 MHz. Verified by `boot_emu.py`, which runs the real `SystemInit`, `rcc_init` and timer set-up and reads the registers back |
| Toolchain | ARM Compiler (Keil MDK) at `-O0`: `b .+2` after almost every statement, addresses via `movw`/`movt`, no literal pools, ARM C library |
| Scheduling | no RTOS. TIM1 = **1 ms** tick (keys every 5 ms, battery every 500 ms, countdowns, 5-minute auto-off), TIM5 = **40 kHz** (ADC sampling, speaker PWM on CH4) |
| Version page | flash page `0x0801F000` holds `3.0.0`; `main` rewrites it when it differs. No settings are stored |
| Stack | `0x20001618`; about 5.6 KB of RAM in use |

There is no code cave: the image has no zero tail, and growing a raw image is a
bet on the bootloader. Patches are in-place, same length, which is easier than
it sounds because `-O0` code is loose enough to rewrite tighter.

The full functional description (modes, decoder, speaker, battery, keys,
device binding, what the bootloader question still blocks) is in [`../../../docs/RX-AUDIT.md`](../../../docs/RX-AUDIT.md).

## Current patch set

| id | risk | what |
|---|---|---|
| `batt-critical-recover` | low | The critical-battery shutdown can be cancelled: one reading below 3280 mV still enters the critical state, but each reading (every 500 ms) at or above 3400 mV returns to the low state and resets the counter, so only five **consecutive** low readings (2.5 s) power the unit off. Stock had no way back. 28 bytes changed, in place. |
| `digital-correlation` | untested, opt-in | Retain two exact sliding matches, or accept a full 48-bit window at one of eight rotations with at most four errors total / two per 16 samples; add a DC-independent contrast floor. Entire replacement fits the existing 336-byte routine, no persistent RAM or image growth. |

### What `verify.py` proves

| § | check | how |
|---|---|---|
| 1 | image | size, vector table, initial SP/reset unchanged; every changed byte declared; **every patched site holds exactly the recorded bytes** (stock before, new after); nothing outside the record differs |
| 2 | code | disassembly inventory compared by address; nothing after the edit differs; the patched block decodes to the intended instruction sequence |
| 3 | battery | the real battery routine run once per reading on stock and mod with a fake ADC and `power_off` trapped, nine voltage sequences with their **expected state/count traces** (dip then recovery, dip into the hysteresis band, flat pack, alternating load, healthy pack, slow decline, both sides of the recovery boundary, a restarted count), the shutdown timing, and the LED hysteresis after recovery |
| 4 | facts | r4 holds the sample-buffer base throughout the patched block; the byte counter wraps like stock; the ADC grid (3400 mV is not a representable reading, 3401 is) |
| 5, `--digital` | digital detector | Real detector/trimmed mean against an independent model: clean and corrupted patterns, contrast boundaries, all 256 periodic bytes, seeded noise, tones, synthetic drift, ISR buffer handoff, register preservation and owned memory writes |

A wrong build (different threshold, different branch target, different count)
fails the byte check, the instruction-sequence check and at least one trace.

## Writing a patch

```python
@patch("my-fix", "One line", risk="low", group="bugfix")
def p_my_fix(img):
    code = img.assemble_at(0x08007880, """
            mov  r1, sp
            ldrh r0, [r1, #4]
            ...
    """)
    img.poke(0x08007880, "40f25700 c2f2...", code, "why")
```

`poke` asserts the stock bytes and refuses a different length. Symbols from
`symbols.py` are available to the assembler by name (`bl power_off`).

## Flashing and recovery status

The owner confirmed update-mode entry on 2026-09-18: probe off, hold SCAN,
connect USB; the "UDISK" drive appears. On 2026-09-19 the owner reported that
both new TX and RX firmware work perfectly. The report does not establish
stock rollback or compatibility with every revision. The previous installed
RX version is uncertain; this patch requires the exact official V3.0.0 base.

The [RX prerelease](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/rx-v1.1)
contains the binary, notes and checksum. Verify the hash and confirm a stock
recovery path for your device before flashing. TX and RX images and update
procedures are separate. The application patch does not alter the UID-binding
code or record outside the image. The bootloader itself has not been audited.
