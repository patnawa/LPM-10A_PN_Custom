"""PN 1.11 candidate: faster Digital tracking and finer Analog feedback.

The complete PN 1.9 parent supplies the proven mode/gate ownership contracts.
Sync32 is deliberately absent from this profile. All edits remain within the
existing raw RX image; no bootloader, license or version-page changes occur.
"""
import hashlib

from lpm10rx.image import PatchError

PATCHES = {'rx-tracking'}
OUTPUT = 'experimental/APP_LPM-10RX_PN1.11-tracking.bin'
PREVIOUS_SHA256 = '6128e0a4a0261f3da51bea232c8e431474033f0a09fd24283faa0a743b67fe3e'


def apply(img):
    if hashlib.sha256(img.data).hexdigest() != PREVIOUS_SHA256:
        raise PatchError('rx-tracking requires the complete, exact PN 1.9 profile')
    import analog_fast
    import analog_integer
    import analog_feedback
    import digital_overlap
    import digital_tracking

    analog_fast.apply(img)
    analog_integer.apply(img)
    analog_feedback.apply(img)
    digital_overlap.apply(img)
    digital_tracking.apply(img)
    img.tracking = True


def register(patch):
    patch('rx-tracking', 'Overlapping Digital acquisition and finer, faster Analog feedback',
          risk='untested', default=False, group='scan')(apply)
