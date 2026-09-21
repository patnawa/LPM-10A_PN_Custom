"""Opt-in PN 2.10 Port FLASH candidate. Hardware validation is still required."""
from lpm10a.thumb import assemble

VERSION = "PN 2.10"
PATCH_ID = "portflash-recovery"


def register(patch):
    @patch(PATCH_ID, "Correct PHY autoneg register and recover FLASH after link loss",
           risk="low", default=False, group="flash",
           requires=("flash-blink", "version-string"))
    def recovery(img):
        # The vendor applies BMCR's ANENABLE/ANRESTART mask to ANAR (!).
        # Fix both register selectors; retain the original masks and ABI.
        for site in (0x0801D53A, 0x0801D5B4):
            img.poke(site, "0420", assemble(site, "movs r0, #0"),
                     "auto-negotiation control belongs to BMCR (0), not ANAR (4)")

        from patches import FLASH_ON_MS, FLASH_OFF_MS, FLASH_RELINK_MS, FLASH_RELINK_MAX_MS
        syms = dict(START=img.flash["start"], PHASE=0x20000076, FLAGS1=0x200002B5,
                    GET_STATE=0x0800F764, TICKS=0x0801C5B0, GPIO_READ=0x08015AF2,
                    PWR_DOWN=0x0801D178, GPIOB=0x40010C00,
                    T_ON=FLASH_ON_MS, T_OFF=FLASH_OFF_MS,
                    T_RELINK=FLASH_RELINK_MS, T_MAX=FLASH_RELINK_MAX_MS)
        tick = img.emit_code("""
            push {r4, r5, r6, lr}
            movs r0, #0
            bl GET_STATE
            cmp r0, #6
            beq flags
            pop {r4, r5, r6, pc}
        flags:
            ldr r0, =FLAGS1
            ldrb r0, [r0]
            cmp r0, #2
            beq active
            pop {r4, r5, r6, pc}
        active:
            ldr r4, =PHASE
            ldr r5, =START
            bl TICKS
            mov r6, r0
            ldrb r0, [r4]
            cmp r0, #2
            beq dark
            cmp r0, #1
            beq hold
            cmp r0, #3
            beq wait_link
            movw r0, #T_RELINK
            str r0, [r5, #4]
        wait_again:
            str r6, [r5]
            movs r0, #3
            strb r0, [r4]
            b done
        wait_link:
            movs r1, #0x20
            ldr r0, =GPIOB
            bl GPIO_READ
            cmp r0, #0
            beq no_link
            str r6, [r5]
            movs r0, #1
            strb r0, [r4]
            b done
        no_link:
            ldr r1, [r5]
            subs r0, r6, r1
            ldr r1, [r5, #4]
            cmp r0, r1
            bhs retry
            movs r0, #0
            bl PWR_DOWN
            b done
        retry:
            lsls r1, r1, #1
            movw r0, #T_MAX
            cmp r1, r0
            bls limit
            mov r1, r0
        limit:
            str r1, [r5, #4]
            b drop
        hold:
            movs r1, #0x20
            ldr r0, =GPIOB
            bl GPIO_READ
            cmp r0, #0
            beq wait_again         ; observed loss cancels the old hold deadline
            ldr r1, [r5]
            subs r0, r6, r1
            movw r1, #T_ON
            cmp r0, r1
            blo done
        drop:
            movs r0, #1
            bl PWR_DOWN
            bl TICKS              ; start AFTER the power operation returns
            str r0, [r5]
            movs r0, #2
            strb r0, [r4]
            b done
        dark:
            ldr r1, [r5]
            subs r0, r6, r1
            movw r1, #T_OFF
            cmp r0, r1
            blo done
            movs r0, #0
            bl PWR_DOWN
            bl TICKS              ; negotiation gets its full powered-up window
            mov r6, r0
            b wait_again
        done:
            pop {r4, r5, r6, pc}
        """, extra_syms=syms, why="FLASH: restart hold on observed link loss; time completed power operations")
        site = 0x0801494C
        img.poke(site, assemble(site, f'bl {img.flash["tick"]}').hex(),
                 assemble(site, f"bl {tick}"), "route FLASH messages to recovery candidate")
        img.flash["tick"] = tick
        img.flash["tick_end"] = img.cave_ptr
        for site in (0x08011660, 0x08012E6C):
            img.set_string(site, VERSION)
