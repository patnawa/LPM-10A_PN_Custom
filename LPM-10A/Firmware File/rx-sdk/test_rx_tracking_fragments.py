"""Independent fragmented-code edge checks against the complete PN 1.11 build.

Runs 6,768 reduced-ADC vectors across every feasible placement of six code-span
lengths, eight phases, three DC levels and three contrasts. The ADC input is
synthetic; the integrated ARM detector, fallback, median and mapper all run.
"""
import statistics
import struct
import unittest

from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1

import digital_tracking
import test_rx_digital_tracking as digital_tests
import test_rx_robust
import test_tracking_integration
from test_rx_followup import GRADE
from verify_control import SP
from verify_digital import ACTIVE, BUFFER


def fragment_vectors():
    """Construct the stimulus independently of the candidate slicing logic."""
    code = (1, 0, 1, 1, 0, 1, 1, 0)
    for span in (24, 25, 31, 32, 40, 48):
        for start in range(49-span):
            for phase in range(8):
                for dc in (0, 1000, 3000):
                    for contrast in (9, 35, 100):
                        samples = [dc]*48
                        for i in range(start, start+span):
                            samples[i] += contrast*code[(i+phase) % 8]
                        yield (span, start, phase, dc, contrast), samples


class TrackingFragments(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.img = test_tracking_integration.candidate()
        cls.data = bytes(cls.img.data)

    cpu = test_rx_robust.Robust.cpu
    detect = test_rx_robust.Robust.detect
    execute = test_rx_robust.Robust.execute

    def test_fragment_matrix_phase_fallback_bounds_and_estimator_arithmetic(self):
        c = self.cpu()
        observed_offsets = set()
        estimate = {}
        mapped_scores = []
        snapshot = SP-128  # 24 saved-register bytes + 104 detector local bytes.

        def at_estimator(uc, address, size, user):
            pointer = uc.reg_read(UC_ARM_REG_R0)
            self.assertGreaterEqual(pointer, snapshot)
            self.assertLessEqual(pointer+32, snapshot+96)
            self.assertEqual(pointer % 2, 0)
            observed_offsets.add(pointer-snapshot)
            # Independently calculate medians from the raw values and the
            # actual phase supplied at the assembly helper boundary.
            raw = [value & 4095 for value in struct.unpack(
                '<16H', bytes(uc.mem_read(pointer, 32)))]
            phase_word = uc.reg_read(UC_ARM_REG_R1)
            wanted = [(phase_word >> (31-i)) & 1 for i in range(16)]
            self.assertEqual(sum(wanted), 10)
            low = int(statistics.median(v for v, bit in zip(raw, wanted) if not bit))
            high = int(statistics.median(v for v, bit in zip(raw, wanted) if bit))
            amplitude = high-low
            estimate['score'] = (29*amplitude-12*(29*amplitude//46)
                                 if high < 4095 and amplitude > 0 else None)

        def at_mapper(uc, address, size, user):
            mapped_scores.append(uc.reg_read(UC_ARM_REG_R0))

        estimator_hook = c.uc.hook_add(UC_HOOK_CODE, at_estimator,
            begin=digital_tracking.ESTIMATOR, end=digital_tracking.ESTIMATOR)
        mapper = digital_tracking.robust_fixes.GAP_HELPER
        mapper_hook = c.uc.hook_add(UC_HOOK_CODE, at_mapper, begin=mapper, end=mapper)
        c.uc.mem_write(SP, b'\xa5'*32)
        c.uc.mem_write(SP-256, b'\x5a'*64)
        count = fallback = accepted = 0
        try:
            for label, samples in fragment_vectors():
                estimate.clear()
                mapped_scores.clear()
                expected = digital_tests.model.measure(samples)
                self.detect(c, samples, recent=560, grade=0)
                self.assertEqual(c.read(GRADE), expected['gap'], (label, expected))
                self.assertEqual(mapped_scores, [] if estimate.get('score') is None
                                 else [estimate['score']], label)
                # The retained shared window must remain untagged even when
                # the stack snapshot has visited local and global slicers.
                self.assertEqual(struct.unpack('<32H', c.uc.mem_read(BUFFER, 64)),
                                 tuple(samples[16:48]), label)
                self.assertEqual(c.read(ACTIVE), 1, label)
                count += 1
                accepted += bool(expected['gap'])
                fallback += expected['reason'] == 'established'
            self.assertEqual(count, 6768)
            self.assertEqual(accepted, 3136)
            self.assertEqual(fallback, 3064)
            self.assertEqual(observed_offsets, set(range(16, 65, 2)))
            self.assertEqual(bytes(c.uc.mem_read(SP, 32)), b'\xa5'*32)
            self.assertEqual(bytes(c.uc.mem_read(SP-256, 64)), b'\x5a'*64)
        finally:
            c.uc.hook_del(estimator_hook)
            c.uc.hook_del(mapper_hook)

    def test_exact_fallback_can_use_older_span_instead_of_newest_sixteen(self):
        # This is an explicit compatibility tradeoff, not a promise that all
        # strength estimates always describe the newest 16 samples. The last
        # 16 samples here contain no tone, but two earlier exact matches remain.
        code = (1, 0, 1, 1, 0, 1, 1, 0)
        samples = [1000+300*code[i % 8] for i in range(32)] + [1000]*16
        expected = digital_tests.model.measure(samples)
        self.assertEqual(expected['reason'], 'established')
        self.assertEqual(expected['amplitude'], 300)
        c = self.cpu()
        offsets = []
        def capture(uc, address, size, user):
            offsets.append(uc.reg_read(UC_ARM_REG_R0)-(SP-128))
        hook = c.uc.hook_add(UC_HOOK_CODE, capture,
            begin=digital_tracking.ESTIMATOR, end=digital_tracking.ESTIMATOR)
        try:
            self.detect(c, samples, recent=560, grade=0)
        finally:
            c.uc.hook_del(hook)
        self.assertEqual(c.read(GRADE), expected['gap'])
        self.assertEqual(offsets, [32])  # samples16..31, not newest samples32..47.


if __name__ == '__main__':
    unittest.main()
