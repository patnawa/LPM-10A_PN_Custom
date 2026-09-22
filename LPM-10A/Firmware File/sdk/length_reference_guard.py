"""Keep a dialled Length REF pending until a result actually calibrates NVP.

PN2.23R consumes the one-shot reference after every completed measurement,
including an all-zero result on which its solver does nothing. This overlay
preserves the reference for the next usable measurement. Numerical policy,
supported partial results, and historical profile builders stay unchanged.
"""
import hashlib

from lpm10a.image import PatchError
from lpm10a.thumb import assemble
from length_ref_anytime import RESULT_SITE


# The existing solver returns zero on either no-result path, and leaves the
# NVP settings address in r0 after its successful store. Pin the complete
# audited body, including literals, before relying on this internal ABI.
SOLVER_BYTES = 60
SOLVER_SHA256 = '3a30da73679b9c91544b5d12cec12e5758514d9e5b32075f15fae84a54bd7020'
RESULT_BYTES = 68
RESULT_SHA256 = 'e94000894669da663f54fb366a2a99d0bdbfce772762d95f75d3878f947c0551'


def install(img):
    """Append and select the guarded result hook on the audited R baseline."""
    lr, previous = img.length_reference, img.length_ref_anytime
    solver, old_result = lr['solve'], previous['result']
    expected_call = assemble(RESULT_SITE, f'bl {old_result}')
    if img.read(RESULT_SITE, 4) != expected_call:
        raise PatchError('Length REF guard requires the original reference result hook')
    for address, size, digest in ((solver, SOLVER_BYTES, SOLVER_SHA256),
                                  (old_result, RESULT_BYTES, RESULT_SHA256)):
        if hashlib.sha256(img.read(address, size)).hexdigest() != digest:
            raise PatchError('Length REF guard requires the audited solver and result ABI')

    prepare = img.emit_code('''
        prepare:
            push {r4, lr}
            ldr r0, =ADJ
            ldrb r0, [r0]
            cmp r0, #2
            bne no_solve
            ldr r4, =PENDING
            ldrb r0, [r4]
            cmp r0, #0
            beq no_solve
            bl SOLVE
            cmp r0, #0
            beq no_solve
            movs r0, #0
            strb r0, [r4]
            movs r0, #1
            pop {r4, pc}
        no_solve:
            movs r0, #0
            pop {r4, pc}
    ''', extra_syms=dict(ADJ=img.adj_target, PENDING=previous['pending'],
                         SOLVE=solver | 1),
        why='Length REF: pure guarded solve for atomic result publication')
    result = img.emit_code(f'''
        result:
            push {{r4, lr}}
            bl {prepare}
            mov r4, r0
            movs r2, #0
            movs r1, #0
            movs r0, #0x1A
            bl GUI_MSG_SEND
            cmp r4, #0
            beq done
            movs r2, #0
            movs r1, #0
            movs r0, #0x3D
            bl GUI_MSG_SEND
        done:
            pop {{r4, pc}}
    ''',
        why='Length REF: consume a pending reference only after NVP is actually solved')
    img.poke(RESULT_SITE, expected_call.hex(), assemble(RESULT_SITE, f'bl {result}'),
             'Length REF: retain pending calibration after an unusable result')
    img.length_reference_guard = dict(prepare=prepare, result=result, solver=solver, old_result=old_result,
                                      site=RESULT_SITE, ram_bytes=0)
    return img.length_reference_guard
