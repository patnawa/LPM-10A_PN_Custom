"""Keep the two-mode PN2.14 profile separate from the retired Sync32 trial."""
import contextlib
import io
import unittest
from unittest.mock import patch

import build
import test_sync_profile


class RecoveryProfile(unittest.TestCase):
    select = test_sync_profile.SyncProfile.select

    def test_complete_parent_and_distinct_output(self):
        parent, _ = self.select('--portflash-status')
        actual, image = self.select('--scan-recovery', '--write')
        self.assertEqual(actual, [*parent, 'scan-recovery'])
        self.assertNotIn('scan-sync', actual)
        image.save.assert_called_once_with(build.SCAN_RECOVERY_OUT)

    def test_explicit_path_and_dry_run(self):
        _, image = self.select('--scan-recovery')
        image.save.assert_not_called()
        _, image = self.select('--scan-recovery', '--write', '--out', 'bench/two-mode.bin')
        image.save.assert_called_once_with('bench/two-mode.bin')

    def test_custom_complete_selection_needs_explicit_output(self):
        expected, _ = self.select('--scan-recovery')
        actual, image = self.select('--only', ','.join(expected), '--write', '--out', 'bench/custom.bin')
        self.assertEqual(actual, expected)
        image.save.assert_called_once_with('bench/custom.bin')

    def test_conflicting_selectors_reject_before_image_load(self):
        arguments = [('--scan-recovery', flag) for flag in
                     ('--scan-sync', '--portflash-status', '--audit', '--portflash', '--roadmap', '--all')]
        arguments += [('--scan-recovery', '--only', ''),
                      ('--scan-recovery', '--with', 'scan-sync'),
                      ('--only', 'scan-recovery'),
                      ('--with', 'scan-recovery', '--write'),
                      ('--only', 'scan-recovery,scan-sync', '--out', 'bench/invalid.bin'),
                      ('--all', '--out', 'bench/invalid.bin')]
        for args in arguments:
            with self.subTest(args=args), patch('sys.argv', ['build.py', *args]), \
                    patch.object(build, 'Image') as loader, \
                    contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as caught:
                    build.main()
                self.assertEqual(caught.exception.code, 2)
                loader.assert_not_called()

    def test_prior_profiles_remain_separate(self):
        for flag in (None, '--roadmap', '--portflash', '--audit', '--portflash-status', '--scan-sync'):
            actual, _ = self.select(*(() if flag is None else (flag,)))
            self.assertNotIn('scan-recovery', actual)


if __name__ == '__main__':
    unittest.main()
