"""Broad TX candidate checks, including actual battery gates and save callers."""
from pathlib import Path
import struct

from unicorn import UcError, UC_ERR_WRITE_UNMAPPED
from audit_flash_length import Machine, FLAGS
import test_portflash
from audit_fixes import PATCHES
from build import AUDIT_OUT
from lpm10a.thumb import assemble
import patches


class Audit(test_portflash.PortFlash):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.portflash_data = cls.data
        cls.portflash_end = cls.img.cave_ptr
        for p in patches.REGISTRY:
            if p.pid in PATCHES:
                p(cls.img)
        cls.img.finalize()
        cls.data = bytes(cls.img.data)

    def test_candidate_matches_disk(self):
        self.assertEqual(Path(AUDIT_OUT).read_bytes(), self.data)

    def test_only_declared_changes_from_released_roadmap(self):
        self.assertEqual(len(self.portflash_data), len(self.data))
        allowed = set(range(0x24, 0x2C))
        for addr, size in ((0x0800E6BA, 4), (0x0801BD7C, 4), (0x0800F94E, 4),
                           (0x0800FE3A, 4), (0x08016690, 4),
                           (0x08011660, 8), (0x08012E6C, 8),
                           (self.portflash_end, self.img.cave_ptr - self.portflash_end)):
            allowed.update(range(self.img.f(addr), self.img.f(addr) + size))
        changed = {i for i, (a, b) in enumerate(zip(self.portflash_data, self.data)) if a != b}
        self.assertTrue(changed <= allowed, sorted(changed - allowed))
        self.assertEqual(self.img.read(0x08011660, 8), b'PN 2.11\0')
        self.assertEqual(self.img.read(0x08012E6C, 8), b'PN 2.11\0')

    def test_battery_monitor_is_not_suppressed_by_flash(self):
        for buf, expect in ((self.previous, False), (self.data, True)):
            m = Machine(buf, 6)
            m.w8(FLAGS + 1, 2)
            for _ in range(1000):
                m.call(0x0801BC70)
            pending = int.from_bytes(m.uc.mem_read(self.img.events['state'], 4), 'little')
            self.assertEqual(bool(pending & (1 << 9)), expect)
            calls = []
            m.handlers[0x080107C0] = lambda machine: machine.ret(10)
            m.handlers[0x08010918] = lambda machine: machine.ret(0)
            m.handlers[0x080108F8] = lambda machine: (calls.append(1), machine.ret(3000))
            m.handlers[0x0800E834] = lambda machine: machine.ret()
            m.w8(0x2000003D, 255)
            for sample in range(3):
                if expect:
                    m.call(0x0800E6B0, until=0x0800E766)
                else:
                    m.call(0x0800E6B0)
                self.assertEqual(m.r8(0x2000003D), 30 if expect and sample == 2 else 255)
            self.assertEqual(len(calls), 3 if expect else 0)

    def test_measurement_setup_and_length_still_suppress_battery_gui(self):
        for state, flag, value in ((6, 1, 1), (7, 0, 1), (9, 1, 1), (5, 1, 0), (2, 1, 0)):
            m = self.machine(state)
            m.w8(FLAGS + flag, value)
            self.assertEqual(m.call(self.img.battery_busy_guard), m.call(0x080130A8))

    def test_original_settings_save_faults_on_null_allocation(self):
        m = Machine(self.previous, 2)
        m.handlers[0x0801C388] = lambda machine: machine.ret(0)
        with self.assertRaises(UcError) as caught:
            m.call(0x0800FF74)
        self.assertEqual(caught.exception.errno, UC_ERR_WRITE_UNMAPPED)

    def test_all_settings_callers_use_checked_writer_without_heap(self):
        for site in (0x0800F94E, 0x0800FE3A, 0x08016690):
            self.assertEqual(self.img.read(site, 4), assemble(site, f'bl {self.img.autosave["save"]}'))
            m = self.machine(2)
            calls = []
            m.uc.mem_write(0x20000C78, bytes(range(200)))
            for addr, name in ((0x0801C844, 'suspend'), (0x080156FC, 'unlock'),
                               (0x08015690, 'lock'), (0x0801D01C, 'resume')):
                m.handlers[addr] = lambda machine, n=name: (calls.append(n), machine.ret())
            m.handlers[0x0801C388] = lambda machine: self.fail('save must not allocate')
            def erase(machine):
                machine.uc.mem_write(machine.arg(0), bytes([255]) * 204)
                machine.ret(6)
            def program(machine):
                machine.uc.mem_write(machine.arg(0), struct.pack('<I', machine.arg(1)))
                machine.ret(6)
            m.handlers[0x080155EC], m.handlers[0x080156A4] = erase, program
            self.assertEqual(m.call(site, until=site + 4), 1)
            self.assertEqual(bytes(m.uc.mem_read(0x0807F800, 204)), bytes(range(200)) + bytes(4))
            self.assertEqual(calls, ['suspend', 'unlock', 'lock', 'resume'])


if __name__ == '__main__':
    import unittest
    unittest.main()
