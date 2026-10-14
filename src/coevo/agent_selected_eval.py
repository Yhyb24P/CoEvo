"""Fresh no-history hash checks after prospective Agent-selected training."""
import argparse
import hashlib
import json
import time
from pathlib import Path
from .agent_learning_pilot import prepare
from .runtime import read_config,write_json,source_snapshot
from .rsi import Server
from .everyday import execute_task
from .evaluate import evaluate


def cases():
    h=lambda text:hashlib.sha256(text.encode()).hexdigest()
    definitions={
      'mixed-prefixes':({'docs/r.txt':'teal\n','tree/deep/s.txt':'gray\n','top.txt':'azure\n'},
        {'docs/r.txt':h('teal\n'),'tree/deep/s.txt':h('orange\n'),'top.txt':h('azure\n')},
        {'matching':['docs/r.txt','top.txt'],'different':['tree/deep/s.txt']}),
      'dot-paths':({'./root.txt':'north\n','v2/check.txt':'east\n'},
        {'./root.txt':h('north\n'),'v2/check.txt':h('west\n')},
        {'matching':['./root.txt'],'different':['v2/check.txt']})}
    result={}
    for name,(files,checksums,expected) in definitions.items():
        result[name]={'inputs':{'checksums.json':json.dumps(checksums),**files},'expected':{'answer.json':json.dumps(expected)},
            'allowed_write_paths':['answer.json'],'output_format':'json','split':'D','train_authorized':False,
            'episode_id':'D-agent-selected-20261014-'+name,'source_cluster_id':'D-agent-selected-20261014-'+name,
            'task_family':'prospective-agent-selected-update','program_family':'path-preserving-hash-check',
            'prompt':'读取 checksums.json，按清单中所给完整相对路径计算实际文件字节 SHA256。输出 matching 和 different 两个按路径排序的数组，保留清单原路径字符串，包括 ./。只写 answer.json，其他文件不动。可自行选择工具，核对后只回复“已完成”。',
            'interaction_origin':'new-controlled-development-input','scope':'new inputs, shared hash operation family; no H or structural novelty claim'}
    return result


def run(config,out,adapter):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False);c=read_config(config)
    arms={'W0':None,'agent-selected-update':adapter}
    tasks={(arm,name):prepare(out/arm/name,spec) for arm in arms for name,spec in cases().items()}
    write_json(out/'manifest.json',{'config':c,'source_snapshot':source_snapshot(),'arms':arms,'R':'no history or retrieved experience',
        'start_time':time.time(),'status':'running','H_used':False})
    results=[];regression=None;server=None
    try:
        for arm,weights in arms.items():
            server=Server(config,out/(arm+'-server.log'),weights)
            try:
                for name in cases():
                    verdict=execute_task(tasks[arm,name],out/arm/name,c,'coevo-current' if weights else c['served_model'])
                    results.append({'arm':arm,'case':name,**verdict})
                if weights:regression=evaluate(config,out/'G',0,'G','coevo-current')
            finally:server.stop();server=None
        write_json(out/'summary.json',{'results':results,'by_arm':{a:{'passed':sum(r['passed'] for r in results if r['arm']==a),'total':2} for a in arms},
            'G':regression,'G_sampling':'legacy default, not fixed inference seed','D_sampling':c['inference_sampling'],
            'candidate_promoted':False,'H_used':False,'scope':'prospective Agent-selected added-budget pilot; two fresh D inputs in shared operation family, no Q3 selector attribution or statistical gain claim'})
    finally:
        if server:server.stop()
        m=json.loads((out/'manifest.json').read_text());write_json(out/'manifest.json',{**m,'end_time':time.time(),'status':'completed' if (out/'summary.json').exists() else 'failed'})


def main():
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--out',required=True);p.add_argument('--adapter',required=True)
    a=p.parse_args();run(a.config,a.out,a.adapter)

if __name__=='__main__':main()
