"""Reproducible RX analog-path audit; no firmware changes or hardware claims.

Run: python docs/experiments/rx_analog_performance_audit.py [--arm]

The standard-library model uses an independent mathematical 64-point DFT.
--arm also runs the exact delivered PN 1.10 instructions through the existing
Unicorn harness, checks all 31 calculated bins, and measures acquisition and
feedback scheduling. ADC inputs, peripheral status and interrupt arrival are
modeled; instruction counts are not Cortex-M cycle or deadline measurements.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import random
import struct
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
RX_DIR = ROOT / 'LPM-10A/Firmware File/rx-sdk'
RX_IMAGE = RX_DIR.parent / 'experimental/APP_LPM-10RX_PN1.10-sync.bin'
RX_SHA256 = '6570f521054d77ee97c1a0e37e5a9da0a975d41d452e5f14e63aadb68a9f6e21'
TIM5_HZ = 64_000_000/1601
SAMPLE_HZ = TIM5_HZ/13
BIN_HZ = SAMPLE_HZ/64
TARGET_HZ = BIN_HZ*17
TX_HZ = 1_000_000/101/12
COEFF = tuple(tuple(complex(math.cos(2*math.pi*k*i/64),
                            -math.sin(2*math.pi*k*i/64)) for i in range(64))
              for k in range(1, 32))


def spectrum(samples):
    return [2*abs(sum(v*c for v, c in zip(samples, row)))/64 for row in COEFF]


def classify(samples):
    # Deliberately preserve vendor's divisor 12, although 29 bins enter it.
    bins = [int(v) for v in spectrum(samples)]
    target = bins[16]
    floor = (sum(bins)-bins[0]-target)//12
    margin = target-floor
    beep = 50 if margin > 600 else 100 if margin > 200 else 200 if margin > 10 else 0
    return {'target': target, 'noise_metric': floor, 'margin': margin, 'beep_ms': beep}


def sine(frequency=TX_HZ, amplitude=300, phase=0, dc=2048, noise=0, rng=None):
    rng = rng or random.Random(20260920)
    return [max(0, min(4095, round(dc+amplitude*math.cos(2*math.pi*frequency*i/SAMPLE_HZ+phase))
                       +(rng.randint(-noise, noise) if noise else 0))) for i in range(64)]


def square(step=300, phase=0, frequency=TX_HZ, noise=0, rng=None):
    rng = rng or random.Random(20260920)
    return [max(0, min(4095, 1000+step*int((i*frequency/SAMPLE_HZ+phase) % 1 >= 0.5)
                       +(rng.randint(-noise, noise) if noise else 0))) for i in range(64)]


def summarize(windows):
    answers = [classify(v) for v in windows]
    return {'windows': len(answers), 'accepted': sum(bool(a['beep_ms']) for a in answers),
            'beep_ms_histogram': dict(sorted(Counter(a['beep_ms'] for a in answers).items())),
            'margin_min_max': [min(a['margin'] for a in answers), max(a['margin'] for a in answers)]}


def model_audit():
    frequency = []
    for hz in (50, 60, 700, 750, 775, 790, 800, TARGET_HZ, TX_HZ, 835, 850, 865, 880, 900, 1000):
        frequency.append({'input_hz': round(hz, 6),
                          **summarize(sine(hz, phase=2*math.pi*p/16) for p in range(16))})
    square_steps = []
    for step in (10, 20, 25, 50, 100, 200, 300, 500, 1000, 2000, 3000):
        square_steps.append({'high_minus_low_adc': step,
                             **summarize(square(step, phase=p/64) for p in range(64))})
    noise = []
    for step in (100, 300, 1000):
        for magnitude in (0, 50, 100, 200, 400, 800):
            rng = random.Random(0x825+step+magnitude)
            noise.append({'high_minus_low_adc': step, 'uniform_noise_plus_minus': magnitude,
                          **summarize(square(step, p/128, noise=magnitude, rng=rng) for p in range(128))})
    noise_only = []
    for magnitude in (50, 100, 200, 400, 800, 1600):
        rng = random.Random(0xBA825+magnitude)
        noise_only.append({'uniform_noise_plus_minus': magnitude,
                           **summarize([2048+rng.randint(-magnitude, magnitude) for _ in range(64)]
                                       for _ in range(1024))})
    bursts = []
    for length in (2, 4, 8, 16, 32, 48, 64):
        windows = []
        for phase in range(16):
            tone = sine(amplitude=300, phase=2*math.pi*phase/16)
            for start in range(65-length):
                windows.append([tone[i] if start <= i < start+length else 2048 for i in range(64)])
        bursts.append({'tone_samples': length, 'burst_duration_ms': 1000*length/SAMPLE_HZ,
                       **summarize(windows)})
    clipping = []
    for amplitude in (100, 300, 600, 1000, 1800, 2047, 2500, 4000, 8000):
        values = sine(amplitude=amplitude)
        clipping.append({'requested_sine_amplitude': amplitude,
                         'rail_samples': sum(v in (0, 4095) for v in values), **classify(values)})
    aliases = []
    for hz in (TX_HZ, SAMPLE_HZ-TX_HZ, SAMPLE_HZ+TX_HZ, 2*SAMPLE_HZ-TX_HZ):
        aliases.append({'input_hz': hz, **classify(sine(hz))})
    return {'clock': {'tim5_hz': TIM5_HZ, 'analog_adc_sample_hz': SAMPLE_HZ,
                      'sample_spacing_us': 1e6/SAMPLE_HZ, 'window_ms': 64000/SAMPLE_HZ,
                      'bin_spacing_hz': BIN_HZ, 'target_bin': 17, 'target_hz': TARGET_HZ,
                      'nominal_tx_hz': TX_HZ, 'target_offset_hz': TX_HZ-TARGET_HZ},
            'frequency_response_sine_amplitude_300': frequency,
            'square_amplitude_response': square_steps, 'square_uniform_noise': noise,
            'uniform_noise_only_open_gate': noise_only, 'finite_sine_bursts': bursts,
            'sine_clipping_response': clipping, 'sampling_aliases_without_analog_filter': aliases}


def arm_audit():
    sys.path.insert(0, str(RX_DIR))
    import test_rx_sync
    from test_rx_followup import ANALYZERS, GATE_STATE, INDICES, TIM5
    from sampling_fixes import PUBLISH_TONE
    from verify_control import BEEP, MODE, SP
    from verify_digital import ACTIVE, BUFFER, GAP
    from unicorn import UC_HOOK_CODE
    from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_PC, UC_ARM_REG_LR, UC_ARM_REG_SP

    class Harness(unittest.TestCase):
        cpu = test_rx_sync.Sync.cpu
        execute = test_rx_sync.Sync.execute
        boundary = test_rx_sync.Sync.boundary

    h = Harness()
    h.data = RX_IMAGE.read_bytes()
    assert hashlib.sha256(h.data).hexdigest() == RX_SHA256

    def analyze(samples, profile=False):
        c = h.cpu()
        c.w8(MODE, 1)
        c.w16(0x20000068, 580)
        c.w8(ACTIVE, 0)
        c.uc.mem_write(BUFFER, struct.pack('<64H', *samples))
        observed = {}
        def result(uc, address, size, user):
            stack = uc.reg_read(UC_ARM_REG_SP)
            observed['bins'] = list(struct.unpack('<31H', uc.mem_read(stack+18, 62)))
        def decision(uc, address, size, user):
            stack = uc.reg_read(UC_ARM_REG_SP)
            observed['target'] = c.read(stack+8, 2)
            observed['noise_metric'] = c.read(stack+4, 2)
        hooks = [c.uc.hook_add(UC_HOOK_CODE, result, begin=0x08009FCE, end=0x08009FCE),
                 c.uc.hook_add(UC_HOOK_CODE, decision, begin=0x08009FFE, end=0x08009FFE)]
        if profile:
            observed.update(instructions=0, maximum_stack_bytes=0, inactive_during_dft=True)
            def count(uc, address, size, user):
                observed['instructions'] += 1
                observed['maximum_stack_bytes'] = max(observed['maximum_stack_bytes'],
                                                     SP-uc.reg_read(UC_ARM_REG_SP))
                if address == 0x0800B4A0:
                    observed['inactive_during_dft'] &= c.read(ACTIVE) == 0
            hooks.append(c.uc.hook_add(UC_HOOK_CODE, count))
        try:
            h.execute(c, ANALYZERS[1])
        finally:
            for hook in hooks:
                c.uc.hook_del(hook)
        reference = spectrum(samples)
        observed['max_bin_error'] = max(abs(a-b) for a, b in zip(observed['bins'], reference))
        assert observed['max_bin_error'] <= 2
        assert observed['noise_metric'] == (sum(observed['bins'])-observed['bins'][0]-observed['target'])//12
        observed['margin'] = observed['target']-observed['noise_metric']
        observed['beep_ms'] = c.read(BEEP)
        observed['gap_ms'] = c.read(GAP)
        assert observed['beep_ms'] == observed['gap_ms']
        assert c.read(ACTIVE) == 1
        del observed['bins']
        return observed

    cases = []
    for hz in (50, 60, 750, 800, TARGET_HZ, TX_HZ, 850, 900, SAMPLE_HZ-TX_HZ):
        for amplitude in (15, 300, 1800):
            cases.append((f'sine_{hz:.6f}Hz_A{amplitude}', sine(hz, amplitude)))
    for step in (20, 100, 300, 1000, 3000):
        for phase in (0, 0.125, 0.5):
            cases.append((f'square_step{step}_phase{phase}', square(step, phase)))
    for amplitude in (2500, 4000, 8000):
        cases.append((f'clipped_sine_A{amplitude}', sine(amplitude=amplitude)))
    for noise in (100, 400, 800):
        cases.append((f'noisy_square_step300_noise{noise}', square(300, noise=noise)))
    for magnitude in (200, 400, 800, 1600):
        rng = random.Random(0xBA825+magnitude)
        for window in range(1024):
            samples = [2048+rng.randint(-magnitude, magnitude) for _ in range(64)]
            if classify(samples)['margin'] >= 16:
                cases.append((f'noise_only_magnitude{magnitude}_window{window}', samples))
                break
    results = [{'case': name, **analyze(samples)} for name, samples in cases]
    profiles = [{'case': name, **analyze(samples, profile=True)}
                for name, samples in (('dc', [2048]*64), ('sine_A15', sine(TARGET_HZ, 15)),
                                      ('sine_A300', sine(TARGET_HZ, 300)), ('sine_A2000', sine(TARGET_HZ, 2000)))]

    # Execute every IRQ, not only sample-due events. The gate is open as set by
    # the harness; its electrical source and analogue gain remain unknown.
    c = h.cpu()
    c.w8(MODE, 1)
    c.w16(0x20000068, 580)
    c.w8(GATE_STATE, 0)
    h.boundary(c)
    tick = 0
    reads = []
    def adc(uc, address, size, user):
        index = c.read(INDICES[1])
        reads.append((tick, index))
        uc.reg_write(UC_ARM_REG_R0, 1000+index)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
    hook = c.uc.hook_add(UC_HOOK_CODE, adc, begin=0x080072A4, end=0x080072A4)
    try:
        while c.read(ACTIVE) and tick < 900:
            tick += 1
            h.execute(c, TIM5)
    finally:
        c.uc.hook_del(hook)
    assert reads == [(13*(i+1), i) for i in range(64)]
    assert tick == 832 and c.read(ACTIVE) == 0
    assert list(struct.unpack('<64H', c.uc.mem_read(BUFFER, 128))) == list(range(1000, 1064))

    def cadence(initial, later=None):
        c = h.cpu()
        c.w8(MODE, 1)
        c.w16(0x20000068, 580)
        h.execute(c, PUBLISH_TONE, 0, initial)
        starts, widths = [(0, initial)], []
        began = 0
        for tick in range(1, 1001):
            before = c.read(BEEP)
            c.run()
            if before and not c.read(BEEP):
                widths.append(tick-began)
            if tick % 21 == 0:
                duration = initial if later is None or tick < 21 else later
                h.execute(c, PUBLISH_TONE, 0, duration)
            if not before and c.read(BEEP):
                began = tick
                starts.append((tick, c.read(BEEP)))
        return {'starts_tick_and_width': starts, 'completed_widths': widths}

    return {'image_sha256': RX_SHA256, 'arm_window_count': len(results),
            'actual_dft_results': results, 'instruction_profiles': profiles,
            'acquisition': {'irq_count': tick, 'adc_count': len(reads),
                            'first_adc_ticks': [a[0] for a in reads[:5]],
                            'last_adc_tick': reads[-1][0]},
            'publisher_with_modeled_21ms_analysis_arrivals': {
                str(duration): cadence(duration) for duration in (50, 100, 200)},
            'weak_to_strong_at_tick21': cadence(200, 50)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arm', action='store_true', help='also execute the delivered RX binary')
    args = parser.parse_args()
    output = model_audit()
    if args.arm:
        output['arm'] = arm_audit()
    print(json.dumps(output, indent=2))


if __name__ == '__main__':
    main()
