"""Diagnostic only: execute PN1.30's analyzer and a real TIM1 interrupt.

The software contract in clean_strength.py says the new fast-gain decision waits
until a completed window is displayed, so that every gain is heard once. Hardware
ADC, GPIO and timer arrival are modeled; production images are never written.
"""
from pathlib import Path
import hashlib
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
SDK = ROOT / "LPM-10A" / "Firmware File" / "rx-sdk"
sys.path.insert(0, str(SDK))

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_MCLASS
import clean_strength as cs
import auto_range
import sample_age_guard
import isolate
import level_display
import test_rx_tracking_streams as streams
import test_rx_auto_range_freshness as agc
from test_rx_followup import ANALYZERS, GRADE
from test_rx_isolate import Analysers, FieldCPU, TIM1
from test_rx_analog_feedback import sine
from verify_control import SP
from verify_digital import ACTIVE, BUFFER, RECENT, pattern


class FastGainHandoff(unittest.TestCase):
    execute = agc.AutoRangeFreshness.execute
    interrupt = agc.AutoRangeFreshness.interrupt
    boundary = agc.AutoRangeFreshness.boundary
    fresh = Analysers.fresh
    timers = streams.TrackingStreams.timers

    @classmethod
    def setUpClass(cls):
        cls.img = cs.build_candidate()
        cls.data = bytes(cls.img.data)
        assert hashlib.sha256(cls.data).hexdigest() == '407b0ba3b80883e4f640ef7e2040a56004ca780a5bd8b81cf3a371ca04a67135'
        cls.curve = cls.img.clean_strength['curve']
        md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS)
        cls.insns = list(md.disasm(cls.img.read(cls.curve, 24), cls.curve))
        marker = next(i for i in cls.insns if i.mnemonic == 'str' and i.op_str == 'r1, [r2]')
        cls.before_marker = marker.address
        cls.after_marker = marker.address + marker.size

    def ready(self, mode):
        c = FieldCPU(self.data, mode=mode, knob=4095)
        self.fresh(c, mode=mode, knob=4095, level=7, grade=0, recent=0)
        c.w32(sample_age_guard.COMPLETED_AT, 1000)
        c.w32(sample_age_guard.TIMER_COUNTER, 1000)
        samples = pattern(0, 800, 3200) if mode == 0 else sine(1200)
        c.uc.mem_write(BUFFER, struct.pack(f'<{len(samples)}H', *samples))
        return c

    def test_no_interrupt_publishes_before_gain_changes(self):
        for mode in (0, 1):
            c = self.ready(mode)
            self.execute(c, ANALYZERS[mode], budget=150000)
            self.assertGreater(c.read(GRADE), 0)
            self.assertGreater(c.read(RECENT, 2), 500)
            self.assertEqual(c.read(auto_range.STATE), 7)
            self.execute(c, TIM1, stack=SP-0x500, budget=10000)
            self.assertEqual(c.read(auto_range.STATE), 2)

    def test_controls_isolate_premature_display_marker(self):
        for mode in (0, 1):
            for location, hide_marker in ((self.before_marker, False),
                                          (self.after_marker, True),
                                          (isolate.PUBLISH, True)):
                c = self.ready(mode)
                def timer(cpu):
                    if hide_marker:
                        cpu.w32(cs.LAST_DISPLAYED, 0)
                    self.execute(cpu, TIM1, stack=SP-0x500, budget=10000)
                self.interrupt(c, ANALYZERS[mode], location, timer)
                self.assertGreater(c.read(GRADE), 0)
                self.assertGreater(c.read(RECENT, 2), 500)
                self.assertEqual(c.read(auto_range.STATE), 7)

    def test_timer_between_display_marker_and_publication_keeps_the_window(self):
        for mode in (0, 1):
            with self.subTest(mode=mode):
                c = self.ready(mode)
                events = []
                def timer(cpu):
                    before = (cpu.read(auto_range.STATE), cpu.read(GRADE), cpu.read(RECENT, 2))
                    self.execute(cpu, TIM1, stack=SP-0x500, budget=10000)
                    after = (cpu.read(auto_range.STATE), cpu.read(GRADE), cpu.read(RECENT, 2))
                    events.append((before, after))
                self.interrupt(c, ANALYZERS[mode], self.after_marker, timer)
                result = (c.read(auto_range.STATE), c.read(GRADE), c.read(RECENT, 2))
                print(f'PN1.30 mode={mode} IRQ at {self.after_marker:#x}: (gain,grade,recent) {events}; final={result}', flush=True)
                self.boundary(c)
                self.assertEqual(c.read(ACTIVE), 1)
                origin = c.read(sample_age_guard.TIMER_COUNTER, 4)
                c.amplitude = lambda tick: 2400
                for _ in range(220):
                    if not c.read(ACTIVE):
                        break
                    self.timers(c, 50)
                self.assertEqual(c.read(ACTIVE), 0)
                delay = (c.read(sample_age_guard.TIMER_COUNTER, 4)-origin)*25.015625/1000
                self.execute(c, ANALYZERS[mode], budget=150000)
                self.assertGreater(c.read(RECENT, 2), 500)
                print(f'PN1.30 mode={mode} accepted feedback returns after full reacquisition: {delay:.2f} modeled ms', flush=True)
                self.assertGreater(result[2], 500,
                    'completed valid window was not published: TIM1 changed gain before publication')

    def test_future_adc_samples_cannot_change_completed_window_strength(self):
        results = []
        for interrupts in (0, 1600):
            c = self.ready(0)
            c.uc.mem_write(BUFFER, struct.pack('<48H', *pattern(0, 800, 1300)))
            c.w16(RECENT, 700)
            c.w32(level_display.AVERAGE, 60000)
            c.w8(level_display.AVERAGE+4, level_display.count(60000))
            c.amplitude = lambda tick: 2400
            if interrupts:
                self.interrupt(c, ANALYZERS[0], self.curve, lambda cpu: self.timers(cpu, interrupts))
            else:
                self.execute(c, ANALYZERS[0], budget=150000)
            result = (c.read(GRADE), c.read(RECENT, 2), c.read(level_display.AVERAGE, 4))
            results.append(result)
            print(f'PN1.30 identical completed Digital window, next ADC interrupts={interrupts}: (grade,recent,strength)={result}', flush=True)
        self.assertEqual(results[1], results[0],
            'future samples in the next acquisition changed the completed window display')


if __name__ == '__main__':
    unittest.main(verbosity=2)
