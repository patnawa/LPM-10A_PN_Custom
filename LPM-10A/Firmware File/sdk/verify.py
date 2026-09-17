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
  8  length result is no longer sticky
  9  low-battery debounce (3 samples) and recovery / charger cancel
 10  10-step battery gauge and its drawing switch
 11  settings save frees its staging buffer on both exit paths
 12  NVP scaling inside the length conversion
 13  length unit loaded from / stored to settings
 14  NVP UP/DOWN key hook (clicks, auto-repeat, clamps, other screens)
 15  GUI message 0x3D routing and the rendered "NVP nn%" text
 16  NVP text drawn by the Length screen's header epilogue
 17  all three font tables rendered by the firmware's own glyph drawers

Every behavioural check runs the stock image too, so the report shows the
before/after pair rather than a bare pass.
"""
import os
import sys
import struct
import hashlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
FW = os.path.dirname(HERE)

from lpm10a import symbols as S          # noqa: E402
from lpm10a.image import Image, require_stock   # noqa: E402
import patches                            # noqa: E402

STOCK = require_stock(os.path.join(FW, "LPM-10A-TX_V2.0.7_260610.bin"))
MOD = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    FW, "LPM-10A-TX_V2.0.7-mod_260610.bin")

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
check(len(mod) == len(stock), "file size unchanged", f"{len(mod)} bytes")
check(mod[:0x20] == stock[:0x20], "internal image name unchanged",
      mod[:0x20].split(b"\0")[0].decode())
check(off == 0x1000, "payload offset 0x1000")
check(off + length - 1 == end, "payload_len / payload_end consistent",
      f"len=0x{length:X} end=0x{end:X}")
check(off + length <= len(mod), "payload fits inside the file")

# ---------------------------------------------------------------- 2
print("\n2. difference footprint")
diff = [i for i in range(len(stock)) if stock[i] != mod[i]]
# the only header bytes allowed to change are payload_len / payload_end
# (0x24..0x2B), and only when the cave was used
hdr_ok = all(0x24 <= i < 0x2C for i in diff if i < off)
in_payload = all(off <= i < off + length for i in diff if i >= off)
check(bool(diff), "image actually changed", f"{len(diff)} bytes")
check(hdr_ok and in_payload, "every changed byte is inside the payload (or the header length fields)")
lo, hi = min(diff), max(diff)
check(True, "changed range", f"file 0x{lo:X}..0x{hi:X}")

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
        (8, 0, 2, 101, 0,   "FLASH, blink running  "),
        (8, 0, 0, 101, 101, "FLASH, blink finished "),
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
    for label, buf, want in (("stock", stock, 1), ("mod", mod, 0)):
        uc = run(buf, 0x0801958C)
        s = uc.mem_read(0x20000C78, 0xC9)
        magic = struct.unpack_from("<H", s, 0xA0)[0]
        lang, flag = s[0xA5], s[0xA8]
        ok = magic == 0x9718 and lang == 2 and flag == want
        check(ok, f"{label:5}: magic=0x{magic:04X} language={lang} first_boot={flag}",
              "(English, no picker)" if want == 0 else "(English, picker shown)")

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
            self.calls = []
            uc.hook_add(UC_HOOK_CODE, self._hook)

        def _hook(self, uc, addr, size, ud):
            if addr in self.stops:
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
                           (0, 1005, "7-8 = 10.1")):
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
        e.w32(0x40011008, 0xFFFF)                    # GPIOA IDR: PA10 high = no CHRG
        e.w32(0x40010808, 0xFFFF)                    # GPIOB? IDR: bit15 high = no STDBY
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
    NVP_B, UNIT_B = SETTINGS + 0xA6, SETTINGS + 0xA7
    GUI_MSG_SEND, KEY_NOTIFY, GUI_BLIT, SPRINTF = 0x0800E428, 0x080116BC, 0x080174E8, 0x0800A38C
    RESULT_DRAW, SYSSTATE = 0x080199B0, 0x2000013C

    def ref_nvp(cm, nvp):
        return (cm * nvp + 34) // 69 if 50 <= nvp <= 99 else cm

    print("\n12. length: NVP scaling in the conversion (mod)")
    for nvp in (0, 69, 75, 50, 99, 120):
        bad = []
        for unit in (0, 1, 2):
            for cm in (201, 5540, 10000, 20000):
                e = Emu(mod)
                e.w(UNIT, bytes([unit]))
                e.w(NVP_B, bytes([nvp]))
                r = e.run(LENG_CONVERT, {"r0": cm})
                want = ref_convert(ref_nvp(cm, nvp), unit)
                if r["r0"] != want:
                    bad.append((unit, cm, r["r0"], want))
        label = f"NVP byte {nvp:3}" + (" (factory/identity)" if nvp in (0, 69, 120) else "")
        check(not bad, f"{label}: 12 vectors match reference", "" if not bad else f"{bad[:3]}")
    e = Emu(mod); e.w(UNIT, b"\x00"); e.w(NVP_B, bytes([75]))
    r = e.run(LENG_CONVERT, {"r0": 5540})
    check(r["r0"] == 602, "55.40 m cable at NVP 75 % reads 60.2 m", f"{r['r0'] / 10} m")

    print("\n13. length: unit remembered across screens (mod)")
    for stored, want in ((0, 0), (1, 1), (2, 2), (7, 0), (255, 0)):
        e = Emu(mod)
        e.w(UNIT_B, bytes([stored]))
        e.w(UNIT, b"\x01")
        e.run(0x08012F1C, {"r1": 0x200002B4}, until=0x08012F20)
        check(e.r8(UNIT) == want, f"entry: settings unit {stored:3} -> Length screen unit {e.r8(UNIT)}")
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
    def press(state, key, evt, nvp):
        e = Emu(mod)
        e.w(SYSSTATE, bytes([state]))
        e.w(NVP_B, bytes([nvp]))
        e.w(KEYBUF, bytes([key, evt]))
        e.traps.update({GUI_MSG_SEND, KEY_NOTIFY})
        r = e.run(KEY_HOOK, {"r5": KEYBUF})
        msgs = [c[1][0] for c in e.calls if c[0] == GUI_MSG_SEND]
        notified = any(c[0] == KEY_NOTIFY for c in e.calls)
        return e.r8(NVP_B), msgs, notified, r["r0"]
    UP, DOWN, CLICK, LONG, REPEAT = 2, 3, 3, 6, 12
    v, m, n, st = press(7, UP, CLICK, 0)
    check((v, m, n, st) == (70, [0x3D], True, 0x80), "LENGTH, UP click, byte 0 (=69%) -> 70 %, GUI 0x3D, activity, state mask kept",
          f"nvp={v} msgs={[hex(x) for x in m]} notify={n} r0=0x{st:X}")
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
    v, m, n, st = press(7, 4, CLICK, 0)
    check((v, m) == (0, []), "LENGTH, OK key: not ours", f"nvp={v}")

    print("\n15. NVP: GUI message 0x3D and the on-screen text (mod)")
    for msg, want_at, label in ((0x10, 0x0800F490, "0x10 -> stock jump table"), (0xFF, 0x0800F4DC, "0xFF -> exit (shutdown filter)")):
        e = Emu(mod)
        r = e.run(0x0800F48C, {"r0": msg}, until=want_at, count=20)
        check(r["pc"] == want_at and r["r0"] == msg, f"message {label}", f"pc=0x{r['pc']:08X}")
    e = Emu(mod)
    e.w(NVP_B, bytes([72]))
    e.traps.update({GUI_BLIT, RESULT_DRAW})
    r = e.run(0x0800F48C, {"r0": 0x3D}, until=0x0800F4DC, count=20000)
    blits = [c for c in e.calls if c[0] == GUI_BLIT]
    ok = len(blits) == 1 and r["pc"] == 0x0800F4DC
    if ok:
        (x, y, w, h), (size, strp) = blits[0][1], blits[0][2]
        text = e.cstr(strp)
        ok = (x, y, w, h, size, text) == (166, 90, 56, 16, 0x10, "NVP 72%")
        check(ok, f'0x3D: gui_blit({x}, {y}, {w}, {h}, size 0x{size:X}, "{text}") then results redraw',
              "" if ok else "(unexpected)")
    else:
        check(False, "0x3D: text drawn once", f"{len(blits)} blits, pc=0x{r['pc']:08X}")
    check(any(c[0] == RESULT_DRAW for c in e.calls), "0x3D: length_result_draw called after the text")
    fg, bg = struct.unpack("<HH", e.uc.mem_read(0x200001AC, 4))
    check((fg, bg) == (0xFFFF, 0x0000), "text colours white on the black background", f"fg=0x{fg:04X} bg=0x{bg:04X}")
    for nvp, want in ((0, "NVP 69%"), (50, "NVP 50%"), (99, "NVP 99%"), (255, "NVP 69%")):
        e = Emu(mod); e.w(NVP_B, bytes([nvp])); e.traps.add(GUI_BLIT); e.traps.add(RESULT_DRAW)
        e.run(0x0800F48C, {"r0": 0x3D}, until=0x0800F4DC, count=20000)
        got = e.cstr([c for c in e.calls if c[0] == GUI_BLIT][0][2][1])
        check(got == want, f'byte {nvp:3} -> "{got}"')

    print("\n16. NVP: drawn when the Length screen opens (mod)")
    e = Emu(mod)
    e.w(NVP_B, bytes([69]))
    F = 0x2000E000 - 0x28
    for i in range(4):
        e.w32(F + 0x14 + 4 * i, 0x44444444 + i)      # saved r4..r7
    e.w32(F + 0x24, MAGIC | 1)                        # saved lr
    e.traps.add(GUI_BLIT)
    e.uc.reg_write(UC_ARM_REG_SP, F)
    e.uc.emu_start(0x08019970 | 1, MAGIC, count=20000)
    blits = [c for c in e.calls if c[0] == GUI_BLIT]
    sp_after = e.uc.reg_read(UC_ARM_REG_SP)
    check(len(blits) == 1 and e.cstr(blits[0][2][1]) == "NVP 69%" and sp_after == F + 0x28
          and e.uc.reg_read(UC_ARM_REG_R7) == 0x44444447,
          "epilogue draws the text, then returns with the stack and r4-r7 restored",
          f"blits={len(blits)} sp=+0x{sp_after - F:X} r7=0x{e.uc.reg_read(UC_ARM_REG_R7):X}")

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
    for name, (addr, n, w, h, per) in fonts.TABLES.items():
        blob_mod = mod[addr - S.APP_BASE + 0x1000: addr - S.APP_BASE + 0x1000 + n * per]
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
except ImportError:
    check(False, "unicorn not available")

print("\n" + ("ALL CHECKS PASSED" if not fails else f"{fails} CHECK(S) FAILED"))
sys.exit(1 if fails else 0)
