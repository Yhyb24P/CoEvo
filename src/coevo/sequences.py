"""Compose individually verified Assistant targets into one faithful replay sequence."""
import json
from .everyday import digest


def compose(components):
    components=sorted(components,key=lambda c:len(c['prefix']))
    if not components:raise ValueError('No verified replay targets')
    first=components[0]
    if any(c['source_cluster_id']!=first['source_cluster_id'] or c['raw_generation_and_tool_trace_ref']!=first['raw_generation_and_tool_trace_ref'] or c['tools']!=first['tools'] for c in components):
        raise ValueError('A sequence must keep one source, trace and tool schema')
    messages=json.loads(json.dumps(components[-1]['prefix']+[components[-1]['target']]))
    indices=[len(c['prefix']) for c in components]
    if len(set(indices))!=len(indices):raise ValueError('Duplicate supervised turn')
    for c,index in zip(components,indices):messages[index]=c['target']
    return {'candidate_format':'verified_behavior_sequence_v1','candidate_id':first['source_cluster_id']+'-sequence',
        'source_cluster_id':first['source_cluster_id'],'split':'L','train_authorized':True,
        'actor':'student','origin_kind':'W0-self-replay','behavior_kind':'read-output-stop-replay',
        'messages':messages,'tools':first['tools'],'target_indices':indices,'components':components,
        'derivation':'canonical verified Assistant targets; original tool observations and unverified context retained'}


def admit(candidate):
    from .train import admit as admit_target
    if candidate.get('split')!='L' or candidate.get('train_authorized') is not True or candidate.get('actor')!='student':
        raise ValueError('No authorized student replay sequence')
    components=candidate['components']
    for component in components:
        if component.get('candidate_format')!='verified_behavior_v1':
            raise ValueError('Replay sequence requires target-level student certificates')
        admit_target(component)
    expected=compose(components)
    for key in ('source_cluster_id','messages','tools','target_indices'):
        if digest(candidate[key])!=digest(expected[key]):raise ValueError('Replay sequence differs from verified targets')
    if not {'read','write','stop'}<= {c['behavior_kind'] for c in components}:
        raise ValueError('Replay sequence lacks read, correct output or stopping targets')
    return candidate


def encode(tokenizer,candidate,max_length):
    from .train import normalize_messages
    from .assistant_mask import encode as encode_canonical
    messages=normalize_messages(candidate['messages'])
    return encode_canonical(tokenizer,messages,candidate['tools'],candidate['target_indices'],max_length)
