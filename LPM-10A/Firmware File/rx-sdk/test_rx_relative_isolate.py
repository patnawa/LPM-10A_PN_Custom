"""PN1.26: full sensitivity everywhere, peak-relative isolation, on the actual ARM code.

The analysers, publisher, AGC, sampler and speaker of the built image execute
in Unicorn; ADC values, the analogue link and interrupt arrival are modeled.
The Compare arithmetic (peak, decay, window, ranking) is checked against an
independent model of its stated rules; the upper half against PN1.24. None of
this measures pickup, coupling between real pairs or loudness.
"""
import contextlib
import hashlib
import io
import random
import struct
import unittest

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_MCLASS
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_PRIMASK, UC_ARM_REG_R0

import auto_range
import isolate
import relative_isolate as rel
import rx_precision
import sample_age_guard
import test_rx_digital_strong_gain as strong
import test_rx_followup as followup
import test_rx_tracking_streams as streams
from lpm10rx import symbols
from lpm10rx.container import unwrap, wrap
from lpm10rx.image import PatchError
from test_rx_analog_fast import corpus as analog_corpus
from test_rx_followup import ANALYZERS, GATE_STATE, GRADE, REQUEST
from test_rx_isolate import (CCR4, Streams, analog_windows, clipped_digital, digital_windows,
                             knob_code, smoothed, walk)
from test_scan_acquisition_timing import TIMER_COUNTER
from verify_control import BEEP, MODE, SP
from verify_digital import ACTIVE, BUFFER, GAP, GATE, RECENT, pattern

PARENT = CANDIDATE = IMG = None
CANDIDATE_SHA256 = 'd3f19545c3d9f382534e60e0cc91e64af038b80f03da77ff0c61c4d4006edab8'
MULT = (200, 92, 26, 26, 11, 11, 11, 10)
NOW = 0xfffffff0
COMPARE_KNOBS = (2, 300, 580, 700, 1024, 1300, 1600, 1900, 2047)
SEARCH_KNOBS = (2048, 3000, 4095)
DIGITAL_HOLD, ANALOG_HOLD = 660, 560


def setUpModule():
    global PARENT, CANDIDATE, IMG
    with contextlib.redirect_stdout(io.StringIO()):
        PARENT = bytes(rx_precision.build_candidate().data)
    IMG = rel.build_candidate()
    CANDIDATE = bytes(IMG.data)


# ---------------------------------------------------------------- reference model
def decayed(peak, elapsed):
    if elapsed > rel.STALE_TICKS:
        peak, elapsed = 0, 0
    while elapsed >= rel.STEP_TICKS:
        elapsed -= rel.STEP_TICKS
        peak = peak * rel.DECAY >> 8
    return peak, elapsed


def model(raw, level, knob, peak, elapsed):
    """(quiet interval or None when muted, new peak, unfinished decay ticks)."""
    score = raw & 0xFFFFFFFF
    if level <= 7:
        score = ((score * MULT[level]) & 0xFFFFFFFF) // 10
    score = min(score, rel.CLAMP)
    peak, rest = decayed(peak, elapsed)
    peak = max(peak, score)
    w = rel.window(knob)
    if w is None:
        return walk(score), peak, rest
    threshold = peak * w >> 8
    if score < threshold:
        return None, peak, rest
    span = peak - threshold
    ranked = rel.SATURATION_SCORE if span == 0 else (
        (((score - threshold) << 8) // span) * rel.SATURATION_SCORE >> 8)
    return walk(ranked), peak, rest


class Analysers:
    execute = followup.Followup.execute

    def entry(self, data):
        return IMG.relative_isolate['curve'] if data is CANDIDATE else isolate.OLD_CURVE

    def analyse(self, data, samples, *, mode=0, knob=4095, level=7, grade=0, recent=0, gap=0,
                peak=0, elapsed=0, mask=0):
        c = streams.StreamCPU(data)
        c.uc.mem_write(0x20000000, bytes(0x220))
        c.w8(MODE, mode)
        c.w8(REQUEST, 0)
        c.w16(GATE, knob)
        c.w16(GATE + 2, knob_code(knob))
        c.w8(GATE_STATE, 2)
        c.w8(ACTIVE, 0)
        c.w8(GRADE, grade)
        c.w8(GAP, gap)
        c.w16(RECENT, recent)
        c.uc.mem_write(auto_range.STATE, bytes((level, 0, 0, knob_code(knob))))
        c.w32(sample_age_guard.COMPLETED_AT, NOW)
        c.w32(sample_age_guard.TIMER_COUNTER, NOW)
        c.w32(sample_age_guard.COMPLETED_VALID, 1)
        c.w32(rel.PEAK, peak)
        c.w32(rel.PEAK + 4, (NOW - elapsed) & 0xFFFFFFFF)
        if mode == 0:
            c.uc.mem_write(BUFFER, struct.pack('<48H', *samples) + bytes([0xA5] * 32))
        else:
            c.uc.mem_write(BUFFER, struct.pack('<64H', *samples))
        c.uc.reg_write(UC_ARM_REG_PRIMASK, mask)
        scores = []
        at = self.entry(data)
        hook = c.uc.hook_add(UC_HOOK_CODE, lambda uc, a, s, u: scores.append(uc.reg_read(UC_ARM_REG_R0)),
                             begin=at, end=at)
        try:
            self.execute(c, ANALYZERS[mode], budget=150000)
        finally:
            c.uc.hook_del(hook)
        self.assertEqual(c.uc.reg_read(UC_ARM_REG_PRIMASK), mask)
        state = tuple(c.read(a, n) for a, n in
                      ((GRADE, 1), (RECENT, 2), (ACTIVE, 1), (0x2000005B, 1), (BEEP, 1), (GAP, 1)))
        return state, tuple(scores), (c.read(rel.PEAK, 4), (NOW - c.read(rel.PEAK + 4, 4)) & 0xFFFFFFFF)

    def expected(self, parent_state, raw, *, mode, knob, level, grade, recent, gap, peak, elapsed):
        aim, new_peak, rest = model(raw, level, knob, peak, elapsed)
        hold = DIGITAL_HOLD if mode == 0 else ANALOG_HOLD
        if aim is None:
            state = (grade, min(recent, hold)) + parent_state[2:5] + (gap,)
        else:
            new_grade = smoothed(aim, grade, recent)
            new_recent, new_gap = (800, gap) if mode == 0 else (600, min(gap, new_grade))
            state = (new_grade, new_recent) + parent_state[2:5] + (new_gap,)
        return state, (new_peak, rest)


PEAKS = ((0, 0), (5_000, 0), (60_000, 0), (400_000, 0), (400_000, 4_000), (400_000, 23_999),
         (900_000, 120_000), (900_000, rel.STALE_TICKS + 1), (rel.CLAMP, 0))


class Build(unittest.TestCase):
    def test_parent_is_pinned_and_only_declared_sites_change(self):
        self.assertEqual(IMG.relative_isolate['start'], symbols.APP_BASE + len(PARENT))
        allowed = set()
        for site, size in ((isolate.GAP_ENTRY, 4), (isolate.DIGITAL_UNCERTAIN, 4), (isolate.ANALOG_SITE, 24),
                           (isolate.GAIN_SITE, 4), (isolate.TONE_HIGH, 4), (isolate.TONE_LOW, 4),
                           (0x0800CDE4, 8)):
            allowed |= set(range(site, site + size))
        changed = {symbols.APP_BASE + i for i, (a, b) in enumerate(zip(PARENT, CANDIDATE)) if a != b}
        self.assertTrue(changed)
        self.assertLessEqual(changed, allowed)
        self.assertEqual(len(CANDIDATE) - len(PARENT), IMG.relative_isolate['helper_bytes'])
        self.assertLessEqual(symbols.APP_BASE + len(CANDIDATE), symbols.EXTEND_LIMIT)
        self.assertEqual(CANDIDATE[0x0800CDE4 - symbols.APP_BASE:][:8], b'PN1.26\0\0')

    def test_peak_ram_is_zero_initialised_and_unused_by_pn124(self):
        lo, hi = rel.ZERO_INIT
        self.assertTrue(lo <= rel.PEAK and rel.PEAK + 8 <= 0x200013F0 <= hi,
                        'inside startup zero-init and below the deepest audited stack')
        for word in range(rel.PEAK, rel.PEAK + 8, 4):
            self.assertNotIn(word.to_bytes(4, 'little'), PARENT, 'no literal pool entry')
        md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS)
        md.skipdata = True
        reached = set()
        for skew in (0, 2):
            listing = list(md.disasm(PARENT[skew:], symbols.APP_BASE + skew))
            for insn, following in zip(listing, listing[1:]):
                if insn.mnemonic.startswith('movw') and following.mnemonic.startswith('movt'):
                    reg = insn.op_str.split(',')[0]
                    if following.op_str.split(',')[0] == reg:
                        low = int(insn.op_str.split('#')[-1], 16)
                        high = int(following.op_str.split('#')[-1], 16)
                        reached.add(high << 16 | low)
        self.assertGreater(len(reached), 100, 'the -O0 image addresses RAM with movw/movt pairs')
        self.assertFalse(set(range(rel.PEAK, rel.PEAK + 8)) & reached, 'no movw/movt pair reaches the peak words')

    def test_changed_parent_is_rejected_before_any_byte_changes(self):
        with contextlib.redirect_stdout(io.StringIO()):
            img = rx_precision.build_candidate()
        img.data[img.f(isolate.TONE_HIGH)] ^= 1
        before = bytes(img.data), list(img.log)
        with self.assertRaises(PatchError):
            rel.apply(img)
        self.assertEqual((bytes(img.data), img.log), before)

    def test_written_candidate_is_this_exact_build(self):
        self.assertEqual(hashlib.sha256(CANDIDATE).hexdigest(), CANDIDATE_SHA256)
        raw, update = rel.DIRECTORY / rel.OUTPUT, rel.DIRECTORY / rel.UPDATE
        if not raw.exists():
            self.skipTest('experimental PN1.26 files not written yet (python relative_isolate.py --write)')
        self.assertEqual(raw.read_bytes(), CANDIDATE)
        self.assertEqual(update.read_bytes(), wrap(CANDIDATE))
        self.assertEqual(unwrap(update.read_bytes())[1], CANDIDATE)
        sums = (rel.DIRECTORY / rel.SUMS).read_text(encoding='ascii').split()
        self.assertEqual(sums, [CANDIDATE_SHA256, rel.OUTPUT, hashlib.sha256(wrap(CANDIDATE)).hexdigest(), rel.UPDATE])

    def test_no_branch_lands_inside_replaced_instructions(self):
        forbidden = {isolate.DIGITAL_UNCERTAIN + 2, isolate.GAP_ENTRY + 2, isolate.GAIN_SITE + 2,
                     isolate.TONE_HIGH + 2, isolate.TONE_LOW + 2}
        forbidden |= set(range(isolate.ANALOG_SITE + 2, isolate.ANALOG_SITE + 24, 2))
        replaced = set(range(isolate.ANALOG_SITE, isolate.ANALOG_SITE + 24))
        conditions = ('eq', 'ne', 'hs', 'cs', 'lo', 'cc', 'mi', 'pl', 'vs', 'vc', 'hi', 'ls', 'ge', 'lt', 'gt', 'le')
        branches = {'b', 'bl', 'cbz', 'cbnz'} | {'b' + c for c in conditions}
        md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS)
        md.skipdata = True
        hits, seen = [], 0
        for skew in (0, 2):
            for insn in md.disasm(CANDIDATE[skew:], symbols.APP_BASE + skew):
                if insn.mnemonic.split('.')[0] in branches and '#' in insn.op_str:
                    seen += 1
                    dest = int(insn.op_str.split('#')[-1], 16)
                    if dest in forbidden and insn.address not in replaced:
                        hits.append((hex(insn.address), insn.mnemonic, hex(dest)))
        self.assertGreater(seen, 1000)
        self.assertEqual(hits, [])

    def test_window_table_in_image_and_model(self):
        values = [rel.window(k) for k in range(4096)]
        self.assertTrue(all(v is None for v in values[rel.SEARCH_RAW:]))
        compare = values[:rel.SEARCH_RAW]
        self.assertEqual(compare, sorted(compare, reverse=True), 'the window only narrows as the knob turns down')
        self.assertEqual((compare[0], compare[-1]), (128, 1))
        start = IMG.relative_isolate['curve'] - symbols.APP_BASE
        self.assertIn(struct.pack(f'<{len(rel.WINDOW)}H', *rel.WINDOW), CANDIDATE[start:start + 0x140])


class Digital(Analysers, unittest.TestCase):
    def test_upper_half_is_pn124_whatever_the_peak(self):
        cases = 0
        windows = list(digital_windows()) + list(clipped_digital())
        rng = random.Random(0x126D)
        windows += [(f'noise_{n}', [rng.randrange(4096) for _ in range(48)]) for n in range(8)]
        for knob in SEARCH_KNOBS:
            for level in (0, 2, 7):
                for grade, recent in ((0, 0), (20, 800), (65, 700)):
                    for peak, elapsed in PEAKS[::2]:
                        for name, samples in windows:
                            kw = dict(knob=knob, level=level, grade=grade, recent=recent, mask=cases & 1)
                            new = self.analyse(CANDIDATE, samples, peak=peak, elapsed=elapsed, **kw)
                            old = self.analyse(PARENT, samples, **kw)
                            self.assertEqual(new[:2], old[:2], (knob, level, name, peak))
                            cases += 1
        print('Digital upper-half vectors identical to PN1.24:', cases)

    def test_lower_half_follows_the_peak_model(self):
        cases = muted = ranked = 0
        for knob in COMPARE_KNOBS:
            for level in (0, 1, 2, 7):
                for grade, recent in ((0, 0), (45, 800)):
                    for peak, elapsed in PEAKS:
                        for name, samples in digital_windows():
                            kw = dict(knob=knob, level=level, grade=grade, recent=recent)
                            parent_state, parent_scores = self.analyse(PARENT, samples, **kw)[:2]
                            state, scores, stored = self.analyse(CANDIDATE, samples, peak=peak, elapsed=elapsed, **kw)
                            self.assertEqual(scores, parent_scores)
                            if not scores:
                                self.assertEqual(state, parent_state)
                                self.assertEqual(stored, (peak, elapsed), 'no detection leaves the peak alone')
                                continue
                            want, want_peak = self.expected(parent_state, scores[0], mode=0, knob=knob, level=level,
                                                            grade=grade, recent=recent, gap=0, peak=peak,
                                                            elapsed=elapsed)
                            self.assertEqual((state, stored), (want, want_peak),
                                             (knob, level, name, grade, peak, elapsed, scores))
                            cases += 1
                            aim = model(scores[0], level, knob, peak, elapsed)[0]
                            muted += aim is None
                            ranked += aim is not None
        self.assertGreater(muted, 200)
        self.assertGreater(ranked, 200)
        print('Digital lower-half vectors:', cases, 'muted', muted, 'ranked', ranked)

    def test_clipped_window_counts_as_saturation_at_the_driven_gain(self):
        for name, samples in clipped_digital():
            old = self.analyse(PARENT, samples)
            self.assertEqual(old[0][:2], (20, 800))
            self.assertEqual(self.analyse(CANDIDATE, samples)[0], old[0], 'upper half: PN1.24')
            for knob in COMPARE_KNOBS:
                for level in (0, 2, 7):
                    for peak, elapsed in PEAKS[:4]:
                        state, scores, stored = self.analyse(CANDIDATE, samples, knob=knob, level=level,
                                                             peak=peak, elapsed=elapsed)
                        self.assertEqual(scores, (rel.SATURATION_SCORE,))
                        parent_state = self.analyse(PARENT, samples, knob=knob, level=level)[0]
                        want = self.expected(parent_state, rel.SATURATION_SCORE, mode=0, knob=knob, level=level,
                                             grade=0, recent=0, gap=0, peak=peak, elapsed=elapsed)
                        self.assertEqual((state, stored), want, (name, knob, level, peak))

    def test_one_cable_alone_is_its_own_peak_at_every_knob(self):
        weak = pattern(0, 800, 830)
        for knob in COMPARE_KNOBS:
            state, scores, stored = self.analyse(CANDIDATE, weak, knob=knob, level=7)
            self.assertTrue(scores)
            self.assertEqual(state[:2], (isolate.FASTEST_MS, 800), knob)
            self.assertEqual(stored[0], scores[0])


class Analog(Analysers, unittest.TestCase):
    def test_upper_half_is_pn124_whatever_the_peak(self):
        cases = 0
        windows = list(analog_corpus()) + list(analog_windows())
        for knob in (2048, 4095):
            for level in (0, 7):
                for grade, recent, gap in ((0, 0, 0), (45, 800, 90)):
                    for peak, elapsed in PEAKS[::3]:
                        for name, samples in windows:
                            kw = dict(mode=1, knob=knob, level=level, grade=grade, recent=recent, gap=gap,
                                      mask=cases & 1)
                            new = self.analyse(CANDIDATE, samples, peak=peak, elapsed=elapsed, **kw)
                            old = self.analyse(PARENT, samples, **kw)
                            self.assertEqual(new[:2], old[:2], (knob, level, name))
                            cases += 1
        print('Analog upper-half vectors identical to PN1.24:', cases)

    def test_lower_half_follows_the_model_and_mute_skips_the_refresh(self):
        cases = muted = 0
        for knob in COMPARE_KNOBS[2:]:
            for level in (0, 2, 7):
                for grade, recent, gap in ((0, 0, 0), (45, 800, 90)):
                    for peak, elapsed in PEAKS:
                        for name, samples in analog_windows():
                            kw = dict(mode=1, knob=knob, level=level, grade=grade, recent=recent, gap=gap)
                            parent_state, parent_scores = self.analyse(PARENT, samples, **kw)[:2]
                            state, scores, stored = self.analyse(CANDIDATE, samples, peak=peak, elapsed=elapsed, **kw)
                            self.assertEqual(scores, parent_scores)
                            if not scores:
                                self.assertEqual(state, parent_state)
                                continue
                            want = self.expected(parent_state, scores[0], mode=1, knob=knob, level=level, grade=grade,
                                                 recent=recent, gap=gap, peak=peak, elapsed=elapsed)
                            self.assertEqual((state, stored), want, (knob, level, name, peak, elapsed))
                            cases += 1
                            muted += model(scores[0], level, knob, peak, elapsed)[0] is None
        self.assertGreater(muted, 50)
        print('Analog lower-half vectors:', cases, 'muted', muted)


class MainsAndSpeaker(Analysers, unittest.TestCase):
    def test_mains_analysis_is_pn124(self):
        for knob in (0, 700, 2048, 4095):
            for name, samples in list(analog_corpus())[:40]:
                kw = dict(mode=2, knob=knob, level=2, grade=0, recent=700)
                self.assertEqual(self.analyse(CANDIDATE, samples, **kw)[:2], self.analyse(PARENT, samples, **kw)[:2])

    def test_tone_is_the_pn125_louder_swing(self):
        for keep_alive, want in ((30, [1100, 500] * 3), (0, [800] * 6)):
            c = streams.StreamCPU(CANDIDATE)
            writes = []
            c.uc.hook_add(UC_HOOK_MEM_WRITE, lambda uc, access, a, size, value, user: writes.append(value),
                          begin=CCR4, end=CCR4 + 1)
            for _ in range(6):
                self.execute(c, 0x08007508, keep_alive, stack=SP - 0x400)
            self.assertEqual(writes, want)


class Gain(Streams):
    def test_tracing_uses_the_full_gain_at_every_knob_position(self):
        weak = lambda ms: 60
        for knob, pn124 in ((300, 0), (1000, 1), (2000, 2), (4095, 7)):
            for mode in (0, 1):
                old = self.stream(PARENT, mode=mode, knob=knob, amplitude=weak, end_ms=700)
                new = self.stream(CANDIDATE, mode=mode, knob=knob, amplitude=weak, end_ms=700)
                self.assertEqual((old['driven'], new['driven']), (pn124, 7), (knob, mode))

    def test_compare_ceiling_follows_the_peak_and_window(self):
        # Executes the gain hook through the real TIM1 500 ms path with a seeded peak.
        cases = 0
        for knob in (300, 700, 1300, 1900, 2047, 2048, 4095):
            for peak in (0, 20_000, 120_000, 400_000, 900_000, rel.CLAMP):
                c = strong.GainStreamCPU(CANDIDATE, mode=0, level=7)
                c.knob_raw = knob
                c.w16(0x20000068, knob)
                c.uc.mem_write(auto_range.STATE, bytes((7, 0, 0, 7)))
                c.w32(TIMER_COUNTER, 5000)
                c.w32(rel.PEAK, peak)
                c.w32(rel.PEAK + 4, 5000)
                c.w32(0x200000FC, 499)          # TIM1 tick: the next interrupt runs the 500 ms work
                self.execute(c, strong.TIM1, stack=SP - 0x500, budget=10000)
                want = rel.ceiling(peak, knob)
                self.assertEqual(c.read(auto_range.STATE), want, (knob, peak))
                self.assertEqual(c.read(rel.PEAK, 4), peak, 'the gain hook never writes the peak')
                cases += 1
        print('Compare ceiling cases:', cases)

    def test_full_knob_agc_is_pn124(self):
        for mode in (0, 1):
            for amplitude, end in ((lambda ms: 2400 if ms < 1000 else 800, 1800), (lambda ms: 20000, 2900)):
                old = self.stream(PARENT, mode=mode, knob=4095, amplitude=amplitude, end_ms=end)
                new = self.stream(CANDIDATE, mode=mode, knob=4095, amplitude=amplitude, end_ms=end)
                self.assertEqual(new['levels'], old['levels'])
                self.assertEqual(new['publications'], old['publications'])

    def test_ncv_gain_follows_the_knob_full_from_a_quarter(self):
        strong_signal = lambda ms: 30000
        for knob, wanted in ((4095, 7), (1100, 7), (800, 1), (300, 0)):
            new = self.stream(CANDIDATE, knob=knob, amplitude=strong_signal, end_ms=3700, mode_changes={3000: 2})
            self.assertEqual((new['mode'], new['driven']), (2, wanted), knob)
        old = self.stream(PARENT, knob=4095, amplitude=strong_signal, end_ms=3700, mode_changes={3000: 2})
        self.assertEqual(old['driven'], 0, 'PN1.24 keeps the lowered tracing gain in mains')

    def test_knob_off_still_silences(self):
        for mode in (0, 1):
            row = self.stream(CANDIDATE, mode=mode, knob=4095, amplitude=lambda ms: 30000,
                              end_ms=3600, knob_changes={3000: 0})
            self.assertGreater(self.sounding(row, 2000, 3000), 100)
            self.assertEqual(self.sounding(row, 3300, 3600), 0)


class Field(Streams):
    def test_owner_bench_test_a_weak_cable_sounds_low_on_the_knob(self):
        # Probe held still near one cable; only the full gain detects it.
        for mode, amplitude, knobs in ((0, 20, (300, 700, 1024, 1500)), (1, 40, (700, 1024, 1500))):
            for knob in knobs:
                rows = {name: self.stream(data, mode=mode, knob=knob, amplitude=lambda ms: amplitude, end_ms=1600)
                        for name, data in (('PN1.24', PARENT), ('PN1.26', CANDIDATE))}
                tone = {name: self.sounding(row, 800, 1600) / 800 for name, row in rows.items()}
                print('mode', mode, 'amplitude', amplitude, 'knob', knob,
                      {k: round(v, 2) for k, v in tone.items()})
                self.assertEqual(tone['PN1.24'], 0.0, (mode, knob))
                self.assertGreater(tone['PN1.26'], 0.1, (mode, knob))

    TARGET, NEIGHBOUR, SEGMENT = 30000, 6000, 1200

    def pairs(self, ms):
        return self.TARGET if (ms // self.SEGMENT) % 2 == 0 else self.NEIGHBOUR

    def test_cabinet_neighbour_muted_in_the_lower_half_both_sound_above(self):
        for mode, knob in ((0, 300), (1, 600)):
            for data, knob_used in ((PARENT, knob), (CANDIDATE, 3000), (CANDIDATE, knob)):
                row = self.stream(data, mode=mode, knob=knob_used, amplitude=self.pairs, end_ms=6000)
                duty = [self.sounding(row, n * self.SEGMENT + 500, (n + 1) * self.SEGMENT) / (self.SEGMENT - 500)
                        for n in range(5)]
                name = 'PN1.26' if data is CANDIDATE else 'PN1.24'
                print('mode', mode, name, 'knob', knob_used, 'tone fraction per segment',
                      [round(d, 2) for d in duty])
                if data is CANDIDATE and knob_used == knob:
                    self.assertGreater(min(duty[2], duty[4]), 0.1, 'target sounds')
                    self.assertEqual(duty[3], 0.0, 'neighbour muted next to the target')
                else:
                    self.assertTrue(all(d > 0.3 for d in duty[2:]), 'both sound')

    def test_dwelling_on_the_neighbour_lets_it_sound_after_the_peak_fades(self):
        amplitude = lambda ms: self.TARGET if ms < 3000 else self.NEIGHBOUR
        row = self.stream(CANDIDATE, mode=1, knob=600, amplitude=amplitude, end_ms=9000)
        first = next((when for when, on in row['edges'] if on and when > 3100), None)
        print('neighbour first sounds', None if first is None else round(first - 3000), 'ms after leaving the target')
        self.assertIsNotNone(first)
        self.assertGreater(first - 3000, 1500)
        self.assertLess(first - 3000, 5000)


if __name__ == '__main__':
    unittest.main()
