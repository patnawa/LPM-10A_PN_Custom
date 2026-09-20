"""Temporary PN 1.13 identity diagnostic: turn the lamp on during GPIO init.

This changes one byte in the exact PN 1.13 image. It changes neither the
detector nor audio timing and is not a release or a Digital-tail fix. The lamp
key and shutdown still use the original code. Physical lamp behavior remains
to be confirmed on the owner's probe.

The command is read-only by default. --write creates only the fixed local
experimental artifact; it never copies anything to a device or Desktop.
"""
import argparse
import hashlib
import json
from pathlib import Path


APP_BASE = 0x08006800
IMAGE_SIZE = 26152
PARENT_SHA256 = '2cafd8a234a9b372a4d09c4969b28c8c35a45f05b72c57d2248d39f22cf7373b'
SITE = 0x08007D54
OLD = bytes.fromhex('00f00cfa')  # BL 0x08008170: GPIO PBC (+0x28), clear PA10.
NEW = bytes.fromhex('00f016fa')  # BL 0x08008184: GPIO PBSC (+0x18), set PA10.
CHANGED_ADDRESS = 0x08007D56
EXPERIMENTAL = Path(__file__).resolve().parent.parent / 'experimental'
DEFAULT_PARENT = EXPERIMENTAL / 'APP_LPM-10RX_PN1.13-audio-clock.bin'
DEFAULT_OUTPUT = EXPERIMENTAL / 'APP_LPM-10RX_PN1.13-id-lamp.bin'


class IdentityMarkerError(ValueError):
    """The input or existing local output is not the exact expected image."""


def marker_bytes(parent):
    """Validate the complete input and call site before changing a copy."""
    original = bytes(parent)
    if len(original) != IMAGE_SIZE or hashlib.sha256(original).hexdigest() != PARENT_SHA256:
        raise IdentityMarkerError('Identity marker requires the complete, exact PN 1.13 audio-clock image')
    offset = SITE - APP_BASE
    if original[offset:offset + len(OLD)] != OLD:
        raise IdentityMarkerError(f'Identity marker call-site guard failed at {SITE:#x}')
    candidate = bytearray(original)
    candidate[offset:offset + len(NEW)] = NEW
    changes = [APP_BASE + i for i, (old, new) in enumerate(zip(original, candidate)) if old != new]
    if changes != [CHANGED_ADDRESS]:
        raise IdentityMarkerError('Identity marker exceeded its one-byte change scope')
    return bytes(candidate)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--parent', type=Path, default=DEFAULT_PARENT,
                        help='read the exact PN 1.13 parent from this path')
    parser.add_argument('--write', action='store_true',
                        help='create the fixed local experimental artifact (default: dry run)')
    args = parser.parse_args(argv)
    try:
        parent = args.parent.read_bytes()
        candidate = marker_bytes(parent)
        status = 'dry-run'
        if args.write:
            # Validation precedes every output operation. An unexpected existing
            # file is never overwritten, and the parent is never modified.
            if DEFAULT_OUTPUT.exists():
                if DEFAULT_OUTPUT.read_bytes() != candidate:
                    raise IdentityMarkerError(f'Refusing to overwrite unexpected output: {DEFAULT_OUTPUT}')
                status = 'already-present'
            else:
                DEFAULT_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
                with DEFAULT_OUTPUT.open('xb') as target:
                    target.write(candidate)
                status = 'written-local-only'
        print(json.dumps({
            'purpose': 'temporary startup lamp identity diagnostic; not a tail fix',
            'status': status,
            'parent': str(args.parent.resolve()),
            'output': str(DEFAULT_OUTPUT),
            'parent_sha256': hashlib.sha256(parent).hexdigest(),
            'candidate_sha256': hashlib.sha256(candidate).hexdigest(),
            'bytes': len(candidate),
            'changed_addresses': [hex(CHANGED_ADDRESS)],
            'changed_byte': {'old': OLD[2], 'new': NEW[2]},
        }, indent=2))
    except (OSError, IdentityMarkerError) as error:
        parser.exit(1, f'{error}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
