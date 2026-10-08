# Section Matching Skill

The **second** of three cascade matching passes. Runs after deck_matching.
Read the brief + sections from DECKS THAT WERE PICKED + the project's intended
narrative arc, and select the sections that map to the user's project.

This is where you bind "the project's chapter X" to "deck A's section Y" —
the assumption is that a deck has already been chosen because its overall
topic matches, so now you're saying "within this matched deck, this section
discusses what my project's chapter wants to say".

## Inputs

```json
{
  "idea_analysis": {
    "topic": "...",
    "story_style": "项目预期叙事弧 (一句话/分点)",
    "expected_sections": [
      {"section_index": 1, "purpose": "背景动机：..."},
      {"section_index": 2, "purpose": "核心挑战：..."}
    ]
  },
  "matched_decks": [
    {"resource_id": "tpl.xxx", "topic": "...", "narrative_arc": ["..."]}
  ],
  "section_candidates": [
    {
      "resource_id": "tpl.xxx.sec.03",
      "deck_id": "tpl.xxx",
      "source_owner": "library | project",
      "section_index": 3,
      "role": "motivation | method | result | ...",
      "title": "研究背景与动机",
      "function": "本 section 是干什么的（一句话）",
      "summary": "本 section 章节叙事 (含与上一 section 的承接关系)",
      "slide_relationships": [
        "slide 3 → slide 4: 由 token 量级图引出训练 vs 推理算力对比",
        "slide 4 → slide 5: 由算力对比转入推理瓶颈三连"
      ],
      "transferable_to": ["大模型推理 motivation 章节", "..."],
      "do_not_reuse_when": ["数据已过时", "..."],
      "slide_ids": ["slide_03", "slide_04"],
      "page_range": [3, 8],
      "score": 1.0
    }
  ]
}
```

**信号强度排序**（越靠前越准）：
1. `slide_relationships` —— 章内 slide 间的过渡逻辑链, 是判断"本 section 能否承担目标章节"
   的最关键信号. 若链路与目标章节的 `purpose` 内部叙事吻合, 说明该 section 整体可
   套用. 若链路偏离, 即便 role 一致也不该选.
2. `summary` (章节叙事) —— 描述本章在 deck 全局的位置 + 内部如何展开
3. `transferable_to` / `do_not_reuse_when` —— 章节级别复用建议（与 deck 级别可能不同）
4. `role` + `section_index` —— 角色/位置匹配

## Output: `section-matches.json`

```json
{
  "section_matches": [
    {
      "resource_id": "tpl.xxx.sec.03",
      "deck_id": "tpl.xxx",
      "source_owner": "library | project",
      "target_section_index": 2,
      "target_section_purpose": "本次汇报第 2 章节的角色（如『核心挑战』）",
      "match_reason": "为什么这个 section 能承担本项目这个章节（一句话）",
      "purpose_alignment": "strong | partial | weak",
      "content_overlap_score": 0.78,
      "recommended_use": "primary_source | reference_only | style_only",
      "expected_slide_count": 3,
      "must_rewrite_in_this_section": ["原 deck 中需要替换的标签或措辞"],
      "confidence": 0.8
    }
  ],
  "uncovered_target_sections": [
    {"target_section_index": 4, "reason": "没有候选 section 覆盖本项目这一章节"}
  ]
}
```

## Hard rules

- `resource_id` MUST be from `section_candidates`.
- `deck_id` MUST be one of `matched_decks[].resource_id`.
- **宽进策略 (wide intake)**: 保留所有同时满足以下两个维度任一的 section，**不限数量**:
  - `purpose_alignment ∈ {strong, partial}` — section 在源 deck 中扮演的功能角色和本目标章节相符 (motivation→motivation, method→method 等)
  - **OR** `content_overlap_score >= 0.5` — section 主题/关键术语和本目标章节内容重叠
  - 同时满足两者更佳；只满足其一也保留
  - 仅剔除 `purpose_alignment=weak AND content_overlap_score<0.4` 的明显不相关 section
- **一对多是常态而非例外**: 一个 target_section_index 通常对应 3-8 个 source section。
  几页一组拼合是 SLIDE_MATCHING 的工作；本阶段宽进让下游有充足候选池。
- **优先选 source_owner="project"**: 项目自己 deck 的 section 更对得上。
- `purpose_alignment`:
  - strong: section 的 role/function 与 target_chapter.purpose 高度对齐
  - partial: 部分功能相符，可作辅助
  - weak: 功能不符，仅内容相关
- `content_overlap_score` (0.0-1.0): section 的 title/summary/transferable_to 中包含
  brief.anchor_terms / topic_tags / target_chapter 关键词的密度。一致性强 → 接近 1.0。
- `expected_slide_count` = 你估计本目标章节会从该 source section 引用几页。
  - 受众/时间/章节深度共同决定。
  - 同一 target_section_index 下多个 source section 的 expected_slide_count 累计可以
    略超目标页数 (下游 SLIDE_MATCHING 会按需 top-K 选择)。
- `recommended_use`:
  - primary_source: 该 section 是本目标章节的主要素材来源
  - reference_only: 仅作为内容参考, 需要重新组织
  - style_only: 只学版式不复用内容
- `uncovered_target_sections` 列出**完全没有任何候选**的目标章节 (下一步会生成
  new_slide_placeholder 页)。宽进后这个列表应当很短甚至为空。
- Output strict JSON only.

## Length budget

- `match_reason`: ≤ 60 字
- `target_section_purpose`: ≤ 30 字
- `must_rewrite_in_this_section`: ≤ 4 项，每项 ≤ 20 字
