"""End-to-end check of a Thai build: every screen rendered by the built image's
own code (language 2, nothing intercepted) must be pixel-identical to the
mock-up model (a build without thai-ui, Chinese drawers intercepted, the Thai
wording drawn from the shipped cell table).  English must be identical between
the two builds.

    python -m thai.compare <thai-build.bin> [reference-build.bin]
(the reference defaults to the same patch set without thai-ui, built in memory)
"""
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from thai.engine import Scene                       # noqa: E402
from thai.cells import Table                        # noqa: E402
from thai.wording import TH, ASCII_TH               # noqa: E402
from thai.mockup import SCREENS, ALL_SCREENS        # noqa: E402

FONT = Table.shipped(os.path.join(os.path.dirname(HERE), "fonts_out"))


def render(image, lang, thai, sid):
    s = Scene(image=image, lang=lang, thai=(TH if thai else None), ascii_thai=(ASCII_TH if thai else None), font=FONT)
    fn, kw = next((f, k) for i, _, f, k in ALL_SCREENS if i == sid)
    fn(s, **kw)
    return s


def thai_texts_drawn(image):
    """Every Thai string the model draws over all states (for the coverage check)."""
    seen = set()
    for sid, title, fn, kw in ALL_SCREENS:
        m = render("reference", 2, True, sid)
        seen.update(t for k, t, x, y, fg, ex in m.log if k == "thai")
    return seen


def diff(a, b):
    return [(x, y) for y in range(320) for x in range(240) if a[y][x] != b[y][x]]


def compare(thai_bin, ref_bin, ids=None, save_dir=None):
    """-> list of (screen, language, differing pixel count); empty means identical."""
    bad = []
    for sid, title, fn, kw in ALL_SCREENS:
        if ids and sid not in ids:
            continue
        # Thai: firmware vs model
        fw = render(thai_bin, 2, False, sid)
        model = render(ref_bin, 2, True, sid)
        d = diff(fw.fb, model.fb)
        if d or model.missing:
            bad.append((sid, "th", len(d), model.missing))
            if save_dir:
                fw.image(2).save(os.path.join(save_dir, f"{sid}_fw.png"))
                model.image(2).save(os.path.join(save_dir, f"{sid}_model.png"))
        # English: the two builds must agree
        e1 = render(thai_bin, 1, False, sid)
        e2 = render(ref_bin, 1, False, sid)
        d = diff(e1.fb, e2.fb)
        if d:
            bad.append((sid, "en", len(d), []))
    return bad


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    thai_bin = sys.argv[1]
    ref_bin = sys.argv[2] if len(sys.argv) > 2 else "reference"
    out = os.path.join(HERE, "cmp")
    os.makedirs(out, exist_ok=True)
    bad = compare(thai_bin, ref_bin, save_dir=out)
    for b in bad:
        print("DIFF", b)
    print("identical" if not bad else f"{len(bad)} screens differ")
    sys.exit(1 if bad else 0)
