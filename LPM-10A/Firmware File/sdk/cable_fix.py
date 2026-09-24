"""PN2.30: PN2.29's LAN colours with a Switch-mode check meant to tolerate centre-tap paths.

Status: owner 2026-09-24 "every line cable test 1-8 show yellow" with a good cable in a switch port, so the
model of a switch port behind this check is still wrong for the owner's switch; PN2.33 (release v2.33)
switches the check off and keeps this module's RX-unit median, single beep and panel background.
Historical stage pn2.30.

Owner report 2026-09-24 on PN2.29 (and PN2.28): with a good cable in the switch every wire is
yellow.  Cause (reproduced in the emulator, and found independently by the code review): PN2.28
called a wire "joined" to every pin reading within m1 + 4 + m1/16 of its lowest reading.  A
switch port's centre taps (Bob-Smith termination) link every pair to the others; when that path
reads within a few counts of the pair winding (62..67 against 60), each wire looked joined to
six pins, no pair looked like a switch pair, and every wire was called a short.

PN2.30 keeps PN2.29 and changes the judgement, not the measurement:
  * a signal row passes when its own pair partner is among its joined pins -- the partner is
    always the lowest path, whatever the centre taps read, so a good cable cannot fail;
  * the far end is a switch when at least two T568 pairs see their partners that way;
  * behind a switch: partner not joined, but something else is = MISWIRE (red); a short between
    pairs cannot be told from the centre taps and is no longer claimed (stock could not either);
  * no switch at the far end (unplugged, or a lone joined pair): a joined wire is a SHORT (yellow);
  * behind a switch, a row whose partner is open is left as measured (the broken wire fails, red);
  * the extra red LED / double beep is given only when the stock routine found no fault;
  * RX-unit rows use the median of the kept readings instead of the trimmed mean, so two loose
    wires leaking below 4000 no longer shift a good row (review P1-B);
  * the start hook leaves the text background at the panel colour (no brown box behind
    "Not connected" / "Result error!!").
Everything else (keys, RX-unit plausibility, colours, readings) is PN2.29's.

    python cable_fix.py --write    experimental/LPM-10A-TX_PN2.30-cable-fix.bin
"""
import argparse
import contextlib
import hashlib
import io
from pathlib import Path

from lpm10a.image import PatchError
from lpm10a.thumb import assemble

import cable_check as CC

VERSION = 'PN2.30'
PARENT_SHA256 = '47cebcb4f884d99a3adf938fa7cd4b6c69e020c672bcda57c64523a8ef96ab44'   # PN2.29
OUTPUT = Path(__file__).resolve().parent.parent / 'experimental' / 'LPM-10A-TX_PN2.30-cable-fix.bin'


def apply(img):
    img.finalize()
    if hashlib.sha256(bytes(img.data)).hexdigest() != PARENT_SHA256:
        raise PatchError('cable-fix requires the exact finalized PN2.29 parent')
    cc, cl = img.cable_check, img.cable_colours
    med, hi = img.cable['med'], img.cable['hi']
    checks = ((CC.SWITCH_VALUES, cc['switch_tail']), (CC.CLASSIFY, cc['classify_row']),
              *((a, cc['start_hook']) for a in CC.FRAME_CALLS))
    for site, target in checks:
        if img.read(site, 4) != assemble(site, f'bl {target}'):
            raise PatchError(f'cable-fix: 0x{site:08X} does not call the PN2.28 code')
    syms = dict(STATUS=CC.STATUS, MAP=CC.MAP, MED=med, HI=hi, FG=CC.FG, BG=CC.BG, XTAB=cc['xtab'])

    start2 = img.emit_code(f'''
    start2:                             ; PN2.28's start hook, then the panel colour back as text background
            push {{r4, lr}}
            bl   {cc['start_hook']}
            ldr  r0, =BG
            movw r1, #{CC.INTERIOR}
            strh r1, [r0]
            pop  {{r4, pc}}
    ''', extra_syms=syms, why='Cable Test: text background = panel after the Testing... button')

    switch2 = img.emit_code(f'''
    switch2:                            ; after the stock switch drawing; r8 = the stock fault flag
            push {{r4, r5, r6, r7, lr}}
            sub  sp, #44                ; [sp..8) args, +8 mask u16[8], +32 fault, +36 switch pairs
            movs r0, #0
            str  r0, [sp, #32]
            movs r4, #0
    row_a:  movw r7, #0xFFFF            ; the row's lowest reading (shield slot left out)
            movs r5, #0
    scan_a: mov  r2, r5
            cmp  r4, r5
            bgt  pin_a
            adds r2, #1
    pin_a:  cmp  r2, #8
            beq  next_a
            lsls r0, r4, #3
            add  r0, r5
            lsls r0, r0, #1
            ldr  r1, =MED
            add  r1, r0
            ldrh r0, [r1]
            cmp  r0, r7
            bhs  next_a
            mov  r7, r0
    next_a: adds r5, #1
            cmp  r5, #8
            blt  scan_a
            movs r3, #0
            movw r0, #{CC.SHORT_MAX}
            cmp  r7, r0
            bhi  store
            lsrs r1, r7, #4
            add  r1, r7
            adds r1, #{CC.JOIN_MARGIN}
            cmp  r1, r0
            bls  lim_ok
            mov  r1, r0
    lim_ok: movs r5, #0
    scan_b: mov  r2, r5
            cmp  r4, r5
            bgt  pin_b
            adds r2, #1
    pin_b:  cmp  r2, #8
            beq  next_b
            lsls r0, r4, #3
            add  r0, r5
            lsls r0, r0, #1
            ldr  r6, =MED
            add  r6, r0
            ldrh r0, [r6]
            cmp  r0, r1
            bhi  next_b
            ldr  r6, =bits
            lsls r0, r2, #1
            add  r6, r0
            ldrh r6, [r6]
            orrs r3, r6
    next_b: adds r5, #1
            cmp  r5, #8
            blt  scan_b
    store:  mov  r0, sp
            adds r0, #8
            lsls r1, r4, #1
            add  r0, r1
            strh r3, [r0]
            adds r4, #1
            cmp  r4, #8
            blt  row_a

            movs r6, #0                 ; pairs whose two rows both see their partner
            movs r4, #0
    pair:   ldr  r0, =pairs
            add  r0, r4
            ldrb r5, [r0]               ; row a (the first of the pair)
            bl   partner_joined
            cmp  r0, #0
            beq  pair_next
            ldr  r0, =partner
            add  r0, r5
            ldrb r5, [r0]               ; row b
            bl   partner_joined
            cmp  r0, #0
            beq  pair_next
            adds r6, #1
    pair_next:
            adds r4, #1
            cmp  r4, #4
            blt  pair
            str  r6, [sp, #36]

            movs r5, #0                 ; classify the rows stock drew as connected
    row_c:  ldr  r0, =STATUS
            add  r0, r5
            ldrb r0, [r0]
            cmp  r0, #2
            bne  next_c
            ldr  r0, [sp, #36]
            cmp  r0, #2
            blt  short                  ; no switch at the far end: a joined wire is a short
            ldr  r0, =partner
            add  r0, r5
            ldrb r0, [r0]
            ldr  r1, =STATUS
            add  r1, r0
            ldrb r1, [r1]
            cmp  r1, #1
            beq  next_c                 ; behind a switch, its partner is open: that wire already fails
            bl   partner_joined
            cmp  r0, #0
            bne  next_c                 ; its own partner: ok
            mov  r0, sp
            adds r0, #8
            lsls r1, r5, #1
            add  r0, r1
            ldrh r0, [r0]
            cmp  r0, #0
            beq  short                  ; only the shield: a short to the shield
            movs r1, #3                 ; something else, not its partner: wrong pair
            movw r2, #{CC.RED}
            b    mark
    short:  movs r1, #0
            movw r2, #{CC.YELLOW}
    mark:   ldr  r0, =STATUS
            add  r0, r5
            strb r1, [r0]
            ldr  r0, =FG
            strh r2, [r0]
            movs r0, #1
            str  r0, [sp, #32]
            movs r1, #24
            muls r1, r5, r1
            adds r1, #68
            mov  r3, r1
            movs r0, #25
            movs r2, #207
            bl   {CC.LINE}
    next_c: adds r5, #1
            cmp  r5, #8
            blt  row_c

            ldr  r0, =STATUS            ; the shield row, as PN2.28
            ldrb r1, [r0, #8]
            cmp  r1, #2
            bne  g_open
            movs r1, #0
            strb r1, [r0, #8]
            movs r0, #1
            str  r0, [sp, #32]
            movw r2, #{CC.YELLOW}
            b    g_line
    g_open: cmp  r1, #1
            bne  fault
            movs r1, #5
            strb r1, [r0, #8]
            movw r0, #{CC.INTERIOR}
            str  r0, [sp]
            movs r0, #112
            movw r1, #256
            movs r2, #120
            movw r3, #264
            bl   {CC.SHAPE}
            movw r2, #{CC.GREY}
    g_line: ldr  r0, =FG
            strh r2, [r0]
            movs r0, #25
            movw r1, #260
            movs r2, #207
            mov  r3, r1
            bl   {CC.LINE}
    fault:  ldr  r0, [sp, #32]
            cmp  r0, #0
            beq  done
            mov  r0, r8                 ; the stock routine already beeped and lit red
            cmp  r0, #0
            bne  done
            movs r0, #2
            bl   {CC.BEEP}
            movs r0, #1
            bl   {CC.RGB_LED}
    done:   movs r0, #0
            bl   {cl['colour_values']}
            add  sp, #44
            pop  {{r4, r5, r6, r7, pc}}

    partner_joined:                     ; r5 = row -> r0 = mask(row) & bit(partner(row)); uses the caller's frame + 4
            ldr  r0, =expected
            lsls r1, r5, #1
            add  r0, r1
            ldrh r0, [r0]
            mov  r2, sp                 ; leaf: sp is switch2's, masks at sp + 8
            adds r2, #8
            add  r2, r1
            ldrh r2, [r2]
            ands r0, r2
            bx   lr
            .align 2
    bits:     .short 0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x100
    expected: .short 0x02, 0x01, 0x20, 0x10, 0x08, 0x04, 0x80, 0x40
    partner:  .byte 1, 0, 5, 4, 3, 2, 7, 6
    pairs:    .byte 0, 2, 3, 6
    ''', extra_syms=syms, why='Cable Test switch mode: pass whenever the pair partner is joined')

    classify2 = img.emit_code(f'''
    classify2:                          ; r4 = driven pin: median of the kept slots, then PN2.28's rules
            push {{r4, r5, r6, r7, lr}}
            sub  sp, #20                ; [sp..16) sorted kept medians u16[8]
            movs r6, #0
            movs r5, #0
    slot:   lsls r0, r4, #3
            add  r0, r5
            lsls r0, r0, #1
            ldr  r1, =HI
            add  r1, r0
            ldrh r1, [r1]
            movw r2, #{CC.RAIL_MIN}
            cmp  r1, r2
            bhi  next
            ldr  r1, =MED
            add  r1, r0
            ldrh r0, [r1]
            movw r2, #{CC.SHORT_MAX}
            cmp  r0, r2
            bls  next
            mov  r2, r6                 ; insertion into the sorted list
    ins:    cmp  r2, #0
            beq  put_v
            subs r3, r2, #1
            lsls r3, r3, #1
            mov  r7, sp
            add  r7, r3
            ldrh r1, [r7]
            cmp  r1, r0
            bls  put_v
            strh r1, [r7, #2]
            subs r2, #1
            b    ins
    put_v:  lsls r3, r2, #1
            mov  r7, sp
            add  r7, r3
            strh r0, [r7]
            adds r6, #1
    next:   adds r5, #1
            cmp  r5, #8
            blt  slot
            movs r0, #4
            cmp  r6, #0
            beq  put
            lsrs r1, r6, #1             ; median: middle one, or the mean of the middle two
            lsls r2, r1, #1
            mov  r7, sp
            add  r7, r2
            ldrh r7, [r7]
            lsls r0, r6, #31
            bne  have_x                 ; odd count
            mov  r0, sp
            add  r0, r2
            subs r0, #2
            ldrh r0, [r0]
            add  r7, r0
            lsrs r7, r7, #1
    have_x: ldr  r0, =XTAB
            lsls r1, r4, #1
            add  r0, r1
            strh r7, [r0]
            mov  r0, r7
            bl   {cc['near_idx']}
            movs r1, #2
            cmp  r0, r4
            beq  put_s
            ldr  r2, =MAP
            lsls r3, r4, #1
            add  r2, r3
            strh r0, [r2]
            movs r1, #3
    put_s:  mov  r0, r1
    put:    ldr  r1, =STATUS
            add  r1, r4
            strb r0, [r1]
            add  sp, #20
            pop  {{r4, r5, r6, r7, pc}}
    ''', extra_syms=syms, why='Cable Test RX unit: median of the non-floating slots')

    img.poke(CC.SWITCH_VALUES, assemble(CC.SWITCH_VALUES, f"bl {cc['switch_tail']}").hex(),
             assemble(CC.SWITCH_VALUES, f'bl {switch2}'), 'switch: partner check that tolerates centre taps')
    img.poke(CC.CLASSIFY, assemble(CC.CLASSIFY, f"bl {cc['classify_row']}").hex(),
             assemble(CC.CLASSIFY, f'bl {classify2}'), 'RX unit: median of the kept slots')
    for a in CC.FRAME_CALLS:
        img.poke(a, assemble(a, f"bl {cc['start_hook']}").hex(), assemble(a, f'bl {start2}'),
                 'test start: panel background restored')
    for s in (0x08011660, 0x08012E6C):
        img.set_string(s, VERSION)
    img.cable_fix = dict(start2=start2, switch2=switch2, classify2=classify2)
    return img


def build_candidate():
    import cable_colours
    return apply(cable_colours.build_candidate()).finalize()


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
        OUTPUT.with_name('TX-PN2.30-SHA256SUMS.txt').write_text(f'{digest}  {OUTPUT.name}\n', encoding='ascii')
        print(f'Wrote {OUTPUT}')


if __name__ == '__main__':
    main()
