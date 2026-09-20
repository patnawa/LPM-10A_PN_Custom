# Legacy Digital acquisition and tracking candidate — 2026-09-20

The candidate improves the established B6 Digital waveform without adding a
new TX mode. It recovers many burst-corrupted and moving-strength cases that
PN 1.9/1.10 rejects, while retaining their existing clock-drift fallback. This
is modeled ADC and ARM execution evidence, not a measurement of cable range,
adjacent-cable selectivity, or superiority over Fluke IntelliTone.

## Implemented algorithm

1. Snapshot the complete 48-sample ADC window before altering it.
2. The separate [overlap helper](../LPM-10A/Firmware%20File/rx-sdk/digital_overlap.py)
   keeps the last 32 samples in the acquisition buffer and collects 16 new
   samples. It publishes the new index before re-enabling acquisition. Startup
   and mode/gate invalidation still require a fresh complete 48-sample window.
3. For each of six blocks of eight samples, sort a private eight-halfword
   scratch array. Use `(ordered[1]+ordered[5])//2` as the local slicing threshold.
   Require a high-minus-low separation of at least 9 raw ADC units in at least
   five blocks. These values are algorithm parameters, not calibrated distances.
4. Accept this path only when all 48 decisions fit one cyclic B6 phase, with
   at most four total errors and at most two errors in each 16-sample region.
5. If local fitting fails, clear the temporary tags and execute the established
   global threshold, contrast/high-sum eligibility, bounded fit, and two-exact-
   span fallback. This preserves clean sampling-phase and clock-drift tolerance.
6. For a full fit, estimate strength from code-grouped medians in the latest
   16 samples. For an exact fallback, use the latest complete qualified
   16-sample span. Retain the existing cadence mapper, small cadence deadband,
   and upper-rail/inseparable-level uncertainty indication.

The local fit has priority. Otherwise a previously strong exact span could
mask a newly weaker segment, even after a better local full-window fit was
available. The sampler's existing five ADC reads and drop-extremes reduction
are unchanged.

An early local-only design was rejected: it accepted only 73–75 of 128 nominal
clean sampling phases. Retaining the established fallback is essential; ideal
square-wave tests alone would have missed this regression.

## Reproducible model results

Run from the repository root:

```powershell
python docs/experiments/digital_acquisition_candidate.py
```

The [independent model](experiments/digital_acquisition_candidate.py) imports
the previously ARM-verified PN 1.9/1.10 reference for paired comparison. Its
default random seed is 20260920. Acceptance means a nonzero feedback result,
including the uncertain-reading indication; it does not mean physical cable
identity was established.

| Corpus | Windows | Previous accepted | Candidate accepted |
|---|---:|---:|---:|
| Prior audit counterexamples, including every amplitude-step position | 2,490 | 1,517 | 2,482 |
| Fresh/steady five-read sampling, 9 clock ratios and 5 noise levels | 11,520 | 8,298 | 8,655 |
| Weak signal, 6 amplitudes, 4 noise ratios, 3 clock ratios | 9,216 | 6,055 | 6,374 |
| Every pair of positive-rail positions at all 8 code phases | 9,024 | 0 | 8,880 |
| Competing periodic eight-bit words, excluding B6 rotations | 248 | 0 | 0 |
| Square/sine signals at 13 other period/phase sweeps | 3,312 | 0 | 0 |
| Uniform ADC noise, random binary decisions, and bounded random walks | 49,152 | 1 | 1 |
| Signal ends at every window position, all 8 code phases | 392 | 180 | 180 |

No previously accepted window is lost in these corpora. All 2,304 clean
fresh/steady sampling-phase and clock-ratio cases are retained. The clock
ratio sweep is 0.98, 0.99, 0.997, 0.999, 1.0, 1.001, 1.003, 1.01, and 1.02,
relative to the nominal RX/TX timer model; this is not a measured tolerance
specification for the hardware.

All 8,880 recovered two-rail cases report the correct recent amplitude of
100 ADC units. The remaining 144 fail when both impulses corrupt two of the
three low samples inside one eight-sample block. This limitation is retained
in the test corpus and is not presented as solved.

At nominal clock ratio with amplitude 300 and raw uniform noise ±300, the
steady sampler improves from 37/128 accepted phases to 54/128; fresh startup
improves from 34/128 to 51/128. These are controlled synthetic cases, not field
success percentages.

## Tracking and release timing

The previous non-overlapping detector publishes at roughly 240 ms intervals.
The new helper retains the same 48-sample observation length and publishes
after each 16 newly collected samples, nominally about 80 ms apart after the
first complete acquisition. The DSP operates on its owned snapshot while the
sampler fills the shared acquisition buffer.

For a steady-state amplitude step at each of 16 possible update offsets and
all eight code phases, each of the transitions 100→300, 300→100, 60→3000, and
3000→60 settles to its new mapped strength in **45.028–125.078 ms**. Each
transition has 128 cases. Signal removal, tested as 300→0, yields a rejected
window in **95.059–205.128 ms** across its 128 cases.

These times are measured on an abstract reduced-sample grid with
`T=5.003125 ms`. They exclude ADC aperture, DSP execution, rearm delays, and
the currently scheduled audible pulse. A new startup still requires the full
48-sample capture. They must not be described as measured device response.

The recent median trades some long-window averaging for faster comparison.
The old estimator used as many as 18 lows and 30 highs; a complete recent
16-sample span uses six lows and ten highs. Code qualification still uses
all 48 samples. Larger or structured bursts can defeat either stage.

## ARM implementation and checks

Implementation:
[digital_tracking.py](../LPM-10A/Firmware%20File/rx-sdk/digital_tracking.py).
Tests:
[test_rx_digital_tracking.py](../LPM-10A/Firmware%20File/rx-sdk/test_rx_digital_tracking.py).
The module itself does not add a build profile or change the image size.

Run from `LPM-10A/Firmware File/rx-sdk`:

```powershell
python -m unittest test_rx_digital_tracking -q
```

Seven test groups passed. The six-group full run before the final context
test took 17.8 seconds; the additional PRIMASK/incomplete-acquisition group
also passed. There are **14,714 direct ARM/model window comparisons**, plus
context, guard, footprint, and ownership checks:

- 2,490 prior audit vectors and every movement cut;
- 1,920 modeled ADC sampler phase/clock/noise vectors;
- 1,280 periodic words and seeded noise windows;
- 9,024 exhaustive two-rail position/phase combinations.

The checks assert the published grade, mapped score, recent-signal state,
active/index handoff, exact retained 32 samples, callee-saved registers,
floating-point register preservation, stack restoration, and PRIMASK.
Incomplete acquisition returns without mutating sampled data or publication
state. Tampering with prerequisites fails before any patch writes.

| Region | Code bytes | Reserved bytes |
|---|---:|---:|
| Detector at `0x08009E08` | 276 | 280 |
| Local slicer at `0x0800B5B0` | 88 | 88 |
| Clear-tags helper at `0x0800B608` | 26 | 40 |
| Recent estimator at `0x0800B670` | 106 | 110 |
| Shared sort at `0x0800B6DE` | 42 | 46 |
| Total for this module | 538 | 564 |

The local slicer and clear-tags helper reclaim the two original coefficient
helpers only after verifying the optimized DFT loop no longer calls them.
The module also verifies the exact overlap helper and the parent detector and
estimator bytes. No persistent RAM is added. Local sorting needs 16 scratch
bytes; its worst-case insertion-sort comparison count is 168 for all six
blocks. Maximum observed analyzer stack depth is **184 bytes**.

Observed retired-instruction counts, including the snapshot and overlap
handoff, are 3,721 for a clean local fit, 6,971 for a sampler phase requiring
the established fallback, 3,640 for a flat rejection, and 6,199 for the seeded
random rejection fixture. These are instruction counts, not cycle counts or
hardware deadline measurements.

## Remaining limits

- The noise acceptance `uniform_13398` is inherited from the old exact-span
  fallback. Its two matching signatures cover only 24 samples. The candidate
  does not eliminate this false acceptance. No extra noise window was admitted
  in the default 49,152-window corpus, but that is not a proof for all noise.
- Overlap increases decisions per unit time and correlates consecutive
  windows. Per-window synthetic counts are not a physical false-alarm rate.
- The fallback still accepts some partial-code windows after a signal has
  disappeared; overlap reduces their wall-clock persistence but does not
  establish independent temporal confidence.
- The code cannot distinguish a wanted conductor from another conductor
  carrying the same coupled B6 envelope. Stronger audio alone is not proof of
  correct cable identity.
- Partial clipping need not make the median reach the upper rail. The existing
  uncertainty rule is retained; it is not a complete overload detector.
- Hardware propagation, gain behavior, frequency response, external EMI,
  headroom, field false alarms, and an instrument-to-instrument comparison
  remain outside this model and emulator evidence.
