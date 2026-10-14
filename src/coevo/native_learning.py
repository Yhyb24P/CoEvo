"""Learning discussion in the task's actual Pi session, without proposal schema."""
import argparse
import json
import shutil
import time
import hashlib
from pathlib import Path
from .runtime import read_config,source_snapshot,write_json
from .everyday import execute_task,snapshot
from .rsi import Server


def run(config,out,parent,feedback_file=None):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False);parent=Path(parent).resolve();c=read_config(config)
    original=json.loads((parent/'task.json').read_text());trace=json.loads((parent/'transcript.json').read_text())
    shutil.copytree(parent/'workspace',out/'workspace')
    task={**original,'episode_id':original['episode_id']+'-native-learning','workspace':str(out/'workspace'),
        'initial_files':snapshot(out/'workspace'),'expected':{},'allowed_write_paths':[],'action':'discuss',
        'train_authorized':False,'experience_context':'','interaction_origin':'original-task-session-learning-discussion',
        'prompt':'刚才的任务与纠错结束了，现在沿用这段原生会话继续讨论你的学习。由你判断：哪些经验值得保留、怎样改变以后做事的步骤、适用范围是什么、哪些实际动作值得让模型学习、哪些错误不能复用，以及接下来最值得尝试什么。不要求固定字段或 JSON，不必为填表重复读取已经知道的信息；可用自然语言或你认为合适的表达。请依据刚才的真实交互，把外部纠错与你自己发现的事情区分开。现在是学习讨论，原任务“只回复已完成”的要求不适用于这次回复。无需修改文件。'}
    if feedback_file:
        task['prompt']=Path(feedback_file).read_text()
        task['external_feedback_ref']=str(Path(feedback_file).resolve())
        task['train_authorized']=False
    write_json(out/'task.json',task);write_json(out/'manifest.json',{'source_cluster_id':original['source_cluster_id'],
        'parent':str(parent),'parent_session':trace['session_file'],'config':c,'source_snapshot':source_snapshot(),
        'status':'running','start_time':time.time(),'forced_proposal_schema':False,'context_compacted':False,'H_used':False})
    server=None
    try:
        server=Server(config,out/'server.log')
        runtime=execute_task(task,out,c,resume_file=trace['session_file'])
        continued=json.loads((out/'transcript.json').read_text())
        before=continued.get('continuation_start_message_index',0)
        # Compare actual SDK messages; not a reconstruction or a model summary.
        native_prefix_preserved=continued['messages'][:before]==trace['messages']
        record={'runtime':runtime,'native_prefix_preserved':native_prefix_preserved,
            'parent_message_count':len(trace['messages']),'continuation_start_message_index':before,
            'visible_learning_response':continued.get('final_text',''),
            'source_cluster_id':original['source_cluster_id'],'actor':'student-W0',
            'proposal_format':'unconstrained visible natural response','semantic_correctness':'not automatically certified',
            'training_executed':False,'candidate_promoted':False,'H_used':False}
        write_json(out/'summary.json',record)
    finally:
        if server:server.stop()
        manifest=json.loads((out/'manifest.json').read_text());write_json(out/'manifest.json',{**manifest,
            'status':'completed' if (out/'summary.json').exists() else 'failed','end_time':time.time()})


def main():
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--out',required=True);p.add_argument('--parent',required=True)
    p.add_argument('--try-next',action='store_true');p.add_argument('--feedback-file');p.add_argument('--act-on-feedback',action='store_true');p.add_argument('--stress-next',action='store_true')
    a=p.parse_args()
    if a.stress_next:
        act_on_feedback(a.config,a.out,a.parent,stress=True)
    elif a.act_on_feedback:
        act_on_feedback(a.config,a.out,a.parent)
    elif a.try_next:
        next_trial(a.config,a.out,a.parent)
    else:
        run(a.config,a.out,a.parent,a.feedback_file)


def next_trial(config,out,parent):
    from .behavior import certify
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False);parent=Path(parent).resolve();c=read_config(config)
    original=json.loads((parent/'task.json').read_text());trace=json.loads((parent/'transcript.json').read_text())
    h=lambda text:hashlib.sha256(text.encode()).hexdigest()
    inputs={'mixed.json':json.dumps({'docs/k.txt':h('amber\n'),'plain.txt':h('violet\n'),'nested/deep/z.txt':h('black\n')}),
        'docs/k.txt':'amber\n','plain.txt':'violet\n','nested/deep/z.txt':'white\n'}
    expected={'mixed-output.json':json.dumps({'matching':['docs/k.txt','plain.txt'],'different':['nested/deep/z.txt']})}
    tasks={}
    for mode in ['native-context','fresh-context']:
        root=out/mode;root.mkdir();shutil.copytree(parent/'workspace',root/'workspace')
        for name,text in {**inputs,'mixed-output.json':''}.items():
            p=root/'workspace'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
        task={**original,'episode_id':original['episode_id']+'-mixed-paths-'+mode,'workspace':str(root/'workspace'),
            'initial_files':snapshot(root/'workspace'),'inputs':inputs,'expected':expected,'allowed_write_paths':['mixed-output.json'],
            'action':'execute','train_authorized':True,'output_format':'json','split':'L','experience_context':'',
            'prompt':'下一项工作：读取 mixed.json。清单包含带目录和不带目录的完整相对路径，按实际文件字节 SHA256 比对，输出 matching 与 different 两个按路径排序的数组。只允许修改 mixed-output.json，其余文件保持不变。你可自行决定工具和步骤，核对结果后只回复“已完成”。',
            'curriculum_origin':'Agent suggested mixed paths in previous native discussion; researcher built fixture and checker',
            'scope':'same-source L derived curriculum trial; context comparison, no independent D/H generalization claim'}
        tasks[mode]=task;write_json(root/'task.json',task)
    write_json(out/'manifest.json',{'config':c,'source_snapshot':source_snapshot(),'parent':str(parent),
        'source_cluster_id':original['source_cluster_id'],'start_time':time.time(),'status':'running',
        'weights':'W0','same_inputs_and_external_state':True,'H_used':False})
    server=None;results=[]
    try:
        server=Server(config,out/'server.log')
        for mode,task in tasks.items():
            root=out/mode
            runtime=execute_task(task,root,c,resume_file=trace['session_file'] if mode=='native-context' else None)
            targets=certify(task,root)
            t=json.loads((root/'transcript.json').read_text())
            results.append({'mode':mode,**runtime,'certified_target_kinds':[x['behavior_kind'] for x in targets],
                'native_prefix_preserved':t['messages'][:t.get('continuation_start_message_index',0)]==trace['messages'] if mode=='native-context' else None})
        write_json(out/'summary.json',{'results':results,'training_executed':False,'candidate_promoted':False,
            'scope':'actual task chosen from Agent suggestion; same-input native context versus fresh context; single L case, context budgets differ'})
    finally:
        if server:server.stop()
        m=json.loads((out/'manifest.json').read_text());write_json(out/'manifest.json',{**m,'status':'completed' if (out/'summary.json').exists() else 'failed','end_time':time.time()})


def act_on_feedback(config,out,parent,stress=False):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False);parent=Path(parent).resolve();c=read_config(config)
    original=json.loads((parent/'task.json').read_text());trace=json.loads((parent/'transcript.json').read_text())
    h=lambda text:hashlib.sha256(text.encode()).hexdigest()
    inputs={'audit.json':json.dumps({'deep/a/b/p.txt':h('red\n'),'./keep.txt':h('gray\n'),
        'empty.bin':h(''),'gone.txt':h('absent\n')}),
        'deep/a/b/p.txt':'red\n','./keep.txt':'teal\n','empty.bin':''}
    expected={'audit-output.json':json.dumps({'matching':['deep/a/b/p.txt','empty.bin'],
        'different':['./keep.txt'],'missing':['gone.txt']})}
    prompt='现在实际做下一项路径边界工作：读取 audit.json，按清单中完整相对路径核对文件实际字节 SHA256。输出 audit-output.json，JSON 对象包含 matching、different、missing 三个键，值是排序路径数组；不存在的文件归 missing，存在但哈希不同归 different，保留原路径字符串包括 ./。其他输入不动。工具和步骤由你决定。'
    if stress:
        large='0123456789abcdef\n'*70000
        inputs={'stress.json':json.dumps({'资料/第 一份.txt':h('真实字节：青色\n'),
            'semi;colon.txt':h('expected\n'),'大 文件/分块.dat':h(large),'空 缺/缺失.txt':h('absent\n')},ensure_ascii=False),
            '资料/第 一份.txt':'真实字节：青色\n','semi;colon.txt':'actual\n','大 文件/分块.dat':large}
        expected={'stress-output.json':json.dumps({'matching':['大 文件/分块.dat','资料/第 一份.txt'],
            'different':['semi;colon.txt'],'missing':['空 缺/缺失.txt']},ensure_ascii=False)}
        prompt='按你在学习笔记里提出的建议，现在实际测试中文、空格、分号路径与超过1MiB的文件。读取 stress.json，按其完整相对路径核对实际文件字节 SHA256。只写 stress-output.json，JSON 对象含 matching、different、missing 三个排序数组，保留原路径字符串。文件不存在归 missing，存在但哈希不符归 different，输入不动。工具和步骤由你决定。'
    prompt+=' 你也可以自行读取或更新 learning-notes.md，把有效经验、需要撤回的旧假设、是否值得继续参数学习及下一步行动记下来；内容与形式由你决定，不要求填表。现在只允许修改结果文件和学习笔记，不直接启动训练。完成核对后只回复“已完成”。'
    tasks={}
    for mode in ['native-context','fresh-context']:
        root=out/mode;root.mkdir();shutil.copytree(parent/'workspace',root/'workspace')
        additions={**inputs,**{p:'' for p in expected}}
        if not stress:additions['learning-notes.md']=''
        for name,text in additions.items():
            p=root/'workspace'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
        task={**original,'episode_id':('D-feedback-stress-' if stress else 'D-feedback-action-')+'20261014-'+mode,
            'source_cluster_id':original['source_cluster_id'] if stress else 'D-feedback-action-20261014','split':'D','train_authorized':False,
            'workspace':str(root/'workspace'),'initial_files':snapshot(root/'workspace'),
            'inputs':inputs,'expected':expected,'allowed_write_paths':[*expected,'learning-notes.md'],
            'action':'execute','output_format':'json','experience_context':'',
            'prompt':prompt,
            'curriculum_origin':'Agent suggested special-character paths/large files in its own notes' if stress else 'Agent suggested nested/dot paths and missing files after actual update feedback; researcher supplies fixture/checker',
            'context_sources':[original['source_cluster_id'],'D-agent-selected-20261014-mixed-prefixes','D-agent-selected-20261014-dot-paths'],
            'scope':'D exploratory curriculum; native context includes previous D feedback, not a legal L training sequence'}
        tasks[mode]=task;write_json(root/'task.json',task)
    write_json(out/'manifest.json',{'config':c,'source_snapshot':source_snapshot(),'parent':str(parent),
        'start_time':time.time(),'status':'running','context_compacted':False,'weights':'W0','H_used':False,
        'comparison':'same task/files; actual native session continuation versus fresh session with same existing notes' if stress else 'same task/files; actual native session continuation versus fresh session; no reconstructed history'})
    server=None;results=[]
    try:
        server=Server(config,out/'server.log')
        for mode,task in tasks.items():
            root=out/mode
            verdict=execute_task(task,root,c,resume_file=trace['session_file'] if mode=='native-context' else None)
            t=json.loads((root/'transcript.json').read_text());start=t.get('continuation_start_message_index',0)
            calls=[part for m in t['messages'][start:] for part in m.get('content',[]) if isinstance(part,dict) and part.get('type')=='toolCall']
            note=(root/'workspace/learning-notes.md').read_text()
            results.append({'mode':mode,**verdict,'native_prefix_preserved':t['messages'][:start]==trace['messages'] if mode=='native-context' else None,
                'continuation_start_message_index':start,'tool_call_count':len(calls),
                'tool_names':[x['name'] for x in calls],'learning_notes':note,'notes_written':bool(note.strip()),
                'notes_updated':task['initial_files'].get('learning-notes.md')!=snapshot(task['workspace']).get('learning-notes.md'),
                'notes_read':any(x['name']=='read' and x.get('arguments',{}).get('path','').endswith('learning-notes.md') for x in calls)})
        write_json(out/'summary.json',{'results':results,'training_executed':False,'candidate_promoted':False,
            'scope':'actual work plus optional Agent-authored learning state; notes are proposals not automatically verified truth; single paired exploratory task'})
    finally:
        if server:server.stop()
        m=json.loads((out/'manifest.json').read_text());write_json(out/'manifest.json',{**m,'status':'completed' if (out/'summary.json').exists() else 'failed','end_time':time.time()})

if __name__=='__main__':main()
