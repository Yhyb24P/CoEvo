"""Thin JSON command boundary for momo's real local training/evaluation."""
import argparse
import json
from pathlib import Path
from .evaluate import evaluate
from .runtime import read_config
from .state import State


def main():
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['prepare-training', 'evaluate', 'status'])
    p.add_argument('--request', required=True)
    args = p.parse_args()
    request = json.loads(Path(args.request).read_text())
    if args.action == 'prepare-training':
        result = {**request, 'training_control': 'user initiated only', 'training_executed': False}
    elif args.action == 'evaluate':
        result = evaluate(request.get('config', 'configs/workstation.json'), request['out'],
                          request.get('cycle', 0), request.get('split', 'G'), request.get('model'))
    else:
        state = State.for_experiment(read_config(request.get('config', 'configs/workstation.json')))
        try:
            result = {'accepted': state.accepted(), **state.manifest()}
        finally:
            state.close()
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
