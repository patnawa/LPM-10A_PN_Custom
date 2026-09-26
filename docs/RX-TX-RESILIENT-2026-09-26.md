# RX PN1.31 / TX PN2.34 — fixes and validation

Status: prereleases with **an unresolved hardware report**. After publication, the owner reports Analog RX signal dropouts on RX PN1.31 paired with TX PN2.34, both while held still and moving, with the knob from half to maximum. TX is confirmed in Analog 817 Hz mode; the owner reports PN1.30 does not drop with the same TX/setup. This points to the RX update, but the responsible change is not yet established. These releases are not hardware-validated. No connected RX, TX, or debug probe was available for the emulator checks below. PN1.30 and PN2.33 remain the previous device-tested rollback pair; their binaries and historical build profiles are unchanged.

This implements the authorized follow-up to the [bug hunt](RX-TX-BUG-HUNT-2026-09-26.md). Reproductions execute the actual ARM firmware with modeled ADC samples, interrupts, queues, and peripheral state. This is not a measurement of pickup distance, acoustic loudness, real switch-port behavior, or failure frequency on hardware.

## RX: correct strength ordering without losing edge compensation

PN1.30 estimated Digital strength from three/four triplets. Two low impulses could corrupt half of that evidence and turn a weak tone's 100-count contrast into 600 counts. The resulting score was 12,864, greater than the clean stronger tone's 3,222.

`impulse_strength.py` retains the chip-edge compensation and ADC rail policy, but uses eleven/twelve triplets when the detector has verified the entire immutable 48-sample snapshot. The exact-only fallback continues to read just its selected 16-sample span; unverified surrounding samples are never used. The same noisy weak input now scores 2,144, below 3,222.

The helper appends 200 bytes, uses no persistent RAM, and adds 44 bytes of private stack relative to the previous estimator. Its maximum depth including the existing sorter is 96 bytes below the detector snapshot; stack alignment, register preservation, memory bounds, and canaries are tested. Full-fit/fallback call-site contracts are checked before patching.

The longer verified span can smooth strength changes within a frame. It does not add a new acquisition window or alter detection eligibility, knob law, ten strength levels, pitches, or gain thresholds. In the tested strong-to-half-strength case, the displayed level settles in 571 ms; this is modeled timing, not measured sound onset.

## RX: commit gain eligibility with accepted sound

PN1.30 stamped `LAST_DISPLAYED` before guarded sound publication. A TIM1 interrupt could see that marker, lower the gain, and cause the first valid frame to be rejected by the existing gain-generation guard. Removing that guard would allow stale data; it is deliberately retained.

`publication_commit.py` moves the marker into the existing masked accepted-publication section, after the grade and recent-signal stores. Rejected, expired, or invalidated frames do not stamp it. The marker is copied from the analyzed generation, not a later sample. This adds four instructions inside the existing critical section, no image growth, and no persistent RAM.

## TX: queued work belongs to one Cable Test visit

PN2.33's BUSY check occurred before queue delivery. Back returned to the selector without leaving screen 4, so stale OK requests still passed the consumer's screen check. Two delayed requests could run 792 ADC reads in the wrong mode.

`cable_session.py` captures the visit generation and selected mode at the original key sender. Back, entry, mode changes, and exit invalidate old work. Pending Start requests are coalesced, the consumer validates ownership, and a failed nonblocking queue send releases only its own pending claim. Keys are ignored during measurement; the final action boundary is also guarded so a Back already past the first key check cannot change mode after the GUI claims the test.

The eight-byte inline GUI envelope is heap-free and uses message ID `0x42`, distinct from stock messages and Length's `0x40`/`0x41`. Independent review caught both an in-flight Back race and a draft message-ID collision; regressions were added before release. Length text rendering and heap-payload cleanup are checked on the final candidate, not just on its ancestor.

The patch adds 772 bytes of code and 16 bytes of persistent session state; the image grows by one 4 KB page. It does not change ADC sampling, classification thresholds, wire colors, or electrical decisions. The known Switch-mode ambiguity through transformer/center-tap paths remains: a modeled cross-pair 1–3 short can still appear good. The stricter inference withdrawn in PN2.33 is not reinstated without real port captures.

## Validation changes

The cabinet scorecard now distinguishes target detection from identification. A silent target is `MISSED`, never a successful identification. A sounding but insufficiently distinct target is `AMBIGUOUS`. The Analog sound-duty model now uses the actual firmware's 30 ms PWM pulse rather than 12 ms; this corrects the test tool, not speaker output. Long reports checkpoint each completed trial atomically and remain marked `complete: false` until all trials finish; a regression test verifies interrupted-run recovery.

`test_current_pair.py` generates the waveform through the current TX TIM2/carrier GPIO code and replays it through the current RX timers, analyzer, and speaker PWM. It covers both modes, phase and clock variation, noise, disconnected/flat input, paused TX output, and repeated contacts. These transport checks supplement, rather than replace, physical cable tests.

Release verification now finds a named RX profile's top-level, experimental, or archived image without requiring an explicit path. It does not silently fall back when a present image is corrupt.

## Reproducible checks

From `LPM-10A/Firmware File/rx-sdk`:

```powershell
python rx_resilient.py --write
python verify_release.py --profile pn1.31
python -W ignore::ResourceWarning -m unittest discover -q
python -m unittest test_rx_impulse_strength test_rx_impulse_bounds test_rx_publication_commit test_rx_resilient test_cabinet_scorecard test_current_pair -q
```

From `LPM-10A/Firmware File/sdk`:

```powershell
python cable_session.py --write
python build.py --profile pn2.34
python -W ignore::ResourceWarning -m unittest discover -q
python -m unittest test_cable_session test_cable_session_integration test_profiles -q
```

The debug scripts under `docs/debug/2026-09-26-rx-tx/` retain historical firmware as negative controls. Their firmware assertions intentionally demonstrate the old faults; use the SDK regression tests above to test the fixed images.

### Focused RX results

- 960 swept/seeded impulse vectors retain the correct weak-tone strength; clean and mixed-edge cases preserve the previous compensation.
- 1,125 weak/noise/code/rail vectors and 7,200 fragment/tail vectors retain detection eligibility.
- 752 fragment geometries exercise 480 accepted paths (8 full-fit, 472 exact-only), with bounded reads and ABI/stack checks. A forced-full-span negative control catches the invalid fallback access.
- The full PN1.31 image passes 1,177 unmasked interrupt/signal-state schedules, 558 gate/mode/gain invalidation schedules, and 50 pending-interrupt schedules across the publication critical section.
- Steady modeled signals retain a single strength level (minimum/median score ratio 1.0); a 6 dB drop settles in 571 ms.

The final RX focused run (impulse strength, bounds, publication, combined release, and release integrity) passes **43 tests in 63.664 s**. The focused TX run (Cable session, current-image cross-feature contracts, profiles, and latest Cable diagnostics) passes **79 tests in 60.135 s**. These overlap with full discovery and are not additive test totals. Independent TX review also reran 25 Cable/Length tests and checked message-ID ownership.

The final paired transport/scorecard run passes **12 tests in 15.363 s**, explicitly reporting TX `92ebb4cd...22227` and RX `3e03d8ac...094c`. This rerun includes the final checkpoint-loss regression. The historical clean-strength/level-display Cabinet tests also pass after the Analog pulse-model correction (3 tests in 136.77 s).

TX full SDK discovery passes **609 tests in 565.971 s, with one skip**. The skip is the opt-in `CABLE_PREVIEW` PNG-render test; physical tests were not run or counted as skips.

RX full discovery completed **709 tests in 2,232.922 s**, with one absent optional device-accepted container fixture skipped. It reported 11 failing subtests and two errors, all in `test_rx_release_profile.py`: four test methods still assumed the default was PN1.30. No firmware-behavior assertion failed. The narrow reproduction confirmed those outdated expectations; tests now exercise PN1.31 default/explicit/alias output, exact hashes, verifier rejection, import order, and its parent chain while retaining PN1.30's exact hashes, named/alias builds, and rejection of PN1.29's payload. The final corrected profile and integrity run passes **16 tests in 1.896 s** (`python -m unittest test_rx_release_profile test_release_integrity -q`).

The 37-minute monolithic RX run was not repeated after this test-only expectation correction. Four bounds tests and the interrupted-scorecard regression added after discovery are covered by the successful focused runs above. Discovery at that checkpoint contained 714 tests. These details are recorded explicitly rather than representing the initial full run as green; no firmware bytes changed for the test correction.

A subsequent final-tree full run was started, but terminated with Windows interruption status `0xC000013A` before completion. It is not counted as a passing full-suite run. Investigation now prioritizes the owner's Analog dropout report above.

### Hardware dropout isolation, not a fix

The confirmed TX mode and same-setup PN1.30 control narrow the regression to the RX update. Further actual-ARM comparisons have not reproduced the PN1.31-only Analog dropout. See the [paired comparison summary and model blind spots](debug/2026-09-26-rx-tx/release_analog_drop_summary.json) and [TX/layout audit](debug/2026-09-26-rx-tx/tx_analog_dropout_audit.md). Immediate modeled ADC conversion, instantaneous gain response and serialized timer schedules are not substitutes for physical sampling/interrupt timing.

Two local diagnostic builds isolate the changes: PN1.31A adds only the Digital estimator to PN1.30, while PN1.31B adds only the shared publication change. Eight new build/isolation tests pass, with independent artifact and Analog smoke review. Neither is a confirmed fix, promoted profile, or GitHub release; no canonical release bytes change. Follow the [owner A/B checklist](RX-ANALOG-DROPOUT-AB-2026-09-26.md) and retain PN1.30 for ordinary use while hardware results are pending.

### Corrected cabinet matrix

The final PN1.31 matrix completed all 48 trials in 234.70 s using two independent mode workers. Three target amplitudes and eight knob settings are tested in each mode. Its verdicts match the PN1.30 baseline; these calm-signal trials establish no general selectivity improvement. The improvement demonstrated separately is resistance to sparse-impulse strength misranking.

| Profile/mode | Target detected | Identified | Missed | Ambiguous |
|---|---:|---:|---:|---:|
| PN1.30 Digital | 24/24 | 14/24 | 0/24 | 10/24 |
| PN1.31 Digital | 24/24 | 14/24 | 0/24 | 10/24 |
| PN1.30 Analog | 18/24 | 12/24 | 6/24 | 6/24 |
| PN1.31 Analog | 18/24 | 12/24 | 6/24 | 6/24 |

The six Analog misses are silent/gated configurations, no longer credited as successful identification. The 2% audibility floor and 12% rhythm-separation rule are fixture criteria, not measured hearing thresholds.

Evidence: [final PN1.31 report](debug/2026-09-26-rx-tx/release_scorecard_final_pn131.json), reproduced from the repository root with `python docs/debug/2026-09-26-rx-tx/release_final_scorecard.py`. Its hash is the released `3e03d8ac...094c`, and `complete` is true. PN1.30 rows come from the [earlier comparison report](debug/2026-09-26-rx-tx/release_scorecard_interim_matrix.json), hash `407b0ba3...67135`. That report's PN1.31 rows used an interim stack-alignment build and are explicitly labeled as such, not used as final-image evidence. A later non-checkpointed final-image run was interrupted before saving; the completed, checkpointed rerun above supersedes it.

## Release artifacts

All files are under `LPM-10A/Firmware File/experimental/`. Standalone builders and named profiles produce the same bytes. The previous top-level device-tested files are not replaced.

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| RX PN1.31 raw (`APP_LPM-10RX_PN1.31-resilient.bin`) | 28,752 | `3e03d8ac13884a0fb3ad752b551ad346eb8e77e11998d7be9ca599923752094c` |
| RX PN1.31 install update (`APP_LPM-10RX_PN1.31-resilient-update.bin`) | 36,864 | `a6352ab9d604874511d835294d8d50fdd105049905b488e1aa263f13ce87126a` |
| TX PN2.34 install image (`LPM-10A-TX_PN2.34-cable-session.bin`) | 405,504 | `92ebb4cd60e7b652f32ca65cfa21401c1657fa63ee1b945864fed3c74a422227` |

The raw RX grows by only 200 bytes, but the update container crosses its next 4 KB padding boundary. Neither bootloader is patched. Checksums and English/Thai installation notes accompany both prereleases.

## Device acceptance checklist

Keep the previous release files available before updating. Install only the RX `-update.bin` on the RX bootloader drive; the raw RX image is for analysis. TX takes its own `.bin`. Installation and rollback details are in [RX notes](releases/rx-v1.31.md) and [TX notes](releases/v2.34.md).

For before/after comparisons, change one unit's firmware at a time and keep the other unit's firmware fixed. Pair RX Analog with TX **Analog 817 Hz**, and RX Digital with TX Digital. Where practical, record successful contacts out of total attempts and estimate first-tone/release timing from a short video; this makes intermittent failures easier to compare without claiming laboratory timing accuracy.

1. RX: confirm `PN1.31.TXT` in update mode; compare against PN1.30 with the same cable, position, knob, and TX mode. Check weak and strong tones, repeated brief contact, continuous contact, Locate/Isolate/off, and removal of the tone. Note delayed first sound, dropouts, flicker, reversed target/neighbor ordering, and stuck sound.
2. RX: check Analog and Digital, mode-change chirps, and NCV using the normal safe operating procedure. Record the knob position and exact mode for any failure.
3. TX: confirm About says `Software:PN2.34`. Test a known-good cable with the RX unit and a known-good switch port. Try rapid OK, Back before start, Back during measurement, mode change/reentry, and normal Retry. No canceled or wrong-mode test should start; Back during measurement is intentionally ignored.
4. TX: verify Length text/progress/result, QC initialization/live indications, SPEED, FLASH, Digital/Analog tone, and PoE only with suitable equipment. Confirm ordinary keys work again after completion.
5. For a failure, send a short video plus mode, knob position, cable/port type, exact key sequence, and whether rollback to PN1.30/PN2.33 removes it. Do not call these device-tested until both units pass.

## Further improvements requiring measurements

Prioritize unsaturated ADC captures at every gain code, then measured first-tone/release latency and target-versus-neighbor success across knob settings. Capture actual switch-port readings before revisiting Switch-mode short inference. These are useful next experiments; increasing sensitivity or loudness without those measurements is not claimed as part of this release.
