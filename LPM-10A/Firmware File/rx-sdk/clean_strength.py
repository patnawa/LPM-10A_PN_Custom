"""PN1.30 (release rx-v1.30, owner-tested 2026-09-24: "1.30 test pass flicker fixed"): a steady Digital
strength, gain decisions at every window, no walk-down at a touch.

Built from the exact owner-tested PN1.29 image (rx-v1.29). Three findings from running PN1.29 in
the emulator (2026-09-24; real firmware, modeled ADC/link; not a device measurement):

1. Digital strength dips. The receiver samples each 5 ms slot in its last 2.0 ms (five readings,
   trimmed mean) while the transmitter's chip is 5.05 ms, so the chip edges drift through the
   readings once every ~0.55 s. While an edge sits inside the readings, every sample that follows a
   0->1 or 1->0 transition is a mix of both levels, and the PN1.9-1.29 estimator (median of the
   expected-high samples minus median of the expected-low samples) reads the contrast 5/6, 2/3 or
   1/2 of its true value (-1.6, -3.5, -6 dB) for up to 200 ms. On a steady signal 0.6-1.0 dB
   above a level threshold PN1.29's display flickers between two levels about once a second
   (`test_rx_clean_strength.Flicker`, red on PN1.29).
   Fix: in the code 10110110 the highs 4 and 7 follow a high and precede a low. Take each such
   high b with its predecessor a and the low c after it (three samples 15 ms apart). The
   detector aligns a window's samples either to the chip that starts inside their readings or
   to the one that ends there; either way one of a / b holds no edge while the other and c are
   mixed by the same edge fraction f (a mixed high reads L + (1-f)C, a mixed low L + fC), so
   2 max(a, b) - min(a, b) - c = C for every f, and the median over the window's three or four
   triplets rejects the one a change of pair inside the window can corrupt. Clean windows give
   exactly the old H - L. The estimator is replaced at the detector's call; the score scale
   (x21.43) and the rail / inseparable checks are unchanged.

2. Slow gain settle at a touch. The automatic gain decided only at the 500 ms knob tick, so a
   strong pair spent up to 1.5 s (7 -> 2 -> 1 -> 0) reading the saturation of a too-high gain.
   Fix: the TIM1 1 ms tick also lets the same guarded PN1.24 gain routine decide once per
   completed sample window, after the display has shown that window (tracing modes; no hold
   pending), so a step down is followed by the next decision as soon as a complete window at
   the new gain has been heard (about 280 ms in Digital, 21 ms in Analog): a strong touch is
   heard at once at the first gain's saturation and rises one gain at a time to its level in
   about 0.8 s, with no gap. A step up still holds one 500 ms tick, as PN1.29.

3. Walk-down while settling. A window read at a saturated gain is a lower bound, but the PN1.29
   display followed it down (the trace shows level 8 -> 5 -> 7 -> 8 over 2 s on one strong pair).
   Fix: while the driven gain is above the lowest and the newest 40 samples span >= 1900 counts
   (the gain routine's own saturation test), the window is a lower bound: it is counted 1.2 dB
   lower (x 7/8, a margin for the measured gain-step table, whose steps were taken on one unit)
   and, when weaker than the stored strength, never lowers it.
   Stronger windows, the fresh path and the 0.5 dB hysteresis are PN1.29's; an unsaturated
   weaker window moves the stored strength an eighth of the way as in PN1.29, or half way when
   it is 25 % (2.5 dB) or more below it, which the residual edge dips (<= 1.6 dB) never are,
   so a real 6 dB drop shows its new level in about 0.5 s instead of 1 s.

Everything else (levels, knob law K, intervals, NCV gain, beep, detection thresholds, sampler,
Analog analysis) is PN1.29's byte for byte.

    python clean_strength.py            dry build
    python clean_strength.py --write    experimental/APP_LPM-10RX_PN1.30-clean-strength*.bin + sums
"""
import argparse
import contextlib
import hashlib
import io

import auto_range
import isolate
import knob_reference
import level_display
import sample_age_guard
from lpm10rx import symbols
from lpm10rx.container import wrap
from lpm10rx.image import PatchError
import version_tag

VERSION = 'PN1.30'
PARENT_SHA256 = '092d7ad1e4a7d16130b746172b504bd5ee8998590512376962ec044395dfa378'   # raw PN1.29 (rx-v1.29)
OUTPUT = 'APP_LPM-10RX_PN1.30-clean-strength.bin'
UPDATE = 'APP_LPM-10RX_PN1.30-clean-strength-update.bin'
SUMS = 'RX-PN1.30-SHA256SUMS.txt'
DIRECTORY = isolate.DIRECTORY

# PN1.29 sites (checked byte for byte before any change)
ESTIMATE_CALL = 0x08009EFA          # detector: bl recent_estimate (0x0800B670)
OLD_ESTIMATOR = 0x0800B670
CURVE_CALLS = (0x0800D466, 0x0800D484)   # PN1.29 digital / analog helpers: bl curve
OLD_CURVE = 0x0800D348              # PN1.29 curve
TIM1_SITE = 0x0800AA1E              # TIM1_UP_IRQHandler: RECENT countdown (32 bytes, stock)
TIM1_SITE_BYTES = bytes.fromhex('40f26c00c2f200000088012808dbffe740f26c00c2f20000018801390180ffe7')
SORT = 0x0800B6DE                   # sort_u16(ptr, n)
MEDIAN = 0x0800B584                 # robust_median(sorted ptr, n) -> value, 0xFFFF when n == 0
GAIN_SELECT = 0x0800A4FC            # gain_select_3bit(level): PN1.29 gain hook -> PN1.24 AGC
BUFFER = 0x2000006E
RECENT = 0x2000006C
KNOB_CODE = 0x2000006A
MODE = isolate.MODE
STATE = auto_range.STATE            # [0] driven gain [2] hold
SAT_PP = auto_range.SAT_PP          # 1900: the gain routine's saturation test
SAT_SAMPLES = 40                    # the newest samples that are stable while an analyser runs
SAT_MARGIN_SHIFT = 3                # a saturated reading counts as strength - strength >> 3 (-1.2 dB)
LAST_DECIDED = 0x20000218           # u32: COMPLETED_AT of the window the fast gain path judged (zero-init)
LAST_DISPLAYED = 0x2000021C         # u32: COMPLETED_AT of the window the display last showed (zero-init)
FAST_FALL_QUARTER = True            # a window >= 25 % below the stored strength moves it half way, not an eighth

CONTRAST_SCALE = (29, 46, 12)       # score = C x 29 - (C x 29 / 46) x 12  (PN 1.9 arithmetic)


def contrast_score(contrast):
    """The estimator's score for a contrast (the firmware's integer steps)."""
    if contrast <= 0:
        return 0
    x = contrast * CONTRAST_SCALE[0]
    return x - (x // CONTRAST_SCALE[1]) * CONTRAST_SCALE[2]


def estimate(samples, pattern):
    """Model of the new estimator: 16 samples (low 12 bits used), pattern = 32-bit rotated code.

    Every high that precedes a low (chips 4 and 7 of 10110110) follows a high and is followed by a
    low: with a = that high's predecessor, b = the high itself and c = the low after it (15 ms
    apart), whichever way the detector aligned the window one of a / b holds no edge in its
    readings while the other and c are mixed by the same edge fraction, so
    2 max(a, b) - min(a, b) - c is the contrast for every fraction. The median over the window's
    three or four triplets rejects the one a change of pair inside the window can corrupt.
    Returns the score, or 0 for an unranked window (the clean highs at the rail, or C <= 0)."""
    pat = pattern & 0xFFFFFFFF
    bits = []
    for _ in samples:
        bits.append(pat >> 31)
        pat = ((pat << 1) | (pat >> 31)) & 0xFFFFFFFF
    values = [v & 0xFFF for v in samples]
    contrasts, highs = [], []
    for i in range(1, len(samples) - 1):
        if (bits[i - 1], bits[i], bits[i + 1]) == (1, 1, 0):
            h, p = max(values[i - 1], values[i]), min(values[i - 1], values[i])
            contrasts.append(max(0, 2 * h - p - values[i + 1]))
            highs.append(h)
    if not contrasts:
        return 0

    def median(group):
        g = sorted(group)
        n = len(g)
        return (g[n // 2] + g[(n - 1) // 2]) // 2

    if median(highs) >= 4095:
        return 0
    c = median(contrasts)
    return contrast_score(c) if c > 0 else 0


ESTIMATOR_SOURCE = f'''
    push {{r4, r5, r6, r7, lr}}
    sub sp, #16                 ; [0..7] up to four triplet contrasts, [8..15] their highs (u16)
    mov r4, r0                  ; the 16 samples
    movs r5, #0                 ; sample index
    movs r6, #0                 ; triplets found
scan:
    cmp r5, #0
    beq advance                 ; a triplet needs the sample before
    cmp r5, #15
    beq advance                 ; and the one after
    lsrs r2, r1, #30
    cmp r2, #2                  ; expected: this sample high, the next low
    bne advance
    lsls r2, r1, #31
    beq advance                 ; and the previous one high
    lsls r0, r5, #1
    adds r0, r4, r0
    ldrh r2, [r0]               ; b: the high before a low
    subs r0, #2
    ldrh r3, [r0]               ; a: the high before it
    adds r0, #4
    ldrh r7, [r0]               ; c: the low after it
    lsls r2, r2, #20
    lsrs r2, r2, #20
    lsls r3, r3, #20
    lsrs r3, r3, #20
    lsls r7, r7, #20
    lsrs r7, r7, #20            ; 12-bit samples
    cmp r2, r3
    bhs ordered
    mov r0, r2
    mov r2, r3
    mov r3, r0                  ; r2 = max(a, b): the high without an edge; r3 = the mixed one
ordered:
    lsls r0, r2, #1
    subs r0, r0, r3
    subs r0, r0, r7             ; 2 max - min - low: the contrast without the mixed samples' share
    bpl positive
    movs r0, #0
positive:
    lsls r3, r6, #1
    mov r7, sp
    add r7, r3
    strh r0, [r7]
    strh r2, [r7, #8]
    adds r6, #1
advance:
    lsrs r2, r1, #31
    lsls r1, r1, #1
    orrs r1, r2                 ; rotate: bit 31 = the next sample's bit, bit 0 = this one's
    adds r5, #1
    cmp r5, #16
    blo scan
    cmp r6, #0
    beq uncertain
    mov r0, sp
    mov r1, r6
    bl {SORT:#x}
    mov r0, sp
    mov r1, r6
    bl {MEDIAN:#x}
    mov r5, r0                  ; the median contrast
    mov r0, sp
    adds r0, #8
    mov r1, r6
    bl {SORT:#x}
    mov r0, sp
    adds r0, #8
    mov r1, r6
    bl {MEDIAN:#x}
    movw r2, #4095
    cmp r0, r2
    bhs uncertain               ; the clean highs sit on the rail
    mov r0, r5
    cmp r0, #0
    beq uncertain
    movs r1, #{CONTRAST_SCALE[0]}
    muls r0, r1, r0
    movs r1, #{CONTRAST_SCALE[1]}
    udiv r1, r0, r1
    movs r2, #{CONTRAST_SCALE[2]}
    muls r1, r2, r1
    subs r0, r0, r1             ; the PN 1.9 score scale (x21.43)
    add sp, #16
    pop {{r4, r5, r6, r7, pc}}
uncertain:
    movs r0, #0
    add sp, #16
    pop {{r4, r5, r6, r7, pc}}
'''

# PN1.29's display with one insertion: a weaker window read at a saturated gain above the lowest
# never lowers the stored strength (see `saturated`).
CURVE_SOURCE = f'''
    push {{r4, r5, r6, lr}}
    ldr r1, ={sample_age_guard.COMPLETED_AT:#x}
    ldr r1, [r1]
    ldr r2, ={LAST_DISPLAYED:#x}
    str r1, [r2]                ; PN1.30: this window reaches the display (the fast gain path waits for it)
    ldr r1, ={isolate.DRIVEN:#x}
    ldrh r1, [r1]
    cmp r1, #7
    bhi scaled
    ldr r2, ={isolate.MULT_TABLE:#x}
    add r2, r1
    ldrb r1, [r2]
    muls r0, r1, r0
    movs r1, #10
    udiv r0, r0, r1             ; strength at the probe tip (PN 1.15/1.17/1.22)
scaled:
    ldr r2, ={isolate.CLAMP:#x}
    cmp r0, r2
    bls clamped
    mov r0, r2
clamped:
    ldr r1, ={isolate.KNOB:#x}
    ldrh r1, [r1]
    lsrs r2, r1, #8
    lsls r2, r2, #1
    ldr r3, =knob_reference
    add r3, r2
    ldrh r2, [r3]
    ldrh r3, [r3, #2]
    subs r3, r3, r2
    uxtb r1, r1
    muls r3, r1, r3
    lsrs r3, r3, #8
    adds r2, r2, r3             ; K x 256 (PN1.27)
    muls r0, r2, r0
    lsrs r0, r0, #8             ; strength against the knob's reference
    bl saturated
    cmp r2, #0
    beq exact
    lsrs r2, r0, #3
    subs r0, r0, r2             ; PN1.30: a saturated reading is a lower bound; count it 1.2 dB lower (gain-step margin)
exact:
    ldr r5, ={level_display.AVERAGE:#x}
    ldr r4, ={isolate.STATE:#x}
    ldrh r1, [r4, #18]          ; RECENT
    movw r3, #500
    cmp r1, r3
    bls fresh
    ldrb r6, [r5, #4]           ; level on display
    cmp r6, #{level_display.LEVELS}
    bhs fresh
    ldr r1, [r5]
    cmp r0, r1
    bhs rise                    ; a stronger window shows at once
    bl saturated
    cmp r2, #0
    beq fall
    mov r0, r1                  ; PN1.30: a saturated window above the lowest gain is a lower bound
    b rise
fall:
    subs r2, r1, r0
    lsls r3, r2, #2
    cmp r3, r1
    bhs half                    ; PN1.30: 25 % or more below the stored strength: half way (a real drop, not a dip)
    lsrs r2, r2, #3
    subs r0, r1, r2             ; a weaker one moves an eighth of the way (PN1.29)
    b rise
half:
    lsrs r2, r2, #1
    subs r0, r1, r2
rise:
    str r0, [r5]
    mov r4, r0
    lsrs r1, r0, #4
    subs r0, r0, r1             ; -0.5 dB
    bl count
    cmp r1, r6
    bhi show                    ; clearly into a higher level
    lsrs r0, r4, #4
    adds r0, r0, r4             ; +0.5 dB
    bl count
    cmp r1, r6
    blo show                    ; clearly into a lower level
    mov r1, r6
    b show
fresh:
    str r0, [r5]
    bl count
show:
    strb r1, [r5, #4]
    ldr r2, =intervals
    add r2, r1
    ldrb r1, [r2]
    bl {isolate.PUBLISH:#x}
    movs r0, #1
    pop {{r4, r5, r6, pc}}
count:                          ; r1 = level of r0 (thresholds at or below it); r2, r3 clobbered
    ldr r2, =thresholds
    movs r1, #0
next:
    ldr r3, [r2]
    cmp r0, r3
    blo counted
    adds r1, #1
    adds r2, #4
    cmp r1, #{level_display.LEVELS - 1}
    blo next
counted:
    bx lr
saturated:                      ; r2 = 1 when the driven gain is above the lowest and the newest {SAT_SAMPLES} samples span >= {SAT_PP}
    push {{r0, r1, r4, lr}}
    ldr r2, ={STATE:#x}
    ldrb r2, [r2]
    cmp r2, #0
    beq unsaturated             ; lowest gain: nothing lower to measure with
    ldr r1, ={BUFFER:#x}
    movs r4, #{SAT_SAMPLES}
    movw r3, #4095
    movs r0, #0
span:
    ldrh r2, [r1]
    cmp r2, r0
    bls nmax
    mov r0, r2
nmax:
    cmp r2, r3
    bhs nmin
    mov r3, r2
nmin:
    adds r1, #2
    subs r4, #1
    bne span
    subs r0, r0, r3
    movw r2, #{SAT_PP}
    cmp r0, r2
    blo unsaturated
    movs r2, #1
    pop {{r0, r1, r4, pc}}
unsaturated:
    movs r2, #0
    pop {{r0, r1, r4, pc}}
    .align 4
thresholds:
    .word {", ".join(str(t) for t in level_display.THRESHOLDS)}
knob_reference:
    .short {", ".join(str(k) for k in knob_reference.REFERENCE)}
intervals:
    .byte {", ".join(str(i) for i in level_display.INTERVALS)}
    .align 2
    .pool
'''

# Replaces the RECENT countdown in TIM1_UP_IRQHandler (every 1 ms) and adds the fast gain path.
TIM1_SOURCE = f'''
    push {{r4, lr}}
    ldr r0, ={RECENT:#x}
    ldrh r1, [r0]
    cmp r1, #0
    beq counted
    subs r1, #1
    strh r1, [r0]               ; stock: RECENT counts down once per millisecond
counted:
    ldr r0, ={MODE:#x}
    ldrb r0, [r0]
    cmp r0, #2
    bhs done                    ; Mains: the 500 ms tick alone drives the gain
    ldr r0, ={STATE:#x}
    ldrb r1, [r0, #2]
    cmp r1, #0
    bne done                    ; a hold after a step up is counted down by the 500 ms tick only
    ldr r1, ={sample_age_guard.COMPLETED_VALID:#x}
    ldr r1, [r1]
    cmp r1, #1
    bne done                    ; no complete window at the current gain yet
    ldr r1, ={sample_age_guard.COMPLETED_AT:#x}
    ldr r1, [r1]
    ldr r2, ={LAST_DISPLAYED:#x}
    ldr r3, [r2]
    cmp r1, r3
    bne done                    ; the display has not shown this window yet (its reading is a lower bound worth hearing)
    ldr r2, ={LAST_DECIDED:#x}
    ldr r3, [r2]
    cmp r1, r3
    beq done                    ; this window has been judged
    str r1, [r2]
    ldr r0, ={KNOB_CODE:#x}
    ldrh r0, [r0]               ; the knob code, as agc_update_500ms passes it
    bl {GAIN_SELECT:#x}         ; PN1.29 hook -> PN1.24 guarded automatic gain
done:
    pop {{r4, pc}}
    .pool
'''


def _branch(img, site, target):
    return img.assemble_at(site, f'b.w {target:#x}')


def _call(img, site, target):
    return img.assemble_at(site, f'bl {target:#x}')


def apply(img):
    """Apply to the exact PN1.29 image; every site is checked before any byte changes."""
    if hashlib.sha256(bytes(img.data)).hexdigest() != PARENT_SHA256:
        raise PatchError('PN1.30 requires the exact PN1.29 image')
    expected = {
        ESTIMATE_CALL: _call(img, ESTIMATE_CALL, OLD_ESTIMATOR),
        isolate.GAP_ENTRY: _branch(img, isolate.GAP_ENTRY, OLD_CURVE),
        TIM1_SITE: TIM1_SITE_BYTES,
        version_tag.VERSION_STRING: b'PN1.29\0\0',
        **{site: _call(img, site, OLD_CURVE) for site in CURVE_CALLS},
    }
    for site, old in expected.items():
        if img.read(site, len(old)) != old:
            raise PatchError(f'PN1.30: unexpected code at {site:#x}')
    for word in (LAST_DECIDED, LAST_DISPLAYED):
        if word.to_bytes(4, 'little') in bytes(img.data):
            raise PatchError(f'PN1.30: {word:#x} is already referenced by the parent image')
    # PN1.29's curve must be the one this module copies (its tables and RAM).
    old_curve = img.assemble_at(OLD_CURVE, level_display.CURVE_TEMPLATE)
    if img.read(OLD_CURVE, len(old_curve)) != old_curve:
        raise PatchError('PN1.30: PN1.29 curve differs from level_display.CURVE_TEMPLATE')

    start = symbols.APP_BASE + len(img.data)
    body = bytearray()
    addresses = {}

    def append(name, source):
        address = start + len(body)
        body.extend(img.assemble_at(address, source))
        body.extend(bytes(-len(body) % 4))
        addresses[name] = address
        return address

    estimator = append('estimator', ESTIMATOR_SOURCE)
    curve = append('curve', CURVE_SOURCE)
    tim1 = append('tim1', TIM1_SOURCE)
    if start + len(body) > symbols.EXTEND_LIMIT:
        raise PatchError('PN1.30 exceeds the application flash limit')

    img.extend(len(body), 'PN1.30: edge-free strength estimator, lower-bound display, gain at every displayed window')
    img.poke(start, bytes(len(body)).hex(), bytes(body),
             'Digital strength from edge-free highs; saturated windows never lower the display; gain at every window')
    img.poke(ESTIMATE_CALL, expected[ESTIMATE_CALL].hex(), _call(img, ESTIMATE_CALL, estimator),
             'Digital detector: strength through the edge-free estimator')
    img.poke(isolate.GAP_ENTRY, expected[isolate.GAP_ENTRY].hex(), _branch(img, isolate.GAP_ENTRY, curve),
             'Digital strength -> PN1.30 display')
    for site in CURVE_CALLS:
        img.poke(site, expected[site].hex(), _call(img, site, curve),
                 'PN1.29 clipped-window helper -> PN1.30 display')
    tim1_code = _call(img, TIM1_SITE, tim1)
    img.poke(TIM1_SITE, TIM1_SITE_BYTES.hex(),
             tim1_code + bytes.fromhex('00bf') * ((len(TIM1_SITE_BYTES) - len(tim1_code)) // 2),
             'TIM1 1 ms tick: RECENT countdown (stock) + one gain decision per completed window')
    img.poke(version_tag.VERSION_STRING, expected[version_tag.VERSION_STRING].hex(), b'PN1.30\0\0',
             'Candidate identity PN1.30 (BOOTLOADER drive shows PN1.30.TXT)')
    img.version_tag = VERSION
    img.clean_strength = {**addresses, 'start': start, 'helper_bytes': len(body),
                          'last_decided': LAST_DECIDED, 'last_displayed': LAST_DISPLAYED,
                          'sat_pp': SAT_PP, 'sat_samples': SAT_SAMPLES,
                          'sites': (ESTIMATE_CALL, isolate.GAP_ENTRY, *CURVE_CALLS, TIM1_SITE,
                                    version_tag.VERSION_STRING),
                          'persistent_ram_bytes': 8}
    return img


def build_candidate():
    with contextlib.redirect_stdout(io.StringIO()):
        img = level_display.build_candidate()
    return apply(img)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--write', action='store_true', help='write the experimental raw/update images and sums')
    args = parser.parse_args(argv)
    img = build_candidate()
    artifacts = ((OUTPUT, bytes(img.data)), (UPDATE, wrap(img.data)))
    lines = [f'{hashlib.sha256(data).hexdigest()}  {name}' for name, data in artifacts]
    if args.write:
        DIRECTORY.mkdir(parents=True, exist_ok=True)
        for name, data in artifacts:
            (DIRECTORY / name).write_bytes(data)
        (DIRECTORY / SUMS).write_text('\n'.join(lines) + '\n', encoding='ascii')
        print(f'Wrote {VERSION} candidate files to {DIRECTORY}')
    else:
        print('Dry build; pass --write to create the experimental files.')
    for (_, data), line in zip(artifacts, lines):
        print(f'{len(data)} bytes: {line}')
    print(f"helpers {img.clean_strength['helper_bytes']} bytes at {img.clean_strength['start']:#x}")
    print('Copy the -update.bin with Explorer onto the BOOTLOADER drive; the drive then shows PN1.30.TXT.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
