"""Bit-exact Analog decisions with less CPU work on the PN1.23G path.

ADC vectors and interrupt delivery are modeled. Instruction counts are not
hardware cycles, detection range, or measured noise performance.
"""
import contextlib
import io
import math
import random
import struct
import unittest

from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_PRIMASK, UC_ARM_REG_SP

import digital_gain_continuity
import analog_selective
import test_rx_robust as robust
from test_rx_analog_feedback import sine, FS, TX_HZ
from test_rx_analog_fast import corpus
from test_rx_followup import ANALYZERS, GATE_STATE, GRADE, REQUEST
from verify_control import BEEP, MODE, SP
from verify_digital import ACTIVE, BUFFER, GAP, GATE, RECENT


class AnalogSelective(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with contextlib.redirect_stdout(io.StringIO()):
            cls.img = digital_gain_continuity.build_candidate()
        cls.previous = bytes(cls.img.data)
        analog_selective.install(cls.img)
        cls.data = bytes(cls.img.data)

    cpu = robust.Robust.cpu
    execute = robust.Robust.execute

    def ready(self, c, samples):
        c.w8(MODE, 1)
        c.w16(GATE, 580)
        c.w16(GATE+2, 1)
        c.w8(GATE_STATE, 2)
        c.w8(REQUEST, 0)
        c.w8(0x20000200, 1)
        c.w8(ACTIVE, 0)
        c.w8(GRADE, 0)
        c.w8(GAP, 0)
        c.w8(BEEP, 0)
        c.w16(RECENT, 0)
        c.uc.mem_write(BUFFER, struct.pack('<64H', *samples))

    def analyze(self, c, samples, *, profile=False, mask=0):
        self.ready(c, samples)
        c.uc.reg_write(UC_ARM_REG_PRIMASK, mask)
        observed = dict(instructions=0, stack=0, bins=[], scores=[])
        def trace(uc, address, size, user):
            if profile:
                observed['instructions'] += 1
                observed['stack'] = max(observed['stack'], SP-uc.reg_read(UC_ARM_REG_SP))
            if address == 0x0800B4A0:
                observed['bins'].append(uc.reg_read(UC_ARM_REG_R0))
            elif address == 0x0800A048:
                observed['scores'].append(uc.reg_read(UC_ARM_REG_R0))
        hook = c.uc.hook_add(UC_HOOK_CODE, trace)
        try:
            self.execute(c, ANALYZERS[1], budget=100_000)
        finally:
            c.uc.hook_del(hook)
        self.assertEqual(c.uc.reg_read(UC_ARM_REG_PRIMASK), mask)
        self.assertEqual(bytes(c.uc.mem_read(BUFFER, 128)), struct.pack('<64H', *samples))
        result = tuple(c.read(a, n) for a, n in ((GRADE,1),(RECENT,2),(ACTIVE,1),(BEEP,1),(GAP,1)))
        return result, observed

    def test_flat_dc_rejects_without_computing_unused_bins(self):
        result, measured = self.analyze(self.cpu(), [2048]*64, profile=True)
        self.assertEqual(result[0], 0)
        self.assertLess(measured['instructions'], 5000,
                        'flat DC must stop once target magnitude proves rejection')
        self.assertEqual(measured['bins'], [17])

    def test_parent_negative_control_spends_all_31_dfts_on_flat_dc(self):
        result, measured = self.analyze(self.cpu(self.previous), [2048]*64, profile=True)
        self.assertEqual(result[0], 0)
        self.assertEqual(measured['instructions'], 59886)
        self.assertEqual(measured['bins'], list(range(1, 32)))

    def test_patch_is_exactly_scoped_and_rejects_changed_parent_before_mutation(self):
        from lpm10rx.image import PatchError
        changed = [0x08006800+i for i,(a,b) in enumerate(zip(self.previous,self.data)) if a!=b]
        self.assertTrue(changed)
        self.assertTrue(all(analog_selective.START<=a<analog_selective.END for a in changed))
        self.assertEqual(len(self.previous), len(self.data))
        self.assertEqual(self.img.analog_selective['persistent_ram_bytes'], 0)
        self.assertEqual(self.img.analog_selective['additional_stack_bytes'], 0)
        with self.assertRaises(PatchError):
            analog_selective.install(self.img)
        with contextlib.redirect_stdout(io.StringIO()):
            img = digital_gain_continuity.build_candidate()
        img.data[img.f(analog_selective.START)] ^= 1
        before = bytes(img.data), list(img.log)
        with self.assertRaises(PatchError):
            analog_selective.install(img)
        self.assertEqual((bytes(img.data), img.log), before)

    def test_phase_amplitude_dc_noise_wrong_frequency_and_rails_are_bit_exact(self):
        cases = list(corpus())
        cases += [(f'weak_{a}_{phase}_{dc}', sine(a, phase=phase*math.pi/4, dc=dc))
                  for a in (0, 10, 11, 12, 14, 25, 300, 1800)
                  for phase in range(8) for dc in (100, 2048, 3900)]
        cases += [(f'off_frequency_{hz}_{phase}', sine(300, frequency=hz, phase=phase))
                  for hz in (50, 60, 700, 750, 780, 800, 825, 850, 875, 900, 1000, FS-TX_HZ)
                  for phase in (0, 1.1)]
        rng = random.Random(0x124A)
        cases += [(f'noise_{a}_{i}', [2048+rng.randint(-a,a) for _ in range(64)])
                  for a in (4, 12, 50, 400, 1600, 2047) for i in range(8)]
        cases += [('full_u16_dc', [65535]*64), ('full_u16_alternating', [0,65535]*32)]
        cases += [(f'full_u16_{i}', [rng.randrange(65536) for _ in range(64)]) for i in range(8)]
        old, new = self.cpu(self.previous), self.cpu()
        for number,(name,samples) in enumerate(cases):
            with self.subTest(name=name):
                before, original = self.analyze(old, samples, mask=number&1)
                after, optimized = self.analyze(new, samples, mask=number&1)
                self.assertEqual(after, before)
                self.assertEqual(optimized['scores'], original['scores'])
                if len(optimized['bins']) != 1:
                    self.assertEqual(optimized['bins'], [17]+[k for k in range(2,32) if k!=17])
        print('Analog selective exact ADC vectors:', len(cases))

    def test_instruction_and_stack_cost_decrease_without_changing_strength(self):
        measurements = []
        for name,samples in (('dc',[2048]*64), ('weak',sine(25)), ('normal',sine(300)),
                             ('mains',sine(300,frequency=50)), ('clipped',sine(8000))):
            before, original = self.analyze(self.cpu(self.previous), samples, profile=True)
            after, optimized = self.analyze(self.cpu(), samples, profile=True)
            self.assertEqual(after, before)
            self.assertLess(optimized['instructions'], original['instructions'])
            self.assertLessEqual(optimized['stack'], original['stack'])
            if len(optimized['bins']) == 1:
                self.assertLess(optimized['instructions'], original['instructions']*0.05)
            measurements.append((name, original['instructions'], optimized['instructions'], optimized['stack']))
        print('Analog selective instructions (case,parent,candidate,stack):', measurements)


import test_rx_analog_feedback_races as races


class AnalogSelectiveRaces(races.AnalogFeedbackRaces):
    @classmethod
    def setUpClass(cls):
        with contextlib.redirect_stdout(io.StringIO()):
            cls.img = digital_gain_continuity.build_candidate()
        cls.previous = bytes(cls.img.data)
        analog_selective.install(cls.img)
        cls.data = bytes(cls.img.data)

    def speaker(self, c):
        # PN1.14+ Analog dispatch is every16 IRQs; the historical race fixture
        # uses tick7 for the older every8-IRQ speaker schedule.
        c.w32(0x20000100, 15)
        self.execute(c, races.base.TIM5)

    def test_scheduler_key_interrupt_respects_all_critical_sections(self):
        helper = self.img.mode_tone['helper']
        ranges = races.SPEAKER_RANGES + ((helper, helper+self.img.mode_tone['helper_bytes']),)
        for uncertain in (False, True):
            def prepared():
                c = self.ready(uncertain=uncertain, initial_gap=0)
                self.execute(c, ANALYZERS[1])
                c.w32(0x20000100, 15)
                return c
            trace = self.instruction_trace(prepared(), races.base.TIM5, ranges)
            self.assertTrue(any(mask for _, mask in trace))
            for point, mask in trace:
                for kind in ('mode', 'mains', 'lamp'):
                    with self.subTest(uncertain=uncertain, point=hex(point), kind=kind):
                        c = prepared()
                        self.interrupt_at(c, races.base.TIM5, point,
                                          lambda cpu: self.key(cpu, kind), defer_if_masked=True)
                        self.assertEqual(c.read(BEEP), 100)

    def test_early_rejection_respects_keys_and_gate_publication(self):
        def prepared():
            c = self.analog_cpu()
            c.w8(ACTIVE, 0)
            c.uc.mem_write(BUFFER, struct.pack('<64H', *([2048]*64)))
            return c
        trace = self.instruction_trace(prepared(), ANALYZERS[1], races.ANALYZER_RANGES)
        points = [point for point, mask in trace if not mask]
        self.assertGreater(len(points), 10)
        for point in points:
            for kind in ('mode', 'mains', 'lamp'):
                with self.subTest(point=hex(point), kind=kind):
                    c = prepared()
                    self.interrupt_at(c, ANALYZERS[1], point, lambda cpu: self.key(cpu, kind))
                    self.assertEqual(c.read(BEEP), 100)
                    self.assertEqual(c.read(GRADE), 0)
                    self.speaker(c)
                    self.assertEqual(c.read(BEEP), 100)
            for reopen in (False, True):
                with self.subTest(point=hex(point), reopen=reopen):
                    c = prepared()
                    self.interrupt_at(c, ANALYZERS[1], point,
                                      lambda cpu: self.gate_pulse(cpu, reopen))
                    self.speaker(c)
                    self.assertEqual(c.read(BEEP), 0)
                    self.assertEqual(c.read(GRADE), 0)


if __name__ == '__main__':
    unittest.main()
