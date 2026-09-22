"""Length lifecycle through real sequence, state transition and entry code.

The PHY response, RTOS time and external queues are modeled by the existing
audit harness. Sequence/averaging logic and all cancellation checks execute
actual Thumb instructions. A separate event-task stack models navigation while
the network task is suspended inside vTaskDelay.
"""
import contextlib
import io
import struct
import unittest

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB
from unicorn import UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_R0, UC_ARM_REG_SP

from audit_flash_length import Machine, FLAGS, STOP

SEQUENCE, DELAY = 0x080119EC, 0x0801C75C
SET_STATE, ENTER = 0x0800F77C, 0x08012EE4
STATE = 0x2000013C


class LengthLifecycle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import length_integrity
        with contextlib.redirect_stdout(io.StringIO()):
            cls.img = length_integrity.build_candidate()
        cls.data = bytes(cls.img.data)

    def machine(self):
        m = Machine(self.data, 7)
        # Preserve the real state-transition/autosave checks; only its external
        # HOME queue is modeled, just like the PHY and network queues.
        m.handlers[0x08010EA8] = lambda machine: machine.ret(0)
        m.handlers[0x0800E40C] = lambda machine: machine.ret(0)
        m.handlers[STOP] = lambda machine: machine.uc.emu_stop()
        return m

    def press(self, m, key, event=3):
        m.w8(0x20003200, key)
        m.w8(0x20003201, event)
        self.event_call(m, 0x080149FC, 0x20003200)

    def back_and_reenter(self, m):
        self.press(m, 0)
        self.assertEqual(m.r8(STATE), 2)
        m.w8(STATE+1, 7)  # Home cursor points to Length.
        self.press(m, 4)
        self.assertEqual(m.r8(STATE), 7)

    def event_call(self, m, address, argument):
        context = m.uc.context_save()
        m.uc.reg_write(UC_ARM_REG_SP, 0x2000D000)
        m.uc.reg_write(UC_ARM_REG_LR, STOP | 1)
        m.uc.reg_write(UC_ARM_REG_R0, argument)
        try:
            m.uc.emu_start(address | 1, STOP, count=2_000_000)
            self.assertEqual(m.uc.reg_read(UC_ARM_REG_PC), STOP)
            self.assertEqual(m.uc.reg_read(UC_ARM_REG_SP), 0x2000D000)
        finally:
            m.uc.context_restore(context)

    def suspend_first_wait(self, m):
        m.call(SEQUENCE, until=DELAY, count=2_000_000)
        self.assertEqual(m.arg(0), 50)
        self.assertEqual(m.run_index, 0)
        self.assertEqual(m.r8(FLAGS), 1)

    def finish(self, m):
        m.uc.emu_start(DELAY | 1, STOP, count=2_000_000)
        self.assertEqual(m.uc.reg_read(UC_ARM_REG_PC), STOP)
        self.assertEqual(m.uc.reg_read(UC_ARM_REG_SP), 0x2000E000)

    def test_control_four_runs_publish_the_current_length_result(self):
        m = self.machine()
        m.call(SEQUENCE, count=2_000_000)
        self.assertEqual(m.run_index+1, 4)
        self.assertEqual(m.lengths(), [1000]*4)
        self.assertEqual(m.r8(FLAGS), 2)
        self.assertIn(0x1A, m.messages)

    def test_leaving_during_first_wait_cancels_without_publishing(self):
        m = self.machine()
        self.suspend_first_wait(m)
        self.event_call(m, SET_STATE, 2)
        m.messages.clear()
        self.finish(m)
        self.assertEqual(m.r8(STATE), 2)
        self.assertEqual(m.lengths(), [0]*4)
        self.assertEqual(m.r8(FLAGS), 0)
        self.assertNotIn(0x1A, m.messages)

    def test_rapid_reentry_cannot_publish_an_old_sequence_into_the_new_visit(self):
        m = self.machine()
        self.suspend_first_wait(m)
        self.back_and_reenter(m)
        self.assertEqual(m.r8(STATE), 7)
        self.assertEqual(m.r8(FLAGS), 0)
        self.assertEqual(m.lengths(), [0]*4)
        m.messages.clear()
        self.finish(m)
        self.assertEqual(m.lengths(), [0]*4,
                         'the previous visit\'s network task overwrote the new visit\'s empty result')
        self.assertEqual(m.r8(FLAGS), 0)
        self.assertNotIn(0x1A, m.messages)

    def test_cancellation_at_late_accept_and_post_boundaries_cannot_change_new_visit(self):
        api = self.img.length_lifecycle
        md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
        instructions = list(md.disasm(self.img.read(api['accept'], api['gui']-api['accept']), api['accept']))
        # Before commit, immediately after its atomic section, both queue
        # publication calls, and cleanup: these are distinct lifecycle seams.
        points = [0x08011A66, 0x08012178, 0x08012B86, 0x08012C06, 0x08012C14]
        for instruction in instructions:
            if instruction.mnemonic == 'bl' and instruction.op_str in ('#0x801c6d8', '#0x800e428'):
                points.append(instruction.address+4 if instruction.op_str == '#0x801c6d8' else instruction.address)
        # The optional REF header send is unreachable when no REF was dialled.
        points = sorted(set(points))
        reached = 0
        for point in points:
            with self.subTest(point=hex(point)):
                m = self.machine()
                try:
                    m.call(SEQUENCE, until=point, count=2_000_000)
                except RuntimeError as error:
                    if f'stopped at {STOP:#x}' in str(error):
                        continue
                    raise
                reached += 1
                self.back_and_reenter(m)
                snapshot = bytes(m.uc.mem_read(0x200002B8, 8))
                self.assertEqual(m.r8(FLAGS), 0)
                m.uc.emu_start(point | 1, STOP, count=2_000_000)
                self.assertEqual(m.uc.reg_read(UC_ARM_REG_PC), STOP)
                self.assertEqual(m.r8(FLAGS), 0, 'the old task replaced the new idle flag')
                self.assertEqual(bytes(m.uc.mem_read(0x200002B8, 8)), snapshot)
                self.assertEqual(m.uc.reg_read(UC_ARM_REG_SP), 0x2000E000)
        self.assertGreaterEqual(reached, 7)

    def test_result_and_reference_prepare_are_atomic_but_queue_calls_are_not(self):
        m = self.machine()
        depth, writes, queued = [0], [], []
        pending = self.img.length_ref_anytime['pending']
        nvp = 0x20000C78+0xA6
        m.w8(self.img.adj_target, 2)
        m.w8(pending, 1)
        m.w16(self.img.length_reference['ref'], 1200)

        def enter(machine):
            depth[0] += 1
            machine.ret(0)

        def leave(machine):
            self.assertGreater(depth[0], 0)
            depth[0] -= 1
            machine.ret(0)

        def send(machine):
            self.assertEqual(depth[0], 0, 'GUI queue calls must never run inside the commit critical section')
            queued.append(machine.arg(0))
            machine.messages.append(machine.arg(0))
            machine.ret(0)

        def write(uc, access, address, size, value, user):
            self.assertGreater(depth[0], 0, 'all accepted pair results must publish atomically')
            writes.append((address, size))

        def prepare_write(uc, access, address, size, value, user):
            self.assertGreater(depth[0], 0, 'REF solve and pending consumption belong to the same commit')

        m.handlers[0x0801C6B4], m.handlers[0x0801C6D8] = enter, leave
        m.handlers[0x0800E428] = send
        h = m.uc.hook_add(UC_HOOK_MEM_WRITE, write, begin=0x200002B8, end=0x200002BF)
        hn = m.uc.hook_add(UC_HOOK_MEM_WRITE, prepare_write, begin=nvp, end=nvp)
        hp = m.uc.hook_add(UC_HOOK_MEM_WRITE, prepare_write, begin=pending, end=pending)
        try:
            m.call(SEQUENCE, count=2_000_000)
        finally:
            m.uc.hook_del(h)
            m.uc.hook_del(hn)
            m.uc.hook_del(hp)
        self.assertEqual(writes, [(0x200002B8+pin*2, 2) for pin in range(4)])
        self.assertIn(0x1A, queued)
        self.assertIn(0x3D, queued)
        self.assertEqual(m.r8(pending), 0)
        self.assertEqual(depth[0], 0)

    def test_busy_diagnostic_after_reentry_cannot_timeout_the_new_visit(self):
        m = self.machine()
        m.busy = True
        self.suspend_first_wait(m)
        self.back_and_reenter(m)
        m.messages.clear()
        self.finish(m)
        self.assertEqual(m.r8(FLAGS), 0)
        self.assertEqual(m.lengths(), [0]*4)
        self.assertLessEqual(m.now, 250)
        self.assertNotIn(0x1A, m.messages)

    def test_cancellation_still_clears_its_own_flag_after_external_state_change(self):
        m = self.machine()
        m.cancel_after, m.busy = 50, True
        m.call(SEQUENCE)
        self.assertEqual(m.r8(STATE), 2)
        self.assertEqual(m.r8(FLAGS), 0)
        self.assertEqual(m.lengths(), [0]*4)

    def test_idle_sequence_command_cannot_touch_phy_or_new_screen(self):
        m = self.machine()
        self.event_call(m, SET_STATE, 2)
        m.messages.clear()
        m.call(SEQUENCE, count=2_000_000)
        self.assertEqual((m.run_index, m.power, m.messages), (-1, [], []))

    def test_new_measurement_invalidates_the_previous_result_notification(self):
        from thai.engine import Scene
        s = Scene(image=self.data, state=7)
        s.call(ENTER, 7)
        s.drain()
        generation = self.img.length_lifecycle['state']
        s.w16(0x200002B8, 1000, 1000, 1000, 1000)
        s.w8(FLAGS, 2)
        old = bytes(s.uc.mem_read(generation, 4))
        # Actual sequence begin, stopping before the first measurement/log.
        s.uc.reg_write(UC_ARM_REG_SP, 0x2000D000)
        s.uc.reg_write(UC_ARM_REG_LR, STOP | 1)
        s.uc.emu_start(SEQUENCE | 1, 0x080119F0, count=2_000_000)
        self.assertNotEqual(bytes(s.uc.mem_read(generation, 4)), old)
        before = [row[:] for row in s.fb]
        s.dispatch(0x1A, old)
        s.dispatch(0x3D, old)
        s.drain()
        self.assertEqual(s.fb, before)

    def test_start_queued_before_back_does_not_run_after_reentry(self):
        m, packets = self.start_queue()
        self.press(m, 4)
        self.assertEqual(len(packets), 1)
        original = packets[0]
        self.back_and_reenter(m)
        self.assertEqual(m.r8(FLAGS), 0)
        m.messages.clear()
        self.deliver(m, original)
        self.assertEqual(m.run_index, -1, 'the delayed old Start request began a diagnostic on the new visit')
        self.assertEqual(m.r8(FLAGS), 0)
        self.assertEqual(m.lengths(), [0]*4)

    def start_queue(self):
        m = self.machine()
        packets = []
        handle = 0x20003100
        m.uc.mem_write(0x20000070, struct.pack('<I', handle))
        m.handlers[0x08012FBC] = lambda machine: None  # Execute the actual network sender.

        def queue(machine):
            if machine.arg(0) == handle:
                packets.append(bytes(machine.uc.mem_read(machine.arg(1), 8)))
            machine.ret(1)

        m.handlers[0x0801CAA0] = queue
        # Actual screen entry makes the queued generation nonzero, so an
        # incorrectly retained inline word would cause an invalid free.
        self.event_call(m, ENTER, 7)
        packets.clear()
        return m, packets

    def deliver(self, m, packet, until=0x0801499E):
        m.uc.reg_write(UC_ARM_REG_SP, 0x2000C000)
        m.uc.mem_write(0x2000C010, packet)
        m.uc.emu_start(0x08014904 | 1, until, count=2_000_000)
        self.assertEqual(m.uc.reg_read(UC_ARM_REG_PC), until)
        self.assertEqual(m.uc.reg_read(UC_ARM_REG_SP), 0x2000C000)

    def test_current_queued_start_runs_without_allocating_or_freeing_inline_epoch(self):
        m, packets = self.start_queue()
        def no_heap(machine):
            self.fail('tagged Start must neither allocate nor free its inline epoch')
        m.handlers[0x0801C388] = m.handlers[0x0801C6F8] = no_heap
        self.press(m, 4)
        self.assertEqual(len(packets), 1)
        self.assertEqual(packets[0][0], 9)
        self.assertNotEqual(packets[0][4:], bytes(4))
        self.deliver(m, packets[0])
        self.assertEqual(m.run_index+1, 4)
        self.assertEqual(m.lengths(), [1000]*4)
        self.assertEqual(m.r8(FLAGS), 2)

    def test_reentry_after_queue_decode_but_before_sequence_start_is_rechecked(self):
        m, packets = self.start_queue()
        self.press(m, 4)
        self.deliver(m, packets[0], until=0x0801491A)
        self.assertEqual(bytes(m.uc.mem_read(0x2000C014, 4)), bytes(4))
        self.back_and_reenter(m)
        m.uc.emu_start(0x0801491A | 1, 0x0801499E, count=2_000_000)
        self.assertEqual(m.run_index, -1)
        self.assertEqual(m.r8(FLAGS), 0)
        self.assertEqual(m.lengths(), [0]*4)

    def test_non_length_network_command_preserves_original_dispatch(self):
        m, packets = self.start_queue()
        m.w8(FLAGS, 2)
        self.deliver(m, bytes((6, 0, 0, 0, 0, 0, 0, 0)))
        self.assertEqual(m.run_index, -1)
        self.assertEqual(m.r8(FLAGS), 2)
        self.assertEqual(m.power[-1][1], 1)


if __name__ == '__main__':
    unittest.main()
