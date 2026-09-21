"""Render the README's RX figures with PIL (no matplotlib on this machine)."""
import os
from PIL import Image, ImageDraw, ImageFont

ROOT = r"C:\Users\Alpha\Documents\GitHub\LPM-10A_Firmware"
IMG = os.path.join(ROOT, "docs", "img")
F = "C:/Windows/Fonts/arial.ttf"
FB = "C:/Windows/Fonts/arialbd.ttf"
BG, FG, DIM, ACC, ACC2, RED, GRID = (24, 24, 26), (235, 235, 235), (160, 160, 165), (255, 196, 40), (96, 200, 255), (255, 96, 96), (60, 60, 64)


def font(size, bold=False):
    return ImageFont.truetype(FB if bold else F, size)


# ---------------------------------------------------------------- 1. container diagram
W, H = 1400, 520
im = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(im)
d.text((24, 18), "RX firmware update: what the bootloader accepts", font=font(30, True), fill=FG)

# raw image (rejected)
x0, y0 = 40, 90
d.text((x0, y0), "FNIRSI's RX file / any raw image", font=font(22, True), fill=FG)
d.rectangle((x0, y0 + 36, x0 + 560, y0 + 96), outline=DIM, width=2)
d.text((x0 + 12, y0 + 52), "18 16 00 20  5d 69 00 08  ...   application image (26 152 B)", font=font(19), fill=DIM)
d.text((x0, y0 + 110), "copied to BOOTLOADER  ->  status file UNKOWN.TXT, nothing programmed", font=font(20), fill=RED)

# container (accepted)
x1, y1 = 40, 250
d.text((x1, y1), "*-update.bin container (what build.py writes)", font=font(22, True), fill=FG)
top = y1 + 36
d.rectangle((x1, top, x1 + 260, top + 60), fill=(60, 50, 20), outline=ACC, width=2)
d.text((x1 + 10, top + 8), "0x0000  name[32]", font=font(18, True), fill=ACC)
d.text((x1 + 10, top + 32), '"APP_LPM-10RX_V3.0.0_260416.bin"', font=font(15), fill=FG)
d.rectangle((x1 + 260, top, x1 + 520, top + 60), fill=(60, 50, 20), outline=ACC, width=2)
d.text((x1 + 270, top + 8), "0x0020  off 0x1000", font=font(18, True), fill=ACC)
d.text((x1 + 270, top + 32), "0x0024 len   0x0028 end = off+len-1", font=font(15), fill=FG)
d.rectangle((x1 + 520, top, x1 + 700, top + 60), fill=(40, 40, 42), outline=DIM, width=2)
d.text((x1 + 530, top + 20), "zeros to 0x1000", font=font(17), fill=DIM)
d.rectangle((x1 + 700, top, x1 + 1180, top + 60), fill=(20, 50, 70), outline=ACC2, width=2)
d.text((x1 + 712, top + 8), "0x1000  application image", font=font(18, True), fill=ACC2)
d.text((x1 + 712, top + 32), "loaded at 0x08006800, then zero padding to a 4 KB multiple", font=font(15), fill=FG)
d.rectangle((x1 + 1180, top, x1 + 1320, top + 60), fill=(40, 40, 42), outline=DIM, width=2)
d.text((x1 + 1192, top + 20), "pad (32 KB)", font=font(17), fill=DIM)
d.text((x1, top + 76), "copied with Explorer  ->  programmed in ~1 s, probe restarts; the drive then shows PN1.xx.TXT", font=font(20), fill=(120, 230, 120))
d.text((x1, top + 106), "slow / sector-by-sector writers  ->  APPRUN.TXT (aborted)", font=font(20), fill=RED)
d.text((24, H - 40), "Established 2026-09-21 by reading the bootloader's SRAM over SWD while copying; same header layout as FNIRSI's TX file. Details: docs/RX-UPDATE-GUIDE.md", font=font(16), fill=DIM)
im.save(os.path.join(IMG, "rx-update-container.png"))

# ---------------------------------------------------------------- 2. measurements
W, H = 1400, 620
im = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(im)
d.text((24, 16), "RX probe, measured live over SWD (2026-09-21): knob gain steps and the strength rhythm", font=font(26, True), fill=FG)

# left: gain steps bar chart (p-p per code, Digital, one fixed position)
lx, ly, lw, lh = 60, 90, 620, 400
d.text((lx, ly - 30), "front-end gain per knob code (ADC p-p at one fixed position)", font=font(19, True), fill=FG)
codes = list(range(8))
stock = [95, 230, 780, 90, 1920, 1940, 2040, 2400]
fixed = [95, 230, 780, 780, 1920, 1940, 2040, 2400]
maxv = 2600
bw = 60
for i, c in enumerate(codes):
    x = lx + 20 + i * 74
    h_stock = int(stock[i] / maxv * (lh - 60))
    h_fixed = int(fixed[i] / maxv * (lh - 60))
    base = ly + lh - 40
    d.rectangle((x, base - h_fixed, x + bw, base), fill=(40, 90, 120), outline=ACC2)
    d.rectangle((x, base - h_stock, x + bw, base), fill=(200, 160, 60) if c != 3 else RED, outline=ACC)
    d.text((x + 22, base + 6), str(c), font=font(17, True), fill=FG)
    d.text((x + 4, base - h_fixed - 22), str(fixed[i]), font=font(14), fill=FG)
d.text((lx + 20, ly + lh - 8), "knob code 0..7 (0-14 % .. 99-100 % of travel)", font=font(16), fill=DIM)
d.rectangle((lx + 20, ly + 4, lx + 36, ly + 20), fill=(200, 160, 60))
d.text((lx + 44, ly + 2), "stock firmware", font=font(15), fill=FG)
d.rectangle((lx + 20, ly + 28, lx + 36, ly + 44), fill=RED)
d.text((lx + 44, ly + 26), "code 3 dropped to the lowest gain", font=font(15), fill=FG)
d.rectangle((lx + 20, ly + 52, lx + 36, ly + 68), fill=(40, 90, 120))
d.text((lx + 44, ly + 50), "PN 1.17+: level 3 uses level 2", font=font(15), fill=FG)
d.text((lx, ly + lh + 20), "three effective steps: ~90 / ~230 / ~780 / ~1900-2400 (saturates); PN 1.22 steps down by itself at >= 1900 p-p", font=font(15), fill=DIM)

# right: rhythm curve (quiet interval vs normalised strength)
rx, ry, rw, rh = 760, 90, 600, 400
d.text((rx, ry - 30), "quiet interval between 30 ms pulses vs normalised strength", font=font(19, True), fill=FG)
scores = [0, 800, 2400, 7200, 24000, 40000]
gaps = [110, 95, 85, 70, 45, 20]
xmax, ymax = 44000, 120
def px(s): return rx + 40 + int(s / xmax * (rw - 80))
def py(g): return ry + rh - 40 - int(g / ymax * (rh - 80))
for g in (20, 45, 70, 95, 110):
    d.line((rx + 40, py(g), rx + rw - 40, py(g)), fill=GRID)
    d.text((rx + 2, py(g) - 8), f"{g} ms", font=font(13), fill=DIM)
pts = [(px(s), py(g)) for s, g in zip(scores, gaps)]
d.line(pts, fill=ACC, width=4)
for p in pts:
    d.ellipse((p[0] - 5, p[1] - 5, p[0] + 5, p[1] + 5), fill=ACC)
for s, lab in ((800, "800"), (7200, "7 200"), (24000, "24 000")):
    d.text((px(s) - 10, ry + rh - 34), lab, font=font(13), fill=DIM)
d.text((px(40000) - 150, ry + rh - 34), "40 000 = touching the cable", font=font(13), fill=DIM)
d.text((rx + 40, ry + rh - 8), "strength score x knob-gain multiplier (PN 1.15) -> the knob no longer changes the rhythm", font=font(15), fill=DIM)
d.text((rx + 60, ry + 8), "weak: ~7 pulses/s", font=font(15), fill=FG)
d.text((rx + rw - 330, ry + rh - 170), "strongest: ~20 pulses/s", font=font(15), fill=FG)
d.text((24, H - 36), "Sources: docs/RX-SENSITIVITY-2026-09-21.md (captures with docs/experiments/rx_sens_capture.py); one hardware unit", font=font(15), dill=None) if False else d.text((24, H - 36), "Sources: docs/RX-SENSITIVITY-2026-09-21.md (captures with docs/experiments/rx_sens_capture.py); one hardware unit", font=font(15), fill=DIM)
im.save(os.path.join(IMG, "rx-measurements.png"))

# ---------------------------------------------------------------- 3. board photo, resized
src = r"C:\Users\Alpha\Desktop\RX\99035_0.jpg"
ph = Image.open(src)
ph = ph.crop((300, 60, 860, 1000)).resize((420, 705))
ph.save(os.path.join(IMG, "rx-board.jpg"), quality=82)
print("ok", os.listdir(IMG))
