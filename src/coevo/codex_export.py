"""Export visible Codex rollout records as local, unadmitted teacher sources.

Observed local JSONL schema, not a promised Codex API. No reasoning, event replay,
compaction, injected instructions or account metadata is copied. Export != SFT.
"""
import argparse
import collections
import hashlib
import json
import re
from pathlib import Path


def sha(value):
    return hashlib.sha256(value.encode()).hexdigest()


# Drop an entire visible record when it embeds privileged logs or credentials.
# This is a conservative first pass, not a guarantee of anonymity.
BLOCK = re.compile(r'(?i)(encrypted_content|base_instructions|"role"\s*:\s*"(?:system|developer)"|'
                   r'\.codex[/\\](?:sessions|auth|history|session_index)|'
                   r'-----BEGIN [^\n]*PRIVATE KEY-----|'
                   r'\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|password)["\']?\s*[=:]\s*["\']?[^\s"\']{8,}|'
                   r'(?:密码|密钥|令牌)\s*(?:为|是)?\s*[:：=]\s*[^\s"\']+|'
                   r'\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{16,}))')
SCAFFOLD = ('# AGENTS.md instructions', '<environment_context>', '<permissions instructions>',
            '<INSTRUCTIONS>', '<skills_instructions>', '<turn_aborted>', '<user_instructions>')


def text_values(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        yield json.dumps(value, ensure_ascii=False)
        for item in value.values():
            yield from text_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from text_values(item)


def visible(payload):
    kind = payload.get('type')
    if payload.get('channel') in ('analysis', 'summary'):
        return None, 'hidden_channel'
    if kind == 'message':
        role = payload.get('role')
        if role not in ('user', 'assistant'):
            return None, 'instruction_role'
        # Only visible text blocks; never reasoning, images, internal metadata.
        parts = [p.get('text', '') for p in payload.get('content', [])
                 if p.get('type') in ('input_text', 'output_text', 'text')]
        value = '\n'.join(parts)
        if not value:
            return None, 'no_visible_text'
        if value.lstrip().startswith(SCAFFOLD):
            return None, 'injected_scaffolding'
        record = {'kind': 'message', 'role': role, 'text': value}
        if role == 'assistant':
            phase = payload.get('phase') or payload.get('channel')
            if phase not in (None, 'final', 'commentary', 'final_answer'):
                return None, 'hidden_phase'
            record['phase'] = phase
    elif kind in ('function_call', 'custom_tool_call'):
        record = {'kind': 'tool_call', 'call_id': payload.get('call_id'),
                  'tool': payload.get('name'), 'namespace': payload.get('namespace'),
                  'input': payload.get('arguments') if kind == 'function_call' else payload.get('input')}
    elif kind in ('function_call_output', 'custom_tool_call_output'):
        record = {'kind': 'tool_result', 'call_id': payload.get('call_id'), 'output': payload.get('output')}
    else:
        return None, 'non_visible_item'
    if any(BLOCK.search(value) for value in text_values(record)):
        return None, 'sensitive_or_embedded_instructions'
    return record, None


def inventory(root):
    sessions = []
    for path in sorted(Path(root).rglob('rollout-*.jsonl')):
        with path.open() as stream:
            try:
                row = json.loads(next(stream))
            except (ValueError, StopIteration):
                continue
        if row.get('type') != 'session_meta':
            continue
        meta = row.get('payload', {})
        cwd = meta.get('cwd')
        if not cwd:
            continue
        sessions.append({'path': str(path), 'workspace': cwd,
                         'session_id': meta.get('session_id') or meta.get('id') or sha(str(path)),
                         'originator': meta.get('originator'), 'bytes': path.stat().st_size})
    return sessions


def isolation_group(workspace):
    parts = Path(workspace).parts
    if 'git_files' in parts and len(parts) > parts.index('git_files') + 1:
        project = parts[:parts.index('git_files') + 2]
        return 'codex-project-' + sha(str(Path(*project)))[:12]
    if workspace.startswith('/tmp'):
        return 'codex-temporary-unresolved'
    return 'codex-workspace-' + sha(workspace)[:12]


def export(root, destination, workspaces=None):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    sessions = inventory(root)
    if workspaces:
        sessions = [s for s in sessions if s['workspace'] in workspaces]
    excluded, totals = collections.Counter(), collections.Counter()
    indexes, fingerprints = [], collections.defaultdict(set)
    for session in sessions:
        workspace = session['workspace']
        workspace_id = sha(workspace)[:12]
        log_id = sha(session['session_id'] + '\n' + session['path'])[:24]
        output = destination / f"{log_id}.jsonl"
        counts = collections.Counter()
        source_hash = hashlib.sha256()
        calls, results = set(), set()
        records = []
        # Snapshot a bounded prefix even for a currently active append-only session.
        with Path(session['path']).open('rb') as stream:
            raw = stream.read(session['bytes'])
        source_hash.update(raw)
        for line_no, line in enumerate(raw.splitlines(), 1):
            try:
                row = json.loads(line)
            except (ValueError, UnicodeDecodeError):
                excluded['malformed_or_partial_line'] += 1
                continue
            if row.get('type') != 'response_item':
                excluded['non_response_record'] += 1
                continue
            record, reason = visible(row.get('payload', {}))
            if record is None:
                excluded[reason] += 1
                continue
            key = sha(json.dumps(record, sort_keys=True, ensure_ascii=False))
            fingerprints[key].add(log_id)
            record.update({'source_line': line_no, 'timestamp': row.get('timestamp'), 'content_hash': key,
                           'actor': 'user' if record.get('role') == 'user' else 'teacher_codex',
                           'source_cluster_id': isolation_group(workspace),
                           'split': 'unassigned', 'train_ready': False})
            counts[record['kind']] += 1
            if record['kind'] == 'tool_call':
                calls.add(record['call_id'])
            elif record['kind'] == 'tool_result':
                results.add(record['call_id'])
            records.append(record)
        # Link status is explicit; a missing result is not successful execution.
        for record in records:
            if record['kind'] in ('tool_call', 'tool_result'):
                record['paired'] = record['call_id'] in calls & results and record['call_id'] is not None
        output.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in records))
        totals.update(counts)
        indexes.append({**session, 'log_id': log_id, 'workspace_id': workspace_id, 'export': output.name,
                        'source_prefix_bytes': len(raw), 'source_prefix_sha256': source_hash.hexdigest(),
                        'export_sha256': sha(output.read_text()), 'counts': dict(counts),
                        'unpaired_calls': len(calls - results), 'unpaired_results': len(results - calls),
                        'teacher_source': True, 'split': 'unassigned', 'train_ready': False,
                        'isolation_group': isolation_group(workspace),
                        'development_overlap': 'known' if Path(workspace).name == 'CoEvo' else 'unreviewed',
                        'environment_kind': 'temporary_or_probe' if workspace.startswith('/tmp') or '/workspace-audit/' in workspace else 'persistent'})
    duplicate_groups = [sorted(v) for v in fingerprints.values() if len(v) > 1]
    manifest = {'format': 'codex_visible_teacher_v1', 'sessions': indexes,
                'totals': dict(totals), 'excluded': dict(excluded),
                'duplicate_record_groups': duplicate_groups,
                'training_candidates': 0, 'direct_H_access': False,
                'H_status': 'not selected or accessed separately; historical exposure unreviewed',
                'authorization': 'user authorized local multi-workspace export for CoEvo research',
                'admission': 'unassigned sources; review evaluation exposure, scope and outcome before splitting; adapt tool schemas and independently verify targets before training',
                'privacy': 'local only; heuristic filtering is not anonymization; no publication authorized'}
    (destination / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    return {'sessions': len(indexes), 'workspaces': len({s['workspace'] for s in indexes}),
            'totals': dict(totals), 'excluded': dict(excluded), 'duplicate_groups': len(duplicate_groups),
            'training_candidates': 0, 'destination': str(destination)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sessions-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--workspace', action='append')
    parser.add_argument('--propose-shell', action='store_true')
    args = parser.parse_args()
    summary = export(args.sessions_root, args.output, args.workspace)
    if args.propose_shell:
        summary['adaptation'] = propose_shell_targets(args.output)
    print(json.dumps(summary, ensure_ascii=False))


def propose_shell_targets(export_dir):
    """Map paired, completed native shell calls to Pi-shaped *unverified* proposals.

    Host workspaces and historical correctness need a separate task replay. No
    commands are executed here; orchestration code is not parsed or evaluated.
    """
    root = Path(export_dir)
    manifest = json.loads((root / 'manifest.json').read_text())
    counts = collections.Counter()
    proposals = []
    seen = set()
    for session in manifest['sessions']:
        records = [json.loads(line) for line in (root / session['export']).read_text().splitlines()]
        results = {r['call_id']: r for r in records if r['kind'] == 'tool_result' and r['paired']}
        user_line = None
        for record in records:
            if record.get('role') == 'user':
                user_line = record['source_line']
            if record['kind'] != 'tool_call':
                continue
            if record['tool'] != 'exec_command':
                counts['requires_other_tool_adapter'] += 1
                continue
            result = results.get(record['call_id'])
            if not result:
                counts['missing_result'] += 1
                continue
            try:
                args = json.loads(record['input'])
            except (ValueError, TypeError):
                counts['invalid_arguments'] += 1
                continue
            if not isinstance(args, dict) or not isinstance(args.get('cmd'), str):
                counts['invalid_arguments'] += 1
                continue
            text = result.get('output')
            text = text if isinstance(text, str) else json.dumps(text)
            completed = re.search(r'Process exited with code 0\b|["\']exit_code["\']\s*:\s*0\b', text)
            if not completed or re.search(r'(?i)(session_id["\']?\s*:\s*\d+|Process running)', text):
                counts['not_completed_successfully'] += 1
                continue
            if args.get('tty') or args.get('sandbox_permissions') == 'require_escalated':
                counts['requires_execution_mode_review'] += 1
                continue
            if user_line is None:
                counts['no_visible_task'] += 1
                continue
            identity = sha(record['content_hash'] + result['content_hash'] + session['isolation_group'])
            if identity in seen:
                counts['duplicate_pair'] += 1
                continue
            seen.add(identity)
            command = args['cmd']
            cwd = args.get('workdir') or session['workspace']
            if isinstance(cwd, str) and cwd.startswith('/'):
                command = command.replace(cwd, '/workspace')
            proposals.append({'proposal_format': 'codex_pi_shell_unverified_v1',
                'proposal_id': identity, 'actor': 'teacher_codex', 'split': 'unassigned',
                'train_ready': False, 'source_cluster_id': session['isolation_group'],
                'trace_ref': session['export'], 'task_source_line': user_line,
                'call_source_line': record['source_line'], 'result_source_line': result['source_line'],
                'original_workdir': cwd,
                'proposed_target': {'role': 'assistant', 'content': None, 'tool_calls': [{
                    'id': record['call_id'], 'type': 'function', 'function': {
                        'name': 'bash', 'arguments': json.dumps({'command': command}, ensure_ascii=False)}}]},
                'verification_required': ['historical evaluation exposure and permission scope',
                    'task input snapshot and host path/environment adaptation',
                    'independent output correctness, not only process success',
                    'complete prefix and task feedback reconstruction']})
    (root / 'shell-proposals.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in proposals))
    audit = {'visible_sessions': len(manifest['sessions']), 'shell_proposals': len(proposals),
             'training_candidates': 0, 'counts': dict(counts),
             'commands_executed': 0, 'qualification': 'exit status supports execution only, not semantic correctness'}
    (root / 'adaptation-audit.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2))
    return audit


if __name__ == '__main__':
    main()
