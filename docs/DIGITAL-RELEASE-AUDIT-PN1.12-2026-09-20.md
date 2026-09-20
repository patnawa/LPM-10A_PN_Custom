# Digital release audit — pinned RX PN 1.12

**Normal modeled code retention does not reproduce the owner's approximately
one-second continuous Digital tone after TX Pause.** The latest clarification
is one continuous sound after the TX UI shows Pause, with Analog stopping
promptly; it is not a confirmed sequence of separate extra pulses. With actual TIM5 acquisition,
foreground detection, TIM1 countdown and speaker-PWM instructions, the latest
sound ended **223.114 ms after the modeled carrier envelope ceased** in the
96 clean-loss cases. The owner's physical observation remains unresolved.

Test source:
[`test_rx_digital_release_audit.py`](../LPM-10A/Firmware%20File/rx-sdk/test_rx_digital_release_audit.py).
Durable results:
[`pn112-digital-release-audit-2026-09-20.json`](experiments/results/pn112-digital-release-audit-2026-09-20.json).
Exact tested firmware SHA-256:
`4ea18c52bde25353a9a38dbf46775425860f7859bc2c10e3c908a7bff4044403`.

Seven distinct groups passed across an original five-group run and subsequent
focused runs; this is **not** a combined seven-group execution. The original
run took 61.961 seconds. The gate/pulse group was rerun after adding two cuts
inside active pulses (5.022 seconds); the new interrupt-mask group passed in
0.236 seconds and the deliberately withheld-TIM1 group in 0.919 seconds.
The JSON records these runs separately. Production bytes were not edited.

| Condition | Result on the nominal scheduled timer grid |
| --- | --- |
| Abrupt clean loss; three strengths, eight phase offsets, four update offsets | 96 streams, 4,720,224 actual TIM5 IRQs. First rejected publication 21.010–201.013 ms after loss; final PWM sound ends 0–223.114 ms after loss; at most four further short pulses. |
| Old exact-code fallback retained after loss | Worst example accepts at +41.010 and +121.011 ms, with the latter using samples 8–23 of the 48-sample window although its newest 16 are flat. It rejects at +201.013 ms; an already-started pulse ends at +223.114 ms. This behavior explains a short release tail, not one second. |
| Foreground stops, timer interrupts continue | No new publications renew `RECENT`. Pulse starts remain within 300 countdown ticks of the last accepted publication. In the fixture, all sound ends +234.121 ms after loss. |
| Foreground resumes after holding a completed buffer | A distinct stale-data gap exists: a completed frame whose newest ADC reading is **1,209.129 ms old** is accepted when foreground resumes. New pulses start +1,200.156 ms after loss and final sound ends +1,348.048 ms. The fixture deliberately stalls foreground from 610 to 1,850 ms; this is not evidence that the real device experiences such a stall. |
| Weak coherent code remains | Residual modeled contrasts 9, 12, 25 and 60 ADC units can refresh accepted observations and keep generating pulses beyond one second. This is continued modeled code reception, not a frozen countdown. Actual TX Pause makes residual-code reception an incomplete explanation unless another source or persistent sampled input is demonstrated. |
| Actual gate-close helper / main boundary | Prevents subsequent pulse starts. A current normal pulse finishes after 18.174 ms in the selected cut; a current uncertainty pulse finishes after 80.175 ms. Neither is restarted by the gate closure. |
| Deliberately withhold TIM1 for one second, while TIM5 and main continue | Reproduces the **type** of the latest symptom: one existing pulse stays continuously audible until +1,014.071 ms after loss, even though fresh data rejects at +182.014 ms. No new pulse starts. This injected timer-delivery fault is not evidence that it occurs on the physical device. |

The PWM log observes the actual TIM5 CCR4 writes: alternating 700/900 duty
values are sound, 800 is silent. It therefore follows actual tone output
requests instead of inferring audio merely from `GRADE` or `RECENT`.
Complete PWM edge pairs retained in the normal fixtures give a maximum
continuous normal pulse of **30.01875 ms** and an uncertainty pulse of
**100.0625 ms**. The deliberately withheld-TIM1 fixture creates one
**1,030.043375 ms** pulse; its countdown, rather than detector eligibility,
is what was intentionally prevented from advancing.

The scheduling uses the exact nominal register periods: TIM5 ARR 1600 with
PSC 0 gives 1,601 timer-clock cycles; TIM1 ARR 64000 with PSC 0 gives 64,001
cycles. Both clocks are nominally 64 MHz. Thus 300 countdown ticks are
300.0046875 ms, and normal / uncertainty pulses have 30 / 100 countdown ticks,
with an additional speaker-update phase of at most about 0.2 ms.
An independent execution of `tim1_init` at `0x0800A908`, starting with
reset-like MMIO, also explicitly writes TIM1 RCR (`0x40012C30`) to zero;
PSC is zero, ARR is 64000, CR1 is 1, SMCR is zero and DIER is 1. Thus that
initialization does not request a tenfold repetition-counter divider. The
actual TIM1 handler decrements `BEEP` on every delivered update, without a
software divide-by-ten. This isolated init test is not a physical register
read and does not prove the later hardware state.

`RECENT` is set to 800 on acceptance, while the repeat scheduler requires
`RECENT > 500`. A rejected fresh window sets `GRADE` to zero, immediately
preventing additional starts even before that 300-tick expiry. An active pulse
is intentionally allowed to finish; this preserves normal pulse/key ownership.

The stale-buffer case is actionable independently of the owner's exact cause:
the completed shared frame currently has no age qualification. Delayed
foreground processing can therefore promote old signal evidence to a new
800-tick publication. A proposed age guard should reject only excessively aged
completed acquisitions, require fresh data again, and preserve ordinary brief
contacts. It must not repeat the previously rejected policy of silencing every
flat recent tail. Reusing sampler metadata also requires an atomic handoff:
an age-writing ISR must not overwrite index 32 between the overlap helper's
index store and its final `ACTIVE = 1` store.

The delayed-buffer fixture has a long quiet interval before sound resumes;
it does **not** reproduce uninterrupted beeping for the entire one-second
interval. That distinction matters when comparing to the owner's observation.

An independent instruction trace on the same pinned image found no Digital
analysis path leaving interrupts disabled: normal, uncertainty, exact fallback
and upper-tail paths each have a maximum contiguous `PRIMASK=1` span of
15 executed instructions; rejected/noise paths have 13. Analog spans are
13–17 instructions. Every successful path restores `PRIMASK=0`.

The actual ADC routine was also executed with the established synthetic
completion model. Immediate completion masks 107 instructions; injected
500- and 2,000-instruction completion delays mask 602 and 2,102 instructions.
Failure to complete reaches 2,597 masked instructions and then requests reset.
These are retired instruction counts, not hardware cycles. They do not prove
the absence of real interrupt-priority, peripheral or bus-delay problems, but
do not support a one-second interrupt mask in the ordinary Digital DSP code.

Reproduce from `LPM-10A/Firmware File/rx-sdk`:

```powershell
python test_rx_digital_release_audit.py --json ../../../docs/experiments/results/pn112-digital-release-audit-2026-09-20.json
```

Limits: ADC conversion and the analogue link are modeled. The clean-loss test
starts its clock at cessation of the sampled TX envelope, not at the user's
button press. TX key/request latency is outside this RX test. Foreground gets
one opportunity per nominal TIM1 period and completes between scheduled
events; processor cycles, NVIC contention, actual oscillator error, analogue
settling and hardware interrupt starvation are not measured. A physical
one-second result can therefore contradict this normal scheduling model
without contradicting the instruction-level results. No Fluke performance
claim follows from these tests.
