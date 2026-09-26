# RX PN1.31 — robust Digital ranking and reliable feedback handoff

This prerelease fixes two reproducible PN1.30 defects: sparse ADC impulses could make a weak Digital tone sound stronger than a clean stronger tone, and a timer interrupt could change gain before the first valid frame reached sound publication.

**Validation: ARM CPU emulation and reproducible builds. Physical PN1.31 testing is pending.** The owner will test both units after publication; no new range, acoustic loudness, or physical selectivity claim is made.

Install **`APP_LPM-10RX_PN1.31-resilient-update.bin`** on the RX probe. The raw `.bin` is included for analysis and must not be copied to the update drive.

- Digital strength keeps PN1.30's chip-edge compensation, but uses all eleven/twelve triplets from a verified 48-sample phase fit. Two impulses no longer turn a 100-count weak tone into a 600-count estimate. The exact-only fallback still uses only its verified 16-sample span.
- Fast gain becomes eligible only when the analyzed frame has successfully committed its sound state. The existing stale-sample, gate, mode, and gain guards remain active. The fix adds four instructions to the existing publication critical section.
- Ten strength levels, knob law, tone pitches, gain thresholds, Analog detection, NCV, and the sampler stay as PN1.30. No new persistent RAM is used. The raw image grows by 200 bytes; the update container crosses a 4 KB padding boundary and is 36,864 bytes.
- Validation tools now reject silent targets as successful cable identification and use the observed 30 ms Analog speaker pulse in their score calculations. These are test-tool corrections, not firmware sensitivity changes.

The original misranking now produces score 2,144 for the noisy weak tone versus 3,222 for the clean stronger tone. All 960 seeded/swept impulse vectors retain the correct strength. The steady-signal cases hold one level with min/median score 1.0, and the modeled 6 dB drop reaches its new level in 571 ms. Final detection policy is unchanged over 1,125 weak/noise/code/rail vectors and 7,200 fragment/tail vectors. Timing figures describe the modeled input, not measured pickup.

The full RX run completed 709 tests and found only outdated PN1.30-default test expectations; those were corrected and all 16 profile/integrity tests passed on rerun. The final image also passed 43 focused release/regression tests and the paired/scorecard checks. The full run was not repeated after the test-only correction; one optional external container fixture was absent. The report below records the exact coverage and the unchanged verdicts in all 48 final-image cabinet cases.

The longer verified span can smooth changes within a frame; it is not a new minimum contact time. First-contact acquisition and detection thresholds are unchanged. See the [implementation and validation report](https://github.com/patnawa/LPM-10A_PN_Custom/blob/rx-v1.31/docs/RX-TX-RESILIENT-2026-09-26.md) for the full test results and tradeoffs.

Installation: probe off, hold **SCAN**, connect USB, copy the **`-update.bin`** with Explorer onto `BOOTLOADER`. Wait for the drive to disappear, unplug, then power on. Re-entering update mode without copying should show `PN1.31.TXT`.

Device check: compare with PN1.30 on the same cable, test repeated brief contacts and continuous strong contact, turn the knob through Locate/Isolate/off, move between a toned pair and neighbors, remove the tone, and test Analog/NCV plus mode-change chirps. Report any delayed sound, dropouts, wrong ranking, flicker, or failure to boot. This release can pair with TX PN2.33 or PN2.34.

Rollback: install the [owner-tested PN1.30 update](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/rx-v1.30) with the same procedure. Its bytes and build profile remain unchanged.

SHA-256 update: `a6352ab9d604874511d835294d8d50fdd105049905b488e1aa263f13ce87126a`

SHA-256 raw: `3e03d8ac13884a0fb3ad752b551ad346eb8e77e11998d7be9ca599923752094c`
