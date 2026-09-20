# PN 1.11 continuous Digital acquisition / interruption audit

The four tests in
[`test_rx_tracking_streams.py`](../LPM-10A/Firmware%20File/rx-sdk/test_rx_tracking_streams.py)
execute the exact delivered RX artifact with SHA-256
`3e39ae56832cf92881ffdc46564e293278d6c3f1b55a9832b7a9a8350f031828`.
They do not build a substitute profile or modify production firmware.

Result: **all four tests passed**, 28.886 seconds for the recorded standalone
run. No sample-retention corruption, foreground-snapshot corruption, lost
completed next window, or premature publication after key/gate invalidation
was found in these schedules.

| Test | Executed coverage |
| --- | --- |
| Continuous streams | 160 completed analysis windows across four streams, each with 40 consecutive windows. The first window acquires 48 reduced samples; each subsequent window retains 32 and acquires 16. This stream portion executes 538,400 actual TIM5 interrupts and supplies 13,440 ADC readings. |
| Motion / noise input | Amplitude steps 300 → 1000 → 60 → 0 → 300 ADC units, phase offsets 0, 0.3125, 3.875 and 7.75 chips. The last two streams add ±0.3% clock-ratio stress and pairs of rail spikes in the raw ADC reads. Both local fitting and inherited fallback paths execute. |
| Long timer preemption | 18 schedules: interrupts arrive at snapshot, overlap rearm, local slicing, sorting, global fallback and recent-strength estimation. Runs of 1, 139 or 3,217 actual timer IRQs can complete the next window while foreground analysis is paused. That completed window remains available for the next foreground call. |
| Instruction-boundary preemption | 689 schedules covering first and last executed visits to 436 path-specific instruction addresses (181 on the local-fit trace; 255 on the fallback trace). This includes 253 last-loop-visit injections. Each schedule delivers 3,217 actual TIM5 IRQs before resuming foreground analysis. |
| Real key / gate invalidation | 10 schedules interrupt analysis with the actual mode-key scanner or actual gate-close/reopen helper. After the main boundary, Digital must acquire all 240 raw readings / 48 reduced samples again; partially retained old data cannot publish a new strength. |

For every continuous frame, the test reconstructs reduced values directly from
the recorded five raw ADC readings using `(sum − min − max) // 3`. It compares
the entire completed firmware buffer to that chronological history, then checks
the 32 retained values. Foreground feedback is checked against the existing
independent reduced-sample reference, including the inherited gap hysteresis.
The interruption sweep also checks that firmware preserves both the retained
prefix and the newly acquired suffix when the next window becomes complete.

The test runner batches calls in a small emulated Thumb loop only to reduce
host overhead: every individual interrupt executes the actual firmware ISR,
including interrupts that do not read the ADC. It does not skip timer counts
or write synthetic completed samples directly into the live sampler buffer.
The instruction sweep starts from a saved state obtained by an actual full-grid
acquisition; this avoids redundantly reacquiring that same initial frame for
every interruption position.

Reproduction, from `LPM-10A/Firmware File/rx-sdk`:

```powershell
python -m unittest test_rx_tracking_streams.TrackingStreams -v
```

The recorded standalone tool run ended with `Ran 4 tests in 28.886s` / `OK`.
The combined follow-up run passed eight groups in 40.300 seconds, including
these four, two Analog transient tests and two existing fragment tests.
The [retained output](experiments/results/pn111-followup-2026-09-20.log) and
[environment/source-hash record](experiments/results/pn111-followup-2026-09-20.json)
are stored in the repository. Counts from this combined run and the standalone
run overlap and must not be added together.

Limits: the ADC input is an idealized envelope based on the nominal TX
101 µs timer tick / 50-tick B6 chip and RX 25.015625 µs timer tick. Analogue
propagation, cable coupling, ADC settling, real oscillator error and Fluke
hardware are not measured. Interrupted CPU context is explicitly saved and
restored; hardware exception stacking, NVIC priorities and ISR cycle deadlines
are not modeled. Deliberately pausing foreground code for 3,217 timer calls is
an ownership stress test, not a measured or claimed processor runtime. These
results support the firmware's buffer ownership and invalidation behavior,
not physical cable-identification accuracy or superiority over another probe.
