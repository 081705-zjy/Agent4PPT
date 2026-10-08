# Retrieval Match Review Skill

评估**每一页大纲和实际检索到的候选源页之间的匹配质量**。这是 eval 中最关键
的 codex 维度 —— outline 阶段的 `_claim_alignment` 是生成时自打分, 你作为
独立评审读**候选页的实际内容**并给出复核分数。

支持两种调用方:
- **eval CLI**: input 里每个 slide 带 `rank1.source_content_excerpt` (候选页
  markdown 前 1500 字符), 你要**读候选正文**判断是否真能承载目标 claim
- **CODEX_REVIEW pipeline (v30)**: input 里带 **top-level `source_content_excerpts` dict**
  (keyed by resource_id) + **flat slide_matches[]** (resource_id 在顶层, 不在 rank1 嵌套)
  + `source_briefs` 字典 (source 页的 meta). 用这些字段做评审.

## Inputs (可能出现的字段)

```json
{
  "slide_matches": [
    // 两种 schema (union), skill 需能 handle both:
    // Schema A (eval CLI): 每个 slide 有 rank1 嵌套字段
    {
      "target_slide_index": 15,
      "target_role": "method",
      "target_title": "...",
      "target_claim": "...",
      "target_key_points": ["...", "..."],
      "rank1": {
        "resource_id": "tpl.topic.xxx.slide_07",
        "deck_id": "tpl.topic.xxx",
        "score": 5.2,
        "confidence": "high|medium|low",
        "match_reasons": ["...", "..."],
        "source_content_excerpt": "---\n页标识: ...\n核心论断: ...\n本页讲什么: ...\n..."
      }
    },
    // Schema B (v30 pipeline): resource_id/score/confidence 在顶层, 无 rank1 嵌套
    {
      "target_slide_index": 15,
      "target_role": "method",
      "target_title": "...",
      "target_claim": "...",
      "resource_id": "tpl.topic.xxx.slide_07",
      "deck_id": "tpl.topic.xxx",
      "section_id": "tpl.topic.xxx.sec.03",
      "score": 5.2,
      "confidence": "high",
      "match_reason": "..."
    }
  ],
  "source_briefs": {                      // 可选, pipeline 传入时才有
    "<resource_id>": {"title": "...", "claim": "...", "slide_role": "...",
                       "transferable_to": [...], "do_not_reuse_when": [...]}
  },
  "source_content_excerpts": {            // v30 CODEX_REVIEW pipeline 新加
    // top-level dict keyed by resource_id (每 rid 只保存一份, 多 slide 共用一个 excerpt)
    // 每 slide 评审时用 slide_matches[i].resource_id 从此 dict 拿正文摘录
    "<resource_id>": {
      "title": "...", "claim": "...",
      "what_this_slide_explains": "...",
      "key_texts": [...],
      "visual_skeleton": [...],
      "reuse_for": [...]
    }
  }
}
```

**Lookup 规则** (v30 pipeline):
每 slide 评审时先取 `resource_id`:
- Schema A: `slide_matches[i].rank1.resource_id` + `slide_matches[i].rank1.source_content_excerpt` 直接可读
- Schema B: `slide_matches[i].resource_id` + `source_content_excerpts[<resource_id>]` 拿正文

若两种字段都有, 优先用嵌套版本 (rank1). 若只有 Schema B 但 `source_content_excerpts` 里查不到
对应 rid → 说明库里没这源页 (数据问题), 打 content_fit=0 + 报告"资源 ID 无 excerpt".

## What you score per slide (0-100)

对每一 slide, 只看它的 target_claim / target_key_points 和 rank1 候选的
source_content_excerpt (或 source_briefs), 打 3 个子分:

- **content_fit** — 候选页的**核心论断**是否真的能支撑 target_claim? 或者
  只是关键词表面撞车 (topic 相同但立论方向差)?
- **role_fit** — 候选页的 `页面角色` (从 excerpt 或 brief 读) 是否匹配
  target_role? 尤其警惕: content 页选了 cover_candidate / toc_candidate /
  chapter_candidate / ending_candidate (视觉是大字封面, 内容页选它会出现
  "两张连续封面" 视觉伪影)
- **key_points_coverage** — target_key_points 里的具体要点在候选页正文里
  能找到证据吗? 还是要大改内容才能用? (直接照用=100, 改 30%=70, 完全无关=20)

**低匹配 flag**: 只要有一个子分 < 50, 该 slide 归为 `low_match` 并写入
`low_match_pages` 列表。

## Deck-level 汇总

- **deck_score**: 所有 slide 的 mean(min(3 子分))
- **low_match_ratio**: `low_match_pages` 数 / 总 slide 数
- **rank1_confidence_agreement**: rank1.confidence='high' 但你给的三子分
  min < 60 的比例 (这个高说明 outline 阶段的自打分不可信)

## Output (strict JSON, 兼容 CODEX_REVIEW synthesizer)

```json
{
  "dimension": "reuse",
  "score": 72,
  "verdict": "good | needs_revision | major_rework",
  "deck_metrics": {
    "slide_count": 49,
    "low_match_ratio": 0.14,
    "mean_content_fit": 76,
    "mean_role_fit": 88,
    "mean_key_points_coverage": 65,
    "rank1_confidence_agreement": 0.82
  },
  "low_match_pages": [
    {"slide_index": 22, "content_fit": 40, "role_fit": 60, "key_points_coverage": 30,
     "issue": "target_claim 讲 KV cache 压缩, 但 rank1 是稀疏激活 NDP, 只有 '推理加速' 关键词撞车"},
    {"slide_index": 27, "content_fit": 55, "role_fit": 30, "key_points_coverage": 45,
     "issue": "content 页选了 chapter_candidate 版式, 视觉是大字封面不适合内容页"}
  ],
  "critical_issues": [
    {
      "severity": "high | medium | low",
      "slide_indices": [22, 27],
      "issue": "sec 5 method 页 rank1 检索到相关 topic 但立论方向不同, 需 GAP_RESEARCH 补数据",
      "fix_hint": "SLIDE_MATCHING 应加 claim 方向过滤; 或 outline 该页拆为 2 页匹配不同来源"
    }
  ],
  "per_slide": [
    {"slide_index": 1, "content_fit": 95, "role_fit": 100, "key_points_coverage": 90,
     "comment": "cover 完全对题, 直接可用"},
    {"slide_index": 22, "content_fit": 40, "role_fit": 60, "key_points_coverage": 30,
     "comment": "见 low_match_pages[0]"}
  ]
}
```

## Scoring rubric

| score | meaning |
|---|---|
| 90-100 | 每页 rank1 都真的能承载 target_claim, 无 role 错配 |
| 75-89  | 1-3 页需改动 (小规模 rewrite) 后可用 |
| 60-74  | 5+ 页需大改, 或多个 role 错配 |
| 40-59  | 大量页无法直接复用, 需 GAP_RESEARCH 或换检索策略 |
| <40    | 检索基本无效, 需重跑 SLIDE_MATCHING |

## Hard rules

- 只输出 JSON。
- `dimension` 固定为 "reuse"。
- `per_slide` 长度 = slide_matches 长度; 每项 3 个子分必须给出 0-100 整数。
- `low_match_pages` 包含所有 min(3 子分) < 50 的 slide, 按 slide_index 升序。
- `critical_issues` 上限 8 条; 至少 1 条; 每条 slide_indices 是绝对页号。
- `score` = mean(per_slide 的 min(3 子分)); 但**硬扣分**: low_match_ratio >
  0.3 时 score 上限 65。
- 只根据 inputs 判断; 没有 source_content_excerpt 也没有 source_briefs 的
  slide, 给 comment="no source content available, cannot verify" 并把 3 个
  子分设为 rank1.score * 10 (映射 outline 自打分) 作 fallback, 但把它计入
  rank1_confidence_agreement 时视作 "无法确认"。
