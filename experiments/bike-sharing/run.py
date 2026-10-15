"""Own one model service and execute an explicitly prepared complete task."""
import argparse
import json
import time
from pathlib import Path
from coevo.complete_work import run
from coevo.rsi import Server
from coevo.runtime import write_json

if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True)
    p.add_argument('--config',default='configs/complete-work-qwen.json');a=p.parse_args()
    out=Path(a.out).resolve()
    if (out/'manifest.json').exists():
        raise ValueError('Run evidence exists; use a fresh preparation')
    server=None
    try:
        start=time.monotonic();server=Server(a.config,out/'server.log')
        write_json(out/'service.json',{'server_ready_seconds':time.monotonic()-start})
        result=run(out)
        print(json.dumps(result),flush=True)
    finally:
        if server:server.stop()
