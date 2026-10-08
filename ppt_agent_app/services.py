from __future__ import annotations

import subprocess
import json
import mimetypes
import re
from pathlib import Path

from . import devops, jobs, layout_registry, model_providers, providers, research, route_log, skill_runtime, stage_controller, stage_runner, template_library, tool_providers
from .models import ROOT, now, project_dir, read_json, slug, write_json
from .questions import QUESTION_SCHEMA, completion
from .resources import build_resource_digest, scan_project


def split_answer_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "")
    return [item.strip() for item in re.split(r"[\n,，;；]+", text) if item.strip()]


def create_project(payload: dict) -> dict:
    topic = str(payload.get("topic") or "untitled deck").strip()
    project_id = str(payload.get("project_id") or slug(topic)).strip()
    pdir = project_dir(project_id)
    pdir.mkdir(parents=True, exist_ok=True)
    for rel in ("templates", "sources", "assets", "reviews/outline", "reviews/style-sample", "reviews/screenshot", "reviews/deck"):
        (pdir / rel).mkdir(parents=True, exist_ok=True)
    existing = read_json(pdir / "app-state.json", {})
    if existing and not payload.get("reset"):
        existing["loaded_existing"] = True
        existing["project_dir"] = str(pdir)
        return existing
    answers = {
        "topic": topic,
        "slide_count": str(payload.get("slide_count") or "10"),
        "language": str(payload.get("language") or "zh"),
        "user_outline": str(payload.get("user_outline") or ""),
        "reuse_policy": str(payload.get("reuse_policy") or "激进复用：优先复用已有 PPT 的叙事、页面、图片、表格和图解，缺口再检索或生成"),
    }
    state = {
        "project_id": project_id,
        "project_dir": str(pdir),
        "created_at": now(),
        "updated_at": now(),
        "answers": answers,
        "status": "draft",
    }
    write_json(pdir / "app-state.json", state)
    write_json(pdir / "question-state.json", {"questions": QUESTION_SCHEMA, "answers": answers, **completion(answers)})
    stage_controller.initialize(project_id)
    return state


def get_project(project_id: str) -> dict:
    pdir = project_dir(project_id)
    state = read_json(pdir / "app-state.json", {})
    if not state:
        raise FileNotFoundError(project_id)
    state["resources"] = read_json(pdir / "project-source-index.json", [])
    state["quality"] = quality(project_id)
    state["citations"] = read_json(pdir / "citations.json", {}).get("citations", [])
    state["research"] = read_json(pdir / "research-results.json", {})
    state["research_audit"] = read_json(pdir / "research-audit.json", {})
    state["model_plan"] = read_json(pdir / "model-routed-plan.json", {})
    state["stage_state"] = stage_controller.refresh(project_id)
    state["slide_state"] = stage_controller.slide_state(project_id)
    state["route_log"] = route_log.read(project_id, limit=80)
    state["stage_diagnostics"] = stage_diagnostics(project_id)
    state["devops"] = read_json(pdir / "devops/codex-debug-report.json", {})
    state["downloads"] = downloads(project_id)
    return state


def stage_diagnostics(project_id: str) -> dict:
    pdir = project_dir(project_id)
    logs = route_log.read(project_id, limit=200)
    latest_by_stage: dict[str, dict] = {}
    for item in logs:
        stage = str(item.get("stage") or "").upper()
        if stage and stage not in latest_by_stage:
            latest_by_stage[stage] = item
    visual_failed = read_json(pdir / "visual-plan.failed.json", {})
    render_audit_data = read_json(pdir / "render-audit.json", {})
    content_quality = read_json(pdir / "content-quality-report.json", {})
    out: dict[str, dict] = {}
    for spec in skill_runtime.stage_specs():
        stage = str(spec.get("stage") or "").upper()
        model_route = str(spec.get("model_route") or "").upper()
        log_item = latest_by_stage.get(model_route) or latest_by_stage.get(stage) or {}
        diag = {
            "stage": stage,
            "model_route": spec.get("model_route"),
            "latest_model_call": log_item or None,
            "provider": log_item.get("selected_provider"),
            "fallback_used": log_item.get("fallback_used"),
            "success": log_item.get("success"),
            "error": log_item.get("error"),
            "error_type": log_item.get("error_type"),
            "gaps": [],
            "failed_artifact": None,
        }
        if stage == "SLIDE_REWRITE" and visual_failed:
            diag["failed_artifact"] = "visual-plan.failed.json"
            diag["gaps"] = ((visual_failed.get("quality_audit") or {}).get("gaps") or [])[:12]
        if stage == "SLIDE_REWRITE" and not diag.get("provider"):
            visual_plan = read_json(pdir / "visual-plan.json", {})
            if isinstance(visual_plan, dict) and visual_plan.get("generated_by"):
                diag["provider"] = visual_plan.get("generated_by")
        if stage == "RENDER" and render_audit_data:
            diag["failed_artifact"] = "render-audit.json" if not render_audit_data.get("pass", True) else None
            diag["gaps"] = (render_audit_data.get("issues") or [])[:12]
        if stage == "REVIEW" and content_quality:
            visual_spec = content_quality.get("visual_spec_quality") or {}
            if not visual_spec.get("pass", True):
                diag["gaps"] = (
                    (visual_spec.get("gaps") or [])
                    + (visual_spec.get("composition_gaps") or [])
                    + (visual_spec.get("blueprint_gaps") or [])
                    + (visual_spec.get("composition_coverage_gaps") or [])
                )[:12]
        out[stage] = diag
    return out


def project_research_summary(project_id: str) -> dict:
    pdir = project_dir(project_id)
    state = read_json(pdir / "app-state.json", {})
    if not state:
        raise FileNotFoundError(project_id)
    research_data = read_json(pdir / "research-results.json", {})
    results = []
    for item in research_data.get("results", []) if isinstance(research_data, dict) else []:
        if not isinstance(item, dict):
            continue
        results.append({
            "title": item.get("title"),
            "url": item.get("url"),
            "snippet": str(item.get("snippet") or item.get("evidence_text") or "")[:600],
            "source": item.get("source"),
            "fetch_status": item.get("fetch_status"),
            "fetch_provider": item.get("fetch_provider"),
        })
    citations = []
    for item in read_json(pdir / "citations.json", {}).get("citations", []):
        if not isinstance(item, dict):
            continue
        citations.append({
            "id": item.get("id"),
            "title": item.get("title"),
            "url": item.get("url"),
            "evidence_tier": item.get("evidence_tier"),
            "fetch_status": item.get("fetch_status"),
        })
    return {
        "project_id": project_id,
        "research": {
            "web_results_count": research_data.get("web_results_count"),
            "fetched_count": research_data.get("fetched_count"),
            "queries": research_data.get("queries") or [],
            "results": results[:24],
        },
        "research_audit": read_json(pdir / "research-audit.json", {}),
        "citations": citations[:40],
        "downloads": downloads(project_id),
    }


def update_answers(project_id: str, answers: dict) -> dict:
    pdir = project_dir(project_id)
    state = read_json(pdir / "app-state.json", {})
    if not state:
        raise FileNotFoundError(project_id)
    merged = dict(state.get("answers") or {})
    merged.update({k: v for k, v in answers.items() if v is not None})
    state["answers"] = merged
    state["updated_at"] = now()
    write_json(pdir / "app-state.json", state)
    qstate = {"questions": QUESTION_SCHEMA, "answers": merged, **completion(merged)}
    write_json(pdir / "question-state.json", qstate)
    return qstate


# --------------------------------------------------------------------------
# P17: Pre-computed source-analysis readers (replace runtime library_analyzer)
# --------------------------------------------------------------------------

def _read_precomputed_source_analysis(
    pdir: Path, type_dir: str, source_path: str | None
) -> dict | None:
    """Read `projects/<id>/data/<type_dir>/<stem>.json` if it exists.

    Returns the raw (Chinese-keyed) analysis dict, or None if no analysis
    has been written yet for this source file.
    """
    if not source_path:
        return None
    try:
        stem = Path(source_path).stem
    except Exception:
        return None
    candidate = pdir / "data" / type_dir / f"{stem}.json"
    if not candidate.exists():
        return None
    try:
        return json.loads(candidate.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _translate_doc_analysis(zh: dict) -> dict:
    """Map pdf_analysis / doc_analysis Chinese keys → English doc_unit fields."""
    chapters = []
    for c in (zh.get("适合章节") or []):
        if not isinstance(c, dict):
            continue
        chapters.append({
            "chapter_index": c.get("章节序号"),
            "chapter_name": c.get("章节名"),
            "why": c.get("为什么"),
        })
    quotes = []
    for q in (zh.get("可引用片段") or zh.get("关键段落") or []):
        if not isinstance(q, dict):
            continue
        quotes.append({
            "page": q.get("页码") or q.get("标题或位置"),
            "text": q.get("原文") or q.get("原文摘录"),
            "use_for": q.get("可引用场景"),
        })
    key_claims: list[str] = []
    core = zh.get("核心论断")
    if core:
        key_claims.append(str(core))
    for r in (zh.get("实验结果") or []):
        if r:
            key_claims.append(str(r))
    section_summaries: list[str] = []
    for s in (zh.get("结构概要") or []):
        if s:
            section_summaries.append(str(s))
    method = zh.get("方法概要")
    if method and not section_summaries:
        section_summaries.append(str(method))
    score = zh.get("relevance_score") or 0
    cite = "high" if score >= 0.7 else ("medium" if score >= 0.4 else "low")
    return {
        "topic": zh.get("文档主题") or zh.get("标题"),
        "doc_type": zh.get("资料类型"),
        "language": "zh",
        "key_claims": key_claims or None,
        "anchor_terms": zh.get("主题标签") or None,
        "section_summaries": section_summaries or None,
        "reusable_quotes": quotes or None,
        "applicable_chapters": chapters or None,
        "cite_recommendation": cite,
    }


def _translate_figure_analysis(zh: dict) -> dict:
    """Map image_analysis Chinese keys → English figure_unit fields."""
    return {
        "what_it_shows": zh.get("图表内容") or zh.get("标题") or zh.get("图片说明"),
        "figure_kind": zh.get("图表类型") or zh.get("图片类型"),
        "evidence_kind": zh.get("证据类型"),
        "key_elements": zh.get("关键元素") or None,
        "anchor_terms": zh.get("主题标签") or None,
        "applicable_chapters": [
            {"chapter_index": c.get("章节序号"),
             "chapter_name": c.get("章节名"),
             "why": c.get("为什么")}
            for c in (zh.get("适合章节") or []) if isinstance(c, dict)
        ] or None,
        "best_used_for": zh.get("适用场景") or zh.get("最佳用途"),
        "reusability": zh.get("复用建议"),
        "do_not_reuse_when": zh.get("不适用场景"),
        "caption_suggestion": zh.get("建议图注"),
    }


def _translate_sheet_analysis(zh: dict) -> dict:
    """Map excel_analysis Chinese keys → English sheet_unit fields."""
    return {
        "topic": zh.get("文档主题") or zh.get("标题"),
        "sheets": zh.get("工作表") or zh.get("sheets") or None,
        "anchor_terms": zh.get("主题标签") or None,
        "do_not_use_when": zh.get("不适用场景"),
    }


def scan_resources(project_id: str) -> dict:
    pdir = project_dir(project_id)
    resources = scan_project(pdir)
    digest = build_resource_digest(pdir, resources)
    asset_catalog = _asset_catalog_from_resources(resources, pdir)
    # P18: drop legacy aliases (resource-index.json, source-digest.json,
    # asset-catalog.json, chart-candidates.json, visual-reference-index.json).
    # PROJECT_SOURCE_SCAN now writes the canonical project-*-* names directly.
    write_json(pdir / "project-source-index.json", resources)
    write_json(pdir / "project-source-digest.json", digest)
    write_json(pdir / "project-asset-catalog.json", asset_catalog)
    decomposition = _decompose_project_decks(pdir, resources, digest)
    by_type: dict[str, int] = {}
    for item in resources:
        typ = str(item.get("type") or "file")
        by_type[typ] = by_type.get(typ, 0) + 1
    return {
        "project_id": project_id,
        "count": len(resources),
        "parsed_count": digest.get("parsed_count", 0),
        "by_type": by_type,
        "artifacts": {
            "resource_index": "project-source-index.json",
            "source_digest": "project-source-digest.json",
            "asset_catalog": "project-asset-catalog.json",
            "project_slide_units": "project-slide-units.json",
            "project_component_units": "project-component-units.json",
            "project_asset_units": "project-asset-units.json",
            "project_doc_units": "project-doc-units.json",
        },
        "asset_count": len(asset_catalog.get("assets") or []),
        "template_library_current": template_library.is_current(),
        "decomposition": decomposition,
        "sample_resources": [
            {
                "path": item.get("path"),
                "type": item.get("type"),
                "reusable_level": item.get("reusable_level"),
            }
            for item in resources[:20]
        ],
    }


def _decompose_project_decks(pdir: Path, resources: list[dict], digest: dict) -> dict:
    """Decompose user-uploaded resources into reusable units for the matching/draft stages.

    For each PPTX in sources/:
      1. Run the ppt-master importer (idempotent) into ``decomposed/<deck_slug>/``.
      2. Build deck / section / slide / component / asset units that mirror the
         offline template library schema (so retrieval/matching can treat the two
         pools uniformly — only ``source_owner`` differs).
      3. Run the 3-layer Claude semantic analysis (deck → sections ∥ slides) via
         ``library_analyzer.analyze_decks_concurrent`` so every project deck has
         the same enrichment fields as offline templates. 4 decks in parallel.

    PDFs / Word / Excel: emit chunk / figure / table / sheet units from the
    digest. These are referenced by GAP_RESEARCH only — they do NOT enter the
    deck/section/slide matching pools.

    Returns a summary of counts for logging.
    """
    import re as _re
    import sys as _sys
    # P17: removed the legacy library_analyzer fallback. All source semantics
    # now come from pre-computed per-format analyses written by
    # `project_analyzer.analyze_project_sources` (pdf/doc/excel/image) and
    # `project_library.build_project_library` (pptx). This function reads
    # those analyses from `data/<type>/` and translates them into the unit
    # schema. Files not yet analyzed produce units with `semantic_ok=False`
    # and the semantic fields left as None.

    summary = {
        "slide_count": 0,
        "section_count": 0,
        "component_count": 0,
        "asset_count": 0,
        "doc_unit_count": 0,
        "deck_count": 0,
        "semantic_ok": 0,
        "semantic_partial": 0,
        "semantic_failed": 0,
    }

    # PPTX decomposition via vendored ppt-master importer.
    decomposed_root = pdir / "decomposed"
    decomposed_root.mkdir(parents=True, exist_ok=True)
    scripts_dir = ROOT / "scripts" / "lib" / "ppt_master"
    pptx_resources = [r for r in resources if str(r.get("type") or "") in {"presentation", "ppt_deck"}]
    decks: list[dict] = []
    sections: list[dict] = []
    slide_units: list[dict] = []
    component_units: list[dict] = []
    asset_units: list[dict] = []

    # ---- 1. Deterministic decomposition ----------------------------------
    if pptx_resources and scripts_dir.exists():
        try:
            _sys.path.insert(0, str(ROOT / "scripts" / "lib"))
            import template_ingest  # type: ignore
        except Exception:
            template_ingest = None  # type: ignore
        if template_ingest is not None:
            for res in pptx_resources:
                src_rel = str(res.get("path") or "")
                if not src_rel:
                    continue
                src = (pdir / src_rel) if not Path(src_rel).is_absolute() else Path(src_rel)
                if not src.exists():
                    continue
                slug_name = _re.sub(r"[^A-Za-z0-9]+", "-", src.stem)[:48].strip("-").lower() or "deck"
                deck_id = f"proj.{slug_name}"
                import_dir = decomposed_root / slug_name
                ok = template_ingest.run_importer(src, import_dir, scripts_dir)
                if not ok:
                    continue
                manifest_path = import_dir / "manifest.json"
                if not manifest_path.exists():
                    continue
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                except Exception:
                    continue
                deck_slides = manifest.get("slides") or []
                deck_assets = manifest.get("assets") or {}

                # Per-slide units + per-section auto-grouping
                deck_slide_ids: list[str] = []
                deck_section_ids: list[str] = []
                current_section: dict | None = None
                current_section_id = ""
                for s_idx, s in enumerate(deck_slides, start=1):
                    if not isinstance(s, dict):
                        continue
                    sid = f"{deck_id}.slide_{s_idx:02d}"
                    svg_rel = f"decomposed/{slug_name}/svg/slide_{s_idx:02d}.svg"
                    flat_rel = f"decomposed/{slug_name}/svg-flat/slide_{s_idx:02d}.svg"
                    chosen_ref = svg_rel if (pdir / svg_rel).exists() else flat_rel
                    text_samples = []
                    raw_text = s.get("textSamples") or s.get("textRuns") or s.get("text_runs") or []
                    for txt in raw_text:
                        if isinstance(txt, str) and txt.strip():
                            text_samples.append(txt.strip()[:200])
                    if not text_samples and isinstance(s.get("title"), str):
                        text_samples.append(s["title"][:200])
                    image_count = len(s.get("imageAssets") or s.get("images") or [])
                    shape_count = int(s.get("shapeCount") or len(s.get("shapes") or []))
                    page_type = s.get("pageType") or "content"

                    # Coarse section grouping by pageType transitions (mirrors
                    # template_library._section_break heuristics).
                    role = "cover" if s_idx == 1 else (
                        "closing" if s_idx == len(deck_slides) else "content"
                    )
                    is_break = current_section is None or page_type != current_section.get("_page_type")
                    if is_break:
                        sec_idx = len(deck_section_ids) + 1
                        current_section_id = f"{deck_id}.sec.{sec_idx:02d}"
                        current_section = {
                            "section_id": current_section_id,
                            "resource_id": current_section_id,
                            "deck_id": deck_id,
                            "section_index": sec_idx,
                            "role": role,
                            "slide_ids": [],
                            "_page_type": page_type,  # internal: drives break detection
                            "source_owner": "project",
                        }
                        sections.append(current_section)
                        deck_section_ids.append(current_section_id)
                    current_section["slide_ids"].append(sid)

                    slide_units.append({
                        "slide_id": sid,
                        "resource_id": sid,
                        "deck_id": deck_id,
                        "section_id": current_section_id,
                        "slide_index": s_idx,
                        "slide_svg_ref": chosen_ref,
                        "slide_role": role,
                        "slide_layout": page_type,
                        "page_type": page_type,
                        "shape_count": shape_count,
                        "image_count": image_count,
                        "text_samples": text_samples[:10],
                        "what_this_slide_explains": " / ".join(text_samples[:6])[:400],
                        "image_assets": s.get("imageAssets") or [],
                        "source_owner": "project",
                    })
                    deck_slide_ids.append(sid)

                    # Component units (coarse — text + per-image)
                    if text_samples:
                        component_units.append({
                            "component_id": f"{sid}.cmp.text",
                            "resource_id": f"{sid}.cmp.text",
                            "deck_id": deck_id,
                            "slide_id": sid,
                            "kind": "text",
                            "text_sample": " / ".join(text_samples[:5])[:400],
                            "geometry": {},
                            "source_owner": "project",
                        })
                    for c_idx, img in enumerate(s.get("imageAssets") or [], start=1):
                        if not isinstance(img, str):
                            continue
                        component_units.append({
                            "component_id": f"{sid}.cmp.img_{c_idx:02d}",
                            "resource_id": f"{sid}.cmp.img_{c_idx:02d}",
                            "deck_id": deck_id,
                            "slide_id": sid,
                            "kind": "image",
                            "asset_filename": img,
                            "geometry": {},
                            "source_owner": "project",
                        })

                # Strip internal break-detection field from section units.
                for sec in sections:
                    sec.pop("_page_type", None)

                decks.append({
                    "deck_id": deck_id,
                    "resource_id": deck_id,
                    "deck_path": src_rel,
                    "deck_slug": slug_name,
                    "import_dir": str(import_dir.relative_to(pdir)),
                    "slide_count": len(deck_slides),
                    "section_ids": deck_section_ids,
                    "slide_ids": deck_slide_ids,
                    "topic_summary": src.stem,
                    "source_owner": "project",
                })

                # Asset units
                for a_idx, a in enumerate(deck_assets.get("allAssets") or [], start=1):
                    asset_rel = f"decomposed/{slug_name}/assets/{a}"
                    if not (pdir / asset_rel).exists():
                        continue
                    aid = f"{deck_id}.asset_{a_idx:03d}"
                    asset_units.append({
                        "asset_id": aid,
                        "resource_id": aid,
                        "deck_id": deck_id,
                        "asset_path": asset_rel,
                        "filename": a,
                        "source_owner": "project",
                    })

    # ---- 2. Claude semantic analysis: PPT + doc + figure + sheet, all parallel ----
    # Build inputs for all four streams. They share one ThreadPoolExecutor
    # inside library_analyzer.analyze_resources_concurrent.

    # 2a. PPT deck inputs (existing — moved here from the old "if decks:" block)
    analyzer_inputs: list[dict] = []
    if decks:
        slides_by_deck: dict[str, list[dict]] = {}
        sections_by_deck: dict[str, list[dict]] = {}
        for s in slide_units:
            slides_by_deck.setdefault(str(s.get("deck_id")), []).append(s)
        for sec in sections:
            sections_by_deck.setdefault(str(sec.get("deck_id")), []).append(sec)

        for d in decks:
            did = str(d.get("deck_id"))
            deck_slides_for_analyzer = sorted(slides_by_deck.get(did, []), key=lambda x: int(x.get("slide_index") or 0))
            deck_sections_for_analyzer = sorted(sections_by_deck.get(did, []), key=lambda x: int(x.get("section_index") or 0))

            slide_titles = [(s.get("text_samples") or [""])[0] if s.get("text_samples") else "" for s in deck_slides_for_analyzer]
            slide_text_samples = [
                {"index": s.get("slide_index"),
                 "text": " / ".join(s.get("text_samples") or [])[:200]}
                for s in deck_slides_for_analyzer
            ]
            section_break_indices = [
                int((slides_by_deck.get(did, [])[0].get("slide_index") or 1))
                for sec in deck_sections_for_analyzer
                if sec.get("slide_ids")
            ]

            sections_input = []
            for sec in deck_sections_for_analyzer:
                sec_slide_ids = sec.get("slide_ids") or []
                sec_slides_objs = [next((s for s in deck_slides_for_analyzer if s.get("slide_id") == sid), {}) for sid in sec_slide_ids]
                sections_input.append({
                    "section_id": sec.get("section_id"),
                    "section_index": sec.get("section_index"),
                    "role_hint": sec.get("role"),
                    "slide_indices": [s.get("slide_index") for s in sec_slides_objs],
                    "slide_titles": [(s.get("text_samples") or [""])[0] if s.get("text_samples") else "" for s in sec_slides_objs],
                    "slide_text_samples": [(" / ".join(s.get("text_samples") or []))[:200] for s in sec_slides_objs],
                })

            slides_input = []
            for s in deck_slides_for_analyzer:
                slides_input.append({
                    "slide_id": s.get("slide_id"),
                    "slide_index": s.get("slide_index"),
                    "section_id": s.get("section_id"),
                    "slide_role_hint": s.get("slide_role"),
                    "title": (s.get("text_samples") or [""])[0] if s.get("text_samples") else "",
                    "claim_sample": "",
                    "what_this_slide_explains": s.get("what_this_slide_explains"),
                    "text_samples": (s.get("text_samples") or [])[:6],
                    "shape_count": s.get("shape_count"),
                    "image_count": s.get("image_count"),
                    "visual_logic_hint": "image-led" if (s.get("image_count") or 0) >= 3 else ("diagram-led" if (s.get("shape_count") or 0) >= 8 else "text-led"),
                })

            analyzer_inputs.append({
                "deck_id": did,
                "source_path": d.get("deck_path"),
                "template_type": "project_upload",
                "slide_count": len(slides_input),
                "slide_titles": slide_titles,
                "slide_text_samples": slide_text_samples,
                "section_break_indices": section_break_indices,
                "asset_brief": {
                    "image_count": sum((s.get("image_count") or 0) for s in deck_slides_for_analyzer),
                },
                "style_hints": {},
                "sections": sections_input,
                "slides": slides_input,
            })

    # 2b. Doc inputs — PDFs / Word / Markdown
    doc_inputs: list[dict] = []
    digest_items = (digest.get("items") or []) if isinstance(digest, dict) else []
    for item in digest_items:
        item_type = str(item.get("type") or "")
        if item_type not in {"document", "pdf", "markdown", "text"}:
            continue
        rid_base = str(item.get("resource_id") or item.get("path") or "unknown")
        structured = item.get("structured") or {}
        raw_chunks = structured.get("chunks") or item.get("chunks") or []
        chunks = []
        for c_idx, chunk in enumerate(raw_chunks, start=1):
            if not isinstance(chunk, dict):
                continue
            chunks.append({
                "chunk_index": c_idx,
                "section": chunk.get("section") or chunk.get("heading") or "",
                "text": (chunk.get("text") or "")[:1200],
            })
        if not chunks:
            # No structured chunks — skip Claude analysis; doc will still appear
            # in raw doc_units list but without semantic enrichment.
            continue
        doc_inputs.append({
            "doc_id": rid_base,
            "source_path": item.get("path"),
            "file_kind": "pdf" if item_type == "pdf" else item_type,
            "page_count_or_size": item.get("page_count") or item.get("size") or len(chunks),
            "title_hint": item.get("title") or "",
            "section_headings": [c.get("section") for c in chunks if c.get("section")][:20],
            "chunks": chunks[:40],   # cap to keep prompt size sane
            "figure_captions": [f.get("caption", "") for f in (structured.get("figures") or []) if isinstance(f, dict)][:20],
            "table_captions": [t.get("caption", "") for t in (structured.get("tables") or []) if isinstance(t, dict)][:20],
        })

    # 2c. Figure inputs — standalone images in sources/ or assets/
    figure_inputs: list[dict] = []
    for res in resources:
        rtype = str(res.get("type") or "")
        if rtype != "image":
            continue
        rel = str(res.get("path") or "")
        if not rel:
            continue
        path_obj = pdir / rel
        try:
            width = res.get("width")
            height = res.get("height")
        except Exception:
            width = height = None
        figure_inputs.append({
            "figure_id": f"figure.{path_obj.stem}",
            "source_path": rel,
            "file_kind": path_obj.suffix.lower().lstrip(".") or "png",
            "width_px": width,
            "height_px": height,
            "nearby_context": path_obj.stem,
            "image_b64_or_url": "",   # Vision input plumbing TBD; Claude still gets filename + context
        })

    # 2d. Sheet inputs — Excel / CSV
    sheet_inputs: list[dict] = []
    for item in digest_items:
        item_type = str(item.get("type") or "")
        if item_type not in {"spreadsheet", "data"}:
            continue
        structured = item.get("structured") or {}
        sheets = []
        for s_idx, sheet in enumerate(structured.get("sheets") or [], start=1):
            if not isinstance(sheet, dict):
                continue
            rows = sheet.get("rows") or []
            sheets.append({
                "sheet_index": s_idx,
                "sheet_name": sheet.get("name") or f"Sheet{s_idx}",
                "headers": rows[0] if rows else [],
                "row_count": len(rows),
                "sample_rows": rows[1:7] if len(rows) > 1 else [],
            })
        if not sheets:
            continue
        sheet_inputs.append({
            "sheet_id": str(item.get("resource_id") or item.get("path") or "unknown"),
            "source_path": item.get("path"),
            "file_kind": item_type,
            "sheets": sheets,
        })

    # Fan out all four streams through one pool.
    if analyzer_inputs or doc_inputs or figure_inputs or sheet_inputs:
        print(
            f"[project-decompose] building units for {len(analyzer_inputs)} decks + "
            f"{len(doc_inputs)} docs + {len(figure_inputs)} figures + "
            f"{len(sheet_inputs)} sheets — reading pre-computed analyses from data/",
            flush=True,
        )

    # PPTX semantics: project_library.build_project_library has already merged
    # deck/section/slide briefs into the project_library deck output. decks /
    # sections / slide_units were populated from `data/ppt/` at the top of this
    # function, so no per-deck merge step is needed here.

    # ---- 3. Build doc / figure / sheet units (read pre-computed analyses) ----
    # P17: instead of calling library_analyzer at runtime, read per-format
    # Claude analyses written by project_analyzer.analyze_project_sources to
    # `data/<type>/<stem>.json`. Translates Chinese-keyed skill output into
    # English-keyed unit fields. Returns None for unanalyzed files — those
    # fields stay None until SOURCE_UNDERSTAND runs the analyzers and
    # scan_resources is invoked a second time.
    doc_units: list[dict] = []
    for inp in doc_inputs:
        did = str(inp.get("doc_id"))
        kind = str(inp.get("file_kind") or "")
        # pdf → data/pdf/<stem>.json; markdown/text/document → data/doc/<stem>.json
        type_dir = "pdf" if kind == "pdf" else "doc"
        zh = _read_precomputed_source_analysis(pdir, type_dir, inp.get("source_path"))
        r = _translate_doc_analysis(zh) if zh else {}
        doc_units.append({
            "doc_unit_id": did,
            "resource_id": did,
            "kind": "document",
            "source_path": inp.get("source_path"),
            "file_kind": inp.get("file_kind"),
            "page_count_or_size": inp.get("page_count_or_size"),
            "section_headings": inp.get("section_headings"),
            "topic": r.get("topic"),
            "doc_type": r.get("doc_type"),
            "language": r.get("language"),
            "key_claims": r.get("key_claims"),
            "anchor_terms": r.get("anchor_terms"),
            "section_summaries": r.get("section_summaries"),
            "reusable_quotes": r.get("reusable_quotes"),
            "applicable_chapters": r.get("applicable_chapters"),
            "cite_recommendation": r.get("cite_recommendation"),
            "semantic_ok": bool(zh),
            "source_owner": "project",
        })

    figure_units: list[dict] = []
    for inp in figure_inputs:
        fid = str(inp.get("figure_id"))
        zh = _read_precomputed_source_analysis(pdir, "image", inp.get("source_path"))
        r = _translate_figure_analysis(zh) if zh else {}
        figure_units.append({
            "figure_id": fid,
            "resource_id": fid,
            "source_path": inp.get("source_path"),
            "file_kind": inp.get("file_kind"),
            "what_it_shows": r.get("what_it_shows"),
            "figure_kind": r.get("figure_kind"),
            "evidence_kind": r.get("evidence_kind"),
            "key_elements": r.get("key_elements"),
            "anchor_terms": r.get("anchor_terms"),
            "applicable_chapters": r.get("applicable_chapters"),
            "best_used_for": r.get("best_used_for"),
            "reusability": r.get("reusability"),
            "do_not_reuse_when": r.get("do_not_reuse_when"),
            "caption_suggestion": r.get("caption_suggestion"),
            "semantic_ok": bool(zh),
            "source_owner": "project",
        })

    sheet_units: list[dict] = []
    for inp in sheet_inputs:
        sid = str(inp.get("sheet_id"))
        zh = _read_precomputed_source_analysis(pdir, "excel", inp.get("source_path"))
        r = _translate_sheet_analysis(zh) if zh else {}
        sheet_units.append({
            "sheet_id": sid,
            "resource_id": sid,
            "source_path": inp.get("source_path"),
            "file_kind": inp.get("file_kind"),
            "topic": r.get("topic"),
            "sheets": r.get("sheets"),
            "anchor_terms": r.get("anchor_terms"),
            "do_not_use_when": r.get("do_not_use_when"),
            "semantic_ok": bool(zh),
            "source_owner": "project",
        })

    summary["deck_count"] = len(decks)
    summary["section_count"] = len(sections)
    summary["slide_count"] = len(slide_units)
    summary["component_count"] = len(component_units)
    summary["asset_count"] = len(asset_units)
    summary["doc_unit_count"] = len(doc_units)
    summary["figure_unit_count"] = len(figure_units)
    summary["sheet_unit_count"] = len(sheet_units)

    # ---- 4. Write project-side artifacts (mirror library schema) ----------
    write_json(pdir / "project-deck-units.json", {
        "schema_version": "2.0",
        "generated_at": now(),
        "decks": decks,
    })
    write_json(pdir / "project-section-units.json", {
        "schema_version": "2.0",
        "generated_at": now(),
        "sections": sections,
    })
    write_json(pdir / "project-slide-units.json", {
        "schema_version": "2.0",
        "generated_at": now(),
        "decks": [{"deck_id": d.get("deck_id"), "deck_path": d.get("deck_path"),
                   "import_dir": d.get("import_dir"), "slide_count": d.get("slide_count")}
                  for d in decks],
        "slides": slide_units,
    })
    write_json(pdir / "project-component-units.json", {
        "schema_version": "1.0",
        "generated_at": now(),
        "components": component_units,
    })
    write_json(pdir / "project-asset-units.json", {
        "schema_version": "1.0",
        "generated_at": now(),
        "assets": asset_units,
    })
    write_json(pdir / "project-doc-units.json", {
        "schema_version": "2.0",
        "generated_at": now(),
        "doc_units": doc_units,
    })
    write_json(pdir / "project-figure-units.json", {
        "schema_version": "1.0",
        "generated_at": now(),
        "figures": figure_units,
    })
    write_json(pdir / "project-sheet-units.json", {
        "schema_version": "1.0",
        "generated_at": now(),
        "sheets": sheet_units,
    })
    return summary


def _chart_candidates_from_digest(digest: dict) -> dict:
    candidates = []
    for item in digest.get("items", []) if isinstance(digest, dict) else []:
        if item.get("type") not in {"spreadsheet", "data"}:
            continue
        structured = item.get("structured") or {}
        sheets = structured.get("sheets") or []
        for sheet in sheets:
            rows = sheet.get("rows") or []
            if len(rows) >= 2:
                candidates.append({
                    "resource_id": item.get("resource_id"),
                    "path": item.get("path"),
                    "sheet_index": sheet.get("index"),
                    "headers": rows[0],
                    "sample_rows": rows[1:6],
                    "suggested_chart_type": "bar_or_line",
                })
    return {"schema_version": "1.0", "generated_at": now(), "candidates": candidates}


def _image_dimensions(path: Path) -> tuple[int | None, int | None]:
    try:
        raw = path.read_bytes()[:64]
    except Exception:
        return None, None
    if raw.startswith(b"\x89PNG\r\n\x1a\n") and len(raw) >= 24:
        return int.from_bytes(raw[16:20], "big"), int.from_bytes(raw[20:24], "big")
    if raw[:3] == b"\xff\xd8":
        try:
            data = path.read_bytes()
        except Exception:
            return None, None
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
                return int.from_bytes(data[i + 7:i + 9], "big"), int.from_bytes(data[i + 5:i + 7], "big")
            if marker in {0xD8, 0xD9}:
                i += 2
                continue
            length = int.from_bytes(data[i + 2:i + 4], "big")
            i += 2 + max(length, 2)
    return None, None


def _asset_catalog_from_resources(resources: list[dict], pdir: Path | None = None) -> dict:
    assets = [
        {
            "resource_id": item.get("resource_id"),
            "path": item.get("path"),
            "type": item.get("type"),
            "asset_type": item.get("type"),
            "asset_origin": "project_sources",
            "visual_type": item.get("type"),
            "content_type": item.get("content_type"),
            "reusable_level": item.get("reusable_level"),
            "usage_role": "user_provided_image" if item.get("type") == "image" else item.get("type"),
            "reuse_policy": "direct_if_user_provided_and_relevant" if item.get("type") == "image" else "source",
            "approved": item.get("type") == "image",
        }
        for item in resources
        if item.get("type") in {"image", "video", "audio", "ppt_deck"}
        and not (
            item.get("type") == "image"
            and "_template_import/assets/" in str(item.get("path") or "")
        )
        and not (
            item.get("type") == "image"
            and "_template_import/svg" in str(item.get("path") or "")
        )
    ]
    if pdir is not None:
        assets.extend(_source_ppt_image_assets(pdir, resources))
        assets.extend(_source_ppt_slide_assets(pdir, resources))
    return {"schema_version": "1.1", "generated_at": now(), "assets": assets}


def _source_ppt_slide_assets(pdir: Path, resources: list[dict]) -> list[dict]:
    """Expose imported source PPT pages as auditable visual evidence candidates."""
    out: list[dict] = []
    seen: set[str] = set()
    for item in resources:
        if item.get("type") != "ppt_deck":
            continue
        rel = str(item.get("path") or "")
        if not rel.startswith("sources/"):
            continue
        path = pdir / rel
        import_dir = path.parent / f"{path.stem}_template_import"
        manifest_path = import_dir / "manifest.json"
        manifest = read_json(manifest_path, {}) if manifest_path.exists() else {}
        slides = manifest.get("slides") if isinstance(manifest, dict) else []
        if not isinstance(slides, list):
            continue
        for slide in slides:
            if not isinstance(slide, dict):
                continue
            slide_idx = int(slide.get("index") or 0)
            svg_name = slide.get("flatSvgFile") or slide.get("svgFile")
            if not svg_name:
                continue
            svg_rel = f"{path.parent.relative_to(pdir).as_posix()}/{path.stem}_template_import/svg-flat/{svg_name}"
            if not (pdir / svg_rel).exists():
                svg_rel = f"{path.parent.relative_to(pdir).as_posix()}/{path.stem}_template_import/svg/{svg_name}"
            if svg_rel in seen or not (pdir / svg_rel).exists():
                continue
            seen.add(svg_rel)
            samples = [str(x).strip() for x in (slide.get("textSamples") or []) if str(x).strip()]
            caption = " / ".join(samples[:6])
            shape_count = int(slide.get("shapeCount") or 0)
            image_count = len(slide.get("imageAssets") or [])
            text_count = int(slide.get("textCount") or len(samples))
            visual_type = "source_slide_with_images" if image_count else "source_slide_diagram" if shape_count >= 6 else "source_slide_text"
            out.append({
                "resource_id": f"{item.get('resource_id')}-slide-{slide_idx}",
                "path": svg_rel,
                "local_path": svg_rel,
                "type": "image",
                "asset_type": "source_slide_svg",
                "asset_origin": "project_sources",
                "visual_type": visual_type,
                "usage_role": "source_ppt_page",
                "content_type": "image/svg+xml",
                "reusable_level": "page",
                "reuse_policy": "direct_or_redraw_if_page_claim_matches",
                "approved": True,
                "source_priority": 2,
                "source_kind": "project_source_ppt",
                "source_deck": rel,
                "source_slide_index": slide_idx,
                "caption": caption or f"{path.stem} slide {slide_idx}",
                "title": samples[0] if samples else f"{path.stem} slide {slide_idx}",
                "text_context": samples[:12],
                "content_summary": caption or f"Full source PPT page imported from {rel} slide {slide_idx}",
                "original_context": {
                    "source_deck": rel,
                    "source_slide_index": slide_idx,
                    "text_samples": samples[:12],
                    "shape_count": shape_count,
                    "image_count": image_count,
                    "text_count": text_count,
                },
                "topic_tags": sorted({t for t in re.split(r"[\s,，/：:;；()（）\\-]+", caption) if len(t) >= 2})[:24],
                "shape_count": shape_count,
                "image_count": image_count,
                "text_count": text_count,
            })
    return out


def _source_ppt_image_assets(pdir: Path, resources: list[dict]) -> list[dict]:
    """Promote images extracted from project source PPTs into reusable evidence assets.

    `templates/topic/paper share` remains a style reference only. This scans only the
    project's own `sources/*_template_import` folders created by ppt-master.
    """
    out: list[dict] = []
    seen: set[str] = set()
    for item in resources:
        if item.get("type") != "ppt_deck":
            continue
        rel = str(item.get("path") or "")
        if not rel.startswith("sources/"):
            continue
        path = pdir / rel
        import_dir = path.parent / f"{path.stem}_template_import"
        manifest_path = import_dir / "manifest.json"
        manifest = read_json(manifest_path, {}) if manifest_path.exists() else {}
        slides = manifest.get("slides") if isinstance(manifest, dict) else []
        if not isinstance(slides, list):
            continue
        for slide in slides:
            if not isinstance(slide, dict):
                continue
            slide_idx = int(slide.get("index") or 0)
            samples = [str(x).strip() for x in (slide.get("textSamples") or []) if str(x).strip()]
            caption = " / ".join(samples[:5])
            for name in slide.get("imageAssets") or []:
                image_rel = f"{path.parent.relative_to(pdir).as_posix()}/{path.stem}_template_import/assets/{name}"
                if image_rel in seen:
                    continue
                img_path = pdir / image_rel
                if not img_path.exists() or img_path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
                    continue
                width, height = _image_dimensions(img_path)
                size = img_path.stat().st_size
                # Drop tiny logos and footer marks; evidence figures need real visual area.
                if size < 12_000 or (width and height and (width < 160 or height < 90)):
                    continue
                seen.add(image_rel)
                out.append({
                    "resource_id": f"{item.get('resource_id')}-s{slide_idx}-{Path(str(name)).stem}",
                    "path": image_rel,
                    "local_path": image_rel,
                    "type": "image",
                    "asset_type": "source_figure",
                    "asset_origin": "project_sources",
                    "visual_type": "source_figure",
                    "usage_role": "evidence_image",
                    "content_type": mimetypes.guess_type(str(img_path))[0] or "image/png",
                    "reusable_level": "asset",
                    "reuse_policy": "direct_if_relevant",
                    "approved": True,
                    "source_priority": 1,
                    "source_kind": "project_source_ppt",
                    "source_deck": rel,
                    "source_slide_index": slide_idx,
                    "caption": caption or f"{path.stem} slide {slide_idx}",
                    "title": samples[0] if samples else f"{path.stem} slide {slide_idx}",
                    "text_context": samples[:10],
                    "content_summary": caption or f"Image extracted from {rel} slide {slide_idx}",
                    "original_context": {
                        "source_deck": rel,
                        "source_slide_index": slide_idx,
                        "text_samples": samples[:10],
                    },
                    "topic_tags": sorted({t for t in re.split(r"[\s,，/：:;；()（）\\-]+", caption) if len(t) >= 2})[:18],
                    "width": width,
                    "height": height,
                    "size_bytes": size,
                })
    return out


def _ppt_visual_reference_index(pdir: Path, resources: list[dict]) -> dict:
    try:
        from scripts.lib import template_ingest
    except Exception:
        template_ingest = None
    exemplars = []
    scripts_dir = template_ingest.vendored_scripts_dir(ROOT) if template_ingest else None
    for item in resources:
        if item.get("type") != "ppt_deck":
            continue
        rel = str(item.get("path") or "")
        path = pdir / rel
        if not path.exists() or path.name.startswith(("~$", "~", ".")):
            continue
        import_dir = path.parent / f"{path.stem}_template_import"
        manifest_path = import_dir / "manifest.json"
        if template_ingest and scripts_dir and not manifest_path.exists():
            try:
                template_ingest.run_importer(path, import_dir, scripts_dir)
            except Exception:
                pass
        manifest = read_json(manifest_path, {}) if manifest_path.exists() else {}
        slides = manifest.get("slides") if isinstance(manifest, dict) else []
        if not isinstance(slides, list):
            slides = []
        for slide in slides[:30]:
            if not isinstance(slide, dict):
                continue
            idx = int(slide.get("index") or 0)
            shape_count = int(slide.get("shapeCount") or 0)
            text_count = int(slide.get("textCount") or 0)
            image_count = len(slide.get("imageAssets") or [])
            density = "high" if shape_count + text_count + image_count >= 14 else "medium" if shape_count + text_count + image_count >= 7 else "low"
            visual_role = "image_heavy" if image_count >= 2 else "diagram_like" if shape_count >= 8 else "text_light" if text_count <= 3 else "balanced"
            exemplars.append({
                "resource_id": item.get("resource_id"),
                "path": rel,
                "slide_index": idx,
                "role": slide.get("pageType") or "content_candidate",
                "template_svg": f"{path.parent.relative_to(pdir).as_posix()}/{path.stem}_template_import/svg-flat/{slide.get('flatSvgFile') or slide.get('svgFile')}" if slide.get("flatSvgFile") or slide.get("svgFile") else None,
                "shape_count": shape_count,
                "text_count": text_count,
                "image_count": image_count,
                "visual_density": density,
                "visual_role": visual_role,
                "text_samples": [str(x).strip() for x in (slide.get("textSamples") or []) if str(x).strip()][:8],
                "usage_policy": {
                    "style_only": True,
                    "copy_assets": False,
                    "copy_text": False,
                    "use_for": ["visual_density", "spatial_rhythm", "diagram_complexity", "image_need_judgement"],
                },
            })
    by_role: dict[str, int] = {}
    by_density: dict[str, int] = {}
    for item in exemplars:
        by_role[item["visual_role"]] = by_role.get(item["visual_role"], 0) + 1
        by_density[item["visual_density"]] = by_density.get(item["visual_density"], 0) + 1
    return {
        "schema_version": "1.0",
        "generated_at": now(),
        "source": "ppt_visual_reference_index",
        "exemplar_count": len(exemplars),
        "by_role": by_role,
        "by_density": by_density,
        "exemplars": exemplars[:80],
        "policy": "Use PPT references for visual rhythm and density only; do not copy original content assets unless explicitly approved.",
    }


def run_research(project_id: str, payload: dict | None = None) -> dict:
    payload = payload or {}
    pdir = project_dir(project_id)
    state = read_json(pdir / "app-state.json", {})
    if not state:
        raise FileNotFoundError(project_id)
    answers = state.get("answers") or {}
    topic = str(payload.get("topic") or answers.get("topic") or state.get("project_id") or project_id)
    if topic.strip().lower() == project_id.lower():
        plan = read_json(pdir / "model-routed-plan.json", {})
        slides = plan.get("slides") if isinstance(plan, dict) else []
        first_title = ""
        if isinstance(slides, list) and slides and isinstance(slides[0], dict):
            first_title = str(slides[0].get("title") or "").strip()
        if first_title:
            topic = first_title
    language = str(payload.get("language") or answers.get("language") or "zh")
    depth = str(payload.get("research_depth") or answers.get("research_depth") or "light")
    adapter = providers.adapter_commands("research")
    search_cmd = payload.get("search_cmd")
    fetch_cmd = payload.get("fetch_cmd")
    if payload.get("use_legacy_adapter"):
        search_cmd = search_cmd or adapter.get("search_cmd")
        fetch_cmd = fetch_cmd or adapter.get("fetch_cmd")
    result = research.search(
        pdir,
        topic=topic,
        language=language,
        depth=depth,
        search_cmd=search_cmd,
    )
    existing_audit = read_json(pdir / "research-audit.json", {})
    if (
        int(result.get("web_results_count") or 0) == 0
        and int(existing_audit.get("web_results_count") or 0) > 0
        and not payload.get("force_overwrite_failed_research")
    ):
        warnings = list(result.get("warnings") or [])
        warnings.append("new web research returned no usable sources; preserved existing web research artifacts")
        return {
            "project_id": project_id,
            "preserved_existing": True,
            "queries": result.get("queries", []),
            "warnings": warnings,
            "citations": read_json(pdir / "citations.json", {}).get("citations", []),
        }
    artifact_info = research.write_artifacts(
        pdir,
        topic=topic,
        language=language,
        research=result,
        fetch_cmd=fetch_cmd,
    )
    state["last_research"] = {
        "finished_at": now(),
        "provider": "tool_router",
        "result_count": len(result.get("results", [])),
        "warnings": result.get("warnings", []),
    }
    state["updated_at"] = now()
    write_json(pdir / "app-state.json", state)
    return {"project_id": project_id, **result, **artifact_info}


def _fm_value(path: Path, key: str) -> str | None:
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.startswith(f"{key}:"):
            return line.split(":", 1)[1].strip().strip('"')
    return None


def quality(project_id: str) -> dict:
    pdir = project_dir(project_id)
    sv = pdir / "structural-validation.md"
    rm = read_json(pdir / "run-manifest.json", {})
    return {
        "deck_quality_pass": _fm_value(sv, "deck_quality_pass"),
        "render_mode": _fm_value(sv, "render_mode"),
        "aggregate_editable_ratio": _fm_value(sv, "aggregate_editable_ratio"),
        "speaker_notes_ok": _fm_value(sv, "speaker_notes_ok"),
        "transitions_ok": _fm_value(sv, "transitions_ok"),
        "assets_ok": _fm_value(sv, "assets_ok"),
        "deck_path": str(pdir / "deck.pptx") if (pdir / "deck.pptx").exists() else None,
        "manifest": rm,
    }


def render_audit(project_id: str) -> dict:
    pdir = project_dir(project_id)
    scan = _svg_visual_scan(pdir)
    visual_plan = read_json(pdir / "visual-plan.json", {})
    visual_slides = visual_plan.get("slides") if isinstance(visual_plan, dict) else []
    outline = read_json(pdir / "reuse-first-outline.json", {})
    expected_source_paths = {
        str((slide.get("selected_reuse") or {}).get("path") or "").strip()
        for slide in outline.get("slides", []) if isinstance(slide, dict) and isinstance(slide.get("selected_reuse"), dict)
    }
    expected_source_paths = {path for path in expected_source_paths if path}
    bound_source_paths: set[str] = set()
    layout_counts: dict[str, int] = {}
    visual_kind_counts: dict[str, int] = {}
    for item in visual_slides or []:
        if not isinstance(item, dict):
            continue
        layout = str(item.get("layout_variation") or item.get("layout_family") or item.get("layout_type") or "unknown")
        layout_counts[layout] = layout_counts.get(layout, 0) + 1
        spec = item.get("visual_spec") if isinstance(item.get("visual_spec"), dict) else {}
        kind = str(spec.get("kind") or item.get("visual_type") or "unknown")
        visual_kind_counts[kind] = visual_kind_counts.get(kind, 0) + 1
        for asset in item.get("assets") or []:
            if not isinstance(asset, dict):
                continue
            path = str(asset.get("staged_from") or asset.get("local_path") or asset.get("path") or "").strip()
            if path:
                bound_source_paths.add(path)
    issues = list(scan.get("issues") or [])
    missing_bound_sources = sorted(expected_source_paths - bound_source_paths)
    for path in missing_bound_sources[:12]:
        issues.append({"slide": None, "reason": "selected source asset missing from final visual plan", "path": path})
    slide_count = int(scan.get("slide_count") or 0)
    if slide_count >= 6:
        for layout, count in layout_counts.items():
            if layout and count > max(3, slide_count // 2):
                issues.append({"slide": None, "reason": "rendered deck is visually repetitive", "layout": layout, "count": count})
        box_like = sum(count for kind, count in visual_kind_counts.items() if kind in {"cards", "bullets", "evidence-two-box"})
        if box_like / max(1, slide_count) > 0.55:
            issues.append({"slide": None, "reason": "too many rendered slides rely on box/card-like structures", "box_like_count": box_like})
    audit = {
        "schema_version": "1.0",
        "generated_at": now(),
        "source": "svg_render_readback",
        "pass": not issues,
        "issues": issues,
        "svg_scan": scan,
        "layout_counts": layout_counts,
        "visual_kind_counts": visual_kind_counts,
        "expected_source_asset_count": len(expected_source_paths),
        "bound_source_asset_count": len(expected_source_paths & bound_source_paths),
        "missing_bound_sources": missing_bound_sources[:40],
    }
    write_json(pdir / "render-audit.json", audit)
    return audit


def downloads(project_id: str) -> dict:
    pdir = project_dir(project_id)
    candidates = {
        "deck": pdir / "deck.pptx",
        "research": pdir / "research.md",
        "citations": pdir / "citations.json",
        "manifest": pdir / "run-manifest.json",
        "model_plan": pdir / "model-routed-plan.json",
        "slide_state": pdir / "slide-state.json",
        "review_report": pdir / "review-report.json",
        "content_quality": pdir / "content-quality-report.json",
        "render_audit": pdir / "render-audit.json",
        "final_report": pdir / "final-report.json",
        "codex_debug": pdir / "devops/codex-debug-report.md",
    }
    return {
        name: f"/api/projects/{project_id}/files/{path.name}"
        for name, path in candidates.items()
        if path.exists()
    }


def _frontmatter_value(path: Path, key: str) -> str | None:
    return _fm_value(path, key)


def _svg_visual_scan(pdir: Path) -> dict:
    svg_dir = pdir / "svg_build" / "svg_output"
    if not svg_dir.exists():
        svg_dir = pdir / "svg_output"
    visual_plan = read_json(pdir / "visual-plan.json", {})
    visual_by_slide = {
        int(item.get("slide_index") or 0): item
        for item in (visual_plan.get("slides") if isinstance(visual_plan, dict) else []) or []
        if isinstance(item, dict) and str(item.get("slide_index") or "").isdigit()
    }
    issues = []
    slide_reports = []
    placeholder_re = re.compile(r"Content Placeholder|Title 1|个人介绍|教育经历|stroke-dasharray", re.I)
    visual_re = re.compile(
        r'id="(?:visual-|blueprint-composition|content-blocks-panel|component-evidence-two-box|content-title|cover-title|ending-title|lab-template-footer|lab-cover-metadata|lab-ending-metadata)',
        re.I,
    )
    content_title_sizes = []

    def _floats(pattern: str, text: str) -> list[float]:
        vals = []
        for m in re.finditer(pattern, text):
            try:
                vals.append(float(m.group(1)))
            except (TypeError, ValueError):
                pass
        return vals

    def _content_bbox_fill(text: str, width: float, height: float) -> float:
        xs: list[float] = []
        ys: list[float] = []
        for m in re.finditer(r"<(?:rect|image)\b[^>]*>", text):
            tag = m.group(0)
            vals = {}
            for key in ("x", "y", "width", "height"):
                mm = re.search(rf'{key}="(-?\d+(?:\.\d+)?)"', tag)
                if mm:
                    vals[key] = float(mm.group(1))
            if {"x", "y", "width", "height"} <= set(vals) and 70 <= vals["y"] <= height - 42:
                xs.extend([vals["x"], vals["x"] + vals["width"]])
                ys.extend([vals["y"], vals["y"] + vals["height"]])
        for m in re.finditer(r"<text\b[^>]*>", text):
            tag = m.group(0)
            mx = re.search(r'x="(-?\d+(?:\.\d+)?)"', tag)
            my = re.search(r'y="(-?\d+(?:\.\d+)?)"', tag)
            ms = re.search(r'font-size="(\d+(?:\.\d+)?)"', tag)
            if not (mx and my):
                continue
            x = float(mx.group(1))
            y = float(my.group(1))
            size = float(ms.group(1)) if ms else 16.0
            if 70 <= y <= height - 42:
                xs.extend([x, min(width, x + size * 12)])
                ys.extend([max(70, y - size), y + size * 0.35])
        if not xs or not ys:
            return 0.0
        bbox_area = max(0.0, max(xs) - min(xs)) * max(0.0, max(ys) - min(ys))
        content_area = width * max(1.0, height - 112.0)
        return round(min(1.0, bbox_area / content_area), 3)

    def _visible_svg_text(svg_text: str) -> str:
        values = re.findall(r"<text\b[^>]*>(.*?)</text>", svg_text, flags=re.S)
        cleaned = []
        for value in values:
            value = re.sub(r"<[^>]+>", "", value)
            value = value.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
            cleaned.append(value)
        return "\n".join(cleaned)

    for svg_path in sorted(svg_dir.glob("slide_*.svg")) if svg_dir.exists() else []:
        text = svg_path.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r"slide_(\d+)\.svg$", svg_path.name)
        idx = int(m.group(1)) if m else len(slide_reports) + 1
        visual_item = visual_by_slide.get(idx, {})
        page_type = str(visual_item.get("template_page_type") or "").lower()
        layout_type = str(visual_item.get("layout_type") or "").lower()
        visual_type = str(visual_item.get("visual_type") or "").lower()
        is_edge_page = (
            page_type in {"cover", "ending"}
            or layout_type in {"cover", "ending", "closing", "title-image"}
            or (idx == 1 and visual_type == "image-and-bullets")
        )
        text_count = len(re.findall(r"<text\b", text))
        rect_count = len(re.findall(r"<rect\b", text))
        has_visual = bool(visual_re.search(text))
        has_content_blocks = 'id="content-blocks-panel"' in text
        has_blueprint = 'id="blueprint-composition"' in text or 'id="content-blocks-panel"' in text
        has_placeholder = bool(placeholder_re.search(text))
        width_vals = _floats(r'<svg\b[^>]*\bwidth="(\d+(?:\.\d+)?)"', text)
        height_vals = _floats(r'<svg\b[^>]*\bheight="(\d+(?:\.\d+)?)"', text)
        canvas_w = width_vals[0] if width_vals else 960.0
        canvas_h = height_vals[0] if height_vals else 540.0
        title_group = re.search(r'<g id="content-title">([\s\S]*?)</g>', text)
        title_sizes = _floats(r'font-size="(\d+(?:\.\d+)?)"', title_group.group(1) if title_group else "")
        if title_sizes and not is_edge_page:
            content_title_sizes.append({"slide": idx, "font_size": title_sizes[0]})
        fill_ratio = _content_bbox_fill(text, canvas_w, canvas_h)
        visible_text = _visible_svg_text(text)
        try:
            fill_target = float((visual_item.get("quality_requirements") or {}).get("content_fill_target") or visual_item.get("content_fill_target") or 0.58)
        except (TypeError, ValueError):
            fill_target = 0.58
        if has_placeholder:
            issues.append({"slide": idx, "reason": "placeholder or dashed template artifact remains in SVG"})
        if re.search(r"依据\s*S\d+|\bS\d+\b|Sources:", visible_text):
            issues.append({"slide": idx, "reason": "visible citation leak: S ids or Sources footer appear in rendered SVG"})
        if "..." in visible_text or "…" in visible_text:
            issues.append({"slide": idx, "reason": "visible ellipsis suggests copy was truncated instead of rewritten"})
        if idx > 1 and text_count < 3:
            issues.append({"slide": idx, "reason": "too few editable text elements in rendered SVG"})
        if idx > 1 and not has_visual:
            issues.append({"slide": idx, "reason": "no recognizable editable visual/content group in SVG"})
        planned_blocks = visual_item.get("content_blocks") if isinstance(visual_item.get("content_blocks"), list) else []
        if idx > 1 and planned_blocks and not has_content_blocks:
            if is_edge_page or ((page_type == "agenda" or layout_type == "agenda" or idx == 2) and has_blueprint):
                pass
            else:
                issues.append({"slide": idx, "reason": "visual-plan content_blocks were not rendered into the SVG"})
        blueprint = visual_item.get("layout_blueprint") if isinstance(visual_item.get("layout_blueprint"), dict) else {}
        if idx > 1 and not is_edge_page and blueprint and not has_blueprint:
            issues.append({"slide": idx, "reason": "layout_blueprint did not leave a recognizable rendered composition"})
        min_fill_ratio = min(fill_target, max(0.34, fill_target - 0.22))
        if not is_edge_page and fill_ratio < min_fill_ratio:
            issues.append({
                "slide": idx,
                "reason": "content occupancy is below the planned fill target; slide likely has too much blank space",
                "content_fill_ratio": fill_ratio,
                "content_fill_target": round(fill_target, 3),
            })
        asset_request = visual_item.get("asset_request") if isinstance(visual_item.get("asset_request"), dict) else {}
        if (asset_request.get("needs_visual_asset") or asset_request.get("needs_generated_image")) and not visual_item.get("assets"):
            issues.append({"slide": idx, "reason": "model requested a visual/image asset but no image asset was bound"})
        slide_reports.append({
            "slide": idx,
            "text_count": text_count,
            "rect_count": rect_count,
            "has_visual_group": has_visual,
            "has_content_blocks": has_content_blocks,
            "has_blueprint_composition": has_blueprint,
            "placeholder_detected": has_placeholder,
            "content_fill_ratio": fill_ratio,
            "content_fill_target": round(fill_target, 3),
            "title_font_size": title_sizes[0] if title_sizes else None,
        })
    if content_title_sizes:
        sizes = [item["font_size"] for item in content_title_sizes]
        if max(sizes) - min(sizes) > 2.0:
            issues.append({
                "slide": None,
                "reason": "content slide title font sizes are inconsistent",
                "min_font_size": min(sizes),
                "max_font_size": max(sizes),
                "slides": content_title_sizes,
            })
    return {
        "svg_dir": str(svg_dir) if svg_dir.exists() else None,
        "slide_count": len(slide_reports),
        "issues": issues,
        "slides": slide_reports,
        "content_title_font_sizes": content_title_sizes,
        "pass": not issues,
    }


def _content_quality_report(project_id: str) -> dict:
    pdir = project_dir(project_id)
    ts = now()
    plan = read_json(pdir / "model-routed-plan.json", {})
    visual = read_json(pdir / "visual-plan.json", {})
    research_results = read_json(pdir / "research-results.json", {})
    citations = read_json(pdir / "citations.json", {}).get("citations", [])
    source_digest = read_json(pdir / "project-source-digest.json", {})
    manuscript = (pdir / "manuscript.md").read_text(encoding="utf-8", errors="ignore") if (pdir / "manuscript.md").exists() else ""
    manuscript_meta: dict[int, dict] = {}
    for match in re.finditer(r"(?ms)^## Slide\s+(\d+):.*?(?=^---\s*$|^## Slide\s+\d+:|\Z)", manuscript):
        idx = int(match.group(1))
        chunk = match.group(0)
        meta = {}
        for key, pattern in {
            "covered_blocks": r"^Covered blocks:\s*(.+)$",
            "used_sources": r"^Used sources:\s*(.+)$",
            "source_map": r"^Source map:\s*(.+)$",
        }.items():
            m = re.search(pattern, chunk, flags=re.MULTILINE)
            meta[key] = m.group(1).strip() if m else ""
        manuscript_meta[idx] = meta

    visual_by_slide = {
        int(item.get("slide_index") or 0): item
        for item in visual.get("slides", [])
        if isinstance(item, dict) and int(item.get("slide_index") or 0) > 0
    }
    citation_ids = {str(item.get("id")) for item in citations if isinstance(item, dict)}
    citation_by_id = {
        str(item.get("id")): item
        for item in citations
        if isinstance(item, dict) and item.get("id")
    }
    local_source_items = [
        item for item in (source_digest.get("items", []) if isinstance(source_digest, dict) else [])
        if isinstance(item, dict)
        and str(item.get("path") or "").startswith("sources/")
        and item.get("type") in {"document", "spreadsheet", "data", "mindmap", "text", "ppt_deck"}
    ]
    local_ref_by_token: dict[str, dict] = {}
    for item in local_source_items:
        for token in (item.get("resource_id"), item.get("path")):
            token = str(token or "").strip()
            if token:
                local_ref_by_token[token] = item
    slides = []
    unmet_visual = []
    citation_gaps = []
    weak_reference_slides = []
    component_gaps = []
    footer_gaps = []
    repetition_gaps = []
    duplicate_gaps = []
    layout_sequence_gaps = []
    format_reference_gaps = []
    layout_counts: dict[str, int] = {}
    format_decision_counts: dict[str, int] = {}
    seen_titles: dict[str, int] = {}
    seen_claims: dict[str, int] = {}
    recent_layouts: list[str] = []
    source_binding_gaps = []
    component_overuse_gaps = []
    component_counts: dict[str, int] = {}
    semantic_component_gaps = []
    semantic_component_counts: dict[str, int] = {}
    semantic_family_counts: dict[str, int] = {}
    visual_spec_gaps = []
    visual_composition_gaps = []
    blueprint_gaps = []
    composition_coverage_gaps = []
    asset_binding_gaps = []
    slide_composition_gaps = []
    claim_gaps = []
    text_density_gaps = []
    local_sources_used: dict[str, dict] = {}
    citation_sources_used: set[str] = set()
    plan_fallback_risk = bool(plan.get("fallback_used"))
    plan_slide_total = len(plan.get("slides") or []) if isinstance(plan.get("slides"), list) else 0
    for slide in plan.get("slides", []) if isinstance(plan.get("slides"), list) else []:
        idx = int(slide.get("index") or len(slides) + 1)
        is_edge_page = idx == 1 or (plan_slide_total and idx == plan_slide_total)
        visual_item = visual_by_slide.get(idx, {})
        contract = slide.get("layout_contract") if isinstance(slide.get("layout_contract"), dict) else {}
        contract_component = str(contract.get("component_id") or "").strip()
        expected_visual = str(visual_item.get("visual_type") or slide.get("visual_type") or "bullets").lower()
        slide_layout_type = str(slide.get("layout_type") or "").lower()
        visual_spec = visual_item.get("visual_spec") if isinstance(visual_item.get("visual_spec"), dict) else {}
        spec_kind = str(visual_spec.get("kind") or "").lower()
        if contract_component == "evidence_two_box.v1" or expected_visual == "evidence-two-box":
            expected_visual = "evidence-two-box"
        elif slide_layout_type in {"evidence-matrix", "comparison-matrix", "risk-boundary-table", "gap-matrix", "experiment-result"}:
            expected_visual = "table"
        elif slide_layout_type in {"layered-architecture", "process-flow", "roadmap", "assertion-evidence"}:
            expected_visual = "diagram"
        elif slide_layout_type == "problem-framing":
            expected_visual = "table" if spec_kind in {"matrix", "table", "risk_table"} else "diagram"
        elif contract_component == "evidence_two_box.v1" and slide_layout_type in {"", "evidence-two-box"}:
            expected_visual = "evidence-two-box"
        elements = [str(item).lower() for item in visual_item.get("editable_elements") or []]
        actual_layout = str(visual_item.get("layout_type") or "").lower()
        actual_visual = str(visual_item.get("visual_type") or actual_layout or "unknown").lower()
        spec_usable = layout_registry.visual_spec_is_usable(visual_spec)
        content_blocks = visual_item.get("content_blocks") if isinstance(visual_item.get("content_blocks"), list) else []
        usable_content_blocks = [
            item for item in content_blocks
            if isinstance(item, dict) and (str(item.get("heading") or "").strip() or item.get("body"))
        ]
        content_block_roles = {
            str(item.get("role") or "").strip().lower()
            for item in usable_content_blocks
            if str(item.get("role") or "").strip()
        }
        slide_composition = visual_item.get("slide_composition") if isinstance(visual_item.get("slide_composition"), dict) else {}
        layout_blueprint = visual_item.get("layout_blueprint") if isinstance(visual_item.get("layout_blueprint"), dict) else {}
        visual_layout_type = str(visual_item.get("layout_type") or slide_layout_type).lower()
        has_bound_assets = bool(visual_item.get("assets"))
        requires_spec = False if expected_visual == "evidence-two-box" or has_bound_assets else layout_registry.requires_visual_spec_for_slide(slide, slide_index=idx, slide_count=plan_slide_total)
        visual_ok = True
        if is_edge_page:
            visual_ok = True
        elif expected_visual == "diagram":
            visual_ok = has_bound_assets or spec_usable or "diagram" in elements or "diagram" in actual_layout or spec_kind in {"flow", "architecture", "roadmap", "timeline", "matrix", "cards"}
        elif expected_visual == "table":
            visual_ok = has_bound_assets or "table" in elements or spec_kind in {"table", "matrix", "risk_table", "bar_chart", "line_chart"} or re.search(r"(?m)^\|.+\|$", manuscript) is not None
        elif expected_visual in {"image-and-bullets", "image-evidence"} or "source-" in actual_layout:
            visual_ok = has_bound_assets or bool(usable_content_blocks)
        elif expected_visual == "evidence-two-box":
            visual_ok = bool(usable_content_blocks) or (
                str(visual_item.get("component_id") or "") == "evidence_two_box.v1"
                and all(key in elements for key in ["claim", "left_box", "right_box", "footer_citation"])
            )
        if requires_spec and not spec_usable:
            visual_spec_gaps.append({
                "slide": idx,
                "layout_type": slide.get("layout_type"),
                "visual_spec_kind": spec_kind or None,
                "reason": "layout_type requires a usable visual_spec with structured data/nodes",
            })
        has_v2_composition = bool(slide_composition.get("primary_visual_role") or usable_content_blocks or spec_usable)
        if not is_edge_page:
            if layout_blueprint and (
                not layout_blueprint.get("primary_visual")
                or not (layout_blueprint.get("analysis_panel") or layout_blueprint.get("evidence_callouts"))
            ):
                blueprint_gaps.append({
                    "slide": idx,
                    "reason": "layout_blueprint does not define primary visual plus analysis/evidence region",
                    "layout_blueprint_keys": sorted(layout_blueprint.keys()),
                })
            semantic_for_min_blocks = str(visual_item.get("semantic_component_id") or slide.get("semantic_component_id") or "")
            is_agenda_page = semantic_for_min_blocks == "research_agenda.v1"
            if (
                (not is_agenda_page and (not slide_composition.get("claim_to_prove") or not slide_composition.get("evidence_need")))
                or not slide_composition.get("primary_visual_role")
            ):
                slide_composition_gaps.append({
                    "slide": idx,
                    "reason": "missing slide_composition claim/evidence/primary_visual_role",
                })
            min_blocks = 1 if is_agenda_page else 3
            if len(usable_content_blocks) < min_blocks:
                visual_composition_gaps.append({
                    "slide": idx,
                    "reason": "technical content slide has too few content_blocks for a composed research page",
                    "content_block_count": len(usable_content_blocks),
                    "expected_min": min_blocks,
                })
            if min_blocks >= 3 and len(content_block_roles) < 3:
                visual_composition_gaps.append({
                    "slide": idx,
                    "reason": "content_blocks do not cover enough reasoning roles",
                    "roles": sorted(content_block_roles),
                    "expected": ["mechanism", "evidence", "implication/boundary"],
                })
            required_roles = {
                str(role).strip().lower()
                for role in (slide_composition.get("required_blocks") or [])
                if str(role).strip()
            }
            manuscript_roles = {
                token.strip().lower()
                for token in re.split(r"[,，;；]\s*", (manuscript_meta.get(idx, {}) or {}).get("covered_blocks", ""))
                if token.strip() and token.strip().lower() != "missing"
            }
            missing_visual_roles = sorted(role for role in required_roles if role not in content_block_roles)
            missing_copy_roles = sorted(role for role in required_roles if role not in manuscript_roles)
            if len(required_roles) >= 3 and (missing_visual_roles or missing_copy_roles):
                composition_coverage_gaps.append({
                    "slide": idx,
                    "reason": "composition required_blocks are not fully covered by visual content blocks and slide copy",
                    "required_blocks": sorted(required_roles),
                    "missing_visual_roles": missing_visual_roles,
                    "missing_copy_roles": missing_copy_roles,
                })
            meta = manuscript_meta.get(idx, {})
            has_source_lineage = bool(slide.get("source_lineage") or visual_item.get("source_lineage") or visual_item.get("reuse_decisions") or visual_item.get("assets"))
            if not has_source_lineage and (not meta.get("used_sources") or meta.get("used_sources") == "missing" or not meta.get("source_map") or meta.get("source_map") == "missing"):
                composition_coverage_gaps.append({
                    "slide": idx,
                    "reason": "slide copy lacks used_sources/source_map metadata and V2 source_lineage for traceable evidence use",
                })
            if spec_kind in {"bar_chart", "line_chart"}:
                data = visual_spec.get("data") if isinstance(visual_spec.get("data"), dict) else {}
                if data.get("synthetic_structure") is True:
                    visual_composition_gaps.append({
                        "slide": idx,
                        "reason": "chart is a synthetic structure chart, not evidence-backed quantitative data",
                        "visual_spec_kind": spec_kind,
                    })
        asset_request = visual_item.get("asset_request") if isinstance(visual_item.get("asset_request"), dict) else {}
        if (asset_request.get("needs_visual_asset") or asset_request.get("needs_generated_image")) and not visual_item.get("assets"):
            asset_binding_gaps.append({
                "slide": idx,
                "reason": "image requested but no asset is bound",
                "status": asset_request.get("status") or "unknown",
                "provider": asset_request.get("provider") or ("image2" if asset_request.get("needs_generated_image") else "asset_catalog"),
            })
        refs = [str(item) for item in slide.get("source_references") or []]
        citations_for_slide = [str(item) for item in (slide.get("citations") or refs)]
        nested_refs = []
        for box_key in ("left_box", "right_box"):
            box = slide.get(box_key) if isinstance(slide.get(box_key), dict) else {}
            nested_refs.extend(str(item) for item in box.get("source_references") or [])
        chart = slide.get("chart_spec") if isinstance(slide.get("chart_spec"), dict) else {}
        chart_source = str(chart.get("data_source") or "").strip()
        image_asset = str(slide.get("image_asset") or "").strip()
        source_tokens = [
            str(item).strip()
            for item in [*refs, *citations_for_slide, *nested_refs, chart_source, image_asset]
            if str(item).strip()
        ]
        slide_citation_refs = [token for token in source_tokens if token in citation_ids]
        slide_local_refs = []
        for token in source_tokens:
            matched = local_ref_by_token.get(token)
            if not matched:
                matched = next(
                    (
                        item for key, item in local_ref_by_token.items()
                        if key and (key in token or token in key)
                    ),
                    None,
                )
            if matched:
                ref_key = str(matched.get("path") or matched.get("resource_id"))
                if ref_key not in {str(x.get("path") or x.get("resource_id")) for x in slide_local_refs}:
                    slide_local_refs.append(matched)
                    local_sources_used[ref_key] = matched
        citation_sources_used.update(slide_citation_refs)
        if idx != 1 and local_source_items and not slide_local_refs and not slide_citation_refs:
            source_binding_gaps.append({
                "slide": idx,
                "reason": "content slide has no citation or local source binding",
                "title": slide.get("title"),
            })
        local_ref_keys = {
            str(item.get("path") or item.get("resource_id") or "")
            for item in slide_local_refs
            if isinstance(item, dict)
        }
        missing_refs = [
            ref for ref in refs
            if ref
            and ref not in citation_ids
            and ref not in local_ref_keys
            and not any(key and (key in ref or ref in key) for key in local_ref_keys)
        ]
        weak_refs = [
            ref for ref in refs
            if ref in citation_by_id
            and citation_by_id[ref].get("evidence_tier") != "full_text"
        ]
        if not visual_ok:
            unmet_visual.append(idx)
        if missing_refs:
            citation_gaps.append({"slide": idx, "missing_refs": missing_refs})
        if weak_refs:
            weak_reference_slides.append({
                "slide": idx,
                "weak_refs": weak_refs,
                "reason": "referenced source is snippet-only or otherwise not full-text supported",
            })
        component_id = visual_item.get("component_id")
        component_id_str = str(component_id or "")
        if component_id_str:
            component_counts[component_id_str] = component_counts.get(component_id_str, 0) + 1
        semantic_component_id = str(visual_item.get("semantic_component_id") or slide.get("semantic_component_id") or "").strip()
        if not is_edge_page and not has_v2_composition:
            if not semantic_component_id or not layout_registry.semantic_component_entry(semantic_component_id):
                semantic_component_gaps.append({
                    "slide": idx,
                    "reason": "missing or unknown semantic_component_id",
                    "semantic_component_id": semantic_component_id,
                })
            else:
                semantic_component_counts[semantic_component_id] = semantic_component_counts.get(semantic_component_id, 0) + 1
                family = str(visual_item.get("layout_family") or slide.get("layout_family") or layout_registry.semantic_component_entry(semantic_component_id).get("layout_family") or "")
                if family:
                    semantic_family_counts[family] = semantic_family_counts.get(family, 0) + 1
            reuse_level = str(visual_item.get("reuse_level") or slide.get("reuse_level") or "").strip()
            if reuse_level not in {"locked", "style_strategy", "layout_family", "component_pattern"}:
                semantic_component_gaps.append({"slide": idx, "reason": "missing or invalid reuse_level", "reuse_level": reuse_level})
            base_lock = visual_item.get("base_lock") or slide.get("base_lock")
            if not isinstance(base_lock, list) or not base_lock:
                semantic_component_gaps.append({"slide": idx, "reason": "missing base_lock list"})
            paper_share_influence = str(visual_item.get("paper_share_influence") or slide.get("paper_share_influence") or "").strip()
            if not paper_share_influence:
                semantic_component_gaps.append({"slide": idx, "reason": "missing paper_share_influence"})
        base_asset_copy_allowed = is_edge_page and component_id in {"dai_lab_cover.v1", "dai_lab_ending.v1"}
        if contract.get("copy_assets") is True and not base_asset_copy_allowed:
            component_gaps.append({"slide": idx, "component_id": component_id, "reason": "layout_contract.copy_assets=true; templates should be style/layout references unless explicitly approved"})
            semantic_component_gaps.append({"slide": idx, "reason": "copy_assets=true violates paper-share style-only policy"})
        expected_component = contract_component or (layout_registry.component_for_layout(slide_layout_type, idx, plan_slide_total) if slide_layout_type else None)
        if is_edge_page and component_id in {"dai_lab_cover.v1", "dai_lab_ending.v1"}:
            expected_component = component_id
        if expected_component and component_id != expected_component:
            component_gaps.append({
                "slide": idx,
                "component_id": component_id,
                "expected_component_id": expected_component,
                "layout_type": slide.get("layout_type"),
                "reason": "visual-plan component does not match layout_type",
            })
        format_reference = slide.get("format_reference") if isinstance(slide.get("format_reference"), dict) else {}
        format_mode = str(format_reference.get("mode") or visual_item.get("format_decision") or "").strip().lower()
        format_decision_counts[format_mode or "missing"] = format_decision_counts.get(format_mode or "missing", 0) + 1
        if idx != 1 and not format_reference and not has_v2_composition:
            format_reference_gaps.append({"slide": idx, "reason": "missing format_reference decision"})
        if format_mode == "use" and not str(format_reference.get("decision_reason") or "").strip():
            format_reference_gaps.append({"slide": idx, "reason": "format_reference.mode=use requires a decision_reason"})
        if idx != 1 and contract.get("format_locked") is True and not component_id:
            format_reference_gaps.append({"slide": idx, "reason": "format_locked=true without an explicit component_id"})
        if idx != 1 and contract.get("format_locked") is True and contract.get("renderer_may_adapt") is False:
            format_reference_gaps.append({"slide": idx, "reason": "format is fully locked; allow adaptation unless explicitly required by user"})
        if citations_for_slide and not is_edge_page:
            marker = re.sub(r"^S(\d+)$", r"[\1]", str(citations_for_slide[0]))
            svg_candidates = [
                pdir / "svg_build" / "svg_output" / f"slide_{idx:02d}.svg",
                pdir / "svg_output" / f"slide_{idx:02d}.svg",
            ]
            svg_text = ""
            for svg_path in svg_candidates:
                if svg_path.exists():
                    svg_text = svg_path.read_text(encoding="utf-8", errors="ignore")
                    break
            if marker not in svg_text and not re.search(rf"Footer citations:\s*.*{re.escape(str(citations_for_slide[0]))}", manuscript):
                footer_gaps.append({"slide": idx, "missing_footer_reference": citations_for_slide[0]})
        claim = str(slide.get("claim") or slide.get("key_message") or "").strip()
        if idx != 1 and idx != plan_slide_total and len(re.sub(r"\s+", "", claim)) < 8:
            claim_gaps.append({"slide": idx, "reason": "content slide lacks a concrete claim/key_message", "title": slide.get("title")})
        limits = layout_registry.copy_limits(slide_layout_type)
        title_len = len(re.sub(r"\s+", "", str(slide.get("title") or "")))
        claim_len = len(re.sub(r"\s+", "", claim))
        max_title = int(limits.get("title_chars") or 28)
        max_claim = int(limits.get("claim_chars") or 48)
        bullet_values = []
        bullet_values.extend(str(x) for x in (slide.get("bullets") or []) if str(x).strip())
        for box_key in ("left_box", "right_box"):
            box = slide.get(box_key) if isinstance(slide.get(box_key), dict) else {}
            body = box.get("body") or []
            if isinstance(body, str):
                body = [body]
            bullet_values.extend(str(x) for x in body if str(x).strip())
        long_items = [x for x in bullet_values if len(re.sub(r"\s+", "", x)) > int(limits.get("bullet_chars") or limits.get("node_chars") or limits.get("cell_chars") or 28) + 8]
        if title_len > max_title + 8 or claim_len > max_claim + 12 or long_items:
            text_density_gaps.append({
                "slide": idx,
                "title_chars": title_len,
                "claim_chars": claim_len,
                "long_item_count": len(long_items),
                "reason": "copy exceeds layout text limits and may overflow",
            })
        title_key = re.sub(r"\s+", "", str(slide.get("title") or "").strip().lower())
        claim_key = re.sub(r"\s+", "", claim.lower())
        if title_key:
            if title_key in seen_titles:
                duplicate_gaps.append({"slide": idx, "duplicates_slide": seen_titles[title_key], "field": "title", "value": slide.get("title")})
            else:
                seen_titles[title_key] = idx
        if claim_key:
            if claim_key in seen_claims:
                duplicate_gaps.append({"slide": idx, "duplicates_slide": seen_claims[claim_key], "field": "claim", "value": claim[:120]})
            else:
                seen_claims[claim_key] = idx
        layout_key = str(slide.get("layout_type") or actual_layout or expected_visual or "unknown").lower()
        layout_counts[layout_key] = layout_counts.get(layout_key, 0) + 1
        recent_layouts.append(layout_key)
        if len(recent_layouts) >= 3 and len(set(recent_layouts[-3:])) == 1 and layout_key not in {"unknown", ""}:
            layout_sequence_gaps.append({"slide": idx, "layout_type": layout_key, "reason": "same layout repeated for 3 consecutive slides"})
        left_body = " ".join(str(x) for x in ((slide.get("left_box") or {}).get("body") or []))
        right_body = " ".join(str(x) for x in ((slide.get("right_box") or {}).get("body") or []))
        if idx != 1 and claim and (left_body.strip() == right_body.strip() or left_body.strip() == claim or right_body.strip() == claim):
            repetition_gaps.append({"slide": idx, "reason": "left/right boxes repeat each other or the claim"})
        slides.append({
            "slide_id": idx,
            "title": slide.get("title"),
            "expected_visual_type": expected_visual,
            "actual_visual_type": actual_visual,
            "story_role": slide.get("story_role"),
            "layout_type": slide.get("layout_type") or actual_layout,
            "visual_intent": slide.get("visual_intent"),
            "visual_fulfilled": visual_ok,
            "visual_spec": {
                "kind": spec_kind,
                "usable": spec_usable,
                "required": requires_spec,
                "content_block_count": len(usable_content_blocks),
                "content_block_roles": sorted(content_block_roles),
            },
            "source_references": refs,
            "source_binding": {
                "has_source": bool(slide_local_refs or slide_citation_refs),
                "citation_refs": slide_citation_refs,
                "local_refs": [
                    {
                        "resource_id": item.get("resource_id"),
                        "path": item.get("path"),
                        "type": item.get("type"),
                    }
                    for item in slide_local_refs
                ],
                "chart_data_source": chart_source,
                "image_asset": image_asset,
            },
            "missing_references": missing_refs,
            "weak_references": weak_refs,
            "component_id": component_id,
            "format_reference": format_reference,
            "format_decision": format_mode or visual_item.get("format_decision"),
            "footer_citations": citations_for_slide,
        })
    result_items = research_results.get("results") or []
    fetched_count = sum(1 for item in result_items if isinstance(item, dict) and item.get("fetch_status") == "fetched")
    if not fetched_count:
        fetched_count = int(research_results.get("fetched_count") or 0)
    evidence_count = sum(1 for item in result_items if isinstance(item, dict) and item.get("evidence_text"))
    if not evidence_count:
        evidence_count = int(research_results.get("evidence_count") or 0)
    snippet_backed_count = sum(1 for item in result_items if isinstance(item, dict) and item.get("evidence_source") == "search_snippet")
    if not snippet_backed_count:
        snippet_backed_count = int(research_results.get("snippet_backed_count") or 0)
    manifest_source_only_count = sum(
        1 for item in result_items
        if isinstance(item, dict) and item.get("evidence_source") == "manifest_source_only"
    )
    invalid_fetch_count = int(research_results.get("invalid_fetch_count") or 0)
    if not invalid_fetch_count:
        invalid_fetch_count = sum(
            1 for item in result_items
            if isinstance(item, dict) and item.get("fetch_warning") and item.get("fetch_status") != "fetched"
        )
    result_count = len(result_items)
    required_full_fetch = min(3, result_count)
    citation_integrity_pass = not citation_gaps
    full_text_pass = fetched_count >= required_full_fetch
    full_text_reference_pass = not weak_reference_slides
    evidence_pass = evidence_count >= result_count if result_count else False
    source_quality_pass = bool(research_results.get("source_quality_pass", full_text_pass and not snippet_backed_count))
    # Deck-level citation pass should be based on references actually used by the
    # current deck. Research may retain unused DOI/title records that were blocked by
    # ACM/IEEE, but those should not fail a deck after weak refs are removed.
    citation_pass = citation_integrity_pass and full_text_reference_pass
    content_slide_count_for_components = max(1, len([s for s in slides if s.get("slide_id") != 1]))
    for component_id, count in component_counts.items():
        if component_id == "evidence_two_box.v1" and count / max(1, len(slides)) > 0.4:
            component_overuse_gaps.append({
                "component_id": component_id,
                "count": count,
                "reason": "evidence_two_box.v1 used on too many slides; layout_type diversity is being flattened",
            })
        if component_id and component_id != "cover_title_image.v1" and count / content_slide_count_for_components > 0.6:
            component_overuse_gaps.append({
                "component_id": component_id,
                "count": count,
                "reason": "single component dominates content slides",
            })
    for semantic_component_id, count in semantic_component_counts.items():
        if semantic_component_id not in {"research_agenda.v1", "summary_takeaway.v1"} and count / content_slide_count_for_components > 0.45:
            component_overuse_gaps.append({
                "component_id": semantic_component_id,
                "count": count,
                "reason": "single semantic component dominates content slides",
            })
    semantic_component_pass = not semantic_component_gaps
    component_binding_pass = not component_gaps and not component_overuse_gaps
    citation_footer_pass = not footer_gaps
    non_repetition_pass = not repetition_gaps and not duplicate_gaps
    layout_diversity_pass = not layout_sequence_gaps
    format_flexibility_pass = not format_reference_gaps
    content_slide_count = max(0, len([s for s in slides if s.get("slide_id") != 1]))
    source_bound_slide_count = sum(1 for s in slides if s.get("slide_id") != 1 and (s.get("source_binding") or {}).get("has_source"))
    local_source_count = len(local_source_items)
    local_source_used_count = len(local_sources_used)
    source_binding_rate = round(source_bound_slide_count / content_slide_count, 3) if content_slide_count else 1
    local_source_usage_pass = local_source_count == 0 or local_source_used_count > 0
    source_usage_pass = not source_binding_gaps and local_source_usage_pass
    citation_level = "full_text_supported" if citation_pass else (
        "snippet_supported_needs_review" if citation_integrity_pass and evidence_pass else "insufficient"
    )
    plan_visual_audit = visual.get("quality_audit") if isinstance(visual.get("quality_audit"), dict) else {}
    plan_visual_audit_gaps = plan_visual_audit.get("gaps") if isinstance(plan_visual_audit.get("gaps"), list) else []
    visual_spec_pass = (
        not visual_spec_gaps
        and not visual_composition_gaps
        and not slide_composition_gaps
        and not blueprint_gaps
        and not composition_coverage_gaps
        and not plan_visual_audit_gaps
    )
    claim_quality_pass = not claim_gaps
    text_density_pass = not text_density_gaps
    svg_scan = _svg_visual_scan(pdir)
    report = {
        "schema_version": "1.0",
        "generated_at": ts,
        "source": "reuse_first_v2_quality_report",
        "slide_count": len(slides),
        "visual_fulfillment": {
            "unmet_slide_ids": unmet_visual,
            "visual_spec_gaps": visual_spec_gaps,
            "visual_composition_gaps": visual_composition_gaps,
            "blueprint_gaps": blueprint_gaps,
            "composition_coverage_gaps": composition_coverage_gaps,
            "slide_composition_gaps": slide_composition_gaps,
            "asset_binding_gaps": asset_binding_gaps,
            "pass": not unmet_visual and visual_spec_pass,
        },
        "visual_spec_quality": {
            "gaps": visual_spec_gaps,
            "composition_gaps": visual_composition_gaps,
            "blueprint_gaps": blueprint_gaps,
            "composition_coverage_gaps": composition_coverage_gaps,
            "slide_composition_gaps": slide_composition_gaps,
            "visual_plan_quality_audit_gaps": plan_visual_audit_gaps,
            "pass": visual_spec_pass,
        },
        "asset_binding": {
            "gaps": asset_binding_gaps,
            "pass": not asset_binding_gaps,
        },
        "citation_quality": {
            "citation_count": len(citations),
            "research_result_count": result_count,
            "fetched_count": fetched_count,
            "required_full_fetch_count": required_full_fetch,
            "fetched_ratio": round(fetched_count / result_count, 3) if result_count else 0,
            "snippet_backed_count": snippet_backed_count,
            "snippet_backed_ratio": round(snippet_backed_count / result_count, 3) if result_count else 0,
            "manifest_source_only_count": manifest_source_only_count,
            "evidence_count": evidence_count,
            "evidence_ratio": round(evidence_count / result_count, 3) if result_count else 0,
            "invalid_fetch_count": invalid_fetch_count,
            "missing_reference_slides": citation_gaps,
            "weak_reference_slides": weak_reference_slides,
            "citation_integrity_pass": citation_integrity_pass,
            "full_text_support_pass": full_text_pass,
            "full_text_reference_pass": full_text_reference_pass,
            "evidence_available_pass": evidence_pass,
            "source_quality_pass": source_quality_pass,
            "level": citation_level,
            "needs_source_review": not (full_text_pass and full_text_reference_pass and source_quality_pass),
            "pass": citation_pass,
        },
        "component_binding": {
            "missing_or_unbound": component_gaps,
            "component_counts": component_counts,
            "semantic_component_counts": semantic_component_counts,
            "semantic_family_counts": semantic_family_counts,
            "semantic_component_gaps": semantic_component_gaps,
            "component_overuse_gaps": component_overuse_gaps,
            "semantic_component_pass": semantic_component_pass,
            "pass": component_binding_pass and semantic_component_pass,
        },
        "plan_review": {
            "generated_by": plan.get("generated_by"),
            "fallback_used": bool(plan.get("fallback_used")),
            "quality_risk": plan.get("quality_risk") or ("high" if plan_fallback_risk else "normal"),
            "need_human_review": bool(plan.get("need_human_review") or plan_fallback_risk),
            "duplicate_gaps": duplicate_gaps,
            "layout_sequence_gaps": layout_sequence_gaps,
            "layout_counts": layout_counts,
            "format_decision_counts": format_decision_counts,
            "layout_diversity_pass": layout_diversity_pass,
            "template_misuse_risk": bool(component_gaps or component_overuse_gaps or semantic_component_gaps),
            "format_reference_gaps": format_reference_gaps,
            "format_flexibility_pass": format_flexibility_pass,
            "pass": (not plan_fallback_risk) and not duplicate_gaps and layout_diversity_pass and not component_gaps and not component_overuse_gaps and not semantic_component_gaps and format_flexibility_pass,
        },
        "citation_footer": {
            "missing_footer_slides": footer_gaps,
            "pass": citation_footer_pass,
        },
        "content_depth": {
            "repetition_gaps": repetition_gaps,
            "duplicate_gaps": duplicate_gaps,
            "claim_gaps": claim_gaps,
            "text_density_gaps": text_density_gaps,
            "non_repetition_pass": non_repetition_pass,
            "claim_quality_pass": claim_quality_pass,
            "text_density_pass": text_density_pass,
            "pass": non_repetition_pass and claim_quality_pass and text_density_pass,
        },
        "source_usage": {
            "content_slide_count": content_slide_count,
            "source_bound_slide_count": source_bound_slide_count,
            "source_binding_rate": source_binding_rate,
            "unbound_slides": source_binding_gaps,
            "citation_source_used_count": len(citation_sources_used),
            "local_source_count": local_source_count,
            "local_source_used_count": local_source_used_count,
            "local_source_usage_pass": local_source_usage_pass,
            "used_local_sources": [
                {
                    "resource_id": item.get("resource_id"),
                    "path": item.get("path"),
                    "type": item.get("type"),
                }
                for item in local_sources_used.values()
            ],
            "unused_local_sources": [
                {
                    "resource_id": item.get("resource_id"),
                    "path": item.get("path"),
                    "type": item.get("type"),
                }
                for item in local_source_items
                if str(item.get("path") or item.get("resource_id")) not in local_sources_used
            ][:20],
            "pass": source_usage_pass,
        },
        "svg_visual_scan": svg_scan,
        "slides": slides,
    }
    write_json(pdir / "content-quality-report.json", report)
    return report


def content_quality_report(project_id: str) -> dict:
    return _content_quality_report(project_id)


def _existing_model_plan(project_id: str, expected_slide_count: int) -> dict:
    pdir = project_dir(project_id)
    path = pdir / "model-routed-plan.json"
    plan = read_json(path, {})
    slides = plan.get("slides") if isinstance(plan, dict) else None
    if not isinstance(slides, list):
        return {"ok": False, "plan_path": None, "reason": "model-routed-plan.json missing or invalid"}
    if int(plan.get("slide_count") or len(slides)) != expected_slide_count or len(slides) != expected_slide_count:
        return {
            "ok": False,
            "plan_path": None,
            "reason": f"existing plan slide count does not match {expected_slide_count}",
        }
    return {
        "ok": True,
        "reused": True,
        "provider": plan.get("generated_by") or "existing_model_plan",
        "plan_path": str(path),
        "slide_count": expected_slide_count,
        "errors": [],
    }


def get_model_routed_plan(project_id: str) -> dict:
    pdir = project_dir(project_id)
    state = read_json(pdir / "app-state.json", {})
    if not state:
        raise FileNotFoundError(project_id)
    reuse_outline = read_json(pdir / "reuse-first-outline.json", {})
    plan = reuse_outline if reuse_outline else read_json(pdir / "model-routed-plan.json", {})
    return {
        "ok": bool(plan),
        "project_id": project_id,
        "plan": plan,
        "plan_path": str(pdir / "reuse-first-outline.json") if reuse_outline else str(pdir / "model-routed-plan.json") if plan else None,
        "plan_kind": "reuse-first-outline" if reuse_outline else "model-routed-plan" if plan else None,
        "slide_state": stage_controller.slide_state(project_id),
        "gates": stage_controller.gate_status(project_id),
    }


def template_components(project_id: str) -> dict:
    pdir = project_dir(project_id)
    state = read_json(pdir / "app-state.json", {})
    if not state:
        raise FileNotFoundError(project_id)
    try:
        stage_runner._ensure_template_profile(project_id, (_answers(project_id) or {}).get("template"))
    except Exception:
        pass
    components = read_json(pdir / "template-components.json", {})
    components_source = "template-components.json"
    profile = read_json(pdir / "template-profile.json", {})
    items = components.get("components") if isinstance(components, dict) else []
    if not isinstance(items, list):
        items = []
    source_count = sum(
        1 for item in items
        if isinstance(item, dict) and item.get("source") == "ppt_master_source_slide_catalog"
    )
    return {
        "ok": True,
        "project_id": project_id,
        "template_id": components.get("template_id") or profile.get("template_id"),
        "template_name": components.get("template_name") or profile.get("name"),
        "source_artifact": components_source,
        "template_library_manifest": read_json(template_library.MANIFEST, {}),
        "review_status": components.get("review_status") if isinstance(components, dict) else None,
        "review_instructions": components.get("review_instructions") if isinstance(components, dict) else None,
        "component_count": len(items),
        "source_component_count": source_count,
        "by_type": components.get("by_type") if isinstance(components, dict) else {},
        "components": items,
    }


def template_library_candidates(project_id: str) -> dict:
    pdir = project_dir(project_id)
    state = read_json(pdir / "app-state.json", {})
    if not state:
        raise FileNotFoundError(project_id)
    candidates_doc = read_json(pdir / "template-library-candidates.json", {})
    if not candidates_doc:
        try:
            candidates_doc = template_library.query_for_project(project_id)
        except Exception:
            candidates_doc = read_json(pdir / "template-library-candidates.json", {})
    candidates = candidates_doc.get("candidates") if isinstance(candidates_doc, dict) else []
    if not isinstance(candidates, list):
        candidates = []
    by_type: dict[str, int] = {}
    direct_candidates = []
    audit_required = 0
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        object_type = str(candidate.get("object_type") or "unknown")
        by_type[object_type] = by_type.get(object_type, 0) + 1
        if object_type in {"slide", "asset"}:
            audit_required += 1
            direct_candidates.append({
                "object_id": candidate.get("object_id"),
                "object_type": object_type,
                "deck_id": candidate.get("deck_id"),
                "slide_id": candidate.get("slide_id"),
                "text": candidate.get("text"),
                "score": candidate.get("score"),
                "audit_dimensions": ["topic", "claim", "object_or_metric", "caption_or_slide_context", "misleading_risk"],
            })
    visual_plan = read_json(pdir / "visual-plan.json", {})
    visual_slides = visual_plan.get("slides") if isinstance(visual_plan, dict) else []
    slide_decisions = []
    for slide in visual_slides if isinstance(visual_slides, list) else []:
        if not isinstance(slide, dict):
            continue
        decisions = slide.get("reuse_decisions") if isinstance(slide.get("reuse_decisions"), list) else []
        image_decision = slide.get("image_decision") if isinstance(slide.get("image_decision"), dict) else {}
        slide_decisions.append({
            "slide_index": slide.get("slide_index"),
            "title": slide.get("title") or slide.get("assertion_title"),
            "image_decision": image_decision,
            "reuse_decisions": decisions,
            "direct_reuse_count": sum(1 for item in decisions if isinstance(item, dict) and item.get("decision") == "direct_reuse"),
        })
    return {
        "ok": True,
        "project_id": project_id,
        "source_artifact": "template-library-candidates.json",
        "template_library_manifest": candidates_doc.get("library_manifest") if isinstance(candidates_doc, dict) else read_json(template_library.MANIFEST, {}),
        "schema_version": candidates_doc.get("schema_version") if isinstance(candidates_doc, dict) else None,
        "candidate_count": len(candidates),
        "unit_count": len(candidates),
        "by_type": candidates_doc.get("by_type") if isinstance(candidates_doc, dict) and candidates_doc.get("by_type") else by_type,
        "audit_required_count": audit_required,
        "direct_candidate_count": len(direct_candidates),
        "policy": {
            "source": "reuse_first_v2_template_library",
            "direct_reuse": "Allowed only after semantic audit; candidates here are recall results, not approved final reuse.",
            "template_source": "V2 generation reads template-library-candidates.json and data/resources_library/material only.",
        },
        "direct_candidates": direct_candidates[:80],
        "units": candidates[:300],
        "visual_plan_reuse_decisions": slide_decisions,
        "visual_plan_quality_audit": visual_plan.get("quality_audit") if isinstance(visual_plan, dict) else {},
    }


_ROLE_LAYOUT_DEFAULTS = {
    "cover": ("cover", "title-image", "image-and-bullets", "cover_title_image.v1"),
    "section": ("section", "section-divider", "bullets", ""),
    "problem": ("problem", "problem-framing", "bullets", ""),
    "gap": ("problem", "gap-matrix", "table", ""),
    "evidence": ("evidence", "evidence-matrix", "table", ""),
    "experiment": ("evidence", "experiment-result", "table", ""),
    "architecture": ("architecture", "layered-architecture", "diagram", ""),
    "mechanism": ("mechanism", "process-flow", "diagram", ""),
    "comparison": ("comparison", "comparison-matrix", "table", ""),
    "timeline": ("timeline", "roadmap", "diagram", ""),
    "risk": ("risk", "risk-boundary-table", "table", ""),
    "summary": ("summary", "closing", "bullets", ""),
}


def _default_format_reference(story_role: str, layout_type: str, visual_intent: str) -> dict:
    return {
        "mode": "adapt",
        "reference_type": "template_layout_pattern",
        "preferred_role": story_role or "content",
        "decision_reason": (
            f"参考与 {layout_type or story_role or 'content'} 相近的版式节奏；"
            "根据本页表达意图重排内容，不复制示例页的具体图片、原文或图表。"
        ),
        "adaptation_notes": [
            str(visual_intent or "按页面主张选择合适结构").strip(),
            "如果模板示例不匹配本页语义，允许使用生成式可编辑布局。",
        ],
        "reject_if": [
            "模板示例图文语义与本页 claim 不一致",
            "会导致连续页面版式重复",
            "需要复制模板原始图片或原始文字才能成立",
        ],
    }


def _infer_story_role(raw: dict, index: int) -> str:
    role = str(raw.get("story_role") or raw.get("role") or "").strip().lower()
    if role in _ROLE_LAYOUT_DEFAULTS:
        return role
    text = " ".join(str(raw.get(key) or "") for key in ("title", "section", "purpose", "kind", "visual_type")).lower()
    if index == 1 or "封面" in text or "cover" in text:
        return "cover"
    if "章节" in text or "section" in text:
        return "section"
    if any(token in text for token in ("问题", "挑战", "约束", "瓶颈", "problem", "challenge", "constraint")):
        return "problem"
    if any(token in text for token in ("gap", "空白", "不足", "未解决")):
        return "gap"
    if any(token in text for token in ("实验", "结果", "指标", "benchmark", "experiment", "result", "metric")):
        return "experiment"
    if any(token in text for token in ("证据", "依据", "研究", "evidence", "finding")):
        return "evidence"
    if any(token in text for token in ("架构", "分层", "architecture", "layer")):
        return "architecture"
    if any(token in text for token in ("机制", "流程", "策略", "缓存", "卸载", "协同", "mechanism", "flow", "policy")):
        return "mechanism"
    if any(token in text for token in ("对比", "权衡", "trade", "compare", "comparison")):
        return "comparison"
    if any(token in text for token in ("路线", "roadmap", "timeline", "路径")):
        return "timeline"
    if any(token in text for token in ("风险", "边界", "risk", "limitation")):
        return "risk"
    if any(token in text for token in ("总结", "结论", "summary", "conclusion")):
        return "summary"
    return "mechanism"


def _layout_defaults_for(role: str, index: int, total: int | None = None) -> tuple[str, str, str, str]:
    if index == 1:
        return _ROLE_LAYOUT_DEFAULTS["cover"]
    if total and index == total:
        return _ROLE_LAYOUT_DEFAULTS["summary"]
    return _ROLE_LAYOUT_DEFAULTS.get(role, _ROLE_LAYOUT_DEFAULTS["mechanism"])


_SEMANTIC_COMPONENT_DEFAULTS = {
    "cover": "research_agenda.v1",
    "section": "research_agenda.v1",
    "problem": "challenge_quantification.v1",
    "gap": "related_work_matrix.v1",
    "evidence": "experiment_result.v1",
    "experiment": "experiment_result.v1",
    "architecture": "method_overview.v1",
    "mechanism": "technique_detail.v1",
    "comparison": "related_work_matrix.v1",
    "timeline": "research_agenda.v1",
    "risk": "risk_boundary.v1",
    "summary": "summary_takeaway.v1",
}


def _semantic_component_default(role: str) -> str:
    return _SEMANTIC_COMPONENT_DEFAULTS.get(str(role or "").strip().lower(), "technique_detail.v1")


def _normalize_plan_slide(raw: dict, index: int) -> dict:
    bullets = raw.get("bullets") or []
    if isinstance(bullets, str):
        bullets = [line.strip() for line in bullets.splitlines() if line.strip()]
    if not isinstance(bullets, list):
        bullets = []
    refs = raw.get("source_references") or raw.get("source_refs") or []
    if isinstance(refs, str):
        refs = [item.strip() for item in re.split(r"[,，\s]+", refs) if item.strip()]
    if not isinstance(refs, list):
        refs = []
    bullets_clean = [str(item).strip() for item in bullets if str(item).strip()]
    claim = str(raw.get("claim") or raw.get("key_message") or (bullets_clean[0] if bullets_clean else "")).strip()
    evidence_sentence = str(raw.get("evidence_sentence") or raw.get("evidence") or "").strip()
    if not evidence_sentence and len(bullets_clean) > 1:
        evidence_sentence = bullets_clean[1]
    left_box = raw.get("left_box") if isinstance(raw.get("left_box"), dict) else {}
    right_box = raw.get("right_box") if isinstance(raw.get("right_box"), dict) else {}
    if not left_box:
        left_box = {
            "heading": "依据分析",
            "body": bullets_clean[1:3] or ([claim] if claim else []),
            "source_references": refs[:2],
        }
    if not right_box:
        right_box = {
            "heading": "方案含义",
            "body": bullets_clean[3:5] or bullets_clean[-2:] or ([claim] if claim else []),
            "source_references": refs[-2:] if refs else [],
        }
    citations = raw.get("citations") or refs
    if isinstance(citations, str):
        citations = [item.strip() for item in re.split(r"[,，\s]+", citations) if item.strip()]
    if not refs and isinstance(citations, list):
        refs = citations
    total = int(raw.get("_total_slides") or 0) or None
    story_role = _infer_story_role(raw, index)
    _, default_layout_type, default_visual_type, default_component_id = _layout_defaults_for(story_role, index, total)
    layout_type = str(raw.get("layout_type") or default_layout_type).strip()
    visual_intent = str(raw.get("visual_intent") or raw.get("purpose") or raw.get("key_message") or claim).strip()
    layout_contract = raw.get("layout_contract") if isinstance(raw.get("layout_contract"), dict) else {}
    if not layout_contract:
        slots = ["title", "claim", "body", "footer_citation", "page_number"]
        if default_visual_type == "diagram":
            slots.append("diagram")
        elif default_visual_type == "table":
            slots.append("table")
        elif default_visual_type == "evidence-two-box":
            slots = ["title", "claim", "left_box", "right_box", "footer_citation", "page_number"]
        layout_contract = {
            "component_id": default_component_id,
            "style_only": True,
            "copy_assets": False,
            "slots": slots if index != 1 else ["title", "claim"],
        }
    else:
        layout_contract.setdefault("style_only", True)
        layout_contract.setdefault("copy_assets", False)
    layout_contract.setdefault("format_locked", False)
    layout_contract.setdefault("renderer_may_adapt", True)
    format_reference = raw.get("format_reference") if isinstance(raw.get("format_reference"), dict) else {}
    if not format_reference:
        format_reference = _default_format_reference(story_role, layout_type, visual_intent)
    else:
        format_reference.setdefault("mode", "adapt")
        format_reference.setdefault("reference_type", "template_layout_pattern")
        format_reference.setdefault("preferred_role", story_role)
        format_reference.setdefault("decision_reason", "agent selected this reference as suitable for the slide intent")
    visual_type = str(raw.get("visual_type") or default_visual_type or raw.get("kind") or "bullets").strip()
    semantic_component_id = str(raw.get("semantic_component_id") or _semantic_component_default(story_role)).strip()
    reuse_level = str(raw.get("reuse_level") or ("locked" if story_role in {"cover", "section", "summary"} else "component_pattern")).strip()
    base_lock = raw.get("base_lock") if isinstance(raw.get("base_lock"), list) else []
    if not base_lock:
        base_lock = ["title_rule", "footer", "page_number", "palette", "typography"]
    paper_share_influence = str(raw.get("paper_share_influence") or "Learn abstract layout rhythm and information density only; do not copy source text, figures, charts, or citations.").strip()
    layout_family = str(raw.get("layout_family") or raw.get("layout_type") or default_layout_type).strip()
    assertion_title = str(raw.get("assertion_title") or raw.get("title") or claim or f"Slide {index}").strip()
    claim_type = str(raw.get("claim_type") or ("summary" if story_role in {"cover", "summary"} else "inference")).strip()
    if claim_type not in {"fact", "inference", "hypothesis", "proposal", "risk", "summary"}:
        claim_type = "inference"
    evidence_need_raw = raw.get("evidence_need") if isinstance(raw.get("evidence_need"), dict) else {}
    evidence_need = {
        "kind": str(evidence_need_raw.get("kind") or ("none" if story_role in {"cover", "summary"} else "comparison")).strip(),
        "required": bool(evidence_need_raw.get("required")) if "required" in evidence_need_raw else story_role not in {"cover", "summary"},
        "strength": str(evidence_need_raw.get("strength") or ("local_material" if refs else "missing")).strip(),
        "must_show": evidence_need_raw.get("must_show") if isinstance(evidence_need_raw.get("must_show"), list) else ([claim] if claim else []),
    }
    if evidence_need["strength"] not in {"direct", "literature", "local_material", "indirect", "weak", "missing"}:
        evidence_need["strength"] = "indirect"
    primary_visual_raw = raw.get("primary_visual") if isinstance(raw.get("primary_visual"), dict) else {}
    primary_visual = {
        "type": str(primary_visual_raw.get("type") or visual_type or "cards").strip(),
        "visual_goal": str(primary_visual_raw.get("visual_goal") or visual_intent or "Use the visual to support the assertion.").strip(),
        "failure_mode": str(primary_visual_raw.get("failure_mode") or "Generic bullets that do not prove the assertion.").strip(),
    }
    visual_density = str(raw.get("visual_density") or "").strip().lower()
    if visual_density not in {"low", "medium", "high"}:
        visual_density = "medium" if story_role in {"evidence", "architecture", "mechanism", "comparison"} else "low"
    try:
        fill_target = float(raw.get("content_fill_target") or 0.68)
    except (TypeError, ValueError):
        fill_target = 0.68
    fill_target = max(0.45, min(0.88, fill_target))
    asset_request = raw.get("asset_request") if isinstance(raw.get("asset_request"), dict) else {}
    needs_generated_image = bool(raw.get("needs_generated_image") or asset_request.get("needs_generated_image"))
    image_prompt = str(raw.get("image_prompt") or asset_request.get("prompt") or "").strip()
    return {
        "index": int(raw.get("index") or index),
        "section": str(raw.get("section") or "").strip(),
        "title": str(raw.get("title") or f"Slide {index}").strip(),
        "purpose": str(raw.get("purpose") or "").strip(),
        "kind": str(raw.get("kind") or raw.get("visual_type") or "bullets").strip(),
        "story_role": story_role,
        "layout_type": layout_type,
        "visual_intent": visual_intent,
        "key_message": str(raw.get("key_message") or claim).strip(),
        "claim": claim,
        "assertion_title": assertion_title,
        "claim_type": claim_type,
        "evidence_need": evidence_need,
        "primary_visual": primary_visual,
        "semantic_component_id": semantic_component_id,
        "reuse_level": reuse_level,
        "base_lock": [str(item).strip() for item in base_lock if str(item).strip()],
        "paper_share_influence": paper_share_influence,
        "layout_family": layout_family,
        "evidence_sentence": evidence_sentence,
        "left_box": left_box,
        "right_box": right_box,
        "chart_spec": raw.get("chart_spec") if isinstance(raw.get("chart_spec"), dict) else {},
        "image_asset": str(raw.get("image_asset") or "").strip(),
        "citations": [str(item).strip() for item in citations if str(item).strip()] if isinstance(citations, list) else [],
        "layout_contract": layout_contract,
        "format_reference": format_reference,
        "bullets": bullets_clean,
        "visual_type": visual_type,
        "source_references": [str(item).strip() for item in refs if str(item).strip()],
        "visual_density": visual_density,
        "content_fill_target": fill_target,
        "needs_generated_image": needs_generated_image,
        "image_prompt": image_prompt,
        "asset_request": {
            "needs_generated_image": needs_generated_image,
            "prompt": image_prompt,
            "purpose": str(asset_request.get("purpose") or visual_intent).strip(),
            "style_reference": str(asset_request.get("style_reference") or "").strip(),
            "status": "requested" if needs_generated_image and image_prompt else "not_required",
        },
    }


def validate_model_routed_plan(plan: dict) -> tuple[dict, list[str]]:
    errors: list[str] = []
    if not isinstance(plan, dict):
        return {}, ["plan must be a JSON object"]
    slides = plan.get("slides")
    if not isinstance(slides, list) or not slides:
        return {}, ["plan.slides must be a non-empty array"]
    normalized_slides = []
    total = len(slides)
    for idx, slide in enumerate(slides, start=1):
        if not isinstance(slide, dict):
            errors.append(f"slide {idx} must be an object")
            continue
        slide = {**slide, "_total_slides": total}
        normalized = _normalize_plan_slide(slide, idx)
        if not normalized["title"]:
            errors.append(f"slide {idx} title is required")
        if not normalized["bullets"] and idx != 1:
            errors.append(f"slide {idx} should include at least one bullet")
        normalized["index"] = idx
        normalized_slides.append(normalized)
    normalized_plan = {
        **plan,
        "schema_version": str(plan.get("schema_version") or "1.0"),
        "slide_count": len(normalized_slides),
        "slides": normalized_slides,
    }
    return normalized_plan, errors


def update_model_routed_plan(project_id: str, payload: dict | None = None) -> dict:
    payload = payload or {}
    pdir = project_dir(project_id)
    state = read_json(pdir / "app-state.json", {})
    if not state:
        raise FileNotFoundError(project_id)
    plan = payload.get("plan")
    if isinstance(plan, str):
        plan = json.loads(plan)
    normalized, errors = validate_model_routed_plan(plan)
    if errors:
        return {"ok": False, "project_id": project_id, "errors": errors}
    previous = read_json(pdir / "model-routed-plan.json", {})
    normalized["edited_at"] = now()
    normalized["edited_by"] = "app-outline-editor"
    normalized["revision"] = int(previous.get("revision") or 0) + 1 if isinstance(previous, dict) else 1
    write_json(pdir / "model-routed-plan.json", normalized)
    slide_state = stage_controller.build_slide_state(project_id)
    stage_controller.rewind_to_stage(project_id, "REUSE_OUTLINE", reason="model plan edited")
    return {
        "ok": True,
        "project_id": project_id,
        "plan": normalized,
        "plan_path": str(pdir / "model-routed-plan.json"),
        "slide_state": slide_state,
        "gates": stage_controller.gate_status(project_id),
    }


def revise_slide_plan(project_id: str, payload: dict | None = None) -> dict:
    payload = payload or {}
    pdir = project_dir(project_id)
    state = read_json(pdir / "app-state.json", {})
    if not state:
        raise FileNotFoundError(project_id)
    plan = read_json(pdir / "model-routed-plan.json", {})
    if not isinstance(plan, dict) or not isinstance(plan.get("slides"), list) or not plan.get("slides"):
        return {"ok": False, "project_id": project_id, "error": "model-routed-plan.json missing or invalid"}
    try:
        slide_id = int(payload.get("slide_id") or payload.get("index") or 0)
    except (TypeError, ValueError):
        slide_id = 0
    if slide_id < 1 or slide_id > len(plan["slides"]):
        return {
            "ok": False,
            "project_id": project_id,
            "error": f"slide_id must be between 1 and {len(plan['slides'])}",
        }
    instruction = str(payload.get("instruction") or "").strip()
    direct_slide = payload.get("slide")
    current_slide = plan["slides"][slide_id - 1]
    revised_slide = None
    model_result = None
    if isinstance(direct_slide, dict):
        revised_slide = direct_slide
    else:
        if not instruction:
            return {"ok": False, "project_id": project_id, "error": "instruction is required unless slide is provided"}
        answers = state.get("answers") or {}
        context = {
            "answers": answers,
            "current_slide": current_slide,
            "full_plan": plan,
            "research_audit": read_json(pdir / "research-audit.json", {}),
            "citations": read_json(pdir / "citations.json", {}),
            "resource_index": read_json(pdir / "project-source-index.json", []),
            "source_digest": read_json(pdir / "project-source-digest.json", {}),
            "template_components": read_json(pdir / "template-components.json", {}),
        }
        prompt = f"""
你是 PPT-agent 的单页修改模型。请只重写第 {slide_id} 页，输出严格 JSON，不要解释。

项目主题：{answers.get("topic")}
受众：{answers.get("audience")}
场景：{answers.get("scenario")}
整体叙事：{answers.get("story_style")}

当前页 JSON：
{json.dumps(current_slide, ensure_ascii=False, indent=2)}

用户修改要求：
{instruction}

输出 JSON schema：
{{
  "index": {slide_id},
  "section": "章节",
  "title": "页面标题",
  "purpose": "这一页在叙事中的作用",
  "kind": "problem|framework|evidence|comparison|summary|title",
  "key_message": "一句话主张",
  "claim": "标题下方依据判断句，必须可直接上页",
  "evidence_sentence": "用来源支持 claim 的一句证据",
  "left_box": {{"heading": "左框标题", "body": ["分析点1", "分析点2"], "source_references": ["S1"]}},
  "right_box": {{"heading": "右框标题", "body": ["分析点1", "分析点2"], "source_references": ["S2"]}},
  "chart_spec": {{"chart_type": "bar|line|matrix|none", "data_source": "资源或引用编号", "description": "图表要表达什么"}},
  "image_asset": "可选本地图片路径",
  "citations": ["S1", "S2"],
  "layout_type": "problem-framing|evidence-matrix|comparison-matrix|process-flow|layered-architecture|roadmap|risk-boundary-table|closing",
  "visual_intent": "说明这一页应画成图、表、流程、架构还是路线",
  "layout_contract": {{"component_id": "按 layout_type 选择的专用组件，不要默认 evidence_two_box.v1", "style_only": true, "copy_assets": false, "format_locked": false, "renderer_may_adapt": true}},
  "bullets": ["兼容旧渲染的短句1", "短句2"],
  "visual_type": "evidence-two-box|diagram|table|image-and-bullets|bullets",
  "source_references": ["S1", "S2"]
}}

约束：
- index 必须等于 {slide_id}。
- 保持这页与整套 PPT 叙事一致。
- 正文页必须根据 layout_type 选择结构：证据/对比/风险页用表格，机制/架构/路线页用可编辑图形；禁止把所有页默认写成 evidence_two_box.v1。
- left_box/right_box 必须是分析内容，不能简单重复 claim。
- 每个分析框至少 2 条 body，每条说明原因、机制、数据或影响。
- 如果使用外部事实，source_references 使用 citations.json 中的 S 编号。
- S 编号只允许出现在 source_references/citations 等结构化字段中；claim、evidence_sentence、left_box/right_box/body/bullets 等可见正文不要写 S1/S2。如果正文需要引用，只使用 [1]、[2] 这种短标记。
- 只输出合法 JSON。
""".strip()
        prompt = skill_runtime.stage_prompt("SLIDE_REWRITE", prompt)
        model_result = model_providers.generate(project_id, "slide_rewrite", prompt, context=context)
        revised_slide = _extract_json_object(str(model_result.get("output") or ""))
    normalized = _normalize_plan_slide(revised_slide if isinstance(revised_slide, dict) else {}, slide_id)
    normalized["index"] = slide_id
    errors = []
    if not normalized["title"]:
        errors.append("revised slide title is required")
    if not normalized["bullets"] and slide_id != 1:
        errors.append("revised slide should include at least one bullet")
    if errors:
        return {
            "ok": False,
            "project_id": project_id,
            "errors": errors,
            "model_result": model_result,
        }
    previous = read_json(pdir / "model-routed-plan.json", {})
    plan["slides"][slide_id - 1] = normalized
    plan["slide_count"] = len(plan["slides"])
    plan["edited_at"] = now()
    plan["edited_by"] = "app-slide-revise"
    plan["revision"] = int(previous.get("revision") or 0) + 1 if isinstance(previous, dict) else 1
    plan.setdefault("revision_log", [])
    if isinstance(plan["revision_log"], list):
        plan["revision_log"].append({
            "at": now(),
            "slide_id": slide_id,
            "instruction": instruction,
            "provider": model_result.get("provider") if isinstance(model_result, dict) else "direct_edit",
        })
        plan["revision_log"] = plan["revision_log"][-30:]
    write_json(pdir / "model-routed-plan.json", plan)
    slide_state = stage_controller.build_slide_state(project_id)
    stage_controller.rewind_to_stage(project_id, "SLIDE_REWRITE", reason=f"slide {slide_id} revised")
    return {
        "ok": True,
        "project_id": project_id,
        "slide_id": slide_id,
        "slide": normalized,
        "plan": plan,
        "slide_state": slide_state,
        "gates": stage_controller.gate_status(project_id),
        "model_result": model_result,
    }


def generate(project_id: str, payload: dict | None = None) -> dict:
    payload = payload or {}
    pdir = project_dir(project_id)
    state = read_json(pdir / "app-state.json", {})
    if not state:
        raise FileNotFoundError(project_id)
    answers = state.get("answers") or {}
    ready = completion(answers)
    if not ready["ready_to_generate"]:
        return {"ok": False, "error": "required questions missing", **ready}
    run_payload = {
        **payload,
        "max_steps": int(payload.get("max_steps") or 24),
        "stop_at_human_gate": bool(payload.get("stop_at_human_gate", True)),
    }
    result = stage_runner.run_until_blocked(project_id, run_payload)
    state["last_generation"] = {
        "source": "reuse_first_v2_run_until_blocked",
        "finished_at": now(),
        "stop_reason": result.get("stop_reason"),
        "stopped_stage": result.get("stopped_stage"),
        "executed": result.get("executed") or [],
    }
    state["status"] = "generated" if result.get("stop_reason") == "complete" else "in_progress" if result.get("ok") else "error"
    write_json(pdir / "app-state.json", state)
    return {
        "ok": bool(result.get("ok")),
        "result": result,
        "project": state,
        "quality": quality(project_id),
        "downloads": downloads(project_id),
        "citations": read_json(pdir / "citations.json", {}).get("citations", []),
    }


def generate_async(project_id: str, payload: dict | None = None) -> dict:
    return jobs.start("generate", generate, project_id, payload or {}, project_id=project_id)


def run_stage(project_id: str, payload: dict | None = None) -> dict:
    return stage_runner.run_stage(project_id, payload or {})


def run_stage_async(project_id: str, payload: dict | None = None) -> dict:
    return jobs.start("stage-runner", run_stage, project_id, payload or {}, project_id=project_id)


def run_until_blocked(project_id: str, payload: dict | None = None) -> dict:
    return stage_runner.run_until_blocked(project_id, payload or {})


def run_until_blocked_async(project_id: str, payload: dict | None = None) -> dict:
    return jobs.start("stage-runner", run_until_blocked, project_id, payload or {}, project_id=project_id)


def job_status(job_id: str) -> dict:
    job = jobs.get(job_id)
    if not job:
        raise FileNotFoundError(job_id)
    if job.get("kind") == "generate" and job.get("status") == "running" and job.get("project_id"):
        project_id = str(job["project_id"])
        pdir = project_dir(project_id)
        state = read_json(pdir / "app-state.json", {})
        last = state.get("last_generation") or {}
        last_finished_at = str(last.get("finished_at") or "")
        started_at = str(job.get("started_at") or "")
        if last_finished_at and last_finished_at >= started_at and last.get("returncode") is not None:
            ok = int(last.get("returncode") or 0) == 0
            result = {
                "ok": ok,
                "project": state,
                "quality": quality(project_id),
                "downloads": downloads(project_id),
                "citations": read_json(pdir / "citations.json", {}).get("citations", []),
                "reconciled_from_app_state": True,
            }
            job = jobs.update(job_id, {
                "status": "succeeded" if ok else "failed",
                "finished_at": last.get("finished_at") or now(),
                "result": result,
            })
    return job


def list_jobs() -> list[dict]:
    return jobs.list_jobs()


def model_routes() -> dict:
    cfg = research.load_config()
    provider_status = providers.status()
    model_status = model_providers.health()
    tool_status = tool_providers.health()
    return {
        **provider_status,
        "model_router": model_status,
        "tool_router": tool_status,
        "adapters": {
            **providers.adapter_commands("research"),
            "env": {
                "PPT_AGENT_SEARCH_CMD": "optional command; receives query or uses {query}",
                "PPT_AGENT_FETCH_CMD": "optional command; receives url or uses {url}",
            },
        },
        "legacy_config": {
            "web_search_cmd": cfg.get("web_search_cmd") or None,
            "web_fetch_cmd": cfg.get("web_fetch_cmd") or None,
        },
    }


def providers_health() -> dict:
    return model_providers.health()


def tools_health() -> dict:
    return tool_providers.health()


def agents_status() -> dict:
    specs = skill_runtime.stage_specs()
    agents = skill_runtime.agents()
    model_health = model_providers.health()
    route_health = model_health.get("routes") or {}
    direct_model_entrypoints = {
        "IntakeAgent": ["manual: /api/projects/<id>/model-stage stage=intake"],
        "ResourceAgent": ["tool-only: scans project sources/assets"],
        "TemplateLibraryBuildAgent": ["tool-only: compiles data/resources_library/material from templates/"],
        "TemplateLibraryQueryAgent": ["tool-only: writes template-library-candidates.json"],
        "TaskUnderstandingAgent": ["automatic: V2 stage TASK_UNDERSTANDING"],
        "ReuseOutlineAgent": ["automatic: V2 stage REUSE_OUTLINE uses model route outline"],
        "DraftAssemblyAgent": ["tool-only: assembles draft-deck.pptx from approved reuse candidates"],
        "GapAnalysisAgent": ["automatic: V2 stage GAP_ANALYSIS uses model route review when enabled"],
        "GapResearchAgent": ["tool/model: gap-specific search and synthesis only"],
        "SlideRewriteAgent": ["automatic: V2 stage SLIDE_REWRITE uses model route slide_rewrite"],
        "StyleUnificationAgent": ["automatic: locks basic template identity and binds final style"],
        "RenderAgent": ["tool-only: ppt_render/native_svg; no LLM expected"],
        "ReviewAgent": ["automatic/manual: V2 REVIEW plus structural validation"],
        "ExportAgent": ["tool/state only; no LLM expected"],
        "CodexDebugAgent": ["automatic: /api/projects/<id>/codex-debug uses model route pipeline_debug"],
    }
    return {
        "schema_version": "1.0",
        "model_call_truth_source": "projects/<project_id>/route-log.jsonl",
        "note": "model_route means configured route; actual LLM calls only happen through model_providers.generate() and are logged.",
        "stages": [
            {
                "stage": spec.get("stage"),
                "agent": spec.get("agent"),
                "model_route": spec.get("model_route"),
                "model_route_status": route_health.get(str(spec.get("model_route") or "")) if spec.get("model_route") else None,
                "tool_routes": spec.get("tool_routes") or [],
                "output_artifacts": spec.get("output_artifacts") or [],
                "human_gate": bool(spec.get("human_gate")),
                "review_gate": bool(spec.get("review_gate")),
                "next_stage": spec.get("next_stage"),
            }
            for spec in specs
        ],
        "agents": {
            name: {
                "stage": cfg.get("stage"),
                "skills": cfg.get("skills") or [],
                "model_route": cfg.get("model_route"),
                "model_route_status": route_health.get(str(cfg.get("model_route") or "")) if cfg.get("model_route") else None,
                "tool_routes": cfg.get("tool_routes") or [],
                "inputs": cfg.get("inputs") or [],
                "outputs": cfg.get("outputs") or [],
                "human_gate": bool(cfg.get("human_gate")),
                "review_gate": bool(cfg.get("review_gate")),
                "execution_status": direct_model_entrypoints.get(name, ["configured; no direct automatic model entrypoint yet"]),
            }
            for name, cfg in agents.items()
        },
    }


def route_summary(project_id: str) -> dict:
    logs = route_log.read(project_id)
    latest: dict[str, dict] = {}
    latest_success: dict[str, dict] = {}
    counts: dict[str, dict] = {}
    for item in logs:
        key = f"{item.get('route_type')}:{item.get('stage')}"
        latest[key] = item
        bucket = counts.setdefault(key, {"total": 0, "success": 0, "fail": 0})
        bucket["total"] += 1
        if item.get("success"):
            bucket["success"] += 1
            latest_success[key] = item
        else:
            bucket["fail"] += 1
    stages = []
    for spec in skill_runtime.stage_specs():
        model_route = spec.get("model_route")
        tool_routes = spec.get("tool_routes") or []
        model_key = f"model:{model_route}" if model_route else None
        stages.append({
            "stage": spec.get("stage"),
            "agent": spec.get("agent"),
            "configured_model_route": model_route,
            "configured_tool_routes": tool_routes,
            "latest_model_call": latest.get(model_key) if model_key else None,
            "latest_successful_model_call": latest_success.get(model_key) if model_key else None,
            "latest_tool_calls": {
                tool: {
                    "latest_attempt": latest.get(f"tool:{tool}"),
                    "latest_success": latest_success.get(f"tool:{tool}"),
                    "counts": counts.get(f"tool:{tool}", {"total": 0, "success": 0, "fail": 0}),
                }
                for tool in tool_routes
            },
            "model_call_count": counts.get(model_key, {}).get("total", 0) if model_key else 0,
            "model_success_count": counts.get(model_key, {}).get("success", 0) if model_key else 0,
            "model_fail_count": counts.get(model_key, {}).get("fail", 0) if model_key else 0,
        })
    return {
        "project_id": project_id,
        "truth_source": "projects/<project_id>/route-log.jsonl",
        "note": "If latest_model_call is null, that stage is configured but has not actually called a model in this project.",
        "stages": stages,
        "raw_count": len(logs),
    }


def resolve_route(route_type: str, name: str) -> dict:
    if route_type == "tool":
        return tool_providers.resolve(name)
    return model_providers.resolve(name)


def run_model_stage(project_id: str, stage: str, payload: dict | None = None) -> dict:
    payload = payload or {}
    pdir = project_dir(project_id)
    state = read_json(pdir / "app-state.json", {})
    if not state:
        raise FileNotFoundError(project_id)
    prompt = str(payload.get("prompt") or "").strip()
    if not prompt:
        answers = state.get("answers") or {}
        prompt = (
            f"你是 PPT-agent 的 {stage} 阶段模型。"
            f"请基于项目主题、用户回答、已有研究材料，输出该阶段的结构化建议。\n"
            f"主题：{answers.get('topic')}\n"
            f"受众：{answers.get('audience')}\n"
            f"场景：{answers.get('scenario')}\n"
            f"风格：{answers.get('style')}\n"
        )
    prompt = skill_runtime.stage_prompt(stage, prompt)
    context = {
        "answers": state.get("answers") or {},
        "research": read_json(pdir / "research-results.json", {}),
        "citations": read_json(pdir / "citations.json", {}),
        "quality": quality(project_id),
    }
    result = model_providers.generate(project_id, stage, prompt, context=context)
    out_dir = pdir / "model-runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    write_json(out_dir / f"{stage}.json", result)
    if result.get("output"):
        (out_dir / f"{stage}.md").write_text(str(result["output"]) + "\n", encoding="utf-8")
    return result


def _extract_json_object(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(text[start:end + 1])
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _short_text(value, limit: int = 700) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit]


def _compact_model_plan_context(project_id: str, answers: dict) -> dict:
    pdir = project_dir(project_id)
    research_data = read_json(pdir / "research-results.json", {})
    citations_raw = read_json(pdir / "citations.json", {}).get("citations", [])
    source_digest = read_json(pdir / "project-source-digest.json", {})
    resource_index = read_json(pdir / "project-source-index.json", [])
    chart_candidates = {}  # P18: legacy artifact, no longer produced
    asset_catalog = read_json(pdir / "project-asset-catalog.json", {})
    visual_reference_index = {}  # P18: legacy artifact, no longer produced

    citations = []
    for item in citations_raw if isinstance(citations_raw, list) else []:
        if not isinstance(item, dict):
            continue
        citations.append({
            "id": item.get("id"),
            "title": item.get("title"),
            "url": item.get("url"),
            "evidence_tier": item.get("evidence_tier"),
            "fetch_status": item.get("fetch_status"),
            "snippet": _short_text(item.get("snippet") or item.get("evidence_text"), 800),
        })

    digest_items = []
    for item in source_digest.get("items", []) if isinstance(source_digest, dict) else []:
        if not isinstance(item, dict):
            continue
        digest_items.append({
            "path": item.get("path"),
            "type": item.get("type"),
            "text_excerpt": _short_text(item.get("text_excerpt") or item.get("summary"), 650),
        })

    resources = []
    for item in resource_index if isinstance(resource_index, list) else []:
        if not isinstance(item, dict):
            continue
        resources.append({
            "resource_id": item.get("resource_id"),
            "path": item.get("path"),
            "type": item.get("type"),
            "size": item.get("size"),
        })

    charts = chart_candidates.get("candidates") if isinstance(chart_candidates, dict) else chart_candidates
    if not isinstance(charts, list):
        charts = []
    assets = asset_catalog.get("assets") if isinstance(asset_catalog, dict) else asset_catalog
    if not isinstance(assets, list):
        assets = []

    return {
        "answers": answers,
        "research_audit": read_json(pdir / "research-audit.json", {}),
        "research_summary": {
            "queries": research_data.get("queries") if isinstance(research_data, dict) else [],
            "web_results_count": research_data.get("web_results_count") if isinstance(research_data, dict) else 0,
            "fetched_count": research_data.get("fetched_count") if isinstance(research_data, dict) else 0,
            "warnings": research_data.get("warnings") if isinstance(research_data, dict) else [],
        },
        "citations": citations[:16],
        "resource_index": resources[:60],
        "source_digest": {
            "parsed_count": source_digest.get("parsed_count") if isinstance(source_digest, dict) else None,
            "by_type": source_digest.get("by_type") if isinstance(source_digest, dict) else {},
            "items": digest_items[:30],
        },
        "template_components": read_json(pdir / "template-components.json", {}),
        "visual_reference_index": {
            "exemplar_count": visual_reference_index.get("exemplar_count") if isinstance(visual_reference_index, dict) else 0,
            "by_role": visual_reference_index.get("by_role") if isinstance(visual_reference_index, dict) else {},
            "by_density": visual_reference_index.get("by_density") if isinstance(visual_reference_index, dict) else {},
            "policy": visual_reference_index.get("policy") if isinstance(visual_reference_index, dict) else "",
            "exemplars": (visual_reference_index.get("exemplars") or [])[:24] if isinstance(visual_reference_index, dict) else [],
        },
        "chart_candidates": charts[:20],
        "asset_catalog": assets[:40],
    }


def _outline_retry_context(context: dict) -> dict:
    """Smaller context for a JSON-only outline retry after a verbose response truncates."""
    context = context if isinstance(context, dict) else {}
    source_digest = context.get("source_digest") if isinstance(context.get("source_digest"), dict) else {}
    visual_reference = context.get("visual_reference_index") if isinstance(context.get("visual_reference_index"), dict) else {}
    template_policy = context.get("template_knowledge_base_policy") if isinstance(context.get("template_knowledge_base_policy"), dict) else {}
    return {
        "answers": context.get("answers") or {},
        "research_summary": context.get("research_summary") or {},
        "citations": (context.get("citations") or [])[:8],
        "source_digest": {
            "parsed_count": source_digest.get("parsed_count"),
            "by_type": source_digest.get("by_type") or {},
            "items": (source_digest.get("items") or [])[:12],
        },
        "visual_reference_index": {
            "exemplar_count": visual_reference.get("exemplar_count"),
            "by_role": visual_reference.get("by_role") or {},
            "by_density": visual_reference.get("by_density") or {},
        },
        "template_knowledge_base_policy": template_policy,
        "asset_catalog_summary": {
            "count": len(context.get("asset_catalog") or []),
            "sample": (context.get("asset_catalog") or [])[:12],
        },
    }


def _compact_outline_retry_prompt(topic: str, slide_count: int, answers: dict) -> str:
    return f"""
只输出一个合法 JSON 对象，不要 Markdown，不要代码围栏，不要解释。

为这份 PPT 生成 {slide_count} 页英文最小页级大纲。不要输出完整详细 schema，系统会自动补齐缺省字段：
topic: {topic}
audience: {answers.get("audience")}
scenario: {answers.get("scenario")}
story_style: {answers.get("story_style")}
citation_policy: {answers.get("citation_policy")}

JSON schema，严格只使用这些字段：
{{
  "schema_version": "1.0",
  "topic": "{topic}",
  "slide_count": {slide_count},
  "slides": [
    {{
      "index": 1,
      "section": "Cover|Agenda|Motivation|Challenges|Framework|Results|Practice|Roadmap|Summary",
      "title": "short functional title, 2-5 words",
      "kind": "title|section|content|summary",
      "story_role": "cover|section|problem|gap|evidence|experiment|architecture|mechanism|comparison|timeline|risk|summary",
      "layout_type": "title-image|section-divider|problem-framing|gap-matrix|assertion-evidence|evidence-matrix|experiment-result|layered-architecture|process-flow|comparison-matrix|roadmap|risk-boundary-table|closing",
      "visual_type": "diagram|table|image-and-bullets|bullets|evidence-two-box",
      "key_message": "one sentence page takeaway",
      "claim": "one sentence claim, empty for cover/agenda/summary when not needed",
      "assertion_title": "same as claim or empty",
      "claim_type": "fact|inference|hypothesis|proposal|risk|summary",
      "semantic_component_id": "research_agenda.v1|background_trend.v1|challenge_quantification.v1|related_work_matrix.v1|key_insight_mechanism.v1|method_overview.v1|technique_detail.v1|experiment_result.v1|ablation_comparison.v1|risk_boundary.v1|summary_takeaway.v1",
      "evidence_sentence": "evidence-bound sentence",
      "chart_spec": {{"chart_type":"bar|line|matrix|none","data_source":"local path/S id/none","description":"chart purpose"}},
      "citations": ["S1"],
      "bullets": ["4 concise bullets"],
      "source_references": ["local path or S id"]
    }}
  ]
}}

Hard requirements:
- slides length must equal {slide_count}; index values must be 1..{slide_count}.
- Slide 1 is cover. Slide 2 is agenda: title "Agenda", story_role "section", layout_type "roadmap".
- Last slide is summary/roadmap.
- Keep each slide object compact. Do not add extra keys beyond the schema above.
- Use local sources and uploaded PPT/images as auditable evidence candidates where relevant.
- Do not invent precise performance numbers. If evidence is local/internal, mark source_references with local path and use cautious claim_type.
- Keep titles short and functional; put full judgment in claim.
""".strip()



def prepare_model_routed_plan(project_id: str, payload: dict | None = None) -> dict:
    payload = payload or {}
    result = stage_runner.run_stage(
        project_id,
        {
            **payload,
            "stage": "REUSE_OUTLINE",
            "reset_current": bool(payload.get("reset_current", True)),
            "compact": bool(payload.get("compact", True)),
        },
    )
    return {
        "ok": bool(result.get("ok")),
        "provider": "reuse_first_v2",
        "fallback_used": False,
        "quality_risk": None if result.get("ok") else "blocking",
        "need_human_review": True,
        "plan_path": str(project_dir(project_id) / "reuse-first-outline.json") if result.get("ok") else None,
        "result": result,
        "policy": "Legacy model-plan generation is removed. Use REUSE_OUTLINE in the reuse-first V2 pipeline.",
    }

def run_codex_debug(project_id: str, payload: dict | None = None) -> dict:
    return devops.run_codex_debug(project_id, payload or {})


def route_logs(project_id: str) -> list[dict]:
    return route_log.read(project_id)


def stage_state(project_id: str) -> dict:
    state = stage_controller.refresh(project_id)
    diagnostics = stage_diagnostics(project_id)
    for item in state.get("stages") or []:
        stage = str(item.get("stage") or "").upper()
        if stage in diagnostics:
            item["diagnostics"] = diagnostics[stage]
    state["diagnostics"] = diagnostics
    return state


def gate_status(project_id: str, required: list[str] | None = None) -> dict:
    return stage_controller.gate_status(project_id, required)


def slide_state(project_id: str) -> dict:
    return stage_controller.slide_state(project_id)


def confirm_stage(project_id: str, stage: str, payload: dict | None = None) -> dict:
    payload = payload or {}
    return stage_controller.confirm(
        project_id,
        stage,
        note=payload.get("note"),
        force=bool(payload.get("force", False)),
    )


# Editable stage artifacts -> validate-artifact.sh kind (others are written unvalidated).
_ARTIFACT_VALIDATOR_KIND = {
    "reuse-first-outline.json": "reuse-first-outline",
    "draft-assembly-plan.json": "draft-assembly-plan",
    "slide-gap-plan.json": "slide-gap-plan",
    "slide-composition.json": "slide-composition",
    "manuscript.md": "manuscript",
    "visual-plan.json": "visual-plan",
    "style-guide.md": "style-guide",
    "template-binding.json": "template-binding",
    "style-unification-plan.json": "style-unification-plan",
}


def edit_stage_artifact(project_id: str, stage: str, payload: dict | None = None) -> dict:
    """Human-in-the-loop edit of a stage's output artifact: overwrite it (with JSON or
    text content), validate when a schema validator exists (reverting on failure), then
    unconfirm the stage so it re-enters review."""
    payload = payload or {}
    stage = str(stage or "").upper()
    pdir = project_dir(project_id)
    if not (pdir / "app-state.json").exists():
        return {"ok": False, "error": f"unknown project: {project_id}"}

    spec = stage_controller.stage_item(project_id, stage)
    if not spec:
        return {"ok": False, "error": f"unknown stage: {stage}"}

    artifacts = list(spec.get("output_artifacts") or [])
    artifact = payload.get("artifact") or (artifacts[0] if artifacts else None)
    if not artifact:
        return {"ok": False, "error": f"stage {stage} has no editable artifact"}
    if artifact not in artifacts and not payload.get("force_artifact"):
        return {"ok": False, "error": f"{artifact} is not an output of {stage}", "stage_artifacts": artifacts}

    has_json = "json" in payload
    has_content = "content" in payload
    if not has_json and not has_content:
        return {"ok": False, "error": "provide 'json' (object) or 'content' (string)"}

    target = pdir / artifact
    target.parent.mkdir(parents=True, exist_ok=True)
    backup = target.read_text(encoding="utf-8") if target.exists() else None

    if has_json:
        write_json(target, payload["json"])
    else:
        target.write_text(str(payload["content"]), encoding="utf-8")

    kind = _ARTIFACT_VALIDATOR_KIND.get(Path(artifact).name)
    if kind:
        proc = subprocess.run(
            ["bash", str(ROOT / "scripts/validate-artifact.sh"), kind, str(target)],
            cwd=ROOT, text=True, capture_output=True,
        )
        if proc.returncode != 0:
            if backup is not None:
                target.write_text(backup, encoding="utf-8")
            else:
                target.unlink(missing_ok=True)
            return {
                "ok": False,
                "error": f"edited {artifact} failed {kind} validation; reverted",
                "validator_stderr": (proc.stderr or proc.stdout)[-1500:],
            }

    unconfirmed = stage_controller.unconfirm(project_id, stage, reason="artifact edited by user")
    return {
        "ok": True,
        "project_id": project_id,
        "stage": stage,
        "artifact": artifact,
        "validated": bool(kind),
        "current_stage": unconfirmed.get("current_stage"),
        "stage_state": unconfirmed,
    }


def research_health() -> dict:
    return research.health_check()


def list_projects() -> list[dict]:
    out = []
    if not (ROOT / "projects").exists():
        return out
    for path in sorted((ROOT / "projects").iterdir()):
        if path.is_dir() and (path / "app-state.json").exists():
            out.append(read_json(path / "app-state.json", {}))
    return out
