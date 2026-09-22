"""Exact-parent, allocation and update-image checks for the classic QC overlay."""
import contextlib
import hashlib
import io
import struct
import unittest

from lpm10a.image import PatchError
from lpm10a import symbols as S
import qc_classic as R
import qc_continuity as Q


class QCClassicBuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with contextlib.redirect_stdout(io.StringIO()):
            cls.parent = Q.build_candidate()
            cls.img = R.build_candidate()

    def test_exact_parent_and_existing_bytes_belong_to_declared_sites(self):
        old, new = bytes(self.parent.data), bytes(self.img.data)
        self.assertEqual(hashlib.sha256(old).hexdigest(), R.PARENT_SHA256)
        info = self.img.qc_classic
        self.assertEqual(info['parent_end'], self.parent.cave_ptr)
        sites = {R.TIMER_SITE: 4, R.KEY_CLICK_SITE: 2, Q.GUI_SITE: 4,
                 0x0801BBAC: 4, 0x08011660: 8, 0x08012E6C: 8}
        sites.update({site: 4 for site in info['replaced']})
        allowed = set(range(0x24, 0x2C))
        for address, size in sites.items():
            allowed.update(range(self.img.f(address), self.img.f(address)+size))
        for offset in range(self.parent.f(self.parent.cave_ptr)):
            if old[offset] != new[offset]:
                self.assertIn(offset, allowed, f'unowned mutation at {offset:#x}')
        ui = info['ui']
        self.assertEqual(self.img.ram_allocs, self.parent.ram_allocs + [(ui['cache'], ui['cache_size'])])

    def test_container_identity_limits_and_deterministic_build(self):
        data = bytes(self.img.data)
        off, length, end = struct.unpack_from('<III', data, 0x20)
        self.assertEqual(data[:0x20], self.parent.data[:0x20])
        self.assertEqual(off, 0x1000)
        self.assertEqual(end, off+length-1)
        self.assertEqual(S.APP_BASE+length, self.img.cave_ptr)
        self.assertLess(S.APP_BASE+length, S.CONSTS['BOOTFLAG_PAGE'])
        self.assertFalse(any(data[end+1:]))
        for site in (0x08011660, 0x08012E6C):
            self.assertEqual(self.img.read(site, 8), R.VERSION.encode().ljust(8, b'\0'))
        with contextlib.redirect_stdout(io.StringIO()):
            again = R.build_candidate()
        self.assertEqual(bytes(again.data), data)

    def test_wrong_parent_and_double_patch_rejected_before_mutation(self):
        for already_applied in (False, True):
            with self.subTest(already_applied=already_applied):
                with contextlib.redirect_stdout(io.StringIO()):
                    img = R.build_candidate() if already_applied else Q.build_candidate()
                if not already_applied:
                    img.data[img.f(R.TIMER_SITE)] ^= 1
                before = bytes(img.data), img.cave_ptr, tuple(img.ram_allocs), tuple(img.log)
                with self.assertRaisesRegex(PatchError, 'exact finalized PN2.23Q'):
                    R.apply(img)
                self.assertEqual((bytes(img.data), img.cave_ptr, tuple(img.ram_allocs), tuple(img.log)), before)


if __name__ == '__main__':
    unittest.main()
