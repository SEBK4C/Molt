#!/usr/bin/env bash
# molt runner — referee wrapper. The ONLY sanctioned way to invoke the referee.
#
# Usage:
#   runner/score.sh --verify-only                 # harness manifest check only (exit 0 ok / 2 tamper)
#   runner/score.sh <exp_id> [--lite] [--gguf <path>] [--server <url>]
#
# Defaults: --gguf = $(cat serve/current.gguf), --server = http://127.0.0.1:9021.
# Verdict JSON goes to stdout AND notes/logs/score-<exp_id>.json. Exit 2 = manifest tamper.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")/.."

PY=.venv/bin/python
[ -x "$PY" ] || PY=python3

if [ "${1:-}" = "--verify-only" ]; then
  exec "$PY" harness/score.py --verify-only
fi

EXP=${1:?usage: score.sh <exp_id> [--lite] [--gguf path] [--server url] | score.sh --verify-only}
shift

GGUF=""
SERVER="http://127.0.0.1:9021"
EXTRA=()
while [ $# -gt 0 ]; do
  case "$1" in
    --gguf)   GGUF=$2; shift 2 ;;
    --server) SERVER=$2; shift 2 ;;
    --lite)   EXTRA+=(--lite); shift ;;
    *) echo "[score.sh] unknown arg: $1" >&2; exit 64 ;;
  esac
done
if [ -z "$GGUF" ]; then
  GGUF=$(cat serve/current.gguf)
fi

mkdir -p notes/logs
OUT=notes/logs/score-${EXP}.json
set +e
"$PY" harness/score.py --exp "$EXP" --gguf "$GGUF" --server "$SERVER" ${EXTRA[@]+"${EXTRA[@]}"} | tee "$OUT"
rc=${PIPESTATUS[0]}
set -e
exit "$rc"
