"""Short Analog visits and isolated noise against the complete PN 1.11 image.

No new qualification policy is applied. These characterize the tradeoff that
would be hidden by tests containing only sustained tones or only noise.
"""
import hashlib
import math
from pathlib import Path
import random
import sys
import unittest

import test_rx_analog_feedback as analog
import test_tracking_integration
from test_rx_followup import GRADE
from verify_control import BEEP

sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'docs'/'experiments'))
import analog_temporal_followup as temporal


class AnalogTransients(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.img=test_tracking_integration.candidate()
        cls.data=bytes(cls.img.data)
        if hashlib.sha256(cls.data).hexdigest() != '3e39ae56832cf92881ffdc46564e293278d6c3f1b55a9832b7a9a8350f031828':
            raise AssertionError('transient audit requires the exact delivered PN 1.11 artifact')
        cls.previous=bytes(analog.test_rx_robust.candidate().data)

    cpu=analog.AnalogFeedback.cpu
    execute=analog.AnalogFeedback.execute
    analog_cpu=analog.AnalogFeedback.analog_cpu
    analyze=analog.AnalogFeedback.analyze
    speaker=analog.AnalogFeedback.speaker

    def check_isolated_window(self,samples):
        c=self.analog_cpu()
        grade=self.analyze(c,samples)
        self.assertGreater(grade,1)
        self.speaker(c)
        self.assertEqual(c.read(BEEP),30)
        for tick in range(1,201):
            c.run()
            if tick%21==0:
                self.analyze(c,[2048]*64)
                self.assertEqual(c.read(GRADE),0)
            self.speaker(c)
            self.assertEqual(c.read(BEEP),max(0,30-tick))

    def test_weak_single_window_visit_is_detected_then_releases_without_repeating(self):
        for phase in range(16):
            samples=analog.sine(25,phase=phase*2*math.pi/16)
            self.check_isolated_window(samples)
        self.assertEqual(temporal.decisions([-100,21,-100],'two_windows'),[False]*3)
        self.assertEqual(temporal.decisions([-100,21,-100],'strong_or_two'),[False]*3)

    def test_known_isolated_noise_window_can_also_produce_one_short_indication(self):
        rng=random.Random(0x825C0F+1600)
        for _ in range(425):
            samples=[2048+rng.randint(-1600,1600) for _ in range(64)]
        # This is a deterministic no-transmitter stimulus, not a field rate.
        self.assertGreater(temporal.classify(samples)['margin'],200)
        self.check_isolated_window(samples)


if __name__=='__main__': unittest.main()
