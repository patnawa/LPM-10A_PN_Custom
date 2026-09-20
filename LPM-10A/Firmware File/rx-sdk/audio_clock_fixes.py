"""PN 1.13 diagnostic: drive BEEP/GAP countdowns from the TIM5 audio clock.

Only the exact PN 1.12 parent is accepted. TIM1 retains RECENT, housekeeping,
keys and sampler ownership. Every fortieth TIM5 interrupt supplies one audio
countdown tick; the existing speaker dispatch already runs every eighth IRQ.
No new RAM or stack storage is allocated. This is not a proven hardware-cause fix.
"""
import hashlib

from lpm10rx.image import PatchError

PATCHES = {'rx-audio-clock'}
OUTPUT = 'experimental/APP_LPM-10RX_PN1.13-audio-clock.bin'
PARENT_SHA256 = '4ea18c52bde25353a9a38dbf46775425860f7859bc2c10e3c908a7bff4044403'
PREVIOUS_SHA256 = PARENT_SHA256
TIM1_SITE = 0x0800A9B8
TIM1_END = 0x0800A9C4
HELPER = 0x0800A9D4
HELPER_END = 0x0800AA1E
DISPATCH = 0x0800AC56
DISPATCH_END = 0x0800AC7C
COUNTER = 0x20000100
BEEP = 0x2000010C
GAP = 0x2000005A

GUARDS = {
    (TIM1_SITE, TIM1_END): '2dc5bb7abef9044f07c264a36d7e652c9018a8df7bf2666d78c701d386c2a59f',
    (HELPER, HELPER_END): '129ea1b1cee79152f9ef33a75d7777c744a98814b1ed08a59c02d15aee9aded8',
    (DISPATCH, DISPATCH_END): '6b67b3baed99cda4d819d84cd4ddbcc1b6f85895f0d43ca10ba2fb9515a5cc1f',
}

HELPER_SOURCE = '''
    ldr r0, =0x20000100
    ldr r0, [r0]
    movs r1, #40
    udiv r2, r0, r1
    muls r2, r1, r2
    cmp r2, r0
    bne done
    mrs r3, primask
    cpsid i
    ldr r0, =0x2000010C
    ldrb r1, [r0]
    cbz r1, gap
    subs r1, #1
    strb r1, [r0]
    cbnz r1, restore
gap:
    ldr r0, =0x2000005A
    ldrb r1, [r0]
    cbz r1, restore
    subs r1, #1
    strb r1, [r0]
restore:
    msr primask, r3
done:
    bx lr
    .pool
'''

DISPATCH_SOURCE = '''
    bl audio_countdown
    ldr r0, =0x20000048
    ldrb r0, [r0]
    cmp r0, #2
    beq mains
    bl speaker_tick_mode0
    b 0x0800AC7C
mains:
    ldr r0, =0x2000010C
    ldrb r0, [r0]
    bl speaker_tick
    b 0x0800AC7C
    .pool
'''


def apply(img):
    if hashlib.sha256(bytes(img.data)).hexdigest() != PARENT_SHA256:
        raise PatchError('rx-audio-clock requires the complete, exact PN 1.12 profile')
    for (start, end), digest in GUARDS.items():
        if hashlib.sha256(img.read(start, end-start)).hexdigest() != digest:
            raise PatchError(f'audio-clock predecessor differs at {start:#x}')
    sources = (
        (TIM1_SITE, TIM1_END, 'nop\nnop\nnop\nnop\nb.w 0x0800AA1E'),
        (HELPER, HELPER_END, HELPER_SOURCE),
        (DISPATCH, DISPATCH_END, DISPATCH_SOURCE),
    )
    writes = []
    lengths = {}
    for start, end, source in sources:
        code = img.assemble_at(start, source, {'audio_countdown': HELPER})
        if len(code) > end-start or len(code) % 2:
            raise PatchError(f'audio-clock code {start:#x}: {len(code)} exceeds {end-start}')
        lengths[start] = len(code)
        writes.append((start, end, code + bytes.fromhex('00bf')*((end-start-len(code))//2)))
    for start, end, code in writes:
        img.poke(start, img.read(start, end-start).hex(), code,
                 'Audio clock: TIM5 owns BEEP/GAP countdown; TIM1 retains other state')
    img.audio_clock = {
        'parent_sha256': PARENT_SHA256,
        'code_lengths': lengths,
        'helper': HELPER,
        'tim5_irqs_per_audio_tick': 40,
        'persistent_ram_bytes': 0,
        'additional_stack_bytes': 0,
        'wrap_policy': 'counter modulo 40; one 16-IRQ interval at uint32 wrap',
    }


def register(patch):
    patch('rx-audio-clock', 'Diagnostic BEEP/GAP countdown from the TIM5 audio clock',
          risk='untested', default=False, group='reliability')(apply)
