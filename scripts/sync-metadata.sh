#!/usr/bin/env bash
# sync-metadata.sh — write <project>/run-manifest.json for reuse-first V2 projects.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"

if [[ $# -lt 1 || "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    echo "Usage: sync-metadata.sh <project-dir>" >&2
    exit 1
fi

PROJECT_DIR="$1"
if [[ ! -d "$PROJECT_DIR" ]]; then
    log_error "project dir not found: $PROJECT_DIR"
    exit 1
fi

python3 - "$PROJECT_DIR" <<'PY'
from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

project = Path(sys.argv[1])

def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default

def fm(path: Path, key: str) -> str:
    if not path.exists():
        return ""
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.startswith(f"{key}:"):
            return line.split(":", 1)[1].strip().strip('"')
    return ""

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

state = read_json(project / "app-state.json", {})
answers = state.get("answers") if isinstance(state, dict) else {}
answers = answers if isinstance(answers, dict) else {}
plan = read_json(project / "model-routed-plan.json", {})
slides = plan.get("slides") if isinstance(plan, dict) else []
slide_count = len(slides) if isinstance(slides, list) and slides else 0
if not slide_count:
    manuscript = project / "manuscript.md"
    if manuscript.exists():
        slide_count = len(re.findall(r"^##\s+Slide\s+\d+:", manuscript.read_text(encoding="utf-8", errors="ignore"), flags=re.MULTILINE))
if not slide_count:
    try:
        slide_count = int(answers.get("slide_count") or 0)
    except (TypeError, ValueError):
        slide_count = 0

source_urls: list[str] = []
citations = read_json(project / "citations.json", {})
for item in (citations.get("citations") if isinstance(citations, dict) else []) or []:
    if isinstance(item, dict):
        url = str(item.get("url") or item.get("source_url") or "").strip()
        if url.startswith(("http://", "https://")) and url not in source_urls:
            source_urls.append(url)
research = project / "research.md"
if research.exists():
    for url in re.findall(r"https?://[^ )\]\n]+", research.read_text(encoding="utf-8", errors="ignore")):
        if url not in source_urls:
            source_urls.append(url)

artifact_names = [
    "question-state.json",
    "project-outline-input.json",
    "resource-index.json",
    "source-digest.json",
    "asset-catalog.json",
    "visual-reference-index.json",
    "template-library-candidates.json",
    "task-analysis.json",
    "material-selection.json",
    "reuse-first-outline.json",
    "story-strategy.md",
    "draft-assembly-plan.json",
    "draft-manuscript.md",
    "draft-visual-plan.json",
    "draft-deck.pptx",
    "slide-gap-plan.json",
    "gap-research-results.json",
    "citations.json",
    "research.md",
    "slide-composition.json",
    "manuscript.md",
    "visual-plan.json",
    "style-unification-plan.json",
    "template-binding.json",
    "style-profile.json",
    "deck.pptx",
    "render-log.md",
    "structural-validation.md",
    "render-audit.json",
    "review-report.json",
    "final-report.json",
]
artifacts = []
for name in artifact_names:
    path = project / name
    if path.exists() and path.is_file():
        artifacts.append({"path": name, "sha256": sha256(path), "size_bytes": path.stat().st_size})

manifest = {
    "schema_version": "2.0",
    "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "source": "reuse_first_v2_app",
    "project_id": project.name,
    "topic": answers.get("topic") or state.get("topic") or project.name,
    "audience": answers.get("audience"),
    "scenario": answers.get("scenario"),
    "duration_minutes": answers.get("duration_minutes"),
    "slide_count": slide_count,
    "backend": fm(project / "structural-validation.md", "backend") or fm(project / "render-log.md", "backend"),
    "render_mode": fm(project / "structural-validation.md", "render_mode"),
    "deck_quality_pass": fm(project / "structural-validation.md", "deck_quality_pass"),
    "source_urls": source_urls,
    "output_paths": [item["path"] for item in artifacts if item["path"] in {"deck.pptx", "research.md", "citations.json", "render-audit.json", "final-report.json"}],
    "artifacts": artifacts,
    "quality": {
        "aggregate_editable_ratio": fm(project / "structural-validation.md", "aggregate_editable_ratio"),
        "assets_ok": fm(project / "structural-validation.md", "assets_ok"),
        "speaker_notes_ok": fm(project / "structural-validation.md", "speaker_notes_ok"),
        "transitions_ok": fm(project / "structural-validation.md", "transitions_ok"),
    },
}
(project / "run-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

log_info "sync-metadata: wrote run-manifest.json"
