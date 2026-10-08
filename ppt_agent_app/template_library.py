"""Template library shim (Phase B).

The old `template_library.py` produced 9 flat profile JSONs via heuristic
analysis. That whole stack has been replaced by:

  • `library_brief.py`  — generates per-deck/section/slide briefs using
    claude-opus-4-8 and writes the tree under `data/resources_library/material/decks/`
  • `library_query.py`  — reads that tree and emits English-keyed candidate
    dicts for the matching cascade

This module is now a THIN SHIM that:

  1. Preserves the public API surface that `stage_runner.py` and
     `services.py` import (MANIFEST, LIBRARY_DIR, SLIDE_PROFILES, ...,
     `build()`, `is_current()`, `load()`, `query_for_project()`).
  2. Delegates `build()` to `library_brief.generate_briefs_for_decks`.
  3. Delegates `query_for_project()` to `library_query.load_library_candidates`,
     writing a compat `template-library-candidates.json`.
  4. Returns benign empties from `load()` / `query()` so any legacy reader
     of `*-profiles.json` gets `[]` instead of crashing.

The 9 flat profile constants (DECK_PROFILES, …) point to file paths that no
longer exist on disk; reads via `read_json` will return `{}` (already the
graceful default). No active code path should be writing to those paths.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from .models import ROOT, now, project_dir, read_json, write_json


# --------------------------------------------------------------------------
# Paths — kept for backward import compatibility
# --------------------------------------------------------------------------

LIBRARY_DIR = ROOT / "data" / "resources_library" / "material"
MANIFEST = LIBRARY_DIR / "manifest.json"
DECKS_DIR = LIBRARY_DIR / "decks"
DECKS_INDEX = LIBRARY_DIR / "decks-index.json"

# Legacy file path constants — these files NO LONGER EXIST on disk; the
# constants remain only so that `from .template_library import X` doesn't
# raise ImportError. Anyone reading via read_json gets {}.
DECK_PROFILES = LIBRARY_DIR / "deck-profiles.json"
SECTION_PROFILES = LIBRARY_DIR / "section-profiles.json"
SLIDE_PROFILES = LIBRARY_DIR / "slide-profiles.json"
COMPONENT_PROFILES = LIBRARY_DIR / "component-profiles.json"
ASSET_PROFILES = LIBRARY_DIR / "asset-profiles.json"
CITATION_PROFILES = LIBRARY_DIR / "citation-profiles.json"
NARRATIVE_PATTERNS = LIBRARY_DIR / "narrative-patterns.json"
SEMANTIC_PROFILES = LIBRARY_DIR / "semantic-profiles.json"
SEARCH_INDEX = LIBRARY_DIR / "search-index.json"

SCHEMA_VERSION = "tree-v1"


# --------------------------------------------------------------------------
# Source enumeration + manifest tracking
# --------------------------------------------------------------------------

def _template_files() -> list[Path]:
    """All source .pptx files under templates/, sorted by path."""
    root = ROOT / "templates"
    if not root.exists():
        return []
    files: list[Path] = []
    for p in root.rglob("*.pptx"):
        if p.is_file():
            files.append(p)
    files.sort(key=lambda p: str(p))
    return files


def _file_signature(path: Path) -> dict:
    st = path.stat()
    h = hashlib.sha1()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    try:
        rel = str(path.resolve().relative_to(ROOT))
    except ValueError:
        rel = str(path)
    return {
        "path": rel,
        "size": st.st_size,
        "mtime_ns": st.st_mtime_ns,
        "sha1": h.hexdigest(),
    }


def _source_manifest() -> dict:
    files = _template_files()
    files_sig = [_file_signature(p) for p in files]
    aggregate = hashlib.sha1()
    for s in files_sig:
        aggregate.update((s["path"] + s["sha1"]).encode("utf-8"))
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now(),
        "source": "template_library_shim",
        "source_count": len(files_sig),
        "source_hash": aggregate.hexdigest(),
        "files": files_sig,
    }


def is_current() -> bool:
    """Return True if every source .pptx still matches the saved manifest.

    Compares per-file SHA1, not just count, so renames or content edits
    invalidate the library. Returns False if MANIFEST is missing.
    """
    if not MANIFEST.exists():
        return False
    old = read_json(MANIFEST, {})
    fresh = _source_manifest()
    return bool(old.get("source_hash") and old["source_hash"] == fresh["source_hash"])


# --------------------------------------------------------------------------
# deck_id computation — canonical format for library-side (tpl.*) ids
# --------------------------------------------------------------------------

def _scenario_from_pptx(pptx: Path) -> str:
    """First-level dir under templates/ = scenario."""
    try:
        rel = pptx.resolve().relative_to((ROOT / "templates").resolve())
        parts = rel.parts
        if len(parts) >= 2:
            return parts[0]
    except (ValueError, OSError):
        pass
    return "misc"


def compute_deck_id(pptx: Path, sha1_hex: str) -> str:
    """Canonical library-side deck_id: `tpl.<scenario>.<stem>.<sha8>`.

    scenario / stem are sanitized via library_tree.safe_dirname.
    """
    from . import library_tree
    scenario = library_tree.safe_dirname(_scenario_from_pptx(pptx), max_len=40)
    stem = library_tree.safe_dirname(pptx.stem, max_len=60)
    return f"tpl.{scenario}.{stem}.{sha1_hex[:8]}"


# --------------------------------------------------------------------------
# Import — run ppt-master importer on every templates/*.pptx that lacks a
# `data/resources_library/material/imports/<deck_id>/manifest.json`.
# --------------------------------------------------------------------------

def import_all(*, only: list[str] | None = None, force: bool = False) -> dict:
    """Ensure every `templates/**.pptx` is decomposed into imports/<deck_id>/.

    Args:
        only: optional list of pptx paths (relative or absolute) — only
            these will be imported. Path matching is by exact resolved-path
            equality. If None, all templates/**.pptx are processed.
        force: re-run importer even if imports/<deck_id>/manifest.json exists.

    Returns summary dict `{ok: [deck_id...], failed: [{deck_id, error}...],
                            skipped: [deck_id...]}`.
    """
    import sys as _sys
    _sys.path.insert(0, str(ROOT / "scripts" / "lib"))
    try:
        import template_ingest  # type: ignore
    except ImportError as exc:
        return {"ok": [], "failed": [], "skipped": [],
                "error": f"cannot import template_ingest: {exc}"}

    scripts_dir = ROOT / "scripts" / "lib" / "ppt_master"
    if not scripts_dir.exists():
        return {"ok": [], "failed": [], "skipped": [],
                "error": f"ppt_master scripts dir missing: {scripts_dir}"}

    imports_root = LIBRARY_DIR / "imports"
    imports_root.mkdir(parents=True, exist_ok=True)

    pptx_files = _template_files()
    if not pptx_files:
        return {"ok": [], "failed": [], "skipped": [], "error": "no templates/*.pptx found"}

    # Filter by `only` (resolve for exact comparison)
    if only:
        only_set = {str(Path(p).resolve()) for p in only}
        pptx_files = [p for p in pptx_files if str(p.resolve()) in only_set]
        if not pptx_files:
            return {"ok": [], "failed": [], "skipped": [],
                    "error": f"none of the `only` paths matched: {only}"}

    ok: list[str] = []
    failed: list[dict] = []
    skipped: list[str] = []
    for pptx in pptx_files:
        sha1 = _file_signature(pptx)["sha1"]
        deck_id = compute_deck_id(pptx, sha1)
        import_dir = imports_root / deck_id
        manifest_path = import_dir / "manifest.json"
        if manifest_path.exists() and not force:
            skipped.append(deck_id)
            print(f"[import_all] skip {deck_id} (already imported)")
            continue
        print(f"[import_all] importing {pptx.name} → {deck_id}")
        try:
            success = template_ingest.run_importer(pptx, import_dir, scripts_dir)
        except Exception as exc:  # noqa: BLE001
            failed.append({"deck_id": deck_id, "error": f"exception: {exc}"})
            continue
        if not success or not manifest_path.exists():
            failed.append({"deck_id": deck_id, "error": "importer returned failure or no manifest"})
            continue
        ok.append(deck_id)
    print(f"[import_all] done: ok={len(ok)} failed={len(failed)} skipped={len(skipped)}")
    return {"ok": ok, "failed": failed, "skipped": skipped}


# --------------------------------------------------------------------------
# Build — delegate to library_brief
# --------------------------------------------------------------------------

def build(*, force: bool = False, concurrency: int | None = None,
          only_deck_ids: list[str] | None = None) -> dict:
    """Rebuild the directory-tree library by running the 4-skill brief
    pipeline over every unique source deck (dedup by SHA1).

    Args:
        force: rebuild even if manifest looks current.
        concurrency: override DEFAULT_MAX_DECK_CONCURRENCY.
        only_deck_ids: restrict to this subset (must match deck_ids
            already present under imports/).

    Returns a summary including the new MANIFEST contents.
    """
    if not force and only_deck_ids is None and is_current() and DECKS_DIR.exists() and any(DECKS_DIR.iterdir()):
        print("[template_library] up-to-date, skipping build (use force=True to rebuild)")
        return {"manifest": read_json(MANIFEST, {}), "skipped": True}

    from . import library_brief, library_tree

    inputs = library_brief.collect_deck_inputs_from_imports(deck_ids=only_deck_ids)
    if not inputs:
        return {"manifest": {}, "ok": [], "failed": [],
                "error": "no deck imports found"}

    if concurrency is None:
        concurrency = library_brief.DEFAULT_MAX_DECK_CONCURRENCY
    summary = library_brief.generate_briefs_for_decks(
        inputs, decks_root=DECKS_DIR, max_concurrency=concurrency, write_tree=True,
    )

    # Re-emit decks-index.json from the now-populated tree.
    library_tree.write_decks_index(DECKS_DIR)

    # Write SHA1 manifest ONLY on full builds — partial builds shouldn't
    # advertise the whole library as current.
    if only_deck_ids is None:
        manifest = _source_manifest()
        manifest["deck_count"] = len(summary.get("ok") or [])
        manifest["failed_count"] = len(summary.get("failed") or [])
        manifest["briefs_elapsed_seconds"] = summary.get("elapsed_seconds")
        manifest["briefs_model"] = summary.get("model")
        write_json(MANIFEST, manifest)
        summary["manifest"] = manifest
    else:
        summary["manifest"] = read_json(MANIFEST, {})
        summary["partial"] = True
        summary["partial_deck_ids"] = list(only_deck_ids)
    return summary


# --------------------------------------------------------------------------
# Query / load — delegate to library_query
# --------------------------------------------------------------------------

def query_for_project(project_id: str, *, top_k: int = 120) -> dict:
    """Coarse-filter library candidates for a project and write a compat
    `template-library-candidates.json` (English-keyed)."""
    from . import library_query
    import re as _re

    pdir = project_dir(project_id)
    # Build query tokens from project brief / outline.
    tokens: set[str] = set()
    for fp in (pdir / "idea-analysis.json",
               pdir / "task-analysis.json"):
        if not fp.exists():
            continue
        try:
            d = read_json(fp, {}) or {}
        except Exception:
            continue
        for k, v in d.items():
            if isinstance(v, str):
                tokens.update(t for t in _re.split(r"[^\w一-鿿]+", v.lower()) if len(t) >= 2)
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, str):
                        tokens.update(t for t in _re.split(r"[^\w一-鿿]+", item.lower()) if len(t) >= 2)

    lib = library_query.load_library_candidates(
        top_k_decks=None,
        query_tokens=tokens or None,
    )

    # Compose a compat "candidates" flat list (older readers expect this).
    candidates: list = []
    for layer in ("deck", "section", "slide"):
        for item in lib.get(layer, []):
            candidates.append(item)
    candidates.sort(key=lambda x: -(x.get("score") or 0))
    candidates = candidates[: max(1, top_k)]

    result = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now(),
        "source": "template_library.query_for_project (tree-shim)",
        "library_manifest": lib.get("manifest") or {},
        "query": {"anchor_tokens": sorted(tokens)},
        "candidate_count": len(candidates),
        "by_type": {
            "deck": sum(1 for c in candidates if c.get("object_type") == "deck"),
            "section": sum(1 for c in candidates if c.get("object_type") == "section"),
            "slide": sum(1 for c in candidates if c.get("object_type") == "slide"),
        },
        "candidates": candidates,
    }
    write_json(pdir / "template-library-candidates.json", result)
    return result


def load(*, ensure: bool = True) -> dict:
    """Return a compatibility dict for legacy callers that expect the
    old `*-profiles.json` keys. We populate them from the new tree so
    downstream code that iterates `deck_profiles[].decks` still finds
    something — but the field names inside each row are now the
    English-keyed candidate shape (deck_id, topic, audience, ...).
    """
    from . import library_query
    if ensure and not DECKS_INDEX.exists():
        # No tree yet — return empty stubs (no rebuild from this function).
        return {
            "manifest": read_json(MANIFEST, {}),
            "deck_profiles": {"schema_version": SCHEMA_VERSION, "decks": []},
            "section_profiles": {"schema_version": SCHEMA_VERSION, "sections": []},
            "slide_profiles": {"schema_version": SCHEMA_VERSION, "slides": []},
            "component_profiles": {"schema_version": SCHEMA_VERSION, "components": []},
            "asset_profiles": {"schema_version": SCHEMA_VERSION, "assets": []},
            "citation_profiles": {"schema_version": SCHEMA_VERSION, "citations": []},
            "narrative_patterns": {"schema_version": SCHEMA_VERSION, "patterns": []},
            "semantic_profiles": {"schema_version": SCHEMA_VERSION, "decks": []},
            "search_index": {"schema_version": SCHEMA_VERSION, "items": []},
        }
    lib = library_query.load_library_candidates()
    return {
        "manifest": read_json(MANIFEST, {}),
        "deck_profiles": {"schema_version": SCHEMA_VERSION, "decks": lib["deck"]},
        "section_profiles": {"schema_version": SCHEMA_VERSION, "sections": lib["section"]},
        "slide_profiles": {"schema_version": SCHEMA_VERSION, "slides": lib["slide"]},
        # The four below are no longer populated — leave empty.
        "component_profiles": {"schema_version": SCHEMA_VERSION, "components": []},
        "asset_profiles": {"schema_version": SCHEMA_VERSION, "assets": []},
        "citation_profiles": {"schema_version": SCHEMA_VERSION, "citations": []},
        "narrative_patterns": {"schema_version": SCHEMA_VERSION, "patterns": []},
        "semantic_profiles": {"schema_version": SCHEMA_VERSION, "decks": []},
        "search_index": {"schema_version": SCHEMA_VERSION, "items": []},
    }


def query(context: dict, *, top_k: int = 80) -> dict:
    """Legacy `query()` for callers that don't have a project_id. Just
    returns the full library candidate list trimmed to top_k by score."""
    from . import library_query
    lib = library_query.load_library_candidates()
    candidates = []
    for layer in ("deck", "section", "slide"):
        candidates.extend(lib.get(layer, []))
    candidates.sort(key=lambda x: -(x.get("score") or 0))
    candidates = candidates[: max(1, top_k)]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now(),
        "source": "template_library.query (tree-shim)",
        "library_manifest": lib.get("manifest") or {},
        "query": context,
        "candidate_count": len(candidates),
        "by_type": {
            "deck": sum(1 for c in candidates if c.get("object_type") == "deck"),
            "section": sum(1 for c in candidates if c.get("object_type") == "section"),
            "slide": sum(1 for c in candidates if c.get("object_type") == "slide"),
        },
        "candidates": candidates,
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _cli():
    parser = argparse.ArgumentParser(prog="template_library")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("is-current")
    bld = sub.add_parser("build")
    bld.add_argument("--force", action="store_true")
    bld.add_argument("-j", "--concurrency", type=int, default=None)
    qry = sub.add_parser("query")
    qry.add_argument("--topic", default="")
    qry.add_argument("--top-k", type=int, default=20)
    args = parser.parse_args()

    if args.cmd == "status":
        m = read_json(MANIFEST, {})
        print(json.dumps({
            "library_dir": str(LIBRARY_DIR),
            "decks_dir": str(DECKS_DIR),
            "decks_in_tree": len(list(DECKS_DIR.iterdir())) if DECKS_DIR.exists() else 0,
            "manifest_exists": MANIFEST.exists(),
            "is_current": is_current(),
            "manifest_source_count": m.get("source_count"),
            "manifest_deck_count": m.get("deck_count"),
        }, ensure_ascii=False, indent=2))
        return
    if args.cmd == "is-current":
        print("yes" if is_current() else "no")
        sys.exit(0 if is_current() else 1)
    if args.cmd == "build":
        summary = build(force=args.force, concurrency=args.concurrency)
        print(json.dumps({k: (v if not isinstance(v, list) or len(v) <= 5 else f"{len(v)} items")
                          for k, v in summary.items()}, ensure_ascii=False, indent=2))
        return
    if args.cmd == "query":
        r = query({"topic": args.topic}, top_k=args.top_k)
        print(json.dumps({
            "candidate_count": r["candidate_count"],
            "by_type": r["by_type"],
            "top_3": [{"object_type": c.get("object_type"), "resource_id": c.get("resource_id"),
                       "score": c.get("score"), "topic": c.get("topic")}
                      for c in r["candidates"][:3]],
        }, ensure_ascii=False, indent=2))
        return


# Public alias for legacy code paths.
main = _cli


if __name__ == "__main__":
    _cli()
