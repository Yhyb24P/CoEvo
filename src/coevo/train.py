"""Real BF16 LoRA training, constrained to independently verified L candidates."""
import argparse
import hashlib
import json
import math
import time
from pathlib import Path
from .runtime import read_config, new_run, finish_run, write_json


def admit(candidate):
    if candidate.get("split") != "L" or candidate.get("train_authorized") is not True:
        raise ValueError("Candidate has no L training authorization")
    if candidate.get('candidate_format') == 'verified_behavior_sequence_v1':
        from .sequences import admit as admit_sequence
        return admit_sequence(candidate)
    if candidate.get('candidate_format') == 'verified_tool_transition_v1':
        from .tool_corpus import admit as admit_teacher
        return admit_teacher(candidate)
    if candidate.get('candidate_format') == 'verified_behavior_v1':
        from .behavior import admit as admit_behavior
        return admit_behavior(candidate)
    evidence = Path(candidate["verifier_ref"])
    verdict = json.loads(evidence.read_text())
    if not verdict.get("passed") or verdict.get("post_state_hash") != candidate["verified_state_hash"]:
        raise ValueError("Missing or inconsistent real task verification")
    target = candidate["target"]
    if not target.get("tool_calls"):
        raise ValueError("No independently verified action target")
    for call in target.get("tool_calls", []):
        arguments = call["function"]["arguments"]
        arguments = json.loads(arguments) if isinstance(arguments, str) else arguments
        if call["function"]["name"] != "write" or json.loads(arguments["content"]) != verdict["actual"]:
            raise ValueError("Training action does not match verified output")
    if target.get("role") != "assistant":
        raise ValueError("Only verified Assistant targets may be supervised")
    return candidate


def tensor_hash(model):
    h = hashlib.sha256()
    for name, param in model.named_parameters():
        if param.requires_grad:
            h.update(name.encode())
            h.update(param.detach().float().cpu().contiguous().numpy().tobytes())
    return h.hexdigest()


def normalize_messages(messages):
    messages = json.loads(json.dumps(messages))
    for message in messages:
        for call in message.get("tool_calls", []):
            if isinstance(call["function"]["arguments"], str):
                call["function"]["arguments"] = json.loads(call["function"]["arguments"])
    return messages


def encode(tokenizer, candidate, max_length):
    if candidate.get('candidate_format') == 'verified_behavior_sequence_v1':
        from .sequences import encode as encode_sequence
        return encode_sequence(tokenizer, candidate, max_length)
    messages = normalize_messages(candidate["prefix"] + [candidate["target"]])
    prefix = tokenizer.apply_chat_template(messages[:-1], tools=candidate["tools"], tokenize=True, return_dict=False,
            add_generation_prompt=True, enable_thinking=False)
    full = tokenizer.apply_chat_template(messages, tools=candidate["tools"], tokenize=True, return_dict=False,
            add_generation_prompt=False, enable_thinking=False)
    # Refuse ambiguous templates rather than training tool/environment text.
    if full[:len(prefix)] != prefix:
        raise ValueError("Assistant generation prefix is not aligned to the training template")
    labels = [-100] * len(prefix) + full[len(prefix):]
    if len(full) > max_length:
        raise ValueError("Candidate exceeds max length; do not silently truncate necessary state")
    if not any(x != -100 for x in labels):
        raise ValueError("Empty Assistant supervision")
    return full, labels


def train(config, dataset, adapter_out, previous_adapter=None, seed=17, passes=1):
    import torch
    from transformers import AutoTokenizer, AutoModelForImageTextToText
    from peft import LoraConfig, get_peft_model, PeftModel
    c = read_config(config)
    runpath = new_run("B-train", c)
    started = time.monotonic()
    try:
        raw = [admit(json.loads(line)) for line in Path(dataset).read_text().splitlines() if line.strip()]
        if not raw:
            raise ValueError("No legal verified candidates")
        if len({x.get('candidate_id') for x in raw}) != len(raw):
            raise ValueError("Duplicate supervised target IDs")
        if passes not in [1, 2]:
            raise ValueError("Pilot allows at most two passes")
        torch.manual_seed(seed)
        tokenizer = AutoTokenizer.from_pretrained(c["model_path"], local_files_only=True)
        examples = [encode(tokenizer, x, c.get('training_max_length', 4096)) for x in raw]
        target_tokens = sum(sum(v != -100 for v in y) for _, y in examples) * passes
        if target_tokens > c.get('training_token_cap', 200000):
            raise ValueError("Supervised token cap exceeded")
        if len(examples) * passes > c.get('training_max_steps', 200000):
            raise ValueError('Training step cap exceeded')
        model = AutoModelForImageTextToText.from_pretrained(c["model_path"], local_files_only=True,
            dtype=torch.bfloat16, device_map={"": 0}, attn_implementation="sdpa")
        targets = [name for name, module in model.named_modules() if isinstance(module, torch.nn.Linear)
                   and any(name.endswith("." + suffix) for suffix in ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"])
                   and "visual" not in name and "vision" not in name]
        if not targets:
            raise ValueError("No supported text linear projections found")
        if previous_adapter:
            model = PeftModel.from_pretrained(model, previous_adapter, is_trainable=True)
        else:
            model = get_peft_model(model, LoraConfig(r=16, lora_alpha=32, lora_dropout=0.0,
                                                   target_modules=targets, task_type="CAUSAL_LM"))
        model.config.use_cache = False
        model.gradient_checkpointing_enable()
        model.enable_input_require_grads()
        trainable = [p for p in model.parameters() if p.requires_grad]
        optimizer = torch.optim.AdamW(trainable, lr=c.get('training_learning_rate', 1e-4))
        before = tensor_hash(model)
        losses, steps, grad_nonzero = [], 0, False
        model.train()
        for _ in range(passes):
            for ids, labels in examples:
                if time.monotonic() - started > c.get('training_wall_seconds', 7200):
                    raise TimeoutError("Training job exceeded two GPU-hour wall cap")
                inputs = torch.tensor([ids], device="cuda")
                target = torch.tensor([labels], device="cuda")
                optimizer.zero_grad(set_to_none=True)
                loss = model(input_ids=inputs, attention_mask=torch.ones_like(inputs), labels=target).loss
                if not math.isfinite(loss.item()):
                    raise ValueError("Non-finite training loss")
                loss.backward()
                norm = torch.nn.utils.clip_grad_norm_(trainable, 1.0).item()
                if not math.isfinite(norm):
                    raise ValueError("Non-finite gradient norm")
                grad_nonzero = grad_nonzero or norm > 0
                optimizer.step()
                steps += 1
                losses.append(loss.item())
                print(json.dumps({"step": steps, "loss": loss.item()}), flush=True)
        after = tensor_hash(model)
        if before == after or not grad_nonzero:
            raise ValueError("No actual parameter update")
        adapter_out = Path(adapter_out)
        adapter_out.mkdir(parents=True, exist_ok=True)
        model.save_pretrained(adapter_out)
        write_json(adapter_out / "coevo_training.json", {"run_id": runpath.name,
            "dataset_hash": hashlib.sha256(Path(dataset).read_bytes()).hexdigest(),
            "parent_adapter": previous_adapter, "parameters_before": before, "parameters_after": after})
        result = {"checkpoint_and_export_ref": str(adapter_out), "optimizer_steps": steps,
                  "actual_supervised_tokens": target_tokens, "actual_context_tokens": sum(len(x) for x, _ in examples)*passes,
                  "actual_sequences": len(examples)*passes, "unique_source_clusters": len({x['source_cluster_id'] for x in raw}),
                  "initial_and_final_parameter_check_ref": {"before": before, "after": after},
                  "gradient_nonzero": grad_nonzero, "training_loss": losses,
                  "expected_and_actual_trainable_modules_ref": targets,
                  "peak_gpu_allocated": torch.cuda.max_memory_allocated(),
                  "gpu_wall_hours": (time.monotonic() - started)/3600, "training_seeds": [seed]}
        result['learning_rate'] = c.get('training_learning_rate', 1e-4)
        result['behavior_target_counts'] = {kind: sum(x.get('behavior_kind', 'legacy-write') == kind for x in raw)
                                           for kind in sorted({x.get('behavior_kind', 'legacy-write') for x in raw})}
        finish_run(runpath, "completed", result)
        return result
    except Exception as exc:
        finish_run(runpath, "failed", {"error": str(exc), "failure_class": type(exc).__name__,
                   "gpu_wall_hours": (time.monotonic()-started)/3600})
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/workstation.json")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--adapter-out", required=True)
    parser.add_argument("--previous-adapter")
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--passes", type=int, default=1)
    args = parser.parse_args()
    print(json.dumps(train(args.config, args.dataset, args.adapter_out, args.previous_adapter, args.seed, args.passes)), flush=True)


if __name__ == "__main__":
    main()
