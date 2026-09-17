"""Round-trip test: assemble -> disassemble with Capstone -> compare.

The assembler is only trustworthy if an independent disassembler agrees with
it, so every encoder here is checked against Capstone's view of the bytes.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lpm10a.thumb import assemble, verify, AsmError

ORG = 0x08067C98

# (source line, expected Capstone rendering)
CASES = [
    ("nop",                      "nop"),
    ("movs r0, #0",              "movs r0, #0"),
    ("movs r3, #255",            "movs r3, #0xff"),
    ("mov r1, r2",               "mov r1, r2"),
    ("mov r8, r0",               "mov r8, r0"),
    ("movw r0, #0x1234",         "movw r0, #0x1234"),
    ("movt r0, #0x2000",         "movt r0, #0x2000"),
    ("ldr r0, [r1]",             "ldr r0, [r1]"),
    ("ldr r2, [r3, #20]",        "ldr r2, [r3, #0x14]"),
    ("str r0, [r1, #4]",         "str r0, [r1, #4]"),
    ("ldrb r0, [r1, #7]",        "ldrb r0, [r1, #7]"),
    ("strb r5, [r2, #31]",       "strb r5, [r2, #0x1f]"),
    ("ldrh r0, [r1, #2]",        "ldrh r0, [r1, #2]"),
    ("strh r0, [r1, #0x28]",     "strh r0, [r1, #0x28]"),
    ("push {r4, lr}",            "push {r4, lr}"),
    ("push {r0, r1, r2}",        "push {r0, r1, r2}"),
    ("pop {r4, pc}",             "pop {r4, pc}"),
    ("bx lr",                    "bx lr"),
    ("blx r3",                   "blx r3"),
    ("cmp r0, #5",               "cmp r0, #5"),
    ("cmp r1, r2",               "cmp r1, r2"),
    ("adds r0, r1, #3",          "adds r0, r1, #3"),
    ("subs r0, r1, #1",          "subs r0, r1, #1"),
    ("adds r2, #16",             "adds r2, #0x10"),
    ("subs r2, #1",              "subs r2, #1"),
    ("add r0, r9",               "add r0, sb"),   # Capstone prints r9 as its alias "sb"
    ("lsls r0, r1, #4",          "lsls r0, r1, #4"),
    ("lsrs r0, r1, #31",         "lsrs r0, r1, #0x1f"),
    ("ands r0, r1",              "ands r0, r1"),
    ("orrs r0, r1",              "orrs r0, r1"),
    ("bics r0, r1",              "bics r0, r1"),
    # --- additions for the measurement / battery patches
    ("ldr r0, [sp]",             "ldr r0, [sp]"),
    ("ldr r3, [sp, #8]",         "ldr r3, [sp, #8]"),
    ("str r4, [sp]",             "str r4, [sp]"),
    ("str r1, [sp, #0x10]",      "str r1, [sp, #0x10]"),
    ("sub sp, #4",               "sub sp, #4"),
    ("add sp, #4",               "add sp, #4"),
    ("sub sp, #0x28",            "sub sp, #0x28"),
    ("adds r0, r1, r2",          "adds r0, r1, r2"),
    ("subs r6, r6, r0",          "subs r6, r6, r0"),
    ("rsbs r0, r0, #0",          "rsbs r0, r0, #0"),
    ("uxtb r6, r0",              "uxtb r6, r0"),
    ("uxth r0, r0",              "uxth r0, r0"),
    ("sxth r1, r2",              "sxth r1, r2"),
    ("sxtb r1, r2",              "sxtb r1, r2"),
    ("muls r0, r1, r0",          "muls r0, r1, r0"),
    ("mul r0, r0, r1",           "mul r0, r0, r1"),
    ("mls r4, r5, r4, r3",       "mls r4, r5, r4, r3"),
    ("udiv r5, r3, r4",          "udiv r5, r3, r4"),
    ("sdiv r0, r4, r1",          "sdiv r0, r4, r1"),
    ("udiv r0, r0, r1",          "udiv r0, r0, r1"),
]

fails = 0

print("=== single-instruction round trip ===")
for src, want in CASES:
    code = assemble(ORG, src)
    dis = verify(code, ORG)
    got = dis[0][2] if dis else "<undecodable>"
    ok = got == want
    fails += not ok
    print(f"  [{'ok' if ok else 'FAIL'}] {src:24} -> {code.hex():12} {got}"
          + ("" if ok else f"   (expected {want})"))

print("\n=== branches resolve to the right target ===")
BR = [
    ("b",   "b     0x%x" % (ORG + 0x20)),
    ("bl",  "bl    0x%x" % 0x0800F9C0),
    ("b.w", "b.w   0x%x" % (ORG - 0x1000)),
    ("beq", "beq   0x%x" % (ORG + 0x10)),
    ("cbz", "cbz   r0, 0x%x" % (ORG + 0x10)),
    ("cbnz","cbnz  r3, 0x%x" % (ORG + 0x40)),
]
for mn, src in BR:
    code = assemble(ORG, src)
    addr, hexs, text = verify(code, ORG)[0]
    want_target = int(src.split("0x")[1], 16)
    got_target = int(text.split("#")[-1].split("0x")[-1], 16) if "#" in text else None
    ok = got_target == want_target and text.split()[0] == mn.replace(".w", ".w")
    fails += not ok
    print(f"  [{'ok' if ok else 'FAIL'}] {src:28} -> {hexs:10} {text}")

print("\n=== literal pool ===")
src = """
        push {r4, lr}
        ldr  r0, =0x20000178
        ldr  r1, =0xDEADBEEF
        ldr  r2, =0x20000178
        movs r3, #0
        strh r3, [r0]
        pop  {r4, pc}
"""
code = assemble(ORG, src)
print(f"  {len(code)} bytes")
for a, hx, t in verify(code, ORG):
    print(f"    0x{a:08x}: {hx:10} {t}")
import struct
pool = [struct.unpack_from("<I", code, i)[0] for i in range(len(code) - 8, len(code), 4)]
ok = pool == [0x20000178, 0xDEADBEEF]
fails += not ok
print(f"  [{'ok' if ok else 'FAIL'}] pool deduplicated: {[hex(x) for x in pool]}")

print("\n=== labels and forward/backward refs ===")
src = """
top:
        movs r0, #0
        cmp  r0, #1
        beq  done
        b    top
done:
        bx   lr
"""
code = assemble(ORG, src)
dis = verify(code, ORG)
for a, hx, t in dis:
    print(f"    0x{a:08x}: {hx:10} {t}")
ok = (f"0x{ORG+8:x}" in dis[2][2]) and (f"0x{ORG:x}" in dis[3][2])
fails += not ok
print(f"  [{'ok' if ok else 'FAIL'}] beq->done, b->top resolved")

print("\n=== rejects what it does not understand ===")
for bad in ["frobnicate r0, r1", "movs r0, #256", "strh r0, [r1, #3]", "push {r4, r8}"]:
    try:
        assemble(ORG, bad)
        print(f"  [FAIL] {bad!r} was silently accepted")
        fails += 1
    except AsmError as e:
        print(f"  [ok]   {bad:26} rejected: {e}")

print("\n" + ("ALL TESTS PASSED" if not fails else f"{fails} FAILURE(S)"))
sys.exit(1 if fails else 0)
