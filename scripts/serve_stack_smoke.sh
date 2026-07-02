#!/usr/bin/env bash
# Pre-P5 stack validation: serve a SMALL same-family GGUF (ornith-9b) CPU-only on a scratch
# port and drive it through the referee's own chat()/extract_tool_calls()/gate helpers.
# Purpose: surface API-shape surprises (tool_calls population, timings presence, template
# behavior) NOW rather than during Phase-0. Read-only wrt the 9B file; llama-server is OUR
# process on :9022 and is killed on exit. Deliberately tiny CPU footprint (-t 4) so the
# GPU-assisted imatrix keeps its 32 threads mostly uncontended.
set -euo pipefail
cd /home/seb/Ai-projects/Molt

GGUF=${1:-/mnt/proxmox/llm-serve/models/ornith/ornith-9b-mtp-kl-Q6_K.gguf}
PORT=9022
SRV=vendor/llama.cpp/build/bin/llama-server
LOG=notes/logs/serve-stack-smoke.log

"$SRV" -m "$GGUF" -ngl 0 -c 4096 -t 4 -tb 4 --host 127.0.0.1 --port $PORT \
  --alias stack-smoke --jinja >"$LOG" 2>&1 &
PID=$!
trap 'kill $PID 2>/dev/null || true; wait $PID 2>/dev/null || true' EXIT

for i in $(seq 1 60); do
  curl -sf "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 && break
  kill -0 $PID 2>/dev/null || { echo "[stack-smoke] SERVER DIED during load — see $LOG:"; tail -5 "$LOG"; exit 1; }
  sleep 2
done
curl -sf "http://127.0.0.1:$PORT/health" >/dev/null || { echo "[stack-smoke] /health never ready"; exit 1; }
echo "[stack-smoke] server healthy; running referee-path checks"

.venv/bin/python - <<'EOF'
import json, sys
sys.path.insert(0, "harness")
from score import chat, extract_tool_calls

S = "http://127.0.0.1:9022"
fails = []

# 1. plain text reply
r = chat(S, [{"role": "user", "content": "Reply with exactly: STACK OK"}], max_tokens=32)
msg = r["choices"][0]["message"]
txt = (msg.get("content") or "")
print(f"1. text reply: {txt[:60]!r}")
if not txt.strip():
    fails.append("empty text reply")

# 2. usage + timings presence (g45 primary path assumption)
u, t = r.get("usage"), r.get("timings")
print(f"2. usage present: {bool(u)}; timings present: {bool(t)}"
      + (f" (prompt_per_second={t.get('prompt_per_second'):.1f}, predicted_per_second={t.get('predicted_per_second'):.1f})" if t else ""))
if not u:
    fails.append("no usage object")
if not t:
    print("   NOTE: timings absent -> g45 will use the measured-probe fallback (already implemented)")

# 3. tool call end-to-end through the real template + parser
tools = [{"type": "function", "function": {"name": "get_weather",
          "description": "Get current weather for a city",
          "parameters": {"type": "object",
                         "properties": {"city": {"type": "string"},
                                        "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]}},
                         "required": ["city"]}}}]
r2 = chat(S, [{"role": "user", "content": "Use the get_weather tool to check the weather in Paris, in celsius."}],
          tools=tools, max_tokens=256)
m2 = r2["choices"][0]["message"]
calls = extract_tool_calls(m2)
print(f"3. tool_calls raw field: {'present' if m2.get('tool_calls') else 'ABSENT (xml-in-content fallback: ' + str(bool(calls)) + ')'}")
print(f"   extracted: {json.dumps(calls, ensure_ascii=False)[:160]}")
ok = (len(calls) == 1 and calls[0]["name"] == "get_weather"
      and isinstance(calls[0]["arguments"], dict) and calls[0]["arguments"].get("city"))
if not ok:
    fails.append(f"tool-call shape unexpected: {calls}")

# 4. finish_reason sanity on tool call
print(f"4. finish_reason: {r2['choices'][0].get('finish_reason')}")

if fails:
    print("STACK-SMOKE FAIL:", "; ".join(fails)); sys.exit(1)
print("STACK-SMOKE PASS: referee chat/extraction path works against a live llama-server")
EOF
rc=$?
echo "[stack-smoke] done rc=$rc"
exit $rc
