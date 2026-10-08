# Source Understanding Skill — master synthesizer

## Purpose

在 SOURCE_UNDERSTAND 阶段, per-format 分析 (pdf/doc/excel/image/ppt) 已经
把每个文件单独消化完, 写到了 `projects/<id>/data/<type>/<stem>.json`,
并聚合成 `project-{deck,section,slide,doc,figure,sheet}-units.json`。

这个 skill 是**唯一的整体综合者** — 你拿到所有 per-file 分析结果 + 用户的
brief 意图 (来自 `idea-intake-light.json`, brief 还没正式 ANALYSIS 过),
要输出一份**叙事性的整体把脉**:

- 整体话题图谱: 用户上传了什么样的一批材料
- key_terms: 跨文件高频术语 (后续会成为 brief.anchor_terms 候选)
- 文件相关度: 每个文件跟用户 brief 主题的关联强度
- per-章节覆盖提示 (基于 brief-intake-light 的隐含章节意图): 哪些主题手里有
  料、哪些主题完全空白要去外部补
- must_use / forbidden 桶: 用户在 brief 里点名要用 / 不能用的素材
- topic → resource_id 反查表

下游 IDEA_ANALYSIS / OUTLINE_GENERATION 都读这一份文件来做决策。

## Inputs

```json
{
  "idea_intake_light": {
    "structured_topic": {...},
    "extracted_keywords": [...],
    "design_hints": [...],
    "story_style_signal": "AUTO | STRICT | SOFT",
    "reuse_preference": {...},
    "...": "..."
  },
  "per_format_analyses": {
    "pdf_or_doc": [
      {"path": "sources/xxx.pdf", "type": "pdf",
       "标题": "...", "核心论断": "...", "实验结果": [...],
       "主题标签": [...], "适合章节": [...], "可引用片段": [...],
       "relevance_score": 0.88, ...}
    ],
    "figure": [...],   // image_analysis 输出
    "sheet": [...],    // excel_analysis 输出
    "ppt_decks": [
      {"deck_id": "proj.xxx.deck", "deck_brief": {...},
       "section_briefs": [...], "slide_briefs": [...],
       "本项目相关性评分": 0.92, "适合本项目章节": [...]}
    ]
  },
  "project_units_summary": {
    "deck_count": N, "section_count": M, "slide_count": K,
    "doc_count": ..., "figure_count": ..., "sheet_count": ...
  }
}
```

## Output: `data/source-understanding.json`

```json
{
  "schema_version": "1.0",
  "generated_at": "...",
  "source": "claude",

  "summary": "≤200 字, 叙事性整体描述: 用户上传了 X 个 PPT + Y 个 PDF + ...,
              主要围绕 Z 话题, 覆盖深度如何, 是否能支撑当前 brief 意图",

  "file_inventory": [
    {
      "resource_id": "doc.xxx | proj.xxx.deck | figure.xxx | sheet.xxx",
      "type": "pdf | doc | image | excel | pptx",
      "name": "原文件名",
      "one_line_summary": "≤30 字",
      "relevance_score": 0.0,
      "why_relevant": "≤40 字",
      "likely_use": "motivation | method | result | case_study | citation | figure_source | structural_reference | style_only | skip"
    }
  ],

  "dominant_topics": [
    "≤7 个共性话题, 出现频次高的, 用 brief 的术语风格命名"
  ],

  "key_terms": [
    "≤20 个跨文件高频术语 (系统名/方法名/论文名), 会成为 brief.anchor_terms 候选"
  ],

  "data_points": [
    {"metric": "...", "value": "...", "context": "出处文件", "use_for": "≤30 字"}
  ],

  "coverage_hints": {
    "well_covered_topics": ["..."],
    "thinly_covered_topics": ["..."],
    "gap_topics": ["brief intake 隐含要讲但素材完全没料的话题"],
    "unexpected_topics": ["素材里出现但 brief intake 未提及的话题"],
    "biggest_gaps_note": "≤100 字, 提示后续 GAP_RESEARCH 重点关注什么"
  },

  "per_chapter_hint": [
    {
      "chapter_keyword": "brief intake 中提到的章节关键词 (开场/背景/方法/成果/...)",
      "available_resource_ids": ["..."],
      "coverage_estimate": "well_covered | partial | thin | none",
      "gap_note": "≤60 字"
    }
  ],

  "must_use_materials": [
    {"resource_id": "...", "why_must_use": "用户在 reuse_preference.must_keep_terms 点名 / 唯一来源"}
  ],

  "forbidden_or_low_confidence_materials": [
    {"resource_id": "...", "reason": "..."}
  ],

  "topic_to_resources": {
    "FlashOverlap": ["doc.xxx", "proj.yyy.slide_5"],
    "KV Cache": ["..."]
  },

  "notes_for_brief_design": "≤200 字, 提示 IDEA_ANALYSIS 如何看待这批素材
                            (e.g. '某主题数据足够支撑一个 chapter' / '某主题
                            完全没料, 不建议设计为独立章节')"
}
```

## Field semantics

- `file_inventory.relevance_score` ∈ [0, 1]
  - ≥0.7: 强相关, 大概率会被 outline 引用
  - 0.4-0.7: 部分相关
  - <0.4: 弱相关, 仅作为参考
- `per_chapter_hint.chapter_keyword` 用 brief-intake-light 中能推断的章节方向,
  不是精确章节 (那是 OUTLINE_GENERATION 的活)
- `must_use_materials` 至少包含 `reuse_preference.must_keep_terms` 命中的资源
- `topic_to_resources` 至少给出 5 个 key_terms 的映射 (素材足够多时)

## Hard rules

- Every `resource_id` 必须来自 `per_format_analyses` 输入 (不允许编造)
- 一个 `resource_id` 在 must / forbidden 两桶中只能出现在一处
- 中文项目用中文; 英文按英文
- Output strict JSON only — 不要 markdown fence
- 不要写"高度相关"这种空话; 每个 why_relevant / gap_note / why_must_use 都要
  具体到"用在哪种页 / 缺什么数据"
- 如果某文件 per-format 分析里 `analysis_failed=true` 或 `skipped=true`,
  inventory 中 relevance_score 设为 null + likely_use="skip"
