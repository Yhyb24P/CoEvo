"""Small W0 M0-M3 behavior pilot on new controlled tool episodes."""
import argparse
import json
import time
from pathlib import Path
from .runtime import read_config,write_json,source_snapshot
from .state import State
from .memory import Memory
from .everyday import execute_task,snapshot
from .rsi import Server

CASES={
 'transferable':{'operation':'unique','values':[5,-2,5,10,-2],'order':'ascending'},
 'unrelated':{'operation':'sum','values':[-6,17,17,2],'order':'not-applicable'},
 'reversal':{'operation':'sort','values':[5,-2,5,10,-2],'order':'ascending'},
 'withdrawal':{'operation':'unique','values':[11,4,11,-5],'order':'descending'},
}
SOURCE=Path('/mnt/e/CoEvo/runs/codex-replay-pilot/20261014-W0-rootfix/replay/unique')


def prepare(out,name):
    out=Path(out).resolve();workspace=out/'workspace';workspace.mkdir(parents=True,exist_ok=False)
    case=CASES[name];values=case['values'];op=case['operation']
    expected=sum(values) if op=='sum' else sorted(values) if op=='sort' else sorted(set(values),reverse=case['order']=='descending')
    inputs={'input.json':json.dumps(case,ensure_ascii=False,indent=2)+'\n'}
    outputs={'output.json':json.dumps({'result':expected},ensure_ascii=False)+'\n'}
    for path,text in {**inputs,'output.json':''}.items():(workspace/path).write_text(text)
    requirement={'unique':'去重，再按指定 order 排列，输出数组','sort':'按升序排序并保留重复值，输出数组','sum':'对全部值求和，重复值也计入，输出数字'}[op]
    prompt=f'本次任务是 {op}：{requirement}。请用 read 读取 input.json 的实际值；计算可使用 Python 标准库。用 write 写 output.json，只有 result 一个字段。原输入不动，只允许修改 output.json。核对后只回复“已完成”。'
    if name=='withdrawal':prompt+=' 之前的升序约定已经撤回；本次明确要求 unique 结果按降序排列。'
    task={'episode_id':f'D-memory-20261014-{name}','source_cluster_id':f'D-memory-20261014-{name}',
          'split':'D','train_authorized':False,'actor':'student','prompt_actor':'researcher',
          'interaction_origin':'controlled-memory-pilot','program_family':f'file-{op}',
          'task_family':'memory-intervention','output_format':'json','action':'execute',
          'inputs':inputs,'expected':outputs,'allowed_write_paths':['output.json'],'workspace':str(workspace),
          'initial_files':snapshot(workspace),'prompt':prompt,'memory_context':{'operation':op},
          'scope':'new input sources, shared elementary program families; no structural-transfer or formal Q1 claim'}
    write_json(out/'task.json',task);return task


def pool(config,mode,out):
    c={**config,'arm_id':mode,'state_path':str(out/'state.sqlite')}
    state=State.for_experiment(c);memory=Memory(state)
    task=json.loads((SOURCE/'task.json').read_text());verdict=json.loads((SOURCE/'verdict.json').read_text())
    if not verdict['passed'] or task['split']!='L':raise ValueError('Shared memory must come from a verified L source')
    actual=json.loads((SOURCE/'workspace/output.json').read_text())
    body='过去的成功实例：'+json.dumps({'input':json.loads(task['inputs']['input.json']),'output':actual},ensure_ascii=False)
    memory.register('unique-instance','instance',task['source_cluster_id'],body,{'operation':'unique'},[str(SOURCE/'verdict.json')])
    memory.register('unique-skill','skill',task['source_cluster_id'],
                    '历史程序经验：去除 values 中的重复数字，再按升序排列；result 应为数组。读取本次实际值，不使用历史实例的具体数值。',
                    {'operation':'unique'},[str(SOURCE/'verdict.json')],['unique-instance'])
    return state,memory


def run(config,out,prepare_task=prepare,create_pool=pool,case_names=None,source=SOURCE):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False);c=read_config(config)
    modes=['M0','M1','M2','M3'];tasks={};pools={}
    names=list(case_names or CASES)
    for mode in modes:
        pools[mode]=create_pool(c,mode,out/mode)
        tasks[mode]={name:prepare_task(out/mode/name,name) for name in names}
    write_json(out/'manifest.json',{'scope':'single W0 instance-transfer memory development pilot',
        'weights':'W0 frozen','adapter':None,'source_ref':str(source),'config':c,'modes':modes,
        'task_sources':[tasks[modes[0]][n]['source_cluster_id'] for n in names],
        'retrieval_budget':{'max_items':1,'max_chars':1000},'source_snapshot':source_snapshot(),
        'inference_seed_fixed':bool(c.get('inference_sampling')),'H_used':False,'start_time':time.time(),'status':'running'})
    server=None;results=[]
    try:
        server=Server(config,out/'server.log')
        # Rotate paired execution order by case, reducing fixed late-arm effects.
        for index,name in enumerate(names):
            for mode in modes[index%4:]+modes[:index%4]:
                state,memory=pools[mode];task=tasks[mode][name]
                if name=='withdrawal':memory.revoke(task.get('withdraw_object','unique-instance'),'researcher-simulated withdrawal before this paired task')
                retrieval=memory.retrieve(task['memory_context'],mode,max_items=1,max_chars=1000)
                task['experience_context']=retrieval['text']
                write_json(out/mode/name/'retrieval.json',retrieval)
                write_json(out/mode/name/'task.json',task)
                verdict=execute_task(task,out/mode/name,c)
                results.append({'mode':mode,'case':name,'selected_ids':retrieval['selected_ids'],**verdict})
        summary={'results':results,'by_mode':{m:{'passed':sum(r['passed'] for r in results if r['mode']==m),'total':len(names)} for m in modes},
                 'weights_updated':False,'training_executed':False,'H_used':False,
                 'scope':'development pilot; conditions/revocation mechanism measured separately from behavioral benefit'}
        write_json(out/'summary.json',summary);print(json.dumps(summary['by_mode'],ensure_ascii=False))
        return summary
    finally:
        if server:server.stop()
        for state,_ in pools.values():state.close()
        manifest=json.loads((out/'manifest.json').read_text());write_json(out/'manifest.json',{
            **manifest,'end_time':time.time(),'status':'completed' if (out/'summary.json').exists() else 'failed'})


def main():
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--out',required=True)
    a=p.parse_args();run(a.config,a.out)


if __name__=='__main__':main()
