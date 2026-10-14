"""Track canonical Qwen Assistant spans without rerendering partial histories."""


def instrument_qwen(template):
    current="{{- '<|im_start|>' + message.role + '\\n<think>\\n' + reasoning_content + '\\n</think>\\n\\n' + content }}"
    historical="{{- '<|im_start|>' + message.role + '\\n' + content }}"
    end="{{- '<|im_end|>\\n' }}\n    {%- elif message.role == \"tool\" %}"
    if template.count(current)!=1 or template.count(historical)!=1 or template.count(end)!=1:
        raise ValueError('Unsupported Assistant template; do not guess training boundaries')
    template=template.replace(current,current.replace(' + content','')).replace(historical,historical.replace(' + content',''))
    # One generation region per Assistant message; prefilled headers/thinking
    # stay outside the region. The rendered text must remain byte-for-byte equal.
    anchor="        {%- if message.tool_calls and message.tool_calls is iterable and message.tool_calls is not mapping %}"
    if template.count(anchor)!=1:raise ValueError('Assistant tool-call branch is ambiguous')
    template=template.replace(anchor,"        {%- generation %}{{- content }}\n"+anchor)
    return template.replace(end,"{{- '<|im_end|>\\n' }}{%- endgeneration %}\n    {%- elif message.role == \"tool\" %}")


def encode(tokenizer,messages,tools,target_indices,max_length):
    template=tokenizer.get_chat_template(tools=tools)
    tracked=instrument_qwen(template)
    kwargs={'tools':tools,'add_generation_prompt':False,'enable_thinking':False}
    canonical=tokenizer.apply_chat_template(messages,tokenize=True,return_dict=False,**kwargs)
    result=tokenizer.apply_chat_template(messages,chat_template=tracked,tokenize=True,return_dict=True,
        return_assistant_tokens_mask=True,**kwargs)
    if result['input_ids']!=canonical:raise ValueError('Mask instrumentation changed canonical native template')
    if len(canonical)>max_length:raise ValueError('Replay sequence exceeds length; no silent truncation')
    runs=[];start=None
    for i,bit in enumerate([*result['assistant_masks'],0]):
        if bit and start is None:start=i
        elif not bit and start is not None:runs.append((start,i));start=None
    assistants=[i for i,m in enumerate(messages) if m['role']=='assistant']
    if len(runs)!=len(assistants):raise ValueError('Assistant span count does not match actual messages')
    spans=dict(zip(assistants,runs));labels=[-100]*len(canonical)
    for index in target_indices:
        if index not in spans:raise ValueError('Only actual Assistant spans can be supervised')
        left,right=spans[index];labels[left:right]=canonical[left:right]
    if not any(x!=-100 for x in labels):raise ValueError('No Assistant supervision')
    return canonical,labels
