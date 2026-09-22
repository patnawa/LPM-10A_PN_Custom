"""Real queued QC entry must not paint cable artwork over the Init prompt."""
import contextlib
import io
import unittest

from thai.engine import Scene, DRAW_SHAPE, PUT_PIXEL
from test_qc_gate_timing import PulseHarness
import test_qc_classic as classic
import test_qc_gate_timing as timing


class QCEntryDisplay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import qc_display
        import length_integrity
        with contextlib.redirect_stdout(io.StringIO()):
            cls.img = qc_display.build_candidate()
            cls.parent = length_integrity.build_candidate()
        cls.data = bytes(cls.img.data)

    def expected_prompt(self, lang):
        s = Scene(image=self.data, lang=lang, state=8)
        s.call(0x0800E954)
        s.call(0x0800BAD4)
        s.drain()
        return s.fb

    def assert_frame(self, actual, expected, message):
        different = [(x, y) for y in range(320) for x in range(240)
                     if actual[y][x] != expected[y][x]]
        self.assertEqual(len(different), 0,
                         f'{message}: {len(different)} pixels differ; first={different[:5]}')

    def test_legacy_entry_shows_the_unobscured_original_init_prompt(self):
        for lang in (1, 2):
            with self.subTest(lang=lang):
                h = PulseHarness(self.data, lang=lang)
                h.enter()
                self.assertEqual(h.read(self.img.qc['state']), 4)
                self.assert_frame(h.s.fb, self.expected_prompt(lang),
                                  'queued T568B artwork obscures the Init prompt')

    def test_successful_init_recovers_exact_classic_frame_without_prompt_residue(self):
        for lang in (1, 2):
            with self.subTest(lang=lang):
                h = PulseHarness(self.data, lang=lang)
                old = PulseHarness(bytes(self.parent.data), lang=lang)
                old.enter()  # Clean, valid legacy entry is the original artwork reference.
                h.enter()
                self.assertEqual(classic.QCClassic.initialize(self, h)[0], 0)
                self.assert_frame(h.s.fb, old.s.fb,
                                  'successful Init leaves old prompt pixels behind the classic frame')

    def test_late_queued_qc_bitmap_cannot_overpaint_an_init_prompt(self):
        h = PulseHarness(self.data)
        h.enter()
        expected = self.expected_prompt(1)
        h.s.dispatch(0x3B, bytes.fromhex('1a00440015000000'))
        h.s.drain()
        self.assert_frame(h.s.fb, expected, 'stale queued cable bitmap replaced the prompt')

    def test_waiting_for_init_does_not_redraw_or_start_acquisition(self):
        h = PulseHarness(self.data)
        h.enter()
        before = [row[:] for row in h.s.fb]
        writes = []
        def record(uc):
            writes.append(1)
            return False
        h.s.at[DRAW_SHAPE] = h.s.at[PUT_PIXEL] = record
        for _ in range(5):
            h.s.dispatch(0x36)
            h.s.drain()
            self.assertEqual(h.poll(), 0)
        self.assertEqual(writes, [])
        self.assertEqual(h.s.fb, before)

    def test_late_connector_after_back_does_not_change_the_menu(self):
        h = PulseHarness(self.data)
        h.enter()
        h.press(0, 3)
        self.assertEqual(h.read(0x2000013C), 2)
        before = [row[:] for row in h.s.fb]
        h.s.dispatch(0x3B, bytes.fromhex('1a00440015000000'))
        h.s.drain()
        self.assertEqual(h.s.fb, before)

    def test_unrelated_bitmap_message_still_uses_the_native_renderer(self):
        # Same bitmap at another position is outside the exact stale-QC guard.
        payload = bytes.fromhex('1900440015000000')
        rendered = []
        for data in (self.data, bytes(self.parent.data)):
            s = Scene(image=data, lang=1, state=8)
            s.dispatch(0x3B, payload)
            s.drain()
            rendered.append(s.fb)
        self.assertTrue(any(any(row) for row in rendered[0]))
        self.assertEqual(rendered[0], rendered[1])

    def test_stable_automatic_result_still_writes_no_pixels(self):
        h = PulseHarness(self.data)
        h.enter()
        self.assertEqual(classic.QCClassic.initialize(self, h)[0], 0)
        h.hz = [90_000]*8
        h.advance(50)
        for _ in range(40):
            h.poll()
        h.s.call(self.img.qc_classic['ui']['draw'])
        self.assertEqual(list(h.s.uc.mem_read(self.img.qc['state']+32, 8)), [1]*8)
        writes = []
        def record(uc):
            writes.append(1)
            return False
        h.s.at[DRAW_SHAPE] = h.s.at[PUT_PIXEL] = record
        for _ in range(24):
            h.poll()
        h.s.dispatch(0x36)
        h.s.drain()
        self.assertEqual(writes, [])


class QCDisplayTiming(timing.QCGateTiming):
    """The complete display candidate must retain the physical timing fixes."""
    @classmethod
    def setUpClass(cls):
        import qc_display
        with contextlib.redirect_stdout(io.StringIO()):
            cls.img = qc_display.build_candidate()
        cls.data = bytes(cls.img.data)


if __name__ == '__main__':
    unittest.main()
