"""Read-only capture of the RX detector state (RAM 0x20000040..0x20000120) at ~10 Hz."""
import json, sys, time
from datetime import datetime
from rx_ro import open_link, rd32, OUT

label, secs = sys.argv[1], float(sys.argv[2])
link, _ = open_link()
OUT.mkdir(exist_ok=True)
path = OUT / f"{label}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.jsonl"
t0 = time.perf_counter(); n = 0
with path.open("w") as f:
    print(f"capturing {path}", flush=True)
    while time.perf_counter() - t0 < secs:
        blk = bytes(link.read_mem32(0x20000040, 0xE0, 0, 0))
        row = {"t": round(time.perf_counter() - t0, 3), "ram40": blk.hex()}
        f.write(json.dumps(row) + "\n"); n += 1
        if n % 50 == 0:
            mode = blk[0x08]; gate_raw = int.from_bytes(blk[0x28:0x2A], "little"); gate_code = int.from_bytes(blk[0x2A:0x2C], "little")
            print(f"t={row['t']:5.1f}s mode={mode} knob_raw={gate_raw:4d} code={gate_code} recent={int.from_bytes(blk[0x2C:0x2E],'little')} gate_state={blk[0xAF]} beep={blk[0xCC]}", flush=True)
link.close()
print(f"done {n} rows -> {path}")
