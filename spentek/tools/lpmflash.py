#!/usr/bin/env python3
"""lpmflash.py - guarded flashing for the FNIRSI LPM-10A tester (TX) and probe (RX) from Linux.

It refuses to write unless the target really is the unit's update drive and the file really is a
well-formed firmware image for that unit. The write itself uses the two methods already proven on
this hardware: mtools for the tester, fatpush.py (file placed at cluster 4) for the probe.

    sudo ./lpmflash.py check FILE              # inspect an image, touch nothing
    sudo ./lpmflash.py tx FILE [DEVICE]        # tester: off, hold M + Power, plug in USB-C
    sudo ./lpmflash.py rx FILE [DEVICE]        # probe:  off, hold SCAN, plug in USB

Without DEVICE it looks for exactly one removable drive of the right size. Nothing is written
until you type 'yes'.
"""
import hashlib, os, shutil, struct, subprocess, sys

UNITS = {
    "tx": dict(name="tester", prefix=b"APP_LPM-10A_", base=0x0800A000, limit=0x0807F000,
               dev_bytes=458752, how="tester off, hold M + Power, plug in USB-C"),
    "rx": dict(name="probe", prefix=b"APP_LPM-10RX_", base=0x08006800, limit=0x0801E000,
               dev_bytes=104857600, how="probe off, hold SCAN, plug in USB"),
}

def die(msg):
    sys.exit("lpmflash: " + msg)

def inspect_image(path):
    """Return (unit, facts) or stop with the reason the file is not a usable update image."""
    d = open(path, "rb").read()
    if len(d) < 0x1100 or len(d) % 4096:
        die(f"{path}: {len(d)} bytes is not a whole number of 4 KB pages; truncated or not an update file")
    if d[:5] in (b"<!DOC", b"<html") or d[:2] == b"\n<":
        die(f"{path}: this is a web page, not firmware (use GitHub's 'Download raw file')")
    name = d[:32].split(b"\0")[0]
    unit = next((u for u, c in UNITS.items() if name.startswith(c["prefix"])), None)
    if unit is None:
        if struct.unpack_from("<I", d, 0)[0] >> 16 == 0x2000:
            die(f"{path}: this is a raw image with no update header; the bootloader ignores those "
                "(for the probe, use the file ending in -update.bin)")
        die(f"{path}: header name {name!r} is not an LPM-10A tester or probe image")
    c = UNITS[unit]
    off, ln, end = struct.unpack_from("<III", d, 0x20)
    if off != 0x1000 or end != off + ln - 1 or off + ln > len(d):
        die(f"{path}: header lengths are inconsistent (offset {off:#x}, length {ln}, end {end:#x}, file {len(d)})")
    if len(d) - (off + ln) >= 4096 or any(d[off + ln:]):
        die(f"{path}: unexpected data after the image")
    sp, reset = struct.unpack_from("<II", d, off)
    if sp >> 16 not in (0x2000, 0x2001) or not reset & 1 or not c["base"] <= reset < c["base"] + ln:
        die(f"{path}: start-up vectors look wrong (stack {sp:#x}, reset {reset:#x})")
    if c["base"] + ln > c["limit"]:
        die(f"{path}: image is too large for the {c['name']}'s flash")
    ver = ""
    i = d.find(b"PN", off)
    while i >= 0 and not ver:
        s = d[i:i + 8].split(b"\0")[0]
        if 4 <= len(s) <= 7 and s[2:3].isdigit() and b"." in s:
            ver = s.decode("ascii", "replace")
        i = d.find(b"PN", i + 1)
    return unit, dict(bytes=len(d), payload=ln, name=name.decode("ascii", "replace"), version=ver or "(none found)",
                      sha256=hashlib.sha256(d).hexdigest())

def removable_disks():
    out = []
    for n in sorted(os.listdir("/sys/block")):
        try:
            if open(f"/sys/block/{n}/removable").read().strip() != "1":
                continue
            out.append((f"/dev/{n}", int(open(f"/sys/block/{n}/size").read()) * 512))
        except OSError:
            pass
    return out

def mounted_at(dev):
    real = os.path.realpath(dev)
    for line in open("/proc/mounts"):
        src, where = line.split()[:2]
        if src.startswith("/dev/") and os.path.realpath(src).startswith(real):
            return where
    return None

def pick_device(unit, dev):
    c = UNITS[unit]
    if dev is None:
        hits = [d for d, size in removable_disks() if size == c["dev_bytes"]]
        if len(hits) != 1:
            die(f"expected exactly one removable drive of {c['dev_bytes']} bytes, found {hits or 'none'}.\n"
                f"         Is the {c['name']} in update mode? ({c['how']})")
        dev = hits[0]
    if not os.path.exists(dev):
        die(f"{dev} does not exist")
    with open(dev, "rb") as f:
        size = f.seek(0, os.SEEK_END); f.seek(0); bs = f.read(4096)
    if size != c["dev_bytes"]:
        die(f"{dev} is {size} bytes; the {c['name']}'s update drive is {c['dev_bytes']}. Wrong disk?")
    if bs[0] not in (0xEB, 0xE9) or bs[3:11] != b"MSDOS5.0":
        die(f"{dev} does not carry the update drive's boot sector. Wrong disk?")
    where = mounted_at(dev)
    if where:
        die(f"{dev} is mounted at {where}; unmount it first:  udisksctl unmount -b {dev}")
    return dev

def confirm(unit, facts, dev):
    c = UNITS[unit]
    print(f"\n  unit     : {c['name']}\n  file     : {facts['file']}\n  version  : {facts['version']}   ({facts['bytes']} bytes)"
          f"\n  sha256   : {facts['sha256']}\n  drive    : {dev}  ({c['dev_bytes']} bytes, not mounted)\n")
    if input("  type yes to flash: ").strip().lower() != "yes":
        die("cancelled; nothing was written")

def main():
    if len(sys.argv) < 3 or sys.argv[1] not in ("check", "tx", "rx"):
        sys.exit(__doc__)
    cmd, path = sys.argv[1], sys.argv[2]
    dev = sys.argv[3] if len(sys.argv) > 3 else None
    unit, facts = inspect_image(path)
    facts["file"] = path
    if cmd == "check":
        print(f"{path}: a valid {UNITS[unit]['name']} update image, version {facts['version']}, "
              f"{facts['bytes']} bytes\nsha256 {facts['sha256']}")
        return
    if cmd != unit:
        die(f"{path} is a {UNITS[unit]['name']} image, but you asked to flash the {UNITS[cmd]['name']}. "
            "The two are not interchangeable.")
    if os.geteuid() != 0:
        die("run with sudo (reading the raw drive needs root)")
    dev = pick_device(unit, dev)
    if unit == "tx":
        if not shutil.which("mcopy"):
            die("mtools is not installed:  sudo pacman -S mtools")
        if facts["bytes"] > 454656:
            die("file is larger than the tester's update drive can hold")
        confirm(unit, facts, dev)
        r = subprocess.run(["mcopy", "-i", dev, path, "::"], env=dict(os.environ, MTOOLS_SKIP_CHECK="1"))
        os.sync()
        if r.returncode:
            die("mcopy reported an error. If the tester is unresponsive: press reset, hold M + Power, and run this again.")
        print("\nwritten. Unplug, power the tester on, and check Settings > About.\n"
              "If it does not boot: press reset, hold M + Power, and flash a known-good file with this same command.")
    else:
        fp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fatpush.py")
        if not os.path.exists(fp):
            die(f"fatpush.py must sit next to this script ({fp})")
        confirm(unit, facts, dev)
        subprocess.run([sys.executable, fp, dev, path, "--cluster", "4", "--steps", "D1 P SP POLL", "--write"])
        print("\n'DRIVE GONE' above means the probe took the file: unplug, power on, listen for the start-up sound.\n"
              "If the drive is still there, nothing changed on the probe; re-enter update mode and try again.")

if __name__ == "__main__":
    main()
