"""Reduce Analog analyzer work without changing its spectral decision.

PN1.23G evaluates 31 DFT bins even for flat DC (59,886 emulated instructions).
The decision is target17 - unsigned_noise/12 > 10. A target magnitude <=10
cannot pass for any noise value, so those windows need only the target DFT.

Bin1 is always removed from the original noise sum. The remaining windows
therefore compute target17 plus bins2..31 excluding17: 30 DFTs instead of31.
The remaining unsigned16 noise truncation, threshold, rail handling, gain
normalization and guarded publication code are untouched. Arithmetic order
does not change the integer sum or its final uint16 truncation.

The 40-byte replacement uses the existing analyzer stack and registers. It
does not modify the shared DFT or Digital/Mains callers. No RAM or image
growth is needed. Instruction counts are model measurements, not MCU cycles.
"""
from lpm10rx.image import PatchError


START, END = 0x08009F62, 0x08009F8A
EXPECTED = bytes.fromhex(
    '0124002500260027204601f098fa80b20544012c00d10746112c00d106460134202cf1d3ad1bed1b')
SOURCE = '''
    movs r0, #17
    bl 0x0800B4A0
    uxth r6, r0
    cmp r6, #10
    ble 0x08009FF8
    movs r4, #2
    movs r5, #0
bin:
    cmp r4, #17
    beq next
    mov r0, r4
    bl 0x0800B4A0
    uxth r0, r0
    add r5, r0
next:
    adds r4, #1
    cmp r4, #32
    blo bin
'''


def install(img):
    """Compose on the preserved PN1.23G Analog block; caller owns versioning."""
    if not hasattr(img, 'digital_gain_continuity'):
        raise PatchError('Analog selective analysis requires the PN1.23G ancestry')
    if img.read(START, END-START) != EXPECTED:
        raise PatchError('Analog selective analysis: unexpected analyzer block')
    code = img.assemble_at(START, SOURCE)
    if len(code) > END-START or len(code) % 2:
        raise PatchError('Analog selective analysis exceeds its original 40-byte block')
    replacement = code + bytes.fromhex('00bf')*((END-START-len(code))//2)
    img.poke(START, EXPECTED.hex(), replacement,
             'Analog: reject impossible target first; omit canceled bin1 from noise work')
    info = dict(start=START, end=END, code_bytes=len(code),
                persistent_ram_bytes=0, additional_stack_bytes=0,
                target_bin=17, target_minimum=11, noise_bins=tuple(k for k in range(2,32) if k!=17))
    img.analog_selective = info
    return info
