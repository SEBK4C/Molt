# molt — SPEC v0.1

Autoresearch-pattern ratchet loop that searches quantization recipes + serving configs for
`deepreinforce-ai/Ornith-1.0-397B` until the model is servable on the target box with minimal
degradation of tool-calling/reasoning behavior. Direct port of the karpathy/autoresearch contract
(three files, one metric, git ratchet, fixed budgets) with the train step replaced by a
quantize/serve/eval step.

---

## 0. Targets

| Constraint | Value |
|---|---|
| Host | llm-serve: 90 GB DDR5-6000 (dual channel, ~60–70 GB/s eff.), 2×RTX 4090 (48 GB), Samsung 9x0 Gen5 SSD 14 GB/s, 2.6 TB free |
| Artifact | GGUF ≤ 121 GB total; secondary: llamafile package (§8) |
| Hard gates | loads under llama-server; decode ≥ 8 t/s @ 32K ctx; prefill ≥ 250 t/s; no NaN/garbage on smoke set |
| Objective (maximize) | S — behavioral score on tool-calling + reasoning suite (§4) |
| Diagnostics (logged, not ratcheted) | KLD vs Q8, PPL, t/s @ {0, 32K, 128K}, VRAM/RAM residency split |

Model facts (from config, prior analysis): `qwen3_5_moe`, 60 layers, `full_attention_interval: 4`
→ 45 GatedDeltaNet linear-attn + 15 GQA full-attn (kv_heads=2, head_dim=256); 512 routed experts,
top-10, expert dims 4096×1024 → routed ≈ 386.5B / 397B (97.4%), non-expert ≈ 10.5B; vocab 248320;
262K ctx; MTP head available. KV @262K: ~7.9 GB FP16 / ~4 GB q8. DeltaNet state ~190 MB constant.
No custom engine needed — day-1 llama.cpp support incl. `--spec-type draft-mtp`.

Baseline recipe (search seed, ≈118–121 GB):
- `ffn_gate_exps`, `ffn_up_exps` → IQ2_XXS (66.4 GB)
- `ffn_down_exps` → Q2_K (41.3 GB); variant: last-6-layers Q4_K (+3 GB)
- `token_embd`, `output`, `attn_*`, `linear_attn_*`, `*gate*`, `shared_expert*`, vision → Q8_0/F16 (10.5 GB)
- Fragile-tensor set = DeepReinforce's own FP8 `ignore` list. Do not quantize below Q8.

---

## 1. Autoresearch contract, ported

autoresearch = {`prepare.py` immutable, `train.py` agent-owned, `program.md` human-owned, one
metric, fixed 5-min budget, git ratchet branch, keep iff metric improves}. molt maps:

| autoresearch | molt | Owner |
|---|---|---|
| `prepare.py` (data + eval, immutable) | `harness/` — eval suite, `score.py` referee, golden traces, prompts | human; **agent MUST NOT edit** (checksum-enforced) |
| `train.py` (agent sandbox) | `recipes/current.yaml` + `serve/current.args` — quant recipe (per-tensor-group type map, imatrix corpus mix) and serving config | agent |
| `program.md` | `program.md` — research directions, constraints, loop rules | human |
| 5-min train | tiered budgets (§3) — quantize is 1–3 h disk-bound, so budget by tier not uniform | fixed |
| val_bpb | S (§4), lexicographic after hard gates | fixed |
| branch `autoresearch/<tag>` | branch `molt/<yyyymmdd>` ; `experiments.jsonl` journal | fixed |

Ratchet rule: after an experiment, `score.py` emits `{gates: pass|fail, S, diagnostics}`. Keep
(commit recipe+args+journal entry) iff all gates pass ∧ S > S_best + ε. Else `git reset --hard`.
ε = eval noise floor, measured in Phase 0 (3× replication of baseline eval; ε = 2σ).

Known autoresearch failure mode carried over: ratchet forbids "worse-before-better" moves. Mitigation:
`program.md` permits *bundled* experiments (recipe + serving change in one commit) and a bounded
"exploration credit" — max 1 provisional keep per night at S > S_best − ε/2 if it frees ≥ 5 GB
(size buys future headroom for Q4_K promotions).

Anti-reward-hacking: agent never sees golden answers (harness drives the model over HTTP against
llama-server; prompts+refs live in `harness/`, SHA-256 manifest verified by `score.py` before every
scoring run; mismatch → experiment auto-fails). Held-out secret split scored only at session end.

---

## 2. Pipeline (one-time, before loop start)

```
P0  hf download deepreinforce-ai/Ornith-1.0-397B  (BF16, ~807 GB — NOT the FP8;
    convert_hf_to_gguf.py can't ingest compressed-tensors)
P1  convert_hf_to_gguf.py --outtype q8_0  → Ornith-Q8_0.gguf (~420 GB)
    (skip BF16 GGUF intermediate: saves 807 GB of staging)
P2  llama-imatrix on Q8_0, mmap'd from SSD. Prefill-only ⇒ each 512-tok chunk streams the
    model once: 420 GB / 14 GB/s ≈ 30 s/chunk × ~100 chunks ≈ 1 h per corpus.
    Corpus: agentic/tool-call mix (§5), not wikitext.
P3  KLD base: llama-perplexity --kl-divergence-base out.kld on Q8_0 over held-out traces (~1 h).
P4  First quant: llama-quantize --imatrix ... --tensor-type overrides per baseline recipe (1–3 h).
P5  Phase-0 referee calibration: score baseline quant 3× → ε; smoke-test serve config.
Disk peak: 807 (HF) + 420 (Q8) + 2×~121 (quants A/B) ≈ 1.47 TB < 2.6 TB. Keep Q8 forever
(imatrix + KLD reference + requant source); BF16 HF deletable after P1 if space pressure.
```

Golden references (unquantized behavior) — this is what the HF GPU credits are for (§REQUIREMENTS):
run `Ornith-1.0-397B-FP8` on a dedicated HF Inference Endpoint (8×H100 class) for a few hours to
(a) generate golden outputs for the behavioral suite, (b) sample ~50 M tokens of self-generated
agent traces for the imatrix corpus (distribution-matched calibration — strictly better than any
public dataset for an RL'd policy).

---

## 3. Experiment tiers + scheduler

Uniform 5-min budgets don't survive contact with a 121 GB quantize pass. Three tiers, each with a
fixed wall-clock budget; the agent interleaves so the disk-bound tier pipelines with GPU-bound eval:

| Tier | Mutates | Cost | Budget | Examples |
|---|---|---|---|---|
| A | `serve/current.args` only (fixed quant) | minutes | 20 min incl. eval-lite | `--n-cpu-moe N` sweep, layer split across both 4090s, `-fa`, KV q8_0 vs f16, `-ub`/`-b`, MTP on/off (`--spec-type draft-mtp`), `--override-tensor` placement regex |
| B | `recipes/current.yaml` → full requant | 1–3 h disk-bound + eval | 4 h | tensor-type map deltas (e.g. `ffn_down_exps` last-k layers → Q4_K; gate/up → IQ2_XS vs IQ2_XXS; per-layer mixes informed by imatrix activation stats), embed/output Q8_0 vs Q6_K |
| C | imatrix corpus mix | ~1 h imatrix + Tier-B requant | 6 h | corpus reweighting (tool-syntax-heavy vs code-heavy), chunk length 512 vs 2048 |

Overnight session ≈ 8 h → schedule: 3–4 Tier-B (pipelined: requant experiment N+1 runs while
experiment N is being evaluated on GPU — disk and GPU are disjoint resources) + 8–12 Tier-A + ≤1
Tier-C. Tier-A uses eval-lite (§4) for keep/discard; any Tier-A keep is re-confirmed with full S at
session end.

MTP note: A/B it under CPU-MoE offload specifically — verified draft batches amortize expert reads
from RAM/SSD, so it usually flips positive here (the Apple-GPU net-negative result does not transfer).

---

## 4. Metric

Hard gates (checked in order, any fail → discard):
```
G1 file size ≤ 121 GB            G4 decode ≥ 8 t/s @ 32K ctx (greedy, 512 gen)
G2 llama-server loads, no OOM    G5 prefill ≥ 250 t/s @ 32K
G3 smoke set: 20 prompts, no NaN/repetition-collapse/template breakage
```

S ∈ [0,1], weighted composite, all evaluated through llama-server with Ornith's own
`chat_template.jinja` (modified from stock Qwen — do not substitute), `--reasoning-parser qwen3`,
tool parser `qwen3_xml`:

```
S = 0.45 · BFCL-lite            # 300-sample stratified slice of BFCL v4: AST match, single+parallel+irrelevance
  + 0.25 · τ-lite               # 40 τ-bench retail/airline episodes, pass^1, multi-turn tool use
  + 0.20 · EvalPlus HE+ pass@1  # 164 problems, sandboxed exec
  + 0.10 · nested-JSON stress   # 100 internal prompts: deeply nested/unicode/escaped args —
                                #   the known qwen3.5 weak spot and the thing 2-bit kills first
```

eval-lite (Tier A) = smoke + nested-JSON + 50-sample BFCL slice + t/s probes; ~8 min.
Full S ≈ 45–60 min at ≥ 10 t/s decode.
Diagnostics per run: KLD vs Q8 (`llama-perplexity --kl-divergence` against P3 base file, prefill-only,
SSD-streaming ok), PPL on agent traces, per-tensor-group sizes, residency map, t/s @ 0/32K/128K.

Rationale for behavioral-primary, KLD-diagnostic: Ornith's RL'd tool policy is a narrow behavior;
perplexity/KLD under-detects its degradation. Weight the gate toward multi-turn tool syntax.

---

## 5. Calibration + eval data

| Purpose | Source | Size |
|---|---|---|
| imatrix corpus (P2, Tier C) | self-generated Ornith-FP8 agent traces (HF endpoint) + `Salesforce/xlam-function-calling-60k` + `glaiveai/glaive-function-calling-v2` + SWE-agent-style trajectories + 20% code (`bigcode/the-stack-smol` slices) | ~5–20 M tok |
| KLD held-out | disjoint slice of the same mix | ~2 M tok |
| BFCL-lite | `gorilla-llm` BFCL v4 data, stratified 300 | fixed, frozen in harness |
| τ-lite | sierra-research `tau-bench` retail+airline, 40 episodes, GPT-4-class user-sim replaced by canned scripts (determinism) | frozen |
| EvalPlus | HumanEval+ v0.1.10 | frozen |
| nested-JSON stress | generated once (deep nesting, escapes, unicode keys, 64-arg calls), goldens from FP8 endpoint | frozen |
| secret split | 100 mixed samples, scored end-of-session only | frozen, not in repo |

Freeze everything in `harness/` with a SHA-256 manifest at Phase 0. No live user-sim LLMs inside
the loop (nondeterminism breaks the ratchet); any LLM-judged item gets replaced by AST/exec checks.

---

## 6. Serving/placement plan (Tier-A search seed)

```
llama-server -m ornith-molt.gguf -ngl 99 --n-cpu-moe N -fa on \
  --cache-type-k q8_0 --cache-type-v q8_0 -c 131072 \
  --chat-template-file chat_template.jinja --reasoning-parser qwen3 \
  --jinja --spec-type draft-mtp   # A/B
```
- GPUs: non-expert weights + KV + scratch ≈ 16–18 GB; remaining ~30 GB VRAM = resident expert layers
  (tune N until VRAM full; llama.cpp layer-splits across both cards — no ds4 single-device constraint).
- RAM: ~80 GB of experts. SSD: residual few GB mmap'd (14 GB/s covers it).
- Decode model: active routed ≈ 7.55 B params/token × ~2.2 bpw ≈ 2.1 GB/token; ~70–75% CPU-resident
  → ~1.5 GB/token from RAM → 10–20 t/s expected on DDR5-6000 dual-channel. G4 = 8 t/s is the floor.
- Integration: llama-swap entry next to `DeepSeek-V4-Flash` (port assign, `gpu-exclusive` group,
  `checkEndpoint: /health` — llama-server has one, unlike ds4-server).

---

## 7. Loop session lifecycle

```
1. human: git checkout -b molt/<yyyymmdd>; start Claude Code in repo root, permissions off:
   "Read program.md and start tonight's session."
2. agent: verify harness manifest → read experiments.jsonl tail → plan night (tier mix) →
   for each experiment: mutate sandbox files → run runner script → score.py → keep/reset →
   append journal entry {id, tier, hypothesis, mutation diff, gates, S, diagnostics, decision, lesson}.
3. morning: human reads journal + staircase chart (analysis.ipynb port: S vs experiment index),
   promotes recipe, optionally edits program.md (the only human-tuned artifact), uploads keeper to
   HF SEBK4C/Ornith-1.0-397B-Featherweight with recipe.yaml + journal excerpt in the model card.
```

---

## 8. llamafile ("APE") packaging — end-of-project step, not in-loop

- llamafile = Cosmopolitan Libc APE wrapper around llama.cpp. It lags upstream llama.cpp;
  `qwen3_5_moe` support must exist in the llamafile release before packaging. Gate: check llamafile
  release notes; if absent, ship GGUF + pinned llama.cpp build, revisit.
- ≥ 4 GB embedding works via ZIP64 on Linux/macOS but a 121 GB single-file APE is hostile to
  distribution and mmap alignment; recommended shape: small APE binary + external weights
  (`./ornith.llamafile -m ornith-molt.gguf`), zipalign only the metadata.
- Package step: `llamafile-0.9.x` + `zipalign -j0` + embedded `.args` file carrying the converged
  Tier-A serving config and chat template.

---

## 9. Risks

- 512-expert/top-10 high-sparsity MoE at ~2.1 bpw: experts are only 12.6 M params each — less
  redundancy per expert to hide quant noise than DeepSeek V4's fatter experts. Expect the nested-JSON
  stress to be the first thing that cracks; that's why it's in S and in eval-lite.
- Eval noise vs ratchet: BFCL-lite/τ-lite at these sample sizes have σ ≈ 1–2 pts. ε from Phase 0 is
  mandatory; without it the ratchet keeps noise.
- Ratchet locality: no multi-step degradation-then-recovery. Bundling + exploration credit (§1) is a
  partial fix; accept that this finds a good recipe, not the optimal one.
- 90 GB RAM ceiling: requant passes and eval serving cannot overlap in RAM — the scheduler must
  serialize "quantize (disk+CPU)" with "serve (RAM-resident experts)" or run requant with
  `--allow-requantize` niced + mmap so the page cache yields to llama-server. Runner enforces a lock.
