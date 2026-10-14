"""Actual small-model learning proposals followed by frozen-W0 task trials."""
import argparse
import hashlib
import json
import time
from pathlib import Path
from .runtime import read_config,write_json,source_snapshot
from .rsi import Server
from .everyday import execute_task,snapshot,csv_text
from .state import State
from .memory import Memory
from .learning_decisions import packet,validate

ROOT=Path('/mnt/e/CoEvo/runs/decision-replay/20261014-v1')
CORRECTION=Path('/mnt/e/CoEvo/runs/decision-replay/20261014-correction-v1')
CONTEXTS={'quoted_csv':{'operation':'csv','delimiter':','},'digest_check':{'operation':'hash','algorithm':'sha256'},
          'conditional_rows':{'operation':'filter','contract':'ids-object'}}
FIXED={
 'quoted_csv':'读取本次 TSV 字段并用 Python csv.writer 生成 CSV，保留字段内部逗号和双引号。用 read 回读实际输出，内容正确后停止，不重复执行转换。',
 'digest_check':'读取本次哈希清单，按完整相对路径读取实际文件字节并计算 SHA256，matching/different 分类保留路径前缀。回读输出后停止。',
 'conditional_rows':'先读本次策略和行数据，按 minimum 与 include_equal 筛选；输出 JSON 对象只有 ids 字段，值为排序后的 id 数组。回读实际输出后停止。'}


def prepare(out,spec):
    out=Path(out);workspace=out/'workspace';workspace.mkdir(parents=True,exist_ok=False)
    for rel,text in {**spec['inputs'],**{p:'' for p in spec['allowed_write_paths']}}.items():
        p=workspace/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
    task={**spec,'workspace':str(workspace),'initial_files':snapshot(workspace),'actor':'student','prompt_actor':'researcher','action':'execute'}
    write_json(out/'task.json',task);return task


def future(name):
    if name=='quoted_csv':
        inputs={'source.tsv':'label\tprice\n Lake,South \t7.3\n Room "C" \t5\n'}
        expected={'output.csv':csv_text([['label','price'],['Lake,South','7.30'],['Room "C"','5.00']])}
        prompt='读取 source.tsv，去除字段两端空格，价格保留两位小数，转换成标准 CSV，保留字段内部字符和原行序，只写 output.csv。'
        fmt='csv'
    elif name=='digest_check':
        digest=lambda x:hashlib.sha256(x.encode()).hexdigest()
        inputs={'expected.json':json.dumps({'records/m.txt':digest('red\n'),'records/n.txt':digest('green\n')}),
            'records/m.txt':'blue\n','records/n.txt':'green\n'}
        expected={'output.json':json.dumps({'matching':['records/n.txt'],'different':['records/m.txt']})}
        prompt='读取 expected.json，按文件实际字节的 SHA256 将清单中的路径分成 matching、different 两个排序数组，保留完整相对路径。只写 output.json。'
        fmt='json'
    else:
        inputs={'policy.json':json.dumps({'minimum':9,'include_equal':True}),
            'rows.json':json.dumps([{'id':'v','score':9},{'id':'w','score':14},{'id':'u','score':2}])}
        expected={'output.json':json.dumps({'ids':['v','w']})}
        prompt='读取本次 policy.json 和 rows.json，按 minimum 与 include_equal 筛选符合条件的行。只写 output.json，JSON 对象只有 ids 字段，其值为按 id 排序的数组。'
        fmt='json'
    return {'inputs':inputs,'expected':expected,'prompt':prompt+' 输入不动，核对结果后只回复“已完成”。',
        'allowed_write_paths':list(expected),'output_format':fmt,'split':'D','train_authorized':False,
        'episode_id':'D-agent-learning-20261014-'+name,'source_cluster_id':'D-agent-learning-20261014-'+name,
        'task_family':'agent-learning-future-task','program_family':name,'interaction_origin':'controlled-new-input-learning-decision-trial'}


def run(config,out,adapter):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False);c=read_config(config)
    candidates=[json.loads(x) for p in [ROOT/'selected-candidates.jsonl',CORRECTION/'candidates.jsonl'] for x in p.read_text().splitlines()]
    pools={};packets={};proposaltasks={};futures={};decisions={};results=[];proposal_results=[]
    for name,context in CONTEXTS.items():
        task=json.loads((ROOT/name/'task.json').read_text());source=task['source_cluster_id']
        pools[name]=[x for x in candidates if x['source_cluster_id']==source]
        traces=[]
        for root in [ROOT,CORRECTION]:
            p=root/name/'transcript.json'
            if p.exists():
                trace=json.loads(p.read_text());traces.append({'origin':str(p),'messages':trace['messages'],
                    'continuation_start_message_index':trace.get('continuation_start_message_index',0)})
        packets[name]=packet(source,context,task,traces,pools[name])
        write_json(out/'packets'/f'{name}.json',packets[name])
    for arm in ['W0-proposer','updated-candidate-proposer']:
        for name,info in packets.items():
            prompt='用 read 读取 evidence.json 的真实交互与纠错，提出此次经验学习和训练选样决策。只用 write 写 proposal.json，JSON 严格包含 source_cluster_id、memory_kind（none/instance/skill）、body（经验或技能文本）、conditions（只用 context 中已观察键值，可取子集）、training_candidate_ids（从 candidates 中选择最多4个不同ID，可为空）、reason（依据）。不复制工具观察为 Assistant 目标，不把失败动作或错误完成宣称当正确目标；可保存正确片段。不要修改准入或发布标准。来源照抄；none 时 body 为空字符串、conditions 为空对象。输入不动，写完只回复“已完成”。'
            proposaltasks[arm,name]=prepare(out/'proposals'/arm/name,{'inputs':{'evidence.json':json.dumps(info,ensure_ascii=False)},
                'expected':{},'allowed_write_paths':['proposal.json'],'prompt':prompt,'output_format':'json',
                'split':'L','train_authorized':False,'episode_id':f'proposal-{arm}-{name}',
                'source_cluster_id':info['source_cluster_id'],'interaction_origin':'small-model-learning-proposal',
                'task_family':'learning-decision','program_family':name,'verification_scope':'runtime only; separate frozen proposal gate'})
    for mode in ['no-memory','fixed-rule','W0-proposer','updated-candidate-proposer']:
        for name in CONTEXTS:futures[mode,name]=prepare(out/'future'/mode/name,future(name))
    write_json(out/'manifest.json',{'config':c,'candidate_adapter':adapter,'candidate_is_accepted':False,
        'source_snapshot':source_snapshot(),'start_time':time.time(),'status':'running','H_used':False,
        'selection_budget_per_source':4,'memory_budget':{'max_items':1,'max_chars':2400},
        'comparison':'W0 versus updated unpromoted proposer on same L pool; all future execution frozen W0',
        'scope':'Q1/model-assisted distillation pilot; not formal Q3 selector benefit or RSI'})
    server=None
    try:
        for arm,weights in [('W0-proposer',None),('updated-candidate-proposer',adapter)]:
            server=Server(config,out/(arm+'-server.log'),weights)
            try:
                for name,info in packets.items():
                    root=out/'proposals'/arm/name
                    runtime=execute_task(proposaltasks[arm,name],root,c,'coevo-current' if weights else c['served_model'])
                    record={'arm':arm,'case':name,'runtime':runtime,'proposal_valid':False}
                    try:
                        if runtime.get('agent_exit_code')!=0 or runtime.get('unauthorized_changes'):
                            raise ValueError('Proposal runtime failed or modified protected inputs')
                        proposal=json.loads((root/'workspace/proposal.json').read_text())
                        decision=validate(proposal,info,pools[name]);decisions[arm,name]=decision
                        record.update(proposal_valid=True,proposal=proposal,selected_count=len(decision['selected']))
                        write_json(root/'decision.json',decision)
                    except (ValueError,KeyError,TypeError,OSError) as error:record['rejection_reason']=str(error)
                    proposal_results.append(record)
            finally:server.stop();server=None
        for arm in ['W0-proposer','updated-candidate-proposer']:
            selected=[target for name in CONTEXTS for target in decisions.get((arm,name),{}).get('selected',[])]
            (out/(arm+'-selected.jsonl')).write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in selected))
        server=Server(config,out/'future-W0-server.log')
        for index,name in enumerate(CONTEXTS):
            modes=['no-memory','fixed-rule','W0-proposer','updated-candidate-proposer'];modes=modes[index:]+modes[:index]
            for mode in modes:
                root=out/'future'/mode/name;task=futures[mode,name];retrieval={'text':'','selected_ids':[]}
                state=State.for_experiment({**c,'arm_id':mode,'stream_id':name,'state_path':str(root/'state.sqlite')})
                try:
                    memory=Memory(state)
                    if mode=='fixed-rule':
                        memory.register('fixed-skill','skill',packets[name]['source_cluster_id'],FIXED[name],CONTEXTS[name],[str(out/'packets'/f'{name}.json')])
                    elif (mode,name) in decisions:
                        proposal=decisions[mode,name]['proposal']
                        if proposal['memory_kind']!='none':
                            memory.register('agent-proposed-experience',proposal['memory_kind'],proposal['source_cluster_id'],proposal['body'],proposal['conditions'],[str(out/'proposals'/mode/name/'decision.json')])
                    retrieval=memory.retrieve(CONTEXTS[name],'M1' if mode!='fixed-rule' and decisions.get((mode,name),{}).get('proposal',{}).get('memory_kind')=='instance' else 'M3',max_items=1,max_chars=2400)
                    task['experience_context']=retrieval['text'];write_json(root/'retrieval.json',retrieval);write_json(root/'task.json',task)
                    verdict=execute_task(task,root,c);results.append({'mode':mode,'case':name,'selected_ids':retrieval['selected_ids'],**verdict})
                finally:state.close()
        summary={'proposals':proposal_results,'future_results':results,'by_mode':{m:{'passed':sum(r['passed'] for r in results if r['mode']==m),'total':3} for m in ['no-memory','fixed-rule','W0-proposer','updated-candidate-proposer']},
            'training_executed':False,'candidate_promoted':False,'H_used':False,
            'scope':'Agent actually proposes memory and selects existing certified targets; proposed skill truth not automatically certified; no selector-training causal result yet'}
        write_json(out/'summary.json',summary)
    finally:
        if server:server.stop()
        m=json.loads((out/'manifest.json').read_text());write_json(out/'manifest.json',{**m,'status':'completed' if (out/'summary.json').exists() else 'failed','end_time':time.time()})


def main():
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--out',required=True);p.add_argument('--adapter',required=True)
    a=p.parse_args();run(a.config,a.out,a.adapter)

if __name__=='__main__':main()
