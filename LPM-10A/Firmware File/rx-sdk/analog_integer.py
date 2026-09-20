"""Exact integer DFT magnitude after analog_fast's unchanged Q12 sums.

For any 64 uint16_t samples and the pinned Q12 table, |real|, |imag| are
at most 64*65535 = 4,194,240. Their squared sum N is below 2**45 and is
represented exactly by the old double arithmetic. The old pow(x, 2) uses
its direct multiply shortcut, so its squares are exact as well.

sqrt(N) < 2**23. A non-square integer N lies at least 2**-24 away from an
integer root boundary; a rounded binary64 square root errs at most 2**-31
here. Thus it cannot cross a truncation boundary. Scaling by 2/64 is exact,
and floor(sqrt(N)/32) == isqrt(N)//32. This replacement therefore retains
the previous integer magnitude for every input in the original uint16_t
sample contract, including all real 12-bit ADC inputs. No float error,
threshold retuning, approximation or lookup-table change is introduced.

The restoring integer square root has 23 fixed iterations and no helper
calls. It fits inside the original 114-byte corrected magnitude tail and
preserves the median helper at B584 and retired DFT helpers at B5B0.
"""
import hashlib

import analog_fast
from lpm10rx.image import PatchError

PATCHES = {'analog-integer-dft'}
TAIL = analog_fast.LOOP_END
TAIL_END = analog_fast.TAIL_END
SUMS_READY = TAIL + 20
MAX_COMPONENT = 64*65535

SOURCE = '''
    .byte 0x8d,0xe8,0x70,0x00  ; stm.w sp,{r4,r5,r6}, no writeback
    ldr r2, [sp, #28]
    .byte 0x82,0xfb,0x02,0x01  ; smull r0,r1,r2,r2: signed real square
    ldr r2, [sp, #24]
    .byte 0x82,0xfb,0x02,0x23  ; smull r2,r3,r2,r2: signed imag square
    adds r0, r0, r2
    .short 0x4159              ; adcs r1,r3: exact unsigned 64-bit N
    movs r2, #0                ; 64-bit partial root, low/high
    movs r3, #0
    movs r4, #0                ; first test bit = 1 << 44
    movw r5, #0x1000
loop:
    mov r6, r2
    mov r7, r3
    adds r6, r6, r4
    .short 0x416F              ; adcs r7,r5: trial = partial root + test bit
    lsrs r3, r3, #1
    .byte 0x5f,0xea,0x32,0x02  ; rrxs r2,r2: partial root >>= 1
    cmp r1, r7
    bhi accept
    blo advance
    cmp r0, r6
    blo advance
accept:
    subs r0, r0, r6
    .short 0x41B9              ; sbcs r1,r7: N -= trial
    adds r2, r2, r4
    .short 0x416B              ; adcs r3,r5: partial root += test bit
advance:
    lsls r6, r5, #30
    lsrs r4, r4, #2
    orrs r4, r6
    lsrs r5, r5, #2
    mov r6, r4
    orrs r6, r5
    bne loop
    mov r0, r2                ; root < 2**23, so the high word is zero
    lsrs r0, r0, #5           ; unchanged 2/64 magnitude scaling, truncate
    .byte 0x9d,0xe8,0x70,0x00 ; restore r4-r6; original prologue owns r7
    add sp, #40
    .byte 0xbd,0xec,0x02,0x8b ; vpop {d8}, as in the existing epilogue
    pop {r7, pc}
'''


def apply(img):
    if not getattr(img, 'analog_fast', None):
        raise PatchError('analog-integer requires analog-fast-dft first')
    # Pin the loop too: the proof requires exactly the audited table products.
    code = img.assemble_at(analog_fast.LOOP, analog_fast.SOURCE)
    loop = code + bytes.fromhex('00bf') * ((analog_fast.LOOP_END-analog_fast.LOOP-len(code))//2)
    if img.read(analog_fast.LOOP, len(loop)) != loop:
        raise PatchError('analog-integer requires the exact analog-fast loop')
    for region in ((TAIL, TAIL_END), (analog_fast.TABLE, analog_fast.TABLE+512)):
        start, end = region
        if hashlib.sha256(img.read(start, end-start)).hexdigest() != analog_fast.GUARDS[region]:
            raise PatchError(f'analog-integer prerequisite differs at {start:#x}')
    code = img.assemble_at(TAIL, SOURCE)
    size = TAIL_END-TAIL
    if len(code) > size or len(code) % 2:
        raise PatchError(f'analog-integer tail needs {len(code)} bytes; only {size} available')
    img.poke(TAIL, img.read(TAIL, size).hex(),
             code + bytes.fromhex('00bf') * ((size-len(code))//2),
             'DFT: exact 64-bit squares and integer sqrt replace software-double magnitude')
    img.analog_integer = {'tail_bytes': len(code), 'persistent_ram_bytes': 0,
                          'additional_stack_bytes': 0, 'maximum_root_iterations': 23}


def register(patch):
    @patch('analog-integer-dft', 'Exact integer DFT magnitude with bounded work',
           risk='untested', default=False, group='measure')
    def integer(img):
        apply(img)
