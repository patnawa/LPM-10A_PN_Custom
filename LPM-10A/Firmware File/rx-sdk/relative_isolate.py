"""PN1.26 candidate: full sensitivity at every knob position, isolation relative to the strongest pair.

Owner's device test of PN1.25, 2026-09-23: "เสียงแรงขึ้น แต่ยังต้องหมุนจนผ่านกึ่งกลางถึงค่อยได้ยินเสียง"
(louder, but the knob still has to pass the middle before anything sounds).  PN1.25's lower half
raised an absolute floor, so an ordinary signal was silent there by design.

PN1.26 keeps PN1.25's louder beeps and NCV gain, and changes how the knob isolates:

* Digital and Analog always let the automatic gain use the full gain, at every knob position
  (the knob no longer selects a lower hardware gain).  Anything the detectors accept can sound
  anywhere above the stock gates (Digital >= 2, Analog >= 580 of 4095).
* The receiver keeps a peak: the strongest normalised strength heard recently.  It rises at once
  to any stronger reading and falls 2 dB per second of TIM5 time (250/256 every 100 ms); after 10 s
  without a detection it is forgotten.
* Upper half of the knob (reading >= 2048): Search, the PN1.24 rhythm, nothing muted.
* Lower half: Compare.  A reading weaker than peak x window is muted (published as rejected, so
  the existing release hold ends the rhythm).  The window narrows as the knob turns down:
  -36 dB just below the middle ... -6 dB at the bottom.  Readings inside the window are ranked
  against the peak: the peak plays the fastest rhythm (20 ms), the window edge the slowest (110 ms).
  One cable alone is its own peak, so it sounds at any knob position; among many pairs only those
  within the window of the strongest sound, the strongest fastest.
* A clipped window counts as score 40 000 at the driven gain in Compare (fastest in Search).
* Mains (NCV) keeps its stock analysis; its gain is the full gain from a quarter of the knob up
  (the knob's hardware step below) and always the knob's, also right after a tracing mode.
* Speaker duty 800 +- 300 (PN1.25; stock +- 100).

Detection and its thresholds, sampling, overlap, release hold, smoothing, sample-age guards and
the mode pitches are PN1.24's.  RAM: 8 bytes at 0x20000210 (peak, time of the last decay step),
inside the startup zero-init region, unused by PN1.24.

    python relative_isolate.py            dry build
    python relative_isolate.py --write    experimental/APP_LPM-10RX_PN1.26-relative*.bin + sums
"""
import argparse
import contextlib
import hashlib
import io
from pathlib import Path

import isolate
import rx_precision
from lpm10rx import symbols
from lpm10rx.container import wrap
from lpm10rx.image import PatchError
import version_tag

VERSION = 'PN1.26'
PARENT_SHA256 = isolate.PARENT_SHA256          # raw PN1.24
OUTPUT = 'APP_LPM-10RX_PN1.26-relative.bin'
UPDATE = 'APP_LPM-10RX_PN1.26-relative-update.bin'
SUMS = 'RX-PN1.26-SHA256SUMS.txt'
DIRECTORY = isolate.DIRECTORY

PEAK = 0x20000210                  # u32 peak strength, u32 TIM5 tick of the last decay step
TICK = 0x20000100                  # TIM5 40 kHz counter (sample_age_guard.TIMER_COUNTER)
ZERO_INIT = (0x20000018, 0x20001618)
STEP_TICKS = 4000                  # 100 ms of 25 us TIM5 ticks
DECAY = 250                        # x/256 per step: -0.21 dB per 100 ms, about -2 dB/s
STALE_TICKS = 400000               # 10 s without a detection: forget the peak
SEARCH_RAW = isolate.SEARCH_RAW    # 2048: upper half = Search
SEARCH_INDEX = isolate.SEARCH_INDEX
NCV_FULL_RAW = 1024                # mains: full gain from a quarter of the knob up
# Mute threshold as peak x window/256 at knob sixteenths 0..8, interpolated by the low byte:
# -6, -6.5, -8, -11, -15, -21, -28, -36 dB, then 0 (off) at the middle.
WINDOW = (128, 121, 102, 72, 45, 23, 10, 4, 0)
SATURATION_SCORE = isolate.SATURATION_SCORE
CLAMP = isolate.CLAMP

assert len(WINDOW) == SEARCH_INDEX + 1 and WINDOW[-1] == 0
assert all(a >= b for a, b in zip(WINDOW, WINDOW[1:])) and WINDOW[0] < 256
assert CLAMP * 256 < 1 << 32 and CLAMP * DECAY < 1 << 32


def window(knob):
    """Mute threshold x256 relative to the peak, or None in Search (the firmware's integer steps)."""
    i = knob >> 8
    if i >= SEARCH_INDEX:
        return None
    return WINDOW[i] - ((WINDOW[i] - WINDOW[i + 1]) * (knob & 0xFF) >> 8)


CURVE_TEMPLATE = f'''
    push {{r4, r5, r6, lr}}
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
    ldr r2, ={CLAMP:#x}
    cmp r0, r2
    bls clamped
    mov r0, r2                  ; keeps peak arithmetic inside 32 bits (far above fastest anyway)
clamped:
    mov r5, r0                  ; reading
    bl {{peak_now}}             ; r0 = peak decayed to now, r1 = unfinished ticks, r2 = now
    subs r2, r2, r1             ; keep the unfinished part of a step
    ldr r3, ={PEAK:#x}
    str r2, [r3, #4]
    cmp r5, r0
    bls kept
    mov r0, r5                  ; a stronger reading raises the peak at once
kept:
    str r0, [r3]
    mov r4, r0                  ; peak
    mov r0, r5                  ; reading
    ldr r1, ={isolate.KNOB:#x}
    ldrh r1, [r1]
    lsrs r2, r1, #8
    cmp r2, #{SEARCH_INDEX}
    bhs curve                   ; upper half: Search, the PN1.24 rhythm
    lsls r2, r2, #1
    ldr r3, =window
    add r3, r2
    ldrh r2, [r3]
    ldrh r3, [r3, #2]
    subs r3, r2, r3
    uxtb r1, r1
    muls r3, r1, r3
    lsrs r3, r3, #8
    subs r2, r2, r3             ; window x256 at this knob reading
    muls r2, r4, r2
    lsrs r2, r2, #8             ; mute threshold = peak x window
    cmp r0, r2
    bhs inside
    movs r1, #0
    bl {isolate.PUBLISH:#x}     ; weaker than the knob allows next to the peak: rejected
    movs r0, #0
    pop {{r4, r5, r6, pc}}
inside:
    subs r4, r4, r2             ; peak - threshold
    beq top
    subs r0, r0, r2             ; reading - threshold (<= peak - threshold)
    lsls r0, r0, #8
    udiv r0, r0, r4             ; 0..256 across the window
    ldr r1, ={SATURATION_SCORE}
    muls r0, r1, r0
    lsrs r0, r0, #8             ; window edge 0 .. peak 40 000
    b curve
top:
    ldr r0, ={SATURATION_SCORE}
curve:
    ldr r2, ={isolate.CURVE_TABLE:#x}
    mov r4, r0
    movs r5, #5
interval:
    ldrh r0, [r2]
    cmp r4, r0
    blo interpolate
    subs r4, r4, r0
    adds r2, #4
    subs r5, #1
    bne interval
    movs r1, #{isolate.FASTEST_MS}
    b filter
interpolate:
    ldrb r1, [r2, #2]
    ldrb r2, [r2, #3]
    subs r2, r1, r2
    muls r4, r2, r4
    udiv r4, r4, r0
    subs r1, r1, r4             ; r1 = target quiet interval
filter:
    ldr r2, ={isolate.STATE:#x}
    ldrh r0, [r2, #18]          ; RECENT
    movw r3, #500
    cmp r0, r3
    bls publish                 ; no fresh audio: take the target at once
    ldrb r0, [r2, #3]           ; published interval
    cmp r0, #1
    bls publish
    subs r2, r1, r0
    movs r3, #2
    sdiv r2, r2, r3             ; half step toward the target (PN 1.17)
    mov r3, r2
    cmp r3, #0
    bpl absolute
    rsbs r3, r3, #0
absolute:
    cmp r3, #3
    blo hold
    add r0, r2
    mov r1, r0
    b publish
hold:
    mov r1, r0
publish:
    bl {isolate.PUBLISH:#x}
    movs r0, #1
    pop {{r4, r5, r6, pc}}
    .align 4
window:
    .short {", ".join(str(w) for w in WINDOW)}
    .pool
'''


PEAK_NOW_SOURCE = f'''
    ldr r3, ={PEAK:#x}
    ldr r2, ={TICK:#x}
    ldr r2, [r2]                ; now
    ldr r1, [r3, #4]
    subs r1, r2, r1             ; ticks since the last decay step (wraps correctly)
    ldr r0, [r3]                ; stored peak
    ldr r3, ={STALE_TICKS}
    cmp r1, r3
    bls step
    movs r0, #0                 ; nothing heard for a long time: forget the peak
    movs r1, #0
step:
    ldr r3, ={STEP_TICKS}
    cmp r1, r3
    blo done
    subs r1, r1, r3
    movs r3, #{DECAY}
    muls r0, r3, r0
    lsrs r0, r0, #8             ; -0.2 dB per 100 ms
    b step
done:
    bx lr
    .pool
'''


def curve_source(peak_now):
    return CURVE_TEMPLATE.replace('{peak_now}', f'{peak_now:#x}')


# Levels the automatic gain can drive and the normalised strength each one saturates at
# (40 000 x the measured gain step): 7 -> 40 000, 2 -> 104 000, 1 -> 368 000, 0 -> 800 000.
CEILINGS = ((7, 40000), (2, 104000), (1, 368000))


def ceiling(peak, knob):
    """Tracing gain ceiling: full in Search; in Compare the highest level that still measures the mute threshold."""
    w = window(knob)
    if w is None:
        return 7
    threshold = peak * w >> 8
    return next((level for level, saturates in CEILINGS if saturates >= threshold), 0)


def gain_source(peak_now):
    checks = ''.join(f'''    movs r0, #{level}
    ldr r1, ={saturates}
    cmp r1, r4
    bhs tracing
''' for level, saturates in CEILINGS)
    return f'''
    ldr r3, ={isolate.MODE:#x}
    ldrb r3, [r3]
    cmp r3, #2
    beq mains
    ldr r1, ={isolate.KNOB:#x}
    ldrh r1, [r1]
    lsrs r2, r1, #8
    cmp r2, #{SEARCH_INDEX}
    bhs full                    ; upper half: the automatic gain may always use the full gain
    lsls r2, r2, #1
    ldr r3, =window
    add r3, r2
    ldrh r2, [r3]
    ldrh r3, [r3, #2]
    subs r3, r2, r3
    uxtb r1, r1
    muls r3, r1, r3
    lsrs r3, r3, #8
    subs r4, r2, r3             ; window x256
    bl {peak_now:#x}            ; r0 = peak decayed to now (read only: main owns the stored peak)
    muls r4, r0, r4
    lsrs r4, r4, #8             ; mute threshold
{checks}
    movs r0, #0                 ; highest gain whose saturation still reaches the mute threshold
    b tracing
full:
    movs r0, #7
tracing:
    ldr r2, ={isolate.DRIVEN:#x}
    ldrb r1, [r2, #3]           ; ceiling at the previous tick
    cmp r0, r1
    bhs agc                     ; unchanged or raised: PN1.24 (a raised ceiling is followed at once)
    ldrb r3, [r2]
    cmp r3, r0
    bhs agc                     ; lowered below the driven gain: PN1.24 follows it down at once
    strb r0, [r2, #3]
    movs r1, #0
    strb r1, [r2, #2]
    mov r0, r3                  ; lowered, but the gain is already lower: keep it
    mov r1, sp
    strb r0, [r1, #7]           ; gain_select_3bit's copy of the level
    b.w {isolate.GAIN_RESUME:#x}
mains:
    ldr r1, ={isolate.KNOB:#x}
    ldrh r1, [r1]
    movw r2, #{NCV_FULL_RAW}
    cmp r1, r2
    blo coded
    movs r0, #7                 ; NCV: full gain from a quarter of the knob up
coded:
    cmp r0, #3
    bne mapped
    movs r0, #2                 ; level 3 drives level 2's pattern (PN 1.17)
mapped:
    ldr r2, ={isolate.DRIVEN:#x}
    ldrb r3, [r2]
    cmp r3, r0
    beq agc
    movs r3, #0xFF
    strb r3, [r2, #3]           ; make PN1.24 take its knob-change path (invalidate, follow the knob)
agc:
    b.w {isolate.PN124_AGC:#x}
    .align 4
window:
    .short {", ".join(str(w) for w in WINDOW)}
    .pool
'''


def _branch(img, site, target):
    return img.assemble_at(site, f'b.w {target:#x}')


def apply(img):
    """Apply to the exact PN1.24 image; every site is checked before any byte changes."""
    if hashlib.sha256(bytes(img.data)).hexdigest() != PARENT_SHA256:
        raise PatchError('PN1.26 requires the exact PN1.24 image')
    expected = {
        isolate.GAP_ENTRY: _branch(img, isolate.GAP_ENTRY, isolate.OLD_CURVE),
        isolate.DIGITAL_UNCERTAIN: bytes.fromhex('012100e0'),
        isolate.ANALOG_SITE: isolate.ANALOG_SITE_BYTES,
        isolate.GAIN_SITE: _branch(img, isolate.GAIN_SITE, isolate.PN124_AGC),
        isolate.TONE_HIGH: bytes.fromhex('4ff46170'),    # mov.w r0, #900
        isolate.TONE_LOW: bytes.fromhex('4ff42f70'),     # mov.w r0, #700
        version_tag.VERSION_STRING: b'PN1.24\0\0',
    }
    for site, old in expected.items():
        if img.read(site, len(old)) != old:
            raise PatchError(f'PN1.26: unexpected code at {site:#x}')
    if img.read(isolate.MULT_TABLE, 8) != bytes([200, 92, 26, 26, 11, 11, 11, 10]):
        raise PatchError('PN1.26: gain-step table differs from PN1.24')
    table = b''.join(span.to_bytes(2, 'little') + bytes([a, b]) for span, a, b in isolate.LOCATE_SEGMENTS)
    if img.read(isolate.CURVE_TABLE, len(table)) != table:
        raise PatchError('PN1.26: PN1.24 curve table not found')
    for word in range(PEAK, PEAK + 8, 4):
        if word.to_bytes(4, 'little') in bytes(img.data):
            raise PatchError(f'PN1.26: {word:#x} is already referenced by the parent image')

    start = symbols.APP_BASE + len(img.data)
    body = bytearray()
    addresses = {}

    def append(name, source):
        address = start + len(body)
        code = img.assemble_at(address, source)
        body.extend(code)
        body.extend(bytes(-len(body) % 4))
        addresses[name] = address
        return address

    peak_now = append('peak_now', PEAK_NOW_SOURCE)
    curve = append('curve', curve_source(peak_now))
    digital = append('digital', isolate.digital_source(curve))
    analog = append('analog', isolate.analog_source(curve))
    gain = append('gain', gain_source(peak_now))
    if start + len(body) > symbols.EXTEND_LIMIT:
        raise PatchError('PN1.26 exceeds the application flash limit')

    img.extend(len(body), 'PN1.26: peak-relative curve, clipped-window and gain helpers')
    img.poke(start, bytes(len(body)).hex(), bytes(body),
             'Peak-relative knob window, Digital/Analog clipped windows, full tracing gain, NCV gain')
    img.poke(isolate.GAP_ENTRY, expected[isolate.GAP_ENTRY].hex(), _branch(img, isolate.GAP_ENTRY, curve),
             'Digital strength -> peak-relative curve (upper half identical to PN1.24)')
    img.poke(isolate.DIGITAL_UNCERTAIN, expected[isolate.DIGITAL_UNCERTAIN].hex(),
             _branch(img, isolate.DIGITAL_UNCERTAIN, digital),
             'Digital clipped window: fastest in Search, saturation score at the driven gain in Compare')
    analog_jump = _branch(img, isolate.ANALOG_SITE, analog)
    img.poke(isolate.ANALOG_SITE, isolate.ANALOG_SITE_BYTES.hex(),
             analog_jump + bytes.fromhex('00bf') * ((len(isolate.ANALOG_SITE_BYTES) - len(analog_jump)) // 2),
             'Analog score/clipped publication -> helper; a muted window skips the accepted refresh')
    img.poke(isolate.GAIN_SITE, expected[isolate.GAIN_SITE].hex(), _branch(img, isolate.GAIN_SITE, gain),
             'Tracing: full gain in Search, peak-derived ceiling in Compare; NCV: knob gain, full from a quarter up')
    img.poke(isolate.TONE_HIGH, expected[isolate.TONE_HIGH].hex(),
             img.assemble_at(isolate.TONE_HIGH, f'movw r0, #{isolate.SILENT_DUTY + isolate.TONE_SWING}'),
             'speaker tone duty 900 -> 1100 (louder beeps)')
    img.poke(isolate.TONE_LOW, expected[isolate.TONE_LOW].hex(),
             img.assemble_at(isolate.TONE_LOW, f'movw r0, #{isolate.SILENT_DUTY - isolate.TONE_SWING}'),
             'speaker tone duty 700 -> 500 (louder beeps)')
    img.poke(version_tag.VERSION_STRING, expected[version_tag.VERSION_STRING].hex(), b'PN1.26\0\0',
             'Candidate identity PN1.26 (BOOTLOADER drive shows PN1.26.TXT)')
    img.version_tag = VERSION
    img.relative_isolate = {
        **addresses, 'start': start, 'helper_bytes': len(body), 'peak': PEAK,
        'sites': (isolate.GAP_ENTRY, isolate.DIGITAL_UNCERTAIN, isolate.ANALOG_SITE, isolate.GAIN_SITE,
                  isolate.TONE_HIGH, isolate.TONE_LOW, version_tag.VERSION_STRING),
        'window': WINDOW, 'search_raw': SEARCH_RAW, 'ncv_full_raw': NCV_FULL_RAW,
        'persistent_ram_bytes': 8,
    }
    return img


def build_candidate():
    with contextlib.redirect_stdout(io.StringIO()):
        img = rx_precision.build_candidate()
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
    print(f"helpers {img.relative_isolate['helper_bytes']} bytes at {img.relative_isolate['start']:#x}")
    print('Copy the -update.bin with Explorer onto the BOOTLOADER drive; the drive then shows PN1.26.TXT.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
