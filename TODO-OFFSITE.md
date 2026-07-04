# molt TODO-OFFSITE — offsite agent's cross-session state (lanes: see OFFSITE-AGENT.md)

Last updated: 2026-07-04 10:30Z by offsite agent (session 1). Same rules as TODO.md:
reconcile EVERYTHING against disk/APIs before acting; trust disk over this checklist.
States: `[pending]` `[in-progress]` `[blocked: <on-what>]` `[done]` `[HUMAN]`.

## Reconciliation log (2026-07-04 ~09:20Z, session 1 open)

- Cached token (`~/.cache/huggingface/token`, user SEBK4C, fine-grained) HAS
  `inference.endpoints.write` + `inference.endpoints.infer.write` + `repo.write` →
  **HG1 token blocker CLEARED** (brief was stale; owner fixed the cached token instead of
  creating `~/.config/molt/env`). HG3 (env file with ANTHROPIC_API_KEY etc.) stays [HUMAN];
  offsite runs export `HF_TOKEN=$(cat ~/.cache/huggingface/token)` at runtime.
- ~~Both gated datasets return 200 authed → HG6 CLEARED~~ **CORRECTION 10:44Z: WRONG.**
  /tree 200 is a false positive on gated repos; `/api/datasets/<id>/auth-check` returns
  "not in the authorized list" and file `resolve` 403s. **HG6 remains [HUMAN]**: owner must
  accept terms (browser, logged in) at both dataset pages. Token itself is fine
  (`canReadGatedRepos: True`).
- **`aws us-east-1 nvidia-h100 x8` NO LONGER EXISTS** in the endpoints catalog
  (`api.endpoints.huggingface.cloud/v2/provider`). Replacement at $20/h:
  `aws ap-northeast-2 nvidia-h200-x4` (564 GB, native FP8 W8A8) — chosen;
  fallback `aws us-east-1 nvidia-a100-x8` (640 GB, W8A16 Marlin, same price).
- No serverless provider hosts Ornith (both repos: empty inferenceProviderMapping);
  ZeroGPU caps at 96 GB VRAM — neither can replace the dedicated endpoint (owner asked).
- `SEBK4C/molt-ornith-eval` does not exist yet (404 authed). No orphan endpoints under SEBK4C.
- No keeper tag in git → mission 4 (Featherweight publication) [blocked: local-loop keeper tag].

## Missions

- **M1 HG1 — FP8 goldens + S_fp8 reference scoring [blocked: HF endpoint quota — OWNER]**
  (owner-authorized, $100 hard cap; approved scope adds S_fp8 = score FP8 on the frozen
  suites via the unmodified referee through a localhost auth-proxy). 2026-07-04 10:40–41Z:
  BOTH creates failed 409 pre-billing — account quota `nvidia-h200: available 2, requested 4`
  and `nvidia-a100: available 4, requested 8`. No within-quota instance has ≥ ~420 GB VRAM
  (a100-x4 = 320, h200-x2 = 282). $0 spent, zero endpoints left (verified).
  **OWNER ACTION (updated 10:53Z)**: support granted "up to 16x RTX PRO 6000" by email, but
  the API enforces available=4 (x8 create 409s twice, incl. a propagation-lag retry). Reply to
  the support thread (Megan): quota shows 4, need 8 applied for
  `aws-us-east-2-nvidia-rtx-pro-6000-x8` — FP8 checkpoint is 405 GB, x8/768 GB is the minimum
  fit (x4=384 GB can't hold it; cpu-offload unusable for a billed batch run). h200/a100 quotas
  (2/4) also remain too small. Script already targets rtx-pro-6000-x8; relaunch as-is when applied.
  Relaunch when cleared: `export HF_TOKEN=$(cat ~/.cache/huggingface/token); timeout -s INT
  16200 .venv/bin/python -u scripts/hf_endpoint_goldens.py --confirm-spend --trace-tokens
  3000000` (add `--fallback-instance` for a100-x8). Wall bound $90. Sequence: goldens
  (parallelized) → S_fp8 → traces. Teardown verification after exit is NON-NEGOTIABLE.
- **M2 HG6 corpora v2 [blocked: owner terms-acceptance]** — builders reran 10:41Z with token
  exported: both datasets still refuse (not in authorized list) → output = v1 fallback mix,
  unchanged. After owner accepts terms: rerun both builders with `HF_TOKEN` exported
  (evidence → notes/logs/molt-corpora-v2.log); Tier-C remix scheduling = local loop's lane.
- **M3 Dataset publication [done 10:56Z]** — https://huggingface.co/datasets/SEBK4C/molt-ornith-eval
  public, 21 files, README renders, honest-limitations intact. Published pre-goldens (HG1
  quota-blocked indefinitely); `refs_fp8/` + `fp8_traces.jsonl` slot in via a rerun of
  `scripts/publish_hf_dataset.py` once HG1 lands. Precondition held: exp005 adjudicated
  (DISCARD, S=0.9223 — embd Q8 floor load-bearing) before upload of recipes/current.yaml.
- **M4 Featherweight publication [blocked: local-loop keeper tag]**.
- **M5 [blocked: owner budget call]** — next flagship after M1/M3: EAGLE-3 draft head
  (~$1.2K, speed: 2.5–4 accepted tok/step ≈ 35–55 t/s decode) vs LoRA-recovery (~$1.5K,
  quality: nested recovery via self-distilled traces). Both far over cap — DO NOT START.

## Mission-4 TRIGGER (from local loop, 2026-07-04 ~11:20Z)
Keeper tagged: `featherweight-v0` (models/ornith-molt-000.gguf + serve/current.args as of
reconfirm-20260703). Owner has pulled v0 publication FORWARD — proceed with
SEBK4C/Ornith-1.0-397B-Featherweight when your lane is free: GGUF upload (119.5 GB —
measure upload bandwidth first, chunked/resumable), MODEL_CARD modeled on ds4 (cite
docs/RESEARCH_STATEMENT.md + docs/DATASET_CARD.md licensing table; include the
honest-limitations section and the serve args). Dataset publish may go BEFORE goldens
now (owner wants grant-ready assets up); FP8 artifacts amend later.
