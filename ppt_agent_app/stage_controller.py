from __future__ import annotations

from . import layout_registry, skill_runtime
from .models import ROOT, file_lock, now, project_dir, read_json, write_json


DEFAULT_STAGES = [
    {"stage": "BRIEF", "model_route": "intake", "tool_routes": [], "output_artifacts": ["question-state.json"], "human_gate": True, "review_gate": False, "next_stage": "IDEA_INTAKE_LIGHT"},
    {"stage": "IDEA_INTAKE_LIGHT", "model_route": "idea_intake_light", "tool_routes": [], "output_artifacts": ["idea-intake-light.json"], "human_gate": False, "review_gate": False, "next_stage": "IDEA_ANALYSIS"},
    {"stage": "IDEA_ANALYSIS", "model_route": "idea_analysis", "tool_routes": [], "output_artifacts": ["idea-analysis.json", "idea-analysis.md", "idea-user-status.json"], "human_gate": True, "review_gate": True, "next_stage": "OUTLINE_GENERATION"},
    {"stage": "OUTLINE_GENERATION", "model_route": "outline_generation", "tool_routes": [], "output_artifacts": ["outline.json", "outline.md", "outline-user-status.json", "outline-chapter-stubs.json", "slide-matches.json"], "human_gate": True, "review_gate": True, "next_stage": "GAP_CARD_GENERATION"},
    {"stage": "GAP_CARD_GENERATION", "model_route": "gap_card_generation", "tool_routes": [], "output_artifacts": ["gap-cards.json", "chapter-gap-summary.json", "slide-annotations.json", "gap-card-user-status.json"], "human_gate": True, "review_gate": True, "next_stage": "DRAFT_ASSEMBLY"},
    {"stage": "DRAFT_ASSEMBLY", "model_route": None, "tool_routes": ["ppt_render"], "output_artifacts": ["draft-assembly-plan.json", "draft-manuscript.md", "draft-visual-plan.json", "draft-source-lineage.json", "draft-deck.pptx"], "human_gate": False, "review_gate": False, "next_stage": "CODEX_REVIEW"},
    {"stage": "CODEX_REVIEW", "model_route": "review", "tool_routes": ["validation"], "output_artifacts": ["codex-review.md", "codex-review.json"], "human_gate": False, "review_gate": True, "next_stage": "DRAFT_REVIEW"},
    {"stage": "DRAFT_REVIEW", "model_route": "draft_review", "tool_routes": [], "output_artifacts": ["draft-review.json"], "human_gate": True, "review_gate": True, "next_stage": "GAP_ANALYSIS"},
    {"stage": "GAP_ANALYSIS", "model_route": "review", "tool_routes": [], "output_artifacts": ["slide-gap-plan.json"], "human_gate": True, "review_gate": True, "next_stage": "GAP_RESEARCH"},
    {"stage": "GAP_RESEARCH", "model_route": "research_summary", "tool_routes": ["web_search", "web_fetch"], "output_artifacts": ["gap-research-results.json", "research.md", "citations.json", "research-audit.json", "per-slide-evidence-pack.json"], "human_gate": False, "review_gate": True, "next_stage": "SLIDE_REWRITE"},
    {"stage": "GAP_SYNTHESIS", "model_route": "gap_synthesis", "tool_routes": [], "output_artifacts": ["gap-synthesis.json"], "human_gate": False, "review_gate": True, "next_stage": "SLIDE_REWRITE"},
    {"stage": "SLIDE_REWRITE", "model_route": "slide_rewrite", "tool_routes": [], "output_artifacts": ["slide-composition.json", "manuscript.md", "visual-plan.json", "model-routed-plan.json"], "human_gate": False, "review_gate": True, "next_stage": "STYLE_UNIFICATION"},
    {"stage": "STYLE_UNIFICATION", "model_route": "template_style", "tool_routes": [], "output_artifacts": ["style-unification-plan.json", "template-binding.json", "style-profile.json"], "human_gate": False, "review_gate": True, "next_stage": "RENDER_PRECHECK"},
    {"stage": "RENDER_PRECHECK", "model_route": None, "tool_routes": ["validation"], "output_artifacts": ["render-precheck.json"], "human_gate": False, "review_gate": True, "next_stage": "RENDER"},
    {"stage": "RENDER", "model_route": None, "tool_routes": ["ppt_render"], "output_artifacts": ["deck.pptx", "render-log.md", "structural-validation.md", "render-audit.json"], "human_gate": False, "review_gate": True, "next_stage": "REVIEW"},
    {"stage": "REVIEW", "model_route": "review", "tool_routes": ["validation"], "output_artifacts": ["review-report.json"], "human_gate": True, "review_gate": True, "next_stage": "REVISION_DECISION"},
    {"stage": "REVISION_DECISION", "model_route": "review", "tool_routes": [], "output_artifacts": ["revision-decision.json"], "human_gate": False, "review_gate": True, "next_stage": "FINAL_ACCEPT"},
    {"stage": "FINAL_ACCEPT", "model_route": None, "tool_routes": [], "output_artifacts": ["final-report.json"], "human_gate": True, "review_gate": False, "next_stage": None},
]


def stage_specs() -> list[dict]:
    specs = skill_runtime.stage_specs()
    return specs or DEFAULT_STAGES


def confirmation_gates() -> list[str]:
    return skill_runtime.confirmation_gates()


def _artifact_status(project_id: str, artifacts: list[str]) -> str:
    pdir = project_dir(project_id)
    if not artifacts:
        return "not_required"
    def exists(artifact: str) -> bool:
        rel = str(artifact or "")
        if rel.startswith("data/"):
            return (ROOT / rel).exists()
        return (pdir / rel).exists()

    if all(exists(artifact) for artifact in artifacts):
        return "ready"
    if any(exists(artifact) for artifact in artifacts):
        return "partial"
    return "missing"


def initialize(project_id: str) -> dict:
    state = {
        "schema_version": "1.0",
        "generated_at": now(),
        "current_stage": "BRIEF",
        "stages": [],
    }
    for spec in stage_specs():
        artifacts = list(spec.get("output_artifacts") or [])
        state["stages"].append({
            **spec,
            "status": "pending",
            "artifact_status": _artifact_status(project_id, artifacts),
            "confirmed": False,
            "updated_at": now(),
        })
    write_json(project_dir(project_id) / "stage-state.json", state)
    return state


def _merge_specs(state: dict, project_id: str) -> dict:
    old = {item.get("stage"): item for item in state.get("stages", [])}
    merged = []
    for spec in stage_specs():
        stage = spec["stage"]
        previous = old.get(stage) or {}
        artifacts = list(spec.get("output_artifacts") or [])
        merged.append({
            **spec,
            "status": previous.get("status") or "pending",
            "artifact_status": _artifact_status(project_id, artifacts),
            "confirmed": bool(previous.get("confirmed", False)),
            "confirmed_at": previous.get("confirmed_at"),
            "updated_at": previous.get("updated_at") or now(),
        })
    state["stages"] = merged
    if not state.get("current_stage"):
        state["current_stage"] = "BRIEF"
    return state


def refresh(project_id: str) -> dict:
    path = project_dir(project_id) / "stage-state.json"
    with file_lock(path):
        state = read_json(path, {}) or initialize(project_id)
        state = _merge_specs(state, project_id)
        invalid_confirmed_stage = None
        for item in state.get("stages", []):
            artifact_status = _artifact_status(project_id, list(item.get("output_artifacts") or []))
            item["artifact_status"] = artifact_status
            if item.get("confirmed") and artifact_status not in {"ready", "not_required"}:
                item["confirmed"] = False
                item["confirmed_at"] = None
                item["status_reason"] = "confirmation cleared because required artifacts are not ready"
                if invalid_confirmed_stage is None:
                    invalid_confirmed_stage = item.get("stage")
            if item.get("status") == "skipped":
                item["status"] = "skipped"
            elif item.get("confirmed"):
                item["status"] = "confirmed"
            elif artifact_status == "ready":
                item["status"] = "ready_for_review" if item.get("human_gate") or item.get("review_gate") else "done"
            elif artifact_status == "partial":
                item["status"] = "partial"
            else:
                item["status"] = "pending"
        order = [str(item.get("stage")) for item in state.get("stages", [])]
        current = str(state.get("current_stage") or "")
        blockers = []
        for item in state.get("stages", []):
            artifact_status = str(item.get("artifact_status") or "")
            status = str(item.get("status") or "")
            if artifact_status not in {"ready", "not_required"} or status in {"pending", "partial"}:
                blockers.append(str(item.get("stage") or ""))
                break
        if invalid_confirmed_stage:
            blockers.insert(0, str(invalid_confirmed_stage))
        if blockers:
            blocker = blockers[0]
            if current != blocker:
                state["current_stage"] = blocker
        state["updated_at"] = now()
        write_json(path, state)
        return state


def set_stage_status(
    project_id: str,
    stage: str,
    status: str,
    *,
    reason: str | None = None,
    confirmed: bool | None = None,
) -> dict:
    path = project_dir(project_id) / "stage-state.json"
    with file_lock(path):
        state = refresh(project_id)
        stage = stage.upper()
        for item in state.get("stages", []):
            if item.get("stage") == stage:
                item["status"] = status
                if confirmed is not None:
                    item["confirmed"] = confirmed
                    item["confirmed_at"] = now() if confirmed else None
                if reason:
                    item["status_reason"] = reason
                item["updated_at"] = now()
                break
        state["updated_at"] = now()
        write_json(path, state)
        return state


def set_current_stage(project_id: str, stage: str) -> dict:
    path = project_dir(project_id) / "stage-state.json"
    with file_lock(path):
        state = refresh(project_id)
        state["current_stage"] = stage.upper()
        state["updated_at"] = now()
        write_json(path, state)
        return state


def rewind_to_stage(project_id: str, stage: str, reason: str | None = None) -> dict:
    """Move the interactive cursor back to a stage without deleting artifacts.

    This is used by UI stage buttons: clicking a previous stage means "resume from
    here". Existing files stay available, but confirmations from that stage onward
    are cleared because regenerated artifacts may invalidate downstream approvals.
    """
    path = project_dir(project_id) / "stage-state.json"
    with file_lock(path):
        state = refresh(project_id)
        stage = stage.upper()
        stages = state.get("stages") or []
        order = [str(item.get("stage") or "").upper() for item in stages]
        if stage not in order:
            state["ok"] = False
            state["error"] = f"unknown stage: {stage}"
            write_json(path, state)
            return state
        start = order.index(stage)
        for idx, item in enumerate(stages):
            if idx >= start:
                item["confirmed"] = False
                item["confirmed_at"] = None
                item["updated_at"] = now()
                if reason:
                    item["status_reason"] = reason
        state["current_stage"] = stage
        state["updated_at"] = now()
        write_json(path, state)
        return refresh(project_id)


def stage_item(project_id: str, stage: str) -> dict:
    state = refresh(project_id)
    stage = stage.upper()
    for item in state.get("stages", []):
        if item.get("stage") == stage:
            return item
    return {}


def confirm(project_id: str, stage: str, note: str | None = None, force: bool = False) -> dict:
    path = project_dir(project_id) / "stage-state.json"
    with file_lock(path):
        state = refresh(project_id)
        stage = stage.upper()
        next_stage = None
        found = False
        for item in state.get("stages", []):
            if item.get("stage") == stage:
                found = True
                if item.get("artifact_status") not in {"ready", "not_required"} and not force:
                    return {
                        **state,
                        "ok": False,
                        "error": f"stage {stage} is not ready to confirm",
                        "stage": stage,
                        "artifact_status": item.get("artifact_status"),
                        "required_artifacts": item.get("output_artifacts") or [],
                    }
                item["confirmed"] = True
                item["status"] = "confirmed"
                item["confirmed_at"] = now()
                if note:
                    item["confirmation_note"] = note
                item["updated_at"] = now()
                next_stage = item.get("next_stage")
                break
        if not found:
            return {**state, "ok": False, "error": f"unknown stage: {stage}", "stage": stage}
        # Dynamic routing for the bounded review loop: REVISION_DECISION / FINAL_ACCEPT
        # may roll back to an upstream stage or escalate instead of advancing linearly.
        rollback_info = None
        if stage in {"REVISION_DECISION", "FINAL_ACCEPT"}:
            from . import stage_runner  # lazy import avoids a circular dependency
            write_json(path, state)  # persist confirmation before resolver reads state
            transition = stage_runner.resolve_transition(project_id, stage)
            rollback_info = transition
            next_stage = "ESCALATION" if transition.get("escalate") else transition.get("next_stage")
        if next_stage:
            state["current_stage"] = next_stage
        state["updated_at"] = now()
        write_json(path, state)
        out = {**state, "ok": True, "confirmed_stage": stage}
        if rollback_info is not None:
            out["transition"] = rollback_info
        return out


def unconfirm(project_id: str, stage: str, reason: str | None = None) -> dict:
    path = project_dir(project_id) / "stage-state.json"
    with file_lock(path):
        state = refresh(project_id)
        stage = stage.upper()
        for item in state.get("stages", []):
            if item.get("stage") == stage:
                item["confirmed"] = False
                item["confirmed_at"] = None
                item["status"] = "ready_for_review" if item.get("artifact_status") == "ready" else item.get("status", "pending")
                if reason:
                    item["unconfirmed_reason"] = reason
                item["updated_at"] = now()
                state["current_stage"] = stage
                break
        state["updated_at"] = now()
        write_json(path, state)
        return state


def gate_status(project_id: str, required: list[str] | None = None) -> dict:
    required = [s.upper() for s in (required or confirmation_gates())]
    state = refresh(project_id)
    by_stage = {item.get("stage"): item for item in state.get("stages", [])}
    gates = []
    missing = []
    for stage in required:
        item = by_stage.get(stage) or {"stage": stage, "confirmed": False, "status": "missing"}
        gate = {
            "stage": stage,
            "confirmed": bool(item.get("confirmed")),
            "status": item.get("status"),
            "artifact_status": item.get("artifact_status"),
            "required_artifacts": item.get("output_artifacts") or [],
        }
        gates.append(gate)
        if not gate["confirmed"]:
            missing.append(stage)
    return {"ok": not missing, "required": required, "missing": missing, "gates": gates}


_EVIDENCE_REQUIRED_ROLES = {
    "evidence",
    "mechanism",
    "comparison",
    "architecture",
    "timeline",
    "roadmap",
    "risk",
}

_EVIDENCE_REQUIRED_LAYOUTS = {
    "evidence-matrix",
    "comparison-matrix",
    "layered-architecture",
    "process-flow",
    "roadmap",
    "risk-boundary-table",
}


def _slide_requires_evidence(slide: dict) -> bool:
    return layout_registry.requires_evidence(slide)


def _build_per_slide_evidence_pack(project_id: str, slides: list[dict]) -> dict:
    packs = []
    total = len(slides)
    for idx, slide in enumerate(slides, start=1):
        source_refs = slide.get("source_references") or slide.get("source_refs") or []
        citations = slide.get("citations") or []
        chart_spec = slide.get("chart_spec") if isinstance(slide.get("chart_spec"), dict) else {}
        visual_objects = []
        if chart_spec:
            visual_objects.append({"type": "chart", "spec": chart_spec})
        layout_type = str(slide.get("layout_type") or "").strip().lower()
        if layout_type:
            visual_objects.append({"type": "layout", "layout_type": layout_type})
        visual_spec = slide.get("visual_spec") if isinstance(slide.get("visual_spec"), dict) else {}
        if not layout_registry.visual_spec_is_usable(visual_spec):
            visual_spec = layout_registry.synthesize_visual_spec(slide, slide_index=idx, slide_count=total)
        needs_evidence = _slide_requires_evidence(slide)
        source_status = "bound" if source_refs or citations else ("required_missing" if needs_evidence else "optional_missing")
        packs.append({
            "slide_id": int(slide.get("index") or idx),
            "title": slide.get("title") or f"Slide {idx}",
            "story_role": slide.get("story_role"),
            "layout_type": slide.get("layout_type"),
            "needs_research": needs_evidence,
            "needs_evidence_pack": needs_evidence,
            "needs_visual_spec": layout_registry.requires_visual_spec_for_slide(slide, slide_index=idx, slide_count=total),
            "research_query": " ".join(
                str(x).strip()
                for x in [slide.get("title"), slide.get("claim"), slide.get("key_message")]
                if str(x or "").strip()
            ),
            "source_chunks": source_refs,
            "verified_facts": [
                str(x).strip()
                for x in [slide.get("claim"), slide.get("evidence_sentence")]
                if str(x or "").strip()
            ],
            "citations": citations,
            "chart_data": chart_spec,
            "table_data": visual_spec.get("data") if str(visual_spec.get("kind")) in {"table", "matrix", "risk_table"} else {},
            "diagram_spec": {
                "nodes": visual_spec.get("nodes") or [],
                "edges": visual_spec.get("edges") or [],
                "stages": visual_spec.get("stages") or [],
            },
            "visual_spec": visual_spec,
            "visual_objects": visual_objects,
            "copy": {
                "claim": slide.get("claim") or slide.get("key_message"),
                "bullets": slide.get("bullets") or [],
                "left_box": slide.get("left_box") or {},
                "right_box": slide.get("right_box") or {},
            },
            "copy_limits": layout_registry.copy_limits(layout_type),
            "source_binding_status": source_status,
            "evidence_quality": {
                "has_verified_facts": bool(slide.get("claim") or slide.get("evidence_sentence")),
                "has_citations": bool(citations),
                "has_source_chunks": bool(source_refs),
                "status": "ready" if (not needs_evidence or citations or source_refs) else "weak",
            },
            "speaker_notes": "",
        })
    return {
        "schema_version": "1.0",
        "generated_at": now(),
        "project_id": project_id,
        "source": "model-routed-plan.json",
        "slide_count": len(packs),
        "packs": packs,
    }


def build_slide_state(project_id: str) -> dict:
    pdir = project_dir(project_id)
    plan = read_json(pdir / "model-routed-plan.json", {})
    plan_slides = plan.get("slides") if isinstance(plan, dict) else None
    source_slides = plan_slides if isinstance(plan_slides, list) else []
    slides = []
    asset_requests = []
    for idx, slide in enumerate(source_slides or [], start=1):
        source_refs = slide.get("source_references") or slide.get("source_refs") or []
        needs_evidence = _slide_requires_evidence(slide)
        slides.append({
            "slide_id": int(slide.get("index") or idx),
            "status": "draft",
            "title": slide.get("title") or f"Slide {idx}",
            "kind": slide.get("kind") or slide.get("layout") or slide.get("story_role") or "",
            "section": slide.get("section") or "",
            "story_role": slide.get("story_role") or "",
            "layout_type": slide.get("layout_type") or "",
            "visual_type": slide.get("visual_type") or "",
            "needs_research": needs_evidence or not bool(source_refs),
            "needs_asset": str(slide.get("visual_type") or "").lower() in {"image-and-bullets", "diagram", "table"}
            or layout_registry.requires_visual_spec_for_slide(slide, slide_index=idx, slide_count=len(source_slides or [])),
            "needs_evidence_pack": needs_evidence,
            "source_references": source_refs,
            "citations": slide.get("citations") or [],
            "visual_asset_spec": {
                "layout_type": slide.get("layout_type"),
                "visual_intent": slide.get("visual_intent"),
                "chart_spec": slide.get("chart_spec") or {},
                "visual_spec": layout_registry.synthesize_visual_spec(
                    slide,
                    slide_index=idx,
                    slide_count=len(source_slides or []),
                ),
            },
            "copy_limits": layout_registry.copy_limits(slide.get("layout_type")),
            "reuse_candidates": [],
            "review_status": "pending",
        })
        asset_request = slide.get("asset_request") if isinstance(slide.get("asset_request"), dict) else {}
        needs_image = bool(slide.get("needs_generated_image") or asset_request.get("needs_generated_image"))
        prompt = str(slide.get("image_prompt") or asset_request.get("prompt") or "").strip()
        if needs_image:
            asset_requests.append({
                "slide_id": int(slide.get("index") or idx),
                "title": slide.get("title") or f"Slide {idx}",
                "purpose": asset_request.get("purpose") or slide.get("visual_intent") or slide.get("claim"),
                "prompt": prompt,
                "style_reference": asset_request.get("style_reference") or "",
                "provider": "image2",
                "status": "pending" if prompt else "missing_prompt",
                "bound_asset": slide.get("image_asset") or "",
            })
    state = {
        "schema_version": "1.0",
        "generated_at": now(),
        "project_id": project_id,
        "source": "model-routed-plan.json",
        "slide_count": len(slides),
        "slides": slides,
    }
    write_json(pdir / "slide-state.json", state)
    if isinstance(source_slides, list):
        write_json(pdir / "per-slide-evidence-pack.json", _build_per_slide_evidence_pack(project_id, source_slides))
    write_json(pdir / "asset-requests.json", {
        "schema_version": "1.0",
        "generated_at": now(),
        "project_id": project_id,
        "request_count": len(asset_requests),
        "requests": asset_requests,
        "policy": "Generate images only for slides where the planner explicitly requested an explanatory image and no suitable local asset is bound.",
    })
    return state


def slide_state(project_id: str) -> dict:
    pdir = project_dir(project_id)
    state = read_json(pdir / "slide-state.json", {})
    if state.get("slides"):
        return state
    return build_slide_state(project_id)
