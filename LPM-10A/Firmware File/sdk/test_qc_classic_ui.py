"""QC framebuffer write regressions through actual ARM display helpers."""
import contextlib
import io
import struct
import unittest

from thai.engine import DRAW_SHAPE, PUT_PIXEL, Scene


class QcClassicUi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import qc_classic
        with contextlib.redirect_stdout(io.StringIO()):
            cls.img = qc_classic.build_candidate()
        cls.data = bytes(cls.img.data)
        cls.state = cls.img.qc['state']
        cls.api = cls.img.qc_classic['ui']

    def stable_scene(self, lang=1):
        from test_qc_continuity import Harness
        h = Harness(self.data, lang=lang)
        h.enter()
        s = h.s
        data = bytearray(s.uc.mem_read(self.state, 64))
        data[0], data[10] = 1, 255
        struct.pack_into('<H', data, 8, 1)
        data[32:40] = bytes((1,))*8
        s.uc.mem_write(self.state, bytes(data))
        s.w8(0x2000023C, 2)
        s.call(self.api['draw'])
        s.drain()
        return s

    def trace_black_erase(self, s):
        fills = []
        def record_fill(uc):
            x0, y0, x1, y1, colour = (s.arg(i) for i in range(5))
            if colour == 0:
                visible = sum(s.fb[y][x] != 0
                              for y in range(max(0, y0), min(319, y1)+1)
                              for x in range(max(0, x0), min(239, x1)+1))
                if visible:
                    fills.append((x0, y0, x1, y1, visible))
            return False
        s.at[DRAW_SHAPE] = record_fill
        return fills

    def test_unchanged_good_result_does_not_erase_visible_body(self):
        s = self.stable_scene()
        before = [row[:] for row in s.fb]
        erased = self.trace_black_erase(s)
        s.call(self.api['draw'])
        self.assertTrue(s.fb == before, 'stable data changed the final framebuffer')
        self.assertEqual(erased, [], f'stable redraw black-erased visible pixels: {erased}')

    def test_q_parent_negative_control_erases_the_unchanged_result(self):
        import qc_continuity
        with contextlib.redirect_stdout(io.StringIO()):
            img = qc_continuity.build_candidate()
        s = Scene(image=bytes(img.data), lang=1)
        s.set_state(8)
        state = img.qc['state']
        s.w8(state, 1)
        s.w8(state+10, 255)
        s.uc.mem_write(state+32, bytes((1,))*8)
        s.w8(0x2000023C, 2)
        s.call(img.qc['ui']['draw'])
        erased = self.trace_black_erase(s)
        s.call(img.qc['ui']['draw'])
        self.assertTrue(any((x0, y0, x1, y1) == (8, 52, 230, 315) and pixels > 2000
                            for x0, y0, x1, y1, pixels in erased))

    def test_stable_pins_and_increasing_scan_count_write_no_pixels(self):
        for lang in (1, 2):
            with self.subTest(lang=lang):
                s = self.stable_scene(lang)
                writes = []
                def record(uc):
                    writes.append(1)
                    return False
                s.at[DRAW_SHAPE] = s.at[PUT_PIXEL] = record
                for count in (2, 17, 65535):
                    s.w16(self.state+8, count)
                    s.call(self.api['draw'])
                    s.dispatch(0x36)
                    s.drain()
                self.assertEqual(writes, [])

    def test_single_pin_change_is_confined_to_its_old_indicator(self):
        s = self.stable_scene()
        for pin in range(8):
            for state in (2, 1):
                with self.subTest(pin=pin, state=state):
                    before = [row[:] for row in s.fb]
                    s.w8(self.state+32+pin, state)
                    s.call(self.api['draw'])
                    changed = [(x, y) for y in range(320) for x in range(240)
                               if s.fb[y][x] != before[y][x]]
                    self.assertTrue(changed)
                    y0 = 79+27*(7-pin)
                    self.assertTrue(all(201 <= x <= 215 and y0 <= y <= y0+14
                                        for x, y in changed))

    def test_classic_pixels_match_original_artwork_and_good_open_indicators(self):
        import qc_continuity
        from test_qc_continuity import Harness
        with contextlib.redirect_stdout(io.StringIO()):
            old = qc_continuity.parent()
        for lang in (1, 2):
            for states in (bytes((1,))*8, bytes((1, 2, 1, 2, 1, 2, 1, 2))):
                with self.subTest(lang=lang, states=states):
                    h = Harness(bytes(old.data), lang=lang)
                    h.values = [900 if state == 1 else 1000 for state in states]
                    h.enter()
                    h.s.call(0x0800BF40)
                    h.s.drain()
                    s = self.stable_scene(lang)
                    s.uc.mem_write(self.state+32, states)
                    s.call(self.api['draw'])
                    s.drain()
                    self.assertTrue(s.fb == h.s.fb, 'classic result differs from original QC artwork')

    def test_progress_and_error_stay_still_until_successful_init(self):
        s = self.stable_scene()
        state_before = bytes(s.uc.mem_read(self.state, 64))
        before = [row[:] for row in s.fb]
        s.w8(0x2000023C, 4)
        s.dispatch(0x36)
        s.call(self.api['frame'])
        s.call(self.api['error'])
        self.assertEqual(bytes(s.uc.mem_read(self.state, 64)), state_before)
        self.assertTrue(s.fb == before)
        s.w8(0x2000023C, 3)
        s.call(self.api['error'])
        s.drain()
        self.assertEqual(s.uc.mem_read(self.state, 1)[0], 4)
        before = [row[:] for row in s.fb]
        erases = self.trace_black_erase(s)
        s.call(self.api['draw'])
        s.call(self.api['error'])
        s.dispatch(0x36)
        s.drain()
        self.assertTrue(s.fb == before)
        self.assertEqual(erases, [])
        s.call(self.api['frame'])
        s.drain()
        self.assertEqual(s.uc.mem_read(self.state, 1)[0], 1)
        self.assertFalse(s.fb == before)

    def test_unusable_baseline_shows_original_init_prompt(self):
        from test_qc_continuity import Harness
        for lang in (1, 2):
            with self.subTest(lang=lang):
                h = Harness(self.data, lang=lang, baselines=[0]*8)
                h.enter()
                self.assertEqual(h.read(self.state), 4)
                self.assertEqual(h.read(self.api['cache']+8), 2)
                self.assertTrue(h.s.log, 'Init prompt must be visible')

    def test_led_recovers_with_current_pins_despite_old_failure_history(self):
        s = self.stable_scene()
        leds = []
        def record_led(uc):
            leds.append(s.arg(0))
            return False
        s.at[0x08010F94] = record_led
        s.w8(self.state+32, 2)
        s.w16(self.state+16, 1)
        s.call(self.api['draw'])
        s.w8(self.state+32, 1)
        s.call(self.api['draw'])
        self.assertEqual(leds, [1, 2])

    def test_open_and_check_share_the_old_failure_indicator_without_extra_redraw(self):
        s = self.stable_scene()
        s.w8(self.state+32, 2)
        s.call(self.api['draw'])
        before = [row[:] for row in s.fb]
        erases = self.trace_black_erase(s)
        s.w8(self.state+32, 3)
        s.call(self.api['draw'])
        self.assertTrue(s.fb == before)
        self.assertEqual(erases, [])


if __name__ == '__main__':
    unittest.main()
