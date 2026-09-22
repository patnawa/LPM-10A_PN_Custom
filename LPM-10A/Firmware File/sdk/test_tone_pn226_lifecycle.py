"""Pinned PN2.26 Tone lifecycle audit using real keys, IRQs and carrier GPIO.

RTOS/logging and key-activity services are modeled by the established harness.
Register programming is observed, not a physical jack waveform or CPU timing.
"""
import hashlib
from pathlib import Path
import unittest

from unicorn import UC_HOOK_CODE
from unicorn.arm_const import (UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_PRIMASK,
                               UC_ARM_REG_R0, UC_ARM_REG_SP)

import test_scan_recovery as recovery
from test_scan_hardware import CARRIER_INIT, requested_wave
from verify_scan import SCAN, STATE, DIGITAL, IRQ, STOP, STACK


SHA256 = 'c77579f018bb820532b3c5974ae63fbf04c4e60359188f7e39a8a8f9a1533df8'
KEY = 0x080149FC
EVENT = 0x2000D000


class ToneLifecycle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = (Path(__file__).resolve().parents[1]
                    / 'experimental/LPM-10A-TX_PN2.26-qc-display.bin').read_bytes()
        if hashlib.sha256(cls.data).hexdigest() != SHA256:
            raise AssertionError('Tone lifecycle audit requires exact published PN2.26')

    def machine(self, mode=1, count=0, enabled=1, state=5):
        m = recovery.RecoveryMachine(self.data, mode, enabled, state)
        m.call(CARRIER_INIT)
        m.physical_ticks(count, IRQ)
        return m

    def press(self, m, key):
        m.uc.mem_write(EVENT, bytes((key, 3)))
        m.call(KEY, EVENT)

    def assert_next_tick(self, m):
        before = len(m.requests)
        enabled, state = m.r8(SCAN), m.r8(STATE)
        m.call(IRQ)
        if enabled and state == 5:
            self.assertEqual(len(m.requests), before+1)
            self.assertEqual(m.carrier_pins_selected(), m.requests[-1])
        else:
            self.assertEqual(len(m.requests), before)
            self.assertEqual(m.pin_modes()[1], 3, 'PB13 must remain off while stopped')

    def test_real_keys_cover_cold_entry_pause_mode_right_exit_and_reentry(self):
        m = self.machine(mode=0, enabled=0, state=2)
        m.w8(STATE+1, 5)
        self.press(m, 4)  # Home OK enters Tone, initially stopped.
        self.assertEqual((m.r8(STATE), m.r8(SCAN)), (5, 0))
        self.assertIn(9, m.messages)
        self.assert_next_tick(m)
        for cycle in range(4):
            self.press(m, 4)
            mode = m.r8(SCAN+1) or 1
            self.assert_next_tick(m)
            self.assertEqual(m.r8(SCAN+1), mode)
            m.physical_ticks(67, IRQ)
            self.press(m, 5)  # RIGHT carrier setting
            self.assert_next_tick(m)
            self.press(m, 2)  # UP toggles Digital / Analog
            self.assertEqual(m.r8(SCAN+1), 3-mode)
            self.assert_next_tick(m)
            self.press(m, 0)
            frozen = bytes(m.uc.mem_read(DIGITAL, 10))
            self.press(m, 5)
            self.press(m, 3)  # DOWN also changes mode while paused
            for _ in range(20):
                self.assert_next_tick(m)
            self.assertEqual(bytes(m.uc.mem_read(DIGITAL, 4)), frozen[:4])
            self.press(m, 0)
            self.assertEqual(m.r8(STATE), 2)
            self.assert_next_tick(m)
            m.w8(STATE+1, 5)
            self.press(m, 4)
            self.assertEqual((m.r8(STATE), m.r8(SCAN)), (5, 0))

    def test_all_812_phases_survive_right_pause_resume_and_two_mode_roundtrip(self):
        for mode, count in ((1, 800), (2, 12)):
            for phase in range(count):
                with self.subTest(mode=mode, phase=phase):
                    m = self.machine(mode)
                    if mode == 1:
                        m.w32(DIGITAL, phase)
                    else:
                        m.physical_ticks(phase, IRQ)
                    self.press(m, 5)
                    self.assertEqual(m.physical_ticks(1, IRQ), [requested_wave(mode, phase)])
                    self.press(m, 0)
                    self.press(m, 2)
                    self.press(m, 3)
                    self.press(m, 4)
                    self.assertEqual(m.physical_ticks(1, IRQ), [requested_wave(mode, phase+1)])

    def test_gui_messages_render_both_existing_modes_in_both_languages(self):
        from thai.engine import Scene
        from thai.mockup import sc_scan
        for language in (1, 2):
            for mode in (1, 2):
                for enabled in (0, 1):
                    with self.subTest(language=language, mode=mode, enabled=enabled):
                        scene = Scene(image=self.data, lang=language)
                        sc_scan(scene, mode=mode, enable=enabled)
                        labels = [item for item in scene.log if item[0] == 'ascii'
                                  and item[1] in ('Digital 454 kHz', 'Analog 825 Hz')]
                        self.assertEqual({item[1] for item in labels},
                                         {'Digital 454 kHz', 'Analog 825 Hz'})
                        for item in labels:
                            selected = item[1].startswith('Digital') == (mode == 1)
                            self.assertEqual(item[4], 0xFE60 if selected else 0xFFFF)

    def trace_key(self, m, key):
        points = []
        def trace(uc, address, size, user):
            if not uc.reg_read(UC_ARM_REG_PRIMASK):
                points.append(address)
        hook = m.uc.hook_add(UC_HOOK_CODE, trace)
        try:
            self.press(m, key)
        finally:
            m.uc.hook_del(hook)
        return points

    def interrupted_key(self, m, key, occurrence):
        m.uc.mem_write(EVENT, bytes((key, 3)))
        m.uc.reg_write(UC_ARM_REG_SP, STACK)
        m.uc.reg_write(UC_ARM_REG_LR, STOP | 1)
        m.uc.reg_write(UC_ARM_REG_R0, EVENT)
        visited = 0
        def stop(uc, address, size, user):
            nonlocal visited
            if not uc.reg_read(UC_ARM_REG_PRIMASK):
                if visited == occurrence:
                    uc.emu_stop()
                visited += 1
        hook = m.uc.hook_add(UC_HOOK_CODE, stop)
        m.uc.emu_start(KEY | 1, STOP, count=10000)
        m.uc.hook_del(hook)
        resume = m.uc.reg_read(UC_ARM_REG_PC)
        self.assertNotEqual(resume, STOP)
        context = m.uc.context_save()
        # Separate exception stack so the injected IRQ cannot overwrite the
        # suspended key handler's locals. NVIC latency is not modeled.
        m.uc.reg_write(UC_ARM_REG_SP, STACK-0x800)
        m.uc.reg_write(UC_ARM_REG_LR, STOP | 1)
        requests_before = len(m.requests)
        m.uc.emu_start(IRQ | 1, STOP, count=10000)
        self.assertEqual(m.uc.reg_read(UC_ARM_REG_PC), STOP)
        if len(m.requests) > requests_before:
            self.assertEqual(m.carrier_pins_selected(), m.requests[-1],
                             'the preempting IRQ itself must drive its requested gate')
        m.uc.context_restore(context)
        m.uc.emu_start(resume | 1, STOP, count=10000)
        self.assertEqual(m.uc.reg_read(UC_ARM_REG_PC), STOP)
        self.assertEqual(m.uc.reg_read(UC_ARM_REG_SP), STACK)

    def test_timer_preemption_at_every_unmasked_key_instruction_keeps_carrier_coherent(self):
        tested = 0
        for mode, phase in ((1, 17), (1, 67), (2, 3), (2, 9)):
            for key, enabled in ((0, 1), (2, 1), (3, 0), (4, 0), (5, 1), (5, 0)):
                m = self.machine(mode, phase, enabled)
                initial = [(base, bytes(m.uc.mem_read(base, size))) for base, size in
                           ((0x20000000, 0x10000), (0x40000000, 0x30000))]
                context = m.uc.context_save()
                trace = self.trace_key(m, key)
                for occurrence in range(len(trace)):
                    with self.subTest(mode=mode, phase=phase, key=key,
                                      enabled=enabled, occurrence=occurrence):
                        # Restore the exact initialized machine instead of
                        # reexecuting dozens of identical setup IRQs per point.
                        for base, data in initial:
                            m.uc.mem_write(base, data)
                        m.uc.context_restore(context)
                        m.requests.clear()
                        m.outputs.clear()
                        m.messages.clear()
                        m.gpio_writes.clear()
                        m.timer_writes.clear()
                        self.interrupted_key(m, key, occurrence)
                        self.assert_next_tick(m)
                        tested += 1
        self.assertGreater(tested, 1000)


if __name__ == '__main__':
    unittest.main()
