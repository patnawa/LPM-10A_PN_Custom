# RX audio cadence and firmware identity audit

The approximately 50 ms pulses and 49 ms gaps reported by the recording
analysis are compatible with several earlier receiver schedulers. The normal
PN 1.13 Digital scheduler instead starts 30-count pulses; its uncertainty
indication starts 100-count pulses. This discrepancy is a reason to verify the
running image. It does **not** establish which firmware is installed, whether
an update failed, or which bootloader filename rule the device uses.

## Exact-image scheduler comparison

The [reproducible audit](experiments/rx_audio_identity_audit.py) ran the stored
stock image and PN 1.0 through PN 1.13: **15 images, 42 cases**. Results, including
every image SHA-256, are in
[the retained JSON](experiments/results/rx-audio-identity-scheduler-2026-09-20.json).

```powershell
python docs/experiments/rx_audio_identity_audit.py --out docs/experiments/results/rx-audio-identity-scheduler-2026-09-20.json
```

It executes the actual Thumb speaker scheduler, PWM writes and TIM1 handler.
The synthetic schedule supplies one TIM1 interrupt and five speaker dispatches
per unit, nominally about one millisecond. PN 1.13 executes its actual TIM5 audio
countdown helper with the TIM5 counter advanced by 40 per unit; its TIM1 handler
does not decrement BEEP/GAP. This is a **countdown-unit comparison**, not full
TIM5 interrupt execution, ADC acquisition, complete device runtime or a hardware
timing measurement. Existing PN 1.13 integration tests separately execute the
complete TIM5 handler.

The starting state is Digital, an open generation, zero BEEP/GAP, and
RECENT=800. No detector or fresh publication runs afterward. Valid example
grades are selected separately for each profile.

| Stored firmware | ON / quiet units in the relevant case | Last sound end, units after initial state |
|---|---|---|
| Stock V3.0.0 and PN 1.0–1.2 | 49.8 / 49.2 | 842 |
| PN 1.3–1.5, medium grade | 49.8 / 49.2 | 842 |
| PN 1.6, medium grade | 50 / 49 | 842 |
| PN 1.7, strongest example | 30 / 19 | 324 |
| PN 1.8, gap 50 example | 30 / 49 | 267 |
| PN 1.9–1.13, gap 50 example | 30 / 49 | 267 |
| PN 1.9–1.13, uncertainty | 100 / 159 | 359 |

The 0.2-unit edge difference in older images comes from the scheduler order:
it drives the speaker before starting the next BEEP. Quiet-gap countdown begins
on the same tick that BEEP reaches zero. These are modeled instruction effects,
not audio analysis precision. A partial acquisition window can move the time
of the final publication; the table intentionally does not model that process.

PN 1.3–1.6 also support other cadences. PN 1.7 has five repeat gaps; PN 1.8+
supports finer gaps. A single cadence therefore cannot identify one exact
release. A 50-count pulse inherited from another RX mode could occur during a
transition; it does not explain sustained normal Digital repetitions in
PN 1.13. The normal Digital pulse assignments are 30 and 100, not 50.

Source evidence:

- [`rx_patches.py:273`](../LPM-10A/Firmware%20File/rx-sdk/rx_patches.py#L273)
  publishes the older 50-count BEEP/GAP and RECENT=800.
- [`rx_patches.py:454`](../LPM-10A/Firmware%20File/rx-sdk/rx_patches.py#L454)
  implements older graded 30/30, 50/50 and 50/100 cadence.
- [`followup_fixes.py:21`](../LPM-10A/Firmware%20File/rx-sdk/followup_fixes.py#L21)
  preserves active/key pulses in PN 1.6 and caps its new pulse at 50 counts.
- [`precision_fixes.py:240`](../LPM-10A/Firmware%20File/rx-sdk/precision_fixes.py#L240)
  fixes the normal pulse at 30 and gates repeats on RECENT>500.
- [`robust_fixes.py:317`](../LPM-10A/Firmware%20File/rx-sdk/robust_fixes.py#L317)
  starts 100-count uncertainty pulses or 30-count normal pulses.
- [`audio_clock_fixes.py:33`](../LPM-10A/Firmware%20File/rx-sdk/audio_clock_fixes.py#L33)
  decrements BEEP/GAP on every fortieth TIM5 count and removes their TIM1
  countdown. It does not change the 30/100 pulse assignments.

## What identifies an RX update

All 15 audited image files contain the same `3.0.0\0` at application address
`0x0800CDE4`. The application checks/writes this vendor version to page
`0x0801F000`; it does not display a PN version. The image filename and source
file hash identify the file chosen on the computer, but neither proves the
bytes currently running in the receiver.

The verified vendor input basename is:

```text
APP_LPM-10RX_V3.0.0_260416.bin
```

The local original is outside the repository at
`../LPM-10A_FNIRSI_originals/APP_LPM-10RX_V3.0.0_260416.bin`, SHA-256
`083f3825e8f8a38627417e26732e88fd13ee0dbe3c13ca1cd1cd9c4875c7c8c5`.
That basename is established by the vendor input file and
[`image.py:24`](../LPM-10A/Firmware%20File/rx-sdk/lpm10rx/image.py#L24).
It is **not evidence that the bootloader requires this exact name**.

The recorded owner evidence establishes RX update-mode entry: probe off,
hold SCAN and connect USB to expose UDISK. Later reports say new TX/RX firmware
worked, identify the chosen PN 1.12 file, and report trying PN 1.13. The records
inspected here contain no observed filename-parser rule, independent installed
hash, flash readback, or verified per-version acceptance marker. See
[`rx-sdk/README.md:249`](../LPM-10A/Firmware%20File/rx-sdk/README.md#L249),
[the owner feedback record](TONE-DEVICE-FEEDBACK-2026-09-20.md), and
[`RX-AUDIT.md:197`](RX-AUDIT.md#L197).

The receiver bootloader below `0x08006800` is absent from these application
images and has not been audited. RX filename rules, version acceptance and a
USB flash-readback capability cannot be recovered from these application bytes.
TX rename advice must not be treated as an RX bootloader specification.

Without flashing another image, an audio recording of sustained Digital
reception at different signal strengths can distinguish some scheduler
families: ordinary PN 1.7+ pulses should remain near 30 counts, and PN 1.9+
uncertain pulses near 100. It cannot uniquely authenticate PN 1.13. Exact
installed identity needs an available flash readback and hash comparison, or a
separately designed and verified explicit firmware marker. No such marker
candidate, firmware edit, or flash operation was made in this audit.
