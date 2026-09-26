"""PN 2.19 cable-robust (and the cable-diag experiment): the wire map run end to end on the real
routines under Unicorn (thai/engine.py) with a simulated far end -- nothing plugged in (with
mains hum on the floating wires), a switch port, the RX unit, faults -- in English and in Thai.

    python -m unittest test_cable_test -v
"""
import contextlib
import hashlib
import io
import os
import random
import struct
import unittest

from lpm10a.image import Image
import cable_test as CT
from profiles import PROFILES, apply_profile
from thai.engine import Scene
from thai.mockup import sc_cable_result, sc_cable_test_a

HERE = os.path.dirname(os.path.abspath(__file__))
FW_DIR = os.path.dirname(HERE)
STOCK = os.path.join(FW_DIR, "LPM-10A-TX_V2.0.7_260610.bin")
SELECT, ADC, DELAY = 0x080180A0, 0x080107A4, 0x0801C75C
TAB = [1655, 1975, 2319, 2607, 2935, 3183, 3391, 3679, 3900]    # far-end mode: the reading each remote pin gives
SWITCH_PAIRS = {0: 1, 1: 0, 2: 5, 5: 2, 3: 4, 4: 3, 6: 7, 7: 6}
OPEN, OK, CROSSED, SHORT = 1, 2, 3, 0
SWITCH, FAR_END = 0, 1


def build(name, extra=()):
    with contextlib.redirect_stdout(io.StringIO()):
        img = Image(STOCK)
        apply_profile(img, PROFILES[name], extra=extra)
    return img


def far_end(kind, mapping=None):
    """reading(driven, sensed) for a simulated far end; 4095 = nothing there (pull-up)."""
    def reading(d, s):
        if kind == "switch":
            return 60 if SWITCH_PAIRS.get(d) == s else 4095
        if kind == "switch-open3":                      # pin 3 broken: its pair partner 6 loses the path too
            return 60 if SWITCH_PAIRS.get(d) == s and d not in (2, 5) else 4095
        if kind == "remote":                            # every other pin reads the driven pin's remote value
            m = mapping if mapping is not None else {i: i for i in range(9)}
            return TAB[m[d]] if d in m else 4095
        if kind == "remote-short12":
            if {d, s} == {0, 1}:
                return 30
            return TAB[d] if d not in (0, 1) else 4095
        return 4095                                     # floating
    return reading


class Harness:
    def __init__(self, data, mode, kind, hum=0, seed=1, mapping=None, lang=1, wires=None):
        self.s = s = Scene(image=data, lang=lang)
        rnd = random.Random(seed)
        sel = {0: 0, 1: 0}
        f = far_end(kind, mapping)
        self.adc_calls = 0
        self.delays = []

        def select(uc):
            sel[s.arg(1)] = s.arg(0)
            return False

        def adc(uc):
            v = f(sel[0], sel[1])
            if hum and v >= 4000:                       # hum rides on a floating wire; the ADC clips at the rail
                v = min(4095, max(0, v + rnd.randint(-hum, hum)))
            self.adc_calls += 1
            s.ret(v)
            return True

        def delay(uc):
            self.delays.append(s.arg(0))
            s.ret(0)
            return True
        s.at[SELECT], s.at[ADC], s.at[DELAY] = select, adc, delay
        sc_cable_result(s, mode=mode, wires=wires)
        self.status = list(s.uc.mem_read(0x2000023E, 9))
        self.map = struct.unpack("<9H", s.uc.mem_read(0x20000248, 18))
        self.texts = [(t, x, y, fg) for k, t, x, y, fg, ex in s.log
                      if k == "ascii" and y > 260 and t not in ("Test Retry", "Testing...")]   # button labels
        self.thai = [(t, x, y) for k, t, x, y, fg, ex in s.log if k == "glyph" and 265 <= y <= 290]


class CableRobust(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.img = build("pn2.19")
        cls.data = bytes(cls.img.finalize().data)
        cls.info = cls.img.cable
        parent = build("pn2.18")
        cls.parent, cls.parent_end = bytes(parent.finalize().data), parent.cave_ptr

    # -- static ---------------------------------------------------------------
    def test_parent_is_pn218_and_only_the_listed_sites_moved(self):
        self.assertEqual(hashlib.sha256(self.parent).hexdigest(), CT.PARENT_SHA256)
        self.assertEqual(len(self.parent), len(self.data))
        changed = {i for i in range(len(self.parent)) if self.parent[i] != self.data[i]}
        allowed = set(range(0x24, 0x2C))
        sites = {**{s: 6 for s in CT.SAMPLE_SITES}, **{s: 4 for s in CT.RELEASE_SITES},
                 CT.SWITCH_OPEN: 4, CT.FAR_OPEN_SITE: 6, CT.FAR_END_STRING: 16,
                 self.img.thai["reloc"] + 4 * self.img.thai["texts"].index("ปลายสาย"): 4}
        for site, n in sites.items():
            o = site - 0x0800A000 + 0x1000
            allowed |= set(range(o, o + n))
        for s in (0x08011660, 0x08012E6C):
            o = s - 0x0800A000 + 0x1000
            allowed |= set(range(o, o + 8))
        appended = {i for i in changed if i >= self.parent_end - 0x0800A000 + 0x1000}
        self.assertTrue(changed - appended <= allowed, "PN 2.19 touches only its sites, the label, the version and the header")
        self.assertEqual(self.info["sample"], self.parent_end)
        o = CT.FAR_END_STRING - 0x0800A000 + 0x1000
        self.assertEqual(self.data[o:o + 16].hex(), CT.u16(CT.LABEL_EN))
        o = CT.SWITCH_OPEN - 0x0800A000 + 0x1000
        self.assertEqual(self.data[o:o + 4].hex(), CT.SWITCH_OPEN_NEW)
        ptr = self.img.thai["reloc"] + 4 * self.img.thai["texts"].index("ปลายสาย")
        o = ptr - 0x0800A000 + 0x1000
        self.assertEqual(struct.unpack("<I", self.data[o:o + 4])[0], self.info["label_th"])
        cells = self.img.thai["table"].encode_cjk(CT.LABEL_TH)
        o = self.info["label_th"] - 0x0800A000 + 0x1000
        self.assertEqual(self.data[o:o + len(cells)], cells)

    # -- the sampler ---------------------------------------------------------------
    def test_sample_returns_the_median_and_keeps_min_and_max(self):
        s = Scene(image=self.data, lang=1)
        values = [4095, 3700, 4095, 3900, 4095, 3650, 4095, 4095, 3800, 4095, 3950]
        seq = iter(values)
        delays = []
        s.at[ADC] = lambda uc: (s.ret(next(seq)), True)[1]
        s.at[DELAY] = lambda uc: (delays.append(s.arg(0)), s.ret(0), True)[2]
        from unicorn.arm_const import UC_ARM_REG_R4, UC_ARM_REG_R5
        s.uc.reg_write(UC_ARM_REG_R4, 3); s.uc.reg_write(UC_ARM_REG_R5, 5)  # driven pin 3, slot 5, as the routines hold them
        got = s.call(self.info["sample"])
        self.assertEqual(got, sorted(values)[5])
        self.assertEqual(delays, [1] * 10, "eleven samples one tick apart")
        idx = (3 * 8 + 5) * 2
        med = struct.unpack("<H", s.uc.mem_read(self.info["med"] + idx, 2))[0]
        lo = struct.unpack("<H", s.uc.mem_read(self.info["lo"] + idx, 2))[0]
        hi = struct.unpack("<H", s.uc.mem_read(self.info["hi"] + idx, 2))[0]
        self.assertEqual((lo, med, hi), (min(values), sorted(values)[5], max(values)))

    # -- the wire map end to end ----------------------------------------------------
    def test_nothing_connected_is_not_connected_in_both_modes_even_with_hum(self):
        for mode in (SWITCH, FAR_END):
            for seed in range(1, 6):
                with self.subTest(mode=mode, seed=seed):
                    h = Harness(self.data, mode, "floating", hum=300, seed=seed)
                    self.assertEqual(h.status, [OPEN] * 9)
                    self.assertEqual(h.texts, [("Not connected", 68, 271, 0xF800)])
                    self.assertEqual(h.adc_calls, 72 * CT.SAMPLES)
                    self.assertEqual(h.delays.count(2), 72)
                    self.assertEqual(h.delays.count(1), 72 * (CT.SAMPLES - 1))

    def test_pn218_was_random_on_the_same_readings(self):
        seen = set()
        for mode in (SWITCH, FAR_END):
            for seed in range(1, 4):
                h = Harness(self.parent, mode, "floating", hum=300, seed=seed)
                seen.add((mode, tuple(h.status)))
                self.assertEqual(h.adc_calls, 72, "stock: one sample per sensed pin")
        self.assertTrue(any(st != (OPEN,) * 9 for m, st in seen), "PN 2.18 called floating wires connected or crossed")

    def test_thai_says_not_connected_in_thai(self):
        h = Harness(self.data, FAR_END, "floating", hum=300, lang=2)
        self.assertEqual(h.status, [OPEN] * 9)
        self.assertEqual(h.texts, [], "no ASCII text in Thai")
        self.assertTrue(h.thai, "the Thai message is drawn from the cells on the error line")
        xs = [x for t, x, y in h.thai]
        self.assertTrue(min(xs) < 120 < max(xs), "centred on x 120")
        self.assertTrue(all(h.s.fb[y][x] != 0xFFFF for y in range(271, 287) for x in range(60, 180)))
        self.assertTrue(any(h.s.fb[y][x] == 0xF800 for y in range(271, 287) for x in range(60, 180)), "red like the wires")

    def test_switch_port_pairs_are_connected_and_the_shield_is_open(self):
        h = Harness(self.data, SWITCH, "switch", hum=300)
        self.assertEqual(h.status, [OK] * 8 + [OPEN])
        self.assertEqual(h.texts, [])
        h = Harness(self.data, SWITCH, "switch-open3", hum=300)
        self.assertEqual(h.status, [OK, OK, OPEN, OK, OK, OPEN, OK, OK, OPEN], "a broken wire takes its pair partner with it")
        self.assertEqual(h.texts, [])

    def test_switch_mode_needs_a_real_short(self):
        # a floating wire whose level has drifted to 3000 (leakage): stock called it connected, PN 2.19 does not
        s = Scene(image=self.data, lang=1)
        s.at[SELECT] = lambda uc: False
        s.at[ADC] = lambda uc: (s.ret(3000), True)[1]
        s.at[DELAY] = lambda uc: (s.ret(0), True)[1]
        sc_cable_result(s, mode=SWITCH)
        self.assertEqual(list(s.uc.mem_read(0x2000023E, 9)), [OPEN] * 9)
        p = Scene(image=self.parent, lang=1)
        p.at[SELECT] = lambda uc: False
        p.at[ADC] = lambda uc: (p.ret(3000), True)[1]
        p.at[DELAY] = lambda uc: (p.ret(0), True)[1]
        sc_cable_result(p, mode=SWITCH)
        self.assertEqual(list(p.uc.mem_read(0x2000023E, 9)), [OK] * 9, "PN 2.18: anything under 4000 was a connection")

    def test_far_end_mode_still_maps_the_remote(self):
        h = Harness(self.data, FAR_END, "remote", hum=300)
        self.assertEqual(h.status, [OK] * 9)
        self.assertEqual(h.texts, [])
        crossed = {i: i for i in range(9)}
        crossed[0], crossed[2] = 2, 0
        h = Harness(self.data, FAR_END, "remote", hum=300, mapping=crossed)
        self.assertEqual(h.status, [CROSSED, OK, CROSSED, OK, OK, OK, OK, OK, OK])
        self.assertEqual((h.map[0], h.map[2]), (2, 0), "pin 1 reaches remote pin 3 and pin 3 remote pin 1")
        h = Harness(self.data, FAR_END, "remote-short12", hum=300)
        self.assertEqual(h.status[:2], [SHORT, SHORT])
        self.assertEqual(h.status[2:], [OK] * 7)
        one_open = {i: i for i in range(9) if i != 4}
        h = Harness(self.data, FAR_END, "remote", hum=300, mapping=one_open)
        self.assertEqual(h.status, [OK, OK, OK, OK, OPEN, OK, OK, OK, OK])
        self.assertEqual(h.texts, [], '"Not connected" only when every signal pin is open')

    def test_mode_selector_names_the_rx_unit(self):
        s = Scene(image=self.data, lang=1)
        sc_cable_test_a(s, mode=1)
        self.assertIn(("RX unit", 178, 190), [(t, x, y) for k, t, x, y, fg, ex in s.log if k == "mixed"])
        self.assertNotIn("Far end", [t for k, t, x, y, fg, ex in s.log])
        th = Scene(image=self.data, lang=2)
        sc_cable_test_a(th, mode=1)
        glyphs = [(x, y) for k, t, x, y, fg, ex in th.log if k == "glyph" and y == 190 and x > 130]
        self.assertTrue(glyphs, "the Thai label is drawn from the cells")
        parent = Scene(image=self.parent, lang=2)
        sc_cable_test_a(parent, mode=1)
        self.assertNotEqual([r[130:230] for r in th.fb[185:210]], [r[130:230] for r in parent.fb[185:210]],
                            "the Thai label changed")
        self.assertEqual([r[:130] for r in th.fb], [r[:130] for r in parent.fb], "the Switch box did not")


class CableDiag(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.img = build("pn2.19", extra=("cable-diag",))
        cls.data = bytes(cls.img.finalize().data)

    def test_diag_prints_the_deciding_numbers_per_row(self):
        h = Harness(self.data, SWITCH, "switch-open3", hum=0)
        rows = [(t, x, y) for k, t, x, y, fg, ex in h.s.log if k == "ascii" and ex["size"] == 12]
        self.assertEqual(len(rows), 9)
        for i, (t, x, y) in enumerate(rows):
            self.assertEqual((x, y), (CT.DIAG_X, CT.ROW0_Y - 6 + CT.ROW_PITCH * i))
        self.assertEqual(rows[0][0], "2   60   60", "pin 1: lowest median 60 at pin 2, that pin's highest sample 60")
        self.assertEqual(rows[2][0], "- 4095 4095", "pin 3 (broken): nothing under 4000")
        self.assertEqual(rows[8][0], "- 4095 4095")
        self.assertEqual(h.status, [OK, OK, OPEN, OK, OK, OPEN, OK, OK, OPEN], "the result itself is PN 2.19's")
        h = Harness(self.data, SWITCH, "floating", hum=300)
        self.assertEqual(h.texts, [("Not connected", 68, 271, 0xF800)], "the release hook still runs first")


class CableDiagLatest(CableDiag):
    """Diagnostics can replace the latest compact values without drawing both."""

    @classmethod
    def setUpClass(cls):
        from profiles import LATEST
        cls.img = build(LATEST, extra=("cable-diag",))
        cls.data = bytes(cls.img.finalize().data)

    def harness(self, mode, kind, *, lang=1):
        # The current image requires real generation-tagged key/GUI traffic.
        # Historical diagnostic fixtures above intentionally retain raw GUI 0x11.
        from test_cable_session import SessionHarness
        h = SessionHarness(self.data, mode=mode, lang=lang, reading=far_end(kind))
        h.send(2)
        h.flush()
        h.status = list(h.s.uc.mem_read(0x2000023E, 9))
        h.texts = [(t, x, y, fg) for k, t, x, y, fg, ex in h.s.log if k == 'ascii' and y == 271]
        return h

    def test_diag_prints_the_deciding_numbers_per_row(self):
        h = self.harness(SWITCH, 'switch-open3')
        rows = [(t, x, y) for k, t, x, y, fg, ex in h.s.log if k == 'ascii' and ex['size'] == 12]
        self.assertEqual(len(rows), 9)
        for i, (t, x, y) in enumerate(rows):
            self.assertEqual((x, y), (CT.DIAG_X, CT.ROW0_Y - 6 + CT.ROW_PITCH * i))
        self.assertEqual(rows[0][0], '2   60   60')
        self.assertEqual(rows[2][0], '- 4095 4095')
        self.assertEqual(rows[8][0], '- 4095 4095')
        self.assertEqual(h.status, [OK, OK, OPEN, OK, OK, OPEN, OK, OK, OPEN])
        h = self.harness(SWITCH, 'floating')
        self.assertEqual(h.texts, [('Not connected', 68, 271, 0xF800)])

    def test_rx_unit_diagnostics_keep_one_row_per_wire_in_both_languages(self):
        for lang in (1, 2):
            with self.subTest(lang=lang):
                h = self.harness(FAR_END, 'remote', lang=lang)
                rows = [t for k, t, x, y, fg, ex in h.s.log if k == "ascii" and ex["size"] == 12]
                self.assertEqual(len(rows), 9, "the compact cable-values hook must not also draw")
                self.assertEqual([int(t[1:6]) for t in rows], TAB)
                self.assertEqual([int(t[6:]) for t in rows], TAB)
                self.assertEqual(h.status, [OK] * 9)


if __name__ == "__main__":
    unittest.main()
