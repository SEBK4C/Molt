#!/usr/bin/env bash
# molt INF1 — uv venv + python deps (idempotent). torch is CPU-only: needed just for
# vendor/llama.cpp/convert_hf_to_gguf.py; never pull the CUDA wheels.
set -euo pipefail
cd /home/seb/Ai-projects/Molt

export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"

[ -d .venv ] || uv venv
uv pip install gguf safetensors transformers datasets evalplus numpy matplotlib \
               pyyaml pytest requests huggingface_hub
uv pip install torch --index-url https://download.pytorch.org/whl/cpu
echo "[setup_env] OK $(date -u +%FT%TZ)"
.venv/bin/python -c "import torch, gguf, yaml, evalplus; print('imports ok, torch', torch.__version__)"
