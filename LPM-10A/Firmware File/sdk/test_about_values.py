"""PN 2.16 about-values: the BATT / NVP / ZERO line on the About screen, drawn by the real
About routine under Unicorn (thai/engine.py), in English and in Thai.

    python -m unittest test_about_values -v
"""
import contextlib
import hashlib
import io
import os
import struct
import unittest

from lpm10a.image import Image
import about_values as AV
from profiles import PROFILES, apply_profile
from thai.engine import Scene
from thai.mockup import sc_about

HERE = os.path.dirname(os.path.abspath(__file__))
FW_DIR = os.path.dirname(HERE)
STOCK = os.path.join(FW_DIR, "LPM-10A-TX_V2.0.7_260610.bin")
SETTINGS = 0x20000C78
WHITE, PANEL = 0xFFFF, 0x2105


def build(name):
    with contextlib.redirect_stdout(io.StringIO()):
        img = Image(STOCK)
        apply_profile(img, PROFILES[name])
    return img


class AboutValues(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.img = build("pn2.16")
        cls.data = bytes(cls.img.finalize().data)
        cls.info = cls.img.about_values
        parent = build("pn2.15")
        cls.parent, cls.parent_end = bytes(parent.finalize().data), parent.cave_ptr

    # -- static ---------------------------------------------------------------
    def test_parent_is_pn215_and_only_the_epilogue_call_moved(self):
        self.assertEqual(hashlib.sha256(self.parent).hexdigest(), AV.PARENT_SHA256)
        self.assertEqual(len(self.parent), len(self.data))
        changed = {i for i in range(len(self.parent)) if self.parent[i] != self.data[i]}
        site = self.info["epilogue"] - 0x0800A000 + 0x1000
        allowed = set(range(site, site + 4)) | set(range(0x24, 0x2C))
        for s in (0x08011660, 0x08012E6C):
            o = s - 0x0800A000 + 0x1000
            allowed |= set(range(o, o + 8))
        appended = {i for i in changed if i >= self.parent_end - 0x0800A000 + 0x1000}
        self.assertTrue(changed - appended <= allowed, "PN 2.16 touches only one bl, the version and the header")
        self.assertEqual(self.info["values"], self.parent_end, "the new code starts where PN 2.15's cave ended")
        o = AV.EPILOGUE_SITE - 0x0800A000 + 0x1000
        self.assertEqual(self.info["epilogue"], AV.bw_target(AV.EPILOGUE_SITE, self.data[o:o + 4]),
                         "the About routine still ends in crash-record's b.w epilogue")

    def test_line_fits_the_panel(self):
        self.assertEqual(len("BATT 3874mV  NVP 68%  ZERO 0.4m"), 31)
        self.assertEqual(AV.LINE_W, 31 * 6)
        self.assertGreaterEqual(AV.LINE_X, 8)                     # panel interior x 8..232
        self.assertLessEqual(AV.LINE_X + AV.LINE_W, 232)
        self.assertGreaterEqual(AV.LINE_Y, 270)                   # below the Factory Reset button (y 239..269)
        self.assertLessEqual(AV.LINE_Y + 12, 310)                 # above the panel border

    # -- dynamic, on the real About draw code ----------------------------------------
    def scene(self, lang, mv=3874, nvp=68, zero=4):
        s = Scene(image=self.data, lang=lang, mv=mv)
        s.w8(SETTINGS + 0xA6, nvp)
        s.w8(SETTINGS + 0xC5, zero)
        sc_about(s)
        return s

    def line(self, s):
        return [(t, x, y, fg, ex["size"]) for k, t, x, y, fg, ex in s.log if k == "ascii" and y == AV.LINE_Y]

    def test_english_and_thai_draw_the_same_line(self):
        for lang in (1, 2):
            with self.subTest(lang=lang):
                s = self.scene(lang)
                self.assertEqual(self.line(s), [("BATT 3874mV  NVP 68%  ZERO 0.4m", AV.LINE_X, AV.LINE_Y, WHITE, 12)])
                self.assertEqual(s.fg(), WHITE, "colour globals restored to what the About routine left")
                self.assertEqual(s.bg(), 0x7304)
                self.assertTrue(any(s.fb[y][x] == WHITE for y in range(AV.LINE_Y, AV.LINE_Y + 12)
                                    for x in range(AV.LINE_X, AV.LINE_X + AV.LINE_W)), "ink reached the framebuffer")

    def test_factory_values_and_edge_values(self):
        cases = [
            (dict(mv=4198, nvp=0, zero=0), "BATT 4198mV  NVP 69%  ZERO 0.0m"),     # fresh unit: byte 0 = factory 69 %
            (dict(mv=3150, nvp=99, zero=20), "BATT 3150mV  NVP 99%  ZERO 2.0m"),
            (dict(mv=3600, nvp=50, zero=0xFF), "BATT 3600mV  NVP 50%  ZERO 0.0m"),  # erased flash padding = 0.0 m
            (dict(mv=3700, nvp=120, zero=13), "BATT 3700mV  NVP 69%  ZERO 1.3m"),  # out-of-range NVP = factory
        ]
        for kw, text in cases:
            with self.subTest(**kw):
                s = self.scene(1, **kw)
                self.assertEqual([t for t, *_ in self.line(s)], [text])

    def test_rest_of_the_about_screen_is_pn215(self):
        parent = Scene(image=self.parent, lang=1, mv=3874)
        parent.w8(SETTINGS + 0xA6, 68); parent.w8(SETTINGS + 0xC5, 4)
        parent.uc.mem_write(0x08011660, b"PN 2.16" + bytes(1))            # the one string that legitimately differs
        sc_about(parent)
        s = self.scene(1)
        band = range(AV.LINE_Y - 2, AV.LINE_Y + 14)
        self.assertEqual([row for y, row in enumerate(s.fb) if y not in band],
                         [row for y, row in enumerate(parent.fb) if y not in band],
                         "outside the values line the screen is pixel-identical to PN 2.15")
        ascii = lambda sc: [(t, x, y) for k, t, x, y, fg, ex in sc.log if k == "ascii"]
        self.assertEqual(ascii(s), ascii(parent) + [(t, x, y) for t, x, y, fg, size in self.line(s)],
                         "PN 2.15's text, then the values line")

    def test_fault_record_still_shows_first(self):
        s = Scene(image=self.data, lang=1, mv=3874)
        s.w8(SETTINGS + 0xA6, 68); s.w8(SETTINGS + 0xC5, 4)
        record = self.img.crash["record"]
        s.uc.mem_write(record, struct.pack("<IIIIIIIII", 0xDEADBEEF, 0x21524110, 0x0801ABCD, 0x08012345,
                                            0x00000400, 0, 0xFFFFFFFD, 0x2000E000, 3))
        sc_about(s)
        texts = [(t, y) for k, t, x, y, fg, ex in s.log if k == "ascii"]
        self.assertIn(("PC 0801ABCD LR 08012345", 208), texts)
        self.assertIn(("CFSR 00000400 IRQ 3", 222), texts)
        self.assertEqual(texts[-1], ("BATT 3874mV  NVP 68%  ZERO 0.4m", AV.LINE_Y), "the values line is drawn last")


if __name__ == "__main__":
    unittest.main()
