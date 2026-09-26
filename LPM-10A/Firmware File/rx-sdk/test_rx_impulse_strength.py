"""Actual analyzer: preserve edge compensation and reject impulse-driven misranking."""
import contextlib
import io
import random
import struct
import unittest

from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0

import clean_strength as cs
import impulse_strength
import rx_resilient
import steady_probe
import test_rx_clean_strength as old
import test_rx_isolate as base
import test_rx_tracking_streams as streams
from test_rx_followup import ANALYZERS, GRADE
from verify_digital import BUFFER, RECENT, pattern


class ImpulseStrength(base.Analysers, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with contextlib.redirect_stdout(io.StringIO()):
            cls.img = cs.build_candidate()
        cls.parent = bytes(cls.img.data)
        rx_resilient.apply(cls.img)
        cls.data = bytes(cls.img.data)

    def scored(self, samples, *, parent=False, level=7):
        c = streams.StreamCPU(self.parent if parent else self.data)
        self.fresh(c, mode=0, knob=4095, level=level, grade=0, recent=0)
        c.uc.mem_write(BUFFER, struct.pack('<48H', *samples))
        scores = []
        entry = self.img.clean_strength['curve']
        hook = c.uc.hook_add(UC_HOOK_CODE,
            lambda uc, a, s, u: scores.append(uc.reg_read(UC_ARM_REG_R0)), begin=entry, end=entry)
        try:
            self.execute(c, ANALYZERS[0], budget=150000)
        finally:
            c.uc.hook_del(hook)
        return tuple(scores), c.read(GRADE), c.read(RECENT, 2)

    def test_two_low_impulses_do_not_reverse_strength_ranking(self):
        weak = pattern(2, 1000, 1100)
        weak[34] = weak[37] = 0
        strong = pattern(2, 1000, 1150)
        self.assertEqual(self.scored(weak, parent=True)[0], (12864,))
        self.assertEqual(self.scored(strong, parent=True)[0], (3222,))
        for gain in (0, 2, 7):
            actual = self.scored(weak, level=gain)
            self.assertEqual(actual[0], (2144,))
            self.assertLess(actual[0][0], self.scored(strong, level=gain)[0][0])

    def test_single_spike_every_position_and_seeded_two_to_four_spikes(self):
        rng = random.Random(0x131)
        accepted = 0
        for phase in range(8):
            clean = pattern(phase, 1000, 1100)
            cases = [(i,) for i in range(48)]
            cases += [tuple(rng.sample(range(48), n)) for n in (2, 3, 4) for _ in range(24)]
            for indices in cases:
                samples = clean[:]
                for i in indices:
                    samples[i] = 0 if clean[i] == 1000 else 4095
                score = self.scored(samples)[0]
                if score:
                    accepted += 1
                    self.assertEqual(score, (2144,), (phase, indices, score))
        self.assertGreater(accepted, 500)
        print('Accepted impulse vectors with correct strength:', accepted)

    def test_clean_and_mixed_edges_preserve_true_strength_all_phases(self):
        for phase in range(8):
            for contrast in (12, 60, 300, 1200, 2400):
                truth = cs.contrast_score(contrast)
                self.assertEqual(self.scored(pattern(phase, 800, 800 + contrast))[0], (truth,))
                for fraction in (1 / 3, 2 / 3):
                    for alignment in ('start', 'end'):
                        values = old.mixed_pattern(phase, contrast, fraction, alignment)
                        result = self.scored(values)[0]
                        if result:
                            self.assertAlmostEqual(result[0] / truth, 1, delta=.03,
                                                   msg=(phase, contrast, fraction, alignment, result))


class Tracking(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with contextlib.redirect_stdout(io.StringIO()):
            cls.img = cs.build_candidate()
        cls.parent = bytes(cls.img.data)
        rx_resilient.apply(cls.img)
        cls.data = bytes(cls.img.data)

    def probe(self, data, amplitude, *, knob=4095, end=4000):
        return steady_probe._Runner().probe(data, self.img.clean_strength['curve'],
            mode=0, knob=knob, amplitude=amplitude, end_ms=end)

    def test_steady_drifting_edges_still_hold_one_level(self):
        for amplitude in (720, 1000):
            rows, _ = self.probe(self.data, lambda ms: amplitude, end=6000)
            settled = [r for r in rows if r[0] >= 1000 and r[1] is not None]
            levels = {r[3] for r in settled}
            scores = sorted(r[1] for r in settled)
            self.assertEqual(len(levels), 1, (amplitude, levels))
            self.assertGreaterEqual(scores[0] / scores[len(scores) // 2], .8)
            print('Robust steady signal:', amplitude, 'level', levels,
                  'min/median', scores[0] / scores[len(scores) // 2])

    def test_real_drop_keeps_sub_700ms_response_and_fast_gain_settle(self):
        amplitude = lambda ms: 30000 if ms < 2000 else 15000
        rows, gains = self.probe(self.data, amplitude, knob=768)
        shown = [(ms, level) for ms, score, gain, level, grade in rows if score is not None]
        self.assertLessEqual(gains[-1][0] - gains[0][0], 800)
        self.assertEqual({level for ms, level in shown if 1500 < ms < 2000}, {8})
        delay = next(ms - 2000 for ms, level in shown if ms > 2000 and level == 6)
        self.assertLess(delay, 700)
        print('Robust strength 6 dB drop response:', delay, 'ms; gain steps', gains)


if __name__ == '__main__':
    unittest.main()
