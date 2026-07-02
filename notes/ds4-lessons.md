# Lessons from antirez/ds4 (DwarfStar) — read 2026-07-02

molt's SPEC descends from ds4's approach; the README confirms several of our bets and
re-prioritizes one experiment. (ds4 = self-contained DeepSeek-V4 engine, Metal/CUDA, 2-bit
MoE quants, SSD streaming, official-logit validation.)

## Direct validation of molt decisions
- **Baseline recipe is ds4's shipping recipe**: routed experts only; up/gate IQ2_XXS, down
  Q2_K; shared experts/projections/routing untouched. His words: the 2-bit quants "are not a
  joke... call tools in a reliable way." Our bfcl ~90% @2.41 bpw reproduces this on qwen35moe.
- **MTP**: with real MTP weights, ds4 measured "at most a slight speedup, not a meaningful
  generation-speed win" (experimental, correctness-gated). Ornith's unpublished MTP head is
  therefore a near-zero loss. Stop mourning it; ngram-* remains optional curiosity.
- **Thinking off for speed benches** (--nothink) — parallels our --reasoning-budget 1024 as a
  serving-config decision.
- **SSD as a speed spectrum, not a cutoff** ("model needs to fit RAM" → continuous speed
  levels) — the same philosophy behind our mmap expert streaming; he goes further (KV cache
  as "a first-class disk citizen" — llama-server's --slot-save-path is the mainline analog,
  interesting for long agent sessions, not for the eval loop).

## Re-prioritization
- **Tier-B queue #1 should be `ffn_down_exps` last-6-layers → Q4_K**: ds4 SHIPS this exact
  variant (`q2-q4-imatrix`) as a preferred download for 96/128 GB machines — pre-validated
  on a sibling MoE. (+~3 GB, well under our 121 GB gate at 119.5.)

## To adopt at ship time (post-first-keeper)
- Repo hygiene: per-concern sub-READMEs (imatrix dataset, quality-testing, speed-bench),
  QA_BEFORE_RELEASES.md (we have session_preflight.sh for sessions; releases need their own),
  MODEL_CARD.md in-repo, honest speed tables + charts in README.
- Quality testing framing: score local GGUFs against official-implementation continuations
  (our KLD-base/--kl-divergence vs Q8 master = same idea; USE it as a Tier-B regression
  signal, not just a logged diagnostic; FP8-endpoint goldens (HG1) = the stronger version).
- His imatrix dataset README (gguf-tools/imatrix/dataset/) is worth a read before any Tier-C
  corpus remix.
