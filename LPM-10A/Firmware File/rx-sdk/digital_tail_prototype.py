"""REJECTED / UNREGISTERED PN 1.11 experiment: silence exact-fallback flat tails.

This is deliberately absent from build.py, tracking_fixes and the registry.
No artifact or version is published. Exact fallback alone visits this code;
local/global full-window fits retain their existing behavior. The tail is
inspected BEFORE recent_estimate sorts its selected span. Existing uncertain
estimates are preserved. The optional upper-rail variant reports uncertainty
for an all-4095 tail; the baseline experiment rejects it. Neither policy is
validated for deployment or for physical saturation behavior.

Do not integrate this experiment: the independent burst challenge found that
flat-tail silence can erase valid brief contacts. Kept only to reproduce that
tradeoff. digital_upper_rail.py is a separate, narrower policy that preserves
every non-upper-rail tail, including flat low tails.
"""
import hashlib

from lpm10rx.image import PatchError

PARENT_SHA256 = '3e39ae56832cf92881ffdc46564e293278d6c3f1b55a9832b7a9a8350f031828'
CALLSITE = 0x08009EF0
ENTRY = 0x0800A038
LOOP = 0x0800B56E
ESTIMATE = 0x0800B504
DECIDE = 0x0800B622
NORMAL = 0x0800B6DA
UPPER = 0x0800B708

# All six helper ranges are currently unreachable NOP padding, guarded both
# by the complete parent SHA and explicit predecessor bytes. See tests for
# direct branch/return predecessor checks and bit-exact Analog DFT parity.
PADDING = ((ENTRY,16),(LOOP,22),(ESTIMATE,14),(DECIDE,14),(NORMAL,4),(UPPER,4))

ENTRY_SOURCE = '''
    mov r6,r0
    mov r0,sp
    adds r0,#64
    ldrh r1,[r0]
    movs r2,#16
    movs r7,#1
    b.w tail_loop
'''
LOOP_SOURCE = '''
tail_loop:
    ldrh r3,[r0]
    eors r3,r1
    lsls r3,r3,#20
    bne tail_estimate
    adds r0,#2
    subs r2,#1
    bne tail_loop
    mov r7,r1
    adds r7,#1
    lsls r7,r7,#20
    b tail_estimate
'''
ESTIMATE_SOURCE = '''
    mov r0,r6
    mov r1,r4
    bl recent_estimate
    cmp r0,#0
    b.w tail_decide
'''
DECIDE_SOURCE = '''
    beq tail_normal
    cmp r7,#1
    beq tail_normal
    cmp r7,#0
    beq tail_upper
    b.w rejected
'''


def apply(img, *, upper_rail_uncertain=False):
    """Mutate only an exact PN 1.11 in-memory Image; never save an artifact."""
    if hashlib.sha256(bytes(img.data)).hexdigest() != PARENT_SHA256:
        raise PatchError('flat-tail prototype requires the exact delivered PN 1.11 parent')
    if img.read(CALLSITE,4) != bytes.fromhex('199801e0'):
        raise PatchError('exact-fallback callsite differs from audited parent')
    for address,size in PADDING:
        if img.read(address,size) != bytes.fromhex('00bf')*(size//2):
            raise PatchError(f'flat-tail helper padding differs at {address:#x}')
    symbols = {'tail_entry':ENTRY,'tail_loop':LOOP,'tail_estimate':ESTIMATE,
               'tail_decide':DECIDE,'tail_normal':NORMAL,'tail_upper':UPPER,
               'recent_estimate':0x0800B670,'rejected':0x08009F0C,
               'normal_result':0x08009EFE,'upper_result':0x08009F08
                   if upper_rail_uncertain else 0x08009F0C}
    sources = ((CALLSITE,4,'ldr r0,[sp,#100]\nb tail_entry'),
               (ENTRY,16,ENTRY_SOURCE),(LOOP,22,LOOP_SOURCE),
               (ESTIMATE,14,ESTIMATE_SOURCE),(DECIDE,14,DECIDE_SOURCE),
               (NORMAL,4,'b.w normal_result'),(UPPER,4,'b.w upper_result'))
    # Validate every assembled extent before mutating any bytes.
    patches=[]
    for address,size,source in sources:
        code=img.assemble_at(address,source,symbols)
        if len(code)!=size:
            raise PatchError(f'flat-tail prototype size {len(code)} != slot {size} at {address:#x}')
        patches.append((address,size,code))
    for address,size,code in patches:
        img.poke(address,img.read(address,size).hex(),code,
                 'UNREGISTERED flat-tail exact-fallback experiment')
    # r6/r7 are already saved by the detector and preserved by the estimator.
    # No pushes, new buffers, interrupt masks or persistent state are added.
    img.digital_tail_prototype = {
        'experimental_only':True,'rejected_for_delivery':True,
        'upper_rail_uncertain':bool(upper_rail_uncertain),
        'persistent_ram_bytes':0,'additional_stack_bytes':0,
        'changed_slot_bytes':sum(size for _,size,_ in sources),
        'parent_sha256':PARENT_SHA256,
    }
