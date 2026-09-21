"""PN 1.16: bridge single rejected windows instead of cutting the audio at once.

Applies only to the complete, exact PN 1.15 image.

Since PN 1.7 a rejected window clears the published quiet interval (0x2000005D)
immediately, so the repeat scheduler stops on the very next tick.  That killed
the stock ~1 s tail, but at a marginal signal Digital windows alternate between
accepted and rejected every 80 ms and the owner hears it as choppy
("ขาดๆ หายๆ", 2026-09-21 with PN 1.15).

PN 1.16 changes only the shared publisher (0x08009F20, used by Digital and
Analog): a rejected window now keeps the last interval and instead clamps the
RECENT countdown (0x2000006C, 1 ms ticks, audio needs > 500) to

    Digital  500 + 160 ms   (one missed 80 ms update is bridged, two are not)
    Analog   500 +  60 ms   (windows come every ~21 ms)

so a signal that is really gone still stops within ~240 ms (Digital: <= 80 ms to
the first rejected window + 160 ms) or ~80 ms (Analog), while an intermittent
match keeps a steady rhythm.  Accepted windows behave exactly as before (new
interval, RECENT = 800; Analog then trims it to 600 itself).  The publisher moves
to an appended helper; the old slot holds a branch.  No RAM is added.
"""
import hashlib

from lpm10rx.image import PatchError

PATCHES = {'rx-release-hold'}
OUTPUT = 'experimental/APP_LPM-10RX_PN1.16-release-hold.bin'
PARENT_SHA256 = '2363b465a8741757b3025a62b9c64523b86700e5869c988382ff8d58e7b014ad'
PREVIOUS_SHA256 = PARENT_SHA256

PUBLISH = 0x08009F20
PUBLISH_END = 0x08009F58
STATE = 0x20000048             # mode; +1 mode request; +0x15 published interval; +0x24 RECENT; +0xA7 gate state
AUDIO_RECENT_MIN = 500
DIGITAL_HOLD_MS = 160
ANALOG_HOLD_MS = 60

HELPER_SOURCE = f'''
    mrs r3, primask
    cpsid i
    ldr r2, ={STATE:#x}
    ldrb r0, [r2, #1]
    cmp r0, #0
    bne done                    ; a mode change is pending: publish nothing
    mov r0, r2
    adds r0, #0xA7
    ldrb r0, [r0]
    cmp r0, #2
    bne done                    ; gate not open
    cmp r1, #0
    beq rejected
    strb r1, [r2, #0x15]        ; accepted: new quiet interval (1 = uncertain)
    movw r0, #800
    strh r0, [r2, #0x24]
    b done
rejected:
    ldrh r0, [r2, #0x24]        ; RECENT
    ldrb r1, [r2]               ; mode
    cmp r1, #0
    bne analog
    movw r1, #{AUDIO_RECENT_MIN + DIGITAL_HOLD_MS}
    b clamp
analog:
    movw r1, #{AUDIO_RECENT_MIN + ANALOG_HOLD_MS}
clamp:
    cmp r0, r1
    bls done                    ; already closer to release than the hold
    strh r1, [r2, #0x24]
done:
    msr primask, r3
    bx lr
    .pool
'''


def apply(img):
    if hashlib.sha256(bytes(img.data)).hexdigest() != PARENT_SHA256:
        raise PatchError('rx-release-hold requires the complete, exact PN 1.15 profile')
    old = img.read(PUBLISH, PUBLISH_END - PUBLISH)
    # mrs/cpsid/ldr r2,=state/ldrb r0,[r2,#1] ... strb r1,[r2,#0x15]: the PN 1.7 publisher
    if not (old.startswith(bytes.fromhex('eff31083 72b6 094a 5078')) and bytes.fromhex('5175 0029') in old):
        raise PatchError(f'release-hold: publisher at {PUBLISH:#x} is not the expected PN 1.7 code')
    helper = img.extend(96, 'PN 1.16 publisher with rejected-window hold appended after the image')
    code = img.assemble_at(helper, HELPER_SOURCE)
    if len(code) > 96 or len(code) % 4:
        raise PatchError(f'release-hold helper is {len(code)} bytes; 96 reserved')
    img.poke(helper, (b'\0' * 96).hex(), code + bytes(96 - len(code)),
             'Publisher: accepted -> interval + RECENT 800; rejected -> keep interval, clamp RECENT to 660/560')
    jump = img.assemble_at(PUBLISH, f'b.w {helper:#x}')
    img.poke(PUBLISH, old.hex(), jump + bytes.fromhex('00bf') * ((len(old) - len(jump)) // 2),
             'publisher slot -> appended publisher (old code and pool become nops)')
    img.release_hold = {
        'parent_sha256': PARENT_SHA256,
        'helper': helper,
        'helper_bytes': len(code),
        'digital_hold_ms': DIGITAL_HOLD_MS,
        'analog_hold_ms': ANALOG_HOLD_MS,
        'persistent_ram_bytes': 0,
        'additional_stack_bytes': 0,
    }


def register(patch):
    patch('rx-release-hold', 'Rejected windows hold the last rhythm 160 ms (Digital) / 60 ms (Analog)',
          risk='untested', default=False, group='audio')(apply)
