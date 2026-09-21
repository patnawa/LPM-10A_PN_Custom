"""Fast read-only watch of the first 1 KiB of RX SRAM (bootloader state) via ST-Link.
Logs every change as a JSONL row with timestamp. No halt/reset/write."""
import json, sys, time
from datetime import datetime
from pathlib import Path
from rx_ro import open_link, rd32, OUT

label, secs = sys.argv[1], float(sys.argv[2])
SIZE = int(sys.argv[3], 16) if len(sys.argv) > 3 else 0x400
link, _ = open_link()
OUT.mkdir(exist_ok=True)
path = OUT / f"{label}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.jsonl"
prev = bytes(link.read_mem32(0x20000000, SIZE, 0, 0))
t0 = time.perf_counter(); n = 0
with path.open("w") as f:
    f.write(json.dumps({"t": 0, "wall": datetime.now().isoformat(), "full": prev.hex()}) + "\n")
    print(f"watching {path}", flush=True)
    while time.perf_counter() - t0 < secs:
        cur = bytes(link.read_mem32(0x20000000, SIZE, 0, 0))
        if cur != prev:
            runs, s = [], None
            for i in range(SIZE):
                if cur[i] != prev[i]:
                    if s is None: s = i
                elif s is not None:
                    runs.append((s, i)); s = None
            if s is not None: runs.append((s, SIZE))
            row = {"t": round(time.perf_counter() - t0, 3), "wall": datetime.now().strftime("%H:%M:%S.%f"),
                   "changes": [{"addr": f"0x{0x20000000+a:08X}", "old": prev[a:b].hex(), "new": cur[a:b].hex()} for a, b in runs]}
            f.write(json.dumps(row) + "\n"); f.flush()
            n += 1
            prev = cur
link.close()
print(f"done, {n} change rows")
