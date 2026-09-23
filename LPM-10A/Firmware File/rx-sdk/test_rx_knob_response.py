"""Owner report 2026-09-23 on RX PN1.26: "เสียง Rx แรงตลอด ตั้งแต่ 10% หมุนเพิ่ม ลด ไม่ต่าง".

One cable, probe held still (the receiver's only and strongest signal): the tone must be
audible from low on the knob, and turning the knob must change the rhythm -- lower knob,
slower rhythm, for a signal that is not overwhelming. Executes the real analyser, curve,
publisher and peak code on one fresh window per case; ADC values are modeled.
"""
import contextlib
import io
import unittest

import knob_reference as pn127
import relative_isolate as pn126
import rx_precision
import test_rx_relative_isolate as harness
from verify_digital import pattern

KNOBS = (410, 1024, 1638, 2048, 3072, 4095)          # 10, 25, 40, 50, 75, 100 % of travel
# (name, B6 amplitude in ADC counts, driven gain level): normalised strength about
# -30 dB, -12 dB, 0 dB and +10 dB relative to the full gain's saturation (40 000).
SIGNALS = (('weak', 60, 7), ('moderate', 470, 7), ('near', 1870, 7), ('touching', 2270, 2))
CANDIDATES = {}


def setUpModule():
    with contextlib.redirect_stdout(io.StringIO()):
        CANDIDATES['PN1.24'] = bytes(rx_precision.build_candidate().data)
    CANDIDATES['PN1.26'] = bytes(pn126.build_candidate().data)
    CANDIDATES['PN1.27'] = bytes(pn127.build_candidate().data)


class KnobResponse(harness.Analysers, unittest.TestCase):
    def entry(self, data):
        return 0x0800A048                               # every image's Digital curve entry

    def intervals(self, data):
        """{signal: [published quiet interval or None (muted) per knob]} for a lone steady signal."""
        table = {}
        for name, amplitude, level in SIGNALS:
            row = []
            for knob in KNOBS:
                state, scores, _ = self.analyse(data, pattern(0, 800, 800 + amplitude), knob=knob,
                                                level=level, grade=0, recent=0, peak=0, elapsed=0)
                self.assertTrue(scores, (name, knob))
                row.append(state[0] if state[1] == 800 else None)
            table[name] = row
        return table

    def verdict(self, table):
        problems = []
        for name, row in table.items():
            if None in row:
                problems.append(f'{name}: muted at knob {KNOBS[row.index(None)]} although it is the only signal')
                continue
            if any(low < high for low, high in zip(row, row[1:])):
                problems.append(f'{name}: rhythm gets slower as the knob rises {row}')
        for name in ('moderate', 'near'):
            row = table[name]
            if None not in row and row[0] <= row[-1]:
                problems.append(f'{name}: knob 10 % sounds as fast as 100 % {row}')
        return problems

    def report(self, label):
        table = self.intervals(CANDIDATES[label])
        print(label, 'quiet interval ms at knob', [f'{100 * k / 4095:.0f}%' for k in KNOBS])
        for name, row in table.items():
            print(f'   {name:9}', row)
        return self.verdict(table)

    def test_pn126_reproduces_the_owner_report(self):
        problems = self.report('PN1.26')
        print('PN1.26 problems:', problems)
        self.assertTrue(any('as fast as 100 %' in p for p in problems))

    def test_candidate_follows_the_knob_and_stays_audible(self):
        label = next(reversed(CANDIDATES))
        self.assertEqual(self.report(label), [], label)


if __name__ == '__main__':
    unittest.main()
