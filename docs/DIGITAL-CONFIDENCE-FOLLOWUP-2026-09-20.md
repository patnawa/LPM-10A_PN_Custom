# Digital confidence follow-up — PN 1.11

## Finding

การลด false detection ด้วยการบังคับให้ fallback มีรหัสช่วงท้ายที่สมบูรณ์กว่าเดิม
ยังไม่ปลอดภัยสำหรับการนำไปใช้จริง: กฎที่ดูดีบนสัญญาณคงที่กลับตัดสัญญาณจริง
เมื่อความแรงลดเร็วระหว่างเคลื่อนโพรบ จึงยังไม่ใส่กฎเหล่านี้ในเฟิร์มแวร์

สิ่งที่มีหลักฐานรองรับสำหรับทำต้นแบบต่อคือ ยกเลิกผลจากรหัสเก่าเมื่อข้อมูลล่าสุด
16 จุดมีค่าเท่ากันทั้งหมด กฎนี้รักษาการรับสัญญาณสะอาด มี noise และขณะเคลื่อนโพรบ
ในชุดทดสอบนี้ แต่แก้ได้เฉพาะกรณีข้อมูลท้ายแบนจริง ๆ และยังไม่แก้ false detection
`uniform_13398` ที่สืบทอดจาก fallback เดิม

No firmware or existing model file was changed by this investigation. This is a
decision report, not a new release, a physical cable test, or evidence that the
system exceeds Fluke IntelliTone.

## Reproduction and evidence boundary

Run from the repository root:

```powershell
python docs/experiments/digital_confidence_followup.py --arm
```

The [retained JSON output](experiments/results/pn111-digital-confidence-2026-09-20.json)
includes the counts, selected counterexamples, latency ranges and script hash.

The [follow-up script](experiments/digital_confidence_followup.py) pins the
complete PN 1.11 artifact and all three imported reference-model files by
SHA-256. The artifact hash is:

```text
3e39ae56832cf92881ffdc46564e293278d6c3f1b55a9832b7a9a8350f031828
```

It executes the delivered ARM detector, overlap handoff, strength estimator,
cadence mapper and publication path for **2,364 windows**: the 2,304 original
clean sampler windows plus 60 selected counterexamples, including the two
held-out weak-clean rejections and inherited noise acceptance. All ARM/model
comparisons passed. The remaining proposal comparison is
mathematical; proposal firmware does not exist. The ARM comparisons check the
published grade, mapped strength score and recent-signal state. All modeled
clocks, ADC values and motion are synthetic.

The fixed sampling corpus uses fresh and immediate-rearm five-read schedules,
128 phases across the eight-symbol code, and RX/TX clock ratios 0.98, 0.99,
0.997, 0.999, 1.0, 1.001, 1.003, 1.01 and 1.02. Each raw ADC sample is reduced
using the current drop-highest/drop-lowest rule. A separate dense clean grid
uses 81 clock ratios and 256 phases, totaling 41,472 windows. A held-out set
uses 4,096 continuous random phases/ratios and amplitudes 9–3,000 with seed
20260921. These are model test domains, not measured oscillator tolerances.

All proposed filters apply only when PN 1.11 currently accepts through its
two-exact-span fallback. They leave full-window local/global fits and existing
upper-rail uncertainty indications unchanged. This restriction matters: these
are not independent replacement detectors.

## Why straightforward tightening is rejected

Of the 2,304 clean fixed-grid windows, 1,068 need the exact fallback. The most
recent exact 16-sample span can finish 24 samples before the window ends.
The latest 16 samples can differ from every fixed binary code phase by six
bits even with no noise, because the five-read aperture crosses chip edges.

| Fallback requirement | Clean windows lost / 2,304 | Noisy accepted windows lost / 6,351 | Decision |
|---|---:|---:|---|
| Latest exact span is no more than 8 samples old | 370 | 1,008 | Reject |
| Latest 16 global-threshold bits have at most 2 errors | 246 | 733 | Reject |
| Latest 16 locally thresholded bits have at most 2 errors | 246 | 693 | Reject |
| Latest exact span's normalized level residual is at most 15% | 113 | 463 | Reject |

The residual rule also fails a clean fresh-start fixture at ratio 1.003,
phase 53/16: its normalized residual is 31.25%. The inherited noise false
case has only 16.37% residual. Consequently a simple residual cutoff cannot
separate those two cases without losing the legitimate sampled waveform.

An absolute recent-range threshold of 9 ADC units also fails: it loses 96
accepted weak-clean cases and 4 accepted weak-noisy cases. For example,
amplitude 12 at steady ratio 0.997, phase 76/16, has only 8 units of recent
range after aperture reduction. The existing fallback still correctly
recognizes its older qualified code span. A threshold copied from the local
eight-sample slicer's contrast requirement is not automatically appropriate
for this different test.

## Lag-eight periodicity proposal and its counterexamples

For reduced samples `x[0]..x[47]`, define:

```text
D = sum(abs(x[i] - x[i-8]), i=16..47)
R = max(x[8:48]) - min(x[8:48])
```

The initial rule retained fallback only when `D <= 8*R`, equivalent to an
average lag-eight difference no larger than one quarter of the last
40-sample range. It looked promising on stationary windows:

- No additional rejection in the fixed clean, noisy or weak-signal corpora.
- No additional rejection in the 4,096 held-out clean cases.
- Every dense-grid clean waveform satisfies it; the largest normalized
  difference is 0.1875, below the 0.25 cutoff.
- It rejects `uniform_13398`: `D=32001`, `R=3800`, so `D > 30400`.

The continuous-motion test invalidates that conclusion. Its streams retain
the same raw samples across overlapping windows, rather than generating
independent windows. Each stream has 160 reduced samples and publications
at ends 48, 64, ..., 160. There are five clock ratios, sixteen phases and
sixteen step offsets per transition, yielding 10,240 publications per row.
Each raw ADC aperture position decides whether the pre-step or post-step
amplitude applies.

| Continuous amplitude transition | Baseline accepted publications | Lost with lag rule and range ≥9 | Lost with revised nonflat + recent-span-or-lag rule |
|---|---:|---:|---:|
| Constant 300 → 300 control | 10,240 | 0 | 0 |
| 100 → 300 | 9,049 | 0 | 0 |
| 300 → 100 | 9,113 | 40 | 38 |
| 60 → 3,000 | 8,718 | 3 | 0 |
| 3,000 → 60 | 8,768 | 111 | 96 |

The revised rule tries to preserve current evidence by bypassing the lag
check when the latest exact span is no more than eight samples old:

```text
recent_range > 0 AND (latest_exact_age <= 8 OR D <= 8*R)
```

It still loses 134 accepted live-code publications. One counterexample is a
300→100 step, ratio 0.98, phase 1/2, cut 55, publication end 64. The matching
spans start at 0, 8 and 16; the last span is 16 samples old. Here `D=2600`,
`R=300`, so the revised rule rejects a real continuing signal. The latest
local bits have only one error, but adding another bypass would require a
new justification and broader testing; it is not adopted to fit this corpus.

**Both lag-based rejection rules are rejected for production.** Passing a
stationary clean grid and removing one known false alarm is insufficient for
a probe intended to move between cables.

## Narrow flat-tail guard

A smaller proposal rejects an exact fallback only when all of its newest
16 samples are identical:

```text
max(x[32:48]) == min(x[32:48])
```

It uses no guessed physical noise floor and no minimum amplitude threshold.
Full-window acceptance and upper-rail uncertainty are outside its scope.

| Corpus | Windows | PN 1.11 accepted | Additional rejection by flat-tail guard |
|---|---:|---:|---:|
| Fixed-grid clean sampler | 2,304 | 2,304 | 0 |
| Noisy sampler, amplitude 300, raw noise ±50/100/200/300 | 9,216 | 6,351 | 0 |
| Weak clean sampler, amplitudes 9/12/25/50/100 | 11,520 | 10,321 | 0 |
| Weak noisy sampler, noise 25%/50%/100% of amplitude | 11,520 | 6,952 | 0 |
| Held-out clean random phases/clocks/amplitudes | 4,096 | 4,094 | 0 |
| Earlier audit, including amplitude steps | 2,490 | 2,482 | 3 old-code/flat-tail cases |
| Fragment placements, lengths 16/23/24/25/31/32/40/48 | 1,224 | 505 | 84 old-code/flat-tail cases |
| Uniform, binary and bounded random-walk noise | 49,152 | 1 | 0 |

It also removes zero accepted publications in all four live-motion
transitions and the constant-amplitude control above. In the 300→0 removal
streams, it removes 354 stale publications that PN 1.11 still accepts from
older code. Across the 1,280 removal streams, the worst first rejected
publication moves from 210.241 ms to 158.609 ms in this model. The result
does not imply every stream improves by 51.632 ms. Some baseline windows
already reject much earlier, and audio scheduling is not included.

The latency calculation uses the last raw ADC read, not just the nominal
reduced-sample boundary. It still excludes processing stalls, actual IRQ
latency, gain/AFE behavior, cable propagation and audible-pulse timing.

### Remaining limits

- The guard does not fix `uniform_13398`. The existing artifact still reports
  amplitude 2,320 and a 35 ms cadence gap from its older qualified span.
- Noise or a baseline drift after signal removal makes the newest samples
  nonflat, so this guard can leave stale indications unchanged.
- A small nonflat tail is not evidence that the code is currently present.
- Finite zero-regression corpora do not establish a universal guarantee.
- The two baseline-held-out rejections are amplitude 13 at continuous phases
  and clock ratios: fresh ratio 1.0013150496255276, phase 7.292676777330792;
  steady ratio 0.9972673782823049, phase 2.4686612634501577. They are existing
  PN 1.11 weak-signal limitations, not regressions introduced by a proposal.
- All reported noise acceptance counts are synthetic counts. They are not
  calibrated false-alarm rates for a cable bundle or premises wiring.

## Bounded next action

The exact-flat-tail guard is suitable for an isolated implementation
prototype, followed by direct ARM comparison, scope/stack checks and device
tests. Any helper that reads the detector snapshot must mask the temporary
tag bits and use the underlying 12-bit ADC values. A new delivered version
must preserve PN 1.11 rather than overwrite that pinned artifact.

The lag/recent-span rules should not be implemented as rejection gates.
Further work on false detection needs independent evidence of code confidence
under varying amplitude, sampling aperture and clock phase. Marking weak
confidence as uncertainty rather than silence is a possible research path,
but it also changes feedback behavior and has not been validated here.
