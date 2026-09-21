"""PN 1.17: close the gain-code-3 dead zone and smooth the strength rhythm.

Applies only to the complete, exact PN 1.16 image.

Two findings from the 2026-09-21 knob sweeps (docs/RX-SENSITIVITY-2026-09-21.md):

1. `gain_select_3bit` (0x0800A4FC) writes the PB12..PB14 pattern bit by bit, then
   special-cases level 0 to the pattern 0b011 -- which is also what level 3
   produces, so the middle of the knob (43-56 %) drops to the lowest front-end
   gain (~90 ADC counts peak-to-peak where the neighbours give 780 and 1900).
   PN 1.17 maps level 3 to level 2 before the pattern is written, so the knob is
   monotonic: low / 230 / 780 / 780 / high.  The PN 1.15 normaliser table entry
   for code 3 changes from x20.0 to x2.6 to match.

2. With the score normalised, low-gain readings amplify ADC noise into the
   rhythm: at codes 1 and 3 the quiet interval jumped 20 <-> 90 ms within a
   second ("ยังกระตุก").  PN 1.17 replaces the curve helper with one that moves
   the published interval half way toward each new target (delta / 2, applied
   only when that half step is >= the existing 3 ms deadband), so a single noisy
   window shifts the rhythm by half as much and the rhythm settles in two to
   three updates (160-240 ms Digital, ~40-60 ms Analog).  A fresh start (no
   audio in the last 500 ms) or an 'uncertain' reading still takes the target
   directly, so acquisition is not delayed.

The new curve helper is appended (+160 bytes) and reuses the PN 1.15
multiplier table and the PN 1.15 endpoint table; the PN 1.15 normaliser is left
in place but no longer reached.  No RAM is added.
"""
import hashlib

from lpm10rx.image import PatchError

PATCHES = {'rx-smooth-gain'}
OUTPUT = 'experimental/APP_LPM-10RX_PN1.17-smooth-gain.bin'
PARENT_SHA256 = '3b8522146f8903c00decc4e1bf6cedc671cffe106c5fd18c172450fa916f46bc'
PREVIOUS_SHA256 = PARENT_SHA256

GAIN_SELECT_SITE = 0x0800A500      # strb.w r0,[sp,#7]; ldrb.w r0,[sp,#7]  (8 bytes)
GAIN_SELECT_RESUME = 0x0800A508    # lsls r0, r0, #31 (bit 0 -> PB12)
MULT_TABLE = 0x0800CE86            # PN 1.15 table: 200 92 26 200 11 11 11 10
GAP_HELPER = 0x0800A048            # entry: b.w 0x0800CE68 (PN 1.15 normaliser)
PN115_NORMALISER = 0x0800CE68
CURVE_TABLE = 0x080084FC
PUBLISH = 0x08009F20
GAIN_CODE = 0x2000006A
STATE = 0x2000005A                 # +3 published interval (0x5D), +18 RECENT (0x6C)
DEADBAND_MS = 3

GAIN_FIX_SOURCE = f'''
    cmp r0, #3
    bne keep
    movs r0, #2                 ; level 3's pattern equals level 0's (lowest gain): use level 2's
keep:
    mov r1, sp
    strb r0, [r1, #7]
    b.w {GAIN_SELECT_RESUME:#x}
'''

CURVE_SOURCE = f'''
    push {{r4, r5, r6, lr}}
    ldr r1, ={GAIN_CODE:#x}
    ldrh r1, [r1]
    cmp r1, #7
    bhi scaled
    ldr r2, ={MULT_TABLE:#x}
    add r2, r1
    ldrb r1, [r2]
    muls r0, r1, r0
    movs r1, #10
    udiv r0, r0, r1             ; score x measured gain step
scaled:
    mov r4, r0
    ldr r2, ={CURVE_TABLE:#x}
    movs r5, #5
interval:
    ldrh r0, [r2]
    cmp r4, r0
    blo interpolate
    subs r4, r4, r0
    adds r2, #4
    subs r5, #1
    bne interval
    movs r1, #20
    b filter
interpolate:
    ldrb r1, [r2, #2]
    ldrb r2, [r2, #3]
    subs r2, r1, r2
    muls r4, r2, r4
    udiv r4, r4, r0
    subs r1, r1, r4             ; r1 = target quiet interval
filter:
    ldr r2, ={STATE:#x}
    ldrh r0, [r2, #18]          ; RECENT
    movw r3, #500
    cmp r0, r3
    bls publish                 ; no fresh audio: take the target at once
    ldrb r0, [r2, #3]           ; published interval
    cmp r0, #1
    bls publish                 ; none, or 'uncertain': take the target at once
    subs r2, r1, r0             ; delta = target - published
    movs r3, #2
    sdiv r2, r2, r3             ; half step toward the target
    mov r3, r2
    cmp r3, #0
    bpl absolute
    rsbs r3, r3, #0
absolute:
    cmp r3, #{DEADBAND_MS}
    blo hold
    add r0, r2
    mov r1, r0                  ; published + delta/2
    b publish
hold:
    mov r1, r0                  ; within the deadband: keep the rhythm
publish:
    bl {PUBLISH:#x}
    pop {{r4, r5, r6, pc}}
    .pool
'''


def apply(img):
    if hashlib.sha256(bytes(img.data)).hexdigest() != PARENT_SHA256:
        raise PatchError('rx-smooth-gain requires the complete, exact PN 1.16 profile')
    if img.read(GAIN_SELECT_SITE, 8) != bytes.fromhex('8df80700 9df80700'):
        raise PatchError('smooth-gain: gain_select_3bit entry is not the expected stock code')
    if img.read(MULT_TABLE, 8) != bytes([200, 92, 26, 200, 11, 11, 11, 10]):
        raise PatchError('smooth-gain: PN 1.15 multiplier table not found')
    entry = img.assemble_at(GAP_HELPER, f'b.w {PN115_NORMALISER:#x}')
    if img.read(GAP_HELPER, 4) != entry:
        raise PatchError('smooth-gain: curve helper entry does not branch to the PN 1.15 normaliser')

    fix = img.extend(32, 'PN 1.17 gain-select level-3 fix appended after the image')
    code = img.assemble_at(fix, GAIN_FIX_SOURCE)
    if len(code) > 32:
        raise PatchError(f'smooth-gain: gain fix is {len(code)} bytes; 32 reserved')
    img.poke(fix, (b'\0' * 32).hex(), code + bytes(32 - len(code)),
             'gain_select_3bit: level 3 uses level 2 pattern (level 3 == level 0 == lowest gain in stock)')
    jump = img.assemble_at(GAIN_SELECT_SITE, f'b.w {fix:#x}')
    img.poke(GAIN_SELECT_SITE, '8df807009df80700', jump + bytes.fromhex('00bf00bf'),
             'gain_select_3bit entry -> level fix')
    img.poke(MULT_TABLE + 3, 'c8', bytes([26]), 'normaliser: code 3 now has code 2 gain (x2.6, was x20)')

    curve = img.extend(160, 'PN 1.17 curve helper with half-step smoothing appended after the image')
    code = img.assemble_at(curve, CURVE_SOURCE)
    if len(code) > 160:
        raise PatchError(f'smooth-gain: curve helper is {len(code)} bytes; 160 reserved')
    img.poke(curve, (b'\0' * 160).hex(), code + bytes(160 - len(code)),
             'curve helper: normalise, interpolate, move half way toward the target, publish')
    img.poke(GAP_HELPER, entry.hex(), img.assemble_at(GAP_HELPER, f'b.w {curve:#x}'),
             'curve helper entry -> PN 1.17 smoothing curve (PN 1.15 normaliser no longer reached)')
    img.smooth_gain = {
        'parent_sha256': PARENT_SHA256,
        'gain_fix': fix,
        'curve': curve,
        'curve_bytes': len(code),
        'half_step': True,
        'deadband_ms': DEADBAND_MS,
        'persistent_ram_bytes': 0,
        'additional_stack_bytes': 0,
    }


def register(patch):
    patch('rx-smooth-gain', 'Knob level 3 gets real mid gain; rhythm moves half way per update',
          risk='untested', default=False, group='audio')(apply)
