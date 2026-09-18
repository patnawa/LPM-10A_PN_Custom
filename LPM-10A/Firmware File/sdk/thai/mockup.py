"""Render every LPM-10A screen three ways: English (PN 1.3), Chinese (stock
strings, PN 1.3 image) and the proposed Thai UI, from the real draw code.

    python -m thai.mockup [screen ids]       THAI_PX=13 for the 13 px font
"""
import os
import sys
import json
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from thai.engine import Scene, ThaiFont      # noqa: E402

# Chinese (as decoded from the firmware) -> Thai.  Alignment follows the stock call:
# strings the firmware centres stay centred on the same point, left-aligned ones keep their x.
TH = {
    # home tiles / screen titles
    "网线对接": "ทดสอบสาย", "寻线": "ไล่สาย", "端口闪烁": "กะพริบพอร์ต", "长度测试": "วัดความยาว",
    "压接测试": "ทดสอบเข้าหัว", "网线速率": "ความเร็ว", "POE测试": "ทดสอบ PoE", "设置": "ตั้งค่า",
    # language picker / settings
    "语言": "ภาษา", "中文": "ไทย", "亮度": "ความสว่าง", "音量": "เสียง", "自动关机": "ปิดอัตโนมัติ", "关于": "เกี่ยวกับ",
    "5分钟": "5 นาที", "10分钟": "10 นาที", "15分钟": "15 นาที",
    # about / factory reset
    "软件号:": {"text": "ซอฟต์แวร์:", "dx": -14}, "硬件号:": {"text": "ฮาร์ดแวร์:", "dx": -14},
    "型  号:": {"text": "รุ่น:", "dx": -14}, "恢复出厂设置": "คืนค่าโรงงาน",
    "恢复出厂设置会重": "คืนค่าโรงงานจะลบ", "置之前所有的修改": "การตั้งค่าทั้งหมด", "是": "ใช่", "否": "ไม่",
    # cable test
    "交换机": "สวิตช์", "远 端": "ปลายสาย", "开始测试": "เริ่มทดสอบ", "重新测试": "ทดสอบใหม่",
    # scan
    "抗干扰寻线": "ดิจิทัล", "普通寻线": "825 Hz",
    # flash / speed / length
    "测试中": "กำลังทดสอบ", "请观察指示灯": "โปรดดูไฟ LED", "连接成功后开始闪烁": "จะกะพริบเมื่อเชื่อมต่อสำเร็จ",
    "测试超时": "หมดเวลาเชื่อมต่อ", "单位": "หน่วย",
    "英寸": "เมตร", "厘米": "ซม.", "米": "ฟุต",          # PN slots are m / cm / ft (stock Chinese still says inch/cm/m)
    "超出测量范围": "เกินช่วงการวัด", "速率": "ความเร็ว", "双工模式": "ดูเพล็กซ์",
    "全双工": "ฟูลดูเพล็กซ์", "半双工": "ฮาล์ฟดูเพล็กซ์",
    # qc test
    "测试出错": "ทดสอบผิดพลาด", "请移除网线后": "โปรดถอดสายออก", "长按右键校准": "กดปุ่มขวาค้างเพื่อปรับเทียบ",
    # poe
    "交换机标准": "ประเภท", "供电方式": "รูปแบบจ่ายไฟ", "标准协议": "โปรโตคอล", "功率等级": "ระดับกำลัง",
    "标准": "มาตรฐาน", "非标准": "ไม่มาตรฐาน", "末端跨接": "End-span", "中间跨接": "Mid-span",
    # low battery
    "电量低请及时充电": "แบตเตอรี่ต่ำ โปรดชาร์จ", "即将关机": "กำลังจะปิดเครื่อง",
}
# English-only strings in stock (no Chinese variant) that the Thai build would also translate
ASCII_TH = {
    "Test timeout!!": "หมดเวลาทดสอบ!!", "Result error!!": "ผลลัพธ์ผิดพลาด!!", "Error!!": "ผิดพลาด!!",
    "Full-duplex": "ฟูลดูเพล็กซ์", "Half-duplex": "ฮาล์ฟดูเพล็กซ์", "OFF": "ปิด",
}

SIZE = int(os.environ.get("THAI_PX", "12"))
FONT = ThaiFont(size=12, baseline=13, below_lift=1) if SIZE == 12 else ThaiFont(size=13, baseline=14, below_lift=1)
OUT = os.path.join(HERE, "out" if SIZE == 12 else f"out{SIZE}")
os.makedirs(OUT, exist_ok=True)


def scene(lang, thai, **kw):
    return Scene(lang=lang, thai=(TH if thai else None), ascii_thai=(ASCII_TH if thai else None), font=FONT, **kw)


# ---------------------------------------------------------------- scenarios
def sc_language_picker(s):
    s.w8(0x2000013C, 3)
    s.call(0x08010B68); s.drain()
    s.call(0x08010D34); s.drain()


def sc_home(s, sel):
    s.w8(0x2000013D, sel)
    s.call(0x08015BC4); s.call(0x0800F0C0); s.call(0x0801932C); s.call(0x0800F100, 0); s.call(0x0800E6B0)
    s.drain()


def sc_cable_test_a(s, mode=0):
    s.w8(0x20000010, mode)
    s.set_state(4)
    s.call(0x0800C300); s.drain()


def sc_cable_test_b(s, retry=0):
    s.w8(0x20000010, 0)
    s.w8(0x20000012, retry)
    s.set_state(4)
    s.post(0x10); s.post(0x12); s.drain()


def sc_cable_result_switch(s):
    s.w8(0x20000010, 0); s.w8(0x20000012, 1)
    s.set_state(4)
    s.post(0x10); s.drain()
    s.post(0x11); s.drain()


def sc_cable_result_farend(s):
    s.w8(0x20000010, 1); s.w8(0x20000012, 1)
    s.set_state(4)
    s.post(0x10); s.drain()
    s.post(0x11); s.drain()


def sc_scan(s, mode=1, enable=1, phase=1):
    s.w8(0x200000D0, enable, mode, 0, 0, phase)
    s.set_state(5)
    s.post(0x09); s.post(0x0A); s.post(0x0B); s.drain()


def sc_flash_testing(s):
    s.set_state(6)
    s.w8(0x200002B4 + 1, 0)
    s.call(0x0800D47C)
    s.drain(skip=(0x1F,))


def sc_flash_note(s):
    sc_flash_testing(s)
    s.drain()
    s.call(0x0800EF40, 91, 116, 18, 0); s.drain()


def sc_length_idle(s, unit=0):
    s.w8(0x200002C0, unit)
    s.w8(0x20000C78 + 0xA6, 68); s.w8(0x20000C78 + 0xC5, 5)
    s.set_state(7)
    s.post(0x19); s.drain()


DOTS_X = 88          # Thai build: the "..." animation moves right of the wider Thai "Testing"


def sc_length_testing(s):
    sc_length_idle(s)
    s.call(0x08019C38); s.drain()
    s.text_box(DOTS_X if s.thai else 68, 175, 0x2105, 0xFFFF, 0x10, ".. ")


def sc_length_result(s, cm=(1399, 1399, 1399, 1399)):
    sc_length_idle(s)
    s.w16(0x200002B8, *cm)
    s.w8(0x200002B4, 2)
    s.post(0x1A); s.drain()


def sc_length_timeout(s):
    sc_length_testing(s)
    if s.thai:                      # Thai build: clear the line and draw the message from its left edge
        s.post(0x1B); s.drain()
        s.font.draw(s.put, 12, 175, ASCII_TH["Test timeout!!"], 0xFFFF, ascii_font=s.afont, bg=0x2105)
    else:
        s.text_box(68, 175, 0x2105, 0xFFFF, 0x10, "Test timeout!!")


def sc_qc_test(s):
    s.set_state(8)
    s.post(0x0C); s.drain()


def sc_qc_uncal(s):
    sc_qc_test(s)
    s.post(0x0E); s.drain()


def sc_speed_idle(s, retry=0):
    s.w8(0x20000075, retry); s.w8(0x200002B4, 0)
    s.set_state(9)
    s.post(0x1D); s.drain()


def sc_speed_testing(s):
    sc_speed_idle(s)
    s.call(0x0801B06C); s.drain()
    s.text_box(DOTS_X if s.thai else 68, 67, 0x2105, 0xFFFF, 0x10, ".. ")


def sc_speed_result(s, reg11=0x8000 | 0x2000):
    sc_speed_idle(s, retry=1)
    s.w16(0x200002B6, reg11); s.w8(0x200002B4, 3)
    s.call(0x0801A9A8); s.drain()


def sc_speed_timeout(s):
    sc_speed_testing(s)
    s.vals["tick_step"] = 5000
    s.w8(0x200002B4 + 1, 0)
    s.call(0x0800D47C); s.drain()


def sc_poe(s, values=True):
    s.set_state(10)
    s.post(0x13); s.drain()
    if values:
        s.w8(0x20000C5D, 2); s.w8(0x20000C60, 1); s.w8(0x20000C5F, 2)
        s.post(0x14); s.drain()


def sc_settings(s, item=1):
    s.w8(0x2000013E, item); s.w8(0x2000013F, 0)
    s.set_state(11)
    s.post(0x32); s.drain()


def sc_about(s):
    s.w8(0x2000013F, 1)
    s.set_state(11)
    s.post(0x34); s.drain()


def sc_factory_reset(s, flag=2):
    sc_about(s)
    s.w8(0x2000013F, flag)
    s.post(0x35); s.drain()


def sc_lowbatt(s):
    sc_home(s, 4)
    s.vals["mv"] = 3100; s.vals["shutdown"] = 1
    s.call(0x0800E834); s.drain()
    s.w8(0x2000003D, 25)
    s.call(0x0800DCF0); s.drain()


SCREENS = [
    ("language_picker", "Language picker (first boot)", sc_language_picker, {}),
    ("home_1", "Home, page 1", sc_home, dict(sel=4)),
    ("home_2", "Home, page 2", sc_home, dict(sel=8)),
    ("cable_test_mode", "Cable Test: mode selector", sc_cable_test_a, dict(mode=1)),
    ("cable_test_armed", "Cable Test: ready", sc_cable_test_b, {}),
    ("cable_test_result_switch", "Cable Test: result (switch)", sc_cable_result_switch, {}),
    ("cable_test_result_farend", "Cable Test: result (far end)", sc_cable_result_farend, {}),
    ("scan", "SCAN", sc_scan, {}),
    ("flash_testing", "FLASH: testing", sc_flash_testing, {}),
    ("flash_note", "FLASH: link up", sc_flash_note, {}),
    ("length_idle", "Length: ready", sc_length_idle, {}),
    ("length_testing", "Length: testing", sc_length_testing, {}),
    ("length_result", "Length: result", sc_length_result, {}),
    ("length_out_of_range", "Length: out of range", sc_length_result, dict(cm=(0, 0, 0, 0))),
    ("length_timeout", "Length: timeout", sc_length_timeout, {}),
    ("qc_test", "QC Test", sc_qc_test, {}),
    ("qc_test_uncalibrated", "QC Test: not calibrated", sc_qc_uncal, {}),
    ("speed_idle", "SPEED: ready", sc_speed_idle, {}),
    ("speed_testing", "SPEED: testing", sc_speed_testing, {}),
    ("speed_result", "SPEED: result", sc_speed_result, {}),
    ("speed_timeout", "SPEED: connect timeout", sc_speed_timeout, {}),
    ("poe", "POE", sc_poe, {}),
    ("settings", "Settings", sc_settings, {}),
    ("about", "About", sc_about, {}),
    ("factory_reset", "Factory reset", sc_factory_reset, {}),
    ("lowbatt", "Low battery", sc_lowbatt, {}),
]


def render(ids=None, langs=("en", "zh", "th")):
    report = {}
    for sid, title, fn, kw in SCREENS:
        if ids and sid not in ids:
            continue
        for tag in langs:
            lang, thai = {"en": (1, False), "zh": (2, False), "th": (2, True)}[tag]
            s = scene(lang, thai)
            try:
                fn(s, **kw)
                err = None
            except Exception as e:                       # keep going, note the failure
                err = repr(e)
            s.image(2).save(os.path.join(OUT, f"{sid}_{tag}.png"))
            report[f"{sid}_{tag}"] = dict(err=err, missing=s.missing,
                                          text=[(k, t, x, y) for k, t, x, y, fg, ex in s.log if k != "ascii" or tag == "en"])
            print(sid, tag, "ERR " + err if err else "ok", s.missing or "")
    json.dump(report, open(os.path.join(OUT, "report.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    return report


if __name__ == "__main__":
    ids = sys.argv[1:] or None
    render(ids)
