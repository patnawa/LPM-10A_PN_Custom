"""Sync32 CLI profile/output boundaries using synthetic selection fixtures."""
import contextlib
import io
import os
import unittest
from unittest.mock import patch as mock_patch

import build
import test_robust_profile


class SyncProfileTests(unittest.TestCase):
    select = test_robust_profile.RobustProfileTests.select

    def test_sync_is_complete_robust_parent_then_new_patch(self):
        parent, _ = self.select('--robust')
        actual, image = self.select('--sync', '--write')
        self.assertEqual(actual, [*parent, 'rx-sync'])
        image.save.assert_called_once_with(os.path.join(
            build.FW_DIR, 'experimental/APP_LPM-10RX_PN1.10-sync.bin'))

    def test_sync_dry_run_does_not_write(self):
        actual, image = self.select('--sync')
        self.assertEqual(actual[-2:], ['rx-robust', 'rx-sync'])
        image.save.assert_not_called()

    def test_sync_allows_explicit_output_path(self):
        _, image = self.select('--sync', '--write', '--out', 'bench/receiver.bin')
        image.save.assert_called_once_with('bench/receiver.bin')

    def test_custom_sync_selection_requires_explicit_output_and_keeps_it(self):
        parent, _ = self.select('--robust')
        ids = [*parent, 'rx-sync']
        selected, image = self.select('--only', ','.join(ids), '--out', 'bench/custom.bin', '--write')
        self.assertEqual(selected, ids)
        image.save.assert_called_once_with('bench/custom.bin')

    def test_invalid_combinations_reject_before_loading_image(self):
        combinations = [('--sync', flag) for flag in
                        ('--robust', '--pinpoint', '--precision', '--followup',
                         '--audit', '--roadmap', '--all')]
        combinations += [('--sync', '--only', 'batt-critical-recover'),
                         ('--sync', '--only', ''), ('--only', 'rx-sync', '--write'),
                         ('--only', 'rx-sync'), ('--all', '--write')]
        for args in combinations:
            with self.subTest(args=args), mock_patch('sys.argv', ['build.py', *args]), \
                    mock_patch.object(build, 'Image') as loader, \
                    contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as caught:
                    build.main()
                self.assertEqual(caught.exception.code, 2)
                loader.assert_not_called()

    test_historical_profile_selections_remain_unchanged = test_robust_profile.RobustProfileTests.test_historical_profile_selections_remain_unchanged


if __name__ == '__main__':
    unittest.main()
