"""Reproduce three remaining PN 1.5 issues without modifying firmware.

Run: python diagnose_pn15.py
Uses the existing Unicorn control harness; GPIO and ADC are modeled.
Assertions describe this pinned release's observed defects, not desired behavior.
"""
import hashlib
import json
from pathlib import Path
import struct

from unicorn import UC_HOOK_CODE
from unicorn.arm_const import (
    UC_ARM_REG_C1_C0_2, UC_ARM_REG_FPEXC, UC_ARM_REG_LR,
    UC_ARM_REG_PC, UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_SP,
)

from verify_control import BEEP, MODE, SP, STOP, Control
from verify_digital import ACTIVE, BUFFER, GAP, GATE, RECENT, pattern


IMAGE = Path(__file__).resolve().parent.parent / "experimental/APP_LPM-10RX_PN1.5-audit.bin"
SHA256 = "6874d65549e3c67b3ad1020495effc93645e325e104eaa7697737a44c11fb0cd"


def execute(c, entry):
    c.uc.reg_write(UC_ARM_REG_SP, SP)
    c.uc.reg_write(UC_ARM_REG_LR, STOP | 1)
    c.uc.emu_start(entry | 1, STOP, count=4_000_000)
    assert c.uc.reg_read(UC_ARM_REG_PC) == STOP
    assert c.uc.reg_read(UC_ARM_REG_SP) == SP


def mode_transition(data):
    c = Control(data)
    c.uc.reg_write(UC_ARM_REG_C1_C0_2, 0xF00000)
    c.uc.reg_write(UC_ARM_REG_FPEXC, 0x40000000)
    # A previous visit to mains mode ended after 60 samples. Another mode
    # subsequently populated the shared buffer; that old index survives.
    c.w8(MODE, 1)
    c.w8(ACTIVE, 1)
    c.w8(0x20000108, 60)
    c.uc.mem_write(BUFFER, struct.pack("<64H", *([4095] * 64)))
    c.w16(0x20000110, 6)
    c.run(0x080082B8)  # actual accepted mains-key release
    assert c.read(MODE) == 2 and c.read(0x20000108) == 60

    channels = []

    def adc(uc, addr, size, user):
        if addr == 0x080072A4:
            channels.append(uc.reg_read(UC_ARM_REG_R1))
            uc.reg_write(UC_ARM_REG_R0, 0)  # no new mains input
            uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    c.uc.hook_add(UC_HOOK_CODE, adc)
    for _ in range(5):
        # Schedule successive sample-due interrupts, omitting idle ticks.
        c.w32(0x20000100, 61)
        c.run(0x0800AC1C)
    assert channels == [7] * 4 and c.read(ACTIVE) == 0
    # Isolate analysis output from the normal 100-ms key-confirmation beep.
    c.w8(BEEP, 0)
    c.w8(GAP, 0)
    execute(c, 0x080085F4)  # actual mains analyzer and DFT/math runtime
    result = {
        "new_samples": len(channels), "new_adc_value": 0,
        "stale_samples": 60, "magnitude": c.read(0x20000058, 2),
        "analysis_beep_ms": c.read(BEEP),
    }
    assert result["magnitude"] == 437 and result["analysis_beep_ms"] == 50
    return result


def gate_reopening(data):
    c = Control(data)
    c.uc.mem_write(BUFFER, struct.pack("<48H", *pattern()))
    c.w8(ACTIVE, 0)
    c.w16(GATE, 0)
    for _ in range(100):
        c.run(0x08009E08)
        c.run(0x0800AC1C)  # real sampler also stays stopped behind the gate
    assert c.read(ACTIVE) == 0 and c.read(BEEP) == 0
    assert c.uc.mem_read(BUFFER, 96) == struct.pack("<48H", *pattern())
    c.w16(GATE, 2)
    c.run(0x08009E08)
    result = {"new_samples": 0, "beep_ms": c.read(BEEP),
              "signal_hold_ms": c.read(RECENT, 2)}
    assert result == {"new_samples": 0, "beep_ms": 30, "signal_hold_ms": 800}
    return result


def repeated_detection_cadence(data):
    results = []
    for delta in (9, 25, 60):
        c = Control(data)

        def detect():
            c.uc.mem_write(BUFFER, struct.pack("<48H", *pattern(low=500, high=500 + delta)))
            c.w8(ACTIVE, 0)
            c.w16(GATE, 2)
            c.run(0x08009E08)

        detect()
        starts, widths, start = [0], [], 0
        for tick in range(1, 1001):
            before = c.read(BEEP)
            c.run()  # actual TIM1 countdowns, one call per nominal ms
            if tick % 240 == 0:
                detect()  # completed clean window, nominal 240-ms spacing
            c.run(0x08007724)  # actual digital repeat helper
            after = c.read(BEEP)
            if before and not after:
                widths.append(tick - start)
            if not before and after:
                starts.append(tick)
                start = tick
        results.append({"contrast_delta": delta, "beep_start_ticks": starts,
                        "completed_beep_width_ticks": widths})
    assert results[0]["beep_start_ticks"][:5] == [0, 149, 240, 389, 480]
    assert results[1]["completed_beep_width_ticks"][:5] == [50, 50, 92, 50, 92]
    assert 34 in results[2]["completed_beep_width_ticks"]
    return results


def main():
    data = IMAGE.read_bytes()
    if hashlib.sha256(data).hexdigest() != SHA256:
        raise SystemExit("This diagnostic requires the exact released PN 1.5 image.")
    print(json.dumps({
        "image": IMAGE.name, "sha256": SHA256,
        "mode_transition": mode_transition(data),
        "gate_reopening": gate_reopening(data),
        "repeated_detection_cadence": repeated_detection_cadence(data),
    }, indent=2))
    print("All three PN 1.5 issues reproduced. No firmware files were changed.")


if __name__ == "__main__":
    main()
