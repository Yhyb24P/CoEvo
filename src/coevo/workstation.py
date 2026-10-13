"""Sequential A qualification and B/C learning pilot on the workstation."""
import argparse
from pathlib import Path
from .runtime import read_config, write_json
from .rsi import Server, run as run_cycles
from .qualification import run as qualify


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--config', default='configs/workstation.json')
    p.add_argument('--out', default='artifacts/rsi-pilot')
    args = p.parse_args()
    c = read_config(args.config)
    root = Path(args.out).resolve()
    root.mkdir(parents=True, exist_ok=True)
    print('STAGE A: starting real model qualification', flush=True)
    server = Server(args.config, root/'stage-A-server.log')
    try:
        result = qualify(args.config)
        write_json(root/'stage-A-qualification.json',result)
        if not result['qualification_passed']:
            raise RuntimeError('128K model qualification did not pass; inspect actual results')
    finally:
        server.stop()
    print('STAGES B/C: real local learning and three consecutive cycles',flush=True)
    cycles_result=run_cycles(args.config,str(root),c['rsi_cycles'])
    write_json(root/'ABC-result.json',{'qualification':result,'cycles':cycles_result})
    print('A–C pilot completed; D is deferred',flush=True)


if __name__=='__main__':
    main()
