"""
Patch set for LPM-10A TX firmware V2.0.7.

Each patch is a function taking the Image and doing its edits.  Patches are
grouped so a build can select exactly what it wants.  Anything that cannot be
verified without hardware is marked risk="untested" and left out of the
default build.

risk levels
    safe      byte-for-byte reversible edit, verified by disassembly+emulation
    low       behavioural change, verified by emulation, semantics well understood
    untested  needs a real device to confirm; not in the default build
"""

import os

from lpm10a.image import PatchError

HERE = os.path.dirname(os.path.abspath(__file__))
REGISTRY = []


def patch(pid, title, risk, default=True, group="misc"):
    def deco(fn):
        fn.pid, fn.title, fn.risk, fn.default, fn.group = pid, title, risk, default, group
        REGISTRY.append(fn)
        return fn
    return deco


# =====================================================================
# Group: correctness fixes
# =====================================================================

@patch("autooff-hold", "Auto Off is held while a SCAN tone or FLASH blink session is running",
       risk="low", group="bugfix")
def p_autooff_hold(img):
    """
    Stock already resets the auto-off idle counter on every key event
    (Action_key_Process ends with autooff_timer_reset, 0x08014ACE) and after
    every Length / Speed result.  What it never does is pause the counter
    while the unit is deliberately left alone to do a job: the SCAN tone and
    the FLASH port-blink keep running while home_1s_housekeeping counts, so
    with Auto Off at 5 / 10 / 15 min the tester switches itself off in the
    middle of a cable trace.  Professional toners keep the tone alive until
    it is stopped.

    home_1s_housekeeping (0x0800F968, once per second) reads the system
    state and stops counting when it is 0 (OFF).  The `movs r0,#0; bl
    get_sysState` that fetches the state is redirected to a cave routine that
    returns 0 instead of the real state while

        state == SCAN  (5) and scan_state[0] != 0      (tone enabled), or
        state == FLASH (8) and test_busy_flags[1] == 2 (blink running),

    and in that case also clears the idle counter, so the full timeout is
    available again once the session ends.  Everywhere else the state is
    returned unchanged and the behaviour is stock.

    (Mod 1's `autooff-keyreset` patch, which this replaces, added a second
    key-press reset that stock did not need.  Its description was wrong.)
    """
    from lpm10a.thumb import assemble

    hook = img.emit_code("""
    autooff_state:              ; -> r0 = sysState, or 0 while a tone / blink session is running
            push {r4, lr}
            movs r0, #0
            bl   get_sysState
            mov  r4, r0
            cmp  r0, #5             ; SCAN
            bne  not_scan
            ldr  r1, =scan_state
            ldrb r1, [r1]           ; [0] = tone enabled
            cmp  r1, #0
            beq  out
            b    hold
    not_scan:
            cmp  r0, #8             ; FLASH
            bne  out
            ldr  r1, =test_busy_flags
            ldrb r1, [r1, #1]       ; 2 = port blink running
            cmp  r1, #2
            bne  out
    hold:   movs r4, #0             ; report OFF: no idle counting this second
            ldr  r1, =auto_off_ctr
            strh r4, [r1]           ; and restart the timeout for afterwards
    out:    mov  r0, r4
            pop  {r4, pc}
    """, why="auto-off: hold while SCAN tone / FLASH blink is active")

    site = 0x0800F974
    img.poke(site, "0020 fff7f5fe", assemble(site, f"bl 0x{hook:08X}\n nop"),
             "home_1s_housekeeping: state via the hold check")


# =====================================================================
# Group: English / presentation
# =====================================================================

@patch("boot-english", "Boot straight to English (no Chinese/English picker)",
       risk="low", group="english")
def p_boot_english(img):
    """
    The factory defaults already set language=2 (English) at settings+0xA5, but
    they also set first_boot_flag=1 at settings+0xA8, which makes the unit open
    the Chinese/English selection screen before the home screen.  Defaulting the
    flag to 0 keeps English and goes straight to the home screen.

    Affects a fresh settings page and Factory Reset; a unit whose language was
    already chosen is unaffected either way.
    """
    # 0x080195B6:  movs r0, #1   ->   movs r0, #0
    img.poke(0x080195B6, "0120", bytes.fromhex("0020"),
             "factory default first_boot_flag = 0 (skip language picker)")


@patch("english-strings", "Correct the machine-translated English UI text",
       risk="safe", group="english")
def p_english(img):
    """
    In-place string corrections.  Every replacement fits the existing slot, so
    no pointer anywhere has to move.  Only obviously-wrong or non-standard
    wording is touched; menu labels users may recognise are left alone.

    The three length-unit labels ("Inch"/"Cent"/"Meter") are owned by the
    `length-decimal` patch because that patch also changes what each slot
    means.
    """
    fixes = [
        # PoE screen
        (0x080135E8, "Standard"),        # was "Standar Type"
        (0x08013D60, "Non-std"),         # was "UnStandar"
        # Settings / factory reset confirmation
        (0x0801188F, " Factory Reset will"),      # was " Factory Reset should"
        (0x080118A8, "erase all your settings"),  # was "reset all of your modiy"
        # Misc wording
        (0x080142B4, "Silent"),          # was "Noiseless"
        (0x08019C10, "Out of range"),    # was "Out of range."
        (0x080679D4, "Test error"),      # was "Test exception!!"
    ]
    for addr, text in fixes:
        img.set_string(addr, text)


# =====================================================================
# Group: measurement (industrial-grade length display)
# =====================================================================

@patch("length-decimal", "Length in m / cm / ft with one decimal, Zero- and NVP-corrected; unit is remembered",
       risk="low", group="measure")
def p_length_decimal(img):
    """
    Stock behaviour, verified by disassembly of length_convert (0x08019774)
    and length_result_draw (0x080199B0):

      unit 0 "Inch"  -> trunc(cm / 2.54)      shown as an integer
      unit 1 "Cent"  -> cm                    shown as an integer
      unit 2 "Meter" -> round(cm / 100)       shown as an INTEGER (55.4 m -> "55")

    and the unit index is forced to 1 (cm) every time the Length screen is
    entered (0x08012F1C), so a unit choice never survives leaving the
    screen.  Whole metres is far below what a cable tester should show;
    inches is not a cable unit at all.

    New behaviour (fixed-point, integer maths only, no FPU / soft-double):

      cm0 = cm - 10 * ZERO  when settings byte 0xC5 (Zero, 0.1 m steps) is
                            0..20, else cm0 = cm; a result <= 0 becomes 0
                            ("out of range" for that pair).  The PHY's
                            reading includes its own internal path, about
                            0.4 m on the unit measured (2.9 m -> 3.34 m,
                            14 m -> 14.7 m at NVP 69 %), which NVP alone
                            cannot remove because NVP is a factor.
      cm' = cm0 * NVP / 69  when settings byte 0xA6 (NVP %) is 50..99,
                            else cm' = cm0  (0 = factory default = 69 %)
      unit 0 "m"   -> round(cm' / 10)         shown as "%d.%d"   (55.4)
      unit 1 "cm"  -> cm'                     shown as "%d"      (5540)
      unit 2 "ft"  -> round(cm' / 3.048)      shown as "%d.%d"   (181.8)

    The unit index is loaded from settings byte 0xA7 on entry (0 = metres,
    out of range = metres) and written back whenever it is changed, so it
    persists like every other setting (the whole struct is flashed at
    power-off).  Bytes 0xA6/0xA7 are zeroed by the factory-defaults writer
    and never read by stock code, so they are free.  Byte 0xC5 is struct
    padding after the 0x1C-byte net_cfg block (0xA9..0xC4): never read or
    written by stock, so its content on a fresh unit is whatever the flash
    page held (0x00 or 0xFF); anything above 20 is treated as 0, and the
    `nvp-calibration` patch makes Factory Reset write 0.  NVP and Zero are
    edited by that patch; without it the bytes stay 0 and the conversion
    is the identity.  Screen entry also resets the UP/DOWN target (RAM
    byte `adj_target`, arena) to NVP.

    Mechanics:
      * length_convert is redirected (b.w) to a cave routine; the old body
        stays in flash but is never executed.
      * the one sprintf call in length_result_draw (0x08019B12) is redirected
        to a cave wrapper that splits the fixed-point value into "%d.%d" for
        units 0 and 2 and passes cm straight through for unit 1.  It returns
        sprintf's length so the unit label is still placed right after the
        number.
      * the "Out of range" test (all four values == 0) is unaffected: any
        non-zero cm value is still non-zero after conversion.
      * 0x08012F1C `movs r0,#1; strb r0,[r1,#0xc]` -> `bl unit_load`
        (r1 = test_busy_flags there; r0/r1 are dead afterwards).
      * 0x08012EC8 `movs r2,#0; mov r1,r2; movs r0,#0x1c` -> `bl unit_save; nop`
        which stores the new index and then sets up the same three
        registers for the GUI_MSG_SEND that follows.
    """
    from lpm10a.thumb import assemble

    img.adj_target = getattr(img, "adj_target", None) or img.alloc_ram(4)
    syms = {"NVP": 0x20000C78 + 0xA6, "UNIT": 0x20000C78 + 0xA7,
            "ZERO": 0x20000C78 + 0xC5, "ADJ": img.adj_target}

    conv = img.emit_code("""
    length_convert2:            ; r0 = cm (u16)  ->  r0 = display value
            push {r4, lr}
            ldr  r1, =ZERO
            ldrb r1, [r1]
            cmp  r1, #20
            bhi  nvp                ; unset / garbage: no offset
            movs r2, #10
            muls r1, r2, r1         ; zero in cm
            subs r0, r0, r1
            bgt  nvp
            movs r0, #0             ; at or below the zero: out of range
            b    done
    nvp:    ldr  r1, =NVP
            ldrb r1, [r1]
            cmp  r1, #50
            blo  nocal
            cmp  r1, #99
            bhi  nocal
            mul  r0, r0, r1         ; cm * NVP
            adds r0, #34
            movs r1, #69
            udiv r0, r0, r1         ; / 69, rounded  (69 % == factory calibration)
    nocal:  ldr  r1, =leng_unit_idx
            ldrb r1, [r1]
            cmp  r1, #1
            beq  done               ; cm: unchanged
            cmp  r1, #2
            beq  feet
            ; metres x10 = (cm + 5) / 10
            adds r0, #5
            movs r1, #10
            udiv r0, r0, r1
            b    done
    feet:   ; feet x10 = (cm * 1000 + 1524) / 3048
            movw r1, #1000
            mul  r0, r0, r1
            movw r1, #1524
            add  r0, r1
            movw r1, #3048
            udiv r0, r0, r1
    done:   uxth r0, r0
            pop  {r4, pc}
    """, extra_syms=syms, why="length_convert: NVP scale + fixed-point m/cm/ft")

    uload = img.emit_code("""
    unit_load:                  ; Length screen entry; r1 = test_busy_flags (r0, r2 dead)
            ldr  r0, =ADJ
            movs r2, #0
            strb r2, [r0]           ; UP/DOWN adjust NVP first
            ldr  r0, =UNIT
            ldrb r0, [r0]
            cmp  r0, #2
            bls  ok
            movs r0, #0
    ok:     strb r0, [r1, #0xc]     ; leng_unit_idx
            bx   lr
    """, extra_syms=syms, why="load remembered length unit on screen entry")

    usave = img.emit_code("""
    unit_save:                  ; after a unit change; falls into GUI_MSG_SEND(0x1c, 0, 0)
            ldr  r0, =leng_unit_idx
            ldrb r0, [r0]
            ldr  r1, =UNIT
            strb r0, [r1]
            movs r2, #0
            movs r1, #0
            movs r0, #0x1c
            bx   lr
    """, extra_syms=syms, why="remember the length unit in settings")

    site = 0x08012F1C
    img.poke(site, "0120 0873", assemble(site, f"bl 0x{uload:08X}"),
             "Length screen entry: unit from settings (was: always cm), adjust target = NVP")
    site = 0x08012EC8
    img.poke(site, "0022 1146 1c20", assemble(site, f"bl 0x{usave:08X}\n nop"),
             "unit change: store to settings")

    fmt = img.emit_code("""
    length_sprintf:             ; r0=buf r1="%s = %d" r2=name r3=value
            push {r4, r5, lr}
            sub  sp, #4
            ldr  r4, =leng_unit_idx
            ldrb r4, [r4]
            cmp  r4, #1
            beq  plain              ; cm: stock format
            movs r4, #10
            udiv r5, r3, r4         ; integer part
            mls  r4, r5, r4, r3     ; tenths = value - int*10
            str  r4, [sp]           ; 5th vararg
            mov  r3, r5
            ldr  r1, =fmt_dec
    plain:  bl   sprintf
            add  sp, #4
            pop  {r4, r5, pc}
    fmt_dec:
            .asciz "%s = %d.%d"
    """, why="length_result_draw: decimal formatter")

    # length_convert: push {r4-r6,lr}; vpush {d8,d9}  ->  b.w cave; nop
    site = 0x08019774
    code = assemble(site, f"b.w 0x{conv:08X}\n nop")
    assert len(code) == 6
    img.poke(site, "70b5 2ded048b", code, "length_convert -> fixed-point cave routine")

    # length_result_draw: bl sprintf -> bl length_sprintf
    site = 0x08019B12
    code = assemble(site, f"bl 0x{fmt:08X}")
    img.poke(site, "f0f73bfc", code, "sprintf -> decimal-aware wrapper")

    # unit labels, slot order 0/1/2
    img.set_string(0x08067ACC, "m")       # was "Inch"  (slot 0: now metres, the default)
    img.set_string(0x08067AD4, "cm")      # was "Cent"
    img.set_string(0x08067ADC, "ft")      # was "Meter" (slot 2: now feet)


@patch("nvp-calibration", "NVP and Zero calibration: UP/DOWN on the Length screen, long-press OK switches, both saved",
       risk="low", group="measure")
def p_nvp(img):
    """
    Nominal Velocity of Propagation calibration, as on professional testers.

    The PHY reports length assuming one fixed cable velocity.  Real cables
    differ by several percent, so a tester must let the user set NVP (or
    calibrate against a cable of known length).  Stock has nothing.

    UI: on the Length screen, UP / DOWN (click or auto-repeat) change the
    active value: NVP by 1 % within 50..99 %, or Zero by 0.1 m within
    0.0..2.0 m.  A long press of OK switches between the two; the active one
    is drawn white, the other grey.  "NVP 69%" sits to the right of the Unit
    box, "ZERO 0.4m" to its left, and the four pair lengths are redrawn
    immediately with the new correction, so a known cable can be dialled in
    without re-measuring.  Calibrate with two cables: set Zero on a short one
    (3 m), NVP on a long one (15 m or more), repeat once.
    69 % / 0.0 m are the factory values; Factory Reset returns to them
    (the defaults writer is hooked to clear the Zero byte, which stock never
    touches).  NVP lives in settings byte 0xA6 and Zero in 0xC5, written to
    flash at power-off like every other setting.  Screen entry always starts
    with NVP active.

    Hooks (all verified by emulation in verify.py):
      * Action_key_Process 0x08014A04: `movs r0,#1; bl get_sysState` ->
        `bl key_hook; nop`.  The hook returns the same state mask in r0 and,
        when the state is LENGTH and the key is UP/DOWN, adjusts the active
        value, resets the backlight/auto-off timer and posts GUI message
        0x3D; a long press (event 6) of OK toggles the active value and
        posts 0x3D.  UP/DOWN and OK-long-press have no binding in the
        LENGTH state in the stock key table (OK click = 0x11 "Test Start"
        is untouched; the HAL emits press_release (event 7), not a click,
        when the 1 s hold ends, and events 8/10/12 while held, none bound
        in LENGTH).
      * Factory defaults 0x080195BC: `movs r0,#0; b loop` -> `bl zero_default`,
        which clears settings byte 0xC5 and continues into the stock loop
        with r0 = 0 and r1 = the settings base, as before.
      * APP_GUI_task 0x0800F48C: `cmp r0,#0x3d; bhs exit` -> `b.w gui_hook`.
        Messages below 0x3D continue to the stock jump table; 0x3D redraws
        the NVP text and the results; anything else exits as before.
      * length_unit_picker_draw 0x08019970 (the Length screen header): its
        epilogue is routed through the cave so the NVP text is drawn when
        the screen opens.
    """
    from lpm10a.thumb import assemble

    img.adj_target = getattr(img, "adj_target", None) or img.alloc_ram(4)
    syms = {"NVP": 0x20000C78 + 0xA6, "ZERO": 0x20000C78 + 0xC5, "ADJ": img.adj_target,
            "GUI_TBB": 0x0800F490, "GUI_EXIT": 0x0800F4DC}

    draw = img.emit_code("""
    nvp_draw:                   ; "NVP nn%" at (166, 90) and "ZERO n.nm" at (4, 90); active one white, other grey
            push {r4, r5, lr}
            sub  sp, #20            ; text buffer
            ldr  r4, =ADJ
            ldrb r4, [r4]
            cmp  r4, #1
            bls  adjok
            movs r4, #0             ; arena garbage -> NVP active
    adjok:  ldr  r0, =NVP
            ldrb r0, [r0]
            cmp  r0, #50
            blo  dflt
            cmp  r0, #99
            bls  have
    dflt:   movs r0, #69
    have:   mov  r2, r0
            ldr  r1, =fmt
            mov  r0, sp
            bl   sprintf
            mov  r0, r4             ; 0 = white (NVP active), 1 = grey
            bl   colour
            movs r0, #166           ; x
            movs r1, #56            ; w = 7 chars
            mov  r2, sp
            bl   blit
            ldr  r0, =ZERO
            ldrb r0, [r0]
            cmp  r0, #20
            bls  zok
            movs r0, #0
    zok:    movs r1, #10
            udiv r2, r0, r1         ; metres
            mls  r3, r2, r1, r0     ; tenths
            ldr  r1, =fmtz
            mov  r0, sp
            bl   sprintf
            movs r0, #1
            subs r0, r0, r4         ; 0 = white when ZERO is active
            bl   colour
            movs r0, #4             ; x
            movs r1, #72            ; w = 9 chars
            mov  r2, sp
            bl   blit
            add  sp, #20
            pop  {r4, r5, pc}
    colour:                     ; r0 = 0 white / 1 grey; background black (screen is cleared to black)
            ldr  r1, =0x200001AC
            cmp  r0, #0
            bne  grey
            movw r0, #0xFFFF
            b    setc
    grey:   movw r0, #0x8410
    setc:   strh r0, [r1]
            movs r0, #0
            strh r0, [r1, #2]
            bx   lr
    blit:                       ; r0 = x, r1 = w, r2 = string; y = 90, h = 16, font 16
            push {r4, lr}
            sub  sp, #8
            movs r4, #0x10
            str  r4, [sp]           ; font size 16
            str  r2, [sp, #4]       ; string
            mov  r2, r1             ; w
            movs r1, #90            ; y
            movs r3, #16            ; h
            bl   gui_blit
            add  sp, #8
            pop  {r4, pc}
    fmt:    .asciz "NVP %2d%%"
    fmtz:   .asciz "ZERO %d.%dm"
    """, extra_syms=syms, why="draw the NVP and Zero values on the Length screen")

    key = img.emit_code("""
    key_hook:                   ; in: r5 = key event {u8 key, u8 evt}; out: r0 = 1 << sysState
            push {r4, lr}
            movs r0, #1
            bl   get_sysState
            mov  r4, r0
            cmp  r0, #0x80          ; LENGTH screen only
            bne  out
            ldrb r1, [r5]           ; key: 2 = UP, 3 = DOWN, 4 = OK
            ldrb r0, [r5, #1]       ; event: 3 = click, 6 = long press, 12 = auto-repeat
            cmp  r1, #4
            bne  ud
            cmp  r0, #6             ; OK long press: switch NVP <-> ZERO
            bne  out
            ldr  r2, =ADJ
            ldrb r0, [r2]
            cmp  r0, #1
            beq  tonvp
            movs r0, #1
            b    store
    tonvp:  movs r0, #0
            b    store
    ud:     cmp  r0, #3
            beq  updown
            cmp  r0, #12
            bne  out
    updown: ldr  r2, =ADJ
            ldrb r2, [r2]
            cmp  r2, #1
            beq  zero
            ldr  r2, =NVP
            ldrb r0, [r2]
            cmp  r0, #50
            blo  dflt
            cmp  r0, #99
            bls  have
    dflt:   movs r0, #69
    have:   cmp  r1, #2
            bne  down
            cmp  r0, #99
            beq  out
            adds r0, #1
            b    store
    down:   cmp  r1, #3
            bne  out
            cmp  r0, #50
            beq  out
            subs r0, #1
            b    store
    zero:   ldr  r2, =ZERO
            ldrb r0, [r2]
            cmp  r0, #20
            bls  zhave
            movs r0, #0
    zhave:  cmp  r1, #2
            bne  zdown
            cmp  r0, #20
            beq  out
            adds r0, #1
            b    store
    zdown:  cmp  r1, #3
            bne  out
            cmp  r0, #0
            beq  out
            subs r0, #1
    store:  strb r0, [r2]
            movs r0, #0x64
            bl   key_activity_notify
            movs r2, #0
            movs r1, #0
            movs r0, #0x3D
            bl   GUI_MSG_SEND
    out:    mov  r0, r4
            pop  {r4, pc}
    """, extra_syms=syms, why="UP/DOWN adjust NVP or Zero on the Length screen; OK long press switches")

    gui = img.emit_code("""
    gui_hook:                   ; r0 = GUI message id
            cmp  r0, #0x3D
            blo  back
            beq  mine
            b.w  GUI_EXIT
    mine:   bl   nvp_draw
            bl   length_result_draw
            b.w  GUI_EXIT
    back:   b.w  GUI_TBB
    """, extra_syms=dict(syms, nvp_draw=draw | 1), why="GUI message 0x3D: redraw NVP + results")

    tail = img.emit_code("""
    picker_tail:                ; epilogue of length_unit_picker_draw
            bl   nvp_draw
            add  sp, #0x14
            pop  {r4, r5, r6, r7, pc}
    """, extra_syms=dict(syms, nvp_draw=draw | 1), why="draw NVP when the Length screen opens")

    site = 0x08014A04
    img.poke(site, "0120 faf7adfe", assemble(site, f"bl 0x{key:08X}\n nop"),
             "Action_key_Process: NVP key hook")
    site = 0x0800F48C
    img.poke(site, "3d28 25d2", assemble(site, f"b.w 0x{gui:08X}"),
             "APP_GUI_task: message 0x3D")
    site = 0x08019970
    img.poke(site, "05b0 f0bd", assemble(site, f"b.w 0x{tail:08X}"),
             "length_unit_picker_draw: draw NVP and Zero")

    zdef = img.emit_code("""
    zero_default:               ; factory defaults: r1 = settings base; continue the cal loop with r0 = 0
            adds r1, #0xC5
            movs r0, #0
            strb r0, [r1]
            b.w  0x080195E4
    """, why="Factory Reset clears the Zero byte")
    site = 0x080195BC
    img.poke(site, "0020 11e0", assemble(site, f"bl 0x{zdef:08X}"),
             "factory defaults: Zero = 0.0 m")


@patch("length-no-sticky", "Length result no longer sticks to the previous reading",
       risk="low", group="bugfix")
def p_length_no_sticky(img):
    """
    At the end of APP_LENG_Test_Sequence (0x08012B8C..0x08012BF2) each
    channel's new reading is compared with the previous reading kept in
    leng_last_result_cm.  If they differ by less than the tolerance band
    (1 m below 10 m, 3 m below 100 m, 5 m below 200 m, else 6 m) the NEW
    value is discarded and the OLD one is displayed.

    So after measuring a 50 m cable, a 52 m cable still reads "50 m", and a
    6 m cable measured after a 5 m one reads "5 m".  A measuring instrument
    must display what it measured; the four-pair vote already provides the
    noise rejection.

        0x08012BC2:  bge 0x8012bd6   ->   b 0x8012bd6

    The compare result is ignored and the new value is always stored.
    """
    img.poke(0x08012BC2, "08da", bytes.fromhex("08e0"),
             "always accept the new length reading")


AVG_RUNS = 4     # CSD runs averaged per Test Start (1 = one run shown as is); build-time constant
DEAD_BODY = 0x0801977A          # stock length_convert body, unreachable since length-decimal
DEAD_BODY_END = 0x080197EC      # its literal pool ends here; 114 bytes


@patch("length-average", f"Length test averages {AVG_RUNS} CSD runs per pair before it is shown",
       risk="low", group="measure")
def p_length_average(img):
    """
    The PHY's cable diagnostic scatters by about +/-0.2..0.3 m from run to
    run (measured on a real unit: a 14 m cable read 14.4 / 14.6 / 15.0 /
    14.8 m).  Zero and NVP correct the mean, not the scatter.  Stock runs the
    diagnostic once (twice if the four pairs disagree) and shows that run.

    This patch runs the whole CSD sequence AVG_RUNS times and shows, per
    pair, the mean of the runs in which that pair produced a reading (a 0,
    i.e. "out of range" after the blind-zone cut, is left out; a pair that
    never reads stays 0).  Averaging 4 runs halves the scatter.  The test
    takes AVG_RUNS times longer.  The stock 20 s timeout is measured from a
    start tick in the frame ([sp+0x20], stamped once at 0x080119F8); the
    hook re-stamps it on every run, so each run gets its own 20 s and a
    slow diagnostic cannot turn a 4-run test into "Test timeout".

    Mechanics.  APP_LENG_Test_Sequence already contains a re-run loop: at
    0x08012AE0 it reads the retry counter [sp+0x24], accepts the result when
    the counter is >= 1 or the four pairs agree, otherwise increments it and
    jumps back to 0x08011A6E (the start of the sequence, same stack frame).
    The first three instructions of that block
        0x08012AE0  ldr r0,[sp,#0x24]; cmp r0,#1; bge 0x08012B86
    become `bl avg_hook; b 0x08012B0A`.  The hook uses the same counter as
    the run index and accumulates the four post-vote values (u16[4] at
    sp+0x4C) into a RAM-arena accumulator.  While fewer than AVG_RUNS runs
    are done it returns, and the `b 0x08012B0A` takes the stock retry path
    (counter++, a log line, re-entry at 0x08011A6E with the same frame).
    After AVG_RUNS runs it writes the per-pair means back into the frame and
    continues at the stock accept path 0x08012B86 directly.  The stock
    "retry when the pairs disagree" test is thereby bypassed (each run's
    four-pair vote still happens before the hook).  r4-r7 are pushed and
    popped; the sequence itself saves only lr and does not use them.

    The code lives in the body of the stock length_convert (0x0801977A..
    0x080197EB), which the length-decimal patch made unreachable (its entry
    is a b.w to the cave and it has no other caller); the cave itself is
    full.  With AVG_RUNS = 1 there is one run, shown as is (stock's retry on
    disagreeing pairs is gone in every configuration).

    Trade-off, documented rather than hidden: an outlier run is averaged in
    (weight 1/AVG_RUNS) where stock would have retried once and shown the
    retry; the per-run four-pair vote still rejects single-pair outliers.
    """
    from lpm10a.thumb import assemble
    if not 1 <= AVG_RUNS <= 8:
        raise PatchError("AVG_RUNS must be 1..8")
    if img.read(0x08019774, 4) != bytes.fromhex("4ef0aeba"):
        raise PatchError("length-average needs length-decimal (the stock length_convert body must be dead)")
    acc = img.alloc_ram(20)     # u32 acc[4] + u8 n[4]
    code = assemble(DEAD_BODY, f"""
    avg_hook:                   ; entered by bl from 0x08012AE0; frame: [sp+0x24] run, sp+0x4C u16[4]
            push {{r4, r5, r6, r7, lr}}
            bl   xTaskGetTickCount
            str  r0, [sp, #0x34]    ; restart the 20 s timeout for this run ([sp+0x20] of the sequence)
            ldr  r4, =ACC           ; u32 acc[4], then u8 n[4] at +16
            mov  r3, r4
            adds r3, #16
            mov  r5, sp
            adds r5, #0x60          ; &results[0]  (0x4C + 20 pushed)
            ldr  r0, [sp, #0x38]    ; run index (the stock retry counter)
            cmp  r0, #0
            bne  accum
            str  r0, [r4, #16]      ; first run: n[0..3] = 0 (acc is assigned, not added, when n == 0)
    accum:  mov  r6, r5
            movs r7, #4
    loop1:  ldrh r0, [r6]
            cbz  r0, next1          ; out of range in this run: not counted
            ldrb r1, [r3]
            cbz  r1, first
            ldr  r2, [r4]
            add  r0, r2
    first:  str  r0, [r4]
            adds r1, #1
            strb r1, [r3]
    next1:  adds r6, #2
            adds r4, #4
            adds r3, #1
            subs r7, #1
            bne  loop1
            ldr  r0, [sp, #0x38]
            adds r0, #1
            cmp  r0, #{AVG_RUNS}
            bhs  final
            pop  {{r4, r5, r6, r7, pc}}   ; back to the site: stock counter++ and re-run
    final:  subs r4, #16            ; back to acc[0] (loop1 advanced r4 by 16 and r3 by 4)
            subs r3, #4
            mov  r6, r5
            movs r7, #4
    loop2:  ldrb r1, [r3]
            cbz  r1, zero2
            ldr  r0, [r4]
            udiv r0, r0, r1         ; mean of the runs that read this pair
            b    st2
    zero2:  movs r0, #0
    st2:    strh r0, [r6]
            adds r6, #2
            adds r4, #4
            adds r3, #1
            subs r7, #1
            bne  loop2
            pop  {{r4, r5, r6, r7}}
            add  sp, #4             ; drop the saved lr: the sequence's own lr is in its frame
            b.w  0x08012B86         ; accept: store and display
    """, dict(img.syms, ACC=acc))
    if DEAD_BODY + len(code) > DEAD_BODY_END:
        raise PatchError(f"length-average: {len(code)} bytes do not fit the {DEAD_BODY_END - DEAD_BODY}-byte dead body")
    stock_body = img.read(DEAD_BODY, len(code)).hex()
    img.poke(DEAD_BODY, stock_body, code, f"average of {AVG_RUNS} CSD runs (in the dead length_convert body)")
    site = 0x08012AE0
    img.poke(site, "0998 0128 4fda", assemble(site, f"bl 0x{DEAD_BODY:08X}\n b 0x08012B0A"),
             "APP_LENG_Test_Sequence: accumulate each run; below AVG_RUNS runs re-run via the stock retry path")
    img.avg_acc = acc


# =====================================================================
# Group: power / battery robustness
# =====================================================================

@patch("batt-debounce", "Low-battery shutdown needs 3 consecutive low samples and cancels on recovery",
       risk="low", group="bugfix")
def p_batt_debounce(img):
    """
    Stock: battery_ui_update (every 2 s from the GUI task) arms a 30 s
    shutdown countdown the first time ONE unfiltered ADC sample reads below
    3150 mV.  battery_tick (1 Hz, SysTick context) then counts down and only
    a charger connection cancels it.  A load transient on a healthy pack can
    therefore start a shutdown that nothing but the charger can stop.

    Fix, two hooks:

      1. battery_ui_update 0x0800E6E2: the `movw/cmp/bge` against 3150 mV is
         replaced by a call that counts consecutive low samples in the RAM
         arena and only arms on the third (>= 6 s continuously low).  Any
         sample at or above 3150 mV resets the count.  The counter lives in
         non-initialised RAM; a garbage value at boot is cleared by the first
         healthy sample and can at worst reproduce stock behaviour once.

      2. battery_tick 0x0800DD5C: the `bl charger_state` that decides whether
         to cancel the countdown is redirected to a routine that returns
         true if the charger is connected OR the battery reads >= 3250 mV
         (100 mV hysteresis above the arming threshold).

    Both routines read the ADC through the stock battery_millivolts helper.
    """
    from lpm10a.thumb import assemble

    low_cnt = img.alloc_ram(4)

    check = img.emit_code(f"""
    batt_low_check:             ; in: r5 = mV   out: r0 = 1 -> arm countdown
            push {{r4, lr}}
            ldr  r4, =0x{low_cnt:08X}
            movw r0, #3150
            cmp  r5, r0
            bge  healthy
            ldrb r0, [r4]
            adds r0, #1
            cmp  r0, #3
            bls  keep
            movs r0, #3             ; clamp
    keep:   strb r0, [r4]
            cmp  r0, #3
            bne  no
            movs r0, #1
            pop  {{r4, pc}}
    healthy:
            movs r0, #0
            strb r0, [r4]
    no:     movs r0, #0
            pop  {{r4, pc}}
    """, why="low-battery debounce (3 consecutive samples)")

    cancel = img.emit_code("""
    batt_cancel_check:          ; out: r0 != 0 -> cancel shutdown countdown
            push {r4, lr}
            bl   charger_state
            mov  r4, r0
            bl   battery_millivolts
            movw r1, #3250
            cmp  r0, r1
            blt  out
            movs r4, #1
    out:    mov  r0, r4
            pop  {r4, pc}
    """, why="cancel low-battery countdown on charger OR recovery >= 3250 mV")

    site = 0x0800E6E2
    code = assemble(site, f"""
            bl   0x{check:08X}
            cbz  r0, 0x0800E766
            nop
    """)
    assert len(code) == 8
    img.poke(site, "40f64e40 8542 3dda", code, "arm only after 3 consecutive low samples")

    site = 0x0800DD5C
    code = assemble(site, f"bl 0x{cancel:08X}")
    img.poke(site, "02f0dcfd", code, "battery_tick: cancel on charger or recovery")


@patch("batt-gauge", "10-step battery gauge from a Li-ion discharge curve",
       risk="low", group="ux")
def p_batt_gauge(img):
    """
    Stock battery_level_percent maps the cell voltage to just four values
    (>4000 mV 100 %, >3800 80 %, >3600 50 %, else 20 %) and the gauge in
    battery_ui_update only draws for exactly those four values.

    New: a 10-point single-cell Li-ion table (open-circuit, light load)

        >=4150 100  >=4050 90  >=3950 80  >=3870 70  >=3800 60
        >=3750  50  >=3700 40  >=3650 30  >=3600 20  >=3450 10  else 0

    and the gauge draws pct/10 segments for any value.  The red colour is
    used at or below 20 %.  The existing two-sample debounce and the
    "only fall while discharging" rule in the stock code are kept.

    Sites:
      * battery_level_percent 0x080107CA: the table lookup (46 bytes) is
        replaced by `bl curve; b 0x080107FA` -- the remaining bytes of the
        old lookup are dead and untouched.
      * battery_ui_update 0x0800E778..0x0800E7B0 (56 bytes): the four-way
        switch is rewritten as `pct <= 20 -> red`, then the segment count is
        always computed, with the same charging-blink animation.
    """
    from lpm10a.thumb import assemble

    curve = img.emit_code("""
    batt_pct_curve:             ; in: r5 = mV   out: r4 = percent (0..100 step 10)
            push {lr}
            ldr  r1, =table
            movs r4, #100
    loop:   ldrh r0, [r1]
            cmp  r5, r0
            bge  done
            adds r1, #2
            subs r4, #10
            cmp  r4, #0
            bne  loop
    done:   pop  {pc}
            .align 4
    table:  .short 4150, 4050, 3950, 3870, 3800, 3750, 3700, 3650, 3600, 3450
    """, why="Li-ion 10-step percent curve")

    site = 0x080107CA
    code = assemble(site, f"""
            bl   0x{curve:08X}
            b    0x080107FA
    """)
    assert len(code) == 6
    img.poke(site, "3a48 7844 0088", code, "battery_level_percent -> curve")

    site = 0x0800E778
    body = assemble(site, """
            cmp  r0, #20
            bhi  bars
            movw r8, #0xF800        ; red at <= 20 %
    bars:   ldr  r0, =batt_level_pct
            ldrb r0, [r0]
            movs r1, #10
            udiv r0, r0, r1
            uxtb r6, r0
            cmp  r6, #0
            ble  end
            ldr  r0, =blink_phase
            ldrb r0, [r0]
            lsls r0, r0, #1
            subs r6, r6, r0         ; charging animation: 2 segments blink
            uxtb r6, r6
    end:    b    0x0800E7B2
    """, img.syms)
    assert len(body) <= 58 and len(body) % 2 == 0, len(body)
    body = body + b"\x00\xbf" * ((58 - len(body)) // 2)
    orig = ("1428 06d0 3228 09d0 5028 06d0 6428 13d1 02e0 4ff47848 00bf 00bf 00bf "
            "2448 0078 0a21 90fbf1f0 c6b2 002e 04dd 2148 0078 a6eb4000 c6b2 00bf 00bf")
    img.poke(site, orig, body, "gauge: red <= 20 %, segments = pct/10 for any value")


@patch("settings-leak", "Free the 204-byte buffer leaked by every settings save",
       risk="low", group="bugfix")
def p_settings_leak(img):
    """
    APP_Home_Cust_Info_Storage (0x0800FF74) allocates a 0xCC-byte staging
    buffer with pvPortMalloc, writes it to the settings flash page and
    returns through both its "failed" and "Success" paths without freeing
    it.  With a 48 KB heap that is a lock-up after a few hundred settings
    changes in one power cycle.

        0x08010086:  b 0x80100ec  ->  b 0x80100ea   (failed path joins the epilogue)
        0x080100EA:  nop; pop {r3-r7,pc}  ->  b.w cave

    and the cave epilogue does `mov r0, r5; bl vPortFree; pop {r3-r7,pc}`.
    r5 still holds the buffer pointer at both sites (verified: nothing in
    between writes r5).
    """
    from lpm10a.thumb import assemble

    epi = img.emit_code("""
    cust_info_storage_epilogue:
            mov  r0, r5
            bl   vPortFree
            pop  {r3, r4, r5, r6, r7, pc}
    """, why="APP_Home_Cust_Info_Storage: free staging buffer")

    img.poke(0x08010086, "31e0", bytes.fromhex("30e0"),
             "failed path -> shared epilogue")
    site = 0x080100EA
    code = assemble(site, f"b.w 0x{epi:08X}")
    img.poke(site, "00bf f8bd", code, "epilogue -> free + return")


@patch("font-pro", "Professional sans-serif fonts: ASCII 8x16 + 6x12 and all 171 Chinese glyphs",
       risk="low", group="ux")
def p_font(img):
    """
    Replaces the three glyph tables in place (same size, same layout, same
    order) with tables built by fonts.py:

      ascii16  0x08065D78  8x16   Ubuntu Sans Mono 600 @13 px   (was the thin serif "asc2_1608")
      ascii12  0x08065904  6x12   Ubuntu Sans Mono 600 @10 px
      cjk16    0x08066368  16x16  Droid Sans Fallback @16 px    (was SimSun-style Song)

    Every renderer reads the tables by index with fixed strides, so nothing
    else in the image has to change.  verify.py runs the firmware's own glyph
    drawers over the new tables and compares the pixels they produce with the
    bitmaps fonts.py intended, which proves the packing matches the renderer.

    Regenerate with `python fonts.py build` (Pillow + pymupdf); the .bin
    files under fonts_out/ are the shipped result so a build needs neither.
    """
    import fonts
    for name in ("ascii12", "ascii16", "cjk16"):
        addr, n, w, h, per = fonts.TABLES[name]
        new = open(os.path.join(HERE, "fonts_out", f"{name}.bin"), "rb").read()
        if len(new) != n * per:
            raise PatchError(f"{name}.bin is {len(new)} bytes, expected {n * per}")
        img.poke_blob(addr, STOCK_FONT_SHA[name], new, f"{name}: {n} glyphs {w}x{h}")


# sha256 of the three stock glyph tables (see `python fonts.py export`)
STOCK_FONT_SHA = {
    "ascii12": "f0540ce9a9f3f6452eec4ba4a2a253dfb36f69aeefa3ccc25ccd3c9bc5e3b9dc",
    "ascii16": "ce78d3d42ca1f7c16aa5bdab1f83dcc687782c098c5a152ddff782f7ecdfb0ca",
    "cjk16":   "cbc7bf1d7917efdc8a32f89285ac0a94acbcec4ba7b217a6fa4eca85908dacab",
}


# =====================================================================
# Group: identity
# =====================================================================

VERSION = "PN 1.2"          # shown as "Software:PN 1.2" in About; max 7 characters


@patch("version-string", f"Report the firmware version as {VERSION}",
       risk="safe", group="identity")
def p_version(img):
    """
    The About screen prints `Software:%s` with the string at 0x08011660 and
    the UART boot log prints a second copy at 0x08012E6C ("Current Firmware
    ...").  Both slots hold 7 characters.  Only these two user-visible
    strings change: the container's internal image name
    (APP_LPM-10A_V2.0.7_260610.bin) is what the bootloader checks before it
    accepts an update, so it is left exactly as stock.
    """
    if len(VERSION.encode("ascii")) > 7:
        raise PatchError("VERSION must be at most 7 characters")
    img.set_string(0x08011660, VERSION)      # About screen
    img.set_string(0x08012E6C, VERSION)      # boot log


REPO_URL = "github.com/patnawa/LPM-10A_PN_Custom"   # 36 characters, 6x12 font, 216 px


@patch("about-url", f"About screen shows {REPO_URL} instead of the vendor site",
       risk="safe", group="identity")
def p_about_url(img):
    """
    The About screen draws "http://www.fnirsi.cn" (a 20-character slot, 8x16
    font, 160 px wide at (40, 184)).  The project URL is 36 characters, too
    long for the slot and for the screen at 8 px per character, so the
    string lives in the cave and the line is drawn in the 6x12 font, 216 px
    wide, centred at x = 12 on the same row.  The About screen already draws
    other text at size 12 in exactly this way (0x08011556: size in r1, h =
    size, w in r2), so no new drawing behaviour is introduced.

    In place, 0x08011492..0x080114A2:
        adr r0,=url ; movs r1,#0x10   ->  bl about_str   (r0 = url, r1 = 12)
        movs r2,#0xA0 (w 160)         ->  movs r2,#0xD8  (w 216)
        movs r0,#0x28 (x 40)          ->  movs r0,#12
    The `mov r3, r1` between them makes h follow the font size as in stock.
    The vendor string is left in its slot, now unreferenced.
    """
    from lpm10a.thumb import assemble
    if len(REPO_URL) > 36:
        raise PatchError("REPO_URL must be at most 36 characters (240 px at 6 px per character)")
    about = img.emit_code(f"""
    about_str:                  ; -> r0 = url, r1 = font size 12
            ldr  r0, =url
            movs r1, #12
            bx   lr
    url:    .asciz "{REPO_URL}"
    """, why="About screen: project URL string")
    site = 0x08011492
    img.poke(site, "6aa0 1021", assemble(site, f"bl 0x{about:08X}"), "About: URL string and 12-px font")
    img.poke(0x08011498, "a022", bytes.fromhex("d822"), "About: URL width 216 px")
    img.poke(0x080114A0, "2820", bytes.fromhex("0c20"), "About: URL x = 12 (centred)")


@patch("english-only", "Remove Chinese from the language menu",
       risk="untested", default=False, group="english")
def p_english_only(img):
    """
    Blanks the "Chinese" entry in the Settings > Language list so the device
    presents as English-only.

    Left out of the default build: the language list is drawn from a small
    table and the selection logic still accepts index 1, so this needs a real
    device to confirm the list renders and scrolls correctly with one entry.
    """
    img.set_string(0x08010AC7, " ")


# =====================================================================
# Group: tuning
# =====================================================================

@patch("batt-grace", "Low-battery shutdown grace 30s -> 60s",
       risk="low", default=False, group="tuning")
def p_batt_grace(img):
    """
    battery_ui_update() arms the shutdown countdown with 30 seconds the first
    time a single ADC sample reads below 3150 mV.  The sample is unfiltered, so
    a load spike (PHY power-up, backlight, beeper) can start the countdown on a
    healthy pack.  Doubling the grace period gives the user time to react.

    Not a real fix -- the proper one is to average the ADC and cancel the
    countdown when the voltage recovers, which needs new code.
    """
    # 0x0800E6EA:  movs r0, #0x1e  ->  movs r0, #0x3c
    img.poke(0x0800E6EA, "1e20", bytes.fromhex("3c20"),
             "battery shutdown countdown 30 -> 60 seconds")
