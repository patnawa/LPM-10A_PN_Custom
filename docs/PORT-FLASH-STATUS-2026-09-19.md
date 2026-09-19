# Port FLASH intermittent long-on follow-up — PN 2.12

The owner reports that **PN 2.11 on a D-Link gigabit Ethernet switch** sometimes
blinks normally and sometimes pauses for a long time, with the **switch LED
remaining on**. This supersedes the earlier preliminary report that the issue
appeared solved. The exact switch model and pause duration remain unknown.

PN 2.12 is a TX-only release. It reads the PHY's link-status register
for blink decisions and makes the tester's indicator use the same result.
It includes the PN 2.11 battery/settings fixes. The RX candidate is unchanged.
The [published release](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/v2.12)
preserves the exact tested binary and checksum below.

**Owner confirmation — 2026-09-19:** "confirm fix 2.12 port blink".
The owner confirms that PN 2.12 fixes the reported Port FLASH problem on the
D-Link gigabit switch. This records a successful device result for this
function; the exact switch model, test duration and unplug/replug results were
not specified. Other TX/RX functions retain their separate validation status.

## Reproduction and interpretation

PN 2.11 reads GPIO PB5 both when acquiring a link and while holding it. Any
low sample during the hold returns to acquisition; the next high sample starts
the full 1500 ms hold again. A repeating sampled pattern of high/high/low can
therefore restart the timer indefinitely, without ever reaching power-down.
Even a single misleading sample can lengthen a cycle.

The new regression separates PHY link from GPIO input. With PHY link remaining
up whenever powered, inject that GPIO pattern for ten simulated minutes:

| Firmware | Result |
|---|---|
| PN 2.11 | No deliberate power-down after setup; the link stays on. |
| PN 2.12 | Repeated deliberate power-downs, 3000 ms apart in this instant-relink model. |

This confirms an input-dependent state-machine stall. **It does not prove that
PB5 has this waveform on the owner's board.** The steady switch LED is consistent
with an established link and a delayed deliberate drop, but GPIO/MDIO traces
would be needed to prove the hardware cause. Actual blink intervals include
switch negotiation time; the simulated three-second cycle is not a speed claim.

## Change

- Read standard MII BMSR register 1 twice and use bit 2 from the second read.
  Link status is latched low, so the first read clears a historical drop and
  the second samples the current state. Reject `0xFFFF` on either read, since
  the vendor MDIO helper has no separate error result.
- Replace only the two GPIO-read call targets inside the PN 2.10/2.11 FLASH
  controller. Hold/off durations, negotiation backoff and advertisement stay
  as before. Real observed link loss still starts a fresh hold on recovery.
- Replace the indicator task's GPIO-read call at `0x0800DC6C` with a read of
  the net task's published phase. The indicator task performs no MDIO access,
  avoiding a second task using the bit-banged bus concurrently.
- Add 60 bytes of code, no persistent RAM and no container-size growth.
  About and boot text identify the build as `PN 2.12`.

The register semantics and latch handling follow the primary Linux
[PHY link-status implementation](https://linux.googlesource.com/linux/kernel/git/torvalds/linux/+/2b414a95b8f7307d42173ba9e580d6d3e2bcbfce/drivers/net/phy/phy_device.c).
This candidate deliberately polls current status; sub-poll link interruptions
can still be missed. Repeated MDIO errors or a stalled network task are separate
failure modes and are not claimed resolved by this change.

## Validation

**34 candidate test groups pass**, including all inherited TX audit tests:

- Ten-minute steady-link/GPIO-pulse reproduction, plus stuck-high/stuck-low GPIO.
- Historical latch-low reads, real current link-down, all-ones MDIO responses,
  recovery after an intermittent read error, register/stack preservation.
- Actual indicator call uses the published phase without GPIO or MDIO calls.
- No PHY polling when stopped, on another screen or during the off interval.
- Existing ten-minute slow-negotiation/unplug/replug sessions, rollover,
  minimum hold/off timing, shared SPEED setup, SCAN, battery, settings and
  runtime regressions.
- Exact rebuilt-file identity and byte-range comparison against the pinned
  PN 2.11 SHA-256. Earlier candidate files remain reproducible.

The combined TX profile run passes **109 tests**, and the full default-base
`verify.py` reports **ALL CHECKS PASSED** after the MDIO model update. These
totals include inherited checks repeated against different profiles.

The hardware model supplies MDIO values; the tests do not electrically emulate
the D-Link switch. The separate owner report above confirms the Port FLASH fix
on the tested setup, without establishing the precise GPIO waveform or universal
switch compatibility.

## Build and device check

From `LPM-10A/Firmware File/sdk`:

```text
python build.py --portflash-status --write
python -m unittest test_portflash_status -v
python -m unittest test_audit test_roadmap test_portflash test_firmware_audit -v
```

File: `experimental/LPM-10A-TX_PN2.12-portflash-status.bin`, **393216 bytes**.
SHA-256: `3d2db80f8288744191fe1ddb2855a83b900166dd365e1583c6270dfb460a0076`.
Use the [TX device notes](../LPM-10A/Firmware%20File/experimental/PN2.12-PORTFLASH-STATUS-README.txt).

Confirm About shows PN 2.12 and repeat FLASH on the same switch port and cable
for at least ten minutes. Watch for a switch LED that stays on for a long time;
also unplug/replug and exit/re-enter. If it still happens, the pause duration,
exact D-Link model and whether the tester indicator stays on at the same time
will distinguish the next investigation. RX does not need reflashing for this test.

The existing 10 Mb/s advertisement, 500 ms status polling and 4/8/16-second
retry windows remain. A slow link can still produce long **off** gaps, and
real link instability can extend the hold; this is not fixed-frequency blinking.
