"""
Minimal Thumb / Thumb-2 assembler for LPM-10A firmware patches.

Scope is deliberately small: just enough to write hook/trampoline code.
Anything it does not recognise raises AsmError rather than emitting
something approximate -- silence is the enemy when you are writing bytes
into a device's flash.

Every assembled block can be re-checked with `verify()`, which disassembles
the output through Capstone and hands the listing back so a human (or a
test) can confirm the CPU sees what was intended.

Supported:
    directives  .word .short .byte .asciz .space .align .pool
    data move   movs Rd,#imm8 | mov Rd,Rm | movw/movt Rd,#imm16
                ldr Rt,=expr  (auto literal pool)
    memory      ldr/str  Rt,[Rn{,#imm}]      (imm = 0..124, /4)
                ldr/str  Rt,[sp{,#imm}]      (imm = 0..1020, /4)
                ldrb/strb Rt,[Rn{,#imm}]     (imm = 0..31)
                ldrh/strh Rt,[Rn{,#imm}]     (imm = 0..62, /2)
    stack       push/pop {reglist} | add/sub sp,#imm (0..508, /4)
    branch      b/b.w/bl label | bx/blx Rm | b<cond> label | cbz/cbnz Rn,label
    alu         cmp Rn,#imm8 | cmp Rn,Rm | adds/subs Rd,Rn,#imm3
                adds/subs Rd,Rn,Rm | adds/subs Rd,#imm8 | add Rd,Rm
                lsls/lsrs Rd,Rm,#imm5 | ands/orrs/bics/eors Rd,Rm
                rsbs Rd,Rn,#0 | uxtb/uxth/sxtb/sxth Rd,Rm
    mul/div     muls Rd,Rn,Rd | mul Rd,Rn,Rm | mls Rd,Rn,Rm,Ra
                udiv/sdiv Rd,Rn,Rm
    misc        nop
"""
import re
import struct

LO = {f"r{i}": i for i in range(8)}
ALL = dict(LO)
ALL.update({f"r{i}": i for i in range(16)})
ALL.update({"sp": 13, "lr": 14, "pc": 15})

COND = {
    "eq": 0, "ne": 1, "hs": 2, "cs": 2, "lo": 3, "cc": 3, "mi": 4, "pl": 5,
    "vs": 6, "vc": 7, "hi": 8, "ls": 9, "ge": 10, "lt": 11, "gt": 12, "le": 13,
}


class AsmError(Exception):
    pass


def _reg(tok, lo_only=True):
    t = tok.strip().lower()
    if t not in ALL:
        raise AsmError(f"bad register {tok!r}")
    n = ALL[t]
    if lo_only and n > 7:
        raise AsmError(f"{tok!r} is not a low register (r0-r7)")
    return n


def _reglist(tok):
    m = re.fullmatch(r"\{(.*)\}", tok.strip())
    if not m:
        raise AsmError(f"bad register list {tok!r}")
    regs = []
    for part in m.group(1).split(","):
        part = part.strip().lower()
        if "-" in part:
            a, b = part.split("-")
            regs += list(range(_reg(a, False), _reg(b, False) + 1))
        else:
            regs.append(_reg(part, False))
    return regs


class Asm:
    """Two-pass assembler. `org` is the flash address the code starts at."""

    def __init__(self, org, symbols=None):
        self.org = org
        self.symbols = dict(symbols or {})
        self.lines = []

    def add(self, text):
        for raw in text.splitlines():
            line = raw.split(";")[0].split("//")[0].rstrip()
            if not line.strip():
                continue
            # "label:   insn ..." on one line -> two lines
            m = re.match(r"\s*([A-Za-z_.$][\w.$]*):\s*(.*)$", line)
            if m and m.group(2).strip():
                self.lines.append(m.group(1) + ":")
                line = m.group(2)
            self.lines.append(line)
        return self

    # ------------------------------------------------------------ expressions
    def _eval(self, expr, labels):
        e = expr.strip()
        env = dict(self.symbols)
        env.update(labels)
        try:
            return int(eval(e, {"__builtins__": {}}, env))
        except AsmError:
            raise
        except Exception as exc:
            raise AsmError(f"cannot evaluate {expr!r}: {exc}")

    # ------------------------------------------------------------ main entry
    def assemble(self):
        # pass 1: sizes and labels (literal pool sizing needs a fixed point)
        pool_guess = 0
        for _ in range(6):
            labels, size, pools = self._layout(pool_guess)
            if pools == pool_guess:
                break
            pool_guess = pools
        else:
            raise AsmError("literal pool layout did not converge")
        # pass 2: emit
        return self._emit(labels)

    def _parse(self, line):
        line = line.strip()
        m = re.fullmatch(r"([A-Za-z_.$][\w.$]*):", line)
        if m:
            return ("label", m.group(1), None)
        m = re.match(r"(\S+)\s*(.*)", line)
        return ("insn", m.group(1).lower(), m.group(2).strip())

    def _split_ops(self, ops):
        out, depth, cur = [], 0, ""
        for ch in ops:
            if ch in "{[":
                depth += 1
            elif ch in "}]":
                depth -= 1
            if ch == "," and depth == 0:
                out.append(cur.strip())
                cur = ""
            else:
                cur += ch
        if cur.strip():
            out.append(cur.strip())
        return out

    # ------------------------------------------------------------ pass 1
    def _layout(self, pool_bytes):
        pc = self.org
        labels = {}
        pool = []
        for line in self.lines:
            kind, a, b = self._parse(line)
            if kind == "label":
                labels[a] = pc
                continue
            pc, added = self._size(a, b, pc, pool)
        # pool is emitted at the end, 4-aligned
        if pool:
            pc = (pc + 3) & ~3
            pc += 4 * len(set(pool))
        return labels, pc - self.org, 4 * len(set(pool))

    def _size(self, mn, ops, pc, pool):
        if mn == ".word":
            n = len(self._split_ops(ops))
            return pc + 4 * n, 0
        if mn == ".short":
            return pc + 2 * len(self._split_ops(ops)), 0
        if mn == ".byte":
            return pc + len(self._split_ops(ops)), 0
        if mn == ".asciz":
            s = ops.strip().strip('"')
            return pc + len(s.encode()) + 1, 0
        if mn == ".space":
            return pc + int(ops, 0), 0
        if mn == ".align":
            a = int(ops or 4, 0)
            return (pc + a - 1) & ~(a - 1), 0
        if mn == ".pool":
            return pc, 0
        if mn == "ldr" and "=" in ops:
            pool.append(ops.split(",", 1)[1].strip().lstrip("="))
            return pc + 2, 0
        return pc + self._insn_size(mn, ops), 0

    def _insn_size(self, mn, ops):
        if mn in ("movw", "movt", "bl", "b.w", "blx.w", "udiv", "sdiv", "mls", "mul"):
            return 4
        return 2

    # ------------------------------------------------------------ pass 2
    def _emit(self, labels):
        out = bytearray()
        pc = self.org
        pool_order = []
        pool_fix = []   # (offset_in_out, expr)

        def put(bs):
            nonlocal pc
            out.extend(bs)
            pc += len(bs)

        for line in self.lines:
            kind, mn, ops = self._parse(line)
            if kind == "label":
                continue

            if mn == ".word":
                for e in self._split_ops(ops):
                    put(struct.pack("<I", self._eval(e, labels) & 0xFFFFFFFF))
                continue
            if mn == ".short":
                for e in self._split_ops(ops):
                    put(struct.pack("<H", self._eval(e, labels) & 0xFFFF))
                continue
            if mn == ".byte":
                for e in self._split_ops(ops):
                    put(bytes([self._eval(e, labels) & 0xFF]))
                continue
            if mn == ".asciz":
                put(ops.strip().strip('"').encode() + b"\0")
                continue
            if mn == ".space":
                put(b"\0" * int(ops, 0))
                continue
            if mn == ".align":
                a = int(ops or 4, 0)
                while (pc % a) != 0:
                    put(b"\0")
                continue
            if mn == ".pool":
                continue

            if mn == "ldr" and "=" in ops:
                rt_s, expr = ops.split(",", 1)
                rt = _reg(rt_s)
                expr = expr.strip().lstrip("=")
                if expr not in pool_order:
                    pool_order.append(expr)
                pool_fix.append((len(out), rt, expr, pc))
                put(b"\x00\x00")     # placeholder, fixed up below
                continue

            put(self._encode(mn, ops, pc, labels))

        # literal pool, 4-aligned, after the code (no padding if no pool)
        if pool_order:
            while (pc % 4) != 0:
                out.append(0)
                pc += 1
        pool_addr = {}
        for expr in pool_order:
            pool_addr[expr] = pc
            out.extend(struct.pack("<I", self._eval(expr, labels) & 0xFFFFFFFF))
            pc += 4

        # patch the LDR (literal) placeholders
        for off, rt, expr, ins_pc in pool_fix:
            target = pool_addr[expr]
            base = (ins_pc + 4) & ~3
            delta = target - base
            if delta < 0 or delta > 1020 or delta % 4:
                raise AsmError(f"literal for {expr!r} out of LDR range ({delta})")
            word = 0x4800 | (rt << 8) | (delta >> 2)
            struct.pack_into("<H", out, off, word)

        return bytes(out)

    # ------------------------------------------------------------ encoders
    def _encode(self, mn, ops, pc, labels):
        o = self._split_ops(ops)
        E = lambda x: self._eval(x, labels)
        h = lambda v: struct.pack("<H", v)

        if mn == "nop":
            return h(0xBF00)

        if mn == "movs":
            rd, imm = _reg(o[0]), E(o[1].lstrip("#"))
            if not 0 <= imm <= 255:
                raise AsmError("movs immediate out of range")
            return h(0x2000 | (rd << 8) | imm)

        if mn == "mov":
            rd, rm = _reg(o[0], False), _reg(o[1], False)
            return h(0x4600 | ((rd & 8) << 4) | (rm << 3) | (rd & 7))

        if mn in ("movw", "movt"):
            rd, imm = _reg(o[0], False), E(o[1].lstrip("#")) & 0xFFFF
            op = 0xF2400000 if mn == "movw" else 0xF2C00000
            i = (imm >> 11) & 1
            imm4 = (imm >> 12) & 0xF
            imm3 = (imm >> 8) & 7
            imm8 = imm & 0xFF
            w = op | (i << 26) | (imm4 << 16) | (imm3 << 12) | (rd << 8) | imm8
            return struct.pack("<HH", w >> 16, w & 0xFFFF)

        if mn in ("ldr", "str", "ldrb", "strb", "ldrh", "strh"):
            rt = _reg(o[0])
            m = re.fullmatch(r"\[\s*(\w+)\s*(?:,\s*#?([^\]]+))?\]", o[1].strip())
            if not m:
                raise AsmError(f"bad memory operand {o[1]!r}")
            off = E(m.group(2)) if m.group(2) else 0
            if m.group(1).strip().lower() == "sp":
                # T2 SP-relative word load/store: imm8 * 4
                if mn not in ("ldr", "str"):
                    raise AsmError(f"{mn} does not support an sp base")
                if off % 4 or not 0 <= off <= 1020:
                    raise AsmError(f"{mn} sp offset {off} out of range")
                base = 0x9800 if mn == "ldr" else 0x9000
                return h(base | (rt << 8) | (off >> 2))
            rn = _reg(m.group(1))
            if mn in ("ldr", "str"):
                if off % 4 or not 0 <= off <= 124:
                    raise AsmError(f"{mn} offset {off} out of range")
                base = 0x6800 if mn == "ldr" else 0x6000
                return h(base | ((off >> 2) << 6) | (rn << 3) | rt)
            if mn in ("ldrb", "strb"):
                if not 0 <= off <= 31:
                    raise AsmError(f"{mn} offset {off} out of range")
                base = 0x7800 if mn == "ldrb" else 0x7000
                return h(base | (off << 6) | (rn << 3) | rt)
            if off % 2 or not 0 <= off <= 62:
                raise AsmError(f"{mn} offset {off} out of range")
            base = 0x8800 if mn == "ldrh" else 0x8000
            return h(base | ((off >> 1) << 6) | (rn << 3) | rt)

        if mn in ("push", "pop"):
            regs = _reglist(ops)
            extra = 14 if mn == "push" else 15
            lo = [r for r in regs if r <= 7]
            hi = [r for r in regs if r > 7]
            if hi not in ([], [extra]):
                raise AsmError(f"{mn} can only add {'lr' if mn == 'push' else 'pc'}")
            mask = sum(1 << r for r in lo)
            base = 0xB400 if mn == "push" else 0xBC00
            return h(base | (0x100 if hi else 0) | mask)

        if mn == "bx":
            return h(0x4700 | (_reg(o[0], False) << 3))
        if mn == "blx":
            return h(0x4780 | (_reg(o[0], False) << 3))

        # Branch targets: function symbols carry the Thumb bit (addr|1) so
        # they can be used with .word / ldr =sym for blx; a direct branch
        # encodes the halfword offset, so the bit is dropped here.
        if mn == "b":
            delta = (E(o[0]) & ~1) - (pc + 4)
            if delta % 2 or not -2048 <= delta <= 2046:
                raise AsmError(f"b out of range ({delta})")
            return h(0xE000 | ((delta >> 1) & 0x7FF))

        if mn == "b.w":
            delta = (E(o[0]) & ~1) - (pc + 4)
            if delta % 2 or not -(1 << 24) <= delta < (1 << 24):
                raise AsmError(f"b.w out of range ({delta})")
            return self._enc_bl(delta, link=False)

        if mn == "bl":
            delta = (E(o[0]) & ~1) - (pc + 4)
            if delta % 2 or not -(1 << 24) <= delta < (1 << 24):
                raise AsmError(f"bl out of range ({delta})")
            return self._enc_bl(delta, link=True)

        if mn.startswith("b") and mn[1:] in COND:
            delta = (E(o[0]) & ~1) - (pc + 4)
            if delta % 2 or not -256 <= delta <= 254:
                raise AsmError(f"{mn} out of range ({delta})")
            return h(0xD000 | (COND[mn[1:]] << 8) | ((delta >> 1) & 0xFF))

        if mn in ("cbz", "cbnz"):
            rn = _reg(o[0])
            delta = (E(o[1]) & ~1) - (pc + 4)
            if delta < 0 or delta > 126 or delta % 2:
                raise AsmError(f"{mn} out of range ({delta})")
            i = (delta >> 6) & 1
            imm5 = (delta >> 1) & 0x1F
            return h(0xB100 | (0x800 if mn == "cbnz" else 0) | (i << 9) | (imm5 << 3) | rn)

        if mn == "cmp":
            if o[1].strip().startswith("#"):
                rn, imm = _reg(o[0]), E(o[1].lstrip("#"))
                if not 0 <= imm <= 255:
                    raise AsmError("cmp immediate out of range")
                return h(0x2800 | (rn << 8) | imm)
            return h(0x4280 | (_reg(o[1]) << 3) | _reg(o[0]))

        if mn in ("adds", "subs"):
            base3 = 0x1C00 if mn == "adds" else 0x1E00
            base8 = 0x3000 if mn == "adds" else 0x3800
            basereg = 0x1800 if mn == "adds" else 0x1A00
            if len(o) == 3:
                rd, rn = _reg(o[0]), _reg(o[1])
                if o[2].strip().startswith("#"):
                    imm = E(o[2].lstrip("#"))
                    if not 0 <= imm <= 7:
                        raise AsmError(f"{mn} immediate out of range")
                    return h(base3 | (imm << 6) | (rn << 3) | rd)
                rm = _reg(o[2])
                return h(basereg | (rm << 6) | (rn << 3) | rd)
            rd, imm = _reg(o[0]), E(o[1].lstrip("#"))
            if not 0 <= imm <= 255:
                raise AsmError(f"{mn} immediate out of range")
            return h(base8 | (rd << 8) | imm)

        if mn in ("add", "sub") and len(o) == 2 and o[0].strip().lower() == "sp" \
                and o[1].strip().startswith("#"):
            imm = E(o[1].lstrip("#"))
            if imm % 4 or not 0 <= imm <= 508:
                raise AsmError(f"{mn} sp immediate {imm} out of range")
            return h((0xB000 if mn == "add" else 0xB080) | (imm >> 2))

        if mn == "add" and len(o) == 2 and not o[1].strip().startswith("#"):
            rd, rm = _reg(o[0], False), _reg(o[1], False)
            return h(0x4400 | ((rd & 8) << 4) | (rm << 3) | (rd & 7))

        if mn == "rsbs":
            rd, rn = _reg(o[0]), _reg(o[1])
            if E(o[2].lstrip("#")) != 0:
                raise AsmError("rsbs only supports #0")
            return h(0x4240 | (rn << 3) | rd)

        if mn in ("uxtb", "uxth", "sxtb", "sxth"):
            rd, rm = _reg(o[0]), _reg(o[1])
            base = {"sxth": 0xB200, "sxtb": 0xB240, "uxth": 0xB280, "uxtb": 0xB2C0}[mn]
            return h(base | (rm << 3) | rd)

        if mn == "muls":
            # T1: muls Rd, Rn, Rd  (Rd = Rn * Rd)
            rd, rn, rdm = _reg(o[0]), _reg(o[1]), _reg(o[2])
            if rd != rdm:
                raise AsmError("muls: destination must equal the last operand")
            return h(0x4340 | (rn << 3) | rd)

        if mn == "mul":
            rd, rn, rm = _reg(o[0], False), _reg(o[1], False), _reg(o[2], False)
            return struct.pack("<HH", 0xFB00 | rn, 0xF000 | (rd << 8) | rm)

        if mn == "mls":
            # mls Rd, Rn, Rm, Ra : Rd = Ra - Rn*Rm
            rd, rn, rm, ra = (_reg(x, False) for x in o[:4])
            return struct.pack("<HH", 0xFB00 | rn, 0x0010 | (ra << 12) | (rd << 8) | rm)

        if mn in ("udiv", "sdiv"):
            rd, rn, rm = _reg(o[0], False), _reg(o[1], False), _reg(o[2], False)
            hi = (0xFBB0 if mn == "udiv" else 0xFB90) | rn
            return struct.pack("<HH", hi, 0xF0F0 | (rd << 8) | rm)

        if mn in ("lsls", "lsrs") and len(o) == 3:
            rd, rm, imm = _reg(o[0]), _reg(o[1]), E(o[2].lstrip("#"))
            if not 0 <= imm <= 31:
                raise AsmError(f"{mn} shift out of range")
            base = 0x0000 if mn == "lsls" else 0x0800
            return h(base | (imm << 6) | (rm << 3) | rd)

        if mn in ("ands", "orrs", "bics", "eors"):
            rd, rm = _reg(o[0]), _reg(o[1])
            base = {"ands": 0x4000, "eors": 0x4040, "orrs": 0x4300, "bics": 0x4380}[mn]
            return h(base | (rm << 3) | rd)

        raise AsmError(f"unsupported instruction: {mn} {ops}")

    @staticmethod
    def _enc_bl(delta, link=True):
        s = (delta >> 24) & 1
        i1 = (delta >> 23) & 1
        i2 = (delta >> 22) & 1
        imm10 = (delta >> 12) & 0x3FF
        imm11 = (delta >> 1) & 0x7FF
        j1 = (~i1 ^ s) & 1
        j2 = (~i2 ^ s) & 1
        hi = 0xF000 | (s << 10) | imm10
        lo = (0xD000 if link else 0x9000) | (j1 << 13) | (j2 << 11) | imm11
        return struct.pack("<HH", hi, lo)


def assemble(org, source, symbols=None):
    return Asm(org, symbols).add(source).assemble()


def verify(code, org, mclass=True):
    """Disassemble assembled bytes; returns list of (addr, bytes, text)."""
    from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_MCLASS
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | (CS_MODE_MCLASS if mclass else 0))
    out = []
    for ins in md.disasm(code, org):
        out.append((ins.address, ins.bytes.hex(), f"{ins.mnemonic} {ins.op_str}".strip()))
    return out
