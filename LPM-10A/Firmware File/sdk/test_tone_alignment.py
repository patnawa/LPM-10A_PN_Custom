"""Experimental Analog alignment: real Thumb, GPIO registers and bounded image changes.

Peripheral register writes are observed; no electrical amplitude or receiver
sensitivity is inferred from this CPU model. The shipping default stays PN2.26.
"""
from collections import Counter
import contextlib
import copy
import hashlib
import io
import struct
import unittest

from unicorn import UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_PRIMASK

from lpm10a.image import PatchError
from test_scan_recovery import RecoveryMachine
from test_scan_hardware import (BACK, CARRIER_INIT, ENABLE, MODE_KEY,
                               PA_CRH, PB_CRH, TIM1_EXPECTED)
from verify_scan import DIGITAL, DISPATCH, IRQ, SCAN, STATE, digital_expected


ANALOG_ENTRY = 0x08014344
PHASE = 0x200000DE
LABEL = 0x08068916
PARENT_HASH = '575a410fea87da9bc4ecb273d1fd931712bb8a2d911d771c55332dc2a2c4e8b2'


def phase_read(machine):
    return struct.unpack('<H', machine.uc.mem_read(PHASE, 2))[0]


def phase_write(machine, value):
    machine.uc.mem_write(PHASE, struct.pack('<H', value))


def expected(seed, count):
    # Closed-form oracle is independent of the assembly's step/wrap branches.
    origin = seed if seed < 2000 else 0
    return [int((origin + 165 * index) % 2000 >= 1000)
            for index in range(1, count + 1)]


class ToneAlignment(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tone_alignment
        import tone_precision
        cls.candidate = tone_alignment
        with contextlib.redirect_stdout(io.StringIO()):
            cls.parent = tone_precision.build_candidate()
            cls.img = tone_alignment.build_candidate()
        cls.data = bytes(cls.img.data)

    def machine(self, mode=2, enabled=1, state=5, data=None):
        machine = RecoveryMachine(self.data if data is None else data,
                                  mode, enabled, state)
        machine.call(CARRIER_INIT)
        return machine

    def test_alignment_repeats_33_cycles_every_400_ticks_at_half_duty(self):
        m = self.machine()
        trace = m.physical_ticks(1200, IRQ)
        oracle = expected(0, 1200)
        mismatch = next((i for i, (a, b) in enumerate(zip(trace, oracle)) if a != b), None)
        self.assertIsNone(mismatch, f'first waveform mismatch at tick {mismatch}')
        self.assertEqual(trace[:400], trace[400:800])
        self.assertEqual(trace[:400], trace[800:1200])
        period = trace[:400]
        edges = [i for i in range(400) if period[i] != period[(i - 1) % 400]]
        runs = Counter((edges[(i + 1) % len(edges)] - edge) % 400
                       for i, edge in enumerate(edges))
        self.assertEqual(len(edges), 66)
        self.assertEqual(runs, {6: 62, 7: 4})
        self.assertEqual(sum(period), 200)
        self.assertEqual(phase_read(m), 0)
        self.assertAlmostEqual(33 / (400 * 101e-6), 816.8316831683169)
        self.assertEqual(m.timer_configuration(), TIM1_EXPECTED)

    def test_every_valid_phase_and_invalid_halfword_recover_without_legacy_state(self):
        m = self.machine()
        for seed in (*range(2000), 2000, 2001, 4095, 32767, 65535):
            phase_write(m, seed)
            m.w8(SCAN + 12, 255)  # Exercise actual GPIO path for every phase.
            m.w8(SCAN + 2, 0xA7)
            m.uc.mem_write(0x200000E0, b'\xDE\xAD')
            m.call(ANALOG_ENTRY)
            origin = seed if seed < 2000 else 0
            self.assertEqual(phase_read(m), (origin + 165) % 2000, seed)
            self.assertEqual(m.carrier_pins_selected(), expected(seed, 1)[0], seed)
            self.assertEqual(m.r8(SCAN + 2), 0xA7)
            self.assertEqual(bytes(m.uc.mem_read(0x200000E0, 2)), b'\xDE\xAD')

    def test_all_five_phase_residue_classes_have_same_period_and_duty(self):
        for seed in range(5):
            m = self.machine()
            phase_write(m, seed)
            trace = m.physical_ticks(400, IRQ)
            self.assertEqual(trace, expected(seed, 400))
            self.assertEqual(sum(trace), 200)
            self.assertEqual(sum(trace[i] != trace[i-1] for i in range(400)), 66)
            self.assertEqual(phase_read(m), seed)

    def test_disabled_direct_entry_does_not_advance_even_invalid_phase(self):
        for seed in (0, 998, 999, 1000, 1834, 1835, 1999, 65535):
            m = self.machine(enabled=0)
            phase_write(m, seed)
            for _ in range(3):
                m.call(ANALOG_ENTRY)
            self.assertEqual(phase_read(m), seed)
            self.assertEqual(m.requests, [])
            self.assertEqual(m.pin_modes(), (3, 3))
            self.assertEqual(m.timer_configuration(), TIM1_EXPECTED)

    def test_pause_resume_mode_switch_and_home_exit_preserve_cursor(self):
        for seed in (0, 834, 835, 999, 1000, 1834, 1835, 1999):
            m = self.machine()
            phase_write(m, seed)
            m.call(DISPATCH)
            paused = phase_read(m)
            m.call(BACK)
            m.physical_ticks(25, IRQ)
            self.assertEqual(phase_read(m), paused)
            self.assertEqual(m.r8(SCAN), 0)
            self.assertEqual(m.pin_modes(), (3, 3))
            m.call(ENABLE, 1)
            self.assertEqual(m.physical_ticks(1, IRQ), expected(paused, 1))
            saved = phase_read(m)
            m.call(MODE_KEY)
            self.assertEqual(m.r8(SCAN + 1), 1)
            self.assertEqual(m.physical_ticks(61, IRQ), [digital_expected(i) for i in range(61)])
            self.assertEqual(phase_read(m), saved)
            m.call(MODE_KEY)
            self.assertEqual(m.physical_ticks(1, IRQ), expected(saved, 1))
            m.call(BACK)
            m.call(BACK)
            self.assertEqual(m.r8(STATE), 2)
            saved = phase_read(m)
            m.physical_ticks(10, IRQ)
            self.assertEqual(phase_read(m), saved)

    def test_inactive_screen_unknown_mode_and_spurious_irq_leave_phase_untouched(self):
        for mode, enabled, state in ((2, 0, 5), (2, 1, 2), (2, 1, 6), (255, 1, 5)):
            m = self.machine(mode, enabled, state)
            phase_write(m, 1234)
            m.physical_ticks(20, IRQ)
            self.assertEqual(phase_read(m), 1234)
            self.assertEqual(m.requests, [])
        m = self.machine()
        phase_write(m, 1234)
        m.pending = 0
        m.physical_ticks(10, IRQ)
        self.assertEqual(phase_read(m), 1234)
        self.assertEqual(m.requests, [])

    def test_analog_only_ram_write_abi_and_interrupt_mask_contract(self):
        for mask in (0, 1):
            m = self.machine()
            m.uc.reg_write(UC_ARM_REG_PRIMASK, mask)
            writes = []
            m.uc.hook_add(UC_HOOK_MEM_WRITE,
                          lambda uc, access, address, size, value, user:
                          writes.append((address, size, value)))
            for _ in range(20):
                m.call(ANALOG_ENTRY)  # call also checks SP and every r4-r11.
            self.assertEqual(m.uc.reg_read(UC_ARM_REG_PRIMASK), mask)
            for address, size, value in writes:
                if address in (0x40010810, 0x40010814, 0x40010C10, 0x40010C14):
                    # Inherited OFF level/parity routine, after both CRH writes.
                    self.assertEqual(size, 4)
                    self.assertEqual(value, 0x100 if address < 0x40010C00 else 0x2000)
                    continue
                self.assertTrue((address, size) in ((PHASE, 2), (SCAN + 12, 1),
                                                  (PA_CRH, 4), (PB_CRH, 4))
                                or 0x2000DFC0 <= address < 0x2000E000,
                                (hex(address), size))
            self.assertEqual(m.timer_configuration(), TIM1_EXPECTED)

    def test_digital_default_and_explicit_mode_trace_and_shared_irq_clients_unchanged(self):
        for mode in (0, 1):
            old = self.machine(mode, data=bytes(self.parent.data))
            new = self.machine(mode)
            old_trace = old.physical_ticks(1601, IRQ)
            self.assertEqual(new.physical_ticks(1601, IRQ), old_trace)
            self.assertEqual(old_trace, [digital_expected(i) for i in range(1601)])
            self.assertEqual(new.gpio_writes, old.gpio_writes)
            self.assertEqual(new.timer_writes, old.timer_writes)
            self.assertEqual(new.calls, old.calls)
            self.assertEqual(bytes(new.uc.mem_read(DIGITAL, 10)),
                             bytes(old.uc.mem_read(DIGITAL, 10)))
        old = self.machine(data=bytes(self.parent.data))
        new = self.machine()
        old.physical_ticks(1001, IRQ)
        new.physical_ticks(1001, IRQ)
        for address in (0x080169A8, 0x0800F9CC, 0x080183CC):
            self.assertEqual(new.calls[address], old.calls[address], hex(address))

    def test_image_exact_parent_independent_allowlist_and_no_new_ram(self):
        old, new = bytes(self.parent.data), self.data
        self.assertEqual(hashlib.sha256(old).hexdigest(), PARENT_HASH)
        self.assertEqual(self.candidate.PARENT_SHA256, PARENT_HASH)
        self.assertEqual(self.parent.cave_ptr, 0x0806A558)
        self.assertEqual(self.img.cave_ptr, 0x0806A598)
        allowed = set(range(0x24, 0x2C))
        for address, size in ((ANALOG_ENTRY, 4), (LABEL, 14),
                              (0x08011660, 8), (0x08012E6C, 8),
                              (0x0806A558, 64)):
            start = self.parent.f(address)
            allowed.update(range(start, start + size))
        changed = {i for i, (a, b) in enumerate(zip(old, new)) if a != b}
        self.assertFalse(changed - allowed, sorted(changed - allowed))
        self.assertEqual(self.img.ram_allocs, self.parent.ram_allocs)
        self.assertEqual(self.img._ram_ptr, self.parent._ram_ptr)
        self.assertEqual(self.img.tone_alignment['phase_address'], PHASE)
        # Shared TIM2, Digital generator, gate, carrier and control code byte exact.
        for address, size in ((0x08014300, 0x44), (0x0801446C, 0x328),
                              (0x08016598, 0x6C), (0x08018370, 0x5C),
                              (0x0801A60C, 0x118), (0x0800F9CC, 0xFC)):
            self.assertEqual(self.img.read(address, size), self.parent.read(address, size))

    def test_container_label_versions_and_determinism(self):
        self.assertEqual(len(self.data), 401408)
        self.assertEqual(self.data[:0x24], bytes(self.parent.data[:0x24]))
        self.assertEqual(self.data[0x2C:0x1000], bytes(self.parent.data[0x2C:0x1000]))
        off, length, end = struct.unpack_from('<III', self.data, 0x20)
        self.assertEqual(off, 0x1000)
        self.assertEqual(end, off + length - 1)
        self.assertEqual(length + 0x0800A000, self.img.cave_ptr)
        self.assertFalse(any(self.data[end+1:]))
        self.assertEqual(self.img.read(LABEL, 14), b'Analog 817 Hz\0')
        for address in (0x08011660, 0x08012E6C):
            self.assertEqual(self.img.read(address, 8), b'PN2.27A\0')
        self.assertEqual(self.candidate.VERSION, 'PN2.27A')
        with contextlib.redirect_stdout(io.StringIO()):
            again = self.candidate.build_candidate()
        self.assertEqual(bytes(again.data), self.data)

    def test_non_parent_tamper_and_double_apply_rejected_without_mutation(self):
        for kind in ('previous-release', 'tamper', 'double-apply'):
            if kind == 'previous-release':
                import qc_display
                with contextlib.redirect_stdout(io.StringIO()):
                    im = qc_display.build_candidate()
            else:
                im = copy.deepcopy(self.img if kind == 'double-apply' else self.parent)
            if kind == 'tamper':
                im.data[im.f(ANALOG_ENTRY)] ^= 1
            def snapshot():
                return (bytes(im.data), im.cave_ptr, im.cave_end, im.payload_len,
                        im._ram_ptr, tuple(im.ram_allocs), tuple(im.log),
                        tuple(im.__dict__))
            before = snapshot()
            with self.assertRaisesRegex(PatchError, 'exact finalized PN2.27'):
                self.candidate.apply(im)
            self.assertEqual(snapshot(), before)


if __name__ == '__main__':
    unittest.main()
