#!/usr/bin/env python3
"""
LPM-10A on-screen fonts: export the stock glyph tables, or build replacements.

    python fonts.py export              stock tables -> fonts_out/stock_*.png
    python fonts.py preview             fonts_out/*.bin -> fonts_out/*.png (no extra packages)
    python fonts.py build [--mono TTF] [--cjk TTF] [--weight N]
                                        rasterize replacement tables -> fonts_out/*.bin + *.png
                                        (needs Pillow; the CJK default needs pymupdf)

The firmware has exactly three fonts, all "column-major" bitmaps:

    table       flash addr    glyphs   cell   bytes/glyph   used for
    ascii12     0x08065904      95     6x12        12       small labels (About / Factory Reset)
    ascii16     0x08065D78      95     8x16        16       everything else in English
    cjk16       0x08066368     171    16x16        32       Chinese UI text

ASCII layout (renderer 0x080171D4): one column = 2 bytes, MSB = top pixel,
bits 0..7 of the second byte are rows 8..15; for the 12-row font the last
four bits of each column are padding that the renderer skips.  Glyph index
= ASCII - 0x20.

CJK layout (renderer 0x08017550): 16 little-endian u16 columns, bit N =
row N (LSB = top).  Strings in the firmware are not GB2312: each byte is an
index into this table (terminated by a byte >= 0xAB), so the 171 glyphs are
regenerated in the same order from the Unicode text in cjk_chars.py.

Replacement sources (the shipped fonts_out/*.bin were built from these):
    ascii16 / ascii12  Ubuntu Sans Mono, weight 600  (Ubuntu Font Licence 1.0)
    cjk16              Droid Sans Fallback           (Apache License 2.0)
Both licences allow the rasterized glyphs to be redistributed inside a
firmware image.  Do not build the shipped image from a font whose licence
does not (e.g. the Microsoft fonts that come with Windows).
"""
import argparse
import hashlib
import os
import struct
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
FW = os.path.dirname(HERE)
OUT = os.path.join(HERE, "fonts_out")
STOCK = os.path.join(FW, "LPM-10A-TX_V2.0.7_260610.bin")   # not in the repo; see require_stock

from lpm10a import symbols as S
from lpm10a.image import require_stock          # noqa: E402
from cjk_chars import CJK                 # noqa: E402

TABLES = {
    #  name      addr         count  w   h  bytes/glyph
    "ascii12": (0x08065904,   95,   6, 12, 12),
    "ascii16": (0x08065D78,   95,   8, 16, 16),
    "cjk16":   (0x08066368,  171,  16, 16, 32),
}


# ---------------------------------------------------------------- packing
def unpack_ascii(blob, w, h):
    """bytes -> list of h rows of w ints (0/1)"""
    bpc = (h + 7) // 8
    px = [[0] * w for _ in range(h)]
    for c in range(w):
        for r in range(h):
            px[r][c] = (blob[c * bpc + r // 8] >> (7 - r % 8)) & 1
    return px


def pack_ascii(px, w, h):
    bpc = (h + 7) // 8
    out = bytearray(w * bpc)
    for c in range(w):
        for r in range(h):
            if px[r][c]:
                out[c * bpc + r // 8] |= 0x80 >> (r % 8)
    return bytes(out)


def unpack_cjk(blob):
    cols = struct.unpack("<16H", blob)
    return [[(cols[c] >> r) & 1 for c in range(16)] for r in range(16)]


def pack_cjk(px):
    cols = [0] * 16
    for c in range(16):
        for r in range(16):
            if px[r][c]:
                cols[c] |= 1 << r
    return struct.pack("<16H", *cols)


def unpack_table(name, blob):
    addr, n, w, h, per = TABLES[name]
    glyphs = [blob[i * per:(i + 1) * per] for i in range(n)]
    if name == "cjk16":
        return [unpack_cjk(g) for g in glyphs]
    return [unpack_ascii(g, w, h) for g in glyphs]


def pack_table(name, glyphs):
    addr, n, w, h, per = TABLES[name]
    assert len(glyphs) == n
    if name == "cjk16":
        return b"".join(pack_cjk(g) for g in glyphs)
    return b"".join(pack_ascii(g, w, h) for g in glyphs)


# ---------------------------------------------------------------- png (no Pillow)
def write_png(path, w, h, rgb):
    def chunk(t, d):
        c = t + d
        return struct.pack(">I", len(d)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
    raw = b"".join(b"\0" + rgb[y * w * 3:(y + 1) * w * 3] for y in range(h))
    open(path, "wb").write(b"\x89PNG\r\n\x1a\n"
                           + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                           + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def sheet_png(path, glyphs, w, h, per_row=16, scale=3, gap=1):
    rows = (len(glyphs) + per_row - 1) // per_row
    W = per_row * (w * scale + gap) + gap
    H = rows * (h * scale + gap) + gap
    img = bytearray(b"\x30" * (W * H * 3))
    for gi, px in enumerate(glyphs):
        gx = gap + (gi % per_row) * (w * scale + gap)
        gy = gap + (gi // per_row) * (h * scale + gap)
        for r in range(h):
            for c in range(w):
                v = 255 if px[r][c] else 0
                for dy in range(scale):
                    o = (gy + r * scale + dy) * W + gx + c * scale
                    img[o * 3:(o + scale) * 3] = bytes([v, v, v]) * scale
    write_png(path, W, H, bytes(img))


# ---------------------------------------------------------------- commands
def stock_blob(name):
    addr, n, w, h, per = TABLES[name]
    tx = open(require_stock(STOCK), "rb").read()
    o = addr - S.APP_BASE + S.FILE_PAYLOAD_OFF
    return tx[o:o + n * per]


def cmd_export():
    os.makedirs(OUT, exist_ok=True)
    for name, (addr, n, w, h, per) in TABLES.items():
        blob = stock_blob(name)
        path = os.path.join(OUT, f"stock_{name}.png")
        sheet_png(path, unpack_table(name, blob), w, h)
        print(f"  {name:8} 0x{addr:08X} {n:3} x {w}x{h}  sha256 {hashlib.sha256(blob).hexdigest()[:16]}  -> {path}")


def cmd_preview():
    for name, (addr, n, w, h, per) in TABLES.items():
        p = os.path.join(OUT, f"{name}.bin")
        if not os.path.exists(p):
            print(f"  {name}: no {p}")
            continue
        blob = open(p, "rb").read()
        assert len(blob) == n * per, (name, len(blob))
        path = os.path.join(OUT, f"{name}.png")
        sheet_png(path, unpack_table(name, blob), w, h)
        print(f"  {name:8} -> {path}")


def _render_cell(font, ch, cw, chh, baseline):
    """Rasterize one character with FreeType's monochrome hinting into a cw x chh cell."""
    from PIL import Image, ImageDraw
    canvas = Image.new("1", (cw + 32, chh + 32), 0)
    ImageDraw.Draw(canvas).text((16, 16 + baseline), ch, font=font, fill=1, anchor="ls")
    return [[1 if canvas.getpixel((16 + x, 16 + y)) else 0 for x in range(cw)] for y in range(chh)]


def cmd_build(mono, cjk, weight):
    from PIL import ImageFont
    os.makedirs(OUT, exist_ok=True)

    def mono_font(px):
        f = ImageFont.truetype(mono, px)
        try:
            f.set_variation_by_axes([weight])
        except Exception:
            pass                                  # not a variable font
        return f

    if cjk is None:
        import pymupdf                            # Droid Sans Fallback ships inside MuPDF
        f = pymupdf.Font("cjk")
        import tempfile
        cjk = os.path.join(tempfile.gettempdir(), "DroidSansFallback.ttf")   # 3.5 MB; not kept in the SDK
        open(cjk, "wb").write(f.buffer)
        print(f"  extracted {f.name} -> {cjk}")

    plan = {
        #  name      font                  cell   baseline
        "ascii16": (mono_font(13),          8, 16, 12),
        "ascii12": (mono_font(10),          6, 12, 9),
        "cjk16":   (ImageFont.truetype(cjk, 16), 16, 16, 14),
    }
    for name, (font, w, h, bl) in plan.items():
        chars = CJK if name == "cjk16" else [chr(c) for c in range(0x20, 0x7F)]
        glyphs = [_render_cell(font, ch, w, h, bl) for ch in chars]
        blob = pack_table(name, glyphs)
        # sanity: nothing but the space glyph may be blank, and the pack must round-trip
        blank = [i for i, g in enumerate(glyphs) if not any(any(r) for r in g)]
        assert blank == ([0] if name != "cjk16" else []), (name, blank)
        assert unpack_table(name, blob) == glyphs
        open(os.path.join(OUT, f"{name}.bin"), "wb").write(blob)
        sheet_png(os.path.join(OUT, f"{name}.png"), glyphs, w, h)
        print(f"  {name:8} {len(blob):5} bytes  sha256 {hashlib.sha256(blob).hexdigest()[:16]}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["export", "preview", "build"])
    ap.add_argument("--mono", default=os.path.expandvars(
        r"%LOCALAPPDATA%\Microsoft\Windows\Fonts\UbuntuSansMono[wght].ttf"))
    ap.add_argument("--cjk", default=None, help="CJK TrueType; default: extract Droid Sans Fallback from pymupdf")
    ap.add_argument("--weight", type=int, default=600)
    a = ap.parse_args()
    {"export": cmd_export, "preview": cmd_preview,
     "build": lambda: cmd_build(a.mono, a.cjk, a.weight)}[a.cmd]()
