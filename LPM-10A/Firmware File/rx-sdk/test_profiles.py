"""Every build profile reproduces its archived image byte for byte (in memory, nothing written)."""
import hashlib
import io
import os
import unittest
from contextlib import redirect_stdout

from lpm10rx.image import Image, STOCK_NAME
import rx_patches as patches
from profiles import PROFILES, LATEST, apply_profile

HERE = os.path.dirname(os.path.abspath(__file__))
FW_DIR = os.path.dirname(HERE)


def build(profile):
    img = Image(os.path.join(FW_DIR, STOCK_NAME))
    with redirect_stdout(io.StringIO()):
        apply_profile(img, profile)
    return bytes(img.data)


class ProfileChain(unittest.TestCase):
    def test_every_profile_matches_its_archived_image(self):
        for prof in PROFILES.values():
            path = os.path.join(FW_DIR, prof.output)
            if not os.path.exists(path):
                continue
            with self.subTest(profile=prof.name):
                with open(path, 'rb') as f:
                    archived = f.read()
                self.assertEqual(hashlib.sha256(build(prof)).hexdigest(), hashlib.sha256(archived).hexdigest(),
                                 f'{prof.name} does not rebuild {prof.output}')

    def test_chain_parents_are_known_and_latest_is_last(self):
        for prof in PROFILES.values():
            self.assertTrue(prof.parent is None or prof.parent in PROFILES, prof.name)
        self.assertEqual(list(PROFILES)[-1], LATEST)

    def test_tagged_profiles_carry_their_name_in_the_version_slot(self):
        for prof in PROFILES.values():
            if prof.tag:
                data = build(prof)
                slot = data[0x0800CDE4 - 0x08006800:0x0800CDE4 - 0x08006800 + 8]
                self.assertEqual(slot, prof.name.upper().encode().ljust(8, b'\0'), prof.name)

    def test_each_profile_adds_exactly_its_own_patches(self):
        for prof in PROFILES.values():
            if prof.parent:
                self.assertEqual(prof.patch_ids() - PROFILES[prof.parent].patch_ids(), prof.own_patches, prof.name)


if __name__ == '__main__':
    unittest.main()
