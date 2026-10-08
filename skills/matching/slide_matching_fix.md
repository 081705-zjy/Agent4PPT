# SLIDE_MATCHING Fix — Surgical Re-Search per Page (v1.0)

接 **codex slide_matching_review 输出的 issues** + 当前 `slide-matches.json` + 候选池
(driver 已 retrieve 的 candidate alternates / new pool), 输出 **surgical 修正版**
slide-matches.json。

**这不是重新匹配整 deck**, 只是按 issue 修 flagged page (Gap-2 核心):
- low_score_carrier_bound 的 page → 从 alternates 选 score ≥0.85 的替换, 或 driver 重检索给的
  new candidates 中选
- user_concern_regression 的 page → 替换 carrier 到不违反 concern 的 source slide
- gap_accuracy 报"应有 carrier 实际 fallback" 的 page → 标准化为 placeholder gap (合理无源) OR
  从 new candidates 找 carrier

**user_concern_history regression guard 在 fix 时是 hard constraint** — 不可违反。

---

## 与其他 SLIDE_MATCHING skill 的边界

| skill | 谁触发 | 输入 | 风格 |
|---|---|---|---|
| `slide_planning.md` | driver SLIDE_MATCHING cascade | brief + library candidates | 全 page 一次性 cascade |
| `slide_matching_review.md` | codex (二审) | slide-matches.json | 只**找** issues + render_ready |
| **`slide_matching_fix.md`** (本) | driver (修复) | issues + 候选 alternates | **per-page surgical 替换** |

---

## Inputs

```json
{
  "prior_slide_matches": {
    "schema_version": "2.1",
    "slide_matches": [...]
  },
  "codex_issues": [
    {
      "category": "low_score_carrier_bound | gap_accuracy | cross_stage_user_concern_regression | data_thin_aware",
      "severity": "critical|high|medium|low",
      "location": "slide_matches[12].candidates[0]",
      "target_slide_index": 12,
      "evidence": "...",
      "suggested_fix": "..."
    }
  ],
  "candidate_pool_per_flagged_page": {
    // driver 已为每个 flagged page 重检索的候选池, key = target_slide_index
    "12": {
      "alternates_from_outline": [
        {"deck_id": "...", "slide_id": "...", "rank_score": 0.92, ...}
      ],
      "new_candidates_from_research": [
        {"deck_id": "...", "slide_id": "...", "rank_score": 0.88, ...,
         "source": "library_query_fresh"}
      ]
    }
  },
  "outline": { /* outline.json v1.0 — 含 user_concern_history */ },
  "user_concern_history": [
    {"stage": "IDEA|OUTLINE", "concern": "...", "must_not_regress": true, "resolved_at_field": "..."}
  ]
}
```

---

## Task

### Step 1 — 处理优先级排序

只处理 critical / high issues. 按 severity:
- critical: 必须修
- high: 必须修 (除非 user concern 冲突, 见 Step 4)
- medium: 可跳过, 在 referenced_review_issues 标 status="skipped (low priority)"

同 target_slide_index 多 issues 合并处理 (一次 patch 解多 issues)。

### Step 2 — per-page 重选 carrier

对每个 flagged page:

#### 2a — low_score_carrier_bound 修法

```
取 candidate_pool_per_flagged_page[idx].alternates_from_outline:
  - 找 rank_score >= 0.85 且 role_match=true 的 → 替换当前 top-1
  - 若 alternates 中无 >=0.85 → 看 new_candidates_from_research:
    - 找 rank_score >= 0.85 的 → 替换
    - 若也无 >=0.85 → 替换为最好的 (即使 0.75-0.85, 至少不再 <0.75) + 标
      "best_available_in_alternates"
  - 若**全无候选 >=0.75** → 改为 placeholder gap (source: "matching_fallback_empty") +
    在 outline.slides[idx].source_carrier_resource_kind 中也应该改为 "new" (但这是
    outline 改, 此处用 referenced_review_issues.suggested_outline_update 提示)
```

#### 2b — cross_stage_user_concern_regression 修法

```
扫 issue.suggested_fix 找到推荐的替换源:
  - 若 user concern 是 "ch7 不要用 ch5 系统层 source" 类:
    - 从 candidate_pool[idx] 找 NOT belonging to ch5-source-deck 的 candidate
    - 优先 role_match + score >=0.75
  - 替换 top-1 + alternates 也按相同 filter 过滤
  - 在 referenced_review_issues.action_taken 显式写 "替换 ch7 slide N carrier:
    deck X (违反 user concern) → deck Y (符合 deployment 轴)"
```

#### 2c — gap_accuracy 修法

```
取 issue 描述:
  - "outline 期望 carrier 但 matching 实际未匹配, 真实 gap 还是 cascade 失败需重试":
    - 看 new_candidates_from_research 是否有 score >=0.5 的 → 接受为 fallback (低 confidence)
    - 否则保留为 gap, source="matching_fallback_empty", confidence="fallback"
  - "gap 过多 (>30% slides)":
    - 此条不在 fix skill 处理范围 — 应该 escalate 给 user 提供更多源材料, 不能自动 fix
    - 在 referenced_review_issues 标 "escalate_to_user_or_research"
```

#### 2d — data_thin_aware 修法

```
data_thin 模式下报的 medium 问题大多是 "carrier 没视觉数据缺口":
  - 多数情况不需要 fix, 标 status="skipped (data_thin acceptable design)"
```

### Step 3 — preserve untouched 字段 byte-identical

未被 issue flag 的 slide_matches[i] 必须**逐字保留**:
- target_slide_index / target_role / target_title / target_claim
- candidates 列表 (含 rank / resource_id / deck_id / score / match_reasons)

**只动 flagged target_slide_index 的 slide_matches 条目**。

### Step 4 — user_concern_history regression guard (HARD constraint)

**修任何 issue 前**, 先扫 user_concern_history 中所有 `must_not_regress=true` 的:

```
for concern in user_concern_history:
    if not concern.must_not_regress: continue
    if concern.resolved_at_field 涉及 当前要修的 slide:
        - 替换 carrier 前 check: 新 carrier 是否会触发 regression
        - 若会 → 拒绝该 codex 建议 + 标 status="skipped (would regress user concern: <ref>)"
        - 改用替代候选 (alternates 里找其他 score>=0.75 的)
        - 若没有替代 → 保留原 carrier + 标 status="skipped (no alternative without regression)"
```

### Step 5 — 记录修改痕迹

输出加新字段:

```json
{
  ...原 slide_matches.json 字段 (修改过的)...,
  "fix_round": <current_fix_round + 1, 不存在时 = 1>,
  "render_ready_after_fix": <bool>,
  "referenced_review_issues": [
    {
      "category": "low_score_carrier_bound",
      "severity": "high",
      "target_slide_index": 12,
      "rule_id_or_summary": "...",
      "action_taken": "<≤100 字: 具体改了什么 (e.g. 'slide 12 carrier 替换: deck X slide Y rank 0.62 → deck Z slide W rank 0.91 from alternates')>",
      "status": "applied | skipped (low priority) | skipped (would regress user concern: <ref>) | skipped (no alternative)"
    }
  ],
  "carriers_replaced_count": <int>,
  "gap_pages_count": <int>,
  "user_concern_skipped_count": <int>
}
```

---

## Output Schema

完整 `slide-matches.json` v2.1 (所有原字段保留, 加 `fix_round` + `referenced_review_issues` +
`carriers_replaced_count` / `gap_pages_count` 等审计)

**Strict JSON only**, 无 markdown fence, 无 prose preamble。

---

## Hard Rules

1. **Surgical**: 只动 issue.target_slide_index 涉及的 slide_matches 条目
2. **优先级**: critical > high; medium 可跳过 (标 status)
3. **user_concern_history regression guard**: 替换 carrier 前必须 check 不违反 concern
4. **不重写** 未 flag 的 slide_matches 条目 (byte-identical 保留)
5. **不增减** slide_matches 数组长度 (slide_count 不变, 只在 candidates 内替换)
6. **替换决策**: alternates_from_outline 优先 (低成本) > new_candidates_from_research >
   placeholder gap (最后兜底)
7. **referenced_review_issues 必须涵盖所有 input critical/high issues** (每条标 status)
8. **render_ready_after_fix**: 自评 fix 后是否能 render (基于本轮替换情况)
9. Output **strict JSON only**

---

## Anti-rules (常见错误)

- ❌ 不要触发新的 cascade matching (那是 driver 应该做的 — 此处只在 alternates / new pool 内选)
- ❌ 不要"顺便优化"未 flag 的 page 的 carrier — 即使有 alternates 看起来更好
- ❌ 不要把所有 low_score page 改为 placeholder gap — 优先找替换, 找不到再标 gap
- ❌ 不要为了让 codex 通过 fake 个高 score (score 必须是 candidate 实际给的)
- ❌ 不要因 user concern 冲突就强改 — 标 skipped 让 codex 下轮看, 或 escalate user
