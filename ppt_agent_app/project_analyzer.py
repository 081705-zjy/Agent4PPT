"""Project resource analyzer (Phase C.4).

For each file under `projects/<id>/sources/`, route to a format-specific
Claude skill, parse the output, and aggregate into
`projects/<id>/source-relevance.json`.

Per-format extractors:
  - PDF   → `_extract_pdf_pages` (pymupdf / fitz)
  - PPTX  → delegated to `project_library.build_project_library` (separate flow)
  - Excel → TODO: openpyxl not installed; logs a warning and skips
  - Image → TODO: multimodal claude_cli call not yet wired
  - Generic doc (txt/md/docx) → `_extract_text`

Output: `source-relevance.json` with per-file `relevance_score`,
`适合章节`, `不适合章节`, `discard_candidate`.
"""
from __future__ import annotations
import concurrent.futures
import json
import sys
import threading
import time
from pathlib import Path

from . import claude_cli
from .models import ROOT
from .project_library import (
    _classify_file, _project_root, _project_sources_dir, _project_decks_dir,
    _project_analysis_dir, scan_sources_inventory,
)


ANALYZE_MODEL = "claude-opus-4-8"
MAX_RETRIES = 2
ANALYZE_CONCURRENCY = 4

SKILL_BY_TYPE = {
    "pdf":   "skills/sources/pdf_analysis.md",
    "excel": "skills/sources/excel_analysis.md",
    "image": "skills/sources/image_analysis.md",
    "doc":   "skills/sources/doc_analysis.md",
}

_print_lock = threading.Lock()


def _log(msg: str) -> None:
    with _print_lock:
        print(msg, flush=True)


# --------------------------------------------------------------------------
# Per-format text extractors
# --------------------------------------------------------------------------

def _extract_pdf_pages(path: Path, *, max_pages: int = 30, max_chars_per_page: int = 1200) -> list[dict]:
    """Return [{page, text}] using pymupdf. Limits total pages to keep prompt
    manageable; PDF analysis skill cares more about per-page text + figure
    captions than every page."""
    try:
        import fitz  # pymupdf
    except ImportError:
        _log("[analyze] pymupdf not available; cannot read PDF")
        return []
    out: list[dict] = []
    try:
        with fitz.open(str(path)) as doc:
            total = doc.page_count
            for i in range(min(max_pages, total)):
                page = doc[i]
                text = (page.get_text() or "").strip()
                if len(text) > max_chars_per_page:
                    text = text[:max_chars_per_page] + "…"
                if text:
                    out.append({"page": i + 1, "text": text})
    except Exception as exc:  # noqa: BLE001
        _log(f"[analyze] PDF read failed {path.name}: {exc}")
    return out


def _extract_text(path: Path, *, max_chars: int = 8000) -> str:
    try:
        s = path.read_text(encoding="utf-8", errors="ignore")
        return s[:max_chars] + ("…" if len(s) > max_chars else "")
    except Exception as exc:  # noqa: BLE001
        _log(f"[analyze] text read failed {path.name}: {exc}")
        return ""


# --------------------------------------------------------------------------
# Per-file analyzer
# --------------------------------------------------------------------------

def _project_context(project_id: str) -> dict:
    """Build the shared 项目 context dict that all analysis skills see."""
    pdir = _project_root(project_id)
    brief_path = pdir / "idea-analysis.json"
    brief = {}
    if brief_path.exists():
        try:
            brief = json.loads(brief_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    chapters = []
    for c in brief.get("expected_sections") or []:
        if isinstance(c, dict):
            chapters.append({
                "序号": c.get("section_index"),
                "章节名": c.get("chapter") or c.get("章节名"),
                "purpose": c.get("purpose"),
            })
    if not chapters:
        # Fallback: take from narrative_blueprint.arc
        arc = (brief.get("narrative_blueprint") or {}).get("arc") or []
        for i, a in enumerate(arc):
            chapters.append({"序号": i + 1, "章节名": a.get("chapter"), "purpose": a.get("purpose")})
    return {
        "项目主题": brief.get("topic"),
        "项目主题标签": brief.get("topic_tags") or [],
        "项目章节": chapters,
    }


def _analyze_pdf(file_info: dict, ctx: dict, *, project_id: str) -> dict | None:
    path = _project_root(project_id) / file_info["path"]
    pages = _extract_pdf_pages(path)
    if not pages:
        return None
    payload = {
        **ctx,
        "PDF 文件": {
            "文件名": file_info["name"],
            "总页数": len(pages),
            "页面文本": pages,
            "图表标注": [],  # could be extracted with pymupdf later
        }
    }
    return _call_skill(SKILL_BY_TYPE["pdf"], payload, file_info)


def _analyze_doc(file_info: dict, ctx: dict, *, project_id: str) -> dict | None:
    path = _project_root(project_id) / file_info["path"]
    text = _extract_text(path)
    if not text.strip():
        return None
    payload = {
        **ctx,
        "文档": {
            "文件名": file_info["name"],
            "格式": file_info["ext"].lstrip("."),
            "字数": len(text),
            "全文": text,
        }
    }
    return _call_skill(SKILL_BY_TYPE["doc"], payload, file_info)


def _analyze_unsupported(file_info: dict, reason: str) -> dict:
    return {
        "文件名": file_info["name"],
        "path": file_info["path"],
        "type": file_info["type"],
        "relevance_score": None,
        "discard_candidate": False,
        "skipped": True,
        "skip_reason": reason,
    }


def _call_skill(skill_path: str, payload: dict, file_info: dict) -> dict | None:
    prompt = json.dumps(payload, ensure_ascii=False)
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        r = claude_cli.call_claude_json(
            prompt, skill=[skill_path], model=ANALYZE_MODEL, timeout=240,
        )
        if r.get("ok"):
            data = r["data"]
            if isinstance(data, dict) and "relevance_score" in data:
                data["path"] = file_info["path"]
                data["type"] = file_info["type"]
                return data
            last_err = "missing relevance_score in output"
        else:
            last_err = r.get("error")
        _log(f"  [analyze/retry {attempt}] {file_info['name']}: {(last_err or '')[:160]}")
        time.sleep(1.5 ** attempt)
    return {
        "文件名": file_info["name"],
        "path": file_info["path"],
        "type": file_info["type"],
        "relevance_score": 0.0,
        "discard_candidate": False,
        "analysis_failed": True,
        "last_error": last_err,
    }


def _analyze_one(file_info: dict, ctx: dict, *, project_id: str) -> dict:
    t = file_info["type"]
    try:
        if t == "pdf":
            r = _analyze_pdf(file_info, ctx, project_id=project_id)
        elif t == "doc":
            r = _analyze_doc(file_info, ctx, project_id=project_id)
        elif t == "pptx":
            return _analyze_unsupported(file_info,
                "pptx handled by project_library.build_project_library (separate flow)")
        elif t == "excel":
            return _analyze_unsupported(file_info, "excel analyzer TODO (no openpyxl installed)")
        elif t == "image":
            return _analyze_unsupported(file_info, "image analyzer TODO (multimodal CLI not wired)")
        else:
            return _analyze_unsupported(file_info, f"unsupported type: {t}")
        if r is None:
            return _analyze_unsupported(file_info, "extractor returned empty")
        return r
    except Exception as exc:  # noqa: BLE001
        return {
            "文件名": file_info["name"],
            "path": file_info["path"],
            "type": file_info["type"],
            "analysis_failed": True,
            "last_error": f"{type(exc).__name__}: {exc}",
        }


# --------------------------------------------------------------------------
# Orchestrator
# --------------------------------------------------------------------------

def _write_per_file_analysis(project_id: str, file_info: dict, analysis: dict) -> None:
    """Phase P16c: write each file's analysis to `data/<type>/<stem>.json`."""
    t = file_info.get("type")
    if t not in {"pdf", "excel", "image", "doc"}:
        return
    stem = Path(file_info["name"]).stem
    out_dir = _project_analysis_dir(project_id, t)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{stem}.json"
    out_path.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")


def analyze_project_sources(
    project_id: str,
    *,
    concurrency: int = ANALYZE_CONCURRENCY,
    types: list[str] | None = None,
) -> dict:
    """Run per-format analyzers on every file in `sources/`. Returns the
    aggregated report; also writes `source-relevance.json` AND per-file
    `data/<type>/<stem>.json` (Phase P16c).

    `types` (optional): restrict to these classifier types (`pdf`, `doc`,
    `pptx`, `excel`, `image`). Default: all non-pptx (pptx goes through
    `project_library.build_project_library`).
    """
    inv = scan_sources_inventory(project_id)
    files = inv.get("files") or []
    if types is None:
        types = ["pdf", "doc", "excel", "image"]  # pptx skipped — use build_project_library
    target_files = [f for f in files if f["type"] in types]

    ctx = _project_context(project_id)
    if not ctx.get("项目章节"):
        _log("[analyze] WARNING: 项目章节 is empty — idea-analysis.json missing or has no expected_sections")

    _log(f"[analyze] {len(target_files)} files, concurrency={concurrency}, model={ANALYZE_MODEL}")
    t0 = time.time()
    items: list[dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency,
                                               thread_name_prefix="analyze") as pool:
        futs = {pool.submit(_analyze_one, f, ctx, project_id=project_id): f for f in target_files}
        done = 0
        for fut in concurrent.futures.as_completed(futs):
            f = futs[fut]
            try:
                r = fut.result()
            except Exception as exc:
                r = {"path": f["path"], "type": f["type"], "analysis_failed": True,
                     "last_error": str(exc)}
            done += 1
            score = r.get("relevance_score")
            status = "skipped" if r.get("skipped") else (
                "failed" if r.get("analysis_failed") else f"score={score}")
            _log(f"  [{done}/{len(target_files)}] {f['name']:<50} {status}")
            # Phase D: write per-file analysis next to its category
            try:
                _write_per_file_analysis(project_id, f, r)
            except Exception as exc:
                _log(f"  [warn] per-file write failed for {f['name']}: {exc}")
            items.append(r)

    elapsed = time.time() - t0

    # Auto-flag discard candidates: relevance_score < 0.3 AND 适合章节 empty.
    for item in items:
        if item.get("skipped") or item.get("analysis_failed"):
            continue
        score = item.get("relevance_score") or 0.0
        suitable = item.get("适合章节") or item.get("可引用场景") or []
        item["discard_candidate"] = bool(score < 0.3 and not suitable)

    n_discard = sum(1 for x in items if x.get("discard_candidate"))
    report = {
        "schema_version": "relevance-v1",
        "project_id": project_id,
        "elapsed_seconds": elapsed,
        "total_analyzed": len(items),
        "model": ANALYZE_MODEL,
        "n_discard_candidates": n_discard,
        "by_type": {t: sum(1 for x in items if x.get("type") == t) for t in set(x.get("type") for x in items)},
        "items": items,
    }
    out = _project_root(project_id) / "source-relevance.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _log(f"[analyze] done in {elapsed:.1f}s · {n_discard} discard candidates · wrote {out.name}")
    return report


def _cli():
    import argparse
    p = argparse.ArgumentParser(prog="project_analyzer")
    p.add_argument("project_id")
    p.add_argument("-j", "--concurrency", type=int, default=ANALYZE_CONCURRENCY)
    p.add_argument("--types", default=None,
                   help="comma list: pdf,doc,excel,image  (default: pdf+doc+excel+image)")
    args = p.parse_args()

    types = args.types.split(",") if args.types else None
    r = analyze_project_sources(args.project_id, concurrency=args.concurrency, types=types)
    print(json.dumps({k: v for k, v in r.items() if k != "items"},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    _cli()
