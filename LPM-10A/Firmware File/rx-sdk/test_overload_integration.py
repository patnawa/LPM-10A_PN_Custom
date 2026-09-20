"""PN 1.12 full-profile regression and actual TIM5/foreground/audio handoff.

ADC values and interrupt arrivals are modeled. Tests execute the new complete
profile; they do not establish physical saturation thresholds or cable identity.
"""
from collections import Counter
import struct
import unittest

from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_PC, UC_ARM_REG_LR

import digital_upper_rail
import overload_fixes
import test_tracking_integration as base
import test_rx_tracking_streams as streams
from test_rx_followup import GRADE, SPEAKER
from verify_control import BEEP
from verify_digital import ACTIVE, BUFFER, GAP, RECENT


def candidate():
    img=base.candidate()
    overload_fixes.apply(img)
    return img


def setup(cls):
    base.setup(cls)
    overload_fixes.apply(cls.img)
    cls.data=bytes(cls.img.data)
    cls.results={}


class OverloadAnalog(base.TrackingAnalog):
    setUpClass=classmethod(setup)


class OverloadDigital(base.TrackingDigital):
    setUpClass=classmethod(setup)


class OverloadOverlap(base.TrackingOverlap):
    setUpClass=classmethod(setup)


class OverloadRaces(base.TrackingRaces):
    setUpClass=classmethod(setup)


class OverloadControl(base.TrackingControl):
    setUpClass=classmethod(setup)


class ScriptedADC(streams.StreamCPU):
    """Replay each specified ADC level for five actual conversion calls."""
    def __init__(self,data,tail=4095):
        super().__init__(data)
        self.samples=[1000+3000*streams.CODE[i%8] for i in range(32)]+[tail]*64

    def adc(self,uc,address,size,user):
        index=len(self.events)//5
        value=self.samples[min(index,len(self.samples)-1)]
        self.events.append((self.read(streams.TIMER_COUNTER,4),
                            self.read(streams.SAMPLE_INDEX),value))
        self.pending_reads.append(value)
        if len(self.pending_reads)==5:
            vals=self.pending_reads
            self.reduced.append((sum(vals)-min(vals)-max(vals))//3)
            self.pending_reads=[]
        uc.reg_write(UC_ARM_REG_R0,value)
        uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))


class OverloadStreams(streams.TrackingStreams):
    setUpClass=classmethod(setup)

    def clipped_cpu(self,tail=4095):
        c=ScriptedADC(self.data,tail)
        self.boundary(c)
        self.complete(c)
        self.assertEqual(self.words(c),c.samples[:48])
        return c

    def test_actual_raw_acquisition_reports_uncertainty_then_releases_without_new_code(self):
        c=self.clipped_cpu()
        self.assertEqual(self.analyze(c),[])
        self.assertEqual((c.read(GRADE),c.read(RECENT,2)),(1,800))
        self.assertEqual((c.read(ACTIVE),c.read(streams.SAMPLE_INDEX)),(1,32))
        self.execute(c,SPEAKER)
        self.assertEqual(c.read(BEEP),100)
        self.assertEqual(c.read(GAP),160)
        self.complete(c)
        fresh=self.words(c)
        self.assertEqual(fresh,c.samples[16:64])
        self.assertEqual(self.analyze(c),[])
        self.assertEqual(c.read(GRADE),0)
        # Rejection prevents repeats but never truncates an active pulse.
        for tick in range(100):
            c.run()
            self.execute(c,SPEAKER)
        self.assertEqual(c.read(BEEP),0)
        for _ in range(200):
            c.run()
            self.execute(c,SPEAKER)
            self.assertEqual(c.read(BEEP),0)

    def test_each_new_helper_instruction_survives_next_window_completion(self):
        schedules=0
        covered=set()
        for tail in (4095,4094):
            template=self.clipped_cpu(tail)
            points=Counter()
            def trace(uc,address,size,user):
                if any(lo <= address < lo+size for lo,size in digital_upper_rail.PADDING):
                    points[address]+=1
            hook=template.uc.hook_add(UC_HOOK_CODE,trace)
            self.analyze(template)
            template.uc.hook_del(hook)
            self.assertGreater(len(points),8)
            covered.update(points)
            for point,visits in points.items():
                for occurrence in sorted({1,visits}):
                    c=self.clipped_cpu(tail)
                    raw=self.words(c)
                    wanted,scores=(1,[]) if tail==4095 else self.expected(raw,0)
                    self.assertEqual(self.analyze(c,point,3217,occurrence=occurrence),scores)
                    self.assertEqual((c.read(GRADE),c.read(RECENT,2)),(wanted,800))
                    self.assertEqual(c.read(ACTIVE),0)
                    self.assertEqual(self.words(c),raw[16:]+[tail]*16)
                    self.assertEqual(struct.unpack('<32H',c.uc.mem_read(BUFFER,64)),tuple(raw[16:]))
                    self.assertEqual(self.analyze(c),[])
                    self.assertEqual(c.read(GRADE),0)
                    schedules+=1
        self.assertTrue({0x0800A042,0x0800A044,0x0800B576} <= covered)
        self.__class__.results['upper_helper_preemptions']=schedules


if __name__=='__main__':unittest.main()
