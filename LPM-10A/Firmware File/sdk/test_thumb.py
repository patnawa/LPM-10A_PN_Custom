"""Round-trip test: assemble -> disassemble with Capstone -> compare.

The assembler is only trustworthy if an independent disassembler agrees with
it, so every encoder here is checked against Capstone's view of the bytes.
"""
import sys, os
import struct
import unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lpm10a.thumb import assemble, verify, AsmError

ORG = 0x08067C98

# (source line, expected Capstone rendering)
CASES = [
    ("nop",                      "nop"),
    ("mrs r3, primask",           "mrs r3, primask"),
    ("msr primask, r3",           "msr primask, r3"),
    ("mrs r0, msp",               "mrs r0, msp"),
    ("mrs r1, psp",               "mrs r1, psp"),
    ("mrs r2, ipsr",              "mrs r2, ipsr"),
    ("cpsid i",                   "cpsid i"),
    ("cpsie i",                   "cpsie i"),
    ("dsb",                      "dsb sy"),
    ("isb",                      "isb sy"),
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
    ("lsrs r0, r1, #32",         "lsrs r0, r1, #0x20"),
    ("lsls r0, r1, #0",          "movs r0, r1"),
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

BR = [
    ("b",   "b     0x%x" % (ORG + 0x20)),
    ("bl",  "bl    0x%x" % 0x0800F9C0),
    ("b.w", "b.w   0x%x" % (ORG - 0x1000)),
    ("beq", "beq   0x%x" % (ORG + 0x10)),
    ("cbz", "cbz   r0, 0x%x" % (ORG + 0x10)),
    ("cbnz","cbnz  r3, 0x%x" % (ORG + 0x40)),
]


class ThumbTests(unittest.TestCase):
    def test_single_instruction_round_trip(self):
        for source, expected in CASES:
            with self.subTest(source=source):
                code = assemble(ORG, source)
                dis = verify(code, ORG)
                self.assertEqual(len(dis), 1)
                self.assertEqual(dis[0][2], expected)
                self.assertEqual(len(bytes.fromhex(dis[0][1])), len(code))

    def test_branches_reach_the_requested_target(self):
        for mnemonic, source in BR:
            with self.subTest(source=source):
                text = verify(assemble(ORG, source), ORG)[0][2]
                self.assertEqual(text.split()[0], mnemonic)
                self.assertEqual(int(text.split("#")[-1], 16),
                                 int(source.split("0x")[1], 16))

    def test_literal_pool_deduplicated_and_loads_reach_it(self):
        code = assemble(ORG, """
            push {r4, lr}
            ldr r0, =0x20000178
            ldr r1, =0xDEADBEEF
            ldr r2, =0x20000178
            movs r3, #0
            strh r3, [r0]
            pop {r4, pc}
        """)
        self.assertEqual(struct.unpack_from("<II", code, len(code) - 8),
                         (0x20000178, 0xDEADBEEF))
        for offset, expected in ((2, 0x20000178), (4, 0xDEADBEEF), (6, 0x20000178)):
            opcode = struct.unpack_from("<H", code, offset)[0]
            target = ((ORG + offset + 4) & ~3) + (opcode & 255) * 4
            self.assertEqual(struct.unpack_from("<I", code, target - ORG)[0], expected)

    def test_labels_and_forward_backward_references(self):
        code = assemble(ORG, """
        top:
            movs r0, #0
            cmp r0, #1
            beq done
            b top
        done:
            bx lr
        """)
        dis = verify(code, ORG)
        self.assertEqual(dis[2][2], f"beq #0x{ORG + 8:x}")
        self.assertEqual(dis[3][2], f"b #0x{ORG:x}")

    def test_invalid_operands_are_rejected_instead_of_misassembled(self):
        for source in (
            "frobnicate r0, r1", "movs r0, #256", "strh r0, [r1, #3]",
            "push {r4, r8}", "push {r0, r0}", "pop {r2, r2}",
            "push {r0-r3, r2}", "push {r3-r0}", "pop {}",
            "movw r0, #65536", "movt r0, #-1", "lsrs r0, r1, #0",
            "lsrs r0, r1, #33", "lsls r0, r1, #32",
        ):
            with self.subTest(source=source), self.assertRaises(AsmError):
                assemble(ORG, source)

    def test_invalid_layout_cannot_corrupt_branch_targets(self):
        for directive in (".space -2", ".space", ".align 0", ".align -4", ".align 3"):
            with self.subTest(directive=directive), self.assertRaises(AsmError):
                assemble(ORG, f"b target\n{directive}\ntarget: bx lr")
        with self.assertRaises(AsmError):
            assemble(ORG, "target: nop\nb target\ntarget: bx lr")

    def test_unsupported_addressing_and_extra_operands_are_rejected(self):
        # A post-index store must not silently become a non-updating store.
        # Likewise a three-register ALU operation must not become a two-register
        # operation with a different destination/input relationship.
        for source in (
            "str r0, [r1], #4", "ldr r0, [r1], #4",
            "ands r0, r1, r2", "orrs r0, r1, r2",
            "mov r0, r1, r2", "cmp r0, r1, r2", "nop r0",
            "movs r0, #1, #2", "adds r0, #1, #2, #3",
            "mul r0, r1, r2, r3", "mls r0, r1, r2, r3, r4",
            "b 0x08067ca0, r0", "bx lr, r0", "mrs r0, primask, r1",
        ):
            with self.subTest(source=source), self.assertRaises(AsmError):
                assemble(ORG, source)

    def test_missing_operands_raise_assembly_errors(self):
        for source in (
            "mov", "mov r0", "str r0", "mul r0, r1", "mls r0, r1, r2",
            "b", "bx", "mrs r0", "cbz r0", "mov r0, r1,",
            "mov r0,, r1", "str r0, [r1",
        ):
            with self.subTest(source=source), self.assertRaises(AsmError):
                assemble(ORG, source)

    def test_valid_alignment_keeps_branch_target_on_instruction(self):
        for alignment in (2, 4, 8, 16):
            with self.subTest(alignment=alignment):
                code = assemble(ORG, f"b target\n.align {alignment}\ntarget: bx lr")
                target = int(verify(code[:2], ORG)[0][2].split("#")[-1], 16)
                self.assertEqual(target % alignment, 0)
                self.assertEqual(code[target - ORG:], bytes.fromhex("7047"))


if __name__ == "__main__":
    unittest.main()
