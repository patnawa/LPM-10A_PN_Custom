# Experimental builds

**2026-09-20 archival prerelease:** these candidates and their research are
preserved in the [development snapshot](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/tone-snapshot-2026-09-20).
The owner is retaining the working device setup. RX update acceptance remains
unresolved; live SRAM is incompatible with normal execution of the stored
PN 1.13 image. Earlier RX version names below describe selected files and owner
reports, not authenticated installed firmware. PN 1.13 and the lamp marker are
research artifacts, not a confirmed Digital-tail fix or a recommended update.
See [current status](../../../docs/releases/TONE-SNAPSHOT-2026-09-20.md).

**Latest RX PN 1.13 audio-clock test candidate:** moves the shared pulse and
quiet-gap countdown to the speaker timer. Detection and strength logic remain
PN 1.12. The owner tried PN 1.13 and reports the symptom is unchanged; the
physical issue remains unresolved. Retained test artifact:
[RX PN 1.13](APP_LPM-10RX_PN1.13-audio-clock.bin) and keep the same
[TX PN 2.14](LPM-10A-TX_PN2.14-tone-recovery.bin). See
[device notes](TONE-AUDIO-CLOCK-PN1.13-PN2.14-README.txt),
[checksums](TONE-AUDIO-CLOCK-SHA256SUMS.txt), and
[verification](../../../docs/TONE-AUDIO-CLOCK-PN1.13-PN2.14-2026-09-20.md).

The subsequent clip shows repeated roughly 50 ms pulses after TX Digital →
Analog, rather than a continuous one-second pulse. See the
[video diagnosis and unchanged filename-check result](../../../docs/TONE-CLIP-DIAGNOSIS-2026-09-20.md).
A separate [startup lamp identity diagnostic](../../../docs/RX-IDENTITY-MARKER-PN1.13-2026-09-20.md)
changes one byte of PN 1.13 to identify update uptake. It is not a tail fix or
a replacement normal release.

**Preserved RX PN 1.12 local candidate:** includes PN 1.11 tracking and replaces
old normal strength with uncertainty when the newest Digital tail is fully at
the ADC upper rail. Lower-zero and brief-contact behavior remain unchanged.
Download [RX PN 1.12](APP_LPM-10RX_PN1.12-overload.bin), paired with the same
[TX PN 2.14](LPM-10A-TX_PN2.14-tone-recovery.bin); see
[device notes](TONE-OVERLOAD-PN1.12-PN2.14-README.txt),
[checksums](TONE-OVERLOAD-SHA256SUMS.txt) and
[verification](../../../docs/TONE-OVERLOAD-PN1.12-PN2.14-2026-09-20.md).
Software tested. With owner-reported RX PN 1.12 / TX PN 2.14 files, both modes receive
and sweeping is more accurate. Later feedback reports an open Digital release
issue: sound continues about one second after moving away or pressing TX Pause.
Analog has no such delay.
See [owner feedback](../../../docs/TONE-DEVICE-FEEDBACK-2026-09-20.md).
No comparator result is available.

**RX PN 1.11 local tracking candidate:** robust Digital acquisition with the
established fallback, overlapping updates and recent strength; finer short
Analog feedback and exact integer DFT. Use with the two established TX modes.
Download [RX PN 1.11](APP_LPM-10RX_PN1.11-tracking.bin); see
[paired device notes](TONE-TRACKING-PN1.11-PN2.14-README.txt),
[checksums](TONE-TRACKING-SHA256SUMS.txt), and
[verification and remaining limits](../../../docs/TONE-TRACKING-PN1.11-PN2.14-2026-09-20.md).
This RX candidate awaits device testing. No Fluke comparison is available.

**TX PN 2.14 local two-mode candidate:** removes Sync32 and Pulse test from the
menu at the owner's request after Sync32 was silent with RX PN 1.10 digital
mode. Keeps `Digital 454 kHz` / `Analog 825 Hz`, using the unchanged PN 2.12
waveforms, and repairs the RIGHT-key carrier-cache invalidation. Download
[TX PN 2.14](LPM-10A-TX_PN2.14-tone-recovery.bin); see
[device notes](TONE-RECOVERY-PN2.14-README.txt),
[checksum](TONE-RECOVERY-SHA256SUMS.txt), and
[verification report](../../../docs/TONE-RECOVERY-PN2.14-2026-09-20.md).
The [detailed performance audit](../../../docs/TONE-PERFORMANCE-AUDIT-2026-09-20.md)
documents the prior RX limits. The separate RX PN 1.11 candidate above addresses
several of them; a TX-only update does not change the receiver algorithm.
The owner's current RX remains usable with these two modes. This TX image
has owner feedback linked above; the installed RX version is unconfirmed.
The filename does not denote a bootloader recovery image.

**Historical TX PN 2.13 / RX PN 1.10 Sync32 trial — reported failure:** the owner
reports Sync32 silent while Digital/Analog work, despite RX PN 1.10 digital mode.
Pulse test is for an oscilloscope and is expected to be rejected by the probe.
PN 2.14 removes both menu options. The following files preserve the trial;
they are not a recommended Sync32 upgrade. The trial added optional Sync32 tracing
and a TX Pulse test mode while retaining existing Digital and analog waveforms.
The tone labels are `Digital 454 kHz`, `Analog 825 Hz`, `Sync32 454 kHz` and
`Pulse test`. Digital/Sync32 show carrier frequency; Analog shows tone rate.
Download [TX PN 2.13](LPM-10A-TX_PN2.13-sync.bin) and
[RX PN 1.10](APP_LPM-10RX_PN1.10-sync.bin); see
[device notes](SCAN-SYNC-PN2.13-PN1.10-README.txt),
[checksums](SCAN-SYNC-SHA256SUMS.txt), and the
[paired report](../../../docs/SCAN-SYNC-PN2.13-PN1.10-2026-09-20.md).
Sync32 is more sensitive to clock mismatch in the model. The owner has now
tested this pair on hardware and reports the failure above; it is not published.

**RX PN 1.9 robust local experimental candidate:** uses medians grouped by the
expected digital code to improve cable-strength ranking in synthetic impulse
tests. Existing digital detection and sampling remain unchanged. A valid code
with an upper-rail-dominated or inseparable strength estimate gives distinct
100 ms pulses with 160 ms quiet gaps; normal feedback retains 30 ms pulses.
Build `python build.py --robust --write` and run
`python -m unittest test_rx_robust test_robust_profile -v` in `rx-sdk`.
The local candidate is [APP_LPM-10RX_PN1.9-robust.bin](APP_LPM-10RX_PN1.9-robust.bin);
see [device notes](RX-PN1.9-ROBUST-README.txt),
[checksum](RX-ROBUST-SHA256SUMS.txt), and
[implementation report](../../../docs/RX-ROBUST-PN1.9-2026-09-20.md).
It has not been published or flashed; hardware validation is pending.
PN 1.8 remains the current owner-tested experimental prerelease.

**Current owner-tested RX PN 1.8 pinpoint prerelease:** replaces PN 1.7's five broad digital
grades with an interpolated beep interval across a wider strength range.
Build `python build.py --pinpoint --write` and run
`python -m unittest test_rx_pinpoint -v` in `rx-sdk`.
Download [APP_LPM-10RX_PN1.8-pinpoint.bin](APP_LPM-10RX_PN1.8-pinpoint.bin);
see [device notes](RX-PN1.8-PINPOINT-README.txt),
[checksum](RX-PINPOINT-SHA256SUMS.txt), and
[implementation report](../../../docs/RX-PINPOINT-PN1.8-2026-09-19.md).
The owner reports a device test pass on 2026-09-19. The exact binary is published
in the [RX PN 1.8 experimental prerelease](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/rx-v1.8).
Quantitative cable-selection measurements were not supplied; PN 1.7 is preserved.

**Previous RX PN 1.7 precision prerelease:** digital cable tracing with five strength
levels, outlier-resistant grading, stable level transitions and faster release.
Build `python build.py --precision --write` and run
`python -m unittest test_rx_precision -v` in `rx-sdk`.
Download [APP_LPM-10RX_PN1.7-precision.bin](APP_LPM-10RX_PN1.7-precision.bin);
see [device notes](RX-PN1.7-PRECISION-README.txt),
[checksum](RX-PRECISION-SHA256SUMS.txt), and
[implementation report](../../../docs/RX-PRECISION-PN1.7-2026-09-19.md).
It includes PN 1.6; the owner reports a device test pass on 2026-09-19.
Quantitative range and cable-selection measurements were not supplied.
The exact binary is published in the
[RX PN 1.7 experimental prerelease](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/rx-v1.7).

**RX PN 1.6 local candidate:** corrects mode/gate sample ownership and digital
beep timing. Build `python build.py --followup --write` and run
`python -m unittest test_rx_followup -v` in `rx-sdk`.
Download [APP_LPM-10RX_PN1.6-followup.bin](APP_LPM-10RX_PN1.6-followup.bin);
see [device notes](RX-PN1.6-FOLLOWUP-README.txt),
[checksum](RX-FOLLOWUP-SHA256SUMS.txt), and
[implementation report](../../../docs/RX-FIXES-PN1.6-2026-09-19.md).
This intermediate image has no separate device pass; its fixes are included
in the PN 1.7 prerelease above.

This directory also retains the exact binaries published as
[TX PN 2.12](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/v2.12) and
[RX PN 1.5 experimental prerelease](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/rx-v1.5).
Their filenames and bytes are preserved from the tested candidates.

**Latest TX follow-up: PN 2.12 Port FLASH status.** For intermittent long-on
pauses reported on PN 2.11 / D-Link gigabit: the controller and indicator now
use PHY link status. Includes all PN 2.11 fixes; CPU-tested. The owner confirmed
the Port FLASH fix on the D-Link gigabit switch on 2026-09-19. Other functions
await separate device validation.
Build `python build.py --portflash-status --write` and run
`python -m unittest test_portflash_status -v` in `sdk`.
Download [LPM-10A-TX_PN2.12-portflash-status.bin](LPM-10A-TX_PN2.12-portflash-status.bin);
see [device notes](PN2.12-PORTFLASH-STATUS-README.txt),
[checksum](PORTFLASH-STATUS-SHA256SUMS.txt) and
[investigation](../../../docs/PORT-FLASH-STATUS-2026-09-19.md).

**Full audit candidates: TX PN 2.11 / RX PN 1.5.** Seven reproduced firmware
defects are corrected, including all PN 2.10 fixes below. CPU-tested; device
validation pending. Build with `python build.py --audit --write` in each
device's SDK and run `python -m unittest test_firmware_audit -v` there.
See the [full audit](../../../docs/FULL-FIRMWARE-AUDIT-2026-09-19.md) and
[checksums](AUDIT-SHA256SUMS.txt).

| Device | Firmware | Notes |
|---|---|---|
| TX tester | [LPM-10A-TX_PN2.11-audit.bin](LPM-10A-TX_PN2.11-audit.bin) | [FLASH, battery and settings fixes](PN2.11-AUDIT-README.txt) |
| RX probe | [APP_LPM-10RX_PN1.5-audit.bin](APP_LPM-10RX_PN1.5-audit.bin) | [Sample handoff and DFT overflow fixes](RX-PN1.5-AUDIT-README.txt) |

Use the firmware for the matching device; TX and RX images are not interchangeable.

**PN 2.10 Port FLASH candidate:** addresses the reported blink-then-stop issue
with a corrected PHY auto-negotiation register, recovery after observed link
loss, and timing measured after power operations complete. CPU-tested; awaiting
device validation. Build with `python build.py --portflash --write` and test with
`python -m unittest test_portflash -v` in `sdk`.
See the [audit](../../../docs/PORT-FLASH-AUDIT-2026-09-19.md),
[device notes](PN2.10-PORTFLASH-README.txt) and [checksum](PORTFLASH-SHA256SUMS.txt).
The binary is [LPM-10A-TX_PN2.10-portflash.bin](LPM-10A-TX_PN2.10-portflash.bin).

This directory retains experimental profiles and the exact roadmap binaries
published after the owner's device test pass.

The **PN 2.9 TX / PN 1.4 RX roadmap** builds implement the requested fixes
and Ideas 1–7. In the corresponding SDK directory, run `python build.py --roadmap --write`
and `python -m unittest test_roadmap -v`. Their dedicated tests must pass without
expected failures. Checksums are in `ROADMAP-SHA256SUMS.txt`; see the
[implementation report](../../../docs/ROADMAP-IMPLEMENTATION-2026-09-19.md).
These exact files are now the [TX PN 2.9 release](../../../docs/releases/v2.9.md) and
[RX PN 1.4 experimental prerelease](../../../docs/releases/rx-v1.4.md).

The older **PN 2.4 blind-zone experiment** below is the default PN build plus one
experiment, for measuring something on hardware. Its original verifier reports two
expected failures on them (the byte-for-byte match with the default build and
the undeclared instruction at the experiment's site); everything else must pass.

| file | experiment | how to build |
|---|---|---|
| `LPM-10A-TX_PN2.4-exp-blindzone50.bin` | length blind zone 2.0 m → 0.5 m: cables of 0.5–2 m show whatever the PHY reports instead of *Out of range* | `python build.py --with blind-zone-50cm --out ../experimental/LPM-10A-TX_PN2.4-exp-blindzone50.bin --write` |

## What the blind-zone experiment is for

On the tested unit a 1 m cable came back as raw 2.0–2.4 m or as nothing: the
PHY's short-range result exists but is unreliable, and stock discards it
below 2 m. To find out whether short cables can be measured at all:

1. Flash the experimental image. Keep Zero and NVP as calibrated (0.4 m / 68 %).
2. Measure cables of known length 0.5, 1.0, 1.5, 2.0 and 3.0 m, five times each,
   far end unplugged, and record all four pairs each time.
3. Send the table. If the readings are monotonic and repeatable (even if
   wrong), a short-range correction table can be added and the blind zone
   lowered for real. If they scatter or collapse to a constant, the PHY cannot
   resolve that range and the 2 m limit stays.

sha256 of the current experimental image: `b55872030783c2535575e73f352cb4a872a3300e14c7fe2bf025924392cde5d0` (PN 2.4 base, so it also carries the PoE
screen and FLASH changes and the 4 KB longer update file)
