"""PN 2.19: the Cable Test (wire map) stops guessing on an unconnected cable, and says so.

How stock measures (0x0800C4E0 far-end mode, 0x0800CB68 switch mode, both in the CNT
task): for each of the nine tester pins (1..8 and the shield, "G") it drives that pin
through the source mux and reads the other eight through the sense mux into ADC
channel 4, one sample each, 2 ms after switching.  A pin counts as OPEN only when all
eight readings are above 4000 of 4095 -- 95 counts, about 77 mV, under the rail.  With
nothing at the far end every wire floats on the tester's pull-up, and an unterminated
cable picks up enough mains hum for single samples to wander below 4000 now and then.
Switch mode then calls the pin "connected" (its rule: any other pin at or below 4000),
far-end mode goes on to identify which remote pin it reached (windows of +-5 % around
1655 .. 3900, the last of which touches the rail) -- a different random answer on every
Test Retry.  The owner sees random open / crossed wires on a cable that is simply not
plugged into anything.  There is no consistency check and no "nothing connected" state.

PN 2.19, four sites and two strings, nothing else:

  * sampling: the one `movs r0, #4; bl adc_read` of each routine becomes `bl sample`,
    which takes eleven samples one millisecond apart (a whole half-cycle of 50 Hz) and
    returns their median.  A floating wire sits at the rail with hum riding on it, so its
    median is at the rail; a real connection is steady and low.  The routines' own
    thresholds, windows and drawing are untouched, except that far-end mode's open test
    ("all eight sensed pins above 4000") judges each pin's HIGHEST sample: a floating
    wire touches the rail within a half-cycle whatever the hum, a wire that reaches the
    RX unit's ladder does not.  The test takes about 0.9 s instead of 0.15 s.  min /
    median / max of every (driven, sensed) pair are kept in the RAM arena for the
    cable-diag build.
  * switch mode: "connected" was any reading <= 4000; it is now <= 1240 (0x4D8), the
    value the far-end routine itself uses for a direct short.  A switch port joins the
    two wires of a pair through its transformer winding (an ohm or two; at most a
    Bob-Smith 150 ohm path on unused pairs), which reads far below 1240, while a
    floating wire whose level has drifted under 4000 no longer passes.
  * "Not connected": when all eight signal pins come back OPEN (the shield is ignored,
    as stock's LED rule ignores it) the result gets a red "Not connected" /
    "ไม่พบปลายสาย" line where stock prints "Result error!!" (which it prints only for an
    unidentified reading, never for open wires) -- the far end is not plugged into a
    switch or the RX unit.  The wires stay red as before; the mux-release call both
    routines end with is where the check runs.
  * the second mode is named for what you plug in: "RX unit" instead of "Far end"
    (the u16 string at 0x0801E310, same 8 units), "เครื่องรับ" instead of "ปลายสาย"
    (RELOC pointer of that text -> a new cell string in the cave).

cable-diag (not in any profile; `--with cable-diag --out ...`): the result screen also
prints, on every row, the lowest median among the eight sensed pins, which pin it was
and that pin's highest sample -- the numbers that decide the result.  For the owner's
four measurements: nothing plugged in, a cable open at the far end, the cable in a
switch, the cable in the RX unit.
"""
import hashlib
import struct

from lpm10a.image import PatchError
from lpm10a.thumb import assemble


PATCH_ID = 'cable-robust'
DIAG_ID = 'cable-diag'
VERSION = 'PN 2.19'
PARENT_SHA256 = 'b5538e723044e540b497f37de2550bb715ec9113316a683600e1d81b768c8a9f'   # PN 2.18

ADC_READ = 0x080107A4           # (channel) -> the latest DMA sample of that ADC channel
SAMPLE_SITES = {0x0800C544: '0420 04f02df9', 0x0800CBCA: '0420 03f0eafd'}   # movs r0, #4; bl adc_read (far end, switch)
SWITCH_OPEN = 0x0800CBEA        # switch mode: cmp.w r0, #0xFA0 (readings above this count towards "open")
SWITCH_OPEN_STOCK, SWITCH_OPEN_NEW = 'b0f57a6f', 'b0f59b6f'                  # 4000 -> 1240
FAR_OPEN_SITE, FAR_OPEN_STOCK = 0x0800C5A8, 'd348 30f81500'                   # far end, open test: ldr r0, =adc; ldrh.w r0, [r0, r5, lsl #1]
RELEASE_SITES = {0x0800CB18: '0cf090f8', 0x0800CE76: '0bf0e1fe'}               # bl 0x08018C3C (mux release) after the result
MUX_RELEASE = 0x08018C3C
ERROR_Y_SITES = {0x0800CAF2: 'd830', 0x0800CE4E: 'd830'}                       # adds r0, #0xD8: "Result error!!" at y 55 + 216 (cable-error-visible)
NOT_CONNECTED_Y = 55 + 0xD8
FAR_END_STRING = 0x0801E310     # u16 "Far end\0" in the mode selector's layout table (8 units)
STATUS = 0x2000023E             # nine result codes: 0 short, 1 open, 2 ok, 3 crossed, 4 unknown
LANG_IS = 0x0800FD2C
CJK_TEXT = 0x080176AC
GUI_BLIT = 0x080174E8
SAMPLES = 11                    # one millisecond apart: a half-cycle of 50 Hz, 60 Hz too
LABEL_EN, LABEL_TH = 'RX unit', 'เครื่องรับ'
NOT_CONNECTED_EN, NOT_CONNECTED_TH = 'Not connected', 'ไม่พบปลายสาย'
ROW0_Y, ROW_PITCH = 68, 24      # wire rows of the result screen
DIAG_X = 128


def u16(text):
    """The hex of a little-endian u16 unit string with its terminator (the mixed drawer's format)."""
    return ''.join(f'{ord(c) & 0xFF:02x}{ord(c) >> 8:02x}' for c in text) + '0000'


def register(patch):
    @patch(PATCH_ID, "Cable Test: median of 11 samples, switch mode needs a real short, 'Not connected', mode named RX unit",
           risk='low', default=False, group='measure',
           requires=('thai-ui', 'cable-error-visible', 'length-reference'))
    def cable_robust(img):
        img.finalize()
        if hashlib.sha256(bytes(img.data)).hexdigest() != PARENT_SHA256:
            raise PatchError('cable-robust requires the exact finalized PN 2.18 parent')
        for site, stock in {**SAMPLE_SITES, **RELEASE_SITES, **ERROR_Y_SITES, SWITCH_OPEN: SWITCH_OPEN_STOCK,
                            FAR_OPEN_SITE: FAR_OPEN_STOCK}.items():
            if img.read(site, len(bytes.fromhex(stock.replace(' ', '')))).hex() != stock.replace(' ', ''):
                raise PatchError(f'cable-robust: 0x{site:08X} is not the stock code')
        if img.read(FAR_END_STRING, 16).hex() != u16('Far end'):
            raise PatchError('cable-robust: the mode label is not "Far end"')
        table, texts, reloc = img.thai['table'], img.thai['texts'], img.thai['reloc']
        idx = texts.index('ปลายสาย')
        tables = img.alloc_ram(3 * 9 * 8 * 2)           # u16 median / min / max per (driven pin, sensed slot)
        med, lo, hi = tables, tables + 144, tables + 288

        sample = img.emit_code(f'''
        sample:                         ; replaces adc_read(4) in both wire-map routines (r4 = driven pin, r5 = sensed slot there)
                push {{r4, r5, r6, r7, lr}}
                sub  sp, #28            ; the sorted samples (11 x u16), 8-aligned frame
                mov  r6, sp
                movs r7, #0
        next:   movs r0, #4
                bl   ADC_READ
                mov  r1, r6             ; insert r0 into the sorted buffer
                lsls r2, r7, #1
                add  r1, r2
        ins:    cmp  r1, r6
                beq  put
                subs r1, #2
                ldrh r2, [r1]
                cmp  r2, r0
                bls  put_after
                strh r2, [r1, #2]
                b    ins
        put_after:
                adds r1, #2
        put:    strh r0, [r1]
                adds r7, #1
                cmp  r7, #{SAMPLES}
                beq  done
                movs r0, #1
                bl   vTaskDelay
                b    next
        done:   lsls r0, r4, #3         ; (driven * 8 + slot) * 2
                add  r0, r5
                lsls r0, r0, #1
                ldr  r1, =MED
                add  r1, r0
                ldrh r2, [r6, #{(SAMPLES // 2) * 2}]
                strh r2, [r1]
                ldr  r1, =LO
                add  r1, r0
                ldrh r2, [r6]
                strh r2, [r1]
                ldr  r1, =HI
                add  r1, r0
                ldrh r2, [r6, #{(SAMPLES - 1) * 2}]
                strh r2, [r1]
                ldrh r0, [r6, #{(SAMPLES // 2) * 2}]
                add  sp, #28
                pop  {{r4, r5, r6, r7, pc}}
        ''', extra_syms=dict(ADC_READ=ADC_READ | 1, MED=med, LO=lo, HI=hi),
            why=f'Cable Test: median of {SAMPLES} ADC samples 1 ms apart instead of one')

        hi_slot = img.emit_code('''
        hi_slot:                        ; far-end open test: r0 = the highest sample of (driven r4, slot r5), not the median
                lsls r0, r4, #3
                add  r0, r5
                lsls r0, r0, #1
                ldr  r1, =HI
                add  r1, r0
                ldrh r0, [r1]
                bx   lr
        ''', extra_syms=dict(HI=hi), why='Cable Test far end: the open test judges the highest sample')

        not_connected_th = table.encode_cjk(NOT_CONNECTED_TH)
        label_th = table.encode_cjk(LABEL_TH)
        nc_th_addr = img.emit_code('.byte ' + ', '.join(str(b) for b in not_connected_th),
                                   why=f'Thai cells "{NOT_CONNECTED_TH}"')
        label_th_addr = img.emit_code('.byte ' + ', '.join(str(b) for b in label_th),
                                      why=f'Thai cells "{LABEL_TH}" (RELOC target of the mode label)')
        release = img.emit_code(f'''
        release_hook:                   ; the mux release at the end of both routines, then "Not connected" if it applies
                push {{r4, lr}}
                sub  sp, #8
                bl   {MUX_RELEASE}
                ldr  r4, =STATUS
                movs r1, #0
        chk:    ldrb r0, [r4]
                cmp  r0, #1             ; 1 = open
                bne  done
                adds r4, #1
                adds r1, #1
                cmp  r1, #8             ; the eight signal pins; the shield is not a fault (stock's LED rule ignores it too)
                blt  chk
                ldr  r0, =0x200001AC    ; red, like the wires and stock's own "Result error!!"
                movw r1, #0xF800
                strh r1, [r0]
                movs r0, #2
                bl   {LANG_IS}
                cmp  r0, #0
                bne  thai
                movs r0, #16
                str  r0, [sp]
                ldr  r0, =not_connected
                str  r0, [sp, #4]
                movs r0, #{120 - 4 * len(NOT_CONNECTED_EN)}
                movw r1, #{NOT_CONNECTED_Y}
                movs r2, #{8 * len(NOT_CONNECTED_EN)}
                movs r3, #16
                bl   gui_blit
                b    done
        thai:   movs r0, #120           ; centred on x by the proportional drawer (count 1)
                movw r1, #{NOT_CONNECTED_Y}
                ldr  r2, =NC_TH
                movs r3, #1
                bl   {CJK_TEXT}
        done:   add  sp, #8
                pop  {{r4, pc}}
        not_connected:
                .asciz "{NOT_CONNECTED_EN}"
        ''', extra_syms=dict(STATUS=STATUS, NC_TH=nc_th_addr),
            why='Cable Test: "Not connected" when every signal pin is open')

        for site, stock in SAMPLE_SITES.items():
            img.poke(site, stock, assemble(site, f'bl {sample}\n nop'), 'wire map: median of 11 samples per sensed pin')
        img.poke(SWITCH_OPEN, SWITCH_OPEN_STOCK, bytes.fromhex(SWITCH_OPEN_NEW),
                 'switch mode: a pin is connected only through a real short (<= 1240), not anything under 4000')
        img.poke(FAR_OPEN_SITE, FAR_OPEN_STOCK, assemble(FAR_OPEN_SITE, f'bl {hi_slot}' + chr(10) + ' nop'),
                 "far-end mode: a pin is open when every sensed pin's highest sample is above 4000")
        for site, stock in RELEASE_SITES.items():
            img.poke(site, stock, assemble(site, f'bl {release}'), 'wire map: "Not connected" when every signal pin is open')
        img.poke(FAR_END_STRING, u16('Far end'), bytes.fromhex(u16(LABEL_EN)), f'Cable Test mode: "Far end" -> "{LABEL_EN}"')
        ptr = reloc + 4 * idx
        img.poke(ptr, img.read(ptr, 4).hex(), struct.pack('<I', label_th_addr), f'Thai mode label -> "{LABEL_TH}"')
        for site in (0x08011660, 0x08012E6C):
            img.set_string(site, VERSION)
        img.cable = dict(sample=sample, release=release, hi_slot=hi_slot, med=med, lo=lo, hi=hi,
                         label_th=label_th_addr, not_connected_th=nc_th_addr)

    @patch(DIAG_ID, 'EXPERIMENT: the wire-map result prints the lowest median, its pin and that pin\'s highest sample per row',
           risk='low', default=False, group='measure', requires=(PATCH_ID,))
    def cable_diag(img):
        release, med, hi = img.cable['release'], img.cable['med'], img.cable['hi']
        for site in RELEASE_SITES:
            if img.read(site, 4) != assemble(site, f'bl {release}'):
                raise PatchError(f"cable-diag: 0x{site:08X} does not call cable-robust's release hook")
        diag = img.emit_code(f'''
        diag:                           ; after the result is drawn: per driven pin, the deciding numbers
                push {{r4, r5, r6, r7, lr}}
                sub  sp, #28            ; [sp..8) blit args, [sp+8..28) text
                bl   {release}          ; cable-robust: mux release and "Not connected"
                ldr  r0, =0x200001AC
                movw r1, #0xFFFF
                strh r1, [r0]
                movw r1, #0x2105
                strh r1, [r0, #2]
                movs r4, #0             ; driven pin
        row:    lsls r5, r4, #3
                movs r6, #0             ; slot of the lowest median
                movw r7, #0xFFFF        ; the lowest median
                movs r1, #0
        scan:   adds r2, r5, r1
                lsls r2, r2, #1
                ldr  r3, =MED
                add  r3, r2
                ldrh r3, [r3]
                cmp  r3, r7
                bhs  scan_next
                mov  r7, r3
                mov  r6, r1
        scan_next:
                adds r1, #1
                cmp  r1, #8
                blt  scan
                adds r2, r5, r6         ; that slot's highest sample
                lsls r2, r2, #1
                ldr  r3, =HI
                add  r3, r2
                ldrh r3, [r3]
                str  r3, [sp]           ; vararg 3
                cmp  r4, r6             ; the sensed pin behind the slot: slot + 1 from the driven pin on
                bgt  named
                adds r6, #1
        named:  movs r2, #0x2D          ; '-' when nothing read under 4000
                movw r0, #4000
                cmp  r7, r0
                bhi  fmt
                movs r2, #0x47          ; 'G'
                cmp  r6, #8
                beq  fmt
                movs r2, #0x31          ; '1' + pin
                add  r2, r6
        fmt:    str  r2, [sp, #4]       ; the pin character; the firmware's sprintf has no %c, so it is stored by hand
                mov  r2, r7             ; the lowest median
                ldr  r3, [sp]           ; that pin's highest sample
                ldr  r1, =fmt_row
                mov  r0, sp
                adds r0, #8
                bl   sprintf
                ldr  r2, [sp, #4]
                mov  r0, sp
                adds r0, #8
                strb r2, [r0]
                movs r0, #12
                str  r0, [sp]
                mov  r0, sp
                adds r0, #8
                str  r0, [sp, #4]
                movs r0, #{ROW_PITCH}
                muls r0, r4, r0
                adds r0, #{ROW0_Y - 6}
                mov  r1, r0
                movs r0, #{DIAG_X}
                movs r2, #66
                movs r3, #12
                bl   gui_blit
                adds r4, #1
                cmp  r4, #9
                blt  row
                add  sp, #28
                pop  {{r4, r5, r6, r7, pc}}
        fmt_row: .asciz "?%5d%5d"
        ''', extra_syms=dict(MED=med, HI=hi), why='Cable Test diag: lowest median, its pin, that pin\'s highest sample')
        for site in RELEASE_SITES:
            img.poke(site, assemble(site, f'bl {release}').hex(), assemble(site, f'bl {diag}'),
                     'wire map: print the deciding numbers per row')
        img.cable['diag'] = diag
