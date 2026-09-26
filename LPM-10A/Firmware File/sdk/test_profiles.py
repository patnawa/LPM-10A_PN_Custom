"""Every build profile reproduces its released or archived image byte for byte (in memory, nothing written).

    python -m unittest test_profiles -v

The pinned digests are the ones published with each build (SHA256SUMS files in
../archive and ../experimental, docs/releases).  The baseline is checked the same way.
"""
import contextlib
import hashlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch as mock_patch

from lpm10a.image import Image, PatchError
import patches
import build
from profiles import PROFILES, LATEST, BY_FLAG, apply_profile, baseline_ids, profile_patches

HERE = os.path.dirname(os.path.abspath(__file__))
FW_DIR = os.path.dirname(HERE)
STOCK = os.path.join(FW_DIR, "LPM-10A-TX_V2.0.7_260610.bin")

# what each profile must rebuild: (published digest, where the file was archived)
PINNED = {
    "baseline": ("f9d8cbfe3995e2e8e03a205808a93ec2c07fcc39fd6e6917ae1da40b74e4d6a0", "archive/LPM-10A-TX_PN2.9.bin"),
    "pn2.9":    ("2a82c86de8bf9d81dd191ca742d83e6d4b6d359db22daf9a6b0c65f48b5583dd", None),
    "pn2.10":   ("cedadd7057b46ae6a8153ae1a479d4f81cd49fcc53ae92033a083faed4ab76db", None),
    "pn2.11":   ("de27a1448cc1977d00a2104abb9f48dda227e8d71c9040d986769f8e5ffe43f9", None),
    "pn2.12":   ("3d2db80f8288744191fe1ddb2855a83b900166dd365e1583c6270dfb460a0076", None),
    "pn2.13":   ("79ea4157e86e3a6613cb603d7e34e6b61e4f949844095b583bd4ff4f88da1fbd", None),
    "pn2.14":   ("a7402de6f18e39df55bbe53f5641efd5135f0de4d81f9407515cf9d8710c5527", None),
    "pn2.15":   ("e50d53a460870b4105986086e674552dc5dae18c04a92687ecaf6ec26b43445e", None),
    "pn2.16":   ("1b6cbfab6f1f01e9e160ad706cbd00a32669278fe451c39ede2c7e9c7c88ac18", None),
    "pn2.17":   ("78b50e5d003a957f3f941a8b50e39494bbbadb2179d1971bca9a39459e775071", None),
    "pn2.18":   ("b5538e723044e540b497f37de2550bb715ec9113316a683600e1d81b768c8a9f", None),
    "pn2.19":   ("8353e0b018d9ad2de7a98f3fe72ff8812dbc431504dbcf36adcc5b7fc080725d", None),
    "pn2.20":   ("9eaa0fdeded19a0f7c6bb77c386c8abad9ab8d9a4720341d7ec2a79a03866d02", None),
    "pn2.21":   ("23fbc3b4404c866dc8a7961ac7b1cf8ebcfb0bf3b4b2338c6f798d07db0a353e", None),
    "pn2.22":   ("371ed6e2ff8e7aa303a917ddc012f3871bb54c5ffa2f1af96a254db85a0b7c7a", None),
    "pn2.23":   ("8351bbf503d5360a1773b5caf5b574968719493bf961fc5de3015f76ca768528", "LPM-10A-TX_PN2.23-ref-reset.bin"),
    "pn2.23s":  ("007bbeff0deeca6a7d3df63ce4732a0f03350ae01cb3e6e541b067198fcec478", None),
    "pn2.23q":  ("969c775eba1f40805f9e64325a4e0838edf39fa0e964652a47c1158d0f7d5115", None),
    "pn2.23r":  ("cd94672633420a44e9bf9232de87adcc794cc57068035a260ffb6e4ffa35e8b4", None),
    "pn2.24":   ("b3716f6538f8980c075fb85e925cb2ba1d86e46440174d450615fa98253131e7", None),
    "pn2.25":   ("b6d407b662331bf4cf2fdb4f007a595cf75c61d31fa4986dea47d23aaf3c25ae", None),
    "pn2.26":   ("c77579f018bb820532b3c5974ae63fbf04c4e60359188f7e39a8a8f9a1533df8", None),
    "pn2.27":   ("575a410fea87da9bc4ecb273d1fd931712bb8a2d911d771c55332dc2a2c4e8b2", None),
    "pn2.27a":  ("c12b127a634baa038c2504b8e30262a38f963c4900e0967094d7a7f4b1084420", None),
    "pn2.28":   ("03b34b991664731c582b1247b25b29830a8be242f8ddad6be394d901ea9fcc9a", None),
    "pn2.29":   ("47cebcb4f884d99a3adf938fa7cd4b6c69e020c672bcda57c64523a8ef96ab44", None),
    "pn2.30":   ("bfabdc34cf9c8976ece4bdbbac449b5eb4c96a47738bf60684e91221dbeddeb6", None),
    "pn2.33":   ("84f9fb991a5bf43f0e29d978277ebe76baa58ff21714b430c1b6cef040751e91", "LPM-10A-TX_PN2.33-cable-safe.bin"),
    "pn2.34":   ("92ebb4cd60e7b652f32ca65cfa21401c1657fa63ee1b945864fed3c74a422227", "LPM-10A-TX_PN2.34-cable-session.bin"),
}
VERSION_SLOTS = (0x08011660, 0x08012E6C)        # About screen, boot log (patches.p_version)


def build_ids(ids):
    with contextlib.redirect_stdout(io.StringIO()):
        img = Image(STOCK)
        for p in patches.REGISTRY:
            if p.pid in ids:
                p(img)
    return bytes(img.finalize().data)


class ProfileImages(unittest.TestCase):
    built = {}

    @classmethod
    def image(cls, name):
        if name not in cls.built:
            ids = set(baseline_ids()) if name == "baseline" else PROFILES[name].patch_ids()
            cls.built[name] = build_ids(ids)
        return cls.built[name]

    def test_every_profile_matches_its_published_digest(self):
        for name, (digest, _) in PINNED.items():
            with self.subTest(profile=name):
                self.assertEqual(hashlib.sha256(self.image(name)).hexdigest(), digest)

    def test_archived_files_still_carry_the_pinned_digest(self):
        for name, (digest, archived) in PINNED.items():
            candidates = [archived] if archived else []
            if name != "baseline":
                candidates.append(PROFILES[name].output)
            for rel in candidates:
                path = os.path.join(FW_DIR, rel)
                if not os.path.exists(path):
                    continue
                with self.subTest(file=rel):
                    with open(path, "rb") as f:
                        self.assertEqual(hashlib.sha256(f.read()).hexdigest(), digest)

    def test_profile_version_names_the_build(self):
        for prof in PROFILES.values():
            data = self.image(prof.name)
            for site in VERSION_SLOTS:
                o = site - 0x0800A000 + 0x1000
                with self.subTest(profile=prof.name, site=hex(site)):
                    self.assertEqual(data[o:o + 8], prof.version.encode().ljust(8, b"\0"))

    def test_apply_profile_is_the_registry_order_build(self):
        with contextlib.redirect_stdout(io.StringIO()):
            img = Image(STOCK)
            apply_profile(img, PROFILES[LATEST])
        self.assertEqual(bytes(img.finalize().data), self.image(LATEST))


class ProfileChain(unittest.TestCase):
    def test_parents_are_known_and_latest_is_last(self):
        for prof in PROFILES.values():
            self.assertTrue(prof.parent is None or prof.parent in PROFILES, prof.name)
        self.assertEqual(list(PROFILES)[-1], LATEST)
        self.assertEqual(LATEST, "pn2.34")
        self.assertEqual({p.flag for p in PROFILES.values()}, set(BY_FLAG))

    def test_each_profile_adds_exactly_its_own_patches(self):
        registered = {p.pid for p in patches.REGISTRY}
        for prof in PROFILES.values():
            self.assertTrue(prof.own_patches <= registered, prof.name)
            base = PROFILES[prof.parent].patch_ids() if prof.parent else set(baseline_ids())
            self.assertEqual(prof.patch_ids() - base, prof.own_patches, prof.name)

    def test_profiles_are_dependency_complete_and_never_untested(self):
        by_id = {p.pid: p for p in patches.REGISTRY}
        for prof in PROFILES.values():
            ids = prof.patch_ids()
            for pid in ids:
                self.assertTrue(set(by_id[pid].requires) <= ids, f"{prof.name}: {pid} requires {by_id[pid].requires}")
                if prof.name != "pn2.13":           # the retired Sync32 branch keeps its label
                    self.assertNotEqual(by_id[pid].risk, "untested", f"{prof.name}: {pid}")
        self.assertNotIn("scan-sync", PROFILES[LATEST].patch_ids())

    def test_release_builders_and_registry_import_without_cycles(self):
        for first in ('patches', 'profiles', 'tone_precision', 'tone_alignment',
                      'cable_check', 'cable_colours', 'cable_fix', 'cable_safe', 'cable_session'):
            with self.subTest(first_import=first):
                result = subprocess.run(
                    [sys.executable, '-c',
                     f'import {first}; from profiles import PROFILES, LATEST; '
                     'assert LATEST == "pn2.34"; '
                     'assert PROFILES[LATEST].version == "PN2.34"'],
                    cwd=HERE, capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class ProfileExtras(unittest.TestCase):
    """Use real patch functions: mocked CLI selection cannot catch parent-hash failures."""

    def test_tuning_extras_change_only_the_requested_bytes_after_latest(self):
        with contextlib.redirect_stdout(io.StringIO()):
            base = Image(STOCK)
            apply_profile(base, PROFILES[LATEST])
            base.finalize()
            for extra, site, replacement in (("blind-zone-50cm", 0x0801253A, b"\x32\x28"),
                                               ("batt-grace", 0x0800E6EA, b"\x3c\x20")):
                with self.subTest(extra=extra):
                    img = Image(STOCK)
                    applied = []
                    apply_profile(img, PROFILES[LATEST], extra=(extra,),
                                  log=lambda p, before: applied.append(p.pid))
                    expected = bytearray(base.data)
                    offset = base.f(site)
                    expected[offset:offset + len(replacement)] = replacement
                    self.assertEqual(bytes(img.finalize().data), bytes(expected))
                    self.assertEqual(applied[-1], extra)

    def test_invalid_api_extras_fail_before_any_image_changes(self):
        for profile, extras in ((LATEST, ("no-such-patch",)),
                                (LATEST, ("scan-sync",)),
                                ("pn2.12", ("cable-diag",))):
            with self.subTest(profile=profile, extras=extras), contextlib.redirect_stdout(io.StringIO()):
                img = Image(STOCK)
                with self.assertRaises(PatchError):
                    apply_profile(img, PROFILES[profile], extra=extras)
                self.assertEqual(bytes(img.data), img.original)
                self.assertEqual(img.log, [])
                self.assertEqual(img.ram_allocs, [])

    def test_repeated_profile_patch_in_extras_is_applied_once(self):
        selected = profile_patches(PROFILES[LATEST], ("length-ref-reset", "length-ref-reset"))
        self.assertEqual([p.pid for p in selected],
                         [p.pid for p in patches.REGISTRY if p.pid in PROFILES[LATEST].patch_ids()])

    def test_real_cli_builds_documented_custom_examples(self):
        for extra in ("blind-zone-50cm", "batt-grace", "cable-diag", "speed-partner-validity"):
            with self.subTest(extra=extra), mock_patch("sys.argv", ["build.py", "--with", extra]), \
                    contextlib.redirect_stdout(io.StringIO()) as output:
                result = build.main()
            self.assertEqual(result, 0, output.getvalue())


class BuildCli(unittest.TestCase):
    """The parser through build.main(): which patches are applied and where the file goes (nothing built)."""

    def select(self, *arguments):
        applied, registry = [], []
        for original in patches.REGISTRY:
            def record(image, pid=original.pid):
                applied.append(pid)
            for field in ("pid", "title", "risk", "default", "group", "requires"):
                setattr(record, field, getattr(original, field))
            registry.append(record)
        image = Mock(original=b"", data=bytearray(), log=[], name="fixture",
                     payload_len=0, orig_payload_len=0, cave_ptr=0, cave_start=0, cave_end=0, extended=0)
        image.summary.return_value = "name\nlength\ncave"
        image.diff_offsets.return_value = []
        image.save.return_value = "fixture-digest"
        with mock_patch("sys.argv", ["build.py", *arguments]), \
                mock_patch.object(build.patches, "REGISTRY", registry), \
                mock_patch.object(build, "Image", return_value=image), \
                mock_patch.object(build, "STOCK_SHA", hashlib.sha256(b"").hexdigest()), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(build.main(), 0)
        return applied, image

    def ordered(self, ids):
        return [p.pid for p in patches.REGISTRY if p.pid in ids]

    def test_no_flags_builds_the_latest_profile(self):
        applied, image = self.select("--write")
        self.assertEqual(applied, self.ordered(PROFILES[LATEST].patch_ids()))
        image.save.assert_called_once_with(PROFILES[LATEST].path(build.FW_DIR))
        applied, image = self.select()
        image.save.assert_not_called()

    def test_real_default_and_explicit_latest_emit_the_emulator_validated_candidate(self):
        for selection in ((), ('--profile', 'pn2.34')):
            with self.subTest(selection=selection), tempfile.TemporaryDirectory() as folder:
                output = os.path.join(folder, 'tx.bin')
                with mock_patch('sys.argv', ['build.py', *selection, '--out', output, '--write']), \
                        contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(build.main(), 0)
                with open(output, 'rb') as artifact:
                    data = artifact.read()
                self.assertEqual(hashlib.sha256(data).hexdigest(), PINNED['pn2.34'][0])
                self.assertEqual(len(data), 405504)

    def test_default_is_the_frozen_baseline(self):
        applied, image = self.select("--default", "--write")
        self.assertEqual(applied, baseline_ids())
        image.save.assert_called_once_with(build.OUT)

    def test_every_profile_by_name_and_by_alias(self):
        for prof in PROFILES.values():
            for args in (("--profile", prof.name), (f"--{prof.flag}",)):
                with self.subTest(args=args):
                    applied, image = self.select(*args, "--write")
                    self.assertEqual(applied, self.ordered(prof.patch_ids()))
                    image.save.assert_called_once_with(prof.path(build.FW_DIR))

    def test_with_adds_to_a_profile_or_the_baseline_and_needs_out_to_write(self):
        applied, image = self.select("--with", "blind-zone-50cm", "--out", "bench/x.bin", "--write")
        self.assertEqual(applied, self.ordered(PROFILES[LATEST].patch_ids()) + ["blind-zone-50cm"])
        image.save.assert_called_once_with("bench/x.bin")
        applied, image = self.select("--default", "--with", "batt-grace", "--out", "bench/y.bin", "--write")
        self.assertEqual(applied, self.ordered(set(baseline_ids()) | {"batt-grace"}))
        applied, image = self.select("--profile", "pn2.12", "--with", "batt-grace")     # dry run needs no --out
        self.assertEqual(applied, self.ordered(PROFILES["pn2.12"].patch_ids()) + ["batt-grace"])
        image.save.assert_not_called()

    def test_only_builds_exactly_the_listed_set(self):
        want = self.ordered(PROFILES["pn2.12"].patch_ids())
        applied, image = self.select("--only", ",".join(want), "--out", "bench/custom.bin", "--write")
        self.assertEqual(applied, want)
        image.save.assert_called_once_with("bench/custom.bin")

    def test_rejections_happen_before_the_stock_image_is_loaded(self):
        exits = [("--scan-sync", "--scan-recovery"), ("--profile", "pn2.14", "--roadmap"),
                 ("--default", "--profile", "pn2.14"), ("--only", "font-pro", "--all"),
                 ("--only", "font-pro", "--with", "batt-grace"), ("--only", "font-pro", "--default"),
                 ("--only", "font-pro", "--portflash"), ("--all", "--with", "batt-grace"), ("--all", "--default"),
                 ("--all", "--scan-recovery"), ("--profile", "pn9.9"),
                 ("--with", "batt-grace", "--write"), ("--only", "font-pro", "--write"), ("--all", "--write"),
                 ("--all", "--out", "bench/all.bin"),                       # scan-sync and scan-recovery together
                 ("--with", "scan-sync", "--out", "bench/both.bin")]        # on top of pn2.14
        returns = [("--only", ""), ("--only", "no-such-patch"), ("--with", "no-such-patch"),
                   ("--only", "length-blind-text"),                          # needs length-decimal
                   ("--only", "scan-recovery")]                              # needs its parents
        for args in exits + returns:
            with self.subTest(args=args), mock_patch("sys.argv", ["build.py", *args]), \
                    mock_patch.object(build, "Image") as loader, \
                    contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                try:
                    code = build.main()
                except SystemExit as ex:
                    code = ex.code
                    self.assertIn(args, exits)
                else:
                    self.assertIn(args, returns)
                self.assertEqual(code, 2)
                loader.assert_not_called()


if __name__ == "__main__":
    unittest.main()
