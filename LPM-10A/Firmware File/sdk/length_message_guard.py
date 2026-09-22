"""Scope asynchronous Length text to its acquisition epoch.

The original text box transport owns a second heap allocation for its string.
Length strings are short and bounded, so a 40-byte message carries text inline.
Only audited Length callers use it; other screens retain their original API.
"""
from lpm10a.image import PatchError
from lpm10a.thumb import assemble
from length_lifecycle import branch_target
from length_reference import find_bl
import length_progress as LP

GUI_SITE, GUI_END = 0x0800F48C, 0x0800F71E
TEXT_MESSAGE, CLEAR_MESSAGE = 0x40, 0x41
CLEAR_SITE = 0x08019C40
TEXT_SITES = (0x0801214E, 0x0801225C, 0x08012290, 0x080122C4, 0x080122F8,
              0x08019C78, 0x08019CA6)
PACKET_SIZE, TEXT_OFFSET, TEXT_CAPACITY = 40, 16, 24


def install(img):
    life = img.length_lifecycle
    sites = (*TEXT_SITES, find_bl(img.data, img.length_progress['hook'], LP.TEXT_BOX))
    guards = {site: assemble(site, f'bl {LP.TEXT_BOX}') for site in sites}
    guards[CLEAR_SITE] = assemble(CLEAR_SITE, 'bl GUI_MSG_SEND', img.syms)
    for site, expected in guards.items():
        if img.read(site, len(expected)) != expected:
            raise PatchError(f'Length message guard: unexpected caller at {site:#x}')
    old_gui = img.read(GUI_SITE, 4)
    old_target = branch_target(img, GUI_SITE)
    syms = dict(CURRENT=life['current'] | 1, STATE=life['state'])

    text = img.emit_code(f'''
        text:
            push {{r4, r5, r6, r7, lr}}
            sub sp, #44
            mov r7, sp
            strh r0, [r7]
            strh r1, [r7, #2]
            strh r2, [r7, #4]
            strh r3, [r7, #6]
            ldr r5, [sp, #64]
            strb r5, [r7, #8]
            ldr r4, [sp, #68]
            bl CURRENT
            cmp r0, #0
            beq done
            ldr r0, =STATE
            ldr r0, [r0, #4]
            str r0, [sp, #12]
            cmp r4, #0
            beq done
            mov r0, r4
            cmp r5, #0x10
            beq ascii_length
            cmp r5, #0x40
            bne done
            bl 0x0801C920
            b measured
        ascii_length:
            bl 0x0800A6F0
        measured:
            cmp r0, #22
            bhi done
            mov r6, r0
            strb r6, [r7, #9]
            movs r0, #0
            strh r0, [r7, #10]
            mov r7, sp
            adds r7, #16
            movs r1, #0
            cmp r5, #0x40
            bne fill
            subs r1, #1
        fill:
            str r1, [r7, #0]
            str r1, [r7, #4]
            str r1, [r7, #8]
            str r1, [r7, #12]
            str r1, [r7, #16]
            str r1, [r7, #20]
            movs r0, #0
        copy:
            cmp r0, r6
            bhs post
            ldrb r1, [r4]
            strb r1, [r7]
            adds r4, #1
            adds r7, #1
            adds r0, #1
            b copy
        post:
            movs r0, #{TEXT_MESSAGE}
            mov r1, sp
            movs r2, #{PACKET_SIZE}
            bl GUI_MSG_SEND
        done:
            add sp, #44
            pop {{r4, r5, r6, r7, pc}}
    ''', extra_syms=syms, why='Length text: bounded inline strings tagged with the active acquisition')
    clear = img.emit_code(f'''
        clear:
            push {{r4, lr}}
            sub sp, #8
            bl CURRENT
            cmp r0, #0
            beq done
            ldr r0, =STATE
            ldr r0, [r0, #4]
            str r0, [sp]
            movs r0, #{CLEAR_MESSAGE}
            mov r1, sp
            movs r2, #4
            bl GUI_MSG_SEND
        done:
            add sp, #8
            pop {{r4, pc}}
    ''', extra_syms=syms, why='Length Testing box clear belongs to the active acquisition')

    gui = img.emit_code(f'''
        gui:
            cmp r0, #{TEXT_MESSAGE}
            beq text
            cmp r0, #{CLEAR_MESSAGE}
            beq clear
        delegate:
            b.w {old_target}
        clear:
            ldr r1, [sp, #12]
            cmp r1, #0
            beq done
            ldr r2, =0x2000013C
            ldrb r2, [r2]
            cmp r2, #7
            bne done
            ldr r2, =STATE
            ldr r2, [r2]
            ldr r3, [r1]
            cmp r2, r3
            bne done
            movs r0, #0x1B
            mov r1, sp
            adds r1, #8
            strb r0, [r1]   ; stock dispatcher reloads its message id from the frame
            b delegate
        text:
            ldr r1, [sp, #12]
            cmp r1, #0
            beq done
            ldr r2, =0x2000013C
            ldrb r2, [r2]
            cmp r2, #7
            bne done
            ldr r2, =STATE
            ldr r2, [r2]
            ldr r3, [r1, #12]
            cmp r2, r3
            bne done
            mov r4, r1
            ldrh r0, [r4, #6]
            ldr r1, =0x200001AC
            strh r0, [r1]
            ldrh r0, [r4, #4]
            strh r0, [r1, #2]
            ldrb r0, [r4, #8]
            cmp r0, #0x40
            beq cjk
            cmp r0, #0x10
            bne done
            str r0, [sp]
            mov r0, r4
            adds r0, #16
            str r0, [sp, #4]
            ldrb r2, [r4, #9]
            lsls r2, r2, #3
            movs r3, #16
            ldrh r1, [r4, #2]
            ldrh r0, [r4]
            bl 0x080174E8
            b done
        cjk:
            mov r2, r4
            adds r2, #16
            movs r3, #0
            ldrh r1, [r4, #2]
            ldrh r0, [r4]
            bl 0x080176AC
        done:
            b.w {GUI_END}
    ''', extra_syms=syms, why='Length GUI: discard stale Testing text before any display writes')
    for site in sites:
        img.poke(site, guards[site].hex(), assemble(site, f'bl {text}'),
                 'Length: epoch-tagged inline text transport')
    img.poke(CLEAR_SITE, guards[CLEAR_SITE].hex(), assemble(CLEAR_SITE, f'bl {clear}'),
             'Length: epoch-tagged Testing box clear')
    img.poke(GUI_SITE, old_gui.hex(), assemble(GUI_SITE, f'b.w {gui}'),
             'Length: validate asynchronous progress messages before drawing')
    img.length_message_guard = dict(text=text, clear=clear, gui=gui, guards=guards,
                                     previous_gui=old_target, sites=sites)
    return img.length_message_guard
