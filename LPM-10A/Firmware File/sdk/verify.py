#!/usr/bin/env python3
"""
Post-build verification for a patched LPM-10A image.

    python verify.py [modified.bin]

Checks, in order:
  1  container integrity (size, header, payload_len/end consistency)
  2  only the intended bytes differ from stock
  3  the whole image still disassembles into the same function inventory
     (a desync here would mean a patch shifted or corrupted code)
  4  auto-off: stock key-path reset (corrected claim) and the hold during tone / blink
  5  behavioural check of the boot-language default under CPU emulation
  6  length unit conversion (m / cm / ft, fixed point) against a reference model
  7  length on-screen text, produced by the firmware's own sprintf
  8  length result is no longer sticky; 8b the per-pair average over several CSD runs
  9  low-battery debounce (3 samples) and recovery / charger cancel
 10  10-step battery gauge and its drawing switch
 11  settings save frees its staging buffer on both exit paths
 12  Zero offset and NVP scaling inside the length conversion
 13  length unit loaded from / stored to settings; adjust target reset on entry
 14  NVP / Zero UP/DOWN key hook (clicks, auto-repeat, clamps, OK long press, other screens)
 15  GUI message 0x3D routing and the rendered "NVP nn%" / "ZERO n.nm" texts
 16  both texts drawn by the Length screen's header epilogue; Factory Reset clears Zero
 17  all three font tables rendered by the firmware's own glyph drawers
 18  version strings (About screen, boot log), the untouched container name, the SCAN labels, the About URL line

Every behavioural check runs the stock image too, so the report shows the
before/after pair rather than a bare pass.
"""
import os
import sys
import struct
import hashlib

if hasattr(sys.stdout, "reconfigure"):                    # Thai and Chinese in the check labels
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
FW = os.path.dirname(HERE)

from lpm10a import symbols as S          # noqa: E402
from lpm10a.image import Image, require_stock   # noqa: E402
import patches                            # noqa: E402

STOCK = require_stock(os.path.join(FW, "LPM-10A-TX_V2.0.7_260610.bin"))
MOD = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    FW, f"LPM-10A-TX_{patches.VERSION.replace(' ', '')}.bin")

fails = 0


def check(ok, label, detail=""):
    global fails
    fails += not ok
    print(f"  [{'ok  ' if ok else 'FAIL'}] {label}" + (f"   {detail}" if detail else ""))


# Re-run the default patch set in memory to learn exactly which bytes each
# patch claims to touch; the on-disk image is then held to that claim.
_probe = Image(STOCK)
for _p in patches.REGISTRY:
    if _p.default:
        _p(_probe)
EXPECTED_EDITS = list(_probe.log)

stock = open(STOCK, "rb").read()
mod = open(MOD, "rb").read()

print(f"stock : {os.path.basename(STOCK)}  sha256 {hashlib.sha256(stock).hexdigest()[:16]}")
print(f"mod   : {os.path.basename(MOD)}  sha256 {hashlib.sha256(mod).hexdigest()[:16]}")

# ---------------------------------------------------------------- 1
print("\n1. container integrity")
off, length, end = struct.unpack_from("<III", mod, 0x20)
grown = len(mod) - len(stock)
check(grown == 0 or (grown > 0 and grown % 0x1000 == 0),
      "file size is stock's" if grown == 0 else f"file size is stock's + {grown // 1024} KB (whole 4 KB pages, the cave grew)",
      f"{len(mod)} bytes")
check(mod[:0x20] == stock[:0x20], "internal image name unchanged",
      mod[:0x20].split(b"\0")[0].decode())
check(off == 0x1000, "payload offset 0x1000")
check(off + length - 1 == end, "payload_len / payload_end consistent",
      f"len=0x{length:X} end=0x{end:X}")
check(off + length <= len(mod), "payload fits inside the file")
check(not any(mod[off + length:]), "every byte after payload_end is zero (nothing the bootloader would skip)")
if grown:
    check(len(mod) - 0x1000 < off + length <= len(mod),
          "payload_end lies in the last (appended) page: the growth was needed and minimal",
          f"payload ends at file 0x{off + length:X}, stock file ends at 0x{len(stock):X}")
check(S.APP_BASE + length <= S.CONSTS["BOOTFLAG_PAGE"], "the payload ends below the bootloader's flag / settings pages",
      f"0x{S.APP_BASE + length:08X} < 0x{S.CONSTS['BOOTFLAG_PAGE']:08X}")

# ---------------------------------------------------------------- 2
print("\n2. difference footprint")
diff = [i for i in range(len(stock)) if stock[i] != mod[i]] + [i for i in range(len(stock), len(mod)) if mod[i]]
# the only header bytes allowed to change are payload_len / payload_end
# (0x24..0x2B), and only when the cave was used
hdr_ok = all(0x24 <= i < 0x2C for i in diff if i < off)
in_payload = all(off <= i < off + length for i in diff if i >= off)
check(bool(diff), "image actually changed", f"{len(diff)} bytes")
check(hdr_ok and in_payload, "every changed byte is inside the payload (or the header length fields)")
lo, hi = min(diff), max(diff)
check(True, "changed range", f"file 0x{lo:X}..0x{hi:X}")

check(bytes(_probe.finalize().data) == mod, "the file is byte-identical to a fresh in-memory build of the default patch set")

# ---------------------------------------------------------------- 3
print("\n3. code integrity (full-image disassembly inventory)")
try:
    from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_MCLASS
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS)

    CODE_START = 0x0800A198          # first real code, past the vector table
    CODE_END = 0x0801E2F0            # code ends here; assets follow

    def inventory(buf):
        """Linear sweep over the whole code region.

        Capstone stops at the first byte it cannot decode, so stepping 2 bytes
        on failure is what keeps this a real check rather than a vacuous one.
        """
        payload = buf[off:off + length]
        seen = []
        addr = CODE_START
        while addr < CODE_END:
            o = addr - S.APP_BASE
            ins = next(md.disasm(payload[o:o + 4], addr, 1), None)
            if ins is None:
                seen.append((addr, ".data", payload[o:o + 2].hex()))
                addr += 2
            else:
                seen.append((addr, ins.mnemonic, ins.bytes.hex()))
                addr += ins.size
        return seen

    a, b = inventory(stock), inventory(mod)
    check(len(a) > 20000, "code region actually disassembled", f"{len(a)} instructions")

    # Expected-change set is derived from the patch log, not hardcoded, so a
    # patch that touches something it did not declare will fail this check.
    expected = set()
    for addr, old, new, why, kind in EXPECTED_EDITS:
        if kind == "note":                      # a build note (e.g. the container grew), not an edit
            continue
        span = max(len(old), len(new)) + (1 if kind == "text" else 0)
        expected.update(range(addr, addr + span + 1))

    # Compare by address, not by index: a patch is allowed to change the
    # number of instructions inside its own declared range, and that must not
    # look like a desync of everything that follows it.
    da = {addr: (mn, hx) for addr, mn, hx in a}
    db = {addr: (mn, hx) for addr, mn, hx in b}
    changed = sorted(x for x in set(da) | set(db) if da.get(x) != db.get(x))
    unexpected = [x for x in changed if x not in expected]
    check(not unexpected, "every changed instruction was declared by a patch",
          f"{len(changed)} changed, all declared" if not unexpected
          else f"{len(unexpected)} UNDECLARED: "
               + ", ".join(f"0x{x:08X}" for x in unexpected[:5]))
    # and the code that follows the last in-region edit must be identical
    last_edit = max(x for x in expected if x < CODE_END)
    tail_same = all(da.get(x) == db.get(x) for x in da if x > last_edit)
    check(tail_same, "code after the last declared edit is unchanged (no shift)",
          f"from 0x{last_edit + 1:08X}")
except ImportError:
    check(False, "capstone not available")

# ---------------------------------------------------------------- 4 & 5
print("\n4. auto-off: what stock really does, and the hold during tone / blink")
try:
    from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS
    from unicorn.arm_const import UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_R0, UC_ARM_REG_PC

    MAGIC = 0x00100000

    def run(buf, entry, setup=None, r0=0):
        o, ln = struct.unpack_from("<II", buf, 0x20)
        uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
        uc.mem_map(0x08000000, 0x80000)
        uc.mem_map(0x20000000, 0x10000)
        uc.mem_map(MAGIC & ~0xFFF, 0x1000)
        uc.mem_write(S.APP_BASE, buf[o:o + ln])
        if setup:
            setup(uc)
        uc.reg_write(UC_ARM_REG_SP, 0x20008000)
        uc.reg_write(UC_ARM_REG_LR, MAGIC | 1)
        uc.reg_write(UC_ARM_REG_R0, r0)
        uc.emu_start(entry | 1, MAGIC, count=400)
        return uc

    # 4a. the corrected fact: stock resets the idle counter on every key event
    #     (Action_key_Process -> autooff_timer_reset), so no key-reset patch is needed.
    KEYBUF4 = 0x20003300
    for label, buf in (("stock", stock), ("mod", mod)):
        uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
        o, ln = struct.unpack_from("<II", buf, 0x20)
        uc.mem_map(0x08000000, 0x80000); uc.mem_map(0x20000000, 0x10000); uc.mem_map(MAGIC & ~0xFFF, 0x1000)
        uc.mem_write(S.APP_BASE, buf[o:o + ln])
        uc.mem_write(0x2000013C, bytes([4]))                     # sysState = CABLE (UP is unbound there)
        uc.mem_write(0x20000178, struct.pack("<H", 250))        # idle 250 s
        uc.mem_write(KEYBUF4, bytes([2, 3]))                     # UP, click
        uc.reg_write(UC_ARM_REG_SP, 0x2000E000); uc.reg_write(UC_ARM_REG_LR, MAGIC | 1)
        uc.reg_write(UC_ARM_REG_R0, KEYBUF4)
        uc.emu_start(0x080149FC | 1, MAGIC, count=200000)
        ctr = struct.unpack("<H", uc.mem_read(0x20000178, 2))[0]
        check(ctr == 0 and uc.reg_read(UC_ARM_REG_PC) == (MAGIC & ~1),
              f"{label:5}: any key event through Action_key_Process resets auto-off 250 -> {ctr}")

    # 4b. the fix: the once-per-second housekeeping holds while a session runs
    HOUSEKEEP = 0x0800F968
    def tick(buf, state, tone=0, busy1=0, ctr=100, idx=1):
        uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
        o, ln = struct.unpack_from("<II", buf, 0x20)
        uc.mem_map(0x08000000, 0x80000); uc.mem_map(0x20000000, 0x10000); uc.mem_map(MAGIC & ~0xFFF, 0x1000)
        uc.mem_write(S.APP_BASE, buf[o:o + ln])
        uc.mem_write(0x20000C78 + 0xA2, bytes([idx]))            # auto_off_idx (1 = 5 min)
        uc.mem_write(0x2000013C, bytes([state]))
        uc.mem_write(0x200000D0, bytes([tone]))                  # scan_state[0]: tone enabled
        uc.mem_write(0x200002B5, bytes([busy1]))                 # test_busy_flags[1]: 2 = blink running
        uc.mem_write(0x20000178, struct.pack("<H", ctr))
        uc.reg_write(UC_ARM_REG_SP, 0x2000E000); uc.reg_write(UC_ARM_REG_LR, MAGIC | 1)
        uc.emu_start(HOUSEKEEP | 1, MAGIC, count=5000)
        return struct.unpack("<H", uc.mem_read(0x20000178, 2))[0]
    cases = [  # (state, tone, busy1, stock expected, mod expected, label)
        (5, 1, 0, 101, 0,   "SCAN, tone on         "),
        (5, 0, 0, 101, 101, "SCAN, tone off        "),
        (6, 0, 2, 101, 0,   "FLASH, blink running  "),
        (6, 0, 0, 101, 101, "FLASH, blink finished "),
        (8, 0, 2, 101, 101, "QC TEST (flags stale) "),
        (2, 1, 2, 101, 101, "HOME (flags stale)    "),
        (7, 0, 0, 101, 101, "LENGTH                "),
    ]
    for state, tone, busy1, want_s, want_m, label in cases:
        got_s, got_m = tick(stock, state, tone, busy1), tick(mod, state, tone, busy1)
        check((got_s, got_m) == (want_s, want_m),
              f"{label} idle 100 s -> stock {got_s:3}, mod {got_m:3}",
              "(held, counter restarted)" if want_m == 0 else "(counts as before)")
    got = tick(mod, 5, 1, 0, ctr=299)
    check(got == 0, "SCAN tone on at 299 s of a 300 s timeout: no power-off, counter cleared", f"{got}")
    got = tick(mod, 5, 1, 0, idx=0)
    check(got == 100, "Auto Off = OFF: routine returns before the hook, counter untouched", f"{got}")

    print("\n5. factory defaults under emulation")
    for label, buf in (("stock", stock), ("mod", mod)):
        uc = run(buf, 0x0801958C)
        s = uc.mem_read(0x20000C78, 0xC9)
        magic = struct.unpack_from("<H", s, 0xA0)[0]
        lang, flag = s[0xA5], s[0xA8]
        ok = magic == 0x9718 and lang == 2 and flag == 1
        check(ok, f"{label:5}: magic=0x{magic:04X} language={lang} first_boot={flag}",
              "(language 2 = the second language, picker shown on first boot)")

    # ------------------------------------------------------------------
    # A more general runner for the measurement / battery checks: lets the
    # caller preload registers and memory, stops at a given PC or on return.
    from unicorn.arm_const import (UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3,
                                   UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6,
                                   UC_ARM_REG_R7, UC_ARM_REG_R8)
    from unicorn import UC_HOOK_CODE
    REG = {"r0": UC_ARM_REG_R0, "r1": UC_ARM_REG_R1, "r2": UC_ARM_REG_R2,
           "r3": UC_ARM_REG_R3, "r4": UC_ARM_REG_R4, "r5": UC_ARM_REG_R5,
           "r6": UC_ARM_REG_R6, "r8": UC_ARM_REG_R8, "sp": UC_ARM_REG_SP,
           "lr": UC_ARM_REG_LR, "pc": UC_ARM_REG_PC}

    class Emu:
        def __init__(self, buf):
            o, ln = struct.unpack_from("<II", buf, 0x20)
            self.uc = uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
            uc.mem_map(0x08000000, 0x80000)
            uc.mem_map(0x20000000, 0x10000)
            uc.mem_map(0x40000000, 0x20000)          # GPIO / peripherals (reads as 0)
            uc.mem_map(MAGIC & ~0xFFF, 0x1000)
            uc.mem_write(S.APP_BASE, buf[o:o + ln])
            self.stops = set()
            self.traps = set()
            self.zero = set()                # trapped like traps, but return r0 = 0
            self.fake = {}                   # addr -> callable(uc): a stand-in that sets r0 itself
            self.calls = []
            uc.hook_add(UC_HOOK_CODE, self._hook)

        def _hook(self, uc, addr, size, ud):
            if addr in self.fake:
                self.fake[addr](uc)
                uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
            elif addr in self.zero:
                uc.reg_write(UC_ARM_REG_R0, 0)
                uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
            elif addr in self.stops:
                self.calls.append((addr, uc.reg_read(UC_ARM_REG_R0)))
                uc.emu_stop()
            elif addr in self.traps:
                # record the call and return to the caller without running it
                args = tuple(uc.reg_read(r) for r in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3))
                sp = uc.reg_read(UC_ARM_REG_SP)
                stack = struct.unpack("<II", uc.mem_read(sp, 8))
                self.calls.append((addr, args, stack))
                uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

        traps = set()

        def w(self, addr, data):
            self.uc.mem_write(addr, data)

        def w16(self, addr, v):
            self.w(addr, struct.pack("<H", v))

        def w32(self, addr, v):
            self.w(addr, struct.pack("<I", v))

        def r8(self, addr):
            return self.uc.mem_read(addr, 1)[0]

        def r16(self, addr):
            return struct.unpack("<H", self.uc.mem_read(addr, 2))[0]

        def cstr(self, addr):
            return bytes(self.uc.mem_read(addr, 64)).split(b"\0")[0].decode()

        def run(self, entry, regs=None, until=None, count=5000):
            uc = self.uc
            uc.reg_write(UC_ARM_REG_SP, 0x2000E000)
            uc.reg_write(UC_ARM_REG_LR, MAGIC | 1)
            for k, v in (regs or {}).items():
                uc.reg_write(REG[k], v)
            uc.emu_start(entry | 1, until if until else MAGIC, count=count)
            return {k: uc.reg_read(REG[k]) for k in ("r0", "r4", "r5", "r6", "r8", "pc")}

    def bl_target(buf, site):
        """Decode the destination of the 32-bit `bl` at flash address `site`."""
        hi, lo = struct.unpack_from("<HH", buf, site - S.APP_BASE + 0x1000)
        s = (hi >> 10) & 1
        i1 = (~(((lo >> 13) & 1) ^ s)) & 1
        i2 = (~(((lo >> 11) & 1) ^ s)) & 1
        imm = (s << 24) | (i1 << 23) | (i2 << 22) | ((hi & 0x3FF) << 12) | ((lo & 0x7FF) << 1)
        if s:
            imm -= 1 << 25
        return site + 4 + imm

    LENG_CONVERT = 0x08019774
    LENG_SPRINTF_SITE = 0x08019B12
    UNIT = 0x200002C0

    def ref_convert(cm, unit):
        """Reference model of the intended fixed-point conversion."""
        if unit == 1:
            return cm
        if unit == 0:
            return (cm + 5) // 10                   # metres x10, rounded
        return (cm * 1000 + 1524) // 3048           # feet x10, rounded

    print("\n6. length: fixed-point unit conversion (mod)")
    vectors = [201, 250, 555, 999, 1000, 1234, 5540, 9999, 10000, 12345, 30480, 65535]
    for unit, name in ((0, "m"), (1, "cm"), (2, "ft")):
        bad = []
        for cm in vectors:
            e = Emu(mod)
            e.w(UNIT, bytes([unit]))
            r = e.run(LENG_CONVERT, {"r0": cm})
            want = ref_convert(cm, unit)
            if r["r0"] != want or r["pc"] != (MAGIC & ~1):
                bad.append((cm, r["r0"], want))
        check(not bad, f"unit {unit} ({name:2}): {len(vectors)} vectors match reference",
              "" if not bad else f"mismatch {bad[:3]}")
    # inch/metre stock behaviour, for the record
    e = Emu(stock); e.w(UNIT, b"\x02")
    r = e.run(LENG_CONVERT, {"r0": 5540})
    check(r["r0"] == 55, "stock unit 2 (Meter) 5540 cm -> whole metres", f"{r['r0']}")

    print("\n7. length: on-screen formatting through the real sprintf (mod)")
    BUF, NAME = 0x20003000, 0x20003100
    WRAPPER = bl_target(mod, LENG_SPRINTF_SITE)       # the cave formatter the draw site now calls
    for unit, cm, want in ((0, 5540, "1-2 = 55.4"), (0, 250, "1-2 = 2.5"), (0, 65535, "1-2 = 655.4"),
                           (1, 5540, "3-6 = 5540"), (2, 5540, "4-5 = 181.8"), (2, 30480, "4-5 = 1000.0"),
                           (0, 9999, "7-8 = 100.0"), (2, 201, "7-8 = 6.6"), (0, 1004, "7-8 = 10.0"),
                           (0, 1005, "7-8 = 10.1"),
                           (0, 0, "1-2 = < 2"), (1, 0, "3-6 = < 200"), (2, 0, "4-5 = < 7")):   # blind-zone pairs
        e = Emu(mod)
        e.w(UNIT, bytes([unit]))
        e.w(NAME, want.split(" =")[0].encode() + b"\0")
        val = ref_convert(cm, unit)
        # r1 = the stock "%s = %d" format string, exactly as the draw site passes it
        r = e.run(WRAPPER, {"r0": BUF, "r1": 0x08019C28, "r2": NAME, "r3": val}, count=20000)
        got = e.cstr(BUF)
        check(got == want and r["r0"] == len(want) and r["pc"] == (MAGIC & ~1),
              f"unit {unit} {cm:6} cm -> \"{got}\"", f"(expected \"{want}\")" if got != want else "")

    print("\n8. length: new reading always replaces the previous one")
    STORE_LOOP, STORE_END = 0x08012B86, 0x08012BF4
    LAST = 0x200002B8
    # stock keeps the old value while |new-old| < tol-1 (tol = 300 cm here), so the
    # first three pairs stay at 50.00 m and only the +300 cm pair gets through.
    for label, buf, want in (("stock", stock, [5000, 5000, 5000, 5300]), ("mod", mod, [5200, 5200, 5150, 5300])):
        e = Emu(buf)
        sp = 0x2000E000 - 0x5C                       # frame as laid out by the function
        for i, v in enumerate([5200, 5200, 5150, 5300]):
            e.w16(sp + 0x4C + 2 * i, v)               # new readings
        for i in range(4):
            e.w16(LAST + 2 * i, 5000)                 # previous result 50.00 m
        e.uc.reg_write(UC_ARM_REG_SP, sp)
        e.uc.reg_write(UC_ARM_REG_LR, MAGIC | 1)
        e.uc.emu_start(STORE_LOOP | 1, STORE_END, count=5000)
        got = [e.r16(LAST + 2 * i) for i in range(4)]
        check(got == want, f"{label:5}: 50.00 m then 52 m cable -> stored {[g/100 for g in got]}",
              "(sticky)" if label == "stock" else "(new value kept)")

    print("\n8b. length: the four pairs are averaged over several CSD runs (mod)")
    SITE, RERUN, ACCEPT, AFTER_INC = 0x08012AE0, 0x08011A6E, 0x08012B86, 0x08012B12
    TICKS = 0x0801C5B0                                # xTaskGetTickCount
    ACC = _probe.avg_acc
    ACC_SIZE = dict(_probe.ram_allocs)[ACC]
    N = patches.AVG_RUNS
    from unicorn import UC_HOOK_MEM_WRITE

    def test_runs(buf, runs, seed_acc=None):
        """Feed one set of four post-vote values per CSD run through the block at 0x08012AE0.
        Returns (path per run, final results, count, regs_ok, sp_ok)."""
        e = Emu(buf)
        F = 0x2000E000 - 0x5C
        if seed_acc:
            e.w(ACC, seed_acc)
        e.w32(F + 0x24, 0)                            # retry / run counter as the sequence starts
        e.w32(F + 0x20, 0x1000)                       # start tick as stamped by the sequence
        e.stops.update({AFTER_INC, ACCEPT})
        e.traps.add(TICKS)
        arena_writes = set()
        e.uc.hook_add(UC_HOOK_MEM_WRITE, lambda uc, acc, addr, size, val, ud: arena_writes.update(range(addr, addr + size)),
                      begin=S.RAM_SAFE_ARENA, end=S.RAM_SAFE_ARENA_END)
        test_runs.arena_writes = arena_writes
        test_runs.ticks = []
        path, final = [], None
        for k, vals in enumerate(runs):
            for i, v in enumerate(vals):
                e.w16(F + 0x4C + 2 * i, v)
            e.uc.reg_write(UC_ARM_REG_R0, 0x5000 + k)  # what the trapped xTaskGetTickCount returns
            e.uc.reg_write(UC_ARM_REG_SP, F)
            e.uc.reg_write(UC_ARM_REG_LR, MAGIC | 1)
            for r, v in ((UC_ARM_REG_R4, 0x44444444), (UC_ARM_REG_R5, 0x55555555), (UC_ARM_REG_R6, 0x66666666), (UC_ARM_REG_R7, 0x77777777)):
                e.uc.reg_write(r, v)
            e.uc.emu_start(SITE | 1, MAGIC, count=20000)
            pc = e.uc.reg_read(UC_ARM_REG_PC)
            test_runs.ticks.append(struct.unpack("<I", e.uc.mem_read(F + 0x20, 4))[0])
            regs = tuple(e.uc.reg_read(r) for r in (UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7))
            sp_ok = e.uc.reg_read(UC_ARM_REG_SP) == F
            regs_ok = regs == (0x44444444, 0x55555555, 0x66666666, 0x77777777)
            if pc == AFTER_INC:
                path.append(("rerun", e.uc.mem_read(F + 0x24, 4)[0], regs_ok, sp_ok))
                continue
            if pc == ACCEPT:
                final = [e.r16(F + 0x4C + 2 * i) for i in range(4)]
                path.append(("accept", e.uc.mem_read(F + 0x24, 4)[0], regs_ok, sp_ok))
                break
            path.append((f"pc=0x{pc:08X}", None, regs_ok, sp_ok))
            break
        return path, final

    runs = [(1440, 1460, 1500, 1480), (1470, 1450, 1490, 1500), (1450, 1470, 1480, 1460), (1460, 1440, 1510, 1470)]
    path, final = test_runs(mod, runs)
    want = [sum(r[i] for r in runs) // N for i in range(4)]
    ok = ([p[0] for p in path] == ["rerun"] * (N - 1) + ["accept"] and final == want
          and all(p[2] and p[3] for p in path) and [p[1] for p in path][:N - 1] == list(range(1, N)))
    check(ok, f"mod: {N} runs of a 14 m cable -> per-pair means {[f/100 for f in final] if final else None}, counter 1..{N - 1} then accept, r4-r7 and sp intact",
          "" if ok else f"{path} {final}")
    check(test_runs.ticks == [0x5000 + k for k in range(N)],
          "mod: the 20 s timeout start tick is re-stamped from xTaskGetTickCount on every run", f"{[hex(t) for t in test_runs.ticks]}")
    check(test_runs.arena_writes and test_runs.arena_writes <= set(range(ACC, ACC + ACC_SIZE)),
          f"mod: every RAM-arena write of the hook lies inside its own {ACC_SIZE}-byte allocation at 0x{ACC:08X} (no aliasing with other patches)",
          f"{sorted(hex(a) for a in test_runs.arena_writes - set(range(ACC, ACC + ACC_SIZE)))[:4]}")
    allocs = sorted(_probe.ram_allocs)
    check(all(a + sz <= b for (a, sz), (b, _) in zip(allocs, allocs[1:])), "RAM arena allocations of all patches are disjoint", f"{[(hex(a), sz) for a, sz in allocs]}")
    hook_new = next(new for addr, old, new, why, kind in EXPECTED_EDITS if addr == patches.DEAD_BODY)
    hook_lit = struct.unpack_from("<I", mod, patches.DEAD_BODY + len(hook_new) - 4 - S.APP_BASE + 0x1000)[0]
    check(hook_lit == ACC and len(hook_new) <= patches.DEAD_BODY_END - patches.DEAD_BODY,
          f"the hook's accumulator literal is the allocated address; hook is {len(hook_new)} of {patches.DEAD_BODY_END - patches.DEAD_BODY} bytes",
          f"0x{hook_lit:08X}")
    runs2 = [(1440, 0, 1500, 0), (1470, 1450, 0, 0), (0, 1470, 1480, 0), (1460, 1440, 1510, 0)]
    path, final = test_runs(mod, runs2)
    check(final == [(1440 + 1470 + 1460) // 3, (1450 + 1470 + 1440) // 3, (1500 + 1480 + 1510) // 3, 0],
          "mod: a pair that read 0 (out of range) in some runs is averaged over the others; a pair that never read stays 0",
          f"{final}")
    path, final = test_runs(mod, [(334, 335, 333, 334)] * N)
    check(final == [334, 335, 333, 334] and len(path) == N, "mod: identical runs come back unchanged (no rounding drift)", f"{final}")
    path, final = test_runs(mod, runs, seed_acc=b"\xff" * 20)
    check(final == want, "mod: stale accumulator from a previous test (or power-on garbage) is ignored on run 0", f"{final}")
    path, final = test_runs(mod, [(300, 300, 300, 300)] * N)
    check(final == [300] * N and len(path) == N, f"mod: it always takes {N} runs, even when all four pairs agree", f"{[p[0] for p in path]}")
    # stock, for the record: accepts when the four agree, otherwise retries once
    path, final = test_runs(stock, [(1440, 1460, 1500, 1480), (1470, 1450, 1490, 1500)])
    check([p[0] for p in path] == ["rerun", "accept"] and final == [1470, 1450, 1490, 1500],
          "stock: disagreeing pairs -> one retry, then the second run is shown as is", f"{[p[0] for p in path]} {final}")
    path, final = test_runs(stock, [(1440, 1440, 1440, 1440)])
    check([p[0] for p in path] == ["accept"], "stock: agreeing pairs -> the first run is shown as is")

    print("\n9. battery: low-voltage debounce and recovery (mod)")
    ADC_PTR, ADC_BUF = 0x20000170, 0x20000F00        # adc_raw_read: *(u16*)(*(u32*)0x20000170)
    def set_mv(e, mv):
        """Load the ADC sample for `mv`; returns the mV the firmware will compute
        from it (12-bit quantisation: raw*2*3300/4096)."""
        raw = -(-mv * 4096 // 6600)                   # ceil, so `mv` itself is reachable
        e.w32(ADC_PTR, ADC_BUF)
        e.w16(ADC_BUF, raw)
        return raw * 6600 // 4096
    LOWCHK = bl_target(mod, 0x0800E6E2)
    e = Emu(mod)
    seq = [(3100, 0), (3100, 0), (3100, 1), (3200, 0), (3100, 0), (3149, 0), (3100, 1), (3150, 0)]
    got = []
    for mv, _ in seq:
        r = e.run(LOWCHK, {"r5": mv})
        got.append(r["r0"])
    check(got == [w for _, w in seq], "arms on the 3rd consecutive sample < 3150 mV, resets on a healthy one",
          f"{[m for m,_ in seq]} -> {got}")
    # stock: a single sample arms immediately (movw/cmp/bge inline)
    e = Emu(stock)
    e.w(0x2000003D, b"\xff")
    r = e.run(0x0800E6E2, {"r5": 3100, "r4": 0}, until=0x0800E6F0)
    check(e.r8(0x2000003D) == 30, "stock: one sample < 3150 mV arms the 30 s countdown", f"ctr={e.r8(0x2000003D)}")

    CANCEL = bl_target(mod, 0x0800DD5C)
    def gpio_no_charger(e):
        e.w32(0x40011008, 0xFFFF)                    # GPIOC IDR: PC10 high = no CHRG
        e.w32(0x40010808, 0xFFFF)                    # GPIOA IDR: PA15 high = no STDBY
    for mv, chrg, want in ((3100, False, 0), (3248, False, 0), (3250, False, 1), (3600, False, 1), (3100, True, 1)):
        e = Emu(mod)
        gpio_no_charger(e)
        if chrg:
            e.w32(0x40011008, 0x0000)
        seen = set_mv(e, mv)
        r = e.run(CANCEL)
        check((r["r0"] != 0) == (want != 0),
              f"tick: {seen} mV, charger={'yes' if chrg else 'no ':3} -> cancel={'yes' if r['r0'] else 'no'}")

    print("\n10. battery: 10-step gauge (mod)")
    PCT_SITE, PCT_END = 0x080107CA, 0x080107FA
    table = [(4200, 100), (4150, 100), (4149, 90), (4050, 90), (4000, 80), (3950, 80), (3900, 70),
             (3870, 70), (3800, 60), (3760, 50), (3750, 50), (3700, 40), (3650, 30), (3600, 20),
             (3500, 10), (3450, 10), (3449, 0), (3000, 0)]
    bad = []
    for mv, want in table:
        e = Emu(mod)
        r = e.run(PCT_SITE, {"r5": mv, "r4": 0}, until=PCT_END)
        if r["r4"] != want or r["pc"] != PCT_END:
            bad.append((mv, r["r4"], want))
    check(not bad, f"percent curve: {len(table)} points", "" if not bad else f"{bad[:4]}")
    stock_pts = []
    for mv in (4200, 3900, 3700, 3000):
        e = Emu(stock)
        r = e.run(PCT_SITE, {"r5": mv, "r4": 0}, until=PCT_END)
        stock_pts.append(r["r4"])
    check(stock_pts == [100, 80, 50, 20], "stock: four-step table", f"{stock_pts}")

    GAUGE, GAUGE_END = 0x0800E774, 0x0800E7B2
    for label, buf, cases in (
            ("mod", mod, [(70, 0, 7, 0xFFFF), (20, 0, 2, 0xF800), (10, 0, 1, 0xF800), (100, 0, 10, 0xFFFF),
                          (50, 1, 3, 0xFFFF), (0, 0, 0, 0xF800)]),
            ("stock", stock, [(70, 0, 0, 0xFFFF), (20, 0, 2, 0xF800), (100, 0, 10, 0xFFFF)])):
        bad = []
        for pct, blink, want_seg, want_col in cases:
            e = Emu(buf)
            e.w(0x2000003F, bytes([pct]))
            e.w(0x2000003C, bytes([blink]))
            r = e.run(GAUGE, {"r6": 0, "r8": 0xFFFF, "r0": 0}, until=GAUGE_END)
            if (r["r6"], r["r8"] & 0xFFFF) != (want_seg, want_col):
                bad.append((pct, blink, r["r6"], hex(r["r8"] & 0xFFFF)))
        check(not bad, f"{label:5}: gauge segments/colour for {[c[0] for c in cases]} %",
              "" if not bad else f"{bad}")

    print("\n11. settings save frees its buffer (mod)")
    VPORTFREE = 0x0801C6F8
    def frame(e):
        # the function's pop {r3-r7, pc}: six words on the stack, pc slot -> MAGIC
        for i in range(6):
            e.w32(0x2000E000 + 4 * i, MAGIC | 1)
    for entry, label in ((0x080100EA, "success path"), (0x08010086, "failed path")):
        e = Emu(mod)
        frame(e)
        e.stops.add(VPORTFREE)
        e.run(entry, {"r5": 0x20005000}, count=50)
        check(e.calls and e.calls[0] == (VPORTFREE, 0x20005000),
              f"{label}: vPortFree(staging buffer) is called", f"{[hex(a) for a, _ in e.calls]}")
    e = Emu(stock)
    frame(e)
    e.stops.add(VPORTFREE)
    e.run(0x080100EA, {"r5": 0x20005000}, count=50)
    check(not e.calls and e.uc.reg_read(UC_ARM_REG_PC) == (MAGIC & ~1), "stock: returns without freeing")

    # ------------------------------------------------------------------
    SETTINGS = 0x20000C78
    NVP_B, UNIT_B, ZERO_B = SETTINGS + 0xA6, SETTINGS + 0xA7, SETTINGS + 0xC5
    ADJ = _probe.adj_target
    GUI_MSG_SEND, KEY_NOTIFY, GUI_BLIT, SPRINTF = 0x0800E428, 0x080116BC, 0x080174E8, 0x0800A38C
    RESULT_DRAW, SYSSTATE = 0x080199B0, 0x2000013C

    def ref_nvp(cm, nvp):
        return (cm * nvp + 34) // 69 if 50 <= nvp <= 99 else cm

    def ref_zero(cm, zero):
        if zero > 20:
            return cm
        return max(cm - 10 * zero, 0)

    print("\n12. length: Zero offset and NVP scaling in the conversion (mod)")
    for nvp in (0, 69, 75, 50, 99, 120, 49, 100, 255):
        bad = []
        for unit in (0, 1, 2):
            for cm in (201, 5540, 10000, 20000):
                e = Emu(mod)
                e.w(UNIT, bytes([unit]))
                e.w(NVP_B, bytes([nvp]))
                e.w(ZERO_B, b"\x00")
                r = e.run(LENG_CONVERT, {"r0": cm})
                want = ref_convert(ref_nvp(cm, nvp), unit)
                if r["r0"] != want:
                    bad.append((unit, cm, r["r0"], want))
        label = f"NVP byte {nvp:3}, Zero 0" + (" (factory/identity)" if nvp in (0, 69, 120) else "")
        check(not bad, f"{label}: 12 vectors match reference", "" if not bad else f"{bad[:3]}")
    for zero in (4, 20, 1, 21, 255):
        bad = []
        for nvp in (0, 67, 99):
            for unit in (0, 1, 2):
                for cm in (0, 30, 40, 41, 201, 334, 1470, 5540, 20000):
                    e = Emu(mod)
                    e.w(UNIT, bytes([unit]))
                    e.w(NVP_B, bytes([nvp]))
                    e.w(ZERO_B, bytes([zero]))
                    r = e.run(LENG_CONVERT, {"r0": cm})
                    want = ref_convert(ref_nvp(ref_zero(cm, zero), nvp), unit)
                    if r["r0"] != want:
                        bad.append((nvp, unit, cm, r["r0"], want))
        label = f"Zero byte {zero:3}" + (" (out of range = no offset)" if zero > 20 else f" (= {zero / 10} m)")
        check(not bad, f"{label}: 81 vectors match reference", "" if not bad else f"{bad[:3]}")
    e = Emu(mod); e.w(UNIT, b"\x00"); e.w(NVP_B, bytes([75])); e.w(ZERO_B, b"\x00")
    r = e.run(LENG_CONVERT, {"r0": 5540})
    check(r["r0"] == 602, "55.40 m cable at NVP 75 %, Zero 0.0 reads 60.2 m", f"{r['r0'] / 10} m")
    e = Emu(mod); e.w(UNIT, b"\x00"); e.w(NVP_B, bytes([67])); e.w(ZERO_B, bytes([4]))
    r1 = e.run(LENG_CONVERT, {"r0": 334})["r0"]
    r2 = e.run(LENG_CONVERT, {"r0": 1470})["r0"]
    check((r1, r2) == (29, 139), "measured unit: raw 3.34 m / 14.7 m at Zero 0.4 m, NVP 67 % read 2.9 m / 13.9 m (68 %: 14.1 m)",
          f"{r1 / 10} m, {r2 / 10} m")
    e = Emu(mod); e.w(UNIT, b"\x00"); e.w(NVP_B, bytes([69])); e.w(ZERO_B, bytes([4]))
    r1 = e.run(LENG_CONVERT, {"r0": 40})["r0"]
    r2 = e.run(LENG_CONVERT, {"r0": 0})["r0"]
    check((r1, r2) == (0, 0), "a reading at or below the Zero, and a stock 0, stay 0 (out of range)", f"{r1}, {r2}")
    e = Emu(stock); e.w(UNIT, b"\x02"); e.w(ZERO_B, bytes([4])); e.w(NVP_B, bytes([67]))
    r = e.run(LENG_CONVERT, {"r0": 334})
    check(r["r0"] == 3, "stock: ignores both bytes (unit 2 = whole metres, 334 cm -> 3)", f"{r['r0']}")

    print("\n13. length: unit remembered across screens, adjust target reset (mod)")
    for stored, want in ((0, 0), (1, 1), (2, 2), (3, 0), (7, 0), (255, 0)):
        e = Emu(mod)
        e.w(UNIT_B, bytes([stored]))
        e.w(UNIT, b"\x01")
        e.w(ADJ, b"\x01")
        e.run(0x08012F1C, {"r1": 0x200002B4}, until=0x08012F20)
        check(e.r8(UNIT) == want and e.r8(ADJ) == 0,
              f"entry: settings unit {stored:3} -> Length screen unit {e.r8(UNIT)}, UP/DOWN target = NVP")
    e = Emu(stock); e.w(UNIT, b"\x00")
    e.run(0x08012F1C, {"r1": 0x200002B4}, until=0x08012F20)
    check(e.r8(UNIT) == 1, "stock: every entry forces unit 1 (cm)", f"unit={e.r8(UNIT)}")
    e = Emu(mod); e.w(UNIT, b"\x02"); e.w(UNIT_B, b"\x00")
    r = e.run(0x08012EC8, until=0x08012ECE)
    check(e.r8(UNIT_B) == 2 and (r["r0"], e.uc.reg_read(UC_ARM_REG_R1), e.uc.reg_read(UC_ARM_REG_R2)) == (0x1C, 0, 0),
          "unit change: stored to settings and GUI_MSG_SEND(0x1C) args intact",
          f"settings unit={e.r8(UNIT_B)} r0=0x{r['r0']:X}")

    print("\n14. NVP: UP/DOWN key hook on the Length screen (mod)")
    KEY_HOOK = bl_target(mod, 0x08014A04)
    KEYBUF = 0x20003200
    def press(state, key, evt, nvp, adj=0, zero=0):
        e = Emu(mod)
        e.w(SYSSTATE, bytes([state]))
        e.w(NVP_B, bytes([nvp]))
        e.w(ZERO_B, bytes([zero]))
        e.w(ADJ, bytes([adj]))
        e.w(KEYBUF, bytes([key, evt]))
        e.traps.update({GUI_MSG_SEND, KEY_NOTIFY})
        r = e.run(KEY_HOOK, {"r5": KEYBUF, "r4": 0x44444444, "r6": 0x66666666})
        msgs = [c[1][0] for c in e.calls if c[0] == GUI_MSG_SEND]
        press.bad_args = [c[1][:3] for c in e.calls if c[0] == GUI_MSG_SEND and c[1][1:3] != (0, 0)]
        notified = any(c[0] == KEY_NOTIFY for c in e.calls)
        press.last = e
        press.regs_ok = (r["r4"], r["r5"], r["r6"]) == (0x44444444, KEYBUF, 0x66666666)
        return e.r8(NVP_B), msgs, notified, r["r0"]
    UP, DOWN, OK, CLICK, LONG, REPEAT = 2, 3, 4, 3, 6, 12
    v, m, n, st = press(7, UP, CLICK, 0)
    check((v, m, n, st) == (70, [0x3D], True, 0x80), "LENGTH, UP click, byte 0 (=69%) -> 70 %, GUI 0x3D, activity, state mask kept",
          f"nvp={v} msgs={[hex(x) for x in m]} notify={n} r0=0x{st:X}")
    check(not press.bad_args and press.regs_ok, "GUI_MSG_SEND(0x3D, 0, 0): no payload pointer; r4/r5/r6 preserved by the hook",
          f"bad args {press.bad_args}" if press.bad_args else "")
    v, m, n, st = press(7, DOWN, CLICK, 70)
    check((v, m) == (69, [0x3D]), "LENGTH, DOWN click, 70 -> 69", f"nvp={v}")
    v, m, n, st = press(7, UP, REPEAT, 80)
    check((v, m) == (81, [0x3D]), "auto-repeat counts as a press", f"nvp={v}")
    v, m, n, st = press(7, UP, LONG, 80)
    check((v, m, n) == (80, [], False), "long press ignored", f"nvp={v} msgs={m}")
    v, m, n, st = press(7, UP, CLICK, 99)
    check((v, m) == (99, []), "clamped at 99 %", f"nvp={v}")
    v, m, n, st = press(7, DOWN, CLICK, 50)
    check((v, m) == (50, []), "clamped at 50 %", f"nvp={v}")
    v, m, n, st = press(2, UP, CLICK, 0)
    check((v, m, st) == (0, [], 0x04), "HOME screen: UP untouched, state mask 1<<2 returned", f"nvp={v} r0=0x{st:X}")
    v, m, n, st = press(7, OK, CLICK, 0)
    check((v, m) == (0, []) and press.last.r8(ADJ) == 0, "LENGTH, OK click: not ours (stock Test Start)", f"nvp={v}")
    v, m, n, st = press(7, OK, LONG, 70)
    check((v, m, n, st, press.last.r8(ADJ)) == (70, [0x3D], True, 0x80, 1),
          "LENGTH, OK long press: target NVP -> ZERO, GUI 0x3D, NVP untouched",
          f"adj={press.last.r8(ADJ)} nvp={v} msgs={[hex(x) for x in m]}")
    v, m, n, st = press(7, OK, LONG, 70, adj=1)
    check((m, press.last.r8(ADJ)) == ([0x3D], 0), "LENGTH, OK long press again: target ZERO -> NVP", f"adj={press.last.r8(ADJ)}")
    v, m, n, st = press(7, OK, REPEAT, 70, adj=1)
    check((m, press.last.r8(ADJ)) == ([], 1), "LENGTH, OK auto-repeat: ignored (no double toggle)", f"adj={press.last.r8(ADJ)}")
    v, m, n, st = press(2, OK, LONG, 70, adj=0)
    check((m, press.last.r8(ADJ)) == ([], 0), "HOME screen, OK long press: untouched", f"adj={press.last.r8(ADJ)}")
    ignored = []
    for evt in (1, 7, 8, 9, 10, 11):
        v, m, n, st = press(7, OK, evt, 70, adj=1, zero=4)
        if m or press.last.r8(ADJ) != 1 or v != 70 or press.last.r8(ZERO_B) != 4:
            ignored.append(evt)
    check(not ignored, "LENGTH, OK events 1/7/8/9/10/11 (press, releases, 2 s and 5 s holds): all ignored, no double toggle", f"acted on {ignored}")
    for key in (0, 1, 5):
        for evt in (CLICK, LONG, REPEAT):
            v, m, n, st = press(7, key, evt, 70, adj=0, zero=4)
            if m or v != 70 or press.last.r8(ZERO_B) != 4 or press.last.r8(ADJ) != 0:
                ignored.append((key, evt))
            v, m, n, st = press(7, key, evt, 70, adj=1, zero=4)
            if m or v != 70 or press.last.r8(ZERO_B) != 4 or press.last.r8(ADJ) != 1:
                ignored.append((key, evt, 1))
    check(not ignored, "LENGTH, POWER / LEFT / RIGHT keys: never touch NVP, Zero or the target (stock unit change keeps working)", f"acted on {ignored}")
    for evt, z0, key, want, label in ((CLICK, 0, UP, 1, "ZERO 0.0 -> 0.1 on UP click"),
                                      (REPEAT, 4, UP, 5, "ZERO 0.4 -> 0.5 on UP auto-repeat"),
                                      (CLICK, 4, DOWN, 3, "ZERO 0.4 -> 0.3 on DOWN click"),
                                      (CLICK, 20, UP, 20, "clamped at 2.0 m"),
                                      (CLICK, 0, DOWN, 0, "clamped at 0.0 m"),
                                      (CLICK, 255, UP, 1, "garbage byte counts as 0.0 -> 0.1")):
        v, m, n, st = press(7, key, evt, 70, adj=1, zero=z0)
        z = press.last.r8(ZERO_B)
        moved = want != z0 and z0 <= 20
        ok = z == want and v == 70 and (m == [0x3D]) == (z != z0 or z0 > 20) and st == 0x80
        check(ok, f"ZERO target: {label}", f"zero={z} nvp={v} msgs={[hex(x) for x in m]}")
    v, m, n, st = press(7, UP, CLICK, 70, adj=0, zero=4)
    check((v, press.last.r8(ZERO_B)) == (71, 4), "NVP target: UP changes NVP, Zero untouched", f"nvp={v} zero={press.last.r8(ZERO_B)}")

    print("\n14b. end to end: Action_key_Process in the LENGTH state (mod and stock)")
    ACTION, DISPATCH, AUTOOFF_RESET = 0x080149FC, 0x0800D2B4, 0x0800F9C0

    def action(buf, key, evt, nvp=70, zero=4, adj=0):
        e = Emu(buf)
        e.w(SYSSTATE, bytes([7]))
        e.w(NVP_B, bytes([nvp])); e.w(ZERO_B, bytes([zero])); e.w(ADJ, bytes([adj]))
        e.w(KEYBUF, bytes([key, evt]))
        e.traps.update({DISPATCH, GUI_MSG_SEND, KEY_NOTIFY, AUTOOFF_RESET})
        e.stops.add(0x08014A4E)                       # the LOG macro body: stop there and skip it
        e.run(ACTION, {"r0": KEYBUF}, count=200000)
        if e.uc.reg_read(UC_ARM_REG_PC) == 0x08014A4E:
            e.calls.pop()                             # the stop record
            e.uc.emu_start(0x08014AC0 | 1, MAGIC, count=200000)
        dispatched = [c[1][0] for c in e.calls if c[0] == DISPATCH]
        msgs = [c[1][0] for c in e.calls if c[0] == GUI_MSG_SEND]
        return dispatched, msgs, e.r8(NVP_B), e.r8(ZERO_B), e.r8(ADJ), e.uc.reg_read(UC_ARM_REG_PC) == (MAGIC & ~1)

    cases = (("OK click", OK, CLICK, [0x11], [], 70, 4, 0), ("LEFT click", 1, CLICK, [0x13], [], 70, 4, 0),
             ("RIGHT click", 5, CLICK, [0x12], [], 70, 4, 0), ("UP click", UP, CLICK, [], [0x3D], 71, 4, 0),
             ("DOWN repeat", DOWN, REPEAT, [], [0x3D], 69, 4, 0), ("OK 1 s hold", OK, LONG, [], [0x3D], 70, 4, 1),
             ("OK 2 s hold", OK, 8, [], [], 70, 4, 0), ("OK release", OK, 7, [], [], 70, 4, 0))
    for label, key, evt, want_d, want_m, want_nvp, want_zero, want_adj in cases:
        d, m, nv, z, adj, ret = action(mod, key, evt)
        ok = (d, m, nv, z, adj, ret) == (want_d, want_m, want_nvp, want_zero, want_adj, True)
        check(ok, f"mod, {label}: stock actions {[hex(x) for x in d]}, messages {[hex(x) for x in m]}, nvp {nv} zero {z} target {adj}",
              "" if ok else f"wanted {[hex(x) for x in want_d]} {[hex(x) for x in want_m]} {want_nvp} {want_zero} {want_adj}")
    d, m, nv, z, adj, ret = action(mod, UP, CLICK, adj=1)
    check((d, m, z, nv) == ([], [0x3D], 5, 70), "mod, UP click with Zero selected: Zero 0.4 -> 0.5, NVP untouched, no stock action")
    for label, key, evt, want_d in (("OK click", OK, CLICK, [0x11]), ("UP click", UP, CLICK, []), ("OK 1 s hold", OK, LONG, [])):
        d, m, nv, z, adj, ret = action(stock, key, evt)
        check((d, m, nv, z, ret) == (want_d, [], 70, 4, True), f"stock, {label}: actions {[hex(x) for x in d]}, no message, bytes untouched")

    print("\n15. NVP: GUI message 0x3D and the on-screen text (mod)")
    for msg, want_at, label in ((0x10, 0x0800F490, "0x10 -> stock jump table"), (0xFF, 0x0800F4DC, "0xFF -> exit (shutdown filter)")):
        e = Emu(mod)
        r = e.run(0x0800F48C, {"r0": msg}, until=want_at, count=20)
        check(r["pc"] == want_at and r["r0"] == msg, f"message {label}", f"pc=0x{r['pc']:08X}")
    COLOUR = 0x200001AC

    def redraw(nvp, zero, adj):
        """Run GUI message 0x3D with gui_blit trapped; returns [(x, y, w, h, size, text, fg, bg)], e."""
        e = Emu(mod)
        e.w(NVP_B, bytes([nvp])); e.w(ZERO_B, bytes([zero])); e.w(ADJ, bytes([adj]))
        e.w(COLOUR, struct.pack("<HH", 0x07E0, 0x7304))     # sentinel: the picker leaves its box colours here
        seen = []

        def hook(uc, addr, size, ud):          # records each blit at call time (the trap in Emu skips it)
            if addr == GUI_BLIT:
                a = tuple(uc.reg_read(r) for r in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3))
                sp = uc.reg_read(UC_ARM_REG_SP)
                fs, sp_ = struct.unpack("<II", uc.mem_read(sp, 8))
                fg, bg = struct.unpack("<HH", uc.mem_read(COLOUR, 4))
                seen.append((*a, fs, e.cstr(sp_), fg, bg))
        e.uc.hook_add(UC_HOOK_CODE, hook)
        e.traps.update({GUI_BLIT, RESULT_DRAW})
        r = e.run(0x0800F48C, {"r0": 0x3D}, until=0x0800F4DC, count=40000)
        return seen, e, r

    blits, e, r = redraw(72, 4, 0)
    want = [(166, 90, 56, 16, 0x10, "NVP 72%", 0xFFFF, 0x0000), (4, 90, 72, 16, 0x10, "ZERO 0.4m", 0x8410, 0x0000)]
    check(blits == want and r["pc"] == 0x0800F4DC,
          '0x3D, NVP active: gui_blit(166, 90, 56, 16, "NVP 72%") white, gui_blit(4, 90, 72, 16, "ZERO 0.4m") grey, then exit',
          "" if blits == want else f"{blits}")
    check(any(c[0] == RESULT_DRAW for c in e.calls), "0x3D: length_result_draw called after the texts")
    blits, e, r = redraw(72, 4, 1)
    check([b[6] for b in blits] == [0x8410, 0xFFFF] and [b[5] for b in blits] == ["NVP 72%", "ZERO 0.4m"],
          "0x3D, ZERO active: NVP grey, ZERO white", f"{[(b[5], hex(b[6])) for b in blits]}")
    for nvp, zero, adj, want in ((0, 0, 0, ("NVP 69%", "ZERO 0.0m")), (50, 20, 0, ("NVP 50%", "ZERO 2.0m")),
                                 (99, 15, 1, ("NVP 99%", "ZERO 1.5m")), (255, 255, 7, ("NVP 69%", "ZERO 0.0m"))):
        blits, e, r = redraw(nvp, zero, adj)
        got = tuple(b[5] for b in blits)
        cols = tuple((b[6], b[7]) for b in blits)
        want_cols = ((0xFFFF, 0), (0x8410, 0)) if adj != 1 else ((0x8410, 0), (0xFFFF, 0))
        check(got == want and cols == want_cols, f'bytes NVP {nvp:3} Zero {zero:3} adj {adj} -> {got}, colours {[hex(c[0]) for c in cols]} on black',
              "" if cols == want_cols else f"{cols}")

    print("\n16. NVP: drawn when the Length screen opens (mod)")
    e = Emu(mod)
    e.w(NVP_B, bytes([69]))
    F = 0x2000E000 - 0x28
    for i in range(4):
        e.w32(F + 0x14 + 4 * i, 0x44444444 + i)      # saved r4..r7
    e.w32(F + 0x24, MAGIC | 1)                        # saved lr
    e.traps.add(GUI_BLIT)
    texts = []
    e.uc.hook_add(UC_HOOK_CODE, lambda uc, addr, size, ud: texts.append(
        e.cstr(struct.unpack("<II", uc.mem_read(uc.reg_read(UC_ARM_REG_SP), 8))[1])) if addr == GUI_BLIT else None)
    e.uc.reg_write(UC_ARM_REG_SP, F)
    e.uc.emu_start(0x08019970 | 1, MAGIC, count=20000)
    sp_after = e.uc.reg_read(UC_ARM_REG_SP)
    regs = tuple(e.uc.reg_read(r) for r in (UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7))
    check(texts == ["NVP 69%", "ZERO 0.0m"] and sp_after == F + 0x28
          and regs == (0x44444444, 0x44444445, 0x44444446, 0x44444447),
          "epilogue draws both texts, then returns with the stack and r4-r7 restored",
          f"texts={texts} sp=+0x{sp_after - F:X} r7=0x{e.uc.reg_read(UC_ARM_REG_R7):X}")

    print("\n16b. Factory Reset clears the Zero byte (mod) and writes the same defaults as stock")
    DEFAULTS, NETCFG_A, NETCFG_B = 0x0801958C, 0x080131BC, 0x080119B0
    def defaults(buf):
        e = Emu(buf)
        e.w(SETTINGS, b"\xa5" * 0xC8)
        e.traps.update({NETCFG_A, NETCFG_B})
        e.run(DEFAULTS, count=20000)
        return bytes(e.uc.mem_read(SETTINGS, 0xC8)), e
    got_m, em = defaults(mod)
    got_s, es = defaults(stock)
    diff = [i for i in range(0xC8) if got_m[i] != got_s[i]]
    check(diff == [0xC5] and got_m[0xC5] == 0 and got_s[0xC5] == 0xA5,
          "defaults writer: identical to stock except byte 0xC5 (Zero) = 0",
          f"differs at {[hex(i) for i in diff]}")
    check([c[0] for c in em.calls] == [NETCFG_A, NETCFG_B] and em.uc.reg_read(UC_ARM_REG_PC) == (MAGIC & ~1),
          "defaults writer: still calls the two stock finishers and returns", f"{[hex(c[0]) for c in em.calls]}")
    check(got_m[0xA6] == 0 and got_m[0xA7] == 0 and got_m[0xA8] == 1 and got_m[0xA2] == 2 and got_m[0xA5] == 2,
          "defaults: NVP 0 (=69 %), unit 0 (m), first-boot picker, auto-off 10 min, language 2 (Thai) preselected")

    print("\n17. fonts: the firmware's own glyph drawers over the new tables")
    import fonts
    PUT_PIXEL = 0x08016BF0
    def draw_glyph(buf, fn, a0, a1, a2, a3, stack0=0):
        """Run a glyph drawer and collect the pixels it sets (put_pixel is trapped)."""
        e = Emu(buf)
        e.w(0x20000F54, struct.pack("<HH", 240, 320))         # screen size
        e.w(0x200001AC, struct.pack("<HH", 0xFFFF, 0x0000))    # fg / bg
        e.w32(0x2000E000, stack0)                              # 5th argument
        px = {}
        def hook(uc, addr, size, ud):
            if addr == PUT_PIXEL:
                x, y = uc.reg_read(UC_ARM_REG_R0), uc.reg_read(UC_ARM_REG_R1)
                col = struct.unpack("<H", uc.mem_read(0x200001AC, 2))[0]
                if col == 0xFFFF:
                    px[(x, y)] = 1
                uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
        e.uc.hook_add(UC_HOOK_CODE, hook)
        e.run(fn, {"r0": a0, "r1": a1, "r2": a2, "r3": a3}, count=400000)
        return px
    def as_rows(px, w, h):
        return [[px.get((x, y), 0) for x in range(w)] for y in range(h)]
    THAI = any(_p.pid == "thai-ui" and _p.default for _p in patches.REGISTRY)
    for name, (addr, n, w, h, per) in fonts.TABLES.items():
        blob_mod = mod[addr - S.APP_BASE + 0x1000: addr - S.APP_BASE + 0x1000 + n * per]
        if name == "cjk16" and THAI:
            from thai.cells import Table
            ttab = Table.shipped(os.path.join(HERE, "fonts_out"))
            n_used = len(ttab.order)
            blob_new = ttab.blob()
            check(blob_mod[:n_used * 32] == blob_new[:n_used * 32],
                  f"thai16: the first {n_used} cells in the image are fonts_out/thai16.bin (Sarabun {ttab.meta['size']} px)")
            intended = fonts.unpack_table(name, blob_new)
            bad = []
            for i in range(n_used):
                px = draw_glyph(mod, 0x08017550, 0, 0, i, 1)
                if as_rows(px, w, h) != intended[i] or any(x >= w or y >= h for x, y in px):
                    bad.append(i)
            check(not bad, f"thai16: all {n_used} cells render exactly as designed through the stock glyph drawer",
                  "" if not bad else f"mismatch at indices {bad[:6]}")
            continue
        blob_new = open(os.path.join(HERE, "fonts_out", f"{name}.bin"), "rb").read()
        check(blob_mod == blob_new, f"{name}: table in the image is fonts_out/{name}.bin ({n} glyphs, {len(blob_new)} bytes)")
        intended = fonts.unpack_table(name, blob_new)
        bad = []
        for i in range(n):
            if name == "cjk16":
                px = draw_glyph(mod, 0x08017550, 0, 0, i, 1)
            else:
                px = draw_glyph(mod, 0x080171D4, 0, 0, 0x20 + i, h)
            if as_rows(px, w, h) != intended[i] or any(x >= w or y >= h for x, y in px):
                bad.append(i)
        check(not bad, f"{name}: all {n} glyphs render exactly as designed, inside the {w}x{h} cell",
              "" if not bad else f"mismatch at indices {bad[:6]}")
    # the same harness on stock proves it is not vacuous
    stock_px = draw_glyph(stock, 0x080171D4, 0, 0, ord("A"), 16)
    stock_tbl = fonts.unpack_table("ascii16", stock[0x08065D78 - S.APP_BASE + 0x1000:][:95 * 16])
    check(as_rows(stock_px, 8, 16) == stock_tbl[ord("A") - 0x20], "stock: harness reproduces the stock 'A' from the stock table")
    print("\n18. identity: version strings and the bootloader-facing name")
    for label, addr in (("About screen", 0x08011660), ("boot log", 0x08012E6C)):
        e = Emu(mod)
        r = e.run(SPRINTF, {"r0": 0x20003400, "r1": 0x08011668, "r2": addr}, count=20000)   # "Software:%s"
        got = e.cstr(0x20003400)
        check(got == f"Software:{patches.VERSION}", f'{label}: sprintf("Software:%s") -> "{got}"')
    e = Emu(stock)
    e.run(SPRINTF, {"r0": 0x20003400, "r1": 0x08011668, "r2": 0x08011660}, count=20000)
    check(e.cstr(0x20003400) == "Software:V2.0.7", "stock: still reports V2.0.7", e.cstr(0x20003400))
    check(mod[:0x20] == stock[:0x20], "container name unchanged for the bootloader",
          mod[:0x20].split(b"\0")[0].decode())

    print("\n18c. SCAN screen: mode labels through the stock draw code (mod and stock)")
    LANG_IS = 0x0800FD2C                              # (2) -> non-zero when the UI language is Chinese

    def scan_labels(buf):
        seen = []
        for start, end in ((0x080141C0, 0x080141F2), (0x0801425E, 0x08014294)):
            e = Emu(buf)
            e.traps.update({GUI_BLIT, LANG_IS})       # LANG_IS trapped returns r0 = 0: English

            def hook(uc, addr, size, ud, e=e, seen=seen):
                if addr == GUI_BLIT:
                    args = tuple(uc.reg_read(r) for r in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3))
                    fs, sp_ = struct.unpack("<II", uc.mem_read(uc.reg_read(UC_ARM_REG_SP), 8))
                    seen.append((args, fs, e.cstr(sp_)))
                elif addr == LANG_IS:
                    uc.reg_write(UC_ARM_REG_R0, 0)
            e.uc.hook_add(UC_HOOK_CODE, hook)
            e.uc.reg_write(UC_ARM_REG_SP, 0x2000E000 - 0x1C)
            e.uc.emu_start(start | 1, end, count=2000)
        return seen
    got = scan_labels(mod)
    want = [((92, 221, 56, 16), 16, "Digital"), ((96, 260, 48, 16), 16, "825 Hz")]
    check(got == want, 'mod: mode 1 "Digital" at (92, 221, 56, 16), mode 2 "825 Hz" at (96, 260, 48, 16), both centred on x = 120',
          "" if got == want else f"{got}")
    got = scan_labels(stock)
    check(got == [((84, 221, 72, 16), 16, "Noiseless"), ((96, 260, 48, 16), 16, "Normal")],
          'stock: "Noiseless" at (84, 221, 72, 16), "Normal" at (96, 260, 48, 16)', f"{got}")

    print("\n18b. About screen: the URL line (mod)")
    def about_line(buf):
        e = Emu(buf)
        seen = []

        def hook(uc, addr, size, ud):
            if addr == GUI_BLIT:
                args = tuple(uc.reg_read(r) for r in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3))
                fs, sp_ = struct.unpack("<II", uc.mem_read(uc.reg_read(UC_ARM_REG_SP), 8))
                seen.append((args, fs, e.cstr(sp_)))
        e.uc.hook_add(UC_HOOK_CODE, hook)
        e.traps.add(GUI_BLIT)
        e.uc.reg_write(UC_ARM_REG_SP, 0x2000E000 - 0x60)
        e.uc.emu_start(0x08011482 | 1, 0x080114A6, count=2000)
        fg, bg = struct.unpack("<HH", e.uc.mem_read(0x200001AC, 4))
        return seen, (fg, bg), e.uc.reg_read(UC_ARM_REG_PC)
    seen, col, pc = about_line(mod)
    ok = (len(seen) == 1 and seen[0][0] == (12, 184, 216, 12) and seen[0][1] == 12
          and seen[0][2] == patches.REPO_URL and pc == 0x080114A6)
    check(ok, f'gui_blit(12, 184, 216, 12, size 12, "{seen[0][2] if seen else "?"}"), then the stock code continues',
          "" if ok else f"{seen} pc=0x{pc:08X}")
    check(col == (0xFFFF, 0x2105), "colours as stock (white on the panel grey)", f"fg=0x{col[0]:04X} bg=0x{col[1]:04X}")
    check(len(patches.REPO_URL) * 6 <= 240 - 2 * 12, "URL fits the 240 px screen at 6 px per character with 12 px margins")
    seen, col, pc = about_line(stock)
    check(len(seen) == 1 and seen[0][0] == (40, 184, 160, 16) and seen[0][2] == "http://www.fnirsi.cn",
          "stock: draws the vendor site at (40, 184), 8x16", f"{seen}")
except ImportError:
    check(False, "unicorn not available")
except Exception as ex:                                   # noqa: BLE001
    check(False, f"emulation aborted: {type(ex).__name__}: {ex}")


# ---------------------------------------------------------------------------
# 20. Cable Test: Back returns to the mode selector (cable-back)
# ---------------------------------------------------------------------------
if any(_p.pid == "cable-back" and _p.default for _p in patches.REGISTRY):
    print("\n20. Cable Test: Back (action 7) per state, mod and stock")
    try:
        KEY_DISPATCH, SET_STATE, CABLE_ENTER = 0x0800D2B4, 0x0800F77C, 0x0800C300
        OTHER = {0x0801456C: "scan_stop", 0x0800DB8C: "LENG_flash", 0x08011008: "settings_back"}
        STUB0 = {0x080116BC, 0x0800E40C}                     # key_activity_notify, battery_shutdown_active -> 0

        def back(buf, state, layout):
            e = Emu(buf)
            e.w(0x2000013C, bytes([state]))
            e.w(0x20000010, bytes([layout]))
            e.traps.update({SET_STATE, CABLE_ENTER, *OTHER})
            e.zero.update(STUB0)
            e.run(KEY_DISPATCH, {"r0": 7}, count=20000)
            return [(OTHER.get(c[0], {SET_STATE: f"set_state({c[1][0]})", CABLE_ENTER: "cable_enter"}.get(c[0])))
                    for c in e.calls]
        got = back(mod, 4, 0x10)
        check(got == ["cable_enter"], "mod: CABLE_TEST with the layout shown -> re-enter (selector), not Home", f"{got}")
        got = back(mod, 4, 0x00)
        check(got == ["set_state(2)"], "mod: CABLE_TEST on the selector -> Home", f"{got}")
        got = back(stock, 4, 0x10)
        check(got == ["set_state(2)"], "stock: CABLE_TEST with the layout shown -> Home (the reported behaviour)", f"{got}")
        for st, want in ((5, ["scan_stop"]), (6, ["LENG_flash"]), (7, ["set_state(2)"]), (8, ["set_state(2)"]),
                         (9, ["LENG_flash"]), (10, ["set_state(2)"]), (11, ["settings_back"])):
            gm, gs = back(mod, st, 0x10), back(stock, st, 0x10)
            check(gm == want and gs == want, f"state {st}: Back does what stock does ({want[0]})", f"mod {gm} stock {gs}")
    except Exception as ex:                                   # noqa: BLE001
        check(False, f"cable-back section aborted: {type(ex).__name__}: {ex}")

# ---------------------------------------------------------------------------
# 19. Thai UI (thai-ui): structure, then every screen against the mock-up model
# ---------------------------------------------------------------------------
if any(_p.pid == "thai-ui" and _p.default for _p in patches.REGISTRY):
    print("\n19. Thai UI: cell table, stubs, drawers, hook (mod)")
    try:
        import tempfile
        from thai.cells import Table, REDIRECT
        from thai import sites as TS, drawers as TD, wording as TW
        from lpm10a.thumb import assemble
        T = _probe.thai                                   # what the patch recorded while building
        ttab = T["table"]
        n_used = len(ttab.order)
        region_end = TS.CJK_TABLE + 32 * TS.CJK_SLOTS
        used = _probe.regions["thai"][2]
        check(TS.CJK_TABLE + 32 * n_used <= T["wtab"] < used <= region_end,
              f"everything the patch adds sits in the freed glyph slots ({used - TS.CJK_TABLE - 32 * n_used} bytes used, "
              f"{region_end - used} left of {32 * (TS.CJK_SLOTS - n_used)})")

        def rd(addr, n):
            return mod[addr - S.APP_BASE + 0x1000: addr - S.APP_BASE + 0x1000 + n]

        # 19a. width table = the shipped widths
        check(rd(T["wtab"], n_used) == bytes(ttab.widths), f"width table: {n_used} advances as shipped (3..16 px)")

        # 19b. every Chinese slot is a stub that resolves, through RELOC, to the wording table's Thai text
        def thai_of(zh):
            v = TW.TH[zh]
            return v["text"] if isinstance(v, dict) else v
        bad = []
        for addr, kind, zh, slot, copy in TS.CJK_STRINGS:
            raw = rd(addr, slot)
            if kind == "cjk":
                ok = raw[0] < 0xAB and raw[1] == REDIRECT
                idx = raw[2]
            else:
                units = struct.unpack("<%dH" % (slot // 2), raw[:slot // 2 * 2])
                ok = 0x100 <= units[0] < 0x1AB and units[1] == 0x100 | REDIRECT
                idx = units[2]
            ptr = struct.unpack("<I", rd(T["reloc"] + 4 * idx, 4))[0]
            got = rd(ptr, 64)
            enc = ttab.encode_cjk(thai_of(zh))
            if not ok or got[:len(enc)] != enc:
                bad.append((hex(addr), zh))
        check(not bad, f"all {len(TS.CJK_STRINGS)} Chinese slots are redirect stubs and resolve to the Thai wording",
              "" if not bad else f"{bad[:4]}")
        # nothing is left that decodes as Chinese: every stub's first byte is cell 0 (space)
        # 19c. YES / NO word cells
        for site, old_hex, zh in TS.GLYPH_SITES:
            cell = ttab.index[thai_of(zh)]
            check(rd(site, 2) == bytes([cell, 0x22]) and ttab.widths[cell] <= 16,
                  f"{zh} -> single word cell #{cell} {thai_of(zh)!r}, {ttab.widths[cell] - 1} px wide")
        # 19d. the drawers and the hook are exactly the assembled sources
        syms = dict(GLYPH=TS.GLYPH | 1, ASCII_GLYPH=TS.ASCII_GLYPH | 1, WTAB=T["wtab"], RELOC=T["reloc"],
                    THAI_CJK_TEXT=T["cjk"] | 1, LANG_IS=TS.LANG_IS | 1, DRAW_SHAPE=TS.DRAW_SHAPE | 1,
                    GUI_BLIT_CONT=(TS.GUI_BLIT + 4) | 1, HOOKTAB=T["hooktab"], BG_COLOUR=TS.BG_COLOUR)
        for label, addr, src in (("thai_cjk_text", T["cjk"], TD.CJK_TEXT), ("thai_mixed_text", T["mixed"], TD.MIXED_TEXT),
                                 ("blit_hook", T["hook"], TD.BLIT_HOOK)):
            code = assemble(addr, src, syms)
            check(rd(addr, len(code)) == code, f"{label} at 0x{addr:08X} is the assembled thai/drawers.py source ({len(code)} bytes)")
        for label, site, target in (("cjk_text", TS.CJK_TEXT, T["cjk"]), ("mixed_text", TS.MIXED_TEXT, T["mixed"]),
                                    ("gui_blit", TS.GUI_BLIT, T["hook"])):
            check(rd(site, 4) == assemble(site, f"b.w 0x{target:08X}"), f"{label} 0x{site:08X} jumps to the Thai routine")
        # 19d2. the gui_blit hook table: every entry as wording.py says
        entries = []
        for en, spec in TW.ASCII_TH.items():
            flags = {"centre": TD.F_CENTRE, "left": 0, "x": TD.F_X}[spec["layout"]] | (TD.F_CLEAR if spec.get("clear") else 0)
            entries.append((en, ttab.encode_cjk(spec["text"]), flags, spec.get("x", 0)))
        for d in TW.DOTS:
            entries.append((d, None, TD.F_X | TD.F_ASCII | TD.F_AT68, TW.DOTS_X))
        bad = []
        for i, (en, enc, flags, x) in enumerate(entries):
            a_ptr, t_ptr, fl, xx = struct.unpack("<IIHH", rd(T["hooktab"] + 12 * i, 12))
            key = rd(a_ptr, len(en) + 1)
            got = rd(t_ptr, len(enc)) if enc is not None else None
            if key != en.encode() + b"\0" or fl != flags or xx != x or (enc is not None and got != enc) or (enc is None and t_ptr != 0):
                bad.append(en)
        end = struct.unpack("<I", rd(T["hooktab"] + 12 * len(entries), 4))[0]
        check(not bad and end == 0, f"HOOKTAB: {len(entries)} entries ({len(TW.ASCII_TH)} messages + {len(TW.DOTS)} dot frames) match wording.py, 0-terminated",
              "" if not bad else f"{bad}")
        # 19e. drawers versus the model, by direct emulation (thai/test_drawers.py logic)
        import io, contextlib
        from thai import test_drawers
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            n_fail = test_drawers.main()
        check(n_fail == 0, "drawer unit test: inline, redirect and stock-plain cases match the model",
              "" if n_fail == 0 else buf.getvalue()[-300:])
        # 19f. every screen: the built image drawing Thai by itself == the model; English == the reference build
        from thai import compare as TC
        from thai.engine import reference_image
        with tempfile.TemporaryDirectory() as td:
            ref_path = os.path.join(td, "ref.bin")
            mod_path = os.path.join(td, "mod.bin")
            open(ref_path, "wb").write(reference_image())       # every default patch but thai-ui
            open(mod_path, "wb").write(mod)
            bad = TC.compare(mod_path, ref_path)
        n_scr = len(TC.ALL_SCREENS)
        check(not [b for b in bad if b[1] == "th"],
              f"Thai: all {n_scr} screens and states drawn by the firmware are pixel-identical to the mock-up model",
              "" if not bad else f"{[b for b in bad if b[1] == 'th'][:3]}")
        check(not [b for b in bad if b[1] == "en"],
              f"English: all {n_scr} screens and states are pixel-identical to the same build without thai-ui",
              "" if not bad else f"{[b for b in bad if b[1] == 'en'][:3]}")
        drawn = TC.thai_texts_drawn(mod_path)
        want = {v["text"] if isinstance(v, dict) else v for v in list(TW.TH.values()) + list(TW.ASCII_TH.values())}
        check(want <= drawn, f"every Thai string of the wording table ({len(want)}) is drawn by at least one state",
              "" if want <= drawn else f"never drawn: {sorted(want - drawn)}")
    except Exception as ex:                                   # noqa: BLE001
        check(False, f"Thai section aborted: {type(ex).__name__}: {ex}")

# ---------------------------------------------------------------------------
# 21. PoE screen (poe-screen): hooks, live refresh, status text, mod vs stock
# ---------------------------------------------------------------------------
if any(_p.pid == "poe-screen" and _p.default for _p in patches.REGISTRY):
    print("\n21. PoE screen: live voltage, 'Detecting...' / 'No PoE', timeout re-armed (mod and stock)")
    try:
        from thai.engine import Scene
        from thai import mockup as TM
        from thai.wording import ASCII_TH as _ATH
        P = _probe.poe
        LIVE = P["live"]
        POE_SM, TIMEOUT = 0x08019F00, 0x200000C2
        SITES = {0x08013ECC: ("bl", P["tick"]), 0x0801395C: ("b.w", P["live_check"]),
                 0x080139AC: ("b.w", P["std_check"]), 0x0801327E: ("bl", P["entry"]), 0x08013632: ("b.w", P["latch_hook"])}
        LATCH = P["latch"]

        def rd21(buf, addr, n):
            return buf[addr - S.APP_BASE + 0x1000: addr - S.APP_BASE + 0x1000 + n]

        # 21a. the four hooks point at the emitted blocks (bl and b.w share the T4 encoding)
        bad = [f"0x{site:08X}" for site, (kind, dst) in SITES.items() if bl_target(mod, site) != dst]
        check(not bad, "the five hook sites branch to poe_tick / live_check / std_check / entry_hook / latch_hook",
              "" if not bad else f"wrong: {bad}")
        lits = [struct.unpack("<I", rd21(mod, a, 4))[0] for a in (0x08013A38, 0x08013A44, 0x08013A48)]
        check(lits == [LATCH + 12, LATCH, LATCH + 10] and [struct.unpack("<I", rd21(stock, a, 4))[0] for a in (0x08013A38, 0x08013A44, 0x08013A48)] == [0x200000C0, 0x200000B4, 0x200000BE],
              "the 0x14 handler's poe_mv / poe_adc_ch / min literals point at the latch (stock: the task's live block)", f"{[hex(x) for x in lits]}")
        # 21b. the blocks in the file are the assembled sources, and they sit in the grown cave
        blocks = [(a, new) for a, old, new, why, kind in EXPECTED_EDITS if kind == "code" and why.startswith(("poe", "live_check", "std_check", "entry_hook", "latch_hook"))]
        same = all(rd21(mod, a, len(new)) == new for a, new in blocks)
        lo21, hi21 = min(a for a, _ in blocks), max(a + len(n) for a, n in blocks)
        check(same and len(blocks) == 6 and lo21 >= S.APP_END and hi21 <= S.APP_BASE + length,
              f"the 6 emitted blocks are byte-identical to the sources and lie in the cave (0x{lo21:08X}..0x{hi21:08X})")
        check(rd21(mod, P["strs"], 20) == b"No PoE\0Detecting...\0", "status strings: 'No PoE', 'Detecting...'")
        check({"Detecting...", "No PoE"} <= set(_ATH), "both strings have a Thai variant in wording.py (drawn by the thai-ui hook)")

        # 21c. poe_tick: the stock state machine runs, then the live refresh (state 10 + span != 0, every 50 ticks)
        def ticks(image, state, span, n, live=(0, 0, 0), shutdown=0, sc=None):
            if sc is None:
                sc = Scene(image=image, lang=1, state=state)
                sc.w8(LIVE, *live)
                sc.calls = []
                sc.at[POE_SM] = lambda uc: (sc.calls.append(1), sc.ret(0))
            sc.vals["shutdown"] = shutdown
            sc.w8(TM.POE_SPAN, span)
            n0, m0 = len(sc.calls), len(sc.msgs)
            for _ in range(n):
                sc.call(P["tick"])
            return len(sc.calls) - n0, [m for m in sc.msgs[m0:] if m[0] == 0x14], bytes(sc.uc.mem_read(LIVE, 3)), sc
        n_sm, msgs, cell, sc = ticks(mod, 10, 1, patches.POE_LIVE_TICKS - 1)
        check(n_sm == patches.POE_LIVE_TICKS - 1 and not msgs and cell == bytes([patches.POE_LIVE_TICKS - 1, 0, 1]),
              f"POE screen, span 1: {patches.POE_LIVE_TICKS - 1} ticks run the state machine each time and post nothing", f"cell {cell.hex()}")
        n_sm, msgs, cell, sc = ticks(mod, 10, 1, patches.POE_LIVE_TICKS)
        check(msgs == [(0x14, b"")] and cell == bytes([0, 1, 1]),
              f"tick {patches.POE_LIVE_TICKS}: one GUI 0x14 posted, counter back to 0, partial flag set", f"msgs {msgs} cell {cell.hex()}")
        n_sm, msgs, cell, sc = ticks(mod, 10, 1, 4 * patches.POE_LIVE_TICKS)
        check(len(msgs) == 4, f"{4 * patches.POE_LIVE_TICKS} ticks: four refreshes (every 0.5 s)", f"{len(msgs)}")
        n_sm, msgs, cell, sc = ticks(mod, 10, 0, 300)
        check(n_sm == 300 and not msgs and cell == b"\0\0\0", "POE screen, no span yet: nothing posted, counter untouched")
        n_sm, msgs, cell, sc = ticks(mod, 2, 1, 300, live=(7, 1, 3))
        check(n_sm == 300 and not msgs and cell == b"\0\0\0", "Home screen with a supply: nothing posted (the state machine still runs), the cell is zeroed")
        for st, name in ((6, "FLASH"), (9, "SPEED")):
            n_sm, msgs, cell, sc = ticks(mod, st, 1, 300)
            check(n_sm == 300 and not msgs, f"{name} screen with a supply: nothing posted")
        n_sm, msgs, cell, sc = ticks(mod, 10, 1, patches.POE_LIVE_TICKS)
        sc.msgs.clear()
        n_sm, msgs, cell, sc = ticks(mod, 10, 0, 1, sc=sc)
        check(msgs == [(0x14, b"")] and cell == bytes([0, 0, 0]), "supply removed (span 1 -> 0): one full 0x14 at once, flag clear, counter reset", f"msgs {msgs} cell {cell.hex()}")
        n_sm, msgs, cell, sc = ticks(mod, 10, 0, 300, sc=sc)
        check(not msgs, "and nothing more while it stays away")

        # 21d. screen entry: the timeout counter is re-armed, the live cell zeroed, "Detecting..." drawn while no span is known
        def entry(image, span, cnt=0xFFFF, live=(7, 1)):
            sc = Scene(image=image, lang=1, state=10)
            sc.w16(TIMEOUT, cnt); sc.w8(LIVE, *live); sc.w8(TM.POE_SPAN, span)
            sc.post(0x13); sc.drain(skip=(0x14,))
            blits = [(t, x, y) for k, t, x, y, fg, ex in sc.log if k == "ascii" and t in ("Detecting...", "No PoE")]
            return struct.unpack("<H", sc.uc.mem_read(TIMEOUT, 2))[0], bytes(sc.uc.mem_read(LIVE, 2)), blits, [m for m in sc.msgs if m[0] == 0x14]
        cnt, cell, blits, m14 = entry(mod, 0)
        check(cnt == 0 and cell == b"\0\0" and blits == [("Detecting...", patches.POE_VAL_X, patches.POE_ROW0_Y)] and not m14,
              "mod entry, no supply: timeout counter 0xFFFF -> 0, live cell cleared, 'Detecting...' at (117, 220), no 0x14",
              f"cnt {cnt} cell {cell.hex()} blits {blits}")
        cnt, cell, blits, m14 = entry(mod, 1)
        check(cnt == 0 and not blits and m14 == [(0x14, b"")],
              "mod entry with a classified supply: no 'Detecting...', the stock 0x14 is posted", f"blits {blits} msgs {m14}")
        cnt, cell, blits, m14 = entry(stock, 0)
        check(cnt == 0xFFFF and not blits, "stock entry: counter stays parked at 0xFFFF, nothing written in the rows (the blank screen)")

        # 21e. the 0x14 handler: standard 0 (the timeout) says "No PoE"; stock draws nothing
        def result(image, lang=1, thai=False, **kw):
            sc = Scene(image=image, lang=lang, thai=(TM.TH if thai else None), ascii_thai=(TM.ASCII_TH if thai else None), font=TM.FONT)
            TM.sc_poe(sc, **kw)
            return sc
        sc = result(mod, std=0, span=0, mv=0)
        blits = [(t, x, y) for k, t, x, y, fg, ex in sc.log if k == "ascii" and t in ("Detecting...", "No PoE")]
        check(blits == [("Detecting...", 117, 220), ("No PoE", 117, 220)] and not [1 for k, t, x, y, fg, ex in sc.log if k == "ascii" and t in ("Standar", "Yes", "No", "END", "MID")],
              "mod: entry draws 'Detecting...', the timeout's 0x14 replaces it with 'No PoE' and no result values", f"{blits}")
        sc = result(stock, std=0, span=0, mv=0)
        blits = [t for k, t, x, y, fg, ex in sc.log if k == "ascii" and t in ("Detecting...", "No PoE")]
        check(not blits, "stock: the same sequence writes nothing (blank rows)")
        sc = result("reference", lang=2, thai=True, std=0, span=0, mv=0)
        th = [t for k, t, x, y, fg, ex in sc.log if k == "thai"]
        check(_ATH["No PoE"]["text"] in th and _ATH["Detecting..."]["text"] in th,
              "model, Thai: the two status strings are drawn (the firmware's own drawing is compared in 19f)")

        # 21f. live refresh: only the voltage column changes, and to what a full redraw would draw
        COL = (177, 60, 217, 220)                       # the column the 0x14 handler clears: x 177..217, y 60..220
        full1 = result(mod, mv=48200).fb
        sc = result(mod, mv=48200)
        sc.w16(TM.POE_MV, 53100); sc.w8(LIVE + 1, 1)
        sc.post(0x14); sc.drain()
        live_fb = sc.fb
        full2 = result(mod, mv=53100).fb
        in_col = lambda x, y: COL[0] <= x <= COL[2] and COL[1] <= y <= COL[3]
        outside = [(x, y) for y in range(320) for x in range(240) if not in_col(x, y) and live_fb[y][x] != full1[y][x]]
        column = [(x, y) for y in range(COL[1], COL[3] + 1) for x in range(COL[0], COL[2] + 1) if live_fb[y][x] != full2[y][x]]
        changed = [(x, y) for y in range(COL[1], COL[3] + 1) for x in range(COL[0], COL[2] + 1) if live_fb[y][x] != full1[y][x]]
        check(not outside and not column and changed and bytes(sc.uc.mem_read(LIVE, 2))[1] == 0,
              "live refresh 48.2 -> 53.1 V: the voltage column equals a full redraw at 53.1 V, every other pixel is untouched, flag consumed",
              f"{len(outside)} outside, {len(column)} column mismatches, {len(changed)} pixels changed")
        n14 = len([1 for k, t, x, y, fg, ex in sc.log if k == "ascii" and t == "IEEE 802.3AT"])
        check(n14 == 1, "the result rows were drawn once (by the full 0x14), not by the live refresh", f"{n14}")
        # 21g. the latch: the redraw uses one sample block; a value changed by the task mid-draw does not reach the screen
        sc = Scene(image=mod, lang=1)
        TM.sc_poe(sc, mv=48200)
        latched = bytes(sc.uc.mem_read(LATCH, 14))
        check(latched == bytes(sc.uc.mem_read(0x200000B4, 14)), "after a redraw the latch holds the task's sample block (adc[4], max, min, mv)")
        sc = Scene(image=mod, lang=1)
        hits = []
        def bump(uc):                                          # the PoE task lands between the two wires: mv 48.2 -> 48.3 V
            hits.append(1)
            sc.w16(TM.POE_MV, 48300)
        sc.at[0x080132B0] = bump                               # the per-wire voltage formatter
        TM.sc_poe(sc, mv=48200)
        fb_a = sc.fb
        sc2 = Scene(image=mod, lang=1); TM.sc_poe(sc2, mv=48200)
        check(hits and fb_a == sc2.fb, "a sample change during the redraw is not seen: both wires show the latched 48.2 V", f"{len(hits)} wire draws")
        sc3 = Scene(image=stock, lang=1)
        sc3.at[0x080132B0] = lambda uc: sc3.w16(TM.POE_MV, 48300)
        TM.sc_poe(sc3, mv=48200)
        sc4 = Scene(image=stock, lang=1); TM.sc_poe(sc4, mv=48200)
        check(sc3.fb != sc4.fb, "stock: the same change shows up on the second wire (48.2 V and 48.3 V in one redraw)")
    except Exception as ex:                                   # noqa: BLE001
        check(False, f"poe-screen section aborted: {type(ex).__name__}: {ex}")

# ---------------------------------------------------------------------------
# 22. FLASH blink (flash-blink): the link-timed state machine, mod vs stock
# ---------------------------------------------------------------------------
if any(_p.pid == "flash-blink" and _p.default for _p in patches.REGISTRY):
    print("\n22. FLASH: port blink timed from the link (mod), the 5-phase counter (stock)")
    try:
        FT = _probe.flash
        GET_STATE, TICKS, GPIO_READ, PWR_DOWN = 0x0800F764, 0x0801C5B0, 0x08015AF2, 0x0801D178
        MSG8, MSG8_END, PHASE, FLAGS1 = 0x0801494C, 0x08014992, 0x20000076, 0x200002B5
        LOGGERS = {0x0801C6B4, 0x0801C6D8, 0x0800A82C, 0x0800A3B8, 0x08012C64, 0x0801CAA0}

        class Blink:
            """The message 8 handler under emulation with a simulated clock and link."""
            def __init__(self, buf, state=6, flags1=2):
                self.e = Emu(buf)
                self.e.w(0x2000013C, bytes([state]))
                self.e.w(FLAGS1, bytes([flags1]))
                self.now, self.link, self.pwr = 0, 0, []
                self.e.fake[TICKS] = lambda uc: uc.reg_write(UC_ARM_REG_R0, self.now)
                self.e.fake[GPIO_READ] = lambda uc: uc.reg_write(UC_ARM_REG_R0, self.link)
                self.e.fake[PWR_DOWN] = lambda uc: self.pwr.append((self.now, uc.reg_read(UC_ARM_REG_R0)))
                self.e.zero.update(LOGGERS)

            def tick(self, now=None, link=None):
                if now is not None:
                    self.now = now
                if link is not None:
                    self.link = link
                n = len(self.pwr)
                self.e.run(MSG8, until=MSG8_END, count=200000)
                return self.pwr[n:]

            def phase(self):
                return self.e.r8(PHASE)

        # 22a. the hook and the tick divisor
        check(bl_target(mod, MSG8) == FT["tick"] and mod[MSG8 + 4 - S.APP_BASE + 0x1000: MSG8 + 6 - S.APP_BASE + 0x1000] == bytes.fromhex("1fe0"),
              "message 8 handler: bl flash_tick, then b 0x08014992 (the stock phase counter is bypassed)")
        from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_MCLASS
        md22 = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS)
        def ins_at(buf, addr):
            i = next(md22.disasm(buf[addr - S.APP_BASE + 0x1000: addr - S.APP_BASE + 0x1000 + 4], addr, 1))
            return f"{i.mnemonic} {i.op_str}"
        check(ins_at(mod, 0x0801BCEE) == f"mov.w r1, #0x{patches.FLASH_TICK_MS:x}" and ins_at(stock, 0x0801BCEE) == "mov.w r1, #0x3e8",
              f"tick hook: message 8 every {patches.FLASH_TICK_MS} ms (stock 1000)", f"{ins_at(mod, 0x0801BCEE)}")
        check(ins_at(mod, 0x0800DCA0) == "mov.w r0, #0x12c" and ins_at(stock, 0x0800DCA0) == "mov.w r0, #0x320",
              "APP_Flash_task: the screen indicator clears 300 ms after the link drops (stock 800)")
        code22 = [(a, new) for a, old, new, why, kind in EXPECTED_EDITS if kind == "code" and why.startswith("flash_tick")]
        check(len(code22) == 1 and mod[code22[0][0] - S.APP_BASE + 0x1000: code22[0][0] - S.APP_BASE + 0x1000 + len(code22[0][1])] == code22[0][1],
              f"flash_tick in the file is the assembled source ({len(code22[0][1])} bytes at 0x{code22[0][0]:08X})")
        notes = [mod[a - S.APP_BASE + 0x1000:].split(b"\0")[0].decode() for a in (0x0800DB48, 0x0800DB58, 0x0800DB70)]
        check(tuple(notes) == patches.FLASH_NOTE, "the note lines read " + " / ".join(patches.FLASH_NOTE))

        # 22b. mod: wait for the link, hold it FLASH_ON_MS, drop it FLASH_OFF_MS, wait again
        ON, OFF = patches.FLASH_ON_MS, patches.FLASH_OFF_MS
        b = Blink(mod)
        TK = patches.FLASH_TICK_MS
        r = [b.tick(0, 0), b.tick(TK, 0), b.tick(2 * TK, 0)]
        check(not sum(r, []) and b.phase() == 0, "no link yet: three ticks leave the PHY powered and the phase at 0")
        r = b.tick(3 * TK + 7, 1)                                   # ticks carry a few ms of scheduling jitter
        check(not r and b.phase() == 1, "link seen at the 4th tick: phase 1 (hold), no PHY call")
        n_hold = ON // TK                                            # 3 ticks of 500 ms
        r = [b.tick(3 * TK + 7 + k * TK + (3 if k % 2 else -4)) for k in range(1, n_hold)]
        check(not sum(r, []) and b.phase() == 1, f"the next {n_hold - 1} ticks (jittered): still up")
        t_drop = 3 * TK + 7 + n_hold * TK - 6
        r = b.tick(t_drop)
        check(r == [(t_drop, 1)] and b.phase() == 2, f"tick {n_hold} after the link, 6 ms early: yt8531_set_pwr_down(1), phase 2 (dark)", f"{r}")
        t_up = t_drop + TK - 5
        r = b.tick(t_up, 0)
        check(r == [(t_up, 0)] and b.phase() == 0, f"the next tick ({OFF} ms dark, 5 ms early): yt8531_set_pwr_down(0), back to waiting for the link", f"{r}")
        r = [b.tick(t_up + TK, 0), b.tick(t_up + 2 * TK, 0), b.tick(t_up + 3 * TK, 0)]
        check(not sum(r, []) and b.phase() == 0, "a slow switch: 1.5 s without link, the PHY stays powered (no fixed cycle)")
        t1 = t_up + 4 * TK
        r = b.tick(t1, 1); r2 = [b.tick(t1 + k * TK) for k in range(1, n_hold + 1)]
        check(not r and sum(r2[:-1], []) == [] and r2[-1] == [(t1 + n_hold * TK, 1)],
              f"second cycle: on for {ON} ms from the tick that saw the link back, whatever the switch took", f"{r2[-1]}")
        # bunched ticks (the messages queued during the initial link wait) cannot shorten a phase
        b = Blink(mod); b.tick(0, 1)
        r = [b.tick(0) for _ in range(20)]
        check(not sum(r, []) and b.phase() == 1, "20 ticks at the same millisecond: the hold is timed by the clock, not counted")
        # the session gates everything
        b = Blink(mod, flags1=1); b.tick(0, 1); r = b.tick(5000, 1)
        check(not r and b.phase() == 0, "flags[1] = 1 (the initial link wait): the handler does nothing")
        b = Blink(mod, flags1=0); r = b.tick(0, 1)
        check(not r and b.phase() == 0, "flags[1] = 0 (stopped): nothing")
        b = Blink(mod, state=9); r = b.tick(0, 1)
        check(not r and b.phase() == 0, "SPEED screen: nothing")

        # 22c. stock: a phase counter, one power-down every fifth message, no look at the link
        b = Blink(stock)
        seq = [b.tick(i * 1000, 0) for i in range(10)]
        calls = [(i, c) for i, r in enumerate(seq) for (t, c) in r]
        check(calls == [(0, 0), (1, 0), (2, 0), (3, 0), (4, 1), (5, 0), (5, 0), (6, 0), (7, 0), (8, 0), (9, 1)],
              "stock: powered up for four messages, down for one, regardless of the link (a 5 s cycle at 1 s per message; the wrap powers up twice)", f"{calls}")
        b = Blink(stock, flags1=1)
        seq = [b.tick(i * 1000, 0) for i in range(5)]
        check(sum(len(r) for r in seq) == 5, "stock: the counter also runs while the session is not active (flags[1] = 1)")
    except Exception as ex:                                   # noqa: BLE001
        check(False, f"flash-blink section aborted: {type(ex).__name__}: {ex}")

print("\n" + ("ALL CHECKS PASSED" if not fails else f"{fails} CHECK(S) FAILED"))
sys.exit(1 if fails else 0)
