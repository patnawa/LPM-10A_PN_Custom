"""LOCAL DIAGNOSTICS ONLY: isolate the owner's PN1.31 Analog dropout.

A (PN1.31A) adds only impulse_strength to exact PN1.30. It retains the old
publication semantics but has the new estimator's appended flash/stack use.
B (PN1.31B) adds only publication_commit. It retains the old Digital estimator
and raw/container length. Both use unique version labels and output names.

Neither is a fix or a promoted release. Hardware A/B results are pending.
No profile, latest selection, bootloader, or canonical release is changed.
The default run is dry; --write emits only four local diagnostic artifacts
and their dedicated checksum file under experimental/.
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


PARENT_SHA256 = '407b0ba3b80883e4f640ef7e2040a56004ca780a5bd8b81cf3a371ca04a67135'
DIRECTORY = clean_strength.DIRECTORY
SUMS = 'RX-PN1.31-ANALOG-DIAGNOSTIC-SHA256SUMS.txt'
VARIANTS = {
    'A': ('PN1.31A', 'APP_LPM-10RX_PN1.31A-impulse-only.bin'),
    'B': ('PN1.31B', 'APP_LPM-10RX_PN1.31B-publication-only.bin'),
}


def apply(img, variant):
    if variant not in VARIANTS:
        raise PatchError('Analog-drop diagnostic variant must be A or B')
    if hashlib.sha256(bytes(img.data)).hexdigest() != PARENT_SHA256:
        raise PatchError('Analog-drop diagnostics require the exact PN1.30 parent once')
    version, _ = VARIANTS[variant]
    if variant == 'A':
        impulse_strength.install(img)
    else:
        publication_commit.install(img)
    img.poke(version_tag.VERSION_STRING, b'PN1.30\0\0'.hex(), version.encode('ascii')+b'\0',
             f'LOCAL Analog-drop diagnostic {variant}; not a release or confirmed fix')
    img.version_tag = version
    img.analog_drop_ablation = {'variant': variant, 'parent_sha256': PARENT_SHA256,
                                'persistent_ram_bytes': 0, 'diagnostic_only': True}
    return img


def build_candidate(variant):
    with contextlib.redirect_stdout(io.StringIO()):
        img = clean_strength.build_candidate()
    return apply(img, variant)


def artifacts(variant, img):
    _, name = VARIANTS[variant]
    raw = bytes(img.data)
    return ((name, raw), (name[:-4]+'-update.bin', wrap(raw)))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true', help='write local A/B diagnostics, never promote a release')
    args = parser.parse_args(argv)
    files = [item for variant in VARIANTS for item in artifacts(variant, build_candidate(variant))]
    lines = [f'{hashlib.sha256(data).hexdigest()}  {name}' for name, data in files]
    if args.write:
        DIRECTORY.mkdir(parents=True, exist_ok=True)
        for name, data in files:
            (DIRECTORY/name).write_bytes(data)
        (DIRECTORY/SUMS).write_text('\n'.join(lines)+'\n', encoding='ascii')
        print(f'Wrote LOCAL diagnostic A/B artifacts to {DIRECTORY}')
    else:
        print('Dry build; --write emits LOCAL diagnostic A/B artifacts.')
    for (_, data), line in zip(files, lines):
        print(f'{len(data)} bytes: {line}')
    print('NOT A FIX OR RELEASE: owner Analog-drop A/B validation is pending.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
