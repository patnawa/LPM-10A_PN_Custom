"""PN2.30D diagnostic: Switch mode prints each wire's two lowest readings and the pins they reach.

Owner reports 2026-09-24 on PN2.28-2.30: with a good cable in a switch port every wire is yellow
(the pair-partner check called a wire "joined" to every pin reading within m1 + 4 + m1/16 of its
lowest reading; the emulator's model put the centre-tap paths between pairs well above the pair
winding, the owner's switch evidently does not).  This build is PN2.30 (default) or PN2.29
(--base pn2.29) with the Switch-mode readings at the wire ends replaced by

    "2  60 5  63"   lowest reading 60 at pin 2, next lowest 63 at pin 5

so one photo of a good cable in the switch shows the margin a partner check would need.  RX-unit
mode, all decisions and colours are the base build's.  Not a release: flash it, photograph, flash
the release back.  Not a profile; it is the diagnostic for release v2.33 (PN2.33 = PN2.30 with
the partner check off, so PN2.30D's Switch-mode readings are what PN2.33 measures).

    python cable_diag2.py --write                 experimental/LPM-10A-TX_PN2.30D-diag.bin
    python cable_diag2.py --base pn2.29 --write   experimental/LPM-10A-TX_PN2.29D-diag.bin
"""
import argparse
import contextlib
import hashlib
import io
from pathlib import Path

from lpm10a.image import PatchError
from lpm10a.thumb import assemble

PARENTS = {'47cebcb4f884d99a3adf938fa7cd4b6c69e020c672bcda57c64523a8ef96ab44': 'PN2.29D',   # PN2.29
           'bfabdc34cf9c8976ece4bdbbac449b5eb4c96a47738bf60684e91221dbeddeb6': 'PN2.30D'}   # PN2.30
EXP = Path(__file__).resolve().parent.parent / 'experimental'
FG, BG = 0x200001AC, 0x200001AE


def apply(img):
    img.finalize()
    version = PARENTS.get(hashlib.sha256(bytes(img.data)).hexdigest())
    if version is None:
        raise PatchError('cable-diag2 requires the exact finalized PN2.29 or PN2.30 parent')
    med, release = img.cable['med'], img.cable['release']
    colour_values, values = img.cable_colours['colour_values'], img.cable_check['values']
    site = colour_values + 10                     # push; mov r4,r0; bl stripes; mov r0,r4; -> bl values
    if img.read(site, 4) != assemble(site, f'bl {values}'):
        raise PatchError('cable-diag2: colour_values does not call values where expected')
    source = f'''
    diag:                               ; r0 = mode; RX unit -> PN2.28 values, switch -> two lowest per row
            cmp  r0, #0
            beq  sw
            b.w  {values}
    sw:     push {{r4, r5, r6, r7, lr}}
            sub  sp, #36                ; [sp..8) args, [sp+8..20) text, [sp+20] v2, [sp+24] slot2
            bl   {release}
            ldr  r0, =BG
            movw r1, #0x2105
            strh r1, [r0]
            ldr  r0, =FG
            movw r1, #0xFFFF
            strh r1, [r0]
            movs r4, #0
    row:    lsls r5, r4, #3
            movs r6, #0                 ; slot of the lowest
            movw r7, #0xFFFF            ; lowest
            movw r0, #0xFFFF
            str  r0, [sp, #20]
            movs r0, #0
            str  r0, [sp, #24]
            movs r1, #0
    scan:   adds r2, r5, r1
            lsls r2, r2, #1
            ldr  r3, =MED
            add  r3, r2
            ldrh r3, [r3]
            cmp  r3, r7
            bhs  second
            str  r7, [sp, #20]
            str  r6, [sp, #24]
            mov  r7, r3
            mov  r6, r1
            b    scan_next
    second: ldr  r0, [sp, #20]
            cmp  r3, r0
            bhs  scan_next
            str  r3, [sp, #20]
            str  r1, [sp, #24]
    scan_next:
            adds r1, #1
            cmp  r1, #8
            blt  scan
            ldr  r1, =fmt
            mov  r2, r7
            ldr  r3, [sp, #20]
            mov  r0, sp
            adds r0, #8
            bl   sprintf
            mov  r0, r6
            bl   letter
            mov  r1, sp
            strb r0, [r1, #8]
            ldr  r0, [sp, #24]
            bl   letter
            mov  r1, sp
            strb r0, [r1, #14]
            movs r0, #12
            str  r0, [sp]
            mov  r0, sp
            adds r0, #8
            str  r0, [sp, #4]
            movs r1, #24
            muls r1, r4, r1
            adds r1, #62
            movs r0, #141
            movs r2, #66
            movs r3, #12
            bl   gui_blit
            adds r4, #1
            cmp  r4, #9
            blt  row
            add  sp, #36
            pop  {{r4, r5, r6, r7, pc}}
    letter: cmp  r4, r0                 ; r0 = slot, r4 = row -> '1'..'8' or 'G'
            bgt  named
            adds r0, #1
    named:  cmp  r0, #8
            beq  g
            adds r0, #0x31
            bx   lr
    g:      movs r0, #0x47
            bx   lr
    fmt:    .asciz "?%4d ?%4d"
    '''
    syms = dict(img.syms, MED=med, FG=FG, BG=BG)
    if version == 'PN2.30D':
        # PN2.28's switch_tail is dead code in PN2.30 (0x0800CE76 calls switch2): reuse it, the cave is full
        diag = img.cable_check['switch_tail']
        code = assemble(diag, source, syms)
        if diag + len(code) > img.cable_check['classify_row']:
            raise PatchError('cable-diag2: does not fit the dead PN2.28 switch_tail')
        img.poke(diag, img.read(diag, len(code)).hex(), code, 'diag: two lowest readings per row (dead PN2.28 code)')
    else:
        diag = img.emit_code(source, extra_syms=dict(MED=med, FG=FG, BG=BG), why='diag: two lowest readings per row')
    img.poke(site, assemble(site, f'bl {values}').hex(), assemble(site, f'bl {diag}'), 'diag readings')
    for s in (0x08011660, 0x08012E6C):
        img.set_string(s, version)
    img.diag_version = version
    img.cable_diag2 = dict(diag=diag)
    return img


def build_candidate(base='pn2.30'):
    import cable_colours, cable_fix
    return apply((cable_fix if base == 'pn2.30' else cable_colours).build_candidate()).finalize()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    parser.add_argument('--base', default='pn2.30', choices=('pn2.29', 'pn2.30'))
    args = parser.parse_args()
    with contextlib.redirect_stdout(io.StringIO()):
        img = build_candidate(args.base)
    VERSION = img.diag_version
    OUTPUT = EXP / f'LPM-10A-TX_{VERSION}-diag.bin'
    data = bytes(img.data)
    digest = hashlib.sha256(data).hexdigest()
    print(f'{VERSION}: {len(data)} bytes; SHA256 {digest}')
    if args.write:
        OUTPUT.write_bytes(data)
        OUTPUT.with_name(f'TX-{VERSION}-SHA256SUMS.txt').write_text(f'{digest}  {OUTPUT.name}\n', encoding='ascii')
        print(f'Wrote {OUTPUT}')


if __name__ == '__main__':
    main()
