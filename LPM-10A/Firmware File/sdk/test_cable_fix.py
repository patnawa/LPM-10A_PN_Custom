"""PN2.30 cable-fix: a good cable in a switch passes whatever the centre-tap paths read.

The owner's PN2.29 report ("still yellow color no color show", 2026-09-24) is the first test:
PN2.29 turns every wire of a good cable yellow when the switch's cross-pair paths read a few
counts above the pairs; PN2.30 draws them in their colours.

    python -m unittest test_cable_fix -v
"""
import contextlib
import io
import unittest

import cable_colours as CL
import cable_fix as CF
from test_cable_check import (Rig, rx_end, STRAIGHT, CROSSOVER, SWITCH, RX, PARTNER,
                              OK, OPEN, CROSSED, SHORT, UNKNOWN, UNTESTED)

RED, YELLOW, GREY = 0xF800, 0xFFE0, 0x8410


def images():
    with contextlib.redirect_stdout(io.StringIO()):
        img = CF.build_candidate()
        import cable_colours
        parent = cable_colours.build_candidate()
    return img, bytes(img.data), bytes(parent.data)


def port(wiring=STRAIGHT, pair=60, cross=None, cross_pairs=None, shorts=(), plugged=True):
    """A switch port: pair windings read `pair`; centre taps link pairs at `cross`
    (only between the far pins in `cross_pairs` when given, e.g. a 10/100 port)."""
    def reading(d, s):
        for group in shorts:
            if d in group and s in group:
                return pair
        if not plugged:
            return None
        fd, fs = wiring.get(d), wiring.get(s)
        if fd is None or fs is None or 8 in (fd, fs):
            return None
        if PARTNER[fd] == fs:
            return pair
        if cross is not None and (cross_pairs is None or {fd, fs} <= cross_pairs):
            return cross
        return None
    return reading


class SwitchFix(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.img, cls.data, cls.parent = images()

    def test_owner_report_good_cable_is_yellow_on_pn229_and_coloured_on_pn230(self):
        for pair, cross in ((60, 62), (60, 64), (60, 67), (300, 320), (60, 61)):
            with self.subTest(pair=pair, cross=cross):
                old = Rig(self.parent, SWITCH, port(pair=pair, cross=cross))
                self.assertEqual(old.status[:8], [SHORT] * 8, 'PN2.29: every wire yellow')
                r = Rig(self.data, SWITCH, port(pair=pair, cross=cross))
                self.assertEqual(r.status, [OK] * 8 + [UNTESTED])
                self.assertEqual(r.leds[-1], 2)
                self.assertEqual(r.beeps, [])
                for i, colour in enumerate(CL.T568B[:8]):
                    self.assertIn(colour, {r.s.fb[68 + 24 * i][x] for x in range(25, 171)})

    def test_good_cables_on_every_port_model(self):
        models = (('clean', port()), ('gigabit taps 121', port(cross=121)), ('taps equal to pairs', port(cross=60)),
                  ('10/100 taps on 1-2 and 3-6 only', port(cross=62, cross_pairs={0, 1, 2, 5})),
                  ('10/100 4-5-7-8 tied', port(cross=60, cross_pairs={3, 4, 6, 7})),
                  ('crossover, taps', port(CROSSOVER, cross=63)))
        for name, far in models:
            with self.subTest(name):
                r = Rig(self.data, SWITCH, far, hum=300)
                self.assertEqual(r.status, [OK] * 8 + [UNTESTED])
                self.assertEqual(r.beeps, [])

    def test_wrong_pair_still_fails_where_the_taps_are_clearly_weaker(self):
        swapped = dict(STRAIGHT)
        swapped[1], swapped[2] = 2, 1
        for far in (port(swapped), port(swapped, cross=121)):
            r = Rig(self.data, SWITCH, far)
            self.assertEqual([i for i in range(8) if r.status[i] == CROSSED], [0, 1, 2, 5])
            self.assertEqual(r.leds[-1], 1)
            self.assertEqual(r.beeps, [2])

    def test_shorts_without_a_switch_are_yellow(self):
        for shorts in ([{0, 2}], [{0, 1}]):
            r = Rig(self.data, SWITCH, port(shorts=shorts, plugged=False), hum=300)
            self.assertEqual([r.status[i] for i in sorted(shorts[0])], [SHORT, SHORT])
            self.assertEqual(r.leds[-1], 1)
            self.assertEqual(r.beeps, [2], 'one double beep')
        r = Rig(self.data, SWITCH, port(plugged=False), hum=300)
        self.assertEqual(r.status[:8], [OPEN] * 8)
        self.assertEqual(r.line, ['Not connected'])

    def test_a_broken_wire_does_not_make_its_partner_a_short(self):
        broken = dict(STRAIGHT)
        broken[2] = None
        old = Rig(self.parent, SWITCH, port(broken, cross=121))
        self.assertEqual(old.status[5], SHORT, 'PN2.29: the good partner (6) turned yellow')
        r = Rig(self.data, SWITCH, port(broken, cross=121))
        self.assertEqual(r.status[2], OPEN)
        self.assertNotEqual(r.status[5], SHORT)
        self.assertEqual(r.beeps, [2], 'the stock fault beeps once')

    def test_shield(self):
        r = Rig(self.data, SWITCH, port(cross=62))
        self.assertEqual(r.status[8], UNTESTED)
        r = Rig(self.data, SWITCH, port(shorts=[{2, 8}]))
        self.assertEqual(r.status[8], SHORT)
        self.assertEqual(r.leds[-1], 1)

    def test_text_line_background_is_the_panel(self):
        old = Rig(self.parent, SWITCH, port(plugged=False), hum=300)
        r = Rig(self.data, SWITCH, port(plugged=False), hum=300)
        band = lambda rig: {rig.s.fb[y][x] for y in range(271, 287) for x in range(60, 180)}
        self.assertIn(0x7304, band(old), 'PN2.29: brown box behind "Not connected"')
        self.assertNotIn(0x7304, band(r))


class RxFix(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.img, cls.data, cls.parent = images()

    def test_two_leaking_loose_wires_do_not_shift_good_rows(self):
        wiring = {i: i for i in range(8) if i != 4}                 # UTP, wire 5 broken
        for level in (3300, 3600, 3950):
            def far(d, s, level=level):
                if wiring.get(d) is None:
                    return None
                if wiring.get(s) is None:
                    return level                               # a loose wire leaking below 4000
                return rx_end(wiring)(d, s)
            with self.subTest(level=level):
                old = Rig(self.parent, RX, far)
                self.assertIn(CROSSED, old.status[:4], 'PN2.29 misplaces good rows')
                r = Rig(self.data, RX, far)
                self.assertEqual(r.status[:4], [OK] * 4)
                self.assertEqual(r.status[4], OPEN)

    def test_good_and_crossed_cables_keep_pn229_results(self):
        swapped = dict(STRAIGHT)
        swapped[5], swapped[6] = 6, 5
        cases = ((STRAIGHT, 1.0), (CROSSOVER, 1.0), ({i: i for i in range(8)}, 0.96),
                 ({i: i for i in range(8)}, 1.04), (swapped, 1.0125))
        for wiring, gain in cases:
            for phase in (0.0, 5.0):
                a = Rig(self.parent, RX, rx_end(wiring, gain), hum=40, hum_connected=True, phase=phase)
                b = Rig(self.data, RX, rx_end(wiring, gain), hum=40, hum_connected=True, phase=phase)
                self.assertEqual((a.status, a.map), (b.status, b.map))
        both = dict(STRAIGHT)
        both[0] = 1
        self.assertEqual(Rig(self.data, RX, rx_end(both)).status[:2], [UNKNOWN, UNKNOWN])
        self.assertEqual(Rig(self.data, RX, lambda d, s: 3800).status, [UNKNOWN] * 9)


if __name__ == '__main__':
    unittest.main()
