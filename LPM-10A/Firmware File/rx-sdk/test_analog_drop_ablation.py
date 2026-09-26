"""Local A/B diagnostics isolate PN1.31 components without altering releases."""
import contextlib
import hashlib
import io
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import analog_drop_ablation as ab
import clean_strength as cs
import publication_commit as pc
import profiles
import rx_resilient
import version_tag
from lpm10rx import symbols
from lpm10rx.container import DEFAULT_NAME, HEADER_SIZE, unwrap, wrap
from lpm10rx.image import PatchError


class DiagnosticAblations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with contextlib.redirect_stdout(io.StringIO()):
            cls.parent = cs.build_candidate()
            cls.images = {kind: ab.build_candidate(kind) for kind in ('A', 'B')}
        cls.parent_bytes = bytes(cls.parent.data)

    def test_exact_parent_and_no_profile_promotion(self):
        self.assertEqual(hashlib.sha256(self.parent_bytes).hexdigest(), ab.PARENT_SHA256)
        self.assertEqual(profiles.LATEST, 'pn1.31')
        self.assertNotIn('pn1.31a', profiles.PROFILES)
        self.assertNotIn('pn1.31b', profiles.PROFILES)

    def test_changed_parent_duplicate_and_unknown_selection_fail_without_mutation(self):
        for kind in ('A', 'B'):
            with contextlib.redirect_stdout(io.StringIO()):
                corrupt = cs.build_candidate()
            corrupt.data[0x100] ^= 1
            for image in (corrupt, self.images[kind]):
                before = bytes(image.data), list(image.log)
                with self.assertRaises(PatchError):
                    ab.apply(image, kind)
                self.assertEqual((bytes(image.data), image.log), before)
        with contextlib.redirect_stdout(io.StringIO()):
            image = cs.build_candidate()
        before = bytes(image.data), list(image.log)
        with self.assertRaises(PatchError):
            ab.apply(image, 'unknown')
        self.assertEqual((bytes(image.data), image.log), before)

    def test_only_declared_component_and_version_bytes_change(self):
        for kind, image in self.images.items():
            sites = [(version_tag.VERSION_STRING, version_tag.SLOT)]
            if kind == 'A':
                sites.append((cs.ESTIMATE_CALL, 4))
            else:
                sites += [(pc.EARLY_MARKER, 2), (pc.PUBLISHER, pc.PUBLISHER_SIZE)]
            allowed = {address for site, size in sites for address in range(site, site+size)}
            changes = {symbols.APP_BASE+i for i, (old, new) in enumerate(zip(self.parent_bytes, image.data))
                       if old != new}
            self.assertTrue(changes)
            self.assertLessEqual(changes, allowed)
            self.assertEqual(bytes(image.data[:32]), self.parent_bytes[:32], 'reset vectors stay unchanged')
            self.assertEqual(image.read(version_tag.VERSION_STRING, 8), ('PN1.31'+kind).encode()+b'\0')
            self.assertEqual(image.version_tag, 'PN1.31'+kind)
            self.assertEqual(image.analog_drop_ablation['persistent_ram_bytes'], 0)
            self.assertLessEqual(symbols.APP_BASE+len(image.data), symbols.EXTEND_LIMIT)

    def test_a_has_only_impulse_component_and_preserves_complete_old_publication(self):
        image = self.images['A']
        curve = self.parent.clean_strength['curve']
        curve_size = len(self.parent.assemble_at(curve, cs.CURVE_SOURCE))
        self.assertEqual(image.read(curve, curve_size), self.parent.read(curve, curve_size))
        self.assertEqual(image.read(pc.PUBLISHER, pc.PUBLISHER_SIZE),
                         self.parent.read(pc.PUBLISHER, pc.PUBLISHER_SIZE))
        self.assertEqual(len(image.data)-len(self.parent_bytes), 200)
        self.assertEqual(image.impulse_strength['helper_bytes'], 200)
        self.assertEqual(image.impulse_strength['persistent_ram_bytes'], 0)
        self.assertFalse(hasattr(image, 'publication_commit'))

    def test_b_has_only_publication_component_and_no_appended_estimator(self):
        image = self.images['B']
        self.assertEqual(len(image.data), len(self.parent_bytes))
        self.assertEqual(image.read(cs.ESTIMATE_CALL, 4), self.parent.read(cs.ESTIMATE_CALL, 4))
        estimator = self.parent.clean_strength['estimator']
        old_code = self.parent.assemble_at(estimator, cs.ESTIMATOR_SOURCE)
        self.assertEqual(image.read(estimator, len(old_code)), old_code)
        self.assertEqual(image.publication_commit['helper_bytes'], 0)
        self.assertEqual(image.publication_commit['persistent_ram_bytes'], 0)
        self.assertFalse(hasattr(image, 'impulse_strength'))

    def test_canonical_container_extracts_exact_raw_without_bootloader_changes(self):
        for kind, image in self.images.items():
            raw = bytes(image.data)
            container = wrap(raw)
            self.assertEqual(unwrap(container), (DEFAULT_NAME, raw))
            header = DEFAULT_NAME.encode().ljust(32, b'\0')+struct.pack('<III', HEADER_SIZE, len(raw), HEADER_SIZE+len(raw)-1)
            self.assertEqual(container[:HEADER_SIZE], header.ljust(HEADER_SIZE, b'\0'))
            self.assertEqual(container, wrap(unwrap(container)[1]))
            self.assertEqual(len(container), {'A': 36864, 'B': 32768}[kind])

    def test_deterministic_rebuild_and_canonical_pn131_unchanged(self):
        for kind, image in self.images.items():
            self.assertEqual(ab.build_candidate(kind).data, image.data)
        current = bytes(rx_resilient.build_candidate().data)
        self.assertEqual(hashlib.sha256(current).hexdigest(),
                         '3e03d8ac13884a0fb3ad752b551ad346eb8e77e11998d7be9ca599923752094c')
        self.assertEqual((ab.DIRECTORY/rx_resilient.OUTPUT).read_bytes(), current)
        self.assertEqual((ab.DIRECTORY/rx_resilient.UPDATE).read_bytes(), wrap(current))

    def test_cli_is_dry_by_default_and_write_creates_only_named_diagnostics(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            with patch.object(ab, 'DIRECTORY', directory), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(ab.main([]), 0)
                self.assertEqual(list(directory.iterdir()), [])
                self.assertEqual(ab.main(['--write']), 0)
            expected = {ab.SUMS}
            lines = []
            for kind, image in self.images.items():
                for name, data in ab.artifacts(kind, image):
                    expected.add(name)
                    self.assertEqual((directory/name).read_bytes(), data)
                    lines.append(f'{hashlib.sha256(data).hexdigest()}  {name}')
            self.assertEqual({path.name for path in directory.iterdir()}, expected)
            self.assertEqual((directory/ab.SUMS).read_text(encoding='ascii'), '\n'.join(lines)+'\n')


if __name__ == '__main__':
    unittest.main()
