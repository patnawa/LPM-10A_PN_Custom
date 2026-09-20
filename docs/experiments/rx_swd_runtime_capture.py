"""Observe this RX's live SRAM through ST-Link; never program target memory.

Requires pyOCD 0.45.1. Uses its direct STLink transport, without a target
definition, flash algorithm, user script, reset, halt, or unlock operation.
SWD transport setup and sticky-error clearing still configure debug registers.
The SRAM layout is inferred from the supplied RX application, not proof of the
installed image. Samples are not atomic. Power RX normally before attaching.
"""

import argparse
import hashlib
import json
import struct
import time
from datetime import datetime
from pathlib import Path

from pyocd.probe.stlink.stlink import STLink
from pyocd.probe.stlink.usb import STLinkUSBInterface


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe-id", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--seconds", type=float, default=30)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 50:
        parser.error("Capture must be between 1 and 50 seconds")
    if not args.label or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-" for c in args.label):
        parser.error("Use a lowercase letters/digits/hyphens label")

    probes = [d for d in STLinkUSBInterface.get_all_connected_devices()
              if d.serial_number == args.probe_id]
    if len(probes) != 1:
        raise SystemExit("Expected exactly one explicitly selected ST-Link")
    output = Path.home() / "Desktop" / "LPM-10RX-SWD-2026-09-20"
    output.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = output / f"{args.label}-{stamp}.jsonl"
    report = {
        "started_at": datetime.now().astimezone().isoformat(),
        "path": str(path),
        "requested_seconds": args.seconds,
        "requested_swd_hz": 100000,
        "method": "Direct STLink reads; no target-memory write, halt, reset, erase, or unlock",
        "layout_basis": "Store raw bytes and both V3.0.0 and observed-device hypotheses; installed image not authenticated",
        "samples_atomic": False,
        "samples": 0,
    }
    link = STLink(probes[0])
    digest = hashlib.sha256()
    error = None
    try:
        link.open()
        report["probe_firmware"] = link.version_str
        report["probe_reported_voltage"] = link.target_voltage
        link.set_swd_frequency(100000)
        link.enter_debug(STLink.Protocol.SWD)
        link.open_ap(0)
        chip = int.from_bytes(bytes(link.read_mem32(0xE0042000, 4, 0, 0)), "little")
        if chip != 0x22644017:
            raise RuntimeError(f"Unexpected DBG_ID 0x{chip:08X}; refusing this RAM layout")
        report["dbg_id"] = f"0x{chip:08X}"
        report["vtor"] = f"0x{int.from_bytes(bytes(link.read_mem32(0xE000ED08, 4, 0, 0)), 'little'):08X}"
        if report["vtor"] != "0x08006800":
            raise RuntimeError("Application vector base not selected")
        print(f"CAPTURE_STARTED {path}", flush=True)
        start = time.perf_counter()
        with path.open("xb") as stream:
            while time.perf_counter() - start < args.seconds:
                begin = time.perf_counter() - start
                state = bytes(link.read_mem32(0x20000048, 40, 0, 0))
                state_end = time.perf_counter() - start
                counter_block = bytes(link.read_mem32(0x200000EC, 36, 0, 0))
                counters = counter_block[16:]
                end = time.perf_counter() - start
                if len(state) != 40 or len(counter_block) != 36:
                    raise RuntimeError("Short SRAM transfer")
                ticks, speaker_ticks, _, _, beep = struct.unpack("<IIIII", counters)
                row = {
                    "begin_s": begin, "state_end_s": state_end, "end_s": end,
                    "mode": state[0], "request": state[1],
                    "v300_gap": state[0x12], "v300_grade": state[0x15],
                    "v300_gate_state": counter_block[3],
                    "v300_recent": int.from_bytes(state[0x24:0x26], "little"),
                    "observed_gap_05c": state[0x14],
                    "observed_index_05d": state[0x15],
                    "observed_recent_06e": int.from_bytes(state[0x26:0x28], "little"),
                    "beep_raw_word": beep, "beep": beep & 0xFF,
                    "tim1_ticks": ticks, "tim5_ticks": speaker_ticks,
                    "state_hex": state.hex(), "counters_hex": counters.hex(),
                    "sram_0ec_0fb_hex": counter_block[:16].hex(),
                }
                raw = (json.dumps(row, separators=(",", ":")) + "\n").encode("utf-8")
                stream.write(raw)
                digest.update(raw)
                report["samples"] += 1
                time.sleep(0.002)
        report["elapsed_s"] = time.perf_counter() - start
        report["sha256"] = digest.hexdigest()
    except Exception as exc:
        error = exc
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        try:
            link.close()
        except Exception as exc:
            report["close_error"] = str(exc)
        report["completed_at"] = datetime.now().astimezone().isoformat()
        path.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)
    if error is not None:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
