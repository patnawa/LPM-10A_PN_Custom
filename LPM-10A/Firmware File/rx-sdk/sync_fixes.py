"""PN 1.10: autodetect the optional Sync32 transmitter waveform.

The existing PN 1.9 detector first searches legacy B6 rotations. On failure,
search the 32 rotations of 0x1F25EB11 with its unchanged 48-sample error limits.
The old exact-match fallback remains available. This is code-phase search,
not sub-slot timing recovery or a change to the ADC sampling rate.

Only a four-byte branch and an unreachable 28-byte TIM1 padding tail change.
The estimator, acquisition, gain GPIO, timers and publication guards remain
byte-identical. The new code cannot take priority over a legacy exact-union
result: even the closest valid pair of legacy matches requires seven edits
to a Sync32 template, beyond the detector's four-error acceptance budget.
"""
import hashlib

from lpm10rx.image import PatchError

PATCHES = {'rx-sync'}
OUTPUT = 'experimental/APP_LPM-10RX_PN1.10-sync.bin'
PREVIOUS_SHA256 = '6128e0a4a0261f3da51bea232c8e431474033f0a09fd24283faa0a743b67fe3e'
SYNC_WORD = 0x1F25EB11
EXTENSION = 0x0800A9D4
EXTENSION_END = 0x0800A9F0
HOOK = 0x08009EEC
PHASE = 0x08009EAC
FALLBACK = 0x08009EF0


SOURCE = f'''
    uxtb r0, r4
    cmp r0, #0xB6
    bne fallback
    movw r4, #{SYNC_WORD & 65535}
    movt r4, #{SYNC_WORD >> 16}
    movs r5, #32
    b.w {PHASE}
fallback:
    ldr r0, [sp, #96]
    cmp r0, #2
    b.w {FALLBACK}
'''


def apply(img):
    if hashlib.sha256(img.data).hexdigest() != PREVIOUS_SHA256:
        raise PatchError('rx-sync requires the complete, exact PN 1.9 profile')
    # TIM1's preceding unconditional branch at 0x0800A9C0 skips its literals
    # and this entire NOP tail, landing at EXTENSION_END. No entry or literal
    # points inside the tail in the pinned parent image (checked in tests).
    if img.read(EXTENSION, 28) != bytes.fromhex('00bf') * 14:
        raise PatchError('rx-sync requires the audited unreachable TIM1 NOP tail')
    if img.read(HOOK, 4) != bytes.fromhex('18980228'):
        raise PatchError('rx-sync legacy fallback entry differs from audited PN 1.9')
    code = img.assemble_at(EXTENSION, SOURCE)
    branch = img.assemble_at(HOOK, f'b.w {EXTENSION}')
    if len(code) != 28 or len(branch) != 4:
        raise PatchError('rx-sync extension does not fit its exact in-place slots')
    img.poke(EXTENSION, ('00bf' * 14), code,
             'Sync32 search: reuse legacy phase loop, then preserve exact-union fallback')
    img.poke(HOOK, '18980228', branch,
             'After all legacy phases, try the optional 32-bit transmitter code')
    img.syms.update(sync_extension=EXTENSION | 1)
    img.sync = True


def register(patch):
    patch('rx-sync', 'Autodetect optional Sync32 code while retaining legacy digital mode',
          risk='untested', default=False, group='scan')(apply)
