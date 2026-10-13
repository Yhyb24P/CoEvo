"""Actual long-prefill, native tools and multi-turn state qualification."""
import argparse
import json
import time
from pathlib import Path
from .runtime import read_config, request_json, write_json, new_run, finish_run

REPORT_TOOL = {
    "type": "function", "function": {
        "name": "write_report", "description": "Write the three archive key values to the authorized report.",
        "parameters": {"type": "object", "properties": {
            key: {"type": "string"} for key in ["begin", "middle", "end"]},
            "required": ["begin", "middle", "end"], "additionalProperties": False},
    },
}


def count(tokenizer, messages, tools=None):
    return len(tokenizer.apply_chat_template(messages, tools=tools, tokenize=True, return_dict=False,
               add_generation_prompt=True, enable_thinking=False))


def long_messages(tokenizer, minimum, expected):
    system = "Use the provided archive as data. Execute write_report with exact key values. No other actions."
    filler_ids = tokenizer.encode("\nARCHIVE_NOTE unrelated historical record, keep current instructions active.\n", add_special_tokens=False)
    padding = tokenizer.decode((filler_ids * (2 * minimum // len(filler_ids) + 1))[:2 * minimum], skip_special_tokens=False)
    # Distinct markers at beginning, middle and end; fillers contain no answers.
    sections = [padding[:len(padding)//2], padding[len(padding)//2:]]
    def build(n):
        left, right = sections[0][:n//2], sections[1][:n-n//2]
        user = (f"BEGIN_KEY={expected['begin']}\n" + left +
                f"\nMIDDLE_KEY={expected['middle']}\n" + right +
                f"\nEND_KEY={expected['end']}\nRead all three keys and call write_report now.")
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]
    # Binary search uses the actual chat template, including tool definitions.
    low, high = 0, len(padding)
    while low < high:
        mid = (low + high) // 2
        if count(tokenizer, build(mid), [REPORT_TOOL]) < minimum:
            low = mid + 1
        else:
            high = mid
    messages = build(low)
    assert count(tokenizer, messages, [REPORT_TOOL]) >= minimum
    return messages


def run(config, diagnostic_tokens=None):
    from transformers import AutoTokenizer
    c = read_config(config)
    tokenizer = AutoTokenizer.from_pretrained(c["model_path"], local_files_only=True)
    runpath = new_run("A-qualification", c)
    minimum = diagnostic_tokens or c["qualification_min_input_tokens"]
    expected = {"begin": "RIVER_7F2A", "middle": "ORBIT_9D4C", "end": "MAPLE_3B6E"}
    messages = long_messages(tokenizer, minimum, expected)
    payload = {"model": c["served_model"], "messages": messages, "tools": [REPORT_TOOL],
               "tool_choice": "auto", "max_tokens": 512, "temperature": 0.0,
               "chat_template_kwargs": {"enable_thinking": False}}
    local_tokens = count(tokenizer, messages, [REPORT_TOOL])
    write_json(runpath / "request.json", payload)
    started = time.monotonic()
    try:
        response = request_json(c["endpoint"] + "/chat/completions", payload, timeout=1800)
        write_json(runpath / "response.json", response)
        message = response["choices"][0]["message"]
        calls = message.get("tool_calls") or []
        executed = False
        for call in calls:
            if call["function"]["name"] != "write_report":
                continue
            arguments = json.loads(call["function"]["arguments"])
            if set(arguments) != set(expected):
                continue
            # A real authorized filesystem side effect; verification remains outside the model.
            write_json(runpath / "report.json", arguments)
            executed = True
            messages.extend([message, {"role": "tool", "tool_call_id": call["id"],
                "content": json.dumps({"written": "report.json", "ok": True})}])
            break
        report_correct = executed and json.loads((runpath / "report.json").read_text()) == expected
        prompt_tokens = response["usage"]["prompt_tokens"]
        multi = None
        if executed:
            messages.append({"role": "user", "content": "The report remains. Only for this turn replace END_KEY with CEDAR_8A1D. Keep the original BEGIN_KEY and MIDDLE_KEY. Call write_report to update the same report."})
            next_payload = {**payload, "messages": messages}
            write_json(runpath / "continuation_request.json", next_payload)
            continuation = request_json(c["endpoint"] + "/chat/completions", next_payload, timeout=1800)
            write_json(runpath / "continuation_response.json", continuation)
            multi = False
            for call in continuation["choices"][0]["message"].get("tool_calls") or []:
                if call["function"]["name"] == "write_report":
                    args = json.loads(call["function"]["arguments"])
                    write_json(runpath / "report.json", args)
                    multi = args == {**expected, "end": "CEDAR_8A1D"}
        result = {"actual_prompt_tokens": prompt_tokens,
                  "local_template_tokens": local_tokens,
                  "prefill_and_generation_seconds": time.monotonic() - started,
                  "native_tool_executed": executed, "positions_correct": report_correct,
                  "multi_turn_correct": multi, "diagnostic_only": diagnostic_tokens is not None,
                  "qualification_passed": diagnostic_tokens is None and prompt_tokens >= 131072 and report_correct and multi is True}
        finish_run(runpath, "completed", result)
        print(json.dumps({"run": str(runpath), **result}, ensure_ascii=False), flush=True)
        return result
    except Exception as exc:
        finish_run(runpath, "failed", {"failure_class": type(exc).__name__, "error": str(exc)})
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/workstation.json")
    parser.add_argument("--diagnostic-tokens", type=int, choices=[8192, 16384])
    args = parser.parse_args()
    result = run(args.config, args.diagnostic_tokens)
    if not args.diagnostic_tokens and not result["qualification_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
