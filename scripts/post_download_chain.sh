#!/usr/bin/env bash
# molt P1–P4 orchestrator. Run after D2 (download verified). Safe to rerun: every step is
# check-before-do (skips when a valid output exists), writes *.part then atomic-renames,
# logs to notes/logs/. CPU/disk only — NO GPU required (imatrix/KLD run degraded -ngl 0 if
# GPUs are busy; the choice is recorded in the log).
# Suggested launch:  tmux new-window -t molt -n chain \
#   'cd /home/seb/Ai-projects/Molt && ./scripts/post_download_chain.sh 2>&1 | tee -a notes/logs/molt-chain.log'
set -euo pipefail
cd /home/seb/Ai-projects/Molt

PY=.venv/bin/python
LCPP=vendor/llama.cpp
M=models          # -> /mnt/proxmox/llm-serve/models/ornith-397b (symlink; NEVER the root fs)
mkdir -p notes/logs

step() { echo "[chain $(date -u +%FT%TZ)] $*"; }

# --- P0 gate: download must be verified ------------------------------------
step "P0 gate: shallow-verify download"
$PY scripts/verify_download.py || { step "ABORT: download not verified (D2)"; exit 1; }

# --- P1: Q8_0 master --------------------------------------------------------
if [ -s "$M/Ornith-Q8_0.gguf" ]; then
  step "P1 skip: $M/Ornith-Q8_0.gguf exists ($(du -h "$M/Ornith-Q8_0.gguf" | cut -f1))"
else
  step "P1: convert BF16 -> Q8_0 (~31 min; ceiling is single-threaded python quant compute,
        NOT the NVMe — measured 11.1 GB/s read / 7.6 GB/s write direct-IO on /mnt/proxmox)"
  rm -f "$M/Ornith-Q8_0.gguf.part"
  # --no-mtp is REQUIRED: Ornith's config declares mtp_num_hidden_layers=1 but neither the
  # BF16 nor FP8 repo ships the mtp.* weights; a default convert writes block_count=61 +
  # nextn metadata with no blk.60 tensors -> unloadable (2026-07-02 defect, TODO decision log).
  nice -n 10 $PY "$LCPP/convert_hf_to_gguf.py" "$M/hf-bf16" --no-mtp \
    --outtype q8_0 --outfile "$M/Ornith-Q8_0.gguf.part" 2>&1 | tee notes/logs/p1-convert.log
  mv "$M/Ornith-Q8_0.gguf.part" "$M/Ornith-Q8_0.gguf"
  step "P1 done: $(du -h "$M/Ornith-Q8_0.gguf" | cut -f1)"
fi

step "P1 sanity: vocab/header parse + ctx32k token count"
"$LCPP/build/bin/llama-tokenize" -m "$M/Ornith-Q8_0.gguf" \
  -f harness/prompts/ctx32k.txt --show-count 2>&1 | tail -2 | tee notes/logs/p1-tokencount.log \
  || step "WARNING: tokenize sanity failed — investigate before P2"

# --- P2: imatrix --------------------------------------------------------------
if [ -s "$M/imatrix-agentic.dat" ]; then
  step "P2 skip: imatrix exists"
else
  [ -s corpora/imatrix.txt ] || { step "ABORT P2: corpora/imatrix.txt missing (SK-F1)"; exit 1; }
  step "P2: llama-imatrix, GPU-assisted (owner cleared HG4 2026-07-02: molt owns the GPUs)"
  # Flag notes (2026-07-02): --chunk means FROM-chunk (skip!), not chunk size — never use it.
  # -ngl 99 --n-cpu-moe 60: ALL non-expert tensors (~10.5 GB: attention, deltanet, router,
  #   shared experts, embeddings) on the 4090s = ~58% of prefill FLOPs; the 512-expert FFNs
  #   (~411 GB) stay CPU+mmap — they can never fit in 48 GB. Measured CPU-only: 421 s/pass
  #   => 17.5 h uncapped; GPU-assist target ~2-4 min/pass.
  # --chunks 240 = ~123K calibration tokens ≈ community-standard imatrix size (~60 passes);
  #   richer remix is a Tier-C experiment later, not tonight's blocker.
  # --parse-special: corpus embeds the chat template's special tokens; calibrate on real ids.
  # gpu_lock with-gpus: flock + wait-for-idle (never kills anything that grabs the cards back).
  rm -f "$M/imatrix-agentic.dat.part"
  nice -n 15 ionice -c3 runner/gpu_lock.sh with-gpus \
    "$LCPP/build/bin/llama-imatrix" -m "$M/Ornith-Q8_0.gguf" \
    -f corpora/imatrix.txt -o "$M/imatrix-agentic.dat.part" \
    -ngl 99 --n-cpu-moe 60 --chunks 240 --parse-special -t 32 -tb 32 \
    2>&1 | tee notes/logs/p2-imatrix.log
  mv "$M/imatrix-agentic.dat.part" "$M/imatrix-agentic.dat"
  step "P2 done"
fi

# --- P3: KLD reference logits --------------------------------------------------
if [ -s "$M/kld-base.out" ]; then
  step "P3 skip: KLD base exists"
else
  [ -s corpora/kld_heldout.txt ] || { step "ABORT P3: corpora/kld_heldout.txt missing (SK-F2)"; exit 1; }
  step "P3: KLD base logits, GPU-assisted non-expert offload (same rationale as P2)"
  # --chunks 60 ≈ 30K held-out tokens for the KLD reference — a DIAGNOSTIC (logged, never
  # ratcheted); uncapped 2 MB CPU-only would be 10+ h for no decision value.
  rm -f "$M/kld-base.out.part"
  nice -n 15 ionice -c3 runner/gpu_lock.sh with-gpus \
    "$LCPP/build/bin/llama-perplexity" -m "$M/Ornith-Q8_0.gguf" \
    -f corpora/kld_heldout.txt --kl-divergence-base "$M/kld-base.out.part" \
    -ngl 99 --n-cpu-moe 60 --chunks 60 -t 32 -tb 32 \
    2>&1 | tee notes/logs/p3-kld.log
  mv "$M/kld-base.out.part" "$M/kld-base.out"
  step "P3 done"
fi

# --- P4: baseline quant ---------------------------------------------------------
if [ -s "$M/ornith-molt-000.gguf" ]; then
  step "P4 skip: baseline quant exists"
else
  step "P4: baseline quant from recipes/baseline.yaml (est 1-3 h)"
  CMD=$($PY runner/render_quant_cmd.py recipes/baseline.yaml \
        --imatrix "$M/imatrix-agentic.dat" --in "$M/Ornith-Q8_0.gguf" \
        --out "$M/ornith-molt-000.gguf")
  step "P4 cmd: $CMD"
  nice -n 15 ionice -c3 runner/gpu_lock.sh with-lock bash -c "$CMD" \
    2>&1 | tee notes/logs/p4-quant.log
  step "P4 done: $(du -h "$M/ornith-molt-000.gguf" | cut -f1)"
fi

step "CHAIN COMPLETE. Next: P5 = ./scripts/phase0_epsilon.sh"
step "  REQUIRES GPUs idle. NOTE: llama-swap has ttl:0 for Nemotron-Cascade-30B — it will"
step "  NEVER idle-unload by itself; freeing the GPUs is HUMAN gate HG4."
