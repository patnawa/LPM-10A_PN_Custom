"""Emulate the Thai drawers against the firmware's real glyph drawers and
compare the pixels with ThaiFont.draw (the mock-up model).

    python -m thai.test_drawers
"""
import os
import struct
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE
from unicorn.arm_const import *
from lpm10a.thumb import assemble, verify as asm_verify           # noqa: E402
from thai.cells import Table, ui_texts, REDIRECT, FONT             # noqa: E402
from thai.engine import load_payload, ascii_font, DEFAULT_IMAGE, APP, MAGIC, PUT_PIXEL, FG   # noqa: E402
from thai import drawers                                            # noqa: E402

GLYPH, ASCII_GLYPH = 0x08017550, 0x080171D4
CJK_TABLE = 0x08066368
CODE = 0x08070000            # scratch area for the test only: flash beyond the image
WTAB = CODE + 0x400
RELOC = CODE + 0x500
STRS = CODE + 0x600


def build_env(table):
    """(payload with the Thai cell table, extra memory writes with the drawers + width table)."""
    payload = bytearray(load_payload(DEFAULT_IMAGE))
    payload[CJK_TABLE - APP:CJK_TABLE - APP + 171 * 32] = table.blob()
    syms = dict(GLYPH=GLYPH | 1, ASCII_GLYPH=ASCII_GLYPH | 1, WTAB=WTAB, RELOC=RELOC, THAI_CJK_TEXT=CODE | 1)
    cjk = assemble(CODE, drawers.CJK_TEXT, syms)
    mixed = assemble(CODE + 0x100, drawers.MIXED_TEXT, syms)
    asm_verify(cjk, CODE); asm_verify(mixed, CODE + 0x100)
    extra = [(CODE, cjk), (CODE + 0x100, mixed), (WTAB, table.width_blob())]
    return (bytes(payload), extra), len(cjk), len(mixed)


def run(env, fn, x, y, s_bytes, count, extra_mem=()):
    payload, base_extra = env
    uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
    uc.mem_map(0x08000000, 0x80000); uc.mem_map(0x20000000, 0x10000); uc.mem_map(MAGIC, 0x1000)
    uc.mem_write(APP, payload)
    for addr, data in list(base_extra) + list(extra_mem):
        uc.mem_write(addr, data)
    uc.mem_write(0x20000F54, struct.pack("<HH", 240, 320))
    uc.mem_write(FG, struct.pack("<HH", 0xFFFF, 0x2105))
    uc.mem_write(STRS, s_bytes)
    px = {}
    calls = []

    def hook(uc, addr, size, ud):
        if addr == PUT_PIXEL:
            col = struct.unpack("<H", uc.mem_read(FG, 2))[0]
            px[(uc.reg_read(UC_ARM_REG_R0), uc.reg_read(UC_ARM_REG_R1))] = col
            uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
        elif addr in (GLYPH, ASCII_GLYPH):
            calls.append((addr, uc.reg_read(UC_ARM_REG_R0), uc.reg_read(UC_ARM_REG_R1), uc.reg_read(UC_ARM_REG_R2)))
    uc.hook_add(UC_HOOK_CODE, hook)
    sp = 0x2000E000
    uc.reg_write(UC_ARM_REG_SP, sp); uc.reg_write(UC_ARM_REG_LR, MAGIC | 1)
    uc.reg_write(UC_ARM_REG_R0, x); uc.reg_write(UC_ARM_REG_R1, y)
    uc.reg_write(UC_ARM_REG_R2, STRS); uc.reg_write(UC_ARM_REG_R3, count)
    uc.emu_start(fn | 1, MAGIC, count=2_000_000)
    assert uc.reg_read(UC_ARM_REG_PC) == MAGIC
    # callee-saved registers must come back intact (r4-r7 are checked by the return path itself)
    return px, calls


def expected(font, afont, x, y, text, centred):
    px = {}
    w = font.width(text)
    if centred:
        x -= w // 2
    font.draw(lambda X, Y, c: px.__setitem__((X, Y), c), x, y, text, 0xFFFF)
    return px


def main():
    table = Table(ui_texts())
    env, n_cjk, n_mixed = build_env(table)
    afont = None
    print(f"cjk drawer {n_cjk} bytes, mixed drawer {n_mixed} bytes")
    cases = [
        ("cjk", "เริ่มทดสอบ", 120, 285, 4), ("cjk", "ทดสอบสาย", 13, 21, 0), ("cjk", "ฟุต", 60, 137, 2),
        ("cjk", "กดปุ่มขวาค้างเพื่อปรับเทียบ", 120, 191, 6), ("cjk", "ใช่", 65, 195, 0),
        ("mixed", "ทดสอบ PoE", 60, 190, 7), ("mixed", "5 นาที", 136, 227, 5), ("mixed", "แบตเตอรี่ต่ำ โปรดชาร์จ", 66, 130, 0),
        ("mixed", "ซอฟต์แวร์:", 57, 130, 0), ("mixed", "ทดสอบเข้าหัว", 60, 50, 8),
    ]
    fails = 0
    for kind, text, x, y, count in cases:
        fn = CODE if kind == "cjk" else CODE + 0x100
        variants = (False, True) if kind == "cjk" else (True,)      # Thai mixed strings are always stubs
        for redirect in variants:
            if redirect:
                # stub at STRS, real (cjk-kind) string at STRS+0x80, RELOC[3] -> it
                stub = bytes([0, REDIRECT, 3, 0xFF]) if kind == "cjk" else struct.pack("<HHHH", 0x0100, 0x0100 | REDIRECT, 3, 0)
                mem = [(STRS + 0x80, table.encode_cjk(text)), (RELOC + 12, struct.pack("<I", STRS + 0x80))]
                px, calls = run(env, fn, x, y, stub, count, mem)
            else:
                px, calls = run(env, fn, x, y, table.encode_cjk(text), count)
            want = expected(FONT, afont, x, y, text, count != 0)
            ok = px == want
            fails += not ok
            print(f"{'ok ' if ok else 'BAD'} {kind:5} {'redir' if redirect else 'inline':6} count={count} {text!r}: {len(calls)} glyph calls, {len(px)} px")
            if not ok:
                diff = {k for k in set(px) | set(want) if px.get(k) != want.get(k)}
                print("     differing pixels:", sorted(diff)[:8])
    # a mixed string that is not a stub (the English "Switch" / "Far end" boxes) must render as stock does
    stock_env = (load_payload(DEFAULT_IMAGE), [])
    for text, x, y in (("Switch", 58, 190), ("Far end", 178, 190), ("POE", 60, 190)):
        enc = struct.pack("<%dH" % (len(text) + 1), *([ord(c) for c in text] + [0]))
        count = len(text)
        px_stock, _ = run(stock_env, 0x080173EC, x, y, enc, count)
        px_new, _ = run(env, CODE + 0x100, x, y, enc, count)
        ok = px_stock == px_new and len(px_stock) > 0
        fails += not ok
        print(f"{'ok ' if ok else 'BAD'} mixed plain  {text!r}: stock {len(px_stock)} px, new {len(px_new)} px")
    print("FAIL" if fails else "all drawer cases match the mock-up model")
    return fails


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(1 if main() else 0)
