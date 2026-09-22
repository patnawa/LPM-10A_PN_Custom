"""Length work belongs to one visit/test, including final result publication.

The stock network task executes the complete diagnostic synchronously. A Back
and reentry during its delay can restore sysState=7 before its cancellation
check, allowing old work to publish into the new screen. A generation stamped
at sequence start and invalidated on exit/entry prevents that ABA failure.

Final result and pending-REF preparation commit in one bounded critical
section. GUI queue calls occur afterward and carry a copied generation.
Historical builders are unchanged; this module composes existing hooks.
"""
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB

from lpm10a.image import PatchError
from lpm10a.thumb import assemble
from length_ref_anytime import bl_target
import roadmap

SYS, FLAGS, LAST = 0x2000013C, 0x200002B4, 0x200002B8
STATE_SITE, ENTRY_SITE, SEQUENCE = 0x0800F77C, 0x08012F1C, 0x080119EC
POLL_SITE, ACCEPT, TIMEOUT_FLAG = 0x08012178, 0x08012B86, 0x08012152
GUI_SITE, GUI_SEND = 0x0800F48C, 0x0800E428
ENTER_CRITICAL, EXIT_CRITICAL = 0x0801C6B4, 0x0801C6D8
START_SITE, NET_DISPATCH, NET_START_CALL = 0x0800D3F8, 0x08014904, 0x0801491A


def branch_target(img, site):
    instruction = next(Cs(CS_ARCH_ARM, CS_MODE_THUMB).disasm(img.read(site, 4), site))
    if instruction.mnemonic != 'b.w':
        raise PatchError(f'Length lifecycle expects a composed branch at {site:#x}')
    return int(instruction.op_str.lstrip('#'), 16)


def install(img):
    if not hasattr(img, 'length_reference_guard') or 'prepare' not in img.length_reference_guard:
        raise PatchError('Length lifecycle requires the non-queuing REF preparation seam')
    expected = {
        SEQUENCE: bytes.fromhex('00b597b0'),
        0x08011A66: bytes.fromhex('0120e6490870'),
        POLL_SITE: assemble(POLL_SITE, 'bl get_sysState', img.syms),
        0x080121EA: bytes.fromhex('00208d49'),
        ACCEPT: bytes.fromhex('00200790'),
        TIMEOUT_FLAG: bytes.fromhex('0320b3490870'),
        STATE_SITE: img.read(STATE_SITE, 4),
        ENTRY_SITE: img.read(ENTRY_SITE, 4),
        GUI_SITE: img.read(GUI_SITE, 4),
        START_SITE: assemble(START_SITE, 'bl 0x08012FBC'),
        NET_DISPATCH: bytes.fromhex('9df81000'),
        NET_START_CALL: assemble(NET_START_CALL, f'bl {SEQUENCE}'),
    }
    for site, value in expected.items():
        if img.read(site, len(value)) != value:
            raise PatchError(f'Length lifecycle: unexpected instruction at {site:#x}')
    old_state, old_gui = branch_target(img, STATE_SITE), branch_target(img, GUI_SITE)
    old_entry = bl_target(img.data, ENTRY_SITE)
    # Eight-byte network messages have command/length at offsets 0/1 and
    # their owned payload pointer at +4. Command 9 is outside stock's 0..8
    # table. The tagged Start uses that word inline and clears it before the
    # unchanged cleanup considers freeing a payload.
    if img.read(0x08014908, 8).hex() != '092842d2dfe800f0' or \
            img.read(0x08014994, 10).hex() != '059810b1059807f0adfe':
        raise PatchError('Length lifecycle requires the audited network message dispatcher ABI')
    state = img.alloc_ram(8)  # u32 generation, captured generation of network task
    syms = dict(LIFE=state, SYS=SYS, FLAGS=FLAGS, LAST=LAST,
                ENTER_CRITICAL=ENTER_CRITICAL | 1, EXIT_CRITICAL=EXIT_CRITICAL | 1,
                PREPARE=img.length_reference_guard['prepare'] | 1)

    current = img.emit_code('''
        ldr r0, =SYS
        ldrb r0, [r0]
        cmp r0, #7
        bne invalid
        ldr r0, =LIFE
        ldr r1, [r0]
        ldr r0, [r0, #4]
        cmp r0, r1
        bne invalid
        movs r0, #1
        bx lr
    invalid:
        movs r0, #0
        bx lr
    ''', extra_syms=syms, why='Length: current visit and diagnostic generation predicate')
    syms['CURRENT'] = current | 1
    transition = img.emit_code(f'''
        push {{r4, r5, r6, lr}}
        mov r4, r0
        bl ENTER_CRITICAL
        cmp r4, #12
        bhs unchanged
        cmp r4, #7
        beq unchanged
        ldr r0, =SYS
        ldrb r0, [r0]
        cmp r0, #7
        bne unchanged
        ldr r1, =LIFE
        ldr r0, [r1]
        adds r0, #1
        str r0, [r1]
        ldr r1, =FLAGS
        movs r0, #0
        strb r0, [r1]
    unchanged:
        bl EXIT_CRITICAL
        mov r0, r4
        ldr r3, [sp, #12]
        mov lr, r3
        pop {{r4, r5, r6}}
        add sp, #4
        b.w {old_state}
    ''', extra_syms=syms, why='Length: invalidate before leaving, preserving existing state transition hooks')
    entry = img.emit_code(f'''
        push {{r0, r1, r4, lr}}
        bl ENTER_CRITICAL
        ldr r1, =LIFE
        ldr r0, [r1]
        adds r0, #1
        str r0, [r1]
        bl EXIT_CRITICAL
        ldr r3, [sp, #12]
        mov lr, r3
        pop {{r0, r1, r4}}
        add sp, #4
        b.w {old_entry}
    ''', extra_syms=syms, why='Length: a fresh entry invalidates older diagnostics before REF reset')
    begin = img.emit_code('''
        push {lr}
        sub sp, #0x5C
        push {r4, lr}
        mov r4, r0
        bl ENTER_CRITICAL
        ldr r0, =SYS
        ldrb r0, [r0]
        cmp r0, #7
        bne outside
        ldr r1, =LIFE
        ldr r0, [r1]
        ldr r2, [sp, #0x64]
        ldr r3, =0x0801491F
        cmp r2, r3
        bne direct
        cmp r0, r4
        bne outside
    direct:
        adds r0, #1
        str r0, [r1]
        str r0, [r1, #4]
        ldr r1, =FLAGS
        movs r0, #1
        strb r0, [r1]
        bl EXIT_CRITICAL
        pop {r4}
        add sp, #4
        b.w 0x080119F0
    outside:
        bl EXIT_CRITICAL
        pop {r4}
        add sp, #4
        b.w 0x08012172
    ''', extra_syms=syms, why='Length: start only on its screen and stamp one diagnostic generation')
    send_start = img.emit_code('''
        push {r4, lr}
        sub sp, #8
        bl ENTER_CRITICAL
        ldr r0, =SYS
        ldrb r0, [r0]
        cmp r0, #7
        bne outside
        ldr r0, =LIFE
        ldr r0, [r0]
        str r0, [sp, #4]
        movs r0, #9
        str r0, [sp]
        bl EXIT_CRITICAL
        ldr r0, =0x20000070
        ldr r0, [r0]
        cmp r0, #0
        beq out
        mov r1, sp
        movs r2, #0
        movs r3, #0
        bl xQueueGenericSend
        b out
    outside:
        bl EXIT_CRITICAL
        movs r0, #0
    out:
        add sp, #8
        pop {r4, pc}
    ''', extra_syms=syms, why='Length Start: copy its visit epoch inline into the network queue without heap allocation')
    dispatch = img.emit_code('''
        mov r1, sp
        ldrb r0, [r1, #16]
        cmp r0, #9
        beq tagged
        cmp r0, #0
        beq stale
        b.w 0x08014908
    tagged:
        ldr r0, [r1, #20]
        movs r2, #0
        str r2, [r1, #20]
        b.w 0x0801491A
    stale:
        b.w 0x08014992
    ''', why='Length Start: deliver its epoch to the atomic sequence entry; preserve other network commands')
    poll = img.emit_code('''
        push {r4, lr}
        bl CURRENT
        cmp r0, #0
        beq out
        movs r0, #7
    out:
        pop {r4, pc}
    ''', extra_syms=syms, why='Length busy loop: reentry cannot make an old diagnostic current again')
    timeout = img.emit_code('''
        push {r4, lr}
        bl ENTER_CRITICAL
        bl CURRENT
        cmp r0, #0
        beq out
        ldr r1, =FLAGS
        movs r0, #3
        strb r0, [r1]
    out:
        bl EXIT_CRITICAL
        pop {r4, pc}
    ''', extra_syms=syms, why='Length: a stale timeout cannot replace the new visit state')
    cancel = img.emit_code('''
        push {r4, lr}
        bl ENTER_CRITICAL
        ldr r0, =LIFE
        ldr r1, [r0]
        ldr r0, [r0, #4]
        cmp r0, r1
        bne changed
        ldr r1, =FLAGS
        movs r0, #0
        strb r0, [r1]
    changed:
        bl EXIT_CRITICAL
        pop {r4}
        add sp, #4
        b.w 0x080121F0
    ''', extra_syms=syms, why='Length: cancellation clears only the flag owned by the canceled diagnostic')
    accept = img.emit_code(f'''
        push {{r4, r5, r6, lr}}
        mov r4, sp
        adds r4, #0x5C
        bl ENTER_CRITICAL
        bl CURRENT
        cmp r0, #0
        beq canceled
        ldr r1, =LAST
        movs r2, #4
    copy:
        ldrh r0, [r4]
        strh r0, [r1]
        adds r4, #2
        adds r1, #2
        subs r2, #1
        bne copy
        ldr r1, =FLAGS
        movs r0, #2
        strb r0, [r1]
        bl PREPARE
        mov r5, r0
        bl EXIT_CRITICAL
        ldr r1, =LIFE
        adds r1, #4
        movs r2, #4
        movs r0, #0x1A
        bl {GUI_SEND}
        cmp r5, #0
        beq published
        ldr r1, =LIFE
        adds r1, #4
        movs r2, #4
        movs r0, #0x3D
        bl {GUI_SEND}
    published:
        pop {{r4, r5, r6}}
        add sp, #4
        b.w 0x08012C06
    canceled:
        bl EXIT_CRITICAL
        pop {{r4, r5, r6}}
        add sp, #4
        b.w {cancel}
    ''', extra_syms=syms, why='Length: atomic current-result/REF commit, followed by tagged noncritical notifications')
    gui = img.emit_code(f'''
        cmp r0, #0x1A
        beq result
        cmp r0, #0x3D
        bne delegate
    result:
        ldr r1, [sp, #12]
        cmp r1, #0
        beq delegate
        ldr r1, [r1]
        ldr r2, =LIFE
        ldr r2, [r2]
        cmp r1, r2
        bne stale
        ldr r1, =SYS
        ldrb r1, [r1]
        cmp r1, #7
        bne stale
    delegate:
        b.w {old_gui}
    stale:
        b.w 0x0800F71E
    ''', extra_syms=syms, why='Length: queued result/header messages cannot repaint a newer visit')
    init = roadmap.startup(img, '''
        ldr r0, =LIFE
        movs r1, #0
        str r1, [r0]
        str r1, [r0, #4]
    ''', syms)
    for site, target, op in ((STATE_SITE, transition, 'b.w'), (ENTRY_SITE, entry, 'bl'),
                             (SEQUENCE, begin, 'b.w'), (POLL_SITE, poll, 'bl'),
                             (0x080121EA, cancel, 'b.w'),
                             (START_SITE, send_start, 'bl'), (NET_DISPATCH, dispatch, 'b.w'),
                             (ACCEPT, accept, 'b.w'), (GUI_SITE, gui, 'b.w')):
        img.poke(site, expected[site].hex(), assemble(site, f'{op} {target}'), 'Length lifecycle guard')
    img.poke(0x08011A66, expected[0x08011A66].hex(), assemble(0x08011A66, 'nop\nnop\nnop'),
             'Length busy flag is announced atomically at sequence start')
    img.poke(TIMEOUT_FLAG, expected[TIMEOUT_FLAG].hex(),
             assemble(TIMEOUT_FLAG, f'bl {timeout}\nnop'), 'Length timeout flag belongs to its diagnostic generation')
    img.length_lifecycle = dict(state=state, ram_bytes=8, current=current, transition=transition,
                                entry=entry, begin=begin, poll=poll, timeout=timeout, cancel=cancel,
                                accept=accept, gui=gui, init=init, expected=expected,
                                send_start=send_start, dispatch=dispatch,
                                old_entry=old_entry, old_state=old_state, old_gui=old_gui)
    return img.length_lifecycle
