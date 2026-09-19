"""PN 1.7: provisional five-level digital tracing feedback.

Eligibility is identical to PN 1.6. Only accepted-window strength and audio
release change. Thresholds describe ADC contrast, not calibrated distance.
"""
import hashlib

from lpm10rx.image import PatchError

PATCHES = {'rx-precision'}
OUTPUT = 'experimental/APP_LPM-10RX_PN1.7-precision.bin'
PREVIOUS_SHA256 = '159bd15f50e3329fd866bdd7e1ebdac2900569dbd2686e2956d82585280457dc'
THRESHOLDS = (800, 2400, 7200, 18000)
UPPER = (880, 2640, 7920, 19800)
LOWER = (720, 2160, 6480, 16200)
GAPS = (160, 110, 75, 45, 20)
ON_MS = 30
AUDIO_RECENT_MIN = 500
GRADE = 0x2000005D
GRADE_HELPER = 0x0800A048
PUBLISH = 0x08009F20
TABLE = 0x080084FC
GAP_TABLE = TABLE + 24
START_TONE = 0x080086EC


def _put(img, addr, size, source, why):
    code = img.assemble_at(addr, source, {
        'precision_grade': GRADE_HELPER,
        'precision_publish': PUBLISH,
        'precision_start_tone': START_TONE,
        'precision_table': TABLE,
        'precision_gaps': GAP_TABLE,
    })
    if len(code) > size or len(code) % 2:
        raise PatchError(f'{why}: {len(code)} bytes exceed {size} at {addr:#x}')
    img.poke(addr, img.read(addr, size).hex(),
             code + bytes.fromhex('00bf') * ((size-len(code)) // 2), why)


def apply(img):
    if hashlib.sha256(img.data).hexdigest() != PREVIOUS_SHA256:
        raise PatchError('rx-precision requires the complete, exact PN 1.6 profile')
    # All newly reclaimed tails contain only unreachable PN 1.6 NOP padding.
    for addr, size in ((TABLE, 40), (START_TONE, 34)):
        if img.read(addr, size) != bytes.fromhex('00bf') * (size // 2):
            raise PatchError(f'precision helper space at {addr:#x} is not unused PN 1.6 padding')
    _put(img, 0x08009E08, PUBLISH - 0x08009E08, '''
        push {r3, r4, r5, r6, r7, lr}
        sub sp, #104
        bl sampling_ready
        cmp r0, #0
        bne snapshot
    early_out:
        add sp, #104
        pop {r3, r4, r5, r6, r7, pc}
    snapshot:
        ldr r0, =0x2000006E
        mov r1, sp
        movs r2, #48
        movs r4, #0
        movw r5, #4095
    copy:
        ldrh r3, [r0]
        strh r3, [r1]
        cmp r3, r4
        bls not_max
        mov r4, r3
    not_max:
        cmp r3, r5
        bhs not_min
        mov r5, r3
    not_min:
        adds r0, #2
        adds r1, #2
        subs r2, #1
        bne copy
        subs r4, r4, r5
        str r4, [sp, #100]
        ldr r0, =0x20000008
        movs r1, #1
        strb r1, [r0]
        mov r0, sp
        movs r1, #48
        bl trimmed_mean
        mov r5, r0
        mov r0, sp
        movs r1, #48
        movs r6, #5
        movs r7, #0
        movs r4, #0
        str r4, [sp, #96]
    threshold:
        ldrh r2, [r0]
        cmp r2, r5
        bls low
        add r6, r2
        subs r2, r2, r5
        movs r3, #1
        b save_bit
    low:
        subs r2, r5, r2
        movs r3, #0
    save_bit:
        add r7, r2
        lsls r4, r4, #1
        orrs r4, r3
        uxth r4, r4
        movw r2, #0xB6B6
        cmp r4, r2
        bne no_exact
        ldr r2, [sp, #96]
        adds r2, #1
        str r2, [sp, #96]
    no_exact:
        strh r3, [r0]
        adds r0, #2
        subs r1, #1
        bne threshold
        cmp r7, #192
        blo rejected
        movw r0, #1000
        cmp r6, r0
        blo rejected
        ldr r0, [sp, #96]
        ldr r1, [sp, #100]
        subs r7, r7, r1
        str r7, [sp, #96]
        cmp r0, #2
        bhs detected
        movw r4, #0xB6B6
        movt r4, #0xB6B6
        movs r5, #8
    phase:
        mov r6, r4
        mov r0, sp
        movs r1, #48
        movs r2, #0
        movs r3, #0
    bit:
        lsrs r7, r6, #31
        lsls r6, r6, #1
        orrs r6, r7
        ldrh r7, [r0]
        eors r7, r6
        lsls r7, r7, #31
        beq matched
        adds r2, #1
        adds r3, #1
        cmp r2, #4
        bhi next_phase
        cmp r3, #2
        bhi next_phase
    matched:
        adds r0, #2
        subs r1, #1
        beq detected
        movs r7, #15
        ands r7, r1
        bne bit
        movs r3, #0
        b bit
    next_phase:
        lsrs r7, r4, #31
        lsls r4, r4, #1
        orrs r4, r7
        subs r5, #1
        bne phase
    rejected:
        movs r1, #0
        bl precision_publish
        b done
    detected:
        ldr r0, [sp, #96]
        bl precision_grade
    done:
        add sp, #104
        pop {r3, r4, r5, r6, r7, pc}
    ''', 'precision detector: preserve eligibility, remove two extrema from strength only')
    _put(img, PUBLISH, 0x08009F58-PUBLISH, '''
        mrs r3, primask
        cpsid i
        ldr r2, =0x20000048
        ldrb r0, [r2, #1]
        cmp r0, #0
        bne done
        mov r0, r2
        adds r0, #0xA7
        ldrb r0, [r0]
        cmp r0, #2
        bne done
        strb r1, [r2, #21]
        cmp r1, #0
        beq done
        movw r0, #800
        strh r0, [r2, #36]
    done:
        msr primask, r3
        bx lr
    ''', 'precision publication: reject stale work; failed windows clear audio grade only')
    _put(img, GRADE_HELPER, 0x0800A0A4-GRADE_HELPER, '''
        push {r4, r5, r6, lr}
        mov r4, r0
        ldr r2, =0x2000005A
        ldrb r5, [r2, #3]
        ldrh r0, [r2, #18]
        movw r1, #500
        cmp r0, r1
        bhi recent
        movs r5, #0
    recent:
        ldr r6, =precision_table
        movs r1, #1
    boundary:
        ldrh r2, [r6]
        cmp r5, #0
        beq compare
        cmp r5, r1
        bhi falling
        ldrh r2, [r6, #2]
        b compare
    falling:
        ldrh r2, [r6, #4]
    compare:
        cmp r4, r2
        blo publish
        adds r6, #6
        adds r1, #1
        cmp r1, #5
        blo boundary
    publish:
        bl precision_publish
        pop {r4, r5, r6, pc}
    ''', 'precision grade: five wide contrast bands with ten-percent hysteresis')
    values = [x for row in zip(THRESHOLDS, UPPER, LOWER) for x in row]
    table_source = '.short ' + ','.join(str(x) for x in values)
    # Leading zero makes the cadence lookup directly indexed by grade 1..5.
    table_source += '\n.byte 0,' + ','.join(str(x) for x in GAPS)
    _put(img, TABLE, 40, table_source, 'precision thresholds and five repeat gaps')
    _put(img, START_TONE, 34, '''
        ldr r0, =precision_gaps
        add r0, r1
        ldrb r1, [r0]
        ldr r0, =0x2000005A
        strb r1, [r0]
        movs r0, #30
        strb r0, [r2]
        msr primask, r3
        b.w speaker_tick
    ''', 'precision tone: fixed 30 ms pulse with grade-dependent repeat gap')
    _put(img, 0x08007724, 0x4C, '''
        mrs r3, primask
        cpsid i
        ldr r2, =0x2000010C
        ldrb r0, [r2]
        cbnz r0, done
        ldr r0, =0x20000048
        ldrb r1, [r0, #1]
        cbnz r1, done
        adds r0, #0xA7
        ldrb r1, [r0]
        subs r0, #0xA7
        cmp r1, #2
        bne done
        ldrh r1, [r0, #36]
        movw r0, #500
        cmp r1, r0
        bls done
        ldr r0, =0x2000005A
        ldrb r1, [r0]
        cbnz r1, done
        ldrb r1, [r0, #3]
        cbz r1, done
        b.w precision_start_tone
    done:
        ldrb r0, [r2]
        msr primask, r3
        b.w speaker_tick
    ''', 'precision audio: five tempos, first rejected-window release, and 300 ms freshness')
    # PN 1.6's publisher slot now receives a strength score, not a repeat gap.
    # Retire that assembly alias so later patches cannot use the old ABI.
    img.syms.pop('publish_digital', None)
    img.syms.update(precision_grade=GRADE_HELPER | 1,
                    precision_publish=PUBLISH | 1,
                    precision_start_tone=START_TONE | 1)
    img.precision = True


def register(patch):
    patch('rx-precision', 'Five-level digital tracing with hysteresis and prompt audio release',
          risk='untested', default=False, group='scan')(apply)
