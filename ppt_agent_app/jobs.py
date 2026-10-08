from __future__ import annotations

import threading
import traceback
from pathlib import Path

from .models import ROOT, now, project_dir, read_json, write_json


_LOCK = threading.Lock()
_JOBS: dict[str, dict] = {}


def _error_message(result: dict) -> str | None:
    if not isinstance(result, dict):
        return None
    for key in ("error", "message", "reason"):
        value = result.get(key)
        if value:
            return str(value)
    nested = result.get("result")
    if isinstance(nested, dict):
        return _error_message(nested)
    return None


def _job_path(record: dict) -> Path | None:
    project_id = record.get("project_id")
    if not project_id:
        return None
    return project_dir(str(project_id)) / "jobs" / f"{record['job_id']}.json"


def _persist(record: dict) -> None:
    path = _job_path(record)
    if path:
        write_json(path, record)


def _load_from_disk(job_id: str) -> dict:
    projects = ROOT / "projects"
    if not projects.exists():
        return {}
    for path in projects.glob(f"*/jobs/{job_id}.json"):
        data = read_json(path, {})
        if data.get("job_id") == job_id:
            return data
    return {}


def start(kind: str, target, *args, project_id: str | None = None, **kwargs) -> dict:
    job_id = f"{kind}-{now().replace(':', '').replace('-', '')}-{len(_JOBS) + 1}"
    inferred_project_id = project_id
    if inferred_project_id is None and args:
        first = args[0]
        if isinstance(first, str):
            inferred_project_id = first
    record = {
        "job_id": job_id,
        "kind": kind,
        "status": "running",
        "started_at": now(),
        "project_id": inferred_project_id,
    }
    with _LOCK:
        _JOBS[job_id] = record
        _persist(record)

    def run() -> None:
        try:
            result = target(*args, **kwargs)
            status = "failed" if isinstance(result, dict) and result.get("ok") is False else "succeeded"
            update = {"status": status, "finished_at": now(), "result": result}
            if status == "failed":
                update["error"] = _error_message(result) or "job returned ok=false"
            with _LOCK:
                _JOBS[job_id].update(update)
                _persist(_JOBS[job_id])
        except Exception as exc:  # noqa: BLE001
            with _LOCK:
                _JOBS[job_id].update({
                    "status": "failed",
                    "finished_at": now(),
                    "error": str(exc),
                    "traceback": traceback.format_exc()[-4000:],
                })
                _persist(_JOBS[job_id])

    thread = threading.Thread(target=run, name=job_id, daemon=True)
    thread.start()
    return record


def get(job_id: str) -> dict:
    with _LOCK:
        record = _JOBS.get(job_id)
        if record:
            disk = _load_from_disk(job_id)
            if disk and disk.get("status") != record.get("status"):
                _JOBS[job_id] = disk
                record = disk
            return dict(record)
    return _load_from_disk(job_id)


def update(job_id: str, fields: dict) -> dict:
    with _LOCK:
        record = _JOBS.get(job_id) or _load_from_disk(job_id)
        if not record:
            return {}
        record.update(fields)
        _JOBS[job_id] = record
        _persist(record)
        return dict(record)


def list_jobs() -> list[dict]:
    with _LOCK:
        jobs = {k: dict(v) for k, v in _JOBS.items()}
    projects = ROOT / "projects"
    if projects.exists():
        for path in projects.glob("*/jobs/*.json"):
            data = read_json(path, {})
            job_id = data.get("job_id")
            if job_id and job_id not in jobs:
                jobs[job_id] = data
    return list(jobs.values())
