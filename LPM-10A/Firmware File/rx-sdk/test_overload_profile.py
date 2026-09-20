"""Selection/output isolation for PN 1.12 and the unchanged earlier profiles."""
import contextlib
import io
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import build
from lpm10rx.image import PatchError
import overload_fixes
import test_robust_profile


class OverloadProfile(unittest.TestCase):
    select = test_robust_profile.RobustProfileTests.select

    def test_complete_tracking_parent_then_overload_without_sync(self):
        parent, _ = self.select('--tracking')
        selected, img = self.select('--overload', '--write')
        self.assertEqual(selected, [*parent, 'rx-overload'])
        self.assertEqual(selected[-2:], ['rx-tracking', 'rx-overload'])
        self.assertNotIn('rx-sync', selected)
        img.save.assert_called_once_with(os.path.join(build.FW_DIR, overload_fixes.OUTPUT))

    def test_dry_run_and_explicit_output(self):
        _, img = self.select('--overload')
        img.save.assert_not_called()
        _, img = self.select('--overload', '--write', '--out', 'bench/rx.bin')
        img.save.assert_called_once_with('bench/rx.bin')

    def test_custom_selection_requires_and_preserves_explicit_output(self):
        ids, _ = self.select('--overload')
        selected, img = self.select('--only', ','.join(ids), '--out', 'bench/custom.bin', '--write')
        self.assertEqual(selected, ids)
        img.save.assert_called_once_with('bench/custom.bin')

    def test_invalid_selectors_reject_before_loading(self):
        invalid = [('--overload', flag) for flag in
                   ('--tracking', '--sync', '--robust', '--pinpoint', '--precision',
                    '--followup', '--audit', '--roadmap', '--all')]
        invalid += [('--overload', '--only', ''),
                    ('--overload', '--only', 'rx-overload'),
                    ('--only', 'rx-overload'),
                    ('--only', 'rx-overload', '--write'),
                    ('--only', 'rx-tracking,rx-overload'),
                    ('--only', 'rx-overload,rx-sync', '--out', 'bench/rx.bin'),
                    ('--only', 'rx-overload,rx-tracking,rx-sync', '--out', 'bench/rx.bin'),
                    ('--all', '--out', 'bench/rx.bin')]
        for args in invalid:
            with self.subTest(args=args), patch('sys.argv', ['build.py', *args]), \
                 patch.object(build, 'Image') as loader, contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    build.main()
                self.assertEqual(error.exception.code, 2)
                loader.assert_not_called()

    def test_earlier_profiles_do_not_include_overload(self):
        for args in ((), ('--roadmap',), ('--audit',), ('--followup',), ('--precision',),
                     ('--pinpoint',), ('--robust',), ('--sync',), ('--tracking',)):
            selected, _ = self.select(*args)
            self.assertNotIn('rx-overload', selected)

    def test_parent_guard_rejects_before_mutation(self):
        img = SimpleNamespace(data=bytearray(b'not the complete PN 1.11 profile'))
        previous = bytes(img.data)
        with self.assertRaises(PatchError):
            overload_fixes.apply(img)
        self.assertEqual(bytes(img.data), previous)
        self.assertFalse(hasattr(img, 'overload'))


if __name__ == '__main__':
    unittest.main()
