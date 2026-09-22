"""PN 1.13 fixed ancestry/output isolation; earlier profiles remain selectable."""
import contextlib
import io
import os
import unittest
from unittest.mock import patch

import audio_clock_fixes
import build
import test_robust_profile


class AudioClockProfile(unittest.TestCase):
    select = test_robust_profile.RobustProfileTests.select

    def test_exact_overload_ancestry_and_distinct_output(self):
        parent, _ = self.select('--overload')
        selected, image = self.select('--audio-clock', '--write')
        self.assertEqual(selected, [*parent, 'rx-audio-clock'])
        self.assertNotIn('rx-sync', selected)
        image.save.assert_called_once_with(os.path.join(build.FW_DIR, audio_clock_fixes.OUTPUT))

    def test_dry_run_and_explicit_output(self):
        _, image = self.select('--audio-clock')
        image.save.assert_not_called()
        _, image = self.select('--audio-clock', '--out', 'bench/rx.bin', '--write')
        image.save.assert_called_once_with('bench/rx.bin')

    def test_custom_complete_selection_requires_distinct_output(self):
        ids, _ = self.select('--audio-clock')
        selected, image = self.select('--only', ','.join(ids), '--out', 'bench/custom.bin', '--write')
        self.assertEqual(selected, ids)
        image.save.assert_called_once_with('bench/custom.bin')

    def test_invalid_selectors_reject_before_image_loading(self):
        invalid = [('--audio-clock', flag) for flag in
                   ('--overload', '--tracking', '--sync', '--robust', '--pinpoint',
                    '--precision', '--followup', '--audit', '--roadmap', '--all')]
        invalid += [('--audio-clock', '--only', ''),
                    ('--audio-clock', '--only', 'rx-audio-clock'),
                    ('--only', 'rx-audio-clock'),
                    ('--only', 'rx-audio-clock', '--write')]
        for args in invalid:
            with self.subTest(args=args), patch('sys.argv', ['build.py', *args]), \
                    patch.object(build, 'Image') as loader, contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    build.main()
                self.assertEqual(error.exception.code, 2)
                loader.assert_not_called()

    def test_incompatible_custom_ancestry_rejects_before_writing(self):
        test_robust_profile.assert_custom_rejected(
            self, ('--only', 'rx-audio-clock,rx-sync', '--out', 'bench/rx.bin'), 'rx-sync')

    def test_preserved_profiles_exclude_audio_clock(self):
        for args in ((), ('--roadmap',), ('--audit',), ('--followup',), ('--precision',),
                     ('--pinpoint',), ('--robust',), ('--sync',), ('--tracking',), ('--overload',)):
            with self.subTest(args=args):
                selected, _ = self.select(*args)
                self.assertNotIn('rx-audio-clock', selected)


if __name__ == '__main__':
    unittest.main()
