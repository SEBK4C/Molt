# TEACHER-PROTOCOL.md — teacher-guided recovery loop (operative instruction file)

You are a **teacher-loop** instance of the molt autoresearch ratchet (karpathy/autoresearch
pattern, same discipline as `program.md`). The recipe search is COMPLETE and locally optimal
at 2.41 bpw (docs/RESEARCH_REPORT.md). Your mission is the next program: **recover the two
measured deficits of Featherweight-v0** — nested-JSON verbatim fidelity (0.72) and code
robustness (0.96–0.99, unstable tail) — using **GLM-5.2 as a teacher**, without breaking
anything the ratchet already banked (S reference 0.9258, ε 0.005253).

Read first, in order: `TODO-OFFSITE.md` (live state) → `docs/RESEARCH_REPORT.md` §3 (the
failure catalog — do not re-pay for falsified ideas) → this file. Reconcile all three against
disk before acting. Journal to `notes/teacher-journal.jsonl` (same fields as
experiments.jsonl; ids `texp###`); `experiments.jsonl` belongs to the closed local program —
append-only history, never write it.

## 1. Actors

- **Teacher — GLM-5.2** via Fireworks: model `accounts/fireworks/routers/glm-5p2-fast`,
  OpenAI-compatible chat completions, 131K max_tokens. Key: `FIREWORKS_API_KEY` in
  `~/.config/molt/env` (mode 600, NEVER committed; rotate after program end — it transited
  chat once). Call ONLY through `scripts/teacher_client.py` (disk cache + usage metering →
  notes/logs/teacher-usage.jsonl). Measured 2026-07-05: the router exposes raw *thinking in
  content* — always request generous max_tokens (≥4096 for structured work) and extract the
  final answer mechanically (fenced block / last JSON object), never trust prefix text.
- **Student** — `models/ornith-molt-000.gguf` (= Featherweight-v0, sha 1499c2f2…) served by
  vendor llama.cpp with `serve/current.args`.
- **Referee — UNCHANGED**: the frozen harness + `runner/score.sh`. Manifest-verify before
  every scoring run; exit 2 = tamper = auto-fail. The teacher NEVER enters the referee: all
  keep/discard decisions come from the same mechanical suites (AST/exec/deep-equal).

## 2. Lanes (inherits molt ownership rules)

May edit: `corpora/teacher/*`, `recipes/current.yaml` (Tier T-B only), `serve/current.args`
+ `serve/templates/*` (Tier T-A only), `notes/teacher-*.{md,jsonl}`, `scripts/teacher_*`.
MUST NOT touch: `harness/` (frozen), `runner/`, `harness/refs/` (never read),
`experiments.jsonl`, `models/Ornith-Q8_0.gguf` + imatrix masters (requant SOURCES — new
imatrix files get NEW names, e.g. `models/imatrix-teacher-v2.dat`).

**GPU preflight every tick**: molt no longer owns the GPUs by default (session window
closed; `systemctl --user is-active nemotron-proxy` may be active). If Nemotron is up:
queue GPU work, run API/data work only, and ping the owner ONCE for a GPU window. Never
stop nemotron-proxy without fresh owner authorization in-session. `runner/gpu_lock.sh`
semantics apply — wait, never kill.

## 3. Contamination rule (absolute — this is the anti-reward-hack for the SFT era)

The teacher must NEVER see `harness/prompts/*` or `harness/refs/*`. Generation templates
derive from the family *specifications* (the builder code's docstrings in `harness/build/`
describe the 10 nested families and suite shapes — reading builder SPECS is allowed, reading
emitted prompts/refs is not) with **fresh random seeds** and disjoint surface values.
Additionally: hold out 2 of the 10 nested families (rotate per experiment) from all training
data; a keep that improves trained families but not held-out families is memorization →
DISCARD regardless of S.

## 4. Experiment tiers

- **T-A — elicitation (≈$0, hours)**: system-prompt/template scaffolds baked into the chat
  template (a legal serving-config surface): JSON-echo discipline ("repeat keys verbatim,
  integers as-is"), self-check instructions inside the reasoning budget. Hypothesis: part of
  the 0.72 is elicitation, not capacity. Scored with eval-lite (r=0.968 vs full), keeps
  confirmed full-S. Honest floor: 10 nested cases are harness-dead (empty_structures);
  S_max ≈ 0.99.
- **T-B — teacher-authored calibration → imatrix v2 (API $ + ~6 h local, GPU window
  needed)**: the teacher writes *input* corpora (tool-call-heavy, nested-JSON-heavy, code)
  matched to Ornith's deployment distribution — the corpus RECIPE (mix weights, family
  emphasis, length profile) is the search variable. Then: imatrix (`-b/-ub 4096`, measured
  law: streams × 411 GB ÷ 4 GB/s) → requant → full S. One variable per corpus change.
- **T-C — teacher-distilled SFT corpus for LoRA recovery (build NOW, train LATER — offsite,
  owner-budget-gated ~$1.5K)**: (prompt, ideal-response) pairs for nested/code repair.
  EVERY sample passes mechanical validation before entering the corpus: JSON samples must
  survive parse → canonical re-serialize → deep-equal round-trip against the prompt's
  demanded args; code samples must pass their own generated tests in the harness's sandbox
  pattern (subprocess -I, rlimits). Reject-sample until clean; store provenance per line
  (teacher model id, template id, seed, validator verdicts) in `corpora/teacher/sft-*.jsonl`.
  Deliverable even before training: the validated corpus itself publishes to
  `SEBK4C/molt-ornith-eval` as a community artifact.

## 5. Ratchet mechanics (unchanged)

ε = 0.005253; keep iff hard gates pass AND S > S_best + ε (plus the held-out-family check in
§3). Lite-primary screening sanctioned (r = 0.968): lite for keep/discard triage, full S to
confirm keeps. One mutation per experiment; `git commit` keeps, `git reset --hard` discards
(commit BEFORE mutating). Journal the mechanism, not the outcome. Budgets: teacher API spend
metered per call; **$25 cumulative cap without a fresh owner ping** (usage jsonl is the
ledger); GPU wall-time per T-B experiment capped at 8 h.

## 6. Phase plan (loop picks the topmost unblocked item)

1. **P0 — baseline + cheapest hypothesis**: preflight (GPU state, student serves, referee
   verify-only green) → texp001: JSON-echo scaffold in the chat template (T-A). This is the
   control every later result is read against.
2. **P1 — validator infrastructure**: `scripts/teacher_client.py` cache/metering; nested +
   code validators as standalone modules (`scripts/teacher_validate.py`) with fixture tests
   (known-good passes, corrupted fails — same round-trip validation style as the harness
   builders).
3. **P2 — T-B corpus search**: 2–3 corpus recipes max per GPU window, adjudicated by full S.
4. **P3 — T-C SFT corpus build**: target 10–30K validated pairs; publish; hand the training
   spec (base model, LoRA rank/targets = routed-expert down-projections first, lr schedule,
   eval plan) to the owner as the budget-call artifact.
5. **P4 — write-up**: append teacher-program findings to docs/RESEARCH_REPORT.md (§5) with
   the same falsification honesty.

## 7. Tick discipline (30-min loop)

Each tick: reconcile (disk > journal > this file) → if a long job is running (imatrix,
requant, eval), check verdicts/timeouts, act only on state changes, keep the tick terse →
else pick next queue item, execute ONE step, journal, commit. Failures emit verdicts, never
silence. Update THIS FILE in the same commit whenever reality contradicts it. Push
notification to owner on: keeps, discards with surprising mechanisms, budget threshold hits,
and GPU-window requests — never routine ticks.
