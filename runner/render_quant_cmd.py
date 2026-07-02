#!/usr/bin/env python3
"""molt runner — render a quant recipe YAML into a llama-quantize command string.

Usage: render_quant_cmd.py <recipe.yaml> [--imatrix P] [--in P] [--out P] [--threads N] [--bin P]
Prints one shell command to stdout:
  <bin> --allow-requantize --imatrix <im> --tensor-type '<pat>=<type>' ... <in> <out>.part <FALLBACK> <n> \
    && mv <out>.part <out>
Flags override the recipe's source_gguf/imatrix. Output goes through .part + atomic rename;
callers pipe to bash (prepare.sh P4) or capture (run_tierB.sh).
"""
import argparse
import os
import re
import shlex
import sys

import yaml

# ggml quant type names accepted by llama-quantize (lowercase canonical)
KNOWN_TYPES = {
    "f32", "f16", "bf16",
    "q8_0", "q6_k", "q5_k", "q5_k_m", "q5_k_s", "q5_0", "q5_1",
    "q4_k", "q4_k_m", "q4_k_s", "q4_0", "q4_1",
    "q3_k", "q3_k_m", "q3_k_s", "q3_k_l", "q2_k", "q2_k_s",
    "iq4_nl", "iq4_xs", "iq3_m", "iq3_s", "iq3_xxs",
    "iq2_m", "iq2_s", "iq2_xs", "iq2_xxs", "iq1_m", "iq1_s",
    "tq1_0", "tq2_0", "mxfp4_moe",
}


def render(recipe_path, imatrix=None, src=None, out=None, threads=None, binpath=None):
    r = yaml.safe_load(open(recipe_path))

    src = src or r.get("source_gguf")
    imatrix = imatrix or r.get("imatrix")
    if not src:
        raise SystemExit("recipe missing source_gguf and no --in given")
    if not out:
        raise SystemExit("--out required")
    fallback = str(r.get("fallback_type", "q8_0")).lower()
    if fallback not in KNOWN_TYPES:
        raise SystemExit(f"unknown fallback_type: {fallback}")

    binpath = binpath or os.environ.get(
        "MOLT_LLAMA_QUANTIZE", "vendor/llama.cpp/build/bin/llama-quantize"
    )

    parts = [shlex.quote(binpath)]
    if r.get("requantize_from_q8", True):
        parts.append("--allow-requantize")
    if imatrix:
        parts += ["--imatrix", shlex.quote(imatrix)]

    seen = set()
    for ent in r.get("tensor_types", []):
        pat, typ = ent["pattern"], str(ent["type"]).lower()
        if typ not in KNOWN_TYPES:
            raise SystemExit(f"unknown quant type {typ!r} for pattern {pat!r}")
        re.compile(pat)  # fail fast on a bad regex
        if pat in seen:
            raise SystemExit(f"duplicate pattern {pat!r}")
        seen.add(pat)
        parts += ["--tensor-type", shlex.quote(f"{pat}={typ}")]

    nthreads = threads or os.cpu_count() or 16
    part = out + ".part"
    parts += [shlex.quote(src), shlex.quote(part), fallback.upper(), str(nthreads)]
    return " ".join(parts) + f" && mv {shlex.quote(part)} {shlex.quote(out)}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("recipe")
    ap.add_argument("--imatrix")
    ap.add_argument("--in", dest="src")
    ap.add_argument("--out", required=True)
    ap.add_argument("--threads", type=int)
    ap.add_argument("--bin")
    a = ap.parse_args()
    print(render(a.recipe, a.imatrix, a.src, a.out, a.threads, a.bin))


if __name__ == "__main__":
    main()
