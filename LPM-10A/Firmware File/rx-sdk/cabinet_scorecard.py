"""Cabinet identification scorecard: can a listener pick the toned pair out of a bundle?

The owner's task (2026-09-23): touch the pairs of a telephone cabinet one after another and
tell, by ear, which one carries the TX tone. This runs the real receiver firmware (TIM1/TIM5
handlers, sampler, automatic gain, analysers, publisher, speaker PWM) in Unicorn while the
modeled probe visits the pairs of a bundle in a fixed order, and scores what the speaker
does on each visit once it has settled.

Scenario: the toned pair T at a link amplitude (3 000 moderate, 10 000 strong, 30 000 very
strong at contact) and neighbours 3, 6 and 10 dB weaker, visited in the order
N3 N6 T N10 N3 T N6 (each 2 s, no gap), so every neighbour is heard both before and after
the toned pair.

A visit is scored on the tone fraction of the rhythm published over its last 1.2 s. The toned pair is identified when
every neighbour visit's pulse period is at least 12 % longer than every toned-pair visit's
(or the neighbour is silent); 12 % is above the 5-10 % at which a change of tempo is heard.
Repeatability: the spread of one pair's tone fraction across its visits.

    python cabinet_scorecard.py [pn1.24 pn1.27 ...]      (default: every known build)

Modeled ADC, link, coupling and interrupts; not a measurement of real pickup.
"""
import contextlib
import io
import sys

from test_rx_isolate import Streams

DWELL = 2000
SETTLED = 1200
ORDER = ('N3', 'N6', 'T', 'N10', 'N3', 'T', 'N6')
DEFICIT = {'T': 0, 'N3': -3, 'N6': -6, 'N10': -10}
TARGETS = (3000, 10000, 30000)
KNOBS = (4095, 3072, 2048, 1536, 1024, 768, 512, 256)
PERIOD_JND = 1.12


def builds():
    import rx_precision, knob_reference, pair_rank, level_display
    with contextlib.redirect_stdout(io.StringIO()):
        return {'pn1.24': bytes(rx_precision.build_candidate().data),
                'pn1.27': bytes(knob_reference.build_candidate().data),
                'pn1.28': bytes(pair_rank.build_candidate().data),
                'pn1.29': bytes(level_display.build_candidate().data)}


class _Runner(Streams):
    def runTest(self):
        pass


PULSE_MS = (30, 12)                 # Digital, Analog tracing pulse


def published_fraction(row, start, end, pulse):
    """Tone fraction of the rhythm the firmware publishes, time-weighted over [start, end).

    The speaker plays each published interval by construction; counting pulses in a 1.2 s
    window adds +-1 pulse of noise, about the size of one display step. A rejected or absent
    publication (interval 0, or no fresh audio) counts as silence."""
    pubs = row['publications']
    total = 0.0
    for (ms, interval, recent), (nxt, _, _) in zip(pubs, pubs[1:] + [(end, 0, 0)]):
        lo, hi = max(ms, start), min(nxt, end)
        if hi <= lo:
            continue
        if interval == 1:
            interval = 20                       # 'uncertain' plays as the fastest rhythm (PN 1.18)
        sounding = interval > 0 and recent > 500
        total += (hi - lo) * (pulse / (pulse + interval) if sounding else 0.0)
    return total / (end - start)


def visit_fractions(data, *, mode, knob, target):
    runner = _Runner()
    amplitude = lambda ms: target * 10 ** (DEFICIT[ORDER[min(int(ms // DWELL), len(ORDER) - 1)]] / 20)
    row = runner.stream(data, mode=mode, knob=knob, amplitude=amplitude, end_ms=DWELL * len(ORDER))
    return [(pair, published_fraction(row, (n + 1) * DWELL - SETTLED, (n + 1) * DWELL, PULSE_MS[mode]))
            for n, pair in enumerate(ORDER)]


def score(visits):
    toned = [f for p, f in visits if p == 'T']
    worst = min(toned)
    failures = [(p, round(f, 2)) for p, f in visits
                if p != 'T' and f > 0.02 and worst < PERIOD_JND * f]
    spread = {p: round(max(fs) - min(fs), 2) for p in DEFICIT
              for fs in [[f for q, f in visits if q == p]] if len(fs) > 1}
    return not failures, failures, spread


def main(argv):
    images = builds()
    names = argv or list(images)
    for mode in (0, 1):
        for name in names:
            passed = 0
            for target in TARGETS:
                for knob in KNOBS:
                    visits = visit_fractions(images[name], mode=mode, knob=knob, target=target)
                    ok, failures, spread = score(visits)
                    passed += ok
                    print(f'mode {mode} {name} T {target:5} knob {100 * knob / 4095:3.0f}% '
                          f'{"OK  " if ok else "FAIL"} '
                          f'{" ".join(f"{p}:{f:.2f}" for p, f in visits)}  spread {spread}'
                          + (f'  wrong {failures}' if failures else ''))
                    sys.stdout.flush()
            print(f'== mode {mode} {name}: identified {passed}/{len(TARGETS) * len(KNOBS)}')
            sys.stdout.flush()
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
