#!/bin/bash
# Build the args-only llamafile sidecar for SEBK4C/Ornith-1.0-397B-Featherweight.
# Weights are NOT embedded: the .args default `-m` is a relative filename, so users drop the
# llamafile next to the GGUF. Appended user args override embedded ones (last value wins).
#
# Engine requirement (why v0.10.3, not the local Projects/llamafile tree): the GGUF is
# qwen3_5_moe — llamafile ≤0.9.x and the Mar-2025 custom build predate the arch. v0.10.3's
# synced llama.cpp has qwen35moe + --n-cpu-moe/--reasoning-budget/--jinja(default)/-fa.
# The chat template ships inside the GGUF metadata (tokenizer.chat_template), so no
# --chat-template-file is needed.
#
# Smoke-tested 2026-07-04 (CPU-only, 9B sibling GGUF via the relative -m symlink):
# health 200, non-empty completion with reasoning-budget honored.
set -euo pipefail

LLAMAFILE_VERSION=0.10.3
LLAMAFILE_URL="https://github.com/Mozilla-Ocho/llamafile/releases/download/${LLAMAFILE_VERSION}/llamafile-${LLAMAFILE_VERSION}"
OUT="Ornith-1.0-397B-Featherweight-serve.llamafile"
ZIPALIGN="${ZIPALIGN:-/usr/local/bin/zipalign}"   # from the llamafile toolchain

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
cd "$WORK"

curl -fsSL -o llamafile "$LLAMAFILE_URL"
chmod +x llamafile

# SINGLE-USER config (measured 2026-07-05: 15-18.5 t/s warm on 2x24GB): -np 1 frees scratch
# for an 11th GPU expert layer. Multi-user/eval config documented in the model card (append
# args to override: -c 163840 -np 4 --n-cpu-moe 50 -ts 50,10).
# The trailing `...` line makes user-supplied args append after (and thus override) these.
printf '%s\n' \
  --server \
  -m Ornith-1.0-397B-Featherweight-v0.gguf \
  -ngl 99 \
  --n-cpu-moe 49 \
  -ts 52,8 \
  -b 8192 \
  -ub 8192 \
  -fa on \
  --cache-type-k q8_0 \
  --cache-type-v q8_0 \
  -c 65536 \
  -np 1 \
  --reasoning-format auto \
  --reasoning-budget 1024 \
  ... \
  | tr ' ' '\n' > .args

cp llamafile "$OUT"
"$ZIPALIGN" -j0 "$OUT" .args
unzip -l "$OUT" | grep -q "\.args" || { echo "FATAL: .args not embedded"; exit 1; }
sha256sum "$OUT"
mv "$OUT" "$OLDPWD/"
echo "OK: $OLDPWD/$OUT (upload to the HF model repo next to the GGUF)"
