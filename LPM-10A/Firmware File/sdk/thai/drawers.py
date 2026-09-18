"""The Thai text drawers and the gui_blit hook, in the assembler's Thumb subset.

The drawers keep the stock signatures so no call site changes:

  thai_cjk_text(x, y, u8* s, count)      replaces cjk_text   0x080176AC
  thai_mixed_text(x, y, u16* s, count)   replaces mixed_text 0x080173EC

Rules (the mock-up model in thai/engine.py):
  * count != 0  ->  centre the string on x: x -= (sum(adv) - 1) / 2
  * every cell is drawn transparent by the stock glyph drawer GLYPH(x, y, idx, 1)
    and advances by WTAB[idx] (ink width + 1 px gap); a byte >= 0xAB ends the string
  * REDIRECT stubs: a cjk string whose second byte is 0xAC ([cell, 0xAC, idx, ...]) and
    a mixed string whose second unit is 0x01AC ([0x01nn, 0x01AC, idx, ...]) stand for
    RELOC[idx], a cjk-kind string in the freed glyph area.  The first byte/unit is a
    valid cell so that stock's strlen helpers (which stop at 0xFF / at a terminator
    unit) still return a non-zero count for centred strings.  Stock references
    (adr, ldm / ldr / memcpy stack copies, strided tables) are untouched: only the
    first 3..8 bytes of each old slot matter.
  * a mixed string that is not a stub is drawn exactly as stock draws it (16 px per
    glyph unit, 8 px per ASCII unit, centred by half of that): the English "Switch" /
    "Far end" boxes go through this path, so English stays pixel-identical.

blit_hook is entered from the first instruction of gui_blit (0x080174E8) with the
arguments untouched: (x, y, w, h, [sp]=size, [sp+4]=str).  While the language is
Thai and size == 16 it looks the string up in HOOKTAB (12-byte entries:
u32 ascii, u32 thai, u16 flags, u16 x) and either draws the Thai text itself and
returns to gui_blit's caller, or moves x (the "..." animation) and falls through
into gui_blit.  Anything else falls through untouched.

Symbols: GLYPH, ASCII_GLYPH, LANG_IS, DRAW_SHAPE, GUI_BLIT_CONT (0x080174EC|1),
WTAB, RELOC, HOOKTAB, BG_COLOUR, THAI_CJK_TEXT.
"""

F_CENTRE, F_X, F_ASCII, F_CLEAR, F_AT68 = 1, 2, 4, 8, 16

CJK_TEXT = """
thai_cjk_text:                  ; r0 x, r1 y, r2 s, r3 count
        push {r4, r5, r6, r7, lr}
        mov  r4, r0
        mov  r5, r1
        mov  r6, r2
        mov  r7, r3
        ldrb r0, [r6, #1]
        cmp  r0, #0xAC
        bne  cjk_nored
        ldrb r0, [r6, #2]          ; redirect index
        lsls r0, r0, #2
        ldr  r1, =RELOC
        adds r1, r1, r0
        ldr  r6, [r1]
cjk_nored:
        cbz  r7, cjk_draw
        movs r3, #0                ; width = sum(adv) - 1
        mov  r1, r6
cjk_meas:
        ldrb r0, [r1]
        cmp  r0, #0xAB
        bhs  cjk_meas_done
        ldr  r2, =WTAB
        adds r2, r2, r0
        ldrb r2, [r2]
        adds r3, r3, r2
        adds r1, #1
        b    cjk_meas
cjk_meas_done:
        cbz  r3, cjk_draw
        subs r3, #1
        lsrs r3, r3, #1
        subs r4, r4, r3
        uxth r4, r4
cjk_draw:
        ldrb r2, [r6]
        cmp  r2, #0xAB
        bhs  cjk_done
        mov  r0, r4
        mov  r1, r5
        movs r3, #1
        bl   GLYPH
        ldrb r2, [r6]
        ldr  r0, =WTAB
        adds r0, r0, r2
        ldrb r0, [r0]
        adds r4, r4, r0
        adds r6, #1
        b    cjk_draw
cjk_done:
        pop  {r4, r5, r6, r7, pc}
"""

MIXED_TEXT = """
thai_mixed_text:                ; r0 x, r1 y, r2 u16* s, r3 count
        push {r4, r5, r6, r7, lr}
        sub  sp, #4                ; 5th argument slot for ASCII_GLYPH
        mov  r4, r0
        mov  r5, r1
        mov  r6, r2
        mov  r7, r3
        ldrh r0, [r6, #2]
        movw r1, #0x01AC
        cmp  r0, r1
        bne  mix_plain
        ldrh r0, [r6, #4]          ; redirect index -> a cjk-kind string
        lsls r0, r0, #2
        ldr  r1, =RELOC
        adds r1, r1, r0
        ldr  r2, [r1]
        mov  r0, r4
        mov  r1, r5
        mov  r3, r7
        add  sp, #4
        pop  {r4, r5, r6, r7}
        add  sp, #4                ; drop lr: thai_cjk_text returns to our caller
        b.w  THAI_CJK_TEXT
mix_plain:                      ; not a stub: stock's own rules (English "Switch" / "Far end" use this)
        cbz  r7, mix_draw
        movs r3, #0                ; width = 16 per glyph unit + 8 per ASCII unit, centre = x - width/2
        mov  r1, r6
mix_meas:
        ldrh r0, [r1]
        cmp  r0, #0xFF
        bls  mix_meas_ascii
        ldrb r0, [r1]
        cmp  r0, #0xAB
        bhs  mix_meas_done
        adds r3, #16
        adds r1, #2
        b    mix_meas
mix_meas_ascii:
        cmp  r0, #0x7E
        bhi  mix_meas_done
        cmp  r0, #0x20
        blo  mix_meas_done
        adds r3, #8
        adds r1, #2
        b    mix_meas
mix_meas_done:
        lsrs r3, r3, #1
        subs r4, r4, r3
        uxth r4, r4
mix_draw:
        ldrh r2, [r6]
        cmp  r2, #0xFF
        bls  mix_ascii
        ldrb r2, [r6]
        cmp  r2, #0xAB
        bhs  mix_done
        mov  r0, r4
        mov  r1, r5
        movs r3, #1
        bl   GLYPH
        adds r4, #16
        adds r6, #2
        b    mix_draw
mix_ascii:
        cmp  r2, #0x7E
        bhi  mix_done
        cmp  r2, #0x20
        blo  mix_done
        movs r0, #0
        str  r0, [sp]
        mov  r0, r4
        mov  r1, r5
        movs r3, #16
        bl   ASCII_GLYPH
        adds r4, #8
        adds r6, #2
        b    mix_draw
mix_done:
        add  sp, #4
        pop  {r4, r5, r6, r7, pc}
"""

BLIT_HOOK = """
blit_hook:                      ; r0 x, r1 y, r2 w, r3 h, [sp] size, [sp+4] str
        push {r4, r5, r6, r7, lr}
        mov  r4, r0
        mov  r5, r1
        mov  r6, r2
        mov  r7, r3
        push {r6, r7}              ; [sp] w, [sp+4] h, [sp+8..0x14] caller r4-r7, [sp+0x18] lr, [sp+0x1C] size, [sp+0x20] str
        movs r0, #2
        bl   LANG_IS               ; r0 = (language == 2 = Thai)
        cmp  r0, #0
        beq  hk_pass
        ldr  r0, [sp, #0x1C]
        cmp  r0, #16
        bne  hk_pass
        ldr  r6, =HOOKTAB          ; r6 = table entry
hk_tab:
        ldr  r0, [r6]              ; ascii pointer, 0 = end of table
        cmp  r0, #0
        beq  hk_pass
        ldr  r1, [sp, #0x20]       ; the string being drawn
hk_cmp:
        ldrb r2, [r0]
        ldrb r3, [r1]
        cbz  r2, hk_cmp_end
        cmp  r2, r3
        bne  hk_next
        adds r0, #1
        adds r1, #1
        b    hk_cmp
hk_cmp_end:                     ; table string ended: the drawn string must end here too
        cmp  r3, #0x20
        blo  hk_match
        cmp  r3, #0x7E
        bhi  hk_match
hk_next:
        adds r6, #12
        b    hk_tab
hk_match:
        ldrh r7, [r6, #8]          ; flags
        movs r0, #16
        ands r0, r7
        beq  hk_f8
        cmp  r4, #68               ; F_AT68: only the string drawn at x = 68
        bne  hk_next
hk_f8:
        movs r0, #8
        ands r0, r7
        beq  hk_f2
        ldr  r0, =BG_COLOUR        ; F_CLEAR: wipe the 16-px line x 12..220 in the background colour
        ldrh r0, [r0]
        sub  sp, #4
        str  r0, [sp]
        movs r0, #12
        mov  r1, r5
        movs r2, #220
        mov  r3, r5
        adds r3, #15
        bl   DRAW_SHAPE
        add  sp, #4
hk_f2:
        movs r0, #2
        ands r0, r7
        beq  hk_f4
        ldrh r4, [r6, #10]         ; F_X: start at this x
hk_f4:
        movs r0, #4
        ands r0, r7
        bne  hk_pass               ; F_ASCII: keep the ASCII text, only x changed (r4)
        movs r3, #0                ; count 0 = left aligned at x
        movs r0, #1
        ands r0, r7
        beq  hk_draw
        ldr  r0, [sp]              ; F_CENTRE: centre on x + w/2
        lsrs r0, r0, #1
        adds r4, r4, r0
        movs r3, #1
hk_draw:
        mov  r0, r4
        mov  r1, r5
        ldr  r2, [r6, #4]          ; thai string (cjk kind)
        bl   THAI_CJK_TEXT
        add  sp, #8
        pop  {r4, r5, r6, r7, pc}  ; back to gui_blit's caller, nothing else drawn
hk_pass:
        pop  {r6, r7}              ; w, h
        mov  r0, r4
        mov  r1, r5
        mov  r2, r6
        mov  r3, r7
        ldr  r4, [sp, #16]
        mov  lr, r4
        pop  {r4, r5, r6, r7}      ; the caller's registers
        add  sp, #4                ; drop the saved lr
        .short 0xe92d, 0x47f8      ; push.w {r3-r8, sb, sl, lr}: gui_blit's displaced first instruction
        b.w  GUI_BLIT_CONT
"""
