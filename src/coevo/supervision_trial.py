"""Frozen paired development panel for the same-source supervision matrix."""
import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from .runtime import read_config, write_json, source_snapshot
from .workflows import cases
from .agent_learning_pilot import prepare
from .everyday import execute_task
from .tasks import make_task
from .rsi import Server


def freeze(matrix, out, config):
    matrix=Path(matrix).resolve();out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
    specs=[]
    for family,index,spec in cases(4,101):
        # Instance transfer within the four trained families, not source-held-out H.
        specs.append({**spec,'name':f'D-{family}-{index}', 'split':'D','train_authorized':False,
            'episode_id':f'D-supervision-{family}-{index}','source_cluster_id':f'D-supervision-{family}',
            'task_family':'paired-development-workflows','allowed_write_paths':list(spec['expected']),
            'prompt':spec['prompt']+' 输入不动，可自行选择工具，Python标准库可用。写入后用read回读并核对，正确后只回复“已完成”。'})
    for n in range(3):
        legacy=make_task(out/'legacy-fixtures'/str(n),0,n,'G')
        specs.append({**legacy,'name':f'G-{n}','inputs':{'input.json':(Path(legacy['workspace'])/'input.json').read_text()},
            'expected':{'output.json':json.dumps(legacy['expected'])},'output_format':'json',
            'allowed_write_paths':['output.json'],'prompt':legacy['prompt']+' 结束时只回复“已完成”。'})
    write_json(out/'panel.json',specs)
    configs=sorted(p for p in matrix.glob('*.json') if p.name!='plan.json')
    arms=[{'name':p.stem,'config':str(p),'dataset':str(matrix/(p.stem.rsplit('-',2)[0]+'.jsonl'))} for p in configs]
    # Arm names end in same-exposure or token-matched.
    for arm in arms:
        arm['dataset']=str(matrix/(arm['name'].removesuffix('-same-exposure').removesuffix('-token-matched')+'.jsonl'))
    write_json(out/'manifest.json',{'status':'frozen','created_at':time.time(),'config':read_config(config),
        'config_path':str(Path(config).resolve()),'arms':arms,'seed':17,'panel_seed':101,'variants':4,
        'panel_sha256':hashlib.sha256((out/'panel.json').read_bytes()).hexdigest(),
        'inputs_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [*configs,*matrix.glob('*.jsonl')]},
        'source_snapshot':source_snapshot(),'H_used':False,'promotion_allowed':False,
        'scope':'single-seed development mask/replay control; four shared families, 16 instances, no independent H or Q3 claim',
        'G_protocol':'same legacy inputs; unified Pi tools, deterministic sampling and explicit completion; remeasure W0',
        'training_wall_cap_per_arm':600,'evaluation_wall_cap_per_model':2700})


def run(out):
    out=Path(out).resolve();m=json.loads((out/'manifest.json').read_text());panel=json.loads((out/'panel.json').read_text())
    if m['status']!='frozen':raise ValueError('Trial already started; inspect retained outputs rather than restarting')
    for p,digest in m['inputs_sha256'].items():
        if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=digest:raise ValueError('Frozen input changed')
    write_json(out/'manifest.json',{**m,'status':'running','start_time':time.time()})
    results={};server=None
    try:
        for arm in m['arms']:
            root=out/arm['name'];root.mkdir();adapter=root/'adapter'
            with (root/'training.log').open('w') as log:
                proc=subprocess.run([sys.executable,'-m','coevo.train','--config',arm['config'],'--dataset',arm['dataset'],
                    '--adapter-out',str(adapter),'--seed','17'],stdout=log,stderr=subprocess.STDOUT,timeout=720)
            if proc.returncode:raise RuntimeError(f'Training failed: {root}')
            result=json.loads((root/'training.log').read_text().splitlines()[-1]);write_json(root/'training.json',result)
            print(json.dumps({'phase':'trained','arm':arm['name'],'steps':result['optimizer_steps'],'seconds':result['gpu_wall_hours']*3600}),flush=True)
        for name,adapter in [('W0',None),*[(a['name'],str(out/a['name']/'adapter')) for a in m['arms']]]:
            root=out/name/'evaluation';root.mkdir(parents=True);started=time.monotonic()
            server=Server(m['config_path'],root/'server.log',adapter);rows=[]
            for spec in panel:
                if time.monotonic()-started>m['evaluation_wall_cap_per_model']:raise TimeoutError('Panel wall cap')
                task=prepare(root/spec['name'],spec)
                verdict=execute_task(task,root/spec['name'],m['config'],'coevo-current' if adapter else None)
                rows.append({'name':spec['name'],**verdict})
            server.stop();server=None
            summary={'rows':rows,'D_passed':sum(r['passed'] for r in rows if r['name'].startswith('D-')),
                'D_total':16,'G_passed':sum(r['passed'] for r in rows if r['name'].startswith('G-')),'G_total':3,
                'wall_seconds':time.monotonic()-started}
            results[name]=summary;write_json(root/'summary.json',summary);write_json(out/'results.json',results)
            print(json.dumps({'phase':'evaluated','arm':name,'D':summary['D_passed'],'G':summary['G_passed']}),flush=True)
        write_json(out/'manifest.json',{**m,'status':'completed','end_time':time.time()})
    except BaseException as exc:
        write_json(out/'manifest.json',{**m,'status':'failed','end_time':time.time(),'error':str(exc)});raise
    finally:
        if server:server.stop()


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--matrix');p.add_argument('--config');p.add_argument('--run',action='store_true');a=p.parse_args()
    if a.run:run(a.out)
    else:
        if not a.matrix or not a.config:p.error('Freeze requires --matrix and --config')
        freeze(a.matrix,a.out,a.config)


if __name__=='__main__':main()
