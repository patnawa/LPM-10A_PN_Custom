"""PN2.25: QC count gates use measured elapsed time for Init and live scans."""
import argparse
import contextlib
import hashlib
import io
from pathlib import Path

from lpm10a.image import PatchError
import length_integrity

VERSION = 'PN2.25'
PARENT_SHA256 = 'b3716f6538f8980c075fb85e925cb2ba1d86e46440174d450615fa98253131e7'
OUTPUT = Path(__file__).resolve().parent.parent / 'experimental' / 'LPM-10A-TX_PN2.25-qc-timing.bin'


def apply(img):
    img.finalize()
    if hashlib.sha256(bytes(img.data)).hexdigest() != PARENT_SHA256:
        raise PatchError('qc-timing requires the exact finalized PN2.24 parent')
    parent_end, parent_ram = img.cave_ptr, tuple(img.ram_allocs)
    import qc_gate_clock
    import qc_baseline_epoch
    gate = qc_gate_clock.install(img)
    baseline = qc_baseline_epoch.install(img)
    for site in (0x08011660, 0x08012E6C):
        img.set_string(site, VERSION)
    img.qc_timing = dict(gate=gate, baseline=baseline,
                         parent_end=parent_end, parent_ram=parent_ram)
    return img


def build_candidate():
    return apply(length_integrity.build_candidate()).finalize()


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
        OUTPUT.with_name('TX-PN2.25-SHA256SUMS.txt').write_text(
            f'{digest}  {OUTPUT.name}\n', encoding='ascii')
        print(f'Wrote {OUTPUT}')
    else:
        print('Dry build; use --write to emit the experimental update.')
    print('New measurement timing: unplugged Init and physical QC validation are required.')


if __name__ == '__main__':
    main()
