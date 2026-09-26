"""PN2.34: Cable Test keys and redraws belong to one screen visit and mode.

PN2.33 checked BUSY only after the COUNT queue and checked just sysState at
GUI delivery. An OK delayed across Back could undo Back, and two could test
in the newly reset Switch mode. Capture/coalesce at the original key sender;
the GUI validates a copied epoch and mode before accepting work. Back, entry,
mode changes and screen exit invalidate old requests, including redraws.

Cable messages use an eight-byte, heap-free GUI envelope: 0x42, inner ID,
mode, reserved, u32 epoch. The dispatcher clears the inline epoch before
stock cleanup could interpret it as a heap pointer. Failed nonblocking queue
sends release their own pending claim. No electrical decision rule changes.
"""
import argparse
import contextlib
import hashlib
import io
from pathlib import Path

from lpm10a.image import PatchError
from lpm10a.thumb import assemble
from length_lifecycle import branch_target
from length_ref_anytime import bl_target
import cable_check as CC
import roadmap

VERSION = 'PN2.34'
PARENT_SHA256 = '84f9fb991a5bf43f0e29d978277ebe76baa58ff21714b430c1b6cef040751e91'
OUTPUT = Path(__file__).resolve().parent.parent / 'experimental' / 'LPM-10A-TX_PN2.34-cable-session.bin'
ENTRY, KEY_SEND, COUNT_MODE, GUI_SITE, KEY_SITE = 0x0800C300, 0x0800C3B0, 0x0800C40C, 0x0800F48C, 0x08014A04
# Stock owns 0x00..0x3F; Length text/clear own 0x40/0x41.
STATE_SITE, ENVELOPE = 0x0800F77C, 0x42
CURRENT_POSTS = (0x0800C318,)
ACTIVE_POSTS = (0x0800C33C, 0x0800C398, *CC.RETRY_POSTS)
STATE_SIZE = 16  # epoch, pending Start, GUI-owned accepted epoch, entry enabled


def apply(img):
    img.finalize()
    if hashlib.sha256(bytes(img.data)).hexdigest() != PARENT_SHA256:
        raise PatchError('cable-session requires the exact finalized PN2.33 parent')
    from length_message_guard import TEXT_MESSAGE, CLEAR_MESSAGE
    if ENVELOPE <= 0x3F or ENVELOPE in (TEXT_MESSAGE, CLEAR_MESSAGE):
        raise PatchError('cable-session GUI envelope collides with an existing message')
    parent_end, parent_ram = img.cave_ptr, tuple(img.ram_allocs)
    expected = {
        ENTRY: bytes.fromhex('10b50420'), KEY_SEND: bytes.fromhex('7cb50546'),
        COUNT_MODE: assemble(COUNT_MODE, 'bl 0x0800D270'),
        CC.OK_POST: assemble(CC.OK_POST, f"bl {img.cable_check['ok_gate']}"),
        GUI_SITE: img.read(GUI_SITE, 4), STATE_SITE: img.read(STATE_SITE, 4),
        KEY_SITE: img.read(KEY_SITE, 4),
        **{site: assemble(site, 'bl 0x0800E428') for site in CURRENT_POSTS + ACTIVE_POSTS[:2]},
        **{site: assemble(site, f"bl {img.cable_check['retry_post']}") for site in CC.RETRY_POSTS},
    }
    for site, old in expected.items():
        if img.read(site, len(old)) != old:
            raise PatchError(f'cable-session: unexpected instruction at {site:#x}')
    old_gui, old_state = branch_target(img, GUI_SITE), branch_target(img, STATE_SITE)
    old_key = bl_target(img.data, KEY_SITE)
    state = img.alloc_ram(STATE_SIZE)
    syms = dict(LIFE=state, SYS=CC.SYSSTATE, MODE=CC.MODE, BUSY=CC.BUSY,
                QUEUE=0x20000038, SEND_QUEUE=0x0801CAA1)

    invalidate = img.emit_code('''
        mrs r3, primask
        cpsid i
        ldr r1, =LIFE
        str r0, [r1, #12]
        ldr r0, [r1]
        adds r0, #1
        bne epoch_ok
        adds r0, #1
    epoch_ok:
        str r0, [r1]
        movs r0, #0
        str r0, [r1, #4]
        msr primask, r3
        bx lr
    ''', extra_syms=syms, why='Cable Test: invalidate pending work before entry, Back or exit')

    send = img.emit_code(f'''
        push {{r4, lr}}
        sub sp, #8
        str r1, [sp, #4]
        movs r3, #{ENVELOPE}
        lsls r0, r0, #8
        orrs r0, r3
        lsls r2, r2, #16
        orrs r0, r2
        str r0, [sp]
        ldr r0, =QUEUE
        ldr r0, [r0]
        cmp r0, #0
        beq done
        mov r1, sp
        movs r2, #0
        movs r3, #0
        bl SEND_QUEUE
    done:
        add sp, #8
        pop {{r4, pc}}
    ''', extra_syms=syms, why='Cable Test: copy epoch/mode inline into GUI queue without allocation')

    request = img.emit_code(f'''
        push {{r4, r5, r6, lr}}
        mov r4, r0
        mrs r6, primask
        cpsid i
        ldr r3, =LIFE
        ldr r0, [r3, #12]
        cmp r0, #0
        beq rejected
        ldr r0, =SYS
        ldrb r0, [r0]
        cmp r0, #4
        bne rejected
        ldr r0, =BUSY
        ldrb r0, [r0]
        cmp r0, #0
        bne rejected
        ldr r0, =MODE
        ldrb r2, [r0]
        cmp r4, #1
        beq toggle
        cmp r4, #2
        beq start
        cmp r4, #0x11
        bne rejected
    start:
        ldr r1, [r3, #4]
        cmp r1, #0
        bne rejected
        movs r1, #1
        str r1, [r3, #4]
        ldr r5, [r3]
        movs r0, #0x11
        b post
    toggle:
        cmp r2, #0x10
        bhs rejected
        movs r1, #1
        eors r2, r1
        strb r2, [r0]
        ldr r5, [r3]
        adds r5, #1
        bne toggle_epoch
        adds r5, #1
    toggle_epoch:
        str r5, [r3]
        movs r1, #0
        str r1, [r3, #4]
        movs r0, #0x0F
    post:
        mov r1, r5
        msr primask, r6
        bl {send}
        cmp r0, #1
        beq done
        cmp r4, #1
        beq done
        mrs r6, primask
        cpsid i
        ldr r3, =LIFE
        ldr r1, [r3]
        cmp r1, r5
        bne release_done
        movs r1, #0
        str r1, [r3, #4]
    release_done:
        msr primask, r6
        b done
    rejected:
        msr primask, r6
        movs r0, #0
    done:
        pop {{r4, r5, r6, pc}}
    ''', extra_syms=syms, why='Cable Test: capture key intent before any queue and coalesce pending Starts')

    def notify(active):
        return img.emit_code(f'''
            push {{r4, r5, r6, lr}}
            mov r4, r0
            mrs r6, primask
            cpsid i
            ldr r3, =LIFE
            ldr r0, [r3, #12]
            cmp r0, #0
            beq drop
            ldr r0, =SYS
            ldrb r0, [r0]
            cmp r0, #4
            bne drop
            ldr r1, [r3, #{8 if active else 0}]
            ldr r0, [r3]
            cmp r0, r1
            bne drop
            ldr r2, =MODE
            ldrb r2, [r2]
            mov r0, r4
            msr primask, r6
            bl {send}
            pop {{r4, r5, r6, pc}}
        drop:
            msr primask, r6
            movs r0, #0
            pop {{r4, r5, r6, pc}}
        ''', extra_syms=syms, why='Cable Test: stamp ' + ('GUI-owned' if active else 'current-entry') + ' redraw notifications')

    notify_current, notify_active = notify(False), notify(True)
    entry = img.emit_code(f'''
        push {{r4, lr}}
        mrs r4, primask
        cpsid i
        ldr r0, =BUSY
        ldrb r0, [r0]
        cmp r0, #0
        bne busy
        movs r0, #1
        bl {invalidate}
        ldr r0, =MODE
        movs r1, #0
        strb r1, [r0]
        ldr r0, ={CC.RETRY}
        strb r1, [r0]
        msr primask, r4
        movs r0, #4
        bl {STATE_SITE}
        movs r0, #0x0F
        bl {notify_current}
        pop {{r4, pc}}
    busy:
        msr primask, r4
        pop {{r4, pc}}
    ''', extra_syms=syms, why='Cable Test: atomically arbitrate Back/entry against the GUI measurement claim')

    transition = img.emit_code(f'''
        push {{r4, r5, r6, lr}}
        mov r4, r0
        cmp r4, #12
        bhs delegate
        cmp r4, #4
        beq delegate
        ldr r0, =SYS
        ldrb r0, [r0]
        cmp r0, #4
        bne delegate
        movs r0, #0
        bl {invalidate}
    delegate:
        mov r0, r4
        ldr r3, [sp, #12]
        mov lr, r3
        pop {{r4, r5, r6}}
        add sp, #4
        b.w {old_state}
    ''', extra_syms=syms, why='Cable Test: disable old visits before the composed screen transition')

    key = img.emit_code(f'''
        ldr r0, =SYS
        ldrb r0, [r0]
        cmp r0, #4
        bne delegate
        ldr r0, =BUSY
        ldrb r0, [r0]
        cmp r0, #0
        beq delegate
        movs r0, #0
        bx lr
    delegate:
        b.w {old_key}
    ''', extra_syms=syms, why='Cable Test: ignore navigation only after GUI atomically claims a running test')

    gui = img.emit_code(f'''
        cmp r0, #{ENVELOPE}
        beq tagged
        cmp r0, #0x0F
        blo delegate
        cmp r0, #0x12
        bls stale_raw
    delegate:
        b.w {old_gui}
    stale_raw:
        b.w 0x0800F71E
    tagged:
        push {{r4, r5, r6, r7, lr}}
        sub sp, #4
        ldr r0, [sp, #32]
        lsrs r4, r0, #8
        uxtb r4, r4
        lsrs r5, r0, #16
        uxtb r5, r5
        ldr r6, [sp, #36]
        movs r0, #0
        str r0, [sp, #36]
        mrs r7, primask
        cpsid i
        cmp r4, #0x37
        beq id_ok
        cmp r4, #0x0F
        blo invalid
        cmp r4, #0x12
        bhi invalid
    id_ok:
        ldr r0, =SYS
        ldrb r0, [r0]
        cmp r0, #4
        bne invalid
        ldr r3, =LIFE
        ldr r0, [r3, #12]
        cmp r0, #0
        beq invalid
        ldr r0, [r3]
        cmp r0, r6
        bne invalid
        ldr r1, =MODE
        ldrb r0, [r1]
        cmp r0, r5
        bne invalid
        cmp r4, #0x11
        bne redraw
        ldr r0, [r3, #4]
        cmp r0, #0
        beq invalid
        ldr r0, =BUSY
        ldrb r0, [r0]
        cmp r0, #0
        bne invalid
        movs r0, #0
        str r0, [r3, #4]
        str r6, [r3, #8]
        cmp r5, #0x10
        bhs measure
        mov r0, r5
        adds r0, #0x10
        strb r0, [r1]
        msr primask, r7
        movs r0, #0x10
        bl {notify_active}
        b complete
    measure:
        ldr r0, =BUSY
        movs r1, #1
        strb r1, [r0]
        msr primask, r7
        cmp r5, #0x10
        bne rx
        bl 0x0800CB68
        b complete
    rx:
        bl 0x0800C4E0
        b complete
    redraw:
        str r6, [r3, #8]
        msr primask, r7
        str r4, [sp, #32]
        mov r0, r4
        ldr r3, [sp, #20]
        mov lr, r3
        add sp, #4
        pop {{r4, r5, r6, r7}}
        add sp, #4
        b.w {old_gui}
    invalid:
        msr primask, r7
    complete:
        ldr r3, [sp, #20]
        mov lr, r3
        add sp, #4
        pop {{r4, r5, r6, r7}}
        add sp, #4
        b.w 0x0800F71E
    ''', extra_syms=syms, why='Cable Test: validate queued epoch/mode and own measurement before unmasking keys')

    init = roadmap.startup(img, '''
        ldr r0, =LIFE
        movs r1, #0
        str r1, [r0]
        str r1, [r0, #4]
        str r1, [r0, #8]
        str r1, [r0, #12]
    ''', syms)
    targets = {ENTRY: (entry, 'b.w'), KEY_SEND: (request, 'b.w'), COUNT_MODE: (request, 'bl'),
               CC.OK_POST: (request, 'bl'), STATE_SITE: (transition, 'b.w'), KEY_SITE: (key, 'bl'),
               GUI_SITE: (gui, 'b.w'),
               **{site: (notify_current, 'bl') for site in CURRENT_POSTS},
               **{site: (notify_active, 'bl') for site in ACTIVE_POSTS}}
    for site, (target, op) in targets.items():
        img.poke(site, expected[site].hex(), assemble(site, f'{op} {target}'), 'Cable Test queued-session guard')
    for site in (0x08011660, 0x08012E6C):
        img.set_string(site, VERSION)
    img.cable_session = dict(state=state, ram_bytes=STATE_SIZE, invalidate=invalidate, send=send,
                             request=request, notify_current=notify_current, notify_active=notify_active,
                             entry=entry, transition=transition, key=key, gui=gui, init=init,
                             parent_end=parent_end, parent_ram=parent_ram, expected=expected,
                             old_gui=old_gui, old_state=old_state, old_key=old_key)
    return img


def build_candidate():
    import cable_safe
    return apply(cable_safe.build_candidate()).finalize()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    with contextlib.redirect_stdout(io.StringIO()):
        img = build_candidate()
    data = bytes(img.data)
    digest = hashlib.sha256(data).hexdigest()
    print(f'{VERSION}: {len(data)} bytes; SHA256 {digest}')
    if args.write:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_bytes(data)
        OUTPUT.with_name('TX-PN2.34-SHA256SUMS.txt').write_text(f'{digest}  {OUTPUT.name}\n', encoding='ascii')
        print(f'Wrote {OUTPUT}')


if __name__ == '__main__':
    main()
