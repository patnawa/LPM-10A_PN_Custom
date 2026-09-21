"""PN 2.23 length-ref-reset: REF starts at 10.0 m on every Length screen entry, whatever the RAM cell
held before -- the owner's "REF 189.1" on PN 2.22 reproduced and gone.  Same end-to-end harness as
test_length_ref_anytime (the real measurement with a simulated PHY, real keys, real GUI).

    python -m unittest test_length_ref_reset -v
"""
import hashlib
import unittest

import length_ref_anytime as LA
import length_ref_reset as RR
from test_length_reference import build, UP, DOWN, OK, LONG, GREY, WHITE
import test_length_ref_anytime as TA          # not `from ... import RefAnytime`: the loader would collect it here too

POWER_UP = 18910                # what the owner's unit had in the REF cell: "REF 189.1", within 1 .. 300 m


class RefReset(TA.RefAnytime):
    @classmethod
    def setUpClass(cls):
        cls.img = build("pn2.23")
        cls.data = bytes(cls.img.finalize().data)
        cls.info = cls.img.length_ref_anytime
        cls.info = dict(cls.info, entry=cls.img.length_ref_reset["entry"])       # the screen entry hook to call
        cls.adj, cls.ref, cls.pending = cls.img.adj_target, cls.img.length_reference["ref"], cls.info["pending"]
        parent = build("pn2.22")
        cls.parent, cls.parent_end = bytes(parent.finalize().data), parent.cave_ptr

    # the PN 2.22 tests run again on PN 2.23 through inheritance (every scene enters through the
    # PN 2.23 hook); this one replaces the static check
    def test_parent_is_pn221_and_only_three_calls_moved(self):
        self.assertEqual(hashlib.sha256(self.parent).hexdigest(), RR.PARENT_SHA256)
        self.assertEqual(len(self.parent), len(self.data))
        changed = {i for i in range(len(self.parent)) if self.parent[i] != self.data[i]}
        allowed = set(range(0x24, 0x2C))
        o = LA.ENTRY_SITE - 0x0800A000 + 0x1000
        allowed |= set(range(o, o + 4))
        for site in (0x08011660, 0x08012E6C):
            o = site - 0x0800A000 + 0x1000
            allowed |= set(range(o, o + 8))
        appended = {i for i in changed if i >= self.parent_end - 0x0800A000 + 0x1000}
        self.assertTrue(changed - appended <= allowed, "PN 2.23 touches one bl site, the version and the cave")
        self.assertEqual(self.info["entry"], (self.parent_end + 3) & ~3)
        self.assertEqual(LA.bl_target(self.data, LA.ENTRY_SITE), self.info["entry"])
        self.assertEqual(LA.bl_target(self.parent, LA.ENTRY_SITE), self.img.length_ref_anytime["entry"], "in front of PN 2.22's entry hook")

    def test_the_power_up_content_of_the_cell_never_shows(self):
        s = self.scene()
        s.w16(self.ref, POWER_UP)
        self.enter(s)                                                  # the screen is entered after power-up
        self.assertEqual(self.state(s)["ref"], LA.REF_DEFAULT)
        self.press(s, OK, LONG); self.press(s, OK, LONG)
        self.assertEqual(self.header(s), {4: ("REF 10.0 ", WHITE), 166: ("NVP 69%", GREY)}, "was: REF 189.1 on PN 2.22")
        self.press(s, UP); self.press(s, UP)
        self.assertEqual((self.state(s)["ref"], self.state(s)["pending"]), (1020, 1), "dialled on this visit")
        self.press(s, OK, LONG); self.press(s, OK, LONG); self.press(s, OK, LONG)     # NVP -> ZERO -> REF again
        self.assertEqual(self.header(s)[4], ("REF 10.2 ", WHITE), "the value last dialled, while on the screen")
        self.enter(s)
        self.assertEqual((self.state(s)["adj"], self.state(s)["pending"], self.state(s)["ref"]), (0, 0, LA.REF_DEFAULT),
                         "a new visit: NVP target, nothing pending, REF 10.0 m")
        self.measure(s)
        self.press(s, OK, LONG); self.press(s, OK, LONG)
        self.assertEqual(self.header(s)[4], ("REF 20.3 ", WHITE), "with a result the measured length, as before")


if __name__ == "__main__":
    unittest.main()
