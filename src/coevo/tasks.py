"""Small file-transform pilot using the upstream Agent's actual tools."""
import hashlib
import json
import os
import subprocess
from pathlib import Path
from .runtime import write_json


def make_task(directory, cycle, number, split="L"):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    values = [cycle * 11 + number, number - 3, cycle + 2, 7 - number]
    operation = ["sort", "sum", "unique"][number % 3]
    input_data = {"operation": operation, "values": values}
    expected = {"result": sorted(values) if operation == "sort" else
                sum(values) if operation == "sum" else sorted(set(values))}
    write_json(directory / "input.json", input_data)
    prompt = ("Read input.json using the read tool. If operation is sort, sort values ascending; "
              "if sum, add all values; if unique, remove duplicates then sort ascending. "
              "Use write to create output.json as JSON with exactly one key result and the calculated result. "
              "Then report completion. No other paths are authorized.")
    return {"episode_id": f"{split}-c{cycle}-n{number}", "source_cluster_id": f"{split}-c{cycle}-n{number}",
            "split": split, "program_family": f"file-{operation}", "task_family": "file-transform",
            "train_authorized": split == "L", "workspace": str(directory),
            "prompt": prompt, "expected": expected, "input_hash": hashlib.sha256((directory / "input.json").read_bytes()).hexdigest()}


def evaluate_output(task):
    path = Path(task["workspace"]) / "output.json"
    try:
        actual = json.loads(path.read_text())
        return {"passed": actual == task["expected"], "actual": actual,
                "post_state_hash": hashlib.sha256(path.read_bytes()).hexdigest()}
    except (OSError, ValueError) as exc:
        return {"passed": False, "error": str(exc)}


def execute_task(task, runpath, config, model=None, experience="", resume_file=None):
    runpath = Path(runpath).resolve()
    runpath.mkdir(parents=True, exist_ok=True)
    request = {"workspace": task["workspace"], "run_dir": str(runpath),
               "endpoint": config["endpoint"], "model": model or config["served_model"],
               "prompts": [task["prompt"]], "experience": experience,
               "context_tokens": config["max_model_len"], "max_tool_calls": 12}
    if resume_file:
        request["resume_file"] = resume_file
    write_json(runpath / "agent_request.json", request)
    env = os.environ.copy()
    env["COEVO_REQUEST_FILE"] = str(runpath / "agent_request.json")
    env["NO_PROXY"] = "127.0.0.1,localhost"
    with (runpath / "agent.log").open("w") as log:
        result = subprocess.run(["node", str(Path(".worktrees/momo-code/packages/opencode/bin/momo").resolve())],
                                env=env, stdout=log, stderr=subprocess.STDOUT, timeout=960)
    verdict = evaluate_output(task)
    verdict["agent_exit_code"] = result.returncode
    verdict["passed"] = verdict["passed"] and result.returncode == 0
    write_json(runpath / "verdict.json", verdict)
    return verdict


def to_openai(message):
    role = message["role"]
    if role in ["user", "assistant"]:
        content = message["content"]
        if isinstance(content, str):
            return {"role": role, "content": content}
        text = "\n".join(p.get("text", "") for p in content if p.get("type") == "text")
        result = {"role": role, "content": text or None}
        calls = [{"id": p["id"], "type": "function", "function": {
            "name": p["name"], "arguments": json.dumps(p["arguments"], ensure_ascii=False)}}
            for p in content if p.get("type") == "toolCall"]
        if calls:
            result["tool_calls"] = calls
        return result
    if role == "toolResult":
        return {"role": "tool", "tool_call_id": message["toolCallId"],
                "content": "\n".join(p.get("text", "") for p in message["content"] if p.get("type") == "text")}
    return None


def candidate_from_run(task, runpath):
    """Only a verified write action is supervised, never arbitrary successful-episode text."""
    if task.get('candidate_format') == 'verified_behavior_v1':
        from .behavior import candidates_from_run
        return candidates_from_run(task, runpath)
    runpath = Path(runpath)
    verdict = json.loads((runpath / "verdict.json").read_text())
    if task["split"] != "L" or not task["train_authorized"] or not verdict["passed"]:
        return []
    transcript = json.loads((runpath / "transcript.json").read_text())
    prefix = [{"role": "system", "content": transcript["system"]}]
    candidates = []
    for message in transcript["messages"]:
        converted = to_openai(message)
        if converted is None:
            continue
        if message["role"] == "assistant":
            for call in converted.get("tool_calls", []):
                args = json.loads(call["function"]["arguments"])
                if call["function"]["name"] != "write" or Path(args.get("path", "")).name != "output.json":
                    continue
                try:
                    correct = json.loads(args["content"]) == task["expected"]
                except (KeyError, ValueError):
                    correct = False
                if not correct or len(converted.get("tool_calls", [])) != 1:
                    continue
                # Text before a correct call is not automatically verified.
                target = {"role": "assistant", "content": None, "tool_calls": [call]}
                candidates.append({"candidate_id": f"{task['episode_id']}-{len(candidates)}",
                    "source_cluster_id": task["source_cluster_id"], "split": "L", "train_authorized": True,
                    "capability_hypothesis": "derive and serialize a file transformation with actual tools",
                    "prefix": prefix.copy(), "target": target, "tools": transcript["tools"], "verifier_ref": str(runpath / "verdict.json"),
                    "raw_generation_and_tool_trace_ref": str(runpath / "transcript.json"),
                    "verified_state_hash": verdict["post_state_hash"], "input_hash": task["input_hash"]})
        prefix.append(converted)
    return candidates
