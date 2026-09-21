"""PN 1.15: strength feedback independent of the sensitivity knob, audible floor.

Applies only to the complete, exact PN 1.14 image.

Measured on the owner's probe on 2026-09-21 (docs/RX-SENSITIVITY-2026-09-21.md):
the sensitivity knob (PA2, published every 500 ms as gain code = raw / 580)
selects the front-end gain in three effective steps, not eight.  At one fixed
probe position the ADC peak-to-peak was

    code 0 ~95   code 1 ~230   code 2 ~780   code 3 ~90 (!)   codes 4-7 ~1900-2400

so code 3 falls back to the lowest gain (its PB12..PB14 pattern equals code 0's,
a stock quirk) and codes 4-7 are one step.  PN's strength score is ADC contrast,
so with PN 1.12-1.14 the beep rate followed the knob (x20) more than the cable:
the owner had to turn the knob nearly to maximum to hear the "found" rhythm,
although detection itself already held from code 1 (~15 % of travel).

PN 1.15 multiplies every published strength score (Digital and Analog both go
through the shared curve helper at 0x0800A048) by the gain step measured for the
current code, in tenths:

    code   0    1    2    3    4    5    6    7
    x10  200   92   26  200   11   11   11   10

so the rhythm reports the signal at the probe tip and the knob is once more only
a detection threshold, as on the stock firmware.  The curve's quiet-interval
endpoints change from 160/130/105/75/45/20 ms to 110/95/85/70/45/20 ms, so the
weakest accepted signal still gives a clear ~7 pulses/s instead of ~5, while the
strong end keeps its full resolution.  Pulse lengths, detection, release and the
Analog upper-rail handling are unchanged.  The helper is appended after the PN
1.14 code (+64 bytes); no RAM is added.
"""
import hashlib

from lpm10rx.image import PatchError

PATCHES = {'rx-gain-norm'}
OUTPUT = 'experimental/APP_LPM-10RX_PN1.15-gain-norm.bin'
PARENT_SHA256 = 'ec13803775b06854045347e5dac9def0b20e63556d956a819be2b3fee5db8399'
PREVIOUS_SHA256 = PARENT_SHA256

GAP_HELPER = 0x0800A048        # push {r4,r5,r6,lr}; mov r4, r0  (the strength -> quiet-interval curve)
GAIN_CODE = 0x2000006A         # u16 knob raw / 580, published by the AGC every 500 ms
TABLE = 0x080084FC             # five (u16 span, u8 gap_start, u8 gap_end) curve segments
MULT_X10 = (200, 92, 26, 200, 11, 11, 11, 10)
SCORES = (0, 800, 2400, 7200, 24000, 88000)
GAPS = (110, 95, 85, 70, 45, 20)
OLD_GAPS = (160, 130, 105, 75, 45, 20)

HELPER_SOURCE = f'''
    push {{r4, r5, r6, lr}}
    ldr r1, ={GAIN_CODE:#x}
    ldrh r1, [r1]
    cmp r1, #7
    bhi scaled
    ldr r2, =mult_table
    add r2, r1
    ldrb r1, [r2]
    muls r0, r1, r0
    movs r1, #10
    udiv r0, r0, r1
scaled:
    mov r4, r0
    b.w {GAP_HELPER + 4:#x}
mult_table:
    .byte {", ".join(str(m) for m in MULT_X10)}
    .pool
'''


def _table(gaps):
    return b''.join(
        (b - a).to_bytes(2, 'little') + bytes([s, e])
        for a, b, s, e in zip(SCORES, SCORES[1:], gaps, gaps[1:]))


def apply(img):
    if hashlib.sha256(bytes(img.data)).hexdigest() != PARENT_SHA256:
        raise PatchError('rx-gain-norm requires the complete, exact PN 1.14 profile')
    if img.read(GAP_HELPER, 4) != bytes.fromhex('70b5 0446'):
        raise PatchError(f'gain-norm: curve helper at {GAP_HELPER:#x} does not start with push/mov')
    old_table = _table(OLD_GAPS)
    if img.read(TABLE, len(old_table)) != old_table:
        raise PatchError('gain-norm: pinpoint curve table is not the PN 1.8 table')
    helper = img.extend(64, 'PN 1.15 knob-gain normaliser appended after the image')
    code = img.assemble_at(helper, HELPER_SOURCE)
    if len(code) > 64 or len(code) % 4:
        raise PatchError(f'gain-norm helper is {len(code)} bytes; 64 reserved')
    img.poke(helper, (b'\0' * 64).hex(), code + bytes(64 - len(code)),
             'Strength score x measured gain step (tenths) before the quiet-interval curve')
    img.poke(GAP_HELPER, '70b50446', img.assemble_at(GAP_HELPER, f'b.w {helper:#x}'),
             'curve helper entry -> gain normaliser (which pushes and returns to the curve)')
    img.poke(TABLE, old_table.hex(), _table(GAPS),
             'quiet-interval endpoints 160/130/105/75 -> 110/95/85/70 ms (45/20 unchanged)')
    img.gain_norm = {
        'parent_sha256': PARENT_SHA256,
        'helper': helper,
        'helper_bytes': len(code),
        'mult_x10': MULT_X10,
        'gaps_ms': GAPS,
        'persistent_ram_bytes': 0,
        'additional_stack_bytes': 0,
    }


def register(patch):
    patch('rx-gain-norm', 'Beep rate follows the cable, not the sensitivity knob; audible floor',
          risk='untested', default=False, group='audio')(apply)
