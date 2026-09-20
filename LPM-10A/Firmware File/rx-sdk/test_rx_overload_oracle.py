"""Independent PN 1.12 ARM comparisons against the upper-only model oracle.

The delivered artifact is pinned and compared byte-for-byte with a complete
source rebuild. Inputs model ADC observations; none of these counts establish
physical cable selectivity, clipping voltages or a field success rate.
"""
from collections import Counter
import hashlib
from pathlib import Path
import random
import struct
import sys
import unittest

from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_PRIMASK, UC_ARM_REG_R0

import robust_fixes
import test_overload_integration
import test_rx_robust
from test_rx_followup import GRADE, INDICES
from verify_digital import ACTIVE, BUFFER, RECENT

sys.path.insert(0, str(Path(__file__).resolve().parents[3]/'docs/experiments'))
import digital_flat_tail_challenge as oracle
from scan_sync_model import sampled_window

ARTIFACT = Path(__file__).resolve().parent.parent/'experimental/APP_LPM-10RX_PN1.12-overload.bin'
SHA256 = '4ea18c52bde25353a9a38dbf46775425860f7859bc2c10e3c908a7bff4044403'


class OverloadOracle(unittest.TestCase):
    cpu = test_rx_robust.Robust.cpu
    detect = test_rx_robust.Robust.detect
    execute = test_rx_robust.Robust.execute
    results = {}

    @classmethod
    def setUpClass(cls):
        cls.data = ARTIFACT.read_bytes()
        assert hashlib.sha256(cls.data).hexdigest() == SHA256
        rebuilt = test_overload_integration.candidate()
        assert bytes(rebuilt.data) == cls.data, 'Artifact differs from complete source rebuild'
        cls.results = {}

    def verify_rows(self, category, rows):
        c = self.cpu()
        scores = []
        counts = Counter()
        def capture(uc, address, size, userdata):
            scores.append(uc.reg_read(UC_ARM_REG_R0))
        hook = c.uc.hook_add(UC_HOOK_CODE, capture,
            begin=robust_fixes.GAP_HELPER, end=robust_fixes.GAP_HELPER)
        try:
            for index, (name, samples) in enumerate(rows):
                baseline = oracle.current.measure(samples)
                expected = oracle.upper_flat_measure(samples)
                scores.clear()
                mask = index % 2
                c.uc.reg_write(UC_ARM_REG_PRIMASK, mask)
                self.detect(c, samples, recent=560, grade=0)
                amplitude = expected['amplitude']
                score = (29*amplitude-12*(29*amplitude//46)) if amplitude is not None else None
                self.assertEqual(c.read(GRADE), expected['gap'], (name, expected))
                self.assertEqual(scores, [] if score is None else [score], (name, expected))
                self.assertEqual(c.read(RECENT, 2), 800 if expected['gap'] else 560, name)
                self.assertEqual(c.uc.reg_read(UC_ARM_REG_PRIMASK), mask, name)
                self.assertEqual(c.read(ACTIVE), 1, name)
                self.assertEqual(c.read(INDICES[0]), 32, name)
                self.assertEqual(struct.unpack('<32H', c.uc.mem_read(BUFFER, 64)),
                                 tuple(samples[16:48]), name)
                counts['arm_windows'] += 1
                counts['accepted'] += bool(expected['gap'])
                counts['normal_to_uncertain'] += expected['gap'] != baseline['gap']
                counts['prior_uncertainty_preserved'] += baseline['gap'] == expected['gap'] == 1
                self.assertEqual(bool(expected['gap']), bool(baseline['gap']), name)
                if expected['gap'] != baseline['gap']:
                    self.assertEqual(expected['gap'], 1, name)
                    self.assertIsNone(baseline.get('phase'), name)
                    self.assertEqual(samples[32:48], [4095]*16, name)
        finally:
            c.uc.hook_del(hook)
        self.__class__.results[category] = dict(counts)
        return counts

    def test_structured_random_prefix_and_rail_edge_cases(self):
        result = self.verify_rows('structured_random', oracle.structured_random_rows(5000))
        self.assertEqual(result['arm_windows'], 5000)
        self.assertGreater(result['normal_to_uncertain'], 100)

    def test_old_uncertainty_lower_zero_interior_and_upper_tail_matrix(self):
        result = self.verify_rows('tail_matrix', oracle.fixture_rows())
        self.assertEqual(result['arm_windows'], 672)
        self.assertEqual(result['normal_to_uncertain'], 27)
        self.assertEqual(result['prior_uncertainty_preserved'], 116)

    def test_real_five_read_brief_bursts_preserve_all_publications(self):
        def rows():
            for start in (0, 4, 8):
                for duration in (16, 20, 23, 24, 25, 31, 32):
                    for ratio in (.98, 1, 1.02):
                        for phase in range(32):
                            stream = oracle.burst_stream(start, duration, phase/4, ratio)
                            for end in (48, 64, 80, 96):
                                name = f'start{start}/duration{duration}/ratio{ratio}/phase{phase}/end{end}'
                                yield name, stream[end-48:end]
        result = self.verify_rows('brief_contact_publications', rows())
        self.assertEqual(result['arm_windows'], 8064)
        self.assertEqual(result['normal_to_uncertain'], 0)

    def test_existing_audit_movement_and_strength_counterexamples(self):
        rows = ((r['name'], r['samples']) for r in oracle.previous.original.cases())
        result = self.verify_rows('previous_audit', rows)
        self.assertEqual(result['arm_windows'], 2490)
        self.assertEqual(result['normal_to_uncertain'], 0)

    def test_clean_noisy_weak_sampler_and_known_retained_limits(self):
        def rows():
            for amplitude in (9, 13, 300):
                for fresh in (False, True):
                    for ratio in (.98, .997, 1, 1.003, 1.02):
                        for noise in (0, amplitude//2):
                            for phase in range(32):
                                name = f'a{amplitude}/fresh{fresh}/ratio{ratio}/noise{noise}/phase{phase}'
                                yield name, sampled_window('legacy', phase/4, ratio, noise,
                                    random.Random(20260920+phase), amplitude=amplitude,
                                    fresh_start=fresh)
            # Retain the two weak-clean boundary misses explicitly; do not
            # turn inherited limitations into silent disappearances in a grid.
            for name, samples in oracle.previous.heldout_rows():
                if name.startswith(('heldout404/', 'heldout1149/')):
                    self.assertEqual(oracle.current.measure(samples)['gap'], 0)
                    yield name, samples
            rng = random.Random(oracle.current.SEED+100000+13398)
            samples = [rng.randrange(4096) for _ in range(48)]
            self.assertEqual(oracle.current.measure(samples)['gap'], 35)
            yield 'inherited_noise_uniform_13398_not_fixed', samples
        result = self.verify_rows('sampler_and_known_limits', rows())
        self.assertEqual(result['arm_windows'], 1923)
        self.assertEqual(result['normal_to_uncertain'], 0)


if __name__ == '__main__':
    unittest.main()
