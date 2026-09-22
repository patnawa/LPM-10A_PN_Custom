import os
import struct
import unittest
import contextlib
import io
import tempfile
from pathlib import Path

from lpm10rx import container


class ContainerTests(unittest.TestCase):
    raw = bytes(range(256)) * 102 + b"\x11\x22\x33\x44" * 2   # 26120 bytes

    def test_layout_matches_the_accepted_file(self):
        c = container.wrap(self.raw)
        self.assertEqual(c[:32], container.DEFAULT_NAME.encode().ljust(32, b"\0"))
        self.assertEqual(struct.unpack_from("<III", c, 0x20), (0x1000, len(self.raw), 0x1000 + len(self.raw) - 1))
        self.assertFalse(any(c[0x2C:0x1000]))
        self.assertEqual(c[0x1000:0x1000 + len(self.raw)], self.raw)
        self.assertEqual(len(c) % 0x1000, 0)
        self.assertFalse(any(c[0x1000 + len(self.raw):]))

    def test_stock_sized_image_pads_to_32k(self):
        c = container.wrap(b"\xAA" * 26152)
        self.assertEqual(len(c), 32768)

    def test_roundtrip_and_validation(self):
        name, raw = container.unwrap(container.wrap(self.raw, "APP_LPM-10RX_PN1.12.bin"))
        self.assertEqual((name, raw), ("APP_LPM-10RX_PN1.12.bin", self.raw))
        broken = bytearray(container.wrap(self.raw))
        broken[0x28] ^= 1
        with self.assertRaises(ValueError):
            container.unwrap(bytes(broken))
        with self.assertRaises(ValueError):
            container.wrap(self.raw, "x" * 32)
        with self.assertRaises(ValueError):
            container.wrap(b"abc")

    def test_rejects_empty_and_unaligned_payload_headers(self):
        for length in (0, 1, 3, 5):
            with self.subTest(length=length):
                broken = bytearray(container.wrap(b"\0" * 8))
                struct.pack_into("<II", broken, 0x24, length, 0x1000 + length - 1)
                with self.assertRaises(ValueError):
                    container.unwrap(broken)

    def test_rejects_truncated_or_extra_zero_padding(self):
        valid = container.wrap(self.raw)
        for broken in (valid[:-1], valid[:0x1000 + len(self.raw)], valid + b"\0", valid + bytes(0x1000)):
            with self.subTest(size=len(broken)), self.assertRaises(ValueError):
                container.unwrap(broken)

    def test_rejects_malformed_names(self):
        for name in (b"\0" * 32, b"X" * 32, b"name\0junk".ljust(32, b"\0"), b"\xff\0".ljust(32, b"\0")):
            broken = bytearray(container.wrap(self.raw))
            broken[:32] = name
            with self.subTest(name=name), self.assertRaises(ValueError):
                container.unwrap(broken)
        with self.assertRaises(ValueError):
            container.wrap(self.raw, "valid\0hidden")

    def test_check_exits_nonzero_for_an_invalid_container(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "fixture.bin"
            for data, status in ((container.wrap(self.raw), 0), (self.raw, 1), (b"", 1)):
                path.write_bytes(data)
                with self.subTest(status=status), contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(container._main(["check", str(path)]), status)

    def test_matches_the_device_accepted_container_if_present(self):
        # The exact file the owner's probe programmed on 2026-09-21 (payload = stock
        # V3.0.0 with its version string set to 3.0.2, name APP_LPM-10RX_V3.0.2_260921.bin).
        path = os.path.expanduser("~/Desktop/LPM-10RX-SWD-2026-09-21/APP_LPM-10RX_V3.0.2_260921-container.bin")
        if not os.path.exists(path):
            self.skipTest("device-accepted sample not on this machine")
        with open(path, "rb") as f:
            accepted = f.read()
        name, raw = container.unwrap(accepted)
        self.assertEqual(container.wrap(raw, name), accepted)


if __name__ == "__main__":
    unittest.main()
