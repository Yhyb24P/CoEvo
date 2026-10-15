"""Read one explicit PilotDeck transcript as local research evidence, not training data."""
import argparse
import hashlib
import json
import os
import signal
import subprocess
import time
from pathlib import Path

from .runtime import write_json, source_snapshot
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
    bootstrap = Path(__file__).resolve().parents[2] / 'scripts/pilotdeck-task.mjs'
    args += ['--ro-bind', str(bootstrap), str(bootstrap)]
    for name in ('passwd', 'group', 'nsswitch.conf'):
        path = Path('/etc') / name
        if path.exists():
            args += ['--ro-bind', str(path), str(path)]
    args += ['--setenv', 'PILOT_HOME', str(pilot_home),
             '--setenv', 'COEVO_PILOTDECK_ROOT', str(application),
             '--setenv', 'PILOTDECK_GATEWAY_PORT', '18879',
             '--setenv', 'PILOTDECK_WORK_DIR', '/workspace/.work',
             '--setenv', 'PATH', f'{node_root}/bin:/opt/task-env/bin:/usr/bin:/bin',
             '--', str(node_root / 'bin/node'), '--import',
             str(application / 'node_modules/tsx/dist/loader.mjs'),
             str(bootstrap), prompt]
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


def run(out, application, node_root, environment, model_config, start_server=False, timeout=1800):
    """Own a bounded upstream task process and export its native transcript."""
    out = Path(out).resolve()
    if (out / 'manifest.json').exists():
        raise ValueError('Use a new prepared run; evidence must not be overwritten')
    workspace, home = out / 'workspace', out / 'pilot-home'
    args = cli_command(workspace, environment, home, application, node_root,
                       (out / 'prompt.txt').read_text())
    record = dict(status='starting', started_at=time.time(), source_snapshot=source_snapshot(),
                  code_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
                  bootstrap_sha256=hashlib.sha256(Path('scripts/pilotdeck-task.mjs').read_bytes()).hexdigest(),
                  pilotdeck_revision=PILOTDECK_REVISION, command=args, budget_seconds=timeout,
                  source_cluster='coevo-research-workbook', split='D', task_success=None)
    write_json(out / 'manifest.json', record)
    server = child = telemetry = None
    try:
        gpu = (out / 'gpu-samples.csv').open('w')
        telemetry = subprocess.Popen(['nvidia-smi', '--query-gpu=timestamp,memory.used,utilization.gpu',
                                      '--format=csv,noheader,nounits', '-l', '5'], stdout=gpu, stderr=subprocess.STDOUT)
        if start_server:
            from .rsi import Server
            server = Server(model_config, out / 'server.log')
        record.update(status='running', agent_started_at=time.time())
        write_json(out / 'manifest.json', record)
        print('PILOTDECK_TASK_STARTED', flush=True)
        started = time.monotonic()
        with (out / 'agent.log').open('w') as log:
            child = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                record['exit_code'] = child.wait(timeout=timeout)
                record['timeout'] = False
            except subprocess.TimeoutExpired:
                record['timeout'] = True
                os.killpg(child.pid, signal.SIGTERM)
                record['exit_code'] = child.wait(timeout=15)
        record['agent_wall_seconds'] = time.monotonic() - started
        record['transcript_exports'], record['extraction_errors'] = [], []
        for index, path in enumerate(sorted(home.glob('projects/*/chats/*.jsonl'))):
            try:
                summary = extract(path, out / f'evidence-{index}', record['source_cluster'])
                record['transcript_exports'].append(summary)
            except Exception as error:
                record['extraction_errors'].append({'path': str(path), 'error': str(error)})
        record['outputs'] = {str(p.relative_to(workspace)): hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in workspace.glob('*') if p.is_file()}
        record['status'] = 'execution_terminal'
    except BaseException as error:
        record.update(status='failed', error=str(error))
        raise
    finally:
        if child and child.poll() is None:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait(timeout=15)
        if server:
            server.stop()
        if telemetry:
            telemetry.terminate()
            telemetry.wait(timeout=10)
            gpu.close()
        record['ended_at'] = time.time()
        write_json(out / 'manifest.json', record)
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--transcript')
    parser.add_argument('--out', required=True)
    parser.add_argument('--source-cluster')
    parser.add_argument('--split', choices=['L', 'D', 'V', 'G'], default='D')
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--application', default='.cache/pilotdeck')
    parser.add_argument('--node-root')
    parser.add_argument('--environment', default='.cache/pilotdeck-office-env')
    parser.add_argument('--model-config', default='configs/complete-work-qwen.json')
    parser.add_argument('--start-server', action='store_true')
    parser.add_argument('--timeout', type=int, default=1800)
    args = parser.parse_args()
    if args.run:
        if not args.node_root or not 0 < args.timeout <= 7200:
            parser.error('run requires --node-root and a positive timeout <= 7200 seconds')
        result = run(args.out, args.application, args.node_root, args.environment,
                     args.model_config, args.start_server, args.timeout)
    else:
        if not args.transcript or not args.source_cluster:
            parser.error('export requires --transcript and --source-cluster')
        result = extract(args.transcript, args.out, args.source_cluster, args.split)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
