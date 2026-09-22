"""Bound completed ADC window age before analysis and feedback publication.

PN1.23G can publish a window completed before a long foreground stall and
restart feedback after the physical input has gone. TIM5 records completion;
main snapshots that timestamp before analysis. Digital rearms sampling before
its DSP finishes, so publication must check the snapshot, not the next window.

The 300 ms Digital / 100 ms Analog budgets match their existing accepted
feedback eligibility (RECENT=800/600, speaker requires >500). These are age
limits, not detection thresholds. TIM5 is used independently of TIM1 countdown
progress. Unsigned subtraction handles the timer's 32-bit wrap.

RAM 0x20000204..20F follows the four existing AGC bytes. The application's
absolute RAM references name globals only through 0x20000112 and the AGC area;
bounded sample/subsample arrays end at 0xFA. This range is within startup zero
initialization. A separate static walk of 136 reachable functions found no
allocator, dynamic SP adjustment, or recursion; main plus both timer handlers
and two extended/aligned exception frames stays above 0x200013F0 (4576 bytes
above this reservation). This is static evidence, not a device watermark.
Application startup replaces the bootloader's RAM contents and vectors.

Only main clears acquisition on expiry, through the existing G boundary.
The ISR merely publishes the timestamp and validity before ACTIVE=0. G gain
bridging, detection mathematics, overlap size, and Mains remain unchanged.
"""
from lpm10rx import symbols
from lpm10rx.image import PatchError
import digital_gain_continuity
import sampling_fixes


COMPLETED_AT = 0x20000204
ANALYSIS_AT = 0x20000208
COMPLETED_VALID = 0x2000020C
TIMER_COUNTER = 0x20000100
DIGITAL_MAX_AGE_TICKS = 300 * 64000 // 1601
ANALOG_MAX_AGE_TICKS = 100 * 64000 // 1601
PUBLISH = 0x08009F20
OLD_PUBLISH = 0x0800CEA8
ANALOG_REFRESH = 0x08009FC8
COMPLETION_SITES = (0x080076A2, 0x0800770E)


CHECK_SOURCE = f'''
    ldr r1, =0x20000048
    ldrb r1, [r1]
    cmp r1, #2
    bhs fresh                   ; Mains has its original policy
    ldr r2, ={COMPLETED_VALID:#x}
    ldr r2, [r2]
    cmp r2, #1
    bne expired
    ldr r3, [r0]                ; caller chooses completed or analyzed snapshot
    ldr r2, ={TIMER_COUNTER:#x}
    ldr r0, [r2]
    subs r0, r0, r3
    movw r2, #{DIGITAL_MAX_AGE_TICKS}
    cmp r1, #0
    beq limit_ready
    movw r2, #{ANALOG_MAX_AGE_TICKS}
limit_ready:
    cmp r0, r2
    bhi expired
fresh:
    movs r0, #1
    bx lr
expired:
    ldr r1, =0x200000EF
    movs r0, #0
    strb r0, [r1]               ; main boundary owns sampler reset
    ldr r1, ={COMPLETED_VALID:#x}
    str r0, [r1]
    bx lr
'''

STAMP_SOURCE = f'''
    push {{r2, r3}}
    ldr r1, ={TIMER_COUNTER:#x}
    ldr r2, [r1]
    ldr r1, ={COMPLETED_AT:#x}
    str r2, [r1]
    movs r2, #1
    str r2, [r1, #8]
    movs r1, #0
    strb r1, [r0]               ; original ACTIVE=0, after stamp is visible
    pop {{r2, r3}}
    bx lr
'''

RESET_SOURCE = f'''
    strb r1, [r5, #1]           ; exact displaced G boundary instructions
    movs r0, #0
    push {{r2}}
    ldr r2, ={COMPLETED_VALID:#x}
    str r0, [r2]                ; every actual boundary, including gain bridge
    pop {{r2}}
    bx lr
'''


def install(img):
    """Append helpers to PN1.23G; compatible with the isolated Analog patch."""
    if hasattr(img, 'sample_age_guard'):
        raise PatchError('sample age guard is already installed')
    continuity = getattr(img, 'digital_gain_continuity', None)
    if not continuity:
        raise PatchError('sample age guard requires PN1.23G gain continuity')
    boundary = continuity['boundary']
    expected_boundary = img.assemble_at(boundary, digital_gain_continuity.BOUNDARY_SOURCE)
    if img.read(boundary, len(expected_boundary)) != expected_boundary:
        raise PatchError('sample age guard requires the unchanged G boundary')
    needle = img.assemble_at(boundary, 'strb r1, [r5, #1]\nmovs r0, #0')
    if expected_boundary.count(needle) != 1:
        raise PatchError('G boundary reset seam is ambiguous')
    reset_site = boundary + expected_boundary.index(needle)
    guards = {
        sampling_fixes.READY: bytes.fromhex('07484078'),
        PUBLISH: img.assemble_at(PUBLISH, f'b.w {OLD_PUBLISH:#x}'),
        ANALOG_REFRESH: bytes.fromhex('eff31083'),
        reset_site: needle,
        **{site: bytes.fromhex('00210170') for site in COMPLETION_SITES},
    }
    for site, expected in guards.items():
        if img.read(site, len(expected)) != expected:
            raise PatchError(f'sample age guard changed entry at {site:#x}')

    start = symbols.APP_BASE + len(img.data)
    body = bytearray()
    addresses = {}

    def append(name, source):
        address = start + len(body)
        code = img.assemble_at(address, source)
        body.extend(code)
        body.extend(bytes(-len(body) % 4))
        addresses[name] = address
        return address

    check = append('check', CHECK_SOURCE)
    stamp = append('stamp', STAMP_SOURCE)
    reset = append('reset', RESET_SOURCE)
    ready = append('ready', f'''
        push {{r4, lr}}
        mrs r4, primask
        cpsid i
        ldr r0, =0x20000048
        ldrb r0, [r0, #1]
        cmp r0, #0
        bne not_ready
        ldr r0, =0x200000EF
        ldrb r0, [r0]
        cmp r0, #2
        bne not_ready
        ldr r0, =0x20000008
        ldrb r0, [r0]
        cmp r0, #0
        bne not_ready
        ldr r0, ={COMPLETED_AT:#x}
        bl {check:#x}
        cmp r0, #0
        beq done
        ldr r1, ={COMPLETED_AT:#x}
        ldr r2, [r1]
        str r2, [r1, #4]
        b done
not_ready:
        movs r0, #0
done:
        msr primask, r4
        pop {{r4, pc}}
    ''')
    publish = append('publish', f'''
        push {{r4, r5, r6, lr}}
        mrs r4, primask
        cpsid i
        mov r5, r1
        ldr r0, ={ANALYSIS_AT:#x}
        bl {check:#x}
        cmp r0, #0
        beq done
        mov r1, r5
        bl {OLD_PUBLISH:#x}
done:
        msr primask, r4
        pop {{r4, r5, r6, pc}}
    ''')
    refresh = append('refresh', f'''
        push {{r4, lr}}
        mrs r4, primask
        cpsid i
        ldr r0, ={ANALYSIS_AT:#x}
        bl {check:#x}
        mov r3, r4              ; original refresh restores this PRIMASK
        pop {{r4, pc}}
    ''')
    replacements = {
        sampling_fixes.READY: (ready, 'b.w'),
        PUBLISH: (publish, 'b.w'),
        ANALOG_REFRESH: (refresh, 'bl'),
        reset_site: (reset, 'bl'),
        **{site: (stamp, 'bl') for site in COMPLETION_SITES},
    }
    img.extend(len(body), 'Bound completed and analyzed sample age')
    img.poke(start, bytes(len(body)).hex(), bytes(body),
             'Timestamp completed windows and reject expired analysis/publication')
    for site, (target, branch) in replacements.items():
        img.poke(site, guards[site].hex(), img.assemble_at(site, f'{branch} {target:#x}'),
                 'Keep ADC window age and feedback authorization coherent')
    metadata = {
        **addresses, 'start': start, 'helper_bytes': len(body),
        'completed_at': COMPLETED_AT, 'analysis_at': ANALYSIS_AT,
        'completed_valid': COMPLETED_VALID, 'timer_counter': TIMER_COUNTER,
        'age_limit_ticks': {0: DIGITAL_MAX_AGE_TICKS, 1: ANALOG_MAX_AGE_TICKS},
        'reset_site': reset_site, 'hooks': tuple(sorted(guards)),
        'persistent_ram_bytes': 12, 'additional_stack_bytes': 16,
    }
    img.sample_age_guard = metadata
    return metadata
