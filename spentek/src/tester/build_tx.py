"""TX PN2.33 with the About screen's URL line replaced by a custom credit line."""
import hashlib, struct, sys
PARENTS = {"84f9fb991a5bf43f0e29d978277ebe76baa58ff21714b430c1b6cef040751e91": "PN2.33",
           "92ebb4cd60e7b652f32ca65cfa21401c1657fa63ee1b945864fed3c74a422227": "PN2.34"}
OLD = b"github.com/patnawa/LPM-10A_PN_Custom"
TEXT = sys.argv[3] if len(sys.argv) > 3 else "Modded by Spence the Canadian"
APP_BASE, HDR = 0x0800A000, 0x1000
f = lambda a: a - APP_BASE + HDR
d = bytearray(open(sys.argv[1], "rb").read())
parent = PARENTS.get(hashlib.sha256(d).hexdigest())
assert parent, "not an exact PN2.33 or PN2.34 file"
t = TEXT.encode("ascii")
assert len(t) <= len(OLD), "text must be at most 36 characters"
assert all(32 <= c < 127 for c in t)
o = d.find(OLD); assert o >= 0 and d.find(OLD, o + 1) < 0 and d[o + len(OLD)] == 0
d[o:o + len(OLD)] = t.ljust(len(OLD), b"\0")
w = len(t) * 6                      # 6x12 font
x = (240 - w) // 2                  # centred on the 240 px screen
assert d[f(0x08011498):f(0x08011498) + 2] == bytes.fromhex("d822") and d[f(0x080114A0):f(0x080114A0) + 2] == bytes.fromhex("0c20")
d[f(0x08011498)] = w                # movs r2, #w
d[f(0x080114A0)] = x                # movs r0, #x
open(sys.argv[2], "wb").write(d)
print(f'parent {parent}: text "{TEXT}" ({len(t)} chars, {w} px wide, x = {x}); file {len(d)} bytes')
print("sha256", hashlib.sha256(d).hexdigest())
