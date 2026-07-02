# Measured reality vs SPEC assumptions — 2026-07-02 bootstrap

For the session planner: these are MEASURED constants from Phase-0 gate tuning on the real
baseline artifact (ornith-molt-000.gguf, 119.5 GB, 2.41 BPW). Where they contradict SPEC,
trust these. Every number has a commit/log trail (TODO.md + notes/logs/).

## Serving (config: -ngl 99 --n-cpu-moe 52 -ts 52,8 -b/-ub 8192 --reasoning-budget 1024, 4 slots)

| Quantity | SPEC assumed | MEASURED |
|---|---|---|
| decode @32K, single stream | 10–20 t/s | **12.3–13.5 t/s** (stable across configs) |
| prefill @38K | ≥250 t/s easily | **129→211 saturated CPU-side; needs GPU expert layers to clear 250** |
| VRAM at final config | — | GPU0 16.6 GB / GPU1 18.6 GB (24 GB cards) |
| aggregate eval throughput | — | ~28 s/case at 4 parallel slots (bfcl-class cases) |

- Prefill law: cost = full expert-set streams per ubatch; -ub is the lever (129@2048 → 211@8192),
  then only GPU expert placement helps. NEVER --n-cpu-moe without a matching -ts (OOM lesson).
- Thinking: UNBOUNDED by default and the model will think 9K+ chars on trivial prompts.
  --reasoning-budget 1024 is part of the serving config; hold it constant across compared
  configs or S values are not comparable.

## Eval wall-time (drives ALL tier budgets)

| Eval | SPEC budget | MEASURED/projected |
|---|---|---|
| full S (604 cases, 4 workers) | 45–60 min | **~5–6.5 h** |
| eval-lite (smoke+nested+50 bfcl) | ~8 min | **~60–80 min** |
| Tier A total | 20 min | ~1.5–2 h realistically |

Session implication: a night is ~3–4 Tier-A experiments + at most 1 Tier-B requant scored with
eval-lite, NOT SPEC's 8–12 A + 3–4 B. The highest-value early experiments are the ones that
make serving faster (they compound by making all later evals cheaper): expert-layer placement
sweeps, -ub, reasoning-budget, speculative ngram-*.

## Facts that changed the plan

- MTP head: declared in config, weights NEVER published (BF16 + FP8 both) → --no-mtp convert
  is mandatory; draft-mtp impossible; try --spec-type ngram-* instead.
- The model is TEXT-ONLY in GGUF (vision tower not converted). All evals are text — fine.
- Quantize --tensor-type: FIRST regex match wins, in order; patterns must be non-overlapping
  (never .*gate.*; shared experts are *_shexp).
- Quant pipeline speed: P1 convert 31 min; P4 requant ~57 min (llama-quantize, 32 threads) —
  Tier-B cost is ~1 h quant + eval, NOT 1–3 h quant.
- imatrix: 240 chunks/123K tok in ~65 min GPU-assisted with -b/-ub 4096 (--chunk is FROM-chunk,
  never use as size!).
- Storage: everything on the Samsung 9100 PRO (11.1 GB/s read / 7.6 GB/s write measured).
  Page-cache warmth matters: first-touch prefill reads ~2× slower than steady state.
- G4/G5 probes: warm-up pass + cache_prompt=false measured pass (KV cache would fake it).
- Early quality signal: bfcl rolling pass-rate ~90% at 2.41 BPW (n=75, run 1 in flight) —
  the fragile-set Q8 floor + agentic imatrix appear to be holding.
