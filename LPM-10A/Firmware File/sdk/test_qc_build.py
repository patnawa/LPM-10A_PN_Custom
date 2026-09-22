"""Candidate provenance, patch ownership and update-container integrity."""
import contextlib
import hashlib
import io
import struct
import unittest

from lpm10a.image import PatchError
from lpm10a import symbols as S
import qc_continuity as Q
import qc_calibration as C


class QCBuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with contextlib.redirect_stdout(io.StringIO()):
            cls.parent = Q.parent()
            cls.img = Q.build_candidate()

    def test_exact_parent_and_only_declared_existing_sites_change(self):
        old, new = bytes(self.parent.data), bytes(self.img.data)
        self.assertEqual(hashlib.sha256(old).hexdigest(), Q.PARENT_SHA256)
        self.assertEqual(self.img.qc['parent_end'], self.parent.cave_ptr)
        allowed = set(range(0x24, 0x2C))
        sites = {Q.POLL_SITE: 4, Q.FRAME_SITE: 4, Q.TEST_SITE: 4,
                 Q.ERROR_SITE: 4, Q.ENTRY_SITE: 4, Q.KEY_SITE: 4,
                 Q.GUI_SITE: 4, C.ENTRY: 4, 0x0801BBAC: 4,
                 Q.ENTRY_FRAME_SITE: 4,
                 0x08011660: 8, 0x08012E6C: 8}
        for address, size in sites.items():
            allowed.update(range(self.img.f(address), self.img.f(address)+size))
        for offset in range(self.parent.f(self.parent.cave_ptr)):
            if old[offset] != new[offset]:
                self.assertIn(offset, allowed, f'unowned mutation at file offset {offset:#x}')
        self.assertEqual(self.img.ram_allocs, self.parent.ram_allocs + [(self.img.qc['state'], Q.STATE_SIZE)])

    def test_identity_container_tail_and_repeatable_build(self):
        data = bytes(self.img.data)
        off, length, end = struct.unpack_from('<III', data, 0x20)
        self.assertEqual(data[:0x20], self.parent.data[:0x20])
        self.assertEqual(off, 0x1000)
        self.assertEqual(end, off+length-1)
        self.assertEqual(S.APP_BASE+length, self.img.cave_ptr)
        self.assertLess(S.APP_BASE+length, S.CONSTS['BOOTFLAG_PAGE'])
        self.assertFalse(any(data[end+1:]))
        for site in (0x08011660, 0x08012E6C):
            self.assertEqual(self.img.read(site, 8), Q.VERSION.encode().ljust(8, b'\0'))
        with contextlib.redirect_stdout(io.StringIO()):
            again = Q.build_candidate()
        self.assertEqual(bytes(again.data), data)

    def test_wrong_parent_and_double_application_fail_before_mutation(self):
        for already_applied in (False, True):
            with self.subTest(already_applied=already_applied):
                with contextlib.redirect_stdout(io.StringIO()):
                    img = Q.build_candidate() if already_applied else Q.parent()
                if not already_applied:
                    img.data[img.f(Q.POLL_SITE)] ^= 1
                before = bytes(img.data), img.cave_ptr, tuple(img.ram_allocs), tuple(img.log)
                with self.assertRaisesRegex(PatchError, 'exact finalized PN2.23S'):
                    Q.apply(img)
                self.assertEqual((bytes(img.data), img.cave_ptr, tuple(img.ram_allocs), tuple(img.log)), before)


if __name__ == '__main__':
    unittest.main()
