#!/usr/bin/env python3
"""Build corpora/kld_heldout.txt — ~2 MB slice DISJOINT from imatrix.txt (same shuffle seed,
consumed from the BACK; see corpus_lib docstring for the disjointness contract).

Usage: build_kld_heldout.py [--mix recipes/imatrix.yaml] [--out corpora/kld_heldout.txt] [--mb 2]
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
    ap.add_argument("--out", default="corpora/kld_heldout.txt")
    ap.add_argument("--mb", type=float, default=2.0)
    a = ap.parse_args()

    mix = yaml.safe_load(open(a.mix))
    seed = mix.get("seed", 20260702)
    imatrix_budget = mix.get("target_mb", 16) * 1_000_000
    budget = int(a.mb * 1_000_000)

    src = lib.load_sources()
    texts = lib.build_texts(src, seed)

    weights = {c["name"]: c["weight"] for c in mix["components"] if c["name"] in texts}
    z = sum(weights.values())

    parts, total = [], 0
    for name, w in weights.items():
        # sanity: held-out (back) must not reach into the imatrix (front) region
        front_budget = imatrix_budget * w / z
        avail = sum(len(t.encode()) for t in texts[name] if t)
        want = budget * w / z
        assert avail > front_budget + want, \
            f"{name}: source too small for disjoint split ({avail/1e6:.1f} MB avail)"
        got, size = lib.take_bytes(texts[name], want, from_back=True)
        parts.extend(got)
        total += size
        print(f"[kld_heldout] {name}: {len(got)} items, {size/1e6:.2f} MB (from back)")

    tmp = a.out + ".part"
    with open(tmp, "w") as f:
        f.write("".join(parts))
    os.replace(tmp, a.out)
    print(f"[kld_heldout] wrote {a.out}: {total/1e6:.2f} MB")


if __name__ == "__main__":
    main()
