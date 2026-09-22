# LPM-10A receiver (probe) firmware SDK

**Current release: PN 1.23.** `python build.py --write` builds the latest profile
and its update container. `python verify_release.py` verifies the published
current update against an exact rebuild; pass an image path and `--profile pn1.xx`
to check another registered profile. The older `verify.py` models historical
PN 1.0–1.2 behavior. The version notes below are historical.

**Digital gain continuity candidate (2026-09-22):**
`python digital_gain_continuity.py --write` builds **PN1.23G**, its RX update
container and checksums in `experimental/`. It addresses the owner's PN1.23F
report of Digital audio dropouts while moving the probe or turning the knob
under strong input. The reproduced quiet gap falls from 238 ms to 28–37 ms.
Already-confirmed feedback keeps its existing deadline while all samples are
reacquired; gain changes cannot renew it. Analog/Mains retain their behavior.
CPU-tested; the owner confirmed the Digital dropout is fixed on the device
on 2026-09-22. The timing figures above are emulator measurements. See the
[diagnosis, measurements and firmware](../../../docs/RX-DIGITAL-GAIN-PN1.23G-2026-09-22.md).
Run `python -m unittest test_rx_digital_strong_gain test_rx_digital_gain_continuity test_digital_gain_build -q`.
The default release profile remains PN 1.23.

**Earlier audit experiment (2026-09-22):** `python auto_range_freshness.py` dry-builds
`PN1.23F` in memory. It invalidates stale sample windows before a gain change
and prevents mains amplitude from controlling the cable-tracing gain. Run
`python -m unittest test_rx_auto_range_freshness -v` for the CPU regressions.
The owner reports Digital motion/knob dropouts on this candidate; PN1.23G above
adds continuity while retaining its ownership correction. It is not a release profile. The module's
`build_candidate()` returns the distinctively tagged image without writing files.

The [deep audit](../../../docs/DEEP-AUDIT-2026-09-22.md) records the reproductions,
tooling corrections, validation scope and next functional work.

**PN 1.13 audio-clock test candidate:** `python build.py --audio-clock --write`
builds [APP_LPM-10RX_PN1.13-audio-clock.bin](../experimental/APP_LPM-10RX_PN1.13-audio-clock.bin).
Moves the shared BEEP/GAP countdowns to TIM5, which already generates speaker
output; TIM1 retains the other counters. This addresses a pulse stretching when
TIM1 delivery is delayed while TIM5 still runs. Detection and strength mapping
stay byte-identical to PN 1.12. No new RAM is allocated. The actual cause of the
owner's approximately one-second Digital/key sound is not established. The
owner tried PN 1.13 and reports the symptom is unchanged. Keep TX PN 2.14; see the
[candidate report](../../../docs/TONE-AUDIO-CLOCK-PN1.13-PN2.14-2026-09-20.md).

The supplied clip now establishes a train of short pulses after TX Digital →
Analog. Its approximately 50 ms cadence differs from the expected PN 1.13
normal pulse, so installed-image identity is under investigation. See the
[clip analysis](../../../docs/TONE-CLIP-DIAGNOSIS-2026-09-20.md).

`python identity_marker.py --write` builds the separate, temporary PN 1.13
startup lamp diagnostic from the exact existing artifact. Without `--write`
it is a dry run. This one-byte identity check does not alter normal build
profiles; see [scope and verification](../../../docs/RX-IDENTITY-MARKER-PN1.13-2026-09-20.md).

**PN 1.12 local overload candidate:** `python build.py --overload --write` builds
[APP_LPM-10RX_PN1.12-overload.bin](../experimental/APP_LPM-10RX_PN1.12-overload.bin).
Includes the exact PN 1.11 profile, then marks Digital exact fallback uncertain
when all newest 16 raw ADC readings equal 4095. Lower-zero and brief-contact
behavior remain unchanged. The prior `--tracking` output stays byte-identical.
See the [PN 1.12 report](../../../docs/TONE-OVERLOAD-PN1.12-PN2.14-2026-09-20.md).
The owner confirms RX PN 1.12 / TX PN 2.14: both modes receive and sweeping is
more accurate. Later feedback reports Digital sound continuing about one second
after moving away or pressing TX Pause; Analog has no such delay. Digital release
latency remains an open device issue.
See [owner feedback](../../../docs/TONE-DEVICE-FEEDBACK-2026-09-20.md).

**PN 1.11 local tracking candidate:** `python build.py --tracking --write` builds
[APP_LPM-10RX_PN1.11-tracking.bin](../experimental/APP_LPM-10RX_PN1.11-tracking.bin).
Based on exact PN 1.9, it adds robust local B6 acquisition with legacy fallback,
32 retained / 16 new sample overlap, recent strength, interpolated short Analog
feedback and bit-exact integer DFT. It omits Sync32. No image growth, new gain
setting or persistent RAM allocation. Run `python -m unittest discover -p "test_*.py" -q`.
See the [paired report and limitations](../../../docs/TONE-TRACKING-PN1.11-PN2.14-2026-09-20.md).
Device validation is pending; Fluke comparison has not been run.

**PN 1.10 status after device feedback:** the owner confirms Digital/Analog
receive correctly, but Sync32 remains silent in digital mode. TX PN 2.14
therefore removes Sync32 and Pulse test from its menu. The installed RX PN 1.10
can keep receiving the established waveforms; no RX update is needed for that
TX change. See the [follow-up](../../../docs/TONE-RECOVERY-PN2.14-2026-09-20.md).

**PN 1.10 historical paired tracing implementation:** `python build.py --sync --write`
adds automatic Sync32 recognition to the existing digital mode while retaining
legacy recognition and PN 1.9 median-based feedback. Original TX Digital
remains compatible. Run
`python -m unittest test_rx_sync test_sync_profile test_scan_pair -q` after
building both candidates. See the
[paired report and timing limits](../../../docs/SCAN-SYNC-PN2.13-PN1.10-2026-09-20.md).
The Sync32 implementation is retained for investigation, not recommended for
tracing after the reported hardware failure.

**PN 1.9 robust local experimental candidate:** `python build.py --robust --write`
builds [APP_LPM-10RX_PN1.9-robust.bin](../experimental/APP_LPM-10RX_PN1.9-robust.bin).
It estimates strength using medians grouped by the expected digital code,
improving cable-strength ranking in synthetic impulse tests. Existing digital
detection and sampling remain unchanged. A valid code with an upper-rail-dominated
or inseparable strength estimate gives distinct 100 ms pulses with 160 ms quiet
gaps; normal feedback retains 30 ms pulses. Run
`python -m unittest test_rx_robust test_robust_profile -v`. See
[device notes](../experimental/RX-PN1.9-ROBUST-README.txt),
[checksum](../experimental/RX-ROBUST-SHA256SUMS.txt), and the
[implementation report](../../../docs/RX-ROBUST-PN1.9-2026-09-20.md).
This candidate has not been published or flashed; hardware validation is pending.
PN 1.8 remains the current owner-tested experimental prerelease.

**Current owner-tested PN 1.8 pinpoint experimental prerelease:** `python build.py --pinpoint --write` builds
`../experimental/APP_LPM-10RX_PN1.8-pinpoint.bin`. It adds finer digital beep
intervals across a wider strength range, with a small deadband to reduce jitter.
Signal eligibility, sampling and PN 1.7 release behavior remain unchanged.
Run `python -m unittest test_rx_pinpoint -v`. See the
[implementation report](../../../docs/RX-PINPOINT-PN1.8-2026-09-19.md).
The owner reports a PN 1.8 device test pass on 2026-09-19. Quantitative
cable-selection measurements were not supplied; PN 1.7 is preserved.
Download the [RX PN 1.8 prerelease](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/rx-v1.8).

**Previous PN 1.7 precision experimental prerelease:** `python build.py --precision --write` builds
`../experimental/APP_LPM-10RX_PN1.7-precision.bin`. Its existing digital mode
adds robust strength grading, five beep levels, hysteresis and faster release
for comparing cables in a bundle. Includes PN 1.6; earlier profiles remain
available. Run `python -m unittest test_rx_precision -v`. See the
[implementation and validation report](../../../docs/RX-PRECISION-PN1.7-2026-09-19.md).
The owner reports a device test pass on 2026-09-19. Threshold calibration and
quantitative cable-selection measurements remain undocumented.
Download the [RX PN 1.7 prerelease](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/rx-v1.7).

**PN 1.6 local candidate:** `python build.py --followup --write` builds
`../experimental/APP_LPM-10RX_PN1.6-followup.bin`. It includes PN 1.5 plus fresh
sample ownership across mode/gate changes and stable digital beep scheduling.
Run `python -m unittest test_rx_followup -v`. Earlier profiles remain byte-exact.
See the [implementation report](../../../docs/RX-FIXES-PN1.6-2026-09-19.md).
Device validation is pending; this candidate has not been published or flashed.

**Previous PN 1.5 experimental prerelease:** `python build.py --audit --write` builds
`../experimental/APP_LPM-10RX_PN1.5-audit.bin`. It includes PN 1.4 plus a mains
sampler handoff correction and a DFT arithmetic fix that prevents strong
analog/mains signals from overflowing to zero. Run
`python -m unittest test_firmware_audit -v`. See the
[full TX/RX audit](../../../docs/FULL-FIRMWARE-AUDIT-2026-09-19.md).
CPU-tested; device validation pending. Vendor-facing version remains `3.0.0`.
Download the [RX prerelease](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/rx-v1.5).

**PN 1.4 ADC Timeout Fix experimental prerelease:** `python build.py --roadmap --write`
builds `../experimental/APP_LPM-10RX_PN1.4-roadmap.bin`. It adds recent-signal
auto-off protection, serialized ADC completion, main-loop watchdog feeding and
three digital beep cadences and the expanded ADC timeout margin.
Run `python -m unittest test_roadmap -v`.
The owner reported a PN 1.3 device test pass on 2026-09-19; PN 1.4 adds the ADC
timeout correction. The existing PN 1.0/1.1/1.2 profiles remain reproducible.
See the [implementation report](../../../docs/ROADMAP-IMPLEMENTATION-2026-09-19.md).

**Previous PN 1.2 Reliability experimental prerelease; owner-reported hardware pass.**
The owner reported successful new TX/RX testing on 2026-09-19. Retains the PN 1.1
digital detector and checks existing activity before idle auto-off. A narrow
deadline-ordering bug was reproduced in the original timer handler and fixed in
its existing 36-byte block. No ADC, analog/mains detector, battery, timer-rate,
speaker or device-binding changes from PN 1.1. See
[release notes](../RX-PN1.2-README.txt) and
[audit coverage](../../../docs/RELIABILITY-AUDIT-2026-09-19.md).

**2026-09-19: experimental digital detector available, off by default.**
The V3.0.0-based PN 1.1 digital candidate adds bounded bit-error tolerance
alongside the stock exact matcher, plus a provisional contrast floor. The
sampler, ADC and image size are unchanged. On 2026-09-19 the owner reported
successful testing of both new TX and RX firmware. Range/noise measurements
and compatibility with other revisions remain unverified. See
[candidate notes](../RX-PN1.1-DIGITAL-README.txt) and the
[implementation and test report](../../../docs/SCAN-IMPROVEMENTS-2026-09-19.md).

A patching toolkit for the tone-probe half of the FNIRSI LPM-10A, built against
the official receiver image **APP_LPM-10RX_V3.0.0_260416.bin**. Same philosophy
as the transmitter SDK in [`../sdk`](../sdk/README.md): no vendor source, every
byte accounted for, every behavioural change run under CPU emulation before it
is written to a file.

```
rx-sdk/
  lpm10rx/
    symbols.py    recovered symbol database: 156 functions, RAM map, constants
    image.py      raw-image loader, patch primitives, stock-image lookup
  rx_patches.py   the patch set
  build.py        build APP_LPM-10RX_PN1.0.bin
  verify.py       post-build verification (bytes + disassembly + emulation)
  verify_digital.py  opt-in detector: independent model, faults, noise and phase sweeps
  boot_emu.py     boots the image under emulation and prints the clock tree
                  and timer registers the firmware really programs
  disasm.py       movw/movt-aware disassembler, function survey, xref
```

Requires `capstone` and `unicorn`. The Thumb assembler is shared with the
transmitter SDK (`../sdk/lpm10a/thumb.py`).

## Quick start

```bash
python build.py --list          # what patches exist
python build.py                 # dry run: instruction-level diff
python build.py --write         # emit ../APP_LPM-10RX_PN1.0.bin
python verify.py                # 25 checks
python boot_emu.py              # clock tree and timer rates, from the running code
python disasm.py funcs          # survey every function
python disasm.py fn 08007770    # one function (add an image.bin anywhere to pick a file)
```

To build and verify the **experimental** digital candidate separately:

```bash
python build.py --only batt-critical-recover,digital-correlation --write
python verify.py --digital     # 41 checks, including original battery regressions
```

For the previous **PN 1.2 Reliability experimental prerelease**:

```bash
python build.py --only batt-critical-recover,digital-correlation,activity-before-autooff --write
python verify.py --reliability # 97 checks, including keys, housekeeping and auto-off
python -m unittest test_image -v
```

This writes `../APP_LPM-10RX_PN1.2-reliability-experimental.bin` without replacing
PN 1.0 or PN 1.1. `--all` now includes this new opt-in patch too. A custom subset
containing `activity-before-autooff` needs an explicit `--out` filename. Bounds
checks reject truncated reads, unterminated strings and resized-image writes.

The earlier two-patch digital command writes
`../APP_LPM-10RX_PN1.1-digital-experimental.bin`, not PN 1.0 or PN 1.2.
The default build/verification still use PN 1.0. The internal vendor version
string is deliberately unchanged (`3.0.0`); use the candidate hash to identify it.
Stock's five-read trimmed sampler is retained: this is not oversampling or
sub-slot clock recovery. The added contrast threshold needs bench calibration.

The stock receiver image is FNIRSI's and is **not in the repository**. Put it in
`LPM-10A/Firmware File/`, or in a folder named `LPM-10A_FNIRSI_originals` next
to the repository, or point `LPM10RX_STOCK` at it. `build.py` refuses any image
whose SHA-256 is not the V3.0.0 one.

## The target

| | |
|---|---|
| Image | the vendor file is a raw Cortex-M image loaded at `0x08006800`; the bootloader page below holds the UID-binding record (`0x08006700`) and the `_V3.` tag. **The bootloader only programs a container** (32-byte name, `payload_off 0x1000`, length, end, image at `0x1000`, padded to 4 KB): `build.py --write` emits it as `<name>-update.bin` via `lpm10rx/container.py` |
| CPU | Nations N32L40x class: Cortex-M4F (FPU enabled), 16 MHz HSI, MSI, ADC1 at `0x40020800` |
| Clock | 64 MHz (HSI × PLL 4); APB1 = APB2 = 32 MHz; timer clocks 64 MHz. Verified by `boot_emu.py`, which runs the real `SystemInit`, `rcc_init` and timer set-up and reads the registers back |
| Toolchain | ARM Compiler (Keil MDK) at `-O0`: `b .+2` after almost every statement, addresses via `movw`/`movt`, no literal pools, ARM C library |
| Scheduling | no RTOS. TIM1 = **1 ms** tick (keys every 5 ms, battery every 500 ms, countdowns, 5-minute auto-off), TIM5 = **40 kHz** (ADC sampling, speaker PWM on CH4) |
| Version page | flash page `0x0801F000` holds `3.0.0`; `main` rewrites it when it differs. No settings are stored |
| Stack | `0x20001618`; about 5.6 KB of RAM in use |

There is no code cave inside the stock image, so patches up to PN 1.13 are
in-place and same length. Since PN 1.14 new code is **appended after the image**
with `Image.extend()` (the update container carries the payload length; the
bootloader programmed the longer images on 2026-09-21), up to `EXTEND_LIMIT`
`0x0801E000`, well below the version page.

The full functional description (modes, decoder, speaker, battery, keys,
device binding, what the bootloader question still blocks) is in [`../../../docs/RX-AUDIT.md`](../../../docs/RX-AUDIT.md).

## Current patch set

| id | risk | what |
|---|---|---|
| `batt-critical-recover` | low | The critical-battery shutdown can be cancelled: one reading below 3280 mV still enters the critical state, but each reading (every 500 ms) at or above 3400 mV returns to the low state and resets the counter, so only five **consecutive** low readings (2.5 s) power the unit off. Stock had no way back. 28 bytes changed, in place. |
| `digital-correlation` | untested, opt-in | Retain two exact sliding matches, or accept a full 48-bit window at one of eight rotations with at most four errors total / two per 16 samples; add a DC-independent contrast floor. Entire replacement fits the existing 336-byte routine, no persistent RAM or image growth. |

### What `verify.py` proves

| § | check | how |
|---|---|---|
| 1 | image | size, vector table, initial SP/reset unchanged; every changed byte declared; **every patched site holds exactly the recorded bytes** (stock before, new after); nothing outside the record differs |
| 2 | code | disassembly inventory compared by address; nothing after the edit differs; the patched block decodes to the intended instruction sequence |
| 3 | battery | the real battery routine run once per reading on stock and mod with a fake ADC and `power_off` trapped, nine voltage sequences with their **expected state/count traces** (dip then recovery, dip into the hysteresis band, flat pack, alternating load, healthy pack, slow decline, both sides of the recovery boundary, a restarted count), the shutdown timing, and the LED hysteresis after recovery |
| 4 | facts | r4 holds the sample-buffer base throughout the patched block; the byte counter wraps like stock; the ADC grid (3400 mV is not a representable reading, 3401 is) |
| 5, `--digital` | digital detector | Real detector/trimmed mean against an independent model: clean and corrupted patterns, contrast boundaries, all 256 periodic bytes, seeded noise, tones, synthetic drift, ISR buffer handoff, register preservation and owned memory writes |

A wrong build (different threshold, different branch target, different count)
fails the byte check, the instruction-sequence check and at least one trace.

## Writing a patch

```python
@patch("my-fix", "One line", risk="low", group="bugfix")
def p_my_fix(img):
    code = img.assemble_at(0x08007880, """
            mov  r1, sp
            ldrh r0, [r1, #4]
            ...
    """)
    img.poke(0x08007880, "40f25700 c2f2...", code, "why")
```

`poke` asserts the stock bytes and refuses a different length. Symbols from
`symbols.py` are available to the assembler by name (`bl power_off`).

## Flashing and recovery status

**Solved 2026-09-21** ([procedure and evidence](../../../docs/RX-UPDATE-PROCEDURE-2026-09-21.md)):
probe off, hold SCAN, plug USB → `BOOTLOADER` drive → copy the `*-update.bin`
container with Explorer → the probe programs it within about a second and
restarts. Raw images are ignored (status file `UNKOWN.TXT`); a slow
sector-by-sector writer makes the bootloader give up (`APPRUN.TXT`). The
status file otherwise shows the installed version string (`3.0.0.TXT`).

Rollback: wrap the vendor `APP_LPM-10RX_V3.0.0_260416.bin` with
`lpm10rx.container.wrap()` and copy it the same way (verified on the owner's
unit). The probe's earlier 3.0.1 build has no file and cannot be restored.
Every RX "device pass" reported before 2026-09-21 was a test of that factory
build; the first PN image to run on hardware was PN 1.12, followed the same
day by PN 1.14–1.17 (`docs/RX-SENSITIVITY-2026-09-21.md`).

The application patches do not alter the UID-binding code or record outside
the image. The bootloader code itself (flash `0x08000000–0x080067FF`, L1
read-protected) has not been read; its behaviour is known only from the SRAM
observations in the procedure document.
