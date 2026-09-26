"""PN1.30 publication/fast-gain handoff, executing the real ARM instructions.

ADC conversion, GPIO and interrupt arrival schedules are modeled. These tests
prove publication ordering and ownership, not physical pickup or IRQ frequency.
"""
import copy
import struct
import unittest

from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_PRIMASK

import auto_range
import clean_strength as strength
import level_display
import publication_commit as commit
import sample_age_guard as age
import sampling_fixes
import test_rx_auto_range_freshness as agc
import test_rx_analog_feedback_races as races
import test_rx_followup as followup
import test_rx_isolate as fixtures
import test_rx_tracking_streams as streams
from lpm10rx.image import PatchError
from test_rx_analog_feedback import sine
from verify_control import BEEP, MODE, SP, TICK
from verify_digital import ACTIVE, BUFFER, RECENT, pattern


class PublicationCommit(unittest.TestCase):
    execute = agc.AutoRangeFreshness.execute
    interrupt = agc.AutoRangeFreshness.interrupt
    boundary = agc.AutoRangeFreshness.boundary
    timers = streams.TrackingStreams.timers
    fresh = fixtures.Analysers.fresh
    interrupt_at = races.AnalogFeedbackRaces.interrupt_at
    GENERATION = 1000
    PREVIOUS_GENERATION = 500

    @classmethod
    def setUpClass(cls):
        cls.parent = strength.build_candidate()
        cls.old_data = bytes(cls.parent.data)
        cls.img = copy.deepcopy(cls.parent)
        commit.install(cls.img)
        cls.data = bytes(cls.img.data)
        cls.curve = cls.parent.clean_strength['curve']
        cls.after_old_marker = cls.curve + 10

    def ready(self, mode=0, *, previous=False, sustained=False, rejected=False, clipped=False):
        data = self.old_data if previous else self.data
        c = fixtures.FieldCPU(data, mode=mode, knob=4095)
        self.fresh(c, mode=mode, knob=4095, level=7,
                   grade=57 if sustained else 0, recent=700 if sustained else 0)
        c.w32(age.COMPLETED_AT, self.GENERATION)
        c.w32(age.TIMER_COUNTER, self.GENERATION)
        c.w32(strength.LAST_DISPLAYED, self.PREVIOUS_GENERATION)
        c.w32(strength.LAST_DECIDED, self.PREVIOUS_GENERATION)
        if sustained:
            c.w32(level_display.AVERAGE, 40000)
            c.w8(level_display.AVERAGE+4, level_display.count(40000))
        if mode == 0:
            samples = [800, 3200]*24 if rejected else pattern(0, 800, 4095 if clipped else 3200)
        else:
            samples = [2048]*64 if rejected else sine(8000 if clipped else 1200)
        c.uc.mem_write(BUFFER, struct.pack(f'<{len(samples)}H', *samples))
        return c

    def timer(self, c):
        self.execute(c, fixtures.TIM1, stack=SP-0x500, budget=10000)

    def analyze(self, c):
        self.execute(c, followup.ANALYZERS[c.read(MODE)], budget=150000)

    def trace(self, c):
        """Each instruction address and mask reached by the full real analyzer."""
        points = set()
        def record(uc, address, size, user):
            points.add((address, uc.reg_read(UC_ARM_REG_PRIMASK)))
        hook = c.uc.hook_add(UC_HOOK_CODE, record)
        try:
            self.analyze(c)
        finally:
            c.uc.hook_del(hook)
        return points

    def test_parent_reproduces_first_window_loss_in_both_modes(self):
        for mode in (0, 1):
            c = self.ready(mode, previous=True)
            self.interrupt(c, followup.ANALYZERS[mode], self.after_old_marker, self.timer)
            self.assertEqual((c.read(auto_range.STATE), c.read(followup.GRADE),
                              c.read(RECENT, 2)), (2, 0, 0))

    def test_fast_gain_waits_for_successful_publication(self):
        for mode in (0, 1):
            for sustained in (False, True):
                with self.subTest(mode=mode, sustained=sustained):
                    c = self.ready(mode, sustained=sustained)
                    self.interrupt(c, followup.ANALYZERS[mode], self.after_old_marker, self.timer)
                    self.assertEqual(c.read(auto_range.STATE), 7)
                    self.assertGreater(c.read(followup.GRADE), 0)
                    self.assertEqual(c.read(RECENT, 2), (800, 600)[mode])
                    self.assertEqual(c.read(strength.LAST_DISPLAYED, 4), self.GENERATION)
                    self.timer(c)
                    self.assertEqual(c.read(auto_range.STATE), 2)

    def test_fast_gain_at_every_unmasked_analyzer_instruction_sees_a_committed_frame(self):
        schedules = 0
        for mode in (0, 1):
            for sustained in (False, True):
                c = self.ready(mode, sustained=sustained)
                points = sorted(address for address, mask in self.trace(c) if not mask)
                expected_grade = c.read(followup.GRADE)
                self.assertGreater(len(points), 150)
                for point in points:
                    with self.subTest(mode=mode, sustained=sustained, point=hex(point)):
                        c = self.ready(mode, sustained=sustained)
                        observed = []
                        def timer(cpu):
                            before = (cpu.read(strength.LAST_DISPLAYED, 4),
                                      cpu.read(followup.GRADE), cpu.read(RECENT, 2))
                            self.timer(cpu)
                            if cpu.read(auto_range.STATE) != 7:
                                observed.append(before)
                        self.interrupt(c, followup.ANALYZERS[mode], point, timer)
                        self.assertEqual(c.read(followup.GRADE), expected_grade)
                        self.assertGreater(c.read(RECENT, 2), 500)
                        self.assertEqual(c.read(strength.LAST_DISPLAYED, 4), self.GENERATION)
                        for stamp, grade, recent in observed:
                            self.assertEqual(stamp, self.GENERATION)
                            self.assertEqual(grade, expected_grade)
                            self.assertGreater(recent, 500)
                        schedules += 1
        print('Publication commit: real TIM1 at', schedules, 'unmasked analyzer instruction/state combinations')

    def test_marker_store_is_masked_after_feedback_and_restores_entry_mask(self):
        for mode in (0, 1):
            for mask in (0, 1):
                for clipped in (False, True):
                    c = self.ready(mode, clipped=clipped)
                    c.uc.reg_write(UC_ARM_REG_PRIMASK, mask)
                    commits = []
                    def marker(uc, access, address, size, value, user):
                        commits.append((uc.reg_read(UC_ARM_REG_PRIMASK), size, value,
                                        c.read(followup.GRADE), c.read(RECENT, 2)))
                    hook = c.uc.hook_add(UC_HOOK_MEM_WRITE, marker,
                        begin=strength.LAST_DISPLAYED, end=strength.LAST_DISPLAYED+3)
                    try:
                        self.analyze(c)
                    finally:
                        c.uc.hook_del(hook)
                    self.assertEqual(len(commits), 1)
                    self.assertEqual(commits[0][:3], (1, 4, self.GENERATION))
                    self.assertGreater(commits[0][3], 0)
                    self.assertEqual(commits[0][4], 800)
                    self.assertEqual(c.uc.reg_read(UC_ARM_REG_PRIMASK), mask)

    def test_timer_pending_at_every_masked_publisher_instruction_runs_after_commit(self):
        cases = 0
        for mode in (0, 1):
            c = self.ready(mode)
            points = sorted(address for address, mask in self.trace(c)
                if mask and commit.PUBLISHER <= address < commit.PUBLISHER+commit.PUBLISHER_SIZE)
            self.assertGreater(len(points), 15)
            for point in points:
                c = self.ready(mode)
                delivered = []
                def timer(cpu):
                    delivered.append((cpu.read(strength.LAST_DISPLAYED, 4),
                                      cpu.read(followup.GRADE), cpu.read(RECENT, 2)))
                    self.timer(cpu)
                self.interrupt_at(c, followup.ANALYZERS[mode], point, timer, defer_if_masked=True)
                self.assertEqual(len(delivered), 1)
                self.assertEqual(delivered[0][0], self.GENERATION)
                self.assertGreater(delivered[0][1], 0)
                self.assertEqual(delivered[0][2], 800)
                self.assertEqual(c.read(auto_range.STATE), 2)
                self.assertGreater(c.read(RECENT, 2), 500)
                cases += 1
        print('Publication commit: deferred TIM1 at', cases, 'masked publisher instructions')

    def test_marker_commits_analyzed_timestamp_not_next_completed_adc_window(self):
        for previous in (True, False):
            c = self.ready(previous=previous)
            c.amplitude = lambda tick: 2400
            self.interrupt(c, followup.ANALYZERS[0], self.curve,
                           lambda cpu: self.timers(cpu, 1800))
            latest = c.read(age.COMPLETED_AT, 4)
            self.assertNotEqual(latest, self.GENERATION, 'the real next ADC window must complete')
            self.assertEqual(c.read(ACTIVE), 0)
            self.assertGreater(c.read(RECENT, 2), 500)
            self.assertEqual(c.read(age.ANALYSIS_AT, 4), self.GENERATION)
            self.assertEqual(c.read(strength.LAST_DISPLAYED, 4),
                             latest if previous else self.GENERATION)
            self.timer(c)
            if not previous:
                self.assertEqual(c.read(auto_range.STATE), 7,
                    'the unanalysed next window cannot authorize fast gain')

    def test_rejected_windows_never_authorize_fast_gain_or_extend_feedback(self):
        for mode in (0, 1):
            for sustained in (False, True):
                c = self.ready(mode, sustained=sustained, rejected=True)
                self.analyze(c)
                self.assertEqual(c.read(strength.LAST_DISPLAYED, 4), self.PREVIOUS_GENERATION)
                self.assertEqual(c.read(followup.GRADE), 57 if sustained else 0)
                self.assertEqual(c.read(RECENT, 2), (660, 560)[mode] if sustained else 0)
                self.timer(c)
                self.assertEqual(c.read(auto_range.STATE), 7)

    def test_real_gate_mode_and_gain_invalidations_never_commit_a_discarded_window(self):
        for mode in (0, 1):
            for kind in ('gate', 'mode', 'gain'):
                for sustained in (False, True):
                    with self.subTest(mode=mode, kind=kind, sustained=sustained):
                        c = self.ready(mode, sustained=sustained)
                        def event(cpu):
                            if kind == 'gate':
                                self.execute(cpu, sampling_fixes.PUBLISH_GATE, 0, stack=SP-0x500)
                                self.execute(cpu, sampling_fixes.PUBLISH_GATE, 4095, stack=SP-0x500)
                            elif kind == 'mode':
                                cpu.w16(0x2000010E, 6)
                                self.execute(cpu, followup.KEY, stack=SP-0x500)
                            else:
                                cpu.w32(TICK, 499)  # ordinary 500 ms AGC remains independent of fast gain
                                self.timer(cpu)
                                self.assertEqual(cpu.read(auto_range.STATE), 2)
                        self.interrupt(c, followup.ANALYZERS[mode], self.after_old_marker, event)
                        self.assertEqual(c.read(strength.LAST_DISPLAYED, 4), self.PREVIOUS_GENERATION)
                        self.assertLessEqual(c.read(RECENT, 2), 700 if sustained else 0)
                        if not sustained:
                            self.assertEqual(c.read(followup.GRADE), 0)
                        self.boundary(c)
                        if kind != 'gain' or mode != 0:
                            self.assertEqual(c.read(RECENT, 2), 0)
                        self.assertEqual(c.read(BEEP), 100 if kind == 'mode' else 0)

    def test_invalidations_at_every_unmasked_curve_and_publication_instruction_keep_ownership(self):
        cases = 0
        for mode in (0, 1):
            ranges = ((self.curve, self.parent.clean_strength['tim1']),
                      (age.PUBLISH, age.PUBLISH+4),
                      (self.img.sample_age_guard['publish'], self.img.sample_age_guard['refresh']),
                      (commit.PUBLISHER, commit.PUBLISHER+commit.PUBLISHER_SIZE))
            points = sorted(address for address, mask in self.trace(self.ready(mode))
                            if not mask and any(lo <= address < hi for lo, hi in ranges))
            self.assertGreater(len(points), 50)
            for kind in ('gate', 'mode', 'gain'):
                for point in points:
                    c = self.ready(mode)
                    seen = []
                    def event(cpu):
                        seen.append(cpu.read(strength.LAST_DISPLAYED, 4))
                        if kind == 'gate':
                            self.execute(cpu, sampling_fixes.PUBLISH_GATE, 0, stack=SP-0x500)
                            self.execute(cpu, sampling_fixes.PUBLISH_GATE, 4095, stack=SP-0x500)
                        elif kind == 'mode':
                            cpu.w16(0x2000010E, 6)
                            self.execute(cpu, followup.KEY, stack=SP-0x500)
                        else:
                            cpu.w32(TICK, 499)
                            self.timer(cpu)
                    self.interrupt(c, followup.ANALYZERS[mode], point, event)
                    self.assertEqual(c.read(strength.LAST_DISPLAYED, 4), seen[0],
                        (mode, kind, hex(point), 'invalidation must not acquire a new publication stamp'))
                    if seen[0] == self.PREVIOUS_GENERATION:
                        self.assertEqual(c.read(RECENT, 2), 0, (mode, kind, hex(point)))
                    cases += 1
        print('Publication commit: real gate/mode/gain invalidations at', cases, 'unmasked handoff boundaries')

    def test_expiry_during_analysis_does_not_commit_even_if_the_next_window_is_fresh(self):
        for mode, limit in ((0, age.DIGITAL_MAX_AGE_TICKS), (1, age.ANALOG_MAX_AGE_TICKS)):
            for next_window in (False, True):
                c = self.ready(mode)
                def delay(cpu):
                    now = self.GENERATION+limit+1
                    cpu.w32(age.TIMER_COUNTER, now)
                    if next_window:
                        cpu.w32(age.COMPLETED_AT, now)
                self.interrupt(c, followup.ANALYZERS[mode], self.after_old_marker, delay)
                self.assertEqual(c.read(strength.LAST_DISPLAYED, 4), self.PREVIOUS_GENERATION)
                self.assertEqual((c.read(followup.GRADE), c.read(RECENT, 2)), (0, 0))
                self.assertEqual(c.read(age.COMPLETED_VALID, 4), 0)

    def test_uninterrupted_feedback_is_bit_identical_to_pn130(self):
        for mode in (0, 1):
            for sustained in (False, True):
                for kind in ('normal', 'clipped', 'rejected'):
                    states = []
                    for previous in (True, False):
                        c = self.ready(mode, previous=previous, sustained=sustained,
                                       clipped=kind == 'clipped', rejected=kind == 'rejected')
                        self.analyze(c)
                        states.append(tuple(c.read(address, size) for address, size in
                            ((followup.GRADE, 1), (RECENT, 2), (level_display.AVERAGE, 4),
                             (level_display.AVERAGE+4, 1), (ACTIVE, 1), (BEEP, 1))))
                    self.assertEqual(states[0], states[1], (mode, sustained, kind))

    def test_hook_guards_reject_damaged_or_duplicate_install_before_mutation(self):
        for site in self.img.publication_commit['guarded_sites']:
            img = copy.deepcopy(self.parent)
            img.data[img.f(site)] ^= 1
            before = bytes(img.data), list(img.log)
            with self.assertRaises(PatchError):
                commit.install(img)
            self.assertEqual((bytes(img.data), img.log), before)
        before = bytes(self.img.data), list(self.img.log)
        with self.assertRaises(PatchError):
            commit.install(self.img)
        self.assertEqual((bytes(self.img.data), self.img.log), before)

    def test_patch_uses_only_existing_publisher_padding_and_marker_instruction(self):
        self.assertEqual(len(self.data), len(self.old_data))
        changed = {0x08006800+i for i, (old, new) in enumerate(zip(self.old_data, self.data)) if old != new}
        allowed = set(range(commit.PUBLISHER, commit.PUBLISHER+commit.PUBLISHER_SIZE))
        allowed.update(range(commit.EARLY_MARKER, commit.EARLY_MARKER+2))
        self.assertTrue(changed)
        self.assertLessEqual(changed, allowed)
        self.assertEqual(self.img.publication_commit['publisher_bytes'], 96)
        self.assertEqual(self.img.publication_commit['persistent_ram_bytes'], 0)


class ResilientIntegration(unittest.TestCase):
    def test_pn131_composition_preserves_publication_lifecycle_and_preemption_contracts(self):
        import rx_resilient
        PublicationCommit.setUpClass()
        harness = PublicationCommit()
        harness.img = rx_resilient.build_candidate()
        harness.data = bytes(harness.img.data)
        harness.test_fast_gain_waits_for_successful_publication()
        harness.test_fast_gain_at_every_unmasked_analyzer_instruction_sees_a_committed_frame()
        harness.test_marker_store_is_masked_after_feedback_and_restores_entry_mask()
        harness.test_timer_pending_at_every_masked_publisher_instruction_runs_after_commit()
        harness.test_marker_commits_analyzed_timestamp_not_next_completed_adc_window()
        harness.test_rejected_windows_never_authorize_fast_gain_or_extend_feedback()
        harness.test_real_gate_mode_and_gain_invalidations_never_commit_a_discarded_window()
        harness.test_invalidations_at_every_unmasked_curve_and_publication_instruction_keep_ownership()
        harness.test_expiry_during_analysis_does_not_commit_even_if_the_next_window_is_fresh()


if __name__ == '__main__':
    unittest.main()
