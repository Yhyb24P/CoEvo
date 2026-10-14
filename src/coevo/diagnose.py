"""Read-only tokenizer and behavior audit of the frozen LoRA engineering pilot."""
import argparse
import hashlib
import json
from pathlib import Path

from .runtime import write_json
from .train import encode


def audit(pilot, model_path, out):
    from transformers import AutoTokenizer
    pilot = Path(pilot)
    dataset = pilot / 'learning/candidates.jsonl'
    tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
    candidates = []
    for line in dataset.read_text().splitlines():
        if not line.strip():
            continue
        candidate = json.loads(line)
        ids, labels = encode(tokenizer, candidate, 4096)
        candidates.append({'candidate_id': candidate['candidate_id'], 'prefix_aligned': True,
                           'context_tokens': len(ids), 'supervised_tokens': sum(x != -100 for x in labels),
                           'target_tools': [x['function']['name'] for x in candidate['target'].get('tool_calls', [])],
                           'has_text_target': bool(candidate['target'].get('content'))})
    panels = {}
    for panel in ['old-before', 'old-after']:
        traces = []
        for path in sorted((pilot / panel).glob('task-*/transcript.json')):
            transcript = json.loads(path.read_text())
            calls, errors, final_stop = [], 0, False
            for message in transcript['messages']:
                content = message.get('content', [])
                if message['role'] == 'assistant':
                    calls.extend(part['name'] for part in content if isinstance(part, dict) and part.get('type') == 'toolCall')
                    final_stop |= message.get('stopReason') == 'stop'
                elif message['role'] == 'toolResult':
                    errors += bool(message.get('isError'))
            traces.append({'task': path.parent.name, 'tool_sequence': calls, 'tool_error_results': errors,
                           'has_normal_stop': final_stop, 'aborted': transcript.get('aborted'),
                           'trace_sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
        panels[panel] = traces
    result = {'scope': 'frozen synthetic pilot CPU audit; no inference or training',
              'dataset_sha256': hashlib.sha256(dataset.read_bytes()).hexdigest(),
              'candidate_count': len(candidates), 'supervised_tokens': sum(x['supervised_tokens'] for x in candidates),
              'all_targets_write_only': all(x['target_tools'] == ['write'] and not x['has_text_target'] for x in candidates),
              'candidates': candidates, 'behavior_panels': panels,
              'interpretation': 'Mask prefixes align; supervision omits read/recovery/normal-stop targets. '
                                'Post-update traces include repeated and invalid tools. These observations '
                                'support a data/behavior hypothesis but do not identify the causal failure; '
                                'optimization and independent Adapter loading still require controls.'}
    write_json(out, result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--pilot', default='artifacts/rsi-pilot/cycle-1')
    parser.add_argument('--model', default='.cache/active-model/Qwen3.5-4B')
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    result = audit(args.pilot, args.model, args.out)
    print(json.dumps({key: result[key] for key in ['candidate_count', 'supervised_tokens', 'all_targets_write_only', 'interpretation']}), flush=True)


if __name__ == '__main__':
    main()
