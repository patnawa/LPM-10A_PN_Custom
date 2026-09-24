"""PN1.30: edge-free Digital strength, a gain decision at every window, no walk-down at a touch.

The detector, estimator, display, publisher, AGC, sampler, TIM1 tick and speaker of the built image
execute in Unicorn; ADC values, the analogue link (a gain ratio per driven level and a front-end
limit) and interrupt arrival are modeled. The transmitter's 5.05 ms chip against the receiver's
5 ms slot is in the model, so the chip edges drift through the sampler's readings as on the
device. None of this measures pickup, real coupling between pairs or loudness.
"""
import contextlib
import hashlib
import io
import random
import struct
import unittest

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_MCLASS
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1

import auto_range
import cabinet_scorecard as scorecard
import clean_strength as cs
import isolate
import level_display as lvl
import test_rx_gain_response as response
import test_rx_isolate as base
import test_rx_tracking_streams as streams
from lpm10rx import symbols
from lpm10rx.container import unwrap, wrap
from lpm10rx.image import PatchError
from test_rx_followup import ANALYZERS, GRADE
from test_rx_isolate import (CCR4, FieldCPU, Streams, T1_CYCLES, T5_CYCLES, TIM1, analog_windows,
                             clipped_digital, digital_windows)
from test_scan_acquisition_timing import TIMER_COUNTER
from verify_control import SP, MODE
from verify_digital import ACTIVE, BUFFER, RECENT, pattern

PARENT = CANDIDATE = IMG = IMG29 = None
CODE = streams.CODE                     # 1 0 1 1 0 1 1 0
LOW = 800


def setUpModule():
    global PARENT, CANDIDATE, IMG, IMG29
    with contextlib.redirect_stdout(io.StringIO()):
        IMG29 = lvl.build_candidate()
        PARENT = bytes(IMG29.data)
        IMG = cs.build_candidate()
    CANDIDATE = bytes(IMG.data)


def mixed_pattern(rotation, contrast, f, alignment, second_f=None, low=LOW):
    """48 samples of the code in which every sample whose readings hold a chip edge is a mix.

    alignment 'start': the edge is at the start of the sample's chip and a fraction f of its
    readings still belong to the previous chip; 'end': the edge is at the end and 1 - f of the
    readings already belong to the next chip. second_f, when given, applies to the second half of
    the window (the edge drifts by about one reading per 80 ms)."""
    values = []
    for i in range(48):
        bit, prev, nxt = (CODE[(i + rotation + d) % 8] for d in (0, -1, 1))
        ff = f if second_f is None or i < 24 else second_f
        if alignment == 'start':
            level = bit if bit == prev else prev * ff + bit * (1 - ff)
        else:
            level = bit if bit == nxt else bit * ff + nxt * (1 - ff)
        values.append(round(low + contrast * level))
    return values


def level_of(interval):
    """Displayed level for a published quiet interval (1 = 'uncertain' plays as the fastest)."""
    if interval == 1:
        return lvl.LEVELS - 1
    return lvl.INTERVALS.index(interval) if interval in lvl.INTERVALS else None


class Build(unittest.TestCase):
    def test_parent_is_pinned_and_only_declared_sites_change(self):
        self.assertEqual(hashlib.sha256(PARENT).hexdigest(), cs.PARENT_SHA256)
        self.assertEqual(IMG.clean_strength['start'], symbols.APP_BASE + len(PARENT))
        allowed = set()
        for site, size in ((cs.ESTIMATE_CALL, 4), (isolate.GAP_ENTRY, 4), (cs.CURVE_CALLS[0], 4),
                           (cs.CURVE_CALLS[1], 4), (cs.TIM1_SITE, len(cs.TIM1_SITE_BYTES)), (0x0800CDE4, 8)):
            allowed |= set(range(site, site + size))
        changed = {symbols.APP_BASE + i for i, (a, b) in enumerate(zip(PARENT, CANDIDATE)) if a != b}
        self.assertTrue(changed)
        self.assertLessEqual(changed, allowed)
        self.assertEqual(len(CANDIDATE) - len(PARENT), IMG.clean_strength['helper_bytes'])
        self.assertLessEqual(symbols.APP_BASE + len(CANDIDATE), symbols.EXTEND_LIMIT)
        self.assertEqual(CANDIDATE[0x0800CDE4 - symbols.APP_BASE:][:8], b'PN1.30\0\0')
        self.assertEqual(IMG.clean_strength['persistent_ram_bytes'], 8)
        tail = CANDIDATE[cs.TIM1_SITE - symbols.APP_BASE + 4:][:len(cs.TIM1_SITE_BYTES) - 4]
        self.assertEqual(tail, bytes.fromhex('00bf') * (len(tail) // 2))

    def test_changed_parent_is_rejected_before_any_byte_changes(self):
        with contextlib.redirect_stdout(io.StringIO()):
            img = lvl.build_candidate()
        img.data[img.f(cs.TIM1_SITE)] ^= 1
        before = bytes(img.data), list(img.log)
        with self.assertRaises(PatchError):
            cs.apply(img)
        self.assertEqual((bytes(img.data), img.log), before)
        with self.assertRaises(PatchError):
            cs.apply(IMG)

    def test_update_container_round_trips(self):
        update = wrap(CANDIDATE)
        self.assertEqual(len(update) % 0x1000, 0)
        self.assertEqual(unwrap(update)[1], CANDIDATE)

    def test_written_candidate_is_this_exact_build(self):
        raw, update = cs.DIRECTORY / cs.OUTPUT, cs.DIRECTORY / cs.UPDATE
        if not raw.exists():
            self.skipTest('experimental PN1.30 files not written yet (python clean_strength.py --write)')
        self.assertEqual(raw.read_bytes(), CANDIDATE)
        self.assertEqual(update.read_bytes(), wrap(CANDIDATE))
        sums = (cs.DIRECTORY / cs.SUMS).read_text(encoding='ascii').split()
        self.assertEqual(sums, [hashlib.sha256(CANDIDATE).hexdigest(), cs.OUTPUT,
                                hashlib.sha256(wrap(CANDIDATE)).hexdigest(), cs.UPDATE])

    def test_display_ram_is_unused_by_the_parent(self):
        for word in (cs.LAST_DECIDED, cs.LAST_DISPLAYED):
            self.assertNotIn(word.to_bytes(4, 'little'), PARENT)
            self.assertIn(word.to_bytes(4, 'little'), CANDIDATE)

    def test_no_branch_lands_inside_replaced_instructions(self):
        forbidden = {cs.ESTIMATE_CALL + 2, isolate.GAP_ENTRY + 2, cs.CURVE_CALLS[0] + 2, cs.CURVE_CALLS[1] + 2}
        forbidden |= set(range(cs.TIM1_SITE + 2, cs.TIM1_SITE + len(cs.TIM1_SITE_BYTES), 2))
        replaced = set(range(cs.TIM1_SITE, cs.TIM1_SITE + len(cs.TIM1_SITE_BYTES)))
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

    def test_model_reproduces_the_old_estimate_on_clean_windows(self):
        for rotation in range(8):
            for contrast in (12, 60, 400, 2400):
                samples = pattern(rotation, LOW, LOW + contrast)[32:]
                pat = 0xB6B6B6B6
                for _ in range(rotation):
                    pat = ((pat << 1) | (pat >> 31)) & 0xFFFFFFFF
                self.assertEqual(cs.estimate(samples, pat), cs.contrast_score(contrast), (rotation, contrast))


class Estimator(base.Analysers, unittest.TestCase):
    """The Digital analyser on one window: PN1.29 against PN1.30, and PN1.30 against its model."""

    def curve_entry(self, data):
        return IMG.clean_strength['curve'] if data is CANDIDATE else IMG29.level_display['curve']

    def scored(self, data, samples, *, knob=4095, level=7):
        c = streams.StreamCPU(data)
        self.fresh(c, mode=0, knob=knob, level=level, grade=0, recent=0)
        c.uc.mem_write(BUFFER, struct.pack('<48H', *samples) + bytes([0xA5] * 32))
        estimator = cs.OLD_ESTIMATOR if data is PARENT else IMG.clean_strength['estimator']
        captured, scores = {}, []

        def at_entry(uc, a, s, u):
            p = uc.reg_read(UC_ARM_REG_R0)
            captured['samples'] = list(struct.unpack('<16H', uc.mem_read(p, 32)))
            captured['pattern'] = uc.reg_read(UC_ARM_REG_R1)

        def at_return(uc, a, s, u):
            captured['result'] = uc.reg_read(UC_ARM_REG_R0)

        entry = self.curve_entry(data)
        hooks = [c.uc.hook_add(UC_HOOK_CODE, at_entry, begin=estimator, end=estimator),
                 c.uc.hook_add(UC_HOOK_CODE, at_return, begin=cs.ESTIMATE_CALL + 4, end=cs.ESTIMATE_CALL + 4),
                 c.uc.hook_add(UC_HOOK_CODE, lambda uc, a, s, u: scores.append(uc.reg_read(UC_ARM_REG_R0)),
                               begin=entry, end=entry)]
        try:
            self.execute(c, ANALYZERS[0], budget=150000)
        finally:
            for h in hooks:
                c.uc.hook_del(h)
        state = (c.read(GRADE), c.read(RECENT, 2), c.read(lvl.AVERAGE, 4), c.read(lvl.AVERAGE + 4))
        return captured, tuple(scores), state

    def corpus(self):
        rng = random.Random(0x130)
        windows = list(digital_windows()) + list(clipped_digital())
        windows += [(f'noise_{n}', [rng.randrange(4096) for _ in range(48)]) for n in range(12)]
        windows += [(f'dc_{v}', [v] * 48) for v in (0, 2048, 4095)]
        return windows

    def test_clean_windows_score_and_display_as_pn129(self):
        """Scores identical; the display identical unless the window is saturated above the lowest gain,
        where PN1.30 counts it 1.2 dB lower (a lower bound with a gain-step margin)."""
        cases = bounded = 0
        for name, samples in self.corpus():
            saturated = max(samples[:cs.SAT_SAMPLES]) - min(samples[:cs.SAT_SAMPLES]) >= cs.SAT_PP
            for knob in (768, 4095):
                for level in (0, 2, 7):
                    old = self.scored(PARENT, samples, knob=knob, level=level)
                    new = self.scored(CANDIDATE, samples, knob=knob, level=level)
                    self.assertEqual(new[1], old[1], (name, knob, level))
                    if not new[1]:
                        self.assertEqual(new[2], old[2], (name, knob, level))
                        continue
                    cases += 1
                    if saturated and level > 0:
                        stored = old[2][2] - (old[2][2] >> cs.SAT_MARGIN_SHIFT)
                        self.assertEqual(new[2][2:], (stored, lvl.count(stored)), (name, knob, level, old[2], new[2]))
                        self.assertEqual(new[2][:2], (lvl.INTERVALS[lvl.count(stored)], 800), (name, knob, level))
                        bounded += 1
                    else:
                        self.assertEqual(new[2], old[2], (name, knob, level))
        self.assertGreater(cases - bounded, 100)
        self.assertGreater(bounded, 10)
        print('PN1.30 clean Digital windows: scores identical to PN1.29 on', cases, 'windows,', bounded, 'saturated ones bounded 1.2 dB lower')

    def test_firmware_estimate_equals_the_model_on_every_captured_window(self):
        cases = 0
        windows = self.corpus()
        for rotation in range(8):
            for f in (1 / 3, 2 / 3):
                for alignment in ('start', 'end'):
                    windows.append((f'mix_{rotation}_{f:.2f}_{alignment}', mixed_pattern(rotation, 600, f, alignment)))
        for name, samples in windows:
            captured = self.scored(CANDIDATE, samples)[0]
            if 'result' not in captured:
                continue
            self.assertEqual(captured['result'], cs.estimate(captured['samples'], captured['pattern']), name)
            cases += 1
        self.assertGreater(cases, 60)
        print('PN1.30 estimator vectors equal to the model:', cases)

    def test_mixed_edge_windows_read_the_true_contrast(self):
        """Every sample that holds an edge is a mix: PN1.29 reads 1/2 .. 5/6 of the contrast, PN1.30 the contrast."""
        worst_old, accepted = 1.0, 0
        for rotation in range(8):
            for contrast in (60, 300, 1200):
                truth = cs.contrast_score(contrast)
                for f in (1 / 3, 2 / 3):
                    for alignment in ('start', 'end'):
                        samples = mixed_pattern(rotation, contrast, f, alignment)
                        old = self.scored(PARENT, samples)[1]
                        new = self.scored(CANDIDATE, samples)[1]
                        self.assertTrue(new, (rotation, contrast, f, alignment))
                        accepted += 1
                        self.assertAlmostEqual(new[0] / truth, 1.0, delta=0.03, msg=(rotation, contrast, f, alignment, new))
                        if old:
                            worst_old = min(worst_old, old[0] / truth)
        self.assertGreater(accepted, 60)
        self.assertLess(worst_old, 0.7, 'PN1.29 reads mixed windows low (negative control)')
        print('mixed-edge windows accepted:', accepted, 'PN1.29 worst ratio', round(worst_old, 2))

    def test_edge_drifting_inside_the_window_stays_within_a_level_step(self):
        for rotation in range(8):
            for f1, f2 in ((1 / 3, 2 / 3), (2 / 3, 1 / 3), (0, 1 / 3), (2 / 3, 1)):
                for alignment in ('start', 'end'):
                    samples = mixed_pattern(rotation, 600, f1, alignment, second_f=f2)
                    new = self.scored(CANDIDATE, samples)[1]
                    if not new:
                        continue
                    self.assertGreater(new[0] / cs.contrast_score(600), 0.8, (rotation, f1, f2, alignment, new))


class Probe(Streams):
    """A stream with every window's raw score and the display's stored level."""

    def probe(self, data, *, mode, knob, amplitude, end_ms):
        curve = IMG.clean_strength['curve'] if data is CANDIDATE else IMG29.level_display['curve']
        c = FieldCPU(data, mode=mode, knob=knob)
        c.amplitude = lambda tick: amplitude(tick * T5_CYCLES / 64000)
        self.boundary(c)
        rows, levels, last = [], [], [None]
        hook = c.uc.hook_add(UC_HOOK_CODE, lambda uc, a, s, u: last.__setitem__(0, uc.reg_read(UC_ARM_REG_R0)),
                             begin=curve, end=curve)
        try:
            for ms in range(1, end_ms + 1):
                self.timers(c, ms * T1_CYCLES // T5_CYCLES - c.read(TIMER_COUNTER, 4))
                before = c.read(auto_range.STATE)
                self.execute(c, TIM1, stack=SP - 0x500, budget=10000)
                if c.read(auto_range.STATE) != before:
                    levels.append((ms, before, c.read(auto_range.STATE)))
                self.boundary(c)
                if not c.read(ACTIVE):
                    last[0] = None
                    self.execute(c, ANALYZERS[c.read(MODE)], budget=150000)
                    rows.append((ms, last[0], c.read(auto_range.STATE), c.read(lvl.AVERAGE + 4), c.read(GRADE)))
        finally:
            c.uc.hook_del(hook)
        return rows, levels


class Flicker(Probe):
    """A steady Digital signal 0.6-1.0 dB above a level threshold (owner: a probe held still)."""

    def steady(self, data, amp):
        rows, _ = self.probe(data, mode=0, knob=4095, amplitude=lambda ms: amp, end_ms=6000)
        settled = [r for r in rows if r[0] >= 1000 and r[1] is not None]
        scores = sorted(r[1] for r in settled)
        shown = [r[3] for r in settled]
        changes = sum(a != b for a, b in zip(shown, shown[1:]))
        return scores[0] / scores[len(scores) // 2], changes, sorted(set(shown))

    def test_pn129_flickers_between_two_levels_and_pn130_holds_one(self):
        for amp in (720, 1000):
            with self.subTest(amp=amp):
                old_dip, old_changes, old_levels = self.steady(PARENT, amp)
                new_dip, new_changes, new_levels = self.steady(CANDIDATE, amp)
                print(f'amp {amp}: PN1.29 dip {old_dip:.2f} changes {old_changes} levels {old_levels}; '
                      f'PN1.30 dip {new_dip:.2f} changes {new_changes} levels {new_levels}')
                self.assertLessEqual(old_dip, 0.55)
                self.assertGreater(old_changes, 0, 'negative control: PN1.29 flickers')
                self.assertGreaterEqual(new_dip, 0.8)
                self.assertEqual(new_changes, 0)
                self.assertEqual(len(new_levels), 1)


class Settle(Probe):
    """A strong pair touched at the Isolate position: the gain steps down at every window, the display never walks down."""

    def test_digital_settles_in_three_windows_and_the_display_only_rises(self):
        rows, levels = self.probe(CANDIDATE, mode=0, knob=768, amplitude=lambda ms: 30000, end_ms=3000)
        old_rows, old_levels = self.probe(PARENT, mode=0, knob=768, amplitude=lambda ms: 30000, end_ms=3000)
        self.assertEqual([(a, b) for _, a, b in levels], [(1, 7), (7, 2), (2, 1), (1, 0)])
        self.assertEqual([(a, b) for _, a, b in old_levels], [(1, 7), (7, 2), (2, 1), (1, 0)])
        steps = [ms for ms, _, _ in levels]
        self.assertTrue(all(b - a <= 300 for a, b in zip(steps, steps[1:])), levels)
        self.assertLessEqual(steps[-1] - steps[0], 800, levels)
        self.assertGreaterEqual(old_levels[-1][0] - old_levels[0][0], 1500, old_levels)
        shown = [r[3] for r in rows if r[0] > steps[0] and r[1] is not None]
        self.assertTrue(all(b >= a for a, b in zip(shown, shown[1:])), shown)
        self.assertEqual(shown[-1], [r[3] for r in old_rows if r[1] is not None][-1], 'same final level as PN1.29')
        heard = {r[2] for r in rows if steps[0] < r[0] <= steps[-1] and r[1] is not None}
        self.assertEqual(heard, {7, 2, 1}, 'every gain on the way down is heard once before the next step')
        self.assertEqual(IMG.clean_strength['persistent_ram_bytes'], 8)
        old_shown = [r[3] for r in old_rows if r[0] > old_levels[0][0] and r[1] is not None]
        self.assertTrue(any(b < a for a, b in zip(old_shown, old_shown[1:])), 'negative control: PN1.29 walks down')
        print('Digital settle PN1.29', old_levels, 'PN1.30', levels)

    def test_analog_settles_within_a_tenth_of_a_second(self):
        rows, levels = self.probe(CANDIDATE, mode=1, knob=768, amplitude=lambda ms: 30000, end_ms=1500)
        self.assertEqual([(a, b) for _, a, b in levels], [(1, 7), (7, 2), (2, 1), (1, 0)])
        self.assertLessEqual(levels[-1][0] - levels[0][0], 100, levels)
        old_rows, old_levels = self.probe(PARENT, mode=1, knob=768, amplitude=lambda ms: 30000, end_ms=2600)
        shown = [r[3] for r in rows if r[0] > levels[-1][0] + 50 and r[1] is not None]
        final = [r[3] for r in old_rows if r[0] > old_levels[-1][0] + 50 and r[1] is not None][-1]
        self.assertEqual(sorted(set(shown)), [final], shown)
        self.assertGreaterEqual(old_levels[-1][0] - old_levels[0][0], 1500, old_levels)
        print('Analog settle PN1.29', old_levels, 'PN1.30', levels, 'level', final)

    def test_lower_bound_never_lowers_but_an_unsaturated_drop_still_falls(self):
        # Strong pair, then a pair 6 dB weaker that still saturates the first gains: the display must
        # follow the real drop once the gain fits, within the 1/8 filter's time.
        amplitude = lambda ms: 30000 if ms < 2000 else 15000
        rows, levels = self.probe(CANDIDATE, mode=0, knob=768, amplitude=amplitude, end_ms=4000)
        shown = [(ms, lev) for ms, s, drv, lev, _ in rows if s is not None]
        before = [lev for ms, lev in shown if 1500 < ms < 2000]
        after = [lev for ms, lev in shown if ms > 3200]
        self.assertEqual(sorted(set(before)), [8], before)
        self.assertEqual(sorted(set(after)), [6], after)
        drop = next(ms for ms, lev in shown if ms > 2000 and lev == 6)
        self.assertLess(drop - 2000, 700, 'a real 6 dB drop shows within 0.7 s (PN1.29: about 1 s)')
        old_rows, _ = self.probe(PARENT, mode=0, knob=768, amplitude=amplitude, end_ms=4000)
        old_drop = next(ms for ms, s, drv, lev, _ in old_rows if ms > 2000 and s is not None and lev == 6)
        self.assertGreater(old_drop - 2000, drop - 2000, 'negative control: PN1.29 is slower')
        print('drop from level 8 to 6 shown at +%d ms (PN1.29 +%d ms)' % (drop - 2000, old_drop - 2000))


class Attack(unittest.TestCase):
    """PN1.24's AGC stream fixture, knob at 4 060: gain decisions at every completed window."""
    execute = response.GainResponseStreams.execute
    boundary = response.GainResponseStreams.boundary
    timers = response.GainResponseStreams.timers
    run_stream = response.GainResponseStreams.run_stream

    @classmethod
    def setUpClass(cls):
        cls.previous, cls.data = PARENT, CANDIDATE

    def test_saturation_steps_down_at_every_window_without_dropout(self):
        for mode, within in ((0, 300), (1, 60)):
            with self.subTest(mode=mode):
                old = self.run_stream(mode=mode, previous=True, changes={}, end_ms=2900, source_pp=20000)
                self.assertEqual(old['transitions'], [(500, 7, 2), (1000, 2, 1), (1500, 1, 0)])
                row = self.run_stream(mode=mode, changes={}, end_ms=2900, source_pp=20000)
                self.assertEqual([(a, b) for _, a, b in row['transitions']], [(7, 2), (2, 1), (1, 0)])
                steps = [ms for ms, _, _ in row['transitions']]
                self.assertTrue(all(b - a <= within for a, b in zip(steps, steps[1:])), row['transitions'])
                self.assertLessEqual(steps[-1], 500 + 2 * within + 50, row['transitions'])
                self.assertFalse(row['unowned_refreshes'])
                self.assertLess(row['max_quiet_ms'], 150, row['quiet'])
                print('mode', mode, 'PN1.30 transitions', row['transitions'])

    def test_step_up_keeps_the_hold_and_nothing_hunts(self):
        for mode in (0, 1):
            with self.subTest(mode=mode):
                row = self.run_stream(mode=mode, changes={}, end_ms=1800,
                                      source_pp=lambda ms: 2400 if ms < 1000 else 800)
                self.assertEqual([(a, b) for _, a, b in row['transitions']], [(7, 2), (2, 7)], row['transitions'])
                down, up = (ms for ms, _, _ in row['transitions'])
                self.assertLessEqual(down, 500)
                self.assertGreaterEqual(up, 1000)
                self.assertLessEqual(up, 1500)
                for amplitude, expected in ((1850, []), (1950, [(7, 2)]), (1170, []), (800, [])):
                    row = self.run_stream(mode=mode, changes={}, end_ms=3300, source_pp=amplitude)
                    self.assertEqual([(a, b) for _, a, b in row['transitions']], expected, amplitude)


class Cabinet(unittest.TestCase):
    """The owner's task (cabinet_scorecard) at the Isolate position, PN1.29 against PN1.30."""
    ISOLATE = 768

    def test_isolate_identifies_every_contact_strength_and_repeats(self):
        for mode in (0, 1):
            for target in scorecard.TARGETS:
                with self.subTest(mode=mode, target=target):
                    visits = scorecard.visit_fractions(CANDIDATE, mode=mode, knob=self.ISOLATE, target=target)
                    ok, failures, spread = scorecard.score(visits)
                    print('mode', mode, 'PN1.30 knob 19 % T', target, [(p, round(f, 2)) for p, f in visits], spread)
                    self.assertTrue(ok, failures)
                    self.assertLessEqual(spread['T'], 0.02)
                    self.assertLessEqual(spread['N6'], 0.02)


class Unchanged(Streams):
    def test_speaker_tone_and_mains_are_pn129(self):
        c = streams.StreamCPU(CANDIDATE)
        writes = []
        c.uc.hook_add(UC_HOOK_MEM_WRITE, lambda uc, access, a, size, value, user: writes.append(value), begin=CCR4, end=CCR4 + 1)
        for _ in range(4):
            self.execute(c, 0x08007508, 30, stack=SP - 0x400)
        self.assertEqual(writes, [1100, 500] * 2)

    def test_knob_off_still_silences_and_ncv_gain_follows_the_knob(self):
        for mode in (0, 1):
            row = self.stream(CANDIDATE, mode=mode, knob=4095, amplitude=lambda ms: 30000, end_ms=3600,
                              knob_changes={3000: 0})
            self.assertGreater(self.sounding(row, 2000, 3000), 100)
            self.assertEqual(self.sounding(row, 3300, 3600), 0)
        for knob, wanted in ((4095, 7), (800, 1), (300, 0)):
            row = self.stream(CANDIDATE, knob=knob, amplitude=lambda ms: 30000, end_ms=3700, mode_changes={3000: 2})
            self.assertEqual((row['mode'], row['driven']), (2, wanted), knob)

    def test_lost_signal_still_releases_through_the_tim1_countdown(self):
        for mode in (0, 1):
            row = self.stream(CANDIDATE, mode=mode, knob=4095, amplitude=lambda ms: 1500 if ms < 1500 else 0, end_ms=2500)
            self.assertGreater(self.sounding(row, 1000, 1500), 100, mode)
            self.assertEqual(self.sounding(row, 2000, 2500), 0, mode)

    def test_tracing_uses_the_full_gain_at_every_knob(self):
        for knob in (300, 2000, 4095):
            for mode in (0, 1):
                row = self.stream(CANDIDATE, mode=mode, knob=knob, amplitude=lambda ms: 60, end_ms=700)
                self.assertEqual(row['driven'], 7, (knob, mode))


if __name__ == '__main__':
    unittest.main()
