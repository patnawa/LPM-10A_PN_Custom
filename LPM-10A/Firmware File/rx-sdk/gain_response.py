"""Quicker shared Digital/Analog gain recovery over PN1.23G.

Keep the measured gain map, 1900/450-count hysteresis, user ceiling and
PN1.23G gain invalidation. One skipped 500 ms callback gives one second
between automatic steps, instead of 2.5 seconds. A skipped callback does not
scan the 48 samples. Automatic decisions require a recent, fully completed
acquisition from the current gate/gain generation; elapsed time alone does
not prove that fresh samples have arrived.

Install after sample_age_guard, which owns completion timestamps and clears
their validity on every main-owned sampler reset. This module allocates no
RAM and does not change version strings or write firmware files.
"""
import auto_range
import auto_range_freshness
import digital_gain_continuity
import smooth_gain
from lpm10rx import symbols
from lpm10rx.image import PatchError

HOLD_TICKS = 1
GAIN_SITE = smooth_gain.GAIN_SELECT_SITE


def install(img):
    """Append the guarded AGC helper; return its build/audit metadata."""
    if hasattr(img, 'gain_response'):
        raise PatchError('gain_response is already installed')
    age = getattr(img, 'sample_age_guard', None)
    continuity = getattr(img, 'digital_gain_continuity', None)
    if age is None or continuity is None:
        raise PatchError('gain_response requires PN1.23G and sample_age_guard first')
    import sample_age_guard

    invalidator = continuity['invalidator']
    old_source = auto_range_freshness.SOURCE.replace(
        'movs r1, #0\n    strb r1, [r4]', f'bl {invalidator:#x}')
    expected_helper = img.assemble_at(auto_range_freshness.HELPER, old_source)
    expected_helper += bytes(auto_range_freshness.SIZE - len(expected_helper))
    if img.read(auto_range_freshness.HELPER, auto_range_freshness.SIZE) != expected_helper:
        raise PatchError('gain_response requires the intact PN1.23G gain helper')
    expected_entry = img.assemble_at(GAIN_SITE, f'b.w {auto_range_freshness.HELPER:#x}')
    if img.read(GAIN_SITE, 4) != expected_entry:
        raise PatchError('gain_response gain entry differs from PN1.23G')
    expected_invalidation = img.assemble_at(invalidator, digital_gain_continuity.INVALIDATE_SOURCE)
    if img.read(invalidator, len(expected_invalidation)) != expected_invalidation:
        raise PatchError('gain_response requires the intact PN1.23G invalidator')
    if img.read(auto_range.CURVE_LITERAL, 4) != auto_range.STATE.to_bytes(4, 'little'):
        raise PatchError('gain_response normalizer must read the driven level')

    old_hold = '''    ldrb r1, [r2, #2]           ; hold
    cmp r1, #0
    beq nohold
    subs r1, #1
    strb r1, [r2, #2]
    b out
nohold:
'''
    if old_source.count(old_hold) != 1:
        raise PatchError('gain_response cannot identify the inherited hold path')
    source = old_source.replace(old_hold, '')
    before_scan = '''    push {r2}
    ldr r1, ='''
    if source.count(before_scan) != 1:
        raise PatchError('gain_response cannot identify the inherited sample scan')
    checks = f'''    ldrb r1, [r2, #2]
    cmp r1, #0
    beq fresh
    subs r1, #1
    strb r1, [r2, #2]
    b out                     ; a hold never needs a 48-sample P-P scan
fresh:
    ldr r1, =0x20000049
    ldrb r1, [r1]
    cmp r1, #0
    bne out                   ; pending mode changes invalidate old samples
    ldr r1, =0x200000EF
    ldrb r1, [r1]
    cmp r1, #2
    bne out                   ; closed/invalid/gain-bridge acquisitions
    ldr r1, ={sample_age_guard.COMPLETED_VALID:#x}
    ldr r1, [r1]
    cmp r1, #1
    bne out                   ; require a full same-generation raw window
    ldr r1, ={sample_age_guard.COMPLETED_AT:#x}
    ldr r1, [r1]
    ldr r0, ={sample_age_guard.TIMER_COUNTER:#x}
    ldr r0, [r0]
    subs r0, r0, r1           ; unsigned elapsed, including TIM5 wrap
    ldr r1, ={sample_age_guard.DIGITAL_MAX_AGE_TICKS}
    cmp r4, #0
    beq age_ready
    ldr r1, ={sample_age_guard.ANALOG_MAX_AGE_TICKS}
age_ready:
    cmp r0, r1
    bhi out                   ; a stalled completed frame cannot steer AGC
    push {{r2}}
    ldr r1, ='''
    source = source.replace(before_scan, checks)
    source = source.replace(f'movs r1, #{auto_range.HOLD_TICKS}\n    strb r1, [r2, #2]',
                            f'movs r1, #{HOLD_TICKS}\n    strb r1, [r2, #2]')
    start = symbols.APP_BASE + len(img.data)
    code = img.assemble_at(start, source)
    code += bytes(-len(code) % 4)
    branch = img.assemble_at(GAIN_SITE, f'b.w {start:#x}')
    if start + len(code) > symbols.EXTEND_LIMIT:
        raise PatchError('gain_response exceeds the application flash budget')
    img.extend(len(code), 'Shared gain response: fresh-window guarded one-second range changes')
    img.poke(start, bytes(len(code)).hex(), code,
             'Check hold and completion freshness before shared P-P range selection')
    img.poke(GAIN_SITE, expected_entry.hex(), branch,
             'Use quicker fresh-window AGC while preserving PN1.23G ownership')
    img.gain_response = {
        'helper': start, 'helper_bytes': len(code), 'hook': GAIN_SITE,
        'hold_ticks': HOLD_TICKS, 'sat_pp': auto_range.SAT_PP,
        'recover_pp': auto_range.RECOVER_PP,
        'completed_valid': sample_age_guard.COMPLETED_VALID,
        'completed_at': sample_age_guard.COMPLETED_AT,
        'persistent_ram_bytes': 0, 'additional_stack_bytes': 0,
    }
    return img.gain_response
