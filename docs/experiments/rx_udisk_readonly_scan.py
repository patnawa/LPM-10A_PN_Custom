"""Scan the explicitly guarded RX virtual disk with SCSI READ commands only.

The Windows pass-through API requires a read/write-access handle; the only
SCSI opcodes here are READ CAPACITY(10) and READ(10), both DATA_IN. There is
no write, erase, format, reset, eject, driver change or file copy to RX.
Run only while the RX BOOTLOADER volume is mounted. Output is local evidence,
not an MCU-flash backup. Nonzero transfer chunks are retained; zero chunks
are represented by the complete stream hash and coverage count.
"""

import ctypes as c
from ctypes import wintypes as w
from datetime import datetime
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import time


class SPTD(c.Structure):
    _fields_ = [("Length", w.USHORT), ("ScsiStatus", w.BYTE),
                ("PathId", w.BYTE), ("TargetId", w.BYTE), ("Lun", w.BYTE),
                ("CdbLength", w.BYTE), ("SenseInfoLength", w.BYTE), ("DataIn", w.BYTE),
                ("DataTransferLength", w.ULONG), ("TimeOutValue", w.ULONG),
                ("DataBuffer", c.c_void_p), ("SenseInfoOffset", w.ULONG), ("Cdb", w.BYTE * 16)]


class Packet(c.Structure):
    _fields_ = [("sptd", SPTD), ("sense", w.BYTE * 32)]


def main():
    guard = r"""
    $ErrorActionPreference = 'Stop'
    $rxLogical = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='D:'"
    $rxParts = @(Get-CimAssociatedInstance -InputObject $rxLogical -Association Win32_LogicalDiskToPartition)
    $rxDrives = @($rxParts | ForEach-Object { Get-CimAssociatedInstance -InputObject $_ -Association Win32_DiskDriveToDiskPartition })
    if ($rxLogical.VolumeName -ne 'BOOTLOADER' -or $rxLogical.DriveType -ne 2 -or $rxDrives.Count -ne 1 -or
        $rxDrives[0].PNPDeviceID -ne 'USBSTOR\DISK&VEN_NATIONS&PROD_SD_FLASH_DISK&REV_1.0\N32L40X&0') { throw 'RX association guard failed' }
    $rxDrives[0] | Select-Object DeviceID,Model,PNPDeviceID | ConvertTo-Json -Compress
    """
    device = json.loads(subprocess.check_output(["powershell.exe", "-NoProfile", "-Command", guard], text=True))
    assert c.sizeof(c.c_void_p) == 8 and c.sizeof(SPTD) == 56
    assert SPTD.DataBuffer.offset == 24 and SPTD.Cdb.offset == 36
    k = c.WinDLL("kernel32", use_last_error=True)
    k.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, c.c_void_p, w.DWORD, w.DWORD, w.HANDLE]
    k.CreateFileW.restype = w.HANDLE
    k.DeviceIoControl.argtypes = [w.HANDLE, w.DWORD, c.c_void_p, w.DWORD, c.c_void_p, w.DWORD, c.POINTER(w.DWORD), c.c_void_p]
    k.DeviceIoControl.restype = w.BOOL
    k.VirtualAlloc.argtypes = [c.c_void_p, c.c_size_t, w.DWORD, w.DWORD]
    k.VirtualAlloc.restype = c.c_void_p
    k.VirtualFree.argtypes = [c.c_void_p, c.c_size_t, w.DWORD]
    k.CloseHandle.argtypes = [w.HANDLE]
    root = Path.home() / "Desktop" / "LPM-10RX-SWD-2026-09-20"
    out = root / ("udisk-read-scan-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
    out.mkdir(parents=True, exist_ok=False)
    report = {"started_at": datetime.now().astimezone().isoformat(), "device": device,
              "method": "SCSI DATA_IN: READ CAPACITY(10), then READ(10) across reported 100 MiB",
              "device_data_writes": False, "complete": False, "bytes_read": 0,
              "nonzero_bytes": 0, "nonzero_chunks": [], "output_directory": str(out)}
    handle = k.CreateFileW(r"\\.\D:", 0xC0000000, 3, None, 3, 0, None)
    if handle == c.c_void_p(-1).value:
        raise c.WinError(c.get_last_error())
    buffer = k.VirtualAlloc(None, 65536, 0x3000, 4)
    if not buffer:
        k.CloseHandle(handle)
        raise c.WinError(c.get_last_error())

    def read(cdb, length):
        assert len(cdb) == 10 and cdb[0] in (0x25, 0x28) and 0 < length <= 16384
        packet = Packet()
        packet.sptd.Length = c.sizeof(SPTD)
        packet.sptd.CdbLength = 10
        packet.sptd.SenseInfoLength = 32
        packet.sptd.DataIn = 1
        packet.sptd.DataTransferLength = length
        packet.sptd.TimeOutValue = 5
        packet.sptd.DataBuffer = buffer
        packet.sptd.SenseInfoOffset = Packet.sense.offset
        packet.sptd.Cdb[:10] = cdb
        returned = w.DWORD()
        ok = k.DeviceIoControl(handle, 0x4D014, c.byref(packet), c.sizeof(packet),
                             c.byref(packet), c.sizeof(packet), c.byref(returned), None)
        if not ok or packet.sptd.ScsiStatus or packet.sptd.DataTransferLength != length:
            raise RuntimeError(f"Read failed: CDB={bytes(cdb).hex()}, Win32={c.get_last_error() if not ok else 0}, "
                               f"SCSI={packet.sptd.ScsiStatus}, length={packet.sptd.DataTransferLength}, "
                               f"sense={bytes(packet.sense).hex()}; no recovery command issued")
        return c.string_at(buffer, length)

    digest = hashlib.sha256()
    started = time.perf_counter()
    try:
        last, sector = struct.unpack(">II", read(bytes([0x25]) + bytes(9), 8))
        if (last, sector) != (51199, 2048):
            raise RuntimeError("Reported RX geometry changed; refusing scan")
        report.update(last_lba=last, bytes_per_sector=sector)
        print(f"READ_SCAN_STARTED {out}", flush=True)
        for lba in range(0, last + 1, 8):
            count = min(8, last + 1 - lba)
            cdb = bytearray(10)
            cdb[0] = 0x28
            struct.pack_into(">I", cdb, 2, lba)
            struct.pack_into(">H", cdb, 7, count)
            data = read(cdb, count * sector)
            digest.update(data)
            nz = sum(value != 0 for value in data)
            report["bytes_read"] += len(data)
            report["nonzero_bytes"] += nz
            if nz:
                name = f"lba-{lba:05d}-blocks-{count}.bin"
                (out / name).write_bytes(data)
                report["nonzero_chunks"].append({"lba": lba, "blocks": count, "path": str(out / name),
                    "nonzero_bytes": nz, "sha256": hashlib.sha256(data).hexdigest()})
            if report["bytes_read"] % (16 * 1024 * 1024) == 0:
                print(f"READ_PROGRESS {report['bytes_read'] // (1024 * 1024)}/100 MiB, nonzero={report['nonzero_bytes']}", flush=True)
        report["complete"] = True
        report["sha256_complete_stream"] = digest.hexdigest()
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        report["sha256_read_prefix"] = digest.hexdigest()
    finally:
        k.VirtualFree(buffer, 0, 0x8000)
        k.CloseHandle(handle)
        report["elapsed_s"] = time.perf_counter() - started
        report["completed_at"] = datetime.now().astimezone().isoformat()
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)
    if not report["complete"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
