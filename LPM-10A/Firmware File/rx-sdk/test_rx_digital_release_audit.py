"""Pinned PN1.12 release audit: real TIM5, analyzer, TIM1 and speaker PWM.

ADC/propagation and foreground/interrupt arrival times are modeled. Every
scheduled TIM5/TIM1 handler executes the shipped ARM; elapsed times below are
nominal timer-grid times, not wall-clock hardware or CPU-cycle measurements.
"""
import hashlib
import json
from pathlib import Path
import struct
import unittest

from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_R0
from unicorn.arm_const import UC_ARM_REG_PRIMASK

import test_rx_tracking_streams as streams
import test_rx_followup as followup
from sampling_fixes import PUBLISH_GATE
from verify_control import BEEP, SP, MODE
from verify_digital import ACTIVE, BUFFER, RECENT
from test_rx_followup import GRADE

SHA256='4ea18c52bde25353a9a38dbf46775425860f7859bc2c10e3c908a7bff4044403'
TIM1=0x0800A97C
T1_CYCLES=64001  # actual TIM1 ARR64000 / PSC0 at nominal64MHz
T5_CYCLES=1601   # actual TIM5 ARR1600 / PSC0 at nominal64MHz
PWM=0x40000C40


class ReleaseAudit(unittest.TestCase):
    execute=followup.Followup.execute
    boundary=followup.Followup.boundary
    timers=streams.TrackingStreams.timers

    @classmethod
    def setUpClass(cls):
        path=Path(__file__).resolve().parents[1]/'experimental/APP_LPM-10RX_PN1.12-overload.bin'
        cls.data=path.read_bytes()
        if hashlib.sha256(cls.data).hexdigest()!=SHA256:
            raise AssertionError('release audit requires exact delivered PN1.12')
        cls.results={}

    def run_stream(self,*,phase=0,amplitude=300,loss_ms=600,after=0,
                   post_ms=600,stall=None,gate_close=False,countdown=True,
                   timer1_stall=None):
        """A steady B6 envelope followed by flat input or coherent residual.

        Foreground gets one opportunity per TIM1 period; a declared stall
        suppresses only foreground, never the timer interrupts. Analysis itself
        is modeled as completing between scheduler events, not assigned cycles.
        """
        c=streams.StreamCPU(self.data);c.phase=phase
        loss=int(round(loss_ms*64000));end=int(round((loss_ms+post_ms)*64000))
        c.amplitude=lambda tick: amplitude if tick*T5_CYCLES<loss else after
        self.boundary(c)
        publications=[];pulses=[];sound=False;estimates=[];now=0
        def pwm(uc,access,address,size,value,user):
            nonlocal sound
            active=value!=800
            if active!=sound:
                when=c.read(streams.TIMER_COUNTER,4)*T5_CYCLES/64000
                pulses.append((when,active))
                sound=active
        def estimate(uc,address,size,user):
            estimates.append((uc.reg_read(UC_ARM_REG_R0)-(SP-128))//2)
        h=c.uc.hook_add(UC_HOOK_MEM_WRITE,pwm,begin=PWM,end=PWM+1)
        e=c.uc.hook_add(UC_HOOK_CODE,estimate,begin=0x0800B670,end=0x0800B670)
        closed=False
        try:
            tick1=1
            while now<end:
                target=min(tick1*T1_CYCLES,end)
                # The amplitude switch uses exact scheduled ADC-read time;
                # explicit gate closure is applied at the first TIM1 boundary.
                self.timers(c,target//T5_CYCLES-c.read(streams.TIMER_COUNTER,4))
                now=target
                timer1_withheld=(timer1_stall is not None
                    and timer1_stall[0]*64000<=now<timer1_stall[1]*64000)
                if countdown and not timer1_withheld:
                    self.execute(c,TIM1,stack=SP-0x500,budget=4000)
                if gate_close and not closed and now>=loss:
                    self.execute(c,PUBLISH_GATE,0,stack=SP-0x500)
                    closed=True
                is_stalled=stall is not None and stall[0]*64000<=now<stall[1]*64000
                if not is_stalled:
                    self.boundary(c)
                    if c.read(ACTIVE)==0:
                        samples=struct.unpack('<48H',c.uc.mem_read(BUFFER,96))
                        latest=c.events[-1][0]*T5_CYCLES/64000
                        estimates.clear()
                        self.execute(c,0x08009E08,budget=30000)
                        publications.append({'ms':now/64000,'grade':c.read(GRADE),
                            'recent':c.read(RECENT,2),'newest_adc_ms':latest,
                            'age_ms':now/64000-latest,
                            'estimate_start':estimates[0] if estimates else None,
                            'tail_flat':len(set(samples[32:]))==1,
                            'tail_value':samples[-1]})
                tick1+=1
        finally:c.uc.hook_del(h);c.uc.hook_del(e)
        accepted=[p for p in publications if p['grade'] and p['ms']>=loss_ms]
        rejected=[p for p in publications if not p['grade'] and p['ms']>=loss_ms]
        starts=[t for t,on in pulses if on and t>=loss_ms]
        offs=[t for t,on in pulses if not on and t>=loss_ms]
        # If no pulse is still active at loss, its last end may precede loss.
        last_off=max(offs,default=loss_ms)
        return {'phase':phase,'amplitude':amplitude,'after':after,'loss_ms':loss_ms,
            'post_ms':post_ms,'stall':stall,'gate_close':gate_close,
            'timer1_stall':timer1_stall,
            'first_reject_ms':rejected[0]['ms']-loss_ms if rejected else None,
            'last_accepted_ms':max((p['ms']-loss_ms for p in accepted),default=None),
            'last_sound_end_ms':last_off-loss_ms,
            'post_loss_starts_ms':[t-loss_ms for t in starts],
            'accepted_after_loss':accepted,'publications':publications,
            'pwm_edges':pulses,'final_beep':c.read(BEEP),'final_grade':c.read(GRADE),
            'final_recent':c.read(RECENT,2),'final_sound':sound,
            'timer_irqs':c.read(streams.TIMER_COUNTER,4),'adc_reads':len(c.events)}

    def test_clean_loss_phase_update_offset_and_strength_sweep(self):
        rows=[]
        for amplitude in (60,300,3000):
            for phase in (0,0.5,1,2,3,4,5,7):
                for offset in (0,20,40,60):
                    row=self.run_stream(phase=phase,amplitude=amplitude,loss_ms=600+offset)
                    self.assertFalse(row['final_sound'])
                    self.assertEqual(row['final_grade'],0)
                    self.assertIsNotNone(row['first_reject_ms'])
                    self.assertLess(row['first_reject_ms'],250)
                    self.assertLess(row['last_sound_end_ms'],350)
                    self.assertTrue(all(p['age_ms']<1.1 for p in row['publications']))
                    rows.append(row)
        self.__class__.results['clean_loss']={
            'cases':len(rows),'timer_irqs':sum(r['timer_irqs'] for r in rows),
            'first_reject_ms_range':[min(r['first_reject_ms'] for r in rows),
                                     max(r['first_reject_ms'] for r in rows)],
            'last_sound_end_ms_range':[min(r['last_sound_end_ms'] for r in rows),
                                       max(r['last_sound_end_ms'] for r in rows)],
            'max_extra_pulses':max(len(r['post_loss_starts_ms']) for r in rows),
            'worst_sound':max(rows,key=lambda r:r['last_sound_end_ms']),
            'worst_reject':max(rows,key=lambda r:r['first_reject_ms'])}

    def test_live_timer_freshness_caps_beeps_during_missing_main_work(self):
        # No publication can renew freshness while foreground is absent.
        row=self.run_stream(amplitude=3000,loss_ms=600,post_ms=900,stall=(600,2000))
        last_pub=max(p['ms'] for p in row['publications'] if p['grade'])
        starts=[t for t,on in row['pwm_edges'] if on and t>=last_pub]
        self.assertTrue(all(t-last_pub<300.3 for t in starts))
        self.assertLess(row['last_sound_end_ms'],330)
        self.assertFalse(row['final_sound'])
        self.__class__.results['main_absent_expiry']=row

    def test_completed_old_window_can_be_published_when_main_resumes_late(self):
        row=self.run_stream(amplitude=3000,loss_ms=650,post_ms=1700,stall=(610,1850))
        stale=[p for p in row['accepted_after_loss'] if p['age_ms']>1000]
        self.assertTrue(stale,'fixture must demonstrate old complete buffer acceptance')
        self.assertTrue(any(t>1000 for t in row['post_loss_starts_ms']))
        self.assertFalse(row['final_sound'])
        self.assertEqual(row['final_grade'],0)
        self.__class__.results['stale_completed_buffer']=row

    def test_weak_coherent_residual_can_refresh_for_more_than_one_second(self):
        rows=[]
        for residual in (0,9,12,25,60):
            row=self.run_stream(amplitude=3000,after=residual,post_ms=1600)
            if residual==0:
                self.assertEqual(row['final_grade'],0)
                self.assertFalse(any(t>1000 for t in row['post_loss_starts_ms']))
            elif residual>=12:
                self.assertGreater(row['final_grade'],0)
                self.assertTrue(any(t>1000 for t in row['post_loss_starts_ms']))
            rows.append(row)
        self.__class__.results['coherent_residual']=rows

    def test_real_gate_close_prevents_new_pulses_but_current_pulse_finishes(self):
        rows=[]
        schedules=[(a,600+offset) for a in (300,3095) for offset in (0,20,40,60)]
        # Two additional cuts land inside known normal30-tick and uncertain
        #100-tick pulses, rather than accidentally testing only quiet gaps.
        schedules += [(300,580),(3095,520)]
        for amplitude,loss in schedules:
            row=self.run_stream(amplitude=amplitude,loss_ms=loss,gate_close=True)
            self.assertEqual(row['final_grade'],0)
            self.assertFalse(any(t>1.3 for t in row['post_loss_starts_ms']))
            self.assertLess(row['last_sound_end_ms'],101.3)
            rows.append(row)
        self.assertGreater(rows[-1]['last_sound_end_ms'],70)
        self.assertGreater(rows[-2]['last_sound_end_ms'],10)
        self.__class__.results['gate_close']=rows

    def test_digital_analog_and_real_adc_masked_paths_are_bounded(self):
        import random
        import test_rx_analog_fast as analog
        import test_roadmap
        from rx_control_performance_audit import MaskControl
        rows=[]
        rng=random.Random(112)
        cases=[('digital_normal',0,[1000+300*streams.CODE[i%8] for i in range(48)]),
            ('digital_uncertain',0,[1000+3095*streams.CODE[i%8] for i in range(48)]),
            ('digital_reject',0,[1000]*48),
            ('digital_noise',0,[rng.randrange(4096) for _ in range(48)]),
            ('digital_exact_fallback',0,[1000+300*streams.CODE[i%8] for i in range(32)]+[1000]*16),
            ('digital_upper_tail',0,[1000+3000*streams.CODE[i%8] for i in range(32)]+[4095]*16),
            ('analog_normal',1,analog.sine(amplitude=300)),
            ('analog_reject',1,[1000]*64),
            ('analog_clipped',1,analog.sine(amplitude=8000))]
        for name,mode,samples in cases:
            c=streams.StreamCPU(self.data)
            c.w8(streams.GATE_STATE,2);c.w8(MODE,mode);c.w8(ACTIVE,0)
            c.uc.mem_write(BUFFER,struct.pack('<%dH'%len(samples),*samples))
            counts={'instructions':0,'max_contiguous_masked':0,'masked_total':0}
            run=0
            def count(uc,address,size,user):
                nonlocal run
                counts['instructions']+=1
                if uc.reg_read(UC_ARM_REG_PRIMASK):
                    run+=1;counts['masked_total']+=1
                    counts['max_contiguous_masked']=max(counts['max_contiguous_masked'],run)
                else:run=0
            h=c.uc.hook_add(UC_HOOK_CODE,count)
            try:self.execute(c,followup.ANALYZERS[mode],budget=200000)
            finally:c.uc.hook_del(h)
            self.assertEqual(c.uc.reg_read(UC_ARM_REG_PRIMASK),0)
            self.assertLess(counts['max_contiguous_masked'],50)
            rows.append({'path':name,**counts})
        # Exercise the actual ADC routine with a bounded completion model;
        # StreamCPU normally replaces ADC conversion to model the envelope.
        audit=test_roadmap.Roadmap('runTest');audit.data=self.data
        original=test_roadmap.Control
        adc=[]
        try:
            test_roadmap.Control=MaskControl
            for delay in (0,100,500,2000,None):
                c,model=audit.adc(1,delay or 0,complete=delay is not None)
                adc.append({'completion_delay_in_instructions':delay,'instructions':c.steps,
                    'max_contiguous_masked':c.max_masked,'reset_requested':bool(model['resets'])})
                self.assertEqual(bool(model['resets']),delay is None)
                if delay is not None:self.assertEqual(c.uc.reg_read(UC_ARM_REG_PRIMASK),0)
                self.assertLess(c.max_masked,3000)
        finally:test_roadmap.Control=original
        self.__class__.results['mask_audit']={'analysis':rows,'adc':adc,
            'limitation':'Executed instructions, not hardware cycles; no NVIC timing model.'}

    def test_withheld_tim1_is_a_distinct_continuous_tone_failure_model(self):
        # Fault injection only: a frozen countdown can sustain one pulse even
        # after fresh detector windows reject. This does not prove starvation
        # occurs on hardware; normal DSP mask traces above do not show it.
        row=self.run_stream(phase=0.5,amplitude=300,loss_ms=700,post_ms=1500,
                            timer1_stall=(700,1700))
        self.assertEqual(row['final_grade'],0)
        self.assertFalse(row['final_sound'])
        self.assertGreater(row['last_sound_end_ms'],1000)
        self.assertEqual(row['post_loss_starts_ms'],[])
        self.assertLess(row['first_reject_ms'],250)
        self.__class__.results['withheld_tim1_fault_injection']=row


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json',type=Path)
    args=parser.parse_args()
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(ReleaseAudit)
    outcome=unittest.TextTestRunner(verbosity=2).run(suite)
    if args.json:
        args.json.write_text(json.dumps({'sha256':SHA256,'passed':outcome.wasSuccessful(),
            'tests':outcome.testsRun,'results':ReleaseAudit.results},indent=2),encoding='utf-8')
    raise SystemExit(0 if outcome.wasSuccessful() else 1)
