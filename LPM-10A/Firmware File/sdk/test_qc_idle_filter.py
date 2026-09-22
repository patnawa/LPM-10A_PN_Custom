"""QC no-cable synthetic noise replay through the actual Thumb acquisition path.

The count trace is a deterministic stimulus, not a captured hardware trace.
It tests whether near-baseline jitter can incorrectly light a passing pin.
"""
import contextlib
import io
import struct
import unittest

import qc_classic
import qc_idle_filter
from test_qc_continuity import Harness
import test_qc_continuity as continuity


class QCIdleFilter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import length_integrity
        with contextlib.redirect_stdout(io.StringIO()):
            cls.parent = qc_classic.build_candidate()
            cls.parent_data = bytes(cls.parent.data)
            cls.img = length_integrity.build_candidate()
        cls.data = bytes(cls.img.finalize().data)
        cls.state = cls.img.qc['state']
        cls.info = cls.img.qc
        cls.state_size = 64
        cls.filter = cls.img.qc_idle_filter

    faults = continuity.QCContinuity.faults
    test_calibration_preemption_preserves_timer_owner = continuity.QCContinuity.test_calibration_preemption_at_each_unmasked_poll_instruction_respects_timer_owner
    test_rapid_reentry_discards_in_flight_sample = continuity.QCContinuity.test_rapid_exit_and_reentry_keep_timer_ownership_and_discard_the_old_sample

    def now(self, h):
        return list(h.s.uc.mem_read(self.state + 32, 8))

    def scene(self, *, parent=False, baselines=None):
        h = Harness(self.parent_data if parent else self.data, baselines=baselines)
        h.enter()
        return h

    def sweep(self, h, values):
        h.values = values
        self.samples(h, 8)
        h.s.call(self.img.qc_classic['ui']['draw'])
        return self.now(h)

    def samples(self, h, count):
        target = len(h.reads) + count
        for _ in range(count + 60):
            self.assertLessEqual(h.poll(), 1)
            if len(h.reads) == target:
                return
        self.fail('QC acquisition did not advance')

    def test_isolated_near_baseline_dip_does_not_light_unplugged_pin(self):
        h = self.scene()
        h.values = [1000] * 8
        self.samples(h, 8)
        h.values[2] = 993
        self.samples(h, 8)
        self.assertNotEqual(h.read(self.state + 32 + 2), 1,
                            'one 7-count synthetic no-cable dip falsely lights pin 3 green')

    def test_negative_control_parent_lights_a_pin_after_one_raw_dip(self):
        h = self.scene(parent=True)
        h.values = [1000] * 8
        self.samples(h, 8)
        h.values[2] = 993
        self.samples(h, 8)
        self.assertEqual(self.now(h)[2], 1)
        h.s.call(self.parent.qc_classic['ui']['draw'])
        self.assertEqual(h.s.fb[79 + 27 * 5 + 3][205], 0x07E0)

    def test_repeated_isolated_spikes_across_pins_never_show_green(self):
        h = self.scene()
        leds = []
        def led(uc):
            leds.append(h.s.arg(0))
            return False
        h.s.at[0x08010F94] = led
        for pin in (2, 7, 0, 4, 1, 6, 3, 5):
            self.sweep(h, [1000] * 8)
            values = [1000] * 8
            values[pin] = 993 if pin % 2 else 900
            self.assertNotIn(1, self.sweep(h, values))
            self.assertNotIn(1, self.sweep(h, values), 'two spikes are insufficient')
            for row in range(8):
                self.assertNotEqual(h.s.fb[79 + 27 * row + 3][205], 0x07E0)
        self.assertNotIn(2, leds, 'physical status LED must never report all pins passing')

    def test_stable_connection_qualifies_on_third_sweep_and_led_waits_for_every_pin(self):
        h = self.scene()
        leds = []
        def led(uc):
            leds.append(h.s.arg(0))
            return False
        h.s.at[0x08010F94] = led
        self.assertNotIn(1, self.sweep(h, [900] * 8))
        self.assertNotIn(1, self.sweep(h, [900] * 8))
        self.assertNotIn(2, leds)
        self.assertEqual(self.sweep(h, [900] * 8), [1] * 8)
        self.assertEqual(leds[-1], 2)
        self.assertEqual(h.delays, [10] * 24)
        self.assertTrue(all(timeout == 1 for timeout in h.timeouts))
        self.assertEqual(h.reads[-1][2] - h.reads[7][2], 176)

    def test_open_invalid_and_check_clear_immediately_and_recovery_requalifies(self):
        h = self.scene()
        for _ in range(3):
            self.sweep(h, [900] * 8)
        values = [1000, 0, 65535, 1007, 900, 900, 900, 900]
        self.assertEqual(self.sweep(h, values), [2, 3, 3, 3, 1, 1, 1, 1])
        for _ in range(2):
            self.assertEqual(self.sweep(h, [900] * 8), [2, 3, 3, 3, 1, 1, 1, 1])
        self.assertEqual(self.sweep(h, [900] * 8), [1] * 8)

    def test_seven_count_boundary_is_preserved_for_sustained_connections(self):
        h = self.scene()
        values = [0, 65535, 994, 993, 1000, 1006, 1007, 900]
        for _ in range(3):
            self.sweep(h, values)
        self.assertEqual(self.now(h), [3, 3, 2, 1, 2, 2, 3, 1])

    def test_raw_fault_history_survives_unconfirmed_passing_observations(self):
        h = self.scene()
        self.sweep(h, [900] * 8)
        values = [900] * 8
        values[2] = 1000
        self.sweep(h, values)
        self.sweep(h, [900] * 8)
        self.sweep(h, values)
        faults = struct.unpack('<8H', h.s.uc.mem_read(self.state + 16, 16))
        self.assertEqual(faults, (0, 0, 2, 0, 0, 0, 0, 0))

    def test_reentry_cannot_inherit_old_confirmation(self):
        h = self.scene()
        for _ in range(3):
            self.sweep(h, [900] * 8)
        h.press(0, 3)
        h.enter()
        self.assertNotIn(1, self.sweep(h, [900] * 8))
        self.assertNotIn(1, self.sweep(h, [900] * 8))
        self.assertEqual(self.sweep(h, [900] * 8), [1] * 8)

    def test_successful_init_cannot_inherit_old_confirmation(self):
        from test_qc_classic import QCClassic
        from test_qc_continuity import BASE
        h = self.scene()
        for _ in range(3):
            self.sweep(h, [900] * 8)
        h.values = [1100] * 8
        self.assertEqual(QCClassic.initialize(self, h)[0], 0)
        self.assertEqual(struct.unpack('<8H', h.s.uc.mem_read(BASE, 16)), (1100,) * 8)
        self.assertNotIn(1, self.sweep(h, [900] * 8))
        self.assertNotIn(1, self.sweep(h, [900] * 8))
        self.assertEqual(self.sweep(h, [900] * 8), [1] * 8)

    def test_actual_startup_clears_filter_ram_and_preserves_canaries(self):
        from unicorn.arm_const import UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_SP
        from test_qc_continuity import STACK
        from thai.engine import MAGIC, MAIN
        h = Harness(self.data)
        state = self.filter['state']
        size = self.filter['state_size']
        arena_end = max(address + count for address, count in self.img.ram_allocs)
        h.s.uc.mem_write(state, bytes([0xA5]) * size)
        before = bytes(h.s.uc.mem_read(state - 4, 4))
        h.s.uc.mem_write(arena_end, bytes([0xAC]) * 16)
        h.s.uc.reg_write(UC_ARM_REG_SP, STACK)
        h.s.uc.reg_write(UC_ARM_REG_LR, MAGIC | 1)
        h.s.uc.emu_start(MAIN | 1, MAIN + 4, count=100_000)
        self.assertEqual(h.s.uc.reg_read(UC_ARM_REG_PC), MAIN + 4)
        self.assertEqual(h.s.uc.reg_read(UC_ARM_REG_SP), STACK)
        self.assertEqual(bytes(h.s.uc.mem_read(state, size)), bytes(size))
        self.assertEqual(bytes(h.s.uc.mem_read(state - 4, 4)), before)
        self.assertEqual(bytes(h.s.uc.mem_read(arena_end, 16)), bytes([0xAC]) * 16)

    def test_repeated_unplugged_noise_after_successful_init_keeps_screen_pins_off(self):
        from test_qc_classic import QCClassic
        from test_qc_continuity import BASE
        h = self.scene()
        h.values = [1000] * 8
        self.assertEqual(QCClassic.initialize(self, h)[0], 0)
        self.assertEqual(struct.unpack('<8H', h.s.uc.mem_read(BASE, 16)), (1000,) * 8)
        # The owner reports random screen pins even after unplugged Init.
        # Replay dips after a real successful calibration, not an old baseline.
        for pin in (7, 1, 5, 0, 6, 3, 2, 4):
            self.sweep(h, [1000] * 8)
            values = [1000] * 8
            values[pin] = 993
            self.assertNotIn(1, self.sweep(h, values))
            self.assertNotIn(1, self.sweep(h, values))
            for row in range(8):
                self.assertNotEqual(h.s.fb[79 + 27 * row + 3][205], 0x07E0)

    def test_changed_classification_seam_fails_closed_before_allocation(self):
        from lpm10a.image import PatchError
        with contextlib.redirect_stdout(io.StringIO()):
            img = qc_classic.build_candidate()
        img.data[img.f(qc_idle_filter.CLASSIFY_SITE)] ^= 1
        before = (img.cave_ptr, tuple(img.ram_allocs), bytes(img.data))
        with self.assertRaises(PatchError):
            qc_idle_filter.install(img)
        self.assertEqual((img.cave_ptr, tuple(img.ram_allocs), bytes(img.data)), before)


if __name__ == '__main__':
    unittest.main()
