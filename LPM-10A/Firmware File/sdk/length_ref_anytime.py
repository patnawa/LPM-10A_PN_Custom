"""PN 2.22: REF is reachable before a measurement; a REF dialled first is applied to the next result.

PN 2.18 offered the REF target only while a result was on screen: without one, holding OK went
ZERO -> NVP and REF was skipped without a word.  The owner met exactly that on the first try
(2026-09-21, "ZERO doesn't change to REF, it goes back to NVP") -- and measuring first is not the
order everyone expects: "tell the tester the length, then measure" is as natural as "measure, then
tell it the length".

PN 2.22 makes the OK-long cycle always NVP -> ZERO -> REF -> NVP:

  * REF entered with a result on screen starts at the displayed mean, and UP / DOWN solve NVP at
    once -- PN 2.18 unchanged.
  * REF entered without a result starts at the value last dialled (10.0 m the first time).  UP /
    DOWN dial it and mark it pending; when the next measurement completes while REF is still the
    target, NVP is solved from that result once and the mark is cleared, so the measurement after
    it is an ordinary one: a REF target left behind never re-fits NVP by itself.
  * Leaving REF (OK long) and entering the screen clear the mark.

Mechanics, on top of length-reference's routines (patches.py records them in img.length_reference)
and nvp-calibration's (img.nvp):

  * Action_key_Process 0x08014A04 `bl key_hook2` -> `bl key_hook3`: the same cases as key_hook2
    (OK long, UP / DOWN while REF is the target) with the rules above; everything else falls
    through to nvp-calibration's key_hook as before, so NVP and ZERO editing are the PN 1.1 code.
  * APP_LENG_Test_Sequence 0x08012C02, the `bl GUI_MSG_SEND` that posts the result (message 0x1A)
    after the four readings are stored and the flag is set to 2 -> `bl result_hook`: solve if REF
    is the target and pending, then post 0x1A and, after a solve, 0x3D for the header's grey NVP.
  * Length screen entry 0x08012F1C `bl unit_load` -> `bl entry_hook`: unit_load (unit index,
    target = NVP), then the pending mark cleared.
"""
import hashlib

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_MCLASS

from lpm10a.image import PatchError
from lpm10a.thumb import assemble

import length_reference as LR


PATCH_ID = 'length-ref-anytime'
VERSION = 'PN 2.22'
PARENT_SHA256 = '23fbc3b4404c866dc8a7961ac7b1cf8ebcfb0bf3b4b2338c6f798d07db0a353e'   # PN 2.21

KEY_SITE = LR.KEY_SITE          # Action_key_Process: bl key_hook2 (length-reference)
RESULT_SITE = 0x08012C02        # APP_LENG_Test_Sequence: bl GUI_MSG_SEND (0x1A) after the flag is set to 2
ENTRY_SITE = 0x08012F1C         # Length screen entry: bl unit_load (length-decimal)
GUI_MSG_SEND = 0x0800E428
REF_DEFAULT = 1000              # 10.0 m: REF the first time it is entered without a result


def bl_target(data, site):
    """The target of the `bl` at `site` (data = container bytes)."""
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS)
    o = site - 0x0800A000 + 0x1000
    i = next(md.disasm(bytes(data[o:o + 4]), site), None)
    if i is None or i.mnemonic != 'bl':
        raise PatchError(f'length-ref-anytime: no bl at 0x{site:08X}')
    return int(i.op_str[1:], 16)


def register(patch):
    @patch(PATCH_ID, 'Length: REF reachable before a measurement; a REF dialled first is applied to the next result',
           risk='low', default=False, group='measure', requires=('length-reference', 'cable-values'))
    def length_ref_anytime(img):
        img.finalize()
        if hashlib.sha256(bytes(img.data)).hexdigest() != PARENT_SHA256:
            raise PatchError('length-ref-anytime requires the exact finalized PN 2.21 parent')
        lr, old_key = img.length_reference, img.nvp['key']
        key_stock = assemble(KEY_SITE, f'bl {lr["key"]}')
        if img.read(KEY_SITE, 4) != key_stock:
            raise PatchError('length-ref-anytime: the key hook site does not call length-reference')
        result_stock = assemble(RESULT_SITE, f'bl {GUI_MSG_SEND}')
        if img.read(RESULT_SITE, 4) != result_stock:
            raise PatchError('length-ref-anytime: the result site is not the stock GUI_MSG_SEND(0x1A)')
        unit_load = bl_target(img.data, ENTRY_SITE)
        entry_stock = assemble(ENTRY_SITE, f'bl {unit_load}')
        pending = img.alloc_ram(4)                       # u8: a REF dialled before a result, to apply to the next
        syms = dict(REF=lr['ref'], PENDING=pending, ADJ=img.adj_target, UNIT=LR.UNIT, OLD_KEY=old_key | 1,
                    MEAN_RAW=lr['mean_raw'] | 1, DISPLAYED=lr['displayed'] | 1, SOLVE=lr['solve'] | 1,
                    UNIT_LOAD=unit_load | 1, GUI_MSG_SEND=GUI_MSG_SEND | 1)

        key = img.emit_code(f'''
        key_hook3:                      ; r5 = key event {{u8 key, u8 evt}}; out r0 = 1 << sysState (as key_hook)
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
                cmp  r2, #6             ; OK long press: NVP -> ZERO -> REF -> NVP, always
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
                beq  no_result
                bl   DISPLAYED          ; a result: REF starts at what the screen shows, 1 .. 300 m
                movw r1, #{LR.REF_MAX}
                cmp  r0, r1
                bls  init_lo
                mov  r0, r1
        init_lo:
                movs r1, #{LR.REF_MIN}
                cmp  r0, r1
                bhs  init_ok
                mov  r0, r1
        init_ok:
                ldr  r1, =REF
                strh r0, [r1]
                ldr  r0, =PENDING       ; a REF taken from a result is not pending
                movs r1, #0
                strb r1, [r0]
                movs r0, #2
                b    set_adj
        no_result:                      ; no result: REF is the value last dialled, 10.0 m the first time
                ldr  r1, =REF
                ldrh r0, [r1]
                movs r2, #{LR.REF_MIN}
                cmp  r0, r2
                blo  ref_dflt
                movw r2, #{LR.REF_MAX}
                cmp  r0, r2
                bls  ref_kept
        ref_dflt:
                movw r0, #{REF_DEFAULT}
                strh r0, [r1]
        ref_kept:
                movs r0, #2
                b    set_adj
        to_nvp: ldr  r0, =PENDING       ; leaving REF forgets a pending REF
                movs r1, #0
                strb r1, [r0]
                movs r0, #0
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
                movs r3, #{LR.STEP_CM}
                cmp  r0, #2
                bne  step_ok
                movs r3, #{LR.STEP_FT}  ; feet: 0.1 ft per step
        step_ok:
                ldr  r0, =REF
                ldrh r2, [r0]
                cmp  r1, #2
                bne  down
                add  r2, r3
                movw r3, #{LR.REF_MAX}
                cmp  r2, r3
                bls  store_ref
                mov  r2, r3
                b    store_ref
        down:   cmp  r1, #3
                bne  delegate
                subs r2, r2, r3
                movs r3, #{LR.REF_MIN}
                cmp  r2, r3
                bge  store_ref
                mov  r2, r3
        store_ref:
                strh r2, [r0]
                bl   MEAN_RAW
                cmp  r0, #0
                beq  pend
                bl   SOLVE              ; a result on screen: NVP now
                b    redraw
        pend:   ldr  r0, =PENDING       ; none yet: NVP from the next one
                movs r1, #1
                strb r1, [r0]
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
        ''', extra_syms=syms, why='Length keys: OK long always cycles NVP / ZERO / REF; a REF dialled without a result is pending')

        result = img.emit_code('''
        result_hook:                    ; APP_LENG_Test_Sequence: the readings are stored and the flag is 2
                push {r4, lr}
                ldr  r0, =ADJ
                ldrb r0, [r0]
                cmp  r0, #2
                bne  post
                ldr  r4, =PENDING
                ldrb r0, [r4]
                cmp  r0, #0
                beq  post
                bl   SOLVE              ; NVP from this result and the REF dialled before it
                movs r0, #0
                strb r0, [r4]           ; once
                movs r2, #0
                movs r1, #0
                movs r0, #0x1A
                bl   GUI_MSG_SEND       ; the result rows, at the new NVP
                movs r2, #0
                movs r1, #0
                movs r0, #0x3D          ; the header: the grey NVP value
                bl   GUI_MSG_SEND
                pop  {r4, pc}
        post:   movs r2, #0
                movs r1, #0
                movs r0, #0x1A
                bl   GUI_MSG_SEND
                pop  {r4, pc}
        ''', extra_syms=syms, why='Length result: a pending REF solves NVP once')

        entry = img.emit_code('''
        entry_hook:                     ; Length screen entry, in front of unit_load (r1 = test_busy_flags)
                push {r4, lr}
                bl   UNIT_LOAD          ; length-decimal: unit index, target = NVP
                ldr  r0, =PENDING
                movs r1, #0
                strb r1, [r0]
                pop  {r4, pc}
        ''', extra_syms=syms, why='Length screen entry: no pending REF')

        img.poke(KEY_SITE, key_stock.hex(), assemble(KEY_SITE, f'bl {key}'),
                 'Action_key_Process: REF-anytime key hook in front of nvp-calibration')
        img.poke(RESULT_SITE, result_stock.hex(), assemble(RESULT_SITE, f'bl {result}'),
                 'APP_LENG_Test_Sequence: a pending REF solves NVP when the result arrives')
        img.poke(ENTRY_SITE, entry_stock.hex(), assemble(ENTRY_SITE, f'bl {entry}'),
                 'Length screen entry: clear the pending REF')
        for site in (0x08011660, 0x08012E6C):
            img.set_string(site, VERSION)
        img.length_ref_anytime = dict(pending=pending, key=key, result=result, entry=entry, unit_load=unit_load)
