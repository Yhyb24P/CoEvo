#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export UV_CACHE_DIR=/mnt/e/CoEvo/cache/uv
export HF_HOME=/mnt/e/CoEvo/cache/huggingface
exec uv run --locked python -m coevo.workstation "$@"
