"""PN 2.16: the About screen shows the pack voltage and the Length calibration.

ROADMAP 3.5.  The three numbers a service check wants are in RAM already: the
battery voltage (battery_millivolts, the same ADC helper the gauge samples once a
second), NVP (settings byte 0xA6, 0 = factory 69 %) and Zero (byte 0xC5, 0.1 m
steps, anything above 20 = 0.0 m).  PN 2.16 prints them on one 6x12 line under
the Factory Reset button, in both languages (the labels are the ASCII ones the
Length screen already uses):

    BATT 3874mV  NVP 68%  ZERO 0.4m

Mechanics.  The About draw routine (0x08011450) ends in `add sp, #0x58; pop`
at 0x0801162C, which crash-record (PN 2.9) already routes through a cave epilogue:
`bl show; add sp, #0x58; pop {r4, r5, r6, pc}`, where `show` draws the retained
fault record.  PN 2.16 points that one `bl` at a wrapper that calls `show` and
then `values`; nothing else in the routine moves.  `values` saves the two colour
globals (0x200001AC fg, 0x200001AE bg), formats the line with the firmware's
sprintf into a stack buffer, draws it with gui_blit in the 6x12 font (the same
call the URL line and the fault record use: x, y, w, h, [sp]=12, [sp+4]=str)
and restores the colours.  The line sits in the free band between the button
(y 239..269) and the panel border (y 310): y 284, x 27, 31 characters = 186 px.
"""
import hashlib

from lpm10a.image import PatchError
from lpm10a.thumb import assemble


PATCH_ID = 'about-values'
VERSION = 'PN 2.16'
PARENT_SHA256 = 'e50d53a460870b4105986086e674552dc5dae18c04a92687ecaf6ec26b43445e'   # PN 2.15
EPILOGUE_SITE = 0x0801162C     # About draw: `add sp, #0x58; pop {r4, r5, r6, pc}` -> b.w epilogue (crash-record)
NVP, ZERO = 0x20000C78 + 0xA6, 0x20000C78 + 0xC5
LINE_X, LINE_Y, LINE_W = 27, 284, 186     # 31 characters of 6 px, centred in the panel (x 8..232)
FMT = 'BATT %dmV  NVP %d%%  ZERO %d.%dm'


def bw_target(addr, code):
    """The target of a Thumb-2 `b.w` encoded in `code` (4 bytes) at `addr`."""
    hw1, hw2 = int.from_bytes(code[:2], 'little'), int.from_bytes(code[2:4], 'little')
    if hw1 >> 11 != 0b11110 or hw2 >> 12 & 0b1101 != 0b1001:
        raise PatchError(f'@0x{addr:08X}: not a b.w ({code.hex()})')
    s = hw1 >> 10 & 1
    j1, j2 = hw2 >> 13 & 1, hw2 >> 11 & 1
    i1, i2 = 1 - (j1 ^ s), 1 - (j2 ^ s)
    imm = (s << 24) | (i1 << 23) | (i2 << 22) | ((hw1 & 0x3FF) << 12) | ((hw2 & 0x7FF) << 1)
    if imm & (1 << 24):
        imm -= 1 << 25
    return addr + 4 + imm


def register(patch):
    @patch(PATCH_ID, 'About: battery mV, NVP and Zero on one line under Factory Reset',
           risk='low', default=False, group='ux',
           requires=('crash-record', 'nvp-calibration', 'length-progress'))
    def about_values(img):
        img.finalize()
        if hashlib.sha256(bytes(img.data)).hexdigest() != PARENT_SHA256:
            raise PatchError('about-values requires the exact finalized PN 2.15 parent')
        show = img.crash['show']
        epilogue = bw_target(EPILOGUE_SITE, img.read(EPILOGUE_SITE, 4))
        stock_call = assemble(epilogue, f'bl {show}')
        if img.read(epilogue, 4) != stock_call:
            raise PatchError('about-values: the About epilogue does not start with the crash-record call')
        values = img.emit_code(f'''
        about_values:                   ; after the fault record: one 6x12 line of live values
                push {{r4, r5, r6, r7, lr}}
                sub  sp, #52            ; [sp..sp+8) varargs 3 and 4, [sp+8..52) text buffer (31 chars + NUL); frame 8-aligned
                ldr  r4, =0x200001AC
                ldrh r5, [r4]           ; keep the colour globals as the caller left them
                ldrh r6, [r4, #2]
                movw r0, #0xFFFF
                strh r0, [r4]
                movw r0, #0x2105
                strh r0, [r4, #2]
                bl   battery_millivolts
                mov  r7, r0
                ldr  r0, =ZERO
                ldrb r0, [r0]
                cmp  r0, #20
                bls  zero_ok
                movs r0, #0             ; unset flash padding reads as 0.0 m (length-decimal's rule)
        zero_ok:
                movs r1, #10
                udiv r2, r0, r1         ; metres
                mls  r3, r2, r1, r0     ; tenths
                str  r2, [sp]
                str  r3, [sp, #4]
                ldr  r3, =NVP
                ldrb r3, [r3]
                cmp  r3, #50
                blo  nvp_default
                cmp  r3, #99
                bls  nvp_ok
        nvp_default:
                movs r3, #69            ; 0 / out of range = the factory 69 %
        nvp_ok: mov  r2, r7
                ldr  r1, =fmt
                mov  r0, sp
                adds r0, #8
                bl   sprintf
                movs r0, #12
                str  r0, [sp]           ; font size 12 (6x12)
                mov  r0, sp
                adds r0, #8
                str  r0, [sp, #4]       ; the text
                movs r0, #{LINE_X}
                movw r1, #{LINE_Y}
                movs r2, #{LINE_W}
                movs r3, #12
                bl   gui_blit
                strh r5, [r4]
                strh r6, [r4, #2]
                add  sp, #52
                pop  {{r4, r5, r6, r7, pc}}
        fmt:    .asciz "{FMT}"
        ''', extra_syms=dict(NVP=NVP, ZERO=ZERO), why='About: BATT / NVP / ZERO line')
        wrapper = img.emit_code(f'''
        about_tail:                     ; the crash-record epilogue's `bl show` comes here
                push {{r4, lr}}
                bl   {show}
                bl   {values}
                pop  {{r4, pc}}
        ''', why='About epilogue: fault record, then the values line')
        img.poke(epilogue, stock_call.hex(), assemble(epilogue, f'bl {wrapper}'),
                 'About epilogue: draw the values line after the fault record')
        for site in (0x08011660, 0x08012E6C):
            img.set_string(site, VERSION)
        img.about_values = dict(values=values, wrapper=wrapper, epilogue=epilogue,
                                x=LINE_X, y=LINE_Y, w=LINE_W)
