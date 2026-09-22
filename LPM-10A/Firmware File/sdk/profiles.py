"""The tester build profiles: each PN version is its parent plus one module.

    PROFILES["pn2.14"].patch_ids()  -> every patch id build.py applies for PN 2.14
    PROFILES["pn2.14"].output       -> 'experimental/LPM-10A-TX_PN2.14-tone-recovery.bin'
    PROFILES["pn2.14"].version      -> 'PN 2.14' (About screen and boot log)
    LATEST                          -> the profile build.py emits when no profile is named

Every profile starts from the BASELINE: the patches registered with default=True in
patches.py.  That set is frozen -- verify.py models it byte for byte and its image is
archived as LPM-10A-TX_PN2.9.bin (never released on its own; `build.py --default`).
A profile's module writes its own version string last, so the About screen names the
profile, not the baseline. Profile patches run in registry order, which makes every
archived image reproducible (test_profiles.py checks each one). Optional extras run
after the complete profile, in their registry order, so they cannot invalidate the
profile modules' exact-parent checks.

Adding PN 2.x: write the module (PATCHES or PATCH_ID, VERSION, register()), register it
at the end of patches.py, append one Profile line here with its output name and
hardware record, then run `python -m unittest test_profiles`.
Standalone candidate builders with apply() instead use _register_release_stage()
and ReleaseStage metadata, preserving their original entry points and avoiding
imports back into profiles while this registry is being constructed.
"""
import os
from collections import OrderedDict
from importlib import import_module

import patches
from lpm10a.image import PatchError
import roadmap, portflash, audit_fixes, portflash_status, scan_sync, scan_recovery, length_progress  # noqa: E401
import about_values, speed_partner, length_reference, cable_test, cable_clear, cable_values, length_ref_anytime, length_ref_reset  # noqa: E401
import speed_partner_validity


class ReleaseStage:
    """Metadata for candidate builders that import profiles for their parent.

    Load their version only after this registry exists; eagerly importing QC
    builders here would cycle through qc_continuity -> profiles.
    """
    def __init__(self, module_name):
        self.module_name = module_name
        self.PATCH_ID = module_name.replace('_', '-')

    @property
    def VERSION(self):
        return import_module(self.module_name).VERSION


class Profile:
    def __init__(self, name, flag, module, parent, output, title, hardware):
        self.name, self.flag, self.module, self.parent = name, flag, module, parent
        self.output, self.title, self.hardware = output, title, hardware

    def path(self, fw_dir):
        """The output file under the Firmware File folder, with the platform's separators."""
        return os.path.join(fw_dir, *self.output.split("/"))

    @property
    def version(self):
        """The module's version string; pn2.9 keeps the baseline's (roadmap.py sets none)."""
        return getattr(self.module, "VERSION", patches.VERSION)

    @property
    def own_patches(self):
        ids = getattr(self.module, "PATCHES", None) or (self.module.PATCH_ID,)
        return set(ids)

    def patch_ids(self):
        """The baseline plus every module up the chain."""
        ids = set(baseline_ids())
        p = self
        while p is not None:
            ids |= p.own_patches
            p = PROFILES[p.parent] if p.parent else None
        return ids


def baseline_ids():
    return [p.pid for p in patches.REGISTRY if p.default]


_CHAIN = [
    ("pn2.9",  "roadmap",          roadmap,          None,     "experimental/LPM-10A-TX_PN2.9-roadmap.bin",
     "PN 2.9 service task, watchdog, calibration autosave, fault records (release v2.9)",
     "device test pass reported by the owner, 2026-09-19"),
    ("pn2.10", "portflash",        portflash,        "pn2.9",  "experimental/LPM-10A-TX_PN2.10-portflash.bin",
     "PN 2.10 Port FLASH: autoneg register corrected, recovery after link loss (candidate)",
     "CPU-tested only; superseded by PN 2.12"),
    ("pn2.11", "audit",            audit_fixes,      "pn2.10", "experimental/LPM-10A-TX_PN2.11-audit.bin",
     "PN 2.11 battery monitoring during FLASH, static settings writer on every save path (candidate)",
     "owner saw an intermittent long-on blink on a D-Link gigabit switch -> PN 2.12"),
    ("pn2.12", "portflash-status", portflash_status, "pn2.11", "experimental/LPM-10A-TX_PN2.12-portflash-status.bin",
     "PN 2.12 FLASH driven by the PHY link status (release v2.12)",
     "Port FLASH confirmed by the owner on the D-Link gigabit switch, 2026-09-19"),
    ("pn2.13", "scan-sync",        scan_sync,        "pn2.12", "experimental/LPM-10A-TX_PN2.13-sync.bin",
     "PN 2.13 optional Sync32 and Pulse test tone modes (retired branch)",
     "Sync32 silent on the owner's probe with RX PN 1.10, 2026-09-20; not recommended"),
    ("pn2.14", "scan-recovery",    scan_recovery,    "pn2.12", "experimental/LPM-10A-TX_PN2.14-tone-recovery.bin",
     "PN 2.14 two tone modes labelled by frequency, RIGHT-key carrier cache fixed (release v2.14)",
     "on the owner's unit 2026-09-20 .. 21: both tone modes receive, other functions pass; superseded by PN 2.19 / 2.20"),
    ("pn2.15", "length-progress",  length_progress,  "pn2.14", "experimental/LPM-10A-TX_PN2.15-length-progress.bin",
     "PN 2.15 the Length screen counts the averaging runs (1/4 .. 4/4) on the Testing line",
     "on the owner's unit since 2026-09-21 as part of PN 2.19: every function passes"),
    ("pn2.16", "about-values",     about_values,     "pn2.15", "experimental/LPM-10A-TX_PN2.16-about-values.bin",
     "PN 2.16 the About screen shows battery mV, NVP and Zero under Factory Reset",
     "on the owner's unit since 2026-09-21 as part of PN 2.19: every function passes"),
    ("pn2.17", "speed-partner",    speed_partner,    "pn2.16", "experimental/LPM-10A-TX_PN2.17-speed-partner.bin",
     "PN 2.17 the SPEED screen adds a Switch row: the speeds the link partner advertises (IEEE regs 5 and 10)",
     "on the owner's unit since 2026-09-21 as part of PN 2.19: every function passes"),
    ("pn2.18", "length-reference", length_reference, "pn2.17", "experimental/LPM-10A-TX_PN2.18-length-reference.bin",
     "PN 2.18 Length: a REF target dials a known cable length and solves NVP from it (OK long: NVP / ZERO / REF)",
     "on the owner's unit since 2026-09-21 as part of PN 2.19: every function passes"),
    ("pn2.19", "cable-robust",     cable_test,       "pn2.18", "experimental/LPM-10A-TX_PN2.19-cable-robust.bin",
     "PN 2.19 Cable Test: median of 11 samples, switch mode needs a real short, 'Not connected', mode named RX unit",
     "flashed 2026-09-21, every function passes on the owner's unit; the one report: 'Not connected' of an earlier "
     "unplugged test stayed on screen after a Test Retry with the cable in a switch / the RX unit -> PN 2.20"),
    ("pn2.20", "cable-text-clear", cable_clear,      "pn2.19", "experimental/LPM-10A-TX_PN2.20-cable-text-clear.bin",
     "PN 2.20 Cable Test: the text line under the wires is wiped before every test (the stale 'Not connected')",
     "on the owner's unit 2026-09-21: the retry check passes (release v2.20; superseded by PN 2.21)"),
    ("pn2.21", "cable-values",     cable_values,     "pn2.20", "experimental/LPM-10A-TX_PN2.21-cable-values.bin",
     "PN 2.21 Cable Test: every wire ends with the reading that decided it (partner pin in switch mode)",
     "on the owner's unit 2026-09-21, both modes with retries (release v2.21; superseded by PN 2.23); the owner asked for the diag numbers"),
    ("pn2.22", "length-ref-anytime", length_ref_anytime, "pn2.21", "experimental/LPM-10A-TX_PN2.22-ref-anytime.bin",
     "PN 2.22 Length: REF reachable before a measurement; a REF dialled first is applied to the next result",
     "flashed 2026-09-21: the first REF without a result read 'REF 189.1' (the RAM cell's power-up content is in range) -> PN 2.23"),
    ("pn2.23", "length-ref-reset",   length_ref_reset,   "pn2.22", "experimental/LPM-10A-TX_PN2.23-ref-reset.bin",
     "PN 2.23 Length: REF starts at 10.0 m on every screen entry (PN 2.22 showed the RAM cell's power-up content)",
     "on the owner's unit 2026-09-21: REF 10.0 the first time, the fit works (release v2.23)"),
    ("pn2.23s", "speed-partner-validity", speed_partner_validity, "pn2.23", "experimental/LPM-10A-TX_PN2.23S-speed-validity.bin",
     "PN2.23S SPEED: failed partner ability reads display Unknown",
     "included in PN2.26: all functions passed on the owner's device, 2026-09-22"),
    ("pn2.23q", "qc-continuity", ReleaseStage("qc_continuity"), "pn2.23s", "experimental/LPM-10A-TX_PN2.23Q-qc-flex.bin",
     "PN2.23Q continuous QC acquisition and stable Init (historical candidate)",
     "owner rejected the session-table interface and flicker; superseded by PN2.23R"),
    ("pn2.23r", "qc-classic", ReleaseStage("qc_classic"), "pn2.23q", "experimental/LPM-10A-TX_PN2.23R-qc-auto.bin",
     "PN2.23R classic QC screen, automatic continuous testing and selective redraw",
     "owner reported test pass, 2026-09-22; later QC noise reports led to PN2.25 and PN2.26"),
    ("pn2.24", "length-integrity", ReleaseStage("length_integrity"), "pn2.23r", "experimental/LPM-10A-TX_PN2.24-length-qc.bin",
     "PN2.24 Length lifecycle/REF/progress guards and QC passing-sample qualification",
     "owner reported unstable QC indicators with a stationary cable; superseded by PN2.25"),
    ("pn2.25", "qc-timing", ReleaseStage("qc_timing"), "pn2.24", "experimental/LPM-10A-TX_PN2.25-qc-timing.bin",
     "PN2.25 elapsed-time-normalized QC counts and baseline migration",
     "owner reported garbled QC entry artwork; superseded by PN2.26"),
    ("pn2.26", "qc-display", ReleaseStage("qc_display"), "pn2.25", "experimental/LPM-10A-TX_PN2.26-qc-display.bin",
     "PN2.26 QC entry artwork follows calibration state; stale bitmaps cannot cover Init",
     "all functions passed on the owner's device, 2026-09-22 (release v2.26)"),
]

PROFILES = OrderedDict((n, Profile(n, *rest)) for n, *rest in _CHAIN)
BY_FLAG = {p.flag: p for p in PROFILES.values()}
LATEST = list(PROFILES)[-1]


def profile_patches(profile, extra=()):
    """Validate and order a complete profile, followed by its optional patches.

    Several modules verify the exact parent image. Inserting an experiment into
    that chain invalidates its digest even when the experiment changes unrelated
    bytes. Finish the reproducible profile first, then apply extras in registry
    order, once each. Validate the whole selection before the caller edits bytes.
    """
    base = profile.patch_ids()
    ids = base | set(extra)
    registered = {p.pid for p in patches.REGISTRY}
    unknown = ids - registered
    if unknown:
        raise PatchError(f"unknown patch id(s): {', '.join(sorted(unknown))}")
    if {'scan-sync', 'scan-recovery'} <= ids:
        raise PatchError('scan-sync and scan-recovery are alternative profiles; select only one')
    selected = [p for p in patches.REGISTRY if p.pid in ids]
    for p in selected:
        missing = set(p.requires) - ids
        if missing:
            raise PatchError(f"{p.pid} requires: {', '.join(sorted(missing))}")
    return ([p for p in selected if p.pid in base]
            + [p for p in selected if p.pid not in base])


def apply_profile(img, profile, log=None, extra=()):
    """Apply the immutable profile, then any extras, with validation before edits."""
    for p in profile_patches(profile, extra):
        before = len(img.log)
        p(img)
        if log is not None:
            log(p, before)
