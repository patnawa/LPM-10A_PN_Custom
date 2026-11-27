"""TX PN2.34 + credit line -> 'PN2.34D' diagnostic build.

After every Length test the PHY's cable-diagnostic registers (ext 0x84..0x8A) are kept in RAM,
and Settings > About shows them as seven hex words on the bottom line:
    84   85   86   87   88   89   8A
Until a Length test has run, that line shows the credit text.
"""
import hashlib, struct, sys
from keystone import Ks, KS_ARCH_ARM, KS_MODE_THUMB
PARENT_SHA = "81ca4a43bce31db2a1c02c20496c0deb27d55c42cdce54a7a23cb36e121765ad"   # PN2.34 + credit line
APP, HDR = 0x0800A000, 0x1000
PHY_EXT_READ = 0x08018A80
SITE_POLL, SITE_PAIR = 0x08012034, 0x080124B2          # bl phy_ext_read: reg 0x84 poll, regs 0x87..0x8A
SITE_ABOUT, SITE_W, SITE_X = 0x08011492, 0x08011498, 0x080114A0
RAW, TEXT, MAGIC = 0x2000FE00, 0x2000FE10, 0xC5D1      # scratch RAM high in the SDK's arena, far above its allocations
CREDIT = "  Modded by Spence the Canadian   "          # 34 characters, same width as the hex line
ks = Ks(KS_ARCH_ARM, KS_MODE_THUMB)
asm = lambda src, addr: bytes(ks.asm(src, addr)[0])

d = bytearray(open(sys.argv[1], "rb").read())
assert hashlib.sha256(d).hexdigest() == PARENT_SHA, "expects the PN2.34 file that already carries the credit line"
off, ln, end = struct.unpack_from("<III", d, 0x20)
assert off == HDR and end == off + ln - 1 and not any(d[off + ln:]) and ln % 4 == 0
f = lambda a: a - APP + HDR
def poke(a, old, new):
    assert bytes(d[f(a):f(a) + len(old)]) == old, f"guard failed at {a:#x}: {bytes(d[f(a):f(a)+len(old)]).hex()}"
    assert len(new) == len(old)
    d[f(a):f(a) + len(new)] = new

assert len(CREDIT) == 34
cave = APP + ln
src = f"""
wrap:                                   @ r0 = ext register, r1 = optional u16* ; returns the value
    push  {{r4, r5, r6, lr}}
    mov   r4, r0
    mov   r5, r1
    ldr   r6, ={RAW:#x}
    cmp   r4, #0x87
    bne   w_read
    movs  r0, #0x85
    movs  r1, #0
    bl    {PHY_EXT_READ:#x}
    strh  r0, [r6, #2]
    movs  r0, #0x86
    movs  r1, #0
    bl    {PHY_EXT_READ:#x}
    strh  r0, [r6, #4]
w_read:
    mov   r0, r4
    mov   r1, r5
    bl    {PHY_EXT_READ:#x}
    subs  r4, #0x84
    cmp   r4, #6
    bhi   w_out
    strh  r0, [r6, r4, lsl #1]
    cmp   r4, #6
    bne   w_out
    movw  r1, #{MAGIC}
    strh  r1, [r6, #14]
w_out:
    pop   {{r4, r5, r6, pc}}
    .pool
    .balign 4

about:                                  @ -> r0 = text for the About screen's bottom line, r1 = font size 12
    push  {{r4, r5, r6, lr}}
    ldr   r4, ={RAW:#x}
    ldrh  r0, [r4, #14]
    movw  r1, #{MAGIC}
    cmp   r0, r1
    bne   credit
    ldr   r5, ={TEXT:#x}
    mov   r6, r5
    movs  r2, #7
reg:
    ldrh  r0, [r4], #2
    movs  r3, #4
nib:
    lsrs  r1, r0, #12
    lsls  r0, r0, #4
    uxth  r0, r0
    cmp   r1, #10
    blo   dig
    adds  r1, #7
dig:
    adds  r1, #0x30
    strb  r1, [r5], #1
    subs  r3, #1
    bne   nib
    movs  r1, #0x20
    strb  r1, [r5], #1
    subs  r2, #1
    bne   reg
    movs  r1, #0
    strb  r1, [r5, #-1]
    mov   r0, r6
    b     out
credit:
    adr   r0, credit_text
out:
    movs  r1, #12
    pop   {{r4, r5, r6, pc}}
    .pool
    .balign 4
credit_text:
    .asciz "{CREDIT}"
    .balign 4
"""
code = asm(src, cave)
# symbol addresses: 'wrap' is first; find 'about' by assembling the prefix
about = cave + len(asm(src.split("about:")[0] + "\n", cave))
assert len(code) <= 3500
d[off + ln: off + ln + len(code)] = code
struct.pack_into("<III", d, 0x20, off, ln + len(code), off + ln + len(code) - 1)

bl = lambda site, target: asm(f"bl {target:#x}", site)
poke(SITE_POLL, bl(SITE_POLL, PHY_EXT_READ), bl(SITE_POLL, cave | 0))
poke(SITE_PAIR, bl(SITE_PAIR, PHY_EXT_READ), bl(SITE_PAIR, cave | 0))
old_about = bytes(d[f(SITE_ABOUT):f(SITE_ABOUT) + 4])
poke(SITE_ABOUT, old_about, bl(SITE_ABOUT, about))
poke(SITE_W, bytes([29 * 6, 0x22]), bytes([34 * 6, 0x22]))            # movs r2, #204
poke(SITE_X, bytes([33, 0x20]), bytes([(240 - 34 * 6) // 2, 0x20]))    # movs r0, #18
n = 0
o = d.find(b"PN2.34\0\0")
while o >= 0:
    d[o:o + 8] = b"PN2.34D\0"; n += 1
    o = d.find(b"PN2.34\0\0", o + 1)
assert n == 2, n
open(sys.argv[2], "wb").write(d)
print(f"cave code at {cave:#x} ({len(code)} bytes), wrap {cave:#x}, about {about:#x}; payload {ln} -> {ln + len(code)}; file {len(d)} bytes")
print("sha256", hashlib.sha256(d).hexdigest())
