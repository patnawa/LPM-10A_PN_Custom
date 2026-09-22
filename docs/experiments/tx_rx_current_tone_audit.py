"""Published TX PN2.26 gate trace -> modeled link -> published RX PN1.24.

Run from any directory. Executes actual TX GPIO/IRQ and RX sampler/analyzer
code. The link is an ideal unfiltered envelope: it is not a cable/front-end
simulation or an electrical sensitivity measurement. Alternate TX tick lengths
are timing probes only. No firmware file or device is modified; the Analog
prototype changes emulator memory only.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
FW = ROOT / 'LPM-10A' / 'Firmware File'
sys.path.insert(0, str(FW/'rx-sdk'))
sys.path.append(str(FW/'sdk'))

from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_R0
from test_scan_hardware import RealCarrierMachine, CARRIER_INIT, requested_wave
from verify_scan import IRQ
import test_rx_tracking_streams as streams
from test_rx_followup import ANALYZERS, GRADE
from verify_control import MODE
from verify_digital import ACTIVE, GATE, RECENT
from tx_pn226_waveform_audit import analog_accumulator_experiment

TX_SHA = 'c77579f018bb820532b3c5974ae63fbf04c4e60359188f7e39a8a8f9a1533df8'
RX_SHA = '780951565cca543e50d38537cd179ee1793562c6a4642b688c8143b0e4d8b1ce'


class LinkCPU(streams.StreamCPU):
    def __init__(self, data, trace, mode, tick_us, phase, pp):
        super().__init__(data)
        self.trace, self.tick_us = trace, tick_us
        self.phase, self.pp = phase, pp
        self.w8(MODE, mode)
        self.w16(GATE, 4060)
        self.w16(GATE+2, 7)
        self.uc.mem_write(0x20000200, bytes((7, 0, 0, 7)))

    def adc(self, uc, address, size, user):
        tick = self.read(streams.TIMER_COUNTER, 4)
        index = math.floor(tick*25.015625/self.tick_us + self.phase*len(self.trace))
        gate = self.trace[index % len(self.trace)]
        value = round(2048+self.pp*(gate-.5))
        self.events.append((tick, value))
        uc.reg_write(UC_ARM_REG_R0, value)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))


def evaluate_link(rx, trace, mode, tick_us, pp, phase_offsets_ticks=None):
    runner = streams.TrackingStreams()
    grades, strengths, acquired = [], [], []
    if phase_offsets_ticks is None:
        # Eighth-cycle phase offsets plus a non-grid fraction.
        phase_offsets_ticks = [(i+.213)*len(trace)/8 for i in range(8)]
    for phase_tick in phase_offsets_ticks:
        phase = phase_tick/len(trace)
        c = LinkCPU(rx, trace, mode, tick_us, phase, pp)
        runner.boundary(c)
        for _ in range(50):
            if not c.read(ACTIVE):
                break
            runner.timers(c, 200)
        assert c.read(ACTIVE) == 0
        scores = []
        hook = c.uc.hook_add(UC_HOOK_CODE,
            lambda uc,a,s,u: scores.append(uc.reg_read(UC_ARM_REG_R0)),
            begin=0x0800A048, end=0x0800A048)
        try:
            runner.execute(c, ANALYZERS[mode], budget=100000)
        finally:
            c.uc.hook_del(hook)
        grades.append(c.read(GRADE))
        strengths.append(scores[-1] if scores else 0)
        acquired.append(c.read(RECENT, 2) > 500)
        assert len(c.events) == (240 if mode == 0 else 64)
        if not pp:
            assert not acquired[-1], 'flat input must stay rejected'
    return dict(mode=('Digital', 'Analog')[mode], modeled_tx_tick_us=tick_us,
                peak_to_peak_counts=pp, accepted=sum(acquired), phases=len(grades),
                grades=grades, strengths=strengths)


def audit():
    tx = (FW/'experimental/LPM-10A-TX_PN2.26-qc-display.bin').read_bytes()
    rx = (FW/'experimental/APP_LPM-10RX_PN1.24-gain-precision.bin').read_bytes()
    assert hashlib.sha256(tx).hexdigest() == TX_SHA
    assert hashlib.sha256(rx).hexdigest() == RX_SHA
    traces = {}
    for mode, period in ((1,400),(2,12)):
        machine = RealCarrierMachine(tx, mode=mode)
        machine.call(CARRIER_INIT)
        trace = machine.physical_ticks(period*2, IRQ)
        assert trace == [requested_wave(mode,t) for t in range(period*2)]
        assert trace[:period] == trace[period:]
        traces[mode-1] = trace[:period]
    results = []
    for mode in (0,1):
        for tick_us in (100,101,102):
            for pp in (0,12,24,80):
                results.append(evaluate_link(rx, traces[mode], mode, tick_us, pp))
    # Capture actual GPIO selections from the emulator-only Thumb prototype.
    # Keep the shared timer unchanged; this is not a shipped TX waveform.
    # Link voltage, timer arrivals and analog front-end behavior remain modeled.
    prototype = analog_accumulator_experiment(tx)
    proposed = [int(bit) for bit in prototype['observed_trace_first400ticks']]
    assert proposed == [int(((tick+1)*165) % 2000 >= 1000) for tick in range(400)]
    assert sum(proposed) == 200
    assert sum(proposed[t] != proposed[t-1] for t in range(400)) == 66
    fractional = [evaluate_link(rx, proposed, 1, 101, pp) for pp in (0,12,24,80)]
    # The same physical time offsets across the joint 1200-tick repeat period.
    # A prime number of offsets avoids sampling only a handful of aliases of
    # the existing 12-tick waveform. This remains a finite ideal-link corpus.
    offsets = [(i+.213)*1200/127 for i in range(127)]
    dense = {name: [evaluate_link(rx, trace, 1, 101, pp, offsets)
                   for pp in (0,12,24,80)]
             for name, trace in (('published', traces[1]), ('prototype', proposed))}
    return dict(tx_sha256=TX_SHA,rx_raw_sha256=RX_SHA,
        actual_nominal_tx_tick_us=101,rx_tick_us=25.015625,
        windows=len(results)*8,results=results,
        proposed_analog=dict(source='Actual GPIO trace from emulator-only Thumb phase accumulator',
            increment=165, modulus=2000, envelope_duty=0.5,
            trace_sha256=hashlib.sha256(bytes(proposed)).hexdigest(),
            nominal_hz=33/(400*101e-6), windows=len(fractional)*8, results=fractional),
        analog_common_phase_sweep=dict(offsets_ticks=offsets,
            offset_span_ticks=1200, windows=2*4*len(offsets), results=dense),
        limitation='Ideal unfiltered envelope, ADC and timer arrivals modeled; '
                   'alternate tick lengths are probes, not firmware changes or measured clocks.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', type=Path, help='save the complete audit result')
    args = parser.parse_args()
    result = audit()
    report = json.dumps(result, indent=2)+'\n'
    if args.json:
        args.json.write_text(report, encoding='utf-8')
        print(f"PASS: {result['windows']} TX-trace windows + "
              f"{result['proposed_analog']['windows']} emulator-prototype windows + "
              f"{result['analog_common_phase_sweep']['windows']} common-phase windows; saved {args.json}")
    else:
        print(report, end='')
