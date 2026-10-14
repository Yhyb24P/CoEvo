"""Shared multi-episode L collection and native, actionable learning decisions."""
import argparse
import hashlib
import json
import random
import shutil
import time
from pathlib import Path
from .agent_learning_pilot import prepare
from .everyday import csv_text,execute_task,snapshot
from .behavior import certify,admit
from .runtime import read_config,write_json,source_snapshot
from .rsi import Server


def cases(variants,seed):
    for index in range(variants):
        rng=random.Random(seed+index)
        a,b=rng.randrange(2,20),rng.randrange(20,40)
        price1,price2=f'{a}.25',f'{b}.00'
        quoted={'output_format':'csv','program_family':'csv-field-serialization',
            'inputs':{'source.tsv':f'label\tprice\n Site,{index} \t{price1}\n Room "{index}" \t{price2}\n'},
            'expected':{'output.csv':csv_text([['label','price'],[f'Site,{index}',price1],[f'Room "{index}"',price2]])},
            'prompt':'读取 source.tsv，把制表符分隔数据转为标准 CSV，去除字段两端空格、价格两位小数，保留字段内部字符与原行序，表头 label,price。只写 output.csv。'}
        h=lambda text:hashlib.sha256(text.encode()).hexdigest()
        folder=f'batch{index}/sub';path1=f'{folder}/a.txt';path2=f'./row{index}.txt'
        digest={'output_format':'json','program_family':'path-preserving-hash-check',
            'inputs':{'expected.json':json.dumps({path1:h(f'{a}\n'),path2:h(f'{b}\n')}),path1:f'{a}\n',path2:f'{b+1}\n'},
            'expected':{'output.json':json.dumps({'matching':[path1],'different':[path2]})},
            'prompt':'读取 expected.json，对清单完整相对路径的实际文件字节计算 SHA256；输出 matching、different 两个排序数组，保留原路径字符串包括 ./，只写 output.json。'}
        inclusive=bool(index%2)
        rows=[{'id':'p','score':a},{'id':'q','score':b},{'id':'r','score':a-1}]
        conditional={'output_format':'json','program_family':'observed-policy-row-selection',
            'inputs':{'policy.json':json.dumps({'minimum':a,'include_equal':inclusive}),'rows.json':json.dumps(rows)},
            'expected':{'output.json':json.dumps({'ids':['p','q'] if inclusive else ['q']})},
            'prompt':'读取 policy.json 和 rows.json，minimum为阈值，include_equal决定是否包括等于阈值的行；输出只有ids字段的JSON对象，值为符合策略的id排序数组，只写 output.json。'}
        defaults={'app':{'timeout':a,'theme':f'theme{index}'},'plugins':['read','write'],'audit':True}
        patch={'app':{'timeout':b},'plugins':['bash']}
        merged={'app':{'timeout':b,'theme':f'theme{index}'},'plugins':['bash'],'audit':True}
        nested={'output_format':'json','program_family':'nested-json-overlay-array-replacement',
            'inputs':{'defaults.json':json.dumps(defaults),'patch.json':json.dumps(patch)},
            'expected':{'output.json':json.dumps(merged)},
            'prompt':'读取 defaults.json 与 patch.json，将patch递归合并到defaults：对象逐键递归，数组及其他值整项替换，未覆盖字段保留，只写 output.json。'}
        for family,spec in [('csv',quoted),('hash',digest),('filter',conditional),('merge',nested)]:
            yield family,index,spec


def collect(config,out,batch,variants=3,seed=17,learning_discussion=True):
    from transformers import AutoTokenizer
    from .train import encode
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False);c=read_config(config)
    tokenizer=AutoTokenizer.from_pretrained(c['model_path'],local_files_only=True)
    tasks={}
    for family,index,spec in cases(variants,seed):
        name=f'{family}-{index:02d}'
        task=prepare(out/name/'initial',{**spec,'episode_id':f'L-{batch}-{name}',
            'source_cluster_id':f'L-{batch}-{family}','split':'L','train_authorized':True,
            'task_family':'shared-supervision-workflows','interaction_origin':'fresh-controlled-learning-stream',
            'allowed_write_paths':list(spec['expected']),
            'prompt':spec['prompt']+' 输入不动，可自行选择工具，Python标准库可用。写入后用read回读并核对，正确后只回复“已完成”。',
            'scope':'controlled variants share family-level source clusters; no independent-source inflation'})
        tasks[name]=task
    write_json(out/'manifest.json',{'config':c,'source_snapshot':source_snapshot(),'batch':batch,'variants':variants,'seed':seed,
        'episodes':len(tasks),'source_clusters':sorted({t['source_cluster_id'] for t in tasks.values()}),
        'learning_discussion':learning_discussion,
        'checkpoint':'W0','max_corrections_per_episode':1,'selection_max_items':2,'selection_token_cap':1000,
        'all_sources':'L only; no prior D/G/H task content imported','start_time':time.time(),'status':'running'})
    results=[];all_candidates=[];all_selected=[];server=None
    try:
        server=Server(config,out/'server.log')
        for name,initial in tasks.items():
            if time.time()-json.loads((out/'manifest.json').read_text())['start_time']>c.get('collection_wall_seconds',1200):
                raise TimeoutError('Collection exceeded frozen wall budget')
            initial_root=out/name/'initial';verdict=execute_task(initial,initial_root,c)
            task=initial;root=initial_root;initial_verdict=verdict
            if not verdict['passed']:
                root=out/name/'correction';root.mkdir();shutil.copytree(initial_root/'workspace',root/'workspace')
                correct_artifacts=bool(verdict.get('outputs')) and all(verdict['outputs'].values())
                feedback=('外部核验结果文件内容正确，但未正常完成。不要重复写入或计算，回读现有结果确认后停止。' if correct_artifacts else
                    '外部核验发现当前结果不满足任务要求。请重读本次输入与原要求，检查计算、字段、JSON对象结构、排序及字段转义，修正结果，回读确认后停止。')
                task={**initial,'episode_id':initial['episode_id']+'-correction','workspace':str(root/'workspace'),
                    'initial_files':snapshot(root/'workspace'),'parent_run':str(initial_root),
                    'prompt':feedback+' 原始输入和权限不变；正确后只回复“已完成”。'}
                write_json(root/'task.json',task)
                trace=json.loads((initial_root/'transcript.json').read_text())
                verdict=execute_task(task,root,c,resume_file=trace['session_file'])
            candidates=certify(task,root,include_prior_reads=True)
            all_candidates.extend(candidates)
            record={'episode':name,'source_cluster_id':task['source_cluster_id'],'initial':initial_verdict,
                'final':verdict,'corrected':root!=initial_root,'candidate_kinds':[x['behavior_kind'] for x in candidates]}
            # L-only native session; prose is not a target, actual nomination is.
            if candidates and learning_discussion:
                options=[];eligible=[]
                for candidate in candidates:
                    admit(candidate)
                    try:ids,labels=encode(tokenizer,candidate,c.get('training_max_length',5120))
                    except ValueError:continue
                    eligible.append(candidate)
                    options.append({'candidate_id':candidate['candidate_id'],'source_cluster_id':candidate['source_cluster_id'],
                        'kind':candidate['behavior_kind'],'target':candidate['target'],'supervised_tokens':sum(v!=-100 for v in labels)})
                selection=out/name/'learning';selection.mkdir();shutil.copytree(root/'workspace',selection/'workspace')
                listing='\n'.join(f'{i+1}. '+json.dumps(o,ensure_ascii=False) for i,o in enumerate(options))
                discussion={**task,'workspace':str(selection/'workspace'),'initial_files':snapshot(selection/'workspace'),
                    'expected':{},'allowed_write_paths':[],'action':'discuss','train_authorized':False,
                    'learning_candidates':options,'training_selection_token_budget':1000,'training_selection_max_items':2,
                    'prompt':'沿刚才原生会话讨论你的学习：哪些实际行为最值得学习，哪些只是当前样本细节，是否暂不训练？用你自己的自然语言表达，不要求JSON提议。若决定执行候选选样，可调用nominate_training引用下列已核验动作编号；至多两个完整动作、1000监督token，不自行改变核验或发布标准。空列表撤回选样。工具只记录提名，不启动训练。未核验错误动作与自评不在候选中。\n'+listing}
                write_json(selection/'task.json',discussion)
                parent_trace=json.loads((root/'transcript.json').read_text())
                runtime=execute_task(discussion,selection,c,resume_file=parent_trace['session_file'])
                new_trace=json.loads((selection/'transcript.json').read_text())
                start=new_trace['continuation_start_message_index']
                ledger=selection/'learning-selection.jsonl'
                decisions=[json.loads(x) for x in ledger.read_text().splitlines()] if ledger.exists() else []
                last=decisions[-1] if decisions else None
                selected=[candidate for candidate in eligible if last and last['accepted'] and candidate['candidate_id'] in last['selected_ids']]
                if runtime.get('agent_exit_code')!=0 or runtime.get('unauthorized_changes'):selected=[]
                all_selected.extend(selected)
                record['learning']={'runtime':runtime,'native_prefix_preserved':new_trace['messages'][:start]==parent_trace['messages'],
                    'decisions':decisions,'selected_ids':[x['candidate_id'] for x in selected],
                    'selection_method':'actual tool action after free native discussion; no historical JSON proposal parser'}
            results.append(record);write_json(out/name/'summary.json',record)
        (out/'candidates.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in all_candidates))
        (out/'agent-selected.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in all_selected))
        write_json(out/'summary.json',{'results':results,'episodes':len(results),'source_clusters':len({t['source_cluster_id'] for t in tasks.values()}),
            'initial_passed':sum(r['initial']['passed'] for r in results),'final_passed':sum(r['final']['passed'] for r in results),
            'verified_targets':len(all_candidates),'agent_selected_targets':len(all_selected),
            'training_executed':False,'H_used':False,'scope':'shared L cohort and native actionable selection; no SF/SU/SR attribution claim'})
    finally:
        if server:server.stop()
        m=json.loads((out/'manifest.json').read_text());write_json(out/'manifest.json',{**m,'end_time':time.time(),'status':'completed' if (out/'summary.json').exists() else 'failed'})



def reference(family):
    scripts={
      'csv':"import csv\nwith open('source.tsv',newline='') as f: rows=list(csv.reader(f,delimiter='\\t'))\nwith open('output.csv','w',newline='') as f:\n w=csv.writer(f); w.writerow(['label','price'])\n for label,price in rows[1:]: w.writerow([label.strip(),f'{float(price.strip()):.2f}'])",
      'filter':"import json\np=json.load(open('policy.json')); rows=json.load(open('rows.json'))\nids=sorted(r['id'] for r in rows if r['score']>p['minimum'] or (p['include_equal'] and r['score']==p['minimum']))\njson.dump({'ids':ids},open('output.json','w'))",
      'hash':"import json,hashlib\ne=json.load(open('expected.json')); out={'matching':[],'different':[]}\nfor path,h in e.items():\n actual=hashlib.sha256(open(path,'rb').read()).hexdigest()\n out['matching' if actual==h else 'different'].append(path)\nfor values in out.values(): values.sort()\njson.dump(out,open('output.json','w'))"}
    return scripts[family]


def repair(config,out,parent):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False);parent=Path(parent).resolve();c=read_config(config)
    source_summary=json.loads((parent/'summary.json').read_text());tasks={};parents={}
    for row in source_summary['results']:
        if row['final']['passed']:continue
        name=row['episode'];old_root=parent/name/('correction' if row['corrected'] else 'initial')
        old=json.loads((old_root/'task.json').read_text());root=out/name;root.mkdir();shutil.copytree(old_root/'workspace',root/'workspace')
        correct=bool(row['final'].get('outputs')) and all(row['final']['outputs'].values())
        guidance=('外部检查确认当前结果内容已经正确，之前只是没有停止。不要重复计算或写入，只用read回读确认后只回复“已完成”并停止。' if correct else
            '外部检查确认当前结果仍不正确。以下是研究助手提供的参考实现（教师辅助，不是你的自主推导），根据实际输入计算，不提供检查器答案。可据此修正，随后用read回读输出，正确后只回复“已完成”并停止；不要重复执行已成功的步骤。\n```python\n'+reference(name.split('-')[0])+'\n```')
        task={**old,'episode_id':old['episode_id']+'-targeted-feedback','workspace':str(root/'workspace'),
            'initial_files':snapshot(root/'workspace'),'parent_run':str(old_root),'prompt':guidance,
            'prompt_actor':'researcher-teacher' if not correct else 'external-verifier',
            'interaction_origin':'one-additional-targeted-feedback-on-same-L-episode','teacher_reference_supplied':not correct}
        tasks[name]=task;parents[name]=old_root;write_json(root/'task.json',task)
    write_json(out/'manifest.json',{'config':c,'source_snapshot':source_snapshot(),'parent':str(parent),
        'start_time':time.time(),'status':'running','max_additional_feedback_per_episode':1,'checkpoint':'W0',
        'scope':'same original cohort; assisted result separate from original autonomous/first-correction counts','H_used':False})
    server=None;results=[];targets=[]
    try:
        server=Server(config,out/'server.log')
        for name,task in tasks.items():
            trace=json.loads((parents[name]/'transcript.json').read_text())
            verdict=execute_task(task,out/name,c,resume_file=trace['session_file'])
            nominated=certify(task,out/name,include_prior_reads=True,include_prior_mutations=True)
            targets.extend(nominated);current=json.loads((out/name/'transcript.json').read_text());start=current['continuation_start_message_index']
            result={'episode':name,**verdict,'teacher_reference_supplied':task['teacher_reference_supplied'],
                'candidate_kinds':[t['behavior_kind'] for t in nominated],
                'native_prefix_preserved':current['messages'][:start]==trace['messages']}
            results.append(result);write_json(out/name/'summary.json',result)
        (out/'candidates.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in targets))
        write_json(out/'summary.json',{'results':results,'passed':sum(r['passed'] for r in results),'attempted':len(results),
            'original_initial_passed':source_summary['initial_passed'],'original_first_correction_passed':source_summary['final_passed'],
            'training_executed':False,'scope':'additional external teaching/stop correction, not independent W0 capability improvement'})
    finally:
        if server:server.stop()
        m=json.loads((out/'manifest.json').read_text());write_json(out/'manifest.json',{**m,'status':'completed' if (out/'summary.json').exists() else 'failed','end_time':time.time()})

def main():
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--out',required=True);p.add_argument('--batch',default='shared-20261014');p.add_argument('--resume-cohort')
    p.add_argument('--variants',type=int,default=3);p.add_argument('--seed',type=int,default=17)
    p.add_argument('--no-learning-discussion',action='store_true',help='Collect shared candidates; defer selection to a separate same-pool comparison')
    a=p.parse_args()
    if a.resume_cohort:repair(a.config,a.out,a.resume_cohort)
    else:collect(a.config,a.out,a.batch,a.variants,a.seed,not a.no_learning_discussion)

if __name__=='__main__':main()
