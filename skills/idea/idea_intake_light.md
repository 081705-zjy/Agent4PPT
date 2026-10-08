# Brief Intake Light Skill (v2.1)

## Purpose

对用户在 BRIEF 阶段填写的回答做**轻量结构化分析**, 把粗糙的原始输入整理成下游
可用的结构化"用户意图地图"。

**不复杂、不做设计、不引入额外信息**, 只做"结构化提炼"。

v2.1 (2026-07-30) 进一步精简: 删掉 raw_user_input (下游 0 使用; OUTLINE 唯一需要
的 user_outline 直接从 question-state 读)。

v2.0 (2026-07-30) 删掉 0 下游使用的字段（citation_preference / style_signal /
design_hints / missing_information / notes_for_downstream / scenario_type.formality
/ pattern_matching_hints.key_works_or_methods / audience_familiarity_with_topic /
reuse_preference.scope_keywords), 把 pattern_matching_hints 里有用的 2 项摊到顶层.

## Inputs

```json
{
  "question_state": {
    "answers": {
      "topic": "...",
      "audience": "...",
      "scenario": "...",
      "language": "zh",
      "slide_count": "50",
      "duration_minutes": "60",
      "style": "...",
      "story_style": "",           // 可空 (AUTO mode)
      "user_outline": "",
      "reuse_policy": "...",
      "citation_policy": "..."
    }
  },
  "resource_library_contract": { ... }  // logic/rule enum reference for keyword hints
}
```

## Output: `idea-intake-light.json` (v2.1)

**严格 JSON, 无 code fence, 顶层字段只列以下 10 个**（driver 会补 schema_version / generated_at / source，你不用输出）:

```json
{
  "schema_version": "2.0",

  "topic": {
    "subject": "<≤20 字, 用户 topic 的主语 / 核心议题>",
    "sub_topics": ["<2-5 个子话题, 从 topic / story_style / reuse_policy 提取>"],
    "deliverable_type": "paper_share | research_report | tutorial | proposal | other"
  },

  "audience": {
    "primary": "<一句话描述>",
    "background_tags": ["<3-6 个标签>"],
    "depth": "shallow | medium | deep",
    "jargon_tolerance": "low | medium | high"
  },

  "scenario": {
    "category": "internal_share | external_share | open_talk | proposal_defense | onboarding | other",
    "duration_minutes": <int from answers>,
    "slide_count": <int from answers>
  },

  "keywords": [
    "<10-20 个关键术语 / 名词性短语, 从 topic + story_style + reuse_policy 提取>"
  ],

  "story_mode": "AUTO | STRICT | SOFT",

  "narrative_signal": "works_panorama | problem_solution | comparison | timeline | thesis_evidence | unclear",

  "expected_chapters": <int, 4-10 estimated from slide_count + narrative_signal>,

  "topic_tags": [
    "<3-8 个更宽泛的主题标签, 用于跟资源库 deck 的 主题标签 对齐 (source: topic + user story_style)>"
  ],

  "reuse": {
    "target_rate": <float 0-1, from reuse_policy explicit rate or default 0.6>,
    "must_keep_terms": ["<2-6 术语, 用户明示要保留的关键词>"]
  }
}
```

## 字段生成规则

### topic
- `subject`: 用户 topic 的主语。20 字以内, 不重复 topic 全文
- `sub_topics`: 从 topic + story_style + reuse_policy 挖 2-5 个具体子话题
- `deliverable_type`: **必须**从 enum 选一个:
  - `paper_share`: 学术论文分享
  - `research_report`: 课题组研究成果对外分享 / 内部汇报
  - `tutorial`: 教程 / 综述
  - `proposal`: 立项 / 答辩
  - `other`: 都不合

### audience
- `primary`: 1-2 句话描述听众
- `background_tags`: 3-6 个背景标签 (e.g. "AI 研究者", "体系结构", "工业界")
- `depth`: 期望技术深度
- `jargon_tolerance`: 术语容忍度

### scenario
- `category`: **必须**从 enum 选一个
- `duration_minutes / slide_count`: 直接从 answers 抄，不能为空

### keywords
- 从 topic / story_style / reuse_policy 里的**名词性短语**提取
- **不许**加自己的联想词, 只从原文抽
- 10-20 个之间

### story_mode
- `story_style` 空 → `AUTO`
- `story_style` 含"1./2./3." 或"N 个部分" → `STRICT`
- 其他非空 → `SOFT`

### narrative_signal
- 猜测用户想要的叙事走向 (给下游 IDEA_ANALYSIS 选 meta pattern 用):
  - `works_panorama`: 多工作全景 (关键词含"课题组/多项/成果/全景")
  - `problem_solution`: 问题→方案 (关键词含"问题/解决/挑战")
  - `comparison`: 横向对比 (关键词含"对比/vs")
  - `timeline`: 时序推进 (关键词含"演进/发展/趋势")
  - `thesis_evidence`: 单一主张+证据 (关键词含"证明/结果")
  - `unclear`: 都不像

### expected_chapters
- 按 slide_count 估计: <20p → 3-4; 20-50p → 5-7; 50-100p → 6-9; >100p → 8-10
- 结合 narrative_signal 微调

### topic_tags
- 3-8 个更宽泛的、可跟 material 库里 deck.主题标签 对齐的标签
- 参考 `resource_library_contract.material_topic_tags`（如果给了）

### reuse
- `target_rate`: 从 `reuse_policy` 里的百分比 (e.g. "70%" → 0.7)。没写 → 0.6
- `must_keep_terms`: user 明示"必须保留"的术语 (2-6 个)

## 硬约束

1. **严格 JSON**: `{` 开头 `}` 结尾, 无 markdown code fence
2. **不许多字段**: 顶层只允许上面列的 10 个 (schema_version + 9 语义字段)
3. **不许加 design_hints / citation_preference / style_signal / missing_information / notes_for_downstream 等废弃字段** — driver 一律忽略
4. **不许发明信息**: 用户没提到就不写
5. **enum 字段必须从预定值挑**: `deliverable_type / depth / jargon_tolerance / scenario.category / story_mode / narrative_signal`
