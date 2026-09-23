# Firmware files

**Copy these two — nothing else in this folder is needed to update a device:**

| Device | File | How |
|---|---|---|
| TX tester | `LPM-10A-TX_PN2.27A-analog-alignment.bin` | tester off → hold **M + Power** → plug USB-C → copy onto the drive → long-press Power, power on |
| RX probe | `APP_LPM-10RX_PN1.27-knob-update.bin` | probe off → hold **SCAN** → plug USB → copy onto the `BOOTLOADER` drive with Explorer → the drive disappears in ~1 s |

`SHA256SUMS.txt` has both checksums; `TX-PN2.27A-README.txt` and `RX-PN1.27-README.txt` say what each build
does and how to roll back. The RX procedure in full (Thai + English): [`../../docs/RX-UPDATE-GUIDE.md`](../../docs/RX-UPDATE-GUIDE.md).

The owner reports **TX PN2.27A passed device testing paired with RX PN1.24, 2026-09-22**.
It reduces carrier-switching work and aligns Analog modulation to nominal 816.832 Hz,
displayed as Analog 817 Hz, while retaining Digital timing and the PN2.26 QC/Length fixes.
[Implementation and validation](../../docs/TX-TONE-PRECISION-PN2.27-2026-09-22.md).
If QC requests Init after the update, **disconnect all cables and hold Right**
until Init succeeds. Calibration made before PN2.25 requires this once.

The owner confirms **RX PN1.27 passes on the probe, 2026-09-23** ("1.27 test pass").
The probe has full gain at every knob position (on PN1.26, same gain law, the owner heard
the tone from 5–10 % in Digital and 10–20 % in Analog),
the knob sets the rhythm's reference over its whole travel (lower knob, slower rhythm;
the top sixteenth is PN1.24), pairs much weaker than the strongest one are muted below
the middle of the knob, NCV always has the knob's gain, and beeps are about 9.5 dB louder.
[Diagnosis and validation](../../docs/RX-KNOB-PN1.27-2026-09-23.md);
steps before it: [PN1.25](../../docs/RX-ISOLATE-PN1.25-2026-09-23.md),
[PN1.26](../../docs/RX-RELATIVE-PN1.26-2026-09-23.md).

FNIRSI's own files (`LPM-10A-TX_V2.0.7_260610.bin`, `APP_LPM-10RX_V3.0.0_260416.bin`) are **not** in this
repository; the build tools look for them in a folder next to the repository (see each `build.py`).

## Everything else

| Folder / file | What it is |
|---|---|
| `sdk/` | TX toolkit: patch chain PN 2.9 → 2.27A (`profiles.py`), assembler, verifier, Thai UI, tests (`python build.py --write` = the latest profile) |
| `rx-sdk/` | RX toolkit: patch chain PN 1.0 → 1.27 (`profiles.py`), update container, CPU-model tests (`python build.py --write`) |
| `experimental/` | **build outputs of every PN version**, TX and RX, with their notes and checksums; the test suites rebuild and compare against these byte for byte, so they stay. `README.md` inside lists them. |
| `archive/` | earlier release copies and their per-version notes (including TX PN2.26 and RX PN1.23, PN1.24) — history only |
| `FORMULA-AUDIT.md` | every measurement formula with verdicts: TX §1–6, receiver PN formulas §7 |

`publish_current.py` copies the latest TX/RX builds from `experimental/` to this folder and rewrites
`SHA256SUMS.txt` (run it after building a new release).
