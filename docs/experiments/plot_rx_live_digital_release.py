"""Plot existing RX SRAM evidence offline, using stdlib SVG and optional PyMuPDF.

No hardware access. Sample positions use each read window's midpoint; horizontal
whiskers show its host-time bounds. Connecting lines only guide the eye.
"""
import argparse
import html
import json
from pathlib import Path
import struct

from rx_live_digital_release_audit import analyze


def plot(capture, destination):
    evidence = analyze(capture)
    rows = [json.loads(line) for line in capture.read_bytes().splitlines()]
    release = evidence['final_release']
    reference = release['last_recent_refresh_bracket_s']
    zero = sum(reference) / 2
    delay = release['last_refresh_to_last_beep_clear_bracket_s']
    assert release['new_pulses_after_final_refresh'] == 8
    recent = [struct.unpack_from('<H', bytes.fromhex(r['state_hex']), 38)[0]
              for r in rows]
    beep = [bytes.fromhex(r['counters_hex'])[16] for r in rows]
    assert max(recent) == 800 and max(beep) == 50

    width, height = 1400, 900
    left, right = 110, 1335
    xmin, xmax = -.3, 1.2
    panels = [(170, 385, 860), (480, 695, 75)]
    ink, muted, grid = '#182b3a', '#526372', '#dce3e8'
    teal, blue, amber = '#007d7a', '#2459aa', '#a85a00'
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
           '<title>Measured RX Digital release after the last accepted-signal refresh</title>',
           '<desc>Two panels show RECENT and BEEP countdown samples decoded from live SRAM. Eight new BEEP activations follow the last RECENT refresh. Final BEEP clearing follows that refresh by 0.816 to 0.865 seconds. Zero is the estimated last refresh, not the TX Pause event. Reads are sequential and non-atomic.</desc>',
           '<rect width="1400" height="900" fill="white"/>',
           '<g font-family="Helvetica">']

    def add(element):
        svg.append(element)

    def text(x, y, value, size=17, fill=ink, anchor='start', weight='normal'):
        add(f'<text x="{x:.2f}" y="{y:.2f}" font-size="{size}" fill="{fill}" text-anchor="{anchor}" font-weight="{weight}">{html.escape(value)}</text>')

    def line(x1, y1, x2, y2, stroke=grid, sw=1, extra=''):
        add(f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" stroke="{stroke}" stroke-width="{sw}" {extra}/>')

    def x(t):
        return left + (t-xmin)/(xmax-xmin)*(right-left)

    def y(value, panel):
        top, bottom, maximum = panels[panel]
        return bottom - value/maximum*(bottom-top)

    text(55, 44, 'Digital release: eight further BEEP activations', 30, weight='bold')
    text(55, 76, 'Measured live SRAM  |  20 September 2026  |  Median sample spacing: 17.054 ms', 18, muted)
    line(57, 106, 90, 106, teal, 1.8)
    add('<circle cx="73.5" cy="106" r="3" fill="#007d7a"/>')
    text(102, 111, 'Sample + host read window; connecting lines guide the eye', 15, muted)
    add('<rect x="780" y="96" width="20" height="16" fill="#e5e9ed"/>')
    text(811, 110, 'Last-refresh timing bracket', 15, muted)
    add('<rect x="1060" y="96" width="20" height="16" fill="#ffe2b4"/>')
    text(1091, 110, 'Final-clear interval', 15, muted)

    labels = ['A   RECENT: accepted-signal countdown', 'B   BEEP: sound countdown']
    for panel, (top, bottom, maximum) in enumerate(panels):
        text(left, top-25, labels[panel], 20, weight='bold')
        xref1, xref2 = [x(t-zero) for t in reference]
        add(f'<rect x="{xref1:.2f}" y="{top}" width="{xref2-xref1:.2f}" height="{bottom-top}" fill="#e5e9ed"/>')
        add(f'<rect x="{x(delay[0]):.2f}" y="{top}" width="{x(delay[1])-x(delay[0]):.2f}" height="{bottom-top}" fill="#ffe2b4"/>')
        ticks = [0, 200, 400, 600, 800] if panel == 0 else [0, 10, 20, 30, 40, 50]
        for value in ticks:
            line(left, y(value, panel), right, y(value, panel))
            text(left-14, y(value, panel)+6, str(value), 16, muted, 'end')
        for t in [-.2, 0, .2, .4, .6, .8, 1, 1.2]:
            line(x(t), top, x(t), bottom, grid, .8)
            if panel == 1:
                text(x(t), bottom+29, f'{t:.1f}', 17, muted, 'middle')
        line(x(0), top, x(0), bottom, '#7c8791', 1.4, 'stroke-dasharray="5 5"')
        line(left, bottom, right, bottom, '#82919d', 1.2)
        line(left, top, left, bottom, '#82919d', 1.2)
        text(60, (top+bottom)/2, 'Ticks', 16, muted, 'end')

        values = recent if panel == 0 else beep
        colour = teal if panel == 0 else blue
        samples = []
        for i, row in enumerate(rows):
            a, b = ((row['begin_s'], row['state_end_s']) if panel == 0
                    else (row['state_end_s'], row['end_s']))
            midpoint = (a+b)/2-zero
            if xmin <= midpoint <= xmax:
                samples.append((i, midpoint, a-zero, b-zero, values[i]))
        points = ' '.join(f'{x(t):.2f},{y(v,panel):.2f}' for _, t, _, _, v in samples)
        add(f'<polyline points="{points}" fill="none" stroke="{colour}" stroke-width="1.4" opacity="0.6"/>')
        for _, t, a, b, value in samples:
            yy = y(value, panel)
            line(x(a), yy, x(b), yy, colour, 1.5)
            add(f'<circle cx="{x(t):.2f}" cy="{yy:.2f}" r="2.7" fill="{colour}"/>')

    text(x(.945), y(680, 0), 'Last BEEP clear', 19, amber, 'middle', 'bold')
    text(x(.945), y(555, 0), '0.816–0.865 s', 24, amber, 'middle', 'bold')
    text(x(.945), y(450, 0), 'after the last refresh', 16, amber, 'middle')
    text(x(.945), y(340, 0), 'Conservative bracket includes', 14, muted, 'middle')
    text(x(.945), y(250, 0), 'uncertainty in both events.', 14, muted, 'middle')

    text(x(.415), y(68, 1), '8 new zero-to-positive BEEP transitions', 17, blue, 'middle', 'bold')
    for number, pulse in enumerate(release['tail_pulses'], 1):
        index = pulse['first_row']
        row = rows[index]
        t = (row['state_end_s']+row['end_s'])/2-zero
        value = beep[index]
        line(x(t), y(55, 1), x(t), y(value, 1)-6, blue, .9)
        text(x(t), y(58, 1), str(number), 16, blue, 'middle', 'bold')
    text(x(1.025), y(20, 1), 'Remains zero', 17, muted, 'middle')
    text((left+right)/2, 759, 'Time relative to estimated last accepted-signal refresh (seconds)', 20, ink, 'middle')
    text(55, 808, 'Zero = midpoint of the last RECENT-refresh bracket. This is not a timestamp of the TX Pause button.', 17, ink)
    text(55, 835, 'Sequential live reads are non-atomic. Whiskers show individual read windows; the shared zero-time uncertainty is shaded.', 16, muted)
    text(55, 862, 'BEEP is a software countdown, not a direct speaker/PWM measurement. Source: digital-pause-20260920-221932.jsonl', 16, muted)
    add('</g></svg>')
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text('\n'.join(svg)+'\n', encoding='utf-8')
    metadata = {'capture_sha256': evidence['source_sha256'],
                'reference': 'midpoint of last accepted-signal RECENT refresh bracket, not TX Pause',
                'reference_midpoint_s': zero,
                'reference_bracket_s': reference,
                'final_clear_delay_bracket_s': delay,
                'new_beep_activations': 8,
                'read_windows': 'RECENT: begin_s..state_end_s; BEEP: state_end_s..end_s',
                'window_relative_s': [xmin, xmax],
                'svg': str(destination)}
    try:
        import pymupdf
    except ImportError:
        metadata['png'] = None
    else:
        with pymupdf.open(str(destination)) as document:
            document[0].get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5)).save(str(destination.with_suffix('.png')))
        metadata['png'] = str(destination.with_suffix('.png'))
    print(json.dumps(metadata, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    plot(args.capture, args.out)
