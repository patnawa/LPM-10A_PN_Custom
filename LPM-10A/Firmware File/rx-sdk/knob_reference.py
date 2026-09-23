"""PN1.27 candidate: the knob sets the rhythm's reference over its whole travel.

Owner's device test of PN1.26, 2026-09-23: the tone is heard from 5-10 % (Digital) and
10-20 % (Analog), but "เสียง Rx แรงตลอด ตั้งแต่ 10% หมุนเพิ่ม ลด ไม่ต่าง" -- from 10 % up the
sound is always strong and turning the knob changes nothing.

Cause (test_rx_knob_response reproduces it on PN1.26): with one cable the probe's only
signal is also its remembered peak, and PN1.26's lower half ranked readings against that
peak, so a lone cable always played the fastest rhythm; its upper half is knob-independent
by design (full gain, gain-normalised rhythm).  Nothing in the chain followed the knob.

PN1.27 keeps everything PN1.26 got right (full gain at every knob position, the NCV gain,
the louder beep, the peak and its relative mute for bundles) and gives the knob an absolute
reference again, without muting:

* The normalised strength is multiplied by K before PN1.24's curve.  K is 1 on the top
  sixteenth of the knob (reading >= 3840: exactly PN1.24) and falls 2 dB per sixteenth,
  interpolated, to 1/32 (-30 dB) at the bottom.  Lower knob, slower rhythm for the same
  signal; nothing is muted by K, so a lone cable stays audible down to the stock gates.
* Lower half (reading < 2048): as PN1.26, a reading weaker than peak x window is muted
  (window -36 dB below the middle ... -6 dB at the bottom); the Compare gain ceiling keeps
  a reading that should sound out of saturation.  A lone cable is its own peak, never muted.
* A clipped window counts as score 40 000 at the driven gain, then K; on the top sixteenth
  it plays the fastest rhythm directly, as PN1.24.

    python knob_reference.py            dry build
    python knob_reference.py --write    experimental/APP_LPM-10RX_PN1.27-knob*.bin + sums
"""
import argparse
import contextlib
import hashlib
import io

import isolate
import relative_isolate as pn126
import rx_precision
from lpm10rx import symbols
from lpm10rx.container import wrap
from lpm10rx.image import PatchError
import version_tag

VERSION = 'PN1.27'
PARENT_SHA256 = isolate.PARENT_SHA256          # raw PN1.24
OUTPUT = 'APP_LPM-10RX_PN1.27-knob.bin'
UPDATE = 'APP_LPM-10RX_PN1.27-knob-update.bin'
SUMS = 'RX-PN1.27-SHA256SUMS.txt'
DIRECTORY = isolate.DIRECTORY

TOP_INDEX = 15                     # knob sixteenth 15 (reading >= 3840): K = 1, PN1.24 behaviour
# K x 256 at knob sixteenths 0..16 (16 closes the interpolation on the top sixteenth):
# 8 x 32^(i/15), about 2 dB per sixteenth from -30 dB at the bottom to 0 dB.
REFERENCE = (8, 10, 13, 16, 20, 25, 32, 40, 51, 64, 81, 102, 128, 161, 203, 256, 256)
PEAK = pn126.PEAK
SEARCH_INDEX = pn126.SEARCH_INDEX  # 8: the peak-relative mute stays in the lower half
SATURATION_SCORE = isolate.SATURATION_SCORE
CLAMP = isolate.CLAMP

assert len(REFERENCE) == 17 and REFERENCE[TOP_INDEX] == REFERENCE[16] == 256
assert all(0 < a <= b for a, b in zip(REFERENCE, REFERENCE[1:]))
assert CLAMP * 256 < 1 << 32


def reference(knob):
    """K x 256 for a knob reading (the firmware's integer steps)."""
    i = knob >> 8
    return REFERENCE[i] + ((REFERENCE[i + 1] - REFERENCE[i]) * (knob & 0xFF) >> 8)


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
    mov r0, r2                  ; keeps the arithmetic inside 32 bits (far above fastest anyway)
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
    bhs reference               ; upper half: nothing is muted
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
    bhs reference
    movs r1, #0
    bl {isolate.PUBLISH:#x}     ; clearly weaker than the strongest pair: rejected
    movs r0, #0
    pop {{r4, r5, r6, pc}}
reference:
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
    adds r2, r2, r3             ; K x 256
    muls r0, r2, r0
    lsrs r0, r0, #8             ; strength against the knob's reference
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
    .short {", ".join(str(w) for w in pn126.WINDOW)}
knob_reference:
    .short {", ".join(str(k) for k in REFERENCE)}
    .pool
'''


def curve_source(peak_now):
    return CURVE_TEMPLATE.replace('{peak_now}', f'{peak_now:#x}')


def digital_source(curve):
    return f'''
    ldr r0, ={isolate.KNOB:#x}
    ldrh r0, [r0]
    lsrs r0, r0, #8
    cmp r0, #{TOP_INDEX}
    bhs top
    ldr r0, ={SATURATION_SCORE}  ; clipped: the saturation score at the driven gain, then K
    bl {curve:#x}
    b.w {isolate.DIGITAL_DONE:#x}
top:
    movs r1, #1                 ; PN1.24: clipped sounds fastest
    b.w {isolate.DIGITAL_PUBLISH:#x}
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
    b.w {isolate.ANALOG_DONE:#x}  ; muted: rejection published, no accepted-window refresh
accepted:
    b.w {isolate.ANALOG_REFRESH:#x}
clipped:
    ldr r0, ={isolate.KNOB:#x}
    ldrh r0, [r0]
    lsrs r0, r0, #8
    cmp r0, #{TOP_INDEX}
    bhs top
    ldr r0, ={SATURATION_SCORE}
    b score
top:
    movs r1, #1
    bl {isolate.PUBLISH:#x}
    b.w {isolate.ANALOG_REFRESH:#x}
    .pool
'''


def _branch(img, site, target):
    return img.assemble_at(site, f'b.w {target:#x}')


def apply(img):
    """Apply to the exact PN1.24 image; every site is checked before any byte changes."""
    if hashlib.sha256(bytes(img.data)).hexdigest() != PARENT_SHA256:
        raise PatchError('PN1.27 requires the exact PN1.24 image')
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
            raise PatchError(f'PN1.27: unexpected code at {site:#x}')
    if img.read(isolate.MULT_TABLE, 8) != bytes([200, 92, 26, 26, 11, 11, 11, 10]):
        raise PatchError('PN1.27: gain-step table differs from PN1.24')
    table = b''.join(span.to_bytes(2, 'little') + bytes([a, b]) for span, a, b in isolate.LOCATE_SEGMENTS)
    if img.read(isolate.CURVE_TABLE, len(table)) != table:
        raise PatchError('PN1.27: PN1.24 curve table not found')
    for word in range(PEAK, PEAK + 8, 4):
        if word.to_bytes(4, 'little') in bytes(img.data):
            raise PatchError(f'PN1.27: {word:#x} is already referenced by the parent image')

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

    peak_now = append('peak_now', pn126.PEAK_NOW_SOURCE)
    curve = append('curve', curve_source(peak_now))
    digital = append('digital', digital_source(curve))
    analog = append('analog', analog_source(curve))
    gain = append('gain', pn126.gain_source(peak_now))
    if start + len(body) > symbols.EXTEND_LIMIT:
        raise PatchError('PN1.27 exceeds the application flash limit')

    img.extend(len(body), 'PN1.27: knob-reference curve, clipped-window and gain helpers')
    img.poke(start, bytes(len(body)).hex(), bytes(body),
             'Knob reference over the whole travel, peak-relative mute, clipped windows, gain and NCV')
    img.poke(isolate.GAP_ENTRY, expected[isolate.GAP_ENTRY].hex(), _branch(img, isolate.GAP_ENTRY, curve),
             'Digital strength -> knob-reference curve (top sixteenth identical to PN1.24)')
    img.poke(isolate.DIGITAL_UNCERTAIN, expected[isolate.DIGITAL_UNCERTAIN].hex(),
             _branch(img, isolate.DIGITAL_UNCERTAIN, digital),
             'Digital clipped window: fastest on the top sixteenth, else saturation score through the curve')
    analog_jump = _branch(img, isolate.ANALOG_SITE, analog)
    img.poke(isolate.ANALOG_SITE, isolate.ANALOG_SITE_BYTES.hex(),
             analog_jump + bytes.fromhex('00bf') * ((len(isolate.ANALOG_SITE_BYTES) - len(analog_jump)) // 2),
             'Analog score/clipped publication -> helper; a muted window skips the accepted refresh')
    img.poke(isolate.GAIN_SITE, expected[isolate.GAIN_SITE].hex(), _branch(img, isolate.GAIN_SITE, gain),
             'Tracing: full gain in the upper half, peak-derived ceiling below; NCV: knob gain, full from a quarter up')
    img.poke(isolate.TONE_HIGH, expected[isolate.TONE_HIGH].hex(),
             img.assemble_at(isolate.TONE_HIGH, f'movw r0, #{isolate.SILENT_DUTY + isolate.TONE_SWING}'),
             'speaker tone duty 900 -> 1100 (louder beeps)')
    img.poke(isolate.TONE_LOW, expected[isolate.TONE_LOW].hex(),
             img.assemble_at(isolate.TONE_LOW, f'movw r0, #{isolate.SILENT_DUTY - isolate.TONE_SWING}'),
             'speaker tone duty 700 -> 500 (louder beeps)')
    img.poke(version_tag.VERSION_STRING, expected[version_tag.VERSION_STRING].hex(), b'PN1.27\0\0',
             'Candidate identity PN1.27 (BOOTLOADER drive shows PN1.27.TXT)')
    img.version_tag = VERSION
    img.knob_reference = {
        **addresses, 'start': start, 'helper_bytes': len(body), 'peak': PEAK,
        'reference': REFERENCE, 'window': pn126.WINDOW, 'persistent_ram_bytes': 8,
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
    print(f"helpers {img.knob_reference['helper_bytes']} bytes at {img.knob_reference['start']:#x}")
    print('Copy the -update.bin with Explorer onto the BOOTLOADER drive; the drive then shows PN1.27.TXT.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
