# molt TODO — single source of truth for cross-session state

Last updated: 2026-07-02 03:15 local by bootstrap agent (session 1) — skeleton COMPLETE,
committed as d3a827b; download + auto-chain running detached. See notes/bootstrap-2026-07-02.md
for the session summary + HUMAN command block.
**Update states the moment they change.** A fresh instance with zero chat history resumes from
this file + `notes/` alone (see `resume.md`): reconcile every claim here against disk/processes
first, trust disk over checklist.

States: `[pending]` `[in-progress]` `[blocked: <on-what>]` `[done]` `[HUMAN]` (prepare, NEVER execute).

## Standing constraints (verbatim from bootstrap, do not re-litigate)

- Target = `deepreinforce-ai/Ornith-1.0-397B` BF16 originals. The 35B/9B GGUFs in
  `/mnt/proxmox/llm-serve/models/ornith/` are a **different model** — never touch, never delete.
  All 397B artifacts stage under `/mnt/proxmox/llm-serve/models/ornith-397b/`.
- **NEVER** write weights/GGUF to the root fs (119 GB free). Everything large → `/mnt/proxmox`.
- ~~NEVER kill running `llama-server`/`llama-swap`~~ **OVERRIDDEN BY OWNER 2026-07-02 ~06:25Z**
  (chat, verbatim: "You have higher privileges to touching the GPUs and shutting down LlamaSwap
  server temporarily while you train a new model. Nemotron is not the Priority, You are.").
  molt owns both 4090s for the pipeline/session window. `nemotron-proxy.service` (user unit
  running llama-swap) was STOPPED cleanly via `systemctl --user stop nemotron-proxy.service`
  (its llama-server child went down with it; VRAM verified drained to ~1 MiB both cards).
  **RESTORE when the session window ends: `systemctl --user start nemotron-proxy.service`**
  (see item X-restore below). Foreign processes that are not Nemotron/llama-swap remain
  untouchable; gpu_lock still waits rather than kills if anything grabs the cards.
- Never execute `[HUMAN]` items; keep their paste-ready commands fresh.
- `hf download` resumes natively: on restart rerun the same command, **never delete partials**.

## Environment facts (verified 2026-07-02 02:15–02:30)

- Host `llm-serve`, user `seb`. Repo = `/home/seb/Ai-projects/Molt`. `/home/seb/molt` is a
  **symlink** to the repo (created by INF3; `install_timer.sh`, SPEC, gpu-lock paths all assume it).
- Disk: `/` 119 GB free (code only); `/mnt/proxmox` 2.5 TB free (all model artifacts).
- GPUs: 2×RTX 4090 24 GB; both hold ~19 GB VRAM (Nemotron-Cascade via llama-server PID 3339,
  0% util, VRAM-resident). llama-swap PID 1770 config: `/home/seb/llama-swap-config.yaml`.
- CPU 32 threads, RAM 91 GB (~85 available). CUDA 12.8 toolkit at `/usr/local/cuda-12.8`.
- `huggingface-cli` 0.30.2 at `~/.local/bin/huggingface-cli` (no `hf` entrypoint on this box —
  use `huggingface-cli download`, same semantics). HF token cached at `~/.cache/huggingface/token`.
- Ornith-1.0-397B repo: public, not gated, **137 files, ~794 GB** (decimal, HF API tree sum),
  sha `5e3e761811e804c295c1d3c0ce68b21da6154209` (record! verify against this revision).
- User's own llama.cpp at `/home/seb/llama.cpp` (serves Nemotron) — do not modify; molt uses its
  own pinned build at `vendor/llama.cpp` (INF2).
- tmux: all molt jobs live in session `molt` (`tmux attach -t molt`). Pre-existing sessions
  Selfimprove/makemyrepo/setup are not ours — leave alone.

## D — Download (long pole, start first)

- **D1 [done]** `huggingface-cli download deepreinforce-ai/Ornith-1.0-397B --revision 5e3e761811e804c295c1d3c0ce68b21da6154209 --local-dir /mnt/proxmox/llm-serve/models/ornith-397b/hf-bf16`
  via `scripts/download_397b.sh` (Xet backend). **COMPLETE 2026-07-02T04:28:53Z** (log marker),
  ~2h00m wall, avg ~110 MB/s. On-disk file bytes = **793633331312** exact (shallow verify;
  du -sb incl. .cache metadata = 793633397162). Log: `notes/logs/molt-dl.log`;
  rate history: `notes/logs/dl-watch.log`.
- **D1.w [done]** Babysitter subagent completed 04:31Z: 12 watch rounds, zero restarts/stalls,
  ran shallow+deep verify (D2), updated D1/D2. Full rate history in `notes/logs/dl-watch.log`.
- **D2 [done]** Verify PASSED at both depths 2026-07-02: shallow 04:31Z (136 files /
  793633331312 B exact vs hf-tree.json); deep 04:31:33Z — sha256 of all 125 LFS files match
  their pinned LFS oids (`--deep --jobs 8`, ~75 s @ ~10 GB/s, `[deep-verify] EXIT=0`,
  log `notes/logs/verify-deep.log`; independent coreutils spot re-hash of model-00122 also
  matched). HG2/P1 deep-verify precondition satisfied.
  Deep verify REQUIRED before HG2 deletion; shallow suffices to start P1 (convert crashes loudly
  on corrupt safetensors, and deep runs in parallel anyway).
- **D3 [done→handed off to P1]** Auto-chain trigger FIRED ~04:31Z after the COMPLETE marker;
  shallow-verify gate passed; chain is executing in tmux `molt:chain`
  (log notes/logs/molt-chain.log). P1–P4 need NO human/agent action; P5 stays gated on HG4.

## INF — Infrastructure (unblocks everything else)

- **INF1 [done]** uv venv at `.venv` + deps incl. torch 2.12.1+cpu. Log `notes/logs/molt-env.log`
  ends `[setup_env] OK`. Rerun `scripts/setup_env.sh` any time (idempotent).
- **INF2 [done]** Pinned llama.cpp at `vendor/llama.cpp`, commit `4fc4ec5541b243957ae5099edb67372f8f3b550e`
  (`vendor/PIN`). VERIFIED by hand 02:35: `--spec-type` incl. `draft-mtp` in llama-server;
  `--tensor-type pat=type` in llama-quantize; arch `qwen35moe` in llama-arch.cpp (llama.cpp's
  name for HF `qwen3_5_moe`); `convert_hf_to_gguf.py` registers `Qwen3_5MoeForConditionalGeneration`
  with MTP head BUNDLED by default (no --mtp/--no-mtp flags needed at P1; `--mtp` would split the
  head to a separate draft GGUF — a possible Tier-A experiment later).
  NOTE: the two "WARNING: --spec-type/--tensor-type NOT in --help" lines at the end of
  notes/logs/molt-lcpp.log are FALSE ALARMS — a `grep -q`+pipefail SIGPIPE artifact, fixed in
  scripts/build_llamacpp.sh; ignore them.
  Post-build sanity (P-chain precondition): `vendor/llama.cpp/build/bin/llama-server --help | grep -q spec-type`
  and confirm qwen3_5_moe arch listed in convert script / server supports the 35B GGUF load CPU-only.
- **INF3 [done]** Symlinks: `/home/seb/molt` → repo; repo `models` → `/mnt/proxmox/llm-serve/models/ornith-397b`.
  (So SPEC paths `models/Ornith-Q8_0.gguf` etc. resolve AND land on the big disk. install_timer.sh
  paths now valid.)
- **INF4 [done]** `prepare.sh` rewritten as thin idempotent orchestrator over scripts/
  (layout symlinks → build → env → detached download → corpora → tests+provisional manifest;
  `bash -n` clean). Old monolith superseded.
- **INF5 [done]** `CLAUDE.md` state+commands updated; `.gitignore` added (.venv, vendor tree
  minus PIN, notes/logs, locks, regenerable corpora outputs; models symlink + harness/build/cache
  ARE committed — cache is frozen-slice provenance, 744 KB).
- **INF6 [done]** `scripts/verify_download.py` — count+size vs hf-tree.json; `--deep` sha256s
  every LFS file against its oid (threaded).
- **INF7 [done]** `prompts/resume.md` created (copy of resume.md; install_timer's molt_tick.sh
  reads this path).
- **INF8 [done]** `scripts/post_download_chain.sh` (P1→P4: check-before-do, .part+rename,
  nice/ionice, GPU-vs-CPU path auto-choice recorded, per-step logs) and
  `scripts/phase0_epsilon.sh` (P5: 3× full S — resumable, ε=2σ → harness/epsilon.txt, journal
  entries, FINAL manifest freeze, verify green). Both `bash -n` clean; wired into prepare.sh.

## SK — Skeleton (buildable now, no download needed)

### SK-A runner/  — ALL DONE 02:40 (tested where testable without a model)
- **SK-A1 [done]** `runner/gpu_lock.sh` — flock `/home/seb/molt/.gpu.lock` (= repo/.gpu.lock via
  symlink, gitignored); `status|wait-idle [timeout]|with-gpus <cmd…>|with-lock <cmd…>`. wait-idle
  polls nvidia-smi until both GPUs < 1500 MiB (env MOLT_GPU_IDLE_MB) — NEVER kills anything.
- **SK-A2 [done]** `runner/run_tierA.sh <exp_id> [--full] [--gguf p]` — manifest verify → vendor
  llama-server + `serve/current.args` on :9021 under with-gpus → /health wait (30 min cap, emits
  G2-fail verdict JSON if load dies) → score.sh (lite default) → kills only the server it started.
- **SK-A3 [done]** `runner/run_tierB.sh <exp_id>` — render from `recipes/current.yaml` → nice+
  ionice llama-quantize to models/…gguf.part → atomic rename → run_tierA --full on the candidate.
  Quantize deliberately does NOT hold the GPU lock (pipelines with Tier-A evals per SPEC §3);
  check-before-do skips existing outputs. Ratchet keep/reset decision stays with the session agent.
- **SK-A4 [done]** `runner/score.sh <exp_id> [--lite] [--gguf p] [--server url] | --verify-only`
  — wraps .venv python harness/score.py; default gguf from `serve/current.gguf`; verdict tee'd to
  notes/logs/score-<exp>.json; exit 2 propagates manifest tamper.
- **SK-A5 [done]** `runner/journal.sh` — stdin/arg JSON → jq validate (object + id + tier) →
  flock O_APPEND write to experiments.jsonl. Append-only by construction.

### SK-B recipes/ + serve/  — ALL DONE 02:40
- **SK-B1 [done]** `recipes/baseline.yaml` (git mv from root, paths via `models/` symlink) +
  `recipes/current.yaml` copy; `serve/current.args` (SPEC §6 seed, `--spec-type draft-mtp` left
  commented until first live A/B); `serve/current.gguf` pointer file (seed: models/ornith-molt-000.gguf);
  `recipes/imatrix.yaml` (Tier-C corpus mix spec, public-data fallback v1).
- **SK-B2 [done]** `runner/render_quant_cmd.py` — YAML → shell-quoted `llama-quantize
  --allow-requantize --imatrix … --tensor-type '<pat>=<type>' … in out.part <FALLBACK> <n> && mv`.
  Validates types against known ggml set, regexes compile, duplicate patterns rejected. Unit-tested.
  Unit-tested against baseline.yaml (exact expected command fixture).

### SK-C harness/ referee — ALL DONE 02:45 (54/54 tests green)
- **SK-C1 [done]** `harness/score.py` (git mv from root, fully implemented): G2 /health gate added,
  four `check()` suites (bfcl AST-canonical match incl. `__any_of__`/ABSENT alternates + strict/any
  order; tau terminal-state deep-equal via `harness/tau_env.py` canned-script driver — PERMISSIVE
  tools + policy-in-system-prompt so violations mutate state and fail; evalplus sandboxed exec
  pass@1: subprocess -I, rlimits CPU/AS/FSIZE/NOFILE, tmpdir, `unshare -r -n` netns when available;
  nested-json canonical re-serialize → deep-equal). `--verify-only` flag. Tool-call extraction
  handles both `message.tool_calls` and `<tool_call>` XML-in-content. deep_eq: bool≠int, int==float
  numerically, str never coerces. Per-case exceptions count as fails, never crash the eval.
  Weights/gates EXACT per SPEC §4: 0.45/0.25/0.20/0.10; size≤121 GB, decode≥8, prefill≥250.
- **SK-C2 [done]** `harness/tests/` — 54 tests: bfcl 14, tau 10, evalplus 10, nested 12,
  render+manifest 8 (known-pass + known-fail + malformed each). `.venv/bin/python -m pytest
  harness/tests/ -q` → 54 passed in 3.3 s (02:45Z).

### SK-D harness/prompts + refs — ALL DONE 03:05 (every suite round-trip-validated)
- **SK-D1 [done]** `harness/prompts/smoke.json` — 20 hand-written prompts (math/reasoning/code/
  JSON/unicode/tool-call/long-gen; all `expect_no_nan`).
- **SK-D2 [done]** `harness/prompts/ctx32k.txt` — 156 KB deterministic doc (~39K tok est) via
  `harness/build/build_ctx32k.py` (seed 20260702). Exact token count: measure once a GGUF exists
  (`llama-tokenize --show-count`) — see P5-pre below.
- **SK-D3 [done]** `harness/build/build_nested.py` → prompts/nested.json, 100 cases, 10 families
  ×10 (deep_uniform/deep_mixed/escapes incl. control chars + U+2028/29/zwsp/NFD, unicode_keys,
  unicode_values, wide_64_args, big_numbers >2^53, floats, empty_structures, lookalike_keys
  cyrillic/greek) + refs/nested.json (SPEC-DERIVED — prompt demands exact args; not FP8-blocked).
  Deterministic rebuild verified (sha match). max_tokens 2048/case.
- **SK-D4 [done]** `harness/refs/README.md` — layout, agent-forbidden notice, FP8 upgrade path
  (`<suite>.fp8.json` written NEXT TO derived refs; promotion = human decision + re-freeze + re-ε).
- **SK-D5 [done]** `harness/build/build_bfcl.py` — BFCL v4 from gorilla@main
  (simple_python 120 + parallel 90 + irrelevance 90 = 300; raw files cached in
  harness/build/cache/). Weighted round-robin order → eval-lite prefix(50) = 20/15/15.
  Upstream ground_truth → `__any_of__`/ABSENT grammar; dotted fn names sanitized to underscores
  in tools AND refs. VALIDATED: 300/300 synthesized-perfect answers pass check_bfcl,
  210/210 corrupted fail, irrelevance behaves.
- **SK-D6 [done]** `harness/build/build_tau.py` — 40 episodes (retail 22 / airline 18): cancel-ok
  ×5, cancel-must-refuse ×4, address-change ×4 (unicode addresses), damaged-item refund-vs-escalate
  ×5, exchange ×4, flight-change ×5 (incl. basic-fare must-refuse), cancel-refund-arithmetic ×5
  (flex/economy/basic), baggage ×4, bundled ×4. Refs generated by applying intended ops through
  tau_env itself (engine/ref can't drift; builder asserts no intended op errors).
- **SK-D7 [done]** `harness/build/build_evalplus.py` — HumanEval+ **v0.1.10** (exact SPEC version),
  164/164 problems, plus_input capped at 30/problem (logged, 0 inputs dropped). Expected outputs
  precomputed from canonical solutions; refs embed self-contained sandbox test scripts.
  VALIDATED: 25/25 canonical solutions pass through check_evalplus, broken candidate fails.

### SK-E manifest
- **SK-E1 [done]** `harness/manifest.py` (`--write [--provisional] | --verify`, detects
  MODIFIED/MISSING/UNTRACKED). PROVISIONAL manifest written 03:10 over 30 files (code + prompts +
  refs + tests + build/cache provenance). `runner/score.sh --verify-only` GREEN; tamper drill
  (byte appended to smoke.json) correctly exit-2'd, restore green again.
- **SK-E2 [blocked: Phase 0]** FINAL freeze happens inside `scripts/phase0_epsilon.sh` AFTER
  ε is written (epsilon.txt must be inside the frozen set; refs promotions from HG1, if any,
  land before that). Until then the provisional manifest is authoritative.

### SK-F corpora (needed for P2/P3)
- **SK-F1 [done]** (v1) `corpora/imatrix.txt` = 16.0 MB: glaive 6.7 + local-code 5.3 (vendor
  llama.cpp + repo sources — fallback) + synthetic tool-syntax 4.0 (held-out seed 20260702+555).
  DISCOVERY 03:00: `Salesforce/xlam-function-calling-60k` AND `bigcode/the-stack-smol` are
  **gated** → HUMAN gate HG6; after HG6, rerun both builders for the richer v2 mix
  (pre-P2 = free swap; post-P2 = Tier-C-style imatrix redo). Log notes/logs/molt-corpora.log.
- **SK-F2 [done]** (v1) `corpora/kld_heldout.txt` = 1.99 MB, disjoint by construction (same
  shuffle seed, imatrix from front / heldout from back, hard-asserted; two assert-failures on
  pool sizes were fixed by enlarging pools — front slices stay deterministic).

## HG — HUMAN gates (prepared, NEVER executed by the agent)

- **HG1 [HUMAN]** HF Inference Endpoint for FP8 golden refs + ~5 M tok self-traces.
  Paste-ready (spends ~$95–145 at ~ $23.5/h × 4–6 h — verify current pricing):
  `set -a; source ~/.config/molt/env; set +a; .venv/bin/python scripts/hf_endpoint_goldens.py --confirm-spend`
  Safe previews: `--dry-run` (prints call+cost) or `--mock <url>`. Outputs go to `refs_fp8/`
  (never overwrites harness/refs) + `corpora/fp8_traces.jsonl`; endpoint pause+delete in finally.
  - **HG1-prep [done]** script written + 3 mock tests green
    (`.venv/bin/python -m pytest scripts/test_endpoint_mock.py -q`): mock goldens for all 4
    suites, refuse-without---confirm-spend, dry-run cost print.
- **HG2 [HUMAN]** Any deletion > 50 GB. Two queued candidates:
  (a) the defective first convert (421 GB), safe to delete as soon as the fixed canonical
      Ornith-Q8_0.gguf passes its tokenize sanity:
      `rm /mnt/proxmox/llm-serve/models/ornith-397b/Ornith-Q8_0.BAD-phantom-mtp.gguf`
  (b) the BF16 snapshot (794 GB) — deep verify ALREADY PASSED 04:31Z, so this is safe once the
      fixed Q8_0 also passes sanity (it is the requant source thereafter):
      `rm -rf /mnt/proxmox/llm-serve/models/ornith-397b/hf-bf16`
- **HG3 [HUMAN]** Create `~/.config/molt/env` with `HF_TOKEN=` (fine-grained: read + write
  SEBK4C namespace + Inference Endpoints admin), `ANTHROPIC_API_KEY=`. Download currently rides
  the cached `~/.cache/huggingface/token`; HG1 endpoint + HF uploads need the env file.
- **HG4 [done — CLEARED BY OWNER 2026-07-02 ~06:25Z]** Owner granted molt the GPUs and
  authorized temporarily stopping llama-swap. Executed: `systemctl --user stop
  nemotron-proxy.service` (Restart=always does NOT resurrect a manual stop); VRAM drained.
  P5 is no longer HUMAN-gated. NEW pinned obligation:
  - **X-restore [pending — after session window]** `systemctl --user start nemotron-proxy.service`
    to bring llama-swap + Nemotron back. Do this whenever molt is idle for an extended period.
- **HG5 [HUMAN]** `./install_timer.sh` + phase-lock first start at the rate-limit reset
  (5 h cadence successor instances). Prereqs INF3+INF7 are done; timer scripts land in
  runner/molt_tick.sh + systemd user units.
- **HG6 [HUMAN]** Accept gated-dataset terms on the HF account (browser, logged in as the
  token owner): https://huggingface.co/datasets/Salesforce/xlam-function-calling-60k and
  https://huggingface.co/datasets/bigcode/the-stack-smol → then rerun
  `.venv/bin/python corpora/build_imatrix_corpus.py && .venv/bin/python corpora/build_kld_heldout.py`
  (before P2 if possible; after P2 it's a Tier-C-style imatrix redo).

## P — Post-download chain (ALL ENCODED in scripts — run top-to-bottom as each unblocks;
every step: check-before-do → *.part → atomic rename → notes/logs/)

**P1–P4 = one command once D2 passes** (CPU/disk only, no GPU dependency; safe to launch
detached and rerun): `tmux new-window -t molt -n chain 'cd /home/seb/Ai-projects/Molt && ./scripts/post_download_chain.sh 2>&1 | tee -a notes/logs/molt-chain.log'`

- **P1 [in-progress — REDO with --no-mtp]** First convert (04:31–05:02Z, 31 min, 421.5 GB,
  1098 tensors) produced an UNLOADABLE file: config declares `text_config.mtp_num_hidden_layers=1`
  but the BF16 repo ships NO mtp.* weights → convert wrote `block_count=61` +
  `nextn_predict_layers=1` with zero blk.60 tensors → `missing tensor 'blk.60.attn_norm.weight'`
  (chain attempts 2–3 failed the same way; watcher exhausted). FIX running since ~05:2xZ:
  `scripts/fix_p1_reconvert.sh` in tmux `molt:chain` (log notes/logs/molt-chain.log +
  p1-convert-nomtp.log): builds llama-tokenize (was missing from targets — fixed in
  build_llamacpp.sh), re-converts with `--no-mtp` (~31 min), asserts block_count=60 + no nextn
  keys, tokenize sanity + ctx32k count, parks the bad file as
  `Ornith-Q8_0.BAD-phantom-mtp.gguf` (deletion = HG2), promotes the fixed file to canonical
  name, then execs post_download_chain.sh (P1 skips, P2→P4 proceed). Disk fine (1.4 T free).
  PERMANENT artifact once good — never delete.
- **P2 [in-progress — GPU-assisted, attempt 3]** imatrix → models/imatrix-agentic.dat.
  Attempt 1 (05:55): SPEC seed `--chunk 512` = FROM-chunk (skips input!) + uncapped 9650 chunks.
  Attempt 2 (06:01, CPU-only `--chunks 600`): measured **421 s/pass → ETA 17.5 h** — CPU-only
  P2 is NOT viable on this box (experts stream fine at 3.7 GB/s; 32 cores are the ceiling).
  Attempt 3 (06:19): GPU non-expert offload alone did NOT help — bottleneck is expert-weight
  STREAMING, not compute (411 GB ≫ 85 GB page cache; default ubatch 512 ⇒ every 2048-token
  batch streams the full model 4× ≈ 1.6 TB/pass, matches measured 421 s/pass + 86%-of-one-core
  fault-wait profile). Attempt 4 fixed it: `-b 4096 -ub 4096` (--no-warmup was invalid for
  imatrix and cost one aborted relaunch) ⇒ **MEASURED 142.4 s/pass, ETA 1 h 11 m** (was 17.5 h
  — 14.7×). Running since ~06:57Z, saves every 10 chunks, partial-data warnings 95–99% are
  normal MoE coverage. 240 chunks = ~123K calibration tokens.
  LESSON (applies to P3/P5/serving): on this box, wall-time for any prefill-heavy job over the
  Q8 master is (streams × 411 GB ÷ ~4 GB/s); maximize ubatch to minimize streams.
  SPEC hygiene note stands: SPEC §2's `--chunk 512` and `-ngl 15` are both wrong for a 421 GB
  model (15 full layers ≈ 105 GB > VRAM) — human may want to amend SPEC.
- **P3 [blocked: P1, SK-F2]** KLD base → models/kld-base.out (-ngl 0 ok). est 1–6 h.
- **P4 [blocked: P2]** Baseline quant via render_quant_cmd → models/ornith-molt-000.gguf. est 1–3 h.
- **P5 [blocked: P4 only — AUTO-RUNS]** Chain now execs `scripts/phase0_epsilon.sh` after P4
  (HG4 cleared; escape hatch: MOLT_NO_AUTOP5=1). 3× full S (resumable per run), ε=2σ →
  harness/epsilon.txt, journal, **FINAL manifest freeze**, verify green. WALL-TIME UNKNOWN with
  thinking enabled (watch-item). NOTE: a `molt:guard` handover retires the pre-edit chain
  instance after P2's rename (old bash had stale script buffered: slow P3 flags, no auto-P5)
  and takes over — see "[handover]" marker in molt-chain.log.
  ⚠ LOOP DISCIPLINE AFTER P5 RUNS: harness/ is then FROZEN — self-improvement ticks must never
  edit harness/ again without a deliberate re-freeze + full Phase-0 re-run (ε depends on refs).
- **P6 [blocked: P5]** Pre-flight per REQUIREMENTS checklist + `git checkout -b molt/<date>` —
  research session may start (successor switches modes per resume.md §4).

## Loop (session-scoped)

- A 30-min self-improvement cron (`7,37 * * * *`, job d5d63a29, prompt "Self-improvement
  goal.") runs in the CURRENT session only (in-memory; gone if the session exits — do not
  expect it in a fresh instance). Each tick: reconcile TODO vs disk, then fix the
  highest-value defect found. Tick 1 (05:18–05:3xZ) caught the P1 phantom-MTP defect above.
  Tick 2 (05:49–05:5xZ): hardened `g45_throughput` — timings-absent responses previously
  zeroed prefill → guaranteed false G5 fail; now falls back to a measured probe
  (`cache_prompt:false`, max_tokens=1) + derived decode. Provisional manifest regenerated
  (still 30 files), 54/54 tests, verify-only green. Re-convert ~88% at tick end.
  Tick 3 (06:37–06:5xZ): (a) NEW `scripts/serve_stack_smoke.sh` — served the 9B GGUF CPU-only
  on :9022 and drove it through the referee's own chat/extraction helpers: tool_calls shape ✓,
  extraction ✓, finish_reason ✓, timings present ✓ (g45 primary path confirmed live); reusable
  before any risky serving change. (b) It CAUGHT the thinking-model budget bug: `<think>` eats
  small max_tokens → empty content → suites would have scored ~0 artificially at Phase-0. All
  suites regenerated with thinking-aware budgets (nested/evalplus 4096, tau/bfcl 2048, smoke
  1024); g3 empty-rule = no content AND no tool_calls. Manifest re-frozen (provisional), 54/54.
  WATCH-ITEM for Phase-0: full-S wall time with thinking enabled is unmeasured — if it blows
  the 45–60 min budget at ≥10 t/s, consider `--reasoning-budget` or parallel slots (-np) as
  Tier-A-era changes. (c) Diagnosed+fixed imatrix streaming geometry (see P2).

## Notes / decision log

- 2026-07-02: `Ornith-1.0-35B-*`/9B GGUFs in models/ornith/ confirmed present and DIFFERENT from
  target; untouched. 397B is the target per bootstrap §1 — do not rescale spec to 35B.
- 2026-07-02: root `score.py` will move to `harness/score.py` (its `H`-relative prompt/ref paths
  require living inside harness/). After the move, CLAUDE.md command block updated (INF5).
- 2026-07-02: refs strategy — nested/tau/evalplus/bfcl refs are ground-truth-derivable without
  FP8 endpoint (spec-derived args / hand-authored terminal states / exec tests / upstream BFCL
  answers). HG1 endpoint upgrades bfcl+nested refs to FP8-behavioral goldens + supplies imatrix
  self-traces + secret split. ε/P5 therefore NOT blocked on HG1.
- 2026-07-02 06:1x: **Storage topology verified (user question).** /mnt/proxmox = LVM pve-root
  on nvme0n1p3 = Samsung 9100 PRO 4TB. Direct-IO measured: **11.1 GB/s read, 7.6 GB/s write**
  (read bench ran WHILE imatrix streamed 3.7 GB/s). The sda 5TB / sdb 12TB spinners are unmounted
  and unused by molt. Historical slow rates were soft ceilings: download 110 MB/s = network;
  P1 convert 220 MB/s = single-threaded python quant compute (disk ~idle); imatrix 3.7 GB/s =
  32-core MoE forward compute. SPEC §6's 14 GB/s SSD-streaming serving assumption ≈ holds
  (11 GB/s measured). Repo itself also lives on the NVMe (/home/seb/Ai-projects is on pve-root).
- 2026-07-02 05:2x: **MTP is unavailable for Ornith-1.0-397B, period.** Config declares
  `mtp_num_hidden_layers: 1` but the mtp.* weights are absent from BOTH the BF16 repo (weight
  index grep: 0 hits) and the FP8 repo (index grep: 0 hits). Corrects INF2's earlier "MTP
  bundled by default" note (that described convert's default BEHAVIOR, not shipped weights).
  Consequences: SPEC §3's `draft-mtp` A/B is off the table; serve/current.args documents
  model-free `--spec-type ngram-*` as the replacement Tier-A speculative-decoding direction;
  P1 conversion permanently carries `--no-mtp`.
