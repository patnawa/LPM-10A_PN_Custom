"""PN 1.19 strong-cap: the curve reaches 20 ms at the measured front-end saturation."""
import hashlib
import os
import struct
import unittest

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_PC, UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_LR, UC_ARM_REG_SP

from lpm10rx import symbols as S
from lpm10rx.container import unwrap
import strong_cap as sc
import smooth_gain as sg

HERE = os.path.dirname(os.path.abspath(__file__))
IMAGE = os.path.join(HERE, '..', 'experimental', 'APP_LPM-10RX_PN1.19-strong-cap.bin')
UPDATE = os.path.join(HERE, '..', 'experimental', 'APP_LPM-10RX_PN1.19-strong-cap-update.bin')
PARENT = os.path.join(HERE, '..', 'experimental', 'APP_LPM-10RX_PN1.18-rail-strong.bin')


def image():
    with open(IMAGE, 'rb') as f:
        return f.read()


def expected_gap(score):
    for a, b, ga, gb in zip(sc.SCORES, sc.SCORES[1:], sc.GAPS, sc.GAPS[1:]):
        if score < b:
            return ga - (score - a) * (ga - gb) // (b - a)
    return sc.GAPS[-1]


class StrongCapImage(unittest.TestCase):
    def test_only_the_last_table_span_changes(self):
        with open(PARENT, 'rb') as f:
            parent = f.read()
        data = image()
        self.assertEqual(hashlib.sha256(parent).hexdigest(), sc.PARENT_SHA256)
        changed = {S.APP_BASE + i for i in range(len(parent)) if data[i] != parent[i]}
        self.assertEqual(changed, {sc.TABLE + 16, sc.TABLE + 17})
        self.assertEqual(struct.unpack_from('<H', data, sc.TABLE + 16 - S.APP_BASE)[0], 16000)

    def test_update_container_carries_the_image(self):
        with open(UPDATE, 'rb') as f:
            name, raw = unwrap(f.read())
        self.assertEqual(raw, image())


class StrongCapCurve(unittest.TestCase):
    def gap_for(self, score, code=7):
        uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
        uc.mem_map(0x08000000, 0x20000)
        uc.mem_map(0x20000000, 0x10000)
        uc.mem_write(S.APP_BASE, image())
        uc.mem_write(0x2000006A, struct.pack('<H', code))
        uc.mem_write(0x2000006C, struct.pack('<H', 0))       # fresh start: no smoothing
        uc.mem_write(0x2000005D, bytes([0]))
        uc.reg_write(UC_ARM_REG_SP, 0x20001600)
        uc.reg_write(UC_ARM_REG_R0, score)
        uc.reg_write(UC_ARM_REG_LR, 0x0800A0A5)
        seen = {}

        def hook(uc, addr, size, ud):
            if addr == sg.PUBLISH:
                seen['gap'] = uc.reg_read(UC_ARM_REG_R1)
                uc.emu_stop()
        uc.hook_add(UC_HOOK_CODE, hook)
        uc.emu_start(sg.GAP_HELPER | 1, 0, count=400)
        return seen['gap']

    def test_saturation_and_beyond_give_the_fastest_rhythm(self):
        for score in (40000, 50000, 88000, 200000):
            self.assertEqual(self.gap_for(score), 20, score)

    def test_linear_region_unchanged_below_24000(self):
        for score in (0, 800, 2400, 7200, 13000, 24000):
            self.assertEqual(self.gap_for(score), expected_gap(score), score)
        self.assertEqual(self.gap_for(24000), 45)

    def test_on_the_cable_sounds_the_same_at_middle_and_maximum_knob(self):
        # measured on the cable: code 7 contrast ~35 000 (front end saturated), code 2 ~25 000 unclipped
        self.assertEqual(self.gap_for(25000, code=2), 20)     # 25 000 x 2.6 = 65 000 -> 20
        self.assertLessEqual(self.gap_for(35000, code=7), 28)  # 35 000 -> ~28
        self.assertEqual(self.gap_for(40000, code=7), 20)


if __name__ == '__main__':
    unittest.main()
