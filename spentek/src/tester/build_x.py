"""PN2.34C (cyber theme) -> current build. The compiled C part (Tetris, debug log) is placed in the
flash block that held the Thai letter shapes (118 cells x 32 bytes), which the English UI never reads."""
import hashlib, struct, sys
sys.path.insert(0, "/home/claude/tetris")
import build_apps6 as A, build_v as V
from cc import compile_blob
APP, HDR = 0x0800A000, 0x1000
T_BASE, T_ROOM = 0x08066368, 118 * 32          # the old glyph table; the Thai drawing code after it stays
VERSION = b"PN2.35F\0"
def build(c):
    a, cave_a, na = A.build(c, T_BASE)
    v, cave_v, nv = V.build(a, parent_sha=hashlib.sha256(a).hexdigest(), old=b"PN2.34H\0", new=VERSION)
    d = bytearray(v)
    blob = compile_blob(T_BASE)
    assert len(blob) <= T_ROOM, f"C part {len(blob)} > {T_ROOM}"
    o = T_BASE - APP + HDR
    d[o:o + len(blob)] = blob
    off, ln, _ = struct.unpack_from("<III", d, 0x20)
    size = HDR + -(-ln // 4096) * 4096
    assert not any(d[off + ln:]); d = d[:size]
    return bytes(d), len(blob), size - off - ln
if __name__ == "__main__":
    out, n, tail = build(open(sys.argv[1], "rb").read())
    open(sys.argv[2], "wb").write(out)
    print(f"C part {n} of {T_ROOM} bytes in the old letter block; {tail} bytes free at the end; file {len(out)} bytes")
    print("sha256", hashlib.sha256(out).hexdigest())
