"""Version tag: the application's version string names the PN build.

The receiver application keeps its version string ("3.0.0", 8-byte slot at
0x0800CDE4) and, at every boot, rewrites flash page 0x0801F000 with it when the
page differs (`version_page_check`, plain strlen-based copy).  The bootloader
names the empty status file on its BOOTLOADER drive after that page, so the
drive shows which build is installed: "PN1.20.TXT" instead of "3.0.0.TXT".

Applied by build.py as the last step of every profile from pn1.20 on (see
profiles.apply_profile); it is not a registry patch, so the per-module parent
hashes stay those of the untagged chain.  The bootloader does not consult this
page when accepting an update (containers were accepted with the page at both
3.0.0 and 3.0.2 on 2026-09-21), and the `_V3.` compatibility tag it does check
lives on its own page (0x0800676E), untouched.
"""
from lpm10rx.image import PatchError

VERSION_STRING = 0x0800CDE4
SLOT = 8
STOCK = b"3.0.0\0\0\0"


def tag_for(profile_name):
    """'pn1.20' -> 'PN1.20' (6 chars + NUL in the 8-byte slot)."""
    tag = profile_name.upper()
    if not tag.startswith("PN") or len(tag) > SLOT - 1 or not tag.isascii():
        raise PatchError(f"version tag {tag!r} does not fit the {SLOT}-byte slot")
    return tag


def apply(img, profile_name):
    tag = tag_for(profile_name).encode("ascii")
    if img.read(VERSION_STRING, SLOT) != STOCK:
        raise PatchError("version tag: the version string slot is not the stock '3.0.0'")
    img.poke(VERSION_STRING, STOCK.hex(), tag.ljust(SLOT, b"\0"),
             f'version string "3.0.0" -> "{tag.decode()}": the BOOTLOADER drive shows {tag.decode()}.TXT')
    img.version_tag = tag.decode()
