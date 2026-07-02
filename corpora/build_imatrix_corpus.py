#!/usr/bin/env python3
"""Build corpora/imatrix.txt from the recipes/imatrix.yaml mix (front-of-shuffle slices).

Usage: build_imatrix_corpus.py [--mix recipes/imatrix.yaml] [--out corpora/imatrix.txt]
v1 = public-data fallback; FP8 self-traces get added via HG1 later (Tier-C-style change).
"""
import argparse
import os
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import corpus_lib as lib  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mix", default="recipes/imatrix.yaml")
    ap.add_argument("--out", default="corpora/imatrix.txt")
    a = ap.parse_args()

    mix = yaml.safe_load(open(a.mix))
    seed = mix.get("seed", 20260702)
    budget = mix.get("target_mb", 16) * 1_000_000

    src = lib.load_sources()
    texts = lib.build_texts(src, seed)

    weights = {c["name"]: c["weight"] for c in mix["components"] if c["name"] in texts}
    z = sum(weights.values())
    print(f"[imatrix_corpus] components available: {list(weights)} (weights renormalized /{z:.2f})")

    parts, total = [], 0
    for name, w in weights.items():
        got, size = lib.take_bytes(texts[name], budget * w / z, from_back=False)
        parts.extend(got)
        total += size
        print(f"[imatrix_corpus] {name}: {len(got)} items, {size/1e6:.1f} MB")

    tmp = a.out + ".part"
    with open(tmp, "w") as f:
        f.write("".join(parts))
    os.replace(tmp, a.out)
    print(f"[imatrix_corpus] wrote {a.out}: {total/1e6:.1f} MB (target {budget/1e6:.0f} MB)")


if __name__ == "__main__":
    main()
