"""PN2.27A Analog timing alignment, owner-tested with RX PN1.24.

The 101 us TIM2 interrupt and every shared timer client remain unchanged.
Analog uses a local phase accumulator: 33 cycles per 400 interrupts gives
816.831683 Hz at the audited nominal clock, with 6/7-tick half cycles and
50% duty. Digital and the PN2.27 carrier GPIO optimization are inherited.

Current TX release/default. On 2026-09-22 the owner reported test pass on
this exact image paired with RX PN1.24; no gain/range measurement was reported.
The original standalone output path is retained for reproducibility.
"""
import argparse
import contextlib
import hashlib
import io
from pathlib import Path

from lpm10a.image import PatchError
from lpm10a.thumb import assemble
import tone_precision


VERSION = 'PN2.27A'
PARENT_SHA256 = '575a410fea87da9bc4ecb273d1fd931712bb8a2d911d771c55332dc2a2c4e8b2'
OUTPUT = (Path(__file__).resolve().parent.parent / 'experimental' /
          'LPM-10A-TX_PN2.27A-analog-alignment.bin')
ANALOG_ENTRY = 0x08014344
PHASE_ADDRESS = 0x200000DE
LABEL_ADDRESS = 0x08068916
MODE_LABELS = ('Digital 454 kHz', 'Analog 817 Hz')
PARENT_END = 0x0806A558


def apply(img):
    # Check the finalized bytes before doing anything that can mutate img.
    # In particular, a second application or an unrelated profile must fail
    # without changing header fields, allocation cursors, strings or code.
    if hashlib.sha256(bytes(img.data)).hexdigest() != PARENT_SHA256:
        raise PatchError('tone-alignment requires the exact finalized PN2.27 parent')
    if img.cave_ptr != PARENT_END or img.payload_len != PARENT_END - 0x0800A000:
        raise PatchError('tone-alignment requires intact PN2.27 allocation metadata')
    guards = ((ANALOG_ENTRY, bytes.fromhex('7cb53e48')),
              (LABEL_ADDRESS, b'Analog 825 Hz\0'),
              (0x08011660, b'PN2.27\0\0'),
              (0x08012E6C, b'PN2.27\0\0'))
    for address, expected in guards:
        if img.read(address, len(expected)) != expected:
            raise PatchError(f'tone-alignment parent guard failed at {address:#x}')

    parent_ram = tuple(img.ram_allocs)
    # The original Analog-only halfword was a 0..1000 housekeeping counter.
    # Only this generator owned it; the existing enable/mode/Home handlers
    # preserve it. BSS startup initializes it to zero. Reuse keeps pause and
    # mode-switch phase continuity without allocating or initializing RAM.
    # Legacy flag/counter/output bytes at D2/E0/E1 become unused, untouched.
    # The accumulator is unsigned and bounded; corrupted values recover to
    # zero only on an enabled tick. Disabled entry preserves even a corrupt
    # phase and takes the same OFF path as the original generator.
    helper = img.emit_code(f'''
        push {{r4, lr}}
        ldr r0, =0x200000D0
        ldrb r0, [r0]
        cbnz r0, enabled
        bl 0x0801A6B0
        pop {{r4, pc}}
    enabled:
        ldr r4, ={PHASE_ADDRESS:#x}
        ldrh r0, [r4]
        movw r1, #2000
        cmp r0, r1
        blo valid
        movs r0, #0
    valid:
        adds r0, #165
        cmp r0, r1
        blo stored
        subs r0, r0, r1
    stored:
        strh r0, [r4]
        movw r1, #1000
        cmp r0, r1
        movs r0, #0
        blo output
        movs r0, #1
    output:
        bl 0x0801464C
        pop {{r4, pc}}
        .pool
    ''', why='Analog only: 165/2000 phase step at unchanged TIM2 cadence')
    img.poke(ANALOG_ENTRY, guards[0][1].hex(),
             assemble(ANALOG_ENTRY, f'b.w {helper}'),
             'Analog generator: use bounded local phase accumulator')
    # This shared ASCII drawer serves both languages. The replacement has
    # exactly the same length, so existing button geometry/centering stays.
    img.poke(LABEL_ADDRESS, guards[1][1].hex(), b'Analog 817 Hz\0',
             'Analog frequency label: rounded nominal 816.832 Hz, both languages')
    for address, expected in guards[2:]:
        img.poke(address, expected.hex(), VERSION.encode('ascii') + b'\0',
                 'Device-tested PN2.27A Analog-alignment release identity')
    img.tone_alignment = dict(parent_sha256=PARENT_SHA256,
                              parent_end=PARENT_END, parent_ram=parent_ram,
                              helper=helper, phase_address=PHASE_ADDRESS,
                              phase_step=165, phase_modulus=2000,
                              analog_entry=ANALOG_ENTRY,
                              label_address=LABEL_ADDRESS,
                              added_ram=0, helper_stack_bytes=8,
                              timer_tick_us=101)
    return img


def build_candidate():
    return apply(tone_precision.build_candidate()).finalize()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    with contextlib.redirect_stdout(io.StringIO()):
        img = build_candidate()
    data = bytes(img.data)
    digest = hashlib.sha256(data).hexdigest()
    print(f'{VERSION}: {len(data)} bytes; SHA256 {digest}')
    print(img.summary())
    if args.write:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_bytes(data)
        OUTPUT.with_name('TX-PN2.27A-SHA256SUMS.txt').write_text(
            f'{digest}  {OUTPUT.name}\n', encoding='ascii')
        print(f'Wrote {OUTPUT}')
    else:
        print('Dry build; use --write to reproduce the device-tested firmware.')
    print('Owner reported test pass with RX PN1.24, 2026-09-22. No measured gain/range claim.')


if __name__ == '__main__':
    main()
