"""
Update container for the LPM-10A receiver bootloader.

FNIRSI ships the RX application as a raw image (vector table first), but the
receiver's USB-disk bootloader only programs a file in the same container
layout the TX bootloader uses.  Established on the owner's unit on 2026-09-21
by watching the bootloader's SRAM over SWD while files were copied
(docs/RX-UPDATE-PROCEDURE-2026-09-21.md):

    0x0000  char name[32]      internal image name (zero padded)
    0x0020  u32  payload_off   always 0x1000
    0x0024  u32  payload_len   raw image length
    0x0028  u32  payload_end   == payload_off + payload_len - 1
    0x002C  zeros to 0x1000
    0x1000  raw application image (loaded at 0x08006800)
    ...     zero padding to a multiple of 4 KB

A raw image copied to the drive leaves the status file at UNKOWN.TXT and
changes nothing.  A container written slowly (sector by sector with pauses)
makes the bootloader give up early (APPRUN.TXT).  A container copied the
ordinary way (Explorer / Copy-Item) is programmed within about a second and the
probe reboots into the new application.
"""
import struct

HEADER_SIZE = 0x1000
PAD_UNIT = 0x1000
# Kept identical to the vendor file name, like the TX builds do: the header
# name did not affect acceptance in testing, so there is no reason to vary it.
DEFAULT_NAME = "APP_LPM-10RX_V3.0.0_260416.bin"


def wrap(raw, name=DEFAULT_NAME):
    """Return the update container for a raw receiver image."""
    name_bytes = name.encode("ascii")
    if not name_bytes or len(name_bytes) > 31 or b"\0" in name_bytes:
        raise ValueError("container name must be 1-31 ASCII characters without NUL")
    if not raw or len(raw) % 4:
        raise ValueError("raw image must be a non-empty multiple of 4 bytes")
    header = name_bytes.ljust(32, b"\0") + struct.pack(
        "<III", HEADER_SIZE, len(raw), HEADER_SIZE + len(raw) - 1)
    body = header.ljust(HEADER_SIZE, b"\0") + bytes(raw)
    pad = (-len(body)) % PAD_UNIT
    return body + b"\0" * pad


def unwrap(container):
    """Return (name, raw image) from a container, checking the header."""
    if len(container) < HEADER_SIZE + 4:
        raise ValueError("container too short")
    name_bytes, terminator, name_padding = container[:32].partition(b"\0")
    if not name_bytes or not terminator or any(name_padding):
        raise ValueError("container name must be non-empty and zero padded")
    name = name_bytes.decode("ascii")
    off, length, end = struct.unpack_from("<III", container, 0x20)
    if off != HEADER_SIZE or end != off + length - 1:
        raise ValueError("bad container header fields")
    if not length or length % 4:
        raise ValueError("raw image must be a non-empty multiple of 4 bytes")
    expected_size = ((off + length + PAD_UNIT - 1) // PAD_UNIT) * PAD_UNIT
    if len(container) != expected_size:
        raise ValueError("container size must include exactly the required 4 KB padding")
    if any(container[0x2C:HEADER_SIZE]):
        raise ValueError("header padding is not zero")
    if off + length > len(container) or any(container[off + length:]):
        raise ValueError("payload length disagrees with the file")
    return name, bytes(container[off:off + length])


def _main(argv=None):
    """python -m lpm10rx.container wrap <raw.bin> [out.bin] [name]   |   check <file.bin>"""
    import argparse
    import hashlib
    ap = argparse.ArgumentParser(description="RX update container: wrap a raw image, or check a file")
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("wrap", help="wrap a raw receiver image into the update container")
    w.add_argument("raw")
    w.add_argument("out", nargs="?")
    w.add_argument("--name", default=DEFAULT_NAME, help="internal name (default: the vendor file name)")
    c = sub.add_parser("check", help="say whether a file is a raw image or a container, with hashes")
    c.add_argument("file")
    a = ap.parse_args(argv)
    if a.cmd == "wrap":
        with open(a.raw, "rb") as source:
            raw = source.read()
        out = a.out or (a.raw[:-4] if a.raw.lower().endswith(".bin") else a.raw) + "-update.bin"
        data = wrap(raw, a.name)
        with open(out, "wb") as output:
            output.write(data)
        print(f"wrote {out}: {len(data)} bytes, name {a.name!r}, payload {len(raw)} bytes")
        print(f"sha256 {hashlib.sha256(data).hexdigest()}")
        print("copy this file to the BOOTLOADER drive with Explorer")
    else:
        with open(a.file, "rb") as source:
            data = source.read()
        try:
            name, raw = unwrap(data)
            print(f"container: name {name!r}, payload {len(raw)} bytes, payload sha256 {hashlib.sha256(raw).hexdigest()}")
            print("container structure is valid; this does not verify the firmware payload")
        except ValueError:
            sp = int.from_bytes(data[:4], "little")
            kind = "raw image (vector table first)" if 0x20000000 <= sp <= 0x20006000 else "unknown"
            print(f"{kind}: {len(data)} bytes, sha256 {hashlib.sha256(data).hexdigest()}")
            print("NOT a container: the bootloader ignores it (UNKOWN.TXT); wrap it first")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
