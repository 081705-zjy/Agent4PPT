from __future__ import annotations

import contextlib
import datetime as dt
import json
import re
import threading
from pathlib import Path

try:
    import fcntl  # POSIX only; degrades to thread-only locking elsewhere
except ImportError:  # pragma: no cover - non-POSIX fallback
    fcntl = None  # type: ignore[assignment]


ROOT = Path(__file__).resolve().parents[1]
PROJECTS_DIR = ROOT / "projects"


class _PathLock:
    """Per-path reentrant lock: an RLock serializes threads in this process; an
    fcntl flock on the outermost acquisition adds cross-process exclusion."""

    __slots__ = ("rlock", "depth")

    def __init__(self) -> None:
        self.rlock = threading.RLock()
        self.depth = 0


_LOCKS_GUARD = threading.Lock()
_PATH_LOCKS: dict[str, _PathLock] = {}


def _path_lock(path: Path) -> _PathLock:
    key = str(path)
    with _LOCKS_GUARD:
        lock = _PATH_LOCKS.get(key)
        if lock is None:
            lock = _PathLock()
            _PATH_LOCKS[key] = lock
        return lock


@contextlib.contextmanager
def file_lock(path: Path):
    """Hold an exclusive lock for read-modify-write on ``path``. Reentrant within a
    thread; the RLock guarantees only one thread reaches the fcntl section at a time."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    holder = _path_lock(path)
    holder.rlock.acquire()
    outermost = holder.depth == 0
    holder.depth += 1
    fh = None
    try:
        if outermost and fcntl is not None:
            try:
                fh = open(path.with_name(f".{path.name}.lock"), "w")
                fcntl.flock(fh, fcntl.LOCK_EX)
            except OSError:
                if fh is not None:
                    fh.close()
                fh = None
        yield
    finally:
        if fh is not None:
            try:
                fcntl.flock(fh, fcntl.LOCK_UN)
            except OSError:
                pass
            fh.close()
        holder.depth -= 1
        holder.rlock.release()


def update_json(path: Path, mutator, default=None):
    """Locked read-modify-write: read JSON (or ``default``), apply ``mutator`` which
    returns the new value, then atomically write it. Returns the written value."""
    with file_lock(path):
        data = read_json(path, {} if default is None else default)
        data = mutator(data)
        write_json(path, data)
        return data


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def slug(text: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", text.strip()).strip("-").lower()
    return s[:48] or "deck"


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def project_dir(project_id: str) -> Path:
    return PROJECTS_DIR / project_id
