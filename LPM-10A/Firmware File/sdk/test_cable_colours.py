"""PN2.29 cable-colours: T568B wire colours and white stripes; every decision is PN2.28's.

    python -m unittest test_cable_colours -v
"""
import contextlib
import hashlib
import io
import unittest

import cable_check as CC
import cable_colours as CL
from test_cable_check import (Rig, switch_end, rx_end, STRAIGHT, CROSSOVER, SWITCH, RX,
                              OK, OPEN, CROSSED, SHORT, UNTESTED)

RED, YELLOW, GREY = 0xF800, 0xFFE0, 0x8410


def images():
    with contextlib.redirect_stdout(io.StringIO()):
        img = CL.build_candidate()
        parent = CC.build_candidate()
    return img, bytes(img.data), bytes(parent.data)


def row(r, i):
    y = 68 + 24 * i
    return [r.s.fb[y][x] for x in range(25, 171)]


class CableColours(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.img, cls.data, cls.parent = images()

    def test_parent_is_pn228_and_only_the_table_the_two_calls_and_the_version_move(self):
        self.assertEqual(hashlib.sha256(self.parent).hexdigest(), CL.PARENT_SHA256)
        self.assertEqual(len(self.data), len(self.parent))
        sites = {CL.COLOURS: 18, **{a: 4 for a in self.img.cable_colours['calls']}, 0x08011660: 8, 0x08012E6C: 8}
        allowed = set(range(0x24, 0x2C))
        for a, n in sites.items():
            o = a - 0x0800A000 + 0x1000
            allowed |= set(range(o, o + n))
        end = self.img.cable_colours['stripes'] - 0x0800A000 + 0x1000
        changed = {i for i in range(end) if self.parent[i] != self.data[i]}
        self.assertEqual(changed - allowed, set())

    def test_every_decision_is_pn228s(self):
        swapped = dict(STRAIGHT)
        swapped[1], swapped[2] = 2, 1
        cases = ((SWITCH, switch_end()), (SWITCH, switch_end(swapped)), (SWITCH, switch_end(shorts=[{0, 2}])),
                 (SWITCH, switch_end(plugged=False)), (RX, rx_end()), (RX, rx_end(CROSSOVER)),
                 (RX, rx_end(shorts=[{0, 1}])), (RX, lambda d, s: 3800))
        for mode, far in cases:
            a, b = Rig(self.parent, mode, far), Rig(self.data, mode, far)
            self.assertEqual((a.status, a.map, a.leds, a.beeps, a.values, a.texts),
                             (b.status, b.map, b.leds, b.beeps, b.values, b.texts))

    def test_straight_cable_in_lan_colours_with_white_stripes(self):
        for mode, far in ((SWITCH, switch_end()), (RX, rx_end())):
            r = Rig(self.data, mode, far)
            for i, colour in enumerate(CL.T568B[:8]):
                with self.subTest(mode=mode, pin=i + 1):
                    px = row(r, i)
                    self.assertIn(colour, px)
                    self.assertEqual(WHITE_IN(px), i in CL.STRIPED)
                    self.assertTrue(set(px) <= {colour, 0xFFFF})
            self.assertEqual(r.value_colours[:8], list(CL.T568B[:8]))
        r = Rig(self.data, RX, rx_end())
        self.assertIn(CL.SILVER, row(r, 8), 'the shield is silver')
        r = Rig(self.data, SWITCH, switch_end())
        self.assertIn(GREY, row(r, 8), 'switch mode: shield not tested, grey as PN2.28')

    def test_faults_keep_their_colour_and_get_no_stripes(self):
        swapped = dict(STRAIGHT)
        swapped[1], swapped[2] = 2, 1
        r = Rig(self.data, SWITCH, switch_end(swapped))
        self.assertEqual(r.status[0], CROSSED)
        self.assertEqual(set(row(r, 0)), {RED}, 'wrong pair: red, full length, no white')
        r = Rig(self.data, SWITCH, switch_end(shorts=[{0, 2}], plugged=False))
        self.assertEqual(r.status[0], SHORT)
        self.assertEqual(set(row(r, 0)), {YELLOW})
        broken = dict(STRAIGHT)
        broken[0] = None
        r = Rig(self.data, RX, rx_end(broken))
        self.assertEqual(r.status[0], OPEN)
        self.assertNotIn(0xFFFF, row(r, 0))

    def test_crossed_wires_are_striped_along_the_diagonal(self):
        r = Rig(self.data, RX, rx_end(CROSSOVER))
        self.assertEqual(r.status[0], CROSSED)                       # pin 1 (white-orange) lands on remote 3
        whites = [(x, y) for y in range(60, 130) for x in range(29, 171) if r.s.fb[y][x] == 0xFFFF
                  and 68 < y < 116]
        self.assertTrue(whites, 'white dashes between rows 1 and 3')
        ys = sorted({y for x, y in whites})
        self.assertGreater(ys[-1] - ys[0], 20, 'they follow the diagonal')

    def test_preview_images(self):
        import os
        out = os.environ.get('CABLE_PREVIEW')
        if not out:
            self.skipTest('set CABLE_PREVIEW=<folder> to write PNG previews')
        swapped = dict(STRAIGHT)
        swapped[1], swapped[2] = 2, 1
        for name, mode, far, lang in (('switch_straight_en', SWITCH, switch_end(), 1),
                                      ('switch_miswire_en', SWITCH, switch_end(swapped), 1),
                                      ('rx_straight_th', RX, rx_end(), 2),
                                      ('rx_crossover_en', RX, rx_end(CROSSOVER), 1)):
            r = Rig(self.data, mode, far, lang=lang)
            r.s.image(scale=2).save(os.path.join(out, f'pn229_{name}.png'))


def WHITE_IN(px):
    return 0xFFFF in px


if __name__ == '__main__':
    unittest.main()
