"""Publication-state release hypotheses for the exact PN 1.12 Digital profile.

No firmware changes. Time is nominal ADC sampling/publication time, not real
foreground scheduling or audible pulse timing. In particular GRADE=0 clears
repeat eligibility at the next publication even while RECENT remains fresh.
Freshness therefore is not an unconditional audio hold after every rejection.
Continuing code/fades are synthetic hypotheses, not measured AFE behavior.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import random

from digital_flat_tail_challenge import upper_flat_measure, burst_stream
from digital_confidence_followup import fallback_metrics
from scan_sync_model import emitted_bit, RX_SAMPLE_US, TX_TICK_US

T = RX_SAMPLE_US/1000
SHA256 = '4ea18c52bde25353a9a38dbf46775425860f7859bc2c10e3c908a7bff4044403'
ARTIFACT = Path(__file__).resolve().parents[2]/'LPM-10A/Firmware File/experimental/APP_LPM-10RX_PN1.12-overload.bin'
POLICIES = ('baseline', 'flat_after_grade', 'flat_after_recent', 'no_refresh_old_exact')


def sample_stream(amplitude, count=480, phase=0, ratio=1, noise=0, seed=20260923,
                  baseline=lambda t: 1000):
    """One coherent five-read stream with explicit raw-read-time amplitude."""
    rng = random.Random(seed)
    stream = []
    for index in range(count):
        reads = []
        for sub in range(5):
            time = (index+.7+sub*.1)*ratio
            tick = math.floor((phase+time)*RX_SAMPLE_US/TX_TICK_US)
            value = baseline(time)+amplitude(time)*emitted_bit(tick, 'legacy')
            value += rng.randint(-noise, noise)
            reads.append(max(0, min(4095, math.floor(value))))
        stream.append((sum(reads)-min(reads)-max(reads))//3)
    return stream


def prepare(stream, ratio=1, hop=16):
    rows = []
    for end in range(48, len(stream)+1, hop):
        samples = stream[end-48:end]
        result = upper_flat_measure(samples)
        exact_normal = result['gap'] > 1 and result.get('phase') is None
        rows.append({'end': end, 'time': (end+.1)*ratio*T, 'result': result,
                     'flat': exact_normal and max(samples[32:]) == min(samples[32:]),
                     'age': fallback_metrics(samples)['age_samples'] if exact_normal else None,
                     'samples': samples})
    return rows


def run(rows, policy='baseline', fresh_ms=300, hop=16, ratio=1):
    grade, last_refresh = 0, None
    outcomes = []
    for row in rows:
        now, original = row['time'], row['result']['gap']
        fresh = last_refresh is not None and now-last_refresh < fresh_ms
        suppressed = row['flat'] and (
            policy == 'flat_after_grade' and grade > 0 or
            policy == 'flat_after_recent' and fresh)
        proposed = 0 if suppressed else original
        skip_refresh = (policy == 'no_refresh_old_exact' and grade > 0 and
                        row['age'] is not None and row['age'] >= 16)
        if proposed and not skip_refresh:
            last_refresh = now
        until = min(now+hop*ratio*T, last_refresh+fresh_ms) if proposed and last_refresh is not None else now
        outcomes.append({'end': row['end'], 'time': now, 'grade': proposed,
                         'original_grade': original, 'eligible_until': max(now, until),
                         'suppressed': suppressed, 'skip_refresh': bool(skip_refresh)})
        grade = proposed
    return outcomes


def release_stats(outcomes, move_time):
    # Include an indication published before the move when its eligibility
    # interval extends after the move. Do not discard that remaining interval.
    positive = [r for r in outcomes if r['eligible_until'] > max(r['time'], move_time)]
    last = max((r['eligible_until'] for r in positive), default=move_time)
    return {'last_repeat_eligibility_end_after_move_ms': max(0, last-move_time),
            'eligible_publications_after_1s': sum(r['eligible_until'] > move_time+1000 for r in positive),
            'eligible_at_final_publication': bool(outcomes and outcomes[-1]['eligible_until'] > outcomes[-1]['time']),
            'changed_grade_publications': sum(r['grade'] != r['original_grade'] for r in outcomes),
            'suppressed_refresh_publications': sum(r['skip_refresh'] for r in outcomes)}


def abrupt_release():
    result = {name: [] for name in (*POLICIES, 'baseline_fresh120', 'baseline_fresh150', 'baseline_hop8')}
    for ratio in (.98, .997, 1, 1.003, 1.02):
        for phase in range(16):
            for offset in range(16):
                cut = 64+offset
                stream = sample_stream(lambda t: 300 if t < cut else 0, count=160,
                                       phase=phase/2, ratio=ratio)
                rows = prepare(stream, ratio)
                for policy in POLICIES:
                    result[policy].append(release_stats(run(rows, policy, ratio=ratio), cut*T))
                result['baseline_fresh120'].append(release_stats(run(rows, fresh_ms=120, ratio=ratio), cut*T))
                result['baseline_fresh150'].append(release_stats(run(rows, fresh_ms=150, ratio=ratio), cut*T))
                result['baseline_hop8'].append(release_stats(run(prepare(stream, ratio, 8), hop=8, ratio=ratio), cut*T))
    return {name: {'streams': len(values),
                   'last_eligibility_ms_range': [min(r['last_repeat_eligibility_end_after_move_ms'] for r in values),
                                                max(r['last_repeat_eligibility_end_after_move_ms'] for r in values)],
                   'changed_grade_publications': sum(r['changed_grade_publications'] for r in values),
                   'eligible_after_1s': sum(r['eligible_publications_after_1s'] for r in values)}
            for name, values in result.items()}


def first_brief_contacts():
    results = {p: Counter() for p in POLICIES}
    for start in (0, 4, 8):
        for duration in (16, 20, 23, 24, 25, 31, 32):
            for ratio in (.98, 1, 1.02):
                for phase in range(32):
                    rows = prepare(burst_stream(start, duration, phase/4, ratio), ratio)
                    initial = run(rows, ratio=ratio)
                    old_seen = any(r['eligible_until'] > r['time'] for r in initial)
                    for policy in POLICIES:
                        proposed = run(rows, policy, ratio=ratio)
                        new_seen = any(r['eligible_until'] > r['time'] for r in proposed)
                        results[policy]['streams'] += 1
                        results[policy]['baseline_seen'] += old_seen
                        results[policy]['lost_entire_indication'] += old_seen and not new_seen
                        results[policy]['first_publication_changes'] += proposed[0]['grade'] != initial[0]['grade']
    return results


def sustained_hypotheses():
    cases = []
    profiles = []
    for residual in (0, 3, 9, 12, 25, 60, 150):
        profiles.append((f'residual_code_A{residual}', lambda t, a=residual: 300 if t < 64 else a, 0))
    for tau in (50, 100, 250, 500, 1000):
        profiles.append((f'code_fade_tau{tau}ms',
            lambda t, tau=tau: 300 if t < 64 else 300*math.exp(-(t-64)*T/tau), 0))
    for noise in (5, 25, 100, 300):
        profiles.append((f'true_zero_after_move_raw_noise_pm{noise}', lambda t: 300 if t < 64 else 0, noise))
    for label, envelope, noise in profiles:
        per_policy = {p: [] for p in (*POLICIES, 'baseline_fresh120')}
        for ratio in (.98, 1, 1.02):
            for phase in range(8):
                stream = sample_stream(envelope, count=1024, phase=phase, ratio=ratio,
                    noise=noise, seed=20260923+phase)
                rows = prepare(stream, ratio)
                for policy in POLICIES:
                    per_policy[policy].append(release_stats(run(rows, policy, ratio=ratio), 64*T))
                per_policy['baseline_fresh120'].append(release_stats(run(rows, fresh_ms=120, ratio=ratio), 64*T))
        cases.append({'name': label, 'policies': {p: {
            'streams': len(values),
            'max_last_eligibility_after_move_ms': max(v['last_repeat_eligibility_end_after_move_ms'] for v in values),
            'streams_with_eligibility_after_1s': sum(v['eligible_publications_after_1s'] > 0 for v in values),
            'streams_still_eligible_at_end': sum(v['eligible_at_final_publication'] for v in values),
            'changed_grade_publications': sum(v['changed_grade_publications'] for v in values),
        } for p, values in per_policy.items()}})
    return cases


def continuous_motion_and_noise():
    variants = (*POLICIES, 'baseline_fresh150', 'no_refresh_old_exact_fresh150')
    counts = {p: Counter() for p in variants}
    examples = {p: [] for p in variants}
    for before, after in ((300, 300), (100, 300), (300, 100), (60, 3000), (3000, 60), (300, 12)):
        for noise in (0, 5, 25, 100):
            for ratio in (.98, 1, 1.02):
                for phase in range(8):
                    stream = sample_stream(lambda t: before if t < 64 else after, count=320,
                        phase=phase, ratio=ratio, noise=noise, seed=20260923+phase)
                    rows = prepare(stream, ratio)
                    base = run(rows, ratio=ratio)
                    for policy in variants:
                        fresh_ms = 150 if policy.endswith('_fresh150') else 300
                        base_policy = policy.removesuffix('_fresh150')
                        proposed = run(rows, base_policy, fresh_ms=fresh_ms, ratio=ratio)
                        for index, (old, new) in enumerate(zip(base, proposed)):
                            counts[policy]['publications'] += 1
                            if old['eligible_until'] > old['time']:
                                counts[policy]['baseline_eligible_publications'] += 1
                                if new['eligible_until'] < old['eligible_until']:
                                    counts[policy]['shortened_valid_eligibility'] += 1
                                    if len(examples[policy]) < 2:
                                        examples[policy].append({'before': before, 'after': after,
                                            'noise': noise, 'ratio': ratio, 'phase': phase,
                                            'samples': rows[index]['samples'], 'row': rows[index]['result'],
                                            'original': old, 'proposed': new})
    return {p: {**counts[p], 'counterexamples': examples[p]} for p in variants}


def repeated_contacts():
    counts = {p: Counter() for p in POLICIES}
    examples = {p: [] for p in POLICIES}
    for gap in (8, 16, 24, 32, 48, 64):
        for duration in (23, 24, 32):
            for ratio in (.98, 1, 1.02):
                for phase in range(16):
                    start = 64+gap
                    stream = sample_stream(lambda t: 300 if t < 64 or start <= t < start+duration else 0,
                        count=256, phase=phase/2, ratio=ratio)
                    rows = prepare(stream, ratio)
                    base = run(rows, ratio=ratio)
                    for policy in POLICIES:
                        proposed = run(rows, policy, ratio=ratio)
                        for index in range(1, len(rows)):
                            # Compare actual baseline reacquisitions after a
                            # rejected publication, rather than interpreting
                            # any retained old-code report as a new contact.
                            if (rows[index]['time'] >= start*T and base[index-1]['grade'] == 0
                                    and base[index]['grade'] > 0):
                                counts[policy]['baseline_reacquisition_events'] += 1
                                if proposed[index]['grade'] == 0:
                                    counts[policy]['reacquisition_suppressed'] += 1
                                    if len(examples[policy]) < 2:
                                        examples[policy].append({'gap_samples': gap, 'duration_samples': duration,
                                            'ratio': ratio, 'phase': phase/2, 'end': rows[index]['end'],
                                            'samples': rows[index]['samples'], 'original': base[index],
                                            'proposed': proposed[index]})
    return {p: {**counts[p], 'counterexamples': examples[p]} for p in POLICIES}


def main():
    assert hashlib.sha256(ARTIFACT.read_bytes()).hexdigest() == SHA256
    report = {'scope': __doc__, 'sha256': SHA256,
              'abrupt_zero_release': abrupt_release(),
              'first_brief_contacts': first_brief_contacts(),
              'sustained_signal_hypotheses': sustained_hypotheses(),
              'continuous_motion_and_noise': continuous_motion_and_noise(),
              'repeated_contact_reacquisition': repeated_contacts()}
    assert all(v['lost_entire_indication'] == 0 for v in report['first_brief_contacts'].values())
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
