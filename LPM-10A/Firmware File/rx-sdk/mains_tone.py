"""PN 1.23: the mains (50/60 Hz) mode gets its own pitch, 5 kHz.

Applies to the untagged PN 1.22 image.

PN 1.14 gave Digital 2.5 kHz and Analog 1.25 kHz; mains kept Digital's 2.5 kHz.
The mode-tone helper's mains path still flips the speaker duty every 8th TIM5
interrupt (`lsls r0, r0, #29` on the 40 kHz tick).  PN 1.23 changes that one
shift to #30, i.e. every 4th interrupt = a 5 kHz tone, so each of the three
modes has a distinct pitch (Analog low, Digital middle, mains high).  Mains
feedback itself is unchanged: the stock three-tier beep length (50 / 100 / 200
ms per 99 ms window by 50/60 Hz DFT level) is kept because mains detection uses
a different input (PD15) that is not behind the gain stage, so the
knob-normalised rhythm curve would not apply to it.
"""
import hashlib

from lpm10rx.image import PatchError

PATCHES = {'rx-mains-tone'}
OUTPUT = 'experimental/APP_LPM-10RX_PN1.23-mains-tone.bin'
PARENT_SHA256 = 'aeed622e2922b126f793968e41b154fab75805773847a647788471a9d33d487a'   # untagged PN 1.22
PREVIOUS_SHA256 = PARENT_SHA256

MAINS_SHIFT = 0x0800CE4E       # mode_tone helper: `lsls r0, r0, #29` (every 8 IRQs = 2.5 kHz)


def apply(img):
    if hashlib.sha256(bytes(img.data)).hexdigest() != PARENT_SHA256:
        raise PatchError('rx-mains-tone requires the complete, exact PN 1.22 chain')
    if img.read(MAINS_SHIFT, 4) != bytes.fromhex('4007 03d1'):
        raise PatchError('mains-tone: the mode-tone mains cadence is not in place')
    img.poke(MAINS_SHIFT, '4007', img.assemble_at(MAINS_SHIFT, 'lsls r0, r0, #30'),
             'mains speaker cadence: every 4 TIM5 IRQs = 5 kHz (Digital 2.5 kHz, Analog 1.25 kHz)')
    img.mains_tone = {'parent_sha256': PARENT_SHA256, 'mains_hz': 5000}


def register(patch):
    patch('rx-mains-tone', 'Mains mode beeps at 5 kHz: three modes, three pitches',
          risk='untested', default=False, group='audio')(apply)
