# Draft Coherence Review Skill

评估**最终 draft 的整体故事逻辑** —— 通读 draft-manuscript.md + speaker-notes.md,
从**听众视角**判断这份 deck 讲下来是否顺畅、有无重复/断层/矛盾, 备注是否配合正文。

这是从"生成产物"角度打分, 与 `structure_review` (评大纲骨架) 互补。

支持两种调用方:
- **eval CLI**: input 里带 `draft_manuscript_excerpt` + `speaker_notes_excerpt`
  (拼接后的完整草稿; 超长时头尾截取, 中间省略)
- **CODEX_REVIEW pipeline (stage 8)**: input 里带 outline_slides + section_breakdown +
  gap_cards + speaker_notes_by_slide (dict, keyed by slide_index).
  **注意**: `manuscript_status = "draft_stub_pre_slide_rewrite"` 时说明
  draft-manuscript.md 是 stub (真正 on-slide copy 由后续 SLIDE_REWRITE 填, 而 CODEX_REVIEW
  在 stage 8 就跑了 → 拿不到最终 manuscript). 此时 narrative 评分应基于 outline_slides +
  section_breakdown + speaker_notes_by_slide, **不要因 manuscript 缺失或看到 stub 内容
  扣分**. 这是设计使然, 不是 deck 质量问题.

## Inputs (可能出现的字段)

```json
{
  "topic": "...",
  "slide_count": 49,
  "chapter_to_slide_map": {"1": [1,2,3], "2": [4,...]},
  "draft_manuscript_excerpt": "## Slide 1: ...\nOn-slide copy: ...\n\n---\n\n## Slide 2: ...",
  "speaker_notes_excerpt":    "## Slide 1: ...\n【本页讲什么】...\n【怎么讲解】...",
  "outline_slides": [...],                // 可选 (pipeline 模式)
  "section_breakdown": [...],             // 可选
  "gap_cards": [...]                      // 可选
}
```

## What you evaluate (每维 0-100)

1. **narrative_flow** — 从头到尾读一遍, 故事有没有开头→中段→收束? 有没有
   突兀的话题跳转 (前页在讲能效动机, 后页突然进产业趋势, 中间该有的过渡缺失)?

2. **section_transition** — 每章末页 → 下章首页的衔接是否自然? 单靠
   section_divider 切换、还是备注里有内容层面的桥梁? 章内也要看 (章内页
   转换是否流畅)。

3. **claim_consistency** — 整份 deck 提到的关键 claim 是否前后一致?
   有没有 slide A 说 "方法 X 领先 30%", slide B 又说 "方法 X 只快 5%"
   这种数字/立场自相矛盾? 术语 (anchor_terms) 是否稳定?

4. **redundancy_control** — 有没有 2+ slide 讲同一件事 (key_points 高度
   重叠、备注内容相似)? take-away / summary 页是否过于密集重复?

5. **notes_body_alignment** — speaker_notes 里的 "本页讲什么" / "怎么讲解"
   是否**真的对应** manuscript 里的 on-slide copy? 有没有备注是通用模板
   (如 "Open with target_title / Walk through key_points" 这种未填充占位)?
   有没有 "(stub-padded)" 之类的未完成标记?

## Output (strict JSON, 兼容 CODEX_REVIEW synthesizer)

```json
{
  "dimension": "narrative",
  "score": 78,
  "verdict": "good | needs_revision | major_rework",
  "subscores": {
    "narrative_flow": 82,
    "section_transition": 75,
    "claim_consistency": 88,
    "redundancy_control": 70,
    "notes_body_alignment": 76
  },
  "section_scores": [
    {"chapter_index": 1, "chapter": "开场", "flow": 90, "exit_to_next": 85,
     "comment": "封面→个人介绍→过渡到 motivation 自然"},
    {"chapter_index": 5, "chapter": "代表性成果", "flow": 60, "exit_to_next": 70,
     "comment": "连续 22 张同类型成果页, 缺中段小结, 观众易疲劳"}
  ],
  "duplicate_slides_warning": [
    {"slide_indices": [37, 38, 39], "issue": "take-away 三张高度相似, 建议合并为 1"}
  ],
  "hard_jumps": [
    {"between_slides": [10, 11],
     "issue": "从'能效动机总结'直接跳到'算法层方法总览', 中间该有'框架总览'过渡"}
  ],
  "critical_issues": [
    {
      "severity": "high | medium | low",
      "slide_indices": [22, 23, 24, 25, 26, 27, 28],
      "issue": "sec 5 全章备注都是 '(stub-padded)' 占位, speaker 无法照讲",
      "fix_hint": "GAP_CARD sec5 重跑 (增 timeout 或拆 batch)"
    }
  ],
  "summary_zh": "整体故事线成立但 sec5 备注 stub-padded 严重, 且 sec5 缺过渡; 建议重跑 GAP_CARD sec5。"
}
```

## Scoring rubric

| score | meaning |
|---|---|
| 90-100 | 从头到尾读得下来, 有开头/发展/收束; 无跳跃/重复/占位 |
| 75-89  | 1-2 处小跳跃或轻微重复, 备注基本可用 |
| 60-74  | 多处跳跃/重复, 或整章备注 stub-padded 无法讲 |
| 40-59  | 故事线断裂, 大量占位, 无法直接讲 |
| <40    | draft 不成篇, 需重跑 |

## Hard rules

- 只输出 JSON。
- `dimension` 固定为 "narrative"。
- `subscores` 5 项必须全部给出 (缺信号那项给 null 并在 summary 说明)。
- `section_scores` 长度尽量等于 chapter_to_slide_map 的 chapter 数; 只在
  该章有足够信号 (manuscript 覆盖到该章) 时打分。
- `duplicate_slides_warning` 和 `hard_jumps` 只列**明显问题**, 不虚构。
- `critical_issues` 上限 8 条, 至少 1 条。
- `score` 是 5 subscore 的加权均值 (等权); 硬扣分:
  - notes_body_alignment < 50: 整体 score 上限 65 (备注不可用就没法讲)
  - claim_consistency < 60: 整体 score 上限 70 (自相矛盾比空更糟)
- 严禁根据主题猜内容; 只评估 inputs 提供的文本。
