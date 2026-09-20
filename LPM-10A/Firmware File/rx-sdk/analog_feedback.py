"""Analog cable-comparison feedback, layered on the PN 1.9 signal path.

Retains all 31 DFT bins and the original target-minus-noise eligibility rule.
Accepted margins map to the existing interpolated cadence with a fixed 30 ms
pulse. Eight upper-rail samples produce the existing uncertain-reading pulse.
Analog feedback expires after 100 nominal ms without another accepted window.
The original mains publisher and key confirmation beeps remain independent.
"""
import hashlib

from lpm10rx.image import PatchError

ANALYZER = 0x08009F58
ANALYZER_END = 0x0800A048
SPEAKER_DISPATCH = 0x0800AC56
SPEAKER_END = 0x0800AC7C
PUBLISH = 0x08009F20
GAP_HELPER = 0x0800A048
SCALE = 40
UPPER_RAIL_LIMIT = 8
RECENT = 600


ANALYZER_SOURCE = '''
    push {r3, r4, r5, r6, r7, lr}
    bl sampling_ready
    cmp r0, #0
    beq done
    movs r4, #1
    movs r5, #0
    movs r6, #0
    movs r7, #0
bin:
    mov r0, r4
    bl dft_bin_magnitude
    uxth r0, r0
    add r5, r0
    cmp r4, #1
    bne target
    mov r7, r0
target:
    cmp r4, #17
    bne next
    mov r6, r0
next:
    adds r4, #1
    cmp r4, #32
    blo bin
    subs r5, r5, r6
    subs r5, r5, r7
    uxth r5, r5
    movs r0, #12
    udiv r5, r5, r0
    subs r7, r6, r5
    cmp r7, #10
    ble rejected
    ldr r0, =0x2000006E
    movs r1, #64
    movs r2, #0
    movw r4, #4095
rail:
    ldrh r3, [r0]
    cmp r3, r4
    bne advance
    adds r2, #1
advance:
    adds r0, #2
    subs r1, #1
    bne rail
    cmp r2, #8
    bhs uncertain
    mov r0, r7
    subs r0, #10
    movs r1, #40
    muls r0, r1, r0
    bl analog_gap
    b refresh
uncertain:
    movs r1, #1
    bl analog_publish
refresh:
    mrs r3, primask
    cpsid i
    ldr r0, =0x20000048
    ldrb r1, [r0, #1]
    cbnz r1, restore
    ldr r1, =0x200000EF
    ldrb r1, [r1]
    cmp r1, #2
    bne restore
    movw r1, #600
    strh r1, [r0, #36]
    ldrb r1, [r0, #21]
    cmp r1, #1
    bne gap_ready
    movs r1, #160
gap_ready:
    ldrb r2, [r0, #18]
    cmp r2, r1
    bls restore
    strb r1, [r0, #18]
restore:
    msr primask, r3
    b rearm
rejected:
    movs r1, #0
    bl analog_publish
rearm:
    ldr r0, =0x20000008
    movs r1, #1
    strb r1, [r0]
done:
    pop {r3, r4, r5, r6, r7, pc}
    .pool
'''

SPEAKER_SOURCE = '''
    ldr r0, =0x20000048
    ldrb r0, [r0]
    cmp r0, #2
    beq mains
    bl speaker_tick_mode0
    b.w 0x0800AC7C
mains:
    ldr r0, =0x2000010C
    ldrb r0, [r0]
    bl speaker_tick
    b.w 0x0800AC7C
    .pool
'''


def _put(img, address, size, source, digest, why):
    old = img.read(address, size)
    if hashlib.sha256(old).hexdigest() != digest:
        raise PatchError(f'analog feedback site {address:#x} differs from pinned PN 1.9')
    code = img.assemble_at(address, source, {
        'analog_gap': GAP_HELPER, 'analog_publish': PUBLISH,
    })
    if len(code) > size or len(code) % 2:
        raise PatchError(f'analog feedback code {address:#x}: {len(code)} exceeds {size}')
    img.poke(address, old.hex(), code + bytes.fromhex('00bf')*((size-len(code))//2), why)
    return len(code)


def apply(img):
    if not getattr(img, 'robust', False):
        raise PatchError('analog feedback requires PN 1.9 robust audio and publication')
    # Digests are the two complete original slots, independent of DFT-loop
    # optimization elsewhere. No ADC timer, sample buffer or new RAM is used.
    analyzer_size = _put(img, ANALYZER, ANALYZER_END-ANALYZER, ANALYZER_SOURCE,
        'afbe2b2639b9d120043fb08a64282dea1e9fbb7768ed5f9d2e1c3722081dcd94',
        'Analog comparison: interpolated short pulses, bounded freshness, upper-rail uncertainty')
    dispatch_size = _put(img, SPEAKER_DISPATCH, SPEAKER_END-SPEAKER_DISPATCH, SPEAKER_SOURCE,
        '30a953982e6e5722553271cc54a44adcbe015542fc0214cb7e5dd1796213b1c4',
        'Analog and Digital use guarded repeat scheduling; mains retains its existing speaker path')
    img.analog_feedback = {'analyzer_bytes': analyzer_size, 'dispatch_bytes': dispatch_size}
