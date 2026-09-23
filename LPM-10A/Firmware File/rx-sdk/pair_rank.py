"""PN1.28 candidate: the strongest recent pair lands on the fastest rhythm point.

Owner's device test of PN1.27, 2026-09-23: "พอเร่งสุดเหมือนหาสายไม่แม่น ดังทั่วไปหมด ไม่แม่นยำในการ
identify สาย" -- with the knob turned all the way up, every pair of a bundle sounds the same
and the toned pair cannot be picked out.

Cause (test_rx_pair_identify reproduces it on PN1.27): the rhythm curve's fastest point is
score 40 000, the full gain's saturation.  On the top of the knob the knob's reference K is 1,
and a pair touched after the automatic gain has stepped down reads up to 26 dB above that, so
the toned pair and every neighbour within about 10 dB of it are clamped to the same 20 ms.
Lower on the knob K brings the same readings back into the curve, and they rank.

PN1.28 is PN1.27 with two changes:

* Curve: the reference is the smaller of K and 40 000 / peak, where the peak is the
  strongest normalised strength heard recently (PN1.26: instant rise, -2 dB/s, forgotten
  after 10 s).  When the peak fits the curve at the knob's reference nothing changes.  When
  it would pass the fastest point, the curve slides so that the peak lands exactly on it and
  weaker pairs play slower by their dB deficit.  A lone cable is its own peak, so its rhythm
  at every knob position is PN1.27's.
* Fast attack: the front end saturates at about 2 400 counts p-p, before the ADC rail, so a
  window read at too high a gain is not flagged as clipped: it reads the saturation of that
  gain, a lower bound.  PN1.24 steps the gain down one level per second (one 500 ms callback
  held after every change), so a strong toned pair touched for about a second was never
  measured unsaturated, and the first neighbour touched after it became the peak and played
  fastest.  After a step down the next callback may decide again (its freshness guard still
  requires a complete window at the new gain); a step up keeps PN1.24's one-callback hold.

    python pair_rank.py            dry build
    python pair_rank.py --write    experimental/APP_LPM-10RX_PN1.28-pair-rank*.bin + sums
"""
import argparse
import contextlib
import hashlib
import io

import knob_reference
from lpm10rx import symbols
from lpm10rx.container import wrap
from lpm10rx.image import PatchError
import version_tag

VERSION = 'PN1.28'
PARENT_SHA256 = 'febd648daa98b51cf06c35e855afa4a088bb789c8ae643acf42b0f828c081c83'   # raw PN1.27
OUTPUT = 'APP_LPM-10RX_PN1.28-pair-rank.bin'
UPDATE = 'APP_LPM-10RX_PN1.28-pair-rank-update.bin'
SUMS = 'RX-PN1.28-SHA256SUMS.txt'
DIRECTORY = knob_reference.DIRECTORY

FASTEST_SCORE = 40000              # the curve's fastest point (PN 1.19)
SITE = 0x0800D400                  # PN1.27 curve: 'adds r2, r2, r3; muls r0, r2, r0' (K x 256, then x strength)
SITE_BYTES = bytes.fromhex('d2185043')
FOLLOWS = bytes.fromhex('000a')    # lsrs r0, r0, #8

SCALE_SOURCE = f'''
    adds r2, r2, r3             ; K x 256 (the instruction this call replaces)
    ldr r3, ={FASTEST_SCORE}
    cmp r4, r3
    bls knob                    ; the strongest recent pair fits the curve: the knob's reference alone
    ldr r3, ={FASTEST_SCORE * 256 - 1}
    adds r3, r3, r4
    udiv r3, r3, r4             ; ceil(40 000 x 256 / peak): the peak lands on the fastest point
    cmp r3, r2
    bhs knob
    mov r2, r3
knob:
    muls r0, r2, r0             ; the instruction this call replaces
    bx lr
    .pool
'''

AGC_SITE = 0x0800D30A              # PN1.24 AGC after a step: 'strb r3, [r2]; movs r1, #1' (level, then hold 1)
AGC_SITE_BYTES = bytes.fromhex('13700121')
AGC_FOLLOWS = bytes.fromhex('9170')  # strb r1, [r2, #2]: the hold

ATTACK_SOURCE = '''
    ldrb r1, [r2]               ; the level before this step
    strb r3, [r2]               ; the new level (the instruction this call replaces)
    cmp r3, r1
    bhs release
    movs r1, #0                 ; stepped down: the next callback may decide again
    bx lr
release:
    movs r1, #1                 ; stepped up: hold one callback (PN1.24)
    bx lr
'''

assert knob_reference.CLAMP + FASTEST_SCORE * 256 < 1 << 32


def reference(knob, peak):
    """The curve's reference x256 for a knob reading and the stored peak (the firmware's integer steps)."""
    k = knob_reference.reference(knob)
    if peak <= FASTEST_SCORE:
        return k
    return min(k, (FASTEST_SCORE * 256 + peak - 1) // peak)


def apply(img):
    """Apply to the exact PN1.27 image; both sites are checked before any byte changes."""
    if hashlib.sha256(bytes(img.data)).hexdigest() != PARENT_SHA256:
        raise PatchError('PN1.28 requires the exact PN1.27 image')
    if img.read(SITE, 6) != SITE_BYTES + FOLLOWS:
        raise PatchError(f'PN1.28: unexpected code at {SITE:#x}')
    if img.read(AGC_SITE, 6) != AGC_SITE_BYTES + AGC_FOLLOWS:
        raise PatchError(f'PN1.28: unexpected code at {AGC_SITE:#x}')
    if img.read(version_tag.VERSION_STRING, 8) != b'PN1.27\0\0':
        raise PatchError('PN1.28: parent is not tagged PN1.27')

    start = symbols.APP_BASE + len(img.data)
    body = bytearray()
    addresses = {}

    def append(name, source):
        address = start + len(body)
        body.extend(img.assemble_at(address, source))
        body.extend(bytes(-len(body) % 4))
        addresses[name] = address
        return address

    scale = append('scale', SCALE_SOURCE)
    attack = append('attack', ATTACK_SOURCE)
    if start + len(body) > symbols.EXTEND_LIMIT:
        raise PatchError('PN1.28 exceeds the application flash limit')

    img.extend(len(body), 'PN1.28: pair-rank reference and fast-attack helpers')
    img.poke(start, bytes(len(body)).hex(), bytes(body),
             'Reference = min(knob reference, 40 000 / peak); no hold after a gain step down')
    img.poke(SITE, SITE_BYTES.hex(), img.assemble_at(SITE, f'bl {scale:#x}'),
             'PN1.27 curve: the reference multiply goes through the pair-rank helper')
    img.poke(AGC_SITE, AGC_SITE_BYTES.hex(), img.assemble_at(AGC_SITE, f'bl {attack:#x}'),
             'PN1.24 AGC: the hold after a step comes from the fast-attack helper')
    img.poke(version_tag.VERSION_STRING, b'PN1.27\0\0'.hex(), b'PN1.28\0\0',
             'Candidate identity PN1.28 (BOOTLOADER drive shows PN1.28.TXT)')
    img.version_tag = VERSION
    img.pair_rank = {**addresses, 'start': start, 'helper_bytes': len(body)}
    return img


def build_candidate():
    with contextlib.redirect_stdout(io.StringIO()):
        img = knob_reference.build_candidate()
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
    print(f"helpers {img.pair_rank['helper_bytes']} bytes at {img.pair_rank['start']:#x}")
    print('Copy the -update.bin with Explorer onto the BOOTLOADER drive; the drive then shows PN1.28.TXT.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
