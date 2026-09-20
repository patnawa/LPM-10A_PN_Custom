# Acoustic measurements of the owner clip, 2026-09-20

The recording contains repeated short main-tone pulses after each of three
audible change events. It does **not** contain a single uninterrupted one-second
main-tone pulse at those endings. Audio alone does not identify which device was
operated, which binary is installed, or the firmware cause.

Source: `C:\Users\Alpha\Desktop\5da1ebc8-1c14-45a7-ae03-b1cc9fb00ba2.mp4`

SHA-256: `c2f0006778004c8cc0f07197dbe5af3b6631460a7d2012dd2c2a41c246824925`

The MP4 is 15.876667 s. AAC audio is 48 kHz stereo and starts at **0.026 s**
on the video timeline. All timestamps below include that offset.

The source recording, decoded WAV and extracted PNG frames are retained locally
and excluded from the public snapshot. Numerical results and analysis code remain
available for review.

## Frequency and pulse timing

- Main tone: approximately **2516 Hz** (whole-clip interpolated spectral peak
  2515.858 Hz). The main tone frequency is close to the nominal 2.5 kHz audio
  oscillator; it is not ten times slower. This is the sound frequency, not the
  transmitted 454 kHz carrier or the analog modulation rate.
- A separate tone near **2971 Hz** occurs in five acoustic chirps of about
  **104–106 ms**: 1.548–1.654, 3.998–4.102, 8.278–8.382,
  11.006–11.112 and 14.528–14.632 s. Their device identity requires video
  alignment; it is not inferred here.
- During the final main-tone tail, eight acoustic rise/fall transition pairs
  have separations **48.458–49.458 ms**, median **49.104 ms**. Pulse onsets
  recur approximately every **98 ms**. Lower-level room/microphone decay follows
  the large falling edge, so a simple low-amplitude threshold gives longer
  intervals than these transition pairs.
- A second method, autocorrelation of the derivative of the complex-demodulated
  carrier, finds the strongest opposite-sign transition at **50.0, 49.5 and
  49.0 ms** in the three ending sections. A 30 ms lag does not produce the
  corresponding strong opposite-sign transition.

These acoustic transitions are consistent with roughly **50 ms gating**, rather
than 30 ms gating with its decay counted as an uninterrupted one-second pulse.
They are not a direct electrical measurement and cannot establish a firmware
revision. No timer constant should be changed solely to force the model to match
these measurements.

## Three activity endings

The final strong main-tone falling edges occur at:

| Main-tone section | Last pulse rising edge | Last pulse falling edge | Preceding 2971 Hz chirp onset | Interval from chirp onset to last main-tone fall |
| --- | ---: | ---: | ---: | ---: |
| First | 2.221 s | 2.270 s | 1.548 s | 0.722 s |
| Second | 9.138 s | 9.186 s | 8.278 s | 0.908 s |
| Third | 15.336 s | 15.385 s | 14.528 s | 0.857 s |

The interval column uses an **acoustic landmark**, not an assumed button, UI or
electrical mode-change timestamp. The main-tone pulse train continues after the
separate chirp. Acoustic decay remains below the major plateau after each listed
falling edge. Low thresholds also detect small noises; for example the first
section's 0.001 RMS group closes only at 2.382 s, so this should not be mistaken
for a precisely measured electrical release time.

Final-section transition pairs, in seconds:

```text
rise        fall        separation
14.648792   14.697250    48.458 ms
14.746458   14.795917    49.458 ms
14.844771   14.894083    49.312 ms
14.942792   14.991875    49.083 ms
15.041271   15.090396    49.125 ms
15.139542   15.188854    49.312 ms
15.238229   15.287208    48.979 ms
15.336333   15.385000    48.667 ms
```

## Reproduction and limits

Run from the repository root:

```powershell
python docs/experiments/results/clip-5da1ebc8/audio_audit.py
```

The script also accepts a replacement source path as its first argument. It
requires ffmpeg/ffprobe, NumPy and SciPy. It regenerates:

- `audio_audit_decoded.wav`: uncompressed decoded recording.
- `audio_audit_probe.json`: source/container metadata.
- `audio_audit_results.json`: complete thresholds, measurements, versions and
  limitations.
- `audio_audit_envelopes.csv`: 2 ms RMS bins for the two separate frequency bands.
- `audio_audit_envelopes.svg`: full recording and all three ending sections.

The transition method mixes the audio with 2515.3 Hz, applies a zero-phase 400 Hz
low-pass filter, and smooths its magnitude at 150 Hz. It pairs the largest rising
slope near each automatically thresholded pulse with the largest falling slope
25–70 ms later. This search range includes both 30 ms and 50 ms hypotheses. The
independent derivative autocorrelation searches the same 25–70 ms range.

AAC compression, microphone processing, automatic gain and acoustic reflections
affect the waveform. Numerical timestamps retain precision for reproducibility,
not a claim of microsecond accuracy. Video event alignment is limited by its
approximately 33 ms frame spacing. The approximately 50 ms repeated transitions
are stronger evidence than their exact decimal values.

## Alignment with independently inspected video

The parent visual audit identifies **TX selected-mode changes Digital → Analog**
in the brackets below. It does not identify a TX Pause or an RX keypress in this
clip. Applying those visual brackets to the independently measured last main-tone
falling edges gives:

| Digital → Analog selected-mode transition | Last large main-tone falling edge | Interval after visible selected-mode transition |
| --- | ---: | ---: |
| 1.400–1.466 s | 2.270 s | **0.804–0.870 s** |
| 8.165–8.199 s | 9.186 s | **0.987–1.021 s** |
| 14.364–14.398 s | 15.385 s | **0.987–1.021 s** |

This confirms the approximately one-second **train of pulses** after the visible
TX change. It does not establish that a single RX sound counter remains active
for that whole interval. Small acoustic decay follows the last large falling
edge. The UI may change before the TX output changes electrically, so these are
UI-to-sound intervals rather than measured TX-output-to-RX-stop latencies.

The main tone resumes around 4.29 s and 11.21 s. These are acoustic observations
without a confirmed UI transition bracket. The 11.172 s low-threshold group start
includes small pre-onset noise and should not replace the approximately 11.21 s
strong onset. The recording does not authenticate the installed firmware revision.
