"""Cable keys, COUNT queue and GUI dispatch on real firmware instructions.

Only queues, RTOS delay, LCD transport and the explicitly modeled far end are
external fixtures. The PN2.33 negative control reproduces both delayed-OK
symptoms. PN2.34 must preserve Switch/RX decisions while cancelling stale work.
"""
import contextlib
import hashlib
import io
import struct
import unittest

from unicorn.arm_const import (UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_SP, UC_ARM_REG_R0,
                               UC_ARM_REG_PRIMASK, UC_ARM_REG_R4, UC_ARM_REG_R5,
                               UC_ARM_REG_R6, UC_ARM_REG_R7)
from thai.engine import Scene, MAGIC, GUI_DISPATCH, GUI_LOOP_END, GUI_MSG_SEND
from test_cable_check import ADC, DELAY, SELECT, SWITCH, RX, switch_end, rx_end, STRAIGHT, CROSSOVER
import cable_check as CC

COUNT_SEND, COUNT_HANDLER, ENTRY, ACTION = 0x0800C3B0, 0x0800C3FC, 0x0800C300, 0x080149FC
COUNT_HANDLE, GUI_HANDLE = 0x20003000, 0x20001000


class SessionHarness:
    def __init__(self, data, *, mode=RX, armed=True, lang=1, reading=None):
        self.s = s = Scene(image=data, lang=lang)
        self.gui, self.count = [], []
        self.adc_reads, self.routines, self.leds, self.beeps = [], [], [], []
        self.reject_gui = False
        self.on_delay = None
        self.on_queue = None
        selected = {0: 0, 1: 0}
        self.reading = reading or (lambda d, v: None)
        s.uc.mem_write(0x2000000C, struct.pack('<I', COUNT_HANDLE))

        def queue(uc):
            assert uc.reg_read(UC_ARM_REG_PRIMASK) == 0, 'queue call inside interrupt-masked section'
            if s.arg(0) == GUI_HANDLE:
                if self.on_queue:
                    self.on_queue(self)
                if self.reject_gui:
                    s.ret(0)
                    return True
                self.gui.append(('raw', bytes(uc.mem_read(s.arg(1), 8))))
            elif s.arg(0) == COUNT_HANDLE:
                self.count.append(bytes(uc.mem_read(s.arg(1), 8)))
            s.ret(1)
            return True

        def gui(uc):
            data = bytes(uc.mem_read(s.arg(1), s.arg(2))) if s.arg(1) and s.arg(2) else b''
            self.gui.append(('normal', (s.arg(0), data)))
            s.ret(1)
            return True

        def select(uc):
            selected[s.arg(1)] = s.arg(0)
            return False

        def adc(uc):
            value = self.reading(selected[0], selected[1])
            self.adc_reads.append((selected[0], selected[1]))
            s.ret(4095 if value is None else value)
            return True

        def delay(uc):
            if self.on_delay:
                self.on_delay(self)
            s.ret(0)
            return True

        s.at[0x0801CAA0], s.at[GUI_MSG_SEND] = queue, gui
        s.at[SELECT], s.at[ADC], s.at[DELAY] = select, adc, delay
        s.at[0x0800CB68] = lambda uc: (self.routines.append('Switch'), False)[1]
        s.at[0x0800C4E0] = lambda uc: (self.routines.append('RX unit'), False)[1]
        s.at[CC.RGB_LED] = lambda uc: (self.leds.append(s.arg(0)), s.ret(0), True)[2]
        s.at[CC.BEEP] = lambda uc: (self.beeps.append(s.arg(0)), s.ret(0), True)[2]
        s.call(ENTRY)
        self.flush()
        if mode == RX:
            self.send(1)
            self.flush()
        if armed:
            self.send(2)
            self.flush()
        assert self.mode == mode | (0x10 if armed else 0)
        self.routines.clear()
        self.adc_reads.clear()

    @property
    def mode(self):
        return self.s.uc.mem_read(CC.MODE, 1)[0]

    def send(self, command):
        # Real function called by the event-task action sites for Left/OK.
        self.s.call(COUNT_SEND, command, 0, 0)

    def press(self, key):
        self.s.w8(0x20003200, key, 3)
        self.s.call(ACTION, 0x20003200)

    def event_press(self, key):
        """Preempt a yielding GUI/COUNT task using the event task's own stack."""
        s, uc = self.s, self.s.uc
        context = uc.context_save()
        s.w8(0x20003240, key, 3)
        uc.reg_write(UC_ARM_REG_SP, 0x2000C000)
        uc.reg_write(UC_ARM_REG_LR, MAGIC | 1)
        uc.reg_write(UC_ARM_REG_R0, 0x20003240)
        try:
            uc.emu_start(ACTION | 1, MAGIC, count=2_000_000)
            assert uc.reg_read(UC_ARM_REG_PC) == MAGIC
            assert uc.reg_read(UC_ARM_REG_SP) == 0x2000C000
        finally:
            uc.context_restore(context)

    def pause_event(self, key, until):
        s, uc = self.s, self.s.uc
        context = uc.context_save()
        s.w8(0x20003240, key, 3)
        uc.reg_write(UC_ARM_REG_SP, 0x2000C000)
        uc.reg_write(UC_ARM_REG_LR, MAGIC | 1)
        uc.reg_write(UC_ARM_REG_R0, 0x20003240)
        try:
            uc.emu_start(ACTION | 1, until, count=2_000_000)
            assert uc.reg_read(UC_ARM_REG_PC) == until
            return uc.context_save()
        finally:
            uc.context_restore(context)

    def resume_event(self, suspended):
        uc = self.s.uc
        context = uc.context_save()
        try:
            uc.context_restore(suspended)
            uc.emu_start(uc.reg_read(UC_ARM_REG_PC) | 1, MAGIC, count=2_000_000)
            assert uc.reg_read(UC_ARM_REG_PC) == MAGIC
            assert uc.reg_read(UC_ARM_REG_SP) == 0x2000C000
        finally:
            uc.context_restore(context)

    def drain_count(self):
        while self.count:
            self.s.uc.mem_write(0x20003210, self.count.pop(0))
            self.s.call(COUNT_HANDLER, 0x20003210)

    def deliver(self, message):
        kind, packet = message
        if kind == 'normal':
            self.s.dispatch(*packet)
            return
        uc = self.s.uc
        sp = 0x2000E000 - 0x18
        uc.mem_write(sp + 8, packet)
        uc.reg_write(UC_ARM_REG_SP, sp)
        uc.reg_write(UC_ARM_REG_LR, MAGIC | 1)
        uc.emu_start(GUI_DISPATCH | 1, GUI_LOOP_END, count=50_000_000)
        assert uc.reg_read(UC_ARM_REG_PC) == GUI_LOOP_END
        assert uc.reg_read(UC_ARM_REG_SP) == sp

    def flush(self):
        self.drain_count()
        while self.gui:
            self.deliver(self.gui.pop(0))
            self.drain_count()


class CableSession(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import cable_safe
        import cable_session
        with contextlib.redirect_stdout(io.StringIO()):
            cls.img = cable_safe.build_candidate()
            cls.parent = bytes(cls.img.data)
            cable_session.apply(cls.img).finalize()
        cls.data = bytes(cls.img.data)

    def test_one_queued_ok_cannot_undo_back_to_selector(self):
        h = SessionHarness(self.data)
        h.send(2)
        h.drain_count()
        h.press(0)
        self.assertEqual(h.mode, 0)
        h.flush()
        self.assertEqual(h.mode, 0, 'delayed OK undid Back and armed Switch mode')
        self.assertEqual(h.adc_reads, [])

    def test_two_queued_oks_cannot_measure_after_back(self):
        h = SessionHarness(self.data)
        h.send(2)
        h.send(2)
        h.drain_count()
        h.press(0)
        h.flush()
        self.assertEqual(len(h.adc_reads), 0, f'{len(h.adc_reads)} stale reads in {h.routines}')

    def test_pending_oks_coalesce_even_before_count_task_runs(self):
        h = SessionHarness(self.data)
        for _ in range(3):
            h.send(2)
        h.flush()
        self.assertEqual(h.routines, ['RX unit'])
        self.assertEqual(len(h.adc_reads), 792)

    def test_negative_control_pn233_reproduces_both_original_symptoms(self):
        import cable_session as CS
        self.assertEqual(hashlib.sha256(self.parent).hexdigest(), CS.PARENT_SHA256)
        for count in (1, 2):
            h = SessionHarness(self.parent)
            for _ in range(count):
                h.send(2)
            h.drain_count()
            h.press(0)
            h.flush()
            self.assertEqual(h.mode, 0x10)
            self.assertEqual(len(h.adc_reads), 792 * (count - 1))
            self.assertEqual(h.routines, [] if count == 1 else ['Switch'])

    def test_real_ok_keys_arm_measure_and_retry_in_both_modes_and_languages(self):
        for mode, name, far in ((SWITCH, 'Switch', switch_end()), (RX, 'RX unit', rx_end())):
            for lang in (1, 2):
                with self.subTest(mode=mode, lang=lang):
                    h = SessionHarness(self.data, mode=mode, armed=False, lang=lang, reading=far)
                    h.press(4)
                    h.flush()
                    self.assertEqual((h.mode, h.adc_reads), (mode | 0x10, []))
                    h.press(4)
                    h.flush()
                    h.press(4)
                    h.flush()
                    self.assertEqual(h.routines, [name, name])
                    self.assertEqual(len(h.adc_reads), 2 * 792)
                    self.assertEqual(h.s.uc.mem_read(CC.BUSY, 1), bytes(1))
                    self.assertEqual(h.s.uc.mem_read(CC.RETRY, 1), b'\x01')

    def test_mode_changes_invalidate_queued_selector_start_including_aba(self):
        for toggles in (1, 2):
            h = SessionHarness(self.data, mode=SWITCH, armed=False)
            h.send(2)
            for _ in range(toggles):
                h.send(1)
            h.flush()
            self.assertEqual(h.mode, toggles % 2)
            self.assertEqual(h.adc_reads, [])
            h.send(2)
            h.flush()
            self.assertEqual(h.mode, 0x10 | (toggles % 2))

    def test_pending_start_before_back_home_and_reentry_cannot_change_new_visit(self):
        h = SessionHarness(self.data)
        h.send(2)
        h.press(0)
        h.press(0)
        self.assertEqual(h.s.uc.mem_read(CC.SYSSTATE, 1), b'\x02')
        h.s.call(ENTRY)
        h.flush()
        self.assertEqual((h.mode, h.adc_reads), (0, []))
        h.send(2)
        h.flush()
        self.assertEqual(h.mode, 0x10)
        h.send(2)
        h.flush()
        self.assertEqual(h.routines, ['Switch'])

    def test_stale_layout_retry_and_header_packets_cannot_repaint_selector(self):
        for measure in (False, True):
            with self.subTest(measure=measure):
                h = SessionHarness(self.data, armed=measure)
                h.send(2)
                h.drain_count()
                h.deliver(h.gui.pop(0))
                stale = list(h.gui)
                self.assertTrue(stale)
                h.press(0)
                h.flush()
                before = [row[:] for row in h.s.fb]
                for message in stale:
                    h.deliver(message)
                h.flush()
                self.assertEqual(h.mode, 0)
                self.assertEqual(h.s.fb, before)

    def test_back_between_snapshot_and_queue_send_rejects_request(self):
        h = SessionHarness(self.data)
        def back(fixture):
            fixture.on_queue = None
            fixture.event_press(0)
        h.on_queue = back
        h.send(2)
        h.flush()
        self.assertEqual((h.mode, h.adc_reads), (0, []))

    def test_failed_enqueue_releases_pending_and_next_press_works(self):
        h = SessionHarness(self.data)
        h.reject_gui = True
        h.send(2)
        self.assertEqual(h.gui, [])
        self.assertEqual(h.s.uc.mem_read(self.img.cable_session['state'] + 4, 4), bytes(4))
        h.reject_gui = False
        h.send(2)
        h.flush()
        self.assertEqual(h.routines, ['RX unit'])

    def test_busy_test_ignores_back_mode_and_ok_without_queuing_work(self):
        h = SessionHarness(self.data)
        fired = []
        def keys(fixture):
            fixture.on_delay = None
            for key in (0, 1, 4):
                fixture.event_press(key)
            fired.append(fixture.mode)
        h.on_delay = keys
        h.send(2)
        h.flush()
        self.assertEqual(fired, [0x11])
        self.assertEqual(h.routines, ['RX unit'])
        self.assertEqual(h.mode, 0x11)

    def test_back_already_past_key_guard_cannot_reset_a_claimed_measurement(self):
        h = SessionHarness(self.data)
        h.send(2)
        back = h.pause_event(0, 0x08014AC0)
        observed = []
        def resume(fixture):
            fixture.on_delay = None
            fixture.resume_event(back)
            observed.append((fixture.mode, fixture.s.uc.mem_read(CC.BUSY, 1)[0]))
        h.on_delay = resume
        h.flush()
        self.assertEqual(observed, [(0x11, 1)])
        self.assertEqual((h.mode, h.routines), (0x11, ['RX unit']))

    def test_electrical_decisions_and_readings_match_pn233_in_both_modes(self):
        broken = dict(STRAIGHT)
        broken[4] = None
        crossed = dict(STRAIGHT)
        crossed[5], crossed[6] = 6, 5
        cases = [(SWITCH, switch_end()), (SWITCH, switch_end(shorts=[{0, 2}])),
                 (SWITCH, switch_end(plugged=False)), (RX, rx_end()),
                 (RX, rx_end(CROSSOVER)), (RX, rx_end(broken)), (RX, rx_end(crossed)),
                 (RX, rx_end(shorts=[{0, 1}]))]
        for index, (mode, far) in enumerate(cases):
            with self.subTest(case=index):
                outcomes = []
                for data in (self.parent, self.data):
                    h = SessionHarness(data, mode=mode, reading=far)
                    h.send(2)
                    h.flush()
                    values = [(t, fg) for k, t, x, y, fg, ex in h.s.log if k == 'ascii' and ex['size'] == 12]
                    outcomes.append((bytes(h.s.uc.mem_read(CC.STATUS, 9)), bytes(h.s.uc.mem_read(CC.MAP, 18)),
                                     h.leds[-1:], h.beeps, values))
                self.assertEqual(outcomes[0], outcomes[1])

    def test_inline_envelope_never_allocates_or_frees_epoch_as_pointer(self):
        h = SessionHarness(self.data)
        def no_heap(uc):
            self.fail('Cable key/GUI envelope used heap allocation')
        h.s.at[0x0801C388] = h.s.at[0x0801C6F8] = no_heap
        h.send(2)
        message = h.gui.pop(0)
        self.assertEqual(message[0], 'raw')
        self.assertEqual(message[1][0], 0x42)
        self.assertNotEqual(message[1][4:], bytes(4))
        h.deliver(message)
        sp = h.s.uc.reg_read(UC_ARM_REG_SP)
        self.assertEqual(bytes(h.s.uc.mem_read(sp + 12, 4)), bytes(4))
        h.s.uc.emu_start(GUI_LOOP_END | 1, 0x0800F72A, count=100)
        self.assertEqual(h.s.uc.reg_read(UC_ARM_REG_PC), 0x0800F72A)

    def test_request_preserves_callee_registers_stack_and_interrupt_state(self):
        h = SessionHarness(self.data)
        registers = (UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7)
        expected = [0xABCD0000 + n for n in range(len(registers))]
        for reg, value in zip(registers, expected):
            h.s.uc.reg_write(reg, value)
        h.send(2)
        self.assertEqual([h.s.uc.reg_read(reg) for reg in registers], expected)
        self.assertEqual(h.s.uc.reg_read(UC_ARM_REG_SP), 0x2000DFC0)
        self.assertEqual(h.s.uc.reg_read(UC_ARM_REG_PRIMASK), 0)

    def test_raw_untagged_cable_messages_are_discarded(self):
        h = SessionHarness(self.data)
        before = [row[:] for row in h.s.fb]
        for mid in range(0x0F, 0x13):
            h.s.dispatch(mid)
        self.assertEqual((h.mode, h.adc_reads), (0x11, []))
        self.assertEqual(h.s.fb, before)

    def test_build_changes_only_reviewed_hooks_versions_header_and_appended_code(self):
        info = self.img.cable_session
        allowed = set(range(0x24, 0x2C))
        sites = {**{site: len(data) for site, data in info['expected'].items()},
                 0x0801BBAC: 4, 0x08011660: 8, 0x08012E6C: 8}
        for site, size in sites.items():
            allowed.update(range(self.img.f(site), self.img.f(site) + size))
        changes = {index for index in range(self.img.f(info['parent_end']))
                   if self.parent[index] != self.data[index]}
        self.assertFalse(changes - allowed)
        self.assertEqual(self.img.ram_allocs[:-1], list(info['parent_ram']))
        self.assertEqual(self.img.ram_allocs[-1], (info['state'], 16))
        self.assertEqual(len(self.data), len(self.parent) + 4096)
        from lpm10a import symbols
        self.assertLess(self.img.cave_ptr, symbols.CONSTS['BOOTFLAG_PAGE'])
        self.assertEqual(self.data[:32], self.parent[:32], 'bootloader-facing name remains unchanged')

    def test_startup_clears_owned_ram_and_epoch_wrap_still_cancels_stale_work(self):
        h = SessionHarness(self.data)
        info = self.img.cable_session
        h.s.uc.mem_write(info['state'], bytes([0xA5]) * 16)
        h.s.call(info['init'])
        self.assertEqual(bytes(h.s.uc.mem_read(info['state'], 16)), bytes(16))
        h.s.call(ENTRY)
        h.flush()
        h.s.uc.mem_write(info['state'], struct.pack('<I', 0xFFFFFFFF))
        h.send(2)
        h.s.call(ENTRY)
        h.flush()
        self.assertEqual(h.mode, 0)
        self.assertEqual(h.adc_reads, [])
        self.assertEqual(bytes(h.s.uc.mem_read(info['state'], 4)), b'\x01\0\0\0')

    def test_nonparent_and_double_apply_rejected_without_changing_image(self):
        import cable_session
        from lpm10a.image import PatchError
        before = bytes(self.img.data)
        with self.assertRaises(PatchError):
            cable_session.apply(self.img)
        self.assertEqual(bytes(self.img.data), before)


if __name__ == '__main__':
    unittest.main()
