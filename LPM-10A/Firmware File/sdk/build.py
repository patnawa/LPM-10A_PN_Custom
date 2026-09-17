#!/usr/bin/env python3
"""
LPM-10A firmware build tool.

    python build.py --list                 show available patches
    python build.py                        dry run with the default patch set
    python build.py --write                emit LPM-10A-TX_PN1.0.bin
    python build.py --only a,b --write     build a specific set
    python build.py --all --write          include patches marked untested

Every build re-disassembles the result and diffs it against the stock image,
so the exact instruction-level change is printed before anything is written.
"""
import argparse
import os
import sys
import hashlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from lpm10a.image import Image, PatchError          # noqa: E402
from lpm10a import symbols as S                     # noqa: E402
import patches                                       # noqa: E402

FW_DIR = os.path.dirname(HERE)
STOCK = os.path.join(FW_DIR, "LPM-10A-TX_V2.0.7_260610.bin")
STOCK_SHA = "29081ccbbd929a884c7c81fb309aa2894ce2ab84e061918538b3ead8e632940b"
OUT = os.path.join(FW_DIR, "LPM-10A-TX_PN1.0.bin")


def disasm_region(data, payload_off, addr, n):
    from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_MCLASS
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS)
    o = addr - S.APP_BASE + payload_off
    return [(i.address, i.bytes.hex(), f"{i.mnemonic} {i.op_str}".strip())
            for i in md.disasm(bytes(data[o:o + n]), addr)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--all", action="store_true", help="include risk=untested")
    ap.add_argument("--only", help="comma-separated patch ids")
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()

    if args.list:
        print(f"{'id':22} {'risk':9} {'group':8} {'default':8} title")
        print("-" * 96)
        for p in patches.REGISTRY:
            print(f"{p.pid:22} {p.risk:9} {p.group:8} "
                  f"{'yes' if p.default else 'no':8} {p.title}")
        return 0

    # ---- select patches
    if args.only:
        want = [x.strip() for x in args.only.split(",")]
        sel = [p for p in patches.REGISTRY if p.pid in want]
        missing = set(want) - {p.pid for p in sel}
        if missing:
            print(f"unknown patch id(s): {', '.join(sorted(missing))}")
            return 2
    else:
        sel = [p for p in patches.REGISTRY if p.default or args.all]

    # ---- load and check provenance
    img = Image(STOCK)
    sha = hashlib.sha256(img.original).hexdigest()
    print(f"stock name  : {img.name}")
    print(f"sha256      : {sha}")
    if sha != STOCK_SHA:
        print("\nREFUSING TO BUILD: this is not the V2.0.7 image these patches were")
        print("written against.  Re-verify every patch site before changing STOCK_SHA.")
        return 2
    print(f"{img.summary().splitlines()[2]}\n")

    # ---- apply
    print(f"applying {len(sel)} patch(es):")
    touched = []
    for p in sel:
        before = len(img.log)
        try:
            p(img)
        except PatchError as e:
            print(f"  [FAIL] {p.pid}: {e}")
            return 2
        edits = img.log[before:]
        print(f"  [{p.risk:8}] {p.pid:22} {p.title}")
        for addr, old, new, why, kind in edits:
            if kind == "text":
                print(f"              0x{addr:08X}  \"{old.decode()}\" -> \"{new.decode()}\"")
            elif kind == "blob":
                print(f"              0x{addr:08X}  {len(new)} bytes replaced   {why}")
            else:
                print(f"              0x{addr:08X}  {old.hex() or '(new)'} -> {new.hex()}   {why}")
                touched.append(addr)

    img.finalize()

    # ---- verification: show the CPU's view of every changed code site
    print("\ninstruction-level verification (stock -> patched):")
    for addr in sorted(set(touched)):
        o = addr - S.APP_BASE + img.payload_off
        # only disassemble sites that live in the code region
        a = disasm_region(img.original, img.payload_off, addr, 8)
        b = disasm_region(img.data, img.payload_off, addr, 8)
        print(f"  0x{addr:08X}")
        for (aa, ah, at), (ba, bh, bt) in zip(a, b):
            mark = "  " if ah == bh else "->"
            print(f"    {mark} {ah:10} {at:28} | {bh:10} {bt}")
            if ah == bh:
                break

    d = img.diff_offsets()
    print(f"\nbytes changed : {len(d)}")
    print(f"payload len   : 0x{img.orig_payload_len:X} -> 0x{img.payload_len:X}")
    print(f"cave used     : {img.cave_ptr - img.cave_start} / "
          f"{img.cave_end - img.cave_start} bytes")

    if args.write:
        out_sha = img.save(args.out)
        print(f"\nwrote {args.out}")
        print(f"sha256 {out_sha}")
    else:
        print("\n(dry run -- pass --write to emit the file)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
