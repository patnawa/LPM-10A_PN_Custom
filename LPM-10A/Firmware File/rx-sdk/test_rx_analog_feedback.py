"""Actual-ARM Analog feedback regressions with modeled ADC/interrupt arrivals."""
import hashlib
import math
from pathlib import Path
import random
import struct
import unittest

from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_PRIMASK, UC_ARM_REG_SP

import analog_feedback
from lpm10rx.image import PatchError
import test_rx_robust
from test_rx_followup import ANALYZERS, GATE_STATE, GRADE, REQUEST, TIM5
from test_rx_pinpoint import raw_gap
from verify_control import BEEP, MODE
from verify_digital import ACTIVE, BUFFER, GAP, GATE, RECENT, pattern

FS = 64_000_000 / 1601 / 13
TX_HZ = 1_000_000 / 101 / 12


def sine(amplitude=300, frequency=TX_HZ, phase=0, dc=2048):
    return [max(0, min(4095, round(dc+amplitude*math.cos(2*math.pi*frequency*i/FS+phase))))
            for i in range(64)]


def square(step=300, phase=0):
    return [1000+step*int((i*TX_HZ/FS+phase) % 1 >= .5) for i in range(64)]


def candidate():
    img = test_rx_robust.candidate()
    analog_feedback.apply(img)
    return img


class AnalogFeedback(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.previous = bytes(test_rx_robust.candidate().data)
        cls.img = candidate()
        cls.data = bytes(cls.img.data)

    cpu = test_rx_robust.Robust.cpu
    execute = test_rx_robust.Robust.execute
    boundary = test_rx_robust.Robust.boundary

    def analog_cpu(self, previous=False):
        c = self.cpu(self.previous if previous else self.data)
        c.w8(MODE, 1)
        c.w16(GATE, 580)
        c.w16(GATE+2, 1)
        return c

    def analyze(self, c, samples):
        c.w8(ACTIVE, 0)
        c.uc.mem_write(BUFFER, struct.pack('<64H', *samples))
        self.execute(c, ANALYZERS[1])
        return c.read(GRADE)

    def previous_result(self, samples):
        c = self.analog_cpu(previous=True)
        result = {}
        def capture(uc, address, size, user):
            sp = uc.reg_read(UC_ARM_REG_SP)
            result['margin'] = c.read(sp+8, 2)-c.read(sp+4, 2)
        hook = c.uc.hook_add(UC_HOOK_CODE, capture, begin=0x08009FFE, end=0x08009FFE)
        try:
            self.analyze(c, samples)
        finally:
            c.uc.hook_del(hook)
        result['accepted'] = c.read(BEEP) > 0
        return result

    def speaker(self, c):
        # Executes the real IRQ dispatch at a speaker-due, non-sample-due tick.
        c.w32(0x20000100, 7)
        self.execute(c, TIM5)

    def test_scope_and_parent_guards(self):
        allowed = ((analog_feedback.ANALYZER, analog_feedback.ANALYZER_END),
                   (analog_feedback.SPEAKER_DISPATCH, analog_feedback.SPEAKER_END))
        changed = [0x08006800+i for i,(a,b) in enumerate(zip(self.previous,self.data)) if a != b]
        self.assertTrue(changed)
        self.assertEqual(len(self.previous), len(self.data))
        self.assertTrue(all(any(lo <= p < hi for lo,hi in allowed) for p in changed))
        self.assertLessEqual(self.img.analog_feedback['analyzer_bytes'], 240)
        with self.assertRaises(PatchError):
            analog_feedback.apply(self.img)
        img = test_rx_robust.candidate()
        img.data[analog_feedback.ANALYZER-0x08006800] ^= 1
        with self.assertRaises(PatchError):
            analog_feedback.apply(img)

    def test_actual_dft_eligibility_preserved_and_margin_maps_to_finer_feedback(self):
        rng = random.Random(0x20260921)
        cases = [[dc]*64 for dc in (0, 10, 2048, 4095)]
        cases += [sine(a, f, phase=p) for a in (12, 25, 100, 300, 1800)
                  for f in (50, 60, TX_HZ, FS-TX_HZ, 1000) for p in (0, 1.1)]
        cases += [square(a, p) for a in (20, 25, 50, 100, 300, 1000, 3000)
                  for p in (0, .25)]
        cases += [sine(a) for a in (2500, 4000, 8000)]
        cases += [[rng.randrange(4096) for _ in range(64)] for _ in range(16)]
        for number, samples in enumerate(cases):
            with self.subTest(number=number):
                old = self.previous_result(samples)
                c = self.analog_cpu()
                grade = self.analyze(c, samples)
                self.assertEqual(grade > 0, old['accepted'])
                expected = 0 if not old['accepted'] else (
                    1 if samples.count(4095) >= 8 else raw_gap((old['margin']-10)*40))
                self.assertEqual(grade, expected)
                self.assertEqual(c.read(ACTIVE), 1)
                self.assertEqual(c.read(RECENT, 2), 600 if grade else 0)
                self.assertEqual(c.read(BEEP), 0, 'analysis never takes ownership of a live beep')
                self.speaker(c)
                self.assertEqual(c.read(BEEP), (100 if grade == 1 else 30) if grade else 0)

    def test_small_square_steps_have_more_than_three_monotonic_levels(self):
        gaps = [self.analyze(self.analog_cpu(), square(step)) for step in range(25, 301, 25)]
        self.assertTrue(all(g > 1 for g in gaps))
        self.assertEqual(gaps, sorted(gaps, reverse=True))
        self.assertGreaterEqual(len(set(gaps)), 10)

    def test_upper_rail_uncertainty_is_distinct_and_does_not_mean_silence(self):
        for amplitude in (2500, 4000, 8000):
            c = self.analog_cpu()
            samples = sine(amplitude)
            self.assertGreaterEqual(samples.count(4095), 8)
            self.assertEqual(self.analyze(c, samples), 1)
            self.speaker(c)
            self.assertEqual((c.read(BEEP), c.read(GAP)), (100, 160))
        # An ordinary OOK low level of zero alone is not an overload verdict.
        c = self.analog_cpu()
        self.assertGreater(self.analyze(c, [v-1000 for v in square(1000)]), 1)

    def test_stronger_update_shortens_pending_gap_and_preserves_current_pulse(self):
        c = self.analog_cpu()
        weak = sine(25)
        strong = sine(1800)
        weak_gap = self.analyze(c, weak)
        self.speaker(c)
        starts = [(0, weak_gap)]
        strong_gap = None
        for tick in range(1, 241):
            before = c.read(BEEP)
            c.run()
            if tick % 21 == 0:
                remaining = c.read(BEEP)
                strong_gap = self.analyze(c, strong)
                self.assertEqual(c.read(BEEP), remaining)
            self.speaker(c)
            if c.read(BEEP) == 30 and before <= 1:
                starts.append((tick, c.read(GAP)))
        self.assertLess(strong_gap, weak_gap)
        self.assertGreaterEqual(len(starts), 3)
        self.assertEqual(starts[1][1], strong_gap)
        self.assertLessEqual(starts[1][0]-21, 30+strong_gap)

    def test_signal_loss_and_stalled_analysis_stop_repeats(self):
        for rejected_window in (False, True):
            c = self.analog_cpu()
            self.analyze(c, sine(300))
            self.speaker(c)
            if rejected_window:
                self.analyze(c, [2048]*64)
                self.assertEqual(c.read(GRADE), 0)
            for tick in range(1, 401):
                c.run()
                self.speaker(c)
                if tick >= (30 if rejected_window else 130):
                    self.assertEqual(c.read(BEEP), 0)

    def test_pending_changes_and_active_key_beeps_preserve_ownership_and_mask(self):
        for mask in (0, 1):
            for request, gate in ((0, 2), (1, 2), (2, 2), (3, 2), (0, 0), (0, 1)):
                c = self.analog_cpu()
                c.w8(BEEP, 100)
                c.w8(GAP, 160)
                c.w8(REQUEST, request)
                c.w8(GATE_STATE, gate)
                c.uc.reg_write(UC_ARM_REG_PRIMASK, mask)
                self.analyze(c, sine(1800))
                self.speaker(c)
                self.assertEqual(c.read(BEEP), 100)
                self.assertEqual(c.uc.reg_read(UC_ARM_REG_PRIMASK), mask)
                if request or gate != 2:
                    self.assertEqual((c.read(GRADE), c.read(GAP), c.read(RECENT, 2)), (0, 160, 0))

    def test_mains_feedback_and_digital_detection_unchanged(self):
        for data in (self.previous, self.data):
            c = self.cpu(data)
            c.w8(MODE, 2)
            c.w8(BEEP, 100)
            c.w8(GAP, 200)
            c.w8(GRADE, 20)
            c.w16(RECENT, 800)
            self.speaker(c)
            self.assertEqual((c.read(BEEP), c.read(GAP)), (100, 200))
        for mode in (0, 2):
            for amplitude in (0, 10, 100, 1000, 2000):
                samples = (pattern(low=1000, high=1000+amplitude) if mode == 0
                           else [round(2048+amplitude*math.cos(2*math.pi*5*i/64)) for i in range(64)])
                results = []
                for data in (self.previous, self.data):
                    c = self.cpu(data)
                    c.w8(MODE, mode)
                    c.w8(ACTIVE, 0)
                    c.uc.mem_write(BUFFER, struct.pack('<'+'H'*len(samples), *samples))
                    self.execute(c, ANALYZERS[mode])
                    self.speaker(c)
                    results.append(tuple(c.read(a, s) for a,s in ((GRADE,1),(RECENT,2),(BEEP,1),(GAP,1))))
                self.assertEqual(*results)


if __name__ == '__main__':
    unittest.main()
