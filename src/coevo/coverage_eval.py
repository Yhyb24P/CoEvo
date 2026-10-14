"""Disk-loaded candidate G retention and exposed D development panel."""
import argparse
import time
from pathlib import Path
from .runtime import read_config,write_json,source_snapshot
from .rsi import Server
from .evaluate import evaluate
from .panel import prepare,cases
from .everyday import execute_task


def run(config,out,adapter):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False);c=read_config(config)
    tasks={n:prepare(out/'D'/n,n) for n in cases()}
    write_json(out/'manifest.json',{'config':c,'adapter':adapter,'source_snapshot':source_snapshot(),
        'status':'running','start_time':time.time(),'scope':'G retention and already exposed D; no H or promotion'})
    server=None
    try:
        server=Server(config,out/'server.log',adapter)
        old=evaluate(config,out/'G',0,'G','coevo-current')
        results=[{'case':n,**execute_task(t,out/'D'/n,c,'coevo-current')} for n,t in tasks.items()]
        summary={'G':old,'D':results,'D_passed':sum(r['passed'] for r in results),'D_total':len(results),
            'candidate_promoted':False,'H_used':False,'D_inference_sampling':c.get('inference_sampling'),
            'G_inference_sampling':None,
            'scope':'development; new learning sources share operation families with exposed D; no structural novelty claim'}
        write_json(out/'summary.json',summary)
    finally:
        if server:server.stop()
        import json
        m=json.loads((out/'manifest.json').read_text());write_json(out/'manifest.json',{**m,
            'status':'completed' if (out/'summary.json').exists() else 'failed','end_time':time.time()})


def main():
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--out',required=True);p.add_argument('--adapter',required=True)
    a=p.parse_args();run(a.config,a.out,a.adapter)

if __name__=='__main__':main()
