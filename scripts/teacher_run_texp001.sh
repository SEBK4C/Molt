#!/bin/bash
# texp001 arms A+B under ONE gpu_lock tenure (no between-arms gap for the flock queue).
# Run as: runner/gpu_lock.sh with-gpus scripts/teacher_run_texp001.sh
# Verdicts -> notes/logs/teacher-score-texp001-{base,echo}.json (teacher namespace).
set -uo pipefail
cd "$(dirname "$0")/.."
GGUF=models/ornith-molt-000.gguf
PORT=9021
LOG=notes/logs/teacher-texp001.log

say() { echo "[texp001 $(date -u +%H:%M:%SZ)] $*" | tee -a "$LOG"; }

.venv/bin/python harness/score.py --verify-only || { say "MANIFEST TAMPER rc=$?"; exit 2; }

run_arm() {
  local arm="$1" template="$2"
  say "arm $arm: launching server (template: $template)"
  # serve/current.args minus its template line, then our per-arm template flag
  local args
  args=$(grep -vE '^\s*(#|$)' serve/current.args | grep -v chat-template-file | tr '\n' ' ')
  # shellcheck disable=SC2086
  vendor/llama.cpp/build/bin/llama-server -m "$GGUF" --host 127.0.0.1 --port $PORT \
      --alias molt $args --chat-template-file "$template" \
      >> "notes/logs/teacher-serve-texp001-$arm.log" 2>&1 &
  local spid=$!
  for i in $(seq 1 360); do
    curl -sf -m 5 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 && break
    kill -0 $spid 2>/dev/null || { say "arm $arm: server DIED during load"; return 3; }
    sleep 5
  done
  curl -sf -m 5 "http://127.0.0.1:$PORT/health" >/dev/null || { say "arm $arm: health timeout"; kill $spid; return 3; }
  say "arm $arm: healthy, scoring (lite)"
  .venv/bin/python harness/score.py --exp "texp001-$arm" --gguf "$GGUF" \
      --server "http://127.0.0.1:$PORT" --lite \
      | tee "notes/logs/teacher-score-texp001-$arm.json"
  local rc=${PIPESTATUS[0]}
  say "arm $arm: score rc=$rc; stopping own server $spid"
  kill $spid 2>/dev/null; sleep 8; kill -9 $spid 2>/dev/null
  return $rc
}

run_arm base serve/chat_template.jinja;        rcA=$?
run_arm echo serve/templates/scaffold_json_echo.jinja; rcB=$?
say "DONE rcA=$rcA rcB=$rcB (verdicts in notes/logs/teacher-score-texp001-*.json)"
exit 0
