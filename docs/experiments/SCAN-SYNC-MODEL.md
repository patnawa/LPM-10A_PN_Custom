# Sync32 protocol model and bounded comparison

The optional Sync32 waveform improves detection in this model at nominal clock
timing with moderate additive noise. It also has narrow clean-signal phase
blind spots and is less tolerant of clock mismatch than legacy Digital. It must
remain an experimental choice with legacy Digital available.

This result does not establish greater hardware range, cable selectivity, or
performance relative to a commercial probe. The receiver's existing analogue
front end and five-read envelope sampler are not physically simulated.

## Reproduce

From the repository root, using Python 3.10 or newer:

```text
python docs/experiments/scan_sync_model.py
python docs/experiments/scan_sync_model.py --json
python docs/experiments/scan_sync_model.py --fresh-start --json
```

The script uses only the standard library. It executes finite-code checks,
compares the closed-form emitter with 160,100 steps of the exact TX accumulator
recurrence, evaluates 147,456 seeded phase/noise windows, and separately checks
81,920 clean windows on a denser phase grid. These are mathematical and sampler
model checks, not execution of the patched ARM firmware.

The default noisy benchmark uses 64 fractional offsets at each of 32 chip
positions, giving 2,048 windows per protocol per condition. The clean audit
uses 256 fractional offsets, giving 8,192 windows per protocol per condition.
Both cover the first nominal 32-chip frame; they do not exhaust every phase of
the longer physical dither cycle. `--json` includes the rejected phase offsets
and the acquisition origin. By default the model uses immediately rearmed
acquisition; `--fresh-start` selects the first window after fresh startup.

## Sampling origin and the hardware failure follow-up

The original model used ADC positions 0.6, 0.7, 0.8, 0.9, and 1.0 of a nominal
RX sample interval, described as a sampler approximation. The full TIM5 IRQ
audit in [test_scan_acquisition_timing.py](../../LPM-10A/Firmware%20File/rx-sdk/test_scan_acquisition_timing.py)
now distinguishes two origins in the delivered RX PN 1.10 firmware:

| Acquisition origin | First five ADC calls, in TIM5 IRQs after origin | Positions in nominal sample intervals |
|---|---|---|
| Fresh startup, sampler substep initially zero | 140, 160, 180, 200, 220 | 0.7, 0.8, 0.9, 1.0, 1.1 |
| Immediately after the previous window completes and rearms | 120, 140, 160, 180, 200 | 0.6, 0.7, 0.8, 0.9, 1.0 |

Later groups repeat every 200 IRQs within each window. The fresh window finishes
at IRQ 9,620; after immediate rearm, the next reads occur at IRQs
9,740/9,760/9,780/9,800/9,820 and that window finishes at 19,220. These are
observations from executing all timer interrupts in Unicorn, with ADC
conversions supplied by the test. They are not measurements of physical
interrupt latency, ADC conversion timing, or the analogue response.

The previously published default tables below are retained and reproduced as
the **immediately rearmed, steady-acquisition model**. They must not be labeled
as the fresh first window. The separate startup results below use the corrected
first-window origin. This distinction changes the phase being observed, not
the sample interval or acceptance logic. It does not establish the cause of
the reported silent Sync32 mode and is not a firmware fix.

## Waveform contract

Sync32 emits `0x1F25EB11`, most significant bit first:

```text
00011111001001011110101100010001
```

At each 101 microsecond TX timer tick, emit the current bit, then add 808 to a
zero-initialized accumulator. On reaching 40,025, subtract 40,025 and advance the
bit index modulo 32. Chips consequently last 49 or 50 timer ticks. Their exact
long-term mean is 5.003125 ms, matching the nominal RX sample interval.

| Quantity | Legacy Digital | Sync32 |
|---|---:|---:|
| Nominal chip duration | 5.050 ms | 5.003125 ms mean |
| Nominal chip rate | 198.019802 chips/s | 199.875078 chips/s |
| Distinct chips before repeating the code | 8 | 32 |
| Mean code-frame duration | 40.400 ms | 160.100 ms |
| ON duty | 62.5% | 49.999375% over the full dither cycle |

These chip rates describe the envelope code. They are not the carrier
frequency. The combined Sync32 code and dither state repeats after 160,100 timer
ticks, or 16.1701 seconds / 101 code frames. It contains 80,049 ON ticks.

RX uses the same 48-sample observation window and accepts a phase only with at
most four wrong decisions overall and at most two in each successive 16-sample
block. The existing contrast/high-sum gates remain. Legacy Digital additionally
retains its existing fallback requiring at least two exact `B6B6` windows.
Sync32 has no corresponding exact fallback.

## Code properties

All properties below are exhaustively checked over the finite phase and word
sets; they do not imply immunity to arbitrary physical interference.

- Sync32 has 16 ON chips out of 32 and a maximum run of five equal chips.
- Different cyclic phases have Hamming distance at least 16 over 32 samples and
  at least 20 over 48 samples. The four-error acceptance regions cannot overlap.
- Every ideal 48-sample phase contains 21–27 ON samples, leaving substantial
  high and low groups for the existing robust median strength estimator.
- Its minimum 48-sample distance from any repeated eight-bit word is 14.
- It takes at least seven changed decisions to turn a Sync32 phase into a
  window with two compatible exact legacy `B6B6` occurrences. Consequently a
  four-error Sync32 match cannot be stolen by that legacy fallback.

The receiver accepts both protocols. These code properties therefore do not
establish a lower overall false-alarm rate: a valid legacy signal continues to
be accepted, and Sync32 adds another accepted signature. The new code is neither
a unique transmitter ID nor proof that a coupled signal belongs to the cable
under the probe.

## Nominal timing: seeded additive-noise comparison

Every waveform has a 1,000-count baseline and 300-count high-minus-low amplitude.
Independent uniform integer noise is added to every one of the five simulated
ADC reads. Their minimum and maximum are dropped, and the remaining three are
averaged with integer truncation, using the immediately rearmed sampling origin.
Both protocols use the same phase offsets, noise seeds, and observation time.

| Noise per ADC read | Legacy accepted / 2,048 | Sync32 accepted / 2,048 |
|---|---:|---:|
| None | 2,048 | 2,042 |
| Uniform ±100 counts | 1,692 | 1,998 |
| Uniform ±200 counts | 1,331 | 1,709 |
| Uniform ±300 counts | 544 | 1,123 |

This is an **equal-amplitude, equal-observation-time** comparison. Because the
ON duties differ, it is not an equal-average-power comparison. No output-drive
increase is assumed or implemented by this model.

The coarse phase grid overstates clean coverage. On the separate denser grid,
Sync32 accepts **8,090/8,192 (98.75%)** clean nominal windows; legacy accepts all
8,192. The 102 misses have fractional starting phases 0.203125, 0.20703125,
0.2109375, or 0.21484375 of an RX sample period in this frame. The five-read
aperture straddles dithered chip transitions, producing decisions that do not
fit one fixed cyclic phase within the error budget.

## Clock mismatch

`RX clock ratio` scales the actual sample interval relative to its nominal
value while holding the TX timer fixed. For example, 1.001 means an RX sample
interval longer by 1,000 ppm. This is an injected mismatch, not an estimate of
the physical devices' oscillator tolerance.

| Added relative mismatch | Legacy clean / 8,192 | Sync32 clean / 8,192 | Sync32 coverage |
|---|---:|---:|---:|
| −3,000 ppm | 8,192 | 7,261 | 88.64% |
| −1,000 ppm | 8,192 | 7,860 | 95.95% |
| Nominal | 8,192 | 8,090 | 98.75% |
| +1,000 ppm | 8,192 | 7,861 | 95.96% |
| +3,000 ppm | 8,192 | 7,276 | 88.82% |

At ±1% mismatch, the coarser 2,048-window clean benchmark accepts 1,271 and
1,280 Sync32 windows, about 62%. At ±2%, it accepts 498 and 511, about 25%.
Legacy accepts every clean window in those grids because its short repeated
code and retained exact-match fallback can tolerate the modeled phase slip.

The nominal legacy RX/TX chip ratio is already 5.003125/5.05 = 0.990717822;
Sync32's long-term nominal ratio is exactly 1. The added mismatch above applies
equally to the RX sample interval for both comparisons.

At uniform ±100-count noise, the coarser grid gives:

| Added relative mismatch | Legacy accepted / 2,048 | Sync32 accepted / 2,048 |
|---|---:|---:|
| −3,000 ppm | 1,732 | 1,809 |
| −1,000 ppm | 1,706 | 1,949 |
| Nominal | 1,692 | 1,998 |
| +1,000 ppm | 1,679 | 1,940 |
| +3,000 ppm | 1,691 | 1,804 |

## Fresh-start model, kept separate from the original tables

With `--fresh-start`, the same seeded benchmark and dense phase sweep use the
0.7..1.1 first-window aperture. At nominal timer divisors:

| Noise per ADC read | Legacy accepted / 2,048 | Sync32 accepted / 2,048 |
|---|---:|---:|
| None | 2,048 | 2,016 |
| Uniform ±100 counts | 1,700 | 1,999 |
| Uniform ±200 counts | 1,330 | 1,708 |
| Uniform ±300 counts | 569 | 1,114 |

The corresponding dense clean sweep gives:

| Added relative mismatch | Legacy clean / 8,192 | Sync32 clean / 8,192 |
|---|---:|---:|
| −3,000 ppm | 8,192 | 7,259 |
| −1,000 ppm | 8,192 | 7,856 |
| Nominal | 8,192 | 8,065 |
| +1,000 ppm | 8,192 | 7,862 |
| +3,000 ppm | 8,192 | 7,273 |

At nominal timing, its 127 misses lie at fractional starting phases 0.10546875,
0.109375, 0.11328125, or 0.1171875 in this finite grid. Adding one tenth of a
sample period shifts a continuously swept aperture; the finite phase grid and
seed-to-phase assignments also change which specific windows are counted.
Different counts therefore do not mean the hardware changes sensitivity
between startup and rearm. Both sweeps continue to show narrow phase gaps and
increasing failures under injected clock mismatch.

## What still needs measurement

Measure the emitted envelope timing, actual RX sampling aperture and relative
clock error, signal clipping, and detection continuity while moving the probe.
Compare both modes on the same physical bundle with hidden target selection.
The current fixed-phase receiver does not recover arbitrary chip slips or
track fractional timing, and this model provides evidence of that limitation.

Longer codes do not separate a cable's original signal from a copy coupled into
its neighbors. Electrical confirmation and measured analogue selectivity
remain necessary parts of evaluating cable-finding performance.
