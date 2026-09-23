"""PN1.25 candidate: a sensitivity knob that isolates one pair, louder beeps.

Two owner reports, 2026-09-23, with TX PN2.27A + RX PN1.24:

1. In a telephone PBX cabinet with many pairs the probe gave the same fast
   rhythm on every pair ("ดังไปหมด ระบุไม่ได้เลยว่าสายไหน").
2. The knob had to be turned almost half way before anything sounded, in
   Digital, Analog and NCV (mains).

Causes in the receiver firmware:

* Since PN 1.15 the rhythm reports strength normalised by the driven gain;
  PN 1.19 puts the fastest rhythm at the score the highest gain saturates at
  (40 000); PN 1.22 lets the automatic gain reach the lowest gain, which
  measures about 20 times further.  Every reading from 40 000 to about 800 000
  (26 dB) gets the same fastest rhythm, and turning the knob down only lowers
  the gain ceiling, which the normaliser cancels.
* The knob only chooses one of the three hardware gain steps (1/20, 1/9, 1/2.6
  of full below 57 % of travel), so the lower half is deaf for ordinary signals
  and does not rank strong ones either.
* Mains mode skips the automatic gain but keeps whatever level it last drove,
  so after tracing a strong tone NCV stays at the lowered gain until the knob
  moves.

PN1.25:

* Upper half of the knob (reading >= 2048): Search.  The full gain is always
  the ceiling (the automatic gain still steps down on saturation) and the rhythm
  is PN1.24's: everything the detectors accept sounds, 20 ms quiet interval at
  40 000 and above.  Sensitivity no longer depends on where in the upper half
  the knob sits.
* Lower half: Isolate.  The knob sets a reference.  Normalised strength x K,
  K = 1 at the middle falling 6 dB per sixteenth of travel to 1/64 at the bottom
  eighth (interpolated continuously).  A floor that rises from 0 at the middle
  to 7 200 below 3/8 mutes weaker readings: the window is published as
  rejected and the existing release hold ends the rhythm.  Between the floor
  and 40 000 the quiet interval is stretched over the whole PN1.24 curve
  (110 ... 20 ms), so the weakest audible pair is slow and the strongest fast.
  The gain ceiling there is the knob's hardware step as before, and turning the
  knob down never raises an automatically lowered gain.
* A clipped window counts as score 40 000 at the driven gain in Isolate
  (fastest in Search, as PN1.24).
* Mains (NCV): the driven gain always equals the knob's (full in the upper
  half), also right after switching from a tracing mode.
* Beeps are louder: the speaker duty swings 800 +- 300 instead of +- 100
  (3x the tone amplitude, about +9.5 dB) in every mode and for key beeps.

Detection and its thresholds, sampling, overlap, release hold, smoothing,
sample-age guards, the mains analysis and the mode pitches are PN1.24's.  No
RAM is added.  Physical selectivity is still set by how strongly the tone
couples into neighbouring pairs; firmware only makes strength comparable.

    python isolate.py            dry build (hashes only)
    python isolate.py --write    experimental/APP_LPM-10RX_PN1.25-isolate*.bin + sums
"""
import argparse
import contextlib
import hashlib
import io
from pathlib import Path

import auto_range
import rx_precision
import smooth_gain
from lpm10rx import symbols
from lpm10rx.container import wrap
from lpm10rx.image import PatchError
import version_tag

VERSION = 'PN1.25'
PARENT_SHA256 = '780951565cca543e50d38537cd179ee1793562c6a4642b688c8143b0e4d8b1ce'   # raw PN1.24
OUTPUT = 'APP_LPM-10RX_PN1.25-isolate.bin'
UPDATE = 'APP_LPM-10RX_PN1.25-isolate-update.bin'
SUMS = 'RX-PN1.25-SHA256SUMS.txt'
DIRECTORY = Path(__file__).resolve().parent.parent / 'experimental'

# RAM (all existing)
MODE = 0x20000048
KNOB = 0x20000068                  # u16 knob ADC reading 0..4095, published every 500 ms
DRIVEN = auto_range.STATE          # [0] driven gain level [1] 0 [2] hold [3] knob level last tick
STATE = smooth_gain.STATE          # 0x2000005A: +3 published interval, +18 RECENT

# Flash (PN1.24)
MULT_TABLE = smooth_gain.MULT_TABLE          # measured gain steps, tenths: 200 92 26 26 11 11 11 10
CURVE_TABLE = smooth_gain.CURVE_TABLE        # PN1.24 curve, five (u16 span, u8 from, u8 to)
PUBLISH = 0x08009F20                         # guarded publisher (sample age -> release hold -> rail map)
GAP_ENTRY = 0x0800A048                       # curve entry used by Digital: b.w PN 1.17 curve helper
OLD_CURVE = 0x0800CF28                       # PN 1.17 curve helper (normaliser reads the driven level)
DIGITAL_UNCERTAIN = 0x08009F08               # movs r1,#1 ; b publish (clipped / inseparable window)
DIGITAL_PUBLISH = 0x08009F0E                 # bl publish, then the analyser's epilogue
DIGITAL_DONE = 0x08009F12                    # analyser epilogue
ANALOG_SITE = 0x08009FB0                     # rail count test .. uncertain publication (24 bytes)
ANALOG_SITE_BYTES = bytes.fromhex('082a06d238460a3828214843'
                                  '00f044f802e00121fff7acff')
ANALOG_REFRESH = 0x08009FC8                  # accepted-window RECENT/countdown refresh
ANALOG_DONE = 0x08009FFE                     # common tail after a rejection
GAIN_SITE = smooth_gain.GAIN_SELECT_SITE     # gain_select_3bit: b.w PN1.24 automatic gain helper
GAIN_RESUME = smooth_gain.GAIN_SELECT_RESUME
PN124_AGC = 0x0800D244
TONE_HIGH, TONE_LOW = 0x08007528, 0x0800753E  # speaker_tick: mov.w r0,#900 / mov.w r0,#700

# Knob law
SEARCH_RAW = 2048                  # reading at or above: Search (upper half)
SEARCH_INDEX = SEARCH_RAW >> 8     # knob sixteenth where Search starts
# Reference K x 256 and floor (in referenced score) at each sixteenth 0..8, interpolated linearly by
# the low byte of the reading.  K halves per sixteenth (6 dB) below the middle, down to 1/64 at the
# bottom eighth; the floor opens gently below the middle and is 7 200 below 3/8 of travel.
KNOB_REFERENCE = (4, 4, 4, 8, 16, 32, 64, 128, 256)
KNOB_FLOOR = (7200, 7200, 7200, 7200, 7200, 7200, 2400, 450, 0)
SATURATION_SCORE = 40000           # highest-gain saturation score = PN1.24's fastest point
CLAMP = 0x00FFFFFF                 # keeps K x strength inside 32 bits (K <= 256)
LOCATE_SEGMENTS = ((800, 110, 95), (1600, 95, 85), (4800, 85, 70), (16800, 70, 45), (16000, 45, 20))
FASTEST_MS = 20
SILENT_DUTY, TONE_SWING = 800, 300 # stock swing is 100 (900/700)

assert len(KNOB_REFERENCE) == len(KNOB_FLOOR) == SEARCH_INDEX + 1
assert KNOB_REFERENCE[-1] == 256 and KNOB_FLOOR[-1] == 0
assert all(0 < a <= b for a, b in zip(KNOB_REFERENCE, KNOB_REFERENCE[1:]))
assert all(a >= b for a, b in zip(KNOB_FLOOR, KNOB_FLOOR[1:])) and max(KNOB_FLOOR) < SATURATION_SCORE
assert CLAMP * max(KNOB_REFERENCE) < 1 << 32
assert 0 < TONE_SWING < SILENT_DUTY


def knob_law(knob):
    """(K x 256, floor) for a knob reading, or None in Search -- the firmware's integer steps."""
    i = knob >> 8
    if i >= SEARCH_INDEX:
        return None
    f = knob & 0xFF
    k = KNOB_REFERENCE[i] + ((KNOB_REFERENCE[i + 1] - KNOB_REFERENCE[i]) * f >> 8)
    floor = KNOB_FLOOR[i] - ((KNOB_FLOOR[i] - KNOB_FLOOR[i + 1]) * f >> 8)
    return k, floor


FLOOR_OFFSET = 2 * len(KNOB_REFERENCE)

CURVE_SOURCE = f'''
    push {{r4, r5, r6, lr}}
    ldr r1, ={DRIVEN:#x}
    ldrh r1, [r1]
    cmp r1, #7
    bhi scaled
    ldr r2, ={MULT_TABLE:#x}
    add r2, r1
    ldrb r1, [r2]
    muls r0, r1, r0
    movs r1, #10
    udiv r0, r0, r1             ; strength at the probe tip (PN 1.15/1.17/1.22)
scaled:
    ldr r1, ={KNOB:#x}
    ldrh r1, [r1]
    lsrs r3, r1, #8             ; knob sixteenth
    cmp r3, #{SEARCH_INDEX}
    bhs curve                   ; upper half: Search, the PN1.24 rhythm
    lsls r3, r3, #1
    ldr r2, =knob_reference
    add r2, r3
    uxtb r1, r1                 ; position inside the sixteenth
    ldrh r3, [r2]
    ldrh r4, [r2, #2]
    subs r4, r4, r3
    muls r4, r1, r4
    lsrs r4, r4, #8
    adds r3, r3, r4             ; r3 = K x 256
    ldrh r4, [r2, #{FLOOR_OFFSET}]
    ldrh r5, [r2, #{FLOOR_OFFSET + 2}]
    subs r5, r4, r5
    muls r5, r1, r5
    lsrs r5, r5, #8
    subs r4, r4, r5             ; r4 = floor
    ldr r2, ={CLAMP:#x}
    cmp r0, r2
    bls fits
    mov r0, r2                  ; far above the fastest point in any case
fits:
    muls r0, r3, r0
    lsrs r0, r0, #8             ; strength against the knob's reference
    cmp r0, r4
    bhs audible
    movs r1, #0
    bl {PUBLISH:#x}             ; under the knob's floor: publish a rejected window
    movs r0, #0
    pop {{r4, r5, r6, pc}}
audible:
    ldr r2, ={SATURATION_SCORE}
    cmp r0, r2
    bhs curve                   ; fastest
    subs r0, r0, r4
    muls r0, r2, r0
    subs r2, r2, r4
    udiv r0, r0, r2             ; floor .. 40 000 stretched over the whole curve
curve:
    ldr r2, ={CURVE_TABLE:#x}
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
    movs r1, #{FASTEST_MS}
    b filter
interpolate:
    ldrb r1, [r2, #2]
    ldrb r2, [r2, #3]
    subs r2, r1, r2
    muls r4, r2, r4
    udiv r4, r4, r0
    subs r1, r1, r4             ; r1 = target quiet interval
filter:
    ldr r2, ={STATE:#x}
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
    bl {PUBLISH:#x}
    movs r0, #1
    pop {{r4, r5, r6, pc}}
    .align 4
knob_reference:
    .short {", ".join(str(k) for k in KNOB_REFERENCE)}
    .short {", ".join(str(k) for k in KNOB_FLOOR)}
    .pool
'''


def digital_source(curve):
    return f'''
    ldr r0, ={KNOB:#x}
    ldrh r0, [r0]
    lsrs r0, r0, #8
    cmp r0, #{SEARCH_INDEX}
    bhs search
    ldr r0, ={SATURATION_SCORE}  ; clipped: the saturation score at the driven gain
    bl {curve:#x}
    b.w {DIGITAL_DONE:#x}
search:
    movs r1, #1                 ; PN1.24: clipped sounds fastest
    b.w {DIGITAL_PUBLISH:#x}
    .pool
'''


def analog_source(curve):
    return f'''
    cmp r2, #8
    bhs clipped                 ; >= 8 of 64 samples on the upper rail
    mov r0, r7
    subs r0, #10
    movs r1, #40
    muls r0, r1, r0             ; (bin 17 above the noise - 10) x 40, as PN1.24
score:
    bl {curve:#x}
    cmp r0, #0
    bne accepted
    b.w {ANALOG_DONE:#x}        ; muted: rejection published, no accepted-window refresh
accepted:
    b.w {ANALOG_REFRESH:#x}
clipped:
    ldr r0, ={KNOB:#x}
    ldrh r0, [r0]
    lsrs r0, r0, #8
    cmp r0, #{SEARCH_INDEX}
    bhs search
    ldr r0, ={SATURATION_SCORE}
    b score
search:
    movs r1, #1
    bl {PUBLISH:#x}
    b.w {ANALOG_REFRESH:#x}
    .pool
'''


GAIN_SOURCE = f'''
    ldr r1, ={KNOB:#x}
    ldrh r1, [r1]
    movw r2, #{SEARCH_RAW}
    cmp r1, r2
    blo coded
    movs r0, #7                 ; upper half: the full gain is the ceiling
coded:
    cmp r0, #3
    bne mapped
    movs r0, #2                 ; level 3 drives level 2's pattern (PN 1.17)
mapped:
    ldr r2, ={DRIVEN:#x}
    ldr r3, ={MODE:#x}
    ldrb r3, [r3]
    cmp r3, #2
    bne tracing
    ldrb r3, [r2]               ; Mains has no automatic gain: drive the knob's gain
    cmp r3, r0
    beq agc
    movs r3, #0xFF
    strb r3, [r2, #3]           ; make PN1.24 take its knob-change path (invalidate, follow the knob)
    b agc
tracing:
    ldrb r1, [r2, #3]           ; knob level at the previous tick
    cmp r0, r1
    bhs agc                     ; unchanged or turned up: PN1.24
    ldrb r3, [r2]               ; driven level
    cmp r3, r0
    bhs agc                     ; at or above the new ceiling: PN1.24 follows the knob down
    strb r0, [r2, #3]
    movs r1, #0
    strb r1, [r2, #2]           ; a knob change clears the hold, as in PN1.24
    mov r0, r3                  ; turned down while the gain is already lower: keep it
    mov r1, sp
    strb r0, [r1, #7]           ; gain_select_3bit's copy of the level
    b.w {GAIN_RESUME:#x}
agc:
    b.w {PN124_AGC:#x}
    .pool
'''


def _branch(img, site, target):
    return img.assemble_at(site, f'b.w {target:#x}')


def apply(img):
    """Apply to the exact PN1.24 image; every site is checked before any byte changes."""
    if hashlib.sha256(bytes(img.data)).hexdigest() != PARENT_SHA256:
        raise PatchError('PN1.25 requires the exact PN1.24 image')
    expected = {
        GAP_ENTRY: _branch(img, GAP_ENTRY, OLD_CURVE),
        DIGITAL_UNCERTAIN: bytes.fromhex('012100e0'),
        ANALOG_SITE: ANALOG_SITE_BYTES,
        GAIN_SITE: _branch(img, GAIN_SITE, PN124_AGC),
        TONE_HIGH: bytes.fromhex('4ff46170'),    # mov.w r0, #900
        TONE_LOW: bytes.fromhex('4ff42f70'),     # mov.w r0, #700
        version_tag.VERSION_STRING: b'PN1.24\0\0',
    }
    for site, old in expected.items():
        if img.read(site, len(old)) != old:
            raise PatchError(f'PN1.25: unexpected code at {site:#x}')
    if img.read(MULT_TABLE, 8) != bytes([200, 92, 26, 26, 11, 11, 11, 10]):
        raise PatchError('PN1.25: gain-step table differs from PN1.24')
    locate = b''.join(span.to_bytes(2, 'little') + bytes([a, b]) for span, a, b in LOCATE_SEGMENTS)
    if img.read(CURVE_TABLE, len(locate)) != locate:
        raise PatchError('PN1.25: PN1.24 curve table not found')

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

    curve = append('curve', CURVE_SOURCE)
    digital = append('digital', digital_source(curve))
    analog = append('analog', analog_source(curve))
    gain = append('gain', GAIN_SOURCE)
    if start + len(body) > symbols.EXTEND_LIMIT:
        raise PatchError('PN1.25 exceeds the application flash limit')

    img.extend(len(body), 'PN1.25: knob law curve, clipped-window, gain-ceiling helpers')
    img.poke(start, bytes(len(body)).hex(), bytes(body),
             'Knob reference/floor curve, Digital/Analog clipped windows, gain ceiling and NCV gain')
    img.poke(GAP_ENTRY, expected[GAP_ENTRY].hex(), _branch(img, GAP_ENTRY, curve),
             'Digital strength -> knob-law curve (upper half identical to PN1.24)')
    img.poke(DIGITAL_UNCERTAIN, expected[DIGITAL_UNCERTAIN].hex(), _branch(img, DIGITAL_UNCERTAIN, digital),
             'Digital clipped window: fastest in Search, saturation score at the driven gain in Isolate')
    analog_jump = _branch(img, ANALOG_SITE, analog)
    img.poke(ANALOG_SITE, ANALOG_SITE_BYTES.hex(),
             analog_jump + bytes.fromhex('00bf') * ((len(ANALOG_SITE_BYTES) - len(analog_jump)) // 2),
             'Analog score/clipped publication -> helper; a muted window skips the accepted refresh')
    img.poke(GAIN_SITE, expected[GAIN_SITE].hex(), _branch(img, GAIN_SITE, gain),
             'Upper half: full gain ceiling; knob-down keeps a lowered gain; Mains drives the knob gain')
    img.poke(TONE_HIGH, expected[TONE_HIGH].hex(),
             img.assemble_at(TONE_HIGH, f'movw r0, #{SILENT_DUTY + TONE_SWING}'),
             f'speaker tone duty 900 -> {SILENT_DUTY + TONE_SWING} (louder beeps)')
    img.poke(TONE_LOW, expected[TONE_LOW].hex(),
             img.assemble_at(TONE_LOW, f'movw r0, #{SILENT_DUTY - TONE_SWING}'),
             f'speaker tone duty 700 -> {SILENT_DUTY - TONE_SWING} (louder beeps)')
    img.poke(version_tag.VERSION_STRING, expected[version_tag.VERSION_STRING].hex(), b'PN1.25\0\0',
             'Candidate identity PN1.25 (BOOTLOADER drive shows PN1.25.TXT)')
    img.version_tag = VERSION
    img.isolate = {
        **addresses, 'start': start, 'helper_bytes': len(body),
        'sites': (GAP_ENTRY, DIGITAL_UNCERTAIN, ANALOG_SITE, GAIN_SITE, TONE_HIGH, TONE_LOW,
                  version_tag.VERSION_STRING),
        'search_raw': SEARCH_RAW, 'knob_reference': KNOB_REFERENCE, 'knob_floor': KNOB_FLOOR,
        'tone_duty': (SILENT_DUTY + TONE_SWING, SILENT_DUTY - TONE_SWING),
        'persistent_ram_bytes': 0,
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
    print(f"helpers {img.isolate['helper_bytes']} bytes at {img.isolate['start']:#x}")
    print('Copy the -update.bin with Explorer onto the BOOTLOADER drive; the drive then shows PN1.25.TXT.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
