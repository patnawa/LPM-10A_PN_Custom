"""Exact-image ARM checks for isolated flat-tail policies, not deployment proof."""
from collections import Counter
import hashlib
from pathlib import Path
import random
import struct
import unittest

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_PRIMASK, UC_ARM_REG_SP

import digital_tail_prototype as prototype
import test_rx_analog_fast as analog
import test_rx_followup as followup
import test_rx_robust as robust
import test_rx_tracking_fragments as fragments
import test_rx_tracking_streams as streams
from lpm10rx.image import Image, PatchError
from test_rx_followup import GATE_STATE, GRADE
from verify_control import SP
from verify_digital import ACTIVE, BUFFER, RECENT

reference=streams.reference
CODE=streams.CODE
PARENT=Path(__file__).resolve().parents[1]/'experimental/APP_LPM-10RX_PN1.11-tracking.bin'


def candidate(upper=False):
    img=Image(str(PARENT))
    prototype.apply(img,upper_rail_uncertain=upper)
    return img


def expected(samples,upper=False):
    result=reference.measure(samples)
    if (result['gap'] > 1 and result['reason']=='established'
            and result['phase'] is None and len(set(samples[32:48]))==1):
        return 1 if upper and samples[-1]==4095 else 0
    return result['gap']


def tail_rows():
    for low,high in ((0,35),(0,4095),(1000,1300),(1000,4000),
                     (1000,4095),(3000,4095)):
        for tail in (0,1,25,1000,1300,2048,4000,4094,4095):
            for phase in range(8):
                yield (low,high,tail,phase), [low+(high-low)*CODE[(i+phase)%8]
                    for i in range(32)]+[tail]*16


class TailPrototype(unittest.TestCase):
    execute=followup.Followup.execute
    detect=robust.Robust.detect
    magnitude=analog.AnalogFast.magnitude

    @classmethod
    def setUpClass(cls):
        cls.previous=PARENT.read_bytes()
        cls.variants=[bytes(candidate(flag).data) for flag in (False,True)]
        cls.data=cls.variants[0]
        cls.results={}

    def cpu(self,data=None):
        c=streams.StreamCPU(self.data if data is None else data)
        c.w8(GATE_STATE,2)
        return c

    def test_exact_parent_scope_padding_control_flow_and_transactional_guard(self):
        self.assertEqual(hashlib.sha256(self.previous).hexdigest(),prototype.PARENT_SHA256)
        allowed={a for lo,size in ((prototype.CALLSITE,4),*prototype.PADDING)
                 for a in range(lo,lo+size)}
        for upper in (False,True):
            img=candidate(upper)
            changed={0x08006800+i for i,(a,b) in enumerate(zip(self.previous,img.data)) if a!=b}
            self.assertTrue(changed <= allowed)
            self.assertEqual(len(img.data),len(self.previous))
            self.assertEqual(img.digital_tail_prototype['additional_stack_bytes'],0)
            self.assertEqual(img.digital_tail_prototype['persistent_ram_bytes'],0)
            self.assertEqual(img.digital_tail_prototype['changed_slot_bytes'],78)
            reconstructed=bytearray(self.previous)
            for address,old,new,why,kind in img.log:
                offset=address-0x08006800
                self.assertEqual(reconstructed[offset:offset+len(old)],old)
                reconstructed[offset:offset+len(new)]=new
            self.assertEqual(reconstructed,img.data)
            before=bytes(img.data)
            with self.assertRaises(PatchError):prototype.apply(img)
            self.assertEqual(bytes(img.data),before)
        for address in (0x08006800,prototype.CALLSITE,*(lo for lo,_ in prototype.PADDING)):
            img=Image(str(PARENT));img.data[address-0x08006800]^=1
            before=bytes(img.data)
            with self.assertRaises(PatchError):prototype.apply(img)
            self.assertEqual(bytes(img.data),before)
        # Padding follows a branch around literal data or a function return;
        # no live fall-through instruction is replaced by the experiment.
        md=Cs(CS_ARCH_ARM,CS_MODE_THUMB)
        for address,mnemonic in ((0x0800A036,'bx'),(0x0800B4F8,'b'),
                                  (0x0800B56C,'pop'),(0x0800B620,'pop'),
                                  (0x0800B6D8,'pop'),(0x0800B706,'pop')):
            insn=next(md.disasm(self.previous[address-0x08006800:address-0x08006800+4],address))
            self.assertEqual(insn.mnemonic,mnemonic)
            if address==0x0800B4F8:self.assertEqual(insn.op_str,'#0x800b512')

    def test_fragment_and_flat_tail_matrix_matches_explicit_policy(self):
        cpus=[self.cpu(data) for data in self.variants]
        counts=Counter()
        for label,samples in list(fragments.fragment_vectors())+list(tail_rows()):
            baseline=reference.measure(samples)
            for upper,c in zip((False,True),cpus):
                self.detect(c,samples,recent=560,grade=0)
                wanted=expected(samples,upper)
                self.assertEqual(c.read(GRADE),wanted,(label,baseline,upper))
                self.assertEqual(c.read(RECENT,2),800 if wanted else 560,label)
                self.assertEqual(struct.unpack('<32H',c.uc.mem_read(BUFFER,64)),tuple(samples[16:]))
                self.assertEqual(c.read(ACTIVE),1)
                counts['arm_vectors']+=1
                counts['changed_'+str(upper)]+=wanted != baseline['gap']
                counts['uncertain_preserved_'+str(upper)]+=baseline['gap']==1 and wanted==1
        self.assertEqual(counts['arm_vectors'],14400)
        self.assertGreater(counts['changed_False'],100)
        self.assertGreater(counts['uncertain_preserved_False'],0)
        self.__class__.results['matrix']=dict(counts)

    def test_rail_uncertainty_is_visible_and_never_claimed_signal_loss(self):
        samples=[1000+3000*CODE[i%8] for i in range(32)]+[4095]*16
        cpus=[self.cpu(data) for data in (self.previous,*self.variants)]
        gaps=[]
        for c in cpus:
            self.detect(c,samples,recent=560,grade=0)
            gaps.append(c.read(GRADE))
        self.assertEqual(gaps,[30,0,1])
        # An already-uncertain clipped source remains uncertain in both
        # variants, even with a flat low baseline following it.
        samples=[1000+3095*CODE[i%8] for i in range(32)]+[1000]*16
        self.assertEqual(reference.measure(samples)['gap'],1)
        for c in cpus:
            self.detect(c,samples,recent=560,grade=0)
            self.assertEqual(c.read(GRADE),1)

    def test_all_sixteen_tag_patterns_and_every_nonflat_tail_position(self):
        # Tags are injected only after the unchanged detector has selected its
        # exact fallback. Comparison must inspect 12-bit ADC values, not tags.
        for data in self.variants:
            c=self.cpu(data)
            for flat in (1000,4095):
                samples=[1000+3000*CODE[i%8] for i in range(32)]+[flat]*16
                self.assertGreater(reference.measure(samples)['gap'],1)
                for tag_rotation in range(16):
                    def tags(uc,address,size,user):
                        start=SP-128+64
                        words=struct.unpack('<16H',uc.mem_read(start,32))
                        uc.mem_write(start,struct.pack('<16H',*[(v&4095)|(((i+tag_rotation)%16)<<12)
                                                               for i,v in enumerate(words)]))
                    hook=c.uc.hook_add(UC_HOOK_CODE,tags,begin=prototype.CALLSITE,end=prototype.CALLSITE)
                    try:self.detect(c,samples,recent=560,grade=0)
                    finally:c.uc.hook_del(hook)
                    self.assertEqual(c.read(GRADE),expected(samples,data==self.variants[1]))
                for index in range(16):
                    perturbed=list(samples)
                    perturbed[32+index]+= -1 if flat==4095 else 1
                    self.detect(c,perturbed,recent=560,grade=0)
                    self.assertEqual(c.read(GRADE),reference.measure(perturbed)['gap'])

    def test_nonflat_phase_clock_noise_and_other_words_unchanged(self):
        from scan_sync_model import sampled_window
        rng=random.Random(20260921)
        rows=[]
        for fresh in (False,True):
            for ratio in (0.997,1,1.003):
                for phase in range(64):
                    rows.append(sampled_window('legacy',phase/8,ratio,100,rng,
                                               amplitude=300,fresh_start=fresh))
        for word in range(256):
            rows.append([1000+300*((word>>(7-i%8))&1) for i in range(48)])
        rows.extend([[rng.randrange(4096) for _ in range(48)] for _ in range(256)])
        for data in self.variants:
            c=self.cpu(data)
            for samples in rows:
                self.detect(c,samples,recent=560,grade=0)
                self.assertEqual(c.read(GRADE),reference.measure(samples)['gap'])
        self.__class__.results['nonflat_control_arm_vectors']=2*len(rows)

    def test_abi_stack_write_ownership_and_mask_remain_bounded(self):
        rows=list(tail_rows())[::17]
        maxima=[]
        for data in (self.previous,*self.variants):
            c=self.cpu(data);depths=[];writes=[]
            def depth(uc,a,s,u):depths.append(SP-uc.reg_read(UC_ARM_REG_SP))
            def write(uc,access,a,s,value,u):writes.append((a,s))
            h=c.uc.hook_add(UC_HOOK_CODE,depth)
            m=c.uc.hook_add(UC_HOOK_MEM_WRITE,write)
            try:
                for mask in (0,1):
                    for label,samples in rows:
                        c.uc.reg_write(UC_ARM_REG_PRIMASK,mask)
                        writes.clear()
                        self.detect(c,samples,recent=560,grade=0)
                        self.assertEqual(c.uc.reg_read(UC_ARM_REG_PRIMASK),mask)
                        for address,size in writes:
                            self.assertTrue(SP-256 <= address and address+size <= SP
                                or BUFFER <= address and address+size <= BUFFER+96
                                or address in (ACTIVE,streams.SAMPLE_INDEX,GRADE,RECENT),hex(address))
                maxima.append(max(depths))
            finally:c.uc.hook_del(h);c.uc.hook_del(m)
        self.assertEqual(maxima,[184,184,184])
        self.__class__.results['maximum_stack_bytes']=maxima

    def test_reclaimed_dft_padding_is_unreachable_and_analog_results_bit_exact(self):
        cpus=[self.cpu(data) for data in (self.previous,*self.variants)]
        rows=list(analog.corpus())[::7]
        for name,samples in rows:
            for k in (1,5,6,17,31):
                values=[self.magnitude(c,samples,k) for c in cpus]
                self.assertEqual(values,[values[0]]*3,(name,k))


if __name__=='__main__':
    unittest.main()
