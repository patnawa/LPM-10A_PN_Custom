"""Thai text as 16x16 1-bit cells, one cell per grapheme cluster, proportional
advance -- the model the PN Thai firmware drawer will use.  Shaping (mark
placement) by HarfBuzz, rasterising by FreeType in monochrome hinted mode
(crisp 1-px stems, as a hand-made bitmap font would be).  Font: Sarabun (OFL)."""
import os
from PIL import Image, ImageDraw, ImageFont
import uharfbuzz as hb

HERE = os.path.dirname(os.path.abspath(__file__))
CELL = 16
COMB = set(chr(c) for c in list(range(0x0E31, 0x0E32)) + list(range(0x0E34, 0x0E3B)) + list(range(0x0E47, 0x0E4F)))
BELOW = set("ฺุู")


def clusters(text):
    """Split into grapheme clusters: a base char plus its combining marks."""
    out, cur = [], ""
    text = text.replace("ำ", "ํา")          # sara am = nikhahit (mark) + sara aa
    for ch in text:
        if ch in COMB and cur:
            cur += ch
        else:
            if cur:
                out.append(cur)
            cur = ch
    if cur:
        out.append(cur)
    return out


class ThaiFont:
    def __init__(self, path=None, size=13, baseline=13, below_lift=0, space=4, gap=1):
        self.path = path or os.path.join(HERE, "Sarabun-SemiBold.ttf")
        self.size, self.baseline, self.below_lift, self.space, self.gap = size, baseline, below_lift, space, gap
        self.pil = ImageFont.truetype(self.path, size)
        blob = hb.Blob.from_file_path(self.path)
        face = hb.Face(blob)
        self.hb = hb.Font(face)
        self.upem = face.upem
        self.hb.scale = (self.upem, self.upem)
        self.cache = {}

    def _shape(self, cluster):
        buf = hb.Buffer()
        buf.cluster_level = hb.BufferClusterLevel.MONOTONE_CHARACTERS
        buf.add_str(cluster)
        buf.guess_segment_properties()
        hb.shape(self.hb, buf)
        k = self.size / self.upem
        seen, out = set(), []
        for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
            ci = info.cluster
            if ci in seen:
                continue
            seen.add(ci)
            out.append((cluster[ci], pos.x_offset * k, pos.y_offset * k, pos.x_advance * k))
        return out

    def _render(self, cluster):
        """Monochrome render on a wide canvas, baseline at row BASE; -> (Image '1', BASE)."""
        W, H, BASE = 64, 48, 24
        im = Image.new("1", (W, H), 0)
        d = ImageDraw.Draw(im)
        d.fontmode = "1"
        pen = 0.0
        for ch, xo, yo, adv in self._shape(cluster):
            lift = self.below_lift if ch in BELOW else 0
            d.text((16 + round(pen + xo), BASE - round(yo) - lift), ch, font=self.pil, fill=1, anchor="ls")
            pen += adv
        return im, BASE

    def cell(self, cluster):
        """-> (rows: 16 lists of 16 ints, advance px, clipped (above, below, right) px counts or 0)."""
        if cluster in self.cache:
            return self.cache[cluster]
        if cluster == " ":
            r = ([[0] * CELL for _ in range(CELL)], self.space, 0)
            self.cache[cluster] = r
            return r
        im, BASE = self._render(cluster)
        bb = im.getbbox()
        if bb is None:
            r = ([[0] * CELL for _ in range(CELL)], self.space, 0)
            self.cache[cluster] = r
            return r
        x0 = bb[0]
        top = BASE - self.baseline                       # canvas row that becomes cell row 0
        px = im.load()
        rows = [[1 if (0 <= x0 + x < im.width and 0 <= top + y < im.height and px[x0 + x, top + y]) else 0
                 for x in range(CELL)] for y in range(CELL)]
        cols = [x for y in range(CELL) for x in range(CELL) if rows[y][x]]
        w = (max(cols) + 1) if cols else 1
        above = sum(1 for y in range(0, top) for x in range(x0, min(x0 + CELL, im.width)) if px[x, y])
        below = sum(1 for y in range(top + CELL, im.height) for x in range(x0, min(x0 + CELL, im.width)) if px[x, y])
        right = sum(1 for y in range(im.height) for x in range(x0 + CELL, im.width) if px[x, y])
        clipped = (above, below, right) if (above or below or right) else 0
        r = (rows, w + self.gap, clipped)
        self.cache[cluster] = r
        return r

    def width(self, text):
        return sum(self.cell(c)[1] for c in clusters(text)) - (self.gap if text else 0)

    def draw(self, put, x, y, text, fg, ascii_font=None, bg=None):
        """put(x, y, colour).  Thai cells are transparent (fg only); ASCII 0x20..0x7E
        goes through ascii_font (dict ch -> 16 rows of 8) opaque like the firmware."""
        for c in clusters(text):
            if len(c) == 1 and 0x20 <= ord(c) <= 0x7E and ascii_font is not None and c != " ":
                g = ascii_font[c]
                for yy in range(16):
                    for xx in range(8):
                        if g[yy][xx]:
                            put(x + xx, y + yy, fg)
                        elif bg is not None:
                            put(x + xx, y + yy, bg)
                x += 8
                continue
            rows, adv, _ = self.cell(c)
            for yy in range(CELL):
                for xx in range(CELL):
                    if rows[yy][xx]:
                        put(x + xx, y + yy, fg)
            x += adv
        return x


def sheet(font, words, path, scale=3, W=420):
    """Preview: each word on its own line; cell boxes shaded, clipped cells reddish."""
    rows_out = [(w, [(c, font.cell(c)) for c in clusters(w)]) for w in words]
    H = len(rows_out) * (CELL + 6)
    im = Image.new("RGB", (W * scale, H * scale), (26, 26, 25))
    px = im.load()
    clip_report = []
    for i, (w, cells) in enumerate(rows_out):
        x = 4
        y = i * (CELL + 6) + 3
        for c, (rows, adv, clipped) in cells:
            if clipped:
                clip_report.append((w, c, clipped))
            for yy in range(CELL):
                for xx in range(CELL):
                    col = (255, 255, 255) if rows[yy][xx] else ((70, 40, 40) if clipped else (44, 44, 46))
                    if xx >= adv - font.gap and not rows[yy][xx]:
                        col = (34, 34, 36)
                    for dy in range(scale):
                        for dx in range(scale):
                            X, Y = (x + xx) * scale + dx, (y + yy) * scale + dy
                            if X < W * scale:
                                px[X, Y] = col
            x += adv
    im.save(path)
    return clip_report


WORDS = ["ทดสอบสาย", "ไล่สาย", "กะพริบพอร์ต", "วัดความยาว", "ทดสอบเข้าหัว", "ความเร็ว", "ทดสอบ PoE", "ตั้งค่า",
         "สวิตช์", "ปลายสาย", "เริ่มทดสอบ", "ทดสอบใหม่", "ดิจิทัล", "กำลังทดสอบ", "โปรดดูไฟ LED",
         "จะกะพริบเมื่อเชื่อมต่อสำเร็จ", "หมดเวลาเชื่อมต่อ", "หน่วย", "ฟุต", "ซม.", "เมตร", "เกินช่วงการวัด",
         "ทดสอบผิดพลาด", "โปรดถอดสายออก", "กดปุ่มขวาค้างเพื่อปรับเทียบ", "ดูเพล็กซ์", "มาตรฐาน", "รูปแบบจ่ายไฟ",
         "โปรโตคอล", "ระดับกำลัง", "ไม่มาตรฐาน", "ภาษา", "ความสว่าง", "เสียง", "ปิดอัตโนมัติ", "เกี่ยวกับ", "ไทย",
         "5 นาที", "ซอฟต์แวร์:", "ฮาร์ดแวร์:", "รุ่น:", "คืนค่าโรงงาน", "คืนค่าโรงงานจะลบ", "การตั้งค่าทั้งหมด",
         "ใช่", "ไม่", "แบตเตอรี่ต่ำ โปรดชาร์จ", "กำลังจะปิดเครื่อง", "ปิด", "ปกติ", "ที่", "ปี", "ฟ้า", "ญี่ปุ่น"]

if __name__ == "__main__":
    import sys
    size = int(sys.argv[1]) if len(sys.argv) > 1 else 13
    base = int(sys.argv[2]) if len(sys.argv) > 2 else 13
    lift = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    f = ThaiFont(size=size, baseline=base, below_lift=lift)
    rep = sheet(f, WORDS, os.path.join(HERE, f"words_{size}_{base}_{lift}.png"))
    print("clipped:", rep)
    print("widths:", [(w, f.width(w)) for w in WORDS])
