"""Execute the QC clock/counter helper with physical elapsed-time stimuli.

The clock register values and task resumption are modeled, while all capture,
pending-tick correction, duration arithmetic and normalization run as Thumb.
"""
import contextlib
import io
import random
import struct
import unittest

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE, UC_HOOK_MEM_READ
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3,
                               UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
                               UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11,
                               UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_SP, UC_ARM_REG_PRIMASK)
from lpm10a.image import PatchError
import qc_gate_clock as G


STOP, STACK, DELAY = 0x00100000, 0x2000DFC0, 0x0801C75C
SAVED = (UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
         UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11)


class Machine:
    def __init__(self, image):
        self.u = u = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
        for address, size in ((0x08000000, 0x80000), (0x20000000, 0x20000),
                              (0x40000000, 0x30000), (0xE000E000, 0x1000), (STOP, 0x1000)):
            u.mem_map(address, size)
        u.mem_write(0x0800A000, bytes(image.data[image.payload_off:]))
        self.w32(G.LOAD, G.CYCLES_PER_TICK-1)
        self.calls, self.masked_runs, self.current_masked = [], [], 0
        self.on_delay = lambda: None

        def code(uc, address, size, user):
            if uc.reg_read(UC_ARM_REG_PRIMASK):
                self.current_masked += 1
            elif self.current_masked:
                self.masked_runs.append(self.current_masked)
                self.current_masked = 0
            if address == DELAY:
                self.calls.append((uc.reg_read(UC_ARM_REG_R0), uc.reg_read(UC_ARM_REG_PRIMASK)))
                self.on_delay()
                for register in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3):
                    uc.reg_write(register, 0xBAD0)
                uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
            elif address == STOP:
                uc.emu_stop()
        u.hook_add(UC_HOOK_CODE, code)

    def w32(self, address, value):
        self.u.mem_write(address, struct.pack('<I', value & 0xFFFFFFFF))

    def clock(self, cycles, pending=False):
        tick, phase = divmod(cycles, G.CYCLES_PER_TICK)
        self.w32(G.TICK, tick-int(pending))
        self.w32(G.VAL, G.CYCLES_PER_TICK-1-phase)
        self.w32(G.ICSR, (1 << 26) if pending else 0)

    def call(self, address, r0=0, r1=0, mask=0):
        expected = [0xACBD0000+i for i in range(len(SAVED))]
        for register, value in zip(SAVED, expected):
            self.u.reg_write(register, value)
        self.u.reg_write(UC_ARM_REG_R0, r0)
        self.u.reg_write(UC_ARM_REG_R1, r1)
        self.u.reg_write(UC_ARM_REG_SP, STACK)
        self.u.reg_write(UC_ARM_REG_LR, STOP | 1)
        self.u.reg_write(UC_ARM_REG_PRIMASK, mask)
        self.u.emu_start(address | 1, STOP, count=10_000)
        assert self.u.reg_read(UC_ARM_REG_PC) == STOP, 'helper did not return within bounded instructions'
        assert self.u.reg_read(UC_ARM_REG_SP) == STACK, 'helper leaked stack'
        assert [self.u.reg_read(r) for r in SAVED] == expected, 'helper broke callee-saved ABI'
        assert self.u.reg_read(UC_ARM_REG_PRIMASK) == mask, 'helper leaked interrupt mask'
        return self.u.reg_read(UC_ARM_REG_R0)

    def sample(self, start, elapsed, count, *, start_pending=False, end_pending=False, overflow=False):
        self.clock(start, start_pending)
        self.w32(G.TIMER+16, 1)  # A previous sample's stale UIF must be cleared.
        def resume():
            self.clock(start+elapsed, end_pending)
            self.u.mem_write(G.TIMER+36, struct.pack('<H', count))
            self.w32(G.TIMER+16, int(overflow))
        self.on_delay = resume
        return self.call(G.MEASURE)


class QCGateClock(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import length_integrity
        with contextlib.redirect_stdout(io.StringIO()):
            cls.img = length_integrity.build_candidate()
            cls.before = bytes(cls.img.data)
            cls.info = G.install(cls.img)
            cls.img.finalize()

    def machine(self):
        return Machine(self.img)

    def test_same_frequency_at_varying_wake_phase_has_same_normalized_count(self):
        m = self.machine()
        for duration in (9000, 9100, 9500, 10000, 10300, 11000, 15000, 20000, 50000):
            with self.subTest(duration=duration):
                self.assertEqual(m.sample(123_456, duration*144, duration//10), 1000)
        self.assertEqual(m.calls, [(10, 0)]*9)
        self.assertLessEqual(max(m.masked_runs), 55, 'captures must stay short and exclude division/wait')

    def test_normalization_matches_exact_integer_oracle_without_large_product_overflow(self):
        m = self.machine()
        rng = random.Random(225)
        vectors = [(raw, duration) for raw in (0, 1, 7, 900, 1000, 32767, 65534)
                   for duration in (G.MIN_CYCLES, G.NOMINAL_CYCLES, G.MAX_CYCLES)]
        vectors += [(rng.randrange(65535), rng.randrange(G.MIN_CYCLES, G.MAX_CYCLES+1))
                    for _ in range(250)]
        for raw, duration in vectors:
            expected = (2*raw*G.NOMINAL_CYCLES+duration)//(2*duration)
            expected = min(expected, 65535)
            with self.subTest(raw=raw, duration=duration):
                self.assertEqual(m.call(self.info['normalize'], raw, duration), expected)

    def test_normalization_rejects_invalid_gate_and_unrepresentable_count(self):
        m = self.machine()
        for raw, duration in ((1000, 0), (1000, G.MIN_CYCLES-1), (1000, G.MAX_CYCLES+1),
                              (65535, G.NOMINAL_CYCLES), (65536, G.NOMINAL_CYCLES),
                              (65534, G.MIN_CYCLES)):
            with self.subTest(raw=raw, duration=duration):
                self.assertEqual(m.call(self.info['normalize'], raw, duration), 65535)

    def test_pending_ticks_at_start_and_end_are_compensated_once(self):
        m = self.machine()
        for start_pending in (False, True):
            for end_pending in (False, True):
                with self.subTest(start_pending=start_pending, end_pending=end_pending):
                    self.assertEqual(m.sample(25*144000+333, 11*144000, 1100,
                                              start_pending=start_pending, end_pending=end_pending), 1000)

    def test_full_32_bit_tick_wrap_and_subtick_difference(self):
        m = self.machine()
        start = 0xFFFFFFFC*G.CYCLES_PER_TICK+G.CYCLES_PER_TICK-144
        self.assertEqual(m.sample(start, 9500*144, 950), 1000)

    def test_snapshot_handles_reload_before_or_after_icsr_read(self):
        cases = [(1000, 999, 0, 19), (1000, 999, 1 << 26, 20),
                 (0, 143999, 1 << 26, 20), (0, 143999, 0, 20),
                 (143999, 143998, 1 << 26, 20)]
        for first, second, pending, expected_tick in cases:
            with self.subTest(first=first, second=second, pending=pending):
                m = self.machine()
                m.w32(G.TICK, 19)
                m.w32(G.ICSR, pending)
                vals = iter((first, second))
                def read(uc, access, address, size, value, user):
                    if address == G.VAL:
                        m.w32(G.VAL, next(vals))
                m.u.hook_add(UC_HOOK_MEM_READ, read)
                self.assertEqual(m.call(self.info['snapshot'], mask=1), expected_tick)
                self.assertEqual(m.u.reg_read(UC_ARM_REG_R1), second)

    def test_snapshot_pending_tick_wraps_to_zero(self):
        m = self.machine()
        m.w32(G.TICK, 0xFFFFFFFF)
        m.w32(G.VAL, 143900)
        m.w32(G.ICSR, 1 << 26)
        self.assertEqual(m.call(self.info['snapshot'], mask=1), 0)

    def test_overflowed_counter_is_invalid_even_if_wrapped_count_looks_connected(self):
        m = self.machine()
        self.assertEqual(m.sample(0, G.NOMINAL_CYCLES, 900, overflow=True), 65535)
        self.assertEqual(m.sample(0, G.NOMINAL_CYCLES, 900), 900)

    def test_wrong_reload_never_enters_delay_and_restores_mask(self):
        m = self.machine()
        m.w32(G.LOAD, 71999)
        self.assertEqual(m.call(G.MEASURE), 65535)
        self.assertEqual(m.calls, [])

    def test_changed_reload_during_wait_is_invalid(self):
        m = self.machine()
        m.clock(0)
        def resume():
            m.clock(G.NOMINAL_CYCLES)
            m.w32(G.LOAD, 71999)
        m.on_delay = resume
        self.assertEqual(m.call(G.MEASURE), 65535)
        self.assertEqual(m.calls, [(10, 0)])

    def test_invalid_val_and_masked_caller_never_yield(self):
        m = self.machine()
        m.w32(G.VAL, G.CYCLES_PER_TICK)
        self.assertEqual(m.call(G.MEASURE), 65535)
        self.assertEqual(m.call(G.MEASURE, mask=1), 65535)
        self.assertEqual(m.calls, [])

    def test_long_or_short_wait_cannot_alias_into_a_good_gate(self):
        m = self.machine()
        for elapsed in (0, G.MIN_CYCLES-1, G.MAX_CYCLES+1,
                        0x100000000, 50_000*G.CYCLES_PER_TICK):
            with self.subTest(elapsed=elapsed):
                self.assertEqual(m.sample(0, elapsed, 900), 65535)

    def test_native_patch_changes_only_four_original_sampler_bytes(self):
        address = self.img.f(G.MEASURE)
        self.assertNotEqual(self.before[address:address+4], bytes(self.img.data[address:address+4]))
        self.assertEqual(self.before[address+4:address+len(G.EXPECTED_MEASURE)],
                         bytes(self.img.data[address+4:address+len(G.EXPECTED_MEASURE)]))
        self.assertEqual(self.img.read(G.SYSTICK_SETUP, len(G.EXPECTED_SYSTICK)), G.EXPECTED_SYSTICK)

    def test_duplicate_install_cannot_silently_repatch_unknown_sampler(self):
        with self.assertRaises(PatchError):
            G.install(self.img)


if __name__ == '__main__':
    unittest.main()
