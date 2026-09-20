"""PN 1.12 candidate: distinguish a fully upper-railed Digital fallback tail.

Applies only to the complete PN 1.11 parent. The existing uncertain indication
is reused instead of publishing an older exact-span strength when all sixteen
newest raw ADC samples are 4095. No extra mode or persistent RAM is introduced.
"""
import hashlib

from lpm10rx.image import PatchError

PATCHES = {'rx-overload'}
OUTPUT = 'experimental/APP_LPM-10RX_PN1.12-overload.bin'
PREVIOUS_SHA256 = '3e39ae56832cf92881ffdc46564e293278d6c3f1b55a9832b7a9a8350f031828'


def apply(img):
    if hashlib.sha256(img.data).hexdigest() != PREVIOUS_SHA256:
        raise PatchError('rx-overload requires the complete, exact PN 1.11 profile')
    import digital_upper_rail

    digital_upper_rail.apply(img)
    img.overload = True


def register(patch):
    patch('rx-overload', 'Mark a fully upper-railed Digital fallback tail as uncertain',
          risk='untested', default=False, group='scan')(apply)
