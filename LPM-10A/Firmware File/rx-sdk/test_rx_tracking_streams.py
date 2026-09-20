"""Continuous TIM5/foreground ownership audit of the exact PN 1.11 image.

Every TIM5 interrupt, including non-sampling ticks, executes the shipped ARM
code. Only ADC conversion/analogue propagation and interrupt arrival times are
modeled. Timer arrivals during analysis are adversarial schedules, not a CPU
cycle or interrupt-latency model. The envelope uses the independently derived
nominal TX 101 us tick / 50-tick B6 chip and RX 25.015625 us timer tick.
"""
import hashlib
from collections import Counter
import math
from pathlib import Path
import struct
import sys
import unittest

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE
from unicorn.arm_const import (UC_ARM_REG_C1_C0_2, UC_ARM_REG_FPEXC,
    UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_SP, UC_ARM_REG_LR,
    UC_ARM_REG_PC, UC_ARM_REG_PRIMASK)

from lpm10rx.image import assemble
import digital_tracking
import test_rx_followup as followup
from sampling_fixes import PUBLISH_GATE
from test_rx_followup import GATE_STATE, GRADE, KEY, REQUEST
from test_rx_pinpoint import expected_gap
from test_rx_robust import _FastControl
from test_scan_acquisition_timing import SAMPLE_INDEX, SUBSTEP, TIMER_COUNTER
from verify_control import Control, MODE, SP, STOP
from verify_digital import ACTIVE, BUFFER, GATE, RECENT

sys.path.insert(0, str(Path(__file__).resolve().parents[3]/'docs'/'experiments'))
import digital_acquisition_candidate as reference

SHA256 = '3e39ae56832cf92881ffdc46564e293278d6c3f1b55a9832b7a9a8350f031828'
BATCH = STOP+0x100
ADC = 0x080072A4
CODE = (1, 0, 1, 1, 0, 1, 1, 0)


class StreamCPU(Control):
    """Same MMIO stubs as established tests; sparse hooks keep long runs cheap."""
    def __init__(self, data):
        self.uc = uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
        for base, size in ((0x08000000, 0x20000), (0x20000000, 0x10000),
                           (0x40000000, 0x30000), (STOP, 0x1000)):
            uc.mem_map(base, size)
        uc.mem_write(0x08006800, data)
        self.pressed, self.gpio, self.calls = set(), {}, []
        self.pending = True
        for address in _FastControl.MOCK_ENTRIES:
            uc.hook_add(UC_HOOK_CODE, self.hook, begin=address, end=address)
        uc.reg_write(UC_ARM_REG_C1_C0_2, 0xF00000)
        uc.reg_write(UC_ARM_REG_FPEXC, 0x40000000)
        uc.mem_write(BATCH, assemble(BATCH, '''
            push {r4,r5,r6,lr}
            mov r4,r0
            ldr r5,=0x0800AC1D
        loop:
            blx r5
            subs r4,#1
            bne loop
            pop {r4,r5,r6,pc}
            .pool
        ''', {}))
        self.w16(GATE, 580)
        self.w16(GATE+2, 1)
        self.w8(GATE_STATE, 0)
        self.events, self.reduced, self.pending_reads = [], [], []
        self.amplitude = lambda tick: 300
        self.phase = 0.0
        self.ratio = 1.0
        self.glitch = False
        uc.hook_add(UC_HOOK_CODE, self.adc, begin=ADC, end=ADC)

    def adc(self, uc, address, size, user):
        tick = self.read(TIMER_COUNTER, 4)
        # Integer TIM2 ticks account for TX gate update quantization. The ratio
        # parameter is optional clock stress, not a measured oscillator error.
        tx_tick = math.floor(tick*25.015625*self.ratio/101 + self.phase*50)
        value = 1000 + self.amplitude(tick)*CODE[(tx_tick//50) % 8]
        if self.glitch and len(self.events) % 107 in (2, 3):
            value = 4095
        value = max(0, min(4095, int(value)))
        index = self.read(SAMPLE_INDEX)
        self.events.append((tick, index, value))
        self.pending_reads.append(value)
        if len(self.pending_reads) == 5:
            vals = self.pending_reads
            self.reduced.append((sum(vals)-min(vals)-max(vals))//3)
            self.pending_reads = []
        uc.reg_write(UC_ARM_REG_R0, value)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))


class TrackingStreams(unittest.TestCase):
    execute = followup.Followup.execute
    boundary = followup.Followup.boundary

    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1]/'experimental/APP_LPM-10RX_PN1.11-tracking.bin'
        cls.data = path.read_bytes()
        if hashlib.sha256(cls.data).hexdigest() != SHA256:
            raise AssertionError('stream audit requires the exact delivered PN 1.11 artifact')
        cls.results = {}

    def cpu(self, phase=0, ratio=1, glitch=False):
        c = StreamCPU(self.data)
        c.phase, c.ratio, c.glitch = phase, ratio, glitch
        self.boundary(c)
        return c

    def timers(self, c, count):
        if not count:
            return
        before = c.read(TIMER_COUNTER, 4)
        self.execute(c, BATCH, count, stack=SP-0x500, budget=count*100+100)
        self.assertEqual(c.read(TIMER_COUNTER, 4), (before+count) & 0xffffffff)

    def complete(self, c):
        """Advance only actual interrupts until acquisition stops."""
        for _ in range(50):
            if not c.read(ACTIVE):
                return
            self.timers(c, 200)
        self.fail('complete Digital frame not acquired within 10,000 IRQs')

    def words(self, c):
        return list(struct.unpack('<48H', c.uc.mem_read(BUFFER, 96)))

    def analyze(self, c, injection=None, count=0, event=None, occurrence=1):
        """Pause/resume real main code, restoring a preempted register context."""
        seen, score = [], []
        visits = 0
        def stop(uc, address, size, user):
            nonlocal visits
            if address == injection and not seen:
                visits += 1
                if visits != occurrence:
                    return
                self.assertEqual(uc.reg_read(UC_ARM_REG_PRIMASK), 0)
                seen.append(address)
                uc.emu_stop()
        def metric(uc, address, size, user):
            score.append(uc.reg_read(UC_ARM_REG_R0))
        hooks = [c.uc.hook_add(UC_HOOK_CODE, metric,
                    begin=digital_tracking.robust_fixes.GAP_HELPER,
                    end=digital_tracking.robust_fixes.GAP_HELPER)]
        if injection is not None:
            hooks.append(c.uc.hook_add(UC_HOOK_CODE, stop,
                                      begin=injection, end=injection))
        c.uc.reg_write(UC_ARM_REG_SP, SP)
        c.uc.reg_write(UC_ARM_REG_LR, STOP | 1)
        try:
            c.uc.emu_start(digital_tracking.DETECTOR | 1, STOP, count=30000)
            if seen:
                pc = c.uc.reg_read(UC_ARM_REG_PC)
                context = c.uc.context_save()
                if event:
                    event(c)
                self.timers(c, count)
                c.uc.context_restore(context)
                c.uc.emu_start(pc | 1, STOP, count=30000)
            self.assertEqual(c.uc.reg_read(UC_ARM_REG_PC), STOP)
            self.assertEqual(c.uc.reg_read(UC_ARM_REG_SP), SP)
        finally:
            for hook in hooks:
                c.uc.hook_del(hook)
        if injection is not None:
            self.assertEqual(seen, [injection], hex(injection))
        return score

    def expected(self, samples, previous):
        result = reference.measure(samples)
        amplitude = result['amplitude']
        if amplitude is None:
            return result['gap'], []
        score = 29*amplitude - 12*(29*amplitude//46)
        return expected_gap(score, previous, 800), [score]

    def test_long_full_grid_streams_follow_raw_read_oracle_through_motion_and_dropout(self):
        totals = {'frames': 0, 'timer_irqs': 0, 'adc_reads': 0,
                  'local_fit': 0, 'established': 0, 'rejected': 0, 'uncertain': 0}
        for phase, ratio, glitch in ((0,1,False), (0.3125,1,False),
                                     (3.875,1.003,True), (7.75,0.997,True)):
            c = self.cpu(phase, ratio, glitch)
            c.amplitude = lambda tick: (300,1000,60,0,300)[min(4, tick//25600)]
            previous = 0
            for frame in range(40):
                with self.subTest(phase=phase, ratio=ratio, frame=frame):
                    self.complete(c)
                    raw = self.words(c)
                    self.assertEqual(raw, c.reduced[-48:])
                    self.assertEqual(c.pending_reads, [])
                    wanted, scores = self.expected(raw, previous)
                    self.assertEqual(self.analyze(c), scores)
                    self.assertEqual(c.read(GRADE), wanted)
                    self.assertEqual(self.words(c)[:32], raw[-32:])
                    self.assertEqual((c.read(ACTIVE), c.read(SAMPLE_INDEX)), (1,32))
                    previous = wanted
                    totals['frames'] += 1
                    totals[reference.measure(raw)['reason']] += 1
            totals['timer_irqs'] += c.read(TIMER_COUNTER,4)
            totals['adc_reads'] += len(c.events)
        self.assertGreater(totals['local_fit'], 50)
        self.assertGreater(totals['rejected'], 5)
        self.assertGreater(totals['established'], 0)
        self.__class__.results['long_streams'] = totals

    def test_analysis_snapshot_and_all_dsp_stages_survive_next_window_completion(self):
        # Phase 5/16 reliably exercises the inherited global fallback. The
        # latest window may complete before analysis resumes: ACTIVE must stay
        # zero and its data must be preserved for the next foreground call.
        points = ((0, 0x08009E1C), (0, digital_tracking.REARM),
                  (0, digital_tracking.LOCAL), (0, digital_tracking.SORT),
                  (0.3125, digital_tracking.UNTAG),
                  (0, digital_tracking.ESTIMATOR))
        rows = []
        for phase, point in points:
            for count in (1, 139, 3217):
                c = self.cpu(phase)
                self.complete(c)
                raw = self.words(c)
                before = len(c.reduced)
                wanted, scores = self.expected(raw, 0)
                self.assertEqual(self.analyze(c, point, count), scores)
                self.assertEqual(c.read(GRADE), wanted)
                self.assertEqual(self.words(c)[:32], raw[-32:])
                self.complete(c)
                fresh = self.words(c)
                self.assertEqual(fresh, raw[-32:]+c.reduced[before:])
                self.assertEqual(len(c.reduced)-before,16)
                wanted2, scores2 = self.expected(fresh, wanted)
                self.assertEqual(self.analyze(c), scores2)
                self.assertEqual(c.read(GRADE), wanted2)
                rows.append((point,count))
        self.__class__.results['preempted_stages'] = len(rows)

    def test_every_executed_dsp_instruction_boundary_preserves_snapshot_and_retention(self):
        ranges = ((digital_tracking.DETECTOR,digital_tracking.PUBLISH),
                  (digital_tracking.REARM,digital_tracking.REARM+32),
                  (digital_tracking.LOCAL,digital_tracking.LOCAL_END),
                  (digital_tracking.ESTIMATOR,digital_tracking.ESTIMATOR_END))
        totals = {'schedules':0,'instruction_addresses':0,'last_loop_visits':0}
        for phase in (0,0.3125):
            template=self.cpu(phase)
            self.complete(template)
            raw=self.words(template)
            memory=bytes(template.uc.mem_read(0x20000000,0x3000))
            points=Counter()
            def trace(uc,address,size,user):
                if any(lo <= address < hi for lo,hi in ranges):
                    self.assertEqual(uc.reg_read(UC_ARM_REG_PRIMASK),0)
                    points[address] += 1
            hook=template.uc.hook_add(UC_HOOK_CODE,trace)
            self.analyze(template)
            template.uc.hook_del(hook)
            wanted,scores=self.expected(raw,0)
            self.assertGreater(len(points),130)
            for point,visits in points.items():
                for occurrence in sorted({1,visits}):
                    with self.subTest(phase=phase,point=hex(point),occurrence=occurrence):
                        c=self.cpu(phase)
                        c.uc.mem_write(0x20000000,memory)
                        # Restart from a real fully acquired immutable frame;
                        # only future raw events matter to the retention oracle.
                        c.events=[]
                        c.reduced=[]
                        c.pending_reads=[]
                        actual=self.analyze(c,point,3217,occurrence=occurrence)
                        self.assertEqual(actual,scores)
                        self.assertEqual(c.read(GRADE),wanted)
                        self.assertEqual(self.words(c)[:32],raw[-32:])
                        self.assertLessEqual(len(c.reduced),16)
                        self.assertEqual(self.words(c)[32:32+len(c.reduced)],c.reduced)
                        self.assertEqual(self.words(c)[32+len(c.reduced):],
                                         raw[32+len(c.reduced):])
                        self.assertEqual(c.read(ACTIVE),0 if len(c.reduced)==16 else 1)
                        totals['schedules'] += 1
                        totals['last_loop_visits'] += occurrence > 1
            totals['instruction_addresses'] += len(points)
        self.__class__.results['instruction_boundary_sweep']=totals

    def test_real_gate_and_key_events_discard_preempted_retention_then_take_full48(self):
        def close_open(c):
            self.execute(c,PUBLISH_GATE,0,stack=SP-0x500)
            self.execute(c,PUBLISH_GATE,580,stack=SP-0x500)
            self.assertEqual(c.read(GATE_STATE),0)
        def analog_key(c):
            c.w16(0x2000010E,6)
            self.execute(c,KEY,stack=SP-0x500)
            self.assertEqual(c.read(REQUEST),2)
        rows = []
        for point in (0x08009E1C, digital_tracking.REARM, digital_tracking.LOCAL,
                      digital_tracking.SORT, digital_tracking.ESTIMATOR):
            for kind,event in (('gate',close_open),('key',analog_key)):
                c=self.cpu()
                self.complete(c)
                self.analyze(c,point,400,event)
                self.boundary(c)
                if kind == 'key':
                    self.assertEqual(c.read(MODE),1)
                    # Actual second key release returns to Digital. No Analog
                    # sampling occurs between requests in this ownership test.
                    c.w16(0x2000010E,6)
                    self.execute(c,KEY,stack=SP-0x500)
                    self.boundary(c)
                self.assertEqual((c.read(MODE),c.read(ACTIVE),c.read(SAMPLE_INDEX),
                                  c.read(SUBSTEP),c.read(GRADE),c.read(RECENT,2)),
                                 (0,1,0,0,0,0))
                # Discard only the oracle's partial ADC group at the exact
                # boundary where firmware invalidates its own partial group.
                c.pending_reads=[]
                origin=len(c.reduced)
                before=len(c.events)
                c.amplitude=lambda tick: 60
                self.timers(c,9200)
                self.assertEqual(c.read(ACTIVE),1)
                self.assertEqual(self.analyze(c),[])
                self.assertEqual(c.read(GRADE),0)
                self.complete(c)
                self.assertEqual(len(c.events)-before,240)
                self.assertEqual(len(c.reduced)-origin,48)
                raw=self.words(c)
                self.assertEqual(raw,c.reduced[origin:])
                wanted,scores=self.expected(raw,0)
                self.assertGreater(wanted,1)
                self.assertEqual(self.analyze(c),scores)
                self.assertEqual(c.read(GRADE),wanted)
                rows.append((point,kind))
        self.__class__.results['fresh_reacquisitions'] = len(rows)


if __name__ == '__main__':
    unittest.main()
