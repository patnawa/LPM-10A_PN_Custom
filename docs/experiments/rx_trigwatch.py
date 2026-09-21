"""Read-only watch for a commit trigger: logs VTOR + changes in SRAM 0x0-0x400 (bootloader state)
about every 100 ms, survives SWD dropouts (re-attaches). No halt/reset/write."""
import json, sys, time
from datetime import datetime
from pyocd.probe.stlink.stlink import STLink
from pyocd.probe.stlink.usb import STLinkUSBInterface
from rx_ro import OUT, EXPECTED_DBG_ID

label, secs = sys.argv[1], float(sys.argv[2])
SIZE = 0x400
OUT.mkdir(exist_ok=True)
path = OUT / f"{label}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.jsonl"
f = path.open("w")
print(f"watching {path}", flush=True)


def attach():
    p = STLinkUSBInterface.get_all_connected_devices()[0]
    l = STLink(p); l.open()
    try:
        l.set_swd_frequency(100000); l.enter_debug(STLink.Protocol.SWD); l.open_ap(0)
        if int.from_bytes(bytes(l.read_mem32(0xE0042000, 4, 0, 0)), "little") != EXPECTED_DBG_ID:
            raise RuntimeError("wrong chip")
        return l
    except Exception:
        try: l.close()
        except Exception: pass
        raise


link, prev, prev_vtor, n, alive = None, None, None, 0, False
t0 = time.perf_counter()
while time.perf_counter() - t0 < secs:
    now = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    try:
        if link is None:
            link = attach()
            print(f"{now} attached", flush=True); alive = True
            prev = None
        vtor = int.from_bytes(bytes(link.read_mem32(0xE000ED08, 4, 0, 0)), "little")
        cur = bytes(link.read_mem32(0x20000000, SIZE, 0, 0))
    except Exception as exc:
        if alive:
            print(f"{now} LINK LOST: {type(exc).__name__} {exc}", flush=True)
            f.write(json.dumps({"wall": now, "event": "link_lost", "error": str(exc)}) + "\n"); f.flush()
        alive = False
        try:
            if link: link.close()
        except Exception: pass
        link = None
        time.sleep(0.5)
        continue
    if vtor != prev_vtor:
        print(f"{now} VTOR=0x{vtor:08X}", flush=True)
        f.write(json.dumps({"wall": now, "vtor": f"0x{vtor:08X}"}) + "\n"); f.flush()
        prev_vtor = vtor
    if prev is None:
        f.write(json.dumps({"wall": now, "full": cur.hex()}) + "\n"); f.flush()
    elif cur != prev:
        runs, s = [], None
        for i in range(SIZE):
            if cur[i] != prev[i]:
                if s is None: s = i
            elif s is not None:
                runs.append((s, i)); s = None
        if s is not None: runs.append((s, SIZE))
        ch = [{"addr": f"0x{0x20000000+a:08X}", "old": prev[a:b].hex(), "new": cur[a:b].hex()} for a, b in runs]
        f.write(json.dumps({"wall": now, "changes": ch}) + "\n"); f.flush()
        vis = [c for c in ch if c["addr"] not in ("0x20000008", "0x2000014C")]
        if vis:
            print(now, " ".join(f'{c["addr"][6:]}:{c["old"][:8]}->{c["new"][:8]}' for c in vis[:10]), flush=True)
        n += 1
    prev = cur
if link:
    link.close()
print("done", n, flush=True)
