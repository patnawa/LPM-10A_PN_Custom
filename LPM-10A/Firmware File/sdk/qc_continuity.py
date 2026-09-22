"""PN2.23Q: bounded 20-second QC flex test, per-pin history and stable Init.

Build with ``python qc_continuity.py --write``. This opt-in TX candidate is
based on the exact PN2.23S image; released profiles remain reproducible.
One real TIM8 acquisition runs before each GUI queue receive, with interrupts
enabled during the 10 ms wait. Stock's one-second QC messages become no-ops.
OK stops/starts a fresh test; Right starts a fresh test; Right hold keeps Init.
Counts are a contact-response indication, not resistance or cable certification.
"""
import argparse
import contextlib
import hashlib
import io
from pathlib import Path

from lpm10a.image import Image, PatchError
from lpm10a.thumb import assemble
from profiles import PROFILES, apply_profile
from length_ref_anytime import bl_target
import roadmap
import speed_partner_validity as SV

VERSION = 'PN2.23Q'
PARENT_SHA256 = '007bbeff0deeca6a7d3df63ce4732a0f03350ae01cb3e6e541b067198fcec478'
HERE = Path(__file__).resolve().parent
OUTPUT = HERE.parent / 'experimental' / 'LPM-10A-TX_PN2.23Q-qc-flex.bin'
STATE_SIZE = 64
MODE, NEXT, DIRTY, BUSY, START, SCANS, SEEN = 0, 1, 2, 3, 4, 8, 10
LAST_DRAW, DRAW_INTERVAL_MS = 12, 200
GENERATION, CAL_EPOCH = 56, 60
FAULTS, NOW, BASE = 16, 32, 40
DURATION_MS, SETTLE_MS, MAX_FAULTS = 20_000, 50, 999
SYS_STATE, BASELINE, COUNTS = 0x2000013C, 0x2000021C, 0x2000022C
PHASE, VALID = 0x2000023C, 0x2000023D
POLL_SITE, FRAME_SITE, TEST_SITE, ERROR_SITE = 0x0800F462, 0x0800F57A, 0x0800F580, 0x0800F586
ENTRY_SITE, KEY_SITE, GUI_SITE = 0x0800BA2C, 0x08014A04, 0x0800F48C
ENTRY_FRAME_SITE = 0x0800BA42


def parent():
    img = Image(str(HERE.parent / 'LPM-10A-TX_V2.0.7_260610.bin'))
    apply_profile(img, PROFILES['pn2.23'], extra=(SV.PATCH_ID,))
    return img.finalize()


def apply(img):
    img.finalize()
    if hashlib.sha256(bytes(img.data)).hexdigest() != PARENT_SHA256:
        raise PatchError('qc-continuity requires the exact finalized PN2.23S parent')
    parent_end = img.cave_ptr
    expected = {
        POLL_SITE: bytes.fromhex('4ff0ff32'), ENTRY_SITE: bytes.fromhex('10b50820'),
        FRAME_SITE: assemble(FRAME_SITE, 'bl 0x0800BA54'),
        TEST_SITE: assemble(TEST_SITE, 'bl 0x0800BF40'),
        ERROR_SITE: assemble(ERROR_SITE, 'bl 0x0800BAD4'),
        ENTRY_FRAME_SITE: assemble(ENTRY_FRAME_SITE, 'bl GUI_MSG_SEND', img.syms),
        KEY_SITE: img.read(KEY_SITE, 4), GUI_SITE: img.read(GUI_SITE, 4),
    }
    for site, old in expected.items():
        if img.read(site, len(old)) != old:
            raise PatchError(f'qc-continuity: unexpected hook at {site:#x}')
    old_key = bl_target(img.data, KEY_SITE)
    old_gui = img.nvp['gui']
    if expected[GUI_SITE] != assemble(GUI_SITE, f'b.w {old_gui}'):
        raise PatchError('qc-continuity: unexpected GUI dispatcher')

    state = img.alloc_ram(STATE_SIZE)
    syms = dict(Q=state, SYS=SYS_STATE, BASELINE=BASELINE, COUNTS=COUNTS,
                PHASE=PHASE, VALID=VALID, SELECT=0x08018061, MEASURE=0x08018B85)
    clear = img.emit_code(f'''
        clear:
            ldr r0, =Q
            movs r1, #0
            movs r2, #{STATE_SIZE // 4}
        zero:
            str r1, [r0]
            adds r0, #4
            subs r2, #1
            bne zero
            bx lr
    ''', extra_syms=syms, why='QC: clear owned session RAM')
    invalidate = img.emit_code(f'''
        invalidate:
            push {{r3, r4, r5, r6, r7, lr}}
            mrs r7, primask
            cpsid i
            ldr r4, =Q
            ldrb r5, [r4, #{BUSY}]
            ldr r6, [r4, #{GENERATION}]
            adds r6, #1
            mov r0, r4
            movs r1, #0
            movs r2, #{GENERATION // 4}
        zero:
            str r1, [r0]
            adds r0, #4
            subs r2, #1
            bne zero
            str r6, [r4, #{GENERATION}]
            strb r5, [r4, #{BUSY}]
            msr primask, r7
            pop {{r3, r4, r5, r6, r7, pc}}
    ''', extra_syms=syms, why='QC: invalidate old work while preserving a live timer owner')
    reset = img.emit_code(f'''
        reset:
            push {{r4, r5, r6, lr}}
            bl {invalidate}
            ldr r4, =Q
            ldr r0, =COUNTS
            movs r1, #0
            str r1, [r0]
            str r1, [r0, #4]
            str r1, [r0, #8]
            str r1, [r0, #12]
            ldr r0, =SYS
            ldrb r0, [r0]
            cmp r0, #8
            bne done
            ldr r0, =VALID
            ldrb r0, [r0]
            cmp r0, #1
            bne done
            ldr r5, =BASELINE
            movs r6, #0
        baseline:
            ldrh r0, [r5]
            cmp r0, #7
            blo done
            movw r1, #65535
            cmp r0, r1
            beq done
            mov r1, r4
            adds r1, #{BASE}
            lsls r2, r6, #1
            add r1, r2
            strh r0, [r1]
            adds r5, #2
            adds r6, #1
            cmp r6, #8
            blo baseline
            bl xTaskGetTickCount
            str r0, [r4, #{START}]
            str r0, [r4, #{LAST_DRAW}]
            movs r0, #1
            strb r0, [r4, #{MODE}]
            ldr r0, =PHASE
            movs r1, #2
            strb r1, [r0]
        done:
            pop {{r4, r5, r6, pc}}
    ''', extra_syms=syms, why='QC: new bounded session and immutable per-session baseline')

    import qc_ui
    ui = qc_ui.install(img, state, reset)
    syms['DRAW'] = ui['draw'] | 1

    # Claim the timer atomically with calibration's PHASE=4 announcement.
    # No scheduler call or measurement occurs with interrupts masked.
    poll = img.emit_code(f'''
        poll:
            push {{r0, r1, r3, r4, r5, r6, r7, lr}}
            sub sp, #8
            ldr r4, =Q
            ldr r0, =SYS
            ldrb r0, [r0]
            cmp r0, #8
            beq in_qc
            movs r0, #0
            strb r0, [r4, #{MODE}]
            b.w idle
        in_qc:
            ldrb r0, [r4, #{MODE}]
            cmp r0, #1
            beq running
            b.w idle
        running:
            ldr r0, =PHASE
            ldrb r0, [r0]
            cmp r0, #4
            bne not_calibrating
            b.w active
        not_calibrating:
            ldrb r0, [r4, #{BUSY}]
            cmp r0, #0
            beq timer_free
            b.w active
        timer_free:
            bl xTaskGetTickCount
            ldr r1, [r4, #{START}]
            subs r0, r0, r1
            movw r1, #{DURATION_MS}
            cmp r0, r1
            blo within_time
            b.w complete
        within_time:
            cmp r0, #{SETTLE_MS}
            bhs settled
            b.w active
        settled:
            mrs r7, primask
            cpsid i
            ldr r0, =PHASE
            ldrb r0, [r0]
            cmp r0, #4
            beq claim_denied
            ldr r0, =SYS
            ldrb r0, [r0]
            cmp r0, #8
            bne claim_denied
            ldrb r0, [r4, #{BUSY}]
            cmp r0, #0
            bne claim_denied
            ldr r0, [r4, #{GENERATION}]
            str r0, [sp]
            movs r0, #1
            strb r0, [r4, #{BUSY}]
            msr primask, r7
            ldrb r5, [r4, #{NEXT}]
            mov r0, r5
            bl SELECT
            bl MEASURE
            mov r6, r0
            movs r0, #8
            bl SELECT
            mrs r7, primask
            cpsid i
            ldr r0, =PHASE
            ldrb r0, [r0]
            cmp r0, #4
            beq discard
            ldr r0, =SYS
            ldrb r0, [r0]
            cmp r0, #8
            bne discard
            ldr r0, [r4, #{GENERATION}]
            ldr r1, [sp]
            cmp r0, r1
            bne discard
            lsls r2, r5, #1
            ldr r0, =COUNTS
            add r0, r2
            strh r6, [r0]
            mov r0, r4
            adds r0, #{BASE}
            add r0, r2
            ldrh r1, [r0]
            movs r3, #3
            cmp r6, #0
            beq classified
            movw r0, #65535
            cmp r6, r0
            beq classified
            subs r0, r6, r1
            bpl absolute
            rsbs r0, r0, #0
        absolute:
            cmp r0, #7
            blo is_open
            cmp r6, r1
            bhi classified
            movs r3, #1
            b classified
        is_open:
            movs r3, #2
        classified:
            mov r0, r4
            adds r0, #{NOW}
            add r0, r5
            ldrb r1, [r0]
            strb r3, [r0]
            cmp r3, #1
            beq recorded
            cmp r1, #1
            bhi recorded
            mov r0, r4
            adds r0, #{FAULTS}
            add r0, r2
            ldrh r1, [r0]
            movw r3, #{MAX_FAULTS}
            cmp r1, r3
            bhs recorded
            adds r1, #1
            strh r1, [r0]
        recorded:
            ldr r0, =pin_bits
            add r0, r5
            ldrb r0, [r0]
            ldrb r1, [r4, #{SEEN}]
            orrs r1, r0
            strb r1, [r4, #{SEEN}]
            adds r5, #1
            cmp r5, #8
            blo next_pin
            movs r5, #0
            ldrh r0, [r4, #{SCANS}]
            movw r1, #65535
            cmp r0, r1
            bhs sweep_counted
            adds r0, #1
            strh r0, [r4, #{SCANS}]
        sweep_counted:
            movs r0, #1
            strb r0, [r4, #{DIRTY}]
        next_pin:
            strb r5, [r4, #{NEXT}]
            movs r0, #0
            strb r0, [r4, #{BUSY}]
            msr primask, r7
            ldrb r0, [r4, #{DIRTY}]
            cmp r0, #0
            beq active
            bl xTaskGetTickCount
            ldr r1, [r4, #{LAST_DRAW}]
            subs r1, r0, r1
            cmp r1, #{DRAW_INTERVAL_MS}
            blo active
            str r0, [r4, #{LAST_DRAW}]
            movs r0, #0
            strb r0, [r4, #{DIRTY}]
            bl DRAW
            b active
        discard:
            movs r0, #0
            strb r0, [r4, #{BUSY}]
        claim_denied:
            msr primask, r7
            b active
        complete:
            movs r0, #2
            strb r0, [r4, #{MODE}]
            ldr r0, =PHASE
            movs r1, #3
            strb r1, [r0]
            bl DRAW
        idle:
            movw r2, #65535
            movt r2, #65535
            add sp, #8
            pop {{r0, r1, r3, r4, r5, r6, r7, pc}}
        active:
            movs r2, #1
            add sp, #8
            pop {{r0, r1, r3, r4, r5, r6, r7, pc}}
        pin_bits:
            .byte 1, 2, 4, 8, 16, 32, 64, 128
    ''', extra_syms=syms, why='QC: one unfiltered pin per GUI receive, with bounded timer ownership')

    toggle = img.emit_code(f'''
        toggle:
            push {{r4, lr}}
            ldr r0, =SYS
            ldrb r0, [r0]
            cmp r0, #8
            bne done
            ldr r0, =PHASE
            ldrb r0, [r0]
            cmp r0, #4
            beq done
            ldr r4, =Q
            ldrb r0, [r4, #{MODE}]
            cmp r0, #1
            bne start
            movs r0, #3
            strb r0, [r4, #{MODE}]
            ldr r0, =PHASE
            movs r1, #3
            strb r1, [r0]
            b draw
        start:
            bl {reset}
        draw:
            bl DRAW
        done:
            pop {{r4, pc}}
    ''', extra_syms=syms, why='QC: OK stops or starts a fresh test without losing held results')
    entry = img.emit_code(f'''
        entry:
            push {{r4, lr}}
            bl {invalidate}
            movs r0, #8
            b.w 0x0800BA30
    ''', why='QC: clear the session synchronously before entering the screen')
    entry_notify = img.emit_code(f'''
        notify:
            ldr r1, =Q
            adds r1, #{GENERATION}
            movs r2, #4
            b.w GUI_MSG_SEND
    ''', extra_syms=syms, why='QC entry frame carries its visit generation through the GUI queue')

    key = img.emit_code(f'''
        key:
            push {{r4, lr}}
            ldr r0, =SYS
            ldrb r0, [r0]
            cmp r0, #8
            bne delegate
            ldrb r0, [r5]
            cmp r0, #5
            bne click
            ldrb r0, [r5, #1]
            cmp r0, #8
            beq initialize
        click:
            ldrb r0, [r5, #1]
            cmp r0, #3
            bne delegate
            ldrb r0, [r5]
            cmp r0, #4
            beq ok
            cmp r0, #5
            bne delegate
            movs r0, #0x3F
            b send
        ok:
            movs r0, #0x3E
        send:
            sub sp, #8
            ldr r1, =Q
            ldr r1, [r1, #{GENERATION}]
            str r1, [sp]
            mov r1, sp
            movs r2, #4
            bl GUI_MSG_SEND
            add sp, #8
            movw r0, #0x100
            pop {{r4, pc}}
        initialize:
            movs r0, #0
            movs r1, #0
            movs r2, #0
            bl CNT_MSG_SEND
            movw r0, #0x100
            pop {{r4, pc}}
        delegate:
            bl {old_key}
            pop {{r4, pc}}
    ''', extra_syms=syms, why='QC: add OK and Right click controls while retaining existing key bindings')
    noop = img.emit_code('bx lr', why='QC: ignore the superseded one-second scan request')
    gui = img.emit_code(f'''
        gui:
            cmp r0, #0x0C
            beq notification
            cmp r0, #0x0E
            beq notification
            cmp r0, #0x36
            beq notification
            cmp r0, #0x3E
            beq control
            cmp r0, #0x3F
            beq control
            b.w {old_gui}
        notification:
            mov r3, r0
            ldr r1, [sp, #12]
            cmp r1, #0
            beq current_notification
            ldr r1, [r1]
            ldr r2, =Q
            ldr r2, [r2, #{GENERATION}]
            cmp r1, r2
            bne done
        current_notification:
            mov r0, r3
            cmp r0, #0x36
            beq progress
            b.w {old_gui}
        control:
            mov r3, r0
            ldr r1, [sp, #12]
            cmp r1, #0
            beq done
            ldr r1, [r1]
            ldr r2, =Q
            ldr r2, [r2, #{GENERATION}]
            cmp r1, r2
            bne done
            cmp r3, #0x3F
            beq fresh
        toggle:
            bl {toggle}
            b.w 0x0800F71E
        fresh:
            ldr r0, =SYS
            ldrb r0, [r0]
            cmp r0, #8
            bne done
            ldr r0, =PHASE
            ldrb r0, [r0]
            cmp r0, #4
            beq done
            bl {reset}
            bl DRAW
            b done
        progress:
            ldr r0, =SYS
            ldrb r0, [r0]
            cmp r0, #8
            bne old_progress
            bl 0x0800E954
            ldr r0, =PHASE
            ldrb r0, [r0]
            cmp r0, #4
            bne redraw
            bl {ui['progress']}
            b done
        redraw:
            bl DRAW
            b done
        old_progress:
            movs r0, #0x36
            b.w {old_gui}
        done:
            b.w 0x0800F71E
    ''', extra_syms=syms, why='QC: GUI-owned session controls; reject stale controls outside QC')
    init = roadmap.startup(img, f'bl {clear}', {})

    import qc_calibration
    qc_calibration.apply(img)
    cal_notify = img.emit_code(f'''
        notify:
            ldr r1, =Q
            adds r1, #{CAL_EPOCH}
            movs r2, #4
            b.w GUI_MSG_SEND
    ''', extra_syms=syms, why='QC Init: queued progress/results carry the calibration session generation')
    cal_site = img.qc_calibration['notify']
    img.poke(cal_site, img.read(cal_site, 4).hex(), assemble(cal_site, f'b.w {cal_notify}'),
             'QC Init notifications cannot repaint a later visit')
    cal_begin = img.emit_code('''
        begin:
            ldr r0, =Q
            ldr r1, [r0, #56]
            str r1, [r0, #60]
            bx lr
    ''', extra_syms=syms, why='QC Init: snapshot its session before posting any progress message')
    cal_site = img.qc_calibration['begin_session']
    img.poke(cal_site, img.read(cal_site, 4).hex(), assemble(cal_site, f'b.w {cal_begin}'),
             'QC Init captures its session during the atomic calibration announcement')
    handoff = img.emit_code('''
        handoff:
            push {r4, r5, r6, lr}
            ldr r5, =Q
            movs r4, #100
        wait:
            ldr r0, =SYS
            ldrb r0, [r0]
            cmp r0, #8
            bne abort
            ldr r0, [r5, #56]
            ldr r1, [r5, #60]
            cmp r0, r1
            bne abort
            ldr r0, =Q
            ldrb r0, [r0, #3]
            cmp r0, #0
            beq owned
            movs r0, #1
            bl vTaskDelay
            subs r4, #1
            bne wait
        abort:
            movs r0, #0
            pop {r4, r5, r6, pc}
        owned:
            mrs r6, primask
            cpsid i
            ldr r0, [r5, #56]
            ldr r1, [r5, #60]
            cmp r0, r1
            bne changed
            ldr r0, =SYS
            ldrb r0, [r0]
            cmp r0, #8
            bne changed
            ldrb r0, [r5, #3]
            cmp r0, #0
            bne changed
            movs r0, #2
            strb r0, [r5, #3]
            msr primask, r6
            movs r0, #1
            pop {r4, r5, r6, pc}
        changed:
            msr primask, r6
            b abort
    ''', extra_syms=syms, why='QC Init: yield until the in-flight GUI sample releases TIM8')
    # Calibration exports the acquisition handoff call for this composition.
    cal_site = img.qc_calibration['handoff']
    img.poke(cal_site, img.read(cal_site, 4).hex(), assemble(cal_site, f'b.w {handoff}'),
             'QC calibration shares the timer only after the current sample completes')
    cal_current = img.emit_code('''
        current:
            ldr r0, =SYS
            ldrb r0, [r0]
            cmp r0, #8
            bne invalid
            ldr r0, =Q
            ldr r1, [r0, #56]
            ldr r0, [r0, #60]
            cmp r0, r1
            bne invalid
            movs r0, #1
            bx lr
        invalid:
            movs r0, #0
            bx lr
    ''', extra_syms=syms, why='QC Init: reject work from a previous visit even after rapid reentry')
    cal_site = img.qc_calibration['current_session']
    img.poke(cal_site, img.read(cal_site, 4).hex(), assemble(cal_site, f'b.w {cal_current}'),
             'QC Init uses the captured session generation')
    cal_release = img.emit_code('''
        release:
            ldr r0, =Q
            ldrb r1, [r0, #3]
            cmp r1, #2
            bne done
            movs r1, #0
            strb r1, [r0, #3]
        done:
            bx lr
    ''', extra_syms=syms, why='QC Init: release timer ownership only after releasing the mux')
    cal_site = img.qc_calibration['after_release']
    img.poke(cal_site, img.read(cal_site, 4).hex(), assemble(cal_site, f'b.w {cal_release}'),
             'QC Init releases its explicit timer ownership on every owned exit')

    targets = {POLL_SITE: (poll, 'bl'), FRAME_SITE: (ui['frame'], 'bl'),
               TEST_SITE: (noop, 'bl'), ERROR_SITE: (ui['error'], 'bl'),
               ENTRY_SITE: (entry, 'b.w'), KEY_SITE: (key, 'bl'), GUI_SITE: (gui, 'b.w'),
               ENTRY_FRAME_SITE: (entry_notify, 'bl')}
    for site, (target, op) in targets.items():
        img.poke(site, expected[site].hex(), assemble(site, f'{op} {target}'), 'QC flex test hook')
    for site in (0x08011660, 0x08012E6C):
        img.set_string(site, VERSION)
    img.qc = dict(state=state, clear=clear, invalidate=invalidate, reset=reset, poll=poll, toggle=toggle,
                  entry=entry, key=key, gui=gui, handoff=handoff, init=init,
                  frame=ui['frame'], error=ui['error'], ui=ui, noop=noop,
                  cal_begin=cal_begin, cal_current=cal_current, cal_release=cal_release,
                  entry_notify=entry_notify, cal_notify=cal_notify,
                  parent_end=parent_end)
    return img


def build_candidate():
    return apply(parent()).finalize()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--write', action='store_true')
    args = ap.parse_args()
    with contextlib.redirect_stdout(io.StringIO()):
        img = build_candidate()
    data = bytes(img.data)
    digest = hashlib.sha256(data).hexdigest()
    print(f'{VERSION}: {len(data)} bytes; SHA256 {digest}')
    print(img.summary())
    if args.write:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_bytes(data)
        OUTPUT.with_name('TX-PN2.23Q-SHA256SUMS.txt').write_text(
            f'{digest}  {OUTPUT.name}\n', encoding='ascii')
        print(f'Wrote {OUTPUT}')
    else:
        print('Dry build; use --write to emit the experimental update file.')
    print('CPU validation is separate from device validation; hardware QC testing is pending.')


if __name__ == '__main__':
    main()
