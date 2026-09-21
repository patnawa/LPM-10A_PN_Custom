"""PN 2.12 candidate: drive Port FLASH from MDIO link status, not GPIO level."""
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB
from lpm10a.image import PatchError
from lpm10a.thumb import assemble

PATCH_ID = 'portflash-phy-status'
VERSION = 'PN 2.12'


def register(patch):
    @patch(PATCH_ID, 'Use PHY link status for FLASH control and its indicator',
           risk='low', default=False, group='flash',
           requires=('portflash-recovery', 'battery-during-flash', 'settings-save-static'))
    def status(img):
        # MII BMSR bit 2 is link, latched low. Clear a historical drop with the
        # first read and use the second current value. The vendor MDIO reader
        # has no error return; reject all-ones bus reads instead of false link.
        link = img.emit_code('''
            push {r4, lr}
            movs r0, #1
            bl mdio_read
            mov r4, r0
            movs r0, #1
            bl mdio_read
            movw r1, #0xFFFF
            cmp r4, r1
            beq invalid
            cmp r0, r1
            beq invalid
            lsrs r0, r0, #2
            movs r1, #1
            ands r0, r1
            pop {r4, pc}
        invalid:
            movs r0, #0
            pop {r4, pc}
        ''', why='FLASH: read current BMSR link, clear latch-low and reject invalid MDIO')

        start, end = img.flash['tick'], img.flash['tick_end']
        md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
        sites = [i.address for i in md.disasm(img.read(start, end-start), start)
                 if i.mnemonic == 'bl' and i.op_str == '#0x8015af2']
        if len(sites) != 2:
            raise PatchError('expected both acquisition and hold GPIO calls in FLASH handler')
        for site in sites:
            img.poke(site, assemble(site, 'bl GPIO_ReadInputDataBit', img.syms).hex(),
                     assemble(site, f'bl {link}'), 'FLASH link decisions use PHY status')

        # APP_Flash_task is a different task. Read the already-published phase
        # here; do not introduce a concurrent bit-banged MDIO transaction.
        # Phase 1 means the net task observed link up; 0/2/3 are not linked.
        indicator = img.emit_code('''
            ldr r0, =0x20000076
            ldrb r0, [r0]
            cmp r0, #1
            beq linked
            movs r0, #0
            bx lr
        linked:
            movs r0, #1
            bx lr
        ''', why='FLASH screen/LED uses the net task link phase without accessing MDIO')
        site = 0x0800DC6C
        img.poke(site, assemble(site, 'bl GPIO_ReadInputDataBit', img.syms).hex(),
                 assemble(site, f'bl {indicator}'), 'FLASH indicator follows the same link source')
        img.flash_status = dict(link=link, indicator=indicator, sites=sites)
        for site in (0x08011660, 0x08012E6C):
            img.set_string(site, VERSION)
