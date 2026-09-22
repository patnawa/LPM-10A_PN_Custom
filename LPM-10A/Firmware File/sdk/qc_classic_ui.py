"""Original QC artwork with changes limited to the affected pin indicators.

The continuous acquisition owner supplies the 64-byte QC state and reset().
This renderer keeps a separate 16-byte display cache; it never changes sample
history or calibration data. Calibration rejection retains the stock prompt
until a successful Init starts a new session.
"""
from lpm10a.image import PatchError

STATE_SIZE, CACHE_SIZE = 64, 16
SYS_STATE, PHASE, COLOURS = 0x2000013C, 0x2000023C, 0x200001AC
STOCK_HEADER, STOCK_FRAME, STOCK_ERROR = 0x0800E954, 0x0800BA54, 0x0800BAD4


def install(img, state, reset):
    if state % 4 or not (0x2000F000 <= state <= 0x20010000-STATE_SIZE):
        raise PatchError('Classic QC state must fit the aligned SDK RAM arena')
    cache = img.alloc_ram(CACHE_SIZE)
    syms = dict(Q=state, CACHE=cache, SYS=SYS_STATE, PHASE=PHASE,
                COLOURS=COLOURS, RESET=reset | 1)
    clear = img.emit_code('''
        ldr r0, =CACHE
        movs r1, #0
        str r1, [r0]
        str r1, [r0, #4]
        str r1, [r0, #8]
        str r1, [r0, #12]
        bx lr
    ''', extra_syms=syms, why='Classic QC: initialize the owned display cache at startup')
    full = img.emit_code('''
        push {r4, r5, r6, lr}
        ldr r4, =CACHE
        ldr r5, =COLOURS
        ldr r6, [r5]
        bl 0x0800E954
        bl 0x0800BA54
        str r6, [r5]
        movs r0, #0
        str r0, [r4]
        str r0, [r4, #4]
        str r0, [r4, #8]
        movs r0, #1
        strb r0, [r4, #8]
        ldr r0, =Q
        ldr r0, [r0, #56]
        str r0, [r4, #12]
        pop {r4, r5, r6, pc}
    ''', extra_syms=syms, why='Classic QC: original header/artwork on screen entry or recovery only')
    syms['FULL'] = full | 1
    draw = img.emit_code('''
        push {r3, r4, r5, r6, r7, lr}
        sub sp, #8
        ldr r0, =SYS
        ldrb r0, [r0]
        cmp r0, #8
        bne out
        ldr r0, =PHASE
        ldrb r0, [r0]
        cmp r0, #4
        beq out
        ldr r5, =Q
        ldrb r0, [r5]
        cmp r0, #1
        bne out
        ldr r4, =CACHE
        ldr r0, [r5, #56]
        ldr r1, [r4, #12]
        cmp r0, r1
        bne rebuild
        ldrb r0, [r4, #8]
        cmp r0, #1
        beq ready
    rebuild:
        bl FULL
    ready:
        ldr r0, =COLOURS
        ldr r0, [r0]
        str r0, [sp, #4]
        movs r6, #0
    pin:
        mov r0, r5
        adds r0, #32
        add r0, r6
        ldrb r7, [r0]
        cmp r7, #1
        bls normal
        movs r7, #2
    normal:
        mov r0, r4
        add r0, r6
        ldrb r1, [r0]
        cmp r1, r7
        beq next
        strb r7, [r0]
        movs r0, #7
        subs r0, r0, r6
        movs r1, #27
        muls r0, r1, r0
        adds r0, #79
        mov r1, r0
        mov r3, r0
        adds r3, #14
        movs r0, #0
        cmp r7, #1
        bne have_colour
        movw r0, #0x07E0
    have_colour:
        str r0, [sp]
        movs r0, #201
        movs r2, #215
        bl gui_draw_shape
        cmp r7, #2
        bne next
        ldr r0, =COLOURS
        movw r1, #0xF800
        strh r1, [r0]
        movs r0, #7
        subs r0, r0, r6
        movs r1, #27
        muls r0, r1, r0
        adds r0, #82
        mov r1, r0
        movs r0, #204
        bl 0x0800DEA8
    next:
        adds r6, #1
        cmp r6, #8
        blo pin
        ldr r0, =COLOURS
        ldr r1, [sp, #4]
        str r1, [r0]
        movs r6, #1
        ldrb r0, [r5, #10]
        cmp r0, #255
        bne led
        movs r7, #8
        adds r5, #32
    led_pin:
        ldrb r0, [r5]
        cmp r0, #1
        bne led
        adds r5, #1
        subs r7, #1
        bne led_pin
        movs r6, #2
    led:
        ldrb r0, [r4, #9]
        cmp r0, r6
        beq out
        strb r6, [r4, #9]
        mov r0, r6
        bl 0x08010F94
    out:
        add sp, #8
        pop {r3, r4, r5, r6, r7, pc}
    ''', extra_syms=syms, why='Classic QC: draw only changed 15-pixel pin indicators; LED uses current readings')
    syms['DRAW'] = draw | 1
    error = img.emit_code('''
        push {r4, r5, r6, lr}
        ldr r0, =SYS
        ldrb r0, [r0]
        cmp r0, #8
        bne out
        ldr r0, =PHASE
        ldrb r1, [r0]
        cmp r1, #4
        beq out
        movs r1, #3
        strb r1, [r0]
        ldr r5, =Q
        movs r0, #4
        strb r0, [r5]
        ldr r4, =CACHE
        ldr r0, [r5, #56]
        ldr r1, [r4, #12]
        cmp r0, r1
        bne show_error
        ldrb r1, [r4, #8]
        cmp r1, #2
        beq out
    show_error:
        str r0, [r4, #12]
        movs r0, #2
        strb r0, [r4, #8]
        ldr r5, =COLOURS
        ldr r6, [r5]
        bl 0x0800E954
        bl 0x0800BAD4
        str r6, [r5]
        movs r0, #1
        strb r0, [r4, #9]
        bl 0x08010F94
    out:
        pop {r4, r5, r6, pc}
    ''', extra_syms=syms, why='Classic QC: retain original calibration-error prompt until successful Init')
    syms['ERROR'] = error | 1
    frame = img.emit_code('''
        push {r4, lr}
        ldr r0, =SYS
        ldrb r0, [r0]
        cmp r0, #8
        bne out
        ldr r0, =PHASE
        ldrb r0, [r0]
        cmp r0, #4
        beq out
        bl RESET
        ldr r0, =Q
        ldrb r0, [r0]
        cmp r0, #0
        bne ready
        bl ERROR
        b out
    ready:
        bl FULL
        bl DRAW
    out:
        pop {r4, pc}
    ''', extra_syms=syms, why='Classic QC frame: automatically test, or explain an unusable baseline')
    header = img.emit_code('''
        push {r4, lr}
        ldr r0, =SYS
        ldrb r0, [r0]
        cmp r0, #8
        bne out
        ldr r0, =Q
        ldr r1, [r0, #56]
        ldr r2, =CACHE
        ldr r3, [r2, #12]
        cmp r1, r3
        bne rebuild
        ldrb r1, [r2, #8]
        cmp r1, #0
        bne out
    rebuild:
        ldrb r0, [r0]
        cmp r0, #4
        bne normal
        bl ERROR
        b out
    normal:
        bl FULL
        bl DRAW
    out:
        pop {r4, pc}
    ''', extra_syms=syms, why='Classic QC: coalesce repeated header/progress notifications without blanking artwork')
    # Progress leaves the current artwork/prompt still while calibration owns
    # the measurement hardware. An uninitialized visit may draw it once.
    return dict(draw=draw, frame=frame, error=error, progress=header,
                header=header, clear=clear, cache=cache,
                cache_size=CACHE_SIZE, full=full)
