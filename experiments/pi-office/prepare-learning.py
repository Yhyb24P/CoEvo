"""Prepare the frozen Office recovery's reviewed development masks; no training.

Raw requests and reasoning remain local. Only explicitly reviewed actions receive
loss masks; the episode remains D, and the trainer's admission policy is unchanged.
"""
import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from coevo.assistant_mask import encode
from coevo.extract import native_tool_pairs
from coevo.project import hashes
from coevo.runtime import write_json
from coevo.sandbox import execute
from coevo.train import normalize_messages

ROOT = Path(__file__).resolve().parents[2]
READ = 'chatcmpl-tool-889a863dee9157e7'
REPAIR = 'chatcmpl-tool-84de4569b835296f'
VERIFY = 'chatcmpl-tool-ac28e8c89a7c284f'


def build(run, out, environment, tokenizer_path):
    run, out = Path(run).resolve(), Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    load = lambda p: json.loads(p.read_text())
    transcript, task = load(run/'transcript.json'), load(run/'task.json')
    review = load(run/'semantic-review.json')
    if task['split'] != 'D' or not review.get('semantic_review_passed'):
        raise ValueError('This frozen preparation requires the reviewed D Office recovery')
    parent = Path(task['parent_run'])
    if hashes(parent/'workspace') != task['initial_files']:
        raise ValueError('Parent files no longer match the actual continuation inputs')
    payloads = [json.loads(x) for x in (run/'payloads.jsonl').read_text().splitlines()]
    pairs = native_tool_pairs(payloads, transcript)
    selected = [p for p in pairs if p['tool_call_ids'] in ([READ], [REPAIR], [VERIFY])]
    if [p['tool_call_ids'][0] for p in selected] != [READ, REPAIR, VERIFY] or any(any(p['tool_errors']) for p in selected):
        raise ValueError('Reviewed actions are missing, reordered or failed')
    observed = next(m for m in transcript['messages'] if m.get('toolCallId') == READ)
    text = '\n'.join(p.get('text', '') for p in observed['content'] if p.get('type') == 'text')
    if text != (run/'workspace/.skills/spreadsheets/SKILL.md').read_text():
        raise ValueError('Actual Skill observation differs from the source')

    workspace = out/'replay-workspace'
    shutil.copytree(parent/'workspace', workspace)
    before = hashes(workspace)
    for pair in selected[1:]:
        call = pair['target']['tool_calls'][0]
        args = call['function']['arguments']
        args = json.loads(args) if isinstance(args, str) else args
        if call['function']['name'] != 'bash':
            raise ValueError('Frozen repair/verification must be actual bash calls')
        result = execute(workspace, environment, ['/bin/bash', '--noprofile', '--norc', '-c', args['command']],
                         out/(pair['tool_call_ids'][0]+'.log'), timeout=120)
        if result['exit_code']:
            raise ValueError('Exact recorded action did not replay successfully')
    changed = {p for p,h in hashes(workspace).items() if before.get(p) != h} | (before.keys()-hashes(workspace).keys())
    if changed != {'updated-research-ledger.xlsx'}:
        raise ValueError('Replay changed files outside the reviewed output')
    verdict = json.loads(subprocess.check_output([
        str(Path(environment).resolve()/'bin/python'), str(ROOT/'experiments/pilotdeck/check-workbook.py'),
        '--original', str(workspace/'research-ledger.xlsx'),
        '--submitted', str(workspace/'updated-research-ledger.xlsx'),
        '--results', str(workspace/'first-W0-results.json')], text=True, timeout=120))
    recorded = load(run/'workbook-verdict.json')
    if not verdict['mechanical_checks_passed'] or verdict['submitted_rows'] != recorded['submitted_rows']:
        raise ValueError('Replayed workbook differs from the accepted artifact')
    write_json(out/'replay-verdict.json', verdict)

    # The final selected request contains the actual whole preceding history.
    final = selected[-1]
    messages = final['prefix'] + [final['target']]
    indices = {}
    for cid in (READ, REPAIR, VERIFY):
        found = [i for i,m in enumerate(messages) if any(c.get('id') == cid for c in m.get('tool_calls', []))]
        if len(found) != 1:
            raise ValueError('Reviewed action cannot be located uniquely')
        index, = found
        if messages[:index] != next(p['prefix'] for p in selected if p['tool_call_ids'] == [cid]):
            raise ValueError('Combined context differs from the actual request at a target')
        indices[cid] = index
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(tokenizer_path, local_files_only=True)
    request_counts = {}
    for pair in selected:
        cid, = pair['tool_call_ids']
        native = next(m for m in transcript['messages'] if any(
            c.get('id') == cid for c in m.get('content', []) if isinstance(c, dict)))
        usage = native['usage']
        recorded = sum(usage.get(k, 0) for k in ('input', 'cacheRead', 'cacheWrite'))
        prompt = tokenizer.apply_chat_template(normalize_messages(pair['prefix']), tools=pair['tools'],
            tokenize=True, return_dict=False, add_generation_prompt=True, **pair['chat_template_kwargs'])
        if len(prompt) != recorded:
            raise ValueError('Offline prompt token count differs from the actual request usage')
        request_counts[cid] = {'offline_tokens':len(prompt), 'recorded_tokens':recorded}
    normalized = normalize_messages(messages)
    previews, previous_ids = {}, None
    for arm, ids in [('output-only', [REPAIR]), ('reviewed-turns', [READ, REPAIR, VERIFY])]:
        token_ids, labels = encode(tokenizer, normalized, final['tools'], [indices[c] for c in ids], 139264)
        if previous_ids is not None and previous_ids != token_ids:
            raise ValueError('Mask arms changed the actual context')
        previous_ids = token_ids
        previews[arm] = {'context_tokens':len(token_ids), 'supervised_tokens':sum(x != -100 for x in labels),
                         'target_indices':[indices[c] for c in ids], 'tool_call_ids':ids}
    refs = {n:hashlib.sha256((run/n).read_bytes()).hexdigest() for n in
            ['transcript.json','payloads.jsonl','task.json','semantic-review.json','workbook-verdict.json']}
    write_json(out/'reviewed-context.json', {'split':task['split'],'source_cluster':task['source_cluster'],
        'train_authorized':False,'feedback_assisted':True,'actor':'student','messages':messages,
        'tools':final['tools'],'raw_refs_sha256':refs,'mask_arms':previews,
        'reasoning_status':'actual native context, retained but not positive supervision',
        'scope':'reviewed actions within one D recovery; final answer and experience proposal excluded'})
    summary = {'split':'D','source_cluster':task['source_cluster'],'train_authorized':False,
        'feedback_assisted':True,'replayed_recorded_commands':2,'replay_artifact_matches_reviewed_rows':True,
        'mask_arms':previews,'request_token_counts':request_counts,'raw_refs_sha256':refs,
        'scope':'Same-context reviewed action masks; not complete-behavior supervision or independent learning evidence.'}
    write_json(out/'summary.json', summary)
    return summary


if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--run',required=True);p.add_argument('--out',required=True)
    p.add_argument('--environment',default='.cache/pilotdeck-office-env')
    p.add_argument('--tokenizer',default='.cache/active-model/Qwen3.5-4B')
    a=p.parse_args()
    print(json.dumps(build(a.run,a.out,a.environment,a.tokenizer),ensure_ascii=False))
