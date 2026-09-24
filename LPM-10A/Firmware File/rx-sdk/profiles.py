"""The receiver build profiles: each PN version is the previous one plus one module.

    PROFILES["pn1.19"].patch_ids()  -> every patch id that build.py applies for PN 1.19
    PROFILES["pn1.19"].output       -> 'experimental/APP_LPM-10RX_PN1.19-strong-cap.bin'

A profile's module pins the exact SHA-256 of its parent image inside apply(), so the
chain is also verified byte for byte while building.  Side branches: pn1.10 (Sync32,
off pn1.9), pn1.13 (audio-clock diagnostic, off pn1.12), pn1.25 / pn1.26 / pn1.27 (knob
builds off pn1.24) and pn1.28 (off pn1.27); pn1.29 also branches from pn1.24, and the release
pn1.30 is built on the exact pn1.29 image.

Adding PN 1.x: write the module (PATCHES, OUTPUT, PARENT_SHA256, apply, register),
register it at the end of rx_patches.py, and append one Profile line here.
Standalone candidate builders use lazy ReleaseStage metadata instead. Their
guarded stages follow the registry patches, without importing builders while
profiles is still initializing or adding them to custom --all selections.
"""
from collections import OrderedDict
from importlib import import_module
from lpm10rx.image import PatchError

import rx_patches
import audit_fixes, followup_fixes, precision_fixes, pinpoint_fixes, robust_fixes  # noqa: E401
import sync_fixes, tracking_fixes, overload_fixes, audio_clock_fixes            # noqa: E401
import mode_tone, gain_norm, release_hold, smooth_gain, rail_strong, strong_cap  # noqa: E401
import fast_update, auto_range, mains_tone                                      # noqa: E401


class ReleaseStage:
    """A guarded candidate stage, imported only when a profile is applied."""
    def __init__(self, module_name, pid, output, title, tag_after=None):
        self.module_name, self.pid, self.OUTPUT = module_name, pid, output
        self.title, self.tag_after = title, tag_after
        self.PATCHES = frozenset((pid,))
        self.risk, self.group, self.default = 'validated', 'scan', False

    def __call__(self, img):
        import_module(self.module_name).apply(img)
        if self.tag_after is not None:
            import version_tag
            version_tag.apply(img, self.tag_after)


class Profile:
    def __init__(self, name, flag, module, parent, title, tag=False, hardware=None):
        self.name, self.flag, self.module, self.parent, self.title, self.tag = name, flag, module, parent, title, tag
        self.hardware = hardware

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
        seen = {self.name}
        p = self.parent
        while p is not None:
            if p not in PROFILES:
                raise PatchError(f"profile {self.name}: unknown parent {p!r}")
            if p in seen:
                raise PatchError(f"profile {self.name}: cyclic parent chain at {p!r}")
            seen.add(p)
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
    ("pn1.23", "mains-tone",   mains_tone,        "pn1.22", "PN 1.23 mains mode beeps at 5 kHz: three modes, three pitches", True),
    ("pn1.23f", "gain-freshness", ReleaseStage("auto_range_freshness", "rx-gain-freshness",
        "experimental/APP_LPM-10RX_PN1.23F-gain-freshness.bin",
        "Invalidate old-gain acquisitions before publishing new gain", tag_after="pn1.23f"),
     "pn1.23", "PN1.23F gain/sample ownership correction (historical candidate)", True),
    ("pn1.23g", "digital-gain", ReleaseStage("digital_gain_continuity", "rx-digital-gain",
        "experimental/APP_LPM-10RX_PN1.23G-digital-gain.bin",
        "Keep confirmed Digital rhythm during fresh gain acquisition"),
     "pn1.23f", "PN1.23G bounded Digital feedback across gain changes", True,
     "Digital gain-change dropout fix confirmed by the owner, 2026-09-22"),
    ("pn1.24", "gain-precision", ReleaseStage("rx_precision", "rx-gain-precision",
        "experimental/APP_LPM-10RX_PN1.24-gain-precision.bin",
        "Faster fresh-window gain recovery, efficient Analog analysis and sample-age guards"),
     "pn1.23g", "PN1.24 Digital/Analog gain response, Analog efficiency and sample freshness", True,
     "Hardware test passed: no Digital or Analog audio dropout reported by the owner, 2026-09-22"),
    # PN1.25-1.27 and PN1.29 branch from PN1.24 (each module pins the exact PN1.24 image);
    # PN1.28 pins the exact PN1.27 image; PN1.30 pins the exact PN1.29 image.
    ("pn1.25", "isolate", ReleaseStage("isolate", "rx-isolate",
        "experimental/APP_LPM-10RX_PN1.25-isolate.bin",
        "Knob-reference isolate below the middle, louder beeps, NCV gain"),
     "pn1.24", "PN1.25 absolute-floor isolate (historical candidate)", True,
     "Owner 2026-09-23: louder beeps confirmed; the knob still had to pass the middle (superseded)"),
    ("pn1.26", "relative", ReleaseStage("relative_isolate", "rx-relative-isolate",
        "experimental/APP_LPM-10RX_PN1.26-relative.bin",
        "Full gain at every knob position, isolation relative to the strongest pair"),
     "pn1.24", "PN1.26 peak-relative isolate (historical candidate)", True,
     "Owner 2026-09-23: heard from 5-10 %, but the knob had no effect (superseded)"),
    ("pn1.27", "knob", ReleaseStage("knob_reference", "rx-knob-reference",
        "experimental/APP_LPM-10RX_PN1.27-knob.bin",
        "Knob sets the rhythm reference over its whole travel; peak-relative mute below the middle"),
     "pn1.24", "PN1.27 knob reference, full sensitivity, peak-relative mute, louder beeps, NCV gain", True,
     "Hardware test passed: owner reports '1.27 test pass', 2026-09-23 (superseded by PN1.29)"),
    ("pn1.28", "pair-rank", ReleaseStage("pair_rank", "rx-pair-rank",
        "experimental/APP_LPM-10RX_PN1.28-pair-rank.bin",
        "Strongest recent pair on the fastest rhythm point, fast gain attack"),
     "pn1.27", "PN1.28 pair ranking against a remembered peak (historical candidate)", True,
     "Owner 2026-09-23: detects, but not accurately, worse than PN1.27 (superseded)"),
    ("pn1.29", "levels", ReleaseStage("level_display", "rx-level-display",
        "experimental/APP_LPM-10RX_PN1.29-levels.bin",
        "Ten absolute strength levels against the knob reference; no memory; fast gain attack"),
     "pn1.24", "PN1.29 IntelliTone-style absolute levels, Locate/Isolate knob, full sensitivity, fast attack", True,
     "Hardware test passed: owner reports '1.29 test pass work perfect', 2026-09-23 (superseded by PN1.30)"),
    ("pn1.30", "clean-strength", ReleaseStage("clean_strength", "rx-clean-strength",
        "experimental/APP_LPM-10RX_PN1.30-clean-strength.bin",
        "Edge-free Digital strength, a gain decision at every displayed window, saturated lower bound, faster real drop"),
     "pn1.29", "PN1.30 steady Digital strength (chip-edge dips removed), fast gain settle, no walk-down at a touch", True,
     "Hardware test passed: owner reports '1.30 test pass flicker fixed', 2026-09-24"),
]

PROFILES = OrderedDict((n, Profile(n, *rest)) for n, *rest in _CHAIN)
BY_FLAG = {p.flag: p for p in PROFILES.values()}
LATEST = list(PROFILES)[-1]


def profile_patches(profile):
    """Validate a complete selection before applying registry and lazy stages."""
    ids = profile.patch_ids()
    available = list(rx_patches.REGISTRY) + [p.module for p in PROFILES.values()
                                           if isinstance(p.module, ReleaseStage)]
    registered = [p.pid for p in available]
    missing = ids - set(registered)
    duplicate = {pid for pid in ids if registered.count(pid) > 1}
    if missing or duplicate:
        raise PatchError(f"profile {profile.name}: missing patches {sorted(missing)}, duplicate patches {sorted(duplicate)}")
    return [p for p in available if p.pid in ids]


def apply_profile(img, profile, log=None):
    """Apply ordered guarded patches, then the historical profile's final tag.

    PN1.23F and later stages carry exact tagged-parent guards and establish
    their own identities. Earlier profiles still tag only after their complete
    untagged registry chain, preserving every archived parent hash.
    """
    for p in profile_patches(profile):
        before = len(img.log)
        p(img)
        if log is not None:
            log(p, before)
    if profile.tag and not isinstance(profile.module, ReleaseStage):
        import version_tag
        before = len(img.log)
        version_tag.apply(img, profile.name)
        if log is not None:
            log(None, before)
