"""Native same-pool selector comparison; unaccepted SU stays a development proxy."""
import argparse
import hashlib
import itertools
import json
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path
from .runtime import read_config,write_json,source_snapshot
from .behavior import certify
from .supervision import project,admit
from .train import encode
from .everyday import execute_task,snapshot
from .agent_learning_pilot import prepare
from .rsi import Server
from .workflows import cases
from .tasks import make_task


def stratified_random(options,budget,seed):
    families=sorted({o['family'] for o in options})
    combinations=[list(c) for c in itertools.product(*[[i for i,o in enumerate(options) if o['family']==f] for f in families])
                  if sum(options[i]['supervised_tokens'] for i in c)<=budget]
    if not combinations:raise ValueError('No whole-sequence stratified selection fits nomination budget')
    return random.Random(seed).choice(combinations)


def matched_schedules(costs,selections,updates=12,max_budget=18000,tolerance=.03,max_microsteps=80,seed=17):
    if any(not s or len(set(s))!=len(s) or any(type(i)!=int or i<0 or i>=len(costs) for i in s) for s in selections.values()):
        raise ValueError('Each matched arm needs explicit unique valid references; abstention is not a training selection')
    if any(type(x)!=int or x<=0 for x in costs):raise ValueError('Positive actual tokenizer costs required')
    tables={}
    for name,selected in selections.items():
        selected=sorted(selected);start=sum(costs[i] for i in selected);dp=[None]*(max_budget+1)
        if start>max_budget:raise ValueError('Budget cannot cover selection')
        dp[start]=tuple(selected)
        for amount in range(start,max_budget+1):
            path=dp[amount]
            if path is None or len(path)>=max_microsteps:continue
            for i in selected:
                target=amount+costs[i]
                if target>max_budget:continue
                proposed=path+(i,)
                if dp[target] is None or (len(proposed),proposed)<(len(dp[target]),dp[target]):dp[target]=proposed
        tables[name]=dp
    latest={name:None for name in tables}
    minimum=updates*max(costs[i] for s in selections.values() for i in s)
    for budget in range(max_budget+1):
        for name,dp in tables.items():
            if dp[budget] is not None and len(dp[budget])>=updates:latest[name]=budget
        if budget<minimum or any(a is None or a<(1-tolerance)*budget for a in latest.values()):continue
        result={}
        for name,amount in latest.items():
            schedule=list(tables[name][amount]);random.Random(seed).shuffle(schedule)
            groups=[[] for _ in range(updates)];loads=[0]*updates
            for i in schedule:
                group=min(range(updates),key=lambda g:(loads[g],g));groups[group].append(i);loads[group]+=costs[i]
            result[name]={'supervised_tokens':amount,'selected':sorted(selections[name]),'update_groups':groups,
                'schedule':[i for g in groups for i in g],'micro_steps':len(schedule),'optimizer_steps':updates}
        return {'budget':budget,'tolerance':tolerance,'arms':result}
    raise ValueError('No common whole-sequence budget within frozen bounds; do not truncate or invent selections')


def freeze(config,cohort,feedback,updated,out):
    from transformers import AutoTokenizer
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False);cohort=Path(cohort).resolve();feedback=Path(feedback).resolve()
    c=read_config(config);tokenizer=AutoTokenizer.from_pretrained(c['model_path'],local_files_only=True)
    old=json.loads((cohort/'summary.json').read_text());pool=[];options=[]
    for row in old['results']:
        name=row['episode'];root=feedback/name if (feedback/name/'verdict.json').exists() else cohort/name/('correction' if row['corrected'] else 'initial')
        task=json.loads((root/'task.json').read_text());verdict=json.loads((root/'verdict.json').read_text())
        if not verdict['passed']:raise ValueError('Shared pool requires completed task trajectories')
        full=project(certify(task,root,certificate_dir=out/'certificates'/name,include_prior_reads=True,include_prior_mutations=True),'full');admit(full)
        ids,labels=encode(tokenizer,full,16384);pool.append(full)
        options.append({'candidate_id':full['candidate_id'],'source_cluster_id':full['source_cluster_id'],'family':name.split('-')[0],
            'file':f'candidate-{len(pool)}.json','supervised_tokens':sum(x!=-100 for x in labels),'context_tokens':len(ids),
            'teacher_reference_supplied':task.get('teacher_reference_supplied',False),
            'target_kinds':[x['behavior_kind'] for x in full['base']['components']]})
    (out/'pool.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in pool));write_json(out/'options.json',options)
    panel=[]
    for family,index,spec in cases(4,202):
        panel.append({**spec,'name':f'D-{family}-{index}','split':'D','train_authorized':False,
            'episode_id':f'D-selector-{family}-{index}','source_cluster_id':f'D-selector-{family}',
            'task_family':'selector-future-instance-panel','allowed_write_paths':list(spec['expected']),
            'prompt':spec['prompt']+' 输入不动，Python标准库可用。写入后用read回读并核对，正确后只回复“已完成”。'})
    for n in range(3):
        legacy=make_task(out/'legacy-fixtures'/str(n),0,n,'G')
        panel.append({**legacy,'name':f'G-{n}','inputs':{'input.json':(Path(legacy['workspace'])/'input.json').read_text()},
            'expected':{'output.json':json.dumps(legacy['expected'])},'output_format':'json','allowed_write_paths':['output.json'],
            'prompt':legacy['prompt']+' 结束时只回复“已完成”。'})
    write_json(out/'panel.json',panel)
    frozen=[Path(config).resolve(),out/'pool.jsonl',out/'options.json',out/'panel.json',*Path(updated).glob('adapter*')]
    frozen=[p for p in frozen if p.is_file()]
    write_json(out/'manifest.json',{'status':'frozen','config':c,'config_path':str(Path(config).resolve()),
        'updated_selector':str(Path(updated).resolve()),'updated_selector_accepted':False,
        'selection_budget':1500,'selection_max_items':6,'selection_max_tool_calls':16,'training_max_budget':18000,'training_max_microsteps':80,
        'training_updates':12,'training_token_tolerance':.03,'training_wall_seconds':600,'seed':17,
        'source_snapshot':source_snapshot(),'inputs_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in frozen},
        'checkpoint_for_all_retraining':'original W0; no previous_adapter','candidate_collection_checkpoint':'W0',
        'selector_roles':{'SF':'W0','SU-proxy':'unaccepted full same-exposure candidate','SR':'uniform feasible family-stratified random'},
        'scope':'development same-pool cross-retraining; SU proxy is not accepted SU, single seed, same generator families, no H or multi-stream claim',
        'panel_seed':202,'H_used':False,'promotion_allowed':False,'created_at':time.time()})


def run(out):
    out=Path(out).resolve();m=json.loads((out/'manifest.json').read_text())
    if m['status']!='frozen':raise ValueError('Started trial cannot be implicitly restarted')
    for p,h in m['inputs_sha256'].items():
        if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=h:raise ValueError('Frozen input changed')
    m={**m,'status':'running','start_time':time.time()};write_json(out/'manifest.json',m)
    pool=[json.loads(x) for x in (out/'pool.jsonl').read_text().splitlines()];options=json.loads((out/'options.json').read_text())
    c=m['config'];server=None;selections={};results={}
    try:
        files={'pool.json':json.dumps([{**o,'index':i+1} for i,o in enumerate(options)],ensure_ascii=False)}
        files.update({o['file']:json.dumps({k:p[k] for k in ['messages','tools','target_indices']},ensure_ascii=False) for o,p in zip(options,pool)})
        anchor=out/'native-anchor'
        task=prepare(anchor,{'inputs':files,'expected':{},'allowed_write_paths':[],'split':'L','train_authorized':False,
            'episode_id':'L-native-selector-anchor','source_cluster_id':'L-native-selector-anchor',
            'prompt':'这是下一批合法学习候选。请用read读取pool.json，了解其编号、来源、真实核验目标、辅助情况及监督token成本。暂不选样或训练，读后简短确认并停止；等待下一步自由讨论。'})
        task['action']='discuss';write_json(anchor/'task.json',task)
        server=Server(m['config_path'],out/'anchor-server.log');verdict=execute_task(task,anchor,c)
        server.stop();server=None
        if not verdict['passed']:raise RuntimeError('Native orientation failed; no reconstructed fallback')
        original=json.loads((anchor/'transcript.json').read_text())
        observed=any(msg.get('role')=='toolResult' and msg.get('toolName')=='read' and not msg.get('isError')
            and '\n'.join(x.get('text','') for x in msg['content'] if x.get('type')=='text')==files['pool.json'] for msg in original['messages'])
        if not observed:raise RuntimeError('Native anchor did not actually observe the common pool')
        prompt=('沿此原生会话讨论如何学习：下一批工作仍需独立完成CSV序列化、完整路径哈希、策略筛选与递归合并，关注首次执行和核对后停止。'
            '候选全是已核验完整片段，错误和教师提示仍作为上下文，不是监督真值。可自行read候选文件了解实际动作，再用自己的自然语言说明取舍。'
            '请通过nominate_training实际记录决定：引用pool.json中的1-based编号，至多6条完整序列、1500监督token；不想训练可引用空列表撤回。'
            '这只记录选择，不改变准入或发布标准。不要写文件，不需要JSON学习提议，不重复已接受的提名，完成讨论后停止。')
        for name,adapter in [('SF',None),('SU-proxy',m['updated_selector'])]:
            root=out/name/'selection';root.mkdir(parents=True);shutil.copytree(anchor/'workspace',root/'workspace')
            selected_task={**task,'workspace':str(root/'workspace'),'initial_files':snapshot(root/'workspace'),'prompt':prompt,
                'learning_candidates':options,'training_selection_token_budget':m['selection_budget'],'training_selection_max_items':m['selection_max_items'],
                'max_tool_calls':m['selection_max_tool_calls']}
            write_json(root/'task.json',selected_task);server=Server(m['config_path'],root/'server.log',adapter)
            v=execute_task(selected_task,root,c,'coevo-current' if adapter else None,resume_file=original['session_file'])
            server.stop();server=None
            trace=json.loads((root/'transcript.json').read_text());start=trace['continuation_start_message_index']
            preserved=trace['messages'][:start]==original['messages']
            if not preserved:raise ValueError('Native prefix changed')
            ledger=root/'learning-selection.jsonl';decisions=[json.loads(x) for x in ledger.read_text().splitlines()] if ledger.exists() else []
            last=decisions[-1] if decisions else None
            refs=[i-1 for i in last['indices']] if v['passed'] and last and last['accepted'] else []
            selections[name]=refs;write_json(root/'summary.json',{'verdict':v,'native_prefix_preserved':preserved,'decisions':decisions,'selected':refs})
            print(json.dumps({'phase':'selected','arm':name,'references':refs}),flush=True)
        selections['SR']=stratified_random(options,m['selection_budget'],m['seed']);write_json(out/'selections.json',selections)
        if any(not s for s in selections.values()):
            write_json(out/'manifest.json',{**m,'status':'completed-without-matched-training','end_time':time.time(),
                'reason':'An Agent abstained or failed to execute selection; no invented fallback or budget-matched claim'});return
        allocation=matched_schedules([o['supervised_tokens'] for o in options],selections,m['training_updates'],m['training_max_budget'],m['training_token_tolerance'],m['training_max_microsteps'],m['seed'])
        write_json(out/'allocation.json',allocation)
        for name,plan in allocation['arms'].items():
            root=out/name;config={**c,'study_id':'q3-selector-development','stream_id':'same-W0-cross-retraining','arm_id':name,
                'training_schedule':plan['schedule'],'training_update_groups':plan['update_groups'],'training_token_cap':allocation['budget'],
                'training_max_length':16384,'training_max_steps':m['training_updates'],'training_max_microsteps':m['training_max_microsteps'],
                'training_loss_mode':'selected-logits','training_wall_seconds':m['training_wall_seconds']}
            path=root/'training-config.json';write_json(path,config)
            with (root/'training.log').open('w') as log:
                p=subprocess.run([sys.executable,'-m','coevo.train','--config',str(path),'--dataset',str(out/'pool.jsonl'),
                    '--adapter-out',str(root/'adapter'),'--seed',str(m['seed'])],stdout=log,stderr=subprocess.STDOUT,timeout=720)
            if p.returncode:raise RuntimeError(f'Cross-retraining failed: {name}')
            write_json(root/'training.json',json.loads((root/'training.log').read_text().splitlines()[-1]))
            print(json.dumps({'phase':'trained','arm':name}),flush=True)
        panel=json.loads((out/'panel.json').read_text())
        for name,adapter in [('W0',None),*[(n,str(out/n/'adapter')) for n in selections]]:
            root=out/name/'evaluation';root.mkdir(parents=True);started=time.monotonic();server=Server(m['config_path'],root/'server.log',adapter);rows=[]
            for spec in panel:
                if time.monotonic()-started>2700:raise TimeoutError('Evaluation wall cap exceeded')
                task=prepare(root/spec['name'],spec);v=execute_task(task,root/spec['name'],c,'coevo-current' if adapter else None);rows.append({'name':spec['name'],**v})
            server.stop();server=None
            results[name]={'rows':rows,'D_passed':sum(r['passed'] for r in rows if r['name'].startswith('D-')),
                'G_passed':sum(r['passed'] for r in rows if r['name'].startswith('G-')),'wall_seconds':time.monotonic()-started}
            write_json(root/'summary.json',results[name]);write_json(out/'results.json',results)
            print(json.dumps({'phase':'evaluated','arm':name,'D':results[name]['D_passed'],'G':results[name]['G_passed']}),flush=True)
        write_json(out/'manifest.json',{**m,'status':'completed','end_time':time.time()})
    except BaseException as exc:
        write_json(out/'manifest.json',{**m,'status':'failed','end_time':time.time(),'error':str(exc)});raise
    finally:
        if server:server.stop()


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--config');p.add_argument('--cohort');p.add_argument('--feedback');p.add_argument('--updated');p.add_argument('--run',action='store_true');a=p.parse_args()
    if a.run:run(a.out)
    else:
        if not all([a.config,a.cohort,a.feedback,a.updated]):p.error('Freeze requires config/cohort/feedback/updated')
        freeze(a.config,a.cohort,a.feedback,a.updated,a.out)


if __name__=='__main__':main()
