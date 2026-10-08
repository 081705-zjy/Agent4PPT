"""Project-internal deck library builder (Phase C.2 + D.1 + P16c).

For each .pptx the user uploaded to `projects/<id>/sources/`, run the same
4-skill brief pipeline used by the global library and write the result to
`projects/<id>/data/ppt/<deck-stem>/`. The LAYERED_RETRIEVAL stage then
merges these project-internal candidates with the global library so the
matching cascade considers BOTH pools.

Public API:
  - `build_project_library(project_id, *, force=False, concurrency=4)`
  - `_project_imports_dir(project_id)`  (data/.imports/)
  - `_project_decks_dir(project_id)`    (data/ppt/)
  - `_project_analysis_dir(project_id, file_type)`  (data/<type>/)
  - `scan_sources_inventory(project_id)`
  - `prune_sources(project_id)`
"""
from __future__ import annotations
import hashlib
import json
import sys
from pathlib import Path

from .models import ROOT


def _project_root(project_id: str) -> Path:
    return ROOT / "projects" / project_id


def _project_sources_dir(project_id: str) -> Path:
    return _project_root(project_id) / "sources"


# Phase P16c: per-project analysis output lives under `data/` (separated from
# user originals under `sources/`). Originals stay at `sources/<file>`;
# analysis lands at `data/<type>/<stem>.json` and pptx briefs at
# `data/ppt/<deck-stem>/{deck.json, sections/, slides/}`.
def _project_data_dir(project_id: str) -> Path:
    return _project_root(project_id) / "data"


def _project_decks_dir(project_id: str) -> Path:
    """Brief tree for project PPTX. Mirrors `data/resources_library/material/decks/`."""
    return _project_data_dir(project_id) / "ppt"


def _project_imports_dir(project_id: str) -> Path:
    """Hidden ppt-master importer workspace for project PPTX."""
    return _project_data_dir(project_id) / ".imports"


def _project_decks_index(project_id: str) -> Path:
    return _project_data_dir(project_id) / "ppt" / "decks-index.json"


def _project_analysis_dir(project_id: str, file_type: str) -> Path:
    """Per-type analysis output dir under data/. file_type ∈ {pdf,excel,image,doc}.
    Each file's analysis is written as `data/<type>/<stem>.json`."""
    return _project_data_dir(project_id) / file_type


def _sha1_file(path: Path) -> str:
    h = hashlib.sha1()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_deck_id(pptx_path: Path) -> str:
    """Project-internal deck ids look like `proj.<file-stem>.<8hex>`."""
    short_sha = _sha1_file(pptx_path)[:12]
    stem = pptx_path.stem
    # Normalize stem similar to library_tree.safe_dirname (but inside id)
    import re
    safe = re.sub(r"\s+", "-", stem.strip())
    safe = re.sub(r"[<>:\"/\\|?*\x00-\x1f]", "-", safe)
    safe = re.sub(r"-{2,}", "-", safe).strip("-")
    return f"proj.{safe}.{short_sha}"


def _collect_project_pptx_inputs(project_id: str) -> list[dict]:
    """Find all project .pptx files; run importer where needed; return the
    list of deck inputs ready for `library_brief.generate_briefs_for_decks`."""
    from . import library_brief

    sources = _project_sources_dir(project_id)
    if not sources.exists():
        return []
    pptx_files = sorted([p for p in sources.iterdir() if p.suffix.lower() == ".pptx"])
    if not pptx_files:
        return []

    # ppt-master importer
    try:
        from scripts.lib import template_ingest
    except Exception as exc:  # noqa: BLE001
        print(f"[project_library] cannot import template_ingest: {exc}", file=sys.stderr)
        return []
    scripts_dir = template_ingest.vendored_scripts_dir(ROOT)
    if not scripts_dir or not scripts_dir.exists():
        scripts_dir = template_ingest.ppt_master_scripts_dir(ROOT)
    if not scripts_dir or not scripts_dir.exists():
        print(f"[project_library] no ppt-master scripts dir found", file=sys.stderr)
        return []

    imports_root = _project_imports_dir(project_id)
    imports_root.mkdir(parents=True, exist_ok=True)

    inputs: list[dict] = []
    for pptx in pptx_files:
        deck_id = _safe_deck_id(pptx)
        import_dir = imports_root / deck_id
        if not template_ingest.run_importer(pptx, import_dir, scripts_dir):
            print(f"[project_library] importer failed for {pptx.name}", file=sys.stderr)
            continue
        manifest_path = import_dir / "manifest.json"
        if not manifest_path.exists():
            print(f"[project_library] no manifest after import: {pptx.name}", file=sys.stderr)
            continue
        m = json.loads(manifest_path.read_text(encoding="utf-8"))
        slides = m.get("slides") or []
        src_raw = m.get("source")
        if isinstance(src_raw, dict):
            src_abs = src_raw.get("pptx") or str(pptx)
        else:
            src_abs = str(src_raw or pptx)
        try:
            source_pptx_rel = str(Path(src_abs).resolve().relative_to(ROOT))
        except (ValueError, OSError):
            source_pptx_rel = src_abs
        sld = m.get("slideSize") or {}
        if "cx" in sld:
            slide_size = [sld.get("cx"), sld.get("cy")]
        elif "width_emu" in sld:
            slide_size = [sld.get("width_emu"), sld.get("height_emu")]
        else:
            slide_size = None
        inputs.append({
            "deck_id": deck_id,
            "source_pptx": source_pptx_rel,
            "file_sha1": _sha1_file(pptx),
            "slide_size": slide_size,
            "slides_meta": slides,
        })
    return inputs


def _project_context_from_brief(project_id: str) -> dict | None:
    """Build the optional `项目上下文` dict that brief skills consume in
    project-side mode. Returns None if idea-analysis.json is missing."""
    brief_path = _project_root(project_id) / "idea-analysis.json"
    if not brief_path.exists():
        return None
    try:
        b = json.loads(brief_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    chapters = []
    es = b.get("expected_sections") or []
    if es and isinstance(es[0], dict):
        for s in es:
            chapters.append({
                "section_index": s.get("section_index"),
                "chapter": s.get("chapter") or s.get("章节名"),
                "purpose": s.get("purpose"),
            })
    else:
        arc = (b.get("narrative_blueprint") or {}).get("arc") or []
        for i, a in enumerate(arc):
            chapters.append({
                "section_index": i + 1,
                "chapter": a.get("chapter"),
                "purpose": a.get("purpose"),
            })
    if not (b.get("topic") or chapters):
        return None
    return {
        "项目主题": b.get("topic"),
        "项目主题标签": b.get("topic_tags") or b.get("anchor_terms") or [],
        "项目章节": chapters,
    }


def build_project_library(
    project_id: str,
    *,
    force: bool = False,
    concurrency: int | None = None,
) -> dict:
    """Build the per-project deck library by running the brief 4-skill
    pipeline on every .pptx in `projects/<id>/sources/`.

    Writes to `projects/<id>/data/ppt/<deck-stem>/`.
    `force=False` skips decks whose existing deck.json's `源哈希` matches the
    current source PPTX SHA1.
    """
    from . import library_brief, library_tree

    inputs = _collect_project_pptx_inputs(project_id)
    if not inputs:
        return {"ok": [], "failed": [], "skipped": [], "reason": "no project pptx found"}

    # Phase D: inject 项目上下文 so brief skills additionally tag each deck
    # with `本项目相关性评分` + `适合本项目章节`. Falls back to global mode
    # when idea-analysis.json doesn't exist yet.
    proj_ctx = _project_context_from_brief(project_id)
    if proj_ctx is None:
        print(f"[project_library] WARNING: no idea-analysis.json for {project_id}; "
              "running in global-library mode (no project relevance fields)",
              flush=True)
    for inp in inputs:
        inp["project_context"] = proj_ctx

    decks_dir = _project_decks_dir(project_id)
    decks_dir.mkdir(parents=True, exist_ok=True)

    # Skip-if-current pass
    to_run: list[dict] = []
    skipped: list[str] = []
    if not force:
        for inp in inputs:
            existing = list(decks_dir.glob("**/deck.json"))
            stale = True
            for ej in existing:
                try:
                    d = json.loads(ej.read_text(encoding="utf-8"))
                    if d.get("deck标识") == inp["deck_id"] and d.get("源哈希") == inp["file_sha1"]:
                        stale = False
                        skipped.append(inp["deck_id"])
                        break
                except json.JSONDecodeError:
                    pass
            if stale:
                to_run.append(inp)
    else:
        to_run = inputs

    if not to_run:
        return {"ok": [], "failed": [], "skipped": skipped, "reason": "all up to date"}

    summary = library_brief.generate_briefs_for_decks(
        to_run,
        decks_root=decks_dir,
        max_concurrency=concurrency or library_brief.DEFAULT_MAX_DECK_CONCURRENCY,
        write_tree=True,
    )
    # Re-emit decks-index.json from the project tree
    library_tree.write_decks_index(decks_dir)
    summary["skipped"] = skipped
    return summary


# --------------------------------------------------------------------------
# Phase C.1 + C.4: inventory + prune
# --------------------------------------------------------------------------

# Extension → analyzer routing
EXT_PPTX = {".pptx", ".ppt"}
EXT_PDF = {".pdf"}
EXT_EXCEL = {".xlsx", ".xls", ".csv"}
EXT_IMAGE = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg"}
EXT_DOC = {".txt", ".md", ".markdown", ".docx", ".rtf"}


def _classify_file(p: Path) -> str:
    """Return the analyzer category for a source file."""
    ext = p.suffix.lower()
    if ext in EXT_PPTX:  return "pptx"
    if ext in EXT_PDF:   return "pdf"
    if ext in EXT_EXCEL: return "excel"
    if ext in EXT_IMAGE: return "image"
    if ext in EXT_DOC:   return "doc"
    return "other"


def scan_sources_inventory(project_id: str) -> dict:
    """Walk projects/<id>/sources/, classify by extension, write
    `source-inventory.json`. Also surfaces existing discard_candidate flags
    from any previous analysis pass (source-relevance.json)."""
    sources = _project_sources_dir(project_id)
    if not sources.exists():
        return {"by_type": {}, "files": [], "total": 0,
                "reason": f"no sources dir: {sources}"}

    by_type: dict[str, list[dict]] = {}
    files: list[dict] = []
    for p in sorted(sources.rglob("*")):
        if not p.is_file():
            continue
        cat = _classify_file(p)
        try:
            rel = str(p.relative_to(_project_root(project_id)))
        except ValueError:
            rel = str(p)
        info = {
            "path": rel,
            "name": p.name,
            "type": cat,
            "size_bytes": p.stat().st_size,
            "ext": p.suffix.lower(),
        }
        by_type.setdefault(cat, []).append(info)
        files.append(info)

    # Carry over previous discard markers if present
    rel_path = _project_root(project_id) / "source-relevance.json"
    discard_set: set[str] = set()
    if rel_path.exists():
        try:
            rel_data = json.loads(rel_path.read_text(encoding="utf-8"))
            for item in rel_data.get("items") or []:
                if item.get("discard_candidate") and item.get("path"):
                    discard_set.add(item["path"])
        except json.JSONDecodeError:
            pass
    for f in files:
        f["discard_candidate"] = f["path"] in discard_set

    inventory = {
        "schema_version": "inventory-v1",
        "project_id": project_id,
        "sources_dir": str(sources),
        "total": len(files),
        "by_type": by_type,
        "files": files,
        "discard_candidates": [f["path"] for f in files if f.get("discard_candidate")],
    }
    out = _project_root(project_id) / "source-inventory.json"
    out.write_text(json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8")
    return inventory


def prune_sources(project_id: str, *, dry_run: bool = True) -> dict:
    """Delete (or list) files marked discard_candidate in source-relevance.json."""
    inv = scan_sources_inventory(project_id)
    discard = inv.get("discard_candidates") or []
    actions: list[dict] = []
    for rel_path in discard:
        full = _project_root(project_id) / rel_path
        if not full.exists():
            actions.append({"path": rel_path, "status": "missing"})
            continue
        if dry_run:
            actions.append({"path": rel_path, "status": "would_delete",
                            "size_bytes": full.stat().st_size})
        else:
            try:
                full.unlink()
                actions.append({"path": rel_path, "status": "deleted"})
            except OSError as exc:
                actions.append({"path": rel_path, "status": f"error: {exc}"})
    return {
        "project_id": project_id,
        "dry_run": dry_run,
        "total_discard": len(discard),
        "actions": actions,
    }


def _cli():
    """Usage: python3 -m ppt_agent_app.project_library <project_id> [--force] [-j N]"""
    import argparse
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    bld = sub.add_parser("build", help="build per-project PPTX brief tree")
    bld.add_argument("project_id")
    bld.add_argument("--force", action="store_true")
    bld.add_argument("-j", "--concurrency", type=int, default=None)

    inv = sub.add_parser("inventory", help="scan sources/ and classify")
    inv.add_argument("project_id")

    pru = sub.add_parser("prune", help="delete sources marked discard_candidate")
    pru.add_argument("project_id")
    pru.add_argument("--dry-run", action="store_true", default=True)
    pru.add_argument("--apply", dest="dry_run", action="store_false")

    args = p.parse_args()

    if args.cmd == "build":
        summary = build_project_library(args.project_id, force=args.force,
                                         concurrency=args.concurrency)
        out = {k: (v if not isinstance(v, list) or len(v) <= 8 else f"{len(v)} items")
               for k, v in summary.items()}
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    if args.cmd == "inventory":
        inv_data = scan_sources_inventory(args.project_id)
        print(json.dumps({
            "by_type": {k: len(v) for k, v in inv_data["by_type"].items()},
            "total": inv_data["total"],
            "discard_candidates": len(inv_data.get("discard_candidates") or []),
        }, ensure_ascii=False, indent=2))
        return

    if args.cmd == "prune":
        report = prune_sources(args.project_id, dry_run=args.dry_run)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return


if __name__ == "__main__":
    _cli()
