"""PN 2.17 speed-partner: the Switch row on the SPEED screen, exercised on the real screen
builder and result code under Unicorn (thai/engine.py), in English and in Thai.

    python -m unittest test_speed_partner -v
"""
import contextlib
import hashlib
import io
import os
import unittest

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_MCLASS

from lpm10a.image import Image
import speed_partner as SP
from profiles import PROFILES, apply_profile
from thai.engine import Scene
from thai.mockup import sc_speed_idle, sc_speed_result

HERE = os.path.dirname(os.path.abspath(__file__))
FW_DIR = os.path.dirname(HERE)
STOCK = os.path.join(FW_DIR, "LPM-10A-TX_V2.0.7_260610.bin")
MDIO_READ = 0x080178F0
FLAGS = 0x200002B4
GIGABIT = dict(lpa=0x45E1, st=0x3800)       # 10/100 HD+FD advertised, partner 1000 HD+FD, both receivers OK
ROW = range(SP.ROW_Y, SP.ROW_Y + 49)


def build(name):
    with contextlib.redirect_stdout(io.StringIO()):
        img = Image(STOCK)
        apply_profile(img, PROFILES[name])
    return img


class SpeedPartner(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.img = build("pn2.17")
        cls.data = bytes(cls.img.finalize().data)
        cls.info = cls.img.speed_partner
        parent = build("pn2.16")
        cls.parent, cls.parent_end = bytes(parent.finalize().data), parent.cave_ptr

    # -- static ---------------------------------------------------------------
    def test_parent_is_pn216_and_only_three_sites_moved(self):
        self.assertEqual(hashlib.sha256(self.parent).hexdigest(), SP.PARENT_SHA256)
        self.assertEqual(len(self.parent), len(self.data))
        changed = {i for i in range(len(self.parent)) if self.parent[i] != self.data[i]}
        allowed = set(range(0x24, 0x2C))
        for site, n in ((SP.READ_SITE, 6), (SP.BUILD_SITE, 4), (SP.RESULT, 4)):
            o = site - 0x0800A000 + 0x1000
            allowed |= set(range(o, o + n))
        for s in (0x08011660, 0x08012E6C):
            o = s - 0x0800A000 + 0x1000
            allowed |= set(range(o, o + 8))
        appended = {i for i in changed if i >= self.parent_end - 0x0800A000 + 0x1000}
        self.assertTrue(changed - appended <= allowed, "PN 2.17 touches only its three sites, the version and the header")
        self.assertEqual(self.info["read"], self.parent_end)

    def test_hooks_call_what_they_replace(self):
        md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS)

        def calls(addr, n=0x120):
            o = addr - 0x0800A000 + 0x1000
            return [(i.mnemonic, int(i.op_str[1:], 16)) for i in md.disasm(self.data[o:o + n], addr)
                    if i.mnemonic in ("bl", "b.w") and i.op_str.startswith("#")]
        read = calls(self.info["read"], 0x20)
        self.assertEqual(read, [("bl", MDIO_READ)] * 3)
        build = calls(self.info["build"], 0x60)
        self.assertEqual(build[:3], [("bl", SP.BUTTON_DRAW), ("bl", SP.RECORD_DRAW), ("bl", SP.RECORD_DRAW)])
        self.assertIn(("bl", SP.LANG_IS), build)
        self.assertIn(("bl", 0x080174E8), build)                     # gui_blit for the English label
        self.assertIn(("bl", SP.CJK_TEXT), build)                     # the Thai drawer for สวิตช์
        result = calls(self.info["result"], 0x30)
        self.assertIn(("b.w", SP.RESULT_BODY), result, "the stock body continues after its displaced push")
        self.assertEqual(self.info["thai_label"], self.img.thai["where"][SP.LABEL_TH])
        self.assertEqual(SP.ROW_Y + 48, 273)                         # ends 7 px above the Test Retry button (280)
        self.assertEqual(SP.ROW_Y - (170 + 48), 7)                    # 7 px under Link Type's box (170..218)

    # -- the net-task hook: partner registers, then stock's register 0x11 ---------------
    def test_read_hook_returns_reg11_and_keeps_registers_5_and_10(self):
        s = Scene(image=self.data, lang=1)
        regs = {1: 0x796D, 5: 0x45E1, 10: 0x3800, 0x11: 0xAC00}
        seen = []

        def mdio(uc):
            reg = s.arg(0)
            seen.append(reg)
            s.ret(regs.get(reg, 0))
            return True
        s.at[MDIO_READ] = mdio
        self.assertEqual(s.call(self.info["read"]), 0xAC00)
        self.assertEqual(seen, [5, 10, 0x11], "partner ability, 1000BASE-T status, then the status register as stock")
        cells = s.uc.mem_read(self.info["cells"], 4)
        self.assertEqual(int.from_bytes(cells[:2], "little"), 0x45E1)
        self.assertEqual(int.from_bytes(cells[2:], "little"), 0x3800)

    # -- the screen builder: the row exists before any test ------------------------------
    def scene(self, lang, lpa=0, st=0):
        s = Scene(image=self.data, lang=lang)
        s.w16(self.info["cells"], lpa, st)
        return s

    def test_builder_draws_the_row_and_its_label(self):
        for lang, label in ((1, "ascii"), (2, "glyph")):
            with self.subTest(lang=lang):
                s = self.scene(lang)
                sc_speed_idle(s)
                if lang == 1:
                    self.assertIn(("Switch", SP.LABEL_X, SP.TEXT_Y, 0xFFFF), [(t, x, y, fg) for k, t, x, y, fg, ex in s.log if k == "ascii"])
                else:
                    self.assertFalse([t for k, t, x, y, fg, ex in s.log if k == "ascii" and t == "Switch"])
                    self.assertTrue([1 for k, t, x, y, fg, ex in s.log if k == "glyph" and y == SP.TEXT_Y and 12 < x < 100],
                                    "the Thai label is drawn from the cells inside the label cell")
                # the third row box looks like the second: same colour profile, 55 px lower
                for x in (10, 104, 222):                      # box border, gap after the label cell, interior
                    self.assertEqual([s.fb[y][x] for y in range(170, 219)], [s.fb[y + 55][x] for y in range(170, 219)],
                                     f"column {x}: row 3 mirrors row 2's box, cell and interior")

    def test_rest_of_the_screen_is_pn216(self):
        for lang in (1, 2):
            with self.subTest(lang=lang):
                parent = Scene(image=self.parent, lang=lang)
                sc_speed_idle(parent)
                s = self.scene(lang)
                sc_speed_idle(s)
                self.assertEqual([row for y, row in enumerate(s.fb) if y not in ROW],
                                 [row for y, row in enumerate(parent.fb) if y not in ROW])
                self.assertEqual({parent.fb[y][x] for y in ROW for x in range(8, 226)}, {0x31A7},
                                 "PN 2.16 had plain panel where the row now is")
                self.assertEqual((s.fg(), s.bg()), (parent.fg(), parent.bg()), "colour globals as PN 2.16 leaves them")

    # -- the result: the value after the stock result, in every case ----------------------
    def value(self, s):
        return [(t, x) for k, t, x, y, fg, ex in s.log if k == "ascii" and y == SP.TEXT_Y and x > 100]

    def test_every_partner_combination_has_its_text(self):
        cases = [(0, 0, "No autoneg"), (0x0020, 0, "10"), (0x0040, 0, "10"), (0x0080, 0, "100"), (0x0100, 0, "100"),
                 (0x0200, 0, "100"), (0x01E1, 0, "10/100"), (0, 0x0800, "1000"), (0, 0x0400, "1000"),
                 (0x0061, 0x0800, "10/1000"), (0x0181, 0x0C00, "100/1000"), (0x45E1, 0x3800, "10/100/1000"),
                 (0xCDE1, 0xFFFF, "10/100/1000")]
        for lpa, st, text in cases:
            with self.subTest(lpa=hex(lpa), st=hex(st)):
                s = self.scene(1, lpa, st)
                sc_speed_result(s, reg11=0x8000 | 0x2000)
                self.assertEqual(self.value(s), [(text, SP.VALUE_X - 4 * len(text))], "centred on x 160 like the other values")

    def test_thai_value_is_the_same_ascii(self):
        s = self.scene(2, **GIGABIT)
        sc_speed_result(s, reg11=0x8000 | 0x2000)
        self.assertEqual(self.value(s), [("10/100/1000", SP.VALUE_X - 44)])
        en = self.scene(1, **GIGABIT)
        sc_speed_result(en, reg11=0x8000 | 0x2000)
        self.assertEqual([r[101:225] for r in s.fb[SP.ROW_Y:SP.ROW_Y + 49]], [r[101:225] for r in en.fb[SP.ROW_Y:SP.ROW_Y + 49]],
                         "the value cell is pixel-identical in both languages")

    def test_stock_values_and_return_code_are_untouched(self):
        for reg11, retries, texts, rc in ((0x8000 | 0x2000, 0, ["1000Mbps", "Full-duplex"], 0),
                                          (0x4000, 0, [" 100Mbps", "Half-duplex"], 0),         # stock's own string
                                          (0xC000, 0, [], 1),                         # first error: retry
                                          (0xC000, 1, ["Error!!"], 0)):               # second error: shown, no retry
            with self.subTest(reg11=hex(reg11), retries=retries):
                s = self.scene(1, **GIGABIT)
                sc_speed_idle(s, retry=1)
                s.w8(0x20000074, retries)
                s.w16(0x200002B6, reg11); s.w8(FLAGS, 3)
                self.assertEqual(s.call(SP.RESULT), rc)
                s.drain()
                got = [t for k, t, x, y, fg, ex in s.log if k == "ascii" and (y in (123, 186) and x > 100 or y == 67)]
                self.assertEqual(got, texts)
                if rc == 0 and texts != ["Error!!"]:
                    self.assertEqual(self.value(s), [("10/100/1000", 116)])
                else:
                    self.assertEqual(self.value(s), [], "no partner text on a retry or an Error!! result")

    def test_error_result_clears_a_previous_value(self):
        s = self.scene(1, **GIGABIT)
        sc_speed_result(s, reg11=0x8000 | 0x2000)
        cell = lambda: [r[112:209] for r in s.fb[SP.ROW_Y + 7:SP.ROW_Y + 42]]
        self.assertTrue(any(0xFFFF in r for r in cell()))
        s.w8(0x20000074, 1); s.w16(0x200002B6, 0xC000)
        self.assertEqual(s.call(SP.RESULT), 0)
        s.drain()
        self.assertFalse(any(0xFFFF in r for r in cell()), "the value cell is cleared like the stock cells")

    def test_builder_redraws_the_value_with_a_result_on_screen(self):
        s = self.scene(1, **GIGABIT)
        s.w16(0x200002B6, 0x8000 | 0x2000); s.w8(FLAGS + 1, 3)          # flags[1] == 3: result shown
        s.w8(0x20000075, 1)
        s.set_state(9)
        s.post(0x1D); s.drain()
        self.assertEqual(self.value(s), [("10/100/1000", 116)])
        self.assertIn(("Switch", SP.LABEL_X, SP.TEXT_Y), [(t, x, y) for k, t, x, y, fg, ex in s.log if k == "ascii"])


if __name__ == "__main__":
    unittest.main()
