"""Compose the README hero banner from the firmware-rendered screens (PIL only)."""
import os
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = r"C:\Users\Alpha\Documents\GitHub\LPM-10A_Firmware"
IMG = os.path.join(ROOT, "docs", "img")
OVER = Image.open(os.path.join(IMG, "thai", "thai_overview.png")).convert("RGB")


def font(name, size):
    return ImageFont.truetype(f"C:/Windows/Fonts/{name}", size)


def tile(row, col):
    """Crop one 240x320 screen from the overview grid, trimmed to its dark frame."""
    x0 = 12 + col * 252
    y0 = 60 + row * 356
    im = OVER.crop((x0 - 4, y0 - 4, x0 + 244, y0 + 324))
    # trim: find the bounding box of non-background (background is (24,24,26)-ish)
    px = im.load()
    W, H = im.size
    def is_bg(p): return abs(p[0] - 24) < 6 and abs(p[1] - 24) < 6 and abs(p[2] - 26) < 6
    xs = [x for x in range(W) if any(not is_bg(px[x, y]) for y in range(0, H, 4))]
    ys = [y for y in range(H) if any(not is_bg(px[x, y]) for x in range(0, W, 4))]
    return im.crop((min(xs), min(ys), max(xs) + 1, max(ys) + 1))


screens = [tile(0, 1), tile(1, 1), tile(2, 0), tile(3, 5)]      # main menu, tone, length result, PoE 48.2 V
screens.append(Image.open(os.path.join(IMG, "scan-pn214-en.png")).convert("RGB").resize((240, 320)))

W, H = 1600, 640
im = Image.new("RGB", (W, H), (14, 16, 20))
d = ImageDraw.Draw(im)
# subtle diagonal gradient + glow
for y in range(H):
    for x in range(0, W, 4):
        t = (x / W) * 0.55 + (y / H) * 0.45
        c = (int(14 + 14 * t), int(16 + 18 * t), int(20 + 28 * t))
        d.rectangle((x, y, x + 3, y), fill=c)
glow = Image.new("RGB", (W, H), (0, 0, 0))
gd = ImageDraw.Draw(glow)
gd.ellipse((900, -150, 1750, 700), fill=(38, 52, 80))
glow = glow.filter(ImageFilter.GaussianBlur(120))
im = Image.blend(im, Image.eval(glow, lambda v: v), 0.0)
im.paste(Image.blend(im, glow, 0.9).crop((0, 0, W, H)), (0, 0), mask=glow.convert("L").point(lambda v: min(255, v * 3)))
d = ImageDraw.Draw(im)

# --- left: text block
x = 72
d.text((x, 88), "LPM-10A", font=font("bahnschrift.ttf", 92), fill=(255, 255, 255))
d.text((x, 186), "PN Custom Firmware", font=font("bahnschrift.ttf", 54), fill=(255, 196, 40))
d.text((x, 262), "Unofficial firmware for the FNIRSI LPM-10A cable tester and its tone probe", font=font("segoeui.ttf", 24), fill=(200, 205, 215))
d.text((x, 296), "เฟิร์มแวร์ปรับปรุงสำหรับเครื่องทดสอบสาย LPM-10A และโพรบ  —  ไทย / English", font=font("LeelawUI.ttf", 24), fill=(160, 170, 185))

# badges
def badge(x, y, text, fill, fg=(20, 20, 24)):
    f = font("segoeuib.ttf", 22)
    w = d.textlength(text, font=f)
    d.rounded_rectangle((x, y, x + w + 28, y + 40), radius=20, fill=fill)
    d.text((x + 14, y + 7), text, font=f, fill=fg)
    return x + w + 28 + 14
bx = badge(x, 350, "TX  PN 2.14", (255, 196, 40))
bx = badge(bx, 350, "RX  PN 1.23", (96, 200, 255))
bx = badge(bx, 350, "MIT", (120, 230, 120))
bx = badge(bx, 350, "tested on hardware", (70, 74, 84), fg=(230, 230, 235))

feats = [
    "Length with one decimal, Zero / NVP calibration, four-run average",
    "Live PoE voltage, link-timed Port FLASH, safe low-battery logic",
    "Thai interface on every screen, open-licence fonts",
    "Probe: one pitch per mode, rhythm = distance, automatic gain range, 40 ms updates",
]
fy = 424
for t in feats:
    d.ellipse((x, fy + 9, x + 10, fy + 19), fill=(255, 196, 40))
    d.text((x + 22, fy), t, font=font("segoeui.ttf", 22), fill=(225, 228, 235))
    fy += 36

# --- right: fanned screens with shadow
def shadowed(scr, scale):
    s = scr.resize((int(scr.width * scale), int(scr.height * scale)), Image.LANCZOS)
    sh = Image.new("RGBA", (s.width + 60, s.height + 60), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((30, 34, 30 + s.width, 34 + s.height), radius=10, fill=(0, 0, 0, 170))
    sh = sh.filter(ImageFilter.GaussianBlur(14))
    return s, sh

placements = [(2, 0.82, 950, 170), (3, 0.82, 1166, 130), (4, 0.82, 1382, 170)]
for idx, scale, px_, py_ in placements:
    s, sh = shadowed(screens[idx], scale)
    im.paste(sh, (px_ - 30, py_ - 34), sh)
    im.paste(s, (px_, py_))
    ImageDraw.Draw(im).rounded_rectangle((px_, py_, px_ + s.width - 1, py_ + s.height - 1), radius=8, outline=(70, 76, 90), width=2)

d = ImageDraw.Draw(im)
d.text((W - 24, H - 34), "screens rendered from the firmware's own draw code", font=font("segoeui.ttf", 16), fill=(120, 128, 140), anchor="ra")
im.save(os.path.join(IMG, "hero.png"), optimize=True)
print("hero", im.size)
