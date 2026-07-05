#!/usr/bin/env python3
"""molt staircase chart — S vs experiment index from experiments.jsonl (the hero image).

Usage: staircase.py [--journal experiments.jsonl] [--out notes/progress.png]
                    [--epsilon harness/epsilon.txt]
Kept runner-side so the session agent regenerates it at session end (program.md) without
touching harness/. Skips malformed lines rather than dying (append-only journals accrete).

Rendering contract (the journal is the source of truth, and it is prose):
- decision fields are free text ("keep (config committed; ...)", "discard (no-op)") —
  classify by prefix, never by string equality.
- Tier-A speed runs are scored on eval-lite (diagnostics.S_is), a different instrument with
  its own noise floor (eps_lite): they get their own panel, never the full-suite axis.
- S_best is seeded by the best phase0 replica and rebases on full-suite keeps — the same
  reference the journal's delta fields are computed against.
"""
import argparse
import json
import statistics

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

GREEN, GRAY = "#2b8a3e", "#8899aa"


def load(journal):
    rows = []
    try:
        with open(journal) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except FileNotFoundError:
        pass
    return rows


def klass(e):
    d = (e.get("decision") or "").strip().lower()
    if d.startswith("calibration"):
        return "calibration"
    if d.startswith(("keep", "kept")):
        return "keep"
    return "discard"  # discard/reset/other: anything that did not move the ratchet


def is_lite(e):
    return str((e.get("diagnostics") or {}).get("S_is", "")).startswith("eval-lite")


def scatter_class(ax, pts, cls):
    if not pts:
        return
    xs, ss = [p[0] for p in pts], [p[1] for p in pts]
    if cls == "keep":
        ax.scatter(xs, ss, s=64, color=GREEN, zorder=3, label="keep")
    elif cls == "keep-provisional":
        ax.scatter(xs, ss, s=52, facecolors="none", edgecolors=GREEN, linewidths=1.6,
                   zorder=3, label="keep-provisional (reconfirmed at full S)")
    elif cls == "calibration":
        ax.scatter(xs, ss, s=36, facecolors="none", edgecolors=GRAY, linewidths=1.4,
                   label="baseline replica (ε calibration)")
    else:
        ax.scatter(xs, ss, s=36, color=GRAY, alpha=0.75, label="discard")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--journal", default="experiments.jsonl")
    ap.add_argument("--out", default="notes/progress.png")
    ap.add_argument("--epsilon", default="harness/epsilon.txt")
    a = ap.parse_args()

    rows = load(a.journal)
    scored = [e for e in rows if e.get("S") is not None]
    if not scored:
        print(f"[staircase] no scored entries in {a.journal}; nothing to plot")
        return

    try:
        eps = float(open(a.epsilon).read().strip())
    except (OSError, ValueError):
        eps = None
    lite_band = None  # (mean of clean lite replicas, eps_lite) from the lite-eps-cal row
    for e in rows:
        d = e.get("diagnostics") or {}
        if d.get("eps_lite") and d.get("clean_replicas"):
            lite_band = (statistics.mean(d["clean_replicas"]), float(d["eps_lite"]))

    xs = list(range(1, len(scored) + 1))
    full = [(x, e) for x, e in zip(xs, scored) if not is_lite(e)]
    lite = [(x, e) for x, e in zip(xs, scored) if is_lite(e)]

    # S_best per full-suite run: best replica seeds it, keeps rebase it.
    best, b = [], float("-inf")
    for _, e in full:
        if klass(e) in ("calibration", "keep"):
            b = max(b, e["S"])
        best.append(b if b != float("-inf") else None)

    fig, (ax, axl) = plt.subplots(
        2, 1, figsize=(9, 6.4), dpi=150, sharex=True,
        gridspec_kw={"height_ratios": [2.4, 1.0]}, constrained_layout=True)
    fig.suptitle(f"molt ratchet — {len(scored)} scored experiments", fontsize=12)

    # ── top: frozen full suite, the ratchet ─────────────────────────────────
    ax.set_title("frozen full suite", fontsize=9, loc="left", color="#444444")
    steps = [(x, v) for (x, _), v in zip(full, best) if v is not None]
    if steps:
        sx = [x for x, _ in steps] + [xs[-1] + 0.6]
        sv = [v for _, v in steps] + [steps[-1][1]]
        if eps:
            ax.fill_between(sx, [v - eps for v in sv], [v + eps for v in sv],
                            step="post", color=GREEN, alpha=0.10, lw=0,
                            label=f"S_best ± ε ({eps:.4f}, 2σ of replicas)")
        ax.step(sx, sv, where="post", lw=2, color=GREEN, label="S_best (ratchet reference)")
    for cls in ("calibration", "discard", "keep"):
        scatter_class(ax, [(x, e["S"]) for x, e in full if klass(e) == cls], cls)
    for x, e in full:
        if klass(e) == "keep" and e.get("delta") is not None:
            ax.annotate(f"keep: Δ {e['delta']:+.4f}", (x, e["S"]),
                        xytext=(8, 8), textcoords="offset points",
                        fontsize=7.5, color=GREEN)
    ax.set_ylabel("S (full suite)")
    ax.legend(loc="lower right", fontsize=7.5)
    ax.grid(alpha=0.25)

    # ── bottom: eval-lite screening runs (Tier-A speed experiments) ─────────
    axl.set_title("eval-lite screen — speed tier, not comparable to full S",
                  fontsize=9, loc="left", color="#444444")
    if lite_band:
        m, el = lite_band
        axl.axhspan(m - el, m + el, color=GRAY, alpha=0.15, lw=0,
                    label=f"lite noise band ± ε_lite ({el:g})")
        axl.axhline(m, color=GRAY, lw=1, ls=":", alpha=0.8)
    for cls, mapped in (("keep", "keep-provisional"), ("discard", "discard")):
        scatter_class(axl, [(x, e["S"]) for x, e in lite if klass(e) == cls], mapped)
    axl.set_ylabel("S (eval-lite)")
    axl.set_xlabel("experiment index (journal order)")
    axl.legend(loc="upper right", fontsize=7.5)
    axl.grid(alpha=0.25)

    axl.set_xlim(0.4, len(scored) + 0.6)
    axl.set_xticks(xs)
    axl.set_xticklabels([e.get("id", e.get("tier", "?")) for e in scored],
                        rotation=38, ha="right", fontsize=6.5)

    fig.savefig(a.out)
    print(f"[staircase] wrote {a.out} ({len(scored)} points: "
          f"{len(full)} full-suite, {len(lite)} eval-lite)")


if __name__ == "__main__":
    main()
