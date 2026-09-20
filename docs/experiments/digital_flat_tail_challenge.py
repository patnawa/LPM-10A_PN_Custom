"""Challenge exact-flat-tail policies against pinned PN 1.11.

No firmware/model files are edited. This explicitly includes normal-strength
and UNCERTAIN exact fallbacks, because a pre-estimator guard sees both. ADC
transfers, clipping and cable contact are synthetic hypotheses, not measured
LPM-10A front-end behavior. --arm verifies current-image outcomes only.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import random

import digital_acquisition_candidate as current
import digital_confidence_followup as previous
from scan_sync_model import emitted_bit, RX_SAMPLE_US, TX_TICK_US

POLICIES = ('original_established_only_silence', 'pre_estimator_all_exact_silence',
            'rail_high_uncertain_preserve_prior_uncertain', 'all_flat_uncertain',
            'only_rail_high_uncertain')


def upper_flat_measure(samples):
    """Independent oracle for the selected upper-flat-only policy.

    Keep every existing decision except an accepted exact fallback whose
    newest sixteen raw ADC values are all4095. Such a fallback publishes
    uncertainty without presenting the older span's strength. No other flat
    level is special; existing uncertainty and full-window fits are preserved.
    This is a mathematical oracle, not evidence that firmware implements it.
    """
    baseline = current.measure(samples)
    if (baseline['gap'] and baseline.get('phase') is None and
            all(value == 4095 for value in samples[32:48])):
        return {'gap': 1, 'amplitude': None, 'reason': 'uncertain', 'phase': None}
    return baseline


def evaluate(samples):
    baseline = current.measure(samples)
    exact = bool(baseline['gap']) and baseline.get('phase') is None
    tail = samples[32:48]
    flat = exact and max(tail) == min(tail)
    grades = {name: baseline['gap'] for name in POLICIES}
    if flat:
        if baseline['reason'] == 'established':
            grades['original_established_only_silence'] = 0
        grades['pre_estimator_all_exact_silence'] = 0
        grades['rail_high_uncertain_preserve_prior_uncertain'] = (
            1 if tail[0] == 4095 or baseline['gap'] == 1 else 0)
        grades['all_flat_uncertain'] = 1
        if tail[0] == 4095:
            grades['only_rail_high_uncertain'] = 1
    return {'baseline': baseline, 'exact_fallback': exact, 'flat_tail': flat,
            'tail_value': tail[0] if flat else None, 'policy_grades': grades}


def prefix_tail(low, high, tail, span=32, phase=0):
    return [low+(high-low)*current.CODE[(i+phase)%8] for i in range(span)]+list(tail)*(48-span)


def fixture_rows():
    for low, high in ((0, 300), (1000, 1300), (0, 4094), (1000, 4000),
                      (3000, 4000), (0, 4095), (1000, 4095)):
        for value in (0, 1, 1000, 2048, 4094, 4095):
            for span in (24, 32):
                for phase in range(8):
                    yield f'lo{low}/hi{high}/tail{value}/span{span}/phase{phase}', (
                        prefix_tail(low, high, [value], span, phase))


def summarize(rows, arm_rows):
    counts = Counter()
    changed = {p: Counter() for p in POLICIES}
    examples = {}
    for name, samples in rows:
        result = evaluate(samples)
        baseline = result['baseline']['gap']
        counts['windows'] += 1
        counts['baseline_accepted'] += bool(baseline)
        counts['exact_fallback'] += result['exact_fallback']
        counts['flat_exact_fallback'] += result['flat_tail']
        if result['flat_tail']:
            category = 'upper_rail' if result['tail_value'] == 4095 else (
                'lower_zero' if result['tail_value'] == 0 else 'interior')
            category += '_prior_uncertain' if baseline == 1 else '_prior_normal'
            counts[category] += 1
            if category not in examples:
                examples[category] = {'name': name, 'samples': samples, **result}
        for policy, grade in result['policy_grades'].items():
            if grade != baseline:
                changed[policy]['silenced' if grade == 0 else 'changed_to_uncertain'] += 1
        arm_rows[name] = samples
    return {'counts': dict(counts), 'changed': changed, 'examples': examples}


def raw_transfer_window(label):
    """Exact raw integer ADC transfer examples, not a hardware calibration."""
    samples = []
    for index in range(48):
        reads = []
        for sub in range(5):
            t = index+.7+sub*.1
            bit = emitted_bit(math.floor(t*RX_SAMPLE_US/TX_TICK_US), 'legacy')
            before = 1000+3000*bit
            if t < 32:
                value = before
            elif label == 'upper_clamp':
                value = before+5000  # Continuing modulation, both levels clip high.
            elif label == 'lower_clamp':
                value = before-5000  # Hypothesis only; not proof of RX lower clipping.
            elif label == 'quantized_weak_code':
                value = 1000+.4*bit  # Both ADC levels quantize to the same code.
            elif label == 'removed_at_nonzero_baseline':
                value = 1000
            elif label == 'gain_zero_constant_output':
                value = 1000+0*before  # Conditional gain/blanking hypothesis.
            elif label == 'removed_at_zero_baseline':
                value = 0
            else:
                raise ValueError(label)
            reads.append(max(0, min(4095, math.floor(value))))
        samples.append((sum(reads)-min(reads)-max(reads))//3)
    return samples


def burst_stream(start, duration, phase, ratio, count=96):
    samples = []
    for index in range(count):
        reads = []
        for sub in range(5):
            relative = (index+.7+sub*.1)*ratio
            bit = emitted_bit(math.floor((phase+relative)*RX_SAMPLE_US/TX_TICK_US), 'legacy')
            reads.append(1000+300*bit if start <= relative < start+duration else 1000)
        samples.append((sum(reads)-min(reads)-max(reads))//3)
    return samples


def burst_report(arm_rows):
    counters = Counter()
    lost = Counter()
    changed_publications = Counter()
    examples = {}
    for start in (0, 4, 8):
        for duration in (16, 20, 23, 24, 25, 31, 32):
            for ratio in (.98, 1, 1.02):
                for phase in range(32):
                    stream = burst_stream(start, duration, phase/4, ratio)
                    windows = [(end, stream[end-48:end]) for end in (48, 64, 80, 96)]
                    outcomes = [evaluate(x) for _, x in windows]
                    counters['streams'] += 1
                    baseline = any(r['baseline']['gap'] for r in outcomes)
                    counters['baseline_detected_streams'] += baseline
                    for policy in POLICIES:
                        changed_publications[policy] += sum(
                            r['policy_grades'][policy] != r['baseline']['gap'] for r in outcomes)
                        erased = baseline and not any(r['policy_grades'][policy] for r in outcomes)
                        lost[policy] += erased
                        if erased and policy not in examples:
                            name = f'burst/start{start}/duration{duration}/ratio{ratio}/phase{phase}/4'
                            examples[policy] = {'name': name,
                                'publication_outcomes': [{'end': end, **r}
                                    for (end, _), r in zip(windows, outcomes)]}
                            for end, samples in windows:
                                arm_rows[f'{name}/end{end}'] = samples
    assert changed_publications['only_rail_high_uncertain'] == 0
    return {**counters, 'all_indications_erased_by_policy': dict(lost),
            'changed_publications_by_policy': dict(changed_publications), 'examples': examples}


def structured_random_rows(count=10000):
    rng = random.Random(20260922)
    for index in range(count):
        low = rng.randrange(2001)
        amplitude = rng.randint(9, 4095-low)
        phase = rng.randrange(8)
        cut = rng.randrange(24, 33)
        samples = [low+amplitude*current.CODE[(i+phase)%8] for i in range(48)]
        # Small independent perturbations stress threshold, exact fallback
        # and prior-uncertain boundaries, not just repeated identical fixtures.
        for i in range(cut):
            samples[i] = max(0, min(4095, samples[i]+rng.randint(-amplitude//10, amplitude//10)))
        kind = index % 5
        tail = (4095, 0, rng.randrange(1, 4095), 4094, 4095)[kind]
        samples[cut:] = [tail]*(48-cut)
        if kind == 4:
            samples[rng.randrange(32, 48)] = 4094
        yield f'structured_{index}/kind{kind}/cut{cut}', samples


def selected_policy_corpus(rows, arm_rows):
    counts = Counter()
    examples = []
    for name, samples in rows:
        baseline, proposed = current.measure(samples), upper_flat_measure(samples)
        counts['windows'] += 1
        counts['baseline_accepted'] += bool(baseline['gap'])
        counts['proposed_accepted'] += bool(proposed['gap'])
        assert bool(baseline['gap']) == bool(proposed['gap']), name
        if proposed != baseline:
            assert baseline['gap'] != 1 and proposed == {
                'gap': 1, 'amplitude': None, 'reason': 'uncertain', 'phase': None}, name
            assert baseline.get('phase') is None and samples[32:48] == [4095]*16, name
            counts['normal_to_uncertain'] += 1
            if len(examples) < 8:
                examples.append({'name': name, 'samples': samples,
                                 'baseline': baseline, 'proposed': proposed})
                arm_rows[name] = samples
        else:
            counts['unchanged'] += 1
    return {**counts, 'changed_examples': examples}


def same_code_examples():
    # This is a statement about equal resolved ADC observations, not a model
    # asserting that the physical analogue front end adds envelopes linearly.
    shared = [1000+300*b for b in current.CODE*4]+[1000]*16
    direct = [1000+300*b for b in current.CODE*6]
    return {'identical_observation_hypotheses': [
        'one source resolved amplitude300 until sample32, then no resolved signal',
        'same-code coupled mixture resolved amplitude300 until sample32, then below ADC resolution',
        'one continuing source whose gain/observation path becomes constant at sample32'],
        'observations': shared, 'result': evaluate(shared),
        'equal_resolved_amplitude_from_target_or_neighbor': evaluate(direct),
        'limitation': 'Equal ADC samples imply equal firmware outputs. Cable identity and cause of flattening are not identifiable here.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arm', action='store_true')
    args = parser.parse_args()
    assert hashlib.sha256(previous.ARTIFACT.read_bytes()).hexdigest() == previous.SHA256
    for name, digest in previous.MODEL_HASHES.items():
        assert hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() == digest, name
    arm_rows = {}
    report = {'scope': __doc__, 'sha256': previous.SHA256}
    report['flat_tail_matrix'] = summarize(fixture_rows(), arm_rows)
    report['raw_transfer_hypotheses'] = {}
    for label in ('upper_clamp', 'lower_clamp', 'quantized_weak_code',
                  'removed_at_nonzero_baseline', 'gain_zero_constant_output',
                  'removed_at_zero_baseline'):
        samples = raw_transfer_window(label)
        arm_rows[label] = samples
        report['raw_transfer_hypotheses'][label] = {'samples': samples, **evaluate(samples)}
    assert raw_transfer_window('quantized_weak_code') == raw_transfer_window('removed_at_nonzero_baseline')
    assert raw_transfer_window('gain_zero_constant_output') == raw_transfer_window('removed_at_nonzero_baseline')
    almost = {}
    for value, alternate in ((4095, 4094), (0, 1), (1000, 1001)):
        samples = prefix_tail(0, 4094, [value])
        samples[-1] = alternate
        label = f'near_flat_tail_{value}_with_one_{alternate}'
        almost[label] = {'samples': samples, **evaluate(samples)}
        arm_rows[label] = samples
    report['near_flat_counterexamples'] = almost
    report['brief_contact_streams'] = burst_report(arm_rows)
    report['same_code_coupling'] = same_code_examples()
    report['selected_upper_only_policy'] = {
        'structured_random': selected_policy_corpus(structured_random_rows(), arm_rows),
        'clean_sampler': selected_policy_corpus(previous.sampling_rows(), arm_rows),
        'noisy_sampler': selected_policy_corpus(previous.sampling_rows((50, 100, 200, 300)), arm_rows),
        'weak_clean_sampler': selected_policy_corpus(
            previous.sampling_rows(amplitudes=(9, 12, 25, 50, 100)), arm_rows),
        'weak_noisy_sampler': selected_policy_corpus(previous.weak_noisy_rows(), arm_rows),
        'heldout_clean_sampler': selected_policy_corpus(previous.heldout_rows(), arm_rows),
        'prior_audit': selected_policy_corpus(((row['name'], row['samples'])
            for row in previous.original.cases()), arm_rows),
        'fragment_placements': selected_policy_corpus(previous.fragment_rows(), arm_rows),
        'deterministic_noise': selected_policy_corpus(previous.noise_rows(16384), arm_rows),
    }
    if args.arm:
        report['arm_baseline_verification'] = previous.arm_verify(arm_rows)
    # Check key observations, not universality or physical field performance.
    upper = evaluate(prefix_tail(1000, 4000, [4095]))
    assert upper['baseline']['gap'] == 30
    assert upper['policy_grades']['pre_estimator_all_exact_silence'] == 0
    assert upper['policy_grades']['rail_high_uncertain_preserve_prior_uncertain'] == 1
    uncertain = evaluate(prefix_tail(1000, 4095, [1000]))
    assert uncertain['baseline']['gap'] == 1
    assert uncertain['policy_grades']['original_established_only_silence'] == 1
    assert uncertain['policy_grades']['pre_estimator_all_exact_silence'] == 0
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
