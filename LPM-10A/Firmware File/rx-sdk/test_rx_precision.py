"""PN 1.7 precision feedback: independent models against candidate ARM code.

GPIO/ADC readings and interrupt arrival are modeled. These regressions do not
measure analogue cable selectivity, usable range, or real interrupt deadlines.
"""
import math
from functools import lru_cache
from pathlib import Path
import random
import struct
import unittest

from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm_const import *

from lpm10rx.image import PatchError
import test_rx_followup
from verify_control import BEEP, MODE, SP, STOP
from verify_digital import ACTIVE, BUFFER, GAP, RECENT, pattern, reference, sampled_wave
from test_rx_followup import GRADE, REQUEST, GATE_STATE, ANALYZERS, KEY, SPEAKER

THRESHOLDS = (800, 2400, 7200, 18000)
GAPS = (160, 110, 75, 45, 20)


def strength(samples):
    """Trim extremes first: independent equivalent to the firmware arithmetic."""
    middle = sorted(samples)[1:-1]
    mean = sum(middle)//len(middle)
    return sum(abs(value-mean) for value in middle)


def initial_grade(samples):
    value = strength(samples)
    return 1+sum(value >= boundary for boundary in THRESHOLDS)


def expected_grade(samples, previous, recent):
    value = strength(samples)
    if previous == 0 or recent <= 500:
        return initial_grade(samples)
    boundaries = [boundary * (9 if previous > number else 11)//10
                  for number, boundary in enumerate(THRESHOLDS, 1)]
    return 1+sum(value >= boundary for boundary in boundaries)


@lru_cache(maxsize=None)
def samples_at_strength(target):
    """Find valid coded windows exactly on either side of integer boundaries."""
    center = target*46//986  # ideal trimmed B6 deviation for its 29/17 populations
    for delta in range(max(10, center-3), center+5):
        for high_adjust in range(17):
            for low_adjust in range(17):
                samples = pattern(low=1000, high=1000+delta)
                samples[0] -= high_adjust
                samples[1] += low_adjust
                if strength(samples) == target and reference(samples):
                    return tuple(samples)
    raise AssertionError(f'no exact representative for strength {target}')


def candidate():
    import precision_fixes
    img = test_rx_followup.candidate()
    precision_fixes.apply(img)
    return img


def eligibility_cases():
    """Keep the preceding profile's independent detector corpus unchanged."""
    yield from (pattern(p, lo, hi) for p in range(8)
                for lo, hi in ((0, 1000), (500, 1500), (3000, 3100), (0, 4095)))
    yield from (pattern(p, wrong=(i,)) for p in range(8) for i in range(48))
    yield from (pattern(p, wrong=w) for p in range(8) for w in
                ((8, 24, 40), (0, 1, 16, 32), (0, 1, 2),
                 (0, 1, 16, 17, 32), (0, 1, 16, 17, 32, 33)))
    yield from (pattern(p, 2000, 2000+d) for p in range(8) for d in (0, 1, 4, 8, 9, 10, 16))
    yield from ([1500 if code >> (7-i % 8) & 1 else 500 for i in range(48)] for code in range(256))
    yield from ([level]*48 for level in (0, 1, 1000, 2048, 4095))
    yield [500+i*50 for i in range(48)]
    yield [3000-i*50 for i in range(48)]
    yield from ([1500 if i == spike else 500 for i in range(48)] for spike in range(48))
    yield pattern()[:16]+[500]*32
    yield from ([round(2000+1000*math.sin(2*math.pi*(hz*i*0.005003125+p/16))) for i in range(48)]
                for hz in (10, 25, 50, 60, 100, 200, 825) for p in range(16))
    rng = random.Random(0xB6B6)
    yield from ([rng.randrange(4096) for _ in range(48)] for _ in range(1024))
    yield from ([500+1000*rng.randrange(2) for _ in range(48)] for _ in range(1024))
    yield from (sampled_wave(p/8, ratio, noise, rng)
                for ratio in (0.98, 0.990718, 1, 1.01, 1.02)
                for p in range(64) for noise in (0, 100))


class Precision(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.previous = bytes(test_rx_followup.candidate().data)
        cls.img = candidate()
        cls.data = bytes(cls.img.data)

    cpu = test_rx_followup.Followup.cpu
    execute = test_rx_followup.Followup.execute
    boundary = test_rx_followup.Followup.boundary
    acquire = test_rx_followup.Followup.acquire

    def detect(self, c, samples, recent=None, grade=None):
        c.uc.mem_write(BUFFER, struct.pack('<48H', *samples))
        c.w8(ACTIVE, 0)
        if recent is not None:
            c.w16(RECENT, recent)
        if grade is not None:
            c.w8(GRADE, grade)
        self.execute(c, ANALYZERS[0], budget=12000)
        return c.read(GRADE) > 0

    def tick(self, c):
        c.run()
        self.execute(c, SPEAKER)

    def test_full_phase_error_noise_corpus_preserves_detector_eligibility(self):
        c = self.cpu()
        for number, samples in enumerate(eligibility_cases()):
            c.w8(BEEP, 17)
            c.w8(GAP, 23)
            actual = self.detect(c, samples, recent=321, grade=0)
            self.assertEqual(actual, reference(samples), number)
            self.assertEqual(c.read(GRADE), initial_grade(samples) if actual else 0, number)
            self.assertEqual(c.read(RECENT, 2), 800 if actual else 321, number)
            self.assertEqual((c.read(BEEP), c.read(GAP)), (17, 23), number)
            self.assertEqual(c.read(ACTIVE), 1, number)

    def test_single_high_or_low_outlier_cannot_promote_a_weak_valid_pattern(self):
        c = self.cpu()
        for phase in range(8):
            clean = pattern(phase, low=2000, high=2010)
            self.assertTrue(self.detect(c, clean, recent=0, grade=0))
            expected = initial_grade(clean)
            for index in range(48):
                for spike in (0, 4095):
                    samples = clean[:]
                    samples[index] = spike
                    actual = self.detect(c, samples, recent=0, grade=0)
                    self.assertEqual(actual, reference(samples), (phase, index, spike))
                    self.assertTrue(actual, (phase, index, spike))
                    self.assertEqual(c.read(GRADE), expected, (phase, index, spike, strength(samples)))

    def test_five_widely_spaced_strengths_have_distinct_cadences(self):
        for delta, grade, gap in ((10, 1, 160), (60, 2, 110), (180, 3, 75),
                                  (500, 4, 45), (1000, 5, 20)):
            for baseline in (0, 1000, 2000):
                c = self.cpu()
                # Preserve the original high-sample-sum floor at zero DC.
                sample_delta = 35 if not baseline and delta == 10 else delta
                samples = pattern(low=baseline, high=baseline+sample_delta)
                self.assertEqual(initial_grade(samples), grade)
                self.assertTrue(self.detect(c, samples, recent=0, grade=0))
                self.assertEqual(c.read(GRADE), grade)
                self.execute(c, SPEAKER)
                self.assertEqual((c.read(BEEP), c.read(GAP)), (30, gap))

    def test_nominal_and_hysteresis_boundaries_match_independent_model(self):
        c = self.cpu()
        for boundary in THRESHOLDS:
            for scale in (9, 10, 11):
                for offset in (-1, 0, 1):
                    target = boundary*scale//10+offset
                    samples = samples_at_strength(target)
                    self.assertEqual(strength(samples), target)
                    for previous in range(6):
                        for recent in (0, 500, 501, 800):
                            c.w8(BEEP, 19)
                            c.w8(GAP, 27)
                            self.assertTrue(self.detect(c, samples, recent=recent, grade=previous))
                            self.assertEqual(c.read(GRADE), expected_grade(samples, previous, recent),
                                             (target, previous, recent))
                            self.assertEqual((c.read(BEEP), c.read(GAP), c.read(RECENT, 2)), (19, 27, 800))

    def test_threshold_noise_does_not_toggle_grade_and_large_moves_remain_responsive(self):
        for low_grade, threshold in enumerate(THRESHOLDS, 1):
            for starting_grade in (low_grade, low_grade+1):
                c = self.cpu()
                c.w8(GRADE, starting_grade)
                c.w16(RECENT, 800)
                for target in (threshold-1, threshold+1)*6:
                    self.assertTrue(self.detect(c, samples_at_strength(target)))
                    self.assertEqual(c.read(GRADE), starting_grade)
            c = self.cpu()
            self.assertTrue(self.detect(c, pattern(low=1000, high=1010)))
            self.assertEqual(c.read(GRADE), 1)
            self.assertTrue(self.detect(c, pattern(low=1000, high=2000)))
            self.assertEqual(c.read(GRADE), 5)
            self.assertTrue(self.detect(c, pattern(low=1000, high=1010)))
            self.assertEqual(c.read(GRADE), 1)

    def test_strength_uses_32bit_accumulation_across_full_adc_range(self):
        c = self.cpu()
        for delta in (2900, 3000, 3050, 3100, 3200, 3500, 4095):
            for phase in range(8):
                samples = pattern(phase, low=0, high=delta)
                self.assertTrue(self.detect(c, samples, recent=0, grade=0))
                self.assertEqual(c.read(GRADE), initial_grade(samples), (delta, phase, strength(samples)))
        self.assertGreater(strength(pattern(low=0, high=3100)), 65535)

    def test_sustained_240ms_windows_keep_each_cadence_without_restarting_pulses(self):
        for delta, gap in zip((10, 60, 180, 500, 1000), GAPS):
            for arrival_phase in (0, 1, 119, 239):
                c = self.cpu()
                samples = pattern(low=1000, high=1000+delta)
                self.assertTrue(self.detect(c, samples, recent=0, grade=0))
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

    def test_completed_reject_stops_repeats_without_clearing_activity_hold(self):
        for delta in (10, 60, 180, 500, 1000):
            c = self.cpu()
            self.assertTrue(self.detect(c, pattern(low=1000, high=1000+delta)))
            self.execute(c, SPEAKER)
            for _ in range(239):
                self.tick(c)
            c.run()  # the next complete acquisition arrives at nominal 240 ms
            pair = c.read(BEEP), c.read(GAP)
            self.assertEqual(c.read(RECENT, 2), 560)
            self.assertFalse(self.detect(c, [1000]*48))
            self.assertEqual(c.read(GRADE), 0)
            self.assertEqual(c.read(RECENT, 2), 560)
            self.assertEqual((c.read(BEEP), c.read(GAP)), pair)
            for elapsed in range(1, 101):
                self.tick(c)
                self.assertEqual(c.read(BEEP), max(0, pair[0]-elapsed))
            self.assertEqual(c.read(RECENT, 2), 460)

    def test_missing_windows_have_bounded_audio_expiry_but_retain_power_hold(self):
        for grade, gap in enumerate(GAPS, 1):
            c = self.cpu()
            c.w8(GRADE, grade)
            c.w16(RECENT, 800)
            self.execute(c, SPEAKER)
            starts = [0]
            last_sound = 0
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
            self.assertTrue(all(tick < 300 for tick in starts), starts)
            self.assertLess(last_sound, 330)
            self.assertEqual((c.read(BEEP), c.read(RECENT, 2)), (0, 0))

    def test_key_feedback_survives_accepted_rejected_and_stale_windows(self):
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
        c.w8(GRADE, 5)
        c.w16(RECENT, 500)
        for elapsed in range(1, 74):
            self.tick(c)
            self.assertEqual(c.read(BEEP), 73-elapsed)

    def test_in_progress_or_invalidated_windows_do_not_change_previous_grade(self):
        for active, request, gate_state in ((1, 0, 2), (2, 0, 1), (0, 0, 0),
                                            (0, 0, 1), (0, 1, 2), (0, 2, 2), (0, 3, 2)):
            for samples in (pattern(), [1000]*48):
                c = self.cpu()
                c.uc.mem_write(BUFFER, struct.pack('<48H', *samples))
                c.w8(ACTIVE, active)
                c.w8(REQUEST, request)
                c.w8(GATE_STATE, gate_state)
                c.w8(GRADE, 3)
                c.w16(RECENT, 560)
                c.w8(BEEP, 17)
                c.w8(GAP, 23)
                self.execute(c, ANALYZERS[0])
                self.assertEqual((c.read(ACTIVE), c.read(GRADE), c.read(RECENT, 2),
                                  c.read(BEEP), c.read(GAP)), (active, 3, 560, 17, 23))

    def test_publisher_guards_atomicity_and_mask_restoration_for_accept_and_reject(self):
        from precision_fixes import PUBLISH
        for request, gate_state in ((0, 2), (1, 2), (2, 2), (3, 2), (0, 0), (0, 1)):
            for published_grade in range(6):
                for mask in (0, 1):
                    c = self.cpu()
                    c.w8(REQUEST, request)
                    c.w8(GATE_STATE, gate_state)
                    c.w8(GRADE, 4)
                    c.w16(RECENT, 560)
                    c.w8(BEEP, 73)
                    c.w8(GAP, 45)
                    c.uc.reg_write(UC_ARM_REG_PRIMASK, mask)
                    writes = []
                    def memory(uc, access, addr, size, value, user):
                        writes.append((addr, size))
                        self.assertEqual(uc.reg_read(UC_ARM_REG_PRIMASK), 1)
                    hook = c.uc.hook_add(UC_HOOK_MEM_WRITE, memory)
                    self.execute(c, PUBLISH, 0, published_grade)
                    c.uc.hook_del(hook)
                    allowed = request == 0 and gate_state == 2
                    self.assertEqual(c.read(GRADE), published_grade if allowed else 4)
                    self.assertEqual(c.read(RECENT, 2), 800 if allowed and published_grade else 560)
                    self.assertEqual((c.read(BEEP), c.read(GAP)), (73, 45))
                    self.assertEqual(c.uc.reg_read(UC_ARM_REG_PRIMASK), mask)
                    self.assertTrue(all(item in ((GRADE, 1), (RECENT, 2)) for item in writes), writes)

    def test_scheduler_enforces_freshness_grade_guards_and_countdowns(self):
        # GRADE is owned RAM: publishers and mode/gate resets produce only
        # 0..5. The scheduler relies on that separately tested invariant.
        for grade in range(6):
            for recent in (0, 499, 500, 501, 800):
                for mask in (0, 1):
                    c = self.cpu()
                    c.w8(GRADE, grade)
                    c.w16(RECENT, recent)
                    c.uc.reg_write(UC_ARM_REG_PRIMASK, mask)
                    self.execute(c, SPEAKER)
                    expected = (30, GAPS[grade-1]) if 1 <= grade <= 5 and recent > 500 else (0, 0)
                    self.assertEqual((c.read(BEEP), c.read(GAP)), expected, (grade, recent, mask))
                    self.assertEqual(c.uc.reg_read(UC_ARM_REG_PRIMASK), mask)
        for request, gate_state in ((0, 2), (1, 2), (2, 2), (3, 2), (0, 0), (0, 1)):
            for beep, gap in ((0, 0), (1, 0), (0, 1), (73, 45)):
                c = self.cpu()
                c.w8(REQUEST, request)
                c.w8(GATE_STATE, gate_state)
                c.w8(GRADE, 5)
                c.w16(RECENT, 800)
                c.w8(BEEP, beep)
                c.w8(GAP, gap)
                self.execute(c, SPEAKER)
                expected = (30, 20) if (request, gate_state, beep, gap) == (0, 2, 0, 0) else (beep, gap)
                self.assertEqual((c.read(BEEP), c.read(GAP)), expected)

    def test_snapshot_survives_shared_buffer_overwrite_and_stack_is_bounded(self):
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
        self.assertEqual(c.read(GRADE), initial_grade(samples))
        self.assertEqual((c.read(BEEP), c.read(GAP)), (0, 0))
        allowed = {(ACTIVE, 1), (GRADE, 1), (RECENT, 2)}
        # Detector saves 24 bytes, reserves 104, then calls the 24-byte
        # trimmed_mean frame: the expanded metric costs eight extra bytes.
        outside = [(hex(addr), size) for addr, size in writes
                   if not (SP-152 <= addr and addr+size <= SP or (addr, size) in allowed)]
        self.assertEqual(outside, [])

    def test_key_request_at_every_publication_instruction_boundary_is_safe(self):
        from precision_fixes import PUBLISH, GRADE_HELPER
        tracked = {GRADE, RECENT, BEEP, GAP}
        for entry, args in ((SPEAKER, ()), (PUBLISH, (0, 0)),
                            (PUBLISH, (0, 5)), (GRADE_HELPER, (90000,))):
            def fresh():
                c = self.cpu()
                c.w8(GRADE, 5)
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
                    # A pending TIM1 key interrupt waits until PRIMASK clears.
                    if state['step'] >= target and not state['injected'] and not uc.reg_read(UC_ARM_REG_PRIMASK):
                        state['injected'] = True
                        state['published_before'] = bool(writes)
                        c.w8(REQUEST, 2)
                        c.w8(BEEP, 100)
                def memory(uc, access, addr, size, value, user):
                    if addr in tracked:
                        self.assertEqual(uc.reg_read(UC_ARM_REG_PRIMASK), 1, (hex(entry), target, hex(addr)))
                        self.assertFalse(state['injected'] and not state['published_before'],
                                         ('publication after earlier mode request', hex(entry), target))
                        writes.append((addr, size, value))
                code_hook = c.uc.hook_add(UC_HOOK_CODE, step)
                write_hook = c.uc.hook_add(UC_HOOK_MEM_WRITE, memory)
                self.execute(c, entry, *args)
                c.uc.hook_del(code_hook)
                c.uc.hook_del(write_hook)
                self.assertTrue(state['injected'], (hex(entry), target))
                self.assertEqual(c.read(BEEP), 100, (hex(entry), target))
                self.assertEqual(c.uc.reg_read(UC_ARM_REG_PRIMASK), 0)

    # Reuse only unchanged behavioral contracts, never PN 1.6 grade/hold rules.
    test_all_directed_mode_changes_discard_partial_and_completed_windows = test_rx_followup.Followup.test_all_directed_mode_changes_discard_partial_and_completed_windows
    test_key_request_during_analysis_rejects_old_result_and_keeps_confirmation = test_rx_followup.Followup.test_key_request_during_analysis_rejects_old_result_and_keeps_confirmation
    test_digital_and_analog_gate_reopening_requires_complete_fresh_window = test_rx_followup.Followup.test_digital_and_analog_gate_reopening_requires_complete_fresh_window
    test_mains_publishes_rearm_after_clear_and_first_tim5_sample_survives = test_rx_followup.Followup.test_mains_publishes_rearm_after_clear_and_first_tim5_sample_survives
    test_prior_battery_adc_dft_and_timer_fixes_are_byte_exact = test_rx_followup.Followup.test_prior_battery_adc_dft_and_timer_fixes_are_byte_exact

    def test_image_rebuild_and_profiles_are_preserved(self):
        import precision_fixes
        fw = Path(__file__).resolve().parent.parent
        self.assertEqual((fw / precision_fixes.OUTPUT).read_bytes(), self.data)
        self.assertEqual((fw / 'experimental/APP_LPM-10RX_PN1.6-followup.bin').read_bytes(), self.previous)
        self.assertEqual(len(self.data), len(self.previous))
        rebuilt = bytearray(self.img.original)
        for addr, old, new, why, kind in self.img.log:
            offset = addr-0x08006800
            self.assertEqual(bytes(rebuilt[offset:offset+len(old)]), old, why)
            rebuilt[offset:offset+len(new)] = new
        self.assertEqual(bytes(rebuilt), self.data)
        for start, end in ((0x08006800, 0x08006948), (0x0800B388, 0x0800B484),
                           (0x0800BAE8, 0x0800BBB0)):
            self.assertEqual(self.data[start-0x08006800:end-0x08006800],
                             self.previous[start-0x08006800:end-0x08006800])

    def test_profile_rejects_wrong_parent_tampering_and_double_application(self):
        import precision_fixes
        import test_roadmap
        for img in (test_roadmap.candidate(), candidate()):
            before = bytes(img.data)
            with self.assertRaises(PatchError):
                precision_fixes.apply(img)
            self.assertEqual(bytes(img.data), before)
        img = test_rx_followup.candidate()
        img.data[0x100] ^= 1
        before = bytes(img.data)
        with self.assertRaises(PatchError):
            precision_fixes.apply(img)
        self.assertEqual(bytes(img.data), before)


if __name__ == '__main__':
    unittest.main()
