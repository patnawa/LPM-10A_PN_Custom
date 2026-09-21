"""PN 2.21: every wire of the Cable Test result carries the number that decided it.

The owner's remark on the cable-diag build: the numbers on the wires are worth keeping,
they tell the state of the cable, not just pass / fail.  PN 2.21 makes them part of the
result, tidied: at the right end of every wire, in the wire's own colour, the lowest
median among the eight sensed pins (the value PN 2.19's rules judge):

    switch mode    "2   60"   the pin it reaches through the switch, and the reading
                   "- 4095"   no partner (no reading at or below 1240): open, or a
                              floating wire's near-rail value
    RX unit mode   "1655"     the reading; the RX unit's ladder makes it the remote pin
                              (1655 pin 1, 1975 pin 2, 2319, 2607, 2935, 3183, 3391, 3679,
                              3900 shield); 4095 open, under 1240 a short

In switch mode the pin letter is the wire's real partner: a good cable reads 2 1 6 5 4 3 8 7
down the rows, a swapped pair shows up as the wrong letter where stock only draws green.
In RX unit mode the letter would be arbitrary (every sensed pin reads the ladder value),
so only the reading is shown; the wire drawing itself shows a crossing.  A reading that is
low but not at the rail on an unplugged cable (say 3800) is leakage or moisture; one that
is not quite a short on a switch (say 300 instead of 60) is a poor contact.

Mechanics: the two `bl release_hook` sites of cable-robust become `bl values_hook`,
which runs the release hook (mux release, "Not connected") and then draws one 6x12 text
per row from the median table cable-robust keeps: x = 207 - width, y = row - 6 (the
rows are at 68 + 24 i), colour = the wire's table colour (0x0801E2CC), red for an open
wire and yellow for a short as stock draws them, on the frame's 0x2105 interior.  The
firmware's sprintf has no %c, so the letter is stored by hand.
"""
import hashlib

from lpm10a.image import PatchError
from lpm10a.thumb import assemble

import cable_test as CT


PATCH_ID = 'cable-values'
VERSION = 'PN 2.21'
PARENT_SHA256 = '9eaa0fdeded19a0f7c6bb77c386c8abad9ab8d9a4720341d7ec2a79a03866d02'   # PN 2.20

COLOURS = 0x0801E2CC            # u16 per wire: the colours stock draws the nine wires with
MODE = 0x20000010               # low nibble: 0 switch, 1 RX unit; 0x10 = a test has started
RIGHT_X, INTERIOR = 207, 0x2105
RED, YELLOW = 0xF800, 0xFFE0


def register(patch):
    @patch(PATCH_ID, 'Cable Test: every wire ends with the reading that decided it (partner pin in switch mode)',
           risk='low', default=False, group='measure', requires=('cable-text-clear',))
    def cable_values(img):
        img.finalize()
        if hashlib.sha256(bytes(img.data)).hexdigest() != PARENT_SHA256:
            raise PatchError('cable-values requires the exact finalized PN 2.20 parent')
        release, med = img.cable['release'], img.cable['med']
        for site in CT.RELEASE_SITES:
            if img.read(site, 4) != assemble(site, f'bl {release}'):
                raise PatchError(f"cable-values: 0x{site:08X} does not call cable-robust's release hook")
        hook = img.emit_code(f'''
        values_hook:                    ; after the result: the deciding reading at the right end of every wire
                push {{r4, r5, r6, r7, lr}}
                sub  sp, #28            ; [sp..8) blit args, [sp+8..28) text
                bl   {release}          ; cable-robust: mux release and "Not connected"
                ldr  r0, =0x200001AE
                movw r1, #{INTERIOR}
                strh r1, [r0]           ; text background = the frame interior
                movs r4, #0             ; the driven pin / row
        row:    lsls r5, r4, #3
                movs r6, #0             ; slot of the lowest median
                movw r7, #0xFFFF        ; the lowest median
                movs r1, #0
        scan:   adds r2, r5, r1
                lsls r2, r2, #1
                ldr  r3, =MED
                add  r3, r2
                ldrh r3, [r3]
                cmp  r3, r7
                bhs  scan_next
                mov  r7, r3
                mov  r6, r1
        scan_next:
                adds r1, #1
                cmp  r1, #8
                blt  scan
                cmp  r4, r6             ; the sensed pin behind the slot
                bgt  named
                adds r6, #1
        named:  movs r2, #0x2D          ; '-': no real short, so no partner (switch mode's own rule, 1240)
                movw r0, #{CT.SWITCH_SHORT}
                cmp  r7, r0
                bhi  letter
                movs r2, #0x47          ; 'G'
                cmp  r6, #8
                beq  letter
                movs r2, #0x31          ; '1' + pin
                add  r2, r6
        letter: str  r2, [sp, #4]
                ldr  r0, =MODE
                ldrb r0, [r0]
                movs r1, #0x0F
                ands r0, r1
                cmp  r0, #0
                bne  rx_fmt
                ldr  r1, =fmt_switch    ; "? %4d": partner pin and reading
                b    fmt
        rx_fmt: ldr  r1, =fmt_rx        ; "%4d": the reading is the remote pin
        fmt:    mov  r2, r7
                mov  r0, sp
                adds r0, #8
                bl   sprintf
                mov  r5, r0             ; length
                ldr  r0, =MODE
                ldrb r0, [r0]
                movs r1, #0x0F
                ands r0, r1
                cmp  r0, #0
                bne  colour             ; RX unit mode: no letter
                ldr  r2, [sp, #4]
                mov  r0, sp
                adds r0, #8
                strb r2, [r0]
        colour: ldr  r0, =STATUS
                add  r0, r4
                ldrb r0, [r0]
                cmp  r0, #1
                bne  not_open
                movw r0, #{RED}
                b    set_fg
        not_open:
                cmp  r0, #0
                bne  wire_colour
                movw r0, #{YELLOW}
                b    set_fg
        wire_colour:
                ldr  r0, =COLOURS
                lsls r1, r4, #1
                add  r0, r1
                ldrh r0, [r0]
        set_fg: ldr  r1, =0x200001AC
                strh r0, [r1]
                movs r0, #12
                str  r0, [sp]
                mov  r0, sp
                adds r0, #8
                str  r0, [sp, #4]
                movs r0, #{CT.ROW_PITCH}
                muls r0, r4, r0
                adds r0, #{CT.ROW0_Y - 6}
                mov  r1, r0             ; y
                movs r2, #6
                muls r2, r5, r2         ; width = 6 * length
                movs r0, #{RIGHT_X}
                subs r0, r0, r2         ; x = right end - width
                movs r3, #12
                bl   gui_blit
                adds r4, #1
                cmp  r4, #9
                blt  row
                add  sp, #28
                pop  {{r4, r5, r6, r7, pc}}
        fmt_switch: .asciz "? %4d"
        fmt_rx:     .asciz "%4d"
        ''', extra_syms=dict(MED=med, STATUS=CT.STATUS, COLOURS=COLOURS, MODE=MODE),
            why='Cable Test: the deciding reading at the right end of every wire')
        for site in CT.RELEASE_SITES:
            img.poke(site, assemble(site, f'bl {release}').hex(), assemble(site, f'bl {hook}'),
                     'wire map: the readings on the wires after the result')
        for site in (0x08011660, 0x08012E6C):
            img.set_string(site, VERSION)
        img.cable_values = dict(hook=hook)
