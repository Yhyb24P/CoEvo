"""Same causal objective, projecting only positions with verified targets."""


def selected_causal_loss(model,input_ids,labels):
    import torch
    from torch.nn import functional as F
    if labels.shape[0]!=1:raise ValueError('Current pilot uses one sequence per microbatch')
    positions=torch.nonzero(labels[0,1:]!=-100,as_tuple=False).flatten()
    if not positions.numel():raise ValueError('No supervised causal positions')
    output=model(input_ids=input_ids,attention_mask=torch.ones_like(input_ids),logits_to_keep=positions)
    return F.cross_entropy(output.logits[0].float(),labels[0,positions+1])
