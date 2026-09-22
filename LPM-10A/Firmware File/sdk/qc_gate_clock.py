"""Normalize QC pulse counts by the actual SysTick acquisition duration.

The native ten-tick RTOS wait is not an exact ten-millisecond gate. Both QC
Init and continuous acquisition call MEASURE, so correcting that shared seam
gives their counts the same nominal ten-millisecond unit. Interrupts are
masked only around adjacent timer/clock captures, never around the wait or
normalization. Existing timer ownership remains the caller's responsibility.

Persisted baselines made with the old raw gate need separate migration by the
release builder. This module does not modify settings, UI, or version strings.
"""
from lpm10a.image import PatchError
from lpm10a.thumb import assemble


MEASURE, RESET, COUNTER, CLEAR_STATUS = 0x08018B84, 0x080188CE, 0x0801858C, 0x080183CC
TIMER, TICK, VAL, LOAD, ICSR = 0x40013400, 0x200001A0, 0xE000E018, 0xE000E014, 0xE000ED04
CYCLES_PER_TICK, NOMINAL_TICKS = 144_000, 10
NOMINAL_CYCLES = CYCLES_PER_TICK * NOMINAL_TICKS
MIN_CYCLES, MAX_CYCLES = 9*CYCLES_PER_TICK, 500*CYCLES_PER_TICK
EXPECTED_MEASURE = bytes.fromhex('10b500210548fff7a0fe0a2003f0e4fd0248fff7f9fc0446204610bd00340140')
SYSTICK_SETUP = 0x0801C744
EXPECTED_SYSTICK = bytes.fromhex('00204ff0e02108618861024848610720086170477f320200')


def install(img):
    """Replace only the guarded native QC sampler and append its helpers."""
    if not hasattr(img, 'qc') or not hasattr(img, 'qc_classic'):
        raise PatchError('QC gate clock requires the classic QC ownership layer')
    for address, expected in ((MEASURE, EXPECTED_MEASURE), (SYSTICK_SETUP, EXPECTED_SYSTICK)):
        if img.read(address, len(expected)) != expected:
            raise PatchError(f'QC gate clock: unexpected measurement/clock contract at {address:#x}')
    # Called with interrupts masked. A task cannot overlap an executing SysTick
    # handler. Account for a pending tick, including a reload between either of
    # the VAL reads and the ICSR read; never count that same reload twice.
    snapshot = img.emit_code(f'''
        ldr r0, ={TICK}
        ldr r0, [r0]
        ldr r3, ={VAL}
        ldr r1, [r3]
        ldr r2, ={ICSR}
        ldr r2, [r2]
        ldr r3, [r3]
        lsls r2, r2, #5
        bmi pending
        cmp r3, r1
        bls captured
    pending:
        adds r0, #1
    captured:
        mov r1, r3
        bx lr
    ''', why='QC: atomic tick/sub-tick snapshot with pending and reload compensation')
    # Exact Horner division evaluates raw*NOMINAL_CYCLES/elapsed without a
    # 64-bit product. Each intermediate is < 2*MAX_CYCLES+NOMINAL_CYCLES,
    # and each quotient digit is <=3 at the accepted nine-ms lower bound.
    normalize = img.emit_code(f'''
        push {{r3, r4, r5, r6, r7, lr}}
        movw r2, #65535
        cmp r0, r2
        bhs invalid
        ldr r2, ={MIN_CYCLES}
        cmp r1, r2
        blo invalid
        ldr r2, ={MAX_CYCLES}
        cmp r1, r2
        bhi invalid
        mov r4, r0
        mov r5, r1
        ldr r6, ={NOMINAL_CYCLES}
        movs r7, #16
        movs r0, #0
        movs r1, #0
    bit:
        lsls r0, r0, #1
        lsls r1, r1, #1
        lsls r4, r4, #1
        lsrs r2, r4, #16
        uxth r4, r4
        cmp r2, #0
        beq divide
        add r1, r6
    divide:
        udiv r2, r1, r5
        mls r1, r2, r5, r1
        add r0, r2
        subs r7, #1
        bne bit
        lsls r1, r1, #1
        cmp r1, r5
        blo rounded
        adds r0, #1
    rounded:
        movw r2, #65535
        cmp r0, r2
        blo done
    invalid:
        movw r0, #65535
    done:
        pop {{r3, r4, r5, r6, r7, pc}}
    ''', why='QC: exact rounded ten-ms normalization without 32-bit product overflow')
    measure = img.emit_code(f'''
        push {{r3, r4, r5, r6, r7, lr}}
        sub sp, #16
        mrs r7, primask
        cmp r7, #0
        beq begin
        b.w invalid
    begin:
        cpsid i
        ldr r0, ={LOAD}
        ldr r0, [r0]
        ldr r1, ={CYCLES_PER_TICK-1}
        cmp r0, r1
        bne invalid_masked
        ldr r0, ={TIMER}
        movs r1, #1
        bl {CLEAR_STATUS}
        ldr r0, ={TIMER}
        movs r1, #0
        bl {RESET}
        bl {snapshot}
        str r0, [sp]
        str r1, [sp, #4]
        ldr r2, ={CYCLES_PER_TICK}
        cmp r1, r2
        bhs invalid_masked
        msr primask, r7
        movs r0, #{NOMINAL_TICKS}
        bl vTaskDelay
        mrs r7, primask
        cpsid i
        ldr r0, ={TIMER}
        bl {COUNTER}
        mov r6, r0
        bl {snapshot}
        str r0, [sp, #8]
        str r1, [sp, #12]
        ldr r2, ={CYCLES_PER_TICK}
        cmp r1, r2
        bhs invalid_masked
        ldr r0, ={LOAD}
        ldr r0, [r0]
        ldr r1, ={CYCLES_PER_TICK-1}
        cmp r0, r1
        bne invalid_masked
        ldr r0, ={TIMER}
        ldr r0, [r0, #16]
        movs r1, #1
        ands r0, r1
        bne invalid_masked
        msr primask, r7
        ldr r0, [sp, #8]
        ldr r1, [sp]
        subs r0, r0, r1
        movw r1, #501
        cmp r0, r1
        bhi invalid
        ldr r1, ={CYCLES_PER_TICK}
        mul r0, r0, r1
        ldr r1, [sp, #4]
        add r0, r1
        ldr r1, [sp, #12]
        subs r1, r0, r1
        mov r0, r6
        bl {normalize}
        b done
    invalid_masked:
        msr primask, r7
    invalid:
        movw r0, #65535
    done:
        add sp, #16
        pop {{r3, r4, r5, r6, r7, pc}}
    ''', why='QC: capture actual gate duration while retaining the yielding ten-tick wait')
    img.poke(MEASURE, EXPECTED_MEASURE[:4].hex(), assemble(MEASURE, f'b.w {measure}'),
             'QC: normalize shared Init/live native sampler by measured elapsed time')
    img.qc_gate_clock = dict(measure=measure, snapshot=snapshot, normalize=normalize,
                             native=MEASURE, nominal_cycles=NOMINAL_CYCLES,
                             guards={MEASURE: EXPECTED_MEASURE, SYSTICK_SETUP: EXPECTED_SYSTICK})
    return img.qc_gate_clock
