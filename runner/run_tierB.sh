#!/usr/bin/env bash
# molt runner — Tier B experiment: full requant from the frozen Q8_0 master per
# recipes/current.yaml, then full eval (budget 4 h total).
#
# Quantize phase is disk/CPU-bound and runs nice'd WITHOUT the GPU lock (so Tier-A evals can
# pipeline on GPU); the serve+eval phase goes through run_tierA.sh --full which takes the lock.
# Output: models/ornith-molt-<exp_id>.gguf (written as .part, atomic rename).
#
# Usage: run_tierB.sh <exp_id> [--recipe recipes/current.yaml] [--keep-part]
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")/.."

EXP=${1:?usage: run_tierB.sh <exp_id> [--recipe path]}
shift
RECIPE=recipes/current.yaml
while [ $# -gt 0 ]; do
  case "$1" in
    --recipe) RECIPE=$2; shift 2 ;;
    *) echo "[tierB] unknown arg: $1" >&2; exit 64 ;;
  esac
done

runner/score.sh --verify-only

PY=.venv/bin/python; [ -x "$PY" ] || PY=python3
SRC=models/Ornith-Q8_0.gguf
IMX=models/imatrix-agentic.dat
OUT=models/ornith-molt-${EXP}.gguf
[ -f "$SRC" ] || { echo "[tierB] Q8_0 master missing: $SRC" >&2; exit 66; }
[ -f "$IMX" ] || { echo "[tierB] imatrix missing: $IMX" >&2; exit 66; }
case "$OUT" in models/*) : ;; *) echo "[tierB] refusing non-models/ output: $OUT" >&2; exit 65 ;; esac

mkdir -p notes/logs
QLOG=notes/logs/quant-${EXP}.log

if [ -f "$OUT" ]; then
  echo "[tierB] $OUT already exists — skipping quantize (check-before-do)" >&2
else
  echo "[tierB] rendering quant command from $RECIPE" >&2
  CMD=$("$PY" runner/render_quant_cmd.py "$RECIPE" --imatrix "$IMX" --in "$SRC" --out "$OUT")
  echo "[tierB] $CMD" | tee -a "$QLOG" >&2
  # nice + ionice: page cache must yield to any live llama-server (SPEC §9)
  nice -n 15 ionice -c3 bash -c "$CMD" >>"$QLOG" 2>&1 \
    || { echo "[tierB] quantize FAILED (see $QLOG tail):" >&2; tail -5 "$QLOG" >&2; exit 1; }
fi

echo "[tierB] quant done: $(du -h "$OUT" | cut -f1). Scoring (full S)..." >&2
runner/run_tierA.sh "$EXP" --full --gguf "$OUT"
echo "[tierB] NOTE: candidate at $OUT — ratchet decision (keep => update serve/current.gguf + commit; discard => delete candidate + git reset) belongs to the session agent, not this runner." >&2
