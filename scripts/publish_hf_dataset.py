#!/usr/bin/env python3
"""Publish the molt eval suite + FP8 goldens + calibration corpus as a community dataset on
the owner's HF account (authorized 2026-07-04: "publish this dataset on my HF and make a
project and documentation to get feedback from the community").

Usage:
  .venv/bin/python scripts/publish_hf_dataset.py --dry-run       # list what would upload
  .venv/bin/python scripts/publish_hf_dataset.py                 # create + upload
  .venv/bin/python scripts/publish_hf_dataset.py --repo SEBK4C/molt-ornith-eval --private

Contents (licensing checked):
- harness/prompts/* + harness/refs/* (ours + BFCL-derived [Apache-2.0, gorilla-llm] +
  HumanEval+ derived [MIT/Apache, evalplus]) with provenance notes
- refs_fp8/*.fp8.json + corpora/fp8_traces.jsonl (derived from MIT-licensed Ornith weights)
  — included only if present (HG1 output)
- experiments.jsonl + notes/progress.png + key notes/*.md (the research journal)
- README.md rendered from docs/DATASET_CARD.md
Excludes: anything under models/ (weights publish separately as the Featherweight model repo),
the secret split (never in-repo), tokens/credentials (nothing under ~/.config or ~/.cache).
"""
import argparse
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

INCLUDE = [
    ("harness/prompts", "harness/prompts"),
    ("harness/refs", "harness/refs"),
    ("refs_fp8", "refs_fp8"),                      # optional (post-HG1)
    ("corpora/fp8_traces.jsonl", "corpora/fp8_traces.jsonl"),  # optional
    ("experiments.jsonl", "journal/experiments.jsonl"),
    ("notes/progress.png", "journal/progress.png"),
    ("notes/measured-reality-2026-07-02.md", "docs/measured-reality.md"),
    ("notes/validation-audit-2026-07-03.md", "docs/validation-audit.md"),
    ("notes/ds4-lessons.md", "docs/ds4-lessons.md"),
    ("recipes/baseline.yaml", "recipes/baseline.yaml"),
    ("recipes/current.yaml", "recipes/current.yaml"),
    ("serve/current.args", "serve/current.args"),
    ("docs/RESEARCH_STATEMENT.md", "docs/research-statement.md"),
    ("docs/RESEARCH_REPORT.md", "RESEARCH_REPORT.md"),
    ("docs/DATASET_CARD.md", "README.md"),
]


def gather():
    ok, missing = [], []
    for src, dst in INCLUDE:
        p = os.path.join(REPO_ROOT, src)
        (ok if os.path.exists(p) else missing).append((src, dst))
    return ok, missing


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default="SEBK4C/molt-ornith-eval")
    ap.add_argument("--private", action="store_true",
                    help="create private first; flip public in the UI after review")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    ok, missing = gather()
    print(f"[publish] {len(ok)} paths ready, {len(missing)} absent (skipped):")
    for src, dst in ok:
        print(f"  + {src}  ->  {dst}")
    for src, _ in missing:
        print(f"  - {src}  (absent — fine if pre-HG1)")
    if a.dry_run:
        return 0

    from huggingface_hub import HfApi
    api = HfApi()
    api.create_repo(a.repo, repo_type="dataset", private=a.private, exist_ok=True)
    for src, dst in ok:
        p = os.path.join(REPO_ROOT, src)
        if os.path.isdir(p):
            api.upload_folder(folder_path=p, path_in_repo=dst, repo_id=a.repo,
                              repo_type="dataset")
        else:
            api.upload_file(path_or_fileobj=p, path_in_repo=dst, repo_id=a.repo,
                            repo_type="dataset")
        print(f"[publish] uploaded {src}")
    print(f"[publish] done: https://huggingface.co/datasets/{a.repo}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
