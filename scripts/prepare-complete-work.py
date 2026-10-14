"""Prepare fixed complete-work cases and native Pi requests; does not run a model."""
import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from coevo.project import hashes
from coevo.runtime import read_config, write_json
from coevo.sandbox import command

SOURCES = {
    'software': ('python-frontmatter', 'd2977d71638cb451bc06f2af3bb48e09e0dbe8c6'),
    'science': ('palmerpenguins', '8957207b78d6ccd1b4654a9dd9c9041b657478ab'),
}


def prepare(args):
    out = Path(args.out).resolve()
    if out.exists():
        raise ValueError('Use a new directory to preserve previous evidence')
    name, revision = SOURCES[args.case]
    source = Path(args.sources).resolve() / name
    actual = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    if actual != revision:
        raise ValueError('Source differs from registered revision')
    environment = Path(args.environment).resolve()
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
    prompt = Path(f'experiments/complete-work/{args.case}-task.txt').read_text()
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
                   bash_timeout_seconds=budget['bash_seconds'], repeat_failure_limit=4,
                   system_prompt='Complete the authorized work using actual tools. Choose methods independently, learn from observations and report evidence honestly.')
    write_json(out / 'agent_request.json', request)
    write_json(out / 'preparation.json', dict(config=config, environment=str(environment),
               prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
               prepared_inputs=task['initial_files']))
    print(json.dumps(dict(case=args.case, out=str(out), source_revision=revision)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--case', choices=SOURCES, required=True)
    parser.add_argument('--sources', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--environment', required=True)
    parser.add_argument('--config', default='configs/mcm-thinking.json')
    parser.add_argument('--pi-entry', default='.worktrees/momo-code/packages/opencode/node_modules/@earendil-works/pi-coding-agent/dist/index.js')
    prepare(parser.parse_args())
