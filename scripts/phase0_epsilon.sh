#!/usr/bin/env bash
# molt P5 — Phase-0 referee calibration: score the baseline quant 3x (full S), derive the
# eval-noise floor ε = 2σ into harness/epsilon.txt, journal the runs, then FINAL-freeze the
# manifest (epsilon.txt + any promoted refs become part of the frozen harness).
#
# PRECONDITIONS: P4 done; harness refs complete; GPUs must become idle (HUMAN gate HG4 if
# llama-swap keeps them resident — Nemotron-Cascade entry has ttl:0, it never self-unloads).
# run_tierA's gpu_lock waits for idleness; it NEVER kills foreign processes.
set -euo pipefail
cd /home/seb/Ai-projects/Molt

GGUF=models/ornith-molt-000.gguf
[ -s "$GGUF" ] || { echo "[phase0] ABORT: $GGUF missing (run P4 first)"; exit 1; }

for i in 1 2 3; do
  V=notes/logs/score-phase0-$i.json
  if [ -s "$V" ] && jq -e '.S != null' "$V" >/dev/null 2>&1; then
    echo "[phase0] run $i already scored (check-before-do): S=$(jq -r .S "$V")"
    continue
  fi
  echo "[phase0] scoring run $i/3 (full S; serve+eval under GPU lock)..."
  runner/run_tierA.sh "phase0-$i" --full --gguf "$GGUF"
  jq -e '.S != null' "$V" >/dev/null \
    || { echo "[phase0] ABORT: run $i produced no S (gates failed?) — see $V"; exit 1; }
done

.venv/bin/python - <<'EOF'
import json, statistics
ss = [json.load(open(f"notes/logs/score-phase0-{i}.json"))["S"] for i in (1, 2, 3)]
sigma = statistics.stdev(ss)
eps = 2 * sigma
with open("harness/epsilon.txt", "w") as f:
    f.write(f"{eps:.6f}\n")
print(f"[phase0] S runs: {ss}  sigma={sigma:.6f}  epsilon(2s)={eps:.6f} -> harness/epsilon.txt")
EOF

for i in 1 2 3; do
  S=$(jq -r .S notes/logs/score-phase0-$i.json)
  printf '{"id":"phase0-%s","tier":"phase0","hypothesis":"baseline replication for epsilon","gates":"pass","S":%s,"decision":"calibration","lesson":"noise floor sample"}\n' "$i" "$S" \
    | runner/journal.sh
done

echo "[phase0] FINAL manifest freeze (includes epsilon.txt + refs as they now stand)"
.venv/bin/python harness/manifest.py --write
runner/score.sh --verify-only
echo "[phase0] DONE. Session-ready: git checkout -b molt/$(date +%Y%m%d); then start the agent per program.md"
