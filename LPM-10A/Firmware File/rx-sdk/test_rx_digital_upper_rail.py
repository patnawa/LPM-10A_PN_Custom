"""Exact-fallback upper-rail checks; preserve all other PN 1.11 feedback."""
from collections import Counter
import hashlib
from pathlib import Path
import random
import struct
import unittest

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_PRIMASK, UC_ARM_REG_SP

import digital_upper_rail as patch
import test_rx_analog_fast as analog
import test_rx_digital_tail_prototype as baseline
import test_rx_followup as followup
import test_rx_robust as robust
import test_rx_tracking_fragments as fragments
import test_rx_tracking_streams as streams
from lpm10rx.image import Image, PatchError
from test_rx_followup import GATE_STATE, GRADE
from verify_control import SP
from verify_digital import ACTIVE, BUFFER, RECENT

PARENT=baseline.PARENT
reference=baseline.reference
CODE=baseline.CODE


def candidate():
    img=Image(str(PARENT))
    patch.apply(img)
    return img


def expected(samples):
    result=reference.measure(samples)
    if (result['gap'] > 1 and result['reason']=='established'
            and result['phase'] is None and all(v==4095 for v in samples[32:])):
        return 1
    return result['gap']


class DigitalUpperRail(unittest.TestCase):
    execute=followup.Followup.execute
    detect=robust.Robust.detect
    magnitude=analog.AnalogFast.magnitude

    @classmethod
    def setUpClass(cls):
        cls.previous=PARENT.read_bytes()
        cls.img=candidate()
        cls.data=bytes(cls.img.data)
        cls.results={}

    def cpu(self,data=None):
        c=streams.StreamCPU(self.data if data is None else data)
        c.w8(GATE_STATE,2)
        return c

    def test_exact_parent_scope_abi_padding_predecessors_and_guard(self):
        self.assertEqual(hashlib.sha256(self.previous).hexdigest(),patch.PARENT_SHA256)
        allowed={a for lo,size in ((patch.CALLSITE,4),*patch.PADDING)
                 for a in range(lo,lo+size)}
        changed={0x08006800+i for i,(a,b) in enumerate(zip(self.previous,self.data)) if a!=b}
        self.assertTrue(changed <= allowed)
        self.assertEqual(len(self.data),len(self.previous))
        self.assertEqual(self.img.digital_upper_rail['additional_stack_bytes'],0)
        self.assertEqual(self.img.digital_upper_rail['persistent_ram_bytes'],0)
        self.assertEqual(self.img.digital_upper_rail['changed_slot_bytes'],42)
        reconstructed=bytearray(self.previous)
        for address,old,new,why,kind in self.img.log:
            offset=address-0x08006800
            self.assertEqual(reconstructed[offset:offset+len(old)],old)
            reconstructed[offset:offset+len(new)]=new
        self.assertEqual(reconstructed,self.img.data)
        for address in (0x08006800,patch.CALLSITE,*(lo for lo,_ in patch.PADDING)):
            img=Image(str(PARENT));img.data[address-0x08006800]^=1
            before=bytes(img.data)
            with self.assertRaises(PatchError):patch.apply(img)
            self.assertEqual(bytes(img.data),before)
        with self.assertRaises(PatchError):patch.apply(self.img)
        md=Cs(CS_ARCH_ARM,CS_MODE_THUMB)
        for address,mnemonic in ((0x0800A036,'bx'),(0x0800B56C,'pop')):
            insn=next(md.disasm(self.previous[address-0x08006800:address-0x08006800+4],address))
            self.assertEqual(insn.mnemonic,mnemonic)

    def test_full_fragment_and_tail_matrix_preserves_every_nonrail_result(self):
        c=self.cpu();counts=Counter()
        for label,samples in list(fragments.fragment_vectors())+list(baseline.tail_rows()):
            old=reference.measure(samples)
            self.detect(c,samples,recent=560,grade=0)
            wanted=expected(samples)
            self.assertEqual(c.read(GRADE),wanted,(label,old))
            self.assertEqual(c.read(RECENT,2),800 if wanted else 560,label)
            self.assertEqual(struct.unpack('<32H',c.uc.mem_read(BUFFER,64)),tuple(samples[16:]))
            self.assertEqual(c.read(ACTIVE),1)
            counts['arm_vectors']+=1
            counts['changed_to_uncertain']+=wanted!=old['gap']
            counts['previously_uncertain_preserved']+=wanted==old['gap']==1
            self.assertFalse(old['gap'] and not wanted,'No previously signaled window may become silent')
        self.assertEqual(counts['arm_vectors'],7200)
        self.assertGreater(counts['changed_to_uncertain'],0)
        self.__class__.results['matrix']=dict(counts)

    def test_upper4095_uncertain_lower0_and_other_flat_tails_preserved(self):
        parent,new=self.cpu(self.previous),self.cpu()
        for tail in (0,1,1000,1300,4000,4094,4095):
            samples=[1000+3000*CODE[i%8] for i in range(32)]+[tail]*16
            self.detect(parent,samples,recent=560,grade=0)
            self.detect(new,samples,recent=560,grade=0)
            self.assertEqual(new.read(GRADE),1 if tail==4095 else parent.read(GRADE))
        self.assertEqual(parent.read(GRADE),30)
        self.assertEqual(new.read(GRADE),1)

    def test_upper_tail_requires_all16_raw_values_and_ignores_every_tag_nibble(self):
        c=self.cpu();samples=[1000+3000*CODE[i%8] for i in range(32)]+[4095]*16
        for rotation in range(16):
            def tags(uc,address,size,user):
                start=SP-128+64
                words=struct.unpack('<16H',uc.mem_read(start,32))
                uc.mem_write(start,struct.pack('<16H',*[(v&4095)|(((i+rotation)%16)<<12)
                                                       for i,v in enumerate(words)]))
            hook=c.uc.hook_add(UC_HOOK_CODE,tags,begin=patch.CALLSITE,end=patch.CALLSITE)
            try:self.detect(c,samples,recent=560,grade=0)
            finally:c.uc.hook_del(hook)
            self.assertEqual(c.read(GRADE),1)
        for index in range(16):
            for nonrail in (0,1,1000,2048,4094):
                altered=list(samples);altered[32+index]=nonrail
                self.detect(c,altered,recent=560,grade=0)
                self.assertEqual(c.read(GRADE),reference.measure(altered)['gap'])

    def test_nonflat_phase_clock_noise_and_other_words_unchanged(self):
        from scan_sync_model import sampled_window
        c=self.cpu();rng=random.Random(20260921);rows=[]
        for fresh in (False,True):
            for ratio in (0.997,1,1.003):
                for phase in range(64):
                    rows.append(sampled_window('legacy',phase/8,ratio,100,rng,
                                               amplitude=300,fresh_start=fresh))
        for word in range(256):
            rows.append([1000+300*((word>>(7-i%8))&1) for i in range(48)])
        rows.extend([[rng.randrange(4096) for _ in range(48)] for _ in range(256)])
        for samples in rows:
            self.detect(c,samples,recent=560,grade=0)
            self.assertEqual(c.read(GRADE),reference.measure(samples)['gap'])
        self.__class__.results['nonflat_control_arm_vectors']=len(rows)

    def test_stack_writes_mask_and_dft_padding_unchanged(self):
        maxima=[]
        for data in (self.previous,self.data):
            c=self.cpu(data);depths=[];writes=[]
            def depth(uc,a,s,u):depths.append(SP-uc.reg_read(UC_ARM_REG_SP))
            def write(uc,access,a,s,value,u):writes.append((a,s))
            h=c.uc.hook_add(UC_HOOK_CODE,depth);m=c.uc.hook_add(UC_HOOK_MEM_WRITE,write)
            try:
                for mask in (0,1):
                    for label,samples in list(baseline.tail_rows())[::17]:
                        c.uc.reg_write(UC_ARM_REG_PRIMASK,mask);writes.clear()
                        self.detect(c,samples,recent=560,grade=0)
                        self.assertEqual(c.uc.reg_read(UC_ARM_REG_PRIMASK),mask)
                        for address,size in writes:
                            self.assertTrue(SP-256 <= address and address+size <= SP
                                or BUFFER <= address and address+size <= BUFFER+96
                                or address in (ACTIVE,streams.SAMPLE_INDEX,GRADE,RECENT),hex(address))
                maxima.append(max(depths))
            finally:c.uc.hook_del(h);c.uc.hook_del(m)
        self.assertEqual(maxima,[184,184])
        old,new=self.cpu(self.previous),self.cpu()
        for name,samples in list(analog.corpus())[::7]:
            for k in (1,5,6,17,31):
                self.assertEqual(self.magnitude(new,samples,k),self.magnitude(old,samples,k),(name,k))
        self.__class__.results['maximum_stack_bytes']=maxima


if __name__=='__main__':
    unittest.main()
