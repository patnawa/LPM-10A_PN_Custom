"""PN 1.6: main-loop sample ownership and latched gate invalidation.

Metadata lives in audited zero-initialized padding, not sample storage:
MODE_REQUEST (.49): zero, or requested mode + 1; GATE_STATE (.EF): zero
(startup/invalidated), one (closed), or two (open). Only the main loop resets
sampler state. In particular, AGC never resets a possibly preempted ADC ISR.
"""
import hashlib

from lpm10rx.image import PatchError

MODE_REQUEST = 0x20000049
GATE_STATE = 0x200000EF
BOUNDARY = 0x08008378
READY = 0x08008408
PUBLISH_DIGITAL = 0x0800A048
PUBLISH_TONE = 0x08008434
PUBLISH_GATE = 0x08008688


def _code(img, addr, size, source):
    result = img.assemble_at(addr, source, {
        'sampling_boundary': BOUNDARY, 'sampling_ready': READY,
        'publish_digital': PUBLISH_DIGITAL, 'publish_tone': PUBLISH_TONE,
        'publish_gate': PUBLISH_GATE,
    })
    if len(result) > size or len(result) % 2:
        raise PatchError(f'sampling helper {addr:#x}: {len(result)} bytes exceed {size}')
    return result + bytes.fromhex('00bf') * ((size - len(result)) // 2)


def apply(img):
    """Apply after PN 1.5 audit patches, before the PN 1.6 digital detector."""
    slots = {
        (0x080082B8, 0x1C0): '7e021d1cec642cc7fd420a3143698b191034ec38cfca5ae301908728a1dadd94',
        (0x080084D8, 0x4C): 'e794fdcf248655aacc9e6486a5051f808ebf23cbcee699e20129c6455204c440',
        (0x0800863A, 0xD4): 'c67f97ca445a5ef783e009672748d0a6e88608d9e0a596e997261c1a6b3fae92',
        (0x08009FFE, 0xA6): 'f0f365ee770ab9e5e0c2b2f5bd6d63c0c4fa5940faec3e52aad28333997c43df',
    }
    # Hashes pin each complete reclaimed block, including the PN 1.5 mains
    # publication-order fix. A subsequent patch cannot silently steal a slot.
    for (addr, size), digest in slots.items():
        actual = hashlib.sha256(img.read(addr, size)).hexdigest()
        if actual != digest:
            raise PatchError(f'sampling patch site {addr:#x} differs from audited PN 1.5')

    key = _code(img, 0x080082B8, BOUNDARY - 0x080082B8, '''
        push {r3, r4, r5, r6, r7, lr}
        ldr r4, =0x2000010C
        movs r5, #0
        mov r6, r4
        adds r6, #2
    next_key:
        ldr r0, =0x40011400
        cmp r5, #0
        bne port_ready
        ldr r0, =0x40011000
    port_ready:
        movw r1, #0x8000
        cmp r5, #2
        bne pin_ready
        lsrs r1, r1, #1
    pin_ready:
        bl gpio_read_pin
        ldrh r1, [r6]
        cmp r0, #0
        bne released
        adds r1, #1
        strh r1, [r6]
        b advance
    released:
        movs r0, #0
        strh r0, [r6]
        cmp r1, #6
        blo advance
        cmp r5, #2
        beq lamp
        movs r7, #2
        cmp r5, #1
        beq request
        ldr r0, =0x20000048
        ldrb r1, [r0, #1]
        cmp r1, #0
        bne queued
        ldrb r1, [r0]
        adds r1, #1
    queued:
        movs r7, #0
        cmp r1, #1
        bne request
        movs r7, #1
    request:
        ldr r0, =0x20000048
        mov r1, r7
        adds r1, #1
        strb r1, [r0, #1]
        ldrb r0, [r0, #12]
        cmp r0, #1
        beq confirm
        ldr r0, =0x40010C00
        movw r1, #0x8000
        cmp r7, #2
        beq mains_led
        bl gpio_reset_pin
        cmp r7, #0
        beq confirm
        ldr r0, =0x40010800
        movw r1, #0x100
        bl gpio_set_pin
        b confirm
    mains_led:
        bl gpio_set_pin
        ldr r0, =0x40010800
        movw r1, #0x100
        bl gpio_reset_pin
        b confirm
    lamp:
        ldr r0, =0x40010800
        movw r1, #0x400
        bl gpio_toggle_pin
    confirm:
        movs r0, #100
        strb r0, [r4]
    advance:
        adds r6, #2
        adds r5, #1
        cmp r5, #3
        blo next_key
        pop {r3, r4, r5, r6, r7, pc}
    ''')
    boundary = _code(img, BOUNDARY, READY - BOUNDARY, '''
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
        strb r1, [r5, #1]
        movs r0, #0
        strb r0, [r5]
        strh r0, [r4, #16]
        strb r0, [r4, #18]
        strb r0, [r4, #19]
        strb r0, [r4, #20]
        strb r0, [r4, #21]
        ldr r2, =0x2000006C
        strh r0, [r2]
        ldr r2, =0x20000108
        strb r0, [r2]
        movs r0, #3
        subs r1, r0, r1
        ldr r2, =0x20000008
        strb r1, [r2]
    done:
        msr primask, r6
        pop {r4, r5, r6, pc}
    ''')
    ready = _code(img, READY, PUBLISH_TONE - READY, '''
        ldr r0, =0x20000048
        ldrb r0, [r0, #1]
        cmp r0, #0
        bne denied
        ldr r0, =0x200000EF
        ldrb r0, [r0]
        cmp r0, #2
        bne denied
        ldr r0, =0x20000008
        ldrb r0, [r0]
        cmp r0, #0
        bne denied
        movs r0, #1
        bx lr
    denied:
        movs r0, #0
        bx lr
    ''')
    gate = _code(img, PUBLISH_GATE, 0x0800870E - PUBLISH_GATE, '''
        push {r4, r5, r6, lr}
        mrs r6, primask
        cpsid i
        ldr r4, =0x20000068
        ldr r1, =0x20000048
        ldrb r1, [r1]
        cmp r1, #2
        beq publish
        cmp r1, #0
        beq digital
        ldrh r2, [r4, #2]
        cmp r2, #1
        movs r2, #0
        blo old_ready
        movs r2, #1
    old_ready:
        movw r3, #580
        cmp r0, r3
        b new_ready
    digital:
        ldrh r2, [r4]
        cmp r2, #2
        movs r2, #0
        blo digital_old_ready
        movs r2, #1
    digital_old_ready:
        cmp r0, #2
    new_ready:
        movs r3, #0
        blo compare
        movs r3, #1
    compare:
        cmp r2, r3
        beq publish
        ldr r1, =0x200000EF
        movs r2, #0
        strb r2, [r1]
    publish:
        strh r0, [r4]
        movw r1, #580
        udiv r0, r0, r1
        strh r0, [r4, #2]
        msr primask, r6
        pop {r4, r5, r6, pc}
    ''')
    agc = _code(img, 0x080084D8, 0x4C, '''
        push {r4, lr}
        ldr r4, =0x2000005E
        movs r0, #3
        mov r1, r4
        bl adc_read_n
        mov r0, r4
        movs r1, #5
        bl trimmed_mean
        bl publish_gate
        bl gain_select_3bit
        pop {r4, pc}
    ''')
    tone = _code(img, PUBLISH_TONE, 0x08008478 - PUBLISH_TONE, '''
        mrs r3, primask
        cpsid i
        ldr r0, =0x20000048
        ldrb r0, [r0, #1]
        cmp r0, #0
        bne done
        ldr r0, =0x200000EF
        ldrb r0, [r0]
        cmp r0, #2
        bne done
        ldr r0, =0x2000010C
        ldrb r2, [r0]
        cmp r2, #0
        bne done
        ldr r2, =0x2000005A
        ldrb r0, [r2]
        cmp r0, #0
        bne done
        strb r1, [r2]
        ldr r0, =0x2000010C
        strb r1, [r0]
    done:
        msr primask, r3
        bx lr
    ''')
    digital = _code(img, PUBLISH_DIGITAL, 0x0800A0A4 - PUBLISH_DIGITAL, '''
        mrs r3, primask
        cpsid i
        ldr r0, =0x20000048
        ldrb r0, [r0, #1]
        cmp r0, #0
        bne done
        ldr r0, =0x200000EF
        ldrb r0, [r0]
        cmp r0, #2
        bne done
        ldr r0, =0x2000005A
        strb r1, [r0, #3]
        movw r1, #800
        strh r1, [r0, #18]
    done:
        msr primask, r3
        bx lr
    ''')
    analog = _code(img, 0x08009FFE, PUBLISH_DIGITAL - 0x08009FFE, '''
        mov r3, sp
        ldrh r0, [r3, #8]
        ldrh r2, [r3, #4]
        movw r1, #600
        add r1, r2
        cmp r0, r1
        ble medium
        movs r1, #50
        b tone
    medium:
        mov r1, r2
        adds r1, #200
        cmp r0, r1
        ble low
        movs r1, #100
        b tone
    low:
        mov r1, r2
        adds r1, #10
        cmp r0, r1
        ble rearm
        movs r1, #200
    tone:
        bl publish_tone
    rearm:
        ldr r0, =0x20000008
        movs r1, #1
        strb r1, [r0]
        b.w 0x0800A0A4
    ''')
    mains = _code(img, 0x0800863A, PUBLISH_GATE - 0x0800863A, '''
        ldr r1, =0x20000058
        strh r0, [r1]
        movw r1, #350
        cmp r0, r1
        ble medium
        movs r1, #50
        b tone
    medium:
        cmp r0, #251
        blo low
        movs r1, #100
        b tone
    low:
        cmp r0, #151
        blo rearm
        movs r1, #200
    tone:
        bl publish_tone
    rearm:
        ldr r0, =0x2000006E
        movs r1, #128
        bl __aeabi_memclr
        ldr r0, =0x20000008
        movs r1, #1
        strb r1, [r0]
        b.w 0x0800870E
    ''')
    for addr, code, why in (
        (0x080082B8, key + boundary + ready + tone, 'queued mode requests and atomic main-loop sample ownership'),
        (0x080084D8, agc, 'AGC publishes both gates atomically and latches threshold crossings'),
        (0x0800863A, mains + gate, 'mains feedback commit guard and AGC publication helper'),
        (0x08009FFE, analog + digital, 'analog and digital publication reject invalidated windows'),
    ):
        img.poke(addr, img.read(addr, len(code)).hex(), code, why)
    img.poke(0x0800B8F2, 'fcf797fc284600bf',
             img.assemble_at(0x0800B8F2, f'bl {BOUNDARY}\nmov r0, r5\nnop'),
             'main boundary applies sampler ownership before mode dispatch and feeds IWDG')
    for site, continuation, exit_addr, expected in (
        (0x080085F8, 0x0800860C, 0x0800870E, '40f20800c2f2000090f90000002840f08280ffe7'),
        (0x08009F5C, 0x08009F70, 0x0800A0A4, '40f20800c2f2000090f90000002840f09b80ffe7'),
    ):
        code = _code(img, site, 20, f'''
            bl sampling_ready
            cmp r0, #0
            bne {continuation}
            b.w {exit_addr}
        ''')
        img.poke(site, expected, code, 'reject acquisition from a pending mode or gate transition')
    img.sampling_freshness = True
    img.syms.update(sampling_ready=READY | 1, publish_digital=PUBLISH_DIGITAL | 1)
