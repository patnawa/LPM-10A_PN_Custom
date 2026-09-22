"""QC Init: stage five-count medians and commit only a complete stable baseline.

The stock decision separates an open pin from a connected pin at a difference
of seven counts. MAX_SPREAD=6 is an initial conservative calibration limit:
the five observations may not span that complete decision boundary. It is
configurable here, not a hardware-validated noise specification. A median
below seven cannot support that decision; 0xFFFF is rejected as a counter
limit. No claim is made that a stable sample proves the cable is removed.

Only Init (CNT command 0) is replaced. Commands 1/2 retain stock behavior.
Temporary samples and all eight candidate baselines live on the stack. State
is checked before/after each ten-millisecond sample and inside the final
critical section. Rejection/cancellation retains the previous baseline and
settings. Only a complete success reaches the stock settings-update caller.

Continuity sampling may replace the four-byte handoff helper. Its ABI is
() -> r0 (1=ownership acquired, 0=abort); it must preserve r4-r7 and SP.
Calibration publishes status 4 before calling it, preventing new live scans.
The default helper grants ownership because standalone QC has no live scan.
The four-byte current_session helper has the same ABI and defaults to testing
sysState==8; a live sampler can replace it with its captured session epoch.
The four-byte after_release helper is called only after owned exits release
the mux; a composed sampler can clear its calibration ownership marker there.
The four-byte begin_session callback runs in the initial critical section
before announcing status 4, allowing epoch capture before any yielding call.
The four-byte notify adapter forwards (r0=message, r1=payload, r2=length) to
GUI_MSG_SEND by default; composition may attach the captured session epoch.
"""
from lpm10a.image import PatchError
from lpm10a.thumb import assemble, verify


ENTRY, ENTRY_STOCK, STOCK_BODY = 0x0800BDD4, 'feb50546', 0x0800BDD8
BASELINE, STATUS, VALID = 0x2000021C, 0x2000023C, 0x2000023D
SYS_STATE = 0x2000013C
SELECT, MEASURE, SORT, SAVE = 0x08018060, 0x08018B84, 0x08014BE4, 0x080118F0
GUI_SEND, ENTER_CRITICAL, EXIT_CRITICAL = 0x0800E428, 0x0801C6B4, 0x0801C6D8
SAMPLES, MAX_SPREAD, MIN_BASELINE = 5, 6, 7
STACK_BYTES = 32  # 16 baseline + 10 sample bytes + 2 padding + saved status word


def apply(img):
    """Append the calibration handler, without changing profile/version identity."""
    if img.read(ENTRY, 4) != bytes.fromhex(ENTRY_STOCK):
        raise PatchError('QC calibration requires the untouched stock CNT command entry')
    if SAMPLES != 5 or not 0 <= MAX_SPREAD < 7 or MIN_BASELINE != 7:
        raise PatchError('QC calibration constants no longer match its five-sample decision seam')
    handoff = img.emit_code('movs r0, #1\n bx lr', why='QC calibration ownership handoff (standalone: granted)')
    default_session = img.emit_code(f'''
        ldr r0, ={SYS_STATE}
        ldrb r0, [r0]
        cmp r0, #8
        beq valid
        movs r0, #0
        bx lr
    valid:
        movs r0, #1
        bx lr
    ''', why='QC calibration standalone session predicate')
    current_session = img.emit_code(f'b.w {default_session}',
                                   why='QC calibration replaceable session predicate')
    after_release = img.emit_code('bx lr\n nop', why='QC calibration released ownership notification')
    begin_session = img.emit_code('bx lr\n nop', why='QC calibration atomic session capture callback')
    notify = img.emit_code(f'b.w {GUI_SEND}', why='QC calibration replaceable GUI notification adapter')
    set_status = img.emit_code(f'''
        push {{r4, r5, r6, lr}}
        mov r4, r0
        bl {ENTER_CRITICAL}
        bl {current_session}
        mov r5, r0
        cmp r0, #0
        beq done
        ldr r1, ={STATUS}
        strb r4, [r1]
        cmp r4, #5
        bne done
        movs r0, #1
        strb r0, [r1, #1]
    done:
        bl {EXIT_CRITICAL}
        mov r0, r5
        pop {{r4, r5, r6, pc}}
    ''', why='QC calibration status may update only its own session, atomically')
    hook = img.emit_code(f'''
        push {{r1, r2, r3, r4, r5, r6, r7, lr}}
        mov r5, r0
        ldrb r0, [r5]
        cmp r0, #0
        beq initialize
        b.w {STOCK_BODY}
    initialize:
        sub sp, #{STACK_BYTES}
        ldr r6, ={STATUS}
        bl {ENTER_CRITICAL}
        ldrb r0, [r6]
        str r0, [sp, #28]
        ldr r0, ={SYS_STATE}
        ldrb r0, [r0]
        cmp r0, #8
        beq begin
        bl {EXIT_CRITICAL}
        b.w canceled_unowned
    begin:
        bl {begin_session}
        movs r0, #4
        strb r0, [r6]
        bl {EXIT_CRITICAL}
        movs r0, #0x36
        movs r1, #0
        movs r2, #0
        bl {notify}
        bl {handoff}
        cmp r0, #0
        bne owned
        b.w canceled_unowned
    owned:
        movs r7, #0
        mov r5, sp
        adds r5, #16
    pin:
        bl {current_session}
        cmp r0, #0
        beq canceled
        mov r0, r7
        bl {SELECT}
        movs r4, #0
    sample:
        bl {current_session}
        cmp r0, #0
        beq canceled
        bl {MEASURE}
        lsls r1, r4, #1
        add r1, r5
        strh r0, [r1]
        bl {current_session}
        cmp r0, #0
        beq canceled
        adds r4, #1
        cmp r4, #{SAMPLES}
        blo sample
        mov r0, r5
        mov r1, r5
        movs r2, #{SAMPLES}
        bl {SORT}                 ; stock sorter: source,destination,count, descending
        ldrh r0, [r5]
        ldrh r1, [r5, #8]
        subs r0, r0, r1
        cmp r0, #{MAX_SPREAD}
        bhi rejected
        ldrh r0, [r5, #4]
        cmp r0, #{MIN_BASELINE}
        blo rejected
        movw r1, #0xFFFF
        cmp r0, r1
        beq rejected
        lsls r1, r7, #1
        add r1, sp
        strh r0, [r1]
        adds r7, #1
        cmp r7, #8
        blo pin
        bl {ENTER_CRITICAL}
        bl {current_session}
        cmp r0, #0
        beq canceled_critical
        mov r1, sp
        ldr r2, ={BASELINE}
        movs r3, #8
    commit:
        ldrh r0, [r1]
        strh r0, [r2]
        adds r1, #2
        adds r2, #2
        subs r3, #1
        bne commit
        bl {EXIT_CRITICAL}
        ldr r0, ={BASELINE}
        bl {SAVE}                 ; copies all 16 bytes to settings; requests stock save
        movs r0, #8
        bl {SELECT}
        bl {after_release}
        movs r0, #5                ; mux released before enabling another live scan
        bl {set_status}
        cmp r0, #0
        beq success
        movs r0, #0x0C
        movs r1, #0
        movs r2, #0
        bl {notify}
    success:
        movs r0, #0
        b finish
    canceled_critical:
        bl {EXIT_CRITICAL}
    canceled:
        movs r0, #8
        bl {SELECT}
        bl {after_release}
    canceled_unowned:
        ldr r0, [sp, #28]
        bl {set_status}
        movs r0, #2
        b finish
    rejected:
        movs r0, #8
        bl {SELECT}
        bl {after_release}
        ldr r0, [sp, #28]
        bl {set_status}
        cmp r0, #0
        beq rejected_done
        movs r0, #0x0E
        movs r1, #0
        movs r2, #0
        bl {notify}
    rejected_done:
        movs r0, #1
    finish:
        add sp, #{STACK_BYTES}
        pop {{r1, r2, r3, r4, r5, r6, r7, pc}}
    ''', why='QC Init: five-count stable medians, transactional baseline and cancellation')
    img.poke(ENTRY, ENTRY_STOCK, assemble(ENTRY, f'b.w {hook}'),
             'QC command handler: robust Init; preserve all other stock commands')
    handoff_call = next(address for address, _, instruction in
                        verify(img.read(hook, img.cave_ptr-hook), hook)
                        if instruction == f'bl #0x{handoff:x}')
    img.qc_calibration = dict(hook=hook, handoff=handoff, handoff_bytes=4,
                              handoff_call=handoff_call,
                              current_session=current_session, current_session_bytes=4,
                              after_release=after_release, after_release_bytes=4,
                              begin_session=begin_session, begin_session_bytes=4,
                              notify=notify, notify_bytes=4,
                              samples=SAMPLES, max_spread=MAX_SPREAD,
                              min_baseline=MIN_BASELINE, stack_bytes=STACK_BYTES,
                              additional_stack_bytes=STACK_BYTES,
                              persistent_ram_bytes=0, result_success=0,
                              result_rejected=1, result_canceled=2)
    return img.qc_calibration
