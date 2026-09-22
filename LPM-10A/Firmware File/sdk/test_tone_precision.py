"""Actual Thumb checks for specialized PN2.27 carrier pin transitions.

Peripheral registers, RTOS ticks and interrupt arrival are modeled. Instruction
counts are not MCU cycles, cable amplitude, range or measured edge timing.
"""
import contextlib
import copy
import hashlib
import io
import random
import unittest

from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm_const import (UC_ARM_REG_BASEPRI, UC_ARM_REG_PRIMASK,
                               UC_ARM_REG_SP)

from lpm10a.image import PatchError
import qc_display
import test_scan_recovery as recovery
from test_scan_hardware import (CARRIER_INIT, CARRIER_OFF, CARRIER_ON,
                               PA_CRH, PB_CRH, TIM1, TIM1_EXPECTED)
from verify_scan import SCAN, STACK


PARENT_HASH = 'c77579f018bb820532b3c5974ae63fbf04c4e60359188f7e39a8a8f9a1533df8'
PINS = ((PB_CRH, 20), (PA_CRH, 0))
TICK = 0x200001A0


class CarrierMachine(recovery.RecoveryMachine):
    """Run the vendor OFF parity routine's real RTOS tick reader too."""
    def __init__(self, data, mode=1):
        super().__init__(data, mode)
        self.mmio = []
        self.minimum_sp = STACK
        self.uc.hook_add(UC_HOOK_MEM_WRITE, self.observe_write)
        self.uc.hook_add(UC_HOOK_CODE, self.observe_stack)

    def hook(self, uc, address, size, user):
        if address == 0x0801C5B0:
            self.instructions += 1
            self.calls[address] += 1
        else:
            super().hook(uc, address, size, user)

    def observe_write(self, uc, access, address, size, value, user):
        if 0x40000000 <= address < 0x40030000:
            self.mmio.append((address, size, value, self.instructions))

    def observe_stack(self, uc, address, size, user):
        self.minimum_sp = min(self.minimum_sp, uc.reg_read(UC_ARM_REG_SP))

    def measure(self, address):
        self.mmio.clear()
        self.minimum_sp = STACK
        before = self.instructions
        self.call(address)
        pin_writes = [row for row in self.mmio if row[0] in (PA_CRH, PB_CRH)]
        return dict(instructions=self.instructions-before,
                    stack=STACK-self.minimum_sp,
                    skew=pin_writes[1][3]-pin_writes[0][3],
                    writes=[row[:3] for row in self.mmio])


class TonePrecision(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tone_precision
        with contextlib.redirect_stdout(io.StringIO()):
            cls.parent = qc_display.build_candidate()
            cls.img = tone_precision.build_candidate()
        cls.previous, cls.data = bytes(cls.parent.data), bytes(cls.img.data)

    def test_transition_instruction_work_is_bounded(self):
        """Red on PN2.26: generic GPIO calls alone exceed this whole-path budget."""
        measured = []
        for entry in (CARRIER_ON, CARRIER_OFF):
            for tick in (0, 1):
                m = CarrierMachine(self.data)
                m.w32(TICK, tick)
                row = m.measure(entry)
                self.assertLess(row['instructions'], 80, (hex(entry), tick, row))
                self.assertLess(row['skew'], 12, (hex(entry), tick, row))
                measured.append((hex(entry), tick, row['instructions'], row['skew']))
        print('Specialized carrier (entry,tick,instructions,pin-write separation):', measured)

    def test_parent_negative_control_and_candidate_instruction_stack_costs(self):
        measured = []
        for entry in (CARRIER_ON, CARRIER_OFF):
            for tick in (0, 1, 0x12345678, 0xFFFFFFFF):
                rows = []
                for data in (self.previous, self.data):
                    m = CarrierMachine(data)
                    m.w32(TICK, tick)
                    rows.append(m.measure(entry))
                old, new = rows
                self.assertGreater(old['instructions'], 250)
                self.assertEqual(old['skew'], 126)
                self.assertEqual(old['writes'], new['writes'])
                self.assertLess(new['instructions'], old['instructions'])
                self.assertLessEqual(new['stack'], old['stack'])
                measured.append((hex(entry), tick, old['instructions'], new['instructions'],
                                 old['stack'], new['stack']))
        print('Carrier cost (entry,tick,parent,candidate,parent stack,candidate stack):', measured)

    def test_seeded_gpio_timer_drive_and_slew_are_exactly_equivalent(self):
        rng = random.Random(0x227)
        regions = ((0x40010800, 0x28), (0x40010C00, 0x28),
                   (0x40010000, 0x20), (TIM1, 0x48), (0x40000000, 0x48))
        cases = 0
        for seed in range(16):
            memory = [(a, bytes(rng.randrange(256) for _ in range(n))) for a,n in regions]
            for entry in (CARRIER_ON, CARRIER_OFF):
                for tick in (0, 1, 0x12345678, 0xFFFFFFFF):
                    for mask in (0, 1):
                        with self.subTest(seed=seed, entry=hex(entry), tick=tick, mask=mask):
                            machines = [CarrierMachine(data) for data in (self.previous, self.data)]
                            results = []
                            for m in machines:
                                for a,b in memory:
                                    m.uc.mem_write(a, b)
                                m.w32(TICK, tick)
                                m.uc.reg_write(UC_ARM_REG_PRIMASK, mask)
                                m.uc.reg_write(UC_ARM_REG_BASEPRI, 0xBF if seed&1 else 0)
                                before = {a: m.r32(a) for a,_ in PINS}
                                results.append(m.measure(entry))
                                self.assertEqual(m.uc.reg_read(UC_ARM_REG_PRIMASK), mask)
                                self.assertEqual(m.uc.reg_read(UC_ARM_REG_BASEPRI), 0xBF if seed&1 else 0)
                                for address, shift in PINS:
                                    value = (0xB if entry == CARRIER_ON else 3) << shift
                                    self.assertEqual(m.r32(address), (before[address] & ~(15 << shift)) | value)
                            self.assertEqual(results[0]['writes'], results[1]['writes'])
                            for address,size in regions:
                                self.assertEqual(bytes(machines[0].uc.mem_read(address, size)),
                                                 bytes(machines[1].uc.mem_read(address, size)))
                            self.assertEqual([r[0] for r in results[1]['writes'][:2]], [PB_CRH, PA_CRH])
                            if entry == CARRIER_OFF:
                                parity = ((tick ^ tick>>8 ^ tick>>16) & 7).bit_count() & 1
                                offset = 0x10 if parity else 0x14
                                self.assertEqual(results[1]['writes'][2:],
                                                 [(0x40010C00+offset,4,0x2000),
                                                  (0x40010800+offset,4,0x100)])
                            cases += 1
        print('Seeded carrier equivalence cases:', cases)

    def test_actual_carrier_initialization_has_identical_ordered_peripheral_writes(self):
        rows = []
        for data in (self.previous, self.data):
            m = CarrierMachine(data)
            m.w32(PA_CRH, 0x87654321)
            m.w32(PB_CRH, 0x12345678)
            for address in (0x40010820,0x40010824,0x40010C20,0x40010C24):
                m.w32(address, 0x96A5)
            m.call(CARRIER_INIT)
            self.assertEqual(m.timer_configuration(), TIM1_EXPECTED)
            self.assertEqual(m.pin_modes(), (3,3))
            for address in (0x40010820,0x40010824,0x40010C20,0x40010C24):
                self.assertEqual(m.r32(address), 0x96A5)
            rows.append([row[:3] for row in m.mmio])
        self.assertEqual(*rows)

    def test_all_six_direct_caller_paths_preserve_control_and_peripheral_effects(self):
        # The pinned image has exactly five BLs to OFF and one BL to ON.
        # Call the real enclosing functions, including both gate branches;
        # no caller consumes carrier return flags or a return value.
        cases = ((0x08014344,0,0,0),  # disabled Analog -> OFF at 1434C
                 (0x0801456C,0,1,1),  # Back -> OFF at 1457A
                 (0x0801464C,1,0,1),  # disabled gate -> OFF at 14656
                 (0x0801464C,1,1,0),  # enabled gate -> ON at 1466A
                 (0x0801464C,0,1,1),  # enabled gate -> OFF at 14670
                 (CARRIER_INIT,0,1,0))
        for entry,argument,enabled,cache in cases:
            for mask in (0,1):
                with self.subTest(entry=hex(entry), enabled=enabled, mask=mask):
                    rows = []
                    for data in (self.previous,self.data):
                        m = CarrierMachine(data, mode=2)
                        m.w8(SCAN,enabled)
                        m.w8(SCAN+12,cache)
                        m.w32(PA_CRH,0xA7654321)
                        m.w32(PB_CRH,0x12345678)
                        m.w32(TICK,0x12345678)
                        m.uc.reg_write(UC_ARM_REG_PRIMASK,mask)
                        m.call(entry,argument)
                        self.assertEqual(m.uc.reg_read(UC_ARM_REG_PRIMASK),mask)
                        rows.append(([row[:3] for row in m.mmio],m.messages,m.requests,
                                     bytes(m.uc.mem_read(0x200000C0,0xA0))))
                    self.assertEqual(*rows)

    def test_only_two_carrier_slots_and_version_strings_change(self):
        import tone_precision
        self.assertEqual(hashlib.sha256(self.previous).hexdigest(), PARENT_HASH)
        allowed = set()
        for address,size in ((0x0801A6B0,60),(0x0801A6EC,56),
                             (0x08011660,8),(0x08012E6C,8)):
            offset = self.parent.f(address)
            allowed.update(range(offset, offset+size))
        changed = {i for i,(a,b) in enumerate(zip(self.previous,self.data)) if a!=b}
        self.assertTrue(changed)
        self.assertTrue(changed <= allowed)
        self.assertEqual(len(self.previous), len(self.data))
        self.assertEqual(self.img.cave_ptr, self.parent.cave_ptr)
        self.assertEqual(self.img.ram_allocs, self.parent.ram_allocs)
        self.assertEqual(self.img._ram_ptr, self.parent._ram_ptr)
        self.assertEqual(self.img.tone_precision['persistent_ram_bytes'], 0)
        self.assertEqual(self.img.tone_precision['additional_stack_bytes'], 0)
        for address in (0x08011660,0x08012E6C):
            self.assertEqual(self.img.read(address,8), b'PN2.27\0\0')
        self.assertEqual(tone_precision.VERSION, 'PN2.27')
        with contextlib.redirect_stdout(io.StringIO()):
            again = tone_precision.build_candidate()
        self.assertEqual(bytes(again.data), self.data)

    def test_changed_parent_and_double_apply_are_rejected_without_mutation(self):
        import tone_precision
        for source,site in ((self.parent,0x0801A6B0),(self.parent,0x08014344),
                            (self.img,None)):
            img = copy.deepcopy(source)
            if site is not None:
                img.data[img.f(site)] ^= 1
            before = bytes(img.data), list(img.log), img.cave_ptr, list(img.ram_allocs)
            with self.assertRaisesRegex(PatchError, 'exact finalized PN2.26'):
                tone_precision.apply(img)
            self.assertEqual((bytes(img.data), img.log, img.cave_ptr, img.ram_allocs), before)


if __name__ == '__main__':
    unittest.main()
