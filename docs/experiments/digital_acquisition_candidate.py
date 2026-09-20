"""Independent reduced-ADC model of a legacy B6 acquisition candidate.

The released PN 1.9/1.10 model is imported only for paired comparison. This
does not patch firmware and makes no physical cable/Fluke performance claim.
Run: python docs/experiments/digital_acquisition_candidate.py
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import math
import random
import statistics

import digital_bundle_audit as prior
from scan_sync_model import sampled_window

CODE = prior.CODE
SEED = 20260920


def median(values):
    return int(statistics.median(values))


def measure(samples):
    """V4: robust full-window fit, preserving established fallback eligibility.

    The established global slicer/fallback preserves clock drift tolerance.
    The local path has priority so a recent weak segment is not obscured by
    a previously strong segment which still passes an old exact-code span.
    """
    assert len(samples) == 48 and all(0 <= x <= 4095 for x in samples)
    old = prior.measure(samples)
    bits, levels = [], []
    for start in range(0, 48, 8):
        ordered = sorted(samples[start:start+8])
        low, high = ordered[1], ordered[5]
        levels.append(high-low)
        threshold = (low+high)//2
        bits.extend(int(x > threshold) for x in samples[start:start+8])
    result = {'gap': 0, 'amplitude': None, 'reason': 'rejected'}
    # A clean B6 frame always has three lows and five highs. At least five
    # of the six frames must resolve a useful level separation.
    phases = []
    if sum(level >= 9 for level in levels) >= 5:
        for phase in range(8):
            wanted = [CODE[(i+phase) % 8] for i in range(48)]
            errors = [actual != expected for actual, expected in zip(bits, wanted)]
            if sum(errors) <= 4 and all(sum(errors[i:i+16]) <= 2 for i in (0, 16, 32)):
                phases.append((phase, wanted))
    if len(phases) == 1:
        phase, wanted = phases[0]
        return strength(samples, range(32, 48), wanted, phase, 'local_fit')
    if old['gap']:
        threshold = old['threshold']
        bits = [int(x > threshold) for x in samples]
        if old['phase'] is None:
            starts = [i for i in range(33) if bits[i:i+16] == list(CODE*2)]
            selected = range(starts[-1], starts[-1]+16)
            wanted = bits
        else:
            selected = range(32, 48)
            wanted = [CODE[(i+old['phase']) % 8] for i in range(48)]
        return strength(samples, selected, wanted, old['phase'], 'established')
    return result


def strength(samples, selected, wanted, phase, reason):
    result = {'gap': 0, 'amplitude': None, 'reason': 'rejected'}
    lo = median([samples[i] for i in selected if not wanted[i]])
    hi = median([samples[i] for i in selected if wanted[i]])
    amplitude = hi-lo
    if hi == 4095 or amplitude <= 0:
        result.update(gap=1, reason='uncertain', phase=phase)
    else:
        result.update(gap=prior.gap_for_amplitude(amplitude), amplitude=amplitude,
                      reason=reason, phase=phase)
    return result


def overlap_tracking():
    """Steady tracking after a prior complete48-sample lock, new16 each step."""
    rows = []
    for before, after in ((100, 300), (300, 100), (60, 3000), (3000, 60), (300, 0)):
        latencies, first_update = [], Counter()
        for phase in range(8):
            for cut in range(16):
                for end in range(16, 97, 16):
                    samples = [1000+CODE[(i+phase)%8]*(before if i < cut else after)
                               for i in range(end-48, end)]
                    result = measure(samples)
                    desired = prior.gap_for_amplitude(after) if after else 0
                    if end == 16:
                        first_update['settled' if result['gap'] == desired else 'pending'] += 1
                    if result['gap'] == desired:
                        latencies.append((end-cut)*prior.SAMPLE_MS)
                        break
                else:
                    raise AssertionError(('no settled overlap result', before, after, phase, cut))
        rows.append({'before': before, 'after': after, 'cases': len(latencies),
                     'first_update': dict(first_update),
                     'settled_latency_ms_range': [min(latencies), max(latencies)]})
    return {'convention': 'Steady state after startup; step at reduced-sample boundary cut*T; '
                         'next publications at16*T,32*T,...; ADC aperture, CPU time and audio '
                         'scheduling excluded. New startup still requires48 samples.',
            'transitions': rows}


def paired(rows):
    counts = Counter()
    examples, gains, acceptances = [], [], []
    for label, samples in rows:
        old, new = prior.measure(samples), measure(samples)
        counts['total'] += 1
        counts['old_accepted'] += bool(old['gap'])
        counts['new_accepted'] += bool(new['gap'])
        counts['gained'] += not old['gap'] and bool(new['gap'])
        counts['lost'] += bool(old['gap']) and not new['gap']
        if old['gap'] and not new['gap'] and len(examples) < 12:
            examples.append({'name': label, 'samples': samples, 'old': old, 'new': new})
        if new['gap'] and not old['gap'] and len(gains) < 12:
            gains.append({'name': label, 'samples': samples, 'old': old, 'new': new})
        if new['gap'] and len(acceptances) < 12:
            acceptances.append({'name': label, 'old': old, 'new': new})
    return {**dict(counts), 'lost_examples': examples, 'gained_examples': gains,
            'first_accepted_examples': acceptances}


def benchmark(noise_windows=16384):
    old_cases = prior.cases()
    counterexamples = paired((row['name'], row['samples']) for row in old_cases)
    movement = []
    for old, new in ((100, 300), (300, 100), (100, 1000), (1000, 100),
                     (60, 3000), (3000, 60)):
        counts = Counter()
        times = []
        for row in old_cases:
            if row.get('old') != old or row.get('new') != new:
                continue
            result = measure(row['samples'])
            state = ('new_rank' if result['gap'] == prior.gap_for_amplitude(new)
                     else 'rejected' if not result['gap'] else 'intermediate_or_old')
            counts[state] += 1
            windows = 1 if state == 'new_rank' else 2
            times.append((windows*48-row['cut'])*prior.SAMPLE_MS)
        movement.append({'old': old, 'new': new, 'counts': dict(counts),
                         'settled_latency_ms_max': max(times)})
    phase_clock = []
    for fresh in (False, True):
        for ratio in (0.98, 0.99, 0.997, 0.999, 1.0, 1.001, 1.003, 1.01, 1.02):
            for noise in (0, 50, 100, 200, 300):
                phase_clock.append({'fresh_start': fresh, 'ratio': ratio,
                                    'uniform_raw_noise_half_range': noise,
                                    **paired((f'phase_{index}/16', sampled_window(
                                        'legacy', index/16, ratio, noise,
                                        random.Random(SEED+index), amplitude=300,
                                        fresh_start=fresh)) for index in range(128))})
    competing = []
    legitimate = {sum(CODE[(i+p) % 8] << (7-i) for i in range(8)) for p in range(8)}
    for word in range(256):
        if word in legitimate:
            continue
        bits = [(word >> (7-i % 8)) & 1 for i in range(48)]
        competing.append((f'period8_{word:02x}', [1000+300*x for x in bits]))
    wrong_periods = []
    for period in (2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 16, 24, 32):
        for duty in (0.25, 0.5, 0.75):
            for phase in range(period*4):
                wrong_periods.append((f'square_p{period}_d{duty}_phase{phase}',
                    [1000+300*int((i+phase/4) % period < period*duty) for i in range(48)]))
                wrong_periods.append((f'sine_p{period}_phase{phase}',
                    [1000+round(300*math.sin((i+phase/4)*2*math.pi/period))
                     for i in range(48)]))
    random_rows = []
    for index in range(noise_windows):
        rng = random.Random(SEED+100000+index)
        random_rows.append((f'uniform_{index}', [rng.randrange(4096) for _ in range(48)]))
        random_rows.append((f'binary_{index}', [1000+300*rng.randrange(2) for _ in range(48)]))
        values = [1000]
        for _ in range(47):
            values.append(max(0, min(4095, values[-1]+rng.randint(-100,100))))
        random_rows.append((f'random_walk_{index}', values))
    weak = []
    for amplitude in (9, 12, 25, 50, 100, 300):
        for noise_fraction in (0, 0.25, 0.5, 1):
            weak.append({'amplitude': amplitude, 'raw_noise_ratio': noise_fraction,
                **paired((f'weak_a{amplitude}_p{p}_r{r}', sampled_window(
                    'legacy', p/16, r, round(amplitude*noise_fraction),
                    random.Random(SEED+p), low=1000, amplitude=amplitude))
                    for p in range(128) for r in (0.997, 1, 1.003))})
    dropout = []
    for span in range(49):
        for phase in range(8):
            samples = prior.waveform(300, 1000, phase)[:span]+[1000]*(48-span)
            dropout.append((f'signal_ends_{span}_p{phase}', samples))
    bursts = []
    for phase in range(8):
        for first in range(48):
            for second in range(first+1, 48):
                samples = prior.waveform(100, 1000, phase)
                samples[first] = samples[second] = 4095
                bursts.append((f'two_rails_p{phase}_{first}_{second}', samples))
    burst_report = paired(bursts)
    burst_report['accepted_with_exact_recent_amplitude'] = sum(
        measure(samples)['amplitude'] == 100 for _, samples in bursts)
    return {'scope': __doc__, 'counterexamples': counterexamples, 'movement': movement,
            'phase_clock': phase_clock, 'competing_eight_bit_words': paired(competing),
            'wrong_periodic_signals': paired(wrong_periods),
            'deterministic_noise': paired(random_rows), 'weak_signal': weak,
            'dropout': paired(dropout), 'all_two_rail_positions': burst_report,
            'overlap_tracking': overlap_tracking(),
            'algorithm_cost_bounds': {
                'additional_persistent_ram_bytes': 0,
                'local_sort_scratch_bytes': 16,
                'local_sort_worst_comparisons': 6*28,
                'local_full_fit_worst_bit_comparisons': 8*48,
                'retained_observation_samples': 48,
                'recent_strength_samples': 16,
                'nominal_observation_ms': 48*prior.SAMPLE_MS,
                'recent_strength_history_ms': 16*prior.SAMPLE_MS,
                'status': 'Algorithm bounds only; compiled costs are measured separately by the ARM tests'}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--noise-windows', type=int, default=16384)
    args = parser.parse_args()
    report = benchmark(args.noise_windows)
    assert report['counterexamples']['lost'] == 0
    assert report['counterexamples']['gained'] == 965
    assert report['all_two_rail_positions']['new_accepted'] == 8880
    assert report['all_two_rail_positions']['accepted_with_exact_recent_amplitude'] == 8880
    assert report['competing_eight_bit_words']['new_accepted'] == 0
    assert report['wrong_periodic_signals']['new_accepted'] == 0
    assert all(row['lost'] == 0 for row in report['phase_clock']+report['weak_signal'])
    assert all(row['new_accepted'] == 128 for row in report['phase_clock']
               if row['uniform_raw_noise_half_range'] == 0)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
