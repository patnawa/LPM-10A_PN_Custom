"""Independent audio-clock integration over exact PN1.12 + proposed patch.

Real TIM5/TIM1 handlers, detector, key scanner, publisher and PWM instructions
execute. ADC input and IRQ scheduling are synthetic; no hardware-cause claim.
The prior pinned release-audit module remains unchanged.
"""
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import random
import struct
import unittest
from unittest import mock

from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm_const import (UC_ARM_REG_LR, UC_ARM_REG_PC,
    UC_ARM_REG_PRIMASK, UC_ARM_REG_SP)

import test_rx_digital_release_audit as release
import test_rx_analog_fast as analog
import test_rx_followup as followup
import test_rx_robust as robust
import test_rx_tracking_fragments as fragments
import test_rx_tracking_streams as streams
from lpm10rx.image import Image
from test_rx_followup import GATE_STATE, GRADE, KEY, REQUEST, TIM5
from verify_control import BEEP, MODE, SP, STOP
from verify_digital import ACTIVE, BUFFER, GAP, RECENT

PARENT=Path(__file__).resolve().parents[1]/'experimental/APP_LPM-10RX_PN1.12-overload.bin'
CODE=streams.CODE


class AudioClockIntegration(unittest.TestCase):
    execute=followup.Followup.execute
    boundary=followup.Followup.boundary
    timers=streams.TrackingStreams.timers
    detect=robust.Robust.detect
    run_stream=release.ReleaseAudit.run_stream

    @classmethod
    def setUpClass(cls):
        import audio_clock_fixes
        cls.previous=PARENT.read_bytes()
        if hashlib.sha256(cls.previous).hexdigest()!=release.SHA256:
            raise AssertionError('integration requires exact PN1.12 predecessor')
        cls.img=Image(str(PARENT));audio_clock_fixes.apply(cls.img)
        cls.data=bytes(cls.img.data)
        delivered=PARENT.with_name('APP_LPM-10RX_PN1.13-audio-clock.bin').read_bytes()
        if delivered!=cls.data:
            raise AssertionError('PN1.13 artifact differs from exact-parent in-memory build')
        cls.results={'parent_sha256':release.SHA256,
            'candidate_sha256':hashlib.sha256(cls.data).hexdigest()}

    def cpu(self,data=None,mode=0):
        c=streams.StreamCPU(self.data if data is None else data)
        c.w8(GATE_STATE,2);c.w8(MODE,mode)
        return c

    def clock_audio(self,c,duration_ms,*,timer1_cycles=release.T1_CYCLES):
        """Capture actual PWM edges while clocking every real TIM5 IRQ."""
        origin=c.read(streams.TIMER_COUNTER,4)*release.T5_CYCLES
        end=origin+round(duration_ms*64000)
        now=origin
        sound=c.read(release.PWM,2) in (700,900)
        edges=[]
        def pwm(uc,access,address,size,value,user):
            nonlocal sound
            active=value!=800
            if active!=sound:
                tick=c.read(streams.TIMER_COUNTER,4)
                edges.append(((tick*release.T5_CYCLES-origin)/64000,active))
                sound=active
        hook=c.uc.hook_add(UC_HOOK_MEM_WRITE,pwm,begin=release.PWM,end=release.PWM+1)
        # A pulse may already have translated the PWM write block. Unicorn's
        # bounded memory hook must be present when that block is translated;
        # otherwise an already cached block can hide later physical writes.
        c.uc.ctl_remove_cache(0x0800B364,0x0800B382)
        next1=(origin//timer1_cycles+1)*timer1_cycles if timer1_cycles else end
        try:
            while now<end:
                target=min(next1,end)
                self.timers(c,target//release.T5_CYCLES-c.read(streams.TIMER_COUNTER,4))
                now=target
                if timer1_cycles and target==next1:
                    self.execute(c,release.TIM1,stack=SP-0x500,budget=4000)
                    next1+=timer1_cycles
        finally:c.uc.hook_del(hook)
        return {'edges':edges,'sound':sound,'beep':c.read(BEEP),'gap':c.read(GAP)}

    def assert_one_pulse(self,result,ticks):
        self.assertFalse(result['sound'])
        self.assertEqual(result['beep'],0)
        self.assertEqual([on for _,on in result['edges']],[True,False])
        width=result['edges'][1][0]-result['edges'][0][0]
        nominal=ticks*40*release.T5_CYCLES/64000
        self.assertGreaterEqual(width,nominal-1.01)
        self.assertLessEqual(width,nominal+0.21)
        return width

    def test_normal_uncertain_analog_and_actual_key_pulses_ignore_timer1_rate(self):
        rows=[]
        clocks=(release.T1_CYCLES//2,release.T1_CYCLES,release.T1_CYCLES*10,None)
        for mode in (0,1):
            for uncertain in (False,True):
                for phase in (0,19,39):
                    for clock in clocks:
                        c=self.cpu(mode=mode)
                        c.w32(streams.TIMER_COUNTER,phase)
                        c.w8(GRADE,1 if uncertain else 30);c.w16(RECENT,800)
                        c.w8(ACTIVE,2)
                        # Schedule once through the actual speaker IRQ; then
                        # a fresh rejected result disallows another pulse.
                        self.timers(c,8-phase%8)
                        expected=100 if uncertain else 30
                        self.assertGreater(c.read(BEEP),0)
                        c.w8(GRADE,0)
                        # Capture starts from an already audible pulse.
                        before=c.read(streams.TIMER_COUNTER,4)
                        result=self.clock_audio(c,expected+5,timer1_cycles=clock)
                        self.assertFalse(result['sound'],(mode,uncertain,phase,clock,result,c.read(BEEP)))
                        self.assertEqual(result['beep'],0)
                        self.assertEqual([on for _,on in result['edges']],[False])
                        duration=result['edges'][0][0]
                        nominal=expected*40*release.T5_CYCLES/64000
                        self.assertGreaterEqual(duration,nominal-1.01)
                        self.assertLessEqual(duration,nominal+0.21)
                        rows.append((mode,uncertain,phase,clock,duration))
        keys=[]
        for mode in (0,1,2):
            for held in (0x2000010E,0x20000110,0x20000112):
                for clock in clocks:
                    c=self.cpu(mode=mode);c.w8(ACTIVE,2)
                    c.w16(held,6)
                    self.execute(c,KEY)
                    self.assertEqual(c.read(BEEP),100)
                    result=self.clock_audio(c,105,timer1_cycles=clock)
                    keys.append(self.assert_one_pulse(result,100))
        self.__class__.results['pulse_matrix']={'tone_cases':len(rows),'key_cases':len(keys),
            'tone_remaining_ms_range':[min(r[-1] for r in rows),max(r[-1] for r in rows)],
            'key_width_ms_range':[min(keys),max(keys)]}

    def test_mains_actual_analyzer_and_legacy_pulse_lengths_remain_bounded(self):
        rows=[]
        for amplitude in (180,300,1800):
            samples=[round(2048+amplitude*math.cos(2*math.pi*5*i/64))
                     for i in range(64)]
            initial=[]
            for data in (self.previous,self.data):
                c=self.cpu(data,mode=2)
                c.uc.mem_write(BUFFER,struct.pack('<64H',*samples));c.w8(ACTIVE,0)
                self.execute(c,followup.ANALYZERS[2])
                initial.append((c.read(BEEP),c.read(GAP)))
            self.assertEqual(initial[0],initial[1])
            self.assertGreater(initial[1][0],0,(amplitude,initial))
            c.w8(ACTIVE,2)
            result=self.clock_audio(c,initial[1][0]+5,timer1_cycles=None)
            width=self.assert_one_pulse(result,initial[1][0])
            rows.append({'amplitude':amplitude,'beep_ticks':initial[1][0],'width_ms':width})
        self.__class__.results['mains_pulses']=rows

    def test_actual_boot_confirmation_is100_ticks_on_audio_clock(self):
        rows=[]
        for clock in (release.T1_CYCLES,release.T1_CYCLES*10,None):
            c=self.cpu()
            c.uc.reg_write(UC_ARM_REG_SP,SP)
            # Execute the actual startup BEEP=100 / initialAnalog-mode stores;
            # hardware NVIC enabling itself is outside this timing harness.
            c.uc.emu_start(0x0800B8C7,0x0800B8DE,count=100)
            self.assertEqual((c.read(BEEP),c.read(MODE)),(100,1))
            c.w8(ACTIVE,2)
            result=self.clock_audio(c,105,timer1_cycles=clock)
            rows.append(self.assert_one_pulse(result,100))
        self.__class__.results['boot_confirmation_width_ms']=rows

    def test_no_double_decrement_and_gap_transition_match_old_order(self):
        for mode in (0,1,2):
            c=self.cpu(mode=mode);c.w8(ACTIVE,2)
            c.w8(BEEP,2);c.w8(GAP,3);c.w16(RECENT,800)
            for _ in range(10):self.execute(c,release.TIM1,budget=4000)
            self.assertEqual((c.read(BEEP),c.read(GAP),c.read(RECENT,2)),(2,3,790))
            observed=[]
            for _ in range(4):
                self.timers(c,40)
                observed.append((c.read(BEEP),c.read(GAP)))
            self.assertEqual(observed,[(1,3),(0,2),(0,1),(0,0)])

    def test_clean_loss_and_missing_timer1_cap_continuous_pulses(self):
        rows=[]
        for amplitude in (300,3095):
            for phase in (0,0.5,3,7):
                row=self.run_stream(amplitude=amplitude,phase=phase,loss_ms=600,post_ms=500)
                self.assertFalse(row['final_sound'])
                self.assertEqual(row['final_grade'],0)
                self.assertLess(row['last_sound_end_ms'],350)
                rows.append(row)
        frozen=[]
        for amplitude,loss in ((300,700),(3095,520)):
            row=self.run_stream(amplitude=amplitude,phase=.5,loss_ms=loss,post_ms=1500,
                                timer1_stall=(loss,loss+1000))
            self.assertFalse(row['final_sound'])
            self.assertEqual(row['final_grade'],0)
            self.assertLess(row['last_sound_end_ms'],350)
            widths=[];start=None
            for t,on in row['pwm_edges']:
                if on:start=t
                elif start is not None:widths.append(t-start);start=None
            self.assertLessEqual(max(widths),100.3)
            frozen.append(row)
        self.__class__.results['clean_loss']=rows
        self.__class__.results['withheld_tim1']=frozen

    def test_real_sampling_loss_and_reacquisition_remain_identical(self):
        parent_streams=streams.StreamCPU
        class ScriptedEnvelope(parent_streams):
            def adc(self,uc,address,size,user):
                self.amplitude=lambda tick: 300 if (
                    tick*release.T5_CYCLES<600*64000
                    or tick*release.T5_CYCLES>=1000*64000) else 0
                return super().adc(uc,address,size,user)
        rows=[]
        for phase in (0,0.5):
            answers=[]
            for data in (self.previous,self.__class__.data):
                original=self.data;self.data=data
                try:
                    # Only the synthetic ADC envelope changes, never firmware
                    # or another test module's source. Restore after each run.
                    with mock.patch.object(streams,'StreamCPU',ScriptedEnvelope):
                        row=self.run_stream(phase=phase,amplitude=300,loss_ms=600,post_ms=1000)
                finally:self.data=original
                answers.append(row)
            self.assertEqual(answers[0]['publications'],answers[1]['publications'])
            self.assertEqual(answers[0]['adc_reads'],answers[1]['adc_reads'])
            self.assertEqual(answers[0]['timer_irqs'],answers[1]['timer_irqs'])
            new=answers[1]
            self.assertTrue(any(not p['grade'] and 800<p['ms']<1000 for p in new['publications']))
            reacquired=[p['ms'] for p in new['publications'] if p['ms']>=1000 and p['grade']]
            self.assertTrue(reacquired)
            # A resumed signal can arrive just after an overlap publication;
            # full48-sample observation plus one16-sample scheduling phase is
            # up to about320ms. The exact parent comparison above is primary.
            self.assertLess(reacquired[0]-1000,321.5)
            self.assertTrue(any(on and t>=reacquired[0] for t,on in new['pwm_edges']))
            rows.append({'phase':phase,'adc_reads':new['adc_reads'],
                         'timer_irqs':new['timer_irqs'],'reacquired_after_ms':reacquired[0]-1000})
        self.__class__.results['loss_reacquisition']=rows

    def test_all_fragment_geometry_and_static_strength_outputs_unchanged(self):
        old,new=self.cpu(self.previous),self.cpu()
        count=0
        rows=list(fragments.fragment_vectors())
        rng=random.Random(113)
        rows += [(('random',i),[rng.randrange(4096) for _ in range(48)]) for i in range(256)]
        for label,samples in rows:
            states=[]
            for c in (old,new):
                self.detect(c,samples,recent=560,grade=0)
                states.append((c.read(GRADE),c.read(RECENT,2),c.read(ACTIVE),
                               bytes(c.uc.mem_read(BUFFER,64))))
            self.assertEqual(*states,label)
            count+=1
        self.__class__.results['unchanged_geometry_vectors']=count

    def test_actual_key_preemption_cannot_be_overwritten_by_countdown(self):
        lo,hi=0x0800A9D4,0x0800AA1E
        def ready(mode,beep):
            c=self.cpu(mode=mode);c.w8(ACTIVE,2)
            c.w8(BEEP,beep);c.w8(GAP,7);c.w32(streams.TIMER_COUNTER,39)
            return c
        rows=0;masked=0
        for mode in (0,1,2):
            for beep in (1,30,100):
                c=ready(mode,beep);points={}
                def trace(uc,address,size,user):
                    if lo<=address<hi:points[address]=uc.reg_read(UC_ARM_REG_PRIMASK)
                h=c.uc.hook_add(UC_HOOK_CODE,trace)
                self.execute(c,TIM5,budget=4000);c.uc.hook_del(h)
                self.assertTrue(any(points.values()))
                for point,was_masked in points.items():
                    for held in (0x2000010E,0x20000110,0x20000112):
                        c=ready(mode,beep);pending=False;delivered=[]
                        def pause(uc,address,size,user):
                            nonlocal pending
                            if address==point:pending=True
                            if pending and not uc.reg_read(UC_ARM_REG_PRIMASK):
                                delivered.append(address);uc.emu_stop()
                        h=c.uc.hook_add(UC_HOOK_CODE,pause)
                        c.uc.reg_write(UC_ARM_REG_SP,SP);c.uc.reg_write(UC_ARM_REG_LR,STOP|1)
                        try:c.uc.emu_start(TIM5|1,STOP,count=4000)
                        finally:c.uc.hook_del(h)
                        self.assertEqual(len(delivered),1)
                        pc=c.uc.reg_read(UC_ARM_REG_PC);context=c.uc.context_save()
                        c.w16(held,6);self.execute(c,KEY,stack=SP-0x500)
                        self.assertEqual(c.read(BEEP),100)
                        c.uc.context_restore(context)
                        c.uc.emu_start(pc|1,STOP,count=4000)
                        self.assertEqual(c.uc.reg_read(UC_ARM_REG_PC),STOP)
                        self.assertIn(c.read(BEEP),(99,100))
                        self.assertEqual(c.uc.reg_read(UC_ARM_REG_PRIMASK),0)
                        rows+=1;masked+=bool(was_masked)
        self.__class__.results['key_preemptions']={'cases':rows,'masked_arrivals_deferred':masked}


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json',type=Path)
    args=parser.parse_args()
    result=unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(AudioClockIntegration))
    if args.json:
        args.json.parent.mkdir(parents=True,exist_ok=True)
        args.json.write_text(json.dumps({'passed':result.wasSuccessful(),'tests':result.testsRun,
            'results':AudioClockIntegration.results},indent=2),encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
