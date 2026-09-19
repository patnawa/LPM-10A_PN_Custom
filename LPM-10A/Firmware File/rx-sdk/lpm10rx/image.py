"""
LPM-10A receiver firmware image: a raw Cortex-M image, no container.

    file offset 0  <->  flash 0x08006800   (see symbols.APP_BASE)

There is no header, no length field and no checksum: the bootloader writes
the file as it is.  Patches therefore never change the file size; every
edit is an in-place replacement of the same number of bytes.

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
        self.data = bytearray(open(self.path, "rb").read())
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
        return bytes(self.data[self.f(addr):self.f(addr) + n])

    # ---------------------------------------------------------- primitives
    def poke(self, addr, expect_hex, new_bytes, why=""):
        """Overwrite bytes, asserting what was there first; same length only."""
        expect = bytes.fromhex(expect_hex.replace(" ", ""))
        o = self.f(addr)
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
        while self.data[j] != 0:
            j += 1
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
    def save(self, path):
        open(path, "wb").write(bytes(self.data))
        return hashlib.sha256(bytes(self.data)).hexdigest()

    def diff_offsets(self):
        return [i for i in range(len(self.data)) if self.data[i] != self.original[i]]
