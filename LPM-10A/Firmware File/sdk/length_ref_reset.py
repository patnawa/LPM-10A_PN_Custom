"""PN 2.23: REF starts at 10.0 m whenever the Length screen is entered.

PN 2.22 on the owner's unit (2026-09-21): the first REF without a result read "REF 189.1".  PN 2.22
took the REF cell's content as "the value last dialled" whenever it was within 1 .. 300 m -- but the
cell is RAM-arena memory that nothing initialises at power-up, and 18910 is as likely a content as
any other (reproduced: test_length_ref_reset.py).  PN 2.23 writes 10.0 m into the cell on every
entry to the Length screen, in the same hook that resets the target to NVP and clears the pending
mark, so the first REF of a visit is 10.0 m -- or, with a result on screen, the measured length --
and "the value last dialled" is what was dialled on this visit.

Mechanics: Length screen entry 0x08012F1C `bl entry_hook` (length-ref-anytime) -> `bl entry_hook2`:
entry_hook (unit_load, target = NVP, pending mark cleared), then REF = 1000.
"""
import hashlib

from lpm10a.image import PatchError
from lpm10a.thumb import assemble

import length_ref_anytime as LA


PATCH_ID = 'length-ref-reset'
VERSION = 'PN 2.23'
PARENT_SHA256 = '371ed6e2ff8e7aa303a917ddc012f3871bb54c5ffa2f1af96a254db85a0b7c7a'   # PN 2.22

ENTRY_SITE = LA.ENTRY_SITE      # Length screen entry: bl entry_hook (length-ref-anytime)


def register(patch):
    @patch(PATCH_ID, 'Length: REF starts at 10.0 m on every screen entry (the RAM cell is not initialised at power-up)',
           risk='low', default=False, group='measure', requires=('length-ref-anytime',))
    def length_ref_reset(img):
        img.finalize()
        if hashlib.sha256(bytes(img.data)).hexdigest() != PARENT_SHA256:
            raise PatchError('length-ref-reset requires the exact finalized PN 2.22 parent')
        old_entry = img.length_ref_anytime['entry']
        entry_stock = assemble(ENTRY_SITE, f'bl {old_entry}')
        if img.read(ENTRY_SITE, 4) != entry_stock:
            raise PatchError('length-ref-reset: the entry site does not call length-ref-anytime')
        entry = img.emit_code(f'''
        entry_hook2:                    ; Length screen entry, in front of length-ref-anytime's hook (r1 = test_busy_flags)
                push {{r4, lr}}
                bl   ENTRY_HOOK         ; unit_load, target = NVP, pending mark cleared
                ldr  r0, =REF
                movw r1, #{LA.REF_DEFAULT}
                strh r1, [r0]           ; REF = 10.0 m until dialled or taken from a result
                pop  {{r4, pc}}
        ''', extra_syms=dict(ENTRY_HOOK=old_entry | 1, REF=img.length_reference['ref']),
            why='Length screen entry: REF = 10.0 m')
        img.poke(ENTRY_SITE, entry_stock.hex(), assemble(ENTRY_SITE, f'bl {entry}'),
                 'Length screen entry: REF starts at 10.0 m')
        for site in (0x08011660, 0x08012E6C):
            img.set_string(site, VERSION)
        img.length_ref_reset = dict(entry=entry)
