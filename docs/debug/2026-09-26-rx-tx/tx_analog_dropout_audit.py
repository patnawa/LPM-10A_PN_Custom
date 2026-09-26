"""Read-only PN2.33/PN2.34 upstream audit for owner-reported Analog dropouts.

Actual Thumb keys, state hooks, TIM2 dispatcher, Analog generator and carrier
GPIO run. Timer arrival, RTOS/logging/queue services and peripheral registers
are modeled: this cannot establish signal amplitude or continuity at the jack.
No firmware bytes or release artifacts are changed.
"""
from collections import Counter
import hashlib
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
SDK = ROOT / 'LPM-10A/Firmware File/sdk'
sys.path.insert(0, str(SDK))

from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_PRIMASK,
                               UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC)
from test_scan_recovery import RecoveryMachine
from test_scan_hardware import CARRIER_INIT, TIM1_EXPECTED
from test_tone_alignment import expected, phase_read
from test_tone_pn226_lifecycle import KEY, EVENT
from verify_scan import IRQ, SCAN, STATE, DIGITAL, STACK, STOP
from length_ref_anytime import bl_target

FILES = (
    ('PN2.33', 'LPM-10A-TX_PN2.33-cable-safe.bin',
     '84f9fb991a5bf43f0e29d978277ebe76baa58ff21714b430c1b6cef040751e91'),
    ('PN2.34', 'LPM-10A-TX_PN2.34-cable-session.bin',
     '92ebb4cd60e7b652f32ca65cfa21401c1657fa63ee1b945864fed3c74a422227'),
)
TICK, SESSION = 0x200001A0, 0x2000F378


class Machine(RecoveryMachine):
    """Also execute the real RTOS tick reader used by carrier OFF parity."""
    def __init__(self, data, enabled=1, state=5):
        super().__init__(data, 2, enabled, state)
        self.uc.mem_map(0xE000E000, 0x2000)
        self.queued = []

    def hook(self, uc, address, size, user):
        if address == 0x0801C5B0:
            self.instructions += 1
            self.calls[address] += 1
        elif address == 0x0801CAA0:
            self.queued.append(uc.reg_read(UC_ARM_REG_R0))
            self.ret(1)
        else:
            super().hook(uc, address, size, user)

    def press(self, key):
        self.uc.mem_write(EVENT, bytes((key, 3)))
        self.call(KEY, EVENT)

    def initialize(self, data):
        # The historical main initializer intentionally establishes main's
        # register state; unlike ordinary functions it is not an AAPCS seam.
        self.uc.reg_write(UC_ARM_REG_SP, STACK)
        self.uc.reg_write(UC_ARM_REG_LR, STOP | 1)
        self.uc.emu_start(bl_target(data, 0x0801BBAC) | 1, STOP, count=10000)
        assert self.uc.reg_read(UC_ARM_REG_PC) == STOP
        assert self.uc.reg_read(UC_ARM_REG_SP) == STACK


class AnalogDropoutAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.images = []
        for version, name, digest in FILES:
            data = (SDK.parent / 'experimental' / name).read_bytes()
            assert hashlib.sha256(data).hexdigest() == digest
            cls.images.append((version, data))

    def assert_running(self, m, ticks, *, tick_seed=0, session_sentinels=False):
        seed = phase_read(m)
        trace = []
        requests = len(m.requests)
        timer = list(m.timer_writes)
        for tick in range(ticks):
            m.w32(TICK, (tick_seed + tick // 10) & 0xFFFFFFFF)
            m.call(IRQ)
            self.assertEqual(m.uc.reg_read(UC_ARM_REG_PRIMASK), 0, tick)
            trace.append(m.carrier_pins_selected())
        self.assertEqual(trace, expected(seed, ticks))
        self.assertEqual(len(m.requests) - requests, ticks)
        self.assertEqual((m.r8(STATE), m.r8(SCAN), m.r8(SCAN + 1)), (5, 1, 2))
        self.assertEqual(m.timer_configuration(), TIM1_EXPECTED)
        self.assertEqual(m.timer_writes, timer)
        if session_sentinels:
            self.assertEqual(bytes(m.uc.mem_read(SESSION, 16)), b'\xA5' * 16)
        # In steady Analog, each intended LOW/HIGH is six or seven timer ticks.
        edge = [i for i in range(1, len(trace)) if trace[i] != trace[i-1]]
        runs = Counter(b-a for a, b in zip(edge, edge[1:]))
        self.assertTrue(set(runs) <= {6, 7}, runs)
        return (bytes(trace), m.gpio_writes, m.timer_writes,
                bytes(m.uc.mem_read(DIGITAL, 10)), runs)

    def test_twenty_seconds_active_analog_and_rtos_tick_wrap_are_parent_exact(self):
        rows = []
        for version, data in self.images:
            m = Machine(data)
            m.call(CARRIER_INIT)
            m.uc.mem_write(SESSION, b'\xA5' * 16)
            rows.append(self.assert_running(m, 200_000, tick_seed=0xFFFFFF00,
                                            session_sentinels=True))
            print(version, '200000 TIM2 ticks / 20.2 s modeled; no extra gap;',
                  'half-cycle runs', dict(rows[-1][-1]), flush=True)
        self.assertEqual(*rows)

    def test_composed_startup_then_cable_home_scan_reentry(self):
        rows = []
        for version, data in self.images:
            m = Machine(data, enabled=0, state=2)
            m.uc.mem_write(SESSION, b'\xA5' * 16)
            # Execute the actual complete composed initializer, not a simulated
            # zero of the new allocation. SysInit/RTOS logging remain fixtures.
            m.initialize(data)
            if version == 'PN2.34':
                self.assertEqual(bytes(m.uc.mem_read(SESSION, 16)), bytes(16))
            m.call(CARRIER_INIT)
            for visit in range(8):
                m.w8(STATE + 1, 4)
                m.press(4)  # Home OK -> Cable Test entry.
                self.assertEqual(m.r8(STATE), 4)
                m.press(2)  # A mode key at the selector.
                m.press(0)  # Selector Back -> Home; session invalidation runs.
                self.assertEqual(m.r8(STATE), 2)
                m.w8(STATE + 1, 5)
                m.press(4)  # Home OK -> SCAN.
                self.assertEqual((m.r8(STATE), m.r8(SCAN)), (5, 0))
                if m.r8(SCAN + 1) != 2:
                    m.press(2)
                m.press(4)
                self.assert_running(m, 400)
                m.press(5)  # Real Right: next TIM2 must repair carrier cache.
                self.assert_running(m, 400)
                m.press(0)
                paused = phase_read(m)
                for _ in range(50):
                    m.call(IRQ)
                self.assertEqual(phase_read(m), paused)
                self.assertEqual(m.pin_modes(), (3, 3))
                m.press(0)
                self.assertEqual(m.r8(STATE), 2)
            rows.append((m.gpio_writes, m.timer_writes,
                         bytes(m.uc.mem_read(SCAN, 16))))
            print(version, '8 real Cable/Home/SCAN/Right/pause cycles pass', flush=True)
        self.assertEqual(*rows)

    def test_oracle_rejects_a_simulated_missing_timer_request(self):
        # Detector negative control, not reproduction of the hardware fault.
        m = Machine(self.images[-1][1])
        m.call(CARRIER_INIT)
        m.pending = 0
        with self.assertRaises(AssertionError):
            self.assert_running(m, 20)


if __name__ == '__main__':
    unittest.main(verbosity=2)
