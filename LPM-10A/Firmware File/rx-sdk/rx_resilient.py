"""PN1.31: impulse-resistant Digital ranking and atomic feedback/gain handoff.

Built from the exact released PN1.30 image. The new Digital estimator retains
edge compensation and uses the full verified phase-fit snapshot for robust
triplet statistics. Exact-only fallback spans remain bounded to 16 samples.
The fast-gain eligibility marker is committed with accepted sound publication.
Validation executes the ARM firmware on modeled ADC/timer input; hardware
validation of PN1.31 is pending. No physical sensitivity or loudness gain is claimed.
"""
import argparse
import contextlib
import hashlib
import io

import clean_strength
import impulse_strength
import publication_commit
import version_tag
from lpm10rx.container import wrap
from lpm10rx.image import PatchError

VERSION = 'PN1.31'
PARENT_SHA256 = '407b0ba3b80883e4f640ef7e2040a56004ca780a5bd8b81cf3a371ca04a67135'
OUTPUT = 'APP_LPM-10RX_PN1.31-resilient.bin'
UPDATE = 'APP_LPM-10RX_PN1.31-resilient-update.bin'
SUMS = 'RX-PN1.31-SHA256SUMS.txt'
DIRECTORY = clean_strength.DIRECTORY


def apply(img):
    if hashlib.sha256(bytes(img.data)).hexdigest() != PARENT_SHA256:
        raise PatchError('PN1.31 requires the exact PN1.30 image')
    impulse_strength.install(img)
    publication_commit.install(img)
    img.poke(version_tag.VERSION_STRING, b'PN1.30\0\0'.hex(), b'PN1.31\0\0',
             'PN1.31 identity: robust strength and committed feedback')
    img.version_tag = VERSION
    img.resilient = {'sites': (*img.impulse_strength['sites'], *img.publication_commit['sites'],
                               version_tag.VERSION_STRING),
                     'persistent_ram_bytes': 0,
                     'helper_bytes': img.impulse_strength['helper_bytes']}
    return img


def build_candidate():
    with contextlib.redirect_stdout(io.StringIO()):
        img = clean_strength.build_candidate()
    return apply(img)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args(argv)
    img = build_candidate()
    artifacts = ((OUTPUT, bytes(img.data)), (UPDATE, wrap(img.data)))
    lines = [f'{hashlib.sha256(data).hexdigest()}  {name}' for name, data in artifacts]
    if args.write:
        DIRECTORY.mkdir(parents=True, exist_ok=True)
        for name, data in artifacts:
            (DIRECTORY / name).write_bytes(data)
        (DIRECTORY / SUMS).write_text('\n'.join(lines) + '\n', encoding='ascii')
        print(f'Wrote {VERSION} to {DIRECTORY}')
    else:
        print('Dry build; --write emits raw image, update container and hashes.')
    for (_, data), line in zip(artifacts, lines):
        print(f'{len(data)} bytes: {line}')
    print('Emulator validated; PN1.31 device validation pending.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
