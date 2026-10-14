"""Same-trace supervision masks and explicit whole-sequence budget plans."""
import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from .runtime import write_json,read_config
from .sequences import compose,encode as encode_sequence


def output_target(component):
    if component['behavior_kind']=='write':return True
    if component['behavior_kind']!='bash':return False
    trace=Path(component['raw_generation_and_tool_trace_ref'])
    states=trace.parent/'tool-states.jsonl'
    call=component['target']['tool_calls'][0]['id']
    if not states.exists():return False
    for line in states.read_text().splitlines():
        state=json.loads(line)
        if state['tool_call_id']==call:
            return any(value!=state['before_outputs'].get(path) for path,value in state['after_outputs'].items())
    return False


def project(components,mode):
    if mode not in ('output-only','full'):raise ValueError('Unknown supervision mode')
    base=compose(components)
    selected=base['target_indices'] if mode=='full' else [len(c['prefix']) for c in base['components'] if output_target(c)]
    if not selected:raise ValueError('Trace has no verified output-producing target')
    return {'candidate_format':'verified_behavior_ablation_v1','candidate_id':base['candidate_id']+'-'+mode,
        'source_cluster_id':base['source_cluster_id'],'split':'L','train_authorized':True,
        'actor':'student','behavior_kind':'same-trace-'+mode,'mode':mode,'base':base,
        'messages':base['messages'],'tools':base['tools'],'target_indices':selected,
        'scope':'identical complete context; loss covers only the declared certified Assistant turns'}


def admit(candidate):
    from .behavior import admit as admit_target
    components=candidate['base']['components']
    for component in components:admit_target(component)
    expected=project(components,candidate['mode'])
    if candidate!=expected:raise ValueError('Ablation differs from certified trace or mask')
    return candidate


def encode(tokenizer,candidate,max_length):
    return encode_sequence(tokenizer,candidate,max_length)


def groups(paths):
    from .behavior import admit as admit_target
    traces=defaultdict(list)
    for path in paths:
        for line in Path(path).read_text().splitlines():
            if not line.strip():continue
            c=admit_target(json.loads(line));traces[(c['source_cluster_id'],c['raw_generation_and_tool_trace_ref'])].append(c)
    return list(traces.values())


def plan(learning_tokens,replay_tokens,budget,max_steps,tolerance):
    # Repetition is schedule metadata, never a new independent source or target.
    result={}
    for arm,tokens in [('output-only',learning_tokens['output-only']),('full',learning_tokens['full']),('full-replay',learning_tokens['full'])]:
        options=[]
        for main_passes in range(1,max_steps//len(tokens)+1):
            for replay_passes in (range(1,max_steps//len(replay_tokens)+1) if arm=='full-replay' else [0]):
                steps=main_passes*len(tokens)+replay_passes*len(replay_tokens)
                total=main_passes*sum(tokens)+replay_passes*sum(replay_tokens)
                if steps<=max_steps and total<=budget:
                    options.append((budget-total,steps,main_passes,replay_passes,total))
        if not options:raise ValueError(f'Budget cannot cover all sources in {arm}')
        _,steps,main_passes,replay_passes,total=min(options)
        if (budget-total)/budget>tolerance:raise ValueError(f'{arm} cannot match declared token tolerance using complete sequences')
        result[arm]={'main_passes':main_passes,'replay_passes':replay_passes,'optimizer_steps':steps,'supervised_tokens':total,
            'schedule':list(range(len(tokens)))*main_passes+list(range(len(tokens),len(tokens)+len(replay_tokens)))*replay_passes}
    return result


def build(learning,replay,tokenizer_path,out,config,budget,tolerance,max_steps,max_length):
    from transformers import AutoTokenizer
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
    tokenizer=AutoTokenizer.from_pretrained(tokenizer_path,local_files_only=True)
    learning_groups=groups(learning);replay_groups=groups(replay)
    if not learning_groups or not replay_groups:raise ValueError('Both pools are required')
    learning_sources={g[0]['source_cluster_id'] for g in learning_groups};replay_sources={g[0]['source_cluster_id'] for g in replay_groups}
    if learning_sources & replay_sources:raise ValueError('Replay must use distinct source clusters')
    pools={mode:[project(g,mode) for g in learning_groups] for mode in ('output-only','full')}
    replay_pool=[project(g,'full') for g in replay_groups]
    def preview(pool):
        result=[]
        for c in pool:
            admit(c);ids,labels=encode(tokenizer,c,max_length)
            result.append({'id':c['candidate_id'],'source':c['source_cluster_id'],'context_tokens':len(ids),'supervised_tokens':sum(x!=-100 for x in labels),'targets':len(c['target_indices'])})
        return result
    previews={mode:preview(pool) for mode,pool in pools.items()};replay_preview=preview(replay_pool)
    schedules=plan({k:[r['supervised_tokens'] for r in v] for k,v in previews.items()},[r['supervised_tokens'] for r in replay_preview],budget,max_steps,tolerance)
    manifest={'learning_sources':sorted(learning_sources),'replay_sources':sorted(replay_sources),'previews':previews,
        'replay_preview':replay_preview,'matched_schedules':schedules,'budget':budget,'tolerance':tolerance,
        'scope':'same-source mask comparison plus token-matched allocation; repetition/steps/context costs differ and must be reported',
        'training_executed':False,'H_used':False,'arms':{}}
    for arm in ('output-only','full','full-replay'):
        pool=pools['output-only' if arm=='output-only' else 'full']+(replay_pool if arm=='full-replay' else [])
        path=out/(arm+'.jsonl');path.write_text(''.join(json.dumps(c,ensure_ascii=False)+'\n' for c in pool))
        for design,schedule in [('same-exposure',list(range(len(pool)))),('token-matched',schedules[arm]['schedule'])]:
            c={**read_config(config),'training_schedule':schedule,'training_max_steps':max_steps,
                'training_token_cap':max(budget,sum((previews['output-only' if arm=='output-only' else 'full']+ (replay_preview if arm=='full-replay' else []))[i]['supervised_tokens'] for i in range(len(pool)))),
                'training_max_length':max_length,'study_id':'supervision-ablation','stream_id':design,'arm_id':arm}
            write_json(out/(arm+'-'+design+'.json'),c)
        manifest['arms'][arm]={'dataset':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    write_json(out/'plan.json',manifest)
    return manifest


def main():
    p=argparse.ArgumentParser();p.add_argument('--learning',nargs='+',required=True);p.add_argument('--replay',nargs='+',required=True)
    p.add_argument('--tokenizer',required=True);p.add_argument('--out',required=True);p.add_argument('--config',required=True)
    p.add_argument('--budget',type=int,required=True);p.add_argument('--tolerance',type=float,default=.03)
    p.add_argument('--max-steps',type=int,default=40);p.add_argument('--max-length',type=int,default=5120)
    a=p.parse_args();build(a.learning,a.replay,a.tokenizer,a.out,a.config,a.budget,a.tolerance,a.max_steps,a.max_length)

if __name__=='__main__':main()
