"""Execute the matched Sync32 RX ARM code; synthetic ADC, not hardware proof."""
import hashlib
import importlib.util
from pathlib import Path
import random
import statistics
import struct
import unittest

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_MCLASS
from capstone.arm import ARM_OP_IMM, ARM_OP_MEM, ARM_REG_PC
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_PRIMASK, UC_ARM_REG_R0, UC_ARM_REG_SP

from lpm10rx.image import PatchError
import robust_fixes
import sync_fixes
import test_rx_robust
from test_rx_followup import ANALYZERS, GATE_STATE, GRADE, REQUEST, SPEAKER
from test_rx_pinpoint import expected_gap
from test_rx_precision import eligibility_cases, strength
from verify_control import BEEP, SP
from verify_digital import ACTIVE, BUFFER, GAP, RECENT, pattern, reference

BASE = 0x08006800
BITS = tuple(int(bit) for bit in f'{sync_fixes.SYNC_WORD:032b}')


def template(phase=0, count=48):
    return [BITS[(i+phase) % 32] for i in range(count)]


def window(phase=0, low=1000, high=1300, wrong=()):
    return [high if bit ^ (i in wrong) else low
            for i, bit in enumerate(template(phase))]


def sync_fit(samples):
    """Mathematical template search independent of firmware rotation and tags."""
    threshold = (sum(samples)-min(samples)-max(samples)) // 46
    observed = [sample > threshold for sample in samples]
    if sum(abs(sample-threshold) for sample in samples) < 192:
        return None
    if 5+sum(value for value, high in zip(samples, observed) if high) < 1000:
        return None
    fits = []
    for phase in range(32):
        errors = [actual != expected for actual, expected in zip(observed, template(phase))]
        if sum(errors) <= 4 and all(sum(errors[i:i+16]) <= 2 for i in (0, 16, 32)):
            fits.append(phase)
    assert len(fits) <= 1, 'accepted code phases must be unique'
    return fits[0] if fits else None


def feedback(samples, previous=0, recent=0):
    if reference(samples):
        return test_rx_robust.feedback(samples, previous, recent)
    phase = sync_fit(samples)
    if phase is None:
        return 0
    bits = template(phase)
    low = int(statistics.median(value for value, bit in zip(samples, bits) if not bit))
    high = int(statistics.median(value for value, bit in zip(samples, bits) if bit))
    if high == 4095 or high <= low:
        return 1
    return expected_gap(strength(pattern(low=low, high=high)), previous, recent)


def candidate():
    img = test_rx_robust.candidate()
    sync_fixes.apply(img)
    return img


class Sync(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.previous = bytes(test_rx_robust.candidate().data)
        cls.img = candidate()
        cls.data = bytes(cls.img.data)

    cpu = test_rx_robust.Robust.cpu
    execute = test_rx_robust.Robust.execute
    detect = test_rx_robust.Robust.detect
    boundary = test_rx_robust.Robust.boundary
    acquire = test_rx_robust.Robust.acquire
    tick = test_rx_robust.Robust.tick
    map_score = test_rx_robust.Robust.map_score

    def test_all_legacy_and_sync_phases_dc_and_amplitude(self):
        c = self.cpu()
        for make, phases in ((pattern, 8), (window, 32)):
            for phase in range(phases):
                for low, delta in ((0, 8), (0, 10), (1000, 10), (1000, 100),
                                   (1000, 300), (0, 4094), (4000, 94), (1000, 3095)):
                    samples = make(phase, low=low, high=low+delta)
                    c.w8(BEEP, 17)
                    c.w8(GAP, 23)
                    expected = feedback(samples)
                    self.assertEqual(self.detect(c, samples, recent=321, grade=0), bool(expected))
                    self.assertEqual(c.read(GRADE), expected, (make.__name__, phase, low, delta))
                    self.assertEqual(c.read(RECENT, 2), 800 if expected else 321)
                    self.assertEqual((c.read(BEEP), c.read(GAP), c.read(ACTIVE)), (17, 23, 1))

    def test_all_single_bit_errors_and_bounded_multi_errors(self):
        c = self.cpu()
        wrong_sets = [(i,) for i in range(48)]
        wrong_sets += [(0, 16, 32), (1, 8, 20, 45), (0, 15, 16, 47), (7, 22, 35, 41)]
        for phase in range(32):
            for wrong in wrong_sets:
                samples = window(phase, wrong=wrong)
                self.assertEqual(sync_fit(samples), phase)
                self.assertTrue(self.detect(c, samples, recent=0, grade=0))
                self.assertEqual(c.read(GRADE), feedback(window(phase)), (phase, wrong))

    def test_error_limits_reject_three_in_block_or_five_total(self):
        c = self.cpu()
        for phase in range(32):
            for wrong in ((0, 1, 2), (15, 14, 13), (16, 17, 18), (32, 33, 34),
                          (0, 1, 16, 17, 32), (2, 18, 19, 34, 35)):
                samples = window(phase, wrong=wrong)
                self.assertFalse(reference(samples), (phase, wrong))
                self.assertIsNone(sync_fit(samples), (phase, wrong))
                self.assertFalse(self.detect(c, samples, recent=321, grade=109))
                self.assertEqual((c.read(GRADE), c.read(RECENT, 2)), (0, 321))

    def test_variable_odd_even_groups_and_impulses_use_expected_code_medians(self):
        c = self.cpu()
        rng = random.Random(0x11032)
        scores = []
        hook = c.uc.hook_add(UC_HOOK_CODE,
                            lambda uc, addr, size, user: scores.append(uc.reg_read(UC_ARM_REG_R0)),
                            begin=robust_fixes.GAP_HELPER, end=robust_fixes.GAP_HELPER)
        counts = set()
        try:
            for phase in range(32):
                bits = template(phase)
                counts.add(sum(bits))
                for ordering in range(4):
                    lows = [1000+i*2 for i in range(bits.count(0))]
                    highs = [2000+i*3 for i in range(bits.count(1))]
                    if ordering % 2:
                        rng.shuffle(lows)
                        rng.shuffle(highs)
                    if ordering >= 2:
                        lows[:2] = [0, 0]
                        highs[-2:] = [4095, 4095]
                    lo, hi = iter(lows), iter(highs)
                    samples = [next(hi) if bit else next(lo) for bit in bits]
                    expected_score = strength(pattern(low=int(statistics.median(lows)),
                                                     high=int(statistics.median(highs))))
                    scores.clear()
                    self.assertTrue(self.detect(c, samples, recent=0, grade=0))
                    self.assertEqual(scores, [expected_score], (phase, ordering))
                    self.assertEqual(c.read(GRADE), feedback(samples))
        finally:
            c.uc.hook_del(hook)
        self.assertEqual(counts, set(range(21, 28)))

    def test_complete_legacy_corpus_feedback_is_unchanged(self):
        c = self.cpu()
        count = 0
        for count, samples in enumerate(eligibility_cases(), 1):
            expected = test_rx_robust.feedback(samples)
            self.assertEqual(feedback(samples), expected, count)
            self.assertEqual(self.detect(c, samples, recent=321, grade=0), bool(expected), count)
            self.assertEqual(c.read(GRADE), expected, count)
        self.assertEqual(count, 3624)

    def test_malformed_dc_alternating_periodic_and_random_windows(self):
        c = self.cpu()
        rng = random.Random(110)
        cases = [[value]*48 for value in (0, 10, 1000, 4095)]
        cases += [[1000+300*((i//period) % 2) for i in range(48)] for period in range(1, 25)]
        cases += [[rng.randrange(4096) for _ in range(48)] for _ in range(160)]
        cases += [[1000+300*rng.randrange(2) for _ in range(48)] for _ in range(160)]
        for number, samples in enumerate(cases):
            expected = feedback(samples)
            self.assertEqual(self.detect(c, samples, recent=321, grade=0), bool(expected), number)
            self.assertEqual(c.read(GRADE), expected, number)

    def test_dithered_transmitter_sampler_clock_and_noise_model_matches_arm(self):
        model_path = Path(__file__).resolve().parents[3] / 'docs/experiments/scan_sync_model.py'
        spec = importlib.util.spec_from_file_location('independent_scan_sync_model', model_path)
        model = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(model)
        self.assertEqual(model.SYNC_CODE, BITS)
        c = self.cpu()
        checked = 0
        for mode in ('legacy', 'sync32'):
            for ratio in (0.98, 0.99, 1.0, 1.01, 1.02):
                for noise in (0, 100, 200):
                    for phase_index in range(32):
                        phase = phase_index + (phase_index % 4)*0.25
                        samples = model.sampled_window(mode, phase, ratio, noise,
                                                       random.Random(1900+phase_index),
                                                       tick_offset=phase_index*977)
                        expected = (model.detect(samples, model.LEGACY_CODE, exact_fallback=True) or
                                    model.detect(samples, model.SYNC_CODE))
                        actual = self.detect(c, samples, recent=321, grade=0)
                        self.assertEqual(actual, expected, (mode, ratio, noise, phase))
                        self.assertEqual(c.read(GRADE), feedback(samples), (mode, ratio, noise, phase))
                        checked += 1
        self.assertEqual(checked, 960)

    def test_new_and_old_code_are_separate_and_legacy_exact_priority_is_proven(self):
        phases = [template(phase) for phase in range(32)]
        self.assertEqual(min(sum(a != b for a, b in zip(x, y))
                             for i, x in enumerate(phases) for y in phases[i+1:]), 20)
        self.assertEqual(min(sum(a != b for a, b in zip(x[:32], y[:32]))
                             for i, x in enumerate(phases) for y in phases[i+1:]), 16)
        legacy = pattern(low=0, high=1)[:16]
        pair_unions = []
        for first in range(33):
            for second in range(first+1, 33):
                assignments = [(start+i, bit) for start in (first, second)
                               for i, bit in enumerate(legacy)]
                required = dict(assignments)
                if all(required[i] == bit for i, bit in assignments):
                    pair_unions.append(required)
        minimum = min(sum(bits[i] != bit for i, bit in required.items())
                      for bits in phases for required in pair_unions)
        self.assertEqual(minimum, 7)
        for phase in range(32):
            self.assertFalse(reference(window(phase)), phase)
        for phase in range(8):
            self.assertIsNone(sync_fit(pattern(phase)), phase)

    def test_new_extension_preserves_stack_snapshot_interrupt_mask_and_active_beep(self):
        c = self.cpu()
        writes = []
        hook = c.uc.hook_add(UC_HOOK_MEM_WRITE,
                            lambda uc, access, addr, size, value, user: writes.append((addr, size)))
        try:
            for phase in range(32):
                samples = window(phase)
                packed = struct.pack('<48H', *samples)
                for mask in (0, 1):
                    writes.clear()
                    c.uc.reg_write(UC_ARM_REG_PRIMASK, mask)
                    c.w8(BEEP, 19)
                    c.w8(GAP, 23)
                    writes.clear()
                    self.assertTrue(self.detect(c, samples, recent=0, grade=0))
                    self.assertEqual(bytes(c.uc.mem_read(BUFFER, 96)), packed)
                    self.assertEqual(c.uc.reg_read(UC_ARM_REG_PRIMASK), mask)
                    self.assertEqual((c.read(BEEP), c.read(GAP)), (19, 23))
                    allowed = {(ACTIVE, 1), (GRADE, 1), (RECENT, 2)}
                    outside = [(addr, size) for addr, size in writes
                               if not (SP-152 <= addr and addr+size <= SP or
                                       (addr, size) in allowed)]
                    self.assertEqual(outside, [])
        finally:
            c.uc.hook_del(hook)

    def test_key_or_gate_transition_during_extension_rejects_result(self):
        md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS)
        entries = [i.address for i in md.disasm(self.data[sync_fixes.EXTENSION-BASE:
                                                        sync_fixes.EXTENSION_END-BASE],
                                               sync_fixes.EXTENSION)]
        for address in entries:
            for kind in ('key', 'gate'):
                c = self.cpu()
                hit = []
                def invalidate(uc, addr, size, user):
                    hit.append(addr)
                    if kind == 'key':
                        c.w8(REQUEST, 2)
                        c.w8(BEEP, 100)
                    else:
                        c.w8(GATE_STATE, 0)
                hook = c.uc.hook_add(UC_HOOK_CODE, invalidate, begin=address, end=address)
                # The fallback half is executed only after all Sync32 phases fail.
                samples = window(31) if address < sync_fixes.EXTENSION+20 else [1000, 1300]*24
                try:
                    self.assertFalse(self.detect(c, samples, recent=321, grade=0))
                    self.assertTrue(hit, hex(address))
                    self.assertEqual(c.read(RECENT, 2), 321)
                    if kind == 'key':
                        self.assertEqual(c.read(BEEP), 100)
                finally:
                    c.uc.hook_del(hook)

    def test_instruction_budget_including_last_sync_phase_and_fallback(self):
        profile = instruction_profile(self.data)
        self.assertEqual(profile['windows'], 185)
        self.assertLess(profile['worst_instructions'], 20000)
        self.assertLessEqual(profile['maximum_stack_bytes'], 152)

    def test_only_two_slots_change_and_parent_tail_has_no_incoming_references(self):
        self.assertEqual(hashlib.sha256(self.previous).hexdigest(), sync_fixes.PREVIOUS_SHA256)
        self.assertEqual(len(self.data), 26152)
        allowed = set(range(sync_fixes.HOOK, sync_fixes.HOOK+4)) | set(range(
            sync_fixes.EXTENSION, sync_fixes.EXTENSION_END))
        changed = {BASE+i for i, (a, b) in enumerate(zip(self.previous, self.data)) if a != b}
        self.assertTrue(changed <= allowed)
        self.assertEqual(self.previous[sync_fixes.EXTENSION-BASE:sync_fixes.EXTENSION_END-BASE],
                         bytes.fromhex('00bf')*14)
        md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS)
        md.detail = True
        md.skipdata = True
        address_halves = {}
        for instruction in md.disasm(self.previous[0x148:], BASE+0x148):
            if instruction.id == 0:
                continue
            if instruction.mnemonic == 'movw':
                address_halves[instruction.operands[0].reg] = instruction.operands[1].imm
            elif instruction.mnemonic == 'movt':
                register = instruction.operands[0].reg
                if register in address_halves:
                    address = (instruction.operands[1].imm << 16) | address_halves[register]
                    self.assertFalse(sync_fixes.EXTENSION <= (address & ~1) < sync_fixes.EXTENSION_END,
                                     ('movw/movt reference', hex(instruction.address), hex(address)))
            if instruction.mnemonic.startswith(('b', 'cb')):
                for operand in instruction.operands:
                    if operand.type == ARM_OP_IMM:
                        self.assertFalse(sync_fixes.EXTENSION <= operand.imm < sync_fixes.EXTENSION_END,
                                         (hex(instruction.address), instruction.op_str))
            if instruction.mnemonic.startswith('ldr'):
                for operand in instruction.operands:
                    if operand.type == ARM_OP_MEM and operand.mem.base == ARM_REG_PC:
                        target = ((instruction.address+4) & ~3)+operand.mem.disp
                        self.assertFalse(sync_fixes.EXTENSION <= target < sync_fixes.EXTENSION_END,
                                         (hex(instruction.address), hex(target)))
        for offset in range(len(self.previous)-3):
            value = struct.unpack_from('<I', self.previous, offset)[0] & ~1
            self.assertFalse(sync_fixes.EXTENSION <= value < sync_fixes.EXTENSION_END,
                             ('pointer', hex(BASE+offset)))
        branch = next(md.disasm(self.previous[0x0800A9C0-BASE:0x0800A9C4-BASE], 0x0800A9C0))
        self.assertEqual((branch.mnemonic, branch.operands[0].imm), ('b.w', sync_fixes.EXTENSION_END))
        reconstructed = bytearray(self.img.original)
        for address, before, after, reason, kind in self.img.log:
            offset = address-BASE
            self.assertEqual(bytes(reconstructed[offset:offset+len(before)]), before, reason)
            reconstructed[offset:offset+len(after)] = after
        self.assertEqual(bytes(reconstructed), self.data)

    def test_wrong_parent_tampering_and_reapplication_fail_without_changes(self):
        for img in (candidate(), test_rx_robust.test_rx_pinpoint.candidate()):
            before = bytes(img.data)
            with self.assertRaises(PatchError):
                sync_fixes.apply(img)
            self.assertEqual(bytes(img.data), before)
        img = test_rx_robust.candidate()
        img.data[0x100] ^= 1
        before = bytes(img.data)
        with self.assertRaises(PatchError):
            sync_fixes.apply(img)
        self.assertEqual(bytes(img.data), before)

    # Existing publication/scheduler/ownership contracts against the new image.
    test_publisher_mode_gate_guards_and_interrupt_mask_for_accept_and_reject = test_rx_robust.Robust.test_publisher_mode_gate_guards_and_interrupt_mask_for_accept_and_reject
    test_in_progress_or_invalidated_windows_preserve_previous_gap = test_rx_robust.Robust.test_in_progress_or_invalidated_windows_preserve_previous_gap
    test_scheduler_freshness_guards_and_existing_countdowns = test_rx_robust.Robust.test_scheduler_freshness_guards_and_existing_countdowns
    test_all_directed_mode_changes_discard_partial_and_completed_windows = test_rx_robust.Robust.test_all_directed_mode_changes_discard_partial_and_completed_windows
    test_key_request_during_analysis_rejects_old_result_and_keeps_confirmation = test_rx_robust.Robust.test_key_request_during_analysis_rejects_old_result_and_keeps_confirmation
    test_digital_and_analog_gate_reopening_requires_complete_fresh_window = test_rx_robust.Robust.test_digital_and_analog_gate_reopening_requires_complete_fresh_window
    test_analog_and_mains_threshold_responses_match_previous_release = test_rx_robust.Robust.test_analog_and_mains_threshold_responses_match_previous_release
    test_uncertainty_uses_long_pulses_and_normal_measurement_recovers = test_rx_robust.Robust.test_uncertainty_uses_long_pulses_and_normal_measurement_recovers


def instruction_profile(data=None):
    """Reproducible instruction/stack observations, not Cortex-M cycle timing.

    Covers all code phases, correctable and rejected errors, adversarial sort
    directions, and all locations for a minimal legacy exact-union fallback.
    Interrupts and flash wait states are not modeled by these instruction counts.
    """
    test = Sync()
    test.data = bytes(candidate().data) if data is None else data
    c = test.cpu()
    cases = []
    for phase in range(32):
        for wrong in ((), (0, 1, 16, 32), (0, 1, 2)):
            cases.append((f'sync-phase{phase}-wrong{wrong}', window(phase, wrong=wrong)))
        for descending in (False, True):
            lo = iter(sorted(range(1000, 1100, 2), reverse=descending))
            hi = iter(sorted(range(2000, 2200, 3), reverse=descending))
            cases.append((f'sync-phase{phase}-descending{descending}',
                          [next(hi) if bit else next(lo) for bit in template(phase)]))
    for start in range(25):
        cases.append((f'legacy-exact-fallback-offset{start}',
                      [500]*start+pattern()[:24]+[500]*(24-start)))
    steps, minimum_sp = [0], [SP]
    def count(uc, addr, size, user):
        steps[0] += 1
        minimum_sp[0] = min(minimum_sp[0], uc.reg_read(UC_ARM_REG_SP))
    hook = c.uc.hook_add(UC_HOOK_CODE, count)
    worst = (0, '')
    try:
        for name, samples in cases:
            steps[0] = 0
            test.assertEqual(test.detect(c, samples, recent=0, grade=0), bool(feedback(samples)))
            worst = max(worst, (steps[0], name))
    finally:
        c.uc.hook_del(hook)
    return {'windows': len(cases), 'worst_instructions': worst[0],
            'worst_window': worst[1], 'maximum_stack_bytes': SP-minimum_sp[0]}


if __name__ == '__main__':
    unittest.main()
