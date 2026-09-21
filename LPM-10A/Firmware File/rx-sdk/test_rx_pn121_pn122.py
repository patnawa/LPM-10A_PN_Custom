"""PN 1.21 fast-update (overlap 40/8) and PN 1.22 auto-range (AGC step-down), on the CPU model."""
import os
import struct
import unittest

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_PC, UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_LR, UC_ARM_REG_SP

from lpm10rx import symbols as S
import digital_overlap
import auto_range as ar
import fast_update as fu

HERE = os.path.dirname(os.path.abspath(__file__))
IMG121 = os.path.join(HERE, '..', 'experimental', 'APP_LPM-10RX_PN1.21-fast-update.bin')
IMG122 = os.path.join(HERE, '..', 'experimental', 'APP_LPM-10RX_PN1.22-auto-range.bin')
BUFFER, INDEX, ACTIVE = 0x2000006E, 0x2000005B, 0x20000008
GAIN_SELECT = 0x0800A4FC
GPIO_CLEAR, GPIO_SET = 0x08008170, 0x08008184
RETURN = 0x0800B001


def machine(path):
    uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
    uc.mem_map(0x08000000, 0x20000)
    uc.mem_map(0x20000000, 0x10000)
    uc.mem_map(0x40000000, 0x30000)
    with open(path, 'rb') as f:
        uc.mem_write(S.APP_BASE, f.read())
    uc.reg_write(UC_ARM_REG_SP, 0x20001600)
    uc.reg_write(UC_ARM_REG_LR, RETURN)
    return uc


class FastUpdate(unittest.TestCase):
    def test_overlap_keeps_40_samples_and_arms_8(self):
        uc = machine(IMG121)
        snapshot = 0x20001000
        samples = [1000 + i for i in range(48)]
        uc.mem_write(snapshot, b''.join(struct.pack('<H', s) for s in samples))
        uc.mem_write(BUFFER, bytes(96))
        uc.reg_write(UC_ARM_REG_R0, BUFFER + 96)
        uc.reg_write(UC_ARM_REG_R1, snapshot + 96)
        uc.hook_add(UC_HOOK_CODE, lambda uc, a, s, u: uc.emu_stop() if a == RETURN & ~1 else None)
        uc.emu_start(digital_overlap.HELPER | 1, 0, count=2000)
        self.assertEqual(uc.reg_read(UC_ARM_REG_PC), RETURN & ~1)
        kept = [struct.unpack('<H', uc.mem_read(BUFFER + 2 * i, 2))[0] for i in range(48)]
        self.assertEqual(kept[:40], samples[8:48])          # newest 40 moved to the front
        self.assertEqual(kept[40:], [0] * 8)                # 8 slots left for new samples
        self.assertEqual(uc.mem_read(INDEX, 1)[0], 40)
        self.assertEqual(uc.mem_read(ACTIVE, 1)[0], 1)

    def test_evaluation_period_is_40_ms(self):
        self.assertEqual(fu.NEW * 5, 40)


class AutoRange(unittest.TestCase):
    def tick(self, uc, knob, pp):
        """One AGC tick: buffer holds a signal of the given peak-to-peak; returns (driven level, pins)."""
        mid = 2048
        samples = [mid + (pp // 2 if i % 2 else -(pp // 2)) for i in range(48)]
        uc.mem_write(BUFFER, b''.join(struct.pack('<H', s) for s in samples))
        uc.reg_write(UC_ARM_REG_R0, knob)
        uc.reg_write(UC_ARM_REG_SP, 0x20001600)
        uc.reg_write(UC_ARM_REG_LR, RETURN)
        writes = {}

        def hook(uc, addr, size, ud):
            if addr in (GPIO_CLEAR, GPIO_SET):
                writes[uc.reg_read(UC_ARM_REG_R1)] = 'set' if addr == GPIO_SET else 'clear'
                uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
            elif addr == RETURN & ~1:
                uc.emu_stop()
        h = uc.hook_add(UC_HOOK_CODE, hook)
        uc.emu_start(GAIN_SELECT | 1, 0, count=3000)
        uc.hook_del(h)
        self.assertEqual(uc.reg_read(UC_ARM_REG_PC), RETURN & ~1)
        state = uc.mem_read(ar.STATE, 4)
        return state[0], tuple(writes.get(m) for m in (0x1000, 0x2000, 0x4000)), state

    def test_first_tick_follows_the_knob_and_level_3_maps_to_2(self):
        uc = machine(IMG122)
        level, pins, _ = self.tick(uc, 7, 500)
        self.assertEqual(level, 7)
        level, pins3, _ = self.tick(uc, 3, 500)
        self.assertEqual(level, 2)
        _, pins2, _ = self.tick(uc, 2, 500)
        self.assertEqual(pins3, pins2)

    def test_saturation_steps_down_then_holds(self):
        uc = machine(IMG122)
        self.tick(uc, 7, 500)                       # first tick: level 7
        level, _, st = self.tick(uc, 7, 2400)       # saturated: 7 -> 2
        self.assertEqual((level, st[2]), (2, 4))
        for _ in range(4):                          # hold 4 ticks even if still saturated
            level, _, _ = self.tick(uc, 7, 2400)
            self.assertEqual(level, 2)
        level, _, _ = self.tick(uc, 7, 2400)        # then 2 -> 1
        self.assertEqual(level, 1)
        for _ in range(4):
            self.tick(uc, 7, 2400)
        level, _, _ = self.tick(uc, 7, 2400)        # 1 -> 0
        self.assertEqual(level, 0)
        for _ in range(5):
            level, _, _ = self.tick(uc, 7, 2400)
        self.assertEqual(level, 0)                  # never below 0

    def test_recovery_steps_back_up_to_the_knob(self):
        uc = machine(IMG122)
        self.tick(uc, 6, 500)
        self.tick(uc, 6, 2400)                      # 6 -> 2, hold 4
        for _ in range(4):
            self.tick(uc, 6, 100)
        level, _, _ = self.tick(uc, 6, 100)         # after the hold: 2 -> knob (6)
        self.assertEqual(level, 6)
        for _ in range(6):
            level, _, _ = self.tick(uc, 6, 100)
        self.assertEqual(level, 6)                  # never above the knob

    def test_in_between_amplitude_keeps_the_level(self):
        uc = machine(IMG122)
        self.tick(uc, 5, 500)
        self.tick(uc, 5, 2400)                      # -> 2
        for _ in range(5):
            self.tick(uc, 5, 1000)
        level, _, _ = self.tick(uc, 5, 1000)        # 450 <= pp < 1900: stay at 2
        self.assertEqual(level, 2)

    def test_knob_change_resets_to_the_knob(self):
        uc = machine(IMG122)
        self.tick(uc, 7, 500)
        self.tick(uc, 7, 2400)                      # -> 2
        level, _, st = self.tick(uc, 5, 2400)       # knob moved: follow it at once
        self.assertEqual((level, st[2]), (5, 0))

    def test_normaliser_reads_the_driven_level(self):
        with open(IMG122, 'rb') as f:
            data = f.read()
        self.assertEqual(data[ar.CURVE_LITERAL - S.APP_BASE:ar.CURVE_LITERAL - S.APP_BASE + 4], ar.STATE.to_bytes(4, 'little'))
        # the byte after the level is never written, so the halfword read equals the level
        uc = machine(IMG122)
        self.tick(uc, 7, 2400)
        self.tick(uc, 7, 2400)
        self.assertEqual(uc.mem_read(ar.STATE + 1, 1)[0], 0)


if __name__ == '__main__':
    unittest.main()
