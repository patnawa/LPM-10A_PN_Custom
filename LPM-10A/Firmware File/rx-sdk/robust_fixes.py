"""PN 1.9 prototype: code-conditioned strength and uncertain-reading audio.

Find eligibility and sampling remain PN 1.8-compatible. A bounded full-window
code match supplies a unique phase for two group medians. Exact-only matches
instead use the union of their verified samples, counting overlap once.
Upper-rail-dominated or inseparable levels use a distinct 100 ms pulse rather
than a misleading strength estimate. No gain calibration, physical cable
identity, or increased sampling rate is claimed.
"""
import hashlib

from lpm10rx.image import PatchError
import compact_mean

PATCHES = {'rx-robust'}
OUTPUT = 'experimental/APP_LPM-10RX_PN1.9-robust.bin'
PREVIOUS_SHA256 = 'a588af8e0883fca119b9ed00e30761502ec0c4e0d2b6fee16a67c8b7cacc615d'
DETECTOR = 0x08009E08
PUBLISH = 0x08009F20
GAP_HELPER = 0x0800A048
ESTIMATOR = 0x0800B670
ESTIMATOR_END = 0x0800B70C
MEDIAN = 0x0800B584
START_TONE = 0x080086EC
UNCERTAIN = 1
UNCERTAIN_ON_MS = 100
UNCERTAIN_GAP_MS = 160


def _put(img, addr, size, source, why):
    code = img.assemble_at(addr, source, {
        'robust_estimate': ESTIMATOR,
        'robust_publish': PUBLISH,
        'robust_gap': GAP_HELPER,
        'robust_median': MEDIAN,
    })
    if len(code) > size or len(code) % 2:
        raise PatchError(f'{why}: {len(code)} bytes exceed {size} at {addr:#x}')
    img.poke(addr, img.read(addr, size).hex(),
             code + bytes.fromhex('00bf') * ((size-len(code)) // 2), why)


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
    mov r12, r1
    movs r1, #16
    mov r2, r0
    str r7, [sp, #100]
    movw r7, #0x4000
mark_exact:
    ldrh r3, [r2]
    orrs r3, r7
    strh r3, [r2]
    subs r2, #2
    subs r1, #1
    bne mark_exact
    mov r1, r12
    ldr r7, [sp, #100]
no_exact:
    adds r0, #2
    subs r1, #1
    bne threshold
    cmp r7, #192
    blo rejected
    movw r0, #1000
    cmp r6, r0
    blo rejected
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
    cmp r0, #2
    blo rejected
    movs r4, #0
    b detected
rejected:
    movs r1, #0
    b publish
detected:
    mov r0, sp
    mov r1, r4
    bl robust_estimate
    cmp r0, #0
    beq uncertain
    bl robust_gap
    b done
uncertain:
    movs r1, #1
publish:
    bl robust_publish
done:
    add sp, #104
    pop {r3, r4, r5, r6, r7, pc}
'''

# Input: r0 -> owned 48-halfword snapshot; r1 -> rotated B6 pattern, or zero
# for the union of exact matches marked in bit 14 by the detector. Bit 15
# carries the observed threshold decision. The full fit groups all samples
# by EXPECTED code; fallback groups only marked samples by their observed bit.
# Sorting puts selected lows first, then highs, then excluded 0xFFFF values.
# Group medians handle even and odd counts; only the owned snapshot is mutated.
ESTIMATOR_SOURCE = '''
    push {r3, r4, r5, r6, r7, lr}
    mov r4, r0
    movs r5, #48
    movs r6, #0
    movs r7, #0
tag:
    ldrh r2, [r0]
    cmp r1, #0
    bne code
    lsls r3, r2, #17
    bpl exclude
    lsrs r3, r2, #15
    b include
code:
    lsrs r3, r1, #31
    lsls r1, r1, #1
    orrs r1, r3
include:
    add r6, r3
    adds r7, #1
    lsls r2, r2, #20
    lsrs r2, r2, #20
    lsls r3, r3, #12
    orrs r2, r3
    b store
exclude:
    movw r2, #65535
store:
    strh r2, [r0]
    adds r0, #2
    subs r5, #1
    bne tag
    subs r7, r7, r6
    mov r12, r6
    mov r6, r0
    mov r5, r4
    adds r5, #2
outer:
    ldrh r2, [r5]
    mov r0, r5
inner:
    subs r1, r0, #2
    ldrh r3, [r1]
    cmp r3, r2
    bls insert
    strh r3, [r0]
    mov r0, r1
    cmp r0, r4
    bhi inner
insert:
    strh r2, [r0]
    adds r5, #2
    cmp r5, r6
    blo outer
    mov r0, r4
    mov r1, r7
    bl robust_median
    mov r5, r0
    mov r1, r7
    lsls r1, r1, #1
    adds r0, r4, r1
    mov r1, r12
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


# Median of a sorted u16 array: floor((a[n//2] + a[(n-1)//2])/2).
# Empty groups return 0xFFFF without reading the array. Both an empty low
# group and an empty high group therefore fail the estimator's existing
# nonpositive/rail checks. The two register-offset LDRH instructions are
# encoded explicitly because the local assembler accepts only immediate
# offsets for LDRH. This leaf preserves r4-r12 and uses no stack.
MEDIAN_SOURCE = '''
    cbz r1, empty
    lsrs r2, r1, #1
    lsls r2, r2, #1
    .short 0x5A83          ; ldrh r3, [r0, r2]
    subs r1, #1
    lsrs r1, r1, #1
    lsls r1, r1, #1
    .short 0x5A40          ; ldrh r0, [r0, r1]
    adds r0, r0, r3
    lsrs r0, r0, #1
    bx lr
empty:
    movw r0, #65535
    bx lr
'''


def apply(img):
    if hashlib.sha256(img.data).hexdigest() != PREVIOUS_SHA256:
        raise PatchError('rx-robust requires the complete, exact PN 1.8 profile')
    # This PN 1.5 DFT tail follows `pop {r7, pc}` at 0x0800B582.
    # PN 1.8 has no incoming branches, pointers or PC-relative references.
    if img.read(MEDIAN, 28) != bytes.fromhex('00bf') * 14:
        raise PatchError('robust median requires the audited 28-byte NOP tail')
    compact_mean.apply(img)
    _put(img, MEDIAN, 28, MEDIAN_SOURCE,
         'robust median: audited unreachable DFT NOP tail; no DFT behavior change')
    _put(img, ESTIMATOR, ESTIMATOR_END-ESTIMATOR, ESTIMATOR_SOURCE,
         'robust strength: full-code or exact-union medians; unsuitable comparison guard')
    _put(img, DETECTOR, PUBLISH-DETECTOR, DETECTOR_SOURCE,
         'robust detector: preserve eligibility and raw samples; qualify strength phase')
    _put(img, START_TONE, 34, '''
        ldr r0, =0x2000005A
        cmp r1, #1
        bne normal
        movs r1, #160
        strb r1, [r0]
        movs r0, #100
        b start
    normal:
        strb r1, [r0]
        movs r0, #30
    start:
        strb r0, [r2]
        msr primask, r3
        b.w speaker_tick
    ''', 'robust audio: long uncertain pulse; preserve normal cadence and key ownership')
    img.syms.update(robust_estimate=ESTIMATOR | 1, robust_median=MEDIAN | 1)
    img.robust = True


def register(patch):
    patch('rx-robust', 'Code-conditioned strength and distinct uncertain-reading feedback',
          risk='untested', default=False, group='scan')(apply)
