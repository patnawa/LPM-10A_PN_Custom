"""RX audit: publish completed buffer clearing last; avoid DFT integer overflow."""
import hashlib
from lpm10rx.image import PatchError

PATCHES = {'mains-sampler-publish-last', 'dft-square-overflow'}
OUTPUT = 'experimental/APP_LPM-10RX_PN1.5-audit.bin'


def register(patch):
    @patch('mains-sampler-publish-last', 'Clear the mains sample buffer before rearming TIM5',
           risk='untested', default=False, group='reliability')
    def mains(img):
        site, size = 0x080086F2, 26
        original = bytes.fromhex('40f20800 c2f20000 0121 0170 40f26e00 c2f20000 8021 fef721fc')
        code = img.assemble_at(site, '''
            movw r0, #0x6E
            movt r0, #0x2000
            movs r1, #128
            bl __aeabi_memclr
            movw r0, #8
            movt r0, #0x2000
            movs r1, #1
            strb r1, [r0]
        ''')
        if len(code) != size:
            raise PatchError('mains rearm must retain its 26-byte footprint')
        img.poke(site, original.hex(), code, 'publish sampling_active only after shared buffer is cleared')

    @patch('dft-square-overflow', 'Keep squared DFT components in double precision until final magnitude',
           risk='untested', default=False, group='measure')
    def dft(img):
        # The initial real-component pow() and saved d8=2.0 remain in place.
        # Original converted each square to signed int32, then added as int32.
        # A 1450-count bin-centered cosine already exceeds INT32_MAX.
        site, size = 0x0800B52C, 116
        original = img.read(site, size)
        if hashlib.sha256(original).hexdigest() != 'dc9562ec5b62b6a6f99f88afdc4a226a12ed95ccefd6ff7975044301e78485f1':
            raise PatchError('DFT arithmetic is not the audited vendor routine')
        # The global builder pins the vendor image; also reject patch overlap.
        if original != img.original[site-0x08006800:site-0x08006800+size]:
            raise PatchError('DFT arithmetic was already modified')
        code = img.assemble_at(site, '''
            .byte 0x51,0xEC,0x10,0x0B   ; vmov r0,r1,d0 (real square)
            str r0, [sp]
            str r1, [sp, #4]
            ldr r0, [sp, #24]
            bl __aeabi_i2d
            .byte 0x41,0xEC,0x10,0x0B   ; vmov d0,r0,r1
            .byte 0xB0,0xEE,0x48,0x1A   ; vmov.f32 s2,s16
            .byte 0xF0,0xEE,0x68,0x1A   ; vmov.f32 s3,s17 (d1 = d8 = 2.0)
            bl pow
            .byte 0x51,0xEC,0x10,0x0B   ; vmov r0,r1,d0 (imaginary square)
            ldr r2, [sp]
            ldr r3, [sp, #4]
            bl __aeabi_dadd
            .byte 0x41,0xEC,0x10,0x0B   ; vmov d0,r0,r1
            bl sqrt
            .byte 0x51,0xEC,0x10,0x0B   ; vmov r0,r1,d0
            mov r2, r0
            mov r3, r1
            bl __aeabi_dadd            ; 2 * magnitude, as in the vendor scale
            movs r2, #0
            movw r3, #0
            movt r3, #0x4050           ; denominator 64.0 in r2:r3
            bl __aeabi_ddiv
            bl __aeabi_d2iz            ; only the final magnitude is integer
            add sp, #40
            .byte 0xBD,0xEC,0x02,0x8B   ; vpop {d8}
            pop {r7, pc}
        ''')
        if len(code) > size or len(code) % 2:
            raise PatchError('DFT arithmetic exceeds its original footprint')
        code += bytes.fromhex('00bf') * ((size-len(code))//2)
        img.poke(site, original.hex(), code, 'DFT: no signed int32 square/sum truncation before sqrt')
