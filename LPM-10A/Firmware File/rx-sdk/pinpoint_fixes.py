"""PN 1.8: finer digital strength feedback across the valid ADC range.

The PN 1.7 detector, trimmed strength estimate, publication guards, release,
and active-beep ownership remain unchanged. Its five discrete audio grades
are replaced by an interpolated quiet interval with a small output deadband.
The uncalibrated ADC score remains an indication of contrast, not distance.
"""
import hashlib

from lpm10rx.image import PatchError

PATCHES = {'rx-pinpoint'}
OUTPUT = 'experimental/APP_LPM-10RX_PN1.8-pinpoint.bin'
PREVIOUS_SHA256 = '5ccd7990043507911aeb357d83b0bc6fd054208ff6d253b7feea718e963d38e6'
SCORES = (0, 800, 2400, 7200, 24000, 88000)
GAPS = (160, 130, 105, 75, 45, 20)
SPANS = tuple(b-a for a, b in zip(SCORES, SCORES[1:]))
DEADBAND_MS = 3
ON_MS = 30
AUDIO_RECENT_MIN = 500
GAP_VALUE = 0x2000005D
GAP_HELPER = 0x0800A048
TABLE = 0x080084FC
START_TONE = 0x080086EC
PUBLISH = 0x08009F20


def _put(img, addr, size, source, why):
    code = img.assemble_at(addr, source, {
        'pinpoint_publish': PUBLISH,
        'pinpoint_table': TABLE,
    })
    if len(code) > size or len(code) % 2:
        raise PatchError(f'{why}: {len(code)} bytes exceed {size} at {addr:#x}')
    img.poke(addr, img.read(addr, size).hex(),
             code + bytes.fromhex('00bf') * ((size-len(code)) // 2), why)


def apply(img):
    if hashlib.sha256(img.data).hexdigest() != PREVIOUS_SHA256:
        raise PatchError('rx-pinpoint requires the complete, exact PN 1.7 profile')
    _put(img, GAP_HELPER, 0x0800A0A4-GAP_HELPER, '''
        push {r4, r5, r6, lr}
        mov r4, r0
        ldr r2, =pinpoint_table
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
        subs r1, r1, r4
    filter:
        ldr r2, =0x2000005A
        ldrh r0, [r2, #18]
        movw r3, #500
        cmp r0, r3
        bls publish
        ldrb r0, [r2, #3]
        cbz r0, publish
        subs r2, r1, r0
        bpl absolute
        rsbs r2, r2, #0
    absolute:
        cmp r2, #3
        bhs publish
        mov r1, r0
    publish:
        bl pinpoint_publish
        pop {r4, r5, r6, pc}
    ''', 'pinpoint audio: interpolated strength curve with three-millisecond update threshold')
    # Segment widths fit u16; the strength and remaining distance stay u32.
    # Subtracting five widths also safely clamps a score above the ADC range
    # before multiplication. No absolute 88000-count anchor is narrowed.
    table = '\n'.join(
        f'.short {span}\n.byte {start}, {end}'
        for span, start, end in zip(SPANS, GAPS, GAPS[1:]))
    _put(img, TABLE, 40, table, 'pinpoint curve: five segment widths and endpoint quiet intervals')
    _put(img, START_TONE, 34, '''
        ldr r0, =0x2000005A
        strb r1, [r0]
        movs r0, #30
        strb r0, [r2]
        msr primask, r3
        b.w speaker_tick
    ''', 'pinpoint repeat scheduler: use the published quiet interval directly')
    # These addresses retain their calling convention, but the byte passed
    # to the publisher is now a quiet interval rather than a 1..5 grade.
    img.syms.pop('precision_grade', None)
    img.syms.pop('precision_start_tone', None)
    img.syms.update(pinpoint_gap=GAP_HELPER | 1,
                    pinpoint_publish=PUBLISH | 1,
                    pinpoint_start_tone=START_TONE | 1)
    img.pinpoint = True


def register(patch):
    patch('rx-pinpoint', 'Finer digital strength feedback across the ADC range',
          risk='untested', default=False, group='scan')(apply)
