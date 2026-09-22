"""Provenance, composition and container checks for the PN1.24 candidate."""
import contextlib
import hashlib
import io
import unittest

import digital_gain_continuity
from lpm10rx.container import unwrap, wrap
from lpm10rx.image import PatchError
from lpm10rx import symbols
import rx_precision
import version_tag


def build():
    with contextlib.redirect_stdout(io.StringIO()):
        return rx_precision.build_candidate()


class PrecisionBuild(unittest.TestCase):
    def test_exact_owner_tested_parent_and_application_boundary(self):
        with contextlib.redirect_stdout(io.StringIO()):
            parent = digital_gain_continuity.build_candidate()
        original = bytes(parent.data)
        self.assertEqual(hashlib.sha256(original).hexdigest(), rx_precision.PARENT_SHA256)
        img = rx_precision.apply(parent)
        self.assertEqual(img.version_tag, 'PN1.24')
        self.assertEqual(img.read(version_tag.VERSION_STRING, 8), b'PN1.24\0\0')
        self.assertEqual(img.rx_precision['parent_size'], len(original))
        self.assertEqual(len(img.data) % 4, 0)
        self.assertLessEqual(symbols.APP_BASE + len(img.data), symbols.EXTEND_LIMIT)
        # Keep the vector table, clock setup and stock ADC transaction intact.
        for begin, end in ((0x08006800, 0x08006948), (0x080072A4, 0x080072E8),
                           (0x0800A208, 0x0800A4FC), (0x0800A7D8, 0x0800A97C),
                           (0x0800AB74, 0x0800AC1C)):
            with self.subTest(begin=hex(begin)):
                self.assertEqual(img.read(begin, end-begin),
                                 original[begin-symbols.APP_BASE:end-symbols.APP_BASE])

    def test_wrong_parent_and_double_application_fail_without_mutation(self):
        for already_applied in (False, True):
            img = build()
            if not already_applied:
                with contextlib.redirect_stdout(io.StringIO()):
                    img = digital_gain_continuity.build_candidate()
                img.data[100] ^= 1
            before, log = bytes(img.data), list(img.log)
            with self.assertRaisesRegex(PatchError, 'exact PN1.23G'):
                rx_precision.apply(img)
            self.assertEqual(bytes(img.data), before)
            self.assertEqual(img.log, log)

    def test_combined_patch_footprint_and_shared_ram_ownership(self):
        with contextlib.redirect_stdout(io.StringIO()):
            parent = digital_gain_continuity.build_candidate()
        before = bytes(parent.data)
        img = rx_precision.apply(parent)
        allowed = set()
        # These are independently pinned seams in the exact G parent, including
        # the reset instruction pair inside its appended boundary helper.
        for start, size in ((0x080076A2, 4), (0x0800770E, 4),
                            (0x08008408, 4), (0x08009F20, 4),
                            (0x08009F62, 40), (0x08009FC8, 4),
                            (0x0800A500, 4), (0x0800CDE4, 8),
                            (0x0800D0FE, 4)):
            allowed.update(range(start, start+size))
        changes = {symbols.APP_BASE+i for i,(a,b) in enumerate(zip(before,img.data))
                   if a != b}
        self.assertTrue(changes)
        self.assertLessEqual(changes, allowed)
        self.assertEqual(img.sample_age_guard['completed_at'], 0x20000204)
        self.assertEqual(img.sample_age_guard['analysis_at'], 0x20000208)
        self.assertEqual(img.sample_age_guard['completed_valid'], 0x2000020C)
        self.assertEqual(img.sample_age_guard['persistent_ram_bytes'], 12)
        self.assertEqual(img.gain_response['persistent_ram_bytes'], 0)
        self.assertEqual(img.analog_selective['persistent_ram_bytes'], 0)
        self.assertEqual(img.gain_response['completed_valid'],
                         img.sample_age_guard['completed_valid'])
        self.assertEqual(len(img.data)-len(before),
                         img.sample_age_guard['helper_bytes']+img.gain_response['helper_bytes'])

    def test_composed_raw_is_repeatable_and_update_is_canonical(self):
        first, second = bytes(build().data), bytes(build().data)
        self.assertEqual(first, second)
        update = wrap(first)
        name, payload = unwrap(update)
        self.assertEqual(payload, first)
        self.assertEqual(wrap(payload, name), update)


if __name__ == '__main__':
    unittest.main()
