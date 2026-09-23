# Firmware files

**Copy these two — nothing else in this folder is needed to update a device:**

| Device | File | How |
|---|---|---|
| TX tester | `LPM-10A-TX_PN2.27A-analog-alignment.bin` | tester off → hold **M + Power** → plug USB-C → copy onto the drive → long-press Power, power on |
| RX probe | `APP_LPM-10RX_PN1.29-levels-update.bin` | probe off → hold **SCAN** → plug USB → copy onto the `BOOTLOADER` drive with Explorer → the drive disappears in ~1 s |

`SHA256SUMS.txt` has both checksums; `TX-PN2.27A-README.txt` and `RX-PN1.29-README.txt` say what each build
does and how to roll back. The RX procedure in full (Thai + English): [`../../docs/RX-UPDATE-GUIDE.md`](../../docs/RX-UPDATE-GUIDE.md).

The owner reports **TX PN2.27A passed device testing paired with RX PN1.24, 2026-09-22**.
It reduces carrier-switching work and aligns Analog modulation to nominal 816.832 Hz,
displayed as Analog 817 Hz, while retaining Digital timing and the PN2.26 QC/Length fixes.
[Implementation and validation](../../docs/TX-TONE-PRECISION-PN2.27-2026-09-22.md).
If QC requests Init after the update, **disconnect all cables and hold Right**
until Init succeeds. Calibration made before PN2.25 requires this once.

The owner confirms **RX PN1.29 passes on the probe, 2026-09-23** ("1.29 test pass work perfect").
The probe plays the tone's strength as one of ten absolute levels 3 dB apart (a weaker level's
Digital pulse period is 15 % longer; no comparison with pairs touched before), with no peak memory
and no muting. The knob scales the strength (0 dB at the top, −30 dB at the bottom, PN1.27's law);
Digital and Analog tracing can use the full gain at every knob position.
Knob fully up = **Locate**: find the bundle or cabinet; at the cabinet strong pairs all play the
top level, by design. About a fifth of the knob = **Isolate**: touch each pair about 2 s; the toned
pair plays faster than each neighbour, and every neighbour is at least one level slower (emulator
at 19 % of the knob, with neighbours 3 dB or more weaker; a neighbour within about 2 dB of the toned
pair cannot be separated). Every pair at the slowest level: turn up a little; suspect pair and
neighbours all at the top level: turn down a little. In the emulator Analog separates pairs more
steadily than Digital. NCV keeps the knob's gain; beeps stay about 9.5 dB louder than stock/PN1.24
(speaker duty 1100/500 against 900/700; worked out from the duty, not measured).
The owner's report is a pass on the probe; it did not measure pickup distance, loudness or
selectivity. The figures here are design or emulator values.
[IntelliTone comparison, design and validation](../../docs/RX-INTELLITONE-ANALYSIS-2026-09-23.md).

FNIRSI's own files (`LPM-10A-TX_V2.0.7_260610.bin`, `APP_LPM-10RX_V3.0.0_260416.bin`) are **not** in this
repository; the build tools look for them in a folder next to the repository (see each `build.py`).

## Everything else

| Folder / file | What it is |
|---|---|
| `sdk/` | TX toolkit: patch chain PN 2.9 → 2.27A (`profiles.py`), assembler, verifier, Thai UI, tests (`python build.py --write` = the latest profile) |
| `rx-sdk/` | RX toolkit: patch chain PN 1.0 → 1.29 (`profiles.py`), update container, CPU-model tests (`python build.py --write` = the latest profile, PN1.29) |
| `experimental/` | **build outputs of every PN version**, TX and RX, with their notes and checksums; the test suites rebuild and compare against these byte for byte, so they stay. `README.md` inside lists them. |
| `archive/` | earlier release copies and their per-version notes (including TX PN2.26 and RX PN1.23, PN1.24, PN1.27) — history only |
| `FORMULA-AUDIT.md` | every measurement formula with verdicts: TX §1–6, receiver PN formulas §7 |

To publish a new release: first move the release being replaced (its root `.bin` and notes) to
`archive/` and add a per-version checksum file there (`RX-PN1.xx-SHA256SUMS.txt` or
`TX-PN2.xx-SHA256SUMS.txt`), as was done for RX PN1.27. Then run `publish_current.py` with both
current file names, TX and RX; it copies the named builds from `experimental/` to this folder,
removes the previous release files listed in `SHA256SUMS.txt` that are not named, and rewrites
`SHA256SUMS.txt`. Finally copy the new build's `…-README.txt` from `experimental/` and update the
table above.
