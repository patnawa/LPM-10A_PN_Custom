"""Execute real RX timer/AGC instructions; ADC/link and IRQ arrival are modeled.

The timed stream uses the documented Digital gain ratios, including for the
Analog control. It establishes ownership and response timing, not a new
physical gain calibration or measured CPU/interrupt deadlines.
"""
import struct
import unittest

from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_READ
from unicorn.arm_const import UC_ARM_REG_PRIMASK

import auto_range
import digital_gain_continuity
import gain_response
import sample_age_guard
import test_rx_auto_range_freshness as control
import test_rx_digital_strong_gain as stream
from lpm10rx import symbols
from lpm10rx.image import PatchError
from sampling_fixes import GATE_STATE
from verify_control import MODE
from verify_digital import ACTIVE, BUFFER


def candidate():
    img = digital_gain_continuity.build_candidate()
    sample_age_guard.install(img)
    gain_response.install(img)
    return img


class GainResponseStreams(unittest.TestCase):
    execute = stream.StrongGainStream.execute
    boundary = stream.StrongGainStream.boundary
    timers = stream.StrongGainStream.timers
    run_stream = stream.StrongGainStream.run_stream

    @classmethod
    def setUpClass(cls):
        cls.previous = bytes(digital_gain_continuity.build_candidate().data)
        cls.img = candidate()
        cls.data = bytes(cls.img.data)

    def test_strong_to_weak_recovers_within_one_second_in_both_modes(self):
        for mode in (0, 1):
            with self.subTest(mode=mode):
                row = self.run_stream(mode=mode, changes={}, end_ms=1800,
                    source_pp=lambda ms: 2400 if ms < 1000 else 800)
                self.assertEqual(row['transitions'], [(500, 7, 2), (1500, 2, 7)])
                self.assertGreater(row['final_grade'], 0)
                self.assertFalse(row['unowned_refreshes'])
                self.assertLess(row['max_quiet_ms'], 150)

    def test_pn123g_negative_control_reproduces_delayed_recovery(self):
        for mode in (0, 1):
            with self.subTest(mode=mode):
                row = self.run_stream(mode=mode, previous=True, changes={}, end_ms=3100,
                    source_pp=lambda ms: 2400 if ms < 1000 else 800)
                self.assertEqual(row['transitions'], [(500, 7, 2), (3000, 2, 7)])

    def test_near_boundary_static_inputs_do_not_hunt_in_both_modes(self):
        for mode in (0, 1):
            for amplitude, expected in ((1850, []), (1950, [(500, 7, 2)]),
                    (1170, []), (800, [])):
                with self.subTest(mode=mode, amplitude=amplitude):
                    row = self.run_stream(mode=mode, changes={}, end_ms=3300,
                                          source_pp=amplitude)
                    self.assertEqual(row['transitions'], expected)
                    self.assertFalse(row['unowned_refreshes'])

    def test_very_strong_input_steps_down_without_renewing_feedback(self):
        for mode in (0, 1):
            with self.subTest(mode=mode):
                row = self.run_stream(mode=mode, changes={}, end_ms=2900, source_pp=20000)
                self.assertEqual(row['transitions'], [(500, 7, 2), (1500, 2, 1), (2500, 1, 0)])
                self.assertFalse(row['unowned_refreshes'])

    def test_quiet_gate_and_manual_gain_controls_preserve_g_invariants(self):
        for mode in (0, 1):
            with self.subTest(mode=mode):
                quiet = self.run_stream(mode=mode, signal=False, end_ms=1800,
                                       changes={500: 2, 1000: 7, 1500: 2})
                self.assertFalse(quiet['edges'])
                self.assertFalse(quiet['unowned_refreshes'])
                self.assertEqual(quiet['final_beep'], 0)
                closed = self.run_stream(mode=mode, changes={500: 0})
                self.assertEqual(closed['final_beep'], 0)
                self.assertFalse([t for t, on in closed['edges'] if on and t >= 530])


class GainResponseInstructions(unittest.TestCase):
    execute = control.AutoRangeFreshness.execute
    boundary = control.AutoRangeFreshness.boundary
    timers = stream.StrongGainStream.timers

    @classmethod
    def setUpClass(cls):
        cls.img = candidate()
        cls.data = bytes(cls.img.data)
        cls.previous = bytes(digital_gain_continuity.build_candidate().data)

    def cpu(self, *, mode=0, level=7, last=7, hold=0, pp=1000, previous=False):
        c = control.GainControl(self.previous if previous else self.data)
        c.w8(MODE, mode)
        c.w16(0x20000068, 4060)
        c.w16(0x2000006A, 7)
        c.w8(GATE_STATE, 2)
        c.uc.mem_write(auto_range.STATE, bytes((level, 0, hold, last)))
        c.uc.mem_write(BUFFER, struct.pack('<64H', *([2048-pp//2, 2048+pp//2]*32)))
        c.w32(sample_age_guard.COMPLETED_VALID, 1)
        c.w32(sample_age_guard.COMPLETED_AT, 100000)
        c.w32(sample_age_guard.TIMER_COUNTER, 100000)
        return c

    def select(self, c, knob=7):
        self.execute(c, 0x0800A4FC, knob, budget=3000)
        self.assertEqual(c.read(auto_range.STATE+1), 0,
                         'normalizer reads driven gain as a zero-extended halfword')
        return c.read(auto_range.STATE)

    def test_incomplete_closed_pending_or_expired_windows_cannot_drive_gain(self):
        for mode in (0, 1):
            for field, value in ((sample_age_guard.COMPLETED_VALID, 0),
                    (GATE_STATE, 0), (GATE_STATE, 1), (GATE_STATE, 3),
                    (0x20000049, 1), (0x20000049, 2)):
                with self.subTest(mode=mode, field=hex(field), value=value):
                    c = self.cpu(mode=mode, pp=2400)
                    (c.w32 if field == sample_age_guard.COMPLETED_VALID else c.w8)(field, value)
                    self.assertEqual(self.select(c), 7)
            limit = (sample_age_guard.DIGITAL_MAX_AGE_TICKS,
                     sample_age_guard.ANALOG_MAX_AGE_TICKS)[mode]
            for elapsed, wanted in ((limit, 2), (limit+1, 7)):
                for stamp in (100000, 0xfffffff0):
                    with self.subTest(mode=mode, elapsed=elapsed, stamp=stamp):
                        c = self.cpu(mode=mode, pp=2400)
                        c.w32(sample_age_guard.COMPLETED_AT, stamp)
                        c.w32(sample_age_guard.TIMER_COUNTER, (stamp+elapsed)&0xffffffff)
                        self.assertEqual(self.select(c), wanted)

    def test_exact_hysteresis_knob_ceiling_alias_and_mains_bypass(self):
        for mode in (0, 1):
            for level, pp, wanted in ((7,1898,7),(7,1900,2),(2,450,2),(2,448,7),
                                      (0,2400,0),(1,2400,0),(2,2400,1)):
                c = self.cpu(mode=mode, level=level, pp=pp)
                self.assertEqual(self.select(c), wanted)
            c = self.cpu(mode=mode, level=2, last=2, pp=100)
            self.assertEqual(self.select(c, knob=2), 2)
            c = self.cpu(mode=mode, pp=2400)
            self.assertEqual(self.select(c, knob=3), 2)
        c = self.cpu(mode=2, pp=2400, hold=1)
        self.assertEqual(self.select(c), 7)
        self.assertEqual(c.read(auto_range.STATE+2), 1)
        self.assertEqual(self.select(c, knob=2), 2)

    def test_hold_skips_all_48_sample_reads_and_preserves_abi_and_interrupt_state(self):
        metrics = {}
        for previous in (True, False):
            c = self.cpu(level=2, hold=1, previous=previous)
            reads, instructions = [], []
            h1 = c.uc.hook_add(UC_HOOK_MEM_READ,
                lambda uc,a,addr,size,value,user: reads.append(addr), begin=BUFFER, end=BUFFER+95)
            h2 = c.uc.hook_add(UC_HOOK_CODE,
                lambda uc,addr,size,user: instructions.append(addr))
            try:
                self.assertEqual(self.select(c), 2)
            finally:
                c.uc.hook_del(h1)
                c.uc.hook_del(h2)
            self.assertEqual(c.read(auto_range.STATE+2), 0)
            self.assertEqual(c.uc.reg_read(UC_ARM_REG_PRIMASK), 0)
            metrics[previous] = (len(reads), len(instructions))
        self.assertEqual(metrics[True][0], 48)
        self.assertEqual(metrics[False][0], 0)
        self.assertLess(metrics[False][1], metrics[True][1]//4)
        self.__class__.hold_metrics = metrics

    def test_partial_new_gain_buffer_cannot_trigger_a_second_change(self):
        for mode, irqs in ((0, 6000), (1, 200)):
            for previous in (True, False):
                with self.subTest(mode=mode, previous=previous):
                    c = stream.GainStreamCPU(self.previous if previous else self.data, mode=mode)
                    self.boundary(c)
                    c.uc.mem_write(BUFFER, struct.pack('<64H', *([848, 3248]*32)))
                    c.w32(sample_age_guard.COMPLETED_VALID, 1)
                    self.assertEqual(self.select(c), 2)
                    self.boundary(c)
                    self.timers(c, irqs)
                    self.assertEqual(c.read(ACTIVE), 1)
                    # Isolate freshness from elapsed hold callbacks. The tail
                    # still contains high-gain samples; the new prefix does not.
                    c.w8(auto_range.STATE+2, 0)
                    self.assertEqual(self.select(c), 1 if previous else 2)
                    if not previous:
                        self.assertEqual(c.read(GATE_STATE), 2)
                        self.assertEqual(c.read(sample_age_guard.COMPLETED_VALID, 4), 0)


class GainResponseBuild(unittest.TestCase):
    def test_only_four_entry_bytes_change_below_parent_end_and_build_is_deterministic(self):
        img = digital_gain_continuity.build_candidate()
        sample_age_guard.install(img)
        before = bytes(img.data)
        meta = gain_response.install(img)
        changes = {symbols.APP_BASE+i for i,(a,b) in enumerate(zip(before,img.data)) if a != b}
        self.assertTrue(changes)
        self.assertLessEqual(changes, set(range(0x0800A500,0x0800A504)))
        self.assertEqual(len(img.data)-len(before), meta['helper_bytes'])
        self.assertEqual(meta['persistent_ram_bytes'], 0)
        self.assertEqual(meta['additional_stack_bytes'], 0)
        self.assertEqual(bytes(img.data), bytes(candidate().data))

    def test_requires_freshness_and_rejects_reapplication_without_mutation(self):
        img = digital_gain_continuity.build_candidate()
        before = bytes(img.data)
        with self.assertRaises(PatchError):
            gain_response.install(img)
        self.assertEqual(bytes(img.data), before)
        sample_age_guard.install(img)
        gain_response.install(img)
        before = bytes(img.data)
        log = list(img.log)
        with self.assertRaises(PatchError):
            gain_response.install(img)
        self.assertEqual(bytes(img.data), before)
        self.assertEqual(img.log, log)

    def test_corrupted_parent_contracts_reject_before_any_mutation(self):
        for address in (0x0800CFC8,0x0800A500,0x0800D088,auto_range.CURVE_LITERAL):
            with self.subTest(address=hex(address)):
                img = digital_gain_continuity.build_candidate()
                sample_age_guard.install(img)
                img.data[address-symbols.APP_BASE] ^= 1
                before, log = bytes(img.data), list(img.log)
                with self.assertRaises(PatchError):
                    gain_response.install(img)
                self.assertEqual(bytes(img.data), before)
                self.assertEqual(img.log, log)


if __name__ == '__main__':
    unittest.main()
