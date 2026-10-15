"""Prepare source-identical fresh Office tasks for model-specific native serving."""
import argparse
import hashlib
import json
import runpy
import shutil
from pathlib import Path
from coevo.pi_office import prepare as prepare_office
from coevo.project import hashes
from coevo.runtime import read_config,write_json
from coevo.sandbox import command

ROOT=Path(__file__).resolve().parents[2]


def prepare(out,data):
    out,data=Path(out).resolve(),Path(data).resolve();out.mkdir(parents=True,exist_ok=False)
    template=out/'olympic-audit.xlsx'
    runpy.run_path(str(ROOT/'experiments/olympic-office/prepare.py'))['make_template'](data,template)
    prompt=(ROOT/'experiments/olympic-office/task.txt').read_text()
    environment=ROOT/'.cache/pilotdeck-office-env';cache=ROOT/'.cache/spreadsheets-skill-cache'
    versions={}
    for arm in ['spark','qwen']:
        config=read_config(ROOT/f'configs/complete-work-{arm}.json')
        root=out/arm;r=prepare_office(root,ROOT/'.cache/pilotdeck',
             ROOT/'.cache/pi-1.2/node_modules/@earendil-works/pi-coding-agent/dist/index.js',environment,cache)
        workspace=root/'workspace'
        for name in ['research-ledger.xlsx','first-W0-results.json']:(workspace/name).unlink()
        shutil.copy2(template,workspace/'olympic-audit.xlsx');(workspace/'data').mkdir()
        for name in ['summerOly_medal_counts.csv','summerOly_hosts.csv','summerOly_programs.csv']:
            shutil.copy2(data/name,workspace/'data'/name)
        readonly=['.skills','data','olympic-audit.xlsx']
        prefix=command(workspace,environment,[],readonly_paths=readonly)[:-1]
        prefix+=['--ro-bind',str(cache),'/opt/skill-cache','--setenv','SPREADSHEET_SKILL_CACHE','/opt/skill-cache','--']
        r.update(prompts=[prompt],readonly_paths=readonly,sandbox_prefix=prefix,
                 timeout_ms=1500000,max_tool_calls=80,repeat_failure_limit=4,
                 endpoint=config['endpoint'],model=config['served_model'],sampling=config['inference_sampling'],
                 context_tokens=config['max_model_len'],enable_thinking=config['enable_thinking'])
        write_json(root/'agent_request.json',r)
        t=json.loads((root/'task.json').read_text());initial=hashes(workspace)
        t.update(case='olympic-office',arm=arm,source_cluster='mcm-2025-c',split='D',train_authorized=False,
                 inputs={p:h for p,h in initial.items() if not p.startswith('.skills/')},initial_files=initial,
                 budget={'wall_seconds':1500,'max_tool_calls':80,'max_output_tokens':32768})
        write_json(root/'task.json',t)
        versions[arm]={'config_path':str(ROOT/f'configs/complete-work-{arm}.json'),'config':config,
                       'request_sha256':hashlib.sha256((root/'agent_request.json').read_bytes()).hexdigest()}
    assert json.loads((out/'spark/task.json').read_text())['initial_files']==json.loads((out/'qwen/task.json').read_text())['initial_files']
    record={'status':'prepared','arms':['spark','qwen'],'source_cluster':'mcm-2025-c','split':'D',
            'same_initial_files':True,'same_prompt_tools_skill_budget':True,'fresh_sessions':True,
            'effective_task_budget':{'wall_seconds':1500,'max_tool_calls':80,'max_output_tokens':32768},
            'models':versions,'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),
            'checker_sha256':hashlib.sha256((ROOT/'experiments/olympic-office/check.py').read_bytes()).hexdigest(),
            'scope':'Single D complete Office task; model plus native template/parser/recommended sampling comparison. No isolated weight-learning claim or automatic model promotion.'}
    write_json(out/'comparison.json',record)
    return record


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--data',required=True);a=p.parse_args()
    print(json.dumps(prepare(a.out,a.data),ensure_ascii=False))
