"""RX roadmap CPU tests with conversion-completion and preemption models."""
import struct
import unittest
from pathlib import Path
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE, UC_HOOK_MEM_READ
from unicorn.arm_const import *
from lpm10rx.image import Image, STOCK_NAME
import rx_patches
from verify_control import Control, STOP, SP, BEEP, IDLE, TICK, MODE
from verify_digital import Detector, pattern, run_checks, RECENT, GAP, reference


def candidate():
    img = Image(str(Path(__file__).resolve().parent.parent / STOCK_NAME))
    for patch in rx_patches.REGISTRY:
        patch(img)
    return img


class Roadmap(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.img = candidate()
        cls.data = bytes(cls.img.data)

    def test_image_ownership_and_unchanged_size_vectors_binding(self):
        path = Path(__file__).resolve().parent.parent / "experimental/APP_LPM-10RX_PN1.3-roadmap.bin"
        self.assertEqual(path.read_bytes(), self.data)
        self.assertEqual(len(self.data), len(self.img.original))
        rebuilt = bytearray(self.img.original)
        for addr, old, new, why, kind in self.img.log:
            offset = addr-0x08006800
            self.assertEqual(bytes(rebuilt[offset:offset+len(old)]), old, why)
            rebuilt[offset:offset+len(new)] = new
        self.assertEqual(bytes(rebuilt), self.data)
        for start, end in ((0x08006800, 0x08006948), (0x0800B388, 0x0800B484), (0x0800BAE8, 0x0800BBB0)):
            self.assertEqual(self.data[start-0x08006800:end-0x08006800],
                             self.img.original[start-0x08006800:end-0x08006800])

    def test_existing_digital_noise_phase_error_and_abi_suite(self):
        def check(ok, label, detail=""):
            self.assertTrue(ok, label+": "+detail)
        run_checks(self.img.original, self.data, check, graded=True)

    def test_existing_key_power_and_timer_suite(self):
        from verify_control import run_checks as controls
        controls(self.img.original, self.data,
                 lambda ok, label, detail="": self.assertTrue(ok, label+": "+detail), roadmap=True)

    def test_strength_levels_and_repeat_cadence(self):
        detector = Detector(self.data, graded=True)
        for delta, expected in ((9, (50, 100)), (25, (50, 50)), (60, (30, 30))):
            for wrong in ((), (3, 20, 40)):
                samples = pattern(low=500, high=500+delta, wrong=wrong)
                self.assertTrue(detector.run(samples))
                self.assertEqual((detector.uc.mem_read(BEEP, 1)[0], detector.uc.mem_read(GAP, 1)[0]), expected)
            c = Control(self.data)
            c.w8(0x2000005D, expected[1])
            c.w16(RECENT, 800)
            c.run(0x08007724)
            self.assertEqual((c.read(BEEP), c.read(GAP)), expected)
            for _ in range(sum(expected)-1):
                c.run()
                c.run(0x08007724)
            self.assertEqual(c.read(BEEP), expected[0])
            self.assertEqual(c.read(GAP), expected[1])

    def test_recent_signal_deadline_and_full_idle_after_expiry(self):
        for recent in (0, 1, 50, 800):
            for beep in (0, 1, 50):
                c = Control(self.data)
                c.w32(IDLE, 300000)
                c.w16(RECENT, recent)
                c.w8(BEEP, beep)
                c.run()
                self.assertEqual(0x08007570 in c.calls, not (recent or beep))
                self.assertEqual(c.read(IDLE, 4), 0 if recent or beep else 300001)
                self.assertEqual(c.read(RECENT, 2), max(0, recent-1))
                self.assertEqual(c.read(BEEP), max(0, beep-1))
        c = Control(self.data)
        c.w16(RECENT, 1)
        c.run()
        self.assertEqual(c.read(IDLE, 4), 0)
        c.run()
        self.assertEqual(c.read(IDLE, 4), 1)
        c.w32(IDLE, 299999)
        c.run()
        self.assertNotIn(0x08007570, c.calls)
        c.run()
        self.assertIn(0x08007570, c.calls)

    def test_beep_gaps_do_not_accumulate_five_minutes_in_previous_release(self):
        # Correct the submitted report: every stock beep already resets idle.
        previous = Path(__file__).resolve().parent.parent / "APP_LPM-10RX_PN1.2-reliability-experimental.bin"
        c = Control(previous.read_bytes())
        c.w32(IDLE, 299990)
        c.w8(BEEP, 50)
        c.w8(GAP, 50)
        c.w16(RECENT, 800)
        high_idle = 0
        for _ in range(2000):
            if c.read(RECENT, 2) < 100:
                c.w16(RECENT, 800)
            c.run()
            c.run(0x08007724)
            high_idle = max(high_idle, c.read(IDLE, 4))
        self.assertLessEqual(high_idle, 50)
        self.assertNotIn(0x08007570, c.calls)

    def test_main_watchdog_and_timer_housekeeping(self):
        c = Control(self.data)
        for _ in range(1000):
            c.run()
        self.assertEqual(c.calls.count(0x08008224), 0)
        self.assertEqual(c.calls.count(0x08007770), 2)
        self.assertEqual(c.calls.count(0x080084D8), 2)
        self.assertEqual(c.calls.count(0x0800ADC0), 1000)
        for mode in (0, 1, 2, 255):
            c.w8(MODE, mode)
            c.uc.reg_write(UC_ARM_REG_R5, MODE)
            c.uc.reg_write(UC_ARM_REG_SP, SP)
            before = len(c.calls)
            c.uc.emu_start(0x0800B8F3, 0x0800B8FC, count=100)
            self.assertEqual(c.calls[before:], [0x08008224])
            self.assertEqual(c.uc.reg_read(UC_ARM_REG_R0), mode)
        c = Control(self.data)
        c.pressed = {(0x40011000, 0x2000)}
        c.w16(RECENT, 2000)
        for _ in range(1200):
            c.run()
        self.assertEqual(c.calls.count(0x08007570), 1)

    def adc(self, channel, delay, mask=0, complete=True):
        c = Control(self.data)
        c.uc.mem_map(0xE000E000, 0x1000)
        base = 0x40020800
        c.w32(base+0x4C, 0xBAD)
        c.w32(base, 0x32)  # stale completion from the previous transaction
        model = dict(start=None, steps=0, reads=[], resets=[], masked=[], attempts=0)
        def memory(uc, access, addr, size, value, user):
            if addr == base+8 and value & 0x400000:
                self.assertEqual(c.read(base, 4) & 0x32, 0, "clear stale flags before SWSTART")
                model["start"] = model["steps"]
            if addr == 0xE000ED0C:
                model["resets"].append(value)
                uc.emu_stop()
        def read(uc, access, addr, size, value, user):
            if addr == base+0x4C:
                model["reads"].append(c.read(base, 4) & 2)
        def step(uc, addr, size, user):
            model["steps"] += 1
            if addr == 0x08007020:
                model["attempts"] += 1  # TIM1 becomes pending while TIM5 selects channel
                self.assertEqual(uc.reg_read(UC_ARM_REG_PRIMASK), 1)
            if model["start"] is not None:
                model["masked"].append(uc.reg_read(UC_ARM_REG_PRIMASK))
                if complete and model["steps"]-model["start"] >= delay:
                    c.w32(base+0x4C, 1000+channel)
                    c.w32(base, c.read(base, 4) | 2)
        c.uc.hook_add(UC_HOOK_MEM_WRITE, memory)
        c.uc.hook_add(UC_HOOK_MEM_READ, read)
        c.uc.hook_add(UC_HOOK_CODE, step)
        c.uc.reg_write(UC_ARM_REG_R0, base)
        c.uc.reg_write(UC_ARM_REG_R1, channel)
        c.uc.reg_write(UC_ARM_REG_SP, SP)
        c.uc.reg_write(UC_ARM_REG_LR, STOP | 1)
        c.uc.reg_write(UC_ARM_REG_PRIMASK, mask)
        c.uc.emu_start(0x080072A5, STOP, count=4000)
        return c, model

    def test_adc_waits_for_selected_channel_and_restores_mask(self):
        for channel in (1, 2, 3, 7):
            for delay in (0, 10, 100, 500):
                for mask in (0, 1):
                    c, model = self.adc(channel, delay, mask)
                    self.assertEqual(c.uc.reg_read(UC_ARM_REG_PC), STOP)
                    self.assertEqual(c.uc.reg_read(UC_ARM_REG_R0), 1000+channel)
                    self.assertEqual(c.uc.reg_read(UC_ARM_REG_PRIMASK), mask)
                    self.assertEqual(c.uc.reg_read(UC_ARM_REG_SP), SP)
                    self.assertEqual(model["reads"], [2])
                    self.assertEqual(model["attempts"], 1)
                    self.assertEqual(model["resets"], [])
                    self.assertTrue(all(model["masked"][:-1]))

    def test_adc_timeout_never_returns_stale_or_false_battery_data(self):
        c, model = self.adc(2, 0, complete=False)
        self.assertEqual(model["resets"], [0x05FA0004])
        self.assertEqual(model["reads"], [])
        self.assertLess(model["steps"], 1000)


if __name__ == "__main__":
    unittest.main()
