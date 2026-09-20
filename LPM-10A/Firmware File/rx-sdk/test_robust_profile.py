"""CLI profile-boundary regressions; no vendor image or assembler required."""
import contextlib
import hashlib
import io
import os
import unittest
from unittest.mock import Mock, patch as mock_patch

import build


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
        image = Mock(original=b"", data=bytearray(), log=[])
        image.diff_offsets.return_value = []
        image.save.return_value = "fixture-digest"
        with mock_patch("sys.argv", ["build.py", *args]), \
                mock_patch.object(build.patches, "REGISTRY", registry), \
                mock_patch.object(build, "Image", return_value=image), \
                mock_patch.object(build.S, "STOCK_SHA256", hashlib.sha256(b"").hexdigest()), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(build.main(), 0)
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
        profiles = [((), ["batt-critical-recover"]), (("--roadmap",), roadmap),
                    (("--audit",), audit), (("--followup",), followup),
                    (("--precision",), precision),
                    (("--pinpoint",), [*precision, "rx-pinpoint"])]
        for args, expected in profiles:
            with self.subTest(args=args):
                actual, image = self.select(*args)
                self.assertEqual(actual, expected)
                image.save.assert_not_called()

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
