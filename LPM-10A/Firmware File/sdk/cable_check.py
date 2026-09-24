"""PN2.28: the Cable Test checks which pin every wire reaches, and ignores keys while it measures.

Status: owner-tested 2026-09-24 ("2.28 tested"); its Switch-mode partner check turned every wire of a
good cable yellow on the owner's switch and was withdrawn in PN2.33 (release v2.33), which keeps the
RX-unit rules, the key guard and the Testing... button from this module.  Historical stage pn2.28.

Audit of PN2.27A (docs/TX-CABLE-TEST-AUDIT-2026-09-23.md), fixed here:

Switch mode (B1, B3, B4).  Stock only counted how many sensed pins read at or below 1240, so
a wire crimped into the wrong pair, or a short between two pairs, was drawn green with a
green LED.  A switch port joins exactly the two wires of each pair (1-2, 3-6, 4-5, 7-8), so
the routine can check each wire's partner from the 72 medians PN2.19 already keeps.  After
the stock drawing, `switch_tail`:
  * per signal row takes the lowest median (the shield is left out; a signal row never
    decides a shield fault) and the set of pins within a small margin of it
    (m1 + 4 + m1/16, never above 1240): the pins that row is joined to;
  * calls the far end a switch when at least two T568 pairs are joined each only to its
    own partner; a port that ties 4, 5, 7 and 8 together (some 10/100 ports) counts as two
    good pairs;
  * behind a switch: joined to its partner only = ok; to one other pin = MISWIRE (the wire is
    redrawn red, full length, status 3); to more than one = SHORT (yellow, status 0);
  * without a switch (nothing plugged in, a short on an unplugged cable): any joined wire is a
    SHORT, yellow; it is no longer drawn green;
  * the shield row: any sensed pin at or below 1240 = shield short (yellow, fault); otherwise
    "not tested" (grey line, no X, status 5) -- a switch gives the shield nowhere to go;
  * a fault turns the LED red with the double beep, as stock does for an open wire.
  The numbers at the end of the wires are PN2.21's (partner letter and reading); rows now
  take the colour of their result.

RX unit mode (B2, B5, B6).  Stock marked a row straight when any one of its eight readings
fell inside the driven pin's own +-5 % window; from pin 5 up the windows overlap, so a 6-7
or 8-G crossing could pass as straight.  The average behind the crossing decision also took
in floating slots (a broken wire, the empty shield of a UTP cable).  `classify_row` replaces
both rules: the row value is the trimmed mean of the medians of the slots that never
touched the rail region (highest sample <= 4000) and read above 1240; the wire goes to the
nearest ladder value (no own-window short-cut).  `post_pass` then refuses maps no RX unit
can produce: two wires landing on one remote pin, a wire landing on an open shield, and a
uniform level on every wire (leakage of an unplugged cable) become "unknown" -- blank row,
"Result error!!", red LED.  The short rule, the open rule (every highest sample above 4000)
and the ladder are stock / PN2.19, unchanged.

Keys during a test (B7, B10, B13, critic NEW-1).  The measurement blocks the GUI task for
about 0.86 s while the key task keeps running:
  * OK while a test runs is dropped (the stock "routine running" byte 0x20000011, written
    at the start and end of both routines and read nowhere before);
  * Cable Test GUI messages 0x0F..0x12 run only on the Cable Test screen (sysState 4): a
    test queued before the user left can no longer run over Home or SPEED;
  * after a test, "Test Retry" is posted only if the screen is still armed; after a Back
    during the test the retry label is reset, so no stray button and the next screen says
    "Test Start";
  * each routine passes its own mode to the values drawing (no re-read of 0x20000010);
  * the button reads "Testing..." / "กำลังทดสอบ" while the test runs.

Not changed: the RX-mode open test (B8: both proposed changes regressed owner-confirmed
behaviour in the audit), the switch threshold 1240, sampling (11 samples 1 ms apart).
The margins are chosen from the emulator's electrical model, not from device captures.

    python cable_check.py            dry build
    python cable_check.py --write    experimental/LPM-10A-TX_PN2.28-cable-check.bin  (python build.py --profile pn2.28)
"""
import argparse
import contextlib
import hashlib
import io
from pathlib import Path

from lpm10a.image import PatchError
from lpm10a.thumb import assemble


VERSION = 'PN2.28'
PARENT_SHA256 = 'c12b127a634baa038c2504b8e30262a38f963c4900e0967094d7a7f4b1084420'   # PN2.27A release
PARENT_END = 0x0806A598
OUTPUT = (Path(__file__).resolve().parent.parent / 'experimental' / 'LPM-10A-TX_PN2.28-cable-check.bin')

# firmware
STATUS, MAP = 0x2000023E, 0x20000248        # u8[9] result codes, u16[9] map (index when crossed, bitmask when short)
MODE, BUSY, RETRY = 0x20000010, 0x20000011, 0x20000012
SYSSTATE = 0x2000013C                        # u8: 4 = Cable Test
FG, BG = 0x200001AC, 0x200001AE
LADDER = 0x0801E2BA                          # u16[9]: the RX unit's reading per remote pin
COLOURS = 0x0801E2CC                         # u16[9]: wire colours
LINE = 0x08016ADC                            # (x0, y0, x1, y1), colour FG
SHAPE = 0x08016D08                           # (x0, y0, x1, y1, [sp] colour) filled
RGB_LED, BEEP = 0x08010F94, 0x080116E0
RECORD_DRAW, BUTTON = 0x0800E1B4, 0x0801E320
LANG_IS, CJK_TEXT = 0x0800FD2C, 0x080176AC
CABLE_MSG = 0x0800C344                       # GUI handler for 0x0F..0x12
# sites
OK_POST = 0x0800C418                         # COUNT task, OK: bl GUI_MSG_SEND(0x11)
GUI_CALL = 0x0800F596                        # GUI dispatcher: bl 0x0800C344
RETRY_POSTS = (0x0800CB2E, 0x0800CE8C)       # both tails: bl GUI_MSG_SEND(0x12)
FRAME_CALLS = (0x0800C4F4, 0x0800CB7A)       # both routines' start: bl frame_hook (PN2.20)
FAR_VALUES, SWITCH_VALUES = 0x0800CB18, 0x0800CE76   # bl values_hook (PN2.21)
CLASSIFY, CLASSIFY_SKIP, NEXT_ROW = 0x0800C5CC, 0x0800C5D0, 0x0800C714
POST_PASS = 0x0800C71E                       # ldr r0,=status; ldrb r0,[r0,#8]
SHORT_MAX = 1240                             # stock's short threshold (0x4D8)
RAIL_MIN = 4000                              # stock's open threshold (0xFA0)
LEAK_SPAN = 150                              # counts; adjacent ladder values are >= 208 apart
JOIN_MARGIN = 4                              # counts over the row's lowest median, plus 1/16 of it
K_MIN, K_MAX = 3809, 4383                    # common RX-unit gain, Q12: 0.93 .. 1.07
RED, YELLOW, GREY, INTERIOR = 0xF800, 0xFFE0, 0x8410, 0x2105
TESTING_EN, TESTING_TH = 'Testing...', 'กำลังทดสอบ'


def _site(img, addr, target, what):
    expected = assemble(addr, f'bl {target}')
    if img.read(addr, 4) != expected:
        raise PatchError(f'cable-check: 0x{addr:08X} is not {what}')
    return expected.hex()


def apply(img):
    img.finalize()
    if hashlib.sha256(bytes(img.data)).hexdigest() != PARENT_SHA256:
        raise PatchError('cable-check requires the exact finalized PN2.27A parent')
    if img.cave_ptr != PARENT_END:
        raise PatchError('cable-check requires intact PN2.27A allocation metadata')
    med, hi, release = img.cable['med'], img.cable['hi'], img.cable['release']
    values_hook, frame_hook = img.cable_values['hook'], img.cable_clear['hook']
    send = img.syms['GUI_MSG_SEND']
    stock = {
        OK_POST: _site(img, OK_POST, send, 'the OK post of GUI 0x11'),
        GUI_CALL: _site(img, GUI_CALL, CABLE_MSG, 'the Cable Test GUI dispatch'),
        FAR_VALUES: _site(img, FAR_VALUES, values_hook, "PN2.21's values hook (far end)"),
        SWITCH_VALUES: _site(img, SWITCH_VALUES, values_hook, "PN2.21's values hook (switch)"),
        **{a: _site(img, a, send, 'the Test Retry post') for a in RETRY_POSTS},
        **{a: _site(img, a, frame_hook, "PN2.20's frame hook") for a in FRAME_CALLS},
    }
    for addr, hexbytes in ((CLASSIFY, '0026cb48'), (CLASSIFY_SKIP, '7844'), (POST_PASS, '7448007a'),
                           (0x0800CB2A, '11461220'), (0x0800CE88, '11461220')):
        if img.read(addr, len(hexbytes) // 2).hex() != hexbytes:
            raise PatchError(f'cable-check: 0x{addr:08X} is not the stock code')
    xtab = img.alloc_ram(18, align=2)              # u16[9]: the RX-unit row value classify_row decided on
    common = dict(STATUS=STATUS, MAP=MAP, MED=med, HI=hi, MODE=MODE, BUSY=BUSY, RETRY=RETRY,
                  SYSSTATE=SYSSTATE, FG=FG, BG=BG, LADDER=LADDER, COLOURS=COLOURS, XTAB=xtab)

    # ---- keys and messages ---------------------------------------------------------------
    ok_gate = img.emit_code(f'''
    ok_gate:                            ; COUNT task, r0 = 0x11: drop OK while a wire map is measuring
            ldr  r3, =BUSY
            ldrb r3, [r3]
            cbz  r3, post
            bx   lr
    post:   b.w  {send}
    ''', extra_syms=common, why='Cable Test: OK during a test is ignored')

    gui_guard = img.emit_code(f'''
    gui_guard:                          ; GUI task, r0 = 0x0F..0x12: only on the Cable Test screen
            ldr  r1, =SYSSTATE
            ldrb r1, [r1]
            cmp  r1, #4
            bne  drop
            b.w  {CABLE_MSG}
    drop:   bx   lr
    ''', extra_syms=common, why='Cable Test messages run only in sysState 4 (no test over Home / SPEED)')

    retry_post = img.emit_code(f'''
    retry_post:                         ; both tails, r0 = 0x12: the button only if the screen is still armed
            ldr  r3, =SYSSTATE
            ldrb r3, [r3]
            cmp  r3, #4
            bne  stale
            ldr  r3, =MODE
            ldrb r3, [r3]
            lsrs r3, r3, #4
            beq  stale
            b.w  {send}
    stale:  ldr  r3, =RETRY             ; Back came during the test: the next screen says "Test Start"
            movs r1, #0
            strb r1, [r3]
            bx   lr
    ''', extra_syms=common, why='Cable Test: no stray Test Retry after Back during a test')

    table = img.thai['table']
    testing_th = img.emit_code('.byte ' + ', '.join(str(b) for b in table.encode_cjk(TESTING_TH)),
                               why=f'Thai cells "{TESTING_TH}"')
    start_hook = img.emit_code(f'''
    start_hook:                         ; start of both routines: frame (PN2.20), then "Testing..." on the button
            push {{r4, lr}}
            sub  sp, #8
            bl   {frame_hook}
            ldr  r0, ={BUTTON}
            bl   {RECORD_DRAW}
            ldr  r0, =FG
            movw r1, #0xFFFF
            strh r1, [r0]
            ldr  r0, =BG
            movw r1, #0x7304
            strh r1, [r0]
            movs r0, #2
            bl   {LANG_IS}
            cmp  r0, #0
            bne  thai
            movs r0, #16
            str  r0, [sp]
            ldr  r0, =testing
            str  r0, [sp, #4]
            movs r0, #{120 - 4 * len(TESTING_EN)}
            movw r1, #294
            movs r2, #{8 * len(TESTING_EN)}
            movs r3, #16
            bl   gui_blit
            b    done
    thai:   movs r0, #120
            movw r1, #294
            ldr  r2, =TH
            movs r3, #4
            bl   {CJK_TEXT}
    done:   add  sp, #8
            pop  {{r4, pc}}
    testing: .asciz "{TESTING_EN}"
    ''', extra_syms=dict(common, TH=testing_th), why='Cable Test: the button says Testing... while measuring')

    # ---- values at the wire ends, mode passed by the caller ---------------------------------
    values = img.emit_code(f'''
    values:                             ; r0 = 0 switch, 1 RX unit; PN2.21's drawing, colour of the result
            push {{r4, r5, r6, r7, lr}}
            sub  sp, #28                ; [sp..8) blit args, [sp+8..24) text, [sp+24] mode
            str  r0, [sp, #24]
            bl   {release}              ; PN2.19: mux release and "Not connected"
            ldr  r0, =BG
            movw r1, #{INTERIOR}
            strh r1, [r0]
            movs r4, #0
    row:    lsls r5, r4, #3
            movs r6, #0
            movw r7, #0xFFFF
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
            cmp  r4, r6
            bgt  named
            adds r6, #1
    named:  movs r2, #0x2D
            movw r0, #{SHORT_MAX}
            cmp  r7, r0
            bhi  letter
            movs r2, #0x47
            cmp  r6, #8
            beq  letter
            movs r2, #0x31
            add  r2, r6
    letter: str  r2, [sp, #4]
            ldr  r0, [sp, #24]
            cmp  r0, #0
            bne  rx_fmt
            ldr  r1, =fmt_switch
            b    fmt
    rx_fmt: ldr  r1, =fmt_rx
    fmt:    mov  r2, r7
            mov  r0, sp
            adds r0, #8
            bl   sprintf
            mov  r5, r0
            ldr  r0, [sp, #24]
            cmp  r0, #0
            bne  colour
            ldr  r2, [sp, #4]
            mov  r0, sp
            adds r0, #8
            strb r2, [r0]
    colour: ldr  r0, =STATUS
            add  r0, r4
            ldrb r0, [r0]
            movw r1, #{RED}
            cmp  r0, #1
            beq  set_fg
            cmp  r0, #4
            beq  set_fg
            movw r1, #{YELLOW}
            cmp  r0, #0
            beq  set_fg
            movw r1, #{GREY}
            cmp  r0, #5
            beq  set_fg
            cmp  r0, #3
            bne  wire_colour
            movw r1, #{RED}
            ldr  r2, [sp, #24]
            cmp  r2, #0
            beq  set_fg
    wire_colour:
            ldr  r1, =COLOURS
            lsls r2, r4, #1
            add  r1, r2
            ldrh r1, [r1]
    set_fg: ldr  r0, =FG
            strh r1, [r0]
            movs r0, #12
            str  r0, [sp]
            mov  r0, sp
            adds r0, #8
            str  r0, [sp, #4]
            movs r0, #24
            muls r0, r4, r0
            adds r0, #62
            mov  r1, r0
            movs r2, #6
            muls r2, r5, r2
            movs r0, #207
            subs r0, r0, r2
            movs r3, #12
            bl   gui_blit
            adds r4, #1
            cmp  r4, #9
            blt  row
            add  sp, #28
            pop  {{r4, r5, r6, r7, pc}}
    fmt_switch: .asciz "? %4d"
    fmt_rx:     .asciz "%4d"
    ''', extra_syms=common, why='Cable Test: readings at the wire ends, mode from the caller, colour of the result')

    far_tail = img.emit_code(f'''
    far_tail:
            push {{r4, lr}}
            movs r0, #1
            bl   {values}
            pop  {{r4, pc}}
    ''', why='Cable Test RX unit: values in the RX-unit format')

    # ---- switch mode: partner check ------------------------------------------------------------
    switch_tail = img.emit_code(f'''
    switch_tail:                        ; after the stock switch drawing (LED already set green / red)
            push {{r4, r5, r6, r7, lr}}
            sub  sp, #44                ; [sp..8) args, +8 mask u16[8], +24 partner u8[8], +32 fault, +36 switch
            movs r0, #0
            str  r0, [sp, #32]
            movs r4, #0                 ; signal row
    row_a:  movw r7, #0xFFFF            ; lowest median of the row (shield slot left out)
            movs r5, #0
    scan_a: mov  r2, r5                 ; sensed pin = slot + (slot >= row)
            cmp  r4, r5
            bgt  pin_a
            adds r2, #1
    pin_a:  cmp  r2, #8
            beq  next_a
            lsls r0, r4, #3
            add  r0, r5
            lsls r0, r0, #1
            ldr  r1, =MED
            add  r1, r0
            ldrh r0, [r1]
            cmp  r0, r7
            bhs  next_a
            mov  r7, r0
    next_a: adds r5, #1
            cmp  r5, #8
            blt  scan_a
            movs r3, #0                 ; mask of joined pins
            movw r0, #{SHORT_MAX}
            cmp  r7, r0
            bhi  store
            lsrs r1, r7, #4             ; limit = m1 + 4 + m1/16, at most 1240
            add  r1, r7
            adds r1, #{JOIN_MARGIN}
            cmp  r1, r0
            bls  lim_ok
            mov  r1, r0
    lim_ok: movs r5, #0
    scan_b: mov  r2, r5
            cmp  r4, r5
            bgt  pin_b
            adds r2, #1
    pin_b:  cmp  r2, #8
            beq  next_b
            lsls r0, r4, #3
            add  r0, r5
            lsls r0, r0, #1
            ldr  r6, =MED
            add  r6, r0
            ldrh r0, [r6]
            cmp  r0, r1
            bhi  next_b
            ldr  r6, =bits
            lsls r0, r2, #1
            add  r6, r0
            ldrh r6, [r6]
            orrs r3, r6
    next_b: adds r5, #1
            cmp  r5, #8
            blt  scan_b
    store:  mov  r0, sp
            adds r0, #8
            lsls r1, r4, #1
            add  r0, r1
            strh r3, [r0]
            adds r4, #1
            cmp  r4, #8
            blt  row_a

            mov  r5, sp                 ; r5 = masks
            adds r5, #8
            ldrh r0, [r5, #6]           ; 4, 5, 7 and 8 tied together (10/100 port): two good pairs
            cmp  r0, #0xD0
            bne  pairs
            ldrh r0, [r5, #8]
            cmp  r0, #0xC8
            bne  pairs
            ldrh r0, [r5, #12]
            cmp  r0, #0x98
            bne  pairs
            ldrh r0, [r5, #14]
            cmp  r0, #0x58
            bne  pairs
            movs r0, #0x10
            strh r0, [r5, #6]
            movs r0, #0x08
            strh r0, [r5, #8]
            movs r0, #0x80
            strh r0, [r5, #12]
            movs r0, #0x40
            strh r0, [r5, #14]
    pairs:  movs r6, #0                 ; T568 pairs joined each only to its own partner
            ldrh r0, [r5, #0]
            cmp  r0, #0x02
            bne  p36
            ldrh r0, [r5, #2]
            cmp  r0, #0x01
            bne  p36
            adds r6, #1
    p36:    ldrh r0, [r5, #4]
            cmp  r0, #0x20
            bne  p45
            ldrh r0, [r5, #10]
            cmp  r0, #0x04
            bne  p45
            adds r6, #1
    p45:    ldrh r0, [r5, #6]
            cmp  r0, #0x10
            bne  p78
            ldrh r0, [r5, #8]
            cmp  r0, #0x08
            bne  p78
            adds r6, #1
    p78:    ldrh r0, [r5, #12]
            cmp  r0, #0x80
            bne  counted
            ldrh r0, [r5, #14]
            cmp  r0, #0x40
            bne  counted
            adds r6, #1
    counted:
            str  r6, [sp, #36]

            movs r4, #0                 ; classify the rows stock drew as connected
    row_c:  ldr  r0, =STATUS
            add  r0, r4
            ldrb r0, [r0]
            cmp  r0, #2
            bne  next_c
            mov  r0, sp
            adds r0, #8
            lsls r1, r4, #1
            add  r0, r1
            ldrh r3, [r0]               ; mask
            ldr  r0, [sp, #36]
            cmp  r0, #2
            blt  short                  ; no switch at the far end: any joined wire is a short
            ldr  r0, =expected
            add  r0, r1
            ldrh r0, [r0]
            cmp  r3, r0
            beq  next_c                 ; its own partner only
            cmp  r3, #0
            beq  short
            subs r0, r3, #1
            ands r0, r3
            cmp  r0, #0
            bne  short
            movs r1, #3                 ; one other pin: miswire
            movw r2, #{RED}
            b    mark
    short:  movs r1, #0
            movw r2, #{YELLOW}
    mark:   ldr  r0, =STATUS
            add  r0, r4
            strb r1, [r0]
            ldr  r0, =FG
            strh r2, [r0]
            movs r0, #1
            str  r0, [sp, #32]
            movs r1, #24
            muls r1, r4, r1
            adds r1, #68
            mov  r3, r1
            movs r0, #25
            movs r2, #207
            bl   {LINE}
    next_c: adds r4, #1
            cmp  r4, #8
            blt  row_c

            ldr  r0, =STATUS            ; the shield row
            ldrb r1, [r0, #8]
            cmp  r1, #2
            bne  g_open
            movs r1, #0                 ; a pin reaches the shield: short
            strb r1, [r0, #8]
            movs r0, #1
            str  r0, [sp, #32]
            movw r2, #{YELLOW}
            b    g_line
    g_open: cmp  r1, #1
            bne  fault
            movs r1, #5                 ; a switch gives the shield nowhere to go: not tested
            strb r1, [r0, #8]
            movw r0, #{INTERIOR}        ; wipe the X
            str  r0, [sp]
            movs r0, #112
            movw r1, #{260 - 4}
            movs r2, #120
            movw r3, #{260 + 4}
            bl   {SHAPE}
            movw r2, #{GREY}
    g_line: ldr  r0, =FG
            strh r2, [r0]
            movs r0, #25
            movw r1, #260
            movs r2, #207
            mov  r3, r1
            bl   {LINE}
    fault:  ldr  r0, [sp, #32]
            cmp  r0, #0
            beq  values_
            movs r0, #2
            bl   {BEEP}
            movs r0, #1
            bl   {RGB_LED}
    values_:
            movs r0, #0
            bl   {values}
            add  sp, #44
            pop  {{r4, r5, r6, r7, pc}}
            .align 2
    bits:     .short 0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x100
    expected: .short 0x02, 0x01, 0x20, 0x10, 0x08, 0x04, 0x80, 0x40
    ''', extra_syms=common, why='Cable Test switch mode: each wire must reach its own pair partner')

    # ---- RX unit mode: nearest ladder value, then plausibility ------------------------------
    near_idx = img.emit_code('''
    near_idx:                           ; r0 = reading -> r0 = index of the nearest ladder value (ties: the lower)
            push {r4, lr}
            movs r1, #0
            movs r3, #0
            movw r2, #0xFFFF
    loop:   ldr  r4, =LADDER
            add  r4, r1
            add  r4, r1
            ldrh r4, [r4]
            subs r4, r0, r4
            bpl  dist
            rsbs r4, r4, #0
    dist:   cmp  r4, r2
            bhs  next
            mov  r2, r4
            mov  r3, r1
    next:   adds r1, #1
            cmp  r1, #9
            blt  loop
            mov  r0, r3
            pop  {r4, pc}
    ''', extra_syms=common, why='Cable Test RX unit: nearest ladder value')

    classify_row = img.emit_code(f'''
    classify_row:                       ; r4 = driven pin, neither short nor open; writes status / map / XTAB
            push {{r4, r5, r6, r7, lr}}
            sub  sp, #12                ; [sp] lowest, [sp+4] highest kept median
            movs r6, #0
            movs r7, #0
            movw r0, #0xFFFF
            str  r0, [sp]
            movs r0, #0
            str  r0, [sp, #4]
            movs r5, #0
    slot:   lsls r0, r4, #3
            add  r0, r5
            lsls r0, r0, #1
            ldr  r1, =HI
            add  r1, r0
            ldrh r1, [r1]
            movw r2, #{RAIL_MIN}
            cmp  r1, r2
            bhi  next                   ; touched the rail region: floating, not a ladder reading
            ldr  r1, =MED
            add  r1, r0
            ldrh r0, [r1]
            movw r2, #{SHORT_MAX}
            cmp  r0, r2
            bls  next
            adds r6, #1
            add  r7, r0
            ldr  r1, [sp]
            cmp  r0, r1
            bhs  not_lo
            str  r0, [sp]
    not_lo: ldr  r1, [sp, #4]
            cmp  r0, r1
            bls  next
            str  r0, [sp, #4]
    next:   adds r5, #1
            cmp  r5, #8
            blt  slot
            movs r0, #4                 ; nothing usable: unknown
            cmp  r6, #0
            beq  put
            cmp  r6, #4
            blo  mean
            ldr  r0, [sp]               ; four or more: drop the lowest and the highest
            subs r7, r7, r0
            ldr  r0, [sp, #4]
            subs r7, r7, r0
            subs r6, #2
    mean:   udiv r7, r7, r6
            ldr  r0, =XTAB
            lsls r1, r4, #1
            add  r0, r1
            strh r7, [r0]
            mov  r0, r7
            bl   {near_idx}             ; provisional; post_pass decides with the common gain
            mov  r6, r0
            movs r0, #2
            cmp  r6, r4
            beq  put
            ldr  r1, =MAP
            lsls r2, r4, #1
            add  r1, r2
            strh r6, [r1]
            movs r0, #3
    put:    ldr  r1, =STATUS
            add  r1, r4
            strb r0, [r1]
            add  sp, #12
            pop  {{r4, r5, r6, r7, pc}}
    ''', extra_syms=common, why='Cable Test RX unit: nearest ladder value of the non-floating slots')

    post_pass = img.emit_code(f'''
    post_pass:                          ; after the measure loop; returns r0 = status[8] (stock's next use)
            push {{r4, r5, r6, r7, lr}}
            sub  sp, #52                ; [sp..36) gain ratios u32[9] sorted, [sp+36..45) landing pin per row
            movs r4, #0                 ; common gain k (Q12): median of X / nearest ladder value over the rows
            movs r5, #0
    cal:    ldr  r0, =STATUS
            add  r0, r4
            ldrb r0, [r0]
            cmp  r0, #2
            beq  cal_x
            cmp  r0, #3
            bne  cal_next
    cal_x:  ldr  r0, =XTAB
            lsls r1, r4, #1
            add  r0, r1
            ldrh r6, [r0]
            mov  r0, r6
            bl   {near_idx}
            ldr  r1, =LADDER
            lsls r0, r0, #1
            add  r1, r0
            ldrh r1, [r1]
            lsls r0, r6, #12
            udiv r0, r0, r1
            mov  r2, r5                 ; insert into the sorted ratios
    ins:    cmp  r2, #0
            beq  ins_put
            subs r3, r2, #1
            lsls r3, r3, #2
            mov  r7, sp
            add  r7, r3
            ldr  r1, [r7]
            cmp  r1, r0
            bls  ins_put
            str  r1, [r7, #4]
            subs r2, #1
            b    ins
    ins_put:
            lsls r3, r2, #2
            mov  r7, sp
            add  r7, r3
            str  r0, [r7]
            adds r5, #1
    cal_next:
            adds r4, #1
            cmp  r4, #9
            blt  cal
            movw r6, #4096
            cmp  r5, #3
            blo  have_k
            lsrs r0, r5, #1
            lsls r0, r0, #2
            mov  r7, sp
            add  r7, r0
            ldr  r6, [r7]
            movw r0, #{K_MIN}
            cmp  r6, r0
            bhs  k_lo_ok
            mov  r6, r0
    k_lo_ok:
            movw r0, #{K_MAX}
            cmp  r6, r0
            bls  have_k
            mov  r6, r0
    have_k: movs r4, #0                 ; every landed row: nearest ladder value of X / k
    recl:   ldr  r0, =STATUS
            add  r0, r4
            ldrb r0, [r0]
            cmp  r0, #2
            beq  recl_x
            cmp  r0, #3
            bne  recl_next
    recl_x: ldr  r0, =XTAB
            lsls r1, r4, #1
            add  r0, r1
            ldrh r0, [r0]
            lsls r0, r0, #12
            udiv r0, r0, r6
            bl   {near_idx}
            movs r1, #2
            cmp  r0, r4
            beq  recl_put
            ldr  r2, =MAP
            lsls r3, r4, #1
            add  r2, r3
            strh r0, [r2]
            movs r1, #3
    recl_put:
            ldr  r0, =STATUS
            add  r0, r4
            strb r1, [r0]
    recl_next:
            adds r4, #1
            cmp  r4, #9
            blt  recl

            movs r4, #0
    land:   ldr  r0, =STATUS
            add  r0, r4
            ldrb r0, [r0]
            movs r1, #0xFF
            cmp  r0, #2
            bne  land3
            mov  r1, r4
            b    land_put
    land3:  cmp  r0, #3
            bne  land_put
            ldr  r2, =MAP
            lsls r3, r4, #1
            add  r2, r3
            ldrh r1, [r2]
    land_put:
            mov  r2, sp
            adds r2, #36
            add  r2, r4
            strb r1, [r2]
            adds r4, #1
            cmp  r4, #9
            blt  land

            movs r4, #0                 ; two wires on one remote pin: both unknown
    dup_a:  mov  r0, sp
            adds r0, #36
            add  r0, r4
            ldrb r6, [r0]
            cmp  r6, #0xFF
            beq  dup_next_a
            adds r5, r4, #1
    dup_b:  cmp  r5, #9
            bge  dup_next_a
            mov  r0, sp
            adds r0, #36
            add  r0, r5
            ldrb r0, [r0]
            cmp  r0, r6
            bne  dup_next_b
            movs r2, #4
            ldr  r1, =STATUS
            add  r1, r4
            strb r2, [r1]
            ldr  r1, =STATUS
            add  r1, r5
            strb r2, [r1]
    dup_next_b:
            adds r5, #1
            b    dup_b
    dup_next_a:
            adds r4, #1
            cmp  r4, #9
            blt  dup_a

            ldr  r0, =STATUS            ; landing on the shield needs a shield row that is not open / unknown
            ldrb r7, [r0, #8]
            cmp  r7, #1
            beq  g_chk
            cmp  r7, #4
            bne  leak
    g_chk:  movs r4, #0
    g_loop: ldr  r1, =STATUS
            add  r1, r4
            ldrb r2, [r1]
            cmp  r2, #3
            bne  g_next
            mov  r0, sp
            adds r0, #36
            add  r0, r4
            ldrb r0, [r0]
            cmp  r0, #8
            bne  g_next
            movs r2, #4
            strb r2, [r1]
    g_next: adds r4, #1
            cmp  r4, #8
            blt  g_loop

    leak:   movs r4, #0                 ; every wire at one level: leakage, not an RX unit
            movs r5, #0
            movw r6, #0xFFFF
            movs r7, #0
    u_loop: ldr  r0, =STATUS
            add  r0, r4
            ldrb r0, [r0]
            cmp  r0, #0
            beq  done                   ; a short: a real cable
            cmp  r0, #2
            beq  u_count
            cmp  r0, #3
            bne  u_next
    u_count:
            adds r5, #1
            ldr  r1, =XTAB
            lsls r2, r4, #1
            add  r1, r2
            ldrh r1, [r1]
            cmp  r1, r6
            bhs  u_hi
            mov  r6, r1
    u_hi:   cmp  r1, r7
            bls  u_next
            mov  r7, r1
    u_next: adds r4, #1
            cmp  r4, #8
            blt  u_loop
            cmp  r5, #3
            blo  done
            subs r0, r7, r6
            cmp  r0, #{LEAK_SPAN}
            bhi  done
            movs r4, #0
    d_loop: ldr  r1, =STATUS
            add  r1, r4
            ldrb r0, [r1]
            cmp  r0, #2
            beq  demote
            cmp  r0, #3
            bne  d_next
    demote: movs r0, #4
            strb r0, [r1]
    d_next: adds r4, #1
            cmp  r4, #9
            blt  d_loop
    done:   ldr  r0, =STATUS
            ldrb r0, [r0, #8]
            add  sp, #52
            pop  {{r4, r5, r6, r7, pc}}
    ''', extra_syms=common, why='Cable Test RX unit: refuse maps no RX unit can produce')

    # ---- sites ------------------------------------------------------------------------------
    img.poke(OK_POST, stock[OK_POST], assemble(OK_POST, f'bl {ok_gate}'), 'OK: no second test while one runs')
    img.poke(GUI_CALL, stock[GUI_CALL], assemble(GUI_CALL, f'bl {gui_guard}'), 'Cable Test messages only in sysState 4')
    for a in RETRY_POSTS:
        img.poke(a, stock[a], assemble(a, f'bl {retry_post}'), 'Test Retry only on the armed screen')
    for a in FRAME_CALLS:
        img.poke(a, stock[a], assemble(a, f'bl {start_hook}'), 'test start: frame, then "Testing..."')
    img.poke(FAR_VALUES, stock[FAR_VALUES], assemble(FAR_VALUES, f'bl {far_tail}'), 'RX unit: values, mode fixed')
    img.poke(SWITCH_VALUES, stock[SWITCH_VALUES], assemble(SWITCH_VALUES, f'bl {switch_tail}'),
             'switch: partner check, then values')
    img.poke(CLASSIFY, '0026cb48', assemble(CLASSIFY, f'bl {classify_row}'), 'RX unit: nearest ladder value')
    img.poke(CLASSIFY_SKIP, '7844', assemble(CLASSIFY_SKIP, f'b {NEXT_ROW}'), 'RX unit: skip the stock window rules')
    img.poke(POST_PASS, '7448007a', assemble(POST_PASS, f'bl {post_pass}'), 'RX unit: plausibility of the map')
    for site in (0x08011660, 0x08012E6C):
        img.set_string(site, VERSION)
    img.cable_check = dict(ok_gate=ok_gate, gui_guard=gui_guard, retry_post=retry_post, start_hook=start_hook,
                           values=values, far_tail=far_tail, switch_tail=switch_tail,
                           classify_row=classify_row, post_pass=post_pass, xtab=xtab, testing_th=testing_th,
                           near_idx=near_idx)
    return img


def build_candidate():
    import tone_alignment
    return apply(tone_alignment.build_candidate()).finalize()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    with contextlib.redirect_stdout(io.StringIO()):
        img = build_candidate()
    data = bytes(img.data)
    digest = hashlib.sha256(data).hexdigest()
    print(f'{VERSION}: {len(data)} bytes; SHA256 {digest}')
    if args.write:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_bytes(data)
        OUTPUT.with_name('TX-PN2.28-SHA256SUMS.txt').write_text(f'{digest}  {OUTPUT.name}\n', encoding='ascii')
        print(f'Wrote {OUTPUT}')
    else:
        print('Dry build; use --write for the candidate file. Not device-tested.')


if __name__ == '__main__':
    main()
