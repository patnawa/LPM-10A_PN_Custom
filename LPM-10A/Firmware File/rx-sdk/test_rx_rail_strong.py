"""PN 1.18 rail-strong: the publisher maps the 'uncertain' interval to the fastest rhythm."""
import hashlib
import os
import struct
import unittest

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_PC, UC_ARM_REG_R1, UC_ARM_REG_LR, UC_ARM_REG_SP

from lpm10rx import symbols as S
from lpm10rx.container import unwrap
import rail_strong as rs
import release_hold as rh

HERE = os.path.dirname(os.path.abspath(__file__))
IMAGE = os.path.join(HERE, '..', 'experimental', 'APP_LPM-10RX_PN1.18-rail-strong.bin')
UPDATE = os.path.join(HERE, '..', 'experimental', 'APP_LPM-10RX_PN1.18-rail-strong-update.bin')
PARENT = os.path.join(HERE, '..', 'experimental', 'APP_LPM-10RX_PN1.17-smooth-gain.bin')
RETURN = 0x0800A0A5
MODE, INTERVAL, RECENT, GATE = 0x20000048, 0x2000005D, 0x2000006C, 0x200000EF


def image():
    with open(IMAGE, 'rb') as f:
        return f.read()


class RailStrongImage(unittest.TestCase):
    def test_only_the_publisher_helper_differs_from_pn117(self):
        with open(PARENT, 'rb') as f:
            parent = f.read()
        data = image()
        self.assertEqual(hashlib.sha256(parent).hexdigest(), rs.PARENT_SHA256)
        self.assertEqual(len(data), len(parent))
        changed = {S.APP_BASE + i for i in range(len(parent)) if data[i] != parent[i]}
        self.assertTrue(changed <= set(range(rs.PUBLISHER, rs.PUBLISHER + 96)), sorted(hex(a) for a in changed)[:6])

    def test_update_container_carries_the_image(self):
        with open(UPDATE, 'rb') as f:
            name, raw = unwrap(f.read())
        self.assertEqual(raw, image())


class RailStrongPublisher(unittest.TestCase):
    def publish(self, r1, mode=0, recent=800, interval=40):
        uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
        uc.mem_map(0x08000000, 0x20000)
        uc.mem_map(0x20000000, 0x10000)
        uc.mem_write(S.APP_BASE, image())
        uc.mem_write(MODE, bytes([mode, 0]))
        uc.mem_write(INTERVAL, bytes([interval]))
        uc.mem_write(RECENT, struct.pack('<H', recent))
        uc.mem_write(GATE, bytes([2]))
        uc.reg_write(UC_ARM_REG_SP, 0x20001600)
        uc.reg_write(UC_ARM_REG_R1, r1)
        uc.reg_write(UC_ARM_REG_LR, RETURN)
        uc.hook_add(UC_HOOK_CODE, lambda uc, a, s, u: uc.emu_stop() if a == RETURN & ~1 else None)
        uc.emu_start(rh.PUBLISH | 1, 0, count=100)
        self.assertEqual(uc.reg_read(UC_ARM_REG_PC), RETURN & ~1)
        return uc.mem_read(INTERVAL, 1)[0], struct.unpack('<H', uc.mem_read(RECENT, 2))[0]

    def test_uncertain_becomes_the_fastest_normal_rhythm(self):
        self.assertEqual(self.publish(1, mode=0, interval=40), (rs.FASTEST_MS, 800))
        self.assertEqual(self.publish(1, mode=1, interval=90), (rs.FASTEST_MS, 800))

    def test_other_values_unchanged(self):
        self.assertEqual(self.publish(55, interval=0), (55, 800))
        self.assertEqual(self.publish(0, mode=0, recent=800, interval=40), (40, 660))
        self.assertEqual(self.publish(0, mode=1, recent=600, interval=33), (33, 560))

    def test_interval_1_is_never_stored_so_the_100ms_pattern_cannot_start(self):
        for r1 in range(0, 120):
            interval, _ = self.publish(r1, interval=40)
            self.assertNotEqual(interval, 1, r1)


if __name__ == '__main__':
    unittest.main()
