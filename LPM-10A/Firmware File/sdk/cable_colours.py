"""PN2.29: the Cable Test draws every wire in its LAN cable colour (T568B).

Status: owner 2026-09-24 "every color right", but PN2.28's Switch-mode check underneath still made a good
cable yellow; the colours ship in PN2.33 (release v2.33).  Historical stage pn2.29.

Owner request 2026-09-24 after testing PN2.28: "color per line base on lan cable".

    pin 1 white-orange   pin 2 orange   pin 3 white-green   pin 4 blue
    pin 5 white-blue     pin 6 green    pin 7 white-brown   pin 8 brown     G silver (drain)

Stock drew the nine wires from a u16 colour table at 0x0801E2CC (green, cyan, dark green,
magenta, orange, grey, orange, blue, white) that nothing but the Cable Test reads: the two
straight-wire draws (far end 0x0800C74A, switch 0x0800CC3E), the crossed-wire draw 0x0800CA30
and the PN2.21 / PN2.28 per-wire readings.  PN2.29 writes the T568B colours into that table,
and the white-striped wires (pins 1, 3, 5, 7) get white dashes over their colour: 5 px every
12 px, from x 29 to x 170 (the readings start at x 171), along straight wires and, in RX-unit
mode, along the crossed diagonals too.  Result colours are PN2.28's and win over the cable
colour: red = open / wrong pair (switch), yellow = short, grey = shield not tested, and those
rows get no stripes.

Mechanics: PN2.28's two value calls (inside far_tail and switch_tail, after every wire is drawn)
become `bl colour_values`, which draws the stripes and then runs PN2.28's `values` with the
same mode argument.  Nothing else changes; the decisions are PN2.28's byte for byte.

    python cable_colours.py            dry build
    python cable_colours.py --write    experimental/LPM-10A-TX_PN2.29-cable-colours.bin
"""
import argparse
import contextlib
import hashlib
import io
import struct
from pathlib import Path

from lpm10a.image import PatchError
from lpm10a.thumb import assemble


VERSION = 'PN2.29'
PARENT_SHA256 = '03b34b991664731c582b1247b25b29830a8be242f8ddad6be394d901ea9fcc9a'   # PN2.28, owner-tested 2026-09-24
OUTPUT = (Path(__file__).resolve().parent.parent / 'experimental' / 'LPM-10A-TX_PN2.29-cable-colours.bin')

COLOURS = 0x0801E2CC
STOCK_COLOURS = (0x07E0, 0x07FF, 0x0400, 0xF81F, 0xF621, 0xC618, 0xFB80, 0x0C7F, 0xFFFF)
ORANGE, GREEN, BLUE, BROWN, SILVER, WHITE = 0xFC00, 0x07E0, 0x041F, 0xA280, 0xC618, 0xFFFF
T568B = (ORANGE, ORANGE, GREEN, BLUE, BLUE, GREEN, BROWN, BROWN, SILVER)
STRIPED = (0, 2, 4, 6)                      # pins 1, 3, 5, 7: white-orange, white-green, white-blue, white-brown
X0, X1, DASH, PITCH = 29, 170, 4, 12        # dashes x .. x+4, every 12 px, up to the readings (x >= 171)
STATUS, MAP, FG = 0x2000023E, 0x20000248, 0x200001AC
LINE = 0x08016ADC


def apply(img):
    img.finalize()
    if hashlib.sha256(bytes(img.data)).hexdigest() != PARENT_SHA256:
        raise PatchError('cable-colours requires the exact finalized PN2.28 parent')
    cc = img.cable_check
    values, far_tail, switch_tail = cc['values'], cc['far_tail'], cc['switch_tail']
    stock = struct.pack('<9H', *STOCK_COLOURS)
    if img.read(COLOURS, 18) != stock:
        raise PatchError('cable-colours: the wire colour table is not stock')
    calls = []
    for start, end in ((far_tail, far_tail + 12), (switch_tail, cc['classify_row'])):
        for a in range(start, end, 2):
            if img.read(a, 4) == assemble(a, f'bl {values}'):
                calls.append(a)
    if len(calls) != 2:
        raise PatchError(f'cable-colours: expected the two PN2.28 value calls, found {len(calls)}')

    stripes = img.emit_code(f'''
    stripes:                            ; r0 = mode (0 switch, 1 RX unit); white dashes on pins 1, 3, 5, 7
            push {{r4, r5, r6, r7, lr}}
            sub  sp, #20                ; [sp] mode, [sp+4] y0, [sp+8] y1 - y0, [sp+12] dash start y
            str  r0, [sp]
            movs r4, #0
    row:    ldr  r0, =STATUS
            add  r0, r4
            ldrb r0, [r0]
            movs r1, #24
            muls r1, r4, r1
            adds r1, #68
            str  r1, [sp, #4]
            movs r2, #0
            str  r2, [sp, #8]
            cmp  r0, #2
            beq  draw
            cmp  r0, #3                 ; crossed: only in RX-unit mode (in switch mode it is a red fault)
            bne  next
            ldr  r0, [sp]
            cmp  r0, #0
            beq  next
            ldr  r0, =MAP
            lsls r2, r4, #1
            add  r0, r2
            ldrh r0, [r0]
            movs r2, #24
            muls r2, r0, r2
            adds r2, #68
            subs r2, r2, r1             ; y1 - y0 (signed)
            str  r2, [sp, #8]
    draw:   ldr  r0, =FG
            movw r1, #{WHITE}
            strh r1, [r0]
            movs r5, #{X0}
    dash:   mov  r0, r5
            bl   y_at
            str  r0, [sp, #12]
            adds r0, r5, #{DASH}
            bl   y_at
            mov  r3, r0
            ldr  r1, [sp, #12]
            mov  r0, r5
            adds r2, r5, #{DASH}
            bl   {LINE}
            adds r5, #{PITCH}
            cmp  r5, #{X1}
            blo  dash
    next:   adds r4, #2
            cmp  r4, #8
            blo  row
            add  sp, #20
            pop  {{r4, r5, r6, r7, pc}}
    y_at:   subs r0, #25                ; r0 = x -> y0 + (y1 - y0) * (x - 25) / 182 (leaf; the frame is sp + 0)
            ldr  r1, [sp, #8]
            muls r0, r1, r0
            movs r1, #182
            sdiv r0, r0, r1
            ldr  r1, [sp, #4]
            adds r0, r0, r1
            bx   lr
    ''', extra_syms=dict(STATUS=STATUS, MAP=MAP, FG=FG), why='Cable Test: white dashes on the white-striped wires')

    colour_values = img.emit_code(f'''
    colour_values:                      ; r0 = mode: stripes, then PN2.28's values with the same mode
            push {{r4, lr}}
            mov  r4, r0
            bl   {stripes}
            mov  r0, r4
            bl   {values}
            pop  {{r4, pc}}
    ''', why='Cable Test: LAN colours, then the readings')

    img.poke(COLOURS, stock.hex(), struct.pack('<9H', *T568B), 'wire colours: T568B')
    for a in calls:
        img.poke(a, assemble(a, f'bl {values}').hex(), assemble(a, f'bl {colour_values}'),
                 'stripes before the readings')
    for site in (0x08011660, 0x08012E6C):
        img.set_string(site, VERSION)
    img.cable_colours = dict(stripes=stripes, colour_values=colour_values, calls=tuple(calls))
    return img


def build_candidate():
    import cable_check
    return apply(cable_check.build_candidate()).finalize()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    with contextlib.redirect_stdout(io.StringIO()):
        img = build_candidate()
    data = bytes(img.data)
    digest = hashlib.sha256(data).hexdigest()
    print(f'{VERSION}: {len(data)} bytes; SHA256 {digest}')
    if args.write:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_bytes(data)
        OUTPUT.with_name('TX-PN2.29-SHA256SUMS.txt').write_text(f'{digest}  {OUTPUT.name}\n', encoding='ascii')
        print(f'Wrote {OUTPUT}')
    else:
        print('Dry build; use --write for the candidate file. Not device-tested.')


if __name__ == '__main__':
    main()
