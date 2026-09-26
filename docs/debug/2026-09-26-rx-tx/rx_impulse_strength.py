"""Diagnostic: current RX must not rank an impulsive weak tone above a clean stronger tone.

Run from the repository root. Executes the released PN1.30 analyzer in Unicorn;
the vectors are completed ADC windows, not measurements of the analog front end.
"""
from pathlib import Path
import hashlib
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'LPM-10A' / 'Firmware File' / 'rx-sdk'))

import test_rx_clean_strength as current
from verify_digital import pattern
from lpm10a.thumb import assemble


class ImpulseStrength(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        current.setUpModule()
        assert hashlib.sha256(current.CANDIDATE).hexdigest() == '407b0ba3b80883e4f640ef7e2040a56004ca780a5bd8b81cf3a371ca04a67135'

    @staticmethod
    def vector(indices):
        samples = pattern(2, 1000, 1100)
        for index in indices:
            samples[index] = 0
        return samples

    def test_removing_either_dip_restores_correct_order(self):
        runner = current.Estimator()
        strong = runner.scored(current.CANDIDATE, pattern(2, 1000, 1150))[1][0]
        for indices in ((), (34,), (37,)):
            result = runner.scored(current.CANDIDATE, self.vector(indices))
            self.assertEqual(result[1], (2144,))
            self.assertLess(result[1][0], strong)

    def test_unchanged_alignment_and_estimator_only_intervention_isolates_cause(self):
        runner = current.Estimator()
        clean = runner.scored(current.CANDIDATE, self.vector(()))
        noisy = runner.scored(current.CANDIDATE, self.vector((34, 37)))
        self.assertEqual(clean[0]['pattern'], noisy[0]['pattern'])
        # Change only the estimator branch in emulator memory, never a firmware file.
        data = bytearray(current.CANDIDATE)
        at = current.cs.ESTIMATE_CALL - 0x08006800
        data[at:at + 4] = assemble(current.cs.ESTIMATE_CALL, f'bl {current.cs.OLD_ESTIMATOR}')
        runner.curve_entry = lambda data: current.IMG.clean_strength['curve']
        control = runner.scored(bytes(data), self.vector((34, 37)))
        self.assertEqual(control[1], (2144,))
        for gain in (0, 2, 7):
            self.assertEqual(runner.scored(current.CANDIDATE, self.vector((34, 37)), level=gain)[1], (12864,))

    def test_two_dips_must_not_make_weak_tone_outrank_stronger_tone(self):
        runner = current.Estimator()
        weak = runner.scored(current.CANDIDATE, self.vector((34, 37)))
        strong = runner.scored(current.CANDIDATE, pattern(2, 1000, 1150))
        print('PN1.30 two dips at samples 34/37: weak score/gap/level =',
              (weak[1][0], weak[2][0], weak[2][3]),
              '; clean stronger score/gap/level =', (strong[1][0], strong[2][0], strong[2][3]))
        self.assertLess(weak[1][0], strong[1][0], 'two low spikes reverse cable strength ordering')

    def test_impulsive_weak_signal_does_not_outrank_clean_stronger_signal(self):
        runner = current.Estimator()
        failures = []
        tested = 0
        for phase in range(8):
            clean = pattern(phase, 1000, 1100)
            stronger = pattern(phase, 1000, 1150)
            strong = runner.scored(current.CANDIDATE, stronger)[1][0]
            for start in (0, 16, 32):
                polluted = clean[:]
                highs = [i for i in range(start, start + 16) if clean[i] == 1100]
                lows = [i for i in range(start, start + 16) if clean[i] == 1000]
                for index in highs[:2]:
                    polluted[index] += 1000
                for index in lows[:2]:
                    polluted[index] -= 1000
                captured, scores, state = runner.scored(current.CANDIDATE, polluted)
                tested += 1
                if scores and scores[0] > strong:
                    old = runner.scored(current.PARENT, polluted)[1]
                    failures.append((phase, start, scores[0], strong, old, state))
        print(f'PN1.30 impulsive weak/strong comparisons: {tested}; misranked: {len(failures)}')
        print('First misranked cases (phase, start, weak score, strong score, PN1.29 score, state):', failures[:4])
        self.assertEqual(failures, [], 'impulses reverse the strength ordering')


if __name__ == '__main__':
    unittest.main()
