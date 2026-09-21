"""
Patch set for the LPM-10A receiver firmware V3.0.0.

Same conventions as the transmitter SDK: each patch declares every byte it
touches (stock bytes and new bytes), and verify.py checks the built image
against that record byte for byte before it runs the behavioural checks.

risk levels
    safe      byte-for-byte reversible edit, verified by disassembly+emulation
    low       behavioural change, verified by emulation, semantics well understood
    untested  needs a real device to confirm; not in the default build
"""
from lpm10rx.image import PatchError   # noqa: F401
import hashlib

REGISTRY = []

DIGITAL_EXPERIMENT = "APP_LPM-10RX_PN1.1-digital-experimental.bin"
RELIABILITY_EXPERIMENT = "APP_LPM-10RX_PN1.2-reliability-experimental.bin"
ROADMAP_EXPERIMENT = "experimental/APP_LPM-10RX_PN1.4-roadmap.bin"
ROADMAP_PATCHES = {"batt-critical-recover", "activity-before-autooff", "digital-correlation",
                   "recent-signal-autooff", "adc-complete", "main-watchdog", "digital-strength"}


def patch(pid, title, risk, default=True, group="misc"):
    def deco(fn):
        fn.pid, fn.title, fn.risk, fn.default, fn.group = pid, title, risk, default, group
        REGISTRY.append(fn)
        return fn
    return deco


# =====================================================================
# Group: correctness fixes
# =====================================================================

@patch("batt-critical-recover", "Critical-battery shutdown recovers if the voltage comes back",
       risk="low", group="bugfix")
def p_batt_recover(img):
    """
    battery_500ms (0x08007770) runs every 500 ms (TIM1 tick 500): trimmed
    mean of five ADC samples, mV = raw * 6600 / 4096, then a three-state
    machine kept in batt_state (0x20000056):

        0 ok        -> 1 when mV <= 3579  (low-battery LED on)
        1 low       -> 0 when mV >= 3621, -> 2 when mV <  3280
        2 critical  -> counts readings in batt_crit_count (0x20000057);
                       power_off at 5 (2.5 s).  Nothing ever leaves state 2.

    So one reading below 3280 mV -- a beep burst is exactly the load that
    dips a tired cell for one reading -- starts a 2.5 s countdown that no
    recovery can stop.

    Fix, in place (the stock block is 30 bytes, so is the new one):

        state 2:  if mV >= 3400 -> jump to the existing "state = 1, count = 0"
                  code at 0x080077F2, which then falls through the normal
                  state-1 handling (LED, hysteresis checks) and the epilogue;
                  else count++ (as a byte, like stock) and power_off at 5.

    The counter therefore only reaches 5 after five consecutive readings
    (2.5 s) below 3400 mV, with 120 mV of hysteresis above the 3280 mV
    entry.  The ADC grid is 1.6 mV, so the first reading that recovers is
    raw 2111 = 3401 mV; 3400 itself is not a representable value.

    Register facts the patch relies on (verified in verify.py):
      * r4 == 0x2000004A (batt_samples) for the whole function, so
        batt_crit_count is [r4, #0xD] and needs no 8-byte address load;
      * mV is the u16 at [sp, #4], as the stock state-1 code also reads it;
      * the block is entered only from `cmp state,#2 / bne`, so no other
        branch lands inside it.
    """
    site = 0x08007880
    code = img.assemble_at(site, """
            mov  r1, sp
            ldrh r0, [r1, #4]        ; mV
            movw r1, #3400
            cmp  r0, r1
            bhs  0x080077F2          ; recovered: state = 1, count = 0 (stock code)
            ldrb r1, [r4, #0xD]      ; batt_crit_count
            adds r1, #1
            uxtb r1, r1              ; byte counter, wraps like stock
            strb r1, [r4, #0xD]
            cmp  r1, #5
            blt  0x080078AC          ; not yet: epilogue
            bl   power_off
            b    0x080078AC
    """)
    assert len(code) == 30, len(code)
    img.poke(site,
             "40f25700 c2f20000 0178 0131 0170 0078 0528 03db ffe7 fff76bfe ffe7 06e0",
             code, "critical battery: recover above 3400 mV, else count to 5 as stock")


@patch("activity-before-autooff", "Honor existing activity at the auto-off deadline",
       risk="untested", default=False, group="power")
def p_activity_autooff(img):
    """TIM1 checked idle >=300001 before processing a nonzero beep/keepalive.

    A signal or key arriving on that final tick could therefore power off an
    active probe. Keep the original counter increment and shutdown threshold,
    but skip auto-off when the existing keepalive byte is nonzero. The normal
    downstream code still decrements that byte and resets idle to zero. No
    ADC, battery protection, physical power-key or watchdog changes.

    Replace exactly 36 bytes; both exits branch over the literal pool. r0-r2
    are caller-saved scratch here; TIM1's next block overwrites r0/r1 and no
    later code consumes the original r2. No additional stack or persistent RAM.
    """
    site = 0x0800A992
    code = img.assemble_at(site, """
            ldr  r0, =0x20000104
            ldr  r1, [r0]
            adds r1, #1
            str  r1, [r0]
            ldrb r2, [r0, #8]       ; beep / activity countdown at 0x2000010C
            cmp  r2, #0
            bne  done
            ldr  r0, =300001
            cmp  r1, r0
            blo  done
            bl   power_off
    done:   b    0x0800A9B6
    """)
    assert len(code) <= 36 and len(code) % 2 == 0, len(code)
    code += bytes.fromhex("00bf") * ((36 - len(code)) // 2)
    img.poke(site,
             "40f20410 c2f20000 0168 0131 0160 0068 49f2e131 c0f20401 8842 03d3 ffe7 fcf7defd ffe7",
             code, "TIM1: pending activity wins over idle auto-off at the deadline")
    img.activity_autooff = True


@patch("digital-correlation", "Experimental digital detector: phase search and bounded bit-error tolerance",
       risk="untested", default=False, group="scan")
def p_digital_correlation(img, strength=False, scheduled=False):
    """Replace only analyse_mode0, in its existing 336-byte footprint.

    Keep the ADC sampler, 48-sample snapshot, trimmed threshold, PA2 gate,
    50-ms beep and 800-ms hold. Search the eight rotations of repeated B6
    over ALL 48 bits; accept <=4 errors total, <=2 in each 16-bit block.
    Also retain stock's two exact sliding 16-bit matches: requiring only
    whole-window correlation would regress reception during clock drift.
    This is sample/bit phase search, NOT sub-slot oversampling or clock lock.
    Require sum(abs(sample-threshold)) >=192 ADC counts (4/sample) and
    retain the stock high-sample sum floor. Contrast is independent of DC
    level; its threshold needs bench calibration and is deliberately opt-in.

    The ISR remains paused until the snapshot is complete, then may overwrite
    the shared buffer while analysis uses its stack copy, just as in stock.
    No persistent RAM, image growth, vector, binding, version-page or ADC edits.
    The PN 1.6 scheduled variant instead uses sampling_fixes' guarded entry
    and result publisher; that profile owns two additional padding bytes.
    """
    site, size = 0x08009E08, 0x150
    old = img.read(site, size)
    if strength:
        if old != getattr(img, "digital_code", None):
            raise PatchError("digital-strength requires digital-correlation first")
    elif hashlib.sha256(old).hexdigest() != "ccb897bffd0017ae556df66c6bcb5cfd709959e869a1ee7caf2eb9c2b5452f7a":
        raise PatchError("digital detector is not the audited V3.0.0 routine")
    source = """
        push {r3, r4, r5, r6, r7, lr}
        sub  sp, #96
        ldr  r0, =0x20000008
        ldrb r1, [r0]
        cmp  r1, #0
        bne  early_out
        ldr  r1, =0x20000068
        ldrh r1, [r1]
        cmp  r1, #2
        bhs  snapshot
    early_out:
        add  sp, #96
        pop  {r3, r4, r5, r6, r7, pc}
    snapshot:
        ldr  r0, =0x2000006E
        mov  r1, sp
        movs r2, #48
    copy:
        ldrh r3, [r0]
        strh r3, [r1]
        adds r0, #2
        adds r1, #2
        subs r2, #1
        bne  copy
        ldr  r0, =0x20000008
        movs r1, #1
        strb r1, [r0]
        mov  r0, sp
        movs r1, #48
        bl   trimmed_mean
        mov  r5, r0
        mov  r0, sp
        movs r1, #48
        movs r6, #5
        movs r7, #0
        movs r4, #0
        str  r4, [sp, #96]       ; pushed caller-saved r3 slot is scratch
    threshold:
        ldrh r2, [r0]
        cmp  r2, r5
        bls  low
        add  r6, r2
        subs r2, r2, r5
        movs r3, #1
        b    save_bit
    low:
        subs r2, r5, r2
        movs r3, #0
    save_bit:
        add  r7, r2
        lsls r4, r4, #1
        orrs r4, r3
        uxth r4, r4
        movw r2, #0xB6B6
        cmp  r4, r2
        bne  no_exact
        ldr  r2, [sp, #96]
        adds r2, #1
        str  r2, [sp, #96]
    no_exact:
        strh r3, [r0]
        adds r0, #2
        subs r1, #1
        bne  threshold
        cmp  r7, #192
        blo  done
        movw r0, #1000
        cmp  r6, r0
        blo  done
        ldr  r0, [sp, #96]
        cmp  r0, #2
        bhs  detected
        movw r4, #0xB6B6
        movt r4, #0xB6B6
        movs r5, #8
    phase:
        mov  r6, r4
        mov  r0, sp
        movs r1, #48
        movs r2, #0
        movs r3, #0
    bit:
        lsrs r7, r6, #31
        lsls r6, r6, #1
        orrs r6, r7
        ldrh r7, [r0]
        eors r7, r6
        lsls r7, r7, #31
        beq  matched
        adds r2, #1
        adds r3, #1
        cmp  r2, #4
        bhi  next_phase
        cmp  r3, #2
        bhi  next_phase
    matched:
        adds r0, #2
        subs r1, #1
        beq  detected
        movs r7, #15
        ands r7, r1
        bne  bit
        movs r3, #0
        b    bit
    next_phase:
        lsrs r7, r4, #31
        lsls r4, r4, #1
        orrs r4, r7
        subs r5, #1
        bne  phase
        b    done
    detected:
        ldr  r0, =0x2000010C
        movs r1, #50
        strb r1, [r0]
        ldr  r0, =0x2000005A
        strb r1, [r0]
        ldr  r0, =0x2000006C
        movw r1, #800
        strh r1, [r0]
    done:
        add  sp, #96
        pop  {r3, r4, r5, r6, r7, pc}
    """
    if strength:
        source = source.replace("ldr  r0, [sp, #96]\n        cmp  r0, #2",
                                "ldr r0, [sp, #96]\n        str r7, [sp, #96]\n        cmp r0, #2")
        source = source.replace("""        ldr  r0, =0x2000010C
        movs r1, #50
        strb r1, [r0]
        ldr  r0, =0x2000005A
        strb r1, [r0]""", """        ldr r7, [sp, #96]
        movs r1, #100
        movw r0, #500
        cmp r7, r0
        blo grade_ready
        movs r1, #50
        movw r0, #1000
        cmp r7, r0
        bls grade_ready
        movs r1, #30
    grade_ready:
        ldr r0, =0x2000005A
        strb r1, [r0, #3]       ; owned padding byte: repeat gap
        strb r1, [r0]
        cmp r1, #50
        bls grade_on
        movs r1, #50
    grade_on:
        ldr r0, =0x2000010C
        strb r1, [r0]""")
    if scheduled:
        if not strength:
            raise PatchError("scheduled digital feedback requires strength grading")
        source = source.replace("""        ldr  r0, =0x20000008
        ldrb r1, [r0]
        cmp  r1, #0
        bne  early_out
        ldr  r1, =0x20000068
        ldrh r1, [r1]
        cmp  r1, #2
        bhs  snapshot""", """        bl sampling_ready
        cmp r0, #0
        bne snapshot""")
        begin = source.index("    grade_ready:")
        end = source.index("    done:", begin)
        source = source[:begin] + """    grade_ready:
        bl publish_digital
""" + source[end:]
    code = img.assemble_at(site, source)
    if len(code) > size:
        raise PatchError(f"digital detector exceeds in-place footprint: {len(code)} > {size}")
    code += bytes.fromhex("00bf") * ((size - len(code)) // 2)
    img.poke(site, old.hex(), code, "experimental digital detection: 48-bit correlation over eight phases")
    img.digital_code = code


@patch("recent-signal-autooff", "Reset idle time for a recently detected digital signal",
       risk="untested", default=False, group="power")
def p_recent_autooff(img):
    # Replaces the already patched prefix and stock tick/beep housekeeping.
    # The base is idle_ticks (0x104): signal_recent is -0x98, NOT -0xA0.
    if not getattr(img, "activity_autooff", False):
        raise PatchError("recent-signal-autooff requires activity-before-autooff")
    site, size = 0x0800A992, 0x5E
    code = img.assemble_at(site, """
        ldr r0, =0x20000104
        ldr r1, [r0]
        adds r1, #1
        ldrb r2, [r0, #8]
        ldr r3, =0x2000006C
        ldrh r3, [r3]
        orrs r3, r2
        beq idle
        movs r1, #0
    idle:
        str r1, [r0]
        ldr r3, =300001
        cmp r1, r3
        blo housekeeping
        bl power_off
    housekeeping:
        ldr r0, =0x200000FC
        ldr r1, [r0]
        adds r1, #1
        str r1, [r0]
        ldrb r1, [r0, #16]
        cbz r1, done
        subs r1, #1
        strb r1, [r0, #16]
    done:
        b.w 0x0800A9F0
    """)
    _replace(img, site, size, code, "TIM1: recent signal or beep resets idle before deadline check")


def _replace(img, site, size, code, why):
    audited = {
        0x080072A4: "90910793a729f7ce82a20beacebb8381c653e0e27bbdf281529dd50e5c8c9db5",
        0x08007724: "6248df7f65b4da246ef8b64a2a8aec580606f87006ce5f9829bad38b5014e828",
        0x0800A992: "a4316ad81168615fed4a38e7d7fba3120600b29ff490a38599364209bf0b4a98",
    }
    offset = site - 0x08006800
    if hashlib.sha256(img.original[offset:offset+size]).hexdigest() != audited[site]:
        raise PatchError(f"{why}: original routine differs from audited V3.0.0")
    if site != 0x0800A992 and img.read(site, size) != img.original[offset:offset+size]:
        raise PatchError(f"{why}: patch site already modified")
    if len(code) > size or len(code) % 2:
        raise PatchError(f"{why}: code {len(code)} exceeds slot {size}")
    img.poke(site, img.read(site, size).hex(), code + bytes.fromhex("00bf") * ((size-len(code))//2), why)


@patch("adc-complete", "Serialize channel selection through completed ADC conversion",
       risk="untested", default=False, group="reliability")
def p_adc_complete(img):
    # N32L40x manual, ADC_STS: ENDC bit 1, clear by writing zero (SDK
    # ADC_ClearFlag writes 0x7F & ~flag). Mask only the transaction and restore
    # PRIMASK. A finite 500-poll timeout requests reset instead of returning
    # fabricated battery/tone data or leaving a conversion in flight.
    site, size = 0x080072A4, 0x44
    code = img.assemble_at(site, """
        push {r4, r5, r6, lr}
        mov r4, r0
        mrs r6, primask
        cpsid i
        bl adc_config_regular_channel
        mov r0, r4
        movs r1, #0x4D
        str r1, [r0]          ; clear ENDC, ENDCA and STR before starting
        bl adc_software_start_conv
        movw r2, #500
    poll:
        ldr r0, [r4]
        lsls r0, r0, #30
        bmi ready
        subs r2, #1
        bne poll
        ldr r0, =0xE000ED0C
        ldr r1, =0x05FA0004
        str r1, [r0]
    reset_pending:
        b reset_pending
    ready:
        mov r0, r4
        bl adc_get_data
    done:
        msr primask, r6
        pop {r4, r5, r6, pc}
    """)
    _replace(img, site, size, code, "ADC: selected-channel completion, bounded wait, restore interrupt mask")


@patch("main-watchdog", "Refresh IWDG from completed main-loop iterations",
       risk="untested", default=False, group="reliability")
def p_main_watchdog(img):
    # Reuse the two movw/movt instructions which load mode at the loop head.
    # r5 already permanently holds &mode on every route into this loop.
    img.poke(0x0800B8F2, "40f24800 c2f20000",
             img.assemble_at(0x0800B8F2, "bl iwdg_reload\nmov r0, r5\nnop"),
             "main loop: watchdog refresh before mode dispatch")
    img.poke(0x0800AA8E, "fdf7c9fb", bytes.fromhex("00bf00bf"),
             "TIM1: remove unconditional watchdog refresh")


@patch("digital-strength", "Three contrast-based digital beep cadences",
       risk="untested", default=False, group="scan")
def p_digital_strength(img):
    """Own the zero-initialized padding byte 0x2000005D between the byte
    sample_idx_mode1 and halfword agc_samples; no sample buffer is borrowed.
    Correlation still decides eligibility; contrast chooses cadence only.
    """
    p_digital_correlation(img, strength=True)
    site, size = 0x08007724, 0x4C
    code = img.assemble_at(site, """
        push {r4, lr}
        ldr r4, =0x2000010C
        ldrb r0, [r4]
        bl speaker_tick
        ldr r0, =0x2000006C
        ldrh r0, [r0]
        cbz r0, done
        ldr r0, =0x2000005A
        ldrb r1, [r0]
        cbnz r1, done
        ldrb r1, [r0, #3]
        cmp r1, #30
        beq valid
        cmp r1, #100
        beq valid
        movs r1, #50
    valid:
        strb r1, [r0]
        cmp r1, #50
        bls on
        movs r1, #50
    on:
        strb r1, [r4]
    done:
        pop {r4, pc}
    """)
    _replace(img, site, size, code, "digital cadence: high 30/30, medium 50/50, low 50/100 ms")


from audit_fixes import register as _register_audit
_register_audit(patch)

from followup_fixes import register as _register_followup
_register_followup(patch)

from precision_fixes import register as _register_precision
_register_precision(patch)

from pinpoint_fixes import register as _register_pinpoint
_register_pinpoint(patch)

from robust_fixes import register as _register_robust
_register_robust(patch)

from sync_fixes import register as _register_sync
_register_sync(patch)

from tracking_fixes import register as _register_tracking
_register_tracking(patch)

from overload_fixes import register as _register_overload
_register_overload(patch)

from audio_clock_fixes import register as _register_audio_clock
_register_audio_clock(patch)
from mode_tone import register as _register_mode_tone
_register_mode_tone(patch)
from gain_norm import register as _register_gain_norm
_register_gain_norm(patch)
from release_hold import register as _register_release_hold
_register_release_hold(patch)
from smooth_gain import register as _register_smooth_gain
_register_smooth_gain(patch)
from rail_strong import register as _register_rail_strong
_register_rail_strong(patch)
from strong_cap import register as _register_strong_cap
_register_strong_cap(patch)
from fast_update import register as _register_fast_update
_register_fast_update(patch)
from auto_range import register as _register_auto_range
_register_auto_range(patch)
