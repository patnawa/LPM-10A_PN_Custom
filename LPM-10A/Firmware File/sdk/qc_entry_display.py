"""PN2.26: draw QC artwork only after deciding whether Init is required.

Entry queues header 36 before frame 0C. The classic header used to draw the
connector while MODE was still zero, queuing bitmap 3B behind frame 0C. If
frame 0C then showed the Init popup, that delayed connector overwrote it.
This candidate-only patch defers the undecided header, draws the connector
synchronously, and retains native clearing at view transitions. A guard
rejects a queued QC connector outside its current normal view. Existing
steady-state pin drawing and cached progress/error suppression are retained.
"""
from lpm10a.image import PatchError
from lpm10a.thumb import assemble

HEADER = 0x08069DD4
BITMAP_SITE, GUI_SITE = 0x0800BA66, 0x0800F48C
SYS, PHASE = 0x2000013C, 0x2000023C
GUARDS = {HEADER: bytes.fromhex('10b50c48'), BITMAP_SITE: bytes.fromhex('03f06bfa'),
          GUI_SITE: bytes.fromhex('5af0e0be')}


def install(img):
    if (not hasattr(img, 'qc_timing') or not hasattr(img, 'qc_classic')
            or not hasattr(img, 'length_message_guard')):
        raise PatchError('QC entry display requires the PN2.25 timing candidate')
    ui = img.qc_classic['ui']
    if ui['header'] != HEADER:
        raise PatchError('QC entry display: unexpected classic helper layout')
    for address, expected in GUARDS.items():
        if img.read(address, 4) != expected:
            raise PatchError(f'QC entry display: unexpected parent bytes at {address:#x}')
    old_gui = img.length_message_guard['gui']
    if img.read(GUI_SITE, 4) != assemble(GUI_SITE, f'b.w {old_gui}'):
        raise PatchError('QC entry display: changed dispatcher target')
    syms = dict(Q=img.qc['state'], CACHE=ui['cache'], SYS=SYS, PHASE=PHASE)
    header = img.emit_code(f'''
        ldr r0, =Q
        ldrb r0, [r0]
        cmp r0, #0
        beq deferred
        push {{r4, lr}}
        ldr r0, =SYS
        b.w {HEADER + 4}
    deferred:
        bx lr
    ''', extra_syms=syms,
        why='QC entry: wait for baseline validation before choosing normal artwork or Init prompt')
    gui = img.emit_code(f'''
        cmp r0, #0x3B
        bne delegate
        push {{r0, r1, r2, r3}}
        ldr r1, [sp, #28]
        cmp r1, #0
        beq restore
        ldrh r2, [r1]
        cmp r2, #26
        bne restore
        ldrh r2, [r1, #2]
        cmp r2, #68
        bne restore
        ldrh r2, [r1, #4]
        cmp r2, #21
        bne restore
        ldr r1, =SYS
        ldrb r1, [r1]
        cmp r1, #8
        bne discard
        ldr r1, =Q
        ldrb r1, [r1]
        cmp r1, #1
        bne discard
        ldr r1, =PHASE
        ldrb r1, [r1]
        cmp r1, #4
        beq discard
        ldr r1, =CACHE
        ldrb r1, [r1, #8]
        cmp r1, #1
        bne discard
    restore:
        pop {{r0, r1, r2, r3}}
    delegate:
        b.w {old_gui}
    discard:
        pop {{r0, r1, r2, r3}}
        b.w 0x0800F71E
    ''', extra_syms=syms,
        why='QC GUI: a delayed connector bitmap cannot overwrite Init or another screen')
    targets = {HEADER: (header, 'b.w'), BITMAP_SITE: (0x0800EEDA, 'bl'),
               GUI_SITE: (gui, 'b.w')}
    for address, (target, operation) in targets.items():
        img.poke(address, GUARDS[address].hex(), assemble(address, f'{operation} {target}'),
                 'QC: draw validated entry artwork and reject stale queued connector images')
    info = dict(header=header, gui=gui, old_gui=old_gui, previous_gui=old_gui,
                guards=dict(GUARDS), targets=targets, ram_bytes=0,
                cache=ui['cache'], state=img.qc['state'])
    img.qc_entry_display = info
    return info
