# Review Synthesizer Skill

你拿到 4 个子 skill (reuse / structure / notes / narrative) 各自的评分结果,
你的任务是**综合成 deck-level 总分 + 行动清单**。

## Inputs

```json
{
  "dimensions": {
    "reuse":      { "score": 78, "verdict": "...", "critical_issues": [...], ...},
    "structure":  { "score": 85, ...},
    "notes":      { "score": 82, ...},
    "narrative":  { "score": 76, ...}
  },
  "project_meta": {
    "project_id": "...", "version": "v9",
    "slide_count": 52, "matched_count": 47, "matched_rate": 0.90
  }
}
```

## What you produce

1. **Overall score (0-100)** = 4 维加权平均 (默认等权 25%); 但允许**结构性硬扣分**:
   - structure < 70: overall 上限 75
   - reuse < 60: overall 上限 70 (复用差则整体不可用)
2. **Verdict**:
   - `good` (overall ≥ 85): 可以发给用户预览
   - `needs_revision` (70-84): 有明显问题, 重跑 1-2 个阶段
   - `major_rework` (< 70): 需要回到 OUTLINE / MATCHING 改逻辑
3. **Top 3 critical issues** — 从 4 维的 critical_issues 里挑最严重的 3 个
4. **Top 5 action items** — 可执行的修复建议, 按优先级排
5. **Pipeline regression flags** — 与上一版比较 (如有 project_meta.previous_version), 哪些维度退化了

## Output (strict JSON)

```json
{
  "schema_version": "1.0",
  "project_id": "software-hardware-cooperate_v9",
  "version": "v9",
  "scores": {
    "reuse": 78,
    "structure": 85,
    "notes": 82,
    "narrative": 76,
    "visual": null,
    "overall": 80
  },
  "verdict": "needs_revision",
  "summary_zh": "v9 复用率 90% 达标但仍有 2 处内容页错选章节封面源; 结构完整; 备注总体可用但 sec5 22 页 stub-padded; 叙事章内流畅但 sec5 缺过渡。建议重跑 GAP_CARD sec5 (增 timeout) 和给 MATCHING 加严格 role isolation。",
  "critical_issues": [
    {"severity": "high", "dimension": "reuse",
     "slide_indices": [15], "issue": "slide 15 chapter_candidate 误选造成连续视觉伪影",
     "fix_hint": "..."},
    {"severity": "medium", "dimension": "notes",
     "slide_indices": [19,20,21,22,23,24,25,26,27,28,29,30,31,32,33,34,35,36,37,38,39,40],
     "issue": "sec5 全章备注 stub-padded",
     "fix_hint": "GAP_CARD sec5 增 timeout / 拆 batch"}
  ],
  "action_items": [
    {"rank": 1, "action": "MATCHING 加 role isolation 硬规则 (内容页禁选 chapter/toc/cover/ending_candidate)", "owner": "stage_runner.py"},
    {"rank": 2, "action": "GAP_CARD sec5 timeout 增大 + 拆为 11+11 子批", "owner": "stage_runner.py"},
    {"rank": 3, "action": "OUTLINE skill 显式禁止 method/result 等内容页与 agenda role 同位置", "owner": "skills/outline_gen/deck_outline.md"}
  ],
  "regression_flags": []
}
```

## Hard rules

- 只输出 JSON。
- overall = round(weighted avg), 整数。
- 当任何维度 verdict=major_rework, overall verdict 必须是 needs_revision 或 major_rework。
- critical_issues 至少 1 项, 最多 5 项。
- action_items 1-5 项。
- summary_zh 中文一段话 (≤200 字), 让用户一眼看明白。
