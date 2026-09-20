"""Opt-in PN 2.13 SCAN modes; the original two waveforms remain available.

Sync32 uses the agreed 0x1F25EB11 word, MSB first. Its rational timing
accumulator advances by 808 for each nominal 101 us TIM2 tick, at a threshold
of 40025: the mean chip interval is 5.003125 ms, matching the RX's nominal
sample interval. This is a nominal-clock match, not clock recovery.

Pulse test applies the existing carrier for 990 ticks, then disables it for
3960 ticks. It measures envelope settling and recovery with an oscilloscope;
it is not a cable-identification protocol. No output voltage, conductor,
carrier frequency or peripheral configuration changes here.
"""
import hashlib

from lpm10a.image import PatchError
from lpm10a.thumb import assemble

PATCH_ID = 'scan-sync'
VERSION = 'PN 2.13'
PARENT_SHA256 = '3d2db80f8288744191fe1ddb2855a83b900166dd365e1583c6270dfb460a0076'
SYNC_WORD = 0x1F25EB11
SYNC_BITS = tuple((SYNC_WORD >> (31 - i)) & 1 for i in range(32))
PHASE_STEP, PHASE_LIMIT = 808, 40025
PULSE_ON, PULSE_PERIOD = 990, 4950
MODE_LABELS = ('Digital 454 kHz', 'Analog 825 Hz', 'Sync32 454 kHz', 'Pulse test')


def register(patch):
    @patch(PATCH_ID, 'Add optional Sync32 and deterministic Pulse test SCAN modes',
           risk='untested', default=False, group='scan',
           requires=('portflash-phy-status', 'scan-timing', 'scan-labels', 'thai-ui'))
    def scan_sync(img):
        img.finalize()
        if hashlib.sha256(bytes(img.data)).hexdigest() != PARENT_SHA256:
            raise PatchError('scan-sync requires the exact finalized PN 2.12 parent')
        parent_end = img.cave_ptr
        # Only modes 3/4 use this word. SCAN always boots in legacy mode; the
        # mode key initializes this RAM before publishing either new mode.
        # The timer additionally bounds-checks both fields before LUT access.
        state = img.alloc_ram(4)
        syms = {'EXT_STATE': state, 'PHASE_STEP': PHASE_STEP,
                'PHASE_LIMIT': PHASE_LIMIT, 'PULSE_ON': PULSE_ON,
                'PULSE_PERIOD': PULSE_PERIOD}
        generator = img.emit_code('''
            push {r4, lr}
            ldr r4, =EXT_STATE
            ldr r1, [r4]
            cmp r0, #4
            beq pulse
            uxth r2, r1
            lsrs r3, r1, #16
            cmp r3, #32
            bhs reset_sync
            ldr r0, =PHASE_LIMIT
            cmp r2, r0
            blo valid_sync
        reset_sync:
            movs r2, #0
            movs r3, #0
        valid_sync:
            ldr r0, =sync_bits
            adds r0, r0, r3
            ldrb r0, [r0]
            ldr r1, =PHASE_STEP
            adds r2, r2, r1
            ldr r1, =PHASE_LIMIT
            cmp r2, r1
            blo store_sync
            subs r2, r2, r1
            adds r3, #1
            cmp r3, #32
            blo store_sync
            movs r3, #0
        store_sync:
            lsls r3, r3, #16
            orrs r2, r3
            str r2, [r4]
            bl 0x0801464C
            pop {r4, pc}
        pulse:
            ldr r2, =PULSE_PERIOD
            cmp r1, r2
            blo valid_pulse
            movs r1, #0
        valid_pulse:
            movs r0, #0
            ldr r2, =PULSE_ON
            cmp r1, r2
            bhs pulse_off
            movs r0, #1
        pulse_off:
            adds r1, #1
            ldr r2, =PULSE_PERIOD
            cmp r1, r2
            blo store_pulse
            movs r1, #0
        store_pulse:
            str r1, [r4]
            bl 0x0801464C
            pop {r4, pc}
            .pool
        sync_bits:
        ''' + '.byte ' + ','.join(str(bit) for bit in SYNC_BITS), syms,
            why='SCAN: bounded Sync32 rational phase and 20 percent duty diagnostic carrier')

        dispatch = img.emit_code(f'''
            ldr r0, =scan_state
            ldrb r0, [r0, #1]
            cmp r0, #1
            beq digital
            cmp r0, #2
            beq analogue
            cmp r0, #3
            beq extended
            cmp r0, #4
            beq extended
            bx lr
        digital:
            b.w 0x08014300
        analogue:
            b.w 0x08014344
        extended:
            b.w {generator}
        ''', why='SCAN: retain legacy generators and route the optional modes')
        site = 0x08014714
        old = '07484078012802d0022806d102e0fff7edfd03e0fff70cfe00e000bf00bf'
        new = assemble(site, f'bl {dispatch}\nb 0x08014732')
        new += assemble(site + len(new), 'nop\n' * ((len(bytes.fromhex(old)) - len(new)) // 2))
        img.poke(site, old, new, 'SCAN mode dispatcher, inside original active-screen/enabled guards')

        mode_key = img.emit_code('''
            mrs r3, PRIMASK
            cpsid i
            ldr r1, =scan_state
            ldrb r0, [r1, #1]
            adds r0, #1
            cmp r0, #4
            bls valid_mode
            movs r0, #1
        valid_mode:
            movs r2, #0
            ldr r1, =EXT_STATE
            str r2, [r1]
            ldr r1, =scan_state
            strb r0, [r1, #1]
            msr PRIMASK, r3
            bx lr
        ''', syms, why='SCAN mode key: reset new cursor before atomic mode publication; preserve interrupt mask')
        site = 0x0801458E
        old = '24484078012803d102202149487002e001201f494870'
        new = assemble(site, f'bl {mode_key}\nb 0x080145A4')
        new += assemble(site + len(new), 'nop\n' * ((len(bytes.fromhex(old)) - len(new)) // 2))
        img.poke(site, old, new, 'SCAN key cycles Digital, 825 Hz, Sync32, Pulse test')

        # The user requested explicit frequency labels in both languages.
        # Digital/Sync32 show nominal carrier frequency; Analog shows its
        # envelope tone frequency. Four rows fit below the stock cable icon
        # and above the footer without changing the global Thai UI.
        ui = img.emit_code('''
            push {r4, r5, r6, r7, lr}
            sub sp, #12
            movs r4, #1
            movs r5, #194
        row:
            movw r6, #0x2105
            movw r7, #0xFFFF
            ldr r0, =scan_state
            ldrb r1, [r0, #1]
            cmp r1, r4
            bne colours
            movw r7, #0xFE60
            ldrb r0, [r0]
            cmp r0, #0
            beq colours
            movw r6, #0x7304
        colours:
            ldr r0, =0x200001AC
            strh r7, [r0]
            strh r6, [r0, #2]
            str r6, [sp]
            movs r0, #34
            mov r1, r5
            movs r2, #205
            mov r3, r5
            adds r3, #21
            bl 0x08016D08
            movs r0, #16
            str r0, [sp]
            mov r1, r4
            subs r1, #1
            lsls r1, r1, #3
            ldr r2, =labels
            adds r2, r2, r1
            ldr r0, [r2]
            str r0, [sp, #4]
            ldr r2, [r2, #4]
            lsrs r0, r2, #1
            movs r1, #120
            subs r0, r1, r0
            mov r1, r5
            adds r1, #3
            movs r3, #16
            bl 0x080174E8
            adds r5, #24
            adds r4, #1
            cmp r4, #5
            bne row
            add sp, #12
            pop {r4, r5, r6, r7, pc}
            .pool
            .align 4
        labels:
            .word digital_label, 120, analog_label, 104, sync_label, 112, pulse_label, 80
        digital_label:
            .asciz "Digital 454 kHz"
        analog_label:
            .asciz "Analog 825 Hz"
        sync_label:
            .asciz "Sync32 454 kHz"
        pulse_label:
            .asciz "Pulse test"
        ''', why='SCAN: four visible mode rows with requested frequency labels in both languages')
        img.poke(0x08014144, '00b587b0', assemble(0x08014144, f'b.w {ui}'),
                 'SCAN mode display: four rows')
        for site in (0x08011660, 0x08012E6C):
            img.set_string(site, VERSION)
        img.scan_sync = dict(state=state, generator=generator, dispatch=dispatch,
                             mode_key=mode_key, ui=ui, parent_end=parent_end,
                             parent_sha256=PARENT_SHA256)
