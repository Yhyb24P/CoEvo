"""Serve the pinned original model with a real 128K+ capacity."""
import argparse
import os
import subprocess
from pathlib import Path
from .runtime import read_config


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/workstation.json")
    parser.add_argument("--adapter")
    parser.add_argument("--adapter-name", default="coevo-current")
    args = parser.parse_args()
    c = read_config(args.config)
    env = os.environ.copy()
    env["HF_HOME"] = str(Path(c["cold_root"]) / "cache/huggingface")
    env["VLLM_CACHE_ROOT"] = str(Path(c["cold_root"]) / "cache/vllm")
    command = [str(Path(".venv/bin/vllm").resolve()), "serve", str(Path(c["model_path"]).resolve()),
               "--host", "127.0.0.1", "--port", "8000", "--served-model-name", c["served_model"],
               "--dtype", c["dtype"], "--max-model-len", str(c["max_model_len"]),
               "--gpu-memory-utilization", str(c["gpu_memory_utilization"]),
               "--max-num-seqs", str(c["max_num_seqs"]),
               "--max-num-batched-tokens", str(c["max_num_batched_tokens"]),
               "--enable-auto-tool-choice", "--tool-call-parser", c["tool_call_parser"],
               "--reasoning-parser", c["reasoning_parser"], "--language-model-only",
               "--enable-chunked-prefill", "--default-chat-template-kwargs", '{"enable_thinking":false}']
    if c.get("enforce_eager"):
        command.append("--enforce-eager")
    if args.adapter:
        command.extend(["--enable-lora", "--max-lora-rank", "16", "--lora-modules", f"{args.adapter_name}={Path(args.adapter).resolve()}"])
    print("Starting", " ".join(command), flush=True)
    subprocess.run(command, env=env, check=True)


if __name__ == "__main__":
    main()
