"""Export recorded interactions and verified candidates without calling training."""
import argparse
import hashlib
import json
from pathlib import Path
from .runtime import write_json
from .tasks import candidate_from_run


def normalize(messages):
    inputs, outputs, thinking, calls, results = [], [], [], [], {}
    for index, message in enumerate(messages):
        role = message.get("role")
        content = message.get("content", [])
        parts = [{"type": "text", "text": content}] if isinstance(content, str) else content
        if role == "user":
            inputs.append({"message_index": index, "content": content})
        elif role == "assistant":
            outputs.append({"message_index": index, "content": content,
                            "stop_reason": message.get("stopReason"), "usage": message.get("usage")})
            for part in parts:
                if part.get("type") == "thinking":
                    thinking.append({"message_index": index, "text": part.get("thinking", "")})
                elif part.get("type") == "toolCall":
                    calls.append({"message_index": index, "id": part["id"], "name": part["name"],
                                  "arguments": part["arguments"]})
        elif role == "toolResult":
            results[message["toolCallId"]] = {"message_index": index, "content": content,
                                            "is_error": message.get("isError", False)}
    for call in calls:
        call["result"] = results.get(call["id"])
    return {"user_inputs": inputs, "assistant_outputs": outputs, "visible_thinking": thinking,
            "thinking_availability": "recorded" if thinking else "not exposed in this recording",
            "tool_calls": calls}


def read_optional(path):
    return json.loads(path.read_text()) if path.is_file() else None


def extract(root, out, origin="unspecified"):
    root, out = Path(root).resolve(), Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    records, candidates = [], []
    # Includes interrupted runs that have streaming events but no final transcript.
    folders = sorted({p.parent for name in ["transcript.json", "events.jsonl"] for p in root.rglob(name)})
    for folder in folders:
        transcript = read_optional(folder / "transcript.json")
        task = read_optional(folder / "task.json") or {}
        request = read_optional(folder / "agent_request.json") or {}
        verdict = read_optional(folder / "verdict.json")
        messages = transcript.get("messages", []) if transcript else []
        if not transcript and (folder / "events.jsonl").is_file():
            for line in (folder / "events.jsonl").read_text().splitlines():
                try:
                    event = json.loads(line)
                except ValueError:
                    continue  # An interrupted final fragment remains in the raw file.
                if event.get("type") == "message_end":
                    messages.append(event["message"])
        refs = {name: {"path": str(folder / name),
                      "sha256": hashlib.sha256((folder / name).read_bytes()).hexdigest()}
                for name in ["transcript.json", "events.jsonl", "agent_request.json", "verdict.json"]
                if (folder / name).is_file()}
        record = {"record_id": str(folder.relative_to(root)), "interaction_origin": origin,
                  "source_cluster_id": task.get("source_cluster_id"), "split": task.get("split"),
                  "train_authorized": task.get("train_authorized", False),
                  "model": request.get("model"), "request_prompts": request.get("prompts", []),
                  "system_prompt": transcript.get("system") if transcript else None,
                  "tools_schema": transcript.get("tools") if transcript else None,
                  "raw_messages": messages, "verdict": verdict,
                  "final_transcript_available": transcript is not None,
                  "aborted": transcript.get("aborted") if transcript else None,
                  "raw_refs": refs, **normalize(messages)}
        records.append(record)
        if transcript and task and verdict:
            candidates.extend(candidate_from_run(task, folder))
    for name, values in [("interactions.jsonl", records), ("candidates.jsonl", candidates)]:
        (out / name).write_text("".join(json.dumps(x, ensure_ascii=False)+"\n" for x in values))
    summary = {"input_root": str(root), "interaction_origin": origin,
               "interaction_count": len(records), "verified_candidate_count": len(candidates),
               "visible_thinking_records": sum(bool(x["visible_thinking"]) for x in records),
               "incomplete_records": sum(not x["final_transcript_available"] for x in records),
               "training_executed": False,
               "outputs": {name: str(out / name) for name in ["interactions.jsonl", "candidates.jsonl"]}}
    write_json(out / "manifest.json", summary)
    return summary


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--origin", choices=["unspecified", "synthetic-pilot", "user-interaction"], default="unspecified")
    args = p.parse_args()
    print(json.dumps(extract(args.input, args.out, args.origin), ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
