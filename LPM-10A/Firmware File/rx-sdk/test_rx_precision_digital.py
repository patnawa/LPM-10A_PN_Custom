"""Final PN1.24 Digital eligibility/strength against owner-tested PN1.23G.

Execute the actual analyzer on just-completed ADC vectors. Completion metadata
is seeded deliberately; the separate timer-stream suites test its ISR/main
ownership. Seeded vectors measure software equivalence, not physical range or
real-world noise false-alarm rates.
"""
import contextlib
import io
import random
import struct
import unittest

from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_PRIMASK, UC_ARM_REG_R0

import auto_range
import digital_gain_continuity
import rx_precision
import sample_age_guard
import test_rx_followup as followup
import test_rx_tracking_streams as streams
from test_rx_followup import ANALYZERS, GATE_STATE, GRADE, REQUEST
from verify_control import BEEP, MODE
from verify_digital import ACTIVE, BUFFER, GAP, GATE, RECENT, pattern


class PrecisionDigital(unittest.TestCase):
    execute = followup.Followup.execute

    @classmethod
    def setUpClass(cls):
        with contextlib.redirect_stdout(io.StringIO()):
            cls.previous = bytes(digital_gain_continuity.build_candidate().data)
            cls.img = rx_precision.build_candidate()
        cls.data = bytes(cls.img.data)

    def analyze(self, c, samples, *, level=7, old_grade=0, recent=0, mask=0):
        self.assertEqual(len(samples), 48)
        self.assertTrue(all(0 <= x <= 4095 for x in samples))
        c.uc.mem_write(0x20000000, bytes(0x220))
        c.w8(MODE, 0)
        c.w8(REQUEST, 0)
        c.w16(GATE, 4060)
        c.w16(GATE+2, 7)
        c.w8(GATE_STATE, 2)
        c.w8(ACTIVE, 0)
        c.w8(GRADE, old_grade)
        c.w16(RECENT, recent)
        c.uc.mem_write(auto_range.STATE, bytes((level, 0, 0, 7)))
        c.uc.mem_write(BUFFER, struct.pack('<48H', *samples)+bytes([0xA5]*32))
        # Freshness guards must see an actual completed generation, not simply
        # ACTIVE=0. Timer IRQ acquisition coverage lives in other suites.
        c.w32(sample_age_guard.COMPLETED_AT, 0xfffffff0)
        c.w32(sample_age_guard.TIMER_COUNTER, 0xfffffff0)
        c.w32(sample_age_guard.COMPLETED_VALID, 1)
        c.uc.reg_write(UC_ARM_REG_PRIMASK, mask)
        scores = []
        hook = c.uc.hook_add(UC_HOOK_CODE,
            lambda uc,a,s,u: scores.append(uc.reg_read(UC_ARM_REG_R0)),
            begin=0x0800A048, end=0x0800A048)
        try:
            # execute verifies SP, all callee-saved core registers and D8.
            self.execute(c, ANALYZERS[0], budget=100000)
        finally:
            c.uc.hook_del(hook)
        self.assertEqual(c.uc.reg_read(UC_ARM_REG_PRIMASK), mask)
        self.assertEqual(c.read(auto_range.STATE, 2), level)
        state = tuple(c.read(a,n) for a,n in
            ((GRADE,1),(RECENT,2),(ACTIVE,1),(0x2000005B,1),(BEEP,1),(GAP,1)))
        return state, tuple(scores), bytes(c.uc.mem_read(BUFFER,128))

    def test_weak_b6_cutoff_matches_g_across_all_phases_and_dc_offsets(self):
        old, new = streams.StreamCPU(self.previous), streams.StreamCPU(self.data)
        cutoffs, cases = {}, 0
        for dc in (0, 1000, 4000):
            for phase in range(8):
                accepted = []
                for amplitude in range(49):
                    samples = pattern(phase, dc, dc+amplitude)
                    before = self.analyze(old, samples, mask=amplitude&1)
                    after = self.analyze(new, samples, mask=amplitude&1)
                    self.assertEqual(after, before, (dc, phase, amplitude))
                    if before[0][1] == 800:
                        accepted.append(amplitude)
                    cases += 1
                self.assertTrue(accepted, (dc,phase))
                self.assertGreater(min(accepted), 0, 'zero contrast is not a signal')
                cutoffs[dc,phase] = min(accepted)
        print('Final Digital weak vectors:', cases, 'cutoff P-P counts by DC:',
              {dc: sorted({cutoffs[dc,p] for p in range(8)}) for dc in (0,1000,4000)})

    def test_seeded_noise_wrong_codes_rails_and_transients_are_bit_exact(self):
        cases = [(f'word_{code:02x}', [1000+300*((code>>(7-i%8))&1) for i in range(48)])
                 for code in range(256)]
        rng = random.Random(0x124D)
        cases += [(f'noise_{n}', [rng.randrange(4096) for _ in range(48)]) for n in range(64)]
        cases += [(f'binary_noise_{n}', [1000+300*rng.randrange(2) for _ in range(48)])
                  for n in range(64)]
        cases += [(f'dc_{value}', [value]*48) for value in (0,1,2048,4094,4095)]
        cases += [(f'upper_rail_spike_{at}', [4095 if i==at else 1000 for i in range(48)])
                  for at in range(48)]
        cases += [(f'lower_rail_spike_{at}', [0 if i==at else 3000 for i in range(48)])
                  for at in range(48)]
        cases += [('alternating_rails',[0,4095]*24)]
        cases += [(f'rail_b6_{phase}',pattern(phase,0,4095)) for phase in range(8)]
        cases += [(f'distributed_bad_bits_{phase}',pattern(phase,1000,1300,(8,24,40)))
                  for phase in range(8)]
        old, new = streams.StreamCPU(self.previous), streams.StreamCPU(self.data)
        accepted_words, noise_hits = [], 0
        for n,(name,samples) in enumerate(cases):
            before = self.analyze(old, samples, mask=n&1)
            after = self.analyze(new, samples, mask=n&1)
            self.assertEqual(after, before, name)
            accepted = before[0][1] == 800
            if name.startswith('word_') and accepted:
                accepted_words.append(int(name[5:],16))
            if 'noise_' in name and accepted:
                noise_hits += 1
            if name.startswith('dc_'):
                self.assertFalse(accepted, name)
        rotations = {((0xB6<<n)|(0xB6>>(8-n)))&255 for n in range(8)}
        self.assertEqual(set(accepted_words), rotations)
        print('Final Digital control vectors:', len(cases),
              'accepted word rotations:', len(accepted_words), 'seeded noise hits:', noise_hits)

    def test_strength_normalization_and_existing_rhythm_filter_match_g(self):
        old, new = streams.StreamCPU(self.previous), streams.StreamCPU(self.data)
        cases = 0
        for level in range(8):
            for phase in (0,3):
                for amplitude in (12,60,300,1600,3000):
                    for grade,recent in ((0,0),(20,800),(65,700),(110,501),(65,500)):
                        samples = pattern(phase,1000,1000+amplitude)
                        kwargs = dict(level=level,old_grade=grade,recent=recent,mask=cases&1)
                        self.assertEqual(self.analyze(new,samples,**kwargs),
                                         self.analyze(old,samples,**kwargs),
                                         (level,phase,amplitude,grade,recent))
                        cases += 1
        print('Final Digital gain/filter vectors:', cases)


if __name__ == '__main__':
    unittest.main()
