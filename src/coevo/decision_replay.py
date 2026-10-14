"""Fresh L workflows covering observation, serialization checks and stopping."""
import argparse
import hashlib
import json
import time
import shutil
from pathlib import Path
from .behavior import certify
from .everyday import csv_text, execute_task, snapshot
from .runtime import read_config, source_snapshot, write_json
from .rsi import Server


def cases():
    return {
        'quoted_csv': {'output_format':'csv','program_family':'csv-field-serialization',
            'inputs':{'source.tsv':'label\tprice\n North,West \t3.4\n Studio "A" \t19\n'},
            'expected':{'output.csv':csv_text([['label','price'],['North,West','3.40'],['Studio "A"','19.00']])},
            'prompt':'读取 source.tsv，去除字段两端空格，价格保留两位小数，转成标准 CSV，字段内部逗号和双引号必须保留。使用 Python csv 模块处理转义，表头 label,price，行序不变。'},
        'digest_check': {'output_format':'json','program_family':'path-preserving-hash-check',
            'inputs':{'expected.json':json.dumps({'docs/x.txt':hashlib.sha256(b'one\n').hexdigest(),'docs/y.txt':hashlib.sha256(b'two\n').hexdigest()}),'docs/x.txt':'one\n','docs/y.txt':'changed\n'},
            'expected':{'output.json':json.dumps({'matching':['docs/x.txt'],'different':['docs/y.txt']})},
            'prompt':'读取 expected.json，用 Python hashlib 对其中每个路径的实际文件字节算 SHA256，按相等与不同分成 matching、different 两个排序数组。路径保留完整 docs/ 前缀，不要猜测哈希。'},
        'conditional_rows': {'output_format':'json','program_family':'observed-policy-row-selection',
            'inputs':{'policy.json':json.dumps({'minimum':12,'include_equal':False}),'rows.json':json.dumps([{'id':'p','score':12},{'id':'q','score':18},{'id':'r','score':4}])},
            'expected':{'output.json':json.dumps({'ids':['q']})},
            'prompt':'先读取 policy.json 再读取 rows.json。minimum 是阈值，include_equal 决定是否包含等于阈值；仅保留符合当前策略的行，按 id 排序，输出只有 ids 字段。不能采用历史默认阈值。'},
    }


def run(config,out):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False);c=read_config(config)
    tasks={}
    for name,spec in cases().items():
        root=out/name;workspace=root/'workspace';workspace.mkdir(parents=True)
        for rel,content in {**spec['inputs'],**{p:'' for p in spec['expected']}}.items():
            p=workspace/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(content)
        task={**spec,'episode_id':f'L-decision-20261014-{name}','source_cluster_id':f'L-decision-20261014-{name}',
            'split':'L','train_authorized':True,'actor':'student','prompt_actor':'researcher',
            'interaction_origin':'controlled-guided-W0-replay','task_family':'observation-output-check-stop',
            'action':'execute','workspace':str(workspace),'allowed_write_paths':list(spec['expected']),
            'initial_files':snapshot(workspace),'guidance':'explicit implementation guidance; not autonomous D score',
            'prompt':spec['prompt']+' 只允许写 '+next(iter(spec['expected']))+'，输入保持不变。可用 bash 执行 Python 标准库。写入后必须用 read 读取实际输出并核对，再只回复“已完成”。'}
        tasks[name]=task;write_json(root/'task.json',task)
    write_json(out/'manifest.json',{'config':c,'source_snapshot':source_snapshot(),'checkpoint':'W0','start_time':time.time(),
        'sources':[t['source_cluster_id'] for t in tasks.values()],'D_reused_for_training':False,'H_used':False,'status':'running'})
    server=None;results=[];targets=[]
    try:
        server=Server(config,out/'server.log')
        for name,task in tasks.items():
            verdict=execute_task(task,out/name,c,c['served_model'])
            admitted=certify(task,out/name) if verdict['passed'] else []
            targets.extend(admitted);results.append({'name':name,**verdict,'target_kinds':[x['behavior_kind'] for x in admitted]})
        (out/'candidates.jsonl').write_text(''.join(json.dumps(t,ensure_ascii=False)+'\n' for t in targets))
        summary={'results':results,'passed':sum(r['passed'] for r in results),'total':len(results),'targets':len(targets),
            'scope':'guided fresh L; observations not loss targets; not independent ability evidence','training_executed':False}
        write_json(out/'summary.json',summary);print(json.dumps(summary,ensure_ascii=False))
    finally:
        if server:server.stop()
        m=json.loads((out/'manifest.json').read_text());write_json(out/'manifest.json',{**m,'status':'completed' if (out/'summary.json').exists() else 'failed','end_time':time.time()})


def main():
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--out',required=True)
    p.add_argument('--resume-batch')
    a=p.parse_args()
    if a.resume_batch:
        recover(a.config,a.out,a.resume_batch)
    else:
        run(a.config,a.out)


def recover(config,out,parent):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False);parent=Path(parent).resolve();c=read_config(config)
    feedback={
        'quoted_csv':'外部核验确认 output.csv 内容已经正确，但你重复执行命令而没有停止。不要再次转换或写入。只用 read 回读 output.csv，确认后只回复“已完成”并停止。',
        'conditional_rows':'外部核验确认选出的 id 正确，但 output.json 是数组，违反要求的对象结构。请读取现有 output.json，改为只有 ids 字段的 JSON 对象，其值为当前数组。写入后用 read 回读核对，正确后只回复“已完成”并停止。'}
    tasks={};resumes={}
    for name,prompt in feedback.items():
        root=out/name;root.mkdir();shutil.copytree(parent/name/'workspace',root/'workspace')
        task=json.loads((parent/name/'task.json').read_text())
        trace=json.loads((parent/name/'transcript.json').read_text())
        task={**task,'episode_id':task['episode_id']+'-correction','workspace':str(root/'workspace'),
            'prompt':prompt,'initial_files':snapshot(root/'workspace'),'parent_run':str(parent/name),
            'interaction_origin':'external-result-correction-continuation'}
        tasks[name]=task;resumes[name]=trace['session_file'];write_json(root/'task.json',task)
    write_json(out/'manifest.json',{'config':c,'source_snapshot':source_snapshot(),'parent':str(parent),
        'start_time':time.time(),'status':'running','H_used':False,'checkpoint':'W0'})
    server=None;results=[];targets=[]
    try:
        server=Server(config,out/'server.log')
        for name,task in tasks.items():
            verdict=execute_task(task,out/name,c,resume_file=resumes[name])
            selected=certify(task,out/name)
            targets.extend(selected);results.append({'name':name,**verdict,'target_kinds':[x['behavior_kind'] for x in selected]})
        (out/'candidates.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in targets))
        write_json(out/'summary.json',{'results':results,'targets':len(targets),'scope':'same-source actual correction continuations; preceding failures remain context'})
    finally:
        if server:server.stop()
        m=json.loads((out/'manifest.json').read_text());write_json(out/'manifest.json',{**m,'status':'completed' if (out/'summary.json').exists() else 'failed','end_time':time.time()})

if __name__=='__main__':main()
