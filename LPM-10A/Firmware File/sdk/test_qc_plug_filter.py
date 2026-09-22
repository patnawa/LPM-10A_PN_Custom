"""Plugged-cable filter probes through the emitted Thumb and screen renderer.

Stimuli are synthetic boundary/noise cases, not captured device measurements.
"""
import contextlib
import io
import unittest

from test_qc_continuity import Harness


class QCPlugFilter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import length_integrity
        with contextlib.redirect_stdout(io.StringIO()):
            cls.img = length_integrity.build_candidate()
        cls.data = bytes(cls.img.finalize().data)
        cls.state = cls.img.qc['state']

    def scene(self):
        h = Harness(self.data)
        h.enter()
        return h

    def sweep(self, h):
        target = len(h.reads) + 8
        for _ in range(68):
            h.poll()
            if len(h.reads) == target:
                break
        self.assertEqual(len(h.reads), target)
        h.s.call(self.img.qc_classic['ui']['draw'])
        return list(h.s.uc.mem_read(self.state + 32, 8))

    def test_every_single_connected_pin_maps_to_its_own_classic_indicator(self):
        for pin in range(8):
            with self.subTest(pin=pin):
                h = self.scene()
                h.values = [1000] * 8
                h.values[pin] = 900
                for _ in range(3):
                    actual = self.sweep(h)
                self.assertEqual(actual, [1 if i == pin else 2 for i in range(8)])
                for i in range(8):
                    color = h.s.fb[82 + 27 * (7 - i)][205]
                    self.assertEqual(color == 0x07E0, i == pin)

    def test_continuously_passing_counts_remain_green_despite_changing_magnitude(self):
        h = self.scene()
        passing = [1, 500, 900, 980, 990, 991, 992, 993]
        for sweep in range(20):
            h.values = [passing[(pin + sweep) % 8] for pin in range(8)]
            actual = self.sweep(h)
            if sweep >= 2:
                self.assertEqual(actual, [1] * 8)
        self.assertEqual([pin for pin, _, _ in h.reads], list(range(8)) * 20)

    def test_negative_control_pn224_boundary_chatter_rotates_screen(self):
        h = self.scene()
        # First qualify all eight pins. Then inject one count above the raw
        # threshold once per four scans, staggered across otherwise good pins.
        # This is a diagnostic negative control: the software cannot determine
        # whether such input variation came from a real contact or bad timing.
        # Fix the acquisition path rather than declaring both values passing.
        h.values = [993] * 8
        for _ in range(3):
            self.sweep(h)
        h.source = lambda pin, number: 994 if (number + pin) % 4 == 0 else 993
        frames = [self.sweep(h) for _ in range(8)]
        self.assertEqual(frames[-4:], [
            [1, 2, 2, 2, 1, 2, 2, 2],
            [2, 2, 2, 1, 2, 2, 2, 1],
            [2, 2, 1, 2, 2, 2, 1, 2],
            [2, 1, 2, 2, 2, 1, 2, 2],
        ])
        for pin in range(8):
            color = h.s.fb[82 + 27 * (7 - pin)][205]
            self.assertEqual(color == 0x07E0, frames[-1][pin] == 1)


if __name__ == '__main__':
    unittest.main()
