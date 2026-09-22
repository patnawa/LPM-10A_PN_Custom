# PN1.23G: Digital audio continuity during gain changes

ผู้ใช้รายงานว่า **PN1.23F เสียง Digital ขาด ๆ หาย ๆ เมื่อขยับหัวรับหรือหมุนปุ่ม
ขณะสัญญาณแรง** แต่วางนิ่งไม่มีอาการและ Analog ปกติ รุ่น PN1.23G แก้ช่วงเงียบ
ที่เกิดจากการเปลี่ยนเกน โดยยังทิ้งตัวอย่างเก่าและรับข้อมูลใหม่ครบก่อนยืนยันผล

ไฟล์อัปเดต:
[`APP_LPM-10RX_PN1.23G-digital-gain-update.bin`](../LPM-10A/Firmware%20File/experimental/APP_LPM-10RX_PN1.23G-digital-gain-update.bin).
เป็นรุ่นทดลองที่ผ่านตัวจำลอง และผู้ใช้ยืนยันแล้วว่าแก้อาการเสียง Digital ขาดหาย
บนเครื่องจริงได้ (2026-09-22) ดูวิธีอัปเดตที่
[RX update guide](RX-UPDATE-GUIDE.md). ไม่มีการเปลี่ยน TX หรือ release ปัจจุบัน

## Owner confirmation, 2026-09-22

After testing PN1.23G, the owner reported:

> 1.23G Fix the digital lost confirm

The reported Digital audio dropout is **confirmed fixed on the owner's unit**.
This is qualitative device feedback for the motion/knob symptom reported on
PN1.23F. The numerical timing results below remain emulator measurements.

## Reproduction

From `LPM-10A/Firmware File/rx-sdk`:

```powershell
python -m unittest test_rx_digital_strong_gain -v
```

The regression executes actual TIM5 sampling, TIM1 gain control, Digital/Analog
analysis, main-loop ownership and speaker PWM instructions. Only ADC values,
the analog link and interrupt/foreground arrival times are modeled.

The original 1.6-second stream failed in 0.764 seconds:

```text
FAIL: test_sustained_strong_digital_has_no_dropout_while_turning_knob
AssertionError: 225.140625 not less than 150
```

The minimized case starts a continuous B6 signal at gain 7, changes the knob to
gain 2 at the first 500 ms AGC event and runs to 900 ms. A strong signal stays
present throughout. PN1.23F's longest quiet interval is **237.948625 ms**.
The prior publication is at 481 ms, and the first fresh one is at 741 ms.
The permanent suite retains PN1.23F as a negative control.

The behavior matches the reported Digital/Analog difference. Nominal full-grid
acquisition after invalidation takes 9,620 TIM5 interrupts / **240.650313 ms**
for Digital, but only 832 interrupts / **20.813 ms** for Analog. Digital's
normal overlapping updates take **40.025 ms**, so a full restart is much longer.

## Cause and discriminating probes

Ranked hypotheses were:

1. Clearing the last confirmed feedback during a full acquisition restart
   creates the long mute. Preserving that feedback with its existing deadline
   should remove the mute without allowing stale samples to publish.
2. Mixed-gain/clipped samples cause detector rejection. Holding modeled ADC
   amplitude constant during the same gain event should remove the failure.
3. Gain-control work interferes with audio timer scheduling. The same work in
   the earlier firmware without this reset should still interrupt its cadence.

Hypothesis 1 is confirmed in the emulator. Changing only modeled ADC amplitude
to remain constant through the knob event still produces a 237.95 ms mute,
which rules out hypothesis 2 for this reproduction. PN1.23 with the same gain
event remains near its 41 ms normal quiet interval. Separately, 16 continuous
strong amplitude/clipping transition controls at fixed gain do not reproduce
the mute. No new detector or threshold algorithm is needed for this defect.

PN1.23F fixed real sample ownership: a gain change invalidates the old window,
and the main boundary resets sampling. However, that boundary also clears
`GRADE`, `GAP` and `RECENT`, erasing already-confirmed feedback. An active beep
can finish, but nothing starts another until the complete new window arrives.
Analog's much shorter window makes the corresponding interruption small.

## Correction

[`digital_gain_continuity.py`](../LPM-10A/Firmware%20File/rx-sdk/digital_gain_continuity.py)
applies only to the exact tagged PN1.23F image:

- A gain change in an already-open Digital acquisition sets `GATE_STATE=3`.
  The existing analyzer readiness and publication guards require state 2, so
  work interrupted by the gain change still cannot publish.
- Main performs the full sample reset and returns the gate to 2, but retains
  the last confirmed `GRADE`, current `GAP` and remaining `RECENT` deadline.
- The countdown is never refreshed by a gain change. A newly accepted, fully
  fresh window remains the only way to renew signal feedback. Repeated gain
  changes therefore cannot sustain a tone indefinitely after signal loss.
- Mode requests, gate closure/reopening, startup, Analog and Mains retain the
  previous reset behavior. Existing beeps retain their ordinary countdown.

All 48 new reduced Digital samples (240 ADC reads) are still required after a
gain change. This improves audible continuity; it does not claim a faster
fresh measurement or reuse old samples with a new gain scale. The temporary
rhythm represents the last validated result until it expires or is replaced.

The image adds 184 bytes of code, no persistent RAM and no additional stack
reservation. Independent checks of 144 boundary state combinations found RAM
differences only in the intended retained feedback bytes. The longest masked
boundary path increases from 43 to 48 executed instructions; this is not a
hardware cycle or interrupt-latency measurement. Another 24 invalidator and
288 full gain-selector ABI cases preserve the required registers and return
correctly.

## Results and validation

| Continuous input case | PN1.23F longest quiet | PN1.23G longest quiet |
|---|---:|---:|
| Knob changes 7 -> 2 | 237.95 ms | **37.02 ms** |
| Approach triggers automatic gain decrease | 237.95 ms | **28.02 ms** |
| Repeated knob changes | approximately 238 ms per restart | **37.02 ms** |

These are nominal emulated PWM timings, not microphone measurements. In the
signal-loss control, signal disappears at 500 ms and the final pulse ends at
762.08 ms; later gain changes do not restart it. No-prior-signal and knob-off
controls also pass. Analog/Mains reset parity is checked separately.

```powershell
python -m unittest test_rx_digital_strong_gain test_rx_digital_gain_continuity test_digital_gain_build -q
# Ran 24 tests in 6.614s: OK

python -m unittest test_profiles test_rx_auto_range_freshness test_rx_pn121_pn122 test_rx_analog_feedback_races test_rx_analog_integer test_rx_rail_strong test_rx_strong_cap test_rx_release_hold test_rx_mode_tone test_release_integrity -q
# Ran 70 tests in 66.317s: OK
```

The new tests include interruptions of the old analyzer and the ownership
boundary, fresh sample requirements, expired feedback, mode changes, closed
gates, repeated gain changes and unchanged Analog/Mains behavior. Interrupt
sweeps cover first visits to unique unmasked instructions, not every loop
iteration or nested NVIC schedule. Build tests check the exact parent, patch
footprint, repeatability and container round trip.

Boot emulation reaches the ADC initialization boundary and verifies unchanged
64 MHz clocks and timer setup. This boot harness does not establish a complete
hardware boot. Saved raw/update files are read back and compared with a fresh
build and canonical container, including all bytes and hashes. No temporary
debug instrumentation remains.

## Build and artifacts

```powershell
python digital_gain_continuity.py --write
```

Outputs in `LPM-10A/Firmware File/experimental/`:

| File | Size | SHA-256 |
|---|---:|---|
| `APP_LPM-10RX_PN1.23G-digital-gain.bin` (raw) | 26,944 bytes | `a0822e2f454e08d0a213e63a1bbf0cac9948776dd8b067560d4786605b0307bb` |
| `APP_LPM-10RX_PN1.23G-digital-gain-update.bin` | 32,768 bytes | `f3a05aac4077ee1c050abab041083fe6db291614dfc7aaa51f335e1516a4db65` |

Use the **`-update.bin`** file for the RX bootloader. The installed identity
should become `PN1.23G.TXT`. The generated checksum manifest is
`RX-PN1.23G-SHA256SUMS.txt`. Published PN1.23 and experimental PN1.23F remain
available; TX does not need a change for this fix.

The owner subsequently confirmed the reported Digital dropout is fixed on
PN1.23G. Quantitative noise, electrical settling, oscillator/interrupt timing
and TX-pause-to-silence measurements were not supplied in that confirmation.
