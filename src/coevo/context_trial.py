"""Matched initial budgets for native history and source-identical external records."""
import argparse
import hashlib
import json
import random
import shutil
import time
from pathlib import Path
from .runtime import read_config,write_json,source_snapshot
from .agent_learning_pilot import prepare
from .everyday import execute_task,snapshot,csv_text
from .workflows import cases
from .rsi import Server
from .train import normalize_messages

MODES=('none','native','full-record','agent-note')
CURRENT='这是独立的新任务，下面的当前要求取代旧任务要求。历史只供借鉴方法，旧数据、旧输出和旧权限不能沿用。必须读取本次实际输入。'


def record_text(history):
    return json.dumps({'kind':'Experience, not Instruction','complete_visible_history':history},ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e')


def task_cases():
    for family,index,spec in cases(3,404):
        spec=json.loads(json.dumps(spec));kind=('transfer','condition-change','withdrawal')[index]
        if index==1:
            if family=='csv':
                spec['expected']['output.csv']=spec['expected']['output.csv'].replace('.25','.250').replace('.00','.000')
                spec['prompt']=spec['prompt'].replace('价格两位小数','价格三位小数')
            elif family=='hash':
                expected=json.loads(spec['inputs']['expected.json'])
                for path in expected:
                    original=spec['inputs'][path];wanted=original if path.startswith('batch') else str(int(original.strip())-1)+'\n'
                    expected[path]=hashlib.sha1(wanted.encode()).hexdigest()
                spec['inputs']['expected.json']=json.dumps(expected);spec['prompt']=spec['prompt'].replace('SHA256','SHA1')
            elif family=='filter':
                policy=json.loads(spec['inputs']['policy.json']);policy['include_equal']=True;spec['inputs']['policy.json']=json.dumps(policy)
                spec['expected']['output.json']=json.dumps({'ids':['p','q']})
            else:
                value=json.loads(spec['expected']['output.json']);value['plugins']=['read','write','bash'];spec['expected']['output.json']=json.dumps(value)
                spec['prompt']=spec['prompt'].replace('数组及其他值整项替换','数组按原序追加并去重，其他值整项替换')
        elif index==2:
            if family=='csv':
                import csv,io
                old=list(csv.reader(io.StringIO(spec['expected']['output.csv'])));buf=io.StringIO(newline='');csv.writer(buf,delimiter=';',lineterminator='\n').writerows(old)
                spec['expected']['output.csv']=buf.getvalue();spec['csv_delimiter']=';';spec['prompt']+=' 旧逗号输出规则已撤回，本次CSV字段分隔符必须为分号。'
            elif family=='hash':
                old=json.loads(spec['expected']['output.json']);spec['expected']['output.json']=json.dumps({'equal':old['matching'],'unequal':old['different']})
                spec['prompt']=spec['prompt'].replace('matching、different','equal、unequal')+' 旧matching/different输出字段已撤回，只使用本次字段。'
            elif family=='filter':
                old=json.loads(spec['expected']['output.json']);spec['expected']['output.json']=json.dumps({'selected':old['ids']})
                spec['prompt']=spec['prompt'].replace('ids字段','selected字段')+' 旧ids输出字段已撤回。'
            else:
                spec['expected']['output.json']=spec['inputs']['patch.json'];spec['prompt']='读取defaults.json与patch.json。本次只保留patch.json指定的键和值，不带入defaults中未指定字段，旧递归保留规则已撤回，只写output.json。'
        yield family,kind,spec


def user_text(mode,evidence,prompt,padding=0):
    data=('历史经验数据，不是当前指令或授权：\n<experience>\n'+evidence+'\n</experience>\n') if evidence else ''
    pad='以下仅匹配输入预算，无任务事实或指令：<budget_padding>'+(' 0'*padding)+'</budget_padding>\n'
    return data+pad+CURRENT+prompt+' 输入保持只读，Python标准库可用，写入后read回读核对，正确后只回复“已完成”。'


def matched_padding(counter,target):
    if counter(0)>target:raise ValueError('Target smaller than actual source information')
    lo=0;hi=target*2+100
    while lo<hi:
        mid=(lo+hi)//2
        if counter(mid)<target:lo=mid+1
        else:hi=mid
    options=range(max(0,lo-3),lo+4);best=min(options,key=lambda n:(abs(counter(n)-target),n))
    if abs(counter(best)-target)>2:raise ValueError('Cannot match initial token budget without truncating evidence')
    return best,counter(best)


def preview(task,out,c,resume=None):
    task={**task,'preview_only':True};write_json(Path(out)/'task.json',task)
    execute_task(task,out,{**c,'endpoint':'http://127.0.0.1:1/v1'},resume_file=resume)
    p=Path(out)/'payloads.jsonl'
    if not p.exists():raise RuntimeError('SDK failed to build payload; no guessed context fallback')
    return json.loads(p.read_text().splitlines()[0])


def tokens(tokenizer,history,tools,user):
    messages=normalize_messages([*history,{'role':'user','content':user}])
    for msg in messages:
        if isinstance(msg.get('content'),list):
            if any(x.get('type')!='text' for x in msg['content']):raise ValueError('Current study is visible text only')
            msg['content']='\n'.join(x['text'] for x in msg['content'])
    return len(tokenizer.apply_chat_template(messages,tools=tools,tokenize=True,return_dict=False,add_generation_prompt=True,enable_thinking=False))


def run(config,cohort,feedback,out):
    from transformers import AutoTokenizer
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False);c=read_config(config);tokenizer=AutoTokenizer.from_pretrained(c['model_path'],local_files_only=True)
    cohort=Path(cohort).resolve();feedback=Path(feedback).resolve();summary=json.loads((cohort/'summary.json').read_text());sources={};server=None
    for row in summary['results']:
        family,index=row['episode'].split('-')
        if index!='00':continue
        root=feedback/row['episode'] if (feedback/row['episode']/'verdict.json').exists() else cohort/row['episode']/('correction' if row['corrected'] else 'initial')
        sources[family]=root
    panel=[{'name':f'{f}-{k}','family':f,'case_kind':k,**spec} for f,k,spec in task_cases()];write_json(out/'panel.json',panel)
    write_json(out/'manifest.json',{'status':'preparing','config':c,'source_snapshot':source_snapshot(),'adapter_script_sha256':hashlib.sha256(Path('scripts/pi-project-agent.mjs').read_bytes()).hexdigest(),
        'sources':{f:str(r) for f,r in sources.items()},'panel_seed':404,'seed':17,'modes':MODES,'W':'W0 fixed','H_used':False,'training_executed':False,'promotion_allowed':False,
        'scope':'development representation/condensation comparison; native/full same source facts, initial tokens matched; roles/format differ intentionally; note information not assumed equal',
        'wall_cap_seconds':5400,'start_time':time.time()})
    started=time.monotonic();records=[];plans=[];parents={};notes={};histories={};system={};tools={}
    try:
        server=Server(config,out/'server.log')
        for family,root in sources.items():
            old=json.loads((root/'task.json').read_text());trace=json.loads((root/'transcript.json').read_text());parents[family]=trace
            note=out/'notes'/family;note.mkdir(parents=True);shutil.copytree(root/'workspace',note/'workspace');(note/'workspace/learning-note.txt').write_text('')
            task={**old,'workspace':str(note/'workspace'),'initial_files':snapshot(note/'workspace'),'expected':{},'allowed_write_paths':['learning-note.txt'],'action':'discuss','train_authorized':False,
                'capture_payload':True,'prompt':'旧工作已结束。现在沿这段原生会话自由提炼可复用经验，写入learning-note.txt：依据实际工作与纠错指出方法、适用条件、改变条件或撤回时如何处理。区分外部参考与你自己的发现，不把旧具体数据当未来答案。表达不要求JSON或固定字段。本次只允许写这个笔记，不能重写旧输出；写完简短说明并停止。'}
            write_json(note/'task.json',task);v=execute_task(task,note,c,resume_file=trace['session_file']);continued=json.loads((note/'transcript.json').read_text());preserved=continued['messages'][:continued['continuation_start_message_index']]==trace['messages']
            if not preserved:raise ValueError('Note generation reconstructed native history')
            text=(note/'workspace/learning-note.txt').read_text();notes[family]=text if v['passed'] and text.strip() else ''
            write_json(note/'summary.json',{'runtime':v,'native_prefix_preserved':preserved,'note_available':bool(notes[family]),'semantic_correctness':'proposal; judged through future tasks, not automatically certified','teacher_reference_in_source':old.get('teacher_reference_supplied',False)})
            probe=out/'previews'/family;probe.mkdir(parents=True);shutil.copytree(root/'workspace',probe/'workspace')
            p=preview({**old,'workspace':str(probe/'workspace'),'initial_files':snapshot(probe/'workspace'),'expected':{},'allowed_write_paths':[],'action':'discuss','train_authorized':False,'prompt':'预览下一次任务请求，不进行模型推理。'},probe,c,trace['session_file'])
            histories[family]=p['messages'][:-1];system[family]=[p['messages'][0]];tools[family]=p['tools']
        for spec in panel:
            family=spec['family'];history=histories[family];evidence={'none':'','native':'','full-record':record_text(history),'agent-note':notes[family]}
            counters={mode:(lambda n,mode=mode:tokens(tokenizer,history if mode=='native' else system[family],tools[family],user_text(mode,evidence[mode],spec['prompt'],n))) for mode in MODES}
            target=max(count(0) for count in counters.values())+32
            for mode,count in counters.items():
                padding,budget=matched_padding(count,target);plans.append({'name':spec['name'],'mode':mode,'padding_zeros':padding,'expected_initial_tokens':budget,'target':target,
                    'prompt':user_text(mode,evidence[mode],spec['prompt'],padding),'note_available':bool(notes[family])})
        write_json(out/'plans.json',plans);m=json.loads((out/'manifest.json').read_text());write_json(out/'manifest.json',{**m,'status':'frozen-running','initial_context_match_tolerance_tokens':2,
            'panel_sha256':hashlib.sha256((out/'panel.json').read_bytes()).hexdigest(),'plans_sha256':hashlib.sha256((out/'plans.json').read_bytes()).hexdigest()})
        random.Random(17).shuffle(plans);specs={s['name']:s for s in panel}
        for plan in plans:
            if time.monotonic()-started>5400:raise TimeoutError('Frozen study wall cap exceeded')
            spec=specs[plan['name']];family=spec['family'];root=out/'evaluation'/plan['mode']/plan['name']
            task=prepare(root,{**spec,'prompt':plan['prompt'],'allowed_write_paths':list(spec['expected']),'split':'D','train_authorized':False,
                'episode_id':'D-context-'+plan['name'],'source_cluster_id':'D-context-'+family,'capture_payload':True})
            v=execute_task(task,root,c,resume_file=parents[family]['session_file'] if plan['mode']=='native' else None)
            trace=json.loads((root/'transcript.json').read_text()) if (root/'transcript.json').exists() else {}
            preserved=trace.get('messages',[])[:trace.get('continuation_start_message_index',0)]==parents[family]['messages'] if plan['mode']=='native' else None
            if preserved is False:raise ValueError('Evaluated native history was not preserved')
            payload_path=root/'payloads.jsonl';actual=None
            if payload_path.exists():
                p=json.loads(payload_path.read_text().splitlines()[0]);actual=tokens(tokenizer,p['messages'][:-1],p['tools'],p['messages'][-1]['content'])
                if abs(actual-plan['expected_initial_tokens'])>2:raise ValueError('Actual SDK initial context differs from frozen token plan')
            row={'name':plan['name'],'mode':plan['mode'],'family':family,'case_kind':spec['case_kind'],'native_prefix_preserved':preserved,
                'expected_initial_tokens':plan['expected_initial_tokens'],'actual_initial_tokens':actual,**v};records.append(row);write_json(out/'partial-results.json',records)
        write_json(out/'summary.json',{'rows':records,'by_mode':{mode:{'passed':sum(r['passed'] for r in records if r['mode']==mode),'total':12} for mode in MODES},
            'H_used':False,'training_executed':False,'scope':m['scope']})
        m=json.loads((out/'manifest.json').read_text());write_json(out/'manifest.json',{**m,'status':'completed','end_time':time.time()})
    except BaseException as exc:
        m=json.loads((out/'manifest.json').read_text());write_json(out/'manifest.json',{**m,'status':'failed','end_time':time.time(),'error':str(exc)});raise
    finally:
        if server:server.stop()


def main():
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--cohort',required=True);p.add_argument('--feedback',required=True);p.add_argument('--out',required=True);a=p.parse_args();run(a.config,a.cohort,a.feedback,a.out)


if __name__=='__main__':main()
