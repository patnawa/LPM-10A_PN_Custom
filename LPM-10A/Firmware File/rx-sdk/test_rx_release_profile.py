"""PN1.27 default promotion preserves exact artifacts and historical builders."""
from contextlib import redirect_stdout
import hashlib
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import build
import knob_reference
import profiles
import verify_release
from lpm10rx.container import wrap
from lpm10rx.image import Image, PatchError


RAW_SHA = 'febd648daa98b51cf06c35e855afa4a088bb789c8ae643acf42b0f828c081c83'
UPDATE_SHA = 'b3aa9618e4eeaabc14120bcae6a381771d8b8b0c65a85f38b0d1808cdbf36de1'
SDK = Path(__file__).resolve().parent


def image_for(name):
    with redirect_stdout(io.StringIO()):
        image = Image(build.STOCK)
        profiles.apply_profile(image, profiles.PROFILES[name])
    return image


class ReleaseProfile(unittest.TestCase):
    def test_latest_and_pinned_parent_stages_rebuild_exact_owner_tested_bytes(self):
        self.assertEqual(profiles.LATEST, 'pn1.27')
        self.assertEqual(profiles.PROFILES[profiles.LATEST].output,
                         'experimental/APP_LPM-10RX_PN1.27-knob.bin')
        for name, digest in (
            ('pn1.23', '384596d75fdfc95be31984173bac5fec116083b00bec4643757a8db9b0575392'),
            ('pn1.23f', '0c000550e4143032070bed34ab62ff24ec18fe60d53824a81ecb3d77c4e7e8c0'),
            ('pn1.23g', 'a0822e2f454e08d0a213e63a1bbf0cac9948776dd8b067560d4786605b0307bb'),
            ('pn1.24', '780951565cca543e50d38537cd179ee1793562c6a4642b688c8143b0e4d8b1ce'),
            ('pn1.25', 'c8617ea67228d86bad30a80af1f5e0d4f8fd3ae55983c81761e541efd362be95'),
            ('pn1.26', 'd3f19545c3d9f382534e60e0cc91e64af038b80f03da77ff0c61c4d4006edab8'),
            ('pn1.27', RAW_SHA),
        ):
            with self.subTest(profile=name):
                image = image_for(name)
                self.assertEqual(hashlib.sha256(image.data).hexdigest(), digest)
                self.assertEqual(image.version_tag, name.upper())
                archived = SDK.parent / profiles.PROFILES[name].output
                self.assertEqual(archived.read_bytes(), bytes(image.data),
                                 'the archived experimental file is this build')
        with redirect_stdout(io.StringIO()):
            standalone = knob_reference.build_candidate()
        self.assertEqual(image.data, standalone.data)
        self.assertEqual(hashlib.sha256(wrap(image.data)).hexdigest(), UPDATE_SHA)

    def test_default_explicit_and_alias_cli_write_exact_raw_and_update(self):
        with tempfile.TemporaryDirectory() as directory:
            fw = Path(directory)
            (fw / 'experimental').mkdir()
            raw = fw / profiles.PROFILES['pn1.27'].output
            update = Path(build.update_path(str(raw)))
            for args in ([], ['--profile', 'pn1.27'], ['--knob']):
                with self.subTest(args=args), patch.object(build, 'FW_DIR', directory), \
                        patch('sys.argv', ['build.py', *args, '--write']), \
                        redirect_stdout(io.StringIO()):
                    self.assertEqual(build.main(), 0)
                self.assertEqual(hashlib.sha256(raw.read_bytes()).hexdigest(), RAW_SHA)
                self.assertEqual(hashlib.sha256(update.read_bytes()).hexdigest(), UPDATE_SHA)
                raw.unlink()
                update.unlink()

    def test_verifier_accepts_default_release_and_rejects_previous_payload_as_latest(self):
        latest = image_for('pn1.27')
        previous = image_for('pn1.24')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'APP_LPM-10RX_PN1.27-knob-update.bin'
            path.write_bytes(wrap(latest.data))
            with patch.object(verify_release, 'FW', Path(directory)), redirect_stdout(io.StringIO()):
                self.assertEqual(verify_release.main([]), 0)
            path.write_bytes(wrap(previous.data))
            with redirect_stdout(io.StringIO()), self.assertRaisesRegex(PatchError, 'does not match pn1.27'):
                verify_release.verify_release(path, profiles.PROFILES['pn1.27'])

    def test_candidate_import_orders_do_not_cycle_and_rebuild_latest(self):
        for first in ('profiles', 'auto_range_freshness', 'digital_gain_continuity', 'rx_precision',
                      'isolate', 'relative_isolate', 'knob_reference'):
            with self.subTest(first=first):
                code = (
                    f'import {first}\n'
                    'import profiles, hashlib, build\n'
                    'from lpm10rx.image import Image\n'
                    'image=Image(build.STOCK)\n'
                    'profiles.apply_profile(image,profiles.PROFILES[profiles.LATEST])\n'
                    'print(hashlib.sha256(image.data).hexdigest())\n'
                )
                result = subprocess.run([sys.executable, '-c', code], cwd=SDK,
                                        capture_output=True, text=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip().splitlines()[-1], RAW_SHA)

    def test_lazy_release_stages_follow_complete_parent_without_changing_custom_registry(self):
        selected = profiles.profile_patches(profiles.PROFILES['pn1.27'])
        self.assertEqual([p.pid for p in selected[-4:]],
                         ['rx-gain-freshness', 'rx-digital-gain', 'rx-gain-precision', 'rx-knob-reference'])
        registry = {p.pid for p in profiles.rx_patches.REGISTRY}
        self.assertTrue(all(p.pid not in registry for p in selected[-4:]))
        parent = profiles.profile_patches(profiles.PROFILES['pn1.24'])
        self.assertEqual(selected[:-1], parent)
        for branch in ('pn1.25', 'pn1.26'):
            with self.subTest(branch=branch):
                self.assertEqual(profiles.profile_patches(profiles.PROFILES[branch])[:-1], parent)


if __name__ == '__main__':
    unittest.main()
