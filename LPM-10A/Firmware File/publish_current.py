"""Publish selected PN releases from experimental/ and rewrite SHA256SUMS.txt.

    python publish_current.py LPM-10A-TX_PN2.33-cable-safe.bin APP_LPM-10RX_PN1.29-levels-update.bin

Only obsolete PN releases listed in the previous manifest are removed. Stock
firmware and other local files are preserved. Sources and destinations are
checked, staged and backed up before replacing any published file.
"""
import argparse
import hashlib
import os
from pathlib import Path
import re
import shutil
import tempfile

HERE = Path(__file__).resolve().parent
DEFAULT_NAMES = (
    "LPM-10A-TX_PN2.33-cable-safe.bin",
    "APP_LPM-10RX_PN1.29-levels-update.bin",
)
MANIFEST = "SHA256SUMS.txt"
RELEASE_NAME = re.compile(
    r"(?:LPM-10A-TX_PN[0-9]+\.[0-9]+[A-Z]?(?:-[A-Za-z0-9_-]+)?|"
    r"APP_LPM-10RX_PN[0-9]+\.[0-9]+[A-Z]?(?:-[A-Za-z0-9_-]+)?-update)\.bin"
)


def _release_name(name):
    if not isinstance(name, str) or not RELEASE_NAME.fullmatch(name):
        raise ValueError(f"not a TX PN release or RX PN update filename: {name!r}")
    return name


def _previous_releases(path):
    """A manifest grants cleanup authority only for named PN release files."""
    if not path.exists():
        return []
    names = []
    for line in path.read_text(encoding="ascii").splitlines():
        if not line.strip():
            continue
        match = re.fullmatch(r"[0-9a-fA-F]{64}  ([A-Za-z0-9][A-Za-z0-9._-]*\.bin)", line)
        if match is None:
            raise ValueError("invalid SHA256SUMS.txt; refusing to change published files")
        name = match[1]
        if name.casefold() in {n.casefold() for n in names}:
            raise ValueError("duplicate release filename in SHA256SUMS.txt")
        if RELEASE_NAME.fullmatch(name):
            names.append(name)
    return names


def publish(names=DEFAULT_NAMES, directory=HERE):
    """Return (filename, digest) pairs after an all-preflighted publication.

    File replacements are atomic individually; an ordinary I/O exception rolls
    back the set. This is not a transaction against power loss or concurrent
    publishers, so run one publisher at a time.
    """
    root = Path(directory).resolve()
    names = [_release_name(name) for name in names]
    if not names or len({name.casefold() for name in names}) != len(names):
        raise ValueError("provide at least one release, with no duplicate filenames")
    manifest = root / MANIFEST
    if manifest.is_symlink() or (manifest.exists() and not manifest.is_file()):
        raise ValueError("SHA256SUMS.txt must be a regular file")
    previous = _previous_releases(manifest)
    stale = list(dict.fromkeys(name for name in previous if name.casefold() not in {n.casefold() for n in names}))
    affected = list(dict.fromkeys([*names, *stale, MANIFEST]))
    for name in affected:
        path = root / name
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise ValueError(f"destination must be a regular file: {path}")

    sources = {}
    experimental = root / "experimental"
    for name in names:
        path = experimental / name
        if path.is_symlink() or path.resolve().parent != experimental.resolve() or not path.is_file():
            raise ValueError(f"release source is not a regular file: {path}")
        data = path.read_bytes()
        if not data:
            raise ValueError(f"release source is empty: {path}")
        sources[name] = data
    digests = [(name, hashlib.sha256(sources[name]).hexdigest()) for name in names]
    sources[MANIFEST] = "".join(f"{digest}  {name}\n" for name, digest in digests).encode("ascii")

    stage = Path(tempfile.mkdtemp(prefix=".publish-", dir=root))
    changed = []
    backups = {}
    keep_backups = False
    try:
        for i, name in enumerate(affected):
            target = root / name
            backup = stage / f"backup-{i}"
            if target.exists():
                shutil.copy2(target, backup)
                backups[name] = backup
            else:
                backups[name] = None
        for name, data in sources.items():
            (stage / name).write_bytes(data)
        try:
            for name in sources:
                os.replace(stage / name, root / name)
                changed.append(name)
            for name in stale:
                target = root / name
                if target.exists():
                    target.unlink()
                    changed.append(name)
        except OSError:
            try:
                for name in reversed(changed):
                    if backups[name] is None:
                        (root / name).unlink()
                    else:
                        os.replace(backups[name], root / name)
            except OSError as rollback_error:
                keep_backups = True
                raise RuntimeError(f"publication rollback failed; recovery files are in {stage}") from rollback_error
            raise
    finally:
        if not keep_backups:
            shutil.rmtree(stage)
    return digests


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("names", nargs="*", help="PN release filenames in experimental/")
    args = parser.parse_args(argv)
    try:
        digests = publish(args.names or DEFAULT_NAMES)
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f"publication failed: {error}\n")
    for name, digest in digests:
        print(digest, name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
