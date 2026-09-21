"""Digital matched-filter model, evaluated on the 2026-09-21 live RAM captures.

For every captured 48-sample Digital window: correlate the mean-removed samples
with the +-1 pattern of the repeated 16-chip code at all 16 phases, take the
best |S|, and compare it with the other phases (margin).  Windows the PN detector
accepted (RECENT refreshed) versus windows with no signal (gate open, RECENT 0,
tiny peak-to-peak) show how well a margin threshold separates them.

    python rx_matched_filter_model.py  Desktop/LPM-10RX-SWD-2026-09-21/sens-*digital*.jsonl ...
"""
import glob
import json
import statistics as st
import sys

CODE_HEX = 0xB6B6
CHIPS = [1 if (CODE_HEX >> (15 - i)) & 1 else -1 for i in range(16)]


def correlate(samples):
    n = len(samples)
    mean = sum(samples) / n
    x = [s - mean for s in samples]
    scores = []
    for phase in range(16):
        s = sum(x[i] * CHIPS[(i + phase) % 16] for i in range(n))
        scores.append(abs(s))
    best = max(scores)
    others = sorted(scores)[:-1]
    ref = st.median(others) if others else 1.0
    return best, best / max(ref, 1.0), scores.index(best)


def load(paths):
    rows = []
    for p in paths:
        for line in open(p):
            r = json.loads(line)
            b = bytes.fromhex(r["ram40"])
            if b[0x08] != 0:                      # Digital only
                continue
            samples = [int.from_bytes(b[0x2E + 2 * i:0x30 + 2 * i], 'little') for i in range(48)]
            rows.append({
                "t": r["t"], "file": p.split('/')[-1],
                "knob": int.from_bytes(b[0x28:0x2A], 'little'),
                "recent": int.from_bytes(b[0x2C:0x2E], 'little'),
                "gate": b[0xAF], "samples": samples,
                "pp": max(samples) - min(samples),
            })
    return rows


def main(paths):
    rows = load(paths)
    prev_recent = None
    accepted, noise = [], []
    for r in rows:
        best, margin, phase = correlate(r["samples"])
        r.update(best=best, margin=margin)
        refreshed = prev_recent is not None and r["recent"] > prev_recent + 20
        prev_recent = r["recent"]
        if refreshed and r["pp"] > 0:
            accepted.append(r)
        elif r["gate"] == 2 and r["recent"] == 0 and r["pp"] <= 40:
            noise.append(r)
    print(f"{len(rows)} Digital windows; {len(accepted)} PN-accepted (RECENT refreshed), {len(noise)} no-signal (gate open, RECENT 0, p-p<=40)")

    def q(vals, p):
        vals = sorted(vals)
        return vals[min(len(vals) - 1, int(p * len(vals)))] if vals else float('nan')

    for name, group in (("accepted", accepted), ("noise", noise)):
        m = [r["margin"] for r in group]
        b = [r["best"] for r in group]
        if not m:
            print(f"{name}: none"); continue
        print(f"{name:9s} margin  p05 {q(m, .05):5.1f}  median {q(m, .5):5.1f}  p95 {q(m, .95):5.1f}  | best|S| p05 {q(b, .05):8.0f} median {q(b, .5):8.0f}")
    # threshold sweep
    print("\nmargin threshold -> accepted-window pass rate | noise false-accept rate")
    for thr in (1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0):
        pa = sum(r["margin"] >= thr for r in accepted) / max(1, len(accepted))
        pn = sum(r["margin"] >= thr for r in noise) / max(1, len(noise))
        print(f"  {thr:3.1f}  {pa:6.1%} | {pn:6.2%}")
    # sensitivity: windows with small p-p where PN did not accept but the filter margin is high
    weak = [r for r in rows if r["gate"] == 2 and 30 < r["pp"] <= 150]
    if weak:
        hi = sum(r["margin"] >= 3.0 for r in weak)
        acc = sum(r["recent"] > 500 for r in weak)
        print(f"\nweak windows (30 < p-p <= 150): {len(weak)}; PN currently locked in {acc/len(weak):.0%}; matched-filter margin >= 3 in {hi/len(weak):.0%}")
    # best|S| versus p-p (linearity of the strength score)
    strong = [r for r in accepted if r["pp"] > 200]
    if strong:
        ratios = [r["best"] / r["pp"] for r in strong]
        print(f"\nbest|S| / p-p over accepted windows: median {st.median(ratios):.1f}, p05 {q(ratios,.05):.1f}, p95 {q(ratios,.95):.1f}  (a constant ratio = linear strength score)")


if __name__ == "__main__":
    paths = [p for a in sys.argv[1:] for p in glob.glob(a)]
    main(paths)
