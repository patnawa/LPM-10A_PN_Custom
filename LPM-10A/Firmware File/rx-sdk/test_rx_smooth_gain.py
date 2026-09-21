"""PN 1.17 smooth-gain: level-3 gain fix and half-step rhythm smoothing, on the CPU model."""
import hashlib
import os
import struct
import unittest

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_PC, UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_LR, UC_ARM_REG_SP

from lpm10rx import symbols as S
from lpm10rx.container import unwrap
import smooth_gain as sg
import gain_norm

HERE = os.path.dirname(os.path.abspath(__file__))
IMAGE = os.path.join(HERE, '..', 'experimental', 'APP_LPM-10RX_PN1.17-smooth-gain.bin')
UPDATE = os.path.join(HERE, '..', 'experimental', 'APP_LPM-10RX_PN1.17-smooth-gain-update.bin')
PARENT = os.path.join(HERE, '..', 'experimental', 'APP_LPM-10RX_PN1.16-release-hold.bin')
GAIN_SELECT = 0x0800A4FC
GPIO_CLEAR, GPIO_SET = 0x08008170, 0x08008184
PUBLISH = sg.PUBLISH
RETURN = 0x0800B001


def image():
    with open(IMAGE, 'rb') as f:
        return f.read()


def machine():
    uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
    uc.mem_map(0x08000000, 0x20000)
    uc.mem_map(0x20000000, 0x10000)
    uc.mem_map(0x40000000, 0x30000)
    uc.mem_write(S.APP_BASE, image())
    uc.reg_write(UC_ARM_REG_SP, 0x20001600)
    uc.reg_write(UC_ARM_REG_LR, RETURN)
    return uc


def expected_gap(score):
    for a, b, ga, gb in zip(gain_norm.SCORES, gain_norm.SCORES[1:], gain_norm.GAPS, gain_norm.GAPS[1:]):
        if score < b:
            return ga - (score - a) * (ga - gb) // (b - a)
    return gain_norm.GAPS[-1]


class SmoothGainImage(unittest.TestCase):
    def test_changes_are_confined_to_the_three_sites_and_the_appended_code(self):
        with open(PARENT, 'rb') as f:
            parent = f.read()
        data = image()
        self.assertEqual(hashlib.sha256(parent).hexdigest(), sg.PARENT_SHA256)
        self.assertEqual(len(data), len(parent) + 32 + 160)
        changed = {S.APP_BASE + i for i in range(len(parent)) if data[i] != parent[i]}
        allowed = set(range(sg.GAIN_SELECT_SITE, sg.GAIN_SELECT_SITE + 8)) | {sg.MULT_TABLE + 3} | set(range(sg.GAP_HELPER, sg.GAP_HELPER + 4))
        self.assertTrue(changed <= allowed, sorted(hex(a) for a in changed - allowed)[:8])
        self.assertEqual(data[sg.MULT_TABLE - S.APP_BASE:sg.MULT_TABLE - S.APP_BASE + 8], bytes([200, 92, 26, 26, 11, 11, 11, 10]))

    def test_update_container_carries_the_image(self):
        with open(UPDATE, 'rb') as f:
            name, raw = unwrap(f.read())
        self.assertEqual(raw, image())


class GainSelectFix(unittest.TestCase):
    def pins_for(self, level):
        uc = machine()
        uc.reg_write(UC_ARM_REG_R0, level)
        writes = []

        def hook(uc, addr, size, ud):
            if addr in (GPIO_CLEAR, GPIO_SET):
                writes.append(('set' if addr == GPIO_SET else 'clear', uc.reg_read(UC_ARM_REG_R1)))
                uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
            elif addr == RETURN & ~1:
                uc.emu_stop()
        uc.hook_add(UC_HOOK_CODE, hook)
        uc.emu_start(GAIN_SELECT | 1, 0, count=400)
        self.assertEqual(uc.reg_read(UC_ARM_REG_PC), RETURN & ~1)
        # final state of PB12 (0x1000), PB13 (0x2000), PB14 (0x4000)
        state = {}
        for action, mask in writes:
            state[mask] = action
        return tuple(state[m] for m in (0x1000, 0x2000, 0x4000))

    def test_level_3_now_writes_level_2_pattern(self):
        self.assertEqual(self.pins_for(3), self.pins_for(2))
        self.assertNotEqual(self.pins_for(3), self.pins_for(0))

    def test_other_levels_are_unchanged(self):
        # stock: bit -> pin, level 0 forced to PB12/PB13 set, PB14 clear (== the level 3 pattern)
        self.assertEqual(self.pins_for(0), ('set', 'set', 'clear'))
        self.assertEqual(self.pins_for(1), ('set', 'clear', 'clear'))
        self.assertEqual(self.pins_for(2), ('clear', 'set', 'clear'))
        self.assertEqual(self.pins_for(4), ('clear', 'clear', 'set'))
        self.assertEqual(self.pins_for(7), ('set', 'set', 'set'))
        self.assertEqual(len({self.pins_for(l) for l in (1, 2, 4, 5, 6, 7)}), 6)


class SmoothCurve(unittest.TestCase):
    def gap_for(self, score, code=7, recent=800, published=0):
        uc = machine()
        uc.mem_write(0x2000006A, struct.pack('<H', code))
        uc.mem_write(0x2000006C, struct.pack('<H', recent))
        uc.mem_write(0x2000005D, bytes([published]))
        uc.reg_write(UC_ARM_REG_R0, score)
        seen = {}

        def hook(uc, addr, size, ud):
            if addr == PUBLISH:
                seen['gap'] = uc.reg_read(UC_ARM_REG_R1)
                uc.emu_stop()
        uc.hook_add(UC_HOOK_CODE, hook)
        uc.emu_start(sg.GAP_HELPER | 1, 0, count=400)
        self.assertIn('gap', seen)
        return seen['gap']

    def test_fresh_start_takes_the_target_directly(self):
        for score in (0, 800, 5000, 30000, 88000):
            self.assertEqual(self.gap_for(score, recent=300, published=0), expected_gap(score))
            self.assertEqual(self.gap_for(score, recent=800, published=0), expected_gap(score))
            self.assertEqual(self.gap_for(score, recent=800, published=1), expected_gap(score))   # after 'uncertain'

    def test_active_rhythm_moves_half_way_toward_the_target(self):
        # published 90 ms, target 20 ms (score 88000) -> 55; target 110 (score 0) from 20 -> 65
        self.assertEqual(self.gap_for(88000, published=90), 90 + (20 - 90) // 2)
        self.assertEqual(self.gap_for(0, published=20), 20 + (110 - 20) // 2)
        # converge: repeated updates approach the target
        g = 90
        for _ in range(6):
            g = self.gap_for(88000, published=g)
        self.assertLessEqual(g - 20, 5)

    def test_half_step_below_the_deadband_keeps_the_rhythm(self):
        target = expected_gap(30000)            # ~42
        self.assertEqual(self.gap_for(30000, published=target + 4), target + 4)   # half step 2 < 3
        self.assertEqual(self.gap_for(30000, published=target + 6), target + 3)   # half step 3 applies

    def test_code_3_is_scaled_like_code_2(self):
        self.assertEqual(self.gap_for(13000, code=3), self.gap_for(13000, code=2))
        self.assertEqual(self.gap_for(13000, code=2), expected_gap(13000 * 26 // 10))

    def test_noisy_low_gain_windows_shift_the_rhythm_half_as_much(self):
        # measured at code 1: targets alternating between ~90 and ~20 ms
        seq = [90, 20, 90, 20, 90, 20]
        g = 55
        out = []
        for target_gap in seq:
            score = 0 if target_gap == 90 else 88000
            g = self.gap_for(score, code=7, published=g)
            out.append(g)
        self.assertLess(max(out) - min(out), 60)     # raw swing was 70


if __name__ == '__main__':
    unittest.main()
