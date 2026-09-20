"""PN 2.14: two established SCAN modes with explicit frequency labels.

This profile starts from the exact PN 2.12 image. It does not contain the
PN 2.13 Sync32/Pulse test extension. It widens the original rounded buttons
for explicit frequency labels and repairs the RIGHT-key carrier cache after
the original GPIO operation. Mode cycling, modulation, carrier setup, and
RAM allocation remain those of PN 2.12.
"""
import hashlib
import struct

from lpm10a.image import PatchError
from lpm10a.thumb import assemble


PATCH_ID = 'scan-recovery'
VERSION = 'PN 2.14'
PARENT_SHA256 = '3d2db80f8288744191fe1ddb2855a83b900166dd365e1583c6270dfb460a0076'
MODE_LABELS = ('Digital 454 kHz', 'Analog 825 Hz')
LABEL_BLOCKS = (
    (0x080141C0, 0x080141F2, 221,
     '0220fbf7b3fd50b138a103c9cde90101052301aadd21782003f068fa09e035a010210b463822cde90010dd215c2003f07bf9'),
    (0x0801425E, 0x08014294, 260,
     '0220fbf764fd58b116a103c9cde90101042301aa4ff48271782003f018fa0ae012a010210b463022cde900104ff48271602003f02af9'),
)


def register(patch):
    @patch(PATCH_ID, 'Retain Digital/Analog SCAN; label frequencies and repair RIGHT-key carrier cache',
           risk='untested', default=False, group='scan',
           requires=('portflash-phy-status', 'scan-labels', 'thai-ui'))
    def scan_recovery(img):
        img.finalize()
        if hashlib.sha256(bytes(img.data)).hexdigest() != PARENT_SHA256:
            raise PatchError('scan-recovery requires the exact finalized PN 2.12 parent')
        parent_end, parent_size = img.cave_ptr, len(img.data)
        parent_ram_allocs = tuple(img.ram_allocs)
        # The original rounded buttons are 99 px wide; the longest explicit
        # label is 120 px. Relocate the descriptor, widening only these two
        # buttons while retaining the stock y positions, radius and colours.
        descriptor = img.emit_code('''
            .short 38, 0, 164, 26, 0x2105, 0x4A69, 3, 0x1000
        ''', why='SCAN buttons: preserve rounded shape, widen for frequency labels')
        img.poke(0x08014298, 'eaa50000', struct.pack('<I', descriptor - 0x0801414E),
                 'SCAN button descriptor: local wider copy')
        drawers = []
        for label, (site, resume, y, expected) in zip(MODE_LABELS, LABEL_BLOCKS):
            width = len(label) * 8
            drawer = img.emit_code(f'''
                push {{lr}}
                sub sp, #12
                movs r0, #16
                str r0, [sp]
                ldr r0, =label
                str r0, [sp, #4]
                movs r0, #{120 - width // 2}
                movw r1, #{y}
                movs r2, #{width}
                movs r3, #16
                bl 0x080174E8
                add sp, #12
                pop {{pc}}
                .pool
            label:
                .asciz "{label}"
            ''', why=f'SCAN label only: {label}, both languages')
            replacement = assemble(site, f'bl {drawer}\nb {resume}')
            remaining = len(bytes.fromhex(expected)) - len(replacement)
            replacement += assemble(site + len(replacement), 'nop\n' * (remaining // 2))
            img.poke(site, expected, replacement,
                     f'SCAN label only: preserve original mode {len(drawers)+1} button drawing')
            drawers.append(drawer)
        # RIGHT calls the vendor's PA8 input configuration even while a tone
        # is active. Its unchanged cache then skips restoring PA8 until the
        # next waveform edge. Keep the original operation, but publish an
        # invalid cache atomically with it so the next tick restores the
        # requested state. This also preserves a caller's existing mask.
        right_key_repair = img.emit_code('''
            push {r4, lr}
            mrs r4, PRIMASK
            cpsid i
            bl 0x0801C590
            ldr r0, =0x200000DC
            movs r1, #255
            strb r1, [r0]
            msr PRIMASK, r4
            pop {r4, pc}
            .pool
        ''', why='SCAN RIGHT: retain vendor GPIO operation and invalidate gate cache atomically')
        img.poke(0x08014480, '08f086f8', assemble(0x08014480, f'bl {right_key_repair}'),
                 'SCAN RIGHT: next timer tick restores both carrier pins')
        for site in (0x08011660, 0x08012E6C):
            img.set_string(site, VERSION)
        img.scan_recovery = dict(drawers=tuple(drawers), descriptor=descriptor,
                                 right_key_repair=right_key_repair,
                                 sites=tuple((start, end-start) for start, end, _, _ in LABEL_BLOCKS)
                                       + ((0x08014298, 4), (0x08014480, 4),
                                          (0x08011660, 8), (0x08012E6C, 8)),
                                 parent_end=parent_end,
                                 parent_size=parent_size,
                                 parent_ram_allocs=parent_ram_allocs,
                                 parent_sha256=PARENT_SHA256)
