#!/usr/bin/env bash
# Post-Phase-0 falsification probes (notes/validation-audit-2026-07-03.md):
#  A. Negative control — score the tiny 9B on the SAME frozen suite (eval-lite). A weak model
#     must score clearly lower; if tau/nested stay high, those suites lack discrimination.
#  B. KLD diagnostic — distributional distance of the baseline quant from the Q8 master
#     (llama-perplexity --kl-divergence vs models/kld-base.out). Harness-free number.
# Read-only wrt harness/ (frozen); servers launched here are OURS and killed on exit.
set -uo pipefail
cd /home/seb/Ai-projects/Molt
PY=.venv/bin/python
BIN=vendor/llama.cpp/build/bin

echo "=== A. negative control: 9B on the frozen eval-lite ($(date -u +%FT%TZ)) ==="
"$BIN/llama-server" -m /mnt/proxmox/llm-serve/models/ornith/ornith-9b-mtp-kl-Q6_K.gguf \
  -ngl 99 -c 163840 -np 4 -b 4096 -ub 4096 --jinja --reasoning-format auto \
  --reasoning-budget 1024 --host 127.0.0.1 --port 9022 --alias neg-control \
  >notes/logs/serve-neg-control.log 2>&1 &
SRV=$!
trap 'kill $SRV 2>/dev/null || true; wait $SRV 2>/dev/null || true' EXIT
for i in $(seq 1 60); do
  curl -sf http://127.0.0.1:9022/health >/dev/null 2>&1 && break
  kill -0 $SRV 2>/dev/null || { echo "[probe-A] 9B server died"; break; }
  sleep 2
done
if curl -sf http://127.0.0.1:9022/health >/dev/null 2>&1; then
  # G1 measures the 9B file (7.6 GB, passes trivially) — we want the SUITE numbers
  $PY harness/score.py --exp neg-control-9b \
    --gguf /mnt/proxmox/llm-serve/models/ornith/ornith-9b-mtp-kl-Q6_K.gguf \
    --server http://127.0.0.1:9022 --lite | tee notes/logs/score-neg-control-9b.json
else
  echo "[probe-A] SKIPPED (server unavailable) — investigate serve-neg-control.log"
fi
kill $SRV 2>/dev/null || true; wait $SRV 2>/dev/null || true; trap - EXIT
sleep 3

echo "=== B. KLD of baseline quant vs Q8 master ($(date -u +%FT%TZ)) ==="
nice -n 10 runner/gpu_lock.sh with-gpus \
  "$BIN/llama-perplexity" -m models/ornith-molt-000.gguf \
  -f corpora/kld_heldout.txt --kl-divergence-base models/kld-base.out --kl-divergence \
  -ngl 99 --n-cpu-moe 52 -ts 52,8 -b 4096 -ub 4096 --chunks 60 -t 32 -tb 32 \
  2>&1 | tee notes/logs/kld-baseline.log | tail -25

echo "=== probes complete ($(date -u +%FT%TZ)) ==="
