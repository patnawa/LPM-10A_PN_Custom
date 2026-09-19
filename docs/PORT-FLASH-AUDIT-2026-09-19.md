# Port FLASH bug hunt — PN 2.10 candidate, 2026-09-19

This report covers the initial Port FLASH stage. The subsequent
[full TX/RX audit](FULL-FIRMWARE-AUDIT-2026-09-19.md) incorporates these fixes in
TX PN 2.11 and adds TX battery/settings and RX PN 1.5 sampling/math corrections.

The owner reports that Ethernet Port FLASH blinks a few times and then stops.
Three defects were reproduced in the released PN 2.9 firmware and corrected in
an opt-in **PN 2.10 Port FLASH candidate**. They affect PHY setup and recovery,
but no hardware trace establishes which defect causes the owner's particular
stall. The installed version and switch model were not provided.

The new image includes all PN 2.9 roadmap features. The PN 2.9 release, default
build, RX firmware, bootloader-facing name, and container file size are unchanged.
The candidate has passed CPU emulation; it has not yet been tested on a device.

## Reproduced findings

| Severity | Finding | Reproduction and correction |
|---|---|---|
| High | Auto-negotiation writes the wrong PHY register | The helper at `0x0801D534` reads register **4** and writes `value OR 0x1200` back to register **4**. The mask belongs to BMCR, register **0**. The FLASH setup changes the intended advertisement `0x0061` to `0x1261`, without requesting a BMCR restart. Correct both `movs r0,#4` selectors at `0x0801D53A` and `0x0801D5B4` to register 0. Preserve masks, ABI, and unrelated bits. The shared SPEED setup also receives this correction. |
| Medium | A lost link retains its old hold deadline | Link first observed at 500 ms, lost at 1000 ms, and observed again at 1500 ms: PN 2.9 powers down at 2000 ms, giving the recovered link only **500 ms**. The candidate returns to link acquisition on observed loss and starts a fresh 1500 ms hold on recovery. |
| Medium | Power-call latency shortens the dark interval | Inject a 200 ms delay into power-down and a 75 ms delay into power-up. PN 2.9 completes down at 2200 ms and up at 3075 ms: **875 ms** powered down. The candidate timestamps after each power operation returns and does not begin the next power-up before 3200 ms. This models task preemption/MDIO/logging latency; the delays are not measured device timings. |

Register semantics are independently supported by the Linux project's
[MII register definitions](https://github.com/torvalds/linux/blob/master/include/uapi/linux/mii.h):
BMCR is 0, advertisement is 4, and the enable/restart control mask is `0x1200`.
In advertisement, those bits have different meanings. The
[Motorcomm PHY driver](https://github.com/torvalds/linux/blob/master/drivers/net/phy/motorcomm.c)
uses the standard MII framework for YT8531. This identifies a software error;
it does not prove how this particular switch responds to the erroneous advertisement.

The previous FLASH emulator intercepted the complete power, speed-advertisement,
and auto-negotiation helpers. Timing tests therefore passed even though the
auto-negotiation helper addressed the wrong register. The new `PhyMachine`
executes those helper instructions and models only the underlying MDIO reads
and writes. It makes the distinction between a blink-state test and a PHY-setup
test explicit.

## Implementation

`sdk/portflash.py` registers `portflash-recovery`, an opt-in patch requiring
`flash-blink` and `version-string`. `build.py --portflash` selects the existing
roadmap profile plus that patch. It reports `PN 2.10` in About and the boot log.

The candidate replaces the FLASH message-8 call target with a new handler in
the unused tail of the existing container. It reuses the previous eight-byte
FLASH timer allocation, preserves callee-saved registers and stack alignment,
and retains the state/active-session guards, 500 ms polling, 4/8/16-second
retry backoff, and 1000 ms dark interval. It does not change interrupt masking
or add an MDIO reader in the separate indicator task.

Compared with released PN 2.9, differences are restricted to the two register
selectors, the FLASH call target, two version strings, appended handler bytes,
and payload-length fields. A test checks every changed byte against those
ranges and pins the preceding image to its published SHA-256.

## Verification

- **23 candidate test groups pass**, including the 13 inherited roadmap groups.
  The new tests reproduce all three defects on PN 2.9 and verify the corrections.
- Actual auto-negotiation helper: enable and disable with three initial BMCR
  values; correct register, expected control bits, advertisement unchanged.
- Actual FLASH setup: 10 Mb/s advertisement retained, gigabit full-duplex
  advertisement cleared, BMCR restart requested, PHY powered up. Actual shared
  SPEED setup retains 10/100/1000 advertisements and requests the proper restart.
- Four **10-minute simulated sessions** use 0.5, 4.5, 12 and 16-second link
  acquisition delays, a 30-second cable disconnection, replug, stop, stale
  message and re-entry. All continue acquiring links after replug.
- Focused reliability checks also run on the candidate: bounded retry backoff,
  no-link behavior, phase minima, rollover, calibration/formatting, all 65,536
  raw cm values at maximum NVP, and 7,776 conversion boundary vectors.
- The SCAN suite runs on the candidate. Its TIM2 byte comparison uses released
  PN 2.9 because that profile intentionally redirects the watchdog call;
  heartbeat behavior remains covered by inherited roadmap tests.
- All **25 existing TX audit/roadmap tests**, the Thumb assembler suite and the
  complete base `verify.py` pass, including the base English/Thai screen checks.
- All **14 existing RX image/roadmap tests** pass. RX bytes were not changed.

These tests execute firmware instructions with modeled hardware and RTOS
services. They are not a full preemptive scheduler, electrical Ethernet test,
or proof that the switch's LED follows the modeled GPIO.

## Remaining limitations and broader review

These are known limits retained after this pass, not newly claimed fixes:

| Area | Remaining limitation |
|---|---|
| Port compatibility | FLASH retains the existing 10 Mb/s setup. A partner rejecting that mode may never link. No new speed fallback was introduced. |
| Slow links | The bounded retry window still caps at 16 seconds. A partner requiring longer uninterrupted acquisition can remain starved. |
| Link feedback | Link decisions still sample PB5 every 500 ms. A dropout between samples can be missed; electrical pin behavior and MDIO integrity require device measurements. |
| Indicator | The separate vendor indicator task still delays and displays its sampled GPIO value. Screen/LED timing is not an authoritative trace of switch link status. |
| Runtime health | The TX watchdog proves service-task progress, not every task's health. |
| Length | The vendor cross-pair filter can merge close pair lengths; passing numeric tests does not validate raw PHY fault classifications or short-cable accuracy. |
| Settings | Calibration saving uses one flash page; interruption during erase/program is not power-fail atomic. |
| PoE / RX ADC | Existing emulation covers logic and ADC completion handling, not supply classification accuracy, analog noise, or worst-case peripheral/interrupt latency. |

## Build and device follow-up

From `LPM-10A/Firmware File/sdk`:

```text
python build.py --portflash --write
python -m unittest test_portflash -v
python -m unittest test_audit test_roadmap -v
python test_thumb.py
python verify.py
```

Use `test_portflash` for the candidate. The legacy `verify.py` intentionally
expects the default base image; passing a roadmap/portflash image to it is not
the profile's verification workflow.

Candidate: `experimental/LPM-10A-TX_PN2.10-portflash.bin`, **393216 bytes**.
SHA-256: `cedadd7057b46ae6a8153ae1a479d4f81cd49fcc53ae92033a083faed4ab76db`.

Test on the same switch and cable that stop blinking: confirm About says
`PN 2.10`, run FLASH for at least 10 minutes, disconnect/reconnect the cable,
then exit/re-enter FLASH. Observe the switch port and tester separately.
Also check SPEED at 10/100/1000 where available because its setup shares the
corrected helper. Record the switch model, time/cycle at any stall, and whether
the switch LED remains on or off. Those observations determine the next
hardware investigation if this candidate still stops.
