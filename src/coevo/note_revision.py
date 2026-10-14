"""Agent-authored experience revision with an extra-deliberation control."""
import argparse
import hashlib
import json
import random
import shutil
import time
from pathlib import Path
from .runtime import read_config,write_json,source_snapshot
from .everyday import execute_task,snapshot
from .agent_learning_pilot import prepare
from .context_trial import task_cases,user_text,matched_padding,tokens,record_text
from .rsi import Server

MODES=('none','old-note','self-review','feedback-review','full-record')
REVIEW='沿这段原生会话继续改进learning-note.txt，保留可靠方法，修正不准确概括，说明条件变化和撤回时怎样处理。可回看实际工作和旧笔记，自由表达，不要求JSON或固定字段。只允许修改这个笔记，不修改旧输入输出。写完简短说明并停止。'


def feedback_data(parent,family):
    parent=Path(parent);summary=json.loads((parent/'summary.json').read_text());panel={x['name']:x for x in json.loads((parent/'panel.json').read_text())}
    rows=[]
    for row in summary['rows']:
        if row['mode']!='agent-note' or row['family']!=family:continue
        spec=panel[row['name']];item={'case_kind':row['case_kind'],'current_user_requirement':spec['prompt'],'external_result':'passed' if row['passed'] else 'failed'}
        if not row['passed']:
            workspace=parent/'evaluation/agent-note'/row['name']/'workspace'
            item['actual_output']={name:(workspace/name).read_text() for name in spec['expected']}
            item['checks']=row.get('outputs',{})
        rows.append(item)
    return rows


def run(config,parent,out):
    from transformers import AutoTokenizer
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False);parent=Path(parent).resolve();c=read_config(config)
    tokenizer=AutoTokenizer.from_pretrained(c['model_path'],local_files_only=True)
    panel=[{'name':f'{f}-{k}','family':f,'case_kind':k,**spec} for f,k,spec in task_cases(505)];write_json(out/'panel.json',panel)
    write_json(out/'manifest.json',{'status':'preparing','config':c,'parent':str(parent),'source_snapshot':source_snapshot(),
        'adapter_script_sha256':hashlib.sha256(Path('scripts/pi-project-agent.mjs').read_bytes()).hexdigest(),
        'panel_seed':505,'seed':17,'modes':MODES,'W':'W0 fixed','H_used':False,'training_executed':False,'promotion_allowed':False,
        'note_revision_split':'D; inherited L plus exposed D feedback; not legal L training targets',
        'scope':'development feedback-driven note revision vs extra deliberation; same future panel and initial tokens, roles/contents differ by intervention',
        'wall_cap_seconds':5400,'start_time':time.time()})
    server=None;started=time.monotonic();notes={};contexts={};tools={};records=[];plans=[]
    try:
        server=Server(config,out/'server.log')
        for family in ['csv','hash','filter','merge']:
            oldroot=parent/'notes'/family;old=json.loads((oldroot/'task.json').read_text());trace=json.loads((oldroot/'transcript.json').read_text())
            oldtext=(oldroot/'workspace/learning-note.txt').read_text();notes[family]={'none':'','old-note':oldtext}
            original=json.loads((parent/'previews'/family/'payloads.jsonl').read_text().splitlines()[0]);contexts[family]=[original['messages'][0]];tools[family]=original['tools']
            notes[family]['full-record']=record_text(original['messages'][:-1])
            feedback=feedback_data(parent,family);write_json(out/'feedback'/f'{family}.json',feedback)
            for mode in ['self-review','feedback-review']:
                root=out/'revision'/mode/family;root.mkdir(parents=True);shutil.copytree(oldroot/'workspace',root/'workspace')
                prompt=REVIEW
                if mode=='feedback-review':prompt+='\n这些是你的旧笔记在先前D任务中实际使用的外部反馈，不是你的自主发现。分析哪些方法保留、哪些需要修订，不能把旧输出数字当未来答案；这里不提供检查器期望答案或新的参考代码：\n'+json.dumps(feedback,ensure_ascii=False)
                task={**old,'workspace':str(root/'workspace'),'initial_files':snapshot(root/'workspace'),'prompt':prompt,
                    'capture_payload':True,'split':'D','source_cluster_id':'D-note-revision-'+family,'train_authorized':False,
                    'interaction_origin':'native-experience-revision','feedback_origins':['L original work','D exposed note evaluation'] if mode=='feedback-review' else ['L original work','D extra-deliberation intervention']}
                write_json(root/'task.json',task);v=execute_task(task,root,c,resume_file=trace['session_file']);new=json.loads((root/'transcript.json').read_text())
                preserved=new['messages'][:new['continuation_start_message_index']]==trace['messages']
                if not preserved:raise ValueError('Revision did not preserve original native note session')
                text=(root/'workspace/learning-note.txt').read_text();notes[family][mode]=text if v['passed'] and text.strip() else ''
                write_json(root/'summary.json',{'runtime':v,'native_prefix_preserved':preserved,'note_available':bool(notes[family][mode]),
                    'note_sha256':hashlib.sha256(text.encode()).hexdigest(),'source_split':'D','train_authorized':False,
                    'semantic_correctness':'proposal; independent future task outcomes required'})
                print(json.dumps({'phase':'revision','family':family,'mode':mode,'available':bool(notes[family][mode])}),flush=True)
        for spec in panel:
            family=spec['family'];counters={mode:(lambda n,mode=mode:tokens(tokenizer,contexts[family],tools[family],user_text(mode,notes[family][mode],spec['prompt'],n))) for mode in MODES}
            target=max(f(0) for f in counters.values())+32
            for mode,counter in counters.items():
                padding,budget=matched_padding(counter,target);plans.append({'name':spec['name'],'mode':mode,'padding_zeros':padding,
                    'expected_initial_tokens':budget,'prompt':user_text(mode,notes[family][mode],spec['prompt'],padding),'note_available':bool(notes[family][mode])})
        write_json(out/'plans.json',plans);m=json.loads((out/'manifest.json').read_text());write_json(out/'manifest.json',{**m,'status':'frozen-running',
            'panel_sha256':hashlib.sha256((out/'panel.json').read_bytes()).hexdigest(),'plans_sha256':hashlib.sha256((out/'plans.json').read_bytes()).hexdigest()})
        random.Random(17).shuffle(plans);specs={x['name']:x for x in panel}
        for plan in plans:
            if time.monotonic()-started>5400:raise TimeoutError('Frozen note revision wall cap')
            spec=specs[plan['name']];root=out/'evaluation'/plan['mode']/plan['name']
            task=prepare(root,{**spec,'prompt':plan['prompt'],'allowed_write_paths':list(spec['expected']),'split':'D','train_authorized':False,
                'episode_id':'D-note-revision-'+plan['name'],'source_cluster_id':'D-note-revision-'+spec['family'],'capture_payload':True})
            v=execute_task(task,root,c);payload=root/'payloads.jsonl';actual=None;reported=None
            if payload.exists():
                p=json.loads(payload.read_text().splitlines()[0]);actual=tokens(tokenizer,p['messages'][:-1],p['tools'],p['messages'][-1]['content'])
                if abs(actual-plan['expected_initial_tokens'])>2:raise ValueError('Actual SDK context differs from frozen budget')
                trace=json.loads((root/'transcript.json').read_text());first=next(x for x in trace['messages'] if x['role']=='assistant');u=first.get('usage',{})
                reported=u.get('input',0)+u.get('cacheRead',0)+u.get('cacheWrite',0)
            row={'name':plan['name'],'mode':plan['mode'],'family':spec['family'],'case_kind':spec['case_kind'],
                'expected_initial_tokens':plan['expected_initial_tokens'],'actual_initial_tokens':actual,'reported_initial_tokens':reported,**v}
            records.append(row);write_json(out/'partial-results.json',records)
        write_json(out/'summary.json',{'rows':records,'by_mode':{mode:{'passed':sum(x['passed'] for x in records if x['mode']==mode),'total':12} for mode in MODES},
            'scope':m['scope'],'H_used':False,'training_executed':False})
        m=json.loads((out/'manifest.json').read_text());write_json(out/'manifest.json',{**m,'status':'completed','end_time':time.time()})
    except BaseException as exc:
        m=json.loads((out/'manifest.json').read_text());write_json(out/'manifest.json',{**m,'status':'failed','end_time':time.time(),'error':str(exc)});raise
    finally:
        if server:server.stop()


def main():
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--parent',required=True);p.add_argument('--out',required=True);a=p.parse_args();run(a.config,a.parent,a.out)


if __name__=='__main__':main()
