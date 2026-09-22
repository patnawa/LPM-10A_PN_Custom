"""Reference calibration regression on PN2.24 with PN2.23R negative control.

Measurements run the real four-run PHY sequence, reference solver, actual key
handler and GUI dispatcher. The fixture supplies external PHY readings only.
"""
import contextlib
import io
import unittest

import test_length_ref_anytime as anytime
from length_ref_anytime import ENTRY_SITE, bl_target
from test_length_reference import UP, OK, LONG, SETTINGS


def bind_image(fixture, img):
    fixture.img = img
    fixture.data = bytes(img.finalize().data)
    fixture.info = dict(img.length_ref_anytime, entry=bl_target(fixture.data, ENTRY_SITE))
    fixture.adj = img.adj_target
    fixture.ref = img.length_reference['ref']
    fixture.pending = fixture.info['pending']


class LengthReferenceAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import length_integrity
        with contextlib.redirect_stdout(io.StringIO()):
            bind_image(cls, length_integrity.build_candidate())

    scene = anytime.RefAnytime.scene
    enter = anytime.RefAnytime.enter
    measure = anytime.RefAnytime.measure
    press = anytime.RefAnytime.press
    state = anytime.RefAnytime.state
    header = anytime.RefAnytime.header
    readings = anytime.RefAnytime.readings

    def dial_before_measurement(self, s):
        self.press(s, OK, LONG)
        self.press(s, OK, LONG)
        s.w16(self.ref, 1990)
        self.press(s, UP)
        self.assertEqual((self.state(s)['ref'], self.state(s)['pending']), (2000, 1))

    def test_a_result_without_a_usable_length_keeps_ref_for_the_next_valid_result(self):
        s = self.scene()
        self.dial_before_measurement(s)
        for _ in range(2):
            self.measure(s, cable=(0, 0, 0, 0))
            self.assertEqual(self.state(s)['flag'], 2)
            self.assertEqual(self.state(s)['nvp'], 69)
            self.assertEqual(self.state(s)['pending'], 1,
                             'no length was available to solve NVP; the reference must remain pending')
        self.measure(s)
        self.assertEqual((self.state(s)['nvp'], self.state(s)['pending']), (68, 0))
        self.measure(s, cable=(3000, 3000, 3000, 3000))
        self.assertEqual((self.state(s)['nvp'], self.state(s)['pending']), (68, 0),
                         'the solved reference is consumed once, not applied to later cables')

    def test_parent_negative_control_consumes_ref_without_a_usable_result(self):
        import qc_classic
        original = LengthReferenceAudit()
        with contextlib.redirect_stdout(io.StringIO()):
            bind_image(original, qc_classic.build_candidate())
        s = original.scene()
        original.dial_before_measurement(s)
        original.measure(s, cable=(0, 0, 0, 0))
        self.assertEqual((original.state(s)['pending'], original.state(s)['nvp']), (0, 69))
        original.measure(s)
        self.assertEqual(original.state(s)['nvp'], 69,
                         'the archived R parent reproduces the lost calibration request')

    def test_nonpositive_zero_corrected_length_does_not_consume_ref(self):
        s = self.scene(zero=20)
        self.dial_before_measurement(s)
        for raw in (0, 1, 199, 200):
            with self.subTest(raw=raw):
                s.w8(anytime.FLAGS, 2)
                s.w16(anytime.RESULTS, raw, raw, raw, raw)
                before = len(s.msgs)
                result = s.call(self.img.length_reference_guard['prepare'])
                self.assertEqual(result, 0)
                self.assertEqual((self.state(s)['pending'], self.state(s)['nvp']), (1, 69))
                self.assertEqual(len(s.msgs), before, 'pure preparation must not queue GUI work')

    def test_ref_edits_while_measuring_never_solve_from_incomplete_pair_memory(self):
        s = self.scene()
        self.dial_before_measurement(s)
        s.w8(anytime.FLAGS, 1)
        s.w16(anytime.RESULTS, 250, 3000, 0, 4000)
        self.press(s, UP)
        self.assertEqual((self.state(s)['ref'], self.state(s)['nvp'], self.state(s)['pending']),
                         (2010, 69, 1))
        self.measure(s)
        self.assertEqual((self.state(s)['nvp'], self.state(s)['pending']), (68, 0))

    def test_reentry_clears_reference_and_pending_without_mutating_settings(self):
        for poisoned in (0, 99, 100, 18910, 30000, 65535):
            with self.subTest(poisoned=poisoned):
                s = self.scene()
                s.w16(self.ref, poisoned)
                s.w8(self.pending, 1)
                s.w8(self.adj, 2)
                before = bytes(s.uc.mem_read(SETTINGS, 0xCC))
                self.enter(s)
                self.assertEqual((self.state(s)['ref'], self.state(s)['pending'], self.state(s)['adj']),
                                 (1000, 0, 0))
                self.assertEqual(bytes(s.uc.mem_read(SETTINGS, 0xCC)), before)


if __name__ == '__main__':
    unittest.main()
