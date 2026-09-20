"""Reproduce measurements on the pinned, complete PN 1.11 artifact.

ADC values and interrupt timing are modeled. Retired instructions are not
CPU cycles, and nominal tick latencies are not measured device response.
"""
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
SDK = ROOT/'LPM-10A/Firmware File/rx-sdk'
sys.path.insert(0,str(SDK))
import test_rx_analog_feedback as checks
from test_rx_followup import ANALYZERS, GRADE
from verify_control import BEEP, SP
from verify_digital import ACTIVE, BUFFER, GAP, RECENT
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_SP

ARTIFACT = SDK.parent/'experimental/APP_LPM-10RX_PN1.11-tracking.bin'
SHA256 = '3e39ae56832cf92881ffdc46564e293278d6c3f1b55a9832b7a9a8350f031828'
PARENT = SDK.parent/'experimental/APP_LPM-10RX_PN1.9-robust.bin'
PARENT_SHA = '6128e0a4a0261f3da51bea232c8e431474033f0a09fd24283faa0a743b67fe3e'


def main():
    h = checks.AnalogFeedback()
    h.data = ARTIFACT.read_bytes()
    h.previous = PARENT.read_bytes()
    assert hashlib.sha256(h.data).hexdigest() == SHA256
    assert hashlib.sha256(h.previous).hexdigest() == PARENT_SHA
    profiles = []
    for label, samples in (('dc', [2048]*64), ('825Hz_sine_A300', checks.sine(300)),
                           ('clipped_825Hz_A8000',checks.sine(8000))):
        row = {'case': label}
        for prior in (True, False):
            c = h.analog_cpu(previous=prior)
            c.w8(ACTIVE,0)
            c.uc.mem_write(BUFFER,struct.pack('<64H',*samples))
            result = {'instructions':0,'max_stack_bytes':0}
            def count(uc,address,size,user):
                result['instructions'] += 1
                result['max_stack_bytes'] = max(result['max_stack_bytes'],SP-uc.reg_read(UC_ARM_REG_SP))
            hook = c.uc.hook_add(UC_HOOK_CODE,count)
            try:
                h.execute(c,ANALYZERS[1])
            finally:
                c.uc.hook_del(hook)
            row['parent' if prior else 'candidate'] = result
        profiles.append(row)
    grades = []
    for step in range(25,301,25):
        samples=checks.square(step)
        old=h.analog_cpu(previous=True)
        h.analyze(old,samples)
        c=h.analog_cpu()
        gap=h.analyze(c,samples)
        h.speaker(c)
        grades.append({'square_step_adc':step,'parent_beep_ms':old.read(BEEP),
                       'candidate_beep_ms':c.read(BEEP),'candidate_gap_ms':gap})
    # Old publisher starts tones itself; new scheduler executes through the
    # actual TIM5 path. Both use the same 21 ms modeled analysis arrivals.
    motion=[]
    for prior in (True,False):
        c=h.analog_cpu(previous=prior)
        h.analyze(c,checks.sine(25))
        h.speaker(c)
        starts=[{'tick':0,'beep_ms':c.read(BEEP),'gap_ms':c.read(GAP)}]
        for tick in range(1,501):
            c.run()
            before=c.read(BEEP)
            if tick % 21 == 0: h.analyze(c,checks.sine(1800))
            h.speaker(c)
            if before == 0 and c.read(BEEP):
                starts.append({'tick':tick,'beep_ms':c.read(BEEP),'gap_ms':c.read(GAP)})
        motion.append({'profile':'parent' if prior else 'candidate',
                       'strong_result_first_tick':21,'tone_starts':starts})
    print(json.dumps({'artifact':ARTIFACT.name,'sha256':SHA256,'size':len(h.data),
        'scope':__doc__,'analog_profiles':profiles,'square_strength_steps':grades,
        'weak_to_strong_feedback':motion},indent=2))


if __name__ == '__main__': main()
