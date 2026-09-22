"""Actual Thumb sample-age regression; timer/ADC arrival schedules are modeled.

These measurements establish software freshness, not physical sensitivity or
interrupt latency on a receiver.
"""
import copy
import unittest

from unicorn import UC_HOOK_CODE
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,
                               UC_ARM_REG_R3, UC_ARM_REG_PRIMASK)

import digital_gain_continuity
import sample_age_guard
import test_rx_digital_release_audit as release
import test_rx_robust as robust
import test_rx_followup as followup
from test_rx_analog_feedback import sine
from verify_control import MODE
from verify_digital import ACTIVE, BUFFER, GATE, RECENT, pattern
from lpm10rx.image import PatchError


def candidate():
    img = digital_gain_continuity.build_candidate()
    sample_age_guard.install(img)
    return img


class SampleAgeGuard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parent = digital_gain_continuity.build_candidate()
        cls.img = candidate()
        cls.data = bytes(cls.img.data)

    cpu = robust.Robust.cpu
    execute = robust.Robust.execute
    boundary = robust.Robust.boundary
    acquire = followup.Followup.acquire

    def setup_mode(self, mode, *, data=None):
        c = self.cpu(data)
        c.w8(MODE, mode)
        c.w16(GATE, 580)
        c.w16(GATE+2, 1)
        c.w8(0x20000200, 1)
        c.w8(followup.GATE_STATE, 0)
        self.boundary(c)
        return c

    def completed(self, mode, *, data=None, samples=None):
        c = self.setup_mode(mode, data=data)
        samples = samples or (pattern() if mode == 0 else sine(300))
        calls = self.acquire(c, samples)
        self.assertEqual(len(calls), 240 if mode == 0 else 64)
        self.assertEqual(c.read(ACTIVE), 0)
        if data is None:
            self.assertEqual(c.read(sample_age_guard.COMPLETED_VALID, 4), 1)
            self.assertEqual(c.read(sample_age_guard.COMPLETED_AT, 4),
                             c.read(sample_age_guard.TIMER_COUNTER, 4))
        return c, samples

    def stream(self, img, **kw):
        harness = release.ReleaseAudit()
        harness.data = bytes(img.data)
        return harness.run_stream(**kw)

    def test_foreground_stall_cannot_publish_a_completed_old_window(self):
        scenario = dict(amplitude=3000, loss_ms=650, post_ms=1700,
                        stall=(610, 1850))
        old = self.stream(self.parent, **scenario)
        stale = [row for row in old['accepted_after_loss'] if row['age_ms'] > 1000]
        self.assertTrue(stale, 'negative control must reproduce PN1.23G defect')
        new = self.stream(self.img, **scenario)
        self.assertFalse([row for row in new['accepted_after_loss']
                          if row['age_ms'] > 300 and row['recent'] > 500])
        self.assertFalse([t for t in new['post_loss_starts_ms'] if t > 1000])

    def test_fresh_completed_windows_keep_parent_feedback_and_overlap(self):
        for mode in (0, 1):
            with self.subTest(mode=mode):
                old, samples = self.completed(mode, data=bytes(self.parent.data))
                new, _ = self.completed(mode, samples=samples)
                for c in (old, new):
                    self.execute(c, followup.ANALYZERS[mode], budget=100_000)
                for address, size in ((followup.GRADE, 1), (RECENT, 2),
                                      (ACTIVE, 1), (followup.INDICES[mode], 1)):
                    self.assertEqual(new.read(address, size), old.read(address, size))
                self.assertGreater(new.read(RECENT, 2), 500)
                self.assertEqual(new.read(sample_age_guard.COMPLETED_VALID, 4), 1)

    def test_expired_readiness_restarts_a_full_fresh_window_in_main(self):
        for mode, limit in self.img.sample_age_guard['age_limit_ticks'].items():
            with self.subTest(mode=mode):
                c, samples = self.completed(mode)
                before = bytes(c.uc.mem_read(BUFFER, 128))
                completed = c.read(sample_age_guard.COMPLETED_AT, 4)
                c.w32(sample_age_guard.TIMER_COUNTER, completed+limit+1)
                self.execute(c, followup.ANALYZERS[mode], budget=100_000)
                self.assertEqual(c.read(RECENT, 2), 0)
                self.assertEqual(c.read(followup.GATE_STATE), 0)
                self.assertEqual(c.read(sample_age_guard.COMPLETED_VALID, 4), 0)
                self.assertEqual(c.read(ACTIVE), 0, 'expiry must not reset ADC inside the check')
                self.assertEqual(bytes(c.uc.mem_read(BUFFER, 128)), before)
                self.boundary(c)
                self.assertEqual(c.read(ACTIVE), 1)
                self.assertEqual(c.read(followup.INDICES[mode]), 0)
                partial = self.acquire(c, samples, complete=False)
                self.assertEqual(c.read(sample_age_guard.COMPLETED_VALID, 4), 0)
                self.assertEqual(c.read(followup.INDICES[mode]), len(samples)-1)
                tail = self.acquire(c, samples)
                self.assertEqual(len(partial)+len(tail), 240 if mode == 0 else 64)
                self.assertEqual(c.read(sample_age_guard.COMPLETED_VALID, 4), 1)
                self.execute(c, followup.ANALYZERS[mode], budget=100_000)
                self.assertGreater(c.read(RECENT, 2), 500)

    def test_deadlines_and_unsigned_wrap_are_checked_before_analysis(self):
        for mode, limit in self.img.sample_age_guard['age_limit_ticks'].items():
            for start in (0, 0xFFFFFF00):
                for delta in (0, limit, limit+1):
                    with self.subTest(mode=mode, start=start, delta=delta):
                        c, _ = self.completed(mode)
                        c.w32(sample_age_guard.COMPLETED_AT, start)
                        c.w32(sample_age_guard.TIMER_COUNTER, (start+delta) & 0xFFFFFFFF)
                        self.execute(c, followup.ANALYZERS[mode], budget=100_000)
                        self.assertEqual(c.read(RECENT, 2) > 500, delta <= limit)

    def test_publication_uses_analyzed_timestamp_even_if_next_window_is_new(self):
        # The scheduler advances the modeled clock at an unmasked foreground
        # seam. ADC completion bookkeeping is independently exercised above.
        for mode, limit in self.img.sample_age_guard['age_limit_ticks'].items():
            for next_window in (False, True):
                with self.subTest(mode=mode, next_window=next_window):
                    c, _ = self.completed(mode)
                    completed = c.read(sample_age_guard.COMPLETED_AT, 4)
                    observed = []
                    def stall(uc, address, size, user):
                        self.assertEqual(uc.reg_read(UC_ARM_REG_PRIMASK), 0)
                        observed.append(address)
                        now = completed+limit+1
                        c.w32(sample_age_guard.TIMER_COUNTER, now)
                        if next_window:
                            c.w32(sample_age_guard.COMPLETED_AT, now)
                        c.w16(RECENT, 0)
                    hook = c.uc.hook_add(UC_HOOK_CODE, stall,
                        begin=sample_age_guard.PUBLISH, end=sample_age_guard.PUBLISH)
                    try:
                        self.execute(c, followup.ANALYZERS[mode], budget=100_000)
                    finally:
                        c.uc.hook_del(hook)
                    self.assertTrue(observed)
                    self.assertEqual(c.read(RECENT, 2), 0)
                    self.assertEqual(c.read(followup.GATE_STATE), 0)
                    self.assertEqual(c.read(sample_age_guard.ANALYSIS_AT, 4), completed)

    def test_analog_refresh_cannot_renew_feedback_after_late_preemption(self):
        for img, expected in ((self.parent, 600), (self.img, 0)):
            c, _ = self.completed(1, data=bytes(img.data))
            def stall(uc, address, size, user):
                self.assertEqual(uc.reg_read(UC_ARM_REG_PRIMASK), 0)
                c.w32(sample_age_guard.TIMER_COUNTER,
                      c.read(sample_age_guard.TIMER_COUNTER, 4)
                      +sample_age_guard.ANALOG_MAX_AGE_TICKS+1)
                c.w16(RECENT, 0)  # elapsed countdown during the modeled stall
            hook = c.uc.hook_add(UC_HOOK_CODE, stall,
                begin=sample_age_guard.ANALOG_REFRESH, end=sample_age_guard.ANALOG_REFRESH)
            try:
                self.execute(c, followup.ANALYZERS[1], budget=100_000)
            finally:
                c.uc.hook_del(hook)
            self.assertEqual(c.read(RECENT, 2), expected)

    def test_completion_inline_hook_preserves_live_registers_stack_and_mask(self):
        for mask in (0, 1):
            c = self.cpu()
            c.w32(sample_age_guard.TIMER_COUNTER, 0xFFFFFFFE)
            c.uc.reg_write(UC_ARM_REG_R2, 0x23456789)
            c.uc.reg_write(UC_ARM_REG_R3, 0x3456789A)
            c.uc.reg_write(UC_ARM_REG_PRIMASK, mask)
            self.execute(c, self.img.sample_age_guard['stamp'], ACTIVE, 0x11223344)
            self.assertEqual(c.uc.reg_read(UC_ARM_REG_R0), ACTIVE)
            self.assertEqual(c.uc.reg_read(UC_ARM_REG_R1), 0)
            self.assertEqual(c.uc.reg_read(UC_ARM_REG_R2), 0x23456789)
            self.assertEqual(c.uc.reg_read(UC_ARM_REG_R3), 0x3456789A)
            self.assertEqual(c.uc.reg_read(UC_ARM_REG_PRIMASK), mask)
            self.assertEqual(c.read(sample_age_guard.COMPLETED_AT, 4), 0xFFFFFFFE)
            self.assertEqual(c.read(sample_age_guard.COMPLETED_VALID, 4), 1)
            self.assertEqual(c.read(ACTIVE), 0)

    def test_mains_does_not_require_digital_or_analog_completion_metadata(self):
        c = self.setup_mode(2)
        samples = [2048]*64
        self.acquire(c, samples)
        self.assertEqual(c.read(sample_age_guard.COMPLETED_VALID, 4), 0)
        self.assertEqual(self.execute(c, 0x08008408), 1)

    def test_masked_analyzer_entry_restores_mask_for_fresh_and_expired_windows(self):
        for mode, limit in self.img.sample_age_guard['age_limit_ticks'].items():
            for expired in (False, True):
                c, _ = self.completed(mode)
                if expired:
                    c.w32(sample_age_guard.TIMER_COUNTER,
                          c.read(sample_age_guard.COMPLETED_AT, 4)+limit+1)
                c.uc.reg_write(UC_ARM_REG_PRIMASK, 1)
                self.execute(c, followup.ANALYZERS[mode], budget=100_000)
                self.assertEqual(c.uc.reg_read(UC_ARM_REG_PRIMASK), 1)
                self.assertEqual(c.read(RECENT, 2) > 500, not expired)

    def test_exact_hook_guards_reject_tampering_before_any_mutation(self):
        for site in self.img.sample_age_guard['hooks']:
            with self.subTest(site=hex(site)):
                altered = copy.deepcopy(self.parent)
                altered.data[altered.f(site)] ^= 1
                before = bytes(altered.data), list(altered.log)
                with self.assertRaises(PatchError):
                    sample_age_guard.install(altered)
                self.assertEqual((bytes(altered.data), altered.log), before)
        with self.assertRaises(PatchError):
            sample_age_guard.install(self.img)


if __name__ == '__main__':
    unittest.main()
