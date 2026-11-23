"""TX PN2.34H -> 'PN2.34W': boot splash, battery percent, Cable Test verdict.

- Boot: the 0.5 s black screen before Home becomes a splash (logo, credit line, a bar that fills in ~1.1 s).
- Battery: a number left of the battery icon. Own curve from the smoothed cell voltage (stock only
  knows 20/50/80/100). While the charger is charging it shows CHG (the voltage is inflated then);
  charger standby shows 100%.
- Cable Test: a coloured verdict bar between the wire map and the button, from the result codes the
  test already produced (no measurement or decision rule changes).
"""
import hashlib, struct, sys
from keystone import Ks, KS_ARCH_ARM, KS_MODE_THUMB
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_MCLASS
PARENT_SHA = "691474955efedc057f2d9a3ec1d8d838b6ad8383028e9f506d4bd750ffbd0956"   # PN2.34H
APP, HDR = 0x0800A000, 0x1000
GUI_BLIT, DRAW_SHAPE, ASSET, DELAY = 0x080174E8, 0x08016D08, 0x0800EEDA, 0x0801C75C
RETRY_POST, BATT_TAIL, FRAME_HOOK = 0x0806B088, 0x0800DCF0, 0x0806ACA0
BAND = 0x31A7                     # panel colour behind the verdict bar
SITES_START = (0x0800C4F4, 0x0800CB7A)          # both routines: bl frame_hook
FG, STATUS, AVG = 0x200001AC, 0x2000023E, 0x2000FE50
SITE_BATT = 0x0800E810            # battery_ui_update: bl 0x0800DCF0 (last call)
SITE_BOOT = 0x0800F50C            # GUI msg 1: mov.w r0,#500 ; bl vTaskDelay
SITE_FAR, SITE_SW = 0x0800CB2E, 0x0800CE8C      # both Cable Test tails: bl retry_post
CURVE = [(4150, 100), (4050, 90), (3950, 78), (3870, 65), (3800, 52), (3750, 40), (3700, 28),
         (3650, 18), (3580, 10), (3500, 5), (3300, 0), (0, 0)]
PATS = [(2, 5, 0, 3, 4, 1, 6, 7), (2, 5, 0, 6, 7, 1, 3, 4), (7, 6, 5, 4, 3, 2, 1, 0)]
PAT_LABELS = ["PASS  CROSSOVER", "PASS  GIG XOVER", "PASS  ROLLOVER"]
CREDIT = "modded by spence the canadian"
ks = Ks(KS_ARCH_ARM, KS_MODE_THUMB)
asm = lambda src, addr: bytes(ks.asm(src, addr)[0])

def s(label, text, pad=None):
    b = text.encode("ascii") + b"\0"
    if pad: assert len(b) <= pad; b += b"\0" * (pad - len(b))
    b += b"\0" * (-len(b) % 4)
    return f"    {label}: .byte " + ", ".join(str(v) for v in b) + "\n"

def source():
    data = "    .align 2\n    data_start:\n"
    data += "    batt_tab: .short " + ", ".join(f"{mv}, {p}" for mv, p in CURVE) + "\n"
    data += "    pats: .byte " + ", ".join(str(v) for p in PATS for v in p) + "\n"
    data += "".join(s(f"t_xo{i}", t, 16) for i, t in enumerate(PAT_LABELS))
    data += s("t_nc", "NOT CONNECTED") + s("t_short", "FAIL  SHORT") + s("t_unk", "FAIL  UNKNOWN")
    data += s("t_open", "FAIL  OPEN") + s("t_2p", "PASS  2 PAIRS (10/100)") + s("t_mis", "FAIL  MISWIRE")
    data += s("t_str", "PASS  STRAIGHT") + s("t_4p", "PASS  4 PAIRS") + s("s_credit", CREDIT)
    data += f"    fg_addr: .word {FG:#x}\n    status_addr: .word {STATUS:#x}\n    avg_addr: .word {AVG:#x}\n"
    return f"""
        b.w   batt_hook                     @ +0
        b.w   splash                        @ +4
        b.w   verd_far                      @ +8
        b.w   verd_sw                       @ +12
        b.w   vclear                        @ +16
    v_blit:   b.w {GUI_BLIT:#x}
    v_shape:  b.w {DRAW_SHAPE:#x}
    v_asset:  b.w {ASSET:#x}
    v_delay:  b.w {DELAY:#x}
    v_retry:  b.w {RETRY_POST:#x}
    v_tail:   b.w {BATT_TAIL:#x}
    v_frame:  b.w {FRAME_HOOK:#x}

    @ ------------------------------------------------ test start: wipe the verdict bar (replaces bl frame_hook)
    vclear:
        push  {{r0, r1, r2, r3, r4, lr}}
        sub   sp, #8
        movw  r0, #{BAND:#x}
        str   r0, [sp]
        movs  r0, #8
        movw  r1, #271
        movs  r2, #231
        movw  r3, #286
        bl    v_shape
        add   sp, #8
        pop.w {{r0, r1, r2, r3, r4, lr}}
        b     v_frame

    @ ------------------------------------------------ battery percent (r5 = mV, r4 = charger state)
    batt_hook:
        push  {{r4, r5, r6, r7, lr}}
        sub   sp, #20
        ldr   r6, avg_addr
        ldrh  r0, [r6]
        subs  r1, r5, r0
        add.w r2, r1, #200
        cmp.w r2, #400
        bhi   bh_reset
        asrs  r1, r1, #2
        adds  r0, r0, r1
        b     bh_store
    bh_reset:
        mov   r0, r5
    bh_store:
        strh  r0, [r6]
        mov   r5, r0
        add   r7, sp, #8
        lsls  r0, r4, #31
        beq   bh_pct
        movs  r0, #32
        strb  r0, [r7]
        movs  r0, #67
        strb  r0, [r7, #1]
        movs  r0, #72
        strb  r0, [r7, #2]
        movs  r0, #71
        strb  r0, [r7, #3]
        movw  r4, #0xFFFF
        b     bh_draw
    bh_pct:
        cmp   r4, #0
        beq   bh_calc
        movs  r0, #100
        b     bh_fmt
    bh_calc:
        adr   r2, batt_tab
        ldrh  r0, [r2]
        cmp   r5, r0
        blo   bh_scan
        movs  r0, #100
        b     bh_fmt
    bh_scan:
        ldrh  r1, [r2, #4]
        cmp   r5, r1
        bhs   bh_interp
        adds  r2, #4
        b     bh_scan
    bh_interp:
        ldrh  r0, [r2]
        ldrh  r3, [r2, #2]
        ldrh  r6, [r2, #6]
        subs  r3, r3, r6
        subs  r5, r5, r1
        mul   r3, r5, r3
        subs  r1, r0, r1
        mov   r0, r3
        .short 0xFBB0, 0xF0F1               @ udiv r0, r0, r1
        adds  r0, r0, r6
    bh_fmt:
        movw  r4, #0xFFFF
        cmp   r0, #15
        bhi   bh_col
        movw  r4, #0xF800
    bh_col:
        movs  r1, #32
        strb  r1, [r7]
        strb  r1, [r7, #1]
        cmp   r0, #100
        blo   bh_2
        movs  r1, #49
        strb  r1, [r7]
        movs  r1, #48
        strb  r1, [r7, #1]
        movs  r0, #0
        b     bh_ones
    bh_2:
        cmp   r0, #10
        blo   bh_ones
        movs  r1, #10
        .short 0xFBB0, 0xF3F1               @ udiv r3, r0, r1
        mul   r2, r3, r1
        subs  r0, r0, r2
        adds  r3, #48
        strb  r3, [r7, #1]
    bh_ones:
        adds  r0, #48
        strb  r0, [r7, #2]
        movs  r0, #37
        strb  r0, [r7, #3]
    bh_draw:
        movs  r0, #0
        strb  r0, [r7, #4]
        ldr   r6, fg_addr
        ldr   r5, [r6]
        strh  r4, [r6]
        strh  r0, [r6, #2]
        movs  r0, #12
        str   r0, [sp]
        str   r7, [sp, #4]
        movs  r0, #148
        movs  r1, #6
        movs  r2, #24
        movs  r3, #12
        bl    v_blit
        str   r5, [r6]
        add   sp, #20
        pop.w {{r4, r5, r6, r7, lr}}
        b     v_tail

    @ ------------------------------------------------ boot splash (replaces a 500 ms delay)
    splash:
        push  {{r4, r5, r6, lr}}
        sub   sp, #8
        movs  r0, #120
        movs  r1, #140
        movs  r2, #13
        movs  r3, #1
        bl    v_asset
        ldr   r6, fg_addr
        movw  r0, #0x07FF
        strh  r0, [r6]
        movs  r0, #0
        strh  r0, [r6, #2]
        movs  r0, #12
        str   r0, [sp]
        adr   r0, s_credit
        str   r0, [sp, #4]
        movs  r0, #33
        movs  r1, #162
        movs  r2, #174
        movs  r3, #12
        bl    v_blit
        movs  r4, #0
    sp_loop:
        movw  r0, #0xFFE0
        str   r0, [sp]
        add.w r0, r4, r4, lsl #3
        adds  r0, #66
        movs  r1, #186
        adds  r2, r0, #7
        movs  r3, #189
        bl    v_shape
        movs  r0, #90
        bl    v_delay
        adds  r4, #1
        cmp   r4, #12
        blt   sp_loop
        movw  r0, #0xFFFF
        strh  r0, [r6]
        add   sp, #8
        pop   {{r4, r5, r6, pc}}

    @ ------------------------------------------------ Cable Test verdict (replaces bl retry_post; r0-r2 are its args)
    verd_far:
        movs  r3, #1
        b     verd
    verd_sw:
        movs  r3, #0
    verd:
        push.w {{r0, r1, r2, r4, r5, r6, r7, lr}}
        sub   sp, #48                       @ [0,8) call args  [8,40) text  [40,48) far-end pin per wire
        mov   r7, r3
        ldr   r4, status_addr
        movs  r6, #0                        @ bit0 short, bit1 open, bit2 crossed, bit3 unknown
        movs  r2, #0                        @ open signal wires
        movs  r1, #0
        add   r3, sp, #40
    vs_loop:
        ldrb  r0, [r4, r1]
        strb  r1, [r3, r1]
        cmp   r0, #0
        bne   vs_a
        orr   r6, r6, #1
        b     vs_next
    vs_a:
        cmp   r0, #1
        bne   vs_b
        orr   r6, r6, #2
        adds  r2, #1
        b     vs_next
    vs_b:
        cmp   r0, #2
        beq   vs_next
        cmp   r0, #3
        bne   vs_c
        orr   r6, r6, #4
        add.w r0, r4, r1, lsl #1            @ map = status + 10, u16 per wire
        ldrh  r0, [r0, #10]
        strb  r0, [r3, r1]
        b     vs_next
    vs_c:
        orr   r6, r6, #8
    vs_next:
        adds  r1, #1
        cmp   r1, #8
        blt   vs_loop
        ldrb  r0, [r4, #8]                  @ shield: only a short counts
        cmp   r0, #0
        bne   vd_0
        orr   r6, r6, #1
    vd_0:
        movw  r5, #0xF800
        cmp   r2, #8
        bne   vd_1
        adr   r0, t_nc
        movs  r1, #0xFF
        b     vd_go
    vd_1:
        lsls  r0, r6, #31
        beq   vd_2
        adr   r0, t_short
        movs  r1, #0
        b     vd_go
    vd_2:
        lsls  r0, r6, #28
        bpl   vd_3
        adr   r0, t_unk
        movs  r1, #4
        b     vd_go
    vd_3:
        lsls  r0, r6, #30
        bpl   vd_5
        cmp   r7, #0                        @ switch mode, exactly 4,5,7,8 open: a 10/100 port or a 2-pair cable
        bne   vd_open
        cmp   r2, #4
        bne   vd_open
        lsls  r0, r6, #29
        bmi   vd_open
        ldrb  r0, [r4, #0]
        cmp   r0, #1
        beq   vd_open
        ldrb  r0, [r4, #1]
        cmp   r0, #1
        beq   vd_open
        ldrb  r0, [r4, #2]
        cmp   r0, #1
        beq   vd_open
        ldrb  r0, [r4, #5]
        cmp   r0, #1
        beq   vd_open
        movw  r5, #0xFD20
        adr   r0, t_2p
        movs  r1, #0xFF
        b     vd_go
    vd_open:
        adr   r0, t_open
        movs  r1, #1
        b     vd_go
    vd_5:
        lsls  r0, r6, #29
        bpl   vd_pass
        adr   r2, pats
        movs  r6, #0
    vp_pat:
        movs  r1, #0
    vp_cmp:
        ldrb  r0, [r3, r1]
        ldrb.w ip, [r2, r1]
        cmp   r0, ip
        bne   vp_nextpat
        adds  r1, #1
        cmp   r1, #8
        blt   vp_cmp
        movw  r5, #0xFD20
        adr   r0, t_xo0
        add.w r0, r0, r6, lsl #4
        movs  r1, #0xFF
        b     vd_go
    vp_nextpat:
        adds  r2, #8
        adds  r6, #1
        cmp   r6, #3
        blt   vp_pat
        adr   r0, t_mis
        movs  r1, #3
        b     vd_go
    vd_pass:
        movw  r5, #0x07E0
        adr   r0, t_str
        cmp   r7, #0
        bne   vd_pp
        adr   r0, t_4p
    vd_pp:
        movs  r1, #0xFF
    vd_go:                                  @ r0 label, r1 result code whose wires are listed (0xFF none), r5 colour
        add   r2, sp, #8
    vg_cp:
        ldrb  r3, [r0], #1
        cmp   r3, #0
        beq   vg_list
        strb  r3, [r2], #1
        b     vg_cp
    vg_list:
        cmp   r1, #0xFF
        beq   vg_end
        movs  r7, #8
        cmp   r1, #0
        bne   vg_from
        movs  r7, #9                        @ the shield is listed only for a short
    vg_from:
        movs  r6, #0
    vg_l:
        ldrb  r3, [r4, r6]
        cmp   r3, r1
        bne   vg_n
        movs  r3, #32
        strb  r3, [r2], #1
        add.w r3, r6, #49
        cmp   r6, #8
        bne   vg_s
        movs  r3, #71
    vg_s:
        strb  r3, [r2], #1
    vg_n:
        adds  r6, #1
        cmp   r6, r7
        blt   vg_l
    vg_end:
        movs  r3, #0
        strb  r3, [r2]
        add   r0, sp, #8
        subs  r6, r2, r0                    @ length
        ldr   r4, fg_addr
        ldr   r7, [r4]
        str   r5, [sp]
        movs  r0, #8
        movw  r1, #271
        movs  r2, #231
        movw  r3, #286
        bl    v_shape
        strh  r5, [r4, #2]
        movs  r0, #0
        movw  r1, #0xF800
        cmp   r5, r1
        bne   vg_fg
        movw  r0, #0xFFFF
    vg_fg:
        strh  r0, [r4]
        movs  r0, #16
        str   r0, [sp]
        add   r0, sp, #8
        str   r0, [sp, #4]
        lsls  r2, r6, #3
        rsb.w r0, r6, #30
        lsls  r0, r0, #2
        movw  r1, #271
        movs  r3, #16
        bl    v_blit
        str   r7, [r4]
        add   sp, #48
        pop.w {{r0, r1, r2, r4, r5, r6, r7, lr}}
        b     v_retry
""" + data

def build(parent, parent_sha=PARENT_SHA, old=b"PN2.34H\0", new=b"PN2.34W\0"):
    d = bytearray(parent)
    assert hashlib.sha256(d).hexdigest() == parent_sha, "unexpected parent"
    off, ln, end = struct.unpack_from("<III", d, 0x20)
    assert not any(d[off + ln:]) and ln % 4 == 0
    f = lambda a: a - APP + HDR
    rd = lambda a, n: bytes(d[f(a):f(a) + n])
    cave = APP + ln
    code = asm(source(), cave)
    code += b"\0" * (-len(code) % 4)
    marker = struct.pack("<4H", *[v for p in CURVE[:2] for v in p])
    ncode = code.index(marker)
    allowed = {GUI_BLIT, DRAW_SHAPE, ASSET, DELAY, RETRY_POST, BATT_TAIL, FRAME_HOOK}
    seen = set()
    for i in Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS).disasm(code[:ncode], cave):
        if i.mnemonic in ("bl", "b.w", "b") or (i.mnemonic[0] == "b" and len(i.mnemonic) == 3):
            if i.op_str.startswith("#"):
                t = int(i.op_str[1:], 16)
                if not cave <= t < cave + ncode:
                    assert t in allowed, f"stray branch at {i.address:#x} -> {t:#x}"
                    seen.add(t)
    assert seen == allowed, [hex(x) for x in allowed - seen]
    assert len(code) <= len(d) - off - ln, "no room"
    d[off + ln: off + ln + len(code)] = code
    struct.pack_into("<III", d, 0x20, off, ln + len(code), off + ln + len(code) - 1)
    def poke(a, old, new):
        assert rd(a, len(old)) == old, f"{a:#x}: {rd(a, len(old)).hex()}"
        assert len(old) == len(new); d[f(a):f(a) + len(new)] = new
    poke(SITE_BATT, asm(f"bl {BATT_TAIL:#x}", SITE_BATT), asm(f"bl {cave:#x}", SITE_BATT))
    poke(SITE_BOOT, bytes.fromhex("4ff4fa70") + asm(f"bl {DELAY:#x}", SITE_BOOT + 4),
         asm(f"bl {cave + 4:#x}", SITE_BOOT) + bytes.fromhex("00bf00bf"))
    poke(SITE_FAR, asm(f"bl {RETRY_POST:#x}", SITE_FAR), asm(f"bl {cave + 8:#x}", SITE_FAR))
    poke(SITE_SW, asm(f"bl {RETRY_POST:#x}", SITE_SW), asm(f"bl {cave + 12:#x}", SITE_SW))
    poke(0x0800F4F4, asm("bl 0x0801B1DC", 0x0800F4F4), bytes.fromhex("00bf00bf"))   # skip the stock animated FNIRSI logo
    for site in SITES_START:
        poke(site, asm(f"bl {FRAME_HOOK:#x}", site), asm(f"bl {cave + 16:#x}", site))
    n = 0; p = d.find(old)
    while p >= 0:
        d[p:p + 8] = new; n += 1; p = d.find(old, p + 1)
    assert n == 2
    return bytes(d), cave, len(code)

if __name__ == "__main__":
    out, cave, n = build(open(sys.argv[1], "rb").read())
    open(sys.argv[2], "wb").write(out)
    print(f"code+data at {cave:#x}, {n} bytes; file {len(out)} bytes")
    print("sha256", hashlib.sha256(out).hexdigest())
