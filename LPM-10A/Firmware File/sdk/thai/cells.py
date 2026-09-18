"""The Thai cell table for the firmware: every grapheme cluster the UI needs,
rendered by ThaiFont into the 16x16 column-major format of the stock CJK
table, plus the per-cell advance widths and the string encoders.

    python -m thai.cells        -> fonts_out/thai16.bin, thai16_widths.bin, thai16.png

Cell 0 is the blank (space) cell.  Index bytes >= 0xAB terminate a string
exactly as in stock; 0xAC is the redirect marker used by the Thai drawers
(see patches.py, thai-ui).
"""
import os
import sys
import struct
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from thai.thaifont import ThaiFont, clusters, CELL      # noqa: E402

SLOTS = 171                     # the stock table has room for 171 glyphs
REDIRECT = 0xAC                 # index byte that means "the real string is elsewhere"
TERM = 0xFF
WORD_CELLS = ["ใช่", "ไม่"]      # whole words squeezed into one cell for the two single-glyph sites (YES / NO)

FONT = ThaiFont(size=13, baseline=14, below_lift=1)     # the size chosen for PN 2.0


def cluster_set(texts):
    """All clusters used by the given strings (Latin letters and digits inside Thai
    strings are cells too, in the same face), cell 0 = space."""
    seen = {" "}
    order = [" "]
    for t in texts:
        for c in clusters(t):
            if c in seen:
                continue
            seen.add(c)
            order.append(c)
    return order


def pack_cell(rows):
    cols = [0] * 16
    for c in range(16):
        for r in range(16):
            if rows[r][c]:
                cols[c] |= 1 << r
    return struct.pack("<16H", *cols)


class Table:
    def __init__(self, texts, font=FONT, word_cells=WORD_CELLS):
        self.font = font
        self.order = cluster_set(texts) + list(word_cells)
        if len(self.order) > SLOTS:
            raise ValueError(f"{len(self.order)} cells needed, {SLOTS} slots")
        self.index = {c: i for i, c in enumerate(self.order)}
        self.cells = []
        self.widths = []
        for c in self.order:
            rows, adv, clipped = font.cell(c)
            if c in word_cells and clipped and clipped[2]:
                raise ValueError(f"word cell {c!r} is wider than 16 px")
            self.cells.append(rows)
            self.widths.append(adv)

    @classmethod
    def shipped(cls, fonts_out):
        """The table as shipped in fonts_out/ (no font tooling needed): order, widths, cell bitmaps."""
        import json
        meta = json.load(open(os.path.join(fonts_out, "thai16.json"), encoding="utf-8"))
        blob = open(os.path.join(fonts_out, "thai16.bin"), "rb").read()
        t = cls.__new__(cls)
        t.font = None
        t.order = meta["order"]
        t.index = {c: i for i, c in enumerate(t.order)}
        t.widths = meta["widths"]
        t.cells = [[[(struct.unpack_from("<16H", blob, i * 32)[c] >> r) & 1 for c in range(16)] for r in range(16)]
                   for i in range(len(t.order))]
        t.meta = meta
        return t

    def width(self, text):
        adv = [self.widths[self.index[c]] for c in clusters(text)]
        return sum(adv) - (1 if adv else 0)

    def draw(self, put, x, y, text, fg):
        """The firmware's rule: each cell transparent at x, advance by its width."""
        for c in clusters(text):
            i = self.index[c]
            rows = self.cells[i]
            for yy in range(16):
                for xx in range(16):
                    if rows[yy][xx]:
                        put(x + xx, y + yy, fg)
            x += self.widths[i]
        return x

    def draw_word_cell(self, put, x, y, word, fg):
        rows = self.cells[self.index[word]]
        for yy in range(16):
            for xx in range(16):
                if rows[yy][xx]:
                    put(x + xx, y + yy, fg)

    def blob(self):
        """171 x 32 bytes: the Thai cells, then blank cells."""
        out = b"".join(pack_cell(r) for r in self.cells)
        return out + b"\0" * (SLOTS * 32 - len(out))

    def width_blob(self):
        w = bytes(self.widths)
        return w + b"\0" * (SLOTS - len(w))

    def encode_cjk(self, text):
        """Index bytes + 0xFF."""
        return bytes(self.index[c] for c in clusters(text)) + bytes([TERM])

    def encode_mixed(self, text):
        """u16 units, 0x0100 | cell index each, 0x0000 end (the stock ASCII unit path is
        never used by a Thai string: Latin characters are cells in the same face)."""
        units = [0x0100 | self.index[c] for c in clusters(text)] + [0]
        return struct.pack("<%dH" % len(units), *units)

    def preview(self, path, scale=3, per_row=16):
        from PIL import Image
        n = len(self.cells)
        rows = (n + per_row - 1) // per_row
        im = Image.new("RGB", (per_row * 17 * scale, rows * 18 * scale), (26, 26, 25))
        px = im.load()
        for i, g in enumerate(self.cells):
            cx, cy = (i % per_row) * 17, (i // per_row) * 18
            adv = self.widths[i]
            for y in range(16):
                for x in range(16):
                    col = (255, 255, 255) if g[y][x] else ((44, 44, 46) if x < adv - 1 else (34, 34, 36))
                    for dy in range(scale):
                        for dx in range(scale):
                            px[(cx + x) * scale + dx, (cy + y) * scale + dy] = col
        im.save(path)


def ui_texts():
    """Every Thai string of the UI (from the mock-up wording table)."""
    from thai.wording import TH, ASCII_TH
    out = []
    for v in list(TH.values()) + list(ASCII_TH.values()):
        out.append(v["text"] if isinstance(v, dict) else v)
    return out


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    t = Table(ui_texts())
    out = os.path.join(os.path.dirname(HERE), "fonts_out")
    open(os.path.join(out, "thai16.bin"), "wb").write(t.blob())
    open(os.path.join(out, "thai16_widths.bin"), "wb").write(t.width_blob())
    import json
    json.dump(dict(font=os.path.basename(FONT.path), size=FONT.size, baseline=FONT.baseline, below_lift=FONT.below_lift,
                   order=t.order, widths=t.widths),
              open(os.path.join(out, "thai16.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    t.preview(os.path.join(out, "thai16.png"))
    print(f"{len(t.order)} cells (of {SLOTS}); widths {min(t.widths)}..{max(t.widths)}")
    print("".join(t.order))
