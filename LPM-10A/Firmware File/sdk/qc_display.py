"""PN2.26: keep queued QC artwork from obscuring the Init prompt."""
import argparse
import contextlib
import hashlib
import io
from pathlib import Path

from lpm10a.image import PatchError
import qc_timing

VERSION = 'PN2.26'
PARENT_SHA256 = 'b6d407b662331bf4cf2fdb4f007a595cf75c61d31fa4986dea47d23aaf3c25ae'
OUTPUT = Path(__file__).resolve().parent.parent / 'experimental' / 'LPM-10A-TX_PN2.26-qc-display.bin'


def apply(img):
    img.finalize()
    if hashlib.sha256(bytes(img.data)).hexdigest() != PARENT_SHA256:
        raise PatchError('qc-display requires the exact finalized PN2.25 parent')
    parent_end, parent_ram = img.cave_ptr, tuple(img.ram_allocs)
    import qc_entry_display
    display = qc_entry_display.install(img)
    for site in (0x08011660, 0x08012E6C):
        img.set_string(site, VERSION)
    img.qc_display = dict(display=display, parent_end=parent_end, parent_ram=parent_ram)
    return img


def build_candidate():
    return apply(qc_timing.build_candidate()).finalize()


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
        OUTPUT.with_name('TX-PN2.26-SHA256SUMS.txt').write_text(
            f'{digest}  {OUTPUT.name}\n', encoding='ascii')
        print(f'Wrote {OUTPUT}')
    else:
        print('Dry build; use --write to emit the released update.')
    print('Owner reported all functions passed, 2026-09-22. If QC requests Init, disconnect every cable and hold Right.')


if __name__ == '__main__':
    main()
