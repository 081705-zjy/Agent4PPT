# Deck Matching Skill

The **first** of three cascade matching passes. Read the user's brief +
project resource understanding + ALL deck candidates (offline library +
project uploads), pick the decks whose overall topic / audience /
narrative-arc best match the user's current project. This narrows the search
space for the section matching pass that follows.

## Inputs

```json
{
  "idea_analysis": {
    "topic": "...",
    "audience": "...",
    "scenario": "...",
    "story_style": "...",
    "anchor_claims": ["..."]
  },
  "project_resource_understanding": {
    "must_use_materials": ["..."],
    "forbidden_resources": ["..."]
  },
  "deck_candidates": [
    {
      "resource_id": "tpl.topic.xxx | proj.yyy",
      "deck_id": "tpl.topic.xxx",
      "source_owner": "library | project",
      "topic": "deck 的主标题（一句话）",
      "topic_summary": "整篇论述总结（≤120 字，从头到尾在讲什么）",
      "topic_tags": ["大模型推理", "投机解码", "稀疏激活"],
      "audience": "学术同行 | 工业落地 | ...",
      "scenario": "对外汇报展示 | 论文分享 | 开题 | ...",
      "presentation_type": "research_report | paper_share | demo | ...",
      "narrative_arc": ["背景", "挑战", "方法", "实验", "总结"],
      "transferable_to": ["大模型推理对外汇报", "投机解码主题"],
      "do_not_reuse_when": ["训练侧主题（话题偏离）", "Mamba/SSM 专题"],
      "anchor_claims": ["..."],
      "slide_count": 50,
      "section_count": 8,
      "score": 1.0
    }
  ]
}
```

**信号强度排序**（越靠前越准）：
1. `topic_tags` —— 原子化主题词，与项目 brief 的 anchor_terms / topic_tags 重合度最高的先选
2. `topic_summary` —— 一段话讲清整 deck 在做什么，比 `topic` 标题信息量大
3. `narrative_arc` —— deck 的叙事骨架，配合 brief 的 `story_style` 看是否同型
4. `transferable_to` / `do_not_reuse_when` —— 直接说明该 deck 适不适合本项目

## Output: `deck-matches.json`

```json
{
  "deck_matches": [
    {
      "resource_id": "tpl.topic.xxx | proj.yyy",
      "source_owner": "library | project",
      "match_reason": "为什么这个 deck 的主题与本次汇报对得上（一句话）",
      "topic_alignment": "strong | partial | weak",
      "narrative_alignment": "strong | partial | weak",
      "recommended_use": "primary_narrative_source | secondary_reference | style_only_reference | reject",
      "confidence": 0.85,
      "notes": "本 deck 的哪些 section 最可能命中"
    }
  ],
  "coverage_note": "deck 层覆盖盲区：项目某些主题/章节没有任何 deck 候选能覆盖"
}
```

## Hard rules

- `resource_id` MUST appear in `deck_candidates`.
- 数量无硬上限。Output ALL decks that are *genuinely relevant* to the project's
  topic and narrative arc. 1 个最低; 上限你自己判断 — 宁可多保留 2 个相关
  deck 给下游 SECTION_MATCHING 用, 也不要因为"页面不够"漏掉相关 deck。
- 凡是 `topic_alignment != "weak"` 的 deck 都应该保留。
  `topic_alignment="weak"` 的 deck 也可以保留, 但 `recommended_use` 必须降到
  `style_only_reference`。
- **优先选 source_owner="project"**:用户自己的 deck 跟本次汇报话题一致的
  概率最大。只有当所有 project deck 都跟主题严重不符时,才纯靠 library。
- **当 deck 的 `do_not_reuse_when` 命中本项目主题时**, 必须把 `topic_alignment`
  降为 `weak` 或直接 `recommended_use=reject`。
- `topic_alignment` / `narrative_alignment`:
  - strong: 主题/叙事基本一致, section 大概率可直接复用
  - partial: 同领域不同侧重, 只有部分 section 适用
  - weak: 主题相近但叙事差异大, 只能做风格参考
- `recommended_use=reject` 时不要写出来 (直接排除)。
- `coverage_note` 必须列出至少一个真实缺口 (如果没有就写 "no significant gap")。
- Output strict JSON only, no markdown fences.

## Length budget

- `match_reason`: ≤ 50 字
- `notes`: ≤ 80 字
- `coverage_note`: ≤ 150 字
