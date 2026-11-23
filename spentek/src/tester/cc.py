import subprocess, sys, os
D = os.path.dirname(os.path.abspath(__file__))
def compile_blob(base):
    f = ["clang", "--target=thumbv7em-none-eabi", "-mcpu=cortex-m4", "-mfloat-abi=soft", "-Oz", "-ffreestanding",
         "-fno-builtin", "-fno-pic", "-fno-jump-tables", "-Wall", "-c"]
    subprocess.check_call(f + [f"{D}/tetris.c", "-o", f"{D}/tetris.o"])
    subprocess.check_call(f + [f"{D}/entry.S", "-o", f"{D}/entry.o"])
    subprocess.check_call(["ld.lld", "-T", f"{D}/link.ld", f"--defsym=BASE={base:#x}", "--gc-sections", "-e", "_entry",
                           f"{D}/entry.o", f"{D}/tetris.o", "-o", f"{D}/tetris.elf", "-Map", f"{D}/tetris.map"])
    out = subprocess.run(["llvm-objdump", "-h", f"{D}/tetris.elf"], capture_output=True, text=True).stdout
    for name in (".data", ".bss"):
        for line in out.splitlines():
            p = line.split()
            if len(p) > 2 and p[1] == name: assert int(p[2], 16) == 0, f"{name} must be empty"
    und = subprocess.run(["llvm-nm", "-u", f"{D}/tetris.elf"], capture_output=True, text=True).stdout.strip()
    assert not und, und
    subprocess.check_call(["llvm-objcopy", "-O", "binary", "-j", ".text", f"{D}/tetris.elf", f"{D}/tetris.bin"])
    b = open(f"{D}/tetris.bin", "rb").read()
    return b + b"\0" * (-len(b) % 4)
if __name__ == "__main__":
    b = compile_blob(int(sys.argv[1], 16)); print(len(b), "bytes")
