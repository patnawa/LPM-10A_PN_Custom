"""PN 2.14 recovery: exact parent, real GPIO, RIGHT cache, and two-mode controls."""
import hashlib
import unittest

from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_PRIMASK

import patches
import scan_recovery
from lpm10a.image import PatchError
import test_portflash_status
from test_scan_hardware import (RealCarrierMachine, CARRIER_INIT, MODE_KEY,
                                ENABLE, BACK, TIM1_EXPECTED, requested_wave)
from verify_scan import SCAN, STATE, DIGITAL, IRQ, DISPATCH


class RecoveryMachine(RealCarrierMachine):
    def hook(self, uc, address, size, user):
        if address == 0x080116BC:        # key feedback; leave real key dispatch/GPIO intact
            self.ret()
        else:
            super().hook(uc, address, size, user)


def build_candidate():
    test_portflash_status.PortFlashStatus.setUpClass()
    img = test_portflash_status.PortFlashStatus.img
    baseline = bytes(img.data)
    if not any(p.pid == scan_recovery.PATCH_ID for p in patches.REGISTRY):
        scan_recovery.register(patches.patch)
    next(p for p in patches.REGISTRY if p.pid == scan_recovery.PATCH_ID)(img)
    img.finalize()
    return img, baseline


class ScanRecovery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.img, cls.baseline = build_candidate()
        cls.data = bytes(cls.img.data)

    def machine(self, mode=1, enabled=1, state=5, data=None):
        m = RecoveryMachine(self.data if data is None else data, mode, enabled, state)
        m.call(CARRIER_INIT)
        return m

    def test_exact_parent_and_declared_changes_no_new_ram(self):
        self.assertEqual(hashlib.sha256(self.baseline).hexdigest(), scan_recovery.PARENT_SHA256)
        meta = self.img.scan_recovery
        self.assertEqual(tuple(self.img.ram_allocs), meta['parent_ram_allocs'])
        self.assertEqual(len(self.data), meta['parent_size'])
        allowed = set(range(0x24, 0x2C))
        blocks = [(start, end-start) for start, end, _, _ in scan_recovery.LABEL_BLOCKS]
        blocks += [(0x08014298, 4), (0x08014480, 4), (0x08011660, 8), (0x08012E6C, 8),
                   (meta['parent_end'], self.img.cave_ptr-meta['parent_end'])]
        for address, size in blocks:
            allowed.update(range(self.img.f(address), self.img.f(address)+size))
        changed = {i for i, pair in enumerate(zip(self.baseline, self.data)) if pair[0] != pair[1]}
        self.assertTrue(changed <= allowed, sorted(changed-allowed))
        for site in (0x08011660, 0x08012E6C):
            self.assertEqual(self.img.read(site, 8), b'PN 2.14\0')
        # No PN 2.13 modulation cursor or dispatch is present in this profile.
        self.assertFalse(hasattr(self.img, 'scan_sync'))

    def test_guard_rejects_non_parent(self):
        with self.assertRaises(PatchError):
            next(p for p in patches.REGISTRY if p.pid == scan_recovery.PATCH_ID)(self.img)

    def test_real_gpio_waveforms_match_parent_and_expected(self):
        for mode in (0, 1, 2):
            with self.subTest(mode=mode):
                old = self.machine(mode, data=self.baseline)
                new = self.machine(mode)
                expected = [requested_wave(mode or 1, t) for t in range(8001)]
                self.assertEqual(new.physical_ticks(8001, IRQ), expected)
                self.assertEqual(old.physical_ticks(8001, IRQ), expected)
                self.assertEqual(new.requests, old.requests)
                self.assertEqual(new.gpio_writes, old.gpio_writes)
                self.assertEqual(new.timer_writes, old.timer_writes)
                self.assertEqual(new.timer_configuration(), TIM1_EXPECTED)
                self.assertEqual(bytes(new.uc.mem_read(DIGITAL, 10)),
                                 bytes(old.uc.mem_read(DIGITAL, 10)))

    def test_two_mode_key_cycle_and_legacy_cursor_resume(self):
        m = self.machine()
        m.physical_ticks(17)
        for expected in (2, 1, 2, 1, 2, 1):
            m.call(MODE_KEY)
            self.assertEqual(m.r8(SCAN+1), expected)
            self.assertEqual(m.r32(DIGITAL), 17)
        self.assertEqual(m.physical_ticks(1, IRQ), [requested_wave(1, 17)])
        self.assertEqual(m.r32(DIGITAL), 18)
        self.assertEqual(m.timer_configuration(), TIM1_EXPECTED)

    def test_pause_resume_both_pin_states_and_exit(self):
        for mode, count in ((1, 17), (1, 67), (2, 3), (2, 9)):
            with self.subTest(mode=mode, count=count):
                m = self.machine(mode)
                m.physical_ticks(count)
                m.call(BACK)
                self.assertEqual(m.r8(SCAN), 0)
                self.assertEqual(m.r8(STATE), 5)
                self.assertEqual(m.pin_modes(), (3, 3))
                before = bytes(m.uc.mem_read(DIGITAL, 10)), len(m.requests)
                self.assertEqual(m.physical_ticks(20, IRQ), [0]*20)
                self.assertEqual((bytes(m.uc.mem_read(DIGITAL, 10)), len(m.requests)), before)
                m.call(ENABLE, 1)
                self.assertEqual(m.physical_ticks(1, IRQ), [requested_wave(mode, count)])
                m.call(BACK)
                m.call(BACK)
                self.assertEqual(m.r8(STATE), 2)
                self.assertEqual(m.pin_modes(), (3, 3))
                self.assertEqual(m.timer_configuration(), TIM1_EXPECTED)

    def test_inactive_screen_and_enable_guards(self):
        for mode in (1, 2):
            for enabled, state in ((0, 5), (1, 2), (1, 6)):
                with self.subTest(mode=mode, enabled=enabled, state=state):
                    m = self.machine(mode, enabled, state)
                    before = list(m.gpio_writes), list(m.timer_writes)
                    self.assertEqual(m.physical_ticks(20, IRQ), [0]*20)
                    self.assertEqual(m.requests, [])
                    self.assertEqual((m.gpio_writes, m.timer_writes), before)

    def test_actual_right_key_reproduces_parent_fault_and_repairs_next_tick(self):
        for data, repaired in ((self.baseline, False), (self.data, True)):
            m = self.machine(data=data)
            m.physical_ticks(101)
            self.assertEqual(m.pin_modes(), (11, 11))
            m.uc.mem_write(0x2000D000, bytes((5, 3)))   # RIGHT click
            m.call(0x080149FC, 0x2000D000)
            self.assertEqual(m.pin_modes(), (0, 11))  # original PA8 operation retained
            self.assertEqual(m.r8(SCAN+12), 255 if repaired else 1)
            self.assertEqual(m.messages[-1], 10)      # original refresh retained
            m.call(DISPATCH)
            self.assertEqual(m.pin_modes(), (11, 11) if repaired else (0, 11))
            if not repaired:
                for _ in range(98):
                    m.call(DISPATCH)
                    self.assertEqual(m.pin_modes(), (0, 11))
                m.call(DISPATCH)
                self.assertEqual(m.pin_modes(), (3, 3))  # stock waits for next LOW

    def test_right_cache_repair_all_812_waveform_phases(self):
        for mode, phases in ((1, 800), (2, 12)):
            for phase in range(phases):
                with self.subTest(mode=mode, phase=phase):
                    m = self.machine(mode)
                    if mode == 1:
                        m.w32(DIGITAL, phase)
                        m.physical_ticks(1)
                    else:
                        m.physical_ticks(phase+1)
                    before = bytes(m.uc.mem_read(DIGITAL, 10))
                    timer_before = list(m.timer_writes)
                    m.call(0x0801446C, 1)
                    self.assertEqual(m.pin_modes()[0], 0)
                    self.assertEqual(m.r8(SCAN+12), 255)
                    after = bytes(m.uc.mem_read(DIGITAL, 10))
                    self.assertEqual(after[:4], before[:4])
                    self.assertEqual(after[5:], before[5:])
                    self.assertEqual(m.timer_writes, timer_before)
                    m.call(DISPATCH)
                    self.assertEqual(m.carrier_pins_selected(), requested_wave(mode, phase+1))

    def test_right_repair_restores_mask_and_safe_interrupt_boundaries(self):
        for mask in (0, 1):
            for mode, count in ((1, 1), (1, 51), (2, 1), (2, 7)):
                with self.subTest(mask=mask, mode=mode, count=count):
                    m = self.machine(mode)
                    m.physical_ticks(count)
                    m.uc.reg_write(UC_ARM_REG_PRIMASK, mask)
                    observable = []
                    def observe(uc, address, size, unused):
                        if not uc.reg_read(UC_ARM_REG_PRIMASK):
                            observable.append((*m.pin_modes(), m.r8(SCAN+12)))
                    hook = m.uc.hook_add(UC_HOOK_CODE, observe)
                    m.call(0x0801446C, 1)
                    m.uc.hook_del(hook)
                    self.assertEqual(m.uc.reg_read(UC_ARM_REG_PRIMASK), mask)
                    self.assertEqual(m.r8(SCAN+12), 255)
                    self.assertTrue(all((a == b and a in (3, 11)) or cache == 255
                                        for a, b, cache in observable), observable)
                    # At every boundary where an IRQ can run, the hardware
                    # is still valid or the cache forces its next-tick repair.
                    self.assertEqual(bool(observable), mask == 0)

    def test_right_while_paused_stays_disabled_and_resumes_correctly(self):
        for mode in (1, 2):
            m = self.machine(mode)
            m.physical_ticks(17)
            m.call(BACK)
            m.call(0x0801446C, 1)
            self.assertEqual(m.r8(SCAN), 0)
            self.assertEqual(m.pin_modes(), (0, 3))
            before = bytes(m.uc.mem_read(DIGITAL, 10)), len(m.requests)
            for _ in range(20):
                m.call(DISPATCH)
            self.assertEqual((bytes(m.uc.mem_read(DIGITAL, 10)), len(m.requests)), before)
            m.call(ENABLE, 1)
            self.assertEqual(m.physical_ticks(1), [requested_wave(mode, 17)])

    def test_full_screen_both_languages_and_selection_states(self):
        from thai.engine import Scene
        from thai.mockup import sc_scan
        for language in (1, 2):
            for mode in (1, 2):
                for enabled in (0, 1):
                    with self.subTest(language=language, mode=mode, enabled=enabled):
                        before = Scene(image=self.baseline, lang=language)
                        after = Scene(image=self.data, lang=language)
                        for scene in (before, after):
                            sc_scan(scene, mode=mode, enable=enabled)
                        labels = [item for item in after.log if item[0] == 'ascii'
                                  and item[1] in scan_recovery.MODE_LABELS]
                        self.assertEqual({item[1] for item in labels}, set(scan_recovery.MODE_LABELS))
                        self.assertFalse(any(item[0] == 'ascii' and ('Sync32' in item[1] or 'Pulse' in item[1])
                                             for item in after.log))
                        for item in labels:
                            index = scan_recovery.MODE_LABELS.index(item[1])
                            self.assertEqual(item[2], (60, 68)[index])
                            self.assertEqual(item[3], (221, 260)[index])
                            self.assertEqual(item[5]['w'], len(item[1])*8)
                            self.assertGreater(item[2], 38+3)
                            self.assertLess(item[2]+item[5]['w'], 202-3)
                            self.assertEqual(item[4], 0xFE60 if mode == index+1 else 0xFFFF)
                        # Only the two widened buttons may alter the screen.
                        # Header, cable icon, and footer remain pixel exact.
                        changed = [(x, y) for y in range(320) for x in range(240)
                                   if before.fb[y][x] != after.fb[y][x]]
                        self.assertTrue(changed)
                        self.assertTrue(all(38 <= x <= 202 and
                                            (216 <= y <= 242 or 255 <= y <= 281)
                                            for x, y in changed), changed[:20])


if __name__ == '__main__':
    unittest.main()
