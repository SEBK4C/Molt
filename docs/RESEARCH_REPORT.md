# molt: a 397B MoE at 2.41 bits/weight on two consumer GPUs — what worked, what didn't, and what it costs to go further

**TL;DR** — We compressed `deepreinforce-ai/Ornith-1.0-397B` (512-expert MoE, MIT) from 794 GB
to **119.5 GB (2.41 bits/weight)** and served it at **18.5 tok/s decode / 717 tok/s prefill**
on one machine: 2×RTX 4090 (48 GB VRAM), 90 GB DDR5, one Gen5 SSD. On a frozen, mechanically-
checked behavioral suite it scores **S = 0.9258**: function-calling 91%, multi-turn tool
episodes 100% (240/240), code 98%, nested-JSON fidelity 72%. An autonomous ratchet loop then
searched recipes and configs for two days under a tamper-proof referee — one config improvement
survived; **every recipe change was falsified**. This report documents both directions with
equal care, because the negative results are the expensive part and you should not pay for
them twice.

Assets: model + llamafile [`SEBK4C/Ornith-1.0-397B-Featherweight`](https://huggingface.co/SEBK4C/Ornith-1.0-397B-Featherweight) ·
harness/goldens/journal [`SEBK4C/molt-ornith-eval`](https://huggingface.co/datasets/SEBK4C/molt-ornith-eval) ·
method: [karpathy/autoresearch](https://github.com/karpathy/autoresearch)-style ratchet; recipe
family: [antirez/ds4](https://github.com/antirez/ds4).

---

## 1. Headline results

| Metric | Value | How measured |
|---|---|---|
| Size | 119.5 GB (15% of BF16) | 2.41 BPW; routed experts IQ2_XXS/Q2_K, imatrix-tuned |
| S (behavioral, weighted) | **0.9258** | frozen suite, 3× replicated, ε = 0.0053 |
| — BFCL v4 slice (300) | 0.903–0.910 | AST match, four independent runs spread 270–273/300 |
| — τ multi-turn (40 episodes) | **1.000, every run** | deterministic env, terminal-state equality |
| — HumanEval+ (164) | 0.96–0.99 | sandboxed exec pass@1 |
| — nested-JSON stress (100) | 0.70–0.73 | canonical deep-equality — the discriminating canary |
| Decode / prefill @38K ctx | 18.5 / 717 tok/s | warm cache, `cache_prompt=false` measured pass |
| KLD vs 8.5-BPW master | median **0.00075**, p99 0.34 | 2-bit damage = thin tail, not broad drift |
| Eval noise floor ε | 0.0053 (full), 0.041 (lite) | 2σ from replication; lite/full r = 0.968 |

The picture across instruments is consistent: **the RL'd agentic core survives 2.41 BPW
essentially intact; the loss concentrates in a ~1–5% tail of precision-critical tokens**,
visible as verbatim-fidelity errors on pathological JSON, not as reasoning or tool-selection
failures.

## 2. What worked (do copy these)

1. **The asymmetric-crush recipe** (ds4's family, independently reproduced on a second MoE
   architecture): quantize ONLY the routed experts (97.4% of params) — gate/up `IQ2_XXS`,
   down `Q2_K`, with an agentic-mix imatrix; protect everything else (router, attention/GDN,
   embeddings, shared experts) at Q8_0. The protected 2.6% is what makes 2.41 BPW behave.
2. **Expert placement with an explicit tensor-split**: `-ngl 99 --n-cpu-moe 50 -ts 50,10`
   puts 10 expert layers (~18 GB) + all lean tensors on the GPUs, saturating 48 GB VRAM.
   Measured ladder: 8/9/10 GPU expert layers → 17.8/18.3/18.6 tok/s (diminishing).
3. **Large micro-batch is the prefill lever**: on a bigger-than-RAM MoE, prefill cost =
   (number of full expert-weight streams) — `-ub 8192` took prefill from 129 → 211 tok/s
   CPU-side, then GPU expert layers took it to 717. The same law cut imatrix generation from
   a projected 17.5 h to 65 min (`-b/-ub 4096`).
4. **Bounded thinking as a serving-config decision**: `--reasoning-budget 1024`. The model
   otherwise thinks unboundedly (9.3K characters on a trivial prompt) and evaluation/latency
   become unbounded with it. Below 1024 is a measured no-op (thinking rarely reaches 512).
5. **The referee design**: SHA-256-manifested harness (it caught its own maintainer twice),
   mechanical checkers only (AST/exec/deep-equal, zero LLM judges), measured noise floor
   before any keep/discard decision, append-only journal with a mechanism-lesson per verdict.
6. **A same-family 9B as a negative control**: scoring a small distill on the identical suite
   exposed which suites actually discriminate (only nested-JSON) — and cost nothing.

## 3. What did NOT work — documented so you don't pay for it

### 3.1 Speculative decoding INVERTS on CPU-resident MoE (do not retry naively)
- `--spec-type ngram-simple`: decode **−10%** (16.6 vs 18.5 tok/s). Think-stream prose is not
  self-repetitive; drafting overhead beats acceptance.
- Same-family 9B drafter (`draft-simple`, IQ4 on GPU, quantized draft-KV): decode **−34%**
  (12.2 tok/s), single-stream, despite the drafter matching the target on tool-calling.
- **Mechanism**: verifying k drafted tokens batches k tokens through the target — but each
  token routes to its own top-10 of 512 experts, so batch-verify streams up to k× the expert
  weights of sequential decode. The entire amortization premise of speculation inverts when
  expert weights live in RAM/SSD. **This also invalidates EAGLE/Medusa-style draft heads for
  this hardware class** — we cancelled a planned ~$1.2K EAGLE-3 training on this result.
  (Corollary: Ornith's own MTP head is unreleased in both repos — convert with `--no-mtp`,
  a default convert writes phantom metadata and produces an unloadable GGUF.)

### 3.2 Recipe search at 2.4 BPW is locally optimal — three surfaces falsified
- **Last-layer down-projection promotion** (blk.58–59 Q2_K→Q4_K, +1.04 GB): S unchanged
  (nested +1 case, inside noise). The damaged-token tail is NOT last-layer-concentrated.
- **Activation energy does not predict behavioral value**: imatrix energy puts 53.7% of all
  down-proj energy in layer 59 — i.e. the falsified experiment above WAS the energy-optimal
  choice. Ranking layers by imatrix magnitude and promoting the top is a trap.
- **Gate/up promotion** (top-8 energy layers IQ2_XXS→IQ2_XS, +1.04 GB): S −0.0006, nested
  flat. The third and last in-budget surface.
- **Embedding/output shrink Q8_0→Q6_K** (−0.62 GB): nested −3–4 cases with everything else
  flat. At 248K vocab, **embedding precision is load-bearing for verbatim token fidelity**
  — the Q8 floor is a measured requirement, not caution.

### 3.3 Evaluation traps (these silently zero or inflate your scores)
- **Tool schemas ARE grammars** under llama-server: a permissive schema
  (`additionalProperties: true`, no properties) compiles to a grammar that only admits `{}` —
  our nested suite scored 0/25 with the model *forced* to emit empty arguments. Schemas must
  mirror the expected payload. Related: `{"anyOf": []}` (empty array schema) 400s the request.
- **Saturation**: a 9B distill TIES the 397B on our BFCL slice; BFCL/τ-style suites certify
  "competent tool-caller", not model quality. Only token-fidelity stress discriminated.
  Never present suite scores as capability claims.
- **Cold-cache throughput lies**: first-touch prefill is ~3× slower than steady-state; KV
  prompt-cache fakes it in the other direction. Measure warm with `cache_prompt=false`.
- **Temp-0 replication measures infrastructure noise** (batched fp ordering), not sampling
  noise — our ε doubled as a batching-noise meter. Budget accordingly; near-threshold "wins"
  are noise.
- Tooling semantics that cost us hours: llama-imatrix `--chunk` means *from*-chunk (skips
  input!); `--n-cpu-moe` without a matching `--tensor-split` OOMs one GPU (expert layers
  concentrate on the tail device); quantize `--tensor-type` is first-match-wins in argument
  order (never use over-broad patterns like `.*gate.*` — it would swallow `ffn_gate_exps`).

## 4. Next steps, with costs

| Step | Cost | What it buys | Status |
|---|---|---|---|
| FP8 golden generation + **S_fp8** (score the unquantized model on this exact suite) | **~$100** (4×H200 endpoint, ~4.5 h) | the true degradation number (today's 2–4% is an estimate); golden refs; distribution-matched trace corpus | blocked on an endpoint-quota request |
| imatrix v2 from FP8 self-traces (Tier C) | ~$0 local (needs the traces above) | reopens the recipe search legitimately — the current local optimum is conditional on public-data calibration | queued |
| Harness v2 freeze (fix 10 dead nested cases, harder τ episodes, per-case paired stats) | ~$0 + one re-calibration (~16 h compute) | ~√2–2× more sensitive comparisons at identical eval cost | bundled with goldens promotion |
| LoRA recovery pass (train adapters on FP8 against self-distilled traces, merge, requant) | **~$1.5K** endpoint hours | the only surviving big-ticket quality play (EAGLE-3 cancelled by §3.1) — targets the nested tail directly | decision pending |
| Second model family end-to-end | ~$3K | demonstrates the methodology transfers | roadmap |

## 5. Reproduce / verify

Everything is deterministic or noise-floored: recipes, serving args, prompts, refs, journal,
and per-experiment verdicts ship in the dataset repo. Rebuild the quant from any Q8_0 master
with the recipe YAML; re-score with `runner/score.sh` (manifest-verified referee); compare
against `experiments.jsonl`. The 100-sample secret split is withheld by design.

*Research conducted by an autonomous loop (Claude) under human authorization, 2026-07-02 →
07-05: ~60 h wall, 14 journaled verdicts, 5 falsified hypotheses, 2 published artifacts, and
every mistake in the git history. Thanks: llama.cpp/GGML, antirez/ds4, karpathy/autoresearch,
DeepReinforce for MIT-licensed weights.*
