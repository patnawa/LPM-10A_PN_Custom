"""RX key/housekeeping CPU regressions; GPIO, ADC work and power latch simulated."""
import struct
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R4,
    UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7, UC_ARM_REG_R8, UC_ARM_REG_R9,
    UC_ARM_REG_R10, UC_ARM_REG_R11, UC_ARM_REG_PC, UC_ARM_REG_LR, UC_ARM_REG_SP)

STOP, SP = 0x100000, 0x20001600
MODE, IDLE, TICK, BEEP = 0x20000048, 0x20000104, 0x200000FC, 0x2000010C
SAVED = (UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
         UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11)


class Control:
    def __init__(self, image):
        self.uc = uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
        for base, size in ((0x08000000, 0x20000), (0x20000000, 0x10000),
                           (0x40000000, 0x30000), (STOP, 0x1000)):
            uc.mem_map(base, size)
        uc.mem_write(0x08006800, bytes(image))
        self.pressed, self.gpio, self.calls = set(), {}, []
        self.pending = True
        uc.hook_add(UC_HOOK_CODE, self.hook)

    def w8(self, addr, n):
        self.uc.mem_write(addr, bytes([n]))

    def w16(self, addr, n):
        self.uc.mem_write(addr, struct.pack("<H", n))

    def w32(self, addr, n):
        self.uc.mem_write(addr, struct.pack("<I", n))

    def read(self, addr, size=1):
        return int.from_bytes(self.uc.mem_read(addr, size), "little")

    def hook(self, uc, addr, size, user):
        r0, r1 = uc.reg_read(UC_ARM_REG_R0), uc.reg_read(UC_ARM_REG_R1)
        if addr == 0x08008108:
            uc.reg_write(UC_ARM_REG_R0, int((r0, r1) not in self.pressed))
        elif addr == 0x0800AF08:
            uc.reg_write(UC_ARM_REG_R0, int(self.pending))
        elif addr in (0x08008170, 0x08008184, 0x08008198):
            key = (r0, r1)
            self.gpio[key] = int(addr == 0x08008170) if addr != 0x08008198 else 1 - self.gpio.get(key, 0)
        elif addr in (0x08007570, 0x08007770, 0x080084D8, 0x08008224, 0x0800ADC0):
            self.calls.append(addr)
        else:
            return
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    def run(self, addr=0x0800A97C):
        uc = self.uc
        sentinels = [0x11220000 + n for n in range(len(SAVED))]
        for reg, value in zip(SAVED, sentinels):
            uc.reg_write(reg, value)
        uc.reg_write(UC_ARM_REG_SP, SP)
        uc.reg_write(UC_ARM_REG_LR, STOP | 1)
        uc.emu_start(addr | 1, STOP, count=4000)
        assert uc.reg_read(UC_ARM_REG_PC) == STOP, "instruction budget exceeded"
        assert uc.reg_read(UC_ARM_REG_SP) == SP
        assert [uc.reg_read(r) for r in SAVED] == sentinels


def run_checks(stock, mod, check):
    def deadline(buf, idle, beep):
        c = Control(buf)
        c.w32(IDLE, idle); c.w8(BEEP, beep)
        c.run()
        return c

    before, after = deadline(stock, 300000, 50), deadline(mod, 300000, 50)
    check(0x08007570 in before.calls and 0x08007570 not in after.calls and after.read(IDLE, 4) == 0,
          "stock deadline bug reproduced: existing signal/key activity now prevents auto-off")
    for idle in (0, 299999, 300000, 300001):
        for beep in (0, 1, 50, 100, 255):
            c = deadline(mod, idle, beep)
            expected_off = idle >= 300000 and beep == 0
            check((0x08007570 in c.calls) == expected_off and c.read(IDLE, 4) == (0 if beep else idle + 1)
                  and c.read(BEEP) == max(0, beep - 1),
                  f"idle {idle}, activity {beep}: power-off={expected_off}, countdown/reset preserved")

    # Key presses act on RELEASE after six 5-ms scans, not on the press edge.
    mode, mains, lamp = (0x40011000, 0x8000), (0x40011400, 0x8000), (0x40011400, 0x4000)
    for label, pin in (("mode", mode), ("mains", mains), ("lamp", lamp)):
        for scans in (0, 1, 5, 6, 100):
            c = Control(mod)
            c.pressed = {pin}
            for _ in range(scans):
                c.run(0x080082B8)
            held = c.read(MODE) == 0 and c.read(BEEP) == 0 and not c.gpio
            c.pressed.clear()
            c.run(0x080082B8)
            accepted = scans >= 6
            effect = c.read(MODE) == (1 if label == "mode" else 2) if label != "lamp" else c.gpio.get((0x40010800, 0x400)) == 1
            check(held and bool(effect) == accepted and c.read(BEEP) == (100 if accepted else 0),
                  f"{label} key: {scans} held scans, exactly one release action={accepted}")
            state = (c.read(MODE), dict(c.gpio))
            c.run(0x080082B8)
            check((c.read(MODE), c.gpio) == state, f"{label} release does not repeat ({scans} scans)")

    c = Control(mod)
    modes = []
    for pin in (mode, mode, mains, mode):
        c.pressed = {pin}
        for _ in range(6):
            c.run(0x080082B8)
        c.pressed.clear(); c.run(0x080082B8)
        modes.append(c.read(MODE))
    check(modes == [1, 0, 2, 0], "mode sequence: digital / analog toggle, mains, return to digital", str(modes))

    c = Control(mod)
    for _ in range(1000):
        c.run()
    check(c.calls.count(0x08007770) == c.calls.count(0x080084D8) == c.calls.count(0x08008224) == 2
          and c.calls.count(0x0800ADC0) == 1000 and c.read(TICK, 4) == 1000,
          "1000 TIM1 ticks: battery, gain and watchdog each twice; interrupt acknowledged every tick")
    c = Control(mod); c.pending = False
    c.w32(IDLE, 300001); c.w8(BEEP, 50); c.run()
    check(not c.calls and c.read(IDLE, 4) == 300001 and c.read(BEEP) == 50,
          "no pending TIM1 interrupt: no countdown, power or housekeeping activity")
    c = Control(mod)
    c.pressed = {(0x40011000, 0x2000)}  # power key PC13
    c.w8(BEEP, 255)
    for _ in range(1199):
        c.run()
    early = 0x08007570 in c.calls
    c.w8(BEEP, 50)  # active on the actual shutdown tick, not merely earlier in the hold
    c.run()
    check(not early and c.calls.count(0x08007570) == 1,
          "physical power key still powers off after 1200 ticks, regardless of recent activity")

    # No other firmware paths changed between the prior digital image and PN 1.2.
    from pathlib import Path
    previous = (Path(__file__).resolve().parent.parent / "APP_LPM-10RX_PN1.1-digital-experimental.bin").read_bytes()
    changed = [0x08006800 + n for n, (a, b) in enumerate(zip(previous, mod)) if a != b]
    check(len(previous) == len(mod) and changed and all(0x0800A992 <= a < 0x0800A9B6 for a in changed),
          "PN 1.2 changes only the 36-byte auto-off block from PN 1.1; analog/mains/sampler untouched")
