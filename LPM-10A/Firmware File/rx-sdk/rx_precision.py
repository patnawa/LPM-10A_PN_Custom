"""PN1.24: RX gain response, Analog efficiency and sample freshness.

Build from the exact owner-tested PN1.23G parent. The owner confirmed PN1.24
passes on the device without Digital or Analog signal dropouts on 2026-09-22.
"""
import argparse
import contextlib
import hashlib
import io
from pathlib import Path

import digital_gain_continuity
from lpm10rx.container import wrap
from lpm10rx.image import PatchError
from lpm10rx import symbols
import version_tag

VERSION = 'PN1.24'
PARENT_SHA256 = 'a0822e2f454e08d0a213e63a1bbf0cac9948776dd8b067560d4786605b0307bb'
OUTPUT = 'APP_LPM-10RX_PN1.24-gain-precision.bin'
UPDATE = 'APP_LPM-10RX_PN1.24-gain-precision-update.bin'
DIRECTORY = Path(__file__).resolve().parent.parent / 'experimental'


def apply(img):
    if hashlib.sha256(bytes(img.data)).hexdigest() != PARENT_SHA256:
        raise PatchError('RX precision requires the exact PN1.23G parent')
    parent_size = len(img.data)
    import gain_response
    import analog_selective
    import sample_age_guard
    freshness = sample_age_guard.install(img)
    gain = gain_response.install(img)
    analog = analog_selective.install(img)
    img.poke(version_tag.VERSION_STRING, b'PN1.23G\0'.hex(), b'PN1.24\0\0',
             'Release identity PN1.24')
    img.version_tag = VERSION
    if symbols.APP_BASE + len(img.data) > 0x0801E000:
        raise PatchError('RX precision exceeds the application flash boundary')
    img.rx_precision = dict(gain=gain, analog=analog, freshness=freshness,
                            parent_size=parent_size)
    return img


def build_candidate():
    return apply(digital_gain_continuity.build_candidate())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args(argv)
    with contextlib.redirect_stdout(io.StringIO()):
        img = build_candidate()
    artifacts = ((OUTPUT, bytes(img.data)), (UPDATE, wrap(img.data)))
    lines = [f'{hashlib.sha256(data).hexdigest()}  {name}' for name, data in artifacts]
    if args.write:
        DIRECTORY.mkdir(parents=True, exist_ok=True)
        for name, data in artifacts:
            (DIRECTORY / name).write_bytes(data)
        (DIRECTORY / 'RX-PN1.24-SHA256SUMS.txt').write_text(
            '\n'.join(lines)+'\n', encoding='ascii')
    for (_, data), line in zip(artifacts, lines):
        print(f'{len(data)} bytes: {line}')
    print('Use the -update.bin file for the RX bootloader. Owner-confirmed Digital/Analog pass.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
