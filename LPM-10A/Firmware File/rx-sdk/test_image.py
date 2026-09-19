"""RX build-boundary regressions; synthetic inputs, no vendor image required."""
from pathlib import Path
import tempfile
import unittest

from lpm10rx.image import Image, PatchError
from lpm10rx import symbols as S


class ImageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "fixture.bin"
        self.path.write_bytes(bytes(S.APP_SIZE))
        # Explicitly bypass environment resolution for synthetic fixtures.
        from unittest.mock import patch
        with patch("lpm10rx.image.require_stock", return_value=str(self.path)):
            self.img = Image(self.path)

    def test_read_valid_boundary(self):
        self.assertEqual(self.img.read(S.APP_END - 1, 1), b"\0")
        self.assertEqual(self.img.read(S.APP_END, 0), b"")

    def test_invalid_reads_are_not_silently_truncated(self):
        for addr, n in ((S.APP_BASE - 1, 1), (S.APP_END - 1, 2),
                        (S.APP_BASE, -1), (S.APP_END + 1, 0)):
            with self.subTest(addr=addr, n=n), self.assertRaises(PatchError):
                self.img.read(addr, n)

    def test_invalid_pokes_never_modify_image_or_log(self):
        for addr, old, new in ((S.APP_END - 1, "0000", b"xx"),
                               (S.APP_BASE, "00", b"xx"),
                               (S.APP_BASE, "ff", b"x")):
            with self.subTest(addr=addr, old=old), self.assertRaises(PatchError):
                self.img.poke(addr, old, new)
            self.assertEqual(bytes(self.img.data), self.img.original)
            self.assertEqual(self.img.log, [])

    def test_unterminated_string_is_a_patch_error(self):
        self.img.data[-4:] = b"ABCD"
        before = bytes(self.img.data)
        with self.assertRaises(PatchError):
            self.img.set_string(S.APP_END - 4, "X")
        self.assertEqual(bytes(self.img.data), before)

    def test_resized_image_cannot_overwrite_output(self):
        self.img.data.append(0)
        with self.assertRaises(PatchError):
            self.img.save(self.path)
        self.assertEqual(self.path.read_bytes(), self.img.original)


if __name__ == "__main__":
    unittest.main()
