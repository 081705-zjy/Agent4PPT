from __future__ import annotations

import re
from copy import deepcopy


EVIDENCE_REQUIRED_ROLES = {
    "evidence",
    "mechanism",
    "comparison",
    "architecture",
    "roadmap",
    "risk",
    "technical_evidence",
    "technical_mechanism",
}


def citation_marker(token: str) -> str:
    m = re.fullmatch(r"S(\d+)", str(token or "").strip())
    return f"[{m.group(1)}]" if m else str(token or "").strip()

LAYOUT_REGISTRY: dict[str, dict] = {
    "title-image": {
        "component_id": "cover_title_image.v1",
        "visual_type": "image-and-bullets",
        "visual_kind": "cover",
        "requires_evidence": False,
        "requires_visual_spec": False,
        "copy_limits": {"title_chars": 34, "claim_chars": 46, "bullet_chars": 24, "max_bullets": 3},
    },
    "section-divider": {
        "component_id": "timeline_3_stage.v1",
        "visual_type": "diagram",
        "visual_kind": "timeline",
        "requires_evidence": False,
        "requires_visual_spec": True,
        "copy_limits": {"title_chars": 24, "claim_chars": 36, "bullet_chars": 18, "max_bullets": 3},
    },
    "problem-framing": {
        "component_id": "problem_framing.v1",
        "visual_type": "bullets",
        "visual_kind": "cards",
        "requires_evidence": False,
        "requires_visual_spec": True,
        "copy_limits": {"title_chars": 24, "claim_chars": 42, "bullet_chars": 24, "max_bullets": 4},
    },
    "gap-matrix": {
        "component_id": "editable_matrix_table.v1",
        "visual_type": "table",
        "visual_kind": "matrix",
        "requires_evidence": True,
        "requires_visual_spec": True,
        "copy_limits": {"title_chars": 24, "claim_chars": 42, "cell_chars": 20, "max_rows": 5},
    },
    "assertion-evidence": {
        "component_id": "editable_chart_or_table.v1",
        "visual_type": "diagram",
        "visual_kind": "cards",
        "requires_evidence": True,
        "requires_visual_spec": True,
        "copy_limits": {"title_chars": 26, "claim_chars": 44, "bullet_chars": 22, "max_bullets": 3},
    },
    "evidence-matrix": {
        "component_id": "editable_chart_or_table.v1",
        "visual_type": "table",
        "visual_kind": "table",
        "requires_evidence": True,
        "requires_visual_spec": True,
        "copy_limits": {"title_chars": 24, "claim_chars": 42, "cell_chars": 22, "max_rows": 5},
    },
    "comparison-matrix": {
        "component_id": "editable_matrix_table.v1",
        "visual_type": "table",
        "visual_kind": "matrix",
        "requires_evidence": True,
        "requires_visual_spec": True,
        "copy_limits": {"title_chars": 24, "claim_chars": 42, "cell_chars": 20, "max_rows": 5},
    },
    "process-flow": {
        "component_id": "editable_flow_diagram.v1",
        "visual_type": "diagram",
        "visual_kind": "flow",
        "requires_evidence": True,
        "requires_visual_spec": True,
        "copy_limits": {"title_chars": 24, "claim_chars": 40, "node_chars": 18, "max_nodes": 5},
    },
    "layered-architecture": {
        "component_id": "editable_layered_architecture.v1",
        "visual_type": "diagram",
        "visual_kind": "architecture",
        "requires_evidence": True,
        "requires_visual_spec": True,
        "copy_limits": {"title_chars": 24, "claim_chars": 40, "node_chars": 18, "max_nodes": 5},
    },
    "roadmap": {
        "component_id": "editable_step_roadmap.v1",
        "visual_type": "diagram",
        "visual_kind": "roadmap",
        "requires_evidence": True,
        "requires_visual_spec": True,
        "copy_limits": {"title_chars": 24, "claim_chars": 40, "stage_chars": 18, "max_stages": 4},
    },
    "risk-boundary-table": {
        "component_id": "editable_risk_table.v1",
        "visual_type": "table",
        "visual_kind": "risk_table",
        "requires_evidence": True,
        "requires_visual_spec": True,
        "copy_limits": {"title_chars": 24, "claim_chars": 40, "cell_chars": 18, "max_rows": 5},
    },
    "experiment-result": {
        "component_id": "editable_chart_or_table.v1",
        "visual_type": "table",
        "visual_kind": "bar_chart",
        "requires_evidence": True,
        "requires_visual_spec": True,
        "copy_limits": {"title_chars": 24, "claim_chars": 42, "cell_chars": 18, "max_rows": 5},
    },
    "evidence-two-box": {
        "component_id": "evidence_two_box.v1",
        "visual_type": "evidence-two-box",
        "visual_kind": "cards",
        "requires_evidence": True,
        "requires_visual_spec": False,
        "copy_limits": {"title_chars": 24, "claim_chars": 42, "bullet_chars": 22, "max_bullets": 3},
    },
    "closing": {
        "component_id": "closing_summary.v1",
        "visual_type": "bullets",
        "visual_kind": "closing",
        "requires_evidence": False,
        "requires_visual_spec": False,
        "copy_limits": {"title_chars": 18, "claim_chars": 34, "bullet_chars": 22, "max_bullets": 3},
    },
    "title-and-body": {
        "component_id": "problem_framing.v1",
        "visual_type": "bullets",
        "visual_kind": "cards",
        "requires_evidence": False,
        "requires_visual_spec": False,
        "copy_limits": {"title_chars": 24, "claim_chars": 42, "bullet_chars": 24, "max_bullets": 4},
    },
}

SEMANTIC_COMPONENTS: dict[str, dict] = {
    "research_agenda.v1": {
        "layout_family": "agenda_grid",
        "visual_kind": "roadmap",
        "layout_type": "roadmap",
        "copy_limits": {"title_chars": 12, "item_chars": 14, "max_items": 6},
    },
    "background_trend.v1": {
        "layout_family": "trend_visual_plus_implication",
        "visual_kind": "bar_chart",
        "layout_type": "experiment-result",
        "copy_limits": {"title_chars": 18, "claim_chars": 42, "fact_chars": 22, "max_facts": 4},
    },
    "challenge_quantification.v1": {
        "layout_family": "big_metric_plus_causal_explanation",
        "visual_kind": "bar_chart",
        "layout_type": "experiment-result",
        "copy_limits": {"title_chars": 18, "claim_chars": 42, "metric_chars": 18, "max_callouts": 4},
    },
    "related_work_matrix.v1": {
        "layout_family": "highlighted_gap_matrix",
        "visual_kind": "matrix",
        "layout_type": "gap-matrix",
        "copy_limits": {"title_chars": 20, "claim_chars": 42, "cell_chars": 20, "max_rows": 5},
    },
    "key_insight_mechanism.v1": {
        "layout_family": "dominant_mechanism_with_callouts",
        "visual_kind": "flow",
        "layout_type": "process-flow",
        "copy_limits": {"title_chars": 18, "claim_chars": 44, "node_chars": 18, "max_nodes": 5},
    },
    "method_overview.v1": {
        "layout_family": "pipeline_or_layered_architecture",
        "visual_kind": "architecture",
        "layout_type": "layered-architecture",
        "copy_limits": {"title_chars": 18, "claim_chars": 42, "node_chars": 18, "max_nodes": 5},
    },
    "technique_detail.v1": {
        "layout_family": "mechanism_diagram_plus_notes",
        "visual_kind": "flow",
        "layout_type": "process-flow",
        "copy_limits": {"title_chars": 18, "claim_chars": 42, "node_chars": 18, "max_nodes": 6},
    },
    "experiment_result.v1": {
        "layout_family": "dominant_result_visual_plus_interpretation",
        "visual_kind": "bar_chart",
        "layout_type": "experiment-result",
        "copy_limits": {"title_chars": 18, "claim_chars": 42, "cell_chars": 18, "max_rows": 5},
    },
    "ablation_comparison.v1": {
        "layout_family": "small_multiples_or_comparison_grid",
        "visual_kind": "matrix",
        "layout_type": "comparison-matrix",
        "copy_limits": {"title_chars": 18, "claim_chars": 42, "cell_chars": 18, "max_rows": 5},
    },
    "risk_boundary.v1": {
        "layout_family": "risk_matrix_with_mitigations",
        "visual_kind": "risk_table",
        "layout_type": "risk-boundary-table",
        "copy_limits": {"title_chars": 18, "claim_chars": 40, "cell_chars": 18, "max_rows": 5},
    },
    "summary_takeaway.v1": {
        "layout_family": "contribution_takeaways",
        "visual_kind": "cards",
        "layout_type": "closing",
        "copy_limits": {"title_chars": 16, "claim_chars": 34, "bullet_chars": 22, "max_bullets": 4},
    },
}


ROLE_TO_SEMANTIC_COMPONENT = {
    "section": "research_agenda.v1",
    "background": "background_trend.v1",
    "motivation": "background_trend.v1",
    "problem": "challenge_quantification.v1",
    "gap": "related_work_matrix.v1",
    "evidence": "experiment_result.v1",
    "experiment": "experiment_result.v1",
    "architecture": "method_overview.v1",
    "mechanism": "technique_detail.v1",
    "comparison": "ablation_comparison.v1",
    "timeline": "risk_boundary.v1",
    "risk": "risk_boundary.v1",
    "summary": "summary_takeaway.v1",
}


LAYOUT_TO_SEMANTIC_COMPONENT = {
    "section-divider": "research_agenda.v1",
    "roadmap": "risk_boundary.v1",
    "problem-framing": "challenge_quantification.v1",
    "gap-matrix": "related_work_matrix.v1",
    "evidence-matrix": "related_work_matrix.v1",
    "experiment-result": "experiment_result.v1",
    "layered-architecture": "method_overview.v1",
    "process-flow": "technique_detail.v1",
    "comparison-matrix": "ablation_comparison.v1",
    "risk-boundary-table": "risk_boundary.v1",
    "closing": "summary_takeaway.v1",
}


def registry_entry(layout_type: str | None, *, slide_index: int | None = None, slide_count: int | None = None) -> dict:
    key = str(layout_type or "").strip().lower()
    if not key:
        if slide_index == 1:
            key = "title-image"
        elif slide_count and slide_index == slide_count:
            key = "closing"
        else:
            key = "problem-framing"
    return deepcopy(LAYOUT_REGISTRY.get(key) or LAYOUT_REGISTRY["problem-framing"])


def component_for_layout(layout_type: str | None, idx: int, total: int) -> str:
    return str(registry_entry(layout_type, slide_index=idx, slide_count=total)["component_id"])


def semantic_component_entry(component_id: str | None) -> dict:
    key = str(component_id or "").strip()
    return deepcopy(SEMANTIC_COMPONENTS.get(key) or {})


def semantic_component_for_slide(slide: dict, idx: int | None = None, total: int | None = None) -> str:
    explicit = str(slide.get("semantic_component_id") or "").strip()
    if explicit in SEMANTIC_COMPONENTS:
        return explicit
    role = str(slide.get("story_role") or "").strip().lower()
    layout = str(slide.get("layout_type") or "").strip().lower()
    title = str(slide.get("title") or "").strip()
    if idx == 2 and title in {"目录", "汇报结构", "Agenda"}:
        return "research_agenda.v1"
    if total and idx == total:
        return "summary_takeaway.v1"
    if ROLE_TO_SEMANTIC_COMPONENT.get(role):
        return ROLE_TO_SEMANTIC_COMPONENT[role]
    if LAYOUT_TO_SEMANTIC_COMPONENT.get(layout):
        return LAYOUT_TO_SEMANTIC_COMPONENT[layout]
    return "key_insight_mechanism.v1"


def visual_type_for_layout(layout_type: str | None) -> str:
    return str(registry_entry(layout_type)["visual_type"])


def requires_evidence(slide: dict) -> bool:
    role = str(slide.get("story_role") or "").strip().lower()
    layout = str(slide.get("layout_type") or "").strip().lower()
    visual = str(slide.get("visual_type") or "").strip().lower()
    chart = slide.get("chart_spec") if isinstance(slide.get("chart_spec"), dict) else {}
    chart_type = str(chart.get("chart_type") or chart.get("type") or "").strip().lower()
    entry = registry_entry(layout)
    return (
        role in EVIDENCE_REQUIRED_ROLES
        or bool(entry.get("requires_evidence"))
        or visual in {"diagram", "table"}
        or (bool(chart) and chart_type not in {"", "none", "null"})
    )


def requires_visual_spec(layout_type: str | None) -> bool:
    return bool(registry_entry(layout_type).get("requires_visual_spec"))


def requires_visual_spec_for_slide(slide: dict, *, slide_index: int | None = None, slide_count: int | None = None) -> bool:
    component_id = semantic_component_for_slide(slide, slide_index, slide_count)
    if component_id in {"research_agenda.v1", "summary_takeaway.v1"}:
        return True
    if component_id in SEMANTIC_COMPONENTS:
        return True
    return requires_visual_spec(slide.get("layout_type"))


def copy_limits(layout_type: str | None) -> dict:
    return deepcopy(registry_entry(layout_type).get("copy_limits") or {})


def compact_text(value, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if limit <= 0 or len(text) <= limit:
        return text
    cut = text[:limit]
    cut = re.sub(r"[，,。；;：:\-/\\|]+$", "", cut).strip()
    return cut or text[:limit].strip()


def compact_list(values, *, limit: int, count: int) -> list[str]:
    out = []
    seen = set()
    for value in values or []:
        text = compact_text(value, limit)
        key = re.sub(r"\s+", "", text).lower()
        if text and key not in seen:
            out.append(text)
            seen.add(key)
        if len(out) >= count:
            break
    return out


def _box_body(slide: dict, key: str) -> list[str]:
    box = slide.get(key) if isinstance(slide.get(key), dict) else {}
    body = box.get("body") or []
    if isinstance(body, str):
        body = [body]
    return [str(item).strip() for item in body if str(item).strip()]


def _candidate_nodes(slide: dict, *, limit: int = 18, count: int = 5) -> list[str]:
    values = []
    for key in ("claim", "key_message", "evidence_sentence"):
        if slide.get(key):
            values.append(slide[key])
    values.extend(slide.get("bullets") if isinstance(slide.get("bullets"), list) else [])
    values.extend(_box_body(slide, "left_box"))
    values.extend(_box_body(slide, "right_box"))
    return compact_list(values, limit=limit, count=count)


def _semantic_defaults(component_id: str) -> dict:
    return deepcopy(SEMANTIC_COMPONENTS.get(component_id) or {})


def _semantic_kind(component_id: str, fallback: str) -> str:
    entry = _semantic_defaults(component_id)
    return str(entry.get("visual_kind") or fallback or "cards")


def synthesize_content_blocks(slide: dict, *, slide_index: int | None = None, slide_count: int | None = None) -> list[dict]:
    """Build compact explanation blocks when the model under-specifies a page.

    These blocks are not a replacement for the model plan; they preserve the
    slide-specific claim/evidence text and give the renderer enough material to
    avoid empty side panels after a fallback repair.
    """
    component_id = semantic_component_for_slide(slide, slide_index, slide_count)
    nodes = _candidate_nodes(slide, limit=34, count=8)
    claim = compact_text(slide.get("claim") or slide.get("key_message") or slide.get("title"), 46)
    evidence = compact_text(slide.get("evidence_sentence") or "", 44)
    left_body = compact_list(_box_body(slide, "left_box"), limit=34, count=3)
    right_body = compact_list(_box_body(slide, "right_box"), limit=34, count=3)

    def take(start: int, count: int, fallback: list[str]) -> list[str]:
        values = nodes[start:start + count]
        values = values or fallback
        return compact_list(values, limit=34, count=count)

    if component_id == "research_agenda.v1":
        agenda = take(0, 6, ["背景与趋势", "关键瓶颈", "现有不足", "核心方法", "实验验证", "总结展望"])
        return [{"role": "agenda", "heading": "汇报结构", "body": agenda}]
    if component_id == "background_trend.v1":
        return [
            {"role": "mechanism", "heading": "趋势", "body": take(0, 2, [claim])},
            {"role": "evidence", "heading": "证据", "body": take(2, 2, left_body or [evidence or claim])},
            {"role": "implication", "heading": "含义", "body": take(4, 2, right_body or ["趋势正在改变系统瓶颈"])}
        ]
    if component_id == "challenge_quantification.v1":
        return [
            {"role": "evidence", "heading": "量化现象", "body": take(0, 2, left_body or [claim])},
            {"role": "mechanism", "heading": "成因", "body": take(2, 2, right_body or ["开销来自状态维护与搬运"])},
            {"role": "implication", "heading": "后果", "body": take(4, 2, ["延迟、成本和质量目标相互牵制"])}
        ]
    if component_id == "related_work_matrix.v1":
        return [
            {"role": "mechanism", "heading": "已有方法", "body": take(0, 2, left_body or ["按优化对象分组比较"])},
            {"role": "boundary", "heading": "不足", "body": take(2, 2, right_body or ["缺少统一状态流建模"])},
            {"role": "implication", "heading": "空白", "body": take(4, 2, [claim])}
        ]
    if component_id == "key_insight_mechanism.v1":
        return [
            {"role": "mechanism", "heading": "核心机制", "body": take(0, 2, [claim])},
            {"role": "evidence", "heading": "支撑依据", "body": take(2, 2, left_body or [evidence or "来自调研资料的共同模式"])},
            {"role": "implication", "heading": "设计含义", "body": take(4, 2, right_body or ["后续页面据此展开技术路线"])}
        ]
    if component_id == "method_overview.v1":
        return [
            {"role": "mechanism", "heading": "输入/状态", "body": take(0, 2, ["任务上下文与状态对象"])},
            {"role": "mechanism", "heading": "资源映射", "body": take(2, 2, ["端边云/异构存储分层承载"])},
            {"role": "implication", "heading": "输出指标", "body": take(4, 2, ["延迟、成本、质量和一致性"])}
        ]
    if component_id == "technique_detail.v1":
        return [
            {"role": "mechanism", "heading": "解决对象", "body": take(0, 2, [claim])},
            {"role": "mechanism", "heading": "执行路径", "body": take(2, 2, left_body or ["识别热状态并减少重复搬运"])},
            {"role": "boundary", "heading": "代价边界", "body": take(4, 2, right_body or ["需要处理一致性与调度开销"])}
        ]
    if component_id == "experiment_result.v1":
        return [
            {"role": "evidence", "heading": "结果读数", "body": take(0, 2, [claim])},
            {"role": "mechanism", "heading": "对比基线", "body": take(2, 2, left_body or ["与 full context / naive baseline 比较"])},
            {"role": "boundary", "heading": "局限", "body": take(4, 2, right_body or ["需扩大 workload 和硬件配置验证"])}
        ]
    if component_id == "ablation_comparison.v1":
        return [
            {"role": "evidence", "heading": "变量", "body": take(0, 2, ["控制单一优化开关"])},
            {"role": "mechanism", "heading": "差异", "body": take(2, 2, left_body or [claim])},
            {"role": "implication", "heading": "结论", "body": take(4, 2, right_body or ["定位最值得保留的机制"])}
        ]
    if component_id == "risk_boundary.v1":
        return [
            {"role": "boundary", "heading": "风险", "body": take(0, 2, left_body or ["状态一致性与检索误差"])},
            {"role": "mechanism", "heading": "触发条件", "body": take(2, 2, ["长任务、多工具和多副本状态"])},
            {"role": "implication", "heading": "缓解", "body": take(4, 2, right_body or ["通过评测与回退策略控制风险"])}
        ]
    if component_id == "summary_takeaway.v1":
        return [
            {"role": "summary", "heading": "问题", "body": take(0, 1, [claim])},
            {"role": "summary", "heading": "方法", "body": take(1, 1, ["围绕状态流组织技术路线"])},
            {"role": "summary", "heading": "价值", "body": take(2, 1, ["为后续系统评测和优化提供入口"])}
        ]
    return [
        {"role": "mechanism", "heading": "判断", "body": take(0, 2, [claim])},
        {"role": "evidence", "heading": "依据", "body": take(2, 2, [evidence or claim])},
        {"role": "implication", "heading": "含义", "body": take(4, 2, ["支撑下一步页面展开"])}
    ]


def synthesize_slide_composition(slide: dict, *, slide_index: int | None = None, slide_count: int | None = None) -> dict:
    component_id = semantic_component_for_slide(slide, slide_index, slide_count)
    entry = semantic_component_entry(component_id)
    claim = compact_text(slide.get("claim") or slide.get("key_message") or slide.get("title"), 72)
    evidence = compact_text(slide.get("evidence_sentence") or "", 72)
    blocks = synthesize_content_blocks(slide, slide_index=slide_index, slide_count=slide_count)
    block_roles = [str(item.get("role") or "") for item in blocks if isinstance(item, dict)]
    evidence_kind = {
        "research_agenda.v1": "outline",
        "background_trend.v1": "trend_or_scale",
        "challenge_quantification.v1": "metric_or_formula",
        "related_work_matrix.v1": "comparison",
        "key_insight_mechanism.v1": "mechanism",
        "method_overview.v1": "architecture",
        "technique_detail.v1": "design_detail",
        "experiment_result.v1": "quantitative_result",
        "ablation_comparison.v1": "controlled_comparison",
        "risk_boundary.v1": "risk_matrix",
        "summary_takeaway.v1": "takeaway",
    }.get(component_id, "mechanism")
    return {
        "semantic_component_id": component_id,
        "layout_family": entry.get("layout_family") or "",
        "claim_to_prove": claim,
        "evidence_need": evidence_kind,
        "evidence_available": bool(evidence or slide.get("citations") or slide.get("source_references") or slide.get("chart_spec")),
        "primary_visual_role": str(entry.get("visual_kind") or "cards"),
        "required_blocks": block_roles[:4],
        "density_target": slide.get("visual_density") or "medium",
        "avoid": ["single_empty_chart", "template_asset_copy", "generic_cards_only"],
    }


def _table_from_slide(slide: dict, layout_type: str) -> list[list[str]]:
    left = slide.get("left_box") if isinstance(slide.get("left_box"), dict) else {}
    right = slide.get("right_box") if isinstance(slide.get("right_box"), dict) else {}
    left_body = _box_body(slide, "left_box")
    right_body = _box_body(slide, "right_box")
    layout = str(layout_type or "").lower()
    if "risk" in layout:
        defaults = ["量化精度", "算子适配", "I/O开销", "供应链"]
        mitigations = ["回归测试/混合精度", "trace分类", "异步预取/批量搬运", "软件优先"]
        rows = [["风险", "边界条件", "缓解动作"]]
        merged = left_body + right_body
        for i, risk in enumerate(defaults):
            rows.append([risk, compact_text(merged[i] if i < len(merged) else "需结合实测确认", 18), mitigations[i]])
        return rows
    if "comparison" in layout:
        rows = [["维度", compact_text(left.get("heading") or "方案A", 12), compact_text(right.get("heading") or "方案B", 12)]]
        for i in range(max(3, min(4, max(len(left_body), len(right_body))))):
            rows.append([
                f"要点{i + 1}",
                compact_text(left_body[i] if i < len(left_body) else "", 20),
                compact_text(right_body[i] if i < len(right_body) else "", 20),
            ])
        return rows
    rows = [["类别", "判断", "依据"]]
    nodes = _candidate_nodes(slide, limit=22, count=4)
    refs = slide.get("citations") or slide.get("source_references") or [""]
    ref_label = citation_marker(str(refs[0])) if refs else ""
    for i, node in enumerate(nodes[:4]):
        rows.append([f"证据{i + 1}", node, compact_text(ref_label, 14)])
    return rows


def _chart_from_slide(slide: dict) -> dict:
    chart = slide.get("chart_spec") if isinstance(slide.get("chart_spec"), dict) else {}
    labels = chart.get("x") or chart.get("labels") or chart.get("categories") or []
    values = chart.get("y") or chart.get("values") or chart.get("series") or []
    if labels and values:
        return {
            "type": str(chart.get("chart_type") or chart.get("type") or "bar").lower(),
            "title": compact_text(chart.get("title") or slide.get("title"), 24),
            "labels": [compact_text(x, 14) for x in labels][:6],
            "values": values[:6] if isinstance(values, list) else values,
            "unit": chart.get("unit") or chart.get("y_unit") or "",
            "citation": chart.get("citation") or chart.get("data_source") or slide.get("citations") or [],
        }
    return {}


def synthesize_visual_spec(slide: dict, *, slide_index: int | None = None, slide_count: int | None = None) -> dict:
    layout_type = str(slide.get("layout_type") or "").strip().lower()
    entry = registry_entry(layout_type, slide_index=slide_index, slide_count=slide_count)
    semantic_component_id = semantic_component_for_slide(slide, slide_index, slide_count)
    semantic_entry = semantic_component_entry(semantic_component_id)
    kind = _semantic_kind(semantic_component_id, str(entry.get("visual_kind") or "cards"))
    limits = semantic_entry.get("copy_limits") or entry.get("copy_limits") or {}
    chart = _chart_from_slide(slide)
    if chart and kind in {"table", "matrix", "cards"}:
        kind = "line_chart" if "line" in str(chart.get("type")) else "bar_chart"
    spec = {
        "kind": kind,
        "layout_type": layout_type or None,
        "semantic_component_id": semantic_component_id,
        "layout_family": semantic_entry.get("layout_family"),
        "purpose": compact_text(slide.get("visual_intent") or slide.get("claim") or slide.get("title"), 64),
        "editable": True,
        "constraints": {
            "max_text_per_node": int(limits.get("node_chars") or limits.get("bullet_chars") or 18),
            "max_rows": int(limits.get("max_rows") or 5),
            "max_items": int(limits.get("max_nodes") or limits.get("max_stages") or limits.get("max_bullets") or 4),
        },
    }
    if kind in {"table", "matrix", "risk_table"}:
        spec["data"] = {"rows": _table_from_slide(slide, layout_type)}
    elif kind in {"bar_chart", "line_chart"}:
        if not chart:
            nodes = _candidate_nodes(slide, limit=12, count=4)
            labels = nodes[:4] or ["背景", "瓶颈", "方案", "验证"]
            values = [1, 2, 3, 4]
            if semantic_component_id == "challenge_quantification.v1":
                labels, values = ["上下文", "工具等待", "状态搬运", "一致性"], [3, 2, 4, 2]
            elif semantic_component_id == "background_trend.v1":
                labels, values = ["单轮问答", "工具调用", "长链路", "多Agent"], [1, 2, 3, 4]
            elif semantic_component_id == "experiment_result.v1":
                labels, values = ["Baseline", "KV复用", "分层状态", "组合策略"], [4, 3, 2, 1]
            chart = {
                "type": "bar",
                "title": compact_text(slide.get("claim") or slide.get("title"), 24),
                "labels": labels,
                "values": values,
                "unit": "",
                "citation": slide.get("citations") or [],
                "synthetic_structure": True,
            }
        spec["data"] = chart
    elif kind == "roadmap":
        stages = _candidate_nodes(slide, limit=int(limits.get("stage_chars") or 18), count=4)
        while len(stages) < 4:
            stages.append(["启动验证", "机制增强", "系统集成", "规模落地"][len(stages)])
        spec["stages"] = [{"label": f"阶段{i + 1}", "text": text} for i, text in enumerate(stages[:4])]
    elif kind in {"flow", "architecture", "timeline"}:
        nodes = _candidate_nodes(slide, limit=int(limits.get("node_chars") or 18), count=5)
        if kind == "architecture" and len(nodes) < 4:
            nodes.extend(["应用状态", "调度策略", "异构介质", "监控反馈"])
        if kind == "flow" and len(nodes) < 4:
            nodes.extend(["输入状态", "策略判断", "资源执行", "反馈更新"])
        spec["nodes"] = [{"id": f"n{i + 1}", "label": text} for i, text in enumerate(nodes[:5])]
        spec["edges"] = [{"from": f"n{i + 1}", "to": f"n{i + 2}"} for i in range(max(0, min(len(nodes), 5) - 1))]
    else:
        spec["nodes"] = [{"id": f"n{i + 1}", "label": text} for i, text in enumerate(_candidate_nodes(slide, limit=24, count=4))]
    return spec


def visual_spec_is_usable(spec: dict | None) -> bool:
    if not isinstance(spec, dict) or not spec.get("kind"):
        return False
    kind = str(spec.get("kind") or "")
    data = spec.get("data") if isinstance(spec.get("data"), dict) else {}
    if kind in {"table", "matrix", "risk_table"}:
        return len(data.get("rows") or []) >= 2
    if kind in {"bar_chart", "line_chart"}:
        if data.get("placeholder") and (data.get("labels") or data.get("rows")):
            return True
        return bool(data.get("labels") and data.get("values"))
    if kind in {"roadmap", "timeline"}:
        return bool(spec.get("stages"))
    if kind in {"flow", "architecture", "cards"}:
        return bool(spec.get("nodes"))
    return True
