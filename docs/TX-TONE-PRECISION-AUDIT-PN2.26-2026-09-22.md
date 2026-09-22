# TX PN2.26 Tone Probe precision audit

Date: 2026-09-22. Receiver reference: released RX PN1.24.

Follow-up after user authorization: [PN2.27 and PN2.27A implementation and validation](TX-TONE-PRECISION-PN2.27-2026-09-22.md).
The findings below describe the earlier audit of unchanged PN2.26.

**TX has credible opportunities to reduce carrier-switching work and improve Analog frequency alignment. This audit found no new reproducible Tone Probe control defect and no adjustable amplitude-gain control in the active tone path.** A local Analog timing prototype improves weak-input detection in the ideal link model, but physical range, output strength and continuous audio performance remain unmeasured.

The published firmware files are unchanged. This is an audit and emulator experiment, not a new firmware release. PN2.26 and PN1.24 retain their existing owner-tested status; it does not transfer to the prototype.

## Baseline and diagnosis workflow

The `diagnosing-bugs` workflow was applied: establish executable feedback, rank falsifiable hypotheses, probe the real path, and distinguish modeled evidence from device observations. No new device failure was supplied for this audit. The existing user reports establish that TX PN2.26 passed all tested functions and RX PN1.24 had no Digital/Analog signal drop.

| Pinned input | SHA-256 |
|---|---|
| `LPM-10A-TX_PN2.26-qc-display.bin` | `c77579f018bb820532b3c5974ae63fbf04c4e60359188f7e39a8a8f9a1533df8` |
| Raw `APP_LPM-10RX_PN1.24-gain-precision.bin` | `780951565cca543e50d38537cd179ee1793562c6a4642b688c8143b0e4d8b1ce` |
| Published RX PN1.24 update container | `d08285d835562ed7154bdd75bb4d2a12b2875e694adfffe3d2970fbe4625609f` |

The feedback loop executes firmware Thumb instructions in the existing Unicorn harness, including actual carrier GPIO setup, timer initialization, key dispatch, modulation IRQ and RX sampling/analyzers. Seven tone/timer/GPIO regions are byte-identical to PN2.14, including its RIGHT-key recovery path. Independent control, hardware and timer investigations were used to cross-check the findings.

| Ranked hypothesis | Probe and outcome |
|---|---|
| 1. Generic GPIO setup adds avoidable work to each carrier edge. | Confirmed: two `GPIO_Init` calls consume 242 instructions per transition; the two pin-configuration writes are 126 instructions apart. This establishes a performance opportunity, not a measured electrical timing failure. |
| 2. Delayed timer service stretches the modulation. | Confirmed under deliberate withheld-IRQ fault injection. No evidence here establishes missed deadlines on the device. Ordinary FreeRTOS critical sections do not mask this timer's priority. |
| 3. TX/RX frequency alignment affects weak Analog inputs. | Supported in the ideal link model. An Analog-only prototype moves the mean tone close to the RX target bin and improves this finite corpus. Hardware sensitivity remains unproven. |
| 4. Pause, mode changes or reentry leave inconsistent carrier output. | Not reproduced in current PN2.26: all lifecycle tests passed, including exhaustive selected key-preemption points and all 812 existing phase-counter positions. |

## What the transmitter currently generates

Clock initialization programs nominal CPU/AHB 144 MHz, APB1 36 MHz and APB2 72 MHz. Timer clocks are 72 MHz for TIM2 and 144 MHz for TIM1. These are derived from the programmed clock tree and firmware's 8 MHz crystal constant, not a frequency-counter measurement.

| Quantity | Published PN2.26 behavior |
|---|---|
| Carrier | TIM1 PSC 0, ARR 316, CCR1 158: **454,258.675 Hz** |
| Configured OC1 duty | **49.842%**, with complementary output configured |
| Modulation tick | TIM2 PSC 71, ARR 100: **101 µs** |
| Digital | 50 ticks/chip = **5.05 ms**; `10110110` repeats every **40.4 ms**; cursor wraps every 80.8 ms |
| Digital envelope duty | **62.5%**, from the existing code pattern |
| Analog | Six ticks/half-cycle = **606 µs**, or **825.082508 Hz**, 50% envelope duty |

Actual carrier setup starts at `0x0801A664`; TIM1 setup is at `0x08014760`. ON/OFF routines at `0x0801A6EC` / `0x0801A6B0` switch PB13 and PA8 between timer alternate-function and GPIO output modes. They do not adjust a calibrated amplitude setting during tone operation. OFF also drives both pins according to the existing tick-parity behavior; its electrical purpose is not established and a future optimization must preserve it.

GPIO drive strength and slew controls are separate hardware registers (`DS_CFG` / `SR_CFG`, offsets `0x20` / `0x24`), not a calibrated transmitter-gain interface. The active paths preserved seeded values in these registers. Firmware register inspection cannot establish loaded connector voltage, power or useful tracing range. See the [N32G45x reference manual, GPIO register descriptions](https://www.nationstech.com/uploadfile/file/20230822/1692689014562769.pdf).

Consequently, changing carrier duty or increasing pin drive cannot presently be justified as a precision improvement. Stronger coupling could also broaden the area in which nearby cables are detected; connector and receiver measurements are needed to assess that tradeoff.

## Performance and control results

The full timer IRQ was profiled for 10,001 invocations in each mode:

| Mode | Minimum / maximum instructions | Mean instructions |
|---|---:|---:|
| Digital | 102 / 393 | 113.632 |
| Analog | 116 / 451 | 170.757 |

These are instruction counts, not CPU cycles or elapsed microseconds. Flash stalls, electrical transitions, concurrent tasks and worst-case NVIC latency are not simulated. The generic GPIO work is a substantial part of edge handling, so specializing the two pin updates is a concrete optimization candidate. It must preserve unrelated register fields, PB13/PA8 ordering, existing OFF levels, complementary output settings and the recovery cache.

The new PN2.26 lifecycle suite passed **4 tests in 22.304 seconds**:

- Actual key paths cover cold entry, RIGHT, mode switching, pause/resume, exit and reentry.
- All **812 phase positions** are checked: 800 Digital cursor positions and 12 Analog positions.
- The actual timer IRQ is injected at **16,020 unmasked key-instruction occurrences** across selected states. Both the interrupt's output and resumed control behavior are checked.
- Eight existing GUI states cover both languages, both modes and both enable states, including label highlighting.

The inherited carrier/recovery baseline also passed 16 tests. Those historical baseline checks are separate from the hash-pinned current-firmware suite. Existing Thai-font fixture file-handle `ResourceWarning`s appeared during the GUI checks; the tests completed successfully.

The timer priority byte is `0x10`; FreeRTOS critical entry uses `BASEPRI=0xBF`, which does not mask TIM2. PRIMASK masking and hardware stalls remain separate possibilities. Deliberately withholding eight Digital IRQ services delays an edge by 808 µs; withholding two Analog services delays an edge by 202 µs. This demonstrates the consequence of missed service, not an observed device defect.

## Analog alignment experiment

RX PN1.24 samples Analog every 13 TIM5 ticks. With the nominal TIM5 period of 25.015625 µs, its 64-sample bin 17 is centered at **816.797194 Hz**. Current TX Analog is approximately 1.014% higher.

Changing the shared TX tick globally from 101 to 102 µs would move Analog to 816.993464 Hz, but also change Digital chips from 5.05 to 5.10 ms, watchdog heartbeat checks from 101 to 102 ms, and key-beep PWM service from 505 to 510 µs. The service at `0x0800F9CC` was previously mislabeled as a backlight update in the symbol metadata; inspection shows key-beep state, volume and TIM3 CCR3 access. That metadata and one audit comment have been corrected.

Instead, an **emulator-only 64-byte Analog routine** reuses the existing phase halfword at `0x200000DE`: add 165 modulo 2000 each unchanged 101 µs tick; enable the envelope when the phase is at least 1000. Actual Thumb execution over 1,600 IRQs produces:

- **33 cycles per 400 ticks = 816.831683 Hz**, about 0.00422% above the nominal RX bin.
- Exactly 50% envelope duty over the repeating period.
- 62 half-cycles of six ticks and four of seven ticks per period: **606 / 707 µs**.
- Unchanged TIM1 carrier configuration and TIM2 PSC/ARR.

The tradeoff is deterministic edge variation: the average half-cycle is 612.121 µs, but individual edges remain quantized to the timer grid. Mean-frequency alignment does not imply lower instantaneous jitter. This prototype is not a production patch: its lifecycle, older-RX compatibility and electrical behavior are not validated.

### Paired TX/RX execution

The script captures actual GPIO selections from the published TX and the in-memory Thumb prototype, then feeds those traces into the actual RX PN1.24 sampler and analyzers. The link is an ideal square envelope centered at ADC value 2048, at fixed gain 7. Each case starts a fresh acquisition. Analog requires 64 ADC samples; Digital requires 240 ADC reads. Flat input must be rejected.

The initial 192 windows span Digital/Analog, eight phase offsets, four peak-to-peak levels and three modeled tick lengths (100/101/102 µs). All Digital phase cases at levels 12, 24 and 80 were detected; flat input was rejected. The alternate tick lengths rescale a trace in the model rather than execute a retimed TX timer configuration. Another 32 windows use the actual prototype trace.

The expanded comparison uses **127 identical modeled start-time offsets** for both Analog waveforms across their joint 1,200-tick repeat span, adding **1,016 windows**. The prime phase count avoids repeatedly sampling only a few aliases of the 12-tick published waveform.

| ADC peak-to-peak level | Published Analog detections | Prototype detections | Published raw score range | Prototype raw score range |
|---:|---:|---:|---:|---:|
| 0 | 0 / 127 | 0 / 127 | 0 | 0 |
| 12 | 0 / 127 | 0 / 127 | 0 | 0 |
| 24 | **124 / 127** | **127 / 127** | 0–160 | 80–160 |
| 80 | 127 / 127 | 127 / 127 | 1040–1280 | 1160–1440 |

All **1,240 acquisition cases** completed their audit assertions. This does not mean that all inputs were detected: rejection at zero and low levels is reported explicitly above.

The result supports further evaluation of Analog alignment. It is not a measured gain in sensitivity, distance or localization precision. There is no modeled front-end filtering, noise, cable loading, coupling, clipping, settling, oscillator drift or movement. These fresh fixed-gain windows do not establish continuous tracking, AGC recovery or audible dropout behavior. The finite deterministic phase corpus is not a statistical field trial.

## Recommended implementation sequence

1. **Specialize the existing carrier GPIO transition path first.** Preserve the current waveform and UI. Compare actual old/new register writes across seeded unrelated pin fields, OFF polarities, RIGHT recovery and interrupt interleavings. Measure edge spacing on hardware before making timing claims.
2. **Evaluate Analog-only frequency alignment as a separate candidate.** Preserve the shared timer and Digital code. Run old/new waveform comparisons on RX PN1.24 and supported older receivers, including quiet/open input, weak coupling, adjacent cables, strong signals, movement and gain changes. Update the displayed Analog frequency if the candidate is adopted.
3. **Measure the connector before considering output-drive changes.** A scope and repeatable cable/receiver setup should establish amplitude under load, edge shape, tone frequency, distance and neighboring-cable discrimination. The audit supplies no basis for claiming a firmware-only maximum gain setting.

No version bump, flashable candidate, commit, push or release was produced for this audit. The next firmware change should be selected from the evidence above rather than labeled as a fix for an unobserved defect.

## Reproduce and inspect

From the repository root:

```powershell
python docs/experiments/tx_pn226_waveform_audit.py --json docs/experiments/results/tx-pn226-waveform-audit-2026-09-22.json
python docs/experiments/tx_rx_current_tone_audit.py --json docs/experiments/results/tx-rx-tone-pn226-pn124-2026-09-22.json
```

From `LPM-10A/Firmware File/sdk`:

```powershell
python -m unittest test_tone_pn226_lifecycle -q
python build.py --profile pn2.26
```

The PN2.26 dry-run build completed successfully. Both experiment scripts pin their firmware inputs; the waveform audit also verifies its input remains byte-identical afterward. These commands do not write firmware files.

Evidence: [waveform script](experiments/tx_pn226_waveform_audit.py), [waveform results](experiments/results/tx-pn226-waveform-audit-2026-09-22.json), [paired RX script](experiments/tx_rx_current_tone_audit.py), [paired RX results](experiments/results/tx-rx-tone-pn226-pn124-2026-09-22.json), [PN2.26 lifecycle tests](../LPM-10A/Firmware%20File/sdk/test_tone_pn226_lifecycle.py).
