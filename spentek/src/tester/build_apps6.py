"""TX PN2.34C -> 'PN2.34H': tools on a third home page.

Home screen: a third page with a Pinout tile and a Link tile (own icons), three page dots, and
navigation that wraps across three pages. OK on a tile opens that tool; Back returns to the home
screen. Inside a tool, LEFT / RIGHT switch between tools. The About screen is back to stock.
(Supersedes the About-page builds PN2.34A / PN2.34B.)

Pages (LEFT / RIGHT on the About screen): 0 About, 1 Pinout reference, 2 Link monitor.
- The About draw routine is entered through a hook: page 0 runs the stock code, other pages are
  drawn by this patch (no stock About drawing underneath, so no flash when a page refreshes).
- A once-a-second hook in the home task asks the GUI task to refresh the Link page while it is
  showing, and powers the network chip back down once the page is left.
- OK on a page is handled by the page (Link: reset the counters) and no longer opens Factory Reset.
"""
import hashlib, struct, sys
from keystone import Ks, KS_ARCH_ARM, KS_MODE_THUMB
PARENT_SHA = "283bdf66805fcafa0831198fcdc1b55114f86db3a32309452423d2f8efeb4ad9"   # PN2.34C cyber build
APP, HDR = 0x0800A000, 0x1000
GUI_MSG_SEND, GUI_BLIT, DRAW_SHAPE, SPRINTF = 0x0800E428, 0x080174E8, 0x08016D08, 0x0800A38C
MDIO_READ, MDIO_WRITE, PHY_EXT_WRITE, PHY_RESET = 0x080178F0, 0x08017AFC, 0x08018A9E, 0x08017E34
DRAW_BOX, ABOUT_BOX = 0x0800E1B4, 0x08064DFC      # box drawer and the About panel's layout record
FG, SYS, SETTINGS = 0x200001AC, 0x2000013C, 0x20000C78
ST, BUF = 0x2000FE40, 0x2000FE60      # patch state and a text buffer, high in the SDK scratch area
PANEL = 0x2105
ABOUT_ENTRY = 0x08011450              # push {r4,r5,r6,lr} ; sub sp,#0x58
SITE_ENTER = 0x08011386               # bl GUI_MSG_SEND when OK opens About from the settings list
SITE_KEYS = 0x08011394                # About showing: LEFT/RIGHT were ignored here (10 bytes)
TICK_ENTRY = 0x0800F968               # home_1s_housekeeping: push {r4,lr} ; ldr r0,=g_settings
ORANGE, GREEN, BLUE, BROWN, WHITE, GREY, RED = 0xFD20, 0x07E0, 0x001F, 0xC407, 0xFFFF, 0x8410, 0xF800
LINK = 2
NT = 3                                 # tool tiles on home page 3: sel 12..14 (Debug opens from Settings)
DEBUG = 4                              # Debug page
ITEM_DRAW, LIST_DRAW = 0x080101F0, 0x08011038     # settings_item_draw(item), settings list draw (GUI msg 0x32)
EDIT_SITE, MOVE_SITE = 0x080111DA, 0x080111BA     # value edit: cmp r5,#6 ; bhs default.  cursor move: bl post_item(old)
ITEM_POST, EDIT_EXIT, EDIT_DEFAULT = 0x080118E0, 0x0801136C, 0x080112D0
THEME = 0x0806B310                                # theme routine of the cyber build: uxth r0, r0 ; lsrs r1, r0, #11
THM = 0x20000C78 + 0xC6                           # spare byte of the settings block (saved at power-off): theme index
# name, red / green / blue weight (of 64) for the one-hue themes, kind: 0 one hue, 1 cyber, 2 stock, 3 inverted
THEMES = [("Cyber", 0, 0, 0, 1), ("Green", 0, 64, 0, 0), ("Stock", 0, 0, 0, 2), ("Amber", 32, 48, 0, 0),
          ("Ice", 20, 56, 32, 0), ("Red", 32, 0, 0, 0), ("Mono", 32, 64, 32, 0), ("Violet", 22, 14, 32, 0),
          ("Pink", 32, 22, 24, 0), ("Teal", 0, 56, 22, 0), ("Gold", 32, 58, 6, 0), ("Light", 0, 0, 0, 3)]
LISTBG = 0x31A7
MSG_SITE = 0x0800F488                  # GUI loop, a message was received: ldrb.w r0, [sp, #8]
TETRIS, NCYC = 3, 3                    # Tetris page; LEFT / RIGHT cycle only through pages below NCYC
POLL_SITE = 0x0800F466                 # GUI loop, r2 = queue timeout: add r1, sp, #8 ; ldr r0, =gui_queue
CURSOR_ENTRY = 0x08011174              # settings_cursor_move (UP / DOWN): push {r4,r5,r6,lr} ; mov r4, r0
GUI_QUEUE = 0x20000038
GET_PTR, SET_STATE, PUT_PIXEL = 0x0800F75C, 0x0800F77C, 0x08016BF0
HOME_NAV, HOME_DRAW_TILE, HOME_TILE_SKIP, OK_SITE, BACK_ENTRY = 0x08016850, 0x0800F268, 0x0800F3AA, 0x0800D322, 0x08011008

def pinout_page():
    b = [("W-Orange", ORANGE), ("Orange", ORANGE), ("W-Green", GREEN), ("Blue", BLUE),
         ("W-Blue", BLUE), ("Green", GREEN), ("W-Brown", BROWN), ("Brown", BROWN)]
    a = [("W-Green", GREEN), ("Green", GREEN), ("W-Orange", ORANGE), ("Blue", BLUE),
         ("W-Blue", BLUE), ("Orange", ORANGE), ("W-Brown", BROWN), ("Brown", BROWN)]
    L = [(17, 64, 16, WHITE, "Pinout"),
         (14, 86, 16, GREY, "Pin"), (54, 86, 16, GREY, "T568B"), (142, 86, 16, GREY, "T568A")]
    for i in range(8):
        y = 106 + 16 * i
        L += [(22, y, 16, WHITE, str(i + 1)), (54, y, 16, b[i][1], b[i][0]), (142, y, 16, a[i][1], a[i][0])]
    L += [(12, 242, 12, WHITE, "PoE A: 1,2 / 3,6    PoE B: 4,5 / 7,8"),
          (12, 258, 12, WHITE, "X-over 1<>3 2<>6, gig also 4<>7 5<>8"),
          (66, 290, 12, GREY, "<  >  switch tool")]
    return L

def link_page():
    return [(17, 64, 16, WHITE, "Link"),
            (12, 246, 12, GREY, "Time and drops count from when this"),
            (12, 260, 12, GREY, "page opened. MDI reading unverified."),
            (30, 290, 12, GREY, "OK reset counters    <  >  tool")]

def debug_page():
    return [(17, 64, 16, WHITE, "Debug"), (150, 68, 12, GREY, "OK clears log")]

PAGES = [pinout_page(), link_page(), [], debug_page()]

def icon_planes(draw_fn, w=48, h=40):
    from PIL import Image, ImageDraw
    a, b = Image.new("1", (w, h), 0), Image.new("1", (w, h), 0)
    draw_fn(ImageDraw.Draw(a), ImageDraw.Draw(b))
    def bits(im):
        out = bytearray()
        for y in range(h):
            for x0 in range(0, w, 8):
                v = 0
                for x in range(x0, min(x0 + 8, w)):
                    if im.getpixel((x, y)): v |= 0x80 >> (x - x0)
                out.append(v)
        return bytes(out)
    return bytes([w, h]) + bits(a) + bits(b)

def icon_pinout(a, b):                    # a jack seen from the front, eight contacts
    a.rounded_rectangle((3, 2, 44, 37), radius=4, outline=1, width=3)
    a.rectangle((17, 30, 30, 37), fill=0)                       # latch notch
    a.rectangle((14, 28, 33, 30), fill=1)
    a.rectangle((14, 28, 16, 37), fill=1); a.rectangle((31, 28, 33, 37), fill=1)
    for i in range(8):
        b.rectangle((9 + 4 * i, 8, 10 + 4 * i, 21), fill=1)

def icon_link(a, b):                      # two interlocked chain links and a status dot
    a.rounded_rectangle((3, 4, 27, 22), radius=8, outline=1, width=4)
    a.rounded_rectangle((20, 16, 44, 34), radius=8, outline=1, width=4)
    a.rectangle((20, 18, 23, 22), fill=0)                       # the lower link passes behind the upper one
    a.rectangle((24, 16, 27, 19), fill=0)
    b.ellipse((4, 28, 13, 37), fill=1)

def icon_tetris(a, b):                    # an S piece (white) on an L piece (orange)
    for x, y in ((1, 0), (2, 0), (0, 1), (1, 1)):
        a.rectangle((2 + 9 * x, 3 + 9 * y, 9 + 9 * x, 10 + 9 * y), fill=1)
    for x, y in ((0, 2), (1, 2), (2, 2), (2, 1)):
        b.rectangle((2 + 9 * x, 3 + 9 * y, 9 + 9 * x, 10 + 9 * y), fill=1)

def icon_debug(a, b):                     # a terminal window with a prompt
    a.rectangle((1, 3, 30, 28), outline=1, width=2)
    a.rectangle((1, 3, 30, 8), fill=1)
    b.line((6, 13, 11, 17), fill=1, width=2); b.line((11, 17, 6, 21), fill=1, width=2)
    b.rectangle((14, 21, 22, 22), fill=1)

ICONS = [icon_planes(icon_pinout), icon_planes(icon_link), icon_planes(icon_tetris, 32, 32)]
ks = Ks(KS_ARCH_ARM, KS_MODE_THUMB)
asm = lambda src, addr: bytes(ks.asm(src, addr)[0])

def page_data(lines):
    strs, blob = {}, b""
    for *_, t in lines:
        if t not in strs:
            strs[t] = len(blob); blob += t.encode("ascii") + b"\0"
    rec_len = 8 * len(lines) + 2
    rec = b"".join(struct.pack("<BBHHH", x, sz, y, col, rec_len + strs[t]) for x, y, sz, col, t in lines) + b"\xff\xff"
    out = rec + blob
    return out + b"\0" * (-len(out) % 4)

def build(parent, T_BASE=0x0806D000):
    d = bytearray(parent)
    assert hashlib.sha256(d).hexdigest() == PARENT_SHA, "expects the PN2.34C build"
    off, ln, end = struct.unpack_from("<III", d, 0x20)
    assert not any(d[off + ln:]) and ln % 4 == 0
    f = lambda a: a - APP + HDR
    rd = lambda a, n: bytes(d[f(a):f(a) + n])
    cave = APP + ln
    npages = len(PAGES) + 1
    data = [page_data(p) for p in PAGES]
    src = f"""
        b.w   enter_hook                    @ +0
        b.w   key_hook                      @ +4
        b.w   about_entry                   @ +8
        b.w   tick_hook                     @ +12
        b.w   ok_hook                       @ +16
        b.w   back_hook                     @ +20
        b.w   tile_hook                     @ +24
        b.w   poll_hook                     @ +28
        b.w   cursor_hook                   @ +32
        b.w   nav_fix                       @ +36
        b.w   msg_hook                      @ +40
        b.w   name_fix                      @ +44
        b.w   item_hook                     @ +48
        b.w   list_hook                     @ +52
        b.w   edit_fix                      @ +56
        b.w   move_fix                      @ +60
        b.w   theme2                        @ +64
    v_item_cont:  b.w {ITEM_DRAW + 4:#x}
    v_list_cont:  b.w {LIST_DRAW + 4:#x}
    v_item_post:  b.w {ITEM_POST:#x}
    v_edit_exit:  b.w {EDIT_EXIT:#x}
    v_edit_def:   b.w {EDIT_DEFAULT:#x}
    v_theme_cont: b.w {THEME + 4:#x}
    v_tlog:       b.w {T_BASE + 12:#x}
    v_tdebug:     b.w {T_BASE + 16:#x}
    v_tclear:     b.w {T_BASE + 20:#x}
    v_tmsg:       b.w {T_BASE + 24:#x}
    v_tpoll:      b.w {T_BASE:#x}
    v_tkey:       b.w {T_BASE + 4:#x}
    v_tenter:     b.w {T_BASE + 8:#x}
    v_cursor_cont: b.w {CURSOR_ENTRY + 4:#x}
    v_gui:        b.w {GUI_MSG_SEND:#x}
    v_blit:       b.w {GUI_BLIT:#x}
    v_box:        b.w {DRAW_BOX:#x}
    v_sprintf:    b.w {SPRINTF:#x}
    v_mdio_r:     b.w {MDIO_READ:#x}
    v_mdio_w:     b.w {MDIO_WRITE:#x}
    v_ext_w:      b.w {PHY_EXT_WRITE:#x}
    v_phy_reset:  b.w {PHY_RESET:#x}
    v_about_cont: b.w {ABOUT_ENTRY + 4:#x}
    v_tick_cont:  b.w {TICK_ENTRY + 4:#x}
    v_get_ptr:    b.w {GET_PTR:#x}
    v_set_state:  b.w {SET_STATE:#x}
    v_pixel:      b.w {PUT_PIXEL:#x}
    v_tile_skip:  b.w {HOME_TILE_SKIP:#x}
    v_back_cont:  b.w {BACK_ENTRY + 4:#x}

    enter_hook:                             @ r0 = 0x34, r1 = r2 = 0 : open About at page 0
        ldr   r3, st_addr
        strb  r1, [r3]
        b     v_gui

    key_hook:                               @ About showing, r4 = action ; r0 = 1 if the key was used
        push  {{r4, r5, r6, lr}}
        ldr   r5, st_addr
        ldrb  r0, [r5]
        cmp   r0, #{npages}
        blo   k_ok
        movs  r0, #0
    k_ok:
        cmp   r0, #{TETRIS}
        bne   k_nt
        movs  r0, #0                        @ Tetris: LEFT / RIGHT / OK go to the game, nothing else acts
        cmp   r4, #0x1e
        beq   k_t
        movs  r0, #1
        cmp   r4, #0x1f
        beq   k_t
        movs  r0, #4
        cmp   r4, #0x20
        bne   kused
    k_t:
        bl    v_tkey
        b     kused
    k_nt:
        cmp   r0, #{DEBUG}
        bne   k_nd
        cmp   r4, #0x20                     @ Debug: OK clears the log, other keys do nothing
        bne   kused
        bl    v_tclear
        movs  r0, #{DEBUG}
        b     kstore
    k_nd:
        cmp   r0, #0
        bne   k_tool
        cmp   r4, #0x1e                     @ About itself: LEFT / RIGHT are ignored, as in stock
        beq   kused
        cmp   r4, #0x1f
        beq   kused
        b     knone
    k_tool:
        cmp   r4, #0x1e
        beq   kprev
        cmp   r4, #0x1f
        beq   knext
        cmp   r4, #0x20
        bne   knone
        cmp   r0, #{LINK}
        bne   kused
        movs  r1, #0                        @ Link page: OK resets the counters
        strh  r1, [r5, #4]
        str   r1, [r5, #8]
    kused:
        movs  r0, #1
        pop   {{r4, r5, r6, pc}}
    knone:
        movs  r0, #0
        pop   {{r4, r5, r6, pc}}
    knext:
        adds  r0, #1
        cmp   r0, #{NCYC}
        blo   kstore
        movs  r0, #1
        b     kstore
    kprev:
        subs  r0, #1
        bne   kstore
        movs  r0, #{NCYC - 1}
    kstore:
        strb  r0, [r5]
        movs  r0, #1
        strb  r0, [r5, #1]                  @ full redraw wanted
        movs  r2, #0
        mov   r1, r2
        movs  r0, #0x36
        bl    v_gui
        movs  r2, #0
        mov   r1, r2
        movs  r0, #0x34
        bl    v_gui
        movs  r0, #1
        pop   {{r4, r5, r6, pc}}

    about_entry:                            @ replaces the first two instructions of the About draw routine
        ldr   r3, st_addr
        ldrb  r0, [r3]
        cmp   r0, #0
        beq   stock
        cmp   r0, #{npages}
        blo   page_draw
    stock:
        push  {{r4, r5, r6, lr}}
        sub   sp, #0x58
        b     v_about_cont

    page_draw:                              @ r0 = page ; returns to the About routine's caller
        push  {{r4, r5, r6, r7, lr}}
        sub   sp, #20
        mov   r6, r0
        ldr   r5, st_addr
        ldr   r3, fg_addr
        ldrh  r0, [r3]
        strh  r0, [sp, #8]
        ldrh  r0, [r3, #2]
        strh  r0, [sp, #10]                 @ keep the caller's colours
        ldrb  r0, [r5, #1]
        cmp   r0, #0
        beq   pd_dyn
        ldr   r0, box_addr
        bl    v_box
        ldr   r3, fg_addr                   @ header: TOOLS in place of SETTING
        movw  r0, #0xffff
        strh  r0, [r3]
        movs  r0, #0
        strh  r0, [r3, #2]
        movs  r0, #16
        str   r0, [sp]
        adr.w r0, s_tools
        str   r0, [sp, #4]
        movs  r0, #13
        movs  r1, #21
        movs  r2, #56
        movs  r3, #16
        bl    v_blit
        subs  r0, r6, #1
        adr   r7, page_table
        ldr   r1, [r7, r0, lsl #2]
        adds  r7, r7, r1
        mov   r4, r7
    pd_line:
        ldrb  r0, [r7]
        cmp   r0, #0xff
        beq   pd_dyn
        ldrh  r1, [r7, #2]
        ldrh  r2, [r7, #6]
        adds  r2, r2, r4
        ldrh  r3, [r7, #4]
        ldrb  r7, [r7, #1]                  @ size (r7 restored below)
        cmp   r7, #12
        beq   pd_small
        bl    text16
        b     pd_next
    pd_small:
        bl    text12
    pd_next:
        b     pd_adv
    pd_dyn:
        cmp   r6, #{TETRIS}
        bne   pd_link
        bl    v_tenter
        b     pd_end
    pd_link:
        cmp   r6, #{DEBUG}
        bne   pd_link2
        bl    v_tdebug
        b     pd_end
    pd_link2:
        cmp   r6, #{LINK}
        bne   pd_end
        bl    link_draw
    pd_end:
        movs  r0, #0
        strb  r0, [r5, #1]
        ldr   r3, fg_addr
        ldrh  r0, [sp, #8]
        strh  r0, [r3]
        ldrh  r0, [sp, #10]
        strh  r0, [r3, #2]
        add   sp, #20
        pop   {{r4, r5, r6, r7, pc}}
    pd_adv:
        ldr   r7, [sp, #12]
        adds  r7, #8
        str   r7, [sp, #12]
        b     pd_line

    text16s:                                @ same, on the Settings list background
        push  {{r4, r5, r6, r7, lr}}
        movs  r4, #16
        movw  ip, #{LISTBG}
        b     tx
    text12k:                                @ same, on the black header
        push  {{r4, r5, r6, r7, lr}}
        movs  r4, #12
        movw  ip, #0
        b     tx
    text16:                                 @ r0 = x, r1 = y, r2 = text, r3 = colour
        push  {{r4, r5, r6, r7, lr}}
        movs  r4, #16
        movw  ip, #{PANEL}
        b     tx
    text12:
        push  {{r4, r5, r6, r7, lr}}
        movs  r4, #12
        movw  ip, #{PANEL}
    tx: sub   sp, #12
        mov   r5, r0
        mov   r6, r1
        mov   r7, r2
        ldr   r0, fg_addr
        strh  r3, [r0]
        strh.w ip, [r0, #2]
        movs  r2, #0
    tx_len:
        ldrb  r0, [r7, r2]
        cbz   r0, tx_have
        adds  r2, #1
        b     tx_len
    tx_have:
        lsrs  r0, r4, #1
        muls  r2, r0, r2
        str   r4, [sp]
        str   r7, [sp, #4]
        mov   r0, r5
        mov   r1, r6
        mov   r3, r4
        bl    v_blit
        add   sp, #12
        pop   {{r4, r5, r6, r7, pc}}

    link_draw:                              @ r5 = state
        push  {{r4, r5, r6, r7, lr}}
        sub   sp, #20
        ldrb  r0, [r5, #1]
        cmp   r0, #0
        beq   ld_poll
        bl    v_phy_reset                @ page just opened: reset the chip, then autonegotiate
        movw  r1, #0x1200
        movs  r0, #0
        bl    v_mdio_w
        movs  r1, #0
        mov.w r0, #0xa000
        bl    v_ext_w
        movs  r1, #6
        mov.w r0, #0x100
        bl    v_ext_w
        movs  r0, #0xa7
        strb  r0, [r5, #2]                  @ chip is up because of this page
        movs  r0, #0
        strb  r0, [r5, #3]
        strh  r0, [r5, #4]
        str   r0, [r5, #8]
    ld_poll:
        movs  r0, #1
        bl    v_mdio_r
        movs  r0, #1
        bl    v_mdio_r                @ second read: the link bit is latched
        mov   r4, r0
        movs  r0, #0x11
        bl    v_mdio_r
        mov   r6, r0
        movs  r0, #5
        bl    v_mdio_r
        mov   r7, r0
        movs  r0, #10
        bl    v_mdio_r
        str   r0, [sp, #12]
        lsrs  r0, r4, #2
        and   r0, r0, #1                    @ link up?
        str   r0, [sp, #16]
        cmp   r0, #0
        beq   ld_down
        ldr   r1, [r5, #8]
        adds  r1, #1
        str   r1, [r5, #8]
        b     ld_book
    ld_down:
        ldrb  r1, [r5, #3]
        cmp   r1, #0
        beq   ld_zero
        ldrh  r1, [r5, #4]
        adds  r1, #1
        strh  r1, [r5, #4]                  @ it was up a second ago: one more drop
    ld_zero:
        movs  r1, #0
        str   r1, [r5, #8]
    ld_book:
        strb  r0, [r5, #3]

        @ line 1: state, speed, duplex
        ldr   r0, [sp, #16]
        cmp   r0, #0
        beq   l1_down
        lsrs  r2, r6, #14
        adr   r1, speeds
        ldrh  r2, [r1, r2, lsl #1]
        adr   r3, s_fd
        tst   r6, #0x2000
        bne   l1_fmt
        adr   r3, s_hd
    l1_fmt:
        adr   r1, f_up
        ldr   r0, buf_addr
        bl    v_sprintf
        movw  r3, #{GREEN}
        b     l1_put
    l1_down:
        adr   r1, f_down
        ldr   r0, buf_addr
        bl    v_sprintf
        movw  r3, #{RED}
    l1_put:
        ldr   r2, buf_addr
        movs  r0, #20
        movs  r1, #92
        bl    text16

        @ line 2: time the link has been up
        ldr   r0, [r5, #8]
        movw  r1, #3600
        .short 0xFBB0, 0xF2F1               @ udiv r2, r0, r1     hours
        .short 0xFB02, 0x0011               @ mls  r0, r2, r1, r0
        movs  r1, #60
        .short 0xFBB0, 0xF3F1               @ udiv r3, r0, r1     minutes
        .short 0xFB03, 0x0011               @ mls  r0, r3, r1, r0 seconds
        str   r0, [sp]
        adr   r1, f_time
        ldr   r0, buf_addr
        bl    v_sprintf
        ldr   r2, buf_addr
        movs  r0, #20
        movs  r1, #116
        movw  r3, #{WHITE}
        bl    text16

        @ line 3: drops
        ldrh  r2, [r5, #4]
        adr   r1, f_drops
        ldr   r0, buf_addr
        bl    v_sprintf
        ldr   r2, buf_addr
        movs  r0, #20
        movs  r1, #140
        movw  r3, #{WHITE}
        bl    text16

        @ line 4: what the far end offers
        adr   r2, s_no2
        tst   r7, #0x60
        beq   l4_a
        adr   r2, s_10
    l4_a:
        adr   r3, s_no3
        tst   r7, #0x180
        beq   l4_b
        adr   r3, s_100
    l4_b:
        adr   r0, s_no4
        ldr   r1, [sp, #12]
        tst   r1, #0xc00
        beq   l4_c
        adr   r0, s_1000
    l4_c:
        str   r0, [sp]
        adr   r1, f_peer
        ldr   r0, buf_addr
        bl    v_sprintf
        ldr   r2, buf_addr
        movs  r0, #20
        movs  r1, #164
        movw  r3, #{WHITE}
        bl    text16

        @ line 5: crossover state (only meaningful with a link)
        adr   r2, s_none
        ldr   r0, [sp, #16]
        cmp   r0, #0
        beq   l5_fmt
        adr   r2, s_straight
        tst   r6, #0x40
        beq   l5_fmt
        adr   r2, s_crossed
    l5_fmt:
        adr   r1, f_mdi
        ldr   r0, buf_addr
        bl    v_sprintf
        ldr   r2, buf_addr
        movs  r0, #20
        movs  r1, #188
        movw  r3, #{WHITE}
        bl    text16

        @ line 6: the raw registers
        ldr   r0, [sp, #12]
        str   r0, [sp, #4]
        str   r7, [sp]
        mov   r3, r6
        mov   r2, r4
        adr   r1, f_raw
        ldr   r0, buf_addr
        bl    v_sprintf
        ldr   r2, buf_addr
        movs  r0, #24
        movs  r1, #220
        movw  r3, #{GREY}
        bl    text12
        add   sp, #20
        pop   {{r4, r5, r6, r7, pc}}

    @ ------------------------------------------------ Settings: a sixth item (Theme) on a second list page
    item_hook:                              @ settings_item_draw(r0 = item): replaces push.w {{r4-r9, lr}}
        ldr   r3, sys_addr
        ldrb  r1, [r3, #2]
        cmp   r1, #6
        bhs   ih_p2
        cmp   r0, #1
        beq   theme_tile                    @ the first row is Theme (it was Language)
        cmp   r0, #6
        bhs   ih_ret
        push.w {{r4, r5, r6, r7, r8, sb, lr}}
        b     v_item_cont
    ih_p2:
        cmp   r0, #6
        beq   debug_tile
    ih_ret:
        bx    lr

    theme_tile:
        push  {{r4, lr}}
        ldr   r0, thm_addr
        ldrb  r0, [r0]
        cmp   r0, #{len(THEMES)}
        blo   tt1
        movs  r0, #0
    tt1:
        adr.w r1, thm_names
        add.w r1, r1, r0, lsl #3
        movs  r0, #68
        movs  r2, #1
        movs  r3, #1
        bl    val_tile
        pop   {{r4, pc}}

    debug_tile:
        push  {{r4, lr}}
        movs  r0, #68
        adr.w r1, s_open
        movs  r2, #6
        movs  r3, #0
        bl    val_tile
        pop   {{r4, pc}}

    val_tile:                               @ r0 = box y, r1 = text, r2 = item number, r3 = draw < > arrows
        push  {{r4, r5, r6, r7, lr}}
        sub   sp, #36
        str   r0, [sp, #24]
        str   r3, [sp, #28]
        mov   r5, r1
        ldr   r6, fg_addr
        ldr   r7, [r6]
        movw  r4, #0x31a7
        movw  r3, #0x4a69
        ldr   r1, sys_addr
        ldrb  r1, [r1, #2]
        cmp   r1, r2
        bne   vt1
        movw  r4, #0x7304                   @ the selected item
        movw  r3, #0xfe60
    vt1:
        movs  r1, #106
        strh.w r1, [sp, #8]
        strh.w r0, [sp, #10]
        movs  r1, #100
        strh.w r1, [sp, #12]
        movs  r1, #27
        strh.w r1, [sp, #14]
        strh.w r4, [sp, #16]
        strh.w r3, [sp, #18]
        movs  r1, #3
        strb.w r1, [sp, #20]
        add   r0, sp, #8
        bl    v_box
        movs  r2, #0
    tt_len:
        ldrb  r0, [r5, r2]
        cbz   r0, tt_have
        adds  r2, #1
        b     tt_len
    tt_have:
        movw  r0, #0xffff
        strh  r0, [r6]
        strh  r4, [r6, #2]
        movs  r0, #16
        str   r0, [sp]
        str   r5, [sp, #4]
        rsb.w r0, r2, #39
        lsls  r0, r0, #2
        ldr   r1, [sp, #24]
        adds  r1, #6
        lsls  r2, r2, #3
        movs  r3, #16
        bl    v_blit
        ldr   r0, [sp, #28]
        cmp   r0, #0
        beq   vt_end
        movs  r0, #16
        str   r0, [sp]
        adr.w r0, s_lt
        str   r0, [sp, #4]
        movs  r0, #110
        ldr   r1, [sp, #24]
        adds  r1, #6
        movs  r2, #8
        movs  r3, #16
        bl    v_blit
        movs  r0, #16
        str   r0, [sp]
        adr.w r0, s_gt
        str   r0, [sp, #4]
        movs  r0, #194
        ldr   r1, [sp, #24]
        adds  r1, #6
        movs  r2, #8
        movs  r3, #16
        bl    v_blit
    vt_end:
        str   r7, [r6]
        add   sp, #36
        pop   {{r4, r5, r6, r7, pc}}

    list_hook:                              @ settings list draw (GUI msg 0x32): replaces push {{r4-r7, lr}} ; sub sp, #0x54
        push  {{r4, r5, r6, lr}}
        ldr   r6, fg_addr
        ldr   r5, [r6]
        ldr   r3, sys_addr
        ldrb  r1, [r3, #3]
        cmp   r1, #0
        bne   lh_plain                      @ About or a dialog is showing: stock only
        ldrb  r1, [r3, #2]
        cmp   r1, #6
        blo   lh_page1
        movs  r0, #15                       @ page 2
        movs  r1, #73
        adr.w r2, s_debug
        movw  r3, #0xffff
        bl    text16s
        movs  r0, #92
        movs  r1, #24
        adr.w r2, s_p2
        movw  r3, #0x8410
        bl    text12k
        bl    debug_tile
        b     lh_done
    lh_page1:
        bl    lh_body
        movs  r0, #15                       @ the first row's label
        movs  r1, #73
        adr.w r2, s_theme
        movw  r3, #0xffff
        bl    text16s
        movs  r0, #92
        movs  r1, #24
        adr.w r2, s_p1
        movw  r3, #0x8410
        bl    text12k
    lh_done:
        str   r5, [r6]
        pop   {{r4, r5, r6, pc}}
    lh_plain:
        bl    lh_body
        pop   {{r4, r5, r6, pc}}
    lh_body:
        push  {{r4, r5, r6, r7, lr}}
        sub   sp, #0x54
        b     v_list_cont

    move_fix:                               @ cursor moved, r0 = old item: replaces bl post_item
        ldr   r3, sys_addr
        ldrb  r1, [r3, #2]
        cmp   r0, #6                        @ page of the old item ...
        sbcs  r2, r2
        cmp   r1, #6                        @ ... and of the new one
        sbcs  r3, r3
        cmp   r2, r3
        bne   mf_page
        b     v_item_post
    mf_page:                                @ the list page changed: redraw frame and list
        push  {{r4, lr}}
        movs  r2, #0
        mov   r1, r2
        movs  r0, #0x36
        bl    v_gui
        movs  r2, #0
        mov   r1, r2
        movs  r0, #0x32
        bl    v_gui
        pop   {{r4, pc}}

    edit_fix:                               @ value edit, r5 = item, r4 = action: replaces cmp r5, #6 ; bhs default
        cmp   r5, #1
        beq   ef_theme
        cmp   r5, #6
        beq   ef_dbg
        bhi   ef_hi
        bx    lr
    ef_hi:
        b     v_edit_def
    ef_dbg:                                 @ Debug: OK opens the page (borrowing the About sub-screen, like the tools)
        cmp   r4, #0x20
        bne   ef_out
        ldr   r3, st_addr
        movs  r0, #{DEBUG}
        strb  r0, [r3]
        movs  r0, #1
        strb  r0, [r3, #1]
        ldr   r3, sys_addr
        strb  r0, [r3, #3]
        movs  r0, #5
        strb  r0, [r3, #2]
        movs  r2, #0
        mov   r1, r2
        movs  r0, #0x36
        bl    v_gui
        movs  r2, #0
        mov   r1, r2
        movs  r0, #0x34
        bl    v_gui
        b     ef_out
    ef_theme:
        ldr   r3, thm_addr
        ldrb  r0, [r3]
        cmp   r0, #{len(THEMES)}
        blo   ef1
        movs  r0, #0
    ef1:
        cmp   r4, #0x1e
        beq   ef_dec
        cmp   r4, #0x1f
        bne   ef_out
        adds  r0, #1
        cmp   r0, #{len(THEMES)}
        blo   ef_set
        movs  r0, #0
        b     ef_set
    ef_dec:
        subs  r0, #1
        bpl   ef_set
        movs  r0, #{len(THEMES) - 1}
    ef_set:
        strb  r0, [r3]
        movs  r2, #0
        mov   r1, r2
        movs  r0, #0x36
        bl    v_gui
        movs  r2, #0
        mov   r1, r2
        movs  r0, #0x32
        bl    v_gui
    ef_out:
        b     v_edit_exit

    theme2:                                 @ every pixel: r0 = RGB565 -> themed ; may use r1, r2 only
        uxth  r0, r0
        ldr   r1, thm_addr
        ldrb  r1, [r1]
        cmp   r1, #{len(THEMES)}
        blo   th_ok
        movs  r1, #0
    th_ok:
        adr.w r2, thm_tab
        add.w r2, r2, r1, lsl #2
        ldrb  r1, [r2, #3]
        cmp   r1, #1
        beq   th_cyber
        bhi   th_other
        push  {{r3}}                        @ one hue: warm colours kept, the rest by brightness
        mov   r3, r2
        lsrs  r1, r0, #11
        and   r2, r0, #31
        subs  r1, r1, r2
        cmp   r1, #8
        bge   th_pop
        lsrs  r1, r0, #11
        cmp   r1, r2
        bhs   tm1
        mov   r1, r2
    tm1:
        lsls  r1, r1, #1
        ubfx  r2, r0, #5, #6
        cmp   r1, r2
        bhs   tm2
        mov   r1, r2
    tm2:
        subs  r1, #14
        bge   tm3
        movs  r1, #0
    tm3:
        add.w r1, r1, r1, lsr #2            @ t = brightness 0..61
        ldrb  r2, [r3]
        muls  r2, r1, r2
        lsrs  r2, r2, #6
        lsls  r0, r2, #11
        ldrb  r2, [r3, #1]
        muls  r2, r1, r2
        lsrs  r2, r2, #6
        orr.w r0, r0, r2, lsl #5
        ldrb  r2, [r3, #2]
        muls  r2, r1, r2
        lsrs  r2, r2, #6
        orrs  r0, r2
    th_pop:
        pop   {{r3}}
        bx    lr
    th_cyber:
        lsrs  r1, r0, #11
        b     v_theme_cont
    th_other:
        cmp   r1, #2
        beq   th_ret                        @ Stock: unchanged
        mvns  r0, r0                        @ Light: inverted
        uxth  r0, r0
    th_ret:
        bx    lr

    name_fix:                               @ home selection log: r0 = sel - 4, r1 = the stock 8-entry name table
        cmp   r0, #8                        @ (stock read past the table for the tool tiles and printed a wild pointer)
        bhs   nx_tool
        ldr.w r0, [r1, r0, lsl #2]
        bx    lr
    nx_tool:
        subs  r0, #8
        cmp   r0, #{NT}
        blo   nx_ok
        movs  r0, #0
    nx_ok:
        adr.w r1, tile_names
        ldr.w r0, [r1, r0, lsl #2]
        adds  r0, r0, r1
        bx    lr

    msg_hook:                               @ GUI loop, message received: replaces ldrb.w r0, [sp, #8]
        push  {{r4, lr}}
        ldrb.w r0, [sp, #16]
        bl    v_tmsg
        pop.w {{r4, lr}}
        ldrb.w r0, [sp, #8]
        bx    lr

    poll_hook:                              @ GUI loop, r2 = queue timeout; replaces add r1, sp, #8 ; ldr r0, =gui_queue
        push  {{r4, lr}}
        mov   r0, r2
        bl    v_tpoll
        mov   r2, r0
        pop.w {{r4, lr}}
        add   r1, sp, #8
        ldr   r0, guiq_addr
        bx    lr

    nav_fix:                                @ home RIGHT from a left-column tile (r4 = position): returns sel, or
        ldr   r0, sys_addr                  @ a value one below the wrap target when sel is the last tile
        ldrb  r0, [r0, #1]
        cmp   r0, #{12 + NT - 1}
        bne   nf_ret
        movs  r0, #3
        cmp   r4, #0
        beq   nf_ret
        movs  r0, #5
    nf_ret:
        bx    lr

    cursor_hook:                            @ UP / DOWN in Settings: r0 = 0 up, 1 down
        ldr   r3, sys_addr
        ldrb  r1, [r3, #3]
        cmp   r1, #1
        bne   cu_stock
        ldr   r3, st_addr
        ldrb  r1, [r3]
        cmp   r1, #{TETRIS}
        bne   cu_stock
        adds  r0, #2                        @ Tetris: UP turns, DOWN drops
        b     v_tkey
    cu_stock:
        push  {{r4, r5, r6, lr}}
        mov   r4, r0
        b     v_cursor_cont

    tick_hook:                              @ replaces push {{r4,lr}} ; ldr r0,=g_settings
        push  {{r4, lr}}
        bl    tick_work
        ldr   r0, settings_addr
        b     v_tick_cont
    tick_work:
        push  {{r4, lr}}
        ldr   r4, st_addr
        ldr   r3, sys_addr
        ldrb  r0, [r3]
        cmp   r0, #11
        bne   tw_off
        ldrb  r1, [r3, #3]
        cmp   r1, #1
        bne   tw_off
        ldrb  r1, [r4]
        cmp   r1, #{DEBUG}
        beq   tw_post
        cmp   r1, #{LINK}
        bne   tw_off
    tw_post:
        movs  r2, #0
        mov   r1, r2
        movs  r0, #0x34                     @ Link page showing: refresh it
        bl    v_gui
        pop   {{r4, pc}}
    tw_off:
        ldrb  r1, [r4, #2]
        cmp   r1, #0xa7
        bne   tw_ret
        movs  r1, #0
        strb  r1, [r4, #2]
        cmp   r0, #6                        @ FLASH, LENGTH and SPEED manage the chip themselves
        beq   tw_ret
        cmp   r0, #7
        beq   tw_ret
        cmp   r0, #9
        beq   tw_ret
        movs  r0, #0
        bl    v_mdio_r
        orr   r1, r0, #0x800                @ power the chip back down
        movs  r0, #0
        bl    v_mdio_w
    tw_ret:
        pop   {{r4, pc}}

    ok_hook:                                @ home screen OK: replaces bl get_sysState_ptr
        push  {{r4, lr}}
        bl    v_get_ptr
        mov   r4, r0
        ldrb  r1, [r4]
        cmp   r1, #2
        bne   ok_ret
        ldrb  r1, [r4, #1]
        subs  r1, #12
        cmp   r1, #{NT}
        bhs   ok_ret                        @ not one of the tool tiles
        adds  r1, #1
        ldr   r3, st_addr
        strb  r1, [r3]                      @ tool page
        movs  r1, #1
        strb  r1, [r3, #1]
        movs  r0, #11
        bl    v_set_state                   @ borrow the Settings screen state: frame
        movs  r1, #5
        strb  r1, [r4, #2]
        movs  r1, #1
        strb  r1, [r4, #3]                  @ as if About were open
        movs  r2, #0
        mov   r1, r2
        movs  r0, #0x34
        bl    v_gui
    ok_ret:
        mov   r0, r4
        pop   {{r4, pc}}

    back_hook:                              @ Back in Settings: replaces push {{r4,lr}} ; ldr r0,=sysState
        ldr   r0, sys_addr
        ldrb  r1, [r0, #3]
        cmp   r1, #1
        bne   bk_stock
        ldr   r3, st_addr
        ldrb  r1, [r3]
        cmp   r1, #0
        beq   bk_stock
        cmp   r1, #{npages}
        bhs   bk_stock
        push  {{r4, r5, r6, lr}}            @ leaving a tool: straight back to the home screen
        mov   r4, r0
        mov   r5, r3
        mov   r6, r1
        movs  r0, #88                       @ log 'X': Back seen on a tool page
        movs  r2, #0
        bl    v_tlog
        cmp   r6, #{DEBUG}
        bne   bk_home
        movs  r1, #0                        @ Debug: back to its row in the Settings list
        strb  r1, [r5]
        strb  r1, [r4, #3]
        movs  r1, #6
        strb  r1, [r4, #2]
        movs  r2, #0
        mov   r1, r2
        movs  r0, #0x36
        bl    v_gui
        movs  r2, #0
        mov   r1, r2
        movs  r0, #0x32
        bl    v_gui
        pop   {{r4, r5, r6, pc}}
    bk_home:
        movs  r1, #0
        strb  r1, [r5]
        strb  r1, [r4, #3]
        movs  r1, #1
        strb  r1, [r4, #2]
        movs  r0, #2
        bl    v_set_state
        movs  r0, #120                      @ log 'x': the state change returned
        mov   r1, r6
        movs  r2, #0
        bl    v_tlog
        pop   {{r4, r5, r6, pc}}
    bk_stock:
        push  {{r4, lr}}
        ldr   r0, sys_addr
        b     v_back_cont

    tile_hook:                              @ home tile loop: replaces add.w r0, r4, r6, lsl #2
        add.w r0, r4, r6, lsl #2            @ tile number = position + 4 * page
        cmp   r0, #8
        blo   th_stock
        cmp   r0, #{8 + NT}
        bhs   th_skip                       @ empty slot on page 3
        push  {{r5, r7}}
        sub   sp, #8
        subs  r5, r0, #8                    @ tool tile index
        adr.w r7, tile_xy
        add.w r7, r7, r4, lsl #3            @ this position's coordinates
        adr.w r1, tile_names
        ldr.w r1, [r1, r5, lsl #2]
        adr.w r0, tile_names
        adds  r1, r1, r0                    @ name
        movs  r2, #0
    th_len:
        ldrb  r0, [r1, r2]
        cbz   r0, th_have
        adds  r2, #1
        b     th_len
    th_have:
        movs  r0, #16
        str   r0, [sp]
        str   r1, [sp, #4]
        ldrh  r0, [r7]
        sub.w r0, r0, r2, lsl #2            @ centred
        ldrh  r1, [r7, #2]
        lsls  r2, r2, #3
        movs  r3, #16
        bl    v_blit
        adr.w r1, tile_icons
        ldr.w r2, [r1, r5, lsl #2]
        adds  r2, r2, r1
        ldrh  r0, [r7, #4]
        ldrh  r1, [r7, #6]
        bl    icon_draw
        add   sp, #8
        pop   {{r5, r7}}
    th_skip:
        b     v_tile_skip
    th_stock:
        bx    lr

    icon_draw:                              @ r0 = centre x, r1 = centre y, r2 = icon (w, h, plane A, plane B)
        push  {{r4, r5, r6, r7, r8, sb, sl, fp, lr}}
        sub   sp, #12
        ldrb  r4, [r2]
        ldrb  r5, [r2, #1]
        adds  r6, r2, #2
        adds  r3, r4, #7
        lsrs  r3, r3, #3
        mov   r8, r3
        mul   r7, r3, r5
        adds  r7, r7, r6
        sub.w sb, r0, r4, lsr #1
        sub.w sl, r1, r5, lsr #1
        ldr   r3, fg_addr
        ldrh  r0, [r3]
        str   r0, [sp]
        movs  r0, #0
        str   r0, [sp, #4]
        str   r5, [sp, #8]
    id_row:
        movs  r5, #0
    id_px:
        lsrs  r0, r5, #3
        and   r1, r5, #7
        movs  r2, #0x80
        lsrs  r2, r1
        ldrb  r3, [r6, r0]
        tst   r3, r2
        beq   id_b
        movw  fp, #0xffff
        b     id_put
    id_b:
        ldrb  r3, [r7, r0]
        tst   r3, r2
        beq   id_next
        movw  fp, #{ORANGE}
    id_put:
        ldr   r3, fg_addr
        strh  fp, [r3]
        add.w r0, sb, r5
        ldr   r1, [sp, #4]
        add   r1, r1, sl
        bl    v_pixel
    id_next:
        adds  r5, #1
        cmp   r5, r4
        blo   id_px
        add   r6, r6, r8
        add   r7, r7, r8
        ldr   r0, [sp, #4]
        adds  r0, #1
        str   r0, [sp, #4]
        ldr   r1, [sp, #8]
        cmp   r0, r1
        blo   id_row
        ldr   r3, fg_addr
        ldr   r0, [sp]
        strh  r0, [r3]
        add   sp, #12
        pop   {{r4, r5, r6, r7, r8, sb, sl, fp, pc}}

        .balign 4
    tile_xy:       .short 60, 50, 61, 106,  180, 50, 179, 106,  60, 190, 61, 243,  180, 190, 179, 243
    tile_names:    .word n_pin - tile_names, n_link - tile_names, n_tet - tile_names
    n_pin:         .asciz "Pinout"
    n_link:        .asciz "Link"
    n_tet:         .asciz "Tetris"
    s_debug:       .asciz "Debug"
    s_open:        .asciz "Open"
    s_theme:       .asciz "Theme    "
    s_p1:          .asciz "1/2 v"
    s_p2:          .asciz "2/2 ^"
    s_lt:          .asciz "<"
    s_gt:          .asciz ">"
        .balign 4
    thm_names:
THM_NAMES
    s_tools:       .asciz "TOOLS  "
        .balign 4
    tile_icons:    .word ICON_OFFSETS
        ICON_DATA
        .balign 4
    st_addr:       .word {ST:#x}
    box_addr:      .word {ABOUT_BOX:#x}
    fg_addr:       .word {FG:#x}
    buf_addr:      .word {BUF:#x}
    sys_addr:      .word {SYS:#x}
    settings_addr: .word {SETTINGS:#x}
    guiq_addr:     .word {GUI_QUEUE:#x}
    thm_addr:      .word {THM:#x}
    speeds:        .short 10, 100, 1000, 0
    f_up:      .asciz "UP   %4d Mb %s  "
    f_down:    .asciz "DOWN             "
    f_time:    .asciz "Up for  %02d:%02d:%02d "
    f_drops:   .asciz "Drops   %-6d"
    f_peer:    .asciz "Offers  %-3s%-4s%-4s"
    f_mdi:     .asciz "MDI     %-9s"
    f_raw:     .asciz "01:%04X 11:%04X 05:%04X 0A:%04X"
    s_fd:      .asciz "FD"
    s_hd:      .asciz "HD"
    s_10:      .asciz "10"
    s_100:     .asciz "100"
    s_1000:    .asciz "1000"
    s_no2:     .asciz "--"
    s_no3:     .asciz "---"
    s_no4:     .asciz "----"
    s_none:    .asciz "-"
    s_straight: .asciz "straight"
    s_crossed: .asciz "crossed"
        .balign 4
    page_table:
    """
    # the static-text loop keeps its record pointer in a stack slot
    src = src.replace("""        adds  r7, r7, r1
        mov   r4, r7
    pd_line:
        ldrb  r0, [r7]""", """        adds  r7, r7, r1
        mov   r4, r7
        str   r7, [sp, #12]
    pd_line:
        ldr   r7, [sp, #12]
        ldrb  r0, [r7]""")
    offs, pos, body = [], 4 * len(ICONS), ""
    for ic in ICONS:
        ic = ic + b"\0" * (-len(ic) % 4)
        offs.append(pos); pos += len(ic)
        body += "".join("        .byte " + ", ".join(str(v) for v in ic[i:i + 16]) + "\n" for i in range(0, len(ic), 16))
    src = src.replace("THM_NAMES\n", "".join("    .byte " + ", ".join(str(v) for v in (n[0].encode() + bytes(8))[:8]) + "\n" for n in THEMES)
                      + "    thm_tab:\n" + "".join(f"    .byte {r}, {g}, {b}, {k}\n" for _, r, g, b, k in THEMES))
    src = src.replace("ICON_OFFSETS", ", ".join(str(o) for o in offs)).replace("        ICON_DATA\n", body)
    code = asm(src, cave)
    assert len(code) % 4 == 0
    from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_MCLASS
    allowed = {GUI_MSG_SEND, GUI_BLIT, DRAW_BOX, SPRINTF, MDIO_READ, MDIO_WRITE, PHY_EXT_WRITE, PHY_RESET, ABOUT_ENTRY + 4, TICK_ENTRY + 4,
               GET_PTR, SET_STATE, PUT_PIXEL, HOME_TILE_SKIP, BACK_ENTRY + 4,
               T_BASE, T_BASE + 4, T_BASE + 8, T_BASE + 12, T_BASE + 16, T_BASE + 20, T_BASE + 24, CURSOR_ENTRY + 4,
               ITEM_DRAW + 4, LIST_DRAW + 4, ITEM_POST, EDIT_EXIT, EDIT_DEFAULT, THEME + 4}
    seen = set()
    for i in Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS).disasm(code[:code.index(struct.pack("<4H", 60, 50, 61, 106))], cave):
        if i.mnemonic in ("bl", "b.w", "b") and i.op_str.startswith("#"):
            t = int(i.op_str[1:], 16)
            if not cave <= t < cave + len(code):
                assert t in allowed, f"stray branch at {i.address:#x} -> {t:#x}"
                seen.add(t)
    assert seen == allowed, [hex(x) for x in allowed - seen]
    offs, pos = [], 4 * len(data)
    for blob in data:
        offs.append(pos); pos += len(blob)
    code += b"".join(struct.pack("<I", o) for o in offs) + b"".join(data)
    room = len(d) - off - ln
    if len(code) > room:
        d += b"\0" * (-(-(len(code) - room) // 4096) * 4096)
    d[off + ln: off + ln + len(code)] = code
    struct.pack_into("<III", d, 0x20, off, ln + len(code), off + ln + len(code) - 1)
    def poke(a, old, new):
        assert rd(a, len(old)) == old, f"{a:#x}: {rd(a, len(old)).hex()}"
        assert len(old) == len(new); d[f(a):f(a) + len(new)] = new
    poke(SITE_ENTER, asm(f"bl {GUI_MSG_SEND:#x}", SITE_ENTER), asm(f"bl {cave:#x}", SITE_ENTER))
    keys = asm(f"bl {cave + 4:#x}", SITE_KEYS) + asm(f"cbz r0, {SITE_KEYS + 10:#x}", SITE_KEYS + 4) \
         + asm(f"b {0x0801136C:#x}", SITE_KEYS + 6) + bytes.fromhex("00bf")
    poke(SITE_KEYS, bytes.fromhex("1e2c01d01f2c00d1e6e7"), keys)
    poke(ABOUT_ENTRY, bytes.fromhex("70b596b0"), asm(f"b.w {cave + 8:#x}", ABOUT_ENTRY))
    poke(TICK_ENTRY, bytes.fromhex("10b51248"), asm(f"b.w {cave + 12:#x}", TICK_ENTRY))
    # ---- home screen: third page
    last = 12 + NT - 1                                  # last selectable tile (13)
    poke(0x0801689C, bytes.fromhex("c0f10c00"), bytes([0xc0, 0xf1, 12 + NT, 0x00]))   # DOWN: (14 - sel) > 2
    poke(0x0801690C, bytes.fromhex("c0f10c00"), bytes([0xc0, 0xf1, 12 + NT, 0x00]))   # RIGHT: (14 - sel) > 3, else wrap
    top = 12 + min(NT, 2) - 1                           # rightmost tile of the last page's top row
    poke(0x080168E6, bytes.fromhex("0b20"), bytes([last if NT > 2 else top, 0x20]))   # LEFT off page 1, bottom row
    poke(0x080168EE, bytes.fromhex("0920"), bytes([top, 0x20]))              # LEFT off page 1, top row
    poke(0x08016924, bytes.fromhex("0928"), bytes([top, 0x28]))              # RIGHT off the top-right tile -> tile 4, else 6
    poke(0x080168FC, bytes.fromhex("13484078"), asm(f"bl {cave + 36:#x}", 0x080168FC))   # RIGHT from a left-column tile
    poke(0x0800F1D2, bytes.fromhex("022c"), bytes.fromhex("032c"))           # three page dots (the table already has three)
    poke(0x0800F1E8, bytes.fromhex("0828"), bytes([8 + NT, 0x28]))           # tile frames for the tool tiles
    poke(HOME_DRAW_TILE, bytes.fromhex("04eb8600"), asm(f"bl {cave + 24:#x}", HOME_DRAW_TILE))
    poke(OK_SITE, asm(f"bl {GET_PTR:#x}", OK_SITE), asm(f"bl {cave + 16:#x}", OK_SITE))
    poke(BACK_ENTRY, bytes.fromhex("10b50a48"), asm(f"b.w {cave + 20:#x}", BACK_ENTRY))
    poke(POLL_SITE, bytes.fromhex("02a9b048"), asm(f"bl {cave + 28:#x}", POLL_SITE))
    assert struct.unpack_from("<I", d, f(0x0800F72C))[0] == GUI_QUEUE
    poke(0x0801781E, bytes.fromhex("51f82000"), asm(f"bl {cave + 44:#x}", 0x0801781E))   # selection log: bounded name lookup
    poke(ITEM_DRAW, bytes.fromhex("2de9f043"), asm(f"b.w {cave + 48:#x}", ITEM_DRAW))
    poke(LIST_DRAW, bytes.fromhex("f0b595b0"), asm(f"b.w {cave + 52:#x}", LIST_DRAW))
    poke(EDIT_SITE, bytes.fromhex("062d78d2"), asm(f"bl {cave + 56:#x}", EDIT_SITE))
    poke(MOVE_SITE, asm(f"bl {ITEM_POST:#x}", MOVE_SITE), asm(f"bl {cave + 60:#x}", MOVE_SITE))
    poke(0x080111A4, bytes.fromhex("0521"), bytes.fromhex("0621"))           # UP from the first item -> item 6
    poke(0x080111AE, bytes.fromhex("0628"), bytes.fromhex("0728"))           # DOWN from item 6 -> item 1
    poke(THEME, bytes.fromhex("80b2c10a"), asm(f"b.w {cave + 64:#x}", THEME))
    poke(0x0800F504, bytes.fromhex("02d1"), bytes.fromhex("02e0"))           # boot: never show the language picker
    poke(MSG_SITE, bytes.fromhex("9df80800"), asm(f"bl {cave + 40:#x}", MSG_SITE))
    poke(CURSOR_ENTRY, bytes.fromhex("70b50446"), asm(f"b.w {cave + 32:#x}", CURSOR_ENTRY))
    assert struct.unpack_from("<I", d, f(0x08011034))[0] == SYS
    assert struct.unpack_from("<I", d, f(0x0800F9B4))[0] == SETTINGS
    n = 0; p = d.find(b"PN2.34C\0")
    while p >= 0:
        d[p:p + 8] = b"PN2.34H\0"; n += 1; p = d.find(b"PN2.34C\0", p + 1)
    assert n == 2
    return bytes(d), cave, len(code)

if __name__ == "__main__":
    out, cave, n = build(open(sys.argv[1], "rb").read())
    open(sys.argv[2], "wb").write(out)
    print(f"code+data at {cave:#x}, {n} bytes; file {len(out)} bytes")
    print("sha256", hashlib.sha256(out).hexdigest())
