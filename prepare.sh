#!/usr/bin/env bash
# molt prepare.sh — one-time setup on llm-serve. Idempotent: every step checks before doing.
# Thin orchestrator over scripts/ (each independently rerunnable + tmux-friendly).
# ~/.config/molt/env (HF_TOKEN, ANTHROPIC_API_KEY) is needed for HG1 endpoint + HF uploads;
# the public 397B download itself rides the cached ~/.cache/huggingface/token.
set -euo pipefail
[ -f ~/.config/molt/env ] && { set -a; source ~/.config/molt/env; set +a; }

ROOT=/home/seb/molt              # symlink -> the repo (created below if absent)
REPO=/home/seb/Ai-projects/Molt
STAGE=/mnt/proxmox/llm-serve/models/ornith-397b   # ALL large artifacts live here, never on /

# 0. layout: symlinks + dirs (models/ -> big disk; /home/seb/molt -> repo)
[ -e "$ROOT" ] || ln -s "$REPO" "$ROOT"
mkdir -p "$STAGE" "$REPO/notes/logs"
[ -e "$REPO/models" ] || ln -s "$STAGE" "$REPO/models"

cd "$REPO"

# 1. pinned llama.cpp build (qwen35moe + --spec-type draft-mtp + --tensor-type; see vendor/PIN)
[ -x vendor/llama.cpp/build/bin/llama-quantize ] || ./scripts/build_llamacpp.sh

# 2. python env (uv; torch is CPU-only, for convert_hf_to_gguf)
[ -x .venv/bin/python ] || ./scripts/setup_env.sh

# 3. P0: BF16 originals (~794 GB; NOT the FP8 repo — convert can't ingest compressed-tensors).
#    Resumes natively; run detached because this takes hours:
if [ ! -f notes/logs/molt-dl.log ] || ! grep -q 'COMPLETE' notes/logs/molt-dl.log; then
  tmux has-session -t molt 2>/dev/null || tmux new-session -d -s molt -n dl
  tmux list-windows -t molt | grep -q ' dl' || tmux new-window -t molt -n dl
  tmux send-keys -t molt:dl "cd $REPO && ./scripts/download_397b.sh 2>&1 | tee -a notes/logs/molt-dl.log" Enter
  echo ">> download running in tmux molt:dl (progress: du -sb $STAGE/hf-bf16 vs 793633331312)"
fi

# 4. corpora (small; can run while weights download)
[ -s corpora/imatrix.txt ]     || .venv/bin/python corpora/build_imatrix_corpus.py --mix recipes/imatrix.yaml --out corpora/imatrix.txt
[ -s corpora/kld_heldout.txt ] || .venv/bin/python corpora/build_kld_heldout.py --out corpora/kld_heldout.txt

# 5. harness self-check (tests + provisional manifest if none yet)
.venv/bin/python -m pytest harness/tests/ -q
[ -f harness/manifest.json ] || .venv/bin/python harness/manifest.py --write --provisional
runner/score.sh --verify-only

cat <<'EOF'
>> prepare.sh done (download may still be streaming — see tmux molt:dl).
>> After the download verifies (scripts/verify_download.py):
>>   ./scripts/post_download_chain.sh   # P1 Q8_0 -> P2 imatrix -> P3 KLD -> P4 baseline quant
>>   ./scripts/phase0_epsilon.sh        # P5: 3x baseline -> harness/epsilon.txt -> FINAL freeze
>>     (P5 needs idle GPUs: llama-swap's Nemotron entry is ttl:0 — freeing GPUs is HUMAN gate HG4)
>> then: git checkout -b molt/$(date +%Y%m%d); start Claude Code: "Read program.md and start tonight's session."
EOF
