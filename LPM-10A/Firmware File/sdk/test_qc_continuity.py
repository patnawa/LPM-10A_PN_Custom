"""QC lifecycle and timer-count regressions through the real GUI receive path.

Only the elapsed RTOS delay, the TIM8 external pulse count and queue delivery
are modeled. Wire selection, counter reset/read, GUI dispatch and candidate
firmware helpers execute their actual ARM instructions.
"""
import struct
import unittest

from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm_const import (UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_PRIMASK,
                               UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6,
                               UC_ARM_REG_R7, UC_ARM_REG_R8, UC_ARM_REG_R9,
                               UC_ARM_REG_R10, UC_ARM_REG_R11, UC_ARM_REG_SP)

from thai.engine import MAGIC, Scene


ENTRY, RUN, SELECT = 0x0800BA2C, 0x0800BF40, 0x08018060
DELAY, RECEIVE, COUNTER_READ = 0x0801C75C, 0x0801CBB8, 0x0801858C
POLL, AFTER_RECEIVE, TIMER_COUNT = 0x0800F462, 0x0800F470, 0x40013424
BASE, COUNTS, FLAGS, STATE = 0x2000021C, 0x2000022C, 0x2000023C, 0x2000013C
STACK = 0x2000DFC0
SAVED = (UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
         UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11)


class Harness:
    def __init__(self, data, *, lang=1, baselines=None):
        self.s = s = Scene(image=data, lang=lang)
        self.selected = 8
        self.selections, self.reads, self.delays, self.timeouts = [], [], [], []
        self.values = [900]*8
        self.pin_reads = [0]*8
        self.source = lambda pin, number: self.values[pin]
        self.during_sample = None

        def select(uc):
            self.selected = s.arg(0)
            self.selections.append(self.selected)
            return False  # Execute the real mux GPIO function.

        def delay(uc):
            duration = s.arg(0)
            self.delays.append(duration)
            s.vals['tick'] += duration
            if duration == 10 and self.selected < 8:
                pin = self.selected
                value = self.source(pin, self.pin_reads[pin])
                s.w16(TIMER_COUNT, value)
                if self.during_sample:
                    self.during_sample(self)
            s.ret(0)
            return True

        def counter(uc):
            pin = self.selected
            value = int.from_bytes(uc.mem_read(TIMER_COUNT, 2), 'little')
            self.reads.append((pin, value, s.vals['tick']))
            self.pin_reads[pin] += 1
            return False  # Read TIM8's modeled register using the real code.

        def receive(uc):
            self.timeouts.append(s.arg(2))
            # One GUI queue wait; the test drives GUI event delivery explicitly.
            timeout = s.arg(2)
            if timeout != 0xFFFFFFFF:
                s.vals['tick'] += timeout
            s.ret(0)
            return True

        s.at[SELECT], s.at[DELAY] = select, delay
        s.at[COUNTER_READ], s.at[RECEIVE] = counter, receive
        s.w16(BASE, *(baselines if baselines is not None else [1000]*8))

    def read(self, address, size=1):
        return int.from_bytes(self.s.uc.mem_read(address, size), 'little')

    def enter(self):
        self.s.call(ENTRY)
        self.s.drain()

    def start_stop(self):
        self.press(4)

    def restart(self):
        self.press(5)

    def press(self, key, event=3, *, drain=True):
        """Send an event through the real Action_key_Process pipeline."""
        self.s.w8(0x20003200, key, event)
        self.s.call(0x080149FC, 0x20003200)
        pending = list(self.s.msgs)
        if drain:
            self.s.drain()
        return pending

    def advance(self, ticks):
        self.s.vals['tick'] = (self.s.vals['tick']+ticks) & 0xFFFFFFFF

    def poll(self, *, drain=True):
        """One actual GUI receive prefix, including the patched scheduling call."""
        s = self.s
        expected = [0xACBD0000+i for i in range(len(SAVED))]
        for reg, value in zip(SAVED, expected):
            s.uc.reg_write(reg, value)
        s.uc.reg_write(UC_ARM_REG_SP, STACK)
        s.uc.reg_write(UC_ARM_REG_LR, MAGIC | 1)
        before = len(self.reads)
        # Every eighth pin also renders the whole result using real glyph code.
        s.uc.emu_start(POLL | 1, AFTER_RECEIVE, count=2_000_000)
        if s.uc.reg_read(UC_ARM_REG_PC) != AFTER_RECEIVE:
            raise AssertionError('GUI poll exceeded its instruction budget')
        if s.uc.reg_read(UC_ARM_REG_SP) != STACK:
            raise AssertionError('GUI poll changed its caller stack')
        if [s.uc.reg_read(reg) for reg in SAVED] != expected:
            raise AssertionError('GUI poll corrupted callee-saved registers')
        if drain:
            s.drain()
        return len(self.reads)-before


class QCContinuity(unittest.TestCase):
    patched = True

    @classmethod
    def setUpClass(cls):
        if cls.patched:
            import qc_continuity
            cls.img = qc_continuity.build_candidate()
            cls.info = cls.img.qc
            cls.state_size = qc_continuity.STATE_SIZE
        else:
            from test_cable_test import build
            cls.img = build('pn2.23')
            cls.info = None
        cls.data = bytes(cls.img.finalize().data)

    def scene(self, **options):
        h = Harness(self.data, **options)
        h.enter()
        return h

    def mode(self, h):
        return h.read(self.info['state'])

    def now(self, h):
        return list(h.s.uc.mem_read(self.info['state']+32, 8))

    def faults(self, h):
        return list(struct.unpack('<8H', h.s.uc.mem_read(self.info['state']+16, 16)))

    def samples(self, h, count):
        target = len(h.reads)+count
        for _ in range(count+60):
            self.assertLessEqual(h.poll(), 1, 'a GUI receive iteration may sample at most one pin')
            if len(h.reads) == target:
                return
        self.fail(f'continuous QC acquired {len(h.reads)} samples, expected {target}')

    def test_gui_entry_starts_continuous_sampling_without_timer_run_messages(self):
        h = self.scene()
        self.samples(h, 16)
        self.assertEqual([pin for pin, _, _ in h.reads], list(range(8))*2)
        self.assertEqual(h.delays, [10]*16, 'the original fifty-tick blocking wait is gone')
        self.assertEqual(self.now(h), [1]*8)
        self.assertEqual(self.faults(h), [0]*8)
        self.assertEqual(h.read(self.info['state']+8, 2), 2)
        self.assertTrue(all(timeout == 1 for timeout in h.timeouts))

    def test_one_bad_raw_count_then_good_retains_only_that_pin_history(self):
        h = self.scene()
        h.source = lambda pin, number: 1000 if pin == 2 and number == 0 else 900
        self.samples(h, 24)
        self.assertEqual(self.now(h), [1]*8)
        self.assertEqual(self.faults(h), [0, 0, 1, 0, 0, 0, 0, 0],
                         'a brief raw failure must survive later passing samples')

    def test_persistent_bad_counts_are_one_episode_until_a_pass_rearms_history(self):
        h = self.scene()
        h.values[4] = 1000
        self.samples(h, 24)
        self.assertEqual(self.faults(h)[4], 1)
        h.values[4] = 900
        self.samples(h, 8)
        h.values[4] = 1010
        self.samples(h, 8)
        self.assertEqual(self.faults(h)[4], 2)
        self.assertEqual(self.now(h)[4], 3)

    def test_raw_count_boundaries_preserve_open_check_and_good_distinctions(self):
        h = self.scene()
        h.values = [0, 65535, 994, 993, 1000, 1006, 1007, 900]
        self.samples(h, 8)
        self.assertEqual(self.now(h), [3, 3, 2, 1, 2, 2, 3, 1])
        self.assertEqual(self.faults(h), [1, 1, 1, 0, 1, 1, 1, 0])

    def test_hold_stops_sampling_and_a_new_session_clears_old_history(self):
        h = self.scene()
        h.values[1] = 1000
        self.samples(h, 8)
        h.start_stop()
        self.assertEqual(self.mode(h), 3)
        before = list(h.reads)
        for _ in range(3):
            self.assertEqual(h.poll(), 0)
        self.assertEqual(h.reads, before)
        self.assertEqual(h.timeouts[-1], 0xFFFFFFFF)
        self.assertEqual(self.faults(h)[1], 1)
        h.values[1] = 900
        h.start_stop()
        self.assertEqual(self.faults(h), [0]*8)
        self.assertEqual(self.now(h), [0]*8)
        self.samples(h, 8)
        self.assertEqual(self.faults(h), [0]*8)

    def test_right_restart_and_reentry_reset_history_synchronously(self):
        for action in ('right', 'entry'):
            with self.subTest(action=action):
                h = self.scene()
                h.values[7] = 1000
                self.samples(h, 8)
                if action == 'right':
                    h.restart()
                else:
                    h.s.set_state(2)
                    h.s.call(ENTRY)
                    self.assertEqual(self.faults(h), [0]*8, 'entry must clear before queued GUI drawing')
                    h.s.drain()
                self.assertEqual(self.mode(h), 1)
                self.assertEqual(self.faults(h), [0]*8)
                self.assertEqual(self.now(h), [0]*8)

    def test_twenty_second_limit_is_bounded_even_across_tick_wrap(self):
        for start in (0, 0xFFFFFFE0):
            with self.subTest(start=start):
                h = Harness(self.data)
                h.s.vals['tick'] = start
                h.enter()
                self.samples(h, 8)
                elapsed = (h.s.vals['tick']-start) & 0xFFFFFFFF
                h.advance(20_000-elapsed)
                self.assertEqual(h.poll(), 0)
                self.assertEqual(self.mode(h), 2)
                self.assertEqual(h.timeouts[-1], 0xFFFFFFFF)
                self.assertEqual(h.selected, 8)

    def test_leaving_during_counter_wait_discards_the_sample_and_stops_hardware(self):
        h = self.scene()
        h.during_sample = lambda fixture: fixture.s.w8(STATE, 2)
        h.advance(50)
        before = len(h.s.log)
        h.poll()
        self.assertEqual(h.read(STATE), 2)
        self.assertEqual(self.now(h), [0]*8)
        self.assertEqual(self.faults(h), [0]*8)
        self.assertEqual(h.read(self.info['state']+3), 0, 'the hardware claim must be released')
        self.assertEqual(h.selected, 8)
        self.assertEqual(h.s.log[before:], [], 'cancelled QC must not redraw the new screen')
        before_reads = len(h.reads)
        for _ in range(3):
            self.assertEqual(h.poll(), 0)
        self.assertEqual(len(h.reads), before_reads)

    def test_rapid_exit_and_reentry_keep_timer_ownership_and_discard_the_old_sample(self):
        h = self.scene()
        q = self.info['state']
        observed = []

        def reenter(fixture):
            s = fixture.s
            before = fixture.read(q+3)
            s.w8(STATE, 2)
            context = s.uc.context_save()
            try:
                # The Home task has its own stack while the GUI task sleeps.
                # Using Scene.call's stack here would overwrite the suspended
                # poll's saved registers, unlike an actual RTOS task switch.
                s.uc.reg_write(UC_ARM_REG_SP, 0x2000C000)
                s.uc.reg_write(UC_ARM_REG_LR, MAGIC | 1)
                s.uc.emu_start(ENTRY | 1, MAGIC, count=100_000)
                self.assertEqual(s.uc.reg_read(UC_ARM_REG_PC), MAGIC)
                self.assertEqual(s.uc.reg_read(UC_ARM_REG_SP), 0x2000C000)
            finally:
                s.uc.context_restore(context)
            observed.append((before, fixture.read(q+3), fixture.read(STATE)))

        h.during_sample = reenter
        h.advance(50)
        h.poll(drain=False)
        self.assertEqual(observed, [(1, 1, 8)],
                         'screen reentry must not release another task\'s live TIM8 claim')
        self.assertEqual(self.now(h), [0]*8,
                         'the pre-entry sample must not publish into the new session')
        self.assertEqual(self.faults(h), [0]*8)
        self.assertEqual(h.read(q+3), 0, 'only the suspended acquisition releases BUSY')
        self.assertEqual(h.selected, 8)
        h.during_sample = None
        h.s.drain()
        self.assertEqual(self.now(h), [0]*8)
        self.samples(h, 8)
        self.assertEqual(self.faults(h), [0]*8)

    def test_legacy_periodic_run_message_cannot_toggle_or_restart_a_session(self):
        h = self.scene()
        h.values[3] = 1000
        self.samples(h, 8)
        snapshot = bytes(h.s.uc.mem_read(self.info['state'], self.state_size))
        for _ in range(3):
            h.s.dispatch(0x0D)
            h.s.drain()
        self.assertEqual(bytes(h.s.uc.mem_read(self.info['state'], self.state_size)), snapshot)
        h.s.set_state(7)
        self.assertEqual(h.poll(), 0)
        before = len(h.s.log)
        h.s.dispatch(0x0D)
        h.s.drain()
        self.assertEqual(h.s.log[before:], [])

    def test_controls_from_a_previous_visit_cannot_change_the_new_session(self):
        for key in (4, 5):
            with self.subTest(key=key):
                h = self.scene()
                pending = h.press(key, drain=False)
                self.assertEqual(len(pending), 1)
                self.assertEqual(len(pending[0][1]), 4)
                h.s.msgs.clear()
                h.s.set_state(2)
                h.enter()
                q = self.info['state']
                self.assertNotEqual(struct.unpack('<I', pending[0][1])[0], h.read(q+56, 4))
                snapshot = bytes(h.s.uc.mem_read(q, self.state_size))
                before = len(h.s.log)
                h.s.dispatch(*pending[0])
                h.s.drain()
                self.assertEqual(bytes(h.s.uc.mem_read(q, self.state_size)), snapshot)
                self.assertEqual(h.s.log[before:], [])
                self.samples(h, 8)
                self.assertEqual(self.now(h), [1]*8)

    def test_controls_without_a_session_payload_do_not_change_the_session(self):
        h = self.scene()
        h.values[0] = 1000
        self.samples(h, 8)
        q = self.info['state']
        snapshot = bytes(h.s.uc.mem_read(q, self.state_size))
        before = len(h.s.log)
        for message in (0x3E, 0x3F):
            h.s.dispatch(message)
            h.s.drain()
        self.assertEqual(bytes(h.s.uc.mem_read(q, self.state_size)), snapshot)
        self.assertEqual(h.s.log[before:], [])

    def test_invalid_baseline_or_calibration_flag_prevents_sampling(self):
        for pin, baseline in ((0, 0), (7, 6), (4, 65535)):
            with self.subTest(pin=pin, baseline=baseline):
                values = [1000]*8
                values[pin] = baseline
                h = self.scene(baselines=values)
                h.advance(100)
                for _ in range(3):
                    self.assertEqual(h.poll(), 0)
                self.assertEqual(self.mode(h), 0)
                self.assertEqual(h.timeouts[-1], 0xFFFFFFFF)
        h = Harness(self.data)
        h.s.call(ENTRY)
        h.s.w8(FLAGS+1, 0)
        h.s.drain()
        h.advance(100)
        self.assertEqual(h.poll(), 0)
        self.assertEqual(self.mode(h), 0)

    def test_calibration_claim_before_or_during_measurement_blocks_publication(self):
        for during in (False, True):
            with self.subTest(during=during):
                h = self.scene()
                if during:
                    h.during_sample = lambda fixture: fixture.s.w8(FLAGS, 4)
                else:
                    h.s.w8(FLAGS, 4)
                h.advance(50)
                before = len(h.s.log)
                h.poll()
                self.assertEqual(len(h.reads), int(during))
                self.assertEqual(self.now(h), [0]*8)
                self.assertEqual(self.faults(h), [0]*8)
                self.assertEqual(h.read(self.info['state']+3), 0)
                self.assertEqual(h.timeouts[-1], 1,
                                 'a live session must keep polling while Init drains')
                self.assertEqual(h.s.log[before:], [])

    def test_a_busy_timer_keeps_the_live_session_polling_without_sampling(self):
        h = self.scene()
        h.advance(50)
        h.s.w8(self.info['state']+3, 2)
        for _ in range(3):
            self.assertEqual(h.poll(), 0)
            self.assertEqual(h.timeouts[-1], 1)
            self.assertEqual(h.read(self.info['state']+3), 2)
        h.s.w8(self.info['state']+3, 0)
        self.samples(h, 8)
        self.assertEqual(self.now(h), [1]*8)

    def test_calibration_handoff_is_bounded_and_cannot_steal_a_busy_timer(self):
        h = self.scene()
        h.s.call(self.info['cal_begin'])
        h.s.w8(FLAGS, 4)
        h.s.w8(self.info['state']+3, 1)
        before = len(h.delays)
        self.assertEqual(h.s.call(self.info['handoff']), 0)
        self.assertEqual(h.delays[before:], [1]*100)
        self.assertEqual(h.read(self.info['state']+3), 1)
        self.assertEqual(h.reads, [])
        h.s.w8(self.info['state']+3, 0)
        self.assertEqual(h.s.call(self.info['handoff']), 1)
        self.assertEqual(h.read(self.info['state']+3), 2)
        h.s.call(self.info['cal_release'])
        self.assertEqual(h.read(self.info['state']+3), 0)

    def test_scanning_keeps_baselines_settings_and_adjacent_arena_memory_untouched(self):
        h = self.scene()
        q = self.info['state']
        baseline = bytes(h.s.uc.mem_read(BASE, 16))
        settings = bytes(h.s.uc.mem_read(0x20000C78, 0xCC))
        before = bytes(h.s.uc.mem_read(q-16, 16))
        after = bytes(h.s.uc.mem_read(q+self.state_size, 16))
        writes = []
        def write(uc, access, address, size, value, user):
            if q-16 <= address < q+self.state_size+16:
                writes.append((address, size))
                self.assertGreaterEqual(address, q)
                self.assertLessEqual(address+size, q+self.state_size)
        hook = h.s.uc.hook_add(UC_HOOK_MEM_WRITE, write)
        try:
            h.values[0] = 1000
            self.samples(h, 8)
            h.values[0] = 900
            self.samples(h, 8)
        finally:
            h.s.uc.hook_del(hook)
        self.assertTrue(writes)
        self.assertEqual(bytes(h.s.uc.mem_read(BASE, 16)), baseline)
        self.assertEqual(bytes(h.s.uc.mem_read(0x20000C78, 0xCC)), settings)
        self.assertEqual(bytes(h.s.uc.mem_read(q-16, 16)), before)
        self.assertEqual(bytes(h.s.uc.mem_read(q+self.state_size, 16)), after)

    def test_actual_ok_and_right_key_pipeline_controls_gui_owned_sessions(self):
        h = self.scene()
        h.values[6] = 1000
        self.samples(h, 8)

        self.assertIn(0x3E, [message[0] for message in h.press(4)])
        self.assertEqual(self.mode(h), 3)
        self.assertEqual(self.faults(h)[6], 1)
        self.assertIn(0x3E, [message[0] for message in h.press(4)])
        self.assertEqual(self.mode(h), 1)
        self.assertEqual(self.faults(h), [0]*8)
        self.samples(h, 8)
        self.assertIn(0x3F, [message[0] for message in h.press(5)])
        self.assertEqual(self.mode(h), 1)
        self.assertEqual(self.faults(h), [0]*8)
        self.assertEqual(self.now(h), [0]*8)

    def test_init_hold_posts_one_calibration_command_and_preserves_the_legacy_binding(self):
        for key, event, expected in ((5, 8, [(0, 0, 0)]),
                                     (5, 6, []), (1, 8, [(0, 0, 0)])):
            with self.subTest(key=key, event=event):
                h = self.scene()
                commands = []
                def send(uc):
                    commands.append(tuple(h.s.arg(i) for i in range(3)))
                    h.s.ret(0)
                    return True
                h.s.at[0x0800BCE8] = send
                before = bytes(h.s.uc.mem_read(self.info['state'], self.state_size))
                pending = h.press(key, event, drain=False)
                self.assertEqual(commands, expected)
                self.assertFalse(any(mid in (0x3E, 0x3F) for mid, data in pending),
                                 'a hold must not also trigger a click control')
                self.assertEqual(bytes(h.s.uc.mem_read(self.info['state'], self.state_size)), before,
                                 'the key task posts Init; it does not mutate the GUI session')

    def test_init_hold_keeps_the_parent_key_behavior_outside_qc(self):
        import qc_continuity
        parent = bytes(qc_continuity.parent().finalize().data)

        def outcome(data, state, key, event):
            h = Harness(data)
            h.s.w8(STATE, state)
            commands, actions = [], []
            def send(uc):
                commands.append(tuple(h.s.arg(i) for i in range(3)))
                h.s.ret(0)
                return True
            def action(uc):
                actions.append(h.s.arg(0))
                return False
            h.s.at[0x0800BCE8] = send
            h.s.at[0x0800D2B4] = action
            pending = h.press(key, event, drain=False)
            return commands, actions, pending, h.read(STATE)

        for state in (2, 4, 5, 6, 7, 9, 10, 11):
            for key, event in ((5, 8), (5, 6), (1, 8)):
                with self.subTest(state=state, key=key, event=event):
                    self.assertEqual(outcome(self.data, state, key, event),
                                     outcome(parent, state, key, event))

    def test_startup_and_entry_clear_poisoned_session_ram_before_it_is_used(self):
        for route in ('startup', 'entry'):
            with self.subTest(route=route):
                h = Harness(self.data)
                q = self.info['state']
                h.s.uc.mem_write(q, bytes([0xA5])*self.state_size)
                h.s.w8(q+3, 0)  # No suspended timer owner in this fixture.
                if route == 'startup':
                    h.s.call(self.info['init'])
                else:
                    h.s.call(ENTRY)
                cleared = self.state_size if route == 'startup' else 56
                self.assertEqual(bytes(h.s.uc.mem_read(q, cleared)), bytes(cleared))
                self.assertEqual(h.reads, [])
                if route == 'entry':
                    h.s.drain()
                    self.samples(h, 8)
                    self.assertEqual(self.faults(h), [0]*8)

    def test_calibration_preemption_at_each_unmasked_poll_instruction_respects_timer_owner(self):
        # First visit to each unique instruction in one actual pin acquisition;
        # this models an Init announcement, not every possible NVIC schedule.
        h = self.scene()
        h.advance(50)
        # Init captures its generation before announcing PHASE=4. Capture the
        # unchanged generation with the real callback before replaying each
        # atomic announcement, without overwriting the suspended GUI stack.
        h.s.call(self.info['cal_begin'])
        ram = bytes(h.s.uc.mem_read(0x20000000, 0x10000))
        context = h.s.uc.context_save()
        tick = h.s.vals['tick']
        points = set()
        def trace(uc, address, size, user):
            if not uc.reg_read(UC_ARM_REG_PRIMASK):
                points.add(address)
        hook = h.s.uc.hook_add(UC_HOOK_CODE, trace)
        try:
            h.poll()
        finally:
            h.s.uc.hook_del(hook)
        self.assertGreater(len(points), 50)
        self.__class__.poll_preemption_points = len(points)

        for point in sorted(points):
            with self.subTest(point=hex(point)):
                h.s.uc.mem_write(0x20000000, ram)
                h.s.uc.context_restore(context)
                h.s.vals['tick'] = tick
                h.reads.clear()
                h.delays.clear()
                h.timeouts.clear()
                h.selections.clear()
                h.s.msgs.clear()
                h.s.log.clear()
                h.pin_reads[:] = [0]*8
                h.selected = 8
                fired = []
                def announce(uc, address, size, user):
                    if address == point and not fired:
                        self.assertEqual(uc.reg_read(UC_ARM_REG_PRIMASK), 0)
                        fired.append((h.read(self.info['state']+3), len(h.reads), self.now(h)))
                        h.s.w8(FLAGS, 4)
                hook = h.s.uc.hook_add(UC_HOOK_CODE, announce)
                try:
                    h.poll()
                finally:
                    h.s.uc.hook_del(hook)
                self.assertEqual(len(fired), 1)
                busy, reads_before, published_before = fired[0]
                self.assertEqual(self.now(h), published_before,
                                 'an Init announcement must block later QC publication')
                self.assertLessEqual(len(h.reads), max(reads_before, busy))
                self.assertEqual(h.read(self.info['state']+3), 0)
                self.assertEqual(h.s.uc.reg_read(UC_ARM_REG_PRIMASK), 0)
                self.assertEqual(h.timeouts[-1], 1,
                                 'a live session must keep polling while Init drains')
                self.assertEqual(h.s.call(self.info['handoff']), 1,
                                 'calibration may own TIM8 only after the QC pin releases it')


if __name__ == '__main__':
    unittest.main()
