"""PN1.28: the strongest recent pair on the fastest rhythm point, fast gain attack.

The analysers, publisher, AGC, sampler and speaker of the built image execute in
Unicorn; ADC values, the analogue link, the coupling between pairs and interrupt
arrival are modeled. The arithmetic is checked against an independent model of its
stated rules and against PN1.27. None of this measures pickup, real coupling
between pairs or loudness.
"""
import contextlib
import hashlib
import io
import struct
import unittest

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_MCLASS

import auto_range
import isolate
import knob_reference as pn127
import pair_rank as rank
import relative_isolate as pn126
import rx_precision
import sample_age_guard
import test_rx_digital_strong_gain as strong
import test_rx_gain_response as response
import test_rx_knob_reference as t127
import test_rx_relative_isolate as base
from lpm10rx import symbols
from lpm10rx.container import unwrap, wrap
from lpm10rx.image import PatchError
from sampling_fixes import GATE_STATE
from test_rx_isolate import Streams, analog_windows, clipped_digital, digital_windows, smoothed, walk
from verify_digital import ACTIVE, BUFFER

PN124 = PN127 = CANDIDATE = IMG = None
CANDIDATE_SHA256 = '0e4b34b2347b1054035194500e1885fffeb1a90ed57753739ed4a2fbb8f5a619'
MULT = base.MULT
KNOBS = t127.KNOBS + t127.TOP_KNOBS
DIGITAL_HOLD, ANALOG_HOLD = t127.DIGITAL_HOLD, t127.ANALOG_HOLD


def setUpModule():
    global PN124, PN127, CANDIDATE, IMG
    with contextlib.redirect_stdout(io.StringIO()):
        PN124 = bytes(rx_precision.build_candidate().data)
        PN127 = bytes(pn127.build_candidate().data)
        IMG = rank.build_candidate()
    CANDIDATE = bytes(IMG.data)


def model(raw, level, knob_raw, peak, elapsed):
    """(quiet interval or None when muted, new peak, unfinished decay ticks)."""
    score = raw & 0xFFFFFFFF
    if level <= 7:
        score = ((score * MULT[level]) & 0xFFFFFFFF) // 10
    score = min(score, pn127.CLAMP)
    peak, rest = base.decayed(peak, elapsed)
    peak = max(peak, score)
    w = pn126.window(knob_raw)
    if w is not None and score < (peak * w >> 8):
        return None, peak, rest
    return walk(score * rank.reference(knob_raw, peak) >> 8), peak, rest


class Analysers(base.Analysers):
    def entry(self, data):
        return isolate.OLD_CURVE if data is PN124 else IMG.knob_reference['curve']

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


class Build(unittest.TestCase):
    def test_parent_is_pinned_and_only_declared_sites_change(self):
        self.assertEqual(IMG.pair_rank['start'], symbols.APP_BASE + len(PN127))
        allowed = set()
        for site, size in ((rank.SITE, 4), (rank.AGC_SITE, 4), (0x0800CDE4, 8)):
            allowed |= set(range(site, site + size))
        changed = {symbols.APP_BASE + i for i, (a, b) in enumerate(zip(PN127, CANDIDATE)) if a != b}
        self.assertLessEqual(changed, allowed)
        for site in (rank.SITE, rank.AGC_SITE, 0x0800CDE4):
            self.assertTrue(changed & set(range(site, site + 8)), hex(site))
        self.assertEqual(len(CANDIDATE) - len(PN127), IMG.pair_rank['helper_bytes'])
        self.assertLessEqual(symbols.APP_BASE + len(CANDIDATE), symbols.EXTEND_LIMIT)
        self.assertEqual(CANDIDATE[0x0800CDE4 - symbols.APP_BASE:][:8], b'PN1.28\0\0')

    def test_changed_parent_is_rejected_before_any_byte_changes(self):
        for site in (rank.SITE, rank.AGC_SITE + 4, 0x0800CDE4):
            with self.subTest(site=hex(site)):
                img = pn127.build_candidate()
                img.data[img.f(site)] ^= 1
                before = bytes(img.data), list(img.log)
                with self.assertRaises(PatchError):
                    rank.apply(img)
                self.assertEqual((bytes(img.data), img.log), before)

    def test_written_candidate_is_this_exact_build(self):
        self.assertEqual(hashlib.sha256(CANDIDATE).hexdigest(), CANDIDATE_SHA256)
        raw, update = rank.DIRECTORY / rank.OUTPUT, rank.DIRECTORY / rank.UPDATE
        if not raw.exists():
            self.skipTest('experimental PN1.28 files not written yet (python pair_rank.py --write)')
        self.assertEqual(raw.read_bytes(), CANDIDATE)
        self.assertEqual(update.read_bytes(), wrap(CANDIDATE))
        self.assertEqual(unwrap(update.read_bytes())[1], CANDIDATE)
        sums = (rank.DIRECTORY / rank.SUMS).read_text(encoding='ascii').split()
        self.assertEqual(sums, [CANDIDATE_SHA256, rank.OUTPUT, hashlib.sha256(wrap(CANDIDATE)).hexdigest(), rank.UPDATE])

    def test_no_branch_lands_inside_replaced_instructions(self):
        forbidden = {rank.SITE + 2, rank.AGC_SITE + 2}
        conditions = ('eq', 'ne', 'hs', 'cs', 'lo', 'cc', 'mi', 'pl', 'vs', 'vc', 'hi', 'ls', 'ge', 'lt', 'gt', 'le')
        branches = {'b', 'bl', 'cbz', 'cbnz'} | {'b' + c for c in conditions}
        md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS)
        md.skipdata = True
        hits, seen = [], 0
        for skew in (0, 2):
            for insn in md.disasm(CANDIDATE[skew:], symbols.APP_BASE + skew):
                if insn.mnemonic.split('.')[0] in branches and '#' in insn.op_str:
                    seen += 1
                    if int(insn.op_str.split('#')[-1], 16) in forbidden:
                        hits.append((hex(insn.address), insn.mnemonic))
        self.assertGreater(seen, 1000)
        self.assertEqual(hits, [])

    def test_reference_law(self):
        peaks = (0, 1, 39_999, 40_000, 40_001, 60_000, 126_510, 400_000, 1_000_000, pn127.CLAMP)
        for knob_raw in range(0, 4096, 5):
            k = pn127.reference(knob_raw)
            for peak in peaks:
                ref = rank.reference(knob_raw, peak)
                self.assertLessEqual(ref, k)
                if peak <= rank.FASTEST_SCORE or peak * k >> 8 < rank.FASTEST_SCORE:
                    self.assertEqual(ref, k, (knob_raw, peak))       # PN1.27 wherever the peak fits the curve
                else:
                    self.assertGreaterEqual(peak * ref >> 8, rank.FASTEST_SCORE, (knob_raw, peak))
                    self.assertLess(peak * (ref - 1) >> 8, rank.FASTEST_SCORE, (knob_raw, peak))


class Digital(Analysers, unittest.TestCase):
    def test_every_knob_position_follows_the_model(self):
        cases = slid = 0
        for knob_raw in KNOBS:
            for level in (0, 1, 2, 7):
                for grade, recent in ((0, 0), (45, 800)):
                    for peak, elapsed in base.PEAKS:
                        for name, samples in digital_windows():
                            kw = dict(knob=knob_raw, level=level, grade=grade, recent=recent)
                            parent_state, parent_scores = self.analyse(PN124, samples, **kw)[:2]
                            state, scores, stored = self.analyse(CANDIDATE, samples, peak=peak, elapsed=elapsed, **kw)
                            self.assertEqual(scores, parent_scores)
                            if not scores:
                                self.assertEqual(state, parent_state)
                                continue
                            want = self.expected(parent_state, scores[0], mode=0, knob=knob_raw, level=level,
                                                 grade=grade, recent=recent, gap=0, peak=peak, elapsed=elapsed)
                            self.assertEqual((state, stored), want, (knob_raw, level, name, grade, peak, elapsed))
                            cases += 1
                            slid += rank.reference(knob_raw, stored[0]) < pn127.reference(knob_raw)
        self.assertGreater(slid, 1000, 'the new reference is exercised')
        print('Digital model vectors:', cases, 'with the curve slid to the peak:', slid)

    def test_pn127_wherever_the_peak_fits_the_curve(self):
        same = differ = 0
        for knob_raw in KNOBS[::2]:
            for level in (0, 2, 7):
                for peak, elapsed in base.PEAKS:
                    for name, samples in digital_windows():
                        kw = dict(knob=knob_raw, level=level, peak=peak, elapsed=elapsed)
                        new = self.analyse(CANDIDATE, samples, **kw)
                        old = self.analyse(PN127, samples, **kw)
                        self.assertEqual(new[2], old[2], 'the peak and its decay are PN1.27\'s')
                        if not new[1] or rank.reference(knob_raw, new[2][0]) == pn127.reference(knob_raw):
                            self.assertEqual(new[0], old[0], (knob_raw, level, name, peak))
                            same += 1
                        else:
                            differ += 1
        self.assertGreater(differ, 100)
        print('Digital vectors identical to PN1.27:', same, 'ranked against the peak instead:', differ)

    def test_clipped_window(self):
        for name, samples in clipped_digital():
            for knob_raw in t127.TOP_KNOBS:
                for peak in (0, 400_000):
                    self.assertEqual(self.analyse(CANDIDATE, samples, knob=knob_raw, peak=peak)[:2],
                                     self.analyse(PN127, samples, knob=knob_raw, peak=peak)[:2])
            for knob_raw in t127.KNOBS:
                for level in (0, 2, 7):
                    for peak, elapsed in base.PEAKS[:6]:
                        state, scores, stored = self.analyse(CANDIDATE, samples, knob=knob_raw, level=level,
                                                             peak=peak, elapsed=elapsed)
                        self.assertEqual(scores, (pn127.SATURATION_SCORE,))
                        parent_state = self.analyse(PN124, samples, knob=knob_raw, level=level)[0]
                        want = self.expected(parent_state, pn127.SATURATION_SCORE, mode=0, knob=knob_raw,
                                             level=level, grade=0, recent=0, gap=0, peak=peak, elapsed=elapsed)
                        self.assertEqual((state, stored), want, (name, knob_raw, level, peak))


class Analog(Analysers, unittest.TestCase):
    def test_every_knob_position_follows_the_model(self):
        cases = slid = 0
        for knob_raw in KNOBS[2:]:
            for level in (0, 2, 7):
                for grade, recent, gap in ((0, 0, 0), (45, 800, 90)):
                    for peak, elapsed in base.PEAKS:
                        for name, samples in analog_windows():
                            kw = dict(mode=1, knob=knob_raw, level=level, grade=grade, recent=recent, gap=gap)
                            parent_state, parent_scores = self.analyse(PN124, samples, **kw)[:2]
                            state, scores, stored = self.analyse(CANDIDATE, samples, peak=peak, elapsed=elapsed, **kw)
                            self.assertEqual(scores, parent_scores)
                            if not scores:
                                self.assertEqual(state, parent_state)
                                continue
                            want = self.expected(parent_state, scores[0], mode=1, knob=knob_raw, level=level,
                                                 grade=grade, recent=recent, gap=gap, peak=peak, elapsed=elapsed)
                            self.assertEqual((state, stored), want, (knob_raw, level, name, peak, elapsed))
                            cases += 1
                            slid += rank.reference(knob_raw, stored[0]) < pn127.reference(knob_raw)
        self.assertGreater(slid, 100)
        print('Analog model vectors:', cases, 'with the curve slid to the peak:', slid)


class AttackStreams(unittest.TestCase):
    """The PN1.24 AGC stream fixture, knob at 4 060 (upper half: tracing ceiling 7)."""
    execute = response.GainResponseStreams.execute
    boundary = response.GainResponseStreams.boundary
    timers = response.GainResponseStreams.timers
    run_stream = response.GainResponseStreams.run_stream

    @classmethod
    def setUpClass(cls):
        cls.previous, cls.data = PN127, CANDIDATE

    def test_saturation_steps_down_every_half_second_without_dropout(self):
        for mode in (0, 1):
            with self.subTest(mode=mode):
                old = self.run_stream(mode=mode, previous=True, changes={}, end_ms=2900, source_pp=20000)
                self.assertEqual(old['transitions'], [(500, 7, 2), (1500, 2, 1), (2500, 1, 0)])
                row = self.run_stream(mode=mode, changes={}, end_ms=2900, source_pp=20000)
                self.assertEqual(row['transitions'], [(500, 7, 2), (1000, 2, 1), (1500, 1, 0)])
                self.assertFalse(row['unowned_refreshes'])
                self.assertLess(row['max_quiet_ms'], 150, row['quiet'])
                self.assertGreater(row['final_grade'], 0)

    def test_step_up_keeps_the_one_second_hold(self):
        for mode in (0, 1):
            with self.subTest(mode=mode):
                row = self.run_stream(mode=mode, changes={}, end_ms=1800,
                                      source_pp=lambda ms: 2400 if ms < 1000 else 800)
                self.assertEqual(row['transitions'], [(500, 7, 2), (1500, 2, 7)])
                self.assertFalse(row['unowned_refreshes'])
                self.assertLess(row['max_quiet_ms'], 150)
                weak = self.run_stream(mode=mode, changes={}, end_ms=3600,
                                       source_pp=lambda ms: 20000 if ms < 1000 else 300)
                ups = [t for t in weak['transitions'] if t[2] > t[1]]
                self.assertEqual([ms for ms, _, _ in ups], [1500, 2500, 3500][:len(ups)], weak['transitions'])
                self.assertGreaterEqual(len(ups), 2)

    def test_near_boundary_static_inputs_do_not_hunt(self):
        for mode in (0, 1):
            for amplitude, expected in ((1850, []), (1950, [(500, 7, 2)]), (1170, []), (800, [])):
                with self.subTest(mode=mode, amplitude=amplitude):
                    row = self.run_stream(mode=mode, changes={}, end_ms=3300, source_pp=amplitude)
                    self.assertEqual(row['transitions'], expected)
                    self.assertFalse(row['unowned_refreshes'])


class AttackInstructions(unittest.TestCase):
    execute = response.GainResponseInstructions.execute
    boundary = response.GainResponseInstructions.boundary
    timers = response.GainResponseInstructions.timers
    cpu = response.GainResponseInstructions.cpu
    select = response.GainResponseInstructions.select

    @classmethod
    def setUpClass(cls):
        cls.previous, cls.data = PN127, CANDIDATE

    def test_hold_is_zero_after_a_step_down_and_one_after_a_step_up(self):
        for mode in (0, 1):
            for level, pp, wanted, hold in ((7, 1900, 2, 0), (2, 2400, 1, 0), (1, 2400, 0, 0),
                                            (0, 100, 1, 1), (1, 100, 2, 1), (2, 448, 7, 1), (7, 1898, 7, 0)):
                with self.subTest(mode=mode, level=level, pp=pp):
                    c = self.cpu(mode=mode, level=level, pp=pp)
                    self.assertEqual(self.select(c), wanted)
                    self.assertEqual(c.read(auto_range.STATE + 2), hold)
                    old = self.cpu(mode=mode, level=level, pp=pp, previous=True)
                    self.assertEqual(self.select(old), wanted, 'thresholds and steps are PN1.24\'s')
                    self.assertEqual(old.read(auto_range.STATE + 2), 1 if wanted != level else 0)

    def test_incomplete_closed_pending_or_expired_windows_cannot_drive_gain(self):
        for mode in (0, 1):
            for field, value in ((sample_age_guard.COMPLETED_VALID, 0), (GATE_STATE, 0), (GATE_STATE, 1),
                                 (GATE_STATE, 3), (0x20000049, 1), (0x20000049, 2)):
                with self.subTest(mode=mode, field=hex(field), value=value):
                    c = self.cpu(mode=mode, pp=2400)
                    (c.w32 if field == sample_age_guard.COMPLETED_VALID else c.w8)(field, value)
                    self.assertEqual(self.select(c), 7)
            limit = (sample_age_guard.DIGITAL_MAX_AGE_TICKS, sample_age_guard.ANALOG_MAX_AGE_TICKS)[mode]
            for elapsed, wanted in ((limit, 2), (limit + 1, 7)):
                c = self.cpu(mode=mode, pp=2400)
                c.w32(sample_age_guard.COMPLETED_AT, 100000)
                c.w32(sample_age_guard.TIMER_COUNTER, 100000 + elapsed)
                self.assertEqual(self.select(c), wanted)

    def test_partial_new_gain_buffer_cannot_trigger_a_second_change(self):
        # Without the hold, only the freshness guard stands between one step down and the
        # next: the window after a change must be complete and acquired at the new gain.
        for mode, irqs in ((0, 6000), (1, 200)):
            with self.subTest(mode=mode):
                c = strong.GainStreamCPU(self.data, mode=mode)
                self.boundary(c)
                c.uc.mem_write(BUFFER, struct.pack('<64H', *([848, 3248] * 32)))
                c.w32(sample_age_guard.COMPLETED_VALID, 1)
                self.assertEqual(self.select(c), 2)
                self.assertEqual(c.read(auto_range.STATE + 2), 0, 'no hold after the step down')
                self.boundary(c)
                self.timers(c, irqs)
                self.assertEqual(c.read(ACTIVE), 1)
                self.assertEqual(self.select(c), 2)
                self.assertEqual(c.read(GATE_STATE), 2)
                self.assertEqual(c.read(sample_age_guard.COMPLETED_VALID, 4), 0)


class Field(Streams):
    SEGMENT = 1200

    def duty(self, data, mode, knob_raw, target, neighbour):
        pairs = lambda ms: target if (ms // self.SEGMENT) % 2 == 0 else neighbour
        row = self.stream(data, mode=mode, knob=knob_raw, amplitude=pairs, end_ms=6000)
        return [self.sounding(row, n * self.SEGMENT + 500, (n + 1) * self.SEGMENT) / (self.SEGMENT - 500)
                for n in range(5)]

    def test_full_knob_ranks_the_toned_pair_from_the_first_touch(self):
        # (toned pair, neighbour) in modeled link units: 3 000 settles at gain level 2 within
        # 0.5 s, 10 000 at level 1, 30 000 needs level 0 (about 1.5 s).
        for mode in (0, 1):
            for target, neighbour in ((3000, 1500), (3000, 600), (10000, 5000), (10000, 2000), (30000, 6000)):
                with self.subTest(mode=mode, target=target, neighbour=neighbour):
                    duty = self.duty(CANDIDATE, mode, 4095, target, neighbour)
                    print('mode', mode, 'PN1.28 knob 100 %', target, neighbour, 'tone fraction T N T N T',
                          [round(d, 2) for d in duty])
                    toned = min(duty[0], duty[2], duty[4])
                    self.assertGreater(toned, duty[1] + 0.1, 'first touch of the neighbour slower')
                    self.assertGreater(toned, duty[3] + 0.1, 'second touch of the neighbour slower')

    def test_pn127_negative_control_plays_every_pair_the_same(self):
        for mode in (0, 1):
            duty = self.duty(PN127, mode, 4095, 10000, 5000)
            self.assertLess(max(duty) - min(duty), 0.05, duty)

    def test_low_knob_still_mutes_the_neighbour(self):
        for mode, low in ((0, 300), (1, 600)):
            duty = self.duty(CANDIDATE, mode, low, 30000, 6000)
            self.assertGreater(min(duty[2], duty[4]), 0.1, 'toned pair sounds')
            self.assertEqual(duty[3], 0.0, 'neighbour muted next to the toned pair')

    def test_lone_moderate_cable_is_pn127(self):
        for mode in (0, 1):
            for knob_raw in (700, 2048, 4095):
                with self.subTest(mode=mode, knob=knob_raw):
                    new = self.stream(CANDIDATE, mode=mode, knob=knob_raw, amplitude=lambda ms: 600, end_ms=1600)
                    old = self.stream(PN127, mode=mode, knob=knob_raw, amplitude=lambda ms: 600, end_ms=1600)
                    self.assertEqual(new['publications'], old['publications'])
                    self.assertEqual(new['levels'], old['levels'])


if __name__ == '__main__':
    unittest.main()
