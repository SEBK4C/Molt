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
  step "P1: convert BF16 -> Q8_0 (CPU+disk, est 4-10 h, ~420 GB out)"
  rm -f "$M/Ornith-Q8_0.gguf.part"
  nice -n 10 $PY "$LCPP/convert_hf_to_gguf.py" "$M/hf-bf16" \
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
  if runner/gpu_lock.sh wait-idle 1 2>/dev/null; then NGL=15; else NGL=0; fi
  step "P2: llama-imatrix with -ngl $NGL ($([ "$NGL" = 0 ] && echo 'DEGRADED CPU-only path — GPUs busy (recorded per bootstrap rule)' || echo 'GPU path'))"
  rm -f "$M/imatrix-agentic.dat.part"
  nice -n 15 ionice -c3 runner/gpu_lock.sh with-lock \
    "$LCPP/build/bin/llama-imatrix" -m "$M/Ornith-Q8_0.gguf" \
    -f corpora/imatrix.txt -o "$M/imatrix-agentic.dat.part" -ngl "$NGL" --chunk 512 \
    2>&1 | tee notes/logs/p2-imatrix.log
  mv "$M/imatrix-agentic.dat.part" "$M/imatrix-agentic.dat"
  step "P2 done"
fi

# --- P3: KLD reference logits --------------------------------------------------
if [ -s "$M/kld-base.out" ]; then
  step "P3 skip: KLD base exists"
else
  [ -s corpora/kld_heldout.txt ] || { step "ABORT P3: corpora/kld_heldout.txt missing (SK-F2)"; exit 1; }
  step "P3: KLD base logits (CPU-only ok; est 1-6 h)"
  rm -f "$M/kld-base.out.part"
  nice -n 15 ionice -c3 runner/gpu_lock.sh with-lock \
    "$LCPP/build/bin/llama-perplexity" -m "$M/Ornith-Q8_0.gguf" \
    -f corpora/kld_heldout.txt --kl-divergence-base "$M/kld-base.out.part" -ngl 0 \
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
