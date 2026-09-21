"""PN 2.17: the SPEED screen shows what the switch port offers, next to what the link got.

Stock's SPEED test negotiates a link and prints the resolved speed and duplex from the
PHY's status register 0x11 (FORMULA-AUDIT section 2).  That answers "what did I get"
but not "what could the port do": a 100 Mbps result on a gigabit port means the cable
(pairs 4-5 / 7-8) is the problem, on a 100 Mbps port it is normal.  Professional link
testers print the partner's advertised speeds for exactly this reason.  PN 2.17 adds a
third row in the same style under Link Type:

    Switch  |  10/100/1000            (สวิตช์ in Thai; the value is ASCII in both)

The speeds come from the two IEEE 802.3 Clause 22 / 40 registers every PHY has:
register 5 (auto-negotiation link partner ability: bits 5/6 = 10BASE-T half/full,
7/8 = 100BASE-TX half/full, 9 = 100BASE-T4) and register 10 (1000BASE-T status:
bits 10/11 = partner 1000BASE-T half/full).  A partner that does not auto-negotiate
(parallel detection, a fixed-speed port) leaves register 5 at 0: the row says
"No autoneg".  Nothing is written to the PHY.

Three sites, none of them in the measurement:

  * 0x0800DA12 (LENG_link_test, net task, right after the link came up and stock's
    `phy_ext_write(0x100, 6)`): `movs r0, #0x11; bl mdio_read` becomes `bl read_hook;
    nop`.  The hook reads registers 5 and 10 into two RAM cells and then register 0x11,
    which it returns in r0 exactly as the stock call did.  FLASH passes here too and
    pays two extra MDIO reads per link; it never shows them.
  * 0x0801A962 (the SPEED screen builder, GUI message 0x1D): `bl 0x0801A724` (the Test
    button) becomes `bl build_hook`, which draws the button as before and then the
    third row's box and label cell with the stock record drawer 0x0800E1B4 and the
    label with gui_blit ("Switch") or, in Thai, the proportional cell drawer with the
    string thai-ui already ships for "สวิตช์".
  * LENG_speed_result 0x0801A9A8 (called by the net task after a test and by the
    builder when a result is on screen): its first two instructions become
    `b.w result_hook`, which runs the stock body through a trampoline and, when it
    returns 0 (result drawn), clears the third row's value cell like stock clears the
    other two and posts the speeds text box centred at x 160 -- the same
    gui_draw_text_box mode 0x20 call the Speed and Link Type values use.  A retry
    (return 1) and an "Error!!" result (speed bits 11) leave the cell empty.

Row geometry follows the two stock rows (boxes at y 107 and 170, 49 px, label cell
12..100, value centred at x 160): the third box sits at y 225, 7 px under Link Type
and 7 px above the Test Retry button (y 280).
"""
import hashlib
import struct

from lpm10a.image import PatchError
from lpm10a.thumb import assemble


PATCH_ID = 'speed-partner'
VERSION = 'PN 2.17'
PARENT_SHA256 = '1b6cbfab6f1f01e9e160ad706cbd00a32669278fe451c39ede2c7e9c7c88ac18'   # PN 2.16

READ_SITE = 0x0800DA12          # LENG_link_test: movs r0, #0x11; bl mdio_read
READ_STOCK = '1120 09f06cff'
BUILD_SITE = 0x0801A962         # SPEED builder: bl 0x0801A724 (Test Start / Retry button)
BUILD_STOCK = 'fff7dffe'
BUTTON_DRAW = 0x0801A724
RESULT = 0x0801A9A8             # LENG_speed_result: push {r1-r7, lr}; movs r5, #0xA0
RESULT_STOCK = 'feb5 a025'
RESULT_BODY = 0x0801A9AC
RECORD_DRAW = 0x0800E1B4        # (record*): box with border/fill from a 14-byte layout record
LANG_IS = 0x0800FD2C            # (2) -> language == 2 (Thai)
CJK_TEXT = 0x080176AC           # thai-ui: b.w thai_cjk_text(x, y, cells, count)
STATUS_REG11 = 0x200002B6

ROW_Y = 225                     # box 225..273; Link Type's box ends at 218, the button starts at 280
LABEL_EN = 'Switch'
LABEL_TH = 'สวิตช์'
TEXT_Y = ROW_Y + 16             # rows 1 and 2: 123 = 107 + 16, 186 = 170 + 16
LABEL_X = 56 - 4 * len(LABEL_EN)  # centred in the label cell x 12..100 like "Speed" (36) and "Link Type" (20)
VALUE_X = 160
CELL_BG, LABEL_BG, WHITE = 0x2105, 0x4A69, 0xFFFF
# partner speeds by (has10 | has100 << 1 | has1000 << 2); 12 bytes each, NUL padded
SPEEDS = ('No autoneg', '10', '100', '10/100', '1000', '10/1000', '100/1000', '10/100/1000')


def register(patch):
    @patch(PATCH_ID, "SPEED: a 'Switch' row lists the speeds the link partner advertises",
           risk='low', default=False, group='measure',
           requires=('thai-ui', 'about-values'))
    def speed_partner(img):
        img.finalize()
        if hashlib.sha256(bytes(img.data)).hexdigest() != PARENT_SHA256:
            raise PatchError('speed-partner requires the exact finalized PN 2.16 parent')
        for site, stock in ((READ_SITE, READ_STOCK), (BUILD_SITE, BUILD_STOCK), (RESULT, RESULT_STOCK)):
            if img.read(site, len(bytes.fromhex(stock.replace(' ', '')))).hex() != stock.replace(' ', ''):
                raise PatchError(f'speed-partner: 0x{site:08X} is not the stock code')
        thai_label = img.thai['where'][LABEL_TH]
        if any(len(s) > 11 for s in SPEEDS):
            raise PatchError('speed-partner: a speeds string does not fit its 12-byte slot')
        cells = img.alloc_ram(4)                     # [0] register 5 (partner ability), [2] register 10 (1000BASE-T status)

        read = img.emit_code('''
        read_hook:                      ; from 0x0800DA12, link up: partner registers, then stock's reg 0x11 in r0
                push {r4, lr}
                ldr  r4, =CELLS
                movs r0, #5
                bl   mdio_read
                strh r0, [r4]
                movs r0, #10
                bl   mdio_read
                strh r0, [r4, #2]
                movs r0, #0x11
                bl   mdio_read
                pop  {r4, pc}
        ''', extra_syms=dict(CELLS=cells), why='SPEED: read the link partner ability registers after link-up')

        build = img.emit_code(f'''
        build_hook:                     ; from the SPEED builder: the button as before, then the Switch row
                push {{r4, r5, r6, lr}}
                sub  sp, #8
                bl   {BUTTON_DRAW}
                ldr  r0, =row_box
                bl   {RECORD_DRAW}
                ldr  r0, =row_label
                bl   {RECORD_DRAW}
                ldr  r4, =0x200001AC
                ldrh r5, [r4]           ; colour globals: white on the label cell, restored afterwards
                ldrh r6, [r4, #2]
                movw r0, #{WHITE}
                strh r0, [r4]
                movw r0, #{LABEL_BG}
                strh r0, [r4, #2]
                movs r0, #2
                bl   {LANG_IS}
                cmp  r0, #0
                bne  thai
                movs r0, #16
                str  r0, [sp]
                ldr  r0, =label_en
                str  r0, [sp, #4]
                movs r0, #{LABEL_X}
                movs r1, #{TEXT_Y}
                movs r2, #{8 * len(LABEL_EN)}
                movs r3, #16
                bl   gui_blit
                b    restore
        thai:   movs r0, #56             ; centred in the label cell, count 1 = centre on x (thai_cjk_text)
                movs r1, #{TEXT_Y}
                ldr  r2, ={thai_label}
                movs r3, #1
                bl   {CJK_TEXT}
        restore:
                strh r5, [r4]
                strh r6, [r4, #2]
                add  sp, #8
                pop  {{r4, r5, r6, pc}}
        label_en:
                .asciz "{LABEL_EN}"
                .align 4
        row_box:                        ; x, y, w, h, border, fill, style (the two stock rows use the same values)
                .short 7, {ROW_Y}, 218, 48, {CELL_BG}, {LABEL_BG}
                .byte 4, 0
                .short 0
        row_label:
                .short 12, {ROW_Y + 4}, 88, 40, {LABEL_BG}, {LABEL_BG}
                .byte 2, 0
                .short 0
        ''', why='SPEED builder: the Switch row box, label cell and label')

        result = img.emit_code(f'''
        result_hook:                    ; LENG_speed_result's entry: stock body, then the Switch value
                push {{r4, lr}}
                bl   stock_body
                mov  r4, r0             ; 0 = result drawn, 1 = the caller retries the test
                cmp  r4, #0
                bne  out
                bl   draw_value
        out:    mov  r0, r4
                pop  {{r4, pc}}
        stock_body:
                push {{r1, r2, r3, r4, r5, r6, r7, lr}}
                movs r5, #0xA0
                b.w  {RESULT_BODY}
        draw_value:
                push {{r4, lr}}
                sub  sp, #8
                movw r0, #{CELL_BG}
                str  r0, [sp]
                movs r0, #112           ; clear the value cell as stock clears rows 1 and 2
                movw r1, #{ROW_Y + 7}
                movs r2, #208
                movw r3, #{ROW_Y + 41}
                bl   gui_draw_rect
                ldr  r0, =STATUS
                ldrh r0, [r0]
                lsrs r0, r0, #14
                cmp  r0, #3             ; "Error!!": no speed resolved, nothing to compare with
                beq  done
                ldr  r4, =CELLS
                ldrh r0, [r4]           ; register 5
                movs r3, #0
                lsrs r1, r0, #5
                movs r2, #3             ; bits 5, 6: 10BASE-T
                ands r1, r2
                beq  no10
                movs r3, #1
        no10:   lsrs r1, r0, #7
                movs r2, #7             ; bits 7, 8, 9: 100BASE-TX / T4
                ands r1, r2
                beq  no100
                adds r3, #2
        no100:  ldrh r0, [r4, #2]       ; register 10
                lsrs r1, r0, #10
                movs r2, #3             ; bits 10, 11: 1000BASE-T
                ands r1, r2
                beq  no1000
                adds r3, #4
        no1000: movs r0, #12
                muls r3, r0, r3
                ldr  r0, =speeds
                add  r0, r3
                str  r0, [sp, #4]
                movs r0, #0x20          ; 8x16 ASCII centred on x
                str  r0, [sp]
                movs r0, #{VALUE_X}
                movw r1, #{TEXT_Y}
                movw r2, #{CELL_BG}
                movw r3, #{WHITE}
                bl   gui_draw_text_box
        done:   add  sp, #8
                pop  {{r4, pc}}
                .align 4
        speeds:
        ''' + '\n'.join(f'        .asciz "{s}"\n        .space {11 - len(s)}' for s in SPEEDS),
            extra_syms=dict(CELLS=cells, STATUS=STATUS_REG11),
            why='LENG_speed_result: the Switch row value after the stock result')

        img.poke(READ_SITE, READ_STOCK, assemble(READ_SITE, f'bl {read}\n nop'),
                 'LENG_link_test: partner registers 5 and 10 before reg 0x11')
        img.poke(BUILD_SITE, BUILD_STOCK, assemble(BUILD_SITE, f'bl {build}'),
                 'SPEED builder: draw the Switch row after the button')
        img.poke(RESULT, RESULT_STOCK, assemble(RESULT, f'b.w {result}'),
                 'LENG_speed_result: draw the Switch value after the stock result')
        for site in (0x08011660, 0x08012E6C):
            img.set_string(site, VERSION)
        img.speed_partner = dict(cells=cells, read=read, build=build, result=result,
                                 row_y=ROW_Y, text_y=TEXT_Y, label_x=LABEL_X, thai_label=thai_label)
