"""Steady-signal precision loop for the RX display: one constant signal, every window's raw score.

The owner's probe held still on one pair must give one steady level. This runs the real receiver
firmware (sampler, detector, estimator, display, AGC, TIM1 tick) in Unicorn on a constant
modeled signal and reports, after the gain has settled, the spread of the raw Digital/Analog
strength score (the transmitter's 5.05 ms chip drifts through the receiver's 5 ms slot in the
model, as on the device), how often the displayed level changes, and the gain-step timeline.

    python steady_probe.py                       PN1.29 and PN1.30, Digital, knob 100 %, six strengths
    python steady_probe.py pn1.30 --mode 1 --knob 768 --amp 300 3000 30000

Modeled ADC and link; not a measurement of real pickup or noise.
"""
import argparse
import contextlib
import io
import statistics
import sys

from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0

import auto_range
import level_display as lvl
from test_rx_followup import ANALYZERS, GRADE
from test_rx_isolate import FieldCPU, Streams, T1_CYCLES, T5_CYCLES, TIM1
from test_scan_acquisition_timing import TIMER_COUNTER
from verify_control import SP, MODE
from verify_digital import ACTIVE

# Strengths 0.2-1.0 dB above a level threshold at knob 100 % (the zone PN1.29 flickered in), and two more.
AMPLITUDES = (680, 720, 745, 1000, 300, 2000)


def builds():
    import clean_strength
    with contextlib.redirect_stdout(io.StringIO()):
        pn129 = lvl.build_candidate()
        pn130 = clean_strength.build_candidate()
    return {'pn1.29': (bytes(pn129.data), pn129.level_display['curve']),
            'pn1.30': (bytes(pn130.data), pn130.clean_strength['curve'])}


class _Runner(Streams):
    def runTest(self):
        pass

    def probe(self, data, curve, *, mode, knob, amplitude, end_ms):
        c = FieldCPU(data, mode=mode, knob=knob)
        c.amplitude = lambda tick: amplitude(tick * T5_CYCLES / 64000)
        self.boundary(c)
        rows, steps, last = [], [], [None]
        hook = c.uc.hook_add(UC_HOOK_CODE, lambda uc, a, s, u: last.__setitem__(0, uc.reg_read(UC_ARM_REG_R0)),
                             begin=curve, end=curve)
        try:
            for ms in range(1, end_ms + 1):
                self.timers(c, ms * T1_CYCLES // T5_CYCLES - c.read(TIMER_COUNTER, 4))
                before = c.read(auto_range.STATE)
                self.execute(c, TIM1, stack=SP - 0x500, budget=10000)
                if c.read(auto_range.STATE) != before:
                    steps.append((ms, before, c.read(auto_range.STATE)))
                self.boundary(c)
                if not c.read(ACTIVE):
                    last[0] = None
                    self.execute(c, ANALYZERS[c.read(MODE)], budget=150000)
                    rows.append((ms, last[0], c.read(auto_range.STATE), c.read(lvl.AVERAGE + 4), c.read(GRADE)))
        finally:
            c.uc.hook_del(hook)
        return rows, steps


def report(name, data, curve, *, mode, knob, amp, end_ms, settle_ms):
    rows, steps = _Runner().probe(data, curve, mode=mode, knob=knob, amplitude=lambda ms: amp, end_ms=end_ms)
    settled = [r for r in rows if r[0] >= settle_ms and r[1] is not None]
    if not settled:
        return f'{name} mode {mode} knob {knob} amp {amp:6.0f}: no scored windows after {settle_ms} ms; gain steps {steps}'
    scores = [r[1] for r in settled]
    med = statistics.median(scores)
    shown = [r[3] for r in settled]
    changes = sum(a != b for a, b in zip(shown, shown[1:]))
    low = sum(s < 0.95 * med for s in scores)
    return (f'{name} mode {mode} knob {knob} amp {amp:6.0f}: gain steps {steps}; {len(settled)} windows after '
            f'{settle_ms} ms; score min/median {min(scores) / med:.2f}, {low} windows below -0.5 dB; '
            f'level(s) {sorted(set(shown))}, {changes} changes ({changes * 1000 / (end_ms - settle_ms):.1f}/s)')


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('builds', nargs='*', help='pn1.29 pn1.30 (default: both)')
    parser.add_argument('--mode', type=int, default=0, help='0 Digital, 1 Analog')
    parser.add_argument('--knob', type=int, default=4095, help='knob reading 0..4095')
    parser.add_argument('--amp', type=float, nargs='+', default=AMPLITUDES, help='link amplitudes')
    parser.add_argument('--end', type=int, default=6000)
    parser.add_argument('--settle', type=int, default=1000)
    args = parser.parse_args(argv)
    images = builds()
    for name in args.builds or list(images):
        data, curve = images[name]
        for amp in args.amp:
            print(report(name, data, curve, mode=args.mode, knob=args.knob, amp=amp, end_ms=args.end,
                         settle_ms=args.settle))
            sys.stdout.flush()
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
