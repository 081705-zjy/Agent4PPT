"""Record per-stage wall-clock timings for eval scoring.

Idempotently monkey-patches `stage_runner._execute_stage` so every stage call
appends one line to `projects/<id>/stage-timings.jsonl`.

Import once at module load — no runtime API needed.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from ..models import project_dir


_PATCHED = False


def _append(project_id: str, event: dict) -> None:
    try:
        path = project_dir(project_id) / "stage-timings.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except OSError:
        pass  # never break a stage over a log write


def install() -> None:
    """Patch stage_runner._execute_stage exactly once."""
    global _PATCHED
    if _PATCHED:
        return

    from . import __init__  # noqa: F401  (ensure package imports before stage_runner)
    from .. import stage_runner

    original = stage_runner._execute_stage

    def _timed(project_id: str, stage: str, payload: dict) -> dict:
        start_perf = time.perf_counter()
        start_iso = datetime.now(timezone.utc).isoformat()
        try:
            result = original(project_id, stage, payload)
            ok = bool(result.get("ok"))
            error = None if ok else str(result.get("error") or "")[:200]
            return result
        except Exception as exc:  # noqa: BLE001
            ok = False
            error = f"{type(exc).__name__}: {exc}"[:200]
            raise
        finally:
            end_perf = time.perf_counter()
            duration = end_perf - start_perf
            _append(project_id, {
                "stage": stage.upper() if isinstance(stage, str) else str(stage),
                "start_ts": start_iso,
                "end_ts": datetime.now(timezone.utc).isoformat(),
                "duration_s": round(duration, 3),
                "ok": ok,
                "error": error,
            })

    stage_runner._execute_stage = _timed  # type: ignore[assignment]
    _PATCHED = True
