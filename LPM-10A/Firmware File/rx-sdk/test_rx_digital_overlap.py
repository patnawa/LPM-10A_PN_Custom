"""Full interrupt-grid and ownership checks for overlapping Digital windows."""
import struct
import unittest

from unicorn import UC_HOOK_CODE
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_PC,
                               UC_ARM_REG_LR, UC_ARM_REG_PRIMASK)

import analog_feedback
import digital_overlap
import test_rx_robust
from test_rx_followup import ANALYZERS, GATE_STATE, REQUEST, TIM5
from test_scan_acquisition_timing import envelope, SAMPLE_INDEX, SUBSTEP, TIMER_COUNTER
from verify_control import MODE, SP
from verify_digital import ACTIVE, BUFFER


def candidate():
    # Isolate the acquisition change from the independent Digital algorithm.
    img = test_rx_robust.candidate()
    analog_feedback.apply(img)
    digital_overlap.apply(img)
    img.poke(0x08009E26, '3d4801210170',
             img.assemble_at(0x08009E26, 'bl overlap_rearm\nnop'),
             'test fixture: use overlap helper from the established detector')
    return img


class DigitalOverlap(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.img = candidate()
        cls.data = bytes(cls.img.data)

    cpu = test_rx_robust.Robust.cpu
    execute = test_rx_robust.Robust.execute
    boundary = test_rx_robust.Robust.boundary

    def test_initial48_then_three16_sample_windows_execute_every_irq(self):
        c = self.cpu()
        c.w8(GATE_STATE, 0)
        self.boundary(c)
        tick = 0
        reads = []
        retained = []
        def adc(uc, address, size, user):
            value = envelope(tick, 'legacy')
            reads.append((tick, c.read(SAMPLE_INDEX), value))
            uc.reg_write(UC_ARM_REG_R0, value)
            uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
        hook = c.uc.hook_add(UC_HOOK_CODE, adc, begin=0x080072A4, end=0x080072A4)
        try:
            for frame, count in enumerate((48, 16, 16, 16)):
                before = len(reads)
                origin = tick
                expected_ticks = 9620 if frame == 0 else 3200
                while c.read(ACTIVE) and tick-origin <= expected_ticks:
                    tick += 1
                    self.execute(c, TIM5, budget=4000)
                self.assertEqual((tick-origin, c.read(ACTIVE)), (expected_ticks, 0))
                events = reads[before:]
                self.assertEqual(len(events), count*5)
                start_index = 0 if frame == 0 else 32
                first_tick = origin+(140 if frame == 0 else 120)
                self.assertEqual([(r[0],r[1]) for r in events],
                                 [(first_tick+200*(i//5)+20*(i%5), start_index+i//5)
                                  for i in range(count*5)])
                values = [r[2] for r in events]
                reduced = [(sum(v)-min(v)-max(v))//3
                           for v in (values[i:i+5] for i in range(0,len(values),5))]
                actual = list(struct.unpack('<48H', c.uc.mem_read(BUFFER,96)))
                self.assertEqual(actual, retained+reduced)
                retained = actual[-32:]
                self.execute(c, ANALYZERS[0], budget=30000)
                self.assertEqual((c.read(ACTIVE), c.read(SAMPLE_INDEX)), (1, 32))
                self.assertEqual(list(struct.unpack('<32H',c.uc.mem_read(BUFFER,64))), retained)
        finally:
            c.uc.hook_del(hook)

    def test_sampler_cannot_write_until_retention_and_index_are_published(self):
        c = self.cpu()
        snapshot = SP-0x200
        values = list(range(1000,1048))
        c.uc.mem_write(snapshot,struct.pack('<48H',*values))
        c.uc.mem_write(BUFFER,bytes(96))
        c.w8(ACTIVE,0)
        c.w8(SAMPLE_INDEX,0)
        observed = []
        def watch(uc,address,size,user):
            if digital_overlap.HELPER <= address < digital_overlap.HELPER+32:
                if c.read(ACTIVE):
                    self.assertEqual(c.read(SAMPLE_INDEX),32)
                    self.assertEqual(list(struct.unpack('<32H',c.uc.mem_read(BUFFER,64))),values[16:])
                observed.append(address)
        hook=c.uc.hook_add(UC_HOOK_CODE,watch)
        try:
            self.execute(c,digital_overlap.HELPER,BUFFER+96,snapshot+96)
        finally:
            c.uc.hook_del(hook)
        self.assertGreater(len(observed),100)
        self.assertEqual((c.read(ACTIVE),c.read(SAMPLE_INDEX)),(1,32))
        self.assertEqual(bytes(c.uc.mem_read(snapshot,96)),struct.pack('<48H',*values))

    def test_mode_or_gate_transition_requires_a_fresh_full_window(self):
        for request,gate in ((1,2),(2,2),(3,2),(0,0)):
            c=self.cpu()
            c.w8(ACTIVE,1)
            c.w8(SAMPLE_INDEX,39)
            c.w8(SUBSTEP,8)
            c.w8(REQUEST,request)
            c.w8(GATE_STATE,gate)
            self.boundary(c)
            self.assertEqual(c.read(SAMPLE_INDEX),0)
            self.assertEqual(c.read(SUBSTEP),0)
            self.assertEqual(c.read(ACTIVE),1)

    def test_each_helper_boundary_survives_real_timer_preemption(self):
        for point in range(digital_overlap.HELPER,digital_overlap.HELPER+32,2):
            c=self.cpu()
            snapshot=SP-0x200
            values=list(range(1000,1048))
            c.uc.mem_write(snapshot,struct.pack('<48H',*values))
            c.w8(ACTIVE,0)
            c.w8(SAMPLE_INDEX,0)
            c.w8(SUBSTEP,1)
            c.w32(TIMER_COUNTER,0)
            fired=[]
            def interrupt(uc,address,size,user):
                if address != point or fired: return
                fired.append(address)
                context=uc.context_save()
                self.execute(c,TIM5,stack=SP-0x500,budget=4000)
                uc.context_restore(context)
            hook=c.uc.hook_add(UC_HOOK_CODE,interrupt)
            try:
                self.execute(c,digital_overlap.HELPER,BUFFER+96,snapshot+96)
            finally:
                c.uc.hook_del(hook)
            self.assertEqual(len(fired),1)
            self.assertEqual((c.read(ACTIVE),c.read(SAMPLE_INDEX)),(1,32))
            self.assertEqual(list(struct.unpack('<32H',c.uc.mem_read(BUFFER,64))),values[16:])


if __name__ == '__main__':
    unittest.main()
