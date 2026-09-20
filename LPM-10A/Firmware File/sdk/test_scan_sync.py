"""Execute PN 2.13 TX SCAN logic and its UI under Unicorn.

These tests prove CPU waveforms and control behavior, not electrical output,
oscillator accuracy, cable selectivity, or measured interrupt headroom.
"""
import hashlib
from pathlib import Path
import unittest

from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_PRIMASK

import patches
import scan_sync
from lpm10a.image import PatchError
from test_portflash_status import PortFlashStatus
from verify_scan import ScanMachine, SCAN, STATE, DIGITAL, IRQ, LOG_CALLS


def sync_reference(count, state=0):
    """Independent integer model: emit current chip, then advance time."""
    phase, chip = state & 0xFFFF, state >> 16
    if phase >= 40025 or chip >= 32:
        phase, chip = 0, 0
    output, durations, length = [], [], 0
    for _ in range(count):
        output.append((0x1F25EB11 >> (31-chip)) & 1)
        phase += 808
        length += 1
        if phase >= 40025:
            phase -= 40025
            chip = (chip+1) % 32
            durations.append(length)
            length = 0
    return output, (chip << 16) | phase, durations


def build_candidate():
    # The inherited fixture reproduces all PN 2.12 features and its exact
    # parent bytes before this opt-in patch is applied.
    PortFlashStatus.setUpClass()
    img = PortFlashStatus.img
    baseline = bytes(img.data)
    if not any(p.pid == scan_sync.PATCH_ID for p in patches.REGISTRY):
        scan_sync.register(patches.patch)
    next(p for p in patches.REGISTRY if p.pid == scan_sync.PATCH_ID)(img)
    img.finalize()
    return img, baseline


class ScanSync(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.img, cls.baseline = build_candidate()
        cls.data = bytes(cls.img.data)
        cls.cursor = cls.img.scan_sync['state']

    def machine(self, mode=3, enabled=1, state=5):
        return ScanMachine(self.data, mode, enabled, state)

    def test_exact_parent_guard_and_declared_changes(self):
        self.assertEqual(hashlib.sha256(self.baseline).hexdigest(), scan_sync.PARENT_SHA256)
        self.assertEqual(len(self.data), len(self.baseline))
        allowed = set(range(0x24, 0x2C))
        for address, size in ((0x08014144, 4), (0x0801458E, 22),
                              (0x08014714, 30), (0x08011660, 8), (0x08012E6C, 8),
                              (self.img.scan_sync['parent_end'],
                               self.img.cave_ptr-self.img.scan_sync['parent_end'])):
            allowed.update(range(self.img.f(address), self.img.f(address)+size))
        changed = {i for i, pair in enumerate(zip(self.baseline, self.data)) if pair[0] != pair[1]}
        self.assertTrue(changed <= allowed, sorted(changed-allowed))
        with self.assertRaises(PatchError):
            next(p for p in patches.REGISTRY if p.pid == scan_sync.PATCH_ID)(self.img)

    def test_legacy_waveforms_and_cursors_remain_identical(self):
        for mode in (0, 1, 2):
            old, new = ScanMachine(self.baseline, mode), self.machine(mode)
            old.ticks(8001)
            new.ticks(8001)
            self.assertEqual(new.requests, old.requests, mode)
            self.assertEqual(new.outputs, old.outputs, mode)
            self.assertEqual(bytes(new.uc.mem_read(DIGITAL, 10)),
                             bytes(old.uc.mem_read(DIGITAL, 10)))
            self.assertEqual(new.r32(self.cursor), 0)

    def test_sync_word_exact_rational_rate_many_frames(self):
        # 40025 ticks = 808 complete chips = 25 frames plus 8 chips. This
        # exercises a complete accumulator orbit and both frame lengths.
        m = self.machine()
        m.ticks(40025)
        expected, state, lengths = sync_reference(40025)
        self.assertEqual(m.requests, expected)
        self.assertEqual(m.outputs, expected)
        self.assertEqual(m.r32(self.cursor), state)
        self.assertEqual(state, 8 << 16)
        self.assertEqual(set(lengths), {49, 50})
        self.assertEqual(len(lengths), 808)
        self.assertEqual(sum(lengths), 40025)
        self.assertEqual(40025 * 101 / 808, 5003.125)
        # A complete 32-chip word has 16 high chips; only dither changes
        # individual chip width, so there is no long term DC code imbalance.
        self.assertEqual(sum(scan_sync.SYNC_BITS), 16)
        self.assertFalse(m.calls.keys() & LOG_CALLS)

    def test_sync_phase_boundaries_and_corrupt_state_recover(self):
        for seed in (0, 39216, 39217, 40024, 40025, 0xFFFF,
                     (31 << 16) | 40024, 32 << 16, 0xFFFFFFFF):
            m = self.machine()
            m.w32(self.cursor, seed)
            m.ticks(103)
            output, state, _ = sync_reference(103, seed)
            self.assertEqual(m.requests, output, hex(seed))
            self.assertEqual(m.r32(self.cursor), state, hex(seed))

    def test_pulse_exact_duty_and_corrupt_counter_recovery(self):
        for seed, count in ((0, 14851), (989, 3), (990, 3), (4949, 3),
                            (4950, 3), (0xFFFFFFFF, 3)):
            m = self.machine(4)
            m.w32(self.cursor, seed)
            m.ticks(count)
            initial = seed if seed < 4950 else 0
            expected = [int((initial+i) % 4950 < 990) for i in range(count)]
            self.assertEqual(m.requests, expected)
            self.assertEqual(m.outputs, expected)
            self.assertEqual(m.r32(self.cursor), (initial+count) % 4950)
        self.assertEqual(990 * 101, 99990)
        self.assertEqual((4950-990) * 101, 399960)

    def test_mode_cycle_resets_new_cursor_and_retains_legacy_cursor(self):
        m = self.machine(1)
        m.ticks(17)
        legacy = m.r32(DIGITAL)
        for expected in (2, 3, 4, 1, 2, 3, 4, 1):
            m.w32(self.cursor, 0xAAAAAAAA)
            m.call(0x0801458C)
            self.assertEqual(m.r8(SCAN+1), expected)
            self.assertEqual(m.r32(self.cursor), 0)
            self.assertEqual(m.r32(DIGITAL), legacy)
            self.assertEqual(m.messages[-1], 10)
            if expected != 1:
                m.ticks(15)
        m.ticks(1)
        self.assertEqual(m.r32(DIGITAL), 18)
        for invalid in (0, 5, 255):
            m.w8(SCAN+1, invalid)
            m.call(0x0801458C)
            self.assertEqual(m.r8(SCAN+1), 1)

    def test_mode_publication_is_atomic_and_preserves_primask(self):
        for mask in (0, 1):
            for mode in (1, 2, 3, 4):
                m = self.machine(mode)
                m.w32(self.cursor, 1234)
                m.uc.reg_write(UC_ARM_REG_PRIMASK, mask)
                observed = []
                def observe(uc, address, size, unused):
                    if not uc.reg_read(UC_ARM_REG_PRIMASK):
                        observed.append((m.r8(SCAN+1), m.r32(self.cursor)))
                m.uc.hook_add(UC_HOOK_CODE, observe)
                m.call(self.img.scan_sync['mode_key'])
                self.assertEqual(m.uc.reg_read(UC_ARM_REG_PRIMASK), mask)
                self.assertEqual(m.r8(SCAN+1), mode % 4 + 1)
                self.assertEqual(m.r32(self.cursor), 0)
                self.assertTrue(set(observed) <= {(mode, 1234), (mode % 4+1, 0)})

    def test_stop_resume_exit_every_new_mode_and_signal_level(self):
        for mode, ticks in ((3, 17), (3, 160), (3, 1586), (4, 100), (4, 1200)):
            m = self.machine(mode)
            m.ticks(ticks)
            m.call(0x0801456C)
            cursor, requests = m.r32(self.cursor), len(m.requests)
            m.ticks(200)
            self.assertEqual(m.r8(SCAN), 0)
            self.assertEqual(m.carrier, 0)
            self.assertEqual(m.r8(STATE), 5)
            self.assertEqual(m.r32(self.cursor), cursor)
            self.assertEqual(len(m.requests), requests)
            m.call(0x08014498, 1)
            m.ticks(1)
            self.assertEqual(m.carrier, m.requests[-1])
            m.call(0x0801456C)
            m.call(0x0801456C)
            self.assertEqual(m.r8(STATE), 2)
            self.assertEqual(m.carrier, 0)

    def test_inactive_guards_preserve_state(self):
        for mode in (3, 4):
            for enabled, screen in ((0, 5), (1, 2), (1, 6), (0, 0)):
                m = self.machine(mode, enabled, screen)
                m.w32(self.cursor, 1234)
                m.ticks(50)
                self.assertEqual(m.requests, [])
                self.assertEqual(m.r32(self.cursor), 1234)

    def test_full_tim2_path_and_pending_interrupt_guard(self):
        for mode in (3, 4):
            m = self.machine(mode)
            m.ticks(5000, IRQ)
            self.assertEqual(len(m.requests), 5000)
            self.assertEqual(m.calls[0x080169A8], 5)
            self.assertEqual(m.calls[0x0800F9CC], 1000)
            self.assertEqual(m.calls[0x080183CC], 5000)
            self.assertFalse(m.calls.keys() & LOG_CALLS)
            count, cursor, calls = len(m.requests), m.r32(self.cursor), m.calls.copy()
            m.pending = 0
            m.ticks(10, IRQ)
            self.assertEqual(len(m.requests), count)
            self.assertEqual(m.r32(self.cursor), cursor)
            self.assertEqual(m.calls, calls)

    def test_four_rows_both_languages_all_selection_states(self):
        from thai.engine import Scene
        for lang in (1, 2):
            for mode in (1, 2, 3, 4):
                for enabled in (0, 1):
                    s = Scene(image=self.data, lang=lang, state=5)
                    s.w8(SCAN, enabled, mode)
                    s.call(0x08014144)
                    labels = [entry for entry in s.log if entry[0] == 'ascii']
                    self.assertEqual([entry[1] for entry in labels], list(scan_sync.MODE_LABELS))
                    self.assertEqual([entry[5]['w'] for entry in labels],
                                     [len(label)*8 for label in scan_sync.MODE_LABELS])
                    for entry in labels:
                        self.assertGreaterEqual(entry[2], 34)
                        self.assertLessEqual(entry[2]+entry[5]['w'], 206)
                        self.assertGreaterEqual(entry[3], 197)
                        self.assertLessEqual(entry[3]+16, 288)
                    # Each row paints the correct background, including the
                    # enabled selected mode and the paused selected mode.
                    for index in range(1, 5):
                        expected_bg = 0x7304 if enabled and index == mode else 0x2105
                        self.assertEqual(s.fb[194+(index-1)*24][34], expected_bg)


if __name__ == '__main__':
    unittest.main()
