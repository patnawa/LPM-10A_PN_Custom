"""PN 1.18: a clipped (upper-railed) reading sounds strongest, not 'uncertain'.

Applies only to the complete, exact PN 1.17 image.

Since PN 1.9 (Digital) and PN 1.11 (Analog) a window whose ADC samples sit on
the upper rail publishes the interval value 1, which the repeat scheduler turns
into 100 ms pulses with 160 ms gaps -- deliberately "not a strength reading".
With PN 1.15-1.17 the knob no longer has to be near maximum, and the owner now
hears the flip side: **at maximum knob a nearby cable clips the front end and
the rhythm goes sparse ("signal weak"), while the middle of the knob sounds
strong** (2026-09-21, both modes).

Clipping only happens when the signal is very strong, and the knob exists to
attenuate it, so PN 1.18 makes the publisher map the 'uncertain' value 1 to the
fastest normal rhythm (20 ms quiet interval, 30 ms pulses).  Nothing else
changes: the 100/160 ms pattern is simply never selected, the detectors still
decide acceptance exactly as before, and the PN 1.17 smoothing takes over as
soon as an unclipped reading returns.  To separate two strong cables, turn the
knob down as on the stock firmware.
"""
import hashlib

from lpm10rx.image import PatchError
import release_hold

PATCHES = {'rx-rail-strong'}
OUTPUT = 'experimental/APP_LPM-10RX_PN1.18-rail-strong.bin'
PARENT_SHA256 = '80468c77d837d6798cc5205d65028424a421b3ae82c8f6659bbe40382a4feb7e'
PREVIOUS_SHA256 = PARENT_SHA256

PUBLISHER = 0x0800CEA8         # the PN 1.16 publisher helper (96 bytes reserved)
FASTEST_MS = 20

HELPER_SOURCE = release_hold.HELPER_SOURCE.replace(
    "    strb r1, [r2, #0x15]        ; accepted: new quiet interval (1 = uncertain)\n",
    f"    cmp r1, #1\n    bne store\n    movs r1, #{FASTEST_MS}              ; clipped/'uncertain' reading: strongest rhythm\nstore:\n    strb r1, [r2, #0x15]        ; accepted: new quiet interval\n")


def apply(img):
    if hashlib.sha256(bytes(img.data)).hexdigest() != PARENT_SHA256:
        raise PatchError('rx-rail-strong requires the complete, exact PN 1.17 profile')
    old = img.assemble_at(PUBLISHER, release_hold.HELPER_SOURCE)
    old = old + bytes(96 - len(old))
    if img.read(PUBLISHER, 96) != old:
        raise PatchError(f'rail-strong: PN 1.16 publisher not found at {PUBLISHER:#x}')
    code = img.assemble_at(PUBLISHER, HELPER_SOURCE)
    if len(code) > 96:
        raise PatchError(f'rail-strong publisher is {len(code)} bytes; 96 reserved')
    img.poke(PUBLISHER, old.hex(), code + bytes(96 - len(code)),
             "publisher: interval 1 ('uncertain'/clipped) -> 20 ms, the strongest normal rhythm")
    img.rail_strong = {'parent_sha256': PARENT_SHA256, 'publisher': PUBLISHER,
                       'fastest_ms': FASTEST_MS, 'persistent_ram_bytes': 0}


def register(patch):
    patch('rx-rail-strong', 'Clipped readings sound strongest instead of sparse/uncertain',
          risk='untested', default=False, group='audio')(apply)
