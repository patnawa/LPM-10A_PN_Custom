# TX / RX reliability audit and release validation — 2026-09-19

The function-by-function review produced TX PN 2.7 and opt-in RX PN 1.2
candidates. Both passed their CPU verifiers. After the audit, the owner reported
"Test pass on new firmware tx rx" for TX PN 2.7 / RX PN 1.2 on 2026-09-19 and
requested publication. The releases preserve those candidate binaries exactly.
This is an owner-reported general functional pass, not a detailed edge-case,
PoE-supply, range/noise or multi-revision test matrix. RX remains experimental.

This is a binary-patching project without vendor source. The coverage below
distinguishes logic emulation, unchanged-code evidence, and untested hardware.
It is not a claim that every internal routine, peripheral or timing interleaving
is bug-free. Release notes: [TX PN 2.7](releases/v2.7.md) and
[RX PN 1.2](releases/rx-v1.2.md).

## Reproduced defects and changes

| Area | Evidence before | Candidate change and boundary |
|---|---|---|
| TX FLASH negotiation | PN 2.6 acquires no link on simulated ports requiring 4.5 or 6 seconds because it power-cycles every 4 seconds | Failed waits increase 4 → 8 → 16 seconds; retain the working window within the session. Tests cover repeated links requiring 0.5–16 seconds. Ports needing longer, or rejecting 10 Mb/s advertisement, can still fail. |
| TX FLASH phase timing | Queued/jittered messages could shorten nominal 1500/1000 ms phases to 1250/750 ms | Full elapsed-time thresholds, tested immediately before/at boundaries and across tick rollover. Dispatch delays can lengthen, not shorten, those software intervals. |
| TX length confidence | One successful 50 m reading plus three zero runs appeared as an ordinary `= 50.0` result | Preserve the useful average but display `~ 50.0` for a pair with 1–3 successful runs out of 4. For a nonzero numeric mean, `=` means all four produced a nonzero value, not proof of accuracy or stability. Blind/overflow labels are separate cases. No numeric policy or cross-pair filter changes. |
| TX length overflow | Raw 45677 cm, NVP 99%, centimetre mode wrapped calibrated 65537 cm to 1 cm | Saturate the display return at reserved `0xFFFF` and print `OVR`. Metre/foot representations remain usable when they fit. This is a representation limit, not raw PHY-status validation or a new measurement-range claim. |
| TX calibration GUI | Queued message 0x3D drew NVP/Zero on Home | Guard both calibration and result draw calls with the current Length screen state. All other defined states plus invalid state 255 ignore the message. |
| TX low-battery startup | Debounce counter in uninitialised arena RAM could arm on the first low sample | Clear its word at main entry, before tasks start; replay displaced vector-base and r4 initialisation. Every byte-fill pattern tested, adjacent words unchanged, then three fresh low samples required. |
| RX auto-off | Timer tested idle ≥300001 before consuming a nonzero signal/key keepalive; existing activity could lose on the deadline tick | In-place 36-byte replacement skips idle shutdown when that existing byte is nonzero. Downstream decrement/reset logic, idle threshold, physical power key and low-battery protection are preserved. |
| RX patch tooling | Range reads could silently truncate; an unterminated string raised an incidental IndexError; save lacked an image-size guard | Validate complete ranges, reject unterminated strings, and reject resized images before opening the output file. Five synthetic regression tests. |

The RX correction only honors activity already recorded when the IRQ checks it.
It does not guarantee acceptance of a physical key or signal first discovered
later in that same interrupt, or of every possible interrupt interleaving.

## Function-by-function coverage

| Function family | Evidence in this audit | What still requires hardware / deeper work |
|---|---|---|
| TX boot, Home, language, About | Startup hook replay and write ownership; version/container checks; all 61 UI states in Thai and English | Bootloader acceptance on this unit and other revisions; full reset/peripheral startup is not emulated |
| TX Cable Test / Switch / Far end | Back routing, selector/results/error layouts and all-language regression | Real cable pin maps, shorts, opens, crossed pairs and remote identification across wiring faults |
| TX digital SCAN | 8001 generator calls, wrap/boundary counters, exact 50-tick slots, pause/resume and mode changes; full timer path | Oscilloscope waveform, range and coupling in bundles |
| TX analog SCAN | 6001 calls match the previous waveform; pause/resume and timer logging checks | Actual carrier/envelope frequency and reception under interference |
| TX FLASH | Actual message handler, PHY helper/setup/exit, adaptive waits, phase bounds, stale messages, tick rollover | Multiple fast/slow switches; missed PHY writes and task scheduling are modeled, not measured |
| TX Length / units / NVP / Zero | Complete four-run diagnostic with fake PHY registers; 65,536 raw values at NVP 99%; 7,776 calibration/unit boundary vectors; actual sprintf, partial/overflow markers, cancellation and timeout audit | Known cable lengths, physical unplug/replug, damaged pairs, measurement calibration and raw PHY error/status limits |
| TX QC Test | Existing UI and Back routing regressions, declared-byte/disassembly audit | QC electrical negotiation, loads and voltage accuracy; not functionally emulated in this pass |
| TX Speed | Existing UI and Back routing regressions, no unintended code edits | Real 10/100/1000 negotiation, partner advertisements and link fault handling |
| TX PoE | Live-refresh/timeout state machine, sample latch, loss of supply and redraw tests | Standard/passive supplies; classification threshold and preemption during latch copying remain open |
| TX settings / battery / auto-off | Defaults/reset, remembered calibration/units, settings buffer free paths, gauge/debounce/recovery, new startup reset, SCAN/FLASH auto-off hold | Flash wear/power-loss persistence, charging/test sampling gaps and low-voltage bench tests |
| RX digital detection | Original 41 checks rerun; bounded bit errors, phases, seeded noise, drift model, stack/ABI and sampler ownership | Real range, weak signals, adjacent-cable rejection and calibrated contrast threshold |
| RX analog / mains | Detector and sampler bytes unchanged from PN 1.1; mode selection and exits CPU-tested | Frequency/sensitivity calibration, false alarms and electrical safety; no new functional DFT sweep in this pass |
| RX keys / lamp / power | Actual key routine with 0/1/5/6/100 held scans for each key, release debounce/no repeats, mode cycling; 1200-tick power hold | Physical contacts, LEDs, lamp driver and power latch modeled |
| RX battery / timing | Existing critical-recovery tests; actual TIM1 handler over 1000 ticks, two battery/gain/watchdog calls, pending-interrupt guard and auto-off boundaries | ADC electrical behavior and preemption; interrupt watchdog still cannot detect a stalled main loop |
| RX boot / clocks / binding | Boot model reaches ADC init with original clock/timer programming; vectors, UID-binding and version routines unchanged | Binding and version checks are skipped by the boot model, not validated by it; never modified |

## Validation completed

TX: full `verify.py` passed, including all 61 screen states in each language,
39 SCAN checks and 51 added reliability checks. Twelve existing audit tests and
the Thumb assembler self-test also pass. The focused reliability suite exercises
65,536 maximum-NVP conversion inputs plus 7,776 calibration/unit boundary cases.

RX: PN 1.2 passes 97 checks (41 existing plus 56 control/power checks). PN 1.1's
41 checks and PN 1.0's default verifier remain separate, preserving reproducibility.
Five new image-boundary tests pass. The new RX image differs from PN 1.1 only in
the declared 36-byte auto-off block; no image growth or extra persistent RAM.

Tests run firmware instructions in Unicorn, with stubbed hardware/RTOS calls.
They do not model the entire scheduler, RF/analog front end, electrical faults,
flash power loss, or worst-case wall-clock ISR latency.

## Remaining priorities, not hidden by a passing verifier

- TX task-level queue calls still occur in interrupt paths outside the SCAN
  fixes. The timer-fed watchdog does not prove task health. RX likewise feeds
  its watchdog from TIM1, not a main-loop health check.
- TX battery sampling can pause during charging/tests. Startup initialisation
  does not establish uninterrupted voltage monitoring or fix every sample gap.
- The vendor length filter still merges nearby pairs: 50/50/50/48 m becomes
  49.5 m on all pairs. Partial markers do not restore independent measurements,
  show variance, or validate physical continuity after the last acquisition.
- Raw out-of-range PHY values are not rejected against an established hardware
  status/range contract. `OVR` fixes arithmetic wrap only. `< 2 m` denotes a
  retained zero, not a validated fault location.
- PoE classification's ineffective byte-spread threshold and shared redraw/latch
  concurrency need a separate hardware-backed change.
- RX ADC reads do not wait for conversion completion; TIM1 can preempt the
  signal sampler with battery/gain conversions. No sampler or IRQ-priority
  redesign was attempted without bench evidence.
- UI-only coverage for QC and Speed must not be mistaken for successful
  electrical/protocol tests. Broad functionality improvements here need traces
  from the device, compatible supplies, known cables and link partners.

## Release images and reproduction

| Device | File | Size | SHA-256 |
|---|---|---:|---|
| TX | `LPM-10A-TX_PN2.7.bin` | 393216 | `2c14ed7be027cb3476896883e13eefb08cf953eb98993c56c100517f7c421360` |
| RX | `APP_LPM-10RX_PN1.2-reliability-experimental.bin` | 26152 | `8176a40988eea3319c5c46dd65b0c97dce16c420b2e7fcbb3ddb05b28feef879` |

Run from `LPM-10A/Firmware File/sdk`:

```text
python -m unittest test_audit -v
python test_thumb.py
python build.py --write
python verify.py
python verify_reliability.py
python audit_flash_length.py ../LPM-10A-TX_PN2.7.bin
```

Run from `LPM-10A/Firmware File/rx-sdk`:

```text
python -m unittest test_image -v
python build.py --only batt-critical-recover,digital-correlation,activity-before-autooff --write
python verify.py --reliability
python verify.py --digital
python verify.py
python boot_emu.py ../APP_LPM-10RX_PN1.2-reliability-experimental.bin
```

## Detailed bench follow-up

The general owner pass does not enumerate these individual checks; keep this
list for reproducible regression, calibration and compatibility testing.

1. Keep the previously working TX PN 2.6 and RX PN 1.1 files. Confirm the correct
   device/update mode and matching recovery image before flashing either candidate.
2. TX: boot, both languages, settings save/reboot/reset, short/long cable tests,
   all units and calibration, unplug during each averaging run (look for `~`),
   leave Length while changing calibration, scan both modes and pause/resume.
3. FLASH: several switches, at least one slower link partner, 10-minute session,
   unplug/replug, exit/re-entry; check both the port and tester indications.
4. Recheck Speed, QC and PoE using suitable equipment. These were not physically
   exercised by this audit. Confirm voltages against a trusted meter.
5. TX battery: cold boot, charger transitions and repeated low/recovery episodes.
   RX: both trace modes, mains mode only with suitable safe test equipment,
   lamp, mode transitions, idle auto-off, active-tone keepalive, physical power
   key and battery recovery. Compare range/noise against PN 1.1.
