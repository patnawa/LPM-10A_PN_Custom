"""QC Init through the actual command handler, timer counter, sorter and save caller."""
import contextlib
import io
import struct
import unittest

from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm_const import (UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_R0,
                               UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6,
                               UC_ARM_REG_R7, UC_ARM_REG_SP)

from lpm10a.image import Image, PatchError
from profiles import PROFILES, apply_profile
import test_speed_partner as speed
from thai.engine import MAGIC, Scene

HANDLER, SELECT, DELAY, SAVE, HOME_MESSAGE = 0x0800BDD4, 0x08018060, 0x0801C75C, 0x080118F0, 0x08010EA8
BASE, FLAGS, SETTINGS, STATE, COMMAND = 0x2000021C, 0x2000023C, 0x20000C78, 0x2000013C, 0x20003200
STACK = 0x2000DFC0


def parent():
    with contextlib.redirect_stdout(io.StringIO()):
        img = Image(speed.STOCK)
        # Standalone Init is installed on its historical pre-QC parent.
        apply_profile(img, PROFILES['pn2.23'], extra=('speed-partner-validity',))
    return img


class QCCalibration(unittest.TestCase):
    patched = True

    @classmethod
    def setUpClass(cls):
        cls.parent = parent()

    def scene(self, rows=None, *, cancel_at=None, lang=1, state=8, command=0):
        import copy
        img = copy.deepcopy(self.parent)
        if self.patched:
            import qc_calibration
            with contextlib.redirect_stdout(io.StringIO()):
                qc_calibration.apply(img)
        s = Scene(image=bytes(img.finalize().data), lang=lang, state=state)
        s.w16(BASE, *range(700, 708))
        s.w8(FLAGS, 3, 1)
        s.uc.mem_write(SETTINGS + 0x90, bytes(range(16)))
        s.w8(COMMAND, command)
        s.reads, s.selected, s.saves, s.save_requests = [], [], [], []
        s.rows = rows or [[1000 + 20*pin + d for d in (3, 0, 2, 1, 4)] for pin in range(8)]
        selected = [8]
        counts = [0]*8

        def select(uc):
            selected[0] = s.arg(0)
            s.selected.append(selected[0])
            return False

        def delay(uc):
            if s.arg(0) == 10:
                pin = selected[0]
                index = counts[pin]
                value = s.rows[pin][index % len(s.rows[pin])]
                counts[pin] += 1
                s.reads.append((pin, value))
                s.w16(0x40013424, value)
                if len(s.reads) == cancel_at:
                    s.w8(STATE, 2)
            s.ret(0)
            return True

        def save(uc):
            s.saves.append(bytes(uc.mem_read(s.arg(0), 16)))
            return False  # run the real baseline-to-settings copy

        def home(uc):
            s.save_requests.append(s.arg(0))
            s.ret(0)
            return True

        s.at[SELECT], s.at[DELAY], s.at[SAVE], s.at[HOME_MESSAGE] = select, delay, save, home
        s.img = img
        s.before_baseline = bytes(s.uc.mem_read(BASE, 16))
        s.before_settings = bytes(s.uc.mem_read(SETTINGS, 0xCC))
        return s

    def run_init(self, s):
        registers = (UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7)
        values = [0xABCD0000 + i for i in range(4)]
        for reg, value in zip(registers, values):
            s.uc.reg_write(reg, value)
        result = s.call(HANDLER, COMMAND)
        self.assertEqual([s.uc.reg_read(reg) for reg in registers], values)
        self.assertEqual(s.uc.reg_read(UC_ARM_REG_SP), STACK)
        return result

    def test_each_pin_uses_five_real_counter_reads_and_saves_medians_once(self):
        s = self.scene()
        self.assertEqual(self.run_init(s), 0)
        expected = struct.pack('<8H', *[1002 + 20*pin for pin in range(8)])
        self.assertEqual([pin for pin, _ in s.reads], [pin for pin in range(8) for _ in range(5)])
        self.assertEqual(bytes(s.uc.mem_read(BASE, 16)), expected)
        self.assertEqual(bytes(s.uc.mem_read(SETTINGS + 0x90, 16)), expected)
        self.assertEqual(s.saves, [expected])
        self.assertEqual(s.save_requests, [5])
        self.assertEqual(bytes(s.uc.mem_read(FLAGS, 2)), bytes((5, 1)))
        self.assertEqual(s.selected[-1], 8)

    def test_unstable_last_pin_keeps_every_previous_baseline_and_settings_byte(self):
        rows = [[1000]*5 for _ in range(8)]
        rows[-1] = [1100, 1100, 1100, 1100, 1107]
        s = self.scene(rows)
        self.assertEqual(self.run_init(s), 1)
        self.assertEqual(len(s.reads), 40)
        self.assertEqual(bytes(s.uc.mem_read(BASE, 16)), s.before_baseline)
        self.assertEqual(bytes(s.uc.mem_read(SETTINGS, 0xCC)), s.before_settings)
        self.assertEqual(s.saves, [])
        self.assertEqual(s.save_requests, [])
        self.assertEqual(bytes(s.uc.mem_read(FLAGS, 2)), bytes((3, 1)))
        self.assertEqual(s.selected[-1], 8)
        self.assertIn(0x0E, [message[0] for message in s.msgs])

    def test_spread_at_six_is_accepted_and_seven_is_rejected(self):
        for span, status in ((6, 0), (7, 1)):
            with self.subTest(span=span):
                s = self.scene([[1000, 1000+span, 1002, 1001, 1003]]*8)
                self.assertEqual(self.run_init(s), status)
                self.assertEqual(len(s.saves), int(status == 0))

    def test_default_notification_adapter_preserves_stock_queue_abi(self):
        import qc_calibration as qc
        from lpm10a.thumb import assemble
        for span, result, final_message in ((6, 0, 0x0C), (7, 1, 0x0E)):
            with self.subTest(span=span):
                s = self.scene([[1000, 1000+span, 1002, 1001, 1003]]*8)
                sent = []

                def observe(uc):
                    sent.append((s.arg(0), s.arg(1), s.arg(2), uc.reg_read(UC_ARM_REG_SP) % 8))
                    return False

                s.at[qc.GUI_SEND] = observe
                self.assertEqual(self.run_init(s), result)
                self.assertEqual(sent, [(0x36, 0, 0, 0), (final_message, 0, 0, 0)])
                self.assertEqual(s.msgs, [(0x36, b''), (final_message, b'')])
                adapter = s.img.qc_calibration['notify']
                self.assertEqual(s.img.read(adapter, 4), assemble(adapter, f'b.w {qc.GUI_SEND}'))

    def test_cancellation_after_every_counter_read_is_transactional(self):
        for sample in range(1, 41):
            with self.subTest(sample=sample):
                s = self.scene(cancel_at=sample)
                self.assertEqual(self.run_init(s), 2)
                self.assertEqual(len(s.reads), sample)
                self.assertEqual(bytes(s.uc.mem_read(BASE, 16)), s.before_baseline)
                self.assertEqual(bytes(s.uc.mem_read(SETTINGS, 0xCC)), s.before_settings)
                self.assertEqual(s.saves, [])
                self.assertEqual(s.save_requests, [])
                self.assertEqual(bytes(s.uc.mem_read(FLAGS, 2)), bytes((4, 1)),
                                 'leaving QC cannot restore status over a newer session')
                self.assertEqual(s.selected[-1], 8)
                self.assertNotIn(0x0E, [message[0] for message in s.msgs])

    def test_unusable_baselines_are_rejected_without_overwriting_prior_calibration(self):
        for value in (0, 6, 7, 65534, 65535):
            with self.subTest(value=value):
                s = self.scene([[value]*5]*8)
                success = 7 <= value < 65535
                self.assertEqual(self.run_init(s), 0 if success else 1)
                self.assertEqual(bool(s.saves), success)
                if not success:
                    self.assertEqual(bytes(s.uc.mem_read(BASE, 16)), s.before_baseline)
                    self.assertEqual(bytes(s.uc.mem_read(SETTINGS, 0xCC)), s.before_settings)

    def test_handoff_waits_for_ownership_and_an_abort_does_not_release_another_sampler(self):
        for owned in (False, True):
            with self.subTest(owned=owned):
                s = self.scene()
                def handoff(uc):
                    self.assertEqual(s.uc.mem_read(FLAGS, 1)[0], 4)
                    self.assertEqual(s.selected, [])
                    self.assertEqual(s.reads, [])
                    s.ret(int(owned))
                    return True
                s.at[s.img.qc_calibration['handoff']] = handoff
                self.assertEqual(self.run_init(s), 0 if owned else 2)
                if not owned:
                    self.assertEqual(s.selected, [])
                    self.assertEqual(s.saves, [])
                    self.assertEqual(bytes(s.uc.mem_read(BASE, 16)), s.before_baseline)
                    self.assertEqual(bytes(s.uc.mem_read(SETTINGS, 0xCC)), s.before_settings)

    def test_complete_baseline_commit_is_inside_one_critical_section(self):
        import qc_calibration as qc
        s = self.scene()
        critical, writes = [False], []
        def enter(uc):
            self.assertFalse(critical[0])
            critical[0] = True
            s.ret(0)
            return True
        def leave(uc):
            self.assertTrue(critical[0])
            critical[0] = False
            s.ret(0)
            return True
        def write(uc, access, address, size, value, user):
            self.assertTrue(critical[0])
            self.assertEqual(len(s.reads), 40)
            writes.append((address, size))
        s.at[qc.ENTER_CRITICAL], s.at[qc.EXIT_CRITICAL] = enter, leave
        h = s.uc.hook_add(UC_HOOK_MEM_WRITE, write, begin=BASE, end=BASE+15)
        try:
            self.assertEqual(self.run_init(s), 0)
        finally:
            s.uc.hook_del(h)
        self.assertEqual(writes, [(BASE+2*pin, 2) for pin in range(8)])
        self.assertFalse(critical[0])

    def test_state_change_at_commit_boundary_is_still_canceled(self):
        import qc_calibration as qc
        s = self.scene()
        critical = []
        def enter(uc):
            critical.append('enter')
            if len(s.reads) == 40:
                s.w8(STATE, 2)
            s.ret(0)
            return True
        def leave(uc):
            critical.append('leave')
            s.ret(0)
            return True
        s.at[qc.ENTER_CRITICAL], s.at[qc.EXIT_CRITICAL] = enter, leave
        self.assertEqual(self.run_init(s), 2)
        self.assertEqual(critical, ['enter', 'leave']*3)
        self.assertEqual(len(s.reads), 40)
        self.assertEqual(bytes(s.uc.mem_read(BASE, 16)), s.before_baseline)
        self.assertEqual(bytes(s.uc.mem_read(SETTINGS, 0xCC)), s.before_settings)
        self.assertEqual(s.saves, [])

    def test_stack_is_bounded_and_only_entry_and_appended_code_change(self):
        import qc_calibration as qc
        s = self.scene()
        lows = []
        def stack(uc, address, size, user):
            lows.append(uc.reg_read(UC_ARM_REG_SP))
        h = s.uc.hook_add(UC_HOOK_CODE, stack)
        try:
            self.assertEqual(self.run_init(s), 0)
        finally:
            s.uc.hook_del(h)
        self.assertLessEqual(STACK-min(lows), 192)
        self.assertEqual(s.img.ram_allocs, self.parent.ram_allocs)
        old = bytes(self.parent.finalize().data)
        new = bytes(s.img.data)
        allowed = set(range(0x24, 0x2C)) | set(range(s.img.f(HANDLER), s.img.f(HANDLER)+4))
        for offset in range(self.parent.f(self.parent.cave_ptr)):
            if old[offset] != new[offset]:
                self.assertIn(offset, allowed)
        before, pointer = bytes(s.img.data), s.img.cave_ptr
        with self.assertRaises(PatchError):
            qc.apply(s.img)
        self.assertEqual(bytes(s.img.data), before)
        self.assertEqual(s.img.cave_ptr, pointer)

    def test_queued_init_outside_qc_and_noninitialization_commands_do_not_measure(self):
        for state, command in ((2, 0), (8, 1), (8, 2)):
            with self.subTest(state=state, command=command):
                s = self.scene(state=state, command=command)
                self.run_init(s)
                self.assertEqual(s.reads, [])
                self.assertEqual(s.saves, [])
                self.assertEqual(bytes(s.uc.mem_read(BASE, 16)), s.before_baseline)


class QCCalibrationHandoff(unittest.TestCase):
    """Switch two real task contexts while the GUI owns an unfinished pin.

    Timer registers and RTOS context switches are modeled; both tasks execute
    the candidate's actual acquisition, handoff, commit and GUI instructions.
    Separate stacks prevent an artificial nested-call ABI from hiding races.
    """

    @classmethod
    def setUpClass(cls):
        import qc_continuity
        with contextlib.redirect_stdout(io.StringIO()):
            cls.img = qc_continuity.build_candidate()
        cls.data = bytes(cls.img.data)

    def paused_tasks(self):
        from test_qc_continuity import Harness, POLL, AFTER_RECEIVE
        h = Harness(self.data)
        h.enter()
        h.advance(50)
        s, q = h.s, self.img.qc['state']
        delay = s.at[DELAY]
        waits = []

        def pause(uc):
            waits.append(s.arg(0))
            uc.emu_stop()
            return True

        s.at[DELAY] = pause
        s.uc.reg_write(UC_ARM_REG_SP, STACK)
        s.uc.reg_write(UC_ARM_REG_LR, MAGIC | 1)
        s.uc.emu_start(POLL | 1, AFTER_RECEIVE, count=2_000_000)
        self.assertEqual(s.uc.reg_read(UC_ARM_REG_PC), DELAY)
        self.assertEqual(waits, [10])
        self.assertEqual(h.read(q+3), 1)
        self.assertEqual(h.selected, 0)
        self.assertEqual(h.reads, [])
        gui_context = s.uc.context_save()

        s.w8(COMMAND, 0)
        s.uc.reg_write(UC_ARM_REG_SP, STACK-0x400)
        s.uc.reg_write(UC_ARM_REG_LR, MAGIC | 1)
        s.uc.reg_write(UC_ARM_REG_R0, COMMAND)
        s.uc.emu_start(HANDLER | 1, MAGIC, count=2_000_000)
        self.assertEqual(s.uc.reg_read(UC_ARM_REG_PC), DELAY)
        self.assertEqual(waits, [10, 1])
        self.assertEqual(h.read(FLAGS), 4)
        self.assertEqual(h.read(q+3), 1)
        self.assertEqual(h.selections, [0], 'Init must not select a pin owned by the GUI')
        self.assertEqual(h.reads, [])
        calibration_context = s.uc.context_save()
        s.at[DELAY] = delay
        return h, gui_context, calibration_context

    def test_inflight_gui_pin_finishes_before_init_takes_timer_and_saves(self):
        from test_qc_continuity import AFTER_RECEIVE, COUNTS
        h, gui_context, calibration_context = self.paused_tasks()
        s, q = h.s, self.img.qc['state']
        baseline = bytes(s.uc.mem_read(BASE, 16))
        s.uc.mem_write(SETTINGS+0x90, bytes(range(16)))
        saves, messages = [], []

        def save(uc):
            saves.append(bytes(uc.mem_read(s.arg(0), 16)))
            return False

        def home(uc):
            messages.append(s.arg(0))
            s.ret(0)
            return True

        s.at[SAVE], s.at[HOME_MESSAGE] = save, home
        s.uc.context_restore(gui_context)
        s.uc.emu_start(DELAY | 1, AFTER_RECEIVE, count=2_000_000)
        self.assertEqual(s.uc.reg_read(UC_ARM_REG_PC), AFTER_RECEIVE)
        self.assertEqual(s.uc.reg_read(UC_ARM_REG_SP), STACK)
        self.assertEqual(len(h.reads), 1)
        self.assertEqual(h.selected, 8)
        self.assertEqual(h.read(q+3), 0)
        self.assertEqual(h.read(FLAGS), 4)
        self.assertEqual(bytes(s.uc.mem_read(q+16, 24)), bytes(24))
        self.assertEqual(bytes(s.uc.mem_read(COUNTS, 16)), bytes(16))
        self.assertEqual(bytes(s.uc.mem_read(BASE, 16)), baseline)
        self.assertEqual(h.timeouts[-1], 1)

        s.uc.context_restore(calibration_context)
        s.uc.emu_start(DELAY | 1, MAGIC, count=2_000_000)
        self.assertEqual(s.uc.reg_read(UC_ARM_REG_PC), MAGIC)
        self.assertEqual(s.uc.reg_read(UC_ARM_REG_SP), STACK-0x400)
        self.assertEqual(s.arg(0), 0)
        self.assertEqual([pin for pin, _, _ in h.reads[1:]], [pin for pin in range(8) for _ in range(5)])
        self.assertEqual(h.selections, [0, 8]+list(range(8))+[8])
        expected = struct.pack('<8H', *([900]*8))
        self.assertEqual(saves, [expected])
        self.assertEqual(messages, [5])
        self.assertEqual(bytes(s.uc.mem_read(BASE, 16)), expected)
        self.assertEqual(bytes(s.uc.mem_read(SETTINGS+0x90, 16)), expected)
        self.assertEqual(bytes(s.uc.mem_read(FLAGS, 2)), bytes((5, 1)))
        s.drain()
        self.assertEqual(h.read(q), 1)
        self.assertEqual(bytes(s.uc.mem_read(q+40, 16)), expected)
        self.assertEqual(h.read(q+8, 2), 0)

    def test_leaving_while_init_waits_keeps_live_owner_and_prior_calibration(self):
        from test_qc_continuity import AFTER_RECEIVE
        h, gui_context, calibration_context = self.paused_tasks()
        s, q = h.s, self.img.qc['state']
        baseline = bytes(s.uc.mem_read(BASE, 16))
        settings = bytes(s.uc.mem_read(SETTINGS, 0xCC))
        s.w8(STATE, 2)
        s.uc.context_restore(calibration_context)
        s.uc.emu_start(DELAY | 1, MAGIC, count=2_000_000)
        self.assertEqual(s.uc.reg_read(UC_ARM_REG_PC), MAGIC)
        self.assertEqual(s.uc.reg_read(UC_ARM_REG_SP), STACK-0x400)
        self.assertEqual(s.arg(0), 2)
        self.assertEqual(h.selections, [0], 'an aborted waiter cannot release the other task\'s mux')
        self.assertEqual(h.read(q+3), 1)
        self.assertEqual(h.reads, [])
        self.assertEqual(bytes(s.uc.mem_read(BASE, 16)), baseline)
        self.assertEqual(bytes(s.uc.mem_read(SETTINGS, 0xCC)), settings)

        s.uc.context_restore(gui_context)
        s.uc.emu_start(DELAY | 1, AFTER_RECEIVE, count=2_000_000)
        self.assertEqual(s.uc.reg_read(UC_ARM_REG_PC), AFTER_RECEIVE)
        self.assertEqual(h.selections, [0, 8])
        self.assertEqual(h.read(q+3), 0)
        self.assertEqual(bytes(s.uc.mem_read(q+16, 24)), bytes(24))
        self.assertEqual(bytes(s.uc.mem_read(BASE, 16)), baseline)
        self.assertEqual(bytes(s.uc.mem_read(SETTINGS, 0xCC)), settings)

    def test_exit_and_reentry_during_init_cannot_save_or_overwrite_new_session(self):
        from test_qc_continuity import ENTRY, Harness
        h = Harness(self.data)
        h.enter()
        s, q = h.s, self.img.qc['state']
        s.w8(COMMAND, 4, 3)
        s.call(0x080149FC, COMMAND)
        s.drain()
        self.assertEqual(h.read(FLAGS), 3)
        before_baseline = bytes(s.uc.mem_read(BASE, 16))
        before_settings = bytes(s.uc.mem_read(SETTINGS, 0xCC))
        delay = s.at[DELAY]

        def pause(uc):
            self.assertEqual(s.arg(0), 10)
            uc.emu_stop()
            return True

        s.at[DELAY] = pause
        s.w8(COMMAND, 0)
        s.uc.reg_write(UC_ARM_REG_SP, STACK-0x400)
        s.uc.reg_write(UC_ARM_REG_LR, MAGIC | 1)
        s.uc.reg_write(UC_ARM_REG_R0, COMMAND)
        s.uc.emu_start(HANDLER | 1, MAGIC, count=2_000_000)
        self.assertEqual(s.uc.reg_read(UC_ARM_REG_PC), DELAY)
        self.assertEqual(h.read(q+3), 2)
        self.assertEqual(h.read(FLAGS), 4)
        self.assertEqual(h.selected, 0)
        generation = h.read(q+56, 4)
        calibration_context = s.uc.context_save()

        s.w8(STATE, 2)
        s.call(ENTRY)
        s.drain()
        self.assertNotEqual(h.read(q+56, 4), generation)
        self.assertEqual(h.read(q+3), 2, 'new entry cannot release a calibration timer owner')
        self.assertEqual(h.read(FLAGS), 2)
        h.advance(50)
        self.assertEqual(h.poll(), 0, 'the new session must wait for old Init to release TIM8')
        self.assertEqual(h.selected, 0)
        self.assertEqual(h.timeouts[-1], 1)

        s.at[DELAY] = delay
        s.uc.context_restore(calibration_context)
        s.uc.emu_start(DELAY | 1, MAGIC, count=2_000_000)
        self.assertEqual(s.uc.reg_read(UC_ARM_REG_PC), MAGIC)
        self.assertEqual(s.uc.reg_read(UC_ARM_REG_SP), STACK-0x400)
        self.assertEqual(s.arg(0), 2)
        self.assertEqual(len(h.reads), 1)
        self.assertEqual(h.selections, [0, 8])
        self.assertEqual(h.read(q+3), 0)
        self.assertEqual(h.read(q), 1)
        self.assertEqual(h.read(FLAGS), 2, 'canceled Init cannot restore the old held status')
        self.assertEqual(bytes(s.uc.mem_read(BASE, 16)), before_baseline)
        self.assertEqual(bytes(s.uc.mem_read(SETTINGS, 0xCC)), before_settings)
        self.assertEqual(s.msgs, [])
        self.assertEqual(h.poll(), 1)

    def test_exit_and_reentry_while_init_posts_progress_cannot_adopt_new_session(self):
        from test_qc_continuity import ENTRY, Harness
        h = Harness(self.data)
        h.enter()
        s, q = h.s, self.img.qc['state']
        baseline = bytes(s.uc.mem_read(BASE, 16))
        settings = bytes(s.uc.mem_read(SETTINGS, 0xCC))
        progress_send = 0x0800E428

        def pause(uc):
            self.assertEqual(s.arg(0), 0x36)
            uc.emu_stop()
            return True

        def home(uc):
            s.ret(0)
            return True

        s.at[progress_send], s.at[HOME_MESSAGE] = pause, home
        s.w8(COMMAND, 0)
        s.uc.reg_write(UC_ARM_REG_SP, STACK-0x400)
        s.uc.reg_write(UC_ARM_REG_LR, MAGIC | 1)
        s.uc.reg_write(UC_ARM_REG_R0, COMMAND)
        s.uc.emu_start(HANDLER | 1, MAGIC, count=2_000_000)
        self.assertEqual(s.uc.reg_read(UC_ARM_REG_PC), progress_send)
        self.assertEqual(h.read(FLAGS), 4)
        context = s.uc.context_save()
        del s.at[progress_send]
        s.w8(STATE, 2)
        s.call(ENTRY)
        s.drain()
        self.assertEqual(h.read(FLAGS), 2)

        s.uc.context_restore(context)
        s.uc.emu_start(progress_send | 1, MAGIC, count=2_000_000)
        self.assertEqual(s.uc.reg_read(UC_ARM_REG_PC), MAGIC)
        self.assertEqual(s.arg(0), 2)
        self.assertEqual(h.reads, [])
        self.assertEqual(bytes(s.uc.mem_read(BASE, 16)), baseline)
        self.assertEqual(bytes(s.uc.mem_read(SETTINGS, 0xCC)), settings)
        self.assertEqual(h.read(FLAGS), 2)
        self.assertEqual(h.read(q+3), 0)


if __name__ == '__main__':
    unittest.main()
