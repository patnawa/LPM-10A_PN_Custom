#!/usr/bin/env python3
"""fatpush.py - write one file onto a small FAT12/FAT16 USB "bootloader" drive by
talking to the raw block device, emitting the sector writes in the order the
Windows FAT driver uses for an ordinary file copy:

    directory entry (size 0) -> FAT chain -> directory entry (cluster + size)
    -> file data in one burst -> directory entry again

Without --write it only reads the drive and prints the plan.

    sudo python3 fatpush.py /dev/sdX firmware-update.bin            # dry run
    sudo python3 fatpush.py /dev/sdX firmware-update.bin --write
"""
import argparse, fcntl, mmap, os, stat, struct, sys, time

BLKSSZGET = 0x1268
MAX_DEV = 256 * 1024 * 1024


def die(msg):
    sys.exit("fatpush: " + msg)


class Dev:
    def __init__(self, path, direct, writable):
        self.path = path
        st = os.stat(path)
        self.is_blk = stat.S_ISBLK(st.st_mode)
        flags = (os.O_RDWR | os.O_SYNC) if writable else os.O_RDONLY
        if direct:
            flags |= os.O_DIRECT
        self.fd = os.open(path, flags)
        self.size = os.lseek(self.fd, 0, os.SEEK_END)
        self.lbs = 512
        if self.is_blk:
            self.lbs = struct.unpack("i", fcntl.ioctl(self.fd, BLKSSZGET, b"\0" * 4))[0]

    def _pad(self, n):
        return (n + self.lbs - 1) // self.lbs * self.lbs

    def read(self, off, n):
        m = mmap.mmap(-1, self._pad(n))
        got = os.preadv(self.fd, [m], off)
        if got < n:
            die(f"short read at {off}: {got} of {n}")
        return bytes(m[:n])

    def write(self, off, data):
        if len(data) % self.lbs or off % self.lbs:
            die("internal: unaligned write")
        m = mmap.mmap(-1, len(data))
        m.write(data)
        done = os.pwrite(self.fd, m, off)
        if done != len(data):
            die(f"short write at {off}: {done} of {len(data)}")


def mounted(path):
    real = os.path.realpath(path)
    with open("/proc/mounts") as f:
        for line in f:
            src = line.split()[0]
            if src.startswith("/dev/") and os.path.realpath(src).startswith(real):
                return line.split()[1]
    return None


def lfn_checksum(sfn):
    s = 0
    for b in sfn:
        s = (((s & 1) << 7) + (s >> 1) + b) & 0xFF
    return s


def short_83(name):
    """The 11-byte directory form of a name that is already a plain upper-case 8.3 name, else None."""
    base, dot, ext = name.partition(".")
    ok = lambda t: t and t == t.upper() and all(c.isalnum() or c in "_-~" for c in t)
    if ok(base) and len(base) <= 8 and (not dot or (ok(ext) and len(ext) <= 3)):
        return base.ljust(8).encode("ascii") + ext.ljust(3).encode("ascii")
    return None


def make_sfn(name, existing):
    plain = short_83(name)
    if plain and plain not in existing:
        return plain
    base, _, ext = name.rpartition(".")
    if not base:
        base, ext = name, ""
    ok = lambda c: c.isalnum() or c in "_-~!#$%&'()@^`{}"
    b = "".join(c for c in base.upper() if ok(c))
    e = "".join(c for c in ext.upper() if ok(c))[:3]
    for n in range(1, 10):
        sfn = (b[:6] + f"~{n}").ljust(8).encode("ascii") + e.ljust(3).encode("ascii")
        if sfn not in existing:
            return sfn
    die("no free short name")


def dos_time(t):
    lt = time.localtime(t)
    d = ((lt.tm_year - 1980) << 9) | (lt.tm_mon << 5) | lt.tm_mday
    tm = (lt.tm_hour << 11) | (lt.tm_min << 5) | (lt.tm_sec // 2)
    return d, tm


def dir_entries(name, sfn, cluster, size, now):
    """LFN entries (last first) followed by the 8.3 entry, as Windows writes them."""
    if sfn == short_83(name):
        d, tm = dos_time(now)
        return (sfn + b"\x20\x00\x00" + struct.pack("<HHHH", tm, d, d, 0) +
                struct.pack("<HHHI", tm, d, cluster, size))
    u = name.encode("utf-16-le")
    chars = [u[i:i + 2] for i in range(0, len(u), 2)]
    if len(chars) % 13:
        chars.append(b"\x00\x00")
        while len(chars) % 13:
            chars.append(b"\xff\xff")
    n = len(chars) // 13
    csum = lfn_checksum(sfn)
    out = b""
    for seq in range(n, 0, -1):
        part = b"".join(chars[(seq - 1) * 13: seq * 13])
        order = seq | (0x40 if seq == n else 0)
        out += (bytes([order]) + part[0:10] + b"\x0f\x00" + bytes([csum]) +
                part[10:22] + b"\x00\x00" + part[22:26])
    d, tm = dos_time(now)
    out += (sfn + b"\x20\x00\x00" + struct.pack("<HHHH", tm, d, d, 0) +
            struct.pack("<HHHI", tm, d, cluster, size))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("device")
    ap.add_argument("file")
    ap.add_argument("--write", action="store_true", help="actually write (default: dry run)")
    ap.add_argument("--name", help="file name to use on the drive (default: the file's own name)")
    ap.add_argument("--seq", choices=["dirdata", "datafirst", "windows", "simple"], default="dirdata",
                    help="dirdata: dir, data, wait, FAT, dir.  datafirst: data, wait, dir, FAT.  "
                         "windows: dir(size 0), FAT, dir, data, dir.  simple: dir, FAT, data")
    ap.add_argument("--label", default="BOOTLOADER", help="volume label the drive must carry")
    ap.add_argument("--steps", help="custom write sequence, space separated, replacing --seq. "
                    "D0 dir entry (size 0)  D1 dir entry (cluster+size)  F1 F2 FAT copies  "
                    "DATA whole file in one write  H first data sector only  REST the other data sectors in one write  "
                    "S whole file one sector per write  SP the same with a status read after every sector  SREST the other sectors one per write  "
                    "W<ms> pause  P read the status file once  POLL watch the status file for 2 s")
    ap.add_argument("--cluster", type=int, metavar="N",
                    help="put the file at this cluster instead of the first free one (2 is the first data cluster)")
    ap.add_argument("--gap", type=int, default=0, metavar="MS",
                    help="with S / SP / SREST: pause this many ms after each data sector")
    ap.add_argument("--stale-ok", action="store_true",
                    help="write even if the drive already shows UNKOWN/APPRUN from an earlier attempt")
    ap.add_argument("--no-direct", action="store_true", help="do not use O_DIRECT (for testing on image files)")
    a = ap.parse_args()

    print("fatpush v8")
    payload = open(a.file, "rb").read()
    name = a.name or os.path.basename(a.file)
    if not payload:
        die("file is empty")

    m = mounted(a.device)
    if m:
        die(f"{a.device} is mounted at {m}; unmount it first (udisksctl unmount -b {a.device})")

    dev = Dev(a.device, not a.no_direct, a.write)
    if dev.size > MAX_DEV:
        die(f"{a.device} is {dev.size >> 20} MiB; refusing anything over {MAX_DEV >> 20} MiB")

    bs = dev.read(0, 512)
    if bs[0] not in (0xEB, 0xE9) or struct.unpack_from("<H", bs, 11)[0] not in (512, 1024, 2048, 4096):
        die("first sector does not look like a FAT boot sector")
    if bs[510:512] != b"\x55\xaa":
        print("note        : boot sector has no 55 AA signature (some bootloader drives omit it); continuing")
    bps, spc, rsvd, nfats, rootent, tot16, _media, fatsz = struct.unpack_from("<HBHBHHBH", bs, 11)
    tot = tot16 or struct.unpack_from("<I", bs, 32)[0]
    if bps == 0 or spc == 0 or fatsz == 0 or rootent == 0 or nfats == 0:
        die("not FAT12/FAT16 (FAT32 or invalid BPB)")
    if bps % dev.lbs:
        die(f"filesystem sector size {bps} does not fit device block size {dev.lbs}")
    root_lba = rsvd + nfats * fatsz
    root_secs = (rootent * 32 + bps - 1) // bps
    data_lba = root_lba + root_secs
    nclus = (tot - data_lba) // spc
    fat16 = nclus >= 4085
    csize = bps * spc

    root = bytearray(dev.read(root_lba * bps, root_secs * bps))
    fat = bytearray(dev.read(rsvd * bps, fatsz * bps))

    label = bs[43:54].decode("ascii", "replace").strip()
    names, sfns, free_at = [], set(), None
    need_clu = (len(payload) + csize - 1) // csize
    for i in range(rootent):
        e = root[i * 32:(i + 1) * 32]
        if e[0] == 0x00:
            if free_at is None:
                free_at = i
            break
        if e[0] == 0xE5:
            continue
        if e[11] == 0x0F:
            continue
        if e[11] & 0x08:
            label = e[0:11].decode("ascii", "replace").strip()
            continue
        sfns.add(bytes(e[0:11]))
        names.append((e[0:8].decode("ascii", "replace").strip() + "." +
                      e[8:11].decode("ascii", "replace").strip(),
                      struct.unpack_from("<I", e, 28)[0], struct.unpack_from("<H", e, 26)[0]))

    def fat_get(c):
        if fat16:
            return struct.unpack_from("<H", fat, c * 2)[0]
        v = struct.unpack_from("<H", fat, c * 3 // 2)[0]
        return v >> 4 if c & 1 else v & 0xFFF

    def fat_set(c, v):
        if fat16:
            struct.pack_into("<H", fat, c * 2, v)
            return
        o = c * 3 // 2
        cur = struct.unpack_from("<H", fat, o)[0]
        cur = (cur & 0x000F) | (v << 4) if c & 1 else (cur & 0xF000) | (v & 0xFFF)
        struct.pack_into("<H", fat, o, cur)

    first = None
    for c in range(2, nclus + 2 - need_clu + 1):
        if all(fat_get(c + k) == 0 for k in range(need_clu)):
            first = c
            break

    if a.cluster is not None:
        if a.cluster < 2 or a.cluster + need_clu > nclus + 2:
            die("--cluster out of range")
        if any(fat_get(a.cluster + k) for k in range(need_clu)):
            die("--cluster: those clusters are in use")
        first = a.cluster

    print(f"device      : {a.device}  {dev.size} bytes, block size {dev.lbs}")
    print(f"filesystem  : {'FAT16' if fat16 else 'FAT12'}  label '{label}'  {bps} B/sector, "
          f"{spc} sectors/cluster ({csize} B), {nfats} FAT(s) x {fatsz} sectors, {nclus} clusters")
    print(f"layout      : FAT at LBA {rsvd}, root dir at LBA {root_lba} ({rootent} entries), data at LBA {data_lba}")
    print("root dir    : " + (", ".join(f"{n} ({s} B, cluster {c})" for n, s, c in names) or "(empty)"))
    print(f"file        : {name}  {len(payload)} bytes -> {need_clu} cluster(s)")

    if label.upper() != a.label.upper():
        die(f"volume label is '{label}', expected '{a.label}'; wrong drive? (override with --label)")
    stale = [n for n, _, _ in names if n.upper().startswith(("UNKOWN", "APPRUN"))]
    if stale and a.write and not a.stale_ok:
        die(f"the drive already shows {stale[0]} from an earlier attempt; unplug, re-enter update mode "
            "(hold SCAN while plugging in) and run again")
    if free_at is None:
        die("no free root directory slot found")
    if first is None:
        die("no contiguous free space")

    sfn = make_sfn(name, sfns)
    now = time.time()
    ents_final = dir_entries(name, sfn, first, len(payload), now)
    ents_empty = dir_entries(name, sfn, 0, 0, now)
    nent = len(ents_final) // 32
    if free_at + nent > rootent:
        die("root directory is full")

    eoc = 0xFFFF if fat16 else 0xFFF
    for k in range(need_clu):
        fat_set(first + k, eoc if k == need_clu - 1 else first + k + 1)
    fbytes = 2 if fat16 else 1.5
    fs0 = int(first * fbytes) // bps
    fs1 = int((first + need_clu) * fbytes + 1) // bps
    fat_chunk = bytes(fat[fs0 * bps:(fs1 + 1) * bps])

    ds0 = free_at * 32 // bps
    ds1 = ((free_at + nent) * 32 - 1) // bps

    def root_chunk(ents):
        r = bytearray(root)
        r[free_at * 32: free_at * 32 + len(ents)] = ents
        return bytes(r[ds0 * bps:(ds1 + 1) * bps])

    data = payload + b"\0" * (-len(payload) % bps)
    data_at = data_lba + (first - 2) * spc

    D0 = ("dir entry, size 0", root_lba + ds0, root_chunk(ents_empty))
    D1 = ("dir entry, cluster + size", root_lba + ds0, root_chunk(ents_final))
    F = [(f"FAT {i + 1} chain", rsvd + i * fatsz + fs0, fat_chunk) for i in range(nfats)]
    DATA = ("file data", data_at, data)
    WAIT = ("wait 1.5 s and see whether the drive is still there", None, None)
    plan = {"dirdata": [D1, DATA, WAIT, *F, D1],
            "datafirst": [DATA, WAIT, D1, *F],
            "windows": [D0, *F, D1, DATA, D1],
            "simple": [D1, *F, DATA]}[a.seq]

    def status():
        r = dev.read(root_lba * bps, bps)
        return ", ".join(r[i:i + 8].decode("ascii", "replace").strip() + "." + r[i + 8:i + 11].decode("ascii", "replace").strip()
                         for i in range(0, 64, 32) if r[i] not in (0, 0xE5) and not r[i + 11] & 0x08 and r[i + 11] != 0x0F) or "(none)"

    if a.steps:
        nsec = len(data) // bps
        sect = lambda i: (f"data sector {i}", data_at + i, data[i * bps:(i + 1) * bps])
        plan = []
        for tok in a.steps.upper().split():
            if tok == "D0": plan.append(D0)
            elif tok == "D1": plan.append(D1)
            elif tok in ("F1", "F2"):
                if int(tok[1]) > nfats: die(f"drive has no {tok}")
                plan.append(F[int(tok[1]) - 1])
            elif tok == "DATA": plan.append(DATA)
            elif tok == "H": plan.append(("first data sector (container header)", data_at, data[:bps]))
            elif tok == "REST": plan.append((f"data sectors 1..{nsec - 1}", data_at + 1, data[bps:]))
            elif tok == "S":
                for i in range(nsec):
                    plan.append(sect(i))
                    if a.gap: plan.append((f"pause {a.gap} ms", None, a.gap))
            elif tok == "SP":
                for i in range(nsec):
                    plan.append(sect(i)); plan.append(("read status", None, "P"))
                    if a.gap: plan.append((f"pause {a.gap} ms", None, a.gap))
            elif tok == "SREST": plan.extend(sect(i) for i in range(1, nsec))
            elif tok == "P": plan.append(("read status", None, "P"))
            elif tok == "POLL": plan.append(("watch status for 2 s", None, "POLL"))
            elif tok[0] == "W" and tok[1:].isdigit(): plan.append((f"pause {tok[1:]} ms", None, int(tok[1:])))
            else: die(f"unknown step {tok!r}")
        a.seq = "custom"
    print(f"plan ({a.seq}) : short name {sfn.decode()!r}, first cluster {first}")
    for what, lba, buf in plan:
        if lba is None:
            print(f"   {what}")
        else:
            print(f"   LBA {lba:6d}  {len(buf) // bps:4d} sector(s)  {what}")
    if dev.is_blk:
        try:
            q = f"/sys/block/{os.path.basename(os.path.realpath(a.device))}/queue/max_sectors_kb"
            kb = int(open(q).read())
            print(f"note        : kernel sends at most {kb} KiB per write command; file data is {len(data) // 1024} KiB"
                  + ("" if kb * 1024 >= len(data) else "  (WILL BE SPLIT)"))
        except (OSError, ValueError):
            pass

    if not a.write:
        print("dry run only; add --write to do it")
        return

    t0 = time.monotonic()
    step = None
    try:
        for step, lba, buf in plan:
            ms = lambda: f"+{(time.monotonic() - t0) * 1000:.0f} ms"
            if lba is None and buf is None:
                time.sleep(1.5)
                dev.read(0, 512)
                print("   drive still present after the data; sending the remaining metadata")
                continue
            if lba is None and buf == "P":
                print(f"   status: {status()}  ({ms()})")
                continue
            if lba is None and buf == "POLL":
                last, end = None, time.monotonic() + 2.0
                while time.monotonic() < end:
                    cur = status()
                    if cur != last:
                        print(f"   status: {cur}  ({ms()})")
                        last = cur
                    time.sleep(0.05)
                continue
            if lba is None:
                time.sleep(buf / 1000)
                continue
            dev.write(lba * bps, buf)
            print(f"   wrote {step}  (+{(time.monotonic() - t0) * 1000:.0f} ms)")
    except OSError as e:
        print(f"   DRIVE GONE at '{step}' (+{(time.monotonic() - t0) * 1000:.0f} ms): {e.strerror}")
        print("the bootloader closed USB: either it took the file and restarted, or it gave up (APPRUN)")
        return
    print("all writes accepted; checking the drive again in 1.5 s")
    time.sleep(1.5)
    try:
        r = dev.read(root_lba * bps, bps)
    except OSError:
        print("drive is gone: the bootloader has taken the file and restarted")
        return
    now_names = [r[i:i + 8].decode("ascii", "replace").strip() + "." + r[i + 8:i + 11].decode("ascii", "replace").strip()
                 for i in range(0, 64, 32) if r[i] not in (0, 0xE5) and not r[i + 11] & 0x08 and r[i + 11] != 0x0F]
    print("drive still present; status file now: " + (", ".join(now_names) or "(none)"))


if __name__ == "__main__":
    main()
