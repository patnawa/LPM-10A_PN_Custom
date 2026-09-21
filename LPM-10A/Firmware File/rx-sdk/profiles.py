"""The receiver build profiles: each PN version is the previous one plus one module.

    PROFILES["pn1.19"].patch_ids()  -> every patch id that build.py applies for PN 1.19
    PROFILES["pn1.19"].output       -> 'experimental/APP_LPM-10RX_PN1.19-strong-cap.bin'

A profile's module pins the exact SHA-256 of its parent image inside apply(), so the
chain is also verified byte for byte while building.  Two side branches exist:
pn1.10 (Sync32, off pn1.9) and pn1.13 (audio-clock diagnostic, off pn1.12).

Adding PN 1.x: write the module (PATCHES, OUTPUT, PARENT_SHA256, apply, register),
register it at the end of rx_patches.py, and append one Profile line here.
"""
from collections import OrderedDict

import rx_patches
import audit_fixes, followup_fixes, precision_fixes, pinpoint_fixes, robust_fixes  # noqa: E401
import sync_fixes, tracking_fixes, overload_fixes, audio_clock_fixes            # noqa: E401
import mode_tone, gain_norm, release_hold, smooth_gain, rail_strong, strong_cap  # noqa: E401
import fast_update, auto_range                                                  # noqa: E401


class Profile:
    def __init__(self, name, flag, module, parent, title, tag=False):
        self.name, self.flag, self.module, self.parent, self.title, self.tag = name, flag, module, parent, title, tag

    @property
    def output(self):
        if self.module is not None:
            return self.module.OUTPUT
        if self.parent is None:
            return rx_patches.ROADMAP_EXPERIMENT
        return f"experimental/APP_LPM-10RX_{self.name.upper()}-{self.flag}.bin"

    @property
    def own_patches(self):
        if self.module is not None:
            return set(self.module.PATCHES)
        return set(rx_patches.ROADMAP_PATCHES) if self.parent is None else set()

    def patch_ids(self):
        ids = set(self.own_patches)
        p = self.parent
        while p is not None:
            ids |= PROFILES[p].own_patches
            p = PROFILES[p].parent
        return ids


_CHAIN = [
    ("pn1.4",  "roadmap",      None,              None,     "PN 1.4 roadmap experiment: battery recovery, auto-off hold, digital correlation"),
    ("pn1.5",  "audit",        audit_fixes,       "pn1.4",  "PN 1.5 sampler handoff and DFT overflow fixes"),
    ("pn1.6",  "followup",     followup_fixes,    "pn1.5",  "PN 1.6 fresh sample ownership and stable beep timing"),
    ("pn1.7",  "precision",    precision_fixes,   "pn1.6",  "PN 1.7 finer digital strength feedback and faster release"),
    ("pn1.8",  "pinpoint",     pinpoint_fixes,    "pn1.7",  "PN 1.8 interpolated digital feedback across a wider strength range"),
    ("pn1.9",  "robust",       robust_fixes,      "pn1.8",  "PN 1.9 robust code-based digital strength feedback"),
    ("pn1.10", "sync",         sync_fixes,        "pn1.9",  "PN 1.10 legacy Digital and Sync32 recognition (branch)"),
    ("pn1.11", "tracking",     tracking_fixes,    "pn1.9",  "PN 1.11 faster Digital tracking and finer Analog feedback"),
    ("pn1.12", "overload",     overload_fixes,    "pn1.11", "PN 1.12 Digital upper-rail fallback uncertainty (first PN image run on hardware)"),
    ("pn1.13", "audio-clock",  audio_clock_fixes, "pn1.12", "PN 1.13 audio countdown on the speaker timer (diagnostic branch)"),
    ("pn1.14", "mode-tone",    mode_tone,         "pn1.12", "PN 1.14 Analog one octave below Digital; key beeps chirp toward the mode"),
    ("pn1.15", "gain-norm",    gain_norm,         "pn1.14", "PN 1.15 beep rate normalised by the measured knob gain step; audible floor"),
    ("pn1.16", "release-hold", release_hold,      "pn1.15", "PN 1.16 a rejected window holds the last rhythm 160/60 ms"),
    ("pn1.17", "smooth-gain",  smooth_gain,       "pn1.16", "PN 1.17 knob level 3 gets real mid gain; rhythm moves half way per update"),
    ("pn1.18", "rail-strong",  rail_strong,       "pn1.17", "PN 1.18 a clipped reading sounds strongest instead of sparse"),
    ("pn1.19", "strong-cap",   strong_cap,        "pn1.18", "PN 1.19 fastest rhythm at the front-end saturation score"),
    # from here on the version string names the build (version_tag.py): the BOOTLOADER drive shows PN1.xx.TXT
    ("pn1.20", "version-tag",  None,              "pn1.19", "PN 1.20 the drive's status file names the PN build", True),
    ("pn1.21", "fast-update",  fast_update,       "pn1.20", "PN 1.21 Digital evaluates every 40 ms instead of 80", True),
    ("pn1.22", "auto-range",   auto_range,        "pn1.21", "PN 1.22 gain steps down by itself when the front end saturates", True),
]

PROFILES = OrderedDict((n, Profile(n, *rest)) for n, *rest in _CHAIN)
BY_FLAG = {p.flag: p for p in PROFILES.values()}
LATEST = list(PROFILES)[-1]


def apply_profile(img, profile, log=None):
    """Apply every patch of the profile in registry order, then its version tag."""
    ids = profile.patch_ids()
    for p in rx_patches.REGISTRY:
        if p.pid in ids:
            before = len(img.log)
            p(img)
            if log is not None:
                log(p, before)
    if profile.tag:
        import version_tag
        before = len(img.log)
        version_tag.apply(img, profile.name)
        if log is not None:
            log(None, before)
