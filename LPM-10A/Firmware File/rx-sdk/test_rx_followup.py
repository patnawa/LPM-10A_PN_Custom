"""PN 1.6 instruction-level regressions; ADC/GPIO and interrupt timing modeled.

These execute the candidate ARM instructions, not a replacement detector or
scheduler. They establish sample ownership and logical countdown behavior, not
analogue sensitivity, interrupt deadlines, or measured audio timing.
"""
import math
from pathlib import Path
import random
import struct
import unittest

from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm_const import *

import audit_fixes
import rx_patches
import test_roadmap
from verify_control import Control, STOP, SP, SAVED, MODE, BEEP, IDLE, TICK
from verify_digital import ACTIVE, BUFFER, GATE, GAP, RECENT, pattern, reference, sampled_wave

GRADE = 0x2000005D
REQUEST, GATE_STATE = 0x20000049, 0x200000EF
INDICES = (0x2000005B, 0x2000005C, 0x20000108)
ANALYZERS = (0x08009E08, 0x08009F58, 0x080085F4)
KEY, TIM5, SPEAKER = 0x080082B8, 0x0800AC1C, 0x08007724


def candidate():
    import followup_fixes
    img = test_roadmap.candidate()
    for patch in rx_patches.REGISTRY:
        if patch.pid in audit_fixes.PATCHES:
            patch(img)
    followup_fixes.apply(img)
    return img


class Followup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.img = candidate()
        cls.data = bytes(cls.img.data)

    def cpu(self, data=None):
        c = Control(self.data if data is None else data)
        c.uc.reg_write(UC_ARM_REG_C1_C0_2, 0xF00000)
        c.uc.reg_write(UC_ARM_REG_FPEXC, 0x40000000)
        c.w16(GATE, 2)
        c.w16(GATE + 2, 1)
        c.w8(GATE_STATE, 2)
        return c

    def execute(self, c, entry, *args, stack=SP, budget=4_000_000):
        for reg, value in zip((UC_ARM_REG_R0, UC_ARM_REG_R1), args):
            c.uc.reg_write(reg, value)
        values = [0xABCD0000 + n for n in range(len(SAVED))]
        for reg, value in zip(SAVED, values):
            c.uc.reg_write(reg, value)
        c.uc.reg_write(UC_ARM_REG_D8, 0x123456789ABCDEF0)
        c.uc.reg_write(UC_ARM_REG_SP, stack)
        c.uc.reg_write(UC_ARM_REG_LR, STOP | 1)
        c.uc.emu_start(entry | 1, STOP, count=budget)
        self.assertEqual(c.uc.reg_read(UC_ARM_REG_PC), STOP, "instruction budget exceeded")
        self.assertEqual(c.uc.reg_read(UC_ARM_REG_SP), stack)
        self.assertEqual([c.uc.reg_read(r) for r in SAVED], values)
        self.assertEqual(c.uc.reg_read(UC_ARM_REG_D8), 0x123456789ABCDEF0)
        return c.uc.reg_read(UC_ARM_REG_R0)

    def detect(self, c, samples, recent=0):
        c.uc.mem_write(BUFFER, struct.pack('<48H', *samples))
        c.w8(ACTIVE, 0)
        c.w16(RECENT, recent)
        self.execute(c, ANALYZERS[0], budget=12000)
        return c.read(RECENT, 2) == 800

    def boundary(self, c):
        """Execute the actual main-loop prefix, stopping before mode dispatch."""
        c.uc.reg_write(UC_ARM_REG_R5, MODE)
        c.uc.reg_write(UC_ARM_REG_SP, SP)
        c.uc.reg_write(UC_ARM_REG_LR, STOP | 1)
        c.uc.emu_start(0x0800B8F3, 0x0800B8FC, count=4000)
        self.assertEqual(c.uc.reg_read(UC_ARM_REG_PC), 0x0800B8FC)
        self.assertEqual(c.uc.reg_read(UC_ARM_REG_SP), SP)

    def acquire(self, c, values, complete=True):
        """Run real TIM5 sample-due interrupts; only ADC conversion is modeled."""
        mode = c.read(MODE)
        calls = []
        def adc(uc, addr, size, user):
            if addr == 0x080072A4:
                channel = uc.reg_read(UC_ARM_REG_R1)
                self.assertEqual(channel, 7 if mode == 2 else 1)
                index = c.read(INDICES[mode])
                calls.append((channel, index))
                uc.reg_write(UC_ARM_REG_R0, values[index])
                uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
        hook = c.uc.hook_add(UC_HOOK_CODE, adc)
        try:
            for _ in range(600):
                if not c.read(ACTIVE):
                    break
                if not complete and c.read(INDICES[mode]) == len(values)-1:
                    break
                c.w32(0x20000100, (19, 12, 61)[mode])
                self.execute(c, TIM5, budget=4000)
            else:
                self.fail('sampler failed to finish within 600 sample-due interrupts')
        finally:
            c.uc.hook_del(hook)
        return calls

    def test_all_directed_mode_changes_discard_partial_and_completed_windows(self):
        for before in range(3):
            for after in range(3):
                if before == after:
                    continue
                for active in (0, 1):
                    with self.subTest(before=before, after=after, active=active):
                        c = self.cpu()
                        c.w8(MODE, before)
                        c.w8(ACTIVE, active)
                        for address, index in zip(INDICES, (45, 60, 60)):
                            c.w8(address, index)
                        c.w8(0x200000EE, 9)
                        c.uc.mem_write(BUFFER, struct.pack('<64H', *([4095]*64)))
                        c.w16(RECENT, 800)
                        c.w8(GRADE, 30)
                        c.w8(GAP, 50)
                        c.w8(BEEP, 100)
                        c.w8(REQUEST, after+1)
                        self.boundary(c)
                        self.assertEqual(c.read(MODE), after)
                        self.assertEqual([c.read(x) for x in INDICES], [0, 0, 0])
                        self.assertEqual(c.read(0x200000EE), 0)
                        self.assertEqual((c.read(REQUEST), c.read(RECENT, 2), c.read(GAP), c.read(GRADE)), (0, 0, 0, 0))
                        self.assertEqual((c.read(ACTIVE), c.read(GATE_STATE)), (1, 2))
                        c.w8(BEEP, 0)  # separate detection from key confirmation
                        self.execute(c, ANALYZERS[after])
                        self.assertEqual(c.read(BEEP), 0)
                        length = 48 if after == 0 else 64
                        first = self.acquire(c, [0]*length, complete=False)
                        self.assertEqual(c.read(ACTIVE), 1)
                        self.execute(c, ANALYZERS[after])
                        self.assertEqual((c.read(BEEP), c.read(RECENT, 2)), (0, 0))
                        last = self.acquire(c, [0]*length)
                        self.assertEqual(len(first)+len(last), length*(5 if after == 0 else 1))
                        self.assertEqual(c.read(ACTIVE), 0)
                        self.assertEqual(bytes(c.uc.mem_read(BUFFER, length*2)), bytes(length*2))
                        self.execute(c, ANALYZERS[after])
                        self.assertEqual((c.read(BEEP), c.read(RECENT, 2)), (0, 0))

    def test_fresh_signal_reacquires_in_every_mode(self):
        for mode in range(3):
            c = self.cpu()
            c.w8(REQUEST, mode+1)
            self.boundary(c)
            c.w8(BEEP, 0)
            values = pattern() if mode == 0 else [round(2048+1800*math.cos(2*math.pi*(17 if mode == 1 else 5)*i/64)) for i in range(64)]
            calls = self.acquire(c, values)
            self.assertEqual(len(calls), 240 if mode == 0 else 64)
            self.execute(c, ANALYZERS[mode])
            if mode == 0:
                self.assertEqual(c.read(RECENT, 2), 800)
                self.execute(c, SPEAKER)
            self.assertGreater(c.read(BEEP), 0)

    def test_analog_and_mains_threshold_responses_match_previous_release(self):
        previous = (Path(__file__).resolve().parent.parent / audit_fixes.OUTPUT).read_bytes()
        for mode, bin_index in ((1, 17), (2, 5), (2, 6)):
            for amplitude in (0, 10, 11, 150, 151, 200, 201, 250, 251, 350, 351, 600, 601, 1800):
                values = [round(2048+amplitude*math.cos(2*math.pi*bin_index*i/64)) for i in range(64)]
                answers = []
                for data in (previous, self.data):
                    c = self.cpu(data)
                    c.w8(MODE, mode)
                    c.uc.mem_write(BUFFER, struct.pack('<64H', *values))
                    self.execute(c, ANALYZERS[mode])
                    answers.append((c.read(BEEP), c.read(GAP), c.read(ACTIVE)))
                self.assertEqual(answers[0], answers[1], (mode, bin_index, amplitude))

    def test_mains_publishes_rearm_after_clear_and_first_tim5_sample_survives(self):
        c = self.cpu()
        c.w8(MODE, 2)
        c.uc.mem_write(BUFFER, bytes([0xAA])*128)
        armed = []
        def memory(uc, access, addr, size, value, user):
            if addr == ACTIVE and value == 1:
                armed.append(True)
        def pause(uc, addr, size, user):
            if armed:
                uc.emu_stop()
            elif addr == 0x0800B4A0:
                uc.reg_write(UC_ARM_REG_R0, 500)
                uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
        write_hook = c.uc.hook_add(UC_HOOK_MEM_WRITE, memory)
        code_hook = c.uc.hook_add(UC_HOOK_CODE, pause)
        c.uc.reg_write(UC_ARM_REG_SP, SP)
        c.uc.reg_write(UC_ARM_REG_LR, STOP | 1)
        c.uc.emu_start(ANALYZERS[2] | 1, STOP, count=4000)
        self.assertTrue(armed)
        self.assertEqual(bytes(c.uc.mem_read(BUFFER, 128)), bytes(128))
        context, resume = c.uc.context_save(), c.uc.reg_read(UC_ARM_REG_PC)
        c.uc.hook_del(code_hook)
        c.uc.hook_del(write_hook)
        def adc(uc, addr, size, user):
            if addr == 0x080072A4:
                self.assertEqual(uc.reg_read(UC_ARM_REG_R1), 7)
                uc.reg_write(UC_ARM_REG_R0, 1234)
                uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
        adc_hook = c.uc.hook_add(UC_HOOK_CODE, adc)
        c.w32(0x20000100, 61)
        self.execute(c, TIM5, stack=SP-0x400)
        c.uc.hook_del(adc_hook)
        self.assertEqual((c.read(BUFFER, 2), c.read(INDICES[2])), (1234, 1))
        c.uc.context_restore(context)
        c.uc.emu_start(resume | 1, STOP, count=4000)
        self.assertEqual(c.uc.reg_read(UC_ARM_REG_PC), STOP)
        self.assertEqual((c.read(BUFFER, 2), c.read(INDICES[2])), (1234, 1))
        self.assertEqual(bytes(c.uc.mem_read(BUFFER+2, 126)), bytes(126))

    def test_digital_and_analog_gate_reopening_requires_complete_fresh_window(self):
        for mode in (0, 1):
            for active in (0, 1):
                c = self.cpu()
                c.w8(MODE, mode)
                c.w8(ACTIVE, active)
                c.w8(INDICES[mode], 30)
                values = pattern() if mode == 0 else [round(2048+1800*math.cos(2*math.pi*17*i/64)) for i in range(64)]
                c.uc.mem_write(BUFFER, struct.pack('<'+'H'*len(values), *values))
                c.w16(GATE+2*mode, 0)
                self.boundary(c)
                self.assertNotEqual(c.read(ACTIVE), 1)
                for _ in range(3):
                    self.execute(c, ANALYZERS[mode])
                    c.w32(0x20000100, (19, 12)[mode])
                    self.execute(c, TIM5)
                self.assertEqual((c.read(BEEP), c.read(RECENT, 2)), (0, 0))
                c.w16(GATE+2*mode, 2 if mode == 0 else 1)
                self.boundary(c)
                self.assertEqual((c.read(ACTIVE), c.read(INDICES[mode])), (1, 0))
                self.execute(c, ANALYZERS[mode])
                self.assertEqual((c.read(BEEP), c.read(RECENT, 2)), (0, 0))
                self.acquire(c, [0]*len(values), complete=False)
                self.execute(c, ANALYZERS[mode])
                self.assertEqual((c.read(BEEP), c.read(RECENT, 2)), (0, 0))
                self.acquire(c, [0]*len(values))
                self.execute(c, ANALYZERS[mode])
                self.assertEqual((c.read(BEEP), c.read(RECENT, 2)), (0, 0))
                self.acquire(c, values)
                self.execute(c, ANALYZERS[mode])
                self.assertEqual(c.read(RECENT, 2), 800 if mode == 0 else 0)
                if mode == 0:
                    self.execute(c, SPEAKER)
                self.assertGreater(c.read(BEEP), 0)

    def test_key_request_during_analysis_rejects_old_result_and_keeps_confirmation(self):
        for mode, target in ((a, b) for a in range(3) for b in range(3) if a != b):
            c = self.cpu()
            c.w8(MODE, mode)
            values = pattern() if mode == 0 else [round(2048+1800*math.cos(2*math.pi*(17 if mode == 1 else 5)*i/64)) for i in range(64)]
            c.uc.mem_write(BUFFER, struct.pack('<'+'H'*len(values), *values))
            pause = 0x0800B630 if mode == 0 else 0x0800B4A0
            def stop(uc, addr, size, user):
                if addr == pause:
                    uc.emu_stop()
            hook = c.uc.hook_add(UC_HOOK_CODE, stop)
            c.uc.reg_write(UC_ARM_REG_SP, SP)
            c.uc.reg_write(UC_ARM_REG_LR, STOP | 1)
            c.uc.emu_start(ANALYZERS[mode] | 1, STOP, count=12000)
            c.uc.hook_del(hook)
            self.assertEqual(c.uc.reg_read(UC_ARM_REG_PC), pause)
            self.assertEqual(c.uc.reg_read(UC_ARM_REG_PRIMASK), 0, 'analysis must permit interrupts')
            context = c.uc.context_save()
            c.w16(0x20000110 if target == 2 else 0x2000010E, 6)
            self.execute(c, KEY, stack=SP-0x400)
            if mode == 2 and target == 1:
                # A second mode release toggles the already queued digital
                # request; no analysis boundary ran between the two keys.
                c.w16(0x2000010E, 6)
                self.execute(c, KEY, stack=SP-0x400)
            self.assertEqual(c.read(REQUEST), target+1)
            self.assertEqual((c.read(MODE), c.read(BEEP)), (mode, 100))
            c.uc.context_restore(context)
            c.uc.emu_start(pause | 1, STOP, count=4_000_000)
            self.assertEqual(c.uc.reg_read(UC_ARM_REG_PC), STOP)
            self.assertEqual((c.read(BEEP), c.read(RECENT, 2), c.read(GRADE)), (100, 0, 0))
            self.boundary(c)
            self.assertEqual((c.read(MODE), c.read(ACTIVE)), (target, 1))

    def test_gate_close_open_pulse_remains_latched_until_fresh_acquisition(self):
        from sampling_fixes import PUBLISH_GATE
        for mode in (0, 1):
            for mask in (0, 1):
                c = self.cpu()
                c.w8(MODE, mode)
                c.w16(GATE, 1000)
                c.w16(GATE+2, 1)
                c.uc.mem_write(BUFFER, struct.pack('<48H', *pattern()))
                c.w8(INDICES[mode], 32)
                c.uc.reg_write(UC_ARM_REG_PRIMASK, mask)
                self.execute(c, PUBLISH_GATE, 0)
                self.assertEqual(c.read(GATE_STATE), 0)
                self.assertEqual(c.uc.reg_read(UC_ARM_REG_PRIMASK), mask)
                self.execute(c, PUBLISH_GATE, 1000)
                self.assertEqual(c.read(GATE_STATE), 0, 'reopening must retain intervening close')
                self.assertEqual(c.uc.reg_read(UC_ARM_REG_PRIMASK), mask)
                self.execute(c, ANALYZERS[mode])
                self.assertEqual((c.read(BEEP), c.read(RECENT, 2)), (0, 0))
                self.boundary(c)
                self.assertEqual(c.uc.reg_read(UC_ARM_REG_PRIMASK), mask)
                self.assertEqual((c.read(INDICES[mode]), c.read(ACTIVE), c.read(GATE_STATE)), (0, 1, 2))

    def test_gate_publisher_threshold_matrix_and_gain_result(self):
        from sampling_fixes import PUBLISH_GATE
        for mode in range(3):
            for raw in (0, 1, 2, 579, 580, 581, 4095):
                for previous in (0, 1, 2, 579, 580, 4095):
                    c = self.cpu()
                    c.w8(MODE, mode)
                    c.w16(GATE, previous)
                    c.w16(GATE+2, previous//580)
                    gain = self.execute(c, PUBLISH_GATE, raw)
                    threshold = (2, 580, 0)[mode]
                    crossed = (previous >= threshold) != (raw >= threshold)
                    self.assertEqual(c.read(GATE_STATE), 0 if crossed else 2, (mode, previous, raw))
                    self.assertEqual((c.read(GATE, 2), c.read(GATE+2, 2), gain), (raw, raw//580, raw//580))

    def test_mode_boundary_restores_mask_and_preserves_active_confirmation(self):
        from sampling_fixes import BOUNDARY
        for mode in range(3):
            for target in range(3):
                for mask in (0, 1):
                    c = self.cpu()
                    c.w8(MODE, mode)
                    c.w8(REQUEST, target+1)
                    c.w16(GATE, 580)
                    c.w8(BEEP, 77)
                    for address in (*INDICES, 0x200000EE):
                        c.w8(address, 47)
                    c.uc.reg_write(UC_ARM_REG_PRIMASK, mask)
                    self.execute(c, BOUNDARY)
                    self.assertEqual(c.uc.reg_read(UC_ARM_REG_PRIMASK), mask)
                    self.assertEqual((c.read(MODE), c.read(REQUEST), c.read(ACTIVE), c.read(GATE_STATE), c.read(BEEP)), (target, 0, 1, 2, 77))
                    self.assertEqual([c.read(x) for x in (*INDICES, 0x200000EE)], [0]*4)

    def test_key_led_and_battery_shadow_match_previous_release(self):
        previous = (Path(__file__).resolve().parent.parent / audit_fixes.OUTPUT).read_bytes()
        held_cases = ((0, 0, 0), (6, 0, 0), (0, 6, 0), (0, 0, 6),
                      (6, 6, 6), (5, 5, 5), (65535, 65535, 65535))
        for mode in range(3):
            for battery_shadow in range(3):
                for held in held_cases:
                    old, new = self.cpu(previous), self.cpu()
                    for c in (old, new):
                        c.w8(MODE, mode)
                        c.w8(0x20000054, battery_shadow)
                        for address, value in zip((0x2000010E, 0x20000110, 0x20000112), held):
                            c.w16(address, value)
                        self.execute(c, KEY)
                    effective = new.read(REQUEST)-1 if new.read(REQUEST) else new.read(MODE)
                    self.assertEqual((effective, new.gpio, new.read(BEEP)),
                                     (old.read(MODE), old.gpio, old.read(BEEP)), (mode, battery_shadow, held))

    def test_startup_discards_unowned_samples_before_first_analysis(self):
        for mode in range(3):
            c = self.cpu()
            c.w8(MODE, mode)
            c.w8(GATE_STATE, 0)
            c.w8(ACTIVE, 0)
            c.uc.mem_write(BUFFER, struct.pack('<64H', *([4095]*64)))
            self.boundary(c)
            self.assertEqual((c.read(ACTIVE), c.read(GATE_STATE)), (1, 2))
            self.execute(c, ANALYZERS[mode])
            self.assertEqual((c.read(BEEP), c.read(RECENT, 2)), (0, 0))

    def test_actual_startup_mode_switch_with_stale_analog_samples_and_timer_preemption(self):
        for gate in (0, 2):
            for request in (0, 2, 3):
                for preempt in (False, True):
                    c = self.cpu()
                    c.w8(GATE_STATE, 0)
                    c.w16(GATE, gate)
                    c.uc.reg_write(UC_ARM_REG_R4, 0)
                    c.uc.reg_write(UC_ARM_REG_SP, SP)
                    def startup(uc, addr, size, user):
                        if addr in (0x0800A958, 0x0800AD98):
                            uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
                        elif addr == 0x0800B9A0:
                            self.assertEqual(c.read(MODE), 1)
                            c.uc.mem_write(BUFFER, struct.pack('<64H', *([4095]*64)))
                            c.w8(ACTIVE, 0)
                            for address, index in zip(INDICES, (45, 60, 60)):
                                c.w8(address, index)
                            c.w8(0x200000EE, 9)
                            c.w8(REQUEST, request)
                            c.w8(BEEP, 73)
                            c.w8(GAP, 30)
                            c.w8(GRADE, 30)
                            c.w16(RECENT, 800)
                            uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
                    hook = c.uc.hook_add(UC_HOOK_CODE, startup)
                    c.uc.emu_start(0x0800B8D3, 0x0800B8F0, count=4000)
                    c.uc.hook_del(hook)
                    self.assertEqual(c.uc.reg_read(UC_ARM_REG_PC), 0x0800B8F0)
                    self.assertEqual(c.read(MODE), 0)
                    if preempt:
                        context = c.uc.context_save()
                        c.w8(ACTIVE, 1)
                        c.w32(0x20000100, 0)
                        self.execute(c, TIM5, stack=SP-0x400)
                        c.uc.context_restore(context)
                    c.uc.emu_start(0x0800B8F1, 0x0800B8FC, count=4000)
                    self.assertEqual(c.uc.reg_read(UC_ARM_REG_PC), 0x0800B8FC)
                    target = request-1 if request else 0
                    self.assertEqual(c.read(MODE), target)
                    self.assertEqual([c.read(x) for x in (*INDICES, 0x200000EE, REQUEST, GAP, GRADE)], [0]*7)
                    self.assertEqual((c.read(BEEP), c.read(RECENT, 2)), (73, 0))
                    self.assertEqual((c.read(ACTIVE), c.read(GATE_STATE)), (2, 1) if not target and not gate else (1, 2))

    def test_timer_housekeeping_main_watchdog_and_physical_power_key(self):
        c = self.cpu()
        for _ in range(1000):
            c.run()
        self.assertEqual(c.calls.count(0x08008224), 0)
        self.assertEqual(c.calls.count(0x08007770), 2)
        self.assertEqual(c.calls.count(0x080084D8), 2)
        self.assertEqual(c.calls.count(0x0800ADC0), 1000)
        self.assertEqual(c.read(TICK, 4), 1000)
        self.boundary(c)
        self.assertEqual(c.calls.count(0x08008224), 1)
        c = self.cpu()
        c.pressed = {(0x40011000, 0x2000)}
        c.w16(RECENT, 2000)
        for _ in range(1199):
            c.run()
        self.assertNotIn(0x08007570, c.calls)
        c.run()
        self.assertEqual(c.calls.count(0x08007570), 1)

    def test_key_debounce_release_and_mode_sequence(self):
        for label, pin in (('mode', (0x40011000, 0x8000)), ('mains', (0x40011400, 0x8000)), ('lamp', (0x40011400, 0x4000))):
            for scans in (0, 1, 5, 6, 100):
                c = self.cpu()
                c.pressed = {pin}
                for _ in range(scans):
                    c.run(KEY)
                self.assertEqual((c.read(MODE), c.read(REQUEST), c.read(BEEP)), (0, 0, 0))
                c.pressed.clear()
                c.run(KEY)
                accepted = scans >= 6
                self.assertEqual(c.read(BEEP), 100 if accepted else 0)
                self.boundary(c)
                if label == 'lamp':
                    self.assertEqual(c.gpio.get((0x40010800, 0x400), 0), int(accepted))
                else:
                    self.assertEqual(c.read(MODE), (1 if label == 'mode' else 2) if accepted else 0)
                before = c.read(MODE), dict(c.gpio)
                c.run(KEY)
                self.boundary(c)
                self.assertEqual((c.read(MODE), c.gpio), before)

    def test_image_matches_rebuild_and_retains_vectors_binding_and_size(self):
        path = Path(__file__).resolve().parent.parent / 'experimental/APP_LPM-10RX_PN1.6-followup.bin'
        self.assertEqual(path.read_bytes(), self.data)
        self.assertEqual(len(self.data), len(self.img.original))
        rebuilt = bytearray(self.img.original)
        for addr, old, new, why, kind in self.img.log:
            offset = addr - 0x08006800
            self.assertEqual(bytes(rebuilt[offset:offset + len(old)]), old, why)
            rebuilt[offset:offset + len(new)] = new
        self.assertEqual(bytes(rebuilt), self.data)
        for start, end in ((0x08006800, 0x08006948), (0x0800B388, 0x0800B484),
                           (0x0800BAE8, 0x0800BBB0)):
            self.assertEqual(self.data[start-0x08006800:end-0x08006800],
                             self.img.original[start-0x08006800:end-0x08006800])

    def test_prior_battery_adc_dft_and_timer_fixes_are_byte_exact(self):
        previous = (Path(__file__).resolve().parent.parent / audit_fixes.OUTPUT).read_bytes()
        for label, start, end in (
                ('serialized ADC transaction', 0x080072A4, 0x080072E8),
                ('critical battery recovery', 0x08007770, 0x080078B0),
                ('TIM1 countdowns and power handling', 0x0800A97C, 0x0800AC1C),
                ('DFT overflow correction', 0x0800B4A0, 0x0800B630)):
            self.assertEqual(self.data[start-0x08006800:end-0x08006800],
                             previous[start-0x08006800:end-0x08006800], label)

    def test_digital_phase_error_noise_and_strength_reference(self):
        c = self.cpu()
        cases = [pattern(p, lo, hi) for p in range(8)
                 for lo, hi in ((0, 1000), (500, 1500), (3000, 3100), (0, 4095))]
        cases += [pattern(p, wrong=(i,)) for p in range(8) for i in range(48)]
        cases += [pattern(p, wrong=w) for p in range(8) for w in
                  ((8, 24, 40), (0, 1, 16, 32), (0, 1, 2),
                   (0, 1, 16, 17, 32), (0, 1, 16, 17, 32, 33))]
        cases += [pattern(p, 2000, 2000+d) for p in range(8) for d in (0, 1, 4, 8, 9, 10, 16)]
        cases += [[1500 if code >> (7-i % 8) & 1 else 500 for i in range(48)] for code in range(256)]
        cases += [[level] * 48 for level in (0, 1, 1000, 2048, 4095)]
        cases += [[500+i*50 for i in range(48)], [3000-i*50 for i in range(48)]]
        cases += [[1500 if i == spike else 500 for i in range(48)] for spike in range(48)]
        cases += [pattern()[:16] + [500] * 32]
        cases += [[round(2000+1000*math.sin(2*math.pi*(hz*i*0.005003125+p/16))) for i in range(48)]
                  for hz in (10, 25, 50, 60, 100, 200, 825) for p in range(16)]
        rng = random.Random(0xB6B6)
        cases += [[rng.randrange(4096) for _ in range(48)] for _ in range(1024)]
        cases += [[500+1000*rng.randrange(2) for _ in range(48)] for _ in range(1024)]
        cases += [sampled_wave(p/8, ratio, noise, rng)
                  for ratio in (0.98, 0.990718, 1, 1.01, 1.02)
                  for p in range(64) for noise in (0, 100)]
        for number, samples in enumerate(cases):
            c.w8(BEEP, 17)
            c.w8(GAP, 23)
            hit = self.detect(c, samples, recent=321)
            self.assertEqual(hit, reference(samples), number)
            self.assertEqual(c.read(RECENT, 2), 800 if hit else 321, number)
            self.assertEqual((c.read(BEEP), c.read(GAP)), (17, 23), number)
            self.assertEqual(c.read(ACTIVE), 1, number)
            if hit:
                mean = (sum(samples)-min(samples)-max(samples)) // 46
                contrast = sum(abs(x-mean) for x in samples)
                expected = 100 if contrast < 500 else 50 if contrast <= 1000 else 30
                self.assertEqual(c.read(GRADE), expected, number)

    def test_snapshot_survives_sampler_overwrite_and_preserves_output_ownership(self):
        c = self.cpu()
        writes = []
        def memory(uc, access, addr, size, value, user):
            writes.append((addr, size))
            if addr == ACTIVE and value == 1:
                uc.mem_write(BUFFER, bytes(128))
        hook = c.uc.hook_add(UC_HOOK_MEM_WRITE, memory)
        self.assertTrue(self.detect(c, pattern()))
        c.uc.hook_del(hook)
        allowed = {(ACTIVE, 1), (RECENT, 2), (GRADE, 1)}
        self.assertTrue(all(SP-144 <= addr and addr+size <= SP or (addr, size) in allowed
                            for addr, size in writes), writes)
        self.assertEqual((c.read(BEEP), c.read(GAP)), (0, 0))

    def cadence(self, delta, arrival_phase, duration=2400):
        c = self.cpu()
        samples = pattern(low=500, high=500+delta)
        self.assertTrue(self.detect(c, samples))
        self.execute(c, SPEAKER)
        starts, widths, active_start = [0], [], 0
        for tick in range(1, duration+1):
            before = c.read(BEEP)
            c.run()
            if (tick-arrival_phase) % 240 == 0:
                pair = c.read(BEEP), c.read(GAP)
                self.assertTrue(self.detect(c, samples, recent=c.read(RECENT, 2)))
                self.assertEqual((c.read(BEEP), c.read(GAP)), pair)
            self.execute(c, SPEAKER)
            after = c.read(BEEP)
            if before and not after:
                widths.append(tick-active_start)
            if not before and after:
                starts.append(tick)
                active_start = tick
        return starts, widths

    def test_sustained_detection_keeps_cadence_at_different_arrival_phases(self):
        for delta, on, off in ((9, 50, 100), (25, 50, 50), (60, 30, 30)):
            for phase in (0, 1, 17, 29, 49, 99, 239):
                with self.subTest(delta=delta, phase=phase):
                    starts, widths = self.cadence(delta, phase)
                    self.assertEqual(starts, list(range(0, 2401, on+off-1)))
                    self.assertTrue(widths and all(width == on for width in widths), widths)

    def test_grade_changes_take_effect_on_next_beep_only(self):
        for old_delta, old_gap in ((9, 100), (25, 50), (60, 30)):
            for delta, gap in ((9, 100), (25, 50), (60, 30)):
                for elapsed in (1, 20, min(old_gap, 50)+5):
                    c = self.cpu()
                    self.detect(c, pattern(low=500, high=500+old_delta))
                    self.execute(c, SPEAKER)
                    for _ in range(elapsed):
                        c.run()
                        self.execute(c, SPEAKER)
                    pair = c.read(BEEP), c.read(GAP)
                    self.detect(c, pattern(low=500, high=500+delta), recent=c.read(RECENT, 2))
                    self.assertEqual((c.read(BEEP), c.read(GAP)), pair)
                    for _ in range(min(old_gap, 50)+old_gap-1-elapsed):
                        c.run()
                        self.execute(c, SPEAKER)
                    self.assertEqual((c.read(BEEP), c.read(GAP)), (min(gap, 50), gap))

    def test_signal_loss_expiry_and_reacquisition(self):
        for delta, gap in ((9, 100), (25, 50), (60, 30)):
            c = self.cpu()
            self.detect(c, pattern(low=500, high=500+delta))
            self.execute(c, SPEAKER)
            for _ in range(1000):
                c.run()
                self.execute(c, SPEAKER)
            self.assertEqual((c.read(BEEP), c.read(GAP), c.read(RECENT, 2)), (0, 0, 0))
            self.assertFalse(self.detect(c, [500]*48))
            self.execute(c, SPEAKER)
            self.assertEqual(c.read(BEEP), 0)
            self.assertTrue(self.detect(c, pattern(low=500, high=500+delta)))
            self.execute(c, SPEAKER)
            self.assertEqual((c.read(BEEP), c.read(GAP)), (min(gap, 50), gap))

    def test_key_confirmation_is_not_shortened_by_detection_or_scheduler(self):
        for delta in (9, 25, 60):
            c = self.cpu()
            c.w16(0x20000112, 6)  # accepted physical lamp-key release
            c.run(KEY)
            self.assertEqual(c.read(BEEP), 100)
            for tick in range(1, 100):
                c.run()
                self.detect(c, pattern(low=500, high=500+delta), recent=c.read(RECENT, 2))
                self.execute(c, SPEAKER)
                self.assertEqual(c.read(BEEP), 100-tick)

    def test_scheduler_restores_interrupt_mask_and_honors_both_countdowns(self):
        for mask in (0, 1):
            for beep, gap in ((0, 0), (1, 0), (0, 1), (50, 30), (100, 0)):
                c = self.cpu()
                c.w16(RECENT, 800)
                c.w8(GRADE, 30)
                c.w8(BEEP, beep)
                c.w8(GAP, gap)
                c.uc.reg_write(UC_ARM_REG_PRIMASK, mask)
                self.execute(c, SPEAKER)
                self.assertEqual(c.uc.reg_read(UC_ARM_REG_PRIMASK), mask)
                self.assertEqual((c.read(BEEP), c.read(GAP)), (30, 30) if not beep and not gap else (beep, gap))

    def test_pending_mode_and_gate_changes_suppress_new_digital_beeps(self):
        for request, gate_state in ((1, 2), (2, 2), (3, 2), (0, 0), (0, 1)):
            c = self.cpu()
            c.w8(REQUEST, request)
            c.w8(GATE_STATE, gate_state)
            c.w16(RECENT, 800)
            c.w8(GRADE, 30)
            self.execute(c, SPEAKER)
            self.assertEqual((c.read(BEEP), c.read(GAP)), (0, 0))
            c.w8(BEEP, 100)
            self.execute(c, SPEAKER)
            self.assertEqual(c.read(BEEP), 100)

    def test_key_interrupt_at_each_unmasked_scheduler_instruction_preserves_confirmation(self):
        c = self.cpu()
        c.w16(RECENT, 800)
        c.w8(GRADE, 30)
        points = []
        def trace(uc, addr, size, user):
            if SPEAKER <= addr < SPEAKER+0x4C and not uc.reg_read(UC_ARM_REG_PRIMASK):
                points.append(addr)
        hook = c.uc.hook_add(UC_HOOK_CODE, trace)
        self.execute(c, SPEAKER)
        c.uc.hook_del(hook)
        self.assertTrue(points)
        for point in points:
            c = self.cpu()
            c.w16(RECENT, 800)
            c.w8(GRADE, 30)
            def pause(uc, addr, size, user):
                if addr == point:
                    uc.emu_stop()
            hook = c.uc.hook_add(UC_HOOK_CODE, pause)
            c.uc.reg_write(UC_ARM_REG_SP, SP)
            c.uc.reg_write(UC_ARM_REG_LR, STOP | 1)
            c.uc.emu_start(SPEAKER | 1, STOP, count=4000)
            c.uc.hook_del(hook)
            self.assertEqual(c.uc.reg_read(UC_ARM_REG_PC), point)
            self.assertEqual(c.uc.reg_read(UC_ARM_REG_PRIMASK), 0)
            context = c.uc.context_save()
            c.w16(0x20000112, 6)
            self.execute(c, KEY, stack=SP-0x400)
            self.assertEqual(c.read(BEEP), 100)
            c.uc.context_restore(context)
            c.uc.emu_start(point | 1, STOP, count=4000)
            self.assertEqual(c.uc.reg_read(UC_ARM_REG_PC), STOP)
            self.assertEqual(c.read(BEEP), 100, hex(point))

    # Unchanged contracts from the preceding release remain exact regressions.
    adc = test_roadmap.Roadmap.adc
    test_adc_waits_for_selected_channel_and_restores_mask = test_roadmap.Roadmap.test_adc_waits_for_selected_channel_and_restores_mask
    test_adc_timeout_never_returns_stale_or_false_battery_data = test_roadmap.Roadmap.test_adc_timeout_never_returns_stale_or_false_battery_data
    test_recent_signal_deadline_and_full_idle_after_expiry = test_roadmap.Roadmap.test_recent_signal_deadline_and_full_idle_after_expiry


if __name__ == '__main__':
    unittest.main()
