# molt — REQUIREMENTS

## Credentials / keys

| Secret | Purpose | Scope / notes |
|---|---|---|
| `HF_TOKEN` | download `deepreinforce-ai/Ornith-1.0-397B` (BF16, 807 GB); upload keepers to `SEBK4C/Ornith-1.0-397B-Featherweight`; spin up Inference Endpoint for golden traces | fine-grained: read (gated-repo accept if gated) + write on your namespace + Inference Endpoints admin. Export in `~/.config/molt/env`, never in repo |
| `ANTHROPIC_API_KEY` | Claude Code = the loop agent | Claude Code reads it from env/`claude login`. Budget: overnight session ≈ 30–80 M tokens of agent traffic; set spend limit |
| GitHub: SSH deploy key or `GH_TOKEN` | push `SEBK4C/molt` (journal, recipes, progress.png); `gh` CLI for end-of-run Discussion/PR summaries (autoresearch community pattern) | deploy key write-scoped to the one repo |
| SSH keypair → llm-serve | you/agent supervision from laptop; Tailscale already provides transport (`llm-serve.bunny-sunfish.ts.net`) | agent runs locally on llm-serve; no inbound keys needed beyond yours |
| `WANDB_API_KEY` (optional) | mirror `experiments.jsonl` as runs | skip in v1; jsonl + notebook suffice |
| ~~OPENAI_API_KEY~~ | not needed — τ-lite user-sim replaced by canned scripts for determinism | — |

HF GPU credits allocation: 1 dedicated Inference Endpoint, 8×H100/MI300-class, ~4–6 h total:
(a) golden outputs for BFCL-lite/τ-lite/nested-JSON refs from FP8 Ornith, (b) ~5–20 M tokens of
self-generated agent traces → imatrix + KLD corpora. Tear down immediately after; everything else
runs locally.

## Software (llm-serve)

- CUDA ≥ 12.4 driver stack (already present for ds4), `gcc`, `cmake`, `git`, `git-lfs`, `uv`, `jq`, `tmux`
- llama.cpp pinned build with `qwen3_5_moe` + `--spec-type draft-mtp`: `cmake -DGGML_CUDA=ON`; binaries
  used: `llama-quantize`, `llama-imatrix`, `llama-perplexity`, `llama-server`, `llama-bench`
- Python env (uv): `gguf`, `safetensors`, `transformers` (convert script deps), `datasets`,
  `evalplus`, `numpy`, `matplotlib` (staircase chart)
- Claude Code CLI on llm-serve, run inside `tmux` with permissions disabled, working dir `/home/seb/molt`
- llama-swap: add `Ornith-Featherweight` entry (port, `gpu-exclusive` group, `checkEndpoint: /health`)
  only after first converged quant — the loop runs llama-server directly on a scratch port (9021)

## Disk plan (2.6 TB)

| Item | Size | Lifecycle |
|---|---|---|
| HF BF16 snapshot | 807 GB | delete after Q8_0 GGUF verified |
| `Ornith-Q8_0.gguf` | ~420 GB | permanent (requant source, imatrix, KLD base) |
| KLD base logits + imatrix files | ~10–40 GB | permanent |
| quants (best + candidate) | 2 × ~121 GB | candidate deleted on discard |
| corpora + harness + goldens | < 20 GB | permanent |
| Peak | ~1.47 TB | OK |

## Datasets

| Dataset | Use |
|---|---|
| self-generated Ornith-FP8 traces (HF endpoint) | imatrix primary + KLD held-out — distribution-matched to the RL'd policy |
| `Salesforce/xlam-function-calling-60k` | imatrix + nested-JSON seed material |
| `glaiveai/glaive-function-calling-v2` | imatrix mix |
| SWE-agent-style trajectories (e.g. `SWE-bench` trajectories dump) | imatrix mix (multi-turn tool loops) |
| `bigcode/the-stack-smol` slices | 20% code component of imatrix |
| BFCL v4 data (`gorilla-llm/Berkeley-Function-Calling-Leaderboard`) | frozen 300-sample eval slice |
| `sierra-research/tau-bench` retail+airline | frozen 40-episode multi-turn eval, canned user scripts |
| EvalPlus HumanEval+ | frozen code eval |
| internal nested-JSON stress set (generated once, goldens from FP8) | frozen canary |

All eval sets frozen into `harness/` with SHA-256 manifest before session 1. Secret 100-sample
split kept outside the repo, scored manually end-of-session.

## Benchmarks / reporting artifacts

- staircase chart: S vs experiment index (`analysis.ipynb` port) — the hero image
- t/s table @ ctx {0, 32K, 128K} decode+prefill, MTP on/off (`llama-bench` + server probes)
- per-keep: recipe.yaml diff, size, KLD, S components — goes in the HF model card
- cross-links in READMEs: `antirez/ds4`, `karpathy/autoresearch`, upstream Ornith repos

## Fine-tuning (explicitly out of scope v1)

No QAT/post-quant recovery finetune locally — 397B optimizer state doesn't fit any budget here.
If 2-bit degradation on tool syntax proves unrecoverable by recipe search: roadmap item = LoRA
recovery pass on HF credits (train adapters on FP8 against self-distilled traces, merge, requant).
Requires nothing new except more endpoint hours; keep `HF_TOKEN` scope ready.

## Pre-flight checklist

1. `nvidia-smi` shows both 4090s idle; llama-swap `gpu-exclusive` group prevents collisions —
   take the group lock for the whole session (runner does this)
2. `df -h` ≥ 1.6 TB free before P0 download
3. `HF_TOKEN`, `ANTHROPIC_API_KEY` in `~/.config/molt/env`; `set -a; source ...` in tmux
4. llama.cpp build passes `llama-server -m <any small gguf> --spec-type draft-mtp` sanity
5. harness manifest generated: `python harness/manifest.py --write`
6. Phase 0: baseline quant scored 3× → `harness/epsilon.txt`
7. `git checkout -b molt/<date>`; start Claude Code: "Read program.md and start tonight's session."
