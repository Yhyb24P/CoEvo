"""Prepare fixed complete-work cases and native Pi requests; does not run a model."""
import argparse
import hashlib
import json
import shutil
import subprocess
import os
import time
from pathlib import Path

from .project import hashes
from .runtime import read_config, write_json, source_snapshot
from .sandbox import command, execute

ROOT = Path(__file__).resolve().parents[2]

SOURCES = {
    'software': ('python-frontmatter', 'd2977d71638cb451bc06f2af3bb48e09e0dbe8c6'),
    'science': ('palmerpenguins', '8957207b78d6ccd1b4654a9dd9c9041b657478ab'),
}


def verify(out, sources, environment):
    """Rebuild submissions outside the agent workspace; retain scientific review needs."""
    out = Path(out).resolve()
    task = json.loads((out / 'task.json').read_text())
    workspace = out / 'workspace'
    source = Path(sources).resolve() / SOURCES[task['case']][0]
    if subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip() != task['source_revision']:
        raise ValueError('Reviewer source revision differs')
    if subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain'], text=True).strip():
        raise ValueError('Reviewer source must be clean')
    if any(p.is_symlink() for p in workspace.rglob('*')):
        raise ValueError('Submission symlinks are not supported')
    review = out / 'review'
    review.mkdir()  # previous verdicts are immutable; choose a new run for re-review
    clean = review / 'workspace'
    result = {'case': task['case'], 'source_cluster': task['source_cluster'],
              'review_origin': 'researcher-external-checks', 'source_revision': task['source_revision']}
    changed = {p for p, h in hashes(workspace).items() if task['initial_files'].get(p) != h}
    if task['case'] == 'software':
        shutil.copytree(source, clean, ignore=shutil.ignore_patterns('.git', '__pycache__'))
        shutil.rmtree(clean / 'frontmatter')
        shutil.copytree(workspace / 'frontmatter', clean / 'frontmatter')
        shutil.copy2(ROOT / 'experiments/complete-work/check-software.py', clean / 'external_check.py')
        result['upstream'] = execute(clean, environment, ['python', '-m', 'pytest', '-q', '-p', 'no:cacheprovider', 'tests'], review / 'upstream.log', readonly=True)
        result['requirements'] = execute(clean, environment, ['python', 'external_check.py'], review / 'requirements.log', readonly=True)
        submitted = sorted(p for p in changed if p.startswith('tests/') and p.endswith('.py'))
        result['submitted_tests'] = execute(workspace, environment, ['python', '-m', 'pytest', '-q', '-p', 'no:cacheprovider', *submitted], review / 'submitted-tests.log', readonly=True) if submitted else None
        result['test_files'] = submitted
        result['behavior_passed'] = all(result[k]['exit_code'] == 0 for k in ('upstream', 'requirements'))
        result['documentation_changes'] = sorted(p for p in changed if p.endswith(('.md', '.rst')) and p != 'WORK_REPORT.md')
        result['report_present'] = (workspace / 'WORK_REPORT.md').is_file() and (workspace / 'WORK_REPORT.md').stat().st_size > 0
        result['review_pending'] = ['Patch compatibility and scope', 'Focused tests cover requested behavior', 'Documentation and report accurately describe actual results']
    else:
        shutil.copytree(workspace, clean, ignore=shutil.ignore_patterns('__pycache__', 'results'))
        expected = {p: h for p, h in task['initial_files'].items() if p.startswith('data/')}
        result['data_unchanged'] = all(hashes(clean).get(p) == h for p, h in expected.items())
        shutil.copy2(ROOT / 'experiments/complete-work/check-science-inputs.py', clean / 'external_input_facts.py')
        result['input_facts'] = execute(clean, environment, ['python', 'external_input_facts.py', 'data'], review / 'input-facts.json', readonly=True)
        result['reproduction'] = execute(clean, environment, ['python', 'analysis.py'], review / 'reproduction.log', timeout=300) if (clean / 'analysis.py').is_file() else None
        original = {p: h for p, h in hashes(workspace).items() if p.startswith('results/')}
        rebuilt = {p: h for p, h in hashes(clean).items() if p.startswith('results/')}
        result['original_results'] = original
        result['rebuilt_results'] = rebuilt
        result['byte_identical_results'] = bool(original) and original == rebuilt
        result['report_present'] = (workspace / 'REPORT.md').is_file() and (workspace / 'REPORT.md').stat().st_size > 0
        result['reproduction_passed'] = bool(result['reproduction'] and result['reproduction']['exit_code'] == 0 and rebuilt and result['data_unchanged'])
        result['review_pending'] = ['Linkage, analysis sample and missingness versus independent input facts', 'Pooled/adjusted estimates and uncertainty independently recomputed', 'Species/island identifiability and repeated IDs', 'Sensitivity results, numerical report claims and causal limitations']
    result['changed_files'] = sorted(changed)
    result['task_success'] = None  # checklist requires substantive reviewer judgement
    write_json(review / 'verdict.json', result)
    return result


def run(out):
    """Explicit execution against an already configured service; preserves native Pi evidence."""
    out = Path(out).resolve()
    request_path = out / 'agent_request.json'
    request = json.loads(request_path.read_text())
    if (out / 'manifest.json').exists() or (out / 'transcript.json').exists():
        raise ValueError('Run evidence already exists; prepare a fresh run')
    before = hashes(out / 'workspace')
    expected = json.loads((out / 'task.json').read_text())['initial_files']
    if before != expected:
        raise ValueError('Initial workspace has changed since preparation')
    manifest = {'status': 'running', 'started_at': time.time(), 'source_snapshot': source_snapshot(),
                'adapter_sha256': hashlib.sha256((ROOT / 'scripts/pi-project-agent.mjs').read_bytes()).hexdigest()}
    write_json(out / 'manifest.json', manifest)
    started = time.monotonic()
    try:
        with (out / 'agent.log').open('w') as log:
            process = subprocess.run(['node', str(ROOT / 'scripts/pi-project-agent.mjs')],
                                     env={**os.environ, 'COEVO_REQUEST_FILE': str(request_path)},
                                     stdout=log, stderr=subprocess.STDOUT,
                                     timeout=request['timeout_ms'] / 1000 + 60)
        transcript = json.loads((out / 'transcript.json').read_text())
        from .mcm_run import termination
        messages = transcript['messages']
        result = {'agent_exit_code': process.returncode, 'termination': termination(transcript),
                  'pi_sdk_version': transcript.get('sdk_version'),
                  'selected_skills': transcript.get('selected_skills', []),
                  'completion': transcript.get('completion'),
                  'resource_stop': transcript.get('resource_stop'), 'wall_seconds': time.monotonic() - started,
                  'tool_calls': transcript['tool_calls'], 'session_file': transcript['session_file'],
                  'usage': {k: sum(m.get('usage', {}).get(k, 0) for m in messages if m['role'] == 'assistant') for k in ('input', 'output', 'cacheRead', 'cacheWrite')},
                  'final_files': hashes(out / 'workspace'), 'feedback_assisted': False,
                  'scope': 'D complete-work execution; deliverables require independent review'}
        write_json(out / 'execution.json', result)
        manifest['status'] = 'completed'
        return result
    except BaseException as error:
        manifest.update(status='failed', error=str(error), failure_class=type(error).__name__)
        raise
    finally:
        manifest['ended_at'] = time.time()
        write_json(out / 'manifest.json', manifest)


def prepare(args):
    out = Path(args.out).resolve()
    if out.exists():
        raise ValueError('Use a new directory to preserve previous evidence')
    name, revision = SOURCES[args.case]
    source = Path(args.sources).resolve() / name
    actual = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    if actual != revision:
        raise ValueError('Source differs from registered revision')
    if subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain'], text=True).strip():
        raise ValueError('Source checkout must be clean')
    environment = Path(args.environment).resolve()
    if not (environment / 'bin/python').is_file() or not Path(args.pi_entry).is_file():
        raise ValueError('Task environment and Pi entry must exist')
    workspace = out / 'workspace'
    readonly = []
    if args.case == 'software':
        shutil.copytree(source, workspace, ignore=shutil.ignore_patterns('.git', '__pycache__'))
    else:
        (workspace / 'data').mkdir(parents=True)
        for filename in ['penguins.csv', 'penguins_raw.csv']:
            shutil.copy2(source / 'inst/extdata' / filename, workspace / 'data' / filename)
        for filename in ['README.md', 'DESCRIPTION', 'LICENSE']:
            if (source / filename).is_file():
                shutil.copy2(source / filename, workspace / ('SOURCE_' + filename))
        readonly = ['data']
    prompt = (ROOT / f'experiments/complete-work/{args.case}-task.txt').read_text()
    config = read_config(args.config)
    budget = dict(wall_seconds=2700, max_tool_calls=100, max_output_tokens=32768,
                  bash_seconds=120, compaction=False)
    task = dict(case=args.case, source_repository=f'https://github.com/{"eyeseast/python-frontmatter" if args.case == "software" else "allisonhorst/palmerpenguins"}',
                source_revision=revision, split='D', source_cluster=name,
                prompt_origin='researcher', initial_files=hashes(workspace), budget=budget)
    write_json(out / 'task.json', task)
    request = dict(workspace=str(workspace), run_dir=str(out),
                   task_environment=str(environment), endpoint=config['endpoint'],
                   model=config['served_model'], context_tokens=config['max_model_len'],
                   enable_thinking=config.get('enable_thinking', True),
                   sampling=config['inference_sampling'], prompts=[prompt],
                   pi_entry=str(Path(args.pi_entry).resolve()),
                   sandbox_prefix=command(workspace, environment, [], readonly_paths=readonly),
                   readonly_paths=readonly, timeout_ms=budget['wall_seconds'] * 1000,
                   max_tool_calls=budget['max_tool_calls'], max_output_tokens=budget['max_output_tokens'],
                   repeat_failure_limit=4,
                   system_prompt='Complete the authorized work using actual tools. Choose methods independently, learn from observations and report evidence honestly.')
    write_json(out / 'agent_request.json', request)
    write_json(out / 'preparation.json', dict(config=config, environment=str(environment),
               environment_packages=subprocess.check_output([str(environment / 'bin/python'), '-m', 'pip', 'freeze'], text=True) if (environment / 'bin/pip').exists() else subprocess.check_output([str(environment / 'bin/python'), '-c', 'import importlib.metadata,json;print(json.dumps(sorted((d.metadata["Name"],d.version) for d in importlib.metadata.distributions())))'], text=True),
               pi_entry_sha256=hashlib.sha256(Path(args.pi_entry).read_bytes()).hexdigest(),
               prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
               prepared_inputs=task['initial_files']))
    print(json.dumps(dict(case=args.case, out=str(out), source_revision=revision)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['prepare', 'verify', 'run'], nargs='?', default='prepare')
    parser.add_argument('--case', choices=SOURCES)
    parser.add_argument('--sources')
    parser.add_argument('--out', required=True)
    parser.add_argument('--environment')
    parser.add_argument('--config', default='configs/complete-work-qwen.json')
    parser.add_argument('--pi-entry', default='.worktrees/momo-code/packages/opencode/node_modules/@earendil-works/pi-coding-agent/dist/index.js')
    args = parser.parse_args()
    if args.action in ('prepare', 'verify') and (not args.sources or not args.environment):
        parser.error('prepare/verify require --sources and --environment')
    if args.action == 'prepare':
        if not args.case:
            parser.error('prepare requires --case')
        prepare(args)
    else:
        print(json.dumps(verify(args.out, args.sources, args.environment) if args.action == 'verify' else run(args.out)))


if __name__ == '__main__':
    main()
