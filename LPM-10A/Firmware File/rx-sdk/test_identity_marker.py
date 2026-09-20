"""One-byte identity marker guards and actual ARM GPIO/startup behavior.

Peripheral model: plain registers with oscillator/PLL/clock ready flags, GPIO
inputs high, and N32L40x PBSC/PBC writes reflected into POD. Delays, ADC bring-up,
UID/license validation, boot-info/version checks are stubbed. No interrupt
arrivals are modeled. The reset, scatter-load, GPIO initialization, application
startup, lamp-key handler, GPIO helpers and power-off routine execute real ARM.
These tests establish code behavior, not physical lamp operation or USB uptake.
"""
import argparse
import contextlib
import hashlib
import io
import json
from pathlib import Path
import struct
import tempfile
import time
import unittest
from unittest import mock

from unicorn import (Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS,
                     UC_HOOK_CODE, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE, UC_MEM_WRITE)
from unicorn.arm_const import (UC_ARM_REG_PC, UC_ARM_REG_LR, UC_ARM_REG_R0,
                               UC_ARM_REG_SP, UC_ARM_REG_PRIMASK)

import identity_marker as marker
from lpm10rx import symbols as symbols


GPIOA, GPIOB = 0x40010800, 0x40010C00
LAMP, LATCH = 0x400, 0x100
MAIN_LOOP, RETURN = 0x0800B8F2, 0x0800D000
SOURCE_URL = ('https://www.nsing.com.sg/uploads/MCUProducts/N32L40x/'
              'Chip_Documentation/User_Manual/EN_UM_N32L40x_Series_User_Manual.pdf')


class MarkerCPU:
    """Boot model independent of the older, reversed GPIO function labels."""

    def __init__(self, image):
        self.uc = cpu = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
        for base, size in ((0x08000000, 0x20000), (0x1FFFF000, 0x1000),
                           (0x20000000, 0x10000), (0x40000000, 0x30000),
                           (0x42000000, 0x2000000), (0xE000E000, 0x1000)):
            cpu.mem_map(base, size)
        cpu.mem_write(marker.APP_BASE, image)
        cpu.mem_write(0x08006700, b'\xff' * 4 + b'\x11\x22\x33\x44' + b'\0' * 16)
        self.write32(0x0800676C, 0x2E33565F)
        cpu.mem_write(0x1FFFF7F0, bytes(range(12)))
        self.outputs = {}
        self.lamp_writes = []
        self.skip = {symbols.FUNCS_BY_NAME[name] for name in (
            'delay_ms', 'delay_us', 'uid_license_check', 'bootinfo_version_tag_missing',
            'version_page_check', 'adc1_init')}
        self.stop = MAIN_LOOP
        self.instructions = 0
        cpu.hook_add(UC_HOOK_MEM_READ, self.on_read, begin=0x40000000, end=0x40030000)
        cpu.hook_add(UC_HOOK_MEM_WRITE, self.on_write, begin=0x40000000, end=0x40030000)
        cpu.hook_add(UC_HOOK_MEM_READ | UC_HOOK_MEM_WRITE, self.on_bitband,
                     begin=0x42000000, end=0x44000000)
        cpu.hook_add(UC_HOOK_CODE, self.on_code)
        sp, reset = struct.unpack_from('<II', image)
        cpu.reg_write(UC_ARM_REG_SP, sp)
        cpu.emu_start(reset, 0, count=100000)
        if cpu.reg_read(UC_ARM_REG_PC) != MAIN_LOOP:
            raise AssertionError('Boot failed to reach the normal main loop within its instruction bound')

    def read32(self, address):
        return int.from_bytes(self.uc.mem_read(address, 4), 'little')

    def write32(self, address, value):
        self.uc.mem_write(address, struct.pack('<I', value))

    def on_read(self, cpu, access, address, size, value, user):
        aligned = address & ~3
        current = self.read32(aligned)
        if aligned == 0x40021000:
            current |= (1 << 1) | (1 << 17) | (1 << 25)
        elif aligned == 0x40021004:
            current = (current & ~0xC) | ((current & 3) << 2)
        elif aligned == 0x40021024:
            current |= 1 << 3
        elif aligned == 0x40007010:
            current |= 2
        elif aligned == 0x4002200C:
            current &= ~1
        elif aligned in (0x40010810, 0x40010C10, 0x40011010, 0x40011410):
            current = 0xFFFF
        else:
            return
        self.write32(aligned, current)

    def on_write(self, cpu, access, address, size, value, user):
        base = address & ~0x3FF
        offset = address - base
        if base not in (GPIOA, GPIOB, 0x40011000, 0x40011400) or offset not in (0x18, 0x28):
            return
        previous = self.outputs.get(base, 0)
        # N32L40x: PBSC at +0x18 sets low-half bits and clears high-half bits;
        # PBC at +0x28 clears bits. The POD output register is at +0x14.
        after = ((previous & ~(value >> 16)) | (value & 0xFFFF)
                 if offset == 0x18 else previous & ~(value & 0xFFFF))
        self.outputs[base] = after
        self.write32(base + 0x14, after)
        if base == GPIOA and ((value | (value >> 16)) & LAMP):
            self.lamp_writes.append({'pc': hex(cpu.reg_read(UC_ARM_REG_PC)),
                                     'register': hex(address), 'PA10_high': bool(after & LAMP)})

    def on_bitband(self, cpu, access, address, size, value, user):
        offset = address - 0x42000000
        register, bit = 0x40000000 + offset // 32, (offset % 32) // 4
        aligned = register & ~3
        current = self.read32(aligned)
        if access == UC_MEM_WRITE:
            self.write32(aligned, (current | (1 << bit)) if value & 1 else current & ~(1 << bit))
        else:
            self.write32(address & ~3, (current >> bit) & 1)

    def on_code(self, cpu, address, size, user):
        self.instructions += 1
        if address in self.skip:
            cpu.reg_write(UC_ARM_REG_R0, 0)
            cpu.reg_write(UC_ARM_REG_PC, cpu.reg_read(UC_ARM_REG_LR))
        elif address == self.stop:
            cpu.emu_stop()

    def call(self, address):
        self.stop = RETURN
        self.uc.reg_write(UC_ARM_REG_SP, 0x20001600)
        self.uc.reg_write(UC_ARM_REG_LR, RETURN | 1)
        self.uc.emu_start(address | 1, RETURN, count=4000)
        if self.uc.reg_read(UC_ARM_REG_PC) != RETURN:
            raise AssertionError('Routine exceeded its instruction bound')
        if self.uc.reg_read(UC_ARM_REG_SP) != 0x20001600:
            raise AssertionError('Routine did not restore its stack')

    def lamp_key_release(self):
        self.uc.mem_write(0x20000112, struct.pack('<H', 6))
        self.call(0x080082B8)


class IdentityMarkerTests(unittest.TestCase):
    evidence = {}

    @classmethod
    def setUpClass(cls):
        cls.parent = marker.DEFAULT_PARENT.read_bytes()
        cls.candidate = marker.marker_bytes(cls.parent)

    def test_exact_one_byte_and_parent_unchanged(self):
        mutable = bytearray(self.parent)
        result = marker.marker_bytes(mutable)
        self.assertEqual(bytes(mutable), self.parent)
        self.assertEqual(len(result), marker.IMAGE_SIZE)
        changed = [marker.APP_BASE + i for i, pair in enumerate(zip(self.parent, result))
                   if pair[0] != pair[1]]
        self.assertEqual(changed, [marker.CHANGED_ADDRESS])
        self.assertEqual(result, self.candidate)
        if marker.DEFAULT_OUTPUT.exists():
            self.assertEqual(marker.DEFAULT_OUTPUT.read_bytes(), self.candidate)
        self.evidence['changed_addresses'] = [hex(value) for value in changed]

    def test_wrong_parent_and_site_guards_leave_input_unchanged(self):
        for offset in (0, marker.SITE-marker.APP_BASE, len(self.parent)-1):
            damaged = bytearray(self.parent)
            damaged[offset] ^= 1
            before = bytes(damaged)
            with self.assertRaises(marker.IdentityMarkerError):
                marker.marker_bytes(damaged)
            self.assertEqual(bytes(damaged), before)
        damaged = bytearray(self.parent)
        damaged[marker.SITE-marker.APP_BASE] ^= 1
        with mock.patch.object(marker, 'PARENT_SHA256', hashlib.sha256(damaged).hexdigest()):
            with self.assertRaisesRegex(marker.IdentityMarkerError, 'call-site'):
                marker.marker_bytes(damaged)

    def test_cli_dry_run_and_rejection_do_not_mutate_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            parent, output = root/'parent.bin', root/'output.bin'
            parent.write_bytes(self.parent)
            with mock.patch.object(marker, 'DEFAULT_OUTPUT', output):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(marker.main(['--parent', str(parent)]), 0)
                self.assertFalse(output.exists())
                self.assertEqual(parent.read_bytes(), self.parent)
                parent.write_bytes(b'wrong input')
                output.write_bytes(b'keep existing output')
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                    marker.main(['--parent', str(parent), '--write'])
                self.assertEqual(error.exception.code, 1)
                self.assertEqual(parent.read_bytes(), b'wrong input')
                self.assertEqual(output.read_bytes(), b'keep existing output')

    def test_cli_explicit_write_is_idempotent_and_refuses_other_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            parent, output = root/'parent.bin', root/'output.bin'
            parent.write_bytes(self.parent)
            with mock.patch.object(marker, 'DEFAULT_OUTPUT', output):
                for _ in range(2):
                    with contextlib.redirect_stdout(io.StringIO()):
                        self.assertEqual(marker.main(['--parent', str(parent), '--write']), 0)
                    self.assertEqual(output.read_bytes(), self.candidate)
                    self.assertEqual(parent.read_bytes(), self.parent)
                output.write_bytes(b'keep unexpected output')
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    marker.main(['--parent', str(parent), '--write'])
                self.assertEqual(output.read_bytes(), b'keep unexpected output')

    def test_actual_boot_persists_marker_to_main_with_other_outputs_unchanged(self):
        old, new = MarkerCPU(self.parent), MarkerCPU(self.candidate)
        self.assertFalse(old.outputs[GPIOA] & LAMP)
        self.assertTrue(new.outputs[GPIOA] & LAMP)
        self.assertEqual(old.outputs[GPIOA] ^ new.outputs[GPIOA], LAMP)
        self.assertEqual({key: value for key, value in old.outputs.items() if key != GPIOA},
                         {key: value for key, value in new.outputs.items() if key != GPIOA})
        self.assertEqual(bytes(old.uc.mem_read(0x20000000, 0x118)),
                         bytes(new.uc.mem_read(0x20000000, 0x118)))
        self.assertEqual(new.uc.reg_read(UC_ARM_REG_PRIMASK), 0)
        self.evidence['boot'] = {
            'parent_PA10_high': False, 'candidate_PA10_high': True,
            'other_gpio_outputs_identical': True, 'app_globals_identical': True,
            'parent_instructions': old.instructions, 'candidate_instructions': new.instructions,
            'candidate_PA10_writes': new.lamp_writes,
        }

    def test_actual_lamp_key_toggles_and_shutdown_restores_original_off_state(self):
        rows = []
        for name, image, initial in (('parent', self.parent, False), ('marker', self.candidate, True)):
            cpu = MarkerCPU(image)
            cpu.lamp_key_release()
            self.assertEqual(bool(cpu.outputs[GPIOA] & LAMP), not initial)
            self.assertEqual(bytes(cpu.uc.mem_read(0x2000010C, 1)), b'\x64')
            cpu.call(0x08007570)
            self.assertFalse(cpu.outputs[GPIOA] & LAMP)
            self.assertFalse(cpu.outputs[GPIOB] & LATCH)
            rows.append({'image': name, 'startup_PA10_high': initial,
                         'after_lamp_key_PA10_high': not initial,
                         'confirmation_ticks': 100, 'shutdown_PA10_high': False,
                         'shutdown_PB8_high': False})
        self.evidence['key_and_shutdown'] = rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', type=Path, help='write local verification evidence after running tests')
    args = parser.parse_args()
    started = time.perf_counter()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(IdentityMarkerTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    elapsed = time.perf_counter() - started
    if args.json:
        report = {
            'purpose': 'temporary identity diagnostic; no claim of fixing the Digital tail',
            'tests': result.testsRun, 'passed': result.wasSuccessful(), 'seconds': round(elapsed, 6),
            'parent_sha256': hashlib.sha256(marker.DEFAULT_PARENT.read_bytes()).hexdigest(),
            'candidate_sha256': hashlib.sha256(IdentityMarkerTests.candidate).hexdigest(),
            'source_sha256': {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                              for path in (Path(marker.__file__), Path(__file__))},
            'gpio_register_source': SOURCE_URL,
            'model_limits': __doc__,
            'results': IdentityMarkerTests.evidence,
            'hardware_status': 'Not tested on the probe; update uptake unresolved; local artifact only',
        }
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
