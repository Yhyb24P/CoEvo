"""Fresh L interaction, actual correction and Agent-selected certified targets."""
import argparse
import hashlib
import json
import shutil
import time
from pathlib import Path
from .agent_learning_pilot import prepare
from .everyday import execute_task,snapshot
from .behavior import certify
from .learning_decisions import packet,validate
from .runtime import read_config,write_json,source_snapshot
from .rsi import Server


def run(config,out,parent):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False);parent=Path(parent).resolve();c=read_config(config)
    previous=json.loads((parent/'proposals/updated-candidate-proposer/digest_check/decision.json').read_text())['proposal']
    h=lambda text:hashlib.sha256(text.encode()).hexdigest()
    spec={'inputs':{'expected.json':json.dumps({'archive/u.txt':h('silver\n'),'archive/v.txt':h('gold\n')}),
            'archive/u.txt':'silver\n','archive/v.txt':'bronze\n'},
        'expected':{'output.json':json.dumps({'matching':['archive/u.txt'],'different':['archive/v.txt']})},
        'prompt':'读取 expected.json，按其中完整相对路径检查实际文件字节 SHA256，将相同与不同路径放入 matching、different 排序数组。只写 output.json，输入不动。核对后只回复“已完成”。',
        'allowed_write_paths':['output.json'],'output_format':'json','split':'L','train_authorized':True,
        'episode_id':'L-agent-feedback-20261014-hash','source_cluster_id':'L-agent-feedback-20261014-hash',
        'task_family':'agent-experience-correction','program_family':'path-preserving-hash-check',
        'interaction_origin':'fresh-controlled-L-with-agent-proposed-experience',
        'experience_context':json.dumps({'source_cluster_id':previous['source_cluster_id'],'body':previous['body']},ensure_ascii=False)}
    initial=prepare(out/'initial',spec)
    write_json(out/'manifest.json',{'config':c,'source_snapshot':source_snapshot(),'parent':str(parent),
        'new_L_source':spec['source_cluster_id'],'D_input_reused':False,'weights':'W0','max_selected_targets':2,
        'provenance_bound_by':'controller','H_used':False,'status':'running','start_time':time.time()})
    server=None
    try:
        server=Server(config,out/'server.log')
        initial_verdict=execute_task(initial,out/'initial',c)
        source_root=out/'initial';task=initial
        if not initial_verdict['passed']:
            root=out/'correction';root.mkdir();shutil.copytree(source_root/'workspace',root/'workspace')
            task={**initial,'episode_id':initial['episode_id']+'-correction','workspace':str(root/'workspace'),
                'initial_files':snapshot(root/'workspace'),'experience_context':'',
                'prompt':'外部检查发现当前核对结果不正确。清单中的路径已经是完整相对路径，不应追加历史 docs/ 或其他目录前缀。请读取当前清单与实际文件，按文件字节重新核对 SHA256，修正 output.json，回读检查后只回复“已完成”。',
                'parent_run':str(source_root),'interaction_origin':'external-result-correction-continuation'}
            write_json(root/'task.json',task)
            trace=json.loads((source_root/'transcript.json').read_text())
            correction_verdict=execute_task(task,root,c,resume_file=trace['session_file']);source_root=root
        else:correction_verdict=None
        targets=certify(task,source_root)
        (out/'candidates.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in targets))
        traces=[{'messages':json.loads((source_root/'transcript.json').read_text())['messages'],
            'origin':str(source_root/'transcript.json')}]
        info=packet(spec['source_cluster_id'],{'operation':'hash','algorithm':'sha256'},initial,traces,targets)
        write_json(out/'evidence.json',info)
        proposal_task=prepare(out/'proposal',{'inputs':{'evidence.json':json.dumps(info,ensure_ascii=False)},'expected':{},
            'allowed_write_paths':['proposal.json'],'output_format':'json','split':'L','train_authorized':False,
            'episode_id':spec['episode_id']+'-learning-proposal','source_cluster_id':spec['source_cluster_id'],
            'task_family':'learning-decision','program_family':'hash-skill-revision',
            'prompt':'用 read 读取 evidence.json。依据实际工具结果和外部纠错，更新可迁移经验，并选最多两个已核验训练目标。只用 write 写 proposal.json，严格包含 memory_kind（none/instance/skill）、body、conditions（context 键值的子集）、training_candidate_ids、reason 五个字段。来源由控制器绑定，不生成 source_cluster_id。不要把历史目录、数值等实例细节写成通用步骤，指出以前经验哪里需要修正；不能把外部纠错说成自主发现。只从 candidates 选择不同ID，可不选。none 时 body 为空字符串、conditions 为空对象。输入不动，写完只回复“已完成”。'})
        runtime=execute_task(proposal_task,out/'proposal',c)
        record={'initial':initial_verdict,'correction':correction_verdict,'certified_targets':len(targets),'proposal_runtime':runtime}
        try:
            raw=json.loads((out/'proposal/workspace/proposal.json').read_text())
            if 'source_cluster_id' in raw:raise ValueError('Source is controller-owned in this protocol')
            if runtime.get('agent_exit_code')!=0 or runtime.get('unauthorized_changes'):raise ValueError('Proposal runtime failed')
            decision=validate({'source_cluster_id':info['source_cluster_id'],**raw},info,targets,max_selected=2)
            write_json(out/'decision.json',decision)
            (out/'selected.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in decision['selected']))
            record.update(proposal_valid=True,proposal=decision['proposal'],selected_targets=len(decision['selected']))
        except (ValueError,KeyError,TypeError,OSError) as error:record.update(proposal_valid=False,rejection_reason=str(error))
        write_json(out/'summary.json',{**record,'training_executed':False,'candidate_promoted':False,'H_used':False,
            'scope':'fresh L correction and prospective agent selection; new proposed skill not automatically certified'})
    finally:
        if server:server.stop()
        m=json.loads((out/'manifest.json').read_text());write_json(out/'manifest.json',{**m,'status':'completed' if (out/'summary.json').exists() else 'failed','end_time':time.time()})


def main():
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--out',required=True);p.add_argument('--parent',required=True)
    p.add_argument('--repair',action='store_true')
    a=p.parse_args()
    if a.repair:
        repair(a.config,a.out,a.parent)
    else:
        run(a.config,a.out,a.parent)


def repair(config,out,parent):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False);parent=Path(parent).resolve();c=read_config(config)
    info=json.loads((parent/'evidence.json').read_text())
    targets=[json.loads(x) for x in (parent/'candidates.jsonl').read_text().splitlines()]
    task=json.loads((parent/'proposal/task.json').read_text())
    shutil.copytree(parent/'proposal/workspace',out/'workspace')
    task={**task,'workspace':str(out/'workspace'),'initial_files':snapshot(out/'workspace'),
        'prompt':'固定准入器拒绝本次提议：conditions 只能是 evidence.json 中 context 键值的子集。可用 context 为 '+json.dumps(info['context'],ensure_ascii=False)+'。path_format、no_prefix_addition 不是允许的条件键；相关经验可放在 body 内。请用 read 回读 evidence.json 与 proposal.json，然后修改 proposal.json 的条件字段，其他字段仍遵循原 schema 和至多两个目标预算。来源由控制器绑定，不输出 source_cluster_id。不要更改规则或输入。写完只回复“已完成”。'}
    write_json(out/'task.json',task);write_json(out/'manifest.json',{'parent':str(parent),'config':c,
        'source_snapshot':source_snapshot(),'start_time':time.time(),'status':'running','max_repair_attempts':1,
        'source_cluster_id':info['source_cluster_id'],'H_used':False})
    server=None
    try:
        server=Server(config,out/'server.log')
        trace=json.loads((parent/'proposal/transcript.json').read_text())
        runtime=execute_task(task,out,c,resume_file=trace['session_file'])
        result={'runtime':runtime,'proposal_valid':False}
        try:
            raw=json.loads((out/'workspace/proposal.json').read_text())
            if 'source_cluster_id' in raw:raise ValueError('Source is controller-owned')
            if runtime.get('agent_exit_code')!=0 or runtime.get('unauthorized_changes'):raise ValueError('Proposal runtime failed')
            decision=validate({'source_cluster_id':info['source_cluster_id'],**raw},info,targets,max_selected=2)
            write_json(out/'decision.json',decision)
            (out/'selected.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in decision['selected']))
            result.update(proposal_valid=True,proposal=decision['proposal'],selected_targets=len(decision['selected']))
        except (ValueError,KeyError,TypeError,OSError) as error:result['rejection_reason']=str(error)
        write_json(out/'summary.json',{**result,'training_executed':False,'scope':'one actual schema-feedback continuation; frozen gate unchanged'})
    finally:
        if server:server.stop()
        m=json.loads((out/'manifest.json').read_text());write_json(out/'manifest.json',{**m,'status':'completed' if (out/'summary.json').exists() else 'failed','end_time':time.time()})

if __name__=='__main__':main()
