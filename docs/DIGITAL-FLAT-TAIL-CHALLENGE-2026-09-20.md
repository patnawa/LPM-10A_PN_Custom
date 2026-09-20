# Challenge to the exact-flat-tail guard — 2026-09-20

## Decision

**Do not promote an unconditional flat-tail-to-silence rule as an overall
performance improvement.** A flat newest 16-sample tail can represent signal
removal, ADC clipping, a gain/observation change, or a valid brief contact
that ended before the first complete acquisition was published. The same
rule that removes stale strength can erase that contact's only indication.

The narrow supported revision is: **when an already accepted exact fallback
has all sixteen newest ADC samples at 4095, report the existing uncertainty
state instead of the older span's normal strength.** Preserve existing
uncertainty outcomes. Leave lower-zero and interior-flat behavior unchanged
until a policy explicitly balances brief-contact awareness against release
speed. This does not solve all stale indications or noise acceptance.

รายงานนี้พบข้อโต้แย้งสำคัญต่อการทำให้เสียงเงียบทันทีเมื่อข้อมูลท้ายแบน:
อาจเป็นสัญญาณแรงจน ADC อิ่มตัว หรือผู้ใช้เพิ่งกวาดผ่านสายถูกเส้นช่วงสั้น ๆ
จึงไม่ควรสรุปว่าความเงียบที่เร็วขึ้นแปลว่าหาสายได้ดีขึ้นทุกกรณี

## What was tested

New script:
[digital_flat_tail_challenge.py](experiments/digital_flat_tail_challenge.py).
Existing firmware and reference models were not edited.

```powershell
python docs/experiments/digital_flat_tail_challenge.py --arm
```

The script pins the complete PN 1.11 image:

```text
3e39ae56832cf92881ffdc46564e293278d6c3f1b55a9832b7a9a8350f031828
```

**693 current-image ARM/model comparisons passed**: 672 prefix/tail fixtures,
six raw-transfer hypotheses, three near-flat counterexamples and four
publication windows for a representative brief-contact stream, plus eight
structured-random policy-change examples. They verify
the existing published grade, mapped strength and recent-signal state.

The policy comparisons and the complete 2,016 brief-contact streams are
model results. None of the proposed policies was executed as firmware by
this script. Raw-transfer examples are explicitly synthetic hypotheses;
they do not claim measured gain, clipping voltage, coupling or ADC behavior
for the LPM-10A hardware.

## A scope error in a pre-estimator implementation

The [preceding model](DIGITAL-CONFIDENCE-FOLLOWUP-2026-09-20.md) evaluated flat
rejection only for normal-strength exact fallbacks:
`reason == 'established'` and `phase is None`.

A branch placed before the strength estimator cannot assume that scope. It
also intercepts exact fallbacks whose old qualified span would yield
`UNCERTAIN` because its high median is clipped. In the new 672-vector matrix:

| Current exact-fallback result | Flat tail 0 | Flat interior tail | Flat tail 4095 | Total |
|---|---:|---:|---:|---:|
| Normal strength | 30 | 115 | 27 | 172 |
| Existing uncertainty | 20 | 78 | 18 | 116 |

There are 288 accepted exact fallbacks in total. The earlier established-only
silence model removes 172; a pre-estimator all-exact silence branch removes
**288**, including the **116 existing uncertainty indications**. Those are
different policies and must not share the earlier model's validation claim.

One example is 24 valid B6 symbols at ADC low 0/high 4095, followed by 24
samples at 1. PN 1.11 reports uncertainty. A pre-estimator flat check would
silence it; the earlier established-only model would preserve it.

## Upper clipping is not signal absence

The direct fixture is:

```text
samples 0..31: B6, ADC low=1000 and high=4000
samples 32..47: all 4095
```

Current PN 1.11 qualifies an earlier exact span and reports amplitude 3000,
with normal cadence grade/gap 30. Its existing upper-rail estimator check
does not catch the newest clipping because that estimator reads the older,
unclipped span. Both flat-to-silence policies turn this into rejection.

A separate five-read example leaves the transmitted code running and adds
an offset large enough that both levels clip to ADC 4095. It produces the
same stale normal-strength outcome and the same silence regression.
This is a constructive counterexample, not a claim that this offset has
been measured on the actual device.

Reporting uncertainty is defensible here: current strength cannot be
resolved from a tail containing only the maximum ADC code. It does not
prove cable identity or even that the clipping came from the target signal.

**Do not treat lower 0 symmetrically.** Zero is also a valid signal-off
envelope baseline, and existing firmware intentionally permits genuine LOW
samples at zero. A continuing waveform shifted below the ADC floor and a
removed signal returning to a zero baseline are indistinguishable in these
synthetic observations. Automatically calling all-zero tails overload would
prolong an indication after genuine removal without enough evidence.

## Brief legitimate contact can disappear entirely

Each coherent stream models five raw ADC reads per reduced sample, including
the existing drop-extremes reduction. It has 96 reduced samples and first
publication at 48, followed by 64, 80 and 96. The corpus covers:

- Contact starts at 0, 4 or 8 nominal reduced-sample periods.
- Contact durations 16, 20, 23, 24, 25, 31 or 32 periods.
- RX/TX clock ratios 0.98, 1.0 and 1.02.
- 32 phases spanning the B6 code; amplitude 300 on baseline 1000.

This yields 2,016 streams. PN 1.11 indicates code in 516 of them. For **233
of those 516**, a flat-to-silence rule removes every indication in the entire
stream. Adding an upper-rail exception does not fix these interior-flat
brief-contact cases.

Example: contact starts at 0, lasts 23 nominal sample periods (about 115 ms),
ratio 0.98, phase 0. At publication end 48, PN 1.11 reports amplitude 300 and
grade 80 from its qualified earlier span. Publications 64, 80 and 96 all
reject. Flat-tail silence suppresses that first and only indication.

This is not a fabricated bit-word acceptance: the fixture uses the modeled
TX B6 waveform and actual five-read aperture convention. It is still not a
physical sweep over a cable. Whether a delayed brief-contact alert helps
or confuses a user requires the intended feedback policy and device tests;
silencing it cannot be labeled a universal improvement.

## Quantization, gain changes and coupling ambiguity

Three raw-transfer hypotheses generate byte-identical observed windows:

1. A formerly strong signal is removed; the ADC returns to baseline 1000.
2. The code continues, but its resolved amplitude becomes 0.4 ADC units, so
   both levels quantize to 1000 under the stated integer quantizer.
3. The observation path becomes constant at 1000 through a gain/blanking
   hypothesis.

No firmware classifier can determine which hypothesis happened from those
identical samples alone. A rejection can mean “no currently resolvable code”;
it cannot establish physical signal absence. The gain example does not
assert that the RX's gain control actually blanks the ADC this way.

Similarly, code-conditioned amplitude cannot identify whether the resolved
signal came from the target or a same-code coupled neighbor. The script
records equal-observation hypotheses without assuming the real front end
adds demodulated envelopes linearly.

Exact equality is also brittle. An old qualified span at low 0/high 4094
followed by fifteen samples at 4095 and one at 4094 is *not* flat. Every
flat-only policy leaves its stale amplitude 4094/grade 21 unchanged. The
same holds for fifteen zeros plus one 1, or fifteen 1000s plus one 1001.
A broader near-flat threshold would need independent justification; the
previous investigation already found weak-clean regressions from a 9-unit
range threshold.

## Explicit policy comparison

All policies below start only after the existing detector accepts through
its exact fallback. Other acceptance paths remain outside their scope.

| Proposed policy | Normal outcomes silenced in matrix | Normal outcomes changed to uncertainty | Existing uncertainty preserved? | Brief streams whose only indication is erased |
|---|---:|---:|---|---:|
| Silence flat normal-strength fallbacks only | 172 | 0 | Yes | 233 |
| Silence all flat exact fallbacks before estimation | 172, plus 116 already uncertain | 0 | No | 233 |
| Tail 4095 or prior uncertainty → uncertainty; other flats → silence | 145 | 27 | Yes | 233 |
| Any accepted flat tail → uncertainty | 0 | 172 | Yes | 0 |
| Only tail 4095 → uncertainty; preserve other behavior | 0 | 27 | Yes | 0 |

Changing every accepted flat tail to uncertainty removes the false precision
of old strength and preserves brief-contact awareness. However, it also
retains an uncertainty alert after real signal removal, including at a zero
baseline. It must not inherit the previous faster-silence latency claim.
The existing uncertainty state uses different audio behavior; publication
grade 1 is a sentinel, not a 1 ms normal-strength cadence.

The last policy is the narrow recommendation for an isolated firmware
prototype: it addresses an evidenced missed upper-clipping indication,
preserves the previous eligibility and contact behavior, and makes no
unsupported decision about lower zero. It does **not** improve every flat
tail, eliminate inherited `uniform_13398`, solve near-flat clipping, or
establish that performance exceeds a commercial probe.

## Selected upper-only oracle and broader comparison

The independent oracle is `upper_flat_measure(samples)` in the new script.
It returns the existing mathematical PN 1.11 result unchanged except when
the accepted result is an exact fallback and all newest sixteen raw ADC
values are 4095. In that case its result is:

```python
{'gap': 1, 'amplitude': None, 'reason': 'uncertain', 'phase': None}
```

This includes an exact fallback that was already uncertain; its uncertainty
is preserved. A full-window fit is not reclassified by this oracle. No
minimum range, lower-rail rule, lag threshold or burst-suppression rule is
included.

The selected policy was compared across **101,522 additional model windows**:

| Corpus | Windows | Current/proposed accepted | Normal strength → uncertainty |
|---|---:|---:|---:|
| Structured random prefix/tail contexts | 10,000 | 2,484 / 2,484 | 306 |
| Clean five-read sampler | 2,304 | 2,304 / 2,304 | 0 |
| Noisy five-read sampler | 9,216 | 6,351 / 6,351 | 0 |
| Weak clean sampler | 11,520 | 10,321 / 10,321 | 0 |
| Weak noisy sampler | 11,520 | 6,952 / 6,952 | 0 |
| Held-out clean phases/clocks/amplitudes | 4,096 | 4,094 / 4,094 | 0 |
| Previous audit and amplitude-step counterexamples | 2,490 | 2,482 / 2,482 | 0 |
| Fragment placements | 1,224 | 505 / 505 | 0 |
| Uniform/binary/random-walk noise | 49,152 | 1 / 1 | 0 |

The structured random seed is 20260922. It varies prefix baseline, contrast,
phase, code duration and small sample perturbations, followed by upper-flat,
lower-flat, interior-flat or near-upper-flat tails. All 306 changed cases
were accepted exact fallbacks with newest sixteen values at 4095. Every
other result was identical, and no accepted window was silenced. These are
model comparisons; the ARM count remains 693, not 101,522.

For the 2,016 brief-contact streams, upper-only reclassification changes
**zero of 8,064 publications**. Consequently it retains all 516 baseline
detected streams, including the 233 that general flat-tail silence would
erase. Their previous short-contact behavior is retained exactly, not
converted to an uncertainty indication. The inherited random-noise failure
is also retained and is not presented as fixed.

## Implementation and promotion conditions

A prototype must distinguish exact fallback from a full-window fit, inspect
the underlying 12-bit ADC samples rather than their temporary tag bits,
preserve existing uncertain publications and handle normal-to-uncertain
transitions through the established publication path. It must verify stack,
register, interrupt-mask and retained-buffer ownership as well as output
grades. Merely matching the normal-strength flat-tail model is insufficient.

PN 1.11 remains this investigation's pinned comparison artifact. The
[retained JSON](experiments/results/pn111-flat-tail-challenge-2026-09-20.json)
contains the model results and source-script hash. The later
[PN 1.12 implementation](TONE-OVERLOAD-PN1.12-PN2.14-2026-09-20.md) adopts only
the upper-rail uncertainty rule, with its own candidate ARM tests. No broad
flat-tail silence rule is delivered. Device measurements and comparative
probe evidence are still required for the original performance objective.
