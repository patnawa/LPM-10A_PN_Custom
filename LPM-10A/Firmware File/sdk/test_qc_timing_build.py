"""Independent PN2.25 image provenance, fixed patch boundaries and startup."""
import contextlib
import copy
import hashlib
import io
import struct
import unittest

from unicorn.arm_const import UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_SP

from lpm10a import symbols as S
from lpm10a.image import PatchError
import length_integrity
import qc_classic
import qc_timing as candidate
from thai.engine import MAGIC, MAIN, Scene


PARENT_HASH = 'b3716f6538f8980c075fb85e925cb2ba1d86e46440174d450615fa98253131e7'
# Independently audited PN2.24 addresses. Deliberately do not derive this
# allowlist from the candidate's metadata, production constants, or Image.log.
HOOKS = {
    0x08018B84: 4,  # Shared native Init/live counter measurement entry.
    0x080692CA: 4,  # QC reset's baseline-validity predicate.
    0x08069AE8: 4,  # Successful five-sample Init's settings-save call.
    0x080195BC: 4,  # Existing factory Length Zero default hook.
    0x08011660: 8,  # About/version text.
    0x08012E6C: 8,  # Debug/version text.
}


class QCTimingBuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with contextlib.redirect_stdout(io.StringIO()):
            cls.parent = length_integrity.build_candidate()
            cls.img = candidate.build_candidate()

    def test_exact_parent_and_fixed_independent_existing_byte_allowlist(self):
        old, new = bytes(self.parent.data), bytes(self.img.data)
        self.assertEqual(hashlib.sha256(old).hexdigest(), PARENT_HASH)
        self.assertEqual(candidate.PARENT_SHA256, PARENT_HASH)
        self.assertEqual(self.parent.cave_ptr, 0x0806A2E4)
        self.assertEqual(self.img.qc_timing['parent_end'], self.parent.cave_ptr)
        self.assertEqual(self.img.qc_timing['parent_ram'], tuple(self.parent.ram_allocs))
        allowed = set(range(0x24, 0x2C))  # Only container payload length/end.
        for address, size in HOOKS.items():
            offset = self.parent.f(address)
            allowed.update(range(offset, offset+size))
            self.assertNotEqual(old[offset:offset+size], new[offset:offset+size],
                                f'required QC/version hook missing at {address:#x}')
        boundary = self.parent.f(self.parent.cave_ptr)
        unexpected = [offset for offset in range(boundary)
                      if old[offset] != new[offset] and offset not in allowed]
        self.assertEqual(unexpected, [], 'unexpected prior-image changes: '+
                         ', '.join(hex(address) for address in unexpected[:12]))
        self.assertFalse(any(old[boundary:]), 'new code must occupy previously unused padding')

    def test_container_identity_flash_bounds_padding_version_and_determinism(self):
        data = bytes(self.img.data)
        offset, length, end = struct.unpack_from('<III', data, 0x20)
        self.assertEqual(data[:0x20], bytes(self.parent.data[:0x20]))
        self.assertEqual(data[0x2C:0x1000], bytes(self.parent.data[0x2C:0x1000]))
        self.assertEqual(offset, 0x1000)
        self.assertEqual(end, offset+length-1)
        self.assertEqual(S.APP_BASE+length, self.img.cave_ptr)
        self.assertGreater(self.img.cave_ptr, self.parent.cave_ptr)
        self.assertLessEqual(self.img.cave_ptr, 0x0806B000, 'QC update must fit existing padding')
        self.assertLess(self.img.cave_ptr, S.CONSTS['BOOTFLAG_PAGE'])
        self.assertEqual(len(data), len(self.parent.data))
        self.assertEqual(len(data), 401408)
        self.assertEqual(len(data) % 0x1000, 0)
        self.assertLessEqual(end+1, len(data))
        self.assertFalse(any(data[end+1:]))
        self.assertEqual(candidate.VERSION, 'PN2.25')
        for address in (0x08011660, 0x08012E6C):
            self.assertEqual(self.img.read(address, 8), b'PN2.25\0\0')
        with contextlib.redirect_stdout(io.StringIO()):
            again = candidate.build_candidate()
        self.assertEqual(bytes(again.data), data)
        self.assertEqual(again.cave_ptr, self.img.cave_ptr)
        self.assertEqual(again.ram_allocs, self.img.ram_allocs)

    def test_no_new_ram_and_inherited_arena_allocations_remain_bounded(self):
        self.assertEqual(self.img.ram_allocs, self.parent.ram_allocs)
        self.assertEqual(self.img._ram_ptr, self.parent._ram_ptr)
        self.assertEqual(self.img._ram_ptr, 0x2000F364)
        previous_end = S.RAM_SAFE_ARENA
        for address, size in self.img.ram_allocs:
            self.assertEqual(address % 4, 0)
            self.assertGreater(size, 0)
            self.assertGreaterEqual(address, previous_end)
            self.assertLessEqual(address+size, S.RAM_SAFE_ARENA_END)
            previous_end = address+size
        baseline = self.img.qc_timing['baseline']
        self.assertEqual(baseline['ram_bytes'], 0)
        self.assertEqual((baseline['marker'], baseline['marker_size']), (0x20000D3E, 2))
        self.assertEqual(self.img.qc['state'], self.parent.qc['state'])
        self.assertEqual(self.img.qc_classic['ui']['cache'], self.parent.qc_classic['ui']['cache'])
        self.assertEqual(self.img.qc_idle_filter['state'], self.parent.qc_idle_filter['state'])
        self.assertEqual(self.img.length_lifecycle['state'], self.parent.length_lifecycle['state'])

    def test_wrong_parent_tampered_parent_and_double_apply_fail_without_mutation(self):
        for route in ('wrong-version', 'changed-parent', 'double-apply'):
            with self.subTest(route=route):
                if route == 'wrong-version':
                    with contextlib.redirect_stdout(io.StringIO()):
                        img = qc_classic.build_candidate()
                else:
                    img = copy.deepcopy(self.img if route == 'double-apply' else self.parent)
                if route == 'changed-parent':
                    img.data[img.f(0x08018B84)] ^= 1
                before = (bytes(img.data), img.cave_ptr, img.cave_end, img.payload_len,
                          img._ram_ptr, tuple(img.ram_allocs), tuple(img.log))
                with self.assertRaisesRegex(PatchError, 'exact finalized PN2.24'):
                    candidate.apply(img)
                self.assertEqual((bytes(img.data), img.cave_ptr, img.cave_end, img.payload_len,
                                  img._ram_ptr, tuple(img.ram_allocs), tuple(img.log)), before)

    def test_actual_main_retains_inherited_initialization_and_arena_canary(self):
        self.assertEqual(self.img.read(MAIN, 4), self.parent.read(MAIN, 4))
        arena_size = S.RAM_SAFE_ARENA_END-S.RAM_SAFE_ARENA
        poison = bytes([0xA5])*arena_size
        canary = bytes(range(0xC0, 0xD0))
        tail = self.parent._ram_ptr
        snapshots = []
        for img in (self.parent, self.img):
            s = Scene(image=bytes(img.data))
            s.uc.mem_write(S.RAM_SAFE_ARENA, poison)
            s.uc.mem_write(tail, canary)
            # Startup should preserve an already-persisted migration marker.
            s.w16(0x20000D3E, 0xB33F)
            stack = 0x2000DFC0
            s.uc.reg_write(UC_ARM_REG_SP, stack)
            s.uc.reg_write(UC_ARM_REG_LR, MAGIC | 1)
            s.uc.emu_start(MAIN | 1, MAIN+4, count=100_000)
            self.assertEqual(s.uc.reg_read(UC_ARM_REG_PC), MAIN+4)
            self.assertEqual(s.uc.reg_read(UC_ARM_REG_SP), stack)
            regions = ((img.qc['state'], 64), (img.qc_classic['ui']['cache'], 16),
                       (img.qc_idle_filter['state'], 20), (img.length_lifecycle['state'], 8))
            for address, size in regions:
                self.assertEqual(bytes(s.uc.mem_read(address, size)), bytes(size),
                                 f'poisoned inherited startup state survived at {address:#x}')
            self.assertEqual(bytes(s.uc.mem_read(tail, len(canary))), canary)
            self.assertEqual(bytes(s.uc.mem_read(tail+len(canary),
                                                S.RAM_SAFE_ARENA_END-tail-len(canary))),
                             bytes([0xA5])*(S.RAM_SAFE_ARENA_END-tail-len(canary)))
            self.assertEqual(bytes(s.uc.mem_read(0x20000D3E, 2)), b'\x3f\xb3')
            snapshots.append(bytes(s.uc.mem_read(S.RAM_SAFE_ARENA, arena_size)))
        self.assertEqual(snapshots[0], snapshots[1], 'QC timing changed inherited arena initialization')


if __name__ == '__main__':
    unittest.main()
