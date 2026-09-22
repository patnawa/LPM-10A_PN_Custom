"""Synthetic CLI routing plus real parent-guard rejection of custom builds."""
import contextlib
import hashlib
import io
import os
import unittest
from unittest.mock import Mock, mock_open, patch as mock_patch

import build
from lpm10rx.container import wrap
import version_tag


def assert_custom_rejected(test, args, failed_patch):
    """Custom syntax is valid; incompatible ancestry must fail before writing."""
    output = io.StringIO()
    with mock_patch("sys.argv", ["build.py", *args, "--write"]), \
            mock_patch.object(build.Image, "save") as save, \
            mock_patch("build.open", mock_open(), create=True) as container_open, \
            contextlib.redirect_stdout(output):
        test.assertEqual(build.main(), 2)
    test.assertIn(f"[FAIL] {failed_patch} requires the complete, exact", output.getvalue())
    save.assert_not_called()
    container_open.assert_not_called()


class RobustProfileTests(unittest.TestCase):
    def select(self, *args):
        """Exercise the real CLI selection and output routing with inert patches."""
        applied = []
        registry = []
        for original in build.patches.REGISTRY:
            def record(img, pid=original.pid):
                applied.append(pid)
            for name in ("pid", "title", "risk", "default", "group"):
                setattr(record, name, getattr(original, name))
            registry.append(record)
        raw = b"test"
        image = Mock(original=raw, data=bytearray(raw), log=[])
        # Byte-exact version-tagging is covered by test_profiles; here retain
        # its real selection/identity behavior over an inert image.
        image.read.return_value = version_tag.STOCK
        image.diff_offsets.return_value = []
        image.save.return_value = "fixture-digest"
        with mock_patch("sys.argv", ["build.py", *args]), \
                mock_patch.object(build.patches, "REGISTRY", registry), \
                mock_patch.object(build, "Image", return_value=image), \
                mock_patch.object(build.S, "STOCK_SHA256", hashlib.sha256(raw).hexdigest()), \
                mock_patch("build.open", mock_open(), create=True) as container_open, \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(build.main(), 0)
        if "--write" in args:
            image.save.assert_called_once()
            output_path = image.save.call_args.args[0]
            container_open.assert_called_once_with(build.update_path(output_path), "wb")
            container_open().write.assert_called_once_with(wrap(bytes(image.data)))
        else:
            image.save.assert_not_called()
            container_open.assert_not_called()
        return applied, image

    def test_robust_is_complete_pinpoint_parent_then_new_patch(self):
        parent, _ = self.select("--pinpoint")
        actual, image = self.select("--robust", "--write")
        self.assertEqual(actual, [*parent, "rx-robust"])
        image.save.assert_called_once_with(os.path.join(
            build.FW_DIR, "experimental/APP_LPM-10RX_PN1.9-robust.bin"))

    def test_historical_profile_selections_remain_unchanged(self):
        roadmap = ["batt-critical-recover", "activity-before-autooff", "digital-correlation",
                   "recent-signal-autooff", "adc-complete", "main-watchdog", "digital-strength"]
        audit = [*roadmap, "mains-sampler-publish-last", "dft-square-overflow"]
        followup = [*audit, "rx-followup"]
        precision = [*followup, "rx-precision"]
        profiles = [(("--default",), ["batt-critical-recover"]), (("--roadmap",), roadmap),
                    (("--audit",), audit), (("--followup",), followup),
                    (("--precision",), precision),
                    (("--pinpoint",), [*precision, "rx-pinpoint"])]
        for args, expected in profiles:
            with self.subTest(args=args):
                actual, image = self.select(*args)
                self.assertEqual(actual, expected)
                image.save.assert_not_called()

    def test_implicit_and_explicit_latest_select_identical_tagged_profile(self):
        expected = [p.pid for p in build.patches.REGISTRY if p.pid in build.PROFILES[build.LATEST].patch_ids()]
        for args in ((), ("--profile", build.LATEST)):
            with self.subTest(args=args):
                selected, image = self.select(*args, "--write")
                self.assertEqual(selected, expected)
                self.assertEqual(image.version_tag, build.LATEST.upper())
                image.save.assert_called_once_with(os.path.join(build.FW_DIR, build.PROFILES[build.LATEST].output))

    def test_robust_allows_explicit_output_path(self):
        _, image = self.select("--robust", "--write", "--out", "bench/receiver.bin")
        image.save.assert_called_once_with("bench/receiver.bin")

    def test_invalid_combinations_reject_before_loading_image(self):
        combinations = [("--robust", flag) for flag in
                        ("--pinpoint", "--precision", "--followup", "--audit",
                         "--roadmap", "--all")]
        combinations.extend([("--robust", "--only", "batt-critical-recover"),
                             ("--robust", "--only", ""),
                             ("--only", "rx-robust", "--write")])
        for args in combinations:
            with self.subTest(args=args), mock_patch("sys.argv", ["build.py", *args]), \
                    mock_patch.object(build, "Image") as loader, \
                    contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as caught:
                    build.main()
                self.assertEqual(caught.exception.code, 2)
                loader.assert_not_called()


if __name__ == "__main__":
    unittest.main()
