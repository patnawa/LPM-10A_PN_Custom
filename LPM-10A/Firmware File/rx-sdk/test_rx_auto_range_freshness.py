"""Real TIM1 gain changes against main/ADC ownership; no hardware timing claim."""
import hashlib
from pathlib import Path
import struct
import unittest

from unicorn import UC_HOOK_CODE
from unicorn.arm_const import (UC_ARM_REG_C1_C0_2, UC_ARM_REG_FPEXC,
                               UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_PRIMASK,
                               UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_SP)

import auto_range
import auto_range_freshness as fix
from lpm10rx.image import Image, PatchError
import profiles
import rx_patches
import test_rx_analog_feedback as analog
import test_rx_robust
from test_rx_followup import ANALYZERS, GATE_STATE, GRADE, INDICES, SPEAKER, TIM5
from verify_control import BEEP, MODE, SP, STOP, TICK
from verify_digital import ACTIVE, BUFFER, GAP, GATE, RECENT, pattern


def parent():
    img = Image(str(Path(__file__).resolve().parent.parent / 'APP_LPM-10RX_V3.0.0_260416.bin'))
    wanted = profiles.PROFILES['pn1.23'].patch_ids()
    for patch in rx_patches.REGISTRY:
        if patch.pid in wanted:
            patch(img)
    return img


class GainControl(test_rx_robust._FastControl):
    """Run the real AGC and TIM1; replace only ADC conversion with a knob value."""
    MOCK_ENTRIES = test_rx_robust._FastControl.MOCK_ENTRIES - {0x080084D8}
    knob_raw = 1160

    def hook(self, uc, addr, size, user):
        if addr == 0x08007320:
            if uc.reg_read(UC_ARM_REG_R0) != 3:
                raise AssertionError('AGC must sample knob channel 3')
            uc.mem_write(uc.reg_read(UC_ARM_REG_R1), struct.pack('<5H', *([self.knob_raw]*5)))
            uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
        elif addr == 0x080072A4:
            if getattr(self, 'pause_adc', False):
                return
            self.sample_reads = getattr(self, 'sample_reads', 0)+1
            uc.reg_write(UC_ARM_REG_R0, 1234)
            uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
        else:
            super().hook(uc, addr, size, user)


class AutoRangeFreshness(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.img = parent()
        cls.previous = bytes(cls.img.data)
        fix.apply(cls.img)
        cls.data = bytes(cls.img.data)

    execute = test_rx_robust.Robust.execute
    boundary = test_rx_robust.Robust.boundary

    def cpu(self, *, previous=False, mode=0):
        c = GainControl(self.previous if previous else self.data)
        c.uc.reg_write(UC_ARM_REG_C1_C0_2, 0xF00000)
        c.uc.reg_write(UC_ARM_REG_FPEXC, 0x40000000)
        c.w8(MODE, mode)
        c.w16(GATE, 4060)
        c.w16(GATE+2, 7)
        c.w8(GATE_STATE, 2)
        c.uc.mem_write(auto_range.STATE, bytes([7, 0, 0, 7]))
        return c

    def tick(self, c, knob=2):
        c.knob_raw = knob*580
        c.w32(TICK, 499)
        self.execute(c, 0x0800A97C, stack=SP-0x500, budget=10000)
        self.assertEqual(c.read(TICK, 4), 500)

    def interrupt(self, c, entry, point, event):
        fired = []
        def pause(uc, address, size, user):
            if address == point:
                fired.append(address)
                uc.emu_stop()
        hook = c.uc.hook_add(UC_HOOK_CODE, pause)
        c.uc.reg_write(UC_ARM_REG_SP, SP)
        c.uc.reg_write(UC_ARM_REG_LR, STOP | 1)
        try:
            c.uc.emu_start(entry | 1, STOP, count=100000)
        finally:
            c.uc.hook_del(hook)
        self.assertEqual(fired, [point])
        self.assertEqual(c.uc.reg_read(UC_ARM_REG_PRIMASK), 0)
        saved = c.uc.context_save()
        event(c)
        c.uc.context_restore(saved)
        c.pause_adc = False
        c.uc.emu_start(point | 1, STOP, count=100000)
        self.assertEqual(c.uc.reg_read(UC_ARM_REG_PC), STOP)
        self.assertEqual(c.uc.reg_read(UC_ARM_REG_SP), SP)

    def test_parent_reproduces_old_window_publication_after_gain_change(self):
        for mode, samples in ((0, pattern(low=1000, high=1300)), (1, analog.sine(300))):
            # Curve entry, after loading the driven gain, and inside Analog DFT.
            points = (0x0800A048, 0x0800CF2E) + ((0x0800B4AC,) if mode == 1 else ())
            for point in points:
                for previous in (True, False):
                    with self.subTest(mode=mode, point=hex(point), previous=previous):
                        c = self.cpu(previous=previous, mode=mode)
                        c.w8(ACTIVE, 0)
                        c.uc.mem_write(BUFFER, struct.pack(f'<{len(samples)}H', *samples))
                        self.interrupt(c, ANALYZERS[mode], point, self.tick)
                        self.assertEqual(c.read(auto_range.STATE), 2)
                        if previous:
                            self.assertGreater(c.read(GRADE), 0, 'PN 1.23 publishes the old-gain window')
                            self.assertGreater(c.read(RECENT, 2), 500)
                        else:
                            self.assertEqual((c.read(GRADE), c.read(RECENT, 2), c.read(GATE_STATE)), (0, 0, 0))
                            self.boundary(c)
                            self.assertEqual((c.read(ACTIVE), c.read(GATE_STATE)), (1, 2))
                            self.assertEqual([c.read(i) for i in INDICES], [0, 0, 0])

    def test_automatic_down_up_and_knob_changes_invalidate_before_gpio(self):
        for mode in (0, 1):
            for level, last, knob, pp, wanted in ((7, 7, 7, 2400, 2), (2, 7, 7, 100, 7),
                                                  (7, 7, 2, 500, 2)):
                c = self.cpu(mode=mode)
                c.uc.mem_write(auto_range.STATE, bytes([level, 0, 0, last]))
                c.uc.mem_write(BUFFER, struct.pack('<48H', *([2048-pp//2, 2048+pp//2]*24)))
                observed = []
                def gpio(uc, address, size, user):
                    if address in (0x08008170, 0x08008184):
                        observed.append(c.read(GATE_STATE))
                hook = c.uc.hook_add(UC_HOOK_CODE, gpio)
                try:
                    self.tick(c, knob)
                finally:
                    c.uc.hook_del(hook)
                self.assertEqual(c.read(auto_range.STATE), wanted)
                self.assertTrue(observed)
                self.assertEqual(set(observed), {0})

    def test_gain_irq_at_each_unmasked_analyzer_instruction_blocks_stale_feedback(self):
        # Trace real DSP instructions, including the Analog DFT. Each unique
        # unmasked instruction gets one TIM1 interruption on its first visit;
        # loop iteration schedules and NVIC priorities are not modeled.
        for mode, samples in ((0, pattern(low=1000, high=1300)), (1, analog.sine(300))):
            def ready():
                c = self.cpu(mode=mode)
                c.w8(ACTIVE, 0)
                c.uc.mem_write(BUFFER, struct.pack(f'<{len(samples)}H', *samples))
                return c

            points = set()
            c = ready()
            def trace(uc, address, size, user):
                if not uc.reg_read(UC_ARM_REG_PRIMASK):
                    points.add(address)
            hook = c.uc.hook_add(UC_HOOK_CODE, trace)
            try:
                self.execute(c, ANALYZERS[mode])
            finally:
                c.uc.hook_del(hook)
            self.assertGreater(c.read(GRADE), 0, 'fixture must publish without an interrupt')
            self.assertGreater(len(points), 150, 'trace must cover the real analyzer')

            for point in sorted(points):
                with self.subTest(mode=mode, point=hex(point)):
                    c = ready()
                    self.interrupt(c, ANALYZERS[mode], point, self.tick)
                    self.assertEqual((c.read(auto_range.STATE), c.read(GATE_STATE)), (2, 0))
                    # An interrupt after the publisher committed may leave its
                    # grade until the boundary, but must prevent new feedback.
                    self.execute(c, SPEAKER, budget=5000)
                    self.assertEqual(c.read(BEEP), 0, 'stale acquisition started feedback')
                    self.boundary(c)
                    self.assertEqual((c.read(GRADE), c.read(RECENT, 2),
                                      c.read(ACTIVE), c.read(GATE_STATE)), (0, 0, 1, 2))
                    self.assertEqual([c.read(i) for i in INDICES], [0, 0, 0])

    def test_unchanged_effective_gain_preserves_acquisition_and_key_beep(self):
        for level, last, knob, hold in ((7, 7, 7, 0), (2, 2, 3, 0), (2, 7, 7, 4)):
            c = self.cpu()
            c.uc.mem_write(auto_range.STATE, bytes([level, 0, hold, last]))
            c.uc.mem_write(BUFFER, struct.pack('<48H', *([1500, 2100]*24)))
            c.w8(ACTIVE, 1)
            c.w8(INDICES[0], 43)
            c.w8(BEEP, 100)
            c.w8(GAP, 70)
            self.tick(c, knob)
            self.assertEqual((c.read(auto_range.STATE), c.read(GATE_STATE), c.read(ACTIVE),
                              c.read(INDICES[0]), c.read(BEEP), c.read(GAP)),
                             (level, 2, 1, 43, 99, 70))

    def test_mains_amplitude_and_cleared_buffer_do_not_change_gain(self):
        for samples in ([0]*48, [4095]*24+[0]*24, [2048]*24+[0]*24):
            for previous in (True, False):
                c = self.cpu(previous=previous, mode=2)
                c.uc.mem_write(BUFFER, struct.pack('<48H', *samples))
                self.tick(c, 7)
                expected = 2 if previous and max(samples)-min(samples) >= 1900 else 7
                self.assertEqual(c.read(auto_range.STATE), expected)
                self.assertEqual(c.read(GATE_STATE), 2)

    def test_gain_irq_during_adc_sample_defers_sampler_reset_to_main(self):
        for mode in (0, 1, 2):
            c = self.cpu(mode=mode)
            c.w8(ACTIVE, 1)
            c.w8(INDICES[mode], 12)
            c.w8(0x200000EE, 6)
            c.w32(0x20000100, (19, 12, 61)[mode])
            c.pause_adc = True
            self.interrupt(c, TIM5, 0x080072A4, self.tick)
            self.assertEqual(c.read(GATE_STATE), 0)
            self.assertEqual(c.read(ACTIVE), 1)
            self.assertGreaterEqual(c.read(INDICES[mode]), 12)
            self.boundary(c)
            self.assertEqual([c.read(i) for i in INDICES], [0, 0, 0])
            self.assertEqual((c.read(ACTIVE), c.read(GATE_STATE)), (1, 2))

    def test_changed_gain_requires_complete_fresh_acquisition(self):
        for mode, length in ((0, 48), (1, 64), (2, 64)):
            c = self.cpu(mode=mode)
            c.w8(ACTIVE, 1)
            c.w8(INDICES[mode], length-1)
            c.uc.mem_write(BUFFER, struct.pack('<64H', *([4095]*64)))
            self.tick(c)
            self.boundary(c)
            for _ in range(600):
                if not c.read(ACTIVE):
                    break
                c.w32(0x20000100, (19, 12, 61)[mode])
                self.execute(c, TIM5, budget=4000)
            self.assertEqual(c.read(ACTIVE), 0)
            self.assertEqual(c.sample_reads, length*(5 if mode == 0 else 1))
            self.assertEqual(bytes(c.uc.mem_read(BUFFER, 2*length)), struct.pack(f'<{length}H', *([1234]*length)))

    def test_scope_exact_parent_and_unchanged_size(self):
        self.assertEqual(hashlib.sha256(self.previous).hexdigest(), fix.PARENT_SHA256)
        self.assertEqual(len(self.previous), len(self.data))
        changed = {0x08006800+i for i, (a, b) in enumerate(zip(self.previous, self.data)) if a != b}
        self.assertTrue(changed)
        self.assertTrue(changed <= set(range(fix.HELPER, fix.HELPER+fix.SIZE)))
        self.assertEqual(self.img.auto_range_freshness['helper_bytes'], 184)
        with self.assertRaises(PatchError):
            fix.apply(self.img)
        img = parent()
        img.data[100] ^= 1
        with self.assertRaises(PatchError):
            fix.apply(img)

    def test_reproducible_candidate_has_distinct_identity_without_changing_latest(self):
        import version_tag
        candidate = fix.build_candidate()
        self.assertEqual(candidate.version_tag, 'PN1.23F')
        self.assertEqual(profiles.LATEST, 'pn1.23')
        expected = bytearray(self.data)
        offset = version_tag.VERSION_STRING-0x08006800
        expected[offset:offset+version_tag.SLOT] = b'PN1.23F\0'
        self.assertEqual(candidate.data, expected)


if __name__ == '__main__':
    unittest.main()
