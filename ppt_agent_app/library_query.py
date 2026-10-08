"""Library query layer (Phase B).

Reads the new directory-tree layout (data/resources_library/material/decks/) and
returns deck/section/slide candidates in the SAME English-keyed shape that
the existing matching cascade expects. This is a thin adapter so we can
swap the storage layer without rewriting the matching skills.

Source of truth:
  data/resources_library/material/
    decks-index.json                    # 28-entry lightweight index
    decks/<dir>/
      deck.json
      section_NN_<slug>/
        section.json
        slide_NN.json

Output of `load_library_candidates(...)`:
    {
      "deck":    [{resource_id, deck_id, source_owner: "library",
                   topic, topic_summary, audience, scenario,
                   presentation_type, narrative_arc, anchor_claims,
                   topic_tags, transferable_to, do_not_reuse_when,
                   slide_count, score, ...}],
      "section": [{resource_id, deck_id, section_id, source_owner: "library",
                   section_index, role, function, summary, transferable_to,
                   do_not_reuse_when, slide_ids, slide_relationships,
                   score, ...}],
      "slide":   [{resource_id, deck_id, section_id, slide_id, source_owner: "library",
                   slide_index, slide_role, title, claim, what_this_slide_explains,
                   text_samples, salient_visuals, transferable_to,
                   do_not_reuse_when, prev_slide_role, next_slide_role,
                   score, ...}],
      "manifest": {schema_version, deck_count, generated_at}
    }
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Iterable

from .models import ROOT


LIB_ROOT = ROOT / "data" / "resources_library" / "material"
DECKS_DIR = LIB_ROOT / "decks"
DECKS_INDEX = LIB_ROOT / "decks-index.json"
LIB_MANIFEST = LIB_ROOT / "manifest.json"


def _project_lib_root(project_id: str) -> Path:
    """Per-project internal deck library — under sources/ since Phase D."""
    return ROOT / "projects" / project_id / "sources"


def _project_decks_dir(project_id: str) -> Path:
    return _project_lib_root(project_id) / "deck"


def _project_decks_index(project_id: str) -> Path:
    return _project_lib_root(project_id) / "decks-index.json"


# --------------------------------------------------------------------------
# Field translation: Chinese-keyed brief schema → English-keyed candidate
# --------------------------------------------------------------------------

def _deck_zh_to_candidate(deck_zh: dict, deck_dir_name: str) -> dict:
    """Translate `decks/<dir>/deck.json` (Chinese keys) to a candidate dict."""
    deck_id = deck_zh.get("deck标识") or deck_dir_name
    return {
        "object_type": "deck",
        "object_id": deck_id,
        "resource_id": deck_id,
        "deck_id": deck_id,
        "source_owner": "library",
        "score": 1.0,
        "deck_dir": deck_dir_name,
        # English-keyed fields used by deck_matching.md skill
        "topic": deck_zh.get("标题"),
        "topic_summary": deck_zh.get("论述总结"),
        "audience": deck_zh.get("目标受众"),
        "scenario": deck_zh.get("适用场景"),
        "presentation_type": deck_zh.get("报告类型"),
        "deck_type": deck_zh.get("报告类型"),
        "narrative_arc": deck_zh.get("论述弧线") or [],
        "topic_tags": deck_zh.get("主题标签") or [],
        "transferable_to": deck_zh.get("适合复用场景") or [],
        "do_not_reuse_when": deck_zh.get("不适合复用场景") or [],
        "slide_count": deck_zh.get("总页数") or 0,
        "section_count": deck_zh.get("章节数") or 0,
        "source_path": deck_zh.get("源文件"),
        "anchor_claims": deck_zh.get("适合复用场景") or [],
    }


def _section_zh_to_candidate(section_zh: dict, deck_id: str, deck_dir_name: str,
                              section_dir_name: str) -> dict:
    """Translate `section.json` (Chinese keys) to a candidate dict."""
    section_id = section_zh.get("章节标识") or f"{deck_id}.sec.{section_zh.get('章节序号'):02d}"
    page_range = section_zh.get("页码范围") or [None, None]
    return {
        "object_type": "section",
        "object_id": section_id,
        "resource_id": section_id,
        "deck_id": deck_id,
        "section_id": section_id,
        "deck_dir": deck_dir_name,
        "section_dir": section_dir_name,
        "source_owner": "library",
        "score": 1.0,
        "section_index": section_zh.get("章节序号"),
        "role": section_zh.get("章节角色"),
        "title": section_zh.get("标题"),
        "function": section_zh.get("章节角色"),
        "narrative_function": section_zh.get("章节叙事"),
        "summary": section_zh.get("章节叙事"),
        "transferable_to": section_zh.get("适合复用场景") or [],
        "do_not_reuse_when": section_zh.get("不适合复用场景") or [],
        "slide_ids": section_zh.get("页ID列表") or [],
        "slide_relationships": section_zh.get("页间关系") or [],
        "page_range": page_range,
        "key_slide_indices": [page_range[0]] if page_range and page_range[0] else [],
    }


def _slide_zh_to_candidate(slide_zh: dict, deck_id: str, section_id: str,
                            deck_dir_name: str, section_dir_name: str) -> dict:
    """Translate `slide_NN.json` (Chinese keys) to a candidate dict."""
    slide_id = slide_zh.get("页标识") or f"{deck_id}.slide_{slide_zh.get('页序号'):02d}"
    text_samples = slide_zh.get("关键文字") or []
    transferable = slide_zh.get("适合复用场景") or []
    avoid = slide_zh.get("不适合复用场景") or []
    visuals = slide_zh.get("视觉骨架") or []

    # Derive `reusability` (4-level enum matching old skill expectations).
    # - hard_topic: broadly transferable, few avoidance constraints
    # - soft_pattern: transferable but has scope constraints
    # - style_only: limited reuse (mostly the visual pattern)
    # - do_not_reuse: explicit avoidance scenarios outweigh transfer ones
    if not transferable:
        reusability = "do_not_reuse" if avoid else "style_only"
    elif len(transferable) >= 3 and not avoid:
        reusability = "hard_topic"
    elif len(transferable) >= 2:
        reusability = "soft_pattern"
    else:
        reusability = "style_only"

    # Derive `evidence_kind` from visual + text density.
    image_count = len(slide_zh.get("资源ID列表") or [])
    if image_count >= 2:
        evidence_kind = "visual_evidence"
    elif visuals:
        evidence_kind = "claim_with_visual"
    elif len(text_samples) >= 4:
        evidence_kind = "claim_with_text"
    else:
        evidence_kind = "claim_only"

    # `rewrite_guidance`: combine avoidance scenarios as concrete things
    # that DRAFT_REVIEW / SLIDE_REWRITE should check + replace.
    rewrite_guidance = (
        "替换前需检查: " + " / ".join(avoid[:3]) if avoid
        else "可直接复用 (按目标项目要求改 metadata)"
    )

    return {
        "object_type": "slide",
        "object_id": slide_id,
        "resource_id": slide_id,
        "deck_id": deck_id,
        "section_id": section_id,
        "slide_id": slide_id,
        "deck_dir": deck_dir_name,
        "section_dir": section_dir_name,
        "source_owner": "library",
        "score": 1.0,
        "slide_index": slide_zh.get("页序号"),
        "slide_role": slide_zh.get("页面角色"),
        "role": slide_zh.get("页面角色"),
        "title": slide_zh.get("标题"),
        "claim": slide_zh.get("核心论断"),
        "what_this_slide_explains": slide_zh.get("本页讲什么"),
        "text_samples": text_samples,
        "salient_visuals": visuals,
        "transferable_to": transferable,
        "do_not_reuse_when": avoid,
        "prev_slide_role": slide_zh.get("上页角色"),
        "next_slide_role": slide_zh.get("下页角色"),
        "asset_ids": slide_zh.get("资源ID列表") or [],
        "image_count": image_count,
        "evidence_kind": evidence_kind,
        "reusability": reusability,
        "rewrite_guidance": rewrite_guidance,
    }


# --------------------------------------------------------------------------
# Coarse-filter helper (for picking top-K decks before loading details)
# --------------------------------------------------------------------------

def _tokenize(text: str | None) -> set[str]:
    if not text:
        return set()
    import re
    # split on non-alnum + lowercase + drop short
    tokens = re.split(r"[^\w一-鿿]+", str(text).lower())
    return {t for t in tokens if len(t) >= 2}


def _deck_score(deck_index_entry: dict, query_tokens: set[str]) -> float:
    """Score a deck-index entry against the project's anchor tokens.
    Higher = more relevant. Used to pick top-K decks for full loading."""
    if not query_tokens:
        return 1.0
    score = 0.0
    # Topic tags are atomic, weight them highest.
    for tag in (deck_index_entry.get("主题标签") or []):
        toks = _tokenize(tag)
        if toks & query_tokens:
            score += 3.0
    # Title / scenario / 论述弧线 contribute mid-weight.
    for field in ("标题", "适用场景"):
        toks = _tokenize(deck_index_entry.get(field))
        if toks & query_tokens:
            score += 2.0
    for arc in (deck_index_entry.get("论述弧线") or []):
        toks = _tokenize(arc)
        if toks & query_tokens:
            score += 1.0
    # 适合复用场景 is also a strong signal.
    for s in (deck_index_entry.get("适合复用场景") or []):
        toks = _tokenize(s)
        if toks & query_tokens:
            score += 2.0
    # Heavy penalty for 不适合 hits — the LLM listed scenarios to avoid.
    for s in (deck_index_entry.get("不适合复用场景") or []):
        toks = _tokenize(s)
        if toks & query_tokens:
            score -= 1.5
    return score


# --------------------------------------------------------------------------
# Public: load all library candidates (or filtered)
# --------------------------------------------------------------------------

def load_decks_index() -> dict:
    """Load decks-index.json. Returns {schema_version, deck_count, decks: [...]}.
    Returns an empty index if the file doesn't exist."""
    if not DECKS_INDEX.exists():
        return {"schema_version": "tree-v1", "deck_count": 0, "decks": []}
    return json.loads(DECKS_INDEX.read_text(encoding="utf-8"))


def load_project_decks_index(project_id: str) -> dict:
    """Load the project-internal decks-index.json (mirror of the global format)."""
    p = _project_decks_index(project_id)
    if not p.exists():
        return {"schema_version": "tree-v1", "deck_count": 0, "decks": []}
    return json.loads(p.read_text(encoding="utf-8"))


def load_one_deck_subtree(deck_dir: Path) -> tuple[dict, list[dict], list[dict]]:
    """Return (deck_dict, sections_list, slides_list) for ONE deck dir.
    All dicts are still in Chinese-keyed schema as stored on disk.
    """
    deck_path = deck_dir / "deck.json"
    if not deck_path.exists():
        return {}, [], []
    deck_zh = json.loads(deck_path.read_text(encoding="utf-8"))
    sections: list[dict] = []
    slides: list[dict] = []
    for sec_dir in sorted(deck_dir.iterdir()):
        if not sec_dir.is_dir() or not sec_dir.name.startswith("section_"):
            continue
        sec_path = sec_dir / "section.json"
        if not sec_path.exists():
            continue
        sec_zh = json.loads(sec_path.read_text(encoding="utf-8"))
        sec_zh.setdefault("_section_dir", sec_dir.name)
        sections.append(sec_zh)
        for slide_path in sorted(sec_dir.glob("slide_*.json")):
            sl_zh = json.loads(slide_path.read_text(encoding="utf-8"))
            sl_zh.setdefault("_section_dir", sec_dir.name)
            slides.append(sl_zh)
    sections.sort(key=lambda s: s.get("章节序号") or 0)
    slides.sort(key=lambda s: s.get("页序号") or 0)
    return deck_zh, sections, slides


def load_library_candidates(
    *,
    top_k_decks: int | None = None,
    query_tokens: set[str] | None = None,
) -> dict:
    """Walk the decks/ tree and emit candidate buckets.

    `top_k_decks`: if set, only the top-K best-matching decks (per
    `query_tokens`) get their sections+slides loaded. Other decks still
    appear in the deck bucket but their sections/slides are SKIPPED (saves
    several MB of token spend in matching). When None, ALL decks load fully.

    Returns the dict described in module docstring.
    """
    index = load_decks_index()
    deck_entries = index.get("decks") or []

    # 1. Score & rank decks (only if we plan to filter).
    scored: list[tuple[float, dict]] = []
    if top_k_decks and query_tokens:
        for entry in deck_entries:
            scored.append((_deck_score(entry, query_tokens), entry))
        scored.sort(key=lambda x: x[0], reverse=True)
        deep_load_ids = {e[1].get("deck标识") for e in scored[:top_k_decks]}
    else:
        deep_load_ids = {e.get("deck标识") for e in deck_entries}

    decks_b: list[dict] = []
    sections_b: list[dict] = []
    slides_b: list[dict] = []

    for entry in deck_entries:
        deck_id = entry.get("deck标识")
        deck_dir_name = entry.get("目录名") or deck_id
        deck_dir = DECKS_DIR / deck_dir_name
        if not deck_dir.is_dir():
            continue

        # Always emit the deck candidate (lightweight).
        deck_cand = _deck_zh_to_candidate(entry, deck_dir_name)
        # Carry per-deck score from coarse filter (default 1.0).
        if scored:
            deck_cand["score"] = next((s for s, e in scored if e.get("deck标识") == deck_id), 1.0)
        decks_b.append(deck_cand)

        # Skip section/slide loading if this deck is below top_k.
        if deck_id not in deep_load_ids:
            continue

        deck_zh, sections_zh, slides_zh = load_one_deck_subtree(deck_dir)
        for sec_zh in sections_zh:
            sec_dir_name = sec_zh.get("_section_dir") or ""
            sec_cand = _section_zh_to_candidate(sec_zh, deck_id, deck_dir_name, sec_dir_name)
            sec_cand["score"] = deck_cand.get("score", 1.0)
            sections_b.append(sec_cand)
        for sl_zh in slides_zh:
            sec_dir_name = sl_zh.get("_section_dir") or ""
            section_id = sl_zh.get("所属章节") or ""
            sl_cand = _slide_zh_to_candidate(sl_zh, deck_id, section_id,
                                              deck_dir_name, sec_dir_name)
            sl_cand["score"] = deck_cand.get("score", 1.0)
            slides_b.append(sl_cand)

    manifest_meta = {
        "schema_version": index.get("schema_version", "tree-v1"),
        "deck_count": index.get("deck_count", len(decks_b)),
        "loaded_with_subtree": len(deep_load_ids),
    }
    if LIB_MANIFEST.exists():
        try:
            lm = json.loads(LIB_MANIFEST.read_text(encoding="utf-8"))
            manifest_meta["generated_at"] = lm.get("generated_at")
            manifest_meta["importer_version"] = lm.get("importer_version")
        except json.JSONDecodeError:
            pass

    return {
        "deck": decks_b,
        "section": sections_b,
        "slide": slides_b,
        "manifest": manifest_meta,
    }


# --------------------------------------------------------------------------
# Project-internal library — same tree layout, under projects/<id>/sources/deck/
# --------------------------------------------------------------------------

def load_project_library_candidates(
    project_id: str,
    *,
    query_tokens: set[str] | None = None,
    project_score_boost: float = 1.5,
) -> dict:
    """Walk the per-project tree at `projects/<id>/sources/deck/` and emit
    candidates in the same English-keyed shape as `load_library_candidates`.

    Each candidate is stamped with `source_owner="project"` and gets a score
    boost (default 1.5) so SECTION/SLIDE_MATCHING surfaces them above
    library candidates with the same relevance.
    """
    decks_dir = _project_decks_dir(project_id)
    index_path = _project_decks_index(project_id)
    if not decks_dir.exists():
        return {"deck": [], "section": [], "slide": [],
                "manifest": {"schema_version": "tree-v1", "deck_count": 0}}

    # Reuse the same loader but point at project paths via temp module override.
    # Simpler: walk directly.
    if index_path.exists():
        index = json.loads(index_path.read_text(encoding="utf-8"))
    else:
        # Fallback: synthesize from deck.json files on disk
        index = {"decks": []}
        for d in sorted(decks_dir.iterdir()):
            if not d.is_dir(): continue
            dj = d / "deck.json"
            if not dj.exists(): continue
            row = json.loads(dj.read_text(encoding="utf-8"))
            index["decks"].append({"deck标识": row.get("deck标识"),
                                   "目录名": d.name,
                                   "标题": row.get("标题"),
                                   "源文件": row.get("源文件"),
                                   "总页数": row.get("总页数"),
                                   "章节数": row.get("章节数"),
                                   "主题标签": row.get("主题标签") or []})

    decks_b: list[dict] = []
    sections_b: list[dict] = []
    slides_b: list[dict] = []

    for entry in index.get("decks") or []:
        deck_id = entry.get("deck标识")
        deck_dir_name = entry.get("目录名") or deck_id
        deck_dir = decks_dir / deck_dir_name
        if not deck_dir.is_dir():
            continue

        deck_cand = _deck_zh_to_candidate(entry, deck_dir_name)
        deck_cand["source_owner"] = "project"
        # coarse-filter score + project boost
        base = _deck_score(entry, query_tokens) if query_tokens else 1.0
        deck_cand["score"] = base + project_score_boost
        decks_b.append(deck_cand)

        # Always deep-load project decks (they're the user's own — high priority)
        _, sections_zh, slides_zh = load_one_deck_subtree(deck_dir)
        for sec_zh in sections_zh:
            sec_dir_name = sec_zh.get("_section_dir") or ""
            sec = _section_zh_to_candidate(sec_zh, deck_id, deck_dir_name, sec_dir_name)
            sec["source_owner"] = "project"
            sec["score"] = deck_cand["score"]
            sections_b.append(sec)
        for sl_zh in slides_zh:
            sec_dir_name = sl_zh.get("_section_dir") or ""
            section_id = sl_zh.get("所属章节") or ""
            sl = _slide_zh_to_candidate(sl_zh, deck_id, section_id, deck_dir_name, sec_dir_name)
            sl["source_owner"] = "project"
            sl["score"] = deck_cand["score"]
            slides_b.append(sl)

    return {
        "deck": decks_b,
        "section": sections_b,
        "slide": slides_b,
        "manifest": {
            "schema_version": "tree-v1",
            "deck_count": len(decks_b),
            "source": "project-internal",
        },
    }


def load_merged_candidates(
    project_id: str,
    *,
    query_tokens: set[str] | None = None,
    top_k_decks: int | None = None,
) -> dict:
    """Convenience: load BOTH global library and project-internal library,
    merge their buckets. Used by `_run_layered_retrieval`."""
    global_lib = load_library_candidates(top_k_decks=top_k_decks, query_tokens=query_tokens)
    proj_lib = load_project_library_candidates(project_id, query_tokens=query_tokens)
    return {
        "deck": list(global_lib.get("deck") or []) + list(proj_lib.get("deck") or []),
        "section": list(global_lib.get("section") or []) + list(proj_lib.get("section") or []),
        "slide": list(global_lib.get("slide") or []) + list(proj_lib.get("slide") or []),
        "manifest": {
            "global": global_lib.get("manifest") or {},
            "project": proj_lib.get("manifest") or {},
        },
    }


# --------------------------------------------------------------------------
# Loader: full Chinese-keyed dicts for a SPECIFIC deck (used by per-stage skills)
# --------------------------------------------------------------------------

def load_deck_md(deck_dir_name: str) -> str:
    """Return the Markdown body of decks/<dir>/deck.md, or empty string."""
    p = DECKS_DIR / deck_dir_name / "deck.md"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def load_section_md(deck_dir_name: str, section_dir_name: str) -> str:
    p = DECKS_DIR / deck_dir_name / section_dir_name / "section.md"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def load_slide_md(deck_dir_name: str, section_dir_name: str, slide_index: int) -> str:
    p = DECKS_DIR / deck_dir_name / section_dir_name / f"slide_{slide_index:02d}.md"
    return p.read_text(encoding="utf-8") if p.exists() else ""


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def find_top_decks_for_intake(intake_light: dict, *, top_n: int = 3,
                                 min_overlap: int = 2) -> list[dict]:
    """WP-E: Find top-N most-matching whole decks for an intake (PPT_material reuse).

    Used by IDEA Mode 1 to flag `selected_primary_deck_to_clone` when one deck
    matches almost perfectly. Downstream SLIDE_MATCHING can then prefer that
    deck for all chapters (deck_bound) instead of cross-deck mosaic.

    Scoring (each axis):
      - topic_tags overlap (substring) — primary
      - report_type match — strong (×2 weight)
      - audience overlap — medium
      - chapter_count proximity — weak

    Returns top-N decks with score breakdown; caller decides if score-1 is
    "good enough" for whole-deck reuse (typically requires total_score >= 4).
    """
    pmh = intake_light or {}   # v2.0 flattened — read top-level fields directly
    user_tags = pmh.get("topic_tags") or []
    if not user_tags:
        user_tags = intake_light.get("extracted_keywords") or []
    structured = intake_light.get("structured_topic") or {}
    intake_deliverable = (structured.get("deliverable_type") or "").strip().lower()
    audience_profile = intake_light.get("audience") or {}
    intake_audience = (audience_profile.get("primary") or "").strip()
    expected_chs = pmh.get("expected_chapters")

    idx = load_decks_index() or {}
    decks = idx.get("decks") or []
    scored: list[dict] = []
    for d in decks:
        if not isinstance(d, dict):
            continue
        deck_tags = d.get("主题标签") if isinstance(d.get("主题标签"), list) else []
        scenario_tags = d.get("适合复用场景") if isinstance(d.get("适合复用场景"), list) else []
        topic_score = 0
        for u in user_tags:
            if not isinstance(u, str) or len(u) < 2:
                continue
            for t in deck_tags + scenario_tags:
                if not isinstance(t, str) or len(t) < 2:
                    continue
                if u in t or t in u:
                    topic_score += 1
                    break
        deck_type = (d.get("报告类型") or "").strip().lower()
        type_match = 1 if (intake_deliverable and deck_type and
                            intake_deliverable in deck_type) else 0
        deck_audience = d.get("目标受众") or ""
        audience_match = 0
        if intake_audience and isinstance(deck_audience, str) and deck_audience:
            if intake_audience[:6] in deck_audience or deck_audience[:6] in intake_audience:
                audience_match = 1
        chap_match = 0
        if expected_chs and d.get("章节数"):
            try:
                diff = abs(int(expected_chs) - int(d["章节数"]))
                if diff <= 1:
                    chap_match = 1
            except (TypeError, ValueError):
                pass
        total = topic_score + type_match * 2 + audience_match + chap_match
        if total < min_overlap:
            continue
        scored.append({
            "deck_id": d.get("deck标识"),
            "目录名": d.get("目录名"),
            "标题": d.get("标题"),
            "报告类型": d.get("报告类型"),
            "总页数": d.get("总页数"),
            "章节数": d.get("章节数"),
            "主题标签": deck_tags,
            "适合复用场景": scenario_tags,
            "score_breakdown": {
                "topic_score": topic_score,
                "type_match": type_match,
                "audience_match": audience_match,
                "chap_match": chap_match,
            },
            "total_score": total,
        })
    scored.sort(key=lambda x: -x["total_score"])
    return scored[:top_n]


def _cli():
    """Quick smoke test:
        python3 -m ppt_agent_app.library_query                 # all decks summary
        python3 -m ppt_agent_app.library_query 大模型推理 投机解码  # filter by tokens
    """
    import sys
    tokens = set(sys.argv[1:])
    bucket = load_library_candidates(
        top_k_decks=8 if tokens else None,
        query_tokens=tokens or None,
    )
    print(f"manifest: {bucket['manifest']}")
    print(f"  deck candidates: {len(bucket['deck'])}")
    print(f"  section candidates: {len(bucket['section'])}")
    print(f"  slide candidates: {len(bucket['slide'])}")
    print()
    print("top decks by score:")
    for d in sorted(bucket["deck"], key=lambda x: -(x.get("score") or 0))[:10]:
        score = d.get("score", 1.0)
        tags = (d.get("topic_tags") or [])[:3]
        print(f"  score={score:6.2f}  {d['deck_id']:<55} tags={tags}  topic={d.get('topic')}")


if __name__ == "__main__":
    _cli()
