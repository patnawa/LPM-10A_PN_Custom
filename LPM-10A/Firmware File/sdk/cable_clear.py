"""PN 2.20: the Cable Test's text line is wiped before every test.

Owner's report on PN 2.19 (2026-09-21): the cable in a switch (or the RX unit) passes,
every wire green, and "Not connected" is still on the screen.  Reproduced on the CPU
model: Test Retry from the result screen runs the wire-map routine straight away, which
redraws the frame and the wires (y 55..270) but never the text line under them
(y 271..286), so the "Not connected" of the previous, unplugged test stays.  Stock had
the same hole for its own "Result error!!" (drawn only for an unidentified reading, so
it was rarely seen).

Fix, two bl sites: the frame redraw both routines start with (`bl 0x0800D170` at
0x0800C4F4 far end / 0x0800CB7A switch) goes through a hook that draws the frame as before
and then fills the text line, x 40..200, y 271..286, with the panel colour 0x31A7.  The
routine's own text ("Result error!!") and PN 2.19's "Not connected" are drawn after it, so
a fresh message still shows; a stale one cannot.
"""
import hashlib

from lpm10a.image import PatchError
from lpm10a.thumb import assemble


PATCH_ID = 'cable-text-clear'
VERSION = 'PN 2.20'
PARENT_SHA256 = '8353e0b018d9ad2de7a98f3fe72ff8812dbc431504dbcf36adcc5b7fc080725d'   # PN 2.19

FRAME_DRAW = 0x0800D170         # (1, &0x20000011): the Cable Test frame and pin numbers
FRAME_SITES = {0x0800C4F4: '00f03cfe', 0x0800CB7A: '00f0f9fa'}                  # bl 0x0800D170 (far end, switch)
DRAW_SHAPE = 0x08016D08         # (x0, y0, x1, y1, [sp] = colour): inclusive fill
PANEL = 0x31A7
BAND = (40, 271, 200, 286)      # the text line under the wire frame (frame ends at 270, the button starts at 289)


def register(patch):
    @patch(PATCH_ID, "Cable Test: the text line under the wires is wiped before every test (stale 'Not connected')",
           risk='low', default=False, group='measure', requires=('cable-robust',))
    def cable_text_clear(img):
        img.finalize()
        if hashlib.sha256(bytes(img.data)).hexdigest() != PARENT_SHA256:
            raise PatchError('cable-text-clear requires the exact finalized PN 2.19 parent')
        for site, stock in FRAME_SITES.items():
            if img.read(site, 4).hex() != stock:
                raise PatchError(f'cable-text-clear: 0x{site:08X} is not the frame redraw call')
        x0, y0, x1, y1 = BAND
        hook = img.emit_code(f'''
        frame_hook:                     ; the frame redraw at the start of both wire-map routines, then a clean text line
                push {{r4, lr}}
                sub  sp, #8
                bl   {FRAME_DRAW}
                movw r0, #{PANEL}
                str  r0, [sp]
                movs r0, #{x0}
                movw r1, #{y0}
                movs r2, #{x1}
                movw r3, #{y1}
                bl   {DRAW_SHAPE}
                add  sp, #8
                pop  {{r4, pc}}
        ''', why='Cable Test: wipe the text line under the wires before every test')
        for site, stock in FRAME_SITES.items():
            img.poke(site, stock, assemble(site, f'bl {hook}'), 'wire map: frame redraw + a clean text line')
        for site in (0x08011660, 0x08012E6C):
            img.set_string(site, VERSION)
        img.cable_clear = dict(hook=hook, band=BAND)
