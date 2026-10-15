"""Prepare one fresh complete-work run using the existing native Pi Office path."""
import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from coevo.pi_office import prepare as prepare_office
from coevo.project import hashes
from coevo.runtime import read_config, write_json
from coevo.sandbox import command

ROOT = Path(__file__).resolve().parents[2]


def prepare(out, data, environment):
    out, data, environment = map(lambda p: Path(p).resolve(), (out, data, environment))
    request = prepare_office(out, ROOT/'.cache/pilotdeck',
        ROOT/'.cache/pi-1.2/node_modules/@earendil-works/pi-coding-agent/dist/index.js',
        environment, ROOT/'.cache/spreadsheets-skill-cache')
    workspace = out/'workspace'
    for name in ['research-ledger.xlsx', 'first-W0-results.json']:
        (workspace/name).unlink()
    (workspace/'data').mkdir()
    source = json.loads((ROOT/'experiments/bike-sharing/source.json').read_text())
    for name in ['hour.csv', 'day.csv', 'Readme.txt', 'source.json']:
        if name in source['files']:
            assert hashlib.sha256((data/name).read_bytes()).hexdigest() == source['files'][name]['sha256']
        shutil.copy2(data/name, workspace/'data'/name)
    prompt = (ROOT/'experiments/bike-sharing/task.txt').read_text()
    config = read_config(ROOT/'configs/complete-work-qwen.json')
    budget = dict(wall_seconds=2700, max_tool_calls=100, max_output_tokens=32768,
                  context_capacity=config['max_model_len'], compaction=False)
    readonly = ['data', '.skills']
    prefix = command(workspace, environment, [], readonly_paths=readonly)[:-1]
    prefix += ['--ro-bind', str((ROOT/'.cache/spreadsheets-skill-cache').resolve()),
               '/opt/skill-cache', '--setenv', 'SPREADSHEET_SKILL_CACHE', '/opt/skill-cache', '--']
    request.update(prompts=[prompt], readonly_paths=readonly, sandbox_prefix=prefix,
                   timeout_ms=budget['wall_seconds']*1000, max_tool_calls=budget['max_tool_calls'],
                   max_output_tokens=budget['max_output_tokens'], repeat_failure_limit=4)
    write_json(out/'agent_request.json', request)
    task = json.loads((out/'task.json').read_text())
    task.update(case='bike-sharing', source_cluster='uci-bike-sharing', split='D',
                train_authorized=False, feedback_assisted=False, native_history='fresh session',
                initial_files=hashes(workspace), inputs=hashes(workspace/'data'), budget=budget)
    write_json(out/'task.json', task)
    packages = subprocess.check_output([str(environment/'bin/python'), '-c',
        'import importlib.metadata,json;print(json.dumps(sorted((d.metadata["Name"],d.version) for d in importlib.metadata.distributions())))'], text=True)
    write_json(out/'preparation.json', dict(config=config, effective_budget=budget,
        prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(), environment_packages=json.loads(packages),
        request_sha256=hashlib.sha256((out/'agent_request.json').read_bytes()).hexdigest()))
    return {'out': str(out), 'budget': budget, 'status': 'prepared'}


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--data',required=True)
    p.add_argument('--environment',default='.cache/bike-analysis-env');a=p.parse_args()
    print(json.dumps(prepare(a.out,a.data,a.environment)))
