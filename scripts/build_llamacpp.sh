#!/usr/bin/env bash
# molt INF2 — pinned llama.cpp build under vendor/. Build is CPU+nvcc only (no GPU needed);
# does not touch the user's /home/seb/llama.cpp serving Nemotron.
set -euo pipefail
cd /home/seb/Ai-projects/Molt
LCPP=vendor/llama.cpp

export PATH="/usr/local/cuda-12.8/bin:$PATH"

if [ ! -d "$LCPP/.git" ]; then
  git clone --depth 50 https://github.com/ggml-org/llama.cpp "$LCPP"
fi

cmake -S "$LCPP" -B "$LCPP/build" -DGGML_CUDA=ON -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_CUDA_ARCHITECTURES=89 -DLLAMA_CURL=OFF
cmake --build "$LCPP/build" -j"$(nproc)" \
      --target llama-quantize llama-imatrix llama-perplexity llama-server llama-bench llama-cli

git -C "$LCPP" rev-parse HEAD > vendor/PIN
echo "[build_llamacpp] pinned $(cat vendor/PIN)"

# sanity: the flags the spec depends on must exist in this build
# (grep WITHOUT -q: -q exits early -> SIGPIPE kills the producer under pipefail -> false alarm)
"$LCPP/build/bin/llama-server" --help 2>&1 | grep 'spec-type' >/dev/null \
  && echo "[build_llamacpp] --spec-type present" \
  || echo "[build_llamacpp] WARNING: --spec-type NOT in llama-server --help (MTP draft unavailable?)"
"$LCPP/build/bin/llama-quantize" --help 2>&1 | grep 'tensor-type' >/dev/null \
  && echo "[build_llamacpp] --tensor-type present" \
  || echo "[build_llamacpp] WARNING: --tensor-type NOT in llama-quantize --help"
echo "[build_llamacpp] OK $(date -u +%FT%TZ)"
