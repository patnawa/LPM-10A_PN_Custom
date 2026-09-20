"""Adversarial Analog publication/audio ownership tests on real ARM code.

DFT arithmetic is separately verified by test_rx_analog_feedback. Race sweeps
stub only the bin magnitude routine to keep exhaustive interrupt interleavings
cheap; publisher, real key scanner, gate helper, boundary, and speaker IRQ run.
Synthetic interrupt delivery respects PRIMASK and restores the interrupted CPU
context. This does not model NVIC priority or real-time interrupt deadlines.
"""
import struct
import unittest

from unicorn import UC_HOOK_CODE
from unicorn.arm_const import (
    UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_PRIMASK, UC_ARM_REG_R0,
    UC_ARM_REG_SP,
)

import analog_feedback
import test_rx_analog_feedback as base
from sampling_fixes import PUBLISH_GATE
from test_rx_followup import ANALYZERS, GATE_STATE, GRADE, KEY, REQUEST, SPEAKER
from verify_control import BEEP, MODE, SP, STOP
from verify_digital import ACTIVE, BUFFER, GAP, RECENT

DFT = 0x0800B4A0
DISPATCH = analog_feedback.SPEAKER_DISPATCH
ANALYZER_RANGES = (
    (analog_feedback.PUBLISH, analog_feedback.ANALYZER_END),
    (analog_feedback.GAP_HELPER, 0x0800A0A4),
)
SPEAKER_RANGES = ((SPEAKER, SPEAKER+0x4C), (0x080086EC, 0x0800870E),
                  (DISPATCH, analog_feedback.SPEAKER_END))


class AnalogFeedbackRaces(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.img = base.candidate()
        cls.data = bytes(cls.img.data)
        cls.previous = bytes(base.test_rx_robust.candidate().data)

    cpu = base.AnalogFeedback.cpu
    execute = base.AnalogFeedback.execute
    boundary = base.AnalogFeedback.boundary
    analog_cpu = base.AnalogFeedback.analog_cpu
    speaker = base.AnalogFeedback.speaker

    def ready(self, *, uncertain=False, initial_gap=160):
        c = self.analog_cpu()
        c.w8(ACTIVE, 0)
        c.w8(GAP, initial_gap)
        samples = [4095]*8+[1000]*56 if uncertain else base.sine(1800)
        c.uc.mem_write(BUFFER, struct.pack('<64H', *samples))
        def magnitude(uc, address, size, user):
            if address == DFT:
                uc.reg_write(UC_ARM_REG_R0,
                             1000 if uc.reg_read(UC_ARM_REG_R0) == 17 else 0)
                uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
        c.uc.hook_add(UC_HOOK_CODE, magnitude, begin=DFT, end=DFT)
        return c

    def instruction_trace(self, c, entry, ranges):
        points = []
        def record(uc, address, size, user):
            if any(lo <= address < hi for lo, hi in ranges):
                point = address, uc.reg_read(UC_ARM_REG_PRIMASK)
                if point not in points:
                    points.append(point)
        hook = c.uc.hook_add(UC_HOOK_CODE, record)
        try:
            self.execute(c, entry)
        finally:
            c.uc.hook_del(hook)
        return points

    def interrupt_at(self, c, entry, point, event, *, defer_if_masked=False):
        pending = False
        delivered_at = []
        def pause(uc, address, size, user):
            nonlocal pending
            if address == point:
                pending = True
            if pending and not uc.reg_read(UC_ARM_REG_PRIMASK):
                delivered_at.append(address)
                uc.emu_stop()
            elif pending and not defer_if_masked:
                self.fail(f'invalid masked interrupt injection at {address:#x}')
        hook = c.uc.hook_add(UC_HOOK_CODE, pause)
        c.uc.reg_write(UC_ARM_REG_SP, SP)
        c.uc.reg_write(UC_ARM_REG_LR, STOP | 1)
        try:
            c.uc.emu_start(entry | 1, STOP, count=100_000)
        finally:
            c.uc.hook_del(hook)
        self.assertEqual(len(delivered_at), 1, (hex(point), delivered_at))
        pc = delivered_at[0]
        self.assertEqual(c.uc.reg_read(UC_ARM_REG_PC), pc)
        self.assertEqual(c.uc.reg_read(UC_ARM_REG_PRIMASK), 0)
        context = c.uc.context_save()
        event(c)
        c.uc.context_restore(context)
        c.uc.emu_start(pc | 1, STOP, count=100_000)
        self.assertEqual(c.uc.reg_read(UC_ARM_REG_PC), STOP)
        self.assertEqual(c.uc.reg_read(UC_ARM_REG_SP), SP)
        self.assertEqual(c.uc.reg_read(UC_ARM_REG_PRIMASK), 0)

    def key(self, c, kind):
        # Accepted physical release after six scans, using the real scanner.
        held = {'mode': 0x2000010E, 'mains': 0x20000110,
                'lamp': 0x20000112}[kind]
        c.w16(held, 6)
        self.execute(c, KEY, stack=SP-0x500)
        self.assertEqual(c.read(BEEP), 100)

    def gate_pulse(self, c, reopen):
        self.execute(c, PUBLISH_GATE, 0, stack=SP-0x500)
        if reopen:
            self.execute(c, PUBLISH_GATE, 580, stack=SP-0x500)
        self.assertEqual(c.read(GATE_STATE), 0)

    def test_real_mode_and_mains_key_at_every_unmasked_publication_instruction(self):
        for uncertain in (False, True):
            trace = self.instruction_trace(self.ready(uncertain=uncertain),
                                           ANALYZERS[1], ANALYZER_RANGES)
            points = [p for p, mask in trace if not mask]
            self.assertGreater(len(points), 30)
            for kind, target in (('mode', 0), ('mains', 2)):
                for point in points:
                    with self.subTest(uncertain=uncertain, kind=kind, point=hex(point)):
                        c = self.ready(uncertain=uncertain)
                        self.interrupt_at(c, ANALYZERS[1], point,
                                          lambda cpu: self.key(cpu, kind))
                        self.assertEqual((c.read(MODE), c.read(REQUEST), c.read(BEEP)),
                                         (1, target+1, 100))
                        self.speaker(c)
                        self.assertEqual(c.read(BEEP), 100)
                        self.boundary(c)
                        self.assertEqual((c.read(MODE), c.read(REQUEST), c.read(GRADE),
                                          c.read(RECENT, 2), c.read(GAP), c.read(BEEP)),
                                         (target, 0, 0, 0, 0, 100))

    def test_gate_close_and_reopen_at_every_unmasked_publication_instruction(self):
        for uncertain in (False, True):
            trace = self.instruction_trace(self.ready(uncertain=uncertain),
                                           ANALYZERS[1], ANALYZER_RANGES)
            for reopen in (False, True):
                for point, mask in trace:
                    if mask:
                        continue
                    with self.subTest(uncertain=uncertain, reopen=reopen, point=hex(point)):
                        c = self.ready(uncertain=uncertain, initial_gap=0)
                        self.interrupt_at(c, ANALYZERS[1], point,
                                          lambda cpu: self.gate_pulse(cpu, reopen))
                        self.speaker(c)
                        self.assertEqual(c.read(BEEP), 0, 'stale gate must not start audio')
                        self.boundary(c)
                        self.assertEqual((c.read(GRADE), c.read(RECENT, 2), c.read(GAP)),
                                         (0, 0, 0))
                        self.assertEqual((c.read(ACTIVE), c.read(GATE_STATE)),
                                         (1, 2) if reopen else (2, 1))

    def test_lamp_confirmation_survives_every_publish_and_refresh_boundary(self):
        for uncertain in (False, True):
            trace = self.instruction_trace(self.ready(uncertain=uncertain),
                                           ANALYZERS[1], ANALYZER_RANGES)
            for point, mask in trace:
                with self.subTest(uncertain=uncertain, point=hex(point), mask=mask):
                    c = self.ready(uncertain=uncertain)
                    self.interrupt_at(c, ANALYZERS[1], point,
                                      lambda cpu: self.key(cpu, 'lamp'),
                                      defer_if_masked=True)
                    self.assertEqual((c.read(REQUEST), c.read(BEEP), c.read(RECENT, 2)),
                                     (0, 100, 600))
                    self.assertGreater(c.read(GRADE), 0)
                    self.speaker(c)
                    self.assertEqual(c.read(BEEP), 100)
                    c.run()
                    self.speaker(c)
                    self.assertEqual(c.read(BEEP), 99)

    def test_scheduler_key_interrupt_respects_all_critical_sections(self):
        for uncertain in (False, True):
            def prepared():
                c = self.ready(uncertain=uncertain, initial_gap=0)
                self.execute(c, ANALYZERS[1])
                c.w32(0x20000100, 7)
                return c
            trace = self.instruction_trace(prepared(), base.TIM5, SPEAKER_RANGES)
            self.assertTrue(any(mask for _, mask in trace))
            for point, mask in trace:
                for kind in ('mode', 'mains', 'lamp'):
                    with self.subTest(uncertain=uncertain, point=hex(point), kind=kind):
                        c = prepared()
                        self.interrupt_at(c, base.TIM5, point,
                                          lambda cpu: self.key(cpu, kind),
                                          defer_if_masked=True)
                        self.assertEqual(c.read(BEEP), 100)

    def test_actual_lamp_key_beep_lasts_full_duration_with_repeated_analog_windows(self):
        for uncertain in (False, True):
            c = self.ready(uncertain=uncertain, initial_gap=0)
            self.key(c, 'lamp')
            for tick in range(100):
                if tick % 21 == 0:
                    c.w8(ACTIVE, 0)
                    self.execute(c, ANALYZERS[1])
                self.speaker(c)
                self.assertEqual(c.read(BEEP), 100-tick)
                c.run()
            self.assertEqual(c.read(BEEP), 0)

    def test_mains_dispatch_matches_parent_across_feedback_and_request_matrix(self):
        for beep in (0, 1, 30, 50, 100, 200):
            for gap in (0, 1, 50, 200):
                for grade in (0, 1, 20, 160):
                    for request in (0, 1, 2, 3):
                        results = []
                        for data in (self.previous, self.data):
                            c = self.cpu(data)
                            c.w8(MODE, 2)
                            c.w8(BEEP, beep)
                            c.w8(GAP, gap)
                            c.w8(GRADE, grade)
                            c.w8(REQUEST, request)
                            c.w16(RECENT, 800)
                            self.speaker(c)
                            results.append((bytes(c.uc.mem_read(0x20000000, 0x120)),
                                            dict(c.gpio), list(c.calls)))
                        self.assertEqual(*results, (beep, gap, grade, request))


if __name__ == '__main__':
    unittest.main()
