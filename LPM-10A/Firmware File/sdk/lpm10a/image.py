"""
LPM-10A firmware container: parse, patch, allocate, re-emit.

Container layout (TX .bin):
    0x0000  char name[32]      internal image name, checked by the bootloader
    0x0020  u32  payload_off   always 0x1000
    0x0024  u32  payload_len
    0x0028  u32  payload_end   == payload_off + payload_len - 1
    0x1000  payload            loaded at APP_BASE (0x0800A000)

There is no CRC or signature anywhere in the container.

New code goes in the "cave": the zero-filled tail between the end of the
stock payload and the end of the final 2 KB flash sector.  Those bytes are
already inside the sector the bootloader must erase to write the end of the
payload, so extending payload_len into them does not touch any sector the
bootloader would otherwise leave alone.
"""
import struct
import hashlib

from . import symbols as S
from .thumb import assemble, verify


class PatchError(Exception):
    pass


STOCK_HELP = """stock image not found:
    {path}

FNIRSI's firmware is not part of this repository.  Download the official
LPM-10A V2.0.7 package from https://www.fnirsi.com (support / downloads),
unzip it, and either copy LPM-10A-TX_V2.0.7_260610.bin to the path above,
put it in a folder named LPM-10A_FNIRSI_originals next to the repository,
or point the LPM10A_STOCK environment variable at it.
sha256 must be 29081ccbbd929a884c7c81fb309aa2894ce2ab84e061918538b3ead8e632940b"""

ORIGINALS_DIR = "LPM-10A_FNIRSI_originals"      # sibling of the repository root


def require_stock(path):
    """Resolve the stock image: the given path, else $LPM10A_STOCK, else the
    originals folder next to the repository.  Exits with instructions if none
    exists, so the vendor file never has to live inside the project."""
    import os
    import sys
    name = os.path.basename(path)
    here = os.path.dirname(os.path.abspath(__file__))          # .../sdk/lpm10a
    repo = os.path.abspath(os.path.join(here, "..", "..", "..", ".."))
    candidates = [path, os.environ.get("LPM10A_STOCK"),
                  os.path.join(os.path.dirname(repo), ORIGINALS_DIR, name)]
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
        name = self.data[:0x20].split(b"\0")[0].decode()
        off, length, end = struct.unpack_from("<III", self.data, 0x20)
        if off != S.FILE_PAYLOAD_OFF or off + length - 1 != end:
            raise PatchError("unexpected container layout")
        self.name = name
        self.payload_off = off
        self.payload_len = length
        self.orig_payload_len = length

        # cave: end of payload .. end of the containing 2 KB sector
        self.cave_start = S.APP_BASE + length
        sector_end = (self.cave_start + S.SECTOR - 1) & ~(S.SECTOR - 1)
        self.cave_end = min(sector_end, S.APP_BASE + len(self.data) - off)
        self.cave_ptr = self.cave_start
        if any(self.data[self.f(self.cave_start):self.f(self.cave_end)]):
            raise PatchError("cave is not empty -- refusing to allocate")

        self.log = []
        self.syms = S.asm_symbols()
        self._ram_ptr = S.RAM_SAFE_ARENA
        self.ram_allocs = []            # (addr, size) in allocation order
        self.regions = {}               # name -> [start, end, ptr]: flash a patch has freed and owns

    # ---------------------------------------------------------- addressing
    def f(self, addr):
        """flash address -> file offset"""
        return addr - S.APP_BASE + self.payload_off

    def read(self, addr, n):
        return bytes(self.data[self.f(addr):self.f(addr) + n])

    # ---------------------------------------------------------- primitives
    def poke(self, addr, expect_hex, new_bytes, why=""):
        """Overwrite bytes, asserting what was there first."""
        expect = bytes.fromhex(expect_hex.replace(" ", ""))
        o = self.f(addr)
        found = bytes(self.data[o:o + len(expect)])
        if found != expect:
            raise PatchError(
                f"@0x{addr:08X}: expected {expect.hex()} but found {found.hex()}"
            )
        if len(new_bytes) != len(expect):
            raise PatchError(f"@0x{addr:08X}: replacement must be the same length")
        self.data[o:o + len(new_bytes)] = new_bytes
        self.log.append((addr, expect, bytes(new_bytes), why, "code"))
        return addr

    def poke_blob(self, addr, expect_sha256, new_bytes, why=""):
        """Replace a data table in place (fonts, lookup tables).  The stock
        bytes are identified by hash rather than listed, and the log records
        kind "blob" so the build report prints a summary instead of kilobytes
        of hex."""
        o = self.f(addr)
        found = bytes(self.data[o:o + len(new_bytes)])
        if hashlib.sha256(found).hexdigest() != expect_sha256:
            raise PatchError(f"@0x{addr:08X}: stock table hash mismatch")
        self.data[o:o + len(new_bytes)] = new_bytes
        self.log.append((addr, found, bytes(new_bytes), why, "blob"))
        return addr

    def set_string(self, addr, text, why=""):
        """Replace a NUL-terminated string in place; must fit its existing slot."""
        o = self.f(addr)
        j = o
        while self.data[j] != 0:
            j += 1
        k = j
        while k < len(self.data) and self.data[k] == 0:
            k += 1
        room = k - o - 1                      # usable chars, NUL not included
        enc = text.encode("ascii")
        if len(enc) > room:
            raise PatchError(
                f'@0x{addr:08X}: "{text}" needs {len(enc)} chars, slot holds {room}'
            )
        old = bytes(self.data[o:j])
        self.data[o:k] = enc + b"\0" * (k - o - len(enc))
        self.log.append((addr, old, enc, why or f'"{old.decode()}" -> "{text}"', "text"))
        return addr

    # ---------------------------------------------------------- allocation
    def alloc_code(self, size, align=4):
        self.cave_ptr = (self.cave_ptr + align - 1) & ~(align - 1)
        if self.cave_ptr + size > self.cave_end:
            raise PatchError(
                f"code cave exhausted: need {size} bytes, "
                f"{self.cave_end - self.cave_ptr} left"
            )
        addr = self.cave_ptr
        self.cave_ptr += size
        return addr

    def alloc_ram(self, size, align=4):
        self._ram_ptr = (self._ram_ptr + align - 1) & ~(align - 1)
        if self._ram_ptr + size > S.RAM_SAFE_ARENA_END:
            raise PatchError("RAM arena exhausted")
        addr = self._ram_ptr
        self._ram_ptr += size
        self.ram_allocs.append((addr, size))
        return addr

    # ---------------------------------------------------------- owned regions
    def add_region(self, name, start, end):
        """Declare a flash range a patch has emptied (e.g. unused glyph slots) as
        allocatable.  The caller is responsible for the range really being free."""
        if start % 4 or end <= start:
            raise PatchError(f"bad region {name}: {start:#x}..{end:#x}")
        self.regions[name] = [start, end, start]

    def alloc_in(self, name, size, align=4):
        r = self.regions[name]
        ptr = (r[2] + align - 1) & ~(align - 1)
        if ptr + size > r[1]:
            raise PatchError(f"region {name} exhausted: need {size} bytes, {r[1] - ptr} left")
        r[2] = ptr + size
        return ptr

    def region_left(self, name):
        r = self.regions[name]
        return r[1] - r[2]

    def write_in(self, name, data, why="", align=4):
        """Allocate in an owned region and write `data` there; logged old -> new."""
        addr = self.alloc_in(name, len(data), align)
        o = self.f(addr)
        old = bytes(self.data[o:o + len(data)])
        self.data[o:o + len(data)] = data
        self.log.append((addr, old, bytes(data), why or "data", "code"))
        return addr

    def emit_code_in(self, name, source, extra_syms=None, why=""):
        """Assemble `source` into an owned region and return its address."""
        syms = dict(self.syms)
        syms.update(extra_syms or {})
        r = self.regions[name]
        probe = assemble((r[2] + 3) & ~3, source, syms)
        addr = self.alloc_in(name, len(probe))
        code = assemble(addr, source, syms)
        if len(code) != len(probe):
            raise PatchError("assembled size changed between passes")
        o = self.f(addr)
        old = bytes(self.data[o:o + len(code)])
        self.data[o:o + len(code)] = code
        self.log.append((addr, old, bytes(code), why or "new code", "code"))
        return addr

    def emit_code_anywhere(self, source, extra_syms=None, why=""):
        """Assemble `source` into whichever owned region has room, else the cave."""
        for name in self.regions:
            try:
                return self.emit_code_in(name, source, extra_syms, why)
            except PatchError:
                continue
        return self.emit_code(source, extra_syms, why)

    def emit_code(self, source, extra_syms=None, why=""):
        """Assemble `source` into the cave and return its address."""
        syms = dict(self.syms)
        syms.update(extra_syms or {})
        # assemble twice: first to learn the size, then at the real address
        probe = assemble(self.cave_start, source, syms)
        addr = self.alloc_code(len(probe))
        code = assemble(addr, source, syms)
        if len(code) != len(probe):
            code = assemble(addr, source, syms)
        self.data[self.f(addr):self.f(addr) + len(code)] = code
        self.log.append((addr, b"", bytes(code), why or "new code", "code"))
        return addr

    # ---------------------------------------------------------- finalise
    def finalize(self):
        """Extend payload_len to cover any allocated cave bytes."""
        used = self.cave_ptr - S.APP_BASE
        if used > self.payload_len:
            self.payload_len = used
            struct.pack_into("<I", self.data, 0x24, self.payload_len)
            struct.pack_into("<I", self.data, 0x28,
                             self.payload_off + self.payload_len - 1)
        return self

    def save(self, path):
        self.finalize()
        open(path, "wb").write(bytes(self.data))
        return hashlib.sha256(bytes(self.data)).hexdigest()

    # ---------------------------------------------------------- reporting
    def diff_offsets(self):
        return [i for i in range(len(self.data)) if self.data[i] != self.original[i]]

    def summary(self):
        d = self.diff_offsets()
        lines = [
            f"source          : {self.name}",
            f"payload len     : 0x{self.orig_payload_len:X} -> 0x{self.payload_len:X}"
            + ("  (extended into cave)" if self.payload_len != self.orig_payload_len else ""),
            f"cave            : 0x{self.cave_start:08X}..0x{self.cave_end:08X} "
            f"({self.cave_end - self.cave_start} bytes, {self.cave_ptr - self.cave_start} used)",
            f"bytes changed   : {len(d)}",
        ]
        return "\n".join(lines)
