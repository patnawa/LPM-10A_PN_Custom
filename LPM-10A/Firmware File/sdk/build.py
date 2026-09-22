#!/usr/bin/env python3
"""
LPM-10A firmware build tool.

    python build.py --list                      show available patches and profiles
    python build.py                             dry run of the latest profile (see profiles.py)
    python build.py --write                     emit the latest profile, e.g. experimental/LPM-10A-TX_PN2.14-tone-recovery.bin
    python build.py --profile pn2.12 --write    reproduce an earlier PN version
    python build.py --default --write           the frozen baseline verify.py models (unreleased LPM-10A-TX_PN2.9.bin)
    python build.py --with blind-zone-50cm --out ../experimental/x.bin --write
                                                a profile (or --default) plus opt-in patches
    python build.py --only a,b --out X --write  build a specific set
    python build.py --all --out X --write       every registered patch

The old per-version flags (--roadmap, --portflash, --audit, --portflash-status,
--scan-sync, --scan-recovery) still work as aliases for --profile.  Custom builds
(--only, --with, --all) need --out when they write: they must not impersonate a
numbered PN file.

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
from profiles import PROFILES, LATEST, profile_patches, baseline_ids   # noqa: E402

FW_DIR = os.path.dirname(HERE)
STOCK = os.path.join(FW_DIR, "LPM-10A-TX_V2.0.7_260610.bin")
STOCK_SHA = "29081ccbbd929a884c7c81fb309aa2894ce2ab84e061918538b3ead8e632940b"
OUT = os.path.join(FW_DIR, "experimental", f"LPM-10A-TX_{patches.VERSION.replace(' ', '')}.bin")   # the baseline
# the profile outputs by name, for the test modules that compare against the archived files
ROADMAP_OUT, PORTFLASH_OUT, AUDIT_OUT, PORTFLASH_STATUS_OUT, SCAN_SYNC_OUT, SCAN_RECOVERY_OUT = (
    PROFILES[n].path(FW_DIR) for n in ("pn2.9", "pn2.10", "pn2.11", "pn2.12", "pn2.13", "pn2.14"))


def disasm_region(data, payload_off, addr, n):
    from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_MCLASS
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS)
    o = addr - S.APP_BASE + payload_off
    return [(i.address, i.bytes.hex(), f"{i.mnemonic} {i.op_str}".strip())
            for i in md.disasm(bytes(data[o:o + n]), addr)]


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--profile", metavar="NAME", help=f"a profile from profiles.py, e.g. {LATEST} (the default)")
    ap.add_argument("--default", action="store_true", help="the frozen baseline patch set (what verify.py models) instead of a profile")
    ap.add_argument("--all", action="store_true", help="every registered patch, including risk=untested (custom build)")
    ap.add_argument("--only", help="comma-separated patch ids (custom build)")
    ap.add_argument("--with", dest="extra", help="comma-separated opt-in patch ids added to the profile or --default (custom build)")
    ap.add_argument("--out", help="output path (required to write a custom build)")
    for p in PROFILES.values():
        ap.add_argument(f"--{p.flag}", dest=f"flag_{p.name}", action="store_true",
                        help=f"alias for --profile {p.name}: {p.title}")
    args = ap.parse_args()

    if args.list:
        latest = PROFILES[LATEST].patch_ids()
        print(f"{'id':22} {'risk':9} {'group':11} {'baseline':9} {LATEST:8} title (required patches)")
        print("-" * 110)
        for p in patches.REGISTRY:
            print(f"{p.pid:22} {p.risk:9} {p.group:11} {'yes' if p.default else 'no':9} "
                  f"{'yes' if p.pid in latest else 'no':8} {p.title}"
                  + (f" (requires: {', '.join(p.requires)})" if p.requires else ""))
        print("\nprofiles (--profile NAME, or the alias flag; the last one is the default):")
        for p in PROFILES.values():
            print(f"  {p.name:7} --{p.flag:17} {p.version:8} {p.output}")
            print(f"          {p.title}")
            print(f"          hardware: {p.hardware}")
        return 0

    # ---- select patches
    aliases = [p for p in PROFILES.values() if getattr(args, f"flag_{p.name}")]
    if len(aliases) > 1 or (aliases and args.profile):
        ap.error("choose one profile")
    if aliases:
        args.profile = aliases[0].name
    if args.default and args.profile:
        ap.error("--default and --profile are exclusive")
    if args.only is not None and (args.profile or args.default or args.extra is not None or args.all):
        ap.error("--only builds exactly the listed set; do not combine it with a profile, --default, --with or --all")
    if args.all and (args.profile or args.default or args.extra is not None):
        ap.error("--all builds every registered patch; do not combine it with a profile, --default or --with")
    custom = args.only is not None or args.extra is not None or args.all
    if custom and args.write and not args.out:
        ap.error("custom builds need --out (they must not impersonate a numbered PN file)")

    prof = None
    if args.only is not None:
        want = [x.strip() for x in args.only.split(",")]
        ids = set(want)
        missing = ids - {p.pid for p in patches.REGISTRY}
        if missing:
            print(f"unknown patch id(s): {', '.join(sorted(missing))}")
            return 2
        out = args.out
    elif args.all:
        ids = {p.pid for p in patches.REGISTRY}
        out = args.out
    else:
        extra = {x.strip() for x in args.extra.split(",")} if args.extra else set()
        missing = extra - {p.pid for p in patches.REGISTRY}
        if missing:
            print(f"unknown patch id(s): {', '.join(sorted(missing))}")
            return 2
        if args.default:
            ids = set(baseline_ids()) | extra
            out = args.out or OUT
        else:
            name = args.profile or LATEST
            if name not in PROFILES:
                ap.error(f"unknown profile {name!r}; known: {', '.join(PROFILES)}")
            prof = PROFILES[name]
            ids = prof.patch_ids() | extra
            out = args.out or prof.path(FW_DIR)

    sel = [p for p in patches.REGISTRY if p.pid in ids]
    if {'scan-sync', 'scan-recovery'} <= ids:
        ap.error("scan-sync and scan-recovery are alternative profiles; select only one")
    for p in sel:
        unmet = set(p.requires) - ids
        if unmet:
            print(f"{p.pid} requires: {', '.join(sorted(unmet))}; include them in --only")
            return 2
    if prof is not None:
        sel = profile_patches(prof, extra)

    if prof is not None:
        print(f"profile {prof.name}: {prof.title}")
        print(f"version {prof.version}; hardware: {prof.hardware}")
    elif args.default:
        print(f"baseline {patches.VERSION}: the frozen set verify.py models (never released on its own)")
    else:
        print("custom build")

    # ---- load and check provenance
    try:
        img = Image(STOCK)
    except PatchError as e:
        print(f"REFUSING TO BUILD: {e}")
        return 2
    sha = hashlib.sha256(img.original).hexdigest()
    print(f"stock name  : {img.name}")
    print(f"sha256      : {sha}")
    if sha != STOCK_SHA:
        print("\nREFUSING TO BUILD: this is not the V2.0.7 image these patches were")
        print("written against.  Re-verify every patch site before changing STOCK_SHA.")
        return 2
    print(f"{img.summary().splitlines()[2]}\n")

    # ---- finish the reproducible profile before applying optional extras
    print(f"applying {len(sel)} patch(es):")
    touched = []

    def report(p, before):
        edits = img.log[before:]
        print(f"  [{p.risk:8}] {p.pid:22} {p.title}")
        for addr, old, new, why, kind in edits:
            if kind == "note":
                print(f"              {why}")
            elif kind == "text":
                print(f"              0x{addr:08X}  \"{old.decode()}\" -> \"{new.decode()}\"")
            elif kind == "blob":
                print(f"              0x{addr:08X}  {len(new)} bytes replaced   {why}")
            else:
                print(f"              0x{addr:08X}  {old.hex() or '(new)'} -> {new.hex()}   {why}")
                touched.append(addr)

    try:
        for p in sel:
            before = len(img.log)
            p(img)
            report(p, before)
    except PatchError as e:
        print(f"  [FAIL] {p.pid}: {e}")
        return 2

    img.finalize()

    # ---- verification: show the CPU's view of every changed code site
    print("\ninstruction-level verification (stock -> patched):")
    original = img.original + bytes(len(img.data) - len(img.original))    # stock, padded to the built length
    for addr in sorted(set(touched)):
        # only disassemble sites that live in the code region
        a = disasm_region(original, img.payload_off, addr, 8)
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
        out_sha = img.save(out)
        print(f"\nwrote {out}")
        print(f"sha256 {out_sha}")
    else:
        print(f"\n(dry run -- pass --write to emit {out or 'the file named by --out'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
