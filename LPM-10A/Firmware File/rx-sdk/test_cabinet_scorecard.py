"""Identification requires hearing the target, then separating its neighbours."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import statistics
import tempfile
import unittest
from unittest.mock import patch

import cabinet_scorecard as scorecard


class Identification(unittest.TestCase):
    def test_silence_and_one_missed_target_visit_cannot_pass(self):
        for visits in ([('T', 0.0), ('N3', 0.0)],
                       [('T', 0.3), ('N3', 0.0), ('T', 0.0)],
                       [('T', 0.02), ('N3', 0.0)]):
            with self.subTest(visits=visits):
                identified, failures, _ = scorecard.score(visits)
                self.assertFalse(identified)
                self.assertTrue(any(pair == 'T' for pair, _ in failures))

    def test_audible_target_can_be_detected_without_being_identifiable(self):
        result = scorecard.assess([('T', 0.3), ('N3', 0.3), ('T', 0.31)])
        self.assertTrue(result.detected)
        self.assertFalse(result.identified)
        self.assertEqual(result.status, 'AMBIGUOUS')

    def test_audible_separated_target_keeps_historical_success(self):
        visits = [('T', 0.3), ('N3', 0.2), ('T', 0.31), ('N6', 0.0)]
        result = scorecard.assess(visits)
        self.assertTrue(result.detected)
        self.assertTrue(result.identified)
        self.assertEqual(result.status, 'IDENTIFIED')
        self.assertEqual(scorecard.score(visits), (True, [], {'T': 0.01}))

    def test_a_fixture_without_a_target_is_invalid(self):
        with self.assertRaisesRegex(ValueError, 'target'):
            scorecard.assess([('N3', 0.0)])

    def test_cli_reports_detection_identification_and_misses_separately(self):
        cases = {1: [('T', 0.0), ('N3', 0.0)],
                 2: [('T', 0.3), ('N3', 0.3)],
                 3: [('T', 0.3), ('N3', 0.2)]}
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(scorecard, 'builds', return_value={'fixture': b''}), \
                patch.object(scorecard, 'TARGETS', (3000,)), \
                patch.object(scorecard, 'KNOBS', (1, 2, 3)), \
                patch.object(scorecard, 'visit_fractions',
                             side_effect=lambda data, *, mode, knob, target: cases[knob]), \
                redirect_stdout(io.StringIO()) as output:
            report_path = Path(directory) / 'result.json'
            self.assertEqual(scorecard.main(['fixture', '--report', str(report_path)]), 0)
            report = json.loads(report_path.read_text(encoding='utf-8'))
            self.assertTrue(report['complete'])
            self.assertEqual(len(report['trials']), 6)
            self.assertEqual(len(report['summaries']), 2)
            for row in report['summaries']:
                self.assertEqual((row['detected'], row['identified'], row['missed'], row['ambiguous']),
                                 (2, 1, 1, 1))
        text = output.getvalue()
        self.assertIn('MISSED', text)
        self.assertIn('AMBIGUOUS', text)
        self.assertIn('IDENTIFIED', text)
        self.assertEqual(text.count('detected 2/3, identified 1/3, missed 1/3, ambiguous 1/3'), 2)

    def test_interrupted_run_preserves_completed_trials_as_incomplete(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(scorecard, 'builds', return_value={'fixture': b'fixture'}), \
                patch.object(scorecard, 'TARGETS', (3000,)), \
                patch.object(scorecard, 'KNOBS', (1, 2)), \
                patch.object(scorecard, 'visit_fractions',
                             side_effect=[[('T', 0.3), ('N3', 0.2)], KeyboardInterrupt]), \
                redirect_stdout(io.StringIO()):
            report_path = Path(directory) / 'result.json'
            with self.assertRaises(KeyboardInterrupt):
                scorecard.main(['fixture', '--report', str(report_path)])
            self.assertTrue(report_path.exists(), 'completed trials must survive interruption')
            report = json.loads(report_path.read_text(encoding='utf-8'))
            self.assertFalse(report['complete'])
            self.assertEqual(len(report['trials']), 1)
            self.assertEqual(report['trials'][0]['status'], 'IDENTIFIED')
            self.assertEqual(report['summaries'], [])
            self.assertIn('fixture', report['sha256'])


class CurrentFirmware(unittest.TestCase):
    def test_pn130_analog_below_the_knob_gate_is_a_miss(self):
        import clean_strength
        with redirect_stdout(io.StringIO()):
            data = bytes(clean_strength.build_candidate().data)
        visits = scorecard.visit_fractions(data, mode=1, knob=512, target=3000)
        self.assertTrue(all(fraction == 0.0 for _, fraction in visits), visits)
        result = scorecard.assess(visits)
        self.assertFalse(result.detected)
        self.assertFalse(result.identified)
        self.assertEqual(result.status, 'MISSED')

    def test_published_fraction_uses_the_actual_speaker_pulse_lengths(self):
        import rx_resilient
        import test_rx_isolate as fixture
        from unicorn import UC_HOOK_MEM_WRITE
        from mode_tone import KEEP_ALIVE

        countdown_writes = []

        class ObservedCPU(fixture.FieldCPU):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.uc.hook_add(UC_HOOK_MEM_WRITE,
                                 lambda uc, access, address, size, value, user: countdown_writes.append(value),
                                 begin=KEEP_ALIVE, end=KEEP_ALIVE)

        with redirect_stdout(io.StringIO()):
            data = bytes(rx_resilient.build_candidate().data)
        for mode, changes in ((0, {}), (1, {}), (0, {300: 1})):
            with self.subTest(mode=mode, changes=changes), patch.object(fixture, 'FieldCPU', ObservedCPU):
                countdown_writes.clear()
                row = scorecard._Runner().stream(data, mode=mode, knob=4095,
                                                amplitude=lambda ms: 1200, end_ms=1500,
                                                mode_changes=changes)
                widths = [end - start for (start, on), (end, next_on)
                          in zip(row['edges'], row['edges'][1:]) if start >= 800 and on and not next_on]
                self.assertGreater(len(widths), 3)
                final_mode = 1 if changes else mode
                self.assertEqual(row['mode'], final_mode)
                self.assertEqual(max(countdown_writes), scorecard.PULSE_MS[final_mode])
                self.assertAlmostEqual(statistics.median(widths), scorecard.PULSE_MS[final_mode],
                                       delta=1.0, msg=f'mode {final_mode}: widths={widths}')


if __name__ == '__main__':
    unittest.main()
