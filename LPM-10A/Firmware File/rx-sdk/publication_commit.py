"""Commit fast-gain eligibility only with an accepted PN1.30 publication.

PN1.30 stamps LAST_DISPLAYED when its strength curve starts. A TIM1 interrupt
can then lower the gain before that window publishes; the gain-generation
guard correctly rejects it. The first strong contact needs a second complete
acquisition before feedback is available.

Remove that early store and stamp ANALYSIS_AT inside the existing accepted
publisher's critical section, after grade and RECENT have been committed. A
rejected, expired, mode-invalidated or gain-invalidated window never stamps.
ANALYSIS_AT identifies the immutable analyzed window even when Digital's next
overlapping acquisition has already completed. The existing publisher's
padding accommodates the four added instructions and two literals: no image
growth, new RAM, or extra interrupt masking around the strength calculation.

This installer composes with other PN1.30-derived patches. All owned code and
the freshness publication wrapper are checked before any byte is changed.
"""
import clean_strength
import rail_strong
import sample_age_guard
from lpm10rx.image import PatchError

CURVE = 0x0800D590
EARLY_MARKER = CURVE + 8
PUBLISHER = rail_strong.PUBLISHER
PUBLISHER_SIZE = 96

COMMIT_SOURCE = f'''    ldr r0, ={sample_age_guard.ANALYSIS_AT:#x}
    ldr r2, [r0]
    ldr r0, ={clean_strength.LAST_DISPLAYED:#x}
    str r2, [r0]               ; accepted analyzed generation, atomically with grade/RECENT
'''


def install(img):
    """Patch the guarded publisher in place; return build/audit metadata."""
    if hasattr(img, 'publication_commit'):
        raise PatchError('publication_commit is already installed')
    strength = getattr(img, 'clean_strength', None)
    freshness = getattr(img, 'sample_age_guard', None)
    if not strength or strength.get('curve') != CURVE or not freshness:
        raise PatchError('publication_commit requires PN1.30 and sample-age guards')

    old_curve = img.assemble_at(CURVE, clean_strength.CURVE_SOURCE)
    old_publisher = img.assemble_at(PUBLISHER, rail_strong.HELPER_SOURCE)
    old_publisher += bytes(PUBLISHER_SIZE-len(old_publisher))
    check, publish = freshness['check'], freshness['publish']
    old_wrapper = img.assemble_at(publish, f'''
        push {{r4, r5, r6, lr}}
        mrs r4, primask
        cpsid i
        mov r5, r1
        ldr r0, ={sample_age_guard.ANALYSIS_AT:#x}
        bl {check:#x}
        cmp r0, #0
        beq done
        mov r1, r5
        bl {sample_age_guard.OLD_PUBLISH:#x}
done:
        msr primask, r4
        pop {{r4, r5, r6, pc}}
    ''')
    guarded = {
        CURVE: old_curve,
        PUBLISHER: old_publisher,
        check: img.assemble_at(check, sample_age_guard.CHECK_SOURCE),
        publish: old_wrapper,
        sample_age_guard.PUBLISH: img.assemble_at(sample_age_guard.PUBLISH, f'b.w {publish:#x}'),
    }
    for site, expected in guarded.items():
        if img.read(site, len(expected)) != expected:
            raise PatchError(f'publication_commit: unexpected parent code at {site:#x}')
    early_store = img.assemble_at(EARLY_MARKER, 'str r1, [r2]')
    if img.read(EARLY_MARKER, len(early_store)) != early_store:
        raise PatchError('publication_commit: premature marker store moved')

    accepted_store = '    strh r0, [r2, #0x24]\n'
    if rail_strong.HELPER_SOURCE.count(accepted_store) != 1:
        raise PatchError('publication_commit: accepted publication is not uniquely identified')
    source = rail_strong.HELPER_SOURCE.replace(accepted_store, accepted_store+COMMIT_SOURCE)
    new_publisher = img.assemble_at(PUBLISHER, source)
    if len(new_publisher) > PUBLISHER_SIZE:
        raise PatchError('publication_commit: publisher exceeds its reserved slot')
    used = len(new_publisher)
    new_publisher += bytes(PUBLISHER_SIZE-used)

    img.poke(EARLY_MARKER, early_store.hex(), bytes.fromhex('00bf'),
             'Do not mark a window displayed before its guarded publication')
    img.poke(PUBLISHER, old_publisher.hex(), new_publisher,
             'Atomically commit the accepted analyzed generation with feedback')
    img.publication_commit = {
        'marker_site': EARLY_MARKER, 'publisher': PUBLISHER,
        'publisher_bytes': used, 'publisher_slot': PUBLISHER_SIZE,
        'guarded_sites': tuple(guarded),
        'sites': (EARLY_MARKER, PUBLISHER), 'helper_bytes': 0,
        'persistent_ram_bytes': 0, 'additional_masked_instructions': 4,
        'committed_timestamp': sample_age_guard.ANALYSIS_AT,
        'last_displayed': clean_strength.LAST_DISPLAYED,
    }
    return img.publication_commit
