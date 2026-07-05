---
license: mit
tags:
- function-calling
- tool-use
- quantization
- evaluation
- gguf
- llama.cpp
pretty_name: "molt: behavioral eval harness + goldens for 2-bit Ornith-397B"
---

# molt — a behavioral eval harness for extreme MoE quantization (Ornith-1.0-397B @ 2.41 bpw)

**molt** is an [autoresearch](https://github.com/karpathy/autoresearch)-style ratchet loop that
searches quantization recipes and serving configs for `deepreinforce-ai/Ornith-1.0-397B`
(512-expert qwen3.5 MoE) until it serves well on one specific consumer box: 2×RTX 4090,
90 GB DDR5, Gen5 SSD. This dataset is the frozen evaluation harness, golden references, the
research journal, and the documentation — published for community feedback.

**The model these numbers describe is published**:
[`SEBK4C/Ornith-1.0-397B-Featherweight`](https://huggingface.co/SEBK4C/Ornith-1.0-397B-Featherweight)
(119.5 GB GGUF + zero-install llamafile sidecar with the reference serving flags embedded).

**→ Full findings: [`RESEARCH_REPORT.md`](RESEARCH_REPORT.md) (in this repo).** The search
program is **complete** as of 2026-07-05: 14 journaled verdicts, one kept config improvement,
five falsified hypotheses. Highlights you should read before spending compute: speculative
decoding *inverts* on CPU-resident MoE (ngram −10%, model-drafter −34% — §3.1); imatrix
activation energy does not predict behavioral value (§3.2); embeddings must stay Q8 at 248K
vocab (measured, §3.2); and the recipe is locally optimal at 2.41 bpw under public-data
calibration — the next quality levers are the FP8 golden anchor (~$100), imatrix v2, and
LoRA recovery (~$1.5K), costed in §4.

## Headline result

A 119 GB / **2.41 bits-per-weight** GGUF of a 397B model that keeps its RL'd agentic core:

| Suite | Score @2.41bpw | Notes |
|---|---|---|
| BFCL v4 slice (300, AST match) | **0.90** | stratified single/parallel/irrelevance |
| τ-lite (40 multi-turn episodes) | **1.00** | deterministic env, policy adherence |
| HumanEval+ (164, sandboxed exec) | **0.98** | plus-inputs capped at 30/problem |
| nested-JSON stress (100) | **0.72** | the discriminating canary — where 2-bit bites |
| **S (weighted)** | **0.9258** | ε (noise floor, 3× replication) = 0.0053 |

Recipe: routed experts only (gate/up `IQ2_XXS`, down `Q2_K`, imatrix-tuned); router, attention,
GDN, shared experts, embeddings protected (Q8_0/Q6_K). Same asymmetric-crush family as
[antirez/ds4](https://github.com/antirez/ds4)'s DeepSeek quants — independently reproduced here
on a different MoE architecture.

## What's in this dataset

- `harness/prompts/` + `harness/refs/` — four frozen suites with mechanical checkers documented
  in the repo (AST/exec/deep-equal; **no LLM judges**; SHA-256 manifested in the source repo).
- `refs_fp8/`, `corpora/fp8_traces.jsonl` — FP8-endpoint golden outputs + self-generated agent
  traces (present after the golden-generation run).
- `journal/experiments.jsonl` + `journal/progress.png` — the append-only research journal:
  14 entries (3 ε-calibration baselines, 1 lite-tier calibration, 1 kept config, 5 falsified
  hypotheses, infra events), each with hypothesis, verdict, and a mechanism-lesson. Discards
  outnumber keeps 5:1 — that ratio is the point.
- `docs/` — measured-reality constants (what SPEC assumed vs what the hardware did),
  a validation audit (including where our own suite is saturated and why absolute scores
  should not be read as capability claims), and lessons taken from ds4.
- `recipes/`, `serve/` — the exact quant recipe and llama.cpp serving arguments.

## Honest limitations (read before citing numbers)

1. bfcl/τ here are **degradation tripwires, not capability meters** — a 9B distill ties the
   397B on the bfcl slice. Only the nested-JSON suite discriminates model quality.
2. Tool calls are grammar-constrained by llama-server from the schemas: malformed-JSON failure
   modes are masked by construction.
3. EvalPlus deviates from the official protocol (input cap + import header): relative use only.
4. Ten nested cases (empty_structures family) fail deterministically due to a known schema-
   generation bug — fixed in the builder, prompts regenerate at the next harness freeze.
5. ε is measured at temperature 0 and reflects batching nondeterminism, not sampling noise.

## Provenance / licensing (per artifact)

| Artifact | Derived from | License |
|---|---|---|
| `harness/prompts/bfcl.json`, `refs/bfcl.json` | gorilla-llm BFCL v4 data + possible_answers | Apache-2.0 (upstream), mapping code MIT |
| `harness/prompts/evalplus.json`, `refs/evalplus.json` | evalplus HumanEval+ v0.1.10 | MIT/Apache-2.0 (upstream) |
| `harness/prompts/{nested,tau,smoke}.json` + refs | original to molt | MIT |
| `refs_fp8/*.fp8.json`, `corpora/fp8_traces.jsonl` | outputs of MIT-licensed Ornith-1.0-397B-FP8 | MIT |
| `journal/`, `docs/`, `recipes/`, `serve/` | original to molt | MIT |
| xlam-function-calling-60k, the-stack-smol | **NOT included** — gated upstream; used locally for imatrix calibration only, never redistributed | n/a |

The secret held-out split is not published (by design).

## Feedback wanted

- Harder τ episodes (ambiguity, distractors) that stay deterministic — the current ones ceiling.
- Nested-JSON families that discriminate *between* 2-bit recipes, not just detect them.
- Independent replication of the S numbers via the source repo's `runner/score.sh`.

*Built by an autonomous research loop (Claude) under human authorization; every decision and
mistake is in the journal. The source repo (harness code, runners, full git history) accompanies
this dataset.*
