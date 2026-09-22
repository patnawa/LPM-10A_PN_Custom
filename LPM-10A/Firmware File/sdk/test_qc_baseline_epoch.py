"""Normalized QC calibration must not silently reuse legacy timed counts."""
import contextlib
import io
import struct
import unittest
import random

from unicorn import UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_R4, UC_ARM_REG_SP, UC_ARM_REG_PC

from test_qc_continuity import Harness, BASE

SETTINGS, MARKER = 0x20000C78, 0x20000D3E


class QCBaselineEpoch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import length_integrity
        import qc_baseline_epoch
        with contextlib.redirect_stdout(io.StringIO()):
            cls.img = length_integrity.build_candidate()
            cls.parent_data = bytes(cls.img.finalize().data)
            qc_baseline_epoch.install(cls.img)
        cls.data = bytes(cls.img.finalize().data)

    def initialize(self, h):
        from test_qc_classic import QCClassic
        return QCClassic.initialize(self, h)

    def test_legacy_baseline_requires_explicit_init_before_auto_test(self):
        h = Harness(self.data)
        before = bytes(h.s.uc.mem_read(BASE, 16))
        h.s.w16(MARKER, 0)
        h.enter()
        self.assertEqual(h.read(self.img.qc['state']), 4)
        for _ in range(60):
            self.assertEqual(h.poll(), 0)
        self.assertEqual(bytes(h.s.uc.mem_read(BASE, 16)), before)

    def test_negative_control_parent_accepts_the_same_legacy_baseline(self):
        h = Harness(self.parent_data)
        h.s.w16(MARKER, 0)
        h.enter()
        self.assertEqual(h.read(self.img.qc['state']), 1)

    def test_thumb_crc_matches_reference_and_preserves_registers(self):
        import qc_baseline_epoch as E
        from test_qc_continuity import SAVED
        h = Harness(self.data)
        rng = random.Random(225)
        for values in (bytes(16), bytes([255]) * 16,
                       *[rng.randbytes(16) for _ in range(32)]):
            h.s.uc.mem_write(BASE, values)
            saved = [h.s.uc.reg_read(reg) for reg in SAVED]
            got = h.s.call(self.img.qc_baseline_epoch['checksum'], BASE)
            self.assertEqual(got, E.fingerprint(values))
            self.assertNotIn(got, (0, 65535))
            self.assertEqual([h.s.uc.reg_read(reg) for reg in SAVED], saved)

    def test_valid_marker_reuses_baseline_but_blank_changed_or_invalid_baseline_does_not(self):
        import qc_baseline_epoch as E
        for marker, valid, delta, expected in (
                (None, 1, 0, 1), (0, 1, 0, 4), (65535, 1, 0, 4),
                (None, 0, 0, 4), (None, 1, 1, 4)):
            h = Harness(self.data)
            checksum = E.fingerprint(bytes(h.s.uc.mem_read(BASE, 16)))
            h.s.w16(MARKER, checksum if marker is None else marker)
            if delta:
                h.s.w16(BASE + 10, 1000 + delta)
            # Stock entry always sets VALID=1. Set the invalid flag after
            # that entry, before the actual queued frame invokes QC reset.
            h.s.call(0x0800BA2C)
            h.s.w8(0x2000023D, valid)
            h.s.drain()
            self.assertEqual(h.read(self.img.qc['state']), expected)

    def test_successful_explicit_init_marks_and_resumes_then_survives_reentry(self):
        import qc_baseline_epoch as E
        h = Harness(self.data)
        h.s.w16(MARKER, 0)
        h.enter()
        h.values = [1100 + pin for pin in range(8)]
        self.assertEqual(self.initialize(h)[0], 0)
        baseline = struct.pack('<8H', *h.values)
        self.assertEqual(bytes(h.s.uc.mem_read(BASE, 16)), baseline)
        self.assertEqual(bytes(h.s.uc.mem_read(SETTINGS + 0x90, 16)), baseline)
        self.assertEqual(h.read(MARKER, 2), E.fingerprint(baseline))
        self.assertEqual(h.read(self.img.qc['state']), 1)
        h.press(0, 3)
        h.enter()
        self.assertEqual(h.read(self.img.qc['state']), 1)

    def test_failed_init_preserves_every_settings_byte_and_remains_unusable(self):
        h = Harness(self.data)
        h.s.w16(MARKER, 0)
        h.enter()
        baseline = bytes(h.s.uc.mem_read(BASE, 16))
        settings = bytes(h.s.uc.mem_read(SETTINGS, 0xC8))
        h.source = lambda pin, number: 1010 if number % 5 == 4 else 1000
        self.assertEqual(self.initialize(h), (1, [], []))
        self.assertEqual(bytes(h.s.uc.mem_read(BASE, 16)), baseline)
        self.assertEqual(bytes(h.s.uc.mem_read(SETTINGS, 0xC8)), settings)
        h.press(0, 3)
        h.enter()
        self.assertEqual(h.read(self.img.qc['state']), 4)

    def test_marker_and_baseline_are_coherent_before_stock_save_request(self):
        import qc_baseline_epoch as E
        import qc_calibration as C
        from test_qc_calibration import COMMAND, HANDLER, HOME_MESSAGE
        h = Harness(self.data)
        h.s.w16(MARKER, 0)
        h.enter()
        h.values = [1100 + pin for pin in range(8)]
        expected = struct.pack('<8H', *h.values)
        depth, writes, requests = [0], [], []
        def enter(uc):
            depth[0] += 1
            h.s.ret(0)
            return True
        def leave(uc):
            self.assertGreater(depth[0], 0)
            depth[0] -= 1
            h.s.ret(0)
            return True
        def write(uc, access, address, size, value, user):
            old = int.from_bytes(uc.mem_read(address, size), 'little')
            if old != value:
                self.assertGreater(depth[0], 0)
                self.assertEqual(len(h.reads), 40)
            writes.append((address, size, depth[0]))
        def home(uc):
            self.assertEqual(depth[0], 0)
            self.assertEqual(bytes(uc.mem_read(SETTINGS + 0x90, 16)), expected)
            self.assertEqual(h.read(MARKER, 2), E.fingerprint(expected))
            requests.append(h.s.arg(0))
            h.s.ret(0)
            return True
        h.s.at[C.ENTER_CRITICAL], h.s.at[C.EXIT_CRITICAL] = enter, leave
        h.s.at[HOME_MESSAGE] = home
        observer = h.s.uc.hook_add(UC_HOOK_MEM_WRITE, write,
                                  begin=SETTINGS + 0x90, end=MARKER + 1)
        try:
            h.s.w8(COMMAND, 0)
            self.assertEqual(h.s.call(HANDLER, COMMAND), 0)
        finally:
            h.s.uc.hook_del(observer)
        self.assertEqual(requests, [5])
        self.assertIn((MARKER, 2, 1), writes)
        self.assertEqual(depth[0], 0)

    def test_factory_defaults_change_only_marker_beyond_parent_changes(self):
        from thai.engine import Scene
        results = []
        for data in (self.parent_data, self.data):
            s = Scene(image=data)
            s.uc.mem_write(SETTINGS, bytes([0xA5]) * 0xCC)
            def skip(uc):
                s.ret(0)
                return True
            s.at[0x080131BC] = skip
            s.at[0x080119B0] = skip
            s.call(0x0801958C)
            results.append(bytes(s.uc.mem_read(SETTINGS, 0xCC)))
        self.assertEqual([i for i in range(0xCC) if results[0][i] != results[1][i]],
                         [0xC6, 0xC7])
        self.assertEqual(results[1][0xC6:0xC8], bytes(2))

    def test_actual_network_storage_stops_before_zero_and_marker_padding(self):
        h = Harness(self.data)
        h.s.uc.mem_write(SETTINGS, bytes([0xA5]) * 0xCC)
        network = bytes(range(0x1C))
        h.s.uc.mem_write(0x20003000, network)
        def netcfg(uc):
            h.s.ret(0x20003000)
            return True
        h.s.at[0x080131B4] = netcfg
        h.s.call(0x080119B0)
        expected = bytes([0xA5]) * 0xA9 + network + bytes([0xA5]) * 7
        self.assertEqual(bytes(h.s.uc.mem_read(SETTINGS, 0xCC)), expected)

    def test_canceled_init_preserves_valid_marker_and_prior_baseline(self):
        import qc_baseline_epoch as E
        from test_qc_calibration import COMMAND, HANDLER, SAVE
        h = Harness(self.data)
        baseline = bytes(h.s.uc.mem_read(BASE, 16))
        h.s.w16(MARKER, E.fingerprint(baseline))
        h.enter()
        settings = bytes(h.s.uc.mem_read(SETTINGS, 0xC8))
        h.during_sample = lambda fixture: fixture.s.w8(0x2000013C, 2)
        def unexpected_save(uc):
            self.fail('Canceled calibration reached persistent settings save')
        h.s.at[SAVE] = unexpected_save
        h.s.w8(COMMAND, 0)
        self.assertEqual(h.s.call(HANDLER, COMMAND), 2)
        self.assertEqual(bytes(h.s.uc.mem_read(BASE, 16)), baseline)
        self.assertEqual(bytes(h.s.uc.mem_read(SETTINGS, 0xC8)), settings)

    def test_actual_settings_save_and_load_preserve_marker_and_all_other_bytes(self):
        from audit_flash_length import Machine
        import qc_baseline_epoch as E
        m = Machine(self.data, 2)
        settings = bytearray(range(0xC8))
        struct.pack_into('<H', settings, 0xC6, E.fingerprint(settings[0x90:0xA0]))
        m.uc.mem_write(SETTINGS, bytes(settings))
        for function in (0x0801C844, 0x080156FC, 0x08015690, 0x0801D01C):
            m.handlers[function] = lambda machine: machine.ret()
        def erase(machine):
            machine.uc.mem_write(0x0807F800, bytes([255]) * 204)
            machine.ret(6)
        def program(machine):
            machine.uc.mem_write(machine.arg(0), struct.pack('<I', machine.arg(1)))
            machine.ret(6)
        m.handlers[0x080155EC], m.handlers[0x080156A4] = erase, program
        self.assertEqual(m.call(self.img.autosave['save']), 1)
        self.assertEqual(bytes(m.uc.mem_read(0x0807F800, 204)), bytes(settings) + bytes(4))
        # The exact stock successful-load block copies C8 bytes from its stage.
        m.uc.mem_write(SETTINGS, bytes([0xEE]) * 0xCC)
        m.uc.mem_write(0x20003000, bytes(m.uc.mem_read(0x0807F800, 204)))
        m.uc.reg_write(UC_ARM_REG_R4, 0x20003000)
        m.uc.reg_write(UC_ARM_REG_SP, 0x2000DFC0)
        m.uc.emu_start(0x0800FE41, 0x0800FE4A, count=10000)
        self.assertEqual(m.uc.reg_read(UC_ARM_REG_PC), 0x0800FE4A)
        self.assertEqual(bytes(m.uc.mem_read(SETTINGS, 0xCC)), bytes(settings) + bytes([0xEE]) * 4)

    def test_guarded_sites_fail_before_any_allocation_or_edit(self):
        import length_integrity
        import qc_baseline_epoch as E
        from lpm10a.image import PatchError
        for address in (E.VALID_SITE, E.DEFAULT_SITE, self.img.qc_baseline_epoch['save_site']):
            with contextlib.redirect_stdout(io.StringIO()):
                img = length_integrity.build_candidate()
            img.data[img.f(address)] ^= 1
            before = (bytes(img.data), img.cave_ptr, tuple(img.ram_allocs))
            with self.assertRaises(PatchError):
                E.install(img)
            self.assertEqual((bytes(img.data), img.cave_ptr, tuple(img.ram_allocs)), before)


if __name__ == '__main__':
    unittest.main()
