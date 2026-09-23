"""PN1.29: ten absolute strength levels against the knob reference, fast attack, no memory.

The analysers, publisher, AGC, sampler and speaker of the built image execute in Unicorn;
ADC values, the analogue link, the coupling between pairs and interrupt arrival are modeled.
The display is checked against an independent model of its stated rules, the gain against
PN1.24's AGC tests, and the owner's cabinet task with cabinet_scorecard. None of this measures
pickup, real coupling between pairs or loudness.
"""
import contextlib
import hashlib
import io
import unittest

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_MCLASS
from unicorn import UC_HOOK_MEM_WRITE

import auto_range
import cabinet_scorecard as scorecard
import isolate
import knob_reference
import level_display as lvl
import pair_rank
import rx_precision
import sample_age_guard
import test_rx_digital_strong_gain as strong
import test_rx_gain_response as response
import test_rx_relative_isolate as base
import test_rx_tracking_streams as streams
from lpm10rx import symbols
from lpm10rx.container import unwrap, wrap
from lpm10rx.image import PatchError
from sampling_fixes import GATE_STATE
from test_rx_isolate import CCR4, Streams, analog_windows, clipped_digital, digital_windows
from verify_control import SP
from verify_digital import ACTIVE, BUFFER

PARENT = CANDIDATE = IMG = None
CANDIDATE_SHA256 = None
MULT = base.MULT
NOW = base.NOW
KNOBS = (2, 300, 580, 1024, 1536, 2047, 2048, 3072, 3839, 3840, 4095)
# (RECENT, level on display, averaged strength): fresh audio, continuing audio at several averages,
# and an out-of-range stored level (fresh).
STATES = ((0, 0, 0), (800, 5, 0), (800, 5, 12_000), (800, 2, 400_000), (800, 9, 60_000), (800, 12, 7_000))


def setUpModule():
    global PARENT, CANDIDATE, IMG, CANDIDATE_SHA256
    with contextlib.redirect_stdout(io.StringIO()):
        PARENT = bytes(rx_precision.build_candidate().data)
        IMG = lvl.build_candidate()
    CANDIDATE = bytes(IMG.data)
    CANDIDATE_SHA256 = hashlib.sha256(CANDIDATE).hexdigest()


def model(raw, driven, knob, average, current, recent):
    """(published quiet interval, stored average, stored level) for one analysed window."""
    s = raw & 0xFFFFFFFF
    if driven <= 7:
        s = ((s * MULT[driven]) & 0xFFFFFFFF) // 10
    s = min(s, isolate.CLAMP)
    s = s * knob_reference.reference(knob) >> 8
    if recent <= 500 or current >= lvl.LEVELS:
        level = lvl.count(s)
    else:
        if s < average:
            s = average - ((average - s) >> 3)
        level = lvl.level(s, current, False)
    return lvl.INTERVALS[level], s, level


class Analysers(base.Analysers):
    def entry(self, data):
        return isolate.OLD_CURVE if data is PARENT else IMG.level_display['curve']

    def display(self, data, samples, *, recent, current, average, **kw):
        state, scores, (stored, rest) = self.analyse(
            data, samples, recent=recent, peak=average, elapsed=(NOW - current) & 0xFFFFFFFF, **kw)
        return state, scores, stored, (NOW - rest) & 0xFFFFFFFF

    def check(self, samples, *, mode, knob, driven, recent, current, average, gap=0):
        kw = dict(mode=mode, knob=knob, level=driven, grade=45, gap=gap)
        parent_state, parent_scores = self.analyse(PARENT, samples, recent=recent, **kw)[:2]
        state, scores, stored, level = self.display(CANDIDATE, samples, recent=recent, current=current,
                                               average=average, **kw)
        self.assertEqual(scores, parent_scores, 'analysers are PN1.24\'s')
        if not scores:
            self.assertEqual(state, parent_state)
            return None
        interval, avg, lev = model(scores[0], driven, knob, average, current, recent)
        recent_after, gap_after = (800, gap) if mode == 0 else (600, min(gap, interval))
        self.assertEqual(state, (interval, recent_after) + parent_state[2:5] + (gap_after,))
        self.assertEqual((stored, level), (avg, lev))
        return lev


class Build(unittest.TestCase):
    def test_parent_is_pinned_and_only_declared_sites_change(self):
        self.assertEqual(IMG.level_display['start'], symbols.APP_BASE + len(PARENT))
        allowed = set()
        for site, size in ((isolate.GAP_ENTRY, 4), (isolate.DIGITAL_UNCERTAIN, 4), (isolate.ANALOG_SITE, 24),
                           (isolate.GAIN_SITE, 4), (pair_rank.AGC_SITE, 4), (isolate.TONE_HIGH, 4),
                           (isolate.TONE_LOW, 4), (0x0800CDE4, 8)):
            allowed |= set(range(site, site + size))
        changed = {symbols.APP_BASE + i for i, (a, b) in enumerate(zip(PARENT, CANDIDATE)) if a != b}
        self.assertLessEqual(changed, allowed)
        self.assertEqual(len(CANDIDATE) - len(PARENT), IMG.level_display['helper_bytes'])
        self.assertLessEqual(symbols.APP_BASE + len(CANDIDATE), symbols.EXTEND_LIMIT)
        self.assertEqual(CANDIDATE[0x0800CDE4 - symbols.APP_BASE:][:8], b'PN1.29\0\0')

    def test_changed_parent_is_rejected_before_any_byte_changes(self):
        with contextlib.redirect_stdout(io.StringIO()):
            img = rx_precision.build_candidate()
        img.data[img.f(pair_rank.AGC_SITE)] ^= 1
        before = bytes(img.data), list(img.log)
        with self.assertRaises(PatchError):
            lvl.apply(img)
        self.assertEqual((bytes(img.data), img.log), before)

    def test_written_candidate_is_this_exact_build(self):
        raw, update = lvl.DIRECTORY / lvl.OUTPUT, lvl.DIRECTORY / lvl.UPDATE
        if not raw.exists():
            self.skipTest('experimental PN1.29 files not written yet (python level_display.py --write)')
        self.assertEqual(raw.read_bytes(), CANDIDATE)
        self.assertEqual(update.read_bytes(), wrap(CANDIDATE))
        self.assertEqual(unwrap(update.read_bytes())[1], CANDIDATE)
        sums = (lvl.DIRECTORY / lvl.SUMS).read_text(encoding='ascii').split()
        self.assertEqual(sums, [CANDIDATE_SHA256, lvl.OUTPUT, hashlib.sha256(wrap(CANDIDATE)).hexdigest(), lvl.UPDATE])

    def test_no_branch_lands_inside_replaced_instructions(self):
        forbidden = {isolate.DIGITAL_UNCERTAIN + 2, isolate.GAP_ENTRY + 2, isolate.GAIN_SITE + 2,
                     pair_rank.AGC_SITE + 2, isolate.TONE_HIGH + 2, isolate.TONE_LOW + 2}
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
                    if int(insn.op_str.split('#')[-1], 16) in forbidden and insn.address not in replaced:
                        hits.append((hex(insn.address), insn.mnemonic))
        self.assertGreater(seen, 1000)
        self.assertEqual(hits, [])

    def test_display_ram_is_unused_by_pn124(self):
        for word in range(lvl.AVERAGE, lvl.AVERAGE + 8, 4):
            self.assertNotIn(word.to_bytes(4, 'little'), PARENT)

    def test_level_law(self):
        self.assertEqual(len(lvl.THRESHOLDS), lvl.LEVELS - 1)
        self.assertEqual(lvl.THRESHOLDS[-1], isolate.SATURATION_SCORE)
        for low, high in zip(lvl.THRESHOLDS, lvl.THRESHOLDS[1:]):
            self.assertAlmostEqual(high / low, 10 ** (lvl.STEP_DB / 20), delta=0.001)
        periods = [30 + i for i in lvl.INTERVALS]
        for slower, faster in zip(periods, periods[1:]):
            self.assertGreaterEqual(slower / faster, 1.14, 'each level at least 14 % longer in period')
        start = IMG.level_display['curve'] - symbols.APP_BASE
        blob = b''.join(t.to_bytes(4, 'little') for t in lvl.THRESHOLDS)
        self.assertIn(blob, CANDIDATE[start:start + 0x200])
        self.assertIn(bytes(lvl.INTERVALS), CANDIDATE[start:start + 0x200])


class Digital(Analysers, unittest.TestCase):
    def test_every_knob_position_follows_the_model(self):
        cases, levels = 0, set()
        for knob in KNOBS:
            for driven in (0, 1, 2, 7):
                for recent, current, average in STATES:
                    for name, samples in digital_windows():
                        lev = self.check(samples, mode=0, knob=knob, driven=driven, recent=recent,
                                         current=current, average=average)
                        if lev is not None:
                            cases += 1
                            levels.add(lev)
        self.assertEqual(levels, set(range(lvl.LEVELS)), 'every level is reached')
        print('Digital model vectors:', cases)

    def test_clipped_window_is_the_saturation_score_through_the_display(self):
        for name, samples in clipped_digital():
            for knob in (300, 2048, 3840, 4095):
                for driven in (0, 2, 7):
                    state, scores, stored, level = self.display(CANDIDATE, samples, mode=0, knob=knob, level=driven,
                                                            grade=0, recent=0, current=0, average=0)
                    self.assertEqual(scores, (isolate.SATURATION_SCORE,))
                    interval, avg, lev = model(isolate.SATURATION_SCORE, driven, knob, 0, 0, 0)
                    self.assertEqual((state[0], state[1], stored, level), (interval, 800, avg, lev))
            state = self.display(CANDIDATE, samples, mode=0, knob=4095, level=7, grade=0, recent=0,
                             current=0, average=0)[0]
            self.assertEqual(state[0], lvl.INTERVALS[-1], 'clipped at full gain and full knob: fastest')


class Analog(Analysers, unittest.TestCase):
    def test_every_knob_position_follows_the_model(self):
        cases = 0
        for knob in KNOBS[2:]:
            for driven in (0, 2, 7):
                for recent, current, average in STATES[:4]:
                    for gap in (0, 90):
                        for name, samples in analog_windows():
                            if self.check(samples, mode=1, knob=knob, driven=driven, recent=recent,
                                          current=current, average=average, gap=gap) is not None:
                                cases += 1
        print('Analog model vectors:', cases)


class MainsAndSpeaker(Analysers, unittest.TestCase):
    def test_mains_analysis_is_pn124(self):
        from test_rx_analog_fast import corpus
        for knob in (0, 700, 2048, 4095):
            for name, samples in list(corpus())[:40]:
                kw = dict(mode=2, knob=knob, level=2, grade=0, recent=700)
                self.assertEqual(self.analyse(CANDIDATE, samples, **kw)[:2], self.analyse(PARENT, samples, **kw)[:2])

    def test_tone_is_the_louder_swing(self):
        for keep_alive, want in ((30, [1100, 500] * 3), (0, [800] * 6)):
            c = streams.StreamCPU(CANDIDATE)
            writes = []
            c.uc.hook_add(UC_HOOK_MEM_WRITE, lambda uc, access, a, size, value, user: writes.append(value),
                          begin=CCR4, end=CCR4 + 1)
            for _ in range(6):
                self.execute(c, 0x08007508, keep_alive, stack=SP - 0x400)
            self.assertEqual(writes, want)


class Gain(Streams):
    def test_tracing_uses_the_full_gain_at_every_knob(self):
        for knob in (300, 1000, 2000, 4095):
            for mode in (0, 1):
                row = self.stream(CANDIDATE, mode=mode, knob=knob, amplitude=lambda ms: 60, end_ms=700)
                self.assertEqual(row['driven'], 7, (knob, mode))

    def test_ncv_gain_follows_the_knob(self):
        for knob, wanted in ((4095, 7), (1100, 7), (800, 1), (300, 0)):
            row = self.stream(CANDIDATE, knob=knob, amplitude=lambda ms: 30000, end_ms=3700, mode_changes={3000: 2})
            self.assertEqual((row['mode'], row['driven']), (2, wanted), knob)

    def test_knob_off_still_silences(self):
        for mode in (0, 1):
            row = self.stream(CANDIDATE, mode=mode, knob=4095, amplitude=lambda ms: 30000,
                              end_ms=3600, knob_changes={3000: 0})
            self.assertGreater(self.sounding(row, 2000, 3000), 100)
            self.assertEqual(self.sounding(row, 3300, 3600), 0)


class AttackStreams(unittest.TestCase):
    """PN1.24's AGC stream fixture, knob at 4 060: the tracing ceiling is the full gain."""
    execute = response.GainResponseStreams.execute
    boundary = response.GainResponseStreams.boundary
    timers = response.GainResponseStreams.timers
    run_stream = response.GainResponseStreams.run_stream

    @classmethod
    def setUpClass(cls):
        cls.previous, cls.data = PARENT, CANDIDATE

    def test_saturation_steps_down_every_half_second_without_dropout(self):
        for mode in (0, 1):
            with self.subTest(mode=mode):
                old = self.run_stream(mode=mode, previous=True, changes={}, end_ms=2900, source_pp=20000)
                self.assertEqual(old['transitions'], [(500, 7, 2), (1500, 2, 1), (2500, 1, 0)])
                row = self.run_stream(mode=mode, changes={}, end_ms=2900, source_pp=20000)
                self.assertEqual(row['transitions'], [(500, 7, 2), (1000, 2, 1), (1500, 1, 0)])
                self.assertFalse(row['unowned_refreshes'])
                self.assertLess(row['max_quiet_ms'], 150, row['quiet'])

    def test_step_up_keeps_the_one_second_hold_and_nothing_hunts(self):
        for mode in (0, 1):
            with self.subTest(mode=mode):
                row = self.run_stream(mode=mode, changes={}, end_ms=1800,
                                      source_pp=lambda ms: 2400 if ms < 1000 else 800)
                self.assertEqual(row['transitions'], [(500, 7, 2), (1500, 2, 7)])
                for amplitude, expected in ((1850, []), (1950, [(500, 7, 2)]), (1170, []), (800, [])):
                    row = self.run_stream(mode=mode, changes={}, end_ms=3300, source_pp=amplitude)
                    self.assertEqual(row['transitions'], expected, amplitude)


class AttackInstructions(unittest.TestCase):
    execute = response.GainResponseInstructions.execute
    boundary = response.GainResponseInstructions.boundary
    timers = response.GainResponseInstructions.timers
    select = response.GainResponseInstructions.select

    @classmethod
    def setUpClass(cls):
        cls.previous, cls.data = PARENT, CANDIDATE

    def test_partial_new_gain_buffer_cannot_trigger_a_second_change(self):
        import struct
        for mode, irqs in ((0, 6000), (1, 200)):
            with self.subTest(mode=mode):
                c = strong.GainStreamCPU(self.data, mode=mode)
                self.boundary(c)
                c.uc.mem_write(BUFFER, struct.pack('<64H', *([848, 3248] * 32)))
                c.w32(sample_age_guard.COMPLETED_VALID, 1)
                self.assertEqual(self.select(c), 2)
                self.assertEqual(c.read(auto_range.STATE + 2), 0, 'no hold after a step down')
                self.boundary(c)
                self.timers(c, irqs)
                self.assertEqual(c.read(ACTIVE), 1)
                self.assertEqual(self.select(c), 2)
                self.assertEqual(c.read(sample_age_guard.COMPLETED_VALID, 4), 0)


class Cabinet(unittest.TestCase):
    """The owner's task (cabinet_scorecard): pick the toned pair out of a bundle by ear."""
    ISOLATE = 768                                      # 19 % of the knob: Isolate for contact strengths 3 000-30 000

    def visits(self, data, mode, target, knob=ISOLATE):
        return scorecard.visit_fractions(data, mode=mode, knob=knob, target=target)

    def test_isolate_position_identifies_the_toned_pair_at_every_contact_strength(self):
        for mode in (0, 1):
            for target in scorecard.TARGETS:
                with self.subTest(mode=mode, target=target):
                    visits = self.visits(CANDIDATE, mode, target)
                    ok, failures, spread = scorecard.score(visits)
                    print('mode', mode, 'PN1.29 knob 19 % T', target, [(p, round(f, 2)) for p, f in visits])
                    self.assertTrue(ok, failures)
                    # The toned pair is visited after N6 and after N3, both once the gain has settled: the
                    # same rhythm both times means nothing depends on what was touched before. (A neighbour's
                    # first visit can fall in the first ~2.5 s at the bundle, while the gain still settles.)
                    self.assertLessEqual(spread['T'], 0.02, 'the toned pair sounds the same on every visit')

    def test_pn127_negative_control(self):
        with contextlib.redirect_stdout(io.StringIO()):
            pn127 = bytes(knob_reference.build_candidate().data)
        results = [scorecard.score(self.visits(pn127, mode, target))[0]
                   for mode in (0, 1) for target in scorecard.TARGETS]
        self.assertIn(False, results, 'PN1.27 does not identify every case at this knob position')
        full = scorecard.score(self.visits(CANDIDATE, 0, 10000, knob=4095))
        self.assertFalse(full[0], 'full knob is Locate: strong pairs all at the top level, by design')


if __name__ == '__main__':
    unittest.main()
