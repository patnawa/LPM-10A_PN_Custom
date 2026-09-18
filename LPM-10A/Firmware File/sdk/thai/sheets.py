"""Contact sheets of the mock-ups for docs/img/thai/ (run thai.mockup first, at 12 and 13 px)."""
import os
import sys
from PIL import Image, ImageDraw, ImageFont
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from thai.mockup import SCREENS            # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))   # sdk/thai -> sdk -> Firmware File -> LPM-10A -> repo
DOCS = os.path.join(REPO, "docs", "img", "thai")
os.makedirs(DOCS, exist_ok=True)
BG = (26, 26, 25); INK = (255, 255, 255); INK2 = (195, 194, 183); MUTED = (120, 120, 116); GOLD = (255, 190, 60)
SB = os.path.join(HERE, "Sarabun-SemiBold.ttf")
SR = os.path.join(HERE, "Sarabun-Regular.ttf")


def f(size, bold=False):
    return ImageFont.truetype(SB if bold else SR, size)


THAI_TITLE = {
    "language_picker": "เลือกภาษา (เปิดเครื่องครั้งแรก)", "home_1": "หน้าหลัก หน้า 1", "home_2": "หน้าหลัก หน้า 2",
    "cable_test_mode": "ทดสอบสาย: เลือกโหมด", "cable_test_armed": "ทดสอบสาย: พร้อม",
    "cable_test_result_switch": "ทดสอบสาย: ผล (สวิตช์)", "cable_test_result_farend": "ทดสอบสาย: ผล (ปลายสาย)",
    "scan": "ไล่สาย", "flash_testing": "กะพริบพอร์ต: กำลังทดสอบ", "flash_note": "กะพริบพอร์ต: ลิงก์ขึ้น",
    "length_idle": "วัดความยาว: พร้อม", "length_testing": "วัดความยาว: กำลังทดสอบ", "length_result": "วัดความยาว: ผล",
    "length_out_of_range": "วัดความยาว: เกินช่วง", "length_timeout": "วัดความยาว: หมดเวลา",
    "qc_test": "ทดสอบเข้าหัว", "qc_test_uncalibrated": "ทดสอบเข้าหัว: ยังไม่ปรับเทียบ",
    "speed_idle": "ความเร็ว: พร้อม", "speed_testing": "ความเร็ว: กำลังทดสอบ", "speed_result": "ความเร็ว: ผล",
    "speed_timeout": "ความเร็ว: หมดเวลาเชื่อมต่อ", "poe": "ทดสอบ PoE", "settings": "ตั้งค่า", "about": "เกี่ยวกับ",
    "factory_reset": "คืนค่าโรงงาน", "lowbatt": "แบตเตอรี่ต่ำ",
}


def load(out, sid, tag):
    return Image.open(os.path.join(HERE, out, f"{sid}_{tag}.png")).resize((240, 320), Image.NEAREST)


def sheet(ids, path, out="out", cols=("en", "zh", "th"), heads=("English", "Chinese (stock)", "Thai (PN 2.0)")):
    W = 250 + len(cols) * 256 + 24
    rowh = 350
    H = 70 + rowh * len(ids)
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    for i, h in enumerate(heads):
        d.text((250 + i * 256 + 120, 24), h, fill=GOLD if "Thai" in h else INK2, font=f(20, True), anchor="mm")
    for r, sid in enumerate(ids):
        title = next(t for s, t, _, _ in SCREENS if s == sid)
        y = 70 + r * rowh
        d.text((16, y + 6), title, fill=INK, font=f(19, True))
        d.text((16, y + 34), THAI_TITLE.get(sid, ""), fill=INK2, font=f(18))
        d.text((16, y + 62), sid, fill=MUTED, font=f(14))
        for c, tag in enumerate(cols):
            im.paste(load(out, sid, tag), (250 + c * 256, y))
    im.save(path)
    return im.size


def overview(path, out="out", cols=6):
    ids = [s for s, _, _, _ in SCREENS]
    rows = (len(ids) + cols - 1) // cols
    W = cols * 252 + 12
    H = 60 + rows * 356
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    d.text((16, 16), "LPM-10A PN 2.0: the Thai interface, every screen (rendered from the firmware draw code)", fill=INK, font=f(22, True))
    for i, sid in enumerate(ids):
        r, c = divmod(i, cols)
        x, y = 12 + c * 252, 60 + r * 356
        im.paste(load(out, sid, "th"), (x, y))
        d.text((x + 120, y + 334), THAI_TITLE.get(sid, sid), fill=INK2, font=f(16), anchor="mm")
    im.save(path)
    return im.size


def sizes(path, ids=("home_1", "length_result", "settings", "qc_test_uncalibrated")):
    W = len(ids) * 256 + 12
    H = 60 + 2 * 356
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    d.text((16, 16), "Thai cell font: 12 px (top row, no clipping) vs 13 px (bottom row, larger; ุ ู lose one pixel row)", fill=INK, font=f(20, True))
    for r, out in enumerate(("out12", "out13")):
        for c, sid in enumerate(ids):
            x, y = 12 + c * 256, 60 + r * 356
            im.paste(load(out, sid, "th"), (x, y))
            d.text((x + 120, y + 334), f"{'12' if r == 0 else '13'} px: {THAI_TITLE.get(sid, sid)}", fill=INK2, font=f(16), anchor="mm")
    im.save(path)
    return im.size


if __name__ == "__main__":
    ids = [s for s, _, _, _ in SCREENS]
    groups = [ids[0:7], ids[7:14], ids[14:21], ids[21:]]
    for n, g in enumerate(groups, 1):
        print(sheet(g, os.path.join(DOCS, f"thai_screens_{n}.png")))
    print(overview(os.path.join(DOCS, "thai_overview.png")))
    if os.path.isdir(os.path.join(HERE, "out12")) and os.path.isdir(os.path.join(HERE, "out13")):
        print(sizes(os.path.join(DOCS, "thai_font_size.png")))
