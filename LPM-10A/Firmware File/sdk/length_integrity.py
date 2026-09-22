"""PN2.24: Length lifecycle/REF/progress and QC idle-noise correction.

Build with ``python length_integrity.py --write`` on the exact PN2.23R parent.
The previous QC screen and all historical experimental builders are retained.
"""
import argparse
import contextlib
import hashlib
import io
from pathlib import Path

from lpm10a.image import PatchError
import qc_classic

VERSION = 'PN2.24'
PARENT_SHA256 = 'cd94672633420a44e9bf9232de87adcc794cc57068035a260ffb6e4ffa35e8b4'
OUTPUT = Path(__file__).resolve().parent.parent / 'experimental' / 'LPM-10A-TX_PN2.24-length-qc.bin'


def apply(img):
    img.finalize()
    if hashlib.sha256(bytes(img.data)).hexdigest() != PARENT_SHA256:
        raise PatchError('length-integrity requires the exact finalized PN2.23R parent')
    parent_end, parent_ram = img.cave_ptr, tuple(img.ram_allocs)
    import length_reference_guard
    import length_progress_quiet
    import length_lifecycle
    import qc_idle_filter
    import length_message_guard
    reference = length_reference_guard.install(img)
    progress = length_progress_quiet.install(img)
    qc_idle_filter.install(img)
    lifecycle = length_lifecycle.install(img)
    messages = length_message_guard.install(img)
    for site in (0x08011660, 0x08012E6C):
        img.set_string(site, VERSION)
    img.length_integrity = dict(reference=reference, progress=progress, lifecycle=lifecycle,
                                qc_filter=img.qc_idle_filter, messages=messages,
                                parent_end=parent_end, parent_ram=parent_ram)
    return img


def build_candidate():
    return apply(qc_classic.build_candidate()).finalize()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--write', action='store_true')
    args = ap.parse_args()
    with contextlib.redirect_stdout(io.StringIO()):
        img = build_candidate()
    data = bytes(img.data)
    digest = hashlib.sha256(data).hexdigest()
    print(f'{VERSION}: {len(data)} bytes; SHA256 {digest}')
    print(img.summary())
    if args.write:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_bytes(data)
        OUTPUT.with_name('TX-PN2.24-SHA256SUMS.txt').write_text(
            f'{digest}  {OUTPUT.name}\n', encoding='ascii')
        print(f'Wrote {OUTPUT}')
    else:
        print('Dry build; use --write to emit the experimental update file.')
    print('CPU/display emulation checks do not replace a physical cable test.')


if __name__ == '__main__':
    main()
