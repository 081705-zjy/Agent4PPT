from __future__ import annotations

import json
from pathlib import Path

from .models import now, project_dir


def append(project_id: str, event: dict) -> dict:
    record = {"ts": now(), **event}
    path = project_dir(project_id) / "route-log.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def read(project_id: str, limit: int = 200) -> list[dict]:
    path = project_dir(project_id) / "route-log.jsonl"
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()[-limit:]
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out
