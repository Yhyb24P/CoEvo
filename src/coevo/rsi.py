"""Bounded three-cycle pilot; stability and scientific improvement stay separate."""
import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from .runtime import read_config, write_json, request_json
from .collect import collect
from .evaluate import evaluate
from .state import State
from .tasks import make_task, execute_task


class Server:
    def __init__(self, config, output, adapter=None):
        self.config = read_config(config)
        self.log = open(output, "w")
        command = [sys.executable, "-m", "coevo.serve", "--config", config]
        if adapter:
            command.extend(["--adapter", adapter])
        self.process = subprocess.Popen(command, stdout=self.log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            started = time.monotonic()
            while time.monotonic() - started < 900:
                if self.process.poll() is not None:
                    raise RuntimeError(f"Inference server failed: inspect {output}")
                try:
                    request_json(self.config["endpoint"] + "/models", timeout=3)
                    return
                except Exception:
                    time.sleep(1)
            raise TimeoutError("Inference initialization exceeded 15 minutes")
        except Exception:
            self.stop()
            raise

    def stop(self):
        if self.process.poll() is None:
            os.killpg(self.process.pid, signal.SIGTERM)
            try:
                self.process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(timeout=10)
        self.log.close()


def resume_task(config, out, model):
    """Persist a task after read, reopen its real session and finish the original task."""
    c = read_config(config)
    root = Path(out).resolve()
    task = make_task(root / "workspace", 7, 1, "D")
    paused = {**task, "prompt": "Read input.json with the read tool. Do not write anything yet. Stop after reading and retain the task state."}
    execute_task(paused, root / "paused", c, model)
    transcript = json.loads((root / "paused/transcript.json").read_text())
    session_file = transcript["session_file"]
    if not session_file or not transcript["tool_calls"]:
        raise RuntimeError("No real persistent intermediate state was created")
    task["prompt"] = "Continue the previously read task: compute the sum of values and write output.json as JSON with exactly one key result."
    verdict = execute_task(task, root / "resumed", c, model, resume_file=session_file)
    write_json(root / "recovery.json", {"session_file": session_file, **verdict,
               "scope": "persistent paused-task recovery; does not claim recovery from power loss"})
    return verdict


def run(config, out, cycles=3):
    c = read_config(config)
    root = Path(out).resolve()
    root.mkdir(parents=True, exist_ok=True)
    state = State()
    server = None
    try:
        for cycle in range(1, cycles+1):
            saved = state.cycle(cycle)
            if saved and saved["phase"] == "finished":
                continue
            accepted = state.accepted()
            adapter = accepted["adapter"] if accepted else None
            model = "coevo-current" if adapter else c["served_model"]
            record = {"cycle": cycle, "parent": accepted, "scope": "single-seed file-task feasibility pilot; adaptive feedback, no H"} if saved is None else {k:v for k,v in saved.items() if k != "phase"}
            if saved is None or saved["phase"] == "collecting":
                state.save_cycle(cycle, "collecting", record)
                server = Server(config, root / f"cycle-{cycle}-collect-server.log", adapter)
                record["old_before"] = evaluate(config, root / f"cycle-{cycle}/old-before", 0, "G", model)
                record["new_before"] = evaluate(config, root / f"cycle-{cycle}/new-before", cycle+20, "G", model)
                record["collection"] = collect(config, root / f"cycle-{cycle}/learning", cycle, model)
                server.stop(); server = None
                state.save_cycle(cycle, "collected", record)
            if cycle == cycles:
                # Frozen operational exercise: withhold the last cycle's update budget.
                # New data and evaluation still occur; this is not an empirical training rejection.
                record["update_decision"] = "keep previous: predeclared last-cycle budget hold"
                server = Server(config, root / f"cycle-{cycle}-hold-server.log", adapter)
                record["old_after"] = evaluate(config, root / f"cycle-{cycle}/old-after", 0, "G", model)
                record["new_after"] = evaluate(config, root / f"cycle-{cycle}/new-after", cycle+20, "G", model)
                record["recovery"] = resume_task(config, root / f"cycle-{cycle}/recovery", model)
                server.stop(); server = None
            elif record["collection"]["candidate_count"] < 2:
                record["update_decision"] = "keep previous: insufficient verified candidates"
                record["old_after"] = record["old_before"]
                record["new_after"] = record["new_before"]
            else:
                candidate = str(root / f"cycle-{cycle}/adapter")
                if not (Path(candidate) / "coevo_training.json").is_file():
                    state.save_cycle(cycle, "training", record)
                    command = [sys.executable, "-m", "coevo.train", "--config", config,
                               "--dataset", record["collection"]["dataset"], "--adapter-out", candidate]
                    if adapter:
                        command.extend(["--previous-adapter", adapter])
                    with (root / f"cycle-{cycle}-train.log").open("w") as log:
                        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=7200)
                record["candidate_adapter"] = candidate
                state.save_cycle(cycle, "trained", record)
                # vLLM reloads the saved candidate; evaluation cannot reuse a trainer's in-memory model.
                server = Server(config, root / f"cycle-{cycle}-candidate-server.log", candidate)
                record["old_after"] = evaluate(config, root / f"cycle-{cycle}/old-after", 0, "G", "coevo-current")
                record["new_after"] = evaluate(config, root / f"cycle-{cycle}/new-after", cycle+20, "G", "coevo-current")
                server.stop(); server = None
                promote = (record["old_after"]["passed"] >= record["old_before"]["passed"] and
                           record["new_after"]["passed"] >= record["new_before"]["passed"])
                state.decide(f"cycle-{cycle}", candidate, accepted["version"] if accepted else None, promote, record)
                record["update_decision"] = "accept candidate" if promote else "keep previous: observed task regression"
            state.save_cycle(cycle, "finished", record)
            write_json(root / f"cycle-{cycle}/cycle.json", record)
            print(json.dumps({"cycle": cycle, "decision": record["update_decision"]}), flush=True)
        records = [state.cycle(i) for i in range(1, cycles+1)]
        process_completed = all(x["phase"] == "finished" for x in records)
        recovery_passed = any(x.get("recovery", {}).get("passed") is True for x in records)
        summaries = [x[k] for x in records for k in ["old_before", "new_before", "old_after", "new_after"] if k in x]
        runtime_failures = sum(1 for s in summaries for task in s["tasks"]
            if task.get("agent_exit_code", 0) != 0 or "failure_class" in task)
        training_records = [json.loads((Path(x["candidate_adapter"]) / "coevo_training.json").read_text())
            for x in records if x.get("candidate_adapter")]
        summary = {"cycles": records, "accepted_version": state.accepted(),
            "cycle_process_completed": process_completed, "task_recovery_passed": recovery_passed,
            "runtime_failures": runtime_failures,
            "real_parameter_updates": sum(x["parameters_before"] != x["parameters_after"] for x in training_records),
            "stability_completed": process_completed and recovery_passed and runtime_failures == 0,
            "ability_continually_improved": "not established by this single-seed adaptive pilot",
            "planned_hold": "last cycle has predeclared zero update budget; no fabricated regression",
            "protocol_revision": c["protocol_revision"]}
        write_json(root / "summary.json", summary)
        return summary
    finally:
        if server:
            server.stop()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="configs/workstation.json")
    p.add_argument("--out", default="artifacts/rsi-pilot")
    p.add_argument("--cycles", type=int, default=3)
    args = p.parse_args()
    if args.cycles < 3:
        raise SystemExit("Stable RSI pilot requires at least three consecutive cycles")
    run(args.config, args.out, args.cycles)


if __name__ == "__main__":
    main()
