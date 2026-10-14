"""Post-hoc zero-delta LoRA loading control, distinct from a trained candidate."""
import argparse
import hashlib
import json
import time
from pathlib import Path
from .runtime import read_config,write_json,source_snapshot
from .rsi import Server
from .agent_learning_pilot import prepare
from .everyday import execute_task


def zero_delta(source,out):
    import torch
    from safetensors.torch import load_file,save_file
    source=Path(source).resolve();out=Path(out).resolve()
    config=json.loads((source/'adapter_config.json').read_text())
    if config.get('peft_type')!='LORA' or config.get('bias')!='none' or config.get('use_dora') or config.get('lora_bias') or config.get('modules_to_save'):
        raise ValueError('Control supports this study plain bias-free linear LoRA only')
    state=load_file(source/'adapter_model.safetensors',device='cpu')
    if not state or any(not (key.endswith('.lora_A.weight') or key.endswith('.lora_B.weight')) for key in state):
        raise ValueError('Unexpected saved parameters; zero B would not prove zero delta')
    before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [source/'adapter_config.json',source/'adapter_model.safetensors']}
    count=0
    for key,tensor in state.items():
        if not torch.isfinite(tensor).all():raise ValueError('Non-finite source adapter')
        if key.endswith('.lora_B.weight'):
            if key.replace('.lora_B.weight','.lora_A.weight') not in state:raise ValueError('Missing paired projection')
            state[key]=torch.zeros_like(tensor);count+=1
    if not count:raise ValueError('No B projections')
    out.mkdir(parents=True,exist_ok=False);write_json(out/'adapter_config.json',config)
    save_file(state,out/'adapter_model.safetensors',metadata={'format':'pt'})
    write_json(out/'zero-delta.json',{'control':'all linear LoRA B zero; delta B@A exactly zero for finite A',
        'zero_B_projections':count,'source_sha256':before,'control_sha256':hashlib.sha256((out/'adapter_model.safetensors').read_bytes()).hexdigest(),
        'optimizer_steps':0,'training_executed':False})


def run(config,source,panel,out):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False);c=read_config(config);rows=json.loads(Path(panel).read_text());server=None
    write_json(out/'manifest.json',{'status':'running','start_time':time.time(),'config':c,'source_snapshot':source_snapshot(),
        'scope':'post-hoc loading diagnosis; same exposed development panel, not preregistered primary Q3 arm',
        'panel_sha256':hashlib.sha256(Path(panel).read_bytes()).hexdigest(),'H_used':False,'promotion_allowed':False})
    try:
        zero_delta(source,out/'adapter');started=time.monotonic();server=Server(config,out/'server.log',str(out/'adapter'));results=[]
        for spec in rows:
            if time.monotonic()-started>2700:raise TimeoutError('Control wall cap')
            task=prepare(out/spec['name'],spec);v=execute_task(task,out/spec['name'],c,'coevo-current');results.append({'name':spec['name'],**v})
        write_json(out/'summary.json',{'rows':results,'D_passed':sum(r['passed'] for r in results if r['name'].startswith('D-')),
            'G_passed':sum(r['passed'] for r in results if r['name'].startswith('G-')),'wall_seconds':time.monotonic()-started})
        m=json.loads((out/'manifest.json').read_text());write_json(out/'manifest.json',{**m,'status':'completed','end_time':time.time()})
    except BaseException as exc:
        m=json.loads((out/'manifest.json').read_text());write_json(out/'manifest.json',{**m,'status':'failed','end_time':time.time(),'error':str(exc)});raise
    finally:
        if server:server.stop()


def main():
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--source',required=True);p.add_argument('--panel',required=True);p.add_argument('--out',required=True);a=p.parse_args();run(a.config,a.source,a.panel,a.out)


if __name__=='__main__':main()
