"""Offline analysis of captured RX SRAM; never opens a hardware connection.

Decode raw bytes, not the original capture's V3.0.0-derived field labels.
The capture performs two sequential live reads, so transitions are bracketed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import struct


def fit_rate(times, values):
    tx = statistics.mean(times)
    vy = statistics.mean(values)
    return sum((t-tx)*(v-vy) for t, v in zip(times, values)) / sum(
        (t-tx)**2 for t in times)


def analyze(path):
    source = path.read_bytes()
    rows = [json.loads(line) for line in source.splitlines()]
    for row in rows:
        state = bytes.fromhex(row['state_hex'])
        tail = bytes.fromhex(row['sram_0ec_0fb_hex'])
        counters = bytes.fromhex(row['counters_hex'])
        assert len(state) == 40 and len(tail) == 16 and len(counters) == 20
        ticks, ticks5, idle, _, beepword = struct.unpack('<5I', counters)
        raw = list(struct.unpack_from('<5H', tail, 6))
        gain_samples = list(struct.unpack_from('<5H', state, 24))
        row.update(mode_raw=state[0], gap_05c=state[20], index_05d=state[21],
                   gate_06a=struct.unpack_from('<H', state, 34)[0],
                   step_06c=struct.unpack_from('<H', state, 36)[0],
                   recent_06e=struct.unpack_from('<H', state, 38)[0],
                   substep_0f0=tail[4], raw5_0f2=raw,
                   trimmed_raw5=sum(sorted(raw)[1:4])//3,
                   gain_samples_060=gain_samples,
                   ticks=ticks, ticks5=ticks5, beep_raw=beepword & 255)
        assert row['begin_s'] <= row['state_end_s'] <= row['end_s']
    assert all(a['end_s'] < b['begin_s'] for a, b in zip(rows, rows[1:]))
    refresh = [i for i in range(1, len(rows))
               if rows[i]['recent_06e'] > rows[i-1]['recent_06e']]
    starts = [i for i in range(1, len(rows))
              if rows[i]['beep_raw'] > 0 and rows[i-1]['beep_raw'] == 0]
    reloaded = [i for i in range(1, len(rows))
                if rows[i]['beep_raw'] > rows[i-1]['beep_raw'] > 0]
    ends = [i for i in range(1, len(rows))
            if rows[i]['beep_raw'] == 0 and rows[i-1]['beep_raw'] > 0]
    wraps = [i for i in range(1, len(rows))
             if rows[i]['index_05d'] < rows[i-1]['index_05d']]
    last = refresh[-1]
    final = ends[-1]
    refresh_bracket = [rows[last-1]['begin_s'], rows[last]['state_end_s']]
    beep_end_bracket = [rows[final-1]['state_end_s'], rows[final]['end_s']]
    final_recent_zero = next(i for i in range(last+1, len(rows))
                             if rows[i]['recent_06e'] == 0)
    constant_sum = [r['ticks']+r['recent_06e']
                    for r in rows[last:final_recent_zero]]
    tail_starts = [i for i in starts if i > last]
    tail_pulses = []
    for start in tail_starts:
        stop = next(i for i in ends if i > start)
        block = rows[start:stop]
        sums = [r['ticks']+r['beep_raw'] for r in block]
        tail_pulses.append({'first_row': start, 'first_zero_row': stop,
            'first_seen_recent': rows[start]['recent_06e'],
            'first_seen_beep': rows[start]['beep_raw'],
            'tim1_plus_beep_range': [min(sums), max(sums)],
            'tim1_plus_beep_median': statistics.median(sums)})
    periods = [b['tim1_plus_beep_median']-a['tim1_plus_beep_median']
               for a, b in zip(tail_pulses, tail_pulses[1:])]
    signal_last = max(i for i, r in enumerate(rows) if r['trimmed_raw5'] > 25)
    signal_drop_bracket = [rows[signal_last]['state_end_s'],
                           rows[signal_last+1]['end_s']]
    outliers = [{'row': i, 'end_s': r['end_s'], 'raw5': r['raw5_0f2'],
                 'gate': r['gate_06a'], 'tim1_mod500': r['ticks'] % 500,
                 'trimmed_raw5': r['trimmed_raw5']}
                for i, r in enumerate(rows) if i > signal_last
                and max(r['raw5_0f2']) > 100]
    time = [r['end_s'] for r in rows]
    elapsed = time[-1]-time[0]
    deltas = [(rows[-1][key]-rows[0][key]) & 0xffffffff for key in ('ticks', 'ticks5')]
    return {
        'source_path': str(path.resolve()),
        'source_sha256': hashlib.sha256(source).hexdigest(),
        'rows': len(rows), 'duration_s': rows[-1]['end_s']-rows[0]['begin_s'],
        'method': 'Offline raw SRAM decoding; sequential, unhalted, non-atomic reads',
        'timing_basis': 'State read occurs between begin_s/state_end_s; tail/counters read between state_end_s/end_s',
        'tx_pause_timestamp_recorded': False,
        'installed_firmware_authenticated': False,
        'sample_spacing_s': {'min': min(b-a for a, b in zip(time, time[1:])),
            'median': statistics.median(b-a for a, b in zip(time, time[1:])),
            'max': max(b-a for a, b in zip(time, time[1:]))},
        'counter_rates': {'elapsed_s': elapsed, 'delta_tim1': deltas[0],
            'delta_tim5': deltas[1], 'endpoint_tim1_hz': deltas[0]/elapsed,
            'endpoint_tim5_hz': deltas[1]/elapsed,
            'linear_fit_tim1_hz': fit_rate(time, [r['ticks'] for r in rows]),
            'linear_fit_tim5_hz': fit_rate(time, [r['ticks5'] for r in rows]),
            'ratio': deltas[1]/deltas[0]},
        'ranges': {key: [min(r[key] for r in rows), max(r[key] for r in rows)]
            for key in ('mode_raw', 'gap_05c', 'index_05d', 'gate_06a',
                        'step_06c', 'recent_06e', 'substep_0f0', 'beep_raw')},
        'gain_alignment': {'trimmed_mean_matches': sum(r['gate_06a'] ==
            sum(sorted(r['gain_samples_060'])[1:4])//3 for r in rows),
            'divide580_matches': sum(r['step_06c'] == r['gate_06a']//580 for r in rows)},
        'index_wraps': len(wraps),
        'index_wrap_interval_median_s': statistics.median(
            rows[b]['state_end_s']-rows[a]['state_end_s'] for a, b in zip(wraps, wraps[1:])),
        'recent_refreshes': len(refresh),
        'recent_refresh_interval_median_s': statistics.median(
            rows[b]['state_end_s']-rows[a]['state_end_s'] for a, b in zip(refresh, refresh[1:])),
        'beep_observations': {'maximum': max(r['beep_raw'] for r in rows),
            'already_positive_at_capture_start': bool(rows[0]['beep_raw']),
            'zero_to_positive_transitions': len(starts),
            'rises_while_already_positive': len(reloaded),
            'positive_reloads_within_one_row_of_recent_refresh': sum(
                any(abs(i-j) <= 1 for j in refresh) for i in reloaded),
            'positive_to_zero_transitions': len(ends)},
        'final_release': {'last_recent_refresh_row': last,
            'last_recent_refresh_bracket_s': refresh_bracket,
            'first_final_recent_zero_row': final_recent_zero,
            'recent_plus_tim1_constant_range': [min(constant_sum), max(constant_sum)],
            'last_beep_clear_row': final,
            'last_beep_clear_bracket_s': beep_end_bracket,
            'last_refresh_to_last_beep_clear_bracket_s': [
                beep_end_bracket[0]-refresh_bracket[1],
                beep_end_bracket[1]-refresh_bracket[0]],
            'new_pulses_after_final_refresh': len(tail_starts),
            'tail_pulses': tail_pulses,
            'tail_cycle_ticks_median': statistics.median(periods),
            'no_more_positive_beep_through_s': rows[-1]['end_s']},
        'input_proxy': {'method': 'Offline trimmed mean of five live raw subsamples, not a captured atomic firmware analysis window',
            'threshold_adc_counts': 25, 'last_above_threshold_row': signal_last,
            'drop_bracket_s': signal_drop_bracket,
            'remaining_trimmed_max': max(r['trimmed_raw5'] for r in rows[signal_last+1:]),
            'drop_to_last_beep_clear_bracket_s': [beep_end_bracket[0]-signal_drop_bracket[1],
                                                   beep_end_bracket[1]-signal_drop_bracket[0]],
            'isolated_postdrop_raw_outliers': outliers},
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.capture)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'rows': result['rows'], 'out': str(args.out),
                      'release': result['final_release']}, indent=2))
