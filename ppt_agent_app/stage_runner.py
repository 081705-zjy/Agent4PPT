from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from copy import deepcopy
from pathlib import Path

from . import layout_registry, skill_runtime, stage_controller, template_library
from .models import ROOT, now, project_dir, read_json, update_json, write_json


TERMINAL_STAGES = {"COMPLETE", "ESCALATION", "ERROR"}
FINAL_RENDER_ARTIFACTS = [
    "manuscript.md",
    "visual-plan.json",
    "deck.pptx",
    "render-log.md",
    "structural-validation.md",
    "render-audit.json",
    "run-manifest.json",
    "slides-html",
    "screenshots",
    "svg_build",
    "svg_output",
    "smoke",
]


IDEA_FORBIDDEN_PAGE_LEVEL_KEYS = {
    "slide_stubs",
    "chapter_page_count",
    "page_to_rhythm_node_map",
    "rhythm_adherence",
    "referenced_archetype_ids",
    "page_specific_archetypes",
    "target_title",
    "target_claim",
    "key_points",
    "source_resource_ids",
    "source_slide_id",
    "slides_by_section",
    "library_pool_slide_ids",
}


def _default_structural_page_contract() -> dict:
    """Deck-level structural contract owned by IDEA and materialized by OUTLINE."""
    return {
        "cover": {
            "required": True,
            "position": 1,
            "target_role": "cover",
            "source_policy": "byte_clone_structural_source",
        },
        "agenda": {
            "required": True,
            "position": 2,
            "target_role": "agenda",
            "source_policy": "byte_clone_structural_source",
            "highlight_mode": "all_chapters_black",
        },
        "section_dividers": {
            "required": True,
            "before_each_content_chapter": True,
            "before_each_business_chapter": True,
            "target_role": "section_divider",
            "source_policy": "reuse_agenda_or_divider_structural_source",
            "highlight_mode": "current_chapter_black_others_white",
        },
    }


def _ensure_parallel_group_contracts(data: dict) -> tuple[dict, list[str]]:
    """Ensure IDEA carries executable contracts for repeated parallel groups."""
    out = deepcopy(data) if isinstance(data, dict) else {}
    changes: list[str] = []
    chapters = out.get("chapter_plan") if isinstance(out.get("chapter_plan"), list) else []
    groups: dict[str, list[dict]] = {}
    for ch in chapters:
        if not isinstance(ch, dict):
            continue
        gid = ch.get("parallel_group_id")
        if not gid:
            continue
        groups.setdefault(str(gid), []).append(ch)
    existing = out.get("parallel_group_contracts")
    if not isinstance(existing, list):
        existing = []
        out["parallel_group_contracts"] = existing
    existing_ids = {
        str(c.get("parallel_group_id"))
        for c in existing
        if isinstance(c, dict) and c.get("parallel_group_id")
    }
    for gid, members in groups.items():
        if len(members) < 2 or gid in existing_ids:
            continue
        page_targets = []
        for ch in members:
            try:
                page_targets.append(int(ch.get("expected_pages_indicative") or 0))
            except Exception:
                pass
        target_pages = round(sum(page_targets) / len(page_targets)) if page_targets else 10
        member_ids = []
        for ch in members:
            try:
                member_ids.append(int(ch.get("section_index")))
            except Exception:
                continue
        existing.append({
            "parallel_group_id": gid,
            "member_section_indices": member_ids,
            "canonical_page_budget": {
                "target_pages_per_chapter": target_pages,
                "allowed_delta_pages": 2,
                "allowed_delta_ratio": 0.2,
            },
            "canonical_chapter_skeleton": [
                "section_divider",
                "framework_anchor_current_layer",
                "chapter_scope_overview",
                "work_block_1.paper_intro",
                "work_block_1.challenge",
                "work_block_1.method",
                "work_block_1.result",
                "work_block_2.paper_intro",
                "work_block_2.challenge",
                "work_block_2.method",
                "work_block_2.result",
                "chapter_summary_to_framework",
            ],
            "canonical_work_block_template": ["paper_intro", "challenge", "method", "result"],
            "framework_anchor_policy": {
                "same_source_required": True,
                "source_scope": "global_or_chapter_framework",
                "only_change": ["current_layer_highlight", "title", "text"],
            },
            "source_scope_policy": {
                "global_or_group_recap_targets_cannot_use_single_work_summary": True,
                "work_block_sources_must_match_work_name": True,
            },
            "source": "driver_default_from_parallel_group_id",
        })
        changes.append(f"parallel_group_contracts[{gid}]")
    if changes:
        out.setdefault("provenance", {}).setdefault("driver_normalization", [])
        out["provenance"]["driver_normalization"].append({
            "stage": "IDEA_ANALYSIS",
            "reason": "filled missing executable parallel_group_contracts",
            "fields": changes,
        })
    return out, changes


def _strip_idea_page_level_fields(data: dict) -> tuple[dict, list[str]]:
    """Remove fields that belong to OUTLINE from an IDEA_ANALYSIS payload."""
    removed: list[str] = []

    def _walk(obj, path: str):
        if isinstance(obj, dict):
            out = {}
            for k, v in obj.items():
                child_path = f"{path}.{k}" if path else str(k)
                if k in IDEA_FORBIDDEN_PAGE_LEVEL_KEYS:
                    removed.append(child_path)
                    continue
                out[k] = _walk(v, child_path)
            return out
        if isinstance(obj, list):
            return [_walk(v, f"{path}[{i}]") for i, v in enumerate(obj)]
        return obj

    return _walk(deepcopy(data), ""), removed


def _compact_logic_story_rules_for_idea(rules: list[dict],
                                        *,
                                        max_rules: int = 70) -> list[dict]:
    """Keep only chapter/story-level hard rules for IDEA generation."""
    # Current rule library exposes canonical compact rules that already merge
    # duplicate raw rules. Preserve their action fields instead of reducing them
    # back to one-line titles.
    if any(isinstance(r, dict) and r.get("must") for r in rules):
        selected = []
        for r in rules:
            if not isinstance(r, dict):
                continue
            stage = r.get("stage") or []
            if stage and "IDEA_ANALYSIS" not in stage:
                continue
            selected.append({
                "id": r.get("id"),
                "category": r.get("category"),
                "when": r.get("when"),
                "must": r.get("must"),
                "avoid": r.get("avoid"),
                "check": r.get("check"),
                "source_rule_ids": r.get("source_rule_ids") or [],
            })
            if len(selected) >= max_rules:
                break
        return selected

    keep_categories = {
        "anchor_trajectory",
        "callback",
        "chapter_transitions",
        "comparison_evidence",
        "pacing",
        "repetition_emphasis",
        "role_position",
        "scenario",
        "structural_promise",
        "structure",
    }
    priority_ids = {
        "method_chapter_structural_rhythm_consistency",
        "parallel_representative_work_blocks_same_template",
        "framework_overview_redisplay_at_each_layer_chapter_open",
        "cover_title_callback_in_closing",
        "cover_thesis_callback_in_closing",
        "chapter_outro_hook_required",
        "chapter_end_hook_bridges_to_next_chapter",
        "closing_no_new_content",
        "closing_chapter_includes_future_vision_slide",
        "trend_chapter_follows_method_chapters",
        "motivation_before_method_invariant",
        "closing_required_and_at_last_2_slides",
        "main_thesis_repeated_across_majority_chapters",
    }
    selected: list[dict] = []
    seen: set[str] = set()
    for r in rules:
        rid = r.get("id")
        if rid in priority_ids and rid not in seen:
            selected.append(r)
            seen.add(rid)
    for r in rules:
        rid = r.get("id")
        if rid in seen:
            continue
        if r.get("category") not in keep_categories:
            continue
        selected.append(r)
        seen.add(rid)
        if len(selected) >= max_rules:
            break
    return [
        {
            "id": r.get("id"),
            "category": r.get("category"),
            "hit_rate": r.get("hit_rate"),
            "summary": (r.get("summary") or "")[:90],
        }
        for r in selected[:max_rules]
    ]


def _compact_deck_patterns_for_idea(patterns: list[dict],
                                    *,
                                    max_deck_tasks: int = 8,
                                    max_deck_arcs: int = 14) -> list[dict]:
    """Keep only fields needed for IDEA to choose deck-level pattern IDs."""
    out: list[dict] = []
    counts = {"deck_task": 0, "deck_arc": 0, "other": 0}
    for p in patterns or []:
        if not isinstance(p, dict):
            continue
        kind = str(p.get("pattern_kind") or "deck_arc")
        if kind == "deck_task":
            if counts["deck_task"] >= max_deck_tasks:
                continue
            counts["deck_task"] += 1
            entry = {
                "id": p.get("id") or p.get("pattern_id"),
                "title": p.get("title"),
                "pattern_kind": kind,
                "trigger_signals": (p.get("trigger_signals") or [])[:4],
                "core_task_sequence": (p.get("core_task_sequence") or [])[:6],
                "invariant_principles": (p.get("invariant_principles") or [])[:4],
                "anti_patterns": (p.get("anti_patterns") or [])[:3],
            }
        elif kind == "deck_arc":
            if counts["deck_arc"] >= max_deck_arcs:
                continue
            counts["deck_arc"] += 1
            nodes = []
            for node in (p.get("abstract_node_sequence") or [])[:8]:
                if isinstance(node, dict):
                    nodes.append({
                        "role": node.get("role") or node.get("chapter_role"),
                        "position": node.get("position"),
                        "count": node.get("count"),
                        "page_count_range": node.get("page_count_range"),
                    })
                else:
                    nodes.append(str(node)[:80])
            entry = {
                "id": p.get("id") or p.get("pattern_id"),
                "title": p.get("title"),
                "pattern_kind": kind,
                "applicable_summary": (p.get("applicable_summary") or "")[:220],
                "abstract_node_sequence": nodes,
                "narrative_arc": (p.get("narrative_arc") or [])[:8],
                "anti_patterns": (p.get("anti_patterns") or [])[:3],
                "source_count": p.get("source_count"),
                "confidence": p.get("confidence"),
            }
        else:
            if counts["other"] >= 4:
                continue
            counts["other"] += 1
            entry = {
                "id": p.get("id") or p.get("pattern_id"),
                "title": p.get("title"),
                "pattern_kind": kind,
                "summary": (
                    p.get("applicable_summary")
                    or p.get("narrative_purpose")
                    or p.get("summary")
                    or ""
                )[:220],
            }
        out.append({k: v for k, v in entry.items() if v not in (None, [], {})})
    return out


def _normalize_idea_v61_required_refs(data: dict,
                                      *,
                                      rhythm_patterns_per_role: dict,
                                      library_understanding: dict) -> tuple[dict, list[str]]:
    """Fill mechanical v6.1 library-reference fields before downstream handoff."""
    from . import outline_context as oc

    out = deepcopy(data) if isinstance(data, dict) else {}
    changes: list[str] = []
    divider_exempt_roles = {"opening", "cover", "agenda", "section_divider", "references"}
    material_structural_roles = {
        "opening", "cover", "agenda", "section_divider", "closing", "references",
    }
    chapters = out.get("chapter_plan") if isinstance(out.get("chapter_plan"), list) else []

    contract = out.get("structural_page_contract")
    if not isinstance(contract, dict):
        out["structural_page_contract"] = _default_structural_page_contract()
        changes.append("structural_page_contract")
    else:
        default_contract = _default_structural_page_contract()
        for key, default_value in default_contract.items():
            if not isinstance(contract.get(key), dict):
                contract[key] = default_value
                changes.append(f"structural_page_contract.{key}")
                continue
            for sub_key, sub_value in default_value.items():
                if sub_key not in contract[key]:
                    contract[key][sub_key] = sub_value
                    changes.append(f"structural_page_contract.{key}.{sub_key}")

    for ch in chapters:
        if not isinstance(ch, dict):
            continue
        role = str(ch.get("section_role") or "").lower()
        if role not in divider_exempt_roles:
            if ch.get("requires_section_divider") is not True:
                ch["requires_section_divider"] = True
                changes.append(f"chapter[{ch.get('section_index')}].requires_section_divider")
            if ch.get("structural_prefix_role") != "section_divider":
                ch["structural_prefix_role"] = "section_divider"
                changes.append(f"chapter[{ch.get('section_index')}].structural_prefix_role")
        if not ch.get("section_rhythm_pattern_id"):
            candidates = rhythm_patterns_per_role.get(role) or rhythm_patterns_per_role.get("content") or []
            if candidates:
                pick = candidates[0]
                ch["section_rhythm_pattern_id"] = pick.get("pattern_id")
                ch["section_rhythm_summary"] = (
                    pick.get("applicable_summary")
                    or pick.get("abstract_node_sequence_brief")
                    or ""
                )[:100]
                ch["section_rhythm_source_count"] = pick.get("source_count")
                changes.append(f"chapter[{ch.get('section_index')}].section_rhythm_pattern_id")
        if role not in material_structural_roles and not ch.get("material_section_hints"):
            candidates = []
            try:
                candidates = oc.select_candidate_sections_from_library_understanding(
                    {"provenance": {"library_understanding": library_understanding}},
                    ch,
                    max_sections=3,
                )
            except Exception:
                candidates = []
            hints = []
            for c in candidates:
                if not isinstance(c, dict):
                    continue
                hints.append({
                    "deck_id": c.get("deck_id"),
                    "deck_title": c.get("deck_title"),
                    "section_id": c.get("section_id"),
                    "section_title": c.get("section_title"),
                    "section_role": c.get("section_role"),
                    "expected_slide_capacity": c.get("page_count"),
                    "reason": "driver_filled_from_idea_section_pool",
                })
            if hints:
                ch["material_section_hints"] = hints
                changes.append(f"chapter[{ch.get('section_index')}].material_section_hints")

    if changes:
        prov = out.setdefault("provenance", {})
        prov.setdefault("driver_normalization", [])
        prov["driver_normalization"].append({
            "stage": "IDEA_ANALYSIS",
            "reason": "filled missing v6.1 library-reference fields before review",
            "fields": changes,
        })
    return out, changes


def _backfill_idea_library_pool_from_material_hints(
    data: dict,
    library_understanding: dict,
) -> tuple[dict, int]:
    """Mirror Claude-selected section hints into IDEA's shared library pool.

    IDEA has two section-level material paths: driver-built cascade hierarchy and
    Claude-selected chapter material_section_hints. When the cascade only finds
    decks, the explicit hints are still valid handoff material for OUTLINE, so
    keep provenance consistent by backfilling them into library_understanding.
    """
    out = deepcopy(library_understanding) if isinstance(library_understanding, dict) else {}
    hierarchy = out.setdefault("hierarchy", {})
    if not isinstance(hierarchy, dict):
        hierarchy = {}
        out["hierarchy"] = hierarchy

    top_decks = hierarchy.get("top_decks")
    if not isinstance(top_decks, list):
        top_decks = []
        hierarchy["top_decks"] = top_decks

    sections_by_deck = hierarchy.get("sections_by_deck")
    if not isinstance(sections_by_deck, dict):
        sections_by_deck = {}
        hierarchy["sections_by_deck"] = sections_by_deck

    top_deck_ids = {
        str(d.get("deck_id"))
        for d in top_decks
        if isinstance(d, dict) and d.get("deck_id")
    }
    section_ids = [
        str(sid) for sid in (out.get("relevant_section_ids") or [])
        if sid
    ]
    section_id_set = set(section_ids)

    existing_by_deck: dict[str, set[str]] = {}
    for did, rows in sections_by_deck.items():
        if not isinstance(rows, list):
            continue
        existing_by_deck[str(did)] = {
            str(r.get("section_id"))
            for r in rows
            if isinstance(r, dict) and r.get("section_id")
        }

    def _intish(value) -> int:
        try:
            return int(value or 0)
        except Exception:
            return 0

    backfilled = 0
    capacity_sum = _intish(out.get("total_relevant_slides_estimate"))
    for ch in data.get("chapter_plan") or []:
        if not isinstance(ch, dict):
            continue
        for hint in ch.get("material_section_hints") or []:
            if not isinstance(hint, dict):
                continue
            did = str(hint.get("deck_id") or "").strip()
            sid = str(hint.get("section_id") or "").strip()
            if not did or not sid:
                continue
            expected_capacity = _intish(
                hint.get("expected_slide_capacity")
                or hint.get("page_count")
                or hint.get("n_slides_in_pool")
            )
            if did not in top_deck_ids:
                top_decks.append({
                    "deck_id": did,
                    "deck_title": hint.get("deck_title") or hint.get("deck") or "",
                    "score": None,
                    "n_relevant_slides": expected_capacity,
                    "source": "chapter_material_section_hints",
                })
                top_deck_ids.add(did)
            rows = sections_by_deck.setdefault(did, [])
            existing = existing_by_deck.setdefault(did, set())
            if sid in existing:
                continue
            rows.append({
                "section_id": sid,
                "section_title": hint.get("section_title") or hint.get("title") or "",
                "section_role": hint.get("section_role"),
                "n_slides_in_pool": expected_capacity,
                "score": hint.get("rank_score") or hint.get("score"),
                "source": "chapter_material_section_hints",
                "reason": hint.get("reason"),
            })
            existing.add(sid)
            if sid not in section_id_set:
                section_ids.append(sid)
                section_id_set.add(sid)
            capacity_sum += expected_capacity
            backfilled += 1

    if backfilled:
        out["relevant_section_ids"] = section_ids
        out["relevant_sections_count"] = len(section_ids)
        out["total_relevant_slides_estimate"] = max(
            _intish(out.get("total_relevant_slides_estimate")),
            capacity_sum,
        )
        out["material_hints_backfilled_from_chapter_plan_count"] = backfilled
    return out, backfilled


def _mark_parallel_framework_source_reuse(outline_doc: dict,
                                          idea_analysis: dict) -> dict:
    """Mark intentional same-source framework anchors across parallel chapters."""
    out = deepcopy(outline_doc) if isinstance(outline_doc, dict) else {}
    slides = out.get("slides")
    contracts = idea_analysis.get("parallel_group_contracts") if isinstance(idea_analysis, dict) else []
    if not isinstance(slides, list) or not isinstance(contracts, list):
        return out
    member_to_group: dict[int, str] = {}
    for contract in contracts:
        if not isinstance(contract, dict):
            continue
        policy = contract.get("framework_anchor_policy") or {}
        if policy.get("same_source_required") is not True:
            continue
        gid = str(contract.get("parallel_group_id") or "")
        for ci in contract.get("member_section_indices") or []:
            try:
                member_to_group[int(ci)] = gid
            except Exception:
                continue
    if not member_to_group:
        return out
    for slide in slides:
        if not isinstance(slide, dict):
            continue
        try:
            ci = int(slide.get("chapter_index") or slide.get("section_index") or 0)
        except Exception:
            continue
        gid = member_to_group.get(ci)
        if not gid:
            continue
        role = str(slide.get("target_role") or "").lower()
        text = " ".join([
            str(slide.get("target_title") or ""),
            str(slide.get("target_claim") or ""),
            str(slide.get("archetype") or ""),
        ]).lower()
        if role not in {"framework", "framework_recap", "method", "content"}:
            continue
        if not any(t in text for t in ("framework", "recap", "框架", "三层", "定位", "高亮")):
            continue
        slide["same_source_intent"] = {
            "allowed": True,
            "reason": (
                "parallel_group framework anchors intentionally reuse the same source "
                "template; downstream rewrite changes chapter highlight/text"
            ),
            "parallel_group_id": gid,
        }
    return out


def _idea_resource_library_contract(oc) -> dict:
    """Return the part of the library contract IDEA_ANALYSIS is allowed to use."""
    contract = oc.load_resource_library_contract_summary()
    if not isinstance(contract, dict):
        return {}
    out = deepcopy(contract)
    rule = out.get("rule")
    if isinstance(rule, dict):
        rule.pop("page_specific", None)
        rule["role"] = "logic_story constraints only for IDEA; page_specific belongs to OUTLINE"
    out["stage_contract"] = {
        "IDEA_ANALYSIS": (
            "select deck-level task/arc patterns, chapter roles, section rhythm pattern, "
            "rough page budget, cross-chapter hooks, and deck/section material hints; "
            "no slide_stubs or source binding"
        ),
        "OUTLINE_GENERATION": (
            "uses IDEA chapter intent plus logic/section_level, rule/page_specific, "
            "and material slide briefs to create slide stubs and bind real sources"
        ),
    }
    return out


def _config() -> dict:
    return read_json(ROOT / "config/default_config.json", {})


def _load_template_kb(project_id: str) -> dict:
    library = template_library.load(ensure=True)
    return {
        "schema_version": "2.0",
        "source": "template_library_v2",
        "manifest": library.get("manifest") or {},
        "deck_profiles": library.get("deck_profiles") or {},
        "section_profiles": library.get("section_profiles") or {},
        "slide_profiles": library.get("slide_profiles") or {},
        "component_profiles": library.get("component_profiles") or {},
        "asset_profiles": library.get("asset_profiles") or {},
        "narrative_patterns": library.get("narrative_patterns") or {},
    }


def _load_template_units(project_id: str) -> dict:
    pdir = project_dir(project_id)
    candidates = read_json(pdir / "template-library-candidates.json", {})
    if not candidates:
        try:
            candidates = template_library.query_for_project(project_id)
        except Exception:
            candidates = {}
    rows = candidates.get("candidates") if isinstance(candidates, dict) else []
    rows = rows if isinstance(rows, list) else []
    return {
        "schema_version": "2.0",
        "source": "template_library_candidates",
        "candidate_count": len(rows),
        "unit_count": len(rows),
        "by_type": candidates.get("by_type") if isinstance(candidates, dict) else {},
        "units": rows,
        "policy": {
            "template_source": "V2 reads data/resources_library/material candidates only.",
            "semantic_audit_required": True,
        },
    }


def _template_reuse_context() -> dict:
    library = template_library.load(ensure=True)
    manifest = library.get("manifest") or {}
    deck_rows = (library.get("deck_profiles") or {}).get("decks") or []
    pattern_rows = (library.get("narrative_patterns") or {}).get("patterns") or []
    semantic_rows = (library.get("semantic_profiles") or {}).get("decks") or []
    semantic_by_id = {
        str(s.get("deck_id")): s
        for s in semantic_rows if isinstance(s, dict) and s.get("deck_id")
    }
    deck_brief = []
    for deck in deck_rows[:20]:
        if not isinstance(deck, dict):
            continue
        sem = semantic_by_id.get(str(deck.get("deck_id"))) or {}
        deck_brief.append({
            "deck_id": deck.get("deck_id"),
            "source_path": deck.get("source_path"),
            "template_scope": deck.get("template_scope"),
            "template_type": deck.get("template_type"),
            "topic_summary": deck.get("topic_summary"),
            "narrative_arc": deck.get("narrative_arc") or [],
            "slide_count": len(deck.get("slides") or []),
            "semantic": sem.get("deck_semantics") if sem else None,
        })
    # 老的 skills/template_library/ (reuse_policy.md + deck_analysis.md) 已删除;
    # 相关字段保留为空字符串以保持下游 dict shape 兼容。
    return {
        "template_library_policy": "",
        "template_library_analysis_skill": "",
        "template_library_manifest": {
            "source": "data/resources_library/material",
            "source_count": manifest.get("source_count"),
            "deck_count": manifest.get("deck_count"),
            "slide_count": manifest.get("slide_count"),
            "component_count": manifest.get("component_count"),
            "asset_count": manifest.get("asset_count"),
            "source_hash": manifest.get("source_hash"),
            "semantic_count": len(semantic_rows),
        },
        "template_library_decks": deck_brief,
        "template_library_narrative_patterns": pattern_rows[:20] if isinstance(pattern_rows, list) else [],
        "reuse_first_policy": {
            "project_sources": "Current project sources are first-class candidates for direct/partial reuse after semantic audit.",
            "topic_templates": "Use topic templates for narrative patterns, slide logic, layout structure, component relations, image explanation, and visual rhythm. Direct copy is allowed only after topic/claim/object/caption/source-context audit.",
            "basic_template": "Use templates/basic as the final identity shell: cover/ending, title rule, typography, footer, page number, and citation style.",
            "template_source": "Use data/resources_library/material as the only system template knowledge source in V2 generation.",
        },
    }


def _stage_names() -> list[str]:
    return [str(item.get("stage")) for item in skill_runtime.stage_specs() if item.get("stage")]


def _advance_current_to_first_blocker(project_id: str, lower_bound_stage: str | None = None, *, force_lower_bound: bool = False) -> dict:
    state = stage_controller.refresh(project_id)
    stages = state.get("stages") or []
    order = [str(item.get("stage") or "").upper() for item in stages]
    start_idx = 0
    current = str(state.get("current_stage") or "").upper()
    if current in order:
        start_idx = order.index(current)
    lower = str(lower_bound_stage or "").upper()
    if lower in order:
        lower_idx = order.index(lower)
        start_idx = lower_idx if force_lower_bound else max(start_idx, lower_idx)
    for item in stages[start_idx:]:
        status = str(item.get("status") or "")
        artifact_status = str(item.get("artifact_status") or "")
        if artifact_status not in {"ready", "not_required"}:
            return stage_controller.set_current_stage(project_id, str(item.get("stage") or "BRIEF"))
        if (item.get("human_gate") or item.get("review_gate")) and not item.get("confirmed"):
            return stage_controller.set_current_stage(project_id, str(item.get("stage") or "BRIEF"))
        if status in {"pending", "partial"}:
            return stage_controller.set_current_stage(project_id, str(item.get("stage") or "BRIEF"))
    return stage_controller.set_current_stage(project_id, "COMPLETE")


def _select_earliest_upstream(current: str, candidates: list) -> str | None:
    """Port of state.sh select_earliest_upstream/is_valid_revision_route: among the
    candidates, pick the one with the smallest stage index that is strictly upstream of
    ``current`` and not terminal. Returns None if none qualify."""
    order = _stage_names()
    current = str(current).upper()
    if current not in order:
        return None
    ci = order.index(current)
    best, best_idx = None, len(order)
    for cand in candidates or []:
        c = str(cand or "").upper()
        if not c or c in TERMINAL_STAGES or c not in order:
            continue
        idx = order.index(c)
        if idx < ci and idx < best_idx:
            best, best_idx = c, idx
    return best


def _write_escalation(project_id: str, reason: str, revision_state: dict) -> dict:
    pdir = project_dir(project_id)
    payload = {
        "schema_version": "1.0",
        "generated_at": now(),
        "source": "stage_runner",
        "reason": reason,
        "rounds": int(revision_state.get("rounds", 0)),
        "stall_streak": int(revision_state.get("stall_streak", 0)),
        "last_rollback": revision_state.get("last_rollback"),
        "history": revision_state.get("history", []),
    }
    write_json(pdir / "escalation.json", payload)
    lines = [
        "---",
        'schema_version: "1.0"',
        f'generated_at: "{now()}"',
        "---",
        "# Escalation",
        "",
        f"- Reason: {reason}",
        f"- Review rounds: {payload['rounds']}",
        f"- Repeated rollback target: {payload['last_rollback']} (x{payload['stall_streak']})",
        "",
        "Automatic revision budget exhausted; human intervention required.",
        "",
    ]
    (pdir / "escalation.md").write_text("\n".join(lines), encoding="utf-8")
    return payload


def _apply_revision_budget(project_id: str, from_stage: str, target: str) -> dict:
    """Account one revision round toward the target rollback stage and decide whether to
    keep looping or escalate (max_review_rounds / circuit_breaker_threshold)."""
    cfg = _config()
    max_rounds = int(cfg.get("max_review_rounds") or 8)
    breaker = int(cfg.get("circuit_breaker_threshold") or 3)

    def mutate(state: dict) -> dict:
        state.setdefault("schema_version", "1.0")
        state["rounds"] = int(state.get("rounds", 0)) + 1
        prev_streak = int(state.get("stall_streak", 0))
        state["stall_streak"] = prev_streak + 1 if state.get("last_rollback") == target else 1
        state["last_rollback"] = target
        state["updated_at"] = now()
        history = state.setdefault("history", [])
        history.append({"from": from_stage, "to": target, "round": state["rounds"], "at": now()})
        return state

    state = update_json(project_dir(project_id) / "revision-state.json", mutate, {})
    if state["rounds"] >= max_rounds or state["stall_streak"] >= breaker:
        reason = (
            f"max_review_rounds={max_rounds} reached"
            if state["rounds"] >= max_rounds
            else f"circuit breaker: rollback to {target} repeated {state['stall_streak']} times"
        )
        _write_escalation(project_id, reason, state)
        return {"next_stage": "ESCALATION", "rollback": True, "escalate": True, "reason": reason, "target": target}
    return {
        "next_stage": target,
        "rollback": True,
        "escalate": False,
        "reason": f"rollback to {target}",
        "target": target,
        "round": state["rounds"],
    }


def resolve_transition(project_id: str, stage: str) -> dict:
    """Determine the next stage after ``stage`` completes. Most stages return their static
    next_stage; REVISION_DECISION and FINAL_ACCEPT resolve dynamically from the revision
    plan / acceptance verdict, enforcing the bounded review loop with escalation."""
    stage = str(stage).upper()
    pdir = project_dir(project_id)
    item = stage_controller.stage_item(project_id, stage)
    static_next = item.get("next_stage")

    if stage == "REVISION_DECISION":
        plan = read_json(pdir / "revision-plan.json", {})
        rtype = str(plan.get("revision_type") or "").upper()
        if rtype in {"", "NONE"}:
            return {"next_stage": static_next, "rollback": False, "escalate": False, "reason": "no revision required"}
        target = _select_earliest_upstream(stage, [plan.get("rollback_stage")])
        if not target:
            return {"next_stage": static_next, "rollback": False, "escalate": False, "reason": "no valid upstream route; proceeding"}
        return _apply_revision_budget(project_id, stage, target)

    if stage == "FINAL_ACCEPT":
        final = read_json(pdir / "final-report.json", {})
        if str(final.get("acceptance_status")) == "rejected":
            target = _select_earliest_upstream(stage, [final.get("rollback_stage") or "RENDER"])
            if target:
                return _apply_revision_budget(project_id, stage, target)
        return {"next_stage": None, "rollback": False, "escalate": False, "reason": "accepted"}

    return {"next_stage": static_next, "rollback": False, "escalate": False, "reason": "linear"}


def _current_or_requested(project_id: str, stage: str | None) -> str:
    if stage:
        return stage.upper()
    state = stage_controller.refresh(project_id)
    return str(state.get("current_stage") or "BRIEF").upper()


def _answers(project_id: str) -> dict:
    state = read_json(project_dir(project_id) / "app-state.json", {})
    return dict(state.get("answers") or {})


def _task_type(answers: dict) -> str:
    text = " ".join(str(answers.get(k) or "") for k in ("topic", "scenario", "style", "audience")).lower()
    if any(word in text for word in ("论文", "literature", "paper", "academic")):
        return "literature_review"
    if any(word in text for word in ("产品", "product", "pitch")):
        return "product_pitch"
    if any(word in text for word in ("方案", "架构", "technical", "技术", "report")):
        return "technical_report"
    if any(word in text for word in ("高管", "executive", "管理")):
        return "executive_briefing"
    return "general_presentation"


def _count_resource_types(resources: list | dict | None) -> dict:
    counts: dict[str, int] = {}
    for item in resources if isinstance(resources, list) else []:
        typ = str(item.get("type") or "file")
        counts[typ] = counts.get(typ, 0) + 1
    return counts


def _parse_reuse_rate_from_text(*values: object) -> float:
    """Best-effort fallback parser for user-level draft reuse intent."""
    text = " ".join(str(v or "") for v in values).strip()
    if not text:
        return 0.7
    percent_match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*%", text)
    if percent_match:
        value = float(percent_match.group(1)) / 100.0
        return max(0.0, min(1.0, value))
    decimal_match = re.search(r"\b0\.\d+\b", text)
    if decimal_match:
        return max(0.0, min(1.0, float(decimal_match.group(0))))
    lowered = text.lower()
    if any(word in lowered for word in ("激进", "尽量", "全量", "直接复制", "direct", "aggressive", "high reuse")):
        return 0.9
    if any(word in lowered for word in ("谨慎", "少量", "low reuse", "new authoring")):
        return 0.5
    return 0.7


def _run_idea_intake_light(project_id: str) -> dict:
    """Lightweight structured analysis of the user's raw BRIEF answers.

    Runs RIGHT AFTER BRIEF (intake). The output `idea-intake-light.json` is
    consumed by:
      - SOURCE_UNDERSTAND (uses light analysis to drive brief-aware source
        analysis)
      - IDEA_ANALYSIS (uses light analysis + logic/rule libraries + compact
        section-level material pool to design the chapter blueprint)

    Lightweight: just structure the raw answers, do NOT design / invent.
    """
    from . import claude_cli, outline_context as oc

    pdir = project_dir(project_id)
    qs = read_json(pdir / "question-state.json", {}) or {}
    answers = qs.get("answers") if isinstance(qs, dict) else {}
    answers = answers if isinstance(answers, dict) else {}

    context = {
        "question_state": {"answers": answers},
        "resource_library_contract": oc.load_resource_library_contract_summary(),
    }
    prompt = (
        "Read the raw BRIEF answers and produce idea-intake-light.json per "
        "the skill schema. Lightweight structuring only — do NOT design or "
        "invent. Use resource_library_contract only to choose valid enums, "
        "keywords, and downstream matching hints for the current material/logic/rule "
        "libraries. Output strict JSON.\n\nINPUT:\n"
        + json.dumps(context, ensure_ascii=False)
    )
    outcome = claude_cli.call_claude_json(
        prompt,
        skill=["skills/idea/idea_intake_light.md"],
        timeout=300,
    )
    if not (outcome.get("ok") and isinstance(outcome.get("data"), dict)):
        _write_stage_status(pdir, "idea-intake-status.json",
                             status="failed",
                             human_approved=False,
                             source="failed",
                             fallback_reason=outcome.get("error"),
                             # 统一 schema: 所有 status 都带 loop 状态字段供 UI 统一解析
                             awaiting_human_review=False,
                             human_feedback_round=0)
        return {"ok": False, "stage": "IDEA_INTAKE_LIGHT",
                "error": (f"Claude CLI failed for IDEA_INTAKE_LIGHT: "
                          f"{(outcome.get('error') or 'unknown')[:400]}"),
                "retry_hint": "重跑 IDEA_INTAKE_LIGHT；当前流程不再写 deterministic stub 继续下游。",
                "raw_excerpt": (outcome.get("raw_excerpt") or "")[:400]}

    data = outcome["data"]
    data.setdefault("schema_version", "2.0")   # v2.0 (2026-07-30) compact schema
    data["generated_at"] = now()
    data["source"] = "claude"
    # v2.1 (2026-07-30): raw_user_input dropped — no downstream stage reads it.
    # OUTLINE_GENERATION reads user_outline directly from question-state (its ONLY
    # raw need); IDEA_ANALYSIS uses the structured story_mode field.
    write_json(pdir / "idea-intake-light.json", data)
    _write_stage_status(pdir, "idea-intake-status.json",
                         source="claude",
                         story_mode=data.get("story_mode"),
                         deliverable_type=(data.get("topic") or {}).get("deliverable_type"),
                         keyword_count=len(data.get("keywords") or []),
                         awaiting_human_review=False,
                         human_feedback_round=0)
    return {
        "ok": True, "stage": "IDEA_INTAKE_LIGHT",
        "idea_intake_light": str(pdir / "idea-intake-light.json"),
        "source": "claude",
        "story_mode": data.get("story_mode"),
        "deliverable_type": (data.get("topic") or {}).get("deliverable_type"),
        "keyword_count": len(data.get("keywords") or []),
        "narrative_signal": data.get("narrative_signal"),
    }


def _render_idea_human_summary(data: dict, pdir, claude_cli) -> None:
    """Re-render idea-analysis.md via idea_human_summary skill (used after human-fix)."""
    try:
        md_prompt = (
            "Render idea-analysis.md per the idea_human_summary skill. "
            "Output the raw markdown text only — do NOT wrap in JSON, do NOT "
            "add code fences around the whole document.\n\n"
            "INPUT idea_analysis:\n" + json.dumps(data, ensure_ascii=False)
        )
        if not hasattr(claude_cli, "call_claude_text"):
            return
        md_out = claude_cli.call_claude_text(
            md_prompt,
            skill=["skills/idea/idea_human_summary.md"],
            timeout=600,
        )
        if md_out and md_out.get("ok") and md_out.get("text"):
            (pdir / "idea-analysis.md").write_text(md_out["text"], encoding="utf-8")
    except Exception as exc:
        print(f"[IDEA_ANALYSIS] re-render idea-analysis.md failed: {exc}", flush=True)


def _run_idea_human_fix_round(project_id: str, pdir, prior_analysis: dict,
                                human_txt, *, oc, claude_cli) -> dict:
    """Big-loop human-fix round for IDEA_ANALYSIS (mirror OUTLINE).

    Trigger: user 写入 idea-human-feedback.txt (自然语言) 后再调 run_stage("IDEA_ANALYSIS").
    Flow:
      1. structurer: idea_revision.md mode=structure_only → idea-human-issues.json
      2. fix: idea_fix_from_review.md (issues source=human, + pattern bodies)
      3. archive human_txt to .applied.round-N
      4. re-render idea-analysis.md
      5. update idea-user-status.json (keep human_approved=True, awaiting_human_review=true)
    """
    raw_text = human_txt.read_text(encoding="utf-8").strip()
    if not raw_text:
        return {"ok": False, "stage": "IDEA_ANALYSIS",
                "error": "idea-human-feedback.txt 为空, 无法处理"}

    prior_status = read_json(pdir / "idea-user-status.json", {}) or {}
    feedback_round = int(prior_status.get("human_feedback_round", 0)) + 1

    print(f"[IDEA_ANALYSIS] human-fix round {feedback_round} triggered "
          f"({len(raw_text)} chars feedback)", flush=True)

    # ─── Step 1: structure natural language → issues ───
    structurer_input = {
        "mode": "structure_only",
        "current_idea_analysis": prior_analysis,
        "user_feedback": {"feedback_round": feedback_round, "raw_text": raw_text},
        "source_understanding": (read_json(pdir / "data" / "source-understanding.json", None)
                                  or read_json(pdir / "source-understand.json", None)
                                  or {}),
    }
    structurer_prompt = (
        "Run idea_revision.md in structure_only mode. Parse user's natural-language "
        "feedback into structured issues (source=human). DO NOT modify idea-analysis.json. "
        "Output {mode, feedback_round, issues[], ambiguous[], rejected[], summary} JSON.\n\n"
        "INPUT:\n" + json.dumps(structurer_input, ensure_ascii=False)
    )
    structurer_out = claude_cli.call_claude_json(
        structurer_prompt,
        skill=["skills/idea/idea_revision.md"],
        timeout=360,
    )
    if not (structurer_out.get("ok") and isinstance(structurer_out.get("data"), dict)):
        return {"ok": False, "stage": "IDEA_ANALYSIS",
                "error": f"structurer 失败: {(structurer_out.get('error') or '')[:200]}",
                "human_feedback_round": feedback_round}
    structured = structurer_out["data"]
    write_json(pdir / "idea-human-issues.json", structured)
    issues_raw = structured.get("issues") or []
    ambiguous_ct = len(structured.get("ambiguous") or [])
    rejected_ct = len(structured.get("rejected") or [])
    print(f"[IDEA_ANALYSIS] human-fix rnd{feedback_round} structurer: "
          f"issues={len(issues_raw)} ambiguous={ambiguous_ct} rejected={rejected_ct}",
          flush=True)

    if not issues_raw:
        _archive_human_txt(human_txt, feedback_round, suffix="no-issues")
        return {"ok": True, "stage": "IDEA_ANALYSIS",
                "idea_analysis": str(pdir / "idea-analysis.json"),
                "human_feedback_round": feedback_round,
                "awaiting_human_review": True,
                "warning": (f"structurer 未产出任何可执行 issue "
                            f"(ambiguous={ambiguous_ct}, rejected={rejected_ct}); "
                            f"prior analysis 未改, 请人类补充/澄清 feedback")}

    # ─── Step 2: surgical fix ───
    primary_pid = ((prior_analysis.get("selected_narrative_arc") or {})
                   .get("primary_pattern_id"))
    selected_pattern_body = (oc.load_deck_level_pattern_full(primary_pid)
                              if primary_pid else None)
    rhythm_bodies: dict = {}
    for ch in (prior_analysis.get("chapter_plan") or []):
        rpid = ch.get("section_rhythm_pattern_id") if isinstance(ch, dict) else None
        if rpid and rpid not in rhythm_bodies:
            b = oc.load_rhythm_pattern_trimmed(rpid)
            if b:
                rhythm_bodies[rpid] = b
    hard_rules = oc.load_logic_story_hard_rules_summary()

    fix_input = {
        "prior_idea_analysis": prior_analysis,
        "issues": issues_raw,
        "logic_story_hard_rules_summary": hard_rules,
        "selected_narrative_pattern_body": selected_pattern_body,
        "rhythm_pattern_bodies": rhythm_bodies,
    }
    fix_prompt = (
        "Apply surgical fix per the idea_fix_from_review skill. Output complete "
        "patched idea-analysis.json v6.1 (strict JSON, all original fields preserved, "
        "only flagged locations modified, add/update fix_round + "
        "referenced_review_issues + user_concern_history).\n\n"
        "INPUT:\n" + json.dumps(fix_input, ensure_ascii=False)
    )
    fix_out = claude_cli.call_claude_json(
        fix_prompt,
        skill=["skills/idea/idea_fix_from_review.md"],
        timeout=600,
    )
    if not (fix_out.get("ok") and isinstance(fix_out.get("data"), dict)):
        return {"ok": False, "stage": "IDEA_ANALYSIS",
                "error": f"human-fix 失败: {(fix_out.get('error') or '')[:200]}",
                "human_feedback_round": feedback_round}
    patched = fix_out["data"]
    patched["generated_at"] = now()
    patched["source"] = "claude_human_surgical_fix"
    write_json(pdir / "idea-analysis.json", patched)

    # ─── Step 3: archive human_txt ───
    _archive_human_txt(human_txt, feedback_round, suffix="applied")

    # ─── Step 4: re-render idea-analysis.md ───
    _render_idea_human_summary(patched, pdir, claude_cli)

    # ─── Step 5: update status ───
    # 保留 UI 在 prior_status 里可能显式设的 human_approved (Q9 fix): 大 loop
    # 只是修当前阶段, 不该悄悄把 UI 的 "不同意" 重置为 True
    _prior_human_approved = prior_status.get("human_approved")
    _write_stage_status(pdir, "idea-user-status.json",
                         human_approved=(True if _prior_human_approved is None
                                          else bool(_prior_human_approved)),
                         story_design_mode=patched.get("story_design_mode"),
                         fix_round=patched.get("fix_round", 0),
                         human_feedback_round=feedback_round,
                         awaiting_human_review=True,
                         codex_review_skipped=True,
                         codex_final_ok=None,
                         post_human_fix_issues_count=0)

    return {"ok": True, "stage": "IDEA_ANALYSIS",
            "idea_analysis": str(pdir / "idea-analysis.json"),
            "source": patched.get("source"),
            "human_feedback_round": feedback_round,
            "fix_round": patched.get("fix_round", 0),
            "awaiting_human_review": True,
            "codex_review_skipped": True,
            "codex_final_ok": None,
            "post_human_fix_issues_count": 0,
            "structurer_summary": structured.get("summary")}


def _run_idea_analysis(project_id: str) -> dict:
    """Brief analysis: data-grounded narrative architect.

    每次调用: 若人类写了 idea-human-feedback.txt 且已有 prior analysis → 走大 loop
    surgical fix; 否则从头跑 Fresh Analysis。

    Inputs (compact):
      1. idea-intake-light.json (structured brief)
      2. logic patterns (deck_level task/arc + section_level rhythm)
      3. logic_story hard rules summary
      4. compact section-level library pool

    Modes (auto-detect from story_style field):
      - AUTO: empty story_style → fully autonomous design, MUST use data
      - STRICT: numbered chapters → strict section count
      - SOFT: prose intent → Claude decides section count

    Pipeline:
      Gate: check idea-intake-status.human_approved (default pass)
      大 loop: 若 idea-human-feedback.txt 存在 → _run_idea_human_fix_round → return
      Step 1: fresh analysis (single Claude call, narrative + chapter plan only)
      Step 2: write idea-analysis.json / idea-review.json / idea-user-status.json
      Step 3: render idea-analysis.md (fail loudly if md render fails)
    """
    from . import claude_cli
    from . import outline_context as oc

    pdir = project_dir(project_id)

    # ═══ Big-loop branch: human natural-language feedback fix ═══
    # **优先级最高 (放在 gate 前)**: 人类写反馈 = 想修当前阶段, gate 只该挡"推进",
    # 不该挡"修当前". 若人类写入 idea-human-feedback.txt 且已有 prior analysis,
    # 走 structure_only → idea_fix_from_review 的 Claude-only 手术式 fix 路径,
    # 不动主生成/小 loop 已产出的结果。大 loop 不限次数, 人类可反复写 txt 触发。
    human_txt = pdir / "idea-human-feedback.txt"
    existing_analysis_early = read_json(pdir / "idea-analysis.json", None)
    if human_txt.exists() and existing_analysis_early:
        return _run_idea_human_fix_round(
            project_id, pdir, existing_analysis_early, human_txt,
            oc=oc, claude_cli=claude_cli,
        )

    # ═══ Gate: 上一阶段 (IDEA_INTAKE_LIGHT) 人类 approve 检查 ═══
    # gate 只挡"从头跑主生成"路径; 大 loop 修当前阶段 (上方) 不受 gate 影响
    _gate_fail = _check_upstream_approval(
        pdir, "idea-intake-status.json",
        upstream_stage_label="IDEA_INTAKE_LIGHT",
        current_stage_label="IDEA_ANALYSIS")
    if _gate_fail is not None:
        return _gate_fail

    # v6.3 (2026-07-30): IDEA_ANALYSIS reads ONLY the compact idea-intake-light.
    # story_design_mode comes from the pre-computed story_mode field (v2.0 schema).
    idea_intake_light = read_json(pdir / "idea-intake-light.json", None) or {}
    story_design_mode = str(idea_intake_light.get("story_mode") or "AUTO").upper()
    if story_design_mode not in {"AUTO", "STRICT", "SOFT"}:
        story_design_mode = "AUTO"
    # `answers` retained as an EMPTY dict for legacy code paths that call .get(...)
    # below (fallback stubs, downstream references) — none of them actually need
    # user-supplied text now.
    answers = {}
    skill = claude_cli.skill_paths_for_agent("BriefAnalysisAgent")

    # ===== Fresh analysis (v4.0 single-Mode narrative-only) =====
    # v4.0 移除 v3.2 的 Mode 2 + Code retrieval (rank_sections_for_chapter):
    # IDEA 不再绑具体 PPT candidate, 只产 rhythm_pattern_id (抽象叙事节奏)
    # 具体 carrier 选择延后到 OUTLINE 阶段

    # Pre-load v6.1 resources. IDEA only needs pattern IDs and compact summaries;
    # carrier/source details are loaded later by OUTLINE after chapter intent is
    # fixed. Keeping carriers in the IDEA prompt makes the single Claude call
    # slow and blurs the stage boundary.
    deck_patterns = _compact_deck_patterns_for_idea(
        oc.load_deck_level_patterns(with_carriers=False)
    )
    hard_rules_summary = oc.load_logic_story_hard_rules_summary()
    hard_rules_for_generation = _compact_logic_story_rules_for_idea(
        hard_rules_summary, max_rules=70)
    # v6.2: former logic/meta is merged into unified deck_level as
    # pattern_kind=deck_task. Recommend a few task patterns, but keep all
    # deck-level patterns in one namespace for Claude.
    recommended_deck_task_patterns = oc.recommend_deck_task_patterns_for_intake(
        idea_intake_light or {}, top_n=3)
    # Pre-compute top-3 rhythm patterns per role (driver-side, Claude select 1 per chapter)
    rhythm_patterns_per_role: dict[str, list[dict]] = {}
    # Common chapter roles seen in chapter_plan
    for role in ("cover", "agenda", "section_divider", "motivation", "background",
                 "problem", "framework", "method", "comparison", "result",
                 "experiment", "engineering", "discussion", "outlook",
                 "closing", "references", "content"):
        top3 = oc.recommend_section_rhythm_patterns_for_chapter_role(role, top_n=2)
        if top3:
            rhythm_patterns_per_role[role] = [
                {
                    "pattern_id": r.get("pattern_id"),
                    "source_count": r.get("source_count"),
                    "applicable_summary": (r.get("applicable_summary") or "")[:180],
                    "abstract_node_sequence_brief": (
                        ", ".join(
                            str(n.get("archetype") or n.get("name") or "?")[:30]
                            for n in (r.get("abstract_node_sequence") or [])[:5]
                        ) or "?"
                    ),
                    # v30 fix: 给 Claude 明示每个 rhythm 的典型页数, 避免选了"单页收尾"
                    # 却填 expected_pages_indicative=3 这类容量-节奏不一致 issue
                    "typical_page_count": len(r.get("abstract_node_sequence") or []) or None,
                }
                for r in top3
            ]

    # --- Single Mode call: design narrative + select rhythm_pattern_id per chapter ---
    # v36: IDEA is intentionally light. Do not inline full slide inventory here.
    # It only needs logic patterns + logic_story rules + section-level material
    # capacity hints. Slide-level grounding/source binding belongs to OUTLINE.

    # v35: IDEA builds a section-level library view only. It may use deck and
    # section capacity to choose chapter topics and material_section_hints, but
    # it must not choose individual slides or emit page-level skeletons.
    try:
        _intake = idea_intake_light or {}
        _kw_pool: list[str] = []
        for _f in ("subject", "topic_tags", "keywords", "sub_topics"):
            _v = _intake.get(_f)
            if isinstance(_v, str) and _v:
                _kw_pool.append(_v)
            elif isinstance(_v, list):
                _kw_pool.extend([str(x) for x in _v if x])
        # 去重 + 保序
        _seen: set = set(); _kws: list[str] = []
        for _k in _kw_pool:
            _k = _k.strip()
            if _k and _k not in _seen:
                _seen.add(_k); _kws.append(_k)
        _kws = _kws[:20]  # cap
        print(f"[IDEA_ANALYSIS] library_understanding: cascade with {len(_kws)} keywords: "
              f"{_kws[:6]}...", flush=True)
        _cascade = oc.cascade_search_for_gap(
            keywords=_kws or ["大模型", "推理", "优化"],
            role_hint=None,
            max_decks=6, max_sections=18, max_slides=120,
        )
        _rel_slides = _cascade.get("slides") or []
        _rel_sections = _cascade.get("sections") or []
        _rel_decks = _cascade.get("decks") or []

        # v35 stage-boundary fix:
        # IDEA may inspect only deck/section-level material. Slide-level source
        # binding belongs to OUTLINE Stage 1b. We still count relevant slides per
        # section so IDEA can estimate capacity, but do not expose slide ids,
        # titles, claims, or page-level briefs in the generation payload.
        # top_decks 摘要 (含 n_relevant_slides 让 Claude 判断哪本 deck 素材最够)
        top_decks_view = [
            {"deck_id": _d.get("deck_id"),
             "deck_title": _d.get("title") or _d.get("deck_title"),
             "报告类型": _d.get("报告类型"),
             "主题标签": _d.get("主题标签") or [],
             "score": _d.get("_score") or _d.get("score"),
             "n_relevant_slides": sum(1 for _s in _rel_slides
                                       if _s.get("deck_id") == _d.get("deck_id"))}
            for _d in _rel_decks[:6]
        ]
        # sections_by_deck: {deck_id: [{section_id, section_title, section_role,
        #                                n_slides_in_pool, score}]}
        sections_by_deck: dict[str, list] = {}
        for _sec in _rel_sections:
            _did = _sec.get("deck_id")
            if not _did:
                continue
            _sid = _sec.get("section_id")
            _n_slides_pool = sum(1 for _s in _rel_slides if _s.get("section_id") == _sid)
            sections_by_deck.setdefault(_did, []).append({
                "section_id": _sid,
                "section_title": _sec.get("section_title") or _sec.get("标题"),
                "section_role": _sec.get("section_role") or _sec.get("章节角色"),
                "n_slides_in_pool": _n_slides_pool,
                "score": _sec.get("_score") or _sec.get("score"),
            })

        for _did, _items in list(sections_by_deck.items()):
            _items.sort(key=lambda x: float(x.get("score") or 0.0), reverse=True)
            sections_by_deck[_did] = _items[:3]

        library_understanding = {
            "total_relevant_slides_estimate": len(_rel_slides),
            "relevant_sections_count": sum(len(v) for v in sections_by_deck.values()),
            "hierarchy": {
                "top_decks": top_decks_view,
                "sections_by_deck": sections_by_deck,
                "hint": "IDEA 只可选择 deck/section 级材料提示, 不可挑 slide. "
                         "OUTLINE Stage 1a 使用这些 section hints 生成 stubs; "
                         "OUTLINE Stage 1b 再加载 slide briefs 绑定真实来源.",
            },
            "relevant_section_ids": [
                _s.get("section_id")
                for _items in sections_by_deck.values()
                for _s in _items
                if isinstance(_s, dict) and _s.get("section_id")
            ],
            "cascade_keywords_used": _kws,
        }
        print(f"[IDEA_ANALYSIS] library_understanding built: "
              f"{library_understanding['total_relevant_slides_estimate']} slide-capacity / "
              f"{len(top_decks_view)} decks / "
              f"{sum(len(v) for v in sections_by_deck.values())} sections",
              flush=True)
    except Exception as _e:
        print(f"[IDEA_ANALYSIS] library_understanding build failed: {_e}", flush=True)
        library_understanding = {
            "total_relevant_slides_estimate": 0,
            "hierarchy": {"top_decks": [], "sections_by_deck": {}},
            "relevant_section_ids": [],
            "cascade_keywords_used": [], "error": str(_e),
        }

    v4_payload = {
        "intake_light": idea_intake_light or {},
        "resource_library_contract": _idea_resource_library_contract(oc),
        "deck_level_patterns": deck_patterns,
        "recommended_deck_task_patterns": recommended_deck_task_patterns,
        "logic_story_hard_rules_summary": hard_rules_for_generation,
        "rhythm_patterns_per_role": rhythm_patterns_per_role,
        "required_structural_page_contract": _default_structural_page_contract(),
        "story_design_mode_hint": story_design_mode,
        # v35: section-level library understanding only. No slide-level material
        # enters IDEA_ANALYSIS.
        "library_understanding": library_understanding,
    }
    v4_prompt = (
        "Run IDEA_ANALYSIS v6.1 (narrative + chapter plan only). "
        "Output complete idea-analysis.json v6.1 schema:\n"
        "  - selected_narrative_arc (选主叙事骨架 + 借鉴)\n"
        "  - selected_meta_pattern (compat field: choose one deck_level pattern_kind=deck_task; cannot be null)\n"
        "  - chapter_plan (per chapter 含: section_role / purpose / "
        "section_rhythm_pattern_id / expected_pages_indicative / "
        "material_section_hints / requires_section_divider / structural_prefix_role / "
        "parallel_group / chapter_bridge_hint)\n"
        "  - structural_page_contract (cover@1, agenda@2, section_divider before each chapter)\n"
        "  - parallel_group_contracts (for every repeated parallel_group_id: page budget, "
        "canonical chapter skeleton, work block template, framework anchor policy)\n"
        "  - narrative_constraints\n"
        "  - reuse_strategy\n"
        "  - provenance\n\n"
        "**HARD STAGE BOUNDARY**: IDEA_ANALYSIS owns only the high-level story, "
        "chapter classification, chapter intent, section rhythm selection, rough "
        "page budget, parallel chapter relationships, and material SECTION hints. "
        "Do not output slide_stubs, chapter_page_count, page_specific archetypes, "
        "target_title, target_claim, key_points, source_resource_ids, or source slide ids. "
        "OUTLINE Stage 1a owns slide_stubs; OUTLINE Stage 1b owns source binding.\n\n"
        "**STRUCTURAL PAGE CONTRACT**: copy `required_structural_page_contract` into "
        "`structural_page_contract` and treat it as a hard promise: slide 1 is cover, "
        "slide 2 is agenda, and every chapter_plan business chapter has "
        "`requires_section_divider=true` with `structural_prefix_role=\"section_divider\"`. "
        "These pages are not post-processing decoration; OUTLINE must materialize them "
        "as source-backed byte-clone pages. IDEA must not choose slide IDs.\n\n"
        "**CURRENT RESOURCE LIBRARY CONTRACT**: resource_library_contract is authoritative "
        "for the optimized data/resources_library split: logic=unified deck_level/section_level narrative "
        "patterns, material=actual reusable source slides/sections/decks, and rule=logic_story "
        "chapter/story constraints. Do not use legacy template_library narrative "
        "patterns as the primary source of truth.\n\n"
        "**DECK-LEVEL / RHYTHM ID BOUNDARY**: deck_level_patterns is the unified "
        "whole-deck layer. Choose selected_meta_pattern from pattern_kind=deck_task "
        "(compat field name), choose selected_narrative_arc.primary_pattern_id and "
        "borrowed_patterns from pattern_kind=deck_arc, and choose chapter rhythm IDs "
        "only from rhythm_patterns_per_role. Do not mix section-level rhythm IDs into "
        "deck-level fields.\n\n"
        "**LIBRARY-FIRST, SECTION-LEVEL ONLY**: use `library_understanding.hierarchy` "
        "(top_decks → sections_by_deck) to choose chapter topics and fill each "
        "`chapter_plan[i].material_section_hints[]` with section-level candidates "
        "{deck_id, section_id, section_role, reason, expected_slide_capacity}. "
        "Do not choose individual slides. Use section capacity only to set rough "
        "`expected_pages_indicative` / `expected_pages_range`; precise page count "
        "is decided by OUTLINE Stage 1a.\n\n"
        "**OPTIONAL CHAPTER DISCIPLINE**: any optional chapter such as discussion / "
        "outlook / background must stay single-axis. Do not mix industry benchmark, "
        "future paradigm, GPU, edge, and network topics into one chapter. If the "
        "deck needs multiple axes, split them across chapters or keep one as the "
        "main axis and convert the rest into setup or callback wording.\n\n"
        "**CLOSING DISCIPLINE**: the last chapter must recap the cover title / core "
        "thesis in plain language, must not introduce new methods or new evidence, "
        "and may only thank / sign off / invite collaboration after the callback.\n\n"
        "**HOOK DISCIPLINE**: before you finish, ensure `narrative_constraints.cross_section_hooks` "
        "covers most chapter boundaries. For an N-chapter deck, aim for at least N-2 hooks, "
        "including explicit handoffs for method chains and outlook→closing.\n\n"
        "**PARALLEL GROUP DISCIPLINE**: if multiple chapters share a `parallel_group_id`, "
        "you MUST output `parallel_group_contracts[]`. Their page budgets must be close "
        "(delta <= 2 pages or <=20%), their `canonical_chapter_skeleton` must be shared, "
        "and their representative work blocks must use one `canonical_work_block_template` "
        "(usually paper_intro → challenge → method → result). Framework anchor pages across "
        "the group should reuse the same source template later; IDEA only declares the policy.\n\n"
        "Strict JSON only.\n\n"
        "INPUT:\n" + json.dumps(v4_payload, ensure_ascii=False)
    )
    print(
        "[IDEA_ANALYSIS] prompt payload sizes: "
        f"prompt~{len(v4_prompt) // 1024}KB, "
        f"deck_patterns={len(deck_patterns)}, "
        f"rules={len(hard_rules_for_generation)}, "
        f"rhythm_roles={len(rhythm_patterns_per_role)}, "
        f"library_sections={library_understanding.get('relevant_sections_count')}",
        flush=True,
    )
    v4_out = claude_cli.call_claude_json(v4_prompt, skill=skill, timeout=900)
    if not (v4_out.get("ok") and isinstance(v4_out.get("data"), dict)):
        # v31: 不再静默 fallback 到 stub. Stub 会让 chapter_plan 空, 下游立即挂,
        # 且 idea-analysis.json 变假数据 (source=stub, no library info). 直接 fail
        # 让用户知道 IDEA 失败, 可以查 CLI 错误 / 减 payload / 重试.
        return {"ok": False, "stage": "IDEA_ANALYSIS",
                "error": (f"Claude CLI failed for IDEA_ANALYSIS: "
                          f"{(v4_out.get('error') or 'unknown')[:400]}"),
                "retry_hint": ("检查 payload 大小 (可能超 CLI stdin 上限). "
                                "尝试减少 library_understanding.hierarchy 中 top_decks/"
                                "sections_by_deck 的候选数量."),
                "raw_excerpt": (v4_out.get("raw_excerpt") or "")[:400]}
    data = v4_out["data"]
    data, _removed_idea_fields = _strip_idea_page_level_fields(data)
    data["source"] = "claude_v6_narrative_chapter_plan_only"
    data["schema_version"] = "6.1"   # v6.1: IDEA no longer emits slide stubs
    # v6: ensure selected_meta_pattern key exists (Claude fills it; stub if absent)
    data.setdefault("selected_meta_pattern", None)
    chapters = data.get("chapter_plan") or []
    with_rhythm = sum(1 for c in chapters if c.get("section_rhythm_pattern_id"))
    print(f"[IDEA_ANALYSIS] v6.1 OK, chapters={len(chapters)}, "
          f"with_rhythm_pattern={with_rhythm}", flush=True)

    # Keep the section-level material pool for OUTLINE. Slide-level pools are
    # intentionally not stored here; Stage 1b loads material slide briefs after
    # Stage 1a has produced stubs.
    _prov = data.setdefault("provenance", {})
    _prov["library_pool_section_ids"] = library_understanding.get("relevant_section_ids") or []
    _prov["library_pool_source"] = "cascade_from_intake_keywords"
    _prov["library_pool_size"] = library_understanding.get("relevant_sections_count") or 0
    _prov["library_understanding"] = library_understanding
    _prov["resource_library_contract"] = _idea_resource_library_contract(oc)
    if _removed_idea_fields:
        _prov["removed_page_level_fields"] = _removed_idea_fields
        print(f"[IDEA_ANALYSIS] stripped {len(_removed_idea_fields)} page-level fields "
              "from Claude output before review", flush=True)
    data, _normalized_idea_refs = _normalize_idea_v61_required_refs(
        data,
        rhythm_patterns_per_role=rhythm_patterns_per_role,
        library_understanding=library_understanding,
    )
    data, _parallel_contract_changes = _ensure_parallel_group_contracts(data)
    library_understanding, _backfilled_pool_count = _backfill_idea_library_pool_from_material_hints(
        data,
        library_understanding,
    )
    _prov["library_pool_section_ids"] = library_understanding.get("relevant_section_ids") or []
    _prov["library_pool_size"] = library_understanding.get("relevant_sections_count") or 0
    _prov["library_understanding"] = library_understanding
    if _backfilled_pool_count:
        _prov.setdefault("driver_normalization", [])
        _prov["driver_normalization"].append({
            "stage": "IDEA_ANALYSIS",
            "reason": "backfilled library pool from Claude-selected material_section_hints",
            "section_count": _backfilled_pool_count,
        })
        print(f"[IDEA_ANALYSIS] backfilled {_backfilled_pool_count} section hints "
              "into library_understanding pool", flush=True)
    if _normalized_idea_refs:
        print(f"[IDEA_ANALYSIS] driver-filled {len(_normalized_idea_refs)} "
              "missing v6.1 reference fields before review", flush=True)
    if _parallel_contract_changes:
        print(f"[IDEA_ANALYSIS] driver-filled {len(_parallel_contract_changes)} "
              "parallel group contracts before review", flush=True)

    # Post-processing (v4.0 only — legacy schema branches removed with revision path)
    data["generated_at"] = now()
    if not data.get("story_design_mode"):
        data["story_design_mode"] = story_design_mode

    # v36 temporary policy: IDEA_ANALYSIS is generated by Claude and then handed
    # to human review directly. Codex review/fix loop is intentionally disabled
    # here so IDEA quality is driven by the Claude skill + logic/rule libraries,
    # not by repeated Codex-discovered repairs.
    write_json(pdir / "idea-analysis.json", data)
    write_json(pdir / "idea-analysis.draft.json", data)
    write_json(pdir / "idea-review.json", {
        "schema_version": "1.0",
        "stage": "IDEA_ANALYSIS",
        "review_skipped": True,
        "reason": "temporary_v36_claude_only_idea_generation",
        "rounds": [],
        "final_ok": None,
        "generated_at": now(),
    })
    _write_stage_status(pdir, "idea-user-status.json",
                         story_design_mode=data.get("story_design_mode") or story_design_mode,
                         fix_round=data.get("fix_round", 0),
                         codex_review_rounds=0,
                         codex_final_ok=None,
                         codex_review_skipped=True,
                         awaiting_human_review=False,
                         human_feedback_round=0)

    md_prompt = (
        "Render idea-analysis.md per the idea_human_summary skill. "
        "Output the raw markdown text only — do NOT wrap in JSON, do NOT "
        "add code fences around the whole document.\n\n"
        "INPUT idea_analysis:\n" + json.dumps(data, ensure_ascii=False)
    )
    if not hasattr(claude_cli, "call_claude_text"):
        raise RuntimeError(
            "IDEA_ANALYSIS: claude_cli.call_claude_text 缺失, 无法渲染 idea-analysis.md")
    md_out = claude_cli.call_claude_text(
        md_prompt,
        skill=["skills/idea/idea_human_summary.md"],
        timeout=600,
    )
    if not (md_out and md_out.get("ok") and md_out.get("text")):
        raise RuntimeError(
            f"IDEA_ANALYSIS: idea-analysis.md 渲染失败 — "
            f"{(md_out.get('error') if isinstance(md_out, dict) else 'no output')}")
    (pdir / "idea-analysis.md").write_text(md_out["text"], encoding="utf-8")
    print(f"[IDEA_ANALYSIS] wrote idea-analysis.md ({len(md_out['text'])} chars)", flush=True)

    return {
        "ok": True,
        "stage": "IDEA_ANALYSIS",
        "idea_analysis": str(pdir / "idea-analysis.json"),
        "source": data.get("source"),
        "review_skipped": True,
        "review_rounds": 0,
        "story_design_mode": data.get("story_design_mode") or story_design_mode,
    }


def _select_hierarchical_library_decks(brief_light: dict | None, answers: dict) -> dict:
    """Hierarchical match: top-15 deck overview + top-5 deck section/slide deep dive.

    Step 1: Score all 28 library decks by keyword overlap with the brief
            (using light analysis preferred, raw answers fallback).
    Step 2: Pick top-15 — return their compact deck-level overview.
    Step 3: From top-15, pick top-5 (highest scores) and load their section.json
            (chapter narrative / page relationships) + slide.json brief
            (role / claim / title).

    Returns:
        {
            "top15_overview": [...deck overview, 15 items...],
            "top5_deep_dive": {
                "<deck_id>": {
                    "overview": {...},
                    "sections": [{section_index, role, title, narrative, page_count}],
                    "slides_brief": [{slide_index, role, claim}],
                }
            }
        }
    """
    decks_index_path = ROOT / "data" / "resources_library" / "material" / "decks-index.json"
    if not decks_index_path.exists():
        return {"top15_overview": [], "top5_deep_dive": {}}
    idx_doc = read_json(decks_index_path, {}) or {}
    decks = idx_doc.get("decks") or []
    if not decks:
        return {"top15_overview": [], "top5_deep_dive": {}}

    # Build query bag — prefer light analysis (better signals)
    import re as _re_h
    query_bits: list[str] = []
    if brief_light:
        st = brief_light.get("topic") or {}
        ap = brief_light.get("audience") or {}
        sc = brief_light.get("scenario") or {}
        query_bits.append(str(st.get("subject") or ""))
        for s in (st.get("sub_topics") or []):
            query_bits.append(str(s))
        query_bits.append(str(ap.get("primary") or ""))
        for t in (ap.get("background_tags") or []):
            query_bits.append(str(t))
        query_bits.append(str(sc.get("category") or ""))
        for k in (brief_light.get("keywords") or []):
            query_bits.append(str(k))
    else:
        for k in ("topic", "audience", "scenario", "reuse_policy", "style"):
            v = (answers.get(k) or "")
            if isinstance(v, str):
                query_bits.append(v)

    query_text = " ".join(query_bits)
    query_tokens: set[str] = set()
    for tok in _re_h.findall(r"[A-Za-z一-鿿][A-Za-z0-9一-鿿/_+\-]{1,}", query_text):
        if len(tok) >= 2 and tok not in {"研究", "成果", "分享", "技术", "本次", "汇报"}:
            query_tokens.add(tok)

    def _deck_score(d: dict) -> float:
        text_pool = " ".join([
            str(d.get("标题") or ""),
            str(d.get("适用场景") or ""),
            " ".join(str(t) for t in (d.get("主题标签") or [])),
            " ".join(str(t) for t in (d.get("论述弧线") or [])),
            str(d.get("报告类型") or ""),
            str(d.get("目标受众") or ""),
        ])
        keyword_hits = sum(1 for t in query_tokens if t and t in text_pool)
        # Bonus for matching deliverable_type when light analysis provided one
        bonus = 0.0
        if brief_light:
            dt = (brief_light.get("topic") or {}).get("deliverable_type")
            rt = d.get("报告类型") or ""
            type_map = {
                "research_share": ["research_report"],
                "tutorial": ["tutorial"],
                "proposal": ["proposal"],
                "project_review": ["proposal", "research_report"],
            }
            if dt in type_map and rt in type_map[dt]:
                bonus = 2.0
        return float(keyword_hits) + bonus

    scored = sorted(((_deck_score(d), d) for d in decks), key=lambda x: -x[0])
    top15 = scored[:15]
    top5 = scored[:5]

    def _overview(d: dict, score: float) -> dict:
        return {
            "deck_id": d.get("deck标识"),
            "标题": d.get("标题"),
            "报告类型": d.get("报告类型"),
            "主题标签": d.get("主题标签"),
            "目标受众": d.get("目标受众"),
            "适用场景": d.get("适用场景"),
            "论述弧线": d.get("论述弧线"),
            "总页数": d.get("总页数"),
            "章节数": d.get("章节数"),
            "_similarity_score": score,
        }

    top15_overview = [_overview(d, score) for score, d in top15]

    # Deep dive for top-5
    decks_root = ROOT / "data" / "resources_library" / "material" / "decks"
    top5_deep_dive: dict[str, dict] = {}
    for score, d in top5:
        deck_id = d.get("deck标识")
        deck_dir_name = d.get("目录名")
        if not deck_dir_name:
            continue
        deck_dir = decks_root / deck_dir_name
        if not deck_dir.exists():
            continue
        sections_brief: list[dict] = []
        slides_brief: list[dict] = []
        # iterate section_XX_<title>/ subdirs in deck.json's 章节列表 order
        for sec_name in (d.get("章节列表") or []):
            sec_dir = deck_dir / sec_name
            sec_json = sec_dir / "section.json"
            if not sec_json.exists():
                continue
            try:
                sd = read_json(sec_json, {}) or {}
                sections_brief.append({
                    "章节序号": sd.get("章节序号"),
                    "章节角色": sd.get("章节角色"),
                    "标题": sd.get("标题"),
                    "页数": sd.get("页数"),
                    "章节叙事": (sd.get("章节叙事") or "")[:120],
                    "页间关系": (sd.get("页间关系") or [])[:2],
                })
            except Exception:
                pass
            # slide briefs in this section
            for slide_path in sorted(sec_dir.glob("slide_*.json")):
                try:
                    sld = read_json(slide_path, {}) or {}
                    slides_brief.append({
                        "页序号": sld.get("页序号"),
                        "页面角色": sld.get("页面角色"),
                        "标题": (sld.get("标题") or "")[:40],
                        "核心论断": (sld.get("核心论断") or "")[:60],
                    })
                except Exception:
                    pass
        if deck_id:
            top5_deep_dive[deck_id] = {
                "overview": _overview(d, score),
                "sections": sections_brief,
                "slides_brief": slides_brief,
            }

    return {
        "top15_overview": top15_overview,
        "top5_deep_dive": top5_deep_dive,
    }


def _select_top10_library_decks(answers: dict) -> list[dict]:
    """Pre-filter top-10 most topic-similar library decks for IDEA_ANALYSIS.

    Reads data/resources_library/material/decks-index.json (28 decks) and ranks by
    keyword overlap between user's topic/audience/scenario and each deck's
    主题标签 / 适用场景 / 论述弧线 / 报告类型. Returns deck-level overview
    only (not section/slide bodies — those are too large for prompt).
    """
    decks_index_path = ROOT / "data" / "resources_library" / "material" / "decks-index.json"
    if not decks_index_path.exists():
        return []
    idx = read_json(decks_index_path, {}) or {}
    decks = idx.get("decks") or []
    if not decks:
        return []

    # Build query bag from user intake
    import re as _re_top
    query_bits = []
    for k in ("topic", "audience", "scenario", "reuse_policy"):
        v = (answers.get(k) or "")
        if isinstance(v, str):
            query_bits.append(v)
    query_text = " ".join(query_bits)
    query_tokens = set()
    for tok in _re_top.findall(r"[A-Za-z一-鿿][A-Za-z0-9一-鿿/_+\-]{1,}", query_text):
        if len(tok) >= 2 and tok not in {"研究", "成果", "分享", "技术", "本次"}:
            query_tokens.add(tok)

    def _deck_score(d: dict) -> int:
        text_pool = " ".join([
            str(d.get("标题") or ""),
            str(d.get("适用场景") or ""),
            " ".join(str(t) for t in (d.get("主题标签") or [])),
            " ".join(str(t) for t in (d.get("论述弧线") or [])),
            str(d.get("报告类型") or ""),
            str(d.get("目标受众") or ""),
        ])
        return sum(1 for t in query_tokens if t and t in text_pool)

    scored = [(_deck_score(d), d) for d in decks]
    scored.sort(key=lambda x: -x[0])
    top10 = scored[:10]
    # Return compact view (deck-level only)
    return [
        {
            "deck_id": d.get("deck标识"),
            "标题": d.get("标题"),
            "报告类型": d.get("报告类型"),
            "主题标签": d.get("主题标签"),
            "目标受众": d.get("目标受众"),
            "适用场景": d.get("适用场景"),
            "论述弧线": d.get("论述弧线"),
            "总页数": d.get("总页数"),
            "章节数": d.get("章节数"),
            "_similarity_score": score,
        }
        for score, d in top10
    ]


def _brief_skeleton_fallback(context: dict, reuse_rate_hint: float, err: str | None) -> dict:
    """Deterministic skeleton used when Claude entirely fails.

    Tolerates both old (flat slide_count_hint) and new (user_brief_intake.*)
    context shapes.
    """
    intake = context.get("user_brief_intake") or {}
    slide_count = intake.get("slide_count") or context.get("slide_count_hint") or 10
    language = intake.get("language") or context.get("language_hint") or "zh"
    duration_minutes = intake.get("duration_minutes") or context.get("duration_minutes_hint")
    answers = intake or {}
    return {
        "schema_version": "2.1",
        "generated_at": now(),
        "source": "stub",
        "fallback_reason": err,
        "topic": answers.get("topic") or "",
        "language": language,
        "slide_count": slide_count,
        "duration_minutes": duration_minutes,
        "deck_type": "general",
        "audience": {"level": "practitioner", "background": "", "what_they_care_about": [], "knowledge_gaps_to_fill": []},
        "presentation_goal": {"primary": "", "secondary": [], "audience_should_walk_away_with": ""},
        "core_message": "",
        "message_architecture": {"thesis": "", "throughline": "", "supporting_pillars": [], "central_tension": ""},
        "narrative_blueprint": {"arc": [], "depth": "balanced", "evidence_strictness": "medium", "anchor_claims": []},
        "chapter_page_archetype_plan": [],
        "chapter_delivery_plan": [],
        "claim_status_plan": [],
        "constraint_resolution": [],
        "technical_depth_policy": {"assumed_known": [], "must_explain_once": [], "deep_dive_allowed_for": [], "keep_conceptual_for": [], "avoid_or_sanitize": []},
        "reuse_strategy": {
            "target_reuse_rate": reuse_rate_hint,
            "draft_intent": "high page-level source-slide coverage for draft review",
            "preferred_granularity": "whole_slide_when_later_matched",
            "designated_resources": context.get("designated_resources") or [],
            "forbidden_resources": context.get("forbidden_resources") or [],
            "direct_paste_allowed": True,
            "rewrite_required_in_final": True,
            "no_material_decision_at_brief_stage": True,
        },
        "must_have_pages": [],
        "expected_sections": [],
        "page_budget_breakdown": {},
        "citation_policy": answers.get("citation_policy") or "",
        "style_signature": answers.get("style") or "",
        "slide_writing_rules": {
            "title_rule": "short functional title",
            "claim_rule": "each content page needs one provable claim",
            "body_rule": "3-4 key points per page, prefer diagrams",
            "technical_page_pattern": "problem -> mechanism -> result/boundary",
            "result_page_pattern": "conclusion first -> metric -> baseline -> condition",
            "citation_rule": "short citations on key facts; full references at end",
        },
        "referenced_templates": {},
        "story_design_mode": "AUTO",
    }


def _resource_index_brief(project_id: str) -> dict:
    """Compact view of project resources for the resource-understanding prompt."""
    pdir = project_dir(project_id)
    index = read_json(pdir / "project-source-index.json", [])
    digest = read_json(pdir / "project-source-digest.json", {})
    catalog = read_json(pdir / "project-asset-catalog.json", {})
    resources = []
    for item in (index or []):
        if not isinstance(item, dict):
            continue
        resources.append({
            "resource_id": item.get("resource_id") or item.get("path"),
            "path": item.get("path"),
            "type": item.get("type"),
            "size": item.get("size"),
            "reusable_level": item.get("reusable_level"),
        })
    assets = []
    for asset in (catalog.get("assets") if isinstance(catalog, dict) else []) or []:
        if not isinstance(asset, dict):
            continue
        assets.append({
            "resource_id": asset.get("asset_id") or asset.get("path"),
            "path": asset.get("path"),
            "asset_type": asset.get("asset_type") or asset.get("type"),
            "caption": asset.get("caption"),
            "content_summary": (asset.get("content_summary") or "")[:240],
            "source_priority": asset.get("source_priority"),
        })
    digest_brief = []
    items = digest.get("items") if isinstance(digest, dict) else None
    for item in (items or [])[:60]:
        if not isinstance(item, dict):
            continue
        digest_brief.append({
            "resource_id": item.get("resource_id") or item.get("path"),
            "path": item.get("path"),
            "summary": (item.get("summary") or item.get("excerpt") or "")[:400],
        })
    return {
        "resources": resources[:120],
        "assets": assets[:120],
        "digest": digest_brief,
    }


def _run_source_understand(project_id: str) -> dict:
    """SOURCE_UNDERSTAND — single stage that owns ALL source-side analysis.

    Pipeline (Phase P16/P17):
      1. analyze_project_sources  → per-format Claude on pdf/doc/excel/image,
         writes data/<type>/<stem>.json + source-relevance.json
      2. build_project_library     → per-pptx 4-skill briefing, writes
         data/ppt/<deck-stem>/{deck.json, sections/, slides/}
      3. scan_resources (re-run)   → reads pre-computed analyses from data/
         and aggregates project-{deck,section,slide,doc,figure,sheet}-units.json
         with full semantic fields (translation from Chinese → English happens
         inside services._translate_*).
      4. Claude master synthesizer → writes data/source-understanding.json
         (overview + topic landscape + per-chapter coverage hints + must_use /
         forbidden buckets + topic_to_resources)

    Runs AFTER PROJECT_SOURCE_SCAN (which is pure deterministic file
    inventory) and BEFORE IDEA_ANALYSIS. The single output downstream
    stages care about is `data/source-understanding.json`.

    **Empty-sources skip (Phase R, 2026-06-27)**: when the project's `sources/`
    dir is missing or contains zero files, this stage short-circuits — writes
    a stub `data/source-understanding.json` with `file_count=0` and returns
    ok=True with status `skipped_no_sources`. Downstream stages branch on
    `file_count==0` and skip source-grounding logic naturally.
    """
    from . import claude_cli, services, project_analyzer, project_library

    pdir = project_dir(project_id)
    data_dir = pdir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    # --- Phase R: empty-sources short-circuit ---
    sources_dir = pdir / "sources"
    if not sources_dir.exists():
        physical_count = 0
    else:
        physical_count = sum(1 for p in sources_dir.iterdir() if p.is_file())
    if physical_count == 0:
        print(f"[source-understand] sources/ empty or missing — skipping "
              f"(no Claude calls, no project unit aggregation)", flush=True)
        stub_understanding = {
            "schema_version": "2.0",
            "generated_at": now(),
            "source": "skipped_no_sources",
            "file_count": 0,
            "file_inventory": [],
            "dominant_topics": [],
            "key_terms": [],
            "must_use_materials": [],
            "forbidden_or_low_confidence_materials": [],
            "topic_to_resources": {},
            "per_chapter_hint": [],
            "coverage_hints": {"well_covered_topics": [], "gap_topics": []},
            "notes_for_downstream": "Project has no source materials uploaded; "
                                    "downstream stages should skip source-grounding "
                                    "logic and rely on user_intake + brief alone.",
        }
        write_json(data_dir / "source-understanding.json", stub_understanding)
        return {
            "ok": True,
            "stage": "SOURCE_UNDERSTAND",
            "status": "skipped_no_sources",
            "file_count": 0,
            "source": "skipped_no_sources",
            "file_count_metric": 0,
            "dominant_topics_count": 0,
            "key_terms_count": 0,
            "must_use_count": 0,
        }

    # --- Step 1: per-format Claude analysis (pdf / doc / excel / image) ---
    analysis_report = {}
    try:
        analysis_report = project_analyzer.analyze_project_sources(project_id) or {}
    except Exception as exc:  # noqa: BLE001
        print(f"[source-understand] analyze_project_sources failed: {exc}", flush=True)

    # --- Step 2: per-pptx 4-skill brief pipeline ---
    pptx_summary: dict = {}
    try:
        inv = project_library.scan_sources_inventory(project_id) or {}
        has_pptx = any((f.get("type") == "pptx") for f in (inv.get("files") or []))
        if has_pptx:
            pptx_summary = project_library.build_project_library(project_id) or {}
    except Exception as exc:  # noqa: BLE001
        print(f"[source-understand] build_project_library failed: {exc}", flush=True)

    # --- Step 3: re-aggregate project-*-units.json (reads data/<type>/) ---
    try:
        services.scan_resources(project_id)
    except Exception as exc:  # noqa: BLE001
        print(f"[source-understand] re-scan failed: {exc}", flush=True)

    # --- Step 4: build context + call Claude master synthesizer ---
    # Prefer idea-intake-light.json as brief context; fall back to raw answers.
    light = read_json(pdir / "idea-intake-light.json", None)
    if light:
        brief_context = {
            "source": "brief-intake-light",
            "structured_topic": light.get("structured_topic"),
            "audience_profile": light.get("audience_profile"),
            "scenario_type": light.get("scenario_type"),
            "extracted_keywords": light.get("extracted_keywords") or [],
            "design_hints": light.get("design_hints") or [],
            "story_style_signal": light.get("story_style_signal"),
            "reuse_preference": light.get("reuse_preference"),
        }
    else:
        # Fallback to raw answers when light analysis is missing.
        answers_state = read_json(pdir / "question-state.json", {}) or {}
        answers = answers_state.get("answers") if isinstance(answers_state, dict) else {}
        answers = answers if isinstance(answers, dict) else {}
        brief_context = {
            "source": "raw-question-state",
            "topic": answers.get("topic"),
            "audience": answers.get("audience"),
            "scenario": answers.get("scenario"),
            "language": answers.get("language") or "zh",
            "slide_count": answers.get("slide_count"),
            "story_style": (answers.get("story_style") or "")[:600],
            "reuse_policy": (answers.get("reuse_policy") or "")[:300],
        }

    # Read SCAN outputs (deck/doc/figure/sheet units + source-digest).
    project_resources = {
        "deck_units": read_json(pdir / "project-deck-units.json", {}) or {},
        "doc_units": read_json(pdir / "project-doc-units.json", {}) or {},
        "figure_units": read_json(pdir / "project-figure-units.json", {}) or {},
        "sheet_units": read_json(pdir / "project-sheet-units.json", {}) or {},
        "section_units": read_json(pdir / "project-section-units.json", {}) or {},
        "slide_units": read_json(pdir / "project-slide-units.json", {}) or {},
        "source_digest": read_json(pdir / "project-source-digest.json", {}) or {},
        "resource_index": read_json(pdir / "project-source-index.json", {}) or {},
    }

    # Quick deterministic empty-source path: skip Claude call if nothing uploaded.
    # Schema note: doc-units uses "doc_units" key, others use plural noun ("decks"/"figures"/"sheets").
    deck_list = project_resources["deck_units"].get("decks") or []
    doc_list = project_resources["doc_units"].get("doc_units") or []
    figure_list = project_resources["figure_units"].get("figures") or []
    sheet_list = project_resources["sheet_units"].get("sheets") or []
    total_files = len(deck_list) + len(doc_list) + len(figure_list) + len(sheet_list)
    out_path = data_dir / "source-understanding.json"
    if total_files == 0:
        data = {
            "schema_version": "1.0",
            "generated_at": now(),
            "source": "deterministic_empty",
            "summary": "本项目无用户上传素材, brief 设计将依赖资源库 + 叙事模板",
            "file_inventory": [],
            "dominant_topics": [],
            "key_terms": [],
            "data_points": [],
            "coverage_hints": {"well_covered_topics": [], "thinly_covered_topics": [],
                               "gap_topics": [], "unexpected_topics": [],
                               "biggest_gaps_note": ""},
            "per_chapter_hint": [],
            "must_use_materials": [],
            "forbidden_or_low_confidence_materials": [],
            "topic_to_resources": {},
            "notes_for_brief_design": "无素材, brief 必须依靠 template_library + logic_knowledge 设计",
        }
        write_json(out_path, data)
        return {
            "ok": True, "stage": "SOURCE_UNDERSTAND",
            "source_understanding": str(out_path),
            "source": data["source"], "file_count": 0,
        }

    # Build per_format_analyses payload: include per-file Claude analyses
    # produced by analyze_project_sources (Chinese-keyed) AND pptx deck briefs.
    per_format_pdf_doc = []
    for it in (analysis_report.get("items") or []):
        if not isinstance(it, dict):
            continue
        if it.get("type") in {"pdf", "doc"}:
            per_format_pdf_doc.append({k: v for k, v in it.items()
                                       if k not in {"全文", "页面文本", "chunks"}})

    context = {
        "idea_intake_light": brief_context,
        "per_format_analyses": {
            "pdf_or_doc": per_format_pdf_doc,
            "figure": [{"figure_id": f.get("figure_id"),
                        "source_path": f.get("source_path"),
                        "what_it_shows": f.get("what_it_shows"),
                        "anchor_terms": f.get("anchor_terms"),
                        "semantic_ok": f.get("semantic_ok")} for f in figure_list],
            "sheet": [{"sheet_id": s.get("sheet_id"),
                       "source_path": s.get("source_path"),
                       "topic": s.get("topic"),
                       "anchor_terms": s.get("anchor_terms")} for s in sheet_list],
            "ppt_decks": [{
                "deck_id": d.get("deck_id"),
                "标题": d.get("标题") or d.get("title"),
                "报告类型": d.get("报告类型") or d.get("deck_type"),
                "主题标签": d.get("主题标签") or d.get("topic_tags"),
                "论述弧线": d.get("论述弧线") or d.get("narrative_arc"),
                "总页数": d.get("总页数") or d.get("slide_count"),
                "本项目相关性评分": d.get("本项目相关性评分"),
                "适合本项目章节": d.get("适合本项目章节"),
            } for d in deck_list],
        },
        "project_units_summary": {
            "deck_count": len(deck_list),
            "doc_count": len(doc_list),
            "figure_count": len(figure_list),
            "sheet_count": len(sheet_list),
            "section_count": len(project_resources["section_units"].get("sections") or []),
            "slide_count": len(project_resources["slide_units"].get("slides") or []),
            "total_files": total_files,
            "by_type": (project_resources["source_digest"].get("by_type") or {}),
        },
    }

    prompt = (
        "Synthesize ALL per-format source analyses into ONE master "
        "source-understanding per the skill schema. Be brief-aware (read "
        "idea_intake_light) and produce: summary, file_inventory with "
        "relevance scores, dominant_topics, key_terms, per_chapter_hint, "
        "must_use_materials, topic_to_resources. "
        "Return JSON only — strict schema.\n\n"
        "INPUT:\n" + json.dumps(context, ensure_ascii=False)
    )
    outcome = claude_cli.call_claude_json(
        prompt,
        skill=["skills/sources/source_understanding.md"],
        timeout=600,
    )
    if not (outcome.get("ok") and isinstance(outcome.get("data"), dict)):
        # Fallback: deterministic stub built from per-format analyses
        inventory = []
        for it in per_format_pdf_doc:
            inventory.append({
                "resource_id": Path(it.get("path", "")).stem,
                "type": it.get("type"),
                "name": it.get("文件名"),
                "one_line_summary": (it.get("核心论断") or it.get("文档主题") or "")[:30],
                "relevance_score": it.get("relevance_score"),
                "why_relevant": "deterministic fallback (Claude master failed)",
                "likely_use": "citation",
            })
        data = {
            "schema_version": "1.0",
            "generated_at": now(),
            "source": "stub",
            "fallback_reason": outcome.get("error"),
            "summary": f"上传 {total_files} 个文件; Claude 主综合失败, 退化到 per-format 拼接",
            "file_inventory": inventory,
            "dominant_topics": [],
            "key_terms": [],
            "data_points": [],
            "coverage_hints": {"well_covered_topics": [], "thinly_covered_topics": [],
                               "gap_topics": [], "unexpected_topics": [],
                               "biggest_gaps_note": ""},
            "per_chapter_hint": [],
            "must_use_materials": [],
            "forbidden_or_low_confidence_materials": [],
            "topic_to_resources": {},
            "notes_for_brief_design": "source-understanding Claude 综合失败, 仅有 per-format 列表可用",
        }
        write_json(out_path, data)
        return {
            "ok": True, "stage": "SOURCE_UNDERSTAND",
            "source_understanding": str(out_path),
            "source": "stub", "file_count": total_files,
            "fallback_reason": outcome.get("error"),
        }

    data = outcome["data"]
    data.setdefault("schema_version", "1.0")
    data["generated_at"] = now()
    data["source"] = "claude"
    write_json(out_path, data)
    return {
        "ok": True, "stage": "SOURCE_UNDERSTAND",
        "source_understanding": str(out_path),
        "source": "claude",
        "file_count": total_files,
        "pptx_briefed": pptx_summary.get("ok") if isinstance(pptx_summary.get("ok"), list) else None,
        "dominant_topics_count": len(data.get("dominant_topics") or []),
        "key_terms_count": len(data.get("key_terms") or []),
        "must_use_count": len(data.get("must_use_materials") or []),
    }


def _group_briefs_by_section(briefs: list) -> list:
    """v17 C.2: group slide briefs by (deck_id, section_id) so LLM sees continuous-
    page opportunities. Returns compact list per section with slide_ids ordered by
    slide_index_in_source. Used in Stage 1b payload's candidate_pool_stats."""
    from collections import defaultdict
    groups: dict = defaultdict(list)
    for b in briefs or []:
        if not isinstance(b, dict):
            continue
        key = (b.get("deck_id") or "", b.get("section_id") or "")
        groups[key].append(b)
    out = []
    for (did, sid), items in groups.items():
        items_sorted = sorted(items, key=lambda x: x.get("slide_index_in_source") or 0)
        slide_ids = [i.get("slide_id") for i in items_sorted]
        out.append({
            "deck_id": did,
            "section_id": sid,
            "slide_count": len(items_sorted),
            "slide_ids_ordered": slide_ids,
            "section_role": items_sorted[0].get("section_role") if items_sorted else "",
            "deck_title": items_sorted[0].get("deck_title") if items_sorted else "",
        })
    # sort by slide_count desc — biggest sections first (best continuous reuse chance)
    out.sort(key=lambda g: -g["slide_count"])
    return out[:10]  # cap to 10 sections


def _synthesize_slide_matches_from_outline(pdir, outline: dict) -> None:
    """v17: OUTLINE stage now owns all matching. Synthesize slide-matches.json
    from outline.slides[] so downstream stages (SLIDE_PLAN / DRAFT_ASSEMBLY_PLAN /
    SLIDE_REWRITE) that read slide-matches.json keep working without changes.
    Also synthesize slide-matches-review.json (empty issue list — audit is now
    embedded in outline.slides[]._review_audit).
    """
    slides_out = outline.get("slides") or []
    matches: list[dict] = []
    for s in slides_out:
        if not isinstance(s, dict):
            continue
        target_idx = s.get("slide_index") or s.get("target_slide_index")
        src_ids = s.get("source_resource_ids") or []
        alternates = s.get("alternates") or []
        # v30 fix: prefer source_carrier_resource_kind, fall back to Stage 1b's
        # short field name `kind` (skill outputs `kind`, driver sweep uses the
        # longer name — normalization at merge point may miss slides written
        # after the merge, so this fallback is defensive).
        kind = (s.get("source_carrier_resource_kind")
                or s.get("kind") or "matching_fallback")
        # Build candidates list (top-1 from source_resource_ids + rest from alternates)
        candidates: list[dict] = []
        rank = 1
        for cand in list(src_ids) + list(alternates):
            # v30 fix: source_resource_ids items may be plain strings (slide_id)
            # or dicts. Normalize both — before, string entries silently dropped
            # so 30 slides ended up with empty candidates lists and SLIDE_PLAN
            # marked them all as placeholders.
            if isinstance(cand, str):
                cand = {"slide_id": cand}
            elif not isinstance(cand, dict):
                continue
            candidates.append({
                "rank": rank,
                "resource_id": cand.get("slide_id"),
                "deck_id": cand.get("deck_id"),
                "score": cand.get("rank_score"),
                "confidence": ("high" if (cand.get("rank_score") or 0) >= 1.5
                                else "medium" if (cand.get("rank_score") or 0) >= 0.5
                                else "low"),
                "recommended_reuse_mode": ("direct_slide_reuse" if kind == "carrier_bound"
                                            else "partial_reuse" if kind == "matching_fallback"
                                            else "new_slide"),
                "match_reasons": cand.get("match_reasons") or [],
                "source_owner": "library",
                "source": "outline_v17",
            })
            rank += 1
        matches.append({
            "target_slide_index": target_idx,
            "target_role": s.get("target_role"),
            "target_title": s.get("target_title"),
            "target_claim": s.get("target_claim"),
            "section_index": s.get("chapter_index"),
            "candidates": candidates,
            "source": "outline_v17_synthesized",
            "kind": kind,
        })
    write_json(pdir / "slide-matches.json", {
        "schema_version": "v17.0",
        "generated_at": now(),
        "source": "synthesized_from_outline",
        "slide_matches": matches,
        "total_targets": len(matches),
        "carrier_bound_count": sum(1 for m in matches if m["kind"] == "carrier_bound"),
        "matching_fallback_count": sum(1 for m in matches if m["kind"] == "matching_fallback"),
        "new_count": sum(1 for m in matches if m["kind"] == "new"),
    })
    # Empty review artifact (audit is embedded per-slide in outline)
    write_json(pdir / "slide-matches-review.json", {
        "schema_version": "v17.0",
        "generated_at": now(),
        "note": "SLIDE_MATCHING_REVIEW folded into OUTLINE.slides[]._review_audit in v17",
        "issues": [],
        "final_ok": True,
    })


def _normalize_outline_chapter_links(outline: dict, chapter_plan: list[dict]) -> dict:
    """Keep outline slide indices, chapter map, and section_breakdown in sync.

    Claude fix rounds may add/delete/reorder slides. Downstream GAP/DRAFT stages
    rely on absolute slide_index plus section_index grouping, so the driver owns
    this structural normalization instead of trusting model output.
    """
    if not isinstance(outline, dict):
        return outline
    slides = outline.get("slides")
    if not isinstance(slides, list):
        return outline

    ch_meta: dict[int, dict] = {}
    for ch in chapter_plan or []:
        if not isinstance(ch, dict):
            continue
        try:
            ci = int(ch.get("section_index"))
        except (TypeError, ValueError):
            continue
        ch_meta[ci] = ch

    chapter_to_slide_map: dict[int, list[int]] = {}
    normalized_slides: list[dict] = []
    for abs_idx, s in enumerate(slides, start=1):
        if not isinstance(s, dict):
            continue
        row = dict(s)
        row["slide_index"] = abs_idx
        ch_idx = row.get("chapter_index", row.get("section_index"))
        try:
            ch_idx = int(ch_idx)
        except (TypeError, ValueError):
            ch_idx = 0
        row["chapter_index"] = ch_idx
        row["section_index"] = ch_idx
        chapter_to_slide_map.setdefault(ch_idx, []).append(abs_idx)
        normalized_slides.append(row)

    section_breakdown: list[dict] = []
    for ch_idx, slide_indices in sorted(chapter_to_slide_map.items()):
        meta = ch_meta.get(ch_idx, {})
        section_breakdown.append({
            "section_index": ch_idx,
            "chapter": meta.get("chapter") or meta.get("title") or f"Chapter {ch_idx}",
            "section_role": meta.get("section_role"),
            "purpose": meta.get("purpose"),
            "slide_indices": slide_indices,
            "page_count": len(slide_indices),
        })

    outline["slides"] = normalized_slides
    outline["slide_count"] = len(normalized_slides)
    outline["chapter_to_slide_map"] = chapter_to_slide_map
    outline["section_breakdown"] = section_breakdown
    return outline


# ============================================================
# v24 修 F3: IDEA-Library Reconcile helper
# ============================================================
def _reconcile_idea_with_library(pdir, idea: dict) -> dict | None:
    """对 chapter_plan 逐条 claim 查库, 无 library support 的 claim 从 plan 移除.

    策略:
      - 每条 claims_to_make 提取 keywords, 通过 cascade_search 查库
      - 若 top-3 candidate 都 score < 3.0 → 该 claim unsupported
      - expected_pages_indicative -= unsupported claim 数
      - 若 chapter 全部 claim unsupported 且非结构章 (cover/closing/agenda) → chapter 删除
      - 写 idea-analysis-reconciled.json (审计) + 返回 reconciled idea 供后续使用

    Structural chapters (cover/agenda/closing/references/section_divider) 不参与 reconcile —
    它们不需要 subject match, sweep 会用 topic-axis 视觉承载.
    """
    from . import outline_context as _oc
    from . import library_query as _lq
    chapter_plan = idea.get("chapter_plan") or []
    if not chapter_plan:
        return None
    STRUCTURAL = {"cover", "agenda", "closing", "references", "section_divider"}

    # v24 F3 v2: 用 deck 主题标签作为 chapter-level 粗筛支持,而非 slide-level 打分
    # (v1 太严: 把 IDEA 章级抽象 claim 打分误判为无支持)
    # 策略:
    #   - 每 chapter 提取 chapter title + purpose + claims 的关键词 (少剥离,保留 domain terms)
    #   - 若库里至少 1 个 deck 的主题标签跟这些 keyword 有 hit → 该 chapter 有 support
    #   - 只有当 keyword hit 0 个 deck (完全无关话题) → 才 reconcile chapter
    #   - 单条 claim 的判定: keyword hit ≥ 2 个 deck → support; < 2 → unsupported
    try:
        idx_data = _lq.load_decks_index() or {}
        all_decks = idx_data.get("decks") or []
    except Exception:
        return None
    # 建 keyword → deck_count map, 用 token contain (not exact)
    def _tokens(text: str) -> set:
        out = set()
        for tok in text.replace(",", " ").replace(":", " ").replace("·", " ").replace("/", " ").replace(" ", " ").split():
            t = tok.strip().lower()
            if len(t) >= 2:
                out.add(t)
        return out

    deck_topic_tags: list = []
    for d in all_decks:
        tags = " ".join(d.get("主题标签") or []) + " " + (d.get("标题") or "")
        deck_topic_tags.append(tags.lower())

    def _deck_hit_count(kws: set) -> int:
        """How many decks have at least one keyword substring in their topic_tags/title."""
        count = 0
        for tags in deck_topic_tags:
            if any(kw in tags for kw in kws):
                count += 1
        return count

    reconciled_plan: list = []
    reconcile_log: list = []
    total_removed_claims = 0
    total_pages_removed = 0
    for ch in chapter_plan:
        if not isinstance(ch, dict):
            reconciled_plan.append(ch)
            continue
        role = (ch.get("section_role") or "").lower()
        if role in STRUCTURAL:
            reconciled_plan.append(ch)
            continue

        claims = ch.get("claims_to_make") or []
        if not claims:
            reconciled_plan.append(ch)
            continue

        # chapter-level context tokens (title + purpose)
        ctx_tokens = _tokens((ch.get("chapter") or "") + " " + (ch.get("purpose") or ""))

        supported: list = []
        unsupported: list = []
        for claim in claims:
            if not isinstance(claim, str) or len(claim) < 6:
                supported.append(claim)
                continue
            # v2: 只剥少量高度通用词, 保留 domain terms
            claim_tokens = _tokens(claim)
            # 合并 chapter ctx 补充语境
            combined = claim_tokens | ctx_tokens
            # 剥离极通用词 (至少要有 3 个 domain token)
            LIGHT_GENERIC = {"本章", "面向", "研究", "工作", "本层", "方向", "路径", "方法",
                             "示范", "覆盖", "回收", "上升", "尺度", "整体", "统一", "主要",
                             "推动", "确立", "抬升", "把", "为", "以", "在", "的", "了", "上"}
            filtered = {t for t in combined if t not in LIGHT_GENERIC and len(t) >= 2}
            if len(filtered) < 2:
                supported.append(claim)  # 不足以判断, 保留
                continue
            hits = _deck_hit_count(filtered)
            # threshold: hit at least 2 decks → supported (chapter-level bar, not slide-level)
            if hits >= 2:
                supported.append(claim)
            else:
                unsupported.append({
                    "claim": claim,
                    "keywords_searched": sorted(filtered)[:8],
                    "deck_hits": hits,
                })

        orig_pages = ch.get("expected_pages_indicative") or len(claims)
        n_removed = len(unsupported)
        new_pages = max(1, orig_pages - n_removed) if n_removed else orig_pages

        ch_reconciled = dict(ch)
        ch_reconciled["claims_to_make"] = supported
        ch_reconciled["expected_pages_indicative"] = new_pages
        if unsupported:
            ch_reconciled["_reconcile_removed_claims"] = [u["claim"] for u in unsupported]
            reconcile_log.append({
                "chapter_index": ch.get("section_index"),
                "chapter": ch.get("chapter"),
                "orig_claims": len(claims),
                "kept_claims": len(supported),
                "removed_claims": [u["claim"] for u in unsupported],
                "removed_details": unsupported,
                "orig_pages": orig_pages,
                "new_pages": new_pages,
            })
            total_removed_claims += n_removed
            total_pages_removed += (orig_pages - new_pages)

        # 只有当整章 0 claim 且 chapter role 非 core narrative role 时才砍
        # v2: motivation/framework/method/discussion 都保留 (不允许整章删)
        reconciled_plan.append(ch_reconciled)

    reconciled = dict(idea)
    reconciled["chapter_plan"] = reconciled_plan
    reconciled["_reconcile_summary"] = {
        "orig_chapters": len(chapter_plan),
        "kept_chapters": len(reconciled_plan),
        "removed_claims_total": total_removed_claims,
        "pages_reduced_total": total_pages_removed,
        "log": reconcile_log,
    }

    write_json(pdir / "idea-analysis-reconciled.json", reconciled)
    print(
        f"[RECONCILE] chapter_plan: {len(chapter_plan)}→{len(reconciled_plan)} chapters, "
        f"removed {total_removed_claims} claims across {len(reconcile_log)} chapters, "
        f"pages reduced by {total_pages_removed}",
        flush=True,
    )
    return reconciled


def _write_stage_status(pdir, status_filename: str, *, human_approved: bool = True,
                        **extra) -> None:
    """Unified per-stage status writer.

    Every stage writes a status file after successful run. Fields:
      - schema_version, generated_at, status: fixed defaults
      - human_approved: default True (user 永远同意); UI 层可 write False 阻塞下游
      - **extra: stage-specific fields (codex_final_ok, fix_round, slide_count, etc.)

    Usage:
      _write_stage_status(pdir, "idea-user-status.json",
                          codex_final_ok=True, fix_round=2, story_design_mode="AUTO")
    """
    payload = {
        "schema_version": "1.0",
        "generated_at": now(),
        "status": "ready",
        "human_approved": human_approved,
    }
    payload.update(extra)
    write_json(pdir / status_filename, payload)


def _check_upstream_approval(pdir, upstream_status_filename: str,
                              upstream_stage_label: str,
                              current_stage_label: str) -> dict | None:
    """Gate check: reject current stage if upstream's human_approved is explicitly False.

    Returns:
      None → pass (upstream approved or status file absent/malformed → default pass)
      dict → gate failure result to return from stage handler

    Design: default is PASS. Only blocks when UI/human explicitly sets
    human_approved=False in the upstream status file.
    """
    status = read_json(pdir / upstream_status_filename, {}) or {}
    if status.get("human_approved") is False:
        return {
            "ok": False,
            "stage": current_stage_label,
            "error": (f"上一阶段 {upstream_stage_label} 未获人类 approve "
                      f"({upstream_status_filename}.human_approved=False), "
                      f"{current_stage_label} 被 gate 阻塞"),
            "retry_hint": (f"请人类 review {upstream_stage_label} 产物, "
                           f"满意后将 {upstream_status_filename} 的 human_approved 改为 true"),
        }
    return None


def _archive_human_txt(human_txt, feedback_round: int, *, suffix: str = "applied") -> None:
    """Rename *-human-feedback.txt → .round-N.<suffix>.txt to prevent re-consumption.
    Generic — used by both IDEA and OUTLINE human-fix loops.
    """
    try:
        target = human_txt.with_name(
            f"{human_txt.stem}.round-{feedback_round}.{suffix}{human_txt.suffix}"
        )
        if target.exists():
            target = human_txt.with_name(
                f"{human_txt.stem}.round-{feedback_round}.{suffix}."
                f"{now().replace(':', '').replace('-', '').replace('T', '_')[:15]}"
                f"{human_txt.suffix}"
            )
        human_txt.rename(target)
        print(f"[OUTLINE] archived {human_txt.name} → {target.name}", flush=True)
    except Exception as exc:
        print(f"[OUTLINE] archive human_txt failed: {exc}", flush=True)


def _render_outline_human_summary(data: dict, pdir, claude_cli) -> None:
    """Re-render outline.md via outline_human_summary skill (non-blocking).
    Called after human-fix to refresh the human-readable view.
    """
    try:
        md_prompt = (
            "Render outline.md from the JSON below. Your ENTIRE response IS the "
            "markdown file content. First character MUST be `#`. No preamble, no "
            "code fence.\n\nINPUT:\n" + json.dumps({"outline": data}, ensure_ascii=False)
        )
        sum_res = claude_cli.call_claude_text(
            md_prompt,
            skill=["skills/outline_gen/outline_human_summary.md"],
            timeout=600,
        )
        if sum_res.get("ok"):
            md = (sum_res.get("text") or "").strip()
            if md.startswith("```markdown"):
                md = md.split("```markdown", 1)[1].rstrip("`").strip()
            elif md.startswith("```"):
                md = md.strip("`").strip()
            if md:
                (pdir / "outline.md").write_text(md, encoding="utf-8")
    except Exception as exc:
        print(f"[OUTLINE] re-render outline.md failed: {exc}", flush=True)


def _run_outline_human_fix_round(project_id: str, pdir, prior_outline: dict,
                                  human_txt, *, oc, claude_cli, codex_cli) -> dict:
    """Big-loop human-fix round for OUTLINE_GENERATION (mirror IDEA).

    Trigger: user 写入 outline-human-feedback.txt (自然语言) 后再调 run_stage("OUTLINE_GENERATION").
    Flow:
      1. structurer: outline_revision.md mode=structure_only → outline-human-issues.json
      2. fix: outline_fix_from_review.md (issues source=human, + pattern bodies)
      3. safety-net codex review 1 round (outline_review.md)
      4. archive human_txt to .applied.round-N
      5. re-render outline.md
      6. update outline-user-status.json (keep awaiting_human_review=true, 支持多轮)
    """
    raw_text = human_txt.read_text(encoding="utf-8").strip()
    if not raw_text:
        return {"ok": False, "stage": "OUTLINE_GENERATION",
                "error": "outline-human-feedback.txt 为空, 无法处理"}

    prior_status = read_json(pdir / "outline-user-status.json", {}) or {}
    feedback_round = int(prior_status.get("human_feedback_round", 0)) + 1

    idea = read_json(pdir / "idea-analysis.json", {}) or {}
    su = (read_json(pdir / "data" / "source-understanding.json", None)
          or read_json(pdir / "source-understand.json", None)
          or {})

    print(f"[OUTLINE] human-fix round {feedback_round} triggered "
          f"({len(raw_text)} chars feedback)", flush=True)

    # ─── Step 1: structure natural language → issues ───
    structurer_input = {
        "mode": "structure_only",
        "current_outline": prior_outline,
        "user_feedback": {"feedback_round": feedback_round, "raw_text": raw_text},
        "idea_analysis": idea,
        "source_understanding": su,
    }
    structurer_prompt = (
        "Run outline_revision.md in structure_only mode. Parse user's natural-language "
        "feedback into structured issues (source=human). DO NOT modify outline.json. "
        "Output {mode, feedback_round, issues[], ambiguous[], rejected[], "
        "escalate_to_idea[], summary} JSON.\n\n"
        "INPUT:\n" + json.dumps(structurer_input, ensure_ascii=False)
    )
    structurer_out = claude_cli.call_claude_json(
        structurer_prompt,
        skill=["skills/outline_gen/outline_revision.md"],
        timeout=600,
    )
    if not (structurer_out.get("ok") and isinstance(structurer_out.get("data"), dict)):
        return {"ok": False, "stage": "OUTLINE_GENERATION",
                "error": f"structurer 失败: {(structurer_out.get('error') or '')[:200]}",
                "human_feedback_round": feedback_round}
    structured = structurer_out["data"]
    write_json(pdir / "outline-human-issues.json", structured)
    issues_raw = structured.get("issues") or []
    ambiguous_ct = len(structured.get("ambiguous") or [])
    rejected_ct = len(structured.get("rejected") or [])
    escalate_ct = len(structured.get("escalate_to_idea") or [])
    print(f"[OUTLINE] human-fix rnd{feedback_round} structurer: "
          f"issues={len(issues_raw)} ambiguous={ambiguous_ct} rejected={rejected_ct} "
          f"escalate_to_idea={escalate_ct}", flush=True)

    if not issues_raw:
        _archive_human_txt(human_txt, feedback_round, suffix="no-issues")
        warn_bits = []
        if ambiguous_ct: warn_bits.append(f"ambiguous={ambiguous_ct}")
        if rejected_ct: warn_bits.append(f"rejected={rejected_ct}")
        if escalate_ct: warn_bits.append(f"escalate_to_idea={escalate_ct} (回 IDEA 阶段处理)")
        return {"ok": True, "stage": "OUTLINE_GENERATION",
                "outline": str(pdir / "outline.json"),
                "human_feedback_round": feedback_round,
                "awaiting_human_review": True,
                "warning": (f"structurer 未产出任何可执行 issue ({', '.join(warn_bits)}); "
                            f"prior outline 未改, 请人类补充/澄清 feedback")}

    # ─── Step 2: surgical fix ───
    primary_pid = ((idea.get("selected_narrative_arc") or {}).get("primary_pattern_id"))
    selected_pattern_body = (oc.load_deck_level_pattern_full(primary_pid)
                             if primary_pid else None)
    rhythm_bodies: dict = {}
    for ch in (idea.get("chapter_plan") or []):
        rpid = ch.get("section_rhythm_pattern_id") if isinstance(ch, dict) else None
        if rpid and rpid not in rhythm_bodies:
            b = oc.load_rhythm_pattern_trimmed(rpid)
            if b:
                rhythm_bodies[rpid] = b
    hard_rules = oc.load_logic_story_hard_rules_summary()
    archetypes = oc.load_page_specific_archetypes()  # full list; per-chapter filter applied below
    archetype_summary = [{"id": a.get("id"), "summary": a.get("summary")}
                          for a in archetypes if isinstance(a, dict)]

    fix_input = {
        "prior_outline": prior_outline,
        "issues": issues_raw,   # structurer 已经标 source=human
        "idea_analysis": oc.compact_idea_for_fix(idea),
        "logic_story_hard_rules_summary": hard_rules,
        "page_specific_rules_summary": archetype_summary,
        "selected_narrative_pattern_body": selected_pattern_body,
        "rhythm_pattern_bodies": rhythm_bodies,
    }
    fix_prompt = (
        "Apply surgical fix per the outline_fix_from_review skill. Output complete "
        "patched outline.json v1.0 (strict JSON, all original fields preserved, "
        "only flagged locations modified, add/update fix_round + "
        "referenced_review_issues + user_concern_history).\n\n"
        "INPUT:\n" + json.dumps(fix_input, ensure_ascii=False)
    )
    fix_out = claude_cli.call_claude_json(
        fix_prompt,
        skill=["skills/outline_gen/outline_fix_from_review.md"],
        timeout=900,
    )
    if not (fix_out.get("ok") and isinstance(fix_out.get("data"), dict)):
        return {"ok": False, "stage": "OUTLINE_GENERATION",
                "error": f"human-fix 失败: {(fix_out.get('error') or '')[:200]}",
                "human_feedback_round": feedback_round}
    patched = fix_out["data"]
    # v30 safety guard: reject fragment / truncated fix output that dropped
    # top-level outline structure (slides / chapter_to_slide_map / identity).
    # Only structural completeness is checked; a large slide-count drop is
    # legitimate (human may ask to remove many slides).
    _required_keys = ("slides", "chapter_to_slide_map", "identity")
    _missing = [k for k in _required_keys if k not in patched]
    _new_slides = patched.get("slides") or []
    if _missing or not isinstance(_new_slides, list) or len(_new_slides) < 1:
        return {"ok": False, "stage": "OUTLINE_GENERATION",
                "error": (f"human-fix 输出结构不完整: missing={_missing}, "
                          f"slides={len(_new_slides)}; prior outline preserved"),
                "human_feedback_round": feedback_round}
    patched["schema_version"] = "1.0"
    patched["generated_at"] = now()
    patched["source"] = "claude_human_surgical_fix"
    write_json(pdir / "outline.json", patched)

    # Refresh slide-matches synth (downstream stages read it)
    try:
        _synthesize_slide_matches_from_outline(pdir, patched)
    except Exception as exc:
        print(f"[OUTLINE] slide-matches synth failed: {exc}", flush=True)

    # ─── Step 3: safety-net codex review (1 round) ───
    codex_ok = False
    codex_issues_remaining: list = []
    review_prompt = (
        "Review the human-patched outline.json following the outline_review skill.\n"
        "Output JSON only with shape {ok, round, issues, summary}.\n\n"
        "INPUT:\n" + json.dumps({
            "outline": patched,
            "idea_analysis": idea,
            "logic_story_hard_rules_summary": hard_rules,
            "page_specific_rules_summary": archetype_summary,
            "round": 1,
            "prior_issues": [],
            "user_concern_history": patched.get("user_concern_history", []),
        }, ensure_ascii=False)
    )
    rev = codex_cli.call_codex_json(
        review_prompt,
        skill=["skills/outline_gen/outline_review.md"],
        timeout=600,
    )
    if rev.get("ok") and isinstance(rev.get("data"), dict):
        rdata = rev["data"]
        codex_ok = bool(rdata.get("ok"))
        codex_issues_remaining = rdata.get("issues") or []
        review_history = read_json(pdir / "outline-review.json", {}) or {}
        rounds = review_history.get("rounds") or []
        rounds.append({**rdata, "phase": f"post_human_fix_round_{feedback_round}"})
        write_json(pdir / "outline-review.json", {
            **review_history,
            "rounds": rounds,
            "final_ok": codex_ok,
        })

    # ─── Step 4: archive human_txt ───
    _archive_human_txt(human_txt, feedback_round, suffix="applied")

    # ─── Step 5: re-render outline.md ───
    _render_outline_human_summary(patched, pdir, claude_cli)

    # ─── Step 6: update status (保持 awaiting_human_review=true) ───
    # 保留 UI 在 prior_status 里可能显式设的 human_approved (Q9 fix):
    # 大 loop 只是修当前阶段, 不该悄悄把 UI 的 "不同意" 重置为 True
    _prior_human_approved = prior_status.get("human_approved")
    _write_stage_status(pdir, "outline-user-status.json",
                         human_approved=(True if _prior_human_approved is None
                                          else bool(_prior_human_approved)),
                         human_feedback_round=feedback_round,
                         fix_round=patched.get("fix_round", 0),
                         auto_approved=False,
                         awaiting_human_review=True,
                         codex_final_ok=codex_ok,
                         post_human_fix_issues_count=len(codex_issues_remaining))

    return {"ok": True, "stage": "OUTLINE_GENERATION",
            "outline": str(pdir / "outline.json"),
            "source": patched.get("source"),
            "human_feedback_round": feedback_round,
            "fix_round": patched.get("fix_round", 0),
            "awaiting_human_review": True,
            "codex_final_ok": codex_ok,
            "post_human_fix_issues_count": len(codex_issues_remaining),
            "structurer_summary": structured.get("summary")}


def _run_outline_generation(project_id: str) -> dict:
    """E: OUTLINE generation pipeline (v3.2 IDEA-aware, 2026-06-29 rewrite).

    Consumes:
      - projects/<id>/idea-analysis.json (v4.0): chapter_plan with
        section_rhythm_pattern_id (v4.0, 替代 v3.2 candidate_carrier_sections) /
        narrative_constraints + user_concern_history +
        provenance.section_inclusion_rationale
      - projects/<id>/idea-intake-light.json (v1.1): pattern_matching_hints
      - data/resources_library/rule/page_specific/ (54 archetype rules)
      - data/resources_library/rule/logic_story/ (41 hard rules)
      - data/resources_library/logic/section_level/ (rhythm patterns)
      - data/resources_library/material/decks/<id>/section_NN/slide_NN.md
      - projects/<id>/data/pdf/*.json (project PDF briefs)

    Skills (6, replaces old 4-skill flow):
      Stage 1a — outline_chapter_stub.md (per chapter, parallel max 4):
        decide N slides + role + archetype + placement + page_purpose_hint
      Stage 1b — outline_slide_detail.md (per chapter, parallel max 4):
        fill target_claim/key_points/source_resource_ids/anchor/evidence/delivery
      Stage 2 — outline_review.md (codex, max 3 rounds): 11 cats + Cat 10 cross-stage user_concern
      Stage 2.5 — outline_fix_from_review.md (Claude surgical fix between review rounds)
      Stage 3 — outline_human_summary.md (Claude renders outline.md)

    Outputs (compatible with P20a SLIDE_MATCHING bypass + P20b GAP_CARD annotations):
      - outline.json (v1.0, slides with source_resource_ids as dict)
      - outline.md (human-readable)
      - outline-review.json (codex rounds log)
      - outline-user-status.json (UI status)
      - outline-chapter-stubs.json (Stage 1a intermediate)
    """
    import os as _os
    import time as _time
    import concurrent.futures as _cf
    from . import claude_cli, codex_cli, outline_context as oc

    pdir = project_dir(project_id)

    # ═══ Big-loop branch: human natural-language feedback fix ═══
    # **优先级最高 (放在 gate 前)**: 人类写反馈 = 想修当前阶段, gate 只该挡"推进",
    # 不该挡"修当前". 若人类写入 outline-human-feedback.txt 且已有 prior outline, 走
    # structure_only → outline_fix_from_review → codex 兜底 的手术式 fix 路径,
    # 不动主生成/小 loop 的结果。大 loop 不限次数, 人类可反复写 txt 触发。
    human_txt = pdir / "outline-human-feedback.txt"
    existing_outline_early = read_json(pdir / "outline.json", None)
    if human_txt.exists() and existing_outline_early:
        return _run_outline_human_fix_round(
            project_id, pdir, existing_outline_early, human_txt,
            oc=oc, claude_cli=claude_cli, codex_cli=codex_cli,
        )

    # ═══ Gate: 上一阶段 (IDEA_ANALYSIS) 人类 approve 检查 ═══
    # gate 只挡"从头跑主生成"路径; 大 loop 修当前阶段 (上方) 不受 gate 影响
    _gate_fail = _check_upstream_approval(
        pdir, "idea-user-status.json",
        upstream_stage_label="IDEA_ANALYSIS",
        current_stage_label="OUTLINE_GENERATION")
    if _gate_fail is not None:
        return _gate_fail

    idea = deepcopy(read_json(pdir / "idea-analysis.json", {}) or {})
    intake = read_json(pdir / "idea-intake-light.json", {}) or {}
    # v6.3 (2026-07-30): OUTLINE reads user_outline directly from question-state
    # (raw_user_input was dropped from idea-intake-light). user_outline is the
    # ONLY raw text OUTLINE needs — an explicit exception to the "downstream stages
    # avoid question-state" rule.
    _qs = read_json(pdir / "question-state.json", {}) or {}
    user_outline = ((_qs.get("answers") or {}).get("user_outline") or "").strip()

    idea.setdefault("structural_page_contract", _default_structural_page_contract())
    _outline_structural_norm_changes = []
    for _ch in idea.get("chapter_plan") or []:
        if not isinstance(_ch, dict):
            continue
        _role = str(_ch.get("section_role") or "").lower()
        if _role in {"opening", "cover", "agenda", "section_divider", "references"}:
            continue
        if _ch.get("requires_section_divider") is not True:
            _ch["requires_section_divider"] = True
            _outline_structural_norm_changes.append(
                f"chapter[{_ch.get('section_index')}].requires_section_divider")
        if _ch.get("structural_prefix_role") != "section_divider":
            _ch["structural_prefix_role"] = "section_divider"
            _outline_structural_norm_changes.append(
                f"chapter[{_ch.get('section_index')}].structural_prefix_role")
    if _outline_structural_norm_changes:
        idea.setdefault("provenance", {}).setdefault("driver_normalization", [])
        idea["provenance"]["driver_normalization"].append({
            "stage": "OUTLINE_GENERATION",
            "reason": "legacy idea lacked structural divider contract; normalized before Stage 1a",
            "fields": _outline_structural_norm_changes,
        })
    idea, _outline_parallel_contract_changes = _ensure_parallel_group_contracts(idea)
    if _outline_parallel_contract_changes:
        print(f"[OUTLINE] normalized {len(_outline_parallel_contract_changes)} "
              "parallel group contracts before Stage 1a", flush=True)

    chapter_plan = idea.get("chapter_plan") or []
    if not isinstance(chapter_plan, list) or not chapter_plan:
        return {
            "ok": False,
            "stage": "OUTLINE_GENERATION",
            "error": "idea-analysis.chapter_plan empty or missing — run IDEA_ANALYSIS first",
            "retry_hint": "重跑 IDEA_ANALYSIS 直到 chapter_plan 非空",
        }

    # User-supplied outline override: keep legacy path (uses old deck_outline.md skill)
    if user_outline:
        return _run_outline_with_user_override(
            project_id=project_id, brief=idea, brief_raw=idea,
            understanding=read_json(pdir / "data/source-understanding.json", {}) or {},
            user_outline=user_outline,
        )

    # ============================================================
    # Global resources (shared across all chapter calls)
    # ============================================================
    print("[OUTLINE] loading global resources...", flush=True)
    archetypes = oc.load_page_specific_archetypes()  # full list; per-chapter filter applied below
    hard_rules = oc.load_logic_story_hard_rules_summary()
    resource_library_contract = oc.load_resource_library_contract_summary()
    try:
        project_pdf_briefs = oc.load_pdf_briefs_compact(project_id)
    except Exception:
        project_pdf_briefs = []
    must_keep = (idea.get("reuse_strategy") or {}).get("must_keep_terms") or []
    anchor_terms = (idea.get("identity") or {}).get("anchor_terms") or []
    audience = (idea.get("identity") or {}).get("audience") or {}
    if not isinstance(audience, dict):
        audience = (intake.get("audience") or {}) if isinstance(intake, dict) else {}
    if not isinstance(audience, dict):
        audience = {}
    intake_constraints = {
        "must_keep_terms": must_keep,
        "anchor_terms": anchor_terms,
        "audience_expected_depth": audience.get("depth") or audience.get("expected_depth"),
        "audience_tolerance_for_jargon": audience.get("jargon_tolerance") or audience.get("tolerance_for_jargon"),
    }
    nc = idea.get("narrative_constraints") or {}
    print(f"[OUTLINE] archetypes={len(archetypes)}, hard_rules={len(hard_rules)}, "
          f"project_pdf_briefs={len(project_pdf_briefs)}, chapters={len(chapter_plan)}",
          flush=True)
    archetype_for_prompt = [
        {"id": a.get("id"), "category": a.get("category"),
         "enforcement_level": a.get("enforcement_level"),
         "applicable_role": a.get("applicable_role") or [],
         "summary": (a.get("summary") or a.get("description") or "")[:120]}
        for a in archetypes
    ]

    def _chapter_candidate_sections(chapter: dict, *, max_sections: int = 8) -> list[dict]:
        explicit = chapter.get("material_section_hints") or chapter.get("candidate_carrier_sections") or []
        if isinstance(explicit, list) and explicit:
            normalized = []
            for c in explicit[:max_sections]:
                if not isinstance(c, dict):
                    continue
                normalized.append({
                    "deck_id": c.get("deck_id"),
                    "deck_title": c.get("deck_title") or c.get("deck"),
                    "section_id": c.get("section_id"),
                    "section_title": c.get("section_title") or c.get("title"),
                    "section_role": c.get("section_role"),
                    "page_count": (
                        c.get("page_count")
                        or c.get("expected_slide_capacity")
                        or c.get("n_slides_in_pool")
                    ),
                    "rank_score": c.get("rank_score") or c.get("score"),
                    "source": c.get("source") or "idea_material_section_hints",
                    "reason": c.get("reason"),
                })
            if normalized:
                return normalized
        inherited = oc.select_candidate_sections_from_library_understanding(
            idea, chapter, max_sections=max_sections)
        if inherited:
            print(f"[OUTLINE ch{chapter.get('section_index')}] inherited "
                  f"{len(inherited)} candidate sections from IDEA library_understanding",
                  flush=True)
        return inherited

    def _outline_slides_without_source(outline_doc: dict) -> list[dict]:
        missing: list[dict] = []
        for slide in (outline_doc.get("slides") or []):
            if not isinstance(slide, dict):
                continue
            if slide.get("source_resource_ids") or []:
                continue
            missing.append({
                "slide_index": slide.get("slide_index"),
                "chapter_index": slide.get("chapter_index"),
                "target_role": slide.get("target_role"),
                "target_title": (slide.get("target_title") or "")[:80],
                "target_claim": (slide.get("target_claim") or "")[:160],
                "kind": slide.get("kind") or slide.get("source_carrier_resource_kind"),
            })
        return missing

    def _is_navigation_target_slide(slide: dict) -> bool:
        role = str(slide.get("target_role") or "").lower()
        if role in {"cover", "agenda", "toc", "chapter_divider", "section_divider", "closing", "references"}:
            return False
        text = " ".join([
            str(slide.get("target_title") or ""),
            str(slide.get("target_claim") or ""),
            str(slide.get("page_purpose") or ""),
            str(slide.get("page_purpose_hint") or ""),
        ]).lower()
        return (
            any(t in text for t in ("contents", "agenda", "outline"))
            or any(t in text for t in ("目录", "导览", "进入研究展望章", "进入本章", "进入下一章"))
        )

    def _collect_chapter_rebind_candidates(chapter: dict, slides: list[dict]) -> list[dict]:
        ci = chapter.get("section_index")
        ch_layer = oc.infer_chapter_layer(chapter)
        terms: list[str] = []
        out: list[dict] = []
        seen_out: set[str] = set()

        def _add_candidate_from_brief(b: dict, *, source: str, score=None) -> None:
            sid = b.get("slide_id")
            if not sid or sid in seen_out:
                return
            seen_out.add(sid)
            out.append({
                "slide_id": sid,
                "deck_id": b.get("deck_id"),
                "section_id": b.get("section_id"),
                "deck_title": b.get("deck_title"),
                "section_role": b.get("section_role"),
                "inferred_layer": b.get("inferred_layer"),
                "page_role": b.get("页面角色") or b.get("page_role"),
                "role_in_section": b.get("页在section中的作用"),
                "title": b.get("标题") or b.get("title"),
                "claim": b.get("核心论断") or b.get("claim"),
                "what": b.get("本页讲什么") or b.get("what"),
                "layout": b.get("视觉骨架") or b.get("layout_tag"),
                "suitable_for": b.get("适合复用场景") or [],
                "score": score if score is not None else b.get("_score"),
                "source": source,
            })

        material_sections = _chapter_candidate_sections(chapter, max_sections=12)
        for sec in material_sections:
            if not isinstance(sec, dict):
                continue
            terms.extend([
                sec.get("section_title") or "",
                sec.get("deck_title") or "",
                sec.get("reason") or "",
            ])
        for sl in slides:
            if sl.get("chapter_index") != ci:
                continue
            terms.extend([sl.get("target_title") or "", sl.get("target_claim") or ""])
            terms.extend(sl.get("key_points") or [])
            terms.extend(sl.get("anchor_terms") or [])
            for ref in (sl.get("source_resource_ids") or []) + (sl.get("alternates") or []):
                if not isinstance(ref, dict) or not ref.get("slide_id"):
                    continue
                sid = ref.get("slide_id")
                if sid in seen_out:
                    continue
                seen_out.add(sid)
                out.append({
                    "slide_id": sid,
                    "deck_id": ref.get("deck_id"),
                    "section_id": ref.get("section_id"),
                    "deck_title": ref.get("deck_title"),
                    "section_role": ref.get("section_role"),
                    "inferred_layer": ref.get("inferred_layer"),
                    "title": ref.get("标题") or ref.get("title"),
                    "claim": ref.get("核心论断") or ref.get("claim"),
                    "what": ref.get("本页讲什么") or ref.get("what"),
                    "layout": ref.get("视觉骨架") or ref.get("layout_tag"),
                    "score": ref.get("_score") or ref.get("rank_score"),
                    "source": "already_bound_or_alternate",
                })
        terms.extend(chapter.get("claims_to_make") or [])
        terms.extend(chapter.get("claims_to_setup_for_later") or [])
        terms.extend(chapter.get("purpose") or [])
        if isinstance(chapter.get("purpose"), str):
            terms.append(chapter.get("purpose"))

        # Local repair must see the sections selected by IDEA. Keyword cascade
        # can miss concrete work pages when the query is abstract ("系统层",
        # "范式演进"), while material_section_hints already names the real deck
        # slices Claude should choose from.
        direct_briefs = oc.load_slide_briefs_for_chapter(
            material_sections, max_slides_per_section=40) if material_sections else []
        term_blob = " ".join(str(t) for t in terms if t)
        import re as _re_rebind
        proper_terms = [
            m for m in _re_rebind.findall(r"[A-Z][A-Za-z0-9+\-]{2,}", term_blob)
            if m.upper() not in {"GPU", "CPU", "FPGA", "ASIC", "LLM", "KV", "SM", "PD", "AI"}
        ]

        def _direct_score(b: dict) -> float:
            blob = " ".join([
                str(b.get("deck_title") or ""),
                str(b.get("section_id") or ""),
                str(b.get("section_role") or ""),
                str(b.get("页面角色") or ""),
                str(b.get("页在section中的作用") or ""),
                str(b.get("标题") or ""),
                str(b.get("核心论断") or ""),
                str(b.get("本页讲什么") or ""),
                " ".join(str(x) for x in (b.get("关键文字") or [])),
                " ".join(str(x) for x in (b.get("适合复用场景") or [])),
            ]).lower()
            score = float(b.get("_score") or 0)
            for term in [str(t).strip() for t in terms if str(t).strip()][:80]:
                low = term.lower()
                if len(low) >= 2 and low in blob:
                    score += 1.0
            for term in proper_terms:
                if term.lower() in blob:
                    score += 4.0
            return score

        for b in sorted(direct_briefs, key=_direct_score, reverse=True)[:36]:
            _add_candidate_from_brief(
                b, source="idea_material_section_hint", score=round(_direct_score(b), 2))

        cascade = oc.cascade_search_for_gap(
            keywords=[t for t in terms if t][:18],
            layer=ch_layer if ch_layer != "other" else None,
            role_hint=chapter.get("section_role"),
            exclude_slide_ids=None,
            max_decks=6,
            max_sections=8,
            max_slides=18,
        )
        for b in (cascade.get("slides") or [])[:18]:
            sid = b.get("slide_id")
            if sid in seen_out:
                continue
            _add_candidate_from_brief(b, source="cascade", score=b.get("_score"))

        # Final local fallback: scan the global slide index for explicit work /
        # method names already present in the target chapter. This catches cases
        # where the IDEA section hint was too narrow after page deletions.
        global_briefs = oc.load_global_slide_index()
        global_terms = [t for t in proper_terms if t]
        for extra in ("TB-STC", "SpecDiff", "SpecEE", "FlightVGM", "Endor"):
            if extra.lower() in term_blob.lower() and extra not in global_terms:
                global_terms.append(extra)

        def _global_score(b: dict) -> float:
            blob = " ".join([
                str(b.get("deck_title") or ""),
                str(b.get("section_id") or ""),
                str(b.get("section_role") or ""),
                str(b.get("页面角色") or ""),
                str(b.get("页在section中的作用") or ""),
                str(b.get("标题") or ""),
                str(b.get("核心论断") or ""),
                str(b.get("本页讲什么") or ""),
                " ".join(str(x) for x in (b.get("关键文字") or [])),
                " ".join(str(x) for x in (b.get("适合复用场景") or [])),
            ]).lower()
            score = float(b.get("_score") or 0.0)
            hits = 0
            for term in global_terms[:20]:
                if term.lower() in blob:
                    hits += 1
                    score += 10.0
            if ch_layer != "other" and str(b.get("inferred_layer") or "").lower() == ch_layer:
                score += 3.0
            return score if hits else 0.0

        for b in sorted(global_briefs, key=_global_score, reverse=True)[:24]:
            score = _global_score(b)
            if score <= 0:
                continue
            _add_candidate_from_brief(b, source="global_keyword_fallback", score=round(score, 2))
        return out

    def _structural_ref(role: str) -> dict | None:
        briefs = oc.load_structural_slide_briefs_for_role(role, max_keep=8)
        if not briefs:
            return None
        b = briefs[0]
        return {
            "deck_id": b.get("deck_id"),
            "slide_id": b.get("slide_id"),
            "section_id": b.get("section_id"),
            "deck_title": b.get("deck_title"),
            "section_role": b.get("section_role"),
            "rank_score": b.get("_score") or b.get("score"),
            "_tier": 2,
            "match_reasons": [
                f"driver selected real structural source for {role}",
                str(b.get("标题") or "")[:120],
            ],
        }

    def _make_structural_slide(*,
                               role: str,
                               chapter_index: int,
                               title: str,
                               claim: str,
                               ref: dict | None,
                               current_chapter_index: int | None = None) -> dict:
        return {
            "slide_index": 0,
            "chapter_index": chapter_index,
            "section_index": chapter_index,
            "target_role": role,
            "target_title": title,
            "target_claim": claim,
            "page_purpose": claim,
            "key_points": [],
            "anchor_terms": [],
            "archetype": ["chapter_navigation_reuses_toc_with_highlight_dimming"]
            if role in {"agenda", "section_divider"}
            else ["cover_layout_centered_title_with_speaker_signature"],
            "archetype_placement": (
                "section_open" if role in {"cover", "section_divider"}
                else "chapter_transition"
            ),
            "source_resource_ids": [ref] if ref else [],
            "source_carrier_resource_kind": "carrier_bound",
            "kind": "carrier_bound",
            "gap_status": "needs_text_recolor" if role in {"agenda", "section_divider"} else "needs_style_unification",
            "same_source_intent": {
                "allowed": role in {"agenda", "section_divider"},
                "reason": "agenda and section divider pages intentionally byte-clone one directory template",
            },
            "structural_page": True,
            "current_chapter_index": current_chapter_index,
        }

    def _enforce_outline_structural_pages(outline_doc: dict, *, phase: str = "final_check") -> dict:
        """Ensure required source-backed structural pages without replacing main-path pages."""
        if not isinstance(outline_doc, dict):
            return outline_doc
        raw_slides = [
            dict(s) for s in (outline_doc.get("slides") or [])
            if isinstance(s, dict)
        ]
        if not raw_slides:
            return outline_doc

        chapter_titles: dict[int, str] = {}
        for ch in chapter_plan:
            if not isinstance(ch, dict):
                continue
            try:
                ci = int(ch.get("section_index"))
            except Exception:
                continue
            if ci <= 0:
                continue
            chapter_titles[ci] = str(ch.get("chapter") or ch.get("title") or f"Chapter {ci}")
        for s in raw_slides:
            try:
                ci = int(s.get("chapter_index") or s.get("section_index") or 0)
            except Exception:
                continue
            if ci > 0 and ci not in chapter_titles:
                chapter_titles[ci] = str(s.get("target_title") or f"Chapter {ci}")[:80]

        ordered_chapters = []
        for ch in chapter_plan:
            if not isinstance(ch, dict):
                continue
            try:
                ci = int(ch.get("section_index") or 0)
            except Exception:
                continue
            if ci > 0:
                ordered_chapters.append(ci)
        if not ordered_chapters:
            ordered_chapters = sorted({
                int(s.get("chapter_index") or s.get("section_index") or 0)
                for s in raw_slides
                if int(s.get("chapter_index") or s.get("section_index") or 0) > 0
            })
        if not ordered_chapters:
            return _normalize_outline_chapter_links(outline_doc, chapter_plan)

        cover_ref = _structural_ref("cover")
        agenda_ref = _structural_ref("agenda") or _structural_ref("section_divider")
        if not cover_ref or not agenda_ref:
            print("[OUTLINE] structural-page check skipped: missing structural source pool",
                  flush=True)
            return _normalize_outline_chapter_links(outline_doc, chapter_plan)

        deck_title = (
            ((idea.get("identity") or {}).get("title"))
            or ((idea.get("identity") or {}).get("topic"))
            or ((idea.get("deck_identity") or {}).get("title"))
            or ((intake.get("structured_brief") or {}).get("topic"))
            or "大模型软硬件协同：课题组研究脉络与代表性成果"
        )
        agenda_items = [chapter_titles.get(ci, f"Chapter {ci}") for ci in ordered_chapters]

        def _role(slide: dict) -> str:
            return str(slide.get("target_role") or "").lower()

        def _refs(slide: dict) -> list:
            refs = slide.get("source_resource_ids") or []
            return refs if isinstance(refs, list) else []

        first_chapter_index = ordered_chapters[0] if ordered_chapters else 1

        def _decorate_structural(slide: dict, role: str, *, current_ci: int | None = None) -> dict:
            row = dict(slide)
            row["target_role"] = role
            row["structural_page"] = True
            row["source_carrier_resource_kind"] = row.get("source_carrier_resource_kind") or row.get("kind") or "carrier_bound"
            row["kind"] = row.get("kind") or "carrier_bound"
            if role in {"cover", "section_divider"}:
                row["archetype_placement"] = "section_open"
            elif role == "agenda":
                row["archetype_placement"] = "chapter_transition"
            if role in {"agenda", "section_divider"}:
                row["same_source_intent"] = {
                    "allowed": True,
                    "reason": "agenda and section divider pages intentionally byte-clone one directory template",
                }
                row["gap_status"] = row.get("gap_status") or "needs_text_recolor"
                row["source_resource_ids"] = [agenda_ref]
                row["archetype"] = row.get("archetype") or ["chapter_navigation_reuses_toc_with_highlight_dimming"]
                row["current_chapter_index"] = current_ci
            elif role == "cover" and not _refs(row):
                row["source_resource_ids"] = [cover_ref]
            if role in {"cover", "agenda"}:
                row["deck_structural_role"] = role
                row["chapter_index"] = first_chapter_index
                row["section_index"] = first_chapter_index
            return row

        leading_cover = raw_slides[0] if raw_slides and _role(raw_slides[0]) == "cover" else None
        leading_agenda = raw_slides[1] if len(raw_slides) > 1 and _role(raw_slides[1]) in {"agenda", "toc"} else None
        fallback_inserted: list[str] = []
        materialized_in_outline: list[str] = []

        if leading_cover:
            cover_slide = _decorate_structural(leading_cover, "cover")
        else:
            cover_slide = _make_structural_slide(
                role="cover",
                chapter_index=first_chapter_index,
                title=str(deck_title)[:120],
                claim="封面页: 明确报告主题、汇报对象与课题组视角",
                ref=cover_ref,
            )
            cover_slide["deck_structural_role"] = "cover"
            if phase == "outline_main_path":
                materialized_in_outline.append("cover")
            else:
                fallback_inserted.append("cover")

        if leading_agenda:
            agenda_slide = _decorate_structural(leading_agenda, "agenda")
        else:
            agenda_slide = _make_structural_slide(
                role="agenda",
                chapter_index=first_chapter_index,
                title="汇报目录",
                claim="总目录页: " + " / ".join(agenda_items)[:220],
                ref=agenda_ref,
            )
            agenda_slide["deck_structural_role"] = "agenda"
            if phase == "outline_main_path":
                materialized_in_outline.append("agenda")
            else:
                fallback_inserted.append("agenda")

        body_slides = []
        for idx, slide in enumerate(raw_slides):
            if idx == 0 and leading_cover:
                continue
            if idx == 1 and leading_agenda:
                continue
            # If a model accidentally placed a second cover/agenda later, keep it
            # out of the content flow. The formal cover/agenda are the first two pages.
            if _role(slide) in {"cover", "agenda", "toc"}:
                continue
            body_slides.append(dict(slide))

        new_slides: list[dict] = [cover_slide, agenda_slide]
        missing_dividers: list[int] = []
        for ci in ordered_chapters:
            ch_body = []
            for s in body_slides:
                try:
                    sci = int(s.get("chapter_index") or s.get("section_index") or 0)
                except Exception:
                    continue
                if sci == ci:
                    ch_body.append(dict(s))
            ch_body.sort(key=lambda s: int(s.get("slide_index") or s.get("slide_index_in_chapter") or 0))
            if ch_body and _role(ch_body[0]) in {"section_divider", "chapter_divider"}:
                divider = _decorate_structural(ch_body[0], "section_divider", current_ci=ci)
                divider["chapter_index"] = ci
                divider["section_index"] = ci
                new_slides.append(divider)
                new_slides.extend(ch_body[1:])
            else:
                missing_dividers.append(ci)
                fallback_inserted.append(f"section_divider:{ci}")
                new_slides.append(_make_structural_slide(
                    role="section_divider",
                    chapter_index=ci,
                    title=chapter_titles.get(ci, f"Chapter {ci}")[:120],
                    claim=(
                        f"分目录页: 当前章节为第 {ci} 章, 后续进入 "
                        f"{chapter_titles.get(ci, f'Chapter {ci}')}"
                    ),
                    ref=agenda_ref,
                    current_chapter_index=ci,
                ))
                new_slides.extend(ch_body)

        out = dict(outline_doc)
        out["slides"] = new_slides
        out = _normalize_outline_chapter_links(out, chapter_plan)
        out.setdefault("post_passes", [])
        out["post_passes"].append({
            "name": ("structural_pages_main_path_assembly"
                     if phase == "outline_main_path"
                     else "structural_pages_contract_check"),
            "source": "logic_story.major_chapter_navigation_required",
            "main_path_complete": not fallback_inserted,
            "materialized_in_outline": materialized_in_outline,
            "fallback_inserted": fallback_inserted,
            "section_divider_chapters": ordered_chapters,
            "missing_section_divider_chapters": missing_dividers,
            "agenda_source_slide_id": agenda_ref.get("slide_id"),
            "cover_source_slide_id": cover_ref.get("slide_id"),
        })
        if fallback_inserted:
            print(f"[OUTLINE] structural-page fallback inserted {fallback_inserted}", flush=True)
        elif materialized_in_outline:
            print(f"[OUTLINE] structural-page main-path materialized {materialized_in_outline}; "
                  f"{len(ordered_chapters)} section dividers present", flush=True)
        else:
            print(f"[OUTLINE] structural-page main-path check OK: cover + agenda + "
                  f"{len(ordered_chapters)} section dividers present", flush=True)
        return out

    def _apply_no_source_local_fix(current_outline: dict,
                                   issues: list[dict],
                                   *,
                                   reason: str) -> tuple[dict, list[dict]]:
        """Repair only no-source slides with small per-chapter Claude calls.

        The global outline_fix_from_review prompt can exceed a 900s Claude call.
        This fallback sends only the affected chapter plus real material
        candidates. The model must delete unsupported slides or rebind them to
        supplied candidates; empty source_resource_ids remain blocked by the
        final fail-fast gate.
        """
        missing = _outline_slides_without_source(current_outline)
        if not missing:
            return current_outline, []
        missing_chapters = sorted({
            int(m["chapter_index"]) for m in missing
            if m.get("chapter_index") is not None
        })
        if not missing_chapters:
            return current_outline, []
        by_issue_ch: dict[int, list[dict]] = {}
        for iss in issues:
            if not isinstance(iss, dict):
                continue
            ci = iss.get("target_chapter_index")
            try:
                ci = int(ci)
            except (TypeError, ValueError):
                continue
            by_issue_ch.setdefault(ci, []).append(iss)

        patched = dict(current_outline)
        patched["slides"] = [dict(s) for s in (current_outline.get("slides") or [])
                             if isinstance(s, dict)]
        fix_log: list[dict] = []
        for ci in missing_chapters:
            chapter = next((c for c in chapter_plan
                            if isinstance(c, dict) and c.get("section_index") == ci), {})
            patched = _normalize_outline_chapter_links(patched, chapter_plan)
            current_missing = _outline_slides_without_source(patched)
            no_source_indices = {
                int(m.get("slide_index")) for m in current_missing
                if m.get("chapter_index") == ci and m.get("slide_index") is not None
            }
            if not no_source_indices:
                continue
            chapter_slides = [s for s in patched.get("slides", [])
                              if s.get("chapter_index") == ci]
            if not chapter_slides:
                continue
            navigation_deletes = {
                int(s.get("slide_index"))
                for s in chapter_slides
                if s.get("slide_index") is not None
                and int(s.get("slide_index")) in no_source_indices
                and _is_navigation_target_slide(s)
            }
            if navigation_deletes:
                patched["slides"] = [
                    s for s in patched.get("slides", [])
                    if int(s.get("slide_index") or -1) not in navigation_deletes
                ]
                patched = _normalize_outline_chapter_links(patched, chapter_plan)
                fix_log.append({
                    "chapter_index": ci,
                    "ok": True,
                    "action": "delete_navigation_no_source_slides",
                    "deleted_slide_indices": sorted(navigation_deletes),
                    "reason": "content slide was written as agenda/navigation; real structural pages are inserted by driver post-pass",
                })
                print(f"[OUTLINE] local no-source fix ch{ci}: deleted navigation-only "
                      f"no-source slides {sorted(navigation_deletes)}", flush=True)
                chapter_slides = [s for s in patched.get("slides", [])
                                  if s.get("chapter_index") == ci]
                current_missing = _outline_slides_without_source(patched)
                no_source_indices = {
                    int(m.get("slide_index")) for m in current_missing
                    if m.get("chapter_index") == ci and m.get("slide_index") is not None
                }
                if not no_source_indices:
                    continue
            candidates = _collect_chapter_rebind_candidates(chapter, patched.get("slides", []))
            candidates = sorted(
                candidates,
                key=lambda c: float(c.get("score") or 0.0),
                reverse=True,
            )[:72 if str(chapter.get("section_role") or "").lower() in {"outlook", "discussion"} else 48]
            allowed_ids = {
                c.get("slide_id") for c in candidates
                if c.get("slide_id") and c.get("source") in {
                    "cascade", "idea_material_section_hint", "global_keyword_fallback",
                }
            }
            allowed_ids.update({
                c.get("slide_id") for c in candidates
                if c.get("slide_id") and c.get("source") == "already_bound_or_alternate"
            })

            def _candidate_score_for_batch(c: dict, target_batch: list[dict]) -> float:
                blob = " ".join([
                    str(c.get("deck_title") or ""),
                    str(c.get("section_id") or ""),
                    str(c.get("section_role") or ""),
                    str(c.get("page_role") or ""),
                    str(c.get("role_in_section") or ""),
                    str(c.get("title") or ""),
                    str(c.get("claim") or ""),
                    str(c.get("what") or ""),
                    " ".join(str(x) for x in (c.get("suitable_for") or [])),
                ]).lower()
                import re as _re_batch
                target_text = " ".join(
                    " ".join([
                        str(t.get("target_title") or ""),
                        str(t.get("target_claim") or ""),
                        " ".join(str(x) for x in (t.get("key_points") or [])),
                        " ".join(str(x) for x in (t.get("anchor_terms") or [])),
                    ])
                    for t in target_batch
                    if isinstance(t, dict)
                )
                score = float(c.get("score") or 0.0)
                for proper in _re_batch.findall(r"[A-Z][A-Za-z0-9+\-]{2,}", target_text):
                    if proper.upper() not in {"GPU", "CPU", "FPGA", "ASIC", "LLM", "KV", "SM", "PD", "AI"} \
                            and proper.lower() in blob:
                        score += 8.0
                for term in _re_batch.split(r"[\s,，。:：·/()（）\[\]\-]+", target_text):
                    low = term.lower().strip()
                    if len(low) >= 3 and low in blob:
                        score += 1.0
                return score

            chapter_by_idx = {
                int(s.get("slide_index")): s
                for s in chapter_slides
                if isinstance(s, dict) and s.get("slide_index") is not None
            }
            pending_indices = sorted(no_source_indices)
            deleted_indices: set[int] = set()
            patched_by_index = {
                int(s.get("slide_index")): dict(s)
                for s in patched.get("slides", [])
                if isinstance(s, dict) and s.get("slide_index") is not None
            }
            batch_logs: list[dict] = []
            any_batch_applied = False

            for batch_start in range(0, len(pending_indices), 2):
                batch_indices = pending_indices[batch_start:batch_start + 2]
                target_batch = [
                    patched_by_index.get(i) or chapter_by_idx.get(i)
                    for i in batch_indices
                    if (patched_by_index.get(i) or chapter_by_idx.get(i))
                ]
                if not target_batch:
                    continue
                focused_candidates = sorted(
                    candidates,
                    key=lambda c: _candidate_score_for_batch(c, target_batch),
                    reverse=True,
                )[:24]
                cand_by_id = {
                    c.get("slide_id"): c
                    for c in focused_candidates
                    if c.get("slide_id")
                }
                payload = {
                    "repair_reason": reason,
                    "hard_requirement": (
                        "For each target slide, choose exactly one action: "
                        "bind_to_source or delete_slide. Bind only when a candidate "
                        "truly supports the target object/scope. When the target is "
                        "an outlook/discussion/optional bridge page and no candidate "
                        "supports the broad wording, prefer binding a candidate that "
                        "supports the chapter purpose and revise the title/claim down "
                        "to the source page's real meaning. Delete only if all "
                        "candidates are wrong-scope, navigation-only, or would cause "
                        "duplicate/fictional content. Never invent a source."
                    ),
                    "chapter": {
                        "section_index": chapter.get("section_index"),
                        "chapter": chapter.get("chapter"),
                        "section_role": chapter.get("section_role"),
                        "claims_to_make": chapter.get("claims_to_make") or [],
                    },
                    "chapter_context_slides": [
                        {
                            "slide_index": s.get("slide_index"),
                            "target_title": s.get("target_title"),
                            "target_claim": s.get("target_claim"),
                            "has_source": bool(s.get("source_resource_ids")),
                            "source_slide_id": (
                                (s.get("source_resource_ids") or [{}])[0].get("slide_id")
                                if isinstance((s.get("source_resource_ids") or [{}])[0], dict)
                                else None
                            ),
                        }
                        for s in chapter_slides
                    ],
                    "target_no_source_slides": [
                        {
                            "slide_index": s.get("slide_index"),
                            "target_role": s.get("target_role"),
                            "target_title": s.get("target_title"),
                            "target_claim": s.get("target_claim"),
                            "archetype_placement": s.get("archetype_placement"),
                            "key_points": s.get("key_points") or [],
                            "anchor_terms": s.get("anchor_terms") or [],
                            "gap_status": s.get("gap_status"),
                            "alternates": s.get("alternates") or [],
                            "pick_rationale": s.get("_pick_rationale") or s.get("_gap_reason"),
                        }
                        for s in target_batch
                    ],
                    "candidate_material_slides": focused_candidates,
                }
                prompt = (
                    "Repair this SMALL batch of no-source outline slides. "
                    "Output strict JSON only with shape "
                    "{\"actions\":[{\"slide_index\":1,\"action\":\"bind_to_source|delete_slide\","
                    "\"source_slide_id\":\"...\",\"reason\":\"...\","
                    "\"revised_target_title\":\"optional\",\"revised_target_claim\":\"optional\"}],"
                    "\"repair_log\":[...]}. "
                    "Every target slide in target_no_source_slides must have one action. "
                    "Use source_slide_id only from candidate_material_slides. "
                    "If no candidate truly matches the target object/scope, delete the slide.\n\n"
                    "INPUT:\n" + json.dumps(payload, ensure_ascii=False)
                )
                out = claude_cli.call_claude_json(
                    prompt,
                    skill=["skills/outline_gen/outline_fix_from_review.md"],
                    timeout=240,
                )
                if not (out.get("ok") and isinstance(out.get("data"), dict)):
                    print(f"[OUTLINE] local no-source fix ch{ci} batch {batch_indices} failed: "
                          f"{(out.get('error') or '')[:160]}", flush=True)
                    batch_logs.append({
                        "batch_indices": batch_indices,
                        "ok": False,
                        "error": (out.get("error") or "")[:300],
                    })
                    continue
                actions = out["data"].get("actions") or []
                if not isinstance(actions, list):
                    actions = []
                batch_ok = False
                for act in actions:
                    if not isinstance(act, dict):
                        continue
                    try:
                        si = int(act.get("slide_index"))
                    except Exception:
                        continue
                    if si not in batch_indices:
                        continue
                    action = str(act.get("action") or "").lower()
                    if action == "delete_slide":
                        deleted_indices.add(si)
                        batch_ok = True
                        continue
                    if action != "bind_to_source":
                        continue
                    sid = act.get("source_slide_id")
                    cand = cand_by_id.get(sid)
                    if not sid or sid not in allowed_ids or not cand:
                        continue
                    slide = patched_by_index.get(si)
                    if not slide:
                        continue
                    slide["source_resource_ids"] = [{
                        "deck_id": cand.get("deck_id"),
                        "slide_id": sid,
                        "section_id": cand.get("section_id"),
                        "deck_title": cand.get("deck_title"),
                        "section_role": cand.get("section_role"),
                        "rank_score": cand.get("score"),
                        "_tier": 3,
                        "match_reasons": [
                            "local no-source repair selected this real material slide",
                            str(act.get("reason") or "")[:180],
                        ],
                    }]
                    slide["source_carrier_resource_kind"] = "carrier_bound"
                    slide["kind"] = "carrier_bound"
                    slide["gap_status"] = slide.get("gap_status") if slide.get("gap_status") not in {"no_match", "not_applicable"} else "needs_style_unification"
                    if act.get("revised_target_title"):
                        slide["target_title"] = str(act.get("revised_target_title"))[:160]
                    if act.get("revised_target_claim"):
                        slide["target_claim"] = str(act.get("revised_target_claim"))[:260]
                    slide["_local_no_source_repair"] = {
                        "action": "bind_to_source",
                        "source_slide_id": sid,
                        "reason": str(act.get("reason") or "")[:300],
                    }
                    patched_by_index[si] = slide
                    batch_ok = True
                batch_logs.append({
                    "batch_indices": batch_indices,
                    "ok": batch_ok,
                    "actions": actions,
                    "repair_log": out["data"].get("repair_log") or [],
                })
                any_batch_applied = any_batch_applied or batch_ok

            if deleted_indices or any_batch_applied:
                patched["slides"] = [
                    s for s in patched_by_index.values()
                    if int(s.get("slide_index") or -1) not in deleted_indices
                ]
                patched["slides"].sort(key=lambda s: int(s.get("slide_index") or 0))
                patched = _normalize_outline_chapter_links(patched, chapter_plan)
                fix_log.append({
                    "chapter_index": ci,
                    "ok": True,
                    "action": "small_batch_no_source_repair",
                    "deleted_slide_indices": sorted(deleted_indices),
                    "batch_logs": batch_logs,
                })
                print(f"[OUTLINE] local no-source fix ch{ci} small-batch OK "
                      f"(deleted={sorted(deleted_indices)}, batches={len(batch_logs)})",
                      flush=True)
            else:
                fix_log.append({
                    "chapter_index": ci,
                    "ok": False,
                    "action": "blocked_without_deleting_no_source_slides",
                    "no_source_slide_indices": sorted(no_source_indices),
                    "batch_logs": batch_logs,
                })
        if fix_log:
            patched.setdefault("referenced_review_issues", [])
            patched["referenced_review_issues"].extend([
                {
                    "source": "driver",
                    "category": "no_supporting_material_local_repair",
                    "severity": "critical",
                    "location": f"chapter[{x.get('chapter_index')}]",
                    "action_taken": "local per-chapter repair attempted",
                    "status": "applied" if x.get("ok") else "skipped (local repair failed)",
                    "detail": x,
                }
                for x in fix_log
            ])
            patched["fix_round"] = int(patched.get("fix_round") or 0) + 1
        return patched, fix_log

    def _write_outline_artifacts(current_outline: dict,
                                 *,
                                 review_log_in: list[dict],
                                 final_review_in: dict | None,
                                 stage1_errors_in: list[dict],
                                 narrative_warnings_in: list[str],
                                 source_label: str,
                                 enforce_structural_pages: bool = True) -> dict:
        current_outline.setdefault("sweep_stats", {
            "bound_content": 0, "bound_visual_axis": 0, "hard_removed": 0,
            "adj_dedup_swapped": 0, "adj_dedup_removed": 0,
            "note": "v31: Plan-A sweep + hard-prune removed; 源头对齐直接得净 outline",
        })
        current_outline.setdefault("hard_removed_slides", [])
        current_outline.setdefault("no_material_pages", [])
        if enforce_structural_pages:
            current_outline = _enforce_outline_structural_pages(current_outline)
        else:
            current_outline = _normalize_outline_chapter_links(current_outline, chapter_plan)
        current_outline = _normalize_outline_chapter_links(current_outline, chapter_plan)
        current_outline = _mark_parallel_framework_source_reuse(current_outline, idea)
        current_outline["generated_at"] = now()
        current_outline["source"] = source_label

        md_content_local = ""
        try:
            summary_prompt = (
                "Render outline.md from the JSON below. Your ENTIRE response IS the "
                "markdown file content. First character MUST be `#`. No preamble, no "
                "code fence.\n\nINPUT:\n"
                + json.dumps({"outline": current_outline}, ensure_ascii=False)
            )
            sum_res = claude_cli.call_claude_text(
                summary_prompt,
                skill=["skills/outline_gen/outline_human_summary.md"],
                timeout=600,
            )
            if sum_res.get("ok"):
                md = (sum_res.get("text") or "").strip()
                if md.startswith("```markdown"):
                    md = md.split("```markdown", 1)[1].rstrip("`").strip()
                elif md.startswith("```"):
                    md = md.strip("`").strip()
                md_content_local = md
        except Exception as exc:
            print(f"[OUTLINE] human_summary failed: {exc}", flush=True)

        write_json(pdir / "outline.json", current_outline)
        _synthesize_slide_matches_from_outline(pdir, current_outline)
        if md_content_local:
            (pdir / "outline.md").write_text(md_content_local, encoding="utf-8")
        if review_log_in:
            write_json(pdir / "outline-review.json", {
                "schema_version": "1.0",
                "rounds": review_log_in,
                "final_ok": (final_review_in or {}).get("ok") if final_review_in else False,
            })
        _write_stage_status(
            pdir,
            "outline-user-status.json",
            auto_approved=True,
            slide_count=len(current_outline.get("slides", [])),
            chapter_count=len(current_outline.get("chapter_to_slide_map", {})),
            codex_review_rounds=len(review_log_in),
            codex_final_ok=(final_review_in or {}).get("ok") if final_review_in else None,
            stage1_errors_count=len(stage1_errors_in),
            narrative_warnings_count=len(narrative_warnings_in),
            user_concern_count=len(current_outline.get("user_concern_history", [])),
            no_material_page_count=len(current_outline.get("no_material_pages") or []),
            no_material_page_indices=[p.get("slide_index")
                                      for p in (current_outline.get("no_material_pages") or [])],
            awaiting_human_review=False,
            human_feedback_round=0,
        )
        return {
            "ok": True,
            "stage": "OUTLINE_GENERATION",
            "outline": str(pdir / "outline.json"),
            "outline_md": str(pdir / "outline.md") if md_content_local else None,
            "stubs": str(pdir / "outline-chapter-stubs.json"),
            "review": str(pdir / "outline-review.json") if review_log_in else None,
            "source": current_outline.get("source"),
            "slide_count": current_outline.get("slide_count"),
            "user_outline_applied": False,
            "narrative_warnings_count": len(narrative_warnings_in),
            "stage1_errors_count": len(stage1_errors_in),
            "codex_review_rounds": len(review_log_in),
            "codex_final_ok": (final_review_in or {}).get("ok") if final_review_in else None,
        }

    idea_fingerprint = {
        "idea_generated_at": idea.get("generated_at"),
        "idea_schema_version": idea.get("schema_version"),
        "idea_source": idea.get("source"),
    }
    _use_unified_outline = _os.environ.get(
        "OUTLINE_UNIFIED_CHAPTER_CLAUDE", "1").lower() not in {"0", "false", "no"}
    prior_diag = None if _use_unified_outline else read_json(
        pdir / "outline-no-source-diagnostics.json", None)
    if isinstance(prior_diag, dict) and isinstance(prior_diag.get("outline_draft"), dict):
        diag_matches_current_idea = (
            prior_diag.get("idea_generated_at") == idea_fingerprint["idea_generated_at"]
            and prior_diag.get("idea_schema_version") == idea_fingerprint["idea_schema_version"]
            and prior_diag.get("idea_source") == idea_fingerprint["idea_source"]
        )
        if not diag_matches_current_idea:
            print("[OUTLINE] ignoring stale outline-no-source-diagnostics.json "
                  "(idea fingerprint changed)", flush=True)
        prior_draft = prior_diag.get("outline_draft") or {}
        prior_missing = _outline_slides_without_source(prior_draft)
        if diag_matches_current_idea and prior_missing:
            print(f"[OUTLINE] resuming from outline-no-source-diagnostics.json: "
                  f"{len(prior_missing)} no-source slides", flush=True)
            prior_review_log = prior_diag.get("review_log") or []
            prior_issues = []
            if prior_review_log and isinstance(prior_review_log[-1], dict):
                prior_issues = prior_review_log[-1].get("issues") or []
            repaired, local_fix_log = _apply_no_source_local_fix(
                prior_draft,
                prior_issues,
                reason="resume from prior outline-no-source-diagnostics",
            )
            still_missing = _outline_slides_without_source(repaired)
            if still_missing:
                diag = {
                    "schema_version": "1.0",
                    "generated_at": now(),
                    "project_id": project_id,
                    **idea_fingerprint,
                    "error": "OUTLINE_GENERATION blocked because local no-source repair did not resolve all slides.",
                    "no_source_slides": still_missing,
                    "local_fix_log": local_fix_log,
                    "review_log": prior_review_log,
                    "outline_draft": repaired,
                }
                write_json(pdir / "outline-no-source-diagnostics.json", diag)
                return {
                    "ok": False,
                    "stage": "OUTLINE_GENERATION",
                    "outline_diagnostics": str(pdir / "outline-no-source-diagnostics.json"),
                    "error": f"local no-source repair left {len(still_missing)} slides without source_resource_ids",
                    "no_source_slides": still_missing[:20],
                }
            print(f"[OUTLINE] local no-source repair passed from diagnostics: "
                  f"{len(repaired.get('slides') or [])} slides all sourced", flush=True)
            return _write_outline_artifacts(
                repaired,
                review_log_in=prior_review_log,
                final_review_in=prior_review_log[-1] if prior_review_log else None,
                stage1_errors_in=[],
                narrative_warnings_in=repaired.get("narrative_warnings") or [],
                source_label="outline_diagnostics_local_repair",
            )

    # ============================================================
    # Stage 1: per-chapter generation (1a stub → 1b detail), parallel max 4
    # ============================================================
    t_stage1 = _time.time()
    # v6 S3: archetype_for_prompt is now built per-chapter inside _stage1a_chapter_stub
    # using role_filter to reduce from 204 → ~40-60 entries per chapter.
    # S4: meta invariant_principles from idea.selected_meta_pattern injected per chapter.
    _meta_invariants = []
    _selected_meta = (idea.get("selected_meta_pattern") or {}) if isinstance(idea.get("selected_meta_pattern"), dict) else {}
    if _selected_meta:
        _meta_invariants = _selected_meta.get("invariant_principles") or []

    def _stage1a_chapter_stub(chapter: dict) -> dict:
        ch_idx = chapter.get("section_index")
        role_filter = (chapter.get("section_role") or "").lower() or None
        _chapter_archetypes = oc.load_page_specific_archetypes(role_filter=role_filter) or archetypes
        archetype_for_prompt = [
            {"id": a.get("id"), "category": a.get("category"),
             "enforcement_level": a.get("enforcement_level"),
             "applicable_role": a.get("applicable_role") or [],
             "summary": (a.get("summary") or a.get("description") or "")[:120]}
            for a in _chapter_archetypes
        ]
        candidate_sections = _chapter_candidate_sections(chapter, max_sections=8)
        # v4.0 IDEA: rhythm_pattern_id 是单字符串 (而非 v3.2 的 section_rhythm_patterns plural list)
        rhythm_pattern_id = chapter.get("section_rhythm_pattern_id")
        # v3.2 backcompat: 老 idea-analysis.json 可能用 section_rhythm_patterns 数组
        if not rhythm_pattern_id:
            legacy_rp = (chapter.get("section_rhythm_patterns") or [{}])[0]
            rhythm_pattern_id = legacy_rp.get("pattern_id")
        rhythm_pattern = oc.load_rhythm_pattern_trimmed(rhythm_pattern_id, max_carriers=5) if rhythm_pattern_id else None
        narrative_slice = oc.slice_narrative_constraints_for_chapter(nc, ch_idx)
        # v4.0: candidate_section_slide_count_hint 改从 rhythm.carriers 反查
        # (而非 v3.2 的 chapter.candidate_carrier_sections)
        cand_slide_hint: dict[str, int] = {}
        if rhythm_pattern:
            for c in (rhythm_pattern.get("carriers") or [])[:5]:
                if isinstance(c, dict):
                    sid = c.get("section_id")
                    if sid:
                        cand_slide_hint[sid] = c.get("page_count") or c.get("slide_count")
        # backcompat: v3.2 idea-analysis 还有 candidate_carrier_sections (兜底)
        if not cand_slide_hint:
            for c in candidate_sections:
                cand_slide_hint[c.get("section_id")] = c.get("page_count")
        payload = {
            "chapter": chapter,
            "structural_page_contract": idea.get("structural_page_contract") or _default_structural_page_contract(),
            "library_candidate_sections": candidate_sections,
            "resource_library_contract": resource_library_contract,
            "selected_rhythm_pattern": rhythm_pattern or {},
            "page_specific_archetypes": archetype_for_prompt,
            "narrative_constraints_slice": narrative_slice,
            "candidate_section_slide_count_hint": cand_slide_hint,
        }
        # v24 修 G: 提前把库候选池摘要给 Stage 1a, 让它按库真实容量决定 stub 数量
        # (以前 tier1 只在 Stage 1b 才加载, Stage 1a 拍脑袋按 IDEA expected_pages).
        # 只做 summary (~500 chars), 不塞全 briefs — 避免 payload 爆炸.
        try:
            pool_briefs: list[dict] = []
            seen_pool_ids: set = set()
            if rhythm_pattern_id:
                for b in oc.load_slide_briefs_for_rhythm_pattern(rhythm_pattern_id, max_carriers=3):
                    sid = b.get("slide_id")
                    if sid and sid not in seen_pool_ids:
                        seen_pool_ids.add(sid)
                        pool_briefs.append(b)
            if candidate_sections:
                for b in oc.load_slide_briefs_for_chapter(candidate_sections):
                    sid = b.get("slide_id")
                    if sid and sid not in seen_pool_ids:
                        seen_pool_ids.add(sid)
                        pool_briefs.append(b)
            pool_briefs = oc.trim_slide_briefs_by_chapter_relevance(pool_briefs, chapter, max_keep=20)
            # Cluster by 页面角色 (opener/method_detail/result/closer/mixed) — 简单粗分
            from collections import defaultdict
            clusters: dict = defaultdict(list)
            for b in pool_briefs:
                role_in_sec = (b.get("页在section中的作用") or b.get("页面角色") or "other").lower()
                clusters[role_in_sec].append(b)
            cluster_summary = []
            for role_key, items in sorted(clusters.items(), key=lambda x: -len(x[1])):
                cluster_summary.append({
                    "role_in_section": role_key,
                    "n_slides": len(items),
                    "sample_titles": [(x.get("标题") or "")[:50] for x in items[:6]],
                    "sample_claims": [(x.get("核心论断") or "")[:60] for x in items[:5]],
                })
            payload["candidate_pool_summary"] = {
                "n_total": len(pool_briefs),
                "clusters_by_role": cluster_summary,
                "hint": (
                    f"库中本章候选池共 {len(pool_briefs)} 张, 按角色分组见 clusters_by_role. "
                    f"Stage 1a **应基于此判断 stub 数量与 subline 划分**: "
                    f"某类角色 n_slides ≤ 2 → 该主题 subline 只出 1-2 stub (勿硬凑); "
                    f"某类角色 n_slides = 0 → 这一 subline 库不支持, 应从章内删除 (不写对应 stub); "
                    f"n_total < IDEA expected_pages_indicative → 该章 stubs 数量应缩到 n_total 的 100%-120%."
                ),
            }
        except Exception as _e:
            payload["candidate_pool_summary"] = {"n_total": 0, "clusters_by_role": [], "hint": f"pool load failed: {_e}"}
        # v20 P2-W2 disabled: framework Pass 2 removed. dms is never set on chapters
        # under current single-pass mode. Left as dead code, no-op if not present.
        dms = chapter.get("_downstream_method_stubs")
        if dms:
            payload["downstream_method_stubs"] = dms
        pgid = chapter.get("parallel_group_id")
        if pgid:
            pg_contract = next(
                (c for c in (idea.get("parallel_group_contracts") or [])
                 if isinstance(c, dict) and str(c.get("parallel_group_id")) == str(pgid)),
                None,
            )
            siblings = []
            for other in (chapter_plan or []):
                if not isinstance(other, dict):
                    continue
                if other.get("parallel_group_id") != pgid:
                    continue
                if other.get("section_index") == chapter.get("section_index"):
                    continue
                siblings.append({
                    "section_index": other.get("section_index"),
                    "chapter": other.get("chapter"),
                    "purpose": other.get("purpose"),
                    "expected_pages_indicative": other.get("expected_pages_indicative"),
                    "claims_to_make": (other.get("claims_to_make") or [])[:3],
                })
            payload["parallel_group_context"] = {
                "group_id": pgid,
                "terminology": chapter.get("parallel_group_terminology") or {},
                "sibling_chapters": siblings,
                "contract": pg_contract or {},
            }
        # v4.4: detect redo mode + add hint
        is_redo = bool(chapter.get("_decomp_redo_round"))
        redo_hint = ""
        if is_redo:
            missing = chapter.get("_prior_missing_sublines") or []
            redo_hint = (
                f"\n**v4.4 REDO MODE — round {chapter.get('_decomp_redo_round')}**: "
                f"Codex 判定上一版 chapter_decomposition 中 sublines {missing} 资源库 missing. "
                "**禁止保留**这些 subline name 或同义 axis. 必须砍掉或换 axis (按 _codex_review_hints "
                "suggested_fix 中提示的资源库实际存在的方向). chapter_decomposition.rationale 必须 ≥40 字, "
                "明确说明哪些 subline 被砍/换 + 引用 codex hint. 整章 page_count 同步调整 (砍 subline → 减 stub).\n\n"
            )
        # v17 C.1b: skeleton review redo hint
        is_skel_redo = bool(chapter.get("_skeleton_redo_round"))
        if is_skel_redo:
            skel_hints = chapter.get("_skeleton_review_hints") or []
            redo_hint += (
                f"\n**v17 C.1b SKELETON REDO — round {chapter.get('_skeleton_redo_round')}**: "
                "Codex 判定骨架有问题. 修复要求见 _skeleton_review_hints 每条 issue 的 suggested_fix. "
                "常见问题:\n"
                "  - chapter_decomposition subline 重叠/不覆盖 axis → 重新分\n"
                "  - archetype 序列跟 rhythm_pattern 不对齐 → 按 rhythm.abstract_node_sequence 调 archetype\n"
                "  - stub 缺 framework recap / thesis callback 位 → 加对应 archetype 的 stub\n\n"
            )
        prompt = (
            f"Run OUTLINE Stage 1a (chapter_stub) for chapter {ch_idx}. "
            f"Decide N slides + role + archetype sequence + placement + page_purpose_hint. "
            f"archetype MUST be from page_specific_archetypes[].id.\n\n"
            + redo_hint +
            "**v35 stage contract**: IDEA provides chapter intent + material section hints only. "
            "This Stage 1a call is the first and only place that creates slide stubs. "
            "Use `library_candidate_sections`, `candidate_pool_summary`, "
            "`selected_rhythm_pattern`, and current rule/page_specific constraints to decide "
            "the stub sequence. Preserve IDEA intent when supported; shrink, reorder, or "
            "replace stubs when the material library does not support them. Do not invent "
            "unsupported sublines.\n\n"
            "**STRUCTURAL MAIN-PATH CONTRACT**: if chapter.requires_section_divider=true, "
            "stubs[0] MUST be target_role=section_divider with section_open placement. "
            "This is a formal source-backed OUTLINE page and will be bound by Stage 1b; "
            "do not leave it for post-processing. The first real content page starts after it. "
            "The divider counts in page_count but does not consume content material capacity.\n\n"
            "**PARALLEL GROUP CONTRACT**: if input.parallel_group_context.contract exists, "
            "obey it exactly. Use the same canonical_chapter_skeleton, comparable page_count, "
            "same framework_anchor slot, and same canonical_work_block_template as sibling "
            "chapters. Output `work_blocks[]` with work_name, template, and stub_indices. "
            "If material cannot support a full block, compress every block in this chapter "
            "to the same template rather than leaving one work without method/result.\n\n"
            "**v4.2 必填: chapter_decomposition**. 把本章按抽象 intent 分解为 2-4 条"
            "subline (method/discussion 章), 每条 subline 给 name + 2-5 个**抽象主题词**"
            "(`abstract_topics`, 不是具体工作名). e.g. 系统层 subline.abstract_topics = "
            '["调度", "服务框架"] / ["通信", "并行"] / ["KV cache", "算子"]. '
            "**不要写 vLLM/Splitwise/FlightLLM 等具体工作名** — driver 会用 abstract_topics "
            "去 material/decks-index.json 反查资源库**真实存在**的具体工作名 (e.g. FlashOverlap/"
            "semi-PD/SpecEE/TB-STC) 喂给 Stage 1b. cover/closing/agenda 章 sublines=[].\n\n"
            "**v4.0 提示**: chapter.claims_to_make 是 IDEA 的抽象意图. stub.page_purpose_hint "
            "用抽象语言保持与 IDEA 同层. abstract_topics 也保持抽象 — 真正的具体技术名只在 "
            "Stage 1b 读 source 后浮现到 slide.target_claim. "
            "claim_to_stub_map 按主旨/方向对齐. Strict JSON only.\n\n"
            "INPUT:\n" + json.dumps(payload, ensure_ascii=False)
        )
        for attempt in range(1, 4):
            # v18/v20 fix: slim-fallback for any attempt≥3 (not just redo).
            # v20 P2-W2 framework Pass 2 payload includes downstream_method_stubs
            # and can also exceed 600s.
            effective_prompt = prompt
            if attempt >= 3:
                mode_label = "redo" if is_redo else ("framework_pass2" if chapter.get("_downstream_method_stubs") else "normal")
                effective_prompt = prompt + (
                    "\n\n**SLIM FALLBACK MODE (final attempt after prior timeouts)**: "
                    "为压缩输出量, 只需产出核心字段: "
                    "chapter_index / page_count / stubs (每 stub 只需 slide_index_in_chapter / "
                    "target_role / archetype / archetype_placement / page_purpose_hint) / "
                    "chapter_decomposition (sublines: name + abstract_topics + rationale). "
                    "允许省略: rhythm_adherence / adherence_notes / claim_to_stub_map / "
                    "narrative_hook_placement / 其他 meta 字段. "
                    "务必快速产出骨架, 不要为了完整字段而超时."
                )
                print(f"[OUTLINE stage1a ch{ch_idx}] attempt 3 → SLIM FALLBACK ({mode_label})", flush=True)
            res = claude_cli.call_claude_json(
                effective_prompt, skill=["skills/outline_gen/outline_chapter_stub.md"], timeout=600)
            if res.get("ok") and isinstance(res.get("data"), dict):
                # Tolerant key remapping (Claude sometimes uses near-synonyms)
                d = dict(res["data"])
                if "chapter_index" not in d and "section_index" in d:
                    d["chapter_index"] = d.get("section_index")
                if "stubs" not in d and "slides" in d:
                    d["stubs"] = d.get("slides") or []
                if "page_count" not in d:
                    if "slide_count" in d:
                        d["page_count"] = d.get("slide_count")
                    elif isinstance(d.get("stubs"), list):
                        d["page_count"] = len(d["stubs"])
                # Normalize stub field names too
                norm_stubs = []
                for s in (d.get("stubs") or []):
                    if not isinstance(s, dict):
                        continue
                    ns = dict(s)
                    if "target_role" not in ns and "role" in ns:
                        ns["target_role"] = ns.get("role")
                    if "archetype_placement" not in ns and "placement" in ns:
                        ns["archetype_placement"] = ns.get("placement")
                    if isinstance(ns.get("archetype"), str):
                        ns["archetype"] = [ns["archetype"]]
                    ns["archetype"] = oc.normalize_page_specific_archetype_ids(
                        ns.get("archetype"), role_hint=ns.get("target_role") or chapter.get("section_role")
                    )
                    # v4.1: normalize belongs_to_subline_index
                    if "belongs_to_subline_index" not in ns and "subline_index" in ns:
                        ns["belongs_to_subline_index"] = ns.get("subline_index")
                    norm_stubs.append(ns)
                d["stubs"] = norm_stubs
                # v4.1: normalize chapter_decomposition shape
                cd = d.get("chapter_decomposition") or {}
                if isinstance(cd, dict):
                    sublines = cd.get("sublines") or []
                    norm_sublines = []
                    for sl in sublines:
                        if not isinstance(sl, dict):
                            continue
                        ns = dict(sl)
                        # v4.2: prefer abstract_topics. backcompat for "keywords" / "kw".
                        if "abstract_topics" not in ns:
                            ns["abstract_topics"] = (
                                ns.get("keywords") or ns.get("kw") or [])
                        if not isinstance(ns.get("abstract_topics"), list):
                            ns["abstract_topics"] = []
                        # Keep "keywords" as alias for backcompat downstream
                        ns["keywords"] = list(ns.get("abstract_topics") or [])
                        norm_sublines.append(ns)
                    cd["sublines"] = norm_sublines
                    d["chapter_decomposition"] = cd
                # Force chapter_index from caller (authoritative)
                d["chapter_index"] = ch_idx
                if chapter.get("requires_section_divider") is True:
                    stubs = d.get("stubs") if isinstance(d.get("stubs"), list) else []
                    first_role = (
                        str((stubs[0] or {}).get("target_role") or "").lower()
                        if stubs else ""
                    )
                    if first_role not in {"section_divider", "chapter_divider"}:
                        divider_stub = {
                            "slide_index_in_chapter": 1,
                            "target_role": "section_divider",
                            "archetype": ["chapter_navigation_reuses_toc_with_highlight_dimming"],
                            "archetype_placement": "section_open",
                            "page_purpose_hint": "分目录页: 高亮当前章",
                            "belongs_to_subline_index": None,
                            "_driver_inserted_structural_stub": True,
                        }
                        shifted = []
                        for idx, old in enumerate(stubs, start=2):
                            row = dict(old)
                            row["slide_index_in_chapter"] = idx
                            if row.get("archetype_placement") == "section_open":
                                row["archetype_placement"] = "section_middle"
                            shifted.append(row)
                        d["stubs"] = [divider_stub] + shifted
                        d["page_count"] = len(d["stubs"])
                        ptm = d.get("page_to_rhythm_node_map")
                        if isinstance(ptm, list):
                            d["page_to_rhythm_node_map"] = [None] + ptm
                        d.setdefault("driver_normalization", []).append({
                            "stage": "OUTLINE Stage 1a",
                            "reason": "Claude omitted required section_divider stub; inserted structural stub before Stage 1b",
                        })
                return {"chapter_index": ch_idx, "ok": True, "data": d}
            print(f"[OUTLINE stage1a ch{ch_idx}] attempt {attempt}/3 failed: "
                  f"{(res.get('error') or '')[:160]}", flush=True)
            if attempt < 3:
                _time.sleep(2 ** attempt)
        return {"chapter_index": ch_idx, "ok": False,
                "error": f"stage 1a failed all retries: {(res.get('error') or '')[:200]}"}

    def _stage1b_call_llm(payload: dict, ch_idx: int, mode: str,
                            skill_path: str = "skills/outline_gen/outline_slide_detail.md") -> dict:
        """Single LLM call for Stage 1b (mode = carrier_only | fill_gaps).
        Returns normalized {ok, data} or {ok: False, error}.
        """
        slide_count_target = len(payload.get("chapter_stubs") or [])
        if mode == "carrier_only":
            mode_hint = (
                "**v36 PASS-1 mode = carrier_only (claim-aligned, strict final binding)**:\n"
                "candidate_slide_briefs 含 tier1 (rhythm carriers ∪ IDEA material_section_hints 对应 material slides), "
                "已按 `_claim_alignment` (0-1, LLM 评估 source.核心论断 vs target 判断方向对齐度) 降序排好.\n"
                "per slide 只允许最终可进入 draft 的绑定:\n"
                "  - ok: top-1 `_claim_alignment ≥ 0.5` + layer/role/object-scope 对齐 → kind=carrier_bound\n"
                "  - needs_style_unification: source 主题/role 对齐, 但术语/标题/口径需后续统一 → kind=carrier_bound\n"
                "  - 找不到合格 source → kind=new + source_resource_ids=[]; driver 会 PASS-2 扩展/最终阻断\n"
                "**关键**: 不要看 keyword 重叠选 source — 必须用 _claim_alignment 字段为首要判据. "
                "结构页 opening/cover/agenda/section_divider/closing/references 也必须从库中真实绑定 source_resource_ids, 不能空着. "
                "内容页不得绑定 TOC/Contents/目录/导航/封面/致谢源页; 总领页不得绑定个人答辩/单篇论文总纲源.\n"
            )
        else:  # fill_gaps
            mode_hint = (
                "**v36 PASS-2 mode = fill_gaps (claim-aligned, strict final binding)**:\n"
                "你会收到 detail_pass1 (PASS-1 完成的全章 slides) + gap_slides_with_extended_candidates.\n"
                "extended_candidate_slide_briefs 已按 `_claim_alignment` 降序排好.\n"
                "**仅对 gap_slides 重选 source** (从 extended); 其他 ok 的 slide 必须保留 PASS-1 原值.\n"
                "若 top-1 _claim_alignment ≥ 0.5 且 layer/role/object-scope 对齐 → 选, kind=carrier_bound, gap_status=ok 或 needs_style_unification.\n"
                "若 0.3-0.5 或 role/object-scope 不合格 → 不要输出 matching_fallback; 继续找 alternate.\n"
                "都不合格 → kind=new + source_resource_ids=[]; driver 会阻断, 不允许靠下游凭空补.\n"
                "输出完整的 chapter slides (合并 gap 重选+PASS-1 ok 的页), chapter_realized 重新 aggregate.\n"
            )
        prompt = (
            f"Run OUTLINE Stage 1b for chapter {ch_idx}. "
            f"slide_count MUST = {slide_count_target}.\n\n"
            + mode_hint +
            "\n**v35 optimized-library contract**: `library_candidate_sections` and "
            "`candidate_slide_briefs` come from the current material library and from "
            "IDEA's stored deck→section hints. Prefer same-deck / same-section "
            "continuous reuse when it supports the claim. `resource_library_contract` "
            "defines ownership: material supplies cloneable sources; logic supplies "
            "rhythm only; rule supplies constraints. Do not invent sources or unsupported "
            "technical names. Structural pages (opening/cover/agenda/section_divider/closing/references) "
            "must also bind to real library source slides; use structural candidate pools even when "
            "the enclosing chapter role is method/framework/outlook. A section_divider target is "
            "never a content page.\n"
            "\n**v4.0 抽象→具体**: chapter.claims_to_make 抽象意图. 读 candidate slide briefs 把抽象 "
            "意图 realize 为具体技术名/工作名/方法名写进 slide.target_claim. "
            "chapter_realized 必填. **v28 gap 语义改**: gap_research_hint 已弃, 库无支撑就写能力性描述; "
            "若多来源风格不一致 (术语/标题/口径) → 填 style_unification_hint 供 SLIDE_REWRITE 统一, "
            "不允许给已 carrier_bound 的 slide 强加待补数据 hint. "
            "Strict JSON only.\n\n"
            "INPUT:\n" + json.dumps(payload, ensure_ascii=False)
        )
        for attempt in range(1, 4):
            # v17 fix: after 2 failed attempts (often timeout on motivation章 with
            # complex claim space), degrade to slim schema for the 3rd attempt so at
            # least the chapter has skeletal detail — downstream SLIDE_REWRITE / GAP
            # stages can enrich later. Better than losing the whole chapter.
            effective_prompt = prompt
            if attempt >= 3:
                effective_prompt = prompt + (
                    "\n\n**SLIM FALLBACK MODE (final attempt after prior timeouts)**: "
                    "为压缩输出量, 每 slide 只需输出核心 6 字段: "
                    "slide_index_in_chapter / target_role / target_title / target_claim / "
                    "source_resource_ids / gap_status. "
                    "以下字段允许为空数组或省略: key_points / needed_evidence / anchor_terms / "
                    "archetype / claim_status_link / subline_index / gap_research_hint. "
                    "chapter_realized 仅需 summary + realized_specifics (可为空), "
                    "coverage_status / subline_coverage 允许省略. "
                    "务必先出 8 个 slide 的骨架, 不要为了完整字段而超时."
                )
                print(f"[OUTLINE stage1b ch{ch_idx} {mode}] attempt 3 → SLIM FALLBACK", flush=True)
            res = claude_cli.call_claude_json(
                effective_prompt, skill=[skill_path], timeout=900)
            if res.get("ok") and isinstance(res.get("data"), dict):
                d = dict(res["data"])
                d["chapter_index"] = ch_idx
                if "slides" not in d or not isinstance(d.get("slides"), list):
                    for alt in ("stubs", "slide_details", "items"):
                        if isinstance(d.get(alt), list):
                            d["slides"] = d[alt]
                            break
                norm = []
                for s in (d.get("slides") or []):
                    if not isinstance(s, dict):
                        continue
                    ns = dict(s)
                    if "target_role" not in ns and "role" in ns:
                        ns["target_role"] = ns.get("role")
                    if "archetype_placement" not in ns and "placement" in ns:
                        ns["archetype_placement"] = ns.get("placement")
                    if isinstance(ns.get("archetype"), str):
                        ns["archetype"] = [ns["archetype"]]
                    norm.append(ns)
                d["slides"] = norm
                return {"ok": True, "data": d}
            print(f"[OUTLINE stage1b ch{ch_idx} {mode}] attempt {attempt}/3 failed: "
                  f"{(res.get('error') or '')[:160]}", flush=True)
            if attempt < 3:
                _time.sleep(2 ** attempt)
        return {"ok": False, "error": f"stage 1b {mode} failed: {(res.get('error') or '')[:200]}"}

    def _stage1b_slide_detail(chapter: dict, stub_data: dict) -> dict:
        """Two-pass Stage 1b (v4.2):
          PASS-1: carrier-only — feed tier1 (rhythm.carriers) only, LLM marks gap_status
          PASS-2: fill_gaps   — for gaps, run cascade (deck→section→slide) with subline keywords,
                                 only rewrite gap slides, others kept from PASS-1
        """
        ch_idx = chapter.get("section_index")
        rhythm_pattern_id = chapter.get("section_rhythm_pattern_id")
        if not rhythm_pattern_id:
            legacy_rp = (chapter.get("section_rhythm_patterns") or [{}])[0]
            rhythm_pattern_id = legacy_rp.get("pattern_id")
        decomp = stub_data.get("chapter_decomposition") or {}
        sublines = decomp.get("sublines") or []
        narrative_slice = oc.slice_narrative_constraints_for_chapter(nc, ch_idx)
        ch_layer = oc.infer_chapter_layer(chapter)
        ch_role = (chapter.get("section_role") or "").lower()
        candidate_sections = _chapter_candidate_sections(chapter, max_sections=10)

        def _slide_source_id_local(slide: dict) -> str | None:
            refs = slide.get("source_resource_ids") or []
            if not refs:
                return None
            first = refs[0]
            if isinstance(first, dict):
                return first.get("slide_id")
            if isinstance(first, str):
                return first
            return None

        def _mark_illegal_bindings_as_gap(detail: dict, *, label: str) -> dict:
            """Do not deterministically replace sources; only demote illegal
            model-selected bindings so PASS-2/final gate must resolve them."""
            slides_local = detail.get("slides") or []
            source_ids = [
                sid for sid in (_slide_source_id_local(s) for s in slides_local)
                if sid
            ]
            if not source_ids:
                return detail
            brief_by_id = {
                str(b.get("slide_id")): b
                for b in oc.load_slide_briefs_by_ids(source_ids)
                if isinstance(b, dict) and b.get("slide_id")
            }
            changed = []
            structural_ok_roles = {
                "cover", "agenda", "chapter_divider", "section_divider",
                "closing", "references",
            }
            content_roles = {
                "motivation", "background", "problem", "framework", "method",
                "comparison", "benchmark", "result", "experiment", "engineering",
                "discussion", "outlook", "content", "case_study",
            }

            def _txt(b: dict, *keys: str) -> str:
                parts = []
                for key in keys:
                    v = b.get(key)
                    if isinstance(v, list):
                        parts.extend(str(x) for x in v if x)
                    elif v:
                        parts.append(str(v))
                return " ".join(parts)

            def _nav(b: dict) -> bool:
                role = str(b.get("页面角色") or "").lower()
                text = _txt(b, "标题", "本页讲什么", "核心论断", "适合复用场景", "视觉骨架").lower()
                return (
                    role in {"toc_candidate", "cover_candidate", "ending_candidate", "references"}
                    or any(t in text for t in (
                        "toc", "contents", "agenda", "outline",
                        "目录", "议程", "提纲", "章节切换", "章节过渡",
                        "进度导航", "高亮当前", "当前章",
                    ))
                )

            def _personal(b: dict) -> bool:
                page_role = str(b.get("页面角色") or "").lower()
                deck_id = str(b.get("deck_id") or "")
                if page_role in {"cover_candidate", "toc_candidate", "ending_candidate"}:
                    return False
                if "通用模板" in deck_id or "模板" in str(b.get("deck_title") or ""):
                    return False
                text = _txt(b, "deck_id", "deck_title", "标题", "本页讲什么", "适合复用场景")
                return any(t in text for t in ("个人", "博士资格", "资格考试", "开题", "中期", "答辩", "论文分享", "学生"))

            def _overview(sl: dict) -> bool:
                role = (sl.get("target_role") or "").lower()
                text = " ".join([
                    str(sl.get("target_title") or ""),
                    str(sl.get("target_claim") or ""),
                    str(sl.get("archetype") or ""),
                ])
                return role in {"framework", "framework_recap"} or any(t in text for t in (
                    "总纲", "全局", "课题组", "三层协同", "主线", "总体",
                    "整体", "研究脉络", "recap", "收束", "范式", "三层坐标",
                ))

            def _narrow_framework_source(b: dict) -> bool:
                page_role = str(b.get("页面角色") or "").lower()
                if page_role in {"cover_candidate", "toc_candidate", "ending_candidate", "references"}:
                    return False
                role_in_section = str(b.get("页在section中的作用") or "").lower()
                text = _txt(b, "deck_id", "deck_title", "标题", "核心论断", "本页讲什么", "适合复用场景").lower()
                named_work = any(t in text for t in (
                    "specee", "specdiff", "flashoverlap", "semi-pd", "endor",
                    "flightllm", "flightvgm", "tb-stc", "hpca", "isca", "date",
                ))
                narrow_terms = (
                    "单个工作", "单篇", "论文", "通信重叠",
                    "sm 分区", "目标—洞察—方案", "summary:flightvgm",
                    "首个 fpga", "tensor core", "张量核",
                )
                if named_work and role_in_section in {"method_detail", "result", "worker_intro", "closer"}:
                    return True
                return any(t in text for t in narrow_terms)

            for s in slides_local:
                sid = _slide_source_id_local(s)
                if not sid:
                    continue
                b = brief_by_id.get(str(sid)) or {}
                role = (s.get("target_role") or "").lower()
                reasons = []
                if role in content_roles and _nav(b):
                    reasons.append("content_page_bound_to_navigation_source")
                if _overview(s) and _personal(b):
                    reasons.append("overview_source_identity_mismatch")
                if _overview(s) and _narrow_framework_source(b):
                    reasons.append("framework_or_recap_source_narrower_than_target")
                if not reasons:
                    continue
                s["source_carrier_resource_kind"] = "new"
                s["kind"] = "new"
                s["gap_status"] = "no_match"
                s["source_resource_ids"] = []
                s.setdefault("_illegal_binding_reasons", []).extend(reasons)
                changed.append({
                    "slide_index_in_chapter": s.get("slide_index_in_chapter"),
                    "source_slide_id": sid,
                    "source_title": b.get("标题"),
                    "reasons": reasons,
                })
            if changed:
                print(f"[OUTLINE stage1b ch{ch_idx}] {label}: demoted "
                      f"{len(changed)} illegal source bindings → PASS-2 gap",
                      flush=True)
                detail.setdefault("_illegal_binding_demotions", []).extend(changed)
            return detail

        # ============================================================
        # PASS-1: carrier_only
        # v18 fix A: MERGE dual pool — rhythm carriers (叙事骨架) AND candidate_
        # carrier_sections (本项目主题匹配 sections from IDEA). Previous behavior
        # picked ONE (rhythm preferred, else candidate), which caused ch5-style
        # all-gap: rhythm pool was topic-mismatched with the stub the LLM built.
        # ============================================================
        tier1: list[dict] = []
        seen_ids: set = set()
        if rhythm_pattern_id:
            rhythm_carriers = oc.load_slide_briefs_for_rhythm_pattern(
                rhythm_pattern_id, max_carriers=3)
            for b in rhythm_carriers:
                sid = b.get("slide_id")
                if sid and sid not in seen_ids:
                    seen_ids.add(sid)
                    tier1.append(b)
        if candidate_sections:
            proj_carriers = oc.load_slide_briefs_for_chapter(
                candidate_sections)
            for b in proj_carriers:
                sid = b.get("slide_id")
                if sid and sid not in seen_ids:
                    seen_ids.add(sid)
                    tier1.append(b)
        # Structural pages must be source-backed too. A section_divider stub can
        # live inside a method/framework chapter, so derive structural candidate
        # needs from stub roles, not just chapter.section_role.
        structural_candidate_roles = {
            "opening", "cover", "agenda", "chapter_divider",
            "section_divider", "closing", "references",
        }
        needed_struct_roles = set()
        if ch_role in structural_candidate_roles:
            needed_struct_roles.add(ch_role)
        for _stub in (stub_data.get("stubs") or []):
            if not isinstance(_stub, dict):
                continue
            _sr = str(_stub.get("target_role") or "").lower()
            if _sr in structural_candidate_roles:
                needed_struct_roles.add(_sr)
        struct_candidates: list[dict] = []
        for _sr in sorted(needed_struct_roles):
            for b in oc.load_structural_slide_briefs_for_role(_sr, max_keep=12):
                sid = b.get("slide_id")
                if sid and sid not in seen_ids:
                    seen_ids.add(sid)
                    struct_candidates.append(b)
                    tier1.append(b)
        tier1 = oc.trim_slide_briefs_by_chapter_relevance(tier1, chapter, max_keep=15)
        # Re-append structural candidates if the chapter relevance trim dropped
        # them because the enclosing chapter is a content role.
        _tier1_ids = {b.get("slide_id") for b in tier1 if b.get("slide_id")}
        for b in struct_candidates:
            sid = b.get("slide_id")
            if sid and sid not in _tier1_ids:
                tier1.append(b)
                _tier1_ids.add(sid)
        for b in tier1:
            b["_tier"] = 1

        # v4.3 (Phase J): annotate tier1 with claim alignment scores
        # Use chapter-level proxy claim = first 2 stubs' page_purpose_hint + chapter purpose
        proxy_target_claim_parts = []
        if chapter.get("purpose"):
            proxy_target_claim_parts.append(chapter["purpose"][:120])
        for st in (stub_data.get("stubs") or [])[:3]:
            ph = st.get("page_purpose_hint") or ""
            if ph:
                proxy_target_claim_parts.append(ph[:50])
        proxy_target_claim = " / ".join(proxy_target_claim_parts)
        if tier1 and proxy_target_claim:
            try:
                oc.annotate_briefs_with_claim_alignment(
                    proxy_target_claim, tier1,
                    target_role=chapter.get("section_role"),
                    chapter_layer=ch_layer if ch_layer != "other" else None,
                )
                # Reorder tier1 by claim_alignment desc, so LLM sees best first
                tier1.sort(key=lambda b: -float(b.get("_claim_alignment") or 0.0))
                hi = sum(1 for b in tier1 if (b.get("_claim_alignment") or 0) >= 0.5)
                lo = sum(1 for b in tier1 if (b.get("_claim_alignment") or 0) < 0.25)
                print(f"[OUTLINE stage1b ch{ch_idx}] PASS-1 claim alignment: "
                      f"{hi} high (≥0.5), {lo} low (<0.25) of {len(tier1)} carriers", flush=True)
            except Exception as e:
                print(f"[OUTLINE stage1b ch{ch_idx}] claim alignment failed: {e}", flush=True)

        # v17 fix: trim tier1 to reduce single-shot LLM burden (esp. motivation章 like ch2
        # where 15 candidates × 8 stubs = 120 pair decisions push a single call past 900s).
        # Prefer keeping scored high/mid candidates; only fall back to raw slice if scoring
        # left too few.
        if len(tier1) > 10:
            _before = len(tier1)
            scored_kept = [b for b in tier1 if (b.get("_claim_alignment") or 0) >= 0.3]
            tier1 = scored_kept[:10] if len(scored_kept) >= 5 else tier1[:10]
            print(f"[OUTLINE stage1b ch{ch_idx}] tier1 trimmed {_before}→{len(tier1)} "
                  f"(low-alignment carriers dropped to keep single-call payload manageable)",
                  flush=True)
            _tier1_ids = {b.get("slide_id") for b in tier1 if b.get("slide_id")}
            _restored_struct = 0
            for b in struct_candidates:
                sid = b.get("slide_id")
                if sid and sid not in _tier1_ids:
                    tier1.append(b)
                    _tier1_ids.add(sid)
                    _restored_struct += 1
            if _restored_struct:
                print(f"[OUTLINE stage1b ch{ch_idx}] restored {_restored_struct} "
                      "structural candidates after relevance trim", flush=True)
        if ch_role in {"opening", "cover", "agenda", "section_divider", "closing", "references"}:
            struct_pool = [b for b in oc.load_structural_slide_briefs_for_role(ch_role, max_keep=12)
                           if b.get("slide_id")]
            struct_ids = {b.get("slide_id") for b in struct_pool}
            tier1 = [b for b in tier1 if (b.get("slide_id") not in struct_ids) or b in struct_pool]
            for b in struct_pool:
                if b.get("slide_id") and b.get("slide_id") not in {x.get("slide_id") for x in tier1}:
                    tier1.append(b)
            tier1 = sorted(tier1, key=lambda b: float(b.get("_claim_alignment") or b.get("_score") or 0.0), reverse=True)

        payload_p1 = {
            "chapter": chapter,
            "structural_page_contract": idea.get("structural_page_contract") or _default_structural_page_contract(),
            "chapter_stubs": stub_data.get("stubs") or [],
            "chapter_decomposition": decomp,
            "candidate_slide_briefs": tier1,
            "library_candidate_sections": candidate_sections,
            "resource_library_contract": resource_library_contract,
            "candidate_pool_stats": {
                "tier1_rhythm_carriers": len(tier1),
                "chapter_layer": ch_layer,
                "subline_count": len(sublines),
                "library_candidate_sections": candidate_sections,
                "resource_library_contract": resource_library_contract,
                # v17 C.2: group candidates by (deck_id, section_id) so LLM can
                # see continuous-page opportunities within same section.
                "candidate_sections_grouped": _group_briefs_by_section(tier1),
                # v20 W1: section.md summary so LLM understands the "why" of
                # slide N → slide N+1 relations. Helps prefer contiguous reuse
                # (issue: FlightLLM 32-page picked isolated slide instead of section span).
                "candidate_section_summaries": oc.load_section_summaries_for_briefs(tier1),
            },
            "intake_constraints": intake_constraints,
            "narrative_constraints_slice": narrative_slice,
            "project_evidence_briefs": project_pdf_briefs,
        }
        p1 = _stage1b_call_llm(payload_p1, ch_idx, mode="carrier_only")
        if not p1.get("ok"):
            return {"chapter_index": ch_idx, "ok": False, "error": p1.get("error")}
        detail_v1 = _mark_illegal_bindings_as_gap(p1["data"], label="PASS-1 source guard")

        # Detect gaps from PASS-1 output
        slides_v1 = detail_v1.get("slides") or []
        gap_slides_indices = []
        for s in slides_v1:
            gs = (s.get("gap_status") or "").lower()
            kind = (s.get("source_carrier_resource_kind") or s.get("kind") or "").lower()
            refs = s.get("source_resource_ids") or []
            if (
                gs in {"weak_match", "no_match", "weak_match_after_expansion", "no_match_after_expansion", "not_applicable"}
                or kind in {"matching_fallback", "new", "no_supporting_material"}
                or not refs
            ):
                gap_slides_indices.append(s.get("slide_index_in_chapter"))
        print(f"[OUTLINE stage1b ch{ch_idx}] PASS-1: {len(slides_v1)} slides, "
              f"{len(gap_slides_indices)} gaps {gap_slides_indices}", flush=True)
        if not gap_slides_indices:
            # No gaps → return PASS-1 result directly
            return {"chapter_index": ch_idx, "ok": True, "data": detail_v1}

        # ============================================================
        # PASS-2: fill_gaps via cascade search per gap slide
        # v4.2: chapter-level library keyword evidence first (resource-driven concrete names)
        # ============================================================
        # Aggregate all abstract_topics from sublines + extract real concrete keywords
        all_abstract_topics: list[str] = []
        for sl in sublines:
            all_abstract_topics.extend(sl.get("abstract_topics") or sl.get("keywords") or [])
            if sl.get("name"):
                all_abstract_topics.append(sl["name"])
        chapter_lib_evidence = oc.extract_library_keywords_for_topic(
            abstract_topics=all_abstract_topics,
            chapter_layer=ch_layer if ch_layer != "other" else None,
            section_role=chapter.get("section_role") or None,
            top_decks=10,
            max_keywords=20,
        ) if all_abstract_topics else {"concrete_keywords": [], "top_decks": []}
        # Build a chapter-level pool of REAL concrete keywords (evidence-backed)
        chapter_real_keywords = [
            kw["keyword"] for kw in (chapter_lib_evidence.get("concrete_keywords") or [])
        ]
        print(f"[OUTLINE stage1b ch{ch_idx}] PASS-2 lib evidence: "
              f"{len(chapter_real_keywords)} concrete keywords from "
              f"{len(chapter_lib_evidence.get('top_decks') or [])} decks", flush=True)

        # Per gap, gather extended candidates via deck→section→slide cascade.
        # Exclude only sources already bound in PASS-1 output. Do not exclude the
        # whole tier1 pool: unpicked tier1 slides are valid repair candidates.
        already_ids: set[str] = set()
        for _sl in slides_v1:
            for _ref in (_sl.get("source_resource_ids") or []):
                if isinstance(_ref, dict) and _ref.get("slide_id"):
                    already_ids.add(_ref["slide_id"])
                elif isinstance(_ref, str):
                    already_ids.add(_ref)
        direct_material_briefs = (
            oc.load_slide_briefs_for_chapter(candidate_sections, max_slides_per_section=40)
            if candidate_sections else []
        )
        gap_payloads = []
        all_extended: list[dict] = []
        for gidx in gap_slides_indices:
            stub = next((s for s in (stub_data.get("stubs") or [])
                         if s.get("slide_index_in_chapter") == gidx), None)
            if not stub:
                continue
            sub_idx = stub.get("belongs_to_subline_index")
            sub_abstract: list[str] = []
            sub_name = None
            if sub_idx and sub_idx <= len(sublines):
                sl = sublines[sub_idx - 1]
                sub_abstract.extend(sl.get("abstract_topics") or sl.get("keywords") or [])
                sub_name = sl.get("name")
                if sub_name:
                    sub_abstract.append(sub_name)
            hint = stub.get("page_purpose_hint") or ""
            if hint:
                sub_abstract.append(hint[:30])
            # Cascade keys = subline abstract_topics + chapter-level real concrete keywords
            # This is the key v4.2 change: concrete names come from LIBRARY EVIDENCE
            # not LLM imagination. e.g. driver supplies "FlashOverlap/semi-PD/SpecEE"
            # which actually exist in resources, vs LLM may write "vLLM" which doesn't.
            #
            # v30 fix: also extract BARE work names (e.g. "FlightLLM" from
            # "FlightLLM大模型推理加速") — cascade matches on token overlap and
            # compound phrases don't tokenize into "FlightLLM" alone, so slides
            # titled "FlightLLM：FPGA 上 LLM 推理" score 0.20 instead of 3.80.
            import re as _re
            _bare_re = _re.compile(r'[A-Z][A-Za-z0-9\-\+]{2,}(?:\-[A-Za-z0-9\+]{1,})*')
            _bare_kws: list[str] = []
            for _k in chapter_real_keywords[:10]:
                for _m in _bare_re.findall(_k):
                    if _m not in {"KV", "EP", "PD", "II", "LLM", "GPU", "FPGA",
                                    "TPU", "CPU", "MoE", "AI", "MLP"} \
                            and _m not in _bare_kws:
                        _bare_kws.append(_m)
            gap_slide_v1 = next(
                (s for s in slides_v1 if s.get("slide_index_in_chapter") == gidx),
                {},
            )
            gap_terms = [
                gap_slide_v1.get("target_title") or "",
                gap_slide_v1.get("target_claim") or "",
            ]
            gap_terms.extend(gap_slide_v1.get("key_points") or [])
            gap_terms.extend(gap_slide_v1.get("anchor_terms") or [])
            cascade_keys = sub_abstract + gap_terms + _bare_kws + chapter_real_keywords[:10]
            cascade = oc.cascade_search_for_gap(
                keywords=cascade_keys,
                layer=ch_layer if ch_layer != "other" else None,
                role_hint=ch_role if ch_role else None,
                exclude_slide_ids=list(already_ids),
                max_decks=5, max_sections=8, max_slides=10,
            )
            extended = list(cascade["slides"] or [])

            # IDEA already selected concrete deck/page ranges for this chapter.
            # Add those real slides directly so PASS-2 can choose TB-STC/SpecEE/
            # Semi-PD/etc. even when keyword cascade misses the deck.
            direct_seen = {b.get("slide_id") for b in extended if b.get("slide_id")}
            direct_scored: list[tuple[float, dict]] = []
            gap_blob_terms = [str(x) for x in cascade_keys if x]
            for b in direct_material_briefs:
                sid = b.get("slide_id")
                if not sid or sid in already_ids or sid in direct_seen:
                    continue
                blob = " ".join([
                    str(b.get("deck_title") or ""),
                    str(b.get("section_id") or ""),
                    str(b.get("section_role") or ""),
                    str(b.get("页面角色") or ""),
                    str(b.get("页在section中的作用") or ""),
                    str(b.get("标题") or ""),
                    str(b.get("核心论断") or ""),
                    str(b.get("本页讲什么") or ""),
                    " ".join(str(x) for x in (b.get("关键文字") or [])),
                    " ".join(str(x) for x in (b.get("适合复用场景") or [])),
                ]).lower()
                score = 0.0
                for term in gap_blob_terms[:80]:
                    low = term.lower().strip()
                    if len(low) >= 2 and low in blob:
                        score += 1.0
                for proper in _bare_re.findall(" ".join(gap_blob_terms)):
                    if proper.upper() not in {"KV", "EP", "PD", "II", "LLM", "GPU", "FPGA",
                                              "TPU", "CPU", "MOE", "AI", "MLP"} \
                            and proper.lower() in blob:
                        score += 4.0
                direct_scored.append((score, b))
            direct_scored.sort(key=lambda x: -x[0])
            for score, b in direct_scored[:20]:
                b = dict(b)
                b["_tier"] = 2
                b["_for_gap_slide_index"] = gidx
                b["_direct_material_hint_score"] = round(score, 2)
                b["_source"] = "idea_material_section_hint"
                direct_seen.add(b.get("slide_id"))
                extended.append(b)
            for b in extended:
                b["_tier"] = 2
                b["_for_gap_slide_index"] = gidx
            # v4.3 (Phase J): per-gap-slide claim alignment (use this stub's
            # page_purpose_hint as proxy target_claim — more focused than chapter-level)
            stub_target_proxy = (
                (gap_slide_v1.get("target_claim") if isinstance(gap_slide_v1, dict) else "")
                or hint
                or sub_name
                or ""
            )
            if extended and stub_target_proxy:
                try:
                    oc.annotate_briefs_with_claim_alignment(
                        stub_target_proxy, extended,
                        target_role=chapter.get("section_role"),
                        chapter_layer=ch_layer if ch_layer != "other" else None,
                    )
                    extended.sort(key=lambda b: (
                        -float(b.get("_claim_alignment") or 0.0),
                        -float(b.get("_direct_material_hint_score") or b.get("_score") or 0.0),
                    ))
                except Exception as e:
                    print(f"[OUTLINE stage1b ch{ch_idx} gap{gidx}] claim align failed: {e}", flush=True)
            already_ids |= {b.get("slide_id") for b in extended if b.get("slide_id")}

            # v30 fix B: 把三层检索结果按 deck→section→slide 层级结构组织
            # 送 LLM, 让 LLM 优先"先选合适 deck, 再选 section, 再选 slide" 而不是
            # 从 flat slides 里瞎挑. 特别关键: 让 LLM 看到"这个 slide 属于哪个 deck
            # 哪个 section", 避免跨 deck cherry-pick 拼成语义混乱的 deck.
            _cascade_decks = cascade.get("decks") or []
            _cascade_sections = cascade.get("sections") or []
            _deck_meta_by_id = {}
            for _d in _cascade_decks:
                did = _d.get("deck_id")
                if did:
                    _deck_meta_by_id[did] = {
                        "deck_id": did,
                        "deck_title": _d.get("title") or _d.get("deck_title") or "",
                        "score": _d.get("_score") or _d.get("score"),
                        "报告类型": _d.get("报告类型"),
                    }
            _sections_by_deck: dict[str, list] = {}
            for _sec in _cascade_sections:
                did = _sec.get("deck_id")
                if not did:
                    continue
                _sections_by_deck.setdefault(did, []).append({
                    "section_id": _sec.get("section_id"),
                    "section_title": _sec.get("section_title") or _sec.get("标题"),
                    "section_role": _sec.get("section_role") or _sec.get("章节角色"),
                    "score": _sec.get("_score") or _sec.get("score"),
                })
            _slides_by_section: dict[str, list] = {}
            for _sl in extended:
                sid = _sl.get("section_id")
                if not sid:
                    continue
                _slides_by_section.setdefault(sid, []).append({
                    "slide_id": _sl.get("slide_id"),
                    "标题": _sl.get("标题") or _sl.get("title"),
                    "核心论断": _sl.get("核心论断") or _sl.get("claim"),
                    "section_role": _sl.get("section_role"),
                    "_score": _sl.get("_score"),
                    "_claim_alignment": _sl.get("_claim_alignment"),
                })

            gap_payloads.append({
                "gap_slide_index_in_chapter": gidx,
                "subline_index": sub_idx,
                "subline_name": sub_name,
                "subline_abstract_topics": sub_abstract[:8],
                "library_evidence_keywords_used": chapter_real_keywords[:10],
                "page_purpose_hint": hint,
                # v30 fix B: 3-tier cascade hierarchy — LLM 必须按 deck→section→slide 挑
                "cascade_hierarchy": {
                    "top_decks": list(_deck_meta_by_id.values())[:5],
                    "sections_by_deck": _sections_by_deck,
                    "slides_by_section": _slides_by_section,
                    "hint": ("Prefer picking 1 deck first (owner/主题 match target claim), "
                             "then 1-2 sections within that deck, then slides within those "
                             "sections. Avoid cross-deck cherry-pick which produces "
                             "semantically incoherent slides."),
                },
                # 保留 flat list 供 legacy / claim-alignment 排序用
                "extended_candidate_slide_briefs": extended,
                "cascade_stats": {
                    "decks_found": len(cascade["decks"]),
                    "sections_found": len(cascade["sections"]),
                    "slides_found": len(extended),
                },
            })
            all_extended.extend(extended)

        payload_p2 = {
            "chapter": chapter,
            "structural_page_contract": idea.get("structural_page_contract") or _default_structural_page_contract(),
            "chapter_stubs": stub_data.get("stubs") or [],
            "chapter_decomposition": decomp,
            "library_candidate_sections": candidate_sections,
            "resource_library_contract": resource_library_contract,
            "library_keyword_evidence": {
                "concrete_keywords": (chapter_lib_evidence.get("concrete_keywords") or [])[:15],
                "top_decks": (chapter_lib_evidence.get("top_decks") or [])[:5],
            },
            "detail_pass1": detail_v1,
            "gap_slides_with_extended_candidates": gap_payloads,
            "extended_candidate_pool_size": len(all_extended),
            "intake_constraints": intake_constraints,
            "narrative_constraints_slice": narrative_slice,
            "project_evidence_briefs": project_pdf_briefs,
        }
        p2 = _stage1b_call_llm(payload_p2, ch_idx, mode="fill_gaps")
        if not p2.get("ok"):
            print(f"[OUTLINE stage1b ch{ch_idx}] PASS-2 failed, returning PASS-1 as-is: "
                  f"{p2.get('error')}", flush=True)
            # Salvage: return PASS-1 detail (gaps remain marked)
            return {"chapter_index": ch_idx, "ok": True, "data": detail_v1}
        detail_v2 = p2["data"]
        detail_v2 = _mark_illegal_bindings_as_gap(detail_v2, label="PASS-2 source guard")
        print(f"[OUTLINE stage1b ch{ch_idx}] PASS-2 OK: "
              f"{len(detail_v2.get('slides') or [])} slides", flush=True)
        return {"chapter_index": ch_idx, "ok": True, "data": detail_v2}

    def _process_chapter_stage1a(chapter: dict) -> dict:
        """v17 C.1a: only Stage 1a (chapter stub). Stage 1b runs later after skeleton review."""
        ch_idx = chapter.get("section_index")
        stub_res = _stage1a_chapter_stub(chapter)
        if not stub_res["ok"]:
            return {"chapter_index": ch_idx, "ok": False,
                    "error": f"stage 1a: {stub_res['error']}"}
        print(f"[OUTLINE ch{ch_idx}] stage 1a OK "
              f"({stub_res['data'].get('page_count')} slides)", flush=True)
        return {"chapter_index": ch_idx, "ok": True, "stub": stub_res["data"]}

    def _process_chapter_stage1b(chapter: dict, stub_data: dict) -> dict:
        """v17 C.2: only Stage 1b (slide detail). Called after C.1b skeleton review."""
        ch_idx = chapter.get("section_index")
        detail_res = _stage1b_slide_detail(chapter, stub_data)
        if not detail_res["ok"]:
            return {"chapter_index": ch_idx, "ok": False,
                    "error": f"stage 1b: {detail_res['error']}",
                    "stub": stub_data}
        print(f"[OUTLINE ch{ch_idx}] stage 1b OK "
              f"({len(detail_res['data'].get('slides', []))} slides)", flush=True)
        return {
            "chapter_index": ch_idx,
            "ok": True,
            "stub": stub_data,
            "detail": detail_res["data"],
        }

    def _process_chapter(chapter: dict) -> dict:
        """Legacy sequential 1a→1b path (kept for backward compat with paths that
        call it, e.g. review-loop-triggered per-chapter redo in decomposition
        dispatch). New v17 main loop uses _process_chapter_stage1a/1b separately."""
        ch_idx = chapter.get("section_index")
        stub_res = _stage1a_chapter_stub(chapter)
        if not stub_res["ok"]:
            return {"chapter_index": ch_idx, "ok": False,
                    "error": f"stage 1a: {stub_res['error']}"}
        print(f"[OUTLINE ch{ch_idx}] stage 1a OK "
              f"({stub_res['data'].get('page_count')} slides)", flush=True)
        detail_res = _stage1b_slide_detail(chapter, stub_res["data"])
        if not detail_res["ok"]:
            return {"chapter_index": ch_idx, "ok": False,
                    "error": f"stage 1b: {detail_res['error']}",
                    "stub": stub_res["data"]}
        print(f"[OUTLINE ch{ch_idx}] stage 1b OK "
              f"({len(detail_res['data'].get('slides', []))} slides)", flush=True)
        return {
            "chapter_index": ch_idx,
            "ok": True,
            "stub": stub_res["data"],
            "detail": detail_res["data"],
        }

    def _build_unified_chapter_payload(chapter: dict) -> dict:
        """Prepare one compact, bounded context for the unified per-chapter Claude.

        This is intentionally local/deterministic: it gathers the library pieces
        the chapter may need, but does not run extra model scoring. The single
        chapter Claude call owns skeleton decisions and source-choice judgment.
        """
        ch_idx = chapter.get("section_index")
        ch_role = (chapter.get("section_role") or "").lower()
        role_filter = ch_role or None
        chapter_archetypes = oc.load_page_specific_archetypes(role_filter=role_filter) or archetypes
        chapter_archetype_summary = [
            {"id": a.get("id"), "category": a.get("category"),
             "enforcement_level": a.get("enforcement_level"),
             "applicable_role": a.get("applicable_role") or [],
             "summary": (a.get("summary") or a.get("description") or "")[:120]}
            for a in chapter_archetypes
        ]

        candidate_sections = _chapter_candidate_sections(chapter, max_sections=10)
        rhythm_pattern_id = chapter.get("section_rhythm_pattern_id")
        if not rhythm_pattern_id:
            legacy_rp = (chapter.get("section_rhythm_patterns") or [{}])[0]
            rhythm_pattern_id = legacy_rp.get("pattern_id")
        rhythm_pattern = oc.load_rhythm_pattern_trimmed(
            rhythm_pattern_id, max_carriers=5) if rhythm_pattern_id else None
        narrative_slice = oc.slice_narrative_constraints_for_chapter(nc, ch_idx)
        ch_layer = oc.infer_chapter_layer(chapter)

        cand_slide_hint: dict[str, int] = {}
        if rhythm_pattern:
            for c in (rhythm_pattern.get("carriers") or [])[:5]:
                if isinstance(c, dict):
                    sid = c.get("section_id")
                    if sid:
                        cand_slide_hint[sid] = c.get("page_count") or c.get("slide_count")
        if not cand_slide_hint:
            for c in candidate_sections:
                if c.get("section_id"):
                    cand_slide_hint[c.get("section_id")] = c.get("page_count")

        rhythm_briefs: list[dict] = []
        if rhythm_pattern_id:
            rhythm_briefs = oc.load_slide_briefs_for_rhythm_pattern(
                rhythm_pattern_id, max_carriers=3, max_slides_per_section=16)
            for b in rhythm_briefs:
                b["_tier"] = 1
                b["_source_pool"] = "rhythm_carrier"

        material_briefs: list[dict] = []
        if candidate_sections:
            material_briefs = oc.load_slide_briefs_for_chapter(
                candidate_sections, max_slides_per_section=28)
            for b in material_briefs:
                b["_tier"] = 1
                b["_source_pool"] = "idea_material_section_hint"

        structural_roles = {
            "opening", "cover", "agenda", "chapter_divider",
            "section_divider", "closing", "references",
        }
        needed_struct_roles: set[str] = set()
        if ch_role in structural_roles:
            needed_struct_roles.add(ch_role)
        if chapter.get("requires_section_divider") is True:
            needed_struct_roles.add("section_divider")
        structural_briefs: list[dict] = []
        seen_struct: set[str] = set()
        for sr in sorted(needed_struct_roles):
            for b in oc.load_structural_slide_briefs_for_role(sr, max_keep=10):
                sid = b.get("slide_id")
                if not sid or sid in seen_struct:
                    continue
                seen_struct.add(sid)
                bb = dict(b)
                bb["_tier"] = 1
                bb["_source_pool"] = f"structural_{sr}"
                structural_briefs.append(bb)

        # Local cascade gives the same Claude call a small fallback pool without
        # splitting source matching into another model pass.
        cascade_terms: list[str] = []
        for key in ("chapter", "purpose", "section_role", "section_rhythm_summary"):
            val = chapter.get(key)
            if isinstance(val, str) and val:
                cascade_terms.append(val)
        for key in ("claims_to_make", "claims_to_setup_for_later"):
            vals = chapter.get(key) or []
            if isinstance(vals, list):
                cascade_terms.extend(str(v) for v in vals if v)
        if candidate_sections:
            for sec in candidate_sections:
                cascade_terms.extend([
                    str(sec.get("deck_title") or ""),
                    str(sec.get("section_title") or ""),
                    str(sec.get("reason") or ""),
                ])
        cascade_briefs: list[dict] = []
        try:
            cascade = oc.cascade_search_for_gap(
                keywords=[t for t in cascade_terms if t][:18],
                layer=ch_layer if ch_layer != "other" else None,
                role_hint=ch_role if ch_role else None,
                exclude_slide_ids=None,
                max_decks=5,
                max_sections=8,
                max_slides=18,
            )
            for b in cascade.get("slides") or []:
                bb = dict(b)
                bb["_tier"] = 2
                bb["_source_pool"] = "local_cascade"
                cascade_briefs.append(bb)
        except Exception as exc:
            print(f"[OUTLINE unified ch{ch_idx}] local cascade failed: {exc}", flush=True)

        all_pool: list[dict] = []
        seen_ids: set[str] = set()
        for pool in (rhythm_briefs, material_briefs, cascade_briefs, structural_briefs):
            for b in pool:
                sid = b.get("slide_id")
                if not sid or sid in seen_ids:
                    continue
                seen_ids.add(sid)
                all_pool.append(b)

        # Trim only content pools. Structural candidates are appended back so
        # required cover/agenda/divider pages cannot be dropped by relevance.
        content_pool = [b for b in all_pool if not str(b.get("_source_pool") or "").startswith("structural_")]
        content_pool = oc.trim_slide_briefs_by_chapter_relevance(
            content_pool, chapter, max_keep=30)
        content_ids = {b.get("slide_id") for b in content_pool if b.get("slide_id")}
        candidate_slide_briefs = list(content_pool)
        for b in structural_briefs:
            sid = b.get("slide_id")
            if sid and sid not in content_ids:
                candidate_slide_briefs.append(b)
                content_ids.add(sid)

        from collections import defaultdict
        clusters: dict = defaultdict(list)
        for b in candidate_slide_briefs:
            role_in_sec = (b.get("页在section中的作用") or b.get("页面角色") or "other")
            clusters[str(role_in_sec).lower()].append(b)
        cluster_summary = []
        for role_key, items in sorted(clusters.items(), key=lambda x: -len(x[1])):
            cluster_summary.append({
                "role_in_section": role_key,
                "n_slides": len(items),
                "sample_titles": [(x.get("标题") or x.get("title") or "")[:50] for x in items[:6]],
                "sample_claims": [(x.get("核心论断") or x.get("claim") or "")[:70] for x in items[:5]],
                "sample_source_pools": [x.get("_source_pool") for x in items[:6]],
            })

        pgid = chapter.get("parallel_group_id")
        parallel_group_context = {}
        if pgid:
            pg_contract = next(
                (c for c in (idea.get("parallel_group_contracts") or [])
                 if isinstance(c, dict) and str(c.get("parallel_group_id")) == str(pgid)),
                None,
            )
            siblings = []
            for other in (chapter_plan or []):
                if not isinstance(other, dict):
                    continue
                if other.get("parallel_group_id") != pgid:
                    continue
                if other.get("section_index") == chapter.get("section_index"):
                    continue
                siblings.append({
                    "section_index": other.get("section_index"),
                    "chapter": other.get("chapter"),
                    "purpose": other.get("purpose"),
                    "expected_pages_indicative": other.get("expected_pages_indicative"),
                    "claims_to_make": (other.get("claims_to_make") or [])[:3],
                    "section_role": other.get("section_role"),
                })
            parallel_group_context = {
                "group_id": pgid,
                "terminology": chapter.get("parallel_group_terminology") or {},
                "sibling_chapters": siblings,
                "contract": pg_contract or {},
            }

        deck_contract = {
            "structural_page_contract": idea.get("structural_page_contract") or _default_structural_page_contract(),
            "identity": idea.get("identity") or {},
            "narrative_constraints_summary": {
                "thesis": nc.get("thesis") or nc.get("main_thesis"),
                "framework_anchor": nc.get("framework_anchor") or nc.get("framework_anchor_term"),
                "anti_patterns_to_avoid": (nc.get("anti_patterns_to_avoid") or [])[:8],
            },
            "parallel_group_contracts": [
                c for c in (idea.get("parallel_group_contracts") or [])
                if isinstance(c, dict)
            ],
            "resource_library_contract": resource_library_contract,
        }

        return {
            "chapter": chapter,
            "deck_contract": deck_contract,
            "logic_story_hard_rules_summary": hard_rules,
            "selected_rhythm_pattern": rhythm_pattern or {},
            "page_specific_archetypes": chapter_archetype_summary,
            "narrative_constraints_slice": narrative_slice,
            "library_candidate_sections": candidate_sections,
            "candidate_section_slide_count_hint": cand_slide_hint,
            "candidate_pool_summary": {
                "n_total": len(candidate_slide_briefs),
                "clusters_by_role": cluster_summary,
                "source_pool_counts": {
                    "rhythm_carriers": len(rhythm_briefs),
                    "idea_material_sections": len(material_briefs),
                    "local_cascade": len(cascade_briefs),
                    "structural": len(structural_briefs),
                },
                "hint": (
                    "Use this pool to decide page count, sublines, and source binding in one call. "
                    "If a claim is unsupported, narrow the claim to a real candidate or omit the page."
                ),
            },
            "candidate_slide_briefs": candidate_slide_briefs,
            "structural_candidate_slide_briefs": structural_briefs,
            "candidate_pool_stats": {
                "chapter_layer": ch_layer,
                "candidate_sections_grouped": _group_briefs_by_section(candidate_slide_briefs),
                "candidate_section_summaries": oc.load_section_summaries_for_briefs(candidate_slide_briefs),
            },
            "parallel_group_context": parallel_group_context,
            "intake_constraints": intake_constraints,
            "project_evidence_briefs": project_pdf_briefs,
        }

    def _normalize_unified_chapter_output(chapter: dict, data: dict) -> tuple[dict, dict]:
        ch_idx = chapter.get("section_index")
        d = dict(data or {})
        if "chapter_index" not in d and "section_index" in d:
            d["chapter_index"] = d.get("section_index")
        d["chapter_index"] = ch_idx
        if "slides" not in d or not isinstance(d.get("slides"), list):
            for alt in ("slide_details", "items", "pages"):
                if isinstance(d.get(alt), list):
                    d["slides"] = d.get(alt)
                    break
        if "stubs" not in d or not isinstance(d.get("stubs"), list):
            stubs = []
            for s in (d.get("slides") or []):
                if not isinstance(s, dict):
                    continue
                stubs.append({
                    "slide_index_in_chapter": s.get("slide_index_in_chapter"),
                    "target_role": s.get("target_role") or s.get("role"),
                    "archetype": s.get("archetype") or [],
                    "archetype_placement": s.get("archetype_placement") or s.get("placement"),
                    "page_purpose_hint": s.get("page_purpose_hint") or s.get("page_purpose") or "",
                    "belongs_to_subline_index": s.get("belongs_to_subline_index") or s.get("subline_index"),
                })
            d["stubs"] = stubs
        if "page_count" not in d:
            d["page_count"] = len(d.get("slides") or d.get("stubs") or [])

        norm_stubs = []
        for i, s in enumerate(d.get("stubs") or [], start=1):
            if not isinstance(s, dict):
                continue
            ns = dict(s)
            ns["slide_index_in_chapter"] = ns.get("slide_index_in_chapter") or i
            if "target_role" not in ns and "role" in ns:
                ns["target_role"] = ns.get("role")
            if "archetype_placement" not in ns and "placement" in ns:
                ns["archetype_placement"] = ns.get("placement")
            if isinstance(ns.get("archetype"), str):
                ns["archetype"] = [ns["archetype"]]
            ns["archetype"] = oc.normalize_page_specific_archetype_ids(
                ns.get("archetype"), role_hint=ns.get("target_role") or chapter.get("section_role")
            )
            if "belongs_to_subline_index" not in ns and "subline_index" in ns:
                ns["belongs_to_subline_index"] = ns.get("subline_index")
            norm_stubs.append(ns)
        d["stubs"] = norm_stubs

        # Keep the structural divider contract source-owned by Claude. If it was
        # omitted, insert only the stub; the detail source gate below will still
        # fail unless the model also returned/binds a real source for this page.
        if chapter.get("requires_section_divider") is True:
            stubs = d.get("stubs") if isinstance(d.get("stubs"), list) else []
            first_role = (
                str((stubs[0] or {}).get("target_role") or "").lower()
                if stubs else ""
            )
            if first_role not in {"section_divider", "chapter_divider"}:
                divider_stub = {
                    "slide_index_in_chapter": 1,
                    "target_role": "section_divider",
                    "archetype": ["chapter_navigation_reuses_toc_with_highlight_dimming"],
                    "archetype_placement": "section_open",
                    "page_purpose_hint": "分目录页: 高亮当前章",
                    "belongs_to_subline_index": None,
                    "_driver_inserted_structural_stub": True,
                }
                shifted = []
                for idx, old in enumerate(stubs, start=2):
                    row = dict(old)
                    row["slide_index_in_chapter"] = idx
                    if row.get("archetype_placement") == "section_open":
                        row["archetype_placement"] = "section_middle"
                    shifted.append(row)
                d["stubs"] = [divider_stub] + shifted

        stub_by_idx = {
            int(s.get("slide_index_in_chapter") or i): s
            for i, s in enumerate(d.get("stubs") or [], start=1)
            if isinstance(s, dict)
        }
        norm_slides = []
        for i, s in enumerate(d.get("slides") or [], start=1):
            if not isinstance(s, dict):
                continue
            ns = dict(s)
            idx = int(ns.get("slide_index_in_chapter") or i)
            ns["slide_index_in_chapter"] = idx
            stub = stub_by_idx.get(idx) or {}
            for key in ("target_role", "archetype", "archetype_placement",
                        "page_purpose_hint", "belongs_to_subline_index"):
                if key not in ns or ns.get(key) in (None, "", []):
                    ns[key] = stub.get(key)
            if isinstance(ns.get("archetype"), str):
                ns["archetype"] = [ns["archetype"]]
            ns["archetype"] = oc.normalize_page_specific_archetype_ids(
                ns.get("archetype"), role_hint=ns.get("target_role") or chapter.get("section_role")
            )
            if not ns.get("source_carrier_resource_kind") and ns.get("kind"):
                ns["source_carrier_resource_kind"] = ns["kind"]
            if ns.get("source_resource_ids"):
                ns["source_carrier_resource_kind"] = ns.get("source_carrier_resource_kind") or "carrier_bound"
                ns["kind"] = ns.get("kind") or ns["source_carrier_resource_kind"]
                if ns["source_carrier_resource_kind"] in {"new", "matching_fallback", "no_supporting_material"}:
                    ns["source_carrier_resource_kind"] = "carrier_bound"
                    ns["kind"] = "carrier_bound"
            norm_slides.append(ns)
        norm_slides.sort(key=lambda s: int(s.get("slide_index_in_chapter") or 0))
        d["slides"] = norm_slides
        d["page_count"] = len(norm_slides) if norm_slides else len(d.get("stubs") or [])

        stub_data = {
            "chapter_index": ch_idx,
            "chapter_title": d.get("chapter_title") or chapter.get("chapter"),
            "rhythm_pattern_id": d.get("rhythm_pattern_id") or chapter.get("section_rhythm_pattern_id"),
            "chapter_decomposition": d.get("chapter_decomposition") or {},
            "stubs": d.get("stubs") or [],
            "page_count": d.get("page_count"),
            "work_blocks": d.get("work_blocks") or [],
            "parallel_group_adherence": d.get("parallel_group_adherence") or {},
            "page_to_rhythm_node_map": d.get("page_to_rhythm_node_map") or [],
        }
        if d.get("rhythm_adherence"):
            stub_data["rhythm_adherence"] = d["rhythm_adherence"]
        detail_data = {
            "chapter_index": ch_idx,
            "chapter_realized": d.get("chapter_realized") or {},
            "slides": d.get("slides") or [],
            "self_check": d.get("self_check") or {},
        }
        if d.get("rhythm_adherence"):
            detail_data["rhythm_adherence"] = d["rhythm_adherence"]
        return stub_data, detail_data

    def _process_chapter_unified(chapter: dict) -> dict:
        ch_idx = chapter.get("section_index")
        try:
            payload = _build_unified_chapter_payload(chapter)
        except Exception as exc:
            return {"chapter_index": ch_idx, "ok": False,
                    "error": f"unified payload build failed: {exc!r}"}
        prompt = (
            f"Run OUTLINE unified chapter generation for chapter {ch_idx}. "
            "Inside one response, first plan the skeleton, then bind real sources, "
            "then self-check. Output strict JSON only. Do not use sources outside "
            "candidate_slide_briefs / structural_candidate_slide_briefs.\n\n"
            "INPUT:\n" + json.dumps(payload, ensure_ascii=False)
        )
        outcome = None
        for attempt in range(1, 4):
            effective_prompt = prompt
            if attempt >= 3:
                effective_prompt = prompt + (
                    "\n\nFINAL ATTEMPT: keep the chapter compact. Prefer fewer "
                    "source-backed pages over unsupported pages. Every slide still "
                    "needs source_resource_ids."
                )
                print(f"[OUTLINE unified ch{ch_idx}] attempt 3 → compact final attempt",
                      flush=True)
            outcome = claude_cli.call_claude_json(
                effective_prompt,
                skill=["skills/outline_gen/outline_chapter_unified.md"],
                timeout=1200,
            )
            if outcome.get("ok") and isinstance(outcome.get("data"), dict):
                try:
                    stub_data, detail_data = _normalize_unified_chapter_output(
                        chapter, outcome["data"])
                except Exception as exc:
                    return {"chapter_index": ch_idx, "ok": False,
                            "error": f"unified output normalize failed: {exc!r}"}
                if not detail_data.get("slides"):
                    return {"chapter_index": ch_idx, "ok": False,
                            "error": "unified output has no slides",
                            "stub": stub_data}
                missing_src = [
                    s.get("slide_index_in_chapter")
                    for s in detail_data.get("slides") or []
                    if not (s.get("source_resource_ids") or [])
                ]
                if missing_src:
                    return {"chapter_index": ch_idx, "ok": False,
                            "error": f"unified output left slides without source: {missing_src}",
                            "stub": stub_data}
                print(f"[OUTLINE unified ch{ch_idx}] OK "
                      f"({len(detail_data.get('slides') or [])} slides, "
                      f"pool={len(payload.get('candidate_slide_briefs') or [])})",
                      flush=True)
                return {
                    "chapter_index": ch_idx,
                    "ok": True,
                    "stub": stub_data,
                    "detail": detail_data,
                    "unified_payload_stats": {
                        "candidate_slide_briefs": len(payload.get("candidate_slide_briefs") or []),
                        "structural_candidates": len(payload.get("structural_candidate_slide_briefs") or []),
                    },
                }
            print(f"[OUTLINE unified ch{ch_idx}] attempt {attempt}/3 failed: "
                  f"{((outcome or {}).get('error') or '')[:160]}", flush=True)
            if attempt < 3:
                _time.sleep(2 ** attempt)
        return {"chapter_index": ch_idx, "ok": False,
                "error": f"unified generation failed: {((outcome or {}).get('error') or '')[:200]}"}

    def _build_outline_from_chapter_results(chapter_results_in: list[dict],
                                            stage1_errors_in: list[str],
                                            *,
                                            source_label: str) -> tuple[dict, list[str]]:
        per_chapter_slides = []
        for r in chapter_results_in:
            if not r.get("ok"):
                continue
            ds = dict(r["detail"])
            ds["chapter_index"] = r["chapter_index"]
            stub = r.get("stub") or {}
            if "rhythm_adherence" in stub and "rhythm_adherence" not in ds:
                ds["rhythm_adherence"] = stub["rhythm_adherence"]
            per_chapter_slides.append(ds)

        merged = oc.merge_chapter_outlines(per_chapter_slides)
        for _s in merged.get("slides") or []:
            if not _s.get("source_carrier_resource_kind") and _s.get("kind"):
                _s["source_carrier_resource_kind"] = _s["kind"]

        chapter_realized_list = []
        for r in chapter_results_in:
            if not r.get("ok"):
                continue
            det = r.get("detail") or {}
            _cr_raw = det.get("chapter_realized")
            cr = _cr_raw if isinstance(_cr_raw, dict) else {}
            intent = ""
            for ch in chapter_plan:
                if ch.get("section_index") == r["chapter_index"]:
                    claims = ch.get("claims_to_make") or []
                    intent = "; ".join(claims[:2])[:120] if claims else ""
                    break
            chapter_realized_list.append({
                "chapter_index": r["chapter_index"],
                "summary": cr.get("summary") or "",
                "realized_specifics": cr.get("realized_specifics") or [],
                "coverage_status": cr.get("coverage_status") or "",
                "subline_coverage": cr.get("subline_coverage") or [],
                "drift_from_intent": cr.get("drift_from_intent") or {
                    "abstract_intent": intent,
                    "missing_from_source": [],
                    "added_from_source": [],
                    "drift_severity": "unknown",
                },
            })

        sna = idea.get("selected_narrative_arc") or {}
        outline_local = {
            "schema_version": "1.0",
            "generated_at": now(),
            "source": source_label,
            "identity": idea.get("identity"),
            "topic": (idea.get("identity") or {}).get("topic"),
            "language": (idea.get("identity") or {}).get("language") or "zh",
            "slide_count": len(merged["slides"]),
            "user_outline_applied": False,
            "slides": merged["slides"],
            "chapter_to_slide_map": merged["chapter_to_slide_map"],
            "rhythm_adherence_log": merged["rhythm_adherence_log"],
            "chapter_realized": chapter_realized_list,
            "selected_narrative_arc": {
                "primary_pattern_id": sna.get("primary_pattern_id"),
                "borrowed_patterns": sna.get("borrowed_patterns") or [],
                "narrative_arc": sna.get("narrative_arc"),
            },
            "user_concern_history": idea.get("user_concern_history") or [],
            "provenance": {
                "schema_version": "1.0",
                "idea_analysis_path": "idea-analysis.json",
                "rule_relaxed_with_reason": [],
                "outline_generation_mode": source_label,
            },
        }
        outline_local = _normalize_outline_chapter_links(outline_local, chapter_plan)
        outline_local = _enforce_outline_structural_pages(
            outline_local, phase="outline_main_path")
        warnings_local = _check_outline_against_narrative(
            slides=outline_local["slides"], narrative_block=nc)
        if warnings_local:
            outline_local["narrative_warnings"] = warnings_local
            for w in warnings_local:
                print(f"[OUTLINE narrative] {w}", flush=True)
        return outline_local, warnings_local

    def _run_unified_chapter_main_path() -> tuple[dict, list[dict], list[str], list[str]]:
        chapter_results_local: list[dict] = []
        stage1_errors_local: list[str] = []
        max_parallel = int(_os.environ.get("OUTLINE_MAX_PARALLEL", "4") or "4")
        with _cf.ThreadPoolExecutor(max_workers=max_parallel,
                                    thread_name_prefix="outline_unified") as pool:
            futs = {pool.submit(_process_chapter_unified, ch): ch for ch in chapter_plan}
            for fut in _cf.as_completed(futs):
                try:
                    r = fut.result()
                except Exception as e:
                    ch = futs[fut]
                    r = {"chapter_index": ch.get("section_index"), "ok": False,
                         "error": f"executor exception: {e!r}"}
                chapter_results_local.append(r)
                if not r.get("ok"):
                    stage1_errors_local.append(
                        f"ch{r.get('chapter_index')}: {r.get('error', '')[:240]}")
        chapter_results_local.sort(key=lambda r: r.get("chapter_index") or 0)
        ok_count_local = sum(1 for r in chapter_results_local if r.get("ok"))
        print(f"[OUTLINE] unified per-chapter generation done in "
              f"{_time.time()-t_stage1:.1f}s, {ok_count_local}/{len(chapter_results_local)} "
              "chapters OK", flush=True)
        if ok_count_local != len(chapter_results_local):
            raise RuntimeError(
                "Unified OUTLINE did not complete every chapter; "
                + "; ".join(stage1_errors_local)[:600])
        write_json(pdir / "outline-chapter-stubs.json", {
            "schema_version": "1.0",
            "generated_at": now(),
            "source": "claude_unified_chapter_v1",
            "chapter_stubs": [r.get("stub") for r in chapter_results_local if r.get("ok")],
            "stage1_errors": stage1_errors_local,
            "chapter_payload_stats": [
                {
                    "chapter_index": r.get("chapter_index"),
                    **(r.get("unified_payload_stats") or {}),
                }
                for r in chapter_results_local if r.get("ok")
            ],
        })
        outline_local, warnings_local = _build_outline_from_chapter_results(
            chapter_results_local,
            stage1_errors_local,
            source_label="claude_unified_chapter_v1",
        )
        return outline_local, chapter_results_local, stage1_errors_local, warnings_local

    if _use_unified_outline:
        try:
            current, chapter_results, stage1_errors, nlc_warnings = _run_unified_chapter_main_path()
        except Exception as exc:
            diag = {
                "schema_version": "1.0",
                "generated_at": now(),
                "project_id": project_id,
                "error": f"Unified OUTLINE main path failed: {exc}",
            }
            write_json(pdir / "outline-unified-diagnostics.json", diag)
            return {"ok": False, "stage": "OUTLINE_GENERATION",
                    "outline_diagnostics": str(pdir / "outline-unified-diagnostics.json"),
                    "error": str(exc)[:600]}

        import os as _os_outline_codex
        _outline_codex_on = _os_outline_codex.environ.get(
            "OUTLINE_CODEX_LOOP_ENABLED", "0").lower() in {"1", "true", "yes"}
        outline = current
        print("[OUTLINE] using unified per-chapter Claude path "
              "(set OUTLINE_UNIFIED_CHAPTER_CLAUDE=0 for legacy 1a/1b path)",
              flush=True)

        # Unified path intentionally stops here: the per-chapter Claude call
        # already handles skeleton + source binding + self-check in one context.
        # Keep Codex review loops out of this path unless we later add a final
        # post-render review stage.
        current = _normalize_outline_chapter_links(current, chapter_plan)

        _structural_missing = []
        _slides_now = [
            s for s in (current.get("slides") or [])
            if isinstance(s, dict)
        ]
        if not _slides_now or str(_slides_now[0].get("target_role") or "").lower() != "cover":
            _structural_missing.append("slide_1_cover")
        if len(_slides_now) < 2 or str(_slides_now[1].get("target_role") or "").lower() not in {"agenda", "toc"}:
            _structural_missing.append("slide_2_agenda")
        for _ch in chapter_plan:
            if not isinstance(_ch, dict):
                continue
            _role = str(_ch.get("section_role") or "").lower()
            if _role in {"opening", "cover", "agenda", "toc", "references"}:
                continue
            try:
                _ci = int(_ch.get("section_index") or 0)
            except Exception:
                continue
            if _ci <= 0:
                continue
            _ch_slides = [
                s for s in _slides_now
                if int(s.get("chapter_index") or s.get("section_index") or 0) == _ci
            ]
            _ch_slides.sort(key=lambda s: int(s.get("slide_index") or 0))
            if not _ch_slides:
                _structural_missing.append(f"chapter_{_ci}_missing")
                continue
            _first_role = str(_ch_slides[0].get("target_role") or "").lower()
            if _first_role not in {"section_divider", "chapter_divider"}:
                _structural_missing.append(f"chapter_{_ci}_divider")
        if _structural_missing:
            diag = {
                "schema_version": "1.0",
                "generated_at": now(),
                "project_id": project_id,
                "error": "Unified OUTLINE blocked because required structural pages were not generated by Claude.",
                "missing": _structural_missing,
                "outline_draft": current,
            }
            write_json(pdir / "outline-unified-structural-diagnostics.json", diag)
            return {"ok": False, "stage": "OUTLINE_GENERATION",
                    "outline_diagnostics": str(pdir / "outline-unified-structural-diagnostics.json"),
                    "error": "unified outline missing required structural pages: "
                             + ", ".join(_structural_missing[:20])}

        _agenda_roles = {"agenda", "toc", "chapter_divider", "section_divider"}
        _agenda_slides = [
            s for s in (current.get("slides") or [])
            if isinstance(s, dict)
            and str(s.get("target_role") or "").lower() in _agenda_roles
        ]
        if _agenda_slides:
            _canon_src_list = None
            _canon_from = None
            for _s in _agenda_slides:
                _srcs = _s.get("source_resource_ids") or []
                if _srcs:
                    _canon_src_list = list(_srcs)
                    _canon_from = _s.get("slide_index")
                    break
            if _canon_src_list is not None:
                _forced = 0
                for _s in _agenda_slides:
                    if (_s.get("source_resource_ids") or []) != _canon_src_list:
                        _s["source_resource_ids"] = list(_canon_src_list)
                        _s["_agenda_source_forced"] = True
                        _forced += 1
                print(f"[OUTLINE] unified agenda-same-source: "
                      f"{len(_agenda_slides)} agenda-like slides, canonical from "
                      f"slide {_canon_from}, forced {_forced}", flush=True)

        def _unified_source_id(slide: dict) -> str | None:
            refs = slide.get("source_resource_ids") or []
            if not refs:
                return None
            first = refs[0]
            if isinstance(first, dict):
                return first.get("slide_id")
            if isinstance(first, str):
                return first
            return None

        _unified_brief_cache: dict[str, dict] = {}

        def _unified_source_brief(slide: dict) -> dict:
            sid = _unified_source_id(slide)
            if not sid:
                return {}
            if sid not in _unified_brief_cache:
                try:
                    briefs = oc.load_slide_briefs_by_ids([sid])
                except Exception:
                    briefs = []
                _unified_brief_cache[sid] = briefs[0] if briefs else {}
            return _unified_brief_cache.get(sid) or {}

        def _unified_text(brief: dict, *keys: str) -> str:
            parts: list[str] = []
            for key in keys:
                value = brief.get(key)
                if isinstance(value, list):
                    parts.extend(str(v) for v in value if v)
                elif value:
                    parts.append(str(value))
            return " ".join(parts)

        def _unified_is_navigation_source(brief: dict) -> bool:
            role = str(brief.get("页面角色") or "").lower()
            text = _unified_text(
                brief, "标题", "本页讲什么", "核心论断", "适合复用场景", "视觉骨架"
            ).lower()
            return (
                role in {"toc_candidate", "cover_candidate", "ending_candidate", "references"}
                or any(t in text for t in (
                    "toc", "contents", "agenda", "outline",
                    "目录", "议程", "提纲", "章节切换", "章节过渡",
                    "进度导航", "高亮当前", "当前章",
                ))
            )

        _local_issues = []
        _content_roles = {
            "motivation", "background", "problem", "framework", "method",
            "comparison", "benchmark", "result", "experiment", "engineering",
            "discussion", "outlook", "content", "case_study",
        }
        _structural_roles = {"cover", "agenda", "toc", "chapter_divider",
                             "section_divider", "closing", "references"}
        _slides_by_ch: dict[int, list[dict]] = {}
        for _s in (current.get("slides") or []):
            if not isinstance(_s, dict):
                continue
            try:
                _ci = int(_s.get("chapter_index") or _s.get("section_index") or 0)
            except Exception:
                continue
            if _ci:
                _slides_by_ch.setdefault(_ci, []).append(_s)
            _role = str(_s.get("target_role") or "").lower()
            _brief = _unified_source_brief(_s)
            if _role in _content_roles and _unified_is_navigation_source(_brief):
                _local_issues.append({
                    "category": "content_page_bound_to_navigation_source",
                    "slide_index": _s.get("slide_index"),
                    "chapter_index": _s.get("chapter_index"),
                    "target_title": (_s.get("target_title") or "")[:80],
                    "source_title": _brief.get("标题"),
                    "source_role": _brief.get("页面角色"),
                })
            _target_text = " ".join([
                str(_s.get("target_title") or ""),
                str(_s.get("target_claim") or ""),
                str(_s.get("page_purpose") or ""),
                str(_s.get("page_purpose_hint") or ""),
            ]).lower()
            if _role in _content_roles and (
                any(t in _target_text for t in ("contents", "agenda", "outline"))
                or any(t in _target_text for t in ("目录", "导览", "进入本章", "进入下一章"))
            ):
                _local_issues.append({
                    "category": "content_page_written_as_navigation_page",
                    "slide_index": _s.get("slide_index"),
                    "chapter_index": _s.get("chapter_index"),
                    "target_title": (_s.get("target_title") or "")[:80],
                })

        for _ci, _ch_slides in _slides_by_ch.items():
            _by_src: dict[str, list[dict]] = {}
            for _s in _ch_slides:
                _sid = _unified_source_id(_s)
                if _sid:
                    _by_src.setdefault(_sid, []).append(_s)
            for _sid, _dup_slides in _by_src.items():
                if len(_dup_slides) < 2:
                    continue
                _roles = {str(s.get("target_role") or "").lower() for s in _dup_slides}
                if _roles and _roles.issubset(_structural_roles):
                    continue
                _allowed = all(
                    isinstance(s.get("same_source_intent"), dict)
                    and (s.get("same_source_intent") or {}).get("allowed") is True
                    for s in _dup_slides
                )
                if _allowed:
                    continue
                _local_issues.append({
                    "category": "duplicate_source_within_chapter",
                    "chapter_index": _ci,
                    "source_slide_id": _sid,
                    "slide_indices": [s.get("slide_index") for s in _dup_slides],
                    "roles": sorted(_roles),
                })

        if _local_issues:
            diag = {
                "schema_version": "1.0",
                "generated_at": now(),
                "project_id": project_id,
                "error": "Unified OUTLINE blocked by local hard validation.",
                "blocking_issues": _local_issues,
                "outline_draft": current,
            }
            write_json(pdir / "outline-unified-validation-diagnostics.json", diag)
            return {"ok": False, "stage": "OUTLINE_GENERATION",
                    "outline_diagnostics": str(pdir / "outline-unified-validation-diagnostics.json"),
                    "error": f"unified outline local validation found {len(_local_issues)} blocking issues",
                    "blocking_issues": _local_issues[:20]}

        _no_src = []
        for _s in (current.get("slides") or []):
            if not isinstance(_s, dict):
                continue
            if not (_s.get("source_resource_ids") or []):
                _no_src.append({
                    "slide_index": _s.get("slide_index"),
                    "chapter_index": _s.get("chapter_index"),
                    "target_role": _s.get("target_role"),
                    "target_title": (_s.get("target_title") or "")[:60],
                    "kind": _s.get("kind") or _s.get("source_carrier_resource_kind"),
                })
        if _no_src:
            diag = {
                "schema_version": "1.0",
                "generated_at": now(),
                "project_id": project_id,
                **idea_fingerprint,
                "error": "Unified OUTLINE blocked because slides without source_resource_ids are not allowed.",
                "no_source_slides": _no_src,
                "outline_draft": current,
            }
            write_json(pdir / "outline-no-source-diagnostics.json", diag)
            return {"ok": False, "stage": "OUTLINE_GENERATION",
                    "outline_diagnostics": str(pdir / "outline-no-source-diagnostics.json"),
                    "error": f"unified outline: {len(_no_src)} slides have no source_resource_ids",
                    "no_source_slides": _no_src[:20]}

        return _write_outline_artifacts(
            current,
            review_log_in=[],
            final_review_in=None,
            stage1_errors_in=stage1_errors,
            narrative_warnings_in=nlc_warnings,
            source_label=current.get("source") or "claude_unified_chapter_v1",
            enforce_structural_pages=False,
        )
    else:
        outline = None
        nlc_warnings = []

    if not _use_unified_outline:
        # ============================================================
        # Legacy path: Stage 1a stub -> optional skeleton review -> Stage 1b detail.
        # Kept for comparison/rollback. The default path above uses a single
        # Claude call per chapter to avoid context fragmentation.
        # ============================================================
        pass

    # ============================================================
    # v17 C.1a — parallel Stage 1a per chapter (chapter stub only).
    # v35: IDEA_ANALYSIS no longer provides slide_stubs. Stage 1a owns the
    # first slide-level skeleton decision.
    # ============================================================
    stub_results: list[dict] = []
    stage1a_errors: list[str] = []
    MAX_PARALLEL = 4

    with _cf.ThreadPoolExecutor(max_workers=MAX_PARALLEL,
                                  thread_name_prefix="outline_1a") as pool:
        futs = {pool.submit(_process_chapter_stage1a, ch): ch for ch in chapter_plan}
        for fut in _cf.as_completed(futs):
            try:
                r = fut.result()
            except Exception as e:
                ch = futs[fut]
                r = {"chapter_index": ch.get("section_index"), "ok": False,
                     "error": f"executor exception: {e!r}"}
            stub_results.append(r)
            if not r.get("ok"):
                stage1a_errors.append(f"ch{r['chapter_index']}: {r.get('error', '')[:200]}")
    stub_results.sort(key=lambda r: r["chapter_index"] or 0)
    print(f"[OUTLINE] C.1a done: {sum(1 for r in stub_results if r.get('ok'))}/{len(stub_results)} chapters", flush=True)

    # ============================================================
    # v17 C.1b — Codex Skeleton Review (bounded inspector + one redo)
    # ============================================================
    # v6.2 (2026-07-30): codex loop gated by env var. Default off — Claude
    # generates skeleton, immediately accepted. Set OUTLINE_CODEX_LOOP_ENABLED=1 to
    # re-enable the codex review-fix loop (preserved code path).
    import os as _os_outline_codex
    _outline_codex_on = _os_outline_codex.environ.get(
        "OUTLINE_CODEX_LOOP_ENABLED", "0").lower() in {"1", "true", "yes"}
    MAX_SKELETON_REVIEW_ROUNDS = 2 if _outline_codex_on else 0
    skeleton_review_log: list[dict] = []
    for skel_rnd in range(1, MAX_SKELETON_REVIEW_ROUNDS + 1):
        ok_stubs = [r for r in stub_results if r.get("ok")]
        if not ok_stubs:
            break
        skel_payload = {
            "idea_analysis": oc.compact_idea_for_fix(idea),
            "chapter_stubs": [r["stub"] for r in ok_stubs],
            "logic_story_rules_summary": hard_rules,
            "page_specific_archetypes_summary": archetype_for_prompt,
            "round": skel_rnd,
            "prior_issues": (skeleton_review_log[-1].get("issues") if skeleton_review_log else []),
        }
        skel_prompt = (
            f"Review chapter_stubs skeleton (v17 C.1b) round {skel_rnd}. "
            "Check chapter_decomposition / rhythm adherence / cross-chapter coherence / role placement. "
            "Output {ok, round, issues, layer_summary, summary} strict JSON only.\n\n"
            "INPUT:\n" + json.dumps(skel_payload, ensure_ascii=False)
        )
        skel_rev = codex_cli.call_codex_json(
            skel_prompt,
            skill=["skills/outline_gen/outline_skeleton_review.md"],
            timeout=600,
        )
        if not skel_rev.get("ok"):
            diag = {
                "schema_version": "1.0",
                "generated_at": now(),
                "project_id": project_id,
                "error": "OUTLINE Stage 1a skeleton codex inspection failed; stage is blocked because skeleton inspection is required.",
                "codex_error": skel_rev.get("error"),
                "chapter_stubs": [r.get("stub") for r in stub_results if r.get("ok")],
                "review_log": skeleton_review_log,
            }
            write_json(pdir / "outline-skeleton-diagnostics.json", diag)
            return {"ok": False, "stage": "OUTLINE_GENERATION",
                    "outline_diagnostics": str(pdir / "outline-skeleton-diagnostics.json"),
                    "error": (f"Codex inspection failed for OUTLINE Stage 1a skeleton: "
                              f"{(skel_rev.get('error') or '')[:300]}")}
        rdata = skel_rev.get("data") or {}
        rdata["round"] = skel_rnd
        skeleton_review_log.append(rdata)
        issues = rdata.get("issues") or []
        n_ch = sum(1 for i in issues if isinstance(i, dict) and i.get("severity") in ("critical", "high"))
        print(f"[OUTLINE] C.1b rnd{skel_rnd}: ok={rdata.get('ok')}, issues={len(issues)} (crit/high={n_ch})", flush=True)
        if rdata.get("ok") and n_ch == 0:
            break
        if skel_rnd >= MAX_SKELETON_REVIEW_ROUNDS:
            print(f"[OUTLINE] C.1b reached bounded review limit "
                  f"({MAX_SKELETON_REVIEW_ROUNDS} rounds); unresolved "
                  f"critical/high skeleton issues will block", flush=True)
            break
        # Dispatch: redo Stage 1a for affected chapters
        redo_chs = list({iss.get("target_chapter_index") for iss in issues
                          if iss.get("severity") in ("critical", "high")
                          and iss.get("fix_target_layer") in {"chapter_decomposition", "chapter_rhythm", "stub_polish"}
                          and iss.get("target_chapter_index")})
        print(f"[OUTLINE] C.1b rnd{skel_rnd} → redo Stage 1a for chapters {redo_chs}", flush=True)
        for ch_idx_redo in redo_chs:
            chapter = next((c for c in chapter_plan if c.get("section_index") == ch_idx_redo), None)
            if not chapter:
                continue
            ch_hints = [
                {"category": iss.get("category"),
                 "explanation": iss.get("explanation"),
                 "suggested_fix": iss.get("suggested_fix")}
                for iss in issues
                if iss.get("target_chapter_index") == ch_idx_redo
            ]
            chapter_with_hint = dict(chapter)
            chapter_with_hint["_skeleton_review_hints"] = ch_hints
            chapter_with_hint["_skeleton_redo_round"] = skel_rnd
            new_stub_res = _process_chapter_stage1a(chapter_with_hint)
            if new_stub_res.get("ok"):
                # replace in stub_results
                for i, sr in enumerate(stub_results):
                    if sr.get("chapter_index") == ch_idx_redo:
                        stub_results[i] = new_stub_res
                        break

    if skeleton_review_log:
        _last_skel = skeleton_review_log[-1] or {}
        _skel_blocking = [
            i for i in (_last_skel.get("issues") or [])
            if isinstance(i, dict) and i.get("severity") in ("critical", "high")
        ]
        if _skel_blocking:
            diag = {
                "schema_version": "1.0",
                "generated_at": now(),
                "project_id": project_id,
                "error": "OUTLINE Stage 1a skeleton blocked by unresolved critical/high review issues after one redo attempt.",
                "blocking_issues": _skel_blocking,
                "chapter_stubs": [r.get("stub") for r in stub_results if r.get("ok")],
                "review_log": skeleton_review_log,
            }
            write_json(pdir / "outline-skeleton-diagnostics.json", diag)
            return {"ok": False, "stage": "OUTLINE_GENERATION",
                    "outline_diagnostics": str(pdir / "outline-skeleton-diagnostics.json"),
                    "error": (f"bounded skeleton inspection: {len(_skel_blocking)} "
                              "critical/high Stage 1a issues remain after one redo; "
                              "not proceeding to Stage 1b."),
                    "blocking_issues": _skel_blocking[:20]}

    # Write skeleton review log
    if skeleton_review_log:
        write_json(pdir / "outline-skeleton-review.json", {
            "schema_version": "v17.0",
            "generated_at": now(),
            "rounds": skeleton_review_log,
            "final_ok": (skeleton_review_log[-1].get("ok") if skeleton_review_log else False),
        })

    # ============================================================
    # v17 C.2 — parallel Stage 1b per chapter (section-first retrieval)
    # ============================================================
    chapter_results: list[dict] = []
    stage1_errors: list[str] = list(stage1a_errors)
    ok_stubs_for_1b = [r for r in stub_results if r.get("ok")]
    with _cf.ThreadPoolExecutor(max_workers=MAX_PARALLEL,
                                  thread_name_prefix="outline_1b") as pool:
        futs = {}
        for sr in ok_stubs_for_1b:
            ch = next((c for c in chapter_plan if c.get("section_index") == sr["chapter_index"]), None)
            if ch:
                futs[pool.submit(_process_chapter_stage1b, ch, sr["stub"])] = sr
        for fut in _cf.as_completed(futs):
            try:
                r = fut.result()
            except Exception as e:
                sr = futs[fut]
                r = {"chapter_index": sr["chapter_index"], "ok": False,
                     "error": f"executor exception: {e!r}",
                     "stub": sr.get("stub")}
            chapter_results.append(r)
            if not r.get("ok"):
                stage1_errors.append(f"ch{r['chapter_index']}: {r.get('error', '')[:200]}")
    # add failed 1a stub_results too
    for sr in stub_results:
        if not sr.get("ok"):
            chapter_results.append(sr)
    chapter_results.sort(key=lambda r: r["chapter_index"] or 0)
    ok_count = sum(1 for r in chapter_results if r.get("ok"))
    print(f"[OUTLINE] stage 1 done in {_time.time()-t_stage1:.1f}s, "
          f"{ok_count}/{len(chapter_results)} chapters OK", flush=True)

    if ok_count == 0:
        return {
            "ok": False, "stage": "OUTLINE_GENERATION",
            "error": "Stage 1 produced 0 OK chapters; " + "; ".join(stage1_errors)[:600],
            "retry_hint": "重跑 OUTLINE_GENERATION 或检查 idea-analysis.chapter_plan",
        }

    # Persist stage 1 intermediate
    write_json(pdir / "outline-chapter-stubs.json", {
        "schema_version": "1.0",
        "generated_at": now(),
        "chapter_stubs": [r.get("stub") for r in chapter_results if r.get("ok")],
        "stage1_errors": stage1_errors,
    })

    # ============================================================
    # Code merge: per-chapter slides → flat outline.slides with absolute slide_index
    # ============================================================
    per_chapter_slides = []
    for r in chapter_results:
        if not r.get("ok"):
            continue
        ds = dict(r["detail"])
        ds["chapter_index"] = r["chapter_index"]
        stub = r.get("stub") or {}
        if "rhythm_adherence" in stub:
            ds["rhythm_adherence"] = stub["rhythm_adherence"]
        per_chapter_slides.append(ds)

    merged = oc.merge_chapter_outlines(per_chapter_slides)

    # v30 fix: Stage 1b (outline_slide_detail.md) writes the classifier as `kind`,
    # but all downstream driver logic (Plan-A sweep, hard-prune, SLIDE_PLAN reuse
    # decision, slide-matches synthesis) keys off `source_carrier_resource_kind`.
    # Without this normalization, 30/39 slides end up with `source_carrier_resource_kind=None`
    # even though they have library-backed source_resource_ids, and SLIDE_PLAN
    # treats them as placeholder → byte-clone never fires → most pages come out
    # blank. Copy `kind` → `source_carrier_resource_kind` where the latter is
    # missing so all downstream consumers see the same classification.
    for _s in merged.get("slides") or []:
        if not _s.get("source_carrier_resource_kind") and _s.get("kind"):
            _s["source_carrier_resource_kind"] = _s["kind"]

    # ============================================================
    # v4.0: aggregate chapter_realized from per-chapter detail outputs
    # (IDEA gave abstract intent; OUTLINE realized it with concrete tech names)
    # ============================================================
    chapter_realized_list = []
    for r in chapter_results:
        if not r.get("ok"):
            continue
        det = r.get("detail") or {}
        # v30 fix: some Stage 1b outputs return chapter_realized as a plain string
        # (e.g. a one-line summary). Only accept dict; else keep {} so downstream
        # cr.get() calls don't crash with AttributeError.
        _cr_raw = det.get("chapter_realized")
        cr = _cr_raw if isinstance(_cr_raw, dict) else {}
        intent = ""
        for ch in chapter_plan:
            if ch.get("section_index") == r["chapter_index"]:
                claims = ch.get("claims_to_make") or []
                intent = "; ".join(claims[:2])[:120] if claims else ""
                break
        chapter_realized_list.append({
            "chapter_index": r["chapter_index"],
            "summary": cr.get("summary") or "",
            "realized_specifics": cr.get("realized_specifics") or [],
            "coverage_status": cr.get("coverage_status") or "",
            "subline_coverage": cr.get("subline_coverage") or [],
            "drift_from_intent": cr.get("drift_from_intent") or {
                "abstract_intent": intent,
                "missing_from_source": [],
                "added_from_source": [],
                "drift_severity": "unknown",
            },
        })

    # Inherit selected_narrative_arc (primary_pattern_id) from IDEA for md rendering
    sna = idea.get("selected_narrative_arc") or {}
    outline = {
        "schema_version": "1.0",
        "generated_at": now(),
        "source": "claude_two_stage_v40",
        "identity": idea.get("identity"),
        "topic": (idea.get("identity") or {}).get("topic"),
        "language": (idea.get("identity") or {}).get("language") or "zh",
        "slide_count": len(merged["slides"]),
        "user_outline_applied": False,
        "slides": merged["slides"],
        "chapter_to_slide_map": merged["chapter_to_slide_map"],
        "rhythm_adherence_log": merged["rhythm_adherence_log"],
        "chapter_realized": chapter_realized_list,
        # Inherit selected_narrative_arc (so outline.md can show "模板: <pattern_id>")
        "selected_narrative_arc": {
            "primary_pattern_id": sna.get("primary_pattern_id"),
            "borrowed_patterns": sna.get("borrowed_patterns") or [],
            "narrative_arc": sna.get("narrative_arc"),
        },
        # Inherit user_concern_history from IDEA (Cat 10 cross-stage guard)
        "user_concern_history": idea.get("user_concern_history") or [],
        "provenance": {
            "schema_version": "1.0",
            "idea_analysis_path": "idea-analysis.json",
            "rule_relaxed_with_reason": [],
        },
    }
    outline = _normalize_outline_chapter_links(outline, chapter_plan)
    outline = _enforce_outline_structural_pages(outline, phase="outline_main_path")
    # Soft-warning narrative check (legacy helper, still useful)
    nlc_warnings = _check_outline_against_narrative(
        slides=outline["slides"], narrative_block=nc)
    if nlc_warnings:
        outline["narrative_warnings"] = nlc_warnings
        for w in nlc_warnings:
            print(f"[OUTLINE narrative] {w}", flush=True)

    # ============================================================
    # Stage 2: Codex review + at most one surgical fix.
    # Codex is an inspector/gate. Claude generation prompts should produce a
    # valid outline before review; this loop is not a creative optimizer.
    # 大 loop (人类 gate) handled by _run_outline_human_fix_round in a separate
    # entry — this loop only handles codex issues.
    # ============================================================
    review_log: list[dict] = []
    final_review: dict | None = None
    MAX_REVIEW_ROUNDS = 2 if _outline_codex_on else 0
    current = outline

    # Load pattern bodies once for surgical fix skill (idea + chapter_plan are
    # frozen for Stage 2 — pattern bodies won't change across fix rounds)
    primary_pid = ((idea.get("selected_narrative_arc") or {}).get("primary_pattern_id"))
    selected_pattern_body = (oc.load_deck_level_pattern_full(primary_pid)
                             if primary_pid else None)
    rhythm_bodies: dict = {}
    for _ch in chapter_plan:
        _rpid = _ch.get("section_rhythm_pattern_id") if isinstance(_ch, dict) else None
        if _rpid and _rpid not in rhythm_bodies:
            _b = oc.load_rhythm_pattern_trimmed(_rpid)
            if _b:
                rhythm_bodies[_rpid] = _b

    def _outline_source_id(slide: dict) -> str | None:
        refs = slide.get("source_resource_ids") or []
        if not refs:
            return None
        first = refs[0]
        if isinstance(first, dict):
            return first.get("slide_id")
        if isinstance(first, str):
            return first
        return None

    def _outline_archetype_text(slide: dict) -> str:
        arch = slide.get("archetype") or []
        if isinstance(arch, list):
            arch_text = " ".join(str(x) for x in arch)
        else:
            arch_text = str(arch)
        return " ".join([
            arch_text,
            slide.get("target_role") or "",
            slide.get("archetype_placement") or "",
            slide.get("target_title") or "",
            slide.get("target_claim") or "",
        ])

    _outline_source_brief_cache: dict[str, dict] = {}

    def _outline_source_brief(slide: dict) -> dict:
        sid = _outline_source_id(slide)
        if not sid:
            return {}
        if sid not in _outline_source_brief_cache:
            try:
                briefs = oc.load_slide_briefs_by_ids([sid])
            except Exception:
                briefs = []
            _outline_source_brief_cache[sid] = briefs[0] if briefs else {}
        return _outline_source_brief_cache.get(sid) or {}

    def _brief_text(brief: dict, *keys: str) -> str:
        parts: list[str] = []
        for key in keys:
            value = brief.get(key)
            if isinstance(value, list):
                parts.extend(str(v) for v in value if v)
            elif value:
                parts.append(str(value))
        return " ".join(parts)

    def _is_navigation_source(brief: dict) -> bool:
        role = str(brief.get("页面角色") or "").lower()
        text = _brief_text(
            brief, "标题", "本页讲什么", "核心论断", "适合复用场景", "视觉骨架"
        ).lower()
        nav_terms = (
            "toc", "contents", "agenda", "outline",
            "目录", "议程", "提纲", "章节切换", "章节过渡",
            "进度导航", "高亮当前", "当前章", "进入第",
        )
        return (
            role in {"toc_candidate", "cover_candidate", "ending_candidate", "references"}
            or any(t in text for t in nav_terms)
        )

    def _is_personal_or_single_work_deck(brief: dict) -> bool:
        page_role = str(brief.get("页面角色") or "").lower()
        deck_id = str(brief.get("deck_id") or "")
        if page_role in {"cover_candidate", "toc_candidate", "ending_candidate"}:
            return False
        if "通用模板" in deck_id or "模板" in str(brief.get("deck_title") or ""):
            return False
        text = _brief_text(
            brief, "deck_id", "deck_title", "标题", "本页讲什么", "适合复用场景"
        )
        markers = (
            "个人", "博士资格", "资格考试", "开题", "中期", "答辩",
            "论文分享", "paper_share", "单篇", "学生",
        )
        return any(m in text for m in markers)

    def _is_overview_target(slide: dict) -> bool:
        role = (slide.get("target_role") or "").lower()
        text = _outline_archetype_text(slide)
        markers = (
            "总纲", "全局", "课题组", "团队", "组织", "三层协同", "主线",
            "导航骨架", "总体", "整体", "研究脉络", "recap", "收束",
            "范式", "三层坐标",
        )
        return role in {"framework", "framework_recap", "outlook", "closing"} and any(m in text for m in markers) \
            or role in {"framework", "framework_recap"} \
            or any(m in text for m in markers)

    def _is_narrow_source_for_framework(brief: dict) -> bool:
        if not brief:
            return False
        role_in_section = str(brief.get("页在section中的作用") or "").lower()
        page_role = str(brief.get("页面角色") or "").lower()
        text = _brief_text(brief, "deck_id", "deck_title", "标题", "核心论断", "本页讲什么", "适合复用场景")
        narrow_terms = (
            "specee", "flashoverlap", "semi-pd", "endor", "flightllm", "flightvgm",
            "tb-stc", "spec", "早退", "投机", "fpga", "单个工作", "论文",
            "通信重叠", "sm 分区",
            "单篇", "summary:flightvgm", "summary：目标", "目标—洞察—方案",
            "首个 fpga", "tensor core", "张量核",
        )
        overview_terms = ("框架", "总纲", "overview", "全局", "三层", "taxonomy", "路线图")
        text_low = text.lower()
        if page_role in {"toc_candidate", "cover_candidate", "ending_candidate", "references"}:
            return False
        # True global/team framework sources are allowed. Single-work summaries
        # often contain "Summary" and diagrams but still have named-work scope.
        named_work = any(t in text_low for t in (
            "specee", "specdiff", "flashoverlap", "semi-pd", "endor",
            "flightllm", "flightvgm", "tb-stc", "hpca", "isca", "date",
        ))
        if not named_work and (any(t in text_low for t in ("overview", "taxonomy"))
                               or any(t in text for t in overview_terms)):
            return False
        return role_in_section in {"method_detail", "result", "worker_intro", "closer"} and named_work \
            or any(t in text_low for t in narrow_terms)

    def _extract_work_names(text: str) -> set[str]:
        import re as _re_work
        names = set()
        for m in _re_work.findall(r"\b[A-Z][A-Za-z0-9+\-]{2,}\b", text or ""):
            if m.upper() in {"GPU", "CPU", "FPGA", "ASIC", "LLM", "KV", "SM", "PD", "AI"}:
                continue
            names.add(m)
        known = ("SpecEE", "FlashOverlap", "Semi-PD", "Endor", "FlightLLM", "FlightVGM", "TB-STC")
        low = (text or "").lower()
        for k in known:
            if k.lower() in low:
                names.add(k)
        return names

    def _outline_stage_labels(block: list[dict]) -> list[str]:
        labels: list[str] = []
        for i, slide in enumerate(block):
            text = _outline_archetype_text(slide).lower()
            title = slide.get("target_title") or ""
            role = (slide.get("target_role") or "").lower()
            if i == 0 or "paper_intro" in text or "work_intro" in text or "代表工作" in title:
                label = "opener"
            elif any(k in title for k in ("挑战", "问题", "痛点", "瓶颈")) or "challenge" in text or "pain" in text:
                label = "challenge"
            elif role in {"result", "experiment", "benchmark"} or any(k in title for k in ("效果", "结果", "性能", "小结")):
                label = "result"
            elif any(k in title for k in ("方法", "方案", "设计", "实现", "架构")) or "method" in text or "approach" in text:
                label = "method"
            else:
                label = role or "other"
            if label not in labels:
                labels.append(label)
        return labels

    def _outline_structural_rule_issues(outline_doc: dict) -> list[dict]:
        """Driver-side enforcement for v34 logic_story outline rules.

        Codex still performs semantic review, but these deterministic checks
        guarantee that source-binding and repeated chapter rhythm problems are
        converted into concrete fix issues before GAP_CARD_GENERATION.
        """
        slides = [s for s in (outline_doc.get("slides") or []) if isinstance(s, dict)]
        issues_out: list[dict] = []
        seen_keys: set[tuple] = set()

        def add_issue(issue: dict) -> None:
            key = (
                issue.get("category"),
                issue.get("target_slide_index"),
                issue.get("target_chapter_index"),
                issue.get("evidence"),
            )
            if key in seen_keys:
                return
            seen_keys.add(key)
            issue.setdefault("source", "driver_structural_rule")
            issue.setdefault("_driver_synthesized", True)
            issue.setdefault("_source_check", "v34_logic_story_structural_rules")
            issues_out.append(issue)

        slides_by_ch: dict[int, list[dict]] = {}
        for slide in slides:
            try:
                ci = int(slide.get("chapter_index") or slide.get("section_index") or 0)
            except Exception:
                continue
            if ci <= 0:
                continue
            slides_by_ch.setdefault(ci, []).append(slide)
        for ch_slides in slides_by_ch.values():
            ch_slides.sort(key=lambda s: int(s.get("slide_index") or 0))

        # 1. Weak/fallback/new bindings are not final outline states.
        for slide in slides:
            try:
                si = int(slide.get("slide_index"))
            except Exception:
                continue
            ci = slide.get("chapter_index")
            kind = (slide.get("source_carrier_resource_kind") or slide.get("kind") or "").lower()
            gap = (slide.get("gap_status") or "").lower()
            refs = slide.get("source_resource_ids") or []
            weak = (
                kind in {"matching_fallback", "new", "no_supporting_material"}
                or "weak" in gap
                or "no_match" in gap
                or "not_applicable" in gap
                or not refs
            )
            if not weak:
                continue
            add_issue({
                "layer": "L1",
                "category": "weak_or_fallback_source_binding",
                "severity": "critical" if not refs or kind == "new" else "high",
                "location": f"slides[slide_index={si}].source_resource_ids",
                "target_slide_index": si,
                "target_chapter_index": ci,
                "fix_target_layer": "source_matching" if refs else "outline_decomposition",
                "evidence": f"slide {si} kind={kind}, gap_status={gap}, source_count={len(refs)}",
                "explanation": "matching_fallback/weak/new 只能作为 OUTLINE review 信号, 不能进入最终 byte-clone outline.",
                "suggested_fix": "优先从 alternates 或 chapter-wide cascade 改绑强匹配真实源; 无强源则改 target_claim 到源页真实语义, 再不成立就删页或回滚 chapter_decomposition.",
            })

        # 2. Distinct same-chapter target pages should not reuse one source.
        for ci, ch_slides in slides_by_ch.items():
            by_src: dict[str, list[dict]] = {}
            for slide in ch_slides:
                sid = _outline_source_id(slide)
                if sid:
                    by_src.setdefault(sid, []).append(slide)
            for sid, dup_slides in by_src.items():
                if len(dup_slides) < 2:
                    continue
                allowed = all(
                    isinstance(s.get("same_source_intent"), dict)
                    and (s.get("same_source_intent") or {}).get("allowed") is True
                    for s in dup_slides
                )
                if allowed:
                    continue
                indices = [int(s.get("slide_index") or 0) for s in dup_slides]
                roles = [(s.get("target_role") or "") for s in dup_slides]
                titles = [(s.get("target_title") or "")[:40] for s in dup_slides]
                adjacent = any((b - a) == 1 for a, b in zip(sorted(indices), sorted(indices)[1:]))
                any_weak = any(
                    (s.get("source_carrier_resource_kind") or "").lower() == "matching_fallback"
                    or "weak" in ((s.get("gap_status") or "").lower())
                    for s in dup_slides
                )
                add_issue({
                    "layer": "L1",
                    "category": "duplicate_source_within_chapter",
                    "severity": "critical" if adjacent or any_weak else "high",
                    "location": f"chapter[{ci}].slides",
                    "target_chapter_index": ci,
                    "target_slide_index": indices[0],
                    "fix_target_layer": "source_matching",
                    "evidence": f"ch{ci} slides {indices} reuse source {sid}; roles={roles}; titles={titles}",
                    "explanation": "不同目标页复用同一 top-1 source 会在 byte-clone 草稿中形成重复页, 除非显式 same_source_intent.",
                    "suggested_fix": "保留最贴合的一页; 其他重复页改绑 alternate/cascade source. 无真实源则合并/删除较弱目标页或改 claim 到源页真实语义.",
                })

        # 3. Structural pages should bind structural source slides.
        structural_roles = {
            "chapter_divider", "section_divider", "agenda", "framework_recap",
            "cover", "closing", "references",
        }
        content_markers = (
            "方法", "效果", "结果", "挑战", "痛点", "论文", "代表工作",
            "算法优化", "压缩", "稀疏", "量化", "FPGA", "TB-STC",
        )
        for slide in slides:
            role = (slide.get("target_role") or "").lower()
            if role not in structural_roles:
                continue
            audit = slide.get("slide_binding_audit") or {}
            source_layer = (audit.get("source_layer_inferred") or "").lower()
            match_reasons = []
            for ref in (slide.get("source_resource_ids") or []):
                if isinstance(ref, dict):
                    match_reasons.extend(str(x) for x in (ref.get("match_reasons") or []))
            evidence_text = " ".join([
                source_layer,
                " ".join(match_reasons),
                " ".join(str(e.get("content") or "") for e in (slide.get("needed_evidence") or []) if isinstance(e, dict)),
            ])
            has_content_signal = any(marker.lower() in evidence_text.lower() for marker in content_markers)
            if source_layer not in {"algorithm", "system", "hardware"} and not has_content_signal:
                continue
            try:
                si = int(slide.get("slide_index"))
            except Exception:
                si = slide.get("slide_index")
            add_issue({
                "layer": "L1",
                "category": "structural_page_bound_to_content_source",
                "severity": "high",
                "location": f"slides[slide_index={si}].source_resource_ids[0]",
                "target_slide_index": si,
                "target_chapter_index": slide.get("chapter_index"),
                "fix_target_layer": "source_matching",
                "evidence": f"slide {si} role={role}, source_layer={source_layer}, reasons={match_reasons[:2]}",
                "explanation": "结构页绑定了具体内容/方法/结果源页, byte-clone 后视觉语义无法只靠改文字修正.",
                "suggested_fix": "改绑 agenda/framework/closing/references 类结构源页; 若没有结构源, 合并/删除该结构页或把 target_role 改为普通内容页.",
            })

        # 4. Content pages must not bind TOC/navigation/cover/ending sources.
        content_roles = {
            "motivation", "background", "problem", "framework", "method",
            "comparison", "benchmark", "result", "experiment", "engineering",
            "discussion", "outlook", "content", "case_study",
        }
        for slide in slides:
            role = (slide.get("target_role") or "").lower()
            if role not in content_roles:
                continue
            slide_text = " ".join([
                str(slide.get("target_title") or ""),
                str(slide.get("target_claim") or ""),
                str(slide.get("page_purpose") or ""),
                str(slide.get("page_purpose_hint") or ""),
            ])
            if any(t in slide_text.lower() for t in ("contents", "agenda", "outline")) \
                    or any(t in slide_text for t in ("目录", "导览", "进入研究展望章", "进入本章")):
                try:
                    si = int(slide.get("slide_index"))
                except Exception:
                    si = slide.get("slide_index")
                add_issue({
                    "layer": "L1",
                    "category": "content_page_written_as_navigation_page",
                    "severity": "high",
                    "location": f"slides[slide_index={si}]",
                    "target_slide_index": si,
                    "target_chapter_index": slide.get("chapter_index"),
                    "fix_target_layer": "outline_skeleton",
                    "evidence": f"slide {si} role={role}, title='{slide.get('target_title')}', claim='{slide.get('target_claim')}'",
                    "explanation": "内容页自身被写成目录/导览页; deck 已有总目录和章前分目录, 正文页必须承担真实论点.",
                    "suggested_fix": "回 Stage 1a/1b 把该页改成真实内容页: 趋势/问题/代表工作 opener/challenge/method/result.",
                })
            brief_src = _outline_source_brief(slide)
            if not _is_navigation_source(brief_src):
                continue
            try:
                si = int(slide.get("slide_index"))
            except Exception:
                si = slide.get("slide_index")
            add_issue({
                "layer": "L1",
                "category": "content_page_bound_to_navigation_source",
                "severity": "critical",
                "location": f"slides[slide_index={si}].source_resource_ids[0]",
                "target_slide_index": si,
                "target_chapter_index": slide.get("chapter_index"),
                "fix_target_layer": "source_matching",
                "evidence": (
                    f"slide {si} role={role}, target='{slide.get('target_title')}', "
                    f"source_role={brief_src.get('页面角色')}, source_title={brief_src.get('标题')}"
                ),
                "explanation": "内容页绑定了目录/导航/封面/结尾源页, byte-clone 后会出现目录页冒充正文的问题.",
                "suggested_fix": "改绑真实内容源页; 若只是章内导航, 把 target_role 改为 section_divider 并放在内容章之前.",
            })

        # 5. Overview/framework pages must use source with matching owner/object scope.
        for slide in slides:
            if not _is_overview_target(slide):
                continue
            brief_src = _outline_source_brief(slide)
            try:
                si = int(slide.get("slide_index"))
            except Exception:
                si = slide.get("slide_index")
            if _is_personal_or_single_work_deck(brief_src):
                add_issue({
                    "layer": "L1",
                    "category": "overview_source_identity_mismatch",
                    "severity": "critical",
                    "location": f"slides[slide_index={si}].source_resource_ids[0]",
                    "target_slide_index": si,
                    "target_chapter_index": slide.get("chapter_index"),
                    "fix_target_layer": "source_matching",
                    "evidence": (
                        f"slide {si} overview target='{slide.get('target_title')}', "
                        f"source_deck={brief_src.get('deck_title') or brief_src.get('deck_id')}, "
                        f"source_title={brief_src.get('标题')}"
                    ),
                    "explanation": "课题组/全局总领页不能直接复用个人答辩、学生计划或单篇论文的总纲页.",
                    "suggested_fix": "改绑课题组/全局汇报级 overview source; 若该源只适合个人工作, 降级为某个具体代表工作内容页.",
                })
            if (slide.get("target_role") or "").lower() in {"framework", "framework_recap"} \
                    and _is_narrow_source_for_framework(brief_src):
                add_issue({
                    "layer": "L1",
                    "category": "framework_source_scope_too_narrow",
                    "severity": "high",
                    "location": f"slides[slide_index={si}].source_resource_ids[0]",
                    "target_slide_index": si,
                    "target_chapter_index": slide.get("chapter_index"),
                    "fix_target_layer": "source_matching",
                    "evidence": (
                        f"slide {si} framework target='{slide.get('target_title')}', "
                        f"source_role_in_section={brief_src.get('页在section中的作用')}, "
                        f"source_title={brief_src.get('标题')}, source_claim={brief_src.get('核心论断')}"
                    ),
                    "explanation": "framework 页的 source 只覆盖窄技术点/单个工作, 不能抬升为整章或全 deck 主线.",
                    "suggested_fix": "改绑三层框架/总览/taxonomy source; 或把 target_claim 收窄为该 source 真实讲的子内容页.",
                })

        # 6. Method-heavy chapters should share the same intro rhythm.
        method_chapters: dict[int, dict] = {}
        for ci, ch_slides in slides_by_ch.items():
            roles = [(s.get("target_role") or "").lower() for s in ch_slides]
            if not any(r in {"method", "result", "experiment", "engineering", "comparison", "benchmark"} for r in roles):
                continue
            method_chapters[ci] = {
                "has_divider": any(r in {"chapter_divider", "section_divider"} for r in roles),
                "has_framework": any(r == "framework_recap" for r in roles),
                "first_slide_index": ch_slides[0].get("slide_index") if ch_slides else None,
            }
        canonical_has_divider = any(v["has_divider"] for v in method_chapters.values())
        canonical_has_framework = any(v["has_framework"] for v in method_chapters.values())
        if len(method_chapters) >= 2 and (canonical_has_divider or canonical_has_framework):
            for ci, info in method_chapters.items():
                missing = []
                if canonical_has_divider and not info["has_divider"]:
                    missing.append("chapter_divider")
                if canonical_has_framework and not info["has_framework"]:
                    missing.append("framework_recap")
                if not missing:
                    continue
                add_issue({
                    "layer": "L2",
                    "category": "method_chapter_structural_rhythm_inconsistent",
                    "severity": "high",
                    "location": f"chapter[{ci}].slides",
                    "target_chapter_index": ci,
                    "target_slide_index": info.get("first_slide_index"),
                    "fix_target_layer": "outline_skeleton",
                    "evidence": f"method chapters canonical divider={canonical_has_divider}, framework={canonical_has_framework}; ch{ci} missing={missing}",
                    "explanation": "主体方法章章首节奏不一致; 不能只在部分章节出现章节分隔/框架回顾页.",
                    "suggested_fix": f"回 Stage 1a 重做 ch{ci} skeleton, 补同构 {' + '.join(missing)} 或统一全组章首结构节奏.",
                })

        # 6b. Explicit parallel_group contracts: page budget, skeleton rhythm,
        # and framework-anchor consistency must survive Stage 1b pruning.
        pg_contracts = [
            c for c in (idea.get("parallel_group_contracts") or [])
            if isinstance(c, dict) and c.get("parallel_group_id")
        ]
        for contract in pg_contracts:
            try:
                members = [int(x) for x in (contract.get("member_section_indices") or [])]
            except Exception:
                members = []
            if len(members) < 2:
                continue
            counts = {
                ci: len([
                    s for s in slides_by_ch.get(ci, [])
                    if (s.get("target_role") or "").lower() not in {"cover", "agenda", "toc"}
                ])
                for ci in members
            }
            nonzero_counts = {ci: n for ci, n in counts.items() if n > 0}
            if len(nonzero_counts) >= 2:
                max_count = max(nonzero_counts.values())
                min_count = min(nonzero_counts.values())
                budget = contract.get("canonical_page_budget") or {}
                allowed_pages = int(budget.get("allowed_delta_pages") or 2)
                allowed_ratio = float(budget.get("allowed_delta_ratio") or 0.2)
                if (max_count - min_count) > allowed_pages and (
                    min_count == 0 or (max_count - min_count) / max(1, max_count) > allowed_ratio
                ):
                    add_issue({
                        "layer": "L2",
                        "category": "parallel_chapter_page_budget_asymmetric",
                        "severity": "critical",
                        "location": "chapter_to_slide_map",
                        "target_chapter_index": min(nonzero_counts, key=nonzero_counts.get),
                        "fix_target_layer": "outline_skeleton",
                        "evidence": f"parallel_group={contract.get('parallel_group_id')} page_counts={counts}, allowed_delta_pages={allowed_pages}, allowed_delta_ratio={allowed_ratio}",
                        "explanation": "并列章节页数差距过大; 代表工作章节不应一章完整展开、另一章被压缩成少数页.",
                        "suggested_fix": "回 Stage 1a 用 parallel_group_contract 统一 page_count; 若素材不足, 同步压缩全组 work block 模板或移除不支撑的工作.",
                    })

            # Framework anchor slot: each member should have a non-navigation
            # framework/current-layer page after the section divider.
            anchor_sources: dict[int, str | None] = {}
            for ci in members:
                ch_slides = slides_by_ch.get(ci, [])
                contentish = [
                    s for s in ch_slides
                    if (s.get("target_role") or "").lower() not in {"cover", "agenda", "toc", "section_divider", "chapter_divider"}
                ]
                if not contentish:
                    continue
                first = contentish[0]
                first_text = _outline_archetype_text(first)
                first_brief = _outline_source_brief(first)
                if not _is_overview_target(first):
                    add_issue({
                        "layer": "L2",
                        "category": "parallel_chapter_missing_framework_anchor",
                        "severity": "high",
                        "location": f"chapter[{ci}].slides[0]",
                        "target_chapter_index": ci,
                        "target_slide_index": first.get("slide_index"),
                        "fix_target_layer": "outline_skeleton",
                        "evidence": f"first content slide title={first.get('target_title')}, archetype={first.get('archetype')}",
                        "explanation": "并列方法章首个内容页应复用总框架/当前层定位锚点, 不能直接进入普通内容或具体工作.",
                        "suggested_fix": "Stage 1a 在 section_divider 后补 framework_anchor_current_layer slot, 并在同组章节保持同构.",
                    })
                elif _is_navigation_source(first_brief):
                    add_issue({
                        "layer": "L1",
                        "category": "framework_anchor_bound_to_navigation_source",
                        "severity": "critical",
                        "location": f"slides[slide_index={first.get('slide_index')}].source_resource_ids[0]",
                        "target_chapter_index": ci,
                        "target_slide_index": first.get("slide_index"),
                        "fix_target_layer": "source_matching",
                        "evidence": f"framework anchor title={first.get('target_title')}, source_title={first_brief.get('标题')}",
                        "explanation": "framework anchor 不能绑定目录/导航源页; 它应复用真实总框架 source, 只改当前层高亮.",
                        "suggested_fix": "改绑全局三层框架页; 若没有, 回 Stage 1a 删除该 anchor 或降低为普通内容页.",
                    })
                anchor_sources[ci] = _outline_source_id(first)
            if (contract.get("framework_anchor_policy") or {}).get("same_source_required") and len(anchor_sources) >= 2:
                srcs = {src for src in anchor_sources.values() if src}
                if len(srcs) > 1:
                    add_issue({
                        "layer": "L2",
                        "category": "parallel_framework_anchor_source_inconsistent",
                        "severity": "high",
                        "location": "parallel_group.framework_anchor",
                        "target_chapter_index": next(iter(anchor_sources)),
                        "fix_target_layer": "source_matching",
                        "evidence": f"parallel_group={contract.get('parallel_group_id')} anchor_sources={anchor_sources}",
                        "explanation": "并列章 framework anchor 应复用同一个总框架 source 模板, 只改变当前层高亮/文字.",
                        "suggested_fix": "锁定第一个合格 framework anchor source, 统一改绑同组其他 anchor; 不允许使用目录页或具体工作页冒充.",
                    })

        # 7. Parallel representative-work blocks should share one template and stay on one work.
        opener_terms = ("paper_intro", "work_intro", "case_study_opener", "paper_title", "代表工作")
        for ci, ch_slides in slides_by_ch.items():
            openers: list[dict] = []
            for slide in ch_slides:
                text = _outline_archetype_text(slide)
                if any(term in text for term in opener_terms):
                    openers.append(slide)
            method_like = [
                s for s in ch_slides
                if (s.get("target_role") or "").lower() in {"method", "result", "experiment", "benchmark"}
            ]
            if len(openers) >= 2 and method_like:
                assigned = [
                    s for s in method_like
                    if s.get("belongs_to_subline_index") not in {None, "", 0}
                ]
                if len(assigned) < max(1, len(method_like) // 2):
                    add_issue({
                        "layer": "L1",
                        "category": "method_work_blocks_missing_subline_assignment",
                        "severity": "high",
                        "location": f"chapter[{ci}].slides",
                        "target_chapter_index": ci,
                        "target_slide_index": method_like[0].get("slide_index"),
                        "fix_target_layer": "outline_skeleton",
                        "evidence": (
                            f"ch{ci} method_like={len(method_like)}, "
                            f"assigned_to_subline={len(assigned)}, openers="
                            f"{[s.get('slide_index') for s in openers]}"
                        ),
                        "explanation": "方法章有多个代表工作, 但多数内容页没有 belongs_to_subline_index, 后续无法保证每个 block 同构且不串工作.",
                        "suggested_fix": "回 Stage 1a 为每个代表工作 block 连续分配 belongs_to_subline_index; framework recap/章末总结才允许 null.",
                    })
            if len(openers) < 2:
                continue
            blocks: list[list[dict]] = []
            for i, opener in enumerate(openers):
                start = int(opener.get("slide_index") or 0)
                end = (
                    int(openers[i + 1].get("slide_index") or 0) - 1
                    if i + 1 < len(openers)
                    else int(ch_slides[-1].get("slide_index") or start)
                )
                blocks.append([
                    s for s in ch_slides
                    if start <= int(s.get("slide_index") or 0) <= end
                ])
            lengths = [len(b) for b in blocks]
            sequences = [_outline_stage_labels(b) for b in blocks]
            stage_sets = [set(seq) for seq in sequences]
            critical_stage_mismatch = any(
                stage in stage_sets[0] and any(stage not in ss for ss in stage_sets[1:])
                for stage in {"challenge", "method", "result"}
            ) or any(
                stage not in stage_sets[0] and any(stage in ss for ss in stage_sets[1:])
                for stage in {"challenge", "method", "result"}
            )
            if max(lengths) - min(lengths) <= 1 and not critical_stage_mismatch:
                continue
            opener_indices = [int(s.get("slide_index") or 0) for s in openers]
            add_issue({
                "layer": "L2",
                "category": "parallel_work_blocks_asymmetric",
                "severity": "critical" if critical_stage_mismatch else "high",
                "location": f"chapter[{ci}].slides",
                "target_chapter_index": ci,
                "target_slide_index": opener_indices[0],
                "fix_target_layer": "outline_skeleton",
                "evidence": f"ch{ci} work openers={opener_indices}, block_lengths={lengths}, sequences={sequences}",
                "explanation": "同章代表工作必须用同一叙事模板展开, 不能一个工作有 method/result, 另一个缺关键段.",
                "suggested_fix": "统一 work-block 模板: opener→challenge→method→result 或统一压缩为 opener→challenge→result; 无源支撑时同步压缩或移出并列组.",
            })

            for block in blocks:
                names_by_slide: list[tuple[int, set[str]]] = []
                for bslide in block:
                    bbrief = _outline_source_brief(bslide)
                    text = " ".join([
                        _outline_archetype_text(bslide),
                        _brief_text(bbrief, "标题", "核心论断", "本页讲什么"),
                    ])
                    names = _extract_work_names(text)
                    if names:
                        names_by_slide.append((int(bslide.get("slide_index") or 0), names))
                if len(names_by_slide) < 2:
                    continue
                anchor_names = set(names_by_slide[0][1])
                drift = [
                    (idx, sorted(names))
                    for idx, names in names_by_slide[1:]
                    if anchor_names.isdisjoint(names)
                ]
                if not drift:
                    continue
                add_issue({
                    "layer": "L2",
                    "category": "work_block_source_drift",
                    "severity": "high",
                    "location": f"chapter[{ci}].slides",
                    "target_chapter_index": ci,
                    "target_slide_index": names_by_slide[0][0],
                    "fix_target_layer": "source_matching",
                    "evidence": f"ch{ci} block work names by slide={[(i, sorted(n)) for i, n in names_by_slide]}, drift={drift}",
                    "explanation": "同一代表工作 block 内 source/target 工作名发生跳变, 会出现讲第三个工作后突然回到第一个工作的逻辑错误.",
                    "suggested_fix": "同一 block 内改绑同一工作连续 source slides; 若要切换工作, 必须新建 opener 并采用同构 block.",
                })

        return issues_out

    for rnd in range(1, MAX_REVIEW_ROUNDS + 1):
        # v17 C.3: driver 主动跑 chapter-wide cascade for new candidates per round.
        # These candidates are shown to codex so it can suggest add/replace/delete.
        chapter_wide_cascade: list[dict] = []
        try:
            for ch in chapter_plan:
                ci = ch.get("section_index")
                role = (ch.get("section_role") or "").lower()
                if role in {"opening", "cover", "closing", "agenda", "framework"}:
                    continue  # skip structural chapters
                # Collect current chapter's already-selected slide_ids
                cur_slides = [s for s in (current.get("slides") or []) if s.get("chapter_index") == ci]
                already = set()
                for sl in cur_slides:
                    for r in (sl.get("source_resource_ids") or []):
                        if isinstance(r, dict) and r.get("slide_id"):
                            already.add(r["slide_id"])
                        elif isinstance(r, str):
                            already.add(r)
                    for r in (sl.get("alternates") or []):
                        if isinstance(r, dict) and r.get("slide_id"):
                            already.add(r["slide_id"])
                        elif isinstance(r, str):
                            already.add(r)
                # Chapter-level abstract topics + realized_specifics for keyword pool
                cr = next((c for c in (current.get("chapter_realized") or []) if c.get("chapter_index") == ci), {})
                topics = list(cr.get("realized_specifics") or [])
                # Also collect subline abstract_topics
                stub_for_ch = next((r for r in chapter_results if r.get("chapter_index") == ci), {})
                decomp = ((stub_for_ch.get("stub") or {}).get("chapter_decomposition") or {})
                for sl in (decomp.get("sublines") or []):
                    topics.extend(sl.get("abstract_topics") or [])
                    if sl.get("name"):
                        topics.append(sl["name"])
                if not topics:
                    continue
                # v30 fix: extract bare work names (e.g. "FlightLLM") from
                # compound phrases + slides' actual target_claim so cascade
                # hits work-specific slides
                import re as _bre
                _bare_re = _bre.compile(r'[A-Z][A-Za-z0-9\-\+]{2,}(?:\-[A-Za-z0-9\+]{1,})*')
                _EXCLUDE = {"KV", "EP", "PD", "II", "LLM", "GPU", "FPGA",
                             "TPU", "CPU", "MoE", "AI", "MLP"}
                _bare: list[str] = []
                _pool_text = " ".join(topics)
                # Also mine cur_slides for target work names
                for sl in cur_slides:
                    _pool_text += " " + (sl.get("target_title") or "")
                    _pool_text += " " + (sl.get("target_claim") or "")
                for _m in _bare_re.findall(_pool_text):
                    if _m not in _EXCLUDE and _m not in _bare:
                        _bare.append(_m)
                topics = _bare + topics
                ch_layer = oc.infer_chapter_layer(ch)
                cascade = oc.cascade_search_for_gap(
                    keywords=topics[:12],
                    layer=ch_layer if ch_layer != "other" else None,
                    role_hint=ch.get("section_role"),
                    exclude_slide_ids=list(already),
                    max_decks=5, max_sections=6, max_slides=8,
                )
                new_ones = cascade.get("slides") or []
                if new_ones:
                    chapter_wide_cascade.append({
                        "chapter_index": ci,
                        "chapter_title": ch.get("chapter"),
                        "new_candidates": [
                            {
                                "slide_id": b.get("slide_id"),
                                "deck_id": b.get("deck_id"),
                                "标题": b.get("标题"),
                                "核心论断": b.get("核心论断"),
                                "section_role": b.get("section_role"),
                                "inferred_layer": b.get("inferred_layer"),
                                "_score": b.get("_score"),
                            } for b in new_ones[:6]
                        ],
                    })
            print(f"[OUTLINE] rnd{rnd} chapter-wide cascade: found new candidates in "
                  f"{len(chapter_wide_cascade)} chapters", flush=True)
        except Exception as e:
            print(f"[OUTLINE] rnd{rnd} chapter-wide cascade failed: {e}", flush=True)

        review_input = {
            "outline": current,
            "idea_analysis": idea,
            "intake_light": intake,
            "page_specific_rules_summary": archetype_for_prompt,
            "logic_story_hard_rules_summary": hard_rules,
            "round": rnd,
            "prior_issues": (review_log[-1].get("issues") if review_log else []),
            "user_concern_history": current.get("user_concern_history", []),
            # v17 C.3: chapter-wide new candidates for L2-9/L2-10
            "chapter_wide_cascade_candidates": chapter_wide_cascade,
            # v17 fix P5: expose narrative check warnings so codex can dispatch narrative_polish
            "narrative_warnings": current.get("narrative_warnings") or [],
        }
        review_prompt = (
            f"Review outline.json round {rnd}. v17 出 issue 时**必须**给 fix_target_layer "
            "(outline_decomposition / outline_skeleton / source_matching / add_new_source / narrative_polish). "
            "L2-9/L2-10 用 chapter_wide_cascade_candidates 判断加/换/删 slide. "
            "Output {ok, round, issues, summary} strict JSON only.\n\nINPUT:\n"
            + json.dumps(review_input, ensure_ascii=False)
        )
        rev = codex_cli.call_codex_json(
            review_prompt,
            skill=["skills/outline_gen/outline_review.md"],
            timeout=600,
        )
        if not rev.get("ok"):
            diag = {
                "schema_version": "1.0",
                "generated_at": now(),
                "project_id": project_id,
                "error": "OUTLINE_GENERATION codex inspection failed; stage is blocked because final inspection is required.",
                "codex_error": rev.get("error"),
                "review_log": review_log,
                "outline_draft": current,
            }
            write_json(pdir / "outline-review-diagnostics.json", diag)
            return {"ok": False, "stage": "OUTLINE_GENERATION",
                    "outline_diagnostics": str(pdir / "outline-review-diagnostics.json"),
                    "error": (f"Codex inspection failed for OUTLINE_GENERATION: "
                              f"{(rev.get('error') or '')[:300]}")}
        rdata = rev.get("data") or {}
        rdata["round"] = rnd
        review_log.append(rdata)
        final_review = rdata
        issues = list(rdata.get("issues") or [])

        # v4.4 driver-side safety net: codex may forget to scan chapter_realized.
        # Inject synthetic L2-8 issues based on coverage_status — guarantees
        # decomposition redo when subline/critical_missing is reported by Stage 1b.
        # Structural roles (opening/cover/closing/agenda/framework) never trigger redo
        # even if Stage 1b LLM mis-reports coverage_status.
        STRUCTURAL_ROLES = {"opening", "cover", "closing", "agenda", "framework", "section_divider", "references"}
        ch_role_by_idx = {
            (c.get("section_index") if isinstance(c, dict) else None):
                (c.get("section_role") or "").lower()
            for c in (chapter_plan or [])
        }
        for cr in (current.get("chapter_realized") or []):
            cs = (cr.get("coverage_status") or "").lower()
            ci = cr.get("chapter_index")
            role = ch_role_by_idx.get(ci, "")
            if role in STRUCTURAL_ROLES:
                # Structural chapters never trigger decomp redo
                if cs in {"critical_missing", "subline_missing"}:
                    print(f"[OUTLINE] ch{ci} role={role} reported {cs} but treated as not_applicable (driver guard)", flush=True)
                continue
            if cs == "critical_missing":
                missing_names = [s.get("subline_name") for s in (cr.get("subline_coverage") or [])
                                  if s.get("coverage") == "missing"]
                issues.append({
                    "layer": "L2",
                    "category": "chapter_decomposition_misaligned",
                    "severity": "critical",
                    "location": f"chapter_realized[ch={ci}]",
                    "target_chapter_index": ci,
                    "fix_target_layer": "outline_decomposition",
                    "evidence": f"ch{ci} coverage_status=critical_missing, missing sublines={missing_names}",
                    "explanation": "Stage 1b 自报该章 critical_missing (≥50% subline 无 source 或 ≥60% slide kind=new), 资源库不支持当前 chapter_decomposition.",
                    "suggested_fix": f"回 Stage 1a 重做 ch{ci} chapter_decomposition: 砍掉 subline {missing_names} 或换 axis 为资源库实际有的方向. 整章页数同步缩减.",
                    "_driver_synthesized": True,
                })
            elif cs == "subline_missing":
                missing_names = [s.get("subline_name") for s in (cr.get("subline_coverage") or [])
                                  if s.get("coverage") == "missing"]
                if missing_names:
                    issues.append({
                        "layer": "L2",
                        "category": "chapter_decomposition_misaligned",
                        "severity": "high",
                        "location": f"chapter_realized[ch={ci}]",
                        "target_chapter_index": ci,
                        "fix_target_layer": "outline_decomposition",
                        "evidence": f"ch{ci} coverage_status=subline_missing, missing sublines={missing_names}",
                        "explanation": "Stage 1b 自报 ≥1 subline coverage=missing. 资源库无对应 source.",
                        "suggested_fix": f"回 Stage 1a 砍掉 subline {missing_names} 或换 axis. rationale 必须引用 codex hint.",
                        "_driver_synthesized": True,
                    })

        # v30 fix D: 前后逻辑一致性强制检查 — subline_declarations 未被展开
        # (P21b HARD). 之前只有 codex 侧 skill 检查 (L2-2a), 但 codex 有时 miss.
        # driver 加确定性 hard-check: 若某 slide 宣告 "N 主线", 章内 sibling slide 里
        # 应有 N 张 case_study_opener 类 archetype 展开; 若 M<N → CRITICAL issue.
        _subline_kw_re = None
        try:
            import re as _re_sd
            _subline_kw_re = _re_sd.compile(
                r"(\d)\s*(?:主线|路线|抓手|维度|大方向|方向|条路径)"
            )
        except Exception:
            _subline_kw_re = None
        _cur_slides = current.get("slides") or []
        _slides_by_ch: dict = {}
        for _s in _cur_slides:
            _ci = _s.get("chapter_index")
            if _ci is None:
                continue
            _slides_by_ch.setdefault(_ci, []).append(_s)
        for _ci, _ch_slides in _slides_by_ch.items():
            _role = ch_role_by_idx.get(_ci, "")
            if _role in STRUCTURAL_ROLES:
                continue
            # 找该章内声明 N 主线的 slide
            for _decl_s in _ch_slides:
                _text = " ".join([
                    _decl_s.get("target_title") or "",
                    _decl_s.get("page_purpose") or "",
                    " ".join(_decl_s.get("key_points") or []),
                ])
                if not _subline_kw_re:
                    continue
                _match = _subline_kw_re.search(_text)
                if not _match:
                    continue
                try:
                    _n_declared = int(_match.group(1))
                except Exception:
                    continue
                if _n_declared < 2 or _n_declared > 6:
                    continue
                # 统计该章 case_study_opener 类展开 slide 数
                _opener_archetypes = ("case_study_opener", "paper_intro", "case_study_paper",
                                        "worker_intro", "method_arc_uses_paper")
                _n_openers = 0
                _opener_indices = []
                for _cs in _ch_slides:
                    _archs = _cs.get("archetype") or []
                    if isinstance(_archs, str):
                        _archs = [_archs]
                    if any(any(_kw in (a or "").lower() for _kw in _opener_archetypes)
                            for a in _archs):
                        _n_openers += 1
                        _opener_indices.append(_cs.get("slide_index"))
                if _n_openers < _n_declared:
                    issues.append({
                        "layer": "L2",
                        "category": "subline_unfollowed",
                        "severity": "critical",
                        "location": f"chapter_plan[ch={_ci}].slides",
                        "target_chapter_index": _ci,
                        "fix_target_layer": "outline_decomposition",
                        "evidence": (f"ch{_ci} slide {_decl_s.get('slide_index')} 宣告 "
                                     f"'{_n_declared} 主线', 实际展开 case_study_opener 类 "
                                     f"slide 只有 {_n_openers} 张 (indices={_opener_indices})"),
                        "explanation": ("前后逻辑一致性硬约束: 声明 N 主线必须紧跟 N 张代表工作 "
                                         "opener slide 展开, 否则观众预期落空."),
                        "suggested_fix": (f"要么补足 {_n_declared - _n_openers} 张 case_study_opener slide "
                                          f"(每主线 1 张), 要么把宣告改成 '{_n_openers} 主线' "
                                          f"与实际一致."),
                        "_driver_synthesized": True,
                        "_source_check": "v30_subline_hard_enforce",
                    })

        # v30 fix G (refined, corrected order): no_supporting_material 页 → 库驱动
        # 原则要求 outline 必须与库一致, 不留 placeholder. 每轮注入 critical issue
        # 给 outline_fix_from_review skill, 由 skill 决定: 删该 slide / 改
        # target_claim 到库能支撑方向 / 减章页数.
        #
        # 修正: 直接扫 current.slides[] 检测 (kind==new / source_resource_ids=[]
        # / kind==no_supporting_material 都算 no_material). 之前依赖
        # current.no_material_pages 字段, 但该字段是 Plan-A sweep 后填的, sweep
        # 在 Stage 2 之后 → 注入代码永远读到空 → issue 从未生成. 直接扫 slides
        # 就没这个 timing 问题.
        _no_material_slides = []
        for _sl in (current.get("slides") or []):
            if not isinstance(_sl, dict):
                continue
            _srcs = _sl.get("source_resource_ids") or []
            _kind = (_sl.get("source_carrier_resource_kind") or "").lower()
            if not _srcs or _kind in ("no_supporting_material", "new"):
                _no_material_slides.append(_sl)
        for _sl in _no_material_slides:
            _sidx = _sl.get("slide_index")
            _cidx = _sl.get("chapter_index")
            _tclaim = (_sl.get("target_claim") or "")[:100]
            _troll = _sl.get("target_role")
            issues.append({
                "layer": "L3",
                "category": "no_supporting_material",
                "severity": "critical",
                "location": f"slides[slide_index={_sidx}]",
                "target_slide_index": _sidx,
                "target_chapter_index": _cidx,
                "fix_target_layer": "outline_content",
                "evidence": (f"slide {_sidx} (ch{_cidx}, role={_troll}) target_claim="
                             f"'{_tclaim}' 无库支持材料 (source_resource_ids 空 或 "
                             f"kind={_sl.get('source_carrier_resource_kind')})"),
                "explanation": ("库驱动原则: outline 必须与库一致. 无材料 slide 不能保留 "
                                 "placeholder, 必须调整 outline 到库能支撑的形态."),
                "suggested_fix": (
                    "3 选 1 (按优先级): "
                    "(a) 若该 slide 不影响章内叙事完整性 → 删除, 后续 slide_index 顺移; "
                    "(b) 优先: 用 cascade_hierarchy 或 library_evidence_keywords 反查库里 "
                    "该 chapter/role 实际有的内容方向, 改 target_title/target_claim/"
                    "key_points 到该方向, 重新挑 source; "
                    "(c) 若章内 ≥50% slide 都 no_material → 整章 chapter_decomposition "
                    "重拆, 改 axis 到库能支撑的分解方向."
                ),
                "_driver_synthesized": True,
                "_from_no_material_sweep": True,
            })

        # v34 logic_story rule enforcement: move source/rhythm/work-block
        # structural mistakes upstream from GAP_CARD_GENERATION into OUTLINE
        # review/fix, so byte-clone draft does not knowingly start from a bad
        # source binding or asymmetric outline.
        _structural_rule_issues = _outline_structural_rule_issues(current)
        if _structural_rule_issues:
            _existing_fingerprints = {
                (
                    i.get("category"),
                    i.get("target_slide_index"),
                    i.get("target_chapter_index"),
                    i.get("evidence"),
                )
                for i in issues
                if isinstance(i, dict)
            }
            _added_structural = 0
            for _iss in _structural_rule_issues:
                _fp = (
                    _iss.get("category"),
                    _iss.get("target_slide_index"),
                    _iss.get("target_chapter_index"),
                    _iss.get("evidence"),
                )
                if _fp in _existing_fingerprints:
                    continue
                issues.append(_iss)
                _existing_fingerprints.add(_fp)
                _added_structural += 1
            if _added_structural:
                print(f"[OUTLINE] rnd{rnd} driver structural rule issues: "
                      f"+{_added_structural}", flush=True)

        # update rdata.issues so review_log captures the augmented set
        rdata["issues"] = issues

        n_ch = sum(1 for i in issues
                    if isinstance(i, dict) and i.get("severity") in ("critical", "high"))
        n_synth = sum(1 for i in issues if isinstance(i, dict) and i.get("_driver_synthesized"))
        print(f"[OUTLINE] rnd{rnd} review: ok={rdata.get('ok')}, "
              f"issues={len(issues)} (critical/high={n_ch}, synth={n_synth})", flush=True)
        if rdata.get("ok") and n_ch == 0:
            break
        if rnd >= MAX_REVIEW_ROUNDS:
            print(f"[OUTLINE] reached bounded review limit "
                  f"({MAX_REVIEW_ROUNDS} rounds); unresolved {n_ch} "
                  "critical/high issues will block before artifacts", flush=True)
            break

        # ============================================================
        # Pure surgical fix (mirror IDEA small-loop, no 4-way dispatch)
        # ============================================================
        # Normalize issues → unified schema (source=codex)
        unified_issues = []
        for iss in issues:
            if not isinstance(iss, dict):
                continue
            if "source" not in iss:
                iss = {**iss, "source": "codex"}
            unified_issues.append(iss)

        fix_payload = {
            "prior_outline": current,
            "issues": unified_issues,
            "idea_analysis": oc.compact_idea_for_fix(idea),
            "logic_story_hard_rules_summary": hard_rules,
            "page_specific_rules_summary": archetype_for_prompt,
            "selected_narrative_pattern_body": selected_pattern_body,
            "rhythm_pattern_bodies": rhythm_bodies,
        }
        fix_prompt = (
            "Apply surgical fix per the outline_fix_from_review skill. Output complete "
            "patched outline.json v1.0 (strict JSON, ALL original fields preserved, "
            "only flagged locations modified, add/update fix_round + "
            "referenced_review_issues + user_concern_history).\n\n"
            "INPUT:\n" + json.dumps(fix_payload, ensure_ascii=False)
        )
        fix_out = claude_cli.call_claude_json(
            fix_prompt,
            skill=["skills/outline_gen/outline_fix_from_review.md"],
            timeout=900,
        )
        if not (fix_out.get("ok") and isinstance(fix_out.get("data"), dict)):
            print(f"[OUTLINE] rnd{rnd} surgical fix failed: "
                  f"{(fix_out.get('error') or '')[:160]}; trying local no-source repair",
                  flush=True)
            current, local_fix_log = _apply_no_source_local_fix(
                current,
                unified_issues,
                reason=f"global surgical fix failed: {(fix_out.get('error') or '')[:120]}",
            )
            if not any(x.get("ok") for x in local_fix_log):
                print("[OUTLINE] local no-source repair did not apply; keeping prior draft",
                      flush=True)
                break
            continue
        # v30 safety guard: reject fix output that dropped top-level structure.
        # The fix skill sometimes returns a chapter_realized fragment or a
        # "skipped ambiguous fix" stub instead of the full patched outline —
        # blindly assigning it would truncate outline.json and break downstream.
        # Only structural completeness is checked; a large slide-count drop is
        # legitimate (library-driven pruning may delete many no_material slides).
        _new = fix_out["data"]
        _required_keys = ("slides", "chapter_to_slide_map", "identity")
        _missing = [k for k in _required_keys if k not in _new]
        _new_slides = _new.get("slides") or []
        if _missing or not isinstance(_new_slides, list) or len(_new_slides) < 1:
            print(f"[OUTLINE] rnd{rnd} fix output rejected as structural fragment: "
                  f"missing={_missing}, slides={len(_new_slides)}; "
                  f"keeping prior draft", flush=True)
            break
        current = _new
        current["schema_version"] = "1.0"
        current = _normalize_outline_chapter_links(current, chapter_plan)

    if final_review:
        _final_blocking = [
            i for i in ((final_review or {}).get("issues") or [])
            if isinstance(i, dict) and i.get("severity") in ("critical", "high")
        ]
        if _final_blocking:
            diag = {
                "schema_version": "1.0",
                "generated_at": now(),
                "project_id": project_id,
                "error": "OUTLINE_GENERATION blocked by unresolved critical/high review issues after one repair attempt.",
                "blocking_issues": _final_blocking,
                "review_log": review_log,
                "outline_draft": current,
            }
            write_json(pdir / "outline-review-diagnostics.json", diag)
            return {"ok": False, "stage": "OUTLINE_GENERATION",
                    "outline_diagnostics": str(pdir / "outline-review-diagnostics.json"),
                    "error": (f"bounded outline inspection: {len(_final_blocking)} "
                              "critical/high issues remain after one repair; "
                              "not proceeding to GAP_CARD_GENERATION/DRAFT_ASSEMBLY."),
                    "blocking_issues": _final_blocking[:20]}

    current = _enforce_outline_structural_pages(current)

    # ============================================================
    # v3 (2026-07-29) agenda-same-source post-pass.
    # All agenda / toc / chapter_divider / section_divider slides MUST share
    # the SAME source_resource_ids (top-1). This way byte-clone in
    # DRAFT_ASSEMBLY produces visually-identical agenda pages that only differ
    # in which chapter is highlighted (done later by CHARACTER_REVISION.recolor_text).
    # ============================================================
    _agenda_roles = {"agenda", "toc", "chapter_divider", "section_divider"}
    _agenda_slides = [
        s for s in (current.get("slides") or [])
        if isinstance(s, dict)
        and str(s.get("target_role") or "").lower() in _agenda_roles
    ]
    if _agenda_slides:
        # Find first agenda slide that already has a source, use it as canonical
        _canon_src_list = None
        _canon_from = None
        for _s in _agenda_slides:
            _srcs = _s.get("source_resource_ids") or []
            if _srcs:
                _canon_src_list = list(_srcs)
                _canon_from = _s.get("slide_index")
                break
        if _canon_src_list is not None:
            _forced = 0
            for _s in _agenda_slides:
                _existing = _s.get("source_resource_ids") or []
                if _existing != _canon_src_list:
                    _s["source_resource_ids"] = list(_canon_src_list)
                    _s["_agenda_source_forced"] = True
                    _forced += 1
            print(f"[OUTLINE] agenda-same-source post-pass: {len(_agenda_slides)} agenda-like slides, "
                  f"canonical source = {_canon_src_list[0] if _canon_src_list else None} "
                  f"(from slide {_canon_from}), forced {_forced} slides", flush=True)
        else:
            print(f"[OUTLINE] agenda-same-source post-pass: {len(_agenda_slides)} agenda-like slides "
                  f"but NONE has a source yet — skipping (fail-fast may catch this)", flush=True)

    # ============================================================
    # v31 fail-fast: OUTLINE 结束前, assert 每张 slide 有 source_resource_ids.
    # 之前 v23/v30 用 Plan-A sweep + hard-prune + final gate 兜底 (~350 行代码).
    # 现在 IDEA_ANALYSIS 阶段已建 library_understanding 三层结构, chapter_plan 从
    # 库能供的出发, Stage 1b 复用 IDEA 建的池 —— 源头对齐后 no_material 应≈0.
    # 若还有 slide 无 source, 是 pipeline bug (IDEA 逃逸 / Stage 1b 未收敛),
    # fail-fast 汇报诊断信息给 caller, 不再静默兜底.
    # ============================================================
    _final_slides = current.get("slides") or []
    _no_src: list[dict] = []
    for _s in _final_slides:
        if not isinstance(_s, dict):
            continue
        _srcs = _s.get("source_resource_ids") or []
        if not _srcs:
            _no_src.append({
                "slide_index": _s.get("slide_index"),
                "chapter_index": _s.get("chapter_index"),
                "target_role": _s.get("target_role"),
                "target_title": (_s.get("target_title") or "")[:60],
                "kind": _s.get("kind") or _s.get("source_carrier_resource_kind"),
            })
    if _no_src:
        diag = {
            "schema_version": "1.0",
            "generated_at": now(),
            "project_id": project_id,
            **idea_fingerprint,
            "error": "OUTLINE_GENERATION blocked because slides without source_resource_ids are not allowed.",
            "no_source_slides": _no_src,
            "review_log": review_log,
            "outline_draft": current,
        }
        write_json(pdir / "outline-no-source-diagnostics.json", diag)
        return {"ok": False, "stage": "OUTLINE_GENERATION",
                "outline_diagnostics": str(pdir / "outline-no-source-diagnostics.json"),
                "error": (f"v31 fail-fast: {len(_no_src)} slides have no "
                          "source_resource_ids after codex loop — 无来源页禁止进入 "
                          "GAP_CARD_GENERATION/DRAFT_ASSEMBLY. 检查 diagnostics 中 "
                          "的 no_source_slides, 回滚/重写这些页并绑定真实 material source."),
                "no_source_slides": _no_src[:20]}

    _remaining_structural_issues = [
        i for i in _outline_structural_rule_issues(current)
        if isinstance(i, dict) and i.get("severity") in {"critical", "high"}
    ]
    if _remaining_structural_issues:
        diag = {
            "schema_version": "1.0",
            "generated_at": now(),
            "project_id": project_id,
            "error": "OUTLINE_GENERATION blocked by unresolved v34 logic_story structural/source-binding rules.",
            "blocking_issues": _remaining_structural_issues,
            "review_log": review_log,
            "outline_draft": current,
        }
        write_json(pdir / "outline-structural-rule-diagnostics.json", diag)
        return {"ok": False, "stage": "OUTLINE_GENERATION",
                "outline_diagnostics": str(pdir / "outline-structural-rule-diagnostics.json"),
                "error": (f"v34 structural gate: {len(_remaining_structural_issues)} "
                          "critical/high source/rhythm/work-block issues remain after "
                          "review loop — 不允许继续进入 GAP_CARD_GENERATION/DRAFT_ASSEMBLY."),
                "blocking_issues": _remaining_structural_issues[:20]}
    # v31 兼容: 初始化 sweep_stats / hard_removed_slides / no_material_pages 为空
    # (下游 outline-user-status.json / UI 可能读, 保持字段存在)
    current.setdefault("sweep_stats", {
        "bound_content": 0, "bound_visual_axis": 0, "hard_removed": 0,
        "adj_dedup_swapped": 0, "adj_dedup_removed": 0,
        "note": "v31: Plan-A sweep + hard-prune removed; 源头对齐直接得净 outline",
    })
    current.setdefault("hard_removed_slides", [])
    current.setdefault("no_material_pages", [])
    current = _normalize_outline_chapter_links(current, chapter_plan)
    print(f"[OUTLINE] v31 fail-fast passed: {len(_final_slides)} slides all "
          f"have source_resource_ids", flush=True)

    # v31: final gate 已删 (源头对齐后 no_material 恒为 0, fail-fast 在
    # codex loop 后, 结构性检查已完成. thin chapter warning 交给 codex review 处理).
    return _write_outline_artifacts(
        current,
        review_log_in=review_log,
        final_review_in=final_review,
        stage1_errors_in=stage1_errors,
        narrative_warnings_in=nlc_warnings,
        source_label=current.get("source") or "claude_outline_generation",
    )


def _run_outline_with_user_override(
    project_id: str, brief: dict, brief_raw: dict, understanding: dict, user_outline: str
) -> dict:
    """Legacy single-shot path when user supplies a non-empty user_outline.

    Uses the deprecated deck_outline.md skill (still valid for user-override case
    where two-stage offers no benefit — user has already done the chaptering).
    """
    import time as _time
    from . import claude_cli

    pdir = project_dir(project_id)
    narrative_block = brief.get("narrative_constraints") or {}
    context = {
        "idea_analysis": brief,
        "project_source_understanding": understanding,
        "user_outline": user_outline,
        "narrative_constraints": narrative_block,
    }
    prompt = (
        "user_outline is non-empty — follow it page-by-page strictly per deck_outline.md.\n"
        "Output strict JSON only.\n\nINPUT:\n" + json.dumps(context, ensure_ascii=False)
    )
    outcome = None
    for attempt in range(1, 4):
        outcome = claude_cli.call_claude_json(
            prompt,
            skill=["skills/outline_gen/deck_outline.md"],
            timeout=900,
        )
        if outcome.get("ok"):
            break
        if attempt < 3:
            _time.sleep(2 ** attempt)
    if not (outcome.get("ok") and isinstance(outcome.get("data"), dict)):
        return {
            "ok": False, "stage": "OUTLINE_GENERATION",
            "error": (outcome.get("error") or "claude returned unusable shape")[:600],
            "retry_hint": "OUTLINE 失败 (user_outline 路径) — 重跑该 stage",
        }
    data = outcome["data"]
    data.setdefault("schema_version", "1.0")
    data["generated_at"] = now()
    data["source"] = "claude_user_outline"
    write_json(pdir / "outline.json", data)
    return {
        "ok": True, "stage": "OUTLINE_GENERATION",
        "outline": str(pdir / "outline.json"),
        "source": data.get("source"),
        "slide_count": data.get("slide_count"),
        "user_outline_applied": True,
    }


def _run_outline_revision(project_id: str) -> dict:
    """OUTLINE user-flow revision (2026-06-29).

    Reads:
      - projects/<id>/outline.json (current outline, post codex final_ok)
      - projects/<id>/outline-user-feedback.json (user natural-language feedback)
      - projects/<id>/idea-analysis.json (idea v3.2, for chapter context + escalation check)
      - projects/<id>/data/source-understanding.json (optional, for resource lookup)

    Pipeline:
      1. Claude `outline_revision.md` — surgical apply user feedback + append user_concern_history
      2. Codex `outline_review.md` round 1 — Cat 10 user_concern_regression check
      3. (If issues) Claude `outline_fix_from_review.md` surgical fix, max 3 rounds
      4. Claude `outline_human_summary.md` — re-render outline.md

    Writes:
      - outline.json (revised)
      - outline.md (re-rendered)
      - outline-review.json (appended new rounds)
      - outline-user-status.json (updated revision_round)
    """
    import time as _time
    from . import claude_cli, codex_cli, outline_context as oc

    pdir = project_dir(project_id)
    fb_path = pdir / "outline-user-feedback.json"
    if not fb_path.exists():
        return {
            "ok": False, "stage": "OUTLINE_REVISION",
            "error": f"missing {fb_path}",
            "retry_hint": "请先写 outline-user-feedback.json (含 user_comments)",
        }

    current = read_json(pdir / "outline.json", {}) or {}
    if not current.get("slides"):
        return {
            "ok": False, "stage": "OUTLINE_REVISION",
            "error": "outline.json missing or empty slides",
            "retry_hint": "先跑 OUTLINE_GENERATION",
        }
    feedback = read_json(fb_path, {}) or {}
    idea = read_json(pdir / "idea-analysis.json", {}) or {}
    intake = read_json(pdir / "idea-intake-light.json", {}) or {}
    su_path = pdir / "data" / "source-understanding.json"
    source_understanding = read_json(su_path, {}) if su_path.exists() else {}

    # Global resources (for codex review)
    archetypes = oc.load_page_specific_archetypes()  # full list; per-chapter filter applied below
    hard_rules = oc.load_logic_story_hard_rules_summary()
    archetype_for_prompt = [
        {"id": a["id"], "category": a["category"],
         "enforcement_level": a["enforcement_level"],
         "applicable_role": a["applicable_role"],
         "hit_rate": a["hit_rate"], "summary": a["summary"]}
        for a in archetypes
    ]

    # ============================================================
    # Step 1 — Claude surgical apply user feedback
    # ============================================================
    revision_payload = {
        "current_outline": current,
        "user_feedback": feedback,
        "idea_analysis": idea,
        "source_understanding": source_understanding,
    }
    revision_prompt = (
        "Apply USER feedback to PRIOR outline.json. Surgical: only modify fields "
        "user_comments target. Preserve untouched fields byte-identical. APPEND new "
        "entries to user_concern_history (don't drop existing IDEA-stage concerns). "
        "Output FULL corrected outline.json v1.0. Strict JSON only.\n\n"
        "INPUT:\n" + json.dumps(revision_payload, ensure_ascii=False)
    )
    rev_out = claude_cli.call_claude_json(
        revision_prompt,
        skill=["skills/outline_gen/outline_revision.md"],
        timeout=900,
    )
    if not (rev_out.get("ok") and isinstance(rev_out.get("data"), dict)):
        return {
            "ok": False, "stage": "OUTLINE_REVISION",
            "error": f"idea_revision call failed: {(rev_out.get('error') or '')[:200]}",
            "retry_hint": "重试 (transient cli failures), 或检查 outline-user-feedback.json",
        }
    revised = rev_out["data"]
    revised["schema_version"] = "1.0"
    revised["generated_at"] = now()
    print(f"[OUTLINE_REVISION] revision applied, "
          f"user_concern_history={len(revised.get('user_concern_history', []))}",
          flush=True)

    # ============================================================
    # Step 2 — Codex review (Cat 10 user_concern_regression active)
    # ============================================================
    review_log: list[dict] = []
    final_review: dict | None = None
    MAX_ROUNDS = 3
    cur = revised
    for rnd in range(1, MAX_ROUNDS + 1):
        review_input = {
            "outline": cur,
            "idea_analysis": idea,
            "intake_light": intake,
            "page_specific_rules_summary": archetype_for_prompt,
            "logic_story_hard_rules_summary": hard_rules,
            "round": rnd,
            "prior_issues": (review_log[-1].get("issues") if review_log else []),
            "user_concern_history": cur.get("user_concern_history", []),
        }
        review_prompt = (
            f"Review outline.json round {rnd} post-user-revision. Cat 10 "
            f"user_concern_regression is ACTIVE (cross-stage, check IDEA + OUTLINE concerns). "
            f"Output {{ok, round, issues, summary}} strict JSON only.\n\nINPUT:\n"
            + json.dumps(review_input, ensure_ascii=False)
        )
        rev_resp = codex_cli.call_codex_json(
            review_prompt,
            skill=["skills/outline_gen/outline_review.md"],
            timeout=600,
        )
        if not rev_resp.get("ok"):
            review_log.append({"round": rnd, "codex_error": rev_resp.get("error")})
            break
        rdata = rev_resp.get("data") or {}
        rdata["round"] = rnd
        review_log.append(rdata)
        final_review = rdata
        issues = rdata.get("issues") or []
        n_ch = sum(1 for i in issues
                    if isinstance(i, dict) and i.get("severity") in ("critical", "high"))
        print(f"[OUTLINE_REVISION] rnd{rnd}: ok={rdata.get('ok')}, "
              f"issues={len(issues)}, critical/high={n_ch}", flush=True)
        if rdata.get("ok") and n_ch == 0:
            break
        if rnd >= MAX_ROUNDS:
            break
        # Surgical fix with regression guard
        # Use compact_idea_for_fix to trim payload (Bug-2 fix)
        fix_payload = {
            "prior_outline": cur,
            "codex_issues": issues,
            "idea_analysis": oc.compact_idea_for_fix(idea),
            "logic_story_hard_rules_summary": hard_rules,
            "page_specific_rules_summary": archetype_for_prompt,
        }
        fix_prompt = (
            "Apply SURGICAL fixes to PRIOR outline.json. Preserve untouched fields "
            "byte-identical. Respect user_concern_history regression guard (include IDEA "
            "stage concerns). Output FULL corrected outline.json v1.0. Strict JSON only.\n\n"
            "INPUT:\n" + json.dumps(fix_payload, ensure_ascii=False)
        )
        fix_resp = claude_cli.call_claude_json(
            fix_prompt,
            skill=["skills/outline_gen/outline_fix_from_review.md"],
            timeout=900,
        )
        if not (fix_resp.get("ok") and isinstance(fix_resp.get("data"), dict)):
            print(f"[OUTLINE_REVISION] rnd{rnd} fix failed; keeping prior", flush=True)
            break
        cur = fix_resp["data"]
        cur["schema_version"] = "1.0"

    # ============================================================
    # Step 3 — Re-render outline.md
    # ============================================================
    md_content = ""
    try:
        summary_prompt = (
            "Render outline.md from the JSON below. Your ENTIRE response IS the "
            "markdown file content. First character MUST be `#`. No preamble, no "
            "code fence.\n\nINPUT:\n"
            + json.dumps({"outline": cur}, ensure_ascii=False)
        )
        sum_res = claude_cli.call_claude_text(
            summary_prompt,
            skill=["skills/outline_gen/outline_human_summary.md"],
            timeout=600,
        )
        if sum_res.get("ok"):
            md = (sum_res.get("text") or "").strip()
            if md.startswith("```markdown"):
                md = md.split("```markdown", 1)[1].rstrip("`").strip()
            elif md.startswith("```"):
                md = md.strip("`").strip()
            md_content = md
    except Exception as exc:
        print(f"[OUTLINE_REVISION] human_summary failed: {exc}", flush=True)

    # ============================================================
    # Write artifacts
    # ============================================================
    write_json(pdir / "outline.json", cur)
    if md_content:
        (pdir / "outline.md").write_text(md_content, encoding="utf-8")
    # Append review rounds to outline-review.json
    prior_review = read_json(pdir / "outline-review.json", {}) or {}
    prior_rounds = prior_review.get("rounds") or []
    all_rounds = prior_rounds + review_log
    write_json(pdir / "outline-review.json", {
        "schema_version": "1.0",
        "rounds": all_rounds,
        "final_ok": (final_review or {}).get("ok") if final_review else False,
        "revision_round": cur.get("revision_round"),
    })
    _write_stage_status(pdir, "outline-user-status.json",
                         slide_count=len(cur.get("slides", [])),
                         chapter_count=len(cur.get("chapter_to_slide_map", {})),
                         revision_round=cur.get("revision_round"),
                         codex_review_rounds_total=len(all_rounds),
                         codex_final_ok=(final_review or {}).get("ok") if final_review else None,
                         user_concern_count=len(cur.get("user_concern_history", [])))

    return {
        "ok": True,
        "stage": "OUTLINE_REVISION",
        "outline": str(pdir / "outline.json"),
        "outline_md": str(pdir / "outline.md") if md_content else None,
        "review": str(pdir / "outline-review.json"),
        "revision_round": cur.get("revision_round"),
        "codex_review_rounds_this_flow": len(review_log),
        "codex_final_ok": (final_review or {}).get("ok") if final_review else None,
        "slide_count": len(cur.get("slides", [])),
        "user_concern_count": len(cur.get("user_concern_history", [])),
    }


def _check_outline_against_narrative(slides: list, narrative_block: dict) -> list[str]:
    """Soft-warning check: verify outline satisfies brief.narrative_constraints.

    Returns list of human-readable warning strings (empty list if all pass).
    Does NOT reject the outline — just surfaces issues for the developer.
    """
    if not isinstance(narrative_block, dict) or not narrative_block:
        return []
    if not isinstance(slides, list) or not slides:
        return []

    warnings: list[str] = []

    # Build slide → chapter map (new v3.2 OUTLINE uses `chapter_index`; legacy
    # v3.0 brief uses `section_index`. Accept either for backcompat.)
    slide_to_section: dict[int, int] = {}
    section_first_slide: dict[int, int] = {}
    for s in slides:
        if not isinstance(s, dict):
            continue
        idx = s.get("slide_index")
        sec = s.get("chapter_index")
        if sec is None:
            sec = s.get("section_index")
        if idx is not None and sec is not None:
            try:
                slide_to_section[int(idx)] = int(sec)
                if int(sec) not in section_first_slide:
                    section_first_slide[int(sec)] = int(idx)
            except (TypeError, ValueError):
                pass

    # 1. thesis_callback check
    tc = narrative_block.get("thesis_callback") or {}
    raise_chap = tc.get("raise_at_chapter")
    callback_chaps = tc.get("callback_at_chapters") or []
    if raise_chap and raise_chap not in section_first_slide.values() and raise_chap not in slide_to_section.values():
        warnings.append(f"thesis_callback: raise_at_chapter={raise_chap} not found in any slide.section_index")
    for cb in callback_chaps:
        if cb not in slide_to_section.values():
            warnings.append(f"thesis_callback: callback_at_chapter={cb} not found in any slide.section_index")

    # 2. anchor_term_trajectory check
    for anchor_spec in (narrative_block.get("anchor_term_trajectory") or []):
        if not isinstance(anchor_spec, dict):
            continue
        anchor = anchor_spec.get("anchor")
        if not isinstance(anchor, str) or not anchor:
            continue  # skip malformed entries (None / empty / non-string anchor)
        must_in = anchor_spec.get("must_appear_in_chapters") or []
        # Collect anchor_terms across slides in those chapters
        for chap in must_in:
            present = any(
                anchor in (s.get("anchor_terms") or [])
                or anchor in str(s.get("target_title") or "")
                or anchor in str(s.get("target_claim") or "")
                for s in slides
                if isinstance(s, dict) and (s.get("chapter_index") == chap or s.get("section_index") == chap)
            )
            if not present:
                warnings.append(
                    f"anchor_term_trajectory: anchor '{anchor}' "
                    f"required in chapter {chap} but not found in any slide.anchor_terms/title/claim"
                )

    # 3. framework_anchor_repeat check (just check chapter presence)
    far = narrative_block.get("framework_anchor_repeat") or {}
    far_chaps = far.get("must_appear_in_chapters") or []
    for chap in far_chaps:
        if chap not in slide_to_section.values():
            warnings.append(
                f"framework_anchor_repeat: chapter {chap} required for anchor recurrence but section not found"
            )

    # 4. cross_section_hooks: light sanity (just check section pairs exist)
    for hook in (narrative_block.get("cross_section_hooks") or []):
        if not isinstance(hook, dict):
            continue
        fr = hook.get("from_section")
        to = hook.get("to_section")
        if fr is not None and fr not in slide_to_section.values():
            warnings.append(f"cross_section_hook: from_section={fr} not in outline")
        if to is not None and to not in slide_to_section.values():
            warnings.append(f"cross_section_hook: to_section={to} not in outline")

    return warnings



    pdir = project_dir(project_id)
    answers = _answers(project_id)
    resources = read_json(pdir / "project-source-index.json", [])
    audit = read_json(pdir / "research-audit.json", {})
    useful = []
    reusable_candidates = []
    semantic_audit_required = []
    style_only = []
    content_source_types = {"text", "data", "document", "spreadsheet", "mindmap"}
    reusable_source_types = {"ppt_deck", "image", "video"}
    for item in resources if isinstance(resources, list) else []:
        typ = str(item.get("type") or "")
        path = str(item.get("path") or "")
        is_content_source = typ in content_source_types
        is_reusable_candidate = typ in reusable_source_types
        is_import_svg = "_template_import/svg" in path
        is_import_asset = "_template_import/assets/" in path
        is_decorative_or_derived = (
            is_import_svg
            or "slidemaster" in path.lower()
            or "slidelayout" in path.lower()
            or "/theme/" in path.lower()
        )
        entry = {
            "resource_id": item.get("resource_id"),
            "path": path,
            "type": typ,
            "reusable_level": item.get("reusable_level"),
            "reason": "usable local source" if is_content_source else "auditable visual/page candidate" if is_reusable_candidate and not is_decorative_or_derived else "style or derived visual reference",
        }
        if is_content_source:
            useful.append(entry)
        elif is_reusable_candidate and not is_decorative_or_derived:
            candidate = {
                **entry,
                "allowed_decisions": ["direct_reuse", "redraw_from_source", "adapt_structure", "style_only", "reject"],
                "audit_rule": "model must verify topic/claim/object/caption/context before direct reuse",
            }
            reusable_candidates.append(candidate)
            semantic_audit_required.append(candidate)
        elif is_import_asset and typ == "image":
            candidate = {
                **entry,
                "allowed_decisions": ["direct_reuse", "redraw_from_source", "reject"],
                "audit_rule": "source PPT extracted images can support a page only when surrounding slide context matches the current claim",
            }
            reusable_candidates.append(candidate)
            semantic_audit_required.append(candidate)
        else:
            style_only.append(entry)
    task = {
        "schema_version": "1.0",
        "generated_at": now(),
        "source": "stage_runner",
        "deck_type": _task_type(answers),
        "topic": answers.get("topic"),
        "audience": answers.get("audience"),
        "scenario": answers.get("scenario"),
        "language": answers.get("language") or "zh",
        "slide_count": int(answers.get("slide_count") or 10),
        "additional_web_research_required": int(audit.get("web_results_count") or 0) == 0,
        "known_gaps": [] if audit else ["research audit is missing or empty"],
    }
    selection = {
        "schema_version": "1.0",
        "generated_at": now(),
        "source": "stage_runner",
        "useful_materials": useful,
        "reusable_candidate_materials": reusable_candidates,
        "semantic_audit_required_materials": semantic_audit_required,
        "style_only_materials": style_only,
        "irrelevant_materials": [],
        "stale_materials": [],
        "selection_policy": answers.get("reuse_policy") or "prefer project resources before generated content",
        "reuse_policy": {
            "project_sources": "PPT pages, extracted figures, images, tables, and data are candidates for model-audited page evidence or redraw; do not demote them to style-only before semantic audit.",
            "templates": "Global templates remain style/layout/component knowledge unless a unit explicitly passes direct reuse guards.",
            "direct_reuse_requires": ["topic_match", "claim_match", "object_or_metric_match", "caption_or_slide_context_match", "low_misleading_risk"],
        },
    }
    # Optional model refinement: keep the deterministic skeleton (schema-safe) and let the
    # model only override the soft classification fields. Falls back silently if no model.
    from . import stage_models

    base_prompt = (
        "你是 PPT-agent 的任务理解模型。基于上下文 JSON 判断这次演示的类型与缺口。"
        "如果 resource_count > 0 或 useful_materials 非空，禁止声称本地资料库为空；"
        "只能指出这些资料还缺哪些量化事实、引用或实验设计。"
        "只输出 JSON：{\"deck_type\":\"literature_review|product_pitch|technical_report|"
        "executive_briefing|general_presentation\",\"known_gaps\":[\"...\"],"
        "\"narrative_hint\":\"一句话叙事建议\"}。不要输出解释。"
    )
    model = stage_models.generate_artifact(
        project_id, "TASK_UNDERSTANDING", base_prompt,
        context={
            "answers": answers,
            "resource_count": len(resources) if isinstance(resources, list) else 0,
            "resource_type_counts": _count_resource_types(resources),
            "useful_materials": useful,
            "reusable_candidate_materials": reusable_candidates[:120],
            "semantic_audit_required_materials": semantic_audit_required[:120],
            "style_only_materials": style_only,
            "research_audit": audit,
        },
        parse="json",
    )
    if model.get("ok"):
        data = model["data"]
        if data.get("deck_type"):
            task["deck_type"] = str(data["deck_type"])
        if isinstance(data.get("known_gaps"), list):
            task["known_gaps"] = [str(x) for x in data["known_gaps"] if str(x).strip()] or task["known_gaps"]
        if data.get("narrative_hint"):
            task["narrative_hint"] = str(data["narrative_hint"])
        task["generated_by"] = model.get("provider")
    if resources and isinstance(task.get("known_gaps"), list):
        task["known_gaps"] = [
            gap for gap in task["known_gaps"]
            if "本地资料库为空" not in gap and "本地资源库为空" not in gap
        ] or [
            "本地资料已载入，但仍需补齐可引用的量化基准、实验设置与外部来源"
        ]

    write_json(pdir / "task-analysis.json", task)
    write_json(pdir / "material-selection.json", selection)
    return {"task_analysis": task, "material_selection": selection}





def _fm_dict(path) -> dict:
    """Parse a leading ``key: value`` YAML-frontmatter block into a flat dict."""
    out: dict = {}
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return out
    if not text.startswith("---"):
        return out
    body = text.split("---", 2)
    if len(body) < 3:
        return out
    for line in body[1].splitlines():
        if ":" in line:
            key, val = line.split(":", 1)
            out[key.strip()] = val.strip().strip('"')
    return out


def _outline_lines(user_outline: str) -> list[str]:
    lines = []
    for raw in str(user_outline or "").splitlines():
        line = re.sub(r"^\s*[-*#\d.、\)）]+\s*", "", raw).strip()
        if line:
            lines.append(line)
    return lines


def _asset_candidates_for_text(asset_catalog: dict, text: str, *, limit: int = 5) -> list[dict]:
    assets = asset_catalog.get("assets") if isinstance(asset_catalog, dict) else []
    query = {t for t in re.split(r"[^A-Za-z0-9_\u4e00-\u9fff]+", str(text or "").lower()) if len(t) >= 2}
    ranked = []
    for asset in assets or []:
        if not isinstance(asset, dict):
            continue
        if asset.get("asset_type") not in {"source_slide_svg", "source_figure", "image", "ppt_deck"}:
            continue
        hay = " ".join([
            str(asset.get("title") or ""),
            str(asset.get("caption") or ""),
            str(asset.get("content_summary") or ""),
            " ".join(str(x) for x in asset.get("text_context") or []),
            str(asset.get("path") or ""),
        ]).lower()
        tokens = {t for t in re.split(r"[^A-Za-z0-9_\u4e00-\u9fff]+", hay) if len(t) >= 2}
        overlap = len(query & tokens)
        priority = int(asset.get("source_priority") or 9)
        score = overlap * 10 + max(0, 10 - priority)
        if asset.get("asset_type") == "source_slide_svg":
            score += 4
        if asset.get("asset_type") == "source_figure":
            score += 6
        if score > 0:
            ranked.append((score, str(asset.get("path") or ""), asset))
    ranked.sort(key=lambda row: (-row[0], row[1]))
    return [dict(asset, match_score=round(score, 3)) for score, _, asset in ranked[:limit]]


def _outline_role(title: str, idx: int, slide_count: int) -> str:
    text = str(title or "").lower()
    if idx == 1:
        return "cover"
    if idx == slide_count:
        return "closing"
    if any(key in text for key in ["目录", "agenda", "outline", "汇报结构"]):
        return "agenda"
    if any(key in text for key in ["为什么", "背景", "趋势", "重要", "需求", "动机", "motivation", "background"]):
        return "motivation"
    if any(key in text for key in ["问题", "瓶颈", "挑战", "gap", "痛点", "矛盾"]):
        return "problem"
    if any(key in text for key in ["相关工作", "对比", "比较", "竞品", "baseline", "comparison"]):
        return "comparison"
    if any(key in text for key in ["技术", "路线", "框架", "系统", "方法", "机制", "架构", "method", "architecture"]):
        return "method"
    if any(key in text for key in ["实验", "性能", "结果", "评估", "benchmark", "latency", "throughput", "result"]):
        return "result"
    if any(key in text for key in ["风险", "边界", "计划", "落地", "roadmap"]):
        return "risk"
    return "content"


def _default_reuse_outline_lines(answers: dict, task: dict, slide_count: int) -> list[str]:
    topic = " ".join([
        str(answers.get("topic") or ""),
        str(task.get("topic") or ""),
        str(answers.get("scenario") or ""),
    ]).lower()
    if any(key in topic for key in ["大模型推理", "llm inference", "inference", "推理技术"]):
        seeds = [
            "封面",
            "目录",
            "为什么推理效率成为核心瓶颈",
            "推理工作负载变化：长上下文、Agent 与多租户",
            "瓶颈地图：计算、存储、通信与调度",
            "KV Cache 容量与带宽挑战",
            "Prefill/Decode 资源差异",
            "连续批处理与调度策略",
            "分布式集群推理相关工作",
            "推理优化技术全景",
            "大模型推理优化拆解",
            "算法-系统-算子-硬件协同框架",
            "投机解码与并行生成",
            "SpecEE/SpecDiff/SpeContext 课题组进展",
            "semi-PD 与 Prefill/Decode 分离",
            "vLLM、SGLang、Orca、Mooncake 系统对比",
            "KV Cache 管理与长上下文",
            "融合式与分离式实例分析",
            "通信重叠与 FlashOverlap",
            "Attention、GEMM 与 GroupGEMM 算子优化",
            "AWQ、GPTQ 与量化压缩部署边界",
            "昇腾与国产硬件适配实践",
            "云端推理集群资源编排",
            "端云协同与边缘推理",
            "内部实践、合作实践与引用边界",
            "新人阅读路线",
            "如何从论文形成研究问题",
            "未来方向：Agent 推理系统",
            "开放问题与学生课题",
            "总结与下一步",
        ]
    else:
        seeds = [
            "封面",
            "目录",
            "背景与目标",
            "关键问题",
            "资料与证据概览",
            "相关方案对比",
            "核心方法",
            "机制拆解",
            "数据与结果",
            "工程实践",
            "风险与边界",
            "路线图",
            "总结与下一步",
        ]
    if slide_count <= len(seeds):
        if slide_count >= 2:
            out = seeds[:slide_count]
            out[-1] = seeds[-1]
            return out
        return seeds[:slide_count]
    out = list(seeds[:-1])
    while len(out) < slide_count - 1:
        out.append(f"补充证据页 {len(out)}")
    out.append(seeds[-1])
    return out[:slide_count]


def _role_terms(role: str) -> set[str]:
    role = str(role or "").lower()
    mapping = {
        "cover": {"cover", "封面", "title"},
        "closing": {"closing", "summary", "总结", "thanks", "致谢", "参考"},
        "agenda": {"agenda", "目录", "outline", "汇报结构"},
        "motivation": {"motivation", "background", "背景", "趋势", "动机", "需求", "价格", "规模", "能效"},
        "problem": {"problem", "gap", "challenge", "问题", "瓶颈", "挑战", "带宽", "迁移", "成本"},
        "comparison": {"comparison", "matrix", "related", "对比", "比较", "相关工作"},
        "method": {"method", "framework", "system", "architecture", "diagram", "方法", "框架", "系统", "架构", "技术", "优化拆解", "设计层次"},
        "result": {"result", "experiment", "performance", "benchmark", "结果", "实验", "性能", "评估", "吞吐", "延迟"},
        "risk": {"risk", "roadmap", "boundary", "风险", "边界", "计划", "路线图"},
        "content": {"content", "diagram", "visual_evidence", "机制", "分析"},
    }
    return mapping.get(role, mapping["content"])


def _candidate_text_tokens(text: str) -> set[str]:
    return {t for t in re.split(r"[^A-Za-z0-9_\u4e00-\u9fff]+", str(text or "").lower()) if len(t) >= 2}


def _library_candidates_by_type(candidates: dict, object_type: str, *, limit: int = 8) -> list[dict]:
    rows = candidates.get("candidates") if isinstance(candidates, dict) else []
    return [
        item for item in rows or []
        if isinstance(item, dict) and item.get("object_type") == object_type
    ][:limit]


def _score_outline_candidate(
    slide: dict,
    candidate: dict,
    idx: int,
    slide_count: int,
    *,
    used_template_slide_ids: set[str] | None = None,
) -> float:
    title = str(slide.get("target_title") or slide.get("title") or "")
    role = str(slide.get("target_role") or "").lower()
    text = str(candidate.get("text") or "").lower()
    tokens = _candidate_text_tokens(" ".join([title, str(slide.get("target_claim") or ""), str(slide.get("topic") or "")]))
    score = float(candidate.get("score") or 0)
    candidate_role = str(candidate.get("slide_role") or "").lower()
    candidate_id = str(candidate.get("object_id") or candidate.get("slide_id") or "")
    role_terms = _role_terms(role)
    for token in tokens:
        if token in text or any(token in x or x in token for x in re.split(r"\s+", text) if len(x) >= 2):
            score += 12
    for term in role_terms:
        if term and term in text:
            score += 8
    if candidate_role:
        if role == candidate_role:
            score += 16
        elif role == "method" and candidate_role in {"method", "diagram_explanation", "visual_evidence"}:
            score += 12
        elif role == "motivation" and candidate_role in {"motivation", "visual_evidence", "content"}:
            score += 10
        elif role == "problem" and candidate_role in {"problem", "visual_evidence", "diagram_explanation"}:
            score += 10
        elif role == "result" and candidate_role in {"result", "visual_evidence"}:
            score += 12
        elif role == "comparison" and candidate_role in {"content", "diagram_explanation", "visual_evidence"} and any(k in text for k in ["对比", "比较", "matrix", "comparison"]):
            score += 10
    if any(key in text for key in ["高效大模型推理", "大模型推理", "模型推理", "llm", "inference"]):
        score += 18
    if "汇报展示" in text:
        score += 8
    if role == "cover" or idx == 1:
        score += 24 if candidate_role == "cover" or "cover" in text or "封面" in text else -12
    elif candidate_role == "cover" or "cover" in text or "封面" in text:
        score -= 28
    if role in {"closing", "summary"} or idx == slide_count:
        score += 24 if candidate_role == "closing" or "closing" in text or "summary" in text or "总结" in text else -10
    elif candidate_role == "closing" or "closing" in text or "summary" in text or "总结" in text:
        score -= 22
    if role not in {"cover", "closing", "agenda"} and candidate_role in {"agenda"}:
        score -= 18
    if used_template_slide_ids and candidate_id in used_template_slide_ids:
        score -= 80
    if "paper_share" in str(candidate.get("object_id") or "") and "大模型" not in text and "llm" not in text:
        score -= 12
    return score


def _best_template_slide_for_outline(
    slide: dict,
    template_slides: list[dict],
    idx: int,
    slide_count: int,
    *,
    used_template_slide_ids: set[str] | None = None,
) -> dict:
    ranked = [
        (
            _score_outline_candidate(
                slide,
                item,
                idx,
                slide_count,
                used_template_slide_ids=used_template_slide_ids,
            ),
            str(item.get("object_id") or ""),
            item,
        )
        for item in template_slides
        if isinstance(item, dict)
    ]
    ranked = [row for row in ranked if row[0] > 0]
    ranked.sort(key=lambda row: (-row[0], row[1]))
    if not ranked:
        return {}
    best = dict(ranked[0][2])
    best["outline_match_score"] = round(ranked[0][0], 3)
    return best


def _template_slide_profile_candidates() -> list[dict]:
    library = template_library.load(ensure=True)
    data = library.get("slide_profiles") or {}
    deck_rows = (library.get("deck_profiles") or {}).get("decks") or []
    decks = {
        str(item.get("deck_id")): item
        for item in deck_rows
        if isinstance(item, dict) and item.get("deck_id")
    }
    out = []
    for item in data.get("slides") or []:
        if not isinstance(item, dict):
            continue
        deck = decks.get(str(item.get("deck_id"))) or {}
        text = " ".join([
            str(deck.get("source_path") or ""),
            str(deck.get("template_type") or ""),
            str(item.get("slide_role") or ""),
            str(item.get("title") or ""),
            str(item.get("claim") or ""),
            str(item.get("what_this_slide_explains") or ""),
            str(item.get("visual_logic") or ""),
            " ".join(str(x) for x in item.get("text_samples") or []),
        ])
        out.append({
            "object_id": item.get("slide_id"),
            "object_type": "slide",
            "deck_id": item.get("deck_id"),
            "slide_id": item.get("slide_id"),
            "text": text,
            "score": 0,
            "slide_role": item.get("slide_role"),
            "template_svg": item.get("template_svg"),
            "source_path": deck.get("source_path"),
            "template_type": deck.get("template_type"),
            "template_scope": deck.get("template_scope"),
            "slide_index": item.get("slide_index"),
            "title": item.get("title"),
        })
    return out


def _source_candidate_from_template_slide(tpl: dict) -> dict:
    return {
        "source_type": "template_library_slide",
        "object_id": tpl.get("object_id"),
        "deck_id": tpl.get("deck_id"),
        "source_slide_index": tpl.get("slide_index"),
        "template_svg": tpl.get("template_svg"),
        "why_match": tpl.get("text") or "",
        "score": tpl.get("outline_match_score") or tpl.get("score"),
        "reuse_mode": "adapt_structure",
        "semantic_audit_required": True,
    }


def _source_candidate_from_asset(asset: dict) -> dict:
    asset_type = asset.get("asset_type") or asset.get("type")
    mode = "direct_asset_reuse" if asset_type == "source_figure" else "partial_slide_reuse" if asset_type == "source_slide_svg" else "direct_asset_reuse"
    return {
        "source_type": asset_type,
        "path": asset.get("path"),
        "source_deck": asset.get("source_deck"),
        "source_slide_index": asset.get("source_slide_index"),
        "why_match": asset.get("content_summary") or asset.get("caption") or "",
        "score": asset.get("match_score"),
        "reuse_mode": mode,
        "semantic_audit_required": True,
    }


def _rank_reuse_candidates(
    slide: dict,
    template_candidate: dict,
    source_assets: list[dict],
    *,
    idx: int,
    slide_count: int,
    used_source_paths: set[str] | None = None,
) -> list[dict]:
    role = str(slide.get("target_role") or "content")
    ranked: list[tuple[float, str, dict]] = []
    if template_candidate:
        candidate = _source_candidate_from_template_slide(template_candidate)
        score = float(candidate.get("score") or 0)
        if role in {"cover", "closing", "agenda"}:
            score += 6
        else:
            score -= 4
        ranked.append((score, str(candidate.get("object_id") or ""), candidate))
    for asset in source_assets:
        candidate = _source_candidate_from_asset(asset)
        score = float(asset.get("match_score") or 0)
        asset_type = str(candidate.get("source_type") or "")
        if asset_type == "source_figure":
            score += 34
        elif asset_type == "source_slide_svg":
            score += 30
        elif asset_type == "ppt_deck":
            score += 14
        elif asset_type == "image":
            score += 22
        if role in {"cover", "closing", "agenda"} and asset_type in {"source_figure", "image", "source_slide_svg"}:
            score -= 38
        if role in {"method", "problem", "result", "comparison"} and asset_type in {"source_slide_svg", "source_figure"}:
            score += 14
        if role not in {"cover", "closing", "agenda"} and asset_type in {"source_slide_svg", "source_figure", "image"}:
            score += 10
        if used_source_paths and candidate.get("path") and str(candidate["path"]) in used_source_paths:
            score -= 80
        ranked.append((score, str(candidate.get("path") or ""), candidate))
    ranked.sort(key=lambda row: (-row[0], row[1]))
    out = []
    for score, _, candidate in ranked:
        item = dict(candidate)
        item["score"] = round(score, 3)
        out.append(item)
    return out


def _run_template_library_build(project_id: str, payload: dict) -> dict:
    data = template_library.build(force=bool((payload or {}).get("force")))
    manifest = data.get("manifest") or {}
    return {
        "ok": True,
        "library_manifest": str(template_library.MANIFEST),
        "source_count": manifest.get("source_count"),
        "deck_count": manifest.get("deck_count"),
        "slide_count": manifest.get("slide_count"),
        "component_count": manifest.get("component_count"),
        "asset_count": manifest.get("asset_count"),
        "current": template_library.is_current(),
    }


def _run_template_library_query(project_id: str, payload: dict) -> dict:
    top_k = int((payload or {}).get("top_k") or 120)
    result = template_library.query_for_project(project_id, top_k=top_k)
    return {
        "ok": True,
        "template_library_candidates": str(project_dir(project_id) / "template-library-candidates.json"),
        "candidate_count": result.get("candidate_count"),
        "by_type": result.get("by_type") or {},
    }


def _run_layered_retrieval(project_id: str, payload: dict | None = None) -> dict:
    """LAYERED_RETRIEVAL: build a 3-layer candidate pool (deck / section / slide)
    drawn from BOTH the offline template library AND the project's own decomposed
    uploads. Component/asset layers are intentionally NOT retrieved here — the
    new architecture is deck→section→slide cascade only.

    Each candidate carries:
      - resource_id, deck_id, source_owner ("library"|"project"), score
      - layer-specific semantic fields (topic/audience/claim/reusability/etc.)

    Output: ``raw-layered-candidates.json`` with deck_candidates, section_candidates,
    slide_candidates arrays.

    The old name ``_run_library_retrieval`` and artifact path
    ``raw-library-candidates.json`` are kept as aliases for backward compatibility.
    """
    pdir = project_dir(project_id)

    # Load brief for coarse-filter tokens (used to focus library candidates).
    brief = read_json(pdir / "idea-analysis.json", {}) or {}
    brief = _enrich_brief_for_matching(brief)
    anchor_tokens: set[str] = set()
    # `anchor_terms` is the brief's explicit retrieval-vocabulary field (added
    # by the enrichment helper when brief schema is < 2.1).
    for src in (brief.get("anchor_terms"), brief.get("topic_tags"),
                brief.get("topic")):
        if isinstance(src, list):
            for s in src:
                if isinstance(s, str):
                    import re as _re
                    anchor_tokens.update(t for t in _re.split(r"[^\w一-鿿]+", s.lower()) if len(t) >= 2)
        elif isinstance(src, str):
            import re as _re
            anchor_tokens.update(t for t in _re.split(r"[^\w一-鿿]+", src.lower()) if len(t) >= 2)

    # Pull library candidates from BOTH the global directory tree AND the
    # project's internal tree (Phase C). Project candidates carry
    # source_owner="project" + a +1.5 score boost so the matching cascade
    # surfaces user-uploaded slides above offline library ones.
    from . import library_query
    lib = library_query.load_merged_candidates(
        project_id,
        top_k_decks=None,
        query_tokens=anchor_tokens or None,
    )
    library_manifest = lib.get("manifest") or {}
    buckets: dict[str, list] = {
        "deck": list(lib.get("deck") or []),
        "section": list(lib.get("section") or []),
        "slide": list(lib.get("slide") or []),
    }

    # Project-side candidates: read the merged deck/section/slide unit files.
    proj_decks = read_json(pdir / "project-deck-units.json", {}) or {}
    proj_sections = read_json(pdir / "project-section-units.json", {}) or {}
    proj_slides = read_json(pdir / "project-slide-units.json", {}) or {}
    PROJECT_SCORE_BOOST = 1.5

    for d in (proj_decks.get("decks") or []):
        if not isinstance(d, dict):
            continue
        buckets["deck"].append({
            "object_type": "deck",
            "object_id": d.get("deck_id"),
            "resource_id": d.get("deck_id"),
            "deck_id": d.get("deck_id"),
            "source_owner": "project",
            "score": PROJECT_SCORE_BOOST,
            "template_type": "project_upload",
            # Claude-merged fields (present if analyzer succeeded)
            "topic": d.get("topic"),
            "topic_summary": d.get("topic_summary"),
            "audience": d.get("audience"),
            "scenario": d.get("scenario"),
            "presentation_type": d.get("presentation_type"),
            "narrative_arc": d.get("narrative_arc"),
            "anchor_claims": d.get("anchor_claims"),
            "style_signature": d.get("style_signature"),
            "slide_count": d.get("slide_count"),
        })
    for sec in (proj_sections.get("sections") or []):
        if not isinstance(sec, dict):
            continue
        buckets["section"].append({
            "object_type": "section",
            "object_id": sec.get("section_id"),
            "resource_id": sec.get("section_id"),
            "deck_id": sec.get("deck_id"),
            "source_owner": "project",
            "score": PROJECT_SCORE_BOOST,
            "section_index": sec.get("section_index"),
            "role": sec.get("role"),
            "function": sec.get("function") or sec.get("narrative_function"),
            "narrative_function": sec.get("narrative_function"),
            "summary": sec.get("summary"),
            "transferable_to": sec.get("transferable_to"),
            "do_not_reuse_when": sec.get("do_not_reuse_when"),
            "key_slide_indices": sec.get("key_slide_indices"),
            "slide_ids": sec.get("slide_ids"),
        })
    for s in (proj_slides.get("slides") or []):
        if not isinstance(s, dict):
            continue
        text_samples = s.get("text_samples") or []
        buckets["slide"].append({
            "object_type": "slide",
            "object_id": s.get("slide_id"),
            "resource_id": s.get("slide_id"),
            "deck_id": s.get("deck_id"),
            "section_id": s.get("section_id"),
            "source_owner": "project",
            "score": PROJECT_SCORE_BOOST,
            "template_svg": s.get("slide_svg_ref"),
            "slide_svg_ref": s.get("slide_svg_ref"),
            "slide_role": s.get("role") or s.get("slide_role") or s.get("page_type") or "content",
            "slide_index": s.get("slide_index"),
            # Claude-merged fields
            "role": s.get("role"),
            "claim": s.get("claim"),
            "evidence_kind": s.get("evidence_kind"),
            "reusability": s.get("reusability"),
            "transferable_to": s.get("transferable_to"),
            "do_not_reuse_when": s.get("do_not_reuse_when"),
            "rewrite_guidance": s.get("rewrite_guidance"),
            "salient_visuals": s.get("salient_visuals"),
            # Raw fields
            "text_samples": text_samples,
            "title": (text_samples or [""])[0] if text_samples else "",
            "what_this_slide_explains": s.get("what_this_slide_explains"),
            "image_count": s.get("image_count"),
            "shape_count": s.get("shape_count"),
        })

    # Doc-level candidates (Claude-analyzed PDF/Word/MD).
    # ---- evidence pool (NOT used by deck/section/slide cascade) ----
    # P1: doc and figure units are evidence for GAP_RESEARCH / SLIDE_REWRITE
    # only. They no longer participate in the matching cascade. We still
    # write the pool into raw-layered-candidates.json so GAP_* can read it.
    evidence_doc_pool: list = []
    evidence_figure_pool: list = []
    proj_docs = read_json(pdir / "project-doc-units.json", {}) or {}
    for d in (proj_docs.get("doc_units") or []):
        if not isinstance(d, dict):
            continue
        if not d.get("semantic_ok"):
            continue
        evidence_doc_pool.append({
            "resource_id": d.get("doc_unit_id"),
            "source_owner": "project",
            "source_path": d.get("source_path"),
            "topic": d.get("topic"),
            "doc_type": d.get("doc_type"),
            "key_claims": d.get("key_claims"),
            "anchor_terms": d.get("anchor_terms"),
            "applicable_chapters": d.get("applicable_chapters"),
            "reusable_quotes": d.get("reusable_quotes"),
        })

    proj_figures = read_json(pdir / "project-figure-units.json", {}) or {}
    for f in (proj_figures.get("figures") or []):
        if not isinstance(f, dict):
            continue
        if not f.get("semantic_ok"):
            continue
        evidence_figure_pool.append({
            "resource_id": f.get("figure_id"),
            "source_owner": "project",
            "source_path": f.get("source_path"),
            "what_it_shows": f.get("what_it_shows"),
            "applicable_chapters": f.get("applicable_chapters"),
        })

    # Drop None-valued keys to keep the JSON compact.
    for bucket in buckets.values():
        for item in bucket:
            for k in list(item.keys()):
                if item[k] is None or item[k] == [] or item[k] == "":
                    item.pop(k, None)

    raw = {
        "schema_version": "3.1",
        "generated_at": now(),
        "project_id": project_id,
        "source": "layered_retrieval",
        "library_manifest": library_manifest,
        "query": {"anchor_tokens": sorted(anchor_tokens)} if anchor_tokens else {},
        "deck_candidates":      buckets["deck"],
        "section_candidates":   buckets["section"],
        "slide_candidates":     buckets["slide"],
        # P1: doc/figure live in an evidence pool that GAP_RESEARCH /
        # SLIDE_REWRITE consult, but cascade matching does NOT see them.
        "evidence_doc_pool":    evidence_doc_pool,
        "evidence_figure_pool": evidence_figure_pool,
        # Legacy keys preserved as empty arrays so older readers don't crash.
        "doc_candidates":       [],
        "figure_candidates":    [],
        "total_candidates":     sum(len(v) for v in buckets.values()),
        "by_type":              {k: len(v) for k, v in buckets.items()},
        "by_source_owner":      {
            "project": sum(1 for k in buckets for it in buckets[k] if it.get("source_owner") == "project"),
            "library": sum(1 for k in buckets for it in buckets[k] if it.get("source_owner") == "library"),
        },
    }
    write_json(pdir / "raw-layered-candidates.json", raw)
    # Back-compat: keep the old filename as a copy so older readers don't break
    # mid-migration.
    write_json(pdir / "raw-library-candidates.json", raw)
    return {
        "ok": True,
        "stage": "LAYERED_RETRIEVAL",
        "raw_layered_candidates": str(pdir / "raw-layered-candidates.json"),
        "by_type": raw["by_type"],
        "by_source_owner": raw["by_source_owner"],
        "total_candidates": raw["total_candidates"],
    }


# Backward-compat alias — old callers still import this name.
_run_library_retrieval = _run_layered_retrieval

def _compact_library_candidates_for_matching(raw: dict, *, per_layer_limit: int = 24) -> dict:
    """Trim raw-library-candidates.json to the fields the matching cascade needs.

    raw-library-candidates can carry hundreds of items with full SVG paths and
    profile fields; that's too much for one prompt. Keep top-N per layer with
    only the semantic fields the matcher will actually use.

    Project-owned candidates (source_owner="project") are reserved a wider quota
    than library candidates because the user's own uploads are the most likely
    legitimate source for direct reuse — when both are competing for slots, we
    surface the project's own slides first.
    """
    def trim_item(item: dict, layer: str) -> dict:
        out = {
            "resource_id": item.get("object_id") or item.get("resource_id"),
            "layer": layer,
            "score": item.get("score"),
            "deck_id": item.get("deck_id"),
            "source_owner": item.get("source_owner") or "library",
        }
        if layer == "deck":
            out["topic_summary"] = (item.get("profile") or {}).get("topic_summary")
            out["template_type"] = (item.get("profile") or {}).get("template_type")
            sem = item.get("semantic") or {}
            if sem:
                out["semantic"] = {
                    "topic": sem.get("topic"),
                    "audience": sem.get("audience"),
                    "anchor_claims": (sem.get("anchor_claims") or [])[:3],
                    "narrative_arc": (sem.get("narrative_arc") or [])[:8],
                }
        elif layer == "section":
            prof = item.get("profile") or {}
            out["narrative_function"] = prof.get("narrative_function")
            out["summary"] = (prof.get("summary") or "")[:160]
        elif layer == "slide":
            prof = item.get("profile") or {}
            out["slide_role"] = item.get("slide_role") or prof.get("slide_role")
            out["title"] = prof.get("title")
            out["claim"] = prof.get("claim")
            out["visual_logic"] = prof.get("visual_logic")
            out["template_svg"] = item.get("template_svg") or item.get("slide_svg_ref") or prof.get("template_svg")
            # Project-side slides have raw text_samples instead of a clean
            # title/claim. Include them so the matcher can actually judge the
            # content of each candidate page.
            text_samples = item.get("text_samples") or prof.get("text_samples") or []
            if text_samples:
                out["text_samples"] = [str(t)[:160] for t in text_samples[:8]]
            sem = item.get("semantic") or {}
            if sem:
                out["semantic"] = {
                    "claim": sem.get("claim"),
                    "reusability": sem.get("reusability"),
                    "transferable_to": (sem.get("transferable_to") or [])[:3],
                    "do_not_reuse_when": (sem.get("do_not_reuse_when") or [])[:2],
                    "rewrite_guidance": sem.get("rewrite_guidance"),
                }
        elif layer == "component":
            prof = item.get("profile") or {}
            out["component_type"] = prof.get("component_type") or item.get("kind")
            out["summary"] = (prof.get("summary") or item.get("text_sample") or "")[:160]
        elif layer == "asset":
            prof = item.get("profile") or {}
            out["asset_type"] = item.get("asset_type") or prof.get("asset_type")
            out["path"] = item.get("path") or item.get("asset_path") or prof.get("path")
            out["content_summary"] = (prof.get("content_summary") or item.get("filename") or "")[:160]
        return {k: v for k, v in out.items() if v is not None and v != ""}

    def _split_by_owner(items: list) -> tuple[list, list]:
        proj, lib = [], []
        for it in items or []:
            if isinstance(it, dict) and (it.get("source_owner") == "project"):
                proj.append(it)
            else:
                lib.append(it)
        return proj, lib

    def _pick(items: list, layer: str, total: int) -> list:
        # Reserve up to ~75% of slots for project-owned candidates (so the matcher
        # has more of the user's own slides than offline templates), then top up
        # with library candidates.
        proj, lib = _split_by_owner(items)
        proj_quota = min(len(proj), max(int(total * 0.75), 1))
        chosen = proj[:proj_quota] + lib[:max(0, total - proj_quota)]
        # If we still have room (project candidates are short) fill from library.
        if len(chosen) < total:
            seen = {id(x) for x in chosen}
            for x in lib:
                if id(x) in seen:
                    continue
                chosen.append(x)
                if len(chosen) >= total:
                    break
        return [trim_item(x, layer) for x in chosen]

    return {
        "library_manifest": raw.get("library_manifest") or {},
        "query": raw.get("query") or {},
        "deck_candidates":      _pick(raw.get("deck_candidates")      or [], "deck",      per_layer_limit),
        "section_candidates":   _pick(raw.get("section_candidates")   or [], "section",   per_layer_limit),
        # Slides are the layer that matters most for direct reuse — give it the
        # widest budget. 240 entries covers ~half of a typical project's slide
        # pool plus the offline library top hits.
        "slide_candidates":     _pick(raw.get("slide_candidates")     or [], "slide",     per_layer_limit * 10),
        "component_candidates": _pick(raw.get("component_candidates") or [], "component", per_layer_limit * 2),
        "asset_candidates":     _pick(raw.get("asset_candidates")     or [], "asset",     per_layer_limit * 2),
        "by_type":              raw.get("by_type") or {},
        "by_source_owner":      raw.get("by_source_owner") or {},
    }


def _run_deck_matching(project_id: str) -> dict:
    """B2 step 1: Pick ALL decks whose topic/narrative match the project well.

    Number of decks is NOT capped — we keep every deck whose
    topic_alignment >= "partial" OR confidence >= 0.5. This lets downstream
    SECTION_MATCHING draw from a wide pool. Reads brief +
    project understanding + all deck candidates (library + project).
    Writes deck-matches.json.
    """
    from . import claude_cli

    pdir = project_dir(project_id)
    brief = read_json(pdir / "idea-analysis.json", {}) or {}
    brief = _enrich_brief_for_matching(brief)
    understanding = read_json(pdir / "data/source-understanding.json", {}) or {}
    raw = read_json(pdir / "raw-layered-candidates.json", {}) or read_json(pdir / "raw-library-candidates.json", {}) or {}
    deck_candidates = raw.get("deck_candidates") or []

    context = {
        "idea_analysis": brief,
        "project_source_understanding": understanding,
        "deck_candidates": deck_candidates,
    }
    prompt = (
        "Pick **ALL decks that are genuinely relevant** to the project's topic and\n"
        "narrative arc. There is NO count limit — output every deck whose\n"
        "topic_alignment is `strong` or `partial`, AND every deck whose\n"
        "confidence >= 0.5, AND every project-owned deck. Drop only decks that are\n"
        "clearly off-topic (`topic_alignment=weak` AND `confidence<0.5`).\n"
        "\n"
        "Each kept deck gets a `recommended_use` tag:\n"
        "  - primary_narrative_source — strong topic+narrative alignment\n"
        "  - secondary_reference     — partial alignment, can contribute sections\n"
        "  - style_only_reference    — weak content but useful layout/style\n"
        "\n"
        "Return JSON only. Every resource_id you cite must appear in deck_candidates.\n\n"
        "INPUT:\n" + json.dumps(context, ensure_ascii=False)
    )
    try:
        outcome = _call_claude_json_retry(
            prompt,
            skill=["skills/matching/deck_matching.md"],
            timeout=600,
            stage_name="DECK_MATCHING",
        )
    except RuntimeError as exc:
        # Phase F.1: NO silent stub. Surface failure with retry instructions.
        return {
            "ok": False,
            "stage": "DECK_MATCHING",
            "error": str(exc),
            "retry_hint": "重跑 DECK_MATCHING — 通常是 Claude CLI 抖动",
        }
    data = outcome["data"]
    data.setdefault("schema_version", "1.0")
    data["generated_at"] = now()
    data["source"] = "claude"

    # Enrich each match with source candidate fields (source_owner, topic, etc.).
    cand_idx = {str(c.get("resource_id") or c.get("object_id")): c for c in deck_candidates if isinstance(c, dict)}
    for m in (data.get("deck_matches") or []):
        if not isinstance(m, dict):
            continue
        rid = str(m.get("resource_id") or "")
        src = cand_idx.get(rid)
        if src:
            m.setdefault("source_owner", src.get("source_owner") or "library")
            for k in ("topic", "topic_summary", "narrative_arc", "anchor_claims",
                     "slide_count", "template_type"):
                if src.get(k) is not None:
                    m.setdefault(k, src[k])

    write_json(pdir / "deck-matches.json", data)
    return {
        "ok": True,
        "stage": "DECK_MATCHING",
        "deck_matches": str(pdir / "deck-matches.json"),
        "count": len(data.get("deck_matches") or []),
        "source": data.get("source"),
    }


def _enrich_brief_for_matching(brief: dict) -> dict:
    """Synthesize fields the matching skills expect when the brief stage
    didn't emit them yet (back-compat for brief schema_version < 2.1).

    v3.0 → v2.1 backwards-compat layer:
      - If brief has `identity` (v3.0), flatten identity.* to top level
        (so legacy code reading brief.topic / brief.audience still works)
      - If brief has `synthesized_decision` (v3.0), surface deck_type to top
      - If brief has `chapter_plan` (v3.0), derive expected_sections +
        chapter_page_archetype_plan + chapter_delivery_plan + narrative_blueprint.arc
        so legacy downstream code (OUTLINE / SECTION_MATCHING / SLIDE_PLAN /
        GAP_CARD) continues to work without code changes.
      - `narrative_constraints` and `resource_anchor` pass through unchanged.

    v2.1 → richer form (original logic):
      - topic_tags / anchor_terms / expected_sections (rich) derivation
    """
    import re as _re
    out = dict(brief)

    # ──────────────────────────────────────────────────────────────────
    # v3.0 → v2.1 backwards-compat: flatten identity / synthesized_decision
    # and derive legacy chapter-level fields from chapter_plan
    # ──────────────────────────────────────────────────────────────────
    schema_v = str(brief.get("provenance", {}).get("schema_version")
                   or brief.get("schema_version") or "")

    # Flatten identity.* to top level (non-destructive: only if not already set)
    identity = brief.get("identity") or {}
    for k in ("topic", "language", "duration_minutes",
              "audience", "topic_tags", "anchor_terms", "must_have_pages"):
        if identity.get(k) is not None and out.get(k) in (None, "", [], {}):
            out[k] = identity.get(k)
    if identity.get("slide_count_target") is not None and out.get("slide_count") in (None, 0):
        out["slide_count"] = identity.get("slide_count_target")

    # Flatten synthesized_decision.deck_type
    synth = brief.get("synthesized_decision") or {}
    if synth.get("deck_type") and not out.get("deck_type"):
        out["deck_type"] = synth.get("deck_type")

    # Flatten provenance.referenced_templates / referenced_decks to top level
    # (legacy consumers may read brief.referenced_templates directly).
    provenance = brief.get("provenance") or {}
    if provenance.get("referenced_templates") and not out.get("referenced_templates"):
        out["referenced_templates"] = provenance.get("referenced_templates")
    if provenance.get("referenced_decks") and not out.get("referenced_decks"):
        out["referenced_decks"] = provenance.get("referenced_decks")

    # Derive legacy chapter-level fields from chapter_plan (v3.0 → v2.1)
    chapter_plan = brief.get("chapter_plan") or []
    if chapter_plan and isinstance(chapter_plan, list):
        # expected_sections (rich)
        if not out.get("expected_sections"):
            out["expected_sections"] = [
                {
                    "section_index": c.get("section_index", i + 1),
                    "chapter": c.get("chapter"),
                    "purpose": (c.get("purpose") or "")[:200],
                    "expected_pages": c.get("expected_pages_indicative")
                                       or c.get("expected_pages"),
                }
                for i, c in enumerate(chapter_plan) if isinstance(c, dict)
            ]
        # chapter_page_archetype_plan
        if not out.get("chapter_page_archetype_plan"):
            out["chapter_page_archetype_plan"] = [
                {
                    "chapter": c.get("chapter"),
                    "expected_pages": c.get("expected_pages_indicative")
                                       or c.get("expected_pages"),
                    "page_archetypes": c.get("page_archetypes") or [],
                }
                for c in chapter_plan if isinstance(c, dict)
            ]
        # chapter_delivery_plan
        if not out.get("chapter_delivery_plan"):
            out["chapter_delivery_plan"] = [
                {
                    "chapter": c.get("chapter"),
                    **(c.get("delivery") or {}),
                }
                for c in chapter_plan if isinstance(c, dict)
            ]
        # narrative_blueprint.arc (synth from chapter_plan)
        if not (brief.get("narrative_blueprint") or {}).get("arc"):
            out_arc = [
                {
                    "chapter": c.get("chapter"),
                    "purpose": c.get("purpose"),
                    "expected_pages": c.get("expected_pages_indicative")
                                       or c.get("expected_pages"),
                    "key_points": c.get("claims_to_make") or [],
                }
                for c in chapter_plan if isinstance(c, dict)
            ]
            nb = dict(brief.get("narrative_blueprint") or {})
            nb["arc"] = out_arc
            # Pull anchor_claims from narrative_constraints if present
            nlc = brief.get("narrative_constraints") or {}
            if nlc.get("thesis_callback", {}).get("thesis_text") and not nb.get("anchor_claims"):
                nb["anchor_claims"] = [nlc["thesis_callback"]["thesis_text"]]
            out["narrative_blueprint"] = nb

    # ──────────────────────────────────────────────────────────────────
    # Original v2.1 enrichment (back-compat for older briefs)
    # ──────────────────────────────────────────────────────────────────
    arc = (out.get("narrative_blueprint") or {}).get("arc") or []

    # 1. expected_sections rich form
    es_raw = brief.get("expected_sections") or []
    needs_rich = (
        not es_raw
        or (es_raw and not isinstance(es_raw[0], dict))
        or (es_raw and isinstance(es_raw[0], dict) and "purpose" not in es_raw[0])
    )
    if needs_rich and arc:
        out["expected_sections"] = [
            {
                "section_index": i + 1,
                "chapter": a.get("chapter") or es_raw[i] if i < len(es_raw) else a.get("chapter"),
                "purpose": (a.get("purpose") or "")[:200],
                "expected_pages": a.get("expected_pages"),
            }
            for i, a in enumerate(arc)
        ]

    # 2. topic_tags fallback
    if not out.get("topic_tags"):
        tags: list[str] = []
        for src in [
            brief.get("topic"),
            (brief.get("message_architecture") or {}).get("throughline"),
            (brief.get("narrative_blueprint") or {}).get("anchor_claims"),
        ]:
            if isinstance(src, str):
                tags.extend(t for t in _re.split(r"[^\w一-鿿]+", src) if 2 <= len(t) <= 8)
            elif isinstance(src, list):
                for s in src:
                    if isinstance(s, str):
                        tags.extend(t for t in _re.split(r"[^\w一-鿿]+", s) if 2 <= len(t) <= 8)
        # de-dup, drop generic
        BORING = {"研究", "成果", "分享", "技术", "项目", "方向", "代表性", "未来", "总结",
                  "report", "research", "based", "the", "and"}
        seen, uniq = set(), []
        for t in tags:
            tl = t.lower()
            if tl in seen or tl in BORING:
                continue
            seen.add(tl)
            uniq.append(t)
        out["topic_tags"] = uniq[:10]

    # 3. anchor_terms fallback (used by LAYERED_RETRIEVAL)
    if not out.get("anchor_terms"):
        out["anchor_terms"] = list(out.get("topic_tags") or [])

    return out


def _call_claude_json_retry(prompt: str, *, skill: list[str], timeout: int,
                             stage_name: str, max_retries: int = 3) -> dict:
    """Call Claude with retry. Phase F.1 + H: no silent fallback. Returns the raw
    `call_claude_json` outcome dict on success; raises RuntimeError after
    `max_retries` failures with the last error message.

    **Phase H**: when retry happens, the new attempt's prompt includes the
    previous attempt's partial output (raw_excerpt) and error mode, so the
    new Claude can DIAGNOSE what went wrong and continue rather than start
    from scratch. This often recovers from JSON truncation: prev attempt
    had good picks but stdout got cut → new attempt sees "I had 5 picks
    matching the schema, just need to finish".
    """
    import time as _time
    from . import claude_cli

    last_error = ""
    last_excerpt = ""
    for attempt in range(1, max_retries + 1):
        if attempt == 1:
            eff_prompt = prompt
        else:
            # Wrap previous failure context. Keep prev raw_excerpt small enough
            # to avoid bloating retry prompt beyond Claude's input limits.
            eff_prompt = (
                f"=== PREVIOUS ATTEMPT (#{attempt-1}) FAILED ===\n"
                f"failure mode: {last_error[:300]}\n\n"
                f"partial / raw output produced before dying (may be truncated):\n"
                f"```\n{last_excerpt[:5000]}\n```\n\n"
                f"DIAGNOSIS REQUEST: read the partial output above. Identify "
                f"what went wrong (truncated JSON? schema mismatch? missing "
                f"key? wrong array length?). Then produce the CORRECT and "
                f"COMPLETE output following the schema exactly. If the previous "
                f"attempt had good picks before truncating, you may KEEP "
                f"those picks and just finish; if it picked badly, fix them.\n\n"
                f"=== ORIGINAL TASK BELOW ===\n\n{prompt}"
            )
        outcome = claude_cli.call_claude_json(eff_prompt, skill=skill, timeout=timeout)
        if outcome.get("ok") and isinstance(outcome.get("data"), dict):
            return outcome
        last_error = outcome.get("error") or "no data returned"
        last_excerpt = outcome.get("raw_excerpt") or ""
        print(f"[{stage_name}] attempt {attempt}/{max_retries} failed: {last_error[:300]}", flush=True)
        if attempt < max_retries:
            _time.sleep(2 ** attempt)  # 2s, 4s
    raise RuntimeError(
        f"{stage_name} failed after {max_retries} attempts. "
        f"last error: {last_error}. "
        f"raw excerpt: {last_excerpt[:400]}"
    )


def _run_section_matching(project_id: str) -> dict:
    """B2 step 2: Within the matched decks, match each project's target section to one source section."""
    from . import claude_cli

    pdir = project_dir(project_id)
    brief = read_json(pdir / "idea-analysis.json", {}) or {}
    brief = _enrich_brief_for_matching(brief)
    deck_match_doc = read_json(pdir / "deck-matches.json", {}) or {}
    raw = read_json(pdir / "raw-layered-candidates.json", {}) or read_json(pdir / "raw-library-candidates.json", {}) or {}

    matched_deck_ids = {str(m.get("resource_id")) for m in (deck_match_doc.get("deck_matches") or []) if isinstance(m, dict)}
    section_candidates = [s for s in (raw.get("section_candidates") or [])
                          if isinstance(s, dict) and str(s.get("deck_id")) in matched_deck_ids]

    matched_decks_brief = [
        {"resource_id": m.get("resource_id"),
         "topic": m.get("topic") or m.get("topic_summary"),
         "narrative_arc": m.get("narrative_arc"),
         "source_owner": m.get("source_owner")}
        for m in (deck_match_doc.get("deck_matches") or []) if isinstance(m, dict)
    ]

    context = {
        "idea_analysis": brief,
        "matched_decks": matched_decks_brief,
        "section_candidates": section_candidates,
    }
    prompt = (
        "Match each target section to **ALL relevant source sections** (wide intake — no count limit).\n"
        "A target chapter typically maps to 3-8 source sections from across the matched decks;\n"
        "1-to-many is the norm, not the exception. SLIDE_MATCHING downstream will refine.\n"
        "\n"
        "Two dimensions for inclusion (keep section if EITHER is met):\n"
        "  (1) purpose_alignment ∈ {strong, partial}: source section's role/function matches\n"
        "      target chapter's purpose (e.g. motivation→motivation, method→method).\n"
        "  (2) content_overlap_score >= 0.5: source section's title/summary/transferable_to\n"
        "      shares terms with brief.anchor_terms / topic_tags / target chapter keywords.\n"
        "Only drop sections where BOTH purpose_alignment=weak AND content_overlap_score<0.4.\n"
        "\n"
        "Project-owned sections (source_owner=project) should be prioritized.\n"
        "Return JSON only. resource_id must come from section_candidates;\n"
        "deck_id must be one of matched_decks.\n\n"
        "INPUT:\n" + json.dumps(context, ensure_ascii=False)
    )
    try:
        outcome = _call_claude_json_retry(
            prompt,
            skill=["skills/matching/section_matching.md"],
            timeout=600,
            stage_name="SECTION_MATCHING",
        )
    except RuntimeError as exc:
        return {
            "ok": False,
            "stage": "SECTION_MATCHING",
            "error": str(exc),
            "retry_hint": "重跑 SECTION_MATCHING — 通常是 Claude CLI 抖动",
        }
    data = outcome["data"]
    data.setdefault("schema_version", "1.0")
    data["generated_at"] = now()
    data["source"] = "claude"

    # Enrich each match with section candidate fields (slide_ids, role, etc.).
    cand_idx = {str(c.get("resource_id") or c.get("object_id")): c for c in section_candidates}
    for m in (data.get("section_matches") or []):
        if not isinstance(m, dict):
            continue
        rid = str(m.get("resource_id") or "")
        src = cand_idx.get(rid)
        if src:
            m.setdefault("source_owner", src.get("source_owner") or "library")
            for k in ("slide_ids", "section_index", "role", "function", "summary", "deck_id"):
                if src.get(k) is not None:
                    m.setdefault(k, src[k])

    write_json(pdir / "section-matches.json", data)
    return {
        "ok": True,
        "stage": "SECTION_MATCHING",
        "section_matches": str(pdir / "section-matches.json"),
        "count": len(data.get("section_matches") or []),
        "uncovered_count": len(data.get("uncovered_target_sections") or []),
        "source": data.get("source"),
    }


def _build_target_pages_for_slide_matching(project_id: str, section_match_doc: dict) -> list[dict]:
    """Derive per-page target pages from brief + section_matches.

    Produces a list of ``{target_slide_index, target_role, page_purpose,
    claim_to_prove}`` for SLIDE_MATCHING input. Page count follows
    brief.slide_count; first/last 2-3 pages are cover/agenda/closing, the
    rest are distributed across matched sections by ``expected_slide_count``.
    """
    pdir = project_dir(project_id)
    brief = read_json(pdir / "idea-analysis.json", {}) or {}
    try:
        total = int(brief.get("slide_count") or 12)
    except Exception:
        total = 12
    # Fallback: pull from question-state.json if brief didn't record it.
    if not brief.get("slide_count"):
        qs = read_json(pdir / "question-state.json", {}) or {}
        qs_count = (qs.get("answers") or {}).get("slide_count")
        try:
            if qs_count:
                total = int(qs_count)
        except Exception:
            pass

    section_matches = section_match_doc.get("section_matches") or []
    uncovered = section_match_doc.get("uncovered_target_sections") or []

    pages: list[dict] = []
    # Cover
    pages.append({"target_slide_index": 1, "target_role": "cover",
                  "page_purpose": "封面：建立汇报身份与主题", "claim_to_prove": ""})
    # Agenda (only when total >= 6 — for short decks skip agenda)
    next_idx = 2
    if total >= 6:
        pages.append({"target_slide_index": next_idx, "target_role": "agenda",
                      "page_purpose": "全局目录页", "claim_to_prove": ""})
        next_idx += 1

    closing_pages = 1
    if total >= 30:
        closing_pages = 2  # closing + thanks/references
    body_budget = total - len(pages) - closing_pages

    # Distribute body budget across matched sections proportional to expected_slide_count.
    sec_entries = [m for m in section_matches if isinstance(m, dict)]
    if sec_entries:
        total_expected = sum(int(m.get("expected_slide_count") or 1) for m in sec_entries) or len(sec_entries)
        sec_pages_remaining = body_budget
        for i, m in enumerate(sec_entries):
            if i == len(sec_entries) - 1:
                sec_count = max(1, sec_pages_remaining)
            else:
                share = int(m.get("expected_slide_count") or 1)
                sec_count = max(1, round(body_budget * share / total_expected))
                sec_count = min(sec_count, sec_pages_remaining - (len(sec_entries) - i - 1))
                sec_count = max(sec_count, 1)
            sec_pages_remaining -= sec_count
            for k in range(sec_count):
                pages.append({
                    "target_slide_index": next_idx,
                    "target_role": m.get("role") or "content",
                    "page_purpose": f"{m.get('target_section_purpose') or '内容页'} (本节第 {k+1}/{sec_count} 页)",
                    "claim_to_prove": "",
                    "_section_match": {
                        "target_section_index": m.get("target_section_index"),
                        "section_resource_id": m.get("resource_id"),
                        "slide_ids": m.get("slide_ids") or [],
                    },
                })
                next_idx += 1
        # If we under-counted, pad with content pages
        while len(pages) + closing_pages < total:
            pages.append({"target_slide_index": next_idx, "target_role": "content",
                          "page_purpose": "补充内容页", "claim_to_prove": ""})
            next_idx += 1
    else:
        # No matched sections — fill with content placeholders.
        while len(pages) + closing_pages < total:
            pages.append({"target_slide_index": next_idx, "target_role": "content",
                          "page_purpose": "无匹配 section，DRAFT 将走 placeholder", "claim_to_prove": ""})
            next_idx += 1

    # Closing pages
    for i in range(closing_pages):
        role = "closing" if i == 0 else "references"
        pages.append({"target_slide_index": next_idx,
                      "target_role": role,
                      "page_purpose": "总结收尾" if role == "closing" else "参考文献",
                      "claim_to_prove": ""})
        next_idx += 1
    return pages[:total]


def _run_slide_matching(project_id: str, payload: dict | None = None) -> dict:
    """B2 step 3: For each target page from outline.json, pick one slide_id
    or leave null (placeholder).

    Now reads outline.json directly so target_pages have explicit key_points
    and needed_evidence that Claude can use to judge candidate relevance.

    payload (optional):
      - retry_sections: list[int] — only re-run these section_index batches,
        reusing the existing slide-matches.json for other sections. Used to
        cheaply re-do batches that hit Claude CLI transients.
    """
    from . import claude_cli

    pdir = project_dir(project_id)
    brief = read_json(pdir / "idea-analysis.json", {}) or {}
    qs = read_json(pdir / "question-state.json", {}) or {}
    answers = qs.get("answers") if isinstance(qs, dict) else {}
    outline_doc = read_json(pdir / "outline.json", {}) or {}
    section_match_doc = read_json(pdir / "section-matches.json", {}) or {}
    raw = read_json(pdir / "raw-layered-candidates.json", {}) or read_json(pdir / "raw-library-candidates.json", {}) or {}
    reuse_rate_hint = _parse_reuse_rate_from_text(
        (answers or {}).get("reuse_policy"),
        (answers or {}).get("direct_slide_reuse_policy"),
    )

    outline_slides = outline_doc.get("slides") if isinstance(outline_doc.get("slides"), list) else []
    if not outline_slides:
        # Fallback: synthesize target_pages from brief if outline is missing.
        outline_slides = _build_target_pages_for_slide_matching(project_id, section_match_doc)

    # P20a: bypass + scoped cascade
    # ────────────────────────────
    # Outline (post-P19/Phase 5) already binds many slides to specific library
    # carriers via source_carrier_resource_kind=carrier_bound + source_resource_ids
    # = [{deck_id, slide_id, rank_score, match_reasons}]. Re-running the full
    # cascade for those slides is pure waste. Split:
    #   - carrier_bound → synthesize slide_matches entry directly from outline
    #   - matching_fallback (or unknown kind / empty source_resource_ids) →
    #     pass to the existing cascade (filtered subset only)
    bound_slide_matches: list[dict] = []
    fallback_outline_slides: list[dict] = []
    for s in outline_slides:
        if not isinstance(s, dict):
            continue
        kind = s.get("source_carrier_resource_kind")
        src_ids = s.get("source_resource_ids") or []
        # Only treat as bound when kind=carrier_bound AND source_resource_ids is a
        # list of dicts containing slide_id (the outline's resolved binding).
        is_bound = (
            kind == "carrier_bound"
            and isinstance(src_ids, list)
            and src_ids
            and isinstance(src_ids[0], dict)
            and src_ids[0].get("slide_id")
        )
        if is_bound:
            target_idx = s.get("slide_index") or s.get("target_slide_index")
            candidates = []
            for rank, cand in enumerate(src_ids, start=1):
                if not isinstance(cand, dict):
                    continue
                candidates.append({
                    "rank": rank,
                    "resource_id": cand.get("slide_id"),
                    "deck_id": cand.get("deck_id"),
                    "score": cand.get("rank_score"),
                    "confidence": "high" if (cand.get("rank_score") or 0) >= 1.5 else "medium",
                    "recommended_reuse_mode": "direct_slide_reuse",
                    "match_reasons": cand.get("match_reasons") or [],
                    "source_owner": "library",
                    "source": "outline_carrier_bound",
                })
            bound_slide_matches.append({
                "target_slide_index": target_idx,
                "target_role": s.get("target_role"),
                "target_title": s.get("target_title"),
                "target_claim": s.get("target_claim"),
                "section_index": s.get("section_index"),
                "candidates": candidates,
                "source": "outline_carrier_bound",
            })
        else:
            fallback_outline_slides.append(s)

    print(
        f"[slide-matching] outline carrier-bound: {len(bound_slide_matches)} pages "
        f"(direct bypass), matching_fallback: {len(fallback_outline_slides)} pages "
        f"(will run cascade)",
        flush=True,
    )

    # The remaining cascade processes only fallback slides. If everything is
    # carrier-bound, the cascade has nothing to do — short-circuit with the
    # synthesized matches only.
    if not fallback_outline_slides:
        print("[slide-matching] all pages bound; skipping cascade entirely", flush=True)
        data = {
            "schema_version": "2.1",
            "generated_at": now(),
            "source": "outline_carrier_bound_only",
            "slide_matches": bound_slide_matches,
        }
        write_json(pdir / "slide-matches.json", data)
        # Emit compat matched-resource-pack.json with the bound matches flattened
        flat = []
        for m in bound_slide_matches:
            for c in m.get("candidates") or []:
                flat.append({
                    "resource_id": c.get("resource_id"),
                    "target_slide_index": m.get("target_slide_index"),
                    "candidate_rank": c.get("rank"),
                    "target_slide_hint": m.get("target_role"),
                    "recommended_reuse_mode": c.get("recommended_reuse_mode"),
                    "deck_id": c.get("deck_id"),
                    "confidence": c.get("confidence"),
                    "score": c.get("score"),
                    "source_owner": c.get("source_owner"),
                })
        write_json(pdir / "matched-resource-pack.json", {
            "schema_version": "2.0",
            "generated_at": now(),
            "source": "outline_carrier_bound_only",
            "deck_level_matches": [],
            "section_level_matches": [],
            "slide_level_matches": flat,
            "component_level_matches": [],
            "asset_level_matches": [],
            "coverage_note": "all pages carrier-bound from outline",
        })
        return {
            "ok": True, "stage": "SLIDE_MATCHING",
            "slide_matches": str(pdir / "slide-matches.json"),
            "matched_resource_pack": str(pdir / "matched-resource-pack.json"),
            "source": "outline_carrier_bound_only",
            "carrier_bound_count": len(bound_slide_matches),
            "cascade_count": 0,
            "target_pages": len(outline_slides),
            "covered_targets": len(bound_slide_matches),
            "placeholder_targets": 0,
        }

    # Otherwise: continue with the existing cascade BUT scope it to fallback only.
    outline_slides = fallback_outline_slides


    target_pages = [
        {
            "target_slide_index": s.get("slide_index") or s.get("target_slide_index"),
            "target_role": s.get("target_role"),
            "target_title": s.get("target_title"),
            "target_claim": s.get("target_claim") or s.get("target_claim_hint"),
            "page_purpose": s.get("page_purpose"),
            "key_points": s.get("key_points") or [],
            "needed_evidence": s.get("needed_evidence") or [],
            "expected_resource_kind": s.get("expected_resource_kind"),
            "anchor_terms": s.get("anchor_terms") or [],
            "section_index": s.get("section_index"),
        }
        for s in outline_slides if isinstance(s, dict)
    ]

    # Restrict candidate pool to slides inside matched sections (or wider).
    matched_section_ids = {str(m.get("resource_id")) for m in (section_match_doc.get("section_matches") or []) if isinstance(m, dict)}
    matched_section_doc_slide_ids: set[str] = set()
    for m in (section_match_doc.get("section_matches") or []):
        if not isinstance(m, dict):
            continue
        for sid in (m.get("slide_ids") or []):
            matched_section_doc_slide_ids.add(str(sid))

    candidate_pool: list[dict] = []
    seen_rids: set[str] = set()
    # Phase 1: STRONG pool — slides from matched sections (high context coherence).
    for s in (raw.get("slide_candidates") or []):
        if not isinstance(s, dict):
            continue
        sid = str(s.get("resource_id") or s.get("object_id"))
        sec = str(s.get("section_id") or "")
        if sid in seen_rids:
            continue
        if sec in matched_section_ids or sid in matched_section_doc_slide_ids:
            candidate_pool.append(s)
            seen_rids.add(sid)

    # Phase 2: WIDE pool — anchor-term/keyword retrieval across the entire
    # library + project slide pool. This ensures every target page can find a
    # candidate even if it's not in a matched section. Top-N by keyword overlap
    # with outline.anchor_terms + outline.key_points.
    import re as _re
    # Build the outline "search bag" once
    bag_terms: set[str] = set()
    for sp in target_pages:
        for t in (sp.get("anchor_terms") or []):
            if isinstance(t, str) and t.strip():
                bag_terms.add(t.strip())
        for kp in (sp.get("key_points") or []):
            if isinstance(kp, str):
                for tok in _re.findall(r"[A-Za-z一-鿿][A-Za-z0-9一-鿿/_+\-]{1,}", kp):
                    if len(tok) >= 2:
                        bag_terms.add(tok)
        title = sp.get("target_title") or ""
        for tok in _re.findall(r"[A-Za-z一-鿿][A-Za-z0-9一-鿿/_+\-]{1,}", title):
            if len(tok) >= 2:
                bag_terms.add(tok)
    # Drop overly generic terms
    bag_terms.discard("本页")
    bag_terms.discard("page")

    # Load all library slide candidates from the new directory tree so we
    # see all ~1500 slides (Phase B refactor — replaces old SLIDE_PROFILES).
    try:
        from . import library_query
        all_lib_slides = library_query.load_library_candidates().get("slide") or []
    except Exception:
        all_lib_slides = []
    proj_slide_units = read_json(pdir / "project-slide-units.json", {}) or {}
    all_proj_slides = proj_slide_units.get("slides") or []

    def _score_candidate(slide: dict) -> int:
        if not isinstance(slide, dict):
            return 0
        # Semantic-only scoring: title/claim/explains/text_samples/transferable_to/
        # rewrite_guidance. `salient_visuals` (visual skeleton description like
        # "六宫格" or "层次架构图") is INTENTIONALLY excluded — keyword matches
        # against visual descriptors caused off-topic source slides to be picked
        # for their layout similarity rather than content alignment (e.g. a
        # "四类受限" hardware slide getting picked for a "六类挑战" target page
        # just because both used a multi-cell grid layout).
        text_pool = " ".join([
            str(slide.get("title") or ""),
            str(slide.get("claim") or ""),
            str(slide.get("what_this_slide_explains") or ""),
            " ".join(str(t) for t in (slide.get("text_samples") or [])),
            " ".join(str(t) for t in (slide.get("transferable_to") or [])),
            str(slide.get("rewrite_guidance") or ""),
        ])
        return sum(1 for term in bag_terms if term and term in text_pool)

    def _normalize_lib_slide(s: dict) -> dict:
        return {
            "resource_id": s.get("slide_id"),
            "object_id": s.get("slide_id"),
            "deck_id": s.get("deck_id"),
            "section_id": s.get("section_id"),
            "source_owner": "library",
            "slide_index": s.get("slide_index"),
            "slide_role": s.get("slide_role"),
            "role": s.get("role"),
            "title": s.get("title"),
            "claim": s.get("claim"),
            "what_this_slide_explains": s.get("what_this_slide_explains"),
            "evidence_kind": s.get("evidence_kind"),
            "reusability": s.get("reusability"),
            "transferable_to": s.get("transferable_to"),
            "do_not_reuse_when": s.get("do_not_reuse_when"),
            "rewrite_guidance": s.get("rewrite_guidance"),
            "salient_visuals": s.get("salient_visuals"),
            "template_svg": s.get("template_svg"),
            "text_samples": s.get("text_samples") or [],
            "image_count": s.get("image_count"),
            "shape_count": s.get("shape_count"),
        }

    def _normalize_proj_slide(s: dict) -> dict:
        return {
            "resource_id": s.get("slide_id"),
            "object_id": s.get("slide_id"),
            "deck_id": s.get("deck_id"),
            "section_id": s.get("section_id"),
            "source_owner": "project",
            "slide_index": s.get("slide_index"),
            "slide_role": s.get("role") or s.get("slide_role"),
            "role": s.get("role"),
            "title": (s.get("text_samples") or [""])[0] if s.get("text_samples") else "",
            "claim": s.get("claim"),
            "evidence_kind": s.get("evidence_kind"),
            "reusability": s.get("reusability"),
            "transferable_to": s.get("transferable_to"),
            "rewrite_guidance": s.get("rewrite_guidance"),
            "salient_visuals": s.get("salient_visuals"),
            "template_svg": s.get("slide_svg_ref"),
            "text_samples": s.get("text_samples") or [],
            "image_count": s.get("image_count"),
            "shape_count": s.get("shape_count"),
        }

    scored: list[tuple[int, dict]] = []
    for s in all_lib_slides:
        rid = str(s.get("slide_id") or "")
        if rid in seen_rids:
            continue
        sc = _score_candidate(s)
        if sc > 0:
            scored.append((sc, _normalize_lib_slide(s)))
    for s in all_proj_slides:
        rid = str(s.get("slide_id") or "")
        if rid in seen_rids:
            continue
        # Project slides get a +2 boost so they always sort to the top when relevant.
        sc = _score_candidate(s) + 2
        if sc > 0:
            scored.append((sc, _normalize_proj_slide(s)))
    scored.sort(key=lambda x: x[0], reverse=True)
    WIDE_POOL_CAP = 200
    for _, cand in scored[:WIDE_POOL_CAP]:
        rid = str(cand.get("resource_id") or "")
        if rid in seen_rids:
            continue
        candidate_pool.append(cand)
        seen_rids.add(rid)

    # Phase I.fix2: structural-role candidates (cover/toc/chapter/ending) often
    # have generic titles ("封面"/"目录"/章节名) that score 0 on topic anchor-term
    # filter, so they get dropped from the WIDE pool. But they're EXACTLY the
    # candidates we need for cover/agenda/section_divider/closing/references
    # rows. Inject ALL of them unconditionally — adds ~130 slides to the pool.
    STRUCTURAL_ROLES = {"cover_candidate", "toc_candidate", "chapter_candidate",
                        "ending_candidate"}
    for s in all_lib_slides:
        if s.get("页面角色") not in STRUCTURAL_ROLES and \
           s.get("slide_role") not in STRUCTURAL_ROLES:
            continue
        rid = str(s.get("slide_id") or "")
        if not rid or rid in seen_rids:
            continue
        candidate_pool.append(_normalize_lib_slide(s))
        seen_rids.add(rid)

    # If still empty (no matched sections, no keyword hits), take top of raw.
    if not candidate_pool:
        for s in (raw.get("slide_candidates") or []):
            if not isinstance(s, dict):
                continue
            sid = str(s.get("resource_id") or s.get("object_id"))
            if sid in seen_rids:
                continue
            candidate_pool.append(s)
            seen_rids.add(sid)

    # Compact candidate (trim heavy fields).
    def _trim(c: dict) -> dict:
        return {k: c.get(k) for k in [
            "resource_id", "deck_id", "section_id", "source_owner",
            "slide_index", "slide_role", "role", "title", "claim",
            "what_this_slide_explains", "evidence_kind", "reusability",
            "transferable_to", "do_not_reuse_when", "rewrite_guidance",
            "salient_visuals", "text_samples", "template_svg",
            "image_count", "shape_count",
            # Phase B: new tree-schema fields
            "prev_slide_role", "next_slide_role",
            "score", "adjacency_bonus",
        ] if c.get(k) is not None}

    slide_candidates_compact = [_trim(c) for c in candidate_pool]
    target_reuse_rate = float((brief.get("reuse_strategy") or {}).get("target_reuse_rate") or reuse_rate_hint)

    # Phase H + I: section-based parallel batching with TRUE hierarchical narrowing.
    # - Each batch = one chapter's target_pages → coherent narrative within batch
    # - Sections run in parallel via ThreadPoolExecutor
    # - Per-section retry uses _call_claude_json_retry (smart retry with prev-attempt context)
    # - Phase I: per-section candidate pool = STRONG (this section's matched
    #   source slides) + STRUCTURAL (cover/agenda/divider templates when target_role
    #   needs them) + small WIDE fallback (top-K by anchor-term score from same deck)
    #   — rather than every section seeing all 1580 candidates
    from collections import defaultdict as _dd
    import concurrent.futures as _cf

    by_sec: dict[int, list[dict]] = _dd(list)
    for tp in target_pages:
        si = tp.get("section_index")
        try:
            si_int = int(si) if si is not None else 0
        except (TypeError, ValueError):
            si_int = 0
        by_sec[si_int].append(tp)
    section_indices = sorted(by_sec.keys())

    # payload.retry_sections: only re-run these sections, reuse existing results
    # for the rest. Saves Claude CLI calls when a previous run had partial failures.
    payload = payload or {}
    retry_sections_raw = payload.get("retry_sections") or []
    try:
        retry_sections = {int(x) for x in retry_sections_raw if x is not None}
    except (TypeError, ValueError):
        retry_sections = set()
    existing_matches_by_target: dict[int, dict] = {}
    if retry_sections:
        existing_doc = read_json(pdir / "slide-matches.json", {}) or {}
        for m in (existing_doc.get("slide_matches") or []):
            if isinstance(m, dict) and m.get("target_slide_index") is not None:
                try:
                    existing_matches_by_target[int(m["target_slide_index"])] = m
                except Exception:
                    pass
        # Restrict the batch list to retry_sections; everything else will be
        # pulled from existing_matches_by_target after the run.
        section_indices = [i for i in section_indices if i in retry_sections]
        print(f"[SLIDE_MATCHING] retry_sections active: {sorted(retry_sections)}; "
              f"will re-run {len(section_indices)} of "
              f"{len(by_sec)} sections, reuse rest from prior slide-matches.json",
              flush=True)
    print(f"[SLIDE_MATCHING] section batching: {len(section_indices)} sections, "
          f"sizes={[len(by_sec[i]) for i in section_indices]}", flush=True)

    # Phase I: build a per-target-section strong-pool index.
    # section_matches[i].slide_ids gives the source slide_ids that match THIS target section.
    sec_strong_slide_ids: dict[int, set[str]] = {}
    sec_strong_section_ids: dict[int, set[str]] = {}
    for m in (section_match_doc.get("section_matches") or []):
        if not isinstance(m, dict):
            continue
        tsi = m.get("target_section_index")
        try:
            tsi_int = int(tsi) if tsi is not None else None
        except (TypeError, ValueError):
            tsi_int = None
        if tsi_int is None:
            continue
        sec_strong_slide_ids.setdefault(tsi_int, set()).update(
            str(x) for x in (m.get("slide_ids") or []))
        rid = m.get("resource_id")
        if rid:
            sec_strong_section_ids.setdefault(tsi_int, set()).add(str(rid))

    # Phase I.fix2: structural-role candidate pool — use the library's actual
    # role enum values (页面角色 → slide_role mapping in library_query):
    #   cover_candidate   (22)  → cover
    #   toc_candidate     (35)  → agenda          ← was 0 due to wrong keyword
    #   chapter_candidate (36)  → section_divider ← was 0 due to wrong keyword
    #   ending_candidate  (41)  → closing / references (split by title)
    # Previous keyword-based matching ("agenda" in role / "divider" in role) hit 0
    # for the agenda + chapter pools, forcing cascade to pick from content_candidate
    # pool — that's why v7 dividers all got "层次2:算法优化" (a content slide that
    # happens to look like a chapter封面).
    structural_candidates: dict[str, list[dict]] = {
        "cover": [], "agenda": [], "section_divider": [],
        "closing": [], "references": [],
    }
    REFS_TITLE_HINTS = ("参考文献", "references", "致谢", "thanks", "q&a", "questions")
    for c in slide_candidates_compact:
        role = (c.get("slide_role") or c.get("role") or "")
        role_lc = role.lower()
        title = str(c.get("title") or "")
        title_lc = title.lower()
        # Match by exact library enum first; fall back to title hints.
        if role == "cover_candidate" or "cover" in role_lc:
            structural_candidates["cover"].append(c)
        elif role == "toc_candidate" or "目录" in title or "议程" in title or "提纲" in title:
            structural_candidates["agenda"].append(c)
        elif role == "chapter_candidate" or "章节封面" in title or "section_divider" in role_lc:
            structural_candidates["section_divider"].append(c)
        elif role == "ending_candidate":
            # Split ending_candidate into closing vs references by title hint.
            if any(h in title_lc for h in REFS_TITLE_HINTS):
                structural_candidates["references"].append(c)
            else:
                structural_candidates["closing"].append(c)
        elif "reference" in role_lc or "参考" in title:
            structural_candidates["references"].append(c)
        elif "closing" in role_lc or "总结" in title or "结尾" in title:
            structural_candidates["closing"].append(c)

    # If divider pool is empty, fall back to agenda; if agenda also empty, fall
    # back to chapter_candidate-tagged-but-missed via title contains "章".
    if not structural_candidates["section_divider"]:
        structural_candidates["section_divider"] = list(structural_candidates["agenda"])
    if not structural_candidates["agenda"]:
        structural_candidates["agenda"] = list(structural_candidates["section_divider"])

    print(f"[SLIDE_MATCHING] structural pool: cover={len(structural_candidates['cover'])} "
          f"agenda={len(structural_candidates['agenda'])} "
          f"divider={len(structural_candidates['section_divider'])} "
          f"closing={len(structural_candidates['closing'])} "
          f"refs={len(structural_candidates['references'])}", flush=True)

    def _section_timeout(n: int) -> int:
        """Dynamic timeout: 900s base + 90s/slide, capped at 3600s (60 min)."""
        return min(3600, 900 + n * 90)

    def _build_section_pool(sec_idx: int, sec_pages: list[dict]) -> list[dict]:
        """Phase I.fix: each section sees the FULL candidate pool (~270 slides)
        rather than a narrowed strong+wide subset. Phase I's narrowing dropped
        content reuse from 93% → 83% because Claude couldn't find good fallbacks
        when the matched section's slides weren't a perfect fit.

        Layering retained as TIER LABELS only (for prompt-side guidance):
          - strong: slides inside the matched source section for THIS sec_idx
          - same_deck: other slides in matched-section's deck
          - structural_<role>: cover/agenda/divider/closing/refs templates
          - default: rest of pool sorted by anchor-term score
        Claude prefers higher-tier candidates but can fall back across the full pool.
        """
        strong_ids = sec_strong_slide_ids.get(sec_idx, set())
        strong_section_ids = sec_strong_section_ids.get(sec_idx, set())
        strong_deck_ids: set[str] = set()
        for c in slide_candidates_compact:
            if str(c.get("section_id") or "") in strong_section_ids:
                d = c.get("deck_id")
                if d:
                    strong_deck_ids.add(str(d))

        roles_needed = {(p.get("target_role") or "").lower() for p in sec_pages}
        structural_rids: dict[str, str] = {}
        for role_key in ("cover", "agenda", "section_divider", "closing", "references"):
            if role_key not in roles_needed:
                continue
            for c in structural_candidates.get(role_key) or []:
                rid = str(c.get("resource_id") or c.get("object_id") or "")
                if rid:
                    structural_rids.setdefault(rid, role_key)

        pool: list[dict] = []
        seen: set[str] = set()
        # Tag every candidate with its tier and emit ALL of them (full pool).
        for c in slide_candidates_compact:
            rid = str(c.get("resource_id") or c.get("object_id") or "")
            if not rid or rid in seen:
                continue
            if rid in strong_ids:
                tier = "strong"
            elif str(c.get("deck_id") or "") in strong_deck_ids:
                tier = "same_deck"
            elif rid in structural_rids:
                tier = f"structural_{structural_rids[rid]}"
            else:
                tier = "default"
            pool.append({**c, "_pool_tier": tier})
            seen.add(rid)
        # Inject any structural candidates not present in slide_candidates_compact
        # (e.g. cover slides that didn't match anchor-term filter).
        for rid, role_key in structural_rids.items():
            if rid in seen:
                continue
            for c in structural_candidates.get(role_key) or []:
                c_rid = str(c.get("resource_id") or c.get("object_id") or "")
                if c_rid == rid:
                    pool.append({**c, "_pool_tier": f"structural_{role_key}"})
                    seen.add(rid)
                    break

        tier_order = {"strong": 0, "same_deck": 1}
        for k in structural_candidates:
            tier_order[f"structural_{k}"] = 2
        tier_order["default"] = 3
        pool.sort(key=lambda c: (tier_order.get(c.get("_pool_tier"), 9),
                                  -(c.get("score") or 0)))
        return pool

    def _match_one_section(sec_idx: int, sec_pages: list[dict]) -> tuple[list[dict], list[str]]:
        """Run Claude for a single section. Returns (matches, errors)."""
        cands = _build_section_pool(sec_idx, sec_pages)
        # Inline tier counts for prompt-side guidance
        tier_counts = _dd(int)
        for c in cands:
            tier_counts[c.get("_pool_tier", "?")] += 1

        ctx = {
            "idea_analysis": {k: brief.get(k) for k in
                               ("topic", "audience", "scenario", "slide_count", "story_style")},
            "section_focus": sec_idx,
            "target_pages": sec_pages,
            "target_coverage_rate": target_reuse_rate,
            "section_matches_brief": [
                {k: m.get(k) for k in ("resource_id", "target_section_index",
                                        "expected_slide_count", "slide_ids")}
                for m in (section_match_doc.get("section_matches") or [])
                if isinstance(m, dict) and m.get("target_section_index") == sec_idx
            ],
            "slide_candidates": cands,
            "candidate_pool_breakdown": dict(tier_counts),
            "previous_picks": [],
            "batch_info": {"section_index": sec_idx, "n_pages": len(sec_pages)},
        }
        prompt = (
            f"SECTION {sec_idx} batch ({len(sec_pages)} target pages).\n"
            f"Candidate pool: {dict(tier_counts)}.\n"
            "\n"
            "Follow the 3-step process defined in the loaded skill files:\n"
            "  1. ASPECT EXTRACTION (slide_aspect_extraction.md)\n"
            "  2. RANK-1 SEMANTIC SELECTION (slide_rank1_semantic.md)\n"
            "  3. RANK-2/3 GAP-BASED SELECTION (slide_rank23_gap_based.md)\n"
            "\n"
            "OUTPUT: For each target_page, emit a slide_matches entry containing\n"
            "  - `aspects` (1-5 atomic content units of the target page)\n"
            "  - `candidates` (length 0-3, each with covered_aspects + residual_gap/addresses_gap)\n"
            "Length of slide_matches must equal n_pages.\n"
            "\n"
            f"**TARGET COVERAGE RATE: {int(target_reuse_rate*100)}%** — most target pages "
            "should have ≥1 candidate. Structural pages → exactly 1 candidate. Content "
            "pages → 1-3 candidates per the gap-based process. Only emit `candidates: []`\n"
            "when the rank-1 score < 0.5 (no semantically on-topic candidate available).\n"
            "\n"
            "**SEMANTIC PRIORITY (HARDEST RULE — repeated for emphasis)**:\n"
            "Selection MUST be driven by topic/claim alignment with target_pages[i] aspects.\n"
            "Visual skeleton (`salient_visuals` / `template_svg`) is at most a tie-breaker\n"
            "between equally-on-topic candidates. NEVER pick a source slide whose claim is\n"
            "off-topic just because the visual layout is similar.\n"
            "\n"
            "**NO CROSS-TARGET DEDUP**: same source slide may appear in multiple target lists.\n"
            "\n"
            "READ target_pages[i].key_points and anchor_terms carefully — each candidate's\n"
            "claim/title/text_samples must cover at least one aspect.\n"
            "\n"
            "INPUT:\n" + json.dumps(ctx, ensure_ascii=False)
        )
        timeout = _section_timeout(len(sec_pages))
        try:
            outcome = _call_claude_json_retry(
                prompt,
                skill=[
                    "skills/matching/slide_matching.md",
                    "skills/matching/slide_aspect_extraction.md",
                    "skills/matching/slide_rank1_semantic.md",
                    "skills/matching/slide_rank23_gap_based.md",
                ],
                timeout=timeout,
                stage_name=f"SLIDE_MATCHING[sec{sec_idx}]",
                max_retries=3,
            )
            sec_matches = outcome["data"].get("slide_matches") or []
            return sec_matches, []
        except RuntimeError as exc:
            err = f"section {sec_idx}: {str(exc)[:300]}"
            # Emit placeholders (new schema: candidates=[]) to keep length parity.
            ph = [{
                "target_slide_index": tp.get("target_slide_index"),
                "target_role": tp.get("target_role"),
                "target_claim": tp.get("target_claim") or tp.get("target_claim_hint"),
                "candidates": [],
                "plan_note": tp.get("page_purpose") or "本页待补充",
                "error": err,
            } for tp in sec_pages]
            return ph, [err]

    # Run all section batches in parallel. Cap at 4 workers — typical decks
    # have 6-8 sections; 4 in flight balances throughput vs Claude API rate.
    sec_results: dict[int, tuple[list[dict], list[str]]] = {}
    with _cf.ThreadPoolExecutor(max_workers=4, thread_name_prefix="slidematch") as pool:
        futs = {pool.submit(_match_one_section, idx, by_sec[idx]): idx
                for idx in section_indices}
        for fut in _cf.as_completed(futs):
            idx = futs[fut]
            try:
                sec_results[idx] = fut.result()
            except Exception as exc:  # defensive — _match_one_section already catches RuntimeError
                sec_results[idx] = ([], [f"section {idx} pool exception: {exc}"])

    # NOTE: cross-section dedup INTENTIONALLY removed (user decision 2026-06-25).
    # In the new top-3 candidates schema, the same source slide is allowed to
    # appear as a candidate across multiple target pages — the user decides at
    # review time which target gets which source.

    # Reassemble ordered by target_slide_index
    all_matches: list[dict] = []
    for idx in section_indices:
        all_matches.extend(sec_results[idx][0])
    # When retry_sections is active, merge in matches from sections we did NOT
    # re-run (pull from prior slide-matches.json). Avoid duplicates: skip any
    # target_slide_index that the current run already produced.
    if retry_sections and existing_matches_by_target:
        current_target_ids = {m.get("target_slide_index") for m in all_matches}
        for tsi, m in existing_matches_by_target.items():
            if tsi in current_target_ids:
                continue
            all_matches.append(m)
    all_matches.sort(key=lambda m: int(m.get("target_slide_index") or 0))

    # Phase I.fix: agenda + section_divider rows SHARE one source.
    # User decision: "所有的agenda页使用同一个检索的复用agenda" — only the first
    # agenda needs retrieval; every divider thereafter byte-clones the same
    # source. New schema: operate on candidates[0] (the rank-1 candidate),
    # since structural pages emit at most 1 candidate.
    AGENDA_ROLES = {"agenda", "section_divider"}

    def _first_cand_rid(m: dict) -> str | None:
        cands = m.get("candidates") or []
        if cands and isinstance(cands[0], dict):
            return cands[0].get("resource_id")
        return None

    def _candidate_role(rid: str) -> str:
        """Look up the slide_role of a candidate from slide_candidates_compact."""
        for c in slide_candidates_compact:
            if str(c.get("resource_id") or c.get("object_id") or "") == str(rid):
                return str(c.get("slide_role") or c.get("role") or "").lower()
        return ""

    agenda_targets = [m for m in all_matches
                      if (m.get("target_role") or "").lower() in AGENDA_ROLES]

    # Step 1: prefer toc_candidate as the shared source for ALL agenda + divider
    # rows. User decision: "分隔页直接复制目录页" — section_divider 不要单选
    # chapter_candidate, 全部和 agenda 共用同一张 toc 模板, 保证视觉一致。
    chosen_cand = None
    chosen_meta = None
    chosen_rid = None
    chosen_source_target_idx = None

    # 1a. 看 Claude 是否已经给某 agenda/divider target 选了 toc_candidate
    toc_picks = []
    for m in agenda_targets:
        rid = _first_cand_rid(m)
        if not rid: continue
        if _candidate_role(rid) == "toc_candidate":
            toc_picks.append(m)
    if toc_picks:
        toc_picks.sort(key=lambda m: -((m.get("candidates") or [{}])[0].get("confidence") or 0))
        chosen = toc_picks[0]
        chosen_cand = dict((chosen.get("candidates") or [{}])[0])
        chosen_rid = chosen_cand.get("resource_id")
        chosen_source_target_idx = chosen.get("target_slide_index")
        for c in slide_candidates_compact:
            if str(c.get("resource_id") or c.get("object_id") or "") == str(chosen_rid):
                chosen_meta = c
                break

    # 1b. 如果 Claude 没给任何 agenda/divider 选 toc_candidate, 直接从池子里
    # 抓一个 score 最高的 toc_candidate 作为共享源 (force-override)
    if chosen_cand is None:
        toc_pool = [c for c in slide_candidates_compact
                    if (c.get("slide_role") or c.get("role") or "").lower() == "toc_candidate"]
        toc_pool.sort(key=lambda c: -(c.get("score") or 0))
        if toc_pool:
            chosen_meta = toc_pool[0]
            chosen_rid = chosen_meta.get("resource_id") or chosen_meta.get("object_id")
            chosen_cand = {
                "rank": 1,
                "resource_id": chosen_rid,
                "deck_id": chosen_meta.get("deck_id"),
                "section_id": chosen_meta.get("section_id"),
                "source_owner": chosen_meta.get("source_owner") or "library",
                "score": 0.88,
                "confidence": 0.88,
                "match_reason": f"forced-toc agenda template",
                "recommended_reuse_mode": "partial_slide_reuse",
                "parts_to_reuse": "目录/议程版式与章节编号样式",
                "parts_to_drop": "原 deck 的章节文字",
                "relation_to_others": "所有 agenda + section_divider 共享此目录页模板",
                "gap_explanation": "",
                "must_rewrite": ["章节标题列表", "当前章节高亮"],
            }
            print(f"[SLIDE_MATCHING] force-toc share: no Claude-picked toc found, "
                  f"using {chosen_rid} from toc_pool ({len(toc_pool)} candidates)",
                  flush=True)

    # 1c. 如果连 toc_pool 都没有 (库里无 toc_candidate), fallback 到原逻辑:
    # 用 Claude 选的 confidence 最高的 agenda/divider candidate
    if chosen_cand is None:
        agenda_picks = [m for m in agenda_targets if _first_cand_rid(m)]
        if agenda_picks:
            agenda_picks.sort(key=lambda m: -((m.get("candidates") or [{}])[0].get("confidence") or 0))
            chosen = agenda_picks[0]
            chosen_cand = dict((chosen.get("candidates") or [{}])[0])
            chosen_rid = chosen_cand.get("resource_id")
            chosen_source_target_idx = chosen.get("target_slide_index")
            for c in slide_candidates_compact:
                if str(c.get("resource_id") or c.get("object_id") or "") == str(chosen_rid):
                    chosen_meta = c
                    break
            print(f"[SLIDE_MATCHING] fallback share: no toc in pool, "
                  f"using Claude's best agenda/divider pick {chosen_rid}",
                  flush=True)

    # 1d. Propagate chosen source to ALL agenda + section_divider rows
    if chosen_cand and chosen_rid:
        propagated = 0
        for m in agenda_targets:
            if _first_cand_rid(m) == chosen_rid:
                continue
            shared_cand = dict(chosen_cand)
            shared_cand["rank"] = 1
            base_reason = chosen_cand.get("match_reason") or "shared toc"
            if chosen_source_target_idx:
                shared_cand["match_reason"] = base_reason + \
                    f" | shared-toc from slide {chosen_source_target_idx}"
            else:
                shared_cand["match_reason"] = base_reason
            shared_cand["confidence"] = max(chosen_cand.get("confidence") or 0, 0.85)
            if chosen_meta:
                for k in ("deck_id", "section_id", "source_owner"):
                    if chosen_meta.get(k):
                        shared_cand[k] = chosen_meta.get(k)
            m["candidates"] = [shared_cand]
            propagated += 1
        if propagated:
            print(f"[SLIDE_MATCHING] agenda+divider share: chosen rid={chosen_rid}, "
                  f"propagated to {propagated} rows (target_role agenda or section_divider)",
                  flush=True)

    batch_errors: list[str] = []
    for idx in section_indices:
        batch_errors.extend(sec_results[idx][1])
    n_batches = len(section_indices)
    n_failed_batches = sum(1 for idx in section_indices if sec_results[idx][1])
    # Coverage = # of target pages with non-empty candidates list
    def _cands(m: dict) -> list:
        return m.get("candidates") or []
    covered_count = sum(1 for m in all_matches if _cands(m))

    if all_matches and not batch_errors:
        outcome = {"ok": True, "data": {"slide_matches": all_matches}}
    elif all_matches and n_failed_batches < max(1, n_batches // 3):
        outcome = {"ok": True, "data": {"slide_matches": all_matches},
                   "partial_errors": batch_errors}
    elif all_matches:
        outcome = {
            "ok": False,
            "error": f"SLIDE_MATCHING: {n_failed_batches}/{n_batches} sections failed; "
                     f"{covered_count}/{len(all_matches)} target pages covered. "
                     f"first error: {batch_errors[0][:200] if batch_errors else 'n/a'}",
            "retry_hint": "重跑 SLIDE_MATCHING — 多个 section Claude CLI 抖动失败",
            "data": {"slide_matches": all_matches},
        }
    else:
        outcome = {"ok": False, "error": "; ".join(batch_errors) or "all sections failed"}
    if outcome.get("ok") and isinstance(outcome.get("data"), dict):
        data = outcome["data"]
        data.setdefault("schema_version", "2.0")  # new top-3 candidate schema
        data["generated_at"] = now()
        data["source"] = "claude"
    else:
        # Fallback: PRESERVE partial matches even when overall outcome=False.
        # outcome.data carries successful section matches (with placeholders
        # for failed sections). Earlier bug threw these away and wrote an
        # empty stub artifact — losing ~10 pages of good Claude work.
        preserved = (outcome.get("data") or {}).get("slide_matches") or all_matches or []
        data = {
            "schema_version": "2.0",
            "generated_at": now(),
            "source": "stub_partial" if preserved else "stub",
            "fallback_reason": outcome.get("error"),
            "slide_matches": preserved,
        }

    # Enrich each candidate with template_svg / source_owner / deck_id /
    # section_id from the candidate pool. (Schema 2.0: per-candidate enrichment)
    cand_idx = {str(c.get("resource_id")): c for c in candidate_pool}
    for m in (data.get("slide_matches") or []):
        if not isinstance(m, dict):
            continue
        for cand in (m.get("candidates") or []):
            if not isinstance(cand, dict):
                continue
            rid = cand.get("resource_id")
            if not rid:
                continue
            src = cand_idx.get(str(rid))
            if src:
                cand.setdefault("source_owner", src.get("source_owner") or "library")
                cand.setdefault("template_svg", src.get("template_svg") or src.get("slide_svg_ref"))
                cand.setdefault("deck_id", src.get("deck_id"))
                cand.setdefault("section_id", src.get("section_id"))

    # P20a: merge carrier-bound matches (computed from outline at top of fn)
    # into the cascade's slide_matches BEFORE writing. This way slide-matches.json
    # contains BOTH bound + cascade entries.
    if bound_slide_matches:
        cascade_indices = {m.get("target_slide_index") for m in (data.get("slide_matches") or [])
                           if isinstance(m, dict)}
        all_matches = list(data.get("slide_matches") or []) + [
            b for b in bound_slide_matches if b.get("target_slide_index") not in cascade_indices
        ]
        all_matches.sort(key=lambda m: m.get("target_slide_index") or 0)
        data["slide_matches"] = all_matches
        data["source"] = "outline_carrier_bound_plus_cascade"
        print(
            f"[slide-matching] merged: {len(bound_slide_matches)} bound + "
            f"{len(cascade_indices)} cascade = {len(all_matches)} total",
            flush=True,
        )

    write_json(pdir / "slide-matches.json", data)

    # Backwards-compat artifact: matched-resource-pack.json
    # Schema 2.0: slide_level_matches lists every (target, candidate) pair so
    # downstream consumers that still expect a flat resource_id list keep working.
    deck_match_doc = read_json(pdir / "deck-matches.json", {}) or {}
    flat_slide_level: list[dict] = []
    for m in (data.get("slide_matches") or []):
        if not isinstance(m, dict):
            continue
        for cand in (m.get("candidates") or []):
            if not isinstance(cand, dict) or not cand.get("resource_id"):
                continue
            flat_slide_level.append({
                "resource_id": cand.get("resource_id"),
                "target_slide_index": m.get("target_slide_index"),
                "candidate_rank": cand.get("rank"),
                "target_slide_hint": m.get("target_role"),
                "recommended_reuse_mode": cand.get("recommended_reuse_mode"),
                "must_rewrite": cand.get("must_rewrite"),
                "source_owner": cand.get("source_owner"),
                "template_svg": cand.get("template_svg"),
                "deck_id": cand.get("deck_id"),
                "section_id": cand.get("section_id"),
                "confidence": cand.get("confidence"),
                "score": cand.get("score"),
                "parts_to_reuse": cand.get("parts_to_reuse"),
                "parts_to_drop": cand.get("parts_to_drop"),
                "relation_to_others": cand.get("relation_to_others"),
                "gap_explanation": cand.get("gap_explanation"),
            })
    compat = {
        "schema_version": "2.0",
        "generated_at": now(),
        "source": "slide_matching_compat",
        "deck_level_matches": deck_match_doc.get("deck_matches") if isinstance(deck_match_doc, dict) else [],
        "section_level_matches": [
            {"resource_id": m.get("resource_id"),
             "target_section_index": m.get("target_section_index"),
             "purpose_alignment": m.get("purpose_alignment"),
             "content_overlap_score": m.get("content_overlap_score"),
             "recommended_use": m.get("recommended_use"),
             "source_owner": m.get("source_owner")}
            for m in (section_match_doc.get("section_matches") or [])
        ],
        "slide_level_matches": flat_slide_level,
        "component_level_matches": [],
        "asset_level_matches": [],
        "coverage_note": deck_match_doc.get("coverage_note") if isinstance(deck_match_doc, dict) else "",
    }
    write_json(pdir / "matched-resource-pack.json", compat)

    # New metrics: target_coverage (% of target pages with ≥1 candidate),
    # total_candidates, avg_candidates_per_covered_target.
    # P20a: target_pages above is the cascade subset only. For overall coverage
    # the denominator must include carrier-bound pages too (they all count as
    # covered by definition).
    matches_list = data.get("slide_matches") or []
    covered_targets = [m for m in matches_list if _cands(m)]
    total_cands = sum(len(_cands(m)) for m in matches_list)
    total_target_pages = len(target_pages) + len(bound_slide_matches)
    target_coverage = len(covered_targets) / max(1, total_target_pages)
    avg_cands = total_cands / max(1, len(covered_targets)) if covered_targets else 0.0

    return {
        "ok": True,
        "stage": "SLIDE_MATCHING",
        "slide_matches": str(pdir / "slide-matches.json"),
        "matched_resource_pack": str(pdir / "matched-resource-pack.json"),
        "carrier_bound_count": len(bound_slide_matches),
        "cascade_count": len(target_pages),
        "target_pages": total_target_pages,
        "covered_targets": len(covered_targets),
        "placeholder_targets": total_target_pages - len(covered_targets),
        "total_candidates": total_cands,
        "avg_candidates_per_covered": round(avg_cands, 2),
        "target_coverage": round(target_coverage, 3),
        "target_coverage_goal": target_reuse_rate,
        "source": data.get("source"),
    }


# ──────────────────────────────────────────────────────────────────────────
# SLIDE_MATCHING_REVIEW (codex gate + Claude surgical fix) — WP-B
# ──────────────────────────────────────────────────────────────────────────

def _slide_matching_research_per_page(project_id: str, outline_slides: list[dict],
                                        flagged_indices: set[int],
                                        current_slide_matches: list[dict]) -> dict:
    """For each flagged page, re-search the library for fresh candidates.

    Returns: {target_slide_index: {
        "alternates_from_outline": [...],   # from outline.slides[i].alternates (preserved)
        "new_candidates_from_research": [...],  # fresh from library_query, score >= 0.5
    }}
    """
    from . import library_query

    pool: dict[str, dict] = {}
    # Index outline slides by slide_index for quick lookup
    outline_by_idx: dict[int, dict] = {}
    for s in outline_slides:
        try:
            outline_by_idx[int(s.get("slide_index"))] = s
        except (TypeError, ValueError):
            pass

    # Already-used resource_ids in current matches (avoid suggesting same)
    used_resource_ids: set[str] = set()
    for m in current_slide_matches:
        for c in (m.get("candidates") or []):
            rid = c.get("resource_id")
            if rid:
                used_resource_ids.add(rid)

    for idx in flagged_indices:
        out_s = outline_by_idx.get(idx) or {}
        # Tokenize from target_title + target_claim + anchor_terms for query
        tokens: set[str] = set()
        for fld in ("target_title", "target_claim"):
            v = out_s.get(fld)
            if isinstance(v, str):
                for t in v.split():
                    if len(t) >= 2:
                        tokens.add(t)
        for at in (out_s.get("anchor_terms") or []):
            if isinstance(at, str) and len(at) >= 2:
                tokens.add(at)

        # Alternates from outline
        alternates = out_s.get("alternates") or []
        # Fresh re-search from library
        new_cands: list[dict] = []
        try:
            merged = library_query.load_merged_candidates(
                project_id, query_tokens=tokens, top_k_decks=5)
            slide_bucket = merged.get("slide") or []
            target_role = out_s.get("target_role") or ""
            for c in slide_bucket:
                rid = c.get("resource_id") or c.get("slide_id")
                if not rid or rid in used_resource_ids:
                    continue
                role = c.get("role") or c.get("slide_role") or ""
                score = c.get("score") or c.get("rank_score") or 0
                if score < 0.5:
                    continue
                # Soft role filter
                role_match = (role == target_role) if (role and target_role) else True
                if not role_match:
                    score *= 0.7
                    if score < 0.5:
                        continue
                new_cands.append({
                    "deck_id": c.get("deck_id"),
                    "slide_id": rid,
                    "rank_score": round(score, 3),
                    "role": role,
                    "match_reasons": [c.get("match_reason") or "fresh re-search"],
                    "source": "library_query_fresh",
                })
            new_cands.sort(key=lambda x: -(x.get("rank_score") or 0))
            new_cands = new_cands[:5]
        except Exception as exc:
            print(f"[SLIDE_MATCHING_REVIEW] re-search ch{idx} failed: {exc}", flush=True)

        pool[str(idx)] = {
            "alternates_from_outline": alternates,
            "new_candidates_from_research": new_cands,
        }
    return pool


def _run_slide_matching_review(project_id: str) -> dict:
    """SLIDE_MATCHING_REVIEW pipeline (WP-B/C/D, 2026-06-29).

    Codex 二审 slide-matches.json → render_ready gate.
    若 not render_ready → Claude surgical re-search/replace per flagged page → 重审.
    Max 3 rounds.

    Outputs:
      - slide-matches.json (revised, with fix_round + render_ready)
      - slide-matches-review.json (codex rounds log)
      - slide-matches-user-status.json (UI status, render_ready)

    Cross-stage propagation (WP-D):
      - user_concern_history inherited from outline.json → propagated to slide-matches.json
      - data_thin mode auto-detected from intake_light + outline.claims_pending_data
    """
    from . import claude_cli, codex_cli, outline_context as oc

    pdir = project_dir(project_id)
    sm_doc = read_json(pdir / "slide-matches.json", {}) or {}
    if not sm_doc.get("slide_matches"):
        return {
            "ok": False, "stage": "SLIDE_MATCHING_REVIEW",
            "error": "slide-matches.json empty or missing — run SLIDE_MATCHING first",
        }
    outline = read_json(pdir / "outline.json", {}) or {}
    idea = read_json(pdir / "idea-analysis.json", {}) or {}
    intake = read_json(pdir / "idea-intake-light.json", {}) or {}

    # WP-D: ensure slide-matches inherits user_concern_history from outline
    if "user_concern_history" not in sm_doc:
        sm_doc["user_concern_history"] = outline.get("user_concern_history") or []
    user_concerns = sm_doc.get("user_concern_history") or []

    MAX_ROUNDS = 3
    review_log: list[dict] = []
    final_review: dict | None = None
    current_sm = sm_doc
    fix_round = 0

    for rnd in range(1, MAX_ROUNDS + 1):
        # --- Codex review call ---
        review_input = {
            "slide_matches": current_sm,
            "outline": oc.compact_outline_for_fix(outline),
            "idea_analysis_slim": oc.compact_idea_for_fix(idea),
            "intake_light": intake,
            "round": rnd,
            "prior_issues": (review_log[-1].get("issues") if review_log else []),
        }
        review_prompt = (
            f"Review slide-matches.json round {rnd}. 6 cats including Cat 4 "
            f"cross_stage_user_concern_regression + Cat 6 render_ready_gate. "
            f"Output {{ok, round, data_thin_mode, render_ready, render_ready_reasoning, "
            f"metrics, issues, summary}} strict JSON only.\n\nINPUT:\n"
            + json.dumps(review_input, ensure_ascii=False)
        )
        print(f"[SLIDE_MATCHING_REVIEW] rnd{rnd} codex review (payload "
              f"{len(review_prompt)/1024:.0f} KB)", flush=True)
        rev = codex_cli.call_codex_json(
            review_prompt,
            skill=["skills/matching/slide_matching_review.md"],
            timeout=600,
        )
        if not rev.get("ok"):
            print(f"[SLIDE_MATCHING_REVIEW] codex rnd{rnd} cli failed: "
                  f"{(rev.get('error') or '')[:160]}", flush=True)
            review_log.append({"round": rnd, "codex_error": rev.get("error")})
            break
        rdata = rev.get("data") or {}
        rdata["round"] = rnd
        review_log.append(rdata)
        final_review = rdata
        render_ready = bool(rdata.get("render_ready"))
        issues = rdata.get("issues") or []
        n_ch = sum(1 for i in issues
                    if isinstance(i, dict) and i.get("severity") in ("critical", "high"))
        print(f"[SLIDE_MATCHING_REVIEW] rnd{rnd}: render_ready={render_ready}, "
              f"issues={len(issues)} (critical/high={n_ch}), "
              f"data_thin={rdata.get('data_thin_mode')}", flush=True)

        if render_ready:
            print(f"  ✓ render_ready=true at rnd{rnd}", flush=True)
            break
        if n_ch == 0:
            print(f"  ✓ no critical/high issues at rnd{rnd}", flush=True)
            break
        if rnd >= MAX_ROUNDS:
            print(f"  reached max {MAX_ROUNDS} rounds with {n_ch} unresolved critical/high",
                  flush=True)
            break

        # --- Claude surgical fix (WP-B/C) ---
        flagged_indices: set[int] = set()
        for i in issues:
            if not isinstance(i, dict):
                continue
            tsi = i.get("target_slide_index")
            if tsi is not None:
                try:
                    flagged_indices.add(int(tsi))
                except (TypeError, ValueError):
                    pass
        if not flagged_indices:
            print(f"  no flagged target_slide_index — cannot fix; breaking", flush=True)
            break
        print(f"  flagged pages: {sorted(flagged_indices)}", flush=True)

        # Build per-page candidate pool (alternates + fresh re-search)
        candidate_pool = _slide_matching_research_per_page(
            project_id, outline.get("slides") or [], flagged_indices,
            current_sm.get("slide_matches") or [])
        print(f"  re-searched: {sum(len(p.get('new_candidates_from_research') or []) for p in candidate_pool.values())} fresh candidates across {len(candidate_pool)} pages", flush=True)

        fix_payload = {
            "prior_slide_matches": current_sm,
            "codex_issues": issues,
            "candidate_pool_per_flagged_page": candidate_pool,
            "outline": oc.compact_outline_for_fix(outline),
            "user_concern_history": user_concerns,
        }
        fix_prompt = (
            "Apply SURGICAL fixes to PRIOR slide-matches.json based on CODEX ISSUES. "
            "Per flagged page: pick from candidate_pool_per_flagged_page (alternates + "
            "fresh re-search). Preserve untouched pages byte-identical. Respect "
            "user_concern_history regression guard (HARD constraint). Output FULL "
            "corrected slide-matches.json v2.1. Strict JSON only.\n\nINPUT:\n"
            + json.dumps(fix_payload, ensure_ascii=False)
        )
        print(f"  Claude fix (payload {len(fix_prompt)/1024:.0f} KB)", flush=True)
        fix_out = claude_cli.call_claude_json(
            fix_prompt,
            skill=["skills/matching/slide_matching_fix.md"],
            timeout=900,
        )
        if not (fix_out.get("ok") and isinstance(fix_out.get("data"), dict)):
            print(f"  ! fix rnd{rnd} failed: {(fix_out.get('error') or '')[:160]}",
                  flush=True)
            break
        current_sm = fix_out["data"]
        fix_round = rnd
        current_sm["fix_round"] = fix_round
        current_sm["user_concern_history"] = user_concerns  # preserve
        print(f"  fix applied: carriers_replaced={current_sm.get('carriers_replaced_count', '?')}, "
              f"gap_pages={current_sm.get('gap_pages_count', '?')}", flush=True)

    # Write artifacts
    if final_review:
        current_sm["render_ready"] = bool(final_review.get("render_ready"))
        current_sm["data_thin_mode"] = bool(final_review.get("data_thin_mode"))
    write_json(pdir / "slide-matches.json", current_sm)
    write_json(pdir / "slide-matches-review.json", {
        "schema_version": "1.0",
        "generated_at": now(),
        "rounds": review_log,
        "render_ready": (final_review or {}).get("render_ready") if final_review else False,
        "render_ready_reasoning": (final_review or {}).get("render_ready_reasoning"),
        "metrics": (final_review or {}).get("metrics"),
        "fix_round": fix_round,
    })
    write_json(pdir / "slide-matches-user-status.json", {
        "schema_version": "1.0",
        "generated_at": now(),
        "status": "ready" if ((final_review or {}).get("render_ready")) else "needs_attention",
        "render_ready": (final_review or {}).get("render_ready") if final_review else False,
        "render_ready_reasoning": (final_review or {}).get("render_ready_reasoning"),
        "codex_review_rounds": len(review_log),
        "fix_round": fix_round,
        "user_concern_count": len(user_concerns),
        "metrics": (final_review or {}).get("metrics"),
    })

    return {
        "ok": True,
        "stage": "SLIDE_MATCHING_REVIEW",
        "slide_matches": str(pdir / "slide-matches.json"),
        "review": str(pdir / "slide-matches-review.json"),
        "render_ready": (final_review or {}).get("render_ready") if final_review else False,
        "render_ready_reasoning": (final_review or {}).get("render_ready_reasoning"),
        "codex_review_rounds": len(review_log),
        "fix_round": fix_round,
        "carriers_replaced_count": current_sm.get("carriers_replaced_count"),
        "gap_pages_count": current_sm.get("gap_pages_count"),
        "user_concern_count": len(user_concerns),
    }


def _batch_codex_slide_annotations(project_id: str) -> tuple[int, int]:
    """P20b: one-shot codex call to produce per-slide annotation summaries.

    Reads outline.json + gap-cards.json. For each slide, sends target_role /
    target_title / target_claim / page_purpose / key_points + the matching
    gap_info to codex via draft_annotation_summary.md skill. Writes
    `projects/<id>/slide-annotations.json` with shape:

      {"schema_version": "1.0", "generated_at": "...",
       "summaries": [{"slide_index": 1, "objective": "≤14字", "gap_brief": "≤24字"}, ...]}

    Returns (n_summaries, n_input_slides). On total failure writes an empty
    summaries list and returns (0, n_input_slides) — DRAFT_ASSEMBLY's
    _inject_review_annotation handles the missing-data fallback.
    """
    from . import codex_cli

    pdir = project_dir(project_id)
    outline = read_json(pdir / "outline.json", {}) or {}
    cards_doc = read_json(pdir / "gap-cards.json", {}) or {}
    cards_by_idx: dict[int, dict] = {}
    for c in (cards_doc.get("gap_cards") or []):
        if isinstance(c, dict):
            try:
                cards_by_idx[int(c.get("slide_index"))] = c
            except (TypeError, ValueError):
                pass

    outline_slides = outline.get("slides") or []
    if not outline_slides:
        write_json(pdir / "slide-annotations.json", {
            "schema_version": "1.0",
            "generated_at": now(),
            "source": "stub_no_outline",
            "summaries": [],
        })
        return 0, 0

    anno_input_slides = []
    for o in outline_slides:
        if not isinstance(o, dict):
            continue
        try:
            sl_idx = int(o.get("slide_index"))
        except (TypeError, ValueError):
            continue
        gc = cards_by_idx.get(sl_idx, {}) or {}
        anno_input_slides.append({
            "slide_index": sl_idx,
            "target_role": o.get("target_role"),
            "target_title": o.get("target_title"),
            "target_claim": o.get("target_claim"),
            "page_purpose": o.get("page_purpose"),
            "key_points": (o.get("key_points") or [])[:4],
            "gap_info": {
                "must_replace": (gc.get("must_replace") or [])[:3],
                "must_add": (gc.get("must_add") or [])[:3],
                "evidence_needed": (gc.get("evidence_needed") or [])[:2],
                "next_action": gc.get("next_action"),
            },
        })

    total = len(anno_input_slides)
    # WP-D: pass user_concern_history so codex notes don't accidentally
    # recommend content that violates protected concerns
    user_concerns = outline.get("user_concern_history") or []
    sm_doc = read_json(pdir / "slide-matches.json", {}) or {}
    if not user_concerns:
        user_concerns = sm_doc.get("user_concern_history") or []
    prompt = (
        "Generate annotation summaries for all slides per the skill schema.\n"
        "Each slide → {slide_index, objective (≤14字), gap_brief (≤24字)}.\n"
        "Respect user_concern_history (must_not_regress=true items) — do NOT "
        "recommend content that would violate them.\n"
        "Output strict JSON only.\n\n"
        "INPUT:\n" + json.dumps({
            "slides": anno_input_slides,
            "user_concern_history": user_concerns,
        }, ensure_ascii=False)
    )
    out = codex_cli.call_codex_json(
        prompt,
        skill=["skills/draft/draft_annotation_summary.md"],
        timeout=300,
    )
    summaries: list[dict] = []
    if out.get("ok") and isinstance(out.get("data"), dict):
        for s in (out["data"].get("summaries") or []):
            if isinstance(s, dict):
                summaries.append(s)
        source = "codex"
    else:
        source = "stub_codex_failed"

    write_json(pdir / "slide-annotations.json", {
        "schema_version": "1.0",
        "generated_at": now(),
        "source": source,
        "summaries": summaries,
        "fallback_reason": out.get("error") if not summaries else None,
    })
    return len(summaries), total


def _render_story_strategy_md(data: dict) -> str:
    lines = [
        "---",
        'schema_version: "3.0"',
        f'generated_at: "{now()}"',
        'source: "story_strategy"',
        "---",
        "",
        "# Story Strategy",
        "",
        "## Main Thesis",
        str(data.get("main_thesis") or ""),
        "",
        "## Audience Journey",
    ]
    for step in data.get("audience_journey") or []:
        if isinstance(step, dict):
            lines.append(f"- **{step.get('stage') or '?'}**: {step.get('what_audience_knows') or step.get('what_should_change') or step.get('what_audience_takes_home') or ''}")
    lines.extend(["", "## Narrative Arc"])
    for sect in data.get("narrative_arc") or []:
        if isinstance(sect, dict):
            reuse = ", ".join(sect.get("reuse_sources") or []) or "(no reuse)"
            lines.append(f"- **{sect.get('section')}** — {sect.get('purpose') or ''}  "
                         f"[depth: {sect.get('depth') or 'balanced'} · evidence: {sect.get('preferred_evidence_kind') or '-'} · reuse: {reuse}]")
    return "\n".join(lines).rstrip() + "\n"


def _run_story_strategy(project_id: str) -> dict:
    """W3: Claude designs the narrative arc from brief + matched-pack."""
    from . import claude_cli

    pdir = project_dir(project_id)
    brief = read_json(pdir / "idea-analysis.json", {}) or {}
    understanding = read_json(pdir / "data/source-understanding.json", {}) or {}
    matched = read_json(pdir / "matched-resource-pack.json", {}) or {}
    answers = _answers(project_id)
    user_outline = str(answers.get("user_outline") or "")
    context = {
        "idea_analysis": brief,
        "project_resource_understanding_summary": {
            "must_use_count": len(understanding.get("must_use_materials") or []),
            "forbidden_count": len(understanding.get("forbidden_or_low_confidence_materials") or []),
            "topic_to_project_sources": understanding.get("topic_to_project_sources") or {},
        },
        "matched_resource_pack_summary": {
            "deck_matches":    [m.get("resource_id") for m in (matched.get("deck_level_matches") or [])],
            "section_matches": [m.get("resource_id") for m in (matched.get("section_level_matches") or [])],
            "slide_matches":   [{"id": m.get("resource_id"), "hint": m.get("target_slide_hint")} for m in (matched.get("slide_level_matches") or [])][:30],
            "coverage_note":   matched.get("coverage_note"),
        },
        "user_outline": user_outline,
    }
    prompt = (
        "Design the deck's narrative arc per the skill schema.\n"
        "Return JSON only. Reuse_sources may only reference resource_ids in matched_resource_pack_summary.\n\n"
        "INPUT:\n" + json.dumps(context, ensure_ascii=False)
    )
    skill = claude_cli.skill_paths_for_agent("StoryStrategyAgent")
    outcome = claude_cli.call_claude_json(prompt, skill=skill, timeout=240)
    if outcome.get("ok") and isinstance(outcome.get("data"), dict):
        data = outcome["data"]
        data.setdefault("schema_version", "3.0")
        data["generated_at"] = now()
        data["source"] = "claude"
    else:
        data = {
            "schema_version": "3.0",
            "generated_at": now(),
            "source": "stub",
            "fallback_reason": outcome.get("error"),
            "main_thesis": brief.get("core_message") or "",
            "audience_journey": [],
            "narrative_arc": [
                {"section": s, "purpose": "", "depth": "balanced",
                 "preferred_evidence_kind": "narrative", "reuse_sources": [], "must_research": True}
                for s in (brief.get("expected_sections") or ["背景", "问题", "方法", "结果", "总结"])
            ],
            "decision_log": {"why_this_arc": "stub fallback", "rejected_arcs": [],
                             "user_outline_alignment": "fully_followed" if user_outline else "reinterpreted",
                             "user_outline_alignment_reason": "stub"},
        }
    write_json(pdir / "story-strategy.json", data)
    (pdir / "story-strategy.md").write_text(_render_story_strategy_md(data), encoding="utf-8")
    return {"ok": True, "stage": "STORY_STRATEGY", "story_strategy": str(pdir / "story-strategy.json"),
            "source": data.get("source"), "arc_length": len(data.get("narrative_arc") or [])}


def _matched_pack_index(matched: dict) -> dict:
    """Flat resource_id -> match metadata index across all 5 layers, for outline/audit checks."""
    out = {}
    for layer in ["deck", "section", "slide", "component", "asset"]:
        for m in (matched.get(f"{layer}_level_matches") or []):
            if isinstance(m, dict) and m.get("resource_id"):
                out[str(m["resource_id"])] = {**m, "layer": layer}
    return out


def _build_model_routed_plan(project_id: str, slides: list[dict], topic: str, generated_by: str) -> dict:
    """Adapter that maps reuse-first-outline slides into the legacy model-routed-plan.json
    shape downstream stages still read."""
    return {
        "schema_version": "3.0",
        "generated_at": now(),
        "project_id": project_id,
        "topic": topic,
        "generated_by": generated_by,
        "fallback_used": False,
        "slides": [
            {
                "index": s["slide_index"],
                "title": s["target_title"],
                "section": s["target_role"],
                "story_role": s["target_role"],
                "layout_type": "title-image" if s["target_role"] == "cover" else "agenda" if s["target_role"] == "agenda" else "assertion-evidence",
                "visual_type": "image-and-bullets" if s["target_role"] == "cover" else "table" if s["target_role"] == "agenda" else "diagram",
                "claim": s.get("target_claim") or "",
                "key_message": s.get("target_claim") or s.get("target_title"),
                "assertion_title": s.get("target_claim") or s.get("target_title"),
                "source_lineage": s.get("source_candidates") or [],
                "selected_reuse": s.get("selected_reuse") or {},
                "reuse_level": (s.get("selected_reuse") or {}).get("reuse_mode"),
                "citations": [],
            }
            for s in slides
        ],
    }


def _run_reuse_outline(project_id: str, payload: dict) -> dict:
    """W3: Claude-driven outline that only cites matched-resource-pack resource_ids.
    Falls back to deterministic _run_reuse_outline_legacy on claude failure so the
    pipeline still produces a valid reuse-first-outline.json."""
    from . import claude_cli

    pdir = project_dir(project_id)
    answers = _answers(project_id)
    brief = read_json(pdir / "idea-analysis.json", {}) or {}
    story = read_json(pdir / "story-strategy.json", {}) or {}
    matched = read_json(pdir / "matched-resource-pack.json", {}) or {}
    understanding = read_json(pdir / "data/source-understanding.json", {}) or {}

    slide_count = int(answers.get("slide_count") or brief.get("slide_count") or 10)
    user_outline = answers.get("user_outline") or ""

    matched_idx = _matched_pack_index(matched)
    matched_summary = {
        "resource_ids": list(matched_idx.keys())[:200],
        "slide_matches": [
            {"resource_id": k, "hint": v.get("target_slide_hint"),
             "reuse_mode": v.get("recommended_reuse_mode"),
             "allowed_use": v.get("allowed_use"),
             "forbidden_use": v.get("forbidden_use") or []}
            for k, v in matched_idx.items() if v.get("layer") == "slide"
        ][:60],
    }
    context = {
        "slide_count": slide_count,
        "user_outline": user_outline,
        "idea_analysis": {
            "deck_type": brief.get("deck_type"),
            "audience_level": brief.get("audience_level"),
            "core_message": brief.get("core_message"),
            "must_have_pages": brief.get("must_have_pages") or [],
            "expected_sections": brief.get("expected_sections") or [],
        },
        "story_strategy": {
            "main_thesis": story.get("main_thesis"),
            "narrative_arc": story.get("narrative_arc") or [],
        },
        "project_resource_summary": {
            "must_use": [m.get("resource_id") for m in (understanding.get("must_use_materials") or [])],
            "forbidden": [m.get("resource_id") for m in (understanding.get("forbidden_or_low_confidence_materials") or [])],
        },
        "matched_resource_pack": matched_summary,
    }
    prompt = (
        "Produce reuse-first-outline.json per the skill schema. The slide count must equal "
        f"{slide_count}. Every resource_id you cite must appear in matched_resource_pack.resource_ids.\n"
        "Return JSON only.\n\nINPUT:\n" + json.dumps(context, ensure_ascii=False)
    )
    skill = claude_cli.skill_paths_for_agent("ReuseOutlineAgent")
    outcome = claude_cli.call_claude_json(prompt, skill=skill, timeout=300)
    data = None
    if outcome.get("ok") and isinstance(outcome.get("data"), dict):
        candidate = outcome["data"]
        slides = candidate.get("slides") if isinstance(candidate.get("slides"), list) else None
        if slides and len(slides) == slide_count:
            allowed_ids = set(matched_idx.keys())
            for s in slides:
                if not isinstance(s, dict):
                    continue
                sel = s.get("selected_reuse") or {}
                if sel.get("resource_id") and str(sel.get("resource_id")) not in allowed_ids:
                    sel["resource_id"] = None
                    sel["reuse_mode"] = "new_slide_placeholder"
                    sel["why_match"] = (sel.get("why_match") or "") + " [pruned: not in matched-pack]"
                s["selected_reuse"] = sel
                s["source_candidates"] = [
                    sc for sc in (s.get("source_candidates") or [])
                    if isinstance(sc, dict) and str(sc.get("resource_id") or "") in allowed_ids
                ]
            artifact = {
                "schema_version": "3.0",
                "generated_at": now(),
                "project_id": project_id,
                "source": "claude",
                "user_outline_priority": bool(user_outline),
                "topic": answers.get("topic"),
                "audience": answers.get("audience"),
                "scenario": answers.get("scenario"),
                "slide_count": slide_count,
                "slides": slides,
            }
            write_json(pdir / "reuse-first-outline.json", artifact)
            write_json(pdir / "model-routed-plan.json",
                       _build_model_routed_plan(project_id, slides, answers.get("topic") or "", "reuse_outline_v3"))
            stage_controller.build_slide_state(project_id)
            data = artifact

    if data is None:
        # claude failed or returned an unusable shape — fall back to deterministic legacy
        legacy = _run_reuse_outline_legacy(project_id, payload)
        legacy["source"] = "legacy"
        legacy["fallback_reason"] = outcome.get("error") or "claude returned unusable shape"
        return legacy

    return {"ok": True, "stage": "REUSE_OUTLINE", "source": "claude",
            "reuse_first_outline": str(pdir / "reuse-first-outline.json"),
            "slide_count": slide_count}


def _run_reuse_outline_legacy(project_id: str, payload: dict) -> dict:
    pdir = project_dir(project_id)
    answers = _answers(project_id)
    task = read_json(pdir / "task-analysis.json", {})
    candidates = read_json(pdir / "template-library-candidates.json", {})
    asset_catalog = read_json(pdir / "project-asset-catalog.json", {})
    slide_count = int(answers.get("slide_count") or task.get("slide_count") or 10)
    user_lines = _outline_lines(answers.get("user_outline") or "")
    seed_lines = _default_reuse_outline_lines(answers, task, slide_count) if not user_lines else []
    template_slides = _template_slide_profile_candidates()
    template_decks = _library_candidates_by_type(candidates, "deck", limit=6)
    slides = []
    used_template_slide_ids: set[str] = set()
    used_source_paths: set[str] = set()
    for idx in range(1, slide_count + 1):
        user_title = user_lines[idx - 1] if idx <= len(user_lines) else ""
        seed_title = seed_lines[idx - 1] if idx <= len(seed_lines) else ""
        title = user_title or seed_title or ("封面" if idx == 1 else "总结" if idx == slide_count else f"第 {idx} 页")
        role = _outline_role(title, idx, slide_count)
        if idx == 2 and (not user_title or role == "content"):
            role = "agenda"
            title = "目录"
        claim = title if role not in {"cover", "agenda"} else ""
        slide_seed = {
            "target_title": title,
            "target_role": role,
            "target_claim": claim,
            "topic": answers.get("topic") or task.get("topic") or project_id,
        }
        tpl = _best_template_slide_for_outline(
            slide_seed,
            template_slides,
            idx,
            slide_count,
            used_template_slide_ids=used_template_slide_ids,
        )
        text_for_match = " ".join([title, claim, answers.get("topic") or "", answers.get("scenario") or ""])
        source_assets = _asset_candidates_for_text(asset_catalog, text_for_match, limit=5)
        source_candidates = _rank_reuse_candidates(
            slide_seed,
            tpl,
            source_assets,
            idx=idx,
            slide_count=slide_count,
            used_source_paths=used_source_paths,
        )
        selected = source_candidates[0] if source_candidates else {
            "source_type": "new_slide",
            "reuse_mode": "new_slide_placeholder",
            "why_match": "no strong source/template match",
        }
        if selected.get("source_type") == "template_library_slide" and selected.get("object_id"):
            used_template_slide_ids.add(str(selected["object_id"]))
        if selected.get("path"):
            used_source_paths.add(str(selected["path"]))
        if user_title:
            outline_source = "user_outline"
        elif selected.get("source_type") in {"source_slide_svg", "source_figure", "image", "ppt_deck"}:
            outline_source = "project_sources"
        elif selected.get("source_type") == "template_library_slide":
            outline_source = "template_library"
        else:
            outline_source = "new_slide_placeholder"
        slides.append({
            "slide_index": idx,
            "target_title": title,
            "target_role": role,
            "target_claim": claim,
            "outline_source": outline_source,
            "source_candidates": source_candidates,
            "selected_reuse": selected,
            "gap": [] if source_candidates else ["需要补充页面证据或可复用视觉资源"],
            "research_needed": [] if source_candidates else [f"{answers.get('topic') or ''} {title}".strip()],
        })
    artifact = {
        "schema_version": "2.0",
        "generated_at": now(),
        "project_id": project_id,
        "source": "reuse_first_outline",
        "user_outline_priority": bool(user_lines),
        "topic": answers.get("topic"),
        "audience": answers.get("audience"),
        "scenario": answers.get("scenario"),
        "slide_count": slide_count,
        "template_deck_candidates": template_decks,
        "slides": slides,
    }
    write_json(pdir / "reuse-first-outline.json", artifact)
    model_plan = {
        "schema_version": "2.0",
        "generated_at": now(),
        "project_id": project_id,
        "topic": answers.get("topic"),
        "generated_by": "reuse_first_outline",
        "fallback_used": False,
        "slides": [
            {
                "index": s["slide_index"],
                "title": s["target_title"],
                "section": s["target_role"],
                "story_role": s["target_role"],
                "layout_type": "title-image" if s["target_role"] == "cover" else "agenda" if s["target_role"] == "agenda" else "assertion-evidence",
                "visual_type": "image-and-bullets" if s["target_role"] == "cover" else "table" if s["target_role"] == "agenda" else "diagram",
                "claim": s["target_claim"],
                "key_message": s["target_claim"] or s["target_title"],
                "assertion_title": s["target_claim"] or s["target_title"],
                "source_lineage": s["source_candidates"],
                "selected_reuse": s["selected_reuse"],
                "reuse_level": s["selected_reuse"].get("reuse_mode"),
                "citations": [],
            }
            for s in slides
        ],
    }
    write_json(pdir / "model-routed-plan.json", model_plan)
    story = [
        "---",
        'schema_version: "2.0"',
        f'generated_at: "{now()}"',
        'source: "reuse_first_outline"',
        "---",
        "",
        "# Story Strategy",
        "",
        "## Narrative Source",
        "User outline has priority." if user_lines else "Template library narrative patterns provide the initial structure.",
        "",
        "## Candidate Decks",
    ]
    for deck in template_decks:
        story.append(f"- {deck.get('object_id')}: {deck.get('text')}")
    story.extend(["", "## Slide Spine"])
    for slide in slides:
        story.append(f"{slide['slide_index']}. {slide['target_title']} — {slide['selected_reuse'].get('reuse_mode')}")
    (pdir / "story-strategy.md").write_text("\n".join(story).rstrip() + "\n", encoding="utf-8")
    stage_controller.build_slide_state(project_id)
    return {"ok": True, "reuse_first_outline": str(pdir / "reuse-first-outline.json"), "slide_count": slide_count}


def _run_gap_card_generation(project_id: str) -> dict:
    """Generate per-page gap_card unifying outline + matches + source briefs.

    Output: gap-cards.json — schema in skills/gap_cards/gap_card_generation.md.
    Used by SLIDE_PLAN, DRAFT_ASSEMBLY_PLAN, DRAFT_REVIEW, GAP_ANALYSIS as the
    single source of truth for "what's wrong with this page and what to do".
    """
    from . import claude_cli, outline_context as oc

    pdir = project_dir(project_id)
    _gate_fail = _check_upstream_approval(
        pdir, "outline-user-status.json",
        upstream_stage_label="OUTLINE_GENERATION",
        current_stage_label="GAP_CARD_GENERATION")
    if _gate_fail is not None:
        return _gate_fail

    outline_doc = read_json(pdir / "outline.json", {}) or {}
    sm_doc = read_json(pdir / "slide-matches.json", {}) or {}
    section_match_doc = read_json(pdir / "section-matches.json", {}) or {}
    understanding = read_json(pdir / "data/source-understanding.json", {}) or {}
    raw = read_json(pdir / "raw-layered-candidates.json", {}) or {}
    proj_doc_units = read_json(pdir / "project-doc-units.json", {}) or {}
    brief = read_json(pdir / "idea-analysis.json", {}) or {}

    outline_slides = outline_doc.get("slides") or []
    matches = sm_doc.get("slide_matches") or []
    if not outline_slides:
        return {"ok": False, "stage": "GAP_CARD_GENERATION",
                "error": "outline.json missing or empty"}

    def _append_unique_list(card: dict, key: str, values: list) -> None:
        cur = card.setdefault(key, [])
        if not isinstance(cur, list):
            cur = []
            card[key] = cur
        for val in values:
            if val and val not in cur:
                cur.append(val)

    def _mark_gap(card: dict, *, gap_type: str, priority: str = "high",
                  scope: str = "text_only", next_action: str = "slide_rewrite",
                  must_replace: list | None = None, must_remove: list | None = None,
                  must_add: list | None = None, hint: str | None = None,
                  audit_entry: dict | None = None) -> None:
        card["gap_required"] = True
        card["rewrite_priority"] = priority
        card["rewrite_scope"] = scope
        card["next_action"] = next_action
        _append_unique_list(card, "gap_types", [gap_type])
        _append_unique_list(card, "must_replace", must_replace or [])
        _append_unique_list(card, "must_remove", must_remove or [])
        _append_unique_list(card, "must_add", must_add or [])
        if hint:
            hints = card.setdefault("unification_hints", [])
            if isinstance(hints, list):
                obj = {"type": gap_type, "hint": hint}
                if obj not in hints:
                    hints.append(obj)
        if audit_entry:
            audits = card.setdefault("_structural_audits", [])
            if isinstance(audits, list):
                audits.append(audit_entry)

    def _source_id_from_slide(slide: dict) -> str | None:
        refs = slide.get("source_resource_ids") or []
        if not refs:
            return None
        top = refs[0]
        if isinstance(top, dict):
            return top.get("slide_id")
        if isinstance(top, str):
            return top
        return None

    def _augment_gap_cards_with_structural_audit(cards: list[dict]) -> list[dict]:
        """Add deterministic structural edit tasks that Claude gap cards may miss.

        This keeps DRAFT_ASSEMBLY byte-clone-first, but ensures downstream
        CHARACTER_REVISION/REVIEW sees repeated-source, weak-match, structural
        source, chapter rhythm, and parallel-work symmetry issues as explicit
        gap-card tasks.
        """
        card_by_idx: dict[int, dict] = {}
        for c in cards:
            if not isinstance(c, dict):
                continue
            try:
                card_by_idx[int(c.get("slide_index"))] = c
            except Exception:
                continue

        slides_by_ch: dict[int, list[dict]] = {}
        for s in outline_slides:
            if not isinstance(s, dict):
                continue
            try:
                ci = int(s.get("chapter_index") or s.get("section_index") or 0)
                idx = int(s.get("slide_index"))
            except Exception:
                continue
            row = dict(s)
            row["_idx_int"] = idx
            row["_src_id"] = _source_id_from_slide(row)
            slides_by_ch.setdefault(ci, []).append(row)
        for ch_slides in slides_by_ch.values():
            ch_slides.sort(key=lambda x: x.get("_idx_int") or 0)

        audit: list[dict] = []
        # 1. Repeated rank-1 source inside a chapter.
        for ci, ch_slides in slides_by_ch.items():
            by_src: dict[str, list[dict]] = {}
            for s in ch_slides:
                sid = s.get("_src_id")
                if sid:
                    by_src.setdefault(sid, []).append(s)
            for sid, dup_slides in by_src.items():
                if len(dup_slides) < 2:
                    continue
                indices = [x["_idx_int"] for x in dup_slides]
                roles = [x.get("target_role") for x in dup_slides]
                titles = [x.get("target_title") for x in dup_slides]
                entry = {
                    "type": "duplicate_source_within_chapter",
                    "chapter_index": ci,
                    "source_slide_id": sid,
                    "slide_indices": indices,
                    "roles": roles,
                }
                audit.append(entry)
                for s in dup_slides:
                    card = card_by_idx.get(s["_idx_int"])
                    if not card:
                        continue
                    _mark_gap(
                        card,
                        gap_type="duplicate_source",
                        priority="high",
                        scope="full_page" if (s.get("source_carrier_resource_kind") == "matching_fallback") else "text_only",
                        next_action="slide_rewrite",
                        must_replace=[
                            f"本页与同章 slide {', '.join(str(i) for i in indices if i != s['_idx_int'])} 复用同一源页 {sid}; 后续修改必须显著区分叙事角度或改绑其他真实源页"
                        ],
                        must_add=[
                            "若保留同源, 增加明确说明: 本页只复用源页视觉骨架, 文字需重写为当前 target_claim"
                        ],
                        hint=f"同章重复源页: {indices} 均绑定 {sid}; titles={titles}",
                        audit_entry=entry,
                    )

        # 2. Weak/matching fallback must be visible to downstream revision.
        for s in outline_slides:
            if not isinstance(s, dict):
                continue
            kind = (s.get("source_carrier_resource_kind") or s.get("kind") or "").lower()
            gap_status = (s.get("gap_status") or "").lower()
            try:
                idx = int(s.get("slide_index"))
            except Exception:
                continue
            if kind == "matching_fallback" or "weak" in gap_status:
                card = card_by_idx.get(idx)
                if not card:
                    continue
                entry = {
                    "type": "weak_matching_fallback",
                    "slide_index": idx,
                    "kind": kind,
                    "gap_status": gap_status,
                }
                audit.append(entry)
                _mark_gap(
                    card,
                    gap_type="semantic_gap",
                    priority="high",
                    scope="full_page",
                    next_action="human_intervention_required",
                    must_replace=[
                        "当前页是 weak/matching_fallback: 不得视为最终可用页; 后续必须重写为 target_claim 或改绑更贴合的真实源页"
                    ],
                    must_add=[
                        "在修订时补充本页与目标论断一一对应的标题、关键点和图注"
                    ],
                    hint=f"weak source binding: kind={kind}, gap_status={gap_status}",
                    audit_entry=entry,
                )

        # 3. Structural roles should not bind ordinary content pages.
        structural_roles = {"chapter_divider", "section_divider", "framework_recap", "agenda", "cover", "closing", "references"}
        bad_struct_terms = ["三方法", "三条压缩", "核心方法", "挑战", "效果", "论文封面"]
        for s in outline_slides:
            if not isinstance(s, dict):
                continue
            role = (s.get("target_role") or "").lower()
            if role not in structural_roles:
                continue
            try:
                idx = int(s.get("slide_index"))
            except Exception:
                continue
            card = card_by_idx.get(idx)
            if not card:
                continue
            source_title = card.get("source_title") or ""
            if any(term in source_title for term in bad_struct_terms):
                entry = {
                    "type": "structural_page_bound_to_content_source",
                    "slide_index": idx,
                    "role": role,
                    "source_title": source_title,
                }
                audit.append(entry)
                _mark_gap(
                    card,
                    gap_type="structural_source_mismatch",
                    priority="high",
                    scope="full_page",
                    next_action="slide_rewrite",
                    must_replace=[
                        f"结构页当前源页标题为 '{source_title}', 内容页语义过强; 后续必须改写为章节导航/框架回顾, 不保留源页具体方法主线"
                    ],
                    must_remove=[
                        "删除源页中不属于章节导航或框架回顾的具体方法/论文/实验描述"
                    ],
                    must_add=[
                        "补充统一三层框架/章节当前位置高亮/下一分点预告"
                    ],
                    hint=f"role={role} should use divider/framework source, not content source '{source_title}'",
                    audit_entry=entry,
                )

        # 4. Chapter rhythm consistency for method-heavy chapters.
        method_chapters = {
            ci: ch_slides for ci, ch_slides in slides_by_ch.items()
            if any((s.get("target_role") or "").lower() in {"method", "result"} for s in ch_slides)
        }
        for ci, ch_slides in method_chapters.items():
            roles = [(s.get("target_role") or "").lower() for s in ch_slides]
            has_divider = any(r in {"chapter_divider", "section_divider"} for r in roles)
            has_framework = any(r == "framework_recap" for r in roles)
            if has_divider and has_framework:
                continue
            entry = {
                "type": "chapter_rhythm_inconsistent",
                "chapter_index": ci,
                "has_divider": has_divider,
                "has_framework_recap": has_framework,
            }
            audit.append(entry)
            first = ch_slides[0]
            card = card_by_idx.get(first["_idx_int"])
            if card:
                missing = []
                if not has_divider:
                    missing.append("chapter_divider")
                if not has_framework:
                    missing.append("framework_recap")
                _mark_gap(
                    card,
                    gap_type="chapter_rhythm_inconsistent",
                    priority="high",
                    scope="text_only",
                    next_action="slide_rewrite",
                    must_add=[
                        f"本章缺少与其他方法章一致的 {' + '.join(missing)} 节奏; 后续应补结构页或把本页改成兼具章节分隔/框架回顾功能"
                    ],
                    hint=f"chapter {ci} rhythm differs from method chapters: missing {missing}",
                    audit_entry=entry,
                )

        # 5. Parallel paper/work openers should have symmetric block length.
        opener_terms = ("paper_intro", "work_intro", "paper_title", "论文封面", "代表工作")
        for ci, ch_slides in slides_by_ch.items():
            openers = []
            for s in ch_slides:
                arch = " ".join(s.get("archetype") or []) if isinstance(s.get("archetype"), list) else str(s.get("archetype") or "")
                title = s.get("target_title") or ""
                if any(t in arch or t in title for t in opener_terms):
                    openers.append(s)
            if len(openers) < 2:
                continue
            opener_indices = [s["_idx_int"] for s in openers]
            block_lengths = []
            for i, op in enumerate(openers):
                start = op["_idx_int"]
                end = (openers[i + 1]["_idx_int"] - 1) if i + 1 < len(openers) else ch_slides[-1]["_idx_int"]
                block = [s for s in ch_slides if start <= s["_idx_int"] <= end]
                # Ignore terminal chapter summary only if target_role=result? Keep simple: count physical block.
                block_lengths.append(len(block))
            if max(block_lengths) - min(block_lengths) <= 1:
                continue
            entry = {
                "type": "parallel_work_blocks_asymmetric",
                "chapter_index": ci,
                "opener_slide_indices": opener_indices,
                "block_lengths": block_lengths,
            }
            audit.append(entry)
            for op in openers:
                card = card_by_idx.get(op["_idx_int"])
                if not card:
                    continue
                _mark_gap(
                    card,
                    gap_type="parallel_work_asymmetry",
                    priority="high",
                    scope="text_only",
                    next_action="slide_rewrite",
                    must_add=[
                        f"同章代表工作必须同构展开; 当前 opener={opener_indices}, block_lengths={block_lengths}. 后续应统一为 opener→challenge→method/solution→result 或统一压缩为 opener→challenge→result"
                    ],
                    hint=f"parallel works in chapter {ci} are asymmetric: openers={opener_indices}, lengths={block_lengths}",
                    audit_entry=entry,
                )

        if audit:
            for c in cards:
                if isinstance(c, dict) and c.get("_structural_audits"):
                    c["gap_required"] = True
            data_audit = audit
        else:
            data_audit = []
        return cards, data_audit

    # Build source slide brief lookup (claim/title/text_samples)
    source_briefs: dict[str, dict] = {}
    for s in (raw.get("slide_candidates") or []):
        if not isinstance(s, dict):
            continue
        rid = str(s.get("resource_id") or s.get("object_id"))
        if not rid:
            continue
        source_briefs[rid] = {
            "title": s.get("title") or "",
            "claim": s.get("claim") or "",
            "what_this_slide_explains": s.get("what_this_slide_explains") or "",
            "salient_visuals": s.get("salient_visuals") or [],
            "transferable_to": s.get("transferable_to") or [],
            "do_not_reuse_when": s.get("do_not_reuse_when") or [],
            "reusability": s.get("reusability"),
            "deck_id": s.get("deck_id"),
            "section_id": s.get("section_id"),
            "source_owner": s.get("source_owner"),
        }

    # v33: OUTLINE now selects sources directly from the optimized material
    # library. Legacy raw-layered-candidates.json may be absent, so hydrate
    # source_slide_briefs from data/resources_library/material by selected
    # slide_id to keep GAP grounded in the actual byte-clone sources.
    selected_slide_ids: list[str] = []
    for s in outline_slides:
        if not isinstance(s, dict):
            continue
        for cand in list(s.get("source_resource_ids") or []) + list(s.get("alternates") or []):
            sid = cand.get("slide_id") if isinstance(cand, dict) else cand
            if sid:
                selected_slide_ids.append(str(sid))
    for m in matches:
        if not isinstance(m, dict):
            continue
        for cand in m.get("candidates") or []:
            if isinstance(cand, dict) and cand.get("resource_id"):
                selected_slide_ids.append(str(cand["resource_id"]))
    if selected_slide_ids:
        for b in oc.load_slide_briefs_by_ids(selected_slide_ids):
            rid = str(b.get("slide_id") or "")
            if not rid or rid in source_briefs:
                continue
            source_briefs[rid] = {
                "title": b.get("标题") or "",
                "claim": b.get("核心论断") or "",
                "what_this_slide_explains": b.get("本页讲什么") or "",
                "salient_visuals": b.get("视觉骨架") or [],
                "transferable_to": b.get("适合复用场景") or [],
                "do_not_reuse_when": b.get("不适合复用场景") or [],
                "reusability": b.get("可复用性"),
                "deck_id": b.get("deck_id"),
                "section_id": b.get("section_id"),
                "section_role": b.get("section_role"),
                "source_owner": "library",
            }

    # Build project_doc_anchors (anchor_term -> [doc_unit_ids])
    project_doc_anchors: dict[str, list[str]] = {}
    for d in (proj_doc_units.get("doc_units") or []):
        if not isinstance(d, dict) or not d.get("semantic_ok"):
            continue
        for term in (d.get("anchor_terms") or []):
            if not isinstance(term, str) or not term.strip():
                continue
            project_doc_anchors.setdefault(term.strip(), []).append(d.get("doc_unit_id"))

    coverage_per_chapter = (understanding.get("coverage_assessment") or {}).get("per_chapter") or []
    # Phase E.A: brief.claim_status_plan tells the gap_card skill which named
    # entities/claims need verification. The skill should map claims into
    # per-page evidence_needed entries when the page touches that claim.
    claim_status_plan = brief.get("claim_status_plan") or []

    context = {
        "outline_slides": outline_slides,
        "slide_matches": matches,
        "source_slide_briefs": source_briefs,
        "section_matches": [
            {"target_section_index": m.get("target_section_index"),
             "resource_id": m.get("resource_id"),
             "recommended_use": m.get("recommended_use"),
             "deck_id": m.get("deck_id")}
            for m in (section_match_doc.get("section_matches") or []) if isinstance(m, dict)
        ],
        "project_doc_anchors": project_doc_anchors,
        "coverage_per_chapter": coverage_per_chapter,
        "claim_status_plan": claim_status_plan,
    }
    n = len(outline_slides)

    resource_library_contract = oc.load_resource_library_contract_summary()

    # v7 (2026-07-28): WHOLE-DECK single Claude call.
    # Prior code (v30 Phase H): 8 sections in parallel, each Claude call scoped
    # to one section's slides. Problem: cross-chapter term/style/metric
    # inconsistencies (CNN vs 卷积神经网络, "加速比" vs "Speedup") never
    # surface because each call is blind to other sections.
    # Fix: one call covers all 50 slides. Payload measured at ~20-64 KB
    # (well below Claude 200K context). Set GAP_CARD_MODE="per_section" to
    # fall back to old behavior.
    import os as _os_g
    GAP_CARD_MODE = _os_g.environ.get("GAP_CARD_MODE", "whole_deck").lower()

    # Mark no-material slides (skill should emit no_supporting_material=true,
    # not fabricate hints)
    no_material_slide_indices: list = []
    for _s in outline_slides:
        if not isinstance(_s, dict):
            continue
        _kind = (_s.get("source_carrier_resource_kind") or "").lower()
        if _s.get("_no_material") or _kind == "no_supporting_material":
            no_material_slide_indices.append(_s.get("slide_index"))

    batch_errors: list[str] = []
    outcome: dict = {}

    if GAP_CARD_MODE == "whole_deck":
        # ────────────────────────────────────────────────────────────
        # Single whole-deck Claude call
        # ────────────────────────────────────────────────────────────
        # Trim source_briefs to only the resource_ids actually referenced by
        # outline slides (via slide-matches candidates[0]).
        relevant_rids: set = set()
        for m in matches:
            if not isinstance(m, dict):
                continue
            top = (m.get("candidates") or [{}])[0]
            rid = top.get("resource_id") or m.get("resource_id")
            if rid:
                relevant_rids.add(str(rid))
        trimmed_source_briefs = {rid: source_briefs[rid] for rid in relevant_rids if rid in source_briefs}

        whole_context = {
            "outline_slides": outline_slides,
            "slide_matches": matches,
            "source_slide_briefs": trimmed_source_briefs,
            "section_matches": [
                {"target_section_index": m.get("target_section_index"),
                 "resource_id": m.get("resource_id"),
                 "recommended_use": m.get("recommended_use"),
                 "deck_id": m.get("deck_id")}
                for m in (section_match_doc.get("section_matches") or [])
                if isinstance(m, dict)
            ],
            "project_doc_anchors": project_doc_anchors,
            "coverage_per_chapter": coverage_per_chapter,
            "claim_status_plan": claim_status_plan,
            "resource_library_contract": resource_library_contract,
            "batch_info": {"scope": "whole_deck", "n_pages": n},
            "no_supporting_material_slides": no_material_slide_indices,
        }
        # Timeout: 900s base + 30s/slide, capped 3600s.
        # Whole-deck is single Claude session, so slightly generous per-slide
        # allowance (Claude re-reads all context each turn).
        whole_timeout = min(3600, 900 + n * 30)
        prompt = (
            f"WHOLE DECK ({n} slides across {len(set(s.get('section_index') for s in outline_slides))} sections).\n"
            "Produce gap_cards for ALL outline slides in a single pass. Cross-chapter "
            "term/style/metric unification MUST be captured (e.g. same concept named "
            "differently in ch2 vs ch7). Section-internal coherence (transitions, "
            "connects_from_prev / connects_to_next) still applies per section.\n"
            f"Produce gap-cards.json: ONE gap_card per outline slide ({n} entries).\n"
            "Order MUST match outline_slides. See skill schema for fields.\n"
            "Return JSON only.\n\nINPUT:\n" + json.dumps(whole_context, ensure_ascii=False)
        )
        print(f"[GAP_CARD_GENERATION] whole-deck mode: {n} slides, "
              f"payload~{len(prompt)//1024}KB, timeout={whole_timeout}s", flush=True)
        try:
            outcome = _call_claude_json_retry(
                prompt,
                skill=["skills/gap_cards/gap_card_generation.md"],
                timeout=whole_timeout,
                stage_name="GAP_CARD[whole]",
                max_retries=3,
            )
        except Exception as exc:
            outcome = {"ok": False, "error": f"whole-deck Claude call failed: {str(exc)[:400]}"}

    else:
        # ────────────────────────────────────────────────────────────
        # Legacy per-section parallel mode (GAP_CARD_MODE=per_section)
        # ────────────────────────────────────────────────────────────
        from collections import defaultdict as _dd_g
        import concurrent.futures as _cf_g

        by_sec_g: dict = _dd_g(list)
        for s in outline_slides:
            si = s.get("section_index")
            try:
                si_int = int(si) if si is not None else 0
            except (TypeError, ValueError):
                si_int = 0
            by_sec_g[si_int].append(s)
        g_section_indices = sorted(by_sec_g.keys())
        print(f"[GAP_CARD_GENERATION] per-section mode (legacy): "
              f"{len(g_section_indices)} sections, "
              f"sizes={[len(by_sec_g[i]) for i in g_section_indices]}", flush=True)

        match_by_idx: dict[int, dict] = {}
        for m in matches:
            if not isinstance(m, dict) or m.get("target_slide_index") is None:
                continue
            try:
                match_by_idx[int(m.get("target_slide_index"))] = m
            except (TypeError, ValueError):
                continue

        def _gap_section_timeout(n_pages: int) -> int:
            return min(3600, 900 + n_pages * 90)

        def _gen_one_section_cards(sec_idx: int, sec_slides: list) -> tuple:
            sec_indices = {s.get("slide_index") for s in sec_slides}
            relevant_rids = set()
            for idx in sec_indices:
                mm = match_by_idx.get(int(idx)) if idx is not None else None
                if mm:
                    _top = (mm.get("candidates") or [{}])[0]
                    _rid = _top.get("resource_id") or mm.get("resource_id")
                    if _rid:
                        relevant_rids.add(str(_rid))
            sec_source_briefs = {rid: source_briefs[rid] for rid in relevant_rids if rid in source_briefs}
            sec_matches = []
            for mm in matches:
                if not isinstance(mm, dict):
                    continue
                try:
                    _target_idx = int(mm.get("target_slide_index") or 0)
                except (TypeError, ValueError):
                    continue
                if _target_idx in sec_indices:
                    sec_matches.append(mm)
            sec_no_material = [i for i in no_material_slide_indices
                               if i in sec_indices]
            s_context = {
                "outline_slides": sec_slides,
                "slide_matches": sec_matches,
                "source_slide_briefs": sec_source_briefs,
                "section_matches": [
                    {"target_section_index": m.get("target_section_index"),
                     "resource_id": m.get("resource_id"),
                     "recommended_use": m.get("recommended_use"),
                     "deck_id": m.get("deck_id")}
                    for m in (section_match_doc.get("section_matches") or [])
                    if isinstance(m, dict) and m.get("target_section_index") == sec_idx
                ],
                "project_doc_anchors": project_doc_anchors,
                "coverage_per_chapter": coverage_per_chapter,
                "claim_status_plan": claim_status_plan,
                "resource_library_contract": resource_library_contract,
                "batch_info": {"section_index": sec_idx, "n_pages": len(sec_slides)},
                "no_supporting_material_slides": sec_no_material,
            }
            prompt = (
                f"SECTION {sec_idx} batch ({len(sec_slides)} pages).\n"
                "All outline slides here belong to ONE chapter — produce gap_cards "
                "that flow naturally within this section (transitions, narrative_role, "
                "connects_from_prev / connects_to_next coherent).\n"
                f"Produce gap-cards.json: ONE gap_card per outline slide ({len(sec_slides)} entries).\n"
                "Order MUST match outline_slides. See skill schema for fields.\n"
                "Return JSON only.\n\nINPUT:\n" + json.dumps(s_context, ensure_ascii=False)
            )
            timeout = _gap_section_timeout(len(sec_slides))
            try:
                _outc = _call_claude_json_retry(
                    prompt,
                    skill=["skills/gap_cards/gap_card_generation.md"],
                    timeout=timeout,
                    stage_name=f"GAP_CARD[sec{sec_idx}]",
                    max_retries=3,
                )
                cards = [c for c in (_outc["data"].get("gap_cards") or []) if isinstance(c, dict)]
                if len(cards) != len(sec_slides):
                    raise RuntimeError(
                        f"section {sec_idx} gap_card count mismatch: got {len(cards)}, expected {len(sec_slides)}"
                    )
                return cards, []
            except RuntimeError as exc:
                return [], [f"section {sec_idx}: {str(exc)[:300]}"]

        g_results: dict = {}
        with _cf_g.ThreadPoolExecutor(max_workers=4, thread_name_prefix="gapcard") as pool:
            futs = {pool.submit(_gen_one_section_cards, idx, by_sec_g[idx]): idx
                    for idx in g_section_indices}
            for fut in _cf_g.as_completed(futs):
                idx = futs[fut]
                try:
                    g_results[idx] = fut.result()
                except Exception as exc:
                    g_results[idx] = ([], [f"section {idx} pool exception: {exc}"])

        all_cards: list = []
        for idx in g_section_indices:
            all_cards.extend(g_results[idx][0])
        all_cards.sort(key=lambda c: int(c.get("slide_index") or 0))
        for idx in g_section_indices:
            batch_errors.extend(g_results[idx][1])
        if all_cards and len(all_cards) == n and not batch_errors:
            outcome = {"ok": True, "data": {"gap_cards": all_cards}}
        elif all_cards:
            outcome = {"ok": True, "data": {"gap_cards": all_cards}, "partial_errors": batch_errors}
        else:
            outcome = {"ok": False, "error": "; ".join(batch_errors) or "all sections failed"}

    data = None
    if outcome.get("ok") and isinstance(outcome.get("data"), dict):
        cand = outcome["data"]
        cards = cand.get("gap_cards") if isinstance(cand.get("gap_cards"), list) else None
        # No deterministic padding: every outline slide must get a Claude gap card.
        if cards and len(cards) == n:
            data = {
                "schema_version": "1.0",
                "generated_at": now(),
                "project_id": project_id,
                "source": "claude" if not outcome.get("partial_errors") else "claude_partial",
                "partial_errors": outcome.get("partial_errors"),
                "gap_cards": cards,
            }
    elif (pdir / "gap-cards.json").exists():
        prior_gap = read_json(pdir / "gap-cards.json", {}) or {}
        prior_cards = prior_gap.get("gap_cards") if isinstance(prior_gap.get("gap_cards"), list) else None
        if prior_cards and len(prior_cards) == n:
            data = {
                "schema_version": prior_gap.get("schema_version") or "1.0",
                "generated_at": now(),
                "project_id": project_id,
                "source": "prior_gap_cards_plus_structural_audit",
                "partial_errors": [outcome.get("error") or "gap card model call failed"],
                "gap_cards": prior_cards,
            }
    if data is None:
        return {
            "ok": False,
            "stage": "GAP_CARD_GENERATION",
            "error": outcome.get("error") or "claude returned wrong card count",
            "partial_errors": outcome.get("partial_errors") or batch_errors,
            "retry_hint": "Fix the failed section batch in Claude and rerun; deterministic padding is disabled.",
        }
    cards_aug, structural_audit = _augment_gap_cards_with_structural_audit(data.get("gap_cards") or [])
    data["gap_cards"] = cards_aug
    if structural_audit:
        data["structural_audit"] = structural_audit
    write_json(pdir / "gap-cards.json", data)

    # Side artifact: chapter-level gap summary derived deterministically from
    # gap_cards + outline.section_breakdown. Decision-makers (DRAFT_REVIEW,
    # human gate) read this for "should I compress this chapter / get more
    # internal material" calls.
    try:
        outline_sections = outline_doc.get("section_breakdown") or []
        outline_chapters_by_index: dict[int, str] = {}
        for sec in outline_sections:
            if not isinstance(sec, dict):
                continue
            try:
                outline_chapters_by_index[int(sec.get("section_index"))] = sec.get("chapter") or ""
            except Exception:
                pass
        # Group cards by section_index pulled from outline.
        section_for_slide: dict[int, int] = {}
        for s in outline_slides:
            try:
                section_for_slide[int(s.get("slide_index"))] = int(s.get("section_index") or 0)
            except Exception:
                pass

        per_chapter: dict[int, dict] = {}
        for c in (data.get("gap_cards") or []):
            if not isinstance(c, dict):
                continue
            sec_idx = section_for_slide.get(int(c.get("slide_index") or -1)) or 0
            entry = per_chapter.setdefault(sec_idx, {
                "section_index": sec_idx,
                "chapter": outline_chapters_by_index.get(sec_idx, ""),
                "page_count": 0,
                "matched_count": 0,
                "weak_count": 0,
                "placeholder_count": 0,
                "internal_material_gaps": 0,
                "evidence_gaps": 0,
                "biggest_gaps": [],
                "recommendation": "",
            })
            entry["page_count"] += 1
            fit = c.get("reuse_fit") or "none"
            if fit == "weak": entry["weak_count"] += 1
            if fit == "none": entry["placeholder_count"] += 1
            if c.get("source_resource_id"): entry["matched_count"] += 1
            gtypes = c.get("gap_types") or []
            if "internal_material_gap" in gtypes: entry["internal_material_gaps"] += 1
            if "evidence_gap" in gtypes: entry["evidence_gaps"] += 1
            for kp in (c.get("must_add") or []):
                if kp and kp not in entry["biggest_gaps"] and len(entry["biggest_gaps"]) < 5:
                    entry["biggest_gaps"].append(kp)
        # Recommendations
        for sec_idx, entry in per_chapter.items():
            n = entry["page_count"]
            weak = entry["weak_count"] + entry["placeholder_count"]
            if n == 0:
                entry["recommendation"] = "skip"
                continue
            ratio = weak / n
            if entry["internal_material_gaps"] >= max(2, n // 3):
                entry["recommendation"] = "needs_internal_material; consider compressing chapter or pause for user input"
            elif ratio >= 0.5:
                entry["recommendation"] = f"thin coverage ({weak}/{n} weak/placeholder); consider compressing chapter or rewriting"
            elif ratio >= 0.25:
                entry["recommendation"] = f"partial coverage ({weak}/{n}); rewrite affected pages from project docs"
            else:
                entry["recommendation"] = "well covered"
        chapter_summary = {
            "schema_version": "1.0",
            "generated_at": now(),
            "project_id": project_id,
            "source": "deterministic_from_gap_cards",
            "chapters": [per_chapter[k] for k in sorted(per_chapter.keys())],
        }
        write_json(pdir / "chapter-gap-summary.json", chapter_summary)
    except Exception as exc:
        (pdir / "chapter-gap-summary-error.txt").write_text(f"chapter summary failed: {exc}\n", encoding="utf-8")

    # P20b: pre-generate per-slide annotation summaries via codex now that
    # matching + gap analysis are both done. Writes slide-annotations.json;
    # DRAFT_ASSEMBLY reads from disk instead of calling codex inline.
    try:
        anno_n, anno_total = _batch_codex_slide_annotations(project_id)
        print(f"[gap-cards] codex annotation summaries: {anno_n}/{anno_total} slides", flush=True)
    except Exception as exc:
        print(f"[gap-cards] codex annotation pre-gen failed (will fallback at draft): {exc}", flush=True)

    _write_stage_status(pdir, "gap-card-user-status.json",
                         source=data.get("source"),
                         card_count=len(data.get("gap_cards") or []),
                         partial_errors_count=len(data.get("partial_errors") or []),
                         awaiting_human_review=False,
                         human_feedback_round=0)

    return {
        "ok": True,
        "stage": "GAP_CARD_GENERATION",
        "gap_cards": str(pdir / "gap-cards.json"),
        "source": data.get("source"),
        "card_count": len(data.get("gap_cards") or []),
    }


def _finalize_slide_plan_artifacts(pdir, project_id: str, data: dict, brief: dict) -> dict:
    """Write slide-plan.json and reuse-first-outline.json compatibility artifact."""
    plan_slides = data.get("slides") if isinstance(data.get("slides"), list) else []
    slide_count = int(data.get("slide_count") or len(plan_slides))
    write_json(pdir / "slide-plan.json", data)

    # Back-compat: write reuse-first-outline.json. Older downstream readers
    # (DRAFT_REVIEW / SLIDE_REWRITE / etc.) keep working without changes.
    outline_compat = {
        "schema_version": "3.0",
        "generated_at": now(),
        "project_id": project_id,
        "source": "slide_plan_compat",
        "user_outline_priority": True,
        "topic": (brief.get("topic") or ""),
        "slide_count": slide_count,
        "slides": [
            {
                "slide_index": s.get("slide_index"),
                "target_title": s.get("target_title"),
                "target_role": s.get("target_role"),
                "target_claim": s.get("target_claim"),
                "plan_note": s.get("plan_note") or "",
                "page_purpose": s.get("page_purpose") or "",
                "outline_source": "user_outline" if s.get("reuse_binding", {}).get("source_owner") == "project"
                                   else ("template_library" if s.get("reuse_binding", {}).get("resource_id") else "new_slide_placeholder"),
                "source_candidates": [
                    {"resource_id": b.get("resource_id"),
                     "reuse_mode": b.get("reuse_mode"),
                     "rank": b.get("rank"),
                     "score": b.get("score"),
                     "confidence": b.get("confidence"),
                     "parts_to_reuse": b.get("parts_to_reuse"),
                     "parts_to_drop": b.get("parts_to_drop"),
                     "relation_to_others": b.get("relation_to_others"),
                     "gap_explanation": b.get("gap_explanation"),
                     "deck_id": b.get("deck_id"),
                     "section_id": b.get("section_id")}
                    for b in (s.get("reuse_bindings") or [])
                ],
                "selected_reuse": {
                    "resource_id": s.get("reuse_binding", {}).get("resource_id"),
                    "object_id":   s.get("reuse_binding", {}).get("resource_id"),
                    "reuse_mode":  s.get("reuse_binding", {}).get("reuse_mode") or "none",
                    "allowed_use": "full" if s.get("reuse_binding", {}).get("resource_id") else "none",
                    "forbidden_use": s.get("reuse_binding", {}).get("must_rewrite") or [],
                    "source_type": "claude_plan",
                    "why_match": s.get("page_purpose") or "",
                },
                "gap": [s.get("plan_note")] if s.get("plan_note") else [],
                "research_needed": s.get("evidence_need") or [],
            }
            for s in plan_slides
        ],
    }
    write_json(pdir / "reuse-first-outline.json", outline_compat)

    placeholder_count = sum(1 for s in plan_slides if not (s.get("reuse_binding") or {}).get("resource_id"))
    covered_count = sum(1 for s in plan_slides if (s.get("reuse_bindings") or []))
    total_candidates = sum(len(s.get("reuse_bindings") or []) for s in plan_slides)
    return {
        "ok": True, "stage": "SLIDE_PLAN",
        "slide_plan": str(pdir / "slide-plan.json"),
        "source": data.get("source"),
        "slide_count": slide_count,
        "placeholder_count": placeholder_count,
        "covered_targets": covered_count,
        "total_candidates": total_candidates,
        "target_coverage": round(covered_count / max(1, slide_count), 3),
    }


def _run_slide_plan(project_id: str, *, allow_claude_refine: bool = True) -> dict:
    """B3: merge outline.json + slide-matches.json into the final per-page plan.

    Outline is the ground truth (target_title, target_claim, key_points,
    needed_evidence). slide-matches provides the source binding. SLIDE_PLAN
    is a deterministic merge plus optional light Claude refine that produces:
      - one row per outline page (same order, same count)
      - reuse_binding filled in for pages that have a matched source
      - plan_note assembled from outline.key_points + outline.needed_evidence
        when the page is a placeholder

    DRAFT_ASSEMBLY calls this with allow_claude_refine=False so draft assembly
    remains a no-model byte-clone stage.
    """
    from . import claude_cli

    pdir = project_dir(project_id)

    # ═══ Gate: 上一阶段 (OUTLINE_GENERATION) 人类 approve 检查 ═══
    _gate_fail = _check_upstream_approval(
        pdir, "outline-user-status.json",
        upstream_stage_label="OUTLINE_GENERATION",
        current_stage_label="SLIDE_PLAN")
    if _gate_fail is not None:
        return _gate_fail

    brief = read_json(pdir / "idea-analysis.json", {}) or {}
    outline_doc = read_json(pdir / "outline.json", {}) or {}
    sm_doc = read_json(pdir / "slide-matches.json", {}) or {}
    section_match_doc = read_json(pdir / "section-matches.json", {}) or {}
    gc_doc = read_json(pdir / "gap-cards.json", {}) or {}
    matches = sm_doc.get("slide_matches") or []
    outline_slides = outline_doc.get("slides") if isinstance(outline_doc.get("slides"), list) else []
    gap_cards = gc_doc.get("gap_cards") if isinstance(gc_doc.get("gap_cards"), list) else []

    if not outline_slides and not matches:
        return {"ok": False, "stage": "SLIDE_PLAN",
                "error": "outline.json and slide-matches.json both empty"}

    # Index matches and gap_cards by target_slide_index.
    match_by_idx: dict[int, dict] = {}
    for m in matches:
        if isinstance(m, dict) and m.get("target_slide_index") is not None:
            try:
                match_by_idx[int(m["target_slide_index"])] = m
            except Exception:
                pass
    gc_by_idx: dict[int, dict] = {}
    for c in gap_cards:
        if isinstance(c, dict) and c.get("slide_index") is not None:
            try:
                gc_by_idx[int(c["slide_index"])] = c
            except Exception:
                pass

    slide_count = len(outline_slides) if outline_slides else len(matches)

    # v30 library-driven gate: outline is supposed to guarantee EVERY slide
    # has a library-backed source (hard-prune in OUTLINE deletes no_material
    # pages). If any slide reaches SLIDE_PLAN without a source_id, that's an
    # upstream contract violation — refuse to fall back to a placeholder,
    # since the whole v30 pipeline is byte-clone based and empty pages defeat
    # the point.
    _no_src: list[int] = []
    for _s in outline_slides:
        if not isinstance(_s, dict):
            continue
        _idx = _s.get("slide_index")
        _m = match_by_idx.get(int(_idx)) if _idx is not None else None
        _cands = (_m or {}).get("candidates") or []
        _rid = _cands[0].get("resource_id") if _cands and isinstance(_cands[0], dict) else None
        if not _rid:
            _no_src.append(_idx)
    if _no_src:
        return {"ok": False, "stage": "SLIDE_PLAN",
                "error": (f"v30 库驱动契约破裂: {len(_no_src)} 张 slide 无 source_resource_id "
                          f"({_no_src[:10]}...) — OUTLINE_GENERATION 的 hard-prune 应该已经删掉"
                          " 或换掉这些页. 检查 outline.json + slide-matches.json 一致性, "
                          " 修 OUTLINE 后重跑."),
                "no_source_slide_indices": _no_src}

    # Build SLIDE_PLAN rows deterministically — outline drives, matches plug in.
    plan_slides: list[dict] = []
    for s in outline_slides:
        if not isinstance(s, dict):
            continue
        idx = s.get("slide_index")
        m = match_by_idx.get(int(idx)) if idx is not None else None
        gc = gc_by_idx.get(int(idx)) if idx is not None else None
        # Schema 2.0: m has `candidates` (list of 0-3); primary = candidates[0].
        candidates_full = (m or {}).get("candidates") or []
        primary = candidates_full[0] if candidates_full else {}
        rid = primary.get("resource_id") if primary else None
        # v30 semantics: every slide has a source (guarded above). draft_action
        # is either as-is byte-clone or byte-clone + small text tweaks.
        # placeholder is no longer a valid draft_action in v30.
        _reuse_mode = (primary.get("recommended_reuse_mode") or "").lower()
        if gc:
            # gap_card 可以覆盖: 若 gc.draft_action 明确要求 partial (小改) 就听它,
            # 否则默认走 direct
            _gc_action = (gc.get("draft_action") or "").lower()
            if _gc_action in ("partial_rewrite", "copy_source_slide_with_text_edits"):
                draft_action = "partial_rewrite"
            else:
                draft_action = "copy_source_slide_as_is"
            reuse_fit = gc.get("reuse_fit") or "full"
            gap_required = bool(gc.get("gap_required", False))
            rewrite_scope = gc.get("rewrite_scope") or "none"
        elif _reuse_mode == "partial_reuse":
            # matching_fallback → 视觉骨架对但语义要小改
            draft_action = "partial_rewrite"
            reuse_fit = "partial"
            gap_required = False
            rewrite_scope = "text_only"
        else:
            # direct_slide_reuse (carrier_bound with strong alignment)
            draft_action = "copy_source_slide_as_is"
            reuse_fit = "full"
            gap_required = False
            rewrite_scope = "none"
        plan_note = ""
        # v30: no more placeholder branch (guarded at entry). plan_note only
        # carries a short hint about rewrite scope for partial pages.
        if draft_action == "partial_rewrite":
            _rewrite_hints = []
            for _mr in (primary.get("must_rewrite") or []):
                if isinstance(_mr, str):
                    _rewrite_hints.append(_mr)
                elif isinstance(_mr, dict):
                    _t = _mr.get("field") or _mr.get("text") or ""
                    if _t:
                        _rewrite_hints.append(str(_t))
            plan_note = ("需小改: " + ", ".join(_rewrite_hints[:5]))[:200] if _rewrite_hints else ""
        plan_slides.append({
            "slide_index": idx,
            "target_title": s.get("target_title") or "",
            "target_role": s.get("target_role") or "content",
            "target_claim": s.get("target_claim") or "",
            "page_purpose": s.get("page_purpose") or "",
            "key_points": s.get("key_points") or [],
            "needed_evidence": s.get("needed_evidence") or [],
            "plan_note": plan_note,
            # Backward-compat single binding == primary candidate.
            "reuse_binding": {
                "resource_id": rid,
                "reuse_mode": primary.get("recommended_reuse_mode") if rid else "none",
                "source_owner": primary.get("source_owner") if rid else None,
                "deck_id": primary.get("deck_id") if rid else None,
                "section_id": primary.get("section_id") if rid else None,
                "must_rewrite": primary.get("must_rewrite") or [],
            },
            # Schema 2.0: full list of candidates (1-3 for content pages,
            # 0-1 for placeholders/structural). DRAFT_ASSEMBLY_PLAN consumes
            # this to emit separator-page + N candidate-byte-clone rows per target.
            "reuse_bindings": [
                {
                    "rank": c.get("rank"),
                    "resource_id": c.get("resource_id"),
                    "reuse_mode": c.get("recommended_reuse_mode"),
                    "source_owner": c.get("source_owner"),
                    "deck_id": c.get("deck_id"),
                    "section_id": c.get("section_id"),
                    "must_rewrite": c.get("must_rewrite") or [],
                    "score": c.get("score"),
                    "confidence": c.get("confidence"),
                    "match_reason": c.get("match_reason"),
                    "parts_to_reuse": c.get("parts_to_reuse"),
                    "parts_to_drop": c.get("parts_to_drop"),
                    "relation_to_others": c.get("relation_to_others"),
                    "gap_explanation": c.get("gap_explanation"),
                    "template_svg": c.get("template_svg"),
                    # gap-based matching (new in skill v3):
                    "covered_aspects": c.get("covered_aspects") or [],
                    "residual_gap": c.get("residual_gap") or [],     # rank-1 only typically
                    "addresses_gap": c.get("addresses_gap") or [],   # rank-2/3 only typically
                }
                for c in candidates_full if isinstance(c, dict)
            ],
            # Preserve the aspects list at slide level so downstream consumers
            # (DRAFT_ASSEMBLY notes injection, audit/review) can see the
            # decomposition that drove rank selection.
            "target_aspects": (m or {}).get("aspects") or [],
            "chapter_index": s.get("chapter_index"),
            "section_index": s.get("section_index"),
            "section_titles": s.get("section_titles") or [],
            "active_section_index": s.get("active_section_index"),
            "agenda_style": s.get("agenda_style") or {},
            # New B-style explicit state — replaces ambiguous reuse_mode-as-action.
            "draft_action": draft_action,
            "reuse_fit": reuse_fit,
            "gap_required": gap_required,
            "rewrite_scope": rewrite_scope,
            # Single canonical gap source — gap_card if present
            "gap_card": gc,
            "evidence_need": s.get("needed_evidence") or [],
            "citation_need": bool(s.get("needed_evidence")),
        })

    data = {
        "schema_version": "5.0",
        "generated_at": now(),
        "project_id": project_id,
        "source": "deterministic_outline_plus_matches",
        "slide_count": slide_count,
        "slides": plan_slides,
        "reuse_rate": round(
            sum(1 for s in plan_slides if (s.get("reuse_binding") or {}).get("resource_id"))
            / max(1, slide_count), 3),
    }
    if not allow_claude_refine:
        data["source"] = "deterministic_outline_plus_matches_no_refine"
        brief_for_compat = _enrich_brief_for_matching(read_json(pdir / "idea-analysis.json", {}) or {})
        return _finalize_slide_plan_artifacts(pdir, project_id, data, brief_for_compat)

    # Phase F.2: Refine title/claim/page_purpose/proof_structure with Claude.
    # The deterministic merge above provides the SKELETON (every row has
    # reuse_binding + draft_action + gap_card already correctly set).
    # Claude's job is to apply brief.slide_writing_rules + chapter_page_archetype_plan
    # to polish per-page text. We DO NOT let Claude change resource_id /
    # reuse_binding / gap_card — only title/claim/page_purpose/proof_structure/plan_note.
    brief = _enrich_brief_for_matching(read_json(pdir / "idea-analysis.json", {}) or {})
    target_pages_for_skill = []
    for row in plan_slides:
        target_pages_for_skill.append({
            "target_slide_index": row.get("slide_index"),
            "target_role": row.get("target_role"),
            "target_claim_hint": row.get("target_claim") or "",
            "source_resource_id": (row.get("reuse_binding") or {}).get("resource_id"),
            "source_owner": (row.get("reuse_binding") or {}).get("source_owner"),
            "deck_id": (row.get("reuse_binding") or {}).get("deck_id"),
            "section_id": (row.get("reuse_binding") or {}).get("section_id"),
            "recommended_reuse_mode": (row.get("reuse_binding") or {}).get("reuse_mode"),
            "must_rewrite": (row.get("reuse_binding") or {}).get("must_rewrite") or [],
            "match_reason": "",
            "plan_note_hint": row.get("plan_note") or "",
            "page_purpose_hint": row.get("page_purpose") or "",
            "key_points": row.get("key_points") or [],
            "needed_evidence": row.get("needed_evidence") or [],
            "confidence": 0.85,
        })

    # Phase H: section-batched parallel Claude refine.
    # - Each batch = one chapter's target_pages → coherent in-section polish.
    # - Sections run in parallel, smart retry per section.
    # - Refine is a SOFT enhancement: per-section failure keeps that section's
    #   deterministic rows. Pipeline never blocks on refine.
    from collections import defaultdict as _dd_p
    import concurrent.futures as _cf_p

    brief_for_skill = {
        "topic": brief.get("topic"),
        "audience": brief.get("audience"),
        "scenario": brief.get("scenario"),
        "slide_count": slide_count,
        "story_style": (brief.get("narrative_blueprint") or {}).get("story_style") or "",
        "anchor_claims": (brief.get("narrative_blueprint") or {}).get("anchor_claims") or [],
        "chapter_page_archetype_plan": brief.get("chapter_page_archetype_plan") or [],
        "slide_writing_rules": brief.get("slide_writing_rules") or {},
        "technical_depth_policy": brief.get("technical_depth_policy") or {},
    }

    by_sec_p: dict[int, list[tuple[int, dict, dict]]] = _dd_p(list)
    for det_idx, (det_row, tp_row) in enumerate(zip(plan_slides, target_pages_for_skill)):
        # Try outline.section_index first; fall back to 0 group.
        si = None
        if outline_slides:
            for o in outline_slides:
                if isinstance(o, dict) and o.get("slide_index") == det_row.get("slide_index"):
                    si = o.get("section_index")
                    break
        try:
            si_int = int(si) if si is not None else 0
        except (TypeError, ValueError):
            si_int = 0
        by_sec_p[si_int].append((det_idx, det_row, tp_row))
    p_section_indices = sorted(by_sec_p.keys())
    print(f"[SLIDE_PLAN] section batching: {len(p_section_indices)} sections, "
          f"sizes={[len(by_sec_p[i]) for i in p_section_indices]}", flush=True)

    def _plan_section_timeout(n: int) -> int:
        return min(3600, 720 + n * 60)

    def _refine_one_section(sec_idx: int, sec_rows: list[tuple[int, dict, dict]]) -> tuple[list[tuple[int, dict]], list[str]]:
        """Refine one section. Returns ([(det_idx, refined_row)], errors).
        On failure, returns empty list (caller keeps deterministic rows)."""
        sec_target_pages = [t[2] for t in sec_rows]
        sec_skill_context = {
            "idea_analysis": brief_for_skill,
            "target_pages": sec_target_pages,
            "section_focus": sec_idx,
        }
        sec_prompt = (
            f"SECTION {sec_idx} batch ({len(sec_target_pages)} pages).\n"
            "Refine per-page title / claim / page_purpose / proof_structure / plan_note "
            "using brief.slide_writing_rules and brief.chapter_page_archetype_plan as hard "
            "constraints. Output schema is `slide_plan.md`. Keep one row per target_page, "
            "same order, same length. **DO NOT change reuse_binding.resource_id**.\n"
            "Return JSON only.\n\nINPUT:\n" + json.dumps(sec_skill_context, ensure_ascii=False)
        )
        try:
            outcome = _call_claude_json_retry(
                sec_prompt,
                skill=["skills/slide/slide_plan.md"],
                timeout=_plan_section_timeout(len(sec_target_pages)),
                stage_name=f"SLIDE_PLAN[sec{sec_idx}]",
                max_retries=3,
            )
            refined = outcome["data"].get("slides") or []
            if len(refined) != len(sec_target_pages):
                return [], [f"section {sec_idx}: row count mismatch "
                            f"(got {len(refined)}, expected {len(sec_target_pages)})"]
            return [(sec_rows[i][0], r) for i, r in enumerate(refined) if isinstance(r, dict)], []
        except RuntimeError as exc:
            return [], [f"section {sec_idx}: {str(exc)[:200]}"]

    refine_warnings: list[str] = []
    n_sec_refined = 0
    with _cf_p.ThreadPoolExecutor(max_workers=4, thread_name_prefix="slideplan") as pool:
        futs = {pool.submit(_refine_one_section, idx, by_sec_p[idx]): idx
                for idx in p_section_indices}
        for fut in _cf_p.as_completed(futs):
            idx = futs[fut]
            try:
                refined_pairs, errs = fut.result()
            except Exception as exc:
                refined_pairs, errs = [], [f"section {idx} pool exception: {exc}"]
            if errs:
                refine_warnings.extend(errs)
                continue
            # Merge refined fields into deterministic rows. Keep reuse_binding /
            # gap_card / draft_action untouched.
            for det_idx, ref in refined_pairs:
                det_row = plan_slides[det_idx]
                for k in ("target_title", "target_claim", "page_purpose",
                          "proof_structure", "plan_note"):
                    if ref.get(k) is not None:
                        det_row[k] = ref[k]
            n_sec_refined += 1

    if n_sec_refined == len(p_section_indices) and not refine_warnings:
        data["source"] = "claude_refined"
    elif n_sec_refined > 0:
        data["source"] = "claude_refined_partial"
        data["claude_refine_warning"] = "; ".join(refine_warnings)[:600]
        print(f"[SLIDE_PLAN] partial refine: {n_sec_refined}/{len(p_section_indices)} sections succeeded", flush=True)
    else:
        data["source"] = "deterministic_outline_plus_matches"
        data["claude_refine_warning"] = "; ".join(refine_warnings)[:600]
        print(f"[SLIDE_PLAN] all sections failed refine, keeping deterministic plan", flush=True)
    write_json(pdir / "slide-plan.json", data)

    # Back-compat: write reuse-first-outline.json. Older downstream readers
    # (DRAFT_REVIEW / SLIDE_REWRITE / etc.) keep working without changes.
    outline_compat = {
        "schema_version": "3.0",
        "generated_at": now(),
        "project_id": project_id,
        "source": "slide_plan_compat",
        "user_outline_priority": True,
        "topic": (brief.get("topic") or ""),
        "slide_count": slide_count,
        "slides": [
            {
                "slide_index": s.get("slide_index"),
                "target_title": s.get("target_title"),
                "target_role": s.get("target_role"),
                "target_claim": s.get("target_claim"),
                "plan_note": s.get("plan_note") or "",
                "page_purpose": s.get("page_purpose") or "",
                "outline_source": "user_outline" if s.get("reuse_binding", {}).get("source_owner") == "project"
                                   else ("template_library" if s.get("reuse_binding", {}).get("resource_id") else "new_slide_placeholder"),
                "source_candidates": [
                    {"resource_id": b.get("resource_id"),
                     "reuse_mode": b.get("reuse_mode"),
                     "rank": b.get("rank"),
                     "score": b.get("score"),
                     "confidence": b.get("confidence"),
                     "parts_to_reuse": b.get("parts_to_reuse"),
                     "parts_to_drop": b.get("parts_to_drop"),
                     "relation_to_others": b.get("relation_to_others"),
                     "gap_explanation": b.get("gap_explanation"),
                     "deck_id": b.get("deck_id"),
                     "section_id": b.get("section_id")}
                    for b in (s.get("reuse_bindings") or [])
                ],
                "selected_reuse": {
                    "resource_id": s.get("reuse_binding", {}).get("resource_id"),
                    "object_id":   s.get("reuse_binding", {}).get("resource_id"),
                    "reuse_mode":  s.get("reuse_binding", {}).get("reuse_mode") or "none",
                    "allowed_use": "full" if s.get("reuse_binding", {}).get("resource_id") else "none",
                    "forbidden_use": s.get("reuse_binding", {}).get("must_rewrite") or [],
                    "source_type": "claude_plan",
                    "why_match": s.get("page_purpose") or "",
                },
                "gap": [s.get("plan_note")] if s.get("plan_note") else [],
                "research_needed": s.get("evidence_need") or [],
            }
            for s in data["slides"]
        ],
    }
    write_json(pdir / "reuse-first-outline.json", outline_compat)

    placeholder_count = sum(1 for s in plan_slides if not (s.get("reuse_binding") or {}).get("resource_id"))
    covered_count = sum(1 for s in plan_slides if (s.get("reuse_bindings") or []))
    total_candidates = sum(len(s.get("reuse_bindings") or []) for s in plan_slides)
    return {
        "ok": True, "stage": "SLIDE_PLAN",
        "slide_plan": str(pdir / "slide-plan.json"),
        "source": data.get("source"),
        "slide_count": slide_count,
        "placeholder_count": placeholder_count,
        "covered_targets": covered_count,
        "total_candidates": total_candidates,
        "target_coverage": round(covered_count / max(1, slide_count), 3),
    }


def _semantic_profiles_index() -> dict:
    from . import template_library
    lib = template_library.load(ensure=False)
    idx = {}
    for entry in (lib.get("semantic_profiles") or {}).get("decks") or []:
        if not isinstance(entry, dict):
            continue
        deck_id = str(entry.get("deck_id") or "")
        if deck_id:
            idx[deck_id] = {"layer": "deck",
                "reusability": (entry.get("deck_semantics") or {}).get("presentation_type")}
        for s in entry.get("slides") or []:
            if isinstance(s, dict) and s.get("slide_id"):
                idx[str(s["slide_id"])] = {
                    "layer": "slide",
                    "reusability": s.get("reusability"),
                    "do_not_reuse_when": s.get("do_not_reuse_when") or [],
                    "rewrite_guidance": s.get("rewrite_guidance"),
                }
    return idx


def _run_reuse_decision_audit(project_id: str) -> dict:
    """W3: Hard gate before DRAFT_ASSEMBLY."""
    from . import claude_cli

    pdir = project_dir(project_id)
    plan = read_json(pdir / "slide-plan.json", {}) or {}
    matched = read_json(pdir / "matched-resource-pack.json", {}) or {}
    matched_idx = _matched_pack_index(matched)
    semantic_idx = _semantic_profiles_index()

    plan_slides = plan.get("slides") if isinstance(plan.get("slides"), list) else []
    audit_items = []
    for s in plan_slides:
        rb = s.get("reuse_binding") or {}
        rid = rb.get("resource_id")
        if not rid:
            continue
        audit_items.append({
            "slide_index": s.get("slide_index"),
            "claim_to_prove": s.get("claim_to_prove"),
            "page_purpose": s.get("page_purpose"),
            "resource_id": rid,
            "proposed_reuse_mode": rb.get("reuse_mode"),
            "proposed_allowed_use": rb.get("allowed_use"),
            "proposed_forbidden_use": rb.get("forbidden_use") or [],
            "matched_pack_meta": matched_idx.get(str(rid)) or {},
            "semantic_meta": semantic_idx.get(str(rid)) or {},
        })

    prompt = (
        "Audit each slide's reuse decision per the skill schema. Produce audits[] with decision in\n"
        "{approved, approved_with_rewrite, rejected}, audit_basis covering the 5 dimensions,\n"
        "required_actions when approved_with_rewrite. Build approved_resource_ids[] (decision != rejected)\n"
        "and rejected_resource_ids[]. Hard rule: semantic_meta.reusability=hard_topic blocks anything\n"
        "other than style_only when topic differs.\n"
        "Return JSON only.\n\nINPUT:\n" + json.dumps({"audit_items": audit_items}, ensure_ascii=False)
    )
    skill = claude_cli.skill_paths_for_agent("ReuseDecisionAuditAgent")
    outcome = claude_cli.call_claude_json(prompt, skill=skill, timeout=240)
    if outcome.get("ok") and isinstance(outcome.get("data"), dict):
        data = outcome["data"]
        data.setdefault("schema_version", "1.0")
        data["generated_at"] = now()
        data["source"] = "claude"
    else:
        audits = [
            {
                "slide_index": item["slide_index"],
                "resource_id": item["resource_id"],
                "decision": "approved_with_rewrite",
                "allowed_use": item.get("proposed_allowed_use") or "layout_only",
                "not_allowed": ["original_claim", "original_numeric_values"],
                "required_actions": ["rewrite title", "replace data labels", "regenerate caption"],
                "risk_level": "medium",
                "audit_basis": [],
                "stub_note": "audit deferred (claude call failed)",
            }
            for item in audit_items
        ]
        data = {
            "schema_version": "1.0",
            "generated_at": now(),
            "source": "stub",
            "fallback_reason": outcome.get("error"),
            "audits": audits,
            "approved_resource_ids": list({str(a["resource_id"]) for a in audits if a.get("decision") != "rejected"}),
            "rejected_resource_ids": [],
        }
    write_json(pdir / "reuse-decision-audit.json", data)
    return {"ok": True, "stage": "REUSE_DECISION_AUDIT",
            "reuse_decision_audit": str(pdir / "reuse-decision-audit.json"),
            "source": data.get("source"),
            "approved_count": len(data.get("approved_resource_ids") or []),
            "rejected_count": len(data.get("rejected_resource_ids") or [])}


def _draft_slide_rewrite_lines(slide: dict, selected: dict) -> list[str]:
    """Manuscript body lines for the DRAFT pass.

    DRAFT POLICY: when a slide is being pasted verbatim (direct_slide_reuse) we
    must NOT inject any extra body text — the source SVG already carries the
    page's content and any added text gets rendered as an OVERLAY by the
    renderer, producing visible "Reuse source / Mode / template slide" boxes
    on top of the source page. Audit lineage belongs in speaker notes and
    draft-source-lineage.json, not on the slide.

    For ``new_slide_placeholder`` pages we emit:
      - the target_title (used by the renderer's title region)
      - the target_claim (the page's main assertion)
      - a "本页待补充" line followed by the plan_note from SLIDE_PLAN

    Cover / agenda / closing pages get minimal labels.
    """
    title = str(slide.get("target_title") or f"Slide {slide.get('slide_index')}").strip()
    role = str(slide.get("target_role") or "content")
    mode = str(selected.get("reuse_mode") or "new_slide_placeholder")
    direct_paste = mode in {"direct_slide_reuse", "partial_slide_reuse"}
    if direct_paste:
        # Source SVG owns the page. Manuscript body stays empty so the renderer
        # doesn't draw on top of the pasted slide.
        return []
    lines: list[str] = []
    if role == "cover":
        lines.extend([title, "Reuse-first draft"])
        return lines
    if role == "agenda":
        lines.extend(["复用优先大纲", "先拼接已有页面与素材，再逐页补 gap 和统一风格"])
        return lines
    # New-page placeholder: emit claim + plan_note as the on-slide body
    claim = str(slide.get("target_claim") or "")
    plan_note = str(slide.get("plan_note") or "")
    if claim:
        lines.append(claim)
    if plan_note:
        lines.append(f"本页待补充: {plan_note}")
    elif not claim:
        lines.append("本页待补充内容")
    return lines


def _asset_catalog_by_path(project_id: str) -> dict[str, dict]:
    catalog = read_json(project_dir(project_id) / "project-asset-catalog.json", {})
    out: dict[str, dict] = {}
    for asset in catalog.get("assets") or []:
        if not isinstance(asset, dict):
            continue
        for key in ("path", "local_path"):
            path = str(asset.get(key) or "").strip()
            if path:
                out[path] = asset
    return out


def _approved_asset_from_reuse(project_id: str, selected: dict, *, slide_index: int) -> dict | None:
    path = str((selected or {}).get("path") or "").strip()
    if not path:
        return None
    catalog_asset = _asset_catalog_by_path(project_id).get(path) or {}
    asset_type = str(selected.get("source_type") or catalog_asset.get("asset_type") or catalog_asset.get("type") or "source_asset")
    usage_role = "source_ppt_page" if asset_type == "source_slide_svg" else "evidence_image"
    out = {
        **catalog_asset,
        "path": path,
        "local_path": path,
        "asset_type": asset_type,
        "asset_origin": catalog_asset.get("asset_origin") or "project_sources",
        "usage_role": catalog_asset.get("usage_role") or usage_role,
        "approved": True,
        "intended_slide": slide_index,
        "reuse_mode": selected.get("reuse_mode") or "direct_asset_reuse",
        "semantic_audit_required": bool(selected.get("semantic_audit_required", True)),
        "why_match": selected.get("why_match") or catalog_asset.get("content_summary") or catalog_asset.get("caption") or "",
    }
    for key in ("source_deck", "source_slide_index"):
        if selected.get(key) is not None:
            out[key] = selected.get(key)
    return out


def _reuse_asset_request(selected: dict, assets: list[dict]) -> dict:
    paths = [str(asset.get("local_path") or asset.get("path") or "").strip() for asset in assets if isinstance(asset, dict)]
    paths = [path for path in paths if path]
    asset_kind = str(selected.get("source_type") or (assets[0].get("asset_type") if assets else "") or "none")
    return {
        "needs_visual_asset": bool(paths),
        "asset_kind": asset_kind,
        "needs_generated_image": False,
        "prompt": "",
        "role": "evidence" if paths else "none",
        "candidate_asset_paths": paths,
        "source_reference_candidates": paths,
        "status": "bound" if paths else "not_required",
        "provider": "",
        "bound_asset": paths[0] if paths else "",
    }


def _reuse_image_decision(selected: dict, assets: list[dict], action: str) -> dict:
    path = ""
    if assets:
        path = str(assets[0].get("local_path") or assets[0].get("path") or "")
    decision = "use_existing" if path and action in {"direct_asset_reuse", "partial_slide_reuse", "direct_slide_reuse"} else action
    return {
        "decision": decision,
        "selected_path": path,
        "why_relevant": selected.get("why_match") or (assets[0].get("content_summary") if assets else "") or "reuse-first selected source",
        "how_to_explain": "Use the approved source visual as evidence, then rewrite labels and narration for this deck.",
        "source_priority": ["project_sources", "template_library", "gap_research"],
        "rejected_assets": [],
        "fallback_visual": "editable_diagram" if not path else "none",
    }


def _v2_visual_fields(slide: dict, selected: dict, idx: int, slide_count: int) -> dict:
    """Minimal V2 visual fields for DRAFT.

    Earlier versions of this function emitted an "evidence-matrix" (a blue
    3x3 audit table showing 对象/复用来源/当前处理/缺口/Reuse source/...)
    plus a `content_blocks` triple of Reuse source / Current gap / Rewrite
    plan.  Both of those got rendered on every page and produced the
    spurious blue boxes the user complained about in DRAFT.

    DRAFT must be a faithful copy of the source slide (or a clean stripped
    skeleton).  Audit/lineage info belongs in draft-assembly-plan.json,
    speaker notes, and the source-screenshots dir — NOT in the deck.  So
    we now emit ONLY the claim_to_prove + source_lineage, and leave
    content_blocks / visual_spec empty so the renderer doesn't overlay
    anything on the source SVG.
    """
    title = str(slide.get("target_title") or slide.get("title") or f"Slide {idx}")
    role = str(slide.get("target_role") or slide.get("story_role") or "content")
    claim = str(slide.get("target_claim") or slide.get("claim") or title)
    mode = str(selected.get("reuse_mode") or "new_slide_placeholder")
    lightweight = idx in {1, slide_count} or role in {"cover", "agenda", "closing"}
    return {
        "slide_composition": {
            "claim_to_prove": "" if lightweight else claim,
            "evidence_need": "source lineage and gap resolution",
            "evidence_available": bool(selected.get("path") or selected.get("object_id")),
            "primary_visual_role": mode,
            "required_blocks": [],
            "source_lineage": slide.get("source_candidates") or slide.get("source_lineage") or [],
        },
        "content_blocks": [],
        "visual_spec": {
            "kind": "passthrough",
            "layout_type": "passthrough",
            "purpose": claim,
            "editable": True,
            "generated_by_model": False,
            "data": {},
        },
    }


def _derive_draft_assembly_plan(pdir) -> dict:
    """Pure code: derive DRAFT actions deterministically from slide-plan.json.

    Writes draft-assembly-plan.json AND returns summary dict for the caller
    to include in stage result. No gate, no LLM. Callable from both
    _run_draft_assembly_plan (legacy stage handler) and _run_draft_assembly
    (merged stage, ensures plan is fresh before assembly).

    DRAFT IS BINARY:
      - reuse_binding.resource_id is non-null → ``direct_slide_reuse`` (paste
        the source slide verbatim). source_slide_svg_ref points at the SVG
        produced by either ``template_library`` (offline) or
        ``services._decompose_project_decks`` (project).
      - reuse_binding.resource_id is null → ``new_slide_placeholder``. The
        ``plan_note`` from SLIDE_PLAN is the on-page hint telling later
        SLIDE_REWRITE what the page should cover.
    """
    slide_plan = read_json(pdir / "slide-plan.json", {}) or {}
    project_slide_units = read_json(pdir / "project-slide-units.json", {}) or {}

    # Build slide_id -> svg_ref lookup from both library and project sides.
    slide_svg_lookup: dict[str, str] = {}
    # Library: byte-clone flow doesn't use SVG refs anymore — leave the
    # lookup empty for library slides (DRAFT_ASSEMBLY now reads the source
    # PPTX directly). Project still populates SVG refs below.
    pass
    # Project: pull from project-slide-units.json
    for s in (project_slide_units.get("slides") or []):
        if isinstance(s, dict) and s.get("slide_id"):
            ref = s.get("slide_svg_ref") or s.get("template_svg")
            if ref:
                slide_svg_lookup[str(s["slide_id"])] = str(ref)

    # Build slide_id -> (pptx_path, slide_index_1based) lookup for the
    # P0 pptx_slide_clone path. Library deck imports keep the pptx absolute path
    # in their manifest.json; project decks have it via project-deck-units.
    # Phase F.3: deck-profiles.json was deleted; rebuild the lookup by walking
    # decks-index.json + the per-deck `imports/<deck_id>/manifest.json`.
    slide_pptx_lookup: dict[str, tuple[str, int]] = {}
    try:
        from .template_library import LIBRARY_DIR
        index_path = LIBRARY_DIR / "decks-index.json"
        if index_path.exists():
            idx = read_json(index_path, {}) or {}
            decks_iter = [
                {
                    "deck_id": e.get("deck标识"),
                    "import_dir": f"data/resources_library/material/imports/{e.get('deck标识')}",
                    "source_path": e.get("源文件"),
                }
                for e in (idx.get("decks") or [])
            ]
        else:
            decks_iter = []
        for deck in decks_iter:
            if not isinstance(deck, dict):
                continue
            did = str(deck.get("deck_id"))
            import_dir = deck.get("import_dir")
            if not import_dir:
                continue
            manifest_path = ROOT / import_dir / "manifest.json"
            manifest = read_json(manifest_path, {}) or {}
            src_pptx = (manifest.get("source") or {}).get("pptx")
            if src_pptx and not Path(src_pptx).exists():
                # File renamed/moved since import. Try to locate by basename
                # under templates/. The import dir name keeps a hash so
                # matching by stem is fine.
                target_name = Path(src_pptx).name
                stem = Path(src_pptx).stem
                # Strip leading [YYYYMMDD] / 【YYYYMMDD】 prefix when looking
                # for a relocated file.
                import re as _re
                stripped = _re.sub(r"^[\[【]\d{6,8}[\]】]\s*-?\s*", "", stem)
                templates_dir = ROOT / "templates"
                # Search recursively for a .pptx whose stem matches either
                # the full or stripped form.
                for cand in templates_dir.rglob("*.pptx"):
                    if cand.stem == stem or cand.stem == stripped or cand.name == target_name:
                        src_pptx = str(cand)
                        break
            if not src_pptx or not Path(src_pptx).exists():
                continue
            slides = manifest.get("slides") or []
            for s in slides:
                if not isinstance(s, dict):
                    continue
                sl_idx = int(s.get("index") or 0)
                if sl_idx <= 0:
                    continue
                sid = f"{did}.slide_{sl_idx:02d}"
                slide_pptx_lookup[sid] = (src_pptx, sl_idx)
    except Exception:
        pass
    # Project: project-deck-units.json has deck_path; manifest in
    # decomposed/<slug>/manifest.json has slide indices.
    proj_deck_doc = read_json(pdir / "project-deck-units.json", {}) or {}
    for d in (proj_deck_doc.get("decks") or []):
        if not isinstance(d, dict):
            continue
        did = str(d.get("deck_id"))
        deck_path = d.get("deck_path")
        if not deck_path:
            continue
        # deck_path is project-relative (e.g. "sources/foo.pptx")
        abs_pptx = pdir / deck_path
        if not abs_pptx.exists():
            continue
        import_dir = pdir / (d.get("import_dir") or "")
        manifest_path = import_dir / "manifest.json"
        manifest = read_json(manifest_path, {}) or {}
        slides = manifest.get("slides") or []
        for s in slides:
            if not isinstance(s, dict):
                continue
            sl_idx = int(s.get("index") or 0)
            if sl_idx <= 0:
                continue
            sid = f"{did}.slide_{sl_idx:02d}"
            slide_pptx_lookup[sid] = (str(abs_pptx), sl_idx)

    # Phase I.fix: build rid → source_title lookup so divider notes can show
    # the gap between source slide's title (e.g. "层次2:算法优化") and the
    # target chapter (e.g. "背景与动机"). The brief library has each slide's
    # title in its slide_NN.json under the "标题" key (Chinese) or "title".
    source_title_lookup: dict[str, str] = {}
    try:
        from . import library_query
        for c in (library_query.load_library_candidates().get("slide") or []):
            rid = str(c.get("slide_id") or c.get("resource_id") or "")
            t = c.get("title") or c.get("标题") or ""
            if rid and t:
                source_title_lookup[rid] = t
    except Exception:
        pass

    plan_slides = slide_plan.get("slides") if isinstance(slide_plan.get("slides"), list) else []
    slide_count = len(plan_slides)

    # Schema 7.0: ONE physical row per target (rank-1 byte-clone).
    # rank-2/3 candidates ride along in `alternate_candidates` for downstream
    # speaker-notes injection — they are NOT separate physical pages.
    out_slides: list[dict] = []
    direct_reuse_n = 0
    placeholder_n = 0
    weak_fit_n = 0
    partial_fit_n = 0

    def _alt_cand(b: dict, pp: tuple[str, int] | None) -> dict:
        """Strip a reuse_bindings entry down to fields needed in speaker notes."""
        return {
            "rank": b.get("rank"),
            "resource_id": b.get("resource_id"),
            "deck_id": b.get("deck_id"),
            "section_id": b.get("section_id"),
            "source_owner": b.get("source_owner"),
            "source_pptx_path": pp[0] if pp else None,
            "source_slide_index": pp[1] if pp else None,
            "score": b.get("score"),
            "confidence": b.get("confidence"),
            "match_reason": b.get("match_reason"),
            "parts_to_reuse": b.get("parts_to_reuse"),
            "parts_to_drop": b.get("parts_to_drop"),
            "relation_to_others": b.get("relation_to_others"),
            "gap_explanation": b.get("gap_explanation"),
            "recommended_reuse_mode": b.get("reuse_mode"),
            # gap-based new fields
            "covered_aspects": b.get("covered_aspects") or [],
            "addresses_gap": b.get("addresses_gap") or [],
        }

    for s in plan_slides:
        if not isinstance(s, dict):
            continue
        target_idx = s.get("slide_index")
        bindings = s.get("reuse_bindings") or []
        primary = bindings[0] if bindings else {}
        alternates = bindings[1:] if len(bindings) > 1 else []
        rid = primary.get("resource_id") if primary else None
        gap_card = s.get("gap_card") or {}
        plan_note = s.get("plan_note") or ""
        reuse_fit = s.get("reuse_fit") or ("partial" if rid else "none")
        rewrite_scope = s.get("rewrite_scope") or "text_only"
        target_title = s.get("target_title") or ""
        target_role = s.get("target_role") or "content"
        target_claim = s.get("target_claim") or ""
        key_points = s.get("key_points") or []
        if reuse_fit == "weak":
            weak_fit_n += 1
        elif reuse_fit == "partial":
            partial_fit_n += 1

        # rank-1 source pptx lookup
        pp_primary = slide_pptx_lookup.get(str(rid)) if rid else None

        # alternates with their pptx lookup resolved
        alt_resolved = []
        for b in alternates:
            arid = b.get("resource_id")
            pp_alt = slide_pptx_lookup.get(str(arid)) if arid else None
            alt_resolved.append(_alt_cand(b, pp_alt))

        if rid and pp_primary:
            svg_ref = slide_svg_lookup.get(str(rid))
            # v30 fix: preserve SLIDE_PLAN's draft_action (direct or partial_rewrite)
            # instead of hard-coding "direct_slide_reuse". partial_rewrite pages
            # need to reach DRAFT_ASSEMBLY intact so text-edit branch fires.
            _plan_action = s.get("draft_action") or "copy_source_slide_as_is"
            # v31: DRAFT_ASSEMBLY 只做 byte-clone as-is. 即使 gap-card 里
            # standardized `edit_hints` (must_replace / must_add / must_remove) 存在,
            # DRAFT_ASSEMBLY 不 apply — 保留 hints 在 assembly plan 里, 未来
            # APPLY_EDITS stage (可选) 才根据 hints 做 partial_rewrite.
            # 因此这里强制 _draft_action = direct_slide_reuse, 不再走 partial 分支.
            # `draft_action_kind` 保留原 SLIDE_PLAN 决定 (作 hint 记录).
            _draft_action = "direct_slide_reuse"
            out_slides.append({
                "slide_index": target_idx,
                "draft_action": _draft_action,
                "draft_action_kind": _plan_action,
                "reuse_fit": reuse_fit,
                "gap_required": bool(s.get("gap_required", True)),
                "rewrite_scope": rewrite_scope,
                "source_resource_id": rid,
                "source_title": source_title_lookup.get(str(rid), ""),
                "source_owner": primary.get("source_owner"),
                "source_slide_svg_ref": svg_ref,
                "source_pptx_path": pp_primary[0],
                "source_slide_index": pp_primary[1],
                "source_asset_refs": [],
                "deck_id": primary.get("deck_id"),
                "section_id": primary.get("section_id"),
                "keep": gap_card.get("keep_from_source") or ["full_page"],
                "replace": gap_card.get("must_replace") or primary.get("must_rewrite") or [],
                "remove": gap_card.get("must_remove") or [],
                "add": gap_card.get("must_add") or [],
                "evidence_needed": gap_card.get("evidence_needed") or s.get("needed_evidence") or [],
                "next_action": gap_card.get("next_action"),
                "gap_types": gap_card.get("gap_types") or [],
                "fit_score": primary.get("score") if primary else gap_card.get("fit_score"),
                "confidence": primary.get("confidence"),
                "match_reason": primary.get("match_reason"),
                "parts_to_reuse": primary.get("parts_to_reuse"),
                "parts_to_drop": primary.get("parts_to_drop"),
                "relation_to_others": primary.get("relation_to_others"),
                "gap_explanation": primary.get("gap_explanation"),
                # gap-based fields from rank-1 (for notes rendering):
                "primary_covered_aspects": (primary or {}).get("covered_aspects") or [],
                "primary_residual_gap": (primary or {}).get("residual_gap") or [],
                "target_aspects": s.get("target_aspects") or [],
                "plan_note": plan_note or s.get("page_purpose") or "",
                "target_title": target_title,
                "target_role": target_role,
                "target_claim": target_claim,
                "key_points": key_points,
                "chapter_index": s.get("chapter_index"),
                "section_index": s.get("section_index"),
                "section_titles": s.get("section_titles") or [],
                "active_section_index": s.get("active_section_index"),
                "agenda_style": s.get("agenda_style") or {},
                "section_coherence": gap_card.get("section_coherence"),
                "transition_note": gap_card.get("transition_note"),
                # NEW: alternates ride along for speaker-notes injection.
                "alternate_candidates": alt_resolved,
                "n_total_candidates": len(bindings),
            })
            direct_reuse_n += 1
            continue
        # Placeholder fallthrough: no rid OR pptx lookup miss.
        out_slides.append({
            "slide_index": target_idx,
            "draft_action": "new_slide_placeholder",
            "draft_action_kind": "placeholder",
            "reuse_fit": "none",
            "gap_required": True,
            "rewrite_scope": rewrite_scope,
            "source_resource_id": None,
            "source_owner": None,
            "source_slide_svg_ref": None,
            "source_pptx_path": None,
            "source_slide_index": None,
            "source_asset_refs": [],
            "deck_id": None,
            "section_id": None,
            "keep": [],
            "replace": [],
            "remove": [],
            "add": gap_card.get("must_add") or list(key_points)[:3],
            "evidence_needed": gap_card.get("evidence_needed") or s.get("needed_evidence") or [],
            "next_action": gap_card.get("next_action"),
            "gap_types": gap_card.get("gap_types") or ["semantic_gap"],
            "fit_score": 0.0,
            "plan_note": plan_note or s.get("page_purpose") or "本页待补充内容",
            "target_title": target_title,
            "target_role": target_role,
            "target_claim": target_claim,
            "key_points": key_points,
            "section_coherence": gap_card.get("section_coherence"),
            "transition_note": gap_card.get("transition_note"),
            "alternate_candidates": alt_resolved,  # may have alts even if primary failed pptx lookup
            "n_total_candidates": len(bindings),
        })
        placeholder_n += 1

    # Phase I (replaces Phase G.1): section dividers are NO LONGER synthetic
    # rows injected here. Instead OUTLINE_GENERATION emits explicit divider
    # rows (target_role="section_divider", expected_resource_kind="slide_paste")
    # which flow through the cascade like any other page — SLIDE_MATCHING picks
    # a divider/agenda template from the library, byte-clone path renders them.
    # If a divider can't find a match, we fall back to _add_agenda_slide at
    # byte-clone time (see _run_draft_assembly).
    outline_doc = read_json(pdir / "outline.json", {}) or {}
    section_breakdown = outline_doc.get("section_breakdown") or []
    section_titles: list[str] = []
    for sec in section_breakdown:
        if isinstance(sec, dict):
            si = sec.get("section_index")
            chap = sec.get("chapter") or ""
            if si is not None:
                section_titles.append(chap or f"section {si}")

    data = {
        "schema_version": "7.0",  # one row per target; rank-1 byte-clone; alternates in row
        "generated_at": now(),
        "project_id": pdir.name,   # derived from pdir since helper takes only pdir
        "source": "deterministic_from_slide_plan",
        "slide_count": slide_count,
        "slides": out_slides,
        "by_action": {
            "direct_slide_reuse": direct_reuse_n,
            "new_slide_placeholder": placeholder_n,
        },
        "by_fit": {
            "partial": partial_fit_n,
            "weak": weak_fit_n,
        },
    }
    write_json(pdir / "draft-assembly-plan.json", data)
    covered_targets = sum(1 for s in plan_slides if (s.get("reuse_bindings") or []))
    total_alternates = sum(len(r.get("alternate_candidates") or []) for r in out_slides)
    return {
        "draft_assembly_plan": str(pdir / "draft-assembly-plan.json"),
        "source": data.get("source"),
        "slide_count": slide_count,
        "direct_slide_reuse": direct_reuse_n,
        "new_slide_placeholder": placeholder_n,
        "covered_targets": covered_targets,
        "target_coverage": round(covered_targets / max(1, slide_count), 3),
        "total_alternates_in_notes": total_alternates,
    }


def _run_draft_assembly_plan(project_id: str) -> dict:
    """Legacy stage handler kept for backwards-compat + explicit debug triggers.

    Main pipeline now: SLIDE_PLAN → DRAFT_ASSEMBLY (which calls
    _derive_draft_assembly_plan internally). This handler is a thin wrapper
    that runs the gate + helper for anyone who still invokes
    stage='DRAFT_ASSEMBLY_PLAN' directly.
    """
    pdir = project_dir(project_id)

    # ═══ Gate: 上一阶段 (GAP_CARD_GENERATION) 人类 approve 检查 ═══
    _gate_fail = _check_upstream_approval(
        pdir, "gap-card-user-status.json",
        upstream_stage_label="GAP_CARD_GENERATION",
        current_stage_label="DRAFT_ASSEMBLY_PLAN")
    if _gate_fail is not None:
        return _gate_fail

    summary = _derive_draft_assembly_plan(pdir)
    return {"ok": True, "stage": "DRAFT_ASSEMBLY_PLAN", **summary}


def _run_draft_assembly(project_id: str, payload: dict) -> dict:
    pdir = project_dir(project_id)
    inject_review_annotations = os.environ.get("PPT_INJECT_REVIEW_ANNOTATIONS", "0") == "1"

    # ═══ Gate: 上一阶段 (GAP_CARD_GENERATION) 人类 approve 检查 ═══
    _gate_fail = _check_upstream_approval(
        pdir, "gap-card-user-status.json",
        upstream_stage_label="GAP_CARD_GENERATION",
        current_stage_label="DRAFT_ASSEMBLY")
    if _gate_fail is not None:
        return _gate_fail

    if not (pdir / "gap-cards.json").exists():
        return {"ok": False, "stage": "DRAFT_ASSEMBLY",
                "error": "gap-cards.json missing — run GAP_CARD_GENERATION before DRAFT_ASSEMBLY",
                "retry_hint": "先跑 GAP_CARD_GENERATION，确认 gap-cards.json 后再拼草稿。"}

    def _compat_slide_count(path: Path) -> int:
        doc = read_json(path, {}) or {}
        if isinstance(doc.get("slides"), list):
            return len(doc.get("slides") or [])
        if isinstance((doc.get("plan") or {}).get("slides"), list):
            return len((doc.get("plan") or {}).get("slides") or [])
        if isinstance((doc.get("outline") or {}).get("slides"), list):
            return len((doc.get("outline") or {}).get("slides") or [])
        return int(doc.get("slide_count") or 0)

    outline_doc_for_freshness = read_json(pdir / "outline.json", {}) or {}
    current_outline_count = len(outline_doc_for_freshness.get("slides") or [])
    latest_upstream_mtime = max(
        (pdir / "outline.json").stat().st_mtime if (pdir / "outline.json").exists() else 0,
        (pdir / "gap-cards.json").stat().st_mtime if (pdir / "gap-cards.json").exists() else 0,
        (pdir / "slide-matches.json").stat().st_mtime if (pdir / "slide-matches.json").exists() else 0,
    )
    slide_plan_path = pdir / "slide-plan.json"
    reuse_outline_path = pdir / "reuse-first-outline.json"
    compat_missing = not slide_plan_path.exists() or not reuse_outline_path.exists()
    compat_count_mismatch = (
        current_outline_count > 0 and (
            _compat_slide_count(slide_plan_path) != current_outline_count
            or _compat_slide_count(reuse_outline_path) != current_outline_count
        )
    )
    compat_stale = (
        (slide_plan_path.exists() and slide_plan_path.stat().st_mtime < latest_upstream_mtime)
        or (reuse_outline_path.exists() and reuse_outline_path.stat().st_mtime < latest_upstream_mtime)
    )

    # ═══ v31: SLIDE_PLAN 已从 pipeline 删除, 但 slide-plan.json /
    # reuse-first-outline.json 仍是 draft-assembly-plan 派生的输入.
    # 若 artifacts 缺失/过期/页数不匹配, 内部自动跑 _run_slide_plan
    # (纯确定性合成, 无 LLM 决策).
    # 这是 SLIDE_PLAN 死后的兼容层, 未来清理时可整合进 _derive_draft_assembly_plan.
    if compat_missing or compat_count_mismatch or compat_stale:
        print("[DRAFT_ASSEMBLY] slide-plan.json / reuse-first-outline.json stale or invalid, "
              f"auto-invoking no-model slide-plan compatibility synthesis "
              f"(outline_count={current_outline_count}, "
              f"slide_plan_count={_compat_slide_count(slide_plan_path)}, "
              f"reuse_outline_count={_compat_slide_count(reuse_outline_path)}) "
              "(v31: SLIDE_PLAN no longer in pipeline)", flush=True)
        _sp_res = _run_slide_plan(project_id, allow_claude_refine=False)
        if not _sp_res.get("ok"):
            return {"ok": False, "stage": "DRAFT_ASSEMBLY",
                    "error": f"internal slide-plan synth failed: {_sp_res.get('error')}"}

    # ═══ Merged DRAFT_ASSEMBLY_PLAN: 确保 draft-assembly-plan.json 新鲜 ═══
    # 之前 SLIDE_PLAN → DRAFT_ASSEMBLY_PLAN → DRAFT_ASSEMBLY 三步, 现在合并到
    # 一步。plan 仍写盘 (中间产物, 可调试/审查). Legacy 手动触发
    # DRAFT_ASSEMBLY_PLAN 仍可用 (见 _run_draft_assembly_plan 薄壳).
    try:
        _assembly_plan_summary = _derive_draft_assembly_plan(pdir)
        print(f"[DRAFT_ASSEMBLY] plan derived: "
              f"slides={_assembly_plan_summary.get('slide_count')}, "
              f"direct_reuse={_assembly_plan_summary.get('direct_slide_reuse')}, "
              f"placeholder={_assembly_plan_summary.get('new_slide_placeholder')}",
              flush=True)
    except Exception as exc:
        print(f"[DRAFT_ASSEMBLY] plan derivation failed: {exc}; "
              f"falling back to prior draft-assembly-plan.json if any", flush=True)

    outline = read_json(pdir / "reuse-first-outline.json", {})
    slides = outline.get("slides") if isinstance(outline, dict) else []
    if not isinstance(slides, list) or not slides:
        return {"ok": False, "error": "reuse-first-outline.json missing or invalid"}

    # W4: prefer the upstream-produced draft-assembly-plan.json (from DRAFT_ASSEMBLY_PLAN).
    # If absent or stale, fall back to outline-derived assembly (legacy v2 behavior).
    existing_plan = read_json(pdir / "draft-assembly-plan.json", {}) or {}
    plan_source = str(existing_plan.get("source") or "")
    has_upstream_plan = plan_source in {"claude", "stub", "deterministic_from_slide_plan"} and isinstance(existing_plan.get("slides"), list)
    plan_by_idx = {}
    if has_upstream_plan:
        # Schema 7.0: one row per target keyed by slide_index (50 rows).
        for ps in existing_plan.get("slides") or []:
            if isinstance(ps, dict) and ps.get("slide_index") is not None:
                plan_by_idx[int(ps["slide_index"])] = ps

    audit_doc = read_json(pdir / "reuse-decision-audit.json", {}) or {}
    audits_by_rid = {str(a.get("resource_id")): a for a in (audit_doc.get("audits") or []) if isinstance(a, dict)}

    assembly_slides = []
    visual_slides = []
    lineage_entries = []
    manuscript = [
        "---",
        'schema_version: "2.0"',
        f'generated_at: "{now()}"',
        f"slide_count: {len(slides)}",
        f'topic: "{str(outline.get("topic") or project_id).replace(chr(34), chr(92) + chr(34))}"',
        'draft: true',
        "---",
    ]
    for slide in slides:
        idx = int(slide.get("slide_index") or len(assembly_slides) + 1)
        plan_entry = plan_by_idx.get(idx) if has_upstream_plan else None
        if plan_entry:
            rid = plan_entry.get("source_resource_id")
            action = str(plan_entry.get("draft_action") or "new_slide_placeholder")
            audit_meta = audits_by_rid.get(str(rid)) if rid else {}
            selected = {
                "source_type": "claude_plan",
                "resource_id": rid,
                "object_id": rid,
                "reuse_mode": action,
                "allowed_use": (audit_meta or {}).get("allowed_use") or "layout_only",
                "forbidden_use": plan_entry.get("replace") or (audit_meta or {}).get("not_allowed") or [],
                "why_match": "from draft-assembly-plan",
                "path": next((b.get("asset_resource_id") for b in plan_entry.get("asset_bindings") or [] if isinstance(b, dict)), None),
            }
        else:
            selected = slide.get("selected_reuse") if isinstance(slide.get("selected_reuse"), dict) else {}
            mode = str(selected.get("reuse_mode") or "new_slide_placeholder")
            action = mode if mode in {"direct_slide_reuse", "partial_slide_reuse", "direct_asset_reuse", "redraw_from_source", "adapt_structure"} else "placeholder"
        assets = []
        hydrated_asset = _approved_asset_from_reuse(project_id, selected, slide_index=idx)
        if hydrated_asset:
            assets.append(hydrated_asset)
        # Hydrate source_asset_refs from the plan into the staged assets list so
        # _stage_visual_assets copies them into build/assets/bound/ and the
        # renderer can place them. Each entry preserves source_bbox_emu when the
        # plan gave one — used by the bbox-aware overlay path.
        if plan_entry and isinstance(plan_entry.get("source_asset_refs"), list):
            for ref in plan_entry["source_asset_refs"]:
                if not isinstance(ref, dict):
                    continue
                ap = str(ref.get("asset_path") or ref.get("local_path") or "")
                if not ap:
                    continue
                # The path may be project-root-relative (e.g.
                # "data/resources_library/material/imports/<deck>/assets/imageNN.png"); copy
                # to project assets dir so _stage_visual_assets can stage it.
                src = (ROOT / ap).resolve() if not os.path.isabs(ap) else Path(ap)
                if src.exists() and src.is_file():
                    target_assets_dir = pdir / "assets"
                    target_assets_dir.mkdir(parents=True, exist_ok=True)
                    target = target_assets_dir / src.name
                    if not target.exists():
                        try:
                            shutil.copy2(src, target)
                        except Exception:
                            pass
                    assets.append({
                        "local_path": f"assets/{src.name}",
                        "path": f"assets/{src.name}",
                        "asset_resource_id": ref.get("asset_resource_id"),
                        "source_bbox_emu": ref.get("source_bbox_emu") or [],
                        "source_owner": ref.get("source_owner") or "library",
                    })
        copied_asset_refs = [
            str(asset.get("local_path") or asset.get("path") or "")
            for asset in assets
            if isinstance(asset, dict) and str(asset.get("local_path") or asset.get("path") or "").strip()
        ]
        copied_slide_refs = []
        if plan_entry and plan_entry.get("source_resource_id"):
            copied_slide_refs = [plan_entry["source_resource_id"]]
        elif selected.get("object_id"):
            copied_slide_refs = [selected.get("object_id")]
        placeholder_slots = (plan_entry or {}).get("placeholder_slots")
        if placeholder_slots is None:
            placeholder_slots = [] if copied_asset_refs or copied_slide_refs else ["evidence", "visual"]
        rewrite_instructions = (plan_entry or {}).get("rewrite_instructions") or [
            "verify topic/claim/object/caption/source context",
            "rewrite visible text for current project",
            "preserve source lineage in final slide",
        ]
        assembly_slides.append({
            "slide_index": idx,
            "draft_action": action,
            "source_lineage": slide.get("source_candidates") or [],
            "selected_reuse": selected,
            "copied_slide_refs": copied_slide_refs,
            "copied_asset_refs": copied_asset_refs,
            "placeholder_slots": placeholder_slots,
            "rewrite_instructions": rewrite_instructions,
            "gap_notes": slide.get("gap") or [],
            "speaker_note_feedback": f"Draft action {action}; revise after GAP_ANALYSIS.",
        })
        lineage_entries.append({
            "slide_index": idx,
            "draft_action": action,
            "source_resource_id": (plan_entry or {}).get("source_resource_id") or selected.get("resource_id") or selected.get("object_id"),
            "asset_paths": copied_asset_refs,
            "from_plan": bool(plan_entry),
        })
        visual_item = {
            "slide_index": idx,
            "visual_type": "image-and-bullets" if idx == 1 else "table" if slide.get("target_role") == "agenda" else "diagram",
            "layout_type": "title-image" if idx == 1 else "evidence-matrix" if slide.get("target_role") == "agenda" else "assertion-evidence",
            "assertion_title": slide.get("target_claim") or slide.get("target_title"),
            "reuse_decisions": [selected] if selected else [],
            "source_lineage": slide.get("source_candidates") or [],
            "assets": assets,
            "image_decision": _reuse_image_decision(selected, assets, action),
            "asset_request": _reuse_asset_request(selected, assets),
            # Direct-reuse hooks the renderer reads (set when the upstream plan
            # provided per-slide source SVG / asset refs).
            "reuse_mode": action if action in {"direct_slide_reuse", "partial_slide_reuse", "direct_asset_reuse"} else "",
            "source_slide_svg_ref": (plan_entry or {}).get("source_slide_svg_ref") or "",
            "source_asset_refs": (plan_entry or {}).get("source_asset_refs") or [],
            # New B-style + gap_card fields for renderer to draw warning bands /
            # gap-page cards. plan_entry comes from draft-assembly-plan.json which
            # carries these per-page fields.
            "draft_action_kind": (plan_entry or {}).get("draft_action_kind"),
            "reuse_fit": (plan_entry or {}).get("reuse_fit"),
            "gap_types": (plan_entry or {}).get("gap_types") or [],
            "next_action": (plan_entry or {}).get("next_action"),
            "fit_score": (plan_entry or {}).get("fit_score"),
            "target_title": (plan_entry or {}).get("target_title") or slide.get("target_title"),
            "target_claim": (plan_entry or {}).get("target_claim") or slide.get("target_claim") or "",
            "key_points": (plan_entry or {}).get("key_points") or [],
            "evidence_needed": (plan_entry or {}).get("evidence_needed") or [],
            "plan_note": (plan_entry or {}).get("plan_note") or "",
            "transition_note": (plan_entry or {}).get("transition_note"),
            "section_coherence": (plan_entry or {}).get("section_coherence"),
        }
        visual_item.update(_v2_visual_fields(slide, selected, idx, len(slides)))
        visual_slides.append(visual_item)
        manuscript.extend([
            "",
            f"## Slide {idx}: {slide.get('target_title') or f'Slide {idx}'}",
            "On-slide copy:",
            "\n".join(_draft_slide_rewrite_lines(slide, selected)),
            "Visual instruction: Draft page may preserve copied source visuals and placeholders.",
            f"Speaker notes: {assembly_slides[-1]['speaker_note_feedback']} Gaps: {'; '.join(slide.get('gap') or []) or 'none'}",
            "QA notes: Draft page requires gap analysis before final use.",
            f"Source references: {', '.join(copied_asset_refs) if copied_asset_refs else (copied_slide_refs[0] if copied_slide_refs else 'none')}",
        ])
        if idx < len(slides):
            manuscript.extend(["", "---"])
    visual = {
        "schema_version": "2.0",
        "generated_at": now(),
        "project_id": project_id,
        "source": "draft_assembly",
        "slide_count": len(slides),
        "slides": visual_slides,
    }
    # Only overwrite draft-assembly-plan.json when we didn't have an upstream plan.
    if not has_upstream_plan:
        plan = {
            "schema_version": "2.0",
            "generated_at": now(),
            "project_id": project_id,
            "source": "draft_assembly_tool_inferred",
            "slide_count": len(slides),
            "slides": assembly_slides,
        }
        write_json(pdir / "draft-assembly-plan.json", plan)
    write_json(pdir / "draft-visual-plan.json", visual)
    write_json(pdir / "draft-source-lineage.json", {
        "schema_version": "1.0",
        "generated_at": now(),
        "project_id": project_id,
        "source": "draft_assembly",
        "from_upstream_plan": has_upstream_plan,
        "entries": lineage_entries,
    })
    (pdir / "draft-manuscript.md").write_text("\n".join(manuscript).rstrip() + "\n", encoding="utf-8")

    # speaker-notes.md — full per-page "讲解脚本" so the user can open the
    # PPT and read what each page says + how to present it + what gap to
    # fill. Each slide gets a 600-1000 char block.
    try:
        gc_doc = read_json(pdir / "gap-cards.json", {}) or {}
        outline_doc = read_json(pdir / "outline.json", {}) or {}
        section_breakdown = outline_doc.get("section_breakdown") or []
        # Build slide_index → (chapter_name, position_in_chapter)
        chapter_of: dict[int, tuple[str, int, int]] = {}
        for sec in section_breakdown:
            if not isinstance(sec, dict):
                continue
            chap = sec.get("chapter") or ""
            indices = sec.get("slide_indices") or []
            total_in_chap = len(indices)
            for pos, si in enumerate(indices, start=1):
                try:
                    chapter_of[int(si)] = (chap, pos, total_in_chap)
                except Exception:
                    pass
        cards_by_idx = {int(c.get("slide_index")): c for c in (gc_doc.get("gap_cards") or [])
                        if isinstance(c, dict) and c.get("slide_index") is not None}
        # Pull draft-assembly-plan so we can quote the actual source pptx path
        # + slide index in each speaker-notes block (the user asked for this
        # before any analysis text, to make the lineage obvious in the deck).
        dap_doc = read_json(pdir / "draft-assembly-plan.json", {}) or {}
        dap_by_idx = {int(s.get("slide_index")): s for s in (dap_doc.get("slides") or [])
                      if isinstance(s, dict) and s.get("slide_index") is not None}
        # v30 fix: 建 outline slides lookup 供 prev/next 衔接 fallback 用
        outline_slides_by_idx: dict[int, dict] = {}
        for _s in (outline_doc.get("slides") or []):
            if isinstance(_s, dict) and _s.get("slide_index") is not None:
                try:
                    outline_slides_by_idx[int(_s["slide_index"])] = _s
                except Exception:
                    pass

        # v30 fix: role → 为什么放这里 的默认解释映射
        _role_purpose = {
            "cover": "全 deck 开场; 亮出主题 + 讲者身份, 为后续叙事定基调",
            "agenda": "章节导航; 让听众建立整份 deck 的心智地图",
            "section_divider": "章节切换; 明确前一章收束、下一章开启",
            "motivation": "问题驱动; 建立听众对'为什么值得听'的共鸣",
            "background": "铺垫共识; 让听众进入同一术语/框架的对话前提",
            "problem": "痛点显式化; 把听众带到接下来方法要回应的核心痛点",
            "framework": "总纲图; 建立后续 method 章共享的分层坐标",
            "method": "方法展开; 呈现具体技术路径 + 代表工作 + 论证收益",
            "case_study": "案例落地; 让方法从抽象方向变成可指认的具体成果",
            "experiment": "实证证据; 用数据验证方法承诺",
            "result": "结果证据; 收束前段方法 + 抛出可量化收益",
            "comparison": "对照定位; 明确方案相对 baseline / SOTA 的差别",
            "discussion": "延展讨论; 把已呈现方法抬升到趋势 / 局限 / 应用视角",
            "outlook": "未来展望; 收束当前工作 + 指向下一阶段研究方向",
            "closing": "全篇收束; 回扣 thesis + 未来愿景 + 致谢",
            "references": "引用页; 让听众能追溯来源",
        }

        def _default_why_here(role: str, pos: int, total: int, chap: str) -> str:
            """Derive '为什么放这里' fallback when gap_card 未给 narrative_role."""
            base = _role_purpose.get((role or "").lower(), "支撑本章叙事")
            if total == 0:
                return base
            if pos == 1:
                loc = "章首页"
            elif pos == total:
                loc = "章末页"
            else:
                loc = f"章中第 {pos}/{total} 页"
            if chap:
                return f"{loc} · {chap}: {base}"
            return f"{loc}: {base}"

        def _derive_how_to_present(target_claim: str, key_points: list, target_title: str) -> list[str]:
            """Derive '怎么讲解' steps from key_points if 未提供 how_to_present."""
            steps = []
            if target_claim:
                steps.append(f"先点题: {target_claim}")
            if isinstance(key_points, list):
                for kp in key_points:
                    if isinstance(kp, str) and kp.strip():
                        steps.append(f"展开: {kp.strip()}")
            if not steps and target_title:
                steps.append(f"围绕标题 '{target_title}' 展开一句概述, 让听众抓到本页主意图")
            # 兜底最后一步: 承接下一页
            steps.append("末尾回扣: 一句话总结本页承担的作用, 顺势切入下一页")
            return steps

        def _derive_transition(prev_slide: dict | None, next_slide: dict | None,
                                 same_chap_prev: bool, same_chap_next: bool) -> tuple[str, str]:
            """Derive '与前后页衔接' from prev/next slide title, 区分同章/跨章."""
            cfp = ""
            ctn = ""
            if prev_slide:
                ptitle = prev_slide.get("target_title") or ""
                if ptitle:
                    if same_chap_prev:
                        cfp = f"承接同章上一页《{ptitle}》"
                    else:
                        cfp = f"跨章承接上一章末《{ptitle}》, 明确本章开启新板块"
            if next_slide:
                ntitle = next_slide.get("target_title") or ""
                if ntitle:
                    if same_chap_next:
                        ctn = f"引出同章下一页《{ntitle}》"
                    else:
                        ctn = f"收束本章 + 引出下一章《{ntitle}》"
            return cfp, ctn

        notes_lines: list[str] = []
        for s in assembly_slides:
            idx = s.get("slide_index")
            try:
                idx_int = int(idx)
            except Exception:
                idx_int = -1
            gc = cards_by_idx.get(idx_int) or {}
            dapent = dap_by_idx.get(idx_int) or {}
            target_title = s.get("target_title") or gc.get("target_title") or f"Slide {idx}"
            target_claim = s.get("target_claim") or gc.get("target_claim") or ""
            ch, pos, total = chapter_of.get(idx_int, ("", 0, 0))
            # v30 fix: 从 outline slides 拿 role/key_points/prev/next 供 fallback 派生
            oslide = outline_slides_by_idx.get(idx_int) or {}
            target_role = oslide.get("target_role") or s.get("target_role") or ""
            key_points = oslide.get("key_points") or s.get("key_points") or []
            prev_oslide = outline_slides_by_idx.get(idx_int - 1)
            next_oslide = outline_slides_by_idx.get(idx_int + 1)
            same_chap_prev = (prev_oslide is not None
                              and prev_oslide.get("section_index") == oslide.get("section_index"))
            same_chap_next = (next_oslide is not None
                              and next_oslide.get("section_index") == oslide.get("section_index"))

            notes_lines.append(f"## Slide {idx}: {target_title}")
            # 0. Source lineage — must come FIRST so the lineage is obvious
            # before any analysis text (user request).
            src_path = dapent.get("source_pptx_path") or s.get("source_pptx_path")
            src_idx = dapent.get("source_slide_index") or s.get("source_slide_index")
            src_rid = dapent.get("source_resource_id") or gc.get("source_resource_id") or s.get("source_resource_id")
            if src_path:
                # Show file name (compact) on one line, full path on next.
                from pathlib import PurePath as _PP
                fname = _PP(src_path).name
                if src_idx:
                    notes_lines.append(f"【源页来源】 {fname} · 第 {src_idx} 页")
                else:
                    notes_lines.append(f"【源页来源】 {fname}")
                notes_lines.append(f"  · 完整路径: {src_path}")
                if src_rid:
                    notes_lines.append(f"  · resource_id: {src_rid}")
            else:
                notes_lines.append("【源页来源】 (placeholder / new slide — 无现成源页)")
                if src_rid:
                    notes_lines.append(f"  · 期望 resource_id: {src_rid}")
            # 1. Position
            if ch:
                notes_lines.append(f"【在 PPT 中的位置】 第 {idx} 页 · {ch} (本章第 {pos}/{total} 页)")
            else:
                notes_lines.append(f"【在 PPT 中的位置】 第 {idx}/{len(assembly_slides)} 页")
            # 2. What this page says
            what = gc.get("what_this_page_says") or target_claim or s.get("page_purpose") or ""
            notes_lines.append(f"【本页讲什么】 {what}")
            # 3. Why this page — 优先 gap_card, 否则从 role+pos+chapter 派生
            role_desc = gc.get("narrative_role") or oslide.get("page_purpose") or ""
            if not role_desc:
                role_desc = _default_why_here(target_role, pos, total, ch)
            notes_lines.append(f"【为什么放这里】 {role_desc}")
            # 4. How to present — 优先 gap_card, 否则从 key_points 派生
            steps = gc.get("how_to_present") or []
            if not steps:
                steps = _derive_how_to_present(target_claim, key_points, target_title)
            notes_lines.append("【怎么讲解】")
            for i, step in enumerate(steps, start=1):
                notes_lines.append(f"  {i}. {step}")
            # 5. Connect prev / next — 优先 gap_card, 否则从 prev/next slide title 派生
            cfp = gc.get("connects_from_prev") or ""
            ctn = gc.get("connects_to_next") or ""
            if not cfp and not ctn:
                cfp, ctn = _derive_transition(prev_oslide, next_oslide,
                                                same_chap_prev, same_chap_next)
            notes_lines.append("【与前后页衔接】")
            if cfp:
                notes_lines.append(f"  从上一页: {cfp}")
            else:
                notes_lines.append("  从上一页: (本页为 deck 开场)")
            if ctn:
                notes_lines.append(f"  到下一页: {ctn}")
            else:
                notes_lines.append("  到下一页: (本页为 deck 收尾)")
            # v30 fix: 移除 fit_score / reuse_fit 等生成侧 metadata (codex 提示"备注不可直接
            # 上台演讲, 应移除生成过程信息")。Gap 任务块只在有 v28 unification_hints /
            # legacy must_replace/must_add 时才输出, 且不带 fit_score。
            unification_hints = gc.get("unification_hints") or []
            mr = gc.get("must_replace") or []
            mrm = gc.get("must_remove") or []
            ma = gc.get("must_add") or []
            ev = gc.get("evidence_needed") or []
            if unification_hints or mr or mrm or ma or ev:
                notes_lines.append("【统一化 / Gap 任务】")
                for uh in unification_hints:
                    if isinstance(uh, dict) and uh.get("hint"):
                        notes_lines.append(f"  · [{uh.get('type', 'unify')}] {uh['hint']}")
                if mr:
                    notes_lines.append(f"  · 必须替换: {'; '.join(mr)}")
                if mrm:
                    notes_lines.append(f"  · 必须删除: {'; '.join(mrm)}")
                if ma:
                    notes_lines.append(f"  · 必须新增: {'; '.join(ma)}")
                if ev:
                    notes_lines.append(f"  · 待补证据: {'; '.join(ev)}")
            notes_lines.append("")
        (pdir / "speaker-notes.md").write_text("\n".join(notes_lines).rstrip() + "\n", encoding="utf-8")
    except Exception as exc:
        # Speaker-notes is supplementary; don't block DRAFT_ASSEMBLY on its
        # failure. Log so SYSTEM_REVIEW can catch.
        (pdir / "speaker-notes-error.txt").write_text(f"speaker-notes generation failed: {exc}\n", encoding="utf-8")

    # P3.2: copy source-slide screenshots next to each draft slide so the user
    # can visually verify "this draft page is actually a reuse of that source
    # page". Best-effort: looks for slide_<NN>.png/.svg under the resource's
    # import dir; resolves relative refs against project root.
    src_shot_dir = pdir / "draft-source-screenshots"
    src_shot_dir.mkdir(parents=True, exist_ok=True)
    for entry in lineage_entries:
        idx = entry.get("slide_index")
        rid = entry.get("source_resource_id") or ""
        if not rid or idx is None:
            continue
        plan_entry = plan_by_idx.get(int(idx)) if has_upstream_plan else None
        if not plan_entry:
            continue
        svg_ref = plan_entry.get("source_slide_svg_ref") or ""
        if not svg_ref:
            continue
        src_path = (ROOT / svg_ref) if not Path(svg_ref).is_absolute() else Path(svg_ref)
        if not src_path.exists():
            # Try project-dir-relative
            cand = pdir / svg_ref
            if cand.exists():
                src_path = cand
            else:
                continue
        # Copy SVG itself; the user can open the SVG to verify visually. Skip PNG
        # rasterization here — that requires an external converter and is best
        # effort only.
        target = src_shot_dir / f"slide-{int(idx):02d}-source.svg"
        try:
            target.write_bytes(src_path.read_bytes())
        except Exception:
            continue
    # Drop a README pointing users at the comparison
    try:
        (src_shot_dir / "README.md").write_text(
            "# Draft source-slide previews\n\n"
            "Each slide-NN-source.svg is the EXACT source slide that DRAFT_ASSEMBLY copied\n"
            "(when draft_action is direct_slide_reuse or partial_slide_reuse). Compare with\n"
            "screenshots/slide-NN.png to verify the reuse landed correctly. If a slide is\n"
            "missing here, the draft did NOT reuse a source page for it.\n",
            encoding="utf-8",
        )
    except Exception:
        pass
    snapshots = _snapshot_paths(pdir, FINAL_RENDER_ARTIFACTS)
    render = {"ok": False, "error": "draft render did not start"}
    prev_draft_env = os.environ.get("PPT_DRAFT_REUSE")
    try:
        (pdir / "manuscript.md").write_text((pdir / "draft-manuscript.md").read_text(encoding="utf-8"), encoding="utf-8")
        write_json(pdir / "visual-plan.json", visual)

        # ---------- P0/P6 path: pptx_slide_clone (byte-level) ----------
        # Try the byte-level clone path first. It handles direct_slide_reuse
        # pages by copying source PPTX slides verbatim. Placeholder pages still
        # need the gap_page_card renderer; we render those into a small SVG
        # build dir, then merge the two into the final deck.
        clone_ok = False
        try:
            assembly_plan = read_json(pdir / "draft-assembly-plan.json", {}) or {}
            plan_slides = assembly_plan.get("slides") or []
            # Precompute per-slide speaker-notes text so we can inject it
            # into the cloned PPT's notesSlide part (P10) AND write it to
            # speaker-notes.md (legacy artifact / SYSTEM_REVIEW reads it).
            outline_for_notes = read_json(pdir / "outline.json", {}) or {}
            section_breakdown_n = outline_for_notes.get("section_breakdown") or []
            chapter_of_n: dict[int, tuple[str, int, int]] = {}
            for sec in section_breakdown_n:
                if not isinstance(sec, dict):
                    continue
                chap = sec.get("chapter") or ""
                indices = sec.get("slide_indices") or []
                tot = len(indices)
                for pos, si in enumerate(indices, start=1):
                    try:
                        chapter_of_n[int(si)] = (chap, pos, tot)
                    except Exception:
                        pass
            gc_doc_n = read_json(pdir / "gap-cards.json", {}) or {}
            cards_n = {int(c.get("slide_index")): c for c in (gc_doc_n.get("gap_cards") or [])
                       if isinstance(c, dict) and c.get("slide_index") is not None}

            def _notes_text_for(spec: dict) -> str:
                idx = spec.get("slide_index")
                try:
                    idx_i = int(idx)
                except Exception:
                    idx_i = -1
                # Phase I.fix: section_divider notes branch ONLY for the
                # fallback case (no source — rendered by _add_agenda_slide).
                # When a divider successfully matched a library template via
                # cascade (Phase I.fix agenda-share), it goes through the normal
                # source-lineage notes path below.
                action_g = (spec.get("draft_action") or "").lower()
                role_g = (spec.get("target_role") or "").lower()
                has_source = bool(spec.get("source_pptx_path") and spec.get("source_slide_index"))
                if (action_g == "section_divider" or role_g == "section_divider") and not has_source:
                    # Derive chapter info from chapter_of_n lookup (which is
                    # built from outline.section_breakdown), not from spec —
                    # OUTLINE-emitted divider rows don't carry section_title.
                    ch, _, _ = chapter_of_n.get(idx_i, ("", 0, 0))
                    sec_idx = spec.get("section_index") or 0
                    sec_title = spec.get("section_title") or ch or spec.get("target_title") or ""
                    lines: list[str] = []
                    lines.append(f"【章节导引页】 进入第 {sec_idx} 章 · {sec_title}")
                    lines.append("  · 本页由 _add_agenda_slide 自动生成（库内无可用 divider 模板,fallback 渲染）")
                    lines.append(f"【演讲提示】 从前一章过渡到「{sec_title}」的导引页")
                    lines.append("  · 用 5-10 秒提示听众: 接下来这一章要讲什么、为何重要")
                    return "\n".join(lines)
                gc = cards_n.get(idx_i) or {}
                lines: list[str] = []
                target_title = spec.get("target_title") or gc.get("target_title") or f"Slide {idx}"
                # 0. Source first
                src_path = spec.get("source_pptx_path")
                src_idx = spec.get("source_slide_index")
                src_rid = spec.get("source_resource_id") or gc.get("source_resource_id")
                if src_path:
                    fname = Path(src_path).name
                    lines.append(f"【源页来源】 {fname}" + (f" · 第 {src_idx} 页" if src_idx else ""))
                    lines.append(f"  · 完整路径: {src_path}")
                    if src_rid:
                        lines.append(f"  · resource_id: {src_rid}")
                else:
                    lines.append("【源页来源】 (placeholder / new slide — 无现成源页)")
                    if src_rid:
                        lines.append(f"  · 期望 resource_id: {src_rid}")
                # Phase I.fix: 目录页差异说明 — for agenda/divider rows that
                # byte-clone a library template, the slide visually shows the
                # SOURCE's title (e.g. "层次2:算法优化") but the page is meant
                # to introduce a DIFFERENT chapter. Surface this gap so the
                # presenter knows to verbally pivot.
                if role_g in {"agenda", "section_divider"} and src_rid:
                    src_title = spec.get("source_title") or ""
                    target_chapter = ""
                    ch_pair = chapter_of_n.get(idx_i)
                    if ch_pair:
                        target_chapter = ch_pair[0]
                    target_chapter = target_chapter or target_title
                    if src_title and target_chapter and src_title.strip() != target_chapter.strip():
                        lines.append("【目录页差异说明 (字面 vs 实际)】")
                        lines.append(f"  · 源页面字面文字: 「{src_title}」")
                        lines.append(f"  · 本页实际章节: 「{target_chapter}」")
                        lines.append(f"  · 演讲建议: 把源标题理解为视觉模板,口头介绍当前章节即可;"
                                     f"无需为字面差异道歉")
                # 1. Position
                ch, pos, total = chapter_of_n.get(idx_i, ("", 0, 0))
                if ch:
                    lines.append(f"【在 PPT 中的位置】 第 {idx} 页 · {ch} (本章第 {pos}/{total} 页)")
                else:
                    lines.append(f"【在 PPT 中的位置】 第 {idx}/{len(plan_slides)} 页")
                # 2. What this page says
                what = gc.get("what_this_page_says") or spec.get("target_claim") or spec.get("plan_note") or ""
                if what:
                    lines.append(f"【本页讲什么】 {what}")
                # 3. Why this page
                role = gc.get("narrative_role") or spec.get("page_purpose") or ""
                if role:
                    lines.append(f"【为什么放这里】 {role}")
                # 4. How to present
                steps = gc.get("how_to_present") or []
                if steps:
                    lines.append("【怎么讲解】")
                    for j, st in enumerate(steps, start=1):
                        lines.append(f"  {j}. {st}")
                # 5. Connect prev / next
                cfp = gc.get("connects_from_prev") or ""
                ctn = gc.get("connects_to_next") or ""
                if cfp or ctn:
                    lines.append("【与前后页衔接】")
                    if cfp:
                        lines.append(f"  从上一页: {cfp}")
                    if ctn:
                        lines.append(f"  到下一页: {ctn}")
                # 6. Fit metric
                fit = gc.get("reuse_fit") or spec.get("reuse_fit") or "n/a"
                score = gc.get("fit_score") or spec.get("fit_score")
                if fit != "n/a" or score is not None:
                    lines.append(f"【适配度】 reuse_fit={fit}" + (f" · fit_score={score}" if score is not None else ""))
                # 7. Gap tasks
                lines.append("【Gap 任务】")
                if gc.get("must_replace"):
                    lines.append(f"  · 必须替换: {'; '.join(gc.get('must_replace'))}")
                if gc.get("must_remove"):
                    lines.append(f"  · 必须删除: {'; '.join(gc.get('must_remove'))}")
                if gc.get("must_add"):
                    lines.append(f"  · 必须新增: {'; '.join(gc.get('must_add'))}")
                if gc.get("evidence_needed"):
                    lines.append(f"  · 待补证据: {'; '.join(gc.get('evidence_needed'))}")
                if gc.get("next_action"):
                    lines.append(f"  · 下一动作: {gc.get('next_action')}")
                # 7b. Aspect coverage (gap-based matching, new in skill v3)
                tgt_aspects = spec.get("target_aspects") or []
                covered = spec.get("primary_covered_aspects") or []
                residual = spec.get("primary_residual_gap") or []
                if tgt_aspects:
                    lines.append("")
                    lines.append(f"【本页 aspect 拆解 ({len(tgt_aspects)} 个)】")
                    for a in tgt_aspects[:6]:
                        if isinstance(a, dict):
                            aid = a.get("aspect_id", "?")
                            atext = (a.get("aspect_text") or "")[:50]
                            atype = a.get("aspect_type", "")
                            lines.append(f"  {aid} [{atype}]: {atext}")
                if covered:
                    lines.append(f"  rank-1 已覆盖: {' / '.join(str(x)[:30] for x in covered[:5])}")
                if residual:
                    lines.append(f"  rank-1 未覆盖 (rank-2/3 补): "
                                 f"{' / '.join(str(x)[:30] for x in residual[:5])}")
                # 8. Alternate candidates (rank 2/3) — only reference info, the
                # primary slide is what was actually byte-cloned above. Show the
                # reviewer what OTHER source slides were considered, where to
                # find them, and how they relate to the primary pick.
                alts = spec.get("alternate_candidates") or []
                if alts:
                    lines.append("")
                    lines.append(f"【备选候选（共 {len(alts)} 个）】")
                    for c in alts:
                        if not isinstance(c, dict):
                            continue
                        rank = c.get("rank") or "?"
                        sc = c.get("score")
                        sc_str = f"{sc:.2f}" if isinstance(sc, (int, float)) else "?"
                        lines.append("")
                        lines.append(f"▸ 备选 #{rank}  (score {sc_str})")
                        # 来源说清楚
                        alt_pptx = c.get("source_pptx_path")
                        alt_sli = c.get("source_slide_index")
                        if alt_pptx:
                            fname = Path(alt_pptx).name
                            lines.append(f"  来源: {fname}" + (f" · 第 {alt_sli} 页" if alt_sli else ""))
                        if c.get("deck_id") or c.get("section_id"):
                            ddi = (c.get("deck_id") or "?").split(".")[-1]
                            ssi = (c.get("section_id") or "").split(".")[-1] if c.get("section_id") else ""
                            lines.append(f"  来自: deck {ddi}" + (f" / {ssi}" if ssi else ""))
                        if c.get("resource_id"):
                            lines.append(f"  resource_id: {c.get('resource_id')}")
                        if c.get("addresses_gap"):
                            lines.append(f"  补 gap: {' / '.join(str(x)[:30] for x in c.get('addresses_gap', [])[:3])}")
                        if c.get("match_reason"):
                            lines.append(f"  入选原因: {c.get('match_reason')}")
                        if c.get("parts_to_reuse"):
                            lines.append(f"  可用部分: {c.get('parts_to_reuse')}")
                        if c.get("parts_to_drop"):
                            lines.append(f"  应丢弃: {c.get('parts_to_drop')}")
                        if c.get("relation_to_others"):
                            lines.append(f"  与 rank-1 关系: {c.get('relation_to_others')}")
                        if c.get("gap_explanation"):
                            lines.append(f"  ⚠ Gap: {c.get('gap_explanation')}")

                # Char budget: hard ceiling at ~1500 chars. The 8 sections of
                # primary metadata + Gap tasks already occupy ~600-800 chars on
                # detail-rich pages; alternates need ~150-250 chars each. So a
                # 3-candidate page lands around 1100-1300 chars. 1500 cap leaves
                # headroom for a 4th-line edge case without truncating alternates.
                full = "\n".join(lines)
                MAX_CHARS = 1500
                if len(full) > MAX_CHARS:
                    full = full[:MAX_CHARS - 20].rstrip() + "\n…(已截断, 节约篇幅)"
                return full

            # Pre-build notes for every plan slide; key by slide_index so we
            # can inject by position in the cloned deck.
            notes_by_idx: dict[int, str] = {}
            for sp in plan_slides:
                try:
                    notes_by_idx[int(sp.get("slide_index"))] = _notes_text_for(sp)
                except Exception:
                    pass

            # Only attempt clone if every direct_slide_reuse page has source_pptx_path.
            needs_clone = [s for s in plan_slides if s.get("draft_action") == "direct_slide_reuse"]
            ready_for_clone = [s for s in needs_clone if s.get("source_pptx_path") and s.get("source_slide_index")]
            if needs_clone and len(ready_for_clone) == len(needs_clone):
                from . import pptx_slide_clone
                from pptx import Presentation as _Pres
                from pptx.oxml.ns import qn as _qn
                from pptx.enum.shapes import MSO_SHAPE
                from collections import Counter as _Counter

                target_pres = _Pres()
                while len(target_pres.slides) > 0:
                    rId = target_pres.slides._sldIdLst[0].rId
                    target_pres.part.drop_rel(rId)
                    del target_pres.slides._sldIdLst[0]

                # P7 (revised): target canvas = DOMINANT source sldSz (mode).
                # PowerPoint's copy-paste only preserves format when source and
                # target sldSz match exactly. Cross-size scaling stretches the
                # spTree EMU coords but does NOT scale font pt sizes or the
                # layout/master design coords — text ends up relatively small,
                # layouts mis-positioned, images blurry. So we maximize the
                # number of slides where source == target by picking the most
                # common source size; the minority that mismatch still get
                # P8 EMU rescale.
                size_seen: list[tuple[int, int]] = []
                for s in plan_slides:
                    sp = s.get("source_pptx_path")
                    if not sp or not Path(sp).exists():
                        continue
                    try:
                        src_p = pptx_slide_clone._open_source(sp)
                        src_pres_xml = src_p.part._element
                        sldSz_el = src_pres_xml.find(_qn("p:sldSz"))
                        if sldSz_el is not None:
                            cx = int(sldSz_el.get("cx") or 0)
                            cy = int(sldSz_el.get("cy") or 0)
                            if cx and cy:
                                size_seen.append((cx, cy))
                    except Exception:
                        pass
                if size_seen:
                    # Pick the (cx, cy) that appears in the most slides; on
                    # ties prefer the larger canvas (so we never accidentally
                    # downscale a high-DPI source unless it really is the
                    # minority).
                    from collections import Counter as _Counter
                    cnt = _Counter(size_seen)
                    cx_win, cy_win = max(cnt.items(),
                                         key=lambda kv: (kv[1], kv[0][0], kv[0][1]))[0]
                    print(f"[draft-assembly] sldSz distribution: {dict(cnt)} → target {cx_win}×{cy_win}", flush=True)
                    tgt_xml = target_pres.part._element
                    tgt_sldSz = tgt_xml.find(_qn("p:sldSz"))
                    if tgt_sldSz is not None:
                        tgt_sldSz.set("cx", str(cx_win))
                        tgt_sldSz.set("cy", str(cy_win))
                        # Preserve correct type attribute
                        ratio = cx_win / max(1, cy_win)
                        if abs(ratio - 16 / 9) < 0.05:
                            tgt_sldSz.set("type", "screen16x9")
                        elif abs(ratio - 4 / 3) < 0.05:
                            tgt_sldSz.set("type", "screen4x3")

                state = pptx_slide_clone._CloneState(target_pres)
                placeholder_pages: list = []
                clone_integrity_warnings: list = []  # v30 fix F

                # Build section title list (used by agenda renderer).
                outline_doc_for_agenda = read_json(pdir / "outline.json", {}) or {}
                section_titles_list: list[str] = []
                for sec in (outline_doc_for_agenda.get("section_breakdown") or []):
                    if isinstance(sec, dict) and sec.get("chapter"):
                        section_titles_list.append(str(sec.get("chapter")))
                # Build slide_index → active section index for mini-agendas (1-based).
                first_slide_of_section: dict[int, int] = {}
                for i, sec in enumerate((outline_doc_for_agenda.get("section_breakdown") or []), start=1):
                    if not isinstance(sec, dict):
                        continue
                    indices = sec.get("slide_indices") or []
                    if indices:
                        try:
                            first_slide_of_section[int(indices[0])] = i
                        except Exception:
                            pass

                def _add_agenda_slide(target_pres, section_titles, active_idx_1based):
                    """Render agenda/divider pages with the required color contract.

                    active_idx_1based=0/None means full TOC: all chapter titles black.
                    active_idx_1based=N means section TOC: chapter N black, others white.
                    """
                    from pptx.util import Inches, Pt
                    from pptx.dml.color import RGBColor
                    from pptx.enum.shapes import MSO_SHAPE
                    # Pick first layout (cloned ones preferred; else blank)
                    if len(target_pres.slide_layouts) > 0:
                        layout = target_pres.slide_layouts[0]
                    else:
                        from pptx import Presentation as _P
                        seed = _P()
                        layout = seed.slide_layouts[6] if len(seed.slide_layouts) > 6 else seed.slide_layouts[0]
                    new = target_pres.slides.add_slide(layout)
                    # Erase any inherited placeholder content
                    spTree = new.shapes._spTree
                    for child in list(spTree):
                        from pptx.oxml.ns import qn as _qn2
                        if child.tag in (_qn2("p:sp"), _qn2("p:pic"), _qn2("p:grpSp"), _qn2("p:graphicFrame")):
                            spTree.remove(child)
                    is_section_toc = bool(active_idx_1based)
                    bg = new.background.fill
                    bg.solid()
                    if is_section_toc:
                        bg.fore_color.rgb = RGBColor(0x13, 0x1A, 0x24)
                    else:
                        bg.fore_color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
                    # Title
                    tx = new.shapes.add_textbox(Inches(0.6), Inches(0.4), Inches(9), Inches(0.9))
                    tf = tx.text_frame
                    tf.text = "汇报议程"
                    tf.paragraphs[0].font.size = Pt(36)
                    tf.paragraphs[0].font.bold = True
                    tf.paragraphs[0].font.color.rgb = (
                        RGBColor(0xFF, 0xFF, 0xFF) if is_section_toc
                        else RGBColor(0x10, 0x10, 0x10)
                    )
                    # Section list as numbered bullets
                    ly = 1.6
                    for i, ch in enumerate(section_titles, start=1):
                        if is_section_toc and i == active_idx_1based:
                            band = new.shapes.add_shape(
                                MSO_SHAPE.RECTANGLE,
                                Inches(0.55), Inches(ly - 0.08), Inches(8.95), Inches(0.58)
                            )
                            band.fill.solid()
                            band.fill.fore_color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
                            band.line.fill.background()
                        tb = new.shapes.add_textbox(Inches(0.8), Inches(ly), Inches(8.5), Inches(0.55))
                        ttf = tb.text_frame
                        ttf.word_wrap = True
                        p = ttf.paragraphs[0]
                        run_num = p.add_run()
                        run_num.text = f"{i:02d}    "
                        run_num.font.size = Pt(22)
                        run_num.font.bold = True
                        run_title = p.add_run()
                        run_title.text = ch
                        run_title.font.size = Pt(22)
                        if not is_section_toc:
                            run_num.font.color.rgb = RGBColor(0x10, 0x10, 0x10)
                            run_title.font.color.rgb = RGBColor(0x10, 0x10, 0x10)
                        elif i == active_idx_1based:
                            run_num.font.color.rgb = RGBColor(0x10, 0x10, 0x10)
                            run_title.font.color.rgb = RGBColor(0x10, 0x10, 0x10)
                            run_title.font.bold = True
                        else:
                            run_num.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
                            run_title.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
                        ly += 0.7
                    return new

                def _add_cover_slide(target_pres, title, subtitle=None):
                    """Render a simple project-specific cover while preserving lineage."""
                    from pptx.util import Inches, Pt
                    from pptx.dml.color import RGBColor
                    if len(target_pres.slide_layouts) > 0:
                        layout = target_pres.slide_layouts[0]
                    else:
                        from pptx import Presentation as _P
                        seed = _P()
                        layout = seed.slide_layouts[6] if len(seed.slide_layouts) > 6 else seed.slide_layouts[0]
                    new = target_pres.slides.add_slide(layout)
                    spTree = new.shapes._spTree
                    for child in list(spTree):
                        from pptx.oxml.ns import qn as _qn2
                        if child.tag in (_qn2("p:sp"), _qn2("p:pic"), _qn2("p:grpSp"), _qn2("p:graphicFrame")):
                            spTree.remove(child)
                    bg = new.background.fill
                    bg.solid()
                    bg.fore_color.rgb = RGBColor(0xF7, 0xF9, 0xFC)
                    bar = new.shapes.add_shape(
                        MSO_SHAPE.RECTANGLE,
                        Inches(0), Inches(0), Inches(0.18), Inches(5.625)
                    )
                    bar.fill.solid()
                    bar.fill.fore_color.rgb = RGBColor(0x0A, 0x2E, 0x5D)
                    bar.line.fill.background()
                    tx = new.shapes.add_textbox(Inches(0.75), Inches(1.55), Inches(8.6), Inches(1.5))
                    tf = tx.text_frame
                    tf.word_wrap = True
                    tf.text = title or "汇报标题"
                    tf.paragraphs[0].font.size = Pt(30)
                    tf.paragraphs[0].font.bold = True
                    tf.paragraphs[0].font.color.rgb = RGBColor(0x10, 0x10, 0x10)
                    sub = new.shapes.add_textbox(Inches(0.78), Inches(3.15), Inches(8.4), Inches(0.55))
                    stf = sub.text_frame
                    stf.text = subtitle or "课题组研究脉络与代表性成果"
                    stf.paragraphs[0].font.size = Pt(16)
                    stf.paragraphs[0].font.color.rgb = RGBColor(0x4B, 0x55, 0x63)
                    foot = new.shapes.add_textbox(Inches(0.78), Inches(4.65), Inches(8.4), Inches(0.35))
                    ftf = foot.text_frame
                    ftf.text = "DAI Lab"
                    ftf.paragraphs[0].font.size = Pt(12)
                    ftf.paragraphs[0].font.color.rgb = RGBColor(0x6B, 0x72, 0x80)
                    return new

                def _inject_notes(slide_obj, slide_idx_in_plan):
                    """Write speaker-notes block into slide.notes_slide."""
                    if slide_obj is None:
                        return
                    try:
                        idx_i = int(slide_idx_in_plan)
                    except Exception:
                        return
                    note_text = notes_by_idx.get(idx_i)
                    if not note_text:
                        return
                    try:
                        slide_obj.notes_slide.notes_text_frame.text = note_text
                    except Exception as exc:
                        print(f"[draft-assembly] notes inject slide {idx_i} skipped: {exc}", flush=True)

                # Phase J: build outline lookup for review annotation
                outline_for_anno = read_json(pdir / "outline.json", {}) or {}
                outline_by_idx: dict[int, dict] = {}
                for o in (outline_for_anno.get("slides") or []):
                    if isinstance(o, dict) and o.get("slide_index") is not None:
                        try:
                            outline_by_idx[int(o["slide_index"])] = o
                        except Exception:
                            pass

                # P20b: load pre-computed annotation summaries from disk.
                # GAP_CARD_GENERATION runs _batch_codex_slide_annotations after
                # gap analysis so by the time DRAFT_ASSEMBLY runs the summaries
                # are ready. We just look them up by slide_index. If the file
                # is missing or empty, _inject_review_annotation falls back to
                # the truncation path automatically.
                annotation_by_idx: dict[int, dict] = {}
                anno_doc = read_json(pdir / "slide-annotations.json", {}) or {}
                for s in (anno_doc.get("summaries") or []):
                    if isinstance(s, dict):
                        try:
                            annotation_by_idx[int(s.get("slide_index"))] = s
                        except (TypeError, ValueError):
                            pass
                if annotation_by_idx:
                    print(f"[draft-assembly] loaded {len(annotation_by_idx)} "
                          f"pre-computed annotation summaries from "
                          f"slide-annotations.json ({anno_doc.get('source')})",
                          flush=True)
                else:
                    print(f"[draft-assembly] no slide-annotations.json or empty; "
                          f"annotations will use truncation fallback",
                          flush=True)

                def _inject_review_annotation(slide_obj, slide_idx_in_plan):
                    """Phase J: top-right红边框批注 (双行: 目标 + Gap).
                    shape.name='REVIEW_ANNOTATION_v1' → 可一键 strip 移除。

                    Direct XML append into spTree — pptx_slide_clone.clone_slide
                    wholesale-replaces the slide's element tree, so python-pptx's
                    cached spTree reference goes stale. Using `slide.shapes.add_textbox`
                    appends to the orphaned old spTree and the textbox is silently
                    lost on save. Bypass python-pptx and build the <p:sp> XML
                    directly against the slide's CURRENT spTree element.
                    """
                    if not inject_review_annotations:
                        return
                    if slide_obj is None:
                        return
                    try:
                        idx_i = int(slide_idx_in_plan)
                    except Exception:
                        return
                    from lxml import etree as _et

                    o = outline_by_idx.get(idx_i, {}) or {}
                    gc = cards_n.get(idx_i, {}) or {}

                    # 优先用 codex 归纳的 annotation summary; 否则 fallback 到截断
                    anno = annotation_by_idx.get(idx_i)
                    if anno and (anno.get("objective") or anno.get("gap_brief")):
                        raw_purpose = (anno.get("objective") or "")[:36].strip()
                        gap = (anno.get("gap_brief") or "已就绪").strip()
                    else:
                        # Fallback: 字数压缩 (codex 不可用时)
                        raw_purpose = (o.get("target_title") or o.get("target_claim")
                                       or o.get("page_purpose") or "")[:36].strip()
                        gap_bits: list[str] = []
                        for k, label in [("must_replace", "改"), ("must_add", "加"),
                                         ("evidence_needed", "证")]:
                            items = gc.get(k) or []
                            if items:
                                joined = "+".join(str(x)[:8] for x in items[:2])[:18]
                                gap_bits.append(f"{label}:{joined}")
                        gap = " · ".join(gap_bits) or "无 gap"

                    try:
                        pres_w = int(target_pres.slide_width or 0)
                        pres_h = int(target_pres.slide_height or 0)
                    except Exception:
                        pres_w = pres_h = 0
                    if pres_w <= 0 or pres_h <= 0:
                        return
                    box_w = int(pres_w * 0.40)
                    box_h = int(pres_h * 0.13)
                    margin = int(pres_w * 0.012)
                    box_x = pres_w - box_w - margin
                    box_y = margin

                    # Locate the slide's CURRENT spTree (after any clone-replace)
                    P = "http://schemas.openxmlformats.org/presentationml/2006/main"
                    A = "http://schemas.openxmlformats.org/drawingml/2006/main"
                    sld = slide_obj.element
                    cSld = sld.find(f"{{{P}}}cSld")
                    if cSld is None:
                        return
                    spTree = cSld.find(f"{{{P}}}spTree")
                    if spTree is None:
                        return
                    # Generate a unique shape id (max existing + 1)
                    max_id = 1
                    for el in spTree.iter(f"{{{P}}}cNvPr"):
                        try:
                            max_id = max(max_id, int(el.get("id") or 0))
                        except Exception:
                            pass
                    new_id = max_id + 1

                    # XML-escape text content
                    def _esc(s: str) -> str:
                        return (s.replace("&","&amp;").replace("<","&lt;")
                                .replace(">","&gt;").replace('"',"&quot;"))

                    line1 = f"🎯 {raw_purpose}"
                    line2 = f"🔧 {gap}"
                    sp_xml = (
                        f'<p:sp xmlns:p="{P}" xmlns:a="{A}">'
                          f'<p:nvSpPr>'
                            f'<p:cNvPr id="{new_id}" name="REVIEW_ANNOTATION_v1"/>'
                            f'<p:cNvSpPr txBox="1"/>'
                            f'<p:nvPr/>'
                          f'</p:nvSpPr>'
                          f'<p:spPr>'
                            f'<a:xfrm>'
                              f'<a:off x="{box_x}" y="{box_y}"/>'
                              f'<a:ext cx="{box_w}" cy="{box_h}"/>'
                            f'</a:xfrm>'
                            f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
                            f'<a:solidFill><a:srgbClr val="FFF59D"/></a:solidFill>'
                            f'<a:ln><a:noFill/></a:ln>'
                          f'</p:spPr>'
                          f'<p:txBody>'
                            f'<a:bodyPr wrap="square" lIns="72000" tIns="36000" '
                                f'rIns="72000" bIns="36000" anchor="t">'
                              f'<a:normAutofit/>'
                            f'</a:bodyPr>'
                            f'<a:lstStyle/>'
                            f'<a:p>'
                              f'<a:r>'
                                f'<a:rPr lang="zh-CN" sz="1000" dirty="0">'
                                  f'<a:latin typeface="Microsoft YaHei"/>'
                                  f'<a:ea typeface="Microsoft YaHei"/>'
                                f'</a:rPr>'
                                f'<a:t>{_esc(line1)}</a:t>'
                              f'</a:r>'
                            f'</a:p>'
                            f'<a:p>'
                              f'<a:r>'
                                f'<a:rPr lang="zh-CN" sz="1000" dirty="0">'
                                  f'<a:latin typeface="Microsoft YaHei"/>'
                                  f'<a:ea typeface="Microsoft YaHei"/>'
                                f'</a:rPr>'
                                f'<a:t>{_esc(line2)}</a:t>'
                              f'</a:r>'
                            f'</a:p>'
                          f'</p:txBody>'
                        f'</p:sp>'
                    )
                    try:
                        spTree.append(_et.fromstring(sp_xml))
                    except Exception as exc:
                        print(f"[anno] slide {idx_i}: spTree append failed: {exc}", flush=True)

                for s in plan_slides:
                    # Phase I: structural-role rows (agenda/section_divider) now
                    # prefer matched source byte-clone — they only fall back to
                    # the synthetic _add_agenda_slide template when SLIDE_MATCHING
                    # couldn't find a library template (no rid OR no source pptx).
                    role = (s.get("target_role") or "").lower()
                    action = (s.get("draft_action") or "").lower()
                    if role in {"cover", "opening"}:
                        new_slide_obj = _add_cover_slide(
                            target_pres,
                            s.get("target_title") or outline_doc_for_agenda.get("topic") or "",
                            s.get("target_claim") or "",
                        )
                        _inject_notes(new_slide_obj, s.get("slide_index"))
                        _inject_review_annotation(new_slide_obj, s.get("slide_index"))
                        continue
                    is_structural_role = role in {"agenda", "section_divider"}
                    has_byte_clone_source = (
                        action == "direct_slide_reuse"
                        and s.get("source_pptx_path")
                        and Path(s.get("source_pptx_path") or "").exists()
                        and s.get("source_slide_index")
                    )
                    if is_structural_role and section_titles_list:
                        titles = s.get("section_titles") or section_titles_list
                        active_idx = s.get("active_section_index")
                        if active_idx is None:
                            try:
                                active_idx = int(s.get("chapter_index") or 0)
                            except Exception:
                                active_idx = 0
                        if role == "agenda":
                            active_idx = 0
                        new_slide_obj = _add_agenda_slide(target_pres, titles, active_idx)
                        _inject_notes(new_slide_obj, s.get("slide_index"))
                        _inject_review_annotation(new_slide_obj, s.get("slide_index"))
                        continue
                    if s.get("draft_action") == "direct_slide_reuse":
                        src_path = s.get("source_pptx_path")
                        if not src_path or not Path(src_path).exists():
                            # Source PPTX missing — render placeholder for this page
                            # rather than abort the whole clone job.
                            placeholder_pages.append(s.get("slide_index"))
                            if len(target_pres.slide_layouts) > 0:
                                layout = target_pres.slide_layouts[0]
                            else:
                                from pptx import Presentation as _P2
                                seed = _P2()
                                layout = seed.slide_layouts[6] if len(seed.slide_layouts) > 6 else seed.slide_layouts[0]
                            new = target_pres.slides.add_slide(layout)
                            from pptx.util import Inches
                            tb = new.shapes.add_textbox(Inches(0.5), Inches(2), Inches(9), Inches(4))
                            tf = tb.text_frame
                            tf.word_wrap = True
                            tf.text = f"⚠ 源 PPTX 缺失: {Path(src_path or '').name}"
                            tf.add_paragraph().text = (s.get("target_title") or "")[:80]
                            _inject_notes(new, s.get("slide_index"))
                            _inject_review_annotation(new, s.get("slide_index"))
                            continue
                        src_pres = pptx_slide_clone._open_source(src_path)
                        try:
                            cloned = pptx_slide_clone.clone_slide(target_pres, src_pres, int(s["source_slide_index"]), state)
                            _inject_notes(cloned, s.get("slide_index"))
                            _inject_review_annotation(cloned, s.get("slide_index"))
                            # v30 fix F: 检测源 slide 是否含"不支持完整 clone"的元素,
                            # 记录到 clone_integrity_warnings. 这些元素 clone 可能表面
                            # 成功但视觉降级 (e.g. OLE 对象/嵌入媒体不带 payload).
                            try:
                                src_slide_obj = list(src_pres.slides)[int(s["source_slide_index"]) - 1]
                                _unsupported = _detect_unsupported_pptx_elements(src_slide_obj)
                                if _unsupported:
                                    clone_integrity_warnings.append({
                                        "slide_index": s.get("slide_index"),
                                        "source_pptx": str(src_path).split("/")[-1],
                                        "source_slide_index": int(s["source_slide_index"]),
                                        "unsupported_elements": _unsupported,
                                    })
                                    print(f"[draft-assembly] slide {s.get('slide_index')} "
                                          f"clone 有降级风险: {_unsupported}", flush=True)
                            except Exception as _iexc:
                                print(f"[draft-assembly] integrity check failed slide "
                                      f"{s.get('slide_index')}: {_iexc}", flush=True)
                        except Exception as exc:
                            placeholder_pages.append(s.get("slide_index"))
                            if len(target_pres.slide_layouts) > 0:
                                layout = target_pres.slide_layouts[0]
                            else:
                                from pptx import Presentation as _P2
                                seed = _P2()
                                layout = seed.slide_layouts[6] if len(seed.slide_layouts) > 6 else seed.slide_layouts[0]
                            new = target_pres.slides.add_slide(layout)
                            from pptx.util import Inches
                            tb = new.shapes.add_textbox(Inches(0.5), Inches(2), Inches(9), Inches(4))
                            tf = tb.text_frame
                            tf.word_wrap = True
                            tf.text = f"⚠ Clone 失败: {exc}"
                            tf.add_paragraph().text = (s.get("target_title") or "")[:80]
                            _inject_notes(new, s.get("slide_index"))
                            _inject_review_annotation(new, s.get("slide_index"))
                    else:
                        # Placeholder / new_slide — render a minimal placeholder
                        # slide using the first available master/layout.
                        if len(target_pres.slide_layouts) == 0:
                            from pptx import Presentation as _P2
                            seed = _P2()
                            layout = seed.slide_layouts[6] if len(seed.slide_layouts) > 6 else seed.slide_layouts[0]
                        else:
                            layout = target_pres.slide_layouts[0]
                        new = target_pres.slides.add_slide(layout)
                        from pptx.util import Inches, Pt
                        title = s.get("target_title") or "本页待补充"
                        plan_note = s.get("plan_note") or ""
                        if new.shapes.title:
                            new.shapes.title.text = title
                        tb = new.shapes.add_textbox(Inches(0.5), Inches(2), Inches(9), Inches(4))
                        tf = tb.text_frame
                        tf.word_wrap = True
                        # v30 fix #7: 区分 no_supporting_material (库无支撑, 需人类
                        # 补充材料或改 outline) vs 普通 placeholder (structural page)
                        _kind = (s.get("source_carrier_resource_kind") or "").lower()
                        _no_mat = bool(s.get("_no_material")) or _kind == "no_supporting_material"
                        if _no_mat:
                            tf.text = "⚠️ 库无支持材料 · 需人类介入"
                            p2 = tf.add_paragraph()
                            p2.text = f"目标 claim: {(s.get('target_claim') or '')[:120]}"
                            p3 = tf.add_paragraph()
                            p3.text = (
                                "库驱动原则要求 outline 与库对齐; 该 slide 未找到 grounding. "
                                "选项: (1) 补充相关素材到库 (2) 改 outline 删除本页 "
                                "(3) 改 target_claim 到库能支撑的方向."
                            )
                            if plan_note:
                                p4 = tf.add_paragraph()
                                p4.text = "上下文: " + plan_note[:200]
                        else:
                            tf.text = "⚠ Gap Page · 本页暂无可直接复用 slide"
                            p2 = tf.add_paragraph()
                            p2.text = (s.get("target_claim") or "")[:120]
                            if plan_note:
                                p3 = tf.add_paragraph()
                                p3.text = "本页待补充: " + plan_note[:300]
                        _inject_notes(new, s.get("slide_index"))
                        _inject_review_annotation(new, s.get("slide_index"))
                target_pres.save(pdir / "draft-deck.pptx")
                clone_ok = (pdir / "draft-deck.pptx").exists()
                render = {"ok": clone_ok, "source": "pptx_slide_clone",
                          "cloned_pages": len(needs_clone) - len(placeholder_pages),
                          "placeholder_pages": len(plan_slides) - len(needs_clone) + len(placeholder_pages),
                          "clone_failures": placeholder_pages,
                          # v30 fix F: 记录含不支持元素的 clone (视觉可能降级)
                          "clone_integrity_warnings": clone_integrity_warnings}
                # v30 fix #10: 落盘 clone_integrity_warnings 供 CODEX_REVIEW 读取
                if clone_integrity_warnings:
                    write_json(pdir / "draft-integrity-warnings.json", {
                        "schema_version": "1.0",
                        "generated_at": now(),
                        "warnings": clone_integrity_warnings,
                    })
        except Exception as exc:
            import traceback
            traceback.print_exc()
            render = {"ok": False, "source": "pptx_slide_clone", "error": str(exc)}
            clone_ok = False

        # ---------- P9: NO silent SVG fallback ----------
        # If clone failed we surface the error explicitly. The legacy SVG
        # path doesn't preserve PowerPoint slide semantics (charts collapse,
        # fonts substitute, embeds drop) — silently switching to it hides the
        # real problem and produces a misleading deck. Caller can manually
        # invoke the legacy path via PPT_DRAFT_REUSE_FALLBACK=1 if needed.
        if not clone_ok:
            if os.environ.get("PPT_DRAFT_REUSE_FALLBACK") == "1":
                os.environ["PPT_DRAFT_REUSE"] = "1"
                render = _run_render(project_id, {"draft": True})
                if (pdir / "deck.pptx").exists():
                    (pdir / "draft-deck.pptx").write_bytes((pdir / "deck.pptx").read_bytes())
                if (pdir / "render-log.md").exists():
                    (pdir / "draft-render-log.md").write_text(
                        (pdir / "render-log.md").read_text(encoding="utf-8", errors="ignore"),
                        encoding="utf-8",
                    )
            else:
                # Leave previous draft-deck.pptx (if any) untouched and report.
                if not isinstance(render, dict):
                    render = {}
                render = {**render, "ok": False,
                          "error": render.get("error") or "pptx_slide_clone failed; no SVG fallback (set PPT_DRAFT_REUSE_FALLBACK=1 to force)"}
    finally:
        if prev_draft_env is None:
            os.environ.pop("PPT_DRAFT_REUSE", None)
        else:
            os.environ["PPT_DRAFT_REUSE"] = prev_draft_env
        _restore_snapshot(pdir, snapshots)
    return {
        "ok": (pdir / "draft-deck.pptx").exists(),
        "draft_assembly_plan": str(pdir / "draft-assembly-plan.json"),
        "draft_deck": str(pdir / "draft-deck.pptx"),
        "from_upstream_plan": has_upstream_plan,
        "render": render,
    }


def _run_draft_quality_score(project_id: str) -> dict:
    """Codex final reviewer: 多维评分 draft deck.

    Reads brief + outline + slide-matches + slide-plan + draft-assembly-plan +
    real speaker-notes samples from draft-deck.pptx. Codex outputs scores
    across 5 dimensions + critical issues + improvement priorities.

    See skills/review/draft_quality_score.md for the scoring rubric.
    """
    from . import codex_cli
    pdir = project_dir(project_id)

    brief = read_json(pdir / "idea-analysis.json", {}) or {}
    outline = read_json(pdir / "outline.json", {}) or {}
    slide_matches = read_json(pdir / "slide-matches.json", {}) or {}
    slide_plan = read_json(pdir / "slide-plan.json", {}) or {}
    assembly_plan = read_json(pdir / "draft-assembly-plan.json", {}) or {}

    # Compact: trim big arrays before sending to codex
    def _compact_brief(b: dict) -> dict:
        return {k: b.get(k) for k in (
            "topic", "language", "slide_count", "audience", "scenario",
            "deck_type", "core_message", "message_architecture",
            "narrative_blueprint", "expected_sections",
            "chapter_page_archetype_plan", "must_have_pages",
            "anchor_terms", "topic_tags", "reuse_strategy",
            "referenced_templates"
        ) if b.get(k) is not None}

    def _compact_outline(o: dict) -> dict:
        slides = o.get("slides") or []
        return {
            "slide_count": o.get("slide_count"),
            "section_breakdown": o.get("section_breakdown"),
            "slides": [
                {
                    "slide_index": s.get("slide_index"),
                    "target_role": s.get("target_role"),
                    "target_title": s.get("target_title"),
                    "target_claim": s.get("target_claim"),
                    "key_points": (s.get("key_points") or [])[:3],
                    "section_index": s.get("section_index"),
                    "expected_resource_kind": s.get("expected_resource_kind"),
                }
                for s in slides if isinstance(s, dict)
            ],
        }

    def _compact_slide_matches(sm: dict) -> dict:
        matches = sm.get("slide_matches") or []
        return {
            "schema_version": sm.get("schema_version"),
            "source": sm.get("source"),
            "match_count": len(matches),
            "match_per_target": [
                {
                    "target_slide_index": m.get("target_slide_index"),
                    "target_role": m.get("target_role"),
                    "candidate_count": len(m.get("candidates") or []),
                    "rank1_score": ((m.get("candidates") or [{}])[0] or {}).get("score"),
                    "rank1_match_reason": ((m.get("candidates") or [{}])[0] or {}).get("match_reason"),
                    "rank1_deck": ((m.get("candidates") or [{}])[0] or {}).get("deck_id"),
                }
                for m in matches if isinstance(m, dict)
            ][:80],
        }

    def _compact_assembly_plan(a: dict) -> dict:
        return {
            "slide_count": a.get("slide_count"),
            "by_action": a.get("by_action"),
            "by_fit": a.get("by_fit"),
        }

    # Extract real speaker notes from draft-deck.pptx
    notes_samples: list[dict] = []
    summary = {}
    try:
        from pptx import Presentation
        pres = Presentation(str(pdir / "draft-deck.pptx"))
        slides_obj = list(pres.slides)
        total_pages = len(slides_obj)
        notes_lens = []
        n_alt = 0
        for i, s in enumerate(slides_obj):
            if not s.has_notes_slide:
                continue
            txt = s.notes_slide.notes_text_frame.text or ""
            notes_lens.append(len(txt))
            if "【备选候选" in txt:
                n_alt += 1
        # Sample 6 pages: 1, near 25%, 50%, 75%, end, plus a random middle page
        n = total_pages
        if n > 0:
            sample_indices = sorted(set([
                0,
                max(0, n // 4),
                max(0, n // 2),
                max(0, (3 * n) // 4),
                n - 1,
                max(0, n // 2 + 3),
            ]))
            for idx in sample_indices:
                if 0 <= idx < n and slides_obj[idx].has_notes_slide:
                    notes_samples.append({
                        "slide_index": idx + 1,
                        "notes_text": slides_obj[idx].notes_slide.notes_text_frame.text,
                    })
        summary = {
            "total_pages": total_pages,
            "direct_slide_reuse_count": int((assembly_plan.get("by_action") or {}).get("direct_slide_reuse") or 0),
            "placeholder_count": int((assembly_plan.get("by_action") or {}).get("new_slide_placeholder") or 0),
            "notes_with_alternates_count": n_alt,
            "average_notes_length": int(sum(notes_lens) / max(1, len(notes_lens))) if notes_lens else 0,
        }
    except Exception as exc:
        print(f"[DRAFT_QUALITY_SCORE] pptx read failed: {exc}", flush=True)
        summary = {"error": f"pptx read failed: {exc}"}

    review_input = {
        "idea_analysis": _compact_brief(brief),
        "outline": _compact_outline(outline),
        "slide_matches": _compact_slide_matches(slide_matches),
        "draft_assembly_plan": _compact_assembly_plan(assembly_plan),
        "draft_deck_summary": summary,
        "speaker_notes_samples": notes_samples,
    }
    prompt = (
        "Score the draft deck across 5 dimensions per the skill rubric.\n"
        "Output JSON only.\n\nINPUT:\n" + json.dumps(review_input, ensure_ascii=False)
    )
    out = codex_cli.call_codex_json(
        prompt,
        skill=["skills/review/draft_quality_score.md"],
        timeout=600,
    )
    if not out.get("ok"):
        print(f"[DRAFT_QUALITY_SCORE] codex failed: {(out.get('error') or '')[:200]}", flush=True)
        data = {
            "schema_version": "1.0",
            "generated_at": now(),
            "source": "codex_failed",
            "error": out.get("error"),
        }
        write_json(pdir / "draft-quality-score.json", data)
        return {"ok": False, "stage": "DRAFT_QUALITY_SCORE", "error": out.get("error")}

    data = out["data"] or {}
    data["schema_version"] = data.get("schema_version") or "1.0"
    data["generated_at"] = now()
    data["source"] = "codex"
    write_json(pdir / "draft-quality-score.json", data)

    scores = data.get("scores") or {}
    print(f"[DRAFT_QUALITY_SCORE] overall={scores.get('overall')}, "
          f"brief_align={scores.get('brief_alignment')}, "
          f"struct={scores.get('structural_quality')}, "
          f"reuse={scores.get('reuse_quality')}, "
          f"notes={scores.get('notes_quality')}, "
          f"usability={scores.get('usability')}", flush=True)
    return {
        "ok": True,
        "stage": "DRAFT_QUALITY_SCORE",
        "draft_quality_score": str(pdir / "draft-quality-score.json"),
        "scores": scores,
        "critical_issues_count": len(data.get("critical_issues") or []),
        "estimated_user_effort_hours": data.get("estimated_user_effort_hours"),
        "summary": data.get("summary"),
    }


def _run_character_revision(project_id: str) -> dict:
    """CHARACTER_REVISION — apply gap-card unification/edit hints to draft-deck.pptx.

    Runs between DRAFT_ASSEMBLY (byte-clone) and DRAFT_REVIEW (human/model review).

    Per slide:
      1. extract editable elements via character_revision.extract_elements()
      2. build gap instruction (unification_hints + must_replace/remove/add)
      3. Claude call → JSON action list
      4. apply_actions() with python-pptx
      5. on failure, retry up to 3 times with error feedback

    Outputs:
      - projects/<id>/revised-draft-deck.pptx
      - projects/<id>/character-revision-audit.json
    """
    import concurrent.futures as _cf_cr
    import os as _os_cr
    from copy import deepcopy
    from . import character_revision as cr, claude_cli
    from pptx import Presentation

    pdir = project_dir(project_id)
    draft_pptx = pdir / "draft-deck.pptx"
    if not draft_pptx.exists():
        return {"ok": False, "stage": "CHARACTER_REVISION",
                "error": "draft-deck.pptx missing — run DRAFT_ASSEMBLY first"}

    gap_doc = read_json(pdir / "gap-cards.json", {}) or {}
    gap_cards = gap_doc.get("gap_cards") or []
    if not gap_cards:
        return {"ok": False, "stage": "CHARACTER_REVISION",
                "error": "gap-cards.json empty — run GAP_CARD_GENERATION first"}

    checkpoint_pptx = pdir / "revised-draft-deck.checkpoint.pptx"
    checkpoint_audit = pdir / "character-revision-audit.checkpoint.json"
    input_pptx = checkpoint_pptx if checkpoint_pptx.exists() else draft_pptx

    def _int_env(name: str, default: int, *, lo: int, hi: int) -> int:
        try:
            value = int(_os_cr.environ.get(name, "") or default)
        except Exception:
            value = default
        return max(lo, min(hi, value))

    character_revision_timeout = _int_env("CHARACTER_REVISION_TIMEOUT", 480, lo=120, hi=1800)
    character_revision_max_retries = _int_env("CHARACTER_REVISION_MAX_RETRIES", 3, lo=1, hi=5)

    # Load pptx once, index by slide_index (1-based to match gap_card.slide_index)
    prs = Presentation(str(input_pptx))
    n_slides = len(prs.slides)
    print(f"[CHARACTER_REVISION] input={input_pptx.name}, slides={n_slides}, "
          f"gap_cards={len(gap_cards)}, timeout={character_revision_timeout}s, "
          f"max_retries={character_revision_max_retries}",
          flush=True)

    # Build gap_card lookup by slide_index (1-based)
    gap_by_idx = {}
    for g in gap_cards:
        if isinstance(g, dict) and g.get("slide_index") is not None:
            try:
                gap_by_idx[int(g["slide_index"])] = g
            except (TypeError, ValueError):
                pass

    skill_paths = ["skills/character_revision/apply_edits.md"]

    # ─────────────────────────────────────────────────────────────
    # v2 (2026-07-29) P2: agenda-page pre-pass.
    # Scan outline to identify agenda/toc/chapter_divider slides, vote a unified
    # chapter list, then attach an `agenda_directive` to each such slide's
    # base_input so Claude uses the same chapter names + only differs on which
    # chapter is highlighted (per chapter_index).
    # ─────────────────────────────────────────────────────────────
    outline_doc = read_json(pdir / "outline.json", {}) or {}
    outline_slides = outline_doc.get("slides") or []
    _AGENDA_ROLES = {"agenda", "toc", "chapter_divider", "section_divider"}
    # Slides that are agenda-like (1-based idx → outline slide dict)
    agenda_slides_by_idx: dict[int, dict] = {}
    for s in outline_slides:
        if not isinstance(s, dict):
            continue
        role = str(s.get("target_role") or "").lower()
        if role in _AGENDA_ROLES:
            try:
                agenda_slides_by_idx[int(s.get("slide_index"))] = s
            except (TypeError, ValueError):
                pass

    unified_chapter_names: list[str] = []
    section_breakdown = outline_doc.get("section_breakdown") or []
    if isinstance(section_breakdown, list) and section_breakdown:
        for sec in section_breakdown:
            if not isinstance(sec, dict):
                continue
            name = (sec.get("chapter") or sec.get("title")
                    or sec.get("section_title") or "").strip()
            if name:
                unified_chapter_names.append(name)
    else:
        # Fallback: derive from chapter_index → first chapter_divider title
        by_ch: dict[int, str] = {}
        for s in outline_slides:
            if not isinstance(s, dict):
                continue
            role = str(s.get("target_role") or "").lower()
            if role in {"chapter_divider", "section_divider"}:
                try:
                    ci = int(s.get("chapter_index"))
                except (TypeError, ValueError):
                    continue
                t = s.get("target_title") or ""
                if t and ci not in by_ch:
                    by_ch[ci] = t.strip()
        unified_chapter_names = [by_ch[ci] for ci in sorted(by_ch)]

    def _agenda_directive_for(slide_idx_1based: int) -> dict | None:
        """Build the agenda_directive for one agenda slide, or None if not agenda."""
        if slide_idx_1based not in agenda_slides_by_idx:
            return None
        s = agenda_slides_by_idx[slide_idx_1based]
        if not unified_chapter_names:
            return None
        try:
            current_ch = int(s.get("chapter_index") or 0)
        except (TypeError, ValueError):
            current_ch = 0
        # Slide 1 is often the primary TOC → highlight nothing (all black)
        # otherwise highlight the chapter this slide belongs to
        role = str(s.get("target_role") or "").lower()
        if role in {"agenda", "toc"} and current_ch <= 1:
            highlight_index = None
        else:
            highlight_index = current_ch if current_ch >= 1 else None

        return {
            "role": role,
            "shared_chapter_list": unified_chapter_names,
            "highlight_chapter_index": highlight_index,  # 1-based; None = full TOC (all black)
            "colors": {
                "highlight": "000000",   # current chapter → black
                "muted": "FFFFFF",       # other chapters → white
            },
            "instruction": (
                "This is an agenda/chapter_divider slide. All such slides MUST share "
                "the same chapter list (shared_chapter_list, in order, verbatim). "
                "For each chapter paragraph, emit BOTH a replace_text (to set the "
                "chapter name) AND a recolor_text (to set the color): "
                "when highlight_chapter_index is null, every chapter uses "
                "colors.highlight (main TOC = all black); "
                "when it's a number N, chapter N uses colors.highlight and all "
                "others use colors.muted. Do NOT invent chapters, do NOT skip any, "
                "do NOT change wording."
            ),
        }

    if agenda_slides_by_idx:
        print(f"[CHARACTER_REVISION] agenda pre-pass: "
              f"{len(agenda_slides_by_idx)} agenda/divider slides, "
              f"unified {len(unified_chapter_names)} chapters", flush=True)

    # ─────────────────────────────────────────────────────────────
    # v2 (2026-07-29) P3: vision grounding.
    # Load draft-source-lineage to map slide_index → source PNG path.
    # If PNG exists, pass it to Claude via add_dirs so it can Read + see the
    # actual visual layout. Reduces layout errors (title overflow, image misplacement).
    # ─────────────────────────────────────────────────────────────
    lineage_doc = read_json(pdir / "draft-source-lineage.json", {}) or {}
    lineage_entries = lineage_doc.get("entries") or lineage_doc.get("lineage_entries") or []
    slide_to_png: dict[int, Path] = {}
    imports_root = ROOT / "data" / "resources_library" / "material" / "imports"
    import re as _re_png
    _PNG_RE = _re_png.compile(r"^(tpl\.[^.]+\.[^.]+\.[a-f0-9]{6,10})\.slide_(\d+)$")
    for e in lineage_entries:
        if not isinstance(e, dict):
            continue
        try:
            idx = int(e.get("slide_index"))
        except (TypeError, ValueError):
            continue
        rid = str(e.get("source_resource_id") or "")
        m = _PNG_RE.match(rid)
        if not m:
            continue
        deck_id, slide_num = m.group(1), int(m.group(2))
        png = imports_root / deck_id / "pngs" / f"slide_{slide_num:02d}.png"
        if png.exists():
            slide_to_png[idx] = png
    print(f"[CHARACTER_REVISION] vision grounding: "
          f"{len(slide_to_png)}/{n_slides} slides have source PNG",
          flush=True)

    # ─────────────────────────────────────────────────────────────
    # v6 (2026-07-29): source slide brief lookup for image-text consistency.
    # Load the material library's per-slide brief (含 视觉骨架 / 视觉文本层次 /
    # 关键文字 / 适合与不适合复用场景) for each byte-cloned source. Claude uses
    # this to decide whether to rewrite text or preserve it based on whether
    # the new content matches the source's visual structure.
    # ─────────────────────────────────────────────────────────────
    slide_to_source_brief: dict[int, dict] = {}
    material_decks_root = ROOT / "data" / "resources_library" / "material" / "decks"

    # Build deck_id → deck directory name lookup once
    deck_id_to_dir: dict[str, str] = {}
    idx_file = ROOT / "data" / "resources_library" / "material" / "decks-index.json"
    if idx_file.exists():
        try:
            idx_doc = read_json(idx_file, {})
            for d in idx_doc.get("decks") or []:
                did = d.get("deck标识")
                dname = d.get("目录名")
                if did and dname:
                    deck_id_to_dir[did] = dname
        except Exception:
            pass

    _BRIEF_VISUAL_KEYS = ("本页讲什么", "视觉骨架", "视觉文本层次", "关键文字",
                          "适合复用场景", "不适合复用场景", "layout_tag", "页面角色",
                          "页在section中的作用")

    for e in lineage_entries:
        if not isinstance(e, dict):
            continue
        try:
            idx = int(e.get("slide_index"))
        except (TypeError, ValueError):
            continue
        rid = str(e.get("source_resource_id") or "")
        m = _PNG_RE.match(rid)
        if not m:
            continue
        deck_id, slide_num = m.group(1), int(m.group(2))
        deck_dir_name = deck_id_to_dir.get(deck_id)
        if not deck_dir_name:
            continue
        deck_dir = material_decks_root / deck_dir_name
        if not deck_dir.exists():
            continue
        # Find slide_NN.json (naming: slide_NN.json where NN is 0-padded)
        found = None
        for section_dir in deck_dir.iterdir():
            if not section_dir.is_dir() or not section_dir.name.startswith("section_"):
                continue
            for slide_json in section_dir.glob(f"slide_{slide_num:02d}.json"):
                if slide_json.exists():
                    found = slide_json
                    break
            if found: break
            # Also try un-padded form
            for slide_json in section_dir.glob(f"slide_{slide_num}.json"):
                if slide_json.exists():
                    found = slide_json
                    break
            if found: break
        if not found:
            continue
        try:
            brief = read_json(found, {})
            slide_to_source_brief[idx] = {k: brief.get(k) for k in _BRIEF_VISUAL_KEYS if brief.get(k) is not None}
        except Exception:
            pass

    print(f"[CHARACTER_REVISION] source brief grounding: "
          f"{len(slide_to_source_brief)}/{n_slides} slides have source brief",
          flush=True)

    def _gap_has_edits(g: dict) -> bool:
        return bool(
            (g.get("unification_hints") or [])
            or (g.get("must_replace") or [])
            or (g.get("must_remove") or [])
            or (g.get("must_add") or [])
        )

    def _revise_one_slide(slide_idx_1based: int) -> dict:
        """Revise one slide (1-based idx). Returns audit entry."""
        slide = prs.slides[slide_idx_1based - 1]
        gap = gap_by_idx.get(slide_idx_1based, {})
        if not _gap_has_edits(gap):
            return {"slide_index": slide_idx_1based, "status": "skipped_no_edits",
                    "succeeded": [], "failed": []}

        elements = cr.extract_elements(slide)
        if not elements:
            return {"slide_index": slide_idx_1based, "status": "skipped_no_elements",
                    "succeeded": [], "failed": []}

        # Build Claude input
        base_input = {
            "slide_index": slide_idx_1based,
            "elements": elements,
            "gap_card": {
                "slide_index": gap.get("slide_index"),
                "target_title": gap.get("target_title") or "",
                "target_claim": gap.get("target_claim") or "",
                "unification_hints": gap.get("unification_hints") or [],
                "must_replace": gap.get("must_replace") or [],
                "must_remove": gap.get("must_remove") or [],
                "must_add": gap.get("must_add") or [],
            },
        }
        # v2 (2026-07-29): agenda directive from pre-pass
        agenda_dir = _agenda_directive_for(slide_idx_1based)
        if agenda_dir:
            base_input["agenda_directive"] = agenda_dir
        # v6 (2026-07-29): source slide brief for image-text consistency
        _src_brief = slide_to_source_brief.get(slide_idx_1based)
        if _src_brief:
            base_input["source_slide_brief"] = _src_brief

        MAX_RETRIES = character_revision_max_retries
        all_succeeded = []
        all_failed_final = []
        prior_error = None
        for attempt in range(1, MAX_RETRIES + 1):
            _png_path_prompt = slide_to_png.get(slide_idx_1based)
            _vision_note = ""
            if _png_path_prompt:
                _vision_note = (
                    f"\n\n**VISION GROUNDING**: Read the source slide PNG at "
                    f"`{_png_path_prompt}` first (use the Read tool). It shows the "
                    "actual layout of this slide as byte-cloned from the source. "
                    "Use it to sanity-check your actions: don't extend titles that "
                    "would overflow the visible frame, don't add bullets where "
                    "there's no vertical space, and match the visual role of each "
                    "element (title vs body vs yellow annotation box) to what you "
                    "see on the image.\n"
                )
            prompt_parts = [
                f"Slide {slide_idx_1based} of {n_slides}. Produce JSON action list "
                "per the skill schema. Output strict JSON only." + _vision_note + "\n"
            ]
            if prior_error:
                prompt_parts.append(
                    f"Prior attempt {attempt-1}/{MAX_RETRIES} failed: {prior_error}\n"
                    "Only fix the failing actions; keep the successful ones (they're "
                    "already applied). Retry.\n"
                )
            prompt_parts.append("INPUT:\n" + json.dumps(base_input, ensure_ascii=False))
            prompt = "".join(prompt_parts)

            _png_path = slide_to_png.get(slide_idx_1based)
            _add_dirs = [str(_png_path.parent)] if _png_path else None
            outcome = claude_cli.call_claude_json(
                prompt, skill=skill_paths, timeout=character_revision_timeout,
                add_dirs=_add_dirs,
            )
            if not (outcome.get("ok") and isinstance(outcome.get("data"), dict)):
                prior_error = f"Claude call failed: {(outcome.get('error') or '')[:200]}"
                if attempt >= MAX_RETRIES:
                    all_failed_final.append({"attempt": attempt, "error": prior_error})
                    break
                continue

            actions = outcome["data"].get("actions") or []
            if not isinstance(actions, list):
                prior_error = f"actions is not a list, got {type(actions).__name__}"
                if attempt >= MAX_RETRIES:
                    all_failed_final.append({"attempt": attempt, "error": prior_error})
                    break
                continue

            succeeded, failed = cr.apply_actions(slide, actions)
            all_succeeded.extend(succeeded)

            if not failed:
                return {"slide_index": slide_idx_1based, "status": "ok",
                        "attempts": attempt, "succeeded": all_succeeded, "failed": [],
                        "rationale": (outcome["data"].get("rationale") or "")[:200]}

            # Some actions failed — retry with feedback
            prior_error = "; ".join(
                f"[action={f.get('action')}] {f.get('error')}"
                for f in failed[:3]
            )
            if attempt >= MAX_RETRIES:
                all_failed_final.extend(failed)

        return {"slide_index": slide_idx_1based,
                "status": "ok_partial" if all_succeeded else "failed",
                "attempts": MAX_RETRIES,
                "succeeded": all_succeeded,
                "failed": all_failed_final}

    def _plan_actions_for_slide(slide_idx_1based: int, elements: list[dict]) -> dict:
        """Claude-only part of character revision; safe to run in parallel."""
        gap = gap_by_idx.get(slide_idx_1based, {})
        if not _gap_has_edits(gap):
            return {"slide_index": slide_idx_1based, "status": "skipped_no_edits",
                    "actions": [], "failed": []}
        if not elements:
            return {"slide_index": slide_idx_1based, "status": "skipped_no_elements",
                    "actions": [], "failed": []}

        base_input = {
            "slide_index": slide_idx_1based,
            "elements": elements,
            "gap_card": {
                "slide_index": gap.get("slide_index"),
                "target_title": gap.get("target_title") or "",
                "target_claim": gap.get("target_claim") or "",
                "unification_hints": gap.get("unification_hints") or [],
                "must_replace": gap.get("must_replace") or [],
                "must_remove": gap.get("must_remove") or [],
                "must_add": gap.get("must_add") or [],
            },
        }
        agenda_dir = _agenda_directive_for(slide_idx_1based)
        if agenda_dir:
            base_input["agenda_directive"] = agenda_dir
        _src_brief = slide_to_source_brief.get(slide_idx_1based)
        if _src_brief:
            base_input["source_slide_brief"] = _src_brief

        prior_error = None
        for attempt in range(1, character_revision_max_retries + 1):
            _png_path_prompt = slide_to_png.get(slide_idx_1based)
            _vision_note = ""
            if _png_path_prompt:
                _vision_note = (
                    f"\n\n**VISION GROUNDING**: Read the source slide PNG at "
                    f"`{_png_path_prompt}` first (use the Read tool). It shows the "
                    "actual layout of this slide as byte-cloned from the source. "
                    "Use it to sanity-check your actions: don't extend titles that "
                    "would overflow the visible frame, don't add bullets where "
                    "there's no vertical space, and match the visual role of each "
                    "element (title vs body vs yellow annotation box) to what you "
                    "see on the image.\n"
                )
            prompt_parts = [
                f"Slide {slide_idx_1based} of {n_slides}. Produce JSON action list "
                "per the skill schema. Output strict JSON only." + _vision_note + "\n"
            ]
            if prior_error:
                prompt_parts.append(
                    f"Prior attempt {attempt-1}/{character_revision_max_retries} "
                    f"failed: {prior_error}\nRetry with a valid JSON action list.\n"
                )
            prompt_parts.append("INPUT:\n" + json.dumps(base_input, ensure_ascii=False))
            _png_path = slide_to_png.get(slide_idx_1based)
            _add_dirs = [str(_png_path.parent)] if _png_path else None
            outcome = claude_cli.call_claude_json(
                "".join(prompt_parts),
                skill=skill_paths,
                timeout=character_revision_timeout,
                add_dirs=_add_dirs,
            )
            if not (outcome.get("ok") and isinstance(outcome.get("data"), dict)):
                prior_error = f"Claude call failed: {(outcome.get('error') or '')[:200]}"
                continue
            actions = outcome["data"].get("actions") or []
            if not isinstance(actions, list):
                prior_error = f"actions is not a list, got {type(actions).__name__}"
                continue
            return {
                "slide_index": slide_idx_1based,
                "status": "planned",
                "attempts": attempt,
                "actions": actions,
                "rationale": (outcome["data"].get("rationale") or "")[:200],
                "failed": [],
            }
        return {
            "slide_index": slide_idx_1based,
            "status": "failed",
            "attempts": character_revision_max_retries,
            "actions": [],
            "failed": [{"error": prior_error or "Claude action planning failed"}],
        }

    # Serial execution: we share a single Presentation object, so avoid races.
    # (Cost is fine: ~15-30s per slide × 50 slides = 12-25 min. Can parallelize
    # later by loading separate Presentation() copies per worker if needed.)
    def _audit_summary(entries: list[dict]) -> dict:
        return {
            "slide_count": n_slides,
            "processed": len(entries),
            "ok": sum(1 for e in entries if e.get("status") == "ok"),
            "ok_partial": sum(1 for e in entries if e.get("status") == "ok_partial"),
            "failed": sum(1 for e in entries if e.get("status") == "failed"),
            "skipped": sum(1 for e in entries if str(e.get("status", "")).startswith("skipped")),
            "total_actions_succeeded": sum(len(e.get("succeeded") or []) for e in entries),
            "total_actions_failed": sum(len(e.get("failed") or []) for e in entries),
        }

    audit_entries: list[dict] = []
    resume_from = 1
    if checkpoint_pptx.exists() and checkpoint_audit.exists():
        ck = read_json(checkpoint_audit, {}) or {}
        prior_entries = ck.get("entries") if isinstance(ck.get("entries"), list) else []
        audit_entries = [e for e in prior_entries if isinstance(e, dict)]
        completed = []
        for e in audit_entries:
            try:
                completed.append(int(e.get("slide_index")))
            except Exception:
                pass
        if completed:
            resume_from = max(completed) + 1
            print(f"[CHARACTER_REVISION] resume checkpoint: "
                  f"{checkpoint_pptx.name}, completed={len(completed)}, "
                  f"next_slide={resume_from}", flush=True)

    manual_start = _int_env("CHARACTER_REVISION_START_SLIDE", 0, lo=0, hi=max(0, n_slides))
    if manual_start:
        if not checkpoint_pptx.exists():
            print("[CHARACTER_REVISION] WARNING: CHARACTER_REVISION_START_SLIDE set "
                  "but no checkpoint pptx exists; earlier slides will be raw draft.",
                  flush=True)
        resume_from = max(resume_from, manual_start)

    parallel_workers = _int_env("CHARACTER_REVISION_PARALLEL", 4, lo=1, hi=8)
    if parallel_workers <= 1:
        for idx in range(resume_from, n_slides + 1):
            entry = _revise_one_slide(idx)
            audit_entries.append(entry)
            status = entry.get("status", "?")
            n_s = len(entry.get("succeeded") or [])
            n_f = len(entry.get("failed") or [])
            print(f"[CHARACTER_REVISION] slide {idx}/{n_slides}: {status} "
                  f"(+{n_s}/-{n_f})", flush=True)
            prs.save(str(checkpoint_pptx))
            write_json(checkpoint_audit, {
                "schema_version": "1.0",
                "generated_at": now(),
                "project_id": project_id,
                "source": "claude+python_pptx_checkpoint",
                "input_pptx": str(input_pptx),
                "output_pptx": str(checkpoint_pptx),
                "summary": _audit_summary(audit_entries),
                "entries": audit_entries,
            })
    else:
        pending_indices = list(range(resume_from, n_slides + 1))
        elements_by_idx: dict[int, list[dict]] = {}
        preplanned: dict[int, dict] = {}
        for idx in pending_indices:
            gap = gap_by_idx.get(idx, {})
            if not _gap_has_edits(gap):
                preplanned[idx] = {"slide_index": idx, "status": "skipped_no_edits",
                                   "actions": [], "failed": []}
                continue
            elements = cr.extract_elements(prs.slides[idx - 1])
            elements_by_idx[idx] = elements
            if not elements:
                preplanned[idx] = {"slide_index": idx, "status": "skipped_no_elements",
                                   "actions": [], "failed": []}
        print(f"[CHARACTER_REVISION] parallel Claude planning: "
              f"workers={parallel_workers}, slides={len(pending_indices)}, "
              f"model_calls={len(elements_by_idx)}", flush=True)
        planned_by_idx: dict[int, dict] = dict(preplanned)
        with _cf_cr.ThreadPoolExecutor(max_workers=parallel_workers,
                                       thread_name_prefix="charrev") as pool:
            futs = {
                pool.submit(_plan_actions_for_slide, idx, elements): idx
                for idx, elements in elements_by_idx.items()
            }
            for fut in _cf_cr.as_completed(futs):
                idx = futs[fut]
                try:
                    planned_by_idx[idx] = fut.result()
                except Exception as exc:
                    planned_by_idx[idx] = {
                        "slide_index": idx,
                        "status": "failed",
                        "actions": [],
                        "failed": [{"error": f"planner exception: {exc}"}],
                    }
                st = planned_by_idx[idx].get("status")
                print(f"[CHARACTER_REVISION] slide {idx}/{n_slides}: "
                      f"planned {st}", flush=True)

        for idx in pending_indices:
            plan = planned_by_idx.get(idx) or {
                "slide_index": idx, "status": "failed", "actions": [],
                "failed": [{"error": "missing planned actions"}],
            }
            if str(plan.get("status", "")).startswith("skipped"):
                entry = {
                    "slide_index": idx,
                    "status": plan.get("status"),
                    "attempts": plan.get("attempts"),
                    "succeeded": [],
                    "failed": plan.get("failed") or [],
                }
            elif plan.get("status") == "planned":
                succeeded, failed = cr.apply_actions(prs.slides[idx - 1], plan.get("actions") or [])
                entry = {
                    "slide_index": idx,
                    "status": "ok" if not failed else ("ok_partial" if succeeded else "failed"),
                    "attempts": plan.get("attempts"),
                    "succeeded": succeeded,
                    "failed": failed,
                    "rationale": plan.get("rationale"),
                }
            else:
                entry = {
                    "slide_index": idx,
                    "status": "failed",
                    "attempts": plan.get("attempts"),
                    "succeeded": [],
                    "failed": plan.get("failed") or [],
                }
            audit_entries.append(entry)
            status = entry.get("status", "?")
            n_s = len(entry.get("succeeded") or [])
            n_f = len(entry.get("failed") or [])
            print(f"[CHARACTER_REVISION] slide {idx}/{n_slides}: {status} "
                  f"(+{n_s}/-{n_f})", flush=True)
            prs.save(str(checkpoint_pptx))
            write_json(checkpoint_audit, {
                "schema_version": "1.0",
                "generated_at": now(),
                "project_id": project_id,
                "source": "claude_parallel+python_pptx_checkpoint",
                "input_pptx": str(input_pptx),
                "output_pptx": str(checkpoint_pptx),
                "summary": _audit_summary(audit_entries),
                "entries": audit_entries,
            })

    # Save revised deck
    revised_path = pdir / "revised-draft-deck.pptx"
    prs.save(str(revised_path))

    summary = _audit_summary(audit_entries)

    audit_doc = {
        "schema_version": "1.0",
        "generated_at": now(),
        "project_id": project_id,
        "source": "claude+python_pptx",
        "input_pptx": str(draft_pptx),
        "output_pptx": str(revised_path),
        "summary": summary,
        "entries": audit_entries,
    }
    write_json(pdir / "character-revision-audit.json", audit_doc)

    print(f"[CHARACTER_REVISION] done: ok={summary['ok']}, "
          f"partial={summary['ok_partial']}, failed={summary['failed']}, "
          f"skipped={summary['skipped']}, actions ok/failed="
          f"{summary['total_actions_succeeded']}/{summary['total_actions_failed']}",
          flush=True)

    return {
        "ok": summary["failed"] == 0,
        "stage": "CHARACTER_REVISION",
        "revised_pptx": str(revised_path),
        "audit": str(pdir / "character-revision-audit.json"),
        "summary": audit_doc["summary"],
    }



def _run_visual_unification(project_id: str) -> dict:
    """VISUAL_UNIFICATION — normalize fonts/sizes/colors by voting on draft's own
    dominant style. Pure Python (no Claude). Runs between CHARACTER_REVISION and
    TEMPLATE_UNIFICATION (or DRAFT_REVIEW).

    Input : revised-draft-deck.pptx  (from CHARACTER_REVISION)
            (falls back to draft-deck.pptx if revised not found)
    Output: unified-draft-deck.pptx
            visual-profile.json     (the voted profile, human-editable)
            visual-unification-audit.json
    """
    from . import visual_unification as vu

    pdir = project_dir(project_id)
    input_pptx = pdir / "revised-draft-deck.pptx"
    if not input_pptx.exists():
        fallback = pdir / "draft-deck.pptx"
        if not fallback.exists():
            return {"ok": False, "stage": "VISUAL_UNIFICATION",
                    "error": "neither revised-draft-deck.pptx nor draft-deck.pptx found"}
        input_pptx = fallback
        print(f"[VISUAL_UNIFICATION] using {input_pptx.name} (revised not present)",
              flush=True)

    try:
        profile = vu.extract_style_profile(input_pptx)
    except Exception as exc:
        return {"ok": False, "stage": "VISUAL_UNIFICATION",
                "error": f"profile extraction failed: {exc}"}

    write_json(pdir / "visual-profile.json", profile)
    print(f"[VISUAL_UNIFICATION] voted profile: font_latin={profile['primary_font_latin']}, "
          f"font_ea={profile['primary_font_east_asian']}, "
          f"palette={profile['palette']}, "
          f"tiers={profile['size_tiers']}", flush=True)

    out_pptx = pdir / "unified-draft-deck.pptx"
    try:
        # v2 (2026-07-29): default conservative — only color normalization on.
        # Font/size changes broke title designs on v26; opt-in via env vars.
        import os as _os_vu
        _apply_font = _os_vu.environ.get("VISUAL_APPLY_FONT", "0").lower() in {"1", "true", "yes"}
        _apply_size = _os_vu.environ.get("VISUAL_APPLY_SIZE", "0").lower() in {"1", "true", "yes"}
        _apply_color = _os_vu.environ.get("VISUAL_APPLY_COLOR", "1").lower() in {"1", "true", "yes"}
        audit = vu.apply_profile(input_pptx, profile, out_pptx,
                                   apply_font=_apply_font,
                                   apply_size=_apply_size,
                                   apply_color=_apply_color)
    except Exception as exc:
        return {"ok": False, "stage": "VISUAL_UNIFICATION",
                "error": f"apply_profile failed: {exc}"}

    write_json(pdir / "visual-unification-audit.json", audit)
    s = audit.get("summary") or {}
    print(f"[VISUAL_UNIFICATION] applied: {s.get('slide_count')} slides, "
          f"font_changes={s.get('font_changes')}, size_changes={s.get('size_changes')}, "
          f"color_changes={s.get('color_changes')}, color_kept={s.get('color_kept_semantic')}",
          flush=True)

    return {
        "ok": True,
        "stage": "VISUAL_UNIFICATION",
        "unified_pptx": str(out_pptx),
        "profile": str(pdir / "visual-profile.json"),
        "audit": str(pdir / "visual-unification-audit.json"),
        "summary": s,
    }


def _run_template_unification(project_id: str) -> dict:
    """TEMPLATE_UNIFICATION — align outlier slides to the dominant source deck's
    template shell (page number / logo / footer). Pure Python, no LLM.

    Input : unified-draft-deck.pptx  (from VISUAL_UNIFICATION)
            draft-source-lineage.json (from DRAFT_ASSEMBLY, to vote dominant deck)
    Output: final-shell-deck.pptx     (the deliverable of the draft branch)
            template-unification-audit.json

    Modes (auto-chosen per outlier slide):
      - swap    : same canvas → replace master/layout (NOT YET IMPLEMENTED)
      - overlay : keep outlier's own master, overlay dominant deck's shell shapes
    """
    from . import template_unification as tpu

    pdir = project_dir(project_id)
    input_pptx = pdir / "unified-draft-deck.pptx"
    if not input_pptx.exists():
        fallback = pdir / "revised-draft-deck.pptx"
        if not fallback.exists():
            fallback = pdir / "draft-deck.pptx"
        if not fallback.exists():
            return {"ok": False, "stage": "TEMPLATE_UNIFICATION",
                    "error": "no upstream pptx found (unified/revised/draft all missing)"}
        input_pptx = fallback
        print(f"[TEMPLATE_UNIFICATION] using {input_pptx.name} (unified not present)",
              flush=True)

    lineage = read_json(pdir / "draft-source-lineage.json", {}) or {}
    detection = tpu.detect_dominant_source(lineage)
    print(f"[TEMPLATE_UNIFICATION] dominant: {detection.get('dominant_deck_id')} "
          f"({detection.get('dominant_count')}/{detection.get('total_count')} slides), "
          f"minority={len(detection.get('minority_slide_indices') or [])} slides",
          flush=True)

    dominant_deck_id = detection.get("dominant_deck_id")
    out_pptx = pdir / "final-shell-deck.pptx"

    if not dominant_deck_id:
        # No lineage or all slides new_slide_placeholder: just copy through
        import shutil as _sh
        _sh.copy2(str(input_pptx), str(out_pptx))
        audit_doc = {
            "schema_version": "1.0",
            "generated_at": now(),
            "project_id": project_id,
            "source": "no_dominant",
            "note": "draft-source-lineage.json empty or no dominant deck detected; "
                    "output is a byte-copy of the input.",
            "output_pptx": str(out_pptx),
            "detection": detection,
        }
        write_json(pdir / "template-unification-audit.json", audit_doc)
        return {"ok": True, "stage": "TEMPLATE_UNIFICATION",
                "final_pptx": str(out_pptx),
                "audit": str(pdir / "template-unification-audit.json"),
                "note": "no dominant deck; copied through"}

    dominant_pptx = tpu.resolve_deck_pptx_path(dominant_deck_id, ROOT)
    if not dominant_pptx or not dominant_pptx.exists():
        import shutil as _sh
        _sh.copy2(str(input_pptx), str(out_pptx))
        audit_doc = {
            "schema_version": "1.0",
            "generated_at": now(),
            "project_id": project_id,
            "source": "dominant_pptx_missing",
            "detection": detection,
            "error": f"cannot resolve dominant deck pptx path for {dominant_deck_id!r}",
        }
        write_json(pdir / "template-unification-audit.json", audit_doc)
        return {"ok": True, "stage": "TEMPLATE_UNIFICATION",
                "final_pptx": str(out_pptx),
                "audit": str(pdir / "template-unification-audit.json"),
                "warning": audit_doc["error"]}

    minority = detection.get("minority_slide_indices") or []
    if not minority:
        # Every slide already from dominant deck; nothing to do
        import shutil as _sh
        _sh.copy2(str(input_pptx), str(out_pptx))
        audit_doc = {
            "schema_version": "1.0",
            "generated_at": now(),
            "project_id": project_id,
            "source": "no_minority",
            "detection": detection,
            "note": "all slides already from dominant deck; nothing to unify",
            "output_pptx": str(out_pptx),
        }
        write_json(pdir / "template-unification-audit.json", audit_doc)
        return {"ok": True, "stage": "TEMPLATE_UNIFICATION",
                "final_pptx": str(out_pptx),
                "audit": str(pdir / "template-unification-audit.json"),
                "note": "no minority; copied through"}

    try:
        overlay_audit = tpu.apply_shell_overlay(
            draft_pptx=input_pptx,
            dominant_pptx=dominant_pptx,
            out_pptx=out_pptx,
            minority_slide_indices=minority,
        )
    except Exception as exc:
        return {"ok": False, "stage": "TEMPLATE_UNIFICATION",
                "error": f"apply_shell_overlay failed: {exc}"}

    audit_doc = {
        "schema_version": "1.0",
        "generated_at": now(),
        "project_id": project_id,
        "source": "python_pptx_overlay",
        "detection": detection,
        "dominant_pptx": str(dominant_pptx),
        "overlay": overlay_audit,
    }
    write_json(pdir / "template-unification-audit.json", audit_doc)

    print(f"[TEMPLATE_UNIFICATION] overlay mode: {overlay_audit.get('changed_slides')}/{len(minority)} "
          f"minority slides updated; canvas_match={overlay_audit.get('canvas_match')}", flush=True)

    return {
        "ok": True,
        "stage": "TEMPLATE_UNIFICATION",
        "final_pptx": str(out_pptx),
        "audit": str(pdir / "template-unification-audit.json"),
        "summary": {
            "dominant_deck": dominant_deck_id,
            "minority_count": len(minority),
            "changed_slides": overlay_audit.get("changed_slides"),
            "canvas_match": overlay_audit.get("canvas_match"),
        },
    }

def _run_draft_review(project_id: str) -> dict:
    """Per-slide draft review against gap_cards. Schema per user spec:
    {slide_index, source_fit, problem, severity, can_rewrite_from_source, need_new_source}.

    Combines gap_card.fit_score + plan reuse_binding + outline.key_points to flag
    each slide as 'ok' / 'rewrite-from-source' / 'find-new-source' for the
    SLIDE_REWRITE pass.
    """
    pdir = project_dir(project_id)
    plan = read_json(pdir / "draft-assembly-plan.json", {}) or {}
    slide_plan = read_json(pdir / "slide-plan.json", {}) or {}
    gc_doc = read_json(pdir / "gap-cards.json", {}) or {}
    cards_by_idx = {int(c.get("slide_index")): c for c in (gc_doc.get("gap_cards") or []) if isinstance(c, dict) and c.get("slide_index") is not None}
    plan_by_idx = {int(p.get("slide_index")): p for p in (plan.get("slides") or []) if isinstance(p, dict) and p.get("slide_index") is not None}
    sp_by_idx = {int(s.get("slide_index")): s for s in (slide_plan.get("slides") or []) if isinstance(s, dict) and s.get("slide_index") is not None}

    slides_out: list[dict] = []
    blocking: list[str] = []
    for idx in sorted(plan_by_idx.keys()):
        p_entry = plan_by_idx[idx]
        sp_entry = sp_by_idx.get(idx) or {}
        gc = cards_by_idx.get(idx) or {}
        fit_score = gc.get("fit_score")
        reuse_fit = gc.get("reuse_fit") or p_entry.get("reuse_fit") or "none"
        rid = p_entry.get("source_resource_id")
        # Severity ladder
        if reuse_fit == "none":
            severity = "high"
            can_rewrite = False
            need_new_source = True
            problem = "no matching source slide; placeholder requires authoring"
        elif reuse_fit == "weak":
            severity = "high"
            can_rewrite = False
            need_new_source = True
            problem = "source slide only weakly related to target; rewrite from source risks misleading content"
        elif reuse_fit == "partial":
            severity = "medium"
            can_rewrite = True
            need_new_source = False
            problem = "source covers layout/some content; metadata/title/data labels need rewrite"
        else:
            severity = "low"
            can_rewrite = True
            need_new_source = False
            problem = "source is a strong match; only minor metadata replacement needed"
        # Promote conflict_gap / internal_material_gap severity
        gtypes = gc.get("gap_types") or []
        if "conflict_gap" in gtypes:
            severity = "high"
            problem = "source has CONFLICTING data/labels with target topic; must remove before reuse"
            need_new_source = True
        if "internal_material_gap" in gtypes:
            severity = "high"
            problem = "internal-only material gap; needs lab-specific input from user"
            can_rewrite = False
            need_new_source = True

        entry = {
            "slide_index": idx,
            "target_title": p_entry.get("target_title") or sp_entry.get("target_title"),
            "target_role": p_entry.get("target_role"),
            "source_resource_id": rid,
            "source_fit": reuse_fit,
            "fit_score": fit_score,
            "problem": problem,
            "severity": severity,
            "can_rewrite_from_source": can_rewrite,
            "need_new_source": need_new_source,
            "gap_types": gtypes,
            "next_action": gc.get("next_action") or ("text_rewrite" if can_rewrite else "find_new_source"),
        }
        slides_out.append(entry)
        if severity == "high":
            blocking.append(f"slide {idx}: {problem}")

    data = {
        "schema_version": "2.0",
        "generated_at": now(),
        "project_id": project_id,
        "source": "deterministic_from_gap_cards",
        "slides": slides_out,
        "overall_pass": not blocking,
        "blocking_issues": blocking,
        "summary": {
            "total": len(slides_out),
            "high_severity": sum(1 for s in slides_out if s["severity"] == "high"),
            "need_new_source": sum(1 for s in slides_out if s["need_new_source"]),
            "can_rewrite": sum(1 for s in slides_out if s["can_rewrite_from_source"]),
        },
    }
    write_json(pdir / "draft-review.json", data)
    return {"ok": True, "stage": "DRAFT_REVIEW",
            "draft_review": str(pdir / "draft-review.json"),
            "source": data.get("source"),
            "overall_pass": data.get("overall_pass"),
            "blocking_issues_count": len(data.get("blocking_issues") or [])}


def _run_gap_analysis(project_id: str) -> dict:
    """Produce slide-gap-plan.json directly from gap_cards.json.

    Per user spec each entry has:
      {slide_index, gap_type, needed_material, preferred_source, next_agent}.
    """
    pdir = project_dir(project_id)
    gc_doc = read_json(pdir / "gap-cards.json", {}) or {}
    review = read_json(pdir / "draft-review.json", {}) or {}
    understanding = read_json(pdir / "data/source-understanding.json", {}) or {}
    cards = gc_doc.get("gap_cards") or []
    review_by_idx = {int(s.get("slide_index")): s for s in (review.get("slides") or []) if isinstance(s, dict) and s.get("slide_index") is not None}
    must_use_ids = {str(m.get("resource_id")) for m in (understanding.get("must_use_materials") or [])}
    project_doc_anchors = {}
    for theme, ids in (understanding.get("doc_summary_by_theme") or {}).items():
        for rid in ids:
            project_doc_anchors.setdefault(rid, []).append(theme)

    NEXT_AGENT_MAP = {
        "gap_research": "gap_research",
        "new_visual": "slide_rewrite",
        "internal_material_request": "internal_material_request",
        "text_rewrite": "slide_rewrite",
        "no_action": "none",
    }

    slides_out: list[dict] = []
    for c in cards:
        if not isinstance(c, dict):
            continue
        idx = c.get("slide_index")
        rv = review_by_idx.get(int(idx)) if idx is not None else {}
        gap_types = list(c.get("gap_types") or [])
        needed_material = []
        # Evidence-style gaps go to gap_research
        for ev in (c.get("evidence_needed") or []):
            needed_material.append(ev)
        # Visual gaps add what visual the page needs
        if "visual_gap" in gap_types:
            for kp in (c.get("must_add") or []):
                needed_material.append(f"visual: {kp}")
        # Internal material
        if "internal_material_gap" in gap_types:
            needed_material.append("internal material (lab-specific): " + (c.get("transition_note") or c.get("target_title") or ""))
        # Preferred source candidates
        preferred_source = []
        if "evidence_gap" in gap_types:
            preferred_source.append("课题组已上传 PDF / paper")
            preferred_source.append("web search / paper search")
        if "internal_material_gap" in gap_types:
            preferred_source.append("课题组内部部署文档 / 监控截图 / 工程实践 PPT")
        if "visual_gap" in gap_types and "evidence_gap" not in gap_types:
            preferred_source.append("可用项目 figure 池 / 重绘草图")
        if "conflict_gap" in gap_types:
            preferred_source.append("项目自有数据 / 内部实验日志")
        if not preferred_source:
            preferred_source.append("slide_rewrite (本页源已足够, 仅需文字改写)")

        next_action = c.get("next_action") or "text_rewrite"
        next_agent = NEXT_AGENT_MAP.get(next_action, "slide_rewrite")

        slides_out.append({
            "slide_index": idx,
            "target_title": c.get("target_title"),
            "gap_type": gap_types,
            "needed_material": needed_material,
            "preferred_source": preferred_source,
            "next_agent": next_agent,
            # Auxiliary fields (kept for downstream stages that already read them)
            "current_state": f"reuse_fit={c.get('reuse_fit')}; rewrite_scope={c.get('rewrite_scope')}",
            "narrative_gaps": [],
            "evidence_gaps": c.get("evidence_needed") or [],
            "visual_gaps": [k for k in (c.get("must_add") or [])] if "visual_gap" in gap_types else [],
            "citation_gaps": [],
            "sensitivity_risks": [],
            "reuse_risks": [],
            "rewrite_plan": c.get("must_replace") or [],
            "research_queries": [
                {"query": ev,
                 "purpose": f"support slide {idx} target_title: {c.get('target_title')}",
                 "preferred_source_type": "paper"}
                for ev in (c.get("evidence_needed") or [])[:3]
            ] if "evidence_gap" in gap_types else [],
            "severity": (rv or {}).get("severity"),
        })

    data = {
        "schema_version": "4.0",
        "generated_at": now(),
        "project_id": project_id,
        "source": "deterministic_from_gap_cards",
        "slide_count": len(slides_out),
        "slides": slides_out,
        "summary": {
            "high_priority": sum(1 for s in slides_out if (s.get("severity") == "high")),
            "next_gap_research": sum(1 for s in slides_out if s.get("next_agent") == "gap_research"),
            "next_slide_rewrite": sum(1 for s in slides_out if s.get("next_agent") == "slide_rewrite"),
            "next_internal_material_request": sum(1 for s in slides_out if s.get("next_agent") == "internal_material_request"),
        },
    }
    write_json(pdir / "slide-gap-plan.json", data)
    return {"ok": True, "stage": "GAP_ANALYSIS",
            "slide_gap_plan": str(pdir / "slide-gap-plan.json"),
            "source": data.get("source"),
            "gap_count": sum(len(s.get("evidence_gaps") or []) for s in (data.get("slides") or []))}


def _append_gap_log(project_id: str, stage: str, outcome: dict, attempts: int) -> None:
    pdir = project_dir(project_id)
    log_path = pdir / "gap-research-fail-log.md"
    entry = [
        f"## {stage} fallback — {now()}",
        f"- attempts: {attempts}",
        f"- error: `{(outcome or {}).get('error') or 'unknown'}`",
    ]
    if (outcome or {}).get("raw_excerpt"):
        entry.append(f"- raw_excerpt (first 400 chars):\n  ```\n  {(outcome or {})['raw_excerpt']}\n  ```")
    entry.append("")
    text = log_path.read_text(encoding="utf-8") if log_path.exists() else "# Gap Pipeline Fallback Log\n\n"
    log_path.write_text(text + "\n".join(entry) + "\n", encoding="utf-8")


def _run_gap_research(project_id: str, payload: dict) -> dict:
    """W5: Claude with WebSearch+WebFetch tools enabled runs real retrieval over
    slide-gap-plan.research_queries. Outputs research-query-plan.json (model's
    refined plan) + raw-research-results.json (per-query hits with url/title/excerpt).
    Retry once on failure; second failure logs to gap-research-fail-log.md and
    writes empty results — pipeline does NOT roll back (policy)."""
    from . import claude_cli

    pdir = project_dir(project_id)
    plan = read_json(pdir / "slide-gap-plan.json", {}) or {}
    plan_slides = plan.get("slides") if isinstance(plan.get("slides"), list) else []
    query_items = []
    for s in plan_slides:
        if not isinstance(s, dict):
            continue
        idx = s.get("slide_index")
        for q in s.get("research_queries") or []:
            if isinstance(q, dict):
                query_items.append({
                    "slide_index": idx,
                    "query": q.get("query"),
                    "purpose": q.get("purpose"),
                    "preferred_source_type": q.get("preferred_source_type"),
                })
            elif isinstance(q, str) and q.strip():
                query_items.append({"slide_index": idx, "query": q, "purpose": "", "preferred_source_type": "paper"})

    if not query_items:
        # No gaps to research — write empty artifacts and return.
        write_json(pdir / "research-query-plan.json", {
            "schema_version": "3.0", "generated_at": now(), "project_id": project_id,
            "source": "no_queries", "items": [], "note": "slide-gap-plan had no research_queries",
        })
        write_json(pdir / "raw-research-results.json", {
            "schema_version": "3.0", "generated_at": now(), "project_id": project_id,
            "source": "no_queries", "results": [],
        })
        return {"ok": True, "stage": "GAP_RESEARCH", "query_count": 0, "source": "no_queries"}

    # Persist the deterministic query plan first so it survives even if claude fails.
    write_json(pdir / "research-query-plan.json", {
        "schema_version": "3.0",
        "generated_at": now(),
        "project_id": project_id,
        "source": "gap_analysis_passthrough",
        "items": query_items,
    })

    prompt = (
        "You are PPT-agent's research executor. For every item in `queries`, call the WebSearch tool\n"
        "to find authoritative sources, then call WebFetch to extract supporting text from the best hits.\n"
        "Cap at 2 useful sources per query. Output a single JSON object with this shape, no prose:\n"
        '{ "results": [\n'
        '    { "slide_index": int, "query": str, "purpose": str,\n'
        '      "hits": [ { "url": str, "title": str, "access_date": "YYYY-MM-DD",\n'
        '                  "excerpt": "≤400 chars verbatim quote that supports the purpose",\n'
        '                  "source_type": "paper|official_doc|industry_blog|benchmark|other",\n'
        '                  "confidence": 0.0..1.0 } ] }\n'
        '  ] }\n'
        "Hard rules:\n"
        "- Do not fabricate URLs. If WebSearch returns nothing useful, set hits=[].\n"
        "- Excerpts must be verbatim text fragments from WebFetch results (no paraphrase).\n"
        "- Skip queries that look unanswerable rather than guess.\n\n"
        "INPUT:\n" + json.dumps({"queries": query_items}, ensure_ascii=False)
    )
    skill = claude_cli.skill_paths_for_agent("GapResearchAgent")

    def attempt():
        return claude_cli.call_claude_with_tools(
            prompt,
            allowed_tools=["WebSearch", "WebFetch"],
            skill=skill,
            parse_json=True,
            timeout=900,
        )

    outcome, used = claude_cli.call_with_retry(attempt, attempts=2)
    if outcome.get("ok") and isinstance(outcome.get("data"), dict):
        data = outcome["data"]
        results = data.get("results") if isinstance(data.get("results"), list) else []
        artifact = {
            "schema_version": "3.0",
            "generated_at": now(),
            "project_id": project_id,
            "source": "claude_websearch_webfetch",
            "attempts_used": used,
            "query_count": len(query_items),
            "result_count": len(results),
            "results": results,
        }
        write_json(pdir / "raw-research-results.json", artifact)
        return {"ok": True, "stage": "GAP_RESEARCH",
                "query_count": len(query_items),
                "result_count": len(results),
                "source": "claude_websearch_webfetch",
                "attempts_used": used}

    # Failed even with retry — log and proceed with empty results (no rollback).
    _append_gap_log(project_id, "GAP_RESEARCH", outcome, used)
    write_json(pdir / "raw-research-results.json", {
        "schema_version": "3.0",
        "generated_at": now(),
        "project_id": project_id,
        "source": "stub_after_retry_failed",
        "attempts_used": used,
        "fallback_reason": outcome.get("error"),
        "query_count": len(query_items),
        "result_count": 0,
        "results": [],
    })
    return {"ok": True, "stage": "GAP_RESEARCH",
            "query_count": len(query_items),
            "result_count": 0,
            "source": "stub_after_retry_failed",
            "attempts_used": used,
            "fallback_reason": outcome.get("error")}


def _run_gap_synthesis(project_id: str) -> dict:
    """W5: Turn raw-research-results.json into per-slide-evidence-pack.json +
    citations.json + research.md + research-audit.json. Retry once; on second
    failure log + write empty packs (no rollback)."""
    from . import claude_cli

    pdir = project_dir(project_id)
    raw = read_json(pdir / "raw-research-results.json", {}) or {}
    plan = read_json(pdir / "slide-gap-plan.json", {}) or {}
    query_plan = read_json(pdir / "research-query-plan.json", {}) or {}

    results = raw.get("results") if isinstance(raw.get("results"), list) else []
    plan_slides = plan.get("slides") if isinstance(plan.get("slides"), list) else []
    gap_summary = [
        {
            "slide_index": s.get("slide_index"),
            "evidence_gaps": s.get("evidence_gaps") or [],
            "citation_gaps": s.get("citation_gaps") or [],
        }
        for s in plan_slides if isinstance(s, dict)
    ]
    # When research is empty, still produce minimal artifacts so downstream
    # SLIDE_REWRITE can mark claims as unsupported.
    if not results:
        empty = {
            "schema_version": "3.0",
            "generated_at": now(),
            "project_id": project_id,
            "source": raw.get("source") or "no_research_results",
            "packs": [
                {
                    "slide_index": g["slide_index"],
                    "usable_facts": [],
                    "chartable_data": [],
                    "source_refs": [],
                    "unsupported_claims": g.get("evidence_gaps") or [],
                    "remaining_gaps": g.get("evidence_gaps") or [],
                }
                for g in gap_summary
            ],
        }
        write_json(pdir / "per-slide-evidence-pack.json", empty)
        write_json(pdir / "citations.json", {"schema_version": "3.0", "citations": []})
        write_json(pdir / "research-audit.json", {
            "schema_version": "3.0", "generated_at": now(),
            "web_results_count": 0, "gap_query_count": sum(len(s.get("evidence_gaps") or []) for s in plan_slides),
            "unsupported_query_count": sum(len(s.get("evidence_gaps") or []) for s in plan_slides),
            "source": empty["source"],
        })
        (pdir / "research.md").write_text(
            "# Gap Research Synthesis\n\nNo external research results available; "
            "all claims flagged as unsupported.\n", encoding="utf-8")
        # Keep legacy v2 alias for any older consumers.
        write_json(pdir / "gap-research-results.json", {
            "schema_version": "3.0", "generated_at": now(),
            "query_count": len(query_plan.get("items") or []), "result_count": 0,
            "source": empty["source"],
        })
        return {"ok": True, "stage": "GAP_SYNTHESIS",
                "per_slide_evidence_pack": str(pdir / "per-slide-evidence-pack.json"),
                "source": empty["source"], "fact_count": 0}

    prompt = (
        "You are PPT-agent's evidence synthesizer. Read raw research results and per-slide gaps,\n"
        "then produce per-slide-evidence-pack and citations. Return a JSON object only:\n"
        '{ "packs": [ { "slide_index": int, "usable_facts": [ {"fact": str, "source_id": str,\n'
        '    "supports": "claim_to_prove|visual|context", "confidence": 0.0..1.0,\n'
        '    "verbatim_quote": "..." } ],\n'
        '    "chartable_data": [ {"label": str, "values": [...], "source_id": str} ],\n'
        '    "source_refs": [ "citation_001", "..." ],\n'
        '    "unsupported_claims": [ "evidence_gap text..." ],\n'
        '    "remaining_gaps": [ "..." ] } ],\n'
        '  "citations": [ {"id": "citation_001", "url": str, "title": str,\n'
        '    "access_date": "YYYY-MM-DD"} ] }\n'
        "Hard rules:\n"
        "- Every source_id you cite must exist in citations[].\n"
        "- Do not invent numbers; if the source did not give a number, do not fill it in.\n"
        "- For every evidence_gap that has no supporting source, copy it verbatim into\n"
        "  the slide's `unsupported_claims` — downstream SLIDE_REWRITE will mark them.\n"
        "- Return JSON only, no markdown fences.\n\n"
        "INPUT:\n" + json.dumps({"results": results, "gap_summary": gap_summary}, ensure_ascii=False)
    )
    skill = claude_cli.skill_paths_for_agent("GapSynthesisAgent")

    def attempt():
        return claude_cli.call_claude_json(prompt, skill=skill, timeout=480)

    outcome, used = claude_cli.call_with_retry(attempt, attempts=2)
    if outcome.get("ok") and isinstance(outcome.get("data"), dict):
        data = outcome["data"]
        packs = data.get("packs") if isinstance(data.get("packs"), list) else []
        citations = data.get("citations") if isinstance(data.get("citations"), list) else []
        # Build citation lookup for audit.
        cid_set = {str(c.get("id")) for c in citations if isinstance(c, dict) and c.get("id")}
        # Drop source_refs that aren't in citation table.
        fact_count = 0
        for p in packs:
            if not isinstance(p, dict):
                continue
            uf = p.get("usable_facts") or []
            for f in uf:
                if isinstance(f, dict) and str(f.get("source_id")) not in cid_set:
                    f["source_id"] = None
            fact_count += sum(1 for f in uf if isinstance(f, dict) and f.get("source_id"))
            p["source_refs"] = [r for r in (p.get("source_refs") or []) if str(r) in cid_set]
        write_json(pdir / "per-slide-evidence-pack.json", {
            "schema_version": "3.0",
            "generated_at": now(),
            "project_id": project_id,
            "source": "claude",
            "attempts_used": used,
            "packs": packs,
        })
        write_json(pdir / "citations.json", {
            "schema_version": "3.0",
            "generated_at": now(),
            "citations": citations,
        })
        unsupported = sum(len(p.get("unsupported_claims") or []) for p in packs if isinstance(p, dict))
        write_json(pdir / "research-audit.json", {
            "schema_version": "3.0", "generated_at": now(),
            "web_results_count": sum(len(r.get("hits") or []) for r in results if isinstance(r, dict)),
            "gap_query_count": len(query_plan.get("items") or []),
            "unsupported_query_count": unsupported,
            "fact_count": fact_count,
            "citation_count": len(citations),
            "source": "claude",
        })
        # Human-readable research.md
        lines = [
            "---",
            'schema_version: "3.0"',
            f'generated_at: "{now()}"',
            'source: "claude"',
            "---",
            "",
            "# Gap Research Synthesis",
            "",
            f"- usable_facts total: {fact_count}",
            f"- citations: {len(citations)}",
            f"- unsupported claims: {unsupported}",
            "",
            "## Citations",
        ]
        for c in citations:
            if isinstance(c, dict):
                lines.append(f"- `{c.get('id')}` — {c.get('title') or '?'} — {c.get('url') or ''}")
        (pdir / "research.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        # Legacy v2 alias.
        write_json(pdir / "gap-research-results.json", {
            "schema_version": "3.0", "generated_at": now(),
            "query_count": len(query_plan.get("items") or []),
            "result_count": sum(len(r.get("hits") or []) for r in results if isinstance(r, dict)),
            "source": "claude",
        })
        return {"ok": True, "stage": "GAP_SYNTHESIS",
                "per_slide_evidence_pack": str(pdir / "per-slide-evidence-pack.json"),
                "source": "claude", "attempts_used": used,
                "fact_count": fact_count, "citation_count": len(citations),
                "unsupported_count": unsupported}

    # Failed even with retry — log + empty packs (no rollback).
    _append_gap_log(project_id, "GAP_SYNTHESIS", outcome, used)
    empty = {
        "schema_version": "3.0",
        "generated_at": now(),
        "project_id": project_id,
        "source": "stub_after_retry_failed",
        "attempts_used": used,
        "fallback_reason": outcome.get("error"),
        "packs": [
            {
                "slide_index": g["slide_index"],
                "usable_facts": [],
                "chartable_data": [],
                "source_refs": [],
                "unsupported_claims": g.get("evidence_gaps") or [],
                "remaining_gaps": g.get("evidence_gaps") or [],
            }
            for g in gap_summary
        ],
    }
    write_json(pdir / "per-slide-evidence-pack.json", empty)
    write_json(pdir / "citations.json", {"schema_version": "3.0", "citations": []})
    write_json(pdir / "research-audit.json", {
        "schema_version": "3.0", "generated_at": now(),
        "web_results_count": sum(len(r.get("hits") or []) for r in results if isinstance(r, dict)),
        "gap_query_count": len(query_plan.get("items") or []),
        "unsupported_query_count": sum(len(p.get("unsupported_claims") or []) for p in empty["packs"]),
        "fact_count": 0, "citation_count": 0,
        "source": "stub_after_retry_failed",
    })
    (pdir / "research.md").write_text(
        f"# Gap Research Synthesis (FAILED)\n\nattempts={used}; error={outcome.get('error')}\n",
        encoding="utf-8")
    write_json(pdir / "gap-research-results.json", {
        "schema_version": "3.0", "generated_at": now(),
        "query_count": len(query_plan.get("items") or []),
        "result_count": 0, "source": "stub_after_retry_failed",
    })
    return {"ok": True, "stage": "GAP_SYNTHESIS",
            "source": "stub_after_retry_failed",
            "attempts_used": used,
            "fallback_reason": outcome.get("error"),
            "fact_count": 0,
            "unsupported_count": sum(len(p.get("unsupported_claims") or []) for p in empty["packs"])}


def _snapshot_paths(pdir, names: list[str]) -> dict[str, dict]:
    snapshots: dict[str, dict] = {}
    tmp_root = pdir / ".tmp-draft-render-snapshot"
    if tmp_root.exists():
        shutil.rmtree(tmp_root)
    tmp_root.mkdir(parents=True, exist_ok=True)
    for name in names:
        path = pdir / name
        if path.is_file():
            dest = tmp_root / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
            snapshots[name] = {"kind": "file", "dest": dest}
        elif path.is_dir():
            dest = tmp_root / name
            shutil.copytree(path, dest)
            snapshots[name] = {"kind": "dir", "dest": dest}
        else:
            snapshots[name] = {"kind": "missing"}
    return snapshots


def _restore_snapshot(pdir, snapshots: dict[str, dict]) -> None:
    tmp_root = pdir / ".tmp-draft-render-snapshot"
    for name, meta in snapshots.items():
        path = pdir / name
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()
        if meta.get("kind") == "file":
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(meta["dest"], path)
        elif meta.get("kind") == "dir":
            shutil.copytree(meta["dest"], path)
    if tmp_root.exists():
        shutil.rmtree(tmp_root)


def _run_slide_rewrite(project_id: str, payload: dict) -> dict:
    pdir = project_dir(project_id)
    outline = read_json(pdir / "reuse-first-outline.json", {})
    assembly = read_json(pdir / "draft-assembly-plan.json", {})
    draft_visual = read_json(pdir / "draft-visual-plan.json", {})
    slide_plan = read_json(pdir / "slide-plan.json", {}) or {}
    audit = read_json(pdir / "reuse-decision-audit.json", {}) or {}
    evidence_pack = read_json(pdir / "per-slide-evidence-pack.json", {}) or {}
    citations_doc = read_json(pdir / "citations.json", {}) or {}
    slides = outline.get("slides") if isinstance(outline, dict) else []
    if not isinstance(slides, list) or not slides:
        return {"ok": False, "error": "reuse-first-outline.json missing or invalid"}

    plan_by_idx = {int(s.get("slide_index") or 0): s for s in (slide_plan.get("slides") or []) if isinstance(s, dict)}
    pack_by_idx = {int(p.get("slide_index") or 0): p for p in (evidence_pack.get("packs") or []) if isinstance(p, dict)}
    audits_by_rid = {str(a.get("resource_id")): a for a in (audit.get("audits") or []) if isinstance(a, dict)}
    citations_index = {str(c.get("id")): c for c in (citations_doc.get("citations") or []) if isinstance(c, dict) and c.get("id")}

    visual_by_idx = {
        int(item.get("slide_index") or 0): item
        for item in (draft_visual.get("slides") or [])
        if isinstance(item, dict)
    }
    manuscript = [
        "---",
        'schema_version: "3.0"',
        f'generated_at: "{now()}"',
        f"slide_count: {len(slides)}",
        f'topic: "{str(outline.get("topic") or project_id).replace(chr(34), chr(92) + chr(34))}"',
        "---",
    ]
    plan_slides_out = []
    composition_slides = []
    visual_slides = []
    rewrite_audit_entries = []
    total_unsupported = 0
    total_evidence_used = 0

    for slide in slides:
        idx = int(slide.get("slide_index") or len(plan_slides_out) + 1)
        sp = plan_by_idx.get(idx) or {}
        pk = pack_by_idx.get(idx) or {}
        title = str(slide.get("target_title") or f"Slide {idx}")
        role = str(slide.get("target_role") or "content")
        # W5: claim must come from slide-plan (not free invention)
        claim = str(sp.get("claim_to_prove") or slide.get("target_claim") or title)
        selected = slide.get("selected_reuse") if isinstance(slide.get("selected_reuse"), dict) else {}
        # W5: gather evidence facts strictly from per-slide-evidence-pack
        usable_facts = [f for f in (pk.get("usable_facts") or []) if isinstance(f, dict) and f.get("fact")]
        chartable = [c for c in (pk.get("chartable_data") or []) if isinstance(c, dict)]
        unsupported_claims = list(pk.get("unsupported_claims") or [])
        source_refs = [r for r in (pk.get("source_refs") or []) if str(r) in citations_index]
        # W5: forbidden_use must come from reuse-decision-audit, not selected_reuse alone
        rid = str(selected.get("resource_id") or selected.get("object_id") or "")
        audit_entry = audits_by_rid.get(rid) if rid else None
        forbidden_use = (audit_entry or {}).get("not_allowed") or selected.get("forbidden_use") or []
        required_actions = (audit_entry or {}).get("required_actions") or []

        plan_visual_type = "image-and-bullets" if role in {"cover", "closing"} else "table" if role == "agenda" else "diagram"
        plan_layout_type = "title-image" if role == "cover" else "closing" if role == "closing" else "evidence-matrix" if role == "agenda" else "assertion-evidence"
        plan_slides_out.append({
            "index": idx,
            "title": title,
            "section": role,
            "story_role": role,
            "layout_type": plan_layout_type,
            "visual_type": plan_visual_type,
            "claim": claim if role not in {"cover", "agenda"} else "",
            "key_message": claim,
            "assertion_title": claim,
            "source_lineage": slide.get("source_candidates") or [],
            "selected_reuse": selected,
            "reuse_decisions": [selected] if selected else [],
            "gap_resolution": "rewritten from slide-plan + evidence-pack + audited reuse",
            "citations": source_refs,
            "unsupported_claims": unsupported_claims,
        })
        composition_slides.append({
            "slide_index": idx,
            "title": title,
            "claim_to_prove": claim,
            "evidence_need": sp.get("evidence_need") or [],
            "evidence_available": bool(usable_facts) or bool(slide.get("source_candidates")),
            "primary_visual_role": selected.get("reuse_mode") or "editable_redraw",
            "required_blocks": ["source_lineage", "evidence", "final_message"],
            "source_lineage": slide.get("source_candidates") or [],
            "usable_fact_count": len(usable_facts),
            "unsupported_claim_count": len(unsupported_claims),
            "forbidden_use": forbidden_use,
            "required_rewrite_actions": required_actions,
        })
        v = dict(visual_by_idx.get(idx) or {})
        final_visual_type = "image-and-bullets" if role in {"cover", "closing"} else "table" if role == "agenda" else "diagram"
        final_layout_type = "title-image" if role == "cover" else "closing" if role == "closing" else "evidence-matrix" if role == "agenda" else "assertion-evidence"
        v.update({
            "slide_index": idx,
            "visual_type": final_visual_type,
            "layout_type": final_layout_type,
            "assertion_title": claim,
            "source_lineage": slide.get("source_candidates") or [],
            "reuse_decisions": [selected] if selected else [],
            "gap_resolution": "final slide keeps approved source lineage and rewrites visible text",
            "content_fill_target": 0.32 if role in {"cover", "closing"} else 0.58,
            "quality_requirements": {
                "content_fill_target": 0.32 if role in {"cover", "closing"} else 0.58,
                "requires_evidence": role not in {"cover", "agenda", "closing"},
            },
            "evidence_facts": usable_facts,
            "chartable_data": chartable,
            "unsupported_claims": unsupported_claims,
            "citations": source_refs,
        })
        v.update(_v2_visual_fields(slide, selected, idx, len(slides)))
        existing_assets = [
            asset for asset in (v.get("assets") or [])
            if isinstance(asset, dict) and str(asset.get("local_path") or asset.get("path") or "").strip()
        ]
        hydrated_asset = _approved_asset_from_reuse(project_id, selected, slide_index=idx)
        if hydrated_asset and not any(
            str(asset.get("local_path") or asset.get("path") or "") == str(hydrated_asset.get("local_path") or hydrated_asset.get("path") or "")
            for asset in existing_assets
        ):
            existing_assets.insert(0, hydrated_asset)
        if existing_assets:
            v["assets"] = existing_assets
            v["image_decision"] = _reuse_image_decision(selected, existing_assets, str(selected.get("reuse_mode") or "use_existing"))
            v["asset_request"] = _reuse_asset_request(selected, existing_assets)
            v["visual_type"] = "image-and-bullets" if role in {"cover", "closing"} else "image-evidence"
            v["layout_type"] = "source-slide-evidence" if str(existing_assets[0].get("asset_type") or "") == "source_slide_svg" else "source-figure-evidence"
            v["semantic_component_id"] = "key_insight_mechanism.v1"
        visual_slides.append(v)

        # Manuscript with evidence + unsupported markers
        evidence_lines = []
        for f in usable_facts[:5]:
            cite = f"[cite:{f.get('source_id')}]" if f.get("source_id") else "[cite:unsourced]"
            evidence_lines.append(f"- {f.get('fact')} {cite}")
        unsupported_block = []
        if unsupported_claims:
            unsupported_block.append("Unsupported claims (低置信，需后续补研):")
            for u in unsupported_claims[:5]:
                unsupported_block.append(f"- [低置信] {u}")
        manuscript.extend([
            "",
            f"## Slide {idx}: {title}",
            f"Claim: {claim}",
            "On-slide copy:",
            "\n".join(_draft_slide_rewrite_lines(slide, selected)),
            "Evidence:",
            "\n".join(evidence_lines) if evidence_lines else "- (no usable_facts; mark as unsupported)",
        ])
        if unsupported_block:
            manuscript.extend(unsupported_block)
        manuscript.extend([
            "Visual instruction: Use approved source lineage, then rewrite into final presentation language.",
            f"Speaker notes: Final rewrite. Source mode: {selected.get('reuse_mode') or 'placeholder'}; "
            f"facts used: {len(usable_facts)}; unsupported: {len(unsupported_claims)}.",
            f"Forbidden use: {', '.join(forbidden_use) if forbidden_use else 'none'}",
            f"Source references: {selected.get('path') or selected.get('object_id') or 'none'}",
            f"Citations: {', '.join(source_refs) if source_refs else 'none'}",
        ])
        if idx < len(slides):
            manuscript.extend(["", "---"])

        rewrite_audit_entries.append({
            "slide_index": idx,
            "claim_source": "slide_plan" if sp.get("claim_to_prove") else "outline",
            "evidence_facts_used": len(usable_facts),
            "unsupported_claims": len(unsupported_claims),
            "citations_used": source_refs,
            "forbidden_use_respected": True,
        })
        total_unsupported += len(unsupported_claims)
        total_evidence_used += len(usable_facts)

    write_json(pdir / "model-routed-plan.json", {
        "schema_version": "3.0",
        "generated_at": now(),
        "project_id": project_id,
        "generated_by": "slide_rewrite",
        "fallback_used": False,
        "slides": plan_slides_out,
    })
    write_json(pdir / "slide-composition.json", {
        "schema_version": "3.0",
        "generated_at": now(),
        "project_id": project_id,
        "slide_count": len(composition_slides),
        "slides": composition_slides,
    })
    write_json(pdir / "visual-plan.json", {
        "schema_version": "3.0",
        "generated_at": now(),
        "project_id": project_id,
        "source": "slide_rewrite",
        "slide_count": len(visual_slides),
        "slides": visual_slides,
    })
    write_json(pdir / "slide-rewrite-audit.json", {
        "schema_version": "1.0",
        "generated_at": now(),
        "project_id": project_id,
        "total_evidence_facts_used": total_evidence_used,
        "total_unsupported_claims": total_unsupported,
        "entries": rewrite_audit_entries,
    })
    (pdir / "manuscript.md").write_text("\n".join(manuscript).rstrip() + "\n", encoding="utf-8")
    stage_controller.build_slide_state(project_id)
    return {"ok": True, "manuscript": str(pdir / "manuscript.md"), "visual_plan": str(pdir / "visual-plan.json"), "slide_count": len(slides)}


def _run_style_unification(project_id: str, payload: dict) -> dict:
    pdir = project_dir(project_id)
    template = _ensure_template_profile(project_id, payload.get("template"))
    visual = read_json(pdir / "visual-plan.json", {})
    slides = visual.get("slides") if isinstance(visual, dict) else []
    plan = {
        "schema_version": "2.0",
        "generated_at": now(),
        "project_id": project_id,
        "source": "style_unification",
        "template_id": template.get("template_id"),
        "template_name": template.get("name"),
        "policy": {
            "basic_template": "identity shell only",
            "preserve_source_assets": True,
            "unify": ["typography", "footer", "page_number", "title_rule", "citation_format"],
        },
        "slides": [
            {
                "slide_index": item.get("slide_index"),
                "source_lineage_preserved": bool(item.get("source_lineage")),
                "approved_assets": item.get("assets") or [],
                "unification_action": "apply basic shell and keep approved source visuals",
            }
            for item in slides or [] if isinstance(item, dict)
        ],
    }
    write_json(pdir / "style-unification-plan.json", plan)
    result = _run_v2_template_binding(project_id, payload)
    return {"ok": bool(result.get("template_binding")), "style_unification_plan": str(pdir / "style-unification-plan.json"), **result}


# Which upstream stage fixes each failing review dimension.
_DIMENSION_ROUTE = {
    "structural": "RENDER",
    "fact_citation": "GAP_RESEARCH",
    "visual": "STYLE_UNIFICATION",
    "visual_spec": "SLIDE_REWRITE",
    "component_binding": "SLIDE_REWRITE",
    "citation_footer": "STYLE_UNIFICATION",
    "content_depth": "SLIDE_REWRITE",
    "claim_quality": "REUSE_OUTLINE",
    "text_density": "SLIDE_REWRITE",
    "source_usage": "DRAFT_ASSEMBLY",
    "plan_review": "REUSE_OUTLINE",
    "svg_visual_scan": "RENDER",
    "render_audit": "RENDER",
    "logic": "REUSE_OUTLINE",
    "duration_density": "REUSE_OUTLINE",
    "audience_fit": "REUSE_OUTLINE",
    # W6 additions:
    "evidence_coverage": "SLIDE_REWRITE",   # NB: not GAP_* (policy: no GAP rollback)
    "unsupported_claims": "SLIDE_REWRITE",
    "render_precheck": "RENDER",
    "reuse_truth": "DRAFT_ASSEMBLY_PLAN",
}


def _normalize_review_issues(raw_issues) -> list[dict]:
    issues = []
    for raw in raw_issues if isinstance(raw_issues, list) else []:
        if not isinstance(raw, dict):
            continue
        route = str(raw.get("route_to") or _DIMENSION_ROUTE.get(str(raw.get("issue_type")).lower(), "")).upper()
        issues.append({
            "issue_type": str(raw.get("issue_type") or "general"),
            "slide": raw.get("slide"),
            "route_to": route or None,
            "problem": str(raw.get("problem") or "").strip(),
            "required_change": str(raw.get("required_change") or "").strip(),
        })
    return issues


def _detect_unsupported_pptx_elements(src_slide) -> list[str]:
    """v30 fix F: 扫源 slide 找 byte-clone 后可能视觉降级的元素.

    这些元素 clone_slide 常规复制 XML 后仍可能失败:
      - OLE 对象 (嵌入 Excel/Word) — 需 payload 但常常缺失
      - ActiveX 控件 (含表单/按钮) — 需 payload
      - 视频/音频 — 引用外部 media 文件, 可能没导入
      - SmartArt (dgm:dataModel) — dgm 部分复制可能引用外部图元
      - 3D 模型 / Chart 复杂类型
      - AlternateContent 里的 fallback (mc:Fallback)

    返回被检测到的元素类型名列表 (empty if all clean).
    """
    from pptx.oxml.ns import qn
    warnings: list[str] = []
    try:
        root = src_slide.element
    except Exception:
        return []
    ns_ole = "urn:schemas-microsoft-com:office:office"
    ns_v = "urn:schemas-microsoft-com:vml"
    ns_a = "http://schemas.openxmlformats.org/drawingml/2006/main"
    ns_dgm = "http://schemas.openxmlformats.org/drawingml/2006/diagram"
    ns_a14 = "http://schemas.microsoft.com/office/drawing/2010/main"
    checks = [
        (f"{{{ns_ole}}}OLEObject", "OLE 嵌入对象"),
        (f"{{{ns_ole}}}oleobj", "OLE 嵌入对象"),
        ("{http://schemas.openxmlformats.org/presentationml/2006/main}oleObj", "OLE 嵌入对象"),
        ("{http://schemas.openxmlformats.org/presentationml/2006/main}videoFile", "嵌入视频"),
        ("{http://schemas.openxmlformats.org/presentationml/2006/main}audioFile", "嵌入音频"),
        ("{http://schemas.openxmlformats.org/presentationml/2006/main}videoAudioFile", "嵌入媒体"),
        (f"{{{ns_dgm}}}dataModel", "SmartArt 图 (dgm)"),
        (f"{{{ns_dgm}}}relIds", "SmartArt 关联 (dgm relIds)"),
        (f"{{{ns_a}}}m", "复杂 DrawingML MathML"),
        (f"{{{ns_a14}}}m3D", "3D 效果"),
    ]
    seen: set[str] = set()
    for elem in root.iter():
        tag = elem.tag
        for probe, human in checks:
            if tag == probe and human not in seen:
                seen.add(human)
                warnings.append(human)
    return warnings


def _extract_pptx_notes(pptx_path: Path) -> list[dict]:
    """Read speaker notes from a .pptx file. Returns [{slide_index, notes_text}].
    Used by CODEX_REVIEW to feed notes_review skill."""
    try:
        from pptx import Presentation
    except Exception:
        return []
    if not pptx_path.exists():
        return []
    try:
        pres = Presentation(str(pptx_path))
    except Exception:
        return []
    out: list[dict] = []
    for i, slide in enumerate(list(pres.slides), start=1):
        notes = ""
        try:
            if slide.has_notes_slide:
                notes = slide.notes_slide.notes_text_frame.text or ""
        except Exception:
            pass
        out.append({"slide_index": i, "notes_text": notes})
    return out


def _run_codex_review(project_id: str) -> dict:
    """Phase J: codex-based 4-dimension deck reviewer.

    Reads outline / slide-matches / gap-cards / assembly-plan + extracted pptx
    notes, calls 4 codex sub-skills in parallel (reuse / structure / notes /
    narrative), then synthesizes into a final report.

    Writes:
      - projects/<id>/codex-review-report.json
      - projects/<id>/codex-review-report.md
    """
    import concurrent.futures as _cf
    from collections import defaultdict
    from . import codex_cli

    pdir = project_dir(project_id)
    brief = read_json(pdir / "idea-analysis.json", {}) or {}
    outline = read_json(pdir / "outline.json", {}) or {}
    slide_matches_doc = read_json(pdir / "slide-matches.json", {}) or {}
    gap_cards_doc = read_json(pdir / "gap-cards.json", {}) or {}
    assembly_plan = read_json(pdir / "draft-assembly-plan.json", {}) or {}
    raw_layered = read_json(pdir / "raw-layered-candidates.json", {}) or {}

    outline_slides = outline.get("slides") or []
    if not outline_slides:
        return {"ok": False, "stage": "CODEX_REVIEW",
                "error": "outline.json missing or empty"}

    slide_matches = slide_matches_doc.get("slide_matches") or []
    gap_cards = gap_cards_doc.get("gap_cards") or []
    plan_slides = assembly_plan.get("slides") or assembly_plan.get("plan_slides") or []

    # Build source_briefs lookup from raw layered candidates (compact)
    source_briefs: dict[str, dict] = {}
    for s in (raw_layered.get("slide_candidates") or []):
        if not isinstance(s, dict):
            continue
        rid = str(s.get("resource_id") or s.get("object_id") or "")
        if not rid:
            continue
        source_briefs[rid] = {k: s.get(k) for k in
            ("title", "claim", "what_this_slide_explains", "slide_role",
             "transferable_to", "do_not_reuse_when") if s.get(k) is not None}

    # Notes extracted from the rendered pptx
    notes_by_slide = _extract_pptx_notes(pdir / "draft-deck.pptx")

    # ---------- prepare 4 sub-skill contexts ----------
    section_breakdown = outline.get("section_breakdown") or []

    # v30 fix: 加载源页 slide brief 全文 (title + 核心论断 + 本页讲什么 + 关键文字)
    # 作为 source_content_excerpt 供 reuse 维度评审. 之前 codex 只拿到 resource_id
    # 无法验证复用合理性, 直接判 reuse=0.
    #
    # 注意: slide-matches.json schema 里 resource_id 在 candidates[0] (rank-1),
    # 不在顶层. matched_count 也应该按 candidates[0] 算.
    source_content_excerpts: dict[str, dict] = {}
    try:
        from . import library_query as _lq
        _lib_slides = (_lq.load_library_candidates() or {}).get("slide") or []
        _lib_by_rid = {str(c.get("slide_id") or c.get("resource_id") or ""): c
                       for c in _lib_slides if isinstance(c, dict)}
        for m in slide_matches:
            if not isinstance(m, dict):
                continue
            cands = m.get("candidates") or []
            top = cands[0] if cands else {}
            rid = str(top.get("resource_id") or "")
            if not rid or rid in source_content_excerpts:
                continue
            c = _lib_by_rid.get(rid)
            if not c:
                continue
            source_content_excerpts[rid] = {
                "title": c.get("title") or c.get("标题"),
                "claim": c.get("claim") or c.get("核心论断"),
                "what_this_slide_explains": c.get("what_this_slide_explains") or c.get("本页讲什么"),
                "key_texts": (c.get("key_texts") or c.get("关键文字") or [])[:12],
                "visual_skeleton": (c.get("visual_skeleton") or c.get("视觉骨架") or [])[:8],
                "reuse_for": c.get("reuse_for") or c.get("适合复用场景"),
            }
    except Exception as exc:
        print(f"[CODEX_REVIEW] source_content_excerpts load failed: {exc}", flush=True)

    # v30 fix: 从 draft-manuscript.md / speaker-notes.md 里按 slide 切段抽取, 供
    # narrative / notes 维度评审看正文和备注是否对应.
    # 注意: draft-manuscript.md 在 stage 8 (CODEX_REVIEW) 时是 stub, 真正内容由
    # stage 9+ 的 SLIDE_REWRITE 填, 所以 narrative 维度不应基于 manuscript 判分.
    def _split_md_by_slide(md_path) -> dict:
        try:
            if not md_path.exists():
                return {}
        except Exception:
            return {}
        import re
        text = md_path.read_text(encoding="utf-8")
        parts: dict = {}
        # 匹配 "## Slide N" 或 "## Slide N: title" 形式
        blocks = re.split(r"(?m)^##\s+Slide\s+(\d+)", text)
        # blocks: ["preamble", "1", " content1 ", "2", " content2 ", ...]
        for i in range(1, len(blocks) - 1, 2):
            try:
                idx = int(blocks[i])
            except Exception:
                continue
            body = blocks[i + 1].strip()
            # 取前 800 字避免 payload 爆
            parts[idx] = body[:800]
        return parts

    manuscript_by_idx = _split_md_by_slide(pdir / "draft-manuscript.md")
    speaker_notes_by_idx = _split_md_by_slide(pdir / "speaker-notes.md")

    # v30 fix #10: 读 draft-integrity-warnings.json (若存在) 供 structure 维度参考
    _integrity_doc = read_json(pdir / "draft-integrity-warnings.json", None) or {}
    _integrity_warnings = _integrity_doc.get("warnings") or []

    reuse_ctx = {
        "outline_slides": [{k: s.get(k) for k in
            ("slide_index","target_role","target_title","page_purpose",
             "key_points","anchor_terms","section_index")} for s in outline_slides],
        # v30 fix: 从 candidates[0] (rank-1) 拉字段 — slide-matches.json schema
        # 把 resource_id/deck_id/score/confidence/match_reason 放在 candidates[]
        # 里而非顶层, 之前顶层取全 None → codex 判 matched_count=0 → reuse=0
        "slide_matches": [
            (lambda _m, _top: {
                "target_slide_index": _m.get("target_slide_index"),
                "target_role": _m.get("target_role"),
                "target_title": _m.get("target_title"),
                "target_claim": _m.get("target_claim"),
                "resource_id": _top.get("resource_id"),
                "deck_id": _top.get("deck_id"),
                "section_id": _top.get("section_id"),
                "score": _top.get("score"),
                "confidence": _top.get("confidence"),
                "match_reason": (_top.get("match_reasons") or [None])[0],
                "recommended_reuse_mode": _top.get("recommended_reuse_mode"),
            })(m, (m.get("candidates") or [{}])[0])
            for m in slide_matches if isinstance(m, dict)
        ],
        "gap_cards": [{k: g.get(k) for k in
            ("slide_index","source_resource_id","source_title","reuse_fit",
             "must_replace","must_add","narrative_role")} for g in gap_cards
            if isinstance(g, dict)],
        "source_briefs": source_briefs,
        # v30 fix: rank1 源页正文摘录, 让 codex 能真正验证复用合理性
        "source_content_excerpts": source_content_excerpts,
    }
    structure_ctx = {
        "outline_slides": [{k: s.get(k) for k in
            ("slide_index","target_role","target_title","section_index")}
            for s in outline_slides],
        "section_breakdown": section_breakdown,
        "assembly_plan": {"slides": [{k: p.get(k) for k in
            ("slide_index","target_role","source_resource_id","source_owner",
             "draft_action")} for p in plan_slides if isinstance(p, dict)]},
        "brief_must_have_pages": brief.get("must_have_pages") or [],
        # v30 fix #10: 若 draft byte-clone 时含不支持元素 (OLE / SmartArt / 嵌入媒体 /
        # 3D), 视觉可能降级 — 让 codex 结构维度感知这些 slide
        "clone_integrity_warnings": _integrity_warnings,
    }
    # Pair each notes entry with target title/role for context
    title_by_idx = {s.get("slide_index"): s for s in outline_slides if isinstance(s, dict)}
    notes_payload = []
    for n in notes_by_slide:
        idx = n.get("slide_index")
        s = title_by_idx.get(idx, {})
        notes_payload.append({
            "slide_index": idx,
            "target_title": s.get("target_title"),
            "target_role": s.get("target_role"),
            "notes_text": n.get("notes_text") or "",
            # v30 fix: 附上 speaker-notes.md 里对应段落, codex 拿到实际备注全文
            "speaker_notes_excerpt": speaker_notes_by_idx.get(idx, ""),
        })
    notes_ctx = {
        "notes_by_slide": notes_payload,
        "expected_blocks": ["源页来源", "在 PPT 中的位置", "本页讲什么", "为什么放这里",
                            "怎么讲解", "与前后页衔接", "Gap 任务"],
    }
    narrative_ctx = {
        "brief": {"topic": brief.get("topic"), "audience": brief.get("audience"),
                  "narrative_blueprint": brief.get("narrative_blueprint") or {}},
        "outline_slides": [{k: s.get(k) for k in
            ("slide_index","target_role","target_title","target_claim",
             "page_purpose","key_points","section_index")} for s in outline_slides],
        "section_breakdown": section_breakdown,
        # v30 fix: stage 8 (CODEX_REVIEW) 时 draft-manuscript.md 是 stub (只有
        # source_reference / QA/Draft 占位), 真正 on-slide copy 由后续
        # SLIDE_REWRITE stage 填. 送 stub 给 codex 反而拉低 narrative 分.
        # 保留 speaker_notes_by_slide (speaker-notes.md 已有讲稿型内容).
        "speaker_notes_by_slide": speaker_notes_by_idx,
        "manuscript_status": "draft_stub_pre_slide_rewrite",
        "manuscript_note": (
            "draft-manuscript.md 在本 stage 是 stub, 真正 on-slide copy 由 SLIDE_REWRITE "
            "stage 填. narrative 评分应基于 outline_slides + speaker_notes_by_slide + "
            "section_breakdown, 不要因 manuscript 为空扣分."
        ),
        "gap_cards": [{k: g.get(k) for k in
            ("slide_index","narrative_role","what_this_page_says",
             "connects_from_prev","connects_to_next","section_coherence",
             "transition_note")} for g in gap_cards if isinstance(g, dict)],
    }

    dimensions = [
        ("reuse",     "skills/review/reuse_review.md",     reuse_ctx,     900),
        ("structure", "skills/review/structure_review.md", structure_ctx, 600),
        ("notes",     "skills/review/notes_review.md",     notes_ctx,     900),
        ("narrative", "skills/review/narrative_review.md", narrative_ctx, 900),
    ]

    def _run_one_dim(name: str, skill: str, ctx: dict, timeout: int) -> tuple[str, dict]:
        prompt = (f"Review the deck on dimension: **{name}**.\n"
                  "Read the inputs and produce the JSON report per the skill schema.\n\n"
                  "INPUT:\n" + json.dumps(ctx, ensure_ascii=False))
        out = codex_cli.call_codex_json(prompt, skill=[skill], timeout=timeout)
        if not out.get("ok"):
            return name, {"dimension": name, "score": 0, "verdict": "major_rework",
                          "error": out.get("error"), "raw_excerpt": out.get("raw_excerpt")}
        return name, out["data"]

    print(f"[CODEX_REVIEW] launching 4 dimensions in parallel", flush=True)
    dim_results: dict[str, dict] = {}
    with _cf.ThreadPoolExecutor(max_workers=4, thread_name_prefix="review") as pool:
        futs = {pool.submit(_run_one_dim, n, s, c, t): n for n, s, c, t in dimensions}
        for fut in _cf.as_completed(futs):
            n = futs[fut]
            try:
                _, data = fut.result()
                dim_results[n] = data
            except Exception as exc:
                dim_results[n] = {"dimension": n, "score": 0,
                                   "verdict": "major_rework", "error": str(exc)}

    for n in ("reuse","structure","notes","narrative"):
        sc = dim_results.get(n, {}).get("score", 0)
        vd = dim_results.get(n, {}).get("verdict", "?")
        print(f"[CODEX_REVIEW] {n}: score={sc} verdict={vd}", flush=True)

    # ---------- synthesizer ----------
    # v30 fix: matched 从 candidates[0].resource_id 算 (slide-matches.json schema)
    matched = sum(1 for m in slide_matches if isinstance(m, dict)
                   and (m.get("candidates") or [{}])[0].get("resource_id"))
    synth_ctx = {
        "dimensions": dim_results,
        "project_meta": {
            "project_id": project_id,
            "version": project_id.rsplit("_", 1)[-1] if "_" in project_id else "",
            "slide_count": len(outline_slides),
            "matched_count": matched,
            "matched_rate": round(matched / max(1, len(outline_slides)), 3),
        },
    }
    synth_prompt = ("Synthesize the 4-dimension review into a final deck-level "
                    "report per the skill schema.\n\nINPUT:\n"
                    + json.dumps(synth_ctx, ensure_ascii=False))
    print(f"[CODEX_REVIEW] running synthesizer", flush=True)
    synth_out = codex_cli.call_codex_json(synth_prompt,
                                          skill=["skills/review/synthesizer.md"],
                                          timeout=600)
    if synth_out.get("ok"):
        report = synth_out["data"]
    else:
        # Build a deterministic fallback synthesis
        scores = {n: dim_results.get(n, {}).get("score", 0)
                  for n in ("reuse","structure","notes","narrative")}
        avg = round(sum(scores.values()) / 4) if scores else 0
        report = {
            "schema_version": "1.0",
            "project_id": project_id,
            "version": synth_ctx["project_meta"]["version"],
            "scores": {**scores, "visual": None, "overall": avg},
            "verdict": "needs_revision" if avg < 85 else "good",
            "summary_zh": "synthesizer failed; using deterministic average.",
            "synthesizer_error": synth_out.get("error"),
            "critical_issues": [],
            "action_items": [],
            "regression_flags": [],
        }
    report.setdefault("generated_at", now())
    report["dimensions_raw"] = dim_results

    write_json(pdir / "codex-review-report.json", report)

    # Markdown rendering for human reading
    md_lines = [f"# Codex Review — {project_id}", "",
                f"Generated: {report.get('generated_at')}", "",
                "## Scores", ""]
    scores = report.get("scores") or {}
    md_lines.append("| Dimension | Score |")
    md_lines.append("|---|---|")
    for k in ("reuse","structure","notes","narrative","visual","overall"):
        v = scores.get(k)
        md_lines.append(f"| {k} | {'-' if v is None else v} |")
    md_lines.append("")
    md_lines.append(f"**Verdict**: `{report.get('verdict')}`")
    md_lines.append("")
    md_lines.append("## Summary")
    md_lines.append("")
    md_lines.append(report.get("summary_zh") or "(no summary)")
    md_lines.append("")
    md_lines.append("## Critical Issues")
    md_lines.append("")
    for i, issue in enumerate(report.get("critical_issues") or [], start=1):
        md_lines.append(f"{i}. **[{issue.get('severity')}]** "
                        f"({issue.get('dimension', '?')}): {issue.get('issue', '')}")
        if issue.get("slide_indices"):
            md_lines.append(f"   - slides: {issue['slide_indices']}")
        if issue.get("fix_hint"):
            md_lines.append(f"   - fix: {issue['fix_hint']}")
    md_lines.append("")
    md_lines.append("## Action Items")
    md_lines.append("")
    for item in report.get("action_items") or []:
        md_lines.append(f"{item.get('rank', '?')}. {item.get('action', '')} "
                        f"_(owner: {item.get('owner', '?')})_")
    md_lines.append("")
    (pdir / "codex-review-report.md").write_text("\n".join(md_lines), encoding="utf-8")

    return {
        "ok": True,
        "stage": "CODEX_REVIEW",
        "report": str(pdir / "codex-review-report.json"),
        "report_md": str(pdir / "codex-review-report.md"),
        "overall_score": scores.get("overall"),
        "verdict": report.get("verdict"),
        "scores": scores,
    }


def _run_review(project_id: str) -> dict:
    from . import services, stage_models

    pdir = project_dir(project_id)
    quality = services.quality(project_id)
    content_quality = services.content_quality_report(project_id)
    deck_pass = str(quality.get("deck_quality_pass") or "").lower() == "true"
    citation = content_quality.get("citation_quality") or {}
    visual = content_quality.get("visual_fulfillment") or {}
    component = content_quality.get("component_binding") or {}
    footer = content_quality.get("citation_footer") or {}
    depth = content_quality.get("content_depth") or {}
    visual_spec = content_quality.get("visual_spec_quality") or {}
    svg_scan = content_quality.get("svg_visual_scan") or {}
    render_audit = read_json(pdir / "render-audit.json", {})
    source_usage = content_quality.get("source_usage") or {}
    plan_review = content_quality.get("plan_review") or {}
    citation_pass = bool(citation.get("pass", True))
    visual_pass = bool(visual.get("pass", True))
    component_pass = bool(component.get("pass", True))
    footer_pass = bool(footer.get("pass", True))
    depth_pass = bool(depth.get("pass", True))
    visual_spec_pass = bool(visual_spec.get("pass", True))
    claim_pass = bool(depth.get("claim_quality_pass", True))
    text_density_pass = bool(depth.get("text_density_pass", True))
    svg_scan_pass = bool(svg_scan.get("pass", True))
    render_audit_pass = bool(render_audit.get("pass", True))
    source_usage_pass = bool(source_usage.get("pass", True))
    plan_review_pass = bool(plan_review.get("pass", True))

    checks = {
        "structural": {
            "pass": deck_pass,
            "deck_quality_pass": quality.get("deck_quality_pass"),
            "aggregate_editable_ratio": quality.get("aggregate_editable_ratio"),
        },
        "fact_citation": {
            "pass": citation_pass,
            "level": citation.get("level"),
            "missing_reference_slides": citation.get("missing_reference_slides") or [],
        },
        "visual": {"pass": visual_pass, "unmet_slide_ids": visual.get("unmet_slide_ids") or []},
        "visual_spec": {"pass": visual_spec_pass, "gaps": visual_spec.get("gaps") or []},
        "component_binding": {
            "pass": component_pass,
            "missing_or_unbound": component.get("missing_or_unbound") or [],
            "component_counts": component.get("component_counts") or {},
            "component_overuse_gaps": component.get("component_overuse_gaps") or [],
        },
        "citation_footer": {"pass": footer_pass, "missing_footer_slides": footer.get("missing_footer_slides") or []},
        "content_depth": {"pass": depth_pass, "repetition_gaps": depth.get("repetition_gaps") or []},
        "claim_quality": {"pass": claim_pass, "claim_gaps": depth.get("claim_gaps") or []},
        "text_density": {"pass": text_density_pass, "text_density_gaps": depth.get("text_density_gaps") or []},
        "source_usage": {
            "pass": source_usage_pass,
            "source_binding_rate": source_usage.get("source_binding_rate"),
            "unbound_slides": source_usage.get("unbound_slides") or [],
            "local_source_count": source_usage.get("local_source_count"),
            "local_source_used_count": source_usage.get("local_source_used_count"),
        },
        "plan_review": {
            "pass": plan_review_pass,
            "quality_risk": plan_review.get("quality_risk"),
            "duplicate_gaps": plan_review.get("duplicate_gaps") or [],
            "layout_sequence_gaps": plan_review.get("layout_sequence_gaps") or [],
            "format_reference_gaps": plan_review.get("format_reference_gaps") or [],
            "format_decision_counts": plan_review.get("format_decision_counts") or {},
        },
        "svg_visual_scan": {"pass": svg_scan_pass, "issues": svg_scan.get("issues") or []},
        "render_audit": {"pass": render_audit_pass, "issues": render_audit.get("issues") or []},
        "logic": {"pass": True, "blocking_issues": []},
        "duration_density": {"pass": True, "blocking_issues": []},
        "audience_fit": {"pass": True, "blocking_issues": []},
    }

    # W6: incorporate W5 evidence + render-precheck signals.
    rewrite_audit = read_json(pdir / "slide-rewrite-audit.json", {}) or {}
    research_audit = read_json(pdir / "research-audit.json", {}) or {}
    precheck = read_json(pdir / "render-precheck.json", {}) or {}
    entries = rewrite_audit.get("entries") or []
    body_count = max(1, len(entries))
    fact_total = sum(int(e.get("evidence_facts_used") or 0) for e in entries if isinstance(e, dict))
    unsupported_total = sum(int(e.get("unsupported_claims") or 0) for e in entries if isinstance(e, dict))
    evidence_per_slide = fact_total / body_count
    cfg = _config()
    min_evidence = float(cfg.get("min_evidence_per_slide") or 0.5)
    max_unsup = float(cfg.get("max_unsupported_ratio") or 0.5)
    unsup_ratio = unsupported_total / max(1, fact_total + unsupported_total)
    research_failed = str(research_audit.get("source") or "").startswith("stub_after_retry_failed")
    checks["evidence_coverage"] = {
        "pass": research_failed or evidence_per_slide >= min_evidence,
        "evidence_per_slide": round(evidence_per_slide, 3),
        "fact_total": fact_total,
        "min_evidence_per_slide": min_evidence,
        "research_failed_excused": research_failed,
    }
    checks["unsupported_claims"] = {
        "pass": research_failed or unsup_ratio <= max_unsup,
        "unsupported_ratio": round(unsup_ratio, 3),
        "unsupported_total": unsupported_total,
        "max_unsupported_ratio": max_unsup,
        "research_failed_excused": research_failed,
    }
    checks["render_precheck"] = {
        "pass": bool(precheck.get("ok", True)),
        "issues": precheck.get("issues") or [],
        "checks": precheck.get("checks") or {},
    }

    # Reuse-truth check: catches the case where the pipeline ran but the
    # generated deck didn't actually reuse what the audit approved (stub plans,
    # missing source_slide_svg_ref, fallback_reason set, etc). This is what we
    # added to guard against "the deck looks AI-generated, none of my uploads
    # show up" regressions.
    reuse_truth_issues = []
    draft_plan = read_json(pdir / "draft-assembly-plan.json", {}) or {}
    matched_pack = read_json(pdir / "matched-resource-pack.json", {}) or {}
    lineage = read_json(pdir / "draft-source-lineage.json", {}) or {}
    audit_doc = read_json(pdir / "reuse-decision-audit.json", {}) or {}
    approved_ids = set(str(x) for x in (audit_doc.get("approved_resource_ids") or []))
    if str(draft_plan.get("source") or "") == "stub":
        reuse_truth_issues.append(
            f"draft-assembly-plan.json source=stub (fallback_reason={draft_plan.get('fallback_reason')!r})"
        )
    if matched_pack.get("fallback_reason"):
        reuse_truth_issues.append(
            f"matched-resource-pack.json fallback_reason={matched_pack.get('fallback_reason')!r}"
        )
    direct_reuse_slides = [
        s for s in (draft_plan.get("slides") or [])
        if isinstance(s, dict) and str(s.get("draft_action") or "") in {"direct_slide_reuse", "partial_slide_reuse"}
    ]
    for s in direct_reuse_slides:
        rid = str(s.get("source_resource_id") or "")
        if rid and rid not in approved_ids:
            reuse_truth_issues.append(
                f"slide {s.get('slide_index')} draft_action={s.get('draft_action')} cites unapproved resource {rid}"
            )
        if not s.get("source_slide_svg_ref"):
            reuse_truth_issues.append(
                f"slide {s.get('slide_index')} draft_action={s.get('draft_action')} has empty source_slide_svg_ref"
            )
    direct_asset_slides = [
        s for s in (draft_plan.get("slides") or [])
        if isinstance(s, dict) and str(s.get("draft_action") or "") == "direct_asset_reuse"
    ]
    for s in direct_asset_slides:
        if not (s.get("source_asset_refs") or []):
            reuse_truth_issues.append(
                f"slide {s.get('slide_index')} draft_action=direct_asset_reuse has empty source_asset_refs"
            )
    if approved_ids and direct_reuse_slides:
        used_ids = {str(e.get("source_resource_id") or "") for e in (lineage.get("entries") or []) if isinstance(e, dict)}
        if not (approved_ids & used_ids):
            reuse_truth_issues.append(
                "draft-source-lineage records no approved_resource_id; reuse intent did not survive to draft"
            )
    checks["reuse_truth"] = {
        "pass": not reuse_truth_issues,
        "issues": reuse_truth_issues,
        "approved_count": len(approved_ids),
        "direct_reuse_count": len(direct_reuse_slides),
        "direct_asset_count": len(direct_asset_slides),
    }

    verdict = "pass" if all(c["pass"] for c in checks.values()) else "needs_revision"
    issues = [
        {"issue_type": dim, "slide": None, "route_to": _DIMENSION_ROUTE.get(dim, "SLIDE_REWRITE"),
         "problem": f"{dim} check failed", "required_change": f"address {dim} findings"}
        for dim, c in checks.items() if not c["pass"]
    ]
    affected_slides = visual.get("unmet_slide_ids") or []
    source = "stage_runner"

    # Model overlay: a real reviewer (ReviewAgent's 6 review skills are injected) can refine
    # the verdict and surface specific blocking issues with route_to. Falls back to the
    # deterministic structural/citation/visual checks above when no model is available.
    manuscript = (pdir / "manuscript.md")
    base_prompt = (
        "你是 PPT-agent 的演示评审模型。基于上下文（manuscript、结构校验、内容质量）评审这份 deck。"
        "项目规则：正文页标题应是短功能标题，判断句放在标题下方蓝色 assertion/claim box；"
        "不要因为标题是“背景/关键矛盾/技术路线/总结”等短功能标题而判为 visual 问题。"
        "只有 content_quality 中存在明确 unmet_slide_ids/gaps，或页面缺少 assertion/claim 支撑时，才报告视觉问题。"
        "只输出 JSON：{\"verdict\":\"pass|needs_revision\",\"issues\":[{\"issue_type\":\"structural|"
        "fact_citation|visual|visual_spec|component_binding|citation_footer|content_depth|source_usage|plan_review|"
        "logic|duration_density|audience_fit|render_audit\",\"slide\":页码或null,"
        "\"route_to\":\"RENDER|GAP_RESEARCH|SLIDE_REWRITE|STYLE_UNIFICATION|DRAFT_ASSEMBLY|GAP_ANALYSIS|REUSE_OUTLINE\",\"problem\":\"...\","
        "\"required_change\":\"...\"}]}。verdict=pass 时 issues 为空。不要输出解释。"
    )
    model = stage_models.generate_artifact(
        project_id, "REVIEW", base_prompt,
        context={
            "structural_validation": _fm_dict(pdir / "structural-validation.md"),
            "content_quality": content_quality,
            "manuscript_excerpt": manuscript.read_text(encoding="utf-8")[:4000] if manuscript.exists() else "",
        },
        parse="json",
    )
    if model.get("ok"):
        data = model["data"]
        mv = str(data.get("verdict") or "").lower()
        if mv in {"pass", "needs_revision"}:
            model_issues = _normalize_review_issues(data.get("issues"))
            # Trust a needs_revision verdict; only trust pass if deterministic gates also pass.
            if mv == "needs_revision":
                verdict = "needs_revision"
                deterministic_issue_types = {issue.get("issue_type") for issue in issues}
                filtered_model_issues = []
                for issue in model_issues:
                    if (
                        issue.get("issue_type") == "visual"
                        and not (visual.get("unmet_slide_ids") or [])
                        and not deterministic_issue_types.intersection({"visual", "visual_spec"})
                    ):
                        continue
                    filtered_model_issues.append(issue)
                issues = filtered_model_issues or issues
            elif verdict == "pass":
                verdict = "pass"
                issues = []
            source = model.get("provider") or "model"

    route_candidates = [i["route_to"] for i in issues if i.get("route_to")]
    rollback_stage = _select_earliest_upstream("REVIEW", route_candidates) if verdict != "pass" else None
    report = {
        "schema_version": "1.0",
        "generated_at": now(),
        "source": source,
        "verdict": verdict,
        "quality": quality,
        "checks": checks,
        "issues": issues,
        "route_candidates": route_candidates,
        "rollback_stage": rollback_stage,
        "affected_slides": affected_slides,
    }
    write_json(pdir / "review-report.json", report)
    deck_review = [
        "---",
        'schema_version: "1.0"',
        f'generated_at: "{now()}"',
        f'verdict: "{verdict}"',
        f'reviewer: "{source}"',
        "---",
        "# Deck Review",
        "",
        f"- Verdict: {verdict}",
        f"- Structural pass: {deck_pass}",
        f"- Citation pass: {citation_pass}",
        f"- Visual pass: {visual_pass}",
        f"- Blocking issues: {len(issues)}",
        f"- Suggested rollback: {rollback_stage or 'none'}",
        "",
    ]
    for issue in issues:
        deck_review.append(f"  - [{issue['issue_type']} -> {issue.get('route_to')}] {issue.get('problem')}")
    (pdir / "deck-review.md").write_text("\n".join(deck_review) + "\n", encoding="utf-8")
    return report


def _run_render_precheck(project_id: str) -> dict:
    """W6: deterministic 6-check audit before RENDER."""
    from pathlib import Path

    pdir = project_dir(project_id)
    visual = read_json(pdir / "visual-plan.json", {}) or {}
    template_binding = read_json(pdir / "template-binding.json", {}) or {}
    citations_doc = read_json(pdir / "citations.json", {}) or {}
    manuscript_path = pdir / "manuscript.md"
    manuscript_text = manuscript_path.read_text(encoding="utf-8", errors="ignore") if manuscript_path.exists() else ""

    visual_slides = visual.get("slides") if isinstance(visual.get("slides"), list) else []
    citations_index = {str(c.get("id")): c for c in (citations_doc.get("citations") or []) if isinstance(c, dict) and c.get("id")}

    issues = []

    # 1. no_empty_pages
    no_empty_pages = bool(visual_slides) and all(
        isinstance(s, dict) and (s.get("assertion_title") or s.get("assets") or s.get("content_blocks") or s.get("evidence_facts"))
        for s in visual_slides
    )
    if not no_empty_pages:
        for s in visual_slides or []:
            if isinstance(s, dict) and not (s.get("assertion_title") or s.get("assets") or s.get("content_blocks") or s.get("evidence_facts")):
                issues.append({"kind": "empty_page", "slide_index": s.get("slide_index"), "detail": "page lacks title and content"})

    # 2. copy_within_budget — heuristic on manuscript text length per slide
    copy_within_budget = True
    slide_blocks = re.split(r"^## Slide \d+:", manuscript_text, flags=re.MULTILINE)
    for i, block in enumerate(slide_blocks[1:], start=1):
        # rough budget: 1800 chars per body slide (cover/closing skipped via i match below)
        budget = 1200
        if len(block.strip()) > budget * 1.5:
            copy_within_budget = False
            issues.append({"kind": "copy_overflow", "slide_index": i,
                           "detail": f"manuscript block ~{len(block)} chars exceeds {int(budget*1.5)}"})

    # 3. all_visual_specs_present
    all_visual_specs = all(
        isinstance(s, dict) and (s.get("visual_spec") or s.get("layout_type") or s.get("visual_type"))
        for s in visual_slides
    )
    if not all_visual_specs:
        for s in visual_slides:
            if isinstance(s, dict) and not (s.get("visual_spec") or s.get("layout_type") or s.get("visual_type")):
                issues.append({"kind": "missing_visual_spec", "slide_index": s.get("slide_index"), "detail": "no visual_spec/layout_type/visual_type"})

    # 4. all_bound_assets_exist_on_disk
    all_assets_exist = True
    for s in visual_slides:
        if not isinstance(s, dict):
            continue
        for asset in s.get("assets") or []:
            if not isinstance(asset, dict):
                continue
            rel = str(asset.get("local_path") or asset.get("path") or "").strip()
            if not rel:
                continue
            if rel.startswith("/"):
                p = Path(rel)
            elif rel.startswith("data/"):
                p = ROOT / rel
            else:
                p = pdir / rel
            if not p.exists():
                # also try ROOT as fallback
                if not (ROOT / rel).exists():
                    all_assets_exist = False
                    issues.append({"kind": "missing_asset_file", "slide_index": s.get("slide_index"), "detail": rel})

    # 5. citations_closed_loop
    cited_ids = set(re.findall(r"\[cite:([A-Za-z0-9_]+)\]", manuscript_text))
    cited_ids.discard("unsourced")
    citations_closed = True
    dangling_in_text = sorted(cited_ids - set(citations_index.keys()))
    for cid in dangling_in_text:
        citations_closed = False
        issues.append({"kind": "dangling_citation", "slide_index": None, "detail": f"manuscript cites {cid} but citations.json has no such id"})

    # 6. template_binding_usable
    tb_usable = bool(template_binding) and bool(
        template_binding.get("template_id") or template_binding.get("style_profile") or template_binding.get("layouts")
    )
    if not tb_usable:
        issues.append({"kind": "template_layout_missing", "slide_index": None, "detail": "template-binding.json missing required fields"})

    checks = {
        "no_empty_pages": no_empty_pages,
        "copy_within_budget": copy_within_budget,
        "all_visual_specs_present": all_visual_specs,
        "all_bound_assets_exist_on_disk": all_assets_exist,
        "citations_closed_loop": citations_closed,
        "template_binding_usable": tb_usable,
    }
    ok = all(checks.values())
    artifact = {
        "schema_version": "1.0",
        "generated_at": now(),
        "project_id": project_id,
        "source": "deterministic",
        "ok": ok,
        "checks": checks,
        "issues": issues,
        "recommended_action": "proceed" if ok else "fix_and_rerun",
    }
    write_json(pdir / "render-precheck.json", artifact)
    return {"ok": True, "stage": "RENDER_PRECHECK",
            "render_precheck": str(pdir / "render-precheck.json"),
            "precheck_ok": ok,
            "issue_count": len(issues),
            "source": "deterministic"}


def _run_revision_decision(project_id: str) -> dict:
    pdir = project_dir(project_id)
    report = read_json(pdir / "review-report.json", {})
    verdict = report.get("verdict") or "needs_revision"
    if verdict == "pass":
        plan = {
            "schema_version": "1.0",
            "generated_at": now(),
            "source": "stage_runner",
            "revision_type": "NONE",
            "problem": "No blocking review issues.",
            "rollback_stage": None,
            "affected_slides": [],
            "suggested_action": "Proceed to final user acceptance.",
        }
    else:
        candidates = list(report.get("route_candidates") or [])
        if report.get("rollback_stage"):
            candidates.append(report["rollback_stage"])
        rollback = _select_earliest_upstream("REVIEW", candidates) or "SLIDE_REWRITE"
        # W6 policy: GAP_* failures must NOT trigger rollback. Log the request and
        # downgrade to a forward-only revision targeting SLIDE_REWRITE so the model
        # at least re-emits manuscript with current evidence_pack (which already
        # marks unsupported_claims). The GAP-fail-log carries the audit trail.
        gap_targets = {"GAP_RESEARCH", "GAP_SYNTHESIS", "GAP_ANALYSIS"}
        downgraded = False
        if rollback in gap_targets:
            _append_gap_log(project_id, "REVISION_DECISION_DOWNGRADED", {
                "error": f"review wanted rollback to {rollback}; policy forbids GAP_* rollback — downgraded to SLIDE_REWRITE",
            }, attempts=0)
            rollback = "SLIDE_REWRITE"
            downgraded = True
        issues = report.get("issues") or []
        problem = "; ".join(i.get("problem") for i in issues if i.get("problem")) or "Review found blocking issues."
        plan = {
            "schema_version": "1.0",
            "generated_at": now(),
            "source": "stage_runner",
            "revision_type": "P4",
            "problem": problem,
            "rollback_stage": rollback,
            "route_candidates": candidates,
            "issues": issues,
            "affected_slides": report.get("affected_slides") or [],
            "gap_rollback_downgraded": downgraded,
            "suggested_action": (
                f"Roll back to {rollback}, apply required changes, regenerate, then rerun review."
                + (" (Downgraded from GAP_* per policy: GAP failures do not roll back.)" if downgraded else "")
            ),
        }
    write_json(pdir / "revision-plan.json", plan)
    return plan


def _is_true(value) -> bool:
    return str(value).strip().lower() == "true"


def _run_ppt_eval(project_id: str) -> dict:
    """PPT_EVAL — text-only 3-dimension evaluation (adapted from icip-cas/PPTAgent).

    Evaluates the final rendered deck.pptx across:
      - content (per-slide text quality, 5-pt scale)
      - logic (whole-deck coherence, 5-pt scale)
      - constraint (slide_count / aspect_ratio / language, pass/fail 0-1)
    Style dimension is a placeholder until libreoffice is available (needs
    pptx→PNG rendering for VLM inspection).

    Writes:
      projects/<id>/eval-report.json
      projects/<id>/eval-summary.md
    """
    from . import claude_cli, ppt_eval

    pdir = project_dir(project_id)
    # Prefer final deck.pptx from RENDER stage; fall back to revised-draft
    candidates = [pdir / "deck.pptx", pdir / "final-shell-deck.pptx",
                  pdir / "revised-draft-deck.pptx", pdir / "draft-deck.pptx"]
    pptx_path = next((p for p in candidates if p.exists()), None)
    if not pptx_path:
        return {"ok": False, "stage": "PPT_EVAL",
                "error": "no deck.pptx or revised-draft-deck.pptx found"}

    # Project config from idea-intake-light (structured) with fallback to
    # question-state.answers for legacy projects.
    intake = read_json(pdir / "idea-intake-light.json", {}) or {}
    project_config = {
        "slide_count": (intake.get("scenario") or {}).get("slide_count"),
        "language": "zh",  # default; refined below
    }
    # heuristic language detection from intake
    subject = (intake.get("topic") or {}).get("subject") or ""
    if subject and not any("一" <= c <= "鿿" for c in subject):
        project_config["language"] = "en"

    print(f"[PPT_EVAL] evaluating {pptx_path.name} "
          f"(expected slide_count={project_config['slide_count']}, "
          f"language={project_config['language']})", flush=True)

    import time
    t0 = time.time()
    try:
        report = ppt_eval.evaluate_deck(pptx_path, project_config, claude_cli)
    except Exception as exc:
        return {"ok": False, "stage": "PPT_EVAL",
                "error": f"evaluate_deck failed: {exc}"}

    write_json(pdir / "eval-report.json", report)
    summary_md = ppt_eval.render_summary_md(report)
    (pdir / "eval-summary.md").write_text(summary_md, encoding="utf-8")

    agg = report.get("aggregate", {})
    print(f"[PPT_EVAL] done in {time.time()-t0:.1f}s: "
          f"content_avg={agg.get('content_avg')}, "
          f"logic={agg.get('logic_score')}, "
          f"constraint={agg.get('constraint_score')}, "
          f"overall={agg.get('overall')}",
          flush=True)

    return {
        "ok": True,
        "stage": "PPT_EVAL",
        "input_pptx": str(pptx_path),
        "eval_report": str(pdir / "eval-report.json"),
        "eval_summary": str(pdir / "eval-summary.md"),
        "aggregate": agg,
    }


def _run_final_accept(project_id: str) -> dict:
    """Enforce the deck-quality acceptance gate (CLAUDE.md): a deck is accepted only when
    it passed structural validation as a real, sufficiently-editable render with speaker
    notes / transitions / assets intact. Otherwise it is rejected and routed back."""
    from . import services

    pdir = project_dir(project_id)
    quality = services.quality(project_id)
    min_ratio = float(_config().get("min_editable_ratio") or 0.8)
    try:
        ratio = float(quality.get("aggregate_editable_ratio") or 0.0)
    except (TypeError, ValueError):
        ratio = 0.0

    checks = {
        "deck_present": bool(quality.get("deck_path")),
        "deck_quality_pass": _is_true(quality.get("deck_quality_pass")),
        "render_mode_real": str(quality.get("render_mode")) == "real",
        "editable_ratio_ok": ratio >= min_ratio,
        # optional signals: only fail when explicitly false
        "speaker_notes_ok": quality.get("speaker_notes_ok") is None or _is_true(quality.get("speaker_notes_ok")),
        "transitions_ok": quality.get("transitions_ok") is None or _is_true(quality.get("transitions_ok")),
        "assets_ok": quality.get("assets_ok") is None or _is_true(quality.get("assets_ok")),
    }

    # W6: evidence coverage thresholds — accept only if SLIDE_REWRITE consumed
    # enough evidence and didn't leave too many unsupported claims.
    rewrite_audit = read_json(pdir / "slide-rewrite-audit.json", {}) or {}
    research_audit = read_json(pdir / "research-audit.json", {}) or {}
    entries = rewrite_audit.get("entries") or []
    body_entries = [e for e in entries if isinstance(e, dict) and e.get("evidence_facts_used") is not None]
    body_count = max(1, len(body_entries))
    fact_total = sum(int(e.get("evidence_facts_used") or 0) for e in body_entries)
    unsupported_total = sum(int(e.get("unsupported_claims") or 0) for e in body_entries)
    cfg = _config()
    min_evidence_per_slide = float(cfg.get("min_evidence_per_slide") or 0.5)
    max_unsupported_ratio = float(cfg.get("max_unsupported_ratio") or 0.5)
    evidence_per_slide = fact_total / body_count
    unsupported_ratio = unsupported_total / max(1, fact_total + unsupported_total)
    evidence_signal = {
        "fact_total": fact_total,
        "unsupported_total": unsupported_total,
        "evidence_per_slide": round(evidence_per_slide, 3),
        "unsupported_ratio": round(unsupported_ratio, 3),
        "min_evidence_per_slide": min_evidence_per_slide,
        "max_unsupported_ratio": max_unsupported_ratio,
        "research_audit_source": research_audit.get("source"),
    }
    checks["evidence_coverage_ok"] = evidence_per_slide >= min_evidence_per_slide
    checks["unsupported_ratio_ok"] = unsupported_ratio <= max_unsupported_ratio

    failed = [name for name, ok in checks.items() if not ok]
    accepted = not failed

    rollback_stage = None
    if not accepted:
        # If only evidence-coverage thresholds failed, do NOT roll back to GAP_*
        # (per policy). Surface the warning in the report instead.
        evidence_only_failures = set(failed) <= {"evidence_coverage_ok", "unsupported_ratio_ok"}
        if evidence_only_failures:
            rollback_stage = None
            accepted = True  # accept with warnings
        else:
            rollback_stage = "RENDER"

    report = {
        "schema_version": "1.0",
        "generated_at": now(),
        "source": "stage_runner",
        "acceptance_status": "ready_for_user_acceptance" if accepted else "rejected",
        "deck": "deck.pptx" if quality.get("deck_path") else None,
        "quality": quality,
        "checks": checks,
        "failed_checks": failed,
        "min_editable_ratio": min_ratio,
        "aggregate_editable_ratio": ratio,
        "evidence_signal": evidence_signal,
        "warnings": [f"check_failed_with_warning: {name}" for name in failed if name in {"evidence_coverage_ok", "unsupported_ratio_ok"}],
        "rollback_stage": rollback_stage,
    }
    write_json(pdir / "final-report.json", report)
    return report


def _validate_artifact(kind: str, path) -> None:
    subprocess.run(
        ["bash", str(ROOT / "scripts/validate-artifact.sh"), kind, str(path)],
        cwd=ROOT,
        check=True,
        stdout=subprocess.DEVNULL,
    )


def _validate_ok(kind: str, path) -> bool:
    return subprocess.run(
        ["bash", str(ROOT / "scripts/validate-artifact.sh"), kind, str(path)],
        cwd=ROOT, capture_output=True, text=True,
    ).returncode == 0


def _ensure_template_profile(project_id: str, template: str | None = None) -> dict:
    pdir = project_dir(project_id)
    path = pdir / "template-profile.json"
    existing = read_json(path, {}) if path.exists() else {}
    needs_refresh = not path.exists() or not existing.get("source_slide_catalog") or not existing.get("layout_catalog")
    if needs_refresh:
        cmd = [
            "python3",
            str(ROOT / "scripts/lib/template_profile.py"),
            "--project-dir",
            str(pdir),
            "--out",
            str(path),
        ]
        if template:
            cmd.extend(["--template", template])
        subprocess.run(cmd, cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    profile = read_json(path, {})
    lab_contract = profile.get("lab_template_contract") if isinstance(profile.get("lab_template_contract"), dict) else {}
    title_rule = lab_contract.get("title_rule") if isinstance(lab_contract.get("title_rule"), dict) else {}
    rule_blue = str(title_rule.get("line_color") or "#074BA2").strip()
    if isinstance(profile, dict) and lab_contract:
        palette = dict(profile.get("palette") or {})
        palette.update({
            "primary": rule_blue,
            "secondary": rule_blue,
            "accent": "#B52436",
            "neutral": "#EEF4FA",
            "text": "#111827",
        })
        profile["palette"] = palette
        profile["style_contract"] = {
            **(profile.get("style_contract") if isinstance(profile.get("style_contract"), dict) else {}),
            "fixed_shell": ["cover", "agenda", "ending", "title_rule", "footer", "page_number", "typography"],
            "primary_color_source": "DAI title_rule.line_color",
            "accent_color": "#B52436",
            "content_policy": "middle content area is model-planned; shell furniture is fixed",
        }
        write_json(path, profile)
    _ensure_template_components(project_id, profile)
    return profile


def _ensure_template_components(project_id: str, profile: dict | None = None) -> dict:
    pdir = project_dir(project_id)
    profile = profile or read_json(pdir / "template-profile.json", {})
    if not isinstance(profile, dict) or not profile:
        return {}
    canvas = profile.get("canvas") or {"width_px": 1280.0, "height_px": 720.0}
    w = float(canvas.get("width_px") or 1280.0)
    h = float(canvas.get("height_px") or 720.0)
    layouts = profile.get("page_type_layouts") or {}
    content = layouts.get("content") or layouts.get("chapter") or {}
    title = content.get("title_region") or {"x": 80, "y": 24, "width": w - 160, "height": 72}
    body = content.get("body_region") or {"x": 60, "y": 120, "width": w - 120, "height": h - 190}
    bx, by, bw, bh = float(body["x"]), float(body["y"]), float(body["width"]), float(body["height"])
    gap = 34.0
    claim_h = 54.0
    footer_h = 34.0
    box_y = by + claim_h + 34.0
    box_h = max(160.0, bh - claim_h - footer_h - 64.0)
    box_w = (bw - gap) / 2.0
    components = [
        {
            "component_id": "evidence_two_box.v1",
            "name": "标题-依据句-左右双框-页脚引用",
            "page_type": "content",
            "purpose": "technical evidence page with one claim and two analytical panels",
            "slots": {
                "title": title,
                "claim": {"x": bx, "y": by, "width": bw, "height": claim_h},
                "left_box": {"x": bx, "y": box_y, "width": box_w, "height": box_h},
                "right_box": {"x": bx + box_w + gap, "y": box_y, "width": box_w, "height": box_h},
                "footer_citation": {"x": bx, "y": h - 52.0, "width": bw * 0.78, "height": footer_h},
                "page_number": {"x": bx + bw * 0.82, "y": h - 52.0, "width": bw * 0.18, "height": footer_h},
            },
            "source": "template_profile_plus_agent_slots",
            "requires_user_review": True,
        },
        {
            "component_id": "cover_title_image.v1",
            "name": "封面标题与视觉区",
            "page_type": "cover",
            "purpose": "opening page with title, short framing copy, and optional image",
            "slots": (layouts.get("cover") or {}).get("layout_slots") or {},
            "source": "template_profile",
            "requires_user_review": False,
        },
    ]
    lab_contract = profile.get("lab_template_contract") if isinstance(profile.get("lab_template_contract"), dict) else {}
    if lab_contract:
        components.append({
            "component_id": "dai_lab_footer.v1",
            "name": "DAI实验室可编辑页脚与页码",
            "page_type": "all",
            "purpose": "required lab footer; speaker name is editable while affiliation and page-number rhythm follow the base template",
            "slots": {
                "speaker_footer": lab_contract.get("footer_region") or {},
                "page_number": lab_contract.get("page_number_region") or {},
            },
            "source": "global_base_template_contract",
            "editable_fields": ["speaker_name"],
            "default_values": {
                "speaker_name": lab_contract.get("speaker_name") or "xxx",
                "speaker_affiliation": lab_contract.get("speaker_affiliation") or "Shanghai Jiao Tong University",
                "speaker_email": lab_contract.get("speaker_email") or "xxx@shanghai jiaotong",
            },
            "requires_user_review": False,
        })
        components.append({
            "component_id": "dai_lab_title_rule.v1",
            "name": "DAI实验室标题蓝线规则",
            "page_type": "content",
            "purpose": "place each slide title above the blue horizontal rule according to the lab base template",
            "slots": {
                "title": (lab_contract.get("title_rule") or {}).get("title_region") or title,
                "title_rule": lab_contract.get("title_rule") or {},
            },
            "source": "global_base_template_contract",
            "requires_user_review": False,
        })
        for key, component_id, name, page_type in [
            ("cover_reuse", "dai_lab_cover.v1", "DAI实验室封面底板", "cover"),
            ("ending_reuse", "dai_lab_ending.v1", "DAI实验室结束页底板", "ending"),
        ]:
            reuse = lab_contract.get(key) if isinstance(lab_contract.get(key), dict) else {}
            if reuse:
                components.append({
                    "component_id": component_id,
                    "name": name,
                    "page_type": page_type,
                    "purpose": reuse.get("reason") or "required lab base template page",
                    "slots": (layouts.get(page_type) or {}).get("layout_slots") or {},
                    "source": "global_base_template_contract",
                    "template_svg": reuse.get("template_svg"),
                    "copy_assets": bool(reuse.get("copy_assets")),
                    "requires_user_review": False,
                })
    structured_slots = {
        "title": title,
        "claim": {"x": bx, "y": by, "width": bw, "height": claim_h},
        "body": {"x": bx, "y": box_y, "width": bw, "height": box_h},
        "footer_citation": {"x": bx, "y": h - 52.0, "width": bw * 0.78, "height": footer_h},
        "page_number": {"x": bx + bw * 0.82, "y": h - 52.0, "width": bw * 0.18, "height": footer_h},
    }
    for component_id, name, purpose in [
        ("timeline_3_stage.v1", "三阶段时间线", "section page with editable timeline stages"),
        ("editable_chart_or_table.v1", "可编辑证据图表/表格", "evidence page with native editable chart or table"),
        ("editable_matrix_table.v1", "可编辑对照矩阵", "comparison page with native editable matrix table"),
        ("editable_flow_diagram.v1", "可编辑流程图", "mechanism page with native editable flow diagram"),
        ("editable_layered_architecture.v1", "可编辑分层架构图", "architecture page with native editable layered diagram"),
        ("editable_step_roadmap.v1", "可编辑阶梯路线图", "roadmap page with editable staged roadmap"),
        ("editable_risk_table.v1", "可编辑风险边界表", "risk page with editable risk-boundary-mitigation table"),
        ("problem_framing.v1", "问题框定页", "problem page with claim plus editable problem framing"),
        ("closing_summary.v1", "总结建议页", "closing page with concise editable summary and actions"),
    ]:
        components.append({
            "component_id": component_id,
            "name": name,
            "page_type": "content",
            "purpose": purpose,
            "slots": structured_slots,
            "source": "template_profile_plus_agent_slots",
            "requires_user_review": component_id == "problem_framing.v1",
        })
    for source in profile.get("source_slide_catalog") or []:
        if not isinstance(source, dict):
            continue
        idx = int(source.get("index") or 0)
        if idx <= 0:
            continue
        role = str(source.get("role") or "content")
        samples = [str(x).strip() for x in (source.get("text_samples") or []) if str(x).strip()]
        image_assets = source.get("image_assets") or []
        slots = dict((layouts.get(role) or layouts.get("content") or {}).get("layout_slots") or {})
        if image_assets and "image" not in slots:
            slots["image"] = {
                "x": w * 0.56,
                "y": h * 0.22,
                "width": w * 0.34,
                "height": h * 0.48,
                "source": "inferred_from_source_slide_image_assets",
            }
        components.append({
            "component_id": f"ppt_master_source_slide_{idx:02d}.v1",
            "name": f"模板源页 {idx:02d} / {role}",
            "page_type": role,
            "purpose": "ppt-master imported source slide exemplar for reusable layout/style",
            "slots": slots,
            "source": "ppt_master_source_slide_catalog",
            "source_slide_index": idx,
            "template_svg": source.get("template_svg"),
            "layered_svg": source.get("layered_svg"),
            "shape_count": source.get("shape_count"),
            "text_count": source.get("text_count"),
            "image_slots": [
                {
                    "asset": str(asset),
                    "slot_role": "content_image_slot",
                    "reuse_policy": "slot_only_do_not_copy_original_image",
                }
                for asset in image_assets
            ],
            "text_samples": samples[:6],
            "requires_user_review": True,
        })
    paper_share_index = read_json(ROOT / "config/paper_share_components.json", {})
    if isinstance(paper_share_index, dict):
        role_limits = {
            "agenda_or_section_agenda": 12,
            "image_evidence_dense": 12,
            "image_evidence": 12,
            "diagram_dense": 6,
            "content": 10,
            "ending_reference": 2,
        }
        used: dict[str, int] = {}
        for item in paper_share_index.get("components") or []:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "content")
            limit = role_limits.get(role, 0)
            if limit <= 0 or used.get(role, 0) >= limit:
                continue
            used[role] = used.get(role, 0) + 1
            components.append({
                "component_id": str(item.get("component_id") or f"paper_share.{role}.{used[role]}"),
                "name": f"paper-share {role} reference {used[role]}",
                "page_type": "content" if role not in {"cover_reference", "ending_reference"} else role.replace("_reference", ""),
                "purpose": item.get("blueprint") or "research talk style/composition reference",
                "slots": {},
                "source": "templates/topic/paper share",
                "template_svg": item.get("template_svg"),
                "source_slide_index": item.get("slide_index"),
                "paper_share_role": role,
                "image_count": item.get("image_count"),
                "shape_count": item.get("shape_count"),
                "text_count": item.get("text_count"),
                "text_samples": (item.get("text_samples") or [])[:8],
                "reuse_level": "layout_family",
                "reuse_policy": "style_and_composition_only",
                "copy_assets": False,
                "requires_user_review": False,
            })
    payload = {
        "schema_version": "1.0",
        "generated_at": now(),
        "source": "stage_runner",
        "template_id": profile.get("template_id"),
        "template_name": profile.get("name"),
        "template_scope": profile.get("template_scope"),
        "base_template": bool(profile.get("base_template")),
        "lab_template_contract": lab_contract,
        "components": components,
        "review_instructions": "Review source-slide components before final render; image assets are treated as slots unless explicitly approved.",
        "review_status": "needs_user_review",
    }
    write_json(pdir / "template-components.json", payload)
    return payload


def _validate_reuse_first_render_inputs(project_id: str) -> dict:
    pdir = project_dir(project_id)
    plan = read_json(pdir / "model-routed-plan.json", {})
    visual = read_json(pdir / "visual-plan.json", {})
    slides = plan.get("slides") if isinstance(plan, dict) else []
    visual_slides = visual.get("slides") if isinstance(visual, dict) else []
    if not isinstance(slides, list) or not isinstance(visual_slides, list) or not slides:
        return {"ok": False, "changed": False, "reason": "missing plan or visual-plan"}
    visual_by_idx = {
        int(item.get("slide_index") or 0): item
        for item in visual_slides
        if isinstance(item, dict) and str(item.get("slide_index") or "").isdigit()
    }
    gaps = []
    for idx, slide in enumerate(slides, start=1):
        item = visual_by_idx.get(idx) or {}
        if not item:
            gaps.append({"slide_index": idx, "field": "visual_plan", "reason": "missing slide visual plan"})
            continue
        required_spec = layout_registry.requires_visual_spec_for_slide(slide, slide_index=idx, slide_count=len(slides))
        spec = item.get("visual_spec") if isinstance(item.get("visual_spec"), dict) else {}
        if required_spec and not layout_registry.visual_spec_is_usable(spec):
            gaps.append({"slide_index": idx, "field": "visual_spec", "reason": "missing usable V2 visual_spec"})
        content_blocks = item.get("content_blocks") if isinstance(item.get("content_blocks"), list) else []
        page_role = str(slide.get("story_role") or "").lower()
        title = str(slide.get("title") or "").strip()
        lightweight = idx in {1, len(slides)} or page_role in {"cover", "summary", "section"} or (idx == 2 and title in {"目录", "汇报结构", "Agenda"})
        usable_blocks = [
            b for b in content_blocks
            if isinstance(b, dict) and (str(b.get("heading") or "").strip() or b.get("body"))
        ]
        if not lightweight and len(usable_blocks) < 3:
            gaps.append({"slide_index": idx, "field": "content_blocks", "reason": "technical slide needs at least 3 content blocks"})
        composition = item.get("slide_composition") if isinstance(item.get("slide_composition"), dict) else {}
        if not composition.get("primary_visual_role"):
            gaps.append({"slide_index": idx, "field": "slide_composition", "reason": "missing V2 slide composition"})
        elif not lightweight and not composition.get("claim_to_prove"):
            gaps.append({"slide_index": idx, "field": "slide_composition", "reason": "missing V2 composition claim"})
    return {
        "ok": not gaps,
        "changed": False,
        "gaps": gaps,
        "message": "Render preflight validates reuse-first V2 artifacts only. Automatic repair fallback is disabled.",
    }








def _run_render(project_id: str, payload: dict) -> dict:
    """Render the deck directly from the artifacts the App stages already produced
    (manuscript.md + visual-plan.json + style-guide.md + template-profile.json), via the
    export-pptx adapter. Legacy topic-to-deck generation is not used as fallback."""
    from . import services

    payload = payload or {}
    pdir = project_dir(project_id)
    if not (pdir / "manuscript.md").exists():
        return {
            "ok": False,
            "source": "app_artifacts",
            "error": "manuscript.md missing",
            "message": "Run SLIDE_REWRITE before RENDER. Legacy full-pipeline generation is not used as a render fallback.",
        }

    _ensure_template_profile(project_id, payload.get("template") or _answers(project_id).get("template"))
    # Draft pass uses full-copy-first reuse — the SLIDE_REWRITE-era fields
    # (slide_composition, etc.) aren't authored yet because the source slide
    # is pasted verbatim. Skip the preflight that gates those fields.
    if not bool(payload.get("draft")):
        preflight = _validate_reuse_first_render_inputs(project_id)
        if not preflight.get("ok", False):
            return {
                "ok": False,
                "source": "app_artifacts",
                "error": "render preflight failed",
                "message": preflight.get("message") or "Model-authored plan/visual artifacts are incomplete.",
                "gaps": preflight.get("gaps") or [],
            }
    cfg = _config()
    backend = str(cfg.get("render_backend") or "native-svg")
    primary_backend = str(cfg.get("render_primary_backend") or "ppt-master-free")
    primary_timeout = int(cfg.get("render_primary_timeout_seconds") or 3600)

    def _sh(args: list[str], *, timeout: int | None = None):
        return subprocess.run(["bash", *args], cwd=ROOT, capture_output=True, text=True, timeout=timeout)

    # Data-derived charts only when a non-empty chart-spec exists (best effort).
    chart_spec = read_json(pdir / "chart-spec.json", {})
    if isinstance(chart_spec, dict) and chart_spec.get("charts"):
        _sh([str(ROOT / "scripts/gen-charts.sh"), str(pdir)])

    render_backend = primary_backend
    render_fallback_used = False
    render_fallback_reason = None
    render_started = time.time()
    try:
        render = _sh(
            [str(ROOT / "scripts/export-pptx.sh"), "render", str(pdir), "--backend", primary_backend],
            timeout=primary_timeout,
        )
    except subprocess.TimeoutExpired as exc:
        render_fallback_reason = f"primary render timed out after {primary_timeout}s; V2 does not fall back to another render path"
        render = subprocess.CompletedProcess(exc.cmd, 124, stdout=exc.stdout or "", stderr=render_fallback_reason)
    validate = _sh([str(ROOT / "scripts/export-pptx.sh"), "validate", str(pdir), "--backend", render_backend])

    _sh([str(ROOT / "scripts/sync-metadata.sh"), str(pdir)])  # best effort: run-manifest.json

    quality = services.quality(project_id)
    render_audit = services.render_audit(project_id)
    ok = render.returncode == 0 and validate.returncode == 0 and (pdir / "deck.pptx").exists()
    if ok and not render_audit.get("pass", True):
        ok = False
    return {
        "ok": ok,
        "source": "app_artifacts",
        "backend": render_backend,
        "primary_backend": primary_backend,
        "fallback_backend": backend,
        "render_fallback_used": render_fallback_used,
        "render_fallback_reason": render_fallback_reason,
        "render_elapsed_seconds": round(time.time() - render_started, 2),
        "render_returncode": render.returncode,
        "validate_returncode": validate.returncode,
        "quality": quality,
        "render_audit": render_audit,
        "render_stderr": (render.stderr or "")[-1500:] if render.returncode != 0 else None,
        "validate_stderr": (validate.stderr or "")[-1500:] if validate.returncode != 0 else None,
    }


def _model_style_sections(project_id: str, template: dict, answers: dict) -> dict:
    """Model authors the descriptive style-guide sections. Palette/Typography are NOT
    requested (they stay locked to the template). Returns {section: prose, _provider} or {}."""
    from . import stage_models

    base_prompt = (
        "你是 PPT-agent 的风格指南模型。基于主题与受众写演示的风格指引描述（不要写配色和字体，"
        "那些由模板锁定）。只输出 JSON："
        '{"layout_rhythm":"版面节奏与层次的指引","chart_style":"图表风格指引",'
        '"image_treatment":"图片处理指引","icon_rules":"图标使用指引","accessibility":"可访问性指引"}。'
        "每项一到两句、可执行、与受众贴合，不要输出解释。"
    )
    result = stage_models.generate_artifact(
        project_id, "STYLE_UNIFICATION", base_prompt,
        context={"answers": answers, "template_name": template.get("name"),
                 "deck_type": read_json(project_dir(project_id) / "task-analysis.json", {}).get("deck_type")},
        parse="json",
    )
    if not result.get("ok"):
        return {}
    data = result["data"]
    out = {}
    for key in ("layout_rhythm", "chart_style", "image_treatment", "icon_rules", "accessibility"):
        val = str(data.get(key) or "").strip().replace("\n", " ")
        if val:
            out[key] = val
    if not out:
        return {}
    out["_provider"] = result.get("provider")
    return out


def _run_v2_template_binding(project_id: str, payload: dict) -> dict:
    pdir = project_dir(project_id)
    template = _ensure_template_profile(project_id, payload.get("template"))
    plan = read_json(pdir / "model-routed-plan.json", {})
    visual = read_json(pdir / "visual-plan.json", {})
    slides = visual.get("slides") if isinstance(visual, dict) else []
    if not isinstance(slides, list) or not slides:
        return {
            "ok": False,
            "error": "visual-plan.json missing or invalid",
            "message": "STYLE_UNIFICATION requires SLIDE_REWRITE V2 artifacts; legacy visual-plan synthesis is disabled.",
        }
    binding = {
        "schema_version": "1.0",
        "generated_at": now(),
        "source": "stage_runner",
        "template_id": template.get("template_id"),
        "template_name": template.get("name"),
        "template_reuse_policy": {
            "base_locked": ["cover", "agenda", "ending", "title_rule", "footer", "page_number", "typography", "palette"],
            "others_learn_only": ["layout rhythm", "research density", "component pattern", "emphasis strategy"],
            "forbidden": ["copy others text", "copy others images", "copy exact coordinates", "copy paper-specific content"],
        },
        "slide_count": len(slides),
        "slides": [
            {
                "slide_index": item.get("slide_index"),
                "layout_type": item.get("layout_type"),
                "visual_type": item.get("visual_type"),
                "binding_status": "style_shell_bound",
                "fallback_reason": None,
                "approved_asset_count": len(item.get("assets") or []),
            }
            for item in slides
        ],
    }
    style_profile = {
        "schema_version": "1.0",
        "generated_at": now(),
        "source": "stage_runner",
        "template_id": template.get("template_id"),
        "template_name": template.get("name"),
        "palette": template.get("palette", {}),
        "typography": template.get("typography", {}),
        "render": template.get("render", {}),
        "template_reuse_policy": {
            "base_is_top_priority": True,
            "paper_share_is_abstract_reference_only": True,
            "content_pages_are_model_composed": True,
        },
        "plan_revision": plan.get("revision") if isinstance(plan, dict) else None,
    }
    write_json(pdir / "template-binding.json", binding)
    write_json(pdir / "style-profile.json", style_profile)
    pal = template.get("palette", {})
    typo = template.get("typography", {})
    layouts = template.get("layouts", {})
    template_layouts_line = (
        f"Template layouts: title-image = {layouts.get('title-image')}; "
        f"title-and-body = {layouts.get('title-and-body')}; closing = {layouts.get('closing')}."
    )

    # Deterministic guidance prose. The model may rewrite these descriptive
    # sections, but Palette/Typography stay locked to the real template.
    defaults = {
        "layout_rhythm": "Clear hierarchy, generous margins, one main message per slide, consistent title position.",
        "chart_style": "Use native editable charts only when data is present; never render factual charts as images.",
        "image_treatment": "Raster images are optional and must be paired with editable text.",
        "icon_rules": "Use simple line icons only when available; avoid decorative clutter.",
        "accessibility": "Maintain high contrast and do not encode meaning by color alone.",
    }
    sections = dict(defaults)
    model_sections = _model_style_sections(project_id, template, _answers(project_id))
    generated_by = "stage_runner"
    if model_sections:
        for key in sections:
            if model_sections.get(key):
                sections[key] = model_sections[key]
        generated_by = model_sections.get("_provider") or "model"

    def _compose(secs: dict) -> str:
        return (
            "---\n"
            'schema_version: "1.0"\n'
            f'generated_at: "{now()}"\n'
            f'preset: "{template.get("template_id")}"\n'
            f'template_name: "{template.get("name")}"\n'
            f'template_path: "{template.get("_path")}"\n'
            f'generated_by: "{generated_by}"\n'
            "---\n\n"
            "## Palette\n"
            f"Primary {pal.get('primary')}, secondary {pal.get('secondary')}, accent {pal.get('accent')}, "
            f"neutral {pal.get('neutral')}, text {pal.get('text')}.\n\n"
            "## Typography\n"
            f"Headings: {typo.get('heading')} semibold, {typo.get('heading_size')}pt target; "
            f"body: {typo.get('body')} regular, minimum body size {typo.get('body_size')}pt.\n\n"
            f"## Layout Rhythm\n{secs['layout_rhythm']}\n{template_layouts_line}\n\n"
            f"## Chart Style\n{secs['chart_style']}\n\n"
            f"## Image Treatment\n{secs['image_treatment']}\n\n"
            f"## Icon Rules\n{secs['icon_rules']}\n\n"
            f"## Accessibility\n{secs['accessibility']}\n"
        )

    sg = pdir / "style-guide.md"
    sg.write_text(_compose(sections), encoding="utf-8")
    if model_sections and not _validate_ok("style-guide", sg):
        # Model wording broke the schema/contract; keep deterministic prose within V2.
        generated_by = "stage_runner"
        sg.write_text(_compose(defaults), encoding="utf-8")
    _validate_artifact("style-guide", sg)
    return {
        "template_binding": str(pdir / "template-binding.json"),
        "style_profile": str(pdir / "style-profile.json"),
        "style_guide": str(sg),
        "generated_by": generated_by,
    }


def _stub_artifact_payload(stage: str, wave: str, output: str) -> dict | str:
    """Build a minimal placeholder for a stub stage output."""
    if output.endswith(".md"):
        return (
            f"---\nschema_version: \"1.0\"\nstage: \"{stage}\"\nstub: true\nwave: \"{wave}\"\n---\n\n"
            f"# {stage} stub\n\nThis artifact is a placeholder. Real logic lands in {wave}.\n"
        )
    return {
        "schema_version": "1.0",
        "generated_at": now(),
        "stage": stage,
        "stub": True,
        "wave": wave,
        "note": f"Stage {stage} stubbed in W1; real implementation lands in {wave}.",
        "outputs_declared": output,
    }


_STUB_STAGES: dict[str, str] = {}


def _run_stub_stage(project_id: str, stage: str) -> dict:
    """Write placeholder outputs declared in agents.json so artifact_status='ready'.
    Real implementations land in W2-W6; this lets the 24-stage pipeline run end-to-end
    immediately after W1 without crashing on missing artifacts."""
    pdir = project_dir(project_id)
    wave = _STUB_STAGES.get(stage, "W?")
    spec = stage_controller.stage_item(project_id, stage) or {}
    outputs = list(spec.get("output_artifacts") or [])
    written = []
    for rel in outputs:
        if not rel:
            continue
        if rel.startswith("data/") or rel.endswith("/"):
            continue
        path = pdir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = _stub_artifact_payload(stage, wave, rel)
        if isinstance(payload, dict):
            write_json(path, payload)
        else:
            path.write_text(payload, encoding="utf-8")
        written.append(rel)
    return {"ok": True, "stage": stage, "stub": True, "wave": wave, "written": written}


def _execute_stage(project_id: str, stage: str, payload: dict) -> dict:
    from . import services

    stage = stage.upper()
    spec = stage_controller.stage_item(project_id, stage)
    if not spec:
        return {"ok": False, "stage": stage, "error": f"unknown stage: {stage}"}

    # Phase F.6: handler return shape varies — some return {"ok": True, ...},
    # others a result dict that gets wrapped here. To enforce contract:
    #   - call the handler
    #   - check `inner.get("ok")` (default True for handlers that don't set it)
    #   - if inner is falsy, propagate ok=False to outer
    #   - on success, advance current_stage in stage-state.json
    def _finalize(inner: dict, *, default_ok: bool = True) -> dict:
        if not isinstance(inner, dict):
            return {"ok": default_ok, "stage": stage, "result": inner}
        # If the inner result explicitly marks ok=False, propagate the failure.
        if inner.get("ok") is False:
            return {
                "ok": False,
                "stage": stage,
                "result": inner,
                "error": inner.get("error") or f"{stage} returned ok=False",
            }
        outer = {"ok": True, "stage": stage, "result": inner}
        # Phase F.6: advance current_stage on successful completion.
        try:
            next_stage = (spec.get("next_stage") if isinstance(spec, dict) else None) or "COMPLETE"
            stage_controller.set_current_stage(project_id, next_stage)
        except Exception:
            pass
        return outer

    if stage == "BRIEF":
        state = read_json(project_dir(project_id) / "question-state.json", {})
        if not state:
            return {"ok": False, "stage": stage, "error": "question-state.json missing"}
        return _finalize(state)

    if stage in _STUB_STAGES:
        return _finalize(_run_stub_stage(project_id, stage))

    if stage == "IDEA_INTAKE_LIGHT":
        return _finalize(_run_idea_intake_light(project_id))

    if stage == "IDEA_ANALYSIS":
        return _finalize(_run_idea_analysis(project_id))

    # v17: SOURCE_UNDERSTAND / OUTLINE_REVISION removed from pipeline
    if stage == "SOURCE_UNDERSTAND":
        return _finalize({"ok": True, "note": "SOURCE_UNDERSTAND removed in v17 pipeline (no project sources)"})

    if stage == "OUTLINE_GENERATION":
        return _finalize(_run_outline_generation(project_id))

    if stage == "OUTLINE_REVISION":
        return _finalize({"ok": True, "note": "OUTLINE_REVISION removed in v17 pipeline (outline internal review loop handles revision)"})

    # v17: DECK/SECTION/SLIDE matching + review folded into OUTLINE stage
    if stage in ("DECK_MATCHING", "SECTION_MATCHING", "SLIDE_MATCHING", "SLIDE_MATCHING_REVIEW"):
        return _finalize({"ok": True, "note": f"{stage} removed in v17 pipeline (subsumed by OUTLINE internal iterative loop)"})

    if stage == "GAP_CARD_GENERATION":
        return _finalize(_run_gap_card_generation(project_id))

    if stage == "STORY_STRATEGY":
        return _finalize(_run_story_strategy(project_id))

    if stage == "SLIDE_PLAN":
        return _finalize(_run_slide_plan(project_id))

    if stage == "REUSE_DECISION_AUDIT":
        return _finalize(_run_reuse_decision_audit(project_id))

    if stage == "DRAFT_ASSEMBLY_PLAN":
        return _finalize(_run_draft_assembly_plan(project_id))

    if stage == "DRAFT_REVIEW":
        return _finalize(_run_draft_review(project_id))

    # v17: RESOURCE_SCAN / TEMPLATE_LIBRARY / LAYERED removed from pipeline
    # (preprocess is a separate CLI: python3 -m ppt_agent_app.preprocess build-all)
    if stage in ("RESOURCE_SCAN", "PROJECT_SOURCE_SCAN"):
        return {"ok": True, "stage": stage, "result": {"note": "RESOURCE_SCAN removed in v17 (no project sources)"}}

    if stage == "TEMPLATE_LIBRARY_BUILD":
        return {"ok": True, "stage": stage, "result": {"note": "TEMPLATE_LIBRARY_BUILD moved to preprocess CLI in v17"}}

    if stage == "TEMPLATE_LIBRARY_QUERY":
        return {"ok": True, "stage": stage, "result": {"note": "TEMPLATE_LIBRARY_QUERY subsumed by OUTLINE stage in v17"}}

    if stage in ("LIBRARY_RETRIEVAL_CONTEXT_BUILD", "LAYERED_RETRIEVAL"):
        return {"ok": True, "stage": stage, "result": {"note": "LAYERED_RETRIEVAL subsumed by OUTLINE stage in v17"}}

    if stage == "TASK_UNDERSTANDING":
        return _finalize(_run_task_understanding(project_id))

    if stage == "REUSE_OUTLINE":
        result = _run_reuse_outline(project_id, payload)
        return {"ok": bool(result.get("ok")), "stage": stage, "result": result}

    if stage == "DRAFT_ASSEMBLY":
        result = _run_draft_assembly(project_id, payload)
        return {"ok": bool(result.get("ok")), "stage": stage, "result": result}

    if stage == "DRAFT_QUALITY_SCORE":
        result = _run_draft_quality_score(project_id)
        return {"ok": bool(result.get("ok")), "stage": stage, "result": result}

    if stage == "GAP_ANALYSIS":
        result = _run_gap_analysis(project_id)
        return {"ok": bool(result.get("ok")), "stage": stage, "result": result}

    if stage == "GAP_RESEARCH":
        result = _run_gap_research(project_id, payload)
        return {"ok": bool(result.get("ok")), "stage": stage, "result": result}

    if stage == "GAP_SYNTHESIS":
        return _finalize(_run_gap_synthesis(project_id))

    if stage == "SLIDE_REWRITE":
        result = _run_slide_rewrite(project_id, payload)
        return {"ok": bool(result.get("ok")), "stage": stage, "result": result}

    if stage == "STYLE_UNIFICATION":
        result = _run_style_unification(project_id, payload)
        return {"ok": bool(result.get("ok")), "stage": stage, "result": result}

    if stage == "RENDER_PRECHECK":
        return _finalize(_run_render_precheck(project_id))

    if stage == "RENDER":
        result = _run_render(project_id, payload)
        return {
            "ok": bool(result.get("ok")),
            "stage": stage,
            "result": result,
            "bridge": result.get("source"),
        }

    if stage == "REVIEW" or stage == "SYSTEM_REVIEW":
        report = _run_review(project_id)
        pdir = project_dir(project_id)
        src = pdir / "review-report.json"
        dst = pdir / "system-review-report.json"
        if src.exists():
            dst.write_bytes(src.read_bytes())
        return {"ok": True, "stage": stage, "result": report}

    if stage == "CHARACTER_REVISION":
        result = _run_character_revision(project_id)
        return {"ok": bool(result.get("ok")), "stage": stage, "result": result}

    if stage == "VISUAL_UNIFICATION":
        result = _run_visual_unification(project_id)
        return {"ok": bool(result.get("ok")), "stage": stage, "result": result}

    if stage == "TEMPLATE_UNIFICATION":
        result = _run_template_unification(project_id)
        return {"ok": bool(result.get("ok")), "stage": stage, "result": result}

    if stage == "CODEX_REVIEW":
        result = _run_codex_review(project_id)
        return {"ok": bool(result.get("ok")), "stage": stage, "result": result}

    if stage == "REVISION_DECISION":
        return _finalize(_run_revision_decision(project_id))

    if stage == "PPT_EVAL":
        result = _run_ppt_eval(project_id)
        return {"ok": bool(result.get("ok")), "stage": stage, "result": result}

    if stage == "FINAL_ACCEPT":
        return _finalize(_run_final_accept(project_id))

    return {
        "ok": False,
        "stage": stage,
        "error": f"stage {stage} has no automatic executor yet",
    }


def _compact_for_ui(value, *, depth: int = 0):
    if depth > 5:
        return "<truncated: nested data>"
    if isinstance(value, str):
        return value if len(value) <= 1600 else value[:1600] + "\n...<truncated>"
    if isinstance(value, list):
        out = [_compact_for_ui(item, depth=depth + 1) for item in value[:30]]
        if len(value) > 30:
            out.append(f"<truncated: {len(value) - 30} more items>")
        return out
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if str(key) in {"output", "raw", "stdout", "stderr", "fetched_text", "content", "text_excerpt"}:
                text = str(item or "")
                out[key] = text if len(text) <= 800 else text[:800] + "\n...<truncated>"
            else:
                out[key] = _compact_for_ui(item, depth=depth + 1)
        return out
    return value


def run_stage(project_id: str, payload: dict | None = None) -> dict:
    payload = payload or {}
    requested_stage = payload.get("stage")
    stage = _current_or_requested(project_id, requested_stage)
    if requested_stage and payload.get("reset_current", True):
        before = stage_controller.rewind_to_stage(
            project_id,
            stage,
            reason="reset by explicit UI stage button",
        )
    else:
        before = stage_controller.refresh(project_id)
    result = _execute_stage(project_id, stage, payload)
    after = stage_controller.refresh(project_id)
    item = stage_controller.stage_item(project_id, stage)
    if result.get("ok") and not item.get("human_gate") and item.get("artifact_status") in {"ready", "not_required"}:
        after = stage_controller.set_stage_status(project_id, stage, "done")
    if result.get("ok"):
        after = _advance_current_to_first_blocker(project_id, stage, force_lower_bound=bool(requested_stage and payload.get("reset_current", True)))
    if payload.get("compact"):
        diagnostics = {}
        try:
            from . import services
            diagnostics = (services.stage_diagnostics(project_id) or {}).get(stage, {})
        except Exception:
            diagnostics = {}
        compact_result = _compact_for_ui(result)
        inner = result.get("result")
        if stage == "RESOURCE_SCAN" and isinstance(inner, dict):
            compact_result = {
                **_compact_for_ui({k: v for k, v in result.items() if k != "result"}),
                "result": {
                    "project_id": inner.get("project_id"),
                    "count": inner.get("count"),
                    "parsed_count": inner.get("parsed_count"),
                    "by_type": inner.get("by_type"),
                    "artifacts": inner.get("artifacts"),
                    "chart_candidate_count": inner.get("chart_candidate_count"),
                    "asset_count": inner.get("asset_count"),
                },
            }
        return {
            "ok": bool(result.get("ok")),
            "project_id": project_id,
            "stage": stage,
            "before_current_stage": before.get("current_stage"),
            "current_stage": after.get("current_stage"),
            "result": compact_result,
            "diagnostics": _compact_for_ui(diagnostics),
        }
    return {
        "ok": bool(result.get("ok")),
        "project_id": project_id,
        "stage": stage,
        "before_current_stage": before.get("current_stage"),
        "result": result,
        "stage_state": after,
    }


def run_until_blocked(project_id: str, payload: dict | None = None) -> dict:
    payload = payload or {}
    max_steps = int(payload.get("max_steps") or 20)
    stop_at_human_gate = bool(payload.get("stop_at_human_gate", True))
    executed = []
    stage_names = _stage_names()

    for _ in range(max_steps):
        state = stage_controller.refresh(project_id)
        current = str(state.get("current_stage") or "").upper()
        if current in TERMINAL_STAGES:
            return {
                "ok": current != "ERROR",
                "project_id": project_id,
                "executed": executed,
                "stopped_stage": current,
                "stop_reason": "escalated" if current == "ESCALATION" else current.lower(),
                "escalation": read_json(project_dir(project_id) / "escalation.json", {}) if current == "ESCALATION" else None,
                "stage_state": state,
            }
        if not current or current not in stage_names:
            return {
                "ok": False,
                "project_id": project_id,
                "executed": executed,
                "stop_reason": "unknown_current_stage",
                "stage_state": state,
            }
        item = stage_controller.stage_item(project_id, current)
        if stop_at_human_gate and item.get("human_gate") and item.get("artifact_status") in {"ready", "not_required"} and not item.get("confirmed"):
            return {
                "ok": True,
                "project_id": project_id,
                "executed": executed,
                "stopped_stage": current,
                "stop_reason": "human_gate_waiting",
                "stage_state": state,
            }

        result = run_stage(project_id, {**payload, "stage": current, "reset_current": False})
        executed.append({
            "stage": current,
            "ok": result.get("ok"),
            "artifact_status": stage_controller.stage_item(project_id, current).get("artifact_status"),
        })
        if not result.get("ok"):
            return {
                "ok": False,
                "project_id": project_id,
                "executed": executed,
                "stopped_stage": current,
                "stop_reason": "stage_failed",
                "stage_state": stage_controller.refresh(project_id),
                "error": result.get("result", {}).get("error") or result.get("result", {}).get("result", {}).get("error"),
            }

        item = stage_controller.stage_item(project_id, current)
        if item.get("artifact_status") not in {"ready", "not_required"}:
            return {
                "ok": False,
                "project_id": project_id,
                "executed": executed,
                "stopped_stage": current,
                "stop_reason": "artifact_missing_after_stage",
                "stage_state": stage_controller.refresh(project_id),
            }

        if item.get("human_gate") and not item.get("confirmed"):
            return {
                "ok": True,
                "project_id": project_id,
                "executed": executed,
                "stopped_stage": current,
                "stop_reason": "human_gate_waiting",
                "stage_state": stage_controller.refresh(project_id),
            }

        transition = resolve_transition(project_id, current)
        if transition.get("escalate"):
            stage_controller.set_current_stage(project_id, "ESCALATION")
            return {
                "ok": True,
                "project_id": project_id,
                "executed": executed,
                "stopped_stage": current,
                "stop_reason": "escalated",
                "reason": transition.get("reason"),
                "escalation": read_json(project_dir(project_id) / "escalation.json", {}),
                "stage_state": stage_controller.refresh(project_id),
            }
        next_stage = transition.get("next_stage")
        if not next_stage:
            return {
                "ok": True,
                "project_id": project_id,
                "executed": executed,
                "stopped_stage": current,
                "stop_reason": "complete",
                "stage_state": stage_controller.refresh(project_id),
            }
        if transition.get("rollback"):
            executed.append({"stage": current, "rollback_to": next_stage, "reason": transition.get("reason")})
        stage_controller.set_current_stage(project_id, str(next_stage))

    return {
        "ok": False,
        "project_id": project_id,
        "executed": executed,
        "stop_reason": "max_steps_exceeded",
        "stage_state": stage_controller.refresh(project_id),
    }


try:
    from .eval.timing_hook import install as _install_eval_timing_hook

    _install_eval_timing_hook()
except Exception:  # noqa: BLE001
    pass
