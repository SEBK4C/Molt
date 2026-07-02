#!/usr/bin/env python3
"""molt staircase chart — S vs experiment index from experiments.jsonl (the hero image).

Usage: staircase.py [--journal experiments.jsonl] [--out notes/progress.png]
Kept runner-side so the session agent regenerates it at session end (program.md) without
touching harness/. Skips malformed lines rather than dying (append-only journals accrete).
"""
import argparse
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def load(journal):
    rows = []
    try:
        with open(journal) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if e.get("S") is not None:
                    rows.append(e)
    except FileNotFoundError:
        pass
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--journal", default="experiments.jsonl")
    ap.add_argument("--out", default="notes/progress.png")
    a = ap.parse_args()

    rows = load(a.journal)
    if not rows:
        print(f"[staircase] no scored entries in {a.journal}; nothing to plot")
        return

    xs = list(range(1, len(rows) + 1))
    ss = [e["S"] for e in rows]
    kept = [bool(e.get("decision") not in (None, "discard", "reset")
                 and e.get("decision") != "calibration") for e in rows]
    best = []
    b = float("-inf")
    for e, s in zip(rows, ss):
        if e.get("decision") in ("keep", "keep-provisional"):
            b = max(b, s)
        best.append(b if b != float("-inf") else None)

    fig, ax = plt.subplots(figsize=(9, 4.5), dpi=140)
    ax.plot(xs, ss, "o", ms=5, color="#8899aa", alpha=0.65, label="experiment S")
    for x, s, k in zip(xs, ss, kept):
        if k:
            ax.plot([x], [s], "o", ms=7, color="#2b8a3e")
    bx = [x for x, v in zip(xs, best) if v is not None]
    bv = [v for v in best if v is not None]
    if bx:
        ax.step(bx, bv, where="post", lw=2, color="#2b8a3e", label="S_best (ratchet)")
    tiers = [e.get("tier", "?") for e in rows]
    for x, t in zip(xs, tiers):
        ax.annotate(str(t), (x, ax.get_ylim()[0]), fontsize=6, ha="center",
                    xytext=(0, -14), textcoords="offset points", clip_on=False)
    ax.set_xlabel("experiment index")
    ax.set_ylabel("S")
    ax.set_title(f"molt ratchet — {len(rows)} scored experiments")
    ax.legend(loc="lower right", fontsize=8)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(a.out)
    print(f"[staircase] wrote {a.out} ({len(rows)} points)")


if __name__ == "__main__":
    main()
