"""RX audit regressions: real DFT arithmetic and real TIM5 preemption model."""
import cmath
import math
from pathlib import Path
import random
import struct

from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm_const import *
from verify_control import Control, STOP, SP, SAVED
import test_roadmap
import rx_patches
from audit_fixes import PATCHES, OUTPUT

BUFFER, ACTIVE = 0x2000006E, 0x20000008


class Audit(test_roadmap.Roadmap):
    @classmethod
    def setUpClass(cls):
        cls.img = test_roadmap.candidate()
        cls.previous = bytes(cls.img.data)
        for patch in rx_patches.REGISTRY:
            if patch.pid in PATCHES:
                patch(cls.img)
        cls.data = bytes(cls.img.data)

    def test_image_ownership_and_unchanged_size_vectors_binding(self):
        fw = Path(__file__).resolve().parent.parent
        self.assertEqual((fw / OUTPUT).read_bytes(), self.data)
        self.assertEqual((fw / rx_patches.ROADMAP_EXPERIMENT).read_bytes(), self.previous)
        self.assertEqual(len(self.data), len(self.previous))
        changed = {i + 0x08006800 for i, (a, b) in enumerate(zip(self.previous, self.data)) if a != b}
        allowed = set(range(0x080086F2, 0x0800870C)) | set(range(0x0800B52C, 0x0800B5A0))
        self.assertTrue(changed <= allowed, sorted(changed - allowed))
        rebuilt = bytearray(self.img.original)
        for addr, old, new, why, kind in self.img.log:
            offset = addr - 0x08006800
            self.assertEqual(bytes(rebuilt[offset:offset+len(old)]), old, why)
            rebuilt[offset:offset+len(new)] = new
        self.assertEqual(bytes(rebuilt), self.data)

    def test_existing_key_power_and_timer_suite(self):
        from verify_control import run_checks
        run_checks(self.img.original, self.data,
                   lambda ok, label, detail='': self.assertTrue(ok, label + ': ' + detail),
                   roadmap=True, mains_rearm=True)

    def cpu(self, data):
        c = Control(data)
        c.uc.reg_write(UC_ARM_REG_C1_C0_2, 0xF00000)
        c.uc.reg_write(UC_ARM_REG_FPEXC, 0x40000000)
        return c

    def execute(self, c, entry, *args):
        for reg, value in zip((UC_ARM_REG_R0, UC_ARM_REG_R1), args):
            c.uc.reg_write(reg, value)
        values = [0xABCD0000 + n for n in range(len(SAVED))]
        for reg, value in zip(SAVED, values):
            c.uc.reg_write(reg, value)
        c.uc.reg_write(UC_ARM_REG_D8, 0x123456789ABCDEF0)
        c.uc.reg_write(UC_ARM_REG_SP, SP)
        c.uc.reg_write(UC_ARM_REG_LR, STOP | 1)
        c.uc.emu_start(entry | 1, STOP, count=4000000)
        self.assertEqual(c.uc.reg_read(UC_ARM_REG_PC), STOP)
        self.assertEqual(c.uc.reg_read(UC_ARM_REG_SP), SP)
        self.assertEqual([c.uc.reg_read(r) for r in SAVED], values)
        self.assertEqual(c.uc.reg_read(UC_ARM_REG_D8), 0x123456789ABCDEF0)
        return c.uc.reg_read(UC_ARM_REG_R0)

    def samples(self, amplitude, k=17, phase=0):
        return [round(2048 + amplitude * math.cos(2 * math.pi * k * i / 64 + phase)) for i in range(64)]

    def magnitude(self, c, samples, k):
        c.uc.mem_write(BUFFER, struct.pack('<64H', *samples))
        return self.execute(c, 0x0800B4A0, k)

    def test_released_dft_loses_strong_valid_adc_signal(self):
        old, new = self.cpu(self.previous), self.cpu(self.data)
        for k in (5, 6, 17):
            for amplitude in (1450, 1500, 1800, 2000):
                samples = self.samples(amplitude, k)
                self.assertEqual(self.magnitude(old, samples, k), 0)
                self.assertLessEqual(abs(self.magnitude(new, samples, k) - amplitude), 2)

    def test_dft_bins_amplitudes_phases_against_independent_complex_sum(self):
        c = self.cpu(self.data)
        for k in (0, 1, 5, 6, 17, 31):
            for amplitude in (0, 10, 150, 350, 1000, 1400, 1450, 2000, 2047):
                for phase in (0, math.pi/4, math.pi/2):
                    samples = self.samples(amplitude, k, phase)
                    expected = 2 * abs(sum(value * cmath.exp(-2j * math.pi * k * i / 64)
                                           for i, value in enumerate(samples))) / 64
                    self.assertLessEqual(abs(self.magnitude(c, samples, k) - expected), 2,
                                         (k, amplitude, phase, expected))
        rng = random.Random(8531)
        for _ in range(8):
            samples = [rng.randrange(4096) for _ in range(64)]
            for k in (1, 5, 6, 17, 31):
                expected = 2 * abs(sum(value * cmath.exp(-2j * math.pi * k * i / 64)
                                       for i, value in enumerate(samples))) / 64
                self.assertLessEqual(abs(self.magnitude(c, samples, k) - expected), 2)

    def test_complete_analog_and_mains_analysis_accept_strong_signal(self):
        for data, expected_beep in ((self.previous, 0), (self.data, 50)):
            for mode, bin_index, entry in ((1, 17, 0x08009F58), (2, 5, 0x080085F4), (2, 6, 0x080085F4)):
                c = self.cpu(data)
                c.w8(0x20000048, mode)
                c.w16(0x2000006A, 1)
                c.uc.mem_write(BUFFER, struct.pack('<64H', *self.samples(1800, bin_index)))
                self.execute(c, entry)
                self.assertEqual(c.read(0x2000010C), expected_beep)
                self.assertEqual(c.read(ACTIVE), 1)

    def mains_handoff(self, data):
        c = Control(data)
        c.w8(0x20000048, 2)
        c.w32(0x20000100, 61)  # next actual TIM5 call samples channel 7
        c.uc.mem_write(BUFFER, b'\xAA' * 128)
        armed = []
        def memory(uc, access, addr, size, value, user):
            if addr == ACTIVE and value == 1:
                armed.append(True)
        def stop_after_publish(uc, addr, size, user):
            if addr == 0x0800B4A0:
                uc.reg_write(UC_ARM_REG_R0, 500)
                uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
            elif armed:
                uc.emu_stop()
        write_hook = c.uc.hook_add(UC_HOOK_MEM_WRITE, memory)
        code_hook = c.uc.hook_add(UC_HOOK_CODE, stop_after_publish)
        c.uc.reg_write(UC_ARM_REG_SP, SP)
        c.uc.reg_write(UC_ARM_REG_LR, STOP | 1)
        c.uc.emu_start(0x080085F5, STOP, count=4000)
        self.assertTrue(armed)
        context, resume = c.uc.context_save(), c.uc.reg_read(UC_ARM_REG_PC)
        c.uc.hook_del(code_hook)
        c.uc.hook_del(write_hook)
        def adc(uc, addr, size, user):
            if addr == 0x080072A4:
                self.assertEqual(uc.reg_read(UC_ARM_REG_R1), 7)
                uc.reg_write(UC_ARM_REG_R0, 1234)
                uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
        adc_hook = c.uc.hook_add(UC_HOOK_CODE, adc)
        c.uc.reg_write(UC_ARM_REG_SP, SP - 0x100)
        c.uc.reg_write(UC_ARM_REG_LR, STOP | 1)
        c.uc.emu_start(0x0800AC1D, STOP, count=4000)
        self.assertEqual(c.uc.reg_read(UC_ARM_REG_PC), STOP)
        self.assertEqual(c.read(BUFFER, 2), 1234)
        self.assertEqual(c.read(0x20000108), 1)
        c.uc.hook_del(adc_hook)
        c.uc.context_restore(context)
        c.uc.emu_start(resume | 1, STOP, count=4000)
        self.assertEqual(c.uc.reg_read(UC_ARM_REG_PC), STOP)
        return c

    def test_tim5_sample_survives_main_analyzer_handoff(self):
        for data, expected in ((self.previous, 0), (self.data, 1234)):
            c = self.mains_handoff(data)
            self.assertEqual(c.read(BUFFER, 2), expected)
            self.assertEqual(c.read(0x20000108), 1)
            self.assertEqual(bytes(c.uc.mem_read(BUFFER+2, 126)), bytes(126))


if __name__ == '__main__':
    import unittest
    unittest.main()
