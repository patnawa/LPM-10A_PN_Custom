"""
LPM-10A receiver firmware image: a raw Cortex-M image, no container.

    file offset 0  <->  flash 0x08006800   (see symbols.APP_BASE)

The vendor file is a raw application image; releases also wrap the patched
image in the update format implemented in container.py. Patches can append
code up to symbols.EXTEND_LIMIT. A successful host file copy alone does not
establish that the receiver accepted or runs the image.

The Thumb assembler is shared with the transmitter SDK (../../sdk/lpm10a).
"""
import hashlib
import os
import sys

from . import symbols as S

HERE = os.path.dirname(os.path.abspath(__file__))
TX_SDK = os.path.abspath(os.path.join(HERE, "..", "..", "sdk"))
if TX_SDK not in sys.path:
    sys.path.append(TX_SDK)          # appended, so this SDK's own modules win
from lpm10a.thumb import assemble, verify   # noqa: E402,F401

STOCK_NAME = "APP_LPM-10RX_V3.0.0_260416.bin"
ORIGINALS_DIR = "LPM-10A_FNIRSI_originals"      # sibling of the repository root

STOCK_HELP = """stock receiver image not found:
    {path}

FNIRSI's firmware is not part of this repository.  Download the official
matching LPM-10A firmware package from https://www.fnirsi.com (support / downloads),
unzip it, and either copy APP_LPM-10RX_V3.0.0_260416.bin to the path above,
put it in a folder named LPM-10A_FNIRSI_originals next to the repository,
or point the LPM10RX_STOCK environment variable at it.
sha256 must be """ + S.STOCK_SHA256


class PatchError(Exception):
    pass


def require_stock(path):
    """$LPM10RX_STOCK when set (an error if it does not point at a file), else
    the given path, else the originals folder next to the repository.  Exits
    with instructions if none exists."""
    name = os.path.basename(path)
    repo = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
    env = os.environ.get("LPM10RX_STOCK")
    if env and not os.path.isfile(env):
        sys.exit(f"LPM10RX_STOCK is set to {env!r} but that is not a file")
    candidates = [env, path, os.path.join(os.path.dirname(repo), ORIGINALS_DIR, name)]
    for c in candidates:
        if c and os.path.isfile(c):
            if c != path:
                print(f"stock image : {c}")
            return c
    sys.exit(STOCK_HELP.format(path=path))


class Image:
    def __init__(self, path):
        self.path = require_stock(path)
        with open(self.path, "rb") as source:
            self.data = bytearray(source.read())
        self.original = bytes(self.data)
        if len(self.data) != S.APP_SIZE:
            raise PatchError(f"unexpected image size {len(self.data)} (stock is {S.APP_SIZE})")
        self.log = []
        self.syms = S.asm_symbols()

    # ---------------------------------------------------------- addressing
    def f(self, addr):
        """flash address -> file offset"""
        o = addr - S.APP_BASE
        if not 0 <= o < len(self.data):
            raise PatchError(f"0x{addr:08X} is outside the image")
        return o

    def read(self, addr, n):
        o = self._range(addr, n)
        return bytes(self.data[o:o + n])

    def _range(self, addr, size):
        o = addr - S.APP_BASE
        if size < 0 or o < 0 or o + size > len(self.data):
            raise PatchError(f"@0x{addr:08X}: {size} bytes outside the image")
        return o

    # ---------------------------------------------------------- primitives
    def poke(self, addr, expect_hex, new_bytes, why=""):
        """Overwrite bytes, asserting what was there first; same length only."""
        expect = bytes.fromhex(expect_hex.replace(" ", ""))
        o = self._range(addr, len(expect))
        found = bytes(self.data[o:o + len(expect)])
        if found != expect:
            raise PatchError(f"@0x{addr:08X}: expected {expect.hex()} but found {found.hex()}")
        if len(new_bytes) != len(expect):
            raise PatchError(f"@0x{addr:08X}: replacement is {len(new_bytes)} bytes, slot is {len(expect)}")
        self.data[o:o + len(new_bytes)] = new_bytes
        self.log.append((addr, expect, bytes(new_bytes), why, "code"))
        return addr

    def set_string(self, addr, text, why=""):
        o = self.f(addr)
        j = o
        while j < len(self.data) and self.data[j] != 0:
            j += 1
        if j == len(self.data):
            raise PatchError(f"@0x{addr:08X}: unterminated string")
        k = j
        while k < len(self.data) and self.data[k] == 0:
            k += 1
        room = k - o - 1
        enc = text.encode("ascii")
        if len(enc) > room:
            raise PatchError(f'@0x{addr:08X}: "{text}" needs {len(enc)} chars, slot holds {room}')
        old = bytes(self.data[o:j])
        self.data[o:k] = enc + b"\0" * (k - o - len(enc))
        self.log.append((addr, old, enc, why or f'"{old.decode()}" -> "{text}"', "text"))
        return addr

    def assemble_at(self, addr, source, extra_syms=None):
        syms = dict(self.syms)
        syms.update(extra_syms or {})
        return assemble(addr, source, syms)

    # ---------------------------------------------------------- output
    def extend(self, n, why=""):
        """Append n zero bytes (a multiple of 4) after the image and return the
        flash address of the new space.  The update container carries the
        payload length, so a longer image is programmed as-is (established on
        hardware for the TX on 2026-09-18 and for the RX container format on
        2026-09-21); the version page and bootloader pages stay untouched."""
        if n <= 0 or n % 4:
            raise PatchError("extend: size must be a positive multiple of 4")
        start = S.APP_BASE + len(self.data)
        if start + n > S.EXTEND_LIMIT:
            raise PatchError(f"extend: 0x{start + n:08X} would pass EXTEND_LIMIT 0x{S.EXTEND_LIMIT:08X}")
        self.data += bytes(n)
        self.log.append((start, b"", b"", why or f"image extended by {n} bytes at 0x{start:08X}", "note"))
        return start

    def save(self, path):
        if len(self.data) < S.APP_SIZE or len(self.data) % 4 or S.APP_BASE + len(self.data) > S.EXTEND_LIMIT:
            raise PatchError("refusing to save a truncated, unaligned or over-long receiver image")
        with open(path, "wb") as output:
            output.write(bytes(self.data))
        return hashlib.sha256(bytes(self.data)).hexdigest()

    def diff_offsets(self):
        n = len(self.original)
        return [i for i in range(n) if self.data[i] != self.original[i]] + list(range(n, len(self.data)))
