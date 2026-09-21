"""PN 1.14: a different speaker pitch per tracing mode, and a mode chirp.

Applies only to the complete, exact PN 1.12 image (the first PN receiver
build confirmed running on hardware, 2026-09-21).

Stock drives the speaker with TIM5 channel 4 PWM (40 kHz) and flips the duty
between 900 and 700 every eighth TIM5 interrupt, so every beep in every mode is
the same 2.5 kHz tone.  The flip cadence lives in TIM5_IRQHandler's dispatch
(`tick & 7 == 0` -> speaker tick).  PN 1.14 replaces that dispatch with a branch
to a helper appended after the image which picks the cadence by mode:

    Digital (mode 0)   every  8 IRQs  -> 2.5 kHz   (unchanged)
    Analog  (mode 1)   every 16 IRQs  -> 1.25 kHz  (one octave lower)
    Mains   (mode 2)   every  8 IRQs  -> 2.5 kHz   (unchanged, keep_alive beeps)

Chirp: a key press starts a 100 ms confirmation beep (keep_alive = 100).  While
that beep still has more than 50 ms to run, the helper uses the *other* mode's
pitch, so entering Digital sounds low->high and entering Analog high->low; the
lamp key chirps in the current mode's direction.  Tracing pulses are 30 ms
(Digital) and 12 ms (Analog), so they never reach the chirp half.  Mains beeps
are unaffected.  The 100 ms boot beep (stock starts in mode 1) chirps high->low.

Only the phase-flip rate changes.  Pulse and gap lengths are millisecond
countdowns in TIM1 and are untouched; the scheduler is entered at most 0.4 ms
later in Analog instead of 0.2 ms.  No RAM is added, the stack is unchanged,
and the helper runs 12-14 instructions per speaker tick.
"""
import hashlib

from lpm10rx.image import PatchError

PATCHES = {'rx-mode-tone'}
OUTPUT = 'experimental/APP_LPM-10RX_PN1.14-mode-tone.bin'
PARENT_SHA256 = '4ea18c52bde25353a9a38dbf46775425860f7859bc2c10e3c908a7bff4044403'
PREVIOUS_SHA256 = PARENT_SHA256

DISPATCH = 0x0800AC50          # TIM5_IRQHandler: `lsls r0, r0, #29` on tick_40khz .. `b.w skip`
DISPATCH_END = 0x0800AC7C      # first instruction after the speaker dispatch (sampler section)
MODE = 0x20000048
KEEP_ALIVE = 0x2000010C
DIGITAL_MASK = 7               # flip every 8 IRQs  -> 2.5 kHz
ANALOG_MASK = 15               # flip every 16 IRQs -> 1.25 kHz
CHIRP_ABOVE_MS = 50            # keep_alive > 50 only inside a 100 ms confirmation beep

HELPER_SOURCE = f'''
    ; r0 = tick_40khz (loaded by the instruction before the dispatch)
    ldr r3, ={MODE:#x}
    ldrb r1, [r3]
    cmp r1, #2
    beq mains
    ldr r2, ={KEEP_ALIVE:#x}
    ldrb r2, [r2]
    cmp r2, #{CHIRP_ABOVE_MS}
    bls base
    movs r2, #1
    eors r1, r2                 ; first half of a confirmation beep: the other mode's pitch
base:
    movs r2, #{DIGITAL_MASK}
    cmp r1, #1
    bne mask
    movs r2, #{ANALOG_MASK}
mask:
    ands r0, r2
    bne done
    bl speaker_tick_mode0
    b done
mains:
    lsls r0, r0, #29
    bne done
    ldr r0, ={KEEP_ALIVE:#x}
    ldrb r0, [r0]
    bl speaker_tick
done:
    b.w {DISPATCH_END:#x}
    .pool
'''


def apply(img):
    if hashlib.sha256(bytes(img.data)).hexdigest() != PARENT_SHA256:
        raise PatchError('rx-mode-tone requires the complete, exact PN 1.12 profile')
    dispatch = img.read(DISPATCH, DISPATCH_END - DISPATCH)
    # lsls r0,r0,#29 / cbnz r0,skip / b .+2 / ldr r0,=mode / ldrb / cmp #2 / beq ... (stock bytes, unchanged by PN 1.12)
    if not dispatch.startswith(bytes.fromhex('4007 98b9 ffe7 0748 0078 0228 03d0')):
        raise PatchError(f'mode-tone: TIM5 speaker dispatch at {DISPATCH:#x} is not the expected code')
    helper = img.extend(64, 'PN 1.14 speaker-pitch helper appended after the image')
    code = img.assemble_at(helper, HELPER_SOURCE)
    if len(code) > 64 or len(code) % 4:
        raise PatchError(f'mode-tone helper is {len(code)} bytes; 64 reserved')
    img.poke(helper, (b'\0' * 64).hex(), code + bytes(64 - len(code)),
             'Speaker cadence by mode: Digital 2.5 kHz, Analog 1.25 kHz, chirp on key beeps')
    jump = img.assemble_at(DISPATCH, f'b.w {helper:#x}')
    filler = bytes.fromhex('00bf') * ((DISPATCH_END - DISPATCH - len(jump)) // 2)
    img.poke(DISPATCH, dispatch.hex(), jump + filler,
             'TIM5 speaker dispatch -> pitch helper (old literal pool becomes nops)')
    img.mode_tone = {
        'parent_sha256': PARENT_SHA256,
        'helper': helper,
        'helper_bytes': len(code),
        'masks': {'digital': DIGITAL_MASK, 'analog': ANALOG_MASK, 'mains': 7},
        'chirp_above_ms': CHIRP_ABOVE_MS,
        'persistent_ram_bytes': 0,
        'additional_stack_bytes': 0,
    }


def register(patch):
    patch('rx-mode-tone', 'Analog one octave lower than Digital; key beeps chirp toward the mode',
          risk='untested', default=False, group='audio')(apply)
