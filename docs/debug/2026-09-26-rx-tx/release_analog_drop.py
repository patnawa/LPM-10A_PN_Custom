"""Analog dropout diagnostic: actual current TX GPIO -> modeled link -> RX PWM.

No physical sensitivity claim. A >180 ms quiet span is flagged separately from
the normal 20..146 ms quiet cadence; weak/noisy/gated cases are observations,
not automatically bugs. The contact-loss control validates this detector.
"""
import argparse
from contextlib import redirect_stdout
import hashlib
import io
import json
import math
from pathlib import Path
import sys

SDK = Path(__file__).resolve().parents[3] / 'LPM-10A' / 'Firmware File' / 'rx-sdk'
sys.path.insert(0, str(SDK))
import auto_range
import clean_strength
import test_current_pair as pair
from test_rx_followup import ANALYZERS, GRADE
from test_rx_isolate import PWM, T1_CYCLES, T5_CYCLES, TIM1
from test_scan_acquisition_timing import TIMER_COUNTER
from verify_control import MODE, SP
from verify_digital import ACTIVE, GATE, RECENT
from unicorn import UC_HOOK_MEM_WRITE


def cases(group):
    if group == 'controls':
        yield 'steady', {}, lambda ms: 1
        yield 'contact-loss-negative-control', {}, lambda ms: not 2000 <= ms < 3000
    elif group == 'level':
        for amplitude in (30, 60, 120, 300, 1200, 2400, 6000, 30000):
            yield f'level-{amplitude}', {'amplitude': amplitude}, lambda ms: 1
    elif group == 'clock':
        for phase, ratio in ((0, 1), (.375, .997), (3.875, .997), (.375, 1.003), (3.875, 1.003)):
            yield f'phase-{phase}-ratio-{ratio}', {'phase': phase, 'ratio': ratio}, lambda ms: 1
    elif group == 'noise':
        for amplitude in (120, 300, 1200):
            for noise in (30, 60):
                yield f'level-{amplitude}-noise-{noise}', {
                    'amplitude': amplitude, 'noise': noise, 'phase': .375, 'ratio': 1.003}, lambda ms: 1
    elif group == 'envelope':
        yield '2Hz-modulation-300-to-1200', {}, lambda ms: .625 + .375 * math.sin(ms * 2 * math.pi / 500)
        yield '0.8Hz-modulation-1200-to-30000', {}, lambda ms: 13 + 12 * math.sin(ms * 2 * math.pi / 1250)
        yield 'steady-then-half-strength', {'amplitude': 6000}, lambda ms: 1 if ms < 2000 else .5
    elif group == 'knob':
        for amplitude in (1200, 6000, 30000):
            for knob in (2048, 3072, 4095):
                yield f'level-{amplitude}-knob-{knob}', {
                    'knob': knob, 'amplitude': amplitude}, lambda ms: 1


def simulate(runner, data, *, envelope, amplitude=1200, knob=4095,
             phase=0, ratio=1, noise=0, end_ms=4000):
    cpu = pair.TransportCPU(data, mode=1, trace=runner.traces[1], phase=phase,
                            ratio=ratio, noise=noise,
                            contact=lambda ms: amplitude / 1200 * envelope(ms))
    cpu.knob_raw = knob
    runner.boundary(cpu)
    edges, states, publications, sound = [], [], [], False

    def pwm(uc, access, address, size, value, user):
        nonlocal sound
        active = value != 800
        if active != sound:
            edges.append((cpu.read(TIMER_COUNTER, 4) * T5_CYCLES / 64000, active))
            sound = active

    hook = cpu.uc.hook_add(UC_HOOK_MEM_WRITE, pwm, begin=PWM, end=PWM + 1)
    previous = None
    try:
        for ms in range(1, end_ms + 1):
            runner.timers(cpu, ms * T1_CYCLES // T5_CYCLES - cpu.read(TIMER_COUNTER, 4))
            runner.execute(cpu, TIM1, stack=SP - 0x500, budget=10000)
            runner.boundary(cpu)
            if not cpu.read(ACTIVE):
                runner.execute(cpu, ANALYZERS[1], budget=150000)
                publications.append((ms, cpu.read(GRADE), cpu.read(RECENT, 2), cpu.read(auto_range.STATE)))
            state = (cpu.read(MODE), cpu.read(auto_range.STATE), cpu.read(GRADE),
                     cpu.read(RECENT, 2) > 500, cpu.read(GATE, 2))
            if state != previous:
                states.append((ms, *state))
                previous = state
    finally:
        cpu.uc.hook_del(hook)
    # Include a trailing silence: otherwise a dropout that never recovers is missed.
    segments = [(0, False)] + edges + [(end_ms, True)]
    quiet = [(max(a, 1000), b, b - max(a, 1000))
             for (a, on), (b, _) in zip(segments, segments[1:]) if not on and b > 1000]
    return {'edges': edges, 'states': states, 'publications': publications,
            'state_columns': ['ms', 'mode', 'gain', 'grade', 'fresh_audio', 'gate'],
            'publication_columns': ['ms', 'grade', 'recent', 'gain'],
            'first_on_ms': next((ms for ms, active in edges if active), None),
            'max_quiet_ms_after_1s': max((duration for _, _, duration in quiet), default=0),
            'long_quiet_spans': [span for span in quiet if span[2] > 180], 'end_ms': end_ms}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('group', choices=('controls', 'level', 'clock', 'noise', 'envelope', 'knob'))
    parser.add_argument('--end-ms', type=int, default=4000)
    args = parser.parse_args()
    pair.CurrentPair.setUpClass()
    runner = pair.CurrentPair('test_fixture_executes_the_current_pair')
    with redirect_stdout(io.StringIO()):
        baseline = bytes(clean_strength.build_candidate().data)
    images = {'pn1.30': baseline, 'pn1.31': runner.data}
    report = {'scope': __doc__, 'tx_sha256': runner.tx_sha,
              'rx_sha256': {name: hashlib.sha256(data).hexdigest() for name, data in images.items()},
              'complete': False, 'trials': []}
    path = Path(__file__).with_name(f'release_analog_drop_{args.group}.json')
    for name, parameters, envelope in cases(args.group):
        for version, data in images.items():
            result = simulate(runner, data, envelope=envelope, end_ms=args.end_ms, **parameters)
            report['trials'].append({'case': name, 'version': version, 'parameters': parameters, **result})
            path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
            print(json.dumps({'case': name, 'version': version, 'first_on_ms': result['first_on_ms'],
                              'max_quiet_ms': result['max_quiet_ms_after_1s'],
                              'long_quiet_spans': result['long_quiet_spans'],
                              'states': result['states']}), flush=True)
    if args.group == 'controls':
        for row in report['trials']:
            expected_gap = row['case'] == 'contact-loss-negative-control'
            assert bool(row['long_quiet_spans']) == expected_gap, row
    report['complete'] = True
    path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(f'Complete: {path}', flush=True)


if __name__ == '__main__':
    main()
