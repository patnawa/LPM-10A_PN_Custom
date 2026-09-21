"""PN 2.18: calibrate NVP from a cable of known length, on the Length screen.

Since PN 1.1 the Length screen has two calibration values, NVP and Zero: UP / DOWN
change the white one, holding OK for a second swaps them (nvp-calibration).  Setting
NVP against a known cable meant nudging it 1 % at a time until the reading matched.
PN 2.18 adds a third target to the OK-long cycle, REF, offered only while a result is
on screen:

    NVP  ->  ZERO  ->  REF  ->  NVP ...

With REF active the left header text reads "REF 20.7" (the measured length, in the
current unit) instead of "ZERO 0.4m", and UP / DOWN dial it to the cable's true
length (0.1 m / 10 cm / 0.1 ft per step, auto-repeat as for NVP).  Every step solves

    NVP = 69 * REF / (raw - 10 * Zero)          (FORMULA-AUDIT 1.6, rounded, 50..99 %)

where raw is the mean of the four pairs' raw centimetres (pairs the PHY could not
time are left out), stores NVP in its settings byte and redraws "NVP nn%" (grey,
right) and the four readings through GUI message 0x3D, so the readings settle on the
dialled length as you watch.  NVP is saved when leaving the screen like every other
calibration (calibration-autosave).  Zero is unchanged by REF: set it first on a short
cable as before, then REF on a long one.  Leaving the screen resets the target to NVP.

Mechanics, on top of nvp-calibration's routines (patches.py records their addresses
in img.nvp):

  * Action_key_Process 0x08014A04 `bl key_hook` -> `bl key_hook2`.  key_hook2 handles
    OK long press (the three-way cycle) and UP / DOWN while REF is active (REF in a
    RAM cell, then the solve); every other event falls through to key_hook, so NVP and
    ZERO editing are the PN 1.1 code.
  * the two `bl nvp_draw` (GUI message 0x3D and the Length header epilogue) ->
    `bl nvp_draw2`, which draws the REF header while REF is active and otherwise
    jumps to nvp_draw.  Same font, positions and colours as the NVP / ZERO texts.
"""
import hashlib

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_MCLASS

from lpm10a.image import PatchError
from lpm10a.thumb import assemble


PATCH_ID = 'length-reference'
VERSION = 'PN 2.18'
PARENT_SHA256 = '78b50e5d003a957f3f941a8b50e39494bbbadb2179d1971bca9a39459e775071'   # PN 2.17

KEY_SITE = 0x08014A04           # Action_key_Process: bl key_hook (nvp-calibration)
NVP, ZERO = 0x20000C78 + 0xA6, 0x20000C78 + 0xC5
FLAGS, RESULTS, UNIT = 0x200002B4, 0x200002B8, 0x200002C0
REF_MIN, REF_MAX = 100, 30000   # 1 m .. 300 m
STEP_CM, STEP_FT = 10, 3        # 0.1 m; 0.1 ft = 3.048 cm
GREY, WHITE = 0x8410, 0xFFFF
HEADER_Y = 90


def find_bl(data, start, target, span=0x80):
    """Address of the first `bl target` in the code at `start` (data = container bytes)."""
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS)
    o = start - 0x0800A000 + 0x1000
    for i in md.disasm(bytes(data[o:o + span]), start):
        if i.mnemonic == 'bl' and i.op_str.startswith('#') and int(i.op_str[1:], 16) == target:
            return i.address
    raise PatchError(f'length-reference: no bl 0x{target:08X} in the routine at 0x{start:08X}')


def register(patch):
    @patch(PATCH_ID, 'Length: REF target dials a known cable length and solves NVP from it',
           risk='low', default=False, group='measure',
           requires=('nvp-calibration', 'length-decimal', 'speed-partner'))
    def length_reference(img):
        img.finalize()
        if hashlib.sha256(bytes(img.data)).hexdigest() != PARENT_SHA256:
            raise PatchError('length-reference requires the exact finalized PN 2.17 parent')
        old_key, old_draw = img.nvp['key'], img.nvp['draw']
        key_stock = assemble(KEY_SITE, f'bl {old_key}')
        if img.read(KEY_SITE, 4) != key_stock:
            raise PatchError('length-reference: the key hook site does not call nvp-calibration')
        draw_sites = [find_bl(img.data, img.nvp['gui'], old_draw), find_bl(img.data, img.nvp['tail'], old_draw)]
        ref = img.alloc_ram(4)                           # u16: the reference length in cm (session only)
        syms = dict(NVP=NVP, ZERO=ZERO, ADJ=img.adj_target, REF=ref, FLAGS=FLAGS, RESULTS=RESULTS,
                    UNIT=UNIT, OLD_KEY=old_key | 1, OLD_DRAW=old_draw | 1)

        mean_raw = img.emit_code('''
        mean_raw:                       ; r0 = mean raw cm of the pairs the PHY timed; 0 without a result on screen
                ldr  r0, =FLAGS
                ldrb r0, [r0]
                cmp  r0, #2
                bne  no_result
                ldr  r1, =RESULTS
                movs r2, #0             ; sum
                movs r3, #0             ; pairs counted
                ldrh r0, [r1]
                cmp  r0, #0
                beq  pair1
                add  r2, r0
                adds r3, #1
        pair1:  ldrh r0, [r1, #2]
                cmp  r0, #0
                beq  pair2
                add  r2, r0
                adds r3, #1
        pair2:  ldrh r0, [r1, #4]
                cmp  r0, #0
                beq  pair3
                add  r2, r0
                adds r3, #1
        pair3:  ldrh r0, [r1, #6]
                cmp  r0, #0
                beq  summed
                add  r2, r0
                adds r3, #1
        summed: cmp  r3, #0
                beq  no_result
                udiv r0, r2, r3
                bx   lr
        no_result:
                movs r0, #0
                bx   lr
        ''', extra_syms=syms, why='Length REF: mean raw centimetres of the timed pairs')
        zeroed = img.emit_code('''
        zeroed:                         ; r0 = raw cm -> r0 = raw - 10 * Zero (0 at or below it), as length_convert2
                ldr  r1, =ZERO
                ldrb r1, [r1]
                cmp  r1, #20
                bhi  zeroed_done
                movs r2, #10
                muls r1, r2, r1
                subs r0, r0, r1
                bgt  zeroed_done
                movs r0, #0
        zeroed_done:
                bx   lr
        ''', extra_syms=syms, why='Length REF: Zero correction')
        displayed = img.emit_code('''
        displayed:                      ; r0 = raw cm -> r0 = the cm the screen shows for it (Zero and NVP applied)
                push {r4, lr}
                bl   ZEROED
                ldr  r1, =NVP
                ldrb r1, [r1]
                cmp  r1, #50
                blo  displayed_done
                cmp  r1, #99
                bhi  displayed_done
                mul  r0, r0, r1
                adds r0, #34
                movs r1, #69
                udiv r0, r0, r1
        displayed_done:
                pop  {r4, pc}
        ''', extra_syms=dict(syms, ZEROED=zeroed | 1), why='Length REF: the displayed centimetres of a raw reading')
        solve = img.emit_code('''
        solve:                          ; NVP = 69 * REF / (raw - 10 * Zero), rounded, 50..99; nothing without a result
                push {r4, lr}
                bl   MEAN_RAW
                cmp  r0, #0
                beq  solved
                bl   ZEROED
                cmp  r0, #0
                beq  solved
                ldr  r1, =REF
                ldrh r1, [r1]
                movs r2, #69
                muls r1, r2, r1         ; 69 * REF, at most 2 070 000
                lsrs r2, r0, #1
                add  r1, r2             ; + half the divisor: rounded
                udiv r1, r1, r0
                cmp  r1, #50
                bhs  nvp_hi
                movs r1, #50
        nvp_hi: cmp  r1, #99
                bls  nvp_store
                movs r1, #99
        nvp_store:
                ldr  r0, =NVP
                strb r1, [r0]
        solved: pop  {r4, pc}
        ''', extra_syms=dict(syms, MEAN_RAW=mean_raw | 1, ZEROED=zeroed | 1), why='Length REF: the NVP solver')

        key = img.emit_code(f'''
        key_hook2:                      ; r5 = key event {{u8 key, u8 evt}}; out r0 = 1 << sysState (as key_hook)
                push {{r4, r5, r6, lr}}
                movs r0, #1
                bl   get_sysState
                mov  r4, r0
                cmp  r0, #0x80          ; the Length screen only
                bne  delegate
                ldrb r1, [r5]           ; key: 2 = UP, 3 = DOWN, 4 = OK
                ldrb r2, [r5, #1]       ; event: 3 = click, 6 = long press, 12 = auto-repeat
                ldr  r6, =ADJ
                ldrb r3, [r6]
                cmp  r1, #4
                bne  not_ok
                cmp  r2, #6             ; OK long press: NVP -> ZERO -> REF (with a result) -> NVP
                bne  delegate
                cmp  r3, #1
                beq  from_zero
                cmp  r3, #2
                beq  to_nvp
                movs r0, #1             ; NVP (or arena garbage) -> ZERO
                b    set_adj
        from_zero:
                bl   MEAN_RAW
                cmp  r0, #0
                beq  to_nvp             ; nothing measured yet: REF is skipped
                bl   DISPLAYED
                movw r1, #{REF_MAX}     ; REF starts at what the screen shows, within its 1 .. 300 m range
                cmp  r0, r1
                bls  init_lo
                mov  r0, r1
        init_lo:
                movs r1, #{REF_MIN}
                cmp  r0, r1
                bhs  init_ok
                mov  r0, r1
        init_ok:
                ldr  r1, =REF
                strh r0, [r1]
                movs r0, #2
                b    set_adj
        to_nvp: movs r0, #0
        set_adj:
                strb r0, [r6]
                b    redraw
        not_ok: cmp  r3, #2
                bne  delegate           ; NVP / ZERO editing: the PN 1.1 hook
                cmp  r2, #3
                beq  updown
                cmp  r2, #12
                bne  delegate
        updown: ldr  r0, =UNIT
                ldrb r0, [r0]
                movs r3, #{STEP_CM}
                cmp  r0, #2
                bne  step_ok
                movs r3, #{STEP_FT}     ; feet: 0.1 ft per step
        step_ok:
                ldr  r0, =REF
                ldrh r2, [r0]
                cmp  r1, #2
                bne  down
                add  r2, r3
                movw r3, #{REF_MAX}
                cmp  r2, r3
                bls  store_ref
                mov  r2, r3
                b    store_ref
        down:   cmp  r1, #3
                bne  delegate
                subs r2, r2, r3
                movs r3, #{REF_MIN}
                cmp  r2, r3
                bge  store_ref
                mov  r2, r3
        store_ref:
                strh r2, [r0]
                bl   SOLVE
        redraw: movs r0, #0x64
                bl   key_activity_notify
                movs r2, #0
                movs r1, #0
                movs r0, #0x3D
                bl   GUI_MSG_SEND
                mov  r0, r4
                pop  {{r4, r5, r6, pc}}
        delegate:                       ; everything else is nvp-calibration's: restore and jump
                ldr  r0, [sp, #12]
                mov  lr, r0
                pop  {{r4, r5, r6}}
                add  sp, #4
                b.w  OLD_KEY
        ''', extra_syms=dict(syms, MEAN_RAW=mean_raw | 1, DISPLAYED=displayed | 1, SOLVE=solve | 1),
            why='Length keys: OK long cycles NVP / ZERO / REF; UP / DOWN dial REF and solve NVP')

        draw = img.emit_code(f'''
        nvp_draw2:                      ; the header texts: REF replaces ZERO while it is the target
                ldr  r0, =ADJ
                ldrb r0, [r0]
                cmp  r0, #2
                beq  ref_header
                b.w  OLD_DRAW
        ref_header:
                push {{r4, r5, lr}}
                sub  sp, #20            ; text buffer
                ldr  r0, =NVP
                ldrb r2, [r0]
                cmp  r2, #50
                blo  nvp_dflt
                cmp  r2, #99
                bls  nvp_have
        nvp_dflt:
                movs r2, #69
        nvp_have:
                ldr  r1, =fmt_nvp
                mov  r0, sp
                bl   sprintf
                movw r0, #{GREY}
                bl   colour
                movs r0, #166
                movs r1, #56            ; 7 characters, as "NVP nn%"
                bl   blit
                ldr  r0, =REF
                ldrh r0, [r0]
                ldr  r1, =UNIT
                ldrb r1, [r1]
                cmp  r1, #1
                beq  ref_cm
                cmp  r1, #2
                beq  ref_ft
                adds r0, #5             ; metres: tenths = (cm + 5) / 10
                movs r1, #10
                udiv r0, r0, r1
                b    ref_tenths
        ref_ft: movw r1, #1000          ; feet: tenths = (cm * 1000 + 1524) / 3048
                mul  r0, r0, r1
                movw r1, #1524
                add  r0, r1
                movw r1, #3048
                udiv r0, r0, r1
        ref_tenths:
                movs r1, #10
                udiv r2, r0, r1         ; integer part
                mls  r3, r2, r1, r0     ; tenths
                ldr  r1, =fmt_dec
                b    ref_fmt
        ref_cm: mov  r2, r0
                ldr  r1, =fmt_int
        ref_fmt:
                mov  r0, sp
                bl   sprintf
                mov  r1, sp             ; pad with spaces to the 9 characters of "ZERO n.nm", so it is fully covered
                mov  r2, r0
        pad:    cmp  r2, #9
                bge  padded
                adds r3, r1, r2
                movs r0, #0x20
                strb r0, [r3]
                adds r2, #1
                b    pad
        padded: movs r0, #0
                strb r0, [r1, #9]
                movw r0, #{WHITE}
                bl   colour
                movs r0, #4
                movs r1, #72            ; 9 characters
                bl   blit
                add  sp, #20
                pop  {{r4, r5, pc}}
        colour:                         ; r0 = text colour; background black (the header is drawn on the cleared screen)
                ldr  r1, =0x200001AC
                strh r0, [r1]
                movs r0, #0
                strh r0, [r1, #2]
                bx   lr
        blit:                           ; r0 = x, r1 = w; the text is the buffer at the caller's sp; y 90, 8x16
                push {{r4, lr}}
                sub  sp, #8
                movs r4, #0x10
                str  r4, [sp]
                mov  r4, sp
                adds r4, #16            ; the caller's buffer: 8 (our args) + 8 (push)
                str  r4, [sp, #4]
                mov  r2, r1
                movs r1, #{HEADER_Y}
                movs r3, #16
                bl   gui_blit
                add  sp, #8
                pop  {{r4, pc}}
        fmt_nvp: .asciz "NVP %2d%%"
        fmt_dec: .asciz "REF %d.%d"
        fmt_int: .asciz "REF %d"
        ''', extra_syms=syms, why='Length header: "REF n.n" (white) and "NVP nn%" (grey) while REF is the target')

        img.poke(KEY_SITE, key_stock.hex(), assemble(KEY_SITE, f'bl {key}'),
                 'Action_key_Process: REF-aware key hook in front of nvp-calibration')
        for site in draw_sites:
            img.poke(site, assemble(site, f'bl {old_draw}').hex(), assemble(site, f'bl {draw}'),
                     'Length header: REF-aware draw in front of nvp_draw')
        for site in (0x08011660, 0x08012E6C):
            img.set_string(site, VERSION)
        img.length_reference = dict(ref=ref, key=key, draw=draw, mean_raw=mean_raw, zeroed=zeroed,
                                    displayed=displayed, solve=solve, draw_sites=draw_sites)
