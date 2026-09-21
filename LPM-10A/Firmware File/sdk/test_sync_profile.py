"""The retired PN 2.13 Sync32 branch stays reproducible and stays out of every other profile."""
import os
import unittest

import build
from profiles import PROFILES, LATEST
from test_profiles import BuildCli


class SyncProfile(unittest.TestCase):
    select = BuildCli.select
    ordered = BuildCli.ordered

    def test_fixed_profile_is_exact_parent_plus_sync_patch(self):
        parent, _ = self.select('--portflash-status')
        actual, image = self.select('--scan-sync', '--write')
        self.assertEqual(actual, [*parent, 'scan-sync'])
        image.save.assert_called_once_with(os.path.join(
            build.FW_DIR, 'experimental', 'LPM-10A-TX_PN2.13-sync.bin'))
        self.assertEqual(PROFILES['pn2.13'].parent, 'pn2.12')

    def test_no_other_profile_carries_sync(self):
        for prof in PROFILES.values():
            if prof.name != 'pn2.13':
                self.assertNotIn('scan-sync', prof.patch_ids(), prof.name)
        actual, _ = self.select()
        self.assertEqual(actual, self.ordered(PROFILES[LATEST].patch_ids()))
        self.assertNotIn('scan-sync', actual)
        actual, _ = self.select('--default')
        self.assertNotIn('scan-sync', actual)

    def test_fixed_profile_allows_explicit_output(self):
        _, image = self.select('--scan-sync', '--write', '--out', 'bench/tx.bin')
        image.save.assert_called_once_with('bench/tx.bin')

    def test_custom_complete_selection_requires_explicit_output(self):
        expected, _ = self.select('--scan-sync')
        actual, image = self.select('--only', ','.join(expected), '--write', '--out', 'bench/custom.bin')
        self.assertEqual(actual, expected)
        image.save.assert_called_once_with('bench/custom.bin')


if __name__ == '__main__':
    unittest.main()
