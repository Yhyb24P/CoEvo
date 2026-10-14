"""Independent development inputs for post-update tool behavior, no training use."""
import argparse
import hashlib
import json
import time
from pathlib import Path
from .everyday import csv_text,execute_task,snapshot
from .runtime import read_config,write_json,source_snapshot
from .rsi import Server


def cases():
    defaults={'app':{'timeout':30,'theme':'light'},'plugins':['read','write'],'audit':True}
    patch={'app':{'timeout':15},'plugins':['bash']}
    markdown='# Notes\n\n[Guide](docs/manual.md)\n[Jump](docs/manual.md#usage)\n[Web](https://example.invalid/docs/manual.md)\n![Icon](docs/manual.md)\n\n```text\n[Example](docs/manual.md)\n```\n'
    repaired=markdown.replace('[Guide](docs/manual.md)','[Guide](docs/manual-v2.md)').replace('[Jump](docs/manual.md#usage)','[Jump](docs/manual-v2.md#usage)')
    h=lambda text:hashlib.sha256(text.encode()).hexdigest()
    manifest={'files/a.txt':h('alpha\n'),'files/b.txt':h('old\n'),'files/c.txt':h('missing\n')}
    return {
      'nested_merge':{'program_family':'nested-json-overlay-array-replacement','output_format':'json',
          'inputs':{'defaults.json':json.dumps(defaults,indent=2),'patch.json':json.dumps(patch,indent=2)},
          'expected':{'output.json':json.dumps({'app':{'timeout':15,'theme':'light'},'plugins':['bash'],'audit':True})},
          'prompt':'读取 defaults.json 和 patch.json，将 patch 递归合并到 defaults：对象逐键递归，数组及其他值整项替换，没有覆盖的字段保留。只写 output.json，原文件不动。检查后只回复“已完成”。'},
      'dialect':{'program_family':'tsv-to-csv-dialect-conversion','output_format':'csv',
          'inputs':{'data.tsv':'name\tamount\n Lab,East \t12.5\n Home \t8\n'},
          'expected':{'output.csv':csv_text([['name','amount'],['Lab,East','12.50'],['Home','8.00']])},
          'prompt':'读取制表符分隔的 data.tsv，去除字段两端空格，保留字段内部的逗号，金额保留两位小数。转成标准逗号分隔 CSV，表头 name,amount，原行序不变，只写 output.csv。原文件不动，检查后只回复“已完成”。'},
      'markdown_links':{'program_family':'markdown-context-aware-local-link-migration','output_format':'text',
          'inputs':{'notes.md':markdown},'expected':{'output.md':repaired},
          'prompt':'读取 notes.md，将正文中的普通本地 Markdown 链接 docs/manual.md 改为 docs/manual-v2.md，原片段标识保留。不修改外部 URL、图片链接或围栏代码块内的示例；其余字符保持原样。只写 output.md，原文件不动，检查后只回复“已完成”。'},
      'manifest':{'program_family':'filesystem-inventory-digest-reconciliation','output_format':'json',
          'inputs':{'manifest.json':json.dumps(manifest,indent=2),'files/a.txt':'alpha\n','files/b.txt':'beta\n','files/d.txt':'delta\n'},
          'expected':{'output.json':json.dumps({'missing':['files/c.txt'],'changed':['files/b.txt'],'unexpected':['files/d.txt']})},
          'prompt':'读取 manifest.json，并检查 files/ 下实际文件及其 SHA-256（文件字节）。将清单中缺失的文件列入 missing，存在但哈希不同的列入 changed，实际存在但未在清单中的列入 unexpected。各列表按路径排序，只写 output.json，包含这三个键；原文件不动。可使用 Python 标准库计算哈希，检查后只回复“已完成”。'},
    }


def prepare(out,name):
    out=Path(out).resolve();workspace=out/'workspace';workspace.mkdir(parents=True,exist_ok=False)
    spec=cases()[name]
    for name_,text in {**spec['inputs'],**{p:'' for p in spec['expected']}}.items():
        p=workspace/name_;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
    task={**spec,'episode_id':f'D-independent-20261014-{name}','source_cluster_id':f'D-independent-20261014-{name}',
          'split':'D','train_authorized':False,'actor':'student','prompt_actor':'researcher',
          'interaction_origin':'controlled-held-out-program-family-development','task_family':'independent-tool-panel',
          'workspace':str(workspace),'allowed_write_paths':list(spec['expected']),'action':'execute',
          'initial_files':snapshot(workspace),'scope':'new input and intended operation families, D not sealed H'}
    write_json(out/'task.json',task);return task


def run(config,out,adapter,only_arm=None):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False);c=read_config(config)
    arms={'W0':None,'teacher-replay':adapter}
    if only_arm:
        arms={only_arm:arms[only_arm]}
    tasks={arm:{name:prepare(out/arm/name,name) for name in cases()} for arm in arms}
    write_json(out/'manifest.json',{'scope':'new-family D comparison, not formal H evidence','config':c,'arms':arms,
        'R':'no external memory in both arms','W':'original W0 versus saved mixture Adapter',
        'source_snapshot':source_snapshot(),'start_time':time.time(),'status':'running','H_used':False})
    results=[]
    try:
        for arm,path in arms.items():
            server=None
            try:
                server=Server(config,out/(arm+'-server.log'),path)
                model='coevo-current' if path else c['served_model']
                for name,task in tasks[arm].items():
                    verdict=execute_task(task,out/arm/name,c,model)
                    results.append({'arm':arm,'case':name,**verdict})
            finally:
                if server:server.stop()
        summary={'results':results,'by_arm':{arm:{'passed':sum(r['passed'] for r in results if r['arm']==arm),'total':len(cases())} for arm in arms},
            'inference_sampling':c['inference_sampling'],'candidate_promoted':False,'H_used':False,
            'scope':'one new D input per family; descriptive headroom/transfer pilot, no statistical benefit claim'}
        write_json(out/'summary.json',summary);print(json.dumps(summary['by_arm'],ensure_ascii=False));return summary
    finally:
        m=json.loads((out/'manifest.json').read_text());write_json(out/'manifest.json',{
            **m,'end_time':time.time(),'status':'completed' if (out/'summary.json').exists() else 'failed'})


def main():
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--out',required=True);p.add_argument('--adapter',required=True)
    p.add_argument('--only-arm',choices=['W0','teacher-replay'])
    a=p.parse_args();run(a.config,a.out,a.adapter,a.only_arm)


if __name__=='__main__':main()
