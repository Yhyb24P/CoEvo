"""Generate verified W0 read/output/stop replay in a fresh authorized learning stream."""
import argparse
import json
import time
from pathlib import Path
from .everyday import execute_task, snapshot, digest
from .behavior import certify
from .runtime import read_config, write_json, source_snapshot
from .rsi import Server

CASES = {'sort': [7,-4,7,2], 'sum': [-3,8,1,1], 'unique': [9,0,9,-3,0]}


def prepare(out, operation):
    out=Path(out).resolve()
    workspace=out/'workspace';workspace.mkdir(parents=True,exist_ok=False)
    values=CASES[operation]
    result=sorted(values) if operation=='sort' else sum(values) if operation=='sum' else sorted(set(values))
    inputs={'input.json':json.dumps({'operation':operation,'values':values},ensure_ascii=False,indent=2)+'\n'}
    expected={'output.json':json.dumps({'result':result},ensure_ascii=False)+'\n'}
    for name,text in {**inputs,'output.json':''}.items():(workspace/name).write_text(text)
    task={'episode_id':f'L-self-replay-W0-20261014-{operation}',
          'source_cluster_id':f'L-self-replay-W0-20261014-{operation}',
          'split':'L','train_authorized':True,'actor':'student','prompt_actor':'researcher',
          'interaction_origin':'controlled-self-replay','generator_checkpoint':'W0',
          'program_family':f'file-{operation}','task_family':'self-replay','output_format':'json',
          'candidate_format':'verified_behavior_v1','inputs':inputs,'expected':expected,
          'allowed_write_paths':['output.json'],'workspace':str(workspace),'action':'execute',
          'prompt':'请用 read 读取 input.json。operation=sort 时按升序排列并保留重复值；sum 时求和；unique 时去重后按升序排列。用 write 写 output.json，JSON 中只有 result 一个字段，sort/unique 返回数组，sum 返回数字。原输入不动，其他路径不允许修改。核对输出后只回复“已完成”。',
          'initial_files':snapshot(workspace),'created_at':time.time(),
          'capability_hypothesis':'maintain read, conditional computation, correct serialization and stopping',
          'scope':'new L replay fixtures, not existing G or H examples'}
    write_json(out/'task.json',task)
    return task


def collect(config,out):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
    c=read_config(config)
    tasks={name:prepare(out/name,name) for name in CASES}
    write_json(out/'manifest.json',{'checkpoint':'W0','adapter':None,'config':c,
        'source_snapshot':source_snapshot(),'source_clusters':[t['source_cluster_id'] for t in tasks.values()],
        'H_used':False,'start_time':time.time(),'status':'running'})
    server=None;results=[];candidates=[]
    try:
        server=Server(config,out/'server.log')
        for name,task in tasks.items():
            verdict=execute_task(task,out/name,c,c['served_model'])
            admitted=certify(task,out/name) if verdict['passed'] else []
            candidates.extend(admitted)
            results.append({'name':name,**verdict,'candidate_kinds':[x['behavior_kind'] for x in admitted]})
        (out/'candidates.jsonl').write_text(''.join(json.dumps(c,ensure_ascii=False)+'\n' for c in candidates))
        summary={'checkpoint':'W0','passed':sum(r['passed'] for r in results),'total':len(results),
            'candidates':len(candidates),'results':results,'training_executed':False}
        write_json(out/'summary.json',summary)
        print(json.dumps({'passed':summary['passed'],'total':summary['total'],'candidates':len(candidates),
                          'cases':{r['name']:r['candidate_kinds'] for r in results}},ensure_ascii=False))
        return summary
    finally:
        if server:server.stop()
        m=json.loads((out/'manifest.json').read_text());write_json(out/'manifest.json',{
            **m,'end_time':time.time(),'status':'completed' if (out/'summary.json').exists() else 'failed'})


def main():
    p=argparse.ArgumentParser();p.add_argument('--config',default='configs/codex-tool-pilot.json');p.add_argument('--out',required=True)
    a=p.parse_args();collect(a.config,a.out)


if __name__=='__main__':main()
