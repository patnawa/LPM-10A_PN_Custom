# Analog dropout follow-up: TX and RX-layout negative evidence

2026-09-26. Diagnostic-only audit; no firmware, artifact, flash or device state
was changed. The owner's A/B reports RX PN1.30 does not drop with the same TX
PN2.34, cable and knob setting, while RX PN1.31 does. TX is confirmed in Analog
817 Hz. These CPU checks do **not** reproduce or dismiss the hardware fault.

## Pinned inputs

| Image | SHA-256 |
|---|---|
| TX PN2.33 | `84f9fb991a5bf43f0e29d978277ebe76baa58ff21714b430c1b6cef040751e91` |
| TX PN2.34 | `92ebb4cd60e7b652f32ca65cfa21401c1657fa63ee1b945864fed3c74a422227` |
| RX PN1.30 | `407b0ba3b80883e4f640ef7e2040a56004ca780a5bd8b81cf3a371ca04a67135` |
| RX PN1.31 | `3e03d8ac13884a0fb3ad752b551ad346eb8e77e11998d7be9ca599923752094c` |

## TX actual-ARM differential

From the repository root:

```text
python -W ignore::ResourceWarning docs/debug/2026-09-26-rx-tx/tx_analog_dropout_audit.py
Ran 3 tests in 31.746s
OK
```

Both TX images executed 200,000 actual TIM2/Analog/carrier-GPIO iterations,
representing 20.2 seconds at the modeled 101 microsecond timer period. All
200,000 intended gate requests were present. Complete output traces and GPIO
and timer writes matched. Interior half-cycle runs were exactly 31,000 runs of
six ticks and 1,999 runs of seven ticks: no extra output gap. RTOS tick values
crossed the 32-bit wrap boundary; timer configuration and the new Cable Test
RAM sentinel remained unchanged. PRIMASK was restored after every IRQ.

The full composed main initializer and real key handlers were also executed
through eight Cable Test -> Home -> SCAN -> Right -> pause/reentry cycles per
image. Each active Analog segment matched the phase oracle; paused phase stayed
frozen and the carrier stayed off. Results were identical between releases.
An intentionally absent modeled timer interrupt causes the gap oracle to fail,
confirming the detector is not an unconditional pass.

The first harness revision incorrectly required the historical main-entry
initializer to preserve all ordinary callee-saved registers. That expectation
failed on PN2.33 before any candidate comparison. The final fixture checks its
actual main-entry return/stack contract instead; no firmware was changed.

Limits: IRQ arrival, RTOS/logging/queue services and peripheral registers are
modeled. The audit cannot measure scheduling latency, electrical amplitude,
real timer edges, pickup geometry or continuity at the physical jack. It did
not emulate an entire FreeRTOS system or inject physical board faults.

## RX container and appended-page audit

```text
python -W ignore::ResourceWarning docs/debug/2026-09-26-rx-tx/tx_rx_pn131_layout_audit.py
Ran 2 tests in 0.170s
OK
```

| RX | Raw bytes | Container bytes | Application end, exclusive | Header offset/length/end |
|---|---:|---:|---|---|
| PN1.30 | 28,552 | 32,768 | `0x0800D788` | `0x1000 / 0x6F88 / 0x7F87` |
| PN1.31 | 28,752 | 36,864 | `0x0800D850` | `0x1000 / 0x7050 / 0x804F` |

Published PN1.31 raw and update files match their rebuild and canonical
container exactly. The 200-byte helper straddles container offset `0x8000`:
120 helper bytes occupy the old final container page, and 80 occupy the new
one. Neither image approaches the declared reserved/version-page boundary.
The only halfword-aligned direct branch candidate into the appended helper is
the Digital estimator call `0x08009EFA -> 0x0800D788`.

Eighteen actual Analog analyzer cases covered fresh/sustained feedback and
normal/clipped/rejected input, each with the real appended tail, an all-zero
tail, and an erased-`FF` tail. Feedback and publication-marker values matched
in all cases; no instruction or data access entered the appended tail.
This weakens a simple missing-tail explanation for Analog dropout. It does
not establish what bytes the physical bootloader programmed, nor exclude
corruption elsewhere. Physical flash readback was not available.

Conclusion: no TX change is indicated by this audit or the owner's A/B. The
remaining investigation belongs to the RX PN1.31 delta and its real sampling,
gain and feedback integration. These negative results are not a hardware
validation pass for RX PN1.31.
