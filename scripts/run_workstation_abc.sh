#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export UV_CACHE_DIR="${UV_CACHE_DIR:-$PWD/.cache/uv-install}"
export HF_XET_CACHE=/mnt/e/CoEvo/cache/huggingface/xet
exec uv run --locked python -m coevo.workstation "$@"
