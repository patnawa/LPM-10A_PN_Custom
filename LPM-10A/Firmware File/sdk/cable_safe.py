"""PN2.33 (release v2.33, owner "2.33 test pass" 2026-09-24): PN2.30 without its Switch-mode changes.

Owner reports 2026-09-24: PN2.30 "every line 1-8 yellow" with a good cable in a switch port
(the partner check's model of a switch port does not match the owner's switch); PN2.31 / 2.32
"ground show connect even my cable no ground" (the grey "not tested" shield line reads as a
connected wire).  So Switch mode decides and draws exactly as PN2.27A did -- connected = a line
in the wire's LAN colour, open = red with the X, the shield included -- until the PN2.30D
readings show how the owner's switch reads.  Kept from PN2.28-2.30: LAN colours and stripes,
the key / busy guard, the RX-unit decisions (median, nearest ladder value, common gain,
plausibility), the panel background after "Testing...".

    python cable_safe.py --write    experimental/LPM-10A-TX_PN2.33-cable-safe.bin
"""
import argparse
import contextlib
import hashlib
import io
from pathlib import Path

from lpm10a.image import PatchError
from lpm10a.thumb import assemble

import cable_check as CC

VERSION = 'PN2.33'
PARENT_SHA256 = 'bfabdc34cf9c8976ece4bdbbac449b5eb4c96a47738bf60684e91221dbeddeb6'   # PN2.30
OUTPUT = Path(__file__).resolve().parent.parent / 'experimental' / 'LPM-10A-TX_PN2.33-cable-safe.bin'


def apply(img):
    img.finalize()
    if hashlib.sha256(bytes(img.data)).hexdigest() != PARENT_SHA256:
        raise PatchError('cable-safe requires the exact finalized PN2.30 parent')
    switch2, colour_values = img.cable_fix['switch2'], img.cable_colours['colour_values']
    if img.read(CC.SWITCH_VALUES, 4) != assemble(CC.SWITCH_VALUES, f'bl {switch2}'):
        raise PatchError('cable-safe: 0x0800CE76 does not call PN2.30 switch2')
    # PN2.28's classify_row is dead code since PN2.30 (classify2 replaced it): the cave is full, reuse it
    at, end = img.cable_check['classify_row'], img.cable_check['post_pass']
    source = f'''
    switch3:                            ; after the stock switch drawing (stock decisions): the values in LAN colours
            movs r0, #0
            b.w  {colour_values}
    '''
    code = assemble(at, source, dict(img.syms))
    if at + len(code) > end:
        raise PatchError('cable-safe: does not fit the dead PN2.28 classify_row')
    img.poke(at, img.read(at, len(code)).hex(), code, 'switch mode: stock decisions, LAN colours')
    img.poke(CC.SWITCH_VALUES, assemble(CC.SWITCH_VALUES, f'bl {switch2}').hex(),
             assemble(CC.SWITCH_VALUES, f'bl {at}'), 'switch: partner check off until device readings')
    for s in (0x08011660, 0x08012E6C):
        img.set_string(s, VERSION)
    img.cable_safe = dict(switch3=at)
    return img


def build_candidate():
    import cable_fix
    return apply(cable_fix.build_candidate()).finalize()


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
        OUTPUT.write_bytes(data)
        OUTPUT.with_name('TX-PN2.33-SHA256SUMS.txt').write_text(f'{digest}  {OUTPUT.name}\n', encoding='ascii')
        print(f'Wrote {OUTPUT}')


if __name__ == '__main__':
    main()
