"""PN 2.12 regressions: separate physical link status from the indicator GPIO."""
import hashlib
from pathlib import Path

from unicorn.arm_const import UC_ARM_REG_R4, UC_ARM_REG_SP
from audit_flash_length import Machine, FLAGS, PHASE
from build import PORTFLASH_STATUS_OUT, AUDIT_OUT
from lpm10a.thumb import assemble
from portflash_status import PATCH_ID
import patches
import test_firmware_audit
from test_portflash import PhyMachine


class PortFlashStatus(test_firmware_audit.Audit):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.audit_data = cls.data
        cls.audit_end = cls.img.cave_ptr
        next(p for p in patches.REGISTRY if p.pid == PATCH_ID)(cls.img)
        cls.img.finalize()
        cls.data = bytes(cls.img.data)

    def test_candidate_matches_disk(self):
        self.assertEqual(Path(PORTFLASH_STATUS_OUT).read_bytes(), self.data)

    def test_only_declared_changes_from_released_roadmap(self):
        self.assertEqual(Path(AUDIT_OUT).read_bytes(), self.audit_data)
        self.assertEqual(hashlib.sha256(self.audit_data).hexdigest(),
                         'de27a1448cc1977d00a2104abb9f48dda227e8d71c9040d986769f8e5ffe43f9')
        self.assertEqual(len(self.data), len(self.audit_data))
        allowed = set(range(0x24, 0x2C))
        sites = [(a, 4) for a in self.img.flash_status['sites']]
        sites += [(0x0800DC6C, 4), (0x08011660, 8), (0x08012E6C, 8),
                  (self.audit_end, self.img.cave_ptr-self.audit_end)]
        for addr, size in sites:
            allowed.update(range(self.img.f(addr), self.img.f(addr)+size))
        changed = {i for i, (a, b) in enumerate(zip(self.audit_data, self.data)) if a != b}
        self.assertTrue(changed <= allowed, sorted(changed-allowed))
        self.assertEqual(self.img.read(0x08011660, 8), b'PN 2.12\0')
        self.assertEqual(self.img.read(0x08012E6C, 8), b'PN 2.12\0')

    def test_steady_link_with_gpio_pulses_reproduces_old_indefinite_hold(self):
        for buf, old in ((self.audit_data, True), (self.data, False)):
            m = PhyMachine(buf)
            m.call(0x0800D47C)
            m.handlers[0x08015AF2] = lambda cpu: cpu.ret(int(cpu.powered and cpu.now % 1500 != 1000))
            # Link is continuously up whenever powered, independently of PB5.
            for now in range(1000, 601000, 500):
                m.tick(now, int(m.powered))
            downs = [t for t, down in m.power if down and t >= 1000]
            if old:
                self.assertEqual(downs, [], 'PN 2.11 never deliberately drops a steady link under this pin pattern')
            else:
                self.assertGreater(len(downs), 150)
                self.assertEqual(set(b-a for a, b in zip(downs, downs[1:])), {3000})

    def test_gpio_stuck_high_or_low_does_not_control_link_timing(self):
        for pin in (0, 1):
            m = PhyMachine(self.data)
            m.call(0x0800D47C)
            m.handlers[0x08015AF2] = lambda cpu, pin=pin: cpu.ret(pin)
            for now in (1000, 1500, 2000, 2500, 3000):
                m.tick(now, 1)
            self.assertEqual(m.power[-1], (3000, 1))
            m.tick(4000, 0)
            m.tick(4500, 0)
            self.assertEqual(m.r8(PHASE), 3, 'even high GPIO cannot manufacture a link')

    def test_bmsr_latch_low_invalid_reads_and_abi(self):
        for first, second, expected in ((0x7809, 0x782D, 1), (0x782D, 0x7809, 0),
                                       (0, 0, 0), (0xFFFF, 0x782D, 0),
                                       (0x782D, 0xFFFF, 0), (0xFFFF, 0xFFFF, 0),
                                       (4, 4, 1)):
            m = Machine(self.data, 6)
            samples = iter((first, second))
            reads = []
            def read(cpu):
                reads.append(cpu.arg(0))
                cpu.ret(next(samples))
            m.handlers[0x080178F0] = read
            m.uc.reg_write(UC_ARM_REG_R4, 0x12345678)
            self.assertEqual(m.call(self.img.flash_status['link']), expected)
            self.assertEqual(reads, [1, 1])
            self.assertEqual(m.uc.reg_read(UC_ARM_REG_R4), 0x12345678)
            self.assertEqual(m.uc.reg_read(UC_ARM_REG_SP), 0x2000E000)

    def test_actual_indicator_call_uses_phase_without_concurrent_mdio(self):
        for phase in (0, 1, 2, 3, 255):
            m = Machine(self.data, 6)
            m.w8(FLAGS + 1, 2)
            m.w8(PHASE, phase)
            m.handlers[0x080178F0] = lambda cpu: self.fail('indicator task must not access MDIO')
            m.handlers[0x08015AF2] = lambda cpu: self.fail('indicator must not use raw PB5')
            m.call(0x0800DC68, until=0x0800DC72)
            self.assertEqual(m.uc.reg_read(UC_ARM_REG_R4), int(phase == 1))

    def test_dark_stopped_and_other_screens_do_not_poll_mdio(self):
        for state, flag, phase in ((6, 0, 1), (6, 1, 1), (2, 2, 1), (9, 2, 1), (6, 2, 2)):
            m = Machine(self.data, state)
            m.w8(FLAGS+1, flag)
            m.w8(PHASE, phase)
            m.handlers[0x080178F0] = lambda cpu: self.fail('inactive/dark handler must not poll MDIO')
            m.tick(100, 1)

    def test_intermittent_mdio_error_recovers_without_false_hold(self):
        m = PhyMachine(self.data)
        m.call(0x0800D47C)
        original = m.handlers[0x080178F0]
        def read(cpu):
            if cpu.arg(0) == 1 and cpu.now == 2000:
                cpu.ret(0xFFFF)
            else:
                original(cpu)
        m.handlers[0x080178F0] = read
        for now in (1000, 1500, 2000):
            m.tick(now, 1)
        self.assertEqual(m.r8(PHASE), 3)
        m.tick(2500, 1)
        m.tick(3999, 1)
        self.assertFalse(any(down and t >= 1000 for t, down in m.power))
        m.tick(4000, 1)
        self.assertEqual(m.power[-1], (4000, 1))

    def test_replacement_sites_target_the_status_reader(self):
        for site in self.img.flash_status['sites']:
            self.assertEqual(self.img.read(site, 4), assemble(site, f'bl {self.img.flash_status["link"]}'))


if __name__ == '__main__':
    import unittest
    unittest.main()
