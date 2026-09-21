# Firmware files

**Copy these two — nothing else in this folder is needed to update a device:**

| Device | File | How |
|---|---|---|
| TX tester | `LPM-10A-TX_PN2.20-cable-text-clear.bin` | tester off → hold **M + Power** → plug USB-C → copy onto the drive → long-press Power, power on |
| RX probe | `APP_LPM-10RX_PN1.23-mains-tone-update.bin` | probe off → hold **SCAN** → plug USB → copy onto the `BOOTLOADER` drive with Explorer → the drive disappears in ~1 s |

`SHA256SUMS.txt` has both checksums; `TX-PN2.20-README.txt` and `RX-PN1.23-README.txt` say what each build
does and how to roll back. The RX procedure in full (Thai + English): [`../../docs/RX-UPDATE-GUIDE.md`](../../docs/RX-UPDATE-GUIDE.md).

FNIRSI's own files (`LPM-10A-TX_V2.0.7_260610.bin`, `APP_LPM-10RX_V3.0.0_260416.bin`) are **not** in this
repository; the build tools look for them in a folder next to the repository (see each `build.py`).

## Everything else

| Folder / file | What it is |
|---|---|
| `sdk/` | TX toolkit: patch chain PN 2.9 → 2.20 (`profiles.py`), assembler, verifier, Thai UI, tests (`python build.py --write` = the latest profile) |
| `rx-sdk/` | RX toolkit: patch chain PN 1.0 → 1.23 (`profiles.py`), update container, CPU-model tests (`python build.py --write`) |
| `experimental/` | **build outputs of every PN version**, TX and RX, with their notes and checksums; the test suites rebuild and compare against these byte for byte, so they stay. `README.md` inside lists them. |
| `archive/` | earlier release copies and their per-version notes (TX PN 2.4–2.9, 2.14, RX PN 1.0–1.8) — history only |
| `FORMULA-AUDIT.md` | every measurement formula with verdicts: TX §1–6, receiver PN formulas §7 |

`publish_current.py` copies the latest TX/RX builds from `experimental/` to this folder and rewrites
`SHA256SUMS.txt` (run it after building a new release).
