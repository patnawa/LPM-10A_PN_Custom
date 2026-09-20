"""Keep 32 Digital samples, acquire 16 new samples after each 48-sample frame.

Called immediately after the analyzer snapshots the completed ADC buffer:
r0=BUFFER+96, r1=snapshot+96. ACTIVE is still zero; only the main context
owns this buffer. Copy from the immutable snapshot, publish index=32, then
ACTIVE=1 last. A main-boundary mode/gate invalidation resets the index to zero
and therefore requires a fresh full 48-sample acquisition.
"""
from lpm10rx.image import PatchError

HELPER = 0x0800A018
END = 0x0800A048
SOURCE = '''
    subs r0, #96
    subs r1, #64
    movs r2, #32
copy:
    ldrh r3, [r1]
    strh r3, [r0]
    adds r0, #2
    adds r1, #2
    subs r2, #1
    bne copy
    subs r0, #83
    movs r1, #32
    strb r1, [r0]
    subs r0, #83
    movs r1, #1
    strb r1, [r0]
    bx lr
'''


def apply(img):
    info = getattr(img, 'analog_feedback', {})
    if info.get('analyzer_bytes', END) > HELPER-0x08009F58:
        raise PatchError('overlap requires the audited Analog analyzer tail')
    if img.read(HELPER, END-HELPER) != bytes.fromhex('00bf')*((END-HELPER)//2):
        raise PatchError('overlap helper tail is not unused NOP padding')
    code = img.assemble_at(HELPER, SOURCE)
    if len(code) > END-HELPER:
        raise PatchError('overlap helper exceeds the audited tail')
    img.poke(HELPER, img.read(HELPER, END-HELPER).hex(),
             code+bytes.fromhex('00bf')*((END-HELPER-len(code))//2),
             'Digital overlap: retain32 samples, collect16, publish acquisition last')
    img.syms['overlap_rearm'] = HELPER | 1
    img.digital_overlap = {'helper_bytes': len(code), 'retained': 32, 'new': 16}
