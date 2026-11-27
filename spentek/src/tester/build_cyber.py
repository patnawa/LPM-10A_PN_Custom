"""TX PN2.34D -> 'PN2.34C': neon cyberpunk theme + SPENTEK wordmark.

Theme: every pixel sent to the display goes through one routine. Greys, whites, blues and greens are
mapped by brightness onto a neon ramp: black -> magenta/hot pink for mid tones -> cyan for bright
ones. Warm colours (red, orange, yellow, brown) pass through unchanged so fault colours keep their meaning.
Logo: the 108x18 FNIRSI logo asset is replaced in place by a SPENTEK wordmark of the same size.
"""
import hashlib, struct, sys
from keystone import Ks, KS_ARCH_ARM, KS_MODE_THUMB
PARENT_SHA = "a5b1deddfa067f0726fd13facfddbe400436ba6ecc845f6d2fafacebaf45f810"   # PN2.34D diagnostic build
APP, HDR, LCD = 0x0800A000, 0x1000, 0x60020000
FLOOR, WARM = 14, 8
LOGO = 0x080252ED
# pixel-data stores: (address of the 'ldr rA, =LCD', bytes of ldr+strh, colour register)
SITES = [(0x08016A64, "0448 0480", "r4"),          # lcd_fill_screen
         (0x08016C08, "0249 0880", "r0"),          # lcd_put_pixel
         (0x08016D3C, "0748 a0f800a0", "sl"),      # gui_draw_shape fill
         (0x0801705E, "0248 0580", "r5")]          # pixel with explicit colour
ks = Ks(KS_ARCH_ARM, KS_MODE_THUMB)
asm = lambda src, addr: bytes(ks.asm(src, addr)[0])

def theme(c):
    """Python model of the routine below."""
    r, g, b = c >> 11, (c >> 5) & 63, c & 31
    if r - b >= WARM:
        return c
    t = max(2 * max(r, b), g) - FLOOR
    if t < 0: t = 0
    t += t >> 2                                   # 0..61
    return (((t * (62 - t)) >> 5) << 11) | (((t * t) >> 6) << 5) | min(t, 31)

FONT = {  # 5x7
 "S": ["01111","10000","10000","01110","00001","00001","11110"],
 "P": ["11110","10001","10001","11110","10000","10000","10000"],
 "E": ["11111","10000","10000","11110","10000","10000","11111"],
 "N": ["10001","11001","10101","10011","10001","10001","10001"],
 "T": ["11111","00100","00100","00100","00100","00100","00100"],
 "K": ["10001","10010","10100","11000","10100","10010","10001"],
}
def wordmark(w, h, bg, fg):
    px = [bg] * (w * h)
    state = {'fg': fg}
    fg_now = lambda: state['fg']
    text, s, gap, cur = "SPENTEK", 2, 3, 8
    total = len(text) * 5 * s + len(text) * gap + cur
    x0, y0 = (w - total) // 2 + 2, 1
    def box(x, y, ww, hh):
        for yy in range(y, y + hh):
            for xx in range(x, x + ww):
                px[yy * w + xx] = fg_now()
    x = x0
    for ch in text:
        for ry, row in enumerate(FONT[ch]):
            for rx, bit in enumerate(row):
                if bit == "1": box(x + rx * s, y0 + ry * s, s, s)
        x += 5 * s + gap
    state['fg'] = 0xFFE0                                  # cursor: yellow (a warm colour, so it is kept as is)
    box(x, y0, cur, 7 * s)
    state['fg'] = 0x8410                                  # mid grey -> hot pink under the theme
    box(x0, h - 1, total - cur - gap, 1)         # underline
    box(x0 - 4, y0, 2, 7 * s + 2)                # left bracket bar
    return px

if __name__ == "__main__":
    d = bytearray(open(sys.argv[1], "rb").read())
    assert hashlib.sha256(d).hexdigest() == PARENT_SHA, "expects the PN2.34D build"
    off, ln, end = struct.unpack_from("<III", d, 0x20)
    assert not any(d[off + ln:]) and ln % 4 == 0
    f = lambda a: a - APP + HDR
    cave = APP + ln
    stubs = "".join(f"""
    stub{n}:
        push  {{r1, r2, lr}}
        {'' if reg == 'r0' else f'mov   r0, {reg}'}
        bl    theme
        mov.w r1, #0x60000000
        add.w r1, r1, #0x20000
        strh  r0, [r1]
        {'mov   r0, r1' if reg != 'r0' else ''}
        pop   {{r1, r2, pc}}
    """ for n, (_, _, reg) in enumerate(SITES))
    stubs = stubs.replace("""        add.w r1, r1, #0x20000
        strh  r0, [r1]
        
        pop   {r1, r2, pc}""", """        add.w r1, r1, #0x20000
        strh  r0, [r1]
        ldr   r2, [sp, #4]
        add   sp, #8
        pop   {pc}""")
    assert stubs.count("add   sp, #8") == 1                     # put_pixel: the original leaves r1 = LCD address
    src = f"""
    theme:                              @ r0 = RGB565 -> themed RGB565 ; uses r1, r2
        uxth  r0, r0
        lsrs  r1, r0, #11
        and   r2, r0, #31
        subs  r1, r1, r2
        cmp   r1, #{WARM}
        bge   keep
        lsrs  r1, r0, #11
        cmp   r1, r2
        bhs   t1
        mov   r1, r2
    t1: lsls  r1, r1, #1
        ubfx  r2, r0, #5, #6
        cmp   r1, r2
        bhs   t2
        mov   r1, r2
    t2: subs  r1, #{FLOOR}
        bge   t3
        movs  r1, #0
    t3: add   r1, r1, r1, lsr #2      @ t = brightness 0..61
        rsb   r2, r1, #62
        muls  r2, r1, r2
        lsrs  r2, r2, #5              @ red   = t*(62-t)/32 : peaks in the mid tones
        lsls  r2, r2, #11
        mov   r0, r1
        muls  r0, r1, r0
        lsrs  r0, r0, #6              @ green = t*t/64      : only the bright end
        orr   r2, r2, r0, lsl #5
        cmp   r1, #31
        bls   t4
        movs  r1, #31
    t4: orr   r0, r2, r1              @ blue  = min(t, 31)
    keep:
        bx    lr
    {stubs}
        .balign 4
    """
    code = asm(src, cave)
    assert len(code) <= len(d) - off - ln
    d[off + ln: off + ln + len(code)] = code
    struct.pack_into("<III", d, 0x20, off, ln + len(code), off + ln + len(code) - 1)
    # stub addresses: assemble the prefix up to each label (no literal pools before the end, so sizes hold)
    for n, (site, old, reg) in enumerate(SITES):
        addr = cave + len(asm(src.split(f"stub{n}:")[0] + "\n", cave))
        oldb = bytes.fromhex(old)
        assert bytes(d[f(site):f(site) + len(oldb)]) == oldb, hex(site)
        new = asm(f"bl {addr:#x}", site) + bytes.fromhex("00bf") * ((len(oldb) - 4) // 2)
        d[f(site):f(site) + len(oldb)] = new
    # logo
    o = f(LOGO); magic, w, h, flags = struct.unpack_from("<HHHH", d, o)
    assert (magic, w, h) == (0x1000, 108, 18)
    bg = struct.unpack_from("<H", d, o + 8)[0]
    struct.pack_into(f"<{w*h}H", d, o + 8, *wordmark(w, h, bg, 0xFFFF))
    n = 0; p = d.find(b"PN2.34D\0")
    while p >= 0:
        d[p:p + 8] = b"PN2.34C\0"; n += 1; p = d.find(b"PN2.34D\0", p + 1)
    assert n == 2
    open(sys.argv[2], "wb").write(d)
    print(f"theme code at {cave:#x}, {len(code)} bytes; payload {ln} -> {ln + len(code)}; logo bg {bg:#06x}")
    print("sha256", hashlib.sha256(d).hexdigest())
