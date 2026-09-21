"""PN 2.14 (the latest profile and the plain `build.py --write`) is PN 2.12 plus scan-recovery, never Sync32."""
import os
import unittest

import build
from profiles import PROFILES, LATEST
from test_profiles import BuildCli


class RecoveryProfile(unittest.TestCase):
    select = BuildCli.select

    def test_complete_parent_and_distinct_output(self):
        parent, _ = self.select('--portflash-status')
        actual, image = self.select('--scan-recovery', '--write')
        self.assertEqual(actual, [*parent, 'scan-recovery'])
        self.assertNotIn('scan-sync', actual)
        image.save.assert_called_once_with(PROFILES['pn2.14'].path(build.FW_DIR))
        self.assertEqual(PROFILES['pn2.14'].parent, 'pn2.12')

    def test_plain_write_descends_from_pn214(self):
        """`build.py --write` is the latest profile: PN 2.14 plus whatever came after it, never Sync32."""
        chain = []
        p = PROFILES[LATEST]
        while p is not None:
            chain.append(p.name)
            p = PROFILES[p.parent] if p.parent else None
        self.assertIn('pn2.14', chain)
        self.assertNotIn('pn2.13', chain)
        parent, _ = self.select('--scan-recovery')
        actual, image = self.select('--write')
        self.assertEqual(actual[:len(parent)], parent)
        self.assertEqual(set(actual) - set(parent), PROFILES[LATEST].patch_ids() - PROFILES['pn2.14'].patch_ids())
        image.save.assert_called_once_with(PROFILES[LATEST].path(build.FW_DIR))

    def test_explicit_path_and_dry_run(self):
        _, image = self.select('--scan-recovery')
        image.save.assert_not_called()
        _, image = self.select('--scan-recovery', '--write', '--out', 'bench/two-mode.bin')
        image.save.assert_called_once_with('bench/two-mode.bin')

    def test_prior_profiles_remain_separate(self):
        for args in (('--default',), ('--roadmap',), ('--portflash',), ('--audit',), ('--portflash-status',), ('--scan-sync',)):
            actual, _ = self.select(*args)
            self.assertNotIn('scan-recovery', actual, args)


if __name__ == '__main__':
    unittest.main()
