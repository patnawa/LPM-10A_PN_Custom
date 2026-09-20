"""Bit-exact integer DFT magnitude, including integer-boundary stress tests."""
import hashlib
import math
import random
import struct
import unittest

from unicorn import UC_HOOK_CODE
from unicorn.arm_const import (UC_ARM_REG_D8, UC_ARM_REG_LR, UC_ARM_REG_PC,
                               UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R4,
                               UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
                               UC_ARM_REG_SP)

import analog_fast
import analog_integer
from lpm10rx.image import PatchError
import test_rx_analog_fast as baseline
import test_rx_robust
from verify_control import BEEP, MODE, SP, STOP
from verify_digital import ACTIVE, BUFFER, GAP


def candidate():
    img = baseline.candidate()
    analog_integer.apply(img)
    return img


class AnalogInteger(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.img = test_rx_robust.candidate()
        cls.previous = bytes(cls.img.data)
        assert hashlib.sha256(cls.previous).hexdigest() == baseline.PARENT_SHA256
        analog_fast.apply(cls.img)
        cls.fast = bytes(cls.img.data)
        analog_integer.apply(cls.img)
        cls.data = bytes(cls.img.data)
        cls.cases = list(baseline.corpus())

    cpu = baseline.AnalogFast.cpu
    execute = baseline.AnalogFast.execute
    magnitude = baseline.AnalogFast.magnitude
    test_bit_exact_all_analog_bins_tones_noise_clipping_dc_and_impulses = baseline.AnalogFast.test_bit_exact_all_analog_bins_tones_noise_clipping_dc_and_impulses
    test_component_sums_match_independent_fixed_point_model = baseline.AnalogFast.test_component_sums_match_independent_fixed_point_model
    test_u16_sample_and_uint8_bin_contract_remains_bit_exact = baseline.AnalogFast.test_u16_sample_and_uint8_bin_contract_remains_bit_exact
    test_original_private_helpers_have_no_remaining_code_or_pointer_references = baseline.AnalogFast.test_original_private_helpers_have_no_remaining_code_or_pointer_references

    def test_integer_patch_scope_prerequisites_and_reconstruction(self):
        changed = {baseline.BASE+i for i, (a, b) in enumerate(zip(self.fast, self.data)) if a != b}
        self.assertTrue(changed <= set(range(analog_integer.TAIL, analog_integer.TAIL_END)))
        self.assertEqual(len(self.data), len(self.previous))
        self.assertEqual(self.img.analog_integer['tail_bytes'], 92)
        reconstructed = bytearray(self.img.original)
        for addr, old, new, why, kind in self.img.log:
            offset = addr-baseline.BASE
            self.assertEqual(bytes(reconstructed[offset:offset+len(old)]), old, why)
            reconstructed[offset:offset+len(new)] = new
        self.assertEqual(bytes(reconstructed), self.data)
        for img in (test_rx_robust.candidate(), self.img):
            with self.assertRaises(PatchError):
                analog_integer.apply(img)
        for start in (analog_fast.LOOP, analog_integer.TAIL, analog_fast.TABLE):
            img = baseline.candidate()
            img.data[start-baseline.BASE] ^= 1
            with self.assertRaises(PatchError):
                analog_integer.apply(img)

    def test_proven_range_and_binary64_rounding_separation(self):
        table = list(struct.iter_unpack('<ii', self.previous[analog_fast.TABLE-baseline.BASE:
                                                           analog_fast.TABLE-baseline.BASE+512]))
        self.assertEqual(max(abs(v) for pair in table for v in pair), 4096)
        bound = analog_integer.MAX_COMPONENT
        max_n = 2*bound*bound
        self.assertLess(max_n, 2**45)
        self.assertLess(math.sqrt(max_n), 2**23)
        self.assertLessEqual(math.ulp(math.sqrt(max_n))/2, 2**-31)
        self.assertGreater(1/(2*math.sqrt(max_n)), 2**-24)
        # Every possible output quantization boundary has sufficient separation,
        # including the full original uint16_t domain, not just 12-bit ADC data.
        for root in range(32, math.isqrt(max_n)+1, 32):
            minimum_distance = 1/(2*root)
            half_ulp = math.ulp(float(root))/2
            self.assertGreater(minimum_distance, half_ulp)

    def test_original_double_tail_matches_integer_on_signed_boundary_components(self):
        bound = analog_integer.MAX_COMPONENT
        pairs = {(0, 0), (bound, bound), (-bound, bound), (bound, -bound), (-bound, -bound)}
        roots = list(range(0, 8193, 32))
        roots += [2**k+d for k in range(4, 23) for d in (-33, -32, -1, 0, 1, 31, 32, 33)]
        roots += list(range(0, math.isqrt(2*bound*bound), 8160))
        for root in roots:
            if not 0 <= root <= math.isqrt(2*bound*bound):
                continue
            real = min(root, bound)
            imag = math.isqrt(max(0, root*root-real*real))
            for r in (real-1, real, real+1):
                for i in (imag-1, imag, imag+1):
                    if 0 <= r <= bound and 0 <= i <= bound:
                        pairs.add((r, i))
                        pairs.add((-r, i))
        rng = random.Random(0x647512)
        pairs.update((rng.randint(-bound, bound), rng.randint(-bound, bound)) for _ in range(512))
        cpus = (self.cpu(self.previous), self.cpu(self.data))
        current = [(0, 0)]
        def inject(uc, address, size, user):
            real, imag = current[0]
            stack = uc.reg_read(UC_ARM_REG_SP)
            uc.mem_write(stack+24, struct.pack('<ii', imag, real))
        hooks = [cpu.uc.hook_add(UC_HOOK_CODE, inject, begin=analog_integer.TAIL,
                                end=analog_integer.TAIL) for cpu in cpus]
        try:
            for real, imag in sorted(pairs):
                current[0] = (real, imag)
                expected = math.isqrt(real*real+imag*imag)//32
                for cpu in cpus:
                    self.assertEqual(self.magnitude(cpu, [0]*64, 0), expected, (real, imag))
        finally:
            for cpu, hook in zip(cpus, hooks):
                cpu.uc.hook_del(hook)
        print('Original double/integer signed component boundary pairs:', len(pairs))

    def test_integer_sqrt_near_every_possible_12bit_adc_output_boundary(self):
        cpu = self.cpu(self.data)
        stack = SP-56
        cpu.uc.mem_write(stack, struct.pack('<III', 0x44, 0x55, 0x66))
        cpu.uc.mem_write(SP-16, struct.pack('<QII', 0x123456789ABCDEF0, 0x77, STOP | 1))
        cpu.uc.mem_write(SP-64, b'\xA5'*8)
        maximum = 2*(64*4095)**2
        count = 0
        # These arbitrary integer N cases are stronger than sums-of-two-squares
        # alone: every integer immediately below/at/above each ADC-domain output
        # boundary is executed through the real restoring-root ARM instructions.
        for root in range(0, math.isqrt(maximum)+33, 32):
            for delta in (-1, 0, 1):
                n = root*root+delta
                if n < 0 or n >= 2**45:
                    continue
                cpu.uc.reg_write(UC_ARM_REG_SP, stack)
                cpu.uc.reg_write(UC_ARM_REG_R0, n & 0xFFFFFFFF)
                cpu.uc.reg_write(UC_ARM_REG_R1, n >> 32)
                cpu.uc.reg_write(UC_ARM_REG_LR, STOP | 1)
                cpu.uc.emu_start(analog_integer.SUMS_READY | 1, STOP, count=1000)
                self.assertEqual(cpu.uc.reg_read(UC_ARM_REG_PC), STOP)
                self.assertEqual(cpu.uc.reg_read(UC_ARM_REG_R0), math.isqrt(n)//32, n)
                self.assertEqual(cpu.uc.reg_read(UC_ARM_REG_SP), SP)
                self.assertEqual([cpu.uc.reg_read(r) for r in
                                  (UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7)],
                                 [0x44, 0x55, 0x66, 0x77])
                self.assertEqual(cpu.uc.reg_read(UC_ARM_REG_D8), 0x123456789ABCDEF0)
                count += 1
        self.assertEqual(bytes(cpu.uc.mem_read(SP-64, 8)), b'\xA5'*8)
        print('Actual ARM integer-root quantization-boundary values:', count)

    def test_complete_analog_mains_results_profile_and_stack_improve(self):
        profiles = []
        for name, samples in self.cases[::3]:
            answers = []
            for data in (self.previous, self.data):
                cpu = self.cpu(data)
                cpu.w8(MODE, 1)
                cpu.w16(0x20000068, 580)
                cpu.w16(0x2000006A, 1)
                cpu.w8(ACTIVE, 0)
                cpu.uc.mem_write(BUFFER, struct.pack('<64H', *samples))
                self.execute(cpu, 0x08009F58)
                answers.append((cpu.read(BEEP), cpu.read(GAP), cpu.read(ACTIVE)))
            self.assertEqual(answers[0], answers[1], name)
        for k in (5, 6):
            cpu = self.cpu(self.data)
            cpu.w8(MODE, 2)
            cpu.w16(0x2000006A, 1)
            cpu.w8(ACTIVE, 0)
            cpu.uc.mem_write(BUFFER, struct.pack('<64H', *baseline.sine(baseline.SAMPLE_HZ*k/64, 1800)))
            self.execute(cpu, 0x080085F4)
            self.assertEqual((cpu.read(BEEP), cpu.read(GAP), cpu.read(ACTIVE)), (50, 50, 1))
        for name, samples in (('dc', [2048]*64), ('normal', baseline.sine()),
                              ('clipped', baseline.sine(amplitude=8000))):
            measurements = []
            for data in (self.previous, self.fast, self.data):
                cpu = self.cpu(data)
                cpu.w8(MODE, 1)
                cpu.w16(0x20000068, 580)
                cpu.w16(0x2000006A, 1)
                cpu.w8(ACTIVE, 0)
                cpu.uc.mem_write(BUFFER, struct.pack('<64H', *samples))
                count = [0, 0]
                def visit(uc, address, size, user):
                    count[0] += 1
                    count[1] = max(count[1], SP-uc.reg_read(UC_ARM_REG_SP))
                hook = cpu.uc.hook_add(UC_HOOK_CODE, visit)
                try:
                    self.execute(cpu, 0x08009F58)
                finally:
                    cpu.uc.hook_del(hook)
                measurements.append(tuple(count))
            self.assertLess(measurements[2][0], measurements[0][0]*0.30)
            self.assertEqual(measurements[2][1], 144)
            profiles.append((name, *measurements))
        print('Analog [instructions/stack]: original, fast loop, integer magnitude:', profiles)


if __name__ == '__main__':
    unittest.main()
