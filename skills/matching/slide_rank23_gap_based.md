# Slide Rank-2/3 Gap-Based Selection Skill

## Purpose

在 rank-1 选定后,基于 **residual_gap** 选 rank-2/3 候选。每个 rank-2/3
必须**实际补 gap**,而不是"凑数"或"按版式选另一张"。

## Inputs (per target page)

- `target_aspects`: 完整的 aspect 列表 (来自 aspect_extraction)
- `rank1`: 上一步选好的 rank-1 候选 (含 covered_aspects / residual_gap)
- `candidate_pool`: 全候选池 (不含 rank-1)

## Selection Logic

### Step 1 — Rank-2 选源

#### 1.1 检查是否需要 rank-2

```
if rank1.residual_gap == [] :
    # rank-1 已 100% 覆盖, 不出 rank-2/3
    return candidates = [rank1]
```

#### 1.2 在 candidate_pool 中找"最能补 residual_gap"的 candidate

对每个 remaining candidate, 评估它**新覆盖**多少 residual_gap aspects:

```
candidate.title / claim / what_this_slide_explains / text_samples / transferable_to
中明确提到 residual_gap 中的某个 aspect 内容 → 算"补 1 个 gap"
```

按"新覆盖 residual_gap 数量"降序排,取最高的作为 rank-2。

#### 1.3 NO ADJACENCY / NO CROSS-DECK CONSTRAINT for rank-2/3

- **NOT required** rank-2 来自不同 deck/section (同 deck 也行)
- **NOT required** rank-2 与 rank-1 邻接或互斥
- 只看一件事: 它能不能补 rank-1 的 residual_gap

#### 1.4 兜底

```
if 所有 remaining candidates 中, 没有一个能补任何 residual_gap aspect :
    # 没有有意义的 rank-2, 不硬凑
    return candidates = [rank1]
```

### Step 2 — Rank-3 选源 (递归地)

```
remaining_gap_after_rank1_2 = residual_gap - rank2.addresses_gap
if remaining_gap_after_rank1_2 == [] :
    return candidates = [rank1, rank2]
# 否则用同样方法找 rank-3 补 remaining_gap_after_rank1_2
```

最多到 rank-3。即使还有 gap,也不出 rank-4。

### Step 3 — 输出 (rank-2/3 schema)

```json
{
  "rank": 2,
  "resource_id": "tpl.yyy.slide_15",
  "deck_id": "tpl.yyy",
  "section_id": "tpl.yyy.sec.02",
  "source_owner": "library",
  "score": 0.78,
  "confidence": 0.78,
  "match_reason": "公式推导细节最完整, 直接补 rank-1 缺失的接受率公式",
  "addresses_gap": [
    "a3: 接受率公式与数学推导",
    "a4: 投机解码概率推导"
  ],
  "covered_aspects": [
    "a3: 接受率公式与数学推导"
  ],
  "parts_to_reuse": "公式块 (接受率推导) + 注释",
  "parts_to_drop": "右侧无关 benchmark 表",
  "relation_to_others": "rank-1 给框架; 本候选补公式推导 (gap a3)",
  "recommended_reuse_mode": "partial_slide_reuse",
  "must_rewrite": ["术语表述与项目对齐"],
  "gap_explanation": ""
}
```

## Hard Rules

### 🚫 NEVER

- 严禁选与 rank-1 内容**完全重复**的 candidate (即 addresses_gap 与 rank-1.covered_aspects 大量重叠)
- 严禁仅因"和 rank-1 不同 deck"而选(已删除 cross-deck 硬规则)
- 严禁仅因 adjacency / 同 deck 偏好而选 rank-2/3 (rank-2/3 完全 gap 驱动)
- 严禁凑数: 若无候选能补 gap, **少出一个 rank** 优于硬凑
- 严禁仅靠版式相似选 rank-2/3 (与 rank-1 同样的语义优先规则)

### ✅ MUST

- `addresses_gap` 必须从 rank1.residual_gap (或 rank-3 时是 rank-1+rank-2 后的 remaining_gap) 中选
- `addresses_gap` 必须**非空** (rank-2/3 存在的唯一理由)
- `covered_aspects` = 本 candidate 实际覆盖的 aspects (可能超出 addresses_gap)
- `relation_to_others` 必须明确说本候选**补哪些 gap**

### 评分标准 (rank-2/3)

- rank-2/3 的 score 通常低于 rank-1 (因为 rank-1 是最对题的)
- 0.80+: 直接、强力地补 residual_gap
- 0.70: 部分补 gap, 但需要用户改写一些
- 0.60: 弱补, 适合"参考思路"
- < 0.60: 不要选

### Length budget

- `match_reason`: ≤ 60 字, 必须提及"补 rank-1 的哪个 gap"
- `parts_to_reuse`: ≤ 80 字
- `parts_to_drop`: ≤ 80 字
- `relation_to_others`: ≤ 60 字, 明确说本候选补哪些 aspects
- `gap_explanation`: ≤ 120 字 (score<0.70 时必填)
