"""ARM comparisons for local B6 acquisition and recent strength tracking."""
from pathlib import Path
import random
import struct
import sys
import unittest

from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_PRIMASK, UC_ARM_REG_SP

import analog_fast
import analog_feedback
import digital_overlap
import digital_tracking
from lpm10rx.image import PatchError
import test_rx_robust
from test_rx_followup import GRADE, INDICES
from verify_control import SP
from verify_digital import ACTIVE, BUFFER, RECENT

sys.path.insert(0, str(Path(__file__).resolve().parents[3]/'docs'/'experiments'))
import digital_acquisition_candidate as model
import digital_bundle_audit as old
from scan_sync_model import sampled_window


def candidate():
    img = test_rx_robust.candidate()
    analog_fast.apply(img)
    analog_feedback.apply(img)
    digital_overlap.apply(img)
    digital_tracking.apply(img)
    return img


class DigitalTracking(unittest.TestCase):
    cpu = test_rx_robust.Robust.cpu
    detect = test_rx_robust.Robust.detect
    execute = test_rx_robust.Robust.execute
    @classmethod
    def setUpClass(cls):
        cls.img = candidate()
        cls.data = bytes(cls.img.data)

    def verify_rows(self, rows):
        c = self.cpu()
        scores = []
        def mapper(uc, addr, size, user):
            scores.append(uc.reg_read(UC_ARM_REG_R0))
        hook = c.uc.hook_add(UC_HOOK_CODE, mapper,
                            begin=digital_tracking.robust_fixes.GAP_HELPER,
                            end=digital_tracking.robust_fixes.GAP_HELPER)
        try:
            for label, samples in rows:
                scores.clear()
                c.uc.reg_write(UC_ARM_REG_PRIMASK, 0)
                self.detect(c, samples, recent=560, grade=0)
                expected = model.measure(samples)
                self.assertEqual(c.read(GRADE), expected['gap'], (label, expected))
                amplitude = expected['amplitude']
                expected_score = (29*amplitude-12*(29*amplitude//46)
                                  if amplitude is not None else None)
                self.assertEqual(scores, [] if expected_score is None else [expected_score], label)
                self.assertEqual(c.read(RECENT, 2), 800 if expected['gap'] else 560, label)
                self.assertEqual(c.read(ACTIVE), 1, label)
                self.assertEqual(c.read(INDICES[0]), 32, label)
                retained = struct.unpack('<32H', c.uc.mem_read(BUFFER, 64))
                self.assertEqual(retained, tuple(samples[16:48]), label)
                self.assertEqual(c.uc.reg_read(UC_ARM_REG_PRIMASK), 0, label)
        finally:
            c.uc.hook_del(hook)

    def test_audit_counterexamples_and_every_step_position(self):
        self.verify_rows((r['name'], r['samples']) for r in old.cases())

    def test_sampler_clean_and_noisy_phase_clock_compatibility(self):
        self.verify_rows((f'{fresh}_{ratio}_{noise}_{phase}', sampled_window(
            'legacy', phase/8, ratio, noise, random.Random(model.SEED+phase),
            amplitude=300, fresh_start=fresh))
            for fresh in (False, True) for ratio in (0.98, 0.997, 1, 1.003, 1.02)
            for noise in (0, 100, 300) for phase in range(64))

    def test_competing_periodic_words_and_noise(self):
        rows = []
        for word in range(256):
            rows.append((f'period8_{word:02x}',
                         [1000+300*((word>>(7-i%8))&1) for i in range(48)]))
        rng = random.Random(model.SEED+919)
        for i in range(1024):
            rows.append((f'noise_{i}', [rng.randrange(4096) for _ in range(48)]))
        self.verify_rows(rows)

    def test_every_two_rail_position_pair_at_each_phase(self):
        rows = []
        for phase in range(8):
            for first in range(48):
                for second in range(first+1, 48):
                    samples = old.waveform(100, 1000, phase)
                    samples[first] = samples[second] = 4095
                    rows.append((f'p{phase}_{first}_{second}', samples))
        self.verify_rows(rows)

    def test_scope_guards_and_size(self):
        prior = test_rx_robust.candidate()
        with self.assertRaises(PatchError):
            digital_tracking.apply(prior)
        self.assertEqual(len(self.data), len(prior.data))
        self.assertEqual(self.img.digital_tracking['persistent_ram_bytes'], 0)
        allowed = ((analog_fast.LOOP, analog_fast.LOOP_END),
                   (analog_feedback.ANALYZER, analog_feedback.ANALYZER_END),
                   (analog_feedback.SPEAKER_DISPATCH, analog_feedback.SPEAKER_END),
                   (digital_tracking.DETECTOR, digital_tracking.PUBLISH),
                   (digital_tracking.LOCAL, digital_tracking.LOCAL_END),
                   (digital_tracking.ESTIMATOR, digital_tracking.ESTIMATOR_END))
        for i, (before, after) in enumerate(zip(prior.data, self.data)):
            if before != after:
                self.assertTrue(any(start <= 0x08006800+i < end for start, end in allowed), hex(i))
        for address in (digital_tracking.DETECTOR, digital_tracking.ESTIMATOR,
                        digital_tracking.LOCAL, analog_fast.LOOP, digital_overlap.HELPER):
            img = test_rx_robust.candidate()
            analog_fast.apply(img)
            analog_feedback.apply(img)
            digital_overlap.apply(img)
            img.data[img.f(address)] ^= 1
            before = bytes(img.data)
            with self.assertRaises(PatchError):
                digital_tracking.apply(img)
            self.assertEqual(bytes(img.data), before)

    def test_write_ownership_and_stack_profile(self):
        c = self.cpu()
        writes, instructions, depths = [], [], []
        def at_instruction(uc, addr, size, user):
            instructions.append(addr)
            depths.append(SP-uc.reg_read(UC_ARM_REG_SP))
        code = c.uc.hook_add(UC_HOOK_CODE, at_instruction)
        mem = c.uc.hook_add(UC_HOOK_MEM_WRITE,
                            lambda uc, access, addr, size, value, user: writes.append((addr,size)))
        try:
            profiles = {}
            for label, samples in (
                    ('clean_local', old.waveform()), ('rejected_flat', [1000]*48),
                    ('sampler_fallback', sampled_window('legacy', 5/16)),
                    ('random', [random.Random(i).randrange(4096) for i in range(48)])):
                c.uc.mem_write(BUFFER, struct.pack('<48H', *samples))
                c.w8(ACTIVE, 0)
                c.w8(GRADE, 0)
                c.w16(RECENT, 560)
                writes.clear(); instructions.clear(); depths.clear()
                self.execute(c, digital_tracking.DETECTOR, budget=30000)
                for address, size in writes:
                    self.assertTrue(SP-256 <= address and address+size <= SP
                        or BUFFER <= address and address+size <= BUFFER+64
                        or address in (ACTIVE, INDICES[0], GRADE, RECENT), hex(address))
                profiles[label] = {'instructions': len(instructions), 'max_stack_bytes': max(depths)}
            self.__class__.profiles = profiles
        finally:
            c.uc.hook_del(code); c.uc.hook_del(mem)

    def test_primask_and_incomplete_acquisition(self):
        c = self.cpu()
        for mask in (0, 1):
            for samples in (old.waveform(), sampled_window('legacy', 5/16), [1000]*48):
                c.uc.reg_write(UC_ARM_REG_PRIMASK, mask)
                self.detect(c, samples, recent=560, grade=0)
                self.assertEqual(c.uc.reg_read(UC_ARM_REG_PRIMASK), mask)
            c.uc.mem_write(BUFFER, struct.pack('<48H', *old.waveform()))
            c.w8(ACTIVE, 1)
            c.w8(INDICES[0], 36)
            c.w8(GRADE, 53)
            c.w16(RECENT, 560)
            before = bytes(c.uc.mem_read(0x20000000, 0x200))
            self.execute(c, digital_tracking.DETECTOR, budget=30000)
            self.assertEqual(bytes(c.uc.mem_read(0x20000000, 0x200)), before)
            self.assertEqual(c.uc.reg_read(UC_ARM_REG_PRIMASK), mask)


if __name__ == '__main__':
    unittest.main()
