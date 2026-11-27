import subprocess, os
D = os.path.dirname(os.path.abspath(__file__))
def compile_blob(base):
    f = ["clang", "--target=thumbv7em-none-eabi", "-mcpu=cortex-m4", "-mfloat-abi=soft", "-O2", "-ffreestanding",
         "-fno-builtin", "-fno-pic", "-fno-jump-tables", "-Wall", "-c"]
    subprocess.check_call(f + [f"{D}/probe.c", "-o", f"{D}/probe.o"])
    subprocess.check_call(f + [f"{D}/entry.S", "-o", f"{D}/entry.o"])
    subprocess.check_call(["ld.lld", "-T", f"{D}/link.ld", f"--defsym=BASE={base:#x}", "-e", "_entry",
                           f"{D}/entry.o", f"{D}/probe.o", "-o", f"{D}/probe.elf"])
    out = subprocess.run(["llvm-objdump", "-h", f"{D}/probe.elf"], capture_output=True, text=True).stdout
    for line in out.splitlines():
        p = line.split()
        if len(p) > 2 and p[1] in (".data", ".bss"): assert int(p[2], 16) == 0, f"{p[1]} must be empty"
    assert not subprocess.run(["llvm-nm", "-u", f"{D}/probe.elf"], capture_output=True, text=True).stdout.strip()
    subprocess.check_call(["llvm-objcopy", "-O", "binary", "-j", ".text", f"{D}/probe.elf", f"{D}/probe.bin"])
    b = open(f"{D}/probe.bin", "rb").read()
    return b + b"\0" * (-len(b) % 4)
