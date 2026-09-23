"""PN1.25: the knob law, louder beeps and NCV gain, on the actual ARM code.

The Digital, Analog and Mains analysers, publisher, AGC, sampler and speaker
of the built image execute in Unicorn. ADC values, the analogue link (a gain
ratio per driven level and a front-end limit) and interrupt arrival are
modeled. The Isolate arithmetic is checked against an independent model of its
stated rules; the upper half of the knob against PN1.24. None of this measures
pickup distance, coupling between real pairs, loudness or selectivity in a
cabinet.
"""
import contextlib
import hashlib
import io
import math
import random
import struct
import unittest

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_MCLASS
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_PRIMASK, UC_ARM_REG_R0

import auto_range
import isolate
import rx_precision
import sample_age_guard
import test_rx_auto_range_freshness as agc
import test_rx_digital_strong_gain as strong
import test_rx_followup as followup
import test_rx_tracking_streams as streams
from lpm10rx import symbols
from lpm10rx.container import unwrap, wrap
from lpm10rx.image import PatchError
from test_rx_analog_fast import corpus as analog_corpus, sine
from test_rx_followup import ANALYZERS, GATE_STATE, GRADE, REQUEST
from test_scan_acquisition_timing import TIMER_COUNTER
from verify_control import BEEP, MODE, SP
from verify_digital import ACTIVE, BUFFER, GAP, GATE, RECENT, pattern

PARENT = CANDIDATE = IMG = None
CANDIDATE_SHA256 = 'c8617ea67228d86bad30a80af1f5e0d4f8fd3ae55983c81761e541efd362be95'
MULT = (200, 92, 26, 26, 11, 11, 11, 10)
ISOLATE_KNOBS = (0, 2, 300, 580, 700, 800, 1024, 1300, 1536, 1700, 1792, 1900, 2000, 2047)
SEARCH_KNOBS = (2048, 3000, 4095)
DIGITAL_HOLD, ANALOG_HOLD = 660, 560
CCR4 = 0x40000C40


def setUpModule():
    global PARENT, CANDIDATE, IMG
    with contextlib.redirect_stdout(io.StringIO()):
        PARENT = bytes(rx_precision.build_candidate().data)
    IMG = isolate.build_candidate()
    CANDIDATE = bytes(IMG.data)


# ---------------------------------------------------------------- reference model
def walk(score, segments=isolate.LOCATE_SEGMENTS):
    for span, start, end in segments:
        if score < span:
            return start - (start - end) * score // span
        score -= span
    return isolate.FASTEST_MS


def target(raw, level, knob):
    """Quiet interval the curve aims at, or None for a muted (rejected) window."""
    score = raw & 0xFFFFFFFF
    if level <= 7:
        score = ((score * MULT[level]) & 0xFFFFFFFF) // 10
    law = isolate.knob_law(knob)
    if law is None:
        return walk(score)
    k, floor = law
    score = min(score, isolate.CLAMP) * k >> 8
    if score < floor:
        return None
    if score < isolate.SATURATION_SCORE:
        score = (score - floor) * isolate.SATURATION_SCORE // (isolate.SATURATION_SCORE - floor)
    return walk(score)


def smoothed(aim, published, recent):
    if recent <= 500 or published <= 1:
        return aim
    half = int((aim - published) / 2)
    return published if abs(half) < 3 else published + half


def knob_code(knob):
    return min(knob // 580, 7)


# ---------------------------------------------------------------- analyser harness
class Analysers:
    execute = followup.Followup.execute

    def curve_entry(self, data):
        return IMG.isolate['curve'] if data is CANDIDATE else isolate.OLD_CURVE

    def fresh(self, c, *, mode, knob, level, grade, recent, gap=0):
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
        c.w32(sample_age_guard.COMPLETED_AT, 0xfffffff0)
        c.w32(sample_age_guard.TIMER_COUNTER, 0xfffffff0)
        c.w32(sample_age_guard.COMPLETED_VALID, 1)

    def analyse(self, data, samples, *, mode=0, knob=4095, level=7, grade=0, recent=0, gap=0, mask=0):
        c = streams.StreamCPU(data)
        self.fresh(c, mode=mode, knob=knob, level=level, grade=grade, recent=recent, gap=gap)
        if mode == 0:
            self.assertEqual(len(samples), 48)
            c.uc.mem_write(BUFFER, struct.pack('<48H', *samples) + bytes([0xA5] * 32))
        else:
            self.assertEqual(len(samples), 64)
            c.uc.mem_write(BUFFER, struct.pack('<64H', *samples))
        c.uc.reg_write(UC_ARM_REG_PRIMASK, mask)
        scores = []
        entry = self.curve_entry(data)
        hook = c.uc.hook_add(UC_HOOK_CODE, lambda uc, a, s, u: scores.append(uc.reg_read(UC_ARM_REG_R0)),
                             begin=entry, end=entry)
        try:
            self.execute(c, ANALYZERS[mode], budget=150000)
        finally:
            c.uc.hook_del(hook)
        self.assertEqual(c.uc.reg_read(UC_ARM_REG_PRIMASK), mask)
        state = tuple(c.read(a, n) for a, n in
                      ((GRADE, 1), (RECENT, 2), (ACTIVE, 1), (0x2000005B, 1), (BEEP, 1), (GAP, 1)))
        return state, tuple(scores)

    def expected(self, parent_state, raw, *, mode, knob, level, grade, recent, gap):
        """PN1.25 state from the model, given PN1.24's run of the same window."""
        aim = target(raw, level, knob)
        hold = DIGITAL_HOLD if mode == 0 else ANALOG_HOLD
        if aim is None:
            new_grade, new_recent, new_gap = grade, min(recent, hold), gap
        else:
            new_grade = smoothed(aim, grade, recent)
            new_recent, new_gap = (800, gap) if mode == 0 else (600, min(gap, new_grade))
        return (new_grade, new_recent) + parent_state[2:4] + (parent_state[4], new_gap)


def digital_windows():
    for phase in (0, 3, 5):
        for amplitude in (12, 40, 100, 300, 800, 1600, 2400, 3000):
            yield f'b6_{phase}_{amplitude}', pattern(phase, 800, 800 + amplitude)
    for phase in (1, 6):
        yield f'b6_dc_{phase}', pattern(phase, 3000, 3900)


def clipped_digital():
    for phase in range(0, 8, 3):
        for low in (0, 1000, 3000):
            yield f'rail_{phase}_{low}', pattern(phase, low, 4095)


def analog_windows():
    for amplitude in (14, 30, 60, 150, 400, 900, 1600, 2000):
        for phase in (0, 1.1):
            yield f'sine_{amplitude}_{phase}', sine(amplitude=amplitude, phase=phase)


class Build(unittest.TestCase):
    def test_parent_is_pinned_and_only_declared_sites_change(self):
        self.assertEqual(len(PARENT), 27464)
        start = IMG.isolate['start']
        self.assertEqual(start, symbols.APP_BASE + len(PARENT))
        allowed = set()
        for site, size in ((isolate.GAP_ENTRY, 4), (isolate.DIGITAL_UNCERTAIN, 4),
                           (isolate.ANALOG_SITE, 24), (isolate.GAIN_SITE, 4),
                           (isolate.TONE_HIGH, 4), (isolate.TONE_LOW, 4), (0x0800CDE4, 8)):
            allowed |= set(range(site, site + size))
        changed = {symbols.APP_BASE + i for i, (a, b) in enumerate(zip(PARENT, CANDIDATE)) if a != b}
        self.assertTrue(changed)
        self.assertLessEqual(changed, allowed)
        self.assertEqual(len(CANDIDATE) - len(PARENT), IMG.isolate['helper_bytes'])
        self.assertLessEqual(symbols.APP_BASE + len(CANDIDATE), symbols.EXTEND_LIMIT)
        self.assertEqual(CANDIDATE[0x0800CDE4 - symbols.APP_BASE:][:8], b'PN1.25\0\0')
        self.assertEqual(IMG.isolate['persistent_ram_bytes'], 0)
        tail = CANDIDATE[isolate.ANALOG_SITE - symbols.APP_BASE + 4:][:20]
        self.assertEqual(tail, bytes.fromhex('00bf') * 10)

    def test_changed_parent_is_rejected_before_any_byte_changes(self):
        with contextlib.redirect_stdout(io.StringIO()):
            img = rx_precision.build_candidate()
        img.data[img.f(isolate.TONE_LOW)] ^= 1
        before = bytes(img.data), list(img.log)
        with self.assertRaises(PatchError):
            isolate.apply(img)
        self.assertEqual((bytes(img.data), img.log), before)
        with self.assertRaises(PatchError):
            isolate.apply(IMG)

    def test_update_container_round_trips(self):
        update = wrap(CANDIDATE)
        self.assertEqual(len(update) % 0x1000, 0)
        self.assertEqual(unwrap(update)[1], CANDIDATE)

    def test_written_candidate_is_this_exact_build(self):
        raw, update = isolate.DIRECTORY / isolate.OUTPUT, isolate.DIRECTORY / isolate.UPDATE
        if CANDIDATE_SHA256:
            self.assertEqual(hashlib.sha256(CANDIDATE).hexdigest(), CANDIDATE_SHA256)
        if not raw.exists():
            self.skipTest('experimental PN1.25 files not written yet (python isolate.py --write)')
        self.assertEqual(raw.read_bytes(), CANDIDATE)
        self.assertEqual(update.read_bytes(), wrap(CANDIDATE))
        sums = (isolate.DIRECTORY / isolate.SUMS).read_text(encoding='ascii').split()
        self.assertEqual(sums, [hashlib.sha256(CANDIDATE).hexdigest(), isolate.OUTPUT,
                                hashlib.sha256(wrap(CANDIDATE)).hexdigest(), isolate.UPDATE])

    def test_no_branch_lands_inside_replaced_instructions(self):
        forbidden = {isolate.DIGITAL_UNCERTAIN + 2, isolate.GAP_ENTRY + 2, isolate.GAIN_SITE + 2,
                     isolate.TONE_HIGH + 2, isolate.TONE_LOW + 2}
        forbidden |= set(range(isolate.ANALOG_SITE + 2, isolate.ANALOG_SITE + 24, 2))
        replaced = set(range(isolate.ANALOG_SITE, isolate.ANALOG_SITE + 24))
        conditions = ('eq', 'ne', 'hs', 'cs', 'lo', 'cc', 'mi', 'pl', 'vs', 'vc',
                      'hi', 'ls', 'ge', 'lt', 'gt', 'le')
        branches = {'b', 'bl', 'cbz', 'cbnz'} | {'b' + c for c in conditions}
        md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS)
        md.skipdata = True
        for name, data in (('PN1.24', PARENT), ('PN1.25', CANDIDATE)):
            hits, seen = [], 0
            # Two sweeps (even and odd halfword starts) catch branches that a
            # single linear sweep could misalign behind a 32-bit instruction.
            for skew in (0, 2):
                for insn in md.disasm(data[skew:], symbols.APP_BASE + skew):
                    if insn.mnemonic.split('.')[0] in branches and '#' in insn.op_str:
                        seen += 1
                        dest = int(insn.op_str.split('#')[-1], 16)
                        if dest in forbidden and insn.address not in replaced:
                            hits.append((hex(insn.address), insn.mnemonic, hex(dest)))
            self.assertGreater(seen, 1000, name)
            self.assertEqual(hits, [], name)

    def test_knob_law_tables_and_model(self):
        laws = [isolate.knob_law(k) for k in range(4096)]
        self.assertTrue(all(law is None for law in laws[isolate.SEARCH_RAW:]))
        self.assertTrue(all(law is not None for law in laws[:isolate.SEARCH_RAW]))
        refs = [law[0] for law in laws[:isolate.SEARCH_RAW]]
        floors = [law[1] for law in laws[:isolate.SEARCH_RAW]]
        self.assertEqual(refs, sorted(refs), 'reference rises with the knob')
        self.assertEqual(floors, sorted(floors, reverse=True), 'floor falls with the knob')
        self.assertEqual((min(refs), max(refs)), (4, 255))
        self.assertEqual((max(floors), min(floors)), (7200, 2))
        audible_floor = [law[1] * 256 // law[0] for law in laws[:isolate.SEARCH_RAW]]
        self.assertEqual(audible_floor, sorted(audible_floor, reverse=True),
                         'the weakest audible strength never falls as the knob turns down')
        raw = bytes(CANDIDATE[IMG.isolate['curve'] - symbols.APP_BASE:IMG.isolate['digital'] - symbols.APP_BASE])
        self.assertIn(struct.pack(f'<{2 * len(isolate.KNOB_REFERENCE)}H',
                                  *isolate.KNOB_REFERENCE, *isolate.KNOB_FLOOR), raw)


class Digital(Analysers, unittest.TestCase):
    def test_upper_half_is_pn124_for_every_window_level_and_rhythm_state(self):
        cases = 0
        windows = list(digital_windows()) + list(clipped_digital())
        rng = random.Random(0x125D)
        windows += [(f'noise_{n}', [rng.randrange(4096) for _ in range(48)]) for n in range(12)]
        windows += [(f'dc_{v}', [v] * 48) for v in (0, 2048, 4095)]
        for knob in SEARCH_KNOBS:
            for level in (0, 1, 2, 5, 7):
                for grade, recent in ((0, 0), (20, 800), (65, 700), (110, 501)):
                    for name, samples in windows:
                        kwargs = dict(knob=knob, level=level, grade=grade, recent=recent, mask=cases & 1)
                        self.assertEqual(self.analyse(CANDIDATE, samples, **kwargs),
                                         self.analyse(PARENT, samples, **kwargs), (knob, level, name, grade))
                        cases += 1
        print('Digital upper-half vectors identical to PN1.24:', cases)

    def test_lower_half_follows_the_reference_model(self):
        cases = muted = sounding = 0
        for knob in ISOLATE_KNOBS:
            for level in range(8):
                for grade, recent in ((0, 0), (45, 800), (90, 700)):
                    for name, samples in digital_windows():
                        kwargs = dict(knob=knob, level=level, grade=grade, recent=recent)
                        parent_state, parent_scores = self.analyse(PARENT, samples, **kwargs)
                        state, scores = self.analyse(CANDIDATE, samples, **kwargs)
                        self.assertEqual(scores, parent_scores, 'the raw score is unchanged')
                        if not scores:
                            self.assertEqual(state, parent_state, name)
                            continue
                        want = self.expected(parent_state, scores[0], mode=0, knob=knob, level=level,
                                             grade=grade, recent=recent, gap=0)
                        self.assertEqual(state, want, (knob, level, name, grade, recent, scores))
                        cases += 1
                        muted += target(scores[0], level, knob) is None
                        sounding += target(scores[0], level, knob) is not None
        self.assertGreater(muted, 100)
        self.assertGreater(sounding, 100)
        print('Digital lower-half vectors:', cases, 'muted', muted, 'sounding', sounding)

    def test_clipped_window_counts_as_saturation_at_the_driven_gain(self):
        cases = 0
        for name, samples in clipped_digital():
            parent_state, parent_scores = self.analyse(PARENT, samples)
            self.assertEqual(parent_scores, ())
            self.assertEqual(parent_state[:2], (20, 800), 'PN1.24 plays a clipped window fastest')
            self.assertEqual(self.analyse(CANDIDATE, samples)[0], parent_state, 'upper half: unchanged')
            for knob in ISOLATE_KNOBS:
                for level in (0, 1, 2, 7):
                    state, scores = self.analyse(CANDIDATE, samples, knob=knob, level=level)
                    self.assertEqual(scores, (isolate.SATURATION_SCORE,), name)
                    parent_state = self.analyse(PARENT, samples, knob=knob, level=level)[0]
                    want = self.expected(parent_state, isolate.SATURATION_SCORE, mode=0, knob=knob,
                                         level=level, grade=0, recent=0, gap=0)
                    self.assertEqual(state, want, (name, knob, level))
                    cases += 1
        print('Digital clipped lower-half vectors:', cases)

    def test_muted_window_releases_like_a_lost_signal(self):
        weak = pattern(0, 800, 800 + 60)
        knob = 700
        state, scores = self.analyse(CANDIDATE, weak, knob=knob, level=7, grade=45, recent=800)
        self.assertTrue(scores)
        self.assertIsNone(target(scores[0], 7, knob))
        self.assertEqual(state[:2], (45, DIGITAL_HOLD), 'rhythm kept only for the release hold')
        state, _ = self.analyse(CANDIDATE, weak, knob=knob, level=7, grade=45, recent=600)
        self.assertEqual(state[:2], (45, 600), 'the hold never extends the countdown')


class Analog(Analysers, unittest.TestCase):
    def test_upper_half_is_pn124_for_the_analog_corpus(self):
        cases = 0
        windows = list(analog_corpus()) + list(analog_windows())
        for knob in (2048, 4095):
            for level in (0, 2, 7):
                for grade, recent, gap in ((0, 0, 0), (45, 800, 90), (20, 700, 10)):
                    for name, samples in windows:
                        kwargs = dict(mode=1, knob=knob, level=level, grade=grade, recent=recent, gap=gap,
                                      mask=cases & 1)
                        self.assertEqual(self.analyse(CANDIDATE, samples, **kwargs),
                                         self.analyse(PARENT, samples, **kwargs), (knob, level, name))
                        cases += 1
        print('Analog upper-half vectors identical to PN1.24:', cases)

    def test_lower_half_follows_the_model_and_mute_skips_the_refresh(self):
        cases = muted = 0
        for knob in ISOLATE_KNOBS[3:]:
            for level in (0, 1, 2, 7):
                for grade, recent, gap in ((0, 0, 0), (45, 800, 90), (90, 590, 70)):
                    for name, samples in analog_windows():
                        kwargs = dict(mode=1, knob=knob, level=level, grade=grade, recent=recent, gap=gap)
                        parent_state, parent_scores = self.analyse(PARENT, samples, **kwargs)
                        state, scores = self.analyse(CANDIDATE, samples, **kwargs)
                        self.assertEqual(scores, parent_scores)
                        if not scores:
                            self.assertEqual(state, parent_state, name)
                            continue
                        want = self.expected(parent_state, scores[0], mode=1, knob=knob, level=level,
                                             grade=grade, recent=recent, gap=gap)
                        self.assertEqual(state, want, (knob, level, name, grade, recent, gap, scores))
                        cases += 1
                        muted += target(scores[0], level, knob) is None
        self.assertGreater(muted, 20)
        print('Analog lower-half vectors:', cases, 'muted', muted)

    def test_clipped_analog_window_counts_as_saturation(self):
        clipped = sine(amplitude=8000)
        self.assertGreaterEqual(sum(v == 4095 for v in clipped), 8)
        parent_state, parent_scores = self.analyse(PARENT, clipped, mode=1)
        self.assertEqual((parent_state[:2], parent_scores), ((20, 600), ()))
        self.assertEqual(self.analyse(CANDIDATE, clipped, mode=1)[0], parent_state)
        for knob in ISOLATE_KNOBS[3:]:
            for level in (0, 1, 2, 7):
                state, scores = self.analyse(CANDIDATE, clipped, mode=1, knob=knob, level=level, gap=90)
                self.assertEqual(scores, (isolate.SATURATION_SCORE,))
                parent_state = self.analyse(PARENT, clipped, mode=1, knob=knob, level=level, gap=90)[0]
                want = self.expected(parent_state, isolate.SATURATION_SCORE, mode=1, knob=knob,
                                     level=level, grade=0, recent=0, gap=90)
                self.assertEqual(state, want, (knob, level))


class MainsAnalysis(Analysers, unittest.TestCase):
    def test_mains_analysis_is_pn124(self):
        for knob in (0, 700, 2048, 4095):
            for name, samples in list(analog_corpus())[:40]:
                for grade in (0, 60):
                    kwargs = dict(mode=2, knob=knob, level=2, grade=grade, recent=700)
                    self.assertEqual(self.analyse(CANDIDATE, samples, **kwargs),
                                     self.analyse(PARENT, samples, **kwargs), (knob, name))


class Speaker(unittest.TestCase):
    execute = followup.Followup.execute

    def duties(self, data, keep_alive, ticks=6):
        c = streams.StreamCPU(data)
        writes = []
        c.uc.hook_add(UC_HOOK_MEM_WRITE, lambda uc, access, a, size, value, user: writes.append(value),
                      begin=CCR4, end=CCR4 + 1)
        for _ in range(ticks):
            self.execute(c, 0x08007508, keep_alive, stack=SP - 0x400)
        return writes

    def test_tone_swings_three_times_further_and_silence_is_unchanged(self):
        self.assertEqual(self.duties(PARENT, 30), [900, 700] * 3)
        self.assertEqual(self.duties(CANDIDATE, 30), [1100, 500] * 3)
        self.assertEqual(self.duties(PARENT, 0, 2), [800, 800])
        self.assertEqual(self.duties(CANDIDATE, 0, 2), [800, 800])


# ---------------------------------------------------------------- timed streams
T1_CYCLES, T5_CYCLES, PWM, TIM1 = strong.T1_CYCLES, strong.T5_CYCLES, strong.PWM, strong.TIM1
RATIO = (90, 230, 780, 780, 2028, 2028, 2028, 2028)


class FieldCPU(strong.GainStreamCPU):
    """GainStreamCPU with an arbitrary knob reading and a front-end limit."""
    def __init__(self, data, *, mode, knob, limit=2400):
        super().__init__(data, mode=mode, level=knob_code(knob))
        self.knob_raw = knob
        self.w16(0x20000068, knob)
        self.limit = limit

    def adc(self, uc, address, size, user):
        tick = self.read(streams.TIMER_COUNTER, 4)
        level = self.read(auto_range.STATE)
        pp = min(self.amplitude(tick) * RATIO[level] / 2028, self.limit)
        if self.read(MODE) == 0:
            bit = streams.CODE[(math.floor(tick * 25.015625 / 101) // 50) % 8]
            value = round(2048 + pp * (bit - .5))
        else:
            value = round(2048 + pp / 2 * math.cos(2 * math.pi * tick * 25.015625 / 1212))
        uc.reg_write(UC_ARM_REG_R0, max(0, min(4095, value)))
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))


class Streams(unittest.TestCase):
    execute = agc.AutoRangeFreshness.execute
    boundary = agc.AutoRangeFreshness.boundary
    timers = streams.TrackingStreams.timers

    def stream(self, data, *, mode=0, knob, amplitude, end_ms, knob_changes=None, mode_changes=None):
        c = FieldCPU(data, mode=mode, knob=knob)
        c.amplitude = lambda tick: amplitude(tick * T5_CYCLES / 64000)
        knob_changes, mode_changes = knob_changes or {}, mode_changes or {}
        self.boundary(c)
        edges, levels, publications = [], [], []
        sound = False

        def pwm(uc, access, address, size, value, user):
            nonlocal sound
            active = value != 800
            if active != sound:
                edges.append((c.read(TIMER_COUNTER, 4) * T5_CYCLES / 64000, active))
                sound = active

        hook = c.uc.hook_add(UC_HOOK_MEM_WRITE, pwm, begin=PWM, end=PWM + 1)
        try:
            for ms in range(1, end_ms + 1):
                self.timers(c, ms * T1_CYCLES // T5_CYCLES - c.read(TIMER_COUNTER, 4))
                if ms in knob_changes:
                    c.knob_raw = knob_changes[ms]
                if ms in mode_changes:
                    c.w8(REQUEST, mode_changes[ms] + 1)
                before = c.read(auto_range.STATE)
                self.execute(c, TIM1, stack=SP - 0x500, budget=10000)
                if c.read(auto_range.STATE) != before:
                    levels.append((ms, before, c.read(auto_range.STATE)))
                self.boundary(c)
                if not c.read(ACTIVE):
                    self.execute(c, ANALYZERS[c.read(MODE)], budget=150000)
                    publications.append((ms, c.read(GRADE), c.read(RECENT, 2)))
        finally:
            c.uc.hook_del(hook)
        return {'edges': edges, 'levels': levels, 'publications': publications, 'end_ms': end_ms,
                'mode': c.read(MODE), 'driven': c.read(auto_range.STATE)}

    @staticmethod
    def sounding(row, start, end):
        """Milliseconds of speaker tone between start and end."""
        total, on_since = 0.0, None
        for when, active in row['edges'] + [(row['end_ms'], False)]:
            if active and on_since is None:
                on_since = when
            elif not active and on_since is not None:
                total += max(0.0, min(when, end) - max(on_since, start))
                on_since = None
        return total


class Gain(Streams):
    def test_upper_half_always_allows_the_full_gain(self):
        weak = lambda ms: 900
        for knob in (2048, 2400, 3300):
            old = self.stream(PARENT, knob=knob, amplitude=weak, end_ms=700)
            new = self.stream(CANDIDATE, knob=knob, amplitude=weak, end_ms=700)
            self.assertEqual(new['driven'], 7, knob)
            self.assertEqual(old['driven'], {2048: 2, 2400: 4, 3300: 5}[knob], knob)
            self.assertGreater(self.sounding(new, 400, 700), 50, knob)

    def test_turning_down_into_the_lower_half_keeps_the_lowered_gain(self):
        strong_signal = lambda ms: 30000
        changes = {3000: 1500}
        old = self.stream(PARENT, knob=4095, amplitude=strong_signal, end_ms=3600, knob_changes=changes)
        new = self.stream(CANDIDATE, knob=4095, amplitude=strong_signal, end_ms=3600, knob_changes=changes)
        settle = [(500, 7, 2), (1500, 2, 1), (2500, 1, 0)]
        self.assertEqual(old['levels'][:3], settle)
        self.assertEqual(new['levels'], settle)
        self.assertEqual(old['levels'][3][1:], (0, 2), 'PN1.24 re-raises the gain on a knob change')

    def test_turning_down_on_a_strong_pair_keeps_it_sounding(self):
        for mode in (0, 1):
            row = self.stream(CANDIDATE, mode=mode, knob=4095, amplitude=lambda ms: 30000,
                              end_ms=4600, knob_changes={3000: 1100})
            self.assertEqual(row['levels'], [(500, 7, 2), (1500, 2, 1), (2500, 1, 0)])
            quiet = [(a, b) for (a, on_a), (b, on_b) in zip(row['edges'], row['edges'][1:])
                     if not on_a and on_b and a > 2800]
            self.assertTrue(all(b - a < 120 for a, b in quiet), quiet)
            self.assertGreater(self.sounding(row, 3200, 4600) / 1400, 0.15)

    def test_knob_off_still_silences(self):
        for mode in (0, 1):
            row = self.stream(CANDIDATE, mode=mode, knob=4095, amplitude=lambda ms: 30000,
                              end_ms=3600, knob_changes={3000: 0})
            self.assertGreater(self.sounding(row, 2000, 3000), 100)
            self.assertEqual(self.sounding(row, 3300, 3600), 0)

    def test_turning_the_knob_up_still_follows_it(self):
        changes = {1000: 1160, 2000: 4095}
        weak = lambda ms: 900
        for data in (PARENT, CANDIDATE):
            row = self.stream(data, knob=4095, amplitude=weak, end_ms=2300, knob_changes=changes)
            self.assertEqual(row['levels'], [(1000, 7, 2), (2000, 2, 7)])

    def test_full_knob_agc_is_pn124(self):
        cases = (
            (lambda ms: 2400 if ms < 1000 else 800, 1800),
            (lambda ms: 20000, 2900),
            (lambda ms: 1950, 1300),
        )
        for mode in (0, 1):
            for amplitude, end in cases:
                old = self.stream(PARENT, mode=mode, knob=4095, amplitude=amplitude, end_ms=end)
                new = self.stream(CANDIDATE, mode=mode, knob=4095, amplitude=amplitude, end_ms=end)
                self.assertEqual(new['levels'], old['levels'])
                self.assertEqual(new['publications'], old['publications'])

    def test_ncv_gets_the_knob_gain_back_after_a_tracing_mode(self):
        strong_signal = lambda ms: 30000
        for knob, wanted in ((4095, 7), (1300, 2)):
            old = self.stream(PARENT, knob=knob, amplitude=strong_signal, end_ms=3700,
                              mode_changes={3000: 2})
            new = self.stream(CANDIDATE, knob=knob, amplitude=strong_signal, end_ms=3700,
                              mode_changes={3000: 2})
            self.assertEqual((old['mode'], new['mode']), (2, 2))
            self.assertEqual(old['driven'], 0, 'PN1.24 keeps the lowered tracing gain in mains')
            self.assertEqual(new['driven'], wanted, knob)


class Field(Streams):
    """A toned pair and a neighbour at -12 dB, alternately under the probe."""
    TARGET, NEIGHBOUR, SEGMENT = 30000, 7500, 1500

    def amplitude(self, ms):
        return self.TARGET if (ms // self.SEGMENT) % 2 == 0 else self.NEIGHBOUR

    def segments(self, row):
        out = []
        for n in range(4):
            start, end = n * self.SEGMENT + 700, (n + 1) * self.SEGMENT
            out.append(self.sounding(row, start, end) / (end - start))
        return out

    def test_field_report_reproduces_on_pn124_and_the_upper_half(self):
        for mode in (0, 1):
            for data, knob in ((PARENT, 800), (PARENT, 4095), (CANDIDATE, 4095), (CANDIDATE, 2500)):
                row = self.stream(data, mode=mode, knob=knob, amplitude=self.amplitude, end_ms=6000)
                duty = self.segments(row)
                print('mode', mode, 'PN1.25' if data is CANDIDATE else 'PN1.24', 'knob', knob,
                      'tone fraction per segment', [round(d, 2) for d in duty])
                self.assertTrue(all(d > 0.4 for d in duty), 'target and neighbour both sound fast')

    def test_lower_half_keeps_the_target_and_mutes_the_neighbour(self):
        for mode in (0, 1):
            for knob in (650, 800, 900):
                row = self.stream(CANDIDATE, mode=mode, knob=knob, amplitude=self.amplitude, end_ms=6000)
                duty = self.segments(row)
                print('mode', mode, 'PN1.25 knob', knob, 'tone fraction per segment',
                      [round(d, 2) for d in duty], 'gain steps', row['levels'])
                self.assertGreater(duty[0], 0.1)
                self.assertGreater(duty[2], 0.1)
                if knob < 900:
                    self.assertEqual((duty[1], duty[3]), (0.0, 0.0), 'neighbour under the floor')
                else:
                    # Just above the neighbour's floor: it sounds, but clearly slower.
                    self.assertLess(max(duty[1], duty[3]), 0.8 * min(duty[0], duty[2]))


if __name__ == '__main__':
    unittest.main()
