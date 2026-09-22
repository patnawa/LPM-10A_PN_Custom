"""PN2.24 Length acquisition/voting/averaging CPU audit on the integrated image.

PHY result registers and RTOS time are modeled. The complete acquisition
sequence, vendor vote, averaging and result publication execute real Thumb.
Numeric u16 endpoints here are arithmetic inputs, not claims about PHY codes.
"""
import contextlib
import io
import itertools
import random
import struct
import unittest

from audit_flash_length import FLAGS, Machine
from unicorn.arm_const import UC_ARM_REG_SP


class PipelineMachine(Machine):
    def __init__(self, data):
        super().__init__(data, 7)
        self.votes = []
        self.handlers[0x08012AE0] = self.capture_vote

    def capture_vote(self, machine):
        sp = self.uc.reg_read(UC_ARM_REG_SP)
        self.votes.append(tuple(struct.unpack('<4H', self.uc.mem_read(sp+0x4C, 8))))
        # No return stub: continue through the actual averaging hook.


class LengthAuditPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import length_integrity
        with contextlib.redirect_stdout(io.StringIO()):
            cls.img = length_integrity.build_candidate()
        cls.data = bytes(cls.img.data)

    def acquire(self, runs):
        m = PipelineMachine(self.data)
        m.runs = [tuple(row) for row in runs]
        m.call(0x080119EC)
        self.assertEqual(m.run_index+1, 4)
        self.assertEqual(m.r8(FLAGS), 2)  # acquisition complete, before GUI result drawing
        self.assertEqual(len(m.votes), 4)
        return m

    def test_uniform_four_run_boundary_inputs_preserve_accepted_values(self):
        for value in (0, 1, 199, 200, 201, 202, 999, 1000, 32767, 32768, 65534, 65535):
            with self.subTest(value=value):
                expected = value if value > 200 else 0
                m = self.acquire([(value,)*4]*4)
                self.assertEqual(m.lengths(), [expected]*4)

    def test_complete_sequence_averages_actual_runs_and_ignores_zero_runs(self):
        for values, expected in (((1000, 1200, 1400, 1600), 1300),
                                 ((1000, 0, 0, 0), 1000),
                                 ((0, 0, 0, 1000), 1000),
                                 ((65535, 65534, 65533, 65532), 65533)):
            with self.subTest(values=values):
                m = self.acquire([(value,)*4 for value in values])
                self.assertEqual(m.lengths(), [expected]*4)

    def test_real_vote_outputs_use_each_pairs_own_nonzero_denominator(self):
        rng = random.Random(0x10A)
        boundary = (0, 199, 200, 201, 202, 333, 1000, 1500, 10000, 32768, 65534, 65535)
        cases = [[(0, 1000, 0, 1400), (0, 0, 1500, 1401),
                  (0, 1002, 1501, 0), (0, 0, 0, 1403)]]
        cases += [[tuple(rng.choice(boundary) for _ in range(4)) for _ in range(4)]
                  for _ in range(64)]
        for runs in cases:
            with self.subTest(runs=runs):
                m = self.acquire(runs)
                want = []
                for pair in range(4):
                    valid = [vote[pair] for vote in m.votes if vote[pair]]
                    want.append(sum(valid)//len(valid) if valid else 0)
                self.assertEqual(m.lengths(), want)

    def test_vendor_vote_is_equivariant_under_pair_register_permutations(self):
        rng = random.Random(0x10A)
        cases = [(1000, 1000, 1000, 5000), (1000, 1000, 1200, 1200),
                 (1000, 1100, 1200, 1300), (0, 0, 201, 400),
                 (201, 200, 65535, 65534)]
        for _ in range(19):
            base = rng.choice((201, 1000, 5000, 10000, 20000, 32768, 65000))
            cases.append(tuple(max(0, min(65535, base+rng.choice(
                (-501, -500, -301, -300, -101, -100, -1, 0, 1, 100, 101, 300, 301, 500, 501))))
                for _ in range(4)))
        for values in cases:
            reference = self.acquire([values]*4).lengths()
            for permutation in itertools.permutations(range(4)):
                with self.subTest(values=values, permutation=permutation):
                    permuted = tuple(values[i] for i in permutation)
                    actual = self.acquire([permuted]*4).lengths()
                    self.assertEqual(actual, [reference[i] for i in permutation])

    def test_previous_measurement_and_poisoned_accumulator_cannot_bias_next_mean(self):
        m = PipelineMachine(self.data)
        for runs, expected in (([(65535,)*4]*4, [65535]*4),
                               ([(0,)*4]*4, [0]*4),
                               ([(201,)*4]*4, [201]*4)):
            m.uc.mem_write(self.img.avg_acc, bytes((255,))*20)
            m.run_index = -1
            m.votes.clear()
            m.runs = runs
            m.call(0x080119EC)
            self.assertEqual(m.lengths(), expected)

    def test_negative_control_detects_a_missing_three_acquisitions(self):
        data = bytearray(self.data)
        payload_offset = struct.unpack_from('<I', data, 0x20)[0]
        site = payload_offset+0x080197B8-0x0800A000
        self.assertEqual(data[site:site+2], bytes.fromhex('0428'))
        data[site:site+2] = bytes.fromhex('0128')  # test-only: AVG_RUNS 4 -> 1
        m = PipelineMachine(bytes(data))
        m.runs = [(value,)*4 for value in (1000, 1200, 1400, 1600)]
        m.call(0x080119EC)
        self.assertEqual(m.run_index+1, 1)
        self.assertNotEqual(m.lengths(), [1300]*4)


if __name__ == '__main__':
    unittest.main()
