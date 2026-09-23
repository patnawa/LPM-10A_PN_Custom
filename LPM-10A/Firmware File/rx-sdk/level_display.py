"""PN1.29 (release rx-v1.29, owner-tested 2026-09-23): an absolute, stepped strength display (IntelliTone-style), no memory.

Owner's device tests, 2026-09-23: PN1.27 "at full knob every pair sounds the same"; PN1.28
"detects, but not accurately" (worse than PN1.27); the owner has used a Fluke IntelliTone,
"more accurate than this", and needs to pick one pair out of a telephone cabinet.

What Fluke documents (IntelliTone Pro 200 manual, "Cable Toning Techniques" note): the probe
has no gain knob but a Locate / Isolate switch, and shows absolute strength on 8 LEDs; Isolate
is less sensitive with finer steps at the strong end, typically "a couple of LED levels" between
the toned jack and its neighbours. Nothing depends on what was probed before.

cabinet_scorecard.py (the real firmware, a toned pair and neighbours 3/6/10 dB weaker visited
in a fixed order at three contact strengths) shows why PN1.24-PN1.28 fail:
  1. The rhythm curve resolves about 15 dB at its fast end; contact strength varies over
     ~20 dB with pressure, so the knob position that separates the pairs moves with every touch.
  2. The front end saturates before the ADC rail; a first touch reads the saturation of the
     gain in use (a lower bound) until the automatic gain, one step per second, catches up.
  3. PN1.26-PN1.28 remember a peak, so the same pair sounds different depending on history.

PN1.29 (from the exact PN1.24 image; keeps PN1.25-1.27's louder beep and NCV gain law):
* Strength against the knob's reference K (PN1.27's law: 0 dB on the top sixteenth ... -30 dB)
  is shown as one of ten levels, 3 dB apart; each level's pulse period is 15 % longer than
  the next (Digital quiet interval 20, 27, 36, 46, 57, 71, 86, 103, 123, 146 ms). Nothing is
  muted; the same strength always gives the same level.
* While audio continues, a stronger window shows at once and a weaker one moves the shown strength
  an eighth of the way (about 0.3 s for a real 3 dB drop): the Digital estimate is steady but has
  single windows 3-6 dB low. A level changes only 0.5 dB past its boundary.
* Digital and Analog always allow the full gain (no peak, no Compare ceiling); after a gain step
  down the next 500 ms callback may decide again (step up keeps the one-callback hold).
* A clipped window counts as the saturation score at the driven gain, at every knob position.

    python level_display.py            dry build
    python level_display.py --write    experimental/APP_LPM-10RX_PN1.29-levels*.bin + sums
"""
import argparse
import contextlib
import hashlib
import io

import isolate
import knob_reference
import pair_rank
import rx_precision
from lpm10rx import symbols
from lpm10rx.container import wrap
from lpm10rx.image import PatchError
import version_tag

VERSION = 'PN1.29'
PARENT_SHA256 = isolate.PARENT_SHA256          # raw PN1.24
OUTPUT = 'APP_LPM-10RX_PN1.29-levels.bin'
UPDATE = 'APP_LPM-10RX_PN1.29-levels-update.bin'
SUMS = 'RX-PN1.29-SHA256SUMS.txt'
DIRECTORY = isolate.DIRECTORY

AVERAGE = 0x20000210               # u32 averaged strength, u8 current level at +4 (zero-init, unused by PN1.24)
LEVELS = 10
STEP_DB = 3
# Level k (1..9) from strength x K/256 >= THRESHOLDS[k-1]; level 9 at the curve's old fastest point.
THRESHOLDS = tuple(round(isolate.SATURATION_SCORE * 10 ** (-STEP_DB * (LEVELS - 1 - k) / 20))
                   for k in range(1, LEVELS))
# Quiet interval per level 0..9: pulse period (30 ms pulse + interval) 15 % longer per level down.
INTERVALS = tuple(round(50 * 1.15 ** (LEVELS - 1 - k)) - 30 for k in range(LEVELS))
NCV_FULL_RAW = 1024

assert THRESHOLDS == tuple(sorted(THRESHOLDS)) and len(INTERVALS) == LEVELS
assert INTERVALS[-1] == isolate.FASTEST_MS and all(a > b for a, b in zip(INTERVALS, INTERVALS[1:]))
assert isolate.CLAMP + (isolate.CLAMP >> 4) < 1 << 32


def count(value):
    """Level of a strength (number of thresholds at or below it)."""
    return sum(value >= t for t in THRESHOLDS)


def level(value, current, fresh):
    """The displayed level for an averaged strength: 0.5 dB hysteresis unless the audio is fresh."""
    if fresh or current >= LEVELS:
        return count(value)
    up, down = count(value - (value >> 4)), count(value + (value >> 4))
    if up > current:
        return up
    if down < current:
        return down
    return current


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
    ldr r5, ={AVERAGE:#x}
    ldr r4, ={isolate.STATE:#x}
    ldrh r1, [r4, #18]          ; RECENT
    movw r3, #500
    cmp r1, r3
    bls fresh
    ldrb r6, [r5, #4]           ; level on display
    cmp r6, #{LEVELS}
    bhs fresh
    ldr r1, [r5]
    cmp r0, r1
    bhs rise                    ; a stronger window shows at once
    subs r2, r1, r0
    lsrs r2, r2, #3
    subs r0, r1, r2             ; a weaker one moves an eighth of the way (Digital drops 3-6 dB in single windows)
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
    cmp r1, #{LEVELS - 1}
    blo next
counted:
    bx lr
    .align 4
thresholds:
    .word {", ".join(str(t) for t in THRESHOLDS)}
knob_reference:
    .short {", ".join(str(k) for k in knob_reference.REFERENCE)}
intervals:
    .byte {", ".join(str(i) for i in INTERVALS)}
    .align 2
    .pool
'''


def digital_source(curve):
    return f'''
    ldr r0, ={isolate.SATURATION_SCORE}  ; clipped: the saturation score at the driven gain
    bl {curve:#x}
    b.w {isolate.DIGITAL_DONE:#x}
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
    b score
clipped:
    ldr r0, ={isolate.SATURATION_SCORE}
score:
    bl {curve:#x}
    b.w {isolate.ANALOG_REFRESH:#x}
    .pool
'''


GAIN_SOURCE = f'''
    ldr r3, ={isolate.MODE:#x}
    ldrb r3, [r3]
    cmp r3, #2
    beq mains
    movs r0, #7                 ; tracing: the automatic gain may use the full gain at every knob position
    b agc
mains:
    ldr r1, ={isolate.KNOB:#x}
    ldrh r1, [r1]
    movw r2, #{NCV_FULL_RAW}
    cmp r1, r2
    blo coded
    movs r0, #7                 ; NCV: full gain from a quarter of the knob up (PN1.26)
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
    strb r3, [r2, #3]           ; make PN1.24 take its knob-change path
agc:
    b.w {isolate.PN124_AGC:#x}
    .pool
'''


def _branch(img, site, target):
    return img.assemble_at(site, f'b.w {target:#x}')


def apply(img):
    """Apply to the exact PN1.24 image; every site is checked before any byte changes."""
    if hashlib.sha256(bytes(img.data)).hexdigest() != PARENT_SHA256:
        raise PatchError('PN1.29 requires the exact PN1.24 image')
    expected = {
        isolate.GAP_ENTRY: _branch(img, isolate.GAP_ENTRY, isolate.OLD_CURVE),
        isolate.DIGITAL_UNCERTAIN: bytes.fromhex('012100e0'),
        isolate.ANALOG_SITE: isolate.ANALOG_SITE_BYTES,
        isolate.GAIN_SITE: _branch(img, isolate.GAIN_SITE, isolate.PN124_AGC),
        pair_rank.AGC_SITE: pair_rank.AGC_SITE_BYTES + pair_rank.AGC_FOLLOWS,
        isolate.TONE_HIGH: bytes.fromhex('4ff46170'),    # mov.w r0, #900
        isolate.TONE_LOW: bytes.fromhex('4ff42f70'),     # mov.w r0, #700
        version_tag.VERSION_STRING: b'PN1.24\0\0',
    }
    for site, old in expected.items():
        if img.read(site, len(old)) != old:
            raise PatchError(f'PN1.29: unexpected code at {site:#x}')
    if img.read(isolate.MULT_TABLE, 8) != bytes([200, 92, 26, 26, 11, 11, 11, 10]):
        raise PatchError('PN1.29: gain-step table differs from PN1.24')
    for word in range(AVERAGE, AVERAGE + 8, 4):
        if word.to_bytes(4, 'little') in bytes(img.data):
            raise PatchError(f'PN1.29: {word:#x} is already referenced by the parent image')

    start = symbols.APP_BASE + len(img.data)
    body = bytearray()
    addresses = {}

    def append(name, source):
        address = start + len(body)
        body.extend(img.assemble_at(address, source))
        body.extend(bytes(-len(body) % 4))
        addresses[name] = address
        return address

    curve = append('curve', CURVE_TEMPLATE)
    digital = append('digital', digital_source(curve))
    analog = append('analog', analog_source(curve))
    gain = append('gain', GAIN_SOURCE)
    attack = append('attack', pair_rank.ATTACK_SOURCE)
    if start + len(body) > symbols.EXTEND_LIMIT:
        raise PatchError('PN1.29 exceeds the application flash limit')

    img.extend(len(body), 'PN1.29: stepped strength display, gain and fast-attack helpers')
    img.poke(start, bytes(len(body)).hex(), bytes(body),
             'Ten absolute strength levels against the knob reference; full gain; fast attack')
    img.poke(isolate.GAP_ENTRY, expected[isolate.GAP_ENTRY].hex(), _branch(img, isolate.GAP_ENTRY, curve),
             'Digital strength -> stepped display')
    img.poke(isolate.DIGITAL_UNCERTAIN, expected[isolate.DIGITAL_UNCERTAIN].hex(),
             _branch(img, isolate.DIGITAL_UNCERTAIN, digital),
             'Digital clipped window: saturation score at the driven gain through the display')
    analog_jump = _branch(img, isolate.ANALOG_SITE, analog)
    img.poke(isolate.ANALOG_SITE, isolate.ANALOG_SITE_BYTES.hex(),
             analog_jump + bytes.fromhex('00bf') * ((len(isolate.ANALOG_SITE_BYTES) - len(analog_jump)) // 2),
             'Analog score/clipped publication -> stepped display')
    img.poke(isolate.GAIN_SITE, expected[isolate.GAIN_SITE].hex(), _branch(img, isolate.GAIN_SITE, gain),
             'Tracing: full gain at every knob; NCV: knob gain, full from a quarter up')
    img.poke(pair_rank.AGC_SITE, pair_rank.AGC_SITE_BYTES.hex(), img.assemble_at(pair_rank.AGC_SITE, f'bl {attack:#x}'),
             'PN1.24 AGC: no hold after a step down')
    img.poke(isolate.TONE_HIGH, expected[isolate.TONE_HIGH].hex(),
             img.assemble_at(isolate.TONE_HIGH, f'movw r0, #{isolate.SILENT_DUTY + isolate.TONE_SWING}'),
             'speaker tone duty 900 -> 1100 (louder beeps)')
    img.poke(isolate.TONE_LOW, expected[isolate.TONE_LOW].hex(),
             img.assemble_at(isolate.TONE_LOW, f'movw r0, #{isolate.SILENT_DUTY - isolate.TONE_SWING}'),
             'speaker tone duty 700 -> 500 (louder beeps)')
    img.poke(version_tag.VERSION_STRING, expected[version_tag.VERSION_STRING].hex(), b'PN1.29\0\0',
             'Candidate identity PN1.29 (BOOTLOADER drive shows PN1.29.TXT)')
    img.version_tag = VERSION
    img.level_display = {**addresses, 'start': start, 'helper_bytes': len(body), 'average': AVERAGE,
                         'thresholds': THRESHOLDS, 'intervals': INTERVALS, 'persistent_ram_bytes': 5}
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
    print(f"helpers {img.level_display['helper_bytes']} bytes at {img.level_display['start']:#x}")
    print('Copy the -update.bin with Explorer onto the BOOTLOADER drive; the drive then shows PN1.29.TXT.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
