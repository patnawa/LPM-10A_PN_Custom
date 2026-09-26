# RX Analog dropout: owner A/B test

Diagnostic builds only, **not confirmed fixes or new releases**. The owner
reports PN1.31 drops in Analog while PN1.30 does not, using the same TX PN2.34
in Analog 817 Hz, cable and knob position (half to maximum). Drops occur both
while held still and moving. Emulation has not reproduced that difference.

Keep TX unchanged. For ordinary use, stay on the owner-tested PN1.30 while
this is investigated. Do not infer a hardware pass from the software checks.

## Two isolated RX changes

Both builds start from exact PN1.30, with a distinct version label:

| Build | Added change | Retained PN1.30 behavior | Update bytes |
|---|---|---|---:|
| PN1.31A | Digital impulse-resistant strength estimator | Entire old sound/gain publication path | 36,864 |
| PN1.31B | Accepted-frame sound/gain publication commit | Old estimator and original image length | 32,768 |

A also has PN1.31's appended 200-byte helper/container size. B does not.
Neither changes the bootloader, sampling thresholds, knob law or persistent
RAM allocation. A deliberately retains the old publication race; B does not
include the Digital impulse improvement. These are temporary isolation tests.

The local files are under `LPM-10A/Firmware File/experimental/`:

- A: `APP_LPM-10RX_PN1.31A-impulse-only-update.bin`
- B: `APP_LPM-10RX_PN1.31B-publication-only-update.bin`
- Rollback: `APP_LPM-10RX_PN1.30-clean-strength-update.bin`

Copy **only `-update.bin`**, never the raw companion image. No diagnostic
GitHub release, profile or default/latest selection has been created.

## Test order

1. Keep TX PN2.34 showing **Analog 817 Hz**. Keep the same cable, position,
   batteries, RX Analog mode and knob setting that reproduced the fault.
   Record the setting. PN1.30's stable result is the control; repeat it if
   anything in the setup has changed.
2. Install **A**: RX off -> hold SCAN -> connect USB -> release SCAN when
   `BOOTLOADER` appears. Copy its update file with Explorer. Wait for the
   drive to disappear before disconnecting; then power on.
3. After the application has booted, enter update mode again without copying
   anything. On a fresh mount, record the status filename. It should identify
   `PN1.31A`. If it does not, stop and report the name; do not assume A ran.
   Unplug and power on normally for the test.
4. With RX in Analog, hold still for at least 30 seconds, then move slowly for
   at least 30 seconds. Use longer if the original dropout took longer to
   appear. Record unexpected silence separately from the normal beep gaps,
   and whether sound returns without touching controls.
5. Repeat steps 2-4 using **B**, expecting `PN1.31B`, without changing TX or
   the test setup. Stop if the unit behaves abnormally. Return to **PN1.30**
   afterward using the same update procedure and confirm `PN1.30`.

The actual ARM version-page routines were checked with the A/B suffixes.
Physical bootloader filename rendering was not available to emulate; that is
why fresh-mount identity confirmation matters.

Reply with this small record (a short video is useful if available):

```text
Knob / cable / test duration:
A status filename:
A held still: stable / drops / uncertain
A moving: stable / drops / uncertain
A sound returns by itself: yes / no / not applicable
B status filename:
B held still: stable / drops / uncertain
B moving: stable / drops / uncertain
B sound returns by itself: yes / no / not applicable
PN1.30 control: stable / drops / not repeated (same setup)
```

Optional structured capture from Git Bash at the repository root:

```bash
bash docs/debug/2026-09-26-rx-tx/analog_drop_hitl.sh
```

This script only prompts and prints observations; it does not flash, copy,
upload or change firmware. Exit 1 means a reported diagnostic dropout, 0 means
none observed during this test, and 2 means an inconclusive comparison. None
of these alone certifies a production fix. Paste its final `KEY=VALUE` block.

## Interpreting the comparison

| A | B | Next investigation |
|---|---|---|
| Stable | Drops | Shared publication change is implicated |
| Drops | Stable | Estimator/image-layout side is implicated; Analog reachability needs explaining |
| Stable | Stable | Combined interaction or insufficient reproduction; retest PN1.31 under the same conditions |
| Drops | Drops | Recheck identity/control and investigate shared conditions; not a clean component isolation |

These are directions for further tests, not established root causes. A quiet
short run cannot exclude an intermittent fault.

## Build and verification record

From `LPM-10A/Firmware File/rx-sdk`:

```powershell
python analog_drop_ablation.py --write
python -W ignore::ResourceWarning -m unittest -v test_analog_drop_ablation
```

Eight contract tests pass (root rerun: 0.385 seconds). They check exact parent,
component boundaries, version slots, unchanged canonical PN1.31 artifacts,
canonical containers, deterministic rebuilds and a dry-by-default builder.
Independent review checked four Analog comparisons against PN1.30 and exact
artifact/version identity. Those modeled timelines match; hardware is pending.

| Update | SHA-256 |
|---|---|
| A | `b5a23ad498bb3c436610409942f0b4e881a354f517cea55ea5351cb78269994e` |
| B | `32f3a1c2d4fbf316487e6867ad99f5407e04c05057b57837c98293e6e148c118` |
| PN1.30 rollback | `bf723bdd7b51ef850388cc485c02b471a8eb6a48e414701a24924ca336900180` |

The generated `RX-PN1.31-ANALOG-DIAGNOSTIC-SHA256SUMS.txt` also lists raw hashes.
No existing release binary or tag is replaced.

Supporting negative evidence: [33 paired Analog comparisons and model limits](debug/2026-09-26-rx-tx/release_analog_drop_summary.json),
[TX and RX layout audit](debug/2026-09-26-rx-tx/tx_analog_dropout_audit.md).
ADC conversion/settling, real interrupt timing and physical flash behavior
remain blind spots. These checks do not override the owner's PN1.30/PN1.31 A/B.
