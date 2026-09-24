"""PN2.28 cable-check: the wire map run end to end on the real routines under Unicorn.

Every defect test also runs the PN2.27A parent and asserts its wrong answer, so each one is a
red-then-green check of the audit finding named in its docstring
(docs/TX-CABLE-TEST-AUDIT-2026-09-23.md).  The far ends are models (no schematic exists):
a switch joins the far ends of each T568 pair (reading 60), a short reads 30, the RX unit's
ladder gives every connected sensed pin the driven pin's remote value, and a floating wire
sits at the rail with optional 50 Hz hum.

    python -m unittest test_cable_check -v
"""
import contextlib
import hashlib
import io
import math
import struct
import unittest

import cable_check as CC
from thai.engine import Scene
from thai.mockup import sc_cable_result

SELECT, ADC, DELAY = 0x080180A0, 0x080107A4, 0x0801C75C
RGB_LED, BEEP, GUI_MSG_SEND = 0x08010F94, 0x080116E0, 0x0800E428
TAB = [1655, 1975, 2319, 2607, 2935, 3183, 3391, 3679, 3900]
PARTNER = {0: 1, 1: 0, 2: 5, 5: 2, 3: 4, 4: 3, 6: 7, 7: 6}
SHORT, OPEN, OK, CROSSED, UNKNOWN, UNTESTED = 0, 1, 2, 3, 4, 5
SWITCH, RX = 0, 1
STRAIGHT = {i: i for i in range(9)}
CROSSOVER = {0: 2, 1: 5, 2: 0, 5: 1, 3: 3, 4: 4, 6: 6, 7: 7, 8: 8}          # T568A at one end, B at the other


def images():
    with contextlib.redirect_stdout(io.StringIO()):
        img = CC.build_candidate()
        import tone_alignment
        parent = tone_alignment.build_candidate()
    return img, bytes(img.data), bytes(parent.data)


def switch_end(wiring=STRAIGHT, shorts=(), cross=None, tied4578=False, plugged=True):
    """reading(driven, sensed) or None (floating) with the cable's far end in a switch port."""
    def reading(d, s):
        for group in shorts:                        # a crushed / miscrimped short: about 0 ohm, like a winding
            if d in group and s in group:
                return 60
        if not plugged:
            return None
        fd, fs = wiring.get(d), wiring.get(s)
        if fd is None or fs is None or 8 in (fd, fs):
            return None
        if PARTNER[fd] == fs:
            return 60
        if tied4578 and {fd, fs} <= {3, 4, 6, 7}:
            return 60
        if cross is not None:                       # centre taps into a Bob-Smith network
            return cross
        return None
    return reading


def rx_end(wiring=STRAIGHT, gain=1.0, shorts=()):
    """The RX unit: every connected sensed pin reads the driven pin's remote ladder value."""
    def reading(d, s):
        for group in shorts:
            if d in group and s in group:
                return 30
        fd, fs = wiring.get(d), wiring.get(s)
        if fd is None or fs is None:
            return None
        return round(TAB[fd] * gain)
    return reading


class Rig:
    """One Test Retry: the real 0x11 path with the far end, hum and optional mid-test events."""

    def __init__(self, data, mode, reading, lang=1, hum=0, hum_connected=False, phase=0.0, hz=50, events=None):
        self.s = s = Scene(image=data, lang=lang)
        sel = {0: 0, 1: 0}
        clock = [phase]
        self.adc_calls, self.delays, self.leds, self.beeps, self.posted = 0, 0, [], [], []

        def select(uc):
            sel[s.arg(1)] = s.arg(0)
            return False

        def adc(uc):
            v = reading(sel[0], sel[1])
            floating = v is None
            v = 4095 if floating else v
            if hum and (floating or hum_connected):
                v += hum * math.sin(2 * math.pi * hz * clock[0] / 1000)
            s.ret(int(min(4095, max(0, round(v)))))
            self.adc_calls += 1
            return True

        def delay(uc):
            clock[0] += s.arg(0)
            self.delays += 1
            if events and self.delays in events:
                events[self.delays](s)
            s.ret(0)
            return True

        s.at[SELECT], s.at[ADC], s.at[DELAY] = select, adc, delay
        s.at[RGB_LED] = lambda uc: (self.leds.append(s.arg(0)), s.ret(0), True)[2]
        s.at[BEEP] = lambda uc: (self.beeps.append(s.arg(0)), s.ret(0), True)[2]
        s.at[GUI_MSG_SEND] = lambda uc: (self.posted.append(s.arg(0)), False)[1]
        sc_cable_result(s, mode=mode)
        self.status = list(s.uc.mem_read(CC.STATUS, 9))
        self.map = struct.unpack('<9H', s.uc.mem_read(CC.MAP, 18))
        self.values = [t for k, t, x, y, fg, ex in s.log if k == 'ascii' and ex['size'] == 12]
        self.value_colours = [fg for k, t, x, y, fg, ex in s.log if k == 'ascii' and ex['size'] == 12]
        self.texts = [(t, x, y) for k, t, x, y, fg, ex in s.log if k == 'ascii' and ex['size'] == 16]
        self.line = [t for t, x, y in self.texts if y == 271]         # the text line under the wires
        self.retry = s.uc.mem_read(CC.RETRY, 1)[0]

    @property
    def led(self):
        return self.leds[-1] if self.leds else None

    def row_pixels(self, row):
        y = 68 + 24 * row
        return {self.s.fb[y][x] for x in range(30, 100)}


class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.img, cls.data, cls.parent = images()

    def test_parent_is_the_pn227a_release_and_only_the_listed_sites_move(self):
        self.assertEqual(hashlib.sha256(self.parent).hexdigest(), CC.PARENT_SHA256)
        self.assertEqual(len(self.data), len(self.parent), 'fits the cave: the file does not grow')
        sites = {CC.OK_POST: 4, CC.GUI_CALL: 4, CC.FAR_VALUES: 4, CC.SWITCH_VALUES: 4, CC.CLASSIFY: 4,
                 CC.CLASSIFY_SKIP: 2, CC.POST_PASS: 4, **{a: 4 for a in CC.RETRY_POSTS + CC.FRAME_CALLS},
                 0x08011660: 8, 0x08012E6C: 8}
        allowed = set(range(0x24, 0x2C))
        for a, n in sites.items():
            o = a - 0x0800A000 + 0x1000
            allowed |= set(range(o, o + n))
        end = CC.PARENT_END - 0x0800A000 + 0x1000
        changed = {i for i in range(len(self.parent)) if self.parent[i] != self.data[i] and i < end}
        self.assertEqual(changed - allowed, set())
        self.assertEqual(self.img.read(0x08011660, 7), b'PN2.28\0')

    def test_builds_the_same_bytes_twice(self):
        with contextlib.redirect_stdout(io.StringIO()):
            again = bytes(CC.build_candidate().data)
        self.assertEqual(again, self.data)


class SwitchMode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.img, cls.data, cls.parent = images()

    def test_good_cables_pass_straight_crossover_and_with_bob_smith_paths(self):
        for name, far in (('straight', switch_end()), ('crossover', switch_end(CROSSOVER)),
                          ('gigabit centre taps', switch_end(cross=121)),
                          ('centre taps, weak pull-up', switch_end(cross=73)),
                          ('10/100 with 4-5-7-8 tied', switch_end(tied4578=True))):
            with self.subTest(name):
                r = Rig(self.data, SWITCH, far, hum=300)
                self.assertEqual(r.status, [OK] * 8 + [UNTESTED])
                self.assertEqual(r.led, 2, 'green')
                self.assertEqual(r.beeps, [])
                self.assertEqual(r.texts[-1:], [('Test Retry', 80, 294)])
                self.assertEqual(r.values[:8], ['2   60', '1   60', '6   60', '5   60',
                                                '4   60', '3   60', '8   60', '7   60'][:8]
                                 if name == 'straight' else r.values[:8])

    def test_B1_a_wire_in_the_wrong_pair_fails(self):
        swapped = dict(STRAIGHT)
        swapped[1], swapped[2] = 2, 1                  # near 2 -> far 3, near 3 -> far 2 (split into the wrong pairs)
        old = Rig(self.parent, SWITCH, switch_end(swapped))
        self.assertEqual(old.status, [OK] * 8 + [OPEN], 'PN2.27A: eight green wires')
        self.assertEqual(old.led, 2)
        r = Rig(self.data, SWITCH, switch_end(swapped))
        self.assertEqual([i for i in range(8) if r.status[i] == CROSSED], [0, 1, 2, 5])
        self.assertEqual([r.status[i] for i in (3, 4, 6, 7)], [OK] * 4)
        self.assertEqual(r.led, 1, 'red')
        self.assertEqual(r.beeps, [2])
        self.assertIn(0xF800, r.row_pixels(0), 'the miswired wire is redrawn red, full length')

    def test_B1_a_short_between_two_pairs_fails_in_a_switch(self):
        old = Rig(self.parent, SWITCH, switch_end(shorts=[{0, 2}]))
        self.assertEqual(old.status[:8], [OK] * 8)
        r = Rig(self.data, SWITCH, switch_end(shorts=[{0, 2}]))
        self.assertEqual([r.status[i] for i in (0, 2)], [SHORT, SHORT])
        self.assertEqual(r.led, 1)
        self.assertIn(0xFFE0, r.row_pixels(0), 'yellow')

    def test_B4_a_short_on_an_unplugged_cable_is_not_drawn_green(self):
        far = switch_end(shorts=[{0, 2}], plugged=False)
        old = Rig(self.parent, SWITCH, far, hum=300)
        self.assertEqual(old.status[:3], [OK, OPEN, OK], 'PN2.27A: wires 1 and 3 green, the only good ones')
        r = Rig(self.data, SWITCH, far, hum=300)
        self.assertEqual(r.status, [SHORT, OPEN, SHORT, OPEN, OPEN, OPEN, OPEN, OPEN, UNTESTED])
        self.assertEqual(r.led, 1)
        self.assertNotIn(0x07E0, r.row_pixels(0), 'not green')
        far = switch_end(shorts=[{0, 1}], plugged=False)          # one joined pair alone is not a switch either
        r = Rig(self.data, SWITCH, far)
        self.assertEqual(r.status[:2], [SHORT, SHORT])

    def test_B3_shield_open_is_not_a_broken_wire_and_a_shield_short_fails(self):
        r = Rig(self.data, SWITCH, switch_end())
        self.assertEqual(r.status[8], UNTESTED)
        y = 68 + 24 * 8
        g = {r.s.fb[y][x] for x in range(25, 208)}
        self.assertNotIn(0xF800, g, 'no red G')
        self.assertIn(0x8410, g, 'grey: not tested against a switch')
        self.assertFalse(any(r.s.fb[yy][xx] == 0xF800 for yy in range(y - 4, y + 5) for xx in range(112, 121)), 'no X')
        old = Rig(self.parent, SWITCH, switch_end(shorts=[{2, 8}]))
        self.assertEqual((old.status[8], old.led), (OK, 2), 'PN2.27A: a shield short turned G green and passed')
        r = Rig(self.data, SWITCH, switch_end(shorts=[{2, 8}]))
        self.assertEqual(r.status[8], SHORT)
        self.assertEqual(r.led, 1)

    def test_broken_wire_and_nothing_connected_keep_pn221_results(self):
        broken = dict(STRAIGHT)
        broken[2] = None
        r = Rig(self.data, SWITCH, switch_end(broken))
        self.assertEqual(r.status, [OK, OK, OPEN, OK, OK, OPEN, OK, OK, UNTESTED])
        self.assertEqual(r.led, 1)
        for seed_phase in (0.0, 3.0, 7.0):
            r = Rig(self.data, SWITCH, switch_end(plugged=False), hum=300, phase=seed_phase)
            self.assertEqual(r.status[:8], [OPEN] * 8)
            self.assertEqual(r.line, ['Not connected'])


class RxUnitMode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.img, cls.data, cls.parent = images()

    def test_good_cables_still_map(self):
        utp = {i: i for i in range(8)}
        cross_utp = {k: v for k, v in CROSSOVER.items() if k != 8}
        cases = (('straight STP', STRAIGHT, (0.95, 0.97, 1.0, 1.01), [OK] * 9),
                 ('crossover STP', CROSSOVER, (0.95, 0.97, 1.0, 1.01), [CROSSED, CROSSED, CROSSED, OK, OK, CROSSED, OK, OK, OK]),
                 ('straight UTP', utp, (0.95, 0.97, 1.0, 1.03, 1.05), [OK] * 8 + [OPEN]),
                 ('crossover UTP', cross_utp, (0.95, 0.97, 1.0, 1.03, 1.05),
                  [CROSSED, CROSSED, CROSSED, OK, OK, CROSSED, OK, OK, OPEN]))
        for name, wiring, gains, want in cases:
            for gain in gains:
                for phase in (0.0, 5.0):
                    with self.subTest(name, gain=gain, phase=phase):
                        r = Rig(self.data, RX, rx_end(wiring, gain), hum=40, hum_connected=True, phase=phase)
                        self.assertEqual(r.status, want)
                        self.assertEqual(r.led, 1 if CROSSED in want else 2)
        # the shield's open test is PN2.19's (audit B8, unchanged): above +1 % its hum crosses 4000 in both builds
        for data in (self.parent, self.data):
            r = Rig(data, RX, rx_end(STRAIGHT, 1.03), hum=40, hum_connected=True)
            self.assertEqual(r.status[8], OPEN)
        r = Rig(self.data, RX, rx_end(CROSSOVER))
        self.assertEqual([r.map[i] for i in (0, 1, 2, 5)], [2, 5, 0, 1])

    def test_B2_a_neighbour_crossing_is_not_passed_as_straight(self):
        swapped = dict(STRAIGHT)
        swapped[5], swapped[6] = 6, 5                  # 6 <-> 7
        old = Rig(self.parent, RX, rx_end(swapped, gain=1.0125))
        self.assertEqual(old.status[6], OK, 'PN2.27A: pin 7 reads 3223, inside its own window: straight')
        r = Rig(self.data, RX, rx_end(swapped, gain=1.0125))
        self.assertEqual(r.status[5:7], [CROSSED, CROSSED])
        self.assertEqual((r.map[5], r.map[6]), (6, 5))
        swapped = dict(STRAIGHT)
        swapped[7], swapped[8] = 8, 7                  # 8 <-> G on a shielded cable
        r = Rig(self.data, RX, rx_end(swapped, gain=1.01))
        self.assertEqual(r.status[7:], [CROSSED, CROSSED])

    def test_B5_a_floating_slot_is_not_averaged_in(self):
        wrong = 0
        swapped = {0: 1, 1: 0, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6, 7: 7}   # UTP (G floating), 1 <-> 2 reversed
        for phase in range(0, 20, 2):
            old = Rig(self.parent, RX, rx_end(swapped), hum=200, phase=float(phase))
            wrong += old.status[:2] != [CROSSED, CROSSED] or old.map[:2] != (1, 0)
            r = Rig(self.data, RX, rx_end(swapped), hum=200, phase=float(phase))
            self.assertEqual(r.status, [CROSSED, CROSSED, OK, OK, OK, OK, OK, OK, OPEN], f'phase {phase}')
            self.assertEqual(r.map[:2], (1, 0))
        self.assertGreater(wrong, 0, 'PN2.27A misreads some phases')

    def test_B6_two_wires_on_one_remote_pin_are_unknown(self):
        both = dict(STRAIGHT)
        both[0] = 1                                    # pins 1 and 2 both reach remote pin 2
        old = Rig(self.parent, RX, rx_end(both))
        self.assertEqual(old.status[:2], [CROSSED, OK], 'PN2.27A: drawn as a map an RX unit cannot give')
        r = Rig(self.data, RX, rx_end(both))
        self.assertEqual(r.status[:2], [UNKNOWN, UNKNOWN])
        self.assertIn(('Result error!!', 64, 271), r.texts)
        self.assertEqual(r.led, 1)

    def test_B6_leakage_of_an_unplugged_cable_is_not_a_wire_map(self):
        leak = lambda d, s: 3800
        old = Rig(self.parent, RX, leak)
        self.assertIn(CROSSED, old.status, 'PN2.27A: wires "crossed to G"')
        r = Rig(self.data, RX, leak)
        self.assertEqual(r.status, [UNKNOWN] * 9)
        self.assertEqual(r.led, 1)

    def test_shorts_and_opens_keep_their_rules(self):
        r = Rig(self.data, RX, rx_end(shorts=[{0, 1}]))
        self.assertEqual(r.status[:2], [SHORT, SHORT])
        self.assertEqual(r.status[2:], [OK] * 7)
        broken = dict(STRAIGHT)
        broken[4] = None
        r = Rig(self.data, RX, rx_end(broken), hum=200, hum_connected=False)
        self.assertEqual(r.status, [OK, OK, OK, OK, OPEN, OK, OK, OK, OK])
        r = Rig(self.data, RX, lambda d, s: None, hum=300)
        self.assertEqual(r.status, [OPEN] * 9)
        self.assertEqual(r.line, ['Not connected'])


class Keys(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.img, cls.data, cls.parent = images()

    def count_ok(self, data, busy):
        s = Scene(image=data, lang=1)
        posted = []
        s.at[GUI_MSG_SEND] = lambda uc: (posted.append(s.arg(0)), s.ret(0), True)[2]
        s.uc.mem_write(CC.BUSY, bytes([busy]))
        s.uc.mem_write(0x2000E100, bytes([2]))
        s.call(0x0800C3FC, 0x2000E100)                 # APP_COUNT_task handler, message 2 = OK
        return posted

    def test_B7_ok_while_a_test_runs_is_dropped(self):
        self.assertEqual(self.count_ok(self.parent, 1), [0x11], 'PN2.27A queues another full test')
        self.assertEqual(self.count_ok(self.data, 1), [])
        self.assertEqual(self.count_ok(self.data, 0), [0x11])

    def test_NEW1_a_queued_test_does_not_run_on_another_screen(self):
        for data, runs in ((self.parent, True), (self.data, False)):
            s = Scene(image=data, lang=1)
            calls = []
            s.at[ADC] = lambda uc: (calls.append(1), s.ret(4095), True)[2]
            s.at[DELAY] = lambda uc: (s.ret(0), True)[1]
            s.uc.mem_write(CC.MODE, bytes([0x10]))
            s.uc.mem_write(0x2000013C, bytes([2]))     # the user is back on Home
            s.dispatch(0x11)
            self.assertEqual(bool(calls), runs)

    def test_B10_back_during_a_test_leaves_no_retry_button_and_no_retry_label(self):
        def back(s):
            s.uc.mem_write(CC.MODE, bytes([0]))       # cable_test_enter: selector, label "Test Start"
            s.uc.mem_write(CC.RETRY, bytes([0]))
        old = Rig(self.parent, SWITCH, switch_end(), events={400: back})
        self.assertEqual((old.retry, old.posted.count(0x12)), (1, 1), 'PN2.27A: stray button, stale label')
        r = Rig(self.data, SWITCH, switch_end(), events={400: back})
        self.assertEqual((r.retry, r.posted.count(0x12)), (0, 0))

    def test_B13_each_routine_draws_its_own_format(self):
        flip = {400: lambda s: s.uc.mem_write(CC.MODE, bytes([0x11]))}
        old = Rig(self.parent, SWITCH, switch_end(), events=flip)
        self.assertEqual(old.values[0], '  60', 'PN2.27A: switch readings in the RX-unit format')
        r = Rig(self.data, SWITCH, switch_end(), events=flip)
        self.assertEqual(r.values[0], '2   60')

    def test_I5_the_button_says_testing_during_the_test(self):
        r = Rig(self.data, SWITCH, switch_end())
        labels = [t for t, x, y in r.texts if y == 294]
        self.assertEqual(labels[-2:], ['Testing...', 'Test Retry'])
        self.assertIn(('Testing...', 80, 294), r.texts)
        th = Rig(self.data, SWITCH, switch_end(), lang=2)
        cjk = [(x, y) for k, t, x, y, fg, ex in th.s.log if k == 'cjk' and y == 294]
        self.assertTrue(cjk, 'Thai "testing" on the button')
        self.assertEqual(th.status, [OK] * 8 + [UNTESTED])


if __name__ == '__main__':
    unittest.main()
