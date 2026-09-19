"""Read-only CPU experiments for FLASH/length; no firmware files are written.

Run: python audit_flash_length.py [../LPM-10A-TX_PN2.5.bin]
PHY responses, elapsed time, RTOS calls and drawing are simulated. Firmware
control flow, voting, averaging, conversion and formatters execute in Unicorn.
"""
import json
from pathlib import Path
import struct
import sys

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB
from thai.engine import ram_init

APP, STOP = 0x0800A000, 0x00100000
REGS = [UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3]
FLAGS, PHASE, LAST, UNIT = 0x200002B4, 0x20000076, 0x200002B8, 0x200002C0


class Machine:
    def __init__(self, data, state):
        off, size = struct.unpack_from('<II', data, 0x20)
        self.payload = data[off:off + size]
        self.uc = uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
        for base, size in ((0x08000000, 0x80000), (0x20000000, 0x10000),
                           (0x40000000, 0x30000), (STOP, 0x1000)):
            uc.mem_map(base, size)
        uc.mem_write(APP, self.payload)
        uc.mem_write(0x20000000, ram_init(self.payload))
        self.w8(0x2000013C, state)
        self.now, self.run_index, self.link = 0, -1, 0
        self.powered, self.up_since = True, 0
        self.power, self.messages, self.mdios = [], [], []
        self.runs = [(1000,) * 4] * 4
        self.busy = False
        self.cancel_after = None
        self.run_started = 0
        self.done_after = 0
        self.handlers = {}
        uc.hook_add(UC_HOOK_CODE, self.hook)

    def w8(self, addr, value):
        self.uc.mem_write(addr, bytes([value]))

    def w16(self, addr, value):
        self.uc.mem_write(addr, struct.pack('<H', value))

    def r8(self, addr):
        return self.uc.mem_read(addr, 1)[0]

    def arg(self, n):
        return self.uc.reg_read(REGS[n])

    def ret(self, value=0):
        self.uc.reg_write(UC_ARM_REG_R0, value & 0xFFFFFFFF)
        self.uc.reg_write(UC_ARM_REG_PC, self.uc.reg_read(UC_ARM_REG_LR))

    def hook(self, uc, addr, size, user):
        if addr in self.handlers:
            self.handlers[addr](self)
            return
        if addr == 0x08011A6E:
            self.run_index += 1
            self.run_started = self.now
        elif addr == 0x0801C5B0:
            self.ret(self.now)
        elif addr == 0x0801C75C:
            self.now += self.arg(0)
            if self.cancel_after is not None and self.now >= self.cancel_after:
                self.w8(0x2000013C, 2)
            self.ret()
        elif addr == 0x08018A80:
            reg = self.arg(0)
            value = 0x8000 if reg == 0x84 and (self.busy or self.now - self.run_started < self.done_after) else 0
            if 0x87 <= reg <= 0x8A:
                value = self.runs[min(max(self.run_index, 0), len(self.runs) - 1)][reg - 0x87]
            self.w16(self.arg(1), value)
            self.ret()
        elif addr == 0x08015AF2:
            self.ret(self.link)
        elif addr == 0x0801D178:
            down = self.arg(0)
            self.power.append((self.now, down))
            if not down and not self.powered:
                self.up_since = self.now
            self.powered = not down
            self.ret()
        elif addr in (0x0800E428, 0x08012FBC):
            self.messages.append(self.arg(0))
            self.ret()
        elif addr == 0x08012C64:
            self.ret(0x2000F800)
        elif addr == 0x080178F0:
            self.ret(0)
        elif addr == 0x08017AFC:
            self.mdios.append((self.arg(0), self.arg(1)))
            self.ret()
        elif addr in {0x0801C6B4, 0x0801C6D8, 0x0800A82C, 0x0800A3B8,
                      0x0801CAA0, 0x08018A9E, 0x08019CBC, 0x08019C38,
                      0x0800EF6C, 0x08010F94, 0x0800E1B4,
                      0x0801D2B4, 0x0801D3F4, 0x0801D534}:
            self.ret()

    def call(self, addr, *args, until=STOP, count=500000):
        self.uc.reg_write(UC_ARM_REG_SP, 0x2000E000)
        self.uc.reg_write(UC_ARM_REG_LR, STOP | 1)
        for reg, value in zip(REGS, args):
            self.uc.reg_write(reg, value)
        self.uc.emu_start(addr | 1, until, count=count)
        pc = self.uc.reg_read(UC_ARM_REG_PC)
        if pc != until:
            raise RuntimeError(f'{addr:#x} stopped at {pc:#x}, expected {until:#x}')
        return self.arg(0)

    def tick(self, now, link):
        self.now, self.link = now, link
        self.call(0x0801494C, until=0x08014992)

    def lengths(self):
        return list(struct.unpack('<4H', self.uc.mem_read(LAST, 8)))


def run(data):
    results = {}
    for delay in (500, 1500, 3500, 4000, 4500, 6000):
        m = Machine(data, 6)
        m.w8(FLAGS + 1, 2)
        held = 0
        for t in range(0, 60001, 500):
            before = m.r8(PHASE)
            m.tick(t, int(m.powered and t - m.up_since >= delay))
            held += before != 1 and m.r8(PHASE) == 1
        results[f'flash_relink_{delay}ms'] = dict(links_seen=held,
            power_downs=sum(down == 1 for _, down in m.power))

    m = Machine(data, 6)
    m.w8(FLAGS + 1, 2)
    for t in (0, 500, 1000, 1500, 1750):
        m.tick(t, 1)
    m.tick(2500, 0)
    results['flash_delayed_messages'] = m.power

    m = Machine(data, 6)
    m.w8(FLAGS + 1, 2)
    start = 0xFFFFFC00
    for delta in (0, 500, 1000, 1500, 2000, 2500, 3000):
        m.tick((start + delta) & 0xFFFFFFFF, int(delta <= 2000))
    results['flash_tick_wrap'] = m.power
    m.w8(FLAGS + 1, 0)
    n = len(m.power)
    m.tick(10000, 1)
    results['flash_stopped_makes_no_phy_call'] = len(m.power) == n

    m = Machine(data, 6)
    m.call(0x0800D47C)
    results['flash_setup'] = dict(flag=m.r8(FLAGS + 1), phase=m.r8(PHASE),
                                 ms=m.now, power=list(m.power))
    m.call(0x0800DB8C)
    results['flash_exit'] = dict(flag=m.r8(FLAGS + 1), phase=m.r8(PHASE),
        state=m.r8(0x2000013C), powered=m.powered)

    vectors = {
        'normal_14m': [(1440, 1460, 1500, 1480), (1470, 1450, 1490, 1500),
                       (1450, 1470, 1480, 1460), (1460, 1440, 1510, 1470)],
        'unequal_pairs': [(5000, 5000, 5000, 4800)] * 4,
        'large_pair_difference': [(5000, 5000, 5000, 1000)] * 4,
        'one_pair_reads_once': [(5000, 5000, 5000, 4800)] + [(5000, 5000, 5000, 0)] * 3,
        'unplug_after_first_run': [(5000,) * 4] + [(0,) * 4] * 3,
        'all_zero': [(0,) * 4] * 4,
        'short_threshold': [(199, 200, 201, 220)] * 4,
        'all_ffff': [(65535,) * 4] * 4,
    }
    for name, runs in vectors.items():
        m = Machine(data, 7)
        m.runs = runs
        m.call(0x080119EC)
        results['length_' + name] = dict(runs=m.run_index + 1, cm=m.lengths(),
            flag=m.r8(FLAGS), ms=m.now, messages=m.messages)

    for name, busy, cancel in [('busy_timeout', True, None), ('cancel_busy', True, 100),
                               ('cancel_finishing', False, 50)]:
        m = Machine(data, 7)
        m.busy, m.cancel_after = busy, cancel
        m.call(0x080119EC)
        results['length_' + name] = dict(runs=m.run_index + 1, cm=m.lengths(),
            flag=m.r8(FLAGS), ms=m.now, messages=m.messages, final_power=m.power[-1:])

    for start in (0, 0xFFFFFC00):
        m = Machine(data, 7)
        m.now, m.done_after = start, 19000
        m.call(0x080119EC, count=2000000)
        results[f'length_slow_runs_start_{start}'] = dict(runs=m.run_index + 1,
            cm=m.lengths(), flag=m.r8(FLAGS), elapsed_ms=m.now - start)

    m = Machine(data, 7)
    m.w8(0x20000C78 + 0xA6, 99)
    m.w8(0x20000C78 + 0xC5, 0)
    conversions = {}
    for raw in (201, 334, 30000, 45675, 45676, 45677, 60000, 65535):
        values = []
        for unit in range(3):
            m.w8(UNIT, unit)
            values.append(m.call(0x08019774, raw))
        conversions[raw] = values
    results['conversion_nvp99_m_tenths_cm_ft_tenths'] = conversions

    mismatches, count = [], 0
    for nvp in (*range(50, 100), 0, 49, 100, 255):
        for zero in (0, 4, 20, 255):
            m.w8(0x20000C78 + 0xA6, nvp)
            m.w8(0x20000C78 + 0xC5, zero)
            for raw in (0, 1, 199, 200, 201, 220, 334, 999, 1000, 9999, 10000, 30000):
                cm = max(0, raw - (zero * 10 if zero <= 20 else 0))
                cm = (cm * (nvp if 50 <= nvp <= 99 else 69) + 34) // 69
                for unit, expected in enumerate(((cm + 5) // 10, cm, (cm * 1000 + 1524) // 3048)):
                    m.w8(UNIT, unit)
                    actual = m.call(0x08019774, raw)
                    count += 1
                    if actual != expected:
                        mismatches.append((raw, nvp, zero, unit, actual, expected))
    results['conversion_grid_through_30000cm'] = dict(cases=count, mismatches=mismatches)

    # Execute the firmware's sprintf via the actual patched formatter.
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    site = 0x08019B12
    ins = next(md.disasm(m.payload[site - APP:site - APP + 4], site))
    formatter = int(ins.op_str.lstrip('#'), 16)
    m.w8(0x20000C78 + 0xA6, 68)
    m.w8(0x20000C78 + 0xC5, 4)
    m.uc.mem_write(0x2000D000, b'1-2\0')
    texts = {}
    for raw in (0, 334, 1470):
        for unit in range(3):
            m.w8(UNIT, unit)
            value = m.call(0x08019774, raw)
            length = m.call(formatter, 0x2000D080, 0x08019C28, 0x2000D000, value)
            text = bytes(m.uc.mem_read(0x2000D080, 40)).split(b'\0')[0].decode('ascii')
            if length != len(text):
                raise RuntimeError('formatter length mismatch')
            texts[f'{raw}cm_unit{unit}'] = text
    results['real_sprintf_nvp68_zero4'] = texts

    m = Machine(data, 2)
    captions = []
    def capture_blit(machine):
        sp = machine.uc.reg_read(UC_ARM_REG_SP)
        ptr = struct.unpack('<I', machine.uc.mem_read(sp + 4, 4))[0]
        captions.append(bytes(machine.uc.mem_read(ptr, 32)).split(b'\0')[0].decode('ascii'))
        machine.ret()
    m.handlers[0x080174E8] = capture_blit
    m.call(0x0800F48C, 0x3D, until=0x0800F4DC)
    results['length_queued_calibration_redraw_on_home'] = captions

    m = Machine(data, 6)
    m.handlers[0x0801D178] = lambda machine: None  # execute the actual helper body
    m.handlers[0x080178F0] = lambda machine: machine.ret(0x1940)
    for down in (0, 1):
        m.call(0x0801D178, down)
    results['actual_phy_power_helper_bmcr_1940'] = m.mdios
    return results


if __name__ == '__main__':
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / 'LPM-10A-TX_PN2.5.bin'
    print(json.dumps(run(path.read_bytes()), indent=2))
