"""Agent proposes learning decisions; external rules retain admission authority."""
import json
from .train import admit


def validate(proposal, packet, candidates, max_selected=4):
    required={'source_cluster_id','memory_kind','body','conditions','training_candidate_ids','reason'}
    if not isinstance(proposal,dict) or set(proposal)!=required:
        raise ValueError('Learning proposal must match the frozen schema')
    if proposal['source_cluster_id']!=packet['source_cluster_id']:
        raise ValueError('Proposal cannot change its source')
    if proposal['memory_kind'] not in ('none','instance','skill'):
        raise ValueError('Proposal is not an Instruction or permission change')
    if not isinstance(proposal['body'],str) or len(proposal['body'])>2000:
        raise ValueError('Experience body exceeds budget')
    if not isinstance(proposal['reason'],str) or len(proposal['reason'])>1000:
        raise ValueError('Decision reason exceeds budget')
    conditions=proposal['conditions']
    if not isinstance(conditions,dict) or any(k not in packet['context'] or type(v)!=type(packet['context'][k]) or v!=packet['context'][k] for k,v in conditions.items()):
        raise ValueError('Conditions must use observed source context')
    if proposal['memory_kind']=='none' and (proposal['body'] or conditions):
        raise ValueError('No-memory decision must not activate experience')
    if proposal['memory_kind']!='none' and not proposal['body'].strip():
        raise ValueError('Empty proposed experience')
    ids=proposal['training_candidate_ids']
    if not isinstance(ids,list) or any(not isinstance(x,str) for x in ids) or len(ids)>max_selected or len(set(ids))!=len(ids):
        raise ValueError('Invalid selection or exceeded frozen item budget')
    allowed={c['candidate_id']:c for c in candidates}
    selected=[]
    for identity in ids:
        if identity not in allowed or allowed[identity]['source_cluster_id']!=packet['source_cluster_id']:
            raise ValueError('Candidate is not in this authorized source pool')
        selected.append(admit(allowed[identity]))
    return {'proposal':proposal,'selected':selected,'status':'eligible-for-controlled-trial',
        'experience_truth_verified':False,'authority':'external frozen rules; agent proposal only',
        'source_cluster_id':packet['source_cluster_id']}


def packet(source,context,task,traces,candidates):
    return {'source_cluster_id':source,'context':context,'original_request':task['prompt'],
        'inputs':task['inputs'],'correct_output':task['expected'],
        'visible_interactions':traces,'candidates':[{'candidate_id':c['candidate_id'],
            'kind':c['behavior_kind'],'target':c['target'],'verified':True} for c in candidates],
        'scope':'controlled L source; observations and corrections, not new authority'}
