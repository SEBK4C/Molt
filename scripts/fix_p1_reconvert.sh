#!/usr/bin/env bash
# Fix for the 2026-07-02 P1 defect: Ornith's BF16 repo declares an MTP head in
# text_config (mtp_num_hidden_layers: 1) but ships NO mtp.* weights, so a default convert
# writes block_count=61 + nextn_predict_layers=1 with zero blk.60 tensors -> unloadable
# ("missing tensor blk.60.attn_norm.weight"). Remedy: --no-mtp re-convert (upstream-sanctioned),
# verify metadata + load, swap files WITHOUT deleting (>50 GB deletions are HUMAN gate HG2),
# then resume the P2-P4 chain. Safe to rerun (check-before-do throughout).
set -euo pipefail
cd /home/seb/Ai-projects/Molt

M=models
PY=.venv/bin/python
LCPP=vendor/llama.cpp

# 0. llama-tokenize was missing from the original build target list — build it
[ -x "$LCPP/build/bin/llama-tokenize" ] || cmake --build "$LCPP/build" -j"$(nproc)" --target llama-tokenize

# 1. re-convert trunk WITHOUT the phantom MTP head
if [ -s "$M/Ornith-Q8_0.no-mtp.gguf" ]; then
  echo "[fix_p1] re-convert output already exists — skipping convert"
elif [ -s "$M/Ornith-Q8_0.gguf" ] && [ -e "$M/Ornith-Q8_0.BAD-phantom-mtp.gguf" ]; then
  echo "[fix_p1] swap already happened on a previous run — skipping convert"
else
  rm -f "$M/Ornith-Q8_0.no-mtp.gguf.part"
  nice -n 10 $PY "$LCPP/convert_hf_to_gguf.py" "$M/hf-bf16" --no-mtp \
    --outtype q8_0 --outfile "$M/Ornith-Q8_0.no-mtp.gguf.part" 2>&1 | tee -a notes/logs/p1-convert-nomtp.log
  mv "$M/Ornith-Q8_0.no-mtp.gguf.part" "$M/Ornith-Q8_0.no-mtp.gguf"
fi

# 2. verify metadata + loadability on whichever file is the fresh trunk
TRUNK="$M/Ornith-Q8_0.no-mtp.gguf"
[ -s "$TRUNK" ] || TRUNK="$M/Ornith-Q8_0.gguf"
$PY - "$TRUNK" <<'EOF'
import sys
from gguf import GGUFReader
r = GGUFReader(sys.argv[1])
kv = {f.name: f for f in r.fields.values()}
bc = kv["qwen35moe.block_count"].contents()
assert bc == 60, f"block_count={bc}, want 60"
assert not any("nextn" in k for k in kv), "nextn_predict_layers still present"
print(f"[fix_p1] metadata OK: block_count=60, no nextn keys ({sys.argv[1]})")
EOF
"$LCPP/build/bin/llama-tokenize" -m "$TRUNK" -f harness/prompts/ctx32k.txt --show-count 2>&1 \
  | tail -3 | tee notes/logs/p1-tokencount.log

# 3. swap: bad file ASIDE (deletion needs HG2), fixed file takes the canonical name
if [ -s "$M/Ornith-Q8_0.no-mtp.gguf" ]; then
  if [ -s "$M/Ornith-Q8_0.gguf" ] && [ ! -e "$M/Ornith-Q8_0.BAD-phantom-mtp.gguf" ]; then
    mv "$M/Ornith-Q8_0.gguf" "$M/Ornith-Q8_0.BAD-phantom-mtp.gguf"
    echo "[fix_p1] bad file parked as Ornith-Q8_0.BAD-phantom-mtp.gguf (HG2 to delete, frees 421 GB)"
  fi
  mv "$M/Ornith-Q8_0.no-mtp.gguf" "$M/Ornith-Q8_0.gguf"
fi
echo "[fix_p1] canonical trunk ready: $(du -h "$M/Ornith-Q8_0.gguf" | cut -f1)"

# 4. resume P2-P4 (P1 skips via its own check-before-do)
exec ./scripts/post_download_chain.sh
