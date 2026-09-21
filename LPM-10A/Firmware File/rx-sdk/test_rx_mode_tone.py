"""PN 1.14 mode-tone: the appended speaker-cadence helper, executed on the CPU model."""
import hashlib
import os
import struct
import unittest

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_PC, UC_ARM_REG_R0, UC_ARM_REG_LR, UC_ARM_REG_SP

from lpm10rx import symbols as S
from lpm10rx.container import unwrap
import mode_tone

HERE = os.path.dirname(os.path.abspath(__file__))
IMAGE = os.path.join(HERE, '..', 'experimental', 'APP_LPM-10RX_PN1.14-mode-tone.bin')
UPDATE = os.path.join(HERE, '..', 'experimental', 'APP_LPM-10RX_PN1.14-mode-tone-update.bin')
PARENT = os.path.join(HERE, '..', 'experimental', 'APP_LPM-10RX_PN1.12-overload.bin')
SPEAKER_TICK_MODE0 = 0x08007724
SPEAKER_TICK = 0x08007508
HELPER = S.APP_BASE + S.APP_SIZE          # appended right after the stock-sized image
SKIP = mode_tone.DISPATCH_END


def image():
    with open(IMAGE, 'rb') as f:
        return f.read()


class ModeToneImage(unittest.TestCase):
    def test_only_the_dispatch_and_the_appended_helper_differ_from_pn112(self):
        with open(PARENT, 'rb') as f:
            parent = f.read()
        data = image()
        self.assertEqual(hashlib.sha256(parent).hexdigest(), mode_tone.PARENT_SHA256)
        self.assertEqual(len(data), S.APP_SIZE + 64)
        changed = [S.APP_BASE + i for i in range(S.APP_SIZE) if data[i] != parent[i]]
        self.assertTrue(all(mode_tone.DISPATCH <= a < mode_tone.DISPATCH_END for a in changed), changed[:5])
        # the scatter-load init data that ends the stock image is untouched
        self.assertEqual(data[S.APP_SIZE - 0x18:S.APP_SIZE], parent[S.APP_SIZE - 0x18:])

    def test_update_container_carries_the_longer_image(self):
        with open(UPDATE, 'rb') as f:
            container = f.read()
        name, raw = unwrap(container)
        self.assertEqual(raw, image())
        self.assertEqual(struct.unpack_from('<I', container, 0x24)[0], S.APP_SIZE + 64)


class ModeToneHelper(unittest.TestCase):
    """Run the helper from the dispatch entry with a given tick/mode/keep_alive and
    record which speaker routine it reaches (stubbed) before it rejoins the handler."""

    def run_helper(self, tick, mode, keep_alive):
        data = image()
        uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
        uc.mem_map(0x08000000, 0x20000)
        uc.mem_map(0x20000000, 0x10000)
        uc.mem_write(S.APP_BASE, data)
        uc.mem_write(0x20000048, bytes([mode]))
        uc.mem_write(0x2000010C, bytes([keep_alive]))
        uc.mem_write(0x20000100, struct.pack('<I', tick))
        uc.reg_write(UC_ARM_REG_SP, 0x20001600)
        uc.reg_write(UC_ARM_REG_R0, tick)          # `ldr r0, [r0]` at 0x0800AC4E already ran
        calls = []

        def hook(uc, addr, size, ud):
            if addr in (SPEAKER_TICK_MODE0, SPEAKER_TICK):
                calls.append((addr, uc.reg_read(UC_ARM_REG_R0)))
                uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))   # stub: return at once
            if addr == SKIP:
                uc.emu_stop()
        uc.hook_add(UC_HOOK_CODE, hook)
        uc.emu_start(mode_tone.DISPATCH | 1, 0, count=200)
        self.assertEqual(uc.reg_read(UC_ARM_REG_PC), SKIP, 'helper must rejoin the handler at the sampler section')
        return calls

    def test_digital_flips_every_8_irqs(self):
        for tick in range(0, 64):
            calls = self.run_helper(tick, 0, 30)
            self.assertEqual([c[0] for c in calls], [SPEAKER_TICK_MODE0] if tick % 8 == 0 else [], tick)

    def test_analog_flips_every_16_irqs(self):
        for tick in range(0, 64):
            calls = self.run_helper(tick, 1, 12)
            self.assertEqual([c[0] for c in calls], [SPEAKER_TICK_MODE0] if tick % 16 == 0 else [], tick)

    def test_mains_unchanged_every_8_irqs_with_keep_alive_argument(self):
        for tick in range(0, 32):
            calls = self.run_helper(tick, 2, 77)
            self.assertEqual(calls, [(SPEAKER_TICK, 77)] if tick % 8 == 0 else [], tick)

    def test_confirmation_beep_chirps_toward_the_mode(self):
        # first half of a 100 ms key beep (keep_alive > 50): the other mode's cadence
        self.assertEqual([c[0] for c in self.run_helper(8, 0, 90)], [])                   # Digital starts low (16)
        self.assertEqual([c[0] for c in self.run_helper(16, 0, 90)], [SPEAKER_TICK_MODE0])
        self.assertEqual([c[0] for c in self.run_helper(8, 1, 90)], [SPEAKER_TICK_MODE0])  # Analog starts high (8)
        # second half (keep_alive <= 50): the mode's own cadence
        self.assertEqual([c[0] for c in self.run_helper(8, 0, 50)], [SPEAKER_TICK_MODE0])
        self.assertEqual([c[0] for c in self.run_helper(8, 1, 50)], [])
        self.assertEqual([c[0] for c in self.run_helper(16, 1, 50)], [SPEAKER_TICK_MODE0])

    def test_tracing_pulses_never_reach_the_chirp_half(self):
        # Digital pulses start at 30 ms, Analog at 12 ms: both below the 50 ms threshold
        for ka in (0, 12, 30, 50):
            self.assertEqual([c[0] for c in self.run_helper(8, 0, ka)], [SPEAKER_TICK_MODE0], ka)
            self.assertEqual([c[0] for c in self.run_helper(8, 1, ka)], [], ka)


if __name__ == '__main__':
    unittest.main()
