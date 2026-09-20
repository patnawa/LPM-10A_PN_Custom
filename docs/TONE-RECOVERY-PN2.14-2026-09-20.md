# TX PN 2.14: retain Digital and Analog

At the owner's request, PN 2.14 has only **Digital 454 kHz** and
**Analog 825 Hz** in its tone menu. Sync32 and Pulse test are removed. This
candidate retains the established signal generation, updates the two labels,
button width and displayed version, and fixes a RIGHT-key carrier-cache defect
found during the [detailed performance audit](TONE-PERFORMANCE-AUDIT-2026-09-20.md).

Download [LPM-10A-TX_PN2.14-tone-recovery.bin](../LPM-10A/Firmware%20File/experimental/LPM-10A-TX_PN2.14-tone-recovery.bin).
The [checksum](../LPM-10A/Firmware%20File/experimental/TONE-RECOVERY-SHA256SUMS.txt)
and [device notes](../LPM-10A/Firmware%20File/experimental/TONE-RECOVERY-PN2.14-README.txt)
identify this exact candidate. The filename describes returning to the two
established tone modes; it is not a bootloader recovery image.

Size: 393,216 bytes. SHA-256:
`a7402de6f18e39df55bbe53f5641efd5135f0de4d81f9407515cf9d8710c5527`.

<img src="img/scan-pn214-en.png" alt="PN 2.14 English tone menu" width="240"> <img src="img/scan-pn214-th.png" alt="PN 2.14 Thai tone menu" width="240">

## Device feedback and decision

The owner reports that Digital and Analog work with TX PN 2.13 / RX PN 1.10,
but Sync32 remains silent even when RX is in digital mode. No oscilloscope is
available. That device result takes precedence over the earlier passing CPU
and ideal-envelope tests.

Pulse test was a continuous-carrier burst of approximately 100 ms followed by
400 ms off. It contains neither supported digital code nor the 825 Hz analog
modulation. The actual RX digital and analog analyzers reject the modeled
waveform, so receiver silence in that mode was expected. Presenting it alongside
ordinary tracing modes was confusing.

No cause of the physical Sync32 failure has been established. New tests execute
the actual TX carrier/GPIO configuration and the actual RX interrupt sequence;
both still work with a modeled envelope. They do not prove the real analog
signal, receiver response, or oscillator relationship. This release removes
the unnecessary modes rather than claiming to repair or validate Sync32.

## What remains available

| TX label | Nominal signal | RX setting |
|---|---|---|
| Digital 454 kHz | Established B6 code, 50 TIM2 ticks per chip, on the approximately 454 kHz carrier | Digital |
| Analog 825 Hz | Established approximately 825 Hz modulation of the same carrier | Analog |

Digital displays the carrier frequency; Analog displays the modulation rate.
Neither label specifies the receiver's synthesized feedback-beep frequency.
The [Thai explanation](../README.md#tone-probe-frequencies) remains in README.

The existing mode key cycles Digital -> Analog -> Digital. Back pauses, resume
restores the signal, and a second Back while paused exits as before. Both UI
languages use the requested technical frequency labels. The rounded buttons
are widened to fit the longer text.

The installed **RX PN 1.10 can continue to be used**. Its legacy Digital/Analog
paths are retained and the owner reports them working. No receiver firmware
change is required to remove these TX menu options. The RX robust strength
feedback from PN 1.9 remains available through PN 1.10.

## Firmware scope

`sdk/scan_recovery.py` starts from the exact finalized PN 2.12 image, SHA-256
`3d2db80f8288744191fe1ddb2855a83b900166dd365e1583c6270dfb460a0076`.
It does not apply the PN 2.13 extension and does not allocate new RAM.
The UI patch changes two label blocks and the pointer to a wider copy of the
button descriptor. Both version fields become `PN 2.14`.

The RIGHT-key call at `0x08014480` now uses a 28-byte wrapper that preserves
the original GPIO operation and interrupt mask, then atomically invalidates
the cached carrier state. Previously, that operation could change PA8 while
the cache still said HIGH, delaying restoration for up to 100 subsequent
ticks in the Digital fixture (nominally 10.1 ms). The next timer request now
restores the appropriate state. This is not a proven cause of the Sync32 failure.

The Digital and Analog generators, dispatcher, enable/pause/resume handlers,
mode key, timer setup, carrier-gate routine, and underlying GPIO routines remain
byte-identical to PN 2.12. Waveform timing and output-drive settings are preserved;
the RIGHT-key cache repair is the only control-flow change outside the UI.
No increased output power or measured superiority in cable bundles is claimed.

The original PN 2.12 and PN 2.13 binaries are preserved for comparison. Earlier
default/named build profiles remain separate, and the two alternative SCAN
patches cannot be selected together.

## Verification

The final TX run passes **60 test groups**, including eleven recovery-specific
groups, profile isolation, prior PN 2.12 regressions and five actual-GPIO groups.
Five RX paired/acquisition groups also pass. This new TX binary matches a
separate fixture rebuild byte-for-byte.

The recovery tests compare all changed bytes to the declared UI/version and
RIGHT-key hook sites,
check unchanged RAM allocations and container size, run the original waveform
and key regressions, and inspect both languages and both selected/paused states.
The screen is also rendered for visual inspection. The RIGHT-key tests cover
800 Digital cursor phases and 12 Analog phases, interrupt-mask preservation,
unmasked instruction boundaries, and paused/resumed operation.

`test_scan_hardware.py` additionally executes carrier initialization and the
actual GPIO routines of the preserved PN 2.13 trial instead of stubbing the
carrier gate. In every tested mode, ON selects alternate-function push-pull
on PA8/PB13, and OFF restores GPIO output. TIM1 retains ARR 316, CCR1 158,
enabled outputs and its main-output enable. This is register-level emulation,
not a measurement of an electrical carrier.

`rx-sdk/test_scan_acquisition_timing.py` pins RX PN 1.10 and executes 38,440
actual TIM5 IRQ calls for fresh and rearmed windows, checking 960 ADC reads.
It also verifies rejection of Pulse test in 512 digital phases and 43 analog
windows. Fresh startup has its first five reads at ticks 140/160/180/200/220;
immediate rearm uses relative ticks 120/140/160/180/200. The paired test now
uses the fresh-start aperture, while the independent model distinguishes both.
This timing-origin correction is not a demonstrated cause or fix of the
hardware silence.

After the latest RX PN 1.12 / TX PN 2.14 test request, the owner reports both
Digital/Analog receive and sweeping is more accurate. The owner confirms
RX PN 1.12 / TX PN 2.14. Later feedback identifies an open Digital release issue:
sound continues about one second after moving away or pressing TX Pause;
Analog has no such delay. See
[scoped owner feedback](TONE-DEVICE-FEEDBACK-2026-09-20.md).
The owner subsequently reports other tested functions also passed, without an
itemized list or waveform measurements. The specific electrical RIGHT-key
repair is therefore not separately measured. The earlier PN 2.13 observation
remains historical evidence.

## Reproduce

In `LPM-10A/Firmware File/sdk`:

```text
python build.py --scan-recovery --write
python -m unittest test_scan_recovery test_recovery_profile test_sync_profile test_portflash_status test_scan_hardware -q
```

In `LPM-10A/Firmware File/rx-sdk`, using the preserved trial artifacts:

```text
python -m unittest test_scan_pair test_scan_acquisition_timing -q
```

The earlier trial and hardware failure remain documented in the
[PN 2.13 / PN 1.10 report](SCAN-SYNC-PN2.13-PN1.10-2026-09-20.md).
