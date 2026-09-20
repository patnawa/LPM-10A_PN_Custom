"""Actual TX ARM trace -> synthetic analogue link -> actual RX sampler/detector.

Only the envelope link and ADC conversion are modeled. This does not measure
physical propagation, the front end, oscillator accuracy, or bundle selectivity.
The tests deliberately include difficult timing windows that may be rejected.
Run after building both optional candidate binaries.
"""
import importlib.util
import math
from pathlib import Path
import random
import struct
import unittest

from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_PC, UC_ARM_REG_LR

import test_rx_sync
from test_rx_followup import ANALYZERS, GATE_STATE, GRADE, INDICES, TIM5
from verify_digital import ACTIVE, BUFFER, RECENT

FW = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('tx_scan_transport', FW / 'sdk/verify_scan.py')
tx = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tx)


class ScanPair(unittest.TestCase):
    cpu = test_rx_sync.Sync.cpu
    execute = test_rx_sync.Sync.execute
    boundary = test_rx_sync.Sync.boundary

    @classmethod
    def setUpClass(cls):
        cls.data = bytes(test_rx_sync.candidate().data)
        assert cls.data == (FW / 'experimental/APP_LPM-10RX_PN1.10-sync.bin').read_bytes()
        data = (FW / 'experimental/LPM-10A-TX_PN2.13-sync.bin').read_bytes()
        cls.traces = {}
        for mode in (1, 3):
            machine = tx.ScanMachine(data, mode=1)
            # Enter Sync32 through real key handling, including RAM init.
            for _ in range(mode-1):
                machine.call(0x0801458C)
            machine.ticks(8000)
            cls.traces[mode] = machine.outputs

    def transport(self, mode, phase, ratio=1.0, noise=0, offset=0):
        c = self.cpu()
        c.w8(GATE_STATE, 0)
        self.boundary(c)
        self.assertEqual(c.read(ACTIVE), 1)
        rng = random.Random(20260920)
        reads = []
        for index in range(48):
            for sub in range(5):
                # boundary() resets the sampler: its first conversion is
                # TIM5 tick 140, then 160..220. A steady rearmed window has
                # offsets 120..200 instead; see test_scan_acquisition_timing.
                us = (phase+(index+0.7+sub*0.1)*ratio)*5003.125
                tick = offset+math.floor(us/101)
                value = 1000+300*self.traces[mode][tick]+rng.randint(-noise, noise)
                reads.append(max(0, min(4095, value)))
        count = 0

        def adc(uc, addr, size, unused):
            nonlocal count
            self.assertEqual(uc.reg_read(UC_ARM_REG_R1), 1)
            self.assertEqual(c.read(INDICES[0]), count//5)
            uc.reg_write(UC_ARM_REG_R0, reads[count])
            count += 1
            uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

        hook = c.uc.hook_add(UC_HOOK_CODE, adc, begin=0x080072A4, end=0x080072A4)
        try:
            for _ in range(500):
                if not c.read(ACTIVE):
                    break
                # Skip the 19 non-sampling TIM5 ticks; retain the real due
                # interrupt, digital substep counter and five-read reducer.
                c.w32(0x20000100, 19)
                self.execute(c, TIM5, budget=4000)
            self.assertEqual(c.read(ACTIVE), 0)
        finally:
            c.uc.hook_del(hook)
        self.assertEqual(count, 240)
        expected = [(sum(reads[i:i+5])-min(reads[i:i+5])-max(reads[i:i+5]))//3
                    for i in range(0, 240, 5)]
        actual = list(struct.unpack('<48H', c.uc.mem_read(BUFFER, 96)))
        self.assertEqual(actual, expected)
        expected_grade = test_rx_sync.feedback(expected)
        self.execute(c, ANALYZERS[0], budget=30000)
        self.assertEqual(c.read(GRADE), expected_grade)
        self.assertEqual(c.read(RECENT, 2), 800 if expected_grade else 0)
        self.assertEqual(c.read(ACTIVE), 1)
        return expected_grade

    def test_nominal_tx_trace_through_real_rx_sampler(self):
        for mode in (1, 3):
            for phase in (0, 0.125, 3.5, 17.75, 31.875):
                with self.subTest(mode=mode, phase=phase):
                    self.assertGreater(self.transport(mode, phase), 1)

    def test_noisy_drift_and_dither_windows_match_feedback_reference(self):
        for mode in (1, 3):
            for phase, ratio, noise, offset in (
                    (0.203125, 1.0, 0, 0), (0.2109375, 1.0, 0, 0),
                    (2.25, 0.997, 100, 37), (5.75, 1.003, 200, 1300),
                    (15.5, 0.99, 0, 417), (3.25, 1.01, 100, 1999)):
                with self.subTest(mode=mode, phase=phase, ratio=ratio, noise=noise, offset=offset):
                    self.transport(mode, phase, ratio, noise, offset)


if __name__ == '__main__':
    unittest.main()
