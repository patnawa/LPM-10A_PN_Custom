# Experimental builds

This directory retains experimental profiles and the exact roadmap binaries
published after the owner's device test pass.

The **PN 2.8 TX / PN 1.3 RX roadmap** builds implement the requested fixes
and Ideas 1–7. In the corresponding SDK directory, run `python build.py --roadmap --write`
and `python -m unittest test_roadmap -v`. Their dedicated tests must pass without
expected failures. Checksums are in `ROADMAP-SHA256SUMS.txt`; see the
[implementation report](../../../docs/ROADMAP-IMPLEMENTATION-2026-09-19.md).
The owner reported a device test pass on 2026-09-19. These exact files are now
the [TX PN 2.8 release](../../../docs/releases/v2.8.md) and
[RX PN 1.3 experimental prerelease](../../../docs/releases/rx-v1.3.md).

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
