"""PN 1.16 release-hold: the shared publisher, executed on the CPU model."""
import hashlib
import os
import struct
import unittest

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_PC, UC_ARM_REG_R1, UC_ARM_REG_LR, UC_ARM_REG_SP

from lpm10rx import symbols as S
from lpm10rx.container import unwrap
import release_hold as rh

HERE = os.path.dirname(os.path.abspath(__file__))
IMAGE = os.path.join(HERE, '..', 'experimental', 'APP_LPM-10RX_PN1.16-release-hold.bin')
UPDATE = os.path.join(HERE, '..', 'experimental', 'APP_LPM-10RX_PN1.16-release-hold-update.bin')
PARENT = os.path.join(HERE, '..', 'experimental', 'APP_LPM-10RX_PN1.15-gain-norm.bin')
RETURN = 0x0800A0A5
MODE, REQUEST, INTERVAL, RECENT, GATE = 0x20000048, 0x20000049, 0x2000005D, 0x2000006C, 0x200000EF


def image():
    with open(IMAGE, 'rb') as f:
        return f.read()


class ReleaseHoldImage(unittest.TestCase):
    def test_only_the_publisher_slot_and_the_appended_helper_differ(self):
        with open(PARENT, 'rb') as f:
            parent = f.read()
        data = image()
        self.assertEqual(hashlib.sha256(parent).hexdigest(), rh.PARENT_SHA256)
        self.assertEqual(len(data), len(parent) + 96)
        changed = {S.APP_BASE + i for i in range(len(parent)) if data[i] != parent[i]}
        self.assertTrue(changed <= set(range(rh.PUBLISH, rh.PUBLISH_END)), sorted(hex(a) for a in changed)[:6])

    def test_update_container_carries_the_image(self):
        with open(UPDATE, 'rb') as f:
            name, raw = unwrap(f.read())
        self.assertEqual(raw, image())


class ReleaseHoldPublisher(unittest.TestCase):
    def publish(self, r1, mode=0, recent=800, interval=40, gate=2, request=0):
        uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
        uc.mem_map(0x08000000, 0x20000)
        uc.mem_map(0x20000000, 0x10000)
        uc.mem_write(S.APP_BASE, image())
        uc.mem_write(MODE, bytes([mode, request]))
        uc.mem_write(INTERVAL, bytes([interval]))
        uc.mem_write(RECENT, struct.pack('<H', recent))
        uc.mem_write(GATE, bytes([gate]))
        uc.reg_write(UC_ARM_REG_SP, 0x20001600)
        uc.reg_write(UC_ARM_REG_R1, r1)
        uc.reg_write(UC_ARM_REG_LR, RETURN)
        uc.hook_add(UC_HOOK_CODE, lambda uc, a, s, u: uc.emu_stop() if a == RETURN & ~1 else None)
        uc.emu_start(rh.PUBLISH | 1, 0, count=100)
        self.assertEqual(uc.reg_read(UC_ARM_REG_PC), RETURN & ~1, 'publisher must return to its caller')
        return uc.mem_read(INTERVAL, 1)[0], struct.unpack('<H', uc.mem_read(RECENT, 2))[0]

    def test_accepted_window_publishes_interval_and_refreshes_recent(self):
        self.assertEqual(self.publish(55, recent=120, interval=0), (55, 800))
        self.assertEqual(self.publish(1, mode=1, recent=0, interval=0), (1, 800))    # uncertain counts as accepted

    def test_rejected_digital_window_keeps_interval_and_clamps_recent_to_660(self):
        self.assertEqual(self.publish(0, mode=0, recent=800, interval=40), (40, 660))
        self.assertEqual(self.publish(0, mode=0, recent=700, interval=40), (40, 660))
        self.assertEqual(self.publish(0, mode=0, recent=600, interval=40), (40, 600))   # already below the hold
        self.assertEqual(self.publish(0, mode=0, recent=0, interval=0), (0, 0))

    def test_rejected_analog_window_clamps_recent_to_560(self):
        self.assertEqual(self.publish(0, mode=1, recent=600, interval=33), (33, 560))
        self.assertEqual(self.publish(0, mode=1, recent=520, interval=33), (33, 520))

    def test_pending_mode_change_or_closed_gate_publish_nothing(self):
        self.assertEqual(self.publish(55, request=1, recent=100, interval=7), (7, 100))
        self.assertEqual(self.publish(55, gate=1, recent=100, interval=7), (7, 100))
        self.assertEqual(self.publish(0, gate=0, recent=800, interval=7), (7, 800))

    def test_two_consecutive_digital_misses_release_within_240_ms(self):
        # accepted at t=0 (RECENT 800); first rejected update at 80 ms clamps to 660;
        # by the second rejected update at 160 ms RECENT has run down to 580; at 240 ms it is 500 -> silent.
        interval, recent = self.publish(0, mode=0, recent=800 - 80, interval=40)
        self.assertEqual((interval, recent), (40, 660))
        interval, recent = self.publish(0, mode=0, recent=660 - 80, interval=40)
        self.assertEqual((interval, recent), (40, 580))
        self.assertLessEqual(580 - 500, 80)


if __name__ == '__main__':
    unittest.main()
