"""Resume the pinned public original weights, using the existing proxy configuration."""
import os
from pathlib import Path

os.environ.setdefault('HF_HOME', '/mnt/e/CoEvo/cache/huggingface')
os.environ['HF_HUB_DISABLE_XET'] = '1'

from huggingface_hub import snapshot_download

snapshot_download('Qwen/Qwen3.5-4B', revision='851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a',
    local_dir=str(Path('models/Qwen3.5-4B').resolve()), token=False, max_workers=3,
    allow_patterns=['*.json', '*.safetensors', '*.jinja', '*.txt', '*.md', 'LICENSE*', '*.tiktoken', '*.model'])
