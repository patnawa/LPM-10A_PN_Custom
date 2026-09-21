"""PN 1.19: the strongest rhythm is reached where the front end saturates.

Applies only to the complete, exact PN 1.18 image.

Live captures (docs/RX-SENSITIVITY-2026-09-21.md) show the analogue front end
itself limits at roughly 2000-2600 ADC counts peak-to-peak on the high gain
steps (codes 4-7), well before the 4095 rail, so the contrast score at maximum
knob never exceeds about 35 000-40 000 however close the probe is.  On the
middle gain step (780 p-p unclipped) the same closeness gives 25 000 x 2.6 =
65 000 after the PN 1.15 normalisation, so with the curve's fastest point at
88 000 the middle of the knob sounded *stronger* than maximum on the cable
(owner, 2026-09-21: "ตรงกลางแรงกว่าหมุนสุด").

PN 1.19 moves the curve's last knot from 88 000 to 40 000 (the measured
saturation), so touching the cable gives the fastest rhythm (20 ms) at every
knob position, while readings in the linear region are unchanged below 24 000
and only slightly faster between 24 000 and 40 000 (e.g. 34 000 -> 29 ms
instead of 41 ms).  Only the last table span changes (64 000 -> 16 000).
"""
import hashlib

from lpm10rx.image import PatchError

PATCHES = {'rx-strong-cap'}
OUTPUT = 'experimental/APP_LPM-10RX_PN1.19-strong-cap.bin'
PARENT_SHA256 = '6663b515fd912d611c40801e4f1997cdcce6d9518da86efe685561ab98aae5ee'
PREVIOUS_SHA256 = PARENT_SHA256

TABLE = 0x080084FC
LAST_SPAN_OFFSET = 16          # fifth segment: u16 span, u8 45, u8 20
OLD_TOP, NEW_TOP = 88000, 40000
SCORES = (0, 800, 2400, 7200, 24000, NEW_TOP)
GAPS = (110, 95, 85, 70, 45, 20)


def apply(img):
    if hashlib.sha256(bytes(img.data)).hexdigest() != PARENT_SHA256:
        raise PatchError('rx-strong-cap requires the complete, exact PN 1.18 profile')
    old = (OLD_TOP - 24000).to_bytes(2, 'little') + bytes([45, 20])
    new = (NEW_TOP - 24000).to_bytes(2, 'little') + bytes([45, 20])
    img.poke(TABLE + LAST_SPAN_OFFSET, old.hex(), new,
             'strength curve: fastest rhythm at 40 000 (front-end saturation) instead of 88 000')
    img.strong_cap = {'parent_sha256': PARENT_SHA256, 'top_score': NEW_TOP}


def register(patch):
    patch('rx-strong-cap', 'Fastest rhythm at the front-end saturation score (40 000)',
          risk='untested', default=False, group='audio')(apply)
