#!/usr/bin/env python3
"""Verify an RX release against an exact rebuild of its named profile.

    python verify_release.py                      # latest available profile update
    python verify_release.py image.bin --profile pn1.22

Accepts either a raw image or an update container. This checks artifact
integrity and reproducibility, not runtime behaviour or hardware acceptance.
Legacy battery/digital emulation checks remain in verify.py and unit tests.
"""
import argparse
from contextlib import redirect_stdout
import hashlib
import io
from pathlib import Path

from lpm10rx.container import unwrap, wrap
from lpm10rx.image import Image, PatchError, STOCK_NAME
from lpm10rx import symbols as S
from profiles import PROFILES, LATEST, apply_profile

FW = Path(__file__).resolve().parent.parent


def verify_release(path, profile, stock_path=None):
    """Return (format, payload SHA-256) or raise on any integrity mismatch."""
    data = Path(path).read_bytes()
    # The exact expected raw image comparison below also rejects any malformed
    # container that cannot be parsed; it cannot silently pass as a raw image.
    try:
        _, payload = unwrap(data)
        kind = "update container"
    except ValueError:
        payload = data
        kind = "raw image"
    img = Image(stock_path if stock_path is not None else FW / STOCK_NAME)
    if hashlib.sha256(img.original).hexdigest() != S.STOCK_SHA256:
        raise PatchError("stock receiver image does not match the pinned V3.0.0 SHA-256")
    apply_profile(img, profile)
    expected = bytes(img.data)
    if payload != expected:
        raise PatchError(
            f"{path} does not match {profile.name}: expected {len(expected)} payload bytes "
            f"with SHA-256 {hashlib.sha256(expected).hexdigest()}, got {len(payload)} bytes "
            f"with SHA-256 {hashlib.sha256(payload).hexdigest()}"
        )
    if kind == "update container" and data != wrap(expected):
        raise PatchError(f"{path} does not match the canonical update container for {profile.name}")
    return kind, hashlib.sha256(payload).hexdigest()


def default_image(profile):
    """Find a named profile in the current, candidate, or archived location.

    Prefer a current copy and verify it even if corrupt: never silently fall
    back from a present but mismatched release to another artifact.
    """
    output = Path(profile.output)
    name = output.stem + '-update.bin'
    candidates = (FW / name, FW / output.parent / name, FW / 'archive' / name)
    return next((path for path in candidates if path.is_file()), candidates[0])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", nargs="?", type=Path)
    parser.add_argument("--profile", choices=PROFILES, default=LATEST)
    args = parser.parse_args(argv)
    profile = PROFILES[args.profile]
    path = args.image if args.image is not None else default_image(profile)
    try:
        with redirect_stdout(io.StringIO()):
            kind, digest = verify_release(path, profile)
    except (OSError, ValueError, PatchError) as error:
        parser.exit(1, f"verification failed: {error}\n")
    print(f"verified {profile.name}: {path} ({kind})")
    print(f"payload sha256 {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
