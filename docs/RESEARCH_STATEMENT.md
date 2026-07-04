# molt — research statement (one page)

## Problem

Frontier-class open-weight models (300–700B MoE) exist, but almost nobody can run them: they
are published for datacenter inference and evaluated with datacenter assumptions. The gap is
not just quantization — it is **trustworthy** compression: knowing what a 2-bit derivative
preserved, what it lost, and being able to prove both without taking anyone's word for it.

## What molt is

An autoresearch-style **ratchet loop** (after karpathy/autoresearch) that searches quantization
recipes and serving configurations for `deepreinforce-ai/Ornith-1.0-397B` (512-expert MoE,
MIT) on one commodity box — 2×RTX 4090, 90 GB DDR5, one Gen5 SSD — under a referee the search
agent cannot influence:

- **Frozen behavioral harness** (SHA-256 manifested; tamper ⇒ auto-fail): function-calling
  (BFCL-derived, AST-checked), multi-turn tool episodes (deterministic environment, terminal-
  state checked), code (HumanEval+ sandboxed execution), and a nested-JSON fidelity stress
  suite. No LLM judges anywhere; every check is mechanical.
- **Measured noise floor**: ε = 2σ from triple replication (0.0053); nothing is "kept" unless
  it beats the best score by more than the noise. Lite/full eval correlation (r = 0.968) is
  itself measured, enabling a 3× cheaper screening tier.
- **Append-only experiment journal**: every hypothesis, verdict, and mechanism-lesson —
  including the falsified ones — is committed. The negative results (e.g., "last-layer
  down-projection promotion does nothing"; "Q6_K embeddings measurably damage token fidelity
  at 248K vocab") are as reproducible as the positive ones.

## Result to date (v0, ~60 hours of autonomous operation)

A **119.5 GB, 2.41 bits/weight** derivative of a 397B model — 15% of original size — scoring
**S = 0.9258** on the behavioral suite: multi-turn tool use at ceiling (240/240 episodes),
function-calling 91%, code 98%, with degradation concentrated measurably and *only* in
verbatim token-precision tails (nested-JSON 0.70–0.73). Serving: 18.5 t/s decode, 717 t/s
prefill at 38K context, on hardware costing less than one datacenter GPU.

## Why fund it

1. **Democratization with receipts**: the artifact, the recipe, the harness, the noise floors,
   and the journal are all published — anyone with two consumer GPUs can reproduce the scores.
2. **A reusable methodology**: the referee/ratchet design (frozen manifest, mechanical checks,
   ε-gated keeps, saturation-aware interpretation) transfers to any model/hardware pair; the
   validation audit documents its limits as carefully as its results.
3. **A costed roadmap** (budget table): free rungs already in flight (speculative decoding via
   ngram and a same-family 9B drafter); **$100** — FP8 golden references + the true degradation
   anchor S_fp8 (endpoint hours); **~$1.2K** — EAGLE-3 draft head training (est. 2–3× decode,
   compounding into research rate); **~$1.5K** — LoRA quality-recovery pass targeting the one
   degraded capability lane; **~$3K** — generalize the pipeline to a second model family to
   demonstrate transfer.

## Assets

Model: `SEBK4C/Ornith-1.0-397B-Featherweight` (tag `featherweight-v0`). Dataset + harness +
journal: `SEBK4C/molt-ornith-eval`. Source: the molt repository (full git history, including
every mistake). Licensing: MIT throughout molt's original work; derived suites carry their
upstream licenses (BFCL: Apache-2.0; HumanEval+: MIT/Apache-2.0); goldens/traces derive from
MIT-licensed Ornith outputs; gated third-party corpora (xlam, the-stack-smol) are used locally
for calibration only and never redistributed.
