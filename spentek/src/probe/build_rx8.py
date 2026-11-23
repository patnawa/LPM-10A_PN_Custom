"""RX PN1.30 -> probe build 8 (C): power-on tune, tracing sound themes, volume steps, peak hold, signal-lost alarm,
mode announce, low-battery warning, idle reminder, lamp modes with strobe, battery blips, 15-minute auto-off."""
import hashlib, struct, sys
from keystone import Ks, KS_ARCH_ARM, KS_MODE_THUMB
from cc import compile_blob
BASE = 0x08006800
PARENT_SHA = "407b0ba3b80883e4f640ef7e2040a56004ca780a5bd8b81cf3a371ca04a67135"
DISPATCH, OLD_HELPER, DELAY_MS = 0x0800AC50, 0x0800CE28, 0x0800B9A0
BOOT_BEEP_SITE, BOOT_DELAY_CALL, KEY_SITE, AUTO_OFF_LIT = 0x0800B8CE, 0x0800B8EA, 0x080082E8, 0x0800A9CC
AUTO_OFF_MS = 15 * 60 * 1000
ks = Ks(KS_ARCH_ARM, KS_MODE_THUMB)
asm = lambda src, addr: bytes(ks.asm(src, addr)[0])
def wrap(raw):
    name = b"APP_LPM-10RX_V3.0.0_260416.bin".ljust(32, b"\0")
    out = (name + struct.pack("<III", 0x1000, len(raw), 0x1000 + len(raw) - 1)).ljust(0x1000, b"\0") + raw
    return out + b"\0" * (-len(out) % 4096)
def build(parent):
    assert hashlib.sha256(parent).hexdigest() == PARENT_SHA, "not the exact PN1.30 raw image"
    img = bytearray(parent)
    at = lambda a: a - BASE
    def poke(a, old, new):
        assert bytes(img[at(a):at(a) + len(old)]) == old, f"guard failed at {a:#x}: {bytes(img[at(a):at(a)+len(old)]).hex()}"
        assert len(old) == len(new); img[at(a):at(a) + len(new)] = new
    cave = BASE + len(img)
    assert cave % 4 == 0
    blob = compile_blob(cave)
    img += blob
    poke(BOOT_BEEP_SITE, bytes.fromhex("6421"), bytes.fromhex("0121"))        # stock power-on beep: 100 ms -> 1 ms (the tune replaces it)
    poke(AUTO_OFF_LIT, struct.pack("<I", 300001), struct.pack("<I", AUTO_OFF_MS + 1))
    poke(DISPATCH, asm(f"b.w {OLD_HELPER:#x}", DISPATCH), asm(f"b.w {cave:#x}", DISPATCH))
    poke(BOOT_DELAY_CALL, asm(f"bl {DELAY_MS:#x}", BOOT_DELAY_CALL), asm(f"bl {cave + 4:#x}", BOOT_DELAY_CALL))
    poke(KEY_SITE, bytes.fromhex("062933d3"), asm(f"bl {cave + 8:#x}", KEY_SITE))
    return bytes(img), cave, len(blob)
if __name__ == "__main__":
    parent = open(sys.argv[1], "rb").read()
    assert wrap(parent) == open(sys.argv[2], "rb").read(), "wrap() does not reproduce the repo's PN1.30 container"
    raw, cave, n = build(parent)
    cont = wrap(raw)
    open(sys.argv[3] + "/APP_LPM-10RX_PN1.30-spence8.bin", "wb").write(raw)
    open(sys.argv[3] + "/APP_LPM-10RX_PN1.30-spence8-update.bin", "wb").write(cont)
    print(f"code at {cave:#x}, {n} bytes; raw {len(parent)} -> {len(raw)}; container {len(cont)} bytes")
    print("container sha256", hashlib.sha256(cont).hexdigest())
