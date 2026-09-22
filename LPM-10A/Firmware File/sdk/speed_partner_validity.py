"""SPEED correction: failed ability-register reads display Unknown.

The vendor MDIO reader returns the sampled bus word, without an error flag.
Port FLASH already rejects all-ones reads. PN 2.17's Switch row instead treats
0xFFFF as every speed advertised; this also affects the released PN 2.23 image.

Intercept only the Switch-value draw call. If either cached partner register is
0xFFFF, clear its cell and show Unknown. Valid zero ability words still mean
No autoneg. The existing result hook retains its retry, Error!! and return-code
handling. The About and boot strings identify this candidate as PN2.23S. No
measurement, PHY write or historical profile changes.

    python build.py --profile pn2.23 --with speed-partner-validity --out candidate.bin --write

The standalone PN2.23S build remains reproducible. This correction is included
in the default PN2.26 release; the owner reported all functions passing on the
device on 2026-09-22. Synthetic all-ones reads are also checked in CPU tests.
"""
from lpm10a.image import PatchError
from lpm10a.thumb import assemble

import speed_partner as SP


PATCH_ID = 'speed-partner-validity'
VERSION = 'PN2.23S'


def register(patch):
    @patch(PATCH_ID, 'SPEED shows Unknown when a partner ability read is all ones',
           risk='low', default=False, group='measure', requires=('speed-partner', 'length-ref-reset'))
    def speed_partner_validity(img):
        info = img.speed_partner
        # PN 2.17 result_hook: stock_body first, then bl draw_value at +12.
        site, old_draw = info['result'] + 12, info['result'] + 28
        expected = assemble(site, f'bl {old_draw}')
        if img.read(site, 4) != expected:
            raise PatchError('speed-partner-validity: the result hook has no expected value-draw call')
        hook = img.emit_code(f'''
        checked_value:
                ldr  r0, =STATUS
                ldrh r0, [r0]
                lsrs r0, r0, #14
                cmp  r0, #3             ; stock Error!!: clear the cell without a partner value
                beq  original
                ldr  r0, =CELLS
                ldrh r1, [r0]
                ldrh r0, [r0, #2]
                movw r2, #0xFFFF
                cmp  r1, r2
                beq  unknown
                cmp  r0, r2
                beq  unknown
        original:
                b.w  OLD_DRAW
        unknown:
                push {{r4, lr}}
                sub  sp, #8
                movw r0, #{SP.CELL_BG}
                str  r0, [sp]
                movs r0, #112
                movw r1, #{SP.ROW_Y + 7}
                movs r2, #208
                movw r3, #{SP.ROW_Y + 41}
                bl   gui_draw_rect
                ldr  r0, =unknown_text
                str  r0, [sp, #4]
                movs r0, #0x20
                str  r0, [sp]
                movs r0, #{SP.VALUE_X}
                movw r1, #{SP.TEXT_Y}
                movw r2, #{SP.CELL_BG}
                movw r3, #{SP.WHITE}
                bl   gui_draw_text_box
                add  sp, #8
                pop  {{r4, pc}}
        unknown_text:
                .asciz "Unknown"
        ''', extra_syms=dict(STATUS=SP.STATUS_REG11, CELLS=info['cells'], OLD_DRAW=old_draw | 1),
            why='SPEED: unknown partner capabilities on an all-ones MDIO read')
        img.poke(site, expected.hex(), assemble(site, f'bl {hook}'),
                 'SPEED: validate cached ability words before interpreting their capability bits')
        for version_site in (0x08011660, 0x08012E6C):
            img.set_string(version_site, VERSION)
        img.speed_partner_validity = dict(site=site, hook=hook, old_draw=old_draw)
