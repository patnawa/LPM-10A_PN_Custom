"""Counterexamples for the PN 1.9/1.10 legacy Digital detector and ranking.

Run from any directory: python docs/experiments/digital_bundle_audit.py --arm
The standard-library model consumes already reduced 48-sample ADC windows.
--arm additionally executes the pinned delivered binaries using the RX SDK's
Unicorn harness. These are controlled digital experiments, not measured cable
selectivity, analogue performance, or end-to-end device timing. No files change.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter
import hashlib
import json
from pathlib import Path
import statistics
import sys

CODE = (1, 0, 1, 1, 0, 1, 1, 0)
SAMPLE_MS = 5.003125
WINDOW_MS = 48*SAMPLE_MS
KNOTS = (0, 800, 2400, 7200, 24000, 88000)
GAPS = (160, 130, 105, 75, 45, 20)
PROFILES = {
    'PN1.9': ('APP_LPM-10RX_PN1.9-robust.bin',
               '6128e0a4a0261f3da51bea232c8e431474033f0a09fd24283faa0a743b67fe3e'),
    'PN1.10': ('APP_LPM-10RX_PN1.10-sync.bin',
                '6570f521054d77ee97c1a0e37e5a9da0a975d41d452e5f14e63aadb68a9f6e21'),
}


def waveform(amplitude=100, baseline=1000, phase=0):
    return [baseline+amplitude*CODE[(i+phase) % 8] for i in range(48)]


def gap_for_amplitude(amplitude):
    score = 29*amplitude-12*(29*amplitude//46)
    if score >= KNOTS[-1]:
        return GAPS[-1]
    i = bisect_right(KNOTS, score)-1
    width = KNOTS[i+1]-KNOTS[i]
    return GAPS[i]-(score-KNOTS[i])*(GAPS[i]-GAPS[i+1])//width


def measure(samples, previous=0, recent=560):
    """Independent grouping and rational cadence reference, no ARM tags/sort."""
    assert len(samples) == 48 and all(0 <= x <= 4095 for x in samples)
    threshold = (sum(samples)-min(samples)-max(samples))//46
    bits = [int(x > threshold) for x in samples]
    contrast = sum(abs(x-threshold) for x in samples)
    high_sum = 5+sum(x for x, bit in zip(samples, bits) if bit)
    result = {'threshold': threshold, 'contrast': contrast, 'high_sum': high_sum,
              'reason': 'rejected', 'gap': 0, 'amplitude': None, 'score': None}
    if contrast < 192 or high_sum < 1000:
        return result
    fits = []
    for phase in range(8):
        wanted = [CODE[(i+phase) % 8] for i in range(48)]
        errors = [actual != expected for actual, expected in zip(bits, wanted)]
        if sum(errors) <= 4 and all(sum(errors[i:i+16]) <= 2 for i in (0, 16, 32)):
            fits.append((phase, wanted))
    if fits:
        assert len(fits) == 1
        phase, wanted = fits[0]
        selected = list(range(48))
        reason = 'full_fit'
    else:
        starts = [i for i in range(33) if bits[i:i+16] == list(CODE*2)]
        if len(starts) < 2:
            return result
        selected = sorted({i for start in starts for i in range(start, start+16)})
        wanted, phase, reason = bits, None, 'exact_union'
    lo = int(statistics.median(samples[i] for i in selected if not wanted[i]))
    hi = int(statistics.median(samples[i] for i in selected if wanted[i]))
    amplitude = hi-lo
    result.update(reason=reason, phase=phase, low_median=lo, high_median=hi,
                  amplitude=amplitude, selected_count=len(selected))
    if hi == 4095 or amplitude <= 0:
        result.update(reason='uncertain', gap=1)
    else:
        score = 29*amplitude-12*(29*amplitude//46)
        gap = gap_for_amplitude(amplitude)
        if previous and recent > 500 and abs(gap-previous) < 3:
            gap = previous
        result.update(score=score, gap=gap)
    return result


def cases():
    result = []
    def add(name, samples, previous=0, **metadata):
        row = {'name': name, 'samples': samples, 'previous': previous, **metadata}
        row['measurement'] = measure(samples, previous)
        result.append(row)
    for baseline in (0, 1, 8, 16, 24, 25, 1000):
        for amplitude in (8, 9, 10, 33, 34):
            add(f'dc_{baseline}_a_{amplitude}', waveform(amplitude, baseline))
    for amplitude in (10, 30, 60, 100, 150, 300):
        clean = waveform(amplitude)
        add(f'clean_a_{amplitude}', clean)
        for count in (1, 2):
            sample = clean.copy()
            for i in (0, 16)[:count]:
                sample[i] = 4095
            add(f'positive_rail_{count}_a_{amplitude}', sample)
    # Model what repeated raw ADC impulses leave after the five-read trim.
    # One isolated raw spike is discarded; multiple spikes can survive it.
    for amplitude in (10, 60, 100, 150):
        for spikes in (1, 2, 3, 4):
            reads = [4095]*spikes+[1000+amplitude]*(5-spikes)
            reduced = (sum(reads)-min(reads)-max(reads))//3
            sample = waveform(amplitude)
            sample[0] = sample[16] = reduced
            add(f'two_groups_with_{spikes}_raw_spikes_a_{amplitude}', sample,
                reduced_spike_sample=reduced)
    for phase in range(8):
        for slope in (1, 2, 4, 8):
            sample = [x+slope*i for i, x in enumerate(waveform(100, 500, phase))]
            add(f'dc_ramp_p{phase}_s{slope}', sample)
    for clipped in (0, 1, 14, 15, 16):
        sample = waveform(3500, 0)
        indices = [i for i, x in enumerate(sample) if x]
        for i in indices[:clipped]:
            sample[i] = 4095
        add(f'upper_clip_count_{clipped}', sample)
    # Same-code coherent additions cannot be separated by code conditioning.
    add('target_a100', waveform(100))
    add('neighbor_a150', waveform(150))
    add('a100_plus_same_phase_a200',
        [a+b-1000 for a, b in zip(waveform(100), waveform(200))])
    for span in (16, 23, 24, 32):
        add(f'valid_code_then_flat_{span}', waveform(300)[:span]+[1000]*(48-span))
    for amplitude in (100, 300, 1000, 2000, 3000):
        previous = gap_for_amplitude(amplitude)
        same = [a for a in range(9, 4095) if abs(gap_for_amplitude(a)-previous) < 3]
        for after in (min(same)-1, min(same), amplitude, max(same), max(same)+1):
            add(f'deadband_{amplitude}_to_{after}', waveform(after, baseline=0), previous)
    # Local change: before cut, old amplitude; afterwards, new amplitude.
    # The 8-bit code phase stays continuous through the movement.
    for old, new in ((100, 300), (300, 100), (100, 1000), (1000, 100),
                     (60, 3000), (3000, 60)):
        for phase in range(8):
            for cut in range(49):
                sample = [1000+CODE[(i+phase) % 8]*(old if i < cut else new)
                          for i in range(48)]
                add(f'step_{old}_{new}_p{phase}_cut{cut}', sample,
                    gap_for_amplitude(old), old=old, new=new, phase=phase, cut=cut)
    return result


def exact_fallback_fair_bit_count():
    """Exact finite binary count, not a model of real ADC noise or alarm rate."""
    signature = ''.join(map(str, CODE*2))
    transitions = {}
    for prefix in range(16):
        for bit in '01':
            word = signature[:prefix]+bit
            hit = word.endswith(signature)
            next_prefix = max(n for n in range(min(len(word), 15)+1)
                              if word.endswith(signature[:n]))
            transitions[prefix, bit] = next_prefix, hit
    states = {(0, 0): 1}
    for _ in range(48):
        after = Counter()
        for (prefix, hits), ways in states.items():
            for bit in '01':
                next_prefix, hit = transitions[prefix, bit]
                after[next_prefix, min(2, hits+hit)] += ways
        states = after
    assert sum(states.values()) == 2**48
    accepted = sum(ways for (_, hits), ways in states.items() if hits == 2)
    return {'two_B6B6_occurrences_among_all_48bit_words': accepted,
            'all_48bit_words': 2**48, 'fraction': accepted/2**48,
            'interpretation': 'Exact fallback only; fair independent binary decisions, not physical noise'}


def arm_verify(rows):
    root = Path(__file__).resolve().parents[2]
    firmware = root/'LPM-10A'/'Firmware File'
    sys.path.insert(0, str(firmware/'rx-sdk'))
    import test_rx_robust
    import robust_fixes
    from test_rx_followup import GRADE
    from unicorn import UC_HOOK_CODE
    from unicorn.arm_const import UC_ARM_REG_R0
    verified = {}
    for profile, (filename, digest) in PROFILES.items():
        data = (firmware/'experimental'/filename).read_bytes()
        assert hashlib.sha256(data).hexdigest() == digest, profile+' artifact differs'
        harness = test_rx_robust.Robust()
        harness.data = data
        cpu = harness.cpu()
        scores = []
        def at_mapper(uc, addr, size, user):
            scores.append(uc.reg_read(UC_ARM_REG_R0))
        hook = cpu.uc.hook_add(UC_HOOK_CODE, at_mapper,
                              begin=robust_fixes.GAP_HELPER, end=robust_fixes.GAP_HELPER)
        try:
            for row in rows:
                scores.clear()
                harness.detect(cpu, row['samples'], recent=560, grade=row['previous'])
                expected = row['measurement']
                assert cpu.read(GRADE) == expected['gap'], (profile, row['name'], expected)
                assert scores == ([expected['score']] if expected['score'] else []), (
                    profile, row['name'], scores, expected)
        finally:
            cpu.uc.hook_del(hook)
        verified[profile] = {'sha256': digest, 'windows_verified': len(rows)}
    return verified


def summarize(rows):
    selected = [row for row in rows if 'old' not in row]
    floors = {str(dc): next(a for a in range(1, 100)
                           if measure(waveform(a, dc))['gap'])
              for dc in (0, 1, 8, 16, 24, 25, 1000)}
    transitions = []
    for old, new in ((100, 300), (300, 100), (100, 1000), (1000, 100),
                     (60, 3000), (3000, 60)):
        subset = [r for r in rows if r.get('old') == old and r.get('new') == new]
        counts = Counter()
        latency = []
        for row in subset:
            gap, cut = row['measurement']['gap'], row['cut']
            if gap == gap_for_amplitude(new):
                state = 'new_rank'
                windows = 1
            else:
                state = 'rejected' if gap == 0 else 'old_or_intermediate_rank'
                windows = 2
            counts[state] += 1
            # Abstract reduced-sample boundary model: acquisition ends at48T.
            # Detector processing and the currently running beep/gap add time.
            latency.append((windows*48-cut)*SAMPLE_MS)
        example = [{'cut': r['cut'], **r['measurement']}
                   for r in subset if r['phase'] == 0]
        transitions.append({'old_amplitude': old, 'new_amplitude': new,
                            'windows': len(subset), 'states': dict(counts),
                            'settled_rank_latency_ms_range': [min(latency), max(latency)],
                            'phase_zero': example})
    deadband = []
    for amplitude in (100, 300, 1000, 2000, 3000):
        gap = gap_for_amplitude(amplitude)
        same = [a for a in range(9, 4095) if abs(gap_for_amplitude(a)-gap) < 3]
        deadband.append({'starting_amplitude': amplitude, 'starting_gap': gap,
                         'amplitude_range_retaining_previous_gap': [min(same), max(same)]})
    # Rank-updating and noise-rejection checks are intentionally separate.
    assert floors['0'] == 34 and floors['1000'] == 9
    by_name = {r['name']: r['measurement'] for r in rows}
    assert by_name['positive_rail_1_a_100']['amplitude'] == 100
    assert by_name['positive_rail_2_a_100']['gap'] == 0
    assert by_name['two_groups_with_1_raw_spikes_a_10']['amplitude'] == 10
    assert by_name['two_groups_with_2_raw_spikes_a_10']['gap'] == 0
    assert by_name['two_groups_with_3_raw_spikes_a_100']['gap'] == 0
    assert by_name['step_100_300_p0_cut25']['gap'] == 0
    assert by_name['step_100_300_p0_cut33']['amplitude'] == 100
    assert by_name['upper_clip_count_15']['reason'] == 'full_fit'
    assert by_name['upper_clip_count_16']['reason'] == 'uncertain'
    assert by_name['a100_plus_same_phase_a200']['amplitude'] == 300
    return {'scope': 'Reduced ADC windows; no physical cable or analogue model',
            'window_ms': WINDOW_MS, 'dc_to_minimum_clean_amplitude': floors,
            'latency_convention': 'Step at reduced-sample boundary k*T; publication at48*T or96*T. '
                                  'Excludes ADC aperture, detector runtime, rearm delay and audible cadence.',
            'selected_counterexamples': [{k: v for k, v in row.items() if k != 'samples'}
                                        for row in selected],
            'moving_amplitude_steps': transitions, 'cadence_deadband': deadband,
            'exact_fallback_binary_count': exact_fallback_fair_bit_count()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arm', action='store_true', help='verify both pinned ARM images')
    args = parser.parse_args()
    rows = cases()
    report = summarize(rows)
    if args.arm:
        report['arm_verification'] = arm_verify(rows)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
