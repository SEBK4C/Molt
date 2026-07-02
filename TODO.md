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
- **NEVER** kill running `llama-server` (Nemotron PID 3339, port 9001) or `llama-swap` (PID 1770,
  :8080). GPU-needing steps: (a) poll `nvidia-smi` + wait for llama-swap ttl idle-unload via
  `runner/gpu_lock.sh wait-idle`, or (b) run degraded CPU-only (`-ngl 0`) when disk/CPU-bound
  (imatrix, KLD-base qualify). Record which path was taken in the journal/log.
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

- **D1 [in-progress]** `huggingface-cli download deepreinforce-ai/Ornith-1.0-397B --revision 5e3e761811e804c295c1d3c0ce68b21da6154209 --local-dir /mnt/proxmox/llm-serve/models/ornith-397b/hf-bf16`
  via `scripts/download_397b.sh` (retry loop ×200, resumes on rerun; Xet storage backend active).
  tmux: `molt:dl` · pane PID 73373 (also `notes/logs/molt-dl.pid`) · log: `notes/logs/molt-dl.log`
  Started 2026-07-02 ~02:29 local. Progress: `du -sb /mnt/proxmox/llm-serve/models/ornith-397b/hf-bf16`
  vs **793633331312 B** expected (exact, from hf-tree.json).
  est: measured by dl-watch 2026-07-02 02:45Z: ~97 MB/s avg (85/794 GB = 10.7%) → ETA ~04:45Z.
  Rate history: notes/logs/dl-watch.log.
- **D1.w [in-progress]** Babysitter subagent watches the download (rate/ETA → `notes/logs/dl-watch.log`,
  restarts the retry script if it dies, runs D2 verify on completion, updates D1/D2 lines here).
  Session-scoped: if this line is stale (no dl-watch.log updates for >1 h and download still
  running), a successor instance re-adopts the watch itself per resume.md §2.
- **D2 [blocked: D1]** Verify download: `.venv/bin/python scripts/verify_download.py` — count +
  per-file sizes vs `/mnt/proxmox/llm-serve/models/ornith-397b/hf-tree.json` (snapshot @ pinned
  revision), sha256 of every LFS file with `--deep` (~1–2 h). Babysitter runs both on completion.
  Deep verify REQUIRED before HG2 deletion; shallow suffices to start P1 (convert crashes loudly
  on corrupt safetensors, and deep runs in parallel anyway).
- **D3 [in-progress]** Auto-chain trigger: tmux `molt:chain` pane PID 126556 waits for the
  download COMPLETE marker, then runs `scripts/post_download_chain.sh` (P1→P4) with 3 attempts,
  10 min apart (each attempt re-gates on shallow verify). Log notes/logs/molt-chain.log.
  So P1–P4 need NO human/agent action tonight; P5 stays gated on HG4.

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
- **HG2 [HUMAN]** Any deletion > 50 GB. First expected instance: delete
  `/mnt/proxmox/llm-serve/models/ornith-397b/hf-bf16` (794 GB) ONLY after BOTH
  `scripts/verify_download.py --deep` passed AND P1 Q8_0 verified (tokenize sanity + smoke).
  Paste-ready: `rm -rf /mnt/proxmox/llm-serve/models/ornith-397b/hf-bf16`  — NOT before.
- **HG3 [HUMAN]** Create `~/.config/molt/env` with `HF_TOKEN=` (fine-grained: read + write
  SEBK4C namespace + Inference Endpoints admin), `ANTHROPIC_API_KEY=`. Download currently rides
  the cached `~/.cache/huggingface/token`; HG1 endpoint + HF uploads need the env file.
- **HG4 [HUMAN — REQUIRED for P5]** Free the GPUs. CONFIRMED 03:00: llama-swap config gives
  `Nemotron-Cascade-30B` **`ttl: 0` → it NEVER idle-unloads**; `gpu_lock.sh wait-idle` alone can
  never succeed while it's resident. Options (human's call): temporarily set a ttl / unload via
  llama-swap admin, or stop llama-swap + Nemotron for the session window. The molt side needs
  nothing else — runners already wait-and-never-kill.
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

- **P1 [blocked: D2]** Q8_0 convert → models/Ornith-Q8_0.gguf (~420 GB, est 4–10 h) + tokenize
  sanity + ctx32k exact token count. PERMANENT artifact — never delete.
- **P2 [blocked: P1, SK-F1]** imatrix → models/imatrix-agentic.dat. Script auto-picks -ngl 15
  (GPUs idle) vs -ngl 0 (degraded CPU path, allowed per bootstrap; recorded in log). est 2–8 h.
- **P3 [blocked: P1, SK-F2]** KLD base → models/kld-base.out (-ngl 0 ok). est 1–6 h.
- **P4 [blocked: P2]** Baseline quant via render_quant_cmd → models/ornith-molt-000.gguf. est 1–3 h.
- **P5 [blocked: P4 + HG4 (GPUs — Nemotron ttl:0 never self-unloads)]**
  `./scripts/phase0_epsilon.sh` — 3× full S (resumable per run), ε=2σ → harness/epsilon.txt,
  journal, FINAL manifest freeze, verify green. est 3× ~1 h once GPUs are free.
- **P6 [blocked: P5]** Pre-flight per REQUIREMENTS checklist + `git checkout -b molt/<date>` —
  research session may start (successor switches modes per resume.md §4).

## Notes / decision log

- 2026-07-02: `Ornith-1.0-35B-*`/9B GGUFs in models/ornith/ confirmed present and DIFFERENT from
  target; untouched. 397B is the target per bootstrap §1 — do not rescale spec to 35B.
- 2026-07-02: root `score.py` will move to `harness/score.py` (its `H`-relative prompt/ref paths
  require living inside harness/). After the move, CLAUDE.md command block updated (INF5).
- 2026-07-02: refs strategy — nested/tau/evalplus/bfcl refs are ground-truth-derivable without
  FP8 endpoint (spec-derived args / hand-authored terminal states / exec tests / upstream BFCL
  answers). HG1 endpoint upgrades bfcl+nested refs to FP8-behavioral goldens + supplies imatrix
  self-traces + secret split. ε/P5 therefore NOT blocked on HG1.
