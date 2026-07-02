#!/usr/bin/env bash
# molt D1 — download Ornith-1.0-397B BF16 originals to the big disk. Safe to rerun any time:
# huggingface-cli resumes partial downloads natively. NEVER delete partial files to "fix" it.
set -uo pipefail

REPO=deepreinforce-ai/Ornith-1.0-397B
REV=5e3e761811e804c295c1d3c0ce68b21da6154209   # pinned; matches hf-tree.json snapshot
DEST=/mnt/proxmox/llm-serve/models/ornith-397b/hf-bf16

export PATH="$HOME/.local/bin:$PATH"
export HF_HUB_DISABLE_PROGRESS_BARS=1          # keep the log sane over a multi-hour run

mkdir -p "$DEST"
echo "[download_397b] start $(date -u +%FT%TZ) dest=$DEST rev=$REV"

n=0
until huggingface-cli download "$REPO" --revision "$REV" --local-dir "$DEST"; do
  n=$((n+1))
  echo "[download_397b] attempt $n failed at $(date -u +%FT%TZ); retry in 60s" >&2
  if [ "$n" -ge 200 ]; then
    echo "[download_397b] giving up after 200 attempts" >&2
    exit 1
  fi
  sleep 60
done

echo "[download_397b] COMPLETE $(date -u +%FT%TZ)"
echo "[download_397b] next: uv run python scripts/verify_download.py   (TODO item D2)"
