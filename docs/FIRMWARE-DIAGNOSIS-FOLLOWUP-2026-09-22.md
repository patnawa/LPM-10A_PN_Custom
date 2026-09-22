# Firmware diagnosis follow-up, 2026-09-22

The request was to actively find and fix defects, without a reported device
symptom. This pass therefore used reproducible CPU behavior and build-tool
contracts as its failure criteria. The workspace already contained the
[earlier deep audit](DEEP-AUDIT-2026-09-22.md), its TX/RX experimental fixes and
other uncommitted changes. Those were preserved and independently checked.

## Results

| Area | Reproduced failure | Result of this pass |
|---|---|---|
| Shared Thumb assembler | `str r0, [r1], #4` becomes `str r0, [r1]`; the requested pointer update is lost. Several ALU instructions also silently discard extra operands. | Fixed operand validation and added regressions. |
| RX PN 1.23 gain changes | TIM1 changes gain during analysis; an old window can publish a new strength grade using the changed gain. | Confirmed the existing PN1.23F correction; added a 433-location interrupt regression. |
| TX PN 2.23 SPEED | An all-ones failed PHY ability read displays advertised speeds such as `10/100`. | Confirmed the existing PN2.23S correction; added full-screen rebuild and live read/recovery regressions. |

The newly changed production code is the shared assembler. This pass did not
find a further runtime defect in the existing TX/RX experimental corrections.
It did not change their binaries or promote them to the release defaults.

## Assembler: reproduction, cause and fix

From `LPM-10A/Firmware File/sdk`, the permanent red-capable command is:

```powershell
python -m unittest test_thumb.ThumbTests.test_unsupported_addressing_and_extra_operands_are_rejected -v
```

Before the fix: **14 failing subcases**, each `AsmError not raised`, in 0.001 s.
The smallest reproduction is one instruction, `str r0, [r1], #4`. Its output
was `0860`, independently disassembled as `str r0, [r1]`. Executing those bytes
with Unicorn stored the value but left `r1 = 0x20000000`, instead of advancing
it to `0x20000004`.

The ranked hypotheses were: the encoder ignores extra operands; the parser
loses them; or the disassembler omits an encoded writeback. Inspection showed
the parser returned all three operands, and CPU execution ruled out a display
artifact. The encoder indexed the first two operands without checking the
rest. This is the confirmed root cause.

`lpm10a/thumb.py` now validates operand counts before selecting operand values.
Unsupported post-index addressing and three-register forms of the supported
two-register ALU instructions raise `AsmError`. Missing operands and trailing
commas also fail explicitly. No new instruction form is approximated.

The missing-operand test failed before the fix with one silent-acceptance
failure and nine unexpected Python exceptions. Both new tests pass after the
fix. All supported instruction round trips and pinned profile rebuilds still
pass; existing firmware bytes are unchanged. An independent review checked
the operand table against every implemented encoder and exercised additional
stack, barrier, branch and memory forms without a compatibility failure.

## RX: interrupt coverage for the existing correction

The released parent reproduces stale publication during both real Digital and
Analog analyzers. One fixture changes Digital quiet interval from 73 ms to
56 ms after a gain interrupt; Analog changes from 66 ms to 42 ms. These are
emulator state values, not measured device acoustics.

The new regression traces a clean accepted window, then interrupts at each
unique unmasked instruction on its first visit: 245 Digital locations and
188 Analog locations, including the real DFT. Each run executes the real TIM1
gain path, resumes analysis, runs the speaker guard and crosses the main-loop
ownership boundary. It verifies that the invalidated acquisition cannot start
new feedback and that grade, freshness and all sampler indices are reset.

The fixture must first publish successfully without an interrupt. This guards
against a test that passes merely because detection never works. The sweep is
bounded, deterministic and takes about five seconds on this machine. It does
not enumerate every loop iteration, nested interrupt schedule or NVIC priority.
As a negative control, substituting the unpatched PN 1.23 parent causes all
433 scenarios to fail; the candidate passes the same assertions.

## TX: real read-to-display paths

On released PN 2.23, register 5 = `0xFFFF` and register 10 = `0` produces
`10/100`. The same full-screen assertion expecting `Unknown` fails on the
parent in 0.38 s and passes with PN2.23S. Both language paths are covered.

The second new regression uses one live emulated screen and the actual MDIO
read hook: valid gigabit advertisement, failed read, then valid 10 Mbps
advertisement. The displayed row transitions `10/100/1000` -> `Unknown` -> `10`
without replacing cached values directly. Retry and error behavior also pass
the existing tests.

## Validation

Commands run from their respective SDK directories, in separate processes:

| Directory | Command | Result |
|---|---|---|
| `sdk` | `python -m unittest discover -p "test_*.py" -q` | Baseline: 288 tests passed in 115.420 s. Discovery preceded the four new TX tests. |
| `rx-sdk` | `python -m unittest discover -p "test_*.py" -q` | Baseline: 451 tests in 539.680 s, no failures, one optional sample skipped. Discovery preceded the new interrupt test. |
| `sdk` | `python -m unittest test_thumb test_profiles -q` | 26 tests passed, including the two new assembler tests and pinned TX rebuilds. |
| `sdk` | `python -W ignore::ResourceWarning -m unittest test_speed_partner_validity test_speed_partner test_length_ref_reset test_cable_values -q` | 33 tests passed, including the two new SPEED tests. |
| `rx-sdk` | `python -m unittest test_rx_auto_range_freshness test_rx_pn121_pn122 test_rx_digital_overlap test_rx_analog_feedback_races -q` | 27 tests passed, including the new interrupt sweep. |
| `rx-sdk` | `python -m unittest test_profiles test_release_integrity test_container -q` | 22 tests ran successfully; one optional external sample was skipped. |
| `rx-sdk` | `python verify_release.py` | Current PN 1.23 update exactly matches its rebuilt profile and canonical container. |

The two complete baseline suites cover 739 test cases. The five newly added
regression methods passed in the targeted runs above. The RX skip is
`device-accepted sample not on this machine`; the earlier audit's 417-test RX
count does not describe this later tree. Existing TX font-loading code emits
`ResourceWarning` messages; these were not test failures.

The existing TX candidate (397,312 bytes), RX candidate raw image (26,760 bytes)
and RX update container (32,768 bytes) exactly match fresh candidate builds and
canonical wrapping. Their SHA-256 values remain those in
[`AUDIT-2026-09-22-SHA256SUMS.txt`](../LPM-10A/Firmware%20File/experimental/AUDIT-2026-09-22-SHA256SUMS.txt).
Both current release files also match their existing manifest. No temporary
debug instrumentation remains in the changed code or tests.

No device was flashed. Gain settling, real acoustic response, electrical PHY
failure behavior and compatibility with other hardware revisions still require
physical validation. The experimental fixes are available for that validation;
emulation is not a claim of a hardware pass.
