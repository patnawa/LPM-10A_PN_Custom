"""Integrated PN2.24 provenance, patch ownership, allocation and startup."""
import contextlib
import copy
import hashlib
import io
import struct
import unittest

from unicorn.arm_const import UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_SP

from lpm10a import symbols as S
from lpm10a.image import PatchError
from length_reference import find_bl
import length_integrity as candidate
import length_lifecycle as lifecycle
import length_message_guard as messages
import length_progress as progress
import length_ref_anytime as reference
import qc_classic
import qc_continuity
import qc_idle_filter
from thai.engine import MAGIC, MAIN, Scene


class LengthIntegrityBuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with contextlib.redirect_stdout(io.StringIO()):
            cls.parent = qc_classic.build_candidate()
            cls.img = candidate.build_candidate()

    def test_exact_parent_and_explicitly_authorized_existing_patch_sites(self):
        old, new = bytes(self.parent.data), bytes(self.img.data)
        self.assertEqual(hashlib.sha256(old).hexdigest(), candidate.PARENT_SHA256)
        self.assertEqual(candidate.PARENT_SHA256,
                         'cd94672633420a44e9bf9232de87adcc794cc57068035a260ffb6e4ffa35e8b4')
        self.assertEqual(self.img.length_integrity['parent_end'], self.parent.cave_ptr)
        self.assertEqual(self.img.length_integrity['parent_ram'], tuple(self.parent.ram_allocs))

        # This is an audited allowlist of specific contracts, not Image.log or
        # a blanket allowance for whatever a production patch claims to edit.
        sites = {
            reference.RESULT_SITE: 4,
            self.parent.length_progress['hook']+2: 4,
            qc_idle_filter.CLASSIFY_SITE: 4,
            lifecycle.STATE_SITE: 4,
            lifecycle.ENTRY_SITE: 4,
            lifecycle.SEQUENCE: 4,
            lifecycle.START_SITE: 4,
            lifecycle.NET_DISPATCH: 4,
            lifecycle.POLL_SITE: 4,
            lifecycle.ACCEPT: 4,
            lifecycle.TIMEOUT_FLAG: 6,
            0x08011A66: 6,  # Move the busy announcement to atomic sequence entry.
            0x080121EA: 4,  # Generation-aware cancellation epilogue.
            lifecycle.GUI_SITE: 4,
            messages.CLEAR_SITE: 4,
            MAIN: 4,
            0x08011660: 8,
            0x08012E6C: 8,
        }
        for site in messages.TEXT_SITES:
            sites[site] = 4
        counter_text = find_bl(old, self.parent.length_progress['hook'], progress.TEXT_BOX)
        sites[counter_text] = 4
        allowed = set(range(0x24, 0x2C))  # Container payload length/end only.
        for address, size in sites.items():
            offset = self.img.f(address)
            allowed.update(range(offset, offset+size))
            self.assertNotEqual(old[offset:offset+size], new[offset:offset+size],
                                f'expected hook was not installed at {address:#x}')
        boundary = self.parent.f(self.parent.cave_ptr)
        unexpected = [offset for offset in range(boundary)
                      if old[offset] != new[offset] and offset not in allowed]
        self.assertEqual(unexpected, [],
                         'unexpected pre-parent mutations: '+', '.join(hex(o) for o in unexpected[:12]))

    def test_container_identity_version_padding_and_deterministic_build(self):
        data = bytes(self.img.data)
        offset, length, end = struct.unpack_from('<III', data, 0x20)
        self.assertEqual(data[:0x20], self.parent.data[:0x20])
        self.assertEqual(offset, S.FILE_PAYLOAD_OFF)
        self.assertEqual(end, offset+length-1)
        self.assertEqual(S.APP_BASE+length, self.img.cave_ptr)
        self.assertLess(S.APP_BASE+length, S.CONSTS['BOOTFLAG_PAGE'])
        self.assertLessEqual(end+1, len(data))
        self.assertEqual(len(data) % 0x1000, 0)
        self.assertFalse(any(data[end+1:]))
        self.assertEqual(candidate.VERSION, 'PN2.24')
        for address in (0x08011660, 0x08012E6C):
            self.assertEqual(self.img.read(address, 8), b'PN2.24\0\0')
        with contextlib.redirect_stdout(io.StringIO()):
            again = candidate.build_candidate()
        self.assertEqual(bytes(again.data), data)
        self.assertEqual(again.ram_allocs, self.img.ram_allocs)

    def test_ram_is_bounded_nonoverlapping_and_only_declared_new_state_is_allocated(self):
        filtering, life = self.img.qc_idle_filter, self.img.length_lifecycle
        self.assertEqual(qc_idle_filter.STATE_SIZE, 20)
        self.assertEqual(life['ram_bytes'], 8)
        expected = self.parent.ram_allocs+[(filtering['state'], 20), (life['state'], 8)]
        self.assertEqual(self.img.ram_allocs, expected)
        previous_end = S.RAM_SAFE_ARENA
        for address, size in self.img.ram_allocs:
            self.assertEqual(address % 4, 0)
            self.assertGreater(size, 0)
            self.assertGreaterEqual(address, previous_end)
            self.assertLessEqual(address+size, S.RAM_SAFE_ARENA_END)
            previous_end = address+size
        self.assertEqual(self.img.length_reference_guard['ram_bytes'], 0)
        self.assertEqual(self.img.qc['state'], self.parent.qc['state'])
        self.assertEqual(self.img.qc_classic['ui']['cache'], self.parent.qc_classic['ui']['cache'])

    def test_wrong_parent_and_double_application_fail_before_mutation(self):
        for route in ('wrong-version', 'changed-parent', 'double-apply'):
            with self.subTest(route=route):
                if route == 'wrong-version':
                    with contextlib.redirect_stdout(io.StringIO()):
                        img = qc_continuity.build_candidate()
                else:
                    img = copy.deepcopy(self.img if route == 'double-apply' else self.parent)
                if route == 'changed-parent':
                    img.data[img.f(messages.CLEAR_SITE)] ^= 1
                before = bytes(img.data), img.cave_ptr, tuple(img.ram_allocs), tuple(img.log)
                with self.assertRaisesRegex(PatchError, 'exact finalized PN2.23R'):
                    candidate.apply(img)
                self.assertEqual((bytes(img.data), img.cave_ptr, tuple(img.ram_allocs), tuple(img.log)), before)

    def test_actual_main_initializes_new_length_qc_and_inherited_display_state(self):
        s = Scene(image=bytes(self.img.data))
        q = self.img.qc['state']
        ui = self.img.qc_classic['ui']
        filtering, life = self.img.qc_idle_filter, self.img.length_lifecycle
        regions = ((q, qc_continuity.STATE_SIZE),
                   (ui['cache'], ui['cache_size']),
                   (filtering['state'], filtering['state_size']),
                   (life['state'], life['ram_bytes']))
        before = bytes(s.uc.mem_read(S.RAM_SAFE_ARENA, S.RAM_SAFE_ARENA_END-S.RAM_SAFE_ARENA))
        touched = set()
        for index, (address, size) in enumerate(regions):
            s.uc.mem_write(address, bytes([0xA5+index])*size)
            touched.update(range(address, address+size))
        tail = max(address+size for address, size in self.img.ram_allocs)
        canary = bytes(range(0xC0, 0xD0))
        self.assertLessEqual(tail+len(canary), S.RAM_SAFE_ARENA_END)
        s.uc.mem_write(tail, canary)
        touched.update(range(tail, tail+len(canary)))
        stack = 0x2000DFC0
        s.uc.reg_write(UC_ARM_REG_SP, stack)
        s.uc.reg_write(UC_ARM_REG_LR, MAGIC | 1)
        s.uc.emu_start(MAIN | 1, MAIN+4, count=100_000)
        self.assertEqual(s.uc.reg_read(UC_ARM_REG_PC), MAIN+4)
        self.assertEqual(s.uc.reg_read(UC_ARM_REG_SP), stack)
        for address, size in regions:
            self.assertEqual(bytes(s.uc.mem_read(address, size)), bytes(size),
                             f'poisoned startup state survived at {address:#x}')
        self.assertEqual(bytes(s.uc.mem_read(tail, len(canary))), canary)
        after = bytes(s.uc.mem_read(S.RAM_SAFE_ARENA, len(before)))
        unexpected = [S.RAM_SAFE_ARENA+i for i, (left, right) in enumerate(zip(before, after))
                      if left != right and S.RAM_SAFE_ARENA+i not in touched]
        self.assertEqual(unexpected, [], 'startup changed unrelated arena bytes')


if __name__ == '__main__':
    unittest.main()
