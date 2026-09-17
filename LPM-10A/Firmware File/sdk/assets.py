#!/usr/bin/env python3
"""
Export / replace the LPM-10A UI graphics.

    python assets.py export [outdir]
    python assets.py import <index> <image.png> [--out file.bin]

Asset format (22 blobs, pointed to from RAM 0x200000E4..0x20000138, fetched
by the getter at 0x0800E3B0):

    u16 magic   0x1000
    u16 width
    u16 height
    u16 flags   0x1B01
    u16 pixels[width*height]   RGB565, little-endian

A replacement must keep the exact same width and height: the blobs are packed
back-to-back in flash and every pointer is absolute, so resizing one would
shift all the others.
"""
import os
import struct
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
FW = os.path.dirname(HERE)
from lpm10a import symbols as S
from lpm10a.image import require_stock   # noqa: E402

STOCK = os.path.join(FW, "LPM-10A-TX_V2.0.7_260610.bin")   # not in the repo; see require_stock

# asset index -> flash address (order as read by the getter at 0x0800E3B0)
ASSETS = [
    0x08020000, 0x08027E65, 0x08021498, 0x080244E0, 0x0801EB68, 0x0804F6BD,
    0x08026DA9, 0x0804DF8D, 0x08064639, 0x08063D3B, 0x08027951, 0x0801E746,
    0x080252EC, 0x080252ED, 0x08029DED, 0x08032E55, 0x0803BEBD, 0x08044F25,
    0x08022930, 0x08026225, 0x08050DED, 0x08051895,
]


def f2o(addr, payload_off=0x1000):
    return addr - S.APP_BASE + payload_off


def rgb565_to_rgb(v):
    r, g, b = (v >> 11) & 0x1F, (v >> 5) & 0x3F, v & 0x1F
    return (r * 255 + 15) // 31, (g * 255 + 31) // 63, (b * 255 + 15) // 31


def rgb_to_rgb565(r, g, b):
    return ((r * 31 + 127) // 255 << 11) | ((g * 63 + 127) // 255 << 5) | ((b * 31 + 127) // 255)


def write_png(path, w, h, rgb):
    def chunk(t, d):
        c = t + d
        return struct.pack(">I", len(d)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
    raw = b"".join(b"\0" + rgb[y * w * 3:(y + 1) * w * 3] for y in range(h))
    open(path, "wb").write(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b""))


def read_png(path):
    """Minimal PNG reader: 8-bit RGB or RGBA, non-interlaced."""
    d = open(path, "rb").read()
    if d[:8] != b"\x89PNG\r\n\x1a\n":
        raise SystemExit("not a PNG")
    pos, idat, w = 8, b"", None
    while pos < len(d):
        ln = struct.unpack(">I", d[pos:pos + 4])[0]
        typ = d[pos + 4:pos + 8]
        body = d[pos + 8:pos + 8 + ln]
        if typ == b"IHDR":
            w, h, depth, ctype, _, _, inter = struct.unpack(">IIBBBBB", body)
            if depth != 8 or ctype not in (2, 6) or inter:
                raise SystemExit("PNG must be 8-bit RGB/RGBA, non-interlaced")
        elif typ == b"IDAT":
            idat += body
        elif typ == b"IEND":
            break
        pos += 12 + ln
    bpp = 3 if ctype == 2 else 4
    raw = zlib.decompress(idat)
    stride = w * bpp
    out = bytearray()
    prev = bytearray(stride)
    p = 0
    for _ in range(h):
        ft = raw[p]; p += 1
        line = bytearray(raw[p:p + stride]); p += stride
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0
            b_ = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            if ft == 1:   line[i] = (line[i] + a) & 0xFF
            elif ft == 2: line[i] = (line[i] + b_) & 0xFF
            elif ft == 3: line[i] = (line[i] + ((a + b_) >> 1)) & 0xFF
            elif ft == 4:
                pp = a + b_ - c
                pa, pb, pc = abs(pp - a), abs(pp - b_), abs(pp - c)
                pr = a if (pa <= pb and pa <= pc) else (b_ if pb <= pc else c)
                line[i] = (line[i] + pr) & 0xFF
        out += line
        prev = line
    return w, h, bytes(out), bpp


def cmd_export(outdir):
    os.makedirs(outdir, exist_ok=True)
    tx = open(require_stock(STOCK), "rb").read()
    for i, a in enumerate(ASSETS):
        o = f2o(a)
        magic, w, h, flags = struct.unpack_from("<HHHH", tx, o)
        if magic != 0x1000 or w == 0 or h == 0 or o + 8 + w * h * 2 > len(tx):
            print(f"  idx{i:2} 0x{a:08X}  skipped (magic=0x{magic:04X})")
            continue
        px = tx[o + 8:o + 8 + w * h * 2]
        rgb = bytearray()
        for k in range(w * h):
            rgb += bytes(rgb565_to_rgb(px[k * 2] | (px[k * 2 + 1] << 8)))
        name = f"asset{i:02d}_{a:08X}_{w}x{h}.png"
        write_png(os.path.join(outdir, name), w, h, bytes(rgb))
        print(f"  idx{i:2} 0x{a:08X}  {w:3}x{h:3}  -> {name}")


def cmd_import(index, png, out):
    tx = bytearray(open(require_stock(STOCK), "rb").read())
    a = ASSETS[index]
    o = f2o(a)
    magic, w, h, flags = struct.unpack_from("<HHHH", tx, o)
    if magic != 0x1000:
        raise SystemExit(f"asset {index} is not an RGB565 blob")
    pw, ph, raw, bpp = read_png(png)
    if (pw, ph) != (w, h):
        raise SystemExit(f"size mismatch: asset is {w}x{h}, PNG is {pw}x{ph}. "
                         "Assets are packed back-to-back; dimensions must match.")
    buf = bytearray()
    for k in range(w * h):
        r, g, b = raw[k * bpp], raw[k * bpp + 1], raw[k * bpp + 2]
        buf += struct.pack("<H", rgb_to_rgb565(r, g, b))
    tx[o + 8:o + 8 + w * h * 2] = buf
    open(out, "wb").write(bytes(tx))
    print(f"replaced asset {index} (0x{a:08X}, {w}x{h}) -> {out}")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("export", "import"):
        print(__doc__)
        sys.exit(1)
    if sys.argv[1] == "export":
        cmd_export(sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "assets_out"))
    else:
        idx = int(sys.argv[2])
        png = sys.argv[3]
        out = sys.argv[5] if "--out" in sys.argv else os.path.join(
            FW, "LPM-10A-TX_V2.0.7-art_260610.bin")
        cmd_import(idx, png, out)
