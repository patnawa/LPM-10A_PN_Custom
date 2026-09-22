# TX PN2.24 — Length lifecycle and QC noise qualification

This candidate follows the owner's PN2.23R test and the subsequent report of
random QC pin 1–8 indicators with no cable connected, including after Init.
It keeps R's original QC graphic,
automatic continuous acquisition and changed-indicator redraw. It also audits
and corrects the Length test without changing the cable-length formulas or
the four-run averaging policy.

Build from `LPM-10A/Firmware File/sdk`:

```powershell
python length_integrity.py --write
```

Output: `experimental/LPM-10A-TX_PN2.24-length-qc.bin`, with
`experimental/TX-PN2.24-SHA256SUMS.txt`. About and boot identify this image as
`PN2.24`. It is a TX update; RX PN1.23G is unchanged.

| Artifact property | Value |
|---|---|
| File size | 401,408 bytes |
| SHA-256 | `b3716f6538f8980c075fb85e925cb2ba1d86e46440174d450615fa98253131e7` |
| Payload length / exclusive flash end | `0x602E4` / `0x0806A2E4` |
| Additional payload over R | 1,132 bytes |
| Additional container padding over R | 4,096 bytes |
| Additional persistent RAM over R | 28 bytes: QC filter 20, Length lifecycle 8 |

The exact parent is PN2.23R,
`cd94672633420a44e9bf9232de87adcc794cc57068035a260ffb6e4ffa35e8b4`.
The builder rejects any other parent and keeps all historical builders
reproducible. The published release pair is not replaced by this experiment.

## Reproduced defects and corrections

### Length: an old measurement could publish after rapid reentry

The network task runs `APP_LENG_Test_Sequence` synchronously. Pausing its first
50 ms wait, pressing Back, reentering Length and resuming the task reproduced
the defect on R: the previous visit wrote four 1000 cm results and set the
new visit's completed flag. Checking only `sysState == 7` cannot distinguish
two visits to the same screen. A queued Start from the old visit also needs
its original generation checked when it is eventually dispatched.

`length_lifecycle.py` gives each visit/test a generation and validates it
before accepting work or publishing results. The result array, completed
flag and pending REF update commit together in a short critical section;
queue sends happen afterward. Cancel and timeout paths cannot clear or
replace a newer visit's state. Result/header notifications carry the
generation that produced them.

The Start key uses a dedicated network command with an inline generation,
without a heap allocation. The dispatcher clears that inline field before
the vendor's payload cleanup and the sequence rechecks it atomically at
execution. A Start queued before Back therefore cannot restart measurement
on the next visit, including a navigation event between decode and execution.
Other network commands retain their existing routing.

### Length: failed measurement consumed the pending known-length REF

Dial REF 20.0 m before measuring, then feed an all-zero PHY result. R's solver
correctly leaves NVP unchanged, but its caller unconditionally clears the
pending REF. A subsequent valid cable therefore never receives the requested
calibration. The original regression failed with `pending == 0`, expected 1.

`length_reference_guard.py` consumes the request only when the unchanged
solver actually updates NVP. Repeated unusable results retain it; the first
usable result applies it once. For the tested 2031 cm zero-corrected mean,
REF 20.0 m produces NVP 68%; a later measurement does not fit itself again.
Existing partial-pair support and numeric bounds remain unchanged.

### Length: queued Testing text could paint another screen

R queues a box clear plus generic text messages for Testing and the counter.
After a real exit to Home, draining these old messages changed **17,679 Home
pixels**. Generic text messages carried no indication of their originating
screen or measurement.

`length_message_guard.py` replaces only the audited Length text call sites:
Testing, its box clear, the run counter, timeout and four animation states.
Each message carries its originating generation and is rejected before
drawing if it is stale. Text is embedded in one bounded 40-byte packet, so
there is no separate string allocation to free on a discarded message.
Other screens keep their original text transport. English and Thai Testing
frames retain the parent's appearance.

### Length: every averaging run erased the same Testing box

R performs three filled rectangles and 2,096 pixel calls each time it
advances the run counter. Suppressing the stock Testing draw while retaining
the counter reduced this to zero filled rectangles and 384 pixel calls.
Suppressing only the counter still left all three erases, locating the cause.

`length_progress_quiet.py` draws the box and Testing label on run 1. Runs 2–4
update only the existing 24 × 16 counter area: **82% fewer pixel calls** for
those updates, plus removal of the repeated large fills. The number of PHY
measurements and their timing are unchanged; this is display-work reduction,
not a claimed faster physical measurement.

### QC: one noisy count could immediately light a passing pin

The owner clarified that the affected lights are the screen's pin 1–8
indicators, and that the symptom persists after unplugged Init. The
deterministic reproduction is
synthetic, not a captured device trace: baseline 1000, idle counts 1000, then
one count of 993. R immediately publishes a passing pin and a green pixel.
A full sweep of these dips can also make the physical status LED green.
Returning to 1000 clears it, ruling out a retained display-cache state in
this reproduction.

`qc_idle_filter.py` requires **three consecutive passing observations of the
same pin** before publishing green. Every OPEN/CHECK observation immediately
revokes a pass and resets confirmation. The original seven-count electrical
boundary stays intact; increasing it without device measurements could hide
real short cables. Confirmation resets after reentry or Init. Raw fault
history remains separate from the filtered display state.

The extra two sweeps take **176 ms in the existing 10 ms acquisition / 1 ms
queue-wait model**, plus normal GUI scheduling. No additional sampling delay
is inserted. Repeated isolated or double dips do not light the indicators;
a stable cable qualifies on the third observation. Both the eight screen
indicators and the all-pins status LED use the qualified state.

## Validation and limits

Final production snapshot: `python -W ignore::ResourceWarning -m unittest
discover -q` passed **417 tests in 211.727 s**. The subsequently added
post-Init noise regression passed separately in **1.581 s**; it changed only
test coverage, not the delivered binary. Together these are **418 passing
test cases**. The on-disk binary matches a fresh in-memory rebuild and its
SHA-256 manifest. Historical R/Q images and the default TX/RX release files
retain their recorded hashes.

The tests execute actual Thumb instructions, with PHY values, timers, RTOS
queues and LCD writes supplied or observed by the harness. Regression files:

- `test_length_audit_reference.py`: failed-result recovery, one-shot solve,
  incomplete results, reentry and original-parent negative control.
- `test_length_audit_lifecycle.py`: actual key navigation, task suspension,
  queued Start, late acceptance, timeout/cancel and atomic result publication.
- `test_length_audit_pipeline.py`: complete acquisition/vote/average path,
  blind-zone boundaries, mixed per-pair counts, poisoned previous state,
  ordering invariance and a missing-acquisitions negative control.
- `test_length_progress_quiet.py` and `test_length_message_guard.py`: write
  footprint, frame parity, copied text, bounds, stale messages and old-parent
  negative control.
- `test_qc_idle_filter.py`: isolated/double spikes, stable connection,
  immediate loss, original threshold, LED/framebuffer, Init/reentry,
calibration preemption and startup canaries.
- `test_length_integrity_build.py`: exact parent, changed-byte footprint,
  RAM initialization, container limits, version and reproducibility.

The numerical audit found no new arithmetic defect. The existing 2 m raw
blind zone, Zero/NVP scaling, m/cm/ft conversion and four-run means are kept.
The vendor's vote can merge nearby pair lengths: raw 10/11/12/13 m can become
11.5 m on all four rows. These rows are therefore not four independent fault
distance measurements. Tests using raw 65535 check arithmetic only; they do
not assert an undocumented PHY sentinel meaning.

PN2.24 still needs a physical cable and no-cable check. Three confirmations
reject brief disturbances; they cannot distinguish a persistently wrong
baseline from an attached cable. Keep the connector unplugged during Init.
This build does not claim new electrical accuracy or hardware certification.
