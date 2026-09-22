# Project audit: firmware correctness and build integrity

Audit baseline: commit `7e1e5e9`, TX PN 2.23 and RX PN 1.23. This review traced
the Python patch builders and the ARM code they emit, exercised the real
firmware routines under Unicorn, rebuilt historical profiles, and checked the
release workflow. No device was flashed and no distributed firmware was changed.

The main new firmware findings are a gain/sample ownership race in the RX and
misleading switch capabilities after a failed MDIO read in the TX. Both have
separate experimental corrections. Tooling fixes apply immediately; released
profiles retain their original bytes and remain the build defaults.

## Findings, ranked

P1 means address before the next release; P2 means a reproducible correctness
or verification defect. These priorities describe impact, not evidence of an
observed hardware failure.

| Priority | Finding | Reproduction / consequence | Disposition |
|---|---|---|---|
| P1 | RX changes gain while a window is being analyzed | Interrupt a Digital or Analog analyzer at the strength normalizer with the real TIM1 AGC. PN 1.23 publishes old-gain samples using the new gain state. | Opt-in gain freshness correction; hardware validation remains. |
| P1 | Release publisher deletes unrelated binaries before checking inputs | Old `publish_current.py` deletes every unselected root `.bin`, then discovers a missing source. Importing the module also performs publication. | Fixed: explicit entry point, preflight, manifest-scoped cleanup, staging and rollback. |
| P2 | TX reports capabilities from invalid MDIO data | On PN 2.23, reg 5 = `0xFFFF`, reg 10 = `0` displays `10/100`; reg 5 = `0x61`, reg 10 = `0xFFFF` displays `10/1000`. | Opt-in `speed-partner-validity` shows `Unknown`. |
| P2 | TX custom patches interrupt the pinned parent chain | `--with batt-grace` and `--with blind-zone-50cm` fail the scan-recovery parent hash; `--with cable-diag` fails later in the chain. | Fixed: finish the selected profile, then apply extras once in registry order. |
| P2 | Shared assembler silently emits unintended instructions | `push {r0, r0}` emits `push {r1}`; `lsrs r0, r1, #0` emits a 32-bit shift; an oversized `movw` silently truncates. Invalid layout directives can corrupt branch targets. | Fixed: reject malformed operands/layout, support explicit right shift by 32. |
| P2 | Assembler tests fail when imported by discovery | `test_thumb.py` calls `sys.exit(0)` at module scope. Its standalone success becomes an import error in `unittest discover`. | Fixed: normal `unittest` cases with a guarded entry point. |
| P2 | RX container checker accepts malformed containers | Empty or unaligned payload declarations, malformed name padding, and missing/excess page padding can pass the old reader. | Fixed: enforce the format emitted by `wrap`; structural success no longer claims payload compatibility. |
| P2 | RX release verification does not cover the current artifact format | Legacy `verify.py` models PN 1.0–1.2 and does not validate the current extended PN 1.23 update container. | Added `verify_release.py`: exact profile rebuild and complete raw/container comparison. |

## RX: gain changes must invalidate sample ownership

[`auto_range.py`](../LPM-10A/Firmware%20File/rx-sdk/auto_range.py) describes its
500 ms callback as main-context work. The call is actually reached from TIM1.
The helper changes the driven gain at `0x20000200` and the physical gain pins,
while `GATE_STATE` still marks the old acquisition valid. The normalizer reads
that driven gain. Consequently an interrupt between acquisition and publication
can change the scale of a result that was measured at a different gain.

This is reproduced on both actual analyzer paths, rather than inferred from a
Python model. The regression pauses the main analyzer at `0x0800A048`, executes
the real TIM1/AGC path with a different knob value, restores the interrupted CPU
context, and resumes analysis. The original firmware publishes a fresh signal
grade; the correction rejects that stale acquisition.

In the regression fixture, an unchanged Digital window gives a 73 ms quiet
interval at gain 7, but an interrupt changing gain to 2 just before normalization
makes that same old window publish 56 ms. The Analog example changes from 66 ms
to 42 ms. These are emulator measurements demonstrating incorrect strength
scaling, not measured acoustic timings on a device.

The same controller also measures peak-to-peak amplitude from the shared sample
buffer during mains mode. Mains uses a separate input outside the adjustable
gain stage. Its unrelated or partly cleared buffer can therefore change the
gain used when returning to cable tracing.

[`auto_range_freshness.py`](../LPM-10A/Firmware%20File/rx-sdk/auto_range_freshness.py)
invalidates the acquisition before a changed gain becomes visible, allowing the
existing publisher checks to reject it. The main-loop boundary remains
responsible for resetting indices and restarting acquisition. This avoids
resetting sampler state underneath an interrupted ADC operation. Unchanged
effective gain preserves acquisition, and mains amplitude no longer controls
the cable-tracing gain. Manual knob changes still take effect.

The correction reuses the existing 192-byte helper reservation, adds no RAM,
and does not extend the image. Tests cover manual and automatic changes,
unchanged gain, GPIO ordering, Digital and Analog publication, mains buffers,
and an interrupt during ADC sampling. They do not establish electrical settling
time or performance on a second physical unit.

`python auto_range_freshness.py` performs an in-memory dry build from the RX SDK
directory. The image is tagged `PN1.23F`, is 26,760 bytes, and has SHA-256
`0c000550e4143032070bed34ab62ff24ec18fe60d53824a81ecb3d77c4e7e8c0`.
The `build_candidate()` API returns it without writing files. The default
release profile remains PN 1.23.

## TX: distinguish unknown capabilities from advertised speeds

The SPEED row decodes every set capability bit in two cached PHY words. An
all-ones MDIO read therefore becomes an apparently capable partner. Port FLASH
already rejects that sentinel; SPEED did not. The original SPEED test even
encoded an all-ones register-10 word as an expected full-capability result.

[`speed_partner_validity.py`](../LPM-10A/Firmware%20File/sdk/speed_partner_validity.py)
intercepts the Switch-value draw call. Either ability word equal to `0xFFFF`
produces `Unknown`; valid zero words retain `No autoneg`. Valid speed lists,
the resolved speed/duplex, retry handling and `Error!!` behavior are retained.
Tests exercise the real MDIO read hook and screen rendering in English and Thai,
including stale-text clearing and recovery on the next valid result.

From the TX SDK, `python build.py --with speed-partner-validity --out candidate.bin`
is a dry build; add `--write` to emit a local candidate. The patch requires the
PN 2.23 chain and changes the About/boot marker to `PN2.23S`. Its in-memory build
is 397,312 bytes with SHA-256
`007bbeff0deeca6a7d3df63ce4732a0f03350ae01cb3e6e541b067198fcec478`.

This improves the diagnostic meaning of the row. It does not establish that a
100 Mbps negotiation on a gigabit-capable partner uniquely proves a cable fault;
the row reports the partner's advertisement, not the cause of negotiation.

## Build and release corrections

### Preserve the reproducible profile before adding experiments

[`sdk/profiles.py`](../LPM-10A/Firmware%20File/sdk/profiles.py) now validates the
whole selection before editing and orders profile patches before optional
extras. Unknown IDs and unmet dependencies fail explicitly. The actual CLI is
tested with real builds, since the previous mocked ordering tests did not catch
parent-hash failures. The `cable-diag` experiment also composes with current
`cable-values`: diagnostic rows replace the compact numeric rows instead of
drawing both formats over one another.

RX profile traversal additionally rejects unknown parents and cycles, and
checks for missing or duplicate selected registrations. Conflicting RX
`--only`/`--all` options now fail instead of silently choosing one.

### Reject ambiguous assembly

[`thumb.py`](../LPM-10A/Firmware%20File/sdk/lpm10a/thumb.py) is shared by TX and RX,
so a silent encoder mistake can affect either device. Besides the instruction
examples above, `.space -2` could make the layout pass put a label before its
actual instruction, and `.align 3` used different alignment calculations in the
layout and emission passes. Duplicate labels silently replaced prior locations.

The assembler now rejects negative reservations, non-power-of-two alignment,
duplicate labels, repeated/reversed register lists and out-of-range 16-bit
immediates. Logical left shifts accept 0–31; logical right shifts accept 1–32.
Valid instruction encodings remain unchanged. Capstone round trips independently
check encodings and branch destinations, while profile rebuilds check that the
stricter validation preserves existing firmware.

### Make publication fail before it damages the current pair

[`publish_current.py`](../LPM-10A/Firmware%20File/publish_current.py) now checks
filenames, all sources, the prior manifest and destination file types before
mutation. It stages the replacements, computes their hashes, and backs up
affected existing files. Cleanup only applies to obsolete PN releases named by
the prior manifest. Stock images and unrelated files are preserved.

Tests use temporary directories and simulate failures while replacing files and
removing obsolete releases. Ordinary I/O failures roll back the changed set.
Individual file replacements are atomic; the complete publication is not a
power-loss transaction or a multiprocess locking protocol.

### Verify the actual RX release

From `LPM-10A/Firmware File/rx-sdk`:

```powershell
python verify_release.py
python verify_release.py path/to/image.bin --profile pn1.22
```

The first command checks the shipped current update. The second accepts an
explicit historical raw image or update container. Verification rebuilds from
the pinned vendor input and compares the entire payload; containers must also
match the canonical header, internal filename and padding. A correct version
string or structurally valid container alone is insufficient.

The verified PN 1.23 raw payload SHA-256 is
`384596d75fdfc95be31984173bac5fec116083b00bec4643757a8db9b0575392`.
This checks reproducibility and integrity, not bootloader acceptance or runtime
behavior. Legacy CPU verifiers and runtime tests remain separate.

## Verification and scope

Both SDKs use a file named `profiles.py`, `build.py` and several identically named
tests. Run discovery in separate processes from the respective SDK directories:

```powershell
python -m unittest discover -p "test_*.py" -q
```

The TX baseline `python verify.py` completed with `ALL CHECKS PASSED`, including
its firmware draw-code and behavioral checks. TX profile tests rebuild the
baseline and PN 2.9–2.23 (16 images in total) against pinned digests; RX profile tests reproduce
registered archived profiles. No release binary, release manifest or vendor
input was modified during this audit.

Final TX discovery passed **288 tests in 120.571 seconds**. The initial full RX
discovery ran **417 tests in 568.351 seconds**, reporting 5 failures, 19 errors
and 1 skip. Every failure/error was in five legacy build-profile suites; no
runtime test failed. Those suites assumed that no arguments still selected the
battery-only baseline, supplied an empty mock image to a builder that now emits
containers, or expected custom patch sets to fail during argument parsing rather
than at the exact-parent check. Their fixtures and assertions were updated to
the current contract, including checking both raw/container output routing and
that incompatible real custom builds produce no files. The skipped test needs
an external device-accepted sample that is unavailable on this machine.

The final rerun combined all five repaired profile suites, the pipeline tests
and the RX candidate tests: **76 tests ran in 0.899 seconds, 75 passed and the
one optional external sample was skipped**. This rerun resolved every failure
reported by the initial full discovery. The long runtime suite was not repeated
after the test-fixture-only repairs. The gain correction's eight tests include permanent
interruptions inside the Analog DFT and on either side of the gain-normalizer
load. An independent review reproduced those rejection paths. Both shipped
root binaries still match `SHA256SUMS.txt`, and the current RX update passes the
new exact release verifier.

Coverage limitations matter: emulation replaces some hardware accesses, and
not every interrupt interleaving is exhaustively scheduled. Passing historical
tests does not prove new combinations are sound—the gain race and invalid
MDIO result were outside their coverage. New candidates require physical checks
before becoming default profiles.

## Next functional work, in order

1. **Validate gain transitions on the probe.** Capture raw amplitude, driven
   gain, accepted-window state and feedback during approach/withdrawal, knob
   changes and Digital/Analog/mains transitions. Confirm that rejecting one
   stale window improves consistency without unacceptable reacquisition delay.
2. **Validate the SPEED unknown-state candidate.** Check normal switch
   advertisements and reconnect/retry behavior on the unit. Keep hardware and
   CPU evidence recorded separately when promoting a new profile.
3. **Use exact release verification as a release gate.** Run profile rebuilds,
   candidate-specific behavioral tests, container verification and checksum
   comparison before the publisher. A structurally valid container is not a
   complete firmware check.
4. **Improve measurement evidence before changing formulas.** Existing project
   records still lack supplied-PoE validation, long-cable NVP checks and decoded
   per-pair open/short CSD status. Collect those measurements before adding
   fault-type labels or changing blind-zone thresholds. See
   [TX next steps](TX-NEXT-STEPS-2026-09-21.md).
5. **Evaluate recoverable settings storage.** The documented single-page save
   can lose calibration after a torn write. An A/B record design needs confirmed
   flash-page ownership and power-interruption tests before implementation.
6. **Evaluate new RX detection algorithms against captured data.** Compare
   acquisition delay, release delay, false acceptance and neighboring-cable
   separation. Fix sample ownership first, so gain transitions do not confound
   comparisons. See [RX next steps](RX-NEXT-STEPS-2026-09-21.md).
