"""Opt-in PN 2.9 reliability experiments. Register after the established patches.

No vendor source is available. CPU tests establish instruction behavior, not
peripheral timing, flash power-fail atomicity, or complete task-health coverage.
"""
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB
from lpm10a.thumb import assemble
from lpm10a.image import PatchError

PATCHES = ("isr-event-worker", "task-watchdog", "calibration-autosave", "crash-record")


def redirect(img, site, target, expected, why):
    img.poke(site, expected, assemble(site, f"bl 0x{target:X}"), why)


def startup(img, body, syms):
    """Compose with the existing main-entry initializer, preserving its ABI."""
    old = img.read(0x0801BBAC, 4)
    insn = next(Cs(CS_ARCH_ARM, CS_MODE_THUMB).disasm(old, 0x0801BBAC))
    if insn.mnemonic != "bl":
        raise PatchError("roadmap initialization requires batt-debounce's main hook")
    addr = img.emit_code("push {r5, lr}\n" + body +
                         f"\nbl {insn.op_str.lstrip('#')}\npop {{r5, pc}}", extra_syms=syms,
                         why="compose roadmap RAM initialization before interrupts/tasks")
    redirect(img, 0x0801BBAC, addr, old.hex(), "main: composed initialization")
    return addr


def register(patch):
    @patch("isr-event-worker", "Defer every application SysTick callback to a service task",
           risk="low", default=False, group="reliability", requires=("batt-debounce", "scan-timing"))
    def events(img):
        # Each audited call is a distinct bit. Conditions/cadences stay in the
        # vendor tick routine; repeated pending occurrences deliberately coalesce.
        calls = [(0x0801BC94, 0x08010EA8, 4), (0x0801BCA8, 0x0800E428, 11),
                 (0x0801BCBC, 0x0800BCE8, 2), (0x0801BCC0, 0x0800DD34, None),
                 (0x0801BCDC, 0x0800E428, 60), (0x0801BCE6, 0x08013F94, 6),
                 (0x0801BD0C, 0x08012FBC, 8), (0x0801BD32, 0x08013DCC, 1),
                 (0x0801BD5A, 0x080131B0, 1), (0x0801BD88, 0x0800E428, 4)]
        state = img.alloc_ram(12)  # pending, service heartbeat, watchdog armed
        syms = {"EVENTS": state}
        init = startup(img, """
            ldr r0, =EVENTS
            movs r1, #0
            str r1, [r0]
            str r1, [r0, #4]
            str r1, [r0, #8]
            ldr r0, =0xE000ED24
            ldr r1, [r0]
            movw r2, #0
            movt r2, #7
            orrs r1, r2
            str r1, [r0]
        """, syms)
        producers = []
        for bit, (site, function, message) in enumerate(calls):
            producer = img.emit_code(f"""
                mrs r3, primask
                cpsid i
                ldr r0, =EVENTS
                ldr r1, [r0]
                movw r2, #{1 << bit}
                orrs r1, r2
                str r1, [r0]
                msr primask, r3
                bx lr
            """, extra_syms=syms, why=f"SysTick event {bit}: bounded atomic publication")
            redirect(img, site, producer, assemble(site, f"bl 0x{function:X}").hex(),
                     f"SysTick callback {bit} -> pending event")
            producers.append(producer)
        dispatch = ""
        for bit, (_, function, message) in enumerate(calls):
            dispatch += f"movw r0, #{1 << bit}\nands r0, r4\nbeq next_{bit}\n"
            if message is not None:
                dispatch += f"movs r0, #{message}\nmovs r1, #0\nmovs r2, #0\n"
            dispatch += f"bl 0x{function:X}\nnext_{bit}:\n"
        poll = img.emit_code("""
            push {r4, lr}
            mrs r3, primask
            cpsid i
            ldr r0, =EVENTS
            ldr r4, [r0]
            movs r1, #0
            str r1, [r0]
            msr primask, r3
        """ + dispatch + """
            ldr r0, =EVENTS
            movs r1, #1
            str r1, [r0, #4]
            pop {r4, pc}
        """, extra_syms=syms, why="task-context event drain; atomic exchange, then unmasked callbacks")
        worker = img.emit_code(f"""
        loop:
            bl 0x{poll:X}
            movs r0, #1
            bl vTaskDelay
            b loop
        """, why="service task: drain pending events every scheduler tick")
        create = img.emit_code(f"""
            push {{r4, lr}}
            sub sp, #8
            movs r0, #2
            str r0, [sp]
            movs r0, #0
            str r0, [sp, #4]
            ldr r0, ={worker | 1}
            ldr r1, =name
            movw r2, #512
            movs r3, #0
            bl xTaskCreate
            ldr r1, =EVENTS
            movs r2, #1
            str r2, [r1, #8]
            cmp r0, #1
            beq created
        failed:
            b failed
        created:
            add sp, #8
            ldr r4, [sp]
            ldr r3, [sp, #4]
            mov lr, r3
            add sp, #8
            b.w vTaskStartScheduler
        name: .asciz "PN service"
        """, extra_syms=syms, why="create 512-word service task before starting scheduler; fail closed")
        redirect(img, 0x0801BC44, create, "00f0c6fd", "start service task and scheduler")
        img.events = dict(state=state, init=init, producers=producers, poll=poll,
                          worker=worker, create=create, calls=calls)

    @patch("task-watchdog", "Require service-task progress before TIM2 refreshes the watchdog",
           risk="low", default=False, group="reliability", requires=("isr-event-worker",))
    def watchdog(img):
        hook = img.emit_code("""
            ldr r0, =EVENTS
            ldr r1, [r0, #8]
            cbz r1, feed
            ldr r1, [r0, #4]
            cbz r1, done
            movs r1, #0
            str r1, [r0, #4]
        feed:
            b.w 0x080169A8
        done:
            bx lr
        """, extra_syms={"EVENTS": img.events["state"]},
            why="timer consumes a heartbeat; boot remains stock until service task creation")
        redirect(img, 0x08018398, hook, "fef706fb", "TIM2: task-aware watchdog gate")
        img.watchdog = hook

    @patch("calibration-autosave", "Save changed NVP, Zero and unit when leaving Length",
           risk="low", default=False, group="reliability", requires=("length-decimal", "isr-event-worker"))
    def autosave(img):
        # Dedicated staging avoids the vendor routine's unchecked malloc. Tasks
        # stay suspended during the write, preventing concurrent settings writers;
        # interrupts remain enabled. This is still a single flash-page transaction.
        shadow = img.alloc_ram(204)
        save = img.emit_code("""
            push {r4, r5, r6, lr}
            bl vTaskSuspendAll
            ldr r4, =g_settings
            ldr r5, =SHADOW
            movs r6, #50
        copy:
            ldr r0, [r4]
            str r0, [r5]
            adds r4, #4
            adds r5, #4
            subs r6, #1
            bne copy
            movs r0, #0
            str r0, [r5]
            bl flash_unlock
            ldr r0, =0x0807F800
            bl flash_erase_page
            cmp r0, #6             ; vendor FLASH_COMPLETE
            bne failed
            ldr r4, =0x0807F800
            ldr r5, =SHADOW
            movs r6, #51
        program:
            mov r0, r4
            ldr r1, [r5]
            bl flash_program
            cmp r0, #6
            bne failed
            adds r4, #4
            adds r5, #4
            subs r6, #1
            bne program
            ldr r4, =0x0807F800
            ldr r5, =SHADOW
            movs r6, #51
        verify:
            ldr r0, [r4]
            ldr r1, [r5]
            cmp r0, r1
            bne failed
            adds r4, #4
            adds r5, #4
            subs r6, #1
            bne verify
            movs r6, #1
            b finish
        failed:
            movs r6, #0
        finish:
            bl flash_lock
            bl xTaskResumeAll
            mov r0, r6
            pop {r4, r5, r6, pc}
        """, extra_syms={"SHADOW": shadow}, why="bounded static-buffer settings save without heap allocation")
        transition = img.emit_code(f"""
            push {{r2, r3, r4, r5, r6, lr}}
            mov r4, r0
            cmp r4, #7
            beq done
            cmp r4, #12
            bhs done
            cmp r4, #0
            beq done
            ldr r0, =0x2000013C
            ldrb r0, [r0]
            cmp r0, #7
            bne done
            ldr r0, =0x20000D1E
            ldr r1, =0x0807F8A6
            ldrh r2, [r0]
            ldrh r3, [r1]
            cmp r2, r3
            bne changed
            ldrb r2, [r0, #31]
            ldrb r3, [r1, #31]
            cmp r2, r3
            beq done
        changed:
            bl 0x{save:X}
        done:
            b.w 0x0800F780
        """, why="actual system-state transition: save only changed Length preferences")
        img.poke(0x0800F77C, "7cb5 0446", assemble(0x0800F77C, f"b.w 0x{transition:X}"),
                 "set_sysState: save on Length exit, replay original prologue")
        img.autosave = dict(save=save, transition=transition, shadow=shadow)

    @patch("crash-record", "Retain fault context across warm reset and show it in About",
           risk="low", default=False, group="reliability")
    def crash(img):
        record = img.alloc_ram(40)  # outside scatterload ZI; do NOT initialize
        syms = {"RECORD": record}
        handler = img.emit_code("""
            cpsid i
            mov r2, lr
            movs r1, #4
            ands r1, r2
            bne psp_frame
            mrs r0, msp
            b frame
        psp_frame:
            mrs r0, psp
        frame:
            ldr r3, =RECORD
            movs r1, #0
            str r1, [r3]
            str r2, [r3, #24]
            str r0, [r3, #28]
            mrs r1, ipsr
            str r1, [r3, #32]
            ldr r4, =0xE000ED28
            ldr r5, [r4]
            str r5, [r3, #16]
            ldr r1, [r4, #4]
            str r1, [r3, #20]
            movs r1, #0
            str r1, [r3, #8]
            str r1, [r3, #12]
            movw r1, #0x3838
            ands r1, r5
            bne commit
            movs r1, #3
            ands r1, r0
            bne commit
            ldr r1, =0x20000000
            cmp r0, r1
            blo commit
            ldr r1, =0x2000FFE0
            cmp r0, r1
            bhi commit
            ldr r1, [r0, #24]
            str r1, [r3, #8]
            ldr r1, [r0, #20]
            str r1, [r3, #12]
        commit:
            ldr r1, =0x21524110
            str r1, [r3, #4]
            ldr r1, =0xDEADBEEF
            dsb
            str r1, [r3]
            dsb
            ldr r0, =0xE000ED0C
            ldr r1, [r0]
            movw r2, #0x700
            ands r1, r2
            ldr r2, =0x05FA0004
            orrs r1, r2
            str r1, [r0]
            dsb
        wait_reset:
            b wait_reset
        """, extra_syms=syms, why="stackless fault record; MSP/PSP, FP frame and stacking-fault handling")
        for vector in (3, 4, 5, 6):
            site = 0x0800A000 + vector * 4
            img.poke(site, img.read(site, 4).hex(), (handler | 1).to_bytes(4, "little"),
                     f"fault vector {vector} -> retained crash recorder")
        show = img.emit_code("""
            push {r4, r5, r6, lr}
            sub sp, #56
            ldr r4, =RECORD
            ldr r0, [r4]
            ldr r1, =0xDEADBEEF
            cmp r0, r1
            bne no_record
            ldr r0, [r4, #4]
            ldr r1, =0x21524110
            cmp r0, r1
            bne no_record
            ldr r0, =0x200001AC
            ldrh r5, [r0]
            ldrh r6, [r0, #2]
            movw r1, #65535
            strh r1, [r0]
            movw r1, #0x2105
            strh r1, [r0, #2]
            str r1, [sp]
            movs r0, #12
            movs r1, #201
            movs r2, #228
            movs r3, #235
            bl 0x08016D08
            mov r0, sp
            adds r0, #8
            ldr r1, =pcfmt
            ldr r2, [r4, #8]
            ldr r3, [r4, #12]
            bl sprintf
            movs r1, #208
            bl line
            mov r0, sp
            adds r0, #8
            ldr r1, =statusfmt
            ldr r2, [r4, #16]
            ldr r3, [r4, #32]
            bl sprintf
            movs r1, #222
            bl line
        done:
            ldr r0, =0x200001AC
            strh r5, [r0]
            strh r6, [r0, #2]
        no_record:
            add sp, #56
            pop {r4, r5, r6, pc}
        line:
            push {r4, lr}
            sub sp, #8
            movs r0, #12
            str r0, [sp]
            mov r0, sp
            adds r0, #24
            str r0, [sp, #4]
            movs r0, #12
            movs r2, #216
            movs r3, #12
            bl gui_blit
            add sp, #8
            pop {r4, pc}
        pcfmt: .asciz "PC %08X LR %08X"
        statusfmt: .asciz "CFSR %08X IRQ %d"
        """, extra_syms=syms, why="About: retained fault PC/LR/status in two 12-pixel rows")
        epilogue = img.emit_code(f"bl 0x{show:X}\nadd sp, #88\npop {{r4, r5, r6, pc}}",
                                 why="About epilogue: show crash and restore original stack")
        # The English branch jumps directly to 0x1162C, bypassing the preceding NOP.
        img.poke(0x0801162C, "16b0 70bd", assemble(0x0801162C, f"b.w 0x{epilogue:X}"),
                 "About: render retained fault record")
        img.crash = dict(record=record, handler=handler, show=show)
