"""Exercise TX profile/output isolation through the real CLI parser."""
import contextlib
import hashlib
import io
import os
import unittest
from unittest.mock import Mock, patch

import build


class SyncProfile(unittest.TestCase):
    def select(self, *arguments):
        applied, registry = [], []
        for original in build.patches.REGISTRY:
            def record(image, pid=original.pid):
                applied.append(pid)
            for field in ('pid', 'title', 'risk', 'default', 'group', 'requires'):
                setattr(record, field, getattr(original, field))
            registry.append(record)
        image = Mock(original=b'', data=bytearray(), log=[], name='fixture',
                     payload_len=0, orig_payload_len=0, cave_ptr=0,
                     cave_start=0, cave_end=0, extended=0)
        image.summary.return_value = 'name\nlength\ncave'
        image.diff_offsets.return_value = []
        image.save.return_value = 'fixture-digest'
        with patch('sys.argv', ['build.py', *arguments]), \
                patch.object(build.patches, 'REGISTRY', registry), \
                patch.object(build, 'Image', return_value=image), \
                patch.object(build, 'STOCK_SHA', hashlib.sha256(b'').hexdigest()), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(build.main(), 0)
        return applied, image

    def test_fixed_profile_is_exact_parent_plus_sync_patch(self):
        parent, _ = self.select('--portflash-status')
        actual, image = self.select('--scan-sync', '--write')
        self.assertEqual(actual, [*parent, 'scan-sync'])
        image.save.assert_called_once_with(os.path.join(
            build.FW_DIR, 'experimental', 'LPM-10A-TX_PN2.13-sync.bin'))

    def test_default_and_historical_profiles_exclude_sync(self):
        default = [p.pid for p in build.patches.REGISTRY if p.default]
        actual, image = self.select()
        self.assertEqual(actual, default)
        image.save.assert_not_called()
        for profile in ('--roadmap', '--portflash', '--audit', '--portflash-status'):
            with self.subTest(profile=profile):
                actual, image = self.select(profile)
                self.assertNotIn('scan-sync', actual)
                image.save.assert_not_called()

    def test_fixed_profile_allows_explicit_output(self):
        _, image = self.select('--scan-sync', '--write', '--out', 'bench/tx.bin')
        image.save.assert_called_once_with('bench/tx.bin')

    def test_custom_complete_selection_requires_explicit_output(self):
        expected, _ = self.select('--scan-sync')
        actual, image = self.select('--only', ','.join(expected), '--write', '--out', 'bench/custom.bin')
        self.assertEqual(actual, expected)
        image.save.assert_called_once_with('bench/custom.bin')

    def test_invalid_combinations_reject_before_loading_image(self):
        combinations = [('--scan-sync', flag) for flag in
                        ('--portflash-status', '--audit', '--portflash', '--roadmap', '--all')]
        combinations += [('--scan-sync', '--only', ''),
                         ('--scan-sync', '--only', 'scan-sync'),
                         ('--scan-sync', '--with', 'scan-sync'),
                         ('--only', 'scan-sync', '--write'),
                         ('--with', 'scan-sync', '--write'),
                         ('--all', '--write')]
        for args in combinations:
            with self.subTest(args=args), patch('sys.argv', ['build.py', *args]), \
                    patch.object(build, 'Image') as loader, \
                    contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as result:
                    build.main()
                self.assertEqual(result.exception.code, 2)
                loader.assert_not_called()


if __name__ == '__main__':
    unittest.main()
