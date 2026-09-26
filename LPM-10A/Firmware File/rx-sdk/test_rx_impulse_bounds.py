"""PN1.31 estimator's real detector call contract, memory bounds and stack ABI.

Run complete Digital analyzers with synthetic ADC windows. The estimator reads
all 48 immutable samples only after a full phase fit, and only the selected 16
after exact-only fallback. These are CPU/memory proofs, not electrical tests.
"""
import struct
import unittest

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_MCLASS
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE, UC_MEM_READ
from unicorn.arm_const import (UC_ARM_REG_PC, UC_ARM_REG_R0, UC_ARM_REG_R1,
                               UC_ARM_REG_R3, UC_ARM_REG_R5, UC_ARM_REG_SP)

import clean_strength as strength
import rx_resilient
import test_rx_followup as followup
import test_rx_isolate as fixtures
import test_rx_tracking_fragments as fragments
import test_rx_tracking_streams as streams
from verify_control import SAVED, SP
from verify_digital import BUFFER, RECENT, pattern


class ImpulseBounds(unittest.TestCase):
    execute = followup.Followup.execute
    fresh = fixtures.Analysers.fresh
    SNAPSHOT = SP-128

    @classmethod
    def setUpClass(cls):
        cls.img = rx_resilient.build_candidate()
        cls.data = bytes(cls.img.data)
        cls.estimator = cls.img.impulse_strength['estimator']
        md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS)
        instructions = md.disasm(cls.img.read(cls.estimator, cls.img.impulse_strength['helper_bytes']),
                                 cls.estimator)
        cls.sample_loads = {i.address for i in instructions if i.mnemonic == 'ldrh' and
                            i.op_str in ('r2, [r0]', 'r3, [r0]', 'r7, [r0]')}
        if len(cls.sample_loads) != 3:
            raise AssertionError('the real estimator must contain exactly three triplet sample loads')

    def observe(self, samples, *, force_full_fallback=False):
        c = streams.StreamCPU(self.data)
        self.fresh(c, mode=0, knob=4095, level=7, grade=0, recent=0)
        c.uc.mem_write(BUFFER, struct.pack('<48H', *samples))
        c.uc.mem_write(SP, b'\xA5'*32)
        c.uc.mem_write(SP-512, b'\x5A'*32)
        captured = {'entered': False, 'returned': False, 'sample_reads': [], 'calls': []}
        active = False

        def code(uc, address, size, user):
            nonlocal active
            if address == self.estimator:
                self.assertFalse(captured['entered'])
                active = True
                fit = uc.reg_read(UC_ARM_REG_R5)
                ptr = uc.reg_read(UC_ARM_REG_R0)
                self.assertIn(fit, range(9))
                self.assertEqual(uc.reg_read(UC_ARM_REG_SP), self.SNAPSHOT)
                self.assertEqual(ptr % 2, 0)
                if fit:
                    self.assertEqual(ptr, self.SNAPSHOT+64)
                    lo, hi = self.SNAPSHOT, self.SNAPSHOT+96
                else:
                    self.assertGreaterEqual(ptr, self.SNAPSHOT)
                    self.assertLessEqual(ptr+32, self.SNAPSHOT+96)
                    lo, hi = ptr, ptr+32
                captured.update(entered=True, fit=fit, pointer=ptr, lo=lo, hi=hi,
                    snapshot=bytes(uc.mem_read(self.SNAPSHOT, 96)), min_sp=self.SNAPSHOT,
                    saved=[uc.reg_read(r) for r in SAVED], r3=uc.reg_read(UC_ARM_REG_R3))
                if force_full_fallback:
                    self.assertEqual(fit, 0)
                    uc.reg_write(UC_ARM_REG_R5, 1)  # negative control: pretend an exact-only span was a full fit
            elif address == strength.ESTIMATE_CALL+4 and active:
                self.assertEqual(uc.reg_read(UC_ARM_REG_SP), self.SNAPSHOT)
                self.assertEqual([uc.reg_read(r) for r in SAVED], captured['saved'])
                self.assertEqual(uc.reg_read(UC_ARM_REG_R3), captured['r3'])
                self.assertEqual(bytes(uc.mem_read(self.SNAPSHOT, 96)), captured['snapshot'])
                captured.update(returned=True, result=uc.reg_read(UC_ARM_REG_R0))
                active = False
            if active:
                captured['min_sp'] = min(captured['min_sp'], uc.reg_read(UC_ARM_REG_SP))
                if address in (strength.SORT, strength.MEDIAN):
                    stack = uc.reg_read(UC_ARM_REG_SP)
                    self.assertEqual(stack % 8, 0, 'nested sort/median call violates 8-byte stack alignment')
                    count = uc.reg_read(UC_ARM_REG_R1)
                    self.assertIn(count, (11, 12) if captured['fit'] else (3, 4))
                    ptr = uc.reg_read(UC_ARM_REG_R0)
                    self.assertIn(ptr, (self.SNAPSHOT-80, self.SNAPSHOT-56))
                    self.assertLessEqual(ptr+2*count, self.SNAPSHOT-32)
                    captured['calls'].append((address, count, stack))

        def memory(uc, access, address, size, value, user):
            if not active:
                return
            if access == UC_MEM_READ:
                pc = uc.reg_read(UC_ARM_REG_PC)
                if pc in self.sample_loads:
                    self.assertTrue(captured['lo'] <= address and address+size <= captured['hi'],
                        f'sample read escaped verified span: {address:#x}, {captured["lo"]:#x}..{captured["hi"]:#x}')
                    self.assertEqual(size, 2)
                    captured['sample_reads'].append(address)
                    return
            # PUSH memory callbacks precede SP writeback in Unicorn. Bound the
            # complete estimator+sort frame, including those prologue writes.
            # It must not write to the immutable caller snapshot.
            self.assertGreaterEqual(address, self.SNAPSHOT-96)
            self.assertLessEqual(address+size, self.SNAPSHOT)

        hooks = [c.uc.hook_add(UC_HOOK_CODE, code),
                 c.uc.hook_add(UC_HOOK_MEM_READ | UC_HOOK_MEM_WRITE, memory,
                               begin=0x20000000, end=0x2000FFFF)]
        try:
            self.execute(c, followup.ANALYZERS[0], budget=150000)
        finally:
            for hook in hooks:
                c.uc.hook_del(hook)
        self.assertFalse(active)
        self.assertEqual(bytes(c.uc.mem_read(SP, 32)), b'\xA5'*32)
        self.assertEqual(bytes(c.uc.mem_read(SP-512, 32)), b'\x5A'*32)
        if captured['entered']:
            self.assertTrue(captured['returned'])
            self.assertTrue(captured['sample_reads'])
            self.assertEqual(len(captured['calls']), 4)
            self.assertEqual(captured['min_sp'], self.SNAPSHOT-96,
                             '80-byte estimator frame plus the 16-byte sort frame')
            self.assertEqual(c.read(RECENT, 2), 800)
        return captured

    def test_all_full_fit_phases_use_48_samples_and_preserve_stack_and_snapshot(self):
        for phase in range(8):
            for low, high in ((1000, 1100), (0, 4095)):
                row = self.observe(pattern(phase, low, high))
                self.assertGreater(row['fit'], 0)
                self.assertLess(min(row['sample_reads']), self.SNAPSHOT+32)
                self.assertGreaterEqual(max(row['sample_reads']), self.SNAPSHOT+64)
        self.assertEqual(self.img.impulse_strength['additional_stack_bytes'], 44)

    def test_exact_only_older_span_cannot_read_unverified_surroundings(self):
        samples = pattern(0, 1000, 1300)[:32]+[1000]*16
        row = self.observe(samples)
        self.assertEqual(row['fit'], 0)
        self.assertEqual(row['pointer'], self.SNAPSHOT+32)
        self.assertEqual(row['result'], strength.contrast_score(300))
        self.assertGreaterEqual(min(row['sample_reads']), self.SNAPSHOT+32)
        self.assertLess(max(row['sample_reads']), self.SNAPSHOT+64)

    def test_fragment_geometry_exercises_all_selected_span_offsets(self):
        accepted, full, fallback, offsets = 0, 0, 0, set()
        for label, samples in fragments.fragment_vectors():
            if label[3:] != (1000, 100):
                continue
            row = self.observe(samples)
            if row['entered']:
                accepted += 1
                if row['fit']:
                    full += 1
                else:
                    fallback += 1
                    offsets.add(row['pointer']-self.SNAPSHOT)
        self.assertEqual(offsets, set(range(16, 65, 2)))
        self.assertGreater(full, 0)
        self.assertGreater(fallback, 100)
        print('PN1.31 estimator bounds:', accepted, 'accepted windows;', full, 'full fits;',
              fallback, 'exact-only spans; selected offsets', min(offsets), '..', max(offsets))

    def test_bounds_oracle_rejects_accidental_full_window_read_from_exact_only_span(self):
        samples = pattern(0, 1000, 1300)[:32]+[1000]*16
        with self.assertRaisesRegex(AssertionError, 'sample read escaped verified span'):
            self.observe(samples, force_full_fallback=True)


if __name__ == '__main__':
    unittest.main()
