"""Resettable Marko development task; student execution and external checks stay separate."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from .runtime import read_config, source_snapshot, write_json
from .sandbox import command, execute


MARKO_REVISION = "1cc1583dd38bc41fecc113e56df4ce9d2d693efa"
PROMPT = """Maintain the Marko Markdown tool in this independent workspace.
Add --input-encoding and --output-encoding to its CLI. Both default to utf-8.
The input option controls reading a document file; the output option controls
writing an output file. Stdin and stdout retain their existing behavior.
Support codec names recognized by Python, including latin-1 and utf-8-sig.
Retain existing parser, renderer, extension, output and version options.
Update CLI help and add focused tests for non-UTF-8 input/output and defaults.
Do not change existing conversion semantics. Run appropriate tests using bash.
All project files in this disposable workspace may be edited. No other paths,
network access, package installation, or changes to external state are authorized.
Use relative paths for read/write. Bash runs in /workspace with python and pytest
already installed. Inspect the code before editing. Stop and report the actual
result after testing; a failed test is feedback, not a successful completion.
"""

CLI_CHECK = r'''
import pathlib, subprocess, sys, tempfile
import marko
with tempfile.TemporaryDirectory() as tmp:
    root = pathlib.Path(tmp)
    cases = [('utf-8', 'utf-8', '# café\n'), ('latin-1', 'utf-8', '# café\n'),
             ('utf-8', 'latin-1', '# café\n'), ('utf-8-sig', 'utf-8', '# café\n')]
    for number, (source, target, text) in enumerate(cases):
        infile, outfile = root / f'{number}.md', root / f'{number}.html'
        infile.write_bytes(text.encode(source))
        result = subprocess.run([sys.executable, '-m', 'marko', str(infile), '-o', str(outfile),
            '--input-encoding', source, '--output-encoding', target], capture_output=True, timeout=10)
        assert result.returncode == 0, (number, result.stderr.decode(errors='replace'))
        assert outfile.read_bytes() == marko.convert(text).encode(target), number
    infile, outfile = root / 'default.md', root / 'default.html'
    infile.write_text('# café\n', encoding='utf-8')
    result = subprocess.run([sys.executable, '-m', 'marko', str(infile), '-o', str(outfile)],
                            capture_output=True, timeout=10)
    assert result.returncode == 0
    assert outfile.read_bytes() == marko.convert(infile.read_text()).encode('utf-8')
    result = subprocess.run([sys.executable, '-m', 'marko'], input=b'# stdin\n', capture_output=True, timeout=10)
    assert result.returncode == 0 and result.stdout == (marko.convert('# stdin\n') + '\n').encode()
    for option in ['--input-encoding', '--output-encoding']:
        result = subprocess.run([sys.executable, '-m', 'marko', str(infile), '-o', str(outfile),
                                 option, 'not-a-real-codec'], capture_output=True, timeout=10)
        assert result.returncode != 0, option
print('PASS: 4 explicit encoding cases, default file I/O, stdin/stdout, 2 invalid-codec cases')
'''


def hashes(directory):
    return {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(Path(directory).rglob('*')) if p.is_file() and not p.is_symlink()
            and '__pycache__' not in p.parts and '.pytest_cache' not in p.parts}


def prepare(out, source, environment):
    out, source = Path(out).resolve(), Path(source).resolve()
    revision = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != MARKO_REVISION:
        raise ValueError('Source revision differs from the registered task baseline')
    if out.exists():
        raise ValueError('Use a new run directory; previous task evidence must not be overwritten')
    out.mkdir(parents=True)
    workspace = out / 'workspace'
    shutil.copytree(source, workspace, ignore=shutil.ignore_patterns('.git', '__pycache__', '*.pyc'))
    task = {'episode_id': 'D-marko-cli-encoding-v2', 'source_cluster_id': 'marko-cli-encoding-v1',
            'program_family': 'cli-file-encoding', 'split': 'D', 'train_authorized': False,
            'interaction_origin': 'researcher-task', 'actor': 'student', 'prompt_actor': 'researcher',
            'teacher_assisted': False,
            'source_repository': 'https://github.com/frostming/marko', 'source_revision': revision,
            'workspace': str(workspace), 'task_environment': str(Path(environment).resolve()),
            'prompt': PROMPT, 'initial_files': hashes(workspace), 'created_at': time.time(),
            'scope': 'development feasibility; no learning or H evaluation',
            'acceptance': ['requested encoding behavior', 'frozen upstream regression',
                           'focused Python tests added or updated', 'normal student stop within budget'],
            'budget': {'max_tool_calls': 24, 'timeout_ms': 300000, 'max_output_tokens': 4096}}
    write_json(out / 'task.json', task)
    return task


def verify(out, source, environment):
    out = Path(out).resolve()
    workspace = out / 'workspace'
    package = workspace / 'marko'
    if package.is_symlink() or any(p.is_symlink() for p in package.rglob('*')):
        raise ValueError('Symlink in the student package')
    # Frozen upstream tests are copied from the registered source, never from student edits.
    clean = out / 'verification-workspace'
    shutil.copytree(source, clean, ignore=shutil.ignore_patterns('.git', '__pycache__', '*.pyc'))
    shutil.rmtree(clean / 'marko')
    shutil.copytree(workspace / 'marko', clean / 'marko', symlinks=True)
    results = {
        'upstream_regression': execute(clean, environment, ['python', '-m', 'pytest', '-q', '-p', 'no:cacheprovider', 'tests'],
                                       out / 'upstream-regression.log', readonly=True),
        'requested_behavior': execute(clean, environment, ['python', '-c', CLI_CHECK],
                                      out / 'requested-behavior.log', readonly=True),
    }
    task = json.loads((out / 'task.json').read_text())
    current = hashes(workspace)
    results['changed_files'] = sorted(p for p in current.keys() | task['initial_files'].keys()
                                      if current.get(p) != task['initial_files'].get(p))
    results['submitted_test_files'] = [p for p in results['changed_files'] if p.startswith('tests/')
                                       and p.endswith('.py') and p in current]
    results['submitted_tests'] = execute(workspace, environment,
        ['python', '-m', 'pytest', '-q', '-p', 'no:cacheprovider', *results['submitted_test_files']],
        out / 'submitted-tests.log', readonly=True) if results['submitted_test_files'] else None
    results['passed'] = (all(x['exit_code'] == 0 for x in [results['upstream_regression'], results['requested_behavior']])
                         and bool(results['submitted_test_files']) and results['submitted_tests']['exit_code'] == 0)
    results['feedback_origin'] = 'external-executable-checks'
    results['training_executed'] = False
    write_json(out / 'verdict.json', results)
    return results


def run(out, source, environment, config, start_server=False, resume_run=None):
    out = Path(out).resolve()
    if resume_run:
        parent = Path(resume_run).resolve()
        previous = json.loads((parent / 'task.json').read_text())
        verdict = json.loads((parent / 'verdict.json').read_text())
        if verdict['requested_behavior']['exit_code'] != 0 or verdict['upstream_regression']['exit_code'] != 0:
            raise ValueError('This continuation is only for the observed missing-tests/budget failure')
        if out.exists():
            raise ValueError('Continuation requires a new run directory')
        out.mkdir(parents=True)
        shutil.copytree(parent / 'workspace', out / 'workspace', symlinks=True)
        feedback = ('External executable feedback: requested encoding behavior passed, and all 1436 frozen '
                    'upstream tests passed. No focused Python tests were submitted, and the previous run '
                    'ended at its tool budget. Continue from the existing functional implementation. '
                    'Add focused tests under tests/ for Latin-1 input/output, UTF-8 BOM input and defaults. '
                    'Run those tests and report the actual result, then stop. Do not enumerate all encodings '
                    'or rewrite the working implementation unnecessarily. This continuation allows at most '
                    '12 additional tool calls and 180 seconds. Use python -m marko for the CLI.')
        task = {**previous, 'episode_id': previous['episode_id'] + '-feedback-1',
                'workspace': str(out / 'workspace'), 'prompt': feedback, 'prompt_actor': 'external-checker',
                'parent_run_ref': str(parent), 'feedback_assisted': True, 'created_at': time.time(),
                'initial_files': hashes(out / 'workspace'),
                'budget': {'max_tool_calls': 12, 'timeout_ms': 180000, 'max_output_tokens': 4096}}
        write_json(out / 'task.json', task)
    else:
        task = prepare(out, source, environment)
    c = read_config(config)
    request = {**task['budget'], 'workspace': task['workspace'], 'run_dir': str(out),
               'task_environment': task['task_environment'], 'endpoint': c['endpoint'],
               'model': c['served_model'], 'context_tokens': c['max_model_len'], 'prompts': [task['prompt']],
               'pi_entry': str(Path('.worktrees/momo-code/packages/opencode/node_modules/@earendil-works/pi-coding-agent/dist/index.js').resolve()),
               'sandbox_prefix': command(task['workspace'], environment, []),
               'system_prompt': 'You are a local coding agent. Complete the current authorized task with actual read, write and bash tools. Treat tool results as observations. Report tested outcomes accurately.'}
    if resume_run:
        request['resume_file'] = json.loads((Path(resume_run) / 'transcript.json').read_text())['session_file']
    write_json(out / 'agent_request.json', request)
    for path in [*Path('src/coevo').glob('*.py'), Path('scripts/pi-project-agent.mjs'),
                 Path('experiments/project-tasks/requirements.txt'), Path(config), Path('pyproject.toml'), Path('uv.lock')]:
        destination = out / 'source-snapshot' / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
    write_json(out / 'manifest.json', {'task': task['episode_id'], 'source_snapshot': source_snapshot(),
               'config': c, 'task_environment_lock_hash': hashlib.sha256(Path('experiments/project-tasks/requirements.txt').read_bytes()).hexdigest(),
               'adapter_hash': hashlib.sha256(Path('scripts/pi-project-agent.mjs').read_bytes()).hexdigest(),
               'source_snapshot_ref': str(out / 'source-snapshot'),
               'pi_entry_hash': hashlib.sha256(Path(request['pi_entry']).read_bytes()).hexdigest(),
               'student_model': c['served_model'], 'start_time': time.time(), 'run_status': 'running'})
    server = None
    try:
        if start_server:
            from .rsi import Server
            server = Server(config, out / 'server.log')
        env = {**os.environ, 'COEVO_REQUEST_FILE': str(out / 'agent_request.json'), 'NO_PROXY': '127.0.0.1,localhost'}
        with (out / 'agent.log').open('w') as log:
            child = subprocess.run(['node', str(Path('scripts/pi-project-agent.mjs').resolve())], env=env,
                                   stdout=log, stderr=subprocess.STDOUT, timeout=task['budget']['timeout_ms'] / 1000 + 30)
        result = verify(out, source, environment)
        result['agent_exit_code'] = child.returncode
        result['passed'] = result['passed'] and child.returncode == 0
        write_json(out / 'verdict.json', result)
        manifest = json.loads((out / 'manifest.json').read_text())
        write_json(out / 'manifest.json', {**manifest, 'end_time': time.time(), 'run_status': 'completed', 'result': result})
        return result
    except Exception as exc:
        manifest = json.loads((out / 'manifest.json').read_text())
        write_json(out / 'manifest.json', {**manifest, 'end_time': time.time(), 'run_status': 'failed', 'failure_class': type(exc).__name__, 'error': str(exc)})
        raise
    finally:
        if server:
            server.stop()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--out', required=True)
    p.add_argument('--source', required=True)
    p.add_argument('--environment', default='.cache/task-env')
    p.add_argument('--config', default='configs/workstation.json')
    p.add_argument('--start-server', action='store_true')
    p.add_argument('--resume-run')
    args = p.parse_args()
    print(json.dumps(run(args.out, args.source, args.environment, args.config, args.start_server, args.resume_run)), flush=True)


if __name__ == '__main__':
    main()
