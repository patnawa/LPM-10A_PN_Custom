"""Current TX GPIO trace -> modeled link -> current RX sampler and speaker.

The TX timer handler and actual carrier GPIO code produce the gate trace;
the RX executes every TIM5 interrupt, TIM1 tick, analyser and speaker path.
ADC coupling, gain ratios, noise and interrupt arrival are modeled. These
checks do not measure electrical output, pickup distance or sound pressure.
TX construction runs in a subprocess because both SDKs use `profiles` as a
module name. No firmware artifacts are written.
"""
from contextlib import redirect_stdout
import hashlib
import io
import json
import math
from pathlib import Path
import random
import subprocess
import sys
import unittest

from unicorn import UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_R0

import auto_range
import rx_resilient
from test_rx_followup import ANALYZERS, GRADE
from test_rx_isolate import FieldCPU, PWM, RATIO, Streams, T1_CYCLES, T5_CYCLES, TIM1
from test_scan_acquisition_timing import TIMER_COUNTER
from verify_control import SP
from verify_digital import ACTIVE, RECENT


TX_SCRIPT = '''
import contextlib, hashlib, io, json
from cable_session import build_candidate
from test_scan_recovery import RecoveryMachine
from test_scan_hardware import BACK, CARRIER_INIT, TIM1_EXPECTED
from verify_scan import IRQ
with contextlib.redirect_stdout(io.StringIO()):
    image = build_candidate()
data = bytes(image.data)
traces, paused = {}, {}
for mode in (1, 2):
    machine = RecoveryMachine(data, mode)
    machine.call(CARRIER_INIT)
    assert machine.timer_configuration() == TIM1_EXPECTED
    trace = machine.physical_ticks(1600, IRQ)
    assert trace[:800] == trace[800:]
    assert set(trace) == {0, 1}
    assert machine.gpio_writes
    traces[mode - 1] = trace[:800]
    machine.call(BACK)
    paused[mode - 1] = machine.physical_ticks(64, IRQ)
    assert paused[mode - 1] == [0] * 64
print(json.dumps({'sha256': hashlib.sha256(data).hexdigest(),
                  'version': image.read(0x08011660, 8).split(b'\\0')[0].decode(),
                  'traces': traces, 'paused': paused}))
'''


class TransportCPU(FieldCPU):
    def __init__(self, data, *, mode, trace, phase, ratio, noise, contact):
        self.trace = trace
        self.phase, self.ratio = phase, ratio
        self.noise, self.contact = noise, contact
        self.rng = random.Random(0x131234)
        self.adc_reads = 0
        super().__init__(data, mode=mode, knob=4095)

    def adc(self, uc, address, size, user):
        tick = self.read(TIMER_COUNTER, 4)
        milliseconds = tick * T5_CYCLES / 64000
        tx_tick = math.floor(tick * 25.015625 * self.ratio / 101 + self.phase * 50)
        bit = self.trace[tx_tick % len(self.trace)]
        gain = RATIO[self.read(auto_range.STATE)] / RATIO[7]
        pp = min(1200 * self.contact(milliseconds) * gain, self.limit)
        value = round(2048 + pp * (bit - 0.5)) + self.rng.randint(-self.noise, self.noise)
        self.adc_reads += 1
        uc.reg_write(UC_ARM_REG_R0, max(0, min(4095, value)))
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))


class CurrentPair(Streams):
    @classmethod
    def setUpClass(cls):
        tx_sdk = Path(__file__).resolve().parents[1] / 'sdk'
        result = subprocess.run([sys.executable, '-c', TX_SCRIPT], cwd=tx_sdk,
                                capture_output=True, text=True, timeout=30, check=True)
        fixture = json.loads(result.stdout)
        cls.tx_sha = fixture['sha256']
        cls.tx_version = fixture['version']
        cls.traces = {int(mode): trace for mode, trace in fixture['traces'].items()}
        cls.paused = {int(mode): trace for mode, trace in fixture['paused'].items()}
        with redirect_stdout(io.StringIO()):
            cls.data = bytes(rx_resilient.build_candidate().data)

    def transport(self, mode, *, phase=0, ratio=1, noise=0, contact=lambda ms: 1,
                  end_ms=900, trace=None):
        c = TransportCPU(self.data, mode=mode, trace=self.traces[mode] if trace is None else trace,
                         phase=phase, ratio=ratio, noise=noise, contact=contact)
        self.boundary(c)
        edges, publications, sound = [], [], False

        def pwm(uc, access, address, size, value, user):
            nonlocal sound
            active = value != 800
            if active != sound:
                edges.append((c.read(TIMER_COUNTER, 4) * T5_CYCLES / 64000, active))
                sound = active

        hook = c.uc.hook_add(UC_HOOK_MEM_WRITE, pwm, begin=PWM, end=PWM + 1)
        try:
            for ms in range(1, end_ms + 1):
                self.timers(c, ms * T1_CYCLES // T5_CYCLES - c.read(TIMER_COUNTER, 4))
                self.execute(c, TIM1, stack=SP - 0x500, budget=10000)
                self.boundary(c)
                if not c.read(ACTIVE):
                    self.execute(c, ANALYZERS[mode], budget=150000)
                    publications.append((ms, c.read(GRADE), c.read(RECENT, 2)))
        finally:
            c.uc.hook_del(hook)
        self.assertGreater(c.adc_reads, 100)
        return {'edges': edges, 'publications': publications, 'end_ms': end_ms}

    def test_fixture_executes_the_current_pair(self):
        self.assertEqual(self.tx_version, 'PN2.34')
        self.assertEqual(self.data[0x0800CDE4 - 0x08006800:][:8], b'PN1.31\0\0')
        print(f'paired CPU trace TX {self.tx_version} {self.tx_sha} -> '
              f'RX PN1.31 {hashlib.sha256(self.data).hexdigest()}')

    def test_phase_clock_and_noise_sweeps_are_audible_in_both_modes(self):
        for mode in (0, 1):
            for phase, ratio, noise in ((0, 1, 0), (0.375, 1.003, 30), (3.875, 0.997, 60)):
                with self.subTest(mode=mode, phase=phase, ratio=ratio, noise=noise):
                    row = self.transport(mode, phase=phase, ratio=ratio, noise=noise)
                    self.assertGreater(self.sounding(row, 400, 900), 10, row)
                    self.assertTrue(any(grade > 0 and recent > 500
                                        for _, grade, recent in row['publications']), row)

    def test_disconnected_link_and_actual_paused_tx_do_not_detect(self):
        for mode in (0, 1):
            for kwargs in ({'contact': lambda ms: 0, 'noise': 10}, {'trace': self.paused[mode]}):
                with self.subTest(mode=mode, kind=tuple(kwargs)):
                    row = self.transport(mode, **kwargs)
                    self.assertEqual(self.sounding(row, 0, 900), 0, row)
                    self.assertFalse(any(grade > 0 and recent > 500
                                         for _, grade, recent in row['publications']), row)

    def test_short_visits_release_and_reacquire_without_stale_tone(self):
        # Two 600 ms visits with enough intervening quiet time for full release.
        contact = lambda ms: int(200 <= ms < 800 or 1500 <= ms < 2100)
        for mode in (0, 1):
            with self.subTest(mode=mode):
                row = self.transport(mode, phase=0.375, noise=30, contact=contact, end_ms=2700)
                for start, end in ((400, 800), (1700, 2100)):
                    self.assertGreater(self.sounding(row, start, end), 10, row)
                for start, end in ((0, 200), (1300, 1500), (2500, 2700)):
                    self.assertEqual(self.sounding(row, start, end), 0, row)


if __name__ == '__main__':
    unittest.main()
