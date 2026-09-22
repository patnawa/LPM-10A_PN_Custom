"""Publication regressions run only against disposable synthetic releases."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "publish_current.py"
spec = importlib.util.spec_from_file_location("publish_current", SCRIPT)
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)


class PublicationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / "experimental").mkdir()
        self.tx, self.rx = publisher.DEFAULT_NAMES
        self.old = "LPM-10A-TX_PN2.22-length-progress.bin"
        self.old_rx = "APP_LPM-10RX_PN1.23-mains-tone-update.bin"
        (self.root / self.old).write_bytes(b"old release")
        (self.root / self.old_rx).write_bytes(b"old rx release")
        (self.root / "experimental" / self.old_rx).write_bytes(b"archived rx release")
        (self.root / "vendor-stock.bin").write_bytes(b"stock")
        (self.root / "local-backup.bin").write_bytes(b"backup")
        (self.root / publisher.MANIFEST).write_text(
            f"{'0' * 64}  {self.old}\n{'0' * 64}  {self.old_rx}\n", encoding="ascii")
        for name in (self.tx, self.rx):
            (self.root / "experimental" / name).write_bytes(name.encode())

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes()
                for p in self.root.rglob("*") if p.is_file()}

    def test_defaults_select_confirmed_tx_and_rx_update_releases(self):
        self.assertEqual(publisher.DEFAULT_NAMES, (
            "LPM-10A-TX_PN2.27A-analog-alignment.bin",
            "APP_LPM-10RX_PN1.24-gain-precision-update.bin",
        ))

    def test_single_uppercase_version_suffix_accepts_tx_and_rx_updates(self):
        for name in ("LPM-10A-TX_PN2.27A-analog-alignment.bin",
                     "LPM-10A-TX_PN2.27A.bin",
                     "APP_LPM-10RX_PN1.24A-gain-precision-update.bin",
                     "APP_LPM-10RX_PN1.24A-update.bin"):
            with self.subTest(name=name):
                self.assertEqual(publisher._release_name(name), name)

    def test_malformed_version_suffixes_and_paths_change_nothing(self):
        for name in ("LPM-10A-TX_PN2.27AB-analog-alignment.bin",
                     "LPM-10A-TX_PN2.27a-analog-alignment.bin",
                     "LPM-10A-TX_PN2.27A1-analog-alignment.bin",
                     "LPM-10A-TX_PN2.27_A-analog-alignment.bin",
                     "APP_LPM-10RX_PN1.24AA-gain-precision-update.bin",
                     "APP_LPM-10RX_PN1.24a-gain-precision-update.bin",
                     "APP_LPM-10RX_PN1.24A-gain-precision.bin",
                     "../LPM-10A-TX_PN2.27A-analog-alignment.bin",
                     "..\\LPM-10A-TX_PN2.27A-analog-alignment.bin",
                     "C:\\LPM-10A-TX_PN2.27A-analog-alignment.bin",
                     "LPM-10A-TX_PN2.27A-analog-alignment.bin\n"):
            with self.subTest(name=name):
                before = self.snapshot()
                with self.assertRaises(ValueError):
                    publisher.publish([name], self.root)
                self.assertEqual(self.snapshot(), before)

    def test_cleanup_recognizes_manifest_letter_releases_and_preserves_archives(self):
        old_letters = ("LPM-10A-TX_PN2.23R-qc-classic.bin",
                       "APP_LPM-10RX_PN1.23G-digital-gain-update.bin")
        keep = ("LPM-10A-TX_PN2.23RR-qc-classic.bin",
                "APP_LPM-10RX_PN1.22g-digital-gain-update.bin")
        manifest = (self.root / publisher.MANIFEST).read_text(encoding="ascii")
        for name in (*old_letters, *keep):
            (self.root / name).write_bytes(name.encode())
            (self.root / "experimental" / name).write_bytes(name.encode())
            manifest += f"{'0' * 64}  {name}\n"
        unlisted = "LPM-10A-TX_PN2.23Q-unlisted.bin"
        (self.root / unlisted).write_bytes(b"local unlisted release")
        (self.root / publisher.MANIFEST).write_text(manifest, encoding="ascii")
        publisher.publish(directory=self.root)
        for name in old_letters:
            self.assertFalse((self.root / name).exists())
        for name in (*old_letters, *keep):
            self.assertEqual((self.root / "experimental" / name).read_bytes(), name.encode())
        for name in keep:
            self.assertEqual((self.root / name).read_bytes(), name.encode())
        self.assertEqual((self.root / unlisted).read_bytes(), b"local unlisted release")

    def test_import_has_no_filesystem_side_effects(self):
        with patch("os.remove") as remove, patch("builtins.open") as file_open, \
                patch("shutil.copyfile") as copy, patch.object(publisher, "publish"):
            fresh = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(fresh)
        remove.assert_not_called()
        file_open.assert_not_called()
        copy.assert_not_called()

    def test_publishes_exact_hashes_and_preserves_unrelated_files(self):
        result = publisher.publish(directory=self.root)
        self.assertEqual(result, [(n, hashlib.sha256(n.encode()).hexdigest()) for n in (self.tx, self.rx)])
        for name, _ in result:
            self.assertEqual((self.root / name).read_bytes(), name.encode())
        self.assertEqual((self.root / publisher.MANIFEST).read_bytes(),
                         "".join(f"{digest}  {name}\n" for name, digest in result).encode())
        self.assertFalse((self.root / self.old).exists())
        self.assertFalse((self.root / self.old_rx).exists())
        self.assertEqual((self.root / "experimental" / self.old_rx).read_bytes(),
                         b"archived rx release")
        self.assertEqual((self.root / "vendor-stock.bin").read_bytes(), b"stock")
        self.assertEqual((self.root / "local-backup.bin").read_bytes(), b"backup")
        self.assertFalse(list(self.root.glob(".publish-*")))

    def test_missing_second_source_changes_nothing(self):
        (self.root / "experimental" / self.rx).unlink()
        before = self.snapshot()
        with self.assertRaises(ValueError):
            publisher.publish(directory=self.root)
        self.assertEqual(self.snapshot(), before)

    def test_invalid_names_and_empty_sources_change_nothing(self):
        for names in ([], [self.tx, self.tx], ["../" + self.tx], ["C:\\" + self.tx],
                      ["APP_LPM-10RX_PN1.23-mains-tone.bin"], ["vendor-stock.bin"]):
            with self.subTest(names=names):
                before = self.snapshot()
                with self.assertRaises(ValueError):
                    publisher.publish(names, self.root)
                self.assertEqual(self.snapshot(), before)
        (self.root / "experimental" / self.rx).write_bytes(b"")
        before = self.snapshot()
        with self.assertRaises(ValueError):
            publisher.publish(directory=self.root)
        self.assertEqual(self.snapshot(), before)

    def test_invalid_manifest_changes_nothing(self):
        (self.root / publisher.MANIFEST).write_text(f"{'0' * 64}  ../outside.bin\n")
        before = self.snapshot()
        with self.assertRaises(ValueError):
            publisher.publish(directory=self.root)
        self.assertEqual(self.snapshot(), before)

    def test_nonrelease_manifest_entry_does_not_authorize_deletion(self):
        (self.root / publisher.MANIFEST).write_text(f"{'0' * 64}  vendor-stock.bin\n")
        publisher.publish(directory=self.root)
        self.assertEqual((self.root / "vendor-stock.bin").read_bytes(), b"stock")

    def test_replace_failure_rolls_back_created_and_replaced_files(self):
        for prior in (None, b"previous tx"):
            with self.subTest(prior=prior):
                if prior is not None:
                    (self.root / self.tx).write_bytes(prior)
                before = self.snapshot()
                replace = publisher.os.replace

                def fail_second(source, target):
                    if Path(source).name == self.rx:
                        raise OSError("injected second-file failure")
                    return replace(source, target)

                with patch.object(publisher.os, "replace", side_effect=fail_second):
                    with self.assertRaisesRegex(OSError, "second-file"):
                        publisher.publish(directory=self.root)
                self.assertEqual(self.snapshot(), before)
                self.assertFalse(list(self.root.glob(".publish-*")))

    def test_cleanup_failure_restores_manifest_and_releases(self):
        before = self.snapshot()
        unlink = Path.unlink

        def fail_cleanup(path, *args, **kwargs):
            if path == self.root / self.old:
                raise OSError("injected cleanup failure")
            return unlink(path, *args, **kwargs)

        with patch.object(Path, "unlink", fail_cleanup):
            with self.assertRaisesRegex(OSError, "cleanup failure"):
                publisher.publish(directory=self.root)
        self.assertEqual(self.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
