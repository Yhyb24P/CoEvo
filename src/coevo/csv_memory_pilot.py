"""Paired CSV dialect/withdrawal D panel using independently correct L artifacts."""
import argparse
import csv
import io
import json
from pathlib import Path
from .everyday import snapshot
from .runtime import write_json
from .memory import Memory
from .state import State
from .memory_pilot import run

SOURCE=Path('/mnt/e/CoEvo/runs/decision-replay/20261014-v1/quoted_csv')
NAMES=['transferable','unrelated','reversal','withdrawal']


def prepare(out,name):
    out=Path(out).resolve();workspace=out/'workspace';workspace.mkdir(parents=True,exist_ok=False)
    values={'transferable':[['label','price'],['Remote,Site','6.00'],['Team "B"','2.50']],
            'unrelated':[['label','price'],['A','4.00'],['B','7.00']],
            'reversal':[['label','price'],['North,Port','8.00'],['Desk','9.50']],
            'withdrawal':[['label','price'],['East,Gate','1.20'],['Hall','3.00']]}
    rows=values[name];delimiter=';' if name in ('reversal','withdrawal') else ','
    inputs={'source.tsv':'\n'.join('\t'.join(r) for r in rows)+'\n'}
    buf=io.StringIO();csv.writer(buf,delimiter=delimiter,lineterminator='\n').writerows(rows)
    expected={'output.csv':buf.getvalue()}
    prompt=f'读取 source.tsv，转成标准 CSV，本次输出分隔符为 {delimiter!r}，保留字段内部字符与原行序，表头 label,price。只写 output.csv，输入不动；检查后只回复“已完成”。'
    if name=='unrelated':
        expected={'output.json':json.dumps({'total':'11.00'})}
        prompt='读取 source.tsv，将 price 全部求和，保留两位小数。只写 output.json，只有 total 字段，值为字符串。输入不动，检查后只回复“已完成”。'
    if name=='withdrawal':prompt+=' 历史逗号分隔约定已撤回，本次明确使用分号。'
    for rel,text in {**inputs,**{p:'' for p in expected}}.items():(workspace/rel).write_text(text)
    task={'episode_id':f'D-csv-memory-20261014-{name}','source_cluster_id':f'D-csv-memory-20261014-{name}',
        'split':'D','train_authorized':False,'actor':'student','prompt_actor':'researcher','action':'execute',
        'interaction_origin':'controlled-csv-memory-pilot','task_family':'memory-intervention',
        'program_family':'csv-dialect' if name!='unrelated' else 'tabular-aggregation','output_format':'csv' if name!='unrelated' else 'json',
        'inputs':inputs,'expected':expected,'allowed_write_paths':list(expected),'workspace':str(workspace),
        'initial_files':snapshot(workspace),'prompt':prompt,'withdraw_object':'csv-instance','csv_delimiter':delimiter,
        'memory_context':{'operation':'csv' if name!='unrelated' else 'sum','delimiter':',' if name=='withdrawal' else delimiter}}
    # Withdrawal keeps historical retrieval key to test invalidation independently
    # of updated request conditions; the current user request still controls output.
    write_json(out/'task.json',task);return task


def pool(config,mode,out):
    state=State.for_experiment({**config,'arm_id':mode,'state_path':str(out/'state.sqlite')});memory=Memory(state)
    task=json.loads((SOURCE/'task.json').read_text());verdict=json.loads((SOURCE/'verdict.json').read_text())
    if task['split']!='L' or not verdict['outputs'].get('output.csv') or verdict['unauthorized_changes']:
        raise ValueError('Memory requires independently correct L artifact')
    origins=[str(SOURCE/'verdict.json'),str(SOURCE/'transcript.json')]
    memory.register('csv-instance','instance',task['source_cluster_id'],
        json.dumps({'input':task['inputs']['source.tsv'],'output':(SOURCE/'workspace/output.csv').read_text()},ensure_ascii=False),
        {'operation':'csv','delimiter':','},origins)
    memory.register('csv-skill','skill',task['source_cluster_id'],
        '此实例的逗号 CSV 使用 Python csv.writer：字段内部逗号触发双引号包裹，内部双引号重复转义。读取本次字段，不能复制历史数据。此技能仅适用于逗号输出。',
        {'operation':'csv','delimiter':','},origins,['csv-instance'])
    return state,memory


def main():
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--out',required=True)
    a=p.parse_args();run(a.config,a.out,prepare,pool,NAMES,SOURCE)

if __name__=='__main__':main()
