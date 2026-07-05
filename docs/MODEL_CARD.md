---
license: mit
base_model: deepreinforce-ai/Ornith-1.0-397B
base_model_relation: quantized
pipeline_tag: text-generation
tags:
- gguf
- llama.cpp
- quantized
- 2-bit
- moe
- function-calling
- tool-use
- agentic
pretty_name: "Ornith-1.0-397B Featherweight (2.41 bpw GGUF)"
---

# Ornith-1.0-397B Featherweight — a 397B agent in 119.5 GB (2.41 bits/weight)

A single-file GGUF derivative of [`deepreinforce-ai/Ornith-1.0-397B`](https://huggingface.co/deepreinforce-ai/Ornith-1.0-397B)
(512-expert qwen3.5 MoE, MIT) compressed to **15% of original size**, tuned to serve on one
commodity box: **2×RTX 4090 (24 GB) + 90 GB DDR5 + one NVMe SSD**. Produced by
[molt](https://huggingface.co/datasets/SEBK4C/molt-ornith-eval), an autonomous
quantization-research ratchet with a frozen, SHA-256-manifested behavioral referee —
this checkpoint is tag `featherweight-v0`, the best artifact the loop has kept so far.

## Headline numbers (all measured, all replicable)

| Behavioral suite | Score @2.41 bpw | What it checks |
|---|---|---|
| BFCL v4 slice (300 cases, AST match) | **0.91** | single/parallel function calls + irrelevance |
| τ-lite (40 multi-turn episodes) | **1.00** | tool-use episodes, terminal-state deep-equal |
| HumanEval+ (164, sandboxed exec) | **0.98** | code correctness |
| nested-JSON stress (100) | **0.72** | verbatim argument fidelity — *where 2-bit bites* |
| **S (weighted)** | **0.9258** | noise floor ε = 0.0053 (3× replication) |

| Serving (this exact config, warm) | Measured |
|---|---|
| decode @32K context | **18.5 t/s** |
| prefill @38K tokens | **717 t/s** |
| VRAM | ~16.5 + ~21.5 GB (fits 2×24 GB) |
| context served | 4 slots × 40K |

Every number comes from a frozen harness the optimizing agent could not edit (manifest-checked
before every scoring run), with an append-only experiment journal — including the failed
experiments. Full protocol, refs, and journal: the
[molt-ornith-eval dataset](https://huggingface.co/datasets/SEBK4C/molt-ornith-eval). One-page
methodology + costed roadmap: `RESEARCH_STATEMENT.md` in this repo.

## Recipe (what was done to the weights)

Asymmetric crush, same family as antirez/ds4's DeepSeek quants — independently reproduced on
a different MoE architecture:

- **Routed experts** (97.4% of params): gate/up `IQ2_XXS`, down `Q2_K`, imatrix-tuned
  (agentic calibration mix: function-calling + code + tool-syntax).
- **Fragile set** (embeddings, attention/GDN, router gates, shared experts — DeepReinforce's
  own FP8 ignore list): **Q8_0 floor, never lowered.** The loop *tested* lowering embeddings
  to Q6_K (exp005): S dropped 0.0035 — the floor is load-bearing, so it stays.

Exact recipe: `recipe.yaml` in this repo (rendered to `llama-quantize --tensor-type` flags).

## File

`Ornith-1.0-397B-Featherweight-v0.gguf` — 119,517,476,064 bytes,
sha256 `1499c2f2d84dcdbb4c243371522cc8f98ca4a76a0bc2f1e4801b9f64f0c57dc2`.

## How to run

Needs llama.cpp with `qwen3_5_moe` support (upstream commit `4fc4ec55` or later). The
reference config (also shipped as `serving.args` with full per-flag rationale):

```
llama-server -m Ornith-1.0-397B-Featherweight-v0.gguf \
  -ngl 99 --n-cpu-moe 50 -ts 50,10 \
  -b 8192 -ub 8192 -fa on \
  --cache-type-k q8_0 --cache-type-v q8_0 \
  -c 163840 -np 4 -tb 32 \
  --jinja --reasoning-format auto --reasoning-budget 1024
```

Notes that save you a day of tuning:
- `--n-cpu-moe N` places GPU-expert layers at the *tail*; without a matching `-ts` the even
  split OOMs GPU1. The `50,10` split above is measured-safe on 2×24 GB.
- Prefill cost on RAM-bound boxes = expert-weight streams per ubatch: big `-ub` is the lever
  (129 t/s @2048 → 700+ @8192 with 10 GPU expert layers).
- The model thinks unboundedly by default (9K+ chars on trivial prompts);
  `--reasoning-budget 1024` is part of the reference config.
- **Do NOT enable speculative decoding on this class of box — we measured it, it makes
  things worse.** With expert weights CPU/RAM-resident, verifying k drafted tokens batches
  k tokens through the target, and each token routes to its own top-10 of 512 experts —
  batch-verify streams up to k× the expert weights of plain decode, inverting speculation's
  entire premise. Measured on this hardware: `--spec-type ngram-simple` = **−10% decode**;
  a same-family 9B drafter (`draft-simple`, GPU-resident, quantized draft-KV) = **−34%**.
  This extends to EAGLE/Medusa-class draft heads (we cancelled a planned ~$1.2K EAGLE-3
  training on this result). If your experts fit fully in VRAM, the classic economics return —
  re-measure before trusting either direction. (Ornith's declared MTP head is unreleased in
  both upstream repos regardless; convert with `--no-mtp` or the GGUF is unloadable.)
  Details: [RESEARCH_REPORT §3.1](https://huggingface.co/datasets/SEBK4C/molt-ornith-eval/blob/main/RESEARCH_REPORT.md).

### Zero-install option: the llamafile sidecar

`Ornith-1.0-397B-Featherweight-serve.llamafile` (320 MB, sha256
`7583ea2f0e6ad2e9b57e2b3adce8ac20b95b84ddb626163bd9c444218fb089e5`) is
[llamafile](https://github.com/Mozilla-Ocho/llamafile) v0.10.3 (qwen3.5-MoE-capable) with the
reference serving flags embedded — **weights are NOT inside it**. Download it next to the
GGUF and run:

```
chmod +x Ornith-1.0-397B-Featherweight-serve.llamafile
./Ornith-1.0-397B-Featherweight-serve.llamafile
```

It expects `Ornith-1.0-397B-Featherweight-v0.gguf` in the working directory and serves the
OpenAI-compatible API on `:8080` (chat template comes from the GGUF metadata). Anything you
append **overrides** the baked-in defaults (last value wins) — e.g. a slow CPU-only sanity
run on a GPU-less box: `./…serve.llamafile -ngl 0 -c 8192 -np 1`. The baked-in GPU split
(`-ts 50,10`) assumes 2×24 GB cards; single-GPU users should pass their own
`-ngl/-ts/--n-cpu-moe`. Verified end-to-end: boots from embedded args, loads via the relative
model name, answers with bounded thinking.

## Honest limitations (read before citing)

1. **No absolute-degradation anchor yet.** S grades against task ground truth, not against
   FP8 Ornith; S_fp8 (endpoint golden run) is queued. Do not read S = 0.9258 as "7.4% worse
   than the original".
2. BFCL/τ here are **degradation tripwires, not capability meters** — a 9B sibling ties the
   397B on the BFCL slice. The nested-JSON suite is the discriminating instrument, and it is
   where the damage shows (0.72): verbatim token-precision tails, exotic unicode keys,
   >2^53 integers.
3. Tool calls were grammar-constrained during evaluation: malformed-JSON failure modes are
   masked by construction (deployment-realistic, but flattering).
4. EvalPlus protocol deviates from official (plus-input cap 30/problem): relative use only.
5. Long-context *quality* is throughput-probed only; behavioral suites are short-context.

## Provenance / journal excerpt

Journal (append-only, in the dataset repo) — the v0 trail:

| exp | change | verdict |
|---|---|---|
| exp001 | last-2-layer `ffn_down_exps` → Q4_K | DISCARD — damage isn't late-layer-concentrated |
| exp002/004 | expert-layer GPU placement ladder (→10 layers) | KEEP — +4% decode, −1 h/eval |
| exp003 | halve thinking budget | DISCARD — no-op below 1024 |
| exp005 | embeddings Q8→Q6_K | DISCARD — S −0.0035, Q8 embd floor is load-bearing |
| exp007 | ngram speculation | DISCARD — decode −10% (think-streams aren't self-repetitive) |
| exp008 | same-family 9B drafter | DISCARD — decode −34%; **speculation inverts on CPU-resident MoE** |
| exp009 | top-energy gate/up layers → IQ2_XS | DISCARD — flat; imatrix energy ≠ behavioral value |

**Search status**: the recipe is **locally optimal at 2.41 bpw under public-data calibration**
— three surfaces falsified, placement saturated, speculation family closed. v0 is where the
search *completed*, not where it gave up. Next quality levers (costed in the
[research report](https://huggingface.co/datasets/SEBK4C/molt-ornith-eval/blob/main/RESEARCH_REPORT.md)):
FP8 golden anchor (~$100), imatrix v2 from distribution-matched traces (reopens the search),
LoRA recovery (~$1.5K).

Built by an autonomous research loop (Claude) under human authorization on the owner's
hardware; every decision and mistake is journaled. Licensing: MIT (base model MIT; molt's
original work MIT; per-artifact licensing table in the
[dataset card](https://huggingface.co/datasets/SEBK4C/molt-ornith-eval)).
