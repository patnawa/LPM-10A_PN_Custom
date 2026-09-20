"""Compare stored RX images' real audio scheduler/countdown instructions.

This is a synthetic countdown-unit audit, not a physical timing measurement
or device identity readback. ADC, battery, GPIO and interrupt delivery are
mocked. No detector runs; one initially published result is allowed to age.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
FIRMWARE = ROOT / 'LPM-10A' / 'Firmware File'
sys.path.insert(0, str(FIRMWARE / 'rx-sdk'))
from test_rx_robust import _FastControl as Control


def replay(data, version, grade):
    c = Control(data)
    for address, value in ((0x20000048, 0), (0x200000EF, 2),
                           (0x2000005D, grade), (0x20000008, 2)):
        c.w8(address, value)
    c.w16(0x2000006C, 800)
    audible, edges = False, []
    for unit in range(1050):
        if version == 13:
            # Actual PN1.13 audio helper at a multiple of forty TIM5 IRQs.
            # Its full TIM5 integration is covered by the existing tests.
            c.w32(0x20000100, unit * 40)
            c.run(0x0800A9D4)
        for phase in range(5):
            c.run(0x08007724)
            current = c.read(0x40000C40, 2) in (700, 900)
            if current != audible:
                edges.append((unit + phase / 5, current))
                audible = current
        c.run(0x0800A97C)
    widths = [round(b[0]-a[0], 2) for a, b in zip(edges, edges[1:])
              if a[1] and not b[1]]
    gaps = [round(b[0]-a[0], 2) for a, b in zip(edges, edges[1:])
            if not a[1] and b[1]]
    return dict(grade=grade, pulse_units=sorted(set(widths)),
                quiet_units=sorted(set(gaps)), pulse_count=len(widths),
                last_off_units=edges[-1][0] if edges else None,
                final_audible=audible)


def audit():
    stock = ROOT.parent / 'LPM-10A_FNIRSI_originals' / 'APP_LPM-10RX_V3.0.0_260416.bin'
    paths = [stock, *FIRMWARE.glob('APP_LPM-10RX_PN*.bin'),
             *(FIRMWARE / 'experimental').glob('APP_LPM-10RX_PN*.bin')]
    rows = []
    for path in paths:
        match = re.search(r'PN1\.(\d+)', path.name)
        version = int(match.group(1)) if match else -1
        grades = ([0] if version < 3 else [30, 50, 100] if version < 7
                  else [1, 3, 5] if version == 7 else [20, 50, 160]
                  if version == 8 else [1, 20, 50, 160])
        data = path.read_bytes()
        rows.append(dict(image=path.name, version=version,
                         sha256=hashlib.sha256(data).hexdigest(),
                         version_string=data[0x65E4:0x65EA].decode('ascii'),
                         cases=[replay(data, version, grade) for grade in grades]))
    rows.sort(key=lambda row: row['version'])
    assert len(rows) == 15
    assert all(row['version_string'] == '3.0.0\0' for row in rows)
    assert not any(case['final_audible'] for row in rows for case in row['cases'])
    return dict(method='Real Thumb scheduler, TIM1 and PN1.13 audio helper; '
                       'synthetic ticks, no detector refresh; not hardware timing.',
                unit='One TIM1 delivery and five speaker deliveries; '
                     'nominally about 1 ms, not a measured millisecond.',
                images=rows)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    result = audit()
    encoded = json.dumps(result, indent=2) + '\n'
    if args.out:
        args.out.write_text(encoded, encoding='utf-8')
        print(f'{len(result["images"])} images; '
              f'{sum(len(r["cases"]) for r in result["images"])} scheduler cases; '
              f'written to {args.out}')
    else:
        print(encoded)
