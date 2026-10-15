"""Read one explicit PilotDeck transcript as local research evidence, not training data."""
import argparse
import hashlib
import json
from pathlib import Path

from .runtime import write_json
from .sandbox import command as sandbox_command

PILOTDECK_REVISION = '783499ffdb2d501bf590b2e035acd027a882df10'


def cli_command(workspace, environment, pilot_home, application, node_root, prompt):
    """Run the upstream CLI inside the existing task filesystem boundary."""
    pilot_home, application, node_root = [Path(p).resolve() for p in (pilot_home, application, node_root)]
    args = sandbox_command(workspace, environment, [])[:-1]
    args += ['--share-net']  # loopback vLLM access; inherited proxy/credential env is cleared
    for path in (application, node_root):
        args += ['--ro-bind', str(path), str(path)]
    args += ['--bind', str(pilot_home), str(pilot_home)]
    for name in ('passwd', 'group', 'nsswitch.conf'):
        path = Path('/etc') / name
        if path.exists():
            args += ['--ro-bind', str(path), str(path)]
    args += ['--setenv', 'PILOT_HOME', str(pilot_home),
             '--setenv', 'PILOTDECK_GATEWAY_PORT', '18879',
             '--setenv', 'PILOTDECK_WORK_DIR', '/workspace/.work',
             '--setenv', 'PATH', f'{node_root}/bin:/opt/task-env/bin:/usr/bin:/bin',
             '--', str(node_root / 'bin/node'), '--import',
             str(application / 'node_modules/tsx/dist/loader.mjs'),
             str(application / 'src/cli/pilotdeck.ts'), prompt]
    return args


def extract(transcript, out, source_cluster, split='D'):
    transcript, out = Path(transcript).resolve(), Path(out).resolve()
    if out.exists():
        raise ValueError('Use a new evidence directory')
    data = transcript.read_bytes()
    if data and not data.endswith(b'\n'):
        raise ValueError('Transcript has an incomplete final record; export after it is flushed')
    records = [json.loads(line) for line in data.splitlines() if line.strip()]
    calls, observations, turns = {}, {}, {}
    for line, entry in enumerate(records, 1):
        session, turn = entry['sessionId'], entry['turnId']
        key = (session, turn)
        turns.setdefault(key, {'session_id': session, 'turn_id': turn, 'entry_lines': []})['entry_lines'].append(line)
        if entry['type'] == 'turn_result':
            turns[key]['result'] = entry['result']
        if entry['type'] not in ('assistant_message', 'tool_result_message', 'durable_message'):
            continue
        for block in entry['message'].get('content', []):
            if block['type'] == 'tool_call':
                identity = (session, turn, block['id'])
                if identity in calls:
                    raise ValueError('Duplicate tool call identity; inspect transcript boundaries')
                calls[identity] = {'line': line, 'call': block}
            elif block['type'] in ('tool_result', 'tool_result_reference'):
                identity = (session, turn, block['toolCallId'])
                observations.setdefault(identity, []).append({'line': line, 'result': block})
    transitions = [dict(session_id=s, turn_id=t, tool_call_id=i, **call,
                        observations=observations.get((s, t, i), []),
                        verification='unreviewed', train_ready=False)
                   for (s, t, i), call in calls.items()]
    summary = dict(source_cluster=source_cluster, split=split,
                   source_transcript=str(transcript), source_sha256=hashlib.sha256(data).hexdigest(),
                   format_reference_revision=PILOTDECK_REVISION,
                   entries=len(records), turns=list(turns.values()), tool_calls=len(calls),
                   calls_without_observation=sum(not x['observations'] for x in transitions),
                   observations_without_call=sum(len(v) for k, v in observations.items() if k not in calls),
                   scope='native chronology including control/restore boundaries; not an active-branch replay or verified training set')
    out.mkdir(parents=True)
    (out / 'native-transcript.jsonl').write_bytes(data)
    write_json(out / 'tool-transitions.json', transitions)
    write_json(out / 'manifest.json', summary)
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--transcript', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--source-cluster', required=True)
    parser.add_argument('--split', choices=['L', 'D', 'V', 'G'], default='D')
    args = parser.parse_args()
    print(json.dumps(extract(args.transcript, args.out, args.source_cluster, args.split)))


if __name__ == '__main__':
    main()
