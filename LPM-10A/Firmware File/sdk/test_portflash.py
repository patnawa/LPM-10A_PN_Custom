"""Port FLASH regressions executing PHY helpers, with MDIO/RTOS modeled."""
import struct
import hashlib
from pathlib import Path

from unicorn.arm_const import UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7, UC_ARM_REG_SP

from audit_flash_length import Machine, FLAGS, PHASE
import test_roadmap
import patches
from portflash import PATCH_ID
from build import PORTFLASH_OUT


class PhyMachine(Machine):
    """Run vendor power/advertisement/autoneg instructions instead of stubs."""
    def __init__(self, data, state=6):
        super().__init__(data, state)
        self.phy = {0: 0x1940, 4: 0x01E1, 9: 0x0200, 0x11: 0}
        self.powered = False
        self.reads = []
        for addr in (0x0801D178, 0x0801D2B4, 0x0801D3F4, 0x0801D534):
            self.handlers[addr] = lambda m: None
        self.handlers[0x080178F0] = self.read_phy
        self.handlers[0x08017AFC] = self.write_phy

    def read_phy(self, m):
        self.reads.append(m.arg(0))
        m.ret((0x24 if self.link else 0) if m.arg(0) == 1 else self.phy.get(m.arg(0), 0))

    def write_phy(self, m):
        reg, value = m.arg(0), m.arg(1)
        self.mdios.append((reg, value))
        # Model BMCR restart as self-clearing. No negotiation-success assumption.
        self.phy[reg] = value & ~0x0200 if reg == 0 else value
        if reg == 0:
            down = bool(value & 0x0800)
            if not down and not self.powered:
                self.up_since = self.now
            self.powered = not down
            self.power.append((self.now, int(down)))
        m.ret()


class PortFlash(test_roadmap.Roadmap):
    @classmethod
    def setUpClass(cls):
        cls.img = test_roadmap.build_candidate()
        cls.previous = bytes(cls.img.data)
        cls.previous_end = cls.img.cave_ptr
        next(p for p in patches.REGISTRY if p.pid == PATCH_ID)(cls.img)
        cls.img.finalize()
        cls.data = bytes(cls.img.data)

    def test_candidate_matches_disk(self):
        path = Path(PORTFLASH_OUT)
        self.assertEqual(path.read_bytes(), self.data)

    def test_only_declared_changes_from_released_roadmap(self):
        self.assertEqual(hashlib.sha256(self.previous).hexdigest(),
                         '2a82c86de8bf9d81dd191ca742d83e6d4b6d359db22daf9a6b0c65f48b5583dd')
        self.assertEqual(len(self.previous), len(self.data))
        allowed = set(range(0x24, 0x2C))
        for addr, size in ((0x0801D53A, 2), (0x0801D5B4, 2),
                           (0x0801494C, 4), (0x08011660, 8), (0x08012E6C, 8),
                           (self.previous_end, self.img.cave_ptr - self.previous_end)):
            allowed.update(range(self.img.f(addr), self.img.f(addr) + size))
        changed = {i for i, (a, b) in enumerate(zip(self.previous, self.data)) if a != b}
        self.assertTrue(changed <= allowed, sorted(changed - allowed))
        self.assertEqual(self.img.read(0x08011660, 8), b'PN 2.10\0')
        self.assertEqual(self.img.read(0x08012E6C, 8), b'PN 2.10\0')

    def test_previous_release_reproduces_register_and_hold_defects(self):
        m = PhyMachine(self.previous)
        m.phy[4] = 0x61
        m.call(0x0801D534, 1)
        self.assertEqual(m.mdios, [(4, 0x1261)])
        m = Machine(self.previous, 6)
        m.w8(FLAGS + 1, 2)
        for now, link in ((0, 0), (500, 1), (1000, 0), (1500, 1), (2000, 1)):
            m.tick(now, link)
        self.assertEqual(m.power, [(2000, 1)], 'old code cuts recovered link after 500 ms')
        m = Machine(self.previous, 6)
        m.w8(FLAGS + 1, 2)
        def slow_power(machine):
            down = machine.arg(0)
            machine.now += 200 if down else 75
            machine.power.append((machine.now, down))
            machine.ret()
        m.handlers[0x0801D178] = slow_power
        for now, link in ((0, 0), (500, 1), (2000, 1), (3000, 0)):
            m.tick(now, link)
        self.assertEqual(m.power, [(2200, 1), (3075, 0)], 'old dark interval is only 875 ms')

    def test_autoneg_uses_bmcr_and_preserves_advertisement(self):
        for enabled in (0, 1):
            for bmcr in (0x0140, 0x1940, 0x3100):
                with self.subTest(enabled=enabled, bmcr=hex(bmcr)):
                    m = PhyMachine(self.data)
                    m.phy[0] = bmcr
                    original_adv = m.phy[4]
                    m.call(0x0801D534, enabled)
                    expected = bmcr | 0x1200 if enabled else bmcr & ~0x1000
                    self.assertEqual(m.reads, [0])
                    self.assertEqual(m.mdios, [(0, expected)])
                    self.assertEqual(m.phy[4], original_adv)

    def test_complete_flash_setup_restarts_an_without_false_advertisement(self):
        m = PhyMachine(self.data)
        m.call(0x0800D47C)
        self.assertEqual(m.r8(FLAGS + 1), 2)
        self.assertEqual(m.phy[4], 0x0061)
        self.assertEqual(m.phy[9], 0)
        self.assertTrue(any(reg == 0 and value & 0x1200 == 0x1200 for reg, value in m.mdios))
        self.assertFalse(m.phy[0] & 0x0800)

    def test_speed_setup_preserves_supported_advertisements(self):
        m = PhyMachine(self.data, 9)
        # Execute the actual shared setup up to the SPEED-specific link wait.
        m.handlers[0x0801B06C] = lambda machine: machine.ret()
        m.call(0x0800D47C, until=0x0800D5E0)
        self.assertEqual(m.phy[4], 0x01E1)
        self.assertEqual(m.phy[9], 0x0200)
        self.assertTrue(any(reg == 0 and value & 0x1200 == 0x1200 for reg, value in m.mdios))
        self.assertFalse(m.phy[0] & 0x0800)

    def test_ten_minute_sessions_unplug_replug_exit_and_reentry(self):
        for delay in (500, 4500, 12000, 16000):
            with self.subTest(negotiation_ms=delay):
                m = PhyMachine(self.data)
                m.call(0x0800D47C)
                links = []
                for now in range(1000, 601000, 500):
                    linked = (m.powered and now - m.up_since >= delay
                              and not 120000 <= now < 150000)
                    before = m.r8(PHASE)
                    m.tick(now, int(linked))
                    if before != 1 and m.r8(PHASE) == 1:
                        links.append(now)
                    self.assertEqual(m.phy[4], 0x61)
                self.assertGreater(len(links), 15)
                self.assertTrue(any(t > 150000 for t in links))
                m.call(0x0800DB8C)
                self.assertFalse(m.powered)
                self.assertEqual(m.r8(PHASE), 0)
                self.assertEqual(m.r8(FLAGS + 1), 0)
                count = len(m.mdios)
                m.tick(602000, 1)
                self.assertEqual(len(m.mdios), count)
                m.w8(0x2000013C, 6)
                m.call(0x0800D47C)
                m.tick(603000, 0)
                self.assertEqual(struct.unpack('<I', m.uc.mem_read(self.img.flash['window'], 4))[0], 4000)

    def test_existing_reliability_and_scan_suites(self):
        import verify_reliability
        import verify_scan
        def check(ok, label, detail=''):
            self.assertTrue(ok, label + ': ' + detail)
        verify_reliability.run_checks(self.data, self.img, check)
        verify_scan.run_checks(self.img.original, self.data, check, irq_reference=self.previous)

    def test_link_loss_restarts_hold_after_recovery(self):
        for start in (0, 0xFFFFFC00):
            m = self.machine(6)
            m.w8(FLAGS + 1, 2)
            def tick(dt, link):
                m.tick((start + dt) & 0xFFFFFFFF, link)
            tick(0, 0)
            tick(500, 1)
            tick(1000, 0)
            self.assertEqual(m.r8(PHASE), 3)
            tick(1500, 1)
            tick(2000, 1)
            tick(2999, 1)
            self.assertFalse(any(down for _, down in m.power))
            tick(3000, 1)
            self.assertEqual(m.power[-1], ((start + 3000) & 0xFFFFFFFF, 1))

    def test_dark_interval_starts_after_power_write_completes(self):
        m = self.machine(6)
        m.w8(FLAGS + 1, 2)
        def slow_power(machine):
            down = machine.arg(0)
            machine.now += 200 if down else 75  # preemption / MDIO / logging latency
            machine.power.append((machine.now, down))
            machine.ret()
        m.handlers[0x0801D178] = slow_power
        m.tick(0, 0)
        m.tick(500, 1)
        m.tick(2000, 1)
        self.assertEqual(m.power, [(2200, 1)])
        m.tick(3000, 0)
        self.assertEqual(m.power, [(2200, 1)], "must not begin powering up after only 800 ms")
        m.tick(3200, 0)
        self.assertEqual(m.power[-1], (3275, 0))
        self.assertEqual(struct.unpack('<I', m.uc.mem_read(self.img.flash['start'], 4))[0], 3275)

    def test_stale_messages_and_register_preservation(self):
        for state in (2, 6, 7, 9):
            for busy in (0, 1, 2, 3):
                m = self.machine(state)
                m.w8(FLAGS + 1, busy)
                for reg in (UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7):
                    m.uc.reg_write(reg, 0xA55AA55A)
                m.tick(0, 0)
                m.tick(500, 0)
                self.assertEqual(bool(m.power), state == 6 and busy == 2)
                self.assertEqual(m.uc.reg_read(UC_ARM_REG_SP), 0x2000E000)
                for reg in (UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7):
                    self.assertEqual(m.uc.reg_read(reg), 0xA55AA55A)


if __name__ == '__main__':
    import unittest
    unittest.main()
