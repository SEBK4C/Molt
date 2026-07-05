# molt research overview — for owner review, 2026-07-05 ~11:45Z
*(Systems running as-is; this document changes nothing.)*

## 1. Where the science stands

**Published artifact**: Featherweight v0 — 119.5 GB / 2.41 bpw / S = 0.9258 (ε 0.0053) /
18.5–18.9 t/s single-user. Model + llamafile + dataset + research report + GitHub all live
and cross-linked. Local search program COMPLETE: recipe locally optimal (3 surfaces falsified,
embd floor confirmed), placement saturated (10–11 GPU expert layers), speculation family
falsified with mechanism (inverts on CPU-resident MoE — cancelled the EAGLE-3 plan).

**Open science, by owner decision**:
- **S_fp8 anchor + goldens + trace corpus** (~$100): blocked on HF endpoint QUOTA (h200 needs
  4, account has partial grant; teacher lane owns the retry).
- **imatrix v2** (free once traces exist): legitimately reopens the recipe search (Tier C).
- **LoRA recovery** (~$1.5K): the surviving big-ticket quality play. Decide after S_fp8 says
  how much quality is actually missing.
- **Harness v2 freeze bundle** (one ~16 h recalibration): dead-case fix + harder τ + per-case
  paired stats + goldens promotion — bundled, post-HG1.

## 2. The three loops and their lanes

| Loop | Session | Owns | Current activity |
|---|---|---|---|
| **ratchet (this one)** | …LxmyGw6 | frozen harness, ratchet journal, serving guard, publications | watch cadence; chat server steward; publisher |
| **teacher** | …UnXUeEm1Y | texp001 (scaffold-elicitation A/B), endpoint/quota retries, offsite missions | GPU window 11:35–15:35Z, running texp001 arms A+B |
| **owner** | you | arbitration, money gates, GitHub/HF account actions | reviewing this |

**Handoff mechanics now in force** (all born from this morning's collision):
- `notes/gpu-window.claim` — single-writer GPU tenure with TTL; both loops honor; your word
  overrides. Proven live twice today.
- `scripts/serve_guard.sh` — the only sanctioned llama-server runner: claim-aware, flock'd,
  circuit-breaker'd, PID-only kills. My lane migrated; teacher adoption proposed.
- Namespaces: ratchet verdicts `score-*` / teacher verdicts `teacher-score-*`; journals
  `experiments.jsonl` / `notes/offsite-journal.jsonl`; TODO.md / TODO-OFFSITE.md.
- Git-only coordination: every claim, verdict, apology, and protocol change is a commit.

**Handoffs currently open**:
1. teacher → ratchet: texp001 results (if its harder JSON-echo scaffolds discriminate better
   than our nested suite, they feed the harness-v2 bundle).
2. teacher → ratchet: refs_fp8/ + fp8_traces.jsonl when quota clears → I bundle the v2
   freeze + re-ε (~16 h) → possibly a new search cycle on imatrix v2.
3. ratchet → teacher: serve_guard adoption; measured-reality constants (already in repo).
4. → owner: quota click; LoRA yes/no after S_fp8; grant program picks (statement is ready).

## 3. Systems inventory (all steady)

- **Chat server** :4242 — under serve_guard; auto-resumes 15:35Z; stop: `touch .serve-4242-stop`.
- **tmux `molt`**: chat (guard), status (30 s telemetry), others idle-historical.
- **Loop cadence**: 30-min cron (d5d63a29), terse watch ticks; wakes for verdicts/commits.
- **Disk**: ~560 GB free; deletable-on-HG2: BF16 (794 GB), bad master (421 GB), 2 discard
  candidates (~240 GB).
- **Integrity**: harness manifest green (31 files); journal 14 entries; memory files current;
  everything pushed (GitHub main 021495d+, session branch tip 19de0d6).

## 4. What I recommend you review

1. The research report (GitHub README → docs/RESEARCH_REPORT.md) — it is the citable object.
2. The teacher's texp001 design (its commits, ~11:35Z) — it is now the active experiment.
3. The two money decisions in §1 — everything else is autonomous.
