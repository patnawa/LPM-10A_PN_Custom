"""Keep the original Length Testing box still between averaging runs."""
from lpm10a.image import PatchError
from lpm10a.thumb import assemble
import length_progress as LP


def install(img):
    # PN2.15's hook first pushes {r4, lr}, then calls TESTING_DRAW every run.
    # The later text-box call already overwrites the entire 3-character counter.
    hook = img.length_progress['hook']
    site = hook + 2
    expected = assemble(site, f'bl {LP.TESTING_DRAW}')
    if img.read(hook, 2) != bytes.fromhex('10b5') or img.read(site, 4) != expected:
        raise PatchError('length-progress-quiet: unexpected progress hook')
    gate = img.emit_code(f'''
        testing_once:
            ldr r0, [sp, #0x2C]  ; sequence run index, plus progress hook's 8-byte push
            cmp r0, #0
            bne done
            b.w {LP.TESTING_DRAW}
        done:
            bx lr
    ''', why='Length: draw the Testing label and box only on the first run')
    img.poke(site, expected.hex(), assemble(site, f'bl {gate}'),
             'Length: later runs update only the existing n/4 counter')
    return dict(gate=gate, site=site, expected=expected)
