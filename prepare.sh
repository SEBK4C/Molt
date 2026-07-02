#!/usr/bin/env bash
# molt prepare.sh — one-time setup on llm-serve. Idempotent-ish; rerun safe steps skip.
set -euo pipefail
source ~/.config/molt/env   # HF_TOKEN, ANTHROPIC_API_KEY

ROOT=/home/seb/molt
MODELS=/mnt/proxmox/llm-serve/models/ornith
LCPP=$ROOT/vendor/llama.cpp
mkdir -p "$ROOT"/{recipes,serve,notes,harness,runner,corpora} "$MODELS"

# 1. llama.cpp pinned build (qwen3_5_moe + draft-mtp)
if [ ! -x "$LCPP/build/bin/llama-quantize" ]; then
  git clone https://github.com/ggml-org/llama.cpp "$LCPP" || true
  cmake -S "$LCPP" -B "$LCPP/build" -DGGML_CUDA=ON -DCMAKE_BUILD_TYPE=Release
  cmake --build "$LCPP/build" -j"$(nproc)" \
    --target llama-quantize llama-imatrix llama-perplexity llama-server llama-bench
fi

# 2. Python env
cd "$ROOT" && uv venv && uv pip install gguf safetensors transformers datasets evalplus numpy matplotlib

# 3. P0: BF16 originals (807 GB). NOT the FP8 repo — convert can't ingest compressed-tensors.
hf download deepreinforce-ai/Ornith-1.0-397B --local-dir "$MODELS/hf-bf16" \
  --exclude "*.msgpack" &

# 4. Corpora (small; runs while weights download)
python corpora/build_imatrix_corpus.py --mix recipes/imatrix.yaml --out corpora/imatrix.txt
python corpora/build_kld_heldout.py   --out corpora/kld_heldout.txt
wait

# 5. P1: direct Q8_0 GGUF (skip BF16 GGUF intermediate; saves 807 GB staging)
uv run python "$LCPP/convert_hf_to_gguf.py" "$MODELS/hf-bf16" \
  --outtype q8_0 --outfile "$MODELS/Ornith-Q8_0.gguf"

# 6. P2: imatrix (~1 h; prefill-only, streams 420 GB/chunk from SSD at 14 GB/s)
"$LCPP/build/bin/llama-imatrix" -m "$MODELS/Ornith-Q8_0.gguf" \
  -f corpora/imatrix.txt -o "$MODELS/imatrix-agentic.dat" -ngl 15 --chunk 512

# 7. P3: KLD reference logits
"$LCPP/build/bin/llama-perplexity" -m "$MODELS/Ornith-Q8_0.gguf" \
  -f corpora/kld_heldout.txt --kl-divergence-base "$MODELS/kld-base.out" -ngl 15

# 8. P4: baseline quant from recipes/baseline.yaml (rendered to --tensor-type flags)
uv run python runner/render_quant_cmd.py recipes/baseline.yaml \
  --imatrix "$MODELS/imatrix-agentic.dat" \
  --in "$MODELS/Ornith-Q8_0.gguf" --out "$MODELS/ornith-molt-000.gguf" | bash

# 9. Harness freeze + Phase 0
python harness/manifest.py --write
echo ">> Now: score baseline 3x -> harness/epsilon.txt; then 'git checkout -b molt/$(date +%Y%m%d)'"
echo ">> and start Claude Code: 'Read program.md and start tonight's session.'"
