"""Length run progress: real GUI writes must stay in the counter after run 1."""
import contextlib
import io
import unittest

from thai.engine import DRAW_SHAPE, PUT_PIXEL, Scene
from thai.mockup import sc_length_idle, sc_length_result


class LengthProgressQuiet(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import length_integrity
        with contextlib.redirect_stdout(io.StringIO()):
            cls.img = length_integrity.build_candidate()
        cls.data = bytes(cls.img.data)

    def scene(self, lang):
        s = Scene(image=self.data, lang=lang)
        sc_length_idle(s)
        state = self.img.length_lifecycle['state']
        s.uc.mem_write(state+4, bytes(s.uc.mem_read(state, 4)))
        return s

    def run_counter(self, s, run):
        if run == 0:
            s.w8(0x200002B4, 1)  # real sequence start announces Testing before the hook
        stack = [0] * 12
        stack[9] = run  # the actual sequence frame's [sp + 0x24]
        s.call(self.img.length_progress['hook'], stack=tuple(stack))
        s.drain()

    def trace(self, s):
        fills, pixels = [], []

        def fill(uc):
            fills.append(tuple(s.arg(i) for i in range(5)))
            return False

        def pixel(uc):
            pixels.append((s.arg(0), s.arg(1)))
            return False

        s.at[DRAW_SHAPE], s.at[PUT_PIXEL] = fill, pixel
        return fills, pixels

    def test_later_runs_keep_testing_label_and_only_update_counter(self):
        for lang in (1, 2):
            with self.subTest(lang=lang):
                s = self.scene(lang)
                self.run_counter(s, 0)
                fills, pixels = self.trace(s)
                for run in (1, 2, 3):
                    s.log.clear()
                    fills.clear()
                    pixels.clear()
                    self.run_counter(s, run)
                    self.assertEqual(fills, [], 'later run erased the whole result box')
                    self.assertTrue(pixels)
                    self.assertTrue(all(192 <= x < 216 and 175 <= y < 191
                                        for x, y in pixels))
                    self.assertIn(f'{run + 1}/4', [text for kind, text, *_ in s.log
                                                   if kind == 'ascii'])

    def test_final_result_erases_counter_and_new_test_starts_at_one(self):
        for lang in (1, 2):
            with self.subTest(lang=lang):
                s = self.scene(lang)
                for run in range(4):
                    self.run_counter(s, run)
                sc_length_result(s)
                plain = self.scene(lang)
                sc_length_result(plain)
                self.assertEqual(s.fb, plain.fb)
                self.run_counter(s, 0)
                fresh = self.scene(lang)
                self.run_counter(fresh, 0)
                self.assertTrue(s.fb == fresh.fb, 'next test must erase the previous results')


if __name__ == '__main__':
    unittest.main()
