"""Owner report 2026-09-23 on RX PN1.27: "พอเร่งสุดเหมือนหาสายไม่แม่น ดังทั่วไปหมด ไม่แม่นยำในการ identify สาย".

Knob turned up, probe touching the pairs of a bundle. The toned pair was touched first, so
it is the strongest signal heard (the probe's peak); its neighbours carry a coupled tone
3 to 14 dB weaker. On the top of the knob each neighbour must play a clearly slower
rhythm than the toned pair (or none); at every knob position no neighbour may play faster
than the toned pair, nor a weaker neighbour faster than a stronger one. Executes the real
analyser, curve, peak and publisher on one fresh window per case; ADC values and the
coupling are modeled.
"""
import contextlib
import io
import unittest

import knob_reference as pn127
import pair_rank as pn128
import test_rx_relative_isolate as harness
from verify_digital import pattern

KNOBS = (1024, 2048, 3072, 4095)                    # 25, 50, 75, 100 % of travel
TOP = (3072, 4095)
# Touching the toned pair: B6 amplitude 2270 at driven gain level 2 (the automatic gain has
# stepped down), about +10 dB over the full gain's saturation (normalised 40 000).
TARGET, LEVEL = 2270, 2
NEIGHBOURS_DB = (-3, -6, -10, -14)
SETTLE = 20_000                                     # TIM5 ticks (0.5 s) from the toned pair to the neighbour
# +10 ms on the 20 ms fastest interval lengthens the 50 ms pulse period by 20 %, above the
# 5-10 % at which a change of tempo is heard side by side.
SLOWER_MS = 10
CANDIDATES = {}


def setUpModule():
    CANDIDATES['PN1.27'] = bytes(pn127.build_candidate().data)
    with contextlib.redirect_stdout(io.StringIO()):
        CANDIDATES['PN1.28'] = bytes(pn128.build_candidate().data)


class PairIdentify(harness.Analysers, unittest.TestCase):
    def entry(self, data):
        return 0x0800A048                               # every image's Digital curve entry

    def interval(self, data, amplitude, knob, peak, elapsed):
        state, scores, (new_peak, _) = self.analyse(
            data, pattern(0, 800, 800 + amplitude), knob=knob, level=LEVEL,
            grade=0, recent=0, peak=peak, elapsed=elapsed)
        self.assertTrue(scores, (amplitude, knob))
        return (state[0] if state[1] == 800 else None), new_peak

    def table(self, data):
        """{knob: (toned pair interval, [neighbour interval or None (muted) per NEIGHBOURS_DB])}."""
        rows = {}
        for knob in KNOBS:
            target, peak = self.interval(data, TARGET, knob, 0, 0)
            neighbours = [self.interval(data, round(TARGET * 10 ** (db / 20)), knob, peak, SETTLE)[0]
                          for db in NEIGHBOURS_DB]
            rows[knob] = (target, neighbours)
        return rows

    def report(self, label):
        rows = self.table(CANDIDATES[label])
        print(label, 'quiet interval ms: toned pair | neighbours', NEIGHBOURS_DB, 'dB (None = muted)')
        for knob, (target, neighbours) in rows.items():
            print(f'   knob {100 * knob / 4095:3.0f}%  {target:3} | {neighbours}')
        return rows

    @staticmethod
    def top_problems(rows):
        return [f'knob {knob}: neighbour {db} dB plays {heard} ms, toned pair {target} ms'
                for knob in TOP for target, neighbours in [rows[knob]]
                for db, heard in zip(NEIGHBOURS_DB, neighbours)
                if target is None or (heard is not None and heard < target + SLOWER_MS)]

    def test_pn127_reproduces_the_owner_report(self):
        problems = self.top_problems(self.report('PN1.27'))
        print('PN1.27 problems:', problems)
        self.assertIn('knob 4095: neighbour -6 dB plays 20 ms, toned pair 20 ms', problems)

    def test_top_of_knob_ranks_the_toned_pair_first(self):
        label = next(reversed(CANDIDATES))
        self.assertEqual(self.top_problems(self.report(label)), [], label)

    def test_no_neighbour_outranks_the_toned_pair(self):
        label = next(reversed(CANDIDATES))
        slowest = 1000                                  # a muted neighbour ranks below every rhythm
        for knob, (target, neighbours) in self.table(CANDIDATES[label]).items():
            heard = [slowest if n is None else n for n in neighbours]
            self.assertIsNotNone(target, knob)
            self.assertLessEqual(target, min(heard), knob)
            self.assertEqual(heard, sorted(heard), (knob, 'a weaker neighbour never plays faster'))


if __name__ == '__main__':
    unittest.main()
