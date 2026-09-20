"""Pinned PN2.14 Pause control/GPIO audit; RTOS latency and board RF are not modeled."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
SDK = ROOT / 'LPM-10A/Firmware File/sdk'
sys.path.insert(0, str(SDK))
from test_scan_recovery import RecoveryMachine
from test_scan_hardware import CARRIER_INIT, BACK, TIM1_EXPECTED
from verify_scan import SCAN, DIGITAL, IRQ

EXPECTED = 'a7402de6f18e39df55bbe53f5641efd5135f0de4d81f9407515cf9d8710c5527'


def main():
    data = (SDK.parent / 'experimental/LPM-10A-TX_PN2.14-tone-recovery.bin').read_bytes()
    assert hashlib.sha256(data).hexdigest() == EXPECTED
    rows = []
    for mode, phases in ((1, 800), (2, 12)):
        counts = []
        initial_states = set()
        for phase in range(phases):
            m = RecoveryMachine(data, mode, 1, 5)
            m.call(CARRIER_INIT)
            if mode == 1:
                m.w32(DIGITAL, phase)
                m.physical_ticks(1, IRQ)
            else:
                m.physical_ticks(phase + 1, IRQ)
            initial_states.add(m.pin_modes())
            before = m.instructions
            m.call(BACK)
            counts.append(m.instructions - before)
            assert m.r8(SCAN) == 0 and m.pin_modes() == (3, 3)
            cursor = bytes(m.uc.mem_read(DIGITAL, 10))
            requests = len(m.requests)
            assert m.physical_ticks(32, IRQ) == [0] * 32
            assert bytes(m.uc.mem_read(DIGITAL, 10)) == cursor
            assert len(m.requests) == requests
            assert m.timer_configuration() == TIM1_EXPECTED
        rows.append({'mode': mode, 'phases': phases,
                     'initial_pin_states': sorted(initial_states),
                     'pause_instructions_range': [min(counts), max(counts)]})
    result = {'sha256': EXPECTED, 'passed': True, 'cases': sum(r['phases'] for r in rows),
              'scope': 'ARM Pause handler, GPIO registers, and 32 subsequent TIM2 IRQs per phase',
              'limits': 'RTOS services are stubbed; instruction counts are not elapsed time. No jack waveform or analogue decay measurement.',
              'results': rows}
    rendered = json.dumps(result, indent=2)
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(rendered + '\n', encoding='utf-8')
    print(rendered)


if __name__ == '__main__':
    main()
