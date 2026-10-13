"""Offline task execution exposing only a disposable workspace and task environment."""
import argparse
import json
import os
import signal
import subprocess
import time
from pathlib import Path


def command(workspace, environment, argv, readonly=False):
    workspace, environment = Path(workspace).resolve(), Path(environment).resolve()
    if not workspace.is_dir() or not (environment / "bin/python").is_file():
        raise ValueError("Task workspace or Python environment does not exist")
    args = ["bwrap", "--unshare-all", "--die-with-parent", "--new-session",
            "--cap-drop", "ALL", "--clearenv"]
    for directory in ["/usr", "/lib", "/lib64", "/bin"]:
        if Path(directory).exists():
            args += ["--ro-bind", directory, directory]
    args += ["--ro-bind", str(environment), "/opt/task-env",
             "--ro-bind" if readonly else "--bind", str(workspace), "/workspace",
             "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
             "--setenv", "PATH", "/opt/task-env/bin:/usr/bin:/bin",
             "--setenv", "PYTHONPATH", "/workspace",
             "--setenv", "PYTHONDONTWRITEBYTECODE", "1",
             "--setenv", "PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1",
             "--setenv", "LANG", "C.UTF-8", "--chdir", "/workspace", "--", *argv]
    return args


def execute(workspace, environment, argv, log, timeout=120, readonly=False):
    if not 0 < timeout <= 300:
        raise ValueError("Task command timeout must be between 0 and 300 seconds")
    log = Path(log)
    log.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with log.open("w") as output:
        child = subprocess.Popen(command(workspace, environment, argv, readonly),
                                 stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            code = child.wait(timeout=timeout)
            timed_out = False
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
            code = child.wait()
            timed_out = True
    return {"exit_code": code, "timed_out": timed_out,
            "wall_seconds": time.monotonic() - started, "log": str(log),
            "network": "isolated", "workspace_readonly": readonly}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--log", required=True)
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--readonly", action="store_true")
    parser.add_argument("argv", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    argv = args.argv[1:] if args.argv[:1] == ["--"] else args.argv
    if not argv:
        parser.error("A command is required after --")
    result = execute(args.workspace, args.environment, argv, args.log, args.timeout, args.readonly)
    print(json.dumps(result), flush=True)
    raise SystemExit(result["exit_code"] if not result["timed_out"] else 124)


if __name__ == "__main__":
    main()
