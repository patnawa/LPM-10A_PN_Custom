"""Opt-in gain/sample ownership correction over the exact untagged PN 1.23.

The 500 ms AGC runs in TIM1, so it can interrupt a main-context analyzer.
Changing the driven gain invalidates the current sample generation before the
gain metadata or GPIO changes. Existing publisher guards reject that window;
the main boundary then restarts acquisition without retaining old-gain samples.
An unchanged effective gain leaves acquisition and feedback alone.

Mains uses the separate PD15 input, outside the gain stage. Its shared sample
buffer must not drive automatic range changes. Knob changes still take effect.
This module deliberately has no registered release profile. Run
``python auto_range_freshness.py`` for a dry build, or call ``build_candidate()``
for an Image tagged PN1.23F. Neither entry point writes or flashes a binary.
"""
import hashlib
from pathlib import Path

import auto_range
from lpm10rx.image import PatchError

PARENT_SHA256 = '845377217a991fb1c042112aa716e1219901b0c4d3be7a824ffaf0f45db2d7d5'
HELPER = 0x0800CFC8
SIZE = 192
GATE_STATE = 0x200000EF
CANDIDATE_TAG = 'PN1.23F'

SOURCE = auto_range.SOURCE.replace(
    'reset:\n    strb r0, [r2]',
    f'''reset:
    cmp r3, r0
    beq unchanged
    ldr r4, ={GATE_STATE:#x}
    movs r1, #0
    strb r1, [r4]               ; invalidate before publishing a new gain
unchanged:
    strb r0, [r2]''',
).replace(
    'keep:\n    push {r2}',
    '''keep:
    ldr r4, =0x20000048
    ldrb r4, [r4]
    cmp r4, #2
    beq out                    ; mains data does not pass through this gain stage
    push {r2}''',
).replace(
    'changed:\n    strb r3, [r2]',
    f'''changed:
    ldr r4, ={GATE_STATE:#x}
    movs r1, #0
    strb r1, [r4]               ; main owns resetting sampler indices and ACTIVE
    strb r3, [r2]''',
)


def apply(img):
    if hashlib.sha256(bytes(img.data)).hexdigest() != PARENT_SHA256:
        raise PatchError('auto-range freshness requires the exact untagged PN 1.23 chain')
    old = img.assemble_at(HELPER, auto_range.SOURCE)
    old += bytes(SIZE-len(old))
    if img.read(HELPER, SIZE) != old:
        raise PatchError('auto-range freshness helper differs from PN 1.23')
    code = img.assemble_at(HELPER, SOURCE)
    if len(code) > SIZE or len(code) % 2:
        raise PatchError(f'auto-range freshness needs {len(code)} bytes; {SIZE} available')
    img.poke(HELPER, old.hex(), code + bytes(SIZE-len(code)),
             'Auto-range: invalidate windows before gain changes; ignore mains amplitude')
    img.auto_range_freshness = {'helper': HELPER, 'helper_bytes': len(code),
                               'persistent_ram_bytes': 0, 'additional_stack_bytes': 0}


def build_candidate():
    """Build a distinctly tagged candidate from stock; leave all files untouched."""
    from lpm10rx.image import Image, STOCK_NAME
    from lpm10rx import symbols
    import profiles
    import rx_patches
    import version_tag

    img = Image(str(Path(__file__).resolve().parent.parent / STOCK_NAME))
    if hashlib.sha256(bytes(img.data)).hexdigest() != symbols.STOCK_SHA256:
        raise PatchError('auto-range freshness candidate requires the pinned RX stock image')
    wanted = profiles.PROFILES['pn1.23'].patch_ids()
    for patch in rx_patches.REGISTRY:
        if patch.pid in wanted:
            patch(img)
    apply(img)
    version_tag.apply(img, CANDIDATE_TAG)
    return img


if __name__ == '__main__':
    candidate = build_candidate()
    print(f'{candidate.version_tag} experimental candidate: {len(candidate.data)} bytes')
    print(f'SHA-256: {hashlib.sha256(bytes(candidate.data)).hexdigest()}')
    print('Dry run only. Hardware validation pending; no image written or flashed.')
