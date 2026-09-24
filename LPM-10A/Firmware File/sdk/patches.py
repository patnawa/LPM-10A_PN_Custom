"""
Patch set for LPM-10A TX firmware; build inputs are SHA-256 pinned.

Each patch is a function taking the Image and doing its edits.  Patches are
grouped so a build can select exactly what it wants.

default=True marks the BASELINE: the frozen set verify.py models byte for byte
(archived as LPM-10A-TX_PN2.9.bin, never released on its own).  Everything
since PN 2.9 is a module registered at the end of this file and selected by a
profile in profiles.py; build.py emits the latest profile unless told otherwise.

risk levels
    safe      byte-for-byte reversible edit, verified by disassembly+emulation
    low       behavioural change, verified by emulation, semantics well understood;
              the profile record in profiles.py says what the owner's unit confirmed
    untested  needs a real device to confirm (or failed on one); never in a
              released profile
"""

import os
from functools import wraps

from lpm10a.image import PatchError

HERE = os.path.dirname(os.path.abspath(__file__))
REGISTRY = []


def patch(pid, title, risk, default=True, group="misc", requires=()):
    def deco(fn):
        @wraps(fn)
        def apply(img):
            applied = getattr(img, "applied_patches", set())
            missing = set(requires) - applied
            if missing:
                raise PatchError(f"{pid} requires: {', '.join(sorted(missing))}")
            if pid in applied:
                raise PatchError(f"{pid} is already applied")
            result = fn(img)
            img.applied_patches = applied | {pid}
            return result
        apply.pid, apply.title, apply.risk = pid, title, risk
        apply.default, apply.group, apply.requires = default, group, tuple(requires)
        REGISTRY.append(apply)
        return apply
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
        state == FLASH (6) and test_busy_flags[1] == 2 (blink running),

    and in that case also clears the idle counter, so the full timeout is
    available again once the session ends.  Everywhere else the state is
    returned unchanged and the behaviour is stock.

    Correction (PN 2.3): PN 1.0 .. 2.2 compared the state with 8, which is
    QC Test, not FLASH (the symbol table had the two swapped; the 1 ms tick
    posts the blink message only in state 6 and flags[1] == 2 only ever
    exists there), so those builds held Auto Off during a SCAN tone but not
    during a port blink, contrary to what their notes said.  The hardware
    checklist's "same for FLASH" line was never a real test of it.  Fixed
    here with the value taken from the symbol table; verify.py section 4b
    now tests state 6 and checks that state 8 is not held.

    (Mod 1's `autooff-keyreset` patch, which this replaces, added a second
    key-press reset that stock did not need.  Its description was wrong.)
    """
    from lpm10a.thumb import assemble
    from lpm10a import symbols as _S
    states = {v: k for k, v in _S.STATES.items()}
    assert states["SCAN"] == 5 and states["FLASH"] == 6

    hook = img.emit_code(f"""
    autooff_state:              ; -> r0 = sysState, or 0 while a tone / blink session is running
            push {{r4, lr}}
            movs r0, #0
            bl   get_sysState
            mov  r4, r0
            cmp  r0, #{states["SCAN"]}             ; SCAN
            bne  not_scan
            ldr  r1, =scan_state
            ldrb r1, [r1]           ; [0] = tone enabled
            cmp  r1, #0
            beq  out
            b    hold
    not_scan:
            cmp  r0, #{states["FLASH"]}             ; FLASH
            bne  out
            ldr  r1, =test_busy_flags
            ldrb r1, [r1, #1]       ; 2 = port blink running
            cmp  r1, #2
            bne  out
    hold:   movs r4, #0             ; report OFF: no idle counting this second
            ldr  r1, =auto_off_ctr
            strh r4, [r1]           ; and restart the timeout for afterwards
    out:    mov  r0, r4
            pop  {{r4, pc}}
    """, why="auto-off: hold while SCAN tone / FLASH blink is active")

    site = 0x0800F974
    img.poke(site, "0020 fff7f5fe", assemble(site, f"bl 0x{hook:08X}\n nop"),
             "home_1s_housekeeping: state via the hold check")


# =====================================================================
# Group: English / presentation
# =====================================================================

@patch("boot-english", "Factory defaults: English, no first-boot language picker",
       risk="low", default=False, group="english")
def p_boot_english(img):
    """
    Stock's factory defaults (0x0801958C) write language = 2 and
    first_boot_flag = 1, so a fresh unit shows the language picker with the
    second language (Chinese in stock, Thai in PN 2.0) preselected.  This
    option makes a fresh unit, and every Factory Reset, come up in English
    with no picker: the 36-byte block that writes bytes 0xA2..0xA8 is
    reordered so that 0xA5 = 1 (English) and 0xA8 = 0 (picker done); every
    other default (0xA2 = 2, 0xA3 = 0xA4 = 5, 0xA6 = 0xA7 = 0) is unchanged,
    and r0 / r1 hold the same values at 0x080195BC as in stock.

    PN 1.0 to 1.3 shipped an earlier version of this patch that only cleared
    the flag, which left a factory-reset unit in Chinese with no picker (the
    language byte was misread as 2 = English).  Units whose language was
    already chosen were never affected.  Not part of the PN 2.0 default
    build: the Thai build keeps the picker (English / ไทย).
    """
    site = 0x08019598
    stock_block = ("0220 81f8a500 81f8a200 0520 81f8a400 81f8a300 "
                   "0020 81f8a600 81f8a700 0120 81f8a800")
    new_block = bytes.fromhex("0220 81f8a200 0520 81f8a400 81f8a300 "
                              "0020 81f8a600 81f8a700 81f8a800 0120 81f8a500")
    img.poke(site, stock_block, new_block, "factory defaults: language 1 (English), first_boot_flag 0")


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
        # PoE screen: "Standard : Yes / No" (the value slots hold 7 characters; "Standard" does not fit)
        (0x080135E8, "Standard"),        # was "Standar Type"
        (0x08013A54, "Yes"),             # was "Standar"
        (0x08013D60, "No"),              # was "UnStandar"
        # Settings / factory reset confirmation
        (0x0801188F, " Factory Reset will"),      # was " Factory Reset should"
        (0x080118A8, "erase all your settings"),  # was "reset all of your modiy"
        # Misc wording
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

    A display value >= 65535 returns the reserved value 0xFFFF and prints
    OVR. This prevents centimetre overflow from wrapping to a tiny reading;
    it is a representation limit, not a claimed PHY measurement range.

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
      * the "Out of range" test (all four values == 0) is unchanged; note
        that a pair only 1..4 cm above the Zero rounds to 0 tenths and so
        counts as out of range, which is the right reading for it.
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
    done:   movw r1, #65535         ; reserve 0xFFFF for display overflow; never wrap
            cmp  r0, r1
            bls  fits
            mov  r0, r1
    fits:   uxth r0, r0
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
            movw r4, #65535
            cmp  r3, r4
            beq  overflow
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
    overflow:
            ldr  r1, =fmt_overflow
            b    plain
    fmt_overflow:
            .asciz "%s = OVR"
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
    img.length_conversion = conv
    img.length_formatter = fmt

    # unit labels, slot order 0/1/2
    img.set_string(0x08067ACC, "m")       # was "Inch"  (slot 0: now metres, the default)
    img.set_string(0x08067AD4, "cm")      # was "Cent"
    img.set_string(0x08067ADC, "ft")      # was "Meter" (slot 2: now feet)


@patch("nvp-calibration", "NVP and Zero calibration: UP/DOWN on the Length screen, long-press OK switches, both saved",
       risk="low", group="measure", requires=("length-decimal",))
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
    mine:   ldr  r0, =0x2000013C
            ldrb r0, [r0]
            cmp  r0, #7             ; a queued update may outlive the Length screen
            bne  stale
            bl   nvp_draw
            bl   length_result_draw
    stale:
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
    img.nvp = dict(draw=draw, key=key, gui=gui, tail=tail, zero_default=zdef)   # for later modules (length-reference)


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
       risk="low", group="measure", requires=("length-decimal",))
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
    if img.read(0x08019774, 4) != assemble(0x08019774, f"b.w 0x{img.length_conversion:08X}"):
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
    Stock: battery_ui_update (once a second, GUI message 4) arms a 30 s
    shutdown countdown the first time ONE unfiltered ADC sample reads below
    3150 mV.  battery_tick (1 Hz, SysTick context) then counts down and only
    a charger connection cancels it.  A load transient on a healthy pack can
    therefore start a shutdown that nothing but the charger can stop.

    Fix, two hooks:

      1. battery_ui_update 0x0800E6E2: the `movw/cmp/bge` against 3150 mV is
         replaced by a call that counts consecutive low samples in the RAM
         arena and only arms on the third (>= 3 s continuously low).  Any
         sample at or above 3150 mV resets the count.  The counter lives in
         non-initialised RAM, explicitly cleared at main entry before any
         task or interrupt can sample it.

      2. battery_tick 0x0800DD5C: the `bl charger_state` that decides whether
         to cancel the countdown is redirected to a routine that returns
         true if the charger is connected OR the battery reads >= 3250 mV
         (100 mV hysteresis above the arming threshold). PN 2.5 also clears
         the low-sample counter on cancellation: the UI skips the arming
         hook during shutdown/charging, so previously the next low sample
         could re-arm immediately using the previous episode's count.

    Both routines read the ADC through the stock battery_millivolts helper.
    """
    from lpm10a.thumb import assemble

    low_cnt = img.alloc_ram(4)

    init = img.emit_code("""
    batt_init:                 ; replay main's first two instructions, clear only our counter
            ldr  r1, =LOW_CNT
            movs r4, #0
            str  r4, [r1]
            ldr  r0, =0x0800A000
            bx   lr
    """, extra_syms={"LOW_CNT": low_cnt}, why="initialise battery debounce before tasks start")
    img.poke(0x0801BBAC, "0024 2748", assemble(0x0801BBAC, f"bl 0x{init:08X}"),
             "main entry: initialise debounce and replay r4=0, r0=vector base")
    img.batt_init, img.batt_low_cnt = init, low_cnt

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
            blt  reset_if_cancelled
            movs r4, #1
    reset_if_cancelled:
            cmp  r4, #0
            beq  out
            ldr  r1, =LOW_CNT
            movs r0, #0
            strb r0, [r1]           ; the next low episode needs three fresh samples
    out:    mov  r0, r4
            pop  {r4, pc}
    """, extra_syms={"LOW_CNT": low_cnt},
        why="cancel low-battery countdown on charger OR recovery >= 3250 mV; reset debounce")

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

VERSION = "PN 2.9"          # the BASELINE's version; each profile module since PN 2.10 writes its own (profiles.py)


@patch("version-string", f"Report the firmware version as {VERSION} (a profile module overrides it with its own)",
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


@patch("scan-labels", "SCAN screen: the two modes are labelled 'Digital' and '825 Hz' instead of 'Noiseless' / 'Normal'",
       risk="safe", group="identity")
def p_scan_labels(img):
    """
    The SCAN (tone) screen offers two transmit modes.  Stock calls them
    "Noiseless" and "Normal", which says nothing about what goes down the
    wire.  What the code does (TIM2 at 9 901 Hz, verify.py §4 and the tone
    analysis in docs/RX-AUDIT.md):

      mode 1 "Noiseless": the 454 kHz carrier keyed in the 16-slot pattern
             0xB6B6, 50 ticks = 5.05 ms per slot: the digitally coded
             signal the LPM-10RX probe decodes in its digital mode.
      mode 2 "Normal":    the carrier keyed on/off every 6 ticks, i.e. a
             continuous 825 Hz square-wave tone (9 901 / 12) for any
             analogue probe.  (The 100 ms "phase" flag in that routine
             toggles a byte that both branches treat identically.)

    So the labels become "Digital" and "825 Hz".  Both are English-only
    strings drawn by gui_blit; the Chinese labels are untouched.  "825 Hz"
    is six characters like "Normal", so its blit is unchanged; "Digital" is
    seven, so its blit moves from x 84 / w 72 to x 92 / w 56 to stay
    centred on 120 like stock.
    """
    img.set_string(0x080142B4, "Digital")      # was "Noiseless" (PN 1.0..1.2 said "Silent")
    img.set_string(0x080142C8, "825 Hz")       # was "Normal"
    img.poke(0x080141E4, "4822", bytes.fromhex("3822"), "SCAN mode 1 label width 72 -> 56")
    img.poke(0x080141EC, "5420", bytes.fromhex("5c20"), "SCAN mode 1 label x 84 -> 92")


# =====================================================================
# Group: SCAN timing
# =====================================================================

@patch("scan-timing", "SCAN: exact digital wrap, no timer-path logging, reliable resume",
       risk="low", group="scan")
def p_scan_timing(img):
    """Keep the stock wire protocol and hardware configuration.

    Digital divides its tick counter by 50 to choose a bit of 0xB6B6.
    At bit 16 stock clears the counter but uses the stale bit index, so
    the first high bit loses one tick on every wrap. Clear both together.

    Two debug-log blocks run inside TIM2: default-mode initialization and
    the 825 Hz generator's 1000-tick phase rollover. Skip their critical
    sections, formatting and task-context queue send, preserving the state
    updates before/after them. Task-context key-handler logs are retained.

    Back forces the carrier off without updating the gate's cached output.
    Invalidate that cache BEFORE enabling, so the first resumed timer tick
    always drives the requested level, even if the saved bit was high.
    Timer preemption between these stores is safe: on resume the old enabled
    byte is zero; on pause any extra tick precedes the existing forced off.
    No new RAM, timer changes, receiver protocol or carrier changes.
    """
    from lpm10a.thumb import assemble
    img.poke(0x08014310, "0020", assemble(0x08014310, "movs r4, #0"),
             "SCAN digital wrap: clear the bit index")
    img.poke(0x08014314, "0860", assemble(0x08014314, "str r4, [r1]"),
             "SCAN digital wrap: clear the counter with the index")
    for site, expected, target in ((0x0801436C, "08f0a2f9", 0x080143D4),
                                    (0x0801469E, "08f009f8", 0x0801470E)):
        img.poke(site, expected, assemble(site, f"b 0x{target:08X}\nnop"),
                 "SCAN timer path: bypass debug logging, retain state updates")
    hook = img.emit_code("""
        ldr  r0, =0x200000D0
        movs r1, #255
        strb r1, [r0, #12]
        strb r4, [r0]
        bx   lr
    """, why="SCAN enable: invalidate the cached carrier gate before enabling")
    img.poke(0x0801449C, "28480470", assemble(0x0801449C, f"bl 0x{hook:08X}"),
             "SCAN enable setter: force the first resumed tick to drive the carrier")


# =====================================================================
# Group: thai
# =====================================================================

@patch("thai-ui", "Thai user interface: the second language becomes Thai (Sarabun cells, proportional drawers)",
       risk="low", group="thai", requires=("font-pro", "length-decimal"))
def p_thai(img):
    """
    Language 2 of the tester becomes Thai.  English (language 1) is untouched:
    every English string, position and code path is exactly PN 1.3.

    What the stock image has (verified inventory in sdk/thai/sites.py):
      * 171 Chinese glyphs, 16x16 one-bit cells at 0x08066368, drawn by
        0x08017550(x, y, idx, transparent);
      * two string drawers with fixed 16-px advance: cjk_text 0x080176AC
        (index bytes, count != 0 centres by 8*count) and mixed_text 0x080173EC
        (u16 units, 0x01xx = glyph, 0x20..0x7E = ASCII, count != 0 centres by
        4*count);
      * 64 Chinese string slots (3..20 bytes) reached by adr, by ldm / ldr /
        memcpy stack copies of 4..28 bytes and by strided tables (3, 5 and 14
        bytes), all listed in sdk/thai/sites.py.

    What this patch does:
      1. Glyph table: the 171 cells become the Thai cell set built by
         `python -m thai.cells` (fonts_out/thai16.bin: Sarabun SemiBold 13 px,
         one cell per consonant cluster, Latin letters and digits in the same
         face, two whole-word cells for YES / NO), 118 cells today.  The 53
         unused slots (1696 bytes) are the flash this patch lives in.
      2. Drawers: cjk_text and mixed_text jump to Thai versions with the same
         signatures (thai/drawers.py).  Cells advance by their own width
         (WTAB); `count != 0` still means "centre on x" but by the measured
         width, so every call site keeps its anchor and no coordinate changes.
      3. Strings: no Chinese slot is rewritten in place.  Each gets a REDIRECT
         stub -- cjk [cell, 0xAC, idx, 0xFF] (3 bytes in the unit table),
         mixed [0x0100, 0x01AC, idx, 0x0000] -- that the drawers resolve
         through RELOC[idx] to the Thai text in the freed glyph area.  The
         stubs fit the smallest stack copy any caller makes, so adr, ldm,
         memcpy and strided-table references stay as they are.  The first
         stub byte is a real cell so stock's strlen helpers (which stop only
         at 0xFF) still return a non-zero count where stock centres.
      4. YES / NO in the factory-reset dialog are single-glyph draws
         (movs r2,#idx): the index becomes the whole-word cell.
      5. The About page's three Chinese label lines start at x 57 instead of
         71 so the wider Thai labels clear the version column.
      6. gui_blit 0x080174E8 gets a hook (thai/drawers.py BLIT_HOOK) that, only
         while the language is Thai, replaces the messages stock has in
         English alone (wording.py ASCII_TH: "Result error!!", "Test
         timeout!!", "Error!!", "OFF" in PN 2.0, the PoE screen's
         "Detecting..." / "No PoE" since PN 2.3) and moves the "..." animation
         from x 68 to DOTS_X, past the wider Thai "Testing".  Any other string
         falls through to gui_blit unchanged.
      7. The first-boot language picker is kept (boot-english is not part of
         this build): a fresh unit or a factory reset shows English / ไทย.
      8. The boot log's "Chinese" label becomes "Thai".

    Verification (verify.py section 19): the built image is run through the
    real GUI dispatcher for every screen and compared pixel for pixel with
    the mock-up model (the PN 1.3 image with the Chinese drawers intercepted
    and the Thai wording drawn by the model), in Thai and in English.
    """
    import hashlib
    import struct
    from lpm10a.thumb import assemble
    from thai.cells import Table, REDIRECT
    from thai.wording import TH, ASCII_TH, DOTS, DOTS_X
    from thai import sites as S_
    from thai import drawers as D_
    from cjk_chars import CJK as _CJK
    CJK = list(_CJK)
    CJK[0x69] = "\u4e8e"                                   # 关于: index 0x69 is 于

    fonts_out = os.path.join(HERE, "fonts_out")
    table = Table.shipped(fonts_out)
    ncell = len(table.order)
    droid = hashlib.sha256(open(os.path.join(fonts_out, "cjk16.bin"), "rb").read()).hexdigest()

    # 1. the cell table replaces font-pro's Chinese table
    img.poke_blob(S_.CJK_TABLE, droid, table.blob(), f"thai16: {ncell} Thai cells, {S_.CJK_SLOTS - ncell} slots free")
    img.add_region("thai", S_.CJK_TABLE + 32 * ncell, S_.CJK_TABLE + 32 * S_.CJK_SLOTS)

    # 2. width table
    wtab = img.write_in("thai", bytes(table.widths), f"cell advance widths ({ncell})")

    # 3. the Thai strings (deduplicated) and the RELOC pointer table
    def thai_of(zh):
        v = TH[zh]
        return v["text"] if isinstance(v, dict) else v

    texts = []
    for addr, kind, zh, slot, copy in S_.CJK_STRINGS:
        t = thai_of(zh)
        if t not in texts:
            texts.append(t)
    for v in ASCII_TH.values():
        if v["text"] not in texts:
            texts.append(v["text"])
    reloc = img.alloc_in("thai", 4 * len(texts))
    where = {}
    for t in texts:
        where[t] = img.write_in("thai", table.encode_cjk(t), f"Thai string {t!r}", align=1)
    ptrs = b"".join(struct.pack("<I", where[t]) for t in texts)
    o = img.f(reloc)
    old = bytes(img.data[o:o + len(ptrs)])
    img.data[o:o + len(ptrs)] = ptrs
    img.log.append((reloc, old, ptrs, f"RELOC: {len(texts)} string pointers", "code"))

    def decode_cjk(addr):
        out = ""
        for b in img.read(addr, 40):
            if b >= 0xAB:
                break
            out += CJK[b]
        return out

    def decode_mixed(addr):
        out = ""
        raw = img.read(addr, 80)
        for i in range(40):
            v = struct.unpack_from("<H", raw, 2 * i)[0]
            if v > 0xFF:
                if (v & 0xFF) >= 0xAB:
                    break
                out += CJK[v & 0xFF]
            elif 0x20 <= v <= 0x7E:
                out += chr(v)
            else:
                break
        return out

    for addr, kind, zh, slot, copy in S_.CJK_STRINGS:
        got = decode_cjk(addr) if kind == "cjk" else decode_mixed(addr)
        if got != zh:
            raise PatchError(f"@0x{addr:08X}: expected the Chinese string {zh!r}, found {got!r}")
        idx = texts.index(thai_of(zh))
        if kind == "cjk":
            stub = bytes([0, REDIRECT, idx, 0xFF])[:min(slot, 4)]
        else:
            stub = struct.pack("<HHHH", 0x0100, 0x0100 | REDIRECT, idx, 0)
        if len(stub) > slot or (copy is not None and len(stub) > copy):
            raise PatchError(f"@0x{addr:08X}: stub does not fit slot {slot} / copy {copy}")
        old = img.read(addr, slot)                   # the whole slot is declared (the rest of it is kept)
        img.poke(addr, old.hex(), stub + old[len(stub):], f"{zh} -> {thai_of(zh)} (stub -> RELOC[{idx}])")

    # 4. YES / NO whole-word cells
    for site, old_hex, zh in S_.GLYPH_SITES:
        cell = table.index[thai_of(zh)]
        img.poke(site, old_hex, bytes([cell, 0x22]), f"glyph {zh} -> word cell {thai_of(zh)!r} (#{cell})")

    # 5. About labels 14 px to the left
    for site, old_hex in S_.ABOUT_LABEL_X:
        img.poke(site, old_hex, bytes.fromhex("3920"), "About label x 71 -> 57 (Thai branch)")

    # 6. the drawers
    syms = dict(GLYPH=S_.GLYPH | 1, ASCII_GLYPH=S_.ASCII_GLYPH | 1, WTAB=wtab, RELOC=reloc)
    cjk = img.emit_code_in("thai", D_.CJK_TEXT, syms, why="thai_cjk_text: proportional index-byte drawer")
    syms["THAI_CJK_TEXT"] = cjk | 1
    mixed = img.emit_code_in("thai", D_.MIXED_TEXT, syms, why="thai_mixed_text: proportional u16 drawer")
    img.poke(S_.CJK_TEXT, "f0b5 0546", assemble(S_.CJK_TEXT, f"b.w 0x{cjk:08X}"), "cjk_text -> thai_cjk_text")
    img.poke(S_.MIXED_TEXT, "f8b5 0546", assemble(S_.MIXED_TEXT, f"b.w 0x{mixed:08X}"), "mixed_text -> thai_mixed_text")

    # 7. the gui_blit hook and its table
    entries = []
    for en, spec in ASCII_TH.items():
        flags = {"centre": D_.F_CENTRE, "left": 0, "x": D_.F_X}[spec["layout"]]
        if spec.get("clear"):
            flags |= D_.F_CLEAR
        entries.append((en, where[spec["text"]], flags, spec.get("x", 0)))
    for d in DOTS:
        entries.append((d, 0, D_.F_X | D_.F_ASCII | D_.F_AT68, DOTS_X))
    asc = {}
    for en, thai_ptr, flags, x in entries:
        if en not in asc:
            asc[en] = img.write_in("thai", en.encode("ascii") + b"\0", f"hook key {en!r}", align=1)
    tab = b"".join(struct.pack("<IIHH", asc[en], thai_ptr, flags, x) for en, thai_ptr, flags, x in entries) + b"\0" * 4
    hooktab = img.write_in("thai", tab, f"HOOKTAB: {len(entries)} entries")
    syms.update(LANG_IS=S_.LANG_IS | 1, DRAW_SHAPE=S_.DRAW_SHAPE | 1, GUI_BLIT_CONT=(S_.GUI_BLIT + 4) | 1,
                HOOKTAB=hooktab, BG_COLOUR=S_.BG_COLOUR)
    hook = img.emit_code_in("thai", D_.BLIT_HOOK, syms, why="blit_hook: Thai text for English-only messages")
    img.poke(S_.GUI_BLIT, "2de9f847", assemble(S_.GUI_BLIT, f"b.w 0x{hook:08X}"), "gui_blit -> blit_hook")

    # 8. the boot log names the language
    img.set_string(0x08010AC8, "Thai")
    img.thai = dict(table=table, texts=texts, where=where, reloc=reloc, wtab=wtab, hooktab=hooktab,
                    cjk=cjk, mixed=mixed, hook=hook)


@patch("cable-back", "Cable Test: Back returns to the Switch / Far end selector instead of leaving the screen",
       risk="low", group="ux")
def p_cable_back(img):
    """
    The Cable Test screen has two steps: the Switch / Far end selector, then
    the armed wiremap layout (and, after OK, the result).  Stock's Back key
    (action 7) leaves the screen from either step: the per-state table of the
    back handler (0x0800D36C, tbb at 0x0800D37E) sends CABLE_TEST straight to
    APP_HOME_set_sysState(2).  Settings, by contrast, backs out of its About
    sub-page first.  Reported on hardware (2026-09-18): "Back in Cable Test
    goes to Home instead of the Switch / Far end choice".

    The CABLE_TEST entry of that table (byte 0, offset 4) already lands on
    three spare nops at 0x0800D386; the first two become `b.w cable_back`, and
    the QC_TEST entry (byte 4), which pointed at the second nop, moves to the
    third (offset 5 -> 6) so it still reaches the stock Home path.

    cable_back: if the layout flag (bit 4 of 0x20000010) is set, re-enter the
    screen through the stock entry function 0x0800C300 (sets sysState 4 again,
    which redraws the frame, clears the layout and retry flags and posts the
    selector, msg 0x0F); otherwise Home as before.  Every other state keeps
    its stock target.
    """
    from lpm10a.thumb import assemble
    code = img.emit_code_anywhere("""
    cable_back:                 ; Back (action 7) in CABLE_TEST
            ldr  r0, =0x20000010
            ldrb r0, [r0]
            lsrs r0, r0, #4         ; layout shown?
            beq  cb_home
            bl   0x0800C301         ; cable_test_enter: frame, flags cleared, mode selector
            b.w  0x0800D3AA
    cb_home:
            movs r0, #2
            bl   0x0800F77D         ; APP_HOME_set_sysState(HOME)
            b.w  0x0800D3AA
    """, why="Back in Cable Test: selector if the layout is shown, else Home")
    img.poke(0x0800D37E, "040b0f07050e0612", bytes.fromhex("040b0f07060e0612"),
             "back handler table: QC_TEST entry moves from the 2nd to the 3rd spare nop")
    img.poke(0x0800D386, "00bf00bf", assemble(0x0800D386, f"b.w 0x{code:08X}"),
             "CABLE_TEST back -> cable_back")


@patch("cable-error-visible", "Cable Test: 'Result error!!' is drawn above the Test Retry button instead of under it",
       risk="low", group="ux")
def p_cable_error(img):
    """
    When a wire-map test finds a wire it cannot classify, both result drawers
    (switch 0x0800CB68, far end 0x0800C4E0) paint "Result error!!" in red at
    (64, 284) and then post GUI message 0x12, which redraws the Test Retry
    button (70, 280, 100 x 26) over it: on stock only a red "R" and "!" peek
    out at the button's sides.  In Thai the whole message would be hidden.

    The 46 px between the wire-map panel (bottom edge y 270) and the frame
    (y 316) hold a 16 px line and the 26 px button with room to spare:
      * message y: `adds r0,#0xE5` -> `#0xD8` at both sites (55 + 216 = 271,
        rows 271..286),
      * button record 0x0801E320: y 280 -> 289 (rows 289..315),
      * button label y: `movw r1,#0x11D` (285) -> `#0x126` (294) at the two
        label sites of the button drawer 0x0800C424 (Thai and English).
    Every other Cable Test element is unchanged; the Test Start button of the
    armed screen moves down 9 px with its record.
    """
    for site in (0x0800CAF2, 0x0800CE4E):
        img.poke(site, "e530", bytes.fromhex("d830"), "'Result error!!' y 284 -> 271")
    img.poke(0x0801E322, "1801", bytes.fromhex("2101"), "Cable Test button record: y 280 -> 289")
    for site in (0x0800C484, 0x0800C496):
        img.poke(site, "40f21d11", bytes.fromhex("40f22611"), "Cable Test button label y 285 -> 294")


@patch("length-blind-text", "Length: a pair the PHY could not time shows '< 2 m' instead of '0.0 m'",
       risk="low", group="measure", requires=("length-decimal",))
def p_length_blind(img):
    """
    The PHY's cable diagnostic cannot time an echo from inside its blind zone
    (about 2 m): stock zeroes such a pair, and the result rows then print
    "1-2 = 0.0 m" next to the pairs that did read, which looks like a fault
    or a zero-length pair.  Seen on hardware with a 1 m cable: three pairs
    blind, pair 4-5 a raw 2.2 m (1.7 m after Zero and NVP).

    A zero now prints as "1-2 = < 2" (m), "< 200" (cm) or "< 7" (ft); the
    stock code still appends the unit label after the text, so the row reads
    "1-2 = < 2 m" / "1-2 = < 2 เมตร".  All four pairs zero still gives "Out of
    range" as before (that test runs before any row is printed). A zero can
    also mean no usable reading: the text must not be treated as proof of
    an open pair or an independently validated fault distance.

    Implementation: length-decimal's cave formatter (called from the one
    sprintf site 0x08019B12) is replaced by a copy with the zero case; the new
    copy lives in the Thai patch's region (the cave is full), the old one is
    left unreferenced.  The wrapper still returns sprintf's length, which the
    stock code uses to place the unit label.

    PN 2.7: OVR takes precedence over all other text. If length-average is
    selected, counts 1..AVG_RUNS-1 replace '=' with '~' to mark partial
    acquisition. Counts are read only for their pair index (r4 at the call
    site); no extra persistent RAM or changes to measurement means.
    PN 2.8: a calibrated zero uses blind text before examining those counts.
    """
    from lpm10a.thumb import assemble
    syms = dict(sprintf=0x0800A38C | 1, leng_unit_idx=0x200002C0)
    # r4 at the real call site is the pair index. A partial mean remains
    # useful, but must not look like four successful diagnostic runs.
    partial = ""
    if hasattr(img, "avg_acc"):
        syms["COUNTS"] = img.avg_acc + 16
        partial = f"""
            cmp  r3, #0
            beq  complete          ; blind text wins over a partial numeric marker
            ldr  r5, =COUNTS
            add  r5, r4
            ldrb r5, [r5]
            cmp  r5, #0
            beq  complete
            cmp  r5, #{AVG_RUNS}
            bhs  complete
            ldr  r1, =fmt_partial_cm
            ldr  r5, =leng_unit_idx
            ldrb r5, [r5]
            cmp  r5, #1
            beq  plain
            movs r4, #10
            udiv r5, r3, r4
            mls  r4, r5, r4, r3
            str  r4, [sp]
            mov  r3, r5
            ldr  r1, =fmt_partial_dec
            b    plain
        complete:
        """
    fmt = img.emit_code_anywhere("""
    length_sprintf2:            ; r0=buf r1="%s = %d" r2=name r3=value (tenths for m/ft, cm for cm)
            push {r4, r5, lr}
            sub  sp, #4
            movw r5, #65535
            cmp  r3, r5
            beq  overflow
    """ + partial + """
            ldr  r4, =leng_unit_idx
            ldrb r4, [r4]
            cbz  r3, blind
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
    blind:                      ; the echo came back inside the PHY's blind zone
            movs r3, #2             ; m
            cbz  r4, bfmt
            movs r3, #200           ; cm
            cmp  r4, #1
            beq  bfmt
            movs r3, #7             ; ft
    bfmt:   ldr  r1, =fmt_blind
            b    plain
    overflow:
            ldr  r1, =fmt_overflow
            b    plain
    fmt_overflow:
            .asciz "%s = OVR"
    fmt_partial_cm:
            .asciz "%s ~ %d"
    fmt_partial_dec:
            .asciz "%s ~ %d.%d"
    fmt_dec:
            .asciz "%s = %d.%d"
    fmt_blind:
            .asciz "%s = < %d"
    """, extra_syms=syms, why="length_result_draw: decimal formatter with the blind-zone text")
    site = 0x08019B12
    old = img.read(site, 4)
    if old != assemble(site, f"bl 0x{img.length_formatter:08X}"):
        raise PatchError("length-blind-text needs length-decimal's bl at 0x08019B12")
    img.poke(site, old.hex(), assemble(site, f"bl 0x{fmt:08X}"), "sprintf site -> formatter with '< 2 m'")


# =====================================================================
# Group: PoE
# =====================================================================

POE_LIVE_TICKS = 50            # 10 ms PoE task ticks between live voltage refreshes (0.5 s)
POE_VAL_X, POE_ROW0_Y = 117, 220   # the Standard row's value cell (layout record 0x0801E71E: x 7 + 110, y 55 + 5 + 20*8)
POE_STRINGS = {"none": "No PoE", "detect": "Detecting..."}


@patch("poe-screen", "PoE: live voltage every 0.5 s, 'Detecting...' / 'No PoE' status, timeout re-armed on every entry",
       risk="low", group="poe")
def p_poe_screen(img):
    """
    What stock does on the POE screen (disassembly of the PoE task 0x08013F64,
    its state machine 0x08019F00 and the two GUI handlers 0x08013270 / 0x08013620):

      * The PoE task samples the four pair voltages every 10 ms (tick hook
        0x0801BD10), keeps the spread in poe_mv (0x200000C0, mV) and, the first
        time it exceeds 40 V, classifies the supply and posts GUI message 0x14.
      * The 0x14 handler draws "XX.YV" on the wires of the powered pair (0.1 V,
        from poe_mv), "0.0V" on its return pair, and the four result rows.  It
        is posted once per detection: the voltage on screen is the sample
        current a tick or two after the first one above 40 V, i.e. taken on
        the rising edge, and it is not refreshed while the screen is shown
        (only leaving and re-entering redraws it, from whatever the sample is
        then).  The handler loads poe_mv once per wire, so the two wires of a
        pair can even disagree when a sample lands between the two draws.
      * With no supply, a 350-tick (3.5 s) timeout posts 0x14 with nothing to
        show: the handler returns before the rows and only the LED turns blue.
        The counter (0x200000C2) is parked at 0xFFFF after that and is only
        re-armed when a supply is seen and removed, so on every later visit the
        screen simply stays blank -- which is what the tester shows most of the
        time, since the counter runs out 3.5 s after boot.

    What this patch changes (four 4..6 byte hooks; the code lives in the cave,
    which grows the container by one 4 KB page for it):

      1. Live voltage.  The task's `bl poe_state_machine` (0x08013ECC) goes
         through poe_tick, which after the stock state machine counts ticks
         while the tester is on the POE screen with a supply present (span
         != 0) and every POE_LIVE_TICKS (0.5 s) sets a "partial" flag and
         posts 0x14.  A hook at 0x0801395C -- between the eight voltages and
         the result rows of the 0x14 handler -- returns early when the flag is
         set, so a live refresh redraws the voltage column only (cleared and
         redrawn exactly as stock does it) and the rows do not blink.  A full
         0x14 (flag clear) draws everything as before.  The moment the supply
         goes away (span back to 0) one full 0x14 is posted, so the column
         clears and "No PoE" appears at once instead of the last reading
         sitting there for 3.5 s.  While the low-battery countdown box is up
         the stock GUI task discards every queued message but the battery
         tick (0x0800F474), so the refresh cannot paint over it; the flag it
         may leave set is cleared by entry_hook when the screen is redrawn.
         Off the POE screen poe_tick keeps the cell zero (the arena is not
         zero-initialised), so it is defined before the screen can be entered.
      1b. Consistent values.  The 0x14 handler's first instruction (0x08013632)
         goes through latch_hook, which copies the PoE task's sample block
         (poe_adc_ch[4], max, min, poe_mv: 0x200000B4..0x200000C1) into a
         RAM-arena latch, and the handler's three literal-pool words that
         pointed at that block (0x08013A38 poe_mv, 0x08013A44 poe_adc_ch,
         0x08013A48 min) point at the latch, so every wire of one redraw
         shows the same sample whatever the PoE task does meanwhile.
      2. Status text.  The screen-entry handler (0x0801327E, bl poe_screen_draw)
         goes through entry_hook: it zeroes the live counter and flag, re-arms
         the timeout counter, draws the screen and, when no span is known yet,
         writes "Detecting..." in the Standard row.  The 0x14 handler's switch
         on the standard (0x080139AC) goes through std_check: standard 0 (the
         timeout) now draws "No PoE" there instead of returning silently; the
         handler cleared the rows just before, as stock does.  Both strings
         are English-only in stock terms and get their Thai text through the
         thai-ui gui_blit hook (wording.py ASCII_TH): "กำลังตรวจหา..." /
         "ไม่พบ PoE".
      3. Because the timeout is re-armed on entry, "No PoE" appears 3.5 s
         after entering the screen without a supply, every time.

    Nothing about the measurement, the classification or the stock "unstable
    supply" check changes; the latter can never trigger (see FORMULA-AUDIT.md)
    and is left as documented.  Verified in verify.py section 21.
    """
    from lpm10a.thumb import assemble
    live = img.alloc_ram(4)                       # [0] tick counter, [1] partial-redraw flag, [2] last span seen
    latch = img.alloc_ram(16)                     # copy of 0x200000B4..0x200000C3: adc[4], max, min, mv (+2 spare)
    syms = dict(
        POE_SM=0x08019F00 | 1, GET_STATE=0x0800F764 | 1, GUI_MSG_SEND=0x0800E428 | 1,
        GUI_BLIT=0x080174E8 | 1, POE_SCREEN_DRAW=0x08013334 | 1,
        POE_RESULT_EXIT=0x0801362E, POE_RESULT_ROWS=0x08013960, POE_STD_CONT=0x080139B2,
        POE_RESULT_CONT=0x08013636, POE_SAMPLES=0x200000B4, LATCH=latch,
        POE_SPAN=0x20000C60, POE_TIMEOUT_CNT=0x200000C2, LIVE=live,
        LIVE_TICKS=POE_LIVE_TICKS, VAL_X=POE_VAL_X, ROW0_Y=POE_ROW0_Y,
    )
    strs = img.emit_code(f'''
    s_none:   .asciz "{POE_STRINGS["none"]}"
    s_detect: .asciz "{POE_STRINGS["detect"]}"
    ''', why="poe-screen: the two status strings")
    syms["S_NONE"] = strs
    syms["S_DETECT"] = strs + len(POE_STRINGS["none"]) + 1

    tick = img.emit_code("""
    poe_tick:                   ; the task's msg 1: stock state machine, then the live refresh
            push {r4, lr}
            bl   POE_SM
            movs r0, #0
            bl   GET_STATE
            ldr  r4, =LIVE
            cmp  r0, #10            ; POE screen?
            beq  pt_on
            movs r0, #0
            str  r0, [r4]           ; elsewhere: keep the cell zero, so it is defined before any entry
            b    pt_done
    pt_on:
            ldr  r0, =POE_SPAN
            ldrb r0, [r0]           ; span now (0 = no supply classified)
            ldrb r1, [r4, #2]       ; span at the previous tick
            strb r0, [r4, #2]
            cmp  r0, #0
            bne  pt_live
            cmp  r1, #0
            beq  pt_done            ; still nothing
            movs r0, #0             ; the supply went away: one full redraw now ("No PoE")
            strb r0, [r4]
            strb r0, [r4, #1]
            b    pt_post
    pt_live:
            ldrb r0, [r4]
            adds r0, #1
            strb r0, [r4]
            cmp  r0, #LIVE_TICKS
            blo  pt_done
            movs r0, #0
            strb r0, [r4]
            movs r0, #1
            strb r0, [r4, #1]       ; partial: voltages only
    pt_post:
            movs r2, #0
            movs r1, #0
            movs r0, #0x14
            bl   GUI_MSG_SEND
    pt_done:
            pop  {r4, pc}
    """, extra_syms=syms, why="poe_tick: stock state machine + live refresh every 0.5 s")

    latch_hook = img.emit_code("""
    latch_hook:                 ; 0x08013632: the 0x14 handler starts drawing
            mrs  r3, primask
            cpsid i
            ldr  r0, =POE_SAMPLES
            ldr  r1, =LATCH
            ldr  r2, [r0]
            str  r2, [r1]           ; adc[0..1]
            ldr  r2, [r0, #4]
            str  r2, [r1, #4]       ; adc[2..3]
            ldr  r2, [r0, #8]
            str  r2, [r1, #8]       ; max, min
            ldr  r2, [r0, #12]
            str  r2, [r1, #12]      ; mv (+ the u16 after it)
            msr  primask, r3        ; preserve the caller's interrupt mask
            movw r0, #0x2105        ; the displaced instruction
            b.w  POE_RESULT_CONT
    """, extra_syms=syms, why="latch_hook: one sample for the whole redraw")

    live_check = img.emit_code("""
    live_check:                 ; 0x0801395C: the voltages are drawn, the rows come next
            ldr  r0, =LIVE
            ldrb r1, [r0, #1]
            cmp  r1, #0
            beq  lc_full
            movs r1, #0
            strb r1, [r0, #1]
            b.w  POE_RESULT_EXIT    ; pop.w {r2-r8, pc}
    lc_full:
            movw r0, #0x2105        ; the displaced instruction
            b.w  POE_RESULT_ROWS
    """, extra_syms=syms, why="live_check: a live refresh stops before the result rows")

    std_check = img.emit_code("""
    std_check:                  ; 0x080139AC: r0 = standard, r4 = 8 (row 0)
            cmp  r0, #0
            beq  sc_none
            cmp  r0, #1
            b.w  POE_STD_CONT       ; beq (non-standard) / cmp #2 / bne: flags kept
    sc_none:                    ; the timeout: say so instead of leaving the row blank
            ldr  r0, =S_NONE
            movs r1, #16
            str  r1, [sp]           ; size
            str  r0, [sp, #4]       ; string
            movs r0, #VAL_X
            movs r1, #ROW0_Y
            movs r2, #0x5A
            movs r3, #0x14
            bl   GUI_BLIT
            b.w  POE_RESULT_EXIT
    """, extra_syms=syms, why="std_check: standard 0 draws 'No PoE'")

    entry = img.emit_code("""
    entry_hook:                 ; 0x0801327E: bl poe_screen_draw
            push {r4, lr}
            sub  sp, #8
            movs r0, #0
            ldr  r4, =LIVE
            str  r0, [r4]           ; counter, flag, last span
            ldr  r4, =POE_TIMEOUT_CNT
            strh r0, [r4]           ; re-arm the 3.5 s "No PoE" timeout
            bl   POE_SCREEN_DRAW
            ldr  r0, =POE_SPAN
            ldrb r0, [r0]
            cmp  r0, #0
            bne  eh_done            ; a result is known: the caller posts 0x14
            ldr  r0, =S_DETECT
            movs r1, #16
            str  r1, [sp]
            str  r0, [sp, #4]
            movs r0, #VAL_X
            movs r1, #ROW0_Y
            movs r2, #0x5A
            movs r3, #0x14
            bl   GUI_BLIT
    eh_done:
            add  sp, #8
            pop  {r4, pc}
    """, extra_syms=syms, why="entry_hook: re-arm the timeout, draw the screen, 'Detecting...'")
    img.poe = dict(strs=strs, tick=tick, live_check=live_check, std_check=std_check, entry=entry, latch_hook=latch_hook,
                   live=live, latch=latch, syms=syms)

    site = 0x08013ECC                   # bl poe_state_machine -> bl poe_tick
    img.poke(site, "06f018f8", assemble(site, f"bl 0x{tick:08X}"), "PoE task tick -> poe_tick (live refresh)")
    site = 0x0801395C                   # movw r0,#0x2105 -> b.w live_check
    img.poke(site, "42f20510", assemble(site, f"b.w 0x{live_check:08X}"), "0x14 handler: rows only on a full redraw")
    site = 0x080139AC                   # cmp r0,#0; beq 0x08013A96; cmp r0,#1 -> b.w std_check; nop
    img.poke(site, "0028 72d0 0128", assemble(site, f"b.w 0x{std_check:08X}\n nop"), "standard 0 (timeout) draws 'No PoE'")
    site = 0x0801327E                   # bl poe_screen_draw -> bl entry_hook
    img.poke(site, "00f059f8", assemble(site, f"bl 0x{entry:08X}"), "screen entry: re-arm timeout, 'Detecting...'")
    site = 0x08013632                   # 0x14 handler: movw r0,#0x2105 -> b.w latch_hook
    img.poke(site, "42f20510", assemble(site, f"b.w 0x{latch_hook:08X}"), "0x14 handler: latch the sample block first")
    import struct as _st
    for lit, target, what in ((0x08013A38, latch + 12, "poe_mv"), (0x08013A44, latch, "poe_adc_ch"), (0x08013A48, latch + 10, "adc min")):
        old = img.read(lit, 4)
        img.poke(lit, old.hex(), _st.pack("<I", target), f"0x14 handler literal: {what} -> the latch")


# =====================================================================
# Group: FLASH (port blink)
# =====================================================================

FLASH_ON_MS, FLASH_OFF_MS = 1500, 1000     # link held once seen / PHY powered down (stock: 1 s), per blink cycle
FLASH_RELINK_MS = 4000                     # initial negotiation window
FLASH_RELINK_MAX_MS = 16000                # back off 4 -> 8 -> 16 s after failures, retain until session exit
FLASH_TICK_MS = 500                        # the net task's msg 8 period on the FLASH screen (stock 1000)
FLASH_NOTE = ("Watch the port", "LED on the switch:", "it blinks when linked")


@patch("flash-blink", "FLASH: the port LED blinks with a fixed 1.5 s on time, timed from the link, instead of a 5 s counter",
       risk="low", group="flash")
def p_flash_blink(img):
    """
    How stock makes a switch port blink (FLASH, sysState 6; disassembly of
    leng_enter_state 0x08012EE4, LENG_link_test 0x0800D47C, the net task's
    message 8 handler 0x0801494C and APP_Flash_task 0x0800DC5C):

      * entering the screen resets the PHY, advertises 10BASE-T only
        (yt8531_set_1000M(0) / set_100M(0), the fastest-linking speed, a sound
        choice), shows "Testing" for about half a second while the PHY is
        configured, then sets test_busy_flags[1] = 2 and shows the "Please
        note LED" screen.  (The 20 s wait for the link with the "..." dots is
        the SPEED screen's path, 0x0800D5E0; FLASH skips it.)
      * from then on the 1 ms tick hook posts message 8 every 1000 ms
        (0x0801BCEE) while the state is 6, and the handler runs a 5-phase
        counter: phases 0..3 power the PHY up, phase 4 powers it down, phase 5
        wraps.  It never looks at the link.  Every power-up costs the switch a
        full re-link -- its Clause 28 break_link_timer (1.2..1.5 s) from the
        moment the link dropped, then auto-negotiation -- so of the 4 s "up"
        window the port LED is lit only for what is left after 2..3 s, and on
        a switch that takes longer than the window it is never lit at all;
      * the handler does not check that the session is active either;
      * APP_Flash_task mirrors the PHY link output (PB5) on the screen and the
        RGB LED, waiting 150 ms before showing "on" and 800 ms before "off".

    What this patch does:

      1. Message 8 arrives every FLASH_TICK_MS (500 ms) instead of 1000.
      2. The handler becomes a small state machine timed from the link itself
         (flash_tick, in the cave; hook at 0x0801494C): only while the session
         is active (flags[1] == 2) it waits for the link (PB5 high, the same
         input the vendor's screen indicator uses), holds it for FLASH_ON_MS
         from the tick that first saw it, then powers the PHY down for
         FLASH_OFF_MS (1 s, as stock) and waits for the link again.  While
         it waits it re-asserts the power-up every tick (stock wrote it every
         second too; a write the PHY ignored while entering power-down would
         otherwise leave it down for good). PN 2.7 starts with a 4-second
         negotiation window, doubles it after failure to 8 then 16 seconds,
         and retains that window until the session ends. This avoids the
         PN 2.6 starvation reproduced with 4.5- and 6-second simulated ports.
         Ports needing more than 16 seconds or rejecting the advertisement
         can still fail; this is not universal switch compatibility.
         Elapsed time comes from xTaskGetTickCount; on/off phases use the
         full minimum duration, without the former half-tick subtraction.
         Real dispatch delays can lengthen phases. The stock phase byte is
         reset on session exit; both arena words are initialised on phase 0
         before use. Backoff is bounded and does not disable recovery retries.
      3. The screen indicator clears 300 ms after the link drops instead of
         800, so it follows the port LED.
      4. The English note reads "Watch the port / LED on the switch: / it
         blinks when linked" (stock: "Please note LED / It will start blinking
         / when connection successful"); the Thai wording already says this.

    Timing is CPU-model evidence, not bench measurements. verify.py sections
    22 and 24 cover phase bounds, retry backoff, stopped sessions and rollover.
    """
    from lpm10a.thumb import assemble
    start = img.alloc_ram(8)                       # u32 phase start, u32 negotiation window
    syms = dict(
        GET_STATE=0x0800F764 | 1, TICKS=0x0801C5B0 | 1, GPIO_READ=0x08015AF2 | 1,
        PWR_DOWN=0x0801D178 | 1, FLAGS1=0x200002B5, PHASE=0x20000076, START=start,
        GPIOB=0x40010C00, PIN5=0x20,
        T_ON=FLASH_ON_MS, T_OFF=FLASH_OFF_MS,
        T_RELINK=FLASH_RELINK_MS, T_MAX=FLASH_RELINK_MAX_MS,
    )
    tick = img.emit_code("""
    flash_tick:                 ; net task message 8, every FLASH_TICK_MS while sysState == 6
            push {r4, r5, r6, lr}
            movs r0, #0
            bl   GET_STATE
            cmp  r0, #6
            bne  ft_done
            ldr  r0, =FLAGS1        ; test_busy_flags[1]: 2 = blink session active
            ldrb r0, [r0]
            cmp  r0, #2
            bne  ft_done            ; initial link wait, or stopped: leave the PHY alone
            ldr  r4, =PHASE         ; 0 fresh, 3 waiting for link (timed), 1 link held, 2 link dropped
            ldr  r5, =START
            bl   TICKS
            mov  r6, r0             ; now (ms)
            ldrb r0, [r4]
            cmp  r0, #2
            beq  ft_dark
            cmp  r0, #1
            beq  ft_hold
            cmp  r0, #3
            beq  ft_wait
            str  r6, [r5]           ; phase 0 (session start, phase byte cleared by stock): stamp, then wait
            movw r0, #T_RELINK
            str  r0, [r5, #4]       ; no uninitialised-arena dependency
            movs r0, #3
            strb r0, [r4]
            b    ft_done
    ft_wait:                        ; phase 3: is the link up?  (PB5, the PHY's link output)
            movs r1, #PIN5
            ldr  r0, =GPIOB
            bl   GPIO_READ
            cmp  r0, #0
            beq  ft_nolink
            str  r6, [r5]           ; link seen: hold it from now
            movs r0, #1
            strb r0, [r4]
            b    ft_done
    ft_nolink:
            ldr  r1, [r5]
            subs r0, r6, r1
            ldr  r1, [r5, #4]       ; adaptive no-link window
            cmp  r0, r1
            bhs  ft_retry
            movs r0, #0
            bl   PWR_DOWN           ; otherwise re-assert the power-up and keep waiting
            b    ft_done
    ft_retry:
            lsls r1, r1, #1
            movw r0, #T_MAX
            cmp  r1, r0
            bls  ft_limit
            mov  r1, r0
    ft_limit:
            str  r1, [r5, #4]       ; retain backoff even after a successful blink
            b    ft_drop
    ft_hold:
            ldr  r1, [r5]
            subs r0, r6, r1
            movw r1, #T_ON          ; full minimum hold, even with bunched / jittered messages
            cmp  r0, r1
            blo  ft_done
    ft_drop:
            movs r0, #1
            bl   PWR_DOWN           ; drop the link
            str  r6, [r5]
            movs r0, #2
            strb r0, [r4]
            b    ft_done
    ft_dark:
            ldr  r1, [r5]
            subs r0, r6, r1
            movw r1, #T_OFF         ; full minimum powered-down interval
            cmp  r0, r1
            blo  ft_done
            movs r0, #0
            bl   PWR_DOWN           ; power up: the link comes back once the switch re-negotiates
            str  r6, [r5]           ; and wait for it, timed from now
            movs r0, #3
            strb r0, [r4]
    ft_done:
            pop  {r4, r5, r6, pc}
    """, extra_syms=syms, why="flash_tick: link-timed blink state machine")
    img.flash = dict(tick=tick, start=start, window=start + 4)

    site = 0x0801494C                   # msg 8 handler: movs r0,#0; bl get_sysState -> bl flash_tick; b 0x08014992
    img.poke(site, "0020 faf709ff", assemble(site, f"bl 0x{tick:08X}\n b 0x08014992"),
             "net task msg 8 -> flash_tick (stock phase counter bypassed)")
    # mov.w with a modified immediate is not in the SDK assembler: the two words are the T2
    # encodings, checked against Capstone in verify.py section 22
    assert FLASH_TICK_MS == 500
    site = 0x0801BCEE                   # tick hook: mov.w r1,#1000 -> mov.w r1,#500 (msg 8 every FLASH_TICK_MS)
    img.poke(site, "4ff47a71", bytes.fromhex("4ff4fa71"), f"FLASH tick 1000 ms -> {FLASH_TICK_MS} ms")
    site = 0x0800DCA0                   # APP_Flash_task: mov.w r0,#800 -> mov.w r0,#300 before the indicator clears
    img.poke(site, "4ff44870", bytes.fromhex("4ff49670"), "screen indicator off after 300 ms, not 800")
    for addr, text in zip((0x0800DB48, 0x0800DB58, 0x0800DB70), FLASH_NOTE):
        img.set_string(addr, text)


# =====================================================================
# Group: tuning
# =====================================================================

@patch("blind-zone-50cm", "EXPERIMENT: lower the length blind zone from 2.0 m to 0.5 m",
       risk="untested", default=False, group="tuning")
def p_blind_zone(img):
    """
    Stock zeroes every pair whose raw diagnostic result is <= 200 cm
    (0x0801253A: cmp r0,#0xC8; bgt), so cables of 2 m or less read "Out of
    range".  On the tested unit a 1 m cable came back as raw ~200..240 cm
    or nothing, i.e. the PHY's short-range result is unreliable but not
    absent.  This experiment moves the cut to 50 cm so that whatever the
    PHY reports for 0.5..2 m cables becomes visible (after the four-run
    average, Zero and NVP).  Purpose: measure cables of 0.5, 1, 1.5, 2 and
    3 m several times each and decide whether a short-range correction is
    possible.  Not in the default build: below 2 m the numbers are not to
    be trusted until that data exists.
    """
    img.poke(0x0801253A, "c828", bytes.fromhex("3228"), "blind zone: raw <= 200 cm -> raw <= 50 cm")


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


from roadmap import register as _register_roadmap
_register_roadmap(patch)

from portflash import register as _register_portflash
_register_portflash(patch)

from audit_fixes import register as _register_audit
_register_audit(patch)

from portflash_status import register as _register_portflash_status
_register_portflash_status(patch)

from scan_sync import register as _register_scan_sync
_register_scan_sync(patch)

from scan_recovery import register as _register_scan_recovery
_register_scan_recovery(patch)

from length_progress import register as _register_length_progress
_register_length_progress(patch)

from about_values import register as _register_about_values
_register_about_values(patch)

from speed_partner import register as _register_speed_partner
_register_speed_partner(patch)

from length_reference import register as _register_length_reference
_register_length_reference(patch)

from cable_test import register as _register_cable_test
_register_cable_test(patch)

from cable_clear import register as _register_cable_clear
_register_cable_clear(patch)

from cable_values import register as _register_cable_values
_register_cable_values(patch)

from length_ref_anytime import register as _register_length_ref_anytime
_register_length_ref_anytime(patch)

from length_ref_reset import register as _register_length_ref_reset
_register_length_ref_reset(patch)

from speed_partner_validity import register as _register_speed_partner_validity
_register_speed_partner_validity(patch)


def _register_release_stage(module_name, title, parent_id):
    # These standalone builders import profiles to construct their historical
    # parents. Import only while applying a completed profile, never while
    # constructing the registry. Each apply() keeps its exact-parent digest.
    @patch(module_name.replace('_', '-'), title, risk='low', default=False,
           group='release', requires=(parent_id,))
    def release_stage(img):
        from importlib import import_module
        return import_module(module_name).apply(img)


_register_release_stage('qc_continuity', 'QC: continuous acquisition and transactional Init',
                        'speed-partner-validity')
_register_release_stage('qc_classic', 'QC: classic screen with automatic testing and selective redraw',
                        'qc-continuity')
_register_release_stage('length_integrity', 'Length lifecycle, REF and progress guards; qualify QC passes',
                        'qc-classic')
_register_release_stage('qc_timing', 'QC: normalize counts to actual elapsed time and migrate calibration',
                        'length-integrity')
_register_release_stage('qc_display', 'QC: correct entry artwork ordering and reject stale bitmaps',
                        'qc-timing')
_register_release_stage('tone_precision', 'Tone: specialize carrier GPIO transitions without changing pin settings',
                        'qc-display')
_register_release_stage('tone_alignment', 'Tone: align Analog with a local phase accumulator at unchanged timer cadence',
                        'tone-precision')
_register_release_stage('cable_check', 'Cable Test: pair-partner check, RX-unit plausibility, keys ignored while measuring',
                        'tone-alignment')
_register_release_stage('cable_colours', 'Cable Test: wires in their T568B colours with white stripes',
                        'cable-check')
_register_release_stage('cable_fix', 'Cable Test: partner check tolerant of centre taps, RX-unit median',
                        'cable-colours')
_register_release_stage('cable_safe', 'Cable Test: Switch mode decides as stock, LAN colours kept',
                        'cable-fix')
