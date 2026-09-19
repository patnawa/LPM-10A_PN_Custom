"""Additional TX audit fixes, opt-in on top of the PN 2.10 FLASH candidate."""
from lpm10a.thumb import assemble

PATCHES = ('battery-during-flash', 'settings-save-static')
VERSION = 'PN 2.11'


def register(patch):
    @patch(PATCHES[0], 'Keep battery monitoring active during Port FLASH',
           risk='untested', default=False, group='power',
           requires=('portflash-recovery', 'isr-event-worker'))
    def battery(img):
        # These are the only two callers of test_in_progress: the battery
        # event gate in SysTick and the battery UI routine. Keep the original
        # shared helper untouched, and retain suppression during PHY setup/TDR.
        guard = img.emit_code('''
            ldr r0, =0x2000013C
            ldrb r0, [r0]
            cmp r0, #6
            bne original
            ldr r0, =0x200002B5
            ldrb r0, [r0]
            cmp r0, #2
            bne original
            movs r0, #0
            bx lr
        original:
            b.w test_in_progress
        ''', why='battery-only busy gate: active FLASH must not suppress low-voltage monitoring')
        for site in (0x0800E6BA, 0x0801BD7C):
            img.poke(site, assemble(site, 'bl test_in_progress', img.syms).hex(),
                     assemble(site, f'bl {guard}'), 'battery monitoring remains enabled during FLASH')
        img.battery_busy_guard = guard

    @patch(PATCHES[1], 'Use the checked static settings writer for every save path',
           risk='untested', default=False, group='reliability',
           requires=('calibration-autosave', 'portflash-recovery'))
    def settings(img):
        # All three callers run in APP_HOME task context: explicit save,
        # default initialization/factory reset, and power_off. Their return
        # value is ignored, as before. Share autosave's scheduler serialization
        # and checked erase/program/readback path, avoiding NULL heap writes.
        for site in (0x0800F94E, 0x0800FE3A, 0x08016690):
            img.poke(site, assemble(site, 'bl APP_Home_Cust_Info_Storage', img.syms).hex(),
                     assemble(site, f'bl {img.autosave["save"]}'),
                     'normal/default/power-off settings save: checked static writer')
        for site in (0x08011660, 0x08012E6C):
            img.set_string(site, VERSION)
