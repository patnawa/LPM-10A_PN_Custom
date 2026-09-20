"""PN 1.10 failure follow-up: actual TIM5 grid and Pulse test expectations.

Every timer interrupt is executed, including non-sampling interrupts. Only the
ADC conversion and the transmitter-to-probe analogue link are modeled. These
checks distinguish initial sampler alignment from steady acquisition; they do
not measure clock accuracy, interrupt latency or the physical envelope response.
"""
import hashlib
import math
from pathlib import Path
import struct
import unittest

from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_PC, UC_ARM_REG_LR

import test_rx_sync
from test_rx_followup import ANALYZERS, GATE_STATE, GRADE, TIM5
from verify_control import BEEP, MODE
from verify_digital import ACTIVE, BUFFER, RECENT


RX_SHA256 = '6570f521054d77ee97c1a0e37e5a9da0a975d41d452e5f14e63aadb68a9f6e21'
SUBSTEP = 0x200000EE
SAMPLE_INDEX = 0x2000005B
TIMER_COUNTER = 0x20000100
TICK_US = 25.015625
SYNC = tuple(int(bit) for bit in '00011111001001011110101100010001')
LEGACY = tuple(int(bit) for bit in '10110110')


def envelope(timer_tick, mode):
    """Independent nominal TX gate model, before analogue propagation effects."""
    tx_tick = math.floor(timer_tick*TICK_US/101)
    if mode == 'legacy':
        bit = LEGACY[(tx_tick//50) % 8]
    else:
        bit = SYNC[(tx_tick*808//40025) % 32]
    return 1000+300*bit


def pulse_level(milliseconds):
    # PN 2.13 Pulse test carries no 825 Hz modulation and no digital code.
    return 2000 if milliseconds % 499.95 < 99.99 else 1000


class AcquisitionTiming(unittest.TestCase):
    cpu = test_rx_sync.Sync.cpu
    execute = test_rx_sync.Sync.execute
    boundary = test_rx_sync.Sync.boundary
    detect = test_rx_sync.Sync.detect

    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / 'experimental/APP_LPM-10RX_PN1.10-sync.bin'
        cls.data = path.read_bytes()
        if hashlib.sha256(cls.data).hexdigest() != RX_SHA256:
            raise AssertionError('Acquisition audit requires the exact delivered RX PN 1.10 image')

    def test_fresh_and_immediate_rearm_follow_the_complete_tim5_grid(self):
        for mode in ('legacy', 'sync32'):
            with self.subTest(mode=mode):
                c = self.cpu()
                c.w8(GATE_STATE, 0)
                self.boundary(c)
                self.assertEqual((c.read(ACTIVE), c.read(SUBSTEP)), (1, 0))
                tick = 0
                reads = []

                def adc(uc, address, size, user):
                    value = envelope(tick, mode)
                    reads.append((tick, c.read(SUBSTEP), c.read(SAMPLE_INDEX), value))
                    uc.reg_write(UC_ARM_REG_R0, value)
                    uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

                hook = c.uc.hook_add(UC_HOOK_CODE, adc, begin=0x080072A4, end=0x080072A4)
                try:
                    for window, first_tick, last_tick in ((0, 140, 9620), (1, 9740, 19220)):
                        before = len(reads)
                        while c.read(ACTIVE) and tick < last_tick+1:
                            tick += 1
                            self.execute(c, TIM5, budget=4000)
                        self.assertEqual((tick, c.read(ACTIVE)), (last_tick, 0))
                        actual = reads[before:]
                        self.assertEqual(len(actual), 240)
                        self.assertEqual([row[:3] for row in actual],
                                         [(first_tick+200*(i//5)+20*(i % 5),
                                           6+i % 5, i//5) for i in range(240)])
                        values = [row[3] for row in actual]
                        reduced = [(sum(values[i:i+5])-min(values[i:i+5])-max(values[i:i+5]))//3
                                   for i in range(0, 240, 5)]
                        self.assertEqual(list(struct.unpack('<48H', c.uc.mem_read(BUFFER, 96))),
                                         reduced)
                        self.assertEqual((c.read(SUBSTEP), c.read(SAMPLE_INDEX),
                                          c.read(TIMER_COUNTER, 4)), (1, 0, last_tick))
                        self.execute(c, ANALYZERS[0], budget=30000)
                        self.assertEqual(c.read(ACTIVE), 1)
                        self.assertGreater(c.read(GRADE), 1)
                        self.assertEqual(c.read(RECENT, 2), 800)
                finally:
                    c.uc.hook_del(hook)

    def test_pulse_test_has_no_matching_digital_signature(self):
        c = self.cpu()
        for phase_index in range(512):
            phase = phase_index*499.95/512
            samples = []
            for i in range(48):
                values = [pulse_level(phase+(i+0.6+j*0.1)*5.003125) for j in range(5)]
                samples.append((sum(values)-min(values)-max(values))//3)
            with self.subTest(phase=phase):
                self.assertFalse(self.detect(c, samples, recent=0, grade=0))
                self.assertEqual((c.read(GRADE), c.read(RECENT, 2), c.read(BEEP)), (0, 0, 0))

    def test_pulse_test_has_no_matching_analog_tone(self):
        # Cover the quiet interval, flat burst and windows around both edges.
        phases = sorted(set([i*499.95/32 for i in range(32)] +
                            [0, 80, 90, 95, 100, 240, 390, 475, 480, 485, 490, 495]))
        for phase in phases:
            with self.subTest(phase=phase):
                c = self.cpu()
                c.w8(MODE, 1)
                samples = [pulse_level(phase+i*0.325203125) for i in range(64)]
                c.uc.mem_write(BUFFER, struct.pack('<64H', *samples))
                c.w8(ACTIVE, 0)
                self.execute(c, ANALYZERS[1])
                self.assertEqual((c.read(BEEP), c.read(RECENT, 2)), (0, 0))


if __name__ == '__main__':
    unittest.main()
