"""SCAN CPU regressions. Run standalone, or via verify.py section 23.

Executes the firmware's dispatcher, generators, gate and key handlers. The
carrier GPIO routines, RTOS services and other TIM2 clients are trapped: this
checks logical waveforms and control flow, not electrical signals or timing.
"""
from collections import Counter
from pathlib import Path
import struct
import sys

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE
from unicorn.arm_const import (
    UC_ARM_REG_R0, UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6,
    UC_ARM_REG_R7, UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10,
    UC_ARM_REG_R11, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC,
)

APP, STOP, STACK = 0x0800A000, 0x00100000, 0x2000E000
SCAN, STATE, DIGITAL = 0x200000D0, 0x2000013C, 0x200000D8
DISPATCH, IRQ = 0x08014684, 0x08018370
SAVED = (UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
         UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11)
LOG_CALLS = {0x0801C6B4, 0x0801C6D8, 0x0800A82C, 0x0800A3B8,
             0x08012C64, 0x0801CAA0}


class ScanMachine:
    def __init__(self, data, mode=1, enabled=1, state=5):
        off, size = struct.unpack_from('<II', data, 0x20)
        self.uc = uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
        for base, length in ((0x08000000, 0x80000), (0x20000000, 0x10000),
                             (0x40000000, 0x30000), (STOP, 0x1000)):
            uc.mem_map(base, length)
        uc.mem_write(APP, bytes(data[off:off + size]))
        self.w8(STATE, state)
        self.w8(SCAN, enabled)
        self.w8(SCAN + 1, mode)
        self.requests, self.outputs, self.messages = [], [], []
        self.calls, self.instructions = Counter(), 0
        self.carrier, self.pending = 0, 1
        uc.hook_add(UC_HOOK_CODE, self.hook)

    def w8(self, addr, value):
        self.uc.mem_write(addr, bytes([value]))

    def w32(self, addr, value):
        self.uc.mem_write(addr, struct.pack('<I', value))

    def r8(self, addr):
        return self.uc.mem_read(addr, 1)[0]

    def r32(self, addr):
        return struct.unpack('<I', self.uc.mem_read(addr, 4))[0]

    def ret(self, value=0):
        self.uc.reg_write(UC_ARM_REG_R0, value)
        self.uc.reg_write(UC_ARM_REG_PC, self.uc.reg_read(UC_ARM_REG_LR))

    def hook(self, uc, addr, size, user):
        self.instructions += 1
        if addr == 0x0801464C:
            self.requests.append(uc.reg_read(UC_ARM_REG_R0))
        elif addr in (0x0801A6EC, 0x0801A6B0):
            self.carrier = int(addr == 0x0801A6EC)
            self.calls[addr] += 1
            self.ret()
        elif addr in LOG_CALLS:
            self.calls[addr] += 1
            self.ret(0x2000F800 if addr == 0x08012C64 else 0)
        elif addr == 0x08018592:
            self.ret(self.pending)
        elif addr in (0x080183CC, 0x080169A8, 0x0800F9CC, 0x08010F94):
            self.calls[addr] += 1
            self.ret()
        elif addr == 0x0801C5B0:
            self.ret()
        elif addr == 0x0800E428:
            self.messages.append(uc.reg_read(UC_ARM_REG_R0))
            self.ret()

    def call(self, addr, arg=0):
        uc = self.uc
        uc.reg_write(UC_ARM_REG_SP, STACK)
        uc.reg_write(UC_ARM_REG_LR, STOP | 1)
        uc.reg_write(UC_ARM_REG_R0, arg)
        sentinels = [0x12340000 + i for i in range(len(SAVED))]
        for reg, value in zip(SAVED, sentinels):
            uc.reg_write(reg, value)
        uc.emu_start(addr | 1, STOP, count=10000)
        if uc.reg_read(UC_ARM_REG_PC) != STOP:
            raise AssertionError(f'{addr:#x}: did not return within instruction limit')
        if uc.reg_read(UC_ARM_REG_SP) != STACK:
            raise AssertionError(f'{addr:#x}: stack imbalance')
        if [uc.reg_read(r) for r in SAVED] != sentinels:
            raise AssertionError(f'{addr:#x}: callee-saved register corruption')

    def ticks(self, count, entry=DISPATCH):
        for _ in range(count):
            self.call(entry)
            self.outputs.append(self.carrier)


def digital_expected(tick):
    return (0xB6B6 >> (15 - (tick % 800) // 50)) & 1


def run_checks(stock, mod, check):
    old, new = ScanMachine(stock, mode=0), ScanMachine(mod, mode=0)
    old.ticks(8001)
    new.ticks(8001)
    expected = [digital_expected(i) for i in range(8001)]
    wrong = [i for i, (a, b) in enumerate(zip(old.requests, expected)) if a != b]
    check(wrong == list(range(800, 8001, 800)),
          'stock reproduces the one-tick digital wrap defect at every 800 ticks')
    check(new.requests == expected and new.outputs == expected,
          'digital: 10 complete frames plus wrap, every bit exactly 50 ticks')
    check(new.r8(SCAN + 1) == 1 and not (new.calls.keys() & LOG_CALLS),
          'default mode initializes to Digital without interrupt-context logging')
    check(old.calls[0x0801CAA0] == 1,
          'stock default-mode initialization calls the task queue from the timer path')

    for seed in (49, 50, 749, 750, 799, 800, 801, 0xFFFFFFFF):
        m = ScanMachine(mod)
        m.w32(DIGITAL, seed)
        m.ticks(2)
        index = seed if seed < 800 else 0
        check(m.requests == [digital_expected(index), digital_expected(index + 1)],
              f'digital boundary / out-of-range counter {seed:#x} recovers correctly')

    old, new = ScanMachine(stock, mode=2), ScanMachine(mod, mode=2)
    old.ticks(6001)
    new.ticks(6001)
    expected = [(i // 6) & 1 for i in range(6001)]
    check(old.requests == new.requests == expected and new.outputs == expected,
          '825 Hz: 6001 ticks retain the stock six-tick half-cycle across phase wraps')
    check(old.calls[0x0801CAA0] == 6 and not (new.calls.keys() & LOG_CALLS),
          '825 Hz: six periodic stock logging/queue calls removed from timer path')
    check(new.instructions < old.instructions,
          '825 Hz: fewer executed instructions over the same waveform',
          f'{old.instructions} -> {new.instructions} (not a wall-clock timing measurement)')

    for state, enabled, mode in ((2, 1, 1), (2, 1, 2), (5, 0, 1), (5, 0, 2), (5, 1, 255)):
        m = ScanMachine(mod, mode, enabled, state)
        before = bytes(m.uc.mem_read(DIGITAL, 10))
        m.ticks(20)
        check(not m.requests and bytes(m.uc.mem_read(DIGITAL, 10)) == before,
              f'no modulation outside active SCAN: state={state}, enabled={enabled}, mode={mode}')

    m = ScanMachine(mod)
    m.ticks(17)
    m.call(0x0801458C)                    # real mode-change key handler
    start = len(m.requests)
    m.ticks(1001)
    check(m.r8(SCAN + 1) == 2 and m.requests[start:] == [(i // 6) & 1 for i in range(1001)]
          and m.r32(DIGITAL) == 17 and m.messages[-1:] == [0xA],
          'Digital -> 825 Hz routes on the next tick and preserves the digital cursor')
    m.call(0x0801458C)
    start = len(m.requests)
    m.ticks(100)
    check(m.r8(SCAN + 1) == 1 and m.requests[start:] == [digital_expected(i) for i in range(17, 117)],
          '825 Hz -> Digital resumes the saved pattern cursor')

    for mode, ticks in ((1, 17), (1, 67), (2, 8), (2, 14)):
        m = ScanMachine(mod, mode)
        m.ticks(ticks)
        m.call(0x0801456C)                # Back pauses the tone
        before, count = bytes(m.uc.mem_read(DIGITAL, 10)), len(m.requests)
        m.ticks(100)
        check(m.r8(SCAN) == 0 and m.r8(STATE) == 5 and m.carrier == 0
              and len(m.requests) == count and bytes(m.uc.mem_read(DIGITAL, 10)) == before,
              f'Back pauses mode {mode} at tick {ticks}, silences carrier, freezes counters')
        m.call(0x08014498, 1)             # resume through real enable setter
        m.ticks(1)
        check(m.carrier == m.requests[-1],
              f'resume mode {mode} at tick {ticks}: actual gate matches requested gate immediately')
        m.call(0x0801456C)
        m.call(0x0801456C)
        check(m.r8(STATE) == 2 and not m.carrier,
              f'second Back returns Home with mode {mode} stopped')

    for mode in (0, 2):
        m = ScanMachine(mod, mode)
        m.ticks(5000, IRQ)
        check(m.calls[0x080169A8] == 5 and m.calls[0x0800F9CC] == 1000
              and m.calls[0x080183CC] == 5000 and len(m.requests) == 5000
              and not (m.calls.keys() & LOG_CALLS),
              f'full TIM2 path mode {mode}: watchdog / 1000, backlight / 5, no SCAN logging')
        calls, count = m.calls.copy(), len(m.requests)
        m.pending = 0
        m.ticks(10, IRQ)
        check(m.calls == calls and len(m.requests) == count,
              f'TIM2 without pending interrupt does no work (mode {mode})')

    def region(data, start, end):
        off = struct.unpack_from('<I', data, 0x20)[0]
        return data[start - APP + off:end - APP + off]

    check(all(region(stock, a, b) == region(mod, a, b) for a, b in
              ((0x0801A60C, 0x0801A730), (0x08018370, 0x080183CC))),
          'carrier hardware routines and TIM2 interrupt body are byte-identical to stock')


def main():
    from lpm10a.image import require_stock
    import patches
    fw = Path(__file__).resolve().parent.parent
    original = Path(require_stock(str(fw / 'LPM-10A-TX_V2.0.7_260610.bin'))).read_bytes()
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else fw / f"LPM-10A-TX_{patches.VERSION.replace(' ', '')}.bin"
    failures = []

    def check(ok, label, detail=''):
        print(f"[{'ok' if ok else 'FAIL'}] {label}" + (f' -- {detail}' if detail else ''))
        if not ok:
            failures.append(label)

    run_checks(original, path.read_bytes(), check)
    print(f'{len(failures)} SCAN check(s) failed')
    return int(bool(failures))


if __name__ == '__main__':
    sys.exit(main())
