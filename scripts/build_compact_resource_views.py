#!/usr/bin/env python3
"""Validate physically compacted resource-library views.

The active libraries are compacted in place:
- rule/logic_story/INDEX.json is the prompt-facing rule source.
- logic/INDEX.json is the prompt-facing logic source; former meta patterns live
  in logic/deck_level as pattern_kind=deck_task.

This script intentionally does not create COMPACT_INDEX.json or
UNIFIED_INDEX.json sidecar files.
"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESOURCE_ROOT = ROOT / "data" / "resources_library"
LOGIC_ROOT = RESOURCE_ROOT / "logic"
RULE_LOGIC_STORY_ROOT = RESOURCE_ROOT / "rule" / "logic_story"


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Invalid JSON: {path}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"JSON root must be object: {path}")
    return data


def _validate_index(root: Path, index_name: str) -> Path:
    index_path = root / index_name
    idx = _read_json(index_path)
    entries = idx.get("entries")
    if not isinstance(entries, list):
        raise RuntimeError(f"{index_path} missing entries[]")
    missing: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            missing.append(str(entry))
            continue
        rel = entry.get("path")
        if not rel or not (root / rel).exists():
            missing.append(str(rel or entry.get("id") or entry))
    if missing:
        raise RuntimeError(f"{index_path} references missing files: {missing[:10]}")
    return index_path


def validate_logic_story_physical_compact() -> Path:
    return _validate_index(RULE_LOGIC_STORY_ROOT, "INDEX.json")


def validate_logic_physical_compact() -> Path:
    index_path = _validate_index(LOGIC_ROOT, "INDEX.json")
    idx = _read_json(index_path)
    by_layer = idx.get("by_layer") or {}
    if "meta" in by_layer:
        raise RuntimeError("logic/INDEX.json still exposes legacy meta layer")
    if not (LOGIC_ROOT / "deck_level").exists():
        raise RuntimeError("logic/deck_level missing")
    if not (LOGIC_ROOT / "section_level").exists():
        raise RuntimeError("logic/section_level missing")
    if (LOGIC_ROOT / "meta").exists():
        raise RuntimeError("logic/meta should be physically merged into deck_level")
    for sidecar in (
        LOGIC_ROOT / "deck_level" / "UNIFIED_INDEX.json",
        RULE_LOGIC_STORY_ROOT / "COMPACT_INDEX.json",
    ):
        if sidecar.exists():
            raise RuntimeError(f"sidecar compact file should not exist: {sidecar}")
    return index_path


def main() -> None:
    for path in (validate_logic_story_physical_compact(), validate_logic_physical_compact()):
        print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
