# FLASH and length: deeper audit, 2026-09-19

Both functions work on their normal tested paths, but neither deserves an
unqualified "works correctly in every case." New CPU experiments reproduce
FLASH starvation on a sufficiently slow link, loss of length confidence when
only one run returns a usable value, and a stale calibration redraw. The
firmware binaries were not modified during this audit.

## Scope and reproducibility

Audited PN 2.4 and the PN 2.5 candidate from the preceding audit:

| Image | SHA-256 |
|---|---|
| PN 2.4 | `07428e667d765e25d404699ddd45021eb24dc83f45fe6144c2026a5f868f9176` |
| PN 2.5 | `ae3bb28dbdbefa03878bbe12f508b0b147ef10f1fee98870f72c41327fb2c1cf` |

The new experiments return identical results for both. PN 2.5's battery change
does not fix or introduce the findings below.

From `LPM-10A/Firmware File/sdk`:

```
python audit_flash_length.py ../LPM-10A-TX_PN2.4.bin
python audit_flash_length.py ../LPM-10A-TX_PN2.5.bin
```

The script executes the actual firmware in Unicorn, including the complete
length test sequence from `0x080119EC`: setup control flow, diagnostic polling,
reading the four simulated PHY registers, the vendor's pair filter, four-run
averaging, result storage, timeout and cancellation. It also executes the actual
conversion and `sprintf` wrapper, FLASH message handler, setup/exit paths, and
the PHY power helper. This goes beyond the existing verifier's averaging test,
which injects results **after** the vendor pair filter.

PHY responses and link acquisition times are supplied by the experiment.
RTOS scheduling, logging, GUI drawing and hardware I/O are intercepted; simulated
time advances on task delays. Thus durations for a whole length test are model
durations, not bench measurements. A state change simulates cancellation; this
does not model all key/queue interleavings. The existing full verifier passed
on both images in the preceding audit; it was not rerun unchanged here.

## FLASH

The path is screen entry (`0x08012EE4`) → network message 2 →
`LENG_link_test` (`0x0800D47C`) → active flag 2 → periodic network message 8
(`0x0801494C`) → the patched state machine. It disables 100/1000 advertisement
and uses the remaining 10 Mb/s advertisement. A port incompatible with that
advertisement cannot link; the script does not emulate Ethernet negotiation.

### F1 — Medium: the recovery timer can prevent a slow link from ever forming

In [`p_flash_blink`](../LPM-10A/Firmware%20File/sdk/patches.py), phase 3 waits for
link and repeatedly clears PHY power-down. If link is still absent when elapsed
time reaches `FLASH_RELINK_MS - FLASH_TICK_MS/2` (3750 ms), it powers down again.
With 500 ms dispatch intervals this normally occurs at 4000 ms.

The model only restarts negotiation when the PHY actually transitions from
down to up; repeated writes of power-up do not restart its timer.

| Uninterrupted power-up time needed by simulated port | Link acquisitions in 60 s | Power-downs |
|---|---:|---:|
| 0.5 s | 20 | 20 |
| 1.5 s | 15 | 15 |
| 3.5 s | 10 | 10 |
| 4.0 s | 9 | 9 |
| 4.5 s | **0** | 12 |
| 6.0 s | **0** | 12 |

The recovery loop continues running, but the port never has enough uninterrupted
time to establish a link. This disproves the general claim that every slow
switch gets a regular link blink. It does not establish that the user's switch
needs 4.5 s; the repository records PN 2.4 working on the tested unit/switch.

Suggested improvement: increase the negotiation window after repeated failures,
retain recovery retries, and show a waiting/no-link indication. Validate with
both a fast port and a port with a deliberately delayed link.

### F2 — Low: the advertised hold/off durations are nominal

The actual comparison thresholds are 1250 ms on and 750 ms off, because both
configured durations have half a tick subtracted. Injecting handler times
`0, 500, 1000, 1500, 1750, 2500` ms, with link first seen at 500 ms, produces:

```
link seen       500 ms
power down     1750 ms   -> held for 1250 ms after observation
power up       2500 ms   -> down for 750 ms
```

This schedule represents delayed/bunched dispatch. With regular 500 ms messages,
the intended 1500/1000 ms phases work. Messages processed repeatedly at one
timestamp cannot advance the elapsed-time test, but that narrower property
does not prove that all queue jitter preserves the configured durations.

Suggested improvement: use the full elapsed-time thresholds if the values are
intended as minimum durations, or document the early threshold explicitly.

### Confirmed working in the model

- Normal setup reaches active flag 2 and phase 0 with the PHY powered up.
- Normal exit clears the phase and active flag, returns Home and powers down.
- A queued blink message after stop does not call the PHY.
- Elapsed-time subtraction works across the 32-bit tick rollover.
- The actual power helper changes BMCR bit `0x0800` while preserving the other
  bits in the supplied register value: `0x1940 → 0x1140` for up and `0x1940` for down.
- The earlier verifier covers holding Auto Off during an active FLASH session.

## Length

The actual data path is:

```
PHY per-pair cm -> <=200 cm becomes zero -> vendor cross-pair filter
-> four-run nonzero-only average -> stored cm -> Zero/NVP -> m/cm/ft -> text
```

### L1 — Medium: one successful run is displayed without its low confidence

The averaging hook counts nonzero values independently for each pair. It
accepts any count from one to four, with no display of the count or stability.

Input to the complete sequence:

```
run 1:  [5000, 5000, 5000, 5000] cm
runs 2–4: [0, 0, 0, 0] cm
```

Output: `[5000, 5000, 5000, 5000]`, flag 2 (normal result). Thus a test whose
later runs all return no usable length can still finish with an ordinary 50 m
reading. This models removal/intermittent loss during acquisition; the exact
PHY response to physical removal still needs a cable test.

This is consistent with the implemented averaging policy, but the UI does not
distinguish one retained reading from four stable readings. Suggested improvement:
track/show valid-run counts or mark a result incomplete below a chosen minimum,
and do not present an entirely lost final connection as a fresh stable measurement.

### L2 — Medium limitation: the four displayed pairs are not independent measurements

The vendor filter before averaging merges pairs that fall inside its tolerance
band. The complete sequence confirms:

| Simulated raw values on each of four runs | Stored result |
|---|---|
| 50 / 50 / 50 / 48 m | **49.5 / 49.5 / 49.5 / 49.5 m** |
| 50 / 50 / 50 / 10 m | 50 / 50 / 50 / 10 m |

Near 50 m the filter's tolerance is 3 m. Smoothing can be useful for whole-cable
estimation, but it can conceal a real shorter pair within that band. Four-run
averaging does not restore information already removed by this filter. The
first row is reproducible on stock-derived PN 2.4 and PN 2.5, not a new PN 2.5
regression.

Suggested improvement: preserve each pair's readings and apply temporal filtering
per pair, or provide a raw/per-pair diagnostic view. This changes measurement
policy and needs known-good and deliberately damaged cables for validation.

### L3 — Medium display bug: a queued calibration update can draw onto another screen

`p_nvp`'s GUI message `0x3D` unconditionally calls `nvp_draw`, then
`length_result_draw`. Only the latter checks that the current screen is Length.
Executing the actual message-routing hook with current state Home produces:

```
NVP 69%
ZERO 0.0m
```

Therefore a calibration message queued before leaving Length can paint those
labels onto Home if it is serviced after the Home redraw. The stale-handler
behavior is CPU-reproduced; occurrence frequency under the real scheduler is
unknown. Suggested improvement: guard the entire `0x3D` handler with the current
screen state before either draw call.

### L4 — Robustness defect: invalid large inputs are accepted and cm can wrap

Injecting `0xFFFF` for every pair produces a normal stored result of 65535 cm.
The existing upper-limit test in `length_result_draw` is ineffective: the
comparison with 60000 is reached only when the converted value is already zero.

The conversion routine also truncates its return value to 16 bits. With NVP 99%,
Zero 0, raw 45677 cm becomes 65537 calibrated cm, then **1 cm** after truncation.
The same input displays 655.4 m in metre mode, so the units disagree.

This lies outside the 0–30000 cm arithmetic grid checked below. It is a malformed
or out-of-range input defect, not evidence of an error measuring an ordinary
short cable. This audit does not assume that `0xFFFF` is an officially specified
PHY fault sentinel. Suggested improvement: validate raw results against supported
measurement limits/status before averaging, and reject or saturate arithmetic
that cannot fit the display representation.

### Confirmed working in the model

- **7,776 conversion cases matched** independent integer formulas, sampling raw
  values through 30000 cm, all NVP settings 50–99 plus invalid/default bytes,
  Zero 0/0.4/2.0 m plus an invalid byte, and all three units.
- Actual `sprintf`, Zero 0.4 m / NVP 68%: raw 334 cm prints 2.9 m, 290 cm,
  9.5 ft; raw 1470 cm prints 14.1 m, 1409 cm, 46.2 ft.
- Four successful runs execute and reach normal result storage. Entirely zero
  runs remain zero. Large per-pair differences survive the vendor filter.
- Raw 199/200/201/220 cm becomes 0/0/210/210 cm after thresholding and filtering.
  This shows the threshold and smoothing; it does not prove physical accuracy
  near the PHY's blind zone. `< 2 m` means the firmware retained no usable length,
  not a separately validated fault-distance measurement.
- A continuously busy diagnostic times out, sets flag 3, and powers the PHY down.
- A simulated leave-screen event while polling cancels the test and powers down.
- Four simulated 19 s diagnostics finish successfully with the timeout renewed
  per run, including across tick rollover. The model totals 76.4 s; real I/O and
  scheduling costs are not represented.

## Practical verdict and priorities

Normal port identification on the previously tested switch and calibrated
whole-cable length estimation have supporting evidence. Universal switch
compatibility, independent per-pair fault distance, and confidence after
intermittent readings do not.

Prioritise the adaptive link wait and length confidence handling, then the
stale redraw guard and invalid-input rejection. Evaluate changes to cross-pair
smoothing separately with hardware measurements. The existing interrupt-context
queue calls remain a shared reliability risk beyond these isolated experiments.

No firmware changes, rebuild, flashing or release publication were performed
in this deeper audit. The only additions are this report and the diagnostic script.
