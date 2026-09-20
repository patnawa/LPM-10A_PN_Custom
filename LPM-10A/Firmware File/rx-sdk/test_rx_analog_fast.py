"""Execute the original and optimized ARM DFT on identical synthetic ADC data.

These tests establish bit-exact arithmetic/eligibility, ABI and instruction
count contracts; they do not measure Cortex-M cycles or analogue selectivity.
"""
import hashlib
import math
from pathlib import Path
import random
import struct
import unittest

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_MCLASS
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import (UC_ARM_REG_D8, UC_ARM_REG_D9, UC_ARM_REG_D10,
                               UC_ARM_REG_D11, UC_ARM_REG_D12, UC_ARM_REG_D13,
                               UC_ARM_REG_D14, UC_ARM_REG_D15, UC_ARM_REG_PRIMASK,
                               UC_ARM_REG_SP)

import analog_fast
from lpm10rx.image import PatchError
import test_firmware_audit
import test_rx_robust
from verify_control import BEEP, MODE, SP
from verify_digital import ACTIVE, BUFFER, GAP

BASE = 0x08006800
PARENT_SHA256 = '6128e0a4a0261f3da51bea232c8e431474033f0a09fd24283faa0a743b67fe3e'
FP_SAVED = (UC_ARM_REG_D8, UC_ARM_REG_D9, UC_ARM_REG_D10, UC_ARM_REG_D11,
            UC_ARM_REG_D12, UC_ARM_REG_D13, UC_ARM_REG_D14, UC_ARM_REG_D15)
SAMPLE_HZ = 64_000_000 / 1601 / 13


def sine(hz=1_000_000/101/12, amplitude=300, phase=0, dc=2048):
    return [max(0, min(4095, round(dc + amplitude * math.cos(
        2*math.pi*hz*i/SAMPLE_HZ + phase)))) for i in range(64)]


def corpus():
    for level in (0, 1, 25, 1000, 2048, 4095):
        yield f'dc_{level}', [level]*64
    for hz in (50, 60, 700, 800, SAMPLE_HZ*17/64, 1_000_000/101/12, 900,
               SAMPLE_HZ-1_000_000/101/12):
        for amplitude, phase in ((15, 0), (300, 0.25), (1800, 0.8), (8000, 1.3)):
            yield f'sine_{hz}_{amplitude}_{phase}', sine(hz, amplitude, phase)
    for step in (1, 20, 100, 300, 1000, 3095):
        for phase in (0, 0.125, 0.5):
            yield f'square_{step}_{phase}', [1000 + step*int(
                (i*(1_000_000/101/12)/SAMPLE_HZ+phase) % 1 >= 0.5) for i in range(64)]
    rng = random.Random(0xDF72026)
    for magnitude in (10, 100, 400, 800, 1600, 2047):
        yield f'noise_{magnitude}', [2048+rng.randint(-magnitude, magnitude) for _ in range(64)]
    for index in (0, 1, 16, 31, 32, 63):
        values = [0]*64
        values[index] = 4095
        yield f'impulse_{index}', values
    yield 'alternating_rails', [0, 4095]*32
    yield 'adc_ramp', [i*65 for i in range(64)]


def candidate():
    img = test_rx_robust.candidate()
    analog_fast.apply(img)
    return img


class AnalogFast(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.img = test_rx_robust.candidate()
        cls.previous = bytes(cls.img.data)
        assert hashlib.sha256(cls.previous).hexdigest() == PARENT_SHA256
        analog_fast.apply(cls.img)
        cls.data = bytes(cls.img.data)
        cls.cases = list(corpus())

    cpu = test_rx_robust.Robust.cpu
    execute = test_firmware_audit.Audit.execute

    def magnitude(self, cpu, samples, k, profile=False):
        cpu.uc.mem_write(BUFFER, struct.pack('<64H', *samples))
        before = bytes(cpu.uc.mem_read(BUFFER, 128))
        # Existing execute() checks r4-r11, d8 and SP on every invocation.
        expected_fp = [0x123456789ABCDEF0] + [0xABCD000000000000+i for i in range(1, 8)]
        for register, value in zip(FP_SAVED, expected_fp):
            cpu.uc.reg_write(register, value)
        cpu.uc.mem_write(SP-640, b'\xA5'*64)
        cpu.uc.mem_write(SP, b'\x5A'*32)
        cpu.uc.reg_write(UC_ARM_REG_PRIMASK, k & 1)
        observed = {'instructions': 0, 'maximum_stack_bytes': 0}
        def count(uc, address, size, user):
            observed['instructions'] += 1
            observed['maximum_stack_bytes'] = max(observed['maximum_stack_bytes'],
                                                   SP-uc.reg_read(UC_ARM_REG_SP))
        hook = cpu.uc.hook_add(UC_HOOK_CODE, count) if profile else None
        try:
            result = self.execute(cpu, analog_fast.DFT, k)
        finally:
            if hook is not None:
                cpu.uc.hook_del(hook)
        self.assertEqual(bytes(cpu.uc.mem_read(BUFFER, 128)), before)
        self.assertEqual(bytes(cpu.uc.mem_read(SP-640, 64)), b'\xA5'*64)
        self.assertEqual(bytes(cpu.uc.mem_read(SP, 32)), b'\x5A'*32)
        self.assertEqual([cpu.uc.reg_read(r) for r in FP_SAVED], expected_fp)
        self.assertEqual(cpu.uc.reg_read(UC_ARM_REG_PRIMASK), k & 1)
        return (result, observed) if profile else result

    def test_patch_scope_size_log_reconstruction_and_guards(self):
        self.assertEqual(len(self.data), len(self.previous))
        changed = {BASE+i for i, (old, new) in enumerate(zip(self.previous, self.data)) if old != new}
        self.assertTrue(changed <= set(range(analog_fast.LOOP, analog_fast.LOOP_END)))
        self.assertEqual(self.img.analog_fast['loop_bytes'], 92)
        reconstructed = bytearray(self.img.original)
        for addr, old, new, why, kind in self.img.log:
            offset = addr-BASE
            self.assertEqual(bytes(reconstructed[offset:offset+len(old)]), old, why)
            reconstructed[offset:offset+len(new)] = new
        self.assertEqual(reconstructed, self.img.data)
        with self.assertRaises(PatchError):
            analog_fast.apply(self.img)
        for start, end in analog_fast.GUARDS:
            img = test_rx_robust.candidate()
            img.data[start-BASE] ^= 1
            with self.assertRaises(PatchError):
                analog_fast.apply(img)

    def test_bit_exact_all_analog_bins_tones_noise_clipping_dc_and_impulses(self):
        old, new = self.cpu(self.previous), self.cpu(self.data)
        for name, samples in self.cases:
            for k in range(1, 32):
                self.assertEqual(self.magnitude(new, samples, k),
                                 self.magnitude(old, samples, k), (name, k))

    def test_component_sums_match_independent_fixed_point_model(self):
        # This checks signed per-product truncation, not only the final magnitude.
        table = list(struct.iter_unpack('<ii', self.previous[analog_fast.TABLE-BASE:
                                                           analog_fast.TABLE-BASE+512]))
        new = self.cpu(self.data)
        actual = []
        def sums(uc, address, size, user):
            stack = uc.reg_read(UC_ARM_REG_SP)
            imag, real = struct.unpack('<ii', uc.mem_read(stack+24, 8))
            actual.append((real, imag))
        hook = new.uc.hook_add(UC_HOOK_CODE, sums, begin=analog_fast.LOOP_END,
                              end=analog_fast.LOOP_END)
        try:
            for name, samples in self.cases[::3]:
                for k in (0, 1, 5, 6, 17, 31, 32, 63, 64, 127, 255, 256, 511):
                    reference = tuple(sum(math.trunc(value*table[(i*(k & 255)) & 63][axis]/4096)
                                          for i, value in enumerate(samples)) for axis in (0, 1))
                    self.magnitude(new, samples, k)
                    self.assertEqual(actual.pop(), reference, (name, k))
        finally:
            new.uc.hook_del(hook)

    def test_u16_sample_and_uint8_bin_contract_remains_bit_exact(self):
        rng = random.Random(0xFFFFDF7)
        old, new = self.cpu(self.previous), self.cpu(self.data)
        # Firmware ADC is 12-bit; also exercise the full original uint16_t contract.
        for samples in ([65535]*64, [0, 65535]*32, [rng.randrange(65536) for _ in range(64)]):
            for k in (0, 1, 5, 6, 17, 31, 32, 63, 64, 127, 255, 256, 511):
                self.assertEqual(self.magnitude(new, samples, k), self.magnitude(old, samples, k), k)

    def test_original_private_helpers_have_no_remaining_code_or_pointer_references(self):
        cs = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS)
        helper_start, helper_end = analog_fast.RETIRED_HELPERS
        def references(data):
            refs = []
            for offset in range(0, len(data)-3, 2):
                instructions = list(cs.disasm(data[offset:offset+4], BASE+offset, count=1))
                if instructions and instructions[0].mnemonic in ('bl', 'b.w', 'b'):
                    operand = instructions[0].op_str
                    if operand.startswith('#0x') and helper_start <= int(operand[1:], 16) < helper_end:
                        refs.append(BASE+offset)
            for addr in range(helper_start, helper_end, 2):
                for pointer in (addr, addr | 1):
                    self.assertNotIn(struct.pack('<I', pointer), data)
            return refs
        self.assertEqual(references(self.previous), [0x0800B4DA, 0x0800B4EE])
        self.assertEqual(references(self.data), [])

    def test_complete_analog_and_mains_results_unchanged_and_dft_instructions_reduced(self):
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
        for mode, entry, k in ((1, 0x08009F58, 17), (2, 0x080085F4, 5), (2, 0x080085F4, 6)):
            answers = []
            for data in (self.previous, self.data):
                cpu = self.cpu(data)
                cpu.w8(MODE, mode)
                cpu.w16(0x20000068, 580)
                cpu.w16(0x2000006A, 1)
                cpu.w8(ACTIVE, 0)
                cpu.uc.mem_write(BUFFER, struct.pack('<64H', *sine(SAMPLE_HZ*k/64, 1800)))
                self.execute(cpu, entry)
                answers.append((cpu.read(BEEP), cpu.read(GAP), cpu.read(ACTIVE)))
            self.assertEqual(answers, [(50, 50, 1)]*2, (mode, k))
        for name, samples in (('dc', [2048]*64), ('weak', sine(amplitude=15)),
                              ('normal', sine()), ('clipped', sine(amplitude=8000))):
            old_result, old = self.magnitude(self.cpu(self.previous), samples, 17, profile=True)
            new_result, new = self.magnitude(self.cpu(self.data), samples, 17, profile=True)
            self.assertEqual(old_result, new_result)
            self.assertLess(new['instructions'], old['instructions']*0.62)
            self.assertEqual(new['maximum_stack_bytes'], old['maximum_stack_bytes'])
            profiles.append((name, old['instructions'], new['instructions'], new['maximum_stack_bytes']))
        print('DFT profiles (case, original instructions, optimized instructions, max stack bytes):', profiles)

    def test_full_analog_analyzer_instruction_saving_is_31_times_bin_saving(self):
        profiles = []
        for name, samples in (('dc', [2048]*64), ('normal', sine()),
                              ('clipped', sine(amplitude=8000))):
            counts = []
            answers = []
            for data in (self.previous, self.data):
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
                counts.append(tuple(count))
                answers.append((cpu.read(BEEP), cpu.read(GAP), cpu.read(ACTIVE)))
            self.assertEqual(answers[0], answers[1], name)
            self.assertEqual(counts[0][0]-counts[1][0], 31*3260)
            self.assertEqual(counts[0][1], counts[1][1])
            profiles.append((name, counts[0], counts[1]))
        print('Analog profiles (case, original [instructions/stack], optimized [instructions/stack]):', profiles)


if __name__ == '__main__':
    unittest.main()
