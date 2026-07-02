# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

**molt** is an autoresearch-pattern ratchet loop (ported from karpathy/autoresearch) that searches quantization recipes and serving configs for `deepreinforce-ai/Ornith-1.0-397B` (a 512-expert qwen3_5_moe) until it serves well on a specific box: 90 GB DDR5, 2×RTX 4090, Gen5 SSD. The train step of autoresearch is replaced by a quantize/serve/eval step against llama.cpp.

**Current state: bootstrapped (2026-07-02); one-time weight pipeline in flight.** `SPEC.md` remains the design contract. `harness/` (referee `harness/score.py` with all four checkers implemented + tests, prompts, refs, provisional SHA-256 manifest), `runner/`, `recipes/`, `serve/`, `corpora/`, `scripts/` all exist and are tested. **`TODO.md` is the live cross-session state — read it first, reconcile against disk, trust disk.** The 397B BF16 download + P1–P5 chain status, HUMAN gates, and resume procedure live there and in `notes/`. Working dir on llm-serve: `/home/seb/molt` is a symlink to this repo; repo `models/` symlinks to `/mnt/proxmox/llm-serve/models/ornith-397b` (never write large files to the root fs).

## Two operating modes — know which one you're in

1. **Building out the spec/harness (this repo, now).** Normal development. Read `SPEC.md` first; it defines the contract everything else implements.
2. **Running as the overnight research agent (on llm-serve, after setup).** `program.md` is the operative instruction file and defines strict ownership rules:
   - Agent MAY edit: `recipes/current.yaml`, `serve/current.args`, `notes/*.md`.
   - Agent MUST NOT edit: `harness/`, `runner/`, `program.md`, `experiments.jsonl` history, `score.py`. The harness is SHA-256 manifest-checked before every scoring run; any modification auto-fails all subsequent experiments. This is intentional anti-reward-hacking — do not "fix" it.
   - Never read `harness/refs/` (golden answers). S is computed only by the referee.

## Commands

```bash
# One-time setup on llm-serve — thin orchestrator over scripts/ (all idempotent):
./prepare.sh                       # env + vendor build + download + corpora + chain hint
./scripts/post_download_chain.sh   # P1 Q8_0 -> P2 imatrix -> P3 KLD -> P4 baseline quant
./scripts/phase0_epsilon.sh        # P5: score baseline 3x -> harness/epsilon.txt -> FINAL freeze

# Referee — the only source of truth for scores. Exit 2 = manifest tamper (auto-fail).
runner/score.sh <exp_id> [--lite] [--gguf p] [--server url]
runner/score.sh --verify-only      # manifest check only

# Harness tests + manifest
.venv/bin/python -m pytest harness/tests/ scripts/test_endpoint_mock.py -q
.venv/bin/python harness/manifest.py --write [--provisional] | --verify

# Loop runners
runner/run_tierA.sh <exp_id> [--full] [--gguf p]  # serve-config exp: serve + eval(+lite) (~20 min)
runner/run_tierB.sh <exp_id>                      # requant from frozen Q8_0 + full eval (4 h)
runner/journal.sh '<json>'                        # append-only experiments.jsonl writes
runner/gpu_lock.sh status|wait-idle|with-gpus     # GPU serialization; NEVER kills anything
```

Python env is uv-managed: `uv venv && uv pip install gguf safetensors transformers datasets evalplus numpy matplotlib`.

## Architecture

**The ratchet.** Each experiment mutates exactly one sandbox surface, runs, gets scored, and is kept iff all hard gates pass AND `S > S_best + ε` (`git commit`), else `git reset --hard`. ε is the measured eval-noise floor from Phase 0 (3× baseline replication, ε = 2σ), stored in `harness/epsilon.txt`. One exception: once per night a result with `S > S_best − ε/2` may be kept if it frees ≥ 5 GB (buys headroom for later quality promotions). Sessions run on branch `molt/<yyyymmdd>` with an append-only `experiments.jsonl` journal.

**Experiment tiers** (budgets differ because a requant is 1–3 h disk-bound):
- **Tier A** (20 min): `serve/current.args` only — `--n-cpu-moe`, tensor placement, KV cache type, MTP draft on/off. Scored with eval-lite; keeps re-confirmed with full S at session end.
- **Tier B** (4 h): `recipes/current.yaml` → full requant from the permanent Q8_0 master with imatrix.
- **Tier C** (6 h, ≤1/night): imatrix corpus remix, then Tier B.

Tier B requants (disk-bound) pipeline with Tier A evals (GPU-bound); a runner lock serializes RAM-hungry phases since quantize and serve can't both fit in 90 GB.

**The metric.** Hard gates first: size ≤ 121 GB, loads under llama-server, smoke-clean, decode ≥ 8 t/s @ 32K, prefill ≥ 250 t/s. Then S = 0.45·BFCL-lite + 0.25·τ-lite + 0.20·EvalPlus HumanEval+ + 0.10·nested-JSON stress — all behavioral, driven over HTTP against llama-server with Ornith's own chat template. Deliberately behavioral-primary: KLD/PPL under-detect degradation of an RL'd tool-calling policy, so they're logged as diagnostics only. All checks are AST/exec/exact — no LLM judges in the loop (determinism protects the ratchet). Weights and gate thresholds live at the top of `score.py` and must match SPEC.md §4.

**Quant recipe structure** (`baseline.yaml` is the seed; agent edits a copy at `recipes/current.yaml`): YAML tensor-pattern → quant-type map, rendered by `runner/render_quant_cmd.py` into `llama-quantize --tensor-type` flags. The routed experts (97.4% of params) get aggressive 2-bit treatment; the "fragile set" (embeddings, attention, router gates, shared experts, vision — DeepReinforce's own FP8 ignore list) has a Q8_0 floor that must never be lowered. `ffn_down_exps` is the known quality-critical group; nested-JSON stress is the canary that cracks first at ~2 bpw.

**Key invariants**
- `models/Ornith-Q8_0.gguf` (~420 GB) and `imatrix-*.dat` are permanent — the requant source, imatrix base, and KLD reference. Never delete.
- Download the BF16 repo, not FP8: `convert_hf_to_gguf.py` can't ingest compressed-tensors.
- Everything in `harness/` is frozen with a SHA-256 manifest; a 100-sample secret split lives outside the repo entirely.
- llama.cpp is a pinned build (needs `qwen3_5_moe` + `--spec-type draft-mtp`) at `vendor/llama.cpp`.

`REQUIREMENTS.md` covers credentials, disk budget (~1.47 TB peak of 2.6 TB), dataset sources, and the pre-flight checklist for session 1.
