import os
import struct
import unittest

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
