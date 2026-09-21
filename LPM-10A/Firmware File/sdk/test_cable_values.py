"""PN 2.21 cable-values: the reading at the right end of every wire of the Cable Test result, on
the real wire-map routines under Unicorn (thai/engine.py) with simulated far ends and hum.

    python -m unittest test_cable_values -v
"""
import hashlib
import struct
import unittest

import cable_values as CV
import cable_test as CT
from test_cable_test import build, Harness, TAB, OPEN, OK, CROSSED, SHORT, SWITCH, FAR_END

WIRE_COLOURS = [0x07E0, 0x07FF, 0x0400, 0xF81F, 0xF621, 0xC618, 0xFB80, 0x0C7F, 0xFFFF]


def rows(h):
    """(text, x, y, fg) of the nine 6x12 texts, top to bottom."""
    return sorted([(t, x, y, fg) for k, t, x, y, fg, ex in h.s.log if k == "ascii" and ex["size"] == 12],
                  key=lambda r: r[2])


class CableValues(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.img = build("pn2.21")
        cls.data = bytes(cls.img.finalize().data)
        parent = build("pn2.20")
        cls.parent, cls.parent_end = bytes(parent.finalize().data), parent.cave_ptr

    def test_parent_is_pn220_and_only_the_release_calls_moved(self):
        self.assertEqual(hashlib.sha256(self.parent).hexdigest(), CV.PARENT_SHA256)
        changed = {i for i in range(len(self.parent)) if self.parent[i] != self.data[i]}
        allowed = set(range(0x24, 0x2C))
        for site in CT.RELEASE_SITES:
            o = site - 0x0800A000 + 0x1000
            allowed |= set(range(o, o + 4))
        for s in (0x08011660, 0x08012E6C):
            o = s - 0x0800A000 + 0x1000
            allowed |= set(range(o, o + 8))
        appended = {i for i in changed if i >= self.parent_end - 0x0800A000 + 0x1000}
        self.assertTrue(changed - appended <= allowed)
        self.assertEqual(self.img.cable_values["hook"], (self.parent_end + 3) & ~3)
        o = CV.COLOURS - 0x0800A000 + 0x1000
        self.assertEqual(list(struct.unpack("<9H", self.data[o:o + 18])), WIRE_COLOURS, "stock's wire colour table")

    def test_switch_mode_shows_the_partner_pin_and_the_reading(self):
        h = Harness(self.data, SWITCH, "switch", hum=300)
        self.assertEqual(h.status, [OK] * 8 + [OPEN])
        r = rows(h)
        self.assertEqual([t for t, x, y, fg in r][:8], ["2   60", "1   60", "6   60", "5   60", "4   60", "3   60", "8   60", "7   60"])
        self.assertTrue(r[8][0].startswith("- "), "the shield: no partner, its near-rail value")
        self.assertEqual([(x, y) for t, x, y, fg in r], [(CV.RIGHT_X - 36, CT.ROW0_Y - 6 + CT.ROW_PITCH * i) for i in range(9)])
        self.assertEqual([fg for t, x, y, fg in r], WIRE_COLOURS[:8] + [CV.RED])
        box = {h.s.fb[y][x] for y in range(CT.ROW0_Y - 6, CT.ROW0_Y + 6) for x in range(CV.RIGHT_X - 36, CV.RIGHT_X)}
        self.assertEqual(box, {CV.INTERIOR, WIRE_COLOURS[0]}, "row 1's box: the interior colour and the wire's colour only")
        self.assertEqual(h.texts, [], "no message on a passing test")

    def test_a_swapped_pair_shows_the_wrong_partner(self):
        # wires 1 and 3 swapped at the far end: the switch joins tester pin 1 to tester pin 6, pin 3 to pin 2
        pairs = {0: 5, 5: 0, 2: 1, 1: 2, 3: 4, 4: 3, 6: 7, 7: 6}
        import test_cable_test as T
        original = T.far_end

        def swapped(kind, mapping=None):
            return (lambda d, s: 60 if pairs.get(d) == s else 4095) if kind == "swapped" else original(kind, mapping)
        T.far_end = swapped
        try:
            h = Harness(self.data, SWITCH, "swapped", hum=300)
        finally:
            T.far_end = original
        self.assertEqual(h.status[:8], [OK] * 8, "stock's switch mode still says all green ...")
        self.assertEqual([t[0] for t, x, y, fg in rows(h)][:8], ["6", "3", "2", "5", "4", "1", "8", "7"], "... the partner letters tell the swap")

    def test_open_wires_keep_the_dash_even_with_hum(self):
        for seed in range(1, 6):
            h = Harness(self.data, SWITCH, "floating", hum=300, seed=seed)
            self.assertEqual(h.status, [OPEN] * 9)
            for t, x, y, fg in rows(h):
                self.assertEqual(t[0], "-", t)
                self.assertGreater(int(t[2:]), 3700)
                self.assertEqual(fg, CV.RED)
            self.assertEqual(h.texts, [("Not connected", 68, 271, 0xF800)], "the message is still drawn first")
        h = Harness(self.data, SWITCH, "switch-open3", hum=300)
        r = rows(h)
        self.assertEqual(r[2][0][0], "-"); self.assertEqual(r[5][0][0], "-")
        self.assertEqual((r[2][3], r[5][3], r[0][3]), (CV.RED, CV.RED, WIRE_COLOURS[0]))

    def test_rx_unit_mode_shows_the_ladder_value_only(self):
        h = Harness(self.data, FAR_END, "remote", hum=300)
        self.assertEqual(h.status, [OK] * 9)
        r = rows(h)
        self.assertEqual([t for t, x, y, fg in r], [f"{v:4d}" for v in TAB])
        self.assertEqual({x for t, x, y, fg in r}, {CV.RIGHT_X - 24})
        self.assertEqual([fg for t, x, y, fg in r], WIRE_COLOURS)
        crossed = {i: i for i in range(9)}
        crossed[0], crossed[2] = 2, 0
        h = Harness(self.data, FAR_END, "remote", hum=300, mapping=crossed)
        self.assertEqual(h.status[:3], [CROSSED, OK, CROSSED])
        self.assertEqual([t for t, x, y, fg in rows(h)][:3], ["2319", "1975", "1655"], "the value names the remote pin")
        h = Harness(self.data, FAR_END, "remote-short12", hum=300)
        self.assertEqual(h.status[:2], [SHORT, SHORT])
        r = rows(h)
        self.assertEqual(([t for t, x, y, fg in r][:2], r[0][3], r[1][3]), (["  30", "  30"], CV.YELLOW, CV.YELLOW))
        h = Harness(self.data, FAR_END, "floating", hum=300, lang=2)
        self.assertEqual(h.status, [OPEN] * 9)
        self.assertTrue(all(int(t) > 3700 and fg == CV.RED for t, x, y, fg in rows(h)))
        self.assertTrue(h.thai, "ไม่พบปลายสาย still drawn")

    def test_rest_of_the_screen_is_pn220(self):
        for mode, kind in ((SWITCH, "switch"), (FAR_END, "remote")):
            with self.subTest(mode=mode):
                old = Harness(self.parent, mode, kind, hum=300)
                new = Harness(self.data, mode, kind, hum=300)
                self.assertEqual(old.status, new.status)
                self.assertEqual([r[:CV.RIGHT_X - 36] + r[CV.RIGHT_X:] for r in new.s.fb],
                                 [r[:CV.RIGHT_X - 36] + r[CV.RIGHT_X:] for r in old.s.fb],
                                 "outside the number boxes the screen is pixel-identical")


if __name__ == "__main__":
    unittest.main()
