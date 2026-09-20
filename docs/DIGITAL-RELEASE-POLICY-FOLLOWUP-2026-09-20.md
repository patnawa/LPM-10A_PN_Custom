# Digital release-policy investigation — PN 1.12, 2026-09-20

## Decision and current field report

**No production freshness/hold change is justified by this investigation.**
The latest owner clarification is a **single continuous sound lasting about
one second after the TX UI shows Pause**, rather than separately perceived
beeps. Analog does not show the same one-second tail. The publication-state
model below does not reproduce or explain that continuous sound. It must not
be presented as proof that a small release-policy change fixes the report.

Earlier work in this investigation considered repeated indications after
moving the probe away. Those experiments remain useful for rejecting unsafe
policy changes, but the latest continuous-sound clarification takes priority.
The separate actual IRQ/audio/PWM and TX cessation investigations are needed
to address the reported behavior.

## Scope and reproduction

```powershell
python docs/experiments/digital_release_policy_followup.py
```

Retained output: [publication-policy results](experiments/results/pn112-digital-release-policy-2026-09-20.json).

The [new model](experiments/digital_release_policy_followup.py) checks the
PN 1.12 artifact SHA-256:

```text
4ea18c52bde25353a9a38dbf46775425860f7859bc2c10e3c908a7bff4044403
```

It uses the separately ARM-validated upper-only detector oracle and coherent
five-read ADC streams. It models grade publication, freshness and periods
when another tone would be eligible to start. It **does not execute ARM in
this run or model an actual audible pulse, speaker PWM, interrupt delay or
device elapsed time**. No firmware or earlier model was edited.

The relevant distinction is that a rejected complete window publishes
`GRADE=0`. That prevents another tone even if the recent-signal counter has
not expired. Therefore a 300 ms freshness window is not automatically a
300 ms hold added after every rejection.

## Policies compared

All state-aware changes below preserve PN 1.12 upper-rail uncertainty.

| Policy | Definition |
|---|---|
| Current behavior | Refresh freshness on every accepted publication |
| Flat after prior grade | Suppress a normal exact fallback with a flat newest-16 tail only when the immediately preceding published grade was nonzero |
| Flat after recent signal | Suppress the same fallback whenever a previous refresh is still within 300 ms, even if a rejection intervened |
| Do not refresh old exact span | After a prior nonzero grade, retain the normal result but do not refresh freshness when its latest exact span is at least 16 samples old |
| Freshness 120 or 150 ms | Preserve detection; expire eligibility earlier if no accepted publication refreshes it |
| Eight-sample hop | Keep the same 48-sample qualification window but publish after eight new samples instead of sixteen |

The first policy exception refers to a **prior grade**, not proof that a
sound was actually emitted. A queued quiet interval, an active confirmation
tone or speaker state could defer audible feedback. Consequently preserving
first publication acceptance does not by itself prove that a brief cable
visit remains audible.

## Hard-zero cessation does not produce a one-second model tail

The abrupt cessation corpus contains 1,280 coherent streams: five RX/TX
clock ratios, sixteen phases and sixteen cessation offsets. Amplitude is
300 before cessation, then exactly zero on ADC baseline 1000. Publications
use the nominal five-read acquisition timing and no foreground delay.

| Policy | Worst end of repeat eligibility after cessation | Changed grades |
|---|---:|---:|
| Current behavior, 300 ms freshness | 206.839 ms | 0 |
| Prior-grade flat suppression | 157.040 ms | 331 |
| Recent-counter flat suppression | 157.040 ms | 331 |
| Do not refresh old exact spans | 206.839 ms | 0 |
| Freshness 120 ms | 206.839 ms | 0 |
| Freshness 150 ms | 206.839 ms | 0 |
| Eight-sample hop | 166.014 ms | 0 |

These are **repeat-eligibility endpoints**, including intervals whose grade
was published just before cessation. They are not the end of an actual
running pulse. An active pulse is outside this model. None of the streams
retains modeled eligibility one second after hard-zero cessation.

Shorter freshness alone has no benefit here because the next rejection
clears the grade before either timeout matters. An eight-sample hop reduces
this bound by approximately 41 ms while doubling the nominal analyzer
invocation rate. This report does not establish that the extra foreground
load fits the actual device's timing.

Prior-grade flat suppression shows a narrow approximately 50 ms opportunity
on ideal zero cessation, not a fix for a one-second continuous sound. Even
small nonflat input noise can make an exact-flat rule do nothing.

## Brief contacts and reacquisition

The 2,016 first-contact streams from the preceding investigation contain
516 streams accepted at least once by the current detector. All four
publication-state policies preserve those 516 accepted streams and leave
the first publication unchanged. **This is acceptance evidence, not an
audible-alert test.** Shorter freshness is not justified by this result.

Repeated-contact testing exposes a distinction between prior grade and the
recent counter. There are 233 baseline reacquisition events after at least
one rejected publication:

- Prior-grade flat suppression preserves all 233.
- Recent-counter gating suppresses three reacquisitions because the recent
  counter remains fresh from an earlier contact despite an intervening
  rejected window.

One counterexample has an eight-sample gap, a 23-sample new contact, nominal
clock ratio and phase 1.5. At publication end 112 the current detector
reacquires grade 80, but recent-counter gating publishes zero. A recent
timestamp is therefore not an adequate “already alerted about this contact”
flag.

## Shorter freshness plus old-span suppression causes valid losses

The continuous motion/noise corpus contains 10,368 publications, 8,403 of
which are currently eligible. It includes constant amplitude, upward and
downward steps, weak residual code, three clock ratios and four raw-noise
levels.

With the existing 300 ms freshness, the tested state-aware rules do not
shorten an eligible live-code interval in this corpus. Freshness 150 ms
alone also makes no change under the timely publication assumption.

However, **150 ms freshness combined with not refreshing old exact spans
shortens 1,003 valid eligibility intervals**. This includes clean constant
amplitude 300 at clock ratio 0.98. A late exact span can be needed by a valid
aperture/clock-phase window; absence of a recent complete span is not proof
that the signal ended. This combined policy is rejected.

The audio scheduler also permits quiet gaps up to 160 ms and active normal
or uncertain pulses. A shorter 120/150 ms freshness interval must therefore
be checked against pending-audio states before recommendation. This model
does not establish that a single accepted brief contact would sound before
the shorter timeout. Keeping the current hold is the defensible choice
until actual audio-state checks show otherwise.

## Sustained-input hypotheses and their limits

Additional synthetic streams test what could sustain repeated *eligibility*:

- Residual code amplitudes 9–150 ADC units keep accepting in all 24 tested
  phase/clock streams beyond one second. Many remain eligible at the end of
  the roughly five-second observation. A fresh accepted code continues to
  refresh the timeout, so shortening freshness is not a removal detector.
- A transmitted code whose resolved amplitude decays with a 500 ms
  exponential time constant retains eligibility up to about 1.877 seconds;
  a 1,000 ms time constant extends it to about 3.681 seconds.
- True zero code after cessation, with independently seeded raw additive
  noise of ±5, ±25, ±100 or ±300 ADC units, does not retain eligibility beyond
  one second in the 24 streams per noise level tested here.

These examples do not establish that the hardware exhibits those fades or
noise distributions. In particular, a continuing coded fade is not the same
as a simple unmodulated DC envelope decay. Once TX is confirmed to stop,
ongoing coupled code is not an adequate explanation unless delayed TX output
or another signal source is demonstrated. None of these publication examples
explains a single continuously energized speaker pulse by itself.

## Follow-up boundary

The model supports rejecting a freshness-only fix, recent-counter contact
gating and the tested 150 ms/no-refresh combination. It identifies a small
prior-grade flat-tail opportunity that still requires actual queued-audio
verification and does not match the reported one-second symptom.

The next evidence should establish the actual BEEP countdown, speaker/PWM
state and interrupt progress during the reported interval, plus TX output
cessation. Until that evidence is available, no release-policy candidate
from this report should be described as a verified fix or shipped on that
basis.
