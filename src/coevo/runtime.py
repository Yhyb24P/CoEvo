"""Local HTTP and run records shared by qualification and learning."""
import hashlib
import json
import subprocess
import time
import urllib.request
from pathlib import Path


def read_config(path="configs/workstation.json"):
    return json.loads(Path(path).read_text())


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def request_json(url, payload=None, timeout=900):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    # Local serving must not depend on the user's external proxy or credentials.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=timeout) as response:
        return json.load(response)


def source_snapshot():
    return {
        str(p): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in [Path("pyproject.toml"), Path("uv.lock"), *Path("src/coevo").glob("*.py")]
        if p.is_file()
    }


def new_run(stage, config):
    run_id = f"{stage}-{time.strftime('%Y%m%dT%H%M%S')}-{time.time_ns() % 1000000:06d}"
    path = Path("runs") / run_id
    path.mkdir(parents=True)
    write_json(path / "manifest.json", {
        "run_id": run_id, "study_id": config.get('study_id', "workstation-rsi"), "arm": stage,
        "stream_id": config.get('stream_id'), "arm_id": config.get('arm_id'),
        "run_status": "running", "start_time": time.time(),
        "protocol_revision": config["protocol_revision"], "effective_config": config,
        "source_snapshot_ref_and_hash": source_snapshot(),
        "environment_and_hardware_ref": subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"],
            capture_output=True, text=True, check=True).stdout.strip(),
        "model_and_tokenizer_revision": json.loads(
            (Path(config["model_path"]) / "coevo_source.json").read_text()),
    })
    return path


def finish_run(path, status, result):
    manifest = json.loads((path / "manifest.json").read_text())
    manifest.update(run_status=status, end_time=time.time(), evaluation_result_ref=str(path / "result.json"))
    write_json(path / "result.json", result)
    write_json(path / "manifest.json", manifest)
