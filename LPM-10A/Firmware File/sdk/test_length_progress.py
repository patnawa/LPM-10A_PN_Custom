"""PN 2.15 length-progress: the run counter on the Length screen's Testing line, exercised on the
real draw code under Unicorn (thai/engine.py), in English and in Thai.

    python -m unittest test_length_progress -v
"""
import contextlib
import hashlib
import io
import os
import unittest

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_MCLASS

from lpm10a.image import Image
import patches
import length_progress as LP
from profiles import PROFILES, apply_profile
from thai.engine import Scene
from thai.mockup import sc_length_idle, sc_length_result

HERE = os.path.dirname(os.path.abspath(__file__))
FW_DIR = os.path.dirname(HERE)
STOCK = os.path.join(FW_DIR, "LPM-10A-TX_V2.0.7_260610.bin")
RUN_SLOT = 0x24 // 4                      # [sp+0x24] of APP_LENG_Test_Sequence: the run counter
BOX = dict(x0=LP.COUNTER_X, x1=LP.COUNTER_X + 24, y0=175, y1=191)


def build():
    with contextlib.redirect_stdout(io.StringIO()):
        img = Image(STOCK)
        apply_profile(img, PROFILES["pn2.15"])
    return img


class LengthProgress(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.img = build()
        cls.data = bytes(cls.img.finalize().data)
        cls.info = cls.img.length_progress

    # -- static ---------------------------------------------------------------
    def test_parent_is_pn214_and_only_the_run_entry_moved(self):
        parent, parent_end = build_parent()
        self.assertEqual(hashlib.sha256(parent).hexdigest(), LP.PARENT_SHA256)
        self.assertEqual(len(parent), len(self.data))
        changed = {i for i in range(len(parent)) if parent[i] != self.data[i]}
        site = LP.SITE - 0x0800A000 + 0x1000
        allowed = set(range(site, site + 4)) | set(range(0x24, 0x2C))          # the bl; payload_len / payload_end
        for s in (0x08011660, 0x08012E6C):
            o = s - 0x0800A000 + 0x1000
            allowed |= set(range(o, o + 8))                                       # the version string
        appended = {i for i in changed if i >= parent_end - 0x0800A000 + 0x1000}  # the hook, in the cave
        self.assertEqual(changed - appended, allowed & changed)
        self.assertTrue(changed - appended <= allowed, "PN 2.15 touches only the run entry, the version and the header lengths")
        self.assertEqual(self.info["hook"], parent_end, "the hook starts where PN 2.14's cave ended")

    def test_hook_calls_stock_then_the_text_box(self):
        md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS)
        hook = self.info["hook"]
        o = hook - 0x0800A000 + 0x1000
        insns = list(md.disasm(self.data[o:o + 0x40], hook))
        calls = [int(i.op_str[1:], 16) for i in insns if i.mnemonic == "bl"]
        self.assertEqual(calls, [LP.TESTING_DRAW, LP.TEXT_BOX])
        self.assertEqual(insns[0].mnemonic, "push")
        self.assertEqual(self.info["runs"], patches.AVG_RUNS)
        self.assertEqual(self.info, dict(hook=hook, cell=self.info["cell"], x=192, y=175, runs=patches.AVG_RUNS))
        # the stock timeout text at x 68 (14 characters) ends before the counter
        self.assertLessEqual(68 + 14 * 8, LP.COUNTER_X)

    # -- dynamic, on the real draw code ------------------------------------------
    def scene(self, lang):
        s = Scene(image=self.data, lang=lang)
        sc_length_idle(s)
        return s

    def run_hook(self, s, run):
        stack = [0] * 12
        stack[RUN_SLOT] = run
        s.call(self.info["hook"], stack=tuple(stack))
        s.drain()

    def counter_pixels(self, s):
        return [(x, y) for y in range(BOX["y0"], BOX["y1"]) for x in range(BOX["x0"], BOX["x1"])
                if s.fb[y][x] == LP.WHITE]

    def test_every_run_draws_its_number_english(self):
        for run in range(patches.AVG_RUNS):
            with self.subTest(run=run + 1):
                s = self.scene(1)
                self.run_hook(s, run)
                ascii = [(t, x, y, fg) for k, t, x, y, fg, ex in s.log if k == "ascii"]
                self.assertIn(("Testing", 12, 175, LP.WHITE), ascii)
                self.assertIn((f"{run + 1}/{patches.AVG_RUNS}", LP.COUNTER_X, 175, LP.WHITE), ascii)
                self.assertTrue(self.counter_pixels(s), "the digits reach the framebuffer")
                # the counter is the only white ink right of the dots on the Testing line
                self.assertFalse([(x, y) for y in range(175, 191) for x in range(107, LP.COUNTER_X)
                                  if s.fb[y][x] == LP.WHITE])

    def test_thai_keeps_the_label_and_draws_the_same_digits(self):
        s = self.scene(2)
        self.run_hook(s, 1)
        ascii = [(t, x, y) for k, t, x, y, fg, ex in s.log if k == "ascii"]
        self.assertIn(("2/4", LP.COUNTER_X, 175), ascii)             # not moved by the Thai blit hook
        self.assertNotIn(("Testing", 12, 175), ascii)                 # the label is the Thai one ...
        self.assertTrue([1 for k, t, x, y, fg, ex in s.log if k == "glyph" and y == 175 and x < 82],
                        "... drawn from the Thai cells at the left of the line")
        en = self.scene(1)
        self.run_hook(en, 1)
        self.assertEqual([r[BOX["x0"]:BOX["x1"]] for r in s.fb[BOX["y0"]:BOX["y1"]]],
                         [r[BOX["x0"]:BOX["x1"]] for r in en.fb[BOX["y0"]:BOX["y1"]]],
                         "the digits are pixel-identical in both languages")

    def test_result_redraw_leaves_no_counter_behind(self):
        for lang in (1, 2):
            with self.subTest(lang=lang):
                counted = self.scene(lang)
                self.run_hook(counted, patches.AVG_RUNS - 1)
                self.assertTrue(self.counter_pixels(counted))
                sc_length_result(counted)
                plain = self.scene(lang)
                sc_length_result(plain)
                self.assertEqual(counted.fb, plain.fb, "the result screen is the same with or without the counter")

    def test_next_run_overwrites_the_previous_number(self):
        s = self.scene(1)
        self.run_hook(s, 0)
        first = self.counter_pixels(s)
        self.run_hook(s, 1)
        second = self.counter_pixels(s)
        self.assertNotEqual(first, second)
        fresh = self.scene(1)
        self.run_hook(fresh, 1)
        self.assertEqual(second, self.counter_pixels(fresh), "2/4 over 1/4 looks exactly like 2/4 alone")


def build_parent():
    """PN 2.14 as bytes, and the address where its cave ends (the first free code byte)."""
    with contextlib.redirect_stdout(io.StringIO()):
        img = Image(STOCK)
        apply_profile(img, PROFILES["pn2.14"])
    return bytes(img.finalize().data), img.cave_ptr


if __name__ == "__main__":
    unittest.main()
