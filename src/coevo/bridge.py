"""Thin JSON command boundary for momo's real local training/evaluation."""
import argparse
import json
from pathlib import Path
from .train import train
from .evaluate import evaluate
from .state import State


def main():
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['train', 'evaluate', 'status'])
    p.add_argument('--request', required=True)
    args = p.parse_args()
    request = json.loads(Path(args.request).read_text())
    if args.action == 'train':
        result = train(request.get('config', 'configs/workstation.json'), request['dataset'],
                       request['adapter_out'], request.get('previous_adapter'), request.get('seed', 17), request.get('passes', 1))
    elif args.action == 'evaluate':
        result = evaluate(request.get('config', 'configs/workstation.json'), request['out'],
                          request.get('cycle', 0), request.get('split', 'G'), request.get('model'))
    else:
        result = {'accepted': State().accepted()}
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
