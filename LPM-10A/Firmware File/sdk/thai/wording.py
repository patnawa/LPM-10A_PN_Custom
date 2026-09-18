"""The Thai wording: every Chinese UI string (as decoded from the firmware) and
the English-only strings that get a Thai variant.  Pure data, shared by the
mock-ups (thai/mockup.py), the cell table (thai/cells.py) and the patch
(patches.py, thai-ui).  Edit here to change a translation, then run
`python -m thai.cells` to regenerate fonts_out/thai16.*."""

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
# English-only strings in stock (no Chinese variant) that the Thai build also translates,
# through a hook on gui_blit that acts only while the language is Thai.  Layout:
#   centre  -> centred where the English text was centred (x + w/2)
#   left    -> starts at the English text's x
#   x       -> starts at this x instead; "clear": the 16-px line x 12..220 is wiped first
#   dots    -> the "..." animation stays ASCII and only moves right of the Thai "Testing"
ASCII_TH = {
    "Result error!!": {"text": "ผลลัพธ์ผิดพลาด!!", "layout": "centre"},
    "Test timeout!!": {"text": "หมดเวลาทดสอบ!!", "layout": "x", "x": 12, "clear": True},
    "Error!!": {"text": "ผิดพลาด!!", "layout": "left"},
    "OFF": {"text": "ปิด", "layout": "centre"},
}
# the Length / Speed "..." animation is drawn at x = 68, right after the English "Testing";
# in Thai it moves to DOTS_X (past the wider Thai label).  Only strings drawn at x = 68 move.
DOTS = ("   ", ".  ", ".. ", "...")
DOTS_X = 82
