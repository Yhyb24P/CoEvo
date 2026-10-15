"""Prepare an independent CoEvo/Pi Office task with a selected standalone upstream Skill."""
import argparse
import hashlib
import shutil
from pathlib import Path

from .runtime import read_config, write_json
from .sandbox import command
from .project import hashes


def prepare(out, source, pi_entry, environment, skill_cache):
    out, source = Path(out).resolve(), Path(source).resolve()
    pi_entry, environment, skill_cache = map(lambda p: Path(p).resolve(), (pi_entry, environment, skill_cache))
    if out.exists():
        raise ValueError('Use a fresh task directory')
    workspace = out / 'workspace'
    skill = workspace / '.skills/spreadsheets'
    upstream = source / 'skills/spreadsheets'
    original = {str(p.relative_to(upstream)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in upstream.rglob('*') if p.is_file()}
    shutil.copytree(upstream, skill)
    shutil.copy2(source / 'LICENSE', skill / 'LICENSE')
    file = skill / 'SKILL.md'
    text = file.read_text().replace('{{SKILL_ROOT_SHELL}}', '/workspace/.skills/spreadsheets')
    text = text.replace('${PILOTDECK_WORK_DIR:?PILOTDECK_WORK_DIR is required}', '/workspace/.work')
    text = text.replace('`PILOTDECK_WORK_DIR`', '`/workspace/.work`')
    file.write_text(text)
    shutil.copy2('experiments/pilotdeck/fixtures/research-ledger.xlsx', workspace / 'research-ledger.xlsx')
    shutil.copy2('experiments/complete-work/first-W0-results.json', workspace / 'first-W0-results.json')
    prompt = Path('experiments/pilotdeck/workbook-task.txt').read_text()
    config = read_config('configs/complete-work-qwen.json')
    prefix = command(workspace, environment, [], readonly_paths=['.skills'])[:-1]
    prefix += ['--ro-bind', str(skill_cache), '/opt/skill-cache', '--setenv', 'SPREADSHEET_SKILL_CACHE', '/opt/skill-cache', '--']
    request = dict(workspace=str(workspace), model_cwd='/workspace', run_dir=str(out), task_environment=str(environment),
                   pi_entry=str(pi_entry), required_pi_version='1.2.0', skill_dir='.skills',
                   readonly_paths=['.skills'], endpoint=config['endpoint'], model=config['served_model'],
                   enable_thinking=True, context_tokens=config['max_model_len'], sampling=config['inference_sampling'],
                   timeout_ms=1800000, max_tool_calls=100, max_output_tokens=32768,
                   sandbox_prefix=prefix, prompts=[prompt], capture_payload=True,
                   system_prompt='You are CoEvo, an independent local task Agent. Bash runs in /workspace; use workspace-relative paths for task work. Use selected task Skills and actual read/write/bash observations to complete the authorized work. Preserve sources and report outcomes accurately.')
    write_json(out / 'agent_request.json', request)
    write_json(out / 'task.json', dict(source_cluster='coevo-research-workbook', split='D',
               actor='student', prompt_actor='researcher', feedback_assisted=False,
               upstream_repository='https://github.com/OpenBMB/PilotDeck',
               upstream_revision='783499ffdb2d501bf590b2e035acd027a882df10',
               original_skill_hashes=original, adapted_skill_sha256=hashlib.sha256(file.read_bytes()).hexdigest(),
               adaptations=['task-local Skill root', 'task-local work directory'],
               inputs={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in workspace.glob('*') if p.is_file()},
               initial_files=hashes(workspace),
               budget={'wall_seconds':1800,'max_tool_calls':100,'max_output_tokens':32768}))
    return request


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    parser.add_argument('--source', default='.cache/pilotdeck')
    parser.add_argument('--pi-entry', default='.cache/pi-1.2/node_modules/@earendil-works/pi-coding-agent/dist/index.js')
    parser.add_argument('--environment', default='.cache/pilotdeck-office-env')
    parser.add_argument('--skill-cache', default='.cache/spreadsheets-skill-cache')
    args = parser.parse_args()
    prepare(args.out, args.source, args.pi_entry, args.environment, args.skill_cache)
