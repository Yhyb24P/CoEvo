"""Replay the saved rejection through pinned vLLM tokenization and validation.

Only the tokenizer/renderer is constructed, not a model execution engine. The
model registry below supplies the already-known served name, not learned weights.
"""
import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[2]


async def replay(run, out, model_path, sdk_root):
    from vllm.config import ModelConfig
    from vllm.renderers.hf import HfRenderer
    from vllm.renderers.online_renderer import OnlineRenderer
    from vllm.entrypoints.serve.tokenize.protocol import TokenizeChatRequest
    from vllm.entrypoints.serve.tokenize.serving import ServingTokenization
    from vllm.entrypoints.openai.chat_completion.protocol import ChatCompletionRequest
    from vllm.tokenizers import get_tokenizer
    from vllm.exceptions import VLLMValidationError
    run,out,model_path,sdk_root=map(lambda p:Path(p).resolve(),(run,out,model_path,sdk_root))
    out.mkdir(parents=True,exist_ok=False)
    with (run/'payloads.jsonl').open() as handle:
        for line in handle:payload=json.loads(line)
    task_request=json.loads((run/'agent_request.json').read_text())
    capacity=task_request['context_tokens']
    mc=ModelConfig(model=str(model_path),tokenizer=str(model_path),dtype='bfloat16',
                   max_model_len=capacity,language_model_only=True)
    config=SimpleNamespace(model_config=mc,parallel_config=SimpleNamespace(_api_process_rank=0))
    renderer=HfRenderer(config,get_tokenizer(str(model_path)))
    defaults={'enable_thinking':task_request['enable_thinking']}
    online=OnlineRenderer(mc,renderer,request_logger=None,chat_template=None,
                          chat_template_content_format='auto',default_chat_template_kwargs=defaults)
    models=SimpleNamespace(is_base_model=lambda n:n==payload['model'],lora_requests={})
    serving=ServingTokenization(models,online,chat_template=None,
                                chat_template_content_format='auto',default_chat_template_kwargs=defaults)
    body={k:payload[k] for k in ['model','messages','tools','chat_template_kwargs'] if k in payload}
    count=await serving.create_tokenize(TokenizeChatRequest(**body),None)
    helper_code="""
import {readFileSync} from 'node:fs'; import {pathToFileURL} from 'node:url';
const v=JSON.parse(readFileSync(0,'utf8'));
const {allocateContextOutput}=await import(pathToFileURL(v.helper));
const {estimateContextTokens}=await import(pathToFileURL(v.sdk+'/utils/estimate.js'));
const {clampMaxTokensToContext}=await import(pathToFileURL(v.sdk+'/api/simple-options.js'));
const messages=JSON.parse(readFileSync(v.trace,'utf8')).messages.slice(0,-1);
const result=allocateContextOutput(v.payload,v.counted,v.capacity);
console.log(JSON.stringify({budget:result.budget,estimate:estimateContextTokens(messages),
 sdk_output_ceiling:clampMaxTokensToContext({contextWindow:v.capacity,maxTokens:v.max}, {messages}, v.max)}));
"""
    arguments={'helper':str(ROOT/'scripts/pi-task-support.mjs'),'sdk':str(sdk_root),
               'trace':str(run/'transcript.json'),'payload':payload,'counted':{'count':count.count,'max_model_len':count.max_model_len},
               'capacity':capacity,'max':task_request['max_output_tokens']}
    result=json.loads(subprocess.check_output(['node','--input-type=module','-e',helper_code],
                    input=json.dumps(arguments),text=True,timeout=30))
    accepted={}
    for label,ceiling in [('original',payload['max_completion_tokens']),('bounded',result['budget']['allocated_output_tokens'])]:
        req=ChatCompletionRequest(**{**payload,'max_completion_tokens':ceiling})
        try:
            _,inputs=await online.preprocess_chat(req,req.messages,default_template=None,
                default_template_content_format='auto',default_template_kwargs=defaults,
                tool_dicts=[t.model_dump() for t in req.tools])
            accepted[label]={'accepted':True,'prompt_tokens':len(serving._extract_prompt_components(inputs[0]).token_ids)}
        except VLLMValidationError as error:
            accepted[label]={'accepted':False,'error':str(error)}
    assert not accepted['original']['accepted'] and accepted['bounded']['accepted']
    assert accepted['bounded']['prompt_tokens']==count.count
    assert result['sdk_output_ceiling']==payload['max_completion_tokens']
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    result.update(validation=accepted,server_tokenizer_count=count.count,
        vllm_version=importlib.metadata.version('vllm'),
        pi_ai_version=json.loads((sdk_root.parent/'package.json').read_text())['version'],
        tokenizer_sha256={name:sha(model_path/name) for name in
                          ['tokenizer.json','tokenizer_config.json','chat_template.jinja','config.json']
                          if (model_path/name).is_file()},
        original_prompt_lower_bound=capacity-payload['max_completion_tokens']+1,
        original_total_exact=count.count+payload['max_completion_tokens'],
        interpretation='vLLM early-stop error gives a lower bound, not an exact one-token overflow.',
        scope='CPU replay of actual vLLM tokenization/validation and JS allocation, not a repeated Agent task or task-success claim.',
        refs_sha256={n:sha(run/n) for n in ['payloads.jsonl','transcript.json','agent_request.json']})
    (out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--out',required=True)
    p.add_argument('--model',default='.cache/active-model/Qwen3.5-4B')
    p.add_argument('--sdk',default='.cache/pi-1.2/node_modules/@earendil-works/pi-ai/dist')
    a=p.parse_args();print(json.dumps(asyncio.run(replay(a.run,a.out,a.model,a.sdk)),ensure_ascii=False))
