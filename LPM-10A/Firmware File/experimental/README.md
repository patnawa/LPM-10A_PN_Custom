# Experimental builds

**RX PN 1.8 pinpoint prerelease:** replaces PN 1.7's five broad digital
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
