"""PN 2.20 cable-text-clear: the owner's PN 2.19 report -- "Not connected" of an unplugged test stays
on screen after a Test Retry with the cable in a switch -- reproduced on PN 2.19 and gone on PN 2.20,
on the real wire-map routines under Unicorn (thai/engine.py).

    python -m unittest test_cable_clear -v
"""
import hashlib
import os
import random
import unittest

import cable_clear as CC
from test_cable_test import build, far_end, SELECT, ADC, DELAY, OPEN, OK, SWITCH, FAR_END
from thai.engine import Scene
from thai.mockup import sc_cable_result

BAND_ROWS = range(271, 287)


class Retry:
    """The owner's sequence: a test with nothing at the far end, then Test Retry with the cable
    in a switch / the RX unit -- the retry runs the routine straight from the result screen."""

    def __init__(self, data, mode, lang=1, hum=300):
        self.s = s = Scene(image=data, lang=lang)
        self.kind = "floating"
        sel = {0: 0, 1: 0}
        rnd = random.Random(1)

        def select(uc):
            sel[s.arg(1)] = s.arg(0)
            return False

        def adc(uc):
            v = far_end(self.kind)(sel[0], sel[1])
            if hum and v >= 4000:
                v = min(4095, max(0, v + rnd.randint(-hum, hum)))
            s.ret(v)
            return True
        s.at[SELECT], s.at[ADC], s.at[DELAY] = select, adc, (lambda uc: (s.ret(0), True)[1])
        sc_cable_result(s, mode=mode)                   # test 1: nothing at the far end

    def retry(self, kind):
        self.kind = kind
        self.s.log.clear()
        self.s.post(0x11); self.s.drain()               # Test Retry: the routine runs again, no screen rebuild
        return list(self.s.uc.mem_read(0x2000023E, 9))

    def red(self):
        return sum(1 for y in BAND_ROWS for x in range(40, 201) if self.s.fb[y][x] == 0xF800)

    def texts(self):
        return [(t, y) for k, t, x, y, fg, ex in self.s.log if k == "ascii" and y in BAND_ROWS]


class CableTextClear(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.img = build("pn2.20")
        cls.data = bytes(cls.img.finalize().data)
        parent = build("pn2.19")
        cls.parent, cls.parent_end = bytes(parent.finalize().data), parent.cave_ptr

    def test_parent_is_pn219_and_only_the_two_frame_calls_moved(self):
        self.assertEqual(hashlib.sha256(self.parent).hexdigest(), CC.PARENT_SHA256)
        changed = {i for i in range(len(self.parent)) if self.parent[i] != self.data[i]}
        allowed = set(range(0x24, 0x2C))
        for site in CC.FRAME_SITES:
            o = site - 0x0800A000 + 0x1000
            allowed |= set(range(o, o + 4))
        for s in (0x08011660, 0x08012E6C):
            o = s - 0x0800A000 + 0x1000
            allowed |= set(range(o, o + 8))
        appended = {i for i in changed if i >= self.parent_end - 0x0800A000 + 0x1000}
        self.assertTrue(changed - appended <= allowed)
        self.assertEqual(self.img.cable_clear["hook"], self.parent_end)

    def test_pn219_kept_the_stale_text_and_pn220_does_not(self):
        for mode, kind in ((SWITCH, "switch"), (FAR_END, "remote")):
            with self.subTest(mode=mode):
                old = Retry(self.parent, mode)
                self.assertGreater(old.red(), 0, "PN 2.19: Not connected drawn for the unplugged test")
                self.assertEqual(old.retry(kind)[:8], [OK] * 8)
                self.assertGreater(old.red(), 0, "PN 2.19: ... and still there after the passing retry (the report)")
                new = Retry(self.data, mode)
                self.assertGreater(new.red(), 0)
                self.assertEqual(new.retry(kind)[:8], [OK] * 8)
                self.assertEqual(new.red(), 0, "PN 2.20: the line is wiped before the retry draws")
                self.assertEqual(new.texts(), [])
                self.assertEqual({new.s.fb[y][x] for y in BAND_ROWS for x in range(40, 201)}, {CC.PANEL})

    def test_a_fresh_message_still_shows(self):
        for lang in (1, 2):
            with self.subTest(lang=lang):
                r = Retry(self.data, SWITCH, lang=lang)
                self.assertGreater(r.red(), 0, "Not connected on the first, unplugged test")
                r.retry("switch")
                self.assertEqual(r.red(), 0)
                self.assertEqual(r.retry("floating"), [OPEN] * 9)
                self.assertGreater(r.red(), 0, "unplugged again: Not connected is back")
                if lang == 1:
                    self.assertEqual(r.texts(), [("Not connected", 271)])
        # stock's own "Result error!!" (an unidentified reading, status 4) is drawn after the wipe too
        s = Scene(image=self.data, lang=1)
        s.at[SELECT] = lambda uc: False
        s.at[ADC] = lambda uc: (s.ret(4095), True)[1]
        s.at[DELAY] = lambda uc: (s.ret(0), True)[1]
        sc_cable_result(s, mode=FAR_END, wires=[4, 1, 1, 1, 1, 1, 1, 1, 1])
        self.assertIn(("Result error!!", 271), [(t, y) for k, t, x, y, fg, ex in s.log if k == "ascii"])
        self.assertTrue(any(s.fb[y][x] == 0xF800 for y in BAND_ROWS for x in range(64, 176)))

    def test_the_wires_and_the_rest_of_the_screen_are_pn219(self):
        for mode, kind in ((SWITCH, "switch"), (FAR_END, "remote")):
            with self.subTest(mode=mode):
                old, new = Retry(self.parent, mode), Retry(self.data, mode)
                old.retry(kind); new.retry(kind)
                self.assertEqual([r for y, r in enumerate(new.s.fb) if y not in BAND_ROWS],
                                 [r for y, r in enumerate(old.s.fb) if y not in BAND_ROWS])


if __name__ == "__main__":
    unittest.main()
