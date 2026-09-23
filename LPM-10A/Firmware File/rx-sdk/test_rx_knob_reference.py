"""PN1.27: knob reference over the whole travel, peak-relative mute below the middle.

The analysers, publisher, AGC, sampler and speaker of the built image execute in
Unicorn; ADC values, the analogue link and interrupt arrival are modeled. The
arithmetic is checked against an independent model of its stated rules; the top
sixteenth of the knob against PN1.24. None of this measures pickup, coupling
between real pairs or loudness.
"""
import contextlib
import hashlib
import io
import random
import struct
import unittest

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_MCLASS
from unicorn import UC_HOOK_MEM_WRITE

import auto_range
import isolate
import knob_reference as knob
import relative_isolate as pn126
import rx_precision
import test_rx_digital_strong_gain as strong
import test_rx_relative_isolate as base
import test_rx_tracking_streams as streams
from lpm10rx import symbols
from lpm10rx.container import unwrap, wrap
from lpm10rx.image import PatchError
from test_rx_analog_fast import corpus as analog_corpus
from test_rx_isolate import (CCR4, Streams, analog_windows, clipped_digital, digital_windows, smoothed, walk)
from test_scan_acquisition_timing import TIMER_COUNTER
from verify_control import SP
from verify_digital import pattern

PARENT = CANDIDATE = IMG = None
CANDIDATE_SHA256 = 'febd648daa98b51cf06c35e855afa4a088bb789c8ae643acf42b0f828c081c83'
MULT = base.MULT
KNOBS = (2, 300, 580, 700, 1024, 1300, 1600, 1900, 2047, 2048, 2600, 3200, 3839)
TOP_KNOBS = (3840, 4000, 4095)
DIGITAL_HOLD, ANALOG_HOLD = 660, 560


def setUpModule():
    global PARENT, CANDIDATE, IMG
    with contextlib.redirect_stdout(io.StringIO()):
        PARENT = bytes(rx_precision.build_candidate().data)
    IMG = knob.build_candidate()
    CANDIDATE = bytes(IMG.data)


def model(raw, level, knob_raw, peak, elapsed):
    """(quiet interval or None when muted, new peak, unfinished decay ticks)."""
    score = raw & 0xFFFFFFFF
    if level <= 7:
        score = ((score * MULT[level]) & 0xFFFFFFFF) // 10
    score = min(score, knob.CLAMP)
    peak, rest = base.decayed(peak, elapsed)
    peak = max(peak, score)
    w = pn126.window(knob_raw)
    if w is not None and score < (peak * w >> 8):
        return None, peak, rest
    return walk(score * knob.reference(knob_raw) >> 8), peak, rest


class Analysers(base.Analysers):
    def entry(self, data):
        return IMG.knob_reference['curve'] if data is CANDIDATE else isolate.OLD_CURVE

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
        self.assertEqual(IMG.knob_reference['start'], symbols.APP_BASE + len(PARENT))
        allowed = set()
        for site, size in ((isolate.GAP_ENTRY, 4), (isolate.DIGITAL_UNCERTAIN, 4), (isolate.ANALOG_SITE, 24),
                           (isolate.GAIN_SITE, 4), (isolate.TONE_HIGH, 4), (isolate.TONE_LOW, 4),
                           (0x0800CDE4, 8)):
            allowed |= set(range(site, site + size))
        changed = {symbols.APP_BASE + i for i, (a, b) in enumerate(zip(PARENT, CANDIDATE)) if a != b}
        self.assertTrue(changed)
        self.assertLessEqual(changed, allowed)
        self.assertEqual(len(CANDIDATE) - len(PARENT), IMG.knob_reference['helper_bytes'])
        self.assertLessEqual(symbols.APP_BASE + len(CANDIDATE), symbols.EXTEND_LIMIT)
        self.assertEqual(CANDIDATE[0x0800CDE4 - symbols.APP_BASE:][:8], b'PN1.27\0\0')

    def test_changed_parent_is_rejected_before_any_byte_changes(self):
        with contextlib.redirect_stdout(io.StringIO()):
            img = rx_precision.build_candidate()
        img.data[img.f(isolate.GAIN_SITE)] ^= 1
        before = bytes(img.data), list(img.log)
        with self.assertRaises(PatchError):
            knob.apply(img)
        self.assertEqual((bytes(img.data), img.log), before)

    def test_written_candidate_is_this_exact_build(self):
        self.assertEqual(hashlib.sha256(CANDIDATE).hexdigest(), CANDIDATE_SHA256)
        raw, update = knob.DIRECTORY / knob.OUTPUT, knob.DIRECTORY / knob.UPDATE
        if not raw.exists():
            self.skipTest('experimental PN1.27 files not written yet (python knob_reference.py --write)')
        self.assertEqual(raw.read_bytes(), CANDIDATE)
        self.assertEqual(update.read_bytes(), wrap(CANDIDATE))
        self.assertEqual(unwrap(update.read_bytes())[1], CANDIDATE)
        sums = (knob.DIRECTORY / knob.SUMS).read_text(encoding='ascii').split()
        self.assertEqual(sums, [CANDIDATE_SHA256, knob.OUTPUT, hashlib.sha256(wrap(CANDIDATE)).hexdigest(), knob.UPDATE])

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

    def test_tables_in_image_and_reference_law(self):
        refs = [knob.reference(k) for k in range(4096)]
        self.assertEqual(refs, sorted(refs), 'the reference only rises with the knob')
        self.assertEqual((refs[2], refs[3839], refs[3840], refs[4095]), (8, 255, 256, 256))
        start = IMG.knob_reference['curve'] - symbols.APP_BASE
        blob = struct.pack(f'<{len(pn126.WINDOW) + len(knob.REFERENCE)}H', *pn126.WINDOW, *knob.REFERENCE)
        self.assertIn(blob, CANDIDATE[start:start + 0x180])


class Digital(Analysers, unittest.TestCase):
    def test_top_sixteenth_is_pn124_whatever_the_peak(self):
        cases = 0
        windows = list(digital_windows()) + list(clipped_digital())
        rng = random.Random(0x127D)
        windows += [(f'noise_{n}', [rng.randrange(4096) for _ in range(48)]) for n in range(8)]
        for knob_raw in TOP_KNOBS:
            for level in (0, 2, 7):
                for grade, recent in ((0, 0), (20, 800), (65, 700)):
                    for peak, elapsed in base.PEAKS[::2]:
                        for name, samples in windows:
                            kw = dict(knob=knob_raw, level=level, grade=grade, recent=recent, mask=cases & 1)
                            new = self.analyse(CANDIDATE, samples, peak=peak, elapsed=elapsed, **kw)
                            old = self.analyse(PARENT, samples, **kw)
                            self.assertEqual(new[:2], old[:2], (knob_raw, level, name, peak))
                            cases += 1
        print('Digital top-sixteenth vectors identical to PN1.24:', cases)

    def test_every_knob_position_follows_the_model(self):
        cases = muted = 0
        for knob_raw in KNOBS:
            for level in (0, 1, 2, 7):
                for grade, recent in ((0, 0), (45, 800)):
                    for peak, elapsed in base.PEAKS:
                        for name, samples in digital_windows():
                            kw = dict(knob=knob_raw, level=level, grade=grade, recent=recent)
                            parent_state, parent_scores = self.analyse(PARENT, samples, **kw)[:2]
                            state, scores, stored = self.analyse(CANDIDATE, samples, peak=peak, elapsed=elapsed, **kw)
                            self.assertEqual(scores, parent_scores)
                            if not scores:
                                self.assertEqual(state, parent_state)
                                self.assertEqual(stored, (peak, elapsed))
                                continue
                            want = self.expected(parent_state, scores[0], mode=0, knob=knob_raw, level=level,
                                                 grade=grade, recent=recent, gap=0, peak=peak, elapsed=elapsed)
                            self.assertEqual((state, stored), want, (knob_raw, level, name, grade, peak, elapsed))
                            cases += 1
                            muted += model(scores[0], level, knob_raw, peak, elapsed)[0] is None
        self.assertGreater(muted, 200)
        print('Digital model vectors:', cases, 'muted', muted)

    def test_clipped_window(self):
        for name, samples in clipped_digital():
            old = self.analyse(PARENT, samples)
            self.assertEqual(old[0][:2], (20, 800))
            for knob_raw in TOP_KNOBS:
                self.assertEqual(self.analyse(CANDIDATE, samples, knob=knob_raw)[0], old[0])
            for knob_raw in KNOBS:
                for level in (0, 2, 7):
                    for peak, elapsed in base.PEAKS[:4]:
                        state, scores, stored = self.analyse(CANDIDATE, samples, knob=knob_raw, level=level,
                                                             peak=peak, elapsed=elapsed)
                        self.assertEqual(scores, (knob.SATURATION_SCORE,))
                        parent_state = self.analyse(PARENT, samples, knob=knob_raw, level=level)[0]
                        want = self.expected(parent_state, knob.SATURATION_SCORE, mode=0, knob=knob_raw, level=level,
                                             grade=0, recent=0, gap=0, peak=peak, elapsed=elapsed)
                        self.assertEqual((state, stored), want, (name, knob_raw, level, peak))


class Analog(Analysers, unittest.TestCase):
    def test_top_sixteenth_is_pn124_whatever_the_peak(self):
        cases = 0
        windows = list(analog_corpus()) + list(analog_windows())
        for knob_raw in (3840, 4095):
            for level in (0, 7):
                for grade, recent, gap in ((0, 0, 0), (45, 800, 90)):
                    for peak, elapsed in base.PEAKS[::3]:
                        for name, samples in windows:
                            kw = dict(mode=1, knob=knob_raw, level=level, grade=grade, recent=recent, gap=gap,
                                      mask=cases & 1)
                            new = self.analyse(CANDIDATE, samples, peak=peak, elapsed=elapsed, **kw)
                            old = self.analyse(PARENT, samples, **kw)
                            self.assertEqual(new[:2], old[:2], (knob_raw, level, name))
                            cases += 1
        print('Analog top-sixteenth vectors identical to PN1.24:', cases)

    def test_every_knob_position_follows_the_model(self):
        cases = muted = 0
        for knob_raw in KNOBS[2:]:
            for level in (0, 2, 7):
                for grade, recent, gap in ((0, 0, 0), (45, 800, 90)):
                    for peak, elapsed in base.PEAKS:
                        for name, samples in analog_windows():
                            kw = dict(mode=1, knob=knob_raw, level=level, grade=grade, recent=recent, gap=gap)
                            parent_state, parent_scores = self.analyse(PARENT, samples, **kw)[:2]
                            state, scores, stored = self.analyse(CANDIDATE, samples, peak=peak, elapsed=elapsed, **kw)
                            self.assertEqual(scores, parent_scores)
                            if not scores:
                                self.assertEqual(state, parent_state)
                                continue
                            want = self.expected(parent_state, scores[0], mode=1, knob=knob_raw, level=level,
                                                 grade=grade, recent=recent, gap=gap, peak=peak, elapsed=elapsed)
                            self.assertEqual((state, stored), want, (knob_raw, level, name, peak, elapsed))
                            cases += 1
                            muted += model(scores[0], level, knob_raw, peak, elapsed)[0] is None
        self.assertGreater(muted, 50)
        print('Analog model vectors:', cases, 'muted', muted)


class MainsAndSpeaker(Analysers, unittest.TestCase):
    def test_mains_analysis_is_pn124(self):
        for knob_raw in (0, 700, 2048, 4095):
            for name, samples in list(analog_corpus())[:40]:
                kw = dict(mode=2, knob=knob_raw, level=2, grade=0, recent=700)
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
    def test_gain_hook_is_pn126s_source(self):
        gain = IMG.knob_reference['gain']
        code = IMG.assemble_at(gain, pn126.gain_source(IMG.knob_reference['peak_now']))
        self.assertEqual(CANDIDATE[gain - symbols.APP_BASE:][:len(code)], code)

    def test_compare_ceiling_follows_the_peak_and_window(self):
        for knob_raw in (300, 700, 1300, 1900, 2047, 2048, 4095):
            for peak in (0, 20_000, 120_000, 400_000, 900_000, knob.CLAMP):
                c = strong.GainStreamCPU(CANDIDATE, mode=0, level=7)
                c.knob_raw = knob_raw
                c.w16(0x20000068, knob_raw)
                c.uc.mem_write(auto_range.STATE, bytes((7, 0, 0, 7)))
                c.w32(TIMER_COUNTER, 5000)
                c.w32(knob.PEAK, peak)
                c.w32(knob.PEAK + 4, 5000)
                c.w32(0x200000FC, 499)          # TIM1 tick: the next interrupt runs the 500 ms work
                self.execute(c, strong.TIM1, stack=SP - 0x500, budget=10000)
                self.assertEqual(c.read(auto_range.STATE), pn126.ceiling(peak, knob_raw), (knob_raw, peak))
                self.assertEqual(c.read(knob.PEAK, 4), peak)

    def test_tracing_uses_the_full_gain_for_a_lone_cable(self):
        for knob_raw, pn124 in ((300, 0), (1000, 1), (2000, 2), (4095, 7)):
            for mode in (0, 1):
                old = self.stream(PARENT, mode=mode, knob=knob_raw, amplitude=lambda ms: 60, end_ms=700)
                new = self.stream(CANDIDATE, mode=mode, knob=knob_raw, amplitude=lambda ms: 60, end_ms=700)
                self.assertEqual((old['driven'], new['driven']), (pn124, 7), (knob_raw, mode))

    def test_full_knob_agc_is_pn124(self):
        for mode in (0, 1):
            for amplitude, end in ((lambda ms: 2400 if ms < 1000 else 800, 1800), (lambda ms: 20000, 2900)):
                old = self.stream(PARENT, mode=mode, knob=4095, amplitude=amplitude, end_ms=end)
                new = self.stream(CANDIDATE, mode=mode, knob=4095, amplitude=amplitude, end_ms=end)
                self.assertEqual(new['levels'], old['levels'])
                self.assertEqual(new['publications'], old['publications'])

    def test_ncv_gain_follows_the_knob(self):
        for knob_raw, wanted in ((4095, 7), (1100, 7), (800, 1), (300, 0)):
            new = self.stream(CANDIDATE, knob=knob_raw, amplitude=lambda ms: 30000, end_ms=3700,
                              mode_changes={3000: 2})
            self.assertEqual((new['mode'], new['driven']), (2, wanted), knob_raw)

    def test_knob_off_still_silences(self):
        for mode in (0, 1):
            row = self.stream(CANDIDATE, mode=mode, knob=4095, amplitude=lambda ms: 30000,
                              end_ms=3600, knob_changes={3000: 0})
            self.assertGreater(self.sounding(row, 2000, 3000), 100)
            self.assertEqual(self.sounding(row, 3300, 3600), 0)


class Field(Streams):
    def test_lone_cable_sounds_low_on_the_knob_and_speeds_up_with_it(self):
        for mode, amplitude, knobs in ((0, 600, (300, 1024, 2048, 3072, 4095)), (1, 600, (700, 1024, 2048, 3072, 4095))):
            tone = []
            for knob_raw in knobs:
                row = self.stream(CANDIDATE, mode=mode, knob=knob_raw, amplitude=lambda ms: amplitude, end_ms=1600)
                tone.append(round(self.sounding(row, 800, 1600) / 800, 2))
            print('mode', mode, 'lone cable amplitude', amplitude, 'knob', knobs, 'tone fraction', tone)
            self.assertGreater(tone[0], 0.1, 'audible low on the knob')
            self.assertTrue(all(b >= a - 0.02 for a, b in zip(tone, tone[1:])),
                            'no slower rhythm as the knob rises (0.02 = one-pulse measuring granularity)')
            self.assertGreater(tone[-1], tone[0] + 0.05, 'the knob makes an audible difference')

    TARGET, NEIGHBOUR, SEGMENT = 30000, 6000, 1200

    def pairs(self, ms):
        return self.TARGET if (ms // self.SEGMENT) % 2 == 0 else self.NEIGHBOUR

    def test_cabinet(self):
        for mode, low in ((0, 300), (1, 600)):
            for knob_raw in (low, 2100, 4095):
                row = self.stream(CANDIDATE, mode=mode, knob=knob_raw, amplitude=self.pairs, end_ms=6000)
                duty = [self.sounding(row, n * self.SEGMENT + 500, (n + 1) * self.SEGMENT) / (self.SEGMENT - 500)
                        for n in range(5)]
                print('mode', mode, 'PN1.27 knob', knob_raw, 'tone fraction per segment', [round(d, 2) for d in duty])
                if knob_raw == low:
                    self.assertGreater(min(duty[2], duty[4]), 0.1, 'target sounds')
                    self.assertEqual(duty[3], 0.0, 'neighbour muted next to the target')
                elif knob_raw == 2100:
                    # K about -14 dB: only the target stays at the fastest point.
                    self.assertGreater(min(duty[2], duty[4]), duty[3] + 0.1, 'target faster than neighbour')
                else:
                    self.assertTrue(all(d > 0.3 for d in duty[2:]), 'full knob: both sound, as PN1.24')


if __name__ == '__main__':
    unittest.main()
