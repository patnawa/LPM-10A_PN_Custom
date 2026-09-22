"""Classic QC behavior through real keys, timer acquisition and GUI dispatch.

The shared harness models elapsed RTOS time and external TIM8 pulses. The
candidate's ARM instructions perform selection, measurement, classification,
calibration, queue dispatch, drawing and session ownership checks.
"""
import contextlib
import io
import struct
import unittest

from unicorn.arm_const import UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_SP

import test_qc_continuity as continuity
from test_qc_continuity import Harness, BASE, FLAGS, STACK, STATE
from test_qc_calibration import COMMAND, HANDLER, SAVE, HOME_MESSAGE, SETTINGS
from thai.engine import MAGIC, MAIN


class QCClassic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import qc_classic
        import qc_continuity
        with contextlib.redirect_stdout(io.StringIO()):
            cls.img = qc_classic.build_candidate()
        cls.data = bytes(cls.img.finalize().data)
        cls.info = cls.img.qc
        cls.classic = cls.img.qc_classic
        cls.state_size = qc_continuity.STATE_SIZE

    # These contracts concern the acquisition loop and ownership, and remain
    # applicable when the screen/control policy returns to the classic UI.
    scene = continuity.QCContinuity.scene
    mode = continuity.QCContinuity.mode
    now = continuity.QCContinuity.now
    faults = continuity.QCContinuity.faults
    samples = continuity.QCContinuity.samples
    test_transient_raw_failure_is_recorded = continuity.QCContinuity.test_one_bad_raw_count_then_good_retains_only_that_pin_history
    test_rapid_reentry_cannot_publish_the_previous_visit_sample = continuity.QCContinuity.test_rapid_exit_and_reentry_keep_timer_ownership_and_discard_the_old_sample
    test_calibration_preemption_preserves_timer_ownership = continuity.QCContinuity.test_calibration_preemption_at_each_unmasked_poll_instruction_respects_timer_owner

    def initialize(self, h):
        """Deliver the command posted by an actual Right hold to the CNT task."""
        commands, saved, requests = [], [], []

        def command(uc):
            commands.append(tuple(h.s.arg(i) for i in range(3)))
            h.s.ret(0)
            return True

        def save(uc):
            saved.append(bytes(uc.mem_read(h.s.arg(0), 16)))
            return False  # Keep the real baseline-to-settings copy.

        def home(uc):
            requests.append(h.s.arg(0))
            h.s.ret(0)
            return True

        h.s.at[0x0800BCE8], h.s.at[SAVE], h.s.at[HOME_MESSAGE] = command, save, home
        h.press(5, 8)
        self.assertEqual(commands, [(0, 0, 0)])
        h.s.w8(COMMAND, commands[0][0])
        result = h.s.call(HANDLER, COMMAND)
        h.s.drain()
        return result, saved, requests

    def test_entry_starts_and_keeps_acquiring_past_twenty_seconds_and_tick_wrap(self):
        for tick in (0, 0xFFFFFFE0):
            with self.subTest(tick=tick):
                h = Harness(self.data)
                h.s.vals['tick'] = tick
                h.enter()
                self.samples(h, 8)
                for elapsed in (20_001, 60_000, 3_600_000):
                    h.advance(elapsed)
                    self.assertEqual(h.poll(), 1,
                                     'QC acquisition must continue without a session time limit')
                    self.assertEqual(self.mode(h), 1)
                    self.assertEqual(h.timeouts[-1], 1)
                self.assertEqual([pin for pin, _, _ in h.reads], list(range(8))+[0, 1, 2])
                # A full tick-counter cycle must not restart the entry-only
                # 50 ms settling delay once this visit has already sampled.
                h.s.vals['tick'] = (h.read(self.info['state']+4, 4)+1) & 0xFFFFFFFF
                self.assertEqual(h.poll(), 1)

    def test_short_ok_and_right_do_not_stop_restart_or_clear_measurements(self):
        h = self.scene()
        h.values[2] = 1000
        self.samples(h, 8)
        h.values[2] = 900
        self.samples(h, 8)
        q = self.info['state']
        for key in (4, 5, 4, 5):
            with self.subTest(key=key):
                before = bytes(h.s.uc.mem_read(q, self.state_size))
                pending = h.press(key)
                self.assertFalse(any(mid in (0x3E, 0x3F) for mid, _ in pending))
                self.assertEqual(bytes(h.s.uc.mem_read(q, self.state_size)), before)
                self.assertEqual(h.poll(), 1)
                self.assertEqual(self.mode(h), 1)
                self.assertEqual(self.faults(h)[2], 1)
        payload = struct.pack('<I', h.read(q+56, 4))
        before = bytes(h.s.uc.mem_read(q, self.state_size))
        for message in (0x3E, 0x3F):
            h.s.dispatch(message, payload)
            h.s.drain()
        self.assertEqual(bytes(h.s.uc.mem_read(q, self.state_size)), before,
                         'superseded Q session controls remain inert even with a current epoch')

    def test_actual_back_stops_sampling_and_reentry_starts_automatically(self):
        h = self.scene()
        h.values[0] = 1000
        self.samples(h, 8)
        h.press(0, 3)
        self.assertEqual(h.read(STATE), 2)
        before = len(h.s.log)
        for _ in range(3):
            self.assertEqual(h.poll(), 0)
        self.assertEqual(h.s.log[before:], [])
        self.assertEqual(h.selected, 8)
        h.values[0] = 900
        h.enter()
        self.assertEqual(self.faults(h), [0]*8)
        self.samples(h, 8)
        self.assertEqual(self.now(h), [1]*8)

    def test_successful_init_saves_five_sample_medians_and_resumes_automatically(self):
        h = self.scene()
        h.values = [1100+pin for pin in range(8)]
        result, saved, requests = self.initialize(h)
        expected = struct.pack('<8H', *h.values)
        self.assertEqual(result, 0)
        self.assertEqual([pin for pin, _, _ in h.reads], [pin for pin in range(8) for _ in range(5)])
        self.assertEqual(saved, [expected])
        self.assertEqual(requests, [5])
        self.assertEqual(bytes(h.s.uc.mem_read(BASE, 16)), expected)
        self.assertEqual(bytes(h.s.uc.mem_read(SETTINGS+0x90, 16)), expected)
        self.assertEqual(self.mode(h), 1)
        self.assertEqual(h.read(self.info['state']+3), 0)
        h.values = [900]*8
        self.samples(h, 8)
        self.assertEqual(self.now(h), [1]*8)

    def test_failed_init_keeps_old_baseline_and_waits_for_successful_retry(self):
        h = self.scene()
        baseline = bytes(h.s.uc.mem_read(BASE, 16))
        settings = bytes(h.s.uc.mem_read(SETTINGS, 0xCC))
        h.source = lambda pin, number: 1010 if pin == 0 and number % 5 == 4 else 1000
        result, saved, requests = self.initialize(h)
        self.assertEqual((result, saved, requests), (1, [], []))
        self.assertEqual(bytes(h.s.uc.mem_read(BASE, 16)), baseline)
        self.assertEqual(bytes(h.s.uc.mem_read(SETTINGS, 0xCC)), settings)
        self.assertEqual(self.mode(h), 4)
        self.assertEqual(h.read(FLAGS+1), 1)
        self.assertEqual(h.read(self.info['state']+3), 0)
        before = len(h.s.log)
        h.advance(60_000)
        for _ in range(3):
            self.assertEqual(h.poll(), 0)
        self.assertEqual(h.s.log[before:], [], 'the Init error remains visible until recovery')
        h.source = lambda pin, number: 1100
        self.assertEqual(self.initialize(h)[0], 0)
        self.assertEqual(self.mode(h), 1)
        h.source = lambda pin, number: 900
        self.samples(h, 8)
        self.assertEqual(self.now(h), [1]*8)

    def test_reentry_recovers_from_init_error_using_the_retained_baseline(self):
        h = self.scene()
        baseline = bytes(h.s.uc.mem_read(BASE, 16))
        h.source = lambda pin, number: 1010 if number % 5 == 4 else 1000
        self.assertEqual(self.initialize(h)[0], 1)
        self.assertEqual(self.mode(h), 4)
        h.press(0, 3)
        h.source = lambda pin, number: 900
        h.enter()
        self.assertEqual(bytes(h.s.uc.mem_read(BASE, 16)), baseline)
        self.samples(h, 8)
        self.assertEqual(self.now(h), [1]*8)

    def test_actual_main_startup_clears_poisoned_state_and_cache_before_classic_entry(self):
        import qc_continuity
        h = Harness(self.data)
        q = self.info['state']
        cache = self.classic['ui']['cache']
        cache_size = self.classic['ui']['cache_size']
        h.s.uc.mem_write(q, bytes([0xA5])*self.state_size)
        h.s.uc.mem_write(cache, bytes([0x5A])*cache_size)
        before = bytes(h.s.uc.mem_read(q-16, 16))
        after = bytes(range(0xC0, 0xD0))
        h.s.uc.mem_write(cache+cache_size, after)
        h.s.uc.reg_write(UC_ARM_REG_SP, STACK)
        h.s.uc.reg_write(UC_ARM_REG_LR, MAGIC | 1)
        # Execute main's actual patched BL and its complete composed startup
        # chain, stopping before hardware/task initialization continues.
        h.s.uc.emu_start(MAIN | 1, MAIN+4, count=100_000)
        self.assertEqual(h.s.uc.reg_read(UC_ARM_REG_PC), MAIN+4)
        self.assertEqual(h.s.uc.reg_read(UC_ARM_REG_SP), STACK)
        self.assertEqual(bytes(h.s.uc.mem_read(q, self.state_size)), bytes(self.state_size))
        self.assertEqual(bytes(h.s.uc.mem_read(cache, cache_size)), bytes(cache_size))
        self.assertEqual(bytes(h.s.uc.mem_read(q-16, 16)), before)
        self.assertEqual(bytes(h.s.uc.mem_read(cache+cache_size, 16)), after)
        self.assertEqual(h.reads, [])
        h.enter()
        with contextlib.redirect_stdout(io.StringIO()):
            original = Harness(bytes(qc_continuity.parent().finalize().data))
        original.enter()
        self.assertEqual(h.s.fb, original.s.fb, 'startup must lead to the original QC entry artwork')
        self.assertEqual(self.mode(h), 1)
        self.samples(h, 8)
        self.assertEqual(self.now(h), [1]*8)
        self.assertEqual(bytes(h.s.uc.mem_read(cache+cache_size, 16)), after)


if __name__ == '__main__':
    unittest.main()
