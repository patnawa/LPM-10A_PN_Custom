"""PN 1.15 gain-norm: the knob-gain normaliser in front of the strength curve, on the CPU model."""
import hashlib
import os
import struct
import unittest

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_PC, UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_LR, UC_ARM_REG_SP

from lpm10rx import symbols as S
from lpm10rx.container import unwrap
import gain_norm

HERE = os.path.dirname(os.path.abspath(__file__))
IMAGE = os.path.join(HERE, '..', 'experimental', 'APP_LPM-10RX_PN1.15-gain-norm.bin')
UPDATE = os.path.join(HERE, '..', 'experimental', 'APP_LPM-10RX_PN1.15-gain-norm-update.bin')
PARENT = os.path.join(HERE, '..', 'experimental', 'APP_LPM-10RX_PN1.14-mode-tone.bin')
PUBLISH = 0x08009F20
RETURN = 0x0800A0A4          # not used: we stop at publish


def image():
    with open(IMAGE, 'rb') as f:
        return f.read()


def expected_gap(score):
    """Reference implementation of the PN 1.8 curve with the PN 1.15 endpoints."""
    for a, b, ga, gb in zip(gain_norm.SCORES, gain_norm.SCORES[1:], gain_norm.GAPS, gain_norm.GAPS[1:]):
        if score < b:
            return ga - (score - a) * (ga - gb) // (b - a)
    return gain_norm.GAPS[-1]


class GainNormImage(unittest.TestCase):
    def test_changes_are_the_entry_the_table_and_the_appended_helper(self):
        with open(PARENT, 'rb') as f:
            parent = f.read()
        data = image()
        self.assertEqual(hashlib.sha256(parent).hexdigest(), gain_norm.PARENT_SHA256)
        self.assertEqual(len(data), len(parent) + 64)
        changed = {S.APP_BASE + i for i in range(len(parent)) if data[i] != parent[i]}
        allowed = set(range(gain_norm.GAP_HELPER, gain_norm.GAP_HELPER + 4)) | set(range(gain_norm.TABLE, gain_norm.TABLE + 20))
        self.assertTrue(changed <= allowed, sorted(hex(a) for a in changed - allowed)[:8])

    def test_update_container_carries_the_image(self):
        with open(UPDATE, 'rb') as f:
            container = f.read()
        name, raw = unwrap(container)
        self.assertEqual(raw, image())


class GainNormCurve(unittest.TestCase):
    def gap_for(self, score, code, recent=0, published=0):
        data = image()
        uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
        uc.mem_map(0x08000000, 0x20000)
        uc.mem_map(0x20000000, 0x10000)
        uc.mem_write(S.APP_BASE, data)
        uc.mem_write(0x2000006A, struct.pack('<H', code))
        uc.mem_write(0x2000006C, struct.pack('<H', recent))       # RECENT: <=500 disables the 3 ms deadband
        uc.mem_write(0x2000005D, bytes([published]))
        uc.reg_write(UC_ARM_REG_SP, 0x20001600)
        uc.reg_write(UC_ARM_REG_R0, score)
        uc.reg_write(UC_ARM_REG_LR, 0x0800A0A5)
        seen = {}

        def hook(uc, addr, size, ud):
            if addr == PUBLISH:
                seen['gap'] = uc.reg_read(UC_ARM_REG_R1)
                uc.emu_stop()
        uc.hook_add(UC_HOOK_CODE, hook)
        uc.emu_start(gain_norm.GAP_HELPER | 1, 0, count=400)
        self.assertIn('gap', seen, 'curve helper must reach the publisher')
        return seen['gap']

    def test_code_7_uses_the_new_endpoints_unscaled(self):
        for score in (0, 400, 800, 1600, 2400, 5000, 7200, 15000, 24000, 50000, 88000, 200000):
            self.assertEqual(self.gap_for(score, 7), expected_gap(score), score)

    def test_scores_are_multiplied_by_the_measured_gain_step(self):
        for code, x10 in enumerate(gain_norm.MULT_X10):
            for score in (100, 1700, 3700, 13000, 32000):
                self.assertEqual(self.gap_for(score, code), expected_gap(score * x10 // 10), (code, score))

    def test_one_position_sounds_the_same_at_every_knob_step(self):
        # contrast medians measured at one fixed position on 2026-09-21 per gain code
        measured = {0: 1692, 1: 3712, 2: 13009, 3: 1708, 4: 31982, 5: 30547, 6: 32179, 7: 34060}
        gaps = {code: self.gap_for(score, code) for code, score in measured.items()}
        self.assertLessEqual(max(gaps.values()) - min(gaps.values()), 3, gaps)
        self.assertLess(max(gaps.values()), 45)          # clearly on the fast side of the curve

    def test_out_of_range_code_leaves_the_score_alone(self):
        self.assertEqual(self.gap_for(3712, 9), expected_gap(3712))

    def test_floor_is_110_ms_and_ceiling_20_ms(self):
        self.assertEqual(self.gap_for(0, 7), 110)
        self.assertEqual(self.gap_for(10 ** 6, 7), 20)


if __name__ == '__main__':
    unittest.main()
