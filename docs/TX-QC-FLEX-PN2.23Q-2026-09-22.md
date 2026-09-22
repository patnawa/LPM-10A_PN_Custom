# TX PN2.23Q — continuous QC and contact history

สถานะ: รุ่นทดลองสำหรับ TX สร้างต่อจาก PN2.23S ตรวจด้วย CPU emulator แล้ว
ยังไม่มีผลทดสอบ QC รุ่นนี้จากเครื่องจริง ส่วน RX PN1.23G ใช้ไฟล์เดิมได้

## Behavior and controls

Entering **QC Test** starts a 20-second session when the stored baseline is
usable. The table shows all eight pins, their current indication, and a
latched count of fault episodes. A currently connected pin that previously
failed shows **INT** in yellow. Results remain visible when the session ends.

| Control | Action |
|---|---|
| OK, short press | Stop and retain the results; press again to start a fresh session |
| Right, short press | Clear the history and start a fresh 20-second session |
| Right, hold for the existing two-second event | Calibrate with the cable removed |
| Back | Leave QC and cancel outstanding measurement work |

| Table indication | Meaning |
|---|---|
| `-` | This pin has not been sampled in the current session |
| `OK` | Connected according to the existing count threshold; no recorded failure |
| `OPEN` | Count is within six counts of the unplugged baseline |
| `CHECK` | Count is above the baseline by at least seven, zero, or saturated |
| `INT` | The current indication is connected, but this session recorded a failure |
| `FAIL` | Fault episodes, saturated at 999; a continuously bad pin counts once |

An initial bad reading counts as one episode. A new episode is counted after
recovery to OK followed by another bad reading. Changing directly between
OPEN and CHECK does not count an extra episode. New sessions clear history.
The indicator LED is green only after all eight pins have been observed OK
with no history of failure; otherwise it is red.

The stock QC table binds Init to logical Left/event 8 despite its own
"Hold Right" instruction. This candidate adds logical Right/event 8 to match
the displayed instruction and retains the legacy Left hold binding.

These are pulse-count contact indications. They do not measure contact
resistance, certify a cable category, prove network throughput, or replace
Cable Test for shorts and crossed wiring. There is no invented quality score.

## Acquisition and responsiveness

Inspection of the complete scheduling path corrected an incomplete initial
description: stock QC already repeats approximately once a second. Each
request reads one 10 ms TIM8 window per pin, with a 50 ms initial wait, and
overwrites the previous results. It has no per-pin fault history.

PN2.23Q samples at most one pin before each GUI queue receive. It retains the
initial 50 ms settling interval without blocking the GUI, then runs each
10 ms acquisition with interrupts enabled and allows the GUI to process
messages between pins. The receive wait is one tick during an active session;
inactive QC retains the original indefinite queue wait. Eight samples need
80 ms of programmed acquisition waits, plus queue waits, drawing and task
scheduling. This is not a measured device refresh rate.

The display updates no more frequently than every 200 ms and only after a
complete sweep. Raw acquisition failures are recorded immediately, before
display throttling; no median or vote hides a transient failure. A dropout
between acquisition windows, or too short to alter the measured count, can
still be missed. The old one-second scan requests are harmless no-ops.

## Stable calibration

Init reads five windows per pin, sorts the counts, and stages the median for
each of eight pins on the stack. It commits all eight baselines only when the
entire acquisition completes and each set has a spread no greater than six.
A median below seven or at 65535 is rejected as unusable for this threshold.

The six-count spread limit is an initial conservative choice tied to the
existing seven-count decision boundary, not a measured noise specification.
A stable reading does not prove the cable was removed. Remove the cable
before Init, as with the vendor function.

Rejected or canceled acquisition preserves the previous baseline/settings.
The UI displays **Calibration failed / Old values kept** on rejection, and
**Calibrating... / Remove cable first** while measuring. Successful acquisition
uses the existing settings-update/save path once. No new settings format or
claim of power-loss atomic flash storage is introduced.

## Task and session ownership

Live scanning and calibration share the same mux and timer. Calibration
announces its intent atomically, waits for an in-flight GUI sample to release
the timer, and then owns it explicitly. Samples and calibration results carry
a session generation so that a quick Back/reentry cannot publish old data or
overwrite the new session's status. The entry reset preserves an outstanding
timer owner until it releases the mux.

GUI controls, entry frames and calibration notifications carry the session
generation through the queue. Old controls/progress/errors cannot reset or
repaint a later visit. The existing battery gate already permits battery
monitoring in QC; no battery patch was necessary.

The candidate adds 64 bytes of persistent scratch RAM, explicitly cleared at
startup. Calibration's staged data use 32 additional stack bytes; no heap
allocation is added to acquisition or drawing. Tagged GUI messages use the
existing queue payload allocation/free path. Existing profiles remain frozen.

## Build and verification

From `LPM-10A/Firmware File/sdk`:

```powershell
python qc_continuity.py
python -W ignore::ResourceWarning -m unittest test_qc_continuity test_qc_calibration test_qc_ui test_qc_build -q
python -W ignore::ResourceWarning -m unittest discover -q
python qc_continuity.py --write
```

Recorded results: the full TX discovery run passed **342 tests in 152.547 s**.
Two subsequently added hold-key regressions also passed in the final
**22-test continuity run (14.765 s)**, including comparisons against the
parent outside QC. The current test inventory is 344 TX tests, including
52 focused QC tests. English/Thai layouts were rendered and visually checked.

The emitted container was read back and compared byte-for-byte with a fresh
build and its manifest. It is **397,312 bytes**, with **2,468 additional payload
bytes** relative to PN2.23S and a payload end of `0x08069C10` (exclusive).
SHA256:

```text
969c775eba1f40805f9e64325a4e0838edf39fa0e964652a47c1158d0f7d5115
```

The exact parent is PN2.23S, SHA256
`007bbeff0deeca6a7d3df63ce4732a0f03350ae01cb3e6e541b067198fcec478`.
This includes its SPEED failed-register-read correction. Default TX release
selection and the published release pair are unchanged.

The focused suite exercises actual Thumb routines and GUI dispatch, modeling
external timer counts, RTOS scheduling and display I/O. Coverage includes:

- A transient bad pin followed by recovery, persistent faults, threshold
  boundaries, saturating history, and independent results for all eight pins.
- Actual key routing, stop/restart/reentry, 20-second timeout and tick wrap,
  startup with poisoned RAM, register/stack and allocation ownership.
- Calibration announced at each traced unmasked instruction of a GUI sample;
  actual separate GUI/calibration task contexts; cancellation at every sample;
  Back/reentry during sampling and during the progress send.
- Five-count medians, spread boundary six/seven, complete baseline commit,
  unchanged settings after failure, and no premature mux release.
- English/Thai framebuffer layouts, LED behavior, progress redraw, and stale
  control/frame/error messages from a previous session.
- Exact parent/patch footprint, repeatable build, version strings, container
  length/tail, flash limits, and rejection of a wrong or already patched parent.

The original continuous-sampling feature regression fails on PN2.23 with
zero samples through the new scheduling seam, versus the expected sixteen.
Additional regressions were made red with narrow in-memory reversions of the
old session reset and GUI routing. These are code-path negative controls,
not recordings of physical electrical faults.

## Device acceptance

Use the TX update container `experimental/LPM-10A-TX_PN2.23Q-qc-flex.bin`;
the matching digest is in `experimental/TX-PN2.23Q-SHA256SUMS.txt`.

1. Remove the cable and run Init. Check that the five-window calibration
   succeeds repeatedly on the actual unit.
2. Check a known good connector, then test known open/poor contacts on each
   pin. Flex the cable gently and confirm that recovery retains INT/history.
3. Check OK stop/start, Right new test, the 20-second completion, and Back
   during both acquisition and Init. Verify the actual LCD update cadence.
4. Check a noisy/unstable Init attempt retains the prior baseline, then verify
   successful calibration persists after normal power cycling.

Separate filtered snapshot verification and an integrated QC/Cable Test
workflow were optional later ideas; this candidate implements the recommended
first set: continuous capture, per-pin history and stable calibration.
