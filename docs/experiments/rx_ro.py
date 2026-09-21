"""Read-only RX (N32L406) SWD helper.

Direct STLink transport: no target definition, flash algorithm, halt, reset,
unlock, erase, or target-memory write. Only debug-port setup is performed.

  rx_ro.py status                      -> chip identity / protection / core state
  rx_ro.py sram  <label>               -> full 24 KiB SRAM snapshot to Desktop folder
  rx_ro.py watch <label> <seconds>     -> repeated 24 KiB snapshots, saving only diffs
"""
import hashlib, json, sys, time
from datetime import datetime
from pathlib import Path

from pyocd.probe.stlink.stlink import STLink
from pyocd.probe.stlink.usb import STLinkUSBInterface

OUT = Path.home() / "Desktop" / "LPM-10RX-SWD-2026-09-21"  # evidence folder used on 2026-09-21
SRAM_BASE, SRAM_SIZE = 0x20000000, 24 * 1024
EXPECTED_DBG_ID = 0x22644017


def rd32(link, addr):
    return int.from_bytes(bytes(link.read_mem32(addr, 4, 0, 0)), "little")


def open_link():
    probes = STLinkUSBInterface.get_all_connected_devices()
    if len(probes) != 1:
        raise SystemExit(f"Expected exactly one ST-Link, found {len(probes)}")
    link = STLink(probes[0])
    link.open()
    link.set_swd_frequency(100000)
    link.enter_debug(STLink.Protocol.SWD)
    link.open_ap(0)
    chip = rd32(link, 0xE0042000)
    if chip != EXPECTED_DBG_ID:
        link.close()
        raise SystemExit(f"Unexpected DBG_ID 0x{chip:08X}; refusing")
    return link, probes[0].serial_number


def status(link):
    regs = {
        "DBG_ID": 0xE0042000, "CPUID": 0xE000ED00, "VTOR": 0xE000ED08,
        "DHCSR": 0xE000EDF0, "ICSR": 0xE000ED04, "CFSR": 0xE000ED28,
        "HFSR": 0xE000ED2C, "FLASH_OB": 0x4002201C, "RDP1_word": 0x1FFFF800,
        "RDP2_word": 0x1FFFF810, "SP_word0": 0x20000000,
    }
    out = {k: f"0x{rd32(link, a):08X}" for k, a in regs.items()}
    out["probe_firmware"] = link.version_str
    out["probe_voltage"] = link.target_voltage
    return out


def read_sram(link):
    data = bytearray()
    for off in range(0, SRAM_SIZE, 1024):
        chunk = bytes(link.read_mem32(SRAM_BASE + off, 1024, 0, 0))
        if len(chunk) != 1024:
            raise RuntimeError("short SRAM read")
        data += chunk
    return bytes(data)


def save(label, data, meta):
    OUT.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    p = OUT / f"{label}-{stamp}.bin"
    p.write_bytes(data)
    meta.update({"path": str(p), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                 "time": datetime.now().astimezone().isoformat()})
    p.with_suffix(".json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return p


def diff(a, b):
    runs, start = [], None
    for i in range(len(a)):
        if a[i] != b[i]:
            if start is None:
                start = i
        elif start is not None:
            runs.append((start, i)); start = None
    if start is not None:
        runs.append((start, len(a)))
    return runs


def main():
    cmd = sys.argv[1]
    link, serial = open_link()
    try:
        st = status(link)
        st["probe_serial"] = serial
        if cmd == "status":
            print(json.dumps(st, indent=2))
        elif cmd == "sram":
            t0 = time.perf_counter(); data = read_sram(link); st["read_seconds"] = time.perf_counter() - t0
            p = save(sys.argv[2], data, st)
            print(json.dumps({"saved": str(p), "sha256": hashlib.sha256(data).hexdigest(),
                              "read_seconds": st["read_seconds"], "VTOR": st["VTOR"], "DHCSR": st["DHCSR"]}, indent=2))
        elif cmd == "watch":
            label, secs = sys.argv[2], float(sys.argv[3])
            prev = read_sram(link); save(f"{label}-000", prev, dict(st))
            n, t0 = 1, time.perf_counter()
            print(f"baseline saved; watching {secs}s", flush=True)
            while time.perf_counter() - t0 < secs:
                try:
                    cur = read_sram(link)
                except Exception as exc:
                    print(f"t={time.perf_counter()-t0:6.1f}s read failed: {exc}", flush=True)
                    time.sleep(1)
                    try:
                        link.close(); link, _ = open_link()
                        print("re-attached", flush=True)
                    except Exception as exc2:
                        print(f"re-attach failed: {exc2}", flush=True)
                    continue
                vtor = rd32(link, 0xE000ED08)
                runs = diff(prev, cur)
                if runs:
                    p = save(f"{label}-{n:03d}", cur, dict(st, vtor_now=f"0x{vtor:08X}", changed_runs=[[f"0x{SRAM_BASE+s:08X}", e - s] for s, e in runs]))
                    print(f"t={time.perf_counter()-t0:6.1f}s VTOR=0x{vtor:08X} snapshot {n}: {len(runs)} changed run(s) -> "
                          + ", ".join(f"0x{SRAM_BASE+s:08X}+{e-s}" for s, e in runs[:12])
                          + (" ..." if len(runs) > 12 else ""), flush=True)
                    prev, n = cur, n + 1
            print(f"done: {n} snapshots", flush=True)
    finally:
        link.close()


if __name__ == "__main__":
    main()
