# LPM-10A receiver (probe) firmware SDK

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

### What `verify.py` proves

| § | check | how |
|---|---|---|
| 1 | image | size, vector table, initial SP/reset unchanged; every changed byte declared; **every patched site holds exactly the recorded bytes** (stock before, new after); nothing outside the record differs |
| 2 | code | disassembly inventory compared by address; nothing after the edit differs; the patched block decodes to the intended instruction sequence |
| 3 | battery | the real battery routine run once per reading on stock and mod with a fake ADC and `power_off` trapped, nine voltage sequences with their **expected state/count traces** (dip then recovery, dip into the hysteresis band, flat pack, alternating load, healthy pack, slow decline, both sides of the recovery boundary, a restarted count), the shutdown timing, and the LED hysteresis after recovery |
| 4 | facts | r4 holds the sample-buffer base throughout the patched block; the byte counter wraps like stock; the ADC grid (3400 mV is not a representable reading, 3401 is) |

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

## Flashing (unverified)

FNIRSI's package contains the receiver image but its readme only describes the
transmitter's update mode. The receiver bootloader is large enough for the same
USB-drive method with its own key combination, but this has not been confirmed.
Do not flash the receiver until the procedure is known and a way back to the
stock image is confirmed; the stock file is the only recovery. The UID-binding
record sits outside the application image, so an application update does not
re-provision the unit.
