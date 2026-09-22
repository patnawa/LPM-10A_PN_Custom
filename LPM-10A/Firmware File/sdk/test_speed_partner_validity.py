"""Actual MDIO-read and GUI paths for the opt-in partner-capability validity fix."""
import contextlib
import io
import unittest

from lpm10a.image import Image, PatchError
from lpm10a.thumb import assemble
from profiles import PROFILES, apply_profile
import patches
import speed_partner as SP
import speed_partner_validity as SV
import test_speed_partner as T
from thai.engine import Scene


class SpeedPartnerValidity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with contextlib.redirect_stdout(io.StringIO()):
            cls.parent = Image(T.STOCK)
            apply_profile(cls.parent, PROFILES['pn2.23'])
            cls.parent.finalize()
            cls.img = Image(T.STOCK)
            apply_profile(cls.img, PROFILES['pn2.23'], extra=(SV.PATCH_ID,))
            cls.data = bytes(cls.img.finalize().data)

    def scene(self, lpa, status, lang=1, patched=True):
        img = self.img if patched else self.parent
        s = Scene(image=self.data if patched else bytes(img.data), lang=lang)
        reads = []
        values = {5: lpa, 10: status, 0x11: 0x6000}

        def mdio(uc):
            register = s.arg(0)
            reads.append(register)
            s.ret(values[register])
            return True

        s.at[T.MDIO_READ] = mdio
        self.assertEqual(s.call(img.speed_partner['read']), values[0x11])
        self.assertEqual(reads, [5, 10, 0x11])
        return s

    def value(self, s):
        return [t for k, t, x, y, fg, ex in s.log if k == 'ascii' and y == SP.TEXT_Y and x > 100]

    def test_parent_reproduces_false_speed_and_patch_shows_unknown_in_both_languages(self):
        for lpa, status, wrong in ((0xFFFF, 0, '10/100'), (0x61, 0xFFFF, '10/1000'),
                                   (0xFFFF, 0xFFFF, '10/100/1000')):
            for lang in (1, 2):
                with self.subTest(lpa=lpa, status=status, lang=lang):
                    old = self.scene(lpa, status, lang, patched=False)
                    T.sc_speed_result(old, reg11=0x6000)
                    self.assertEqual(self.value(old), [wrong])
                    new = self.scene(lpa, status, lang)
                    T.sc_speed_result(new, reg11=0x6000)
                    self.assertEqual(self.value(new), ['Unknown'])
                    self.assertEqual([r for y, r in enumerate(old.fb) if y not in T.ROW],
                                     [r for y, r in enumerate(new.fb) if y not in T.ROW])

    def test_valid_abilities_and_no_autoneg_are_unchanged(self):
        for lpa, status, text in ((0, 0, 'No autoneg'), (0x61, 0, '10'),
                                  (0x1E1, 0, '10/100'), (0, 0x800, '1000'),
                                  (0x45E1, 0x3800, '10/100/1000')):
            with self.subTest(lpa=lpa, status=status):
                s = self.scene(lpa, status)
                T.sc_speed_result(s, reg11=0x6000)
                self.assertEqual(self.value(s), [text])

    def test_unknown_clears_previous_wide_value_and_recovers(self):
        s = self.scene(0x45E1, 0x3800)
        T.sc_speed_result(s, reg11=0x6000)
        s.w16(self.img.speed_partner['cells'], 0xFFFF, 0)
        s.log.clear()
        self.assertEqual(s.call(SP.RESULT), 0)
        s.drain()
        fresh = self.scene(0xFFFF, 0)
        T.sc_speed_result(fresh, reg11=0x6000)
        self.assertEqual(s.fb[SP.ROW_Y:SP.ROW_Y + 49], fresh.fb[SP.ROW_Y:SP.ROW_Y + 49])
        s.w16(self.img.speed_partner['cells'], 0x61, 0)
        s.log.clear()
        self.assertEqual(s.call(SP.RESULT), 0)
        s.drain()
        self.assertEqual(self.value(s), ['10'])

    def test_retry_and_error_do_not_show_unknown(self):
        for retries, rc in ((0, 1), (1, 0)):
            with self.subTest(retries=retries):
                s = self.scene(0xFFFF, 0xFFFF)
                T.sc_speed_idle(s, retry=1)
                s.w8(0x20000074, retries)
                s.w16(SP.STATUS_REG11, 0xC000)
                s.w8(T.FLAGS, 3)
                s.log.clear()
                self.assertEqual(s.call(SP.RESULT), rc)
                s.drain()
                self.assertEqual(self.value(s), [])

    def test_screen_rebuild_uses_checked_partner_value_in_both_languages(self):
        for lang in (1, 2):
            with self.subTest(lang=lang):
                s = self.scene(0xFFFF, 0, lang)
                s.w16(SP.STATUS_REG11, 0x6000)
                s.w8(T.FLAGS + 1, 3)
                s.w8(0x20000075, 1)
                s.set_state(9)
                s.post(0x1D)
                s.drain()
                self.assertEqual(self.value(s), ['Unknown'])

    def test_failed_read_after_valid_result_and_next_read_recover_without_stale_abilities(self):
        s = self.scene(0x45E1, 0x3800)
        T.sc_speed_result(s, reg11=0x6000)
        self.assertEqual(self.value(s), ['10/100/1000'])
        for lpa, status, expected in ((0, 0xFFFF, 'Unknown'), (0x61, 0, '10')):
            with self.subTest(lpa=lpa, status=status):
                values = {5: lpa, 10: status, 0x11: 0x6000}

                def mdio(uc):
                    s.ret(values[s.arg(0)])
                    return True

                s.at[T.MDIO_READ] = mdio
                s.w16(SP.STATUS_REG11, s.call(self.img.speed_partner['read']))
                s.log.clear()
                self.assertEqual(s.call(SP.RESULT), 0)
                s.drain()
                self.assertEqual(self.value(s), [expected])

    def test_only_one_call_version_strings_and_appended_code_change(self):
        old, new = bytes(self.parent.data), self.data
        site = self.img.speed_partner_validity['site']
        allowed = set(range(0x24, 0x2C)) | set(range(self.img.f(site), self.img.f(site) + 4))
        for version_site in (0x08011660, 0x08012E6C):
            offset = self.img.f(version_site)
            allowed |= set(range(offset, offset + 8))
            self.assertEqual(new[offset:offset + 8], SV.VERSION.encode().ljust(8, b'\0'))
        for i in range(self.img.f(self.parent.cave_ptr)):
            if old[i] != new[i]:
                self.assertIn(i, allowed)
        self.assertEqual(self.img.ram_allocs, self.parent.ram_allocs)

    def test_candidate_requires_its_historical_parent_before_applying_anything(self):
        with contextlib.redirect_stdout(io.StringIO()):
            img = Image(T.STOCK)
        with self.assertRaisesRegex(PatchError, 'requires: length-ref-reset'):
            apply_profile(img, PROFILES['pn2.17'], extra=(SV.PATCH_ID,))
        self.assertEqual(img.data, img.original)
        self.assertEqual(img.log, [])

    def test_unexpected_hook_is_rejected_without_allocating(self):
        with contextlib.redirect_stdout(io.StringIO()):
            img = Image(T.STOCK)
            apply_profile(img, PROFILES['pn2.23'])
        site = img.speed_partner['result'] + 12
        img.poke(site, img.read(site, 4).hex(), assemble(site, 'nop\n nop'))
        before, pointer = bytes(img.data), img.cave_ptr
        patch = next(p for p in patches.REGISTRY if p.pid == SV.PATCH_ID)
        with self.assertRaises(PatchError):
            patch(img)
        self.assertEqual(bytes(img.data), before)
        self.assertEqual(img.cave_ptr, pointer)


if __name__ == '__main__':
    unittest.main()
