"""Execute PN 2.13 carrier initialization and GPIO gating without gate mocks.

This closes one gap in test_scan_sync: its carrier entry points are mocked.
Here the stock GPIO_Init, TIM1 configuration, and gate routines execute as
ARM instructions against mapped peripheral registers. The model does not
oscillate a timer, model an analog front end, or prove a signal at the jack.
The artifact hash pins this regression to the image reported not working.
"""
import hashlib
from pathlib import Path
import unittest

from unicorn import UC_HOOK_MEM_WRITE

from verify_scan import ScanMachine, SCAN, STATE, DIGITAL, DISPATCH, IRQ


ARTIFACT = Path(__file__).resolve().parent.parent / 'experimental' / 'LPM-10A-TX_PN2.13-sync.bin'
ARTIFACT_SHA256 = '79ea4157e86e3a6613cb603d7e34e6b61e4f949844095b583bd4ff4f88da1fbd'
CARRIER_INIT, CARRIER_OFF, CARRIER_ON = 0x0801A664, 0x0801A6B0, 0x0801A6EC
MODE_KEY, ENABLE, BACK = 0x0801458C, 0x08014498, 0x0801456C
PA_CRH, PB_CRH, TIM1 = 0x40010804, 0x40010C04, 0x40012C00
EXT_STATE = 0x2000F138
TIM1_EXPECTED = {0x00: 0x81, 0x04: 0x100, 0x18: 0x61, 0x20: 0x05,
                 0x28: 0, 0x2C: 0x13C, 0x34: 0x9E, 0x44: 0x8000}


def requested_wave(mode, tick):
    if mode == 1:
        return (0xB6B6 >> (15 - (tick % 800) // 50)) & 1
    if mode == 2:
        return (tick // 6) & 1
    if mode == 3:
        chip = (tick * 808 // 40025) % 32
        return (0x1F25EB11 >> (31 - chip)) & 1
    if mode == 4:
        return int(tick % 4950 < 990)
    raise ValueError(mode)


class RealCarrierMachine(ScanMachine):
    """Keep RTOS mocks, but execute the actual carrier and GPIO functions."""
    def __init__(self, data, mode=1, enabled=1, state=5):
        super().__init__(data, mode, enabled, state)
        self.gpio_writes, self.timer_writes = [], []
        self.uc.hook_add(UC_HOOK_MEM_WRITE, self.write_hook)

    def hook(self, uc, addr, size, user):
        if addr in (CARRIER_OFF, CARRIER_ON):
            # Deliberately do not call ScanMachine.hook here: it returns
            # immediately and substitutes the requested carrier state.
            self.instructions += 1
            self.calls[addr] += 1
        else:
            super().hook(uc, addr, size, user)

    def write_hook(self, uc, access, addr, size, value, user):
        if addr in (PA_CRH, PB_CRH):
            self.gpio_writes.append((addr, size, value))
        if TIM1 <= addr < TIM1 + 0x48:
            self.timer_writes.append((addr, size, value))

    def pin_modes(self):
        return self.r32(PA_CRH) & 0xF, (self.r32(PB_CRH) >> 20) & 0xF

    def carrier_pins_selected(self):
        modes = self.pin_modes()
        if modes == (0xB, 0xB):
            return 1                    # both pins select alternate function
        if modes == (0x3, 0x3):
            return 0                    # both pins select GPIO output
        raise AssertionError(f'inconsistent carrier GPIO modes: {modes!r}')

    def timer_configuration(self):
        return {offset: self.r32(TIM1 + offset) for offset in TIM1_EXPECTED}

    def physical_ticks(self, count, entry=DISPATCH):
        # "Physical" means peripheral register programming, not a physical
        # waveform: Unicorn neither runs the timer nor simulates the board.
        states = []
        for _ in range(count):
            self.call(entry)
            states.append(self.carrier_pins_selected())
        return states


class ScanHardwareRegisters(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = ARTIFACT.read_bytes()
        actual = hashlib.sha256(cls.data).hexdigest()
        if actual != ARTIFACT_SHA256:
            raise AssertionError(f'PN 2.13 artifact changed: {actual}')

    def machine(self, mode=1, enabled=1, state=5):
        m = RealCarrierMachine(self.data, mode, enabled, state)
        # Nonzero neighbours catch accidental whole-register replacement.
        m.w32(PA_CRH, 0x87654321)
        m.w32(PB_CRH, 0x12345678)
        m.call(CARRIER_INIT)
        return m

    def assert_timer(self, m):
        self.assertEqual(m.timer_configuration(), TIM1_EXPECTED)

    def test_actual_carrier_init_sets_timer_and_two_pins(self):
        m = self.machine()
        self.assert_timer(m)
        self.assertEqual(m.pin_modes(), (3, 3))
        self.assertGreater(len(m.timer_writes), 0)
        self.assertGreater(len(m.gpio_writes), 0)
        self.assertEqual(m.r32(PA_CRH) & ~0xF, 0x87654320)
        # Initialization also configures PB12, as the stock function does.
        self.assertEqual(m.r32(PB_CRH) & ~0x00FF0000,
                         0x12345678 & ~0x00FF0000)

    def test_all_modes_program_real_gpio_for_each_requested_tick(self):
        for mode in (1, 2, 3, 4):
            with self.subTest(mode=mode):
                m = self.machine(mode)
                before_timer = list(m.timer_writes)
                pa_other = m.r32(PA_CRH) & ~0xF
                pb_other = m.r32(PB_CRH) & ~(0xF << 20)
                # Two complete diagnostic pulses and multiple Sync32 frames.
                expected = [requested_wave(mode, t) for t in range(10001)]
                observed = m.physical_ticks(10001)
                self.assertEqual(m.requests, expected)
                self.assertEqual(observed, expected)
                self.assertEqual(set(observed), {0, 1})
                self.assertGreater(m.calls[CARRIER_ON], 0)
                self.assertGreater(m.calls[CARRIER_OFF], 0)
                self.assertEqual(m.r32(PA_CRH) & ~0xF, pa_other)
                self.assertEqual(m.r32(PB_CRH) & ~(0xF << 20), pb_other)
                self.assertEqual(m.timer_writes, before_timer)
                self.assert_timer(m)

    def test_real_enable_and_mode_keys_reach_new_modes_through_irq(self):
        m = self.machine(mode=0, enabled=0)
        m.call(ENABLE, 1)
        # The first interrupt initializes the shipped default Digital mode.
        self.assertEqual(m.physical_ticks(1, IRQ), [1])
        self.assertEqual(m.r8(SCAN + 1), 1)
        for mode in (2, 3, 4):
            m.call(MODE_KEY)
            self.assertEqual(m.r8(SCAN + 1), mode)
            self.assertEqual(m.r32(EXT_STATE), 0)
            start = len(m.requests)
            expected = [requested_wave(mode, t) for t in range(1600)]
            self.assertEqual(m.physical_ticks(1600, IRQ), expected)
            self.assertEqual(m.requests[start:], expected)
            self.assert_timer(m)

    def test_pause_resume_and_exit_drive_pins_in_all_modes(self):
        # Exercise pausing both carrier states, including Sync32's initial
        # silence and the diagnostic pulse's 100 ms nominal active interval.
        cases = ((1, 17), (1, 67), (2, 3), (2, 9),
                 (3, 17), (3, 160), (4, 100), (4, 1200))
        for mode, count in cases:
            with self.subTest(mode=mode, count=count):
                m = self.machine(mode)
                m.physical_ticks(count)
                m.call(BACK)
                self.assertEqual(m.r8(SCAN), 0)
                self.assertEqual(m.r8(STATE), 5)
                self.assertEqual(m.pin_modes(), (3, 3))
                before = (m.r32(EXT_STATE), bytes(m.uc.mem_read(DIGITAL, 10)),
                          len(m.requests), len(m.gpio_writes))
                self.assertEqual(m.physical_ticks(20, IRQ), [0] * 20)
                self.assertEqual((m.r32(EXT_STATE), bytes(m.uc.mem_read(DIGITAL, 10)),
                                  len(m.requests), len(m.gpio_writes)), before)
                m.call(ENABLE, 1)
                self.assertEqual(m.physical_ticks(1, IRQ),
                                 [requested_wave(mode, count)])
                self.assertEqual(m.carrier_pins_selected(), m.requests[-1])
                m.call(BACK)
                m.call(BACK)
                self.assertEqual(m.r8(STATE), 2)
                self.assertEqual(m.pin_modes(), (3, 3))
                self.assert_timer(m)

    def test_inactive_or_pending_guards_do_not_reprogram_gpio(self):
        for mode in (3, 4):
            for enabled, state, pending in ((0, 5, 1), (1, 2, 1), (1, 5, 0)):
                with self.subTest(mode=mode, enabled=enabled, state=state, pending=pending):
                    m = self.machine(mode, enabled, state)
                    m.pending = pending
                    m.w32(EXT_STATE, 1234)
                    before = list(m.gpio_writes), list(m.timer_writes)
                    self.assertEqual(m.physical_ticks(20, IRQ), [0] * 20)
                    self.assertEqual(m.r32(EXT_STATE), 1234)
                    self.assertEqual(m.requests, [])
                    self.assertEqual((m.gpio_writes, m.timer_writes), before)


if __name__ == '__main__':
    unittest.main()
