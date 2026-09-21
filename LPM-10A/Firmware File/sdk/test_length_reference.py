"""PN 2.18 length-reference: the REF target on the Length screen, driven through the real
Action_key_Process, GUI message 0x3D and the header / result draw code under Unicorn
(thai/engine.py), in English and in Thai.

    python -m unittest test_length_reference -v
"""
import contextlib
import hashlib
import io
import os
import unittest

from lpm10a.image import Image
import length_reference as LR
from profiles import PROFILES, apply_profile
from thai.engine import Scene
from thai.mockup import sc_length_idle, sc_length_result

HERE = os.path.dirname(os.path.abspath(__file__))
FW_DIR = os.path.dirname(HERE)
STOCK = os.path.join(FW_DIR, "LPM-10A-TX_V2.0.7_260610.bin")
SETTINGS = 0x20000C78
ACTION = 0x080149FC             # Action_key_Process(key event*)
DISPATCH = 0x0800D2B4           # key_action_dispatch(action): the stock key table's actions
KEYBUF = 0x20003200
UP, DOWN, OK, LEFT, RIGHT = 2, 3, 4, 1, 5
CLICK, LONG, REPEAT = 3, 6, 12
GREY, WHITE = 0x8410, 0xFFFF
CABLE = (2070, 2080, 2060, 2075)   # raw cm; mean 2071 -> 2031 after Zero 0.4 m -> 20.3 m at NVP 69 %


def build(name):
    with contextlib.redirect_stdout(io.StringIO()):
        img = Image(STOCK)
        apply_profile(img, PROFILES[name])
    return img


class LengthReference(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.img = build("pn2.18")
        cls.data = bytes(cls.img.finalize().data)
        cls.info = cls.img.length_reference
        cls.adj = cls.img.adj_target
        parent = build("pn2.17")
        cls.parent, cls.parent_end = bytes(parent.finalize().data), parent.cave_ptr

    # -- static ---------------------------------------------------------------
    def test_parent_is_pn217_and_only_three_calls_moved(self):
        self.assertEqual(hashlib.sha256(self.parent).hexdigest(), LR.PARENT_SHA256)
        self.assertEqual(len(self.parent), len(self.data))
        changed = {i for i in range(len(self.parent)) if self.parent[i] != self.data[i]}
        allowed = set(range(0x24, 0x2C))
        for site in [LR.KEY_SITE] + self.info["draw_sites"]:
            o = site - 0x0800A000 + 0x1000
            allowed |= set(range(o, o + 4))
        for s in (0x08011660, 0x08012E6C):
            o = s - 0x0800A000 + 0x1000
            allowed |= set(range(o, o + 8))
        appended = {i for i in changed if i >= self.parent_end - 0x0800A000 + 0x1000}
        self.assertTrue(changed - appended <= allowed, "PN 2.18 touches only three bl sites, the version and the header")
        self.assertEqual(self.info["mean_raw"], self.parent_end)
        self.assertEqual(len(self.info["draw_sites"]), 2)
        self.assertEqual(LR.find_bl(self.data, self.img.nvp["gui"], self.info["draw"]), self.info["draw_sites"][0])
        self.assertEqual(LR.find_bl(self.data, self.img.nvp["tail"], self.info["draw"]), self.info["draw_sites"][1])

    # -- the harness: a Length result on screen, keys through the real dispatcher ------------
    def scene(self, lang=1, cm=CABLE, nvp=69, zero=4, unit=0, result=True):
        s = Scene(image=self.data, lang=lang)
        s.actions = []
        s.at[DISPATCH] = lambda uc: (s.actions.append(s.arg(0)), s.ret(0))[1] or True
        if result:
            sc_length_result(s, cm=cm)
        else:
            sc_length_idle(s)
        s.w8(SETTINGS + 0xA6, nvp); s.w8(SETTINGS + 0xC5, zero)
        s.w8(0x200002C0, unit); s.w8(self.adj, 0)
        return s

    def press(self, s, key, evt=CLICK):
        s.heap = 0x2000E800             # the engine's bump allocator never frees: every press starts it over
        s.log.clear()
        s.w8(KEYBUF, key, evt)
        s.call(ACTION, KEYBUF)
        s.drain()

    def state(self, s):
        return dict(adj=s.uc.mem_read(self.adj, 1)[0], nvp=s.uc.mem_read(SETTINGS + 0xA6, 1)[0],
                    zero=s.uc.mem_read(SETTINGS + 0xC5, 1)[0], ref=int.from_bytes(s.uc.mem_read(self.info["ref"], 2), "little"))

    def header(self, s):
        return {x: (t, fg) for k, t, x, y, fg, ex in s.log if k == "ascii" and y == 90}

    def readings(self, s):
        return [t for k, t, x, y, fg, ex in s.log if k == "ascii" and y in (175, 191, 207, 223) and x == 12]

    def test_ok_long_cycles_nvp_zero_ref_only_with_a_result(self):
        s = self.scene()
        for want in (1, 2, 0, 1, 2, 0):
            self.press(s, OK, LONG)
            self.assertEqual(self.state(s)["adj"], want)
            self.assertEqual(s.actions, [], "no stock action for the hold")
        s = self.scene(result=False)
        for want in (1, 0, 1, 0):
            self.press(s, OK, LONG)
            self.assertEqual(self.state(s)["adj"], want, "REF is skipped while nothing is measured")
        s = self.scene(cm=(0, 0, 0, 0))
        for want in (1, 0):
            self.press(s, OK, LONG)
            self.assertEqual(self.state(s)["adj"], want, "REF is skipped when every pair is out of range")

    def test_ref_starts_at_the_displayed_length(self):
        for unit, text, cm in ((0, "REF 20.3 ", CABLE), (1, "REF 2031 ", CABLE), (2, "REF 66.6 ", CABLE),
                               (0, "REF 5.0  ", (540, 0, 0, 0)), (0, "REF 150.3", (15070, 15070, 15070, 15070))):
            with self.subTest(unit=unit, cm=cm):
                s = self.scene(cm=cm, unit=unit)
                self.press(s, OK, LONG); self.press(s, OK, LONG)
                st = self.state(s)
                self.assertEqual(st["adj"], 2)
                mean = sum(c for c in cm if c) // len([c for c in cm if c])
                self.assertEqual(st["ref"], (mean - 40) * 69 // 69, "the mean of the timed pairs, Zero applied")
                self.assertEqual(self.header(s), {4: (text, WHITE), 166: ("NVP 69%", GREY)})

    def test_up_down_dial_ref_and_solve_nvp(self):
        s = self.scene()
        self.press(s, OK, LONG); self.press(s, OK, LONG)
        self.assertEqual(self.readings(s), ["1-2 = 20.3", "3-6 = 20.4", "4-5 = 20.2", "7-8 = 20.4"])
        for key, evt, ref, nvp in ((DOWN, CLICK, 2021, 69), (DOWN, CLICK, 2011, 68), (DOWN, REPEAT, 2001, 68),
                                   (DOWN, CLICK, 1991, 68), (DOWN, CLICK, 1981, 67), (UP, CLICK, 1991, 68),
                                   (UP, REPEAT, 2001, 68)):
            with self.subTest(ref=ref):
                self.press(s, key, evt)
                st = self.state(s)
                self.assertEqual((st["ref"], st["nvp"], st["adj"], st["zero"]), (ref, nvp, 2, 4))
                self.assertEqual(nvp, min(99, max(50, (69 * ref + 2031 // 2) // 2031)), "rounded solve")
                self.assertEqual(self.header(s)[166], (f"NVP {nvp}%", GREY))
                tenths = (ref + 5) // 10
                self.assertEqual(self.header(s)[4], (f"REF {tenths // 10}.{tenths % 10} ", WHITE))
                self.assertEqual(s.actions, [])
        self.assertEqual(self.readings(s), ["1-2 = 20.0", "3-6 = 20.1", "4-5 = 19.9", "7-8 = 20.1"])
        self.press(s, DOWN, CLICK); self.press(s, DOWN, CLICK); self.press(s, DOWN, CLICK)      # 1971 -> 67 %
        self.assertEqual(self.state(s)["nvp"], 67)
        self.assertEqual(self.readings(s), ["1-2 = 19.7", "3-6 = 19.8", "4-5 = 19.6", "7-8 = 19.8"],
                         "the four readings follow the solved NVP without a new measurement")

    def test_steps_and_limits_per_unit(self):
        for unit, step in ((0, 10), (1, 10), (2, 3)):
            with self.subTest(unit=unit):
                s = self.scene(unit=unit)
                self.press(s, OK, LONG); self.press(s, OK, LONG)
                start = self.state(s)["ref"]
                self.press(s, UP)
                self.assertEqual(self.state(s)["ref"], start + step)
                self.press(s, DOWN); self.press(s, DOWN)
                self.assertEqual(self.state(s)["ref"], start - step)
        s = self.scene(cm=(30000, 30000, 30000, 30000), nvp=99, zero=0)
        self.press(s, OK, LONG); self.press(s, OK, LONG)
        self.assertEqual(self.state(s)["ref"], 30000, "REF starts capped at 300 m (the screen shows 430.4 m)")
        self.press(s, UP)
        self.assertEqual(self.state(s)["ref"], 30000)
        s = self.scene(cm=(250, 0, 0, 0), nvp=50, zero=20)
        self.press(s, OK, LONG); self.press(s, OK, LONG)
        self.assertEqual(self.state(s), dict(adj=2, nvp=50, zero=20, ref=100), "0.36 m shown: REF starts at its 1 m floor")
        self.press(s, DOWN)
        self.assertEqual(self.state(s)["ref"], 100, "REF never goes under 1 m")
        self.assertEqual(self.state(s)["nvp"], 99, "69 * 100 / 50 = 138 %, clamped to 99")

    def test_solver_clamps_and_thai_header(self):
        s = self.scene(lang=2)
        self.press(s, OK, LONG); self.press(s, OK, LONG)
        self.assertEqual(self.header(s), {4: ("REF 20.3 ", WHITE), 166: ("NVP 69%", GREY)}, "ASCII header in Thai too")
        for ref, nvp in ((1441, 50), (1481, 50), (1491, 51), (2621, 89), (2911, 99), (3031, 99)):
            with self.subTest(ref=ref):
                s.w16(self.info["ref"], ref + 10)                 # as if dialled there; one more DOWN solves
                self.press(s, DOWN, REPEAT)
                st = self.state(s)
                self.assertEqual((st["ref"], st["nvp"]), (ref, nvp))
                self.assertEqual(nvp, min(99, max(50, (69 * ref + 2031 // 2) // 2031)))
                self.assertEqual(self.header(s)[166], (f"NVP {nvp}%", GREY))

    def test_other_keys_and_targets_are_pn_1_1(self):
        s = self.scene()
        self.press(s, UP)                                    # NVP target: 69 -> 70
        self.assertEqual(self.state(s)["nvp"], 70)
        self.press(s, OK, LONG); self.press(s, DOWN)         # ZERO target: 0.4 -> 0.3
        self.assertEqual(self.state(s)["zero"], 3)
        self.assertEqual(s.actions, [])
        for key, action in ((OK, 0x11), (LEFT, 0x13), (RIGHT, 0x12)):
            self.press(s, key, CLICK)
            self.assertEqual(s.actions[-1], action, "stock click bindings still dispatch")
        self.press(s, OK, LONG)                              # -> REF
        self.assertEqual(self.state(s)["adj"], 2)
        self.press(s, OK, CLICK)
        self.assertEqual(s.actions[-1], 0x11, "Test Start still works while REF is the target")
        self.press(s, OK, 8)                                 # a 2 s hold: nothing, as before
        self.assertEqual(self.state(s)["adj"], 2)
        home = self.scene()
        home.w8(0x2000013C, 2)
        self.press(home, OK, LONG)
        self.assertEqual(self.state(home)["adj"], 0, "no Length key handling outside the Length screen")

    def test_ref_header_covers_the_zero_text_and_leaving_resets(self):
        s = self.scene()
        self.press(s, OK, LONG); self.press(s, OK, LONG)
        fresh = self.scene()
        fresh.w8(self.adj, 2); fresh.w16(self.info["ref"], 2031)
        fresh.log.clear(); fresh.post(0x3D); fresh.drain()
        band = lambda sc: [r[0:80] for r in sc.fb[90:106]]
        self.assertEqual(band(s), band(fresh), "REF over ZERO looks like REF drawn alone: nothing of ZERO left")
        self.assertTrue(any(WHITE in r for r in band(s)))
        s.call(self.parse_bl(0x08012F1C), 0, 0x200002B4)   # length-decimal's unit_load, run on every screen entry
        self.assertEqual(self.state(s)["adj"], 0, "entering the Length screen returns to the NVP target")

    def parse_bl(self, site):
        from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_MCLASS
        md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS)
        o = site - 0x0800A000 + 0x1000
        i = next(md.disasm(self.data[o:o + 4], site))
        self.assertEqual(i.mnemonic, "bl")
        return int(i.op_str[1:], 16)


if __name__ == "__main__":
    unittest.main()
