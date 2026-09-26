"""Diagnostic assertions against the shipped PN2.33 bytes; no firmware writes.

Run from any directory: python docs/debug/2026-09-26-rx-tx/tx_cable_contracts.py -v
Expected to fail while the described faults remain; electrical fixtures are
explicit models, not measurements from hardware.
"""
from pathlib import Path
import hashlib
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
SDK = ROOT / 'LPM-10A' / 'Firmware File' / 'sdk'
sys.path.insert(0, str(SDK))

from thai.engine import Scene
from test_cable_check import Rig, switch_end, SWITCH, RX, ADC, DELAY
import cable_check as CC

DATA = (SDK.parent / 'LPM-10A-TX_PN2.33-cable-safe.bin').read_bytes()
assert hashlib.sha256(DATA).hexdigest() == '84f9fb991a5bf43f0e29d978277ebe76baa58ff21714b430c1b6cef040751e91'


class ReleasedCableContracts(unittest.TestCase):
    def test_switch_cross_pair_short_must_not_report_pass(self):
        r = Rig(DATA, SWITCH, switch_end(shorts=[{0, 2}]))
        self.assertNotEqual(r.led, 2, f'cross-pair short 1-3: status={r.status}, LED={r.led}, beeps={r.beeps}')

    def queued_start(self, *, count=2, claim_second=False, home=False, keep_rx=False):
        s = Scene(image=DATA, lang=1)
        calls, routines = [], []
        s.at[ADC] = lambda uc: (calls.append(1), s.ret(4095), True)[2]
        s.at[DELAY] = lambda uc: (s.ret(0), True)[1]
        s.at[0x0800CB68] = lambda uc: (routines.append('Switch'), False)[1]
        s.at[0x0800C4E0] = lambda uc: (routines.append('RX unit'), False)[1]
        s.w8(CC.MODE, RX | 0x10)
        s.set_state(4)
        s.dispatch(0x10)
        s.drain()
        # The actual COUNT-task OK handler enqueues 0x11 while GUI is delayed.
        s.w8(0x20003200, 2)
        for index in range(count):
            if claim_second and index == 1:
                s.w8(CC.BUSY, 1)
            s.call(0x0800C3FC, 0x20003200)
        s.w8(CC.BUSY, 0)
        pending = list(s.msgs)
        self.assertEqual([mid for mid, payload in pending], [0x11] * (1 if claim_second else count))
        # The event-task Back action runs before the GUI consumes that request.
        s.w8(0x20003210, 0, 3)
        s.call(0x080149FC, 0x20003210)
        self.assertEqual(s.uc.mem_read(CC.MODE, 1)[0], 0)
        self.assertEqual(s.uc.mem_read(0x2000013C, 1)[0], 4)
        if home:
            s.call(0x080149FC, 0x20003210)
            self.assertEqual(s.uc.mem_read(0x2000013C, 1)[0], 2)
            # Isolate whether these two stale requests can measure at Home;
            # rendering unrelated pending navigation messages is outside this probe.
            s.msgs[:] = pending
        if keep_rx:
            s.w8(CC.MODE, RX)
        s.drain()
        return len(calls), routines, s.uc.mem_read(CC.MODE, 1)[0]

    def test_two_old_starts_must_not_run_after_back_to_mode_selector(self):
        reads, routines, mode = self.queued_start()
        self.assertEqual(reads, 0, f'canceled RX-unit starts performed {reads} ADC reads in {routines}; mode={mode:#x}')

    def test_control_one_old_start_does_not_measure(self):
        self.assertEqual(self.queued_start(count=1)[:2], (0, []))

    def test_control_no_pending_start_keeps_selector_after_back(self):
        self.assertEqual(self.queued_start(count=0), (0, [], 0))

    def test_one_old_start_must_not_rearm_selector_after_back(self):
        reads, routines, mode = self.queued_start(count=1)
        self.assertEqual(mode, 0, f'canceled RX-unit Start changed selector mode from 0 to {mode:#x}')

    def test_probe_H1_claim_busy_before_second_request_suppresses_duplicate(self):
        self.assertEqual(self.queued_start(claim_second=True)[:2], (0, []))

    def test_probe_H2_leaving_screen_discards_both_old_requests(self):
        self.assertEqual(self.queued_start(home=True)[:2], (0, []))

    def test_probe_H3_preserving_rx_selector_mode_changes_executed_routine(self):
        self.assertEqual(self.queued_start(keep_rx=True), (792, ['RX unit'], 0x11))


if __name__ == '__main__':
    unittest.main()
