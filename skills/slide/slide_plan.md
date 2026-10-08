# Slide Plan Skill (cascade-aligned)

Author the per-page construction blueprint AFTER slide_matching. One row per
target page, in the same order as ``target_pages`` in your input. This stage
combines what used to be three stages (STORY_STRATEGY / REUSE_OUTLINE /
REUSE_DECISION_AUDIT) into a single thoughtful pass — every page already has
a candidate reuse binding from the cascade, your job is to:

1. Write the page's functional title + claim (the model-authored content)
2. Confirm or downgrade the reuse decision
3. For unmatched pages, write a clear ``plan_note`` saying what content to fill in

## Inputs (matches stage_runner._run_slide_plan)

```json
{
  "idea_analysis": {
    "topic": "...",
    "audience": "...",
    "scenario": "...",
    "slide_count": 50,
    "story_style": "项目预期叙事 (分点或一段)",
    "anchor_claims": ["..."],
    "chapter_page_archetype_plan": [
      {
        "chapter": "背景与动机",
        "expected_pages": 4,
        "page_archetypes": [
          {
            "archetype": "趋势数据图页",
            "count": 1,
            "placement": "本章 1/4 页",
            "purpose": "为什么必须做软硬件协同优化",
            "key_question": "推理算力需求增长曲线为何陡峭",
            "expected_visual_form": "时序柱图 + 数字标注"
          }
        ]
      }
    ]
  },
  "target_pages": [
    {
      "target_slide_index": 1,
      "target_role": "cover | agenda | motivation | problem | method | result | comparison | closing | references | content",
      "target_claim_hint": "(可空)",
      "source_resource_id": "tpl.xxx.slide_03 | null",
      "source_owner": "library | project | null",
      "deck_id": "tpl.xxx",
      "section_id": "tpl.xxx.sec.02",
      "recommended_reuse_mode": "direct_slide_reuse | partial_slide_reuse | style_only",
      "must_rewrite": ["...", "..."],
      "match_reason": "...",
      "plan_note_hint": "(可空)",
      "confidence": 0.85
    },
    ...
  ],
  "section_matches_brief": [
    {"target_section_index": 2, "target_section_purpose": "核心挑战", "resource_id": "tpl.xxx.sec.03"}
  ]
}
```

## Output: `slide-plan.json`

```json
{
  "slides": [
    {
      "slide_index": 1,
      "target_title": "封面",
      "target_role": "cover",
      "target_claim": "",
      "page_purpose": "封面 + 课题组署名（不需要论证）",
      "proof_structure": [],
      "plan_note": "",
      "reuse_binding": {
        "resource_id": "tpl.xxx.slide_03 | null",
        "reuse_mode": "direct_slide_reuse | partial_slide_reuse | style_only | none",
        "source_owner": "library | project | null",
        "deck_id": "tpl.xxx | null",
        "section_id": "tpl.xxx.sec.02 | null",
        "must_rewrite": ["title", "..."]
      },
      "reuse_bindings": "<deterministic — full top-3 candidates list from SLIDE_MATCHING; do not modify>",
      "evidence_need": [],
      "citation_need": false
    }
  ]
}
```

**Note**: `reuse_bindings` (plural) is a deterministic field — it holds the
complete 1-3 candidate list from SLIDE_MATCHING (rank, resource_id, score,
parts_to_reuse, parts_to_drop, relation_to_others, gap_explanation, etc.).
**You do not write or modify this field**; it is filled in by stage_runner
post-processing for downstream DRAFT_ASSEMBLY consumption. The single
`reuse_binding` (singular) above mirrors candidates[0] (primary) and is what
you should reference when writing target_claim / page_purpose.

## Hard rules

- Output ONE row per ``target_pages[i]``, **same order, same count**.
- ``target_title``: 短功能标题，≤14 字 (zh) or ≤7 words (en)。不要把 claim 当 title。
- ``target_claim``: 必须是判断句，≤45 字。下列 role 允许空字符串：cover, agenda, closing, references, thanks。
- ``page_purpose``: 一句话说明本页在叙事弧中承担什么作用。
- ``proof_structure``: 1-3 短句描述论证步骤（cover/agenda 可空）。
- ``reuse_binding.resource_id``: 必须等于 ``target_pages[i].source_resource_id`` 或 null。**禁止换源**。
- ``reuse_binding.reuse_mode``: 与 ``target_pages[i].recommended_reuse_mode`` 一致；当 source_resource_id=null 时必须为 "none"。
- ``plan_note``: 当 source_resource_id=null 时**必填**，≤80 字，描述本页该补什么内容（DRAFT_ASSEMBLY 会把这段批注写到 placeholder 页和 speaker notes）。其余 row 可空。
- **关键 (Phase E.A): `chapter_page_archetype_plan` 是本阶段的硬约束**:
  - 每个 target_page 都属于某 chapter; 该 chapter 的 page_archetype 已经预设好了
    每页的 archetype/purpose/key_question/expected_visual_form
  - target_title / target_claim / page_purpose / proof_structure 必须**承袭并细化**
    本页对应 archetype 的 purpose 与 key_question, 不能瞎编一个新方向
  - `expected_visual_form` 是 SLIDE_REWRITE 阶段 visual-plan 的种子, 不要在本阶段改写
- **(Phase O, 2026-06-27): 若 target_pages[i] 含 `source_resource_ids` (list, 非空)**:
  该页 `proof_structure` 与下游 SLIDE_REWRITE body 必须引用这些 resource_id 对应的资料 (论文标题
  / 关键图表 / 可引用片段)。OUTLINE 阶段已代码预分配, 不要扔掉。
- Output strict JSON only.

## Tone

- 中文项目用中文；英文项目用英文。
- target_title 用名词短句，不用"介绍 XX"。
- 不虚构数据、年份、机构名。
