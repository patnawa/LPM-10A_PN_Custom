#!/usr/bin/env python3
"""
LPM-10A receiver firmware build tool.

    python build.py --list                 show available patches
    python build.py                        dry run with the default patch set
    python build.py --write                emit APP_LPM-10RX_PN1.0.bin
    python build.py --audit --write        emit the PN 1.5 audit candidate
    python build.py --only a,b --write     build a specific set
    python build.py --all --write          include patches marked untested

The stock image is FNIRSI's and is not in the repository; see
lpm10rx/image.py for where the tool looks for it.
"""
import argparse
import hashlib
import os
import sys
from itertools import zip_longest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from lpm10rx.image import Image, PatchError, STOCK_NAME   # noqa: E402
from lpm10rx import symbols as S                          # noqa: E402
import rx_patches as patches                               # noqa: E402
from audit_fixes import PATCHES as AUDIT_PATCHES            # noqa: E402

FW_DIR = os.path.dirname(HERE)
STOCK = os.path.join(FW_DIR, STOCK_NAME)
OUT = os.path.join(FW_DIR, "APP_LPM-10RX_PN1.0.bin")


def disasm(data, addr, n):
    from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_MCLASS
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS)
    o = addr - S.APP_BASE
    return [(i.address, i.bytes.hex(), f"{i.mnemonic} {i.op_str}".strip())
            for i in md.disasm(bytes(data[o:o + n]), addr)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--all", action="store_true", help="include risk=untested")
    ap.add_argument("--roadmap", action="store_true", help="build the PN 1.4 roadmap experiment")
    ap.add_argument("--audit", action="store_true", help="build PN 1.5 with sampler handoff and DFT overflow fixes")
    ap.add_argument("--only", help="comma-separated patch ids")
    ap.add_argument("--out", help="output path (experimental builds use a distinct filename)")
    args = ap.parse_args()
    if args.audit and (args.roadmap or args.all or args.only is not None):
        ap.error("--audit is a fixed profile; do not combine it with --roadmap, --all or --only")
    if args.roadmap and (args.all or args.only is not None):
        ap.error("--roadmap is a fixed profile; do not combine it with --all or --only")

    if args.list:
        print(f"{'id':24} {'risk':9} {'group':8} {'default':8} title")
        print("-" * 96)
        for p in patches.REGISTRY:
            print(f"{p.pid:24} {p.risk:9} {p.group:8} {'yes' if p.default else 'no':8} {p.title}")
        return 0

    if args.only is not None and (args.all or args.roadmap):
        ap.error("--only cannot be combined with --all or --roadmap")
    if args.only is not None:
        want = [x.strip() for x in args.only.split(",")]
        sel = [p for p in patches.REGISTRY if p.pid in want]
        missing = set(want) - {p.pid for p in sel}
        if missing:
            print(f"unknown patch id(s): {', '.join(sorted(missing))}")
            return 2
    else:
        sel = [p for p in patches.REGISTRY if p.default or args.all or
               ((args.roadmap or args.audit) and p.pid in patches.ROADMAP_PATCHES) or
               (args.audit and p.pid in AUDIT_PATCHES)]

    if not args.audit and any(p.pid in AUDIT_PATCHES for p in sel) and not args.out:
        ap.error("custom audit patch selections require --out; use --audit for PN 1.5")
    reliability = any(p.pid == "activity-before-autooff" for p in sel)
    experimental = reliability or any(p.pid == "digital-correlation" for p in sel)
    # A nonstandard subset must have an explicit name, not impersonate PN 1.2.
    if reliability and not args.roadmap and not args.audit and {p.pid for p in sel} != {"batt-critical-recover", "activity-before-autooff", "digital-correlation"} and not args.out:
        ap.error("the PN 1.2 candidate needs all three patches; give --out for a custom subset")
    name = patches.RELIABILITY_EXPERIMENT if reliability else patches.DIGITAL_EXPERIMENT
    if args.roadmap:
        name = patches.ROADMAP_EXPERIMENT
    if args.audit:
        from audit_fixes import OUTPUT
        name = OUTPUT
    out = args.out or (os.path.join(FW_DIR, name) if experimental else OUT)
    if experimental:
        print("EXPERIMENTAL V3.0.0-BASED RX IMAGE: bench validation and matching-device recovery required.")

    img = Image(STOCK)
    sha = hashlib.sha256(img.original).hexdigest()
    print(f"stock size  : {len(img.original)} bytes, load 0x{S.APP_BASE:08X}")
    print(f"sha256      : {sha}")
    if sha != S.STOCK_SHA256:
        print("\nREFUSING TO BUILD: this is not the V3.0.0 receiver image these patches were")
        print("written against.  Re-verify every patch site before changing STOCK_SHA256.")
        return 2

    print(f"\napplying {len(sel)} patch(es):")
    touched = []
    for p in sel:
        before = len(img.log)
        try:
            p(img)
        except PatchError as e:
            print(f"  [FAIL] {p.pid}: {e}")
            return 2
        print(f"  [{p.risk:8}] {p.pid:24} {p.title}")
        for addr, old, new, why, kind in img.log[before:]:
            if kind == "text":
                print(f"              0x{addr:08X}  \"{old.decode()}\" -> \"{new.decode()}\"")
            else:
                print(f"              0x{addr:08X}  {old.hex()} -> {new.hex()}   {why}")
                touched.append((addr, max(len(old), len(new))))

    print("\ninstruction-level verification (stock -> patched):")
    for addr, n in touched:
        a = disasm(img.original, addr, n)
        b = disasm(img.data, addr, n)
        print(f"  0x{addr:08X}")
        for (aa, ah, at), (ba, bh, bt) in zip_longest(a, b, fillvalue=(0, "", "")):
            mark = "  " if ah == bh else "->"
            print(f"    {mark} {ah:10} {at:30} | {bh:10} {bt}")
        if len(a) != len(b):
            print(f"    ({len(a)} instructions -> {len(b)})")

    d = img.diff_offsets()
    print(f"\nbytes changed : {len(d)}")
    print(f"file size     : {len(img.data)} (unchanged; raw image, no container)")

    if args.write:
        out_sha = img.save(out)
        print(f"\nwrote {out}")
        print(f"sha256 {out_sha}")
    else:
        print("\n(dry run -- pass --write to emit the file)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
