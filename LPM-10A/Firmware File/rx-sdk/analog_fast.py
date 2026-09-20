"""Bit-exact DFT inner-loop optimization for the PN 1.9 receiver ancestry.

The 64-sample loop computes the same signed Q12 table products, truncates
each toward zero, and accumulates in the same order. The existing corrected
double-precision square/root/scaling tail is untouched. There is no new RAM,
sample window, threshold, clock, interrupt-mask or feedback-policy change.

The original stack frame has 24 unused bytes during accumulation. They save
r4-r6/r8-r10, which are restored before the unchanged arithmetic tail. r7
and d8 retain their existing prologue/epilogue preservation.
"""
import hashlib

from lpm10rx.image import PatchError

PATCHES = {'analog-fast-dft'}
DFT = 0x0800B4A0
LOOP = 0x0800B4A8
LOOP_END = 0x0800B512
TAIL_END = 0x0800B584
TABLE = 0x0800CB94
# No call remains to these two private helpers after apply(). Another patch
# may reclaim this region, but only after validating this patch's application.
RETIRED_HELPERS = (0x0800B5B0, 0x0800B630)
RETIRED_HELPERS_SHA256 = 'c84ea9413b0551292dedb3f3fff870b5a6c53492232cbe2dfc30860ca73113da'

GUARDS = {
    (DFT, LOOP): 'bc06addf724fce539ec111fe484b9f595d023cafb56ea3366eeff3c468da4a57',
    (LOOP, LOOP_END): '3ccb6dc662858b3477aa498d686cab9ea5bd170690794f074ea60d1e94bb3652',
    (LOOP_END, TAIL_END): 'f51d69af633a5f2d50cccafdacbf2e5ddf13e9d41927f38c01402e85ac91a482',
    RETIRED_HELPERS: RETIRED_HELPERS_SHA256,
    (TABLE, TABLE + 512): 'f0b153e39d92fe4efd1974a7f031f2f5552130a69f0431d0e421d22683941877',
}

SOURCE = '''
    .byte 0x8d,0xe8,0x70,0x07  ; stm.w sp,{r4,r5,r6,r8,r9,r10}; no writeback
    uxtb r7, r0                ; original k was stored as uint8_t
    ldr r4, =0x2000006E
    ldr r5, =0x0800CB94
    mov r10, r4
    movs r0, #128
    add r10, r0
    movs r6, #0                ; phase = (sample index * k) & 63
    mov r8, r6                 ; signed real sum
    mov r9, r6                 ; signed imaginary sum
loop:
    ldrh r0, [r4]
    adds r4, #2
    lsls r1, r6, #3
    adds r1, r5, r1
    ldr r2, [r1, #4]
    ldr r1, [r1]
    muls r1, r0, r1
    muls r2, r0, r2
    .short 0x17CB              ; asrs r3,r1,#31
    lsrs r3, r3, #20           ; 4095 if product negative, else 0
    adds r1, r1, r3
    .short 0x1309              ; asrs r1,r1,#12; signed divide toward zero
    add r8, r1
    .short 0x17D3              ; asrs r3,r2,#31
    lsrs r3, r3, #20
    adds r2, r2, r3
    .short 0x1312              ; asrs r2,r2,#12
    add r9, r2
    adds r6, r6, r7
    movs r0, #63
    ands r6, r0
    .short 0x4554              ; cmp r4,r10
    bne loop
    mov r0, r8
    str r0, [sp, #28]
    mov r0, r9
    str r0, [sp, #24]
    .byte 0x9d,0xe8,0x70,0x07  ; ldm.w sp,{r4,r5,r6,r8,r9,r10}; no writeback
    b 0x0800B512               ; unchanged double-precision magnitude tail
'''


def apply(img):
    for (start, end), expected in GUARDS.items():
        if hashlib.sha256(img.read(start, end-start)).hexdigest() != expected:
            raise PatchError(f'analog-fast DFT prerequisite differs at {start:#x}')
    code = img.assemble_at(LOOP, SOURCE)
    size = LOOP_END - LOOP
    if len(code) > size or len(code) % 2:
        raise PatchError(f'analog-fast loop needs {len(code)} bytes; only {size} available')
    img.poke(LOOP, img.read(LOOP, size).hex(),
             code + bytes.fromhex('00bf') * ((size-len(code)) // 2),
             'DFT: inline exact signed Q12 products and accumulate in registers')
    img.analog_fast = {'loop_bytes': len(code), 'retired_helpers': RETIRED_HELPERS,
                       'persistent_ram_bytes': 0, 'additional_stack_bytes': 0}


def register(patch):
    @patch('analog-fast-dft', 'Bit-exact DFT loop with fewer memory accesses and calls',
           risk='untested', default=False, group='measure')
    def fast(img):
        apply(img)
