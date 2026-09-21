"""PN 2.22 length-ref-anytime: the REF target before a measurement, on the real code end to end
under Unicorn (thai/engine.py): APP_LENG_Test_Sequence with a simulated PHY produces the result,
the keys go through the real Action_key_Process, the drawing through the real GUI task.

    python -m unittest test_length_ref_anytime -v
"""
import hashlib
import unittest

import length_ref_anytime as LA
import length_reference as LR
from test_length_reference import build, ACTION, KEYBUF, UP, DOWN, OK, LEFT, RIGHT, CLICK, LONG, REPEAT, GREY, WHITE, SETTINGS
from thai.engine import Scene
from thai.mockup import sc_length_idle

SEQ = 0x080119EC                # APP_LENG_Test_Sequence: one Test Start, AVG_RUNS runs
RUN_START = 0x08011A6E          # the first instruction of every run
PHY_READ = 0x08018A80           # phy_ext_read(reg, &value): 0x87..0x8A = the four pairs' raw cm
DISPATCH = 0x0800D2B4           # key_action_dispatch(action): the stock key table's actions
FLAGS, RESULTS = 0x200002B4, 0x200002B8
CABLE = (2070, 2080, 2060, 2075)   # raw cm; the four-pair vote settles on 2071 -> 2031 after Zero 0.4 m -> 20.3 m at 69 %


class RefAnytime(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.img = build("pn2.22")
        cls.data = bytes(cls.img.finalize().data)
        cls.info = cls.img.length_ref_anytime
        cls.adj, cls.ref, cls.pending = cls.img.adj_target, cls.img.length_reference["ref"], cls.info["pending"]
        parent = build("pn2.21")
        cls.parent, cls.parent_end = bytes(parent.finalize().data), parent.cave_ptr

    # -- static ---------------------------------------------------------------
    def test_parent_is_pn221_and_only_three_calls_moved(self):
        self.assertEqual(hashlib.sha256(self.parent).hexdigest(), LA.PARENT_SHA256)
        self.assertEqual(len(self.parent), len(self.data))
        changed = {i for i in range(len(self.parent)) if self.parent[i] != self.data[i]}
        allowed = set(range(0x24, 0x2C))
        for site in (LA.KEY_SITE, LA.RESULT_SITE, LA.ENTRY_SITE):
            o = site - 0x0800A000 + 0x1000
            allowed |= set(range(o, o + 4))
        for s in (0x08011660, 0x08012E6C):
            o = s - 0x0800A000 + 0x1000
            allowed |= set(range(o, o + 8))
        appended = {i for i in changed if i >= self.parent_end - 0x0800A000 + 0x1000}
        self.assertTrue(changed - appended <= allowed, "PN 2.22 touches three bl sites, the version and the cave")
        self.assertEqual(self.info["key"], (self.parent_end + 3) & ~3)
        self.assertEqual(self.info["unit_load"], LA.bl_target(self.parent, LA.ENTRY_SITE), "in front of length-decimal's unit_load")
        self.assertEqual(LA.bl_target(self.data, LA.ENTRY_SITE), self.info["entry"])
        self.assertEqual(LA.bl_target(self.data, LA.RESULT_SITE), self.info["result"])
        self.assertEqual(LA.bl_target(self.data, LA.KEY_SITE), self.info["key"])
        self.assertEqual(LA.bl_target(self.parent, LA.RESULT_SITE), LA.GUI_MSG_SEND)

    # -- the harness: the Length screen, a simulated PHY, keys through the real dispatcher -----------
    def scene(self, lang=1, nvp=69, zero=4, unit=0):
        s = Scene(image=self.data, lang=lang)
        s.actions, s.run, s.cable = [], -1, CABLE
        s.vals["tick_step"] = 10

        def phy_read(uc):
            reg, out = s.arg(0), s.arg(1)
            s.w16(out, s.cable[reg - 0x87] if 0x87 <= reg <= 0x8A else 0)
            s.ret(0)
            return True

        def run_start(uc):
            s.run += 1
            return False

        s.at[PHY_READ] = phy_read
        s.at[RUN_START] = run_start
        s.at[DISPATCH] = lambda uc: (s.actions.append(s.arg(0)), s.ret(0))[1] or True
        sc_length_idle(s, unit=unit)
        s.w8(SETTINGS + 0xA6, nvp); s.w8(SETTINGS + 0xA7, unit); s.w8(SETTINGS + 0xC5, zero)    # unit_load reads the unit from settings
        s.w8(self.adj, 0); s.w8(self.pending, 0x5A); s.w16(self.ref, 0xFFFF)     # arena garbage
        self.enter(s)
        return s

    def enter(self, s):
        """The Length screen entry hook, as leng_enter_state calls it (r1 = test_busy_flags)."""
        s.call(self.info["entry"], 0, FLAGS)

    def measure(self, s, cable=CABLE):
        """One Test Start: the whole sequence (four runs), then the GUI draws the result."""
        s.cable, s.run = cable, -1
        s.heap = 0x2000E800
        s.log.clear()
        s.call(SEQ)
        s.drain()

    def press(self, s, key, evt=CLICK):
        s.heap = 0x2000E800             # the engine's bump allocator never frees: every press starts it over
        s.log.clear()
        s.w8(KEYBUF, key, evt)
        s.call(ACTION, KEYBUF)
        s.drain()

    def state(self, s):
        return dict(adj=s.uc.mem_read(self.adj, 1)[0], nvp=s.uc.mem_read(SETTINGS + 0xA6, 1)[0],
                    zero=s.uc.mem_read(SETTINGS + 0xC5, 1)[0], ref=int.from_bytes(s.uc.mem_read(self.ref, 2), "little"),
                    pending=s.uc.mem_read(self.pending, 1)[0], flag=s.uc.mem_read(FLAGS, 1)[0])

    def header(self, s):
        return {x: (t, fg) for k, t, x, y, fg, ex in s.log if k == "ascii" and y == 90}

    def readings(self, s):
        return [t for k, t, x, y, fg, ex in s.log if k == "ascii" and y in (175, 191, 207, 223) and x == 12]

    # -- behaviour -------------------------------------------------------------
    def test_ok_long_always_cycles_and_ref_starts_at_10m_without_a_result(self):
        s = self.scene()
        self.assertEqual(self.state(s)["pending"], 0, "entry clears the mark")
        for want in (1, 2, 0, 1, 2, 0):
            self.press(s, OK, LONG)
            st = self.state(s)
            self.assertEqual((st["adj"], st["flag"]), (want, 0))
            if want == 2:
                self.assertEqual(st["ref"], LA.REF_DEFAULT)
                self.assertEqual(self.header(s), {4: ("REF 10.0 ", WHITE), 166: ("NVP 69%", GREY)})
                self.assertEqual(self.readings(s), [], "nothing measured, nothing to show")
            self.assertEqual(s.actions, [], "no stock action for the hold")
        self.assertEqual(self.state(s)["nvp"], 69, "no result: nothing solved")
        s = self.scene(unit=2)
        self.press(s, OK, LONG); self.press(s, OK, LONG)
        self.assertEqual(self.header(s)[4], ("REF 32.8 ", WHITE), "10.0 m in feet")

    def test_ref_dialled_first_is_applied_to_the_next_result_once(self):
        s = self.scene()
        self.press(s, OK, LONG); self.press(s, OK, LONG)
        for key, evt, ref in ((UP, CLICK, 1010), (UP, REPEAT, 1020), (DOWN, CLICK, 1010)):
            self.press(s, key, evt)
            st = self.state(s)
            self.assertEqual((st["ref"], st["nvp"], st["pending"]), (ref, 69, 1), "dialled, pending, NVP untouched")
            self.assertEqual(self.header(s), {4: (f"REF {ref // 100}.{ref // 10 % 10} ", WHITE), 166: ("NVP 69%", GREY)})
        s.w16(self.ref, 1990); self.press(s, UP)                      # dialled to 20.0 m
        self.assertEqual(self.state(s)["ref"], 2000)
        self.measure(s)
        st = self.state(s)
        self.assertEqual((st["flag"], st["adj"], st["ref"], st["pending"]), (2, 2, 2000, 0))
        self.assertEqual(st["nvp"], 68, "69 * 2000 / 2031 = 67.95: the result is fitted to REF once")
        self.assertEqual(self.readings(s)[-4:], ["1-2 = 20.0", "3-6 = 20.0", "4-5 = 20.0", "7-8 = 20.0"])
        self.assertEqual(self.header(s), {4: ("REF 20.0 ", WHITE), 166: ("NVP 68%", GREY)}, "the header follows (msg 0x3D)")
        self.measure(s, cable=(3000, 3000, 3000, 3000))
        st = self.state(s)
        self.assertEqual((st["nvp"], st["adj"], st["ref"], st["pending"]), (68, 2, 2000, 0), "the next measurement is an ordinary one")
        self.assertEqual(self.readings(s)[-4:], ["1-2 = 29.2"] + ["%s = 29.2" % p for p in ("3-6", "4-5", "7-8")], "(3000 - 40) * 68 / 69")
        self.assertEqual(self.header(s), {}, "no 0x3D without a solve: the header is not redrawn")
        self.press(s, DOWN)                                            # a result is on screen now: dialling solves at once
        st = self.state(s)
        self.assertEqual((st["ref"], st["pending"]), (1990, 0))
        self.assertEqual(st["nvp"], min(99, max(50, (69 * 1990 + 2960 // 2) // 2960)))

    def test_measure_then_dial_is_pn218(self):
        s = self.scene()
        self.measure(s)
        self.assertEqual(self.readings(s)[-4:], ["1-2 = 20.3", "3-6 = 20.3", "4-5 = 20.3", "7-8 = 20.3"])
        self.assertEqual(self.state(s)["nvp"], 69, "REF is not the target: nothing solved")
        self.press(s, OK, LONG)
        self.assertEqual(self.header(s), {4: ("ZERO 0.4m", WHITE), 166: ("NVP 69%", GREY)})
        self.press(s, OK, LONG)
        st = self.state(s)
        self.assertEqual((st["adj"], st["ref"], st["pending"]), (2, 2031, 0), "REF starts at the displayed mean")
        self.assertEqual(self.header(s), {4: ("REF 20.3 ", WHITE), 166: ("NVP 69%", GREY)})
        self.press(s, DOWN); self.press(s, DOWN)
        st = self.state(s)
        self.assertEqual((st["ref"], st["nvp"], st["pending"]), (2011, 68, 0), "solved at once, nothing pending")
        self.assertEqual(self.readings(s), ["1-2 = 20.0", "3-6 = 20.0", "4-5 = 20.0", "7-8 = 20.0"])
        self.press(s, OK, LONG)
        self.assertEqual(self.state(s)["adj"], 0)
        self.press(s, OK, LONG); self.press(s, OK, LONG)
        self.assertEqual(self.state(s)["ref"], (2031 * 68 + 34) // 69, "re-entered with the result: the displayed mean at the new NVP")
        self.assertEqual(self.header(s)[4], ("REF 20.0 ", WHITE))

    def test_leaving_ref_or_the_screen_forgets_a_pending_ref(self):
        s = self.scene()
        self.press(s, OK, LONG); self.press(s, OK, LONG); self.press(s, UP)
        self.assertEqual(self.state(s)["pending"], 1)
        self.press(s, OK, LONG)                                        # REF -> NVP
        self.assertEqual((self.state(s)["adj"], self.state(s)["pending"]), (0, 0))
        self.measure(s)
        self.assertEqual(self.state(s)["nvp"], 69, "nothing fitted")
        s = self.scene()
        self.press(s, OK, LONG); self.press(s, OK, LONG); self.press(s, UP)
        self.assertEqual((self.state(s)["adj"], self.state(s)["pending"], self.state(s)["ref"]), (2, 1, 1010))
        self.enter(s)                                                  # the screen is entered again
        self.assertEqual((self.state(s)["adj"], self.state(s)["pending"]), (0, 0))
        self.measure(s)
        self.assertEqual(self.state(s)["nvp"], 69)
        self.press(s, OK, LONG); self.press(s, OK, LONG)
        self.assertEqual(self.state(s)["ref"], 2031, "with a result, REF starts at the displayed mean, not the old dial")
        s = self.scene()
        self.press(s, OK, LONG); self.press(s, OK, LONG); self.press(s, UP)
        self.press(s, OK, LONG); self.press(s, OK, LONG); self.press(s, OK, LONG)     # NVP -> ZERO -> REF
        self.assertEqual((self.state(s)["ref"], self.state(s)["pending"]), (1010, 0), "without a result REF keeps the dial; the mark is gone")

    def test_other_keys_and_targets_are_unchanged(self):
        s = self.scene()
        self.press(s, UP)                                    # NVP target: 69 -> 70 (PN 1.1)
        self.assertEqual(self.state(s)["nvp"], 70)
        self.press(s, OK, LONG); self.press(s, DOWN)         # ZERO target: 0.4 -> 0.3
        self.assertEqual(self.state(s)["zero"], 3)
        self.assertEqual(s.actions, [])
        self.press(s, OK, LONG)                              # REF, no result
        for key, action in ((OK, 0x11), (LEFT, 0x13), (RIGHT, 0x12)):
            self.press(s, key, CLICK)
            self.assertEqual(s.actions[-1], action, "stock click bindings still dispatch while REF is the target")
        self.press(s, OK, 8)
        self.assertEqual(self.state(s)["adj"], 2, "a 2 s hold: nothing")
        home = self.scene()
        home.w8(0x2000013C, 2)
        self.press(home, OK, LONG)
        self.assertEqual(self.state(home)["adj"], 0, "no Length key handling outside the Length screen")

    def test_thai(self):
        s = self.scene(lang=2)
        self.press(s, OK, LONG); self.press(s, OK, LONG); self.press(s, UP)
        self.assertEqual(self.header(s), {4: ("REF 10.1 ", WHITE), 166: ("NVP 69%", GREY)}, "ASCII header in Thai too")
        s.w16(self.ref, 1990); self.press(s, UP)
        self.measure(s)
        self.assertEqual(self.state(s)["nvp"], 68)
        self.assertTrue(any(t.startswith("1-2 = 20.0") for k, t, x, y, fg, ex in s.log if k in ("ascii", "thai")), s.log[-6:])
        self.assertEqual(self.header(s), {4: ("REF 20.0 ", WHITE), 166: ("NVP 68%", GREY)})


if __name__ == "__main__":
    unittest.main()
