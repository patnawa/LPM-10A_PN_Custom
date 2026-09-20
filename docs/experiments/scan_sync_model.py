"""Independent, synthetic model of the optional Sync32 envelope protocol.

This models timer ticks, five ADC readings, trimmed sampling, and binary
correlation. It does NOT model carrier propagation, the analogue front end,
gain, crosstalk, cable identity, CPU timing, or actual oscillator errors.

Run with Python 3.10+: ``python docs/experiments/scan_sync_model.py``.
Only the standard library is required. Both protocols receive the same
48-sample observation time, ADC baseline, high-minus-low amplitude, and
seeded additive noise. Their ON duties differ: Sync32 is about 50%; legacy is
62.5%. This is an equal-amplitude comparison, not equal average power.
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import random
from functools import lru_cache

LEGACY_CODE = (1, 0, 1, 1, 0, 1, 1, 0)
SYNC_WORD = 0x1F25EB11
SYNC_CODE = tuple((SYNC_WORD >> (31-i)) & 1 for i in range(32))
TX_TICK_US = 101
RX_SAMPLE_US = 5003.125
RX_SAMPLE_TICKS = 200
# ADC calls counted in TIM5 IRQs from the relevant acquisition origin.
# Fresh startup and immediate rearm have different counter phases.
FIRST_ADC_READ_TICKS = (140, 160, 180, 200, 220)
STEADY_ADC_READ_TICKS = (120, 140, 160, 180, 200)
SYNC_ADD = 808
SYNC_LIMIT = 40025
WINDOW = 48
SEED = 20260920


def emitted_bit(tick: int, mode: str = 'sync32') -> int:
    """Output during tick, before advancing the TX accumulator.

    Sync32 uses ``acc += 808; if acc >= 40025: acc -= 40025`` and
    advances its code index on overflow. Both initial state values are zero.
    Integer arithmetic captures the exact 49/50-tick chip schedule.
    """
    if mode == 'sync32':
        return SYNC_CODE[(tick * SYNC_ADD // SYNC_LIMIT) % 32]
    if mode == 'legacy':
        return LEGACY_CODE[(tick // 50) % 8]
    raise ValueError(f'unknown mode: {mode}')


def sampled_window(mode: str = 'sync32', phase: float = 0.0,
                   ratio: float = 1.0, noise: int = 0,
                   rng: random.Random | None = None, low: int = 1000,
                   amplitude: int = 300, tick_offset: int = 0,
                   fresh_start: bool = False) -> list[int]:
    """Model the existing five-read, drop-extremes envelope sampler.

    ``phase`` is a starting offset in nominal RX sample periods. ``ratio``
    scales the RX period relative to the TX timer; 1.0 means the nominal
    hardware divisors. ``tick_offset`` permits other dither accumulator
    positions without resetting the waveform. Noise is independently drawn
    from the inclusive integer range [-noise, noise] for every ADC read.

    Default read positions 0.6..1.0 are relative to the previous completed
    window with immediate rearm. ``fresh_start=True`` uses 0.7..1.1 relative
    to fresh startup instead. Both schedules follow ADC calls observed while
    executing the actual TIM5 handler in Unicorn. Timer time is nominal;
    ADC latency and the analogue front end remain unmodeled.
    """
    if noise < 0 or ratio <= 0:
        raise ValueError('noise must be nonnegative and ratio positive')
    if rng is None:
        rng = random.Random(SEED)
    read_ticks = FIRST_ADC_READ_TICKS if fresh_start else STEADY_ADC_READ_TICKS
    samples = []
    for i in range(WINDOW):
        reads = []
        for sub in range(5):
            t = (phase + (i + read_ticks[0] / RX_SAMPLE_TICKS + sub * 0.1)
                 * ratio) * RX_SAMPLE_US
            tick = tick_offset + math.floor(t / TX_TICK_US)
            value = low + amplitude * emitted_bit(tick, mode)
            if noise:
                value += rng.randint(-noise, noise)
            reads.append(max(0, min(4095, value)))
        samples.append((sum(reads)-min(reads)-max(reads)) // 3)
    return samples


def _word(bits) -> int:
    result = 0
    for bit in bits:
        result = (result << 1) | int(bit)
    return result


@lru_cache(maxsize=None)
def templates(code: tuple[int, ...]) -> tuple[int, ...]:
    return tuple(_word(code[(i+p) % len(code)] for i in range(WINDOW))
                 for p in range(len(code)))


def threshold_bits(samples: list[int]) -> tuple[int, int]:
    if len(samples) != WINDOW or not all(0 <= x <= 4095 for x in samples):
        raise ValueError('expected 48 samples within the 12-bit ADC range')
    mean = (sum(samples)-min(samples)-max(samples)) // 46
    return mean, _word(x > mean for x in samples)


def fitted_phase(samples: list[int], code: tuple[int, ...] = SYNC_CODE):
    """Strict four-total/two-per-16 fit, without legacy exact fallback."""
    _, bits = threshold_bits(samples)
    for phase, wanted in enumerate(templates(code)):
        difference = bits ^ wanted
        if difference.bit_count() <= 4 and all(
                ((difference >> offset) & 0xFFFF).bit_count() <= 2
                for offset in (0, 16, 32)):
            return phase
    return None


def detect(samples: list[int], code: tuple[int, ...] = SYNC_CODE,
           exact_fallback: bool = False) -> bool:
    """Reference acceptance with the existing contrast and high-sum gates."""
    mean, bits = threshold_bits(samples)
    if sum(abs(x-mean) for x in samples) < 192:
        return False
    if 5 + sum(x for x in samples if x > mean) < 1000:
        return False
    if fitted_phase(samples, code) is not None:
        return True
    if exact_fallback:
        if code != LEGACY_CODE:
            raise ValueError('the exact fallback belongs only to legacy B6')
        return sum(((bits >> start) & 0xFFFF) == 0xB6B6
                   for start in range(33)) >= 2
    return False


def certificates() -> dict:
    """Exhaustive finite-code properties, independent of firmware assembly."""
    words = templates(SYNC_CODE)
    distance48 = min((a ^ b).bit_count()
                     for a, b in itertools.combinations(words, 2))
    distance32 = min(sum(SYNC_CODE[i] != SYNC_CODE[(i+p) % 32]
                         for i in range(32)) for p in range(1, 32))
    periodic8_distance = min((word ^ _word((code >> (7-i % 8)) & 1
                            for i in range(48))).bit_count()
                            for word in words for code in range(256))
    exact_union_distance = 48
    compatible_pairs = 0
    signature = LEGACY_CODE * 2
    for a, b in itertools.combinations(range(33), 2):
        requirements = dict(enumerate(signature, a))
        if any(i in requirements and requirements[i] != bit
               for i, bit in enumerate(signature, b)):
            continue
        requirements.update(enumerate(signature, b))
        compatible_pairs += 1
        for phase in range(32):
            differences = sum(SYNC_CODE[(i+phase) % 32] != bit
                              for i, bit in requirements.items())
            exact_union_distance = min(exact_union_distance, differences)
    # LCM of the accumulator period and the code period: 101 code frames.
    full_period_ticks = SYNC_LIMIT * 4
    on_ticks = sum(emitted_bit(t) for t in range(full_period_ticks))
    doubled = ''.join(map(str, SYNC_CODE*2))
    maximum_run = max(len(run) for bit in '01' for run in doubled.split(bit))
    return {
        'word_hex': f'{SYNC_WORD:08X}',
        'ones_per_32_chips': sum(SYNC_CODE),
        'maximum_equal_chip_run': maximum_run,
        'minimum_cyclic_distance_32_samples': distance32,
        'minimum_cyclic_distance_48_samples': distance48,
        'high_group_count_48_range': [min(w.bit_count() for w in words),
                                     max(w.bit_count() for w in words)],
        'minimum_distance_to_any_repeated_8_bit_word': periodic8_distance,
        'minimum_edits_to_two_compatible_legacy_exact_windows': exact_union_distance,
        'compatible_legacy_window_pairs': compatible_pairs,
        'exact_dither_and_code_period_ticks': full_period_ticks,
        'on_ticks_in_exact_period': on_ticks,
        'sync_on_duty': on_ticks / full_period_ticks,
        'legacy_on_duty': sum(LEGACY_CODE) / len(LEGACY_CODE),
        'nominal_sync_chip_us': SYNC_LIMIT * TX_TICK_US / SYNC_ADD,
        'nominal_legacy_chip_us': 50 * TX_TICK_US,
        'rx_sample_interval_timer_ticks': RX_SAMPLE_TICKS,
        'fresh_start_adc_read_timer_ticks': list(FIRST_ADC_READ_TICKS),
        'immediate_rearm_adc_read_timer_ticks': list(STEADY_ADC_READ_TICKS),
    }


def benchmark(samples_per_phase: int = 16, fresh_start: bool = False) -> list[dict]:
    """Paired deterministic phase/noise trials; percentages are synthetic."""
    results = []
    count = 32 * samples_per_phase
    for ratio in (0.98, 0.99, 0.997, 0.999, 1.0, 1.001, 1.003, 1.01, 1.02):
        for noise in (0, 100, 200, 300):
            row = {'rx_clock_ratio': ratio, 'uniform_noise_half_range': noise,
                   'windows_per_protocol': count}
            for mode, code in (('legacy', LEGACY_CODE), ('sync32', SYNC_CODE)):
                hits = 0
                missed_phases = []
                for index in range(count):
                    phase = index / samples_per_phase
                    window = sampled_window(mode, phase, ratio, noise,
                                            random.Random(SEED+index),
                                            fresh_start=fresh_start)
                    accepted = detect(window, code, mode == 'legacy')
                    hits += accepted
                    if not accepted:
                        missed_phases.append(phase)
                row[f'{mode}_hits'] = hits
                if not noise:
                    row[f'{mode}_missed_phases'] = missed_phases
            results.append(row)
    return results


def clean_phase_audit(samples_per_phase: int = 256,
                      fresh_start: bool = False) -> list[dict]:
    """Dense clean phase sweep; catches blind spots missed by coarse grids.

    Phases cover the first nominal 32-chip frame. This is a finite grid, not
    a probability model or proof for every dither epoch and analogue phase.
    """
    results = []
    count = 32*samples_per_phase
    for ratio in (0.997, 0.999, 1.0, 1.001, 1.003):
        row = {'rx_clock_ratio': ratio, 'windows_per_protocol': count}
        for mode, code in (('legacy', LEGACY_CODE), ('sync32', SYNC_CODE)):
            missed = [i for i in range(count) if not detect(
                sampled_window(mode, phase=i/samples_per_phase, ratio=ratio,
                               fresh_start=fresh_start),
                code, mode == 'legacy')]
            row[f'{mode}_hits'] = count-len(missed)
            row[f'{mode}_missed_fractional_phases'] = sorted({
                (i % samples_per_phase)/samples_per_phase for i in missed})
        results.append(row)
    return results


def self_check() -> None:
    facts = certificates()
    assert facts['minimum_cyclic_distance_32_samples'] == 16
    assert facts['maximum_equal_chip_run'] == 5
    assert facts['minimum_cyclic_distance_48_samples'] == 20
    assert facts['minimum_distance_to_any_repeated_8_bit_word'] == 14
    assert facts['minimum_edits_to_two_compatible_legacy_exact_windows'] == 7
    assert facts['nominal_sync_chip_us'] == RX_SAMPLE_US
    assert facts['on_ticks_in_exact_period'] == 80049
    # Fresh-reset TIM5 trace: 140/160/180/200/220, then 340/360/.../420.
    # This catches a return to the former one-substep-early approximation.
    assert tuple(t / RX_SAMPLE_TICKS for t in FIRST_ADC_READ_TICKS) == (
        0.7, 0.8, 0.9, 1.0, 1.1)
    assert tuple(math.floor(t * RX_SAMPLE_US / RX_SAMPLE_TICKS / TX_TICK_US)
                 for t in FIRST_ADC_READ_TICKS) == (34, 39, 44, 49, 54)
    assert tuple(RX_SAMPLE_TICKS+t for t in FIRST_ADC_READ_TICKS) == (
        340, 360, 380, 400, 420)
    # Completion at IRQ 9620 rearms the next window, whose reads start at
    # 9740: 120 IRQs later. Subsequent groups again repeat every 200 IRQs.
    assert tuple(t / RX_SAMPLE_TICKS for t in STEADY_ADC_READ_TICKS) == (
        0.6, 0.7, 0.8, 0.9, 1.0)
    assert tuple(9620+t for t in STEADY_ADC_READ_TICKS) == (
        9740, 9760, 9780, 9800, 9820)
    # Startup changes the aperture origin, not its spacing or code rate.
    for ratio in (0.997, 1.0, 1.003):
        for phase in (0.0, 0.125, 3.5, 31.875):
            assert sampled_window(phase=phase, ratio=ratio, fresh_start=True) == (
                sampled_window(phase=phase+0.1*ratio, ratio=ratio))
    for phase in range(32):
        clean = [1000+300*SYNC_CODE[(i+phase) % 32] for i in range(48)]
        assert fitted_phase(clean) == phase and detect(clean)
        assert not detect(clean, LEGACY_CODE, True)
        # Every single-bit error and representative permitted four-bit errors.
        for errors in [(i,) for i in range(48)] + [(0, 1, 16, 32), (15, 16, 31, 32)]:
            damaged = clean.copy()
            for i in errors:
                damaged[i] = 2300-damaged[i]
            assert fitted_phase(damaged) == phase and detect(damaged)
    for phase in range(8):
        legacy = [1000+300*LEGACY_CODE[(i+phase) % 8] for i in range(48)]
        assert detect(legacy, LEGACY_CODE, True) and not detect(legacy)
    for level in (0, 1000, 4095):
        assert not detect([level]*48)
    # Verify the closed-form emitter against the actual accumulator recurrence.
    accumulator = index = 0
    for tick in range(SYNC_LIMIT*4):
        assert emitted_bit(tick) == SYNC_CODE[index]
        accumulator += SYNC_ADD
        if accumulator >= SYNC_LIMIT:
            accumulator -= SYNC_LIMIT
            index = (index+1) % 32
    assert (accumulator, index) == (0, 0)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--samples-per-phase', type=int, default=64)
    parser.add_argument('--json', action='store_true', help='include clean missed-phase lists')
    parser.add_argument('--fresh-start', action='store_true',
                        help='use the first startup aperture, not immediate rearm')
    args = parser.parse_args()
    if args.samples_per_phase < 1:
        parser.error('--samples-per-phase must be positive')
    self_check()
    facts = certificates()
    results = benchmark(args.samples_per_phase, args.fresh_start)
    phase_audit = clean_phase_audit(fresh_start=args.fresh_start)
    sampling_origin = 'fresh_start' if args.fresh_start else 'immediate_rearm'
    if args.json:
        print(json.dumps({'sampling_origin': sampling_origin,
                          'certificates': facts, 'benchmark': results,
                          'dense_clean_phase_audit': phase_audit}, indent=2))
        return
    print(json.dumps(facts, indent=2))
    print(f'\nSampling origin: {sampling_origin}')
    print('\nEqual 300-count amplitude, 48 samples, baseline 1000; different ON duties.')
    print('RX clock ratio | noise +/- | legacy hits | Sync32 hits | windows')
    for row in results:
        print(f"{row['rx_clock_ratio']:.3f} | {row['uniform_noise_half_range']:3d} | "
              f"{row['legacy_hits']:4d} | {row['sync32_hits']:4d} | "
              f"{row['windows_per_protocol']}")
    print('\nDense clean phase audit, 256 offsets per chip, first 32-chip frame:')
    print('RX clock ratio | legacy hits | Sync32 hits | windows')
    for row in phase_audit:
        print(f"{row['rx_clock_ratio']:.3f} | {row['legacy_hits']:4d} | "
              f"{row['sync32_hits']:4d} | {row['windows_per_protocol']}")
    print('These are synthetic detection results, not measured range or cable selectivity.')


if __name__ == '__main__':
    main()
