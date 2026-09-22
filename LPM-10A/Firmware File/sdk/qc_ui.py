"""QC session/history display helpers; all drawing runs in the GUI task.

The caller owns measurement, key routing, state initialization and patch sites.
Labels use the existing ASCII fonts in both UI languages. No queue messages or
heap allocations are made by these helpers.
"""
from lpm10a.image import PatchError

STATE_SIZE = 56
MODE, SCANS, SEEN, FAULTS, NOW = 0, 8, 10, 16, 32
SYS_STATE = 0x2000013C
QC_PHASE = 0x2000023C
COLOURS = 0x200001AC


def install(img, state, reset):
    """Return draw/frame/error/progress Thumb entry addresses for the QC state.

    reset() initializes the session and returns without drawing. MODE is
    0=needs calibration, 1=live, 2=done, 3=hold, 4=calibration error. FAULTS is
    eight u16 episode counts; NOW is eight bytes (0=unknown, 1=OK, 2=open,
    3=check). An OK pin with a recorded failure displays INT.
    """
    if state % 4 or not (0x2000F000 <= state <= 0x20010000-STATE_SIZE):
        raise PatchError('QC UI state must fit the aligned SDK RAM arena')

    syms = {'QC_STATE': state, 'SYS_STATE': SYS_STATE, 'QC_PHASE': QC_PHASE, 'COLOURS': COLOURS,
            'QC_RESET': reset | 1}
    render = img.emit_code('''
        push {r3, r4, r5, r6, r7, lr}
        sub sp, #40
        str r0, [sp, #36]
        ldr r5, =QC_STATE
        cmp r0, #1
        beq keep_led
        ldrb r0, [r5]
        cmp r0, #0
        beq led_red
        cmp r0, #4
        beq led_red
        ldrb r0, [r5, #10]
        cmp r0, #255
        bne led_red
        mov r6, r5
        adds r6, #16
        mov r7, r5
        adds r7, #32
        movs r4, #8
    led_pin:
        ldrh r0, [r6]
        cmp r0, #0
        bne led_red
        ldrb r0, [r7]
        cmp r0, #1
        bne led_red
        adds r6, #2
        adds r7, #1
        subs r4, #1
        bne led_pin
        movs r0, #2
        b update_led
    led_red:
        movs r0, #1
    update_led:
        bl 0x08010F94
    keep_led:
        ldr r0, =COLOURS
        ldr r1, [r0]
        str r1, [sp, #32]
        movs r1, #0
        strh r1, [r0, #2]
        str r1, [sp]
        movs r0, #8
        movs r1, #52
        movs r2, #230
        movw r3, #315
        bl gui_draw_shape

        ldr r5, =QC_STATE
        ldr r0, [sp, #36]
        cmp r0, #1
        ldr r3, =calibrating
        beq have_title
        ldrb r0, [r5]
        ldr r3, =needs_cal
        cmp r0, #0
        beq have_title
        ldr r3, =live
        cmp r0, #1
        beq have_title
        ldr r3, =done_text
        cmp r0, #2
        beq have_title
        ldr r3, =held
        cmp r0, #3
        beq have_title
        ldr r3, =cal_failed
    have_title:
        ldr r0, =COLOURS
        movw r1, #0xFFFF
        strh r1, [r0]
        movs r0, #16
        movs r1, #55
        movs r2, #208
        bl put16

        ldr r0, [sp, #36]
        cmp r0, #1
        ldr r3, =remove_cable
        beq summary
        ldrb r0, [r5]
        cmp r0, #4
        beq old_values
        ldrh r2, [r5, #8]
        ldr r1, =scan_format
        mov r0, sp
        bl sprintf
        mov r3, sp
        b summary
    old_values:
        ldr r3, =values_kept
    summary:
        movs r0, #16
        movs r1, #74
        movs r2, #208
        bl put12
        ldr r3, =pin_heading
        movs r0, #18
        movs r1, #92
        movs r2, #36
        bl put12
        ldr r3, =now_heading
        movs r0, #66
        movs r1, #92
        movs r2, #60
        bl put12
        ldr r3, =fail_heading
        movs r0, #162
        movs r1, #92
        movs r2, #54
        bl put12

        movs r7, #0
        movs r6, #109
    next_pin:
        movw r1, #0xFFFF
        ldr r0, =COLOURS
        strh r1, [r0]
        mov r2, r7
        adds r2, #1
        ldr r1, =number_format
        mov r0, sp
        bl sprintf
        movs r0, #18
        mov r1, r6
        movs r2, #24
        mov r3, sp
        bl put16

        lsls r0, r7, #1
        adds r0, #16
        adds r0, r5, r0
        ldrh r4, [r0]
        mov r0, r7
        adds r0, #32
        adds r0, r5, r0
        ldrb r0, [r0]
        ldr r3, =unknown
        movw r1, #0x8410
        cmp r0, #1
        bne not_ok
        ldr r3, =ok_text
        movw r1, #0x07E0
        cmp r4, #0
        beq status_ready
        ldr r3, =intermittent
        movw r1, #0xFFE0
        b status_ready
    not_ok:
        cmp r0, #2
        bne not_open
        ldr r3, =open_text
        movw r1, #0xF800
        b status_ready
    not_open:
        cmp r0, #3
        bne status_ready
        ldr r3, =check_text
        movw r1, #0xFFE0
    status_ready:
        ldr r0, =COLOURS
        strh r1, [r0]
        movs r0, #66
        mov r1, r6
        movs r2, #64
        bl put16
        movw r1, #0xFFFF
        ldr r0, =COLOURS
        strh r1, [r0]
        mov r2, r4
        ldr r1, =number_format
        mov r0, sp
        bl sprintf
        movs r0, #162
        mov r1, r6
        movs r2, #48
        mov r3, sp
        bl put16
        adds r6, #20
        adds r7, #1
        cmp r7, #8
        blo next_pin

        ldr r3, =toggle_hint
        movs r0, #16
        movw r1, #276
        movs r2, #208
        bl put12
        ldr r3, =restart_hint
        movs r0, #16
        movw r1, #289
        movs r2, #208
        bl put12
        ldr r3, =init_hint
        movs r0, #16
        movw r1, #302
        movs r2, #208
        bl put12

        ldr r0, =COLOURS
        ldr r1, [sp, #32]
        str r1, [r0]
        add sp, #40
        pop {r3, r4, r5, r6, r7, pc}

    put16:
        push {r4, lr}
        sub sp, #8
        str r3, [sp, #4]
        movs r3, #16
        str r3, [sp]
        bl gui_blit
        add sp, #8
        pop {r4, pc}
    put12:
        push {r4, lr}
        sub sp, #8
        str r3, [sp, #4]
        movs r3, #12
        str r3, [sp]
        bl gui_blit
        add sp, #8
        pop {r4, pc}
        .pool
    needs_cal: .asciz "Needs calibration"
    live: .asciz "Running (20 s)"
    done_text: .asciz "Done (20 s)"
    held: .asciz "Held"
    cal_failed: .asciz "Calibration failed"
    values_kept: .asciz "Old values kept"
    calibrating: .asciz "Calibrating..."
    remove_cable: .asciz "Remove cable first"
    scan_format: .asciz "Scans %d"
    number_format: .asciz "%d"
    pin_heading: .asciz "PIN"
    now_heading: .asciz "NOW"
    fail_heading: .asciz "FAIL"
    unknown: .asciz "-"
    ok_text: .asciz "OK"
    intermittent: .asciz "INT"
    open_text: .asciz "OPEN"
    check_text: .asciz "CHECK"
    toggle_hint: .asciz "OK: Start/Stop"
    restart_hint: .asciz "Right: New test"
    init_hint: .asciz "Hold Right: Init"
    ''', extra_syms=syms, why='QC: bounded-session state and per-pin intermittent failure history')

    syms['QC_RENDER'] = render | 1
    draw = img.emit_code('''
        ldr r0, =SYS_STATE
        ldrb r0, [r0]
        cmp r0, #8
        bne out
        ldr r0, =QC_PHASE
        ldrb r0, [r0]
        cmp r0, #4
        beq out
        movs r0, #0
        b.w QC_RENDER
    out:
        bx lr
    ''', extra_syms=syms, why='QC draw: preserve other screens and calibration ownership')
    progress = img.emit_code('''
        ldr r0, =SYS_STATE
        ldrb r0, [r0]
        cmp r0, #8
        bne out
        ldr r0, =QC_PHASE
        ldrb r0, [r0]
        cmp r0, #4
        bne out
        movs r0, #1
        b.w QC_RENDER
    out:
        bx lr
    ''', extra_syms=syms, why='QC Init: explicit progress and retained per-pin history')
    syms['QC_DRAW'] = draw | 1
    frame = img.emit_code('''
        push {r4, lr}
        ldr r0, =SYS_STATE
        ldrb r0, [r0]
        cmp r0, #8
        bne out
        ldr r0, =QC_PHASE
        ldrb r0, [r0]
        cmp r0, #4
        beq out
        bl QC_RESET
        bl QC_DRAW
    out:
        pop {r4, pc}
    ''', extra_syms=syms, why='QC frame: initialize session, then render in GUI context')
    error = img.emit_code('''
        push {r4, lr}
        ldr r0, =SYS_STATE
        ldrb r0, [r0]
        cmp r0, #8
        bne out
        ldr r0, =QC_PHASE
        ldrb r1, [r0]
        cmp r1, #4
        beq out
        movs r1, #3
        strb r1, [r0]
        ldr r0, =QC_STATE
        movs r1, #4
        strb r1, [r0]
        bl QC_DRAW
    out:
        pop {r4, pc}
    ''', extra_syms=syms, why='QC calibration failure: retain session history and show explicit outcome')
    return {'draw': draw, 'frame': frame, 'error': error, 'progress': progress}
