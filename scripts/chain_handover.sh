#!/usr/bin/env bash
# One-shot guard (2026-07-02): the chain bash instance running in molt:chain launched BEFORE
# the P3 batch-geometry + auto-P5 edits and has the old script buffered. This waits for P2's
# atomic rename (imatrix done, no children at risk), retires the old instance, and takes over
# as the chain (P1/P2 skip via check-before-do; P3 runs with corrected flags; P4 -> auto-P5).
# Self-deletes its TODO relevance once done — see molt-chain.log for the handover marker.
set -uo pipefail
cd /home/seb/Ai-projects/Molt

echo "[handover] waiting for models/imatrix-agentic.dat (P2 atomic rename)..."
until [ -s models/imatrix-agentic.dat ]; do
  # if the old chain died early (e.g. imatrix crash), take over immediately
  if ! pgrep -x llama-imatrix >/dev/null && ! [ -s models/imatrix-agentic.dat ]; then
    sleep 30
    pgrep -x llama-imatrix >/dev/null || { echo "[handover] imatrix not running and no output — taking over now"; break; }
  fi
  sleep 60
done

PANE_PID=$(tmux display -pt molt:chain '#{pane_pid}' 2>/dev/null || echo "")
if [ -n "$PANE_PID" ]; then
  echo "[handover] retiring old chain instance (children of pane $PANE_PID)"
  pkill -TERM -P "$PANE_PID" 2>/dev/null || true
  sleep 2
fi
pgrep -x llama-perplexity >/dev/null && { pkill -x llama-perplexity; sleep 2; }

echo "[handover] $(date -u +%FT%TZ) fresh chain takes over (P3 corrected flags, auto-P5)"
exec ./scripts/post_download_chain.sh
