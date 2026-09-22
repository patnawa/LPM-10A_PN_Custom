# TX PN2.27A Tone Probe release and PN2.27 comparison

Date: 2026-09-22. Parent: owner-tested TX PN2.26. Tested receiver: RX PN1.24.

This work follows the [PN2.26 deep audit](TX-TONE-PRECISION-AUDIT-PN2.26-2026-09-22.md).
The GPIO optimization and Analog alignment were implemented as separate
images for comparison. The owner subsequently reported:
"test pass on LPM-10A-TX_PN2.27A-analog-alignment.bin and rx1.24".
The tested TX SHA-256 is
`c12b127a634baa038c2504b8e30262a38f963c4900e0967094d7a7f4b1084420`.
This feedback covers that exact TX/RX pairing; it does not report measured
gain/range or an exhaustive function checklist.

| Version | Change | Status |
|---|---|---|
| **PN2.27** | Specialized carrier GPIO updates; existing Digital and Analog waveforms retained | Historical comparison; standalone device testing unconfirmed |
| **PN2.27A** | PN2.27 plus Analog alignment at nominal 816.832 Hz; Analog label reads 817 Hz | Owner-reported test pass with RX PN1.24; current TX release/default |

PN2.27A is the current TX firmware and default `build.py` profile. Promotion
preserves the exact tested bytes; the original profiles remain reproducible.
RX PN1.24 remains unchanged. Release notes:
[v2.27A](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/v2.27A).

## PN2.27: reduce switching overhead

The PN2.26 carrier transition calls the general-purpose `GPIO_Init` routine
twice, once for PB13 and once for PA8. Those calls scan pin selections and
consume 242 instructions. The complete carrier-enable path takes 258
instructions in the audit fixture. There is no need to repeat generic pin
selection when both pins and modes are fixed.

PN2.27 specializes only the carrier ON/OFF routines. It updates each pin's
four-bit configuration field, preserving the other pins' fields and the
existing PB13-then-PA8 write order. OFF retains the original level-selection
routine and its tick-dependent polarity. Timer configuration, complementary
output selection, drive-strength and slew settings remain those of PN2.26.

The change fits inside the two existing routine slots. It adds no persistent
RAM and does not extend the image or the allocated code region. About and the
boot log identify PN2.27. The existing two tone buttons and screen layout are
retained.

Digital still uses the B6 pattern, 5.05 ms chips, 40.4 ms code repetition and
nominal 454.259 kHz carrier. Analog remains 825.083 Hz. Reducing instruction
work does not establish a particular elapsed-time saving on the MCU, increased
signal amplitude, longer range or better cable discrimination.

Actual Thumb measurements of the complete carrier routines:

| Measurement | PN2.26 | PN2.27 |
|---|---:|---:|
| Enable instructions | 258 | **17** |
| Disable instructions, depending on OFF polarity | 284 / 285 | **42 / 43** |
| Instructions between PB13 and PA8 configuration writes | 126 | **7** |
| Maximum enable stack use in the fixture | 32 bytes | **0 bytes** |
| Maximum disable stack use in the fixture | 32 bytes | **16 bytes** |

The two replacements each occupy 44 bytes within the original 60-byte OFF and
56-byte ON slots; unused space is NOP padding. All six direct callers were
checked: they discard the result/flags or overwrite them before use. The
existing port read/modify/write ownership assumptions remain; the optimization
does not introduce interrupt masking or claim atomicity against arbitrary
competing GPIO writers.

## PN2.27A: Analog alignment

The Analog receiver's nominal DFT target is 816.797194 Hz. PN2.26/PN2.27 Analog is
825.082508 Hz. Changing the shared timer to improve this alignment would also
change Digital modulation, watchdog checks and key-beep servicing.

PN2.27A keeps the shared 101 us timer tick. Its Analog phase advances by 165
modulo 2000 on each active tick and selects the upper half of the phase range
as the carrier-enabled interval. This produces 33 cycles in 400 ticks:
**816.831683 Hz**, with 50% envelope duty over that repeating period.

The tradeoff is edge quantization: 62 half-cycles last 606 us and four last
707 us in each 400-tick period. Mean-frequency alignment improves; individual
half-cycles are no longer all the same length. PN2.27 remains available as
the comparison image with the original Analog frequency.

The existing Analog phase halfword is reused. Pause does not advance phase;
resuming or returning from the other mode continues it. An out-of-range phase
is normalized before advancing. The older toggle/counter bytes no longer
determine Analog output. The carrier gate, RIGHT-key cache recovery and all
Digital timing are retained. The Analog label changes to **Analog 817 Hz** in
both language settings without changing the button layout.

## Validation method and evidence limits

The `diagnosing-bugs` workflow uses the actual firmware execution path. The
performance regression criterion was established before the new GPIO code:
the existing 258-instruction ON routine fails an 80-instruction transition
budget. Differential tests compare the old and new ordered peripheral writes
under seeded GPIO/timer/drive/slew state, OFF polarities and interrupt masks.

Lifecycle tests execute real keys and timer IRQs, check output during injected
preemption as well as after the key returns, and cover all existing Digital
and Analog phases. PN2.27A has an independent phase oracle and its own control
tests; the old six-tick Analog oracle is not reused for the new waveform.

The paired receiver experiment builds both candidates, captures their actual
GPIO selections, checks their shared clocks and measures complete IRQ
instruction counts. It replays those selections through actual RX PN1.24 and
PN1.23G sampling and analysis code. Analog uses 127 common modeled start-time
offsets and four amplitude levels; Digital uses eight phase offsets and four
levels. PN2.27's traces are required to equal PN2.26 exactly.

These are register and instruction observations, plus a finite ideal-link
model. ADC input is a square envelope centered at 2048, at fixed gain 7, with
fresh acquisition windows. There is no modeled cable coupling, analog
filtering, noise, loading, oscillator drift, movement, clipping or continuous
audio. No measured physical gain or range claim follows from these tests.

Before promotion, the TX SDK regression suite passed **516 tests in 346.476 seconds**,
including the component/lifecycle checks and historical profile reproduction.
After release promotion, **37 profile/component checks and 12 publication
checks passed**. Default and explicit PN2.27A builds retain the exact tested
SHA-256; every historical profile remains reproducible.
The focused component and lifecycle checks also passed independently. Their coverage includes
256 seeded carrier equivalence cases, all six direct caller paths, all 2,000
valid Analog accumulator values and invalid-value recovery. Each candidate
passed 17,834 key/navigation interrupt placements. PN2.27 retained all 812
legacy phase positions; PN2.27A covered 400 reachable Analog phases including
actual Home exit/reentry and all 800 Digital cursor positions. Both passed
eight GUI mode/language/enable states.

The combined experiment passed **60,006 actual TX IRQ executions and 2,096
modeled RX acquisitions**. A completed acquisition is not necessarily an
accepted signal; the explicit rejection results are shown below.

| Full IRQ measurement | PN2.26 | PN2.27 | PN2.27A |
|---|---:|---:|---:|
| Digital mean instructions | 113.632 | 109.986 | 109.986 |
| Digital maximum instructions | 393 | 151 | 151 |
| Analog mean instructions | 170.757 | 130.528 | 118.375 |
| Analog maximum instructions | 451 | 209 | 201 |

Each measurement covers 10,001 ticks per image/mode, with modeled peripheral
registers and no concurrent application tasks. These maxima describe that
corpus; they are not worst-case hardware timing bounds.

RX PN1.24 and PN1.23G gave the same Analog results on the common phase corpus:

| ADC peak-to-peak level | PN2.27 detections | PN2.27A detections | PN2.27 raw score | PN2.27A raw score |
|---:|---:|---:|---:|---:|
| 0 | 0 / 127 | 0 / 127 | 0 | 0 |
| 12 | 0 / 127 | 0 / 127 | 0 | 0 |
| 24 | **124 / 127** | **127 / 127** | 0–160 | 80–160 |
| 80 | 127 / 127 | 127 / 127 | 1040–1280 | 1160–1440 |

All three TX Digital traces are identical. Both RX versions detected all eight
Digital phase cases at levels 12, 24 and 80, and rejected all flat-input cases.
The modeled Analog result supports the alignment change; it does not
establish a hardware sensitivity improvement or compatibility with every RX
version. Full measurements and hashes are in the
[machine-readable validation result](experiments/results/tx-tone-pn227-pn227a-2026-09-22.json).

## Files and reproduction

The original build files and instructions remain in
`LPM-10A/Firmware File/experimental` for reproduction. PN2.27A is also the
current firmware in `LPM-10A/Firmware File`; its bytes are identical.

- [PN2.27 firmware](../LPM-10A/Firmware%20File/experimental/LPM-10A-TX_PN2.27-tone-precision.bin),
  [instructions](../LPM-10A/Firmware%20File/experimental/TX-PN2.27-README.txt),
  [SHA-256](../LPM-10A/Firmware%20File/experimental/TX-PN2.27-SHA256SUMS.txt).
- [PN2.27A firmware](../LPM-10A/Firmware%20File/experimental/LPM-10A-TX_PN2.27A-analog-alignment.bin),
  [instructions](../LPM-10A/Firmware%20File/experimental/TX-PN2.27A-README.txt),
  [SHA-256](../LPM-10A/Firmware%20File/experimental/TX-PN2.27A-SHA256SUMS.txt).

From `LPM-10A/Firmware File/sdk`:

```powershell
python tone_precision.py --write
python tone_alignment.py --write
python -W ignore::ResourceWarning -m unittest test_tone_precision test_tone_alignment test_tone_precision_lifecycle -q
python -W ignore::ResourceWarning -m unittest discover -q
```

From the repository root:

```powershell
python docs/experiments/tx_tone_candidate_validation.py --json docs/experiments/results/tx-tone-pn227-pn227a-2026-09-22.json
```

Both builders pin their exact parent. The original profiles remain reproducible.
The [candidate validation script](experiments/tx_tone_candidate_validation.py)
also verifies any existing emitted candidate matches the freshly built bytes.

Both containers are **401,408 bytes**. Their SHA-256 values are:

| File | SHA-256 |
|---|---|
| `LPM-10A-TX_PN2.27-tone-precision.bin` | `575a410fea87da9bc4ecb273d1fd931712bb8a2d911d771c55332dc2a2c4e8b2` |
| `LPM-10A-TX_PN2.27A-analog-alignment.bin` | `c12b127a634baa038c2504b8e30262a38f963c4900e0967094d7a7f4b1084420` |

PN2.27 retains the PN2.26 payload end at `0x0806A558`. PN2.27A adds a 64-byte
helper ending at `0x0806A598`, inside existing file padding. Both retain the
existing RAM allocation end `0x2000F364`; neither adds persistent RAM.

## Owner verification and further comparison

The owner's test pass applies to PN2.27A with RX PN1.24. No separate device
result was reported for PN2.27. Further controlled comparisons can keep
RX PN1.24, the cable, the RX knob setting and probe position the same while
comparing PN2.26, PN2.27 and PN2.27A. Use the ordinary TX M + Power update
procedure and verify the About version after each copy.

For additional characterization, check weak/far pickup, strong/close pickup,
movement and RX knob changes in
both modes. Exercise TX RIGHT, mode changes, Pause/resume and Back/reentry.
Record any silence, intermittent sound, lingering tone or changed pickup from
adjacent cables. Confirm QC entry/Init, a complete cable and Length operation.

For rollback, install the owner-tested PN2.26 TX file by the same procedure.
PN2.27 also provides the original Analog frequency with the GPIO optimization.
Existing successful PN2.25/PN2.26 QC calibration remains usable; if QC requests
Init, disconnect every cable and hold Right before reconnecting the cable.
