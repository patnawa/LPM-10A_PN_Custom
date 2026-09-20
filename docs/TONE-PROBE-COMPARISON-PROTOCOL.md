# Tone Probe cable-finding comparison protocol

Revision: 1. Date: 2026-09-20. **Status: COMPARISON NOT RUN.**

No physical LPM-10A versus Fluke measurements are present in this document or
the accompanying CSV templates. Firmware emulator results are not substitute
measurements. On 2026-09-20 the owner confirmed that **no Fluke comparator is
available**. Physical comparison therefore has not started, and comparator
serial numbers have not been established.

Following the RX PN 1.12 / TX PN 2.14 test request, the owner now reports both
Digital and Analog receive and cable sweeping is more accurate. Later feedback
reports an open Digital release issue: sound continues about one second after
moving away or pressing TX Pause; Analog does not show this delay.
This is initial qualitative local-device feedback. The owner confirms TX PN 2.14
and the RX filename `APP_LPM-10RX_PN1.12-overload.bin` (PN 1.12). See the
[owner record](TONE-DEVICE-FEEDBACK-2026-09-20.md). A completed Level B protocol
and Level C comparative evidence are still missing.

## สรุปภาษาไทย

เป้าหมายคือ **เลือกสายถูก เสี่ยงเลือกผิดต่ำ และทำงานเสร็จเร็ว** ทั้งในมัดสาย
แน่นและเมื่อมีสัญญาณรบกวน การรับได้ไกลขึ้นหรือเสียงดังขึ้นอย่างเดียวไม่พิสูจน์
ว่าแยกสายได้ดีขึ้น และรหัสดิจิทัลที่รับได้อาจเป็นสัญญาณรั่วมาจากสายข้างเคียง

ขั้นแรกทดสอบ LPM-10A รุ่นเดิมกับรุ่นปรับปรุงได้โดยใช้สายที่ถอดจากระบบแล้ว
โทรศัพท์ถ่ายวิดีโอ ไม้บรรทัด และผู้ช่วยที่ซ่อนเฉลย ไม่ต้องมีออสซิลโลสโคป
ขั้นนี้ใช้ตรวจบั๊กและหาข้อถดถอยของเครื่องเราได้ แต่ยังสรุปว่าเหนือกว่า Fluke ไม่ได้
เจ้าของยืนยันเมื่อ 2026-09-20 ว่ายังไม่มีเครื่อง Fluke สำหรับทดสอบเทียบ

การยืนยันเป้าหมายต้องมีเครื่อง Fluke IntelliTone Pro 200 พร้อม TX/RX ของมัน
ทดสอบบนสภาพสายเดียวกันโดยใช้โหมดที่เหมาะสมของแต่ละเครื่อง ซ่อนสายเป้าหมาย
สุ่มลำดับทดสอบ เก็บทั้งครั้งที่ถูก ผิด เงียบ และเลือกไม่ได้ รวมถึงเวลาและหลักฐาน
ยืนยันสายจริง ต้องแยกผลค้นหาโดยโพรบออกจากผลยืนยันทางไฟฟ้า

เอกสารนี้กำหนดวิธีทดสอบและเกณฑ์ตัดสินล่วงหน้า **ยังไม่มีผลผ่านหรือคำรับรอง
ว่าเหนือกว่า Fluke** การอ้างว่าเหนือกว่าต้องระบุรุ่นคู่เทียบ ประเภทสาย สภาพการใช้
และช่วงความไม่แน่นอนของผล ไม่ขยายผลเป็น “ดีที่สุดในโลก” จากคู่เทียบเพียงรุ่นเดียว

## 1. Benchmark capabilities and scope

Use a complete IntelliTone Pro 200 LAN kit, identifying the exact toner, probe,
hardware revision and manual revision. Fluke documents digital Locate and
Isolate probe modes and direct CableMap verification. The appropriate reference
workflow therefore includes Isolate when selecting a cable, not just Locate.
Its published datasheet does not supply a numerical bundle-selection error
rate or end-to-end latency that can be treated as a measured baseline.
[Official IntelliTone datasheet](https://www.flukenetworks.com/content/datasheet-intellitone-pro-toner-and-probe-series).

Fluke acknowledges that coupling can still make some adjacent cables difficult
to distinguish. Include those difficult geometries; do not assume that a
recognized digital code establishes cable identity.
[Official cable-isolation guidance](https://www.flukenetworks.com/knowledge-base/intellitone/isolating-individual-cable-intellitone).

The retrieved manual is Rev. 2, September 2017. It describes the digital
Locate/Isolate procedure, dry unterminated-pair SmartTone operation, and direct
cable-map tests. Follow the manual applicable to the actual comparator.
Shielded-cable and active-network results must be reported separately; do not
transfer a manufacturer's documented operating capability to the other device.
[Official IntelliTone user manual, pages 5–10](https://media.fluke.com/dc26ce0f-c9f4-45bd-a518-b10800bf3772_original%20file.pdf).

For digital trials, each receiver uses its **own compatible transmitter**.
For analog trials, each system likewise uses its own supported connection and
tone. Cross-brand interoperability is a different experiment. Do not force
Fluke to receive the LPM carrier or disable its normal Isolate procedure to
equalize buttons. Any LPM direct-confirmation accessory and the corresponding
Fluke CableMap workflow are included in full-workflow time and disclosed.

This revision measures cable finding, feedback, and associated usability. It
does not certify electrical protection, EMC, battery lifetime, or universal
compatibility. A claim covering another world-class probe requires naming it,
adding its documented workflow, and collecting its own comparison data.

## 2. Evidence levels

| Level | Equipment and method | What it can establish |
|---|---|---|
| A — Firmware | Known binary hashes, actual ARM execution, synthetic/captured ADC inputs, regression tests | Defined software behavior, reproducibility, and modeled failures; not physical pickup, range or competitor performance |
| B — Local device check | One LPM TX/RX, disconnected labeled cables, helper, ruler, phone video | Real operation, regressions, coarse response timing and blinded selection on those fixtures |
| C — Comparative field test | Both complete systems, hidden targets, randomized balanced trials, independent ground truth, retained recordings | Scoped comparative accuracy, error rates, response and workflow time |
| D — Engineering characterization | Suitable probes/instruments, characterized fixtures and signal injection, input/output traces | Front-end limits, real timing, clipping, drive balance, analog transfer and electrical compatibility within tested limits |

Levels B and C do not require an oscilloscope. Level D becomes necessary for
claims about unknown drive topology, clipping-free dynamic range, physical
selectivity in dB, or new electrical operating limits. Record an unavailable
measurement as missing, not as zero and not as passed.

## 3. Freeze the study before evaluating the final candidate

Create a study manifest beside the results containing:

- Candidate and baseline TX/RX versions, complete binary SHA-256 hashes, build
  command and source revision. Record any local source changes separately.
- A device registry linking masked aliases to model, serial number, hardware
  revision, accessories, manual revision, firmware where visible, and battery
  type/state. Keep alias mapping hidden from the analyst until scoring is fixed.
- Fixture registry: cable category/shielding, actual lengths, conductor gauge
  if known, bundle count, parallel length, tie spacing/tightness, connector and
  termination state, target center/edge positions, photo, and a hidden end map.
- Prespecified claimed use cases and excluded ones, interference-source model,
  distance/orientation and setting, mode/sensitivity policy, deadlines, trial
  count, random seed, randomization schedule, analysis and exclusion rules.
- Operator experience, training procedure, available aids, time source/video
  settings, ambient conditions, protocol revision and dates.

Use pilot fixtures to improve firmware and estimate variance/error frequency.
Reserve different cable assemblies/configurations for the final comparison.
Once final evaluation begins, freeze firmware, thresholds and analysis rules.
A code or threshold change starts a new evaluation cohort; never silently mix
results from multiple candidates.

## 4. Repeatable fixture matrix

The values below are **planned test conditions**, not measured product limits.
Use measured available lengths, document deviations before testing, and keep
the final claim no broader than the conditions actually covered. A fractional
design is acceptable if fixed in advance; do not imply every combination was run.

| Dimension | Core comparison | Separate extensions |
|---|---|---|
| Bundle size | 12, 24 and 48 cables | Smaller/larger installation-specific bundles |
| Parallel run | 1 m and 10 m | Long trays, loops and repeated crossings |
| Total cable length | Short 5–10 m; medium 25–30 m; long 80–90 m | Other measured lengths |
| Cable construction | Cat5e and Cat6 UTP | Cat6A, shielded cable, telephone pairs, coax — separate strata |
| Target position | Balanced center and edge targets; adjacent connectors | Deeply buried target, mixed diameters, metallic tray |
| Termination | Open/dry; passive unpowered patch panel | Supported powered Ethernet and PoE classes only after exact compatibility is established |
| Interference | Quiet; ordinary enclosed charger/LED supply nearby; second compatible toner on another disconnected cable | Characterized mains/harmonic/RF field fixtures in a suitably equipped setting |
| Pickup geometry | Tip positions fixed by nonconductive guides; consistent orientation | Handheld realistic sweeps and changed hand positions |
| Signal extremes | Weak standoff, close contact, strong-to-weak move, TX off/on | Characterized overload and analog compression |
| Power | Normal operating battery; low-but-still-supported battery indication | Quantified battery discharge/lifetime test |

Record source distance and exact operating state for every interference trial.
An ordinary charger experiment is an environmental observation, not a calibrated
EMC test. Do not place exposed mains conductors in the fixture or inject mains
into a cable under test.

Keep the probe's tip-to-jacket distance and orientation repeatable for the
controlled comparison. Use the same human-access constraints for the workflow
comparison, while allowing each manufacturer's recommended technique. Document
whether moving/separating cables is permitted and count those actions.

## 5. Blinded selection sequence

There are three roles: setter, operator and scorer. Two people can combine
setter/scorer if video preserves the observations. The operator must not know
the target; the tester brand cannot reliably be blinded during use. Describe
this as **target-blinded**, not double-blind.

1. Give equal practice with each system on fixtures excluded from evaluation.
   Prespecify allowed mode and sensitivity changes. Use the comparator's normal
   Locate-to-Isolate workflow. Photograph initial controls and battery states.
2. The setter verifies the cable-end map independently by physical tracing or
   a separately established direct electrical map. A tone response is not ground
   truth. Keep labels at the TX end and the answer sheet hidden from the operator.
3. Build randomized blocks by fixture class, target center/edge class and
   operator. Within each block, balance device order using shuffled AB/BA orders.
   Randomly choose targets and no-target trials from a schedule saved before the
   first evaluation run. The schedule records seed, algorithm and its full output.
4. Run matched configurations with both devices, but conceal and randomize the
   target again before the second run. Relabel visible cable IDs and reset the
   fixture as needed to prevent remembering the earlier answer. Treat these as
   matched **conditions**, not identical independent trials. If the same exact
   target is reused, use a different blinded operator and record the pairing.
5. Only the selected system transmits; other transmitters are off/disconnected
   except in the specified interferer condition. The operator starts at a fixed
   mark with the probe away from the bundle. Start the timer on the same cue.
6. Allow a planned **60 s selection deadline**. Before electrical confirmation,
   the operator says a cable ID or “inconclusive” and confidence `low`, `medium`
   or `high`. Record the first committed answer permanently. A later correction
   does not erase an initial wrong selection.
7. Perform the system's documented direct-confirmation workflow when available.
   Record method, confirmed ID, result and total time from the original start.
   Use a planned **120 s full-workflow deadline**. An independent ground-truth
   check still follows; a device's own confirmation claim does not grade itself.
8. Include **20% no-target trials**, hidden from the operator: TX disabled or
   disconnected while all other appearances match. On some no-target trials,
   keep only the specified independent interferer active. Any selected cable is
   then a false selection. Report these separately from target-present accuracy.
9. Record crashes, silent runs, unplanned resets, mode mistakes and timeouts.
   Device-caused failures count. Exclude only a prespecified external failure
   such as a verified miswired fixture, retain its row and reason, and rerun the
   full affected comparison block rather than selectively rerunning a bad score.

Retain the full raw sequence, including unsuccessful trials. Avoid coaching
after individual answers; use the same feedback policy for both devices.
Repeated sweeps of one unchanged bundle are repeated observations within one
fixture, not evidence from many independent installations.

## 6. Outcome definitions and acceptance rules

The following margins are engineering acceptance targets selected for this
project. They are not specifications published by Fluke. Freeze them before
looking at final comparison results.

| Measure | Definition and denominator | Planned requirement |
|---|---|---|
| Correct first selection | Correct committed ID within 60 s / all target-present trials; inconclusive and timeout remain in denominator | Candidate at least 95% observed; lower 95% confidence bound of candidate-minus-reference above −2 percentage points |
| Wrong selection | Incorrect committed ID / all target-present trials | Upper 95% confidence bound of candidate-minus-reference below +1 percentage point |
| Confident wrong selection | Incorrect first selection marked `high` / all target-present trials | No observed event in final cohort; report upper confidence bound rather than claim zero risk |
| No-target false selection | Any cable selected / all no-target trials | Upper 95% confidence bound of candidate-minus-reference below +1 percentage point |
| Inconclusive/timeout | Each separately / all target-present trials | Report both; cannot improve error rate by discarding or silently accepting misses |
| Correct full workflow | Correct first selection plus independent direct confirmation within 120 s / all target-present trials | Lower 95% confidence bound of candidate-minus-reference above −2 percentage points |
| Failure-penalized time | Total time to a correct first selection and confirmation; assign 120 s to incorrect, unconfirmed or timed-out trials | Upper 95% confidence bound of candidate/reference mean-time ratio below 0.80 for the planned speed-superiority claim |
| User burden | Mode/sensitivity changes, cable separations, resets and operator-rated clarity/difficulty | Report by operator and condition; identify new gestures and confusion, not just average time |

All accuracy/error gates and the time gate must pass for the planned combined
claim of faster bundle identification without materially worse selection risk.
Also report uncensored successful-trial median/p95 time, but never use it alone:
a detector could otherwise appear faster by failing all difficult trials.
Report time to first selection separately from time including confirmation so
the source of a performance difference remains visible.

Use prespecified condition weights and cluster-aware paired analysis across
matched blocks; retain operator, physical fixture and repeated-run structure.
Select the interval method and handling of sparse/zero errors before evaluating
the final cohort. A cluster bootstrap must resample whole independent fixtures,
not individual sweeps; with too few independent fixtures its interval is weak.
Seek an appropriate statistical review for a public broad superiority claim.

Plan sample size from pilot variance and paired discordance for at least 80%
power at the chosen 95% interval gates. Begin planning with at least 300
target-present trials **per system**, at least 12 independently assembled
fixtures and at least 3 trained operators, plus the no-target trials. These are
coverage starting points, not a guaranteed sufficient sample size. Inflate for
clustering and rare-error requirements; use more independent fixtures rather
than repeating one fixture indefinitely.

For perspective, with 300 genuinely independent trials and zero errors, the
exact one-sided 95% binomial upper error bound is
`1 - 0.05**(1/300) = 0.009936`, about 0.99%. It is not a bound for clustered
repetitions or every possible installation. A small zero-error demonstration
does not establish the +1 percentage-point error gate.

Publish results by bundle size, cable construction, termination, interference,
target position, battery state and operator. Strong performance in easy cases
must not conceal failures in a claimed hard-use stratum. Unsupported/unrun
strata stay explicitly outside the demonstrated claim. Failure of a gate means
“not demonstrated” or “regressed,” followed by development and a new held-out
evaluation; it does not justify selecting a more favorable subset afterwards.

## 7. Latency, interference and adjacent coupling diagnostics

Selection accuracy is the primary bundle result. These diagnostics explain why
it changes and guide the next firmware iteration.

| Diagnostic | Repeatable procedure | Record |
|---|---|---|
| Acquisition | Fixed quiet-to-target move through a marked plane, and separately TX-off to TX-on at fixed geometry | Physical trigger, first output change, first usable indication, misses and observation limit |
| Release | Move from target to a marked no-signal location, and separately switch TX off | Last retained indication and time until usable no-signal indication |
| Strength tracking | Move from strong target to weaker target/coupled neighbor at marked positions, then reverse | Time until output reflects new location; overshoot/stale indication; correct stronger/weaker choice |
| Interferer rejection | Target off/on crossed with independent interferer off/on | False signal indications, misses and wrong cable selections; duration/count per observation period |
| Adjacent coupling | Keep TX connected only to target; visit each cable at fixed tip geometry in randomized order | Target rank, tied ranks, strongest neighbor, raw visible/audible feedback and selection result |
| Overload recovery | Repeat close-contact then weak-standoff move at supported settings | Whether overload is indicated; recovery latency; persistent max indication or silence |

Use at least 20 repeats per diagnostic condition in development; final sample
size depends on measured variability. Record failures/censored observations as
well as successful timings. A slow or missing response must not disappear from
the average. The trigger is the actual geometric crossing or observed TX action,
not an assumed internal interrupt instant.

A phone recording at a verified 60 fps resolves frames about 16.7 ms apart;
two-event intervals have endpoint and human annotation uncertainty. Retain the
original variable-frame-rate timestamps or verify constant rate before using
frame count divided by fps. Check audio/video offset if measuring sound against
a visible trigger. Do not claim a 5 ms improvement from 60 fps video.

Define “usable indication” before running the diagnostic: identify the exact
audible/visible cue and the same stability criterion appropriate to each output
(for example, a reproducible stronger/weaker judgment lasting 200 ms). Retain
both first-change and stable/usable timings so a brief spurious beep is not
counted as a successful fast response. Pilot this scoring rule on excluded data.

LPM audio cadence and Fluke LED steps are ordinal product outputs. Do not divide
them or call their ratio dB. Target-to-neighbor dB contrast requires a calibrated
linear measurement with known gain and no clipping. A coupled copy of the
target code is not an unrelated false code; grade its consequence using wrong
selection and target ranking.

## 8. Immediate checks possible without a scope or comparator

Use a disconnected 12-cable bundle with a hidden TX connection and end labels
verified before bundling. A helper chooses a different target for each attempt.
Test Digital and Analog separately and save the phone recording.

1. Do 20 target-present and 5 no-target attempts per mode/firmware combination.
   Record initial selection, confidence and elapsed time even when unsuccessful.
2. At a fixed probe position, exercise TX mode changes, pause/resume and the
   RIGHT key. Record silent/stuck states and whether the expected tone returns.
3. Move the probe from close target contact to a nearby cable, then away from
   the whole bundle; repeat in both directions. Look for stale strong feedback,
   prolonged silence, unexpected resets and poor distinction between cables.
4. Repeat near an ordinary enclosed interference source at a recorded distance.
   Repeat with normal and low-but-supported battery indication if available.

This is a small regression/pilot set. It is useful even when the comparator and
instruments are unavailable, but cannot pass the final comparative gates above.
Do not change firmware based on only the easiest fixture or reuse this tuning
set as the sole final performance evidence.

## 9. Connection and confirmation boundaries

Start the equipment-free protocol on detached, unpowered cables. No result here
authorizes connecting modified firmware to a live system outside its hardware's
established ratings. Powered Ethernet, PoE, shield bonding and public telephone
connections require their own documented compatibility and test setup. An
unverified condition is `not_run`, not a competitor failure.

Direct cable mapping is a different path from air-coupled digital recognition.
For a fair full-workflow result, disclose each system's necessary remote/adapter,
access to cable ends, and connection/disconnection time. SmartTone short/open
confirmation is limited by its applicable dry-pair instructions; do not apply
that procedure to live Ethernet/PoE or assume the LPM implements it.
[Official IntelliTone user manual, SmartTone section](https://media.fluke.com/dc26ce0f-c9f4-45bd-a518-b10800bf3772_original%20file.pdf).

## 10. Raw data files and field rules

- [Selection/workflow CSV template](experiments/tone_probe_comparison_trials.csv)
- [Latency/coupling diagnostic CSV template](experiments/tone_probe_comparison_diagnostics.csv)

Both templates intentionally contain **headers only**. No illustrative numeric
rows are supplied that could be mistaken for observations. Copy to a study
directory; preserve the empty templates. Use UTF-8 CSV and decimal points;
quote notes containing commas. Never place a seed or schedule in a hidden-label
field where the operator can see it during testing.

`trial_state` is `planned`, `completed`, `excluded_external`, or `not_run`.
`trial_class` is `target_present` or `no_target`. `selection_outcome` is
`correct`, `wrong`, `inconclusive`, `timeout`, `correct_rejection`,
`false_selection`, or `not_run`. The last two measured outcomes apply only to
no-target trials. `selected_id=NONE` denotes a deliberate no-cable answer;
on target-present trials that is inconclusive, while on no-target trials it is
a correct rejection. A silent timeout is recorded as timeout in either class.
`confirmation_outcome` is `confirmed_correct`, `confirmed_wrong`, `inconclusive`,
`timeout`, `unavailable`, or `not_run`. A device crash remains a completed failed
trial with its reset/interruption fields populated. `ground_truth_id=NONE` only
means a deliberately verified no-target trial, not an unknown target.

An empty numeric cell means unmeasured/unavailable; numeric zero means observed
zero. `correct_workflow_by_deadline` is `1` only if the first selection was
correct and independently confirmed within the workflow deadline, otherwise
`0` for completed trials. Record the elapsed time of an early wrong answer, and
derive its failure-penalized time as 120 s during analysis; do not rewrite raw
time. Count all completed trials in the appropriate denominator.

Registry IDs link to the study manifest rather than duplicating long fixture
descriptions. `condition_id` specifies termination, interference, tip/sweep
policy and other controlled settings for that trial; the same condition is
used by both systems in a comparison block. `interferer_registry_id=NONE` means
deliberately absent interference, while a blank value means not recorded.
`protocol_revision`, `fixture_revision`, `study_id`, `block_id`,
operator and device identity are essential to prevent combining unlike runs.
Selection confidence is the operator's stated confidence, not a calibrated
probability. `evidence_sha256` identifies the original recording/file; retain
uncut recordings and analysis annotations separately.

For diagnostics, `metric` is `acquisition`, `release`, `tracking`,
`interference`, `coupling`, or `overload_recovery`. `censored=1` means no usable
response by `observation_limit_ms`; keep the limit and leave unobserved latency
blank. `raw_feedback` describes the native indication, and `feedback_units`
names that representation. `target_rank` is ordinal and includes ties in notes.
`false_indication_count` is counted over the recorded `observation_limit_ms`;
record the indication rule in the study manifest before measurement.

## 11. Evidence needed before claiming success

The completion record must contain a released-for-test candidate hash, passed
relevant firmware regressions, real LPM device checks, the comparator registry,
frozen protocol and random schedule, fixture ground truth, all raw results,
recordings, prespecified analysis with uncertainty, and a result for every
claimed condition and acceptance gate. Independent repeat testing on previously
unused fixtures should reproduce the conclusion before making a broad public
performance claim.

Current status for the comparison is **NOT RUN / superiority unproven**. The
existing [optimization study](TONE-BUNDLE-OPTIMIZATION-2026-09-20.md) and
[firmware performance audit](TONE-PERFORMANCE-AUDIT-2026-09-20.md) identify
engineering opportunities. They do not fill the missing physical comparison
rows or establish parity/superiority by themselves.
