# TX and RX firmware audit — 2026-09-19

Publication: the TX fixes below are included in
[TX PN 2.12](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/v2.12),
along with the subsequent Port FLASH status correction. RX PN 1.5 is published
as an [experimental prerelease](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/rx-v1.5)
pending device validation. This report preserves the audit-stage findings.

Seven firmware defects were reproduced and fixed: three in Ethernet Port FLASH
and shared PHY setup, two in TX power/settings handling, and two in RX sampling
and signal analysis. The resulting **TX PN 2.11 / RX PN 1.5 candidates** include
the existing PN 2.9 / PN 1.4 roadmap features. They have passed CPU emulation.
The owner subsequently reported intermittent long-on FLASH pauses on PN 2.11
and then confirmed that PN 2.12 fixes Port FLASH on the tested D-Link gigabit
switch. See the [PN 2.12 follow-up](PORT-FLASH-STATUS-2026-09-19.md).
Broader device validation remains pending.

The reported symptom is that Ethernet Port FLASH blinks a few times and stops.
The follow-up identifies PN 2.11 and a D-Link gigabit switch; its exact model
is unknown. The fixes address concrete
software defects, but a hardware trace is still needed to establish the cause
of that particular stall. This is a binary-level audit: vendor C source is not
available. Hardware and RTOS services are modeled at the boundaries described below.

## Owner follow-up — 2026-09-19

After initially reporting that the blinking issue appeared solved, the owner
reported intermittent blinking and long pauses on **PN 2.11 / D-Link gigabit
Ethernet**, with the **switch LED staying on** during the pause. The earlier
apparent success is not a sustained pass. The exact switch model, session
length and unplug/replug results were not specified. The remaining device
checks below document the validation scope of this audit.

After testing PN 2.12, the owner confirmed: "confirm fix 2.12 port blink".
Record Port FLASH as fixed on the tested setup. This confirmation does not
extend to the other TX changes or RX firmware, and does not specify the test
duration or unplug/replug results.

## Confirmed defects and fixes

| Device / severity | Defect and evidence | Correction |
|---|---|---|
| TX / high | Auto-negotiation helper `0x0801D534` reads/writes PHY register 4 with control mask `0x1200`. Actual FLASH setup changes advertisement `0x0061` to `0x1261` without requesting a control-register restart. SPEED shares this helper. | Correct the read/write selectors at `0x0801D53A` and `0x0801D5B4` to BMCR register 0. Retain the intended advertisements and other control bits. |
| TX / medium | FLASH retains the hold deadline across link loss. Link at 500 ms, loss at 1000 ms, recovery at 1500 ms produces power-down at 2000 ms: only 500 ms of recovered link. | Return to acquisition after observed loss; start a fresh minimum 1500 ms hold after reacquisition. |
| TX / medium | FLASH timestamps power operations before their completion. With injected 200 ms down / 75 ms up latency, the modeled dark interval is only 875 ms. | Timestamp after each helper returns; retain at least 1000 ms powered down before the next power-up begins. Injected latency is a regression scenario, not a device measurement. |
| TX / high | An active FLASH session makes `test_in_progress` suppress both battery-event publication and the battery UI's ADC path. Executing 1000 SysTick calls publishes no battery event; low-voltage readings are never taken. Auto-off is also held for FLASH. | Replace only the two battery busy gates, at `0x0801BD7C` and `0x0800E6BA`. Enable battery monitoring during active FLASH; retain busy suppression during setup and Length measurement. Three modeled 3000 mV readings now arm the existing 30-second countdown. |
| TX / high | Normal settings storage at `0x0800FF74` uses unchecked heap allocation. Returning NULL from the actual allocator call produces `UC_ERR_WRITE_UNMAPPED` in the following clear. Normal save, default initialization/factory reset and power-off still use this path despite Length autosave having a static buffer. | Redirect callers at `0x0800F94E`, `0x0800FE3A`, `0x08016690` to the existing checked static writer. All 204 stored bytes are verified, with scheduler serialization, erase/program/readback checks and lock/resume cleanup. No new staging RAM or allocation. |
| RX / medium | Mains analysis publishes `sampling_active=1` before clearing its shared 128-byte buffer. Preempt immediately after publication with the actual TIM5 handler: it writes sample 1234 and advances the index to 1; the resumed main loop erases that sample to 0. | Reorder the 26-byte block at `0x080086F2` so clearing completes before publishing sampling readiness. The same preemption preserves sample 1234 and index 1. No added interrupt masking. |
| RX / high | The shared DFT magnitude routine converts squared real/imaginary components to signed 32-bit integers before summing. Valid 12-bit, bin-centered waveforms with amplitude 1450–2000 counts return zero at bins 5, 6 and 17. Entire mains and analog detection routines consequently produce no beep for a strong 1800-count input. | Replace the 116-byte arithmetic tail at `0x0800B52C`: retain double precision through square/sum/square-root/scaling, converting only the final magnitude to integer. Strong signals now retain their magnitude and trigger the existing 50 ms beep. Thresholds and scaling remain unchanged. |

The PHY register interpretation follows the Linux project's primary
[MII definitions](https://github.com/torvalds/linux/blob/master/include/uapi/linux/mii.h):
BMCR is register 0, advertisement is register 4, and enable/restart is `0x1200`.
The [Port FLASH investigation](PORT-FLASH-AUDIT-2026-09-19.md) contains the
earlier PN 2.10 implementation and detailed recovery scenarios. PN 2.11 includes
all of those fixes plus the two additional TX corrections above.

## Other functions reviewed and exercised

| Function | Evidence from this pass | Practical limit |
|---|---|---|
| TX FLASH / SPEED | Execute actual vendor power, advertisement and auto-negotiation helpers; emulate only MDIO transactions. Verify control-bit preservation, FLASH 10 Mb/s advertisement and SPEED 10/100/1000 advertisement setup. Four ten-minute modeled sessions cover 0.5/4.5/12/16-second acquisition, 30-second unplug, replug, stop and re-entry. | No electrical Ethernet partner or actual negotiation state machine. The switch LED may differ from the modeled PB5 input. |
| TX digital / 825 Hz SCAN | Existing waveform, exact digital-slot timing, wrap, pause/resume, mode-switch and timer-path regressions run on the candidates. | Analog amplitude, carrier quality and real probe range are not measured. |
| TX Length / calibration | Existing four-run aggregation, partial readings, overflow formatting, calibration redraw and autosave regressions; all 65,536 raw cm values at maximum NVP and 7,776 conversion boundary vectors. | These validate software transformations, not the PHY's distance accuracy or electrical fault classifications. The vendor cross-pair filter can merge nearby pair lengths. |
| TX wiremap / QC / navigation | Full base verification exercises the existing English/Thai screen scenarios and Cable Test navigation/layout checks. Candidate changes are restricted to declared byte ranges; candidate About rendering is tested in both languages. | Wiremap electrical excitation/return paths and QC measurement accuracy are not emulated end to end. No new measurement claim. |
| TX PoE | Existing voltage/status logic checks; candidate tests verify the shared sample latch cannot be split by an interrupt and restore the prior interrupt mask. | Real supply classification, ramp behavior and voltage accuracy need bench equipment. |
| TX battery / settings / runtime | Reproduce suppressed FLASH battery monitoring and NULL-allocation fault. Exercise all three redirected save callers, existing erase/program/readback failure cleanup, deferred events, task watchdog and retained crash diagnostics. | Save failure still has no new UI notification; writes are not power-fail atomic. The watchdog proves service-task progress, not every task's health. |
| RX digital detector | Inherited clean/noisy/phase/activity/graded-strength regressions run on the new candidate, along with ADC completion and timeout handling. | Contrast scores and beep cadence are not calibrated distance or signal-strength measurements. |
| RX analog / mains | Execute the actual DFT and math runtime against an independent complex-sum reference: 162 sinusoidal cases across six bins, nine amplitudes and three phases, plus 40 seeded random window/bin pairs. Error stays within two ADC counts. Execute full analog and mains analyzers on strong signals; reproduce the TIM5 handoff race. | Synthetic ADC samples do not establish real sensitivity, noise rejection, mains detection safety or calibration. |
| RX keys / lamp / power / startup | Candidate inherits key, timer, battery recovery, idle deadline, physical power-off and watchdog checks. Boot emulator reaches ADC initialization with 64 MHz core, TIM1 about 1 kHz and TIM5 about 39.975 kHz. | Boot model skips UID/version checks and peripheral delays; it is not a full hardware boot test. Full interrupt timing and all mode-transition interleavings remain unverified. |

The strongest new coverage improvement is executing previously stubbed code:
TX PHY helpers, RX DFT math, and the RX TIM5/main-loop handoff. Passing the old
high-level models alone had not exposed those defects.

## Validation results

The final combined runs pass **75 TX tests and 28 RX tests**. These totals
include inherited behavior exercised against several profiles, not 103
independent defect reproductions.

- TX PN 2.11: **27 candidate test groups**, including all PN 2.10 and roadmap
  behavioral groups. Binary matches a deterministic rebuild; only declared
  patch ranges differ. The separate PN 2.10 suite retains its 23 groups.
- TX existing audit/roadmap tests and Thumb assembler self-tests pass. The full
  default-base `verify.py` passes, including its 61 English/Thai screen states.
  Candidate tests additionally invoke the SCAN and reliability suites.
- RX PN 1.5: **13 candidate test groups**, including existing roadmap behavioral
  groups and the new DFT/preemption regressions. Existing image/profile/roadmap
  tests also pass. The separate PN 1.2 reliability verifier passes **97 checks**.
- RX candidate remains **26152 bytes** and differs from PN 1.4 only in the two
  intended instruction ranges. Vectors, boot/device-binding logic, version
  strings, timer setup and digital detector bytes are unchanged by this stage.
- Build selectors reject incompatible profiles before loading an image. A
  custom RX audit-patch subset requires an explicit output path, preventing it
  from silently overwriting the default PN 1.0 file.

These are instruction-level tests with hardware/RTOS models, not a proof that
all firmware bugs are resolved. In particular, the RX interrupt test schedules
one concrete failing interleaving; it does not exhaust every possible schedule.

## Candidate files and reproducibility

Files are in [`LPM-10A/Firmware File/experimental`](../LPM-10A/Firmware%20File/experimental/README.md).
Published PN 2.9 / PN 1.4 images and default build profiles are preserved.

| Device | Candidate | Bytes | SHA-256 |
|---|---|---:|---|
| TX tester | `LPM-10A-TX_PN2.11-audit.bin` | 393216 | `de27a1448cc1977d00a2104abb9f48dda227e8d71c9040d986769f8e5ffe43f9` |
| RX probe | `APP_LPM-10RX_PN1.5-audit.bin` | 26152 | `6874d65549e3c67b3ad1020495effc93645e325e104eaa7697737a44c11fb0cd` |

TX About/boot text reports `PN 2.11`. RX keeps vendor-facing `3.0.0`; identify
the RX candidate by filename and hash. The existing hash-pinned vendor inputs
are required. Firmware files are specific to each device.

From `LPM-10A/Firmware File/sdk`:

```text
python build.py --audit --write
python -m unittest test_audit test_roadmap test_portflash test_firmware_audit -v
python test_thumb.py
python verify.py
```

From `LPM-10A/Firmware File/rx-sdk`:

```text
python build.py --audit --write
python -m unittest test_image test_roadmap test_firmware_audit -v
python boot_emu.py ../experimental/APP_LPM-10RX_PN1.5-audit.bin
python verify.py --reliability
```

Use `test_firmware_audit` for each new candidate. The legacy `verify.py` commands
above validate their own base/reliability profiles, not the full audit candidate.

## Device checks still needed

1. TX: confirm About `PN 2.11`; run Port FLASH on the troublesome switch for at
   least ten minutes. Unplug/replug and exit/re-enter. Observe the switch LED
   and tester independently; record the model and time/cycle of any stall.
2. TX: check SPEED against available link rates, both SCAN modes, wiremap,
   Length with known cables, and PoE with suitable test equipment. Confirm
   battery indication continues to update during FLASH.
3. TX: change and explicitly save settings, power-cycle, check retention;
   repeat for Length calibration and normal power-off saving.
4. RX: compare digital, analog and mains modes against the previous working
   image, including strong nearby and weak distant signals; exercise mode
   changes, lamp, keys, power-off and a sustained detection session.

FLASH still advertises 10 Mb/s, polls link every 500 ms and caps negotiation
retry windows at 16 seconds. A partner incompatible with those constraints
may still fail to blink. Settings still occupy one flash page and can be lost
if power fails during programming. Those limitations were retained explicitly.

The previously documented PoE "unstable supply" check also remains unresolved:
it compares byte values with 40000 and cannot trigger, while merely changing
units would make its existing window flag every supply. Its intended behavior
needs to be established before replacing it; see the
[existing formula audit](../LPM-10A/Firmware%20File/FORMULA-AUDIT.md).
