"""Regression tests for the September 2026 audit (python -m unittest test_audit)."""
import contextlib
import io
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch as mock_patch

from lpm10a.image import Image, PatchError
from lpm10a import symbols as S
from lpm10a.thumb import assemble
import patches


class ImageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "fixture.bin"
        data = bytearray(0x1800)
        data[:8] = b"fixture\0"
        struct.pack_into("<III", data, 0x20, 0x1000, 0x100, 0x10FF)
        self.path.write_bytes(data)
        self.img = Image(self.path)

    def test_emission_reserves_actual_aligned_size(self):
        self.img.emit_code(".word 1")
        source = ".align 16\n.word 0x12345678"
        addr = self.img.emit_code(source)
        code = assemble(addr, source)
        self.assertGreaterEqual(self.img.cave_ptr, addr + len(code))
        self.img.emit_code(".word 0xFFFFFFFF")
        self.assertEqual(self.img.read(addr, len(code)), code)

    def test_truncated_payload_rejected(self):
        self.path.write_bytes(self.path.read_bytes()[:0x1080])
        with self.assertRaises(PatchError):
            Image(self.path)

    def test_short_header_rejected(self):
        self.path.write_bytes(b"short")
        with self.assertRaises(PatchError):
            Image(self.path)

    def test_reads_cannot_escape_image(self):
        for addr, size in ((S.APP_BASE - 1, 1), (self.img.file_end - 1, 2),
                           (S.APP_BASE, -1)):
            with self.subTest(addr=addr, size=size), self.assertRaises(PatchError):
                self.img.read(addr, size)

    def test_invalid_allocations_do_not_move_pointers(self):
        self.img.add_region("test", S.APP_BASE, S.APP_BASE + 32)
        for allocator in (self.img.alloc_code, self.img.alloc_ram,
                          lambda size, align: self.img.alloc_in("test", size, align)):
            for size, align in ((-1, 4), (4, 0), (4, 3)):
                before = (self.img.cave_ptr, self.img._ram_ptr, self.img.regions["test"][:])
                with self.subTest(size=size, align=align), self.assertRaises(PatchError):
                    allocator(size, align)
                self.assertEqual(before, (self.img.cave_ptr, self.img._ram_ptr,
                                          self.img.regions["test"]))

    def test_unterminated_string_rejected_without_modification(self):
        self.img.data[-4:] = b"ABCD"
        before = bytes(self.img.data)
        with self.assertRaises(PatchError):
            self.img.set_string(self.img.file_end - 4, "X")
        self.assertEqual(bytes(self.img.data), before)


class FirmwareTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from build import STOCK
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                cls.stock = Image(STOCK).path
        except SystemExit as ex:
            raise unittest.SkipTest("pinned vendor image unavailable") from ex

    def test_dependencies_rejected_before_any_edit(self):
        for patch in (patches.p_nvp, patches.p_length_average,
                      patches.p_length_blind, patches.p_thai):
            img = Image(self.stock)
            with self.subTest(patch=patch.pid), self.assertRaises(PatchError):
                patch(img)
            self.assertEqual(bytes(img.data), img.original)
            self.assertEqual(img.log, [])

    def test_cli_rejects_missing_dependencies_before_loading_stock(self):
        import build
        with mock_patch("sys.argv", ["build.py", "--only", "length-blind-text"]), \
                mock_patch.object(build, "Image") as loader, \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(build.main(), 2)
            loader.assert_not_called()

    def test_cli_rejects_ambiguous_or_empty_selection(self):
        import build
        for args in (("--only", ""), ("--only", "font-pro", "--all"),
                     ("--only", "font-pro", "--with", "batt-grace")):
            with self.subTest(args=args), mock_patch("sys.argv", ["build.py", *args]), \
                    mock_patch.object(build, "Image") as loader, \
                    contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                try:
                    result = build.main()
                except SystemExit as ex:
                    result = ex.code
                self.assertEqual(result, 2)
                loader.assert_not_called()

    def test_average_accepts_relocated_decimal_conversion(self):
        for prefix in ((), (patches.p_autooff_hold,)):
            img = Image(self.stock)
            for patch in (*prefix, patches.p_length_decimal, patches.p_length_average):
                patch(img)
            self.assertTrue(hasattr(img, "avg_acc"))

    def test_all_patches_build_with_declared_dependencies(self):
        by_id = {p.pid: p for p in patches.REGISTRY}
        for selected in patches.REGISTRY:
            with self.subTest(patch=selected.pid):
                img = Image(self.stock)
                def apply(p):
                    if p.pid in getattr(img, "applied_patches", set()):
                        return
                    for pid in p.requires:
                        apply(by_id[pid])
                    p(img)
                apply(selected)
                img.finalize()
                self.assertIn(selected.pid, img.applied_patches)
                self.assertLessEqual(img.payload_off + img.payload_len, len(img.data))

    def test_battery_cancel_requires_three_fresh_low_samples(self):
        from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB
        from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE
        from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R5, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC
        img = Image(self.stock)
        patches.p_batt_debounce(img)
        img.finalize()
        md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
        def target(site):
            return int(next(md.disasm(img.read(site, 4), site)).op_str.lstrip("#"), 16)
        low, cancel = target(0x0800E6E2), target(0x0800DD5C)
        for mv, charger, cancelled in ((3300, 0, True), (3100, 1, True), (3248, 0, False)):
            with self.subTest(mv=mv, charger=charger):
                uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
                uc.mem_map(0x08000000, 0x80000)
                uc.mem_map(0x20000000, 0x10000)
                uc.mem_write(S.APP_BASE, bytes(img.data[img.payload_off:]))
                stop = 0x08000000
                def hook(uc, addr, size, user):
                    if addr == (img.syms["charger_state"] & ~1):
                        uc.reg_write(UC_ARM_REG_R0, charger)
                    elif addr == (img.syms["battery_millivolts"] & ~1):
                        uc.reg_write(UC_ARM_REG_R0, mv)
                    else:
                        return
                    uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
                uc.hook_add(UC_HOOK_CODE, hook)
                def run(addr):
                    uc.reg_write(UC_ARM_REG_SP, 0x2000E000)
                    uc.reg_write(UC_ARM_REG_LR, stop | 1)
                    uc.reg_write(UC_ARM_REG_R5, 3100)
                    uc.emu_start(addr | 1, stop, count=200)
                    self.assertEqual(uc.reg_read(UC_ARM_REG_PC), stop)
                    return uc.reg_read(UC_ARM_REG_R0)
                self.assertEqual([run(low) for _ in range(3)], [0, 0, 1])
                self.assertEqual(run(cancel) != 0, cancelled)
                self.assertEqual([run(low) for _ in range(3)],
                                 [0, 0, 1] if cancelled else [1, 1, 1])


if __name__ == "__main__":
    unittest.main()
