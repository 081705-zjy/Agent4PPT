# Outline Logic Review Skill

评估 **大纲本身的逻辑质量** —— 章节切分是否合理、role 编排是否连贯、
页与页之间的论证是否递进、有无跳跃/重复/断层, 以及是否忠实反映 brief 意图。

这个 skill 支持两种调用方:
- **eval CLI** (`ppt_agent_app.eval` — 每次优化后打分): input 里只有 outline 侧信息
- **CODEX_REVIEW pipeline stage**: input 里还带 assembly_plan / section_breakdown

两种 shape 都要能吃; 缺什么字段就不评估那部分, 但**不虚构**。

## Inputs (可能出现的字段)

```json
{
  "topic": "...",
  "slide_count": 49,
  "chapter_to_slide_map": {"1": [1,2,3], "2": [4,5,6,7,8,9,10], ...},
  "selected_narrative_arc": {"primary_pattern_id": "...", "borrowed_patterns": [...]},
  "identity": {"anchor_terms": [...], "topic_tags": [...]},
  "slides": [
    {"slide_index": 1, "chapter_index": 1, "target_role": "cover",
     "target_title": "...", "target_claim": "...", "key_points": [...]}
  ],
  "section_breakdown": [{"section_index": 1, "chapter": "开场与议程",
                          "slide_indices": [1,2,3]}],   // 可选, pipeline 传入时才有
  "assembly_plan": {...}                                  // 可选
}
```

## What you evaluate (每维 0-100)

1. **main_thread_clarity (主线清晰度)** — 通读 slides 的 target_claim, 是否
   能勾勒出一条完整的论证主线? claim 之间是否层层推进? 主线是否呼应 topic /
   anchor_terms?

2. **section_partition (章节切分合理性)** — chapter_to_slide_map 每章页数
   是否均衡? 一章内容是否内聚? 章与章之间有清晰的角色分工 (motivation vs
   method vs discussion)?

3. **role_pacing (role 编排节奏)** — target_role 分布是否合理? 有无长段连续
   同 role (如 15 页连续 method 无 discussion 缓冲)? cover / motivation /
   framework / method / discussion / closing 的比例是否与 narrative arc 匹配?

4. **page_transition (页面过渡逻辑)** — 相邻 slide 的 target_claim 是否有
   逻辑衔接? 是否存在硬跳跃 (前页讲 A, 后页突然讲 B, 中间没桥梁)? 是否
   有重复页 (两页 claim 高度相似)?

5. **arc_coverage (叙事弧覆盖)** — selected_narrative_arc 里承诺的每一段
   (primary_pattern + borrowed_patterns) 是否都能在 slides 里找到对应内容?
   是否有 "承诺了但没兑现" 的段?

## Output (strict JSON, 兼容 CODEX_REVIEW synthesizer)

```json
{
  "dimension": "structure",
  "score": 82,
  "verdict": "good | needs_revision | major_rework",
  "subscores": {
    "main_thread_clarity": 88,
    "section_partition": 80,
    "role_pacing": 75,
    "page_transition": 85,
    "arc_coverage": 82
  },
  "critical_issues": [
    {
      "severity": "high | medium | low",
      "slide_indices": [22, 23, 24, 25, 26, 27, 28],
      "issue": "sec 5 连续 7 张 method role, claim 高度同质 (都在讲算法优化子方向), 缺过渡/收束页",
      "fix_hint": "OUTLINE 应在 sec 5 中间插 1 张 discussion role 做小结, 或拆为 2 段"
    }
  ],
  "strengths": [
    "narrative arc 承诺 3 段全部落地, 每段有专属 chapter",
    "cover→motivation→framework 过渡自然"
  ],
  "summary_zh": "整体主线清晰, 章节切分基本合理; 主要问题在 sec5 role 单一造成节奏拖沓。"
}
```

## Scoring rubric

| score | meaning |
|---|---|
| 90-100 | 主线清晰, role 均衡, 无跳跃/重复, arc 全覆盖 |
| 75-89  | 1-2 处 role 单一或轻微跳跃, 不影响整体逻辑 |
| 60-74  | 多处过渡突兀 / 某章明显单薄或过度膨胀 / arc 兑现不全 |
| 40-59  | 主线断裂, role 编排失衡 |
| <40    | 章节切分混乱, 无法读出论证脉络 |

## Hard rules

- 只输出 JSON, 不要 markdown 围栏。
- `dimension` 必须固定为 "structure" (保持 synthesizer 兼容)。
- `subscores` 5 项必须全部给出。
- `critical_issues` 上限 8 条; 至少给 1 条 (真无问题也要说明 "无严重问题, xxx 得高分")。
- `slide_indices` 是绝对页号 (从 outline.slides[*].slide_index 读), 不用 chapter 内页号。
- 不虚构 — 只评估 inputs 提供的数据; 缺字段就不评那维, 给 subscore=null 并在 summary 说明。
- `score` 是 5 个 subscore 的加权均值 (等权即可), 但允许**硬扣分**:
  - main_thread_clarity < 60: 整体 score 上限 70
  - arc_coverage < 50: 整体 score 上限 65
