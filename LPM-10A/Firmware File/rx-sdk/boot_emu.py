#!/usr/bin/env python3
"""
Boot the receiver image under CPU emulation, from the reset vector through
SystemInit and main's initialisation, and report what the firmware actually
programs: the RCC clock tree, SystemCoreClock, the RCC_GetClocksFreqValue
result and the TIM1 / TIM5 prescaler + period registers.

    python boot_emu.py [image.bin]

This is how the timing facts in docs/RX-AUDIT.md were settled (the timer
rates cannot be read off the code alone: tim5_init computes a prescaler it
never uses, and the APB prescaler decides whether the timers run at the bus
clock or twice it).

Peripheral model: registers are plain memory, plus the few status bits the
start-up code polls (oscillator/PLL ready, clock-switch status, MSI ready,
PWR regulator flag, flash not busy, every GPIO input high).  Delays, the
UID-binding check, the version-tag check and the version-page check are skipped.
The run stops at adc1_init, which is the first routine that needs real
ADC behaviour.
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from lpm10rx import symbols as S                              # noqa: E402
from lpm10rx.image import STOCK_NAME, require_stock           # noqa: E402

from unicorn import (Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE,   # noqa: E402
                     UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE, UC_MEM_WRITE)
from unicorn.arm_const import UC_ARM_REG_PC, UC_ARM_REG_LR, UC_ARM_REG_R0, UC_ARM_REG_SP  # noqa: E402

PATH = sys.argv[1] if len(sys.argv) > 1 else require_stock(os.path.join(os.path.dirname(HERE), STOCK_NAME))
d = open(PATH, "rb").read()
F = S.FUNCS_BY_NAME

uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
uc.mem_map(0x08000000, 0x20000)
uc.mem_map(0x1FFFF000, 0x1000)               # chip UID
uc.mem_map(0x20000000, 0x10000)
uc.mem_map(0x40000000, 0x30000)              # peripherals
uc.mem_map(0x42000000, 0x2000000)            # bit-band alias of the peripheral region
uc.mem_map(0xE000E000, 0x1000)               # SCB / NVIC / SysTick
uc.mem_write(S.APP_BASE, d)
uc.mem_write(S.LICENCE_BLOCK, b"\xff" * 4 + b"\x11\x22\x33\x44" + b"\x00" * 16)   # provisioned
uc.mem_write(0x0800676C, struct.pack("<I", 0x2E33565F))                          # "_V3."
uc.mem_write(0x1FFFF7F0, bytes(range(12)))

RCC, PWR, FLASH = S.PERIPHERALS_BY_NAME["RCC"], S.PERIPHERALS_BY_NAME["PWR"], S.PERIPHERALS_BY_NAME["FLASH"]
GPIOS = {S.PERIPHERALS_BY_NAME[n] for n in ("GPIOA", "GPIOB", "GPIOC", "GPIOD")}
writes = []


def on_read(uc, access, addr, size, value, ud):
    a = addr & ~3
    v = struct.unpack("<I", uc.mem_read(a, 4))[0]
    if a == RCC + 0x00:                       # CTRL: HSIRDY, HSERDY, PLLRDY
        v |= (1 << 1) | (1 << 17) | (1 << 25)
    elif a == RCC + 0x04:                     # CFG: SCLKSTS mirrors SCLKSW
        v = (v & ~0xC) | ((v & 3) << 2)
    elif a == RCC + 0x24:                     # CTRLSTS: MSIRD
        v |= (1 << 3)
    elif a == PWR + 0x10:                     # regulator ready
        v |= 2
    elif a == FLASH + 0x0C:                   # STS: not busy
        v &= ~1
    elif (a & 0xFFFFFC00) in GPIOS and (a & 0x3FF) == 0x10:   # PID: inputs high
        v = 0xFFFF
    else:
        return
    uc.mem_write(a, struct.pack("<I", v))


def on_bitband(uc, access, addr, size, value, ud):
    off = addr - 0x42000000
    reg, bit = 0x40000000 + (off // 32), (off % 32) // 4
    v = struct.unpack("<I", uc.mem_read(reg & ~3, 4))[0]
    if access == UC_MEM_WRITE:
        v = (v | (1 << bit)) if (value & 1) else (v & ~(1 << bit))
        uc.mem_write(reg & ~3, struct.pack("<I", v))
    else:
        uc.mem_write(addr & ~3, struct.pack("<I", (v >> bit) & 1))


def on_write(uc, access, addr, size, value, ud):
    if (addr & ~3) in (RCC + 0x04, RCC + 0x40):
        writes.append((uc.reg_read(UC_ARM_REG_PC), addr, value))


SKIP = {F["delay_ms"], F["delay_us"], F["uid_license_check"], F["bootinfo_version_tag_missing"], F["version_page_check"]}
STOP = F["adc1_init"]
visited = []


def on_code(uc, addr, size, ud):
    if addr in SKIP:
        uc.reg_write(UC_ARM_REG_R0, 0)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
    elif addr == STOP:
        uc.emu_stop()
    elif addr in S.FUNCS and addr not in visited:
        visited.append(addr)


uc.hook_add(UC_HOOK_MEM_READ, on_read, begin=0x40000000, end=0x40030000)
uc.hook_add(UC_HOOK_MEM_WRITE, on_write, begin=0x40000000, end=0x40030000)
uc.hook_add(UC_HOOK_MEM_READ | UC_HOOK_MEM_WRITE, on_bitband, begin=0x42000000, end=0x44000000)
uc.hook_add(UC_HOOK_CODE, on_code)

sp0, reset = struct.unpack_from("<II", d, 0)
uc.reg_write(UC_ARM_REG_SP, sp0)
try:
    uc.emu_start(reset, 0, count=5_000_000)
except Exception as e:                        # noqa: BLE001
    print(f"emulation stopped: {e} at pc=0x{uc.reg_read(UC_ARM_REG_PC):08X}")

pc = uc.reg_read(UC_ARM_REG_PC)
print(f"image   : {PATH}")
print(f"stopped : 0x{pc:08X} {'<' + S.FUNCS[pc] + '>' if pc in S.FUNCS else ''}")
print("path    : " + " -> ".join(S.FUNCS[a] for a in visited))

cfg = struct.unpack("<I", uc.mem_read(RCC + 4, 4))[0]
pres = {0: 1, 4: 2, 5: 4, 6: 8, 7: 16}
ppre1, ppre2 = pres[(cfg >> 8) & 7], pres[(cfg >> 11) & 7]
mul = ((cfg >> 18) & 0xF) + 2 if not (cfg >> 27) & 1 else ((cfg >> 18) & 0xF) + 17
print(f"\nRCC_CFG = 0x{cfg:08X}: SCLKSW={cfg & 3} (3 = PLL)  HPRE=/{pres.get((cfg >> 4) & 0xF, '?')}  "
      f"APB1=/{ppre1}  APB2=/{ppre2}  PLLSRC={'HSE' if (cfg >> 16) & 1 else 'HSI'}  PLLMUL=x{mul}")
core = struct.unpack("<I", uc.mem_read(0x20000004, 4))[0]
clk = struct.unpack("<6I", uc.mem_read(0x20000030, 24))
print(f"SystemCoreClock      = {core:,} Hz")
print(f"RCC_GetClocksFreq    = sysclk {clk[0]:,}  hclk {clk[1]:,}  pclk1 {clk[2]:,}  pclk2 {clk[3]:,}")
tim1 = 2 * clk[3] if ppre2 != 1 else clk[3]
tim5 = 2 * clk[2] if ppre1 != 1 else clk[2]
print(f"timer clocks         = TIM1 {tim1:,} Hz  TIM5 {tim5:,} Hz  (x2 when the APB prescaler is not 1)")
for name, base, tclk in (("TIM1", S.PERIPHERALS_BY_NAME["TIM1"], tim1), ("TIM5", S.PERIPHERALS_BY_NAME["TIM5"], tim5)):
    psc = struct.unpack("<I", uc.mem_read(base + 0x28, 4))[0]
    ar = struct.unpack("<I", uc.mem_read(base + 0x2C, 4))[0]
    rate = tclk / (psc + 1) / (ar + 1)
    print(f"{name}: PSC={psc} AR={ar}  -> update every {1e6 / rate:.3f} us = {rate:,.2f} Hz")
