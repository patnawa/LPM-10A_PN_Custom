"""Model-only confidence follow-up for the pinned PN 1.11 Digital detector.

No firmware is changed. Proposals operate only after the existing detector
accepts through its exact-span fallback. This deliberately keeps full-window
local/global fits unchanged. --arm checks the current artifact against its
independent model; it does not turn a proposal into implemented firmware.

All ADC values, clocks, noise and motion are synthetic. Rejection/acceptance
counts are not field false-alarm rates or evidence of Fluke superiority.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import random
import statistics
import sys

import digital_acquisition_candidate as current
import digital_bundle_audit as original
from scan_sync_model import RX_SAMPLE_US, TX_TICK_US, emitted_bit, sampled_window

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT = ROOT / 'LPM-10A/Firmware File/experimental/APP_LPM-10RX_PN1.11-tracking.bin'
SHA256 = '3e39ae56832cf92881ffdc46564e293278d6c3f1b55a9832b7a9a8350f031828'
MODEL_HASHES = {
    'digital_acquisition_candidate.py': 'a66d9c7f4dd77cfaca857f8e77fe871fa11c528f86fb85d2e56b712e9c7fa22a',
    'digital_bundle_audit.py': 'e572e957fd840336cc4c8b862f6b3876d07a619609a9bffdef3a0288187ee610',
    'scan_sync_model.py': 'c9c59cb5b5cde5178d93a0bbf63faaf18991f4b8b667c00f5d19ed41b265688f',
}
CODE = original.CODE
RULES = ('last_exact_within_8', 'recent_global_errors_le_2',
         'recent_local_errors_le_2', 'span_residual_le_15_percent',
         'recent_range_ge_9', 'lag8_difference_le_quarter_range',
         'range_and_lag8', 'recent_nonflat', 'nonflat_and_recent_span_or_lag8')
RATIOS = (.98, .99, .997, .999, 1, 1.001, 1.003, 1.01, 1.02)


def fallback_metrics(samples):
    threshold = (sum(samples)-min(samples)-max(samples))//46
    bits = [int(v > threshold) for v in samples]
    starts = [i for i in range(33) if bits[i:i+16] == list(CODE*2)]
    assert len(starts) >= 2
    last = starts[-1]
    lo = [samples[i] for i in range(last, last+16) if not bits[i]]
    hi = [samples[i] for i in range(last, last+16) if bits[i]]
    l, h = statistics.median(lo), statistics.median(hi)
    residual = sum(abs(v-l) for v in lo)+sum(abs(v-h) for v in hi)
    local = []
    for start in (32, 40):
        ordered = sorted(samples[start:start+8])
        cut = (ordered[1]+ordered[5])//2
        local.extend(int(v > cut) for v in samples[start:start+8])
    recent_global_errors = min(sum(bits[i] != CODE[(i+p)%8] for i in range(32, 48))
                               for p in range(8))
    recent_local_errors = min(sum(local[i] != CODE[(i+p)%8] for i in range(16))
                              for p in range(8))
    span_range = max(samples[8:])-min(samples[8:])
    lag_difference = sum(abs(samples[i]-samples[i-8]) for i in range(16, 48))
    recent_range = max(samples[32:])-min(samples[32:])
    residual_fraction = residual/(16*(h-l)) if h > l else None
    return {'exact_starts': starts, 'age_samples': 32-last,
            'recent_global_errors': recent_global_errors,
            'recent_local_errors': recent_local_errors,
            'span_residual_fraction': residual_fraction,
            'recent_range': recent_range, 'last40_range': span_range,
            'lag8_difference_sum': lag_difference,
            'lag8_normalized': lag_difference/(32*span_range) if span_range else None}


def evaluate(samples):
    baseline = current.measure(samples)
    # Upper-rail uncertainty is already a separate report. Never turn an
    # uncertain result into silent rejection through these ranking proposals.
    is_fallback = baseline['reason'] == 'established' and baseline['phase'] is None
    decisions = {name: bool(baseline['gap']) for name in RULES}
    metrics = None
    if is_fallback:
        metrics = fallback_metrics(samples)
        decisions.update(
            last_exact_within_8=metrics['age_samples'] <= 8,
            recent_global_errors_le_2=metrics['recent_global_errors'] <= 2,
            recent_local_errors_le_2=metrics['recent_local_errors'] <= 2,
            span_residual_le_15_percent=metrics['span_residual_fraction'] <= .15,
            recent_range_ge_9=metrics['recent_range'] >= 9,
            lag8_difference_le_quarter_range=(metrics['lag8_difference_sum'] <= 8*metrics['last40_range']))
        decisions['range_and_lag8'] = (decisions['recent_range_ge_9'] and
                                     decisions['lag8_difference_le_quarter_range'])
        decisions['recent_nonflat'] = metrics['recent_range'] > 0
        decisions['nonflat_and_recent_span_or_lag8'] = (
            decisions['recent_nonflat'] and (decisions['last_exact_within_8'] or
                                            decisions['lag8_difference_le_quarter_range']))
    return baseline, decisions, metrics


def compare(rows, arm_rows=None):
    counts = Counter()
    removed = Counter()
    examples = {name: [] for name in RULES}
    baseline_rejections = []
    fallback_age = Counter()
    worst_lag = None
    for label, samples in rows:
        baseline, decisions, metrics = evaluate(samples)
        counts['windows'] += 1
        counts['baseline_accepted'] += bool(baseline['gap'])
        counts['baseline_exact_fallback'] += metrics is not None
        if not baseline['gap'] and len(baseline_rejections) < 2:
            baseline_rejections.append({'name': label, 'samples': samples, 'baseline': baseline})
            if arm_rows is not None:
                arm_rows[str(label)] = samples
        if metrics:
            fallback_age[metrics['age_samples']] += 1
            if worst_lag is None or metrics['lag8_normalized'] > worst_lag['metrics']['lag8_normalized']:
                worst_lag = {'name': label, 'metrics': metrics}
        for rule, accepted in decisions.items():
            if baseline['gap'] and not accepted:
                removed[rule] += 1
                if len(examples[rule]) < 2:
                    row = {'name': label, 'samples': samples,
                           'baseline': baseline, 'metrics': metrics}
                    examples[rule].append(row)
                    if arm_rows is not None:
                        arm_rows[str(label)] = samples
    return {**counts, 'removed_by_rule': {r: removed[r] for r in RULES},
            'first_removed_examples': examples, 'first_baseline_rejections': baseline_rejections,
            'fallback_age_histogram': dict(fallback_age),
            'worst_fallback_lag8': worst_lag}


def sampling_rows(noises=(0,), amplitudes=(300,), ratios=RATIOS, phases=128):
    for amplitude in amplitudes:
        for fresh in (False, True):
            for ratio in ratios:
                for noise in noises:
                    for phase in range(phases):
                        label = f'a{amplitude}/fresh{fresh}/ratio{ratio}/noise{noise}/phase{phase}/{phases//8}'
                        yield label, sampled_window('legacy', phase/(phases//8), ratio,
                            noise, random.Random(current.SEED+phase), amplitude=amplitude,
                            fresh_start=fresh)


def noise_rows(count):
    for index in range(count):
        rng = random.Random(current.SEED+100000+index)
        yield f'uniform_{index}', [rng.randrange(4096) for _ in range(48)]
        yield f'binary_{index}', [1000+300*rng.randrange(2) for _ in range(48)]
        walk = [1000]
        for _ in range(47):
            walk.append(max(0, min(4095, walk[-1]+rng.randint(-100, 100))))
        yield f'random_walk_{index}', walk


def weak_noisy_rows():
    for amplitude in (9, 12, 25, 50, 100):
        for fraction in (.25, .5, 1):
            yield from sampling_rows((round(amplitude*fraction),), (amplitude,),
                                     ratios=(.997, 1, 1.003))


def heldout_rows(count=4096):
    rng = random.Random(20260921)
    for index in range(count):
        phase, ratio = rng.random()*8, .98+rng.random()*.04
        amplitude = rng.randint(9, 3000)
        fresh = bool(rng.randrange(2))
        label = f'heldout{index}/a{amplitude}/fresh{fresh}/ratio{ratio}/phase{phase}'
        yield label, sampled_window('legacy', phase, ratio, amplitude=amplitude,
                                    fresh_start=fresh)


def fragment_rows():
    for span in (16, 23, 24, 25, 31, 32, 40, 48):
        for start in range(49-span):
            for phase in range(8):
                samples = [1000]*48
                for i in range(start, start+span):
                    samples[i] += 300*CODE[(i+phase)%8]
                yield f'span{span}/start{start}/phase{phase}', samples


def continuous_samples(phase, ratio, before, after, cut, count=160, noise=0, seed=0):
    """One coherent stream, not independently reseeded overlapping windows.

    The step is at cut*nominal RX sample periods after fresh-start origin.
    Actual ADC aperture positions decide which amplitude each raw read uses.
    CPU stalls, IRQ latency and rearm phase effects are outside this model.
    """
    rng = random.Random(seed)
    samples = []
    for index in range(count):
        reads = []
        for sub in range(5):
            relative_time = (index+.7+sub*.1)*ratio
            t = (phase+relative_time)*RX_SAMPLE_US
            amplitude = before if relative_time < cut else after
            bit = emitted_bit(math.floor(t/TX_TICK_US), 'legacy')
            reads.append(max(0, min(4095, 1000+amplitude*bit+rng.randint(-noise, noise))))
        samples.append((sum(reads)-min(reads)-max(reads))//3)
    return samples


def overlap_report(arm_rows):
    rows = []
    tracked_rules = ('range_and_lag8', 'recent_nonflat', 'nonflat_and_recent_span_or_lag8')
    for before, after in ((300, 300), (100, 300), (300, 100), (60, 3000), (3000, 60), (300, 0)):
        total = Counter()
        removed = {r: Counter() for r in tracked_rules}
        first_release = {r: [] for r in ('baseline',)+tracked_rules}
        counterexamples = {r: [] for r in tracked_rules}
        for ratio in (.98, .997, 1, 1.003, 1.02):
            for phase in range(16):
                for offset in range(16):
                    cut = 48+offset
                    stream = continuous_samples(phase/2, ratio, before, after, cut)
                    released = {}
                    for end in range(48, 161, 16):
                        samples = stream[end-48:end]
                        baseline, decisions, metrics = evaluate(samples)
                        total['publications'] += 1
                        total['baseline_accepted'] += bool(baseline['gap'])
                        for rule in tracked_rules:
                            if baseline['gap'] and not decisions[rule]:
                                # Retained code after genuine removal is the intended
                                # stale indication reduction; live steps are losses.
                                key = 'after_dropout' if after == 0 and end > cut else 'live_code'
                                removed[rule][key] += 1
                                if key == 'live_code' and len(counterexamples[rule]) < 2:
                                    name = f'motion{before}-{after}/r{ratio}/p{phase}/cut{cut}/end{end}'
                                    counterexamples[rule].append({'name': name, 'samples': samples,
                                        'baseline': baseline, 'metrics': metrics})
                                    arm_rows[name] = samples
                        if after == 0 and end > cut:
                            for rule, accepted in [('baseline', bool(baseline['gap']))]+[
                                    (r, decisions[r]) for r in tracked_rules]:
                                if not accepted and rule not in released:
                                    # Last raw read of sample end-1 is at end+.1
                                    # periods from origin in the fresh schedule.
                                    released[rule] = ((end+.1)*ratio-cut)*original.SAMPLE_MS
                    for rule, latency in released.items():
                        first_release[rule].append(latency)
        rows.append({'before': before, 'after': after, **total,
                     'removed_by_rule': removed,
                     'live_code_counterexamples': counterexamples,
                     'first_rejection_latency_ms': {r: [min(v), max(v)] if v else None
                         for r, v in first_release.items()}})
    return {'scope': continuous_samples.__doc__, 'transitions': rows}


def dense_clean_bound():
    """Independent dense grid; do not reuse the nine development ratios."""
    peak = {'normalized': -1}
    violations = 0
    count = 0
    for fresh in (False, True):
        for index in range(81):
            ratio = .98+index*.0005
            for phase in range(256):
                samples = sampled_window('legacy', phase/32, ratio, amplitude=300,
                                         fresh_start=fresh)
                extent = max(samples[8:])-min(samples[8:])
                difference = sum(abs(samples[i]-samples[i-8]) for i in range(16, 48))
                normalized = difference/(32*extent)
                count += 1
                violations += difference > 8*extent
                if normalized > peak['normalized']:
                    peak = {'normalized': normalized, 'fresh': fresh, 'ratio': ratio,
                            'phase': phase/32, 'samples': samples}
    return {'windows': count, 'above_quarter_range': violations, 'maximum': peak}


def arm_verify(rows):
    sys.path.insert(0, str(ROOT/'LPM-10A/Firmware File/rx-sdk'))
    import test_rx_robust
    import robust_fixes
    from test_rx_followup import GRADE
    from verify_digital import RECENT
    from unicorn import UC_HOOK_CODE
    from unicorn.arm_const import UC_ARM_REG_R0
    harness = test_rx_robust.Robust()
    harness.data = ARTIFACT.read_bytes()
    cpu = harness.cpu()
    scores = []
    def capture(uc, address, size, userdata):
        scores.append(uc.reg_read(UC_ARM_REG_R0))
    hook = cpu.uc.hook_add(UC_HOOK_CODE, capture,
        begin=robust_fixes.GAP_HELPER, end=robust_fixes.GAP_HELPER)
    try:
        for name, samples in rows.items():
            expected = current.measure(samples)
            scores.clear()
            harness.detect(cpu, samples, recent=560, grade=0)
            amplitude = expected['amplitude']
            score = (29*amplitude-12*(29*amplitude//46)) if amplitude is not None else None
            assert cpu.read(GRADE) == expected['gap'], (name, expected)
            assert scores == ([] if score is None else [score]), (name, scores, expected)
            assert cpu.read(RECENT, 2) == (800 if expected['gap'] else 560), name
    finally:
        cpu.uc.hook_del(hook)
    return {'windows': len(rows), 'sha256': SHA256, 'proposal_firmware_executed': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arm', action='store_true')
    parser.add_argument('--noise-windows', type=int, default=16384)
    args = parser.parse_args()
    assert hashlib.sha256(ARTIFACT.read_bytes()).hexdigest() == SHA256
    for name, digest in MODEL_HASHES.items():
        assert hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() == digest, name
    arm_rows = dict(sampling_rows())
    report = {'scope': __doc__, 'artifact_sha256': SHA256, 'model_sha256': MODEL_HASHES}
    report['clean_sampling'] = compare(sampling_rows(), arm_rows)
    report['noisy_sampling'] = compare(sampling_rows((50, 100, 200, 300)), arm_rows)
    report['weak_clean_sampling'] = compare(sampling_rows(amplitudes=(9, 12, 25, 50, 100)), arm_rows)
    report['weak_noisy_sampling'] = compare(weak_noisy_rows(), arm_rows)
    report['heldout_clean_sampling'] = compare(heldout_rows(), arm_rows)
    report['prior_counterexamples'] = compare(((r['name'], r['samples'])
                                              for r in original.cases()), arm_rows)
    report['fragments'] = compare(fragment_rows(), arm_rows)
    report['deterministic_noise'] = compare(noise_rows(args.noise_windows), arm_rows)
    rng = random.Random(current.SEED+100000+13398)
    false_case = [rng.randrange(4096) for _ in range(48)]
    arm_rows['inherited_uniform_13398'] = false_case
    baseline, decisions, metrics = evaluate(false_case)
    report['inherited_uniform_13398'] = {'samples': false_case, 'baseline': baseline,
                                      'proposal_acceptance': decisions, 'metrics': metrics}
    report['dense_clean_grid'] = dense_clean_bound()
    report['continuous_overlap'] = overlap_report(arm_rows)
    if args.arm:
        report['arm_baseline_verification'] = arm_verify(arm_rows)
    assert report['clean_sampling']['baseline_accepted'] == 2304
    assert report['dense_clean_grid']['above_quarter_range'] == 0
    assert not decisions['lag8_difference_le_quarter_range']
    # Assert observations, not a claim that every proposal is safe. A future
    # model change deliberately fails the hashes before changing conclusions.
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
