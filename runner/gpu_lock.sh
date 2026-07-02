#!/usr/bin/env bash
# molt runner — GPU lock + idle-wait. This script NEVER kills anything: "acquiring GPUs"
# means holding the molt-internal flock and *waiting* until the cards are actually idle
# (e.g. llama-swap ttl-unloaded Nemotron). Pre-existing llama-server/llama-swap processes
# are sacrosanct (bootstrap constraint).
#
# The flock serializes molt's own RAM/VRAM-hungry phases (quantize vs serve can't both fit).
#
# Usage:
#   gpu_lock.sh status                    # lock holder + per-GPU memory
#   gpu_lock.sh wait-idle [timeout_s]     # block until BOTH GPUs < IDLE_MB used (no lock taken)
#   gpu_lock.sh with-gpus <cmd...>        # flock + wait-idle + run cmd holding the lock
#   gpu_lock.sh with-lock <cmd...>        # flock only (no idle wait) — for CPU-only degraded
#                                         #   paths (-ngl 0) that still must not overlap RAM-wise
set -euo pipefail

LOCK=${MOLT_GPU_LOCK:-/home/seb/molt/.gpu.lock}
IDLE_MB=${MOLT_GPU_IDLE_MB:-1500}
mkdir -p "$(dirname "$LOCK")"
touch "$LOCK"

gpus_idle() {
  local m
  while read -r m; do
    [ "${m:-99999}" -lt "$IDLE_MB" ] || return 1
  done < <(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)
}

wait_idle() {
  local timeout=${1:-14400} t0 now
  t0=$(date +%s)
  until gpus_idle; do
    now=$(date +%s)
    if [ $((now - t0)) -ge "$timeout" ]; then
      echo "[gpu_lock] wait-idle TIMEOUT after ${timeout}s; GPUs still busy (NOT killing anything)" >&2
      return 1
    fi
    sleep 15
  done
  echo "[gpu_lock] GPUs idle at $(date -u +%FT%TZ)" >&2
}

case "${1:-}" in
  status)
    if flock -n "$LOCK" true 2>/dev/null; then echo "lock: free ($LOCK)"; else echo "lock: HELD ($LOCK)"; fi
    nvidia-smi --query-gpu=index,memory.used,memory.total,utilization.gpu --format=csv,noheader
    ;;
  wait-idle)
    wait_idle "${2:-14400}"
    ;;
  with-gpus)
    shift
    [ $# -ge 1 ] || { echo "usage: gpu_lock.sh with-gpus <cmd...>" >&2; exit 64; }
    exec flock "$LOCK" bash -c '
      set -euo pipefail
      "$0" wait-idle "${MOLT_GPU_WAIT_TIMEOUT:-14400}"
      shift
      exec "$@"
    ' "$(readlink -f "$0")" "$0" "$@"
    ;;
  with-lock)
    shift
    [ $# -ge 1 ] || { echo "usage: gpu_lock.sh with-lock <cmd...>" >&2; exit 64; }
    exec flock "$LOCK" "$@"
    ;;
  *)
    echo "usage: gpu_lock.sh status|wait-idle [timeout]|with-gpus <cmd...>|with-lock <cmd...>" >&2
    exit 64
    ;;
esac
