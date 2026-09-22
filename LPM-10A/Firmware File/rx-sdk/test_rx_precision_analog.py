"""Check final PN1.24 Analog decisions, including the composed age guards."""
import contextlib
import io
import unittest

import digital_gain_continuity
import rx_precision
import sample_age_guard
import test_rx_analog_selective as selective


class PrecisionAnalog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with contextlib.redirect_stdout(io.StringIO()):
            cls.previous = bytes(digital_gain_continuity.build_candidate().data)
            cls.img = rx_precision.build_candidate()
        cls.data = bytes(cls.img.data)

    cpu = selective.AnalogSelective.cpu
    execute = selective.AnalogSelective.execute
    analyze = selective.AnalogSelective.analyze

    def ready(self, c, samples):
        selective.AnalogSelective.ready(self, c, samples)
        # Direct analyzer vectors represent just-completed current-gain frames.
        # Separate timer-driven suites establish the marker's actual ownership.
        c.w32(sample_age_guard.TIMER_COUNTER, 123456)
        c.w32(sample_age_guard.COMPLETED_AT, 123456)
        c.w32(sample_age_guard.COMPLETED_VALID, 1)

    test_fresh_decisions_and_strength_match_g = (
        selective.AnalogSelective.test_phase_amplitude_dc_noise_wrong_frequency_and_rails_are_bit_exact)
    test_composed_instruction_and_stack_cost = (
        selective.AnalogSelective.test_instruction_and_stack_cost_decrease_without_changing_strength)


if __name__ == '__main__':
    unittest.main()
