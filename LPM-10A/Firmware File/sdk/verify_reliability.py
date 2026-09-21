"""Execute PN 2.7 reliability and PN 2.8 blind-zero fixes, including full length runs.

Hardware, link-acquisition delay and task scheduling are simulated. Arithmetic,
formatting, state machines and the PHY diagnostic control flow are real firmware.
Run directly for focused checks, or through verify.py section 24.
"""
from pathlib import Path
import struct

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB
from unicorn.arm_const import (UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6,
    UC_ARM_REG_R7, UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11,
    UC_ARM_REG_SP)
from audit_flash_length import Machine, FLAGS, PHASE, UNIT
import patches

SAVED = (UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
         UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11)


def run_checks(data, img, check):
    baseline = Path(__file__).resolve().parent.parent / "archive/LPM-10A-TX_PN2.6.bin"
    old = baseline.read_bytes()
    def flash(buf, delay, duration=90000):
        m = Machine(buf, 6)
        m.w8(FLAGS + 1, 2)
        links = []
        for t in range(0, duration + 1, 500):
            before = m.r8(PHASE)
            m.tick(t, int(m.powered and t - m.up_since >= delay))
            if before != 1 and m.r8(PHASE) == 1:
                links.append(t)
        return m, links

    for delay in (500, 1500, 3500, 4000, 4500, 6000, 8500, 12000, 16000):
        m, links = flash(data, delay)
        check(len(links) >= 2, f"FLASH link needs {delay} ms: repeated acquisitions",
              f"{len(links)} in 90 simulated seconds")
        if delay in (4500, 6000):
            _, previous = flash(old, delay)
            check(not previous and bool(links), f"PN 2.6 starvation reproduced and fixed at {delay} ms")
        if delay > 4000:
            downs = [t for t, d in m.power if d]
            # After acquisition, no extra negotiation timeout between successful blinks.
            check(all(sum(a < t < b for t in downs) == 1 for a, b in zip(links, links[1:])),
                  f"{delay} ms port: successful window retained between cycles")

    m, links = flash(data, 999999, 90000)
    downs = [t for t, d in m.power if d]
    check(not links and downs[:4] == [4000, 13000, 30000, 47000],
          "no link: bounded retries at 4, 8, 16, 16 seconds of uninterrupted power",
          str(downs))
    window = lambda: struct.unpack("<I", m.uc.mem_read(img.flash["window"], 4))[0]
    check(window() == patches.FLASH_RELINK_MAX_MS, "retry window never exceeds the 16-second cap")
    m.call(0x0800DB8C)  # real exit path
    m.w8(0x2000013C, 6)
    m.call(0x0800D47C)  # real PHY setup (screen entry precedes network setup)
    m.tick(100000, 0)
    check(window() == patches.FLASH_RELINK_MS, "exit/re-entry resets the adaptive window to 4 seconds")

    # Exact boundaries, bunched messages, and unsigned tick rollover.
    for start in (0, 0xFFFFFC00):
        m = Machine(data, 6)
        m.w8(FLAGS + 1, 2)
        tick = lambda dt, link: m.tick((start + dt) & 0xFFFFFFFF, link)
        tick(0, 1); tick(0, 1)
        for dt in (0, 0, 1250, 1499):
            tick(dt, 1)
        held = m.power == [] and m.r8(PHASE) == 1
        tick(1500, 1)
        tick(2250, 0); tick(2499, 0)
        dark = m.r8(PHASE) == 2 and len(m.power) == 1
        tick(2500, 0)
        check(held and dark and m.power == [((start + 1500) & 0xFFFFFFFF, 1),
                                          ((start + 2500) & 0xFFFFFFFF, 0)],
              f"full 1500/1000 ms phase minima with jitter and rollover (start {start:#x})")

    # Actual GUI route, both languages: stale messages do no drawing at all.
    for state in (*range(12), 255):
        m = Machine(data, state)
        calls = []
        def capture(machine):
            calls.append(1)
            machine.ret()
        m.handlers[0x080174E8] = capture
        m.handlers[0x080199B0] = capture
        m.call(0x0800F48C, 0x3D, until=0x0800F4DC)
        check(len(calls) == (3 if state == 7 else 0),
              f"queued calibration message on state {state}: " + ("two labels + result" if state == 7 else "ignored"))

    # Verify the new startup hook against poisoned arena RAM and each byte value.
    for poison in range(256):
        m = Machine(data, 2)
        m.uc.mem_write(img.batt_low_cnt - 4, bytes([poison]) * 12)
        m.call(0x0801BBAC, until=0x0801BBB0)
        result = bytes(m.uc.mem_read(img.batt_low_cnt - 4, 12))
        if result != bytes([poison]) * 4 + bytes(4) + bytes([poison]) * 4:
            break
        if m.arg(0) != 0x0800A000 or m.uc.reg_read(UC_ARM_REG_R4) != 0:
            break
    else:
        poison = None
    check(poison is None, "main startup clears only the debounce word for all 256 RAM fill patterns")
    target = lambda addr: int(next(Cs(CS_ARCH_ARM, CS_MODE_THUMB).disasm(img.read(addr, 4), addr)).op_str.lstrip("#"), 16)
    low = target(0x0800E6E2)
    m = Machine(data, 2)
    m.uc.mem_write(img.batt_low_cnt, b"\xff" * 4)
    m.call(0x0801BBAC, until=0x0801BBB0)
    m.uc.reg_write(UC_ARM_REG_R5, 3100)
    check([m.call(low) for _ in range(3)] == [0, 0, 1],
          "cold boot with low battery requires three fresh samples, even after poisoned RAM")

    # Independent reference, all u16 inputs at the highest scaling factor.
    m = Machine(data, 7)
    m.w8(0x20000D1E, 99)
    m.w8(0x20000D3D, 0)
    m.w8(UNIT, 1)
    bad = []
    for raw in range(65536):
        expected = min(65535, (raw * 99 + 34) // 69)
        actual = m.call(0x08019774, raw)
        if actual != expected:
            bad.append((raw, actual, expected))
            break
    check(not bad, "all 65,536 raw cm values at NVP 99%: monotonic, no 16-bit wrap", str(bad) if bad else "")
    cases, bad = 0, []
    for nvp in (*range(50, 100), 0, 49, 100, 255):
        m.w8(0x20000D1E, nvp)
        for zero in (0, 4, 20, 255):
            m.w8(0x20000D3D, zero)
            for raw in (0, 1, 199, 200, 201, 334, 30000, 45675, 45676, 45677, 60000, 65535):
                cm = max(0, raw - (zero * 10 if zero <= 20 else 0))
                cm = (cm * (nvp if 50 <= nvp <= 99 else 69) + 34) // 69
                for unit, value in enumerate(((cm + 5) // 10, cm, (cm * 1000 + 1524) // 3048)):
                    m.w8(UNIT, unit)
                    actual = m.call(0x08019774, raw)
                    cases += 1
                    if actual != min(65535, value):
                        bad.append((raw, nvp, zero, unit, actual, value))
    check(not bad, f"{cases} conversion vectors across NVP, Zero, units and overflow boundaries", str(bad[:2]) if bad else "")

    formatter = target(0x08019B12)
    def text_for(machine, pair, unit, value):
        machine.w8(UNIT, unit)
        machine.uc.mem_write(0x2000D000, b"1-2\0")
        for reg in SAVED:
            machine.uc.reg_write(reg, 0x11223344)
        machine.uc.reg_write(UC_ARM_REG_R4, pair)
        before = [machine.uc.reg_read(r) for r in SAVED]
        length = machine.call(formatter, 0x2000D080, 0x08019C28, 0x2000D000, value)
        text = bytes(machine.uc.mem_read(0x2000D080, 40)).split(b"\0")[0].decode()
        assert length == len(text)
        assert [machine.uc.reg_read(r) for r in SAVED] == before
        assert machine.uc.reg_read(UC_ARM_REG_SP) == 0x2000E000
        return text

    for reads in range(1, patches.AVG_RUNS + 1):
        m = Machine(data, 7)
        m.runs = [(5000,) * 4] * reads + [(0,) * 4] * (patches.AVG_RUNS - reads)
        m.call(0x080119EC)
        check(m.lengths() == [5000] * 4 and m.r8(FLAGS) == 2,
              f"complete PHY sequence: {reads}/4 valid runs retains useful mean")
        texts = [text_for(m, pair, unit, value) for pair in range(4)
                 for unit, value in enumerate((500, 5000, 1640))]
        marker = " ~ " if reads < patches.AVG_RUNS else " = "
        check(all(marker in t for t in texts), f"all four pairs / three units: {reads}/4 valid runs marked correctly",
              str(texts[:3]))

    m = Machine(data, 7)
    m.runs = [(5000,) * 4] + [(5000, 5000, 5000, 0)] * 3
    m.call(0x080119EC)
    texts = [text_for(m, pair, 1, value) for pair, value in enumerate(m.lengths())]
    check(all(" = " in t for t in texts[:3]) and " ~ " in texts[3],
          "partial indication is per pair, not applied to every row", str(texts))
    for unit in range(3):
        check(text_for(m, 3, unit, 65535) == "1-2 = OVR",
              f"overflow takes precedence over partial status, unit {unit}")
    m = Machine(data, 7)
    check([text_for(m, 0, u, 0) for u in range(3)] == ["1-2 = < 2", "1-2 = < 200", "1-2 = < 7"],
          "zero-count blind-pair text preserved; formatter return length / ABI checked on every call")
    for count in range(patches.AVG_RUNS + 1):
        for pair in range(4):
            m.w8(img.avg_acc + 16 + pair, count)
            check([text_for(m, pair, u, 0) for u in range(3)] ==
                  ["1-2 = < 2", "1-2 = < 200", "1-2 = < 7"],
                  f"blind zero never becomes a numeric zero: pair {pair}, count {count}")


if __name__ == "__main__":
    from build import STOCK, OUT
    from lpm10a.image import Image
    img = Image(STOCK)
    for p in patches.REGISTRY:
        if p.default:
            p(img)
    img.finalize()
    data = Path(OUT).read_bytes()
    assert data == bytes(img.data), "candidate differs from the current default build"
    results = []
    def check(ok, label, detail=""):
        results.append(bool(ok))
        print(f"[{'ok' if ok else 'FAIL'}] {label}" + (f": {detail}" if detail else ""))
    run_checks(data, img, check)
    print(f"{len(results)} checks; {results.count(False)} failures")
    raise SystemExit(not all(results))
