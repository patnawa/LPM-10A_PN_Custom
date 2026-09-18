"""Where the Chinese UI strings live in the stock image, and how they are
referenced.  Derived from a verified inventory of every CJK drawer call
(sdk/thai/README: "inventory"); every entry is asserted against the image
bytes when the patch is applied, so a wrong address fails the build.

kind "cjk":   index bytes, terminated by a byte >= 0xAB (stock uses 0xFF)
kind "mixed": u16 units, 0x01xx = CJK index, 0x20..0x7E ASCII, 0x0000 end
slot:  bytes that belong to the string (up to the next used byte)
copy:  size of the stack copy some callers make (ldm/ldr/memcpy), or None
       when the flash pointer is passed directly

The Thai build never rewrites a string in place: each slot gets a 3..4 byte
(cjk) or 8 byte (mixed) REDIRECT stub, and the Thai text lives in the freed
glyph area.  The stub therefore has to fit the smallest copy a caller makes.
"""

# (addr, kind, Chinese text as decoded, slot bytes, smallest copy or None)
CJK_STRINGS = [
    (0x0800BC0C, "cjk", "测试出错", 8, 8),          # qc_test: not-calibrated prompt line 1
    (0x0800BC14, "cjk", "请移除网线后", 8, 8),        # qc_test: line 2
    (0x0800BC1C, "cjk", "长按右键校准", 8, 8),        # qc_test: line 3
    (0x0800C4AC, "cjk", "开始测试", 8, 8),          # cable_test: Test Start
    (0x0800C4B4, "cjk", "重新测试", 8, 8),          # cable_test: Test Retry
    (0x0800D894, "cjk", "测试中", 4, 4),           # flash: Testing (text box, mode 0x50)
    (0x0800D904, "cjk", "测试超时", 8, 8),          # speed/flash: Connect timeout (mode 0x40)
    (0x0800DB3C, "cjk", "请观察指示灯", 8, 8),        # flash: Please note LED
    (0x08010608, "cjk", "中文", 4, 4),            # settings: language value
    (0x08010794, "cjk", "关于", 4, 4),            # settings: About row
    (0x08010CE4, "cjk", "语言", 4, 4),            # language picker: title
    (0x08010E50, "cjk", "中文", 4, 4),            # language picker: option
    (0x080116AC, "cjk", "关于", 4, 4),            # about: title
    (0x080116B4, "cjk", "恢复出厂设置", 8, 8),        # about: Factory Reset button
    (0x080118C8, "cjk", "恢复出厂设置会重", 12, 12),    # factory reset: line 1
    (0x080118D4, "cjk", "置之前所有的修改", 12, 12),    # factory reset: line 2
    (0x080135C4, "cjk", "交换机标准", 8, 8),         # poe: row label
    (0x080135CC, "cjk", "标准协议", 8, 8),          # poe: row label
    (0x080135D4, "cjk", "供电方式", 8, 8),          # poe: row label
    (0x080135DC, "cjk", "功率等级", 8, 8),          # poe: row label
    (0x08013A50, "cjk", "标准", 4, 4),            # poe: value
    (0x08013D58, "cjk", "非标准", 4, 4),           # poe: value
    (0x08013D70, "cjk", "末端跨接", 8, 8),          # poe: value
    (0x08013D7C, "cjk", "中间跨接", 8, 8),          # poe: value
    (0x080142AC, "cjk", "抗干扰寻线", 8, 8),         # scan: mode 1 button
    (0x080142C0, "cjk", "普通寻线", 8, 8),          # scan: mode 2 button
    (0x08019980, "cjk", "单位", 4, 4),            # length: Unit
    (0x08019998, "cjk", "开始测试", 8, 8),          # length: Test Start
    (0x08019CAC, "cjk", "测试中", 4, 4),           # length: Testing (mode 0x40)
    (0x0801A7AC, "cjk", "开始测试", 8, 8),          # speed: Test Start
    (0x0801A7B4, "cjk", "重新测试", 8, 8),          # speed: Test Retry
    (0x0801B010, "cjk", "全双工", 4, 4),           # speed result: full duplex (mode 0x50)
    (0x0801B054, "cjk", "半双工", 4, 4),           # speed result: half duplex (mode 0x50)
    (0x0801B168, "cjk", "测试中", 4, 4),           # speed: Testing (mode 0x40)
    (0x0801E2F0, "mixed", "交换机", 8, 8),         # cable_test: Switch box
    (0x0801E308, "mixed", "远 端", 8, 8),          # cable_test: Far end box
    (0x0801E3E0, "mixed", "电量低请及时充电", 20, 20),  # low battery: line 1
    (0x0801E3F4, "mixed", "即将关机", 12, 12),       # low battery: line 2
    (0x0801E64E, "cjk", "英寸", 3, None),         # length units table, 3-byte stride (PN slot 0 = m)
    (0x0801E651, "cjk", "厘米", 3, None),         #   slot 1 = cm
    (0x0801E654, "cjk", "米", 4, None),          #   slot 2 = ft
    (0x0801E678, "cjk", "速率", 5, 12),           # speed: label (12-byte copy holds both labels)
    (0x0801E67D, "cjk", "双工模式", 7, 12),         # speed: label
    (0x0801E69C, "mixed", "超出测量范围", 16, 16),    # length: Out of range
    (0x0801E6AC, "mixed", "连接成功后开始闪烁", 20, 20),  # flash: note line 2
    (0x08064DA0, "cjk", "语言", 5, 28),           # settings labels table, 5-byte stride (28-byte copy)
    (0x08064DA5, "cjk", "亮度", 5, 28),
    (0x08064DAA, "cjk", "音量", 5, 28),
    (0x08064DAF, "cjk", "自动关机", 5, 28),
    (0x08064DB4, "cjk", "关于", 8, 28),           #   record 4, copied with the table
    (0x08064DCC, "mixed", "5分钟", 8, 8),          # settings: auto-off values
    (0x08064DD4, "mixed", "10分钟", 12, 12),
    (0x08064DE0, "mixed", "15分钟", 12, 12),
    (0x08064E1C, "mixed", "软件号:", 12, 12),       # about: labels (12-byte copies)
    (0x08064E28, "mixed", "硬件号:", 12, 12),
    (0x08064E34, "mixed", "型  号:", 12, 12),
    (0x08064E8E, "mixed", "网线对接", 14, None),     # menu names, 14-byte stride, pointer used directly: titles + home tiles
    (0x08064E9C, "mixed", "寻线", 14, None),
    (0x08064EAA, "mixed", "端口闪烁", 14, None),
    (0x08064EB8, "mixed", "长度测试", 14, None),
    (0x08064EC6, "mixed", "压接测试", 14, None),
    (0x08064ED4, "mixed", "网线速率", 14, None),
    (0x08064EE2, "mixed", "POE测试", 14, None),
    (0x08064EF0, "mixed", "设置", 14, None),
]

# single-glyph draws: (site of `movs r2,#idx`, stock bytes, Chinese glyph) -> a Thai word cell
GLYPH_SITES = [
    (0x0801184E, "8422", "是"),     # factory reset YES at (65,195)
    (0x0801186A, "8522", "否"),     # factory reset NO at (158,195)
]

# About page: the three Chinese label lines start at x = 71; the Thai labels are wider,
# so the Chinese branch starts them at 57 (movs r0,#0x47 -> #0x39)
ABOUT_LABEL_X = [(0x0801158C, "4720"), (0x080115B8, "4720"), (0x080115E6, "4720")]

# stock code that calls the drawers (bytes are the first instructions we replace with b.w)
CJK_TEXT = 0x080176AC      # f0b5 0546  push {r4-r7,lr}; mov r5,r0
MIXED_TEXT = 0x080173EC    # f8b5 0546  push {r3-r7,lr}; mov r5,r0
GUI_BLIT = 0x080174E8      # 2de9f847   push.w {r3-r8,sb,sl,lr}
GLYPH = 0x08017550
ASCII_GLYPH = 0x080171D4
LANG_IS = 0x0800FD2C
DRAW_SHAPE = 0x08016D08
BG_COLOUR = 0x200001AE
CJK_TABLE = 0x08066368
CJK_SLOTS = 171
