"""Instruction-level regressions for the opt-in TX roadmap candidate."""
import struct
import unittest
from pathlib import Path
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm_const import *
from lpm10a.image import Image
from build import STOCK
from audit_flash_length import Machine, STOP
import patches
from roadmap import PATCHES


def build_candidate():
    img = Image(STOCK)
    for patch in patches.REGISTRY:
        if patch.default or patch.pid in PATCHES:
            patch(img)
    img.finalize()
    return img


class Roadmap(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.img = build_candidate()
        cls.data = bytes(cls.img.data)

    def machine(self, state=7):
        return Machine(self.data, state)

    def read32(self, m, addr):
        return int.from_bytes(m.uc.mem_read(addr, 4), "little")

    def write32(self, m, addr, n):
        m.uc.mem_write(addr, struct.pack("<I", n))

    def test_candidate_matches_disk(self):
        path = Path(__file__).resolve().parent.parent / "experimental/LPM-10A-TX_PN2.9-roadmap.bin"
        self.assertEqual(path.read_bytes(), self.data)

    def test_events_init_and_every_tick_path(self):
        state = self.img.events["state"]
        for screen in (0, 1, 5, 6, 7, 8, 10):
            m = self.machine(screen)
            m.uc.mem_write(state, b"\xA5" * 12)
            m.call(self.img.events["init"])
            self.assertEqual(bytes(m.uc.mem_read(state, 12)), bytes(12))
            self.assertEqual(self.read32(m, 0xE000ED24) & 0x70000, 0x70000)
            calls = []
            for _, function, _ in self.img.events["calls"]:
                m.handlers[function] = lambda machine, f=function: (calls.append((f, machine.arg(0))), machine.ret())
            m.handlers[0x080130A8] = lambda machine: machine.ret(0)
            for tick in range(2000):
                m.call(0x0801BC70)
            self.assertEqual(calls, [], "no application callback is allowed in SysTick")
            flags = self.read32(m, state)
            expected = 1 | (1 << 3) | (1 << 4) | (1 << 5)
            if screen == 5:
                expected |= 1 << 1
            if screen == 8:
                expected |= 1 << 2
            if screen == 6:
                expected |= 1 << 6
            if screen not in (0, 1):
                expected |= (1 << 7) | (1 << 8) | (1 << 9)
            self.assertEqual(flags, expected, screen)
            m.call(self.img.events["poll"])
            self.assertEqual(len(calls), expected.bit_count())
            self.assertEqual(self.read32(m, state), 0)
            self.assertEqual(self.read32(m, state+4), 1)

    def test_publication_and_drain_preserve_masks_and_new_events(self):
        state = self.img.events["state"]
        for mask in (0, 1):
            m = self.machine()
            m.uc.reg_write(UC_ARM_REG_PRIMASK, mask)
            for n, producer in enumerate(self.img.events["producers"]):
                m.call(producer)
                self.assertEqual(m.uc.reg_read(UC_ARM_REG_PRIMASK), mask)
                self.assertEqual(self.read32(m, state), (1 << (n+1))-1)
            for _, f, _ in self.img.events["calls"]:
                m.handlers[f] = lambda machine: machine.ret()
            def arrived(machine):
                self.write32(machine, state, 1 << 7)
                machine.ret()
            m.handlers[0x08010EA8] = arrived
            m.call(self.img.events["poll"])
            self.assertEqual(self.read32(m, state), 1 << 7)
            self.assertEqual(m.uc.reg_read(UC_ARM_REG_PRIMASK), mask)

    def test_normal_dispatch_cadences_are_preserved(self):
        from collections import Counter
        m = self.machine(6)
        counts = Counter()
        for _, function, _ in self.img.events["calls"]:
            def record(machine, f=function):
                counts[(f, machine.arg(0) if f != 0x0800DD34 else None)] += 1
                machine.ret()
            m.handlers[function] = record
        m.handlers[0x080130A8] = lambda machine: machine.ret(0)
        for _ in range(2000):
            m.call(0x0801BC70)
            m.call(self.img.events["poll"])
        self.assertEqual(counts, {(0x08010EA8, 4): 2, (0x0800DD34, None): 2,
                                 (0x0800E428, 60): 1, (0x08013F94, 6): 1,
                                 (0x08012FBC, 8): 4, (0x08013DCC, 1): 200,
                                 (0x080131B0, 1): 4, (0x0800E428, 4): 2})

    def test_worker_creation_and_failure(self):
        for result in (1, 0xFFFFFFFF):
            m = self.machine()
            calls = []
            def create(machine):
                sp = machine.uc.reg_read(UC_ARM_REG_SP)
                self.assertEqual(machine.arg(0), self.img.events["worker"] | 1)
                self.assertEqual(machine.arg(2), 512)
                self.assertEqual(self.read32(machine, sp), 2)
                self.assertEqual(self.read32(machine, sp+4), 0)
                machine.ret(result)
            m.handlers[0x0801CD1C] = create
            m.handlers[0x0801C7D4] = lambda machine: (calls.append("scheduler"), machine.ret())
            if result == 1:
                m.call(self.img.events["create"])
                self.assertEqual(calls, ["scheduler"])
                self.assertEqual(m.uc.reg_read(UC_ARM_REG_SP), 0x2000E000)
            else:
                with self.assertRaises(RuntimeError):
                    m.call(self.img.events["create"], count=200)
                self.assertEqual(calls, [])
            self.assertEqual(self.read32(m, self.img.events["state"]+8), 1)

    def test_watchdog_needs_new_task_progress(self):
        m = self.machine()
        feeds = []
        m.handlers[0x080169A8] = lambda machine: (feeds.append(1), machine.ret())
        state = self.img.events["state"]
        m.call(self.img.watchdog)
        self.assertEqual(len(feeds), 1)  # pre-scheduler boot
        self.write32(m, state+8, 1)
        for _ in range(5):
            m.call(self.img.watchdog)
        self.assertEqual(len(feeds), 1)
        self.write32(m, state+4, 1)
        m.call(self.img.watchdog)
        m.call(self.img.watchdog)
        self.assertEqual(len(feeds), 2)
        self.assertEqual(self.read32(m, state+4), 0)

    def test_save_on_actual_length_exit_and_only_if_changed(self):
        for old_state in (2, 6, 7, 9):
            for new_state in (0, 2, 6, 7, 9, 12, 255):
                for field in (None, 0xA6, 0xA7, 0xC5):
                    m = self.machine(old_state)
                    settings = bytearray((i*7) & 255 for i in range(200))
                    m.uc.mem_write(0x0807F800, bytes(settings))
                    if field is not None:
                        settings[field] ^= 1
                    m.uc.mem_write(0x20000C78, bytes(settings))
                    saves = []
                    m.handlers[self.img.autosave["save"]] = lambda machine: (saves.append(1), machine.ret())
                    m.call(0x0800F77C, new_state, until=0x0800F780)
                    self.assertEqual(bool(saves), old_state == 7 and 0 < new_state < 12 and new_state != 7 and field is not None)
                    self.assertEqual(m.uc.reg_read(UC_ARM_REG_R4), new_state)
                    self.assertEqual(m.uc.reg_read(UC_ARM_REG_SP), 0x2000E000-24)

    def test_flash_save_uses_owned_buffer_and_serializes_writers(self):
        m = self.machine()
        settings = bytes(range(200))
        m.uc.mem_write(0x20000C78, settings)
        sequence = []
        for f, name in ((0x0801C844, "suspend"), (0x080156FC, "unlock"),
                        (0x08015690, "lock"), (0x0801D01C, "resume")):
            m.handlers[f] = lambda machine, n=name: (sequence.append(n), machine.ret())
        def erase(machine):
            self.assertEqual(machine.arg(0), 0x0807F800)
            sequence.append("erase")
            machine.uc.mem_write(0x0807F800, b"\xff"*204)
            machine.ret(6)
        def program(machine):
            self.assertGreaterEqual(machine.arg(0), 0x0807F800)
            self.assertLess(machine.arg(0), 0x0807F800+204)
            self.write32(machine, machine.arg(0), machine.arg(1))
            machine.ret(6)
        m.handlers[0x080155EC] = erase
        m.handlers[0x080156A4] = program
        self.assertEqual(m.call(self.img.autosave["save"]), 1)
        self.assertEqual(sequence, ["suspend", "unlock", "erase", "lock", "resume"])
        self.assertEqual(bytes(m.uc.mem_read(0x0807F800, 204)), settings+bytes(4))

    def test_crash_msp_psp_fp_frames_and_invalid_stack(self):
        for exc_return in (0xFFFFFFF9, 0xFFFFFFFD, 0xFFFFFFE9, 0xFFFFFFED):
            for invalid in (False, True):
                m = self.machine()
                frame = 0x2000C000 if exc_return & 4 else 0x2000D000
                self.write32(m, frame+24, 0x08011A6E)
                self.write32(m, frame+20, 0x080119ED)
                self.write32(m, 0xE000ED28, 0x10000 if not invalid else 0x1000)
                self.write32(m, 0xE000ED2C, 0x40000000)
                self.write32(m, 0xE000ED0C, 0x300)
                m.uc.reg_write(UC_ARM_REG_MSP, 0x2000D000)
                m.uc.reg_write(UC_ARM_REG_PSP, 0x2000C000)
                m.uc.reg_write(UC_ARM_REG_LR, exc_return)
                resets = []
                def write(uc, access, addr, size, value, user):
                    if addr == 0xE000ED0C:
                        resets.append(value)
                        uc.emu_stop()
                m.uc.hook_add(UC_HOOK_MEM_WRITE, write)
                m.uc.emu_start(self.img.crash["handler"] | 1, STOP, count=200)
                record = self.img.crash["record"]
                self.assertEqual(resets, [0x05FA0304])
                self.assertEqual(self.read32(m, record), 0xDEADBEEF)
                self.assertEqual(self.read32(m, record+8), 0 if invalid else 0x08011A6E)
                self.assertEqual(self.read32(m, record+12), 0 if invalid else 0x080119ED)
                self.assertEqual(self.read32(m, record+24), exc_return)
                before = bytes(m.uc.mem_read(record, 40))
                m.call(self.img.events["init"])
                self.assertEqual(bytes(m.uc.mem_read(record, 40)), before)

    def test_flash_failure_stops_programming_and_restores_scheduler(self):
        for failure in ("erase", "program", "readback"):
            m = self.machine()
            calls = []
            m.uc.mem_write(0x20000C78, bytes(range(200)))
            for f, name in ((0x0801C844, "suspend"), (0x080156FC, "unlock"),
                            (0x08015690, "lock"), (0x0801D01C, "resume")):
                m.handlers[f] = lambda machine, n=name: (calls.append(n), machine.ret())
            m.handlers[0x080155EC] = lambda machine: machine.ret(3 if failure == "erase" else 6)
            def program(machine):
                calls.append("program")
                machine.ret(3 if failure == "program" else 6)
            m.handlers[0x080156A4] = program
            self.assertEqual(m.call(self.img.autosave["save"]), 0)
            self.assertEqual(calls[-2:], ["lock", "resume"])
            self.assertEqual(calls.count("program"), {"erase": 0, "program": 1, "readback": 51}[failure])

    def test_about_crash_strings_and_no_record(self):
        for valid in (False, True):
            m = self.machine()
            record = self.img.crash["record"]
            m.uc.mem_write(record, struct.pack("<10I", 0xDEADBEEF if valid else 0,
                           0x21524110, 0x08011A6E, 0x080119ED, 0x10000, 0, 0, 0, 3, 0))
            lines = []
            def blit(machine):
                sp = machine.uc.reg_read(UC_ARM_REG_SP)
                pointer = self.read32(machine, sp+4)
                lines.append((machine.arg(1), bytes(machine.uc.mem_read(pointer, 40)).split(b"\0")[0]))
                machine.ret()
            m.handlers[0x080174E8] = blit
            m.handlers[0x08016D08] = lambda machine: machine.ret()
            m.call(self.img.crash["show"])
            self.assertEqual(lines, [(208, b"PC 08011A6E LR 080119ED"),
                                     (222, b"CFSR 00010000 IRQ 3")] if valid else [])

    def test_real_about_screen_both_language_branches(self):
        from thai.engine import Scene
        from thai.mockup import sc_about
        for lang in (1, 2):
            for valid in (False, True):
                s = Scene(image=self.data, lang=lang)
                if valid:
                    s.uc.mem_write(self.img.crash["record"], struct.pack("<10I", 0xDEADBEEF,
                                   0x21524110, 0x08011A6E, 0x080119ED, 0x10000, 0, 0, 0, 3, 0))
                sc_about(s)
                texts = [entry[1] for entry in s.log if entry[0] == "ascii"]
                self.assertEqual("PC 08011A6E LR 080119ED" in texts, valid)
                self.assertEqual("CFSR 00010000 IRQ 3" in texts, valid)

    def test_poe_latch_mask_restored_and_interrupt_cannot_split_copy(self):
        for mask in (0, 1):
            m = self.machine()
            source = self.img.poe["syms"]["POE_SAMPLES"]
            m.uc.mem_write(source, bytes(range(16)))
            writes = []
            def observe(uc, access, addr, size, value, user):
                if self.img.poe["latch"] <= addr < self.img.poe["latch"]+16:
                    writes.append(uc.reg_read(UC_ARM_REG_PRIMASK))
            m.uc.hook_add(UC_HOOK_MEM_WRITE, observe)
            m.uc.reg_write(UC_ARM_REG_PRIMASK, mask)
            m.call(self.img.poe["latch_hook"], until=0x08013636)
            self.assertEqual(writes, [1]*4)
            self.assertEqual(bytes(m.uc.mem_read(self.img.poe["latch"], 16)), bytes(range(16)))
            self.assertEqual(m.uc.reg_read(UC_ARM_REG_PRIMASK), mask)


if __name__ == "__main__":
    unittest.main()
