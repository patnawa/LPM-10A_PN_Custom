"""PN1.23G candidate: preserve confirmed Digital rhythm during gain acquisition.

PN1.23F correctly discards a window when its gain changes, but also clears
the last confirmed feedback. Digital then needs 240 ms to acquire 48 fresh
samples (Analog needs 21 ms). Keep the existing Digital feedback countdown
across gain-only resets; never renew it until a new window is accepted.

GATE_STATE 3 means a gain-invalidated, previously open Digital acquisition.
The existing readiness, publisher and speaker guards still require state 2.
Only main resets sampling and returns it to 2. Mode changes and gate closures
retain the original full reset, as do all Analog/Mains transitions. No RAM is
added, no samples are reused across gains, and detection thresholds are intact.

python digital_gain_continuity.py --write
"""
import argparse
import hashlib
from pathlib import Path

import auto_range_freshness
from lpm10rx.container import wrap
from lpm10rx.image import PatchError
from lpm10rx import symbols
import sampling_fixes
import version_tag


PARENT_SHA256 = '0c000550e4143032070bed34ab62ff24ec18fe60d53824a81ecb3d77c4e7e8c0'
CANDIDATE_TAG = 'PN1.23G'
GAIN_INVALID = 3
OUTPUT = 'APP_LPM-10RX_PN1.23G-digital-gain.bin'
UPDATE = 'APP_LPM-10RX_PN1.23G-digital-gain-update.bin'

INVALIDATE_SOURCE = '''
    ldrb r1, [r4]             ; r4 = GATE_STATE, r0/r2/r3 stay live in AGC
    cmp r1, #3
    beq done                 ; repeated gain change cannot renew feedback
    cmp r1, #2
    bne clear                ; startup or a gate transition: do not bridge
    ldr r1, =0x20000048
    ldrb r1, [r1]
    cmp r1, #0
    bne clear                ; Analog and Mains retain PN1.23F behavior
    movs r1, #3
    b store
clear:
    movs r1, #0
store:
    strb r1, [r4]            ; invalidate before AGC publishes gain or GPIO
done:
    bx lr
'''

# Same ownership transition as sampling_fixes.BOUNDARY. The only new path
# skips feedback clearing for an open Digital gain change. Pending mode
# requests first set GATE_STATE=0, excluding that path.
BOUNDARY_SOURCE = '''
    push {r4, r5, r6, lr}
    bl iwdg_reload
    mrs r6, primask
    cpsid i
    ldr r4, =0x20000048
    ldr r5, =0x200000EE
    ldrb r2, [r4, #1]
    cmp r2, #0
    beq mode_ready
    subs r2, #1
    strb r2, [r4]
    movs r0, #0
    strb r0, [r5, #1]
    strb r0, [r4, #1]
mode_ready:
    ldrb r2, [r4]
    movs r1, #2
    cmp r2, #2
    beq gate_ready
    ldr r0, =0x20000068
    cmp r2, #0
    beq digital_gate
    adds r0, #2
    ldrh r0, [r0]
    cmp r0, #1
    bhs gate_ready
    b closed
digital_gate:
    ldrh r0, [r0]
    cmp r0, #2
    bhs gate_ready
closed:
    movs r1, #1
gate_ready:
    ldrb r0, [r5, #1]
    cmp r0, r1
    beq done
    movs r3, #0
    cmp r0, #3
    bne reset
    cmp r2, #0
    bne reset
    cmp r1, #2
    bne reset
    movs r3, #1
reset:
    strb r1, [r5, #1]
    movs r0, #0
    strb r0, [r5]
    strh r0, [r4, #16]
    strb r0, [r4, #19]
    strb r0, [r4, #20]
    cmp r3, #0
    bne feedback_kept
    strb r0, [r4, #18]
    strb r0, [r4, #21]
    ldr r2, =0x2000006C
    strh r0, [r2]
feedback_kept:
    ldr r2, =0x20000108
    strb r0, [r2]
    movs r0, #3
    subs r1, r0, r1
    ldr r2, =0x20000008
    strb r1, [r2]
done:
    msr primask, r6
    pop {r4, r5, r6, pc}
'''


def apply(img):
    """Apply only to the exact tagged PN1.23F candidate, preserving its fixes."""
    if hashlib.sha256(bytes(img.data)).hexdigest() != PARENT_SHA256:
        raise PatchError('digital gain continuity requires the exact PN1.23F candidate')

    start = symbols.APP_BASE + len(img.data)
    invalidator = img.assemble_at(start, INVALIDATE_SOURCE)
    boundary = start + len(invalidator)
    boundary_code = img.assemble_at(boundary, BOUNDARY_SOURCE)
    code = invalidator + boundary_code
    code += bytes(-len(code) % 4)

    # Both manual and automatic gain paths already load r4 with GATE_STATE.
    # Calling the new invalidator leaves r0/r2/r3 intact; the enclosing stock
    # gain function restores its saved LR, so the additional BL needs no stack.
    old_source = auto_range_freshness.SOURCE
    needle = 'movs r1, #0\n    strb r1, [r4]'
    if old_source.count(needle) != 2:
        raise PatchError('gain freshness source does not contain both invalidations')
    gain_code = img.assemble_at(auto_range_freshness.HELPER,
                               old_source.replace(needle, f'bl {start:#x}'))
    if len(gain_code) > auto_range_freshness.SIZE:
        raise PatchError('gain continuity exceeds the existing AGC helper reservation')
    gain_code += bytes(auto_range_freshness.SIZE - len(gain_code))
    old_gain = img.read(auto_range_freshness.HELPER, auto_range_freshness.SIZE)
    old_entry = img.read(sampling_fixes.BOUNDARY, 4)
    branch = img.assemble_at(sampling_fixes.BOUNDARY, f'b.w {boundary:#x}')

    img.extend(len(code), 'Digital gain continuity: invalidator and sampling boundary')
    img.poke(start, bytes(len(code)).hex(), code,
             'Keep confirmed Digital feedback across gain-only sample resets without renewing it')
    img.poke(auto_range_freshness.HELPER, old_gain.hex(), gain_code,
             'Mark previously open Digital gain changes separately from gate/mode invalidation')
    img.poke(sampling_fixes.BOUNDARY, old_entry.hex(), branch,
             'Main boundary restarts all samples but retains bounded gain-transition feedback')
    img.poke(version_tag.VERSION_STRING, b'PN1.23F\0'.hex(), b'PN1.23G\0',
             'Candidate identity PN1.23G')
    img.version_tag = CANDIDATE_TAG
    img.digital_gain_continuity = {
        'invalidator': start, 'boundary': boundary, 'helper_bytes': len(code),
        'persistent_ram_bytes': 0, 'additional_stack_bytes': 0,
    }


def build_candidate():
    img = auto_range_freshness.build_candidate()
    apply(img)
    return img


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true', help='write experimental raw/update images and hashes')
    args = parser.parse_args(argv)
    candidate = build_candidate()
    artifacts = ((OUTPUT, bytes(candidate.data)), (UPDATE, wrap(candidate.data)))
    lines = [f'{hashlib.sha256(data).hexdigest()}  {name}' for name, data in artifacts]
    if args.write:
        directory = Path(__file__).resolve().parent.parent / 'experimental'
        for name, data in artifacts:
            (directory / name).write_bytes(data)
        (directory / 'RX-PN1.23G-SHA256SUMS.txt').write_text('\n'.join(lines) + '\n', encoding='ascii')
        print(f'Wrote {CANDIDATE_TAG} experimental firmware to {directory}')
    else:
        print('Dry build; pass --write to create the experimental firmware files.')
    for (name, data), line in zip(artifacts, lines):
        print(f'{len(data)} bytes: {line}')
    print('Owner confirmed the Digital dropout fix on PN1.23G (2026-09-22).')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
