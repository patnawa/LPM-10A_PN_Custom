"""Run the final RX cabinet matrix in two checkpointed, independent mode workers.

This is CPU execution with modeled ADC/link/interrupts, not hardware evidence.
Run from any directory: python docs/debug/2026-09-26-rx-tx/release_final_scorecard.py
"""
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
from pathlib import Path
import sys
import time

SDK = Path(__file__).resolve().parents[3] / 'LPM-10A' / 'Firmware File' / 'rx-sdk'
sys.path.insert(0, str(SDK))
import cabinet_scorecard as scorecard

EXPECTED = '3e03d8ac13884a0fb3ad752b551ad346eb8e77e11998d7be9ca599923752094c'
REPORT = Path(__file__).with_name('release_scorecard_final_pn131.json')


def save(path, report):
    checkpoint = path.with_suffix(path.suffix + '.tmp')
    checkpoint.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    checkpoint.replace(path)


def new_report(data):
    digest = hashlib.sha256(data).hexdigest()
    if digest != EXPECTED:
        raise ValueError(f'expected frozen final RX {EXPECTED}, got {digest}')
    return {
        'scope': 'ARM execution with modeled ADC/link/interrupts; no physical performance measurement',
        'provenance': 'Frozen final PN1.31 image; independent mode workers from one immutable byte snapshot.',
        'sha256': {'pn1.31': digest}, 'pulse_ms': scorecard.PULSE_MS,
        'audible_fraction': scorecard.AUDIBLE_FRACTION,
        'complete': False, 'trials': [], 'summaries': [],
    }


def run_mode(mode, data):
    report = new_report(data)
    path = REPORT.with_name(f'release_scorecard_final_pn131_mode{mode}.json')
    save(path, report)
    started = time.monotonic()
    for target in scorecard.TARGETS:
        for knob in scorecard.KNOBS:
            visits = scorecard.visit_fractions(data, mode=mode, knob=knob, target=target)
            result = scorecard.assess(visits)
            report['trials'].append(dict(
                profile='pn1.31', mode=mode, target=target, knob=knob,
                visits=visits, detected=result.detected, identified=result.identified,
                status=result.status, failures=result.failures, spread=result.spread))
            save(path, report)
            print(f'mode {mode}: {len(report["trials"])}/24, target {target}, knob {knob}: {result.status}',
                  flush=True)
    rows = report['trials']
    report['summaries'].append(dict(
        profile='pn1.31', mode=mode, total=len(rows),
        detected=sum(row['detected'] for row in rows),
        identified=sum(row['identified'] for row in rows),
        missed=sum(row['status'] == 'MISSED' for row in rows),
        ambiguous=sum(row['status'] == 'AMBIGUOUS' for row in rows)))
    report['complete'] = True
    report['elapsed_seconds'] = time.monotonic() - started
    save(path, report)
    return report


def main():
    started = time.monotonic()
    data = scorecard.builds()['pn1.31']
    report = new_report(data)
    save(REPORT, report)
    print(f'Frozen RX PN1.31 {EXPECTED}; two mode workers', flush=True)
    with ProcessPoolExecutor(max_workers=2) as workers:
        parts = list(workers.map(run_mode, (0, 1), (data, data)))
    for part in parts:
        if not part['complete'] or part['sha256'] != report['sha256']:
            raise ValueError('incomplete or mixed-image mode result')
        report['trials'].extend(part['trials'])
        report['summaries'].extend(part['summaries'])
    expected_keys = {(m, t, k) for m in (0, 1) for t in scorecard.TARGETS for k in scorecard.KNOBS}
    actual_keys = {(r['mode'], r['target'], r['knob']) for r in report['trials']}
    if actual_keys != expected_keys or len(report['trials']) != len(expected_keys):
        raise ValueError('matrix contains missing or duplicate cases')
    report['complete'] = True
    report['elapsed_seconds'] = time.monotonic() - started
    save(REPORT, report)
    print(json.dumps({'report': str(REPORT), 'elapsed_seconds': report['elapsed_seconds'],
                      'sha256': report['sha256'], 'summaries': report['summaries']}, indent=2), flush=True)


if __name__ == '__main__':
    main()
