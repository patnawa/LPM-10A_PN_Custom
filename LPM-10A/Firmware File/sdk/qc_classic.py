"""PN2.23R: original QC layout, continuous automatic acquisition, quiet redraw.

Build with ``python qc_classic.py --write``. Keeps PN2.23Q's calibration and
timer/session ownership, while restoring the requested simple QC workflow.
The PN2.23Q builder and archived artifact remain reproducible.
"""
import argparse
import contextlib
import hashlib
import io
from pathlib import Path

from lpm10a.image import PatchError
from lpm10a.thumb import assemble
import qc_continuity as Q
import roadmap

VERSION = 'PN2.23R'
PARENT_SHA256 = '969c775eba1f40805f9e64325a4e0838edf39fa0e964652a47c1158d0f7d5115'
OUTPUT = Path(__file__).resolve().parent.parent / 'experimental' / 'LPM-10A-TX_PN2.23R-qc-auto.bin'
TIMER_SITE, CLAIM, ACTIVE = 0x080696EE, 0x0806970A, 0x0806982E
KEY_CLICK_SITE, KEY_DELEGATE = 0x080698C2, 0x080698FC


def apply(img):
    img.finalize()
    if hashlib.sha256(bytes(img.data)).hexdigest() != PARENT_SHA256:
        raise PatchError('qc-classic requires the exact finalized PN2.23Q parent')
    parent_end, parent_ram = img.cave_ptr, tuple(img.ram_allocs)
    info = img.qc
    guards = {
        TIMER_SITE: assemble(TIMER_SITE, 'bl xTaskGetTickCount', img.syms),
        KEY_CLICK_SITE: bytes.fromhex('1bd1'),
        Q.GUI_SITE: assemble(Q.GUI_SITE, f'b.w {info["gui"]}'),
    }
    for site, expected in guards.items():
        if img.read(site, len(expected)) != expected:
            raise PatchError(f'qc-classic: unexpected instruction at {site:#x}')

    import qc_classic_ui
    ui = qc_classic_ui.install(img, info['state'], info['reset'])

    # The first accepted pin closes the startup settling phase permanently;
    # elapsed-tick wrap cannot re-arm it after weeks of continuous operation.
    continuous = img.emit_code(f'''
        continuous:
            ldrb r0, [r4, #{Q.SEEN}]
            cmp r0, #0
            bne ready
            bl xTaskGetTickCount
            ldr r1, [r4, #{Q.START}]
            subs r0, r0, r1
            cmp r0, #{Q.SETTLE_MS}
            bhs ready
            b.w {ACTIVE}
        ready:
            b.w {CLAIM}
    ''', why='QC: automatic continuous scanning with one startup settling interval')
    img.poke(TIMER_SITE, guards[TIMER_SITE].hex(), assemble(TIMER_SITE, f'b.w {continuous}'),
             'QC: remove the 20-second session limit')
    img.poke(KEY_CLICK_SITE, guards[KEY_CLICK_SITE].hex(),
             assemble(KEY_CLICK_SITE, f'b {KEY_DELEGATE}'),
             'QC: ordinary clicks follow the original key table; retain Right hold Init')

    # Retain Q's generation checks for entry and calibration result messages.
    # Header refreshes must not first erase the body behind a cached display.
    gui = img.emit_code(f'''
        gui:
            cmp r0, #0x3E
            beq done
            cmp r0, #0x3F
            beq done
            cmp r0, #0x36
            bne delegate
            ldr r1, ={Q.SYS_STATE}
            ldrb r1, [r1]
            cmp r1, #8
            bne delegate
            ldr r1, [sp, #12]
            cmp r1, #0
            beq header
            ldr r1, [r1]
            ldr r2, ={info['state']}
            ldr r2, [r2, #{Q.GENERATION}]
            cmp r1, r2
            bne done
        header:
            bl {ui['header']}
            b done
        delegate:
            b.w {info['gui']}
        done:
            b.w 0x0800F71E
    ''', why='QC: cached classic header, stale notification checks, no session controls')
    img.poke(Q.GUI_SITE, guards[Q.GUI_SITE].hex(), assemble(Q.GUI_SITE, f'b.w {gui}'),
             'QC classic GUI routing')

    replaced = {}
    for name in ('draw', 'frame', 'error', 'progress'):
        site = info['ui'][name]
        replaced[site] = img.read(site, 4)
        img.poke(site, replaced[site].hex(), assemble(site, f'b.w {ui[name]}'),
                 f'QC: classic {name} instead of the session table')
    init = roadmap.startup(img, f'bl {ui["clear"]}', {})
    for site in (0x08011660, 0x08012E6C):
        img.set_string(site, VERSION)
    img.qc_classic = dict(ui=ui, gui=gui, continuous=continuous, init=init,
                          parent_end=parent_end, parent_ram=parent_ram,
                          replaced=replaced, guards=guards)
    return img


def build_candidate():
    return apply(Q.build_candidate()).finalize()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--write', action='store_true')
    args = ap.parse_args()
    with contextlib.redirect_stdout(io.StringIO()):
        img = build_candidate()
    data = bytes(img.data)
    digest = hashlib.sha256(data).hexdigest()
    print(f'{VERSION}: {len(data)} bytes; SHA256 {digest}')
    print(img.summary())
    if args.write:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_bytes(data)
        OUTPUT.with_name('TX-PN2.23R-SHA256SUMS.txt').write_text(
            f'{digest}  {OUTPUT.name}\n', encoding='ascii')
        print(f'Wrote {OUTPUT}')
    else:
        print('Dry build; use --write to emit the experimental update file.')
    print('Classic layout and automatic acquisition; physical display confirmation pending.')


if __name__ == '__main__':
    main()
