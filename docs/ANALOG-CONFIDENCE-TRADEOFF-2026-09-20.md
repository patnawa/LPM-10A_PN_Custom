# Analog transient-confidence follow-up

**ผลตรวจ:** การรอผลยืนยันสองหน้าต่างลดเสียงหลอกจาก noise จำลองได้มาก
แต่ทำให้พลาดสัญญาณอ่อนที่พบเพียงช่วงสั้น เช่น ขณะกวาดโพรบผ่านสาย
จึงยังไม่ใส่นโยบายนี้ใน RX PN 1.11 โดยไม่มีผลกวาดโพรบและ noise จากเครื่องจริง
ไฟล์เฟิร์มแวร์และ checksum เดิมไม่เปลี่ยน

This tests a specific proposed improvement, not a new firmware release. It
compares the existing one-window Analog eligibility with two consecutive
eligible windows, and a hybrid that permits an immediate result when the
DFT margin exceeds 200. The independent mathematical DFT uses the existing
target-minus-noise rule; it is distinct from measured front-end noise.

## Findings

Each noise row contains 4,096 independent synthetic windows at a 2,048-count
baseline, with the stated uniform perturbation range. One frame contains 64
samples and spans nominally 20.813 ms; processing gaps are excluded.

| Noise half-range | Existing eligible windows | Two consecutive | Strong or two consecutive |
|---|---:|---:|---:|
| 50 | 0 | 0 | 0 |
| 100 | 4 | 0 | 0 |
| 200 | 16 | 0 | 0 |
| 400 | 22 | 0 | 0 |
| 800 | 41 | 1 | 1 |
| 1600 | 51 | 0 | 1 |

These are model decisions per window, not physical false alarms or audible
beep counts. Correlated EMI can behave differently. The mathematical DFT and
the integer implementation can differ slightly near a threshold; selected
actual-ARM reproductions are listed separately below.

The tradeoff is measurable:

- A 25-count nominal 825 Hz sine present for only one complete frame is
  detected in all 16 tested phases by the existing rule, and in **zero** by
  either confirmation policy.
- If the same weak signal persists for two frames, both policies recover all
  16 phases but need the additional frame to make the first indication.
- A 300-count one-frame sine is retained by the strong-or-two policy, while
  unconditional two-frame confirmation still misses it.
- In a sustained 25-count sine with synthetic uniform noise of ±50 counts,
  eligible windows fall from **50/128 to 19/128** under either confirmation
  policy. First acceptance shifts from zero-based frame index 2 to index 5
  (the third to the sixth frame) in that sequence.

A brief legitimate tone and a brief unrelated disturbance producing the same
ADC values are observationally identical in this test. A lower noise count
alone cannot prove better cable finding while sweeping. The appropriate
tradeoff depends on actual sweep dwell time, signal strength and interference.

## Actual firmware checks

Two additional groups execute the complete PN 1.11 ARM code, preserving its
checksum `3e39ae56832cf92881ffdc46564e293278d6c3f1b55a9832b7a9a8350f031828`:

- All 16 weak one-frame phases start a normal 30 ms indication. With rejected
  windows arriving every 21 nominal ms afterward, the current pulse completes
  and no repeat starts over the following 200 ticks.
- A deterministic no-transmitter noise window also starts exactly one such
  pulse. Its mathematical-model margin exceeds 200, demonstrating that the
  modeled hybrid's immediate strong-signal exception cannot exclude every
  noise event. The ARM assertion checks acceptance and pulse release.

The tests passed in 2.866 seconds. Interrupt arrivals and ADC windows are
modeled. This is evidence of the software tradeoff and bounded release, not
a claim that the physical probe produces those noise statistics.
They also pass in the eight-group combined follow-up run: see the
[retained output](experiments/results/pn111-followup-2026-09-20.log) and
[environment/source-hash record](experiments/results/pn111-followup-2026-09-20.json).

## Reproduce and next evidence

From the repository root:

```text
python docs/experiments/analog_temporal_followup.py
```

The [retained model output](experiments/results/pn111-analog-confidence-2026-09-20.json)
contains the complete policy-count tables and source-script hash.

From `LPM-10A/Firmware File/rx-sdk`:

```text
python -m unittest test_rx_analog_transients -q
```

Record real weak-target sweeps and transmitter-off interference before
choosing a confirmation policy. Use the existing
[comparison protocol](TONE-PROBE-COMPARISON-PROTOCOL.md) to retain misses as well
as false indications. The current
[PN 1.11 candidate](TONE-TRACKING-PN1.11-PN2.14-2026-09-20.md) remains the device
test candidate while this tradeoff is unmeasured.
