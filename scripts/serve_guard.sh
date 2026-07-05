#!/usr/bin/env bash
# serve_guard.sh — THE sanctioned way to run llama-server on this box (both agent loops).
# Closes the three observed loop hazards:
#   1. hot-restart spin: exponential backoff + circuit breaker (3 deaths <120 s => HALT with
#      a verdict file, never an infinite 5 s loop)
#   2. resurrection fights: honors notes/gpu-window.claim (foreign unexpired claim => wait;
#      claim appearing MID-SERVE => graceful self-stop, wait, auto-resume at expiry)
#   3. unsynchronized servers: always inside the gpu_lock flock; pidfile per port so others
#      can target THIS server precisely; kills only its own pid, never by process name
#
# Usage: serve_guard.sh <port> <session-tag> -- <llama-server args...>
# Stop deliberately: touch .serve-<port>-stop   Status: notes/serve-<port>.pid + guard log
set -uo pipefail
cd /home/seb/Ai-projects/Molt

PORT=${1:?port}; TAG=${2:?session-tag}; shift 2; [ "${1:-}" = "--" ] && shift
STOPF=".serve-${PORT}-stop"
PIDF="notes/serve-${PORT}.pid"
CLAIM="notes/gpu-window.claim"
BIN=vendor/llama.cpp/build/bin/llama-server

log() { echo "[guard:$PORT] $(date -u +%FT%TZ) $*"; }

claim_active_foreign() {  # 0 = a foreign, unexpired claim exists
  [ -f "$CLAIM" ] || return 1
  grep -q "$TAG" "$CLAIM" && return 1
  local start ttl_h exp now
  start=$(grep -oP '^start:\s*\K\S+' "$CLAIM" 2>/dev/null) || return 1
  ttl_h=$(grep -oP '^ttl:\s*\K[0-9]+(?=h)' "$CLAIM" 2>/dev/null) || ttl_h=4
  exp=$(( $(date -u -d "${start/Z/ UTC}" +%s 2>/dev/null || echo 0) + ttl_h*3600 ))
  now=$(date +%s)
  [ "$now" -lt "$exp" ]
}

deaths=0; last_death=0
while :; do
  [ -f "$STOPF" ] && { log "stop-file present — exiting guard"; exit 0; }
  if claim_active_foreign; then
    log "foreign GPU window active ($(grep -m1 holder: "$CLAIM" 2>/dev/null)) — waiting 60s"
    sleep 60; continue
  fi
  log "starting llama-server under gpu lock"
  runner/gpu_lock.sh with-gpus "$BIN" --port "$PORT" "$@" 2>&1 | tee -a "notes/logs/serve-guard-${PORT}.log" &
  WRAP=$!
  # find the real server pid (child of the lock chain) once it appears
  for i in $(seq 1 30); do
    SPID=$(ss -ltnp 2>/dev/null | grep -oP "(?<=pid=)\d+(?=.*:${PORT})" | head -1)
    [ -n "${SPID:-}" ] && break; sleep 2
  done
  [ -n "${SPID:-}" ] && echo "$SPID" > "$PIDF" && log "serving (pid $SPID)"
  # supervise: exit on server death, stop-file, or claim activation
  while kill -0 "${SPID:-$WRAP}" 2>/dev/null; do
    if [ -f "$STOPF" ]; then
      log "stop-file — graceful SIGINT to own pid ${SPID:-?}"
      [ -n "${SPID:-}" ] && kill -INT "$SPID" 2>/dev/null
      wait "$WRAP" 2>/dev/null; rm -f "$PIDF"; exit 0
    fi
    if claim_active_foreign; then
      log "claim activated mid-serve — yielding (graceful SIGINT, will resume at expiry)"
      [ -n "${SPID:-}" ] && kill -INT "$SPID" 2>/dev/null
      wait "$WRAP" 2>/dev/null; rm -f "$PIDF"
      continue 2
    fi
    sleep 20
  done
  wait "$WRAP" 2>/dev/null; rm -f "$PIDF"
  now=$(date +%s)
  if [ $((now - last_death)) -lt 120 ]; then deaths=$((deaths+1)); else deaths=1; fi
  last_death=$now
  if [ "$deaths" -ge 3 ]; then
    log "CIRCUIT BREAKER: 3 fast deaths — halting (see serve-guard-${PORT}.log)"
    echo "{\"port\":$PORT,\"halted\":\"$(date -u +%FT%TZ)\",\"reason\":\"3 fast deaths - investigate before restarting\"}" \
      > "notes/logs/serve-guard-${PORT}-HALTED.json"
    exit 1
  fi
  backoff=$((15 * deaths * deaths))
  log "server exited — restart in ${backoff}s (death $deaths/3 in window)"
  sleep "$backoff"
done
