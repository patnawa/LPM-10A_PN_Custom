"""QC pulse-count gate under a fixed physical frequency and RTOS wake jitter.

Unlike the old harness, count is derived from elapsed time after the real
TIM8 reset. The scheduler model may wake the task late or at another tick
phase. These are deterministic stimuli, not captured hardware waveforms.
"""
import contextlib
import io
import struct
import unittest

from test_qc_continuity import Harness, DELAY, RECEIVE, TIMER_COUNT
import test_qc_classic as classic

MEASURE, RESET = 0x08018B84, 0x080188CE
TICK, VAL, LOAD, ICSR = 0x200001A0, 0xE000E018, 0xE000E014, 0xE000ED04
CYCLES_PER_US = 144


class PulseHarness(Harness):
    def __init__(self, data, *, lang=1):
        super().__init__(data, lang=lang)
        self.us = self.reset_us = 0
        self.hz = [100_000]*8
        self.gates = lambda pin, number: 10_000
        self.windows = []
        self.s.uc.mem_write(LOAD, struct.pack('<I', 143999))
        self.sync_clock()

        def reset(uc):
            if self.s.arg(0) == 0x40013400:
                self.reset_us = self.us
            return False  # Real TIM_SetCounter still writes the register.

        def delay(uc):
            ms = self.s.arg(0)
            self.delays.append(ms)
            elapsed = self.gates(self.selected, self.pin_reads[self.selected]) \
                if ms == 10 and self.selected < 8 else ms*1000
            self.us += elapsed
            self.sync_clock()
            if self.selected < 8:
                window = self.us-self.reset_us
                count = (self.hz[self.selected]*window+500_000)//1_000_000
                self.s.w16(TIMER_COUNT, count & 65535)
                self.s.uc.mem_write(0x40013410, struct.pack('<I', int(count > 65535)))
                self.windows.append((self.selected, window, count))
            self.s.ret(0)
            return True

        def receive(uc):
            timeout = self.s.arg(2)
            self.timeouts.append(timeout)
            if timeout != 0xFFFFFFFF:
                self.us += timeout*1000
                self.sync_clock()
            self.s.ret(0)
            return True

        self.s.at[RESET], self.s.at[DELAY], self.s.at[RECEIVE] = reset, delay, receive

    def sync_clock(self):
        tick = (self.us//1000) & 0xFFFFFFFF
        self.s.vals['tick'] = tick
        self.s.uc.mem_write(TICK, struct.pack('<I', tick))
        self.s.uc.mem_write(VAL, struct.pack('<I', 143999-(self.us % 1000)*CYCLES_PER_US))
        self.s.uc.mem_write(ICSR, bytes(4))

    def advance(self, ticks):
        self.us += ticks*1000
        self.sync_clock()


class QCGateTiming(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import qc_timing
        with contextlib.redirect_stdout(io.StringIO()):
            cls.img = qc_timing.build_candidate()
        cls.data = bytes(cls.img.data)

    def sweep(self, h):
        target = len(h.reads)+8
        for _ in range(100):
            h.poll()
            if len(h.reads) == target:
                return list(h.s.uc.mem_read(self.img.qc['state']+32, 8))
        self.fail('acquisition did not reach a full sweep')

    def test_same_frequency_returns_same_count_despite_9_to_11ms_wait(self):
        h = PulseHarness(self.data)
        h.s.call(0x08018060, 0)
        actual = []
        for elapsed in (9_000, 10_000, 11_000):
            h.gates = lambda pin, number, elapsed=elapsed: elapsed
            actual.append(h.s.call(MEASURE))
        self.assertEqual(actual, [1000, 1000, 1000],
                         'same wire frequency must not change with the scheduler wake time')

    def test_complete_stationary_cable_stays_green_under_scheduler_jitter(self):
        h = PulseHarness(self.data)
        h.enter()
        self.assertEqual(classic.QCClassic.initialize(self, h)[0], 0)
        h.hz = [93_000]*8  # Every connected wire is well below its 100 kHz unplugged baseline.
        h.gates = lambda pin, number: (10_000, 10_000, 10_000, 11_000)[(number+pin) % 4]
        states = [self.sweep(h) for _ in range(10)]
        self.assertTrue(all(row == [1]*8 for row in states[2:]),
                        f'stable physical wires flickered solely from scheduling: {states}')

    def test_unplugged_after_init_stays_open_despite_early_tick_phase(self):
        h = PulseHarness(self.data)
        h.enter()
        self.assertEqual(classic.QCClassic.initialize(self, h)[0], 0)
        h.gates = lambda pin, number: (9_000, 9_000, 9_000, 10_000)[(number+pin) % 4]
        states = [self.sweep(h) for _ in range(8)]
        self.assertTrue(all(1 not in row for row in states),
                        f'unchanged unplugged frequency created false green: {states}')

    def test_jittered_init_and_live_capture_share_units_for_every_pin(self):
        h = PulseHarness(self.data)
        baseline = [1000+30*pin for pin in range(8)]
        h.hz = [value*100 for value in baseline]
        h.gates = lambda pin, number: (9_000, 9_300, 10_000, 10_700, 11_000)[(number+pin) % 5]
        h.us = 723
        h.sync_clock()
        h.enter()
        self.assertEqual(classic.QCClassic.initialize(self, h)[0], 0)
        self.assertEqual(struct.unpack('<8H', h.s.uc.mem_read(0x2000021C, 16)), tuple(baseline))
        h.hz = [(value-50)*100 for value in baseline]
        for _ in range(3):
            self.sweep(h)
        self.assertEqual(self.sweep(h), [1]*8)
        # A real open conductor clears immediately, despite the green qualifier.
        for pin in range(8):
            h.hz[pin] = baseline[pin]*100
            expected = [1]*8
            expected[pin] = 2
            self.assertEqual(self.sweep(h), expected)
            # Exercise the actual renderer; routine UI refresh is throttled to 200 ms.
            h.s.call(self.img.qc_classic['ui']['draw'])
            for shown in range(8):
                green = h.s.fb[82+27*(7-shown)][205] == 0x07E0
                self.assertEqual(green, shown != pin)
            h.hz[pin] = (baseline[pin]-50)*100
            for _ in range(3):
                self.sweep(h)
            self.assertEqual(self.sweep(h), [1]*8)

    def test_unplug_replug_and_real_invalid_signal_are_not_hidden(self):
        h = PulseHarness(self.data)
        h.enter()
        self.assertEqual(classic.QCClassic.initialize(self, h)[0], 0)
        h.hz = [93_000]*8
        h.gates = lambda pin, number: (9_500, 10_000, 11_000)[(number+pin) % 3]
        for _ in range(3):
            self.sweep(h)
        self.assertEqual(self.sweep(h), [1]*8)
        h.hz = [100_000]*8
        self.assertEqual(self.sweep(h), [2]*8)
        h.hz = [93_000]*8
        self.assertEqual(self.sweep(h), [2]*8)
        self.assertEqual(self.sweep(h), [2]*8)
        self.assertEqual(self.sweep(h), [1]*8)
        h.hz[2], h.hz[5] = 0, 10_000_000
        expected = [1]*8
        expected[2] = expected[5] = 3
        self.assertEqual(self.sweep(h), expected)

    def test_pn224_negative_control_flickers_with_the_same_physical_stimulus(self):
        import length_integrity
        with contextlib.redirect_stdout(io.StringIO()):
            parent = length_integrity.build_candidate()
        h = PulseHarness(bytes(parent.data))
        h.enter()
        self.assertEqual(classic.QCClassic.initialize(self, h)[0], 0)
        h.hz = [93_000]*8
        h.gates = lambda pin, number: (10_000, 10_000, 10_000, 11_000)[(number+pin) % 4]
        states = [self.sweep(h) for _ in range(8)]
        self.assertGreater(len({tuple(row) for row in states[2:]}), 1)
        self.assertTrue(any(3 in row for row in states[2:]))


if __name__ == '__main__':
    unittest.main()
