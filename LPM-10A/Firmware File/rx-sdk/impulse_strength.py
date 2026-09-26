"""Use all verified triplets in a fitted Digital frame to reject sparse impulses.

The detector owns an immutable 48-sample snapshot. Its full phase fit leaves
r5 in 1..8 and passes snapshot+64; the exact-only fallback leaves r5=0 and
passes its selected 16-sample span. Only the full-fit path may use all 48
samples: unverified surroundings of an exact-only span are never measured.
PN1.30's edge-canceling arithmetic and ADC rail policy are preserved.
"""
import clean_strength as cs
from lpm10rx import symbols
from lpm10rx.image import PatchError


DISPATCH = '''
    movs r2, #16
    cmp r5, #0
    beq selected
    subs r0, #64
    movs r2, #48
selected:
'''

# Keep the audited edge compensation but enlarge the private arrays from four
# to twelve triplets. The loop length is explicit and stored on this frame.
SOURCE = DISPATCH + cs.ESTIMATOR_SOURCE.replace(
    'push {r4, r5, r6, r7, lr}', 'push {r3, r4, r5, r6, r7, lr}'
).replace('pop {r4, r5, r6, r7, pc}', 'pop {r3, r4, r5, r6, r7, pc}'
).replace(
    'sub sp, #16', 'sub sp, #56\n    str r2, [sp, #48]\n    subs r2, #1\n    str r2, [sp, #52]'
).replace('cmp r5, #15', 'ldr r3, [sp, #52]\n    cmp r5, r3'
).replace('cmp r5, #16', 'ldr r3, [sp, #48]\n    cmp r5, r3'
).replace('[r7, #8]', '[r7, #24]').replace('adds r0, #8', 'adds r0, #24'
).replace('add sp, #16', 'add sp, #56')


def install(img):
    info = getattr(img, 'clean_strength', None)
    if info is None or hasattr(img, 'impulse_strength'):
        raise PatchError('impulse strength requires PN1.30 once')
    site = cs.ESTIMATE_CALL
    expected = img.assemble_at(site, f'bl {info["estimator"]}')
    # r5 and the snapshot pointer form a private call-site contract. Validate
    # both full-fit and fallback control flow before extending the image.
    guards = {
        site: expected,
        0x08009EE2: bytes.fromhex('013d'),
        0x08009EF4: img.assemble_at(0x08009EF4, 'mov r0, sp\n adds r0, #64\n mov r1, r4'),
        0x0800A042: img.assemble_at(0x0800A042, 'ldr r0, [sp, #100]\n b 0x08009ef8'),
    }
    for address, value in guards.items():
        if img.read(address, len(value)) != value:
            raise PatchError(f'impulse strength: unexpected call contract at {address:#x}')
    start = symbols.APP_BASE + len(img.data)
    code = img.assemble_at(start, SOURCE)
    code += bytes(-len(code) % 4)
    if start + len(code) > symbols.EXTEND_LIMIT:
        raise PatchError('impulse strength exceeds application flash limit')
    img.extend(len(code), 'Impulse-resistant edge-compensated Digital strength')
    img.poke(start, bytes(len(code)).hex(), code, 'Estimate fitted frames from eleven/twelve independent triplets')
    img.poke(site, expected.hex(), img.assemble_at(site, f'bl {start}'), 'Use robust full-fit strength, preserve exact-only span')
    img.impulse_strength = {'estimator': start, 'helper_bytes': len(code), 'sites': (site,),
                            'additional_stack_bytes': 44, 'persistent_ram_bytes': 0}
    return img
