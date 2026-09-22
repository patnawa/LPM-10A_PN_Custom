"""Fail-closed profile selection and current-release artifact verification."""
from contextlib import redirect_stdout, redirect_stderr
import hashlib
import io
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import build
from lpm10rx.container import wrap
from lpm10rx.image import PatchError
import profiles
import verify_release


class ProfileGuards(unittest.TestCase):
    def test_unknown_patch_is_rejected_before_any_patch_runs(self):
        image = SimpleNamespace(log=[])
        profile = SimpleNamespace(name="synthetic", patch_ids=lambda: {"present", "typo"})
        registered = Mock(pid="present")
        with patch.object(profiles.rx_patches, "REGISTRY", [registered]):
            with self.assertRaisesRegex(PatchError, "missing patches"):
                profiles.apply_profile(image, profile)
        registered.assert_not_called()

    def test_duplicate_patch_is_rejected_before_any_patch_runs(self):
        image = SimpleNamespace(log=[])
        profile = SimpleNamespace(name="synthetic", patch_ids=lambda: {"present"})
        registered = Mock(pid="present")
        with patch.object(profiles.rx_patches, "REGISTRY", [registered, registered]):
            with self.assertRaisesRegex(PatchError, "duplicate patches"):
                profiles.apply_profile(image, profile)
        registered.assert_not_called()

    def test_unknown_and_cyclic_parents_fail_without_hanging(self):
        child = profiles.Profile("child", "child", None, "missing", "fixture")
        with self.assertRaisesRegex(PatchError, "unknown parent"):
            child.patch_ids()
        child.parent = "child"
        with patch.object(profiles, "PROFILES", {"child": child}):
            with self.assertRaisesRegex(PatchError, "cyclic parent"):
                child.patch_ids()

    def test_only_and_all_are_rejected_before_loading_stock(self):
        args = ["build.py", "--only", "batt-critical-recover", "--all", "--out", "custom.bin"]
        with patch("sys.argv", args), patch.object(build, "Image") as loader, redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                build.main()
        self.assertEqual(error.exception.code, 2)
        loader.assert_not_called()


class ReleaseVerifier(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "release.bin"
        self.profile = SimpleNamespace(name="pn1.test")
        self.expected = b"expected raw"  # an aligned synthetic payload
        self.stock = b"synthetic stock"
        self.image = SimpleNamespace(original=self.stock, data=self.expected)
        self.addCleanup(patch.stopall)
        patch.object(verify_release, "Image", return_value=self.image).start()
        patch.object(verify_release.S, "STOCK_SHA256", hashlib.sha256(self.stock).hexdigest()).start()
        self.apply = patch.object(verify_release, "apply_profile").start()

    def test_raw_and_container_match_exact_payload(self):
        for data, kind in ((self.expected, "raw image"), (wrap(self.expected), "update container")):
            self.path.write_bytes(data)
            self.assertEqual(verify_release.verify_release(self.path, self.profile),
                             (kind, hashlib.sha256(self.expected).hexdigest()))

    def test_corruption_truncation_and_extra_data_fail(self):
        valid = wrap(self.expected)
        corrupted = bytearray(valid)
        corrupted[0x1000] ^= 1
        for data in (self.expected[:-1], self.expected + b"\0", bytes(corrupted), valid[:-1], valid + b"\0"):
            with self.subTest(size=len(data)):
                self.path.write_bytes(data)
                with self.assertRaisesRegex(PatchError, "does not match"):
                    verify_release.verify_release(self.path, self.profile)

    def test_wrong_stock_fails_before_applying_profile(self):
        self.path.write_bytes(self.expected)
        self.image.original = b"incorrect stock"
        with self.assertRaisesRegex(PatchError, "pinned V3.0.0"):
            verify_release.verify_release(self.path, self.profile)
        self.apply.assert_not_called()

    def test_valid_but_changed_internal_container_name_fails(self):
        self.path.write_bytes(wrap(self.expected, "other.bin"))
        with self.assertRaisesRegex(PatchError, "canonical update container"):
            verify_release.verify_release(self.path, self.profile)

    def test_cli_failure_has_nonzero_exit_status(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            verify_release.main([str(self.path)])
        self.assertEqual(error.exception.code, 1)


class CurrentPublishedRelease(unittest.TestCase):
    def test_published_update_rebuilds_as_latest_profile(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(verify_release.main([]), 0)


if __name__ == "__main__":
    unittest.main()
