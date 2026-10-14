"""Reconstruct visible historical tasks without promoting them to verified examples."""
import argparse
import collections
import json
import re
from pathlib import Path
from .codex_export import sha
from .runtime import write_json


STEERING = re.compile(r'^(?:继续(?:执行|推进|工作)?|开始(?:推进|执行|吧)?|启动(?:任务)?|同意|可以|好的|继续吧|当前任务完成了吗|任务完成了吗|所以当前的任务完成了)[？?。.!！\s]*$')


def request_text(record):
    text = record['text'].strip()
    if text.startswith('<codex_internal_context'):
        match = re.search(r'<objective>\s*(.*?)\s*</objective>', text, re.S)
        if not match:
            return None, 'controller_notification'
        # Retain only the user-supplied objective, not control or budget instructions.
        return match.group(1).strip(), 'controller_objective'
    return text, 'user'


def reconstruct(records, session):
    episodes, current, owners = [], None, {}
    controller_skips = 0
    for record in records:
        if record.get('role') == 'user':
            text, source = request_text(record)
            if text is None:
                controller_skips += 1
                continue
            continuation = current is not None and (text == current['request'] or STEERING.fullmatch(text))
            if not continuation:
                source_id = 'codex-task-' + sha(session['session_id'] + '\n' + text)[:24]
                episode_id = sha(session['log_id'] + '\n' + str(record['source_line']))[:24]
                current = {'episode_id': episode_id, 'source_cluster_id': source_id,
                           'isolation_group': session['isolation_group'],
                           'log_id': session['log_id'], 'session_id': session['session_id'],
                           'workspace': session['workspace'], 'environment_kind': session['environment_kind'],
                           'request': text, 'request_origin': source,
                           'request_ref': {'export': session['export'], 'source_line': record['source_line']},
                           'actor': 'teacher_codex', 'split': 'unassigned', 'train_ready': False,
                           'program_family': 'unreviewed', 'historical_evaluation_exposure': 'unreviewed',
                           'outcome': 'not-independently-verified', 'input_snapshot_status': 'not-reconstructed',
                           'instruction_events': [], 'records': [], 'cross_episode_results': [],
                           'path_hints': [], 'unpaired_calls': [], 'final_response_refs': []}
                episodes.append(current)
            current['instruction_events'].append({'source_line': record['source_line'], 'text': text,
                'origin': source, 'relation': 'continuation' if continuation else 'initial-request'})
            clean = {**record, 'text': text, 'request_origin': source}
            current['records'].append(clean)
        elif record['kind'] == 'tool_result':
            owner = owners.get(record.get('call_id'))
            if owner is not None:
                owner['records'].append(record)
                if current is not owner:
                    owner['cross_episode_results'].append({'call_id': record['call_id'], 'source_line': record['source_line']})
        elif current is not None:
            current['records'].append(record)
            if record['kind'] == 'tool_call':
                owners[record.get('call_id')] = current
                if not record.get('paired'):
                    current['unpaired_calls'].append(record['call_id'])
                value = record.get('input')
                value = value if isinstance(value, str) else json.dumps(value)
                # Hints only. No recursive file access, command evaluation or outcome inference.
                hints = re.findall(r'(?:/home/|/tmp/|/mnt/)[^\s\"\'`<>;,()\\]{1,200}', value)
                current['path_hints'].extend(hints)
            if record.get('role') == 'assistant' and record.get('phase') in ('final', 'final_answer'):
                current['final_response_refs'].append(record['source_line'])
    for episode in episodes:
        episode['records'].sort(key=lambda r: r['source_line'])
        episode['path_hints'] = sorted(set(episode['path_hints']))
    return episodes, controller_skips


def build_index(export_dir, output):
    export_dir, output = Path(export_dir), Path(output)
    output.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((export_dir / 'manifest.json').read_text())
    index, reasons = [], collections.Counter()
    source_versions = collections.defaultdict(list)
    for session in manifest['sessions']:
        path = export_dir / session['export']
        if sha(path.read_text()) != session['export_sha256']:
            raise ValueError('Visible export changed after its manifest was recorded')
        records = [json.loads(line) for line in path.read_text().splitlines()]
        episodes, skipped = reconstruct(records, session)
        reasons['controller_notifications_removed'] += skipped
        for episode in episodes:
            ref = output / 'episodes' / (episode['episode_id'] + '.json')
            episode['visible_export_ref'] = str(path)
            episode['visible_export_sha256'] = session['export_sha256']
            write_json(ref, episode)
            summary = {key: episode[key] for key in ['episode_id', 'source_cluster_id', 'isolation_group',
                       'session_id', 'log_id', 'workspace', 'environment_kind', 'request_ref', 'split',
                       'program_family', 'historical_evaluation_exposure', 'input_snapshot_status']}
            summary.update(episode_ref=str(ref), record_count=len(episode['records']),
                request_characters=len(episode['request']), instruction_events=len(episode['instruction_events']),
                paired_calls=sum(r['kind'] == 'tool_call' and r.get('paired', False) for r in episode['records']),
                final_responses=len(episode['final_response_refs']),
                unpaired_calls=len(episode['unpaired_calls']), path_hints=len(episode['path_hints']),
                train_ready=False, actor='teacher_codex')
            index.append(summary)
            source_versions[episode['source_cluster_id']].append(summary)
    # A repeated snapshot is not another independent task. Keep all evidence refs,
    # nominate the largest visible context only for manual reconstruction review.
    for versions in source_versions.values():
        best = max(versions, key=lambda row: (row['record_count'], row['paired_calls']))
        for row in versions:
            row['preferred_snapshot'] = row is best
    (output / 'index.jsonl').write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in index))
    summary = {'episode_snapshots': len(index), 'source_clusters': len(source_versions),
               'sessions_with_tasks': len({r['session_id'] for r in index}),
               'source_workspaces': len({r['workspace'] for r in index}),
               'with_completed_pairs': sum(r['paired_calls'] > 0 for r in index),
               'with_visible_final_response': sum(r['final_responses'] > 0 for r in index),
               'train_ready': 0, 'counts': dict(reasons),
               'execution': 'no historical commands executed; no files beyond the exported corpus inspected'}
    write_json(output / 'summary.json', summary)
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--export', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build_index(args.export, args.output), ensure_ascii=False))


if __name__ == '__main__':
    main()
