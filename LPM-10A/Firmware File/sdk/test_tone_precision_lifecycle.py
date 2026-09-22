"""Candidate Tone lifecycle checks with real key, timer, GPIO and GUI code.

PN2.27 inherits the exact legacy waveform oracle. The separate PN2.27A tests
use an independent rational Analog reference; they never assume six-tick
half cycles. Timer arrivals and peripheral registers are modeled, not actual
electrical output, hardware interrupt latency, or measured detection range.
"""
import contextlib
import io
import unittest

from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0

import test_tone_pn226_lifecycle as baseline
from test_scan_hardware import requested_wave
from verify_scan import SCAN, STATE, DIGITAL, IRQ


def navigation_preemption_audit(self):
    """Inject actual TIM2 at each task boundary of Home entry and Tone exit."""
    tested = 0
    for mode in (1, 2):
        for state, key, expected in ((5, 0, 2), (2, 4, 5)):
            m = self.machine(mode=mode, enabled=0, state=state)
            m.w8(STATE+1, 5)
            initial = [(base, bytes(m.uc.mem_read(base, size))) for base, size in
                       ((0x20000000, 0x10000), (0x40000000, 0x30000))]
            context = m.uc.context_save()
            points = self.trace_key(m, key)
            for occurrence in range(len(points)):
                with self.subTest(mode=mode, state=state, key=key, occurrence=occurrence):
                    for base, data in initial:
                        m.uc.mem_write(base, data)
                    m.uc.context_restore(context)
                    m.requests.clear()
                    m.messages.clear()
                    m.gpio_writes.clear()
                    m.timer_writes.clear()
                    self.interrupted_key(m, key, occurrence)
                    self.assertEqual((m.r8(STATE), m.r8(SCAN)), (expected, 0))
                    self.assertFalse(m.requests, 'navigation while stopped must not transmit')
                    self.assert_next_tick(m)
                    tested += 1
    self.assertGreater(tested, 1000)


class TonePrecisionLifecycle(baseline.ToneLifecycle):
    test_home_entry_and_tone_exit_survive_every_unmasked_irq = navigation_preemption_audit

    @classmethod
    def setUpClass(cls):
        import tone_precision
        with contextlib.redirect_stdout(io.StringIO()):
            cls.img = tone_precision.build_candidate()
        cls.data = bytes(cls.img.data)


def analog_reference(phase, count):
    """Advance 33/400 cycles per timer tick, then emit the selected half cycle."""
    if not 0 <= phase < 2000:
        phase = 0
    bits = [int(((phase+165*(i+1)) % 2000) >= 1000) for i in range(count)]
    return bits, (phase+165*count) % 2000


class ToneAlignmentLifecycle(unittest.TestCase):
    # These helpers make no assumption about Analog frequency or phase layout.
    machine = baseline.ToneLifecycle.machine
    press = baseline.ToneLifecycle.press
    assert_next_tick = baseline.ToneLifecycle.assert_next_tick
    trace_key = baseline.ToneLifecycle.trace_key
    test_real_keys_cover_cold_entry_pause_mode_right_exit_and_reentry = (
        baseline.ToneLifecycle.test_real_keys_cover_cold_entry_pause_mode_right_exit_and_reentry)
    test_timer_preemption_at_every_unmasked_key_instruction_keeps_carrier_coherent = (
        baseline.ToneLifecycle.test_timer_preemption_at_every_unmasked_key_instruction_keeps_carrier_coherent)
    test_home_entry_and_tone_exit_survive_every_unmasked_irq = navigation_preemption_audit

    @classmethod
    def setUpClass(cls):
        import tone_alignment
        with contextlib.redirect_stdout(io.StringIO()):
            cls.img = tone_alignment.build_candidate()
        cls.data = bytes(cls.img.data)
        # Filled from explicit builder metadata, never discovered by searching
        # the emitted instructions or reconstructing the production algorithm.
        cls.phase_address = cls.img.tone_alignment['phase_address']

    def phase(self, m):
        return int.from_bytes(m.uc.mem_read(self.phase_address, 2), 'little')

    def set_phase(self, m, value):
        m.uc.mem_write(self.phase_address, value.to_bytes(2, 'little'))

    def interrupted_key(self, m, key, occurrence):
        # Strengthen the shared interleaving audit with the independent Analog
        # sample/cursor oracle at the actual generator and gate call sites.
        phase_before = self.phase(m)
        emissions = []
        pending = []
        def observe(uc, address, size, user):
            if address == 0x08014344 and m.r8(SCAN):
                expected, advanced = analog_reference(self.phase(m), 1)
                pending.append((expected[0], advanced))
            elif address == 0x0801464C and pending:
                bit, advanced = pending.pop(0)
                self.assertEqual(uc.reg_read(UC_ARM_REG_R0), bit)
                emissions.append(advanced)
        hook = m.uc.hook_add(UC_HOOK_CODE, observe)
        try:
            baseline.ToneLifecycle.interrupted_key(self, m, key, occurrence)
        finally:
            m.uc.hook_del(hook)
        self.assertFalse(pending)
        self.assertEqual(self.phase(m), emissions[-1] if emissions else phase_before)

    def assert_analog_ticks(self, m, count):
        initial = self.phase(m)
        expected, final = analog_reference(initial, count)
        before = len(m.requests)
        self.assertEqual(m.physical_ticks(count, IRQ), expected)
        self.assertEqual(m.requests[before:], expected)
        self.assertEqual(self.phase(m), final)

    def test_all_400_phases_keep_right_pause_mode_roundtrip_and_home_reentry(self):
        for phase in range(0, 2000, 5):
            with self.subTest(phase=phase):
                m = self.machine(mode=2)
                self.set_phase(m, phase)
                self.press(m, 5)
                self.assert_analog_ticks(m, 2)
                self.press(m, 0)
                frozen = self.phase(m)
                self.press(m, 5)  # RIGHT while stopped must not advance phase.
                self.press(m, 2)
                self.press(m, 3)
                for _ in range(7):
                    self.assert_next_tick(m)
                self.assertEqual(self.phase(m), frozen)
                self.press(m, 4)
                self.assert_analog_ticks(m, 3)
                frozen = self.phase(m)
                self.press(m, 0)
                self.press(m, 0)
                self.assertEqual(m.r8(STATE), 2)
                m.w8(STATE+1, 5)
                self.press(m, 4)
                self.assertEqual((m.r8(STATE), m.r8(SCAN)), (5, 0))
                self.assertEqual(self.phase(m), frozen)
                self.press(m, 4)
                self.assert_analog_ticks(m, 2)

    def test_old_phase_bytes_do_not_control_new_analog_cadence(self):
        # PN2.26 used separate half-cycle/output bytes. A valid accumulator
        # controls output independently of their residue from a prior visit.
        for seed in (0, 995, 1000, 1995):
            for residue in (0, 5, 6, 255):
                with self.subTest(seed=seed, residue=residue):
                    m = self.machine(mode=2)
                    # Independent addresses recovered from exact PN2.26:
                    # periodic toggle, half-cycle counter, prior output bit.
                    for address in (0x200000D2, 0x200000E0, 0x200000E1):
                        m.w8(address, residue)
                    self.set_phase(m, seed)
                    self.assert_analog_ticks(m, 24)

    def test_invalid_phase_cold_start_and_reentry_have_a_bounded_recovery(self):
        for seed in (0, 2000, 65535):
            with self.subTest(seed=seed):
                m = self.machine(mode=2)
                self.set_phase(m, seed)
                self.assert_analog_ticks(m, 400)
                self.assertEqual(self.phase(m), 0)
                self.press(m, 0)
                self.press(m, 0)
                self.assertEqual(m.r8(STATE), 2)
                m.w8(STATE+1, 5)
                self.press(m, 4)
                self.assertEqual((m.r8(STATE), m.r8(SCAN)), (5, 0))
                self.press(m, 4)
                self.assert_analog_ticks(m, 400)
                self.assertEqual(self.phase(m), 0)

    def test_digital_all_800_phases_remain_legacy_exact(self):
        for phase in range(800):
            with self.subTest(phase=phase):
                m = self.machine(mode=1)
                m.w32(DIGITAL, phase)
                self.press(m, 5)
                self.assertEqual(m.physical_ticks(1, IRQ), [requested_wave(1, phase)])
                self.press(m, 0)
                self.press(m, 2)
                self.press(m, 3)
                self.press(m, 4)
                self.assertEqual(m.physical_ticks(1, IRQ), [requested_wave(1, phase+1)])

    def test_gui_renders_alignment_label_and_preserves_digital_label(self):
        from thai.engine import Scene
        from thai.mockup import sc_scan
        for language in (1, 2):
            for mode in (1, 2):
                for enabled in (0, 1):
                    with self.subTest(language=language, mode=mode, enabled=enabled):
                        scene = Scene(image=self.data, lang=language)
                        sc_scan(scene, mode=mode, enable=enabled)
                        labels = [item for item in scene.log if item[0] == 'ascii'
                                  and item[1] in ('Digital 454 kHz', 'Analog 817 Hz')]
                        self.assertEqual({item[1] for item in labels},
                                         {'Digital 454 kHz', 'Analog 817 Hz'})
                        for item in labels:
                            selected = item[1].startswith('Digital') == (mode == 1)
                            self.assertEqual(item[4], 0xFE60 if selected else 0xFFFF)


if __name__ == '__main__':
    unittest.main()
