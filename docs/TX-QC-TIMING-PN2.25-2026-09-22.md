# PN2.25: QC acquisition timing correction

**Superseded by [PN2.26](TX-QC-DISPLAY-PN2.26-2026-09-22.md).** The owner
tested PN2.25 and reported a garbled screen immediately on entering QC.
That display defect is reproduced: queued connector artwork overwrites the
Init prompt. Use PN2.26, which retains the timing correction described here
and fixes the display ordering. PN2.25 remains archived for reproducibility.

The owner reports that PN2.24's QC indicators still change randomly with a
fully terminated eight-conductor cable lying stationary. Earlier reports
also described false indicators with no cable, even after Init. PN2.25 fixes
a timing defect reproduced in the actual ARM sampling and QC display paths.
Device confirmation of this candidate remains pending.

The update is
[`LPM-10A-TX_PN2.25-qc-timing.bin`](../LPM-10A/Firmware%20File/experimental/LPM-10A-TX_PN2.25-qc-timing.bin).
It retains the classic QC graphic, automatic continuous testing, changed-pin
rendering, three-reading green qualification, and PN2.24's Length fixes.

## Use after updating

1. Disconnect all cables from the tester.
2. Open QC Test and hold Right to run **Init**. Wait for it to succeed.
3. Connect the known-good eight-conductor cable. Confirm that all eight
   indicators remain green while stationary, then gently move the connector.
4. Unplug the cable and verify that all eight indicators stop showing green.

The first Init after upgrading is required: the old reference counts were
collected using the variable-duration measurement. PN2.25 rejects those old
references and saves a marker with a successful new Init, so a normal restart
does not require repeating it. Factory Reset invalidates that marker. As
before, Init must be performed with the connectors unplugged; software cannot
infer an unplugged cable reliably from these counts alone.

## Reproduction and diagnosis

The native sampler at `0x08018B84` resets TIM8, calls `vTaskDelay(10)`, and
returns the raw counter. The RTOS wait does not guarantee exactly 10 ms
between the reset and read. QC compares that raw result against a baseline
using a seven-count threshold. At a fixed modeled 100 kHz input, actual
9/10/11 ms gates produce 900/1000/1100 counts for the same physical signal.

The prior harness supplied a count independently of elapsed time. The new
`PulseHarness` derives TIM8 counts from input frequency and elapsed time,
while running the firmware's real selector, reset, reader, Init, classifier,
qualifier, queue path, and renderer. It demonstrated both reported symptoms:

| Fixed modeled input | PN2.24 | PN2.25 |
| --- | --- | --- |
| 100 kHz, 9/10/11 ms gates | 900 / 1000 / 1100 | 1000 / 1000 / 1000 |
| Init at 100 kHz; eight connected pins at 93 kHz; phased 10/11 ms gates | Rotating green/CHECK indicators | All eight remain green after qualification |
| Init at 100 kHz; still unplugged at 100 kHz; phased 9/10 ms gates | False green indicators | All eight remain OPEN |

The minimized failing command was:

```powershell
python -W ignore::ResourceWarning -m unittest test_qc_gate_timing.QCGateTiming.test_same_frequency_returns_same_count_despite_9_to_11ms_wait -q
```

Before the fix it failed with `[900, 1000, 1100] != [1000, 1000, 1000]`.
The complete connected-cable and unplugged reproductions also failed before
the fix. The tests now build PN2.25, and retain a PN2.24 negative control
that must still show changing states with identical inputs.

The ranked hypotheses were variable measurement duration, mux settling/carryover,
and pin-to-screen mapping. Controlling the measurement duration removed the
reproduced failure. Independent pin-mapping checks passed for every pin.
These are deterministic electrical/scheduler stimuli, **not captured device
waveforms**: the defect is proven in firmware, but its contribution to every
physical device symptom remains to be confirmed on the tester.

## Implementation

`sdk/qc_gate_clock.py` replaces the shared native sampler used by both Init
and live QC. It captures the existing RTOS tick plus the SysTick sub-tick
counter, accounts for a pending tick/reload, and calculates:

```text
elapsed_cycles = tick_delta * 144000 + start_VAL - end_VAL
normalized_count = round(raw_count * 1440000 / elapsed_cycles)
```

The result uses a nominal 10 ms count unit. A bounded 16-step division avoids
32-bit multiplication overflow. The original ten-tick cooperative wait remains;
no interrupt mask spans the wait or division. Masked capture sections execute
at most 55 instructions in the modeled valid paths. The exact vendor clock
setup is guarded at build time and the SysTick reload is checked at runtime.
Invalid duration, invalid clock state, counter overflow, and an already-masked
caller return the existing invalid-count sentinel, which QC displays as CHECK.

The correction uses no new peripheral or allocated RAM. It accepts 9–500 ms
measurement windows; the UI may take longer to update if scheduling itself is
delayed. It does not loosen the QC decision threshold or suppress real faults.
The snapshot assumes normal task context and at most one pending SysTick
within each short capture section. Interrupt masking or flash stalls long
enough to lose multiple SysTick events elsewhere are not reproduced by these
tests. No extra scheduler or tick configuration is introduced.

`sdk/qc_baseline_epoch.py` uses the two otherwise unused bytes at settings
offsets `C6/C7` for a version-seeded CRC16 of the 16 calibration bytes. The
parent's settings loader and autosave copy all `C8` bytes, net configuration
ends at `C4`, and Length Zero uses `C5`. A successful Init publishes baseline
and marker together before requesting the original settings save. Failed or
cancelled Init preserves the previous data. Factory Reset clears the marker.
The marker is a compact provenance check with possible 16-bit collisions;
it is not a security boundary or a guarantee against all downgrade edits.

`sdk/qc_timing.py` only accepts the exact finalized PN2.24 parent:
`b3716f6538f8980c075fb85e925cb2ba1d86e46440174d450615fa98253131e7`.
Historical builders and the published TX/RX release pair remain unchanged.

## Validation and artifact

Build from `LPM-10A/Firmware File/sdk`:

```powershell
python qc_timing.py --write
python -W ignore::ResourceWarning -m unittest test_qc_gate_timing test_qc_gate_clock test_qc_baseline_epoch test_qc_timing_build -q
```

The targeted checks cover fixed-frequency timing jitter, jittered Init,
individual conductor faults and screen mapping, unplug/replug, invalid input,
counter overflow, exact integer arithmetic, pending/reloaded SysTick, full
tick wrap, ABI/stack and interrupt restoration, baseline migration/persistence,
factory reset, container integrity and reproducibility. The pre-display-fix
SDK suite passed **458 tests in 278.134 seconds**, but lacked a full-frame
assertion for the Init prompt. The subsequent owner report exposed that gap;
the PN2.26 report records the new visual regression and its correction.

The update has 401,408 bytes, payload length `0x604E0`, and exclusive payload
end `0x0806A4E0`. It adds 508 payload bytes and zero allocated RAM bytes over
PN2.24; the padded update file size is unchanged. SHA256:

```text
b6d407b662331bf4cf2fdb4f007a595cf75c61d31fa4986dea47d23aaf3c25ae
```

The adjacent `TX-PN2.25-SHA256SUMS.txt` records the digest. This is an
experimental TX update with CPU/GUI validation; no physical pass or electrical
accuracy claim is made until the device check above is completed.
