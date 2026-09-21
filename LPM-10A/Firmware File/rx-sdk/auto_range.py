"""PN 1.22: automatic gain step-down when the front end saturates.

Applies to the untagged PN 1.21 image.

The knob (PA2) is read every 500 ms by the AGC routine, which publishes the
gate level and then calls `gain_select_3bit(level)` to drive PB12..PB14.
Measured 2026-09-21: on the high gain steps the front end saturates at about
2000-2600 ADC counts peak-to-peak, well below the 4095 rail, so on the cable
every nearby conductor sounds the same (fastest) and Analog can lose its DFT
margin.  PN 1.22 lets the firmware choose a lower gain step by itself:

  every 500 ms tick (main context, before the pins are written):
    knob level (3 mapped to 2 as in PN 1.17) is compared with the last one;
      a change, or the first tick, resets the driven level to the knob and
      clears the hold
    otherwise the 48-sample buffer's peak-to-peak is measured:
      >= 1900 counts -> step down one *effective* step (7..4 -> 2, 2 -> 1, 1 -> 0)
      <   450 counts -> step up (0 -> 1 -> 2 -> knob), never above the knob
      in between      -> keep
    after any change the level is held for 4 ticks (2 s)

The effective steps come from the measured gain ratios (high : 780 : 230 : 90);
1900/450 > 2.6 x 1.3 so a step never oscillates.  The PN 1.15/1.17 strength
normaliser is re-pointed from the knob code (0x2000006A) to the driven level,
so the rhythm keeps reporting the signal at the probe tip after a step; the
mode gates (Digital raw >= 2, Analog code >= 1) still follow the knob.  State
lives in four bytes at 0x20000200 (zero-initialised by the scatter loader,
4.7 KB below the deepest stack seen).
"""
import hashlib

from lpm10rx.image import PatchError
import smooth_gain

PATCHES = {'rx-auto-range'}
OUTPUT = 'experimental/APP_LPM-10RX_PN1.22-auto-range.bin'
PARENT_SHA256 = '4a220f166d5f2fbc2257d8f8094920ae1b78e3dac3488c515d2a0f2c12ca60d5'   # untagged PN 1.21 (the archived file carries the PN1.21 tag)
PREVIOUS_SHA256 = PARENT_SHA256

STATE = 0x20000200             # [0] driven level  [1] always 0 (the normaliser reads a halfword)  [2] hold ticks  [3] last knob level
GAIN_SELECT_SITE = smooth_gain.GAIN_SELECT_SITE      # b.w to the PN 1.17 level-3 fix
PN117_FIX = 0x0800CF08
GAIN_SELECT_RESUME = smooth_gain.GAIN_SELECT_RESUME
CURVE_LITERAL = 0x0800CF9C     # PN 1.17 curve helper pool: 0x2000006A (knob code) -> driven level
BUFFER = 0x2000006E
SAT_PP, RECOVER_PP, HOLD_TICKS = 1900, 450, 4

SOURCE = f'''
    cmp r0, #3
    bne k1
    movs r0, #2                 ; level 3 == level 0 pattern in stock: use level 2 (PN 1.17)
k1:
    ldr r2, ={STATE:#x}
    ldrb r1, [r2, #3]           ; last knob level
    strb r0, [r2, #3]
    ldrb r3, [r2]               ; driven level
    cmp r3, #7
    bhi reset                   ; unset
    cmp r1, r0
    beq keep
reset:
    strb r0, [r2]               ; knob moved (or first tick): follow it
    movs r1, #0
    strb r1, [r2, #2]
    b out
keep:
    push {{r2}}
    ldr r1, ={BUFFER:#x}
    movs r4, #48
    movw r3, #4095
    movs r0, #0
pp:
    ldrh r2, [r1]
    cmp r2, r0
    bls nmax
    mov r0, r2
nmax:
    cmp r2, r3
    bhs nmin
    mov r3, r2
nmin:
    adds r1, #2
    subs r4, #1
    bne pp
    subs r0, r0, r3             ; r0 = peak-to-peak of the sample buffer
    pop {{r2}}
    ldrb r3, [r2]               ; driven level
    ldrb r1, [r2, #2]           ; hold
    cmp r1, #0
    beq nohold
    subs r1, #1
    strb r1, [r2, #2]
    b out
nohold:
    movw r1, #{SAT_PP}
    cmp r0, r1
    blo tryup
    cmp r3, #0
    beq out                     ; already lowest
    cmp r3, #4
    blo down1
    movs r3, #2                 ; 7..4 (one gain step) -> 2
    b changed
down1:
    subs r3, #1
    b changed
tryup:
    movw r1, #{RECOVER_PP}
    cmp r0, r1
    bhs out
    ldrb r1, [r2, #3]           ; knob level
    cmp r3, r1
    bhs out                     ; never above the knob
    cmp r3, #2
    blo up1
    mov r3, r1                  ; 2 -> the knob's high step
    b changed
up1:
    adds r3, #1
changed:
    strb r3, [r2]
    movs r1, #{HOLD_TICKS}
    strb r1, [r2, #2]
out:
    ldrb r0, [r2]
    mov r1, sp
    strb r0, [r1, #7]           ; gain_select_3bit's local copy of the level
    b.w {GAIN_SELECT_RESUME:#x}
    .pool
'''


def apply(img):
    if hashlib.sha256(bytes(img.data)).hexdigest() != PARENT_SHA256:
        raise PatchError('rx-auto-range requires the complete, exact PN 1.21 chain')
    entry = img.assemble_at(GAIN_SELECT_SITE, f'b.w {PN117_FIX:#x}')
    if img.read(GAIN_SELECT_SITE, 4) != entry:
        raise PatchError('auto-range: gain_select_3bit entry does not branch to the PN 1.17 fix')
    if img.read(CURVE_LITERAL, 4) != (0x2000006A).to_bytes(4, 'little'):
        raise PatchError('auto-range: PN 1.17 curve helper literal (knob code) not found')
    helper = img.extend(192, 'PN 1.22 automatic gain range helper appended after the image')
    code = img.assemble_at(helper, SOURCE)
    if len(code) > 192:
        raise PatchError(f'auto-range helper is {len(code)} bytes; 192 reserved')
    img.poke(helper, (b'\0' * 192).hex(), code + bytes(192 - len(code)),
             'AGC: step the gain down at >= 1900 p-p, back up below 450 p-p, 2 s hold, knob change resets')
    img.poke(GAIN_SELECT_SITE, entry.hex(), img.assemble_at(GAIN_SELECT_SITE, f'b.w {helper:#x}'),
             'gain_select_3bit entry -> auto-range helper (PN 1.17 fix folded in)')
    img.poke(CURVE_LITERAL, (0x2000006A).to_bytes(4, 'little').hex(), STATE.to_bytes(4, 'little'),
             'strength normaliser reads the driven gain level instead of the knob code')
    img.auto_range = {'parent_sha256': PARENT_SHA256, 'helper': helper, 'helper_bytes': len(code),
                      'state': STATE, 'sat_pp': SAT_PP, 'recover_pp': RECOVER_PP, 'hold_ticks': HOLD_TICKS,
                      'persistent_ram_bytes': 4}


def register(patch):
    patch('rx-auto-range', 'Gain steps down by itself when the front end saturates (2 s hold)',
          risk='untested', default=False, group='scan')(apply)
