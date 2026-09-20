"""Reproduce acoustic measurements of the owner's 2026-09-20 clip.

Requires ffmpeg/ffprobe on PATH, NumPy and SciPy. No firmware interpretation
or visual event times are assumed. Times are aligned to the MP4 timeline.
Run: python docs/experiments/results/clip-5da1ebc8/audio_audit.py
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import platform
import subprocess

import numpy as np
import scipy
from scipy.io import wavfile
from scipy.signal import butter, correlate, sosfiltfilt, welch


def intervals(mask: np.ndarray, width_s: float, offset_s: float,
              close_gap_s: float = 0, minimum_s: float = 0):
    mask = mask.copy()
    bounds = np.flatnonzero(np.diff(np.r_[False, ~mask, False])).reshape(-1, 2)
    for begin, end in bounds:
        if begin > 0 and end < len(mask) and (end - begin) * width_s <= close_gap_s:
            mask[begin:end] = True
    bounds = np.flatnonzero(np.diff(np.r_[False, mask, False])).reshape(-1, 2)
    return [{"start_s": round(begin * width_s + offset_s, 6),
             "end_s": round(end * width_s + offset_s, 6),
             "duration_s": round((end - begin) * width_s, 6)}
            for begin, end in bounds if (end - begin) * width_s >= minimum_s]


def peak_hz(x: np.ndarray, fs: int, lo: float, hi: float):
    f, p = welch(x, fs, nperseg=min(fs, len(x)), nfft=fs)
    candidates = np.flatnonzero((f >= lo) & (f <= hi))
    k = candidates[np.argmax(p[candidates])]
    # Quadratic interpolation in log power; still limited by source duration.
    a, b, c = np.log(np.maximum(p[k - 1:k + 2], np.finfo(float).tiny))
    delta = 0.5 * (a - c) / (a - 2 * b + c)
    return round(float(f[k] + delta * (f[1] - f[0])), 3)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", default=str(
        Path.home() / "Desktop/5da1ebc8-1c14-45a7-ae03-b1cc9fb00ba2.mp4"))
    args = parser.parse_args()
    source = Path(args.source).resolve()
    out = Path(__file__).resolve().parent
    probe = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(source)
    ], text=True))
    stream = next(s for s in probe["streams"] if s["codec_type"] == "audio")
    offset = float(stream["start_time"])
    decoded = out / "audio_audit_decoded.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(source),
                    "-map", "0:a:0", "-c:a", "pcm_s16le", str(decoded)], check=True)
    fs, pcm = wavfile.read(decoded)
    x = pcm.astype(np.float64).mean(axis=1) / 32768
    bin_samples = int(round(fs * .002))
    width = bin_samples / fs
    bins = len(x) // bin_samples
    times = offset + (np.arange(bins) + .5) * width
    envelopes = {}
    for name, band in [("main_2300_2700_hz", [2300, 2700]),
                       ("chirp_2880_3060_hz", [2880, 3060])]:
        filtered = sosfiltfilt(butter(4, band, btype="bandpass", fs=fs, output="sos"), x)
        envelopes[name] = np.sqrt(np.mean(filtered[:bins * bin_samples].reshape(-1, bin_samples)**2, axis=1))
    main_env, chirp_env = envelopes.values()
    # Absolute acoustic thresholds are explicit, not undocumented auto-tuning.
    groups = intervals(main_env > .001, width, offset, close_gap_s=.030, minimum_s=.200)
    pulses = intervals(main_env > .005, width, offset, close_gap_s=.014, minimum_s=.020)
    chirps = intervals(chirp_env > .0018, width, offset, close_gap_s=.010, minimum_s=.040)
    for group in groups:
        a = max(0, int((group["start_s"] - offset) * fs))
        b = min(len(x), int((group["end_s"] - offset) * fs))
        group["dominant_hz"] = peak_hz(x[a:b], fs, 2400, 2600)
    for chirp in chirps:
        a = max(0, int((chirp["start_s"] - offset) * fs))
        b = min(len(x), int((chirp["end_s"] - offset) * fs))
        chirp["dominant_hz"] = peak_hz(x[a:b], fs, 2900, 3050)

    final_pulses = [p for p in pulses if 14.64 <= p["start_s"] <= 15.40]
    onset_diffs = np.diff([p["start_s"] for p in final_pulses])
    # Separate gating transitions from the lower-level acoustic decay. A
    # complex-demodulated envelope contains onset and offset transients;
    # compare their largest rising/falling slopes instead of counting all
    # audible reverberation as electrical ON time.
    demod_hz = 2515.3
    demod = sosfiltfilt(butter(4, 400, btype="lowpass", fs=fs, output="sos"),
                       x * np.exp(-2j * np.pi * demod_hz * np.arange(len(x)) / fs))
    smooth_amplitude = sosfiltfilt(butter(3, 150, btype="lowpass", fs=fs, output="sos"), abs(demod))
    slope = np.diff(smooth_amplitude)
    def edge_pair(pulse):
        onset = pulse["start_s"]
        a = int((onset - .006 - offset) * fs)
        b = int((onset + .020 - offset) * fs)
        rise = a + np.argmax(slope[a:b])
        # Both 30 and 50 ms candidate durations are inside the search range.
        a = rise + int(.025 * fs)
        b = rise + int(.070 * fs)
        fall = a + np.argmin(slope[a:b])
        return {"rise_video_s": round(float(rise/fs + offset), 6),
                "fall_video_s": round(float(fall/fs + offset), 6),
                "edge_separation_ms": round(float((fall-rise)/fs*1000), 3)}
    edge_pairs = [edge_pair(pulse) for pulse in final_pulses]
    last_pulse_each_group = [edge_pair([p for p in pulses if g["start_s"] <= p["start_s"] < g["end_s"]][-1]) for g in groups]
    # Independent manual frame inspection supplied by the parent visual audit;
    # these are selected-mode changes, not Pause or RX keypress observations.
    digital_to_analog_brackets = [(1.400, 1.466), (8.165, 8.199), (14.364, 14.398)]
    visual_aligned_tails = []
    for bounds, last_pulse in zip(digital_to_analog_brackets, last_pulse_each_group):
        end = last_pulse["fall_video_s"]
        visual_aligned_tails.append({
            "event": "TX selected mode Digital to Analog",
            "visual_transition_bracket_video_s": list(bounds),
            "last_large_acoustic_falling_edge_video_s": end,
            "ui_to_last_large_falling_edge_range_s": [round(end-bounds[1], 6), round(end-bounds[0], 6)]})
    ac_results = []
    for begin, end in [(1.71, 2.30), (8.43, 9.22), (14.64, 15.43)]:
        a, b = int((begin-offset)*fs), int((end-offset)*fs)
        # 0.5 ms sample interval for the correlation. Record the complete
        # 25–70 ms search rather than selecting the desired lag by eye.
        derivative = np.diff(demod[a:b:24])
        ac = correlate(derivative, derivative, mode="full", method="fft").real[len(derivative)-1:]
        ac /= ac[0]
        k = 50 + np.argmin(ac[50:141])
        ac_results.append({"video_interval_s": [begin, end],
                           "most_negative_lag_25_70_ms": round(float(k*.5), 3),
                           "normalized_correlation_at_minimum": round(float(ac[k]), 6),
                           "normalized_correlation_at_30_ms": round(float(ac[60]), 6),
                           "normalized_correlation_at_49_ms": round(float(ac[98]), 6)})
    result = {
        "source_path": str(source),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "source_bytes": source.stat().st_size,
        "duration_s": float(probe["format"]["duration"]),
        "audio_offset_video_s": offset,
        "sample_rate_hz": fs,
        "channels": int(stream["channels"]),
        "decoded_samples": len(x),
        "software": {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__},
        "analysis": {"rms_bin_s": width, "filter": "zero-phase fourth-order Butterworth bandpass",
                     "group_threshold_rms": .001, "group_close_gap_s": .030,
                     "pulse_threshold_rms": .005, "pulse_close_gap_s": .014,
                     "chirp_threshold_rms": .0018, "chirp_close_gap_s": .010},
        "dominant_main_hz": peak_hz(x, fs, 2400, 2600),
        "dominant_third_harmonic_hz": peak_hz(x, fs, 7400, 7650),
        "main_activity_groups": groups,
        "distinct_frequency_chirps": chirps,
        "strong_envelope_intervals": pulses,
        "final_train_onset_intervals_s": [round(float(t), 6) for t in onset_diffs],
        "final_train_median_onset_interval_s": float(np.median(onset_diffs)),
        "manual_visual_alignment": {
            "provenance": "Parent agent independently inspected MP4 frames and supplied transition brackets; audio analysis does not infer actions.",
            "digital_to_analog_tails": visual_aligned_tails,
            "scope": "Visible TX mode changes only; no TX Pause or RX keypress is established by this clip. The UI change may precede the electrical TX mode change."
        },
        "gating_transition_analysis": {
            "method": "Complex demodulation at 2515.3 Hz; zero-phase 400 Hz fourth-order LPF; amplitude 150 Hz third-order LPF. Largest rising slope within -6/+20 ms of threshold onset; largest falling slope 25–70 ms later.",
            "final_train_edge_pairs": edge_pairs,
            "last_pulse_each_activity_group": last_pulse_each_group,
            "median_edge_separation_ms": float(np.median([p["edge_separation_ms"] for p in edge_pairs])),
            "independent_complex_derivative_autocorrelations": ac_results,
            "interpretation": "Acoustic transitions are consistent with approximately 49–50 ms gating, followed by reverberation. They do not support a continuous 1 s pulse or a tenfold slower speaker oscillator. This is not an electrical measurement and cannot identify the installed binary."
        },
        "limits": [
            "Only acoustic observations; no action or device identification is inferred from audio alone.",
            "AAC compression, microphone processing, room reverberation and automatic gain affect acoustic envelope durations.",
            "Threshold intervals are not exact electrical speaker-on times or MCU counter measurements.",
            "2 ms RMS bins do not imply 2 ms action/video precision; video frames are approximately 33 ms apart.",
            "Audio-only evidence cannot establish firmware revision, internal code path or physical cause.",
        ],
    }
    (out / "audio_audit_results.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    (out / "audio_audit_probe.json").write_text(json.dumps(probe, indent=2) + "\n", encoding="utf-8")
    with (out / "audio_audit_envelopes.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["video_time_s", *envelopes])
        writer.writerows((f"{t:.6f}", f"{a:.9f}", f"{b:.9f}") for t, a, b in zip(times, main_env, chirp_env))

    svg = ['<svg xmlns="http://www.w3.org/2000/svg" width="1500" height="1160" viewBox="0 0 1500 1160">',
           '<rect width="1500" height="1160" fill="white"/>',
           '<style>text{font-family:Arial,sans-serif;fill:#17202a;font-size:16px}.grid{stroke:#d5dce3;stroke-width:1}</style>',
           '<text x="80" y="30" font-size="23">Owner clip acoustic envelope: all timestamps aligned to video</text>',
           '<text x="80" y="55">Blue: 2300–2700 Hz (main 2516 Hz tone); orange: 2880–3060 Hz (2971 Hz chirps)</text>',
           '<text x="80" y="80">Band RMS / full scale. Acoustic envelope includes reverberation; pulses are not continuous one-second tones.</text>']
    panels = [(0, 15.9, "Entire clip"), (1.35, 2.45, "First activity ending"),
              (8.15, 9.4, "Second activity ending"), (14.4, 15.6, "Third activity ending")]
    for i, (start, end, title) in enumerate(panels):
        top, height, left, width_px = 130 + 255*i, 180, 80, 1360
        svg.append(f'<text x="80" y="{top-15}">{title}</text>')
        for value in [0, .01, .02, .03]:
            yy = top + height * (1 - value/.035)
            svg.append(f'<line class="grid" x1="{left}" x2="{left+width_px}" y1="{yy}" y2="{yy}"/>')
            svg.append(f'<text x="22" y="{yy+5}">{value:.2f}</text>')
        for t in np.linspace(start, end, 9):
            xx = left + (t-start)/(end-start)*width_px
            svg.append(f'<line class="grid" x1="{xx}" x2="{xx}" y1="{top}" y2="{top+height}"/>')
            svg.append(f'<text x="{xx-20}" y="{top+height+25}">{t:.2f}</text>')
        for env, color in [(main_env, "#1261a0"), (chirp_env, "#c76609")]:
            selected = np.flatnonzero((times >= start) & (times <= end))
            points = ' '.join(f'{left+(times[k]-start)/(end-start)*width_px:.2f},{top+height*(1-min(env[k],.035)/.035):.2f}' for k in selected)
            svg.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="1.5"/>')
    svg.append('</svg>')
    (out / "audio_audit_envelopes.svg").write_text('\n'.join(svg), encoding='utf-8')
    print(json.dumps({k: result[k] for k in ["source_sha256", "dominant_main_hz", "main_activity_groups", "distinct_frequency_chirps", "final_train_median_onset_interval_s", "gating_transition_analysis"]}, indent=2))


if __name__ == "__main__":
    main()
