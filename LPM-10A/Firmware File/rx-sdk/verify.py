#!/usr/bin/env python3
"""
Post-build verification for a patched LPM-10A receiver image.

    python verify.py [modified.bin]

  1  image integrity: size, vector table, and every patched byte compared
     against the patch record (stock bytes before, new bytes after)
  2  full disassembly inventory compared by address (no undeclared change)
  3  the battery state machine under CPU emulation, one call per reading
     (the firmware takes one every 500 ms), on stock and on the mod, with a
     fake ADC and power_off trapped; expected state/count traces are checked,
     not just whether the unit switched off
  4  the register and byte facts the in-place patch relies on
"""
import hashlib
import argparse
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
FW = os.path.dirname(HERE)

from lpm10rx import symbols as S                              # noqa: E402
from lpm10rx.image import Image, STOCK_NAME, require_stock    # noqa: E402
import rx_patches as patches                                  # noqa: E402

STOCK = require_stock(os.path.join(FW, STOCK_NAME))
ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument("image", nargs="?")
ap.add_argument("--digital", action="store_true", help="verify the opt-in digital-correlation candidate")
ap.add_argument("--reliability", action="store_true", help="verify PN 1.2: digital + activity-aware auto-off")
args = ap.parse_args()
args.digital = args.digital or args.reliability
name = patches.RELIABILITY_EXPERIMENT if args.reliability else (patches.DIGITAL_EXPERIMENT if args.digital else "APP_LPM-10RX_PN1.0.bin")
MOD = args.image or os.path.join(FW, name)

fails = 0
count = 0


def check(ok, label, detail=""):
    global fails, count
    count += 1
    fails += not ok
    print(f"  [{'ok  ' if ok else 'FAIL'}] {label}" + (f"   {detail}" if detail else ""))


_probe = Image(STOCK)
for _p in patches.REGISTRY:
    if _p.default or (args.digital and _p.pid == "digital-correlation") or (args.reliability and _p.pid == "activity-before-autooff"):
        _p(_probe)
EXPECTED = list(_probe.log)

stock = open(STOCK, "rb").read()
mod = open(MOD, "rb").read()
print(f"stock : {os.path.basename(STOCK)}  sha256 {hashlib.sha256(stock).hexdigest()[:16]}")
print(f"mod   : {os.path.basename(MOD)}  sha256 {hashlib.sha256(mod).hexdigest()[:16]}")

# ---------------------------------------------------------------- 1
print("\n1. image integrity")
check(len(mod) == len(stock) == S.APP_SIZE, "file size unchanged", f"{len(mod)} bytes")
check(mod[:0x148] == stock[:0x148], "vector table unchanged")
sp0, rst = struct.unpack_from("<II", mod, 0)
check(sp0 == S.STACK_TOP and rst == 0x0800695D, "initial SP / reset vector", f"sp=0x{sp0:08X} reset=0x{rst:08X}")
diff = [i for i in range(len(stock)) if stock[i] != mod[i]]
declared = set()
bytes_ok = True
for addr, old, new, why, kind in EXPECTED:
    o = addr - S.APP_BASE
    n = max(len(old), len(new)) + (1 if kind == "text" else 0)
    declared.update(range(o, o + n))
    if kind != "text":
        bytes_ok &= stock[o:o + len(old)] == old and mod[o:o + len(new)] == new
check(bool(diff), "image actually changed", f"{len(diff)} bytes")
check(all(i in declared for i in diff), "every changed byte was declared by a patch")
check(bytes_ok, "every patched site holds exactly the recorded bytes (stock before, new after)",
      f"{len(EXPECTED)} site(s)")
check(all(stock[i] == mod[i] for i in range(len(stock)) if i not in declared), "nothing outside the patch record differs")

# ---------------------------------------------------------------- 2
print("\n2. code integrity (disassembly inventory by address)")
try:
    from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_MCLASS
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS)
    CODE_START, CODE_END = 0x08006948, 0x0800CB94

    def inventory(buf):
        seen = {}
        a = CODE_START
        while a < CODE_END:
            o = a - S.APP_BASE
            ins = next(md.disasm(buf[o:o + 4], a, 1), None)
            if ins is None:
                seen[a] = (".data", buf[o:o + 2].hex()); a += 2
            else:
                seen[a] = (ins.mnemonic, ins.bytes.hex()); a += ins.size
        return seen
    a, b = inventory(stock), inventory(mod)
    check(len(a) > 8000, "code region disassembled", f"{len(a)} instructions")
    exp_addr = {S.APP_BASE + o for o in declared}
    changed = sorted(x for x in set(a) | set(b) if a.get(x) != b.get(x))
    undeclared = [x for x in changed if x not in exp_addr]
    check(not undeclared, "every changed instruction was declared",
          f"{len(changed)} changed" if not undeclared else f"UNDECLARED: {[hex(x) for x in undeclared[:5]]}")
    last = max(exp_addr)
    check(all(a.get(x) == b.get(x) for x in a if x > last), "code after the last edit is identical", f"from 0x{last + 1:08X}")
    # the patched block must decode to exactly the intended instructions
    want = ["mov", "ldrh", "movw", "cmp", "bhs", "ldrb", "adds", "uxtb", "strb", "cmp", "blt", "bl", "b"]
    got = [b[x][0] for x in sorted(b) if 0x08007880 <= x < 0x0800789E]
    check(got == want, "patched block decodes to the intended instruction sequence", " ".join(got))
except ImportError:
    check(False, "capstone not available")

# ---------------------------------------------------------------- 3
print("\n3. battery state machine under emulation (one call = one reading, 500 ms apart)")
try:
    from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE
    from unicorn.arm_const import (UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_R0,
                                   UC_ARM_REG_R1, UC_ARM_REG_R4)
    MAGIC = 0x00100000
    BATT, ADC_READ_N, POWER_OFF = S.FUNCS_BY_NAME["battery_500ms"], 0x08007320, 0x08007570
    STATE, COUNT = 0x20000056, 0x20000057

    def raw_for(mv):
        """Smallest ADC count whose firmware conversion (raw*6600>>12) is >= mv."""
        return -(-mv * 4096 // 6600)

    class Batt:
        """The receiver's battery routine with a fake ADC."""
        def __init__(self, buf):
            uc = self.uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
            uc.mem_map(0x08000000, 0x20000)
            uc.mem_map(0x20000000, 0x10000)
            uc.mem_map(0x40000000, 0x30000)              # GPIO etc.: the set/reset helpers run for real
            uc.mem_map(MAGIC & ~0xFFF, 0x1000)
            uc.mem_write(S.APP_BASE, buf)
            self.mv = 4000
            self.power_off = 0
            self.r4_seen = set()
            uc.hook_add(UC_HOOK_CODE, self._hook)

        def _hook(self, uc, addr, size, ud):
            if addr == ADC_READ_N:                       # (ch, buf): five identical samples
                raw = raw_for(self.mv)
                uc.mem_write(uc.reg_read(UC_ARM_REG_R1), struct.pack("<5H", *([raw] * 5)))
                uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
            elif addr == POWER_OFF:
                self.power_off += 1
                uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
            elif 0x08007880 <= addr < 0x0800789E:
                self.r4_seen.add(uc.reg_read(UC_ARM_REG_R4))

        def reading(self, mv):
            self.mv = mv
            uc = self.uc
            uc.reg_write(UC_ARM_REG_SP, 0x20001600)
            uc.reg_write(UC_ARM_REG_LR, MAGIC | 1)
            before = self.power_off
            uc.emu_start(BATT | 1, MAGIC, count=100000)
            assert uc.reg_read(UC_ARM_REG_PC) == (MAGIC & ~1), "did not return"
            return uc.mem_read(STATE, 1)[0], uc.mem_read(COUNT, 1)[0], self.power_off - before

    def run(buf, seq, preset=None):
        b = Batt(buf)
        if preset:
            b.uc.mem_write(STATE, bytes([preset[0]]))
            b.uc.mem_write(COUNT, bytes([preset[1]]))
        trace = [b.reading(mv) for mv in seq]
        return trace, b

    def fmt(t):
        return " ".join(f"{s}/{c}{'!' if p else ''}" for s, c, p in t)

    def off_at(t):
        return next((i + 1 for i, (_, _, p) in enumerate(t) if p), None)

    # (label, sequence, reading at which stock powers off, expected mod trace as "state/count")
    cases = [
        ("one dip to 3200 mV, then a healthy 3600 mV pack",
         [3200, 3600, 3600, 3600, 3600, 3600, 3600], 5,
         "2/1 1/0 1/0 1/0 1/0 1/0 1/0"),
        ("dip, then 3350 mV (inside the 3280..3400 band): still counts to 5",
         [3200, 3350, 3350, 3350, 3350, 3350], 5,
         "2/1 2/2 2/3 2/4 2/5 2/6"),
        ("pack really flat: 3200 mV throughout",
         [3200] * 6, 5,
         "2/1 2/2 2/3 2/4 2/5 2/6"),
        ("beeping on a tired pack: 3200 / 3500 alternating",
         [3200, 3500] * 5, 5,
         "2/1 1/0 2/1 1/0 2/1 1/0 2/1 1/0 2/1 1/0"),
        ("healthy pack, 4000 mV",
         [4000] * 5, None,
         "0/0 0/0 0/0 0/0 0/0"),
        ("slow decline 3700 3500 3300 3250 3250 3250 3250 3250",
         [3700, 3500, 3300, 3250, 3250, 3250, 3250, 3250], 8,
         "0/0 1/0 1/0 2/1 2/2 2/3 2/4 2/5"),
        ("recovery boundary: 3399 mV does not recover",
         [3200, 3399, 3399, 3399, 3399], 5,
         "2/1 2/2 2/3 2/4 2/5"),
        ("recovery boundary: 3401 mV (raw 2111, the first count above 3400) recovers",
         [3200, 3401, 3401], None,
         "2/1 1/0 1/0"),
        ("count 4 then recovery then four more lows: the count restarts",
         [3200, 3200, 3200, 3200, 3600, 3200, 3200, 3200, 3200], 5,
         "2/1 2/2 2/3 2/4 1/0 2/1 2/2 2/3 2/4"),
    ]
    for label, seq, stock_off, want in cases:
        ts, _ = run(stock, seq)
        tm, _ = run(mod, seq)
        got = " ".join(f"{s}/{c}" for s, c, _ in tm)
        mod_off = off_at(tm)
        want_mod_off = None
        # the mod switches off exactly when its count reaches 5
        for i, (s, c, _) in enumerate(tm):
            if c == 5 and want_mod_off is None:
                want_mod_off = i + 1
        ok = (off_at(ts) == stock_off) and (got == want) and (mod_off == want_mod_off)
        check(ok, label, f"stock {fmt(ts)} | mod {fmt(tm)}")

    ts, _ = run(stock, [3200] * 6)
    tm, _ = run(mod, [3200] * 6)
    check(off_at(ts) == off_at(tm) == 5, "legitimate shutdown: power_off fires on the 5th consecutive critical reading (2.5 s) on both",
          f"stock #{off_at(ts)}, mod #{off_at(tm)}")

    tm, _ = run(mod, [3200, 3500, 3700, 3700])
    check([(s, c) for s, c, _ in tm] == [(2, 1), (1, 0), (0, 0), (0, 0)] and not off_at(tm),
          "recovery lands in the LOW state (LED stays on) and clears at 3621 mV as in stock", fmt(tm))

    print("\n4. register and byte facts the in-place patch relies on")
    _, bm = run(mod, [3200, 3200])
    check(bm.r4_seen == {0x2000004A}, "r4 == batt_samples (0x2000004A) throughout the patched block", f"{[hex(x) for x in bm.r4_seen]}")
    ts, _ = run(stock, [3200], preset=(2, 255))
    tm, _ = run(mod, [3200], preset=(2, 255))
    check(ts == tm and ts[0][1] == 0 and not ts[0][2], "byte counter wraps 255 -> 0 without power_off, identical to stock", f"stock {fmt(ts)} | mod {fmt(tm)}")
    check(raw_for(3400) == 2111 and (2110 * 6600 >> 12) == 3399 and (2111 * 6600 >> 12) == 3401,
          "ADC grid: 3400 mV is not representable; first recovering count is 2111 (3401 mV)")
except ImportError:
    check(False, "unicorn not available")

if args.digital:
    print("\n5. experimental digital detection")
    try:
        from verify_digital import run_checks
        run_checks(stock, mod, check)
    except Exception as ex:
        check(False, f"digital checks aborted: {type(ex).__name__}: {ex}")

if args.reliability:
    print("\n6. RX keys, timer housekeeping and auto-off boundary")
    try:
        from verify_control import run_checks
        run_checks(stock, mod, check)
    except Exception as ex:
        check(False, f"control checks aborted: {type(ex).__name__}: {ex}")

print(f"\n{count} checks: " + ("ALL CHECKS PASSED" if not fails else f"{fails} CHECK(S) FAILED"))
sys.exit(1 if fails else 0)
