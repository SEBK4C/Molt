#!/usr/bin/env bash
# Honor the teacher's owner-arbitrated GPU window (11:35-15:35Z, notes/gpu-window.claim):
# yield the chat server at window start (graceful, PID-targeted), resume at window end.
set -uo pipefail
cd /home/seb/Ai-projects/Molt
START=$(date -u -d "2026-07-05 11:35" +%s); END=$(date -u -d "2026-07-05 15:35" +%s)
now=$(date +%s)
[ $now -lt $START ] && sleep $((START - now))
echo "[yield] $(date -u +%FT%TZ) window open: stopping chat server (stop-file + PID kill)"
touch .chat-stop
PID=$(ss -ltnp 2>/dev/null | grep -oP '(?<=pid=)\d+(?=.*:4242)' | head -1)
[ -z "${PID:-}" ] && PID=$(fuser 4242/tcp 2>/dev/null | tr -d ' ')
[ -n "${PID:-}" ] && kill -INT "$PID" 2>/dev/null && echo "[yield] SIGINT -> pid $PID (chat server only)"
now=$(date +%s); [ $now -lt $END ] && sleep $((END - now))
echo "[yield] $(date -u +%FT%TZ) window closed: resuming chat"
rm -f .chat-stop
tmux send-keys -t molt:chat 'while [ ! -f .chat-stop ]; do runner/gpu_lock.sh with-gpus vendor/llama.cpp/build/bin/llama-server -m models/ornith-molt-000.gguf --alias Ornith-Featherweight --host 0.0.0.0 --port 4242 -ngl 99 --n-cpu-moe 49 -ts 52,8 -b 8192 -ub 8192 -fa on --cache-type-k q8_0 --cache-type-v q8_0 -c 65536 -np 1 -tb 32 --jinja --reasoning-format auto --reasoning-budget 1024 2>&1 | tee -a notes/logs/chat-serve.log; echo "[chat-wrapper] exited; restart in 5s (.chat-stop to stop)"; sleep 5; done' Enter
echo "[yield] chat relaunch dispatched"
