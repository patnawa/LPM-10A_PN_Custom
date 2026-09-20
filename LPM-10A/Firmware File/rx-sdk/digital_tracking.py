"""Candidate legacy B6 local slicing and recent-window strength.

Requires PN 1.9 plus analog_fast/analog_feedback and digital_overlap.
Integrated through the explicit PN 1.11 --tracking profile.
"""
import hashlib

from lpm10rx.image import PatchError
import robust_fixes

DETECTOR = 0x08009E08
PUBLISH = 0x08009F20
LOCAL = 0x0800B5B0
LOCAL_END = 0x0800B630
ESTIMATOR = 0x0800B670
ESTIMATOR_END = 0x0800B70C
SORT = 0x0800B6DE
UNTAG = 0x0800B608
REARM = 0x0800A018

DETECTOR_SOURCE = '''
    push {r3, r4, r5, r6, r7, lr}
    sub sp, #104
    bl sampling_ready
    cbnz r0, snapshot
    b done
snapshot:
    ldr r0, =0x2000006E
    mov r1, sp
    movs r2, #48
copy:
    ldrh r3, [r0]
    strh r3, [r1]
    adds r0, #2
    adds r1, #2
    subs r2, #1
    bne copy
    bl overlap_rearm
    mov r0, sp
    bl local_slice
    cmp r0, #5
    blo global_pass
    movs r0, #255
    str r0, [sp, #96]
    b fit
global_pass:
    mov r0, sp
    bl clear_tags
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
    mov r12, r2
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
    lsls r3, r3, #15
    mov r2, r12
    orrs r3, r2
    strh r3, [r0]
    movw r2, #0xB6B6
    cmp r4, r2
    bne no_exact
    ldr r2, [sp, #96]
    adds r2, #1
    str r2, [sp, #96]
    mov r2, r0
    subs r2, #30
    str r2, [sp, #100]
no_exact:
    adds r0, #2
    subs r1, #1
    bne threshold
    cmp r7, #192
    blo rejected
    movw r0, #1000
    cmp r6, r0
    blo rejected
fit:
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
    lsrs r7, r7, #15
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
    ldr r0, [sp, #96]
    cmp r0, #255
    beq global_pass
    cmp r0, #2
    blo rejected
    ldr r0, [sp, #100]
    b estimate
detected:
    mov r0, sp
    adds r0, #64
estimate:
    mov r1, r4
    bl recent_estimate
    cmp r0, #0
    beq uncertain
    bl robust_gap
    b done
uncertain:
    movs r1, #1
    b publish
rejected:
    movs r1, #0
publish:
    bl robust_publish
done:
    add sp, #104
    pop {r3, r4, r5, r6, r7, pc}
    .pool
'''

LOCAL_SOURCE = '''
    push {r3, r4, r5, r6, r7, lr}
    sub sp, #16
    mov r4, r0
    movs r5, #6
    movs r6, #0
block:
    mov r0, r4
    mov r1, sp
    movs r2, #8
copy:
    ldrh r3, [r0]
    strh r3, [r1]
    adds r0, #2
    adds r1, #2
    subs r2, #1
    bne copy
    mov r0, sp
    movs r1, #8
    bl sort_u16
    mov r0, sp
    ldrh r1, [r0, #2]
    ldrh r2, [r0, #10]
    subs r3, r2, r1
    cmp r3, #9
    blo small
    adds r6, #1
small:
    adds r7, r1, r2
    lsrs r7, r7, #1
    movs r1, #8
tag:
    ldrh r2, [r4]
    movs r3, #0
    cmp r2, r7
    bls low
    movs r3, #1
low:
    lsls r3, r3, #15
    orrs r2, r3
    strh r2, [r4]
    adds r4, #2
    subs r1, #1
    bne tag
    subs r5, #1
    bne block
    mov r0, r6
    add sp, #16
    pop {r3, r4, r5, r6, r7, pc}
'''

ESTIMATOR_SOURCE = '''
    push {r3, r4, r5, r6, r7, lr}
    mov r4, r0
    movs r5, #16
    movs r6, #0
tag:
    ldrh r2, [r0]
    lsrs r3, r1, #31
    lsls r1, r1, #1
    orrs r1, r3
    add r6, r3
    lsls r2, r2, #20
    lsrs r2, r2, #20
    lsls r3, r3, #12
    orrs r2, r3
    strh r2, [r0]
    adds r0, #2
    subs r5, #1
    bne tag
    mov r0, r4
    movs r1, #16
    bl sort_u16
    movs r7, #16
    subs r7, r7, r6
    mov r0, r4
    mov r1, r7
    bl robust_median
    mov r5, r0
    lsls r7, r7, #1
    adds r0, r4, r7
    mov r1, r6
    bl robust_median
    movw r2, #4096
    subs r1, r0, r2
    subs r2, #1
    cmp r1, r2
    bhs uncertain
    cmp r1, r5
    bls uncertain
    subs r0, r1, r5
    movs r1, #29
    muls r0, r1, r0
    movs r1, #46
    udiv r1, r0, r1
    movs r2, #12
    muls r1, r2, r1
    subs r0, r0, r1
    pop {r3, r4, r5, r6, r7, pc}
uncertain:
    movs r0, #0
    pop {r3, r4, r5, r6, r7, pc}
'''

SORT_SOURCE = '''
    push {r4, r5, r6, lr}
    mov r4, r0
    lsls r1, r1, #1
    adds r5, r0, r1
    mov r1, r0
    adds r1, #2
outer:
    ldrh r2, [r1]
    mov r0, r1
inner:
    subs r3, r0, #2
    ldrh r6, [r3]
    cmp r6, r2
    bls insert
    strh r6, [r0]
    mov r0, r3
    cmp r0, r4
    bhi inner
insert:
    strh r2, [r0]
    adds r1, #2
    cmp r1, r5
    blo outer
    pop {r4, r5, r6, pc}
'''

UNTAG_SOURCE = '''
    push {r4, lr}
    mov r4, r0
    movs r1, #48
loop:
    ldrh r2, [r0]
    lsls r2, r2, #20
    lsrs r2, r2, #20
    strh r2, [r0]
    adds r0, #2
    subs r1, #1
    bne loop
    mov r0, r4
    movs r1, #48
    pop {r4, pc}
'''

def sources(img):
    symbols = {'overlap_rearm': REARM, 'local_slice': LOCAL,
               'recent_estimate': ESTIMATOR, 'sort_u16': SORT, 'clear_tags': UNTAG,
               'robust_median': robust_fixes.MEDIAN,
               'robust_gap': robust_fixes.GAP_HELPER, 'robust_publish': PUBLISH}
    return {name: img.assemble_at(address, source, symbols)
            for name, address, source in (
                ('detector', DETECTOR, DETECTOR_SOURCE),
                ('local', LOCAL, LOCAL_SOURCE),
                ('estimator', ESTIMATOR, ESTIMATOR_SOURCE),
                ('sort', SORT, SORT_SOURCE), ('untag', UNTAG, UNTAG_SOURCE))}


def apply(img):
    import analog_fast
    import digital_overlap
    if not getattr(img, 'analog_fast', False) or not getattr(img, 'digital_overlap', False):
        raise PatchError('digital tracking requires verified analog-fast and overlap helpers')
    expected_rearm = img.assemble_at(REARM, digital_overlap.SOURCE)
    expected_rearm += bytes.fromhex('00bf')*((digital_overlap.END-REARM-len(expected_rearm))//2)
    if img.read(REARM, len(expected_rearm)) != expected_rearm:
        raise PatchError('digital tracking requires the exact overlap rearm helper')
    expected_loop = img.assemble_at(analog_fast.LOOP, analog_fast.SOURCE)
    expected_loop += bytes.fromhex('00bf')*((analog_fast.LOOP_END-analog_fast.LOOP-len(expected_loop))//2)
    if img.read(analog_fast.LOOP, len(expected_loop)) != expected_loop:
        raise PatchError('digital tracking requires retired DFT coefficient callers')
    before = {
        'detector': (DETECTOR, PUBLISH),
        'local': (LOCAL, LOCAL_END),
        'estimator': (ESTIMATOR, ESTIMATOR_END),
    }
    # Original PN 1.9 slots; populated from the reproducible source while the
    # retained DFT helper bytes have their independent pinned audit digest.
    guards = {
        'detector': img.assemble_at(DETECTOR, robust_fixes.DETECTOR_SOURCE, {
            'robust_estimate': ESTIMATOR, 'robust_publish': PUBLISH,
            'robust_gap': robust_fixes.GAP_HELPER,
            'robust_median': robust_fixes.MEDIAN}),
        'estimator': img.assemble_at(ESTIMATOR, robust_fixes.ESTIMATOR_SOURCE, {
            'robust_median': robust_fixes.MEDIAN}),
    }
    for name, (start, end) in before.items():
        current = img.read(start, end-start)
        if name == 'local':
            valid = hashlib.sha256(current).hexdigest() == analog_fast.RETIRED_HELPERS_SHA256
        else:
            expected = guards[name]+bytes.fromhex('00bf')*((end-start-len(guards[name]))//2)
            valid = current == expected
        if not valid:
            raise PatchError(f'digital tracking prerequisite differs at {start:#x}')
    codes = sources(img)
    layouts = {
        'detector': (DETECTOR, PUBLISH), 'local': (LOCAL, UNTAG),
        'untag': (UNTAG, LOCAL_END), 'estimator': (ESTIMATOR, SORT),
        'sort': (SORT, ESTIMATOR_END),
    }
    for name, (start, end) in layouts.items():
        if len(codes[name]) > end-start or len(codes[name]) % 2:
            raise PatchError(f'digital tracking {name} needs {len(codes[name])} bytes, available {end-start}')
    for name, (start, end) in layouts.items():
        code = codes[name]+bytes.fromhex('00bf')*((end-start-len(codes[name]))//2)
        img.poke(start, img.read(start, end-start).hex(), code,
                 f'Digital tracking: {name}, robust local code fit and recent strength')
    img.digital_tracking = {'code_bytes': {name: len(code) for name, code in codes.items()},
                            'persistent_ram_bytes': 0, 'observation_samples': 48,
                            'strength_samples': 16, 'update_samples': 16}
