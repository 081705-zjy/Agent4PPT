# Speaker Notes Quality Review Skill

Speaker notes (在 pptx 备注区) 是给真人上台讲的脚本。评估每页备注是否完整、可用。

## Inputs

```json
{
  "notes_by_slide": [
    {"slide_index": 1, "target_title": "...", "target_role": "cover",
     "notes_text": "【源页来源】 ...\n【在 PPT 中的位置】 ...\n..."}
  ],
  "expected_blocks": [
    "源页来源", "在 PPT 中的位置", "本页讲什么", "为什么放这里",
    "怎么讲解", "与前后页衔接", "Gap 任务"
  ]
}
```

## What you score per slide

1. **Completeness (0-100)** — 应有的 block 有几个? 缺失关键 block (如「本页讲什么」、「Gap 任务」) 扣大分
2. **Speakability (0-100)** — 备注是否「能让真人按它讲」? 真实场景标准:
   - 「本页讲什么」必须是完整论断句, 不是 stub-padded 占位
   - 「怎么讲解」步骤必须具体 (避免「Open with target_title / Walk through key_points」这种通用占位)
   - 「与前后页衔接」不是 "(stub-padded)" 这种占位文字
3. **Specificity (0-100)** — 备注内容是否针对本页具体内容, 还是 generic 模板
4. **目录页差异说明** — 对 agenda/section_divider 行, 是否有「目录页差异说明 (字面 vs 实际)」block,
   写出源页字面文字 vs 当前章节, 帮演讲者口头转译?

## Deck-level checks

- 多少张 slide 备注是「stub-padded」字样? (大于 5 张 = 严重)
- 多少张 slide 备注 < 100 字符? (太短)
- 多少张 slide 备注完全为空? (空备注 = critical)
- agenda+divider 共享同一源时, 是否每张备注的「本页讲什么」都对应正确的章节 (而不是源页章节)?

## Output (strict JSON)

```json
{
  "dimension": "notes",
  "score": 82,
  "verdict": "good | needs_revision | major_rework",
  "deck_metrics": {
    "avg_notes_length": 850,
    "slides_with_stub_padded": 0,
    "slides_under_100_chars": 0,
    "slides_with_empty_notes": 0,
    "agenda_divider_gap_block_present": "8/8"
  },
  "critical_issues": [
    {
      "severity": "medium",
      "slide_indices": [19],
      "issue": "slide 19 的「怎么讲解」是 generic 占位 (Open with target_title / Walk through key_points), 没有针对成果章节内容",
      "fix_hint": "GAP_CARD sec5 failed → 该 section 走 deterministic-padded; 增大 GAP_CARD timeout 或拆 batch"
    }
  ],
  "per_slide": [
    {"slide_index": 1, "completeness": 100, "speakability": 95, "specificity": 90,
     "comment": "全 block 齐全"},
    {"slide_index": 19, "completeness": 60, "speakability": 30, "specificity": 20,
     "comment": "stub-padded 怎么讲解"}
  ]
}
```

## Scoring

| score | meaning |
|---|---|
| 90-100 | 备注信息密度高, 真人可直接上台讲, 无 stub |
| 75-89  | 个别页 stub / 个别 block 缺失 |
| 60-74  | 多页 stub / 缺关键 block / generic 模板感强 |
| <60    | 大面积空白 / 占位 |

## Hard rules

- 只输出 JSON。
- per_slide 长度 = notes_by_slide 长度。
- 不要虚构 — 只评估 inputs 给的文本。
