# molt bootstrap — 2026-07-02, session 1 (02:15–03:20 local)

Input: notes/abort-2026-07-02.md. Mission: make a research session possible (NOT run one).
Everything below is reconcilable against TODO.md (authoritative per-item state) + disk.
Committed as `d3a827b` on main.

## Status table

| Area | State | Evidence |
|---|---|---|
| D1 download 397B BF16 (794 GB) | **RUNNING** detached | tmux `molt:dl`; ~28% @ ~115 MB/s at 03:05Z; ETA ≈ 04:30Z; log notes/logs/molt-dl.log; watcher log notes/logs/dl-watch.log |
| D1.w babysitter subagent | RUNNING (session-scoped) | measures rate, restarts on death/stall, runs D2 verify on completion, updates TODO |
| D2 verify (count/size/sha256) | AUTO on completion | scripts/verify_download.py [--deep]; tree snapshot pinned @ rev 5e3e7618 |
| D3 auto-chain trigger | **RUNNING** detached | tmux `molt:chain` PID 126556 → launches P1–P4 after COMPLETE+verify |
| INF1 venv | done | .venv, torch 2.12.1+cpu; scripts/setup_env.sh idempotent |
| INF2 pinned llama.cpp | done | vendor/PIN 4fc4ec55; qwen35moe arch ✓, --spec-type draft-mtp ✓, --tensor-type ✓, convert registers Qwen3_5MoeForConditionalGeneration (MTP bundled by default) |
| INF3 symlinks | done | /home/seb/molt → repo; models → /mnt/proxmox/llm-serve/models/ornith-397b |
| SK-A runner/ | done | gpu_lock (wait-idle, NEVER kills), run_tierA/B, score.sh, journal.sh |
| SK-B recipes+serve | done | baseline.yaml→current.yaml, imatrix.yaml, current.args (draft-mtp commented until live A/B), current.gguf pointer |
| SK-C referee | done | harness/score.py: 4 checkers implemented; **54/54 tests green** |
| SK-D suites | done | smoke 20 · ctx32k 156 KB · nested 100 (spec-derived refs) · tau 40 (env-derived refs) · evalplus 164 (HE+ v0.1.10) · bfcl 300 (upstream ground truth); each round-trip validated |
| SK-E manifest | provisional | 30 files frozen; verify-only green; tamper drill exit-2 confirmed; FINAL freeze happens in phase0_epsilon.sh |
| SK-F corpora v1 | done | imatrix.txt 16.0 MB, kld_heldout.txt 1.99 MB (disjoint, asserted). v2 after HG6 |
| P1–P4 chain | encoded + auto-triggered | scripts/post_download_chain.sh (check-before-do, .part+rename, logs) |
| P5 Phase-0 ε | encoded, **blocked on HG4** | scripts/phase0_epsilon.sh (3× full S → ε=2σ → FINAL freeze) |

## What runs tonight without anyone touching anything

download (ETA ~04:30Z) → babysitter verifies → chain watcher fires → P1 Q8_0 convert (4–10 h,
CPU) → P2 imatrix (-ngl 0 degraded path if GPUs still busy — recorded in log) → P3 KLD base →
P4 baseline quant (~121 GB). Expected timeline: P1 done mid-morning, P2–P4 through the day.
Disk math: 794 (BF16) + 420 (Q8) + 121 (quant) ≈ 1.34 TB of 2.5 TB free — fits.

Then everything stops at the GPU wall: **P5 needs idle GPUs and llama-swap's Nemotron-Cascade
entry is `ttl: 0` — it never idle-unloads. HG4 is the only remaining blocker to session-ready.**

## HUMAN gates — exact commands, never executed by agents

- **HG3 (do first, 1 min):** create `~/.config/molt/env`:
  ```
  HF_TOKEN=hf_...        # fine-grained: read + write SEBK4C namespace + Inference Endpoints admin
  ANTHROPIC_API_KEY=sk-ant-...
  ```
- **HG6 (browser, 2 min):** accept terms while logged in as the token owner:
  https://huggingface.co/datasets/Salesforce/xlam-function-calling-60k and
  https://huggingface.co/datasets/bigcode/the-stack-smol — then:
  ```
  cd /home/seb/Ai-projects/Molt && .venv/bin/python corpora/build_imatrix_corpus.py && .venv/bin/python corpora/build_kld_heldout.py
  ```
  (Do before P2 finishes if you want xlam in the v1 imatrix; otherwise it's a Tier-C redo.)
- **HG4 (REQUIRED for P5):** free the GPUs for the session window. Nemotron-Cascade has ttl:0.
  Human options: stop/reconfigure llama-swap, or unload the model via its admin UI on :8080.
  molt never does this itself; runners wait via `runner/gpu_lock.sh wait-idle`.
- **HG1 (spends ~$95–145 GPU credits):** FP8 goldens + self-traces:
  ```
  cd /home/seb/Ai-projects/Molt && set -a; source ~/.config/molt/env; set +a
  .venv/bin/python scripts/hf_endpoint_goldens.py --dry-run     # preview call + cost
  .venv/bin/python scripts/hf_endpoint_goldens.py --confirm-spend
  ```
  Outputs → refs_fp8/ + corpora/fp8_traces.jsonl; endpoint pause+delete in finally. Mock-tested.
- **HG2 (only after --deep verify AND P1 sanity):** reclaim 794 GB:
  ```
  rm -rf /mnt/proxmox/llm-serve/models/ornith-397b/hf-bf16
  ```
- **HG5 (5 h successor cadence):** `./install_timer.sh`, then at the rate-limit reset:
  `systemctl --user start molt.service && systemctl --user start molt.timer`

## Notes for the next instance

- Read TODO.md first; reconcile against disk (resume.md procedure). Trust disk.
- tmux session `molt`: windows dl / env / lcpp / corpora / chain. `tmux attach -t molt`.
- The two WARNING lines at the end of notes/logs/molt-lcpp.log are false alarms (SIGPIPE
  artifact, fixed); --spec-type and --tensor-type are both confirmed present.
- 35B GGUFs in /mnt/proxmox/llm-serve/models/ornith/ = different model, untouched, stay away.
- After P4, if GPUs happen to be free (HG4 done), run `./scripts/phase0_epsilon.sh`, then
  pre-flight (REQUIREMENTS) and `git checkout -b molt/<date>` — session-ready.
- ctx32k.txt exact token count gets measured by the chain (P1 tokenize sanity,
  notes/logs/p1-tokencount.log); regenerate longer via harness/build/build_ctx32k.py ONLY
  before the final freeze if it comes in under 33K tokens (est. 39K, unlikely).

— bootstrap agent, session 1
