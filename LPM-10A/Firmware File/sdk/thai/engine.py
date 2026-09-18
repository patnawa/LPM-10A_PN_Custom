"""Screen emulator for the LPM-10A TX firmware (stock or PN image).

Runs the real draw handlers under Unicorn with the FreeRTOS, LCD and PHY
primitives stubbed, replays GUI messages through the real dispatcher
(0x0800F488), and keeps a 240x320 RGB565 framebuffer.  In Thai mode the three
CJK text drawers are intercepted and the Thai string for the decoded Chinese
text is drawn with the proportional 16x16 cell font instead: the model the Thai
patch implements (centred on the same anchor when count != 0, else
left-aligned at the same x).

    python -m thai.mockup            # every screen, EN / ZH / TH, into thai/out/
"""
import os
import sys
import struct
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE
from unicorn.arm_const import *
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SDK = os.path.dirname(HERE)
sys.path.insert(0, SDK)
from thai.thaifont import ThaiFont, clusters      # noqa: E402
from thai.wording import DOTS, DOTS_X            # noqa: E402
from cjk_chars import CJK as _CJK                 # noqa: E402

CJK = list(_CJK)
CJK[0x69] = "于"                             # 关于 (About): index 0x69 is 于, not 干

FW_DIR = os.path.dirname(SDK)
DEFAULT_IMAGE = "reference"      # the PN build without thai-ui, built in memory (Chinese strings intact)
APP = 0x0800A000
MAGIC = 0x00100000
HEAP0 = 0x2000E800                               # bump allocator for pvPortMalloc (below the 0x2000F000 PN arena)

PUT_PIXEL = 0x08016BF0
DRAW_SHAPE = 0x08016D08        # (x0,y0,x1,y1,[sp]=colour) inclusive fill
FILL_SCREEN = 0x08016A44
GUI_MSG_SEND = 0x0800E428
GUI_DISPATCH = 0x0800F488
GUI_LOOP_END = 0x0800F71E
CJK_TEXT = 0x080176AC          # (x,y,bytes*,count)  count!=0 -> x -= 8*count
MIXED_TEXT = 0x080173EC        # (x,y,u16*,count)    count!=0 -> x -= 4*count
CJK_GLYPH = 0x08017550         # (x,y,idx,transparent)
GUI_BLIT = 0x080174E8          # (x,y,w,h,[sp]=size,[sp+4]=str)
ASCII_GLYPH = 0x080171D4       # (x,y,ch,size,[sp]=transparent)
TEXT_BOX = 0x0800EF6C          # (x,y,bg,fg,[sp]=mode,[sp+4]=str) -> GUI msg 0x38
FG, BG = 0x200001AC, 0x200001AE
SETTINGS = 0x20000C78
LANG = SETTINGS + 0xA5
RESET_HANDLER = 0x0800A198
MAIN = 0x0801BBAC

STUB_RET0 = {
    0x0801CAA0: "xQueueGenericSend", 0x0801CBB8: "xQueueReceive",
    0x0801C75C: "vTaskDelay", 0x0801C6B4: "vPortEnterCritical", 0x0801C6D8: "vPortExitCritical",
    0x0801C6F8: "vPortFree",
    0x08015D46: "GPIO_WriteBit", 0x08015AF2: "GPIO_ReadInputDataBit",
    0x080178F0: "mdio_read", 0x08017AFC: "mdio_write", 0x08018A9E: "phy_ext_write", 0x08018A80: "phy_ext_read",
    0x0801D178: "yt8531_set_pwr_down", 0x0801D2B4: "yt8531_set_1000M", 0x0801D3F4: "yt8531_set_100M",
    0x0801D534: "yt8531_set_autoneg", 0x08019CBC: "phy_csd_a", 0x08019CCA: "phy_csd_b", 0x08010F94: "rgb_led",
    0x080116E0: "led_colour", 0x0800F9C0: "autooff_timer_reset", 0x08012FBC: "LENG_MSG_SEND",
    0x080107B4: "adc_raw_read", 0x08010918: "charger_state",
    0x080130A8: "test_in_progress", 0x08017188: "lcd_set_cursor", 0x0801779C: "lcd_write_cmd",
    0x080116BC: "key_activity_notify", 0x08010FDA: "rgb_led_set",
    0x0800A3B8: "snprintf(log)", 0x0801C7B4: "task_notify", 0x0801A6B0: "speed_a", 0x0801A6EC: "speed_b",
    0x080159CC: "gpio_cfg",
}


_ref_cache = {}


def reference_image(without=("thai-ui",)):
    """The default PN build minus the given patches, as container bytes, built in memory
    from the stock image: the mock-up model needs the Chinese strings in place.  Patches
    that would put their code in the Thai patch's region (cable-back, length-blind-text)
    fall through to the cave, which grows past the end of the file as needed (the same
    Image.extend() a real build uses), so the reference draws exactly what the real build
    draws in English."""
    return bytes(reference_build(without).data)


def reference_build(without=("thai-ui",)):
    """The Image object behind reference_image(): patches record what they placed where
    (e.g. img.poe["live"], the PoE live-refresh RAM cell), which the scenarios need."""
    key = tuple(without)
    if key not in _ref_cache:
        from lpm10a.image import Image, require_stock
        import patches
        img = Image(require_stock(os.path.join(FW_DIR, "LPM-10A-TX_V2.0.7_260610.bin")))
        for p in patches.REGISTRY:
            if p.default and p.pid not in without:
                p(img)
        img.finalize()
        _ref_cache[key] = img
    return _ref_cache[key]


def load_payload(path):
    """path may be a container file, the container bytes, or "reference"."""
    if path == "reference":
        img = reference_image()
    elif isinstance(path, (bytes, bytearray)):
        img = bytes(path)
    else:
        img = open(path, "rb").read()
    off, ln, _ = struct.unpack_from("<III", img, 0x20)
    return img[off:off + ln]


_ram_cache = {}


def ram_init(payload):
    """The initialised RAM image: emulate Reset_Handler -> __main -> scatterload until main()."""
    key = payload[:64] + payload[-64:]
    if key in _ram_cache:
        return _ram_cache[key]
    uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
    uc.mem_map(0x08000000, 0x80000); uc.mem_map(0x20000000, 0x20000)
    uc.mem_map(0x40000000, 0x30000); uc.mem_map(0xE0000000, 0x10000)
    uc.mem_write(APP, payload)
    uc.mem_write(0x40021000, b"\xff" * 0x40)            # RCC->CR: HSE / PLL ready, so SetSysClock returns
    hit = []

    def hook(uc, addr, size, ud):
        if addr == MAIN:
            hit.append(1); uc.emu_stop()
    uc.hook_add(UC_HOOK_CODE, hook)
    uc.reg_write(UC_ARM_REG_SP, struct.unpack_from("<I", payload, 0)[0])
    uc.emu_start(RESET_HANDLER | 1, 0, count=5_000_000)
    assert hit, "did not reach main()"
    ram = bytes(uc.mem_read(0x20000000, 0x1100))
    _ram_cache[key] = ram
    return ram


def rgb(v):
    r, g, b = (v >> 11) & 31, (v >> 5) & 63, v & 31
    return ((r * 255 + 15) // 31, (g * 255 + 31) // 63, (b * 255 + 15) // 31)


_ascii_cache = {}


def ascii_font(payload):
    """8x16 glyph bitmaps of the image's ASCII font, via the real glyph drawer."""
    key = payload[:64] + payload[-64:]
    if key in _ascii_cache:
        return _ascii_cache[key]
    uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
    uc.mem_map(0x08000000, 0x80000); uc.mem_map(0x20000000, 0x10000); uc.mem_map(MAGIC, 0x1000)
    uc.mem_write(APP, payload)
    uc.mem_write(0x20000F54, struct.pack("<HH", 240, 320))
    uc.mem_write(FG, struct.pack("<HH", 0xFFFF, 0x0000))
    px = {}

    def hook(uc, addr, size, ud):
        if addr == PUT_PIXEL:
            px[(uc.reg_read(UC_ARM_REG_R0), uc.reg_read(UC_ARM_REG_R1))] = 1
            uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
    uc.hook_add(UC_HOOK_CODE, hook)
    font = {}
    for c in range(0x20, 0x7F):
        px.clear()
        sp = 0x2000E000
        uc.mem_write(sp, struct.pack("<I", 1))            # transparent: only ink pixels reach put_pixel
        uc.reg_write(UC_ARM_REG_SP, sp); uc.reg_write(UC_ARM_REG_LR, MAGIC | 1)
        uc.reg_write(UC_ARM_REG_R0, 0); uc.reg_write(UC_ARM_REG_R1, 0)
        uc.reg_write(UC_ARM_REG_R2, c); uc.reg_write(UC_ARM_REG_R3, 16)
        uc.emu_start(ASCII_GLYPH | 1, MAGIC, count=200000)
        font[chr(c)] = [[1 if (x, y) in px else 0 for x in range(8)] for y in range(16)]
    _ascii_cache[key] = font
    return font


class Scene:
    def __init__(self, image=DEFAULT_IMAGE, lang=2, thai=None, ascii_thai=None, font=None, state=2,
                 pct=100, mv=4000, charging=0):
        self.source = image                     # what this scene runs: "reference", a path, or bytes
        self.payload = load_payload(image)
        self.thai = thai                        # dict: decoded Chinese text -> Thai text (None = draw Chinese)
        self.ascii_thai = ascii_thai or {}      # dict: English-only string -> Thai (extra strings)
        self.font = font or ThaiFont()
        uc = self.uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
        uc.mem_map(0x08000000, 0x80000)
        uc.mem_map(0x20000000, 0x10000)
        uc.mem_map(0x40000000, 0x30000)
        uc.mem_map(0x60000000, 0x1000)
        uc.mem_map(0xE0000000, 0x10000)
        uc.mem_map(MAGIC, 0x1000)
        uc.mem_write(APP, self.payload)
        uc.mem_write(0x20000000, ram_init(self.payload))
        uc.mem_write(0x20000F54, struct.pack("<HH", 240, 320))
        uc.mem_write(FG, struct.pack("<HH", 0xFFFF, 0x0000))
        uc.mem_write(LANG, bytes([lang]))
        uc.mem_write(0x2000013C, bytes([state]))
        uc.mem_write(0x20000038, struct.pack("<I", 0x20001000))   # gui_queue non-NULL
        uc.mem_write(0x2000003D, bytes([0xFF]))                    # batt_shutdown_ctr idle
        uc.mem_write(0x2000003F, bytes([pct]))
        self.vals = dict(pct=pct, mv=mv, charging=charging, tick=0, tick_step=0)
        self.heap = HEAP0
        self.msgs = []
        self.fb = [[0] * 240 for _ in range(320)]
        self.recording = True
        self.log = []                            # (kind, text, x, y, fg, extra)
        self.missing = []                        # Chinese strings with no Thai mapping
        self.at = {}                             # addr -> callable(uc): scenario hooks (e.g. forced results)
        uc.hook_add(UC_HOOK_CODE, self.hook)

    # -- helpers -----------------------------------------------------------
    def ret(self, val=None):
        if val is not None:
            self.uc.reg_write(UC_ARM_REG_R0, val)
        self.uc.reg_write(UC_ARM_REG_PC, self.uc.reg_read(UC_ARM_REG_LR))

    def arg(self, n):
        uc = self.uc
        if n < 4:
            return uc.reg_read([UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3][n])
        sp = uc.reg_read(UC_ARM_REG_SP)
        return struct.unpack("<I", uc.mem_read(sp + 4 * (n - 4), 4))[0]

    def fg(self):
        return struct.unpack("<H", self.uc.mem_read(FG, 2))[0]

    def bg(self):
        return struct.unpack("<H", self.uc.mem_read(BG, 2))[0]

    def put(self, x, y, col):
        if 0 <= x < 240 and 0 <= y < 320:
            self.fb[y][x] = col

    def w8(self, addr, *vals):
        self.uc.mem_write(addr, bytes(vals))

    def w16(self, addr, *vals):
        self.uc.mem_write(addr, struct.pack("<%dH" % len(vals), *vals))

    def cstr(self, p):
        out = b""
        while True:
            b = self.uc.mem_read(p, 1)[0]
            if b == 0 or len(out) > 64:
                break
            out += bytes([b]); p += 1
        return out.decode("latin1")

    def decode_cjk(self, p):
        s = ""
        while True:
            b = self.uc.mem_read(p, 1)[0]
            if b >= 0xAB or len(s) > 40:
                break
            s += CJK[b]; p += 1
        return s

    def decode_mixed(self, p):
        s = ""
        for i in range(40):
            v = struct.unpack("<H", self.uc.mem_read(p + 2 * i, 2))[0]
            if v > 0xFF:
                if (v & 0xFF) >= 0xAB:
                    break
                s += CJK[v & 0xFF]
            elif 0x20 <= v <= 0x7E:
                s += chr(v)
            else:
                break
        return s

    # -- Thai substitution ---------------------------------------------------
    def draw_thai(self, x, y, src, centred, kind):
        th = self.thai.get(src)
        if th is None:
            self.missing.append((src, kind, x, y))
            return False
        if isinstance(th, dict):                     # {"text", "dx", "dy"}: a deliberate layout tweak
            x += th.get("dx", 0); y += th.get("dy", 0); th = th["text"]
        fg = self.fg()
        if kind == "glyph":                          # a single-glyph site: the whole word is one cell
            w = 16
            self.font.draw_word_cell(self.put, x, y, th, fg)
            self.log.append(("thai", th, x, y, fg, dict(src=src, w=w, centred=False)))
            return True
        w = self.font.width(th)
        if centred:
            x = x - w // 2
        self.font.draw(self.put, x, y, th, fg)          # every character is a cell, Latin included
        self.log.append(("thai", th, x, y, fg, dict(src=src, w=w, centred=centred)))
        return True

    # -- the hook -------------------------------------------------------------
    def hook(self, uc, addr, size, ud):
        if addr in self.at:
            if self.at[addr](uc):                   # True: the scenario handled the call itself
                return
        if addr in STUB_RET0:
            self.ret(0); return
        if addr == 0x0801C5B0:                      # xTaskGetTickCount
            self.vals["tick"] += self.vals["tick_step"]
            self.ret(self.vals["tick"]); return
        if addr == 0x0800E40C:                      # battery_shutdown_active
            self.ret(self.vals.get("shutdown", 0)); return
        if addr == 0x080107C0:                      # battery_level_percent
            self.ret(self.vals["pct"]); return
        if addr == 0x080108F8:                      # battery_millivolts
            self.ret(self.vals["mv"]); return
        if addr == 0x08012C64:                      # log_queue_ptr
            self.ret(0x2000F800); return
        if addr == 0x0801C388:                      # pvPortMalloc
            n = uc.reg_read(UC_ARM_REG_R0)
            p = self.heap; self.heap += (n + 7) & ~7
            self.ret(p); return
        if addr == PUT_PIXEL:
            self.put(self.arg(0), self.arg(1), self.fg())
            self.ret(); return
        if addr == DRAW_SHAPE:
            x0, y0, x1, y1, col = (self.arg(i) for i in range(5))
            for y in range(y0, y1 + 1):
                for x in range(x0, x1 + 1):
                    self.put(x, y, col)
            self.ret(); return
        if addr == FILL_SCREEN:
            col = self.arg(0)
            self.fb = [[col] * 240 for _ in range(320)]
            self.ret(); return
        if addr == GUI_MSG_SEND and self.recording:
            mid, payload, ln = self.arg(0), self.arg(1), self.arg(2)
            data = bytes(uc.mem_read(payload, ln)) if ln and payload else b""
            self.msgs.append((mid, data))
            self.ret(0); return
        if addr == GUI_BLIT:
            p = self.arg(5)
            s = self.cstr(p)
            x, y, w, size = self.arg(0), self.arg(1), self.arg(2), self.arg(4)
            self.log.append(("ascii", s, x, y, self.fg(), dict(w=w, size=size)))
            if self.thai is None or size != 16:
                return
            if s in DOTS:                                  # the "..." animation moves right of the Thai "Testing"
                if x == 68:
                    self.uc.reg_write(UC_ARM_REG_R0, DOTS_X)
                return
            spec = self.ascii_thai.get(s)
            if spec is None:
                return
            th = spec["text"]
            if spec.get("clear"):                          # wipe the 16-px line in the background colour
                bg = self.bg()
                for yy in range(y, y + 16):
                    for xx in range(12, 221):
                        self.put(xx, yy, bg)
            if spec["layout"] == "centre":
                x = x + w // 2 - self.font.width(th) // 2
            elif spec["layout"] == "x":
                x = spec["x"]
            self.font.draw(self.put, x, y, th, self.fg())
            self.log.append(("thai", th, x, y, self.fg(), dict(src=s, w=self.font.width(th), layout=spec["layout"])))
            self.ret(); return
        if addr == CJK_TEXT:
            x, y, p, n = (self.arg(i) for i in range(4))
            s = self.decode_cjk(p)
            self.log.append(("cjk", s, x, y, self.fg(), dict(count=n)))
            if self.thai is not None and self.draw_thai(x, y, s, n != 0, "cjk"):
                self.ret(); return
            return
        if addr == MIXED_TEXT:
            x, y, p, n = (self.arg(i) for i in range(4))
            s = self.decode_mixed(p)
            self.log.append(("mixed", s, x, y, self.fg(), dict(count=n)))
            if self.thai is not None and self.draw_thai(x, y, s, n != 0, "mixed"):
                self.ret(); return
            return
        if addr == CJK_GLYPH:
            x, y, idx = self.arg(0), self.arg(1), self.arg(2)
            lr = uc.reg_read(UC_ARM_REG_LR) & ~1
            if CJK_TEXT <= lr < CJK_TEXT + 0x40 or MIXED_TEXT <= lr < MIXED_TEXT + 0x70:
                return                              # inner call of a drawer we let run (Chinese mode)
            s = CJK[idx]
            self.log.append(("glyph", s, x, y, self.fg(), {}))
            if self.thai is not None and self.draw_thai(x, y, s, False, "glyph"):
                self.ret(); return
            return

    # -- running code -----------------------------------------------------------
    def call(self, fn, *args, stack=(), count=50_000_000):
        uc = self.uc
        sp = 0x2000E000 - 0x40
        for i, v in enumerate(stack):
            uc.mem_write(sp + 4 * i, struct.pack("<I", v))
        uc.reg_write(UC_ARM_REG_SP, sp)
        uc.reg_write(UC_ARM_REG_LR, MAGIC | 1)
        for i, v in enumerate(args):
            uc.reg_write([UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3][i], v)
        uc.emu_start(fn | 1, MAGIC, count=count)
        pc = uc.reg_read(UC_ARM_REG_PC)
        assert pc == MAGIC, f"call {fn:#x} stopped at {pc:#x}"
        return uc.reg_read(UC_ARM_REG_R0)

    def dispatch(self, mid, data=b""):
        """Run the real GUI-task dispatcher for one message."""
        uc = self.uc
        sp = 0x2000E000 - 0x18
        payload = 0
        if data:
            payload = self.heap; self.heap += (len(data) + 7) & ~7
            uc.mem_write(payload, data)
        uc.mem_write(sp + 8, bytes([mid, 0, 0, 0]))
        uc.mem_write(sp + 0xC, struct.pack("<I", payload))
        uc.reg_write(UC_ARM_REG_SP, sp)
        uc.reg_write(UC_ARM_REG_LR, MAGIC | 1)
        self.recording = True
        uc.emu_start(GUI_DISPATCH | 1, GUI_LOOP_END, count=50_000_000)
        pc = uc.reg_read(UC_ARM_REG_PC)
        assert pc == GUI_LOOP_END, f"dispatch {mid:#x} stopped at {pc:#x}"

    def post(self, mid, data=b""):
        self.msgs.append((mid, data))

    def drain(self, skip=()):
        kept = []
        while self.msgs:
            mid, data = self.msgs.pop(0)
            if mid in skip:
                kept.append((mid, data)); continue
            self.dispatch(mid, data)
        self.msgs = kept

    def set_state(self, st):
        """APP_HOME_set_sysState: posts the function-screen frame (msg 0x36) for states 4..11."""
        self.call(0x0800F77C, st)
        self.drain()

    def text_box(self, x, y, bg, fg, mode, s):
        """gui_draw_text_box with a string placed in RAM (modes 0x10 left, 0x20 centred ASCII)."""
        p = self.heap; self.heap += (len(s) + 8) & ~7
        self.uc.mem_write(p, s.encode("latin1") + b"\0")
        self.call(TEXT_BOX, x, y, bg, fg, stack=(mode, p))
        self.drain()

    # -- output ---------------------------------------------------------------------
    def image(self, scale=1):
        im = Image.new("RGB", (240, 320))
        px = im.load()
        for y in range(320):
            row = self.fb[y]
            for x in range(240):
                px[x, y] = rgb(row[x])
        if scale != 1:
            im = im.resize((240 * scale, 320 * scale), Image.NEAREST)
        return im
