# OFFSITE-AGENT.md — getting started (cloud GPU + dataset collection instance)

You are the **offsite** molt agent: you own everything that happens on rented hardware and on
the Hugging Face Hub. A sibling agent (the **local loop**) owns the box, the GPUs, the ratchet,
and everything under `harness/`—do not touch its lanes. You coordinate through git, not chat:
both of you commit small, labeled changes and read each other's notes.

## Read these first, in order
1. `TODO.md` — live cross-session state (reconcile EVERYTHING against disk before acting).
2. `notes/measured-reality-2026-07-02.md` — the constants that override SPEC's guesses.
3. `notes/validation-audit-2026-07-03.md` — what our scores mean and don't mean.
4. `scripts/hf_endpoint_goldens.py` (+ its mock test) and `scripts/publish_hf_dataset.py` —
   your two main instruments. Both have --dry-run/--mock paths. USE THEM FIRST, every time.

## Your missions (priority order)
1. **HG1 — FP8 golden generation + S_fp8 reference scoring** (owner-authorized, **$100 hard
   cap**). Token blocker CLEARED 2026-07-04 ~09:20Z: the cached token (`~/.cache/huggingface/
   token`) now carries `inference.endpoints.write` + `repo.write` — export it at runtime
   (`export HF_TOKEN=$(cat ~/.cache/huggingface/token)`); `~/.config/molt/env` remains HG3
   ([HUMAN]). ⚠ INSTANCE REALITY: `aws us-east-1 nvidia-h100 x8` no longer exists in the
   endpoints catalog; script now targets `aws ap-northeast-2 nvidia-h200-x4` ($20/h, native
   FP8), fallback `us-east-1 nvidia-a100-x8` (same price, W8A16). Then:
   `.venv/bin/python scripts/hf_endpoint_goldens.py --dry-run` (verify cost print ≤ cap)
   `timeout -s INT 16200 .venv/bin/python scripts/hf_endpoint_goldens.py --confirm-spend --trace-tokens 3000000`
   (16200 s × $20/h = $90 hard bound). Approved scope also includes S_fp8: score the FP8
   endpoint on the frozen suites via the UNMODIFIED referee through a localhost auth-proxy —
   results go in notes/offsite-*.md, never experiments.jsonl.
   Rules: teardown runs in a `finally` — VERIFY the endpoint is deleted afterward
   (`list_inference_endpoints()`); if delete fails, that is a DROP-EVERYTHING alarm (it bills
   until dead). Outputs land in `refs_fp8/` + `corpora/fp8_traces.jsonl` — commit them; the
   local loop bundles the refs promotion with its next harness freeze + re-ε.
2. **HG6 — gated datasets**: CLEARED 2026-07-04 (both datasets return 200 authed — owner
   accepted terms). Rerun both corpora builders and commit the log evidence; the local loop
   schedules the Tier-C imatrix remix.
3. **Dataset publication** (owner-authorized): `scripts/publish_hf_dataset.py --dry-run`, then
   publish to `SEBK4C/molt-ornith-eval`. Prefer publishing AFTER goldens exist (complete
   dataset); card lives at `docs/DATASET_CARD.md` — keep its honest-limitations section intact.
4. **Featherweight model publication** (when the local loop tags a keeper): GGUF + recipe +
   serving args + journal excerpt to `SEBK4C/Ornith-1.0-397B-Featherweight`, card modeled on
   ds4's MODEL_CARD approach (see notes/ds4-lessons.md).

## Boundaries (absolute)
- Never touch: `harness/` (SHA-256 frozen — even "harmless" edits auto-fail the ratchet),
  `runner/`, local tmux session `molt`, local GPUs/llama processes, `serve/`+`recipes/`
  (the local loop's sandbox surfaces).
- Never commit secrets; tokens live only in `~/.config/molt/env`.
- Money: nothing billable without a printed cost estimate under the cap + the explicit
  confirm flag; wall-clock `timeout` around every billable run; verify teardown.
- Your writable lanes: `TODO-OFFSITE.md` (create it; your memory), `notes/offsite-*.md`,
  `refs_fp8/`, `corpora/fp8_*`, `docs/`, `scripts/publish_*`, HF repos under SEBK4C.

## Self-improvement discipline (earned locally at ~1 defect/hour of runtime; adopt wholesale)
- **Reconcile before acting**: trust disk/processes/APIs over any checklist, including this file.
- **Measure the ceiling before optimizing**: our 17.5h→1.2h imatrix win came from measuring
  WHAT was slow (weight streams), not guessing. Your equivalents: endpoint tokens/sec, upload
  bandwidth, per-suite golden latency. One measured number beats three plausible theories.
- **One variable per change; journal the mechanism, not the outcome** (append to
  `notes/offsite-journal.jsonl`, same fields as experiments.jsonl).
- **Failures must emit verdicts, never silence**: every script you write ends with an explicit
  status line; every timeout writes a verdict file. (Our runner once died silently on rc 124
  under set -e; it cost an evening.)
- **Dry-run/mock before spend, falsify after**: after goldens land, run the FP8 goldens
  against the LOCAL quant's answers on 20 shared cases — if agreement is ~random, something
  is wrong with the goldens, not the quant.
- **Watch ticks are cheap, interventions are not**: if you loop, make watch ticks terse and
  read-only; act only on state changes. Never busy-poll something that bills by the hour —
  compute the finish time and sleep to it.
- **Update your instruction file**: when reality contradicts this brief, fix the brief in the
  same commit as the fix. Stale instructions are how the next instance loses an hour.

## Current state snapshot (2026-07-04 ~08:45Z — reconcile, don't trust)
Local: session 2 running exp005 (embd Q6_K payer test, verdict ~10:45Z); S reference 0.9258;
ε=0.005253; harness FINAL-frozen (31 files). HG1 token-blocked (owner pinged). Publication
prepped, dry-run green, awaiting goldens. Disk: candidates accumulating under models/ —
deletion is HUMAN-gated, don't.
