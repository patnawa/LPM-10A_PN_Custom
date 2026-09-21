"""Write the stock RX file to D:\\<name> one 2048-byte sector at a time, unbuffered + write-through,
with a delay between sectors so each USB write can be correlated with SRAM changes."""
import ctypes as c, sys, time
from ctypes import wintypes as w
from datetime import datetime

name, delay = sys.argv[1], float(sys.argv[2])
if len(sys.argv) < 4:
    raise SystemExit("usage: rx_slow_copy.py <name on D:> <delay s> <file>  (0 delay = continuous; any pause makes the bootloader give up with APPRUN)")
fw = open(sys.argv[3], "rb").read()
k = c.WinDLL("kernel32", use_last_error=True)
k.CreateFileW.restype = w.HANDLE
k.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, c.c_void_p, w.DWORD, w.DWORD, w.HANDLE]
k.VirtualAlloc.restype = c.c_void_p
k.VirtualAlloc.argtypes = [c.c_void_p, c.c_size_t, w.DWORD, w.DWORD]
GENERIC_WRITE, CREATE_ALWAYS = 0x40000000, 2
FLAGS = 0x20000000 | 0x80000000  # NO_BUFFERING | WRITE_THROUGH
h = k.CreateFileW(f"D:\\{name}", GENERIC_WRITE, 0, None, CREATE_ALWAYS, FLAGS, None)
if h in (None, w.HANDLE(-1).value):
    raise SystemExit(f"create failed {c.get_last_error()}")
print("created", datetime.now().strftime("%H:%M:%S.%f"), flush=True)
time.sleep(delay)
SEC = 2048
buf = k.VirtualAlloc(None, SEC, 0x3000, 0x04)
total = (len(fw) + SEC - 1) // SEC * SEC
for off in range(0, total, SEC):
    chunk = fw[off:off + SEC].ljust(SEC, b"\0")
    c.memmove(buf, chunk, SEC)
    n = w.DWORD()
    ok = k.WriteFile(h, c.c_void_p(buf), SEC, c.byref(n), None)
    print(f"{datetime.now().strftime('%H:%M:%S.%f')} sector {off // SEC:2d} off 0x{off:05X} ok={bool(ok)} n={n.value} err={c.get_last_error()}", flush=True)
    if not ok:
        break
    if delay:
        time.sleep(delay)
# set the exact size: reopen buffered and truncate
k.CloseHandle(h)
time.sleep(delay)
h2 = k.CreateFileW(f"D:\\{name}", GENERIC_WRITE, 0, None, 3, 0x80000000, None)
k.SetFilePointerEx.argtypes = [w.HANDLE, c.c_longlong, c.c_void_p, w.DWORD]
k.SetEndOfFile.argtypes = [w.HANDLE]
if h2 not in (None, w.HANDLE(-1).value):
    k.SetFilePointerEx(h2, len(fw), None, 0)
    k.SetEndOfFile(h2)
    k.CloseHandle(h2)
else:
    print("reopen failed", c.get_last_error())
print("truncated to", len(fw), datetime.now().strftime("%H:%M:%S.%f"), flush=True)
