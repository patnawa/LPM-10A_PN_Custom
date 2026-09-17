"""
Patch set for the LPM-10A receiver firmware V3.0.0.

Same conventions as the transmitter SDK: each patch declares every byte it
touches (stock bytes and new bytes), and verify.py checks the built image
against that record byte for byte before it runs the behavioural checks.

risk levels
    safe      byte-for-byte reversible edit, verified by disassembly+emulation
    low       behavioural change, verified by emulation, semantics well understood
    untested  needs a real device to confirm; not in the default build
"""
from lpm10rx.image import PatchError   # noqa: F401

REGISTRY = []


def patch(pid, title, risk, default=True, group="misc"):
    def deco(fn):
        fn.pid, fn.title, fn.risk, fn.default, fn.group = pid, title, risk, default, group
        REGISTRY.append(fn)
        return fn
    return deco


# =====================================================================
# Group: correctness fixes
# =====================================================================

@patch("batt-critical-recover", "Critical-battery shutdown recovers if the voltage comes back",
       risk="low", group="bugfix")
def p_batt_recover(img):
    """
    battery_500ms (0x08007770) runs every 500 ms (TIM1 tick 500): trimmed
    mean of five ADC samples, mV = raw * 6600 / 4096, then a three-state
    machine kept in batt_state (0x20000056):

        0 ok        -> 1 when mV <= 3579  (low-battery LED on)
        1 low       -> 0 when mV >= 3621, -> 2 when mV <  3280
        2 critical  -> counts readings in batt_crit_count (0x20000057);
                       power_off at 5 (2.5 s).  Nothing ever leaves state 2.

    So one reading below 3280 mV -- a beep burst is exactly the load that
    dips a tired cell for one reading -- starts a 2.5 s countdown that no
    recovery can stop.

    Fix, in place (the stock block is 30 bytes, so is the new one):

        state 2:  if mV >= 3400 -> jump to the existing "state = 1, count = 0"
                  code at 0x080077F2, which then falls through the normal
                  state-1 handling (LED, hysteresis checks) and the epilogue;
                  else count++ (as a byte, like stock) and power_off at 5.

    The counter therefore only reaches 5 after five consecutive readings
    (2.5 s) below 3400 mV, with 120 mV of hysteresis above the 3280 mV
    entry.  The ADC grid is 1.6 mV, so the first reading that recovers is
    raw 2111 = 3401 mV; 3400 itself is not a representable value.

    Register facts the patch relies on (verified in verify.py):
      * r4 == 0x2000004A (batt_samples) for the whole function, so
        batt_crit_count is [r4, #0xD] and needs no 8-byte address load;
      * mV is the u16 at [sp, #4], as the stock state-1 code also reads it;
      * the block is entered only from `cmp state,#2 / bne`, so no other
        branch lands inside it.
    """
    site = 0x08007880
    code = img.assemble_at(site, """
            mov  r1, sp
            ldrh r0, [r1, #4]        ; mV
            movw r1, #3400
            cmp  r0, r1
            bhs  0x080077F2          ; recovered: state = 1, count = 0 (stock code)
            ldrb r1, [r4, #0xD]      ; batt_crit_count
            adds r1, #1
            uxtb r1, r1              ; byte counter, wraps like stock
            strb r1, [r4, #0xD]
            cmp  r1, #5
            blt  0x080078AC          ; not yet: epilogue
            bl   power_off
            b    0x080078AC
    """)
    assert len(code) == 30, len(code)
    img.poke(site,
             "40f25700 c2f20000 0178 0131 0170 0078 0528 03db ffe7 fff76bfe ffe7 06e0",
             code, "critical battery: recover above 3400 mV, else count to 5 as stock")
