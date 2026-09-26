"""PN1.31 default candidate preserves exact artifacts and historical builders."""
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
import clean_strength
import profiles
import rx_resilient
import verify_release
from lpm10rx.container import wrap
from lpm10rx.image import Image, PatchError


RAW_SHA = '407b0ba3b80883e4f640ef7e2040a56004ca780a5bd8b81cf3a371ca04a67135'
UPDATE_SHA = 'bf723bdd7b51ef850388cc485c02b471a8eb6a48e414701a24924ca336900180'
LATEST_RAW_SHA = '3e03d8ac13884a0fb3ad752b551ad346eb8e77e11998d7be9ca599923752094c'
LATEST_UPDATE_SHA = 'a6352ab9d604874511d835294d8d50fdd105049905b488e1aa263f13ce87126a'
SDK = Path(__file__).resolve().parent


def image_for(name):
    with redirect_stdout(io.StringIO()):
        image = Image(build.STOCK)
        profiles.apply_profile(image, profiles.PROFILES[name])
    return image


class ReleaseProfile(unittest.TestCase):
    def test_latest_candidate_and_pinned_historical_stages_rebuild_exact_bytes(self):
        self.assertEqual(profiles.LATEST, 'pn1.31')
        self.assertEqual(profiles.PROFILES[profiles.LATEST].output,
                         'experimental/APP_LPM-10RX_PN1.31-resilient.bin')
        for name, digest in (
            ('pn1.23', '384596d75fdfc95be31984173bac5fec116083b00bec4643757a8db9b0575392'),
            ('pn1.23f', '0c000550e4143032070bed34ab62ff24ec18fe60d53824a81ecb3d77c4e7e8c0'),
            ('pn1.23g', 'a0822e2f454e08d0a213e63a1bbf0cac9948776dd8b067560d4786605b0307bb'),
            ('pn1.24', '780951565cca543e50d38537cd179ee1793562c6a4642b688c8143b0e4d8b1ce'),
            ('pn1.25', 'c8617ea67228d86bad30a80af1f5e0d4f8fd3ae55983c81761e541efd362be95'),
            ('pn1.26', 'd3f19545c3d9f382534e60e0cc91e64af038b80f03da77ff0c61c4d4006edab8'),
            ('pn1.27', 'febd648daa98b51cf06c35e855afa4a088bb789c8ae643acf42b0f828c081c83'),
            ('pn1.28', '0e4b34b2347b1054035194500e1885fffeb1a90ed57753739ed4a2fbb8f5a619'),
            ('pn1.29', '092d7ad1e4a7d16130b746172b504bd5ee8998590512376962ec044395dfa378'),
            ('pn1.30', RAW_SHA),
        ):
            with self.subTest(profile=name):
                image = image_for(name)
                self.assertEqual(hashlib.sha256(image.data).hexdigest(), digest)
                self.assertEqual(image.version_tag, name.upper())
                archived = SDK.parent / profiles.PROFILES[name].output
                self.assertEqual(archived.read_bytes(), bytes(image.data),
                                 'the archived experimental file is this build')
        with redirect_stdout(io.StringIO()):
            standalone = clean_strength.build_candidate()
        self.assertEqual(image.data, standalone.data)
        self.assertEqual(hashlib.sha256(wrap(image.data)).hexdigest(), UPDATE_SHA)
        latest = image_for('pn1.31')
        self.assertEqual(hashlib.sha256(latest.data).hexdigest(), LATEST_RAW_SHA)
        self.assertEqual(hashlib.sha256(wrap(latest.data)).hexdigest(), LATEST_UPDATE_SHA)
        self.assertEqual(latest.version_tag, 'PN1.31')
        self.assertEqual(latest.data, rx_resilient.build_candidate().data)
        self.assertEqual((SDK.parent / profiles.PROFILES['pn1.31'].output).read_bytes(), bytes(latest.data))

    def test_default_explicit_and_alias_cli_write_exact_raw_and_update(self):
        with tempfile.TemporaryDirectory() as directory:
            fw = Path(directory)
            (fw / 'experimental').mkdir()
            selections = (
                ([], 'pn1.31', LATEST_RAW_SHA, LATEST_UPDATE_SHA),
                (['--profile', 'pn1.31'], 'pn1.31', LATEST_RAW_SHA, LATEST_UPDATE_SHA),
                (['--resilient'], 'pn1.31', LATEST_RAW_SHA, LATEST_UPDATE_SHA),
                (['--profile', 'pn1.30'], 'pn1.30', RAW_SHA, UPDATE_SHA),
                (['--clean-strength'], 'pn1.30', RAW_SHA, UPDATE_SHA),
            )
            for args, name, raw_sha, update_sha in selections:
                raw = fw / profiles.PROFILES[name].output
                update = Path(build.update_path(str(raw)))
                with self.subTest(args=args), patch.object(build, 'FW_DIR', directory), \
                        patch('sys.argv', ['build.py', *args, '--write']), \
                        redirect_stdout(io.StringIO()):
                    self.assertEqual(build.main(), 0)
                self.assertEqual(hashlib.sha256(raw.read_bytes()).hexdigest(), raw_sha)
                self.assertEqual(hashlib.sha256(update.read_bytes()).hexdigest(), update_sha)
                raw.unlink()
                update.unlink()

    def test_verifier_accepts_default_release_and_rejects_previous_payload_as_latest(self):
        latest = image_for('pn1.31')
        previous = image_for('pn1.30')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'APP_LPM-10RX_PN1.31-resilient-update.bin'
            path.write_bytes(wrap(latest.data))
            with patch.object(verify_release, 'FW', Path(directory)), redirect_stdout(io.StringIO()):
                self.assertEqual(verify_release.main([]), 0)
            path.write_bytes(wrap(previous.data))
            with redirect_stdout(io.StringIO()), self.assertRaisesRegex(PatchError, 'does not match pn1.31'):
                verify_release.verify_release(path, profiles.PROFILES['pn1.31'])
            self.assertEqual(verify_release.verify_release(path, profiles.PROFILES['pn1.30'])[1], RAW_SHA)
            path.write_bytes(wrap(image_for('pn1.29').data))
            with redirect_stdout(io.StringIO()), self.assertRaisesRegex(PatchError, 'does not match pn1.30'):
                verify_release.verify_release(path, profiles.PROFILES['pn1.30'])

    def test_candidate_import_orders_do_not_cycle_and_rebuild_latest(self):
        for first in ('profiles', 'auto_range_freshness', 'digital_gain_continuity', 'rx_precision',
                      'isolate', 'relative_isolate', 'knob_reference', 'pair_rank', 'level_display',
                      'clean_strength', 'rx_resilient', 'impulse_strength', 'publication_commit'):
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
                self.assertEqual(result.stdout.strip().splitlines()[-1], LATEST_RAW_SHA)

    def test_lazy_release_stages_follow_complete_parent_without_changing_custom_registry(self):
        selected = profiles.profile_patches(profiles.PROFILES['pn1.30'])
        self.assertEqual([p.pid for p in selected[-5:]],
                         ['rx-gain-freshness', 'rx-digital-gain', 'rx-gain-precision', 'rx-level-display',
                          'rx-clean-strength'])
        registry = {p.pid for p in profiles.rx_patches.REGISTRY}
        self.assertTrue(all(p.pid not in registry for p in selected[-5:]))
        latest = profiles.profile_patches(profiles.PROFILES['pn1.31'])
        self.assertEqual(latest[:-1], selected)
        self.assertEqual(latest[-1].pid, 'rx-resilient')
        self.assertNotIn(latest[-1].pid, registry)
        pn129 = profiles.profile_patches(profiles.PROFILES['pn1.29'])
        self.assertEqual(selected[:-1], pn129)
        parent = profiles.profile_patches(profiles.PROFILES['pn1.24'])
        self.assertEqual(pn129[:-1], parent)
        for branch in ('pn1.25', 'pn1.26', 'pn1.27'):
            with self.subTest(branch=branch):
                self.assertEqual(profiles.profile_patches(profiles.PROFILES[branch])[:-1], parent)
        pn127 = profiles.profile_patches(profiles.PROFILES['pn1.27'])
        self.assertEqual(profiles.profile_patches(profiles.PROFILES['pn1.28'])[:-1], pn127)


if __name__ == '__main__':
    unittest.main()
