"""Continuous strong-input repro: real timers, sampler, AGC, analyzer and PWM.

ADC and the analogue link are modeled. Foreground runs once per TIM1 tick;
timer arrivals and reported milliseconds use the established nominal grid,
not measured CPU execution or electrical settling time.
"""
import math
import struct
import unittest

from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_R0, UC_ARM_REG_R1

import auto_range
import auto_range_freshness
import digital_gain_continuity
import test_rx_auto_range_freshness as gain
import test_rx_tracking_streams as streams
from test_rx_followup import ANALYZERS, GRADE
from verify_control import BEEP, MODE, SP
from verify_digital import ACTIVE, RECENT

TIM1 = 0x0800A97C
T1_CYCLES, T5_CYCLES = 64001, 1601
PWM = 0x40000C40


class GainStreamCPU(streams.StreamCPU):
    def __init__(self, data, *, mode=0, level=7):
        super().__init__(data)
        self.w8(MODE, mode)
        self.uc.mem_write(auto_range.STATE, bytes((level, 0, 0, level)))
        self.w16(0x20000068, level*580)
        self.w16(0x2000006A, level)
        self.knob_raw = level*580
        self.amplitude = lambda tick: 1600
        self.uc.hook_add(UC_HOOK_CODE, self.knob, begin=0x08007320, end=0x08007320)

    def hook(self, uc, address, size, user):
        if address != 0x080084D8:
            super().hook(uc, address, size, user)

    def knob(self, uc, address, size, user):
        if uc.reg_read(UC_ARM_REG_R0) != 3:
            raise AssertionError('AGC must read knob channel 3')
        uc.mem_write(uc.reg_read(UC_ARM_REG_R1), struct.pack('<5H', *([self.knob_raw]*5)))
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    def adc(self, uc, address, size, user):
        tick = self.read(streams.TIMER_COUNTER, 4)
        level = self.read(auto_range.STATE)
        # Relative gain based on the documented measured Digital ratios;
        # this fixture is an ideal, continuously present signal with no noise.
        pp = self.amplitude(tick) * (90, 230, 780, 780, 2028, 2028, 2028, 2028)[level] / 2028
        if self.read(MODE) == 0:
            bit = streams.CODE[(math.floor(tick*25.015625/101)//50) % 8]
            value = round(2048 + pp*(bit-.5))
        else:
            value = round(2048 + pp/2*math.cos(2*math.pi*tick*25.015625/1212))
        value = max(0, min(4095, value))
        self.events.append((tick, level, value))
        uc.reg_write(UC_ARM_REG_R0, value)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))


class StrongGainStream(unittest.TestCase):
    execute = gain.AutoRangeFreshness.execute
    boundary = gain.AutoRangeFreshness.boundary
    timers = streams.TrackingStreams.timers

    @classmethod
    def setUpClass(cls):
        img = gain.parent()
        cls.previous = bytes(img.data)
        auto_range_freshness.apply(img)
        cls.freshness = bytes(img.data)
        cls.data = bytes(digital_gain_continuity.build_candidate().data)

    def run_stream(self, *, mode=0, previous=False, change_ms=500, end_ms=900,
                   changes=None, loss_ms=None, signal=True, source_pp=1600, freshness=False):
        data = self.previous if previous else self.freshness if freshness else self.data
        c = GainStreamCPU(data, mode=mode)
        c.amplitude = lambda tick: ((source_pp(tick*T5_CYCLES/64000)
            if callable(source_pp) else source_pp) if signal and
            (loss_ms is None or tick*T5_CYCLES < loss_ms*64000) else 0)
        if changes is None:
            changes = {} if change_ms is None else {change_ms: 2}
        self.boundary(c)
        edges, publications, transitions, unowned_refreshes = [], [], [], []
        sound = False

        def pwm(uc, access, address, size, value, user):
            nonlocal sound
            active = value != 800
            if active != sound:
                edges.append((c.read(streams.TIMER_COUNTER, 4)*T5_CYCLES/64000, active))
                sound = active

        hook = c.uc.hook_add(UC_HOOK_MEM_WRITE, pwm, begin=PWM, end=PWM+1)
        try:
            for tick1 in range(1, end_ms+1):
                prior_recent = c.read(RECENT, 2)
                target = tick1*T1_CYCLES
                self.timers(c, target//T5_CYCLES-c.read(streams.TIMER_COUNTER, 4))
                if tick1 in changes:
                    c.knob_raw = changes[tick1]*580
                before = c.read(auto_range.STATE)
                self.execute(c, TIM1, stack=SP-0x500, budget=10000)
                if c.read(auto_range.STATE) != before:
                    transitions.append((tick1, before, c.read(auto_range.STATE)))
                self.boundary(c)
                if c.read(RECENT, 2) > prior_recent:
                    unowned_refreshes.append((tick1, prior_recent, c.read(RECENT, 2)))
                if not c.read(ACTIVE):
                    self.execute(c, ANALYZERS[mode], budget=100000)
                    publications.append((tick1, c.read(GRADE), c.read(RECENT, 2)))
        finally:
            c.uc.hook_del(hook)
        quiet = [(start, finish-start) for (start, on), (finish, next_on) in zip(edges, edges[1:])
                 if not on and next_on and start > 300]
        if edges and not edges[-1][1] and edges[-1][0] > 300:
            quiet.append((edges[-1][0], end_ms*T1_CYCLES/64000-edges[-1][0]))
        return {'transitions': transitions, 'publications': publications, 'quiet': quiet,
                'max_quiet_ms': max((duration for _, duration in quiet), default=0),
                'edges': edges, 'final_grade': c.read(GRADE), 'final_beep': c.read(BEEP),
                'unowned_refreshes': unowned_refreshes}

    def test_sustained_strong_digital_has_no_dropout_while_turning_knob(self):
        row = self.run_stream()
        self.assertEqual(row['transitions'], [(500, 7, 2)])
        self.assertGreater(row['final_grade'], 0)
        self.assertFalse(row['unowned_refreshes'])
        self.assertEqual(next(p[0] for p in row['publications'] if p[0] >= 500), 741,
                         'gain change still requires all 48 new samples')
        self.assertTrue(any(on and when > 750 for when, on in row['edges']))
        self.assertLess(row['max_quiet_ms'], 150,
                        f"quiet={row['quiet']}; publications={row['publications']}")

    def test_pn123f_reproduces_gain_change_dropout(self):
        row = self.run_stream(freshness=True)
        self.assertEqual(row['transitions'], [(500, 7, 2)])
        self.assertGreater(row['max_quiet_ms'], 200)
        self.assertGreater(row['final_grade'], 0)

    def test_stationary_strong_digital_control_has_no_dropout(self):
        row = self.run_stream(change_ms=None)
        self.assertEqual(row['transitions'], [])
        self.assertGreater(row['final_grade'], 0)
        self.assertLess(row['max_quiet_ms'], 150)

    def test_analog_knob_control_has_no_dropout(self):
        row = self.run_stream(mode=1)
        self.assertEqual(row['transitions'], [(500, 7, 2)])
        self.assertGreater(row['final_grade'], 0)
        self.assertLess(row['max_quiet_ms'], 150)

    def test_signal_loss_during_gain_change_cannot_hold_or_restart_feedback(self):
        row = self.run_stream(loss_ms=500, end_ms=1800,
                              changes={500: 2, 1000: 7, 1500: 2})
        starts = [when for when, on in row['edges'] if on]
        self.assertTrue(starts, 'fixture must establish feedback before signal loss')
        self.assertTrue(any(p[0] < 500 and p[2] == 800 for p in row['publications']))
        self.assertEqual(len(row['transitions']), 3)
        self.assertFalse(row['unowned_refreshes'])
        self.assertFalse([when for when in starts if when >= 850], row['edges'])
        self.assertEqual(row['final_beep'], 0)

    def test_gain_changes_without_prior_signal_never_start_feedback(self):
        row = self.run_stream(signal=False, end_ms=1600,
                              changes={500: 2, 1000: 7, 1500: 2})
        self.assertEqual(len(row['transitions']), 3)
        self.assertFalse(row['edges'])
        self.assertEqual(row['final_beep'], 0)

    def test_repeated_knob_changes_keep_sustained_strong_feedback(self):
        row = self.run_stream(end_ms=1800, changes={500: 2, 1000: 7, 1500: 2})
        self.assertEqual(len(row['transitions']), 3)
        self.assertGreater(row['final_grade'], 0)
        self.assertFalse(row['unowned_refreshes'])
        self.assertLess(row['max_quiet_ms'], 150,
                        f"quiet={row['quiet']}; transitions={row['transitions']}")

    def test_automatic_gain_during_approach_keeps_strong_feedback(self):
        row = self.run_stream(changes={}, source_pp=lambda ms: 1600 if ms < 400 else 2400)
        self.assertEqual(row['transitions'], [(500, 7, 2)])
        self.assertGreater(row['final_grade'], 0)
        self.assertFalse(row['unowned_refreshes'])
        self.assertLess(row['max_quiet_ms'], 150,
                        f"quiet={row['quiet']}; transitions={row['transitions']}")

    def test_turning_knob_off_stops_feedback_despite_sustained_signal(self):
        row = self.run_stream(changes={500: 0})
        starts = [when for when, on in row['edges'] if on]
        self.assertTrue(starts)
        self.assertFalse([when for when in starts if when >= 530], row['edges'])
        self.assertEqual(row['final_beep'], 0)


if __name__ == '__main__':
    unittest.main()
