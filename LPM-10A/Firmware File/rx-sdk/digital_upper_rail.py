"""Exact-fallback upper-rail uncertainty, over the exact complete PN 1.11.

If all newest 16 raw 12-bit samples equal 4095, an old exact-code span must
not supply an ordinary strength rank. Publish existing uncertainty instead.
All other tails, including flat zero and any non-rail constant, retain PN 1.11
behavior. No code is skipped for a normal tail and no acquisition/gate policy
changes. This module does not register a profile, change a version or save an
artifact; the caller owns versioning and delivery.
"""
import hashlib

from lpm10rx.image import PatchError

PARENT_SHA256 = '3e39ae56832cf92881ffdc46564e293278d6c3f1b55a9832b7a9a8350f031828'
CALLSITE = 0x08009EF0
ENTRY = 0x0800A038
NONRAIL = ENTRY+10
LOOP = 0x0800B56E
PADDING = ((ENTRY,16),(LOOP,22))

ENTRY_SOURCE = '''
    mov r0,sp
    adds r0,#64
    movs r2,#16
    b.w upper_loop
nonrail:
    ldr r0,[sp,#100]
    b original_estimate
    nop
'''
LOOP_SOURCE = '''
upper_loop:
    ldrh r3,[r0]
    adds r3,#1
    lsls r3,r3,#20
    beq rail
    b.w nonrail
rail:
    adds r0,#2
    subs r2,#1
    bne upper_loop
    b.w uncertain
'''


def apply(img):
    """Apply atomically after validating the complete PN 1.11 predecessor."""
    if hashlib.sha256(bytes(img.data)).hexdigest()!=PARENT_SHA256:
        raise PatchError('Digital upper-rail guard requires the exact complete PN 1.11 parent')
    if img.read(CALLSITE,4)!=bytes.fromhex('199801e0'):
        raise PatchError('exact-fallback callsite differs from audited PN 1.11')
    for address,size in PADDING:
        if img.read(address,size)!=bytes.fromhex('00bf')*(size//2):
            raise PatchError(f'Digital upper-rail padding differs at {address:#x}')
    symbols={'upper_entry':ENTRY,'upper_loop':LOOP,'nonrail':NONRAIL,
             'original_estimate':0x08009EF8,'uncertain':0x08009F08}
    sources=((CALLSITE,4,'b upper_entry\nnop'),
             (ENTRY,16,ENTRY_SOURCE),(LOOP,22,LOOP_SOURCE))
    patches=[]
    for address,size,source in sources:
        code=img.assemble_at(address,source,symbols)
        if len(code)!=size:
            raise PatchError(f'Digital upper-rail code {len(code)} != slot {size} at {address:#x}')
        patches.append((address,size,code))
    for address,size,code in patches:
        img.poke(address,img.read(address,size).hex(),code,
                 'Digital exact fallback: newest16 raw samples all4095 -> uncertainty')
    # All temporary registers are caller-scratch r0/r2/r3. The original
    # selected pointer and phase are restored at the existing estimate entry.
    # No additional calls, stack words, interrupt masks or persistent state.
    img.digital_upper_rail={'parent_sha256':PARENT_SHA256,'tail_samples':16,
                            'adc_upper_rail':4095,'persistent_ram_bytes':0,
                            'additional_stack_bytes':0,'changed_slot_bytes':42,
                            'flat_lower_tail_policy':'preserve PN 1.11'}
