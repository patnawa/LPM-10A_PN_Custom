"""PN 1.6: fresh sample ownership and independently scheduled digital feedback."""
import hashlib

from lpm10rx.image import PatchError

PATCHES = {"rx-followup"}
OUTPUT = "experimental/APP_LPM-10RX_PN1.6-followup.bin"
PREVIOUS_SHA256 = "6874d65549e3c67b3ad1020495effc93645e325e104eaa7697737a44c11fb0cd"


def apply(img):
    if hashlib.sha256(img.data).hexdigest() != PREVIOUS_SHA256:
        raise PatchError("rx-followup requires the complete, exact PN 1.5 profile")
    import sampling_fixes
    import rx_patches

    sampling_fixes.apply(img)
    rx_patches.p_digital_correlation(img, strength=True, scheduled=True)

    site, size = 0x08007724, 0x4C
    old = img.read(site, size)
    if hashlib.sha256(old).hexdigest() != "6a2d6117b9ad727dbf639c58bdcef985d86abbfc6e8b08f222ce7382a7728748":
        raise PatchError("digital scheduler does not match the PN 1.5 routine")
    code = img.assemble_at(site, """
        mrs r3, primask
        cpsid i
        ldr r2, =0x2000010C
        ldrb r0, [r2]
        cbnz r0, done              ; finish any active tone, including key feedback
        ldr r0, =0x20000048
        ldrb r1, [r0, #1]         ; pending mode changes invalidate repeats
        cbnz r1, done
        adds r0, #0xA7
        ldrb r1, [r0]            ; gate state: 2 = current, open window generation
        subs r0, #0xA7
        cmp r1, #2
        bne done
        ldrh r1, [r0, #0x24]
        cbz r1, done
        ldrb r1, [r0, #0x12]
        cbnz r1, done              ; finish the current quiet interval
        ldrb r1, [r0, #0x15]      ; publisher owns grade: exactly 30, 50, or 100
        strb r1, [r0, #0x12]
        cmp r1, #50
        bls on
        movs r1, #50
    on:
        strb r1, [r2]
    done:
        ldrb r0, [r2]
        msr primask, r3
        b.w speaker_tick
    """)
    if len(code) > size or len(code) % 2:
        raise PatchError("digital scheduler exceeds its in-place footprint")
    img.poke(site, old.hex(), code + bytes.fromhex("00bf") * ((size - len(code)) // 2),
             "digital feedback: one scheduler owns countdowns; preserve active/key beeps and interrupt mask")


def register(patch):
    patch("rx-followup", "Fresh windows across mode/gate changes and stable digital cadence",
          risk="untested", default=False, group="reliability")(apply)
