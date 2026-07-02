You are bootstrapping molt from spec stage to runnable. Input: notes/abort-2026-07-02.md.
Do NOT run a research session. Your job is to make one possible.

## 0. TODO.md is the product
Create TODO.md at repo root immediately: convert the abort note's ordered list into a checklist.
Each item: state [pending|in-progress|blocked|done|HUMAN], dependencies, est. duration, and for
in-progress items the tmux window + PID + log path. Append every new work item you discover.
TODO.md + notes/ are the only cross-session memory — a fresh instance with zero chat history must
be able to resume from them alone. Update states the moment they change, not in a batch at the end.

## 1. Decisions already made — do not re-litigate
- Target is deepreinforce-ai/Ornith-1.0-397B (BF16 originals, ~807 GB). The Ornith-1.0-35B GGUFs
  under models/ornith/ are a different model: leave them untouched, note them in TODO, stage the
  397B under /mnt/proxmox/llm-serve/models/ornith-397b/. NEVER write weights or GGUF outputs to
  the root filesystem (119 GB) — everything large goes to /mnt/proxmox.
- Never kill running llama-server / llama-swap processes (Nemotron PID or otherwise). GPU-needing
  steps either (a) poll nvidia-smi and wait for llama-swap ttl idle-unload, or (b) run degraded
  CPU-only (-ngl 0) when the step is disk/CPU-bound anyway (imatrix and KLD-base qualify: prefill
  streams from SSD; slower but valid). Record which path you took in the journal.

## 2. Start the download FIRST (long pole, needs no GPU)
In a detached tmux window (`molt-dl`):
  hf download deepreinforce-ai/Ornith-1.0-397B \
    --local-dir /mnt/proxmox/llm-serve/models/ornith-397b/hf-bf16
hf resumes partial downloads natively — on any restart, rerun the same command, never delete
partial files. After completion, verify: file count + per-file sizes against the repo tree
(hf api), sha256 where LFS metadata provides it. Mark in-progress in TODO with window+log.

## 3. While it streams, build the missing skeleton (dependency order)
a. runner/: gpu_lock.sh (flock /home/seb/molt/.gpu.lock + wait-for-idle poll),
   run_tierA.sh, run_tierB.sh, score.sh (env setup + harness/score.py wrapper +
   --verify-only mode), journal.sh (append-only experiments.jsonl writer).
b. recipes/baseline.yaml (from SPEC §recipe) -> copy to recipes/current.yaml;
   serve/current.args (SPEC §6 seed); runner/render_quant_cmd.py.
c. harness/: implement the four check() suites in score.py —
   bfcl: AST-parse tool_calls, canonicalize, structural match vs ref;
   tau: terminal-state dict match after canned-script episode;
   evalplus: sandboxed exec (subprocess, rlimits, tmpdir, no net) pass@1;
   nested-json: json.loads -> canonical re-serialize -> deep-equal vs ref.
   Unit-test each checker against >=5 hand-written fixtures (known-pass + known-fail +
   malformed output) BEFORE marking done. Fixtures live in harness/tests/.
d. harness/prompts/ builders: smoke.json (20), ctx32k.txt, nested.json generator (100 cases:
   deep nesting, escapes, unicode keys, 64-arg calls). Cases can be built now; refs that require
   the FP8 model are blocked on the HUMAN gate below — structure refs/ so they drop in later.
e. harness/manifest.py (sha256 manifest writer/verifier). Do NOT write the final manifest until
   refs/ is populated; write a provisional one covering code+prompts so --verify-only works.

## 4. HUMAN gates — prepare, never execute
Mark [HUMAN] in TODO.md with the exact command ready to paste:
- HF Inference Endpoint spin-up for golden refs + FP8 trace generation (spends GPU credits):
  write scripts/hf_endpoint_goldens.py fully, tested against a mock, cost estimate included.
- Any deletion >50 GB (e.g. hf-bf16 after Q8_0 verification).
- Stopping/reconfiguring llama-swap or any service to free GPUs.

## 5. Post-download chain (encode in TODO now, execute when unblocked)
convert_hf_to_gguf.py --outtype q8_0 -> Ornith-Q8_0.gguf (CPU+disk only, no GPU gate)
-> imatrix (CPU-only fallback allowed) -> KLD base -> baseline quant -> Phase-0: score baseline
3x -> harness/epsilon.txt. Each step: check-before-do (skip if valid output exists), write to
*.part then atomic rename, log to notes/logs/.

## 6. Exit condition
When every non-HUMAN item is done, blocked, or running detached: write notes/bootstrap-<date>.md
(status table, what's running with ETAs, exact HUMAN commands pending) and exit cleanly. Do not
idle-wait on the download.
