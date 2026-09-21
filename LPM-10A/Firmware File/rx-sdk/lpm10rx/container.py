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
    if not name_bytes or len(name_bytes) > 31:
        raise ValueError("container name must be 1-31 ASCII characters")
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
    name = container[:32].split(b"\0")[0].decode("ascii")
    off, length, end = struct.unpack_from("<III", container, 0x20)
    if off != HEADER_SIZE or end != off + length - 1:
        raise ValueError("bad container header fields")
    if any(container[0x2C:HEADER_SIZE]):
        raise ValueError("header padding is not zero")
    if off + length > len(container) or any(container[off + length:]):
        raise ValueError("payload length disagrees with the file")
    return name, bytes(container[off:off + length])
