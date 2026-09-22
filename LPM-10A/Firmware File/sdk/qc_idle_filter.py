"""Qualify QC passing pins before lighting the classic indicators.

PN2.23R publishes every raw sample immediately. A single downward fluctuation
of seven timer counts therefore looks like an attached wire. Require three
consecutive passing observations of the same pin before publishing green;
OPEN/CHECK samples still revoke a pass immediately. This preserves the stock
electrical decision boundary and the ten-millisecond acquisition cadence.

The stimulus in test_qc_idle_filter is synthetic: no hardware noise envelope
has been measured. Persistent lower counts still require a valid unplugged
Init baseline. No automatic baseline adaptation can safely infer an unplugged
connector from these eight timer counts alone.

The helper executes inside the existing short publication critical section.
It neither waits nor calls hardware/scheduler functions. Separate raw state
preserves fault episode accounting while the UI consumes qualified states.
"""
from lpm10a.image import PatchError
from lpm10a.thumb import assemble
import qc_continuity as Q
import roadmap


CONFIRMATIONS = 3
STATE_SIZE, STREAK, RAW, EPOCH = 20, 0, 8, 16
CLASSIFY_SITE, RESUME = 0x08069796, 0x080697A0
EXPECTED = bytes.fromhex('20462030284401780370')


def install(img):
    """Append filtering to a composed classic-QC image; leave version to caller."""
    if not hasattr(img, 'qc_classic') or not hasattr(img, 'qc'):
        raise PatchError('QC idle filter requires the classic continuous QC parent')
    if img.read(CLASSIFY_SITE, len(EXPECTED)) != EXPECTED:
        raise PatchError('QC idle filter: unexpected classification seam')
    if CONFIRMATIONS != 3:
        raise PatchError('QC idle filter confirmation contract changed')
    state = img.alloc_ram(STATE_SIZE)
    syms = dict(FILTER=state, Q=img.qc['state'])
    clear = img.emit_code(f'''
        ldr r0, =FILTER
        movs r1, #0
        movs r2, #{STATE_SIZE // 4}
    zero:
        str r1, [r0]
        adds r0, #4
        subs r2, #1
        bne zero
        bx lr
    ''', extra_syms=syms, why='QC: clear confirmation and raw-history state at startup')
    qualify = img.emit_code(f'''
        qualify:
            push {{r2, r6}}
            ldr r0, =FILTER
            ldr r1, [r4, #{Q.GENERATION}]
            ldr r2, [r0, #{EPOCH}]
            cmp r1, r2
            beq current
            movs r2, #0
            str r2, [r0]
            str r2, [r0, #4]
            str r2, [r0, #8]
            str r2, [r0, #12]
            str r1, [r0, #{EPOCH}]
        current:
            add r0, r5
            mov r6, r4
            adds r6, #{Q.NOW}
            add r6, r5
            mov r2, r3
            cmp r3, #1
            beq passing
            movs r1, #0
            strb r1, [r0]
            b publish
        passing:
            ldrb r1, [r0]
            cmp r1, #{CONFIRMATIONS}
            bhs publish
            adds r1, #1
            strb r1, [r0]
            cmp r1, #{CONFIRMATIONS}
            bhs publish
            ldrb r2, [r6]
            cmp r2, #1
            bne publish
            movs r2, #0
        publish:
            strb r2, [r6]
            ldrb r1, [r0, #{RAW}]
            strb r3, [r0, #{RAW}]
            pop {{r2, r6}}
            b.w {RESUME}
    ''', extra_syms=syms,
        why='QC: three same-pin passing observations; immediate faults and raw episode history')
    img.poke(CLASSIFY_SITE, EXPECTED[:4].hex(),
             assemble(CLASSIFY_SITE, f'b.w {qualify}'),
             'QC: qualify passing readings before publishing pin indicators')
    init = roadmap.startup(img, f'bl {clear}', {})
    img.qc_idle_filter = dict(state=state, state_size=STATE_SIZE, clear=clear,
                              qualify=qualify, init=init, site=CLASSIFY_SITE,
                              resume=RESUME, confirmations=CONFIRMATIONS,
                              expected=EXPECTED)
    return img
