"""Collect a new L batch from actual tool execution and result checking."""
import argparse
import json
from pathlib import Path
from .runtime import read_config, write_json
from .tasks import make_task, execute_task, candidate_from_run
from .state import State


def collect(config, out, cycle, model=None, count=6):
    c = read_config(config)
    root = Path(out).resolve()
    root.mkdir(parents=True, exist_ok=True)
    candidates, tasks = [], []
    state = State()
    for n in range(count):
        task = make_task(root / f"task-{n}" / "workspace", cycle, n, "L")
        runpath = root / f"task-{n}"
        write_json(runpath / "task.json", task)
        task_output = Path(task["workspace"]) / "output.json"
        task_output.unlink(missing_ok=True)
        verdict = execute_task(task, runpath, c, model, state.experience_context())
        tasks.append({"episode_id": task["episode_id"], **verdict})
        admitted = candidate_from_run(task, runpath)
        for x in admitted:
            state.add_experience(x)
        candidates.extend(admitted)
    (root / "candidates.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False)+"\n" for x in candidates))
    summary = {"cycle": cycle, "tasks": tasks, "candidate_count": len(candidates), "dataset": str(root / "candidates.jsonl")}
    write_json(root / "summary.json", summary)
    return summary


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="configs/workstation.json")
    p.add_argument("--out", required=True)
    p.add_argument("--cycle", type=int, required=True)
    p.add_argument("--model")
    args = p.parse_args()
    print(json.dumps(collect(args.config, args.out, args.cycle, args.model)), flush=True)


if __name__ == "__main__":
    main()
