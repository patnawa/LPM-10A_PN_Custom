"""Real ARM QC draw/frame/error helpers, using the existing framebuffer seam."""
import contextlib
import io
import struct
import unittest

from lpm10a.image import Image, PatchError
from profiles import PROFILES, apply_profile
from thai.engine import Scene
import qc_ui


class QcUi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with contextlib.redirect_stdout(io.StringIO()):
            cls.img = Image('../LPM-10A-TX_V2.0.7_260610.bin')
            # This fixture independently installs the original Q session UI.
            apply_profile(cls.img, PROFILES['pn2.23'])
        cls.state = cls.img.alloc_ram(qc_ui.STATE_SIZE)
        reset = cls.img.emit_code('''
            push {r4, lr}
            ldr r0, =STATE
            movs r1, #56
            bl memclr
            ldr r0, =STATE
            movs r1, #1
            strb r1, [r0]
            pop {r4, pc}
        ''', extra_syms={'STATE': cls.state}, why='QC UI fixture: session reset callback')
        cls.api = qc_ui.install(cls.img, cls.state, reset)
        cls.data = bytes(cls.img.finalize().data)

    def scene(self, lang=1, mode=1):
        s = Scene(image=self.data, lang=lang)
        s.set_state(8)
        data = bytearray(qc_ui.STATE_SIZE)
        data[0] = mode
        struct.pack_into('<H', data, qc_ui.SCANS, 123)
        struct.pack_into('<8H', data, qc_ui.FAULTS, 0, 1, 9, 999, 3, 0, 2, 0)
        data[qc_ui.NOW:qc_ui.NOW+8] = bytes((1, 1, 2, 3, 0, 1, 2, 3))
        s.uc.mem_write(self.state, bytes(data))
        s.log.clear()
        return s

    def text(self, s):
        return [line[1] for line in s.log if line[0] == 'ascii']

    def test_both_languages_render_status_history_and_controls_within_body(self):
        for lang in (1, 2):
            with self.subTest(lang=lang):
                s = self.scene(lang)
                original_header = [list(row) for row in s.fb[:52]]
                colours = bytes(s.uc.mem_read(qc_ui.COLOURS, 4))
                s.call(self.api['draw'])
                text = self.text(s)
                for wanted in ('Running (20 s)', 'Scans 123', 'INT', 'OPEN', 'CHECK', '999',
                               'OK: Start/Stop', 'Right: New test', 'Hold Right: Init'):
                    self.assertIn(wanted, text)
                self.assertEqual([list(row) for row in s.fb[:52]], original_header)
                self.assertEqual(bytes(s.uc.mem_read(qc_ui.COLOURS, 4)), colours)
                self.assertEqual(s.msgs, [])
                for y in range(109, 250, 20):
                    for x0, x1 in ((18, 42), (162, 210)):
                        self.assertTrue(any(s.fb[yy][xx] == 0xFFFF
                            for yy in range(y, y+16) for xx in range(x0, x1)),
                            f'pin/count pixels missing at ({x0}, {y}) in language {lang}')
                for kind, value, x, y, colour, extra in s.log:
                    if kind == 'ascii':
                        self.assertGreaterEqual(x, 8)
                        self.assertGreaterEqual(y, 52)
                        self.assertLessEqual(x+extra['w'], 230)
                        self.assertLessEqual(y+extra['size'], 315)

    def test_all_session_titles_and_frame_callback(self):
        for mode, title in ((0, 'Needs calibration'), (1, 'Running (20 s)'),
                            (2, 'Done (20 s)'), (3, 'Held'), (4, 'Calibration failed')):
            s = self.scene(mode=mode)
            s.call(self.api['draw'])
            self.assertIn(title, self.text(s))
        s = self.scene(mode=3)
        s.call(self.api['frame'])
        self.assertEqual(bytes(s.uc.mem_read(self.state, qc_ui.STATE_SIZE)),
                         bytes((1,))+bytes(qc_ui.STATE_SIZE-1))
        self.assertIn('Running (20 s)', self.text(s))

    def test_failed_calibration_retains_history_and_renders_explicit_result(self):
        s = self.scene()
        before = bytes(s.uc.mem_read(self.state, qc_ui.STATE_SIZE))
        s.call(self.api['error'])
        after = bytes(s.uc.mem_read(self.state, qc_ui.STATE_SIZE))
        self.assertEqual(after, bytes((4,))+before[1:])
        self.assertEqual(s.uc.mem_read(qc_ui.QC_PHASE, 1)[0], 3)
        self.assertIn('Calibration failed', self.text(s))
        self.assertIn('Old values kept', self.text(s))
        self.assertIn('999', self.text(s))

    def test_redraw_clears_old_status_and_digits(self):
        for lang in (1, 2):
            old = self.scene(lang, mode=4)
            old.call(self.api['draw'])
            final = bytearray(qc_ui.STATE_SIZE)
            final[0] = 3
            final[qc_ui.NOW:qc_ui.NOW+8] = bytes((1,))*8
            old.uc.mem_write(self.state, bytes(final))
            old.call(self.api['draw'])
            fresh = self.scene(lang)
            fresh.uc.mem_write(self.state, bytes(final))
            fresh.call(self.api['draw'])
            self.assertEqual(old.fb, fresh.fb)

    def test_late_qc_messages_do_not_draw_or_reset_other_screens(self):
        s = self.scene()
        s.set_state(2)
        before = bytes(s.uc.mem_read(self.state, qc_ui.STATE_SIZE))
        framebuffer = [list(row) for row in s.fb]
        s.log.clear()
        for entry in self.api.values():
            s.call(entry)
        self.assertEqual(bytes(s.uc.mem_read(self.state, qc_ui.STATE_SIZE)), before)
        self.assertEqual(s.fb, framebuffer)
        self.assertEqual(s.log, [])

    def test_late_frame_or_error_cannot_reset_a_calibration_handoff(self):
        s = self.scene()
        s.w8(qc_ui.QC_PHASE, 4)
        s.w8(self.state+3, 1)  # foreground sample still owns the mux
        before = bytes(s.uc.mem_read(self.state, qc_ui.STATE_SIZE))
        framebuffer = [list(row) for row in s.fb]
        for kind in ('frame', 'error', 'draw'):
            s.call(self.api[kind])
        self.assertEqual(bytes(s.uc.mem_read(self.state, qc_ui.STATE_SIZE)), before)
        self.assertEqual(s.uc.mem_read(qc_ui.QC_PHASE, 1)[0], 4)
        self.assertEqual(s.fb, framebuffer)
        self.assertEqual(s.log, [])

    def test_led_requires_complete_current_good_and_no_failure_history(self):
        s = self.scene()
        leds = []
        def record_led(uc):
            leds.append(s.arg(0))
            return False
        s.at[0x08010F94] = record_led
        good = bytearray(qc_ui.STATE_SIZE)
        good[0] = 1
        good[qc_ui.SEEN] = 255
        good[qc_ui.NOW:qc_ui.NOW+8] = bytes((1,))*8
        cases = [('all good', good, 2)]
        for mode in (0, 4):
            state = good[:]
            state[0] = mode
            cases.append((f'mode {mode}', state, 1))
        for offset, value in ((qc_ui.SEEN, 127), (qc_ui.NOW+7, 0),
                              (qc_ui.NOW+7, 2), (qc_ui.NOW+7, 3),
                              (qc_ui.FAULTS+14, 1)):
            state = good[:]
            state[offset] = value
            cases.append((f'offset {offset} value {value}', state, 1))
        for name, state, expected in cases:
            with self.subTest(name=name):
                s.uc.mem_write(self.state, bytes(state))
                s.call(self.api['draw'])
                self.assertEqual(leds[-1], expected)
        self.assertEqual(len(leds), len(cases))
        s.w8(qc_ui.QC_PHASE, 4)
        s.call(self.api['draw'])
        self.assertEqual(len(leds), len(cases), 'calibration owns its LED')

    def test_calibration_progress_redraws_retained_table_after_stock_frame_clear(self):
        for lang in (1, 2):
            with self.subTest(lang=lang):
                s = self.scene(lang)
                s.call(self.api['draw'])
                table = [row[:] for row in s.fb[92:270]]
                before = bytes(s.uc.mem_read(self.state, qc_ui.STATE_SIZE))
                s.w8(qc_ui.QC_PHASE, 4)
                s.dispatch(0x36)  # The stock handler clears the complete body.
                header = [row[:] for row in s.fb[:52]]
                self.assertNotEqual(s.fb[92:270], table)
                leds = []
                def record_led(uc):
                    leds.append(s.arg(0))
                    return False
                s.at[0x08010F94] = record_led
                s.log.clear()
                s.call(self.api['progress'])
                self.assertEqual(bytes(s.uc.mem_read(self.state, qc_ui.STATE_SIZE)), before)
                self.assertEqual(s.uc.mem_read(qc_ui.QC_PHASE, 1)[0], 4)
                self.assertEqual(s.fb[:52], header)
                self.assertEqual(s.fb[92:270], table)
                self.assertEqual(leds, [])
                self.assertIn('Calibrating...', self.text(s))
                self.assertIn('Remove cable first', self.text(s))
                s.w8(qc_ui.QC_PHASE, 3)
                s.log.clear()
                s.call(self.api['progress'])
                self.assertEqual(s.log, [], 'late progress cannot replace final outcome')

    def test_state_allocation_guard(self):
        for state in (0x2000E000, 0x2000F001, 0x20010000):
            with self.assertRaises(PatchError):
                qc_ui.install(self.img, state, 0x0800A000)


class QcCandidateUi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import qc_continuity
        with contextlib.redirect_stdout(io.StringIO()):
            cls.img = qc_continuity.build_candidate()
        cls.data = bytes(cls.img.data)

    def seed_history(self, h, mode=1):
        s, state = h.s, self.img.qc['state']
        s.w8(state, mode)
        s.w16(state+qc_ui.SCANS, 17)
        s.w8(state+qc_ui.SEEN, 255)
        s.uc.mem_write(state+qc_ui.NOW, bytes((1, 1, 2, 3, 1, 1, 1, 1)))
        s.w16(state+qc_ui.FAULTS, 3, 0, 9, 2, 0, 0, 0, 0)
        s.call(self.img.qc['ui']['draw'])

    def test_live_header_refresh_preserves_current_table_without_resetting(self):
        from test_qc_continuity import Harness
        for lang in (1, 2):
            with self.subTest(lang=lang):
                h = Harness(self.data, lang=lang)
                h.enter()
                self.seed_history(h)
                s, state = h.s, self.img.qc['state']
                self.assertEqual(h.read(qc_ui.QC_PHASE), 2)
                before = bytes(s.uc.mem_read(state, 64))
                framebuffer = [row[:] for row in s.fb]
                s.log.clear()
                s.dispatch(0x36)
                self.assertEqual(bytes(s.uc.mem_read(state, 64)), before)
                self.assertEqual(h.read(qc_ui.QC_PHASE), 2)
                self.assertTrue(s.fb == framebuffer, 'header refresh erased the current QC table')
                text = [line[1] for line in s.log]
                self.assertIn('Running (20 s)', text)
                self.assertIn('Scans 17', text)
                self.assertIn('INT', text)

    def test_previous_session_notifications_cannot_change_reentered_qc(self):
        from test_qc_continuity import Harness
        for lang in (1, 2):
            for mid in (0x36, 0x0C, 0x0E):
                with self.subTest(lang=lang, message=hex(mid)):
                    h = Harness(self.data, lang=lang)
                    h.enter()
                    state = self.img.qc['state']
                    old_generation = h.read(state+56, 4)
                    delayed = (mid, struct.pack('<I', old_generation))
                    h.s.set_state(2)
                    h.enter()  # Actual entry invalidates the previous generation.
                    self.assertNotEqual(h.read(state+56, 4), old_generation)
                    self.seed_history(h, mode=3)
                    h.s.w8(qc_ui.QC_PHASE, 3)
                    before = bytes(h.s.uc.mem_read(state, 64))
                    legacy = bytes(h.s.uc.mem_read(0x2000021C, 34))
                    framebuffer = [row[:] for row in h.s.fb]
                    h.s.log.clear()
                    h.s.post(*delayed)
                    h.s.drain()
                    self.assertEqual(bytes(h.s.uc.mem_read(state, 64)), before)
                    self.assertEqual(bytes(h.s.uc.mem_read(0x2000021C, 34)), legacy)
                    self.assertTrue(h.s.fb == framebuffer, 'stale event changed the new QC screen')
                    self.assertEqual(h.s.log, [])

    def test_actual_entry_and_calibration_progress_route_in_both_languages(self):
        from test_qc_continuity import Harness
        for lang in (1, 2):
            with self.subTest(lang=lang):
                h = Harness(self.data, lang=lang)
                h.enter()
                s = h.s
                self.assertIn('Running (20 s)', [line[1] for line in s.log])
                state = self.img.qc['state']
                # Use a completed sample sweep with known history, then deliver
                # the exact progress event sent by the calibration CNT task.
                s.w8(state+qc_ui.SEEN, 255)
                s.uc.mem_write(state+qc_ui.NOW, bytes((1,))*8)
                s.w16(state+qc_ui.FAULTS, 3)
                before = bytes(s.uc.mem_read(state, 64))
                s.w8(qc_ui.QC_PHASE, 4)
                s.log.clear()
                s.dispatch(0x36)
                text = [line[1] for line in s.log]
                self.assertIn('Calibrating...', text)
                self.assertIn('Remove cable first', text)
                self.assertIn('INT', text)
                self.assertEqual(bytes(s.uc.mem_read(state, 64)), before)
                self.assertEqual(s.uc.mem_read(qc_ui.QC_PHASE, 1)[0], 4)


if __name__ == '__main__':
    unittest.main()
