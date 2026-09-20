"""Reproduce the TX tone audit on preserved PN 2.12 without writing firmware.

Run from any directory: python docs/experiments/tx_tone_performance_audit.py
Requires the SDK's existing Unicorn/Capstone dependencies. Output is JSON.
Peripheral register execution is not a hardware waveform or cycle simulation.
The optional fix below exists only in an emulator's mapped flash memory.
"""
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
SDK = ROOT / 'LPM-10A' / 'Firmware File' / 'sdk'
sys.path.insert(0, str(SDK))

from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_READ
from unicorn.arm_const import UC_ARM_REG_PRIMASK
from lpm10a.thumb import assemble
from test_scan_hardware import (RealCarrierMachine, CARRIER_INIT, PA_CRH, PB_CRH,
                                MODE_KEY, ENABLE, requested_wave)
from verify_scan import SCAN, DIGITAL, DISPATCH, IRQ

ARTIFACT = SDK.parent / 'experimental' / 'LPM-10A-TX_PN2.12-portflash-status.bin'
SHA256 = '3d2db80f8288744191fe1ddb2855a83b900166dd365e1583c6270dfb460a0076'
RIGHT_HANDLER, KEY_DISPATCH, RIGHT_GPIO = 0x0801446C, 0x080149FC, 0x0801C590
WRAPPER = 0x08068F00
WRAPPER_SOURCE = '''
    push {r4, lr}
    mrs r4, PRIMASK
    cpsid i
    bl 0x0801C590
    ldr r0, =0x200000DC
    movs r1, #255
    strb r1, [r0]
    msr PRIMASK, r4
    pop {r4, pc}
    .pool
'''


class AuditMachine(RealCarrierMachine):
    def __init__(self, data, mode=1, clocks=False):
        super().__init__(data, mode)
        self.uc.mem_map(0xE000E000, 0x2000)
        self.uc.mem_map(0x1FFFF000, 0x1000)  # factory ID page, zero-filled model
        self.edge_writes = []
        self.uc.hook_add(UC_HOOK_MEM_READ, self.read_clock)
        if clocks:
            self.call(0x080182A4)         # actual SystemInit -> SetSysClock
            self.call(0x08016598)         # actual TIM2 + NVIC initialization
        self.call(CARRIER_INIT)

    def hook(self, uc, addr, size, user):
        if addr in (0x0800F9CC, 0x0801C5B0, 0x080169A8, 0x080183CC, 0x08018592):
            # Run actual backlight, tick read, watchdog, IRQ clear and status
            # functions; the earlier ScanMachine fixture mocks these.
            self.instructions += 1
            self.calls[addr] += 1
        elif addr == 0x080116BC:          # key feedback; not relevant to GPIO ownership
            self.ret()
        else:
            super().hook(uc, addr, size, user)

    def read_clock(self, uc, access, addr, size, value, user):
        if addr == 0x40021000:
            value = self.r32(addr)
            self.w32(addr, value | ((value & 1) << 1)
                     | ((value & 0x10000) << 1) | ((value & 0x1000000) << 1))
        elif addr == 0x40021004:
            value = self.r32(addr)
            self.w32(addr, (value & ~12) | ((value & 3) << 2))

    def write_hook(self, uc, access, addr, size, value, user):
        super().write_hook(uc, access, addr, size, value, user)
        if hasattr(self, 'edge_writes') and addr in (PA_CRH, PB_CRH):
            self.edge_writes.append((self.instructions, addr, value))

    def timer_tick(self, tick, entry=IRQ):
        self.w32(0x4000000C, 1)         # TIM2 update interrupt enabled
        self.w32(0x40000010, 1)         # emulate a new TIM2 update event
        self.w32(0x200001A0, tick * 101 // 1000)
        self.call(entry)

    def right(self, full_event=False):
        if full_event:
            self.uc.mem_write(0x2000D000, bytes((5, 3)))  # RIGHT click
            self.call(KEY_DISPATCH, 0x2000D000)
        else:
            self.call(RIGHT_HANDLER, 1)

    def install_cache_repair(self):
        self.uc.mem_write(WRAPPER, assemble(WRAPPER, WRAPPER_SOURCE))
        self.uc.mem_write(0x08014480, assemble(0x08014480, f'bl {WRAPPER}'))


def clock_configuration(data):
    m = AuditMachine(data, clocks=True)
    m.call(0x08017F00, 0x2000D000)        # actual RCC_GetClocksFreq
    clocks = struct.unpack('<6I', m.uc.mem_read(0x2000D000, 24))
    assert clocks[:4] == (144000000, 144000000, 36000000, 72000000)
    tim1, tim2 = m.timer_configuration(), {
        offset: m.r32(0x40000000+offset) for offset in (0, 0x0C, 0x28, 0x2C)}
    assert (tim2[0x28], tim2[0x2C]) == (71, 100)
    tim1_clock, tim2_clock = clocks[3]*2, clocks[2]*2
    carrier = tim1_clock / (tim1[0x28]+1) / (tim1[0x2C]+1)
    tick = (tim2[0x28]+1) * (tim2[0x2C]+1) / tim2_clock
    return dict(rcc_cfg=hex(m.r32(0x40021004)), clocks_hz=clocks[:4],
                tim1={hex(k): v for k, v in tim1.items()},
                tim2={hex(k): v for k, v in tim2.items()},
                nominal_carrier_hz=carrier, nominal_tim2_tick_us=tick*1e6,
                nominal_analog_hz=1/(tick*12), nominal_digital_chip_us=tick*50*1e6,
                caveat='Firmware uses 8 MHz HSE constant; ready/status bits are modeled. Crystal frequency/tolerance is not measured.')


def irq_cost(data, mode):
    m = AuditMachine(data, mode, clocks=True)
    counts, edges, skew = Counter(), Counter(), []
    for tick in range(10001):
        start, before = m.instructions, len(m.edge_writes)
        m.timer_tick(tick)
        counts[m.instructions-start] += 1
        writes = m.edge_writes[before:]
        if writes:
            edges[m.instructions-start] += 1
            assert len(writes) == 2
            skew.append(writes[1][0]-writes[0][0])
        assert m.carrier_pins_selected() == requested_wave(mode, tick)
    return dict(ticks=sum(counts.values()), min_instructions=min(counts),
                max_instructions=max(counts),
                mean_instructions=sum(n*c for n, c in counts.items())/sum(counts.values()),
                edge_instruction_counts=dict(sorted(edges.items())),
                pin_configuration_write_separation_instructions=sorted(set(skew)),
                caveat='Instruction counts, not cycles/time. RAM defaults, no concurrent tasks or flash stalls; not worst-case interrupt latency.')


def right_key_repro(data):
    results = []
    for mode, initial in ((1, 1), (1, 101), (2, 7)):
        m = AuditMachine(data, mode)
        for tick in range(initial):
            m.timer_tick(tick, DISPATCH)
        before = m.pin_modes()
        m.right(full_event=True)
        after, cache, recovery = m.pin_modes(), m.r8(SCAN+12), 0
        while m.pin_modes() not in ((3, 3), (11, 11)) and recovery < 201:
            m.timer_tick(initial+recovery, DISPATCH)
            recovery += 1
        assert before == (11, 11) and after == (0, 11) and cache == 1
        results.append(dict(mode=mode, ticks_before_right=initial, pins_before=before,
                            pins_after_right=after, cached_gate=cache,
                            ticks_to_consistent_pins=recovery))
    return results


def cache_repair_experiment(data):
    cases = 0
    mask_cases, unmasked_states, maximum_masked_instructions = 0, set(), 0
    for mode, phases in ((1, 800), (2, 12)):
        for phase in range(phases):
            m = AuditMachine(data, mode)
            if mode == 1:
                m.w32(DIGITAL, phase)
                m.timer_tick(phase, DISPATCH)
            else:
                for tick in range(phase+1):
                    m.timer_tick(tick, DISPATCH)
            m.install_cache_repair()
            state_before = bytes(m.uc.mem_read(DIGITAL, 10))
            m.right()
            assert m.r8(SCAN+12) == 255
            # The underlying PA8 operation is retained, not replaced by NOP.
            assert m.pin_modes()[0] == 0
            after = bytes(m.uc.mem_read(DIGITAL, 10))
            assert after[:4] == state_before[:4] and after[5:] == state_before[5:]
            m.timer_tick(phase+1, DISPATCH)
            assert m.carrier_pins_selected() == requested_wave(mode, phase+1)
            cases += 1
    for mask in (0, 1):
        for mode, initial in ((1, 1), (1, 51), (2, 1), (2, 7)):
            m = AuditMachine(data, mode)
            for tick in range(initial):
                m.timer_tick(tick, DISPATCH)
            m.install_cache_repair()
            m.uc.reg_write(UC_ARM_REG_PRIMASK, mask)
            snapshots, masked_run = [], []
            def observe(uc, addr, size, user):
                if uc.reg_read(UC_ARM_REG_PRIMASK):
                    masked_run.append(addr)
                else:
                    snapshots.append((*m.pin_modes(), m.r8(SCAN+12)))
            hook = m.uc.hook_add(UC_HOOK_CODE, observe)
            m.right()
            m.uc.hook_del(hook)
            assert m.uc.reg_read(UC_ARM_REG_PRIMASK) == mask
            # Every unmasked boundary is either the old valid pin/cache state
            # or the new state with invalid cache; an IRQ cannot skip repair.
            assert all(a == b and a in (3, 11) or cache == 255 for a, b, cache in snapshots)
            unmasked_states.update(snapshots)
            if mask == 0:
                maximum_masked_instructions = max(maximum_masked_instructions, len(masked_run))
            mask_cases += 1
    return dict(phase_cases=cases, primask_cases=mask_cases,
                unmasked_states=sorted(unmasked_states),
                maximum_newly_masked_instructions=maximum_masked_instructions,
                wrapper_bytes=len(assemble(WRAPPER, WRAPPER_SOURCE)),
                next_tick_repair=True,
                caveat='In-memory experiment only. Original RIGHT GPIO operation retained. PRIMASK boundary inspection is not full hardware interrupt emulation.')


def off_level_sequence(data):
    m = AuditMachine(data)
    # Run the real RTOS tick reader and both GPIO bit-write routines.
    levels = []
    for tick in range(32):
        m.w32(0x200001A0, tick)
        m.call(0x0801A6B0)
        a_set, b_set = m.r32(0x40010810), m.r32(0x40010C10)
        a_clear, b_clear = m.r32(0x40010814), m.r32(0x40010C14)
        # These are write registers, not emulated output latches. Check which
        # path runs using a fresh zero before each call, then record the call.
        expected = (tick ^ (tick >> 8) ^ (tick >> 16)) & 7
        expected = (expected.bit_count() & 1)
        assert (a_set == 0x100 and b_set == 0x2000) if expected else (a_clear == 0x100 and b_clear == 0x2000)
        levels.append(expected)
        for addr in (0x40010810, 0x40010C10, 0x40010814, 0x40010C14):
            m.w32(addr, 0)
    return dict(tick_samples=32, gpio_off_levels=levels,
                formula='Both pins static HIGH if parity((tick ^ tick>>8 ^ tick>>16) & 7)==1, else both static LOW.',
                caveat='This is deliberate-looking vendor behavior. It does not establish jack common-mode voltage or justify changing polarity.')


def main():
    data = ARTIFACT.read_bytes()
    actual = hashlib.sha256(data).hexdigest()
    assert actual == SHA256, f'Expected audit artifact {SHA256}, got {actual}'
    result = dict(artifact=str(ARTIFACT), sha256=actual,
                  clocks=clock_configuration(data),
                  irq={str(mode): irq_cost(data, mode) for mode in (1, 2)},
                  right_key_reproduction=right_key_repro(data),
                  conservative_cache_repair=cache_repair_experiment(data),
                  stock_off_level=off_level_sequence(data))
    assert hashlib.sha256(ARTIFACT.read_bytes()).hexdigest() == actual
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
