"""PN2.27 historical comparison: specialize the existing carrier GPIO transitions.

Standalone PN2.27 device testing is unconfirmed. The current TX release is
PN2.27A, which inherits this optimization and was owner-tested with RX PN1.24.

Keep PB13 then PA8 configuration writes, the existing OFF level/parity routine,
all other pin fields and the timer/carrier waveform. These two fixed-pin paths
do not need the general GPIO_Init pin-selection loops. No drive-strength,
slew, amplitude, modulation, UI or shared GPIO implementation changes.

The replacement fits the original routines, adds no RAM/flash allocation and
uses less stack. ON is a leaf; OFF tail-calls the unchanged vendor level helper.
All six direct callers discard the result/flags or overwrite them before use.
The existing RIGHT-key critical section/cache repair remains intact. Ordinary
port RMWs retain the parent's ownership assumptions; this does not make GPIO
port-wide read/modify/write atomic against arbitrary competing writers.
"""
import argparse
import contextlib
import hashlib
import io
from pathlib import Path

from lpm10a.image import PatchError
from lpm10a.thumb import assemble
import qc_display


VERSION = 'PN2.27'
PARENT_SHA256 = 'c77579f018bb820532b3c5974ae63fbf04c4e60359188f7e39a8a8f9a1533df8'
OUTPUT = Path(__file__).resolve().parent.parent / 'experimental' / 'LPM-10A-TX_PN2.27-tone-precision.bin'
OFF, ON, OFF_LEVEL = 0x0801A6B0, 0x0801A6EC, 0x0801A60C
EXPECTED = {
    OFF: '08b510208df8030003208df802004ff40050adf8000069460648fbf77ff94ff48070adf8000069460348fbf777f9fff795ff08bd000c014000080140',
    ON: '08b518208df8030003208df802004ff40050adf8000069460548fbf761f94ff48070adf8000069460248fbf759f908bd000c014000080140',
}


def _source(mode, tail):
    return f'''
        ldr r0, =0x40010C04
        ldr r1, [r0]
        movs r2, #15
        lsls r2, r2, #20
        bics r1, r2
        movs r2, #{mode}
        lsls r2, r2, #20
        orrs r1, r2
        str r1, [r0]           ; PB13 first, matching the vendor
        ldr r0, =0x40010804
        ldr r1, [r0]
        movs r2, #15
        bics r1, r2
        movs r2, #{mode}
        orrs r1, r2
        str r1, [r0]           ; PA8; preserve every other pin field
        {tail}
        .pool
    '''


def apply(img):
    """Apply only to exact finalized PN2.26; keep all other bytes/allocations."""
    img.finalize()
    if hashlib.sha256(bytes(img.data)).hexdigest() != PARENT_SHA256:
        raise PatchError('tone-precision requires the exact finalized PN2.26 parent')
    replacements = {}
    for site, mode, tail in ((OFF,3,f'b.w {OFF_LEVEL:#x}'), (ON,11,'bx lr')):
        old = bytes.fromhex(EXPECTED[site])
        if img.read(site, len(old)) != old:
            raise PatchError(f'tone-precision carrier entry differs at {site:#x}')
        code = assemble(site, _source(mode, tail))
        if len(code) > len(old) or len(code) % 2:
            raise PatchError(f'tone-precision exceeds carrier slot at {site:#x}')
        replacements[site] = (code, code+bytes.fromhex('00bf')*((len(old)-len(code))//2))
    parent_end, parent_ram = img.cave_ptr, tuple(img.ram_allocs)
    for site, (_, padded) in replacements.items():
        img.poke(site, EXPECTED[site], padded,
                 'Specialize carrier pin configuration; retain ordered writes and OFF parity')
    for site in (0x08011660,0x08012E6C):
        img.set_string(site, VERSION)
    img.tone_precision = dict(
        on=ON, off=OFF, off_level=OFF_LEVEL,
        code_bytes={site:len(code) for site,(code,_) in replacements.items()},
        slot_bytes={site:len(bytes.fromhex(old)) for site,old in EXPECTED.items()},
        direct_callers=(0x0801434C,0x0801457A,0x08014656,
                        0x0801466A,0x08014670,0x0801A666),
        parent_sha256=PARENT_SHA256, parent_end=parent_end, parent_ram=parent_ram,
        persistent_ram_bytes=0, additional_stack_bytes=0, added_flash_bytes=0,
    )
    return img


def build_candidate():
    return apply(qc_display.build_candidate()).finalize()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args(argv)
    with contextlib.redirect_stdout(io.StringIO()):
        img = build_candidate()
    data = bytes(img.data)
    digest = hashlib.sha256(data).hexdigest()
    print(f'{VERSION}: {len(data)} bytes; SHA256 {digest}')
    print(img.summary())
    if args.write:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_bytes(data)
        OUTPUT.with_name('TX-PN2.27-SHA256SUMS.txt').write_text(
            f'{digest}  {OUTPUT.name}\n', encoding='ascii')
        print(f'Wrote {OUTPUT}')
    else:
        print('Dry build; use --write to reproduce the historical comparison image.')
    print('Standalone PN2.27 device testing is unconfirmed. Current TX: PN2.27A, owner-tested with RX PN1.24.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
