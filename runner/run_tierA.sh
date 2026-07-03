#!/usr/bin/env bash
# molt runner — Tier A experiment: serve-config only (budget ~20 min).
# Serves the current best GGUF with serve/current.args on :9021, waits /health, runs eval-lite,
# tears down ONLY the server it started. Manifest is verified before anything runs.
#
# Usage: run_tierA.sh <exp_id> [--full] [--gguf <path>]
#   --full  : full S instead of eval-lite (used by Tier B and end-of-session re-confirmation)
#   --gguf  : override GGUF (Tier B scores its candidate through this)
# Env: MOLT_PORT (default 9021), MOLT_EVAL_TIMEOUT seconds (default 1500 lite / 5400 full)
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")/.."

EXP=${1:?usage: run_tierA.sh <exp_id> [--full] [--gguf path]}
shift
MODE=--lite
GGUF=""
while [ $# -gt 0 ]; do
  case "$1" in
    --full) MODE=""; shift ;;
    --gguf) GGUF=$2; shift 2 ;;
    *) echo "[tierA] unknown arg: $1" >&2; exit 64 ;;
  esac
done
[ -n "$GGUF" ] || GGUF=$(cat serve/current.gguf)
PORT=${MOLT_PORT:-9021}
SRV_BIN=${MOLT_LLAMA_SERVER:-vendor/llama.cpp/build/bin/llama-server}
# Ceilings from MEASURED wall times (notes/measured-reality): full S ≈ 6.4 h + gates ~35 min
# => 36000s. eval-lite = gates ~35 min + bfcl-lite ~20 min + nested ~50 min ≈ 105 min =>
# 9000s (2700 killed exp002 mid-suite, silently — hence the explicit timeout verdict below).
if [ -z "$MODE" ]; then TIMEOUT=${MOLT_EVAL_TIMEOUT:-36000}; else TIMEOUT=${MOLT_EVAL_TIMEOUT:-9000}; fi

# 1. referee integrity first — a tampered harness auto-fails everything
runner/score.sh --verify-only

[ -f "$GGUF" ] || { echo "[tierA] GGUF not found: $GGUF" >&2; exit 66; }
[ -x "$SRV_BIN" ] || { echo "[tierA] llama-server not built: $SRV_BIN" >&2; exit 66; }

mkdir -p notes/logs
SRV_LOG=notes/logs/serve-${EXP}.log

# 2. serve + score under the GPU lock (waits for idle; NEVER kills foreign processes)
runner/gpu_lock.sh with-gpus bash -c '
  set -euo pipefail
  EXP=$1; GGUF=$2; PORT=$3; SRV_BIN=$4; SRV_LOG=$5; MODE=$6; TIMEOUT=$7

  # read args file: strip comments/blank lines, expand into words
  mapfile -t ARGWORDS < <(grep -vE "^\s*(#|$)" serve/current.args | xargs -n1 printf "%s\n")

  "$SRV_BIN" -m "$GGUF" --host 127.0.0.1 --port "$PORT" --alias molt \
    "${ARGWORDS[@]}" >"$SRV_LOG" 2>&1 &
  SRV_PID=$!
  trap "kill \$SRV_PID 2>/dev/null || true; wait \$SRV_PID 2>/dev/null || true" EXIT

  # health wait: model load from SSD can take minutes
  t0=$(date +%s)
  until curl -sf "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; do
    if ! kill -0 "$SRV_PID" 2>/dev/null; then
      echo "{\"exp\":\"$EXP\",\"gates_pass\":false,\"reason\":\"G2 fail: llama-server exited during load (see $SRV_LOG)\"}" \
        | tee "notes/logs/score-$EXP.json"
      exit 0
    fi
    if [ $(( $(date +%s) - t0 )) -ge 1800 ]; then
      echo "{\"exp\":\"$EXP\",\"gates_pass\":false,\"reason\":\"G2 fail: /health not ready after 1800s\"}" \
        | tee "notes/logs/score-$EXP.json"
      exit 0
    fi
    sleep 5
  done
  echo "[tierA] server healthy after $(( $(date +%s) - t0 ))s" >&2

  set +e
  if [ -n "$MODE" ]; then
    timeout "$TIMEOUT" runner/score.sh "$EXP" --lite --gguf "$GGUF" --server "http://127.0.0.1:$PORT"
  else
    timeout "$TIMEOUT" runner/score.sh "$EXP" --gguf "$GGUF" --server "http://127.0.0.1:$PORT"
  fi
  rc=$?
  set -e
  if [ "$rc" -eq 124 ]; then
    # a timeout must be a VERDICT, never silence (exp002 lesson: set -e swallowed rc 124)
    echo "{\"exp\":\"$EXP\",\"gates_pass\":false,\"reason\":\"eval timeout after ${TIMEOUT}s — raise MOLT_EVAL_TIMEOUT or investigate stall\"}" \
      | tee "notes/logs/score-$EXP.json"
    exit 0
  fi
  exit "$rc"   # 2 = manifest tamper must propagate; 0 = verdict already on stdout
' _ "$EXP" "$GGUF" "$PORT" "$SRV_BIN" "$SRV_LOG" "$MODE" "$TIMEOUT"
