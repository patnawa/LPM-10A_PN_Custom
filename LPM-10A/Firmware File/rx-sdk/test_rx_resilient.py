"""Final PN1.31 image, eligibility, exact-only fallback, and build integrity."""
import contextlib
import hashlib
import io
import random
import unittest

import clean_strength as cs
import impulse_strength
import publication_commit
import rx_resilient as candidate
import test_rx_impulse_strength as impulse
import test_rx_tracking_fragments as fragments
import test_rx_digital_tail_prototype as tails
from lpm10rx import symbols
from lpm10rx.container import wrap, unwrap
from lpm10rx.image import PatchError
from verify_digital import pattern


class Release(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with contextlib.redirect_stdout(io.StringIO()):
            cls.img = cs.build_candidate()
        cls.parent = bytes(cls.img.data)
        candidate.apply(cls.img)
        cls.data = bytes(cls.img.data)

    def test_exact_parent_scoped_changes_and_container(self):
        self.assertEqual(hashlib.sha256(self.parent).hexdigest(), candidate.PARENT_SHA256)
        allowed = set()
        for address, size in ((cs.ESTIMATE_CALL, 4), (publication_commit.EARLY_MARKER, 2),
                              (publication_commit.PUBLISHER, publication_commit.PUBLISHER_SIZE),
                              (0x0800CDE4, 8)):
            allowed.update(range(address, address + size))
        changed = {symbols.APP_BASE + n for n, (a, b) in enumerate(zip(self.parent, self.data)) if a != b}
        self.assertTrue(changed)
        self.assertLessEqual(changed, allowed)
        self.assertEqual(len(self.data) - len(self.parent), self.img.impulse_strength['helper_bytes'])
        self.assertLess(symbols.APP_BASE + len(self.data), symbols.EXTEND_LIMIT)
        self.assertEqual(self.data[:8], self.parent[:8], 'reset vector and stack unchanged')
        self.assertEqual(self.img.read(0x0800CDE4, 8), b'PN1.31\0\0')
        self.assertEqual(unwrap(wrap(self.data))[1], self.data)
        self.assertEqual(len(wrap(self.data)) % 4096, 0)
        self.assertEqual(self.img.resilient['persistent_ram_bytes'], 0)

    def test_changed_parent_and_duplicate_application_fail_without_mutation(self):
        with contextlib.redirect_stdout(io.StringIO()):
            img = cs.build_candidate()
        img.data[img.f(cs.ESTIMATE_CALL)] ^= 1
        for obj in (img, self.img):
            before = bytes(obj.data), list(obj.log)
            with self.assertRaises(PatchError):
                candidate.apply(obj)
            self.assertEqual((bytes(obj.data), obj.log), before)

    def test_standalone_estimator_checks_all_callsite_guards_before_mutating(self):
        for address in (cs.ESTIMATE_CALL, 0x08009EE2, 0x08009EF4, 0x0800A042):
            with contextlib.redirect_stdout(io.StringIO()):
                img = cs.build_candidate()
            img.data[img.f(address)] ^= 1
            before = bytes(img.data), list(img.log)
            with self.assertRaises(PatchError):
                impulse_strength.install(img)
            self.assertEqual((bytes(img.data), img.log), before)

    def test_written_release_is_exact_and_deterministic(self):
        self.assertEqual(bytes(candidate.build_candidate().data), self.data)
        raw = candidate.DIRECTORY / candidate.OUTPUT
        if raw.exists():
            self.assertEqual(raw.read_bytes(), self.data)
            self.assertEqual((candidate.DIRECTORY / candidate.UPDATE).read_bytes(), wrap(self.data))


class Eligibility(impulse.ImpulseStrength):
    # The inherited cases also exercise the complete composed release.
    def test_weak_cutoff_wrong_codes_noise_and_rails_keep_detection_policy(self):
        rng = random.Random(131)
        cases = [pattern(phase, dc, dc + amplitude)
                 for dc in (0, 1000, 4000) for phase in range(8) for amplitude in range(0, 25)]
        cases += [[1000 + 300 * ((code >> (i % 8)) & 1) for i in range(48)] for code in range(256)]
        cases += [[rng.randrange(4096) for _ in range(48)] for _ in range(256)]
        cases += [[dc] * 48 for dc in (0, 1, 2048, 4094, 4095)]
        cases += [pattern(phase, 0, 4095) for phase in range(8)]
        for index, samples in enumerate(cases):
            old, new = self.scored(samples, parent=True), self.scored(samples)
            self.assertEqual(new[2], old[2], (index, old, new))
            self.assertEqual(new[1] != 0, old[1] != 0, (index, old, new))
        print('PN1.31 detection-policy vectors unchanged:', len(cases))

    def test_exact_fragment_and_untrusted_tail_do_not_introduce_new_detection(self):
        # Full fit may improve strength. Exact-only fallback must not read or
        # infer strength from surrounding samples whose phase was not verified.
        count = 0
        for label, samples in list(fragments.fragment_vectors()) + list(tails.tail_rows()):
            old, new = self.scored(samples, parent=True), self.scored(samples)
            self.assertEqual(new[2], old[2], (label, old, new))
            self.assertEqual(new[1] != 0, old[1] != 0, (label, old, new))
            count += 1
        print('PN1.31 fragment/tail eligibility vectors:', count)


if __name__ == '__main__':
    unittest.main()
