"""Target-level certificates for verified Assistant behavior in legal learning episodes."""
import json
from pathlib import Path
from .runtime import write_json
from .tasks import to_openai
from .everyday import digest, output_matches, snapshot


def task_path(value, workspace):
    value = str(value)
    if value.startswith('/workspace/'):
        return value[len('/workspace/'):]
    path = Path(value)
    if path.is_absolute():
        try:
            return str(path.relative_to(workspace))
        except ValueError:
            return None
    if '..' in path.parts:
        return None
    return str(path)


def certify(task, runpath, certificate_dir=None, include_prior_reads=False, include_prior_mutations=False):
    runpath = Path(runpath).resolve()
    verdict = json.loads((runpath / 'verdict.json').read_text())
    if task['split'] != 'L' or task['train_authorized'] is not True or verdict.get('unauthorized_changes'):
        return []
    if not verdict.get('post_state_hash'):
        return []
    if digest(snapshot(task['workspace'])) != verdict['post_state_hash']:
        raise ValueError('Workspace changed after task verification')
    transcript = json.loads((runpath / 'transcript.json').read_text())
    messages = transcript['messages']
    states_path = runpath / 'tool-states.jsonl'
    states = [json.loads(line) for line in states_path.read_text().splitlines()] if states_path.exists() else []
    prior_state_refs=[];prior_states=[]
    if include_prior_mutations:
        parent_ref=task.get('parent_run');seen=set()
        while parent_ref:
            parent_root=Path(parent_ref).resolve()
            if str(parent_root) in seen:raise ValueError('Cyclic trajectory ancestry')
            seen.add(str(parent_root));parent=json.loads((parent_root/'task.json').read_text())
            if parent['source_cluster_id']!=task['source_cluster_id'] or parent['split']!='L' or parent.get('train_authorized') is not True or parent['inputs']!=task['inputs']:
                raise ValueError('Prior actions must retain the same authorized source and inputs')
            p=parent_root/'tool-states.jsonl'
            if p.exists():
                older=[json.loads(x) for x in p.read_text().splitlines()]
                prior_states.extend(older);prior_state_refs.append({'path':str(p),'hash':digest(older)})
            parent_ref=parent.get('parent_run')
    by_call = {state['tool_call_id']: state for state in [*prior_states,*states]}
    mutators = [part['name'] for message in messages for part in message.get('content', [])
                if isinstance(part, dict) and part.get('type') == 'toolCall' and part.get('name') in ['write', 'bash']]
    certificate_dir = Path(certificate_dir).resolve() if certificate_dir else runpath
    first_target = transcript.get('continuation_start_message_index', 0)
    if include_prior_reads and first_target:
        parent=json.loads((Path(task['parent_run'])/'task.json').read_text())
        if parent['source_cluster_id']!=task['source_cluster_id'] or parent['split']!='L':
            raise ValueError('Prior reads must stay in the same legal learning source')
    tool_results = {m['toolCallId']: m for m in messages if m.get('role') == 'toolResult'}
    prefix = [{'role': 'system', 'content': transcript['system']}]
    targets, certified = {}, []
    user_turn=0;seen_readonly_bash=set()
    for index, message in enumerate(messages):
        converted = to_openai(message)
        if converted is None:
            continue
        if converted['role']=='user':user_turn+=1
        target, kind, reason = None, None, None
        prior_read = include_prior_reads and converted.get('tool_calls') and all(c['function']['name']=='read' for c in converted['tool_calls'])
        if message['role'] == 'assistant' and (index >= first_target or prior_read or include_prior_mutations):
            calls = converted.get('tool_calls', [])
            if len(calls) == 1:
                call = calls[0]
                result = tool_results.get(call['id'])
                args = json.loads(call['function']['arguments'])
                name = call['function']['name']
                if result and not result.get('isError'):
                    path = task_path(args.get('path', ''), task['workspace'])
                    if name == 'read' and path in task['inputs']:
                        content = '\n'.join(x.get('text', '') for x in result.get('content', []) if x.get('type') == 'text')
                        if content == task['inputs'][path]:
                            kind, reason = 'read', 'immutable task input and real tool return match'
                    elif name == 'read' and path in task['allowed_write_paths']:
                        content = '\n'.join(x.get('text', '') for x in result.get('content', []) if x.get('type') == 'text')
                        if output_matches(task, path, content):
                            kind, reason = 'readback', 'actual output observation independently matches the requested artifact'
                    elif name == 'write' and path in task['allowed_write_paths'] and output_matches(task, path, args.get('content', '')) and (index>=first_target or by_call.get(call['id'],{}).get('after_outputs',{}).get(path)==args.get('content')):
                        kind, reason = 'write', 'write content independently matches the requested artifact'
                    elif name == 'bash':
                        state = by_call.get(call['id'])
                        if state:
                            changed = [p for p in task['allowed_write_paths'] if state['before_outputs'].get(p) != state['after_outputs'].get(p)]
                            if changed and all(output_matches(task, p, state['after_outputs'].get(p) or '') for p in changed):
                                kind, reason = 'bash', 'successful scoped command; changed outputs verified at this step, not only at episode end'
                            elif not changed and verdict.get('passed') and index>=first_target:
                                key=(user_turn,json.dumps(args,sort_keys=True))
                                if key not in seen_readonly_bash:
                                    kind,reason='bash','nonrepeated scoped query in a verified successful episode'
                                    seen_readonly_bash.add(key)
                        elif verdict.get('passed') and mutators == ['bash']:
                            kind, reason = 'bash', 'the only mutating tool call in a verified successful episode; scoped outputs match independently'
                    if kind:
                        target = {'role': 'assistant', 'content': None, 'tool_calls': calls}
            elif len(calls)>1 and all(c['function']['name']=='read' for c in calls):
                checks=[]
                for call in calls:
                    args=json.loads(call['function']['arguments']);path=task_path(args.get('path',''),task['workspace']);result=tool_results.get(call['id'])
                    content='\n'.join(x.get('text','') for x in (result or {}).get('content',[]) if x.get('type')=='text')
                    checks.append(path in task['inputs'] and result and not result.get('isError') and content==task['inputs'][path])
                if all(checks):
                    target={'role':'assistant','content':None,'tool_calls':calls};kind='read';reason='all native batched reads match protected inputs and real returns'
            elif verdict.get('passed') and not calls and index == len(messages) - 1 and message.get('stopReason') == 'stop':
                if (converted.get('content') or '').strip().rstrip('。.!！') == '已完成':
                    target, kind, reason = converted, 'stop', 'normal final stop and explicit completion response supported by verified artifacts'
        if target:
            key = f"{task['episode_id']}-m{index}"
            targets[key] = {'target_hash': digest(target), 'prefix_hash': digest(prefix),
                            'tools_hash': digest(transcript['tools']), 'kind': kind, 'reason': reason,
                            'message_index': index, 'actor': 'student'}
            certified.append({'candidate_format': 'verified_behavior_v1', 'candidate_id': key,
                'source_cluster_id': task['source_cluster_id'], 'split': 'L', 'train_authorized': True,
                'capability_hypothesis': task.get('capability_hypothesis', 'verified workflow with reading, execution and normal stopping'),
                'prefix': prefix.copy(), 'target': target, 'tools': transcript['tools'], 'behavior_kind': kind,
                'verifier_ref': str(certificate_dir / 'behavior-verification.json'),
                'verified_state_hash': verdict['post_state_hash'],
                'raw_generation_and_tool_trace_ref': str(runpath / 'transcript.json')})
        prefix.append(converted)
    proof = {'certificate_format': 'verified_behavior_v1', 'passed': True, 'split': 'L',
             'train_authorized': True, 'source_cluster_id': task['source_cluster_id'],
             'post_state_hash': verdict['post_state_hash'], 'trace_hash': digest(transcript),
             'tool_states_hash': digest(states) if states_path.exists() else None,
             'prior_state_refs':prior_state_refs,
             'episode_passed': verdict.get('passed'),
             'targets': targets, 'evidence_kind': 'external-task-and-target-checks'}
    write_json(certificate_dir / 'behavior-verification.json', proof)
    (certificate_dir / 'behavior-candidates.jsonl').write_text(''.join(json.dumps(x, ensure_ascii=False)+'\n' for x in certified))
    return certified


def candidates_from_run(task, runpath):
    if task.get('split') != 'L' or task.get('train_authorized') is not True:
        return []
    path = Path(runpath) / 'behavior-candidates.jsonl'
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()] if path.is_file() else []


def admit(candidate):
    proof = json.loads(Path(candidate['verifier_ref']).read_text())
    if proof.get('certificate_format') != 'verified_behavior_v1' or not proof.get('passed'):
        raise ValueError('No target-level behavior certificate')
    if proof.get('split') != 'L' or proof.get('train_authorized') is not True or proof.get('source_cluster_id') != candidate['source_cluster_id']:
        raise ValueError('Behavior certificate does not authorize this learning source')
    if proof.get('post_state_hash') != candidate['verified_state_hash']:
        raise ValueError('Behavior certificate state mismatch')
    record = proof.get('targets', {}).get(candidate['candidate_id'])
    if not record or record.get('actor') != 'student' or candidate['target'].get('role') != 'assistant':
        raise ValueError('Assistant target is not individually verified')
    for field, value in [('target_hash', candidate['target']), ('prefix_hash', candidate['prefix']), ('tools_hash', candidate['tools'])]:
        if record.get(field) != digest(value):
            raise ValueError('Behavior target, prefix or schema differs from its verification')
    transcript = json.loads(Path(candidate['raw_generation_and_tool_trace_ref']).read_text())
    if proof.get('trace_hash') != digest(transcript):
        raise ValueError('Raw trace changed after verification')
    if proof.get('tool_states_hash'):
        path = Path(candidate['raw_generation_and_tool_trace_ref']).parent / 'tool-states.jsonl'
        if not path.exists() or digest([json.loads(x) for x in path.read_text().splitlines()]) != proof['tool_states_hash']:
            raise ValueError('Per-step tool states changed after verification')
    for ref in proof.get('prior_state_refs',[]):
        older=[json.loads(x) for x in Path(ref['path']).read_text().splitlines()]
        if digest(older)!=ref['hash']:raise ValueError('Ancestral action states changed after verification')
    return candidate
