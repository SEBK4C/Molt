#!/usr/bin/env bash
# molt session pre-flight — the executable version of the checks whose manual failure aborted
# session 1 (notes/abort-2026-07-02.md) + REQUIREMENTS checklist. Run before EVERY research
# session. Exit 0 = go; exit 1 = the listed checks failed (fix or abort, never fudge).
set -uo pipefail
cd /home/seb/Ai-projects/Molt

FAIL=()
ok()   { printf ' PASS  %s\n' "$1"; }
bad()  { printf ' FAIL  %s\n' "$1"; FAIL+=("$1"); }

# 1. harness manifest green (tamper => nothing else matters)
if runner/score.sh --verify-only >/dev/null 2>&1; then ok "harness manifest verified"; else bad "harness manifest (runner/score.sh --verify-only)"; fi

# 2. epsilon calibrated and sane
if [ -s harness/epsilon.txt ]; then
  EPS=$(cat harness/epsilon.txt)
  awk -v e="$EPS" 'BEGIN{exit !(e>0 && e<0.2)}' && ok "epsilon.txt = $EPS" || bad "epsilon.txt out of sane range (0,0.2): $EPS"
else bad "harness/epsilon.txt missing (run scripts/phase0_epsilon.sh)"; fi

# 3. journal exists with phase0 baseline entries
if [ -s experiments.jsonl ] && [ "$(grep -c '"tier": *"phase0"' experiments.jsonl)" -ge 3 ] 2>/dev/null; then
  ok "experiments.jsonl has >=3 phase0 entries"
else bad "experiments.jsonl missing phase0 baseline entries"; fi

# 4. GPUs available to molt (both < 1500 MiB used)
if runner/gpu_lock.sh wait-idle 1 >/dev/null 2>&1; then ok "both GPUs idle/molt-owned"; else bad "GPUs busy (nemotron restored? see TODO X-restore/HG4)"; fi

# 5. disk headroom for a candidate quant
AVAIL=$(df -B1G --output=avail /mnt/proxmox | tail -1 | tr -d ' ')
[ "$AVAIL" -ge 300 ] && ok "/mnt/proxmox ${AVAIL}G free (>=300G)" || bad "/mnt/proxmox only ${AVAIL}G free"

# 6. permanent artifacts present
[ -s models/Ornith-Q8_0.gguf ]      && ok "Q8_0 master present"    || bad "models/Ornith-Q8_0.gguf missing"
[ -s models/imatrix-agentic.dat ]   && ok "imatrix present"        || bad "models/imatrix-agentic.dat missing"

# 7. current best quant exists and respects G1
G=$(cat serve/current.gguf 2>/dev/null)
if [ -n "$G" ] && [ -s "$G" ]; then
  SZ=$(( $(stat -c%s "$G") / 1000000000 ))
  [ "$SZ" -le 121 ] && ok "current gguf $G (${SZ} GB <= 121)" || bad "current gguf ${SZ} GB > 121 GB gate"
else bad "serve/current.gguf target missing: '$G'"; fi

# 8. pinned binaries
[ -x vendor/llama.cpp/build/bin/llama-server ] && ok "vendor llama-server built ($(cat vendor/PIN 2>/dev/null | cut -c1-12))" || bad "vendor llama-server missing"

echo
if [ ${#FAIL[@]} -gt 0 ]; then
  echo "PRE-FLIGHT: ${#FAIL[@]} FAILED — do not start a session. Per contract: fix or write an abort note."
  exit 1
fi
echo "PRE-FLIGHT: ALL GREEN. Next: git checkout -b molt/$(date +%Y%m%d); agent reads program.md."
