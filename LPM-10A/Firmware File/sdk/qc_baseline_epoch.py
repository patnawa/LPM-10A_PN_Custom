"""Require a normalized QC Init before using pre-PN2.25 calibration counts.

The marker occupies settings tail padding C6/C7, after net_cfg A9..C4 and
Length Zero C5. The exact parent copies C8 bytes on load (FE40..FE46) and
autosave (50 words); net_cfg storage copies only 1C bytes at 119B0. Neither
the stock fields nor existing SDK patches use C6/C7. Factory defaults are
extended at their already-patched Zero hook, leaving every other byte intact.

A CRC-16/CCITT with PN2.25 seed binds the marker to the 16 baseline bytes.
Zero/erased markers are never accepted. This is a limited provenance/integrity
marker, not a security guarantee: 16-bit collisions remain possible. It also
rejects most baselines edited by older firmware after a downgrade, unlike a
fixed magic number. A failed Init retains the previous baseline and marker.

Only the normalized candidate installs this patch. Existing profile builders
and their artifacts retain their original settings behavior.
"""
from lpm10a.image import PatchError
from lpm10a.thumb import assemble, verify
from length_ref_anytime import bl_target
import qc_calibration as C

SETTINGS = 0x20000C78
MARKER = SETTINGS + 0xC6
SEED, POLYNOMIAL = 0x225C, 0x1021
VALID_SITE, DEFAULT_SITE = 0x080692CA, 0x080195BC
VALID_EXPECTED = bytes.fromhex('00780128')
DEFAULT_EXPECTED = bytes.fromhex('4ef0d4fc')


def fingerprint(data):
    """Reference value for the compact persisted marker, not a trust boundary."""
    if len(data) != 16:
        raise ValueError('QC marker requires exactly eight uint16 baselines')
    value = SEED
    for byte in data:
        value ^= byte << 8
        for _ in range(8):
            value = ((value << 1) ^ (POLYNOMIAL if value & 0x8000 else 0)) & 0xFFFF
    return 1 if value == 0 else 0xFFFE if value == 0xFFFF else value


def install(img):
    """Append migration guards; callers install only after normalized sampling."""
    if not hasattr(img, 'qc_calibration') or not hasattr(img, 'qc_classic'):
        raise PatchError('QC baseline epoch requires the classic calibrated parent')
    hook = img.qc_calibration['hook']
    calls = [address for address, _, instruction in verify(img.read(hook, 0x200), hook)
             if instruction == f'bl #0x{C.SAVE:x}']
    if len(calls) != 1:
        raise PatchError('QC baseline epoch: expected one calibration commit save')
    save_site = calls[0]
    guards = {VALID_SITE: VALID_EXPECTED, DEFAULT_SITE: DEFAULT_EXPECTED,
              save_site: assemble(save_site, f'bl {C.SAVE}')}
    for address, expected in guards.items():
        if img.read(address, len(expected)) != expected:
            raise PatchError(f'QC baseline epoch: unexpected parent bytes at {address:#x}')
    old_default = bl_target(img.data, DEFAULT_SITE)
    # This hook must still be the single-byte Length Zero reset. A changed
    # layout is rejected before emitting code or changing the image.
    if img.read(old_default, 6) != bytes.fromhex('c53100200870'):
        raise PatchError('QC baseline epoch: changed factory Zero reset contract')
    syms = dict(MARKER=MARKER, BASELINE=C.BASELINE,
                SAVED_BASELINE=SETTINGS + 0x90, VALID=C.VALID)
    checksum = img.emit_code(f'''
        push {{r4, r5}}
        mov r1, r0
        movw r0, #{SEED}
        movs r2, #16
        movw r4, #{POLYNOMIAL}
    byte:
        ldrb r3, [r1]
        adds r1, #1
        lsls r3, r3, #8
        eors r0, r3
        movs r5, #8
    bit:
        lsls r3, r0, #16
        bpl plain
        lsls r0, r0, #1
        eors r0, r4
        b masked
    plain:
        lsls r0, r0, #1
    masked:
        uxth r0, r0
        subs r5, #1
        bne bit
        subs r2, #1
        bne byte
        cmp r0, #0
        bne nonzero
        movs r0, #1
    nonzero:
        movw r1, #65535
        cmp r0, r1
        bne done
        subs r0, #1
    done:
        pop {{r4, r5}}
        bx lr
    ''', why='QC baseline: version-seeded CRC16 binds calibration to its timed-count units')
    valid = img.emit_code(f'''
        push {{r4, lr}}
        ldrb r4, [r0]
        cmp r4, #1
        bne done
        ldr r0, =BASELINE
        bl {checksum}
        ldr r1, =MARKER
        ldrh r1, [r1]
        cmp r0, r1
        beq done
        movs r4, #0
    done:
        mov r0, r4
        cmp r0, #1
        pop {{r4, pc}}
    ''', extra_syms=syms,
        why='QC entry: legacy or changed baseline keeps the original Init prompt')
    save = img.emit_code(f'''
        push {{r4, r5, r6, lr}}
        mov r4, r0
        bl {C.ENTER_CRITICAL}
        mov r0, r4
        bl {checksum}
        mov r6, r0
        ldr r1, =SAVED_BASELINE
        mov r2, r4
        movs r3, #4
    copy:
        ldr r0, [r2]
        str r0, [r1]
        adds r1, #4
        adds r2, #4
        subs r3, #1
        bne copy
        ldr r0, =MARKER
        strh r6, [r0]
        bl {C.EXIT_CRITICAL}
        mov r0, r4
        bl {C.SAVE}
        pop {{r4, r5, r6, pc}}
    ''', extra_syms=syms,
        why='QC Init: atomically publish baseline and marker before requesting settings save')
    defaults = img.emit_code(f'''
        ldr r2, =MARKER
        movs r3, #0
        strh r3, [r2]
        b.w {old_default}
    ''', extra_syms=syms,
        why='Factory Reset invalidates normalized QC baseline provenance')
    for address, target in ((VALID_SITE, valid), (save_site, save), (DEFAULT_SITE, defaults)):
        img.poke(address, guards[address].hex(), assemble(address, f'bl {target}'),
                 'QC normalized-baseline migration hook')
    info = dict(marker=MARKER, marker_size=2, seed=SEED, checksum=checksum,
                valid=valid, save=save, defaults=defaults, save_site=save_site,
                valid_site=VALID_SITE, default_site=DEFAULT_SITE, guards=guards,
                ram_bytes=0, old_default=old_default)
    img.qc_baseline_epoch = info
    return info
