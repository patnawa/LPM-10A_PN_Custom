#!/usr/bin/env python3
"""
LPM-10A receiver firmware build tool.

    python build.py --list                     show available patches and profiles
    python build.py --profile pn1.19 --write   build a PN version (see profiles.py; the default profile is the latest)
    python build.py --write                    build the latest profile
    python build.py --default --write          the PN 1.0 default patch set (battery fix only)
    python build.py --only a,b --out X --write build a custom set (needs an explicit output name)
    python build.py --all --out X --write      include patches marked untested

The old per-version flags (--overload, --mode-tone, ... --strong-cap) still work
as aliases for --profile.

Every --write emits two files: the raw image (hashes, tests, emulation) and
`<name>-update.bin`, the container the receiver bootloader actually programs
(lpm10rx/container.py).  Copy the -update.bin file to the BOOTLOADER drive with
Explorer; the raw image is ignored by the bootloader.

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
from lpm10rx.container import wrap                         # noqa: E402
from lpm10rx import symbols as S                          # noqa: E402
import rx_patches as patches                               # noqa: E402
from profiles import PROFILES, LATEST, apply_profile       # noqa: E402

FW_DIR = os.path.dirname(HERE)
STOCK = os.path.join(FW_DIR, STOCK_NAME)
OUT = os.path.join(FW_DIR, "APP_LPM-10RX_PN1.0.bin")


def disasm(data, addr, n):
    from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_MCLASS
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS)
    o = addr - S.APP_BASE
    return [(i.address, i.bytes.hex(), f"{i.mnemonic} {i.op_str}".strip())
            for i in md.disasm(bytes(data[o:o + n]), addr)]


def update_path(raw_path):
    """`X.bin` -> `X-update.bin`: the container the bootloader accepts."""
    root, ext = os.path.splitext(raw_path)
    return f"{root}-update{ext or '.bin'}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--profile", metavar="NAME", help=f"a profile from profiles.py, e.g. {LATEST} (the default)")
    ap.add_argument("--default", action="store_true", help="the PN 1.0 default patch set instead of a profile")
    ap.add_argument("--all", action="store_true", help="include patches marked untested (custom build)")
    ap.add_argument("--only", help="comma-separated patch ids (custom build)")
    ap.add_argument("--out", help="output path (required for custom builds)")
    for p in PROFILES.values():
        ap.add_argument(f"--{p.flag}", dest=f"flag_{p.name}", action="store_true",
                        help=f"alias for --profile {p.name}: {p.title}")
    args = ap.parse_args()

    if args.list:
        print(f"{'id':24} {'risk':9} {'group':8} {'default':8} title")
        print("-" * 96)
        for p in patches.REGISTRY:
            print(f"{p.pid:24} {p.risk:9} {p.group:8} {'yes' if p.default else 'no':8} {p.title}")
        print("\nprofiles (--profile NAME, or the alias flag):")
        for p in PROFILES.values():
            print(f"  {p.name:7} --{p.flag:13} {p.title}")
        return 0

    aliases = [p for p in PROFILES.values() if getattr(args, f"flag_{p.name}")]
    if len(aliases) > 1 or (aliases and args.profile):
        ap.error("choose one profile")
    if aliases:
        args.profile = aliases[0].name
    custom = args.only is not None or args.all
    if custom and (args.profile or args.default):
        ap.error("--only/--all build a custom set; do not combine them with a profile or --default")
    if custom and not args.out:
        ap.error("custom builds need --out (they must not impersonate a numbered PN file)")
    if args.default and args.profile:
        ap.error("--default and --profile are exclusive")

    if args.only is not None:
        want = [x.strip() for x in args.only.split(",")]
        sel = [p for p in patches.REGISTRY if p.pid in want]
        missing = set(want) - {p.pid for p in sel}
        if missing:
            print(f"unknown patch id(s): {', '.join(sorted(missing))}")
            return 2
        out = args.out
    elif args.all:
        sel = list(patches.REGISTRY)
        out = args.out
    elif args.default:
        sel = [p for p in patches.REGISTRY if p.default]
        out = args.out or OUT
    else:
        name = args.profile or LATEST
        if name not in PROFILES:
            ap.error(f"unknown profile {name!r}; known: {', '.join(PROFILES)}")
        prof = PROFILES[name]
        ids = prof.patch_ids()
        sel = [p for p in patches.REGISTRY if p.pid in ids]
        out = args.out or os.path.join(FW_DIR, prof.output)
        print(f"profile {prof.name}: {prof.title}")
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

    def report(p, before):
        if p is None:
            print(f"  [{'tag':8}] {'version-tag':24} version string names the build")
        else:
            print(f"  [{p.risk:8}] {p.pid:24} {p.title}")
        for addr, old, new, why, kind in img.log[before:]:
            if kind == "text":
                print(f"              0x{addr:08X}  \"{old.decode()}\" -> \"{new.decode()}\"")
            elif kind == "note":
                print(f"              0x{addr:08X}  {why}")
            else:
                print(f"              0x{addr:08X}  {old.hex()} -> {new.hex()}   {why}")
                touched.append((addr, max(len(old), len(new))))

    try:
        if custom or args.default:
            for p in sel:
                before = len(img.log)
                p(img)
                report(p, before)
        else:
            apply_profile(img, prof, report)
    except PatchError as e:
        print(f"  [FAIL] {e}")
        return 2

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
    grown = len(img.data) - len(img.original)
    print(f"file size     : {len(img.data)} raw image" + (f" (+{grown} bytes appended)" if grown else " (unchanged)")
          + "; the update file adds the 4 KB container header")

    if args.write:
        out_sha = img.save(out)
        print(f"\nwrote {out}")
        print(f"sha256 {out_sha}")
        # The receiver bootloader only programs the container, never the raw image.
        update = update_path(out)
        container = wrap(bytes(img.data))
        with open(update, "wb") as output:
            output.write(container)
        print(f"wrote {update}  ({len(container)} bytes; copy THIS file to the BOOTLOADER drive)")
        print(f"sha256 {hashlib.sha256(container).hexdigest()}")
    else:
        print("\n(dry run -- pass --write to emit the file)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
