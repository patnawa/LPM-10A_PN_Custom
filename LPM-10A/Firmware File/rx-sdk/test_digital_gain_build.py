"""Candidate provenance and patch footprint, independent of audio fixtures."""
import hashlib
import unittest

import auto_range_freshness
import digital_gain_continuity as fix
from lpm10rx.container import unwrap, wrap
from lpm10rx.image import PatchError
from lpm10rx import symbols
import sampling_fixes
import version_tag


class DigitalGainBuild(unittest.TestCase):
    def test_exact_parent_identity_and_limited_patch_footprint(self):
        img = auto_range_freshness.build_candidate()
        parent = bytes(img.data)
        self.assertEqual(hashlib.sha256(parent).hexdigest(), fix.PARENT_SHA256)
        fix.apply(img)
        self.assertEqual(img.version_tag, 'PN1.23G')
        self.assertEqual(img.read(version_tag.VERSION_STRING, 8), b'PN1.23G\0')
        allowed = set(range(auto_range_freshness.HELPER,
                            auto_range_freshness.HELPER + auto_range_freshness.SIZE))
        allowed.update(range(sampling_fixes.BOUNDARY, sampling_fixes.BOUNDARY + 4))
        allowed.update(range(version_tag.VERSION_STRING, version_tag.VERSION_STRING + 8))
        changes = {symbols.APP_BASE + i for i, (old, new) in enumerate(zip(parent, img.data))
                   if old != new}
        self.assertTrue(changes)
        self.assertLessEqual(changes, allowed)
        metadata = img.digital_gain_continuity
        self.assertEqual(len(img.data) - len(parent), metadata['helper_bytes'])
        self.assertEqual(metadata['persistent_ram_bytes'], 0)
        self.assertEqual(metadata['additional_stack_bytes'], 0)
        self.assertLessEqual(symbols.APP_BASE + len(img.data), symbols.EXTEND_LIMIT)

    def test_wrong_parent_and_double_application_fail_before_mutation(self):
        for modified in (False, True):
            with self.subTest(modified=modified):
                img = fix.build_candidate() if modified else auto_range_freshness.build_candidate()
                if not modified:
                    img.data[100] ^= 1
                before, log = bytes(img.data), list(img.log)
                with self.assertRaisesRegex(PatchError, 'exact PN1.23F'):
                    fix.apply(img)
                self.assertEqual(bytes(img.data), before)
                self.assertEqual(img.log, log)

    def test_reproducible_raw_and_canonical_update(self):
        first = bytes(fix.build_candidate().data)
        second = bytes(fix.build_candidate().data)
        self.assertEqual(first, second)
        update = wrap(first)
        name, raw = unwrap(update)
        self.assertEqual(raw, first)
        self.assertEqual(wrap(raw, name), update)


if __name__ == '__main__':
    unittest.main()
