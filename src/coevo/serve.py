"""Serve the pinned original model with a real 128K+ capacity."""
import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from .runtime import read_config


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/workstation.json")
    parser.add_argument("--adapter")
    parser.add_argument("--adapter-name", default="coevo-current")
    args = parser.parse_args()
    c = read_config(args.config)
    endpoint = urlsplit(c["endpoint"])
    env = os.environ.copy()
    env["HF_XET_CACHE"] = str(Path(c["cold_root"]) / "cache/huggingface/xet")
    env["VLLM_CACHE_ROOT"] = str(Path(c["cold_root"]) / "cache/vllm")
    command = [str(Path(".venv/bin/vllm").resolve()), "serve", str(Path(c["model_path"]).resolve()),
               "--host", endpoint.hostname, "--port", str(endpoint.port), "--served-model-name", c["served_model"],
               "--dtype", c["dtype"], "--max-model-len", str(c["max_model_len"]),
               "--gpu-memory-utilization", str(c["gpu_memory_utilization"]),
               "--max-num-seqs", str(c["max_num_seqs"]),
               "--max-num-batched-tokens", str(c["max_num_batched_tokens"]),
               "--enable-auto-tool-choice", "--tool-call-parser", c["tool_call_parser"],
               "--reasoning-parser", c["reasoning_parser"], "--language-model-only",
               "--enable-chunked-prefill", "--default-chat-template-kwargs",
               json.dumps({'enable_thinking': bool(c.get('enable_thinking', False))}, separators=(',', ':'))]
    if c.get("enforce_eager"):
        command.append("--enforce-eager")
    if c.get("trust_remote_code"):
        command.append("--trust-remote-code")
    if c.get("chat_template"):
        command.extend(["--chat-template", str(Path(c['chat_template']).resolve())])
    if args.adapter:
        command.extend(["--enable-lora", "--max-lora-rank", "16", "--lora-modules", f"{args.adapter_name}={Path(args.adapter).resolve()}"])
    print("Starting", " ".join(command), flush=True)
    # Keep the supervised PID as the actual API process. A disposable wrapper
    # can otherwise exit before its HTTP child finishes graceful shutdown.
    os.execvpe(command[0], command, env)


if __name__ == "__main__":
    main()
