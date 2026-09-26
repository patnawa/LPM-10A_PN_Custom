# RX/TX bug hunt — 2026-09-26

Follow-up: the user authorized implementation and publication. The fixes and
current validation are recorded in [RX/TX resilient releases](RX-TX-RESILIENT-2026-09-26.md).
The diagnostic scripts below preserve the old released images as negative controls;
the new SDK regression tests exercise PN1.31/PN2.34.

Original diagnostic scope: shipped RX PN1.30 and TX PN2.33, prioritizing RX detection, sensitivity, and sound. No production code, firmware artifacts, or device state changed during that initial investigation. The subsequently authorized implementation is documented in the follow-up above. Diagnostic scripts are retained in `docs/debug/2026-09-26-rx-tx/`.

Three firmware defects reproduced: two RX regressions and one TX queued-request defect. A separate, previously documented scorecard defect overstates identification success. These are deterministic software reproductions executing actual ARM code with modeled input/interrupt arrival; hardware incidence and physical range are not established.

The diagnosing-bugs workflow was adapted to a broad hunt with no reported symptom: existing behavior contracts supplied the assertions. Reproductions were minimized and competing explanations tested. Production fixes and post-fix checks were outside the requested diagnostic scope; the failure assertions intentionally remain red.

## Findings and priority

### 1. RX Digital impulse noise can reverse cable-strength ordering — P2

In a completed 48-sample Digital window, use code phase 2 with low/high values 1000/1100. Set just samples 34 and 37 to zero. PN1.30 assigns this weak signal a score of **12,864**, versus **3,222** for a clean stronger 1000/1150 signal. Published quiet intervals are **57 ms versus 123 ms**: the weaker noisy signal gets the faster rhythm. Display-level indices are 5 versus 1.

PN1.29 scores the same weak noisy frame at 2,144. Removing either dip restores 2,144 in PN1.30. A broader four-spike comparison also reproduces the regression.

Cause: the [new estimator](../LPM-10A/Firmware%20File/rx-sdk/clean_strength.py) uses only three/four triplet contrasts. In this case, two corrupted triplets produce contrasts 1100, 1100, 100, 100; their median is 600 instead of the true 100. Relevant source: `clean_strength.py:106-139` (model), `:145-224` (executed estimator).

Hypotheses tested: estimator robustness, changed code alignment, gain normalization. The detected alignment stays unchanged, the wrong raw score occurs at gains 0/2/7, and replacing only the estimator call with the prior estimator **in emulator memory** restores 2,144. This isolates the estimator.

Recommendation: preserve PN1.30's mixed-edge compensation while adding enough independent evidence to tolerate multiple impulses. Compare a longer span of triplets or robust fusion with the prior estimator; select the rule against both this corpus and the steady-signal/edge-drift tests. Simply rolling back the estimator would reintroduce PN1.29's flicker.

Limit: these are completed sampler values. A real disturbance must survive the five-read trimmed sampler to create them; its field frequency is unmeasured.

### 2. RX fast gain can discard the first valid strong frame — P2

With a valid first strong frame, inject one legal TIM1 interrupt immediately after the display-generation marker is stored at `0x0800D59A`. Both Digital and Analog finish with **gain=2, grade=0, recent=0**: the signal was analyzed but never published to the sound state. The uninterrupted control publishes normally.

The next accepted publication requires a complete new acquisition: **241.40 ms Digital / 21.26 ms Analog** in the model. These measure feedback publication, not physical speaker onset. Brief contacts may be missed or first feedback delayed; permanent signal loss was not reproduced.

Cause: [`clean_strength.py:238-241`](../LPM-10A/Firmware%20File/rx-sdk/clean_strength.py) stamps `LAST_DISPLAYED` at curve entry, before the guarded publication at line 330. TIM1 trusts that stamp at lines 411-424 and changes gain. The existing gain invalidation and publication guard then correctly reject the stale-gain result (`digital_gain_continuity.py:34-49`, `release_hold.py:44-51`).

Hypotheses tested: early display marker, invalid signal fixture, 500-ms gain path, expired samples. Moving the same interrupt just before the marker succeeds; hiding only the marker during the interrupt succeeds. Completion timestamps are equal and fresh, and the injected tick is not the 500-ms path. A separate future-sample interference control passes.

Recommendation: commit the displayed-generation marker atomically with successful guarded sound publication, using the analyzed generation. Retain the gain-generation protections. Test every interruptible point across this handoff, including first contact, continuing sound, rejection, and mode changes.

### 3. TX queued Cable Test starts survive Back — P2

From an RX-unit result screen, delay GUI consumption, enqueue OK twice through the real key handler, then press Back. The delayed requests execute **792 ADC reads in Switch mode**, although the user canceled an RX-unit test. A single pending OK is enough to undo Back and re-arm the Switch result layout without measuring.

Cause: [`cable_check.py:140-155`](../LPM-10A/Firmware%20File/sdk/cable_check.py) checks `BUSY` only before enqueue and checks only the screen number on delivery. Back to the mode selector stays on screen 4, resets mode, and leaves queued requests eligible.

Controls: no pending request preserves the selector; claiming busy before a second request suppresses duplication; leaving fully to Home drops stale requests; preserving RX selector mode changes the wrongly executed routine back to RX.

Recommendation: carry a visit/mode generation with queued work, invalidate it on Back, and coalesce pending Start requests. Guard the pending state as well as the measuring state. Actual queue-delay frequency on hardware is unmeasured.

### 4. RX scorecard credits silence as correct identification — validation defect

[`cabinet_scorecard.py:83-90`](../LPM-10A/Firmware%20File/rx-sdk/cabinet_scorecard.py) returns `True` for `[('T', 0.0), ('N3', 0.0)]`. The actual PN1.30 Analog run at knob 512/4095 and target amplitude 3000 produces seven silent visits and is still marked identified.

The predicate checks only whether a sounding neighbor is insufficiently weaker than the target; it never requires an audible target. This limitation was acknowledged in the September 23 IntelliTone analysis and is still present. It is not a newly established firmware sensitivity failure.

Recommendation: report target detected, target distinguishable from neighbors, and missed/silent separately. Silent/gated configurations should not count as successful identification. Recompute the published scorecard after correcting that metric.

## Reproduce

Run from the repository root with the existing Python/Unicorn environment. Each command was run during diagnosis. The firmware scripts retain the old images and intentionally fail on those faults. The scorecard reproduction imports the current tool and now passes after the follow-up correction; the output below records its original failure.

```powershell
python docs/debug/2026-09-26-rx-tx/rx_impulse_strength.py -v
python docs/debug/2026-09-26-rx-tx/rx_fast_gain_handoff.py
python docs/debug/2026-09-26-rx-tx/release_scorecard_repro.py
python docs/debug/2026-09-26-rx-tx/tx_cable_contracts.py ReleasedCableContracts.test_two_old_starts_must_not_run_after_back_to_mode_selector -v
```

Observed signals:

```text
Impulse: 12864 not less than 3222; removing either dip and estimator-only control pass.
Fast gain: final=(2, 0, 0) in both modes; marker-position and uninterrupted controls pass.
Scorecard: silent visits ... score=(True, [], ...).
TX: 792 != 0 : canceled RX-unit starts performed 792 ADC reads in ['Switch']; mode=0x10.
```

Typical test-body times: 0.13 s impulse, 0.23 s handoff, 5.7 s real scorecard, 0.72 s narrow TX reproduction. Scripts pin the tested image hashes. Multiple failed assertions/subtests can describe the same defect; do not count them as separate bugs.

## Validation and further improvements

Release integrity is clean. RX `python verify_release.py` reproduces the current update; its raw payload SHA-256 is `407b0ba3b80883e4f640ef7e2040a56004ca780a5bd8b81cf3a371ca04a67135`. TX profile tests reproduce PN2.33 SHA-256 `84f9fb991a5bf43f0e29d978277ebe76baa58ff21714b430c1b6cef040751e91`.

Existing current RX clean-strength/knob tests passed (24 tests). Selected RX release/profile/container/image checks passed (43 tests, one skip), as did 12 TX profile checks. The 31 passing TX tone tests exercise PN2.27/PN2.27A ancestors; they are not claimed as a new whole-device PN2.33 verification. No connected-hardware tests were run.

After the two RX fixes and metric correction, prioritize:

1. **Replay the current pair end to end.** `test_scan_pair.py:35-37` still selects TX PN2.13/RX PN1.10. Current field streams synthesize the waveform in `test_rx_isolate.py:425-435`. Reuse the transport seam with PN2.33/PN1.30, including phase drift, short contacts, noise, and mode changes.
2. **Calibrate gain using unsaturated captures.** Current normalization derives from one unit; high-gain ratios were measured while saturated. Record gain-code response on weak signals across units before tuning sensitivity or 3-dB level thresholds. See `RX-CLEAN-STRENGTH-PN1.30-2026-09-24.md`.
3. **Measure sound timing and identification accuracy.** Collect first-tone/release latency and correct-pair rate for short repeated contacts, several knob settings, and controlled neighboring cables. Existing sound tests establish PWM compare values and modeled timing, not acoustic loudness or real pickup distance.

Known TX limitation: Switch mode still gives green for a modeled cross-pair 1-3 short. PN2.33 deliberately withdrew the stricter partner check after real switch center-tap paths caused false failures. This is already documented in `TX-CABLE-TEST-AUDIT-2026-09-23.md` and `cable_safe.py`; gather real port traces before changing that inference again.

Minor tooling issue: `verify_release.py --profile pn1.29` does not automatically find its archived image; passing the explicit archive path verifies successfully. This has no effect on the current firmware images.
