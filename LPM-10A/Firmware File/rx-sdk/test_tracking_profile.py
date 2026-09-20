"""Selection/output isolation for the PN 1.11 profile and preserved parents."""
import contextlib
import io
import os
import unittest
from unittest.mock import patch

import build
import test_robust_profile


class TrackingProfile(unittest.TestCase):
    select = test_robust_profile.RobustProfileTests.select

    def test_complete_parent_without_sync(self):
        parent,_ = self.select('--robust')
        selected,img = self.select('--tracking','--write')
        self.assertEqual(selected,[*parent,'rx-tracking'])
        self.assertNotIn('rx-sync',selected)
        img.save.assert_called_once_with(os.path.join(
            build.FW_DIR,'experimental/APP_LPM-10RX_PN1.11-tracking.bin'))

    def test_dry_run_and_explicit_output(self):
        _,img = self.select('--tracking')
        img.save.assert_not_called()
        _,img = self.select('--tracking','--write','--out','bench/rx.bin')
        img.save.assert_called_once_with('bench/rx.bin')

    def test_invalid_selectors_reject_before_loading(self):
        invalid = [('--tracking',flag) for flag in ('--sync','--robust','--pinpoint',
                   '--precision','--followup','--audit','--roadmap','--all')]
        invalid += [('--tracking','--only',''),('--only','rx-tracking'),
                    ('--only','rx-tracking,rx-sync','--out','bench/rx.bin'),
                    ('--all','--out','bench/rx.bin')]
        for args in invalid:
            with self.subTest(args=args),patch('sys.argv',['build.py',*args]), \
                 patch.object(build,'Image') as loader,contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    build.main()
                self.assertEqual(error.exception.code,2)
                loader.assert_not_called()

    def test_earlier_profiles_do_not_include_tracking(self):
        for args in ((),('--roadmap',),('--audit',),('--followup',),('--precision',),
                     ('--pinpoint',),('--robust',),('--sync',)):
            selected,_ = self.select(*args)
            self.assertNotIn('rx-tracking',selected)


if __name__ == '__main__':
    unittest.main()
