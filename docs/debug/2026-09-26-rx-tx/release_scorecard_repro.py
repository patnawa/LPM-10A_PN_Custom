"""Diagnostic-only regression: an inaudible target cannot be identified by ear.

Run from the repository root:
    python docs/debug/2026-09-26-rx-tx/release_scorecard_repro.py

Both assertions fail against the original scoring implementation and pass after
the target-audibility correction in cabinet_scorecard.py.
The second test runs the exact PN1.30 ARM firmware with modeled ADC input. This
proves a scorecard false positive, not a new firmware or physical-pickup defect.
No firmware artifacts are written or flashed.
"""
from contextlib import redirect_stdout
import hashlib
import io
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "LPM-10A" / "Firmware File" / "rx-sdk"))

import cabinet_scorecard as scorecard
import clean_strength


class AudibleIdentification(unittest.TestCase):
    def test_minimal_silent_target_and_neighbor_are_not_identified(self):
        visits = [("T", 0.0), ("N3", 0.0)]
        result = scorecard.score(visits)
        self.assertFalse(result[0], f"silent visits={visits}, score={result}")

    def test_real_pn130_silent_analog_trace_is_not_identified(self):
        with redirect_stdout(io.StringIO()):
            data = bytes(clean_strength.build_candidate().data)
        self.assertEqual(hashlib.sha256(data).hexdigest(),
                         "407b0ba3b80883e4f640ef7e2040a56004ca780a5bd8b81cf3a371ca04a67135")
        visits = scorecard.visit_fractions(data, mode=1, knob=512, target=3000)
        self.assertTrue(all(fraction == 0.0 for _, fraction in visits), visits)
        result = scorecard.score(visits)
        self.assertFalse(result[0], f"PN1.30 Analog knob=512: visits={visits}, score={result}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
