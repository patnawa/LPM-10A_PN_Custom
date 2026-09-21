"""PN 2.15: the Length screen counts the averaging runs while it tests.

Since PN 1.2 a Length test runs the PHY's cable diagnostic AVG_RUNS (4) times and
averages the runs, so it takes about four times as long as stock; the screen showed
only "Testing" and the "..." animation for the whole wait.  PN 2.15 draws "1/4" ..
"4/4" at the right end of the Testing line, one step per run, so the wait is
understood.  Nothing about the measurement changes.

Mechanics.  APP_LENG_Test_Sequence starts every run at 0x08011A6E with
`bl 0x08019C38` (post GUI msg 0x1B, then the "Testing" label through
gui_draw_text_box); the stock retry path increments the run counter [sp+0x24] and
branches back there, which is what length-average's re-run uses too.  That bl becomes
`bl run_hook`: the hook calls the stock routine, builds "n/N" from the counter in a
4-byte RAM cell and posts it as one more text box at (192, 175) -- the Testing line
(layout table 0x0801E620: x 7 / y 170, +5), 8x16 white on the box colour 0x2105,
right-aligned inside the box (border at x 225).  gui_draw_text_box copies the string
into its GUI message, so the cell is only a scratch buffer, and the three messages
(0x1B, "Testing", the counter) are drawn in order by the GUI task.  The "..." frames
(x 68..92 English, 82..106 Thai), the "Test timeout!!" text (x 68..180) and the
result redraw are stock's; the Thai blit hook leaves the counter alone because it
matches only its own table keys, so the digits are drawn the same in both languages.
"""
import hashlib
import struct

from lpm10a.image import PatchError
from lpm10a.thumb import assemble


PATCH_ID = 'length-progress'
VERSION = 'PN 2.15'
PARENT_SHA256 = 'a7402de6f18e39df55bbe53f5641efd5135f0de4d81f9407515cf9d8710c5527'   # PN 2.14
SITE = 0x08011A6E              # APP_LENG_Test_Sequence: the first instruction of every run
STOCK_CALL = '08f0e3f8'        # bl 0x08019C38
TESTING_DRAW = 0x08019C38      # msg 0x1B + the "Testing" label
TEXT_BOX = 0x0800EF6C          # gui_draw_text_box(x, y, bg, fg, [sp]=size, [sp+4]=str)
LAYOUT = 0x0801E620            # the Testing line's (x, y) in the Length layout table
COUNTER_X = 192                # 3 characters end at 216; the box border is at 225
BOX_BG, WHITE = 0x2105, 0xFFFF


def register(patch):
    @patch(PATCH_ID, 'Length: the Testing line counts the averaging runs (1/4 .. 4/4)',
           risk='low', default=False, group='measure',
           requires=('length-average', 'scan-recovery'))
    def length_progress(img):
        import patches
        img.finalize()
        if hashlib.sha256(bytes(img.data)).hexdigest() != PARENT_SHA256:
            raise PatchError('length-progress requires the exact finalized PN 2.14 parent')
        runs = patches.AVG_RUNS
        if not 2 <= runs <= 9:
            raise PatchError('length-progress needs AVG_RUNS 2..9: one digit, and something to count')
        x0, y0 = struct.unpack('<HH', img.read(LAYOUT, 4))
        if (x0, y0) != (7, 170):
            raise PatchError(f'length-progress: the Testing line moved ({x0}, {y0})')
        if img.read(SITE, 4).hex() != STOCK_CALL:
            raise PatchError('length-progress: the run entry is not the stock Testing call')
        y = y0 + 5
        cell = img.alloc_ram(4)                      # "n/N\0", copied by gui_draw_text_box
        hook = img.emit_code(f'''
        run_hook:                       ; from 0x08011A6E, once per CSD run; the sequence frame is the caller's
                push {{r4, lr}}
                bl   {TESTING_DRAW}     ; stock: msg 0x1B, then the "Testing" label
                ldr  r0, [sp, #0x2C]    ; the run counter [sp+0x24] of the sequence, +8 for the push
                ldr  r4, =CELL
                adds r0, #0x31          ; '1' + run
                strb r0, [r4]
                movs r0, #0x2F          ; '/'
                strb r0, [r4, #1]
                movs r0, #{0x30 + runs}
                strb r0, [r4, #2]
                movs r0, #0
                strb r0, [r4, #3]
                sub  sp, #8
                movs r0, #0x10          ; 8x16 ASCII, left aligned
                str  r0, [sp]
                str  r4, [sp, #4]
                movs r0, #{COUNTER_X}
                movs r1, #{y}
                movw r2, #{BOX_BG}
                movw r3, #{WHITE}
                bl   {TEXT_BOX}
                add  sp, #8
                pop  {{r4, pc}}
                .pool
        ''', extra_syms=dict(CELL=cell), why=f'Length: "n/{runs}" run counter on the Testing line')
        img.poke(SITE, STOCK_CALL, assemble(SITE, f'bl {hook}'),
                 'APP_LENG_Test_Sequence: every run starts by drawing its number')
        for site in (0x08011660, 0x08012E6C):
            img.set_string(site, VERSION)
        img.length_progress = dict(hook=hook, cell=cell, x=COUNTER_X, y=y, runs=runs)
