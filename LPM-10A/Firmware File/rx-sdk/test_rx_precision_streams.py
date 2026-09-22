"""Combined RX candidate through real timer, gain, analyzer and speaker code."""
import contextlib
import io
import unittest

import test_rx_digital_strong_gain as strong


class PrecisionStreams(strong.StrongGainStream):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        import rx_precision
        with contextlib.redirect_stdout(io.StringIO()):
            cls.candidate = rx_precision.build_candidate()
        cls.data = bytes(cls.candidate.data)

    def test_both_modes_restore_gain_without_the_old_two_second_hold(self):
        for mode in (0, 1):
            with self.subTest(mode=mode):
                row = self.run_stream(
                    mode=mode, changes={}, end_ms=1850,
                    source_pp=lambda ms: 4000 if ms < 1000 else 40)
                self.assertEqual(row['transitions'], [(500, 7, 2), (1500, 2, 7)])
                self.assertFalse(row['unowned_refreshes'])
                self.assertGreater(row['final_grade'], 0)


if __name__ == '__main__':
    unittest.main()
