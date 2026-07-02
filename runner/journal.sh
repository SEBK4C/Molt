#!/usr/bin/env bash
# molt runner — append-only experiments.jsonl writer. The ONLY sanctioned way to write the
# journal. Takes one JSON object as $1 or on stdin; validates; appends under flock.
# Append-only by construction (fd opened O_APPEND); never truncates, never edits history.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")/.."

J=experiments.jsonl
line="${1:-$(cat)}"

# must be a single JSON object with at least id+tier; compact to one line
compact=$(printf '%s' "$line" | jq -ce '
  if (type != "object") then error("journal entry must be a JSON object")
  elif (has("id") | not) then error("journal entry missing \"id\"")
  elif (has("tier") | not) then error("journal entry missing \"tier\"")
  else . end')

exec 9>>"$J"
flock 9
printf '%s\n' "$compact" >&9
echo "[journal] appended id=$(printf '%s' "$compact" | jq -r .id) -> $J ($(wc -l < "$J") lines)" >&2
