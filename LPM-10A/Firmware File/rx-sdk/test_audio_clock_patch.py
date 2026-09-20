"""Exact-parent scope and integer countdown/wrap contracts for PN 1.13."""
import hashlib
from pathlib import Path
from types import SimpleNamespace
import unittest

from unicorn.arm_const import UC_ARM_REG_PRIMASK

import audio_clock_fixes as patch
from lpm10rx.image import Image, PatchError
import test_rx_followup as followup
from test_rx_followup import GATE_STATE, TIM5
from test_rx_tracking_streams import StreamCPU
from verify_control import MODE
from verify_digital import ACTIVE

FW = Path(__file__).resolve().parents[1] / 'experimental'
SHA = '2cafd8a234a9b372a4d09c4969b28c8c35a45f05b72c57d2248d39f22cf7373b'


class AudioClockPatch(unittest.TestCase):
    execute = followup.Followup.execute

    @classmethod
    def setUpClass(cls):
        cls.img = Image(str(FW / 'APP_LPM-10RX_PN1.12-overload.bin'))
        cls.parent = bytes(cls.img.data)
        patch.apply(cls.img)
        cls.data = bytes(cls.img.data)

    def test_exact_delivered_bytes_and_confined_changes(self):
        self.assertEqual(hashlib.sha256(self.data).hexdigest(), SHA)
        self.assertEqual(self.data, (FW / 'APP_LPM-10RX_PN1.13-audio-clock.bin').read_bytes())
        self.assertEqual(len(self.data), len(self.parent))
        changed = [0x08006800+i for i, pair in enumerate(zip(self.parent, self.data))
                   if pair[0] != pair[1]]
        self.assertEqual(len(changed), 105)
        self.assertTrue(all(any(lo <= a < hi for lo, hi in patch.GUARDS) for a in changed))
        self.assertEqual(self.img.audio_clock['persistent_ram_bytes'], 0)
        self.assertEqual(self.img.audio_clock['additional_stack_bytes'], 0)

    def test_wrong_parent_rejects_without_mutation(self):
        img = SimpleNamespace(data=bytearray(self.data))
        before = bytes(img.data)
        with self.assertRaises(PatchError):
            patch.apply(img)
        self.assertEqual(bytes(img.data), before)

    def test_all_counter_values_saturate_and_preserve_mask_and_abi(self):
        c = StreamCPU(self.data)
        pairs = {(b, g) for b in range(256) for g in (0, 1, 20, 160, 255)}
        pairs |= {(b, g) for b in (0, 1, 2, 100, 255) for g in range(256)}
        for mask in (0, 1):
            for counter in (40, 41):
                for beep, gap in sorted(pairs):
                    c.w32(patch.COUNTER, counter)
                    c.w8(patch.BEEP, beep)
                    c.w8(patch.GAP, gap)
                    c.uc.reg_write(UC_ARM_REG_PRIMASK, mask)
                    self.execute(c, patch.HELPER, budget=100)
                    expected_beep = max(0, beep-1) if counter == 40 else beep
                    expected_gap = max(0, gap-1) if counter == 40 and expected_beep == 0 else gap
                    self.assertEqual((c.read(patch.BEEP), c.read(patch.GAP)),
                                     (expected_beep, expected_gap))
                    self.assertEqual(c.uc.reg_read(UC_ARM_REG_PRIMASK), mask)
                    self.assertEqual(c.read(patch.COUNTER, 4), counter)

    def test_actual_tim5_dispatch_at_uint32_wrap(self):
        for mode in (0, 1, 2):
            c = StreamCPU(self.data)
            c.w8(MODE, mode)
            c.w8(GATE_STATE, 2)
            c.w8(ACTIVE, 2)
            c.w8(patch.BEEP, 200)
            c.w8(patch.GAP, 3)
            c.w32(patch.COUNTER, 0xffffffb0)
            wanted = 200
            for offset in range(1, 161):
                now = (0xffffffb0 + offset) & 0xffffffff
                if now % 40 == 0:
                    wanted -= 1
                self.execute(c, TIM5, budget=4000)
                self.assertEqual(c.read(patch.COUNTER, 4), now)
                self.assertEqual((c.read(patch.BEEP), c.read(patch.GAP)), (wanted, 3))


if __name__ == '__main__':
    unittest.main()
