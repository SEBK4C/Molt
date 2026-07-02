#!/usr/bin/env bash
# molt status logger — one snapshot every 30 s, displayed live in tmux window `molt:status`
# AND appended to notes/logs/proc-status.log (persisted; gitignored like all logs).
# Read it live:   tmux attach -t molt   (then pick the `status` window)
# Read the log:   tail -f notes/logs/proc-status.log
cd /home/seb/Ai-projects/Molt
LOG=notes/logs/proc-status.log

snapshot() {
  echo "═════ $(date -u +%FT%TZ) ═════"
  echo "── molt processes (pid %cpu %mem elapsed cmd) ──"
  ps -eo pid,pcpu,pmem,etimes,args --sort=-pcpu \
    | grep -E 'convert_hf_to_gguf|llama-(imatrix|perplexity|quantize|server|tokenize|bench)|download_397b|huggingface-cli download' \
    | grep -vE 'grep|proc_status' | awk '{printf "%8s %5s%% %5s%% %6ss  ", $1,$2,$3,$4; for(i=5;i<=NF&&i<12;i++) printf "%s ",$i; print ""}' \
    || echo "  (no molt jobs running)"
  echo "── load / cpu ──"
  echo "  loadavg: $(cat /proc/loadavg)"
  echo "── gpu (held by Nemotron unless HG4 freed them) ──"
  nvidia-smi --query-gpu=index,utilization.gpu,memory.used,memory.total --format=csv,noheader | sed 's/^/  /'
  echo "── disk ──"
  df -h /mnt/proxmox / | tail -2 | sed 's/^/  /'
  for p in models/*.part; do [ -e "$p" ] && echo "  in-flight: $(du -h "$p" | cut -f1)  $p"; done
  echo "── current chain step (last 2 log lines) ──"
  tr '\r' '\n' < notes/logs/molt-chain.log 2>/dev/null | grep -vE '^\s*$' | tail -2 | sed 's/^/  /'
  [ -f notes/logs/p2-imatrix.log ] && tr '\r' '\n' < notes/logs/p2-imatrix.log | grep -E 'compute_imatrix.*chunk|save' | tail -1 | sed 's/^/  imatrix: /'
  echo
}

echo "[proc_status] started $(date -u +%FT%TZ), 30 s cadence, log: $LOG"
while true; do
  snapshot | tee -a "$LOG"
  sleep 30
done
