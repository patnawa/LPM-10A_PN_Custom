#!/usr/bin/env python3
"""
Disassembler for the receiver image, aware of the -O0 build's movw/movt address pairs.

    python disasm.py fn <addr> [maxbytes]     one function, stops at its epilogue
    python disasm.py at <addr> <nbytes>       linear listing (addresses and counts in hex)
    python disasm.py funcs                    every function reachable from the
                                              vectors and main, with peripherals,
                                              RAM variables and callees
    python disasm.py xref <addr>              who references the address (bl, b.w,
                                              conditional branch, movw/movt pair,
                                              literal word)

An argument ending in .bin, anywhere on the line, selects the image (default:
the stock image).  --raw keeps the `b .+2` no-ops that the -O0 build emits.

Lines ending in `; rN = 0x...` resolve a movw/movt pair; known peripherals,
RAM variables and functions are named from lpm10rx/symbols.py.
"""
import collections
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from lpm10rx import symbols as S                              # noqa: E402
from lpm10rx.image import STOCK_NAME, require_stock           # noqa: E402

RAW = "--raw" in sys.argv
if RAW:
    sys.argv.remove("--raw")
IMG = next((a for a in sys.argv[1:] if a.lower().endswith(".bin")), None)
if IMG:
    sys.argv.remove(IMG)
PATH = IMG or require_stock(os.path.join(os.path.dirname(HERE), STOCK_NAME))
D = open(PATH, "rb").read()
BASE, END = S.APP_BASE, S.APP_BASE + len(D)

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_MCLASS   # noqa: E402
md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS)

NAMES = dict(S.FUNCS)
VARS = {a: n for a, (n, _) in S.VARS.items()}


def u32(a):
    return struct.unpack_from("<I", D, a - BASE)[0]


def cstr(a):
    o = a - BASE
    if not 0 <= o < len(D):
        return None
    e = D.find(b"\0", o, o + 100)
    if e < 0:
        return None
    try:
        s = D[o:e].decode()
    except UnicodeDecodeError:
        return None
    return s if len(s) >= 2 and all(32 <= ord(c) < 127 for c in s) else None


PERIPHS = sorted(S.PERIPHERALS.items(), reverse=True)     # highest base first


def is_periph(v):
    return 0x40000000 <= v < 0x40030000 or 0x42000000 <= v < 0x44000000 or 0xE000E000 <= v < 0xE0100000


def name_of(v):
    for b, n in PERIPHS:
        if b <= v < b + S.PERIPHERAL_SIZE.get(n, 0x400):
            return n + (f"+0x{v - b:X}" if v != b else "")
    if v in VARS:
        return VARS[v]
    for a, (n, sz) in S.VARS.items():
        if a < v < a + sz:
            return f"{n}+{v - a}"
    if (v & ~1) in NAMES:
        return NAMES[v & ~1]
    s = cstr(v)
    return f'"{s}"' if s else None


def insns(start, maxb=0x2000, stop_at_ret=True):
    a = start
    while a < END and a - start < maxb:
        got = list(md.disasm(D[a - BASE:a - BASE + 4], a, 1))
        if not got:
            yield None, a
            a += 2
            continue
        i = got[0]
        yield i, a
        a += i.size
        if stop_at_ret and ((i.mnemonic in ("pop", "pop.w") and "pc" in i.op_str) or (i.mnemonic == "bx" and i.op_str == "lr")):
            return


def listing(start, maxb=0x2000, stop_at_ret=True):
    regs = {}
    for i, a in insns(start, maxb, stop_at_ret):
        if i is None:
            print(f"  {a:08X}: {D[a - BASE:a - BASE + 2].hex():10}  .short")
            continue
        if not RAW and i.bytes.hex() == "ffe7" or (not RAW and i.mnemonic == "nop"):
            continue
        note = ""
        if i.mnemonic == "movw":
            rd, imm = i.op_str.split(", #")
            regs[rd] = int(imm, 0)
        elif i.mnemonic == "movt":
            rd, imm = i.op_str.split(", #")
            if rd in regs:
                v = (int(imm, 0) << 16) | (regs[rd] & 0xFFFF)
                regs[rd] = v
                n = name_of(v)
                note = f"{rd} = 0x{v:08X}" + (f" {n}" if n else "")
        elif i.mnemonic in ("ldr", "ldr.w") and "[pc" in i.op_str:
            m = re.search(r"#(0x[0-9a-f]+|\d+)", i.op_str)
            tgt = ((i.address + 4) & ~3) + int(m.group(1), 0)
            if BASE <= tgt < END - 3:
                v = u32(tgt)
                n = name_of(v)
                note = f"=0x{v:08X}" + (f" {n}" if n else "")
                if 0x38000000 < v < 0x4B000000 and not n:
                    note += f" =f{struct.unpack('<f', struct.pack('<I', v))[0]:.5g}"
        elif i.mnemonic in ("bl", "b.w", "b", "beq", "bne", "blo", "bhs", "blt", "bge", "bgt", "ble", "bhi", "bls", "cbz", "cbnz") and "#0x" in i.op_str:
            t = int(i.op_str.split("#")[-1], 16)
            if t in NAMES:
                note = f"<{NAMES[t]}>"
        lbl = f"<{NAMES[a]}>:" if a in NAMES else ""
        if lbl:
            print(f"\n{lbl}")
        print(f"  {a:08X}: {i.bytes.hex():10}  {i.mnemonic:8} {i.op_str:34} {'; ' + note if note else ''}")


def refs_of(insn_list):
    regs, out = {}, []
    for i in insn_list:
        if i.mnemonic == "movw":
            rd, imm = i.op_str.split(", #")
            regs[rd] = int(imm, 0)
        elif i.mnemonic == "movt":
            rd, imm = i.op_str.split(", #")
            if rd in regs:
                v = (int(imm, 0) << 16) | (regs[rd] & 0xFFFF)
                regs[rd] = v
                out.append(v)
        elif i.mnemonic in ("ldr", "ldr.w") and "[pc" in i.op_str:
            m = re.search(r"#(0x[0-9a-f]+|\d+)", i.op_str)
            t = ((i.address + 4) & ~3) + int(m.group(1), 0)
            if BASE <= t < END - 3:
                out.append(u32(t))
    return out


def discover():
    roots = {u32(BASE + 4 * i) & ~1 for i in range(1, 82) if BASE < u32(BASE + 4 * i) < END}
    roots |= {a for a in S.FUNCS}
    funcs, calls, work = {}, collections.defaultdict(set), sorted(roots)
    while work:
        f = work.pop()
        if f in funcs or not BASE <= f < END:
            continue
        body = [i for i, _ in insns(f) if i is not None]
        funcs[f] = body
        for i in body:
            if i.mnemonic == "bl" and "#0x" in i.op_str:
                t = int(i.op_str.split("#")[-1], 16)
                calls[f].add(t)
                if t not in funcs:
                    work.append(t)
        for v in refs_of(body):
            if BASE <= (v & ~1) < END and (v & 1) and (v & ~1) not in funcs:
                work.append(v & ~1)
    return funcs, calls


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    if cmd == "fn":
        listing(int(sys.argv[2], 16), int(sys.argv[3], 16) if len(sys.argv) > 3 else 0x2000)
    elif cmd == "at":
        listing(int(sys.argv[2], 16), int(sys.argv[3], 16), stop_at_ret=False)
    elif cmd == "funcs":
        funcs, calls = discover()
        print(f"{len(funcs)} functions")
        for f in sorted(funcs):
            body = funcs[f]
            r = refs_of(body)
            per = sorted({name_of(v) or f"0x{v:08X}" for v in r if is_periph(v)})
            ram = sorted({v for v in r if 0x20000000 <= v < 0x20004000})
            print(f"0x{f:08X} {sum(i.size for i in body):5}  {NAMES.get(f, ''):26} calls={' '.join(NAMES.get(t, f'{t:X}'[-4:]) for t in sorted(calls[f]))}")
            if per:
                print(f"      per: {' '.join(str(p) for p in per)}")
            if ram:
                print(f"      ram: {' '.join(VARS.get(v, f'{v:X}'[-4:]) for v in ram)}")
    elif cmd == "xref":
        target = int(sys.argv[2], 16)
        funcs, calls = discover()
        BR = ("bl", "b.w", "b", "beq", "bne", "blo", "bhs", "blt", "bge", "bgt", "ble", "bhi", "bls", "cbz", "cbnz")
        in_flash = BASE <= target < END
        for f, body in sorted(funcs.items()):
            for i in body:
                if i.mnemonic in BR and "#0x" in i.op_str and int(i.op_str.split("#")[-1], 16) == (target & ~1):
                    print(f"  {i.mnemonic:4} at 0x{i.address:08X} in {NAMES.get(f, f'0x{f:08X}')}")
            for v in refs_of(body):
                if (v == target) or (in_flash and (v & ~1) == (target & ~1)):
                    print(f"  ref  in {NAMES.get(f, f'0x{f:08X}')}")
    else:
        print(__doc__)
