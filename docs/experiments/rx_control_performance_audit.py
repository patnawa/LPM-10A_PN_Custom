"""Bounded RX control/ADC audit; instruction counts are not hardware cycles.

Run from the repository root. Uses the exact delivered PN1.10 image and the
existing completion model. The analogue function of PB12..PB14 is unknown.
"""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
SDK = ROOT / 'LPM-10A/Firmware File/rx-sdk'
sys.path.insert(0, str(SDK))

from unicorn.arm_const import UC_ARM_REG_PRIMASK
import test_roadmap
import test_rx_sync
from sampling_fixes import PUBLISH_GATE
from test_rx_followup import GATE_STATE
from verify_control import Control, MODE
from verify_digital import ACTIVE, GATE


class MaskControl(Control):
    def __init__(self, data):
        self.steps = self.masked = self.run_masked = self.max_masked = 0
        super().__init__(data)

    def hook(self, uc, addr, size, unused):
        self.steps += 1
        if uc.reg_read(UC_ARM_REG_PRIMASK):
            self.masked += 1
            self.run_masked += 1
            self.max_masked = max(self.max_masked, self.run_masked)
        else:
            self.run_masked = 0
        super().hook(uc, addr, size, unused)


def run():
    data = (SDK.parent / 'experimental/APP_LPM-10RX_PN1.10-sync.bin').read_bytes()
    assert hashlib.sha256(data).hexdigest() == '6570f521054d77ee97c1a0e37e5a9da0a975d41d452e5f14e63aadb68a9f6e21'
    adc = test_roadmap.Roadmap('runTest')
    adc.data = data
    original = test_roadmap.Control
    results = []
    try:
        test_roadmap.Control = MaskControl
        for channel in (1, 2, 3, 7):
            for delay in (0, 100, 500, 2000, None):
                c, model = adc.adc(channel, delay or 0, complete=delay is not None)
                results.append(dict(channel=channel, simulated_completion_delay_in_instructions=delay,
                                    instructions=c.steps, max_contiguous_masked=c.max_masked,
                                    reset_requested=bool(model['resets'])))
                assert bool(model['resets']) == (delay is None)
    finally:
        test_roadmap.Control = original

    audit = test_rx_sync.Sync('runTest')
    audit.data = data
    mapping = []
    for level in range(8):
        c = audit.cpu()
        audit.execute(c, 0x0800A4FC, level)
        mapping.append(dict(level=level, pb12_to_pb14=[c.gpio[(0x40010C00, 1 << bit)]
                                                     for bit in (12, 13, 14)]))
    assert mapping[0]['pb12_to_pb14'] == mapping[3]['pb12_to_pb14']

    gates = []
    for mode in (0, 1):
        for old, new in ((1, 2), (579, 580), (580, 1160), (1160, 1740), (1740, 579)):
            c = audit.cpu()
            c.w8(MODE, mode)
            c.w16(GATE, old)
            c.w16(GATE+2, old//580)
            c.w8(ACTIVE, 1)
            result = audit.execute(c, PUBLISH_GATE, new)
            threshold = 2 if mode == 0 else 580
            crossed = (old >= threshold) != (new >= threshold)
            assert c.read(GATE_STATE) == (0 if crossed else 2)
            gates.append(dict(mode=mode, previous_pa2=old, next_pa2=new,
                              returned_output_code=result,
                              invalidated=c.read(GATE_STATE) == 0))
    return dict(adc=results, output_pin_mapping=mapping, gate_changes=gates,
                interpretation='Output-code changes within an open gate do not invalidate a window. '
                'Impact on amplitude is unknown until the physical role of these pins is identified. '
                'ADC completion delays are injected instruction counts, not measured conversion times.')


if __name__ == '__main__':
    print(json.dumps(run(), indent=2))
