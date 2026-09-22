"""CPU ownership regressions for preserving validated Digital feedback at gain changes.

ADC values and interrupt arrivals are modeled; analyzers, gain control, sampler,
speaker eligibility and main-loop boundaries execute their actual ARM code.
"""
import struct
import unittest

from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_PRIMASK

import auto_range_freshness
import digital_gain_continuity
import sampling_fixes
import test_rx_auto_range_freshness as freshness
import test_rx_robust
from test_rx_followup import ANALYZERS, GATE_STATE, GRADE, INDICES, REQUEST, SPEAKER, TIM5
from verify_control import BEEP
from verify_digital import ACTIVE, BUFFER, GAP, GATE, RECENT, pattern


class DigitalGainContinuity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.previous = bytes(auto_range_freshness.build_candidate().data)
        cls.img = digital_gain_continuity.build_candidate()
        cls.data = bytes(cls.img.data)

    cpu = freshness.AutoRangeFreshness.cpu
    tick = freshness.AutoRangeFreshness.tick
    interrupt = freshness.AutoRangeFreshness.interrupt
    execute = test_rx_robust.Robust.execute
    boundary = test_rx_robust.Robust.boundary
    acquire = test_rx_robust.Robust.acquire

    def feedback(self, c):
        return c.read(GRADE), c.read(GAP), c.read(RECENT, 2)

    def published(self, c):
        c.w8(ACTIVE, 0)
        c.uc.mem_write(BUFFER, struct.pack('<48H', *pattern(low=1000, high=1300)))
        self.execute(c, ANALYZERS[0])
        self.assertGreater(c.read(GRADE), 1, 'fixture must publish a validated signal')
        self.assertEqual(c.read(RECENT, 2), 800)
        self.execute(c, SPEAKER)
        self.assertGreater(c.read(BEEP), 0)
        self.assertGreater(c.read(GAP), 0)

    def test_gain_boundary_preserves_validated_feedback_without_refresh(self):
        c = self.cpu()
        self.published(c)
        grade, gap, recent = self.feedback(c)
        beep = c.read(BEEP)
        self.tick(c, 2)
        self.boundary(c)
        self.assertEqual(self.feedback(c), (grade, gap, recent-1),
                         'gain-only reacquisition must retain the existing feedback deadline')
        self.assertEqual(c.read(BEEP), beep-1)
        self.assertEqual((c.read(GATE_STATE), c.read(ACTIVE)), (2, 1))

    def test_gain_boundary_restarts_every_index_and_requires_240_new_adc_reads(self):
        c = self.cpu()
        self.published(c)
        for address, value in zip(INDICES, (45, 12, 33)):
            c.w8(address, value)
        c.w8(0x200000EE, 8)
        self.tick(c, 2)
        self.boundary(c)
        expected = self.feedback(c)
        self.assertEqual([c.read(address) for address in INDICES], [0, 0, 0])
        self.assertEqual((c.read(0x200000EE), c.read(ACTIVE)), (0, 1))
        self.execute(c, ANALYZERS[0])
        self.assertEqual(self.feedback(c), expected, 'the old buffer must not be analyzed')
        for _ in range(600):
            if not c.read(ACTIVE):
                break
            c.w32(0x20000100, 19)
            self.execute(c, TIM5, budget=4000)
            if c.read(ACTIVE):
                self.execute(c, ANALYZERS[0])
                self.assertEqual(self.feedback(c), expected)
        self.assertEqual(c.read(ACTIVE), 0)
        self.assertEqual(c.sample_reads, 240)
        self.assertEqual(bytes(c.uc.mem_read(BUFFER, 96)), struct.pack('<48H', *([1234]*48)))

    def test_new_complete_valid_window_may_publish_a_fresh_deadline(self):
        c = self.cpu()
        self.published(c)
        self.tick(c, 2)
        self.boundary(c)
        self.assertEqual(c.read(RECENT, 2), 799)
        self.acquire(c, pattern(low=1000, high=1600))
        self.assertEqual(c.read(ACTIVE), 0)
        self.execute(c, ANALYZERS[0])
        self.assertEqual(c.read(RECENT, 2), 800)
        self.assertGreater(c.read(GRADE), 1)
        self.assertEqual((c.read(ACTIVE), c.read(INDICES[0])), (1, 40))

    def test_repeated_gain_changes_never_extend_the_existing_deadline(self):
        for settle_each in (False, True):
            with self.subTest(settle_each=settle_each):
                c = self.cpu()
                self.published(c)
                grade, gap, recent = self.feedback(c)
                for count, knob in enumerate((2, 1, 2, 7), 1):
                    self.tick(c, knob)
                    self.assertEqual(c.read(GATE_STATE), 3)
                    self.assertEqual(self.feedback(c), (grade, gap, recent-count))
                    if settle_each:
                        self.boundary(c)
                        self.assertEqual(self.feedback(c), (grade, gap, recent-count))
                self.boundary(c)
                self.assertEqual(self.feedback(c), (grade, gap, recent-4))

    def test_expired_or_absent_feedback_cannot_restart_audio(self):
        for grade, recent in ((0, 0), (0, 800), (30, 0), (30, 499), (30, 500)):
            with self.subTest(grade=grade, recent=recent):
                c = self.cpu()
                c.w8(GRADE, grade)
                c.w16(RECENT, recent)
                self.tick(c, 2)
                self.boundary(c)
                self.assertLessEqual(c.read(RECENT, 2), recent)
                self.execute(c, SPEAKER)
                self.assertEqual(c.read(BEEP), 0)

    def test_gate_close_reopen_cannot_be_mistaken_for_gain_only_change(self):
        c = self.cpu()
        self.published(c)
        self.tick(c, 0)
        self.assertEqual(c.read(GATE_STATE), 0)
        self.tick(c, 7)
        self.assertEqual(c.read(GATE_STATE), 0)
        self.boundary(c)
        self.assertEqual(self.feedback(c), (0, 0, 0))
        self.assertEqual((c.read(GATE_STATE), c.read(ACTIVE)), (2, 1))

    def test_startup_and_closed_gate_do_not_gain_continuity_authority(self):
        for gate_state in (0, 1):
            c = self.cpu()
            self.published(c)
            c.w8(GATE_STATE, gate_state)
            self.tick(c, 2)
            self.assertEqual(c.read(GATE_STATE), 0)
            self.boundary(c)
            self.assertEqual(self.feedback(c), (0, 0, 0))

    def test_mode_requests_and_closed_raw_gate_clear_prior_feedback(self):
        for request, raw_gate in ((1, 4060), (2, 4060), (3, 4060), (0, 0), (0, 1)):
            with self.subTest(request=request, raw_gate=raw_gate):
                c = self.cpu()
                self.published(c)
                self.tick(c, 2)
                c.w8(REQUEST, request)
                c.w16(GATE, raw_gate)
                self.boundary(c)
                self.assertEqual(self.feedback(c), (0, 0, 0))

    def test_analog_and_mains_changed_gain_match_previous_candidate(self):
        for mode in (1, 2):
            results = []
            for previous in (True, False):
                c = self.cpu(previous=previous, mode=mode)
                c.w8(GRADE, 30)
                c.w8(GAP, 45)
                c.w16(RECENT, 600)
                c.w8(BEEP, 17)
                c.w8(ACTIVE, 1)
                c.w8(INDICES[mode], 12)
                self.tick(c, 2)
                self.assertEqual(c.read(GATE_STATE), 0)
                self.boundary(c)
                results.append((self.feedback(c), c.read(BEEP), c.read(ACTIVE),
                                c.read(GATE_STATE), tuple(c.read(a) for a in INDICES)))
            self.assertEqual(results[0], results[1])

    def test_gain_irq_at_each_unmasked_digital_instruction_blocks_stale_publication(self):
        # Interrupt the first visit to each unique unmasked instruction. This
        # covers the real DSP path, not every loop iteration or NVIC schedule.
        def ready():
            c = self.cpu()
            self.published(c)
            c.w8(BEEP, 0)
            c.w8(GAP, 23)
            c.w16(RECENT, 713)
            c.w8(ACTIVE, 0)
            c.uc.mem_write(BUFFER, struct.pack('<48H', *pattern(low=1000, high=1600)))
            return c

        points = set()
        c = ready()
        def trace(uc, address, size, user):
            if not uc.reg_read(UC_ARM_REG_PRIMASK):
                points.add(address)
        hook = c.uc.hook_add(UC_HOOK_CODE, trace)
        try:
            self.execute(c, ANALYZERS[0])
        finally:
            c.uc.hook_del(hook)
        self.assertGreater(len(points), 150)

        for point in sorted(points):
            with self.subTest(point=hex(point)):
                c = ready()
                interrupted = []
                def event(machine):
                    self.tick(machine, 2)
                    interrupted.append(self.feedback(machine))
                self.interrupt(c, ANALYZERS[0], point, event)
                self.assertEqual(c.read(GATE_STATE), 3)
                self.assertEqual(self.feedback(c), interrupted[0],
                                 'the interrupted old-gain analyzer must not publish')
                self.execute(c, SPEAKER, budget=5000)
                self.assertEqual(c.read(BEEP), 0)
                self.boundary(c)
                self.assertEqual(self.feedback(c), interrupted[0])
                self.assertEqual((c.read(ACTIVE), c.read(GATE_STATE)), (1, 2))
                self.assertEqual([c.read(a) for a in INDICES], [0, 0, 0])
                self.execute(c, ANALYZERS[0])
                self.assertEqual(self.feedback(c), interrupted[0])

    def test_boundary_gain_preemption_never_refreshes_or_loses_validated_feedback(self):
        def ready():
            c = self.cpu()
            self.published(c)
            self.tick(c, 2)
            return c

        points = set()
        c = ready()
        def trace(uc, address, size, user):
            if not uc.reg_read(UC_ARM_REG_PRIMASK):
                points.add(address)
        hook = c.uc.hook_add(UC_HOOK_CODE, trace)
        try:
            self.execute(c, sampling_fixes.BOUNDARY)
        finally:
            c.uc.hook_del(hook)
        self.assertGreaterEqual(len(points), 5)

        for point in sorted(points):
            for knob in (0, 1):
                with self.subTest(point=hex(point), knob=knob):
                    c = ready()
                    grade, gap, recent = self.feedback(c)
                    self.interrupt(c, sampling_fixes.BOUNDARY, point,
                                   lambda machine: self.tick(machine, knob))
                    # A pending IRQ may run immediately after the boundary
                    # unmasks. The following real boundary must consume it.
                    self.boundary(c)
                    if knob:
                        self.assertEqual(self.feedback(c), (grade, gap, recent-1))
                        self.assertEqual((c.read(GATE_STATE), c.read(ACTIVE)), (2, 1))
                    else:
                        self.assertEqual(self.feedback(c), (0, 0, 0))
                        self.assertEqual((c.read(GATE_STATE), c.read(ACTIVE)), (1, 2))
                    self.assertEqual([c.read(a) for a in INDICES], [0, 0, 0])

    def test_boundary_resets_atomically_and_restores_the_callers_interrupt_mask(self):
        owned = {ACTIVE, GATE_STATE, GRADE, GAP, RECENT, 0x200000EE, *INDICES}
        for mask in (0, 1):
            c = self.cpu()
            self.published(c)
            self.tick(c, 2)
            c.uc.reg_write(UC_ARM_REG_PRIMASK, mask)
            writes = []
            def write(uc, access, address, size, value, user):
                if address in owned:
                    writes.append(address)
                    self.assertEqual(uc.reg_read(UC_ARM_REG_PRIMASK), 1)
            hook = c.uc.hook_add(UC_HOOK_MEM_WRITE, write)
            try:
                self.execute(c, sampling_fixes.BOUNDARY)
            finally:
                c.uc.hook_del(hook)
            self.assertIn(ACTIVE, writes)
            self.assertEqual(c.uc.reg_read(UC_ARM_REG_PRIMASK), mask)
            self.assertEqual([c.read(a) for a in INDICES], [0, 0, 0])


if __name__ == '__main__':
    unittest.main()
