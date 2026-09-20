"""PN 1.9: independent code-conditioned strength and uncertainty regressions.

The CPU receives synthetic ADC windows. These tests establish instruction and
ownership contracts, not analogue selectivity, cable identity, or real timing.
The reference groups raw samples mathematically; it does not reproduce the
firmware's tagged in-place sorting implementation.
"""
from pathlib import Path
import random
import statistics
import struct
import unittest

from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm_const import (UC_ARM_REG_C1_C0_2, UC_ARM_REG_FPEXC,
                               UC_ARM_REG_PRIMASK, UC_ARM_REG_R0, UC_ARM_REG_R12)

from lpm10rx.image import PatchError
import test_rx_followup
import test_rx_pinpoint
import test_rx_precision
from test_rx_followup import ANALYZERS, GATE_STATE, GRADE, KEY, REQUEST, SPEAKER
from test_rx_pinpoint import expected_gap, raw_gap
from test_rx_precision import eligibility_cases, strength
from verify_control import BEEP, Control, SP
from verify_digital import ACTIVE, BUFFER, GAP, GATE, RECENT, pattern, reference

SIGNATURE = (1, 0, 1, 1, 0, 1, 1, 0)
UNCERTAIN = 1


class _FastControl(Control):
    """Keep the shared mock calls without two FFI reads per DSP instruction."""
    MOCK_ENTRIES = frozenset((0x08008108, 0x0800AF08, 0x08008170, 0x08008184,
                             0x08008198, 0x08007570, 0x08007770, 0x080084D8,
                             0x08008224, 0x0800ADC0))

    def hook(self, uc, addr, size, user):
        if addr in self.MOCK_ENTRIES:
            super().hook(uc, addr, size, user)


def measurement(samples):
    """Return (accepted, score, reason, phase, amplitude) independently."""
    if not reference(samples):
        return False, 0, 'rejected', None, None
    threshold = sum(sorted(samples)[1:-1]) // 46
    observed = [value > threshold for value in samples]
    fits = []
    for phase in range(8):
        expected = [SIGNATURE[(i + phase) % 8] for i in range(48)]
        errors = [bit != wanted for bit, wanted in zip(observed, expected)]
        if sum(errors) <= 4 and all(sum(errors[i:i+16]) <= 2 for i in (0, 16, 32)):
            fits.append((phase, expected))
    if fits:
        assert len(fits) == 1, 'B6 rotations are farther apart than two error budgets'
        phase, expected = fits[0]
        selected = range(48)
        reason = 'measured'
    else:
        phase, expected = None, observed
        starts = [i for i in range(33) if observed[i:i+16] == list(SIGNATURE*2)]
        selected = sorted({i for start in starts for i in range(start, start+16)})
        assert len(starts) >= 2
        assert len(selected) >= 24
        assert sum(not observed[i] for i in selected) >= 9
        assert sum(observed[i] for i in selected) >= 15
        reason = 'exact_union'
    low = int(statistics.median(samples[i] for i in selected if not expected[i]))
    high = int(statistics.median(samples[i] for i in selected if expected[i]))
    amplitude = high - low
    if high == 4095:
        return True, 0, 'upper_rail', phase, amplitude
    if amplitude <= 0:
        return True, 0, 'inseparable', phase, amplitude
    # Evaluate the preceding release's definition on the fitted ideal waveform.
    # This independently checks the assembly's integer scale conversion.
    score = strength(pattern(low=low, high=high))
    return True, score, reason, phase, amplitude


def feedback(samples, previous=0, recent=0):
    accepted, score, _, _, _ = measurement(samples)
    if not accepted:
        return 0
    return expected_gap(score, previous, recent) if score else UNCERTAIN


def candidate():
    import robust_fixes
    img = test_rx_pinpoint.candidate()
    robust_fixes.apply(img)
    return img


class Robust(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.previous = bytes(test_rx_pinpoint.candidate().data)
        cls.img = candidate()
        cls.data = bytes(cls.img.data)

    execute = test_rx_followup.Followup.execute
    boundary = test_rx_followup.Followup.boundary
    acquire = test_rx_followup.Followup.acquire
    tick = test_rx_precision.Precision.tick
    map_score = test_rx_pinpoint.Pinpoint.map_score

    def cpu(self, data=None):
        c = _FastControl(self.data if data is None else data)
        c.uc.reg_write(UC_ARM_REG_C1_C0_2, 0xF00000)
        c.uc.reg_write(UC_ARM_REG_FPEXC, 0x40000000)
        c.w16(GATE, 2)
        c.w16(GATE+2, 1)
        c.w8(GATE_STATE, 2)
        return c

    def detect(self, c, samples, recent=None, grade=None):
        c.uc.mem_write(BUFFER, struct.pack('<48H', *samples))
        c.w8(ACTIVE, 0)
        if recent is not None:
            c.w16(RECENT, recent)
        if grade is not None:
            c.w8(GRADE, grade)
        self.execute(c, ANALYZERS[0], budget=30000)
        return c.read(GRADE) > 0

    def test_legacy_corpus_preserves_eligibility_and_matches_independent_measurement(self):
        import robust_fixes
        c = self.cpu()
        reasons = set()
        scores = []
        def at_mapper(uc, addr, size, user):
            scores.append(uc.reg_read(UC_ARM_REG_R0))
        hook = c.uc.hook_add(UC_HOOK_CODE, at_mapper,
                            begin=robust_fixes.GAP_HELPER, end=robust_fixes.GAP_HELPER)
        try:
            for number, samples in enumerate(eligibility_cases()):
                scores.clear()
                c.w8(BEEP, 17)
                c.w8(GAP, 23)
                accepted = self.detect(c, samples, recent=321, grade=0)
                result = measurement(samples)
                self.assertEqual(accepted, reference(samples), number)
                self.assertEqual(c.read(GRADE), feedback(samples), (number, result))
                self.assertEqual(scores, [result[1]] if result[1] else [], (number, result))
                self.assertEqual(c.read(RECENT, 2), 800 if accepted else 321, number)
                self.assertEqual((c.read(BEEP), c.read(GAP), c.read(ACTIVE)), (17, 23, 1), number)
                reasons.add(result[2])
        finally:
            c.uc.hook_del(hook)
        self.assertTrue({'rejected', 'measured', 'exact_union', 'upper_rail'} <= reasons)

    def test_clean_phase_dc_and_amplitude_sweep_preserves_pn18_scale(self):
        c = self.cpu()
        deltas = sorted(set(range(9, 4095, 41)) | {10, 60, 100, 150, 300, 1000, 3100, 4094})
        gaps = []
        for delta in deltas:
            for phase in range(8):
                for low in sorted({0, min(1000, 4094-delta), 4094-delta}):
                    samples = pattern(phase, low, low+delta)
                    accepted = self.detect(c, samples, recent=0, grade=0)
                    self.assertEqual(accepted, reference(samples), (phase, low, delta))
                    if accepted:
                        self.assertEqual(measurement(samples)[1], strength(samples))
                        self.assertEqual(c.read(GRADE), raw_gap(strength(samples)), (phase, low, delta))
                        self.assertEqual(measurement(samples)[4], delta)
            if reference(pattern(low=0, high=delta)):
                gaps.append(feedback(pattern(low=0, high=delta)))
        self.assertEqual(gaps, sorted(gaps, reverse=True))
        self.assertGreater(len(set(gaps)), 30)
        self.assertGreater(strength(pattern(low=0, high=3100)), 65535)

    def test_one_to_four_wrong_bits_keep_code_amplitude(self):
        c = self.cpu()
        sets = [(i,) for i in range(48)]
        sets += [(8, 24, 40), (0, 1, 16, 32), (1, 7, 23, 38), (15, 16, 31, 32)]
        for phase in range(8):
            clean = pattern(phase, 1000, 1100)
            for wrong in sets:
                samples = pattern(phase, 1000, 1100, wrong)
                self.assertTrue(reference(samples), (phase, wrong))
                self.assertTrue(self.detect(c, samples, recent=0, grade=0))
                self.assertEqual(measurement(samples)[3:], (phase, 100))
                self.assertEqual(c.read(GRADE), feedback(clean), (phase, wrong))

    def test_four_impulses_no_longer_reverse_weak_and_stronger_signal(self):
        c = self.cpu()
        for phase in range(8):
            clean = pattern(phase, 1000, 1100)
            polluted = clean[:]
            highs = [i for i, value in enumerate(clean) if value == 1100]
            lows = [i for i, value in enumerate(clean) if value == 1000]
            for index in highs[:2]:
                polluted[index] += 1000
            for index in lows[:2]:
                polluted[index] -= 1000
            stronger = pattern(phase, 1000, 1150)
            self.assertLess(raw_gap(strength(polluted)), raw_gap(strength(stronger)))
            actual = []
            for samples in (clean, polluted, stronger):
                self.assertTrue(self.detect(c, samples, recent=0, grade=0))
                actual.append(c.read(GRADE))
            self.assertEqual(actual, [109, 109, 100], phase)

    def test_sparse_impulses_all_positions_and_seeded_multiple_outliers(self):
        c = self.cpu()
        rng = random.Random(0x190B6)
        for phase in range(8):
            clean = pattern(phase, 2000, 2010)
            cases = []
            for index in range(48):
                for spike in (0, 4095):
                    samples = clean[:]
                    samples[index] = spike
                    cases.append(samples)
            for count in (2, 3, 4):
                for _ in range(32):
                    samples = clean[:]
                    for index in rng.sample(range(48), count):
                        samples[index] = rng.choice((0, 4095, rng.randrange(4096)))
                    cases.append(samples)
            for number, samples in enumerate(cases):
                accepted = self.detect(c, samples, recent=0, grade=0)
                self.assertEqual(accepted, reference(samples), (phase, number))
                self.assertEqual(c.read(GRADE), feedback(samples), (phase, number))
                if accepted and measurement(samples)[2] == 'measured':
                    self.assertEqual(measurement(samples)[4], 10, (phase, number))
                    self.assertEqual(c.read(GRADE), feedback(clean), (phase, number))

    def test_even_group_medians_average_both_central_values_with_floor(self):
        c = self.cpu()
        rng = random.Random(1909)
        for phase in range(8):
            bits = pattern(phase, 0, 1)
            lows = list(range(1000, 1018))
            highs = list(range(1200, 1230))
            for reverse in (False, True):
                lo, hi = sorted(lows, reverse=reverse), sorted(highs, reverse=reverse)
                samples = [hi.pop() if bit else lo.pop() for bit in bits]
                self.assertEqual(measurement(samples)[4], 206)
                self.assertTrue(self.detect(c, samples, recent=0, grade=0))
                self.assertEqual(c.read(GRADE), feedback(samples))
            for _ in range(12):
                rng.shuffle(lows)
                rng.shuffle(highs)
                lo, hi = iter(lows), iter(highs)
                samples = [next(hi) if bit else next(lo) for bit in bits]
                self.assertTrue(self.detect(c, samples, recent=0, grade=0))
                self.assertEqual(c.read(GRADE), feedback(samples))

    def test_exact_only_finds_use_only_selected_codes_and_ignore_untrusted_tail(self):
        c = self.cpu()
        for suffix in (500, 1000, 1500):
            samples = pattern()[:24]+[suffix]*24
            self.assertEqual(measurement(samples)[2], 'exact_union')
            self.assertEqual(measurement(samples)[4], 1000)
            for previous in (0, 1, 20, 75, 158, 159, 160):
                self.assertTrue(self.detect(c, samples, recent=800, grade=previous))
                self.assertEqual((c.read(GRADE), c.read(RECENT, 2)),
                                 (expected_gap(strength(pattern()), previous, 800), 800))
        for samples in ([1000]*48, pattern()[:16]+[500]*32):
            self.assertFalse(reference(samples))
            self.assertFalse(self.detect(c, samples, recent=560, grade=UNCERTAIN))
            self.assertEqual((c.read(GRADE), c.read(RECENT, 2)), (0, 560))
        for tail in ([0, 2000]*12, [500+i*43 for i in range(24)], [1250, 750]*12):
            samples = pattern()[:24]+tail
            self.assertEqual(measurement(samples)[2:], ('exact_union', None, 1000))
            self.assertTrue(self.detect(c, samples, recent=0, grade=0))
            self.assertEqual(c.read(GRADE), feedback(pattern()))

    def test_overlapping_exact_windows_are_deduplicated_before_group_medians(self):
        c = self.cpu()
        samples = pattern()[:24]+[500]*24
        # These three lows belong to BOTH exact windows. Double-counting them
        # would produce a 250-count low median instead of the union's 500.
        for index in (9, 12, 15):
            samples[index] = 0
        self.assertEqual(measurement(samples)[2:], ('exact_union', None, 1000))
        self.assertTrue(self.detect(c, samples, recent=0, grade=0))
        self.assertEqual(c.read(GRADE), feedback(pattern()))

    def test_exact_union_handles_disjoint_matches_and_changed_global_phase(self):
        c = self.cpu()
        for second_start in (17, 19, 23, 24, 25, 31, 32):
            samples = pattern()[:16]+[500]*(second_start-16)+pattern()[:16]
            samples += [500]*(48-len(samples))
            self.assertEqual(measurement(samples)[2:], ('exact_union', None, 1000), second_start)
            self.assertTrue(self.detect(c, samples, recent=0, grade=0))
            self.assertEqual(c.read(GRADE), feedback(pattern()), second_start)

    def test_minimum_exact_union_resists_four_code_consistent_outliers(self):
        c = self.cpu()
        clean = pattern()[:24]+[500]*24
        for level, replacement in ((500, 0), (1500, 4095)):
            indices = [i for i in range(24) if clean[i] == level]
            for positions in (indices[:4], indices[-4:], indices[1:5]):
                samples = clean[:]
                for index in positions:
                    samples[index] = replacement
                self.assertEqual(measurement(samples)[2:], ('exact_union', None, 1000), positions)
                self.assertTrue(self.detect(c, samples, recent=0, grade=0))
                self.assertEqual(c.read(GRADE), feedback(pattern()), positions)

    def test_variable_odd_and_even_union_medians_match_exact_unrounded_score(self):
        import robust_fixes
        c = self.cpu()
        scores = []
        def at_mapper(uc, addr, size, user):
            scores.append(uc.reg_read(UC_ARM_REG_R0))
        hook = c.uc.hook_add(UC_HOOK_CODE, at_mapper,
                            begin=robust_fixes.GAP_HELPER, end=robust_fixes.GAP_HELPER)
        try:
            for span in (24, 32, 40):
                bits = pattern(low=0, high=1)[:span]
                lo, hi = iter(range(600, 1000, 20)), iter(range(2200, 2800, 20))
                samples = [next(hi) if bit else next(lo) for bit in bits]+[500]*(48-span)
                result = measurement(samples)
                self.assertEqual(result[2], 'exact_union')
                scores.clear()
                self.assertTrue(self.detect(c, samples, recent=0, grade=0))
                self.assertEqual(scores, [result[1]], (span, result))
        finally:
            c.uc.hook_del(hook)

    def test_median_leaf_all_counts_full_u16_range_empty_null_and_no_writes(self):
        import robust_fixes
        c = self.cpu()
        rng = random.Random(0xB584)
        writes = []
        hook = c.uc.hook_add(UC_HOOK_MEM_WRITE,
                            lambda uc, access, addr, size, value, user: writes.append((addr, size)))
        try:
            self.assertEqual(self.execute(c, robust_fixes.MEDIAN, 0, 0), 65535)
            for count in range(1, 49):
                arrays = ([0]*count, [65535]*count,
                          sorted([0, 65535]*(count//2)+([12345] if count % 2 else [])),
                          sorted(rng.randrange(65536) for _ in range(count)))
                for values in arrays:
                    c.uc.mem_write(BUFFER, struct.pack('<'+'H'*count, *values))
                    c.uc.reg_write(UC_ARM_REG_R12, 0x1212ABCD)
                    self.assertEqual(self.execute(c, robust_fixes.MEDIAN, BUFFER, count),
                                     int(statistics.median(values)), (count, values))
                    self.assertEqual(c.uc.reg_read(UC_ARM_REG_R12), 0x1212ABCD)
            self.assertEqual(writes, [])
        finally:
            c.uc.hook_del(hook)

    def test_upper_rail_dominated_fit_is_uncertain_but_zero_low_is_permitted(self):
        c = self.cpu()
        for phase in range(8):
            clean = pattern(phase, 0, 3500)
            highs = [i for i, value in enumerate(clean) if value]
            for clipped in (0, 1, 14, 15, 16, 29, 30):
                samples = clean[:]
                for index in highs[:clipped]:
                    samples[index] = 4095
                self.assertTrue(self.detect(c, samples, recent=0, grade=0))
                self.assertEqual(c.read(GRADE), feedback(samples), (phase, clipped))
                self.assertEqual(c.read(GRADE) == UNCERTAIN, clipped >= 16, (phase, clipped))
            for low in (0, 1000, 4000):
                self.assertTrue(self.detect(c, pattern(phase, low, 4095), recent=800, grade=20))
                self.assertEqual(c.read(GRADE), UNCERTAIN)

    def test_uncertainty_uses_long_pulses_and_normal_measurement_recovers(self):
        overloaded = pattern(low=1000, high=4095)
        for uncertain_first in (True, False):
            first, second = (overloaded, pattern()) if uncertain_first else (pattern(), overloaded)
            c = self.cpu()
            self.assertTrue(self.detect(c, first))
            self.execute(c, SPEAKER)
            expected_first = (100, 160) if uncertain_first else (30, feedback(pattern()))
            self.assertEqual((c.read(BEEP), c.read(GAP)), expected_first)
            self.tick(c)
            active = c.read(BEEP), c.read(GAP)
            self.assertTrue(self.detect(c, second))
            self.assertEqual((c.read(BEEP), c.read(GAP)), active)
            for _ in range(sum(expected_first)-2):
                self.tick(c)
            expected_second = (30, feedback(pattern())) if uncertain_first else (100, 160)
            self.assertEqual((c.read(BEEP), c.read(GAP)), expected_second)

    def test_uncertainty_expiry_completes_current_pulse_before_400ms(self):
        c = self.cpu()
        c.w8(GRADE, UNCERTAIN)
        c.w16(RECENT, 800)
        self.execute(c, SPEAKER)
        self.assertEqual((c.read(BEEP), c.read(GAP)), (100, 160))
        starts, last_sound = [0], 0
        for tick in range(1, 801):
            before = c.read(BEEP)
            self.tick(c)
            after = c.read(BEEP)
            if not before and after:
                starts.append(tick)
            if after:
                last_sound = tick
        self.assertEqual(starts, [0, 259])
        self.assertLess(last_sound, 400)
        self.assertEqual((c.read(BEEP), c.read(RECENT, 2)), (0, 0))

    def test_key_confirmation_survives_uncertainty_windows(self):
        c = self.cpu()
        c.w16(0x20000112, 6)
        self.execute(c, KEY)
        self.assertEqual(c.read(BEEP), 100)
        for tick in range(1, 100):
            c.run()
            self.assertTrue(self.detect(c, pattern(low=1000, high=4095)))
            self.execute(c, SPEAKER)
            self.assertEqual(c.read(BEEP), 100-tick)

    def test_snapshot_ownership_stack_bound_and_interruptible_sort(self):
        import robust_fixes
        for interrupt in (False, True):
            c = self.cpu()
            writes, seen = [], []
            def memory(uc, access, addr, size, value, user):
                writes.append((addr, size))
                if addr == ACTIVE and value == 1:
                    uc.mem_write(BUFFER, bytes(128))
            def step(uc, addr, size, user):
                if addr == robust_fixes.ESTIMATOR:
                    seen.append(addr)
                    self.assertEqual(uc.reg_read(UC_ARM_REG_PRIMASK), 0)
                    if interrupt:
                        c.w8(REQUEST, 2)
                        c.w8(BEEP, 100)
            hook = c.uc.hook_add(UC_HOOK_MEM_WRITE, memory)
            code = c.uc.hook_add(UC_HOOK_CODE, step)
            samples = pattern(low=1000, high=1500)
            self.detect(c, samples, recent=560, grade=77)
            c.uc.hook_del(hook)
            c.uc.hook_del(code)
            self.assertTrue(seen)
            self.assertEqual(c.read(GRADE), 77 if interrupt else feedback(samples, 77, 560))
            self.assertEqual(c.read(RECENT, 2), 560 if interrupt else 800)
            self.assertEqual((c.read(BEEP), c.read(GAP)), (100 if interrupt else 0, 0))
            allowed = {(ACTIVE, 1), (GRADE, 1), (RECENT, 2)}
            self.assertEqual([(hex(addr), size) for addr, size in writes
                              if not (SP-152 <= addr and addr+size <= SP or (addr, size) in allowed)], [])

    def test_adversarial_sort_orders_stay_inside_instruction_budget(self):
        c = self.cpu()
        cases = []
        for phase in range(8):
            for descending in (False, True):
                lo = iter(sorted(range(1000, 1018), reverse=descending))
                hi = iter(sorted(range(2000, 2030), reverse=descending))
                cases.append([next(hi) if bit else next(lo) for bit in pattern(phase, 0, 1)])
        for offset in range(25):
            cases.append([500]*offset+pattern()[:24]+[500]*(24-offset))
        steps = [0]
        def count(uc, addr, size, user):
            steps[0] += 1
        hook = c.uc.hook_add(UC_HOOK_CODE, count)
        try:
            for number, samples in enumerate(cases):
                steps[0] = 0
                self.assertTrue(self.detect(c, samples, recent=0, grade=0))
                self.assertEqual(c.read(GRADE), feedback(samples), number)
                self.assertLess(steps[0], 20000, (number, steps[0]))
        finally:
            c.uc.hook_del(hook)

    def test_build_exact_patch_log_prior_artifact_and_unchanged_audio_mapper(self):
        import pinpoint_fixes
        import robust_fixes
        fw = Path(__file__).resolve().parent.parent
        self.assertEqual((fw / robust_fixes.OUTPUT).read_bytes(), self.data)
        self.assertEqual((fw / pinpoint_fixes.OUTPUT).read_bytes(), self.previous)
        self.assertEqual(len(self.data), len(self.previous))
        rebuilt = bytearray(self.img.original)
        for address, before, after, reason, kind in self.img.log:
            offset = address-0x08006800
            self.assertEqual(bytes(rebuilt[offset:offset+len(before)]), before, reason)
            rebuilt[offset:offset+len(after)] = after
        self.assertEqual(bytes(rebuilt), self.data)
        changed = {offset+0x08006800 for offset, (before, after)
                   in enumerate(zip(self.previous, self.data)) if before != after}
        allowed = (set(range(0x08009E08, 0x08009F20)) |
                   set(range(0x0800B630, 0x0800B70C)) |
                   set(range(0x0800B584, 0x0800B5A0)) |
                   set(range(0x080086EC, 0x0800870E)))
        self.assertTrue(changed <= allowed, [hex(addr) for addr in sorted(changed-allowed)])
        for start, end in ((0x08006800, 0x08006948), (0x08009F20, 0x08009F58),
                           (0x0800A048, 0x0800A0A4), (0x0800BAE8, 0x0800BBB0)):
            self.assertEqual(self.data[start-0x08006800:end-0x08006800],
                             self.previous[start-0x08006800:end-0x08006800])

    def test_prior_battery_adc_dft_and_timer_instructions_are_preserved(self):
        for label, start, end in (
                ('serialized ADC transaction', 0x080072A4, 0x080072E8),
                ('critical battery recovery', 0x08007770, 0x080078B0),
                ('TIM1 countdowns and power handling', 0x0800A97C, 0x0800AC1C),
                ('DFT overflow correction before reclaimed padding', 0x0800B4A0, 0x0800B584),
                ('remaining DFT tail', 0x0800B5A0, 0x0800B630)):
            self.assertEqual(self.data[start-0x08006800:end-0x08006800],
                             self.previous[start-0x08006800:end-0x08006800], label)

    def test_wrong_parent_tampering_and_double_application_fail_without_mutation(self):
        import robust_fixes
        for img in (test_rx_precision.candidate(), candidate()):
            before = bytes(img.data)
            with self.assertRaises(PatchError):
                robust_fixes.apply(img)
            self.assertEqual(bytes(img.data), before)
        img = test_rx_pinpoint.candidate()
        img.data[0x100] ^= 1
        before = bytes(img.data)
        with self.assertRaises(PatchError):
            robust_fixes.apply(img)
        self.assertEqual(bytes(img.data), before)

    # Reuse unchanged external contracts against PN 1.9's actual ARM image.
    test_mapper_matches_rational_interpolation_across_all_segments_and_32bit_range = test_rx_pinpoint.Pinpoint.test_mapper_matches_rational_interpolation_across_all_segments_and_32bit_range
    test_three_ms_deadband_is_exact_and_resets_on_stale_or_no_previous_gap = test_rx_pinpoint.Pinpoint.test_three_ms_deadband_is_exact_and_resets_on_stale_or_no_previous_gap
    test_new_strength_updates_only_the_next_beep_after_current_countdowns_finish = test_rx_pinpoint.Pinpoint.test_new_strength_updates_only_the_next_beep_after_current_countdowns_finish
    test_missing_windows_stop_repeats_by_300ms_without_truncating_a_tone = test_rx_pinpoint.Pinpoint.test_missing_windows_stop_repeats_by_300ms_without_truncating_a_tone
    test_in_progress_or_invalidated_windows_preserve_previous_gap = test_rx_pinpoint.Pinpoint.test_in_progress_or_invalidated_windows_preserve_previous_gap
    test_scheduler_freshness_guards_and_existing_countdowns = test_rx_pinpoint.Pinpoint.test_scheduler_freshness_guards_and_existing_countdowns
    test_publisher_mode_gate_guards_and_interrupt_mask_for_accept_and_reject = test_rx_pinpoint.Pinpoint.test_publisher_mode_gate_guards_and_interrupt_mask_for_accept_and_reject
    test_key_request_at_every_mapper_publication_and_scheduler_instruction = test_rx_pinpoint.Pinpoint.test_key_request_at_every_mapper_publication_and_scheduler_instruction
    test_completed_reject_stops_repeats_without_clearing_activity_hold = test_rx_precision.Precision.test_completed_reject_stops_repeats_without_clearing_activity_hold
    test_all_directed_mode_changes_discard_partial_and_completed_windows = test_rx_followup.Followup.test_all_directed_mode_changes_discard_partial_and_completed_windows
    test_key_request_during_analysis_rejects_old_result_and_keeps_confirmation = test_rx_followup.Followup.test_key_request_during_analysis_rejects_old_result_and_keeps_confirmation
    test_digital_and_analog_gate_reopening_requires_complete_fresh_window = test_rx_followup.Followup.test_digital_and_analog_gate_reopening_requires_complete_fresh_window
    test_analog_and_mains_threshold_responses_match_previous_release = test_rx_followup.Followup.test_analog_and_mains_threshold_responses_match_previous_release


if __name__ == '__main__':
    unittest.main()
