"""PN 1.8 interpolated tracing feedback, checked against rational arithmetic.

Runs the actual ARM detector, mapper, publication and scheduler. ADC/GPIO and
interrupt arrival remain modeled; these tests do not establish cable identity,
physical range, or the audible usefulness of particular cadence differences.
"""
from bisect import bisect_right
from fractions import Fraction
from functools import lru_cache
import math
from pathlib import Path
import struct
import unittest

from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm_const import *

from lpm10rx.image import PatchError
import test_rx_precision
import test_rx_followup
from test_rx_precision import strength, eligibility_cases
from test_rx_followup import GRADE, REQUEST, GATE_STATE, ANALYZERS, KEY, SPEAKER
from verify_control import BEEP, SP
from verify_digital import ACTIVE, BUFFER, GAP, RECENT, pattern, reference

STRENGTH_KNOTS = (0, 800, 2400, 7200, 24000, 88000)
GAP_KNOTS = (160, 130, 105, 75, 45, 20)


def raw_gap(score):
    """Ceil the exact interpolated duration, independent of ARM mul/div order."""
    if score >= STRENGTH_KNOTS[-1]:
        return GAP_KNOTS[-1]
    segment = bisect_right(STRENGTH_KNOTS, score)-1
    lo, hi = STRENGTH_KNOTS[segment:segment+2]
    at_lo, at_hi = GAP_KNOTS[segment:segment+2]
    return math.ceil(Fraction(at_lo*(hi-score)+at_hi*(score-lo), hi-lo))


def expected_gap(score, previous=0, recent=0):
    value = raw_gap(score)
    return previous if previous and recent > 500 and abs(value-previous) < 3 else value


@lru_cache(maxsize=None)
def score_for_gap(gap):
    """Find the first metric producing a selected integer gap, using the model."""
    lo, hi = 0, STRENGTH_KNOTS[-1]
    while lo < hi:
        mid = (lo+hi)//2
        if raw_gap(mid) <= gap:
            hi = mid
        else:
            lo = mid+1
    if raw_gap(lo) != gap:
        raise AssertionError(f'gap {gap} is unreachable')
    return lo


def candidate():
    import pinpoint_fixes
    img = test_rx_precision.candidate()
    pinpoint_fixes.apply(img)
    return img


class Pinpoint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.previous = bytes(test_rx_precision.candidate().data)
        cls.img = candidate()
        cls.data = bytes(cls.img.data)

    cpu = test_rx_followup.Followup.cpu
    execute = test_rx_followup.Followup.execute
    boundary = test_rx_followup.Followup.boundary
    acquire = test_rx_followup.Followup.acquire
    detect = test_rx_precision.Precision.detect
    tick = test_rx_precision.Precision.tick

    def map_score(self, c, score, previous=0, recent=0):
        from pinpoint_fixes import GAP_HELPER
        c.w8(GRADE, previous)
        c.w16(RECENT, recent)
        self.execute(c, GAP_HELPER, score)
        return c.read(GRADE)

    def test_mapper_matches_rational_interpolation_across_all_segments_and_32bit_range(self):
        values = set(range(0, 100001, 257))
        values.update((65534, 65535, 65536, 65537, 70000, 90000, 94185, 98280,
                       0x7FFFFFFF, 0x80000000, 0xFFFFFFFF))
        values.update(knot+offset for knot in STRENGTH_KNOTS for offset in (-1, 0, 1) if knot+offset >= 0)
        values.update(score_for_gap(gap)+offset for gap in range(20, 161)
                      for offset in (-1, 0, 1) if score_for_gap(gap)+offset >= 0)
        c = self.cpu()
        outputs = []
        for score in sorted(values):
            c.w8(BEEP, 17)
            c.w8(GAP, 23)
            self.assertEqual(self.map_score(c, score), raw_gap(score), score)
            self.assertEqual((c.read(BEEP), c.read(GAP), c.read(RECENT, 2)), (17, 23, 800))
            outputs.append(c.read(GRADE))
        self.assertEqual(outputs, sorted(outputs, reverse=True))
        self.assertEqual(set(outputs), set(range(20, 161)))
        for score, gap in zip(STRENGTH_KNOTS, GAP_KNOTS):
            self.assertEqual(self.map_score(c, score), gap)

    def test_three_ms_deadband_is_exact_and_resets_on_stale_or_no_previous_gap(self):
        c = self.cpu()
        for previous in range(20, 161):
            for change in (-3, -2, -1, 0, 1, 2, 3):
                target = previous+change
                if not 20 <= target <= 160:
                    continue
                score = score_for_gap(target)
                for recent in (500, 501):
                    self.assertEqual(self.map_score(c, score, previous, recent),
                                     expected_gap(score, previous, recent), (previous, target, recent))
        for target in range(20, 161):
            score = score_for_gap(target)
            self.assertEqual(self.map_score(c, score, 0, 800), target)
        self.assertEqual(self.map_score(c, 100000, 22, 800), 22)
        self.assertEqual(self.map_score(c, 100000, 23, 800), 20)
        self.assertEqual(self.map_score(c, 0, 158, 800), 158)
        self.assertEqual(self.map_score(c, 0, 157, 800), 160)

    def test_small_ramps_accumulate_against_last_published_gap_and_large_moves_are_immediate(self):
        sequences = (
            ([100, 99, 98, 97, 96, 95, 94], [100, 100, 100, 97, 97, 97, 94]),
            ([100, 101, 102, 103, 104, 105, 106], [100, 100, 100, 103, 103, 103, 106]),
            ([75, 74, 76, 73, 77, 74, 76], [75]*7),
            ([160, 20, 160, 20], [160, 20, 160, 20]),
        )
        for requested, expected in sequences:
            c = self.cpu()
            published = 0
            observed = []
            for target in requested:
                published = self.map_score(c, score_for_gap(target), published, 800)
                observed.append(published)
            self.assertEqual(observed, expected)

    def test_new_strength_updates_only_the_next_beep_after_current_countdowns_finish(self):
        for first_delta, next_delta in ((60, 100), (300, 120), (10, 2500), (2500, 10)):
            first = pattern(low=1000, high=1000+first_delta)
            second = pattern(low=1000, high=1000+next_delta)
            old_gap, new_gap = raw_gap(strength(first)), raw_gap(strength(second))
            for elapsed in (1, 20, 35):
                c = self.cpu()
                self.assertTrue(self.detect(c, first))
                self.execute(c, SPEAKER)
                for _ in range(elapsed):
                    self.tick(c)
                pair = c.read(BEEP), c.read(GAP)
                self.assertTrue(self.detect(c, second))
                self.assertEqual((c.read(BEEP), c.read(GAP)), pair)
                self.assertEqual(c.read(GRADE), new_gap)
                for _ in range(30+old_gap-1-elapsed):
                    self.tick(c)
                self.assertEqual((c.read(BEEP), c.read(GAP)), (30, new_gap))

    def test_full_eligibility_corpus_preserves_acceptance_and_matches_gap_model(self):
        c = self.cpu()
        for number, samples in enumerate(eligibility_cases()):
            c.w8(BEEP, 17)
            c.w8(GAP, 23)
            accepted = self.detect(c, samples, recent=321, grade=0)
            self.assertEqual(accepted, reference(samples), number)
            self.assertEqual(c.read(GRADE), raw_gap(strength(samples)) if accepted else 0, number)
            self.assertEqual(c.read(RECENT, 2), 800 if accepted else 321, number)
            self.assertEqual((c.read(BEEP), c.read(GAP), c.read(ACTIVE)), (17, 23, 1), number)

    def test_strengths_in_the_same_old_band_now_have_different_feedback(self):
        for first, second in ((60, 100), (120, 300), (400, 800), (1000, 2500)):
            previous, current = [], []
            for delta in (first, second):
                samples = pattern(low=1000, high=1000+delta)
                old, new = self.cpu(self.previous), self.cpu()
                self.assertTrue(self.detect(old, samples, recent=0, grade=0))
                self.assertTrue(self.detect(new, samples, recent=0, grade=0))
                self.execute(old, SPEAKER)
                self.execute(new, SPEAKER)
                previous.append(old.read(GAP))
                current.append(new.read(GAP))
                self.assertEqual(new.read(GAP), raw_gap(strength(samples)))
                self.assertEqual(new.read(BEEP), 30)
            self.assertEqual(previous[0], previous[1], (first, second, previous))
            self.assertGreater(current[0]-current[1], 3, (first, second, current))

    def test_wide_adc_sweep_is_monotonic_with_more_than_five_distinct_gaps(self):
        c = self.cpu()
        observed = []
        for delta in sorted(set(range(9, 4096, 17)) | {10, 60, 100, 120, 300, 1000, 3000, 3100, 4095}):
            samples = pattern(low=0, high=delta)
            accepted = self.detect(c, samples, recent=0, grade=0)
            self.assertEqual(accepted, reference(samples), delta)
            if accepted:
                value = c.read(GRADE)
                self.assertEqual(value, raw_gap(strength(samples)), delta)
                observed.append(value)
        self.assertEqual(observed, sorted(observed, reverse=True))
        self.assertGreater(len(set(observed)), 30)
        self.assertTrue(all(20 <= value <= 160 for value in observed))
        self.assertGreater(strength(pattern(low=0, high=3100)), 65535)

    def test_single_adc_window_outlier_retains_weak_signal_feedback(self):
        c = self.cpu()
        for phase in range(8):
            clean = pattern(phase, low=2000, high=2010)
            expected = raw_gap(strength(clean))
            for index in range(48):
                for spike in (0, 4095):
                    samples = clean[:]
                    samples[index] = spike
                    self.assertTrue(self.detect(c, samples, recent=0, grade=0))
                    self.assertEqual(c.read(GRADE), raw_gap(strength(samples)))
                    self.assertEqual(c.read(GRADE), expected, (phase, index, spike))

    def test_sustained_windows_do_not_restart_active_or_quiet_intervals(self):
        for delta in (10, 60, 100, 120, 300, 1000, 2500):
            samples = pattern(low=1000, high=1000+delta)
            gap = raw_gap(strength(samples))
            for arrival_phase in (0, 119, 239):
                c = self.cpu()
                self.assertTrue(self.detect(c, samples))
                self.execute(c, SPEAKER)
                starts, widths, start = [0], [], 0
                for tick in range(1, 1441):
                    before = c.read(BEEP)
                    c.run()
                    if (tick-arrival_phase) % 240 == 0:
                        pair = c.read(BEEP), c.read(GAP)
                        self.assertTrue(self.detect(c, samples))
                        self.assertEqual((c.read(BEEP), c.read(GAP)), pair)
                    self.execute(c, SPEAKER)
                    after = c.read(BEEP)
                    if before and not after:
                        widths.append(tick-start)
                    if not before and after:
                        starts.append(tick)
                        start = tick
                self.assertEqual(starts, list(range(0, 1441, 30+gap-1)), (delta, arrival_phase))
                self.assertTrue(widths and all(width == 30 for width in widths), widths)

    def test_missing_windows_stop_repeats_by_300ms_without_truncating_a_tone(self):
        for gap in (20, 29, 45, 73, 105, 130, 160):
            c = self.cpu()
            c.w8(GRADE, gap)
            c.w16(RECENT, 800)
            self.execute(c, SPEAKER)
            starts, last_sound = [0], 0
            for tick in range(1, 801):
                before = c.read(BEEP)
                self.tick(c)
                after = c.read(BEEP)
                if not before and after:
                    starts.append(tick)
                if after:
                    last_sound = tick
                if tick == 300:
                    self.assertEqual(c.read(RECENT, 2), 500)
            self.assertTrue(all(tick < 300 for tick in starts))
            self.assertLess(last_sound, 330)
            self.assertEqual((c.read(BEEP), c.read(RECENT, 2)), (0, 0))

    def test_key_feedback_survives_accept_reject_and_audio_expiry(self):
        for samples in (pattern(low=1000, high=2000), [1000]*48):
            c = self.cpu()
            c.w16(0x20000112, 6)
            self.execute(c, KEY)
            self.assertEqual(c.read(BEEP), 100)
            for tick in range(1, 100):
                c.run()
                self.detect(c, samples)
                self.execute(c, SPEAKER)
                self.assertEqual(c.read(BEEP), 100-tick)
        c = self.cpu()
        c.w8(BEEP, 73)
        c.w8(GRADE, 20)
        c.w16(RECENT, 500)
        for elapsed in range(1, 74):
            self.tick(c)
            self.assertEqual(c.read(BEEP), 73-elapsed)

    def test_in_progress_or_invalidated_windows_preserve_previous_gap(self):
        for active, request, state in ((1, 0, 2), (2, 0, 1), (0, 0, 0), (0, 0, 1),
                                      (0, 1, 2), (0, 2, 2), (0, 3, 2)):
            for samples in (pattern(), [1000]*48):
                c = self.cpu()
                c.uc.mem_write(BUFFER, struct.pack('<48H', *samples))
                c.w8(ACTIVE, active)
                c.w8(REQUEST, request)
                c.w8(GATE_STATE, state)
                c.w8(GRADE, 77)
                c.w16(RECENT, 560)
                c.w8(BEEP, 17)
                c.w8(GAP, 23)
                self.execute(c, ANALYZERS[0])
                self.assertEqual((c.read(ACTIVE), c.read(GRADE), c.read(RECENT, 2), c.read(BEEP), c.read(GAP)),
                                 (active, 77, 560, 17, 23))

    def test_scheduler_freshness_guards_and_existing_countdowns(self):
        # The mapper and boundary own this byte; reachable states are 0,20..160.
        for gap_value in (0, 20, 21, 45, 73, 105, 130, 159, 160):
            for recent in (0, 499, 500, 501, 800):
                for mask in (0, 1):
                    c = self.cpu()
                    c.w8(GRADE, gap_value)
                    c.w16(RECENT, recent)
                    c.uc.reg_write(UC_ARM_REG_PRIMASK, mask)
                    self.execute(c, SPEAKER)
                    expected = (30, gap_value) if gap_value and recent > 500 else (0, 0)
                    self.assertEqual((c.read(BEEP), c.read(GAP)), expected)
                    self.assertEqual(c.uc.reg_read(UC_ARM_REG_PRIMASK), mask)
        for request, state in ((0, 2), (1, 2), (2, 2), (3, 2), (0, 0), (0, 1)):
            for beep, gap in ((0, 0), (1, 0), (0, 1), (73, 45)):
                c = self.cpu()
                c.w8(REQUEST, request)
                c.w8(GATE_STATE, state)
                c.w8(GRADE, 77)
                c.w16(RECENT, 800)
                c.w8(BEEP, beep)
                c.w8(GAP, gap)
                self.execute(c, SPEAKER)
                expected = (30, 77) if (request, state, beep, gap) == (0, 2, 0, 0) else (beep, gap)
                self.assertEqual((c.read(BEEP), c.read(GAP)), expected)

    def test_publisher_mode_gate_guards_and_interrupt_mask_for_accept_and_reject(self):
        from pinpoint_fixes import PUBLISH
        for request, state in ((0, 2), (1, 2), (2, 2), (3, 2), (0, 0), (0, 1)):
            for value in (0, 20, 21, 45, 75, 105, 130, 159, 160):
                for mask in (0, 1):
                    c = self.cpu()
                    c.w8(REQUEST, request)
                    c.w8(GATE_STATE, state)
                    c.w8(GRADE, 77)
                    c.w16(RECENT, 560)
                    c.w8(BEEP, 73)
                    c.w8(GAP, 45)
                    c.uc.reg_write(UC_ARM_REG_PRIMASK, mask)
                    writes = []
                    def memory(uc, access, addr, size, content, user):
                        writes.append((addr, size))
                        self.assertEqual(uc.reg_read(UC_ARM_REG_PRIMASK), 1)
                    hook = c.uc.hook_add(UC_HOOK_MEM_WRITE, memory)
                    self.execute(c, PUBLISH, 0, value)
                    c.uc.hook_del(hook)
                    allowed = request == 0 and state == 2
                    self.assertEqual(c.read(GRADE), value if allowed else 77)
                    self.assertEqual(c.read(RECENT, 2), 800 if allowed and value else 560)
                    self.assertEqual((c.read(BEEP), c.read(GAP)), (73, 45))
                    self.assertEqual(c.uc.reg_read(UC_ARM_REG_PRIMASK), mask)
                    self.assertTrue(all(item in ((GRADE, 1), (RECENT, 2)) for item in writes), writes)

    def test_snapshot_overwrite_abi_stack_and_write_ownership(self):
        c = self.cpu()
        writes = []
        def memory(uc, access, addr, size, value, user):
            writes.append((addr, size))
            if addr == ACTIVE and value == 1:
                uc.mem_write(BUFFER, bytes(128))
        hook = c.uc.hook_add(UC_HOOK_MEM_WRITE, memory)
        samples = pattern(low=1000, high=1500)
        self.assertTrue(self.detect(c, samples))
        c.uc.hook_del(hook)
        self.assertEqual(c.read(GRADE), raw_gap(strength(samples)))
        self.assertEqual((c.read(BEEP), c.read(GAP)), (0, 0))
        allowed = {(ACTIVE, 1), (GRADE, 1), (RECENT, 2)}
        self.assertEqual([(hex(addr), size) for addr, size in writes
                          if not (SP-152 <= addr and addr+size <= SP or (addr, size) in allowed)], [])

    def test_key_request_at_every_mapper_publication_and_scheduler_instruction(self):
        from pinpoint_fixes import PUBLISH, GAP_HELPER
        tracked = {GRADE, RECENT, BEEP, GAP}
        for entry, args in ((SPEAKER, ()), (PUBLISH, (0, 0)), (PUBLISH, (0, 75)),
                            (GAP_HELPER, (1296,)), (GAP_HELPER, (7200,)), (GAP_HELPER, (90000,))):
            def fresh():
                c = self.cpu()
                c.w8(GRADE, 75)
                c.w16(RECENT, 800)
                return c
            c = fresh()
            instructions = []
            hook = c.uc.hook_add(UC_HOOK_CODE, lambda uc, addr, size, user: instructions.append(addr))
            self.execute(c, entry, *args)
            c.uc.hook_del(hook)
            for target in range(1, len(instructions)+1):
                c = fresh()
                state = dict(step=0, injected=False, published_before=False)
                writes = []
                def step(uc, addr, size, user):
                    state['step'] += 1
                    if state['step'] >= target and not state['injected'] and not uc.reg_read(UC_ARM_REG_PRIMASK):
                        state['injected'] = True
                        state['published_before'] = bool(writes)
                        c.w8(REQUEST, 2)
                        c.w8(BEEP, 100)
                def memory(uc, access, addr, size, value, user):
                    if addr in tracked:
                        self.assertEqual(uc.reg_read(UC_ARM_REG_PRIMASK), 1, (hex(entry), target, hex(addr)))
                        self.assertFalse(state['injected'] and not state['published_before'], (hex(entry), target))
                        writes.append((addr, size, value))
                code_hook = c.uc.hook_add(UC_HOOK_CODE, step)
                write_hook = c.uc.hook_add(UC_HOOK_MEM_WRITE, memory)
                self.execute(c, entry, *args)
                c.uc.hook_del(code_hook)
                c.uc.hook_del(write_hook)
                self.assertTrue(state['injected'], (hex(entry), target))
                self.assertEqual(c.read(BEEP), 100, (hex(entry), target))
                self.assertEqual(c.uc.reg_read(UC_ARM_REG_PRIMASK), 0)

    def test_image_rebuild_exact_patch_log_and_unchanged_profile(self):
        import pinpoint_fixes
        fw = Path(__file__).resolve().parent.parent
        self.assertEqual((fw / pinpoint_fixes.OUTPUT).read_bytes(), self.data)
        self.assertEqual((fw / 'experimental/APP_LPM-10RX_PN1.7-precision.bin').read_bytes(), self.previous)
        self.assertEqual(len(self.data), len(self.previous))
        rebuilt = bytearray(self.img.original)
        for address, before, after, reason, kind in self.img.log:
            offset = address-0x08006800
            self.assertEqual(bytes(rebuilt[offset:offset+len(before)]), before, reason)
            rebuilt[offset:offset+len(after)] = after
        self.assertEqual(bytes(rebuilt), self.data)
        changed = {address+0x08006800 for address, (old, new) in enumerate(zip(self.previous, self.data)) if old != new}
        allowed = set(range(0x080084FC, 0x08008524)) | set(range(0x080086EC, 0x0800870E)) | set(range(0x0800A048, 0x0800A0A4))
        self.assertTrue(changed <= allowed, sorted(changed-allowed))
        for lo, hi in ((0x08006800, 0x08006948), (0x0800B388, 0x0800B484), (0x0800BAE8, 0x0800BBB0)):
            self.assertEqual(self.data[lo-0x08006800:hi-0x08006800], self.previous[lo-0x08006800:hi-0x08006800])

    def test_wrong_parent_tampering_and_double_application_fail_without_mutation(self):
        import pinpoint_fixes
        for img in (test_rx_followup.candidate(), candidate()):
            before = bytes(img.data)
            with self.assertRaises(PatchError):
                pinpoint_fixes.apply(img)
            self.assertEqual(bytes(img.data), before)
        img = test_rx_precision.candidate()
        img.data[0x100] ^= 1
        before = bytes(img.data)
        with self.assertRaises(PatchError):
            pinpoint_fixes.apply(img)
        self.assertEqual(bytes(img.data), before)

    # Explicit reuse of unchanged contracts; no PN 1.7 grade-number assertions.
    test_completed_reject_stops_repeats_without_clearing_activity_hold = test_rx_precision.Precision.test_completed_reject_stops_repeats_without_clearing_activity_hold
    test_all_directed_mode_changes_discard_partial_and_completed_windows = test_rx_followup.Followup.test_all_directed_mode_changes_discard_partial_and_completed_windows
    test_key_request_during_analysis_rejects_old_result_and_keeps_confirmation = test_rx_followup.Followup.test_key_request_during_analysis_rejects_old_result_and_keeps_confirmation
    test_digital_and_analog_gate_reopening_requires_complete_fresh_window = test_rx_followup.Followup.test_digital_and_analog_gate_reopening_requires_complete_fresh_window
    test_prior_battery_adc_dft_and_timer_fixes_are_byte_exact = test_rx_followup.Followup.test_prior_battery_adc_dft_and_timer_fixes_are_byte_exact


if __name__ == '__main__':
    unittest.main()
