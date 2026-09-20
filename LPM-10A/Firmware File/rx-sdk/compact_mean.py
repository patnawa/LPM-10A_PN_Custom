"""Semantics-preserving compact form of the stock shared trimmed-mean helper.

Reclaims 156 bytes after the helper, without changing its uint8 count, u16
samples/result, zero-count behavior, or callers. Its only writes are the
16-byte register save on the caller's stack (stock uses 24 bytes). No global
RAM, peripherals, floating-point registers or interrupt mask are touched.

Run this file for a read-only differential ARM check against PN 1.8. It does
not build or write a firmware image.
"""
import hashlib

from lpm10rx.image import PatchError

ADDRESS = 0x0800B630
END = 0x0800B70C
MAX_CODE_SIZE = 64
TAIL_START = ADDRESS + MAX_CODE_SIZE
AVAILABLE_TAIL = END - TAIL_START
ORIGINAL_SHA256 = '9259253e2c05aba188c65442ea458d33f07f923841fc2682ffc55b0059fb32b8'

SOURCE = '''
    push {r4, r5, r6, lr}
    uxtb r1, r1
    cbz r1, zero
    mov r4, r0
    mov r5, r1
    movs r0, #0
    movw r2, #65535
    movs r3, #0
loop:
    ldrh r6, [r4]
    adds r4, #2
    add r0, r6
    cmp r6, r2
    bhs no_min
    mov r2, r6
no_min:
    cmp r6, r3
    bls no_max
    mov r3, r6
no_max:
    subs r5, #1
    bne loop
    cmp r1, #3
    blo divide
    subs r0, r0, r2
    subs r0, r0, r3
    subs r1, #2
divide:
    udiv r0, r0, r1
    uxth r0, r0
    pop {r4, r5, r6, pc}
zero:
    movs r0, #0
    pop {r4, r5, r6, pc}
'''


def apply(img):
    """Compact the exact audited helper and expose its NOP-filled tail."""
    before = img.read(ADDRESS, END - ADDRESS)
    if hashlib.sha256(before).hexdigest() != ORIGINAL_SHA256:
        raise PatchError('compact mean requires the exact audited stock helper')
    code = img.assemble_at(ADDRESS, SOURCE)
    if len(code) > MAX_CODE_SIZE or len(code) % 2:
        raise PatchError('compact mean exceeds its 64-byte reservation')
    replacement = code + bytes.fromhex('00bf') * ((END - ADDRESS - len(code)) // 2)
    img.poke(ADDRESS, before.hex(), replacement,
             'preserve shared trimmed mean and reclaim 156 bytes after its return')


def differential_audit(data):
    """Check real old/new ARM instructions for every u8 count and edge values.

    This is CPU equivalence evidence; ADC timing and interrupt arrival are not
    modeled here. A leaf helper is reentrant because all state is local.
    """
    import random
    import struct

    from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_MEM_WRITE
    from unicorn import arm_const as arm
    from lpm10rx.image import assemble

    base, buffer, stack, stop = 0x08006800, 0x20000200, 0x20003000, 0x0800D000
    original = data[ADDRESS-base:END-base]
    if hashlib.sha256(original).hexdigest() != ORIGINAL_SHA256:
        raise AssertionError('input does not contain the audited original helper')
    code = assemble(ADDRESS, SOURCE)
    if len(code) > MAX_CODE_SIZE:
        raise AssertionError('compact helper exceeds reservation')
    cpus, writes = [], [[], []]
    for index in range(2):
        cpu = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
        cpu.mem_map(0x08006000, 0x8000)
        cpu.mem_map(0x20000000, 0x4000)
        cpu.mem_write(base, data)
        if index:
            cpu.mem_write(ADDRESS, code)
        cpu.hook_add(UC_HOOK_MEM_WRITE,
                     lambda uc, access, address, size, value, log: log.append((address, size)),
                     writes[index])
        cpus.append(cpu)
    preserved = tuple(getattr(arm, f'UC_ARM_REG_R{i}') for i in range(4, 12))
    rng = random.Random(1945)
    checked = 0
    for count in range(256):
        for kind in range(12):
            values = ([0] * count if kind == 0 else [65535] * count if kind == 1
                      else [i * 257 for i in range(count)] if kind == 2
                      else [rng.randrange(65536) for _ in range(count)])
            expected = (0 if not count else sum(values) // count if count < 3
                        else (sum(values)-min(values)-max(values)) // (count-2))
            packed = struct.pack('<' + 'H'*count, *values)
            full_count = count | (rng.randrange(1 << 24) << 8)
            for index, cpu in enumerate(cpus):
                cpu.mem_write(buffer, packed or b'\xa5\xa5')
                for register in preserved:
                    cpu.reg_write(register, 0xA0000000 + register)
                # Zero count must return without dereferencing even a null pointer.
                cpu.reg_write(arm.UC_ARM_REG_R0, buffer if count else 0)
                cpu.reg_write(arm.UC_ARM_REG_R1, full_count)
                cpu.reg_write(arm.UC_ARM_REG_SP, stack)
                cpu.reg_write(arm.UC_ARM_REG_LR, stop | 1)
                cpu.reg_write(arm.UC_ARM_REG_PRIMASK, checked & 1)
                writes[index].clear()
                cpu.emu_start(ADDRESS | 1, stop, count=50000)
                assert cpu.reg_read(arm.UC_ARM_REG_PC) == stop
                assert cpu.reg_read(arm.UC_ARM_REG_R0) == expected, (count, kind, index)
                assert cpu.reg_read(arm.UC_ARM_REG_SP) == stack
                assert cpu.reg_read(arm.UC_ARM_REG_PRIMASK) == checked & 1
                assert all(cpu.reg_read(reg) == 0xA0000000 + reg for reg in preserved)
                if packed:
                    assert bytes(cpu.mem_read(buffer, len(packed))) == packed
                depth = 16 if index else 24
                assert all(stack-depth <= address and address+size <= stack
                           for address, size in writes[index])
            checked += 1
    return {'cases': checked, 'code_bytes': len(code), 'tail_start': hex(TAIL_START),
            'tail_bytes': AVAILABLE_TAIL, 'stack_bytes': 16}


if __name__ == '__main__':
    import sys
    from pathlib import Path
    path = (Path(sys.argv[1]) if len(sys.argv) > 1 else
            Path(__file__).resolve().parent.parent /
            'experimental/APP_LPM-10RX_PN1.8-pinpoint.bin')
    print(differential_audit(path.read_bytes()))
