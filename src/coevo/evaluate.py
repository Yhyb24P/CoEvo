"""Real task evaluation through momo's local SDK integration."""
import argparse
import json
from pathlib import Path
from .tasks import make_task, execute_task
from .runtime import read_config, write_json


def evaluate(config, out, cycle, split="G", model=None, count=3, experience=""):
    c = read_config(config)
    root = Path(out).resolve()
    root.mkdir(parents=True, exist_ok=True)
    results = []
    for n in range(count):
        task = make_task(root / f"task-{n}" / "workspace", cycle, n, split)
        # Paired reruns always start without a previous model's output artifact.
        output = Path(task["workspace"]) / "output.json"
        output.unlink(missing_ok=True)
        write_json(root / f"task-{n}" / "task.json", task)
        try:
            verdict = execute_task(task, root / f"task-{n}", c, model, experience)
        except Exception as exc:
            verdict = {"passed": False, "failure_class": type(exc).__name__, "error": str(exc)}
            write_json(root / f"task-{n}" / "verdict.json", verdict)
        results.append({"episode_id": task["episode_id"], "source_cluster_id": task["source_cluster_id"], **verdict})
    summary = {"split": split, "cycle": cycle, "model": model or c["served_model"],
               "passed": sum(x["passed"] for x in results), "total": len(results), "tasks": results,
               "scope": "file-transform pilot; instance transfer; adaptive G feedback; no H confirmation"}
    write_json(root / "summary.json", summary)
    return summary


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="configs/workstation.json")
    p.add_argument("--out", required=True)
    p.add_argument("--cycle", type=int, default=0)
    p.add_argument("--model")
    p.add_argument("--split", choices=["D", "G"], default="G")
    args = p.parse_args()
    print(json.dumps(evaluate(args.config, args.out, args.cycle, args.split, args.model)), flush=True)


if __name__ == "__main__":
    main()
