"""Actual PN2.26 / PN2.27 / PN2.27A TX code and modeled RX compatibility.

Run from the repository root with --json to retain measurements. Builds both
candidates in memory and verifies any emitted candidate is byte-identical.
No firmware file or device is changed. Peripheral registers and CPU instruction
counts are observed; cable coupling, analog filtering and CPU cycles are not
modeled. RX cases are fresh fixed-gain acquisitions, not continuous audio tests.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from tx_rx_current_tone_audit import FW, TX_SHA, RX_SHA, evaluate_link
from tx_tone_performance_audit import AuditMachine, clock_configuration
from test_scan_hardware import requested_wave, TIM1_EXPECTED


RECEIVERS = {
    'PN1.24': ('APP_LPM-10RX_PN1.24-gain-precision.bin', RX_SHA),
    'PN1.23G': ('APP_LPM-10RX_PN1.23G-digital-gain.bin',
               'a0822e2f454e08d0a213e63a1bbf0cac9948776dd8b067560d4786605b0307bb'),
}


def profile(data, mode, alignment=False):
    machine = AuditMachine(data, mode, clocks=True)
    counts, separations = [], set()
    trace = []
    for tick in range(10001):
        start, before = machine.instructions, len(machine.edge_writes)
        machine.timer_tick(tick)
        counts.append(machine.instructions-start)
        selected = machine.carrier_pins_selected()
        expected = (int(((tick+1)*165 % 2000) >= 1000)
                    if mode == 2 and alignment else requested_wave(mode, tick))
        assert selected == expected, (mode, alignment, tick, selected, expected)
        trace.append(selected)
        writes = machine.edge_writes[before:]
        if writes:
            assert len(writes) == 2
            separations.add(writes[1][0]-writes[0][0])
    assert machine.timer_configuration() == TIM1_EXPECTED
    assert (machine.r32(0x40000028), machine.r32(0x4000002C)) == (71, 100)
    period = 400 if mode == 1 or alignment else 12
    assert all(trace[i] == trace[i % period] for i in range(len(trace)))
    period_trace = trace[:period]
    edges = [i for i in range(period) if period_trace[i] != period_trace[i-1]]
    run_lengths = Counter((edges[(i+1) % len(edges)]-start) % period
                         for i, start in enumerate(edges))
    return dict(irq_ticks=len(counts),
                min_instructions=min(counts), max_instructions=max(counts),
                mean_instructions=sum(counts)/len(counts),
                inter_pin_write_instructions=sorted(separations),
                period_ticks=period, envelope_duty=sum(period_trace)/period,
                edge_run_ticks=dict(sorted(run_lengths.items())),
                trace=period_trace)


def run():
    # TX and RX toolkits contain same-named modules (e.g. audit_fixes).
    # Build in a clean TX-only interpreter so RX fixture imports cannot silently
    # alter the patch registry. Transfer the finalized bytes, never patch files.
    script = ('import contextlib, importlib, io, sys\n'
              'with contextlib.redirect_stdout(io.StringIO()):\n'
              '    data = bytes(importlib.import_module(sys.argv[1]).build_candidate().data)\n'
              'sys.stdout.buffer.write(data)\n')
    def build(module):
        result = subprocess.run([sys.executable, '-c', script, module],
                                cwd=FW/'sdk', capture_output=True, check=True)
        return result.stdout
    parent = (FW/'experimental/LPM-10A-TX_PN2.26-qc-display.bin').read_bytes()
    assert hashlib.sha256(parent).hexdigest() == TX_SHA
    base, aligned = build('tone_precision'), build('tone_alignment')
    for filename, data in (('LPM-10A-TX_PN2.27-tone-precision.bin', base),
                           ('LPM-10A-TX_PN2.27A-analog-alignment.bin', aligned)):
        path = FW/'experimental'/filename
        if path.exists():
            assert path.read_bytes() == data, f'stale artifact: {path}'

    images = {'PN2.26': parent, 'PN2.27': base, 'PN2.27A': aligned}
    waveform = {name: {str(mode): profile(data, mode, name == 'PN2.27A')
                       for mode in (1, 2)} for name, data in images.items()}
    for name in ('PN2.27', 'PN2.27A'):
        assert waveform[name]['1']['trace'] == waveform['PN2.26']['1']['trace']
        for mode in ('1', '2'):
            assert waveform[name][mode]['mean_instructions'] < waveform['PN2.26'][mode]['mean_instructions']
            assert max(waveform[name][mode]['inter_pin_write_instructions']) < 126
    assert waveform['PN2.27']['2']['trace'] == waveform['PN2.26']['2']['trace']
    assert waveform['PN2.27A']['2']['edge_run_ticks'] == {6: 62, 7: 4}
    clocks = {name: clock_configuration(data) for name, data in images.items()}
    # The shared timer and carrier settings stay exact. The helper's derived
    # nominal_analog_hz assumes the old divider, so omit that in this report.
    for values in clocks.values():
        values.pop('nominal_analog_hz')
    assert clocks['PN2.26'] == clocks['PN2.27'] == clocks['PN2.27A']

    offsets = [(i+.213)*1200/127 for i in range(127)]
    received = {}
    for version, (filename, digest) in RECEIVERS.items():
        rx = (FW/'experimental'/filename).read_bytes()
        assert hashlib.sha256(rx).hexdigest() == digest
        # PN2.27's exact trace equality proves that replaying PN2.26 separately
        # would be duplicate work; identical ADC inputs execute identical RX code.
        received[version] = dict(
            sha256=digest,
            digital_all_tx=[evaluate_link(rx, waveform['PN2.27']['1']['trace'],
                                         0, 101, pp) for pp in (0, 12, 24, 80)],
            analog={name: [evaluate_link(rx, waveform[name]['2']['trace'],
                                        1, 101, pp, offsets)
                           for pp in (0, 12, 24, 80)]
                    for name in ('PN2.27', 'PN2.27A')})
        for row in received[version]['digital_all_tx']:
            assert row['accepted'] == (0 if row['peak_to_peak_counts'] == 0 else 8)
        for name, rows in received[version]['analog'].items():
            assert rows[0]['accepted'] == 0
            assert rows[-1]['accepted'] == 127, (version, name, rows[-1])
        old, new = (received[version]['analog'][name][2]['accepted']
                    for name in ('PN2.27', 'PN2.27A'))
        assert new >= old, (version, old, new)
    return dict(
        status='Firmware-model assertions passed; hardware validation pending',
        tx_sha256={name: hashlib.sha256(data).hexdigest() for name, data in images.items()},
        bytes={name: len(data) for name, data in images.items()},
        clocks=clocks['PN2.27'], waveforms=waveform,
        analog_frequency_hz={'PN2.26': 1/(12*101e-6), 'PN2.27': 1/(12*101e-6),
                             'PN2.27A': 33/(400*101e-6)},
        modeled_phase_offsets_ticks=offsets,
        rx_windows=len(RECEIVERS)*(4*8+2*4*127), receivers=received,
        limitation='Actual Thumb register traces and actual RX code with ideal square ADC envelope, '
                   'fixed gain7, nominal timers, finite phase/amplitude corpus; '
                   'no noise, filtering, loaded output, movement, continuous audio or cycle timing.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', type=Path)
    args = parser.parse_args()
    result = run()
    output = json.dumps(result, indent=2)+'\n'
    if args.json:
        if args.json.suffix.lower() != '.json':
            parser.error('--json must name a .json file')
        args.json.write_text(output, encoding='utf-8')
        print(f"PASS: 60006 actual TX IRQs and {result['rx_windows']} modeled RX windows; saved {args.json}")
    else:
        print(output, end='')
