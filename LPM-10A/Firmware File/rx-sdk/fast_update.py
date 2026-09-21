"""PN 1.21: Digital re-evaluates every 8 new samples (40 ms) instead of 16 (80 ms).

Applies to the untagged PN 1.19/1.20 image (version tags are applied after the
patch chain, see profiles.apply_profile).

Since PN 1.11 the Digital analyzer snapshots the 48-sample frame, keeps the
newest 32 samples and lets the sampler collect 16 new ones before it runs again
(digital_overlap.py, `overlap_rearm` at 0x0800A018).  Measured on 2026-09-21:
about 9 evaluations per second against ~48 for Analog, which is why Analog
felt more responsive.  PN 1.21 keeps the newest 40 samples and collects 8, so
the detector, the strength estimate and the published rhythm refresh every
40 ms.  The code search still covers all 16 rotations of the full 48-sample
frame; the strength estimate still uses the 16 newest code-verified samples
(one full code period); the first lock after a mode or gate change still needs
a complete 48-sample frame (240 ms).  Detector work per evaluation is unchanged
(a few thousand instructions), so doubling its rate is negligible next to the
Analog DFT.  PN 1.16's 160 ms rejected-window hold now bridges up to three
missed evaluations instead of one; a lost signal still releases within
~200 ms.
"""
import hashlib

from lpm10rx.image import PatchError
import digital_overlap

PATCHES = {'rx-fast-update'}
OUTPUT = 'experimental/APP_LPM-10RX_PN1.21-fast-update.bin'
PARENT_SHA256 = 'e2b85d16ae1ff8c6de08e18b51324f9c657ea40c53895f049fd0050683403849'   # untagged PN 1.19/1.20
PREVIOUS_SHA256 = PARENT_SHA256

RETAINED, NEW = 40, 8
SOURCE = f'''
    subs r0, #96
    subs r1, #{96 - 2 * (48 - RETAINED)}
    movs r2, #{RETAINED}
copy:
    ldrh r3, [r1]
    strh r3, [r0]
    adds r0, #2
    adds r1, #2
    subs r2, #1
    bne copy
    subs r0, #{2 * RETAINED + 19}
    movs r1, #{RETAINED}
    strb r1, [r0]
    subs r0, #83
    movs r1, #1
    strb r1, [r0]
    bx lr
'''


def apply(img):
    if hashlib.sha256(bytes(img.data)).hexdigest() != PARENT_SHA256:
        raise PatchError('rx-fast-update requires the complete, exact PN 1.19 chain')
    old = img.assemble_at(digital_overlap.HELPER, digital_overlap.SOURCE)
    if img.read(digital_overlap.HELPER, len(old)) != old:
        raise PatchError('fast-update: the PN 1.11 overlap helper is not in place')
    code = img.assemble_at(digital_overlap.HELPER, SOURCE)
    if len(code) != len(old):
        raise PatchError('fast-update helper must keep the overlap helper length (the tracking tail follows it)')
    img.poke(digital_overlap.HELPER, old.hex(), code,
             f'Digital overlap: retain {RETAINED} samples, collect {NEW} -> evaluate every {NEW * 5} ms')
    img.fast_update = {'parent_sha256': PARENT_SHA256, 'retained': RETAINED, 'new': NEW}
    if hasattr(img, 'digital_overlap'):
        img.digital_overlap.update(retained=RETAINED, new=NEW)


def register(patch):
    patch('rx-fast-update', 'Digital evaluates every 8 new samples (40 ms) instead of 16',
          risk='untested', default=False, group='scan')(apply)
